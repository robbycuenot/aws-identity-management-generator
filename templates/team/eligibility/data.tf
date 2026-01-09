# Fetch an AWS Identity Store Group if entity_type is 'Group'
data "aws_identitystore_group" "entity_group" {
  identity_store_id = var.environment_data.sso_identity_store_id
  count = var.entity_type == "Group" ? 1 : 0

  alternate_identifier {
    unique_attribute {
      attribute_path  = "DisplayName"
      attribute_value = var.entity_value
    }
  }
}

# Fetch an AWS Identity Store User if entity_type is 'User'
data "aws_identitystore_user" "entity_user" {
  identity_store_id = var.environment_data.sso_identity_store_id
  count = var.entity_type == "User" ? 1 : 0

  alternate_identifier {
    unique_attribute {
      attribute_path  = "UserName"
      attribute_value = var.entity_value
    }
  }
}

data "aws_ssoadmin_permission_set" "permission_sets" {
  for_each = toset(var.permission_sets)

  instance_arn = var.environment_data.sso_instance
  name         = each.key
}
