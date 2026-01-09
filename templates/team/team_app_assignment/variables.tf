# Variables for TEAM application assignment
# This module assigns a single user or group to the TEAM Identity Center application

variable "principal_name" {
  description = "Username or group name to assign to TEAM application"
  type        = string
}

variable "principal_type" {
  description = "Type of principal (USER or GROUP)"
  type        = string
  validation {
    condition     = contains(["USER", "GROUP"], var.principal_type)
    error_message = "principal_type must be either USER or GROUP"
  }
}

variable "sso_identity_store_id" {
  description = "ID of the IAM Identity Center identity store"
  type        = string
}

variable "team_application_arn" {
  description = "ARN of the TEAM customer managed application in Identity Center"
  type        = string
}
