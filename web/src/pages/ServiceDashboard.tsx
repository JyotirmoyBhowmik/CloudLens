import React, { useEffect, useState } from 'react';
import {
  Breadcrumb,
  BreadcrumbItem,
  CostValue,
  FreshnessIndicator,
  AccessibleChart,
} from '../design-system';
import {
  Server,
  DollarSign,
  Gift,
  TrendingUp,
  Cpu,
  Gauge,
  Network,
  ExternalLink,
  ShieldCheck,
  RefreshCw,
  AlertTriangle,
} from 'lucide-react';

interface ServiceDashboardData {
  service_id: string;
  service_code: string;
  service_name: string;
  provider: string;
  category: string;
  freshness: {
    refreshed_at: string;
    age_seconds: number;
    status: string;
  };
  description: string;
  pricing_model: string;
  free_tier_details: {
    eligible: boolean;
    monthly_allowance: string;
    tier_type: string;
  };
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
  budget_allocated: number | string;
  budget_utilisation_pct: number | string;
  active_instances_count: number;
  total_runtime_hours: number | string;
  runtime_status: string;
  metered_usage_quantity: number | string;
  usage_metric_name: string;
  pricing_units: string[];
  primary_cost_driver: string;
  secondary_cost_drivers: string[];
  upstream_dependencies: string[];
  downstream_dependencies: string[];
  network_endpoints_count: number;
  cross_region_egress_gb: number | string;
  historical_points: Array<{
    date: string;
    actual_cost: number | string;
    forecast_cost?: number | string | null;
  }>;
  documentation_url: string;
  finops_guidelines_url: string;
  pricing_source_name: string;
  pricing_source_effective_date: string;
  pricing_source_badge: string;
}

