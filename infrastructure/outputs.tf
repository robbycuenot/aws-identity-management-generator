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

# =============================================================================
# TFC Agent ECS Outputs (when enabled)
# =============================================================================

output "tfc_agent_pool_id" {
  description = "ID of the TFC agent pool"
  value       = var.enable_tfc_agent_ecs ? module.tfc_agent_ecs[0].agent_pool_id : null
}

output "tfc_agent_pool_name" {
  description = "Name of the TFC agent pool"
  value       = var.enable_tfc_agent_ecs ? module.tfc_agent_ecs[0].agent_pool_name : null
}

output "tfc_agent_webhook_url" {
  description = "Webhook URL for TFC notifications"
  value       = var.enable_tfc_agent_ecs ? module.tfc_agent_ecs[0].webhook_url : null
}

output "tfc_agent_ecs_cluster_name" {
  description = "Name of the TFC agent ECS cluster"
  value       = var.enable_tfc_agent_ecs ? module.tfc_agent_ecs[0].ecs_cluster_name : null
}

output "tfc_agent_vpc_id" {
  description = "ID of the TFC agent VPC"
  value       = var.enable_tfc_agent_ecs ? module.tfc_agent_ecs[0].vpc_id : null
}

output "tfc_agent_subnet_ids" {
  description = "Subnet IDs used by TFC agent ECS tasks"
  value       = var.enable_tfc_agent_ecs ? module.tfc_agent_ecs[0].subnet_ids : null
}

output "tfc_agent_cloudwatch_log_group" {
  description = "CloudWatch log group for TFC agent logs"
  value       = var.enable_tfc_agent_ecs ? module.tfc_agent_ecs[0].cloudwatch_log_group_name : null
}
