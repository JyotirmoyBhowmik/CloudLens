"""CloudLens Layered Configuration Resolution Engine.

Implements the three-layer resolution order:
1. BUILTIN_DEFAULT (from SystemConfig and TenantSettings schemas)
2. ENVIRONMENT (from CLOUDLENS_<SECTION>__<FIELD> env vars)
3. TENANT (from tenant settings store / database)

Every resolved setting exposes:
- key: Dotted path (e.g. 'database.pool_size', 'threshold_defaults.budget_alert_threshold_percentage')
- effective_value: Effective resolved value (masked if secret in diagnostics)
- layer: ConfigLayer enum indicating provenance
- description: Setting documentation
- is_secret: Whether value is sensitive
"""

import os
from typing import Any

from domain.config.layers import ConfigLayer, ConfigProvenance
from domain.config.surface import SystemConfig
from domain.config.tenant_settings import TenantSettings, tenant_settings_store

SECRET_SUBSTRINGS = ("password", "secret", "token", "key", "cert")


def _is_secret_field(field_name: str, field_info: Any) -> bool:
    """Determine whether a field contains confidential credentials."""
    extra = getattr(field_info, "json_schema_extra", None)
    if isinstance(extra, dict) and extra.get("is_secret"):
        return True
    return any(sub in field_name.lower() for sub in SECRET_SUBSTRINGS)


def _mask_secret(val: Any) -> str:
    """Mask confidential strings for diagnostic and inspector output."""
    if val is None or val == "":
        return "[NOT SET]"
    return "******"


