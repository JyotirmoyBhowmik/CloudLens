# OCI Connector Research Note

Authoritative reference for Oracle Cloud Infrastructure (OCI) connector capabilities, API versions, and cautions.
See full specification at `docs/connectors/oci_research_note.md`.

## Key Interfaces & Versions
- **Auth**: OCI Identity and Access Management API version `20160918` (Instance Principals, API Signing RSA Key, Identity Domains OIDC).
- **Hierarchy**: Identity and Access Management API version `20160918` (`/20160918/compartments`). Compartment tree depth preserved up to 6 levels; mapped to GROUP and SUB_GROUP. Compartment depth parameter supported in cost queries.
- **Inventory**: Search Service API version `20180409` (`/20180409/resources`). Structured search across tenancy.
- **Cost**: Usage API version `20200107` (`/20200107/usage`) for interactive Cost Analysis queries, and Object Storage Usage Reports (`20160918`) for CSV ingestion.
- **Budgets**: Budgets API version `20190111` (`/20190111/budgets`). Alert types (ACTUAL, FORECAST), Threshold types (ABSOLUTE, PERCENTAGE). Non-authoritative (`is_authoritative = False`).
- **Pricing**: OCI does not expose a dynamic public SKU rate card query API comparable to AWS/Azure/GCP. Static public rate cards and Universal Credits contract rate cards are supported with explicit notation of no dynamic API parity.
- **Tags & Timing**: Tagging API version `20160918`. Free-form, defined namespaced tags, and cost-tracking tags. Non-retroactive tag attribution enforced and surfaced.
- **Relationships**: Minimal structural edges only (VNIC, Volume, Subnet attachments). Declared as PARTIAL / MINIMAL.
