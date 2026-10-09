import React, { useMemo } from 'react';
import {
  Breadcrumb,
  CostValue,
  createCostExplanation,
  NullValue,
  FreshnessIndicator,
  EmptyState,
  ErrorState,
  SkeletonLoader,
} from '../design-system';
import { DemoModeBanner } from '../components/DemoModeBanner';
import { AlertCircle, Clock, CheckCircle2, TrendingDown } from 'lucide-react';
import { useApiData } from '../api';

export interface CommitmentItem {
  id: string;
  provider: 'AWS' | 'AZURE' | 'GCP' | 'OCI';
  type: 'SAVINGS_PLAN' | 'RESERVED_INSTANCE' | 'COMMITTED_USE_DISCOUNT';
  scope: string;
  termMonths: number;
  hourlyCommitment: number | null;
  monthlySavings: number | null;
  utilizationPct: number | null;
  coveragePct: number | null;
  expirationDate: string;
  daysToExpiry: number | null;
  status: 'ACTIVE' | 'EXPIRING_SOON' | 'UNDERUTILIZED' | 'EXPIRED';
}

export const CommitmentRenewalsPage: React.FC<{ isDemo?: boolean }> = ({ isDemo = false }) => {
  const { data: apiData, loading, error, errorMessage, refetch, isEmpty } = useApiData<any>(
    '/api/v1/commitments'
  );

  const commitments: CommitmentItem[] = useMemo(() => {
    if (!apiData) return [];
    const list = Array.isArray(apiData) ? apiData : apiData.items || [];
    return list.map((c: any) => ({
      id: c.id || c.commitment_id || 'COMM-01',
      provider: (c.provider || 'AWS') as CommitmentItem['provider'],
      type: (c.type || 'SAVINGS_PLAN') as CommitmentItem['type'],
      scope: c.scope || c.scope_name || 'Enterprise Core',
      termMonths: c.termMonths ?? c.term_months ?? 12,
      hourlyCommitment: c.hourlyCommitment ?? c.hourly_commitment ?? null,
      monthlySavings: c.monthlySavings ?? c.monthly_savings ?? null,
      utilizationPct: c.utilizationPct ?? c.utilization_pct ?? null,
      coveragePct: c.coveragePct ?? c.coverage_pct ?? null,
      expirationDate: c.expirationDate || c.expiration_date || '',
      daysToExpiry: c.daysToExpiry ?? c.days_to_expiry ?? null,
      status: (c.status || 'ACTIVE') as CommitmentItem['status'],
    }));
  }, [apiData]);

  const expiringCount = commitments.filter((c) => c.status === 'EXPIRING_SOON').length;
  const underutilizedCount = commitments.filter((c) => c.status === 'UNDERUTILIZED').length;
  const totalMonthlySavings = commitments.reduce((sum, c) => sum + (c.monthlySavings || 0), 0);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem', width: '100%' }}>
      <DemoModeBanner isDemo={isDemo} />

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Breadcrumb
          items={[
            { label: 'Home', href: '/' },
            { label: 'Commitment Portfolio', isCurrent: true },
          ]}
        />
        <FreshnessIndicator lastSyncedAt="2026-10-05T12:00:00Z" provider="Multi-Cloud" />
      </div>

      <header>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '0.25rem' }}>
          <h1 style={{ fontSize: '1.75rem', fontWeight: 700, margin: 0, color: 'var(--text-primary)' }}>
            Commitment Portfolio & Renewals Console
          </h1>
          <span
            style={{
              padding: '0.2rem 0.6rem',
              borderRadius: '9999px',
              backgroundColor: 'rgba(56, 189, 248, 0.15)',
              border: '1px solid rgba(56, 189, 248, 0.3)',
              color: '#38bdf8',
              fontSize: '0.75rem',
              fontWeight: 600,
            }}
          >
            FinOps Portfolio Engine
          </span>
        </div>
        <p style={{ color: 'var(--text-secondary)', margin: 0, fontSize: '0.9rem' }}>
          Portfolio discount coverage, utilization tracking, waste detection, and renewal pipeline alerts.
        </p>
      </header>

      {loading && <SkeletonLoader variant="table" rows={3} />}

      {error && !loading && (
        <ErrorState
          title="Failed to Load Commitments"
          message={errorMessage || 'Error fetching cloud commitments from API'}
          onRetry={refetch}
        />
      )}

      {!loading && !error && (
        <>
          {/* KPI Cards */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '1rem' }}>
            <div style={{ backgroundColor: 'var(--bg-secondary)', border: '1px solid var(--border-color)', borderRadius: '8px', padding: '1rem' }}>
              <span style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>Active Commitments</span>
              <div style={{ fontSize: '1.5rem', fontWeight: 700, color: 'var(--text-primary)', marginTop: '0.25rem' }}>
                {commitments.length > 0 ? commitments.length : <NullValue state="ZERO" />}
              </div>
              <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>Across AWS, Azure, GCP</span>
            </div>

            <div style={{ backgroundColor: 'var(--bg-secondary)', border: '1px solid #10b981', borderRadius: '8px', padding: '1rem' }}>
              <span style={{ fontSize: '0.8rem', color: '#6ee7b7' }}>Total Realised Discount</span>
              <div style={{ fontSize: '1.5rem', fontWeight: 700, color: '#34d399', marginTop: '0.25rem' }}>
                {commitments.length > 0 ? (
                  <CostValue
                    amount={totalMonthlySavings}
                    source="ACTUAL"
                    explanation={createCostExplanation('Commitment Realised Savings')}
                    showBadge={false}
                  />
                ) : (
                  <NullValue state="ZERO" />
                )}
              </div>
              <span style={{ fontSize: '0.75rem', color: '#a7f3d0' }}>Saved vs On-Demand rates</span>
            </div>

            <div style={{ backgroundColor: 'var(--bg-secondary)', border: '1px solid #f59e0b', borderRadius: '8px', padding: '1rem' }}>
              <span style={{ fontSize: '0.8rem', color: '#fbbf24' }}>Expiring &lt;60 Days</span>
              <div style={{ fontSize: '1.5rem', fontWeight: 700, color: '#fbbf24', marginTop: '0.25rem' }}>
                {commitments.length > 0 ? expiringCount : <NullValue state="ZERO" />}
              </div>
              <span style={{ fontSize: '0.75rem', color: '#fde68a' }}>Renewal decisions pending</span>
            </div>

            <div style={{ backgroundColor: 'var(--bg-secondary)', border: '1px solid #ef4444', borderRadius: '8px', padding: '1rem' }}>
              <span style={{ fontSize: '0.8rem', color: '#f87171' }}>Underutilized (&lt;80%)</span>
              <div style={{ fontSize: '1.5rem', fontWeight: 700, color: '#ef4444', marginTop: '0.25rem' }}>
                {commitments.length > 0 ? underutilizedCount : <NullValue state="ZERO" />}
              </div>
              <span style={{ fontSize: '0.75rem', color: '#fca5a5' }}>Commitment capacity waste</span>
            </div>
          </div>

          {/* Table Section */}
          <section
            aria-labelledby="commitments-table-heading"
            style={{
              backgroundColor: 'var(--bg-secondary)',
              border: '1px solid var(--border-color)',
              borderRadius: '8px',
              padding: '1.25rem',
            }}
          >
            <h2 id="commitments-table-heading" style={{ fontSize: '1.1rem', fontWeight: 600, marginBottom: '1rem' }}>
              Commitment Portfolio Inventory
            </h2>

            {commitments.length === 0 || isEmpty ? (
              <EmptyState type="NO_DATA" titleOverride="No Commitments Registered" descriptionOverride="No active savings plans, reserved instances, or committed use discounts registered." actionTextOverride="Register Commitment" onAction={() => alert('Register commitment workflow triggered')} />
            ) : (
              <div style={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '0.85rem' }}>
                  <thead>
                    <tr style={{ borderBottom: '1px solid var(--border-color)', color: 'var(--text-secondary)' }}>
                      <th style={{ padding: '0.6rem' }}>Commitment ID / Provider</th>
                      <th style={{ padding: '0.6rem' }}>Type & Term</th>
                      <th style={{ padding: '0.6rem' }}>Monthly Savings</th>
                      <th style={{ padding: '0.6rem' }}>Utilization</th>
                      <th style={{ padding: '0.6rem' }}>Coverage</th>
                      <th style={{ padding: '0.6rem' }}>Expiry Timeline</th>
                      <th style={{ padding: '0.6rem' }}>Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {commitments.map((c) => (
                      <tr key={c.id} style={{ borderBottom: '1px solid var(--border-color)' }}>
                        <td style={{ padding: '0.75rem 0.6rem' }}>
                          <strong>{c.id}</strong>
                          <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
                            {c.provider} ({c.scope})
                          </div>
                        </td>
                        <td style={{ padding: '0.75rem 0.6rem' }}>
                          <div><code>{c.type}</code></div>
                          <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>{c.termMonths} Months</div>
                        </td>
                        <td style={{ padding: '0.75rem 0.6rem' }}>
                          <CostValue
                            amount={c.monthlySavings}
                            source="ACTUAL"
                            explanation={createCostExplanation('Monthly Commitment Savings Delta')}
                          />
                        </td>
                        <td style={{ padding: '0.75rem 0.6rem' }}>
                          {c.utilizationPct !== null ? (
                            <span style={{ fontWeight: 600, color: c.utilizationPct < 80 ? '#f87171' : '#34d399' }}>
                              {c.utilizationPct.toFixed(1)}%
                            </span>
                          ) : (
                            <NullValue state="NOT_SUPPORTED" />
                          )}
                        </td>
                        <td style={{ padding: '0.75rem 0.6rem' }}>
                          {c.coveragePct !== null ? (
                            <span>{c.coveragePct.toFixed(1)}%</span>
                          ) : (
                            <NullValue state="NOT_SUPPORTED" />
                          )}
                        </td>
                        <td style={{ padding: '0.75rem 0.6rem' }}>
                          {c.daysToExpiry !== null ? (
                            <span style={{ display: 'inline-flex', alignItems: 'center', gap: '0.25rem', color: c.daysToExpiry <= 60 ? '#fbbf24' : 'var(--text-secondary)' }}>
                              <Clock size={12} aria-hidden="true" /> {c.daysToExpiry} Days
                            </span>
                          ) : (
                            <NullValue state="NOT_APPLICABLE" />
                          )}
                        </td>
                        <td style={{ padding: '0.75rem 0.6rem' }}>
                          {c.status === 'EXPIRING_SOON' ? (
                            <span style={{ display: 'inline-flex', alignItems: 'center', gap: '0.2rem', padding: '0.15rem 0.5rem', borderRadius: '4px', backgroundColor: '#78350f', color: '#fde68a', fontSize: '0.75rem', fontWeight: 600 }}>
                              <AlertCircle size={12} aria-hidden="true" /> EXPIRING SOON
                            </span>
                          ) : c.status === 'UNDERUTILIZED' ? (
                            <span style={{ display: 'inline-flex', alignItems: 'center', gap: '0.2rem', padding: '0.15rem 0.5rem', borderRadius: '4px', backgroundColor: '#7f1d1d', color: '#fca5a5', fontSize: '0.75rem', fontWeight: 600 }}>
                              <TrendingDown size={12} aria-hidden="true" /> UNDERUTILIZED
                            </span>
                          ) : (
                            <span style={{ display: 'inline-flex', alignItems: 'center', gap: '0.2rem', padding: '0.15rem 0.5rem', borderRadius: '4px', backgroundColor: '#064e3b', color: '#6ee7b7', fontSize: '0.75rem', fontWeight: 600 }}>
                              <CheckCircle2 size={12} aria-hidden="true" /> ACTIVE
                            </span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </>
      )}
    </div>
  );
};

export default CommitmentRenewalsPage;
