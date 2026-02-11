locals {
  # Determine the entity_id based on the entity_type using pre-fetched maps
  entity_id = (
    var.entity_type == "Group" ? 
      var.environment_data.groups_map[var.entity_value] : 
    var.entity_type == "User" ? 
      var.environment_data.users_map[var.entity_value] : 
      error("Invalid entity_type: ${var.entity_type}")
  )
}
