# TFC Agent on ECS Fargate
# Webhook-triggered single-execution mode - tasks start on demand and exit after one job

locals {
  common_tags = merge(var.tags, {
    ManagedBy = "terraform"
    Module    = "tfc-agent-ecs"
  })

  # Agent pool name defaults to name_prefix if not provided
  agent_pool_name = var.tfc_agent_pool_name != null ? var.tfc_agent_pool_name : var.name_prefix

  # ECR pull-through cache image path
  ecr_image = "${data.aws_caller_identity.current.account_id}.dkr.ecr.${var.aws_region}.amazonaws.com/${var.ecr_pull_through_cache_prefix}/hashicorp/tfc-agent:${var.tfc_agent_version}"
}

# =============================================================================
# Data Sources
# =============================================================================

data "aws_caller_identity" "current" {}

# =============================================================================
# ECR Pull-Through Cache
# =============================================================================

resource "aws_ecr_pull_through_cache_rule" "docker_hub" {
  ecr_repository_prefix = var.ecr_pull_through_cache_prefix
  upstream_registry_url = "registry-1.docker.io"
}

# =============================================================================
# TFC Agent Pool and Token
# =============================================================================

resource "tfe_agent_pool" "main" {
  name                = local.agent_pool_name
  organization        = var.tfc_organization
  organization_scoped = true
}

resource "tfe_agent_token" "main" {
  agent_pool_id = tfe_agent_pool.main.id
  description   = "${var.name_prefix} ECS agent token"
}

# =============================================================================
# Security Group
# =============================================================================

resource "aws_security_group" "ecs_tasks" {
  name        = "${var.name_prefix}-ecs-tasks-sg"
  description = "Security group for TFC agent ECS tasks"
  vpc_id      = var.vpc_id

  # Allow all outbound (TFC agent needs to reach app.terraform.io)
  egress {
    description = "Allow all outbound"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(local.common_tags, {
    Name = "${var.name_prefix}-ecs-tasks-sg"
  })
}

# =============================================================================
# Secrets Manager
# =============================================================================

resource "aws_secretsmanager_secret" "tfc_agent_token" {
  name                    = "${var.name_prefix}-token"
  description             = "Terraform Cloud agent token"
  recovery_window_in_days = 0

  tags = local.common_tags
}

resource "aws_secretsmanager_secret_version" "tfc_agent_token" {
  secret_id     = aws_secretsmanager_secret.tfc_agent_token.id
  secret_string = tfe_agent_token.main.token
}

# Webhook secret for HMAC verification
resource "random_password" "webhook_secret" {
  length  = 32
  special = false
}

resource "aws_secretsmanager_secret" "webhook_secret" {
  name                    = "${var.name_prefix}-webhook-secret"
  description             = "HMAC secret for TFC webhook verification"
  recovery_window_in_days = 0

  tags = local.common_tags
}

resource "aws_secretsmanager_secret_version" "webhook_secret" {
  secret_id     = aws_secretsmanager_secret.webhook_secret.id
  secret_string = random_password.webhook_secret.result
}

# =============================================================================
# CloudWatch Log Groups
# =============================================================================

resource "aws_cloudwatch_log_group" "tfc_agent" {
  name              = "/ecs/${var.name_prefix}"
  retention_in_days = var.log_retention_days

  tags = local.common_tags
}

resource "aws_cloudwatch_log_group" "webhook_lambda" {
  name              = "/aws/lambda/${var.name_prefix}-webhook"
  retention_in_days = var.log_retention_days

  tags = local.common_tags
}

# =============================================================================
# ECS Cluster
# =============================================================================

resource "aws_ecs_cluster" "main" {
  name = "${var.name_prefix}-cluster"

  setting {
    name  = "containerInsights"
    value = "enabled"
  }

  tags = local.common_tags
}

resource "aws_ecs_cluster_capacity_providers" "main" {
  cluster_name       = aws_ecs_cluster.main.name
  capacity_providers = ["FARGATE"]

  default_capacity_provider_strategy {
    base              = 1
    weight            = 100
    capacity_provider = "FARGATE"
  }
}


# =============================================================================
# IAM Roles - ECS Task Execution
# =============================================================================

resource "aws_iam_role" "ecs_task_execution" {
  name = "${var.name_prefix}-task-execution-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "ecs-tasks.amazonaws.com"
      }
    }]
  })

  tags = local.common_tags
}

