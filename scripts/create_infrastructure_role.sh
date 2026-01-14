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
                "iam:ListAttachedRolePolicies"
            ],
            "Resource": [
                "arn:aws:iam::${ACCOUNT_ID}:role/tfc-*",
                "arn:aws:iam::${ACCOUNT_ID}:role/github-actions-*"
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
