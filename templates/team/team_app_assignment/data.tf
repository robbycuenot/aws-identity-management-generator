# Data sources for TEAM application assignment
# Looks up Identity Center ID for the principal

# Look up user ID (only if principal_type is USER)
data "aws_identitystore_user" "principal" {
  count = var.principal_type == "USER" ? 1 : 0

  identity_store_id = var.sso_identity_store_id

  alternate_identifier {
    unique_attribute {
      attribute_path  = "UserName"
      attribute_value = var.principal_name
    }
  }
}

# Look up group ID (only if principal_type is GROUP)
data "aws_identitystore_group" "principal" {
  count = var.principal_type == "GROUP" ? 1 : 0

  identity_store_id = var.sso_identity_store_id

  alternate_identifier {
    unique_attribute {
      attribute_path  = "DisplayName"
      attribute_value = var.principal_name
    }
  }
}
