import os
import time
import json
import re
import shutil
import boto3
from pathlib import Path
from config_loader import get_config

# ------------------------------------------------------------------------
# Constants
# ------------------------------------------------------------------------
# Small delay (in seconds) after each paginated call to avoid throttling.
SLEEP_DELAY = 0.001

# ------------------------------------------------------------------------
# Utilities
# ------------------------------------------------------------------------
def sanitize_name(name: str) -> str:
    """
    Sanitize the name to be compatible with Terraform resource names.
    Ensures the name starts with a letter or underscore and replaces invalid characters with underscores.
    """
    name = name.strip()

    # Ensure the name starts with a letter or underscore
    if not re.match(r'^[a-zA-Z_]', name):
        name = '_' + name

    # Replace invalid characters with underscores
    name = re.sub(r'[^a-zA-Z0-9_-]', '_', name)

    return name


def dump_resources_individually(resources, base_dir, resource_type, key_name, verbosity=0):
    """
    Writes each item in 'resources' to a separate JSON file under:
        base_dir/resource_type/<key_value>.json
    """
    subfolder = Path(base_dir) / resource_type
    subfolder.mkdir(parents=True, exist_ok=True)

    for item in resources:
        item_id = str(item.get(key_name, "unknown"))
        filename = f"{item_id}.json"
        filepath = subfolder / filename

        item["FileName"] = filename

        if verbosity >= 2:
            print(f"[VERBOSE-2] Writing file: {filepath}")

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(item, f, indent=2, ensure_ascii=False, default=str, sort_keys=True)


# ------------------------------------------------------------------------
# SSO Admin Instance
# ------------------------------------------------------------------------
def fetch_sso_admin_instance(sso_admin, instance_arn, verbosity=0):
    if verbosity >= 1:
        print("[FETCH] Fetching SSO admin instance...")

    region_name = sso_admin.meta.region_name
    sso_admin_info = sso_admin.describe_instance(InstanceArn=instance_arn)

    sso_admin_info["Region"] = region_name

    sso_admin_dir = Path(JSON_DIR) / "sso_admin"
    sso_admin_dir.mkdir(parents=True, exist_ok=True)

    instance_name = instance_arn.split('/')[-1]
    sanitized_name = sanitize_name(instance_name)
    sso_admin_info["ResourceName"] = sanitized_name

    filepath = sso_admin_dir / f"{sanitized_name}.json"
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(sso_admin_info, f, indent=2, ensure_ascii=False, default=str)

    if verbosity >= 1:
        print(f"[FETCH] Done fetching SSO admin instance. Region: {region_name}")


# ------------------------------------------------------------------------
# Identity Store - Users
# ------------------------------------------------------------------------
def fetch_users(identity_store, identity_store_id, verbosity=0):
    if verbosity >= 1:
        print("[FETCH] Fetching users...")

    users = []
    paginator = identity_store.get_paginator("list_users")
    for page in paginator.paginate(IdentityStoreId=identity_store_id):
        users.extend(page["Users"])
        time.sleep(SLEEP_DELAY)  # Sleep to avoid throttling

    for u in users:
        sanitized_name = sanitize_name(u["UserName"])

        u["ImportId"] = f"{identity_store_id}/{u['UserId']}"
        u["ImportTo"] = f"aws_identitystore_user.{sanitized_name}"
        u["ResourceName"] = sanitized_name
        u["OriginalName"] = u["UserName"]  # Preserve original for map keys
        u["SCIM"] = any("Id" in external_id for external_id in u.get("ExternalIds", []))

    dump_resources_individually(
        resources=users,
        base_dir=JSON_DIR,
        resource_type="users",
        key_name="ResourceName",
        verbosity=verbosity
    )

    if verbosity >= 1:
        print(f"[FETCH] Done fetching users. Count: {len(users)}")

    # Return map with UserId -> (ResourceName, OriginalName) for lookups
    return {u["UserId"]: {"ResourceName": u["ResourceName"], "OriginalName": u["OriginalName"]} for u in users}


# ------------------------------------------------------------------------
# Identity Store - Groups
# ------------------------------------------------------------------------
def fetch_groups(identity_store, identity_store_id, verbosity=0):
    if verbosity >= 1:
        print("[FETCH] Fetching groups...")

    paginator = identity_store.get_paginator("list_groups")
    groups = []
    for page in paginator.paginate(IdentityStoreId=identity_store_id):
        groups.extend(page["Groups"])
        time.sleep(SLEEP_DELAY)

    group_info = {}
    scim_data = {}

    for g in groups:
        sanitized_name = sanitize_name(g["DisplayName"])
        g["ImportId"] = f"{identity_store_id}/{g['GroupId']}"
        g["ImportTo"] = f"aws_identitystore_group.{sanitized_name}"
        g["ResourceName"] = sanitized_name
        g["OriginalName"] = g["DisplayName"]  # Preserve original for map keys
        g["SCIM"] = any("Id" in ext_id for ext_id in g.get("ExternalIds", []))

        group_info[g["GroupId"]] = {"ResourceName": sanitized_name, "OriginalName": g["DisplayName"]}
        scim_data[g["GroupId"]] = g["SCIM"]

    dump_resources_individually(
        resources=groups,
        base_dir=JSON_DIR,
        resource_type="groups",
        key_name="ResourceName",
        verbosity=verbosity
    )

    if verbosity >= 1:
        print(f"[FETCH] Done fetching groups. Count: {len(groups)}")

    return group_info, scim_data


