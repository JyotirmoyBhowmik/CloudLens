# CloudLens Enterprise Data Dictionary

> **Status**: Approved Production Specification (Prompt 05 / Stage 1)  
> **Standards Alignment**: FinOps Open Cost & Usage Specification (FOCUS) v1.0 & BBP Section 39  
> **Four-State Null Discipline**: Bare nulls banned on all numeric measures (`NO_COST`, `NO_DATA`, `NOT_APPLICABLE`, `NOT_SUPPORTED`).

---

## 1. Governance & Provenance Conventions

Every entity and attribute in the CloudLens canonical schema is classified by its **Origin**:
1. **DISCOVERED**: Sourced directly from cloud provider APIs, billing exports, or resource telemetry without manual alteration.
2. **DERIVED**: Computed or calculated by CloudLens business rules (e.g. FOCUS effective cost amortisation, materialized hierarchy paths, health status).
3. **CURATED**: Manually entered or updated by enterprise FinOps architects, application owners, or administrators (e.g. budgets, cost center tags, policy thresholds).

The **Survives Re-Discovery** column specifies whether subsequent automated connector discovery runs will preserve the value (`Yes`) or overwrite it with fresh provider data (`No`).

---

## 2. Canonical Data Dictionary

### 2.1 Scope & Hierarchy (`scopes`, `scope_history`)

| Entity | Attribute | Data Type | Nullability / Measure | Origin | Survives Re-Discovery | Description |
|:---|:---|:---|:---:|:---:|:---:|:---|
| `Scope` | `id` | UUID / String | Not Null | DERIVED | Yes | Globally unique canonical scope identifier. |
| `Scope` | `tenant_id` | String | Not Null | CURATED | Yes | Multi-tenant organization boundary. |
| `Scope` | `name` | String | Not Null | DISCOVERED | Yes | Scope title (e.g. 'Core-Services-MG', 'Prod-Workloads-OU'). |
| `Scope` | `canonical_role` | Enum (`ScopeRole`) | Not Null | DERIVED | Yes | Canonical classification: `TENANT`, `ROOT_GROUP`, `GROUP`, `BILLING_BOUNDARY`, `SUB_GROUP`, `BILLING_ACCOUNT`. |
| `Scope` | `provider` | Enum (`ProviderType`) | Not Null | DISCOVERED | Yes | Cloud provider (`aws`, `azure`, `gcp`, `oci`, `canonical`). |
| `Scope` | `native_type` | String | Not Null | DISCOVERED | Yes | Verbatim native type name (e.g. `ManagementGroup`, `OrganizationalUnit`, `Folder`, `Compartment`). |
| `Scope` | `native_id` | String | Not Null | DISCOVERED | Yes | Verbatim provider identifier (ARN, OCID, Subscription ID, Project ID). |
| `Scope` | `parent_id` | UUID / String | Nullable | DISCOVERED | Yes | Self-referencing tree parent scope identifier. |
| `Scope` | `materialized_path` | String | Not Null | DERIVED | Yes | Full materialized path lineage (e.g. `/<tenant>/<root>/<group>/<sub-id>`). |
| `Scope` | `depth` | Integer | Not Null | DERIVED | Yes | Hierarchy tree level (0 for root). |
| `Scope` | `is_sub_group_applicable` | Boolean | Not Null | DERIVED | Yes | Explicit flag for SUB_GROUP topology applicability (False for AWS & GCP). |
| `Scope` | `sub_group_absence_reason`| Enum (`ScopeAbsenceReason`)| Nullable | DERIVED | Yes | Valid absence state modeling (`NOT_APPLICABLE_TO_PROVIDER`). |
| `Scope` | `provider_native` | JSONB / Dict | Not Null | DISCOVERED | Yes | Raw provider payload fragment preserved verbatim without data loss. |
| `Scope` | `source_provenance` | Complex (`ProvenanceRecord`) | Not Null | DERIVED | Yes | Ingestion system, correlation ID, and discovery timestamp. |
| `Scope` | `created_at` | Timestamp (UTC) | Not Null | DERIVED | Yes | Record creation timestamp. |
| `Scope` | `updated_at` | Timestamp (UTC) | Not Null | DERIVED | Yes | Record modification timestamp. |
| `ScopeHistory` | `id` | UUID / String | Not Null | DERIVED | Yes | Unique SCD Type 2 history version identifier. |
| `ScopeHistory` | `scope_id` | UUID / String | Not Null | DERIVED | Yes | Target Scope entity ID. |
| `ScopeHistory` | `tenant_id` | String | Not Null | CURATED | Yes | Multi-tenant organization boundary. |
| `ScopeHistory` | `parent_scope_id` | UUID / String | Nullable | DERIVED | Yes | Parent scope ID in effect during this time window. |
| `ScopeHistory` | `materialized_path` | String | Not Null | DERIVED | Yes | Materialized lineage path in effect during this time window. |
| `ScopeHistory` | `canonical_role` | Enum (`ScopeRole`) | Not Null | DERIVED | Yes | Canonical role during validity window. |
| `ScopeHistory` | `native_id` | String | Not Null | DISCOVERED | Yes | Provider native identifier. |
| `ScopeHistory` | `native_type` | String | Not Null | DISCOVERED | Yes | Provider native type name. |
| `ScopeHistory` | `effective_from` | Timestamp (UTC) | Not Null | DERIVED | Yes | Start of historical validity window. |
| `ScopeHistory` | `effective_to` | Timestamp (UTC) | Nullable | DERIVED | Yes | End of historical validity window (Null indicates currently active). |
| `ScopeHistory` | `change_reason` | String | Not Null | DERIVED | Yes | Reason for change (`INITIAL_DISCOVERY`, `REPARENTED`, `CASCADE_REPARENTED`). |

