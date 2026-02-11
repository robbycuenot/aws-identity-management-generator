#!/bin/bash
# =============================================================================
# Create IAM Role for Infrastructure Module Deployment
# =============================================================================
# This script creates an IAM role that allows Terraform Cloud to deploy the
# aws-identity-management-generator infrastructure module via OIDC.
#
# Run this in AWS CloudShell on your Identity Center account.
#
# Prerequisites:
#   - AWS CLI configured with appropriate permissions
#   - Terraform Cloud organization, project, and workspace created
# =============================================================================

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}=== Infrastructure Module Deployment Role Setup ===${NC}"
echo ""

# Use environment variables (set before piping script)
if [ -z "$TFC_ORG" ] || [ -z "$TFC_PROJECT" ] || [ -z "$TFC_WORKSPACE" ]; then
    echo -e "${RED}Error: TFC_ORG, TFC_PROJECT, and TFC_WORKSPACE environment variables are required${NC}"
    echo ""
    echo "Run this first:"
    echo '  read -p "TFC Organization: " TFC_ORG && \'
    echo '  read -p "TFC Project: " TFC_PROJECT && \'
    echo '  read -p "TFC Workspace: " TFC_WORKSPACE && \'
    echo '  export TFC_ORG TFC_PROJECT TFC_WORKSPACE'
    exit 1
fi

ROLE_NAME="tfc-identity-management-infrastructure"
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)

echo ""
echo -e "${YELLOW}Creating resources in account: ${ACCOUNT_ID}${NC}"
echo ""

# Check if OIDC provider exists
OIDC_PROVIDER_ARN="arn:aws:iam::${ACCOUNT_ID}:oidc-provider/app.terraform.io"
if aws iam get-open-id-connect-provider --open-id-connect-provider-arn "$OIDC_PROVIDER_ARN" &>/dev/null; then
    echo -e "${GREEN}✓ TFC OIDC provider already exists${NC}"
else
    echo "Creating TFC OIDC provider..."
    THUMBPRINT=$(openssl s_client -servername app.terraform.io -showcerts -connect app.terraform.io:443 </dev/null 2>/dev/null | openssl x509 -fingerprint -sha1 -noout | cut -d'=' -f2 | tr -d ':' | tr '[:upper:]' '[:lower:]')
    
    aws iam create-open-id-connect-provider \
        --url "https://app.terraform.io" \
        --client-id-list "aws.workload.identity" \
        --thumbprint-list "$THUMBPRINT" \
        --tags Key=Name,Value=tfc-oidc-provider Key=ManagedBy,Value=create_infrastructure_role.sh
    
    echo -e "${GREEN}✓ TFC OIDC provider created${NC}"
fi

# Check if GitHub OIDC provider exists
GITHUB_OIDC_PROVIDER_ARN="arn:aws:iam::${ACCOUNT_ID}:oidc-provider/token.actions.githubusercontent.com"
if aws iam get-open-id-connect-provider --open-id-connect-provider-arn "$GITHUB_OIDC_PROVIDER_ARN" &>/dev/null; then
    echo -e "${GREEN}✓ GitHub OIDC provider already exists${NC}"
else
    echo "Creating GitHub OIDC provider..."
    GITHUB_THUMBPRINT=$(openssl s_client -servername token.actions.githubusercontent.com -showcerts -connect token.actions.githubusercontent.com:443 </dev/null 2>/dev/null | openssl x509 -fingerprint -sha1 -noout | cut -d'=' -f2 | tr -d ':' | tr '[:upper:]' '[:lower:]')
    
    aws iam create-open-id-connect-provider \
        --url "https://token.actions.githubusercontent.com" \
        --client-id-list "sts.amazonaws.com" \
        --thumbprint-list "$GITHUB_THUMBPRINT" \
        --tags Key=Name,Value=github-actions-oidc-provider Key=ManagedBy,Value=create_infrastructure_role.sh
    
    echo -e "${GREEN}✓ GitHub OIDC provider created${NC}"
fi