# ------------------------------------------------------------------------
# Identity Store - Group Memberships
# ------------------------------------------------------------------------
def fetch_group_memberships(identity_store, identity_store_id, groups_map, users_map, scim_data, verbosity=0):
    if verbosity >= 1:
        print("[FETCH] Fetching group memberships...")

    all_memberships = []
    for group_id, group_info in groups_map.items():
        mem_paginator = identity_store.get_paginator("list_group_memberships")
        for page in mem_paginator.paginate(IdentityStoreId=identity_store_id, GroupId=group_id):
            all_memberships.extend(page["GroupMemberships"])
            time.sleep(SLEEP_DELAY)

    for membership in all_memberships:
        membership_id = membership["MembershipId"]
        group_id = membership["GroupId"]
        member_info = membership["MemberId"]

        group_info = groups_map.get(group_id, {"ResourceName": "UnknownGroup", "OriginalName": "UnknownGroup"})
        group_res_name = group_info["ResourceName"]
        group_orig_name = group_info["OriginalName"]
        
        user_id = member_info.get("UserId")
        user_info = users_map.get(user_id, {"ResourceName": "UnknownUser", "OriginalName": "UnknownUser"})
        user_res_name = user_info["ResourceName"]
        user_orig_name = user_info["OriginalName"]

        # Combined sanitized name for ResourceName/filename
        combined_res_name = f"{group_res_name}___{user_res_name}"
        sanitized_name = sanitize_name(combined_res_name)

        # ImportTo uses original names to match for_each key in Terraform
        import_to_key = f"{group_orig_name}___{user_orig_name}"

        membership["ImportId"] = f"{identity_store_id}/{membership_id}"
        membership["ImportTo"] = f'aws_identitystore_group_membership.controller["{import_to_key}"]'
        membership["ResourceName"] = sanitized_name
        membership["GroupOriginalName"] = group_orig_name
        membership["UserOriginalName"] = user_orig_name
        membership["SCIM"] = scim_data.get(group_id, False)

    dump_resources_individually(
        resources=all_memberships,
        base_dir=JSON_DIR,
        resource_type="group_memberships",
        key_name="ResourceName",
        verbosity=verbosity
    )

    if verbosity >= 1:
        print(f"[FETCH] Done fetching group memberships. Count: {len(all_memberships)}")


# ------------------------------------------------------------------------
# AWS Organization - Accounts
# ------------------------------------------------------------------------
def fetch_accounts(org, verbosity=0):
    if verbosity >= 1:
        print("[FETCH] Fetching active AWS accounts...")

    accounts = []
    acct_paginator = org.get_paginator("list_accounts")
    for page in acct_paginator.paginate():
        for acct in page["Accounts"]:
            if acct["Status"] == "ACTIVE":
                accounts.append(acct)
        time.sleep(SLEEP_DELAY)

    for acct in accounts:
        original_name = acct.get("Name", "UnknownAccount")
        acct["OriginalName"] = original_name
        acct["ResourceName"] = sanitize_name(original_name)

    dump_resources_individually(
        resources=accounts,
        base_dir=JSON_DIR,
        resource_type="accounts",
        key_name="ResourceName",
        verbosity=verbosity
    )

    if verbosity >= 1:
        print(f"[FETCH] Done fetching accounts. Count: {len(accounts)}")

    return {acct["Id"]: {"ResourceName": acct["ResourceName"], "OriginalName": acct["OriginalName"]} for acct in accounts}


