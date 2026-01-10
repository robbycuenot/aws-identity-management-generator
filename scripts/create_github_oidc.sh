#!/bin/bash
# Script: create_github_oidc.sh
# Purpose: Create GitHub Actions OIDC provider and IAM role for the generator workflow.
# Usage: Run in AWS CloudShell while signed in as an administrator to the Identity Center account.
#
# This script is idempotent and safe to run multiple times.
#
# Required: Set these environment variables before running:
#   GITHUB_ORG      - Your GitHub organization or username
#   GITHUB_REPO     - Repository name (default: aws-identity-management)
#   GITHUB_ENV      - GitHub environment name (default: production)

set -e

# Configuration with defaults
GITHUB_ORG="${GITHUB_ORG:?Error: GITHUB_ORG environment variable is required}"
GITHUB_REPO="${GITHUB_REPO:-aws-identity-management}"
GITHUB_ENV="${GITHUB_ENV:-production}"
ROLE_NAME="${ROLE_NAME:-github-actions-identity-management-generator}"

ACCOUNT_ID=$(aws sts get-caller-identity --query 'Account' --output text)
OIDC_PROVIDER_URL="token.actions.githubusercontent.com"
OIDC_PROVIDER_ARN="arn:aws:iam::${ACCOUNT_ID}:oidc-provider/${OIDC_PROVIDER_URL}"

echo "Configuration:"
echo "  GitHub Org:    $GITHUB_ORG"
echo "  GitHub Repo:   $GITHUB_REPO"
echo "  Environment:   $GITHUB_ENV"
echo "  Role Name:     $ROLE_NAME"
echo "  AWS Account:   $ACCOUNT_ID"
echo ""

# Check if OIDC provider exists
echo "Checking for existing GitHub OIDC provider..."
if aws iam get-open-id-connect-provider --open-id-connect-provider-arn "$OIDC_PROVIDER_ARN" &>/dev/null; then
  echo "GitHub OIDC provider already exists"
else
  echo "Creating GitHub OIDC provider..."
  
  # Get the thumbprint (GitHub's certificate thumbprint)
  THUMBPRINT="6938fd4d98bab03faadb97b34396831e3780aea1"
  
  aws iam create-open-id-connect-provider \
    --url "https://${OIDC_PROVIDER_URL}" \
    --client-id-list "sts.amazonaws.com" \
    --thumbprint-list "$THUMBPRINT" \
    --tags Key=Purpose,Value="GitHub Actions OIDC" Key=ManagedBy,Value="create_github_oidc.sh"
  
  echo "GitHub OIDC provider created"
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
          "token.actions.githubusercontent.com:aud": "sts.amazonaws.com"
        },
        "StringLike": {
          "token.actions.githubusercontent.com:sub": "repo:${GITHUB_ORG}/${GITHUB_REPO}:environment:${GITHUB_ENV}"
        }
      }
    }
  ]
}
EOF
)

# Check if role exists
echo "Checking for existing IAM role..."
if aws iam get-role --role-name "$ROLE_NAME" &>/dev/null; then
  echo "Role '$ROLE_NAME' already exists, updating trust policy..."
  aws iam update-assume-role-policy \
    --role-name "$ROLE_NAME" \
    --policy-document "$TRUST_POLICY"
else
  echo "Creating IAM role '$ROLE_NAME'..."
  aws iam create-role \
    --role-name "$ROLE_NAME" \
    --assume-role-policy-document "$TRUST_POLICY" \
    --description "GitHub Actions role for IAM Identity Center Generator" \
    --tags Key=Purpose,Value="GitHub Actions OIDC" Key=ManagedBy,Value="create_github_oidc.sh"
fi

# Attach managed policies (idempotent)
echo "Attaching managed policies..."
POLICIES=(
  "arn:aws:iam::aws:policy/AWSSSOReadOnly"
  "arn:aws:iam::aws:policy/AWSSSODirectoryReadOnly"
  "arn:aws:iam::aws:policy/IAMReadOnlyAccess"
  "arn:aws:iam::aws:policy/AmazonDynamoDBReadOnlyAccess"
)

for policy in "${POLICIES[@]}"; do
  aws iam attach-role-policy \
    --role-name "$ROLE_NAME" \
    --policy-arn "$policy" 2>/dev/null || true
  echo "  Attached: $(basename $policy)"
done

# Get the role ARN
ROLE_ARN=$(aws iam get-role --role-name "$ROLE_NAME" --query 'Role.Arn' --output text)

echo ""
echo "============================================"
echo "Setup complete!"
echo "============================================"
echo ""
echo "Add these variables to your GitHub environment '$GITHUB_ENV':"
echo ""
echo "  AWS_ROLE_ARN: $ROLE_ARN"
echo "  AWS_REGION:   $(aws configure get region || echo 'us-east-1')"
echo ""
echo "GitHub Settings URL:"
echo "  https://github.com/${GITHUB_ORG}/${GITHUB_REPO}/settings/environments"
echo ""
