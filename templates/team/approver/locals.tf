locals {
  # Determine the entity_id based on the entity_type
  entity_id = (
    # If the entity_type is "Account", fetch the ID from account_map_by_name using entity_value as the key
    var.entity_type == "Account" ? 
      var.environment_data.account_map_by_name[var.entity_value].id : 
      
    # If the entity_type is "OU", further checks are required
    var.entity_type == "OU" ? 
      # If the OU's entity_value is "root" (case-insensitive), use the predefined root_id
      lower(var.entity_value) == "root" ? 
        var.environment_data.root_id :
      # Otherwise, fetch the ID from ou_map_by_name using entity_value as the key
        var.environment_data.ou_map_by_name[var.entity_value].id : 
        
    # If entity_type does not match "Account" or "OU", return an error indicating an invalid entity type
      error("Invalid entity type: ${var.entity_type}")
  )
}