resource "aws_iam_role_policy_attachment" "ecs_task_execution" {
  role       = aws_iam_role.ecs_task_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

resource "aws_iam_role_policy" "ecs_task_execution_ecr" {
  name = "ecr-pull-through-cache"
  role = aws_iam_role.ecs_task_execution.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "ECRAuth"
        Effect = "Allow"
        Action = [
          "ecr:GetAuthorizationToken"
        ]
        Resource = "*"
      },
      {
        Sid    = "ECRPullThroughCache"
        Effect = "Allow"
        Action = [
          "ecr:BatchGetImage",
          "ecr:GetDownloadUrlForLayer",
          "ecr:BatchCheckLayerAvailability",
          "ecr:BatchImportUpstreamImage"
        ]
        Resource = "arn:aws:ecr:${var.aws_region}:${data.aws_caller_identity.current.account_id}:repository/${var.ecr_pull_through_cache_prefix}/*"
      }
    ]
  })
}

resource "aws_iam_role_policy" "ecs_task_execution_secrets" {
  name = "secrets-access"
  role = aws_iam_role.ecs_task_execution.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "secretsmanager:GetSecretValue"
      ]
      Resource = aws_secretsmanager_secret.tfc_agent_token.arn
    }]
  })
}

# =============================================================================
# IAM Roles - ECS Task
# =============================================================================

resource "aws_iam_role" "ecs_task" {
  name = "${var.name_prefix}-task-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "ecs-tasks.amazonaws.com"
      }
      Condition = {
        ArnLike = {
          "aws:SourceArn" = "arn:aws:ecs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:*"
        }
        StringEquals = {
          "aws:SourceAccount" = data.aws_caller_identity.current.account_id
        }
      }
    }]
  })

  tags = local.common_tags
}

resource "aws_iam_role_policy" "ecs_exec" {
  count = var.enable_execute_command ? 1 : 0
  name  = "ecs-exec"
  role  = aws_iam_role.ecs_task.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "ssmmessages:CreateControlChannel",
        "ssmmessages:CreateDataChannel",
        "ssmmessages:OpenControlChannel",
        "ssmmessages:OpenDataChannel"
      ]
      Resource = "*"
    }]
  })
}

# =============================================================================
# ECS Task Definition (Single-Execution Mode)
# =============================================================================

resource "aws_ecs_task_definition" "tfc_agent" {
  family                   = var.name_prefix
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = var.cpu
  memory                   = var.memory
  execution_role_arn       = aws_iam_role.ecs_task_execution.arn
  task_role_arn            = aws_iam_role.ecs_task.arn

  ephemeral_storage {
    size_in_gib = var.ephemeral_storage
  }

  container_definitions = jsonencode([{
    name      = "tfc-agent"
    image     = local.ecr_image
    essential = true

    environment = [
      {
        name  = "TFC_AGENT_NAME"
        value = var.tfc_agent_name
      },
      {
        name  = "TFC_AGENT_LOG_LEVEL"
        value = var.tfc_agent_log_level
      },
      {
        name  = "TFC_AGENT_SINGLE"
        value = "true"  # Single-execution mode - exit after one job
      }
    ]

    secrets = [
      {
        name      = "TFC_AGENT_TOKEN"
        valueFrom = aws_secretsmanager_secret.tfc_agent_token.arn
      }
    ]

    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.tfc_agent.name
        "awslogs-region"        = var.aws_region
        "awslogs-stream-prefix" = "tfc-agent"
      }
    }
  }])

  tags = local.common_tags

  depends_on = [aws_ecr_pull_through_cache_rule.docker_hub]
}


