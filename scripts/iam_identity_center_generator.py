import click
from phase1_fetch import fetch_data
from phase2_generate import generate_terraform
from config_loader import reload_config

@click.group(invoke_without_command=True)
@click.option("-v", "--verbosity", type=click.Choice(["quiet", "normal", "verbose"]), default=None, help="Verbosity level.")
@click.option("-o", "--output", type=click.Path(), default=None, help="Output directory.")
@click.option("-c", "--config", type=click.Path(), default="config.yaml", help="Config file path.")
@click.option("-s", "--state-mode", type=click.Choice(["single", "multi"]), default=None, help="State mode.")
@click.option("-p", "--platform", type=click.Choice(["local", "tfc"]), default=None, help="Platform.")
@click.option("-t", "--tfc-org", type=str, default=None, help="TFC organization.")
@click.option("-x", "--prefix", type=str, default=None, help="Prefix for project/workspace/role names.")
@click.option("-e", "--environment", type=str, default=None, help="Environment name (for TFC and GitHub).")
@click.option("-a", "--auto-update-providers", type=bool, default=None, help="Auto-update providers.")
@click.option("-m", "--enable-team", type=bool, default=None, help="Enable TEAM.")
@click.option("-r", "--retain-managed-policies", type=bool, default=None, help="Retain managed policies (skip refresh).")
@click.pass_context
def cli(ctx, verbosity, output, config, state_mode, platform, tfc_org, prefix, 
        environment, auto_update_providers, enable_team, retain_managed_policies):
    """
    IAM Identity Center Generator.
    
    No subcommand => fetch + generate.
    Configuration priority: CLI flags > config.yaml > defaults
    """
    ctx.ensure_object(dict)
    ctx.obj["CONFIG_PATH"] = config
    ctx.obj["OVERRIDES"] = {
        "verbosity": verbosity,
        "output": output,
        "state_mode": state_mode,
        "platform": platform,
        "tfc_org": tfc_org,
        "prefix": prefix,
        "environment": environment,
        "auto_update_providers": auto_update_providers,
        "enable_team": enable_team,
        "retain_managed_policies": retain_managed_policies,
    }

    if not ctx.invoked_subcommand:
        _run_full(ctx)


def _run_full(ctx):
    """Run fetch + generate."""
    config_path = ctx.obj["CONFIG_PATH"]
    overrides = ctx.obj["OVERRIDES"]
    
    # Load config to get resolved values
    cfg = reload_config(config_path, overrides)
    verbosity = cfg.get_verbosity()
    output_dir = cfg.get("output")
    retain_policies = cfg.get("retain_managed_policies")
    
    fetch_data(
        verbosity=verbosity,
        output=output_dir,
        config=config_path,
        overrides=overrides,
        retain_managed_policies=retain_policies
    )
    generate_terraform(
        verbosity=verbosity,
        output=output_dir,
        config=config_path,
        overrides=overrides,
        retain_managed_policies=retain_policies
    )


@cli.command()
@click.pass_context
def fetch(ctx):
    """Fetch data from AWS only."""
    cfg = reload_config(ctx.obj["CONFIG_PATH"], ctx.obj["OVERRIDES"])
    fetch_data(
        verbosity=cfg.get_verbosity(),
        output=cfg.get("output"),
        config=ctx.obj["CONFIG_PATH"],
        overrides=ctx.obj["OVERRIDES"],
        retain_managed_policies=cfg.get("retain_managed_policies")
    )


@cli.command()
@click.pass_context
def generate(ctx):
    """Generate Terraform files only."""
    cfg = reload_config(ctx.obj["CONFIG_PATH"], ctx.obj["OVERRIDES"])
    generate_terraform(
        verbosity=cfg.get_verbosity(),
        output=cfg.get("output"),
        config=ctx.obj["CONFIG_PATH"],
        overrides=ctx.obj["OVERRIDES"],
        retain_managed_policies=cfg.get("retain_managed_policies")
    )


if __name__ == "__main__":
    cli(obj={})
