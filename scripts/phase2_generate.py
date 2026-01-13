import os
import json
import requests
import shutil
import jinja2
import re
from dataclasses import dataclass, field
from pathlib import Path
from packaging import version
from typing import Optional, Dict, Any, List
from config_loader import get_config, reload_config, Config

# =============================================================================
# Constants
# =============================================================================
SCRIPT_DIR = Path(__file__).parent
REPO_ROOT = SCRIPT_DIR.parent
TEMPLATE_DIR = str(REPO_ROOT / "templates")

SSOADMIN_SUBFOLDERS = [
    "account_assignments",
    "identity_store",
    "managed_policies",
    "permission_sets",
    "team",
]

SSOADMIN_INSTANCES_TEMPLATE_NAME = "aws_ssoadmin_instances.tf.jinja"
PROVIDERS_TEMPLATE_NAME = "providers.tf.jinja"


# =============================================================================
# Generator Context
# =============================================================================
@dataclass
class GeneratorContext:
    """
    Holds all configuration state for the Terraform generator.
    This context object is passed through all generator functions.
    """
    output_dir: str = "."
    config_path: str = "config.yaml"
    state_mode: str = "single"
    platform: str = "local"
    verbosity: int = 0
    retain_managed_policies: bool = False
    overrides: Dict[str, Any] = field(default_factory=dict)
    _config: Optional[Config] = field(default=None, repr=False)

    @property
    def json_dir(self) -> str:
        """Path to JSON data directory."""
        return str(Path(self.output_dir) / "json")
    
    @property
    def terraform_dir(self) -> str:
        """Path to Terraform output directory."""
        return self.output_dir
    
    @property
    def config(self) -> Config:
        """Get the Config instance, creating it if needed."""
        if self._config is None:
            merged_overrides = {
                **self.overrides,
                'state_mode': self.state_mode,
                'platform': self.platform
            }
            self._config = reload_config(self.config_path, merged_overrides)
        return self._config
    
    def is_single_state(self) -> bool:
        return self.state_mode == "single"
    
    def is_multi_state(self) -> bool:
        return self.state_mode == "multi"
    
    def is_tfc(self) -> bool:
        return self.platform == "tfc"
    
    def is_local(self) -> bool:
        return self.platform == "local"
    
    def log(self, message: str, level: int = 1):
        """Print message if verbosity is at or above level."""
        if self.verbosity >= level:
            print(message)
    
    def get_active_subfolders(self) -> List[str]:
        """Get list of active subfolders based on config."""
        if self.config.is_team_enabled():
            return SSOADMIN_SUBFOLDERS
        return [f for f in SSOADMIN_SUBFOLDERS if f != "team"]


# =============================================================================
# Utility Functions
# =============================================================================
def get_latest_aws_provider_version():
    """Fetches the latest stable AWS provider version from the Terraform Registry."""
    url = "https://registry.terraform.io/v1/providers/hashicorp/aws/versions"
    response = requests.get(url)
    response.raise_for_status()

    data = response.json()
    all_versions = [v["version"] for v in data["versions"]]

    stable_versions = []
    for ver_str in all_versions:
        parsed = version.parse(ver_str)
        if not (parsed.is_prerelease or parsed.is_devrelease):
            stable_versions.append(parsed)

    if not stable_versions:
        raise RuntimeError("No stable AWS provider versions found on the registry.")

    stable_versions.sort()
    return str(stable_versions[-1])


def get_latest_tfe_provider_version():
    """Fetches the latest stable TFE provider version from the Terraform Registry."""
    url = "https://registry.terraform.io/v1/providers/hashicorp/tfe/versions"
    response = requests.get(url)
    response.raise_for_status()

    data = response.json()
    all_versions = [v["version"] for v in data["versions"]]

    stable_versions = []
    for ver_str in all_versions:
        parsed = version.parse(ver_str)
        if not (parsed.is_prerelease or parsed.is_devrelease):
            stable_versions.append(parsed)

    if not stable_versions:
        raise RuntimeError("No stable TFE provider versions found on the registry.")

    stable_versions.sort()
    return str(stable_versions[-1])


def read_sso_admin_region(ctx: GeneratorContext) -> str:
    """Reads the 'Region' field from the first JSON file in output/json/sso_admin."""
    sso_admin_dir = Path(ctx.json_dir) / "sso_admin"
    if not sso_admin_dir.is_dir():
        raise FileNotFoundError(
            "[ERROR] sso_admin directory not found. Did you run fetch first?"
        )

    files = list(sso_admin_dir.glob("*.json"))
    if not files:
        raise FileNotFoundError("[ERROR] No JSON files found in sso_admin directory.")

    with open(files[0], "r", encoding="utf-8") as f:
        data = json.load(f)

    region = data.get("Region")
    if not region:
        raise ValueError("[ERROR] 'Region' field not found in sso_admin JSON.")
    return region


def get_template_variant(source_dir: Path, base_name: str, state_mode: str, platform: str) -> tuple:
    """
    Determines which template variant to use based on mode.
    
    Template naming convention:
    - base.tf.jinja: Default template (used for multi-state TFC)
    - base_local.tf.jinja: Single-state variant (uses var.* inputs)
    - base_remote_state.tf.jinja: Multi-state local variant (uses terraform_remote_state)
    """
    base_without_ext = base_name.replace(".tf.jinja", "")
    
    # Multi-state local mode: prefer _remote_state variant
    if state_mode == "multi" and platform == "local":
        remote_state_variant = f"{base_without_ext}_remote_state.tf.jinja"
        if (source_dir / remote_state_variant).exists():
            return (remote_state_variant, f"{base_without_ext}.tf")
    
    # Single-state mode: prefer _local variant
    if state_mode == "single":
        local_variant = f"{base_without_ext}_local.tf.jinja"
        if (source_dir / local_variant).exists():
            return (local_variant, f"{base_without_ext}.tf")
    
    # Multi-state TFC mode: use base template (has tfe_outputs)
    return (base_name, f"{base_without_ext}.tf")


