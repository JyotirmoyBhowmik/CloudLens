# CloudLens Reference Monthly Cost Pack (Prompt 56 Reference Artefact 1)

> **Document Type**: Reference Executive BI Reporting Pack  
> **Source Model**: CloudLens Semantic Layer Star-Schema (`FactCostAndUsage`)  
> **Target Audience**: Chief Financial Officer (CFO), VP of Infrastructure, FinOps Steering Committee  
> **Primary Rule**: 100% derived from the conformed Semantic Layer without any reference to the application database.

---

## 1. Executive Summary & Financial Headline Metrics

| Financial Measure | Current Period (2026-09) | Budget Target | Budget Variance | Discount Realisation |
| :--- | :--- | :--- | :--- | :--- |
| **Total Cloud Spend** | **$7,140.50** | **$7,300.00** | **-$159.50 (Favourable)** | **$1,780.00** |
| **Effective Amortised Spend** | **$6,110.20** | - | - | - |
| **Undiscounted List Value** | **$8,850.00** | - | - | - |
| **Overall Discount Yield** | **20.1%** | - | - | - |

> [!NOTE]
> All figures above represent pre-computed derived measures from `FactCostAndUsage`. Zero manual calculations or external aggregations were performed.

---

## 2. Spend by Business Unit (Pre-Aggregated Conformed View)

| Business Unit (`DimBusinessUnit`) | Billed Cost (`BilledCostAmount`) | Effective Cost (`EffectiveCostAmount`) | Budget (`BudgetAmount`) | Variance (`BudgetVarianceAmount`) | Budget % (`BudgetUtilisationPercentage`) |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **BU-RETAIL** (Global Retail & Digital Channels) | $1,250.50 | $1,050.20 | $1,000.00 | +$250.50 | 125.1% |
| **BU-ANALYTICS** (Data Platform & AI) | $2,100.00 | $1,850.00 | $2,500.00 | -$400.00 | 84.0% |
| **BU-SHARED** (Shared Kubernetes Infrastructure) | $1,500.00 | $1,500.00 | $1,400.00 | +$100.00 | 107.1% |
| **BU-INFRA** (Core Foundation & Operations) | $1,290.00 | $1,160.00 | $1,400.00 | -$110.00 | 92.1% |
| **Dev / Sandboxes** | $0.00 *(ZERO)* | $0.00 | $100.00 | -$100.00 | 0.0% |

---

## 3. Multi-Cloud Provider Cost Comparison & Realised Discounts

| Cloud Provider (`DimProvider`) | Invoiced Spend (`BilledCostAmount`) | Public Retail Value (`ListCostAmount`) | Realised Discounts (`RealisedDiscountAmount`) | Savings % |
| :--- | :--- | :--- | :--- | :--- |
| **Amazon Web Services (AWS)** | $2,750.50 | $3,300.00 | $549.50 | 16.7% |
| **Microsoft Azure** | $840.00 | $1,050.00 | $210.00 | 20.0% |
| **Google Cloud Platform (GCP)** | $2,100.00 | $2,500.00 | $400.00 | 16.0% |
| **Oracle Cloud (OCI)** | $450.00 | $500.00 | $50.00 | 10.0% |

---

## 4. Shared Service Allocation & Unallocated Spend Transparency

- **Total Shared Service Pool (`BU-SHARED`)**: $1,500.00
- **Attributed by Consumption Rules (`AllocatedCostAmount`)**: $1,200.00 (80%)
  - Attributed to BU-RETAIL: $720.00
  - Attributed to BU-ANALYTICS: $480.00
- **Unallocated Shared Pool (`UnallocatedCostAmount`)**: $300.00 (20%)
  - *Governance Note*: Pending ownership attribution update for telemetry gap cluster namespace.

---

## 5. Governance & Data Quality Provenance Disclosure

- **Per-Provider Telemetry Freshness**:
  - AWS: `2026-09-30T23:59:59Z`
  - Azure: `2026-09-30T23:55:00Z`
  - GCP: `2026-09-30T23:45:00Z`
  - OCI: `2026-09-30T23:30:00Z`
- **Cost Basis Applied**: `BILLED` (Standard accounting invoice recognition)
- **Currency Policy**: Consolidated in `USD` at ECB mid-market closing rate.
- **Null State Discipline**:
  - The Dev Sandbox environment spend is verified as **`ZERO`** (genuine $0.00 consumption under free-tier allowance), distinctly separated from **`NO_DATA`** (missing provider billing files).
