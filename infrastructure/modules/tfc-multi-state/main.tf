# AWS Identity Management Integration Module
# This module creates Terraform Cloud workspaces, OIDC providers, and IAM roles
# for managing AWS IAM Identity Center with Terraform.

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

# Create a dedicated project for all Identity Management workspaces
# This groups related workspaces together in the TFC UI
# Set create_tfc_project = false to use an existing project.
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
# Terraform Cloud Workspaces
# ============================================================================
# All workspaces have:
# - allow_destroy_plan = false (prevent accidental destroys via TFC UI)
# - force_delete = true (allow rapid teardown when needed via Terraform)

# Identity Store Workspace
# Manages IAM Identity Center users, groups, and group memberships
resource "tfe_workspace" "identity_store" {
  organization       = local.organization_name
  project_id         = local.project_id
  name               = "${var.workspace_prefix}-identity-store"
  description        = "Manages IAM Identity Center users, groups, and memberships"
  allow_destroy_plan = false
  force_delete       = true

  # VCS Configuration
  # Links workspace to the aws-identity-management repository
  vcs_repo {
    identifier                 = "${var.github_owner}/${var.github_repo}"
    github_app_installation_id = var.github_installation_id
    branch                     = "main"
  }

  # Working Directory
  # Points to the generated Terraform code for identity store resources
  working_directory = "${var.output}/identity_store"

  # Trigger Patterns
  # Only trigger runs when files in the working directory change
  trigger_patterns = ["${var.output}/identity_store/**/*"]
}

# Identity Store Workspace Settings
# Configures execution mode and remote state sharing
resource "tfe_workspace_settings" "identity_store" {
  workspace_id              = tfe_workspace.identity_store.id
  execution_mode            = "remote"
  remote_state_consumer_ids = [tfe_workspace.account_assignments.id]
}

# Managed Policies Workspace
# Tracks AWS managed IAM policies referenced by permission sets
# This is a heavy workspace due to the large number of AWS managed policies
resource "tfe_workspace" "managed_policies" {
  organization       = local.organization_name
  project_id         = local.project_id
  name               = "${var.workspace_prefix}-managed-policies"
  description        = "Tracks AWS managed IAM policies"
  allow_destroy_plan = false
  force_delete       = true

  # VCS Configuration
  # Links workspace to the aws-identity-management repository
  vcs_repo {
    identifier                 = "${var.github_owner}/${var.github_repo}"
    github_app_installation_id = var.github_installation_id
    branch                     = "main"
  }

  # Working Directory
  # Points to the generated Terraform code for managed policies
  working_directory = "${var.output}/managed_policies"

  # Trigger Patterns
  # Only trigger on Terraform files directly in managed_policies, not subdirectories
  # This excludes the policies/*.json files which are reference data
  trigger_patterns = ["${var.output}/managed_policies/*.tf"]
}

# Managed Policies Workspace Settings
# Configures execution mode and remote state sharing
resource "tfe_workspace_settings" "managed_policies" {
  workspace_id              = tfe_workspace.managed_policies.id
  execution_mode            = "remote"
  remote_state_consumer_ids = [tfe_workspace.permission_sets.id]
}

# Permission Sets Workspace
# Manages IAM Identity Center permission sets
# Depends on identity-store and managed-policies workspaces via remote state
resource "tfe_workspace" "permission_sets" {
  organization       = local.organization_name
  project_id         = local.project_id
  name               = "${var.workspace_prefix}-permission-sets"
  description        = "Manages IAM Identity Center permission sets"
  allow_destroy_plan = false
  force_delete       = true

  # VCS Configuration
  # Links workspace to the aws-identity-management repository
  vcs_repo {
    identifier                 = "${var.github_owner}/${var.github_repo}"
    github_app_installation_id = var.github_installation_id
    branch                     = "main"
  }

  # Working Directory
  # Points to the generated Terraform code for permission sets
  working_directory = "${var.output}/permission_sets"

  # Trigger Patterns
  # Only trigger runs when files in the working directory change
  trigger_patterns = ["${var.output}/permission_sets/**/*"]
}

# Permission Sets Workspace Settings
# Configures execution mode and remote state sharing
resource "tfe_workspace_settings" "permission_sets" {
  workspace_id              = tfe_workspace.permission_sets.id
  execution_mode            = "remote"
  remote_state_consumer_ids = [tfe_workspace.account_assignments.id]
}