# ------------------------------------------------------------------------
# AWS Organization - Organizational Units
# ------------------------------------------------------------------------
def fetch_organizational_units(org, verbosity=0):
    """
    Fetches all organizational units (OUs) by traversing the OU tree from the root.
    Returns a flat list including the root and all OUs with their Name, Id, and full path.
    """
    if verbosity >= 1:
        print("[FETCH] Fetching organizational units...")

    # Get the root ID and name
    roots_resp = org.list_roots()
    root = roots_resp["Roots"][0]
    root_id = root["Id"]
    root_name = root.get("Name", "Root")

    all_ous = []
    
    # Add the root itself first
    root_entry = {
        "Id": root_id,
        "Name": root_name,
        "Arn": root.get("Arn", ""),
        "Depth": 0,
        "ParentPath": "",
        "FullPath": root_name,
        "OriginalName": root_name,
        "ResourceName": sanitize_name(root_name)
    }
    all_ous.append(root_entry)
    
    def fetch_children_ous(parent_id, parent_path="", depth=1):
        """Recursively fetch OUs under a parent."""
        paginator = org.get_paginator("list_organizational_units_for_parent")
        for page in paginator.paginate(ParentId=parent_id):
            for ou in page["OrganizationalUnits"]:
                ou_name = ou.get("Name", "UnknownOU")
                ou["Depth"] = depth
                ou["ParentPath"] = parent_path
                ou["FullPath"] = f"{parent_path}/{ou_name}"
                all_ous.append(ou)
                time.sleep(SLEEP_DELAY)
                # Recursively fetch children (up to 5 levels deep)
                if depth < 5:
                    fetch_children_ous(ou["Id"], ou["FullPath"], depth + 1)

    # Start from root
    fetch_children_ous(root_id, root_name)

    # Add metadata for each OU (skip root which already has it)
    for ou in all_ous[1:]:
        original_name = ou.get("Name", "UnknownOU")
        ou["OriginalName"] = original_name
        ou["ResourceName"] = sanitize_name(original_name)

    dump_resources_individually(
        resources=all_ous,
        base_dir=JSON_DIR,
        resource_type="organizational_units",
        key_name="ResourceName",
        verbosity=verbosity
    )

    if verbosity >= 1:
        print(f"[FETCH] Done fetching organizational units. Count: {len(all_ous)}")

    return all_ous


# ------------------------------------------------------------------------
# SSO Admin - Permission Sets
# ------------------------------------------------------------------------
def fetch_permission_sets(sso_admin, instance_arn, verbosity=0):
    if verbosity >= 1:
        print("[FETCH] Fetching permission sets...")

    # 1) List all permission set ARNs
    permission_set_arns = []
    next_token = None
    while True:
        params = {"InstanceArn": instance_arn}
        if next_token:
            params["NextToken"] = next_token
        resp = sso_admin.list_permission_sets(**params)
        permission_set_arns.extend(resp["PermissionSets"])

        next_token = resp.get("NextToken")
        time.sleep(SLEEP_DELAY)  # after each call
        if not next_token:
            break

    # 2) Describe each permission set in detail
    permission_sets = []
    for ps_arn in permission_set_arns:
        detail_resp = sso_admin.describe_permission_set(
            InstanceArn=instance_arn,
            PermissionSetArn=ps_arn
        )
        permission_sets.append(detail_resp["PermissionSet"])
        time.sleep(SLEEP_DELAY)

    # 3) Setup Terraform fields
    for ps in permission_sets:
        raw_name = ps.get("Name") or "UnnamedPermissionSet"
        sanitized_name = sanitize_name(raw_name)

        ps["ResourceName"] = sanitized_name
        ps["ImportId"] = f"{ps['PermissionSetArn']},{instance_arn}"
        ps["ImportTo"] = f"aws_ssoadmin_permission_set.{sanitized_name}"

    # 4) Dump them
    dump_resources_individually(
        resources=permission_sets,
        base_dir=JSON_DIR,
        resource_type="permission_sets",
        key_name="ResourceName",
        verbosity=verbosity
    )

    if verbosity >= 1:
        print(f"[FETCH] Done fetching permission sets. Count: {len(permission_sets)}")

    # 5) Fetch inline/managed/customer-managed policies
    fetch_inline_policies(sso_admin, instance_arn, permission_sets, verbosity)
    fetch_managed_policy_attachments(sso_admin, instance_arn, permission_sets, verbosity)
    fetch_customer_managed_policy_attachments(sso_admin, instance_arn, permission_sets, verbosity)
    fetch_permission_set_tags(sso_admin, instance_arn, permission_sets, verbosity)

    return {ps["PermissionSetArn"]: ps["ResourceName"] for ps in permission_sets}


def fetch_inline_policies(sso_admin, instance_arn, permission_sets, verbosity=0):
    inline_dir = Path(JSON_DIR) / "permission_sets" / "inline_policies"
    inline_dir.mkdir(parents=True, exist_ok=True)

    for ps in permission_sets:
        ps_arn = ps["PermissionSetArn"]
        ps_name = ps["ResourceName"]

        try:
            resp = sso_admin.get_inline_policy_for_permission_set(
                InstanceArn=instance_arn,
                PermissionSetArn=ps_arn
            )
            time.sleep(SLEEP_DELAY)

            policy = resp.get("InlinePolicy")
            if policy:
                policy_data = json.loads(policy)
                policy_filepath = inline_dir / f"{ps_name}.json"
                with open(policy_filepath, "w", encoding="utf-8") as f:
                    json.dump(policy_data, f, indent=2, ensure_ascii=False)
                ps["HasInlinePolicy"] = True

                if verbosity >= 2:
                    print(f"[VERBOSE-2] Writing inline policy: {policy_filepath}")
            else:
                ps["HasInlinePolicy"] = False

        except sso_admin.exceptions.ResourceNotFoundException:
            ps["HasInlinePolicy"] = False
            if verbosity >= 1:
                print(f"[FETCH] No inline policy found for permission set: {ps_name}")

    if verbosity >= 1:
        print("[FETCH] Done fetching inline policies.")


