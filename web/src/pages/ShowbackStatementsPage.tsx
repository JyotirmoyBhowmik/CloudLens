import React, { useState, useEffect } from 'react';
import {
  Breadcrumb,
  CostValue,
  createCostExplanation,
  NullValue,
  FreshnessIndicator,
} from '../design-system';
import { DemoModeBanner } from '../components/DemoModeBanner';
import { AlertCircle, CheckCircle2, RefreshCw } from 'lucide-react';

interface ShowbackStatementItem {
  id: string;
  period: string;
  scopeCode: string;
  scopeName: string;
  directCost: number | null;
  sharedCostAllocated: number | null;
  unallocatedCost: number | null;
  totalBilledCost: number | null;
  status: 'DRAFT' | 'CIRCULATED' | 'DISPUTED' | 'FINALISED' | 'REVISED_V2';
  version: number;
  disputeCount: number;
  disputeDetails?: {
    lineId: string;
    description: string;
    amount: number;
    reason: string;
  };
}

const DEMO_STATEMENTS: ShowbackStatementItem[] = [
  {
    id: 'STMT-2026-09-RETAIL',
    period: '2026-09',
    scopeCode: 'BU-RETAIL',
    scopeName: 'Retail & E-Commerce Business Unit',
    directCost: 142850.00,
    sharedCostAllocated: 24500.00,
    unallocatedCost: 6500.00,
    totalBilledCost: 173850.00,
    status: 'DISPUTED',
    version: 1,
    disputeCount: 1,
    disputeDetails: {
      lineId: 'LINE-S3-CROSS-REGION-RETAIL',
      description: 'Shared cross-region egress from central analytics bucket',
      amount: 14200.00,
      reason: 'Egress traffic was driven by Data Engineering batch extraction, not Retail app queries.',
    },
  },
  {
    id: 'STMT-2026-09-FINTECH',
    period: '2026-09',
    scopeCode: 'BU-FINTECH',
    scopeName: 'Digital Banking & Payments BU',
    directCost: 89400.00,
    sharedCostAllocated: 18200.00,
    unallocatedCost: 0.00,
    totalBilledCost: 107600.00,
    status: 'FINALISED',
    version: 1,
    disputeCount: 0,
  },
  {
    id: 'STMT-2026-08-RETAIL-V2',
    period: '2026-08',
    scopeCode: 'BU-RETAIL',
    scopeName: 'Retail & E-Commerce Business Unit (Restatement v2)',
    directCost: 138200.00,
    sharedCostAllocated: 21000.00,
    unallocatedCost: 0.00,
    totalBilledCost: 159200.00,
    status: 'REVISED_V2',
    version: 2,
    disputeCount: 0,
  },
];

