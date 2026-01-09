resource "time_static" "created_at" {}

resource "time_static" "updated_at" {
  triggers = {
    content_hash = sha256(jsonencode({
        approvers           = var.approvers,
        entity_type         = var.entity_type,
        entity_value        = var.entity_value,
    }))
  }
}
