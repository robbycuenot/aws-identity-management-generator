"""
Configuration loader for IAM Identity Center Generator.

Loads configuration from config.yaml with CLI overrides.
All config keys are flat (no nesting) for consistency with
TF variables, GH env vars, and CLI flags.
"""

import yaml
from pathlib import Path
from typing import Dict, Any, Optional


class ConfigValidationError(Exception):
    """Raised when configuration validation fails."""
    pass


class Config:
    """Configuration manager for the generator."""
    
    # Default values (flat structure)
    DEFAULTS = {
        "verbosity": "normal",
        "output": "./output",
        "state_mode": "single",
        "platform": "local",
        "tfc_org": "",
        "prefix": "aws-identity-management",
        "environment": "",
        "enable_team": False,
        "auto_update_providers": True,
        "retain_managed_policies": False,
    }
    
    VERBOSITY_MAP = {"quiet": 0, "normal": 1, "verbose": 2}
    
    def __init__(self, config_path: str = "config.yaml", overrides: Optional[Dict[str, Any]] = None):
        config_path_obj = Path(config_path)
        if not config_path_obj.is_absolute() and not config_path_obj.exists():
            parent_config = Path(__file__).parent.parent / config_path
            if parent_config.exists():
                config_path_obj = parent_config
        
        self.config_path = config_path_obj
        self.overrides = overrides or {}
        self._config = self._load_config()
    
    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from YAML file with defaults."""
        config = self.DEFAULTS.copy()
        
        if self.config_path.exists():
            try:
                with open(self.config_path, 'r') as f:
                    user_config = yaml.safe_load(f) or {}
                
                # Merge user config (flat structure)
                for key in self.DEFAULTS:
                    if key in user_config:
                        config[key] = user_config[key]
            except Exception as e:
                print(f"Warning: Error loading config file: {e}")
        
        # Apply CLI overrides (highest priority)
        for key in self.DEFAULTS:
            if key in self.overrides and self.overrides[key] is not None:
                config[key] = self.overrides[key]
        
        return config

    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value."""
        return self._config.get(key, default)
    
    def get_verbosity(self) -> int:
        """Get verbosity as integer (0=quiet, 1=normal, 2=verbose)."""
        value = self.get("verbosity", "quiet")
        if isinstance(value, int):
            return value
        return self.VERBOSITY_MAP.get(value, 0)
    
    def get_workspace_name(self, component: str = None) -> str:
        """
        Generate workspace name based on state mode.
        
        Single-state: {prefix}-{environment}
        Multi-state:  {prefix}-{environment}-{component}
        """
        prefix = self.get("prefix")
        env = self.get("environment")
        
        if self.get("state_mode") == "single":
            return f"{prefix}-{env}" if env else prefix
        else:
            if not component:
                raise ValueError("component is required for multi-state mode")
            return f"{prefix}-{env}-{component}" if env else f"{prefix}-{component}"
    
    def validate(self) -> None:
        """Validate configuration."""
        state_mode = self.get("state_mode")
        platform = self.get("platform")
        
        if state_mode not in ("single", "multi"):
            raise ConfigValidationError(f"state_mode must be 'single' or 'multi', got '{state_mode}'")
        
        if platform not in ("local", "tfc"):
            raise ConfigValidationError(f"platform must be 'local' or 'tfc', got '{platform}'")
        
        if platform == "tfc" and not self.get("tfc_org"):
            raise ConfigValidationError("tfc_org is required when platform is 'tfc'")
    
    # Convenience accessors
    def get_state_mode(self) -> str:
        return self.get("state_mode")
    
    def get_platform(self) -> str:
        return self.get("platform")
    
    def get_tfe_organization(self) -> str:
        return self.get("tfc_org")
    
    def get_prefix(self) -> str:
        return self.get("prefix")
    
    def is_team_enabled(self) -> bool:
        return self.get("enable_team", False)
    
    def is_auto_update_providers_enabled(self) -> bool:
        return self.get("auto_update_providers", True)
    
    def use_managed_policy_data_sources(self) -> bool:
        """Internal: use static ARNs (False) for faster planning."""
        return False
    
    def to_dict(self) -> Dict[str, Any]:
        return self._config.copy()


# Global config instance
_config_instance = None


def get_config(config_path: str = "config.yaml", overrides: Optional[Dict[str, Any]] = None) -> Config:
    global _config_instance
    if _config_instance is None:
        _config_instance = Config(config_path, overrides)
    return _config_instance


def reload_config(config_path: str = "config.yaml", overrides: Optional[Dict[str, Any]] = None) -> Config:
    global _config_instance
    _config_instance = Config(config_path, overrides)
    return _config_instance