def fetch_managed_policy_attachments(sso_admin, instance_arn, permission_sets, verbosity=0):
    for ps in permission_sets:
        ps_arn = ps["PermissionSetArn"]
        resp = sso_admin.list_managed_policies_in_permission_set(
            InstanceArn=instance_arn,
            PermissionSetArn=ps_arn
        )
        time.sleep(SLEEP_DELAY)

        attached_policies = [
            {
                "Name": p["Name"],
                "Arn": p["Arn"]
            }
            for p in resp["AttachedManagedPolicies"]
        ]
        ps["ManagedPolicies"] = attached_policies

    # Update the JSON files
    for ps in permission_sets:
        ps_name = ps["ResourceName"]
        filepath = Path(JSON_DIR) / "permission_sets" / f"{ps_name}.json"
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(ps, f, indent=2, ensure_ascii=False, default=str)

    if verbosity >= 1:
        print("[FETCH] Done fetching managed policy attachments.")


def fetch_customer_managed_policy_attachments(sso_admin, instance_arn, permission_sets, verbosity=0):
    for ps in permission_sets:
        ps_arn = ps["PermissionSetArn"]
        resp = sso_admin.list_customer_managed_policy_references_in_permission_set(
            InstanceArn=instance_arn,
            PermissionSetArn=ps_arn
        )
        time.sleep(SLEEP_DELAY)

        cust_managed_names = [p["Name"] for p in resp["CustomerManagedPolicyReferences"]]
        ps["CustomerManagedPolicies"] = cust_managed_names

    # Update JSON files
    for ps in permission_sets:
        ps_name = ps["ResourceName"]
        filepath = Path(JSON_DIR) / "permission_sets" / f"{ps_name}.json"
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(ps, f, indent=2, ensure_ascii=False, default=str)

    if verbosity >= 1:
        print("[FETCH] Done fetching customer managed policy attachments.")


def fetch_permission_set_tags(sso_admin, instance_arn, permission_sets, verbosity=0):
    """
    Fetch tags for each permission set and update the corresponding JSON file in
    output/json/permission_sets/*.json.
    """
    for ps in permission_sets:
        ps_arn = ps["PermissionSetArn"]

        # Call SSO Admin to list tags
        resp = sso_admin.list_tags_for_resource(
            InstanceArn=instance_arn,
            ResourceArn=ps_arn
        )
        # Store the list of tags
        ps["Tags"] = resp.get("Tags", [])

        if verbosity >= 2:
            ps_name = ps["ResourceName"]
            print(f"[VERBOSE-2] Fetched {len(ps['Tags'])} tags for permission set: {ps_name}")

    # Rewrite the updated JSON files with tags
    for ps in permission_sets:
        ps_name = ps["ResourceName"]
        filepath = Path(JSON_DIR) / "permission_sets" / f"{ps_name}.json"

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(ps, f, indent=2, ensure_ascii=False, default=str)

    if verbosity >= 1:
        print("[FETCH] Done fetching permission set tags.")


