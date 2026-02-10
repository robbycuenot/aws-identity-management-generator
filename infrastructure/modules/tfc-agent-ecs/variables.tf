# TFC Agent ECS Fargate Module Variables

# =============================================================================
# AWS Configuration
# =============================================================================

variable "aws_region" {
  description = "AWS region for ECS deployment"
  type        = string
  default     = "us-east-1"
}

# =============================================================================
# Naming
# =============================================================================

variable "name_prefix" {
  description = "Prefix for all resource names"
  type        = string
  default     = "tfc-agent"
}

variable "tags" {
  description = "Tags to apply to all resources"
  type        = map(string)
  default     = {}
}

# =============================================================================
# VPC Configuration
# =============================================================================

variable "vpc_id" {
  description = "VPC ID where ECS tasks will run"
  type        = string
}

variable "subnet_ids" {
  description = "List of private subnet IDs for ECS tasks (must have NAT for outbound internet)"
  type        = list(string)
}

# =============================================================================
# TFC Configuration
# =============================================================================

variable "tfc_organization" {
  description = "Terraform Cloud organization name"
  type        = string
}

variable "tfc_agent_pool_name" {
  description = "Name for the TFC agent pool"
  type        = string
  default     = null
}

variable "tfc_agent_name" {
  description = "Name for the TFC agent (appears in TFC UI)"
  type        = string
  default     = "ecs-agent"
}

variable "tfc_agent_version" {
  description = "Version of the TFC agent container to run. The agent version is independent of Terraform version - the agent downloads whatever Terraform version the workspace requires."
  type        = string
  default     = "latest"
}

# =============================================================================
# ECR Pull-Through Cache
# =============================================================================

variable "ecr_pull_through_cache_prefix" {
  description = "ECR repository prefix for Docker Hub pull-through cache. If set, images are pulled via ECR instead of directly from Docker Hub."
  type        = string
  default     = "docker-hub"
}

variable "docker_hub_username" {
  description = "Docker Hub username for pull-through cache authentication. Required since Docker Hub rate limits unauthenticated pulls."
  type        = string
  default     = null
}

variable "docker_hub_access_token" {
  description = "Docker Hub access token (PAT) for pull-through cache authentication. Create at https://hub.docker.com/settings/security"
  type        = string
  default     = null
  sensitive   = true
}

variable "tfc_agent_log_level" {
  description = "Log level for the TFC agent (trace, debug, info, warn, error)"
  type        = string
  default     = "info"

  validation {
    condition     = contains(["trace", "debug", "info", "warn", "error"], var.tfc_agent_log_level)
    error_message = "tfc_agent_log_level must be one of: trace, debug, info, warn, error"
  }
}

# =============================================================================
# ECS Fargate Configuration
# =============================================================================

variable "tasks_per_run" {
  description = "Number of ECS tasks to start per TFC run (2 recommended: one for plan, one for apply)"
  type        = number
  default     = 2
}

variable "cpu" {
  description = "CPU units for the Fargate task (max: 16384 = 16 vCPU)"
  type        = number
  default     = 16384

  validation {
    condition     = contains([256, 512, 1024, 2048, 4096, 8192, 16384], var.cpu)
    error_message = "cpu must be one of: 256, 512, 1024, 2048, 4096, 8192, 16384"
  }
}

variable "memory" {
  description = "Memory in MiB for the Fargate task (max depends on CPU, up to 122880 for 16 vCPU)"
  type        = number
  default     = 32768

  validation {
    condition     = var.memory >= 512 && var.memory <= 122880
    error_message = "memory must be between 512 and 122880 MiB"
  }
}

variable "ephemeral_storage" {
  description = "Ephemeral storage in GiB for the Fargate task (21-200)"
  type        = number
  default     = 200

  validation {
    condition     = var.ephemeral_storage >= 21 && var.ephemeral_storage <= 200
    error_message = "ephemeral_storage must be between 21 and 200 GiB"
  }
}

variable "enable_execute_command" {
  description = "Enable ECS Exec for debugging"
  type        = bool
  default     = true
}

variable "log_retention_days" {
  description = "CloudWatch log retention in days"
  type        = number
  default     = 30

  validation {
    condition     = contains([1, 3, 5, 7, 14, 30, 60, 90, 120, 150, 180, 365, 400, 545, 731, 1096, 1827, 2192, 2557, 2922, 3288, 3653], var.log_retention_days)
    error_message = "log_retention_days must be a valid CloudWatch Logs retention value"
  }
}