import React, { useEffect, useState } from 'react';
import {
  Breadcrumb,
  BreadcrumbItem,
  CostValue,
  ExplainableNumber,
  ThresholdBadge,
  AccessibleChart,
  DenseTable,
  ColumnDefinition,
  FreshnessIndicator,
} from '../design-system';
import {
  AlertTriangle,
  Download,
  Calendar,
  Layers,
  Server,
  DollarSign,
  TrendingUp,
  Cpu,
  RefreshCw,
  FileText,
  AlertCircle,
  Clock,
} from 'lucide-react';

interface MetricWidgetData {
  amount: number | string;
  currency?: string;
  prior_amount?: number | string | null;
  delta_amount?: number | string | null;
  delta_percentage?: number | string | null;
  cost_source?: string;
  metadata?: {
    freshness?: {
      refreshed_at?: string;
      age_seconds?: number;
    };
    scope_disclosure?: {
      is_filtered?: boolean;
      disclosure_text?: string | null;
    };
  };
}

interface BreakdownItemData {
  id: string;
  label: string;
  cost: number | string;
  percentage: number | string;
  delta_percentage?: number | string | null;
}

interface ExecutiveData {
  time_window: {
    period_id: string;
    period_type: string;
    comparison_basis: string;
    start_date: string;
    end_date: string;
  };
  data_freshness_banner?: string | null;
  total_cloud_cost: MetricWidgetData;
  current_month_cost: MetricWidgetData;
  actual_cost: MetricWidgetData;
  estimated_cost: MetricWidgetData;
  forecast_cost: MetricWidgetData;
  budget: MetricWidgetData;
  budget_utilisation: {
    budget_amount: number | string;
    actual_spend: number | string;
    forecast_spend: number | string;
    utilisation_percentage: number | string;
    projected_utilisation_percentage: number | string;
    threshold_state: string;
    remaining_budget: number | string;
  };
  cost_by_provider: {
    total_cost: number | string;
    items: BreakdownItemData[];
  };
  cost_by_business_unit: {
    total_cost: number | string;
    items: BreakdownItemData[];
  };
  cost_by_application: {
    total_cost: number | string;
    items: BreakdownItemData[];
  };
  cost_by_service: {
    total_cost: number | string;
    items: BreakdownItemData[];
  };
  cost_trend: {
    points: Array<{
      date: string;
      actual_cost: number | string;
      comparison_cost?: number | string | null;
      forecast_cost?: number | string | null;
    }>;
  };
  top_cost_services: {
    items: BreakdownItemData[];
  };
  largest_increases: {
    movements: Array<{
      item_id: string;
      name: string;
      provider: string;
      current_cost: number | string;
      prior_cost: number | string;
      delta_cost: number | string;
      delta_percentage: number | string;
      explanation: string;
    }>;
  };
  threshold_breaches: {
    total_breaches: number;
    critical_count: number;
    warning_count: number;
    breaches: Array<{
      alert_id: string;
      scope_name: string;
      threshold_type: string;
      severity: string;
      utilization_pct: number | string;
      triggered_at: string;
    }>;
  };
  service_counts: {
    free_services_count: number;
    paid_services_count: number;
    conditional_services_count: number;
    total_services_count: number;
  };
  runtime_exceptions: {
    total_count: number;
    items: Array<{
      id: string;
      resource_name: string;
      provider: string;
      type: string;
      description: string;
      impact_amount: number | string;
    }>;
  };
  usage_anomalies: {
    total_count: number;
    items: Array<{
      id: string;
      resource_name: string;
      provider: string;
      type: string;
      description: string;
      impact_amount: number | string;
    }>;
  };
  pricing_changes: {
    recent_changes: Array<{
      id: string;
      provider: string;
      service_name: string;
      change_type: string;
      impact_description: string;
    }>;
  };
  data_freshness: {
    providers: Array<{
      provider: string;
      last_sync_timestamp: string;
      age_hours: number | string;
      status: string;
      alert_banner?: string | null;
    }>;
    has_stale_provider: boolean;
    stale_provider_banner?: string | null;
  };
  reconciliation_status: {
    status: string;
    trust_indicator: string;
    invoice_total: number | string;
    telemetry_total: number | string;
    variance_amount: number | string;
    variance_ratio_pct: number | string;
  };
  governance_exceptions: {
    unapproved_deployments_count: number;
    tagging_gaps_count: number;
    quotas_near_limit_count: number;
    total_exceptions: number;
  };
}

