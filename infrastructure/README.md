# Infrastructure Module

Terraform module that deploys the infrastructure required to run the AWS IAM Identity Center Generator with Terraform Cloud.

## What Gets Created

**In AWS:**
- IAM OIDC providers for Terraform Cloud and GitHub Actions
- IAM roles with least-privilege permissions

**In Terraform Cloud:**
- Project (optional) and Workspace(s) with VCS integration
- OIDC authentication to AWS (no static credentials)

**In GitHub:**
- Environment with variables and secrets
- Deploy key for accessing the generator repository
- OIDC authentication to AWS (no static credentials)

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
   - Administration: Read and write (for deploy keys on generator repo)
   - Codespaces secrets: Read and write
   - Environments: Read and write
   - Secrets: Read and write
   - Variables: Read and write

3. Create a TFC workspace for deploying this infrastructure module, then run these commands in AWS CloudShell on your Identity Center account to create the deployment role:
   ```bash
   read -p "TFC Organization: " TFC_ORG && \
   read -p "TFC Project: " TFC_PROJECT && \
   read -p "TFC Workspace: " TFC_WORKSPACE && \
   export TFC_ORG TFC_PROJECT TFC_WORKSPACE && \
   curl -sL https://raw.githubusercontent.com/robbycuenot/aws-identity-management-generator/main/scripts/create_infrastructure_role.sh | bash
   ```
   The script will output the environment variables to set on your TFC workspace.

4. Get your GitHub App Installation ID for TFC VCS integration, OR your OAuth Token ID if using OAuth connection

5. Create a TFC workspace with VCS integration pointing to your imported generator repository, with working directory set to `infrastructure`

## Configuration

Set these variables in your TFC workspace:

### Required

| Variable | Type | Sensitive | Description |
|----------|------|-----------|-------------|
| `TFC_AWS_PROVIDER_AUTH` | env | no | Set to `true` |
| `TFC_AWS_RUN_ROLE_ARN` | env | no | IAM role ARN for OIDC (from setup script) |
| `TFE_TOKEN` | env | **yes** | TFC token for managing TFC resources |
| `tfc_organization_name` | terraform | no | TFC organization name (must exist) |
| `environment` | terraform | no | Environment name (used in naming and GitHub environment) |
| `github_owner` | terraform | no | GitHub organization or user |
| `github_installation_id` | terraform | no | GitHub App installation ID for VCS (use this OR `github_oauth_token_id`) |
| `github_oauth_token_id` | terraform | no | GitHub OAuth token ID for VCS (use this OR `github_installation_id`) |
| `github_token` | terraform | **yes** | GitHub PAT |

### Optional

| Variable | Type | Sensitive | Description | Default |
|----------|------|-----------|-------------|---------|
| `deployment_mode` | terraform | no | `tfc-single-state` or `tfc-multi-state` | `tfc-single-state` |
| `prefix` | terraform | no | Prefix for project/workspace/role names | `aws-identity-management` |
| `tfc_project_name` | terraform | no | TFC project name (if null, computed as `prefix-environment`) | `null` |
| `aws_region` | terraform | no | AWS Region for Identity Center | `us-east-1` |
| `github_repo` | terraform | no | Identity management repository name | `aws-identity-management` |
| `github_generator_repo` | terraform | no | Generator repository name | `aws-identity-management-generator` |
| `verbosity` | terraform | no | Generator verbosity level | `normal` |
| `output` | terraform | no | Output directory for generated files | `./output` |
| `enable_team` | terraform | no | Enable TEAM support | `false` |
| `auto_update_providers` | terraform | no | Auto-update provider versions | `true` |
| `retain_managed_policies` | terraform | no | Skip managed policy refresh for faster runs | `false` |
| `create_tfc_project` | terraform | no | Create TFC project | `true` |
| `create_aws_tfc_oidc_provider` | terraform | no | Create TFC OIDC provider in AWS | `false` |
| `create_aws_github_oidc_provider` | terraform | no | Create GitHub OIDC provider in AWS | `false` |

### TFC Agent on ECS Fargate (Optional - Single-State Mode Only)

| Variable | Type | Sensitive | Description | Default |
|----------|------|-----------|-------------|---------|
| `enable_tfc_agent_ecs` | terraform | no | Enable TFC agent on ECS Fargate (single-state mode only) | `false` |
| `tfc_agent_name` | terraform | no | Name for the TFC agent (appears in TFC UI) | `ecs-agent` |
| `tfc_agent_tasks_per_run` | terraform | no | Number of ECS tasks to start per run (2 = one for plan, one for apply) | `2` |
| `tfc_agent_vpc_id` | terraform | no | VPC ID (required if `enable_tfc_agent_ecs = true`) | `null` |
| `tfc_agent_subnet_ids` | terraform | no | Private subnet IDs with NAT (required if `enable_tfc_agent_ecs = true`) | `null` |
| `docker_hub_username` | terraform | no | Docker Hub username (required if `enable_tfc_agent_ecs = true`) | `null` |
| `docker_hub_access_token` | terraform | **yes** | Docker Hub access token (required if `enable_tfc_agent_ecs = true`) | `null` |