---

### 2.2 Inventory & Resource Catalog

| Entity | Attribute | Data Type | Nullability / Measure | Origin | Survives Re-Discovery | Description |
|:---|:---|:---|:---:|:---:|:---:|:---|
| `Resource` | `id` | UUID / String | Not Null | DERIVED | Yes | Canonical unique resource identifier. |
| `Resource` | `tenant_id` | String | Not Null | CURATED | Yes | Organization tenant boundary. |
| `Resource` | `scope_id` | UUID / String | Not Null | DISCOVERED | Yes | Immediate parent billing boundary (Subscription, Account, Project). |
| `Resource` | `native_id` | String | Not Null | DISCOVERED | Yes | Verbatim cloud provider ID (ARN, URI, OCID). |
| `Resource` | `name` | String | Not Null | DISCOVERED | Yes | Resource instance name. |
| `Resource` | `provider` | Enum (`ProviderType`) | Not Null | DISCOVERED | Yes | Cloud provider (`aws`, `azure`, `gcp`, `oci`). |
| `Resource` | `service_id` | String | Not Null | DISCOVERED | Yes | Mapped Service ID. |
| `Resource` | `resource_type_id` | String | Not Null | DISCOVERED | Yes | Mapped ResourceType ID. |
| `Resource` | `region_id` | String | Not Null | DISCOVERED | Yes | Deployment region identifier. |
| `Resource` | `availability_zone` | String | Nullable | DISCOVERED | Yes | Availability zone (e.g. `us-east-1a`). |
| `Resource` | `pricing_status` | Enum (`PricingStatus`) | Not Null | DERIVED | Yes | Classification: `FREE`, `FREE_TIER`, `PAID`, `ESTIMATED`, etc. |
| `Resource` | `tags` | List[`Tag`] | Not Null | DISCOVERED | Yes | Array of resource key-value tags. |
| `Resource` | `application_id` | UUID / String | Nullable | CURATED | Yes | Accountable business application ID. |
| `Resource` | `environment_id` | UUID / String | Nullable | CURATED | Yes | Lifecycle environment ID (Prod, Staging). |
| `Resource` | `owner_id` | UUID / String | Nullable | CURATED | Yes | Accountable Owner ID. |
| `Resource` | `cost_center_id` | UUID / String | Nullable | CURATED | Yes | General ledger CostCenter ID. |
| `Resource` | `business_unit_id` | UUID / String | Nullable | CURATED | Yes | Sponsoring BusinessUnit ID. |
| `Resource` | `project_id` | UUID / String | Nullable | CURATED | Yes | Internal project initiative ID. |
| `ResourceType` | `id` | String | Not Null | DERIVED | Yes | Canonical resource type identifier. |
| `ResourceType` | `provider` | Enum (`ProviderType`) | Not Null | DISCOVERED | Yes | Cloud provider. |
| `ResourceType` | `service_id` | String | Not Null | DISCOVERED | Yes | Associated Service ID. |
| `ResourceType` | `native_type_name` | String | Not Null | DISCOVERED | Yes | Native resource type (e.g. `AWS::EC2::Instance`). |
| `ResourceType` | `canonical_type` | String | Not Null | DERIVED | Yes | Normalized type (e.g. `compute/virtual-machine`). |
| `ResourceType` | `service_category` | Enum (`ServiceCategory`) | Not Null | DERIVED | Yes | Functional category. |
| `Service` | `id` | String | Not Null | DERIVED | Yes | Canonical service identifier. |
| `Service` | `provider` | Enum (`ProviderType`) | Not Null | DISCOVERED | Yes | Cloud provider. |
| `Service` | `service_code` | String | Not Null | DISCOVERED | Yes | Provider service code (e.g. `AmazonEC2`, `Microsoft.Compute`). |
| `Service` | `name` | String | Not Null | DISCOVERED | Yes | Human-readable service name. |
| `Service` | `category` | Enum (`ServiceCategory`) | Not Null | DERIVED | Yes | Functional category. |
| `Region` | `id` | String | Not Null | DERIVED | Yes | Canonical region identifier (e.g. `us-east-1`). |
| `Region` | `provider` | Enum (`ProviderType`) | Not Null | DISCOVERED | Yes | Cloud provider. |
| `Region` | `native_name` | String | Not Null | DISCOVERED | Yes | Native region code. |
| `Region` | `display_name` | String | Not Null | DISCOVERED | Yes | Human-readable region name. |
| `Region` | `geography` | String | Not Null | DERIVED | Yes | Geographical continent / region. |
| `Region` | `is_multi_az` | Boolean | Not Null | DISCOVERED | Yes | Indicates multiple AZ resilience. |
| `AvailabilityZone` | `id` | String | Not Null | DERIVED | Yes | Canonical zone ID (e.g. `us-east-1a`). |
| `AvailabilityZone` | `region_id` | String | Not Null | DISCOVERED | Yes | Parent Region ID. |
| `AvailabilityZone` | `provider` | Enum (`ProviderType`) | Not Null | DISCOVERED | Yes | Cloud provider. |
| `AvailabilityZone` | `native_zone_id` | String | Not Null | DISCOVERED | Yes | Native physical / logical zone identifier. |
| `Tag` | `key` | String | Not Null | DISCOVERED / CURATED | Yes | Tag key name. |
| `Tag` | `value` | String | Not Null | DISCOVERED / CURATED | Yes | Tag value string. |
| `Tag` | `inherited` | Boolean | Not Null | DERIVED | Yes | Indicates inheritance from parent scope. |
| `Tag` | `source` | String | Not Null | DERIVED | Yes | Origin source (`native`, `policy`, `curated`). |

