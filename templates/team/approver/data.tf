data "aws_identitystore_group" "approvers" {
  for_each = toset(var.approvers)
  
  identity_store_id = var.environment_data.sso_identity_store_id

  alternate_identifier {
    unique_attribute {
      attribute_path  = "DisplayName"
      attribute_value = each.value
    }
  }
}
