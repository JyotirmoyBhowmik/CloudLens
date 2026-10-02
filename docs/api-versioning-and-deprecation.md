# CloudLens Public API Versioning and Deprecation Policy

## 1. Versioning Strategy
CloudLens adopts strict path-based major versioning (`/api/v1/...`).
- **Patch/Minor changes**: Backward-compatible changes (adding new fields, optional query parameters, or new endpoints) remain within the current major version.
- **Major changes**: Any breaking change (removing endpoints, modifying existing field types, removing fields, altering required parameters, or changing error semantics) requires a new major version path (e.g. `/api/v2/...`).

## 2. Deprecation Policy
- Breaking changes require a new major version with a published deprecation window of **at least two full releases**.
- When an endpoint or field is marked for deprecation:
  1. The OpenAPI specification marks the operation or schema property as `deprecated: true`.
  2. Responses from deprecated endpoints include RFC-standard `Deprecation` and `Sunset` HTTP headers:
     - `Deprecation: @<timestamp>`
     - `Sunset: <Http-Date>`
     - `Link: </api/v2/...>; rel="successor-version"`
  3. Deprecated endpoints remain fully operational and supported for at least two release cycles prior to decommissioning.

## 3. Contract Drift Enforcement
The OpenAPI description at `docs/openapi.json` is the authoritative contract for the public API surface. Contract drift between the running application and `docs/openapi.json` is treated as a release blocker and verified by automated contract tests in CI (`tests/contracts/test_public_api_catalogue.py`).

## 4. Credential Privacy Rule
Under no circumstances may any API response return provider secret keys, certificates, private keys, passwords, or raw credentials. All credential assets are referenced exclusively by opaque identifiers (`credential_profile_id`). This rule is enforced by automated response schema scanning across every route.