# ------------------------------------------------------------------------
# SSO Admin - Account Assignments
# ------------------------------------------------------------------------
def fetch_account_assignments(
    sso_admin,
    instance_arn,
    accounts_map,
    users_map,
    groups_map,
    permission_sets_map,
    verbosity=0
):
    """
    Fetch account assignments for each permission set only on the accounts
    where that permission set is actually provisioned. We do this by calling
    list_accounts_for_provisioned_permission_set to get a list of relevant accounts,
    then calling list_account_assignments for those accounts.
    """
    if verbosity >= 1:
        print("[FETCH] Fetching account assignments...")

    all_assignments = []

    # 1) Loop over each permission set
    for ps_arn, ps_res_name in permission_sets_map.items():
        # If verbosity >= 2, show which permission set we're working on
        if verbosity >= 2:
            print(f"[VERBOSE-2] Checking provisioned accounts for permission set '{ps_res_name}'.")

        # 2) Get all accounts that have this permission set provisioned
        provisioned_accounts = []
        next_token = None
        while True:
            list_accts_params = {
                "InstanceArn": instance_arn,
                "PermissionSetArn": ps_arn,
            }
            if next_token:
                list_accts_params["NextToken"] = next_token

            accts_resp = sso_admin.list_accounts_for_provisioned_permission_set(**list_accts_params)
            provisioned_accounts.extend(accts_resp["AccountIds"])
            next_token = accts_resp.get("NextToken")
            if not next_token:
                break

        if verbosity >= 2 and provisioned_accounts:
            print(f"[VERBOSE-2] Found {len(provisioned_accounts)} accounts with '{ps_res_name}' provisioned.")

        # 3) For each provisioned account, call list_account_assignments
        for account_id in provisioned_accounts:
            account_info = accounts_map.get(account_id, {"ResourceName": f"UnknownAccount_{account_id}", "OriginalName": f"UnknownAccount_{account_id}"})
            account_res_name = account_info["ResourceName"]
            account_orig_name = account_info["OriginalName"]

            if verbosity >= 2:
                print(f"[VERBOSE-2] Working on account '{account_orig_name}' (ID: {account_id}) "
                      f"with permission set '{ps_res_name}' (ARN: {ps_arn}).")

            next_token = None
            while True:
                params = {
                    "InstanceArn": instance_arn,
                    "AccountId": account_id,
                    "PermissionSetArn": ps_arn,
                }
                if next_token:
                    params["NextToken"] = next_token

                resp = sso_admin.list_account_assignments(**params)

                for assignment in resp["AccountAssignments"]:
                    principal_id = assignment["PrincipalId"]
                    principal_type = assignment["PrincipalType"]  # "USER" or "GROUP"
                    target_type = "AWS_ACCOUNT"

                    # Map the userId or groupId to names (both sanitized and original)
                    if principal_type == "USER":
                        user_info = users_map.get(principal_id, {"ResourceName": f"UnknownUser_{principal_id}", "OriginalName": f"UnknownUser_{principal_id}"})
                        principal_res_name = user_info["ResourceName"]
                        principal_orig_name = user_info["OriginalName"]
                    elif principal_type == "GROUP":
                        group_info = groups_map.get(principal_id, {"ResourceName": f"UnknownGroup_{principal_id}", "OriginalName": f"UnknownGroup_{principal_id}"})
                        principal_res_name = group_info["ResourceName"]
                        principal_orig_name = group_info["OriginalName"]
                    else:
                        principal_res_name = f"UnknownPrincipal_{principal_id}"
                        principal_orig_name = f"UnknownPrincipal_{principal_id}"

                    assignment["PrincipalName"] = principal_orig_name  # Use original name for map keys
                    assignment["PrincipalResourceName"] = principal_res_name  # Keep sanitized for resource refs
                    assignment["PermissionSetName"] = ps_res_name
                    assignment["AccountName"] = account_orig_name  # Use original name for map keys

                    # Build a combined name for ResourceName/filename (sanitized)
                    combined_name = (
                        f"{account_res_name}___"
                        f"{ps_res_name}___"
                        f"{principal_type}___"
                        f"{principal_res_name}"
                    )
                    sanitized_name = sanitize_name(combined_name)
                    assignment["ResourceName"] = sanitized_name

                    # Build the import ID: "principal_id,principal_type,account_id,AWS_ACCOUNT,ps_arn,instance_arn"
                    import_id = (
                        f"{principal_id},{principal_type},{account_id},"
                        f"{target_type},{ps_arn},{instance_arn}"
                    )
                    assignment["ImportId"] = import_id

                    # ImportTo uses original names to match for_each key in Terraform
                    import_to_key = f"{account_orig_name}___{ps_res_name}___{principal_type}___{principal_orig_name}"
                    assignment["ImportTo"] = f'aws_ssoadmin_account_assignment.controller["{import_to_key}"]'

                    all_assignments.append(assignment)

                next_token = resp.get("NextToken")
                if not next_token:
                    break

    # 4) Write all assignments to individual JSON files
    dump_resources_individually(
        resources=all_assignments,
        base_dir=JSON_DIR,
        resource_type="account_assignments",
        key_name="ResourceName",
        verbosity=verbosity
    )

    if verbosity >= 1:
        print(f"[FETCH] Done fetching account assignments. Count: {len(all_assignments)}")