class ConfigurationResolver:
    """Resolves layered settings with full provenance and secret protection."""

    def __init__(self) -> None:
        self._builtin_system = SystemConfig()

    def get_effective_value(
        self,
        key: str,
        tenant_id: str | None = None,
    ) -> Any:
        """Retrieve effective unmasked value for execution."""
        prov = self.resolve_provenance(key, tenant_id=tenant_id, mask_secrets=False)
        return prov.effective_value

    def resolve_provenance(
        self,
        key: str,
        tenant_id: str | None = None,
        mask_secrets: bool = True,
    ) -> ConfigProvenance:
        """Resolve effective value and its originating layer provenance for a given key."""
        # 1. Check if key is a tenant-level setting
        if tenant_id is not None:
            tenant_settings = tenant_settings_store.get(tenant_id)
            tenant_prov = self._resolve_tenant_field(key, tenant_settings, tenant_id, mask_secrets)
            if tenant_prov is not None:
                return tenant_prov

        # 2. Check system-level settings
        system_prov = self._resolve_system_field(key, mask_secrets)
        if system_prov is not None:
            return system_prov

        raise KeyError(f"Configuration key '{key}' does not exist on the configuration surface.")

    def inspect_all(
        self,
        tenant_id: str | None = None,
        mask_secrets: bool = True,
    ) -> list[ConfigProvenance]:
        """Generate comprehensive diagnostic list of all settings with provenance."""
        provenances: list[ConfigProvenance] = []

        # System surface inspection
        for section_name, section_model in self._builtin_system:
            for field_name, _field_info in section_model.__class__.model_fields.items():
                key = f"{section_name}.{field_name}"
                prov = self._resolve_system_field(key, mask_secrets=mask_secrets)
                if prov:
                    provenances.append(prov)

        # Tenant surface inspection (if tenant_id provided)
        if tenant_id is not None:
            tenant_settings = tenant_settings_store.get(tenant_id)
            tenant_fields = self._inspect_tenant_surface(tenant_settings, tenant_id, mask_secrets)
            provenances.extend(tenant_fields)

        return provenances

    def _resolve_system_field(self, key: str, mask_secrets: bool) -> ConfigProvenance | None:
        parts = key.split(".")
        if len(parts) != 2:
            return None

        section_name, field_name = parts
        if not hasattr(self._builtin_system, section_name):
            return None

        section_obj = getattr(self._builtin_system, section_name)
        if field_name not in section_obj.__class__.model_fields:
            return None

        field_info = section_obj.__class__.model_fields[field_name]
        is_secret = _is_secret_field(field_name, field_info)
        description = field_info.description or ""
        expected_type = (
            field_info.annotation.__name__
            if hasattr(field_info.annotation, "__name__")
            else str(field_info.annotation)
        )

        builtin_val = getattr(section_obj, field_name)
        effective_val = builtin_val
        layer = ConfigLayer.BUILTIN_DEFAULT

        # Check environment layer: CLOUDLENS_<SECTION>__<FIELD>
        env_var = f"CLOUDLENS_{section_name.upper()}__{field_name.upper()}"
        if env_var in os.environ:
            raw_env = os.environ[env_var]
            effective_val = self._cast_env_val(raw_env, field_info.annotation)
            layer = ConfigLayer.ENVIRONMENT

        raw_unmasked = effective_val
        display_val = _mask_secret(effective_val) if (is_secret and mask_secrets) else effective_val

        return ConfigProvenance(
            key=key,
            effective_value=display_val,
            layer=layer,
            description=description,
            is_secret=is_secret,
            data_type=expected_type,
            raw_unmasked_value=raw_unmasked,
        )

    def _resolve_tenant_field(
        self,
        key: str,
        tenant_settings: TenantSettings,
        tenant_id: str,
        mask_secrets: bool,
    ) -> ConfigProvenance | None:
        _ = mask_secrets
        parts = key.split(".")
        default_tenant = TenantSettings(tenant_id="default")

        # Nested tenant sub-objects (e.g. threshold_defaults.budget_alert_threshold_percentage)
        if len(parts) == 2:
            section_name, field_name = parts
            if hasattr(tenant_settings, section_name):
                sub_obj = getattr(tenant_settings, section_name)
                default_sub_obj = getattr(default_tenant, section_name)
                if hasattr(sub_obj, field_name):
                    field_info = sub_obj.__class__.model_fields[field_name]
                    current_val = getattr(sub_obj, field_name)
                    default_val = getattr(default_sub_obj, field_name)
                    description = field_info.description or ""
                    expected_type = getattr(
                        field_info.annotation, "__name__", str(field_info.annotation)
                    )

                    # Check if overridden from built-in default
                    layer = (
                        ConfigLayer.TENANT
                        if current_val != default_val
                        else ConfigLayer.BUILTIN_DEFAULT
                    )

                    return ConfigProvenance(
                        key=key,
                        effective_value=current_val,
                        layer=layer,
                        description=description,
                        is_secret=False,
                        data_type=expected_type,
                        tenant_id=tenant_id,
                        raw_unmasked_value=current_val,
                    )

        # Top-level tenant fields (e.g. reporting_currency)
        if len(parts) == 1 and hasattr(tenant_settings, key):
            field_name = key
            field_info = TenantSettings.model_fields[field_name]
            current_val = getattr(tenant_settings, field_name)
            default_val = getattr(default_tenant, field_name)
            description = field_info.description or ""
            expected_type = getattr(field_info.annotation, "__name__", str(field_info.annotation))
            layer = (
                ConfigLayer.TENANT if current_val != default_val else ConfigLayer.BUILTIN_DEFAULT
            )

            return ConfigProvenance(
                key=key,
                effective_value=current_val,
                layer=layer,
                description=description,
                is_secret=False,
                data_type=expected_type,
                tenant_id=tenant_id,
                raw_unmasked_value=current_val,
            )

        return None

    def _inspect_tenant_surface(
        self,
        tenant_settings: TenantSettings,
        tenant_id: str,
        mask_secrets: bool,
    ) -> list[ConfigProvenance]:
        items: list[ConfigProvenance] = []
        # Top-level settings
        for field in (
            "reporting_currency",
            "fiscal_calendar_start_month",
            "default_time_zone",
            "cost_basis_default",
            "forecast_method_default",
        ):
            prov = self._resolve_tenant_field(field, tenant_settings, tenant_id, mask_secrets)
            if prov:
                items.append(prov)

        # Nested settings
        for group in ("retention_profile", "threshold_defaults", "approval_limits"):
            sub_obj = getattr(tenant_settings, group)
            for sub_field in sub_obj.__class__.model_fields:
                key = f"{group}.{sub_field}"
                prov = self._resolve_tenant_field(key, tenant_settings, tenant_id, mask_secrets)
                if prov:
                    items.append(prov)

        return items

    def _cast_env_val(self, raw_val: str, annotation: Any) -> Any:
        type_str = str(annotation).lower()
        if "int" in type_str:
            return int(raw_val)
        if "float" in type_str:
            return float(raw_val)
        if "bool" in type_str:
            return raw_val.strip().lower() in ("1", "true", "yes", "on")
        return raw_val


# Global singleton resolver instance
config_resolver = ConfigurationResolver()
