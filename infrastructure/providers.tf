# Infrastructure module provider configuration

terraform {
  required_version = "1.14.3"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "6.27.0"
    }
    tfe = {
      source  = "hashicorp/tfe"
      version = "0.72.0"
    }
    github = {
      source  = "integrations/github"
      version = "6.9.0"
    }
    tls = {
      source  = "hashicorp/tls"
      version = "4.1.0"
    }
  }
}

# AWS Provider for Identity Center account
provider "aws" {
  alias  = "identity_center"
  region = var.aws_region
}

# TFE Provider for managing workspaces
provider "tfe" {
  # Uses TFE_TOKEN environment variable
}

# GitHub Provider for managing Actions variables
provider "github" {
  owner = var.github_owner
  token = var.github_token
}
