# AWS IAM Identity Center Generator

Automated Terraform code generation for AWS IAM Identity Center.

This tool reverse-generates the current AWS IAM Identity Center state into structured Terraform HCL, addressing challenges that come with maintaining a system modified by multiple sources (SCIM, AWS console, Account Factory, break-glass scenarios, etc.).

## Overview

The generator:
- Fetches current AWS IAM Identity Center state using boto3
- Generates Terraform configurations using Jinja2 templates
- Creates import statements for seamless resource adoption
- Supports local execution, containers, GitHub Actions, and Terraform Cloud

## Quick Start

**For development:** Start with [Local Development](#local-development) or [Container](#container).

**For production:** Use [Terraform Cloud](infrastructure/README.md) for team environments, or [GitHub Actions](#github-actions) for automated runs.

### Single vs Multi-State Mode

- **Single state** (`-s single`, default): One Terraform state file, one `terraform apply`. Simpler to manage.
- **Multi state** (`-s multi`): Separate state per component. Better for large environments (1000+ assignments).

---

## Prerequisites

1. **AWS IAM Identity Center** enabled in your AWS account
2. **Delegated administrator account** strongly recommended (keeps Identity Center management separate from the management account)
3. **Read-only access** via a permission set or IAM role

### Recommended Permission Set

Create `AWSIdentityMgmtGeneratorReadOnly` with these AWS managed policies:

| Policy | Purpose |
|--------|---------|
| `AWSSSOReadOnly` | Read IAM Identity Center configuration |
| `AWSSSODirectoryReadOnly` | Read Identity Store (users, groups) |
| `IAMReadOnlyAccess` | Read IAM managed policies |
| `AmazonDynamoDBReadOnlyAccess` | *(Optional)* Only needed if using TEAM |

**Quick Setup via CloudShell:**

```bash
curl -sL https://raw.githubusercontent.com/robbycuenot/aws-identity-management-generator/main/scripts/create_permission_set.sh | bash
```

### Getting AWS Credentials

1. Go to your AWS access portal
2. Select the account where IAM Identity Center is deployed
3. Choose the `AWSIdentityMgmtGeneratorReadOnly` permission set
4. Click "Command line or programmatic access"
5. Copy the environment variables and paste into your terminal

---

## Local Development

### Requirements

- Python 3.13+
- AWS CLI v2
- Terraform CLI

### Setup

```bash
git clone https://github.com/robbycuenot/aws-identity-management-generator.git
cd aws-identity-management-generator

# Linux/macOS
source scripts/activate_env.sh

# Windows PowerShell
.\scripts\activate_env.ps1
```

### Run

```bash
cd scripts
python3 iam_identity_center_generator.py -v normal -o ../output

# With TEAM support
python3 iam_identity_center_generator.py -v normal -o ../output -m true

# Multi-state mode
python3 iam_identity_center_generator.py -v normal -o ../output -s multi
```

### Apply

```bash
cd ../output
terraform init
terraform plan
terraform apply
```

---

## Container

No local dependencies required.

```bash
docker pull ghcr.io/robbycuenot/aws-identity-management-generator:latest

docker run --rm \
  -e AWS_ACCESS_KEY_ID \
  -e AWS_SECRET_ACCESS_KEY \
  -e AWS_SESSION_TOKEN \
  -e AWS_REGION=us-east-1 \
  -v $(pwd)/output:/output \
  ghcr.io/robbycuenot/aws-identity-management-generator:latest \
  -v normal -o /output
```

---

## GitHub Actions (Manual Setup)

Automate the generator with GitHub Actions using OIDC authentication.

1. Create private copies of both repositories via [GitHub Import](https://github.com/new/import) (do not fork - generated output contains sensitive identity data):
   - Import `robbycuenot/aws-identity-management-generator` as a private repo
   - Import `robbycuenot/aws-identity-management` as a private repo
   - Both repos include a `sync-from-upstream.yaml` workflow to pull updates from upstream via PR

2. Choose a GitHub environment name (e.g., `production`). Create this environment in both repositories under Settings → Environments. All secrets and variables will be configured in this environment.

3. Create an IAM OIDC provider and role for GitHub Actions with the same permissions as the permission set above. **Important:** The trust policy must reference the GitHub environment name, not the branch. Example subject claim: `repo:your-org/aws-identity-management-generator:environment:production`

4. Configure GitHub environment variables in the `production` environment:
   - `AWS_ROLE_ARN` - ARN of the OIDC role created in step 3
   - `AWS_REGION` - Region where IAM Identity Center is configured
   - `STATE_MODE` - `single` or `multi`
   - `PLATFORM` - `local` or `tfc`
   - `OUTPUT` - Output directory (typically `./output`)
   - `ENABLE_TEAM` - `true` or `false`

5. Add the `GENERATOR_DEPLOY_KEY` secret to the environment (if your generator repo is private).

6. See the [example workflow](https://github.com/robbycuenot/aws-identity-management/blob/main/.github/workflows/iam_identity_center_generator.yaml) for reference.

If using the [infrastructure module](infrastructure/README.md), steps 3-5 are handled automatically.

---

## Terraform Cloud

For full automation with remote state and OIDC authentication, see the [infrastructure module documentation](infrastructure/README.md).

---

## CLI Reference

| Flag | Description | Default |
|------|-------------|---------|
| `-v, --verbosity` | Output level: `quiet`, `normal`, `verbose` | `normal` |
| `-o, --output` | Output directory | `./output` |
| `-s, --state-mode` | `single` or `multi` | `single` |
| `-p, --platform` | `local` or `tfc` | `local` |
| `-t, --tfc-org` | TFC organization (requires `-p tfc`) | - |
| `-x, --prefix` | Prefix for naming (requires `-p tfc`) | `aws-identity-management` |
| `-e, --environment` | Environment name (requires `-p tfc`) | - |
| `-m, --enable-team` | Enable TEAM support | `false` |
| `-a, --auto-update-providers` | Auto-update provider versions | `true` |
| `-r, --retain-managed-policies` | Skip managed policy refresh | `false` |

### config.yaml

```yaml
verbosity: "normal"
output: "./output"
state_mode: "single"
platform: "local"
enable_team: false
auto_update_providers: true
retain_managed_policies: false
```

Priority: CLI flags > config.yaml > defaults

---

## Generated Output

### Single-State Mode

```
output/
├── main.tf
├── providers.tf
├── identity_store/
├── managed_policies/
├── permission_sets/
├── account_assignments/
└── team/                # if enabled
```

### Multi-State Mode

```
output/
├── identity_store/      # Apply first
├── managed_policies/    # Apply first
├── permission_sets/     # Depends on above
├── account_assignments/ # Depends on above
└── team/                # if enabled
```

Apply order: `identity_store` & `managed_policies` → `permission_sets` → `account_assignments` → `team`

---

## Development Tips

```bash
# Fetch AWS state once (slow)
python3 iam_identity_center_generator.py fetch -v normal

# Iterate on generation (fast)
python3 iam_identity_center_generator.py generate -v normal -o ../output

# Skip managed policy refresh for faster runs
python3 iam_identity_center_generator.py -r true -v normal -o ../output
```

Customize templates in `templates/` or extend `phase1_fetch.py` / `phase2_generate.py`.

---

## Troubleshooting

**"No SSO instances found"**
- Verify IAM Identity Center is enabled
- Check `AWS_REGION` matches where Identity Center is configured

**"Permission denied" errors**
- Check CloudTrail for denied API calls
- Verify permission set has required policies

**Rate limiting**
- Use `-r true` to skip managed policy refresh

---

## License

GNU General Public License v3.0 - see [LICENSE](LICENSE).