# Create trust policy
TRUST_POLICY=$(cat <<EOF
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Principal": {
                "Federated": "${OIDC_PROVIDER_ARN}"
            },
            "Action": "sts:AssumeRoleWithWebIdentity",
            "Condition": {
                "StringEquals": {
                    "app.terraform.io:aud": "aws.workload.identity"
                },
                "StringLike": {
                    "app.terraform.io:sub": "organization:${TFC_ORG}:project:${TFC_PROJECT}:workspace:${TFC_WORKSPACE}:run_phase:*"
                }
            }
        }
    ]
}
EOF
)

# Create permissions policy (least privilege for infrastructure module)
PERMISSIONS_POLICY=$(cat <<EOF
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "IAMOIDCProviderManagement",
            "Effect": "Allow",
            "Action": [
                "iam:CreateOpenIDConnectProvider",
                "iam:DeleteOpenIDConnectProvider",
                "iam:GetOpenIDConnectProvider",
                "iam:ListOpenIDConnectProviders",
                "iam:TagOpenIDConnectProvider",
                "iam:UntagOpenIDConnectProvider",
                "iam:UpdateOpenIDConnectProviderThumbprint"
            ],
            "Resource": "*"
        },
        {
            "Sid": "IAMRoleManagement",
            "Effect": "Allow",
            "Action": [
                "iam:CreateRole",
                "iam:DeleteRole",
                "iam:GetRole",
                "iam:UpdateRole",
                "iam:TagRole",
                "iam:UntagRole",
                "iam:ListRoleTags",
                "iam:UpdateAssumeRolePolicy",
                "iam:GetRolePolicy",
                "iam:PutRolePolicy",
                "iam:DeleteRolePolicy",
                "iam:ListRolePolicies",
                "iam:AttachRolePolicy",
                "iam:DetachRolePolicy",
                "iam:ListAttachedRolePolicies",
                "iam:ListInstanceProfilesForRole",
                "iam:PassRole"
            ],
            "Resource": [
                "arn:aws:iam::${ACCOUNT_ID}:role/tfc-*",
                "arn:aws:iam::${ACCOUNT_ID}:role/github-actions-*",
                "arn:aws:iam::${ACCOUNT_ID}:role/*-tfc-agent-*"
            ]
        },
        {
            "Sid": "IAMPolicyRead",
            "Effect": "Allow",
            "Action": [
                "iam:GetPolicy",
                "iam:GetPolicyVersion"
            ],
            "Resource": "arn:aws:iam::aws:policy/*"
        },
        {
            "Sid": "IAMServiceLinkedRole",
            "Effect": "Allow",
            "Action": [
                "iam:CreateServiceLinkedRole"
            ],
            "Resource": [
                "arn:aws:iam::${ACCOUNT_ID}:role/aws-service-role/ecs.amazonaws.com/*",
                "arn:aws:iam::${ACCOUNT_ID}:role/aws-service-role/pullthroughcache.ecr.amazonaws.com/*"
            ]
        },
        {
            "Sid": "ECSManagement",
            "Effect": "Allow",
            "Action": [
                "ecs:CreateCluster",
                "ecs:DeleteCluster",
                "ecs:DescribeClusters",
                "ecs:UpdateCluster",
                "ecs:PutClusterCapacityProviders",
                "ecs:TagResource",
                "ecs:UntagResource",
                "ecs:ListTagsForResource",
                "ecs:RegisterTaskDefinition",
                "ecs:DeregisterTaskDefinition",
                "ecs:DescribeTaskDefinition",
                "ecs:ListTaskDefinitions",
                "ecs:DescribeTasks",
                "ecs:ListTasks",
                "ecs:StopTask",
                "ecs:RunTask"
            ],
            "Resource": "*"
        },
        {
            "Sid": "LambdaManagement",
            "Effect": "Allow",
            "Action": [
                "lambda:CreateFunction",
                "lambda:DeleteFunction",
                "lambda:GetFunction",
                "lambda:GetFunctionConfiguration",
                "lambda:GetFunctionCodeSigningConfig",
                "lambda:UpdateFunctionCode",
                "lambda:UpdateFunctionConfiguration",
                "lambda:ListVersionsByFunction",
                "lambda:PublishVersion",
                "lambda:AddPermission",
                "lambda:RemovePermission",
                "lambda:GetPolicy",
                "lambda:TagResource",
                "lambda:UntagResource",
                "lambda:ListTags"
            ],
            "Resource": "arn:aws:lambda:*:${ACCOUNT_ID}:function:*-tfc-agent-*"
        },
        {
            "Sid": "APIGatewayManagement",
            "Effect": "Allow",
            "Action": [
                "apigateway:POST",
                "apigateway:GET",
                "apigateway:DELETE",
                "apigateway:PATCH",
                "apigateway:PUT",
                "apigateway:TagResource",
                "apigateway:UntagResource"
            ],
            "Resource": [
                "arn:aws:apigateway:*::/apis",
                "arn:aws:apigateway:*::/apis/*",
                "arn:aws:apigateway:*::/tags/*"
            ]
        },
        {
            "Sid": "SecretsManagerManagement",
            "Effect": "Allow",
            "Action": [
                "secretsmanager:CreateSecret",
                "secretsmanager:DeleteSecret",
                "secretsmanager:DescribeSecret",
                "secretsmanager:GetSecretValue",
                "secretsmanager:PutSecretValue",
                "secretsmanager:UpdateSecret",
                "secretsmanager:TagResource",
                "secretsmanager:UntagResource",
                "secretsmanager:GetResourcePolicy",
                "secretsmanager:PutResourcePolicy",
                "secretsmanager:DeleteResourcePolicy"
            ],
            "Resource": [
                "arn:aws:secretsmanager:*:${ACCOUNT_ID}:secret:*-tfc-agent-*",
                "arn:aws:secretsmanager:*:${ACCOUNT_ID}:secret:ecr-pullthroughcache/*"
            ]
        },
        {
            "Sid": "CloudWatchLogsManagement",
            "Effect": "Allow",
            "Action": [
                "logs:CreateLogGroup",
                "logs:DeleteLogGroup",
                "logs:DescribeLogGroups",
                "logs:PutRetentionPolicy",
                "logs:DeleteRetentionPolicy",
                "logs:TagResource",
                "logs:UntagResource",
                "logs:ListTagsForResource",
                "logs:TagLogGroup",
                "logs:UntagLogGroup",
                "logs:ListTagsLogGroup",
                "logs:CreateLogDelivery",
                "logs:DeleteLogDelivery",
                "logs:GetLogDelivery",
                "logs:ListLogDeliveries",
                "logs:UpdateLogDelivery",
                "logs:PutResourcePolicy",
                "logs:DescribeResourcePolicies"
            ],
            "Resource": "*"
        },
        {
            "Sid": "ECRPullThroughCache",
            "Effect": "Allow",
            "Action": [
                "ecr:CreatePullThroughCacheRule",
                "ecr:DeletePullThroughCacheRule",
                "ecr:DescribePullThroughCacheRules",
                "ecr:ValidatePullThroughCacheRule"
            ],
            "Resource": "*"
        },
        {
            "Sid": "ECRRepositoryManagement",
            "Effect": "Allow",
            "Action": [
                "ecr:DescribeRepositories",
                "ecr:DeleteRepository",
                "ecr:ListImages",
                "ecr:BatchDeleteImage",
                "ecr:GetRepositoryPolicy",
                "ecr:SetRepositoryPolicy",
                "ecr:DeleteRepositoryPolicy",
                "ecr:TagResource",
                "ecr:UntagResource",
                "ecr:ListTagsForResource"
            ],
            "Resource": "arn:aws:ecr:*:${ACCOUNT_ID}:repository/docker-hub/*"
        },
        {
            "Sid": "EC2SecurityGroupManagement",
            "Effect": "Allow",
            "Action": [
                "ec2:CreateSecurityGroup",
                "ec2:DeleteSecurityGroup",
                "ec2:DescribeSecurityGroups",
                "ec2:DescribeSecurityGroupRules",
                "ec2:AuthorizeSecurityGroupEgress",
                "ec2:RevokeSecurityGroupEgress",
                "ec2:AuthorizeSecurityGroupIngress",
                "ec2:RevokeSecurityGroupIngress",
                "ec2:CreateTags",
                "ec2:DeleteTags",
                "ec2:DescribeTags"
            ],
            "Resource": "*"
        },
        {
            "Sid": "EC2VPCRead",
            "Effect": "Allow",
            "Action": [
                "ec2:DescribeVpcs",
                "ec2:DescribeSubnets"
            ],
            "Resource": "*"
        },
        {
            "Sid": "DynamoDBAgentState",
            "Effect": "Allow",
            "Action": [
                "dynamodb:CreateTable",
                "dynamodb:DeleteTable",
                "dynamodb:DescribeTable",
                "dynamodb:UpdateTable",
                "dynamodb:DescribeTimeToLive",
                "dynamodb:UpdateTimeToLive",
                "dynamodb:TagResource",
                "dynamodb:UntagResource",
                "dynamodb:ListTagsOfResource",
                "dynamodb:DescribeContinuousBackups"
            ],
            "Resource": "arn:aws:dynamodb:*:${ACCOUNT_ID}:table/*-tfc-agent-*"
        },
        {
            "Sid": "EventBridgeScheduler",
            "Effect": "Allow",
            "Action": [
                "scheduler:CreateSchedule",
                "scheduler:DeleteSchedule",
                "scheduler:GetSchedule",
                "scheduler:UpdateSchedule",
                "scheduler:ListSchedules",
                "scheduler:TagResource",
                "scheduler:UntagResource",
                "scheduler:ListTagsForResource"
            ],
            "Resource": "arn:aws:scheduler:*:${ACCOUNT_ID}:schedule/default/*-tfc-agent-*"
        },
        {
            "Sid": "IAMSchedulerRole",
            "Effect": "Allow",
            "Action": [
                "iam:CreateRole",
                "iam:DeleteRole",
                "iam:GetRole",
                "iam:UpdateRole",
                "iam:UpdateAssumeRolePolicy",
                "iam:TagRole",
                "iam:UntagRole",
                "iam:ListRoleTags",
                "iam:PutRolePolicy",
                "iam:GetRolePolicy",
                "iam:DeleteRolePolicy",
                "iam:ListRolePolicies",
                "iam:ListAttachedRolePolicies",
                "iam:PassRole"
            ],
            "Resource": "arn:aws:iam::${ACCOUNT_ID}:role/*-tfc-agent-scheduler-role"
        }
    ]
}
EOF
)

