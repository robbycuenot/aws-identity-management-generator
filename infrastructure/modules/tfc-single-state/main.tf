# AWS Identity Management Integration Module - Single State TFC
# This module creates a single Terraform Cloud workspace for all IAM Identity Center components.
# Use this when you want simpler management with a single state file.

# ============================================================================
# Data Sources
# ============================================================================

data "aws_caller_identity" "current" {
  provider = aws.identity_center
}

# ============================================================================
# Terraform Cloud Organization (data source only - org must already exist)
# ============================================================================

data "tfe_organization" "identity_management" {
  name = var.tfc_organization_name
}

locals {
  organization_name = data.tfe_organization.identity_management.name
}

# ============================================================================
# Terraform Cloud Project
# ============================================================================

resource "tfe_project" "identity_management" {
  count        = var.create_tfc_project ? 1 : 0
  organization = local.organization_name
  name         = var.tfc_project_name
}

data "tfe_project" "existing" {
  count        = var.create_tfc_project ? 0 : 1
  organization = local.organization_name
  name         = var.tfc_project_name
}

locals {
  project_id   = var.create_tfc_project ? tfe_project.identity_management[0].id : data.tfe_project.existing[0].id
  project_name = var.tfc_project_name
}

# ============================================================================
# Single Terraform Cloud Workspace
# ============================================================================
# Unlike multi-state mode, this creates a single workspace that manages all
# IAM Identity Center components together.

resource "tfe_workspace" "identity_management" {
  organization        = local.organization_name
  project_id          = local.project_id
  name                = var.workspace_prefix
  description         = "Manages all IAM Identity Center resources (users, groups, permission sets, account assignments)"
  allow_destroy_plan  = false
  force_delete        = true

  vcs_repo {
    identifier                 = "${var.github_owner}/${var.github_repo}"
    github_app_installation_id = var.github_installation_id
    branch                     = "main"
  }

  # Root working directory - all components are child modules
  working_directory = var.output

  # Trigger on any changes in the repository path
  trigger_patterns = ["${var.output}/**/*"]
}

resource "tfe_workspace_settings" "identity_management" {
  workspace_id   = tfe_workspace.identity_management.id
  execution_mode = "remote"
}

# ============================================================================
# OIDC Providers
# ============================================================================

data "aws_iam_openid_connect_provider" "tfc_existing" {
  count    = var.create_aws_tfc_oidc_provider ? 0 : 1
  url      = "https://app.terraform.io"
  provider = aws.identity_center
}

data "aws_iam_openid_connect_provider" "github_existing" {
  count    = var.create_aws_github_oidc_provider ? 0 : 1
  url      = "https://token.actions.githubusercontent.com"
  provider = aws.identity_center
}

data "tls_certificate" "tfc_certificate" {
  count = var.create_aws_tfc_oidc_provider ? 1 : 0
  url   = "https://app.terraform.io"
}

data "tls_certificate" "github_certificate" {
  count = var.create_aws_github_oidc_provider ? 1 : 0
  url   = "https://token.actions.githubusercontent.com"
}

resource "aws_iam_openid_connect_provider" "tfc_identity_center" {
  count           = var.create_aws_tfc_oidc_provider ? 1 : 0
  url             = data.tls_certificate.tfc_certificate[0].url
  client_id_list  = ["aws.workload.identity"]
  thumbprint_list = [data.tls_certificate.tfc_certificate[0].certificates[0].sha1_fingerprint]

  tags = {
    Name      = "tfc-${var.prefix}-oidc"
    Purpose   = "OIDC authentication for Identity Management workspace"
    ManagedBy = "Terraform"
    Module    = "aws-identity-management-integration"
  }

  provider = aws.identity_center
}

resource "aws_iam_openid_connect_provider" "github_identity_center" {
  count           = var.create_aws_github_oidc_provider ? 1 : 0
  url             = data.tls_certificate.github_certificate[0].url
  client_id_list  = ["sts.amazonaws.com"]
  thumbprint_list = [data.tls_certificate.github_certificate[0].certificates[0].sha1_fingerprint]

  tags = {
    Name      = "github-actions-${var.prefix}-oidc"
    Purpose   = "OIDC authentication for GitHub Actions workflows"
    ManagedBy = "Terraform"
    Module    = "aws-identity-management-integration"
  }

  provider = aws.identity_center
}

locals {
  tfc_oidc_provider_arn    = var.create_aws_tfc_oidc_provider ? aws_iam_openid_connect_provider.tfc_identity_center[0].arn : data.aws_iam_openid_connect_provider.tfc_existing[0].arn
  github_oidc_provider_arn = var.create_aws_github_oidc_provider ? aws_iam_openid_connect_provider.github_identity_center[0].arn : data.aws_iam_openid_connect_provider.github_existing[0].arn
}