# Account Assignments Workspace
# Manages IAM Identity Center account assignments (user/group to permission set mappings)
# Depends on identity-store and permission-sets workspaces via remote state
resource "tfe_workspace" "account_assignments" {
  organization       = local.organization_name
  project_id         = local.project_id
  name               = "${var.workspace_prefix}-account-assignments"
  description        = "Manages IAM Identity Center account assignments"
  allow_destroy_plan = false
  force_delete       = true

  # VCS Configuration
  # Links workspace to the aws-identity-management repository
  vcs_repo {
    identifier                 = "${var.github_owner}/${var.github_repo}"
    github_app_installation_id = var.github_installation_id
    branch                     = "main"
  }

  # Working Directory
  # Points to the generated Terraform code for account assignments
  working_directory = "${var.output}/account_assignments"

  # Trigger Patterns
  # Only trigger runs when files in the working directory change
  trigger_patterns = ["${var.output}/account_assignments/**/*"]
}

# Account Assignments Workspace Settings
# Configures execution mode
resource "tfe_workspace_settings" "account_assignments" {
  workspace_id   = tfe_workspace.account_assignments.id
  execution_mode = "remote"
}

# TEAM Workspace (Conditional)
# Manages AWS TEAM (Temporary Elevated Access Management) DynamoDB policies
# Only created when TEAM is enabled via var.enable_team
resource "tfe_workspace" "team" {
  count              = var.enable_team ? 1 : 0
  organization       = local.organization_name
  project_id         = local.project_id
  name               = "${var.workspace_prefix}-team"
  description        = "Manages AWS TEAM DynamoDB policies"
  allow_destroy_plan = false
  force_delete       = true

  # VCS Configuration
  # Links workspace to the aws-identity-management repository
  vcs_repo {
    identifier                 = "${var.github_owner}/${var.github_repo}"
    github_app_installation_id = var.github_installation_id
    branch                     = "main"
  }

  # Working Directory
  # Points to the generated Terraform code for TEAM resources
  working_directory = "${var.output}/team"

  # Trigger Patterns
  # Only trigger runs when files in the working directory change
  trigger_patterns = ["${var.output}/team/**/*"]
}

# TEAM Workspace Settings (Conditional)
# Configures execution mode
resource "tfe_workspace_settings" "team" {
  count          = var.enable_team ? 1 : 0
  workspace_id   = tfe_workspace.team[0].id
  execution_mode = "remote"
}

# ============================================================================
# OIDC Providers (Create if not exists)
# ============================================================================
# These OIDC providers may already exist (created by AFT) or need to be created
# for standalone usage. We check for existence and create only if missing.
# ============================================================================

# Check if Terraform Cloud OIDC provider already exists
data "aws_iam_openid_connect_provider" "tfc_existing" {
  count    = var.create_aws_tfc_oidc_provider ? 0 : 1
  url      = "https://app.terraform.io"
  provider = aws.identity_center
}

# Check if GitHub OIDC provider already exists
data "aws_iam_openid_connect_provider" "github_existing" {
  count    = var.create_aws_github_oidc_provider ? 0 : 1
  url      = "https://token.actions.githubusercontent.com"
  provider = aws.identity_center
}

# TLS certificate for creating TFC OIDC provider
data "tls_certificate" "tfc_certificate" {
  count = var.create_aws_tfc_oidc_provider ? 1 : 0
  url   = "https://app.terraform.io"
}

# TLS certificate for creating GitHub OIDC provider
data "tls_certificate" "github_certificate" {
  count = var.create_aws_github_oidc_provider ? 1 : 0
  url   = "https://token.actions.githubusercontent.com"
}

# Create Terraform Cloud OIDC provider if it doesn't exist
# Requirements: 5.1, 5.2
resource "aws_iam_openid_connect_provider" "tfc_identity_center" {
  count           = var.create_aws_tfc_oidc_provider ? 1 : 0
  url             = data.tls_certificate.tfc_certificate[0].url
  client_id_list  = ["aws.workload.identity"]
  thumbprint_list = [data.tls_certificate.tfc_certificate[0].certificates[0].sha1_fingerprint]

  tags = {
    Name      = "tfc-${var.prefix}-oidc"
    Purpose   = "OIDC authentication for Identity Management workspaces"
    ManagedBy = "Terraform"
    Module    = "aws-identity-management-integration"
  }

  provider = aws.identity_center
}

# Create GitHub OIDC provider if it doesn't exist
# Requirements: 10.1, 10.2
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

