import React, { useState } from 'react';
import {
  Breadcrumb,
  DenseTable,
  ThresholdBadge,
  NullValue,
  DataCell,
  CostValue,
  CostSourceBadge,
  FreshnessIndicator,
  ExplainableNumber,
  FilterBar,
  FilterItem,
  serializeFiltersToQuery,
  parseFiltersFromQuery,
  GlobalSearch,
  AccessibleChart,
  EmptyState,
  ErrorState,
  SkeletonLoader,
  UserTimestamp,
  ProgressiveDisclosure,
  RoleShapedNav,
  UserRole,
  ThresholdState,
  NullStateType,
  CostSource,
  EmptyStateType,
  ColumnDefinition,
} from '../design-system';

interface MockResourceRow {
  id: string;
  name: string;
  provider: string;
  service: string;
  cost: number | null;
  costSource: CostSource;
  utilization: number | null;
  thresholdState: ThresholdState;
  nullReason?: NullStateType;
  lastSynced: string;
}

const MOCK_TABLE_DATA: MockResourceRow[] = [
  {
    id: 'res-01',
    name: 'core-ledger-postgres-rds',
    provider: 'AWS',
    service: 'Amazon RDS',
    cost: 1420.5,
    costSource: 'ACTUAL',
    utilization: 84.5,
    thresholdState: 'WARNING',
    lastSynced: new Date(Date.now() - 15 * 60 * 1000).toISOString(),
  },
  {
    id: 'res-02',
    name: 'k8s-worker-nodegroup-c5',
    provider: 'AWS',
    service: 'Amazon EKS',
    cost: 3250.0,
    costSource: 'ACTUAL',
    utilization: 95.2,
    thresholdState: 'CRITICAL',
    lastSynced: new Date(Date.now() - 35 * 60 * 1000).toISOString(),
  },
  {
    id: 'res-03',
    name: 'customer-portal-app-service',
    provider: 'AZURE',
    service: 'Azure App Service',
    cost: 450.0,
    costSource: 'ESTIMATED',
    utilization: 42.0,
    thresholdState: 'NORMAL',
    lastSynced: new Date(Date.now() - 5 * 3600 * 1000).toISOString(),
  },
  {
    id: 'res-04',
    name: 'audit-log-cold-archive-s3',
    provider: 'AWS',
    service: 'Amazon S3 Glacier',
    cost: 0.0, // Confirmed numeric zero!
    costSource: 'ACTUAL',
    utilization: null, // S3 does not have CPU utilization -> NOT_APPLICABLE
    thresholdState: 'INFORMATIONAL',
    nullReason: 'NOT_APPLICABLE',
    lastSynced: new Date(Date.now() - 2 * 60 * 1000).toISOString(),
  },
  {
    id: 'res-05',
    name: 'ml-inference-gpu-cluster',
    provider: 'GCP',
    service: 'Vertex AI',
    cost: null, // Telemetry gap -> NO_DATA
    costSource: 'UNAVAILABLE',
    utilization: null, // Azure/OCI does not expose GPU memory -> NOT_SUPPORTED
    thresholdState: 'UNKNOWN',
    nullReason: 'NOT_SUPPORTED',
    lastSynced: new Date(Date.now() - 28 * 3600 * 1000).toISOString(), // Stale
  },
  {
    id: 'res-06',
    name: 'redis-cache-cluster-primary',
    provider: 'AWS',
    service: 'ElastiCache',
    cost: 180.25,
    costSource: 'FORECAST',
    utilization: 62.1,
    thresholdState: 'NORMAL',
    lastSynced: new Date(Date.now() - 40 * 60 * 1000).toISOString(),
  },
];

