resource "time_static" "created_at" {}

resource "time_static" "updated_at" {
  triggers = {
    content_hash = sha256(jsonencode({
      approval                  = var.require_approvals
      comments                  = var.require_comments
      duration                  = tostring(var.request_maximum_duration_hours)
      expiry                    = tostring(var.request_expiration_time_hours)
      modifiedBy                = var.modified_by_user
      sesNotificationsEnabled   = var.ses_notifications_enabled
      sesSourceArn              = var.ses_source_arn
      sesSourceEmail            = var.ses_source_email
      slackNotificationsEnabled = var.slack_notifications_enabled
      slackToken                = var.slack_token
      snsNotificationsEnabled   = var.sns_notifications_enabled
      teamAdminGroup            = var.team_admin_group
      teamAuditorGroup          = var.team_auditor_group
      ticketNo                  = var.require_ticket_number
    }))
  }
}