def copy_templates(source_dir: Path, target_dir: Path, ctx: GeneratorContext):
    """
    Renders all *.tf.jinja files from source_dir to target_dir.
    Templates are rendered with configuration variables from config.yaml.
    """
    ctx.log(f"[GENERATE] Rendering template files from {source_dir} to {target_dir}.")

    target_dir.mkdir(parents=True, exist_ok=True)

    config = ctx.config
    
    # Prepare template context with config variables
    template_context = {
        'tfe_organization': config.get_tfe_organization(),
        'workspace_identity_store': config.get_workspace_name('identity-store') if ctx.is_multi_state() else '',
        'workspace_permission_sets': config.get_workspace_name('permission-sets') if ctx.is_multi_state() else '',
        'workspace_account_assignments': config.get_workspace_name('account-assignments') if ctx.is_multi_state() else '',
        'workspace_managed_policies': config.get_workspace_name('managed-policies') if ctx.is_multi_state() else '',
        'state_mode': ctx.state_mode,
        'platform': ctx.platform,
    }

    # Setup Jinja environment
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(source_dir),
        autoescape=False,
        trim_blocks=True,
        lstrip_blocks=True,
    )

    # Templates that are handled by TERRAFORM_GENERATION_TASKS (skip these)
    skip_templates = {
        'aws_identitystore_users.tf.jinja',
        'aws_identitystore_users_scim.tf.jinja',
        'aws_identitystore_users_map.tf.jinja',
        'aws_identitystore_users_import.tf.jinja',
        'aws_identitystore_groups.tf.jinja',
        'aws_identitystore_groups_scim.tf.jinja',
        'aws_identitystore_groups_map.tf.jinja',
        'aws_identitystore_groups_import.tf.jinja',
        'aws_identitystore_group_memberships_map.tf.jinja',
        'aws_identitystore_group_memberships_map_scim.tf.jinja',
        'aws_identitystore_group_memberships_import.tf.jinja',
        'aws_iam_managed_policies_list.tf.jinja',
        'aws_iam_managed_policies_map.tf.jinja',
        'aws_iam_managed_policies_map_static.tf.jinja',
        'aws_ssoadmin_permission_sets.tf.jinja',
        'aws_ssoadmin_permission_sets_map.tf.jinja',
        'aws_ssoadmin_permission_sets_import.tf.jinja',
        'aws_ssoadmin_permission_set_inline_policies_import.tf.jinja',
        'aws_ssoadmin_managed_policy_attachments_map.tf.jinja',
        'aws_ssoadmin_managed_policy_attachments_import.tf.jinja',
        'aws_ssoadmin_account_assignments_import.tf.jinja',
        'aws_ssoadmin_account_assignments_map.tf.jinja',
        'data.tf.jinja',
        'main.tf.jinja',
    }
    
    # Skip data source template when using static ARNs (default)
    if not config.use_managed_policy_data_sources():
        skip_templates.add('aws_iam_managed_policies.tf.jinja')
    
    # Templates to skip in single-state mode
    skip_in_single_state = {
        'external.tf.jinja',
        'external_remote_state.tf.jinja',
        'aws_ssoadmin_account_assignments.tf.jinja',
        'aws_ssoadmin_managed_policy_attachments.tf.jinja',
        'aws_ssoadmin_account_assignments_remote_state.tf.jinja',
        'aws_ssoadmin_managed_policy_attachments_remote_state.tf.jinja',
    }
    
    # Templates to skip in multi-state mode
    skip_in_multi_state = {
        'variables.tf.jinja',
        'aws_ssoadmin_account_assignments_local.tf.jinja',
        'aws_ssoadmin_managed_policy_attachments_local.tf.jinja',
    }
    
    # Templates to skip in multi-state TFC mode
    skip_in_multi_state_tfc = {
        'external_remote_state.tf.jinja',
        'aws_ssoadmin_account_assignments_remote_state.tf.jinja',
        'aws_ssoadmin_managed_policy_attachments_remote_state.tf.jinja',
    }
    
    # Templates to skip in multi-state local mode
    skip_in_multi_state_local = {
        'external.tf.jinja',
        'aws_ssoadmin_account_assignments.tf.jinja',
        'aws_ssoadmin_managed_policy_attachments.tf.jinja',
    }

    for template_file in source_dir.glob("*.tf.jinja"):
        # Skip templates that are handled by TERRAFORM_GENERATION_TASKS
        if template_file.name in skip_templates:
            ctx.log(f"[VERBOSE-2] Skipping {template_file.name} (handled by TERRAFORM_GENERATION_TASKS)", 2)
            continue
        
        # Skip templates based on state mode
        if ctx.is_single_state() and template_file.name in skip_in_single_state:
            ctx.log(f"[VERBOSE-2] Skipping {template_file.name} (not needed in single-state mode)", 2)
            continue
        
        if ctx.is_multi_state() and template_file.name in skip_in_multi_state:
            ctx.log(f"[VERBOSE-2] Skipping {template_file.name} (not needed in multi-state mode)", 2)
            continue
        
        # Skip platform-specific templates
        if ctx.is_multi_state() and ctx.is_tfc() and template_file.name in skip_in_multi_state_tfc:
            ctx.log(f"[VERBOSE-2] Skipping {template_file.name} (not needed in multi-state TFC mode)", 2)
            continue
        
        if ctx.is_multi_state() and ctx.is_local() and template_file.name in skip_in_multi_state_local:
            ctx.log(f"[VERBOSE-2] Skipping {template_file.name} (not needed in multi-state local mode)", 2)
            continue
        
        # Determine output filename based on template variant
        if ctx.is_single_state():
            local_variant = template_file.name.replace(".tf.jinja", "_local.tf.jinja")
            local_variant_path = source_dir / local_variant
            if local_variant_path.exists():
                ctx.log(f"[VERBOSE-2] Skipping {template_file.name} (using single-state variant instead)", 2)
                continue
            
            if "_local.tf.jinja" in template_file.name:
                new_name = template_file.name.replace("_local.tf.jinja", ".tf")
            else:
                new_name = template_file.name.replace(".tf.jinja", ".tf")
        elif ctx.is_multi_state() and ctx.is_local():
            if "_remote_state.tf.jinja" in template_file.name:
                new_name = template_file.name.replace("_remote_state.tf.jinja", ".tf")
            else:
                new_name = template_file.name.replace(".tf.jinja", ".tf")
        else:
            new_name = template_file.name.replace(".tf.jinja", ".tf")
            
        dest_file = target_dir / new_name

        ctx.log(f"[VERBOSE-2] Rendering {template_file} => {dest_file}", 2)

        # Render the template with config variables
        template = env.get_template(template_file.name)
        rendered = template.render(**template_context)
        
        dest_file.write_text(rendered, encoding="utf-8")

    ctx.log("[GENERATE] Done rendering templates.")


def render_template(ctx: GeneratorContext, template_name: str, output_name: str, data: dict, output_folder: str = None):
    """
    Locates and renders a Jinja template with 'data'.
    Writes the rendered output to 'output_name' in 'output_folder'.
    """
    found_path = None
    
    if output_folder:
        search_dir = f"{TEMPLATE_DIR}/{output_folder}"
    else:
        search_dir = TEMPLATE_DIR
    
    for root, _, files in os.walk(search_dir):
        if template_name in files:
            found_path = Path(root) / template_name
            break

    if not found_path or not found_path.is_file():
        raise FileNotFoundError(f"[ERROR] Template not found: {template_name}")

    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(found_path.parent),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    template = env.get_template(found_path.name)

    rendered = template.render(data)
    rendered_clean = rendered.rstrip() + "\n"

    if output_folder is None:
        final_output_folder = Path(ctx.terraform_dir)
    else:
        final_output_folder = Path(ctx.terraform_dir) / output_folder

    final_output_folder.mkdir(parents=True, exist_ok=True)

    output_file = final_output_folder / output_name
    output_file.write_text(rendered_clean, encoding="utf-8")

    ctx.log(f"[GENERATE] Wrote {output_file}")


def load_json_files(directory: Path, required_fields: list, ctx: GeneratorContext, allow_missing: bool = False) -> list:
    """
    Loads and parses all *.json files in 'directory' into a list of dicts.
    Ensures each dict contains all 'required_fields'.
    """
    if not directory.is_dir():
        if allow_missing:
            ctx.log(f"[GENERATE] Directory not found (skipping): {directory}")
            return []
        raise FileNotFoundError(f"[ERROR] Directory not found: {directory}")

    items = []
    for json_file in sorted(directory.glob("*.json"), key=lambda f: f.name.lower()):
        with open(json_file, "r", encoding="utf-8") as f:
            item = json.load(f)
            for field in required_fields:
                if field not in item:
                    raise KeyError(f"[ERROR] Missing '{field}' in {json_file}")
            items.append(item)

            ctx.log(f"[VERBOSE-2] Loaded JSON item: {item.get('ResourceName', json_file.name)}", 2)

    return items


