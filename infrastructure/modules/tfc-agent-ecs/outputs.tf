# TFC Agent ECS Module Outputs

# =============================================================================
# TFC Resources
# =============================================================================

output "agent_pool_id" {
  description = "ID of the TFC agent pool"
  value       = tfe_agent_pool.main.id
}

output "agent_pool_name" {
  description = "Name of the TFC agent pool"
  value       = tfe_agent_pool.main.name
}

# =============================================================================
# Webhook / Lifecycle Manager
# =============================================================================

output "webhook_url" {
  description = "Webhook URL for TFC notifications"
  value       = "${aws_apigatewayv2_api.webhook.api_endpoint}/webhook"
  depends_on  = [aws_lambda_permission.webhook]
}

output "webhook_ready" {
  description = "Indicates the webhook endpoint is fully configured and ready to receive requests"
  value       = true
  depends_on  = [aws_lambda_permission.webhook, aws_apigatewayv2_stage.webhook]
}

output "webhook_secret" {
  description = "HMAC secret for webhook verification (use as 'token' in tfe_notification_configuration)"
  value       = random_password.webhook_secret.result
  sensitive   = true
}

output "lifecycle_lambda_function_name" {
  description = "Name of the lifecycle manager Lambda function"
  value       = aws_lambda_function.lifecycle.function_name
}

output "idle_checker_lambda_function_name" {
  description = "Name of the idle checker Lambda function"
  value       = aws_lambda_function.idle_checker.function_name
}

# =============================================================================
# DynamoDB
# =============================================================================

output "agent_state_table_name" {
  description = "Name of the DynamoDB table for agent state tracking"
  value       = aws_dynamodb_table.agent_state.name
}

output "agent_state_table_arn" {
  description = "ARN of the DynamoDB table for agent state tracking"
  value       = aws_dynamodb_table.agent_state.arn
}

# =============================================================================
# VPC/Network
# =============================================================================

output "vpc_id" {
  description = "ID of the VPC"
  value       = var.vpc_id
}

output "subnet_ids" {
  description = "IDs of the subnets used by ECS tasks"
  value       = var.subnet_ids
}

output "security_group_id" {
  description = "ID of the ECS tasks security group"
  value       = aws_security_group.ecs_tasks.id
}

# =============================================================================
# ECS Resources
# =============================================================================

output "ecs_cluster_name" {
  description = "Name of the ECS cluster"
  value       = aws_ecs_cluster.main.name
}

output "ecs_cluster_arn" {
  description = "ARN of the ECS cluster"
  value       = aws_ecs_cluster.main.arn
}

output "ecs_task_definition_arn" {
  description = "ARN of the ECS task definition"
  value       = aws_ecs_task_definition.tfc_agent.arn
}

output "cloudwatch_log_group_name" {
  description = "Name of the CloudWatch log group for ECS tasks"
  value       = aws_cloudwatch_log_group.tfc_agent.name
}

output "lifecycle_log_group_name" {
  description = "Name of the CloudWatch log group for lifecycle manager Lambda"
  value       = aws_cloudwatch_log_group.lifecycle_lambda.name
}

output "idle_checker_log_group_name" {
  description = "Name of the CloudWatch log group for idle checker Lambda"
  value       = aws_cloudwatch_log_group.idle_checker_lambda.name
}

# =============================================================================
# IAM Resources
# =============================================================================

output "task_execution_role_arn" {
  description = "ARN of the ECS task execution role"
  value       = aws_iam_role.ecs_task_execution.arn
}

output "task_role_arn" {
  description = "ARN of the ECS task role"
  value       = aws_iam_role.ecs_task.arn
}

output "agent_token_secret_arn" {
  description = "ARN of the Secrets Manager secret containing the agent token"
  value       = aws_secretsmanager_secret.tfc_agent_token.arn
}

# =============================================================================
# ECR Pull-Through Cache
# =============================================================================

output "ecr_pull_through_cache_prefix" {
  description = "ECR repository prefix for Docker Hub pull-through cache"
  value       = var.ecr_pull_through_cache_prefix
}

output "ecr_image" {
  description = "Full ECR image URI used by the ECS task"
  value       = local.ecr_image
}

# =============================================================================
# GitHub Webhook
# =============================================================================

output "github_webhook_id" {
  description = "ID of the GitHub webhook (if enabled)"
  value       = var.enable_github_webhook ? github_repository_webhook.agent_trigger[0].id : null
}

output "github_webhook_url" {
  description = "URL of the GitHub webhook (if enabled)"
  value       = var.enable_github_webhook ? github_repository_webhook.agent_trigger[0].url : null
}
