# Infrastructure Module Selector
# Selects the appropriate deployment module based on deployment_mode variable

locals {
  # Compute tfc_project_name if not explicitly set
  tfc_project_name = var.tfc_project_name != null ? var.tfc_project_name : "${var.prefix}-${var.environment}"
  # Workspace prefix always uses prefix-environment (not affected by custom tfc_project_name)
  workspace_prefix = "${var.prefix}-${var.environment}"
}

module "tfc_multi_state" {
  count  = var.deployment_mode == "tfc-multi-state" ? 1 : 0
  source = "./modules/tfc-multi-state"

  providers = {
    aws.identity_center = aws.identity_center
  }

  # Generator parameters (match CLI flags)
  verbosity               = var.verbosity
  output                  = var.output
  enable_team             = var.enable_team
  auto_update_providers   = var.auto_update_providers
  retain_managed_policies = var.retain_managed_policies

  # Environment
  environment = var.environment

  # AWS configuration
  aws_region = var.aws_region

  # GitHub configuration
  github_owner           = var.github_owner
  github_repo            = var.github_repo
  github_generator_repo  = var.github_generator_repo
  github_installation_id = var.github_installation_id
  github_token           = var.github_token

  # TFC configuration
  tfc_organization_name           = var.tfc_organization_name
  prefix                          = var.prefix
  workspace_prefix                = local.workspace_prefix
  tfc_project_name                = local.tfc_project_name
  create_tfc_project              = var.create_tfc_project
  create_aws_tfc_oidc_provider    = var.create_aws_tfc_oidc_provider
  create_aws_github_oidc_provider = var.create_aws_github_oidc_provider
}

module "tfc_single_state" {
  count  = var.deployment_mode == "tfc-single-state" ? 1 : 0
  source = "./modules/tfc-single-state"

  providers = {
    aws.identity_center = aws.identity_center
  }

  # Generator parameters (match CLI flags)
  verbosity               = var.verbosity
  output                  = var.output
  enable_team             = var.enable_team
  auto_update_providers   = var.auto_update_providers
  retain_managed_policies = var.retain_managed_policies

  # Environment
  environment = var.environment

  # AWS configuration
  aws_region = var.aws_region

  # GitHub configuration
  github_owner           = var.github_owner
  github_repo            = var.github_repo
  github_generator_repo  = var.github_generator_repo
  github_installation_id = var.github_installation_id
  github_token           = var.github_token

  # TFC configuration
  tfc_organization_name           = var.tfc_organization_name
  prefix                          = var.prefix
  workspace_prefix                = local.workspace_prefix
  tfc_project_name                = local.tfc_project_name
  create_tfc_project              = var.create_tfc_project
  create_aws_tfc_oidc_provider    = var.create_aws_tfc_oidc_provider
  create_aws_github_oidc_provider = var.create_aws_github_oidc_provider
}
