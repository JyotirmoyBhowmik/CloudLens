"""Test Fixtures for Cloud Provider Inventory Samples.

Provides canonical sample data for contract tests and local verification without
polluting production connectors.
"""

from __future__ import annotations

from typing import Any

from connectors.simulator.sample_resources import (
    get_sample_aws_resources,
    get_sample_azure_resources,
    get_sample_gcp_resources,
    get_sample_oci_resources,
)

__all__ = [
    "get_sample_aws_resources",
    "get_sample_azure_resources",
    "get_sample_gcp_resources",
    "get_sample_oci_resources",
]
