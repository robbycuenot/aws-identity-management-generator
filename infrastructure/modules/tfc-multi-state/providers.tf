# Provider configuration for the AWS Identity Management Integration module

terraform {
  required_version = "1.14.3"

  required_providers {
    aws = {
      source                = "hashicorp/aws"
      version               = "6.27.0"
      configuration_aliases = [aws.identity_center]
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

# Note: Provider configurations are passed from the calling module
