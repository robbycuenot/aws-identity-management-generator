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
# Webhook
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

output "webhook_lambda_function_name" {
  description = "Name of the webhook Lambda function"
  value       = aws_lambda_function.webhook.function_name
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

output "webhook_log_group_name" {
  description = "Name of the CloudWatch log group for webhook Lambda"
  value       = aws_cloudwatch_log_group.webhook_lambda.name
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