# Local values to reference the correct OIDC provider ARN regardless of creation mode
locals {
  tfc_oidc_provider_arn    = var.create_aws_tfc_oidc_provider ? aws_iam_openid_connect_provider.tfc_identity_center[0].arn : data.aws_iam_openid_connect_provider.tfc_existing[0].arn
  github_oidc_provider_arn = var.create_aws_github_oidc_provider ? aws_iam_openid_connect_provider.github_identity_center[0].arn : data.aws_iam_openid_connect_provider.github_existing[0].arn
}

# ============================================================================
# IAM Roles
# ============================================================================

# Terraform Cloud IAM Role for Identity Center Workspaces
# Creates an IAM role that allows Identity Center workspaces to authenticate via OIDC
# The trust policy grants access to all Identity Management workspaces including TEAM
# Requirements: 5.3, 5.4, 5a.1
resource "aws_iam_role" "tfc_identity_management" {
  name        = "tfc-${var.prefix}-${var.environment}-role"
  description = "Role for Identity Management workspaces to access IAM Identity Center and TEAM"

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
            "app.terraform.io:sub" = concat(
              [
                "organization:${local.organization_name}:project:${local.project_name}:workspace:${var.workspace_prefix}-identity-store:run_phase:*",
                "organization:${local.organization_name}:project:${local.project_name}:workspace:${var.workspace_prefix}-managed-policies:run_phase:*",
                "organization:${local.organization_name}:project:${local.project_name}:workspace:${var.workspace_prefix}-permission-sets:run_phase:*",
                "organization:${local.organization_name}:project:${local.project_name}:workspace:${var.workspace_prefix}-account-assignments:run_phase:*"
              ],
              # Add TEAM workspace if enabled
              var.enable_team ? [
                "organization:${local.organization_name}:project:${local.project_name}:workspace:${var.workspace_prefix}-team:run_phase:*"
              ] : []
            )
          }
        }
      }
    ]
  })

  tags = {
    Name        = "tfc-${var.prefix}-${var.environment}-role"
    Purpose     = "OIDC authentication for Identity Management workspaces"
    Environment = var.environment
    ManagedBy   = "Terraform"
    Module      = "aws-identity-management-integration"
  }

  provider = aws.identity_center
}

# Inline Policy: read-write-dynamo-db-team
# Provides read and write access to TEAM DynamoDB tables
resource "aws_iam_role_policy" "tfc_identity_management_dynamodb" {
  name = "read-write-dynamo-db-team"
  role = aws_iam_role.tfc_identity_management.id

  policy = templatefile("${path.module}/policies/dynamodb-team-policy.json", {
    identity_center_region     = var.aws_region
    identity_center_account_id = data.aws_caller_identity.current.account_id
  })

  provider = aws.identity_center
}

# Inline Policy: sso-management
# Provides comprehensive SSO, IAM, and Identity Store management permissions
resource "aws_iam_role_policy" "tfc_identity_management_sso" {
  name = "sso-management"
  role = aws_iam_role.tfc_identity_management.id

  policy = file("${path.module}/policies/sso-management-policy.json")

  provider = aws.identity_center
}

# GitHub Actions IAM Role for Identity Center Account
# Creates an IAM role that allows GitHub Actions workflows to authenticate via OIDC
# The trust policy restricts access to the specified environment in the configuration repository
# This role is used by the generator workflow to read IAM Identity Center resources
# The workflow runs from the configuration repository (aws-identity-management)
# Requirements: 10.3, 10.4, 10.5
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

# Note: Separate TEAM role not needed - TEAM uses same role as Identity Center workspaces

# ============================================================================
# IAM Policy Attachments
# ============================================================================

# Attach AWS Managed Policies to GitHub Actions Role
# Requirements: 10.6
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

# GitHub Environment in Identity Management Repository
# Creates a GitHub environment for scoping variables and OIDC policies
# This environment isolates different deployments (e.g., prod, dev) within the same repository
# The workflow runs from the identity management repository and checks out the generator repository
# Requirements: 10.3
resource "github_repository_environment" "identity_management" {
  repository  = var.github_repo
  environment = var.environment

  # Restrict environment to main branch only
  # This prevents the workflow from running on feature branches
  deployment_branch_policy {
    protected_branches     = false
    custom_branch_policies = true
  }
}

# Allow only the main branch to use this environment
resource "github_repository_environment_deployment_policy" "main_only" {
  repository     = var.github_repo
  environment    = github_repository_environment.identity_management.environment
  branch_pattern = "main"
}

