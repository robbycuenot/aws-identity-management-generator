# Output values from the AWS Identity Management Integration module (Single State)

output "project_id" {
  description = "TFC Project ID for Identity Management workspace"
  value       = local.project_id
}

output "workspace_id" {
  description = "TFC Workspace ID for Identity Management"
  value       = tfe_workspace.identity_management.id
}

output "github_actions_role_arn" {
  description = "IAM Role ARN for GitHub Actions to authenticate and generate Terraform code"
  value       = aws_iam_role.github_actions_identity_management.arn
}

output "tfc_identity_center_role_arn" {
  description = "IAM Role ARN for TFC workspace to manage Identity Center resources"
  value       = aws_iam_role.tfc_identity_management.arn
}

output "identity_center_region" {
  description = "AWS region where IAM Identity Center is deployed"
  value       = var.aws_region
}

output "identity_center_account_id" {
  description = "AWS account ID where IAM Identity Center is deployed"
  value       = data.aws_caller_identity.current.account_id
}
