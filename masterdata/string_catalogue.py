"""Externalised String Catalogue & i18n Resolution Engine (Prompt 48 Item 37).

Enforces:
1. Every user-facing string resolves from the STRING_CATALOGUE master.
2. Labels, help text, explanation text, email text, and error text are editable
   without deployment and translatable without refactoring.
3. Changing any user-facing label requires no deployment.
"""

from typing import Any

from domain.models.exceptions import MasterDataException
from masterdata.models import MasterDataRecord
from masterdata.service import MasterDataService, get_master_data_service


class StringCatalogueService:
    """Resolves localized, user-facing text dynamically from master data."""

    def __init__(self, master_service: MasterDataService | None = None) -> None:
        self._master_service = master_service or get_master_data_service()

    def resolve_string(
        self,
        key: str,
        locale: str = "en_US",
        params: dict[str, Any] | None = None,
        tenant_id: str | None = None,
    ) -> str:
        """Resolves a string template from master data and performs parameter interpolation.

        Acceptance: Changing any user-facing label requires no deployment.
        """
        record: MasterDataRecord | None = self._master_service.get_record(
            master_type="STRING_CATALOGUE",
            code=key,
            tenant_id=tenant_id,
        )

        if not record:
            raise MasterDataException(
                f"User-facing string '{key}' is not registered in the STRING_CATALOGUE master. "
                "All labels, help text, explanation text, and error strings must be declared in master data."
            )

        attrs = record.attributes
        template = (
            attrs.get(f"template_{locale}")
            or attrs.get("template")
            or attrs.get("fallback_en")
            or record.display_name
        )

        if not params:
            return template

        # Interpolate variables safely
        try:
            return template.format(**params)
        except KeyError as err:
            missing_var = str(err).strip("'")
            raise MasterDataException(
                f"String template '{key}' missing required variable parameter '{missing_var}'."
            ) from err

    def list_strings_by_category(
        self,
        category: str,
        locale: str = "en_US",
        tenant_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Lists all registered string templates for a specific UI/reporting category."""
        records = self._master_service.list_records("STRING_CATALOGUE", tenant_id=tenant_id)
        results: list[dict[str, Any]] = []

        cat_upper = category.strip().upper()
        for r in records:
            if r.attributes.get("category", "").upper() == cat_upper:
                results.append(
                    {
                        "code": r.code,
                        "display_name": r.display_name,
                        "category": r.attributes.get("category"),
                        "locale": r.attributes.get("locale", locale),
                        "template": r.attributes.get("template"),
                        "variables": r.attributes.get("variables", []),
                    }
                )

        return results


# Global singleton string service
_string_catalogue_service: StringCatalogueService | None = None


def get_string_catalogue_service() -> StringCatalogueService:
    global _string_catalogue_service
    if _string_catalogue_service is None:
        _string_catalogue_service = StringCatalogueService()
    return _string_catalogue_service


def t(
    key: str,
    locale: str = "en_US",
    tenant_id: str | None = None,
    **kwargs: Any,
) -> str:
    """Convenience i18n lookup function resolving from master data."""
    return get_string_catalogue_service().resolve_string(
        key=key,
        locale=locale,
        params=kwargs,
        tenant_id=tenant_id,
    )
