variable "account_names" {
  type = list(string)
}

variable "approval_required" {
  type = bool
  default = true
}

variable "entity_type" {
  type = string
}

variable "entity_value" {
  type = string
}

variable "environment_data" {
  type = object({
    account_map_by_name = map(object({
      arn    = string
      email  = string
      id     = string
      name   = string
      status = string
    }))
    ou_map_by_name = map(object({
      arn  = string
      id   = string
      name = string
    }))
    root_id              = string
    sso_identity_store_id = string
    sso_instance = string
    table = object({
      name     = string
      hash_key = string
    })
  })
}

variable "max_duration" {
  type = number
}

variable "ou_names" {
  type = list(string)
}

variable "permission_sets" {
  type = list(string)
}