# ------------------------------------------------------------------------
# IAM - Managed Policies
# ------------------------------------------------------------------------
def fetch_managed_policies(iam, verbosity=0):
    if verbosity >= 1:
        print("[FETCH] Fetching IAM managed policies...")

    managed_policies = []
    paginator = iam.get_paginator("list_policies")
    for page in paginator.paginate(Scope="AWS"):
        managed_policies.extend(page["Policies"])
        time.sleep(SLEEP_DELAY)

    # Create directories
    metadata_dir = Path(JSON_DIR) / "managed_policies"
    policies_dir = metadata_dir / "policies"
    metadata_dir.mkdir(parents=True, exist_ok=True)
    policies_dir.mkdir(parents=True, exist_ok=True)

    for policy in managed_policies:
        policy_arn = policy["Arn"]
        policy_name = policy["PolicyName"]

        # Write metadata
        meta_path = metadata_dir / f"{policy_name}.json"
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(policy, f, indent=2, ensure_ascii=False, default=str)

        # Fetch default policy version
        versions_resp = iam.list_policy_versions(PolicyArn=policy_arn)
        time.sleep(SLEEP_DELAY)
        versions = versions_resp["Versions"]

        default_version = next(v for v in versions if v["IsDefaultVersion"])
        version_id = default_version["VersionId"]

        policy_version_resp = iam.get_policy_version(
            PolicyArn=policy_arn,
            VersionId=version_id
        )
        time.sleep(SLEEP_DELAY)
        policy_version = policy_version_resp["PolicyVersion"]["Document"]

        # Write policy doc
        policy_file = policies_dir / f"{policy_name}.json"
        with open(policy_file, "w", encoding="utf-8") as f:
            json.dump(policy_version, f, indent=2, ensure_ascii=False, default=str)

    if verbosity >= 1:
        print(f"[FETCH] Done fetching IAM managed policies. Count: {len(managed_policies)}")


# ------------------------------------------------------------------------
# DynamoDB Tables - Approvers and Eligibility
# ------------------------------------------------------------------------
def fetch_dynamodb_tables(verbosity=0):
    """
    Fetches DynamoDB tables with names matching Approvers-*-main and Eligibility-*-main,
    and having the tags project=iam-identity-center-team and environment=prod.
    The table metadata is stored as JSON files in the "dynamodb_tables" folder,
    and each table item is written to its own JSON file in the appropriate subdirectory
    under "dynamodb_items" (either "approvers" or "eligibility").

    For each item (policy) we generate a new field "ResourceName", which is composed of
    the item's type, three underscores, and the sanitized name (based on the item's "name").
    We also store the sanitized name in the "SanitizedName" field.
    The file name is then set to ResourceName.json.
    """
    if verbosity >= 1:
        print("[FETCH] Fetching DynamoDB tables for IAM Identity Center team...")

    dynamodb_client = boto3.client("dynamodb")

    # Retrieve all table names (with pagination)
    table_names = []
    last_evaluated = None
    while True:
        if last_evaluated:
            response = dynamodb_client.list_tables(ExclusiveStartTableName=last_evaluated)
        else:
            response = dynamodb_client.list_tables()
        table_names.extend(response.get("TableNames", []))
        last_evaluated = response.get("LastEvaluatedTableName")
        if not last_evaluated:
            break

    # Define the name patterns
    approvers_pattern = re.compile(r"^Approvers-.*-main$")
    eligibility_pattern = re.compile(r"^Eligibility-.*-main$")

    # Create (or ensure) the team folder subdirectories for metadata and items exist
    metadata_dir = Path(JSON_DIR) / "team" / "dynamodb_tables"
    items_dir = Path(JSON_DIR) / "team" / "dynamodb_items"
    metadata_dir.mkdir(parents=True, exist_ok=True)
    items_dir.mkdir(parents=True, exist_ok=True)

    # Import the deserializer
    from boto3.dynamodb.types import TypeDeserializer  # type: ignore
    deserializer = TypeDeserializer()

    for table_name in table_names:
        if approvers_pattern.match(table_name) or eligibility_pattern.match(table_name):
            try:
                desc = dynamodb_client.describe_table(TableName=table_name)
            except Exception as e:
                if verbosity >= 1:
                    print(f"[FETCH] Error describing table {table_name}: {e}")
                continue

            table_arn = desc["Table"]["TableArn"]

            try:
                tags_resp = dynamodb_client.list_tags_of_resource(ResourceArn=table_arn)
                tags = tags_resp.get("Tags", [])
            except Exception as e:
                if verbosity >= 1:
                    print(f"[FETCH] Error getting tags for table {table_name}: {e}")
                tags = []

            has_project_tag = any(t.get("Key") == "project" and t.get("Value") == "iam-identity-center-team" for t in tags)
            has_env_tag = any(t.get("Key") == "environment" and t.get("Value") == "prod" for t in tags)

            if not (has_project_tag and has_env_tag):
                if verbosity >= 2:
                    print(f"[FETCH] Table {table_name} does not have required tags.")
                continue

            if verbosity >= 1:
                print(f"[FETCH] Found matching DynamoDB table: {table_name}")

            # Write the table metadata to the metadata directory
            sanitized_table_name = sanitize_name(table_name)
            metadata_filepath = metadata_dir / f"{sanitized_table_name}.json"
            metadata = {
                "Table": desc["Table"],
                "Tags": tags
            }
            with open(metadata_filepath, "w", encoding="utf-8") as f:
                json.dump(metadata, f, indent=2, ensure_ascii=False, default=str)

            if verbosity >= 1:
                print(f"[FETCH] Wrote metadata for table {table_name} to {metadata_filepath}")

            # Scan the table to retrieve all items (with pagination)
            items = []
            scan_kwargs = {"TableName": table_name}
            while True:
                try:
                    scan_resp = dynamodb_client.scan(**scan_kwargs)
                except Exception as e:
                    if verbosity >= 1:
                        print(f"[FETCH] Error scanning table {table_name}: {e}")
                    break
                items.extend(scan_resp.get("Items", []))
                if "LastEvaluatedKey" in scan_resp:
                    scan_kwargs["ExclusiveStartKey"] = scan_resp["LastEvaluatedKey"]
                else:
                    break

            # Deserialize the DynamoDB items into plain Python types
            converted_items = []
            for item in items:
                converted_item = {k: deserializer.deserialize(v) for k, v in item.items()}
                converted_items.append(converted_item)

            # Determine the subdirectory based on the table type
            if approvers_pattern.match(table_name):
                subdir = items_dir / "approvers"
            elif eligibility_pattern.match(table_name):
                subdir = items_dir / "eligibility"
            else:
                subdir = items_dir  # fallback in case of an unexpected match

            subdir.mkdir(parents=True, exist_ok=True)

            # Write each item to its own file with additional ResourceName and SanitizedName fields
            for item in converted_items:
                # Generate the sanitized name from the item's "name" field
                sanitized_name = sanitize_name(item.get("name", "unknown"))
                # Create the ResourceName using the item's "type" field and the sanitized name
                resource_name = f"{item.get('type', 'unknown')}___{sanitized_name}"
                # Add these fields to the item
                item["ResourceName"] = resource_name
                item["SanitizedName"] = sanitized_name

                # Use the ResourceName for the filename
                item_filepath = subdir / f"{resource_name}.json"
                with open(item_filepath, "w", encoding="utf-8") as f:
                    json.dump(item, f, indent=2, ensure_ascii=False, default=str)

            if verbosity >= 1:
                print(f"[FETCH] Wrote {len(converted_items)} items from table {table_name} to {subdir}")


