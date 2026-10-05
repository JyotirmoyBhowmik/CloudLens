import React, { useState, useEffect } from 'react';
import {
  Breadcrumb,
  CostValue,
  createCostExplanation,
  NullValue,
  FreshnessIndicator,
} from '../design-system';
import { DemoModeBanner } from '../components/DemoModeBanner';

interface PlanningWorkspaceItem {
  id: string;
  scopeName: string;
  scopeType: 'BUSINESS_UNIT' | 'COST_CENTRE' | 'APPLICATION';
  currentRunRate: number | null;
  baseForecast: number | null;
  proposedBudget: number | null;
  plannedAdjustment: number | null;
  variancePct: number | null;
  status: 'DRAFT' | 'LOCKED' | 'APPROVED';
}

const DEMO_PLANNING: PlanningWorkspaceItem[] = [
  {
    id: 'PLAN-FY27-CORE-APPS',
    scopeName: 'Core Enterprise Applications',
    scopeType: 'BUSINESS_UNIT',
    currentRunRate: 450000.00,
    baseForecast: 480000.00,
    proposedBudget: 500000.00,
    plannedAdjustment: 20000.00,
    variancePct: 4.1,
    status: 'APPROVED',
  },
  {
    id: 'PLAN-FY27-DATA-LAKE',
    scopeName: 'BigData & Analytics Platform',
    scopeType: 'COST_CENTRE',
    currentRunRate: 280000.00,
    baseForecast: 340000.00,
    proposedBudget: 320000.00,
    plannedAdjustment: -20000.00,
    variancePct: -5.9,
    status: 'DRAFT',
  },
  {
    id: 'PLAN-FY27-CHECKOUT-SQUAD',
    scopeName: 'Checkout Microservices Fleet',
    scopeType: 'APPLICATION',
    currentRunRate: 95000.00,
    baseForecast: 110000.00,
    proposedBudget: 115000.00,
    plannedAdjustment: 5000.00,
    variancePct: 4.5,
    status: 'DRAFT',
  },
];

