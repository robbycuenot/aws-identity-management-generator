#!/bin/bash
# Script: create_permission_set.sh
# Purpose: Create the AWSIdentityMgmtGeneratorReadOnly permission set and assign it to the current user.
# Usage: Run in AWS CloudShell while signed in as an administrator to the Identity Center management account.
# 
# This script is idempotent and safe to run multiple times.

set -e

# Get SSO instance info
INSTANCE_ARN=$(aws sso-admin list-instances --query 'Instances[0].InstanceArn' --output text)
IDENTITY_STORE_ID=$(aws sso-admin list-instances --query 'Instances[0].IdentityStoreId' --output text)
ACCOUNT_ID=$(aws sts get-caller-identity --query 'Account' --output text)

# Extract your username from the current session
USER_EMAIL=$(aws sts get-caller-identity --query 'Arn' --output text | sed 's/.*\///')
echo "Setting up permission set for: $USER_EMAIL"

PERMISSION_SET_NAME="AWSIdentityMgmtGeneratorReadOnly"

# Check if permission set already exists by trying to create it
# If it exists, the create call fails and we search for the existing one
echo "Checking for existing permission set..."
PERMISSION_SET_ARN=$(aws sso-admin create-permission-set \
  --instance-arn "$INSTANCE_ARN" \
  --name "$PERMISSION_SET_NAME" \
  --description "Read-only access for IAM Identity Center Generator" \
  --session-duration "PT1H" \
  --query 'PermissionSet.PermissionSetArn' \
  --output text 2>/dev/null) || {
  # Creation failed, permission set likely exists - find it
  echo "Permission set '$PERMISSION_SET_NAME' already exists, looking up ARN..."
  PERMISSION_SET_ARN=$(aws sso-admin list-permission-sets \
    --instance-arn "$INSTANCE_ARN" \
    --query 'PermissionSets' \
    --output json | \
    jq -r '.[]' | \
    while read -r arn; do
      name=$(aws sso-admin describe-permission-set \
        --instance-arn "$INSTANCE_ARN" \
        --permission-set-arn "$arn" \
        --query 'PermissionSet.Name' \
        --output text 2>/dev/null)
      if [ "$name" = "$PERMISSION_SET_NAME" ]; then
        echo "$arn"
        break
      fi
    done)
}

if [ -z "$PERMISSION_SET_ARN" ]; then
  echo "Error: Could not create or find permission set"
  exit 1
fi

echo "Using permission set: $PERMISSION_SET_ARN"

# Attach managed policies (idempotent - AWS returns success if already attached)
echo "Attaching managed policies..."
aws sso-admin attach-managed-policy-to-permission-set \
  --instance-arn "$INSTANCE_ARN" \
  --permission-set-arn "$PERMISSION_SET_ARN" \
  --managed-policy-arn "arn:aws:iam::aws:policy/AWSSSOReadOnly" 2>/dev/null || true

aws sso-admin attach-managed-policy-to-permission-set \
  --instance-arn "$INSTANCE_ARN" \
  --permission-set-arn "$PERMISSION_SET_ARN" \
  --managed-policy-arn "arn:aws:iam::aws:policy/AWSSSODirectoryReadOnly" 2>/dev/null || true

aws sso-admin attach-managed-policy-to-permission-set \
  --instance-arn "$INSTANCE_ARN" \
  --permission-set-arn "$PERMISSION_SET_ARN" \
  --managed-policy-arn "arn:aws:iam::aws:policy/IAMReadOnlyAccess" 2>/dev/null || true

# Optional: DynamoDB access for TEAM support (remove these lines if not using TEAM)
aws sso-admin attach-managed-policy-to-permission-set \
  --instance-arn "$INSTANCE_ARN" \
  --permission-set-arn "$PERMISSION_SET_ARN" \
  --managed-policy-arn "arn:aws:iam::aws:policy/AmazonDynamoDBReadOnlyAccess" 2>/dev/null || true

# Optional: Organizations read access for TEAM support
aws sso-admin attach-managed-policy-to-permission-set \
  --instance-arn "$INSTANCE_ARN" \
  --permission-set-arn "$PERMISSION_SET_ARN" \
  --managed-policy-arn "arn:aws:iam::aws:policy/AWSOrganizationsReadOnlyAccess" 2>/dev/null || true

# Add inline policy for identitystore actions not covered by AWSSSODirectoryReadOnly
echo "Adding inline policy for Identity Store read access..."
INLINE_POLICY='{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "IdentityStoreReadAccess",
      "Effect": "Allow",
      "Action": [
        "identitystore:GetGroupId",
        "identitystore:GetUserId",
        "identitystore:GetGroupMembershipId"
      ],
      "Resource": "*"
    }
  ]
}'

aws sso-admin put-inline-policy-to-permission-set \
  --instance-arn "$INSTANCE_ARN" \
  --permission-set-arn "$PERMISSION_SET_ARN" \
  --inline-policy "$INLINE_POLICY" 2>/dev/null || true

# Look up your user ID
echo "Looking up user in Identity Store..."
USER_ID=$(aws identitystore list-users \
  --identity-store-id "$IDENTITY_STORE_ID" \
  --filters "AttributePath=UserName,AttributeValue=$USER_EMAIL" \
  --query 'Users[0].UserId' \
  --output text 2>/dev/null)

if [ -z "$USER_ID" ] || [ "$USER_ID" = "None" ]; then
  echo "Warning: Could not find user '$USER_EMAIL' in Identity Store. Skipping assignment."
  echo "You may need to manually assign the permission set via the AWS console."
else
  # Create assignment (idempotent - AWS returns error if already exists, which we ignore)
  echo "Creating account assignment..."
  aws sso-admin create-account-assignment \
    --instance-arn "$INSTANCE_ARN" \
    --target-id "$ACCOUNT_ID" \
    --target-type AWS_ACCOUNT \
    --permission-set-arn "$PERMISSION_SET_ARN" \
    --principal-type USER \
    --principal-id "$USER_ID" 2>/dev/null || echo "Assignment already exists or was just created"
fi

# Provision the permission set (always safe to run)
echo "Provisioning permission set..."
aws sso-admin provision-permission-set \
  --instance-arn "$INSTANCE_ARN" \
  --permission-set-arn "$PERMISSION_SET_ARN" \
  --target-type AWS_ACCOUNT \
  --target-id "$ACCOUNT_ID"

echo "Done! Sign out and back in to your AWS access portal to see the permission set."