# ------------------------------------------------------------------------
# TEAM Application
# ------------------------------------------------------------------------
def fetch_team_application(sso_admin, instance_arn, identity_store, identity_store_id, verbosity=0):
    """
    Fetches the TEAM IDC APP application from Identity Center and saves it to JSON.
    Also fetches all current application assignments (users and groups).
    """
    if verbosity >= 1:
        print("[FETCH] Fetching TEAM IDC APP application...")
    
    try:
        response = sso_admin.list_applications(InstanceArn=instance_arn)
        time.sleep(SLEEP_DELAY)
        
        for app in response.get('Applications', []):
            if app.get('Name') == 'TEAM IDC APP':
                team_dir = Path(JSON_DIR) / "team"
                team_dir.mkdir(parents=True, exist_ok=True)
                
                app_file = team_dir / "team_application.json"
                with open(app_file, 'w', encoding='utf-8') as f:
                    json.dump(app, f, indent=2, ensure_ascii=False, default=str)
                
                if verbosity >= 1:
                    print(f"[FETCH] Found TEAM IDC APP: {app['ApplicationArn']}")
                
                # Fetch application assignments
                fetch_team_application_assignments(sso_admin, app['ApplicationArn'], team_dir, identity_store, identity_store_id, verbosity)
                return
        
        if verbosity >= 1:
            print("[FETCH] TEAM IDC APP not found")
    except Exception as e:
        if verbosity >= 1:
            print(f"[FETCH] Error fetching TEAM application: {e}")


