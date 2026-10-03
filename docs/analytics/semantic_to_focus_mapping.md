# CloudLens Semantic Layer to FinOps FOCUS 1.0 Mapping (Prompt 56 Reference Artefact 2)

> **Specification Standard**: FinOps Open Cost and Usage Specification (FOCUS) v1.0  
> **Source Model**: CloudLens Semantic Layer (`FactCostAndUsage` & Conformed Dimensions)  
> **Purpose**: Enables organizations fluent in FOCUS 1.0 to consume CloudLens feeds immediately with zero translation overhead.

---

## 1. Primary Fact & Metric Mappings

| CloudLens Semantic Layer Field | FinOps FOCUS 1.0 Column Name | FOCUS Requirement Level | Business Description & Semantic Notes |
| :--- | :--- | :--- | :--- |
| `BilledCostAmount` | `BilledCost` | **Mandatory** | The charge amount invoiced by the service provider, reflecting final payable amounts. |
| `EffectiveCostAmount` | `EffectiveCost` | **Mandatory** | Amortised cost of usage, allocating upfront/recurring commitment purchases and blended discounts. |
| `ListCostAmount` | `ListCost` | **Recommended** | Published catalog retail cost before any customer-specific discounts or promotions. |
| `ContractedCostAmount` | `ContractedCost` | **Recommended** | Cost calculated based on customer negotiated contracted rates prior to commitment vehicles. |
| `RealisedDiscountAmount` | `CommitmentDiscountSavings` | **Optional** | Financial savings realized: `ListCost - EffectiveCost`. |
| `Currency` | `BillingCurrency` | **Mandatory** | Standard ISO 4217 three-letter currency code (e.g. `USD`, `EUR`, `GBP`). |
| `UsageQuantity` | `UsageQuantity` | **Mandatory** | Quantified usage volume (e.g. hours, gigabytes, API invocations). |
| `ChargePeriod` (start) | `ChargePeriodStart` | **Mandatory** | UTC start timestamp of the consumed service interval. |
| `ChargePeriod` (end) | `ChargePeriodEnd` | **Mandatory** | UTC end timestamp of the consumed service interval. |

---

## 2. Dimensional & Entity Mappings

| CloudLens Semantic Layer Field | FinOps FOCUS 1.0 Column Name | FOCUS Requirement Level | Dimension Alignment |
| :--- | :--- | :--- | :--- |
| `ProviderKey` | `ProviderName` | **Mandatory** | `DimProvider` (`AWS`, `AZURE`, `GCP`, `OCI`). |
| `ProviderAccountId` | `BillingAccountId` | **Mandatory** | `DimProvider` (Root billing account identifier). |
| `ScopeKey` | `SubAccountId` | **Mandatory** | `DimScope` (Linked account, subscription, or project identifier). |
| `ScopeName` | `SubAccountName` | **Recommended** | `DimScope` (Human-readable sub-account name). |
| `ServiceName` | `ServiceName` | **Mandatory** | `DimService` (Canonical service title, e.g. Amazon Elastic Compute Cloud). |
| `ServiceCategory` | `ServiceCategory` | **Mandatory** | `DimService` (Standard taxonomy: Compute, Storage, Database, Networking). |
| `ResourceIdentifier` | `ResourceId` | **Mandatory** | `DimResource` (Unique canonical resource URI or ARN). |
| `ResourceName` | `ResourceName` | **Recommended** | `DimResource` (User-assigned name or tag name). |
| `RegionIdentifier` | `RegionId` | **Mandatory** | `DimRegion` (Cloud provider region identifier, e.g. `us-east-1`). |
| `RegionKey` | `RegionName` | **Optional** | `DimRegion` (Geographic region title). |
| `AvailabilityZone` | `AvailabilityZone` | **Optional** | `DimResource` (Physical data centre zone identifier). |
| `ChargeCategoryKey` | `ChargeCategory` | **Mandatory** | `DimChargeCategory` (`Usage`, `Purchase`, `Credit`, `Tax`, `Refund`). |
| `ChargeSubCategory` | `ChargeSubcategory` | **Optional** | `DimChargeCategory` (`OnDemand`, `AmortisedCommitment`). |
| `PricingKey` | `PricingCategory` | **Mandatory** | `DimPricing` (`Standard`, `Spot`, `Tiered`). |
| `CommitmentIdentifier` | `CommitmentDiscountId` | **Optional** | `DimCommitment` (Reservation or Savings Plan ID). |
| `CommitmentType` | `CommitmentDiscountCategory` | **Optional** | `DimCommitment` (`ReservedInstance`, `SavingsPlan`, `CUD`). |
| `TagKey` / `TagValue` | `Tags` | **Recommended** | `DimTag` (Serialized JSON dictionary of allocated tags). |

---

## 3. Four-State Null Discipline in FOCUS Ingestion Feeds

CloudLens guarantees that missing values in FOCUS columns are never ambiguous:

1. **`ZERO`**: Represented as numeric `0.0000` with companion metadata flag `BilledCostNullState: "ZERO"`. Represents verified zero-dollar consumption (e.g. Always Free Tier).
2. **`NO_DATA`**: Telemetry gap. Distinguishable from zero to prevent misleading billing variance calculations.
3. **`NOT_APPLICABLE`**: Dimension does not apply to this service type (e.g. `AvailabilityZone` on a serverless global queue).
4. **`NOT_SUPPORTED`**: Cloud provider API does not export this field.

---

## 4. Supersession & Partition Loading Rules

When consuming CloudLens analytics extracts:
- Each period folder is versioned: `/period=YYYY-MM/v{N}/`
- Consumers must select `MAX(version)` for each `(tenant_id, period)`.
- Restated extracts include `supersedes_version: N-1` in `manifest.json`.
- Consumers **must drop and replace** the period partition upon receiving a higher version.