export const ServiceDashboard: React.FC = () => {
  const [selectedService, setSelectedService] = useState<string>('AmazonEC2');
  const [data, setData] = useState<ServiceDashboardData | null>(null);
  const [loading, setLoading] = useState<boolean>(true);

  useEffect(() => {
    setLoading(true);
    fetch(`/api/v1/dashboards/services/${selectedService}`)
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json();
      })
      .then((json: ServiceDashboardData) => {
        setData(json);
        setLoading(false);
      })
      .catch((err) => {
        console.error('Failed to load service dashboard:', err);
        setLoading(false);
      });
  }, [selectedService]);

  const breadcrumbs: BreadcrumbItem[] = [
    { label: 'Platform Home', href: '/' },
    { label: 'Cloud Services', href: '/dashboards/services' },
    { label: data ? data.service_name : selectedService, isCurrent: true },
  ];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem', width: '100%' }}>
      {/* 1. Header & Service Selector */}
      <div>
        <Breadcrumb items={breadcrumbs} />
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '0.75rem', flexWrap: 'wrap', gap: '1rem' }}>
          <div>
            <h1 style={{ fontSize: '1.75rem', fontWeight: 700, margin: 0, color: 'var(--text-primary)' }}>
              Service Deep-Dive: {data?.service_name || selectedService}
            </h1>
            <p style={{ margin: '0.25rem 0 0 0', fontSize: '0.875rem', color: 'var(--text-secondary)' }}>
              Comprehensive 16-panel evaluation of pricing mechanics, runtime telemetry, dependencies, and drivers.
            </p>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
            <span style={{ fontSize: '0.8125rem', color: 'var(--text-secondary)' }}>Select Service:</span>
            <select
              value={selectedService}
              onChange={(e) => setSelectedService(e.target.value)}
              aria-label="Target Cloud Service Selector"
              style={{
                backgroundColor: 'var(--bg-secondary)',
                border: '1px solid var(--border-color)',
                color: 'var(--text-primary)',
                padding: '0.4rem 0.8rem',
                borderRadius: '6px',
                fontWeight: 600,
                fontSize: '0.875rem',
              }}
            >
              <option value="AmazonEC2">Amazon EC2 (AWS Compute)</option>
              <option value="VirtualMachines">Azure Virtual Machines</option>
              <option value="AmazonRDS">Amazon RDS (AWS Database)</option>
              <option value="GoogleKubernetesEngine">Google Kubernetes Engine (GKE)</option>
            </select>
          </div>
        </div>
      </div>

      {loading && (
        <div style={{ padding: '3rem', textAlign: 'center', color: 'var(--text-secondary)' }}>
          <RefreshCw className="animate-spin" style={{ margin: '0 auto 1rem auto' }} />
          <p>Querying 16-panel service telemetry and rate card provenance...</p>
        </div>
      )}

      {!loading && !data && (
        <div style={{ padding: '2rem', textAlign: 'center' }}>
          <AlertTriangle style={{ color: '#ef4444', margin: '0 auto 1rem auto' }} />
          <p>Unable to retrieve service dashboard details.</p>
        </div>
      )}

      {!loading && data && (
        <>
          {/* Top Panel Grid: Panels 1-4 */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '1rem' }}>
            {/* Panel 1: Description & Classification */}
            <div style={{ backgroundColor: 'var(--bg-secondary)', border: '1px solid var(--border-color)', borderRadius: '10px', padding: '1.25rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.5rem' }}>
                <Server size={18} style={{ color: '#38bdf8' }} />
                <h3 style={{ fontSize: '0.9375rem', fontWeight: 600, margin: 0 }}>1. Description</h3>
              </div>
              <p style={{ fontSize: '0.8125rem', color: 'var(--text-secondary)', margin: '0 0 0.5rem 0' }}>
                {data.description}
              </p>
              <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
                <span style={{ fontSize: '0.75rem', backgroundColor: '#0284c7', color: '#e0f2fe', padding: '0.15rem 0.5rem', borderRadius: '4px', textTransform: 'uppercase' }}>
                  {data.provider}
                </span>
                <span style={{ fontSize: '0.75rem', backgroundColor: '#334155', color: '#e2e8f0', padding: '0.15rem 0.5rem', borderRadius: '4px' }}>
                  {data.category}
                </span>
              </div>
            </div>

            {/* Panel 2: Pricing Model */}
            <div style={{ backgroundColor: 'var(--bg-secondary)', border: '1px solid var(--border-color)', borderRadius: '10px', padding: '1.25rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.5rem' }}>
                <DollarSign size={18} style={{ color: '#34d399' }} />
                <h3 style={{ fontSize: '0.9375rem', fontWeight: 600, margin: 0 }}>2. Pricing Model</h3>
              </div>
              <p style={{ fontSize: '0.875rem', fontWeight: 600, color: 'var(--text-primary)', margin: 0 }}>
                {data.pricing_model}
              </p>
              <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', display: 'block', marginTop: '0.5rem' }}>
                Hourly blended amortization active
              </span>
            </div>

            {/* Panel 3: Free-Tier Details */}
            <div style={{ backgroundColor: 'var(--bg-secondary)', border: '1px solid var(--border-color)', borderRadius: '10px', padding: '1.25rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.5rem' }}>
                <Gift size={18} style={{ color: '#fbbf24' }} />
                <h3 style={{ fontSize: '0.9375rem', fontWeight: 600, margin: 0 }}>3. Free Tier</h3>
              </div>
              <div style={{ fontSize: '0.8125rem', fontWeight: 600, color: data.free_tier_details.eligible ? '#10b981' : 'var(--text-secondary)' }}>
                {data.free_tier_details.eligible ? 'Eligible' : 'Paid Only'}
              </div>
              <p style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', margin: '0.25rem 0 0 0' }}>
                {data.free_tier_details.monthly_allowance}
              </p>
            </div>

            {/* Panel 4: Actual Spend */}
            <div style={{ backgroundColor: 'var(--bg-secondary)', border: '1px solid var(--border-color)', borderRadius: '10px', padding: '1.25rem' }}>
              <span style={{ fontSize: '0.8125rem', color: 'var(--text-secondary)', fontWeight: 500 }}>
                4. Actual Spend
              </span>
              <div style={{ marginTop: '0.5rem' }}>
                <CostValue amount={Number(data.actual_cost.amount)} source="ACTUAL" currency="USD" />
              </div>
              <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
                Billed FOCUS reconciliation
              </span>
            </div>
          </div>

          {/* Second Row: Panels 5-8 */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '1rem' }}>
            {/* Panel 5: Estimated Spend */}
            <div style={{ backgroundColor: 'var(--bg-secondary)', border: '1px solid var(--border-color)', borderRadius: '10px', padding: '1.25rem' }}>
              <span style={{ fontSize: '0.8125rem', color: 'var(--text-secondary)', fontWeight: 500 }}>
                5. Estimated Spend
              </span>
              <div style={{ marginTop: '0.5rem' }}>
                <CostValue amount={Number(data.estimated_cost.amount)} source="ESTIMATED" currency="USD" />
              </div>
              <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
                Unbilled / Pre-deployment
              </span>
            </div>

            {/* Panel 6: Forecast */}
            <div style={{ backgroundColor: 'var(--bg-secondary)', border: '1px solid var(--border-color)', borderRadius: '10px', padding: '1.25rem' }}>
              <span style={{ fontSize: '0.8125rem', color: 'var(--text-secondary)', fontWeight: 500 }}>
                6. Month-End Forecast
              </span>
              <div style={{ marginTop: '0.5rem' }}>
                <CostValue amount={Number(data.forecast_cost.amount)} source="FORECAST" currency="USD" />
              </div>
              <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
                Trajectory at 95% confidence
              </span>
            </div>

            {/* Panel 7: Budget */}
            <div style={{ backgroundColor: 'var(--bg-secondary)', border: '1px solid var(--border-color)', borderRadius: '10px', padding: '1.25rem' }}>
              <span style={{ fontSize: '0.8125rem', color: 'var(--text-secondary)', fontWeight: 500 }}>
                7. Service Budget
              </span>
              <div style={{ fontSize: '1.5rem', fontWeight: 700, margin: '0.25rem 0', color: 'var(--text-primary)' }}>
                ${(Number(data.budget_allocated) / 1000).toFixed(0)}k
              </div>
              <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
                {Number(data.budget_utilisation_pct).toFixed(1)}% utilised
              </span>
            </div>

            {/* Panel 8: Runtime */}
            <div style={{ backgroundColor: 'var(--bg-secondary)', border: '1px solid var(--border-color)', borderRadius: '10px', padding: '1.25rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.25rem' }}>
                <Cpu size={18} style={{ color: '#38bdf8' }} />
                <span style={{ fontSize: '0.8125rem', color: 'var(--text-secondary)', fontWeight: 500 }}>
                  8. Runtime Footprint
                </span>
              </div>
              <div style={{ fontSize: '1.25rem', fontWeight: 700, color: 'var(--text-primary)' }}>
                {data.active_instances_count} Active Nodes
              </div>
              <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
                {Number(data.total_runtime_hours).toLocaleString()} hours in state {data.runtime_status}
              </span>
            </div>
          </div>

          {/* Third Row: Panels 9-11 */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: '1rem' }}>
            {/* Panel 9: Usage Volume */}
            <div style={{ backgroundColor: 'var(--bg-secondary)', border: '1px solid var(--border-color)', borderRadius: '10px', padding: '1.25rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.5rem' }}>
                <Gauge size={18} style={{ color: '#fbbf24' }} />
                <h3 style={{ fontSize: '0.9375rem', fontWeight: 600, margin: 0 }}>9. Metered Usage</h3>
              </div>
              <div style={{ fontSize: '1.5rem', fontWeight: 700, color: 'var(--text-primary)' }}>
                {Number(data.metered_usage_quantity).toLocaleString()}
              </div>
              <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
                {data.usage_metric_name} consumed
              </span>
            </div>

            {/* Panel 10: Pricing Units */}
            <div style={{ backgroundColor: 'var(--bg-secondary)', border: '1px solid var(--border-color)', borderRadius: '10px', padding: '1.25rem' }}>
              <h3 style={{ fontSize: '0.9375rem', fontWeight: 600, margin: '0 0 0.5rem 0' }}>10. Pricing Units</h3>
              <div style={{ display: 'flex', gap: '0.4rem', flexWrap: 'wrap' }}>
                {data.pricing_units.map((unit) => (
                  <span
                    key={unit}
                    style={{
                      fontSize: '0.75rem',
                      backgroundColor: 'var(--bg-primary)',
                      border: '1px solid var(--border-color)',
                      padding: '0.25rem 0.5rem',
                      borderRadius: '4px',
                    }}
                  >
                    {unit}
                  </span>
                ))}
              </div>
            </div>

            {/* Panel 11: Cost Drivers */}
            <div style={{ backgroundColor: 'var(--bg-secondary)', border: '1px solid var(--border-color)', borderRadius: '10px', padding: '1.25rem' }}>
              <h3 style={{ fontSize: '0.9375rem', fontWeight: 600, margin: '0 0 0.25rem 0' }}>11. Cost Drivers</h3>
              <div style={{ fontSize: '0.8125rem', fontWeight: 600, color: '#f87171' }}>
                Primary: {data.primary_cost_driver}
              </div>
              <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', marginTop: '0.25rem' }}>
                Secondaries: {data.secondary_cost_drivers.join(', ')}
              </div>
            </div>
          </div>

          {/* Fourth Row: Panels 12-14 */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(360px, 1fr))', gap: '1rem' }}>
            {/* Panel 12 & 13: Topology Dependencies & Connectivity */}
            <div style={{ backgroundColor: 'var(--bg-secondary)', border: '1px solid var(--border-color)', borderRadius: '10px', padding: '1.25rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.75rem' }}>
                <Network size={18} style={{ color: '#38bdf8' }} />
                <h3 style={{ fontSize: '0.9375rem', fontWeight: 600, margin: 0 }}>
                  12 & 13. Dependencies & Connectivity
                </h3>
              </div>
              <div style={{ fontSize: '0.8125rem', marginBottom: '0.4rem' }}>
                <strong>Upstream:</strong> {data.upstream_dependencies.join(', ')}
              </div>
              <div style={{ fontSize: '0.8125rem', marginBottom: '0.75rem' }}>
                <strong>Downstream:</strong> {data.downstream_dependencies.join(', ')}
              </div>
              <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
                {data.network_endpoints_count} Endpoints | Egress: {Number(data.cross_region_egress_gb)} GB
              </div>
            </div>

            {/* Panel 14: Historical Trend */}
            <div style={{ backgroundColor: 'var(--bg-secondary)', border: '1px solid var(--border-color)', borderRadius: '10px', padding: '1.25rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.75rem' }}>
                <TrendingUp size={18} style={{ color: '#34d399' }} />
                <h3 style={{ fontSize: '0.9375rem', fontWeight: 600, margin: 0 }}>
                  14. Historical Spend Trend
                </h3>
              </div>
              <AccessibleChart
                title="Service Trend"
                description="Historical and projected spend trajectory"
                data={data.historical_points.map((pt) => ({
                  label: pt.date.slice(5),
                  value: Number(pt.actual_cost),
                }))}
                currency="USD"
              />
            </div>
          </div>

          {/* Fifth Row: Panels 15-16 */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(360px, 1fr))', gap: '1rem' }}>
            {/* Panel 15: Documentation & FinOps Guides */}
            <div style={{ backgroundColor: 'var(--bg-secondary)', border: '1px solid var(--border-color)', borderRadius: '10px', padding: '1.25rem' }}>
              <h3 style={{ fontSize: '0.9375rem', fontWeight: 600, margin: '0 0 0.5rem 0' }}>
                15. Documentation & Guidelines
              </h3>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                <a
                  href={data.documentation_url}
                  target="_blank"
                  rel="noreferrer"
                  style={{ display: 'flex', alignItems: 'center', gap: '0.35rem', color: '#38bdf8', fontSize: '0.8125rem', textDecoration: 'none' }}
                >
                  <ExternalLink size={14} /> Official Provider Documentation
                </a>
                <a
                  href={data.finops_guidelines_url}
                  target="_blank"
                  rel="noreferrer"
                  style={{ display: 'flex', alignItems: 'center', gap: '0.35rem', color: '#38bdf8', fontSize: '0.8125rem', textDecoration: 'none' }}
                >
                  <ExternalLink size={14} /> FinOps Rate Optimization & Architecture Guide
                </a>
              </div>
            </div>

            {/* Panel 16: Pricing Source Provenance */}
            <div style={{ backgroundColor: 'var(--bg-secondary)', border: '1px solid var(--border-color)', borderRadius: '10px', padding: '1.25rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.5rem' }}>
                <ShieldCheck size={18} style={{ color: '#10b981' }} />
                <h3 style={{ fontSize: '0.9375rem', fontWeight: 600, margin: 0 }}>
                  16. Pricing Source Provenance
                </h3>
              </div>
              <div style={{ fontSize: '0.8125rem', fontWeight: 600, color: 'var(--text-primary)' }}>
                {data.pricing_source_name}
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '0.5rem' }}>
                <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
                  Effective: {data.pricing_source_effective_date}
                </span>
                <FreshnessIndicator
                  lastSyncedAt={data.freshness.refreshed_at}
                  provider={data.provider}
                />
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  );
};

export default ServiceDashboard;