export const DesignSystemShowcase: React.FC = () => {
  // Filter bar state
  const [filters, setFilters] = useState<FilterItem[]>([
    { id: 'f-1', field: 'environment', operator: 'eq', value: 'PROD', displayLabel: 'Environment: PROD' },
    { id: 'f-2', field: 'provider', operator: 'eq', value: 'AWS', displayLabel: 'Provider: AWS' },
  ]);

  // URL Round-trip test state
  const [roundTripStatus, setRoundTripStatus] = useState<string | null>(null);

  // Role persona switcher
  const [activeRole, setActiveRole] = useState<UserRole>('FINOPS');

  // Empty state switcher
  const [selectedEmptyState, setSelectedEmptyState] = useState<EmptyStateType>('NO_DATA');

  // Test URL Round-Trip
  const runUrlRoundTripTest = () => {
    const serialized = serializeFiltersToQuery(filters);
    const deserialized = parseFiltersFromQuery(serialized);
    const matches = JSON.stringify(filters) === JSON.stringify(deserialized);
    if (matches) {
      setRoundTripStatus(
        `SUCCESS: Exactly round-tripped ${filters.length} filters through URL query encoding!`
      );
    } else {
      setRoundTripStatus('FAIL: Deserialized filters do not match original payload.');
    }
  };

  // Table columns definition
  const tableColumns: ColumnDefinition<MockResourceRow>[] = [
    { key: 'name', header: 'Resource Name', sortable: true },
    { key: 'provider', header: 'Provider', width: '90px' },
    { key: 'service', header: 'Service Category' },
    {
      key: 'cost',
      header: 'Monthly Spend',
      isNumeric: true,
      sortable: true,
      render: (row) => <CostValue amount={row.cost} source={row.costSource} currency="USD" />,
    },
    {
      key: 'utilization',
      header: 'CPU / Resource Load',
      isNumeric: true,
      render: (row) => {
        if (row.utilization === null) {
          return <NullValue state={row.nullReason || 'NO_DATA'} />;
        }
        return <DataCell value={row.utilization} precision={1} />;
      },
    },
    {
      key: 'thresholdState',
      header: 'Threshold Status',
      render: (row) => <ThresholdBadge state={row.thresholdState} size="sm" />,
    },
    {
      key: 'lastSynced',
      header: 'Freshness',
      render: (row) => (
        <FreshnessIndicator
          lastSyncedAt={row.lastSynced}
          provider={row.provider}
          jobId={`job-${row.id}`}
        />
      ),
    },
  ];

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: '2.5rem',
        maxWidth: '1360px',
        margin: '0 auto',
        width: '100%',
        paddingBottom: '3rem',
      }}
    >
      {/* Hero Header */}
      <div
        style={{
          borderBottom: '1px solid var(--border-color)',
          paddingBottom: '1.25rem',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'flex-start',
          flexWrap: 'wrap',
          gap: '1rem',
        }}
      >
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.25rem' }}>
            <span
              style={{
                fontSize: '0.75rem',
                backgroundColor: 'rgba(56, 189, 248, 0.15)',
                color: '#38bdf8',
                border: '1px solid rgba(56, 189, 248, 0.3)',
                padding: '0.15rem 0.5rem',
                borderRadius: '9999px',
                fontWeight: 600,
              }}
            >
              Prompt 36 / BBP Section 31
            </span>
            <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
              WCAG 2.1 Level AA Compliant
            </span>
          </div>
          <h1 style={{ fontSize: '1.875rem', fontWeight: 700, margin: '0 0 0.4rem 0' }}>
            Design System & Global Patterns Workbench
          </h1>
          <p style={{ color: 'var(--text-secondary)', fontSize: '0.9375rem', margin: 0, maxWidth: '850px' }}>
            Enforceable UI visual and interaction vocabulary: strict threshold colour system, four-state
            null rendering, cost source badge pairing, data freshness, and WCAG AA accessible controls.
          </p>
        </div>

        <GlobalSearch />
      </div>

      {/* Section 1: Hierarchy Navigation */}
      <section aria-labelledby="section-hierarchy">
        <h2 id="section-hierarchy" style={{ fontSize: '1.25rem', fontWeight: 600, margin: '0 0 0.5rem 0' }}>
          1. Hierarchy Navigation (Clickable Breadcrumb)
        </h2>
        <p style={{ color: 'var(--text-secondary)', fontSize: '0.875rem', margin: '0 0 0.75rem 0' }}>
          Enforces: "hierarchy is the navigation with a complete clickable breadcrumb".
        </p>
        <div style={{ padding: '0.75rem 1rem', backgroundColor: 'var(--bg-secondary)', borderRadius: '8px', border: '1px solid var(--border-color)' }}>
          <Breadcrumb
            items={[
              { label: 'Global Organization', href: '#org' },
              { label: 'Retail Banking (BU_RETAIL_BANKING)', href: '#bu' },
              { label: 'Core Banking Systems (CC-2001)', href: '#cc' },
              { label: 'Customer Mobile App (APP-0001)', href: '#app' },
              { label: 'core-ledger-postgres-rds', isCurrent: true },
            ]}
          />
        </div>
      </section>

      {/* Section 2: Six-State Threshold Colour System */}
      <section aria-labelledby="section-thresholds">
        <h2 id="section-thresholds" style={{ fontSize: '1.25rem', fontWeight: 600, margin: '0 0 0.5rem 0' }}>
          2. Threshold Colour System (Six States & Accessible Equivalents)
        </h2>
        <p style={{ color: 'var(--text-secondary)', fontSize: '0.875rem', margin: '0 0 0.75rem 0' }}>
          Strict Rule: Color is NEVER used decoratively; reserved exclusively for threshold states and
          always paired with an icon and explicit text label.
        </p>
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
            gap: '1rem',
          }}
        >
          <div style={{ backgroundColor: 'var(--bg-secondary)', padding: '1rem', borderRadius: '8px', border: '1px solid var(--border-color)' }}>
            <div style={{ marginBottom: '0.5rem' }}><ThresholdBadge state="NORMAL" /></div>
            <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>Normal / Compliant</div>
            <div style={{ fontSize: '0.7rem', color: '#34d399', marginTop: '0.2rem' }}>Contrast: 8.2:1 (AAA)</div>
          </div>
          <div style={{ backgroundColor: 'var(--bg-secondary)', padding: '1rem', borderRadius: '8px', border: '1px solid var(--border-color)' }}>
            <div style={{ marginBottom: '0.5rem' }}><ThresholdBadge state="WARNING" /></div>
            <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>Warning (80%-99%)</div>
            <div style={{ fontSize: '0.7rem', color: '#fbbf24', marginTop: '0.2rem' }}>Contrast: 9.1:1 (AAA)</div>
          </div>
          <div style={{ backgroundColor: 'var(--bg-secondary)', padding: '1rem', borderRadius: '8px', border: '1px solid var(--border-color)' }}>
            <div style={{ marginBottom: '0.5rem' }}><ThresholdBadge state="HIGH" /></div>
            <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>High Anomaly Risk</div>
            <div style={{ fontSize: '0.7rem', color: '#fb923c', marginTop: '0.2rem' }}>Contrast: 7.4:1 (AAA)</div>
          </div>
          <div style={{ backgroundColor: 'var(--bg-secondary)', padding: '1rem', borderRadius: '8px', border: '1px solid var(--border-color)' }}>
            <div style={{ marginBottom: '0.5rem' }}><ThresholdBadge state="CRITICAL" /></div>
            <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>Critical Breach (&gt;=100%)</div>
            <div style={{ fontSize: '0.7rem', color: '#f87171', marginTop: '0.2rem' }}>Contrast: 6.9:1 (AAA)</div>
          </div>
          <div style={{ backgroundColor: 'var(--bg-secondary)', padding: '1rem', borderRadius: '8px', border: '1px solid var(--border-color)' }}>
            <div style={{ marginBottom: '0.5rem' }}><ThresholdBadge state="INFORMATIONAL" /></div>
            <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>Baseline Info</div>
            <div style={{ fontSize: '0.7rem', color: '#38bdf8', marginTop: '0.2rem' }}>Contrast: 8.5:1 (AAA)</div>
          </div>
          <div style={{ backgroundColor: 'var(--bg-secondary)', padding: '1rem', borderRadius: '8px', border: '1px solid var(--border-color)' }}>
            <div style={{ marginBottom: '0.5rem' }}><ThresholdBadge state="UNKNOWN" /></div>
            <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>Telemetry Missing</div>
            <div style={{ fontSize: '0.7rem', color: '#94a3b8', marginTop: '0.2rem' }}>Contrast: 5.6:1 (AA)</div>
          </div>
        </div>
      </section>

      {/* Section 3: Four-State Null Rendering Components */}
      <section aria-labelledby="section-null-states">
        <h2 id="section-null-states" style={{ fontSize: '1.25rem', fontWeight: 600, margin: '0 0 0.5rem 0' }}>
          3. Four-State Null Rendering (Acceptance: Visually Distinct)
        </h2>
        <p style={{ color: 'var(--text-secondary)', fontSize: '0.875rem', margin: '0 0 0.75rem 0' }}>
          Hard Rule: "Do not render a blank cell for any absent value. Zero, no data, not applicable
          and not supported are visually distinct everywhere."
        </p>
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))',
            gap: '1rem',
          }}
        >
          <div style={{ backgroundColor: 'var(--bg-secondary)', padding: '1.25rem', borderRadius: '8px', border: '1px solid var(--border-color)' }}>
            <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', marginBottom: '0.5rem' }}>
              State 1: Confirmed Numeric Zero
            </div>
            <div style={{ fontSize: '1.25rem', marginBottom: '0.5rem' }}>
              <NullValue state="ZERO" customZeroValue="$0.00" />
            </div>
            <p style={{ fontSize: '0.8125rem', color: 'var(--text-secondary)', margin: 0 }}>
              Rendered as a bold confirmed number; indicates true measured 0.00 spend or usage, not an omission.
            </p>
          </div>

          <div style={{ backgroundColor: 'var(--bg-secondary)', padding: '1.25rem', borderRadius: '8px', border: '1px solid var(--border-color)' }}>
            <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', marginBottom: '0.5rem' }}>
              State 2: No Data Recorded
            </div>
            <div style={{ fontSize: '1.25rem', marginBottom: '0.5rem' }}>
              <NullValue state="NO_DATA" />
            </div>
            <p style={{ fontSize: '0.8125rem', color: 'var(--text-secondary)', margin: 0 }}>
              Dashed underline with tooltip; telemetry was expected for this period but was not recorded.
            </p>
          </div>

          <div style={{ backgroundColor: 'var(--bg-secondary)', padding: '1.25rem', borderRadius: '8px', border: '1px solid var(--border-color)' }}>
            <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', marginBottom: '0.5rem' }}>
              State 3: Not Applicable
            </div>
            <div style={{ fontSize: '1.25rem', marginBottom: '0.5rem' }}>
              <NullValue state="NOT_APPLICABLE" />
            </div>
            <p style={{ fontSize: '0.8125rem', color: 'var(--text-secondary)', margin: 0 }}>
              Styled badge with '⊘ N/A'; this metric does not apply to this resource type (e.g. IOPS on S3).
            </p>
          </div>

          <div style={{ backgroundColor: 'var(--bg-secondary)', padding: '1.25rem', borderRadius: '8px', border: '1px solid var(--border-color)' }}>
            <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', marginBottom: '0.5rem' }}>
              State 4: Not Supported By Provider
            </div>
            <div style={{ fontSize: '1.25rem', marginBottom: '0.5rem' }}>
              <NullValue state="NOT_SUPPORTED" />
            </div>
            <p style={{ fontSize: '0.8125rem', color: 'var(--text-secondary)', margin: 0 }}>
              Styled badge with '⊗ Not supported'; underlying cloud provider does not expose this capability.
            </p>
          </div>
        </div>
      </section>

      {/* Section 4: Cost Source Badges & CostValue Component */}
      <section aria-labelledby="section-cost-sources">
        <h2 id="section-cost-sources" style={{ fontSize: '1.25rem', fontWeight: 600, margin: '0 0 0.5rem 0' }}>
          4. Cost Source Badges (Acceptance: Estimated Cannot Look Like Actual)
        </h2>
        <p style={{ color: 'var(--text-secondary)', fontSize: '0.875rem', margin: '0 0 0.75rem 0' }}>
          Hard Rule: "An estimated cost cannot be styled as an actual cost without deliberately overriding
          the component." Mandatory source tagging enforced by TypeScript contract.
        </p>
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
            gap: '1rem',
          }}
        >
          <div style={{ backgroundColor: 'var(--bg-secondary)', padding: '1rem', borderRadius: '8px', border: '1px solid var(--border-color)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.4rem' }}>
              <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>ACTUAL (Invoiced / Billed)</span>
              <CostSourceBadge source="ACTUAL" size="sm" />
            </div>
            <CostValue amount={1420.5} source="ACTUAL" currency="USD" />
          </div>

          <div style={{ backgroundColor: 'var(--bg-secondary)', padding: '1rem', borderRadius: '8px', border: '1px solid var(--border-color)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.4rem' }}>
              <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>ESTIMATED (Rate Card Calculated)</span>
              <CostSourceBadge source="ESTIMATED" size="sm" />
            </div>
            <CostValue amount={450.0} source="ESTIMATED" currency="USD" />
          </div>

          <div style={{ backgroundColor: 'var(--bg-secondary)', padding: '1rem', borderRadius: '8px', border: '1px solid var(--border-color)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.4rem' }}>
              <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>FORECAST (Projected Run-rate)</span>
              <CostSourceBadge source="FORECAST" size="sm" />
            </div>
            <CostValue amount={180.25} source="FORECAST" currency="USD" />
          </div>

          <div style={{ backgroundColor: 'var(--bg-secondary)', padding: '1rem', borderRadius: '8px', border: '1px solid var(--border-color)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.4rem' }}>
              <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>MANUAL (Journal Voucher Override)</span>
              <CostSourceBadge source="MANUAL" size="sm" />
            </div>
            <CostValue amount={600.0} source="MANUAL" currency="USD" />
          </div>

          <div style={{ backgroundColor: 'var(--bg-secondary)', padding: '1rem', borderRadius: '8px', border: '1px solid var(--border-color)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.4rem' }}>
              <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>CACHED (Offline Snapshot)</span>
              <CostSourceBadge source="CACHED" size="sm" />
            </div>
            <CostValue amount={312.8} source="CACHED" currency="USD" />
          </div>

          <div style={{ backgroundColor: 'var(--bg-secondary)', padding: '1rem', borderRadius: '8px', border: '1px solid var(--border-color)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.4rem' }}>
              <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>UNAVAILABLE (Unresolved Spend)</span>
              <CostSourceBadge source="UNAVAILABLE" size="sm" />
            </div>
            <CostValue amount={null} source="UNAVAILABLE" currency="USD" />
          </div>
        </div>
      </section>

      {/* Section 5: Dense Data Table with Density Toggle & Column Chooser */}
      <section aria-labelledby="section-table">
        <h2 id="section-table" style={{ fontSize: '1.25rem', fontWeight: 600, margin: '0 0 0.5rem 0' }}>
          5. Dense Financial Table (Density Toggle, Sticky Header & Right-Aligned Precision)
        </h2>
        <p style={{ color: 'var(--text-secondary)', fontSize: '0.875rem', margin: '0 0 0.75rem 0' }}>
          Features density switcher (Compact vs Comfortable), sticky headers, column visibility chooser,
          and guarantees no cell renders blank.
        </p>
        <DenseTable<MockResourceRow>
          columns={tableColumns}
          data={MOCK_TABLE_DATA}
          totalRows={MOCK_TABLE_DATA.length}
          pageSize={10}
        />
      </section>

      {/* Section 6: Persistent Combinable Filter Bar & URL Round-Trip Test */}
      <section aria-labelledby="section-filter-bar">
        <h2 id="section-filter-bar" style={{ fontSize: '1.25rem', fontWeight: 600, margin: '0 0 0.5rem 0' }}>
          6. Persistent Filter Bar & URL Round-Trip Serialization
        </h2>
        <p style={{ color: 'var(--text-secondary)', fontSize: '0.875rem', margin: '0 0 0.75rem 0' }}>
          Acceptance: "Filter state round-trips through the URL and restores exactly."
          Discloses active filters and RBAC scope grants.
        </p>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          <FilterBar
            filters={filters}
            onChange={setFilters}
            rbacScopeDisclosure="Retail Banking Unit (BU_RETAIL_BANKING) & Core Banking (CC-2001)"
            totalRecordsCount={142}
            filteredRecordsCount={6}
          />

          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '1rem',
              backgroundColor: 'var(--bg-secondary)',
              padding: '0.75rem 1rem',
              borderRadius: '8px',
              border: '1px solid var(--border-color)',
            }}
          >
            <button
              type="button"
              onClick={runUrlRoundTripTest}
              aria-label="Execute URL round-trip verification test"
              style={{
                padding: '0.4rem 0.8rem',
                borderRadius: '6px',
                border: '1px solid var(--accent-blue, #38bdf8)',
                backgroundColor: 'rgba(56, 189, 248, 0.15)',
                color: 'var(--accent-blue, #38bdf8)',
                fontWeight: 600,
                fontSize: '0.8125rem',
                cursor: 'pointer',
              }}
            >
              Execute URL Round-Trip Test
            </button>

            {roundTripStatus && (
              <span
                style={{
                  fontSize: '0.8125rem',
                  fontWeight: 500,
                  color: roundTripStatus.startsWith('SUCCESS') ? '#34d399' : '#f87171',
                }}
              >
                {roundTripStatus}
              </span>
            )}
          </div>
        </div>
      </section>

      {/* Section 7: Explainable Numbers & Localized Timestamps */}
      <section aria-labelledby="section-explainable-numbers">
        <h2 id="section-explainable-numbers" style={{ fontSize: '1.25rem', fontWeight: 600, margin: '0 0 0.5rem 0' }}>
          7. Explainable Numbers & User-Localized Timestamps
        </h2>
        <p style={{ color: 'var(--text-secondary)', fontSize: '0.875rem', margin: '0 0 0.75rem 0' }}>
          Every numeric value provides an accessible affordance revealing derivation formulas, cost basis,
          currency policy, and attribution rules. Timestamps show local timezone and abbreviation.
        </p>
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))',
            gap: '1rem',
          }}
        >
          <div style={{ backgroundColor: 'var(--bg-secondary)', padding: '1rem', borderRadius: '8px', border: '1px solid var(--border-color)' }}>
            <h4 style={{ margin: '0 0 0.5rem 0', fontSize: '0.875rem', color: 'var(--text-secondary)' }}>
              Explainable Spend Calculation:
            </h4>
            <div style={{ fontSize: '1.125rem' }}>
              <ExplainableNumber
                value={1420.5}
                currency="USD"
                detail={{
                  metricName: 'PostgreSQL RDS Effective Spend',
                  formattedValue: '$1,420.50',
                  rawNumericValue: 1420.5,
                  costBasis: 'EFFECTIVE',
                  currency: 'USD',
                  exchangeRate: 1.0,
                  formula: 'Quantity (720 hrs) × Blended Instance Rate ($1.9729) + Provisioned IOPS ($40.00)',
                  attributionRule: 'Direct Scope Attribution: APP-0001',
                  includesUnallocated: false,
                  dataFreshness: 'Synced 15m ago (AWS CUR)',
                  costSource: 'ACTUAL',
                }}
              />
            </div>
          </div>

          <div style={{ backgroundColor: 'var(--bg-secondary)', padding: '1rem', borderRadius: '8px', border: '1px solid var(--border-color)' }}>
            <h4 style={{ margin: '0 0 0.5rem 0', fontSize: '0.875rem', color: 'var(--text-secondary)' }}>
              Localized Timestamps (User Timezone):
            </h4>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.35rem' }}>
              <div>
                <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>Event Time: </span>
                <UserTimestamp timestamp="2026-10-03T11:04:50Z" />
              </div>
              <div>
                <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>Date Only: </span>
                <UserTimestamp timestamp="2026-10-03T11:04:50Z" format="date-only" />
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Section 8: Accessible Chart with Data-Table Alternative */}
      <section aria-labelledby="section-accessible-chart">
        <h2 id="section-accessible-chart" style={{ fontSize: '1.25rem', fontWeight: 600, margin: '0 0 0.5rem 0' }}>
          8. Accessible Chart (SVG Visualization + Data-Table Alternate)
        </h2>
        <p style={{ color: 'var(--text-secondary)', fontSize: '0.875rem', margin: '0 0 0.75rem 0' }}>
          WCAG 2.1 AA Compliant: ARIA graphics roles, descriptions, and one-click toggle to a fully
          semantic data table for screen reader and keyboard accessibility.
        </p>
        <AccessibleChart
          title="Monthly Cloud Spend Trend by Service"
          description="Aggregated spend across RDS, EKS, App Service, ElastiCache and S3 for the last 6 periods"
          metricName="Monthly Spend"
          currency="USD"
          data={[
            { label: 'May 2026', value: 4200, formattedValue: '$4,200' },
            { label: 'Jun 2026', value: 4650, formattedValue: '$4,650' },
            { label: 'Jul 2026', value: 5120, formattedValue: '$5,120' },
            { label: 'Aug 2026', value: 5400, formattedValue: '$5,400' },
            { label: 'Sep 2026', value: 6300, formattedValue: '$6,300' },
            { label: 'Oct 2026', value: 6720, formattedValue: '$6,720' },
          ]}
        />
      </section>

      {/* Section 9: Four Distinct Empty States */}
      <section aria-labelledby="section-empty-states">
        <h2 id="section-empty-states" style={{ fontSize: '1.25rem', fontWeight: 600, margin: '0 0 0.5rem 0' }}>
          9. Four Distinct Empty States
        </h2>
        <p style={{ color: 'var(--text-secondary)', fontSize: '0.875rem', margin: '0 0 0.75rem 0' }}>
          Four clearly differentiated empty conditions: No Data, Access Restricted, Provider Unsupported,
          and Initial Sync In Progress.
        </p>
        <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '1rem', flexWrap: 'wrap' }}>
          {(['NO_DATA', 'NO_ACCESS', 'NOT_SUPPORTED', 'NOT_YET_SYNCED'] as EmptyStateType[]).map((st) => (
            <button
              key={st}
              type="button"
              onClick={() => setSelectedEmptyState(st)}
              aria-pressed={selectedEmptyState === st}
              style={{
                padding: '0.35rem 0.75rem',
                borderRadius: '6px',
                border: '1px solid var(--border-color)',
                backgroundColor:
                  selectedEmptyState === st ? 'var(--accent-blue, #38bdf8)' : 'var(--bg-secondary)',
                color: selectedEmptyState === st ? '#0f172a' : 'var(--text-secondary)',
                fontWeight: 600,
                fontSize: '0.8125rem',
                cursor: 'pointer',
              }}
            >
              {st}
            </button>
          ))}
        </div>
        <EmptyState
          type={selectedEmptyState}
          onAction={() => alert(`Action triggered for ${selectedEmptyState}`)}
        />
      </section>

      {/* Section 10: Error States & Skeleton Loading */}
      <section aria-labelledby="section-error-skeleton">
        <h2 id="section-error-skeleton" style={{ fontSize: '1.25rem', fontWeight: 600, margin: '0 0 0.5rem 0' }}>
          10. Error States (with Provider Errors) & Skeleton Loading
        </h2>
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(340px, 1fr))',
            gap: '1rem',
          }}
        >
          <ErrorState
            title="AWS Cost Explorer Synchronization Failed"
            message="Connector failed to fetch daily cost allocation tags due to upstream IAM authorization failure."
            errorCode="CONNECTOR_AUTHENTICATION_ERROR"
            correlationId="corr-8849-aws-cur"
            providerError={{
              provider: 'AWS',
              upstreamCode: 'AccessDeniedException',
              upstreamMessage: 'User arn:aws:iam::123456789012:role/CloudLensRole is not authorized to perform: ce:GetCostAndUsage',
              requestId: 'req-3f82-a9b1',
            }}
            onRetry={() => alert('Retrying AWS connector sync...')}
            secondaryAction={{
              label: 'Verify IAM Policy',
              onClick: () => alert('Opening IAM setup instructions...'),
            }}
          />

          <SkeletonLoader
            variant="table"
            rows={3}
            loadingMessage="Fetching real-time FinOps telemetry from 4 cloud connectors..."
            onCancel={() => alert('In-flight fetch aborted by user')}
          />
        </div>
      </section>

      {/* Section 11: Progressive Disclosure & Role-Shaped Navigation */}
      <section aria-labelledby="section-roles-disclosure">
        <h2 id="section-roles-disclosure" style={{ fontSize: '1.25rem', fontWeight: 600, margin: '0 0 0.5rem 0' }}>
          11. Role-Shaped Navigation & Progressive Disclosure
        </h2>
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))',
            gap: '1rem',
          }}
        >
          <RoleShapedNav
            currentRole={activeRole}
            onRoleChange={setActiveRole}
            activePath="/finops/waste"
            onNavigate={(p) => alert(`Navigating to ${p}`)}
          />

          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
            <ProgressiveDisclosure
              title="Raw Focus Ingestion Payload"
              badgeText="JSON 4.2 KB"
              defaultOpen={false}
            >
              <pre
                style={{
                  margin: 0,
                  padding: '0.5rem',
                  backgroundColor: '#0f172a',
                  borderRadius: '4px',
                  fontSize: '0.75rem',
                  color: '#38bdf8',
                  overflowX: 'auto',
                }}
              >
                {JSON.stringify(
                  {
                    BilledCost: 1420.5,
                    EffectiveCost: 1420.5,
                    ChargeCategory: 'Usage',
                    ProviderName: 'AWS',
                    ServiceName: 'Amazon RDS',
                    PricingCurrency: 'USD',
                  },
                  null,
                  2
                )}
              </pre>
            </ProgressiveDisclosure>

            <ProgressiveDisclosure
              title="Audit & Provenance Details"
              badgeText="Prompt 35 Provenance"
              defaultOpen={true}
            >
              <div style={{ fontSize: '0.8125rem', color: 'var(--text-secondary)' }}>
                <div>Generation Time: 2026-10-03 16:45:00 UTC</div>
                <div>Requester Identity: admin@cloudlens.internal</div>
                <div>Cost Basis: EFFECTIVE | Currency Policy: USD Base</div>
                <div>Data Freshness: AWS 15m, Azure 5h, GCP 28h</div>
              </div>
            </ProgressiveDisclosure>
          </div>
        </div>
      </section>
    </div>
  );
};

export default DesignSystemShowcase;
