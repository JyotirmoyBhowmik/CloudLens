import React, { useEffect, useState } from 'react';
import {
  TrendingUp,
  Layers,
  FileSpreadsheet,
  X,
} from 'lucide-react';
import { SkeletonLoader } from '../design-system/SkeletonLoader';
import { ErrorState } from '../design-system/ErrorState';

export interface CostExplorerSeriesPoint {
  timestamp: string;
  amount: number;
}

export interface CostExplorerGroup {
  group_id: string;
  group_name: string;
  total_cost: number;
  percentage: number;
  series: CostExplorerSeriesPoint[];
  contributing_resource_count: number;
}

export interface CostDriverItem {
  category: string;
  name: string;
  amount: number;
  percentage: number;
  unit: string;
  quantity: number;
  rate: number;
  explanation: string;
}

export interface CostExplorerResponse {
  dimension: string;
  granularity: string;
  total_spend: number;
  currency: string;
  groups: CostExplorerGroup[];
  comparison_total_spend?: number | null;
  variance_pct?: number | null;
  cost_drivers: CostDriverItem[];
}

export interface ChargeLineItem {
  charge_id: string;
  resource_id: string;
  resource_name: string;
  provider: string;
  service_name: string;
  usage_date: string;
  charge_category: string;
  description: string;
  quantity: number;
  unit: string;
  rate: number;
  amount: number;
  currency: string;
}

export interface ChargeLinesResponse {
  total_count: number;
  limit: number;
  offset: number;
  total_amount: number;
  currency: string;
  items: ChargeLineItem[];
}

export interface CostExplorerPageProps {
  initialDimension?: string;
  initialGroupId?: string;
  onNavigateToResourceDetail?: (resourceId: string) => void;
}

