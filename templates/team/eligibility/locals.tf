locals {
  # Determine the entity_id based on the entity_type
  entity_id = (
    # If the entity_type is "Group", fetch the ID from the first element in the aws_identitystore_group data source
    var.entity_type == "Group" ? 
      data.aws_identitystore_group.entity_group[0].id : 

    # If the entity_type is "User", fetch the ID from the first element in the aws_identitystore_user data source
    var.entity_type == "User" ? 
      data.aws_identitystore_user.entity_user[0].id : 

    # If entity_type does not match "Group" or "User", return an error indicating an invalid entity_type
      error("Invalid entity_type: ${var.entity_type}")
  )
}
