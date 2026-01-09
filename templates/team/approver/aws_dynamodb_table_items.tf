resource "aws_dynamodb_table_item" "settings_table_settings_item" {
  table_name = var.environment_data.table.name
  hash_key   = var.environment_data.table.hash_key

  item = jsonencode({
    id = {
      "S" = local.entity_id
    },
    approvers = {
      "L" = [for approver in var.approvers : {
        "S" = approver
      }]
    },
    createdAt = {
      "S" = "${formatdate("YYYY-MM-DD'T'hh:mm:ss", time_static.created_at.rfc3339)}.000Z" 
    },
    groupIds = {
      "L" = [for group in data.aws_identitystore_group.approvers : {
        "S" = group.id
      }]
    },
    modifiedBy = {
      "S" = "terraform" 
    },
    name = {
      "S" = lower(var.entity_value) == "root" ? "Root" : var.entity_value
    },
    ticketNo = {
      "S" = "" 
    },
    type = {
      "S" = var.entity_type 
    },
    updatedAt         = {
      "S" = "${formatdate("YYYY-MM-DD'T'hh:mm:ss", time_static.updated_at.rfc3339)}.000Z" 
    },
    __typename = {
      "S" = "Approvers" 
    }
  })
}
