# Output values from the AWS Identity Management Integration module
# These outputs expose resource identifiers and ARNs for use by calling modules

output "project_id" {
  description = "TFC Project ID for Identity Management workspaces"
  value       = local.project_id
}

output "workspace_ids" {
  description = "Map of workspace names to IDs for all Identity Management workspaces"
  value = {
    identity_store      = tfe_workspace.identity_store.id
    managed_policies    = tfe_workspace.managed_policies.id
    permission_sets     = tfe_workspace.permission_sets.id
    account_assignments = tfe_workspace.account_assignments.id
    team                = var.enable_team ? tfe_workspace.team[0].id : null
  }
}

output "github_actions_role_arn" {
  description = "IAM Role ARN for GitHub Actions to authenticate and generate Terraform code"
  value       = aws_iam_role.github_actions_identity_management.arn
}

output "tfc_identity_center_role_arn" {
  description = "IAM Role ARN for TFC workspaces to manage Identity Center resources"
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
