# CloudLens Engineering & Contribution Guidelines

> **Enterprise Standards Compliance**: Strict adherence to Enterprise Production Engineering Rules (Input Validation, Sanitized Error Responses, Circuit Breakers, Correlation-ID Tracing, Zero Hard-Coding).

---

## 1. Monorepo Architecture & Strict Layering Rule

CloudLens is architected as an enterprise monorepo with rigid directional dependencies:

$$\text{Presentation (web)} \longrightarrow \text{Application (api, workers)} \longrightarrow \text{Domain} \longrightarrow \text{Normalisation} \longrightarrow \text{Ingestion} \longrightarrow \text{Connector} \longrightarrow \text{Provider}$$

### The Cardinal Layering Rule:
- **Nothing above the connector layer may import a provider SDK** (`boto3`, `azure.*`, `google.cloud.*`, `oci.*`) or reference a provider SDK client.
- The `domain/` layer is strictly provider-agnostic, modelling canonical cloud entities (`Resource`, `Service`, `CostFact`, `Threshold`, `Budget`).
- The `masterdata/` layer is a first-class monorepo area (`AM-01`) holding all catalogues, registries, and canonical definitions; every layer consumes it and nothing else owns it.
- **Layering Check**: Enforced automatically by `python scripts/check_layering.py` and runs on every commit. Violations fail the build.

---

## 2. Git Branch Naming Conventions

Branches must adhere to the standardized prompt-driven format:

```text
prompt/P<NN>-<short-description>
```

**Examples:**
- `prompt/P01-monorepo-skeleton`
- `prompt/P05-canonical-domain-model`
- `prompt/P16-azure-connector`
- `prompt/P22-cost-ingestion-focus`

---

## 3. Commit Message Conventions

Commit messages must follow the Conventional Commits specification and **must include the prompt identifier** in the scope:

```text
<type>(p<nn>): <concise description in imperative mood>

[optional body explaining rationale, non-obvious trade-offs]
[optional footer referencing requirements closed, e.g. Closes BR-001, FR-020]
```

**Allowed Types:**
- `feat`: New feature or capability
- `fix`: Bug fix or defect closure
- `refactor`: Code change that neither fixes a bug nor adds a feature
- `test`: Adding missing tests or correcting existing tests
- `docs`: Documentation updates
- `chore`: Tooling, build pipeline, or dependency updates

**Examples:**
- `feat(p01): monorepo skeleton, service boundaries and bootstrap`
- `fix(p00r): reconcile pricing dimension catalogue and issue missing ranges`
- `test(p01): add automated layering rule verification suite`

---

## 4. Coding & Quality Standards

### Python (Backend):
- **Formatting**: Automated via `ruff format` (100-character line limit).
- **Linting**: Automated via `ruff check` (E, W, F, I, B, C4, UP, ARG).
- **Import Ordering**: Strict `isort` ordering via Ruff (standard library -> third party -> first party `api`, `domain`, `connectors`, etc.).
- **Type Checking**: Strict type annotations enforced by `mypy`.
- **Docstring Style**: Google Python Style Guide with explicit argument, return, and raise documentation.

### TypeScript / React (Frontend):
- **Language**: TypeScript 5.5+ in strict mode.
- **Components**: Functional components with explicit typed prop interfaces.
- **Icons**: Lucide React.
- **Linting**: ESLint + Prettier.

---

## 5. Local Verification Commands

Before submitting changes, run the complete local gate verification:

```bash
# Run layering rule check
python scripts/check_layering.py

# Run Python linter and formatter checks
ruff check .
ruff format --check .

# Run type checker
mypy .

# Run test suite
pytest
```
