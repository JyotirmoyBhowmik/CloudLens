# Microsoft Azure Connector Research Note (Prompt 16)

> **Connector**: Microsoft Azure Cloud Connector (`connectors/azure`)  
> **Authoritative Specification**: BBP Section 14.2 (Azure capabilities and cautions), Section 15.4 (mapping rules)  
> **Status**: Completed & Verified Against Official Microsoft REST API Documentation  
> **Security Baseline**: Read-only, Least Privilege (SEC-012, SEC-016)

---

## 1. Official Documentation Index & API Version Matrix

| Functional Domain | Official Microsoft Document Title | Target Endpoint / URI Pattern | API / Schema Version | Verified Behavior & Notes |
| :--- | :--- | :--- | :--- | :--- |
| **Authentication & Tokens** | *Microsoft identity platform and OAuth 2.0 client credentials flow* | `POST https://login.microsoftonline.com/{tenantId}/oauth2/v2.0/token` | OAuth 2.0 / RFC 7523 | Supports certificate-based assertion (`client_assertion_type=jwt-bearer`), Workload Identity Federation (OIDC exchange), Managed Identity (IMDS `api-version=2018-02-01`), and audited Client Secret. **Interactive user passwords strictly forbidden**. |
| **Hierarchy — Management Groups** | *Management Groups - Get & Get Descendants (Azure Resource Management)* | `GET https://management.azure.com/providers/Microsoft.Management/managementGroups/{groupId}?$expand=children`<br>`GET https://management.azure.com/providers/Microsoft.Management/managementGroups/{groupId}/descendants` | `2020-05-01` | Returns hierarchy tree with parent-child links. Used to assemble single-pass canonical scope tree with ancestor chains. |
| **Hierarchy — Subscriptions** | *Subscriptions - List & Get (Azure Resource Management)* | `GET https://management.azure.com/subscriptions`<br>`GET https://management.azure.com/subscriptions/{subscriptionId}` | `2020-01-01`<br>`2022-12-01` | Enumerates subscriptions under tenant. Captures state (`Enabled`, `Warned`, `PastDue`, `Disabled`) and parent management group linkage. |
| **Resource Inventory** | *Resources - Query via Azure Resource Graph (Resource Graph)* | `POST https://management.azure.com/providers/Microsoft.ResourceGraph/resources` | `2022-10-01` | Primary cross-subscription inventory source using Kusto queries (`Resources \| project id, name, type, location, tags, properties`). **Caveat**: Eventually consistent; data is indexed with latency and must not be treated as strongly consistent real-time authority. |
| **Cost Ingestion — Bulk Exports** | *Exports - Create, Update, Get & Execute (Cost Management)* | `GET/POST https://management.azure.com/{scope}/providers/Microsoft.CostManagement/exports/{exportName}` | `2023-03-01`<br>`2023-07-01-preview` (FOCUS 1.0) | Default ingestion path. Delivers scheduled bulk files (CSV/Parquet) to Azure Blob Storage container (`Microsoft.Storage/storageAccounts/blobServices/containers/blobs`). Supports FOCUS 1.0 format (`FocusCost`) and legacy `ActualCost`/`AmortizedCost`. |
| **Cost Ingestion — Query Fallback** | *Query - Usage (Cost Management)* | `POST https://management.azure.com/{scope}/providers/Microsoft.CostManagement/query` | `2023-03-01` | Interactive and fallback ingestion path. Requires automatic agreement-type detection (`EA`, `MCA`, `MPA`, `DIRECT`) to construct valid scope paths. Mismatched scope forms result in HTTP 400 bad request. |
| **Pricing — Retail List Rates** | *Azure Retail Prices REST API Overview* | `GET https://prices.azure.com/api/retail/prices?$filter=serviceName eq '{service}' and armRegionName eq '{region}'` | `2023-01-01-preview` / Unauthenticated | Publicly accessible rate card interface. All rates denominated in USD with reference conversions. Must be explicitly flagged as `is_retail=True`. Never present retail rates as actual local-currency costs when negotiated sheets exist. |
| **Pricing — Negotiated Price Sheets** | *Price Sheet - Get By Billing Profile & List (Billing & Consumption)* | `POST https://management.azure.com/providers/Microsoft.Billing/billingAccounts/{ba}/billingProfiles/{bp}/pricesheet/default/download`<br>`GET https://management.azure.com/providers/Microsoft.Billing/billingAccounts/{ba}/priceSheets/default` | `2023-05-01` (MCA)<br>`2019-10-01` (EA)<br>`2021-10-01` (Consumption) | Negotiated customer rate card. Takes precedence over retail pricing when tenant is entitled to enterprise discounts. |
| **Budgets** | *Budgets - List (Cost Management)* | `GET https://management.azure.com/{scope}/providers/Microsoft.CostManagement/budgets` | `2023-03-01` | Read for comparison and variance analysis only; **never authoritative** inside CloudLens. |
| **Usage Telemetry & Metrics** | *Metrics - List (Azure Monitor)* | `GET https://management.azure.com/{resourceId}/providers/Microsoft.Insights/metrics?interval=PT1H` | `2018-01-01` | Collects coarse aggregates (hourly `PT1H`, daily `P1D`). Sub-minute intervals are strictly rejected. |
| **Tag Collections** | *Tags - List At Scope (Azure Resource Management)* | `GET https://management.azure.com/{scope}/providers/Microsoft.Resources/tags/default` | `2021-04-01` | Evaluates tags across resource, resource group, and subscription levels. Records `tag_level` explicitly because Azure does not automatically cascade tags across scopes. |
| **Relationships & Topology** | *Resource Graph structural properties extraction* | `POST https://management.azure.com/providers/Microsoft.ResourceGraph/resources` | `2022-10-01` | Derives structural bindings (NICs, OS/data disks, parent-child, `managedBy`). Capability declared as **PARTIAL** because dynamic network flow routing is not evaluated. |
| **Quota & Limits** | *Azure Quotas REST API* | `GET https://management.azure.com/subscriptions/{subId}/providers/Microsoft.Quota/quotas` | `2023-02-01` | Gathers regional core and compute service limits for AM-07 headroom monitoring. |

