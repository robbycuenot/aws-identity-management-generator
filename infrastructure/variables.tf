# Infrastructure module variables
# Naming matches CLI flags and config.yaml for consistency

# =============================================================================
# Deployment Mode
# =============================================================================

variable "deployment_mode" {
  description = "Deployment mode: tfc-multi-state or tfc-single-state"
  type        = string
  default     = "tfc-single-state"

  validation {
    condition     = contains(["tfc-multi-state", "tfc-single-state"], var.deployment_mode)
    error_message = "deployment_mode must be either 'tfc-multi-state' or 'tfc-single-state'"
  }
}

variable "enable_tfc_agent_ecs" {
  description = "Enable TFC agent on ECS Fargate with webhook-triggered single-execution mode (single-state mode only)"
  type        = bool
  default     = false
}

# =============================================================================
# Generator Parameters (maps to CLI flags / config.yaml / GH env vars)
# =============================================================================

variable "verbosity" {
  description = "Default verbosity level for generator (quiet/normal/verbose)"
  type        = string
  default     = "normal"

  validation {
    condition     = contains(["quiet", "normal", "verbose"], var.verbosity)
    error_message = "verbosity must be 'quiet', 'normal', or 'verbose'"
  }
}

variable "output" {
  description = "Output directory for generated files"
  type        = string
  default     = "./output"
}

variable "enable_team" {
  description = "Enable TEAM support"
  type        = bool
  default     = false
}

variable "auto_update_providers" {
  description = "Auto-update Terraform provider versions"
  type        = bool
  default     = true
}

variable "retain_managed_policies" {
  description = "Retain existing managed policies (skip refresh for faster runs)"
  type        = bool
  default     = false
}

# =============================================================================
# Environment
# =============================================================================

variable "environment" {
  description = "Environment name (used in TFC project/workspace naming and GitHub environment)"
  type        = string
}

# =============================================================================
# AWS Configuration
# =============================================================================

variable "aws_region" {
  description = "AWS Region where IAM Identity Center is configured"
  type        = string
  default     = "us-east-1"
}

# =============================================================================
# GitHub Configuration
# =============================================================================

variable "github_owner" {
  description = "GitHub organization or user that owns the repositories"
  type        = string
}

variable "github_repo" {
  description = "Name of the identity management repository"
  type        = string
  default     = "aws-identity-management"
}

variable "github_generator_repo" {
  description = "Name of the generator repository"
  type        = string
  default     = "aws-identity-management-generator"
}

variable "github_installation_id" {
  description = "GitHub App installation ID for VCS connection (use this OR github_oauth_token_id)"
  type        = string
  default     = null
}

variable "github_oauth_token_id" {
  description = "GitHub OAuth token ID for VCS connection (use this OR github_installation_id)"
  type        = string
  default     = null
}

variable "github_token" {
  description = "GitHub personal access token with repo scope"
  type        = string
  sensitive   = true
}

# =============================================================================
# TFC Configuration
# =============================================================================

variable "tfc_organization_name" {
  description = "Terraform Cloud organization name (must already exist)"
  type        = string
}

variable "prefix" {
  description = "Prefix for TFC project, workspace, and IAM role names"
  type        = string
  default     = "aws-identity-management"
}

variable "tfc_project_name" {
  description = "TFC project name. If null, computed as prefix-environment"
  type        = string
  default     = null
}

variable "create_tfc_project" {
  description = "Create TFC project. Set to false to use existing project."
  type        = bool
  default     = true
}

variable "create_aws_tfc_oidc_provider" {
  description = "Create OIDC provider for Terraform Cloud"
  type        = bool
  default     = false
}

variable "create_aws_github_oidc_provider" {
  description = "Create OIDC provider for GitHub Actions"
  type        = bool
  default     = false
}

# =============================================================================
# TFC Agent on ECS Fargate (Single-State Mode Only)
# =============================================================================

variable "tfc_agent_name" {
  description = "Name for the TFC agent (appears in TFC UI)"
  type        = string
  default     = "ecs-agent"
}

variable "tfc_agent_tasks_per_run" {
  description = "Number of ECS tasks to start per TFC run (2 recommended: one for plan, one for apply)"
  type        = number
  default     = 2
}

variable "tfc_agent_vpc_id" {
  description = "VPC ID for TFC agent (required if enable_tfc_agent_ecs = true)"
  type        = string
  default     = null
}

variable "tfc_agent_subnet_ids" {
  description = "Subnet IDs for ECS tasks (must have NAT for outbound internet, required if enable_tfc_agent_ecs = true)"
  type        = list(string)
  default     = null
}

variable "docker_hub_username" {
  description = "Docker Hub username for ECR pull-through cache authentication (required for TFC agent)"
  type        = string
  default     = null
}

variable "docker_hub_access_token" {
  description = "Docker Hub access token (PAT) for ECR pull-through cache authentication. Create at https://hub.docker.com/settings/security"
  type        = string
  default     = null
  sensitive   = true
}
