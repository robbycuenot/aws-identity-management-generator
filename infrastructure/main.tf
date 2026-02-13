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
  github_oauth_token_id  = var.github_oauth_token_id
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
  github_oauth_token_id  = var.github_oauth_token_id
  github_token           = var.github_token

  # TFC configuration
  tfc_organization_name           = var.tfc_organization_name
  prefix                          = var.prefix
  workspace_prefix                = local.workspace_prefix
  tfc_project_name                = local.tfc_project_name
  create_tfc_project              = var.create_tfc_project
  create_aws_tfc_oidc_provider    = var.create_aws_tfc_oidc_provider
  create_aws_github_oidc_provider = var.create_aws_github_oidc_provider

  # TFC Agent configuration (optional)
  use_agent_execution      = var.enable_tfc_agent_ecs
  agent_pool_id            = var.enable_tfc_agent_ecs ? module.tfc_agent_ecs[0].agent_pool_id : null
  enable_speculative_plans = var.enable_tfc_agent_ecs ? var.enable_tfc_agent_github_webhook : null
}

# =============================================================================
# TFC Agent on ECS Fargate (Optional - Single-State Mode Only)
# =============================================================================

# Validation checks for TFC Agent configuration
check "tfc_agent_deployment_mode" {
  assert {
    condition     = !var.enable_tfc_agent_ecs || var.deployment_mode == "tfc-single-state"
    error_message = "enable_tfc_agent_ecs is only supported with deployment_mode = \"tfc-single-state\""
  }
}

check "tfc_agent_vpc_required" {
  assert {
    condition     = !var.enable_tfc_agent_ecs || var.tfc_agent_vpc_id != null
    error_message = "tfc_agent_vpc_id is required when enable_tfc_agent_ecs = true"
  }
}

check "tfc_agent_subnets_required" {
  assert {
    condition     = !var.enable_tfc_agent_ecs || (var.tfc_agent_subnet_ids != null && length(var.tfc_agent_subnet_ids) > 0)
    error_message = "tfc_agent_subnet_ids is required when enable_tfc_agent_ecs = true"
  }
}

check "tfc_agent_docker_hub_credentials" {
  assert {
    condition     = !var.enable_tfc_agent_ecs || (var.docker_hub_username != null && var.docker_hub_access_token != null)
    error_message = "docker_hub_username and docker_hub_access_token are required when enable_tfc_agent_ecs = true (Docker Hub requires authentication for ECR pull-through cache)"
  }
}

module "tfc_agent_ecs" {
  count  = var.enable_tfc_agent_ecs && var.deployment_mode == "tfc-single-state" ? 1 : 0
  source = "./modules/tfc-agent-ecs"

  providers = {
    aws    = aws.identity_center
    tfe    = tfe
    github = github
  }

  aws_region       = var.aws_region
  name_prefix      = "${var.prefix}-${var.environment}-tfc-agent"
  tfc_organization = var.tfc_organization_name
  tfc_agent_name   = var.tfc_agent_name

  # Lifecycle manager configuration
  max_agents           = var.tfc_agent_max_agents
  idle_timeout_minutes = var.tfc_agent_idle_timeout_minutes

  # VPC configuration
  vpc_id     = var.tfc_agent_vpc_id
  subnet_ids = var.tfc_agent_subnet_ids

  # Docker Hub credentials for ECR pull-through cache
  docker_hub_username     = var.docker_hub_username
  docker_hub_access_token = var.docker_hub_access_token

  # GitHub webhook for speculative plan support
  enable_github_webhook = var.enable_tfc_agent_github_webhook
  github_repository     = var.enable_tfc_agent_github_webhook ? var.github_repo : null

  tags = {
    Environment = var.environment
    Project     = var.prefix
  }
}

# =============================================================================
# TFC Webhook Notification Configuration
# =============================================================================
# Configured separately to avoid circular dependency:
# tfc_agent_ecs creates agent pool → tfc_single_state uses agent pool → 
# notification uses workspace_id from tfc_single_state

# Wait for API Gateway to be fully deployed before TFC tries to verify the webhook
resource "time_sleep" "wait_for_webhook" {
  count = var.enable_tfc_agent_ecs && var.deployment_mode == "tfc-single-state" ? 1 : 0

  depends_on      = [module.tfc_agent_ecs]
  create_duration = "30s"
}

resource "tfe_notification_configuration" "tfc_agent_webhook" {
  count = var.enable_tfc_agent_ecs && var.deployment_mode == "tfc-single-state" ? 1 : 0

  workspace_id     = module.tfc_single_state[0].workspace_id
  name             = "${var.prefix}-${var.environment}-agent-launcher"
  enabled          = true
  destination_type = "generic"
  triggers         = ["run:created", "run:planning", "run:needs_attention", "run:applying"]
  url              = module.tfc_agent_ecs[0].webhook_url
  token            = module.tfc_agent_ecs[0].webhook_secret

  # Ensure webhook endpoint is fully deployed before TFC tries to verify it
  depends_on = [time_sleep.wait_for_webhook]
}
