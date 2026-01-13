# TFC Single-State Module Variables
# Naming matches CLI flags and config.yaml for consistency

# =============================================================================
# Generator Parameters (maps to CLI flags / config.yaml / GH env vars)
# =============================================================================

variable "verbosity" {
  description = "Default verbosity level for generator"
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

variable "workspace_prefix" {
  description = "Prefix for workspace names (always prefix-environment)"
  type        = string
}

variable "tfc_project_name" {
  description = "TFC project name (computed from prefix-environment by parent module)"
  type        = string
}

variable "create_tfc_project" {
  description = "Create TFC project (set to false to use existing)"
  type        = bool
  default     = true
}

variable "create_aws_tfc_oidc_provider" {
  description = "Create OIDC provider for Terraform Cloud"
  type        = bool
  default     = true
}

variable "create_aws_github_oidc_provider" {
  description = "Create OIDC provider for GitHub Actions"
  type        = bool
  default     = true
}
