resource "time_static" "created_at" {}

resource "time_static" "updated_at" {
  triggers = {
    content_hash = sha256(jsonencode({
        account_names       = var.account_names,
        approval_required   = var.approval_required,
        entity_type         = var.entity_type,
        entity_value        = var.entity_value,
        max_duration        = var.max_duration,
        ou_names            = var.ou_names,
        permission_sets     = var.permission_sets,
        root_id             = var.environment_data.root_id,
        table               = var.environment_data.table,
    }))
  }
}