# ============================================================================
# GitHub Actions Variable Configuration
# ============================================================================
# All variables are scoped to the GitHub environment created above
# The workflow runs from the identity management repository (aws-identity-management)
# and checks out the generator repository (aws-identity-management-generator)
# This keeps the generator repository completely static and forkable
# Requirements: 10.7
# ============================================================================

# GitHub Actions Variable - Verbosity
# Default verbosity level for the generator (can be overridden at workflow dispatch)
resource "github_actions_environment_variable" "verbosity" {
  repository    = var.github_repo
  environment   = github_repository_environment.identity_management.environment
  variable_name = "VERBOSITY"
  value         = var.verbosity
}

# GitHub Actions Variable - AWS Role ARN
# Creates a GitHub Actions variable scoped to the environment
# This variable stores the IAM role ARN that GitHub Actions workflows use for OIDC authentication
# The generator workflow reads this variable to authenticate to AWS
# Requirements: 10.7
resource "github_actions_environment_variable" "aws_role_arn" {
  repository    = var.github_repo
  environment   = github_repository_environment.identity_management.environment
  variable_name = "AWS_ROLE_ARN"
  value         = aws_iam_role.github_actions_identity_management.arn
}

# GitHub Actions Variable - AWS Region
# Creates a GitHub Actions variable scoped to the environment
# This variable stores the AWS region where IAM Identity Center is deployed
# The generator workflow reads this variable to configure the AWS provider
# Requirements: 10.7
resource "github_actions_environment_variable" "aws_region" {
  repository    = var.github_repo
  environment   = github_repository_environment.identity_management.environment
  variable_name = "AWS_REGION"
  value         = var.aws_region
}

# GitHub Actions Variable - TFC Organization
# Creates a GitHub Actions variable scoped to the environment
# This variable stores the Terraform Cloud organization name
# The generator workflow uses this to populate config.yaml via environment variable expansion
# Requirements: 10.7
resource "github_actions_environment_variable" "tfc_org" {
  repository    = var.github_repo
  environment   = github_repository_environment.identity_management.environment
  variable_name = "TFC_ORG"
  value         = local.organization_name
}

# GitHub Actions Variable - Auto Update Providers
# Creates a GitHub Actions variable scoped to the environment
# This variable controls whether the generator auto-updates provider versions
# The generator workflow uses this to populate config.yaml via environment variable expansion
# Requirements: 10.7
resource "github_actions_environment_variable" "auto_update_providers" {
  repository    = var.github_repo
  environment   = github_repository_environment.identity_management.environment
  variable_name = "AUTO_UPDATE_PROVIDERS"
  value         = tostring(var.auto_update_providers)
}

# GitHub Actions Variable - Enable TEAM
# Creates a GitHub Actions variable scoped to the environment
# This variable controls whether TEAM support is enabled
# The generator workflow uses this to populate config.yaml via environment variable expansion
# Requirements: 10.7
resource "github_actions_environment_variable" "enable_team" {
  repository    = var.github_repo
  environment   = github_repository_environment.identity_management.environment
  variable_name = "ENABLE_TEAM"
  value         = tostring(var.enable_team)
}

# GitHub Actions Variable - Generator Repository Name
# Creates a GitHub Actions variable scoped to the environment
# This variable stores the name of the generator repository to check out
# The workflow checks out this repository to access scripts and templates
# Requirements: 5.1
resource "github_actions_environment_variable" "generator_repo_name" {
  repository    = var.github_repo
  environment   = github_repository_environment.identity_management.environment
  variable_name = "GENERATOR_REPO_NAME"
  value         = var.github_generator_repo
}

# GitHub Actions Variable - GitHub Owner
# Creates a GitHub Actions variable scoped to the environment
# This variable stores the GitHub organization or user that owns the repositories
# The generator workflow uses this to construct the full repository path for checkout
# Requirements: 5.3
resource "github_actions_environment_variable" "repo_owner" {
  repository    = var.github_repo
  environment   = github_repository_environment.identity_management.environment
  variable_name = "REPO_OWNER"
  value         = var.github_owner
}

# GitHub Actions Variable - Environment Name
# Creates a GitHub Actions variable scoped to the environment
# This variable stores the environment name for reference in the workflow
# The generator workflow uses this for display purposes in PR descriptions
# Requirements: 5.1
resource "github_actions_environment_variable" "environment" {
  repository    = var.github_repo
  environment   = github_repository_environment.identity_management.environment
  variable_name = "TFC_ENVIRONMENT"
  value         = var.environment
}