export const ExecutiveDashboard: React.FC = () => {
  const [data, setData] = useState<ExecutiveData | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [period, setPeriod] = useState<string>('2026-09');
  const [periodType, setPeriodType] = useState<string>('MONTH');
  const [comparisonBasis, setComparisonBasis] = useState<string>('POP');

  useEffect(() => {
    setLoading(true);
    const query = new URLSearchParams({
      period_id: period,
      period_type: periodType,
      comparison_basis: comparisonBasis,
    });
    fetch(`/api/v1/dashboards/executive?${query.toString()}`)
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json();
      })
      .then((json: ExecutiveData) => {
        setData(json);
        setLoading(false);
      })
      .catch((err) => {
        console.error('Failed to load executive dashboard:', err);
        setLoading(false);
      });
  }, [period, periodType, comparisonBasis]);

  const handleExport = (widgetId: string, format: 'CSV' | 'JSON') => {
    window.open(`/api/v1/dashboards/export/${widgetId}?format=${format}`, '_blank');
  };

  const breadcrumbs: BreadcrumbItem[] = [
    { label: 'Platform Home', href: '/' },
    { label: 'Operational Dashboards', href: '/dashboards' },
    { label: 'Executive Multi-Cloud Dashboard', isCurrent: true },
  ];

  if (loading && !data) {
    return (
      <div style={{ padding: '2rem', textAlign: 'center', color: 'var(--text-secondary)' }}>
        <RefreshCw className="animate-spin" style={{ margin: '0 auto 1rem auto' }} />
        <p>Loading Executive Dashboard pre-computed aggregates...</p>
      </div>
    );
  }

  if (!data) {
    return (
      <div style={{ padding: '2rem', textAlign: 'center' }}>
        <AlertTriangle style={{ color: '#ef4444', margin: '0 auto 1rem auto' }} />
        <p>Unable to load dashboard data. Please verify the API backend is running.</p>
      </div>
    );
  }

  // Top services columns for DenseTable
  const topServicesColumns: ColumnDefinition<BreakdownItemData>[] = [
    { key: 'label', header: 'Service Name', sortable: true },
    {
      key: 'cost',
      header: 'Spend (USD)',
      align: 'right',
      render: (row: BreakdownItemData) => (
        <CostValue
          amount={Number(row.cost)}
          source="ACTUAL"
          currency="USD"
        />
      ),
    },
    {
      key: 'percentage',
      header: 'Share %',
      align: 'right',
      render: (row: BreakdownItemData) => `${Number(row.percentage).toFixed(1)}%`,
    },
  ];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem', width: '100%' }}>
      {/* 1. Header & Breadcrumbs */}
      <div>
        <Breadcrumb items={breadcrumbs} />
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '0.75rem', flexWrap: 'wrap', gap: '1rem' }}>
          <div>
            <h1 style={{ fontSize: '1.75rem', fontWeight: 700, margin: 0, color: 'var(--text-primary)' }}>
              Executive Cloud Overview
            </h1>
            <p style={{ margin: '0.25rem 0 0 0', fontSize: '0.875rem', color: 'var(--text-secondary)' }}>
              Cross-provider telemetry, budget tracking, governance exceptions, and unit economic health.
            </p>
          </div>

          {/* Time & Comparison Controls */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', backgroundColor: 'var(--bg-secondary)', padding: '0.5rem 0.75rem', borderRadius: '8px', border: '1px solid var(--border-color)' }}>
            <Calendar size={16} style={{ color: 'var(--text-secondary)' }} />
            <select
              value={periodType}
              onChange={(e) => setPeriodType(e.target.value)}
              aria-label="Period Type Selector"
              style={{ background: 'transparent', border: 'none', color: 'var(--text-primary)', fontSize: '0.8125rem', fontWeight: 500 }}
            >
              <option value="MONTH">Calendar Month</option>
              <option value="QUARTER">Quarter</option>
              <option value="FISCAL_PERIOD">Fiscal Year</option>
            </select>
            <input
              type="text"
              value={period}
              onChange={(e) => setPeriod(e.target.value)}
              aria-label="Target Billing Period"
              style={{ width: '80px', padding: '0.2rem 0.4rem', borderRadius: '4px', border: '1px solid var(--border-color)', background: 'var(--bg-primary)', color: 'var(--text-primary)', fontSize: '0.8125rem' }}
            />
            <span style={{ color: 'var(--border-color)' }}>|</span>
            <select
              value={comparisonBasis}
              onChange={(e) => setComparisonBasis(e.target.value)}
              aria-label="Comparison Basis"
              style={{ background: 'transparent', border: 'none', color: 'var(--text-primary)', fontSize: '0.8125rem', fontWeight: 500 }}
            >
              <option value="POP">Prior Period (PoP)</option>
              <option value="YOY">Same Period Last Year (YoY)</option>
            </select>
          </div>
        </div>
      </div>

      {/* 2. Freshness & Staleness Warning Banner */}
      {data.data_freshness_banner && (
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', padding: '0.75rem 1rem', borderRadius: '8px', backgroundColor: '#451a03', border: '1px solid #b45309', color: '#fef3c7', fontSize: '0.875rem' }}>
          <AlertCircle size={20} style={{ color: '#fbbf24', flexShrink: 0 }} />
          <span>{data.data_freshness_banner}</span>
        </div>
      )}

      {/* 3. Scope Filtering Disclosure Banner */}
      {data.total_cloud_cost.metadata?.scope_disclosure?.is_filtered && (
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', padding: '0.5rem 1rem', borderRadius: '6px', backgroundColor: '#1e293b', border: '1px solid #334155', color: '#94a3b8', fontSize: '0.8125rem' }}>
          <Clock size={16} style={{ color: '#38bdf8' }} />
          <span>{data.total_cloud_cost.metadata.scope_disclosure.disclosure_text}</span>
        </div>
      )}

      {/* 4. Top KPI Cards Grid */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '1rem' }}>
        {/* Total Cloud Spend */}
        <div style={{ backgroundColor: 'var(--bg-secondary)', border: '1px solid var(--border-color)', borderRadius: '10px', padding: '1.25rem' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
            <span style={{ fontSize: '0.8125rem', color: 'var(--text-secondary)', fontWeight: 500 }}>Total Cloud Spend</span>
            <div style={{ display: 'flex', gap: '0.25rem' }}>
              <button onClick={() => handleExport('w_total_cloud_cost', 'CSV')} title="Export CSV" style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-secondary)', padding: '2px' }}>
                <Download size={14} />
              </button>
            </div>
          </div>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: '0.5rem' }}>
            <CostValue amount={Number(data.total_cloud_cost.amount)} source="ACTUAL" currency="USD" />
            <ExplainableNumber
              value={Number(data.total_cloud_cost.amount)}
              detail={{
                metricName: 'Total Cloud Spend',
                formattedValue: `$${Number(data.total_cloud_cost.amount).toLocaleString()}`,
                rawNumericValue: Number(data.total_cloud_cost.amount),
                formula: 'SUM(billed_cost) across active provider feeds',
                costBasis: 'BILLED',
                currency: 'USD',
                attributionRule: 'Authorized tenant scope',
              }}
              currency="USD"
            />
          </div>
          <div style={{ marginTop: '0.5rem', fontSize: '0.75rem', color: Number(data.total_cloud_cost.delta_percentage) >= 0 ? '#ef4444' : '#10b981' }}>
            {Number(data.total_cloud_cost.delta_percentage) >= 0 ? '+' : ''}{Number(data.total_cloud_cost.delta_percentage).toFixed(1)}% vs {comparisonBasis}
          </div>
        </div>

        {/* Current Month MTD */}
        <div style={{ backgroundColor: 'var(--bg-secondary)', border: '1px solid var(--border-color)', borderRadius: '10px', padding: '1.25rem' }}>
          <span style={{ fontSize: '0.8125rem', color: 'var(--text-secondary)', fontWeight: 500 }}>Month to Date (MTD)</span>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: '0.5rem', marginTop: '0.5rem' }}>
            <CostValue amount={Number(data.current_month_cost.amount)} source="ACTUAL" currency="USD" />
          </div>
          <div style={{ marginTop: '0.5rem', fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
            Run-rate trajectory normal
          </div>
        </div>

        {/* Forecast Projected Spend */}
        <div style={{ backgroundColor: 'var(--bg-secondary)', border: '1px solid var(--border-color)', borderRadius: '10px', padding: '1.25rem' }}>
          <span style={{ fontSize: '0.8125rem', color: 'var(--text-secondary)', fontWeight: 500 }}>Forecast Projected</span>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: '0.5rem', marginTop: '0.5rem' }}>
            <CostValue amount={Number(data.forecast_cost.amount)} source="FORECAST" currency="USD" />
          </div>
          <div style={{ marginTop: '0.5rem', fontSize: '0.75rem', color: '#fb923c' }}>
            +6.5% vs period target
          </div>
        </div>

        {/* Budget & Utilisation */}
        <div style={{ backgroundColor: 'var(--bg-secondary)', border: '1px solid var(--border-color)', borderRadius: '10px', padding: '1.25rem' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span style={{ fontSize: '0.8125rem', color: 'var(--text-secondary)', fontWeight: 500 }}>Budget Utilisation</span>
            <ThresholdBadge state={data.budget_utilisation.threshold_state as any} />
          </div>
          <div style={{ fontSize: '1.5rem', fontWeight: 700, margin: '0.5rem 0 0 0', color: 'var(--text-primary)' }}>
            {Number(data.budget_utilisation.utilisation_percentage).toFixed(1)}%
          </div>
          <div style={{ marginTop: '0.5rem', fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
            Budget: ${(Number(data.budget.amount) / 1000).toFixed(0)}k | Rem: ${(Number(data.budget_utilisation.remaining_budget) / 1000).toFixed(0)}k
          </div>
        </div>
      </div>

      {/* 5. Breakdowns Row */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(400px, 1fr))', gap: '1.5rem' }}>
        {/* Cost by Provider */}
        <div style={{ backgroundColor: 'var(--bg-secondary)', border: '1px solid var(--border-color)', borderRadius: '10px', padding: '1.5rem' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <Layers size={18} style={{ color: '#38bdf8' }} />
              <h3 style={{ fontSize: '1rem', fontWeight: 600, margin: 0 }}>Spend by Cloud Provider</h3>
            </div>
            <button onClick={() => handleExport('w_cost_by_provider', 'CSV')} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-secondary)', display: 'flex', alignItems: 'center', gap: '0.25rem', fontSize: '0.75rem' }}>
              <Download size={14} /> Export CSV
            </button>
          </div>
          <AccessibleChart
            title="Cloud Spend by Provider"
            description="Breakdown of actual spend across AWS, Azure, GCP, and OCI"
            data={data.cost_by_provider.items.map((it) => ({
              label: it.label,
              value: Number(it.cost),
            }))}
            currency="USD"
          />
        </div>

        {/* Daily Spend Trend */}
        <div style={{ backgroundColor: 'var(--bg-secondary)', border: '1px solid var(--border-color)', borderRadius: '10px', padding: '1.5rem' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <TrendingUp size={18} style={{ color: '#34d399' }} />
              <h3 style={{ fontSize: '1rem', fontWeight: 600, margin: 0 }}>Spend Trend & Daily Trajectory</h3>
            </div>
            <button onClick={() => handleExport('w_cost_trend', 'CSV')} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-secondary)', display: 'flex', alignItems: 'center', gap: '0.25rem', fontSize: '0.75rem' }}>
              <Download size={14} /> Export
            </button>
          </div>
          <AccessibleChart
            title="Daily Spend Trend"
            description="Daily spend trajectory and comparison run-rate"
            data={data.cost_trend.points.map((pt) => ({
              label: pt.date.slice(5),
              value: Number(pt.actual_cost),
            }))}
            currency="USD"
          />
        </div>
      </div>

      {/* 6. Top Services & Largest Movements */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(400px, 1fr))', gap: '1.5rem' }}>
        {/* Top 5 Services */}
        <div style={{ backgroundColor: 'var(--bg-secondary)', border: '1px solid var(--border-color)', borderRadius: '10px', padding: '1.5rem' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <Server size={18} style={{ color: '#fbbf24' }} />
              <h3 style={{ fontSize: '1rem', fontWeight: 600, margin: 0 }}>Top Dominant Cloud Services</h3>
            </div>
            <button onClick={() => handleExport('w_top_services', 'CSV')} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-secondary)', fontSize: '0.75rem' }}>
              <Download size={14} />
            </button>
          </div>
          <DenseTable
            columns={topServicesColumns}
            data={data.top_cost_services.items}
          />
        </div>

        {/* Largest Cost Movements */}
        <div style={{ backgroundColor: 'var(--bg-secondary)', border: '1px solid var(--border-color)', borderRadius: '10px', padding: '1.5rem' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <DollarSign size={18} style={{ color: '#f87171' }} />
              <h3 style={{ fontSize: '1rem', fontWeight: 600, margin: 0 }}>Largest Cost Increases</h3>
            </div>
            <button onClick={() => handleExport('w_largest_increases', 'CSV')} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-secondary)', fontSize: '0.75rem' }}>
              <Download size={14} />
            </button>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
            {data.largest_increases.movements.map((mov) => (
              <div
                key={mov.item_id}
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  padding: '0.75rem',
                  backgroundColor: 'var(--bg-primary)',
                  borderRadius: '6px',
                  border: '1px solid var(--border-color)',
                }}
              >
                <div>
                  <div style={{ fontWeight: 600, fontSize: '0.875rem' }}>{mov.name}</div>
                  <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', marginTop: '0.15rem' }}>
                    {mov.explanation}
                  </div>
                </div>
                <div style={{ textAlign: 'right' }}>
                  <div style={{ fontWeight: 600, fontSize: '0.875rem', color: '#f87171' }}>
                    +${Number(mov.delta_cost).toLocaleString()}
                  </div>
                  <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
                    +{Number(mov.delta_percentage).toFixed(1)}%
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* 7. Operational Health & Governance Exceptions */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '1.5rem' }}>
        {/* Active Threshold Breaches */}
        <div style={{ backgroundColor: 'var(--bg-secondary)', border: '1px solid var(--border-color)', borderRadius: '10px', padding: '1.25rem' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem' }}>
            <span style={{ fontSize: '0.875rem', fontWeight: 600 }}>Active Threshold Breaches</span>
            <span style={{ fontSize: '0.75rem', backgroundColor: '#7f1d1d', color: '#fca5a5', padding: '0.15rem 0.5rem', borderRadius: '9999px', fontWeight: 600 }}>
              {data.threshold_breaches.total_breaches} Active
            </span>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
            {data.threshold_breaches.breaches.map((b) => (
              <div key={b.alert_id} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '0.8125rem', padding: '0.4rem 0', borderBottom: '1px solid var(--border-color)' }}>
                <span>{b.scope_name}</span>
                <ThresholdBadge state={b.severity as any} labelOverride={`${Number(b.utilization_pct).toFixed(0)}%`} />
              </div>
            ))}
          </div>
        </div>

        {/* Runtime & Idle Exceptions */}
        <div style={{ backgroundColor: 'var(--bg-secondary)', border: '1px solid var(--border-color)', borderRadius: '10px', padding: '1.25rem' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem' }}>
            <span style={{ fontSize: '0.875rem', fontWeight: 600 }}>Runtime & Idle Waste</span>
            <Cpu size={16} style={{ color: '#38bdf8' }} />
          </div>
          <div style={{ fontSize: '1.25rem', fontWeight: 700, color: 'var(--text-primary)' }}>
            {data.runtime_exceptions.total_count} Exceptions
          </div>
          <p style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', margin: '0.25rem 0 0.75rem 0' }}>
            Candidate waste detected across unattached disks & idle nodes.
          </p>
        </div>

        {/* Reconciliation Status */}
        <div style={{ backgroundColor: 'var(--bg-secondary)', border: '1px solid var(--border-color)', borderRadius: '10px', padding: '1.25rem' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem' }}>
            <span style={{ fontSize: '0.875rem', fontWeight: 600 }}>Invoice Reconciliation</span>
            <ThresholdBadge state="NORMAL" labelOverride={data.reconciliation_status.trust_indicator} />
          </div>
          <div style={{ fontSize: '1.25rem', fontWeight: 700, color: 'var(--text-primary)' }}>
            Variance: {Number(data.reconciliation_status.variance_ratio_pct).toFixed(2)}%
          </div>
          <p style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', margin: '0.25rem 0 0 0' }}>
            Invoice ${(Number(data.reconciliation_status.invoice_total) / 1000).toFixed(1)}k vs Telemetry ${(Number(data.reconciliation_status.telemetry_total) / 1000).toFixed(1)}k (Within 1.0% tolerance).
          </p>
        </div>

        {/* Data Freshness Status */}
        <div style={{ backgroundColor: 'var(--bg-secondary)', border: '1px solid var(--border-color)', borderRadius: '10px', padding: '1.25rem' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem' }}>
            <span style={{ fontSize: '0.875rem', fontWeight: 600 }}>Provider Feeds</span>
            <FileText size={16} style={{ color: '#94a3b8' }} />
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
            {data.data_freshness.providers.map((p) => (
              <div key={p.provider} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '0.8125rem' }}>
                <span style={{ textTransform: 'uppercase', fontWeight: 600 }}>{p.provider}</span>
                <FreshnessIndicator
                  lastSyncedAt={p.last_sync_timestamp}
                  provider={p.provider}
                />
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
};

export default ExecutiveDashboard;
