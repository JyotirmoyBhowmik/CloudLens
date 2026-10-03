import React, { useEffect, useState } from 'react';
import {
  Breadcrumb,
  BreadcrumbItem,
  CostValue,
  ThresholdBadge,
  FreshnessIndicator,
} from '../design-system';
import {
  RefreshCw,
  AlertTriangle,
  FolderTree,
  ChevronRight,
  ChevronDown,
  Layers,
  Activity,
  FileCheck,
} from 'lucide-react';

interface NativeHierarchyNode {
  id: string;
  native_id: string;
  native_name: string;
  native_type: string;
  level: number;
  child_count: number;
  cost: number | string;
  resource_count: number;
  children?: NativeHierarchyNode[];
}

interface ProviderDashboardData {
  provider: string;
  display_name: string;
  freshness: {
    refreshed_at: string;
    age_seconds: number;
    status: string;
  };
  hierarchy_root_name: string;
  native_group_term: string;
  native_account_term: string;
  native_group_count: number;
  native_account_count: number;
  resource_count: number;
  service_count: number;
  actual_cost: {
    amount: number | string;
    cost_source: string;
  };
  estimated_cost: {
    amount: number | string;
    cost_source: string;
  };
  forecast_cost: {
    amount: number | string;
    cost_source: string;
  };
  budget_amount: number | string;
  budget_utilisation_pct: number | string;
  threshold_state: string;
  usage_volume_headline: string;
  runtime_active_hours: number | string;
  active_alerts_count: number;
  pricing_model_summary: string;
  hierarchy_tree: NativeHierarchyNode;
}