# ============================================================================
# IAM Roles
# ============================================================================

resource "aws_iam_role" "tfc_identity_management" {
  name        = "tfc-${var.prefix}-${var.environment}-role"
  description = "Role for Identity Management workspace to access IAM Identity Center and TEAM"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Federated = local.tfc_oidc_provider_arn
        }
        Action = "sts:AssumeRoleWithWebIdentity"
        Condition = {
          StringEquals = {
            "app.terraform.io:aud" = "aws.workload.identity"
          }
          StringLike = {
            # Single workspace - simpler trust policy
            "app.terraform.io:sub" = "organization:${local.organization_name}:project:${local.project_name}:workspace:${var.workspace_prefix}:run_phase:*"
          }
        }
      }
    ]
  })

  tags = {
    Name        = "tfc-${var.prefix}-${var.environment}-role"
    Purpose     = "OIDC authentication for Identity Management workspace"
    Environment = var.environment
    ManagedBy   = "Terraform"
    Module      = "aws-identity-management-integration"
  }

  provider = aws.identity_center
}

resource "aws_iam_role_policy" "tfc_identity_management_dynamodb" {
  name = "read-write-dynamo-db-team"
  role = aws_iam_role.tfc_identity_management.id

  policy = templatefile("${path.module}/policies/dynamodb-team-policy.json", {
    identity_center_region     = var.aws_region
    identity_center_account_id = data.aws_caller_identity.current.account_id
  })

  provider = aws.identity_center
}

resource "aws_iam_role_policy" "tfc_identity_management_sso" {
  name = "sso-management"
  role = aws_iam_role.tfc_identity_management.id

  policy = file("${path.module}/policies/sso-management-policy.json")

  provider = aws.identity_center
}

resource "aws_iam_role" "github_actions_identity_management" {
  name        = "github-actions-${var.prefix}-${var.environment}"
  description = "Role for GitHub Actions to generate Identity Management Terraform code"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Federated = local.github_oidc_provider_arn
        }
        Action = "sts:AssumeRoleWithWebIdentity"
        Condition = {
          StringEquals = {
            "token.actions.githubusercontent.com:aud" = "sts.amazonaws.com"
          }
          StringLike = {
            "token.actions.githubusercontent.com:sub" = "repo:${var.github_owner}/${var.github_repo}:environment:${var.environment}"
          }
        }
      }
    ]
  })

  tags = {
    Name        = "github-actions-${var.prefix}-${var.environment}"
    Purpose     = "OIDC authentication for GitHub Actions generator workflow"
    Environment = var.environment
    ManagedBy   = "Terraform"
    Module      = "aws-identity-management-integration"
  }

  provider = aws.identity_center
}

# ============================================================================
# IAM Policy Attachments
# ============================================================================

resource "aws_iam_role_policy_attachment" "github_sso_read" {
  role       = aws_iam_role.github_actions_identity_management.name
  policy_arn = "arn:aws:iam::aws:policy/AWSSSOReadOnly"
  provider   = aws.identity_center
}

resource "aws_iam_role_policy_attachment" "github_sso_directory_read" {
  role       = aws_iam_role.github_actions_identity_management.name
  policy_arn = "arn:aws:iam::aws:policy/AWSSSODirectoryReadOnly"
  provider   = aws.identity_center
}

resource "aws_iam_role_policy_attachment" "github_iam_read" {
  role       = aws_iam_role.github_actions_identity_management.name
  policy_arn = "arn:aws:iam::aws:policy/IAMReadOnlyAccess"
  provider   = aws.identity_center
}

resource "aws_iam_role_policy_attachment" "github_dynamodb_read" {
  role       = aws_iam_role.github_actions_identity_management.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonDynamoDBReadOnlyAccess"
  provider   = aws.identity_center
}

# ============================================================================
# GitHub Environment Configuration
# ============================================================================

resource "github_repository_environment" "identity_management" {
  repository  = var.github_repo
  environment = var.environment

  deployment_branch_policy {
    protected_branches     = false
    custom_branch_policies = true
  }
}

resource "github_repository_environment_deployment_policy" "main_only" {
  repository     = var.github_repo
  environment    = github_repository_environment.identity_management.environment
  branch_pattern = "main"
}

# ============================================================================
# GitHub Actions Variables
# ============================================================================

resource "github_actions_environment_variable" "verbosity" {
  repository    = var.github_repo
  environment   = github_repository_environment.identity_management.environment
  variable_name = "VERBOSITY"
  value         = var.verbosity
}

resource "github_actions_environment_variable" "aws_role_arn" {
  repository    = var.github_repo
  environment   = github_repository_environment.identity_management.environment
  variable_name = "AWS_ROLE_ARN"
  value         = aws_iam_role.github_actions_identity_management.arn
}

