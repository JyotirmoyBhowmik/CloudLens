# CloudLens Architecture Decision Log (ADR)

> **Format**: Architecture Decision Record (ADR) based on Michael Nygard template.  
> **Status**: Maintained per prompt; single source of truth for design trade-offs.

---

## Index of Architectural Decisions

| ADR ID | Decision Title | Status | Date | Target Prompt |
|:---:|:---|:---:|:---:|:---:|
| `ADR-001` | Monorepo Structure & Inward Layering Rule | Accepted | 2026-09-25 | `Prompt 01` |
| `ADR-002` | First-Class Master Data Monorepo Area (`AM-01`) | Accepted | 2026-09-25 | `Prompt 01` / `AM-01` |
| `ADR-003` | Automated Layering Enforcement via AST Scanning | Accepted | 2026-09-25 | `Prompt 01` |

---

### ADR-001: Monorepo Structure & Inward Layering Rule
- **Context**: CloudLens must model four disparate cloud providers (Azure, AWS, GCP, OCI) without permitting vendor lock-in or leaking provider SDK abstractions into core business logic.
- **Decision**: Adopt a strict inward layering rule: `presentation` → `application` → `domain` → `normalisation` → `ingestion` → `connector` → `provider`. No component above `connectors/` may import a provider SDK.
- **Consequences**: Ensures clean domain isolation; permits mock and stub connectors for offline demo mode (Mandate M3); simplifies testing.

### ADR-002: First-Class Master Data Monorepo Area (`AM-01`)
- **Context**: Catalogues, dimensions, threshold defaults, and units are consumed by every layer, yet owned by none.
- **Decision**: Establish `masterdata/` as a top-level first-class package consumed by all layers.
- **Consequences**: Prevents cyclic imports between domain and normalisation; establishes single source of truth for reference data.

### ADR-003: Automated Layering Enforcement via AST Scanning
- **Context**: Architectural layering rules degrade over time without automated enforcement.
- **Decision**: Implement `scripts/check_layering.py` using Python's `ast` parser, wired into pre-commit hooks and CI pipelines.
- **Consequences**: Immediate build failure if a forbidden provider SDK is imported above the connector boundary.
