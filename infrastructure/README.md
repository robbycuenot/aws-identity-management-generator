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

1. Import both repositories to your organization via [github.com/new/import](https://github.com/new/import) (don't fork - output contains identity data):
   - `https://github.com/robbycuenot/aws-identity-management-generator`
   - `https://github.com/robbycuenot/aws-identity-management`

2. Create a GitHub Personal Access Token (fine-grained) with permissions on **both repositories** (`aws-identity-management` and `aws-identity-management-generator`):
   - Metadata: Read
   - Actions: Read and write
   - Actions variables: Read and write
   - Administration: Read and write (for deploy keys on generator repo)
   - Codespaces secrets: Read and write
   - Environments: Read and write
   - Secrets: Read and write

3. Create a TFC workspace for deploying this infrastructure module, then run this script in AWS CloudShell on your Identity Center account to create the deployment role:
   ```bash
   curl -sL https://raw.githubusercontent.com/robbycuenot/aws-identity-management-generator/main/scripts/create_infrastructure_role.sh | bash
   ```
   The script will prompt for your TFC organization, project, and workspace names, then output the environment variables to set on your workspace.

4. Get your GitHub App Installation ID for TFC VCS integration, OR your OAuth Token ID if using OAuth connection

5. Create a TFC workspace with VCS integration pointing to your imported generator repository, with working directory set to `infrastructure`

## Configuration

Create a `terraform.tfvars` file in the `infrastructure/` directory of your generator repo (this file is gitignored):

```hcl
# Required
environment            = "production"
github_owner           = "your-github-org"
github_installation_id = "12345678"  # OR use github_oauth_token_id
github_token           = "ghp_xxxx"  # Or use TFC variable set
tfc_organization_name  = "your-tfc-org"

# Optional
deployment_mode                 = "tfc-single-state"
prefix                          = "aws-identity-management"
aws_region                      = "us-east-1"
enable_team                     = false
create_tfc_project              = true

# Set to false if OIDC providers were created by the setup script
create_aws_tfc_oidc_provider    = false
create_aws_github_oidc_provider = false
```

Alternatively, set these as Terraform variables directly in your TFC workspace.

## Variables

### Required

| Variable | Description |
|----------|-------------|
| `environment` | Environment name (used in naming and GitHub environment) |
| `github_owner` | GitHub organization or user |
| `github_installation_id` | GitHub App installation ID for VCS (use this OR `github_oauth_token_id`) |
| `github_oauth_token_id` | GitHub OAuth token ID for VCS (use this OR `github_installation_id`) |
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

When deploying this module via TFC, set these environment variables on the workspace (output by the setup script):

| Variable | Type | Description |
|----------|------|-------------|
| `TFC_AWS_PROVIDER_AUTH` | env | Set to `true` |
| `TFC_AWS_RUN_ROLE_ARN` | env | IAM role ARN for OIDC (from setup script) |
| `TFE_TOKEN` | env (sensitive) | TFC token for managing TFC resources |

Plus the terraform variables listed above (as Terraform variables, not environment variables).

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

## Post-Deployment: Codespaces Package Access

If using Codespaces with the generator Docker image, you need to grant your identity management repository access to the container package:

1. Go to your generator repository's Packages page (e.g., `github.com/your-org/aws-identity-management-generator/pkgs/container/aws-identity-management-generator`)
2. Click "Package settings"
3. Under "Manage Codespaces access", click "Add Repository"
4. Select your `aws-identity-management` repository
5. Set Role to "Read"

This allows Codespaces in the identity management repo to pull the generator Docker image.

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