resource "github_actions_environment_variable" "aws_region" {
  repository    = var.github_repo
  environment   = github_repository_environment.identity_management.environment
  variable_name = "AWS_REGION"
  value         = var.aws_region
}

resource "github_actions_environment_variable" "tfc_org" {
  repository    = var.github_repo
  environment   = github_repository_environment.identity_management.environment
  variable_name = "TFC_ORG"
  value         = local.organization_name
}

resource "github_actions_environment_variable" "auto_update_providers" {
  repository    = var.github_repo
  environment   = github_repository_environment.identity_management.environment
  variable_name = "AUTO_UPDATE_PROVIDERS"
  value         = tostring(var.auto_update_providers)
}

resource "github_actions_environment_variable" "enable_team" {
  repository    = var.github_repo
  environment   = github_repository_environment.identity_management.environment
  variable_name = "ENABLE_TEAM"
  value         = tostring(var.enable_team)
}

resource "github_actions_environment_variable" "generator_repo_name" {
  repository    = var.github_repo
  environment   = github_repository_environment.identity_management.environment
  variable_name = "GENERATOR_REPO_NAME"
  value         = var.github_generator_repo
}

resource "github_actions_environment_variable" "generator_repo_owner" {
  repository    = var.github_repo
  environment   = github_repository_environment.identity_management.environment
  variable_name = "GENERATOR_REPO_OWNER"
  value         = var.github_owner
}

resource "github_actions_environment_variable" "environment" {
  repository    = var.github_repo
  environment   = github_repository_environment.identity_management.environment
  variable_name = "TFC_ENVIRONMENT"
  value         = var.environment
}

resource "github_actions_environment_variable" "output" {
  repository    = var.github_repo
  environment   = github_repository_environment.identity_management.environment
  variable_name = "OUTPUT"
  value         = var.output
}

resource "github_actions_environment_variable" "state_mode" {
  repository    = var.github_repo
  environment   = github_repository_environment.identity_management.environment
  variable_name = "STATE_MODE"
  value         = "single"
}

resource "github_actions_environment_variable" "platform" {
  repository    = var.github_repo
  environment   = github_repository_environment.identity_management.environment
  variable_name = "PLATFORM"
  value         = "tfc"
}

resource "github_actions_environment_variable" "prefix" {
  repository    = var.github_repo
  environment   = github_repository_environment.identity_management.environment
  variable_name = "PREFIX"
  value         = var.prefix
}

resource "github_actions_environment_variable" "retain_managed_policies" {
  repository    = var.github_repo
  environment   = github_repository_environment.identity_management.environment
  variable_name = "RETAIN_MANAGED_POLICIES"
  value         = tostring(var.retain_managed_policies)
}

# ============================================================================
# Generator Repository Deploy Key
# ============================================================================

resource "tls_private_key" "generator_deploy_key" {
  algorithm = "ED25519"
}

resource "github_repository_deploy_key" "generator" {
  title      = "Identity Management Generator - ${var.environment}"
  repository = var.github_generator_repo
  key        = tls_private_key.generator_deploy_key.public_key_openssh
  read_only  = true
}

resource "github_actions_environment_secret" "generator_deploy_key" {
  repository      = var.github_repo
  environment     = github_repository_environment.identity_management.environment
  secret_name     = "GENERATOR_DEPLOY_KEY"
  plaintext_value = tls_private_key.generator_deploy_key.private_key_openssh
}

# ============================================================================
# TFC Variable Set
# ============================================================================

resource "tfe_variable_set" "identity_management" {
  name         = "Identity Management"
  description  = "Shared OIDC configuration for AWS Identity Management workspace"
  organization = local.organization_name
}

resource "tfe_project_variable_set" "identity_management" {
  project_id      = local.project_id
  variable_set_id = tfe_variable_set.identity_management.id
}

resource "tfe_variable" "provider_auth" {
  key             = "TFC_AWS_PROVIDER_AUTH"
  value           = "true"
  category        = "env"
  variable_set_id = tfe_variable_set.identity_management.id
  description     = "Enable OIDC authentication for AWS provider"
  sensitive       = false
}

resource "tfe_variable" "role_arn" {
  key             = "TFC_AWS_RUN_ROLE_ARN"
  value           = aws_iam_role.tfc_identity_management.arn
  category        = "env"
  variable_set_id = tfe_variable_set.identity_management.id
  description     = "IAM role ARN for OIDC authentication"
  sensitive       = false
}

resource "tfe_variable" "aws_region" {
  key             = "AWS_REGION"
  value           = var.aws_region
  category        = "env"
  variable_set_id = tfe_variable_set.identity_management.id
  description     = "AWS region for IAM Identity Center"
  sensitive       = false
}
