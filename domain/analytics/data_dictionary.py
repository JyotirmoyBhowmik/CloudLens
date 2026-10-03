"""Semantic Layer Data Dictionary & Business Glossaries (Prompt 56 / BBP Section 39).

Publishes the authoritative data dictionary for the CloudLens Semantic Layer,
documenting all conformed dimensions, central fact measures, derivation formulas,
and the four-state null discipline policy for business and finance users.
"""

from __future__ import annotations

from domain.analytics.models import SemanticDataDictionaryField

MASTER_DATA_DICTIONARY: list[SemanticDataDictionaryField] = [
    # --------------------------------------------------------------------------
    # Central Fact: FactCostAndUsage
    # --------------------------------------------------------------------------
    SemanticDataDictionaryField(
        TableName="FactCostAndUsage",
        ColumnName="FactKey",
        BusinessName="Fact Record Key",
        DataType="STRING (UUID)",
        Description="Unique identifier for each individual cost and usage fact record in the star-schema.",
        NullStatePolicy="Mandatory (Non-null)",
        SampleValue="fct-018f3a9e-8c3b-7a1b-9d4e-123456789abc",
    ),
    SemanticDataDictionaryField(
        TableName="FactCostAndUsage",
        ColumnName="ChargePeriod",
        BusinessName="Billing Period",
        DataType="STRING (YYYY-MM)",
        Description="Accounting calendar billing period in year and month format.",
        NullStatePolicy="Mandatory (Non-null)",
        SampleValue="2026-09",
    ),
    SemanticDataDictionaryField(
        TableName="FactCostAndUsage",
        ColumnName="BilledCostAmount",
        BusinessName="Billed Cost Amount",
        DataType="DECIMAL(18,4)",
        Description="Authoritative gross or net charge invoiced by the cloud service provider for the consumed service.",
        DerivationFormula="Direct sum of invoiced line item charge amounts converted to presentation currency.",
        NullStatePolicy="Preserves 4-state null discipline via BilledCostNullState (never flattened).",
        SampleValue="1245.5000",
    ),
    SemanticDataDictionaryField(
        TableName="FactCostAndUsage",
        ColumnName="EffectiveCostAmount",
        BusinessName="Effective Cost Amount",
        DataType="DECIMAL(18,4)",
        Description="Amortised cost of usage reflecting allocated upfront and recurring reservation fees and negotiated committed discounts.",
        DerivationFormula="BilledCostAmount + AmortisedUpfrontCommitmentShare - RealisedDiscountAdjustment.",
        NullStatePolicy="Preserves 4-state null discipline.",
        SampleValue="1015.2000",
    ),
    SemanticDataDictionaryField(
        TableName="FactCostAndUsage",
        ColumnName="ListCostAmount",
        BusinessName="List / Retail Cost Amount",
        DataType="DECIMAL(18,4)",
        Description="Theoretical cost if the resource were billed at standard undiscounted public catalog retail rates.",
        DerivationFormula="UsageQuantity * PublishedPublicCatalogOnDemandRate.",
        NullStatePolicy="Preserves 4-state null discipline.",
        SampleValue="1520.0000",
    ),
    SemanticDataDictionaryField(
        TableName="FactCostAndUsage",
        ColumnName="ContractedCostAmount",
        BusinessName="Contracted Enterprise Cost",
        DataType="DECIMAL(18,4)",
        Description="Cost based on enterprise customer negotiated contracted discount schedule prior to reservation application.",
        DerivationFormula="UsageQuantity * EnterpriseContractedRate.",
        NullStatePolicy="Preserves 4-state null discipline.",
        SampleValue="1368.0000",
    ),
    SemanticDataDictionaryField(
        TableName="FactCostAndUsage",
        ColumnName="RealisedDiscountAmount",
        BusinessName="Realised Discount Value",
        DataType="DECIMAL(18,4)",
        Description="Total financial benefit achieved across enterprise discount plans and commitment vehicles.",
        DerivationFormula="ListCostAmount - EffectiveCostAmount.",
        NullStatePolicy="Calculated; 0.00 if ListCost equals EffectiveCost.",
        SampleValue="504.8000",
    ),
    SemanticDataDictionaryField(
        TableName="FactCostAndUsage",
        ColumnName="BudgetAmount",
        BusinessName="Target Budget Allocation",
        DataType="DECIMAL(18,4)",
        Description="Pro-rated approved fiscal budget allocated to this organizational scope and period.",
        DerivationFormula="Master Data approved budget envelope apportionment.",
        NullStatePolicy="0.00 if unbudgeted.",
        SampleValue="1000.0000",
    ),
    SemanticDataDictionaryField(
        TableName="FactCostAndUsage",
        ColumnName="BudgetVarianceAmount",
        BusinessName="Budget Spend Variance",
        DataType="DECIMAL(18,4)",
        Description="Absolute monetary deviation from allocated budget. Positive indicates over-budget breach; negative indicates surplus.",
        DerivationFormula="BilledCostAmount - BudgetAmount.",
        NullStatePolicy="Calculated metric.",
        SampleValue="245.5000",
    ),
    SemanticDataDictionaryField(
        TableName="FactCostAndUsage",
        ColumnName="BudgetUtilisationPercentage",
        BusinessName="Budget Consumption %",
        DataType="DECIMAL(7,2)",
        Description="Percentage of approved budget consumed during the period.",
        DerivationFormula="(BilledCostAmount / BudgetAmount) * 100.",
        NullStatePolicy="0.00 if BudgetAmount is 0.00.",
        SampleValue="124.55",
    ),
    SemanticDataDictionaryField(
        TableName="FactCostAndUsage",
        ColumnName="SpendForecastAmount",
        BusinessName="Spend Forecast Amount",
        DataType="DECIMAL(18,4)",
        Description="Statistically projected total period spend combining current run-rate, day-of-week seasonality, and trend regression.",
        DerivationFormula="Linear trend regression + seasonal coefficient applied to period boundary.",
        NullStatePolicy="Preserves NO_DATA if historical points insufficient (<14 days).",
        SampleValue="1290.0000",
    ),
    SemanticDataDictionaryField(
        TableName="FactCostAndUsage",
        ColumnName="UnallocatedCostAmount",
        BusinessName="Unallocated Shared Spend",
        DataType="DECIMAL(18,4)",
        Description="Cost portion of multi-tenant shared infrastructure not yet attributed to a specific consumer application or business unit.",
        DerivationFormula="TotalSharedServiceCost - SumOfAttributedConsumerShares.",
        NullStatePolicy="0.00 if 100% allocated.",
        SampleValue="0.0000",
    ),
    SemanticDataDictionaryField(
        TableName="FactCostAndUsage",
        ColumnName="AllocatedCostAmount",
        BusinessName="Attributed Cost Share",
        DataType="DECIMAL(18,4)",
        Description="Portion of cost attributed to the receiving business unit via proportionate consumption or fixed percentage allocation rules.",
        DerivationFormula="AttributionRulePercentage * SourcePoolBilledCost.",
        NullStatePolicy="Equal to BilledCostAmount for directly owned single-tenant assets.",
        SampleValue="1245.5000",
    ),
    SemanticDataDictionaryField(
        TableName="FactCostAndUsage",
        ColumnName="EstimatedCostAmount",
        BusinessName="Pre-Deployment Estimated Cost",
        DataType="DECIMAL(18,4)",
        Description="Architectural estimation or provisioning quotation established prior to resource deployment.",
        DerivationFormula="Quotation catalog rate * requested provisioning spec.",
        NullStatePolicy="NOT_APPLICABLE if resource was deployed without pre-approval estimate.",
        SampleValue="1200.0000",
    ),
    SemanticDataDictionaryField(
        TableName="FactCostAndUsage",
        ColumnName="ReconciliationVarianceAmount",
        BusinessName="Invoice Reconciliation Variance",
        DataType="DECIMAL(18,4)",
        Description="Variance between final closed-period provider invoice total and normalized ingested platform facts.",
        DerivationFormula="AuthoritativeProviderInvoiceTotal - NormalizedCostFactSum.",
        NullStatePolicy="0.00 if balanced within strict zero-tolerance threshold.",
        SampleValue="0.0000",
    ),
    SemanticDataDictionaryField(
        TableName="FactCostAndUsage",
        ColumnName="UsageQuantity",
        BusinessName="Consumable Usage Quantity",
        DataType="DECIMAL(18,6)",
        Description="Measured physical or virtual consumption quantity in the standard pricing unit.",
        NullStatePolicy="Preserves 4-state null discipline via UsageQuantityNullState.",
        SampleValue="720.000000",
    ),
    SemanticDataDictionaryField(
        TableName="FactCostAndUsage",
        ColumnName="BilledCostNullState",
        BusinessName="Billed Cost Data Quality State",
        DataType="STRING (ENUM)",
        Description="Explicit data quality state distinguishing verified zeros from missing data or inapplicable metrics.",
        NullStatePolicy="VALUE_PRESENT, ZERO (genuine 0.00), NO_DATA (missing ingestion), NOT_APPLICABLE, NOT_SUPPORTED.",
        SampleValue="VALUE_PRESENT",
    ),
    SemanticDataDictionaryField(
        TableName="FactCostAndUsage",
        ColumnName="ProviderFreshnessTimestamp",
        BusinessName="Data Freshness Timestamp",
        DataType="STRING (ISO-8601 UTC)",
        Description="The newest ingestion or metering timestamp processed from the cloud provider at generation time.",
        NullStatePolicy="Mandatory (Non-null)",
        SampleValue="2026-09-30T23:59:59Z",
    ),
    SemanticDataDictionaryField(
        TableName="FactCostAndUsage",
        ColumnName="IsRestated",
        BusinessName="Restatement Indicator Flag",
        DataType="BOOLEAN",
        Description="True if this row represents a restated, amended, or retroactively corrected period invoice.",
        NullStatePolicy="Mandatory boolean (False by default)",
        SampleValue="false",
    ),
    # --------------------------------------------------------------------------
    # Conformed Dimensions
    # --------------------------------------------------------------------------
    SemanticDataDictionaryField(
        TableName="DimDate",
        ColumnName="FiscalPeriod",
        BusinessName="Fiscal Accounting Period",
        DataType="STRING",
        Description="Corporate fiscal month code, e.g. FP09 (September in a Jan-Dec fiscal year).",
        NullStatePolicy="Mandatory (Non-null)",
        SampleValue="FP09",
    ),
    SemanticDataDictionaryField(
        TableName="DimScope",
        ColumnName="HierarchyPath",
        BusinessName="Materialized Scope Path",
        DataType="STRING",
        Description="Full hierarchical enterprise tree path from root organization to current leaf scope.",
        NullStatePolicy="Mandatory (Non-null)",
        SampleValue="/Global/Retail/Production/E-Commerce",
    ),
    SemanticDataDictionaryField(
        TableName="DimBusinessUnit",
        ColumnName="BusinessUnitName",
        BusinessName="Business Unit Name",
        DataType="STRING",
        Description="Executive business division title used in financial management reporting packs.",
        NullStatePolicy="Mandatory (Non-null)",
        SampleValue="Global Retail & Digital Channels",
    ),
    SemanticDataDictionaryField(
        TableName="DimCostCentre",
        ColumnName="CostCentreCode",
        BusinessName="General Ledger Cost Centre",
        DataType="STRING",
        Description="Authoritative ERP or General Ledger cost centre code.",
        NullStatePolicy="Mandatory (Non-null)",
        SampleValue="CC-1040",
    ),
    SemanticDataDictionaryField(
        TableName="DimApplication",
        ColumnName="CriticalityTier",
        BusinessName="Application Tier",
        DataType="STRING",
        Description="Operational SLA and financial criticality ranking of the business application.",
        NullStatePolicy="TIER_1_MISSION_CRITICAL, TIER_2_BUSINESS_CRITICAL, TIER_3_SUPPORT.",
        SampleValue="TIER_1_MISSION_CRITICAL",
    ),
    SemanticDataDictionaryField(
        TableName="DimPricing",
        ColumnName="PricingCategory",
        BusinessName="Pricing Model Classification",
        DataType="STRING",
        Description="Classification of the charging mechanism: ON_DEMAND, RESERVED, SPOT, SAVINGS_PLAN.",
        NullStatePolicy="Mandatory (Non-null)",
        SampleValue="ON_DEMAND",
    ),
]


def get_semantic_data_dictionary() -> list[SemanticDataDictionaryField]:
    """Returns the full list of data dictionary entries."""
    return MASTER_DATA_DICTIONARY


def generate_markdown_data_dictionary() -> str:
    """Renders human-readable markdown table documentation of the data dictionary."""
    lines = [
        "# CloudLens Semantic Layer Data Dictionary (Prompt 56 / BBP Section 39)",
        "",
        "| Table Name | Business Name | Technical Column | Data Type | Derivation / Formula | Null State Policy |",
        "| :--- | :--- | :--- | :--- | :--- | :--- |",
    ]
    for entry in MASTER_DATA_DICTIONARY:
        formula = entry.DerivationFormula or "Direct Mapping"
        lines.append(
            f"| `{entry.TableName}` | **{entry.BusinessName}** | `{entry.ColumnName}` | `{entry.DataType}` | {formula} | {entry.NullStatePolicy} |"
        )
    return "\n".join(lines) + "\n"
