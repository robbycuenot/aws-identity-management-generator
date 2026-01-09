resource "aws_dynamodb_table_item" "settings_table_settings_item" {
  table_name = var.environment_data.table.name
  hash_key   = var.environment_data.table.hash_key

  item = jsonencode({
    id = {
      "S" = local.entity_id
    },
    accounts = {
      "L" = [for account in var.account_names : {
        "M" = {
          "id"   = {
            "S" = var.environment_data.account_map_by_name[account].id 
          },
          "name" = {
            "S" = var.environment_data.account_map_by_name[account].name 
          }
        }
      }]
    },
    approvalRequired = {
      "BOOL" = var.approval_required 
    },
    createdAt = {
      "S" = "${formatdate("YYYY-MM-DD'T'hh:mm:ss", time_static.created_at.rfc3339)}.000Z" 
    },
    duration = {
      "S" = tostring(var.max_duration) 
    },
    modifiedBy = {
      "S" = "terraform" 
    },
    name = {
      "S" = var.entity_value
    },
    ous               = {
      "L" = [for ou_name in var.ou_names : {
        "M" = {
          "id"   = {
             "S" = lower(ou_name) == "root" ? var.environment_data.root_id : var.environment_data.ou_map_by_name[ou_name].id 
             },
          "name" = {
             "S" = lower(ou_name) == "root" ? "Root" : var.environment_data.ou_map_by_name[ou_name].name
             }
        }
      }]
    },
    permissions = {
      "L" = [
        for permission_set in data.aws_ssoadmin_permission_set.permission_sets : {
          "M" = {
            "id"  = {
              "S" = permission_set.arn 
            },
            "name" = {
              "S" = permission_set.name 
            }
          }
        }
      ]
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
      "S" = "Eligibility" 
    }
  })
}