---

### 2.3 Financial & Operational Facts (FOCUS 1.0 Aligned)

| Entity | Attribute | Data Type | Nullability / Measure | Origin | Survives Re-Discovery | Description |
|:---|:---|:---|:---:|:---:|:---:|:---|
| `CostFact` | `id` | UUID / String | Not Null | DERIVED | Yes | Canonical billing record identifier. |
| `CostFact` | `tenant_id` | String | Not Null | CURATED | Yes | Organization tenant boundary. |
| `CostFact` | `scope_id` | UUID / String | Not Null | DISCOVERED | Yes | Scope in force during charge interval. |
| `CostFact` | `resource_id` | UUID / String | Nullable | DERIVED | Yes | Associated canonical resource ID. |
| `CostFact` | `charge_period_start` | Timestamp (UTC) | Not Null | DISCOVERED | Yes | Start of charge period. |
| `CostFact` | `charge_period_end` | Timestamp (UTC) | Not Null | DISCOVERED | Yes | End of charge period. |
| `CostFact` | `charge_category` | Enum (`ChargeCategory`) | Not Null | DISCOVERED | Yes | FOCUS category: `Usage`, `Purchase`, `Adjustment`, etc. |
| `CostFact` | `charge_subcategory` | String | Nullable | DISCOVERED | Yes | Pricing construct (On-Demand, Reserved, Spot). |
| `CostFact` | `billed_cost` | `FinancialMeasure` | **4-State Null Discipline** | DISCOVERED | Yes | Billed invoice cost amount (no bare nulls). |
| `CostFact` | `effective_cost` | `FinancialMeasure` | **4-State Null Discipline** | DERIVED | Yes | Amortised effective cost including commitments. |
| `CostFact` | `contracted_cost` | `FinancialMeasure` | **4-State Null Discipline** | DISCOVERED / DERIVED | Yes | Customer negotiated contracted rate. |
| `CostFact` | `list_cost` | `FinancialMeasure` | **4-State Null Discipline** | DISCOVERED | Yes | Public catalog price before discounts. |
| `CostFact` | `billing_currency` | String (ISO 4217) | Not Null | DISCOVERED | Yes | Currency code (e.g. `USD`, `EUR`). |
| `CostFact` | `pricing_quantity` | `QuantityMeasure` | **4-State Null Discipline** | DISCOVERED | Yes | Billed consumption volume. |
| `CostFact` | `pricing_unit` | String | Nullable | DISCOVERED | Yes | Unit of consumption (e.g. `Hours`, `GB-Mo`). |
| `UsageFact` | `id` | UUID / String | Not Null | DERIVED | Yes | Canonical usage metric identifier. |
| `UsageFact` | `tenant_id` | String | Not Null | CURATED | Yes | Organization tenant boundary. |
| `UsageFact` | `scope_id` | UUID / String | Not Null | DISCOVERED | Yes | Associated Scope ID. |
| `UsageFact` | `resource_id` | UUID / String | Not Null | DISCOVERED | Yes | Associated Resource ID. |
| `UsageFact` | `period_start` | Timestamp (UTC) | Not Null | DISCOVERED | Yes | Usage measurement start. |
| `UsageFact` | `period_end` | Timestamp (UTC) | Not Null | DISCOVERED | Yes | Usage measurement end. |
| `UsageFact` | `metric_name` | String | Not Null | DISCOVERED | Yes | Metric descriptor (e.g. `ComputeHours`). |
| `UsageFact` | `usage_quantity` | `QuantityMeasure` | **4-State Null Discipline** | DISCOVERED | Yes | Numeric consumption quantity. |
| `UsageFact` | `usage_unit` | String | Not Null | DISCOVERED | Yes | Unit of measure (`Hours`, `Bytes`, `Requests`). |
| `RuntimeState` | `id` | UUID / String | Not Null | DERIVED | Yes | Operational runtime snapshot ID. |
| `RuntimeState` | `resource_id` | UUID / String | Not Null | DISCOVERED | Yes | Associated Resource ID. |
| `RuntimeState` | `status` | Enum (`RuntimeStatus`) | Not Null | DISCOVERED | Yes | Operational state (`RUNNING`, `STOPPED`, `DEALLOCATED`). |
| `RuntimeState` | `cpu_utilization_avg`| `QuantityMeasure` | **4-State Null Discipline** | DISCOVERED | Yes | Mean CPU percentage (or `NOT_SUPPORTED`). |
| `RuntimeState` | `memory_utilization_avg`| `QuantityMeasure` | **4-State Null Discipline** | DISCOVERED | Yes | Mean RAM percentage (or `NOT_SUPPORTED`). |
| `RuntimeState` | `observed_at` | Timestamp (UTC) | Not Null | DISCOVERED | Yes | Observation timestamp in UTC. |
| `RuntimeState` | `is_idle` | Boolean | Nullable | DERIVED | Yes | Flag indicating FinOps idle determination. |
| `PricingDimension`| `id` | UUID / String | Not Null | DERIVED | Yes | Pricing dimension identifier. |
| `PricingDimension`| `dimension_name` | String | Not Null | DERIVED | Yes | Dimension title (reconciled across 29 dimensions). |
| `PricingDimension`| `unit` | String | Not Null | DERIVED | Yes | Normalized unit of calculation. |
| `PricingDimension`| `description` | Text | Not Null | DERIVED | Yes | Detailed pricing dimension calculation rule. |
| `PricingDimension`| `tier_minimum` | Numeric(18,6) | Nullable | DERIVED | Yes | Minimum tier volume threshold. |
| `PricingDimension`| `tier_maximum` | Numeric(18,6) | Nullable | DERIVED | Yes | Maximum tier volume threshold. |
| `PricingRecord` | `id` | UUID / String | Not Null | DERIVED | Yes | Catalog rate record identifier. |
| `PricingRecord` | `service_id` | String | Not Null | DISCOVERED | Yes | Applicable Service ID. |
| `PricingRecord` | `resource_type_id` | String | Not Null | DISCOVERED | Yes | Applicable ResourceType ID. |
| `PricingRecord` | `pricing_dimension_name`| String | Not Null | DISCOVERED | Yes | Standardized dimension descriptor. |
| `PricingRecord` | `rate` | `FinancialMeasure` | **4-State Null Discipline** | DISCOVERED | Yes | Price rate per unit. |
| `PricingRecord` | `currency` | String (ISO 4217) | Not Null | DISCOVERED | Yes | Rate currency (e.g. `USD`). |
| `PricingRecord` | `pricing_model` | Enum (`PricingModel`) | Not Null | DISCOVERED | Yes | `OnDemand`, `Spot`, `Reserved1Yr`, `Reserved3Yr`. |
| `PricingRecord` | `effective_date` | Timestamp (UTC) | Not Null | DISCOVERED | Yes | Catalog price effective date. |

