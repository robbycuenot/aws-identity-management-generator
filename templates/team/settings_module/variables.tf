variable "modified_by_user" {
  type    = string
  default = "terraform"
}

variable "table" {
  type = object({
    name     = string
    hash_key = string
  })
}

variable "require_approvals" {
  type    = bool
  default = true
}

variable "require_comments" {
  type    = bool
  default = true
}

variable "require_ticket_number" {
  type    = bool
  default = false
}

variable "request_maximum_duration_hours" {
  type    = number
  default = 8
}

variable "request_expiration_time_hours" {
  type    = number
  default = 8
}

variable "ses_notifications_enabled" {
  type    = bool
  default = false
}

variable "ses_source_arn" {
  type    = string
  default = ""
}

variable "ses_source_email" {
  type    = string
  default = ""
}

variable "slack_notifications_enabled" {
  type    = bool
  default = false
}

variable "slack_token" {
  type    = string
  default = ""
}

variable "sns_notifications_enabled" {
  type    = bool
  default = false
}

variable "team_admin_group" {
  type    = string
  default = ""
}

variable "team_auditor_group" {
  type    = string
  default = ""
}
