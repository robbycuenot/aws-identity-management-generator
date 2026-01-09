# Infrastructure module outputs
# Outputs from whichever deployment module is active

output "project_id" {
  description = "TFC Project ID for Identity Management workspaces"
  value       = var.deployment_mode == "tfc-multi-state" ? module.tfc_multi_state[0].project_id : module.tfc_single_state[0].project_id
}

output "workspace_ids" {
  description = "Map of workspace names to IDs (multi-state) or single workspace ID (single-state)"
  value       = var.deployment_mode == "tfc-multi-state" ? module.tfc_multi_state[0].workspace_ids : { main = module.tfc_single_state[0].workspace_id }
}

output "github_actions_role_arn" {
  description = "IAM Role ARN for GitHub Actions"
  value       = var.deployment_mode == "tfc-multi-state" ? module.tfc_multi_state[0].github_actions_role_arn : module.tfc_single_state[0].github_actions_role_arn
}

output "tfc_identity_center_role_arn" {
  description = "IAM Role ARN for TFC workspaces"
  value       = var.deployment_mode == "tfc-multi-state" ? module.tfc_multi_state[0].tfc_identity_center_role_arn : module.tfc_single_state[0].tfc_identity_center_role_arn
}

output "identity_center_region" {
  description = "AWS region where IAM Identity Center is deployed"
  value       = var.deployment_mode == "tfc-multi-state" ? module.tfc_multi_state[0].identity_center_region : module.tfc_single_state[0].identity_center_region
}

output "identity_center_account_id" {
  description = "AWS account ID where IAM Identity Center is deployed"
  value       = var.deployment_mode == "tfc-multi-state" ? module.tfc_multi_state[0].identity_center_account_id : module.tfc_single_state[0].identity_center_account_id
}