def load_membership_files(directory: Path, ctx: GeneratorContext) -> dict:
    """
    Loads membership JSON files into a dict with structure:
      { "group_name": [ {"ResourceName": user_name, "SCIM": bool, ...}, ... ], ... }
    """
    if not directory.is_dir():
        raise FileNotFoundError(f"[ERROR] Directory not found: {directory}")

    memberships = {}
    for json_file in sorted(directory.glob("*.json"), key=lambda f: f.name.lower()):
        with open(json_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            group_name, user_name = json_file.stem.split("___", maxsplit=1)

            group_orig_name = data.get("GroupOriginalName", group_name)
            user_orig_name = data.get("UserOriginalName", user_name)

            if group_orig_name not in memberships:
                memberships[group_orig_name] = []

            memberships[group_orig_name].append({
                "ResourceName": user_name,
                "OriginalName": user_orig_name,
                "SCIM": data.get("SCIM", False),
                "ImportId": data.get("ImportId"),
                "ImportTo": data.get("ImportTo"),
            })

            ctx.log(f"[VERBOSE-2] Loaded membership: {group_orig_name} => {user_orig_name}", 2)

    return memberships


def load_managed_policy_attachments(directory: Path, required_fields: list, ctx: GeneratorContext) -> dict:
    """
    Loads each permission_set JSON in 'directory' and returns a dict mapping:
       PermissionSetName -> [ {Name, Arn, PermissionSetArn, InstanceArn}, ... ]
    Only includes permission sets that have at least one ManagedPolicy attached.
    """
    if not directory.is_dir():
        raise FileNotFoundError(f"[ERROR] Directory not found: {directory}")

    attachments = {}
    for json_file in sorted(directory.glob("*.json"), key=lambda f: f.name.lower()):
        with open(json_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        if required_fields:
            for field in required_fields:
                if field not in data:
                    raise KeyError(f"[ERROR] Missing '{field}' in {json_file}")

        ps_name = data["ResourceName"]
        import_id = data["ImportId"]
        instance_arn, permission_set_arn = import_id.split(",", maxsplit=1)

        managed_policies = data.get("ManagedPolicies", [])

        final_policies = []
        for mp in managed_policies:
            final_policies.append({
                "Name": mp.get("Name"),
                "Arn": mp.get("Arn"),
                "PermissionSetArn": permission_set_arn,
                "InstanceArn": instance_arn,
            })

        if final_policies:
            attachments[ps_name] = final_policies
            ctx.log(f"[VERBOSE-2] Loaded permission set '{ps_name}' -> {len(final_policies)} policies", 2)

    return attachments


def load_account_assignments(directory: Path, required_fields: list, ctx: GeneratorContext) -> list:
    """Loads JSON files in 'directory' that represent account assignments."""
    if not directory.is_dir():
        raise FileNotFoundError(f"[ERROR] Directory not found: {directory}")

    assignments = []
    for json_file in sorted(directory.glob("*.json"), key=lambda f: f.name.lower()):
        with open(json_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        if required_fields:
            for field in required_fields:
                if field not in data:
                    raise KeyError(f"[ERROR] Missing '{field}' in {json_file}")

        assignments.append(data)
        ctx.log(f"[VERBOSE-2] Loaded account assignment from {json_file.name}: {data['ResourceName']}", 2)

    return assignments


def build_account_assignments_map(assignments: list) -> dict:
    """
    Converts a list of assignment dicts into a nested dict:
       { "AccountName": { "PermissionSetName": { "GROUP": [...], "USER": [...] }, ... }, ... }
    """
    result = {}
    for a in assignments:
        account_name = a["AccountName"]
        permset_name = a["PermissionSetName"]
        principal_type = a["PrincipalType"]
        principal_name = a["PrincipalName"]

        if permset_name.startswith("TEAM-") or account_name.startswith("UnknownAccount"):
            continue

        if account_name not in result:
            result[account_name] = {}
        if permset_name not in result[account_name]:
            result[account_name][permset_name] = {}
        if principal_type not in result[account_name][permset_name]:
            result[account_name][permset_name][principal_type] = []

        result[account_name][permset_name][principal_type].append(principal_name)

    return result


# =============================================================================
# Generation Functions
# =============================================================================
def generate_ssoadmin_instances_files(ctx: GeneratorContext):
    """Creates subfolders under output/terraform and writes aws_ssoadmin_instances.tf into each one."""
    ctx.log("[GENERATE] Writing aws_ssoadmin_instances.tf files...")
    Path(ctx.terraform_dir).mkdir(parents=True, exist_ok=True)

    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(TEMPLATE_DIR),
        autoescape=False
    )
    template = env.get_template(SSOADMIN_INSTANCES_TEMPLATE_NAME)
    rendered_text = template.render()

    for folder in ctx.get_active_subfolders():
        folder_path = Path(ctx.terraform_dir) / folder
        folder_path.mkdir(parents=True, exist_ok=True)

        instances_file = folder_path / "aws_ssoadmin_instances.tf"
        ctx.log(f"[VERBOSE-2] Writing file: {instances_file}", 2)

        instances_file.write_text(rendered_text, encoding="utf-8")

    ctx.log("[GENERATE] Completed writing aws_ssoadmin_instances.tf files.")


def generate_providers_tf(ctx: GeneratorContext):
    """
    Creates providers.tf in each SSOADMIN_SUBFOLDERS folder.
    
    Mode behavior:
    - Single-state: Skipped (root module handles providers)
    - Multi-state TFC: Uses providers.tf.jinja with AWS + TFE providers
    - Multi-state local: Uses providers_local.tf.jinja with AWS provider only
    """
    if ctx.is_single_state():
        ctx.log("[GENERATE] Skipping subfolder providers.tf (single-state mode uses root providers)")
        return
    
    ctx.log("[GENERATE] Creating providers.tf in each subfolder...")

    config = ctx.config
    auto_update = config.is_auto_update_providers_enabled()
    
    if auto_update:
        ctx.log("[VERBOSE-2] Auto-update providers enabled, fetching latest versions...", 2)
        aws_provider_version = get_latest_aws_provider_version()
        tfe_provider_version = get_latest_tfe_provider_version() if ctx.is_tfc() else None
    else:
        ctx.log("[VERBOSE-2] Auto-update providers disabled, using pinned versions...", 2)
        aws_provider_version = "5.85.0"
        tfe_provider_version = "0.63.0" if ctx.is_tfc() else None
    
    ctx.log(f"[VERBOSE-2] AWS provider version: {aws_provider_version}", 2)
    if tfe_provider_version:
        ctx.log(f"[VERBOSE-2] TFE provider version: {tfe_provider_version}", 2)

    region = read_sso_admin_region(ctx)
    ctx.log(f"[VERBOSE-2] Region from sso_admin: {region}", 2)

    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(TEMPLATE_DIR),
        autoescape=False
    )
    
    if ctx.is_local():
        template_name = "providers_local.tf.jinja"
        template = env.get_template(template_name)
        rendered = template.render(
            aws_provider_version=aws_provider_version,
            region=region
        ).rstrip() + "\n"
    else:
        template = env.get_template(PROVIDERS_TEMPLATE_NAME)
        rendered = template.render(
            aws_provider_version=aws_provider_version,
            tfe_provider_version=tfe_provider_version,
            region=region
        ).rstrip() + "\n"

    for folder in ctx.get_active_subfolders():
        folder_path = Path(ctx.terraform_dir) / folder
        folder_path.mkdir(parents=True, exist_ok=True)

        providers_file = folder_path / "providers.tf"
        ctx.log(f"[VERBOSE-2] Writing providers.tf: {providers_file}", 2)

        providers_file.write_text(rendered, encoding="utf-8")

    ctx.log("[GENERATE] Completed creating providers.tf in each subfolder.")


def generate_local_root_module(ctx: GeneratorContext):
    """
    Generates root module files for single-state mode.
    Creates main.tf and providers.tf at the root level that wire together all child modules.
    """
    if not ctx.is_single_state():
        return
    
    ctx.log("[GENERATE] Creating root module files for single-state mode...")
    
    config = ctx.config
    auto_update = config.is_auto_update_providers_enabled()
    
    if auto_update:
        aws_provider_version = get_latest_aws_provider_version()
    else:
        aws_provider_version = "5.85.0"
    
    region = read_sso_admin_region(ctx)
    enable_team = config.is_team_enabled()
    
    local_template_dir = Path(TEMPLATE_DIR) / "local"
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(local_template_dir),
        autoescape=False,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    
    # Render root main.tf
    main_template = env.get_template("main.tf.jinja")
    main_rendered = main_template.render(enable_team=enable_team).rstrip() + "\n"
    
    main_file = Path(ctx.terraform_dir) / "main.tf"
    main_file.write_text(main_rendered, encoding="utf-8")
    ctx.log(f"[VERBOSE-2] Writing root main.tf: {main_file}", 2)
    
    # Render root providers.tf based on platform
    if ctx.is_tfc():
        providers_template = env.get_template("providers_tfc.tf.jinja")
        workspace_name = config.get_workspace_name()
        providers_rendered = providers_template.render(
            aws_provider_version=aws_provider_version,
            region=region,
            tfe_organization=config.get_tfe_organization(),
            workspace_name=workspace_name
        ).rstrip() + "\n"
    else:
        providers_template = env.get_template("providers.tf.jinja")
        providers_rendered = providers_template.render(
            aws_provider_version=aws_provider_version,
            region=region
        ).rstrip() + "\n"
    
    providers_file = Path(ctx.terraform_dir) / "providers.tf"
    providers_file.write_text(providers_rendered, encoding="utf-8")
    ctx.log(f"[VERBOSE-2] Writing root providers.tf: {providers_file}", 2)
    
    ctx.log("[GENERATE] Completed creating root module files.")


def generate_subfolder_templates(ctx: GeneratorContext):
    """Copies all *.tf.jinja templates from each subfolder within 'templates/' to 'output/terraform/'."""
    for subfolder in ctx.get_active_subfolders():
        src = Path(TEMPLATE_DIR) / subfolder
        dest = Path(ctx.terraform_dir) / subfolder
        copy_templates(src, dest, ctx)


# Data-driven tasks for generating terraform files
TERRAFORM_GENERATION_TASKS = [
    # ----------------- Users -----------------
    {
        "template_name": "aws_identitystore_users.tf.jinja",
        "output_name": "aws_identitystore_users.tf",
        "json_dir": "users",
        "required_fields": ["SCIM", "ResourceName", "UserName"],
        "loader": "load_json_files",
        "filter": lambda items: items,
        "data_key": "users",
        "output_folder": "identity_store",
    },
    {
        "template_name": "aws_identitystore_users_scim.tf.jinja",
        "output_name": "aws_identitystore_users_scim.tf",
        "json_dir": "users",
        "required_fields": ["SCIM", "ResourceName", "UserName"],
        "loader": "load_json_files",
        "filter": lambda items: [u for u in items if u["SCIM"]],
        "data_key": "users",
        "output_folder": "identity_store",
    },
    {
        "template_name": "aws_identitystore_users_map.tf.jinja",
        "output_name": "aws_identitystore_users_map.tf",
        "json_dir": "users",
        "required_fields": ["SCIM", "ResourceName", "UserName"],
        "loader": "load_json_files",
        "filter": lambda items: items,
        "data_key": "users",
        "output_folder": "identity_store",
    },
    {
        "template_name": "aws_identitystore_users_import.tf.jinja",
        "output_name": "aws_identitystore_users_import.tf",
        "json_dir": "users",
        "required_fields": ["SCIM", "ResourceName", "ImportId"],
        "loader": "load_json_files",
        "filter": lambda items: [u for u in items if not u["SCIM"]],
        "data_key": "users",
        "output_folder": "identity_store",
    },
    # ----------------- Groups -----------------
    {
        "template_name": "aws_identitystore_groups.tf.jinja",
        "output_name": "aws_identitystore_groups.tf",
        "json_dir": "groups",
        "required_fields": ["SCIM", "ResourceName", "DisplayName"],
        "loader": "load_json_files",
        "filter": lambda items: [g for g in items if not g["SCIM"]],
        "data_key": "groups",
        "output_folder": "identity_store",
    },
    {
        "template_name": "aws_identitystore_groups_scim.tf.jinja",
        "output_name": "aws_identitystore_groups_scim.tf",
        "json_dir": "groups",
        "required_fields": ["SCIM", "ResourceName", "DisplayName"],
        "loader": "load_json_files",
        "filter": lambda items: [g for g in items if g["SCIM"]],
        "data_key": "groups",
        "output_folder": "identity_store",
    },
    {
        "template_name": "aws_identitystore_groups_map.tf.jinja",
        "output_name": "aws_identitystore_groups_map.tf",
        "json_dir": "groups",
        "required_fields": ["SCIM", "ResourceName", "DisplayName"],
        "loader": "load_json_files",
        "filter": lambda items: items,
        "data_key": "groups",
        "output_folder": "identity_store",
    },
    {
        "template_name": "aws_identitystore_groups_import.tf.jinja",
        "output_name": "aws_identitystore_groups_import.tf",
        "json_dir": "groups",
        "required_fields": ["SCIM", "ResourceName", "ImportId"],
        "loader": "load_json_files",
        "filter": lambda items: [g for g in items if not g["SCIM"]],
        "data_key": "groups",
        "output_folder": "identity_store",
    },
    # ----------------- Group Memberships -----------------
    {
        "template_name": "aws_identitystore_group_memberships_map.tf.jinja",
        "output_name": "aws_identitystore_group_memberships_map.tf",
        "json_dir": "group_memberships",
        "required_fields": [],
        "loader": "load_membership_files",
        "filter": lambda all_m: {
            g: [m for m in mem if not m["SCIM"]]
            for g, mem in all_m.items()
            if any(not x["SCIM"] for x in mem)
        },
        "data_key": "memberships",
        "output_folder": "identity_store",
    },
    {
        "template_name": "aws_identitystore_group_memberships_map_scim.tf.jinja",
        "output_name": "aws_identitystore_group_memberships_map_scim.tf",
        "json_dir": "group_memberships",
        "required_fields": [],
        "loader": "load_membership_files",
        "filter": lambda all_m: {
            g: [m for m in mem if m["SCIM"]]
            for g, mem in all_m.items()
            if any(x["SCIM"] for x in mem)
        },
        "data_key": "memberships",
        "output_folder": "identity_store",
    },
    {
        "template_name": "aws_identitystore_group_memberships_import.tf.jinja",
        "output_name": "aws_identitystore_group_memberships_import.tf",
        "json_dir": "group_memberships",
        "required_fields": [],
        "loader": "load_membership_files",
        "filter": lambda all_m: {
            g: [m for m in mem if not m["SCIM"]]
            for g, mem in all_m.items()
        },
        "data_key": "memberships",
        "output_folder": "identity_store",
    },
    # ----------------- Managed Policies -----------------
    {
        "template_name": "aws_iam_managed_policies_list.tf.jinja",
        "output_name": "aws_iam_managed_policies_list.tf",
        "json_dir": "managed_policies",
        "required_fields": ["PolicyName"],
        "loader": "load_json_files",
        "filter": lambda items: items,
        "data_key": "policies",
        "output_folder": "managed_policies",
        "allow_missing": True,
    },
    {
        "template_name": "aws_iam_managed_policies_map.tf.jinja",
        "output_name": "aws_iam_managed_policies_map.tf",
        "json_dir": "managed_policies",
        "required_fields": ["PolicyName", "Arn"],
        "loader": "load_json_files",
        "filter": lambda items: items,
        "data_key": "policies",
        "output_folder": "managed_policies",
        "allow_missing": True,
    },
    # ----------------- Permission Sets -----------------
    {
        "template_name": "aws_ssoadmin_permission_sets.tf.jinja",
        "output_name": "aws_ssoadmin_permission_sets.tf",
        "json_dir": "permission_sets",
        "required_fields": ["ResourceName", "SessionDuration"],
        "loader": "load_json_files",
        "filter": lambda items: items,
        "data_key": "permission_sets",
        "output_folder": "permission_sets",
    },
    {
        "template_name": "aws_ssoadmin_permission_sets_map.tf.jinja",
        "output_name": "aws_ssoadmin_permission_sets_map.tf",
        "json_dir": "permission_sets",
        "required_fields": ["ResourceName"],
        "loader": "load_json_files",
        "filter": lambda items: items,
        "data_key": "permission_sets",
        "output_folder": "permission_sets",
    },
    {
        "template_name": "aws_ssoadmin_permission_sets_import.tf.jinja",
        "output_name": "aws_ssoadmin_permission_sets_import.tf",
        "json_dir": "permission_sets",
        "required_fields": ["ResourceName", "ImportId", "ImportTo"],
        "loader": "load_json_files",
        "filter": lambda items: items,
        "data_key": "permission_sets",
        "output_folder": "permission_sets",
    },
    {
        "template_name": "aws_ssoadmin_permission_set_inline_policies_import.tf.jinja",
        "output_name": "aws_ssoadmin_permission_set_inline_policies_import.tf",
        "json_dir": "permission_sets",
        "required_fields": ["ResourceName", "ImportId", "HasInlinePolicy"],
        "loader": "load_json_files",
        "filter": lambda items: [p for p in items if p["HasInlinePolicy"]],
        "data_key": "permission_sets",
        "output_folder": "permission_sets",
    },
    {
        "template_name": "aws_ssoadmin_managed_policy_attachments_map.tf.jinja",
        "output_name": "aws_ssoadmin_managed_policy_attachments_map.tf",
        "json_dir": "permission_sets",
        "required_fields": [],
        "loader": "load_managed_policy_attachments",
        "filter": lambda items: items,
        "data_key": "attachments",
        "output_folder": "permission_sets"
    },
    {
        "template_name": "aws_ssoadmin_managed_policy_attachments_import.tf.jinja",
        "output_name": "aws_ssoadmin_managed_policy_attachments_import.tf",
        "json_dir": "permission_sets",
        "required_fields": ["ResourceName", "ImportId", "ManagedPolicies"],
        "loader": "load_managed_policy_attachments",
        "filter": lambda items: items,
        "data_key": "attachments",
        "output_folder": "permission_sets",
    },
    # ----------------- Account Assignments -----------------
    {
        "template_name": "aws_ssoadmin_account_assignments_import.tf.jinja",
        "output_name": "aws_ssoadmin_account_assignments_import.tf",
        "json_dir": "account_assignments",
        "required_fields": ["ResourceName", "ImportId", "ImportTo"],
        "loader": "load_account_assignments",
        "filter": lambda items: [p for p in items if not p["PermissionSetName"].startswith("TEAM-") and not p["AccountName"].startswith("UnknownAccount")],
        "data_key": "assignments",
        "output_folder": "account_assignments",
    },
    {
        "template_name": "aws_ssoadmin_account_assignments_map.tf.jinja",
        "output_name": "aws_ssoadmin_account_assignments_map.tf",
        "json_dir": "account_assignments",
        "required_fields": ["AccountName", "PermissionSetName", "PrincipalType", "PrincipalName"],
        "loader": "load_account_assignments",
        "filter": build_account_assignments_map,
        "data_key": "account_assignments_map",
        "output_folder": "account_assignments",
    },
    {
        "template_name": "locals.tf.jinja",
        "output_name": "locals.tf",
        "json_dir": "accounts",
        "required_fields": ["ResourceName", "Id"],
        "loader": "load_json_files",
        "filter": lambda items: items,
        "data_key": "accounts",
        "output_folder": "account_assignments",
    },
    # ----------------- Team Policies -----------------
    {
        "template_name": "aws_team_approver_policies.tf.jinja",
        "output_name": "aws_team_approver_policies.tf",
        "json_dir": "team/dynamodb_items/approvers",
        "required_fields": [],
        "loader": "load_json_files",
        "filter": lambda items: items,
        "data_key": "approver_policies",
        "output_folder": "team",
    },
    {
        "template_name": "aws_team_eligibility_policies.tf.jinja",
        "output_name": "aws_team_eligibility_policies.tf",
        "json_dir": "team/dynamodb_items/eligibility",
        "required_fields": [],
        "loader": "load_json_files",
        "filter": lambda items: items,
        "data_key": "eligibility_policies",
        "output_folder": "team",
    }
]


def load_team_application_assignments(directory: Path, ctx: GeneratorContext) -> dict:
    """Loads TEAM application assignments from JSON."""
    assignments_file = directory / "team_application_assignments.json"
    
    if not assignments_file.exists():
        ctx.log(f"[GENERATE] No TEAM application assignments file found at {assignments_file}")
        return {'users': [], 'groups': [], 'assignments': []}
    
    try:
        with open(assignments_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        ctx.log(f"[VERBOSE-2] Loaded {len(data.get('users', []))} users and {len(data.get('groups', []))} groups for TEAM app", 2)
        return data
        
    except Exception as e:
        ctx.log(f"[GENERATE] Error loading TEAM application assignments: {e}")
        return {'users': [], 'groups': [], 'assignments': []}


def get_team_application_arn(ctx: GeneratorContext) -> str:
    """Reads the TEAM IDC APP application ARN from the JSON directory."""
    try:
        team_app_file = Path(ctx.json_dir) / "team" / "team_application.json"
        if team_app_file.exists():
            with open(team_app_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                arn = data.get('ApplicationArn')
                ctx.log(f"[GENERATE] Found TEAM IDC APP ARN: {arn}")
                return arn
        else:
            ctx.log(f"[GENERATE] TEAM application file not found at {team_app_file}")
            return None
        
    except Exception as e:
        ctx.log(f"[GENERATE] Error reading TEAM application file: {e}")
        return None


def render_team_data_tf(ctx: GeneratorContext):
    """Special handler for team/data.tf that needs both DynamoDB tables and TEAM application ARN."""
    ctx.log("[GENERATE] Rendering team/data.tf...")
    
    team_app_arn = get_team_application_arn(ctx)
    if not team_app_arn:
        ctx.log("[GENERATE] Warning: No TEAM application ARN found, skipping team/data.tf")
        return
    
    dynamodb_tables_dir = Path(ctx.json_dir) / "team" / "dynamodb_tables"
    dynamodb_tables = load_json_files(dynamodb_tables_dir, ["Table"], ctx)
    
    render_template(
        ctx,
        template_name="data.tf.jinja",
        output_name="data.tf",
        data={'dynamodb_tables': dynamodb_tables, 'team_application_arn': team_app_arn},
        output_folder="team"
    )
    
    ctx.log("[GENERATE] Rendered team/data.tf")


def render_team_locals_tf(ctx: GeneratorContext):
    """Special handler for team/locals.tf that needs both accounts and organizational units."""
    ctx.log("[GENERATE] Rendering team/locals.tf...")
    
    accounts_dir = Path(ctx.json_dir) / "accounts"
    accounts = load_json_files(accounts_dir, ["ResourceName", "Id"], ctx)
    
    ous_dir = Path(ctx.json_dir) / "organizational_units"
    if ous_dir.is_dir():
        ous = load_json_files(ous_dir, ["OriginalName", "Id"], ctx)
        ous = sorted(ous, key=lambda x: x.get("FullPath", x["OriginalName"]))
    else:
        ous = []
        ctx.log("[GENERATE] No organizational units found, skipping ou_map")
    
    render_template(
        ctx,
        template_name="locals.tf.jinja",
        output_name="locals.tf",
        data={'accounts': accounts, 'organizational_units': ous},
        output_folder="team"
    )
    
    ctx.log("[GENERATE] Rendered team/locals.tf")


def render_team_application_assignments(ctx: GeneratorContext):
    """Special handler for TEAM application assignments."""
    ctx.log("[GENERATE] Rendering TEAM application assignments...")
    
    team_app_arn = get_team_application_arn(ctx)
    if not team_app_arn:
        ctx.log("[GENERATE] Skipping TEAM application assignments (no ARN found)")
        return
    
    team_dir = Path(ctx.json_dir) / "team"
    assignment_data = load_team_application_assignments(team_dir, ctx)
    
    users = assignment_data.get('users', [])
    groups = assignment_data.get('groups', [])
    assignments = assignment_data.get('assignments', [])
    
    if not users and not groups:
        ctx.log("[GENERATE] No TEAM application assignments to render")
        return
    
    render_template(
        ctx,
        template_name="aws_team_application_assignments.tf.jinja",
        output_name="aws_team_application_assignments.tf",
        data={'team_users': users, 'team_groups': groups, 'team_application_arn': team_app_arn},
        output_folder="team"
    )
    
    # Import template location depends on state mode
    if ctx.is_single_state():
        render_template(
            ctx,
            template_name="aws_team_application_assignments_import_single.tf.jinja",
            output_name="aws_team_application_assignments_import.tf",
            data={'assignments': assignments},
            output_folder=None
        )
    else:
        render_template(
            ctx,
            template_name="aws_team_application_assignments_import.tf.jinja",
            output_name="aws_team_application_assignments_import.tf",
            data={'assignments': assignments},
            output_folder="team"
        )
    
    ctx.log(f"[GENERATE] Rendered TEAM application assignments: {len(users)} users, {len(groups)} groups")


def add_module_prefix_to_imports(data, module_name: str, data_key: str):
    """
    Adds module prefix to ImportTo fields for single-state mode.
    In single-state mode, resources are in child modules, so import blocks
    need to reference them as module.<name>.<resource>.
    """
    module_ref = module_name.replace("-", "_")
    
    if isinstance(data, list):
        result = []
        for item in data:
            if isinstance(item, dict) and "ImportTo" in item:
                new_item = item.copy()
                new_item["ImportTo"] = f"module.{module_ref}.{item['ImportTo']}"
                result.append(new_item)
            else:
                result.append(item)
        return result
    elif isinstance(data, dict):
        result = {}
        for key, items in data.items():
            if isinstance(items, list):
                new_items = []
                for item in items:
                    if isinstance(item, dict) and "ImportTo" in item:
                        new_item = item.copy()
                        new_item["ImportTo"] = f"module.{module_ref}.{item['ImportTo']}"
                        new_items.append(new_item)
                    else:
                        new_items.append(item)
                result[key] = new_items
            else:
                result[key] = items
        return result
    else:
        return data


def generate_terraform_files(ctx: GeneratorContext):
    """
    Generates all terraform .tf files by:
      1) Loading the JSON data for each resource type.
      2) Applying the designated filter.
      3) Rendering the corresponding Jinja template.
    """
    ctx.log("[GENERATE] Creating IdentityStore files...")

    config = ctx.config
    team_enabled = config.is_team_enabled()
    use_data_sources = config.use_managed_policy_data_sources()

    for task in TERRAFORM_GENERATION_TASKS:
        # Skip TEAM tasks if TEAM is disabled
        if task.get("output_folder") == "team" and not team_enabled:
            ctx.log(f"[VERBOSE-2] Skipping {task['output_name']} (enable_team is False)", 2)
            continue
        
        # Skip managed policy list when using static ARNs
        if task["template_name"] == "aws_iam_managed_policies_list.tf.jinja" and not use_data_sources:
            ctx.log(f"[VERBOSE-2] Skipping {task['output_name']} (using static ARNs)", 2)
            continue
        
        # Select correct managed policy map template based on config
        template_name = task["template_name"]
        if template_name == "aws_iam_managed_policies_map.tf.jinja" and not use_data_sources:
            template_name = "aws_iam_managed_policies_map_static.tf.jinja"
            ctx.log("[VERBOSE-2] Using static ARN template for managed policies map", 2)
        
        # Determine if this is an import file
        is_import_file = "_import" in task["output_name"]
        
        # In single-state mode, import files go to root with module prefix
        if ctx.is_single_state() and is_import_file:
            output_folder = None
            module_name = task.get("output_folder", "").replace("_", "-")
            if not module_name:
                module_name = "root"
            module_ref = module_name.replace("-", "_")
            module_prefix = f"module.{module_ref}."
        else:
            output_folder = task.get("output_folder")
            module_name = None
            module_prefix = ""
        
        if is_import_file and ctx.is_single_state():
            ctx.log(f"[GENERATE] Rendering {task['output_name']} at root level (single-state mode)")
        else:
            ctx.log(f"[GENERATE] Rendering {task['output_name']} from {task['template_name']} ...")

        directory = Path(ctx.json_dir) / task["json_dir"]

        # Load the data using the appropriate loader
        loader_name = task["loader"]
        if loader_name == "load_membership_files":
            raw_data = load_membership_files(directory, ctx)
        elif loader_name == "load_json_files":
            allow_missing = task.get("allow_missing", False)
            raw_data = load_json_files(directory, task["required_fields"], ctx, allow_missing=allow_missing)
        elif loader_name == "load_managed_policy_attachments":
            raw_data = load_managed_policy_attachments(directory, task["required_fields"], ctx)
        elif loader_name == "load_account_assignments":
            raw_data = load_account_assignments(directory, task["required_fields"], ctx)
        else:
            raise ValueError(f"Unknown loader: {loader_name}")

        filtered_data = task["filter"](raw_data)
        
        # In single-state mode, prefix ImportTo with module name for import files
        if ctx.is_single_state() and is_import_file and module_name:
            filtered_data = add_module_prefix_to_imports(filtered_data, module_name, task["data_key"])

        template_data = {task["data_key"]: filtered_data, "module_prefix": module_prefix}

        render_template(
            ctx,
            template_name=template_name,
            output_name=task["output_name"],
            data=template_data,
            output_folder=output_folder
        )


def copy_additional_folders(ctx: GeneratorContext):
    """
    Copies additional folders from JSON_DIR to TERRAFORM_DIR that contain
    non-Terraform files needed by the generated configuration.
    """
    ctx.log("[GENERATE] Copying additional folders...")
    
    # Copy inline policies from JSON dir to permission_sets output
    json_inline_policies_dir = Path(ctx.json_dir) / "permission_sets" / "inline_policies"
    output_inline_policies_dir = Path(ctx.terraform_dir) / "permission_sets" / "inline_policies"
    
    if json_inline_policies_dir.exists() and json_inline_policies_dir.is_dir():
        output_inline_policies_dir.mkdir(parents=True, exist_ok=True)
        
        json_files = list(json_inline_policies_dir.glob("*.json"))
        if json_files:
            for json_file in json_files:
                dest_file = output_inline_policies_dir / json_file.name
                shutil.copy2(json_file, dest_file)
                ctx.log(f"[VERBOSE-2] Copied inline policy: {json_file.name}", 2)
            
            ctx.log(f"[GENERATE] Copied {len(json_files)} inline policy file(s).")
        else:
            ctx.log("[GENERATE] No inline policy files found to copy.")
    else:
        ctx.log("[GENERATE] No inline_policies directory found in JSON output.")
    
    # Copy managed policies from JSON dir to managed_policies output
    json_managed_policies_dir = Path(ctx.json_dir) / "managed_policies" / "policies"
    output_managed_policies_dir = Path(ctx.terraform_dir) / "managed_policies" / "policies"
    
    if json_managed_policies_dir.exists() and json_managed_policies_dir.is_dir():
        output_managed_policies_dir.mkdir(parents=True, exist_ok=True)
        
        json_files = list(json_managed_policies_dir.glob("*.json"))
        if json_files:
            for json_file in json_files:
                dest_file = output_managed_policies_dir / json_file.name
                shutil.copy2(json_file, dest_file)
                ctx.log(f"[VERBOSE-2] Copied managed policy: {json_file.name}", 2)
            
            ctx.log(f"[GENERATE] Copied {len(json_files)} managed policy file(s).")
        else:
            ctx.log("[GENERATE] No managed policy files found to copy.")
    else:
        ctx.log("[GENERATE] No managed_policies/policies directory found in JSON output.")
    
    # Copy TEAM template modules from generator templates to output
    if not ctx.config.is_team_enabled():
        ctx.log("[GENERATE] Skipping TEAM modules (enable_team is False)")
    else:
        team_template_dir = Path(REPO_ROOT) / "templates" / "team"
        output_modules_dir = Path(ctx.terraform_dir) / "team" / "modules"
        
        if team_template_dir.exists() and team_template_dir.is_dir():
            # Copy approver module
            approver_src = team_template_dir / "approver"
            approver_dest = output_modules_dir / "approver"
            
            if approver_src.exists():
                if approver_dest.exists():
                    shutil.rmtree(approver_dest)
                shutil.copytree(approver_src, approver_dest)
                ctx.log("[GENERATE] Copied TEAM approver module.")
            
            # Copy eligibility module
            eligibility_src = team_template_dir / "eligibility"
            eligibility_dest = output_modules_dir / "eligibility"
            
            if eligibility_src.exists():
                if eligibility_dest.exists():
                    shutil.rmtree(eligibility_dest)
                shutil.copytree(eligibility_src, eligibility_dest)
                ctx.log("[GENERATE] Copied TEAM eligibility module.")
            
            # Copy team_app_assignment module
            team_app_assignment_src = team_template_dir / "team_app_assignment"
            team_app_assignment_dest = Path(ctx.terraform_dir) / "team" / "team_app_assignment"
            
            if team_app_assignment_src.exists():
                if team_app_assignment_dest.exists():
                    shutil.rmtree(team_app_assignment_dest)
                shutil.copytree(team_app_assignment_src, team_app_assignment_dest)
                ctx.log("[GENERATE] Copied TEAM application assignment module.")
        else:
            ctx.log("[GENERATE] No TEAM templates found to copy.")
    
    ctx.log("[GENERATE] Finished copying additional folders.")


def ensure_single_newline_at_end(ctx: GeneratorContext):
    """Ensures every *.tf and *.tf.json file ends with exactly one newline."""
    ctx.log("[GENERATE] Ensuring single newline at end of each file...")

    tf_path = Path(ctx.terraform_dir)
    if not tf_path.is_dir():
        raise FileNotFoundError(f"[ERROR] Terraform directory not found: {tf_path}")

    for file_path in tf_path.rglob("*"):
        if file_path.is_file() and file_path.suffix in [".tf", ".tf.json"]:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
            cleaned = content.rstrip() + "\n"
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(cleaned)

            ctx.log(f"[VERBOSE-2] Updated newline at end: {file_path}", 2)

    ctx.log("[GENERATE] Finished enforcing single newlines.")


def add_headers_to_tf_files(ctx: GeneratorContext, header_comment: str):
    """Prepends 'header_comment' to each *.tf and *.tf.json file."""
    ctx.log("[GENERATE] Adding headers to Terraform files...")

    tf_path = Path(ctx.terraform_dir)
    if not tf_path.is_dir():
        raise FileNotFoundError(f"[ERROR] Terraform directory not found: {tf_path}")

    for file_path in tf_path.rglob("*"):
        if file_path.is_file() and file_path.suffix in [".tf", ".tf.json"]:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            if not content.startswith(header_comment):
                new_content = header_comment + "\n" + content.lstrip()
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(new_content)

                ctx.log(f"[VERBOSE-2] Added header to {file_path}", 2)

    ctx.log("[GENERATE] Finished adding headers.")


def preserve_managed_policies_from_terraform(ctx: GeneratorContext) -> bool:
    """
    Preserves managed policies data from existing Terraform output before cleaning.
    Parses aws_iam_managed_policies_list.tf or aws_iam_managed_policies_map.tf
    and converts to JSON format for the generator.
    """
    ctx.log("[GENERATE] Preserving managed policies from existing Terraform output...")
    
    tf_managed_policies_list_file = Path(ctx.terraform_dir) / "managed_policies" / "aws_iam_managed_policies_list.tf"
    tf_managed_policies_map_file = Path(ctx.terraform_dir) / "managed_policies" / "aws_iam_managed_policies_map.tf"
    tf_policies_dir = Path(ctx.terraform_dir) / "managed_policies" / "policies"
    
    json_managed_policies_dir = Path(ctx.json_dir) / "managed_policies"
    json_policies_dir = json_managed_policies_dir / "policies"
    
    # Determine which source file to use
    source_file = None
    parse_mode = None
    
    if tf_managed_policies_list_file.exists():
        source_file = tf_managed_policies_list_file
        parse_mode = "list"
    elif tf_managed_policies_map_file.exists():
        source_file = tf_managed_policies_map_file
        parse_mode = "map"
    else:
        ctx.log("[GENERATE] No existing managed policies Terraform file found in output")
        return False
    
    ctx.log(f"[VERBOSE-2] Using {parse_mode} format from: {source_file.name}", 2)
    
    try:
        with open(source_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        policies = []
        
        if parse_mode == "list":
            match = re.search(r'managed_policies_list\s*=\s*\[(.*?)\]', content, re.DOTALL)
            if not match:
                ctx.log("[GENERATE] Could not parse managed_policies_list from Terraform file")
                return False
            
            list_content = match.group(1)
            policy_names = re.findall(r'"([^"]+)"', list_content)
            
            for name in policy_names:
                policies.append({"PolicyName": name, "Arn": f"arn:aws:iam::aws:policy/{name}"})
        
        elif parse_mode == "map":
            match = re.search(r'managed_policies_map\s*=\s*\{(.*?)\}', content, re.DOTALL)
            if not match:
                ctx.log("[GENERATE] Could not parse managed_policies_map from Terraform file")
                return False
            
            map_content = match.group(1)
            pairs = re.findall(r'"([^"]+)"\s*=\s*"([^"]+)"', map_content)
            
            for name, arn in pairs:
                policies.append({"PolicyName": name, "Arn": arn})
        
        if not policies:
            ctx.log("[GENERATE] No policies found in Terraform file")
            return False
        
        ctx.log(f"[VERBOSE-2] Found {len(policies)} managed policies in Terraform output", 2)
        
        json_managed_policies_dir.mkdir(parents=True, exist_ok=True)
        
        for policy in policies:
            json_file = json_managed_policies_dir / f"{policy['PolicyName']}.json"
            with open(json_file, 'w', encoding='utf-8') as f:
                json.dump(policy, f, indent=2, ensure_ascii=False)
            ctx.log(f"[VERBOSE-2] Created {policy['PolicyName']}.json", 2)
        
        if tf_policies_dir.exists() and tf_policies_dir.is_dir():
            if json_policies_dir.exists():
                shutil.rmtree(json_policies_dir)
            shutil.copytree(tf_policies_dir, json_policies_dir)
            
            policy_files = list(json_policies_dir.glob("*.json"))
            ctx.log(f"[GENERATE] Preserved {len(policies)} managed policies and {len(policy_files)} policy documents")
        else:
            ctx.log(f"[GENERATE] Preserved {len(policies)} managed policies (no policy documents found)")
        
        return True
        
    except Exception as e:
        ctx.log(f"[GENERATE] Error preserving managed policies: {e}")
        return False


def clean_terraform_directories(ctx: GeneratorContext):
    """
    Removes all generated Terraform directories from the output location.
    Mode-aware cleanup handles switching between modes.
    """
    ctx.log(f"[GENERATE] Cleaning Terraform directories (mode: {ctx.state_mode}, platform: {ctx.platform})...")
    
    active_subfolders = ctx.get_active_subfolders()
    
    # Mode-specific cleanup BEFORE clearing directories
    if ctx.is_single_state():
        # Single-state mode: remove external.tf and providers.tf from components
        for subfolder in SSOADMIN_SUBFOLDERS:
            external_file = Path(ctx.terraform_dir) / subfolder / "external.tf"
            if external_file.exists():
                ctx.log(f"[VERBOSE-2] Removing {external_file} (not needed in single-state mode)", 2)
                external_file.unlink()
            
            providers_file = Path(ctx.terraform_dir) / subfolder / "providers.tf"
            if providers_file.exists():
                ctx.log(f"[VERBOSE-2] Removing {providers_file} (single-state uses root providers)", 2)
                providers_file.unlink()
    else:
        # Multi-state mode: remove root-level files
        root_files = ["main.tf", "providers.tf"]
        for filename in root_files:
            filepath = Path(ctx.terraform_dir) / filename
            if filepath.exists():
                ctx.log(f"[VERBOSE-2] Removing {filepath} (not needed in multi-state mode)", 2)
                filepath.unlink()
        
        for subfolder in SSOADMIN_SUBFOLDERS:
            variables_file = Path(ctx.terraform_dir) / subfolder / "variables.tf"
            if variables_file.exists():
                ctx.log(f"[VERBOSE-2] Removing {variables_file} (not needed in multi-state mode)", 2)
                variables_file.unlink()
    
    # Remove team folder if team is disabled
    if "team" not in active_subfolders:
        team_path = Path(ctx.terraform_dir) / "team"
        if team_path.exists():
            ctx.log(f"[VERBOSE-2] Removing {team_path} (enable_team is False)", 2)
            shutil.rmtree(team_path)
    
    # Clear active subfolders completely and recreate as empty directories
    for subfolder in active_subfolders:
        subfolder_path = Path(ctx.terraform_dir) / subfolder
        
        if subfolder_path.exists():
            ctx.log(f"[VERBOSE-2] Removing {subfolder_path}", 2)
            shutil.rmtree(subfolder_path)
        
        subfolder_path.mkdir(parents=True, exist_ok=True)
        ctx.log(f"[VERBOSE-2] Created {subfolder_path}", 2)
    
    ctx.log("[GENERATE] Terraform directories cleaned.")


# =============================================================================
# Main Entry Point
# =============================================================================
def generate_terraform(verbosity=0, output=".", config="config.yaml", overrides=None, 
                       retain_managed_policies=False):
    """
    Main entry point for generating Terraform files.
    
    Args:
        verbosity: 0=quiet, 1=normal, 2=verbose
        output: Base output directory for Terraform files
        config: Path to config.yaml file
        overrides: Dictionary of CLI parameter overrides
        retain_managed_policies: Preserve managed policies from existing output
    """
    # Load config first to get values, then apply CLI overrides
    merged_overrides = overrides or {}
    cfg = reload_config(config, merged_overrides)
    
    # Get final values (CLI overrides > config.yaml > defaults)
    state_mode = cfg.get_state_mode()
    platform = cfg.get_platform()
    
    # Create the context with resolved values
    ctx = GeneratorContext(
        output_dir=output,
        config_path=config,
        state_mode=state_mode,
        platform=platform,
        verbosity=verbosity,
        retain_managed_policies=retain_managed_policies,
        overrides=merged_overrides
    )
    
    ctx.log(f"[GENERATE] Starting Terraform generation (state-mode: {state_mode}, platform: {platform})...")

    # If retaining managed policies, preserve them from existing Terraform output
    # This must happen BEFORE cleaning directories
    if ctx.retain_managed_policies:
        preserved = preserve_managed_policies_from_terraform(ctx)
        if not preserved:
            print("[WARNING] --retain-managed-policies was set but no existing managed policies found.")
            print("[WARNING] This flag only works when there's existing Terraform output to preserve from.")
            print("[WARNING] Proceeding without managed policies - permission set attachments may fail.")
            print("[WARNING] Run without --retain-managed-policies to fetch fresh data from AWS.")

    # Clean existing Terraform files to ensure deletions are reflected
    clean_terraform_directories(ctx)

    generate_ssoadmin_instances_files(ctx)
    generate_providers_tf(ctx)
    generate_subfolder_templates(ctx)
    generate_terraform_files(ctx)
    
    # Render TEAM-specific files (require special handling) - only if TEAM is enabled
    if ctx.config.is_team_enabled():
        render_team_locals_tf(ctx)
        render_team_data_tf(ctx)
        render_team_application_assignments(ctx)
    else:
        ctx.log("[GENERATE] Skipping TEAM files (enable_team is False)")
    
    copy_additional_folders(ctx)
    
    # Generate root module files for single-state mode
    generate_local_root_module(ctx)
    
    ensure_single_newline_at_end(ctx)

    header_comment = "# Generated Terraform file for AWS IAM Identity Center"
    add_headers_to_tf_files(ctx, header_comment)

    ctx.log("[GENERATE] Terraform generation complete.")