export const ShowbackStatementsPage: React.FC<{ isDemo?: boolean }> = ({ isDemo = true }) => {
  const [statements, setStatements] = useState<ShowbackStatementItem[]>(DEMO_STATEMENTS);
  const [selectedPeriod, setSelectedPeriod] = useState<string>('ALL');

  useEffect(() => {
    if (!isDemo) {
      setStatements([]);
    } else {
      setStatements(DEMO_STATEMENTS);
    }
  }, [isDemo]);

  const filtered = statements.filter((s) => {
    if (selectedPeriod !== 'ALL' && s.period !== selectedPeriod) return false;
    return true;
  });

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem', width: '100%' }}>
      <DemoModeBanner isDemo={isDemo} />

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Breadcrumb
          items={[
            { label: 'Home', href: '/' },
            { label: 'Showback Statements', isCurrent: true },
          ]}
        />
        <FreshnessIndicator lastSyncedAt="2026-10-05T12:00:00Z" provider="Multi-Cloud" />
      </div>

      <header>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '0.25rem' }}>
          <h1 style={{ fontSize: '1.75rem', fontWeight: 700, margin: 0, color: 'var(--text-primary)' }}>
            S-25: Showback & Cost Allocation Statements
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
            Addendum B / Prompt 52 / API-053
          </span>
        </div>
        <p style={{ color: 'var(--text-secondary)', margin: 0, fontSize: '0.9rem' }}>
          Period-close cost circulation, line disputes, shared cost apportionment transparency, and restatement adjustments.
        </p>
      </header>

      {/* High-Level Overview Strip */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '1rem' }}>
        <div style={{ backgroundColor: 'var(--bg-secondary)', border: '1px solid var(--border-color)', borderRadius: '8px', padding: '1rem' }}>
          <span style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>Generated Statements</span>
          <div style={{ fontSize: '1.5rem', fontWeight: 700, color: 'var(--text-primary)', marginTop: '0.25rem' }}>
            {statements.length > 0 ? statements.length : <NullValue state="NO_DATA" />}
          </div>
          <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>Circulated to BU owners</span>
        </div>

        <div style={{ backgroundColor: 'var(--bg-secondary)', border: '1px solid #ef4444', borderRadius: '8px', padding: '1rem' }}>
          <span style={{ fontSize: '0.8rem', color: '#f87171' }}>Active Line Disputes</span>
          <div style={{ fontSize: '1.5rem', fontWeight: 700, color: '#ef4444', marginTop: '0.25rem' }}>
            {statements.length > 0 ? statements.reduce((acc, s) => acc + s.disputeCount, 0) : <NullValue state="ZERO" />}
          </div>
          <span style={{ fontSize: '0.75rem', color: '#fca5a5' }}>Under SLA investigation</span>
        </div>

        <div style={{ backgroundColor: 'var(--bg-secondary)', border: '1px solid #10b981', borderRadius: '8px', padding: '1rem' }}>
          <span style={{ fontSize: '0.8rem', color: '#6ee7b7' }}>Finalised Statements</span>
          <div style={{ fontSize: '1.5rem', fontWeight: 700, color: '#34d399', marginTop: '0.25rem' }}>
            {statements.length > 0 ? statements.filter((s) => s.status === 'FINALISED' || s.status === 'REVISED_V2').length : <NullValue state="ZERO" />}
          </div>
          <span style={{ fontSize: '0.75rem', color: '#a7f3d0' }}>Audited period close</span>
        </div>
      </div>

      {/* Statement Table Section */}
      <section
        aria-labelledby="statements-heading"
        style={{
          backgroundColor: 'var(--bg-secondary)',
          border: '1px solid var(--border-color)',
          borderRadius: '8px',
          padding: '1.25rem',
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
          <h2 id="statements-heading" style={{ fontSize: '1.1rem', fontWeight: 600, margin: 0 }}>
            Period Statement Ledger
          </h2>

          <select
            value={selectedPeriod}
            onChange={(e) => setSelectedPeriod(e.target.value)}
            aria-label="Filter by billing period"
            style={{
              padding: '0.4rem 0.6rem',
              fontSize: '0.8rem',
              borderRadius: '6px',
              border: '1px solid var(--border-color)',
              backgroundColor: 'var(--bg-primary)',
              color: 'var(--text-primary)',
            }}
          >
            <option value="ALL">All Periods</option>
            <option value="2026-09">2026-09</option>
            <option value="2026-08">2026-08</option>
          </select>
        </div>

        {filtered.length === 0 ? (
          <div
            style={{
              padding: '2.5rem',
              borderRadius: '6px',
              border: '1px dashed var(--border-color)',
              textAlign: 'center',
            }}
          >
            <p style={{ color: 'var(--text-secondary)', marginBottom: '0.5rem' }}>
              No statements available for this billing period.
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
                  <th style={{ padding: '0.6rem' }}>Statement ID / Period</th>
                  <th style={{ padding: '0.6rem' }}>Business Unit</th>
                  <th style={{ padding: '0.6rem' }}>Direct Cost</th>
                  <th style={{ padding: '0.6rem' }}>Shared Apportionment</th>
                  <th style={{ padding: '0.6rem' }}>Unallocated</th>
                  <th style={{ padding: '0.6rem' }}>Total Cost</th>
                  <th style={{ padding: '0.6rem' }}>Status</th>
                  <th style={{ padding: '0.6rem' }}>Disputes</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((stmt) => (
                  <tr key={stmt.id} style={{ borderBottom: '1px solid var(--border-color)' }}>
                    <td style={{ padding: '0.75rem 0.6rem' }}>
                      <strong>{stmt.id}</strong>
                      <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
                        Period: {stmt.period} (v{stmt.version})
                      </div>
                    </td>
                    <td style={{ padding: '0.75rem 0.6rem' }}>
                      <div>{stmt.scopeName}</div>
                      <code style={{ fontSize: '0.75rem', color: '#38bdf8' }}>{stmt.scopeCode}</code>
                    </td>
                    <td style={{ padding: '0.75rem 0.6rem' }}>
                      <CostValue
                        amount={stmt.directCost}
                        source="ACTUAL"
                        explanation={createCostExplanation('Direct Statement Cost')}
                      />
                    </td>
                    <td style={{ padding: '0.75rem 0.6rem' }}>
                      <CostValue
                        amount={stmt.sharedCostAllocated}
                        source="ACTUAL"
                        explanation={createCostExplanation('Shared Service Apportionment')}
                      />
                    </td>
                    <td style={{ padding: '0.75rem 0.6rem' }}>
                      {stmt.unallocatedCost !== null && stmt.unallocatedCost > 0 ? (
                        <CostValue
                          amount={stmt.unallocatedCost}
                          source="ACTUAL"
                          explanation={createCostExplanation('Unallocated Infrastructure')}
                        />
                      ) : (
                        <NullValue state="ZERO" customZeroValue="$0.00" />
                      )}
                    </td>
                    <td style={{ padding: '0.75rem 0.6rem' }}>
                      <CostValue
                        amount={stmt.totalBilledCost}
                        source="ACTUAL"
                        explanation={createCostExplanation('Total Statement Spend')}
                      />
                    </td>
                    <td style={{ padding: '0.75rem 0.6rem' }}>
                      {stmt.status === 'DISPUTED' ? (
                        <span style={{ display: 'inline-flex', alignItems: 'center', gap: '0.2rem', padding: '0.15rem 0.5rem', borderRadius: '4px', backgroundColor: '#7f1d1d', color: '#fca5a5', fontSize: '0.75rem', fontWeight: 600 }}>
                          <AlertCircle size={12} aria-hidden="true" /> DISPUTED
                        </span>
                      ) : stmt.status === 'REVISED_V2' ? (
                        <span style={{ display: 'inline-flex', alignItems: 'center', gap: '0.2rem', padding: '0.15rem 0.5rem', borderRadius: '4px', backgroundColor: '#0369a1', color: '#e0f2fe', fontSize: '0.75rem', fontWeight: 600 }}>
                          <RefreshCw size={12} aria-hidden="true" /> REVISED (V2)
                        </span>
                      ) : (
                        <span style={{ display: 'inline-flex', alignItems: 'center', gap: '0.2rem', padding: '0.15rem 0.5rem', borderRadius: '4px', backgroundColor: '#064e3b', color: '#6ee7b7', fontSize: '0.75rem', fontWeight: 600 }}>
                          <CheckCircle2 size={12} aria-hidden="true" /> {stmt.status}
                        </span>
                      )}
                    </td>
                    <td style={{ padding: '0.75rem 0.6rem' }}>
                      {stmt.disputeDetails ? (
                        <div style={{ fontSize: '0.75rem' }}>
                          <strong style={{ color: '#f87171' }}>${stmt.disputeDetails.amount.toFixed(2)}</strong>
                          <div style={{ color: 'var(--text-secondary)', maxWidth: '220px' }}>
                            {stmt.disputeDetails.reason}
                          </div>
                        </div>
                      ) : (
                        <NullValue state="ZERO" customZeroValue="0" />
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
export default ShowbackStatementsPage;
