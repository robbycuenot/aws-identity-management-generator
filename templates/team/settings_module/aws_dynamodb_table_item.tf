resource "aws_dynamodb_table_item" "settings_table_settings_item" {
  table_name = var.table.name
  hash_key   = var.table.hash_key

  item = jsonencode({
    id = {
      "S" = "settings"
    },
    approval = {
      "BOOL" = var.require_approvals
    },
    comments = {
      "BOOL" = var.require_comments
    },
    createdAt = {
      "S" = "${formatdate("YYYY-MM-DD'T'hh:mm:ss", time_static.created_at.rfc3339)}.000Z"
    },
    duration = {
      "S" = tostring(var.request_maximum_duration_hours)
    },
    expiry = {
      "S" = tostring(var.request_expiration_time_hours)
    },
    modifiedBy = {
      "S" = var.modified_by_user
    },
    sesNotificationsEnabled = {
      "BOOL" = var.ses_notifications_enabled
    },
    sesSourceArn = {
      "S" = var.ses_source_arn
    },
    sesSourceEmail = {
      "S" = var.ses_source_email
    },
    slackNotificationsEnabled = {
      "BOOL" = var.slack_notifications_enabled
    },
    slackToken = {
      "S" = var.slack_token
    },
    snsNotificationsEnabled = {
      "BOOL" = var.sns_notifications_enabled
    },
    teamAdminGroup = {
      "S" = var.team_admin_group
    },
    teamAuditorGroup = {
      "S" = var.team_auditor_group
    },
    ticketNo = {
      "BOOL" = var.require_ticket_number
    },
    updatedAt = {
      "S" = "${formatdate("YYYY-MM-DD'T'hh:mm:ss", time_static.updated_at.rfc3339)}.000Z"
    },
    __typename = {
      "S" = "Settings"
    }
  })
}
