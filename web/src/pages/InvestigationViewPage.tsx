import React, { useEffect, useState } from 'react';
import {
  AlertTriangle,
  Layers,
  TrendingUp,
  Server,
  Tag,
} from 'lucide-react';
import { SkeletonLoader } from '../design-system/SkeletonLoader';
import { ErrorState } from '../design-system/ErrorState';

export interface DailySpendInvestigationPoint {
  date: string;
  spend: number;
  is_change_point: boolean;
  note?: string | null;
}

export interface ContributingResourceDelta {
  resource_id: string;
  resource_name: string;
  service_name: string;
  prior_spend: number;
  current_spend: number;
  delta_spend: number;
  percentage_contribution: number;
}

export interface ChangedPricingDimension {
  dimension_name: string;
  old_value: string;
  new_value: string;
  effective_date: string;
  impact_description: string;
}

export interface InventoryChangeWindowItem {
  timestamp: string;
  resource_id: string;
  resource_name: string;
  change_type: string;
  description: string;
}

export interface CostInvestigationReport {
  entity_id: string;
  entity_name: string;
  service_name: string;
  provider: string;
  change_point_date: string;
  prior_daily_spend: number;
  post_daily_spend: number;
  increase_amount: number;
  increase_percentage: number;
  is_restatement: boolean;
  restatement_note?: string | null;
  daily_series: DailySpendInvestigationPoint[];
  contributing_resources: ContributingResourceDelta[];
  changed_pricing_dimensions: ChangedPricingDimension[];
  inventory_changes: InventoryChangeWindowItem[];
  root_cause_summary: string;
}

export interface InvestigationViewPageProps {
  initialEntityId?: string;
  onNavigateToResourceDetail?: (resourceId: string) => void;
}