export const BudgetPlanningPage: React.FC<{ isDemo?: boolean }> = ({ isDemo = true }) => {
  const [plans, setPlans] = useState<PlanningWorkspaceItem[]>(DEMO_PLANNING);

  useEffect(() => {
    if (!isDemo) {
      setPlans([]);
    } else {
      setPlans(DEMO_PLANNING);
    }
  }, [isDemo]);

  const totalProposed = plans.reduce((acc, p) => acc + (p.proposedBudget || 0), 0);
  const totalForecast = plans.reduce((acc, p) => acc + (p.baseForecast || 0), 0);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem', width: '100%' }}>
      <DemoModeBanner isDemo={isDemo} />

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Breadcrumb
          items={[
            { label: 'Home', href: '/' },
            { label: 'Budget Planning', isCurrent: true },
          ]}
        />
        <FreshnessIndicator lastSyncedAt="2026-10-05T12:00:00Z" provider="Multi-Cloud" />
      </div>

      <header>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '0.25rem' }}>
          <h1 style={{ fontSize: '1.75rem', fontWeight: 700, margin: 0, color: 'var(--text-primary)' }}>
            S-26: Budget Planning & Forecasting Workspace
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
            Addendum B / Prompt 48 / Prompt 56
          </span>
        </div>
        <p style={{ color: 'var(--text-secondary)', margin: 0, fontSize: '0.9rem' }}>
          Scenario modeling, run-rate extrapolation, multi-year capacity planning, and hierarchy overlap validation.
        </p>
      </header>

      {/* KPI Cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '1rem' }}>
        <div style={{ backgroundColor: 'var(--bg-secondary)', border: '1px solid var(--border-color)', borderRadius: '8px', padding: '1rem' }}>
          <span style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>Planned Workspaces</span>
          <div style={{ fontSize: '1.5rem', fontWeight: 700, color: 'var(--text-primary)', marginTop: '0.25rem' }}>
            {plans.length > 0 ? plans.length : <NullValue state="NO_DATA" />}
          </div>
        </div>

        <div style={{ backgroundColor: 'var(--bg-secondary)', border: '1px solid #38bdf8', borderRadius: '8px', padding: '1rem' }}>
          <span style={{ fontSize: '0.8rem', color: '#7dd3fc' }}>Total Proposed Envelope</span>
          <div style={{ fontSize: '1.5rem', fontWeight: 700, color: '#38bdf8', marginTop: '0.25rem' }}>
            {plans.length > 0 ? (
              <CostValue
                amount={totalProposed}
                source="ESTIMATED"
                explanation={createCostExplanation('Proposed Annual Budget Envelope')}
                showBadge={false}
              />
            ) : (
              <NullValue state="ZERO" />
            )}
          </div>
        </div>

        <div style={{ backgroundColor: 'var(--bg-secondary)', border: '1px solid #10b981', borderRadius: '8px', padding: '1rem' }}>
          <span style={{ fontSize: '0.8rem', color: '#6ee7b7' }}>Statistical Baseline Forecast</span>
          <div style={{ fontSize: '1.5rem', fontWeight: 700, color: '#34d399', marginTop: '0.25rem' }}>
            {plans.length > 0 ? (
              <CostValue
                amount={totalForecast}
                source="FORECAST"
                explanation={createCostExplanation('Algorithmic Multi-Period Forecast')}
                showBadge={false}
              />
            ) : (
              <NullValue state="ZERO" />
            )}
          </div>
        </div>
      </div>

      {/* Planning Table */}
      <section
        aria-labelledby="planning-table-heading"
        style={{
          backgroundColor: 'var(--bg-secondary)',
          border: '1px solid var(--border-color)',
          borderRadius: '8px',
          padding: '1.25rem',
        }}
      >
        <h2 id="planning-table-heading" style={{ fontSize: '1.1rem', fontWeight: 600, marginBottom: '1rem' }}>
          Active Budget Planning Envelopes
        </h2>

        {plans.length === 0 ? (
          <div
            style={{
              padding: '2.5rem',
              borderRadius: '6px',
              border: '1px dashed var(--border-color)',
              textAlign: 'center',
            }}
          >
            <p style={{ color: 'var(--text-secondary)', marginBottom: '0.5rem' }}>
              No planning envelopes initialized for this fiscal period.
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
                  <th style={{ padding: '0.6rem' }}>Scope & Plan ID</th>
                  <th style={{ padding: '0.6rem' }}>Scope Type</th>
                  <th style={{ padding: '0.6rem' }}>Current Run-Rate</th>
                  <th style={{ padding: '0.6rem' }}>Statistical Forecast</th>
                  <th style={{ padding: '0.6rem' }}>Proposed Budget</th>
                  <th style={{ padding: '0.6rem' }}>Variance Delta</th>
                  <th style={{ padding: '0.6rem' }}>Status</th>
                </tr>
              </thead>
              <tbody>
                {plans.map((p) => (
                  <tr key={p.id} style={{ borderBottom: '1px solid var(--border-color)' }}>
                    <td style={{ padding: '0.75rem 0.6rem' }}>
                      <strong>{p.scopeName}</strong>
                      <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>{p.id}</div>
                    </td>
                    <td style={{ padding: '0.75rem 0.6rem' }}>
                      <code>{p.scopeType}</code>
                    </td>
                    <td style={{ padding: '0.75rem 0.6rem' }}>
                      <CostValue
                        amount={p.currentRunRate}
                        source="ACTUAL"
                        explanation={createCostExplanation('Current Annualized Run Rate')}
                      />
                    </td>
                    <td style={{ padding: '0.75rem 0.6rem' }}>
                      <CostValue
                        amount={p.baseForecast}
                        source="FORECAST"
                        explanation={createCostExplanation('ML Forecast Baseline')}
                      />
                    </td>
                    <td style={{ padding: '0.75rem 0.6rem' }}>
                      <CostValue
                        amount={p.proposedBudget}
                        source="ESTIMATED"
                        explanation={createCostExplanation('Proposed Annual Allocation')}
                      />
                    </td>
                    <td style={{ padding: '0.75rem 0.6rem' }}>
                      {p.variancePct !== null ? (
                        <span style={{ fontWeight: 600, color: p.variancePct > 0 ? '#34d399' : '#f87171' }}>
                          {p.variancePct > 0 ? `+${p.variancePct}%` : `${p.variancePct}%`}
                        </span>
                      ) : (
                        <NullValue state="NOT_APPLICABLE" />
                      )}
                    </td>
                    <td style={{ padding: '0.75rem 0.6rem' }}>
                      <span
                        style={{
                          padding: '0.15rem 0.5rem',
                          borderRadius: '4px',
                          fontSize: '0.75rem',
                          fontWeight: 600,
                          backgroundColor: p.status === 'APPROVED' ? '#064e3b' : '#1e293b',
                          color: p.status === 'APPROVED' ? '#6ee7b7' : '#94a3b8',
                        }}
                      >
                        {p.status}
                      </span>
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
export default BudgetPlanningPage;
