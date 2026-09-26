"""Tag Normalisation Service for CloudLens.

Enforces Prompt 08 Item 54:
"Implement tag normalisation: configurable key convention (case and separator policy),
original key retained, OCI defined-tag namespace retained separately, and the
source level recorded (resource, resource group, subscription, compartment, project)."
"""

import re
from typing import Any

from domain.models.exceptions import InvalidTagConventionException
from normalisation.tags.models import (
    NormalizedTag,
    RawTagInput,
    TagCasePolicy,
    TagKeyConvention,
    TagSeparatorPolicy,
    TagSourceLevel,
)

# Regex to split on camelCase transitions, whitespace, dots, hyphens, and underscores
_TOKEN_SPLIT_REGEX = re.compile(r"[_\s\-\.]+|(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")


class TagNormalisationService:
    """Service that standardizes cloud tags across AWS, Azure, GCP, and OCI."""

    def __init__(self, default_convention: TagKeyConvention | None = None) -> None:
        self.default_convention = default_convention or TagKeyConvention()

    def split_key_tokens(self, key: str) -> list[str]:
        """Splits a tag key into semantic word tokens."""
        trimmed = key.strip()
        if not trimmed:
            return []
        tokens = [t for t in _TOKEN_SPLIT_REGEX.split(trimmed) if t]
        return tokens

    def extract_oci_namespace(
        self,
        raw_key: str,
        explicit_namespace: str | None = None,
        source_level: TagSourceLevel | None = None,
    ) -> tuple[str | None, str]:
        """Extracts OCI defined-tag namespace and key component.

        OCI defined tags commonly use 'Namespace.TagKey' formatting or have explicit namespace bags.
        Returns: (namespace, tag_key)
        """
        if explicit_namespace:
            return explicit_namespace.strip(), raw_key.strip()

        # Check for OCI defined tag pattern: Namespace.TagKey
        # Only extract namespace when from COMPARTMENT (OCI native) or matches Oracle/OCI namespace prefix
        if "." in raw_key:
            parts = raw_key.split(".", 1)
            ns_candidate, key_candidate = parts[0].strip(), parts[1].strip()
            if ns_candidate and key_candidate:
                is_oci_context = (
                    source_level == TagSourceLevel.COMPARTMENT
                    or ns_candidate.lower().startswith("oracle")
                    or ns_candidate.lower().startswith("oci")
                )
                if is_oci_context:
                    return ns_candidate, key_candidate

        return None, raw_key.strip()

    def normalise_key(
        self,
        raw_key: str,
        convention: TagKeyConvention | None = None,
        explicit_namespace: str | None = None,
        source_level: TagSourceLevel | None = None,
    ) -> tuple[str | None, str]:
        """Normalises a tag key according to configured case and separator policy.

        Returns: (namespace, normalized_key)
        """
        conv = convention or self.default_convention
        namespace, key_to_transform = self.extract_oci_namespace(
            raw_key, explicit_namespace=explicit_namespace, source_level=source_level
        )

        tokens = self.split_key_tokens(key_to_transform)
        if not tokens:
            return namespace, key_to_transform.strip()

        # 1. Determine separator character
        sep = "-"
        if conv.separator_policy == TagSeparatorPolicy.HYPHEN:
            sep = "-"
        elif conv.separator_policy == TagSeparatorPolicy.UNDERSCORE:
            sep = "_"
        elif conv.separator_policy == TagSeparatorPolicy.DOT:
            sep = "."
        elif conv.separator_policy == TagSeparatorPolicy.PRESERVE:
            sep = ""

        # 2. Apply Case Policy
        if (
            conv.case_policy == TagCasePolicy.LOWER
            or conv.case_policy == TagCasePolicy.KEBAB
            or conv.case_policy == TagCasePolicy.SNAKE
        ):
            norm_tokens = [t.lower() for t in tokens]
            norm_key = sep.join(norm_tokens)
        elif conv.case_policy == TagCasePolicy.UPPER:
            norm_tokens = [t.upper() for t in tokens]
            norm_key = sep.join(norm_tokens)
        elif conv.case_policy == TagCasePolicy.CAMEL:
            if not tokens:
                norm_key = ""
            else:
                norm_key = tokens[0].lower() + "".join(t.capitalize() for t in tokens[1:])
        elif conv.case_policy == TagCasePolicy.PRESERVE:
            norm_key = sep.join(tokens) if sep else key_to_transform.strip()
        else:
            raise InvalidTagConventionException(
                f"Unsupported tag casing policy: '{conv.case_policy}'."
            )

        return namespace, norm_key

    def normalise_tag(
        self,
        raw: RawTagInput,
        convention: TagKeyConvention | None = None,
    ) -> NormalizedTag:
        """Normalises a single raw tag input into a NormalizedTag."""
        conv = convention or self.default_convention
        namespace, normalized_key = self.normalise_key(
            raw.key,
            convention=conv,
            explicit_namespace=raw.namespace,
            source_level=raw.source_level,
        )

        return NormalizedTag(
            original_key=raw.key,
            normalized_key=normalized_key,
            value=raw.value,
            source_level=raw.source_level,
            namespace=namespace,
            inherited=raw.inherited,
        )

    def normalise_tags(
        self,
        raw_tags: list[RawTagInput],
        convention: TagKeyConvention | None = None,
    ) -> list[NormalizedTag]:
        """Normalises a collection of RawTagInput items."""
        return [self.normalise_tag(t, convention=convention) for t in raw_tags]

    def normalise_dict(
        self,
        tags_dict: dict[str, Any],
        source_level: TagSourceLevel = TagSourceLevel.RESOURCE,
        namespace: str | None = None,
        inherited: bool = False,
        convention: TagKeyConvention | None = None,
    ) -> list[NormalizedTag]:
        """Helper to normalise a dictionary of key-value pairs."""
        raw_inputs = [
            RawTagInput(
                key=str(k),
                value=str(v),
                source_level=source_level,
                namespace=namespace,
                inherited=inherited,
            )
            for k, v in tags_dict.items()
        ]
        return self.normalise_tags(raw_inputs, convention=convention)
