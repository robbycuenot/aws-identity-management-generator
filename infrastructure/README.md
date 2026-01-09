# Infrastructure Module

Terraform module that deploys the infrastructure required to run the AWS IAM Identity Center Generator with Terraform Cloud.

## What Gets Created

**In AWS:**
- IAM OIDC providers for Terraform Cloud and GitHub Actions (optional)
- IAM roles with least-privilege permissions

**In Terraform Cloud:**
- Project and workspace(s) with VCS integration
- OIDC authentication (no static credentials)

**In GitHub:**
- Environment with variables and secrets
- Deploy key for accessing the generator repository

## Deployment Modes

| Mode | Workspaces | Use Case |
|------|------------|----------|
| `tfc-single-state` | 1 | Most environments |
| `tfc-multi-state` | 5 | Large environments (1000+ assignments) |

## Prerequisites

1. Fork both repositories to your organization:
   - `aws-identity-management-generator`
   - `aws-identity-management`

2. Create a GitHub Personal Access Token (fine-grained) with permissions:
   - Metadata: Read
   - Actions: Read and write
   - Actions variables: Read and write
   - Administration: Read and write
   - Environments: Read and write
   - Secrets: Read and write

3. Get your GitHub App Installation ID for TFC VCS integration

## Usage

```hcl
module "identity_management" {
  source = "github.com/robbycuenot/aws-identity-management-generator//infrastructure"

  # Required
  environment            = "production"
  github_owner           = "your-github-org"
  github_installation_id = "12345678"
  github_token           = var.github_token
  tfc_organization_name  = "your-tfc-org"

  # Optional
  deployment_mode                 = "tfc-single-state"
  prefix                          = "aws-identity-management"
  aws_region                      = "us-east-1"
  enable_team                     = false
  create_tfc_project              = true
  create_aws_tfc_oidc_provider    = true
  create_aws_github_oidc_provider = true
}
```

## Variables

### Required

| Variable | Description |
|----------|-------------|
| `environment` | Environment name (used in naming and GitHub environment) |
| `github_owner` | GitHub organization or user |
| `github_installation_id` | GitHub App installation ID for VCS |
| `github_token` | GitHub PAT (sensitive) |
| `tfc_organization_name` | TFC organization name (must exist) |

### Optional

| Variable | Description | Default |
|----------|-------------|---------|
| `deployment_mode` | `tfc-single-state` or `tfc-multi-state` | `tfc-single-state` |
| `prefix` | Prefix for project/workspace/role names | `aws-identity-management` |
| `tfc_project_name` | TFC project name (if null, computed as `prefix-environment`) | `null` |
| `aws_region` | AWS Region for Identity Center | `us-east-1` |
| `github_repo` | Identity management repository name | `aws-identity-management` |
| `github_generator_repo` | Generator repository name | `aws-identity-management-generator` |
| `verbosity` | Generator verbosity level | `normal` |
| `output` | Output directory for generated files | `./output` |
| `enable_team` | Enable TEAM support | `false` |
| `auto_update_providers` | Auto-update provider versions | `true` |
| `create_tfc_project` | Create TFC project | `true` |
| `create_aws_tfc_oidc_provider` | Create TFC OIDC provider in AWS | `true` |
| `create_aws_github_oidc_provider` | Create GitHub OIDC provider in AWS | `true` |

## Workspace Variables

When deploying this module via TFC, set these on the workspace:

| Variable | Type | Description |
|----------|------|-------------|
| `TFE_TOKEN` | env (sensitive) | TFC token for managing resources |
| `TFC_AWS_PROVIDER_AUTH` | env | Set to `true` |
| `TFC_AWS_RUN_ROLE_ARN` | env | IAM role ARN for OIDC |

Plus the terraform variables listed above.

## Outputs

| Output | Description |
|--------|-------------|
| `tfc_project_id` | TFC project ID |
| `tfc_project_name` | TFC project name |
| `workspace_ids` | Map of workspace names to IDs |
| `workspace_names` | List of created workspace names |
| `iam_role_arns` | Map of IAM role ARNs |
| `github_environment_name` | GitHub environment name |

## GitHub Actions Variables

The module creates these GitHub Actions environment variables:

| Variable | Maps to CLI Flag |
|----------|------------------|
| `VERBOSITY` | `-v` |
| `OUTPUT` | `-o` |
| `STATE_MODE` | `-s` |
| `PLATFORM` | `-p` |
| `TFC_ORG` | `-t` |
| `PREFIX` | `-x` |
| `TFC_ENVIRONMENT` | `-e` |
| `ENABLE_TEAM` | `-m` |
| `AUTO_UPDATE_PROVIDERS` | `-a` |
| `AWS_ROLE_ARN` | (OIDC auth) |
| `AWS_REGION` | (OIDC auth) |

## Running the Workflow

After deploying:

1. Go to your identity management repository → Actions
2. Run "IAM Identity Center Generator" workflow
3. Select environment and options
4. The workflow creates a PR with generated code
5. Merging triggers TFC workspace runs

## File Structure

```
infrastructure/
├── main.tf
├── variables.tf
├── outputs.tf
├── providers.tf
└── modules/
    ├── tfc-single-state/
    └── tfc-multi-state/
```
