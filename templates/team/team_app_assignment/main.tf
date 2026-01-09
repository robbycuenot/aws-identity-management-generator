# TEAM Application Assignment
# Creates a single assignment for a user or group to access
# the TEAM customer managed application in IAM Identity Center

resource "aws_ssoadmin_application_assignment" "this" {
  application_arn = var.team_application_arn
  principal_id    = var.principal_type == "USER" ? data.aws_identitystore_user.principal[0].user_id : data.aws_identitystore_group.principal[0].group_id
  principal_type  = var.principal_type
}
