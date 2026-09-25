"""CloudLens Canonical Domain Model and Business Rules Layer.

Strictly provider-agnostic.
Layering rule: presentation -> application -> domain -> normalisation -> ingestion -> connector -> provider.
Nothing in domain may import a provider SDK or reference a provider by name.
"""
