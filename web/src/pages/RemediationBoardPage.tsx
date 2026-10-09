import React, { useState, useEffect } from 'react';
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
import { useApiData } from '../api';
import { DemoModeBanner } from '../components/DemoModeBanner';
import { CheckCircle2, RotateCcw } from 'lucide-react';

interface RemediationTaskItem {
  id: string;
  title: string;
  category: 'IDLE_COMPUTE' | 'UNATTACHED_STORAGE' | 'OVERSIZED_DATABASE' | 'OLD_SNAPSHOTS';
  assignee: string;
  resourceId: string;
  provider: string;
  projectedSavings: number | null;
  realisedSavings: number | null;
  status: 'OPEN' | 'IN_PROGRESS' | 'AWAITING_VERIFICATION' | 'RESOLVED' | 'FALSE_RESOLVED';
  verificationCondition: string;
}

export const RemediationBoardPage: React.FC<{ isDemo?: boolean }> = ({ isDemo = true }) => {
  const { data: apiTasks, loading, error, errorMessage, refetch } = useApiData<any>('/api/v1/remediation/tasks');
  const [tasks, setTasks] = useState<RemediationTaskItem[]>([]);
  const [categoryFilter, setCategoryFilter] = useState<string>('ALL');

  useEffect(() => {
    if (apiTasks) {
      const list = Array.isArray(apiTasks) ? apiTasks : (apiTasks.items || []);
      setTasks(list.map((t: any) => ({
        id: t.id || t.task_id || 'REM-01',
        title: t.title || 'Remediation Task',
        category: (t.category || 'IDLE_COMPUTE') as RemediationTaskItem['category'],
        assignee: t.assignee || 'Unassigned',
        resourceId: t.resource_id || t.resourceId || 'res-01',
        provider: t.provider || 'AWS',
        projectedSavings: t.projected_savings ?? t.projectedSavings ?? 0,
        realisedSavings: t.realised_savings ?? t.realisedSavings ?? null,
        status: (t.status || 'OPEN') as RemediationTaskItem['status'],
        verificationCondition: t.verification_condition || t.verificationCondition || '',
      })));
    }
  }, [apiTasks]);

  const filtered = tasks.filter((t) => {
    if (categoryFilter !== 'ALL' && t.category !== categoryFilter) return false;
    return true;
  });

  const totalProjected = tasks.reduce((sum, t) => sum + (t.projectedSavings || 0), 0);
  const totalRealised = tasks.reduce((sum, t) => sum + (t.realisedSavings || 0), 0);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem', width: '100%' }}>
      <DemoModeBanner isDemo={isDemo} />

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Breadcrumb
          items={[
            { label: 'Home', href: '/' },
            { label: 'Remediation Task Board', isCurrent: true },
          ]}
        />
        <FreshnessIndicator lastSyncedAt="2026-10-05T12:00:00Z" provider="Multi-Cloud" />
      </div>

      <header>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '0.25rem' }}>
          <h1 style={{ fontSize: '1.75rem', fontWeight: 700, margin: 0, color: 'var(--text-primary)' }}>
            S-24: Remediation & Accountability Task Board
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
            Addendum B / Prompt 51 / BBP Sec 34
          </span>
        </div>
        <p style={{ color: 'var(--text-secondary)', margin: 0, fontSize: '0.9rem' }}>
          Accountability without blame: Automated re-testing verification, false-resolution prevention, and realised savings ledger.
        </p>
      </header>

      {/* Realised Savings Highlight Cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '1rem' }}>
        <div style={{ backgroundColor: 'var(--bg-secondary)', border: '1px solid var(--border-color)', borderRadius: '8px', padding: '1rem' }}>
          <span style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>Active Tasks</span>
          <div style={{ fontSize: '1.5rem', fontWeight: 700, color: 'var(--text-primary)', marginTop: '0.25rem' }}>
            {tasks.length > 0 ? tasks.length : <NullValue state="NO_DATA" />}
          </div>
          <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>Across 4 categories</span>
        </div>

        <div style={{ backgroundColor: 'var(--bg-secondary)', border: '1px solid #38bdf8', borderRadius: '8px', padding: '1rem' }}>
          <span style={{ fontSize: '0.8rem', color: '#7dd3fc' }}>Projected Monthly Savings</span>
          <div style={{ fontSize: '1.5rem', fontWeight: 700, color: '#38bdf8', marginTop: '0.25rem' }}>
            {tasks.length > 0 ? (
              <CostValue
                amount={totalProjected}
                source="ESTIMATED"
                explanation={createCostExplanation('Total Projected Remediation Savings')}
                showBadge={false}
              />
            ) : (
              <NullValue state="ZERO" />
            )}
          </div>
          <span style={{ fontSize: '0.75rem', color: '#bae6fd' }}>Identified waste pipeline</span>
        </div>

        <div style={{ backgroundColor: 'var(--bg-secondary)', border: '1px solid #10b981', borderRadius: '8px', padding: '1rem' }}>
          <span style={{ fontSize: '0.8rem', color: '#6ee7b7' }}>Realised Monthly Savings</span>
          <div style={{ fontSize: '1.5rem', fontWeight: 700, color: '#34d399', marginTop: '0.25rem' }}>
            {tasks.length > 0 ? (
              <CostValue
                amount={totalRealised}
                source="ACTUAL"
                explanation={createCostExplanation('Audited Realised Savings Ledger')}
                showBadge={false}
              />
            ) : (
              <NullValue state="ZERO" />
            )}
          </div>
          <span style={{ fontSize: '0.75rem', color: '#a7f3d0' }}>Verified by telemetry re-test</span>
        </div>

        <div style={{ backgroundColor: 'var(--bg-secondary)', border: '1px solid #ef4444', borderRadius: '8px', padding: '1rem' }}>
          <span style={{ fontSize: '0.8rem', color: '#f87171' }}>Auto-Reopened (False Resolved)</span>
          <div style={{ fontSize: '1.5rem', fontWeight: 700, color: '#f87171', marginTop: '0.25rem' }}>
            {tasks.length > 0 ? tasks.filter((t) => t.status === 'FALSE_RESOLVED').length : <NullValue state="ZERO" />}
          </div>
          <span style={{ fontSize: '0.75rem', color: '#fca5a5' }}>Failed automated re-test</span>
        </div>
      </div>

      {/* Task List / Kanban View */}
      <section
        aria-labelledby="remediation-board-heading"
        style={{
          backgroundColor: 'var(--bg-secondary)',
          border: '1px solid var(--border-color)',
          borderRadius: '8px',
          padding: '1.25rem',
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
          <h2 id="remediation-board-heading" style={{ fontSize: '1.1rem', fontWeight: 600, margin: 0 }}>
            Accountability Tasks & Automated Verification
          </h2>

          <select
            value={categoryFilter}
            onChange={(e) => setCategoryFilter(e.target.value)}
            aria-label="Filter by waste category"
            style={{
              padding: '0.4rem 0.6rem',
              fontSize: '0.8rem',
              borderRadius: '6px',
              border: '1px solid var(--border-color)',
              backgroundColor: 'var(--bg-primary)',
              color: 'var(--text-primary)',
            }}
          >
            <option value="ALL">All Categories</option>
            <option value="IDLE_COMPUTE">Idle Compute</option>
            <option value="UNATTACHED_STORAGE">Unattached Storage</option>
            <option value="OVERSIZED_DATABASE">Oversized Database</option>
            <option value="OLD_SNAPSHOTS">Old Snapshots</option>
          </select>
        </div>

        {loading ? (
          <SkeletonLoader variant="table" rows={3} />
        ) : error ? (
          <ErrorState
            title="Failed to Load Remediation Tasks"
            message={errorMessage || 'Error contacting remediation tasks API'}
            onRetry={refetch}
          />
        ) : filtered.length === 0 ? (
          <EmptyState type="NO_DATA" titleOverride="No Remediation Tasks" descriptionOverride="No active remediation tasks or unaddressed optimization recommendations found." actionTextOverride="Refresh Tasks" onAction={refetch} />
        ) : (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: '1rem' }}>
            {filtered.map((task) => (
              <article
                key={task.id}
                style={{
                  backgroundColor: 'var(--bg-primary)',
                  border: `1px solid ${task.status === 'FALSE_RESOLVED' ? '#ef4444' : task.status === 'RESOLVED' ? '#10b981' : 'var(--border-color)'}`,
                  borderRadius: '6px',
                  padding: '1rem',
                  display: 'flex',
                  flexDirection: 'column',
                  justifyContent: 'space-between',
                }}
              >
                <div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '0.5rem' }}>
                    <span style={{ fontSize: '0.75rem', fontWeight: 600, color: '#38bdf8' }}>{task.id}</span>
                    {task.status === 'RESOLVED' ? (
                      <span style={{ display: 'inline-flex', alignItems: 'center', gap: '0.2rem', padding: '0.1rem 0.4rem', borderRadius: '4px', backgroundColor: '#064e3b', color: '#6ee7b7', fontSize: '0.7rem', fontWeight: 600 }}>
                        <CheckCircle2 size={10} aria-hidden="true" /> VERIFIED RESOLVED
                      </span>
                    ) : task.status === 'FALSE_RESOLVED' ? (
                      <span style={{ display: 'inline-flex', alignItems: 'center', gap: '0.2rem', padding: '0.1rem 0.4rem', borderRadius: '4px', backgroundColor: '#7f1d1d', color: '#fca5a5', fontSize: '0.7rem', fontWeight: 600 }}>
                        <RotateCcw size={10} aria-hidden="true" /> AUTO-REOPENED
                      </span>
                    ) : (
                      <span style={{ display: 'inline-flex', alignItems: 'center', gap: '0.2rem', padding: '0.1rem 0.4rem', borderRadius: '4px', backgroundColor: '#1e293b', color: '#94a3b8', fontSize: '0.7rem', fontWeight: 600 }}>
                        {task.status}
                      </span>
                    )}
                  </div>

                  <h3 style={{ fontSize: '0.95rem', fontWeight: 600, margin: '0 0 0.5rem 0', color: 'var(--text-primary)' }}>
                    {task.title}
                  </h3>

                  <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', display: 'flex', flexDirection: 'column', gap: '0.25rem', marginBottom: '0.75rem' }}>
                    <div><strong>Category:</strong> {task.category}</div>
                    <div><strong>Assignee:</strong> {task.assignee}</div>
                    <div><strong>Target:</strong> <code>{task.resourceId}</code> ({task.provider})</div>
                  </div>

                  <div style={{ fontSize: '0.75rem', padding: '0.5rem', backgroundColor: 'var(--bg-secondary)', borderRadius: '4px', border: '1px solid var(--border-color)', marginBottom: '0.75rem' }}>
                    <strong style={{ color: 'var(--text-secondary)' }}>Verification Condition:</strong>
                    <div style={{ color: task.status === 'FALSE_RESOLVED' ? '#fca5a5' : 'var(--text-primary)', marginTop: '0.15rem' }}>
                      {task.verificationCondition}
                    </div>
                  </div>
                </div>

                <div style={{ borderTop: '1px solid var(--border-color)', paddingTop: '0.75rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '0.2rem' }}>
                    <span style={{ fontSize: '0.7rem', color: 'var(--text-secondary)' }}>Savings:</span>
                    <CostValue
                      amount={task.status === 'RESOLVED' ? task.realisedSavings : task.projectedSavings}
                      source={task.status === 'RESOLVED' ? 'ACTUAL' : 'ESTIMATED'}
                      explanation={createCostExplanation('Remediation Savings Ledger')}
                    />
                  </div>

                  <button
                    type="button"
                    style={{
                      padding: '0.3rem 0.6rem',
                      borderRadius: '4px',
                      backgroundColor: '#0369a1',
                      color: '#ffffff',
                      border: 'none',
                      fontSize: '0.75rem',
                      fontWeight: 700,
                      cursor: 'pointer',
                    }}
                  >
                    Re-Test Condition
                  </button>
                </div>
              </article>
            ))}
          </div>
        )}
      </section>
    </div>
  );
};
export default RemediationBoardPage;