def fetch_team_application_assignments(sso_admin, application_arn, team_dir, identity_store, identity_store_id, verbosity=0):
    """
    Fetches all assignments for the TEAM application and resolves principal IDs to names.
    Saves both the raw assignments and resolved names to JSON.
    """
    if verbosity >= 1:
        print("[FETCH] Fetching TEAM application assignments...")
    
    try:
        assignments = []
        paginator = sso_admin.get_paginator('list_application_assignments')
        
        for page in paginator.paginate(ApplicationArn=application_arn):
            assignments.extend(page.get('ApplicationAssignments', []))
            time.sleep(SLEEP_DELAY)
        
        # Resolve principal IDs to names and build assignment data
        users = []
        groups = []
        assignment_details = []
        
        for assignment in assignments:
            principal_id = assignment.get('PrincipalId')
            principal_type = assignment.get('PrincipalType')
            
            assignment_detail = {
                'PrincipalId': principal_id,
                'PrincipalType': principal_type,
                'ApplicationArn': application_arn
            }
            
            if principal_type == 'USER':
                try:
                    user_resp = identity_store.describe_user(
                        IdentityStoreId=identity_store_id,
                        UserId=principal_id
                    )
                    username = user_resp.get('UserName')
                    if username:
                        users.append(username)
                        assignment_detail['PrincipalName'] = username
                    time.sleep(SLEEP_DELAY)
                except Exception as e:
                    if verbosity >= 2:
                        print(f"[VERBOSE-2] Error looking up user {principal_id}: {e}")
                        
            elif principal_type == 'GROUP':
                try:
                    group_resp = identity_store.describe_group(
                        IdentityStoreId=identity_store_id,
                        GroupId=principal_id
                    )
                    group_name = group_resp.get('DisplayName')
                    if group_name:
                        groups.append(group_name)
                        assignment_detail['PrincipalName'] = group_name
                    time.sleep(SLEEP_DELAY)
                except Exception as e:
                    if verbosity >= 2:
                        print(f"[VERBOSE-2] Error looking up group {principal_id}: {e}")
            
            assignment_details.append(assignment_detail)
        
        # Save resolved names and full assignment details
        # Sort assignment_details by PrincipalName for consistent ordering
        assignment_details.sort(key=lambda x: (x.get('PrincipalType', ''), x.get('PrincipalName', '')))
        
        resolved_assignments = {
            'users': sorted(users),
            'groups': sorted(groups),
            'assignments': assignment_details
        }
        
        assignments_file = team_dir / "team_application_assignments.json"
        with open(assignments_file, 'w', encoding='utf-8') as f:
            json.dump(resolved_assignments, f, indent=2, ensure_ascii=False, default=str)
        
        if verbosity >= 1:
            print(f"[FETCH] Found {len(users)} users and {len(groups)} groups assigned to TEAM app")
            
    except Exception as e:
        if verbosity >= 1:
            print(f"[FETCH] Error fetching TEAM application assignments: {e}")



# ------------------------------------------------------------------------
# Main Fetch
# ------------------------------------------------------------------------
def fetch_data(verbosity=0, retain_managed_policies=False, output=".", config="config.yaml", overrides=None):
    """
    Fetch AWS Identity Center (SSO) resources and store them as JSON in 'output/json',
    with small sleeps inserted to reduce the chance of throttling.
    
    Args:
        verbosity: 0=quiet, 1=normal, 2=verbose
        retain_managed_policies: Skip managed policy refresh
        output: Base output directory for JSON files
        config: Path to config.yaml file (default: "config.yaml")
        overrides: Dictionary of CLI parameter overrides
    """
    global JSON_DIR
    JSON_DIR = os.path.join(output, "json")

    if not retain_managed_policies:
        if os.path.exists(JSON_DIR):
            print(f"[FETCH] Removing existing folder: {JSON_DIR}")
            shutil.rmtree(JSON_DIR)
        os.makedirs(JSON_DIR, exist_ok=True)

    if verbosity == 0:
        print("[FETCH] Gathering AWS Identity Center resources...")
    elif verbosity >= 1:
        print("[FETCH] Starting fetch of AWS Identity Center resources...")

    sso_admin = boto3.client("sso-admin")
    identity_store = boto3.client("identitystore")
    org = boto3.client("organizations")
    iam = boto3.client("iam")

    instances_resp = sso_admin.list_instances()
    time.sleep(SLEEP_DELAY)
    if not instances_resp["Instances"]:
        print("No SSO instances found!")
        return

    instance = instances_resp["Instances"][0]
    instance_arn = instance["InstanceArn"]
    identity_store_id = instance["IdentityStoreId"]

    fetch_sso_admin_instance(sso_admin, instance_arn, verbosity)

    users_map = fetch_users(identity_store, identity_store_id, verbosity)
    groups_map, scim_data = fetch_groups(identity_store, identity_store_id, verbosity)
    fetch_group_memberships(identity_store, identity_store_id, groups_map, users_map, scim_data, verbosity)
    accounts_map = fetch_accounts(org, verbosity)
    fetch_organizational_units(org, verbosity)
    permission_sets_map = fetch_permission_sets(sso_admin, instance_arn, verbosity)
    fetch_account_assignments(
        sso_admin, instance_arn,
        accounts_map, users_map, groups_map,
        permission_sets_map, verbosity
    )
    
    # Only fetch TEAM data if enable_team is True
    cfg = get_config(config, overrides)
    if cfg.is_team_enabled():
        fetch_dynamodb_tables(verbosity)
        fetch_team_application(sso_admin, instance_arn, identity_store, identity_store_id, verbosity)
    elif verbosity >= 1:
        print("[FETCH] Skipping TEAM data (enable_team is False)")

    if not retain_managed_policies:
        fetch_managed_policies(iam, verbosity)
    else:
        if verbosity >= 1:
            print("[FETCH] Skipping managed policies due to retain-managed-policies flag.")

    if verbosity == 0:
        print("[FETCH] Done.")
    elif verbosity == 1:
        print("[FETCH] All resources fetched.")
    else:
        print("[FETCH] All resources fetched with detailed output.")