---

### 2.4 Governance, Policy & Audit Entities

| Entity | Attribute | Data Type | Nullability / Measure | Origin | Survives Re-Discovery | Description |
|:---|:---|:---|:---:|:---:|:---:|:---|
| `Budget` | `id` | UUID / String | Not Null | CURATED | Yes | Budget identifier. |
| `Budget` | `tenant_id` | String | Not Null | CURATED | Yes | Organization tenant boundary. |
| `Budget` | `scope_id` | UUID / String | Not Null | CURATED | Yes | Target Scope ID. |
| `Budget` | `name` | String | Not Null | CURATED | Yes | Budget description. |
| `Budget` | `amount` | `FinancialMeasure` | **4-State Null Discipline** | CURATED | Yes | Spend ceiling amount. |
| `Budget` | `period` | Enum (`BudgetPeriod`) | Not Null | CURATED | Yes | `MONTHLY`, `QUARTERLY`, or `ANNUAL`. |
| `Budget` | `start_date` | Date | Not Null | CURATED | Yes | Budget cycle start date. |
| `Budget` | `end_date` | Date | Nullable | CURATED | Yes | Optional sunset end date. |
| `Budget` | `threshold_set_id`| UUID / String | Nullable | CURATED | Yes | Linked ThresholdSet profile ID. |
| `Forecast` | `id` | UUID / String | Not Null | DERIVED | Yes | Predictive forecast record ID. |
| `Forecast` | `budget_id` | UUID / String | Nullable | DERIVED | Yes | Associated Budget ID. |
| `Forecast` | `scope_id` | UUID / String | Not Null | DERIVED | Yes | Target Scope ID. |
| `Forecast` | `forecast_period_start` | Timestamp (UTC) | Not Null | DERIVED | Yes | Projection period start. |
| `Forecast` | `forecast_period_end` | Timestamp (UTC) | Not Null | DERIVED | Yes | Projection period end. |
| `Forecast` | `projected_amount` | `FinancialMeasure` | **4-State Null Discipline** | DERIVED | Yes | Forecasted spend total. |
| `Forecast` | `confidence_score` | Float | Not Null | DERIVED | Yes | Statistical confidence (0.0 to 1.0). |
| `Forecast` | `forecast_model` | String | Not Null | DERIVED | Yes | Algorithm descriptor (`LINEAR`, `ARIMA`, `ENSEMBLE`). |
| `ThresholdSet` | `id` | UUID / String | Not Null | CURATED | Yes | Threshold set configuration ID. |
| `ThresholdSet` | `name` | String | Not Null | CURATED | Yes | Profile name. |
| `ThresholdSet` | `amber_percentage` | Numeric(5,2) | Not Null | CURATED | Yes | Warning threshold percentage (default 80.0). |
| `ThresholdSet` | `red_percentage` | Numeric(5,2) | Not Null | CURATED | Yes | Action threshold percentage (default 90.0). |
| `ThresholdSet` | `critical_percentage`| Numeric(5,2) | Not Null | CURATED | Yes | Breach threshold percentage (default 100.0). |
| `ThresholdState` | `id` | UUID / String | Not Null | DERIVED | Yes | Threshold evaluation snapshot ID. |
| `ThresholdState` | `budget_id` | UUID / String | Not Null | DERIVED | Yes | Target Budget ID. |
| `ThresholdState` | `current_spend` | `FinancialMeasure` | **4-State Null Discipline** | DERIVED | Yes | Evaluated consumption spend. |
| `ThresholdState` | `current_band` | Enum (`ThresholdBand`)| Not Null | DERIVED | Yes | Evaluated status (`NORMAL`, `AMBER`, `RED`, `CRITICAL`). |
| `ThresholdState` | `evaluated_at` | Timestamp (UTC) | Not Null | DERIVED | Yes | Evaluation timestamp in UTC. |
| `Policy` | `id` | UUID / String | Not Null | CURATED | Yes | Governance policy rule ID. |
| `Policy` | `name` | String | Not Null | CURATED | Yes | Policy title. |
| `Policy` | `rule_type` | String | Not Null | CURATED | Yes | Policy category (`TAG_COMPLIANCE`, `BUDGET_CAP`, `IDLE_RESOURCE`). |
| `Policy` | `severity` | Enum (`PolicySeverity`)| Not Null | CURATED | Yes | Violation severity (`LOW`, `MEDIUM`, `HIGH`, `CRITICAL`). |
| `Policy` | `parameters` | JSONB / Dict | Not Null | CURATED | Yes | Evaluation criteria and rules. |
| `PolicyFinding` | `id` | UUID / String | Not Null | DERIVED | Yes | Non-compliance incident record ID. |
| `PolicyFinding` | `policy_id` | UUID / String | Not Null | DERIVED | Yes | Violated Policy ID. |
| `PolicyFinding` | `resource_id` | UUID / String | Not Null | DERIVED | Yes | Non-compliant Resource ID. |
| `PolicyFinding` | `status` | Enum (`PolicyStatus`)| Not Null | DERIVED / CURATED | Yes | Resolution status (`OPEN`, `RESOLVED`, `SUPPRESSED`). |
| `PolicyFinding` | `details` | Text | Not Null | DERIVED | Yes | Explanation of non-compliance. |
| `PolicyFinding` | `detected_at` | Timestamp (UTC) | Not Null | DERIVED | Yes | Detection timestamp. |
| `Dependency` | `id` | UUID / String | Not Null | DISCOVERED / DERIVED | Yes | Inter-resource dependency ID. |
| `Dependency` | `source_resource_id`| UUID / String | Not Null | DISCOVERED | Yes | Dependent Resource ID. |
| `Dependency` | `target_resource_id`| UUID / String | Not Null | DISCOVERED | Yes | Prerequisite Resource ID. |
| `Dependency` | `dependency_type` | Enum (`DependencyType`)| Not Null | DISCOVERED | Yes | Link type (`NETWORK`, `STORAGE_ATTACHMENT`, `IAM_ROLE`). |
| `Dependency` | `direction` | Enum (`DependencyDirection`)| Not Null | DISCOVERED | Yes | `INBOUND`, `OUTBOUND`, `BIDIRECTIONAL`. |
| `Alert` | `id` | UUID / String | Not Null | DERIVED | Yes | Operational alert event ID. |
| `Alert` | `tenant_id` | String | Not Null | DERIVED | Yes | Organization tenant boundary. |
| `Alert` | `alert_type` | String | Not Null | DERIVED | Yes | Classification (e.g. `BUDGET_EXCEEDED`, `ANOMALOUS_SPIKE`). |
| `Alert` | `severity` | Enum (`AlertSeverity`)| Not Null | DERIVED | Yes | Urgency (`INFO`, `WARNING`, `ERROR`, `CRITICAL`). |
| `Alert` | `message` | Text | Not Null | DERIVED | Yes | Notification body text. |
| `Alert` | `status` | Enum (`AlertStatus`) | Not Null | DERIVED / CURATED | Yes | Status (`ACTIVE`, `ACKNOWLEDGED`, `RESOLVED`). |
| `Alert` | `triggered_at` | Timestamp (UTC) | Not Null | DERIVED | Yes | Incident trigger timestamp. |
| `Notification` | `id` | UUID / String | Not Null | DERIVED | Yes | Outbound message dispatch ID. |
| `Notification` | `alert_id` | UUID / String | Not Null | DERIVED | Yes | Linked Alert ID. |
| `Notification` | `channel` | Enum (`NotificationChannel`)| Not Null | CURATED | Yes | Delivery channel (`EMAIL`, `SLACK`, `WEBHOOK`, `TEAMS`). |
| `Notification` | `recipient` | String | Not Null | CURATED | Yes | Destination address, channel name, or webhook URI. |
| `Notification` | `status` | Enum (`NotificationStatus`)| Not Null | DERIVED | Yes | Dispatch status (`PENDING`, `SENT`, `FAILED`). |
| `Notification` | `sent_at` | Timestamp (UTC) | Nullable | DERIVED | Yes | Delivery confirmation timestamp. |
| `SyncJob` | `id` | UUID / String | Not Null | DERIVED | Yes | Connector ingestion job audit ID. |
| `SyncJob` | `connector_type` | Enum (`ProviderType`) | Not Null | DERIVED | Yes | Target cloud provider connector. |
| `SyncJob` | `scope_id` | UUID / String | Not Null | DERIVED | Yes | Target root scope node. |
| `SyncJob` | `status` | Enum (`SyncJobStatus`)| Not Null | DERIVED | Yes | Execution status (`SCHEDULED`, `RUNNING`, `COMPLETED`, `FAILED`). |
| `SyncJob` | `started_at` | Timestamp (UTC) | Not Null | DERIVED | Yes | Job execution start. |
| `SyncJob` | `completed_at` | Timestamp (UTC) | Nullable | DERIVED | Yes | Job execution completion. |
| `SyncJob` | `rows_ingested` | Integer | Not Null | DERIVED | Yes | Count of records normalized. |
| `SyncJob` | `error_message` | Text | Nullable | DERIVED | Yes | Diagnostic error message if failed. |
| `AuditEvent` | `id` | UUID / String | Not Null | DERIVED | Yes | Immutable enterprise audit log ID. |
| `AuditEvent` | `tenant_id` | String | Not Null | CURATED | Yes | Organization tenant boundary. |
| `AuditEvent` | `actor_id` | String | Not Null | DERIVED | Yes | User principal or service account initiating mutation. |
| `AuditEvent` | `action` | String | Not Null | DERIVED | Yes | Action descriptor (e.g. `SCOPE_REPARENTED`, `BUDGET_MODIFIED`). |
| `AuditEvent` | `entity_type` | String | Not Null | DERIVED | Yes | Target entity model name. |
| `AuditEvent` | `entity_id` | String | Not Null | DERIVED | Yes | Target entity identifier. |
| `AuditEvent` | `payload_before` | JSONB / Dict | Nullable | DERIVED | Yes | Pre-mutation snapshot payload. |
| `AuditEvent` | `payload_after` | JSONB / Dict | Nullable | DERIVED | Yes | Post-mutation snapshot payload. |
| `AuditEvent` | `timestamp` | Timestamp (UTC) | Not Null | DERIVED | Yes | Audit occurrence timestamp. |
| `AuditEvent` | `correlation_id` | String | Not Null | DERIVED | Yes | Distributed correlation ID. |
| `Override` | `id` | UUID / String | Not Null | CURATED | Yes | Manual curation override record ID. |
| `Override` | `entity_type` | String | Not Null | CURATED | Yes | Target entity model name. |
| `Override` | `entity_id` | String | Not Null | CURATED | Yes | Target entity identifier. |
| `Override` | `field_name` | String | Not Null | CURATED | Yes | Attribute being overridden. |
| `Override` | `override_value` | Any | Not Null | CURATED | Yes | Admin curated value. |
| `Override` | `reason` | Text | Not Null | CURATED | Yes | Business justification. |
| `Override` | `created_by` | String | Not Null | CURATED | Yes | Administrator user principal. |
| `Override` | `expires_at` | Timestamp (UTC) | Nullable | CURATED | Yes | Optional sunset expiration timestamp. |