# Check if role exists
if aws iam get-role --role-name "$ROLE_NAME" &>/dev/null; then
    echo "Updating existing role..."
    aws iam update-assume-role-policy --role-name "$ROLE_NAME" --policy-document "$TRUST_POLICY"
    aws iam put-role-policy --role-name "$ROLE_NAME" --policy-name "infrastructure-deployment" --policy-document "$PERMISSIONS_POLICY"
    echo -e "${GREEN}✓ Role updated${NC}"
else
    echo "Creating role..."
    aws iam create-role \
        --role-name "$ROLE_NAME" \
        --assume-role-policy-document "$TRUST_POLICY" \
        --description "Role for deploying aws-identity-management-generator infrastructure module" \
        --tags Key=Name,Value="$ROLE_NAME" Key=ManagedBy,Value=create_infrastructure_role.sh
    
    aws iam put-role-policy --role-name "$ROLE_NAME" --policy-name "infrastructure-deployment" --policy-document "$PERMISSIONS_POLICY"
    echo -e "${GREEN}✓ Role created${NC}"
fi

ROLE_ARN="arn:aws:iam::${ACCOUNT_ID}:role/${ROLE_NAME}"

echo ""
echo -e "${GREEN}=== Setup Complete ===${NC}"
echo ""
echo "Add these environment variables to your TFC workspace:"
echo ""
echo -e "${YELLOW}TFC_AWS_PROVIDER_AUTH${NC} = true"
echo -e "${YELLOW}TFC_AWS_RUN_ROLE_ARN${NC}  = ${ROLE_ARN}"
echo ""
echo "Note: The OIDC providers were created/verified. Set these variables"
echo "in your infrastructure module to skip creating them again:"
echo ""
echo "  create_aws_tfc_oidc_provider    = false"
echo "  create_aws_github_oidc_provider = false"