export const ProviderDashboard: React.FC = () => {
  const [selectedProvider, setSelectedProvider] = useState<string>('azure');
  const [data, setData] = useState<ProviderDashboardData | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [expandedNodes, setExpandedNodes] = useState<Record<string, boolean>>({
    'mg-root': true,
    'ou-root': true,
    'org-gcp': true,
    'root-compartment': true,
  });

  useEffect(() => {
    setLoading(true);
    fetch(`/api/v1/dashboards/providers/${selectedProvider}`)
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json();
      })
      .then((json: ProviderDashboardData) => {
        setData(json);
        setLoading(false);
      })
      .catch((err) => {
        console.error('Failed to load provider dashboard:', err);
        setLoading(false);
      });
  }, [selectedProvider]);

  const toggleNode = (nodeId: string) => {
    setExpandedNodes((prev) => ({ ...prev, [nodeId]: !prev[nodeId] }));
  };

  const breadcrumbs: BreadcrumbItem[] = [
    { label: 'Platform Home', href: '/' },
    { label: 'Cloud Providers', href: '/dashboards/providers' },
    { label: data ? `${data.display_name} Infrastructure` : 'Provider Dashboard', isCurrent: true },
  ];

  const renderTree = (node: NativeHierarchyNode) => {
    const isExpanded = !!expandedNodes[node.id];
    const hasChildren = node.children && node.children.length > 0;

    return (
      <div key={node.id} style={{ marginLeft: `${(node.level - 1) * 1.25}rem`, marginTop: '0.4rem' }}>
        <div
          onClick={() => hasChildren && toggleNode(node.id)}
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            padding: '0.5rem 0.75rem',
            backgroundColor: 'var(--bg-secondary)',
            borderRadius: '6px',
            border: '1px solid var(--border-color)',
            cursor: hasChildren ? 'pointer' : 'default',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            {hasChildren ? (
              isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />
            ) : (
              <span style={{ width: 14 }} />
            )}
            <FolderTree size={16} style={{ color: '#38bdf8' }} />
            <span style={{ fontWeight: 600, fontSize: '0.875rem' }}>{node.native_name}</span>
            <span style={{ fontSize: '0.75rem', backgroundColor: '#0284c7', color: '#e0f2fe', padding: '0.1rem 0.4rem', borderRadius: '4px' }}>
              {node.native_type}
            </span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', fontSize: '0.8125rem' }}>
            <span style={{ color: 'var(--text-secondary)' }}>{node.resource_count} resources</span>
            <CostValue amount={Number(node.cost)} source="ACTUAL" currency="USD" />
          </div>
        </div>

        {hasChildren && isExpanded && (
          <div style={{ display: 'flex', flexDirection: 'column' }}>
            {node.children!.map((child) => renderTree(child))}
          </div>
        )}
      </div>
    );
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem', width: '100%' }}>
      {/* 1. Header & Provider Tabs */}
      <div>
        <Breadcrumb items={breadcrumbs} />
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '0.75rem', flexWrap: 'wrap', gap: '1rem' }}>
          <div>
            <h1 style={{ fontSize: '1.75rem', fontWeight: 700, margin: 0, color: 'var(--text-primary)' }}>
              Provider Operations: {data?.display_name || selectedProvider.toUpperCase()}
            </h1>
            <p style={{ margin: '0.25rem 0 0 0', fontSize: '0.875rem', color: 'var(--text-secondary)' }}>
              Native hierarchy tree, structural container counts, utilization and billing alignment.
            </p>
          </div>

          {/* Provider Switcher */}
          <div style={{ display: 'flex', gap: '0.5rem', backgroundColor: 'var(--bg-secondary)', padding: '0.25rem', borderRadius: '8px', border: '1px solid var(--border-color)' }}>
            {(['azure', 'aws', 'gcp', 'oci'] as const).map((prov) => (
              <button
                key={prov}
                onClick={() => setSelectedProvider(prov)}
                style={{
                  padding: '0.4rem 0.8rem',
                  borderRadius: '6px',
                  border: 'none',
                  backgroundColor: selectedProvider === prov ? '#0284c7' : 'transparent',
                  color: selectedProvider === prov ? '#ffffff' : 'var(--text-secondary)',
                  fontWeight: 600,
                  fontSize: '0.8125rem',
                  cursor: 'pointer',
                  textTransform: 'uppercase',
                }}
              >
                {prov}
              </button>
            ))}
          </div>
        </div>
      </div>

      {loading && (
        <div style={{ padding: '3rem', textAlign: 'center', color: 'var(--text-secondary)' }}>
          <RefreshCw className="animate-spin" style={{ margin: '0 auto 1rem auto' }} />
          <p>Querying {selectedProvider.toUpperCase()} native hierarchy and telemetry rollups...</p>
        </div>
      )}

      {!loading && !data && (
        <div style={{ padding: '2rem', textAlign: 'center' }}>
          <AlertTriangle style={{ color: '#ef4444', margin: '0 auto 1rem auto' }} />
          <p>Unable to retrieve provider dashboard details.</p>
        </div>
      )}

      {!loading && data && (
        <>
          {/* 2. Provider Native Metrics Summary Cards */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '1rem' }}>
            {/* Native Group Count */}
            <div style={{ backgroundColor: 'var(--bg-secondary)', border: '1px solid var(--border-color)', borderRadius: '10px', padding: '1.25rem' }}>
              <span style={{ fontSize: '0.8125rem', color: 'var(--text-secondary)', fontWeight: 500 }}>
                {data.native_group_term}
              </span>
              <div style={{ fontSize: '1.75rem', fontWeight: 700, margin: '0.25rem 0', color: 'var(--text-primary)' }}>
                {data.native_group_count}
              </div>
              <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
                Structural governance tiers
              </span>
            </div>

            {/* Native Account Count */}
            <div style={{ backgroundColor: 'var(--bg-secondary)', border: '1px solid var(--border-color)', borderRadius: '10px', padding: '1.25rem' }}>
              <span style={{ fontSize: '0.8125rem', color: 'var(--text-secondary)', fontWeight: 500 }}>
                {data.native_account_term}
              </span>
              <div style={{ fontSize: '1.75rem', fontWeight: 700, margin: '0.25rem 0', color: 'var(--text-primary)' }}>
                {data.native_account_count}
              </div>
              <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
                Billing boundaries
              </span>
            </div>

            {/* Total Resources & Services */}
            <div style={{ backgroundColor: 'var(--bg-secondary)', border: '1px solid var(--border-color)', borderRadius: '10px', padding: '1.25rem' }}>
              <span style={{ fontSize: '0.8125rem', color: 'var(--text-secondary)', fontWeight: 500 }}>
                Resource Footprint
              </span>
              <div style={{ fontSize: '1.75rem', fontWeight: 700, margin: '0.25rem 0', color: 'var(--text-primary)' }}>
                {data.resource_count.toLocaleString()}
              </div>
              <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
                Across {data.service_count} cloud services
              </span>
            </div>

            {/* Actual Spend */}
            <div style={{ backgroundColor: 'var(--bg-secondary)', border: '1px solid var(--border-color)', borderRadius: '10px', padding: '1.25rem' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span style={{ fontSize: '0.8125rem', color: 'var(--text-secondary)', fontWeight: 500 }}>
                  Actual Spend
                </span>
                <ThresholdBadge state={data.threshold_state as any} />
              </div>
              <div style={{ marginTop: '0.4rem' }}>
                <CostValue amount={Number(data.actual_cost.amount)} source="ACTUAL" currency="USD" />
              </div>
              <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
                {Number(data.budget_utilisation_pct).toFixed(1)}% of ${(Number(data.budget_amount) / 1000).toFixed(0)}k budget
              </span>
            </div>
          </div>

          {/* 3. Operational Highlights */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: '1.5rem' }}>
            <div style={{ backgroundColor: 'var(--bg-secondary)', border: '1px solid var(--border-color)', borderRadius: '10px', padding: '1.25rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.5rem' }}>
                <Activity size={18} style={{ color: '#34d399' }} />
                <h3 style={{ fontSize: '0.9375rem', fontWeight: 600, margin: 0 }}>Usage Headline & Runtime</h3>
              </div>
              <p style={{ fontSize: '0.875rem', color: 'var(--text-primary)', margin: 0, fontWeight: 500 }}>
                {data.usage_volume_headline}
              </p>
              <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', marginTop: '0.5rem' }}>
                Active Runtime: {Number(data.runtime_active_hours)} hours in period
              </div>
            </div>

            <div style={{ backgroundColor: 'var(--bg-secondary)', border: '1px solid var(--border-color)', borderRadius: '10px', padding: '1.25rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.5rem' }}>
                <FileCheck size={18} style={{ color: '#fbbf24' }} />
                <h3 style={{ fontSize: '0.9375rem', fontWeight: 600, margin: 0 }}>Contract & Pricing Model</h3>
              </div>
              <p style={{ fontSize: '0.875rem', color: 'var(--text-primary)', margin: 0, fontWeight: 500 }}>
                {data.pricing_model_summary}
              </p>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginTop: '0.5rem' }}>
                <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>Connector Freshness:</span>
                <FreshnessIndicator
                  lastSyncedAt={data.freshness.refreshed_at}
                  provider={data.display_name}
                />
              </div>
            </div>
          </div>

          {/* 4. Native Hierarchy Tree Explorer */}
          <div style={{ backgroundColor: 'var(--bg-secondary)', border: '1px solid var(--border-color)', borderRadius: '10px', padding: '1.5rem' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <Layers size={18} style={{ color: '#38bdf8' }} />
                <h3 style={{ fontSize: '1rem', fontWeight: 600, margin: 0 }}>
                  {data.display_name} Native Hierarchy Tree ({data.hierarchy_root_name})
                </h3>
              </div>
              <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
                Click node to expand/collapse
              </span>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
              {renderTree(data.hierarchy_tree)}
            </div>
          </div>
        </>
      )}
    </div>
  );
};

export default ProviderDashboard;