export const InvestigationViewPage: React.FC<InvestigationViewPageProps> = ({
  initialEntityId = 'res-aws-rds-01',
  onNavigateToResourceDetail,
}) => {
  const [entityId, setEntityId] = useState<string>(initialEntityId);
  const [report, setReport] = useState<CostInvestigationReport | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const presetSpikes = [
    { id: 'res-aws-rds-01', label: 'AWS RDS Postgres - prod-payments-db (+48.4% Spike)' },
    { id: 'res-az-sql-01', label: 'Azure SQL Database - sql-checkout-db (+9.1% Growth)' },
    { id: 'res-aws-vm-01', label: 'AWS EC2 - prod-payment-worker-1 (+3.2% Normal)' },
  ];

  const fetchInvestigationReport = () => {
    setLoading(true);
    setError(null);

    fetch(`/api/v1/resource-detail/investigate/${encodeURIComponent(entityId)}`)
      .then((res) => {
        if (!res.ok) {
          throw new Error(`Investigation report error ${res.status}`);
        }
        return res.json();
      })
      .then((data: CostInvestigationReport) => {
        setReport(data);
        setLoading(false);
      })
      .catch((err: Error) => {
        setError(err.message);
        setLoading(false);
      });
  };

  useEffect(() => {
    fetchInvestigationReport();
  }, [entityId]);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
      {/* Top Banner & Entity Switcher */}
      <div
        style={{
          backgroundColor: 'var(--bg-secondary)',
          border: '1px solid var(--border-color)',
          borderRadius: '8px',
          padding: '1.25rem 1.5rem',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          flexWrap: 'wrap',
          gap: '1rem',
        }}
      >
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', marginBottom: '0.25rem' }}>
            <span
              style={{
                fontSize: '0.75rem',
                fontWeight: 700,
                padding: '0.2rem 0.5rem',
                borderRadius: '4px',
                backgroundColor: 'rgba(239, 68, 68, 0.2)',
                color: '#f87171',
                border: '1px solid #ef4444',
              }}
            >
              LARGEST INCREASES INVESTIGATION
            </span>
            <h1 style={{ fontSize: '1.5rem', fontWeight: 700, margin: 0 }}>
              Cost Spike & Discontinuity Analysis
            </h1>
          </div>
          <p style={{ margin: 0, fontSize: '0.875rem', color: 'var(--text-secondary)' }}>
            Deep-dive diagnosis into sudden cost movement, changed pricing dimensions, and inventory change window events.
          </p>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <label htmlFor="spike-entity-select" style={{ fontSize: '0.8125rem', fontWeight: 600, color: 'var(--text-secondary)' }}>Investigate Entity:</label>
          <select
            id="spike-entity-select"
            value={entityId}
            onChange={(e) => setEntityId(e.target.value)}
            style={{
              padding: '0.45rem 0.75rem',
              borderRadius: '6px',
              border: '1px solid var(--border-color)',
              backgroundColor: 'var(--bg-primary)',
              color: 'var(--text-primary)',
              fontSize: '0.875rem',
              fontWeight: 500,
            }}
          >
            {presetSpikes.map((p) => (
              <option key={p.id} value={p.id}>
                {p.label}
              </option>
            ))}
          </select>
        </div>
      </div>

      {loading ? (
        <SkeletonLoader variant="card" rows={3} />
      ) : error ? (
        <ErrorState title="Diagnosis Failed" message={error} onRetry={fetchInvestigationReport} />
      ) : report ? (
        <>
          {/* Highlighted Change Point Banner */}
          <div
            style={{
              backgroundColor: 'rgba(239, 68, 68, 0.08)',
              border: '1px solid #ef4444',
              borderRadius: '8px',
              padding: '1.25rem 1.5rem',
              display: 'flex',
              flexDirection: 'column',
              gap: '1rem',
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '1rem' }}>
              <div>
                <span style={{ fontSize: '0.75rem', fontWeight: 700, color: '#f87171', display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
                  <AlertTriangle size={15} /> DETECTED CHANGE POINT DISCONTINUITY
                </span>
                <h2 style={{ fontSize: '1.25rem', fontWeight: 700, margin: '0.35rem 0', color: 'var(--text-primary)' }}>
                  {report.entity_name} ({report.service_name} • {report.provider})
                </h2>
                <div style={{ fontSize: '0.875rem', color: 'var(--text-secondary)' }}>
                  Change Point Detected on <strong>{report.change_point_date}</strong> • Daily spend jumped from ${report.prior_daily_spend.toFixed(2)} to ${report.post_daily_spend.toFixed(2)}/day
                </div>
              </div>

              <div style={{ display: 'flex', gap: '1.5rem', alignItems: 'center' }}>
                <div style={{ textAlign: 'right' }}>
                  <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>Spike Delta</span>
                  <div style={{ fontSize: '1.5rem', fontWeight: 700, color: '#f87171' }}>
                    +${report.increase_amount.toFixed(2)} USD
                  </div>
                </div>
                <div style={{ textAlign: 'right' }}>
                  <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>Percentage Increase</span>
                  <div style={{ fontSize: '1.5rem', fontWeight: 700, color: '#f87171' }}>
                    +{report.increase_percentage.toFixed(1)}%
                  </div>
                </div>
                <div style={{ textAlign: 'right' }}>
                  <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>Restatement Flag</span>
                  <div style={{ fontSize: '0.875rem', fontWeight: 700, color: report.is_restatement ? '#fbbf24' : '#10b981' }}>
                    {report.is_restatement ? 'RESTATED' : 'STANDARD'}
                  </div>
                </div>
              </div>
            </div>

            {/* Root Cause Summary Card */}
            <div
              style={{
                backgroundColor: 'var(--bg-secondary)',
                border: '1px solid var(--border-color)',
                borderRadius: '6px',
                padding: '1rem',
                fontSize: '0.875rem',
                lineHeight: 1.5,
              }}
            >
              <strong style={{ color: '#38bdf8', display: 'block', marginBottom: '0.25rem' }}>
                Automated Root Cause Diagnosis:
              </strong>
              {report.root_cause_summary}
            </div>
          </div>

          {/* Daily Spend Series with Highlighted Change Point */}
          <div
            style={{
              backgroundColor: 'var(--bg-secondary)',
              border: '1px solid var(--border-color)',
              borderRadius: '8px',
              padding: '1.25rem',
            }}
          >
            <h3 style={{ margin: '0 0 1rem 0', fontSize: '1.125rem', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
              <TrendingUp size={18} color="#0284c7" /> Daily Spend Series (Change Point Discontinuity Highlighted)
            </h3>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(130px, 1fr))', gap: '0.75rem' }}>
              {report.daily_series.map((pt, idx) => (
                <div
                  key={idx}
                  style={{
                    backgroundColor: pt.is_change_point ? 'rgba(239, 68, 68, 0.15)' : 'var(--bg-primary)',
                    border: pt.is_change_point ? '2px solid #ef4444' : '1px solid var(--border-color)',
                    borderRadius: '6px',
                    padding: '0.75rem',
                    textAlign: 'center',
                    position: 'relative',
                  }}
                >
                  {pt.is_change_point && (
                    <span
                      style={{
                        position: 'absolute',
                        top: '-10px',
                        left: '50%',
                        transform: 'translateX(-50%)',
                        backgroundColor: '#ef4444',
                        color: '#ffffff',
                        fontSize: '0.65rem',
                        fontWeight: 700,
                        padding: '0.1rem 0.4rem',
                        borderRadius: '9999px',
                        whiteSpace: 'nowrap',
                      }}
                    >
                      CHANGE POINT
                    </span>
                  )}
                  <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', display: 'block', marginBottom: '0.25rem' }}>
                    {pt.date}
                  </span>
                  <div style={{ fontSize: '1.125rem', fontWeight: 700, color: pt.is_change_point ? '#f87171' : 'var(--text-primary)' }}>
                    ${pt.spend.toFixed(2)}
                  </div>
                  {pt.note && (
                    <div style={{ fontSize: '0.7rem', color: '#f87171', marginTop: '0.35rem', lineHeight: 1.2 }}>
                      {pt.note}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>

          {/* Contributing Resources & Changed Pricing Dimensions */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(420px, 1fr))', gap: '1.5rem' }}>
            {/* Contributing Resources Delta Table */}
            <div
              style={{
                backgroundColor: 'var(--bg-secondary)',
                border: '1px solid var(--border-color)',
                borderRadius: '8px',
                padding: '1.25rem',
              }}
            >
              <h3 style={{ margin: '0 0 0.75rem 0', fontSize: '1.125rem', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                <Server size={18} color="#06b6d4" /> Contributing Resources Delta
              </h3>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.8125rem' }}>
                <thead>
                  <tr style={{ borderBottom: '1px solid var(--border-color)', textAlign: 'left', color: 'var(--text-secondary)' }}>
                    <th style={{ padding: '0.5rem' }}>Resource</th>
                    <th style={{ padding: '0.5rem', textAlign: 'right' }}>Prior Spend</th>
                    <th style={{ padding: '0.5rem', textAlign: 'right' }}>Current Spend</th>
                    <th style={{ padding: '0.5rem', textAlign: 'right' }}>Delta</th>
                    <th style={{ padding: '0.5rem', textAlign: 'right' }}>% Contrib</th>
                    {onNavigateToResourceDetail && <th style={{ padding: '0.5rem' }}>Action</th>}
                  </tr>
                </thead>
                <tbody>
                  {report.contributing_resources.map((res) => (
                    <tr key={res.resource_id} style={{ borderBottom: '1px solid var(--border-color)' }}>
                      <td style={{ padding: '0.5rem', fontWeight: 600 }}>{res.resource_name}</td>
                      <td style={{ padding: '0.5rem', textAlign: 'right' }}>${res.prior_spend.toFixed(2)}</td>
                      <td style={{ padding: '0.5rem', textAlign: 'right' }}>${res.current_spend.toFixed(2)}</td>
                      <td style={{ padding: '0.5rem', textAlign: 'right', fontWeight: 700, color: '#f87171' }}>
                        +${res.delta_spend.toFixed(2)}
                      </td>
                      <td style={{ padding: '0.5rem', textAlign: 'right' }}>{res.percentage_contribution}%</td>
                      {onNavigateToResourceDetail && (
                        <td style={{ padding: '0.5rem' }}>
                          <button
                            onClick={() => onNavigateToResourceDetail(res.resource_id)}
                            style={{
                              padding: '0.2rem 0.4rem',
                              borderRadius: '4px',
                              border: '1px solid var(--border-color)',
                              backgroundColor: 'var(--bg-primary)',
                              color: '#38bdf8',
                              cursor: 'pointer',
                              fontSize: '0.75rem',
                            }}
                          >
                            Inspect
                          </button>
                        </td>
                      )}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Changed Pricing Dimensions */}
            <div
              style={{
                backgroundColor: 'var(--bg-secondary)',
                border: '1px solid var(--border-color)',
                borderRadius: '8px',
                padding: '1.25rem',
              }}
            >
              <h3 style={{ margin: '0 0 0.75rem 0', fontSize: '1.125rem', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                <Tag size={18} color="#eab308" /> Changed Pricing Dimensions Detected
              </h3>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
                {report.changed_pricing_dimensions.map((dim, idx) => (
                  <div
                    key={idx}
                    style={{
                      backgroundColor: 'var(--bg-primary)',
                      border: '1px solid var(--border-color)',
                      borderRadius: '6px',
                      padding: '0.75rem',
                      fontSize: '0.8125rem',
                    }}
                  >
                    <div style={{ fontWeight: 700, color: '#fbbf24', marginBottom: '0.25rem' }}>
                      {dim.dimension_name}
                    </div>
                    <div style={{ display: 'flex', gap: '0.75rem', color: 'var(--text-secondary)', marginBottom: '0.25rem' }}>
                      <span><strong>Old:</strong> {dim.old_value}</span>
                      <span><strong>New:</strong> {dim.new_value}</span>
                    </div>
                    <div style={{ color: 'var(--text-primary)', fontSize: '0.75rem' }}>
                      {dim.impact_description}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* Inventory Changes in the Window */}
          <div
            style={{
              backgroundColor: 'var(--bg-secondary)',
              border: '1px solid var(--border-color)',
              borderRadius: '8px',
              padding: '1.25rem',
            }}
          >
            <h3 style={{ margin: '0 0 0.75rem 0', fontSize: '1.125rem', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
              <Layers size={18} color="#8b5cf6" /> Inventory Events in Change Window
            </h3>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
              {report.inventory_changes.map((chg, idx) => (
                <div
                  key={idx}
                  style={{
                    backgroundColor: 'var(--bg-primary)',
                    border: '1px solid var(--border-color)',
                    borderRadius: '6px',
                    padding: '0.75rem',
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    fontSize: '0.8125rem',
                  }}
                >
                  <div>
                    <span style={{ fontWeight: 700, color: '#38bdf8', marginRight: '0.5rem' }}>
                      [{chg.change_type}]
                    </span>
                    <span style={{ color: 'var(--text-primary)' }}>{chg.description}</span>
                  </div>
                  <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
                    {new Date(chg.timestamp).toLocaleString()}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </>
      ) : null}
    </div>
  );
};

export default InvestigationViewPage;