Note: `enable_tfc_agent_ecs` is only supported with `deployment_mode = "tfc-single-state"`. Attempting to use it with multi-state mode will fail.

**Docker Hub Credentials:** Docker Hub requires authentication for ECR pull-through cache. Create a Docker Hub access token at https://hub.docker.com/settings/security

## Outputs

| Output | Description |
|--------|-------------|
| `tfc_project_id` | TFC project ID |
| `tfc_project_name` | TFC project name |
| `workspace_ids` | Map of workspace names to IDs |
| `workspace_names` | List of created workspace names |
| `iam_role_arns` | Map of IAM role ARNs |
| `github_environment_name` | GitHub environment name |

### TFC Agent ECS Outputs (when `enable_tfc_agent_ecs = true`)

| Output | Description |
|--------|-------------|
| `tfc_agent_pool_id` | ID of the TFC agent pool |
| `tfc_agent_pool_name` | Name of the TFC agent pool |
| `tfc_agent_webhook_url` | Webhook URL for TFC notifications |
| `tfc_agent_ecs_cluster_name` | Name of the ECS cluster |
| `tfc_agent_vpc_id` | ID of the VPC |
| `tfc_agent_subnet_ids` | Subnet IDs used by ECS tasks |
| `tfc_agent_cloudwatch_log_group` | CloudWatch log group for agent logs |

## TFC Agent on ECS Fargate (Single-State Mode Only)

The module can deploy a webhook-triggered Terraform Cloud agent on ECS Fargate. This is only available when using `deployment_mode = "tfc-single-state"`.

- **Single-execution mode**: Tasks start on demand, execute one job, then exit
- **Pay only for execution time**: No idle costs
- **16 vCPU, 32 GB RAM, 200 GB storage** (maximum Fargate configuration)
- **ECR pull-through cache**: Images cached in your account
- **Webhook-triggered**: TFC notifications start ECS tasks automatically
- **Automatic workspace configuration**: The workspace is automatically configured to use agent execution mode

### Usage

Provide your VPC ID, private subnet IDs, and Docker Hub credentials:

```hcl
enable_tfc_agent_ecs      = true
tfc_agent_vpc_id          = "vpc-0123456789abcdef0"
tfc_agent_subnet_ids      = ["subnet-aaa", "subnet-bbb"]
docker_hub_username       = "your-docker-hub-username"
docker_hub_access_token   = "dckr_pat_xxxxx"  # Mark as sensitive in TFC
```

**Note:** Docker Hub requires authentication for ECR pull-through cache. Create an access token at https://hub.docker.com/settings/security

### What Gets Created

**In Terraform Cloud:**
- Agent pool (organization-scoped)
- Agent token (stored in AWS Secrets Manager)

**In AWS:**
- API Gateway HTTP endpoint (webhook receiver)
- Lambda function (starts ECS tasks on webhook)
- ECR pull-through cache rule for Docker Hub
- ECS cluster with Fargate capacity provider
- ECS task definition (single-execution mode)
- Security group allowing outbound traffic
- IAM roles for Lambda, task execution, and ECS Exec
- CloudWatch log groups for Lambda and ECS tasks

### How It Works

```
TFC Run Created → Webhook POST → API Gateway → Lambda → ECS RunTask
                                                            ↓
                                              Task picks up job, executes, exits
```

1. When a run is created in the workspace, TFC sends a webhook
2. API Gateway receives the webhook and invokes Lambda
3. Lambda verifies the HMAC signature and starts 2 ECS tasks
4. Tasks connect to TFC, pick up the plan/apply jobs, execute, then exit
5. You only pay for actual execution time

### ECR Pull-Through Cache

Images are pulled through ECR instead of directly from Docker Hub. This provides:
- Cached images in your AWS account
- No Docker Hub rate limits
- Images stay in your security boundary
- Automatic caching on first pull

The image path becomes:
```
<account_id>.dkr.ecr.<region>.amazonaws.com/docker-hub/hashicorp/tfc-agent:latest
```

### Viewing Logs

```bash
# ECS task logs
aws logs tail /ecs/aws-identity-management-<environment>-tfc-agent --follow

# Webhook Lambda logs
aws logs tail /aws/lambda/aws-identity-management-<environment>-tfc-agent-webhook --follow
```

### Debugging with ECS Exec

```bash
# Get task ARN
TASK_ARN=$(aws ecs list-tasks --cluster aws-identity-management-<environment>-tfc-agent-cluster --query 'taskArns[0]' --output text)

# Connect to container
aws ecs execute-command --cluster aws-identity-management-<environment>-tfc-agent-cluster --task $TASK_ARN --container tfc-agent --interactive --command /bin/sh
```

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

If using Codespaces on the aws-identity-management repo with your own private generator repo's Docker image, you need to grant your identity management repository access to the container package:

1. Go to your generator repository's Packages page (e.g., `github.com/your-org/aws-identity-management-generator/pkgs/container/aws-identity-management-generator`)
2. Click "Package settings"
3. Under "Manage Codespaces access", click "Add Repository"
4. Select your `aws-identity-management` repository
5. Set Role to "Read"

This allows Codespaces in the identity management repo to pull the generator Docker image.