---

## 2. Agreement Types & Scope-Form Matrix

Azure Cost Management requires strictly formatted scope URIs matching the enterprise billing agreement. A mismatch between agreement type and scope URI produces an immediate API failure.

| Billing Agreement Type | Agreement Code | Supported Cost Management Scope Forms | Prohibited / Invalid Scope Forms |
| :--- | :--- | :--- | :--- |
| **Enterprise Agreement** | `EA` | • `/providers/Microsoft.Billing/billingAccounts/{enrollmentNumber}`<br>• `/providers/Microsoft.Billing/billingAccounts/{ba}/departments/{deptId}`<br>• `/providers/Microsoft.Billing/billingAccounts/{ba}/enrollmentAccounts/{accId}`<br>• `/subscriptions/{subscriptionId}`<br>• `/providers/Microsoft.Management/managementGroups/{mgId}` | ✗ `billingProfiles` (MCA only)<br>✗ `invoiceSections` (MCA only)<br>✗ `customers` (MPA only) |
| **Microsoft Customer Agreement** | `MCA` | • `/providers/Microsoft.Billing/billingAccounts/{billingAccountId}`<br>• `/providers/Microsoft.Billing/billingAccounts/{ba}/billingProfiles/{bpId}`<br>• `/providers/Microsoft.Billing/billingAccounts/{ba}/billingProfiles/{bpId}/invoiceSections/{invSecId}`<br>• `/subscriptions/{subscriptionId}`<br>• `/providers/Microsoft.Management/managementGroups/{mgId}` | ✗ `enrollmentAccounts` (EA only)<br>✗ `departments` (EA only)<br>✗ `customers` (MPA only) |
| **Microsoft Partner Agreement** | `MPA` | • `/providers/Microsoft.Billing/billingAccounts/{ba}/customers/{custId}`<br>• `/subscriptions/{subscriptionId}` | ✗ `departments` (EA only)<br>✗ `enrollmentAccounts` (EA only) |
| **Direct / Modern Web Direct** | `DIRECT` | • `/subscriptions/{subscriptionId}`<br>• `/subscriptions/{subscriptionId}/resourceGroups/{rgName}` | ✗ `billingAccounts` (EA/MCA only)<br>✗ `billingProfiles` (MCA only) |

---

## 3. Explicit Provider Caveats & Gaps

1. **Azure Resource Graph Latency & Eventual Consistency**:
   - Resource Graph data is updated asynchronously as ARM events propagate into indexing stores.
   - Resource state may lag changes made in the Azure Portal or ARM REST APIs by minutes to hours under platform backpressure.
   - **Enforcement**: Freshness indicators are flagged with `is_strongly_consistent=False`, and the UI/API response explicitly communicates this caveat to prevent misinterpretation as real-time state.

2. **Tag Inheritance Non-Propagation**:
   - Tags applied to an Azure Subscription or Resource Group do **not** inherit to child resources automatically in Azure native metadata.
   - **Enforcement**: Tags are collected and indexed with their source tier (`resource`, `resource_group`, `subscription`) recorded in `metadata["tag_level"]`.

3. **Unsupported Subscription Offer Types (Capability Gap Handling)**:
   - Specific subscription categories (e.g. Free Trial `MS-AZR-0044P`, Azure in Open, Sponsorships, Developer MSDN) do not support Cost Management Scheduled Exports or the Query API.
   - **Enforcement**: When an unsupported offer type is detected, the connector marks `COLLECT_COST_BULK` and `COLLECT_COST_QUERY` as degraded/unavailable for that scope, providing a clear explanatory diagnostic rather than throwing system errors.

4. **Pricing Precedence**:
   - Azure Retail Prices are unauthenticated and published in USD.
   - An organization with an EA or MCA agreement is entitled to negotiated discount sheets.
   - **Enforcement**: If a Price Sheet is available, the connector binds and reports negotiated rates; retail rates are only returned for non-entitled scopes and are strictly labeled as retail estimates.