# GitHub Actions Variable - Output Path
# Creates a GitHub Actions variable scoped to the environment
# This variable stores the path within the identity management repository where generated files are written
# The generator workflow uses this as the output directory for the generator
# Requirements: 5.3
resource "github_actions_environment_variable" "output" {
  repository    = var.github_repo
  environment   = github_repository_environment.identity_management.environment
  variable_name = "OUTPUT"
  value         = var.output
}

# GitHub Actions Variable - State Mode
# Creates a GitHub Actions variable scoped to the environment
# This variable tells the generator to use multi-state mode (separate workspaces per component)
# The generator workflow passes this to the --state-mode flag
resource "github_actions_environment_variable" "state_mode" {
  repository    = var.github_repo
  environment   = github_repository_environment.identity_management.environment
  variable_name = "STATE_MODE"
  value         = "multi"
}

# GitHub Actions Variable - Platform
# Creates a GitHub Actions variable scoped to the environment
# This variable tells the generator to use TFC platform (Terraform Cloud backends)
# The generator workflow passes this to the --platform flag
resource "github_actions_environment_variable" "platform" {
  repository    = var.github_repo
  environment   = github_repository_environment.identity_management.environment
  variable_name = "PLATFORM"
  value         = "tfc"
}

# GitHub Actions Variable - Prefix
# Creates a GitHub Actions variable scoped to the environment
# This variable stores the prefix used for workspace and role naming
resource "github_actions_environment_variable" "prefix" {
  repository    = var.github_repo
  environment   = github_repository_environment.identity_management.environment
  variable_name = "PREFIX"
  value         = var.prefix
}

# ============================================================================
# Generator Repository Deploy Key
# ============================================================================
# Creates an SSH deploy key for the generator repository and stores it as
# an environment secret. This allows the workflow in the identity management
# repository to check out the private generator repository.
# ============================================================================

# Generate SSH key pair for deploy key
resource "tls_private_key" "generator_deploy_key" {
  algorithm = "ED25519"
}

# Add public key as deploy key to generator repository
resource "github_repository_deploy_key" "generator" {
  title      = "Identity Management Generator - ${var.environment}"
  repository = var.github_generator_repo
  key        = tls_private_key.generator_deploy_key.public_key_openssh
  read_only  = true
}

# Store private key as environment secret
resource "github_actions_environment_secret" "generator_deploy_key" {
  repository      = var.github_repo
  environment     = github_repository_environment.identity_management.environment
  secret_name     = "GENERATOR_DEPLOY_KEY"
  plaintext_value = tls_private_key.generator_deploy_key.private_key_openssh
}

# ============================================================================
# Identity Management Variable Set
# ============================================================================
# Creates a project-level variable set for shared Identity Management configuration
# This variable set contains OIDC credentials and is applied to all workspaces
# in the aws-identity-management project
# Requirements: 12.2, 12.3, 12.4
# ============================================================================

# Create Identity Management Variable Set
resource "tfe_variable_set" "identity_management" {
  name         = "Identity Management"
  description  = "Shared OIDC configuration for AWS Identity Management workspaces"
  organization = local.organization_name
}

# Attach variable set to the project (applies to all workspaces in project)
resource "tfe_project_variable_set" "identity_management" {
  project_id      = local.project_id
  variable_set_id = tfe_variable_set.identity_management.id
}

# ============================================================================
# OIDC Configuration Variables
# ============================================================================
# These environment variables are shared across all Identity Management workspaces
# to enable AWS provider authentication via OIDC instead of static credentials
# Requirements: 6.1, 6.2, 6.3
# ============================================================================

# Enable OIDC authentication for AWS provider
resource "tfe_variable" "provider_auth" {
  key             = "TFC_AWS_PROVIDER_AUTH"
  value           = "true"
  category        = "env"
  variable_set_id = tfe_variable_set.identity_management.id
  description     = "Enable OIDC authentication for AWS provider"
  sensitive       = false
}

# Specify the IAM role ARN for OIDC authentication
resource "tfe_variable" "role_arn" {
  key             = "TFC_AWS_RUN_ROLE_ARN"
  value           = aws_iam_role.tfc_identity_management.arn
  category        = "env"
  variable_set_id = tfe_variable_set.identity_management.id
  description     = "IAM role ARN for OIDC authentication"
  sensitive       = false
}

# Specify the AWS region for IAM Identity Center
resource "tfe_variable" "aws_region" {
  key             = "AWS_REGION"
  value           = var.aws_region
  category        = "env"
  variable_set_id = tfe_variable_set.identity_management.id
  description     = "AWS region for IAM Identity Center"
  sensitive       = false
}
