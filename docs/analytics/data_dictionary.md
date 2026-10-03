# CloudLens Semantic Layer Data Dictionary (Prompt 56 / BBP Section 39)

> **Document Type**: Authoritative Business Data Dictionary  
> **Source Model**: CloudLens Semantic Layer (`FactCostAndUsage` & Conformed Dimensions)  
> **Target Audience**: Data Engineers, BI Developers, Financial Analysts  

---

| Table Name | Business Name | Technical Column | Data Type | Derivation / Formula | Null State Policy |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `FactCostAndUsage` | **Fact Record Key** | `FactKey` | `STRING (UUID)` | Direct Mapping | Mandatory (Non-null) |
| `FactCostAndUsage` | **Billing Period** | `ChargePeriod` | `STRING (YYYY-MM)` | Direct Mapping | Mandatory (Non-null) |
| `FactCostAndUsage` | **Billed Cost Amount** | `BilledCostAmount` | `DECIMAL(18,4)` | Direct sum of invoiced line item charge amounts converted to presentation currency. | Preserves 4-state null discipline via BilledCostNullState (never flattened). |
| `FactCostAndUsage` | **Effective Cost Amount** | `EffectiveCostAmount` | `DECIMAL(18,4)` | BilledCostAmount + AmortisedUpfrontCommitmentShare - RealisedDiscountAdjustment. | Preserves 4-state null discipline. |
| `FactCostAndUsage` | **List / Retail Cost Amount** | `ListCostAmount` | `DECIMAL(18,4)` | UsageQuantity * PublishedPublicCatalogOnDemandRate. | Preserves 4-state null discipline. |
| `FactCostAndUsage` | **Contracted Enterprise Cost** | `ContractedCostAmount` | `DECIMAL(18,4)` | UsageQuantity * EnterpriseContractedRate. | Preserves 4-state null discipline. |
| `FactCostAndUsage` | **Realised Discount Value** | `RealisedDiscountAmount` | `DECIMAL(18,4)` | ListCostAmount - EffectiveCostAmount. | Calculated; 0.00 if ListCost equals EffectiveCost. |
| `FactCostAndUsage` | **Target Budget Allocation** | `BudgetAmount` | `DECIMAL(18,4)` | Master Data approved budget envelope apportionment. | 0.00 if unbudgeted. |
| `FactCostAndUsage` | **Budget Spend Variance** | `BudgetVarianceAmount` | `DECIMAL(18,4)` | BilledCostAmount - BudgetAmount. | Calculated metric. |
| `FactCostAndUsage` | **Budget Consumption %** | `BudgetUtilisationPercentage` | `DECIMAL(7,2)` | (BilledCostAmount / BudgetAmount) * 100. | 0.00 if BudgetAmount is 0.00. |
| `FactCostAndUsage` | **Spend Forecast Amount** | `SpendForecastAmount` | `DECIMAL(18,4)` | Linear trend regression + seasonal coefficient applied to period boundary. | Preserves NO_DATA if historical points insufficient (<14 days). |
| `FactCostAndUsage` | **Unallocated Shared Spend** | `UnallocatedCostAmount` | `DECIMAL(18,4)` | TotalSharedServiceCost - SumOfAttributedConsumerShares. | 0.00 if 100% allocated. |
| `FactCostAndUsage` | **Attributed Cost Share** | `AllocatedCostAmount` | `DECIMAL(18,4)` | AttributionRulePercentage * SourcePoolBilledCost. | Equal to BilledCostAmount for directly owned single-tenant assets. |
| `FactCostAndUsage` | **Pre-Deployment Estimated Cost** | `EstimatedCostAmount` | `DECIMAL(18,4)` | Quotation catalog rate * requested provisioning spec. | NOT_APPLICABLE if resource was deployed without pre-approval estimate. |
| `FactCostAndUsage` | **Invoice Reconciliation Variance** | `ReconciliationVarianceAmount` | `DECIMAL(18,4)` | AuthoritativeProviderInvoiceTotal - NormalizedCostFactSum. | 0.00 if balanced within strict zero-tolerance threshold. |
| `FactCostAndUsage` | **Consumable Usage Quantity** | `UsageQuantity` | `DECIMAL(18,6)` | Direct Mapping | Preserves 4-state null discipline via UsageQuantityNullState. |
| `FactCostAndUsage` | **Billed Cost Data Quality State** | `BilledCostNullState` | `STRING (ENUM)` | Direct Mapping | VALUE_PRESENT, ZERO (genuine 0.00), NO_DATA (missing ingestion), NOT_APPLICABLE, NOT_SUPPORTED. |
| `FactCostAndUsage` | **Data Freshness Timestamp** | `ProviderFreshnessTimestamp` | `STRING (ISO-8601 UTC)` | Direct Mapping | Mandatory (Non-null) |
| `FactCostAndUsage` | **Restatement Indicator Flag** | `IsRestated` | `BOOLEAN` | Direct Mapping | Mandatory boolean (False by default) |
| `DimDate` | **Fiscal Accounting Period** | `FiscalPeriod` | `STRING` | Direct Mapping | Mandatory (Non-null) |
| `DimScope` | **Materialized Scope Path** | `HierarchyPath` | `STRING` | Direct Mapping | Mandatory (Non-null) |
| `DimBusinessUnit` | **Business Unit Name** | `BusinessUnitName` | `STRING` | Direct Mapping | Mandatory (Non-null) |
| `DimCostCentre` | **General Ledger Cost Centre** | `CostCentreCode` | `STRING` | Direct Mapping | Mandatory (Non-null) |
| `DimApplication` | **Application Tier** | `CriticalityTier` | `STRING` | Direct Mapping | TIER_1_MISSION_CRITICAL, TIER_2_BUSINESS_CRITICAL, TIER_3_SUPPORT. |
| `DimPricing` | **Pricing Model Classification** | `PricingCategory` | `STRING` | Direct Mapping | Mandatory (Non-null) |
