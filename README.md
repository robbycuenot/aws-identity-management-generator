# AWS IAM Identity Center Generator

Automated Terraform code generation for AWS IAM Identity Center.

> **Companion Repository:** [aws-identity-management](https://github.com/robbycuenot/aws-identity-management) - The output repository where generated Terraform configurations are stored and applied.

This tool reverse-generates the current AWS IAM Identity Center state into structured Terraform HCL, addressing challenges that come with maintaining a system modified by multiple sources (SCIM, AWS console, Account Factory, break-glass scenarios, etc.).

## Quick Start

Get running in 5 minutes with Codespaces - no local setup required.

**1. Launch Codespaces:**

[![Open in GitHub Codespaces](https://github.com/codespaces/badge.svg)](https://codespaces.new/robbycuenot/aws-identity-management-generator)

   - Click the badge above, or go to [the repo](https://github.com/robbycuenot/aws-identity-management-generator) → Code → Codespaces → Create codespace
   - Wait for the environment to build (~2 minutes)

**2. Create the read-only permission set** (run in AWS CloudShell on your Identity Center account):
```bash
curl -sL https://raw.githubusercontent.com/robbycuenot/aws-identity-management-generator/main/scripts/create_permission_set.sh | bash
```

**3. Get AWS credentials:**
   - Go to your AWS access portal
   - Select the Identity Center account → `AWSIdentityMgmtGeneratorReadOnly`
   - Copy the environment variables and paste into the Codespaces terminal
   - If your Identity Center region is not `us-east-1`, run: `export AWS_REGION=<your-region>`

**4. Run the generator:**
```bash
python3 scripts/iam_identity_center_generator.py -v normal -o output
```

Your Terraform code is now in `output/`. Run `terraform init && terraform apply` to manage Identity Center as code.

**For ongoing automation**, see [GitHub Actions](#github-actions) to set up automatic PR generation on a schedule.

---

## How It Works

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  AWS Identity   │────▶│    Generator    │────▶│   Terraform     │
│     Center      │     │  (this repo)    │     │   Code (.tf)    │
└─────────────────┘     └─────────────────┘     └─────────────────┘
                                                        │
                                                        ▼
                                                ┌─────────────────┐
                                                │ terraform apply │
                                                └─────────────────┘
```

The generator reads your current AWS state and produces Terraform configurations. You then apply those configurations to manage Identity Center as code.

---

## Running the Generator

Choose how to run the generator based on your needs:

| Method | Best For | Setup Effort |
|--------|----------|--------------|
| [Codespaces](#codespaces) | Quick start, no local setup | Lowest |
| [GitHub Actions](#github-actions) | Automation, teams, PRs | Low |
| [Local Python](#local-python) | Development, debugging | Medium |
| [Container](#container) | CI/CD, air-gapped environments | Low |

### Codespaces

Zero local setup - runs entirely in the browser. Great for quick testing or when you can't install dependencies locally.

[![Open in GitHub Codespaces](https://github.com/codespaces/badge.svg)](https://codespaces.new/robbycuenot/aws-identity-management-generator)

1. Click the badge above or go to Code → Codespaces → Create codespace
2. Wait for the environment to build (includes Python, AWS CLI, Terraform)
3. Get AWS credentials (see [Prerequisites](#permission-set-for-local-development) to create the permission set, then copy credentials from your access portal)
4. Run the generator:

```bash
cd scripts
python3 iam_identity_center_generator.py -v normal -o ../output
```

The devcontainer is pre-configured with all dependencies.

### GitHub Actions

The recommended approach for ongoing use. Runs automatically, creates PRs with changes.

**Setup:**

1. **Import the output repository** (don't fork - output contains identity data):
   - Go to [github.com/new/import](https://github.com/new/import)
   - Import `https://github.com/robbycuenot/aws-identity-management` as a private repo

2. **Create a GitHub environment:**
   - Go to your repo → Settings → Environments → New environment
   - Name it `production` (or your preferred name)

3. **Set up AWS OIDC** (run in CloudShell on your Identity Center account):
   ```bash
   export GITHUB_ORG="your-org-or-username"
   export GITHUB_REPO="aws-identity-management"  # or your repo name
   export GITHUB_ENV="production"                 # must match step 2

   curl -sL https://raw.githubusercontent.com/robbycuenot/aws-identity-management-generator/main/scripts/create_github_oidc.sh | bash
   ```

4. **Add the output values** to your GitHub environment variables:
   - `AWS_ROLE_ARN` - from script output
   - `AWS_REGION` - where Identity Center is configured (e.g., `us-east-1`)

5. **Run the workflow:**
   - Go to Actions → "IAM Identity Center Generator" → Run workflow
   - Select your environment and click "Run workflow"
   - Review and merge the generated PR

**Advanced configuration:**

| Variable | Default | Description |
|----------|---------|-------------|
| `AWS_REGION` | *(required)* | AWS region for Identity Center |
| `AWS_ROLE_ARN` | *(required)* | OIDC role ARN |
| `GENERATOR_REPO_OWNER` | `robbycuenot` | Generator repo owner |
| `GENERATOR_REPO_NAME` | `aws-identity-management-generator` | Generator repo name |
| `STATE_MODE` | `single` | `single` or `multi` |
| `PLATFORM` | `local` | `local` or `tfc` |
| `OUTPUT` | `.` | Output directory |
| `PREFIX` | `aws-identity-management` | Naming prefix (TFC) |
| `ENABLE_TEAM` | `false` | Enable TEAM support |
| `RETAIN_MANAGED_POLICIES` | `false` | Skip managed policy refresh |

**Using a private generator fork:**
1. Import the generator repo privately
2. Generate an SSH deploy key and add to generator repo
3. Add private key as `GENERATOR_DEPLOY_KEY` secret
4. Set `GENERATOR_REPO_OWNER` to your org

### Local Python

Best for development, debugging, or one-off runs.

**Requirements:** Python 3.13+, AWS CLI v2, Terraform CLI

**Setup:**
```bash
git clone https://github.com/robbycuenot/aws-identity-management-generator.git
cd aws-identity-management-generator

# Linux/macOS
source scripts/activate_env.sh

# Windows PowerShell
.\scripts\activate_env.ps1
```

**Get AWS credentials:**
1. Go to your AWS access portal
2. Select the Identity Center account
3. Choose `AWSIdentityMgmtGeneratorReadOnly` (or create it - see [Prerequisites](#prerequisites))
4. Copy environment variables to your terminal

**Run:**
```bash
cd scripts
python3 iam_identity_center_generator.py -v normal -o ../output
```

**Apply:**
```bash
cd ../output
terraform init && terraform plan && terraform apply
```

### Container

No local dependencies required. Good for CI/CD pipelines or air-gapped environments.

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

## State Management

Where your Terraform state lives after running `terraform apply`.

| Platform | Backend | Use Case |
|----------|---------|----------|
| `local` (default) | Local filesystem | Simple setups, manual applies |
| `tfc` | Terraform Cloud | Teams, remote state, automated applies |

### Local Backend

State is stored on whatever machine runs `terraform apply`. Generated code is committed to git, but `.tfstate` files are gitignored.

This is the default and requires no additional setup.

### Terraform Cloud

For team environments with remote state and automated applies.

**Option 1: Infrastructure Module** (recommended)
- Automates TFC workspace, OIDC, and GitHub environment setup
- See [infrastructure module documentation](infrastructure/README.md)

**Option 2: Manual Configuration**
- Create TFC workspace(s) manually
- Set `PLATFORM=tfc`, `TFC_ORG`, and `TFC_ENVIRONMENT` variables
- Configure OIDC authentication

**Note:** The generator regenerates `providers.tf` on each run, so custom backend configurations (like S3) would be overwritten. Use TFC or wrap the output in a parent module with your own backend.

---

## Prerequisites

### AWS Requirements

1. **AWS IAM Identity Center** enabled
2. **Delegated administrator account** recommended (keeps Identity Center separate from management account)
3. **Read-only access** via permission set or IAM role

### Permission Set for Local Development

Create `AWSIdentityMgmtGeneratorReadOnly` with these AWS managed policies:

| Policy | Purpose |
|--------|---------|
| `AWSSSOReadOnly` | Read IAM Identity Center configuration |
| `AWSSSODirectoryReadOnly` | Read Identity Store (users, groups) |
| `IAMReadOnlyAccess` | Read IAM managed policies |
| `AmazonDynamoDBReadOnlyAccess` | *(Optional)* Only if using TEAM |

Plus an inline policy for Identity Store lookups (not covered by managed policies):
```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Action": ["identitystore:GetGroupId", "identitystore:GetUserId", "identitystore:GetGroupMembershipId"],
    "Resource": "*"
  }]
}
```

**Quick setup via CloudShell:**
```bash
curl -sL https://raw.githubusercontent.com/robbycuenot/aws-identity-management-generator/main/scripts/create_permission_set.sh | bash
```

---

## Configuration Options

### Single vs Multi-State Mode

| Mode | Workspaces | Use Case |
|------|------------|----------|
| `single` (default) | 1 | Most environments, simpler management |
| `multi` | 5 | Large environments (1000+ assignments) |

### CLI Reference

| Flag | Description | Default |
|------|-------------|---------|
| `-v, --verbosity` | `quiet`, `normal`, `verbose` | `normal` |
| `-o, --output` | Output directory | `./output` |
| `-s, --state-mode` | `single` or `multi` | `single` |
| `-p, --platform` | `local` or `tfc` | `local` |
| `-t, --tfc-org` | TFC organization | - |
| `-x, --prefix` | Naming prefix | `aws-identity-management` |
| `-e, --environment` | Environment name | - |
| `-m, --enable-team` | Enable TEAM support | `false` |
| `-a, --auto-update-providers` | Auto-update providers | `true` |
| `-r, --retain-managed-policies` | Skip policy refresh | `false` |

### AWS TEAM Support

[AWS TEAM (Temporary Elevated Access Management)](https://aws-samples.github.io/iam-identity-center-team/) provides just-in-time, approval-based temporary access. Enable with `-m true` or `ENABLE_TEAM=true`.

⚠️ **Import limitation:** TEAM eligibility and approver policies are stored in DynamoDB and cannot be imported into Terraform. For existing TEAM deployments:

1. Run the generator with `-m true` to create Terraform code
2. Delete existing policies in the TEAM console
3. Run `terraform apply` to recreate them under Terraform management

This is a one-time migration step.

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

Priority: CLI flags > environment variables > config.yaml > defaults

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
# Fetch AWS state once (slow), then iterate on generation (fast)
python3 iam_identity_center_generator.py fetch -v normal
python3 iam_identity_center_generator.py generate -v normal -o ../output

# Skip managed policy refresh for faster runs
python3 iam_identity_center_generator.py -r true -o ../output
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

## Keeping Up to Date

Both repos include a `sync-from-upstream.yaml` workflow that creates PRs to pull updates from the upstream public repos.

---

## License

GNU General Public License v3.0 - see [LICENSE](LICENSE).
