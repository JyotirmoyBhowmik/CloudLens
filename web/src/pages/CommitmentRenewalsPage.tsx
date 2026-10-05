import React, { useState, useEffect } from 'react';
import {
  Breadcrumb,
  CostValue,
  createCostExplanation,
  NullValue,
  FreshnessIndicator,
} from '../design-system';
import { DemoModeBanner } from '../components/DemoModeBanner';
import { AlertCircle, Clock, CheckCircle2, TrendingDown } from 'lucide-react';

interface CommitmentItem {
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

const DEMO_COMMITMENTS: CommitmentItem[] = [
  {
    id: 'SP-AWS-COMPUTE-3YR',
    provider: 'AWS',
    type: 'SAVINGS_PLAN',
    scope: 'Enterprise Core (Global)',
    termMonths: 36,
    hourlyCommitment: 45.00,
    monthlySavings: 14200.00,
    utilizationPct: 98.4,
    coveragePct: 76.2,
    expirationDate: '2026-11-15T00:00:00Z',
    daysToExpiry: 41,
    status: 'EXPIRING_SOON',
  },
  {
    id: 'RI-AZURE-E4DS-1YR',
    provider: 'AZURE',
    type: 'RESERVED_INSTANCE',
    scope: 'Sub-Prod-EastUS',
    termMonths: 12,
    hourlyCommitment: 12.80,
    monthlySavings: 3840.00,
    utilizationPct: 62.5,
    coveragePct: 44.0,
    expirationDate: '2027-04-01T00:00:00Z',
    daysToExpiry: 178,
    status: 'UNDERUTILIZED',
  },
  {
    id: 'CUD-GCP-N2-1YR',
    provider: 'GCP',
    type: 'COMMITTED_USE_DISCOUNT',
    scope: 'prj-analytics-platform',
    termMonths: 12,
    hourlyCommitment: 24.50,
    monthlySavings: 7100.00,
    utilizationPct: 99.1,
    coveragePct: 82.5,
    expirationDate: '2027-08-30T00:00:00Z',
    daysToExpiry: 329,
    status: 'ACTIVE',
  },
];

export const CommitmentRenewalsPage: React.FC<{ isDemo?: boolean }> = ({ isDemo = true }) => {
  const [commitments, setCommitments] = useState<CommitmentItem[]>(DEMO_COMMITMENTS);

  useEffect(() => {
    if (!isDemo) {
      setCommitments([]);
    } else {
      setCommitments(DEMO_COMMITMENTS);
    }
  }, [isDemo]);

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
            S-27: Commitment Portfolio & Renewals Console
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
            Addendum B / Prompt 31B / Track E
          </span>
        </div>
        <p style={{ color: 'var(--text-secondary)', margin: 0, fontSize: '0.9rem' }}>
          Portfolio discount coverage, utilization tracking, waste detection, and renewal pipeline alerts.
        </p>
      </header>

      {/* KPI Cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '1rem' }}>
        <div style={{ backgroundColor: 'var(--bg-secondary)', border: '1px solid var(--border-color)', borderRadius: '8px', padding: '1rem' }}>
          <span style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>Active Commitments</span>
          <div style={{ fontSize: '1.5rem', fontWeight: 700, color: 'var(--text-primary)', marginTop: '0.25rem' }}>
            {commitments.length > 0 ? commitments.length : <NullValue state="NO_DATA" />}
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

        {commitments.length === 0 ? (
          <div
            style={{
              padding: '2.5rem',
              borderRadius: '6px',
              border: '1px dashed var(--border-color)',
              textAlign: 'center',
            }}
          >
            <p style={{ color: 'var(--text-secondary)', marginBottom: '0.5rem' }}>
              No active cloud commitments registered.
            </p>
            <div style={{ display: 'inline-flex', alignItems: 'center', gap: '0.5rem' }}>
              <span style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>Status:</span>
              <NullValue state="NO_DATA" />
            </div>
          </div>
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
    </div>
  );
};
export default CommitmentRenewalsPage;