# =============================================================================
# Lambda - Webhook Handler
# =============================================================================

data "archive_file" "webhook_lambda" {
  type        = "zip"
  source_file = "${path.module}/lambda/webhook_handler.py"
  output_path = "${path.module}/lambda/webhook_handler.zip"
}

resource "aws_iam_role" "webhook_lambda" {
  name = "${var.name_prefix}-webhook-lambda-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "lambda.amazonaws.com"
      }
    }]
  })

  tags = local.common_tags
}

resource "aws_iam_role_policy" "webhook_lambda" {
  name = "webhook-lambda-policy"
  role = aws_iam_role.webhook_lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "Logs"
        Effect = "Allow"
        Action = [
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "${aws_cloudwatch_log_group.webhook_lambda.arn}:*"
      },
      {
        Sid    = "ECSRunTask"
        Effect = "Allow"
        Action = [
          "ecs:RunTask"
        ]
        # Use wildcard for task definition revisions
        Resource = "arn:aws:ecs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:task-definition/${var.name_prefix}:*"
      },
      {
        Sid    = "ECSPassRole"
        Effect = "Allow"
        Action = [
          "iam:PassRole"
        ]
        Resource = [
          aws_iam_role.ecs_task_execution.arn,
          aws_iam_role.ecs_task.arn
        ]
      }
    ]
  })
}

resource "aws_lambda_function" "webhook" {
  function_name    = "${var.name_prefix}-webhook"
  role             = aws_iam_role.webhook_lambda.arn
  handler          = "webhook_handler.handler"
  runtime          = "python3.12"
  timeout          = 30
  filename         = data.archive_file.webhook_lambda.output_path
  source_code_hash = data.archive_file.webhook_lambda.output_base64sha256

  environment {
    variables = {
      CLUSTER_ARN     = aws_ecs_cluster.main.arn
      TASK_DEFINITION = aws_ecs_task_definition.tfc_agent.arn
      SUBNETS         = join(",", var.subnet_ids)
      SECURITY_GROUP  = aws_security_group.ecs_tasks.id
      WEBHOOK_SECRET  = random_password.webhook_secret.result
      TASKS_PER_RUN   = tostring(var.tasks_per_run)
    }
  }

  depends_on = [aws_cloudwatch_log_group.webhook_lambda]

  tags = local.common_tags
}

# =============================================================================
# API Gateway - Webhook Endpoint
# =============================================================================

resource "aws_apigatewayv2_api" "webhook" {
  name          = "${var.name_prefix}-webhook"
  protocol_type = "HTTP"

  tags = local.common_tags
}

resource "aws_apigatewayv2_stage" "webhook" {
  api_id      = aws_apigatewayv2_api.webhook.id
  name        = "$default"
  auto_deploy = true

  access_log_settings {
    destination_arn = aws_cloudwatch_log_group.webhook_lambda.arn
    format = jsonencode({
      requestId      = "$context.requestId"
      ip             = "$context.identity.sourceIp"
      requestTime    = "$context.requestTime"
      httpMethod     = "$context.httpMethod"
      routeKey       = "$context.routeKey"
      status         = "$context.status"
      responseLength = "$context.responseLength"
    })
  }

  tags = local.common_tags
}

resource "aws_apigatewayv2_integration" "webhook" {
  api_id                 = aws_apigatewayv2_api.webhook.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.webhook.invoke_arn
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_route" "webhook" {
  api_id    = aws_apigatewayv2_api.webhook.id
  route_key = "POST /webhook"
  target    = "integrations/${aws_apigatewayv2_integration.webhook.id}"
}

resource "aws_lambda_permission" "webhook" {
  statement_id  = "AllowAPIGateway"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.webhook.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.webhook.execution_arn}/*/*"
}