export const CostExplorerPage: React.FC<CostExplorerPageProps> = ({
  initialDimension = 'SERVICE',
  initialGroupId,
  onNavigateToResourceDetail,
}) => {
  const [dimension, setDimension] = useState<string>(initialDimension);
  const [granularity, setGranularity] = useState<string>('DAILY');
  const [comparisonPeriod, setComparisonPeriod] = useState<string>('NONE');
  const [providerFilter, setProviderFilter] = useState<string>('ALL');

  const [data, setData] = useState<CostExplorerResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // Drill-through Charge Lines Modal State
  const [activeDrillGroup, setActiveDrillGroup] = useState<string | null>(initialGroupId || null);
  const [chargeLines, setChargeLines] = useState<ChargeLinesResponse | null>(null);
  const [chargeLinesLoading, setChargeLinesLoading] = useState<boolean>(false);

  const fetchExplorerData = () => {
    setLoading(true);
    setError(null);

    const payload: Record<string, any> = {
      dimension,
      granularity,
      comparison_period: comparisonPeriod === 'NONE' ? null : comparisonPeriod,
      filters: {},
    };

    if (providerFilter !== 'ALL') {
      payload.filters.provider = [providerFilter];
    }

    fetch('/api/v1/resource-detail/explorer', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
      .then((res) => {
        if (!res.ok) {
          throw new Error(`Explorer error ${res.status}`);
        }
        return res.json();
      })
      .then((resData: CostExplorerResponse) => {
        setData(resData);
        setLoading(false);
      })
      .catch((err: Error) => {
        setError(err.message);
        setLoading(false);
      });
  };

  useEffect(() => {
    fetchExplorerData();
  }, [dimension, granularity, comparisonPeriod, providerFilter]);

  const loadChargeLines = (groupId: string) => {
    setActiveDrillGroup(groupId);
    setChargeLinesLoading(true);

    fetch(`/api/v1/resource-detail/explorer/charge-lines?group_id=${encodeURIComponent(groupId)}&dimension=${encodeURIComponent(dimension)}`)
      .then((res) => {
        if (!res.ok) {
          throw new Error(`Charge lines query failed: ${res.status}`);
        }
        return res.json();
      })
      .then((resLines: ChargeLinesResponse) => {
        setChargeLines(resLines);
        setChargeLinesLoading(false);
      })
      .catch(() => {
        setChargeLinesLoading(false);
      });
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
      {/* Top Banner */}
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
          <h1 style={{ fontSize: '1.5rem', fontWeight: 700, margin: '0 0 0.35rem 0', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <TrendingUp size={22} color="#0284c7" /> Cost Detail & Exploration
          </h1>
          <p style={{ margin: 0, fontSize: '0.875rem', color: 'var(--text-secondary)' }}>
            Group by any dimension, choose granularity, compare periods, and drill to itemized financial charge lines.
          </p>
        </div>

        {data && (
          <div style={{ textAlign: 'right' }}>
            <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', display: 'block' }}>Total Filtered Spend</span>
            <span style={{ fontSize: '1.5rem', fontWeight: 700, color: '#10b981' }}>
              ${data.total_spend.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })} USD
            </span>
            {data.comparison_total_spend != null && (
              <span style={{ display: 'block', fontSize: '0.75rem', color: '#f87171' }}>
                Prior: ${data.comparison_total_spend.toFixed(2)} (
                {data.variance_pct != null ? `${data.variance_pct > 0 ? '+' : ''}${data.variance_pct}%` : ''})
              </span>
            )}
          </div>
        )}
      </div>

      {/* Control Bar: Dimensions, Granularity, Comparisons, Filters */}
      <div
        style={{
          display: 'flex',
          gap: '1rem',
          alignItems: 'center',
          flexWrap: 'wrap',
          backgroundColor: 'var(--bg-secondary)',
          border: '1px solid var(--border-color)',
          borderRadius: '8px',
          padding: '1rem 1.25rem',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <label htmlFor="dimension-select" style={{ fontSize: '0.8125rem', fontWeight: 600, color: 'var(--text-secondary)' }}>Dimension:</label>
          <select
            id="dimension-select"
            value={dimension}
            onChange={(e) => setDimension(e.target.value)}
            style={{
              padding: '0.4rem 0.6rem',
              borderRadius: '6px',
              border: '1px solid var(--border-color)',
              backgroundColor: 'var(--bg-primary)',
              color: 'var(--text-primary)',
              fontSize: '0.8125rem',
              fontWeight: 600,
            }}
          >
            <option value="SERVICE">Service</option>
            <option value="PROVIDER">Cloud Provider</option>
            <option value="ACCOUNT">Billing Boundary / Account</option>
            <option value="REGION">Region</option>
            <option value="APPLICATION">Application</option>
            <option value="ENVIRONMENT">Environment</option>
            <option value="COST_CENTRE">Cost Centre</option>
            <option value="OWNER">Owner</option>
            <option value="CHARGE_CATEGORY">Charge Category</option>
          </select>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <label htmlFor="granularity-select" style={{ fontSize: '0.8125rem', fontWeight: 600, color: 'var(--text-secondary)' }}>Granularity:</label>
          <select
            id="granularity-select"
            value={granularity}
            onChange={(e) => setGranularity(e.target.value)}
            style={{
              padding: '0.4rem 0.6rem',
              borderRadius: '6px',
              border: '1px solid var(--border-color)',
              backgroundColor: 'var(--bg-primary)',
              color: 'var(--text-primary)',
              fontSize: '0.8125rem',
            }}
          >
            <option value="HOURLY">Hourly (Last 24h)</option>
            <option value="DAILY">Daily (Last 14d)</option>
            <option value="MONTHLY">Monthly (Last 6mo)</option>
          </select>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <label htmlFor="comparison-select" style={{ fontSize: '0.8125rem', fontWeight: 600, color: 'var(--text-secondary)' }}>Compare:</label>
          <select
            id="comparison-select"
            value={comparisonPeriod}
            onChange={(e) => setComparisonPeriod(e.target.value)}
            style={{
              padding: '0.4rem 0.6rem',
              borderRadius: '6px',
              border: '1px solid var(--border-color)',
              backgroundColor: 'var(--bg-primary)',
              color: 'var(--text-primary)',
              fontSize: '0.8125rem',
            }}
          >
            <option value="NONE">None</option>
            <option value="POP">Period over Period (PoP)</option>
            <option value="YOY">Year over Year (YoY)</option>
          </select>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <label htmlFor="provider-filter-select" style={{ fontSize: '0.8125rem', fontWeight: 600, color: 'var(--text-secondary)' }}>Provider Filter:</label>
          <select
            id="provider-filter-select"
            value={providerFilter}
            onChange={(e) => setProviderFilter(e.target.value)}
            style={{
              padding: '0.4rem 0.6rem',
              borderRadius: '6px',
              border: '1px solid var(--border-color)',
              backgroundColor: 'var(--bg-primary)',
              color: 'var(--text-primary)',
              fontSize: '0.8125rem',
            }}
          >
            <option value="ALL">All Providers</option>
            <option value="AWS">AWS Only</option>
            <option value="Azure">Azure Only</option>
            <option value="GCP">GCP Only</option>
            <option value="OCI">OCI Only</option>
          </select>
        </div>
      </div>

      {loading ? (
        <SkeletonLoader variant="table" rows={5} />
      ) : error ? (
        <ErrorState title="Exploration Failed" message={error} onRetry={fetchExplorerData} />
      ) : data ? (
        <>
          {/* Main Aggregations Table */}
          <div
            style={{
              backgroundColor: 'var(--bg-secondary)',
              border: '1px solid var(--border-color)',
              borderRadius: '8px',
              padding: '1.25rem',
            }}
          >
            <h3 style={{ margin: '0 0 1rem 0', fontSize: '1.125rem', fontWeight: 700 }}>
              Grouped Aggregations by {dimension}
            </h3>

            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.875rem' }}>
                <thead>
                  <tr style={{ borderBottom: '1px solid var(--border-color)', textAlign: 'left', color: 'var(--text-secondary)' }}>
                    <th style={{ padding: '0.6rem 0.75rem' }}>Group / Entity</th>
                    <th style={{ padding: '0.6rem 0.75rem', textAlign: 'right' }}>Resources</th>
                    <th style={{ padding: '0.6rem 0.75rem', textAlign: 'right' }}>Total Spend</th>
                    <th style={{ padding: '0.6rem 0.75rem', textAlign: 'right' }}>% Share</th>
                    <th style={{ padding: '0.6rem 0.75rem' }}>Trend Series</th>
                    <th style={{ padding: '0.6rem 0.75rem', textAlign: 'right' }}>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {data.groups.map((group) => (
                    <tr key={group.group_id} style={{ borderBottom: '1px solid var(--border-color)' }}>
                      <td style={{ padding: '0.6rem 0.75rem', fontWeight: 600 }}>{group.group_name}</td>
                      <td style={{ padding: '0.6rem 0.75rem', textAlign: 'right' }}>{group.contributing_resource_count}</td>
                      <td style={{ padding: '0.6rem 0.75rem', textAlign: 'right', fontWeight: 700, color: '#10b981' }}>
                        ${group.total_cost.toFixed(2)}
                      </td>
                      <td style={{ padding: '0.6rem 0.75rem', textAlign: 'right' }}>
                        <div style={{ display: 'inline-flex', alignItems: 'center', gap: '0.4rem' }}>
                          <div
                            style={{
                              width: '40px',
                              height: '6px',
                              backgroundColor: 'rgba(2, 132, 199, 0.2)',
                              borderRadius: '3px',
                              overflow: 'hidden',
                            }}
                          >
                            <div
                              style={{
                                width: `${Math.min(group.percentage, 100)}%`,
                                height: '100%',
                                backgroundColor: '#0284c7',
                              }}
                            />
                          </div>
                          <span>{group.percentage}%</span>
                        </div>
                      </td>
                      <td style={{ padding: '0.6rem 0.75rem' }}>
                        <div style={{ display: 'flex', alignItems: 'flex-end', gap: '2px', height: '24px' }}>
                          {group.series.slice(-10).map((pt, pIdx) => {
                            const maxVal = Math.max(...group.series.map((s) => s.amount), 1);
                            const barHeight = Math.max(Math.round((pt.amount / maxVal) * 20), 2);
                            return (
                              <div
                                key={pIdx}
                                title={`${pt.timestamp}: $${pt.amount}`}
                                style={{
                                  width: '6px',
                                  height: `${barHeight}px`,
                                  backgroundColor: '#38bdf8',
                                  borderRadius: '1px',
                                }}
                              />
                            );
                          })}
                        </div>
                      </td>
                      <td style={{ padding: '0.6rem 0.75rem', textAlign: 'right' }}>
                        <button
                          onClick={() => loadChargeLines(group.group_id)}
                          style={{
                            padding: '0.3rem 0.6rem',
                            borderRadius: '4px',
                            border: '1px solid #0284c7',
                            backgroundColor: 'rgba(2, 132, 199, 0.1)',
                            color: '#38bdf8',
                            fontSize: '0.75rem',
                            fontWeight: 600,
                            cursor: 'pointer',
                          }}
                        >
                          Drill Charge Lines
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* Estate Cost Drivers Breakdown */}
          <div
            style={{
              backgroundColor: 'var(--bg-secondary)',
              border: '1px solid var(--border-color)',
              borderRadius: '8px',
              padding: '1.25rem',
            }}
          >
            <h3 style={{ margin: '0 0 0.75rem 0', fontSize: '1.125rem', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
              <Layers size={18} color="#0284c7" /> Estate-Wide Cost Drivers Decomposition
            </h3>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: '1rem' }}>
              {data.cost_drivers.map((drv, idx) => (
                <div
                  key={idx}
                  style={{
                    backgroundColor: 'var(--bg-primary)',
                    padding: '1rem',
                    borderRadius: '6px',
                    border: '1px solid var(--border-color)',
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.35rem' }}>
                    <span style={{ fontSize: '0.75rem', fontWeight: 700, color: 'var(--text-secondary)' }}>{drv.category}</span>
                    <span style={{ fontSize: '0.75rem', fontWeight: 700, color: '#38bdf8' }}>{drv.percentage}%</span>
                  </div>
                  <div style={{ fontSize: '1.125rem', fontWeight: 700, color: 'var(--text-primary)', marginBottom: '0.25rem' }}>
                    ${drv.amount.toFixed(2)} USD
                  </div>
                  <div style={{ fontSize: '0.8125rem', color: 'var(--text-secondary)' }}>{drv.name}</div>
                  <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', marginTop: '0.5rem' }}>{drv.explanation}</div>
                </div>
              ))}
            </div>
          </div>
        </>
      ) : null}

      {/* Drill-Through Charge Lines Drawer / Modal */}
      {activeDrillGroup && (
        <div
          style={{
            position: 'fixed',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            backgroundColor: 'rgba(0, 0, 0, 0.75)',
            display: 'flex',
            justifyContent: 'center',
            alignItems: 'center',
            zIndex: 1000,
            padding: '2rem',
          }}
        >
          <div
            style={{
              backgroundColor: 'var(--bg-secondary)',
              border: '1px solid var(--border-color)',
              borderRadius: '8px',
              maxWidth: '1000px',
              width: '100%',
              maxHeight: '90vh',
              display: 'flex',
              flexDirection: 'column',
              boxShadow: '0 20px 25px -5px rgba(0, 0, 0, 0.5)',
            }}
          >
            <div
              style={{
                padding: '1.25rem 1.5rem',
                borderBottom: '1px solid var(--border-color)',
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
              }}
            >
              <div>
                <h3 style={{ margin: 0, fontSize: '1.125rem', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                  <FileSpreadsheet size={18} color="#10b981" /> Itemized Financial Charge Lines Drill-Down
                </h3>
                <span style={{ fontSize: '0.8125rem', color: 'var(--text-secondary)' }}>
                  Filtered Group: <strong>{activeDrillGroup}</strong> (Governed by Financial Detail Permission)
                </span>
              </div>
              <button
                onClick={() => setActiveDrillGroup(null)}
                style={{
                  background: 'transparent',
                  border: 'none',
                  color: 'var(--text-secondary)',
                  cursor: 'pointer',
                  padding: '0.25rem',
                }}
              >
                <X size={20} />
              </button>
            </div>

            <div style={{ padding: '1.5rem', overflowY: 'auto', flex: 1 }}>
              {chargeLinesLoading ? (
                <SkeletonLoader variant="table" rows={4} />
              ) : chargeLines && chargeLines.items.length > 0 ? (
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.8125rem' }}>
                  <thead>
                    <tr style={{ borderBottom: '1px solid var(--border-color)', textAlign: 'left', color: 'var(--text-secondary)' }}>
                      <th style={{ padding: '0.5rem' }}>Date</th>
                      <th style={{ padding: '0.5rem' }}>Resource</th>
                      <th style={{ padding: '0.5rem' }}>Category</th>
                      <th style={{ padding: '0.5rem' }}>Description</th>
                      <th style={{ padding: '0.5rem', textAlign: 'right' }}>Qty & Unit</th>
                      <th style={{ padding: '0.5rem', textAlign: 'right' }}>Rate</th>
                      <th style={{ padding: '0.5rem', textAlign: 'right' }}>Amount</th>
                      {onNavigateToResourceDetail && <th style={{ padding: '0.5rem' }}>Detail</th>}
                    </tr>
                  </thead>
                  <tbody>
                    {chargeLines.items.map((line) => (
                      <tr key={line.charge_id} style={{ borderBottom: '1px solid var(--border-color)' }}>
                        <td style={{ padding: '0.5rem' }}>{line.usage_date}</td>
                        <td style={{ padding: '0.5rem', fontWeight: 600 }}>{line.resource_name}</td>
                        <td style={{ padding: '0.5rem' }}>{line.charge_category}</td>
                        <td style={{ padding: '0.5rem', color: 'var(--text-secondary)' }}>{line.description}</td>
                        <td style={{ padding: '0.5rem', textAlign: 'right' }}>{line.quantity} {line.unit}</td>
                        <td style={{ padding: '0.5rem', textAlign: 'right' }}>${line.rate.toFixed(4)}</td>
                        <td style={{ padding: '0.5rem', textAlign: 'right', fontWeight: 700, color: '#10b981' }}>
                          ${line.amount.toFixed(2)}
                        </td>
                        {onNavigateToResourceDetail && (
                          <td style={{ padding: '0.5rem' }}>
                            <button
                              onClick={() => {
                                setActiveDrillGroup(null);
                                onNavigateToResourceDetail(line.resource_id);
                              }}
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
                              View
                            </button>
                          </td>
                        )}
                      </tr>
                    ))}
                  </tbody>
                </table>
              ) : (
                <div style={{ textAlign: 'center', padding: '2rem', color: 'var(--text-secondary)' }}>
                  No itemized charge lines found for this filter scope.
                </div>
              )}
            </div>

            <div
              style={{
                padding: '1rem 1.5rem',
                borderTop: '1px solid var(--border-color)',
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
              }}
            >
              <span style={{ fontSize: '0.8125rem', color: 'var(--text-secondary)' }}>
                Total Itemized Amount: <strong>${chargeLines?.total_amount.toFixed(2) || '0.00'} USD</strong>
              </span>
              <button
                onClick={() => setActiveDrillGroup(null)}
                style={{
                  padding: '0.4rem 0.8rem',
                  borderRadius: '6px',
                  border: '1px solid var(--border-color)',
                  backgroundColor: 'var(--bg-primary)',
                  color: 'var(--text-primary)',
                  fontSize: '0.8125rem',
                  cursor: 'pointer',
                }}
              >
                Close Drill-Down
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default CostExplorerPage;
