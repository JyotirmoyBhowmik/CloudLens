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
import { useApiData } from '../api';

export interface PlanningWorkspaceItem {
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

export const BudgetPlanningPage: React.FC<{ isDemo?: boolean }> = ({ isDemo = false }) => {
  const { data: apiData, loading, error, errorMessage, refetch, isEmpty } = useApiData<any>(
    '/api/v1/budgets/plans'
  );

  const plans: PlanningWorkspaceItem[] = useMemo(() => {
    if (!apiData) return [];
    const rawList = Array.isArray(apiData) ? apiData : apiData.items || [];
    return rawList.map((item: any) => ({
      id: item.id || item.scope_id || 'PLAN-DEFAULT',
      scopeName: item.scopeName || item.scope_name || item.name || item.scope_id || 'Enterprise Scope',
      scopeType: (item.scopeType || item.scope_type || 'BUSINESS_UNIT') as PlanningWorkspaceItem['scopeType'],
      currentRunRate: item.currentRunRate ?? item.current_spend ?? null,
      baseForecast: item.baseForecast ?? item.forecast_spend ?? null,
      proposedBudget: item.proposedBudget ?? item.amount ?? null,
      plannedAdjustment: item.plannedAdjustment ?? null,
      variancePct: item.variancePct ?? null,
      status: (item.status || 'DRAFT') as PlanningWorkspaceItem['status'],
    }));
  }, [apiData]);

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

      {loading && <SkeletonLoader variant="table" rows={3} />}

      {error && !loading && (
        <ErrorState
          title="Failed to Load Budget Plans"
          message={errorMessage || 'Error fetching planning workspaces from API'}
          onRetry={refetch}
        />
      )}

      {!loading && !error && (
        <>
          {/* KPI Cards */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '1rem' }}>
            <div style={{ backgroundColor: 'var(--bg-secondary)', border: '1px solid var(--border-color)', borderRadius: '8px', padding: '1rem' }}>
              <span style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>Planned Workspaces</span>
              <div style={{ fontSize: '1.5rem', fontWeight: 700, color: 'var(--text-primary)', marginTop: '0.25rem' }}>
                {plans.length > 0 ? plans.length : <NullValue state="ZERO" />}
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

            {plans.length === 0 || isEmpty ? (
              <EmptyState type="NO_DATA" titleOverride="No Planning Envelopes Found" descriptionOverride="No budget planning envelopes have been initialized for this tenant." actionTextOverride="Create Plan Envelope" onAction={() => alert('New budget envelope workflow triggered')} />
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
        </>
      )}
    </div>
  );
};

export default BudgetPlanningPage;
