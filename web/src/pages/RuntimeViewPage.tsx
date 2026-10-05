import React, { useState, useEffect } from 'react';
import {
  Breadcrumb,
  CostValue,
  createCostExplanation,
  NullValue,
  FreshnessIndicator,
} from '../design-system';
import { DemoModeBanner } from '../components/DemoModeBanner';
import { Play, Pause } from 'lucide-react';

interface RuntimeResourceItem {
  id: string;
  resourceId: string;
  provider: string;
  environment: string;
  declaredSchedule: string;
  currentState: 'RUNNING' | 'STOPPED';
  runningHoursMonth: number | null;
  scheduledHoursMonth: number | null;
  adherencePct: number | null;
  outOfHoursWasteCost: number | null;
}

const DEMO_RUNTIMES: RuntimeResourceItem[] = [
  {
    id: 'rt-01',
    resourceId: 'res-aws-dev-runner-01',
    provider: 'AWS',
    environment: 'DEVELOPMENT',
    declaredSchedule: 'BUSINESS_HOURS_08_18',
    currentState: 'RUNNING',
    runningHoursMonth: 410,
    scheduledHoursMonth: 220,
    adherencePct: 53.6,
    outOfHoursWasteCost: 182.40,
  },
  {
    id: 'rt-02',
    resourceId: 'res-az-qa-cluster-node',
    provider: 'AZURE',
    environment: 'QA',
    declaredSchedule: 'BUSINESS_HOURS_08_18',
    currentState: 'STOPPED',
    runningHoursMonth: 216,
    scheduledHoursMonth: 220,
    adherencePct: 98.2,
    outOfHoursWasteCost: 0.00,
  },
  {
    id: 'rt-03',
    resourceId: 'res-gcp-prod-fe-lb',
    provider: 'GCP',
    environment: 'PRODUCTION',
    declaredSchedule: 'CONTINUOUS_24X7',
    currentState: 'RUNNING',
    runningHoursMonth: 730,
    scheduledHoursMonth: 730,
    adherencePct: 100.0,
    outOfHoursWasteCost: 0.00,
  },
  {
    id: 'rt-04',
    resourceId: 'res-oci-sandbox-db',
    provider: 'OCI',
    environment: 'SANDBOX',
    declaredSchedule: 'NOT_SCHEDULED',
    currentState: 'RUNNING',
    runningHoursMonth: null,
    scheduledHoursMonth: null,
    adherencePct: null,
    outOfHoursWasteCost: null,
  },
];

export const RuntimeViewPage: React.FC<{ isDemo?: boolean }> = ({ isDemo = true }) => {
  const [items, setItems] = useState<RuntimeResourceItem[]>(DEMO_RUNTIMES);

  useEffect(() => {
    if (!isDemo) {
      setItems([]);
    } else {
      setItems(DEMO_RUNTIMES);
    }
  }, [isDemo]);

  const totalWaste = items.reduce((sum, i) => sum + (i.outOfHoursWasteCost || 0), 0);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem', width: '100%' }}>
      <DemoModeBanner isDemo={isDemo} />

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Breadcrumb
          items={[
            { label: 'Home', href: '/' },
            { label: 'Runtime & Schedule Adherence', isCurrent: true },
          ]}
        />
        <FreshnessIndicator lastSyncedAt="2026-10-05T12:00:00Z" provider="Multi-Cloud" />
      </div>

      <header>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '0.25rem' }}>
          <h1 style={{ fontSize: '1.75rem', fontWeight: 700, margin: 0, color: 'var(--text-primary)' }}>
            S-10: Resource Runtime & Schedule Adherence
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
            Prompt 26 / BBP Sec 20
          </span>
        </div>
        <p style={{ color: 'var(--text-secondary)', margin: 0, fontSize: '0.9rem' }}>
          Evaluate active running states against declared uptime schedules and quantify out-of-hours waste costs.
        </p>
      </header>

      {/* KPI Cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '1rem' }}>
        <div style={{ backgroundColor: 'var(--bg-secondary)', border: '1px solid var(--border-color)', borderRadius: '8px', padding: '1rem' }}>
          <span style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>Tracked Schedulable Assets</span>
          <div style={{ fontSize: '1.5rem', fontWeight: 700, color: 'var(--text-primary)', marginTop: '0.25rem' }}>
            {items.length > 0 ? items.length : <NullValue state="NO_DATA" />}
          </div>
        </div>

        <div style={{ backgroundColor: 'var(--bg-secondary)', border: '1px solid #ef4444', borderRadius: '8px', padding: '1rem' }}>
          <span style={{ fontSize: '0.8rem', color: '#f87171' }}>Out-of-Hours Waste Cost</span>
          <div style={{ fontSize: '1.5rem', fontWeight: 700, color: '#ef4444', marginTop: '0.25rem' }}>
            {items.length > 0 ? (
              <CostValue
                amount={totalWaste}
                source="ACTUAL"
                explanation={createCostExplanation('Schedule Breach Waste Spend')}
                showBadge={false}
              />
            ) : (
              <NullValue state="ZERO" />
            )}
          </div>
          <span style={{ fontSize: '0.75rem', color: '#fca5a5' }}>Running during off-hours</span>
        </div>

        <div style={{ backgroundColor: 'var(--bg-secondary)', border: '1px solid #10b981', borderRadius: '8px', padding: '1rem' }}>
          <span style={{ fontSize: '0.8rem', color: '#6ee7b7' }}>Average Schedule Adherence</span>
          <div style={{ fontSize: '1.5rem', fontWeight: 700, color: '#34d399', marginTop: '0.25rem' }}>
            {items.length > 0 ? '83.9%' : <NullValue state="NOT_APPLICABLE" />}
          </div>
          <span style={{ fontSize: '0.75rem', color: '#a7f3d0' }}>Target: &gt;95%</span>
        </div>
      </div>

      {/* Table */}
      <section
        aria-labelledby="runtime-table-heading"
        style={{
          backgroundColor: 'var(--bg-secondary)',
          border: '1px solid var(--border-color)',
          borderRadius: '8px',
          padding: '1.25rem',
        }}
      >
        <h2 id="runtime-table-heading" style={{ fontSize: '1.1rem', fontWeight: 600, marginBottom: '1rem' }}>
          Runtime State & Schedule Inventory
        </h2>

        {items.length === 0 ? (
          <div
            style={{
              padding: '2.5rem',
              borderRadius: '6px',
              border: '1px dashed var(--border-color)',
              textAlign: 'center',
            }}
          >
            <p style={{ color: 'var(--text-secondary)', marginBottom: '0.5rem' }}>
              No runtime records recorded in this scope.
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
                  <th style={{ padding: '0.6rem' }}>Resource ID / Provider</th>
                  <th style={{ padding: '0.6rem' }}>Environment</th>
                  <th style={{ padding: '0.6rem' }}>Declared Schedule</th>
                  <th style={{ padding: '0.6rem' }}>Current State</th>
                  <th style={{ padding: '0.6rem' }}>Running / Scheduled Hours</th>
                  <th style={{ padding: '0.6rem' }}>Adherence</th>
                  <th style={{ padding: '0.6rem' }}>Waste Cost</th>
                </tr>
              </thead>
              <tbody>
                {items.map((it) => (
                  <tr key={it.id} style={{ borderBottom: '1px solid var(--border-color)' }}>
                    <td style={{ padding: '0.75rem 0.6rem' }}>
                      <strong>{it.resourceId}</strong>
                      <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>{it.provider}</div>
                    </td>
                    <td style={{ padding: '0.75rem 0.6rem' }}>
                      <code>{it.environment}</code>
                    </td>
                    <td style={{ padding: '0.75rem 0.6rem' }}>
                      {it.declaredSchedule}
                    </td>
                    <td style={{ padding: '0.75rem 0.6rem' }}>
                      <span
                        style={{
                          display: 'inline-flex',
                          alignItems: 'center',
                          gap: '0.2rem',
                          padding: '0.15rem 0.45rem',
                          borderRadius: '4px',
                          fontSize: '0.75rem',
                          fontWeight: 600,
                          backgroundColor: it.currentState === 'RUNNING' ? '#064e3b' : '#1e293b',
                          color: it.currentState === 'RUNNING' ? '#6ee7b7' : '#94a3b8',
                        }}
                      >
                        {it.currentState === 'RUNNING' ? <Play size={10} aria-hidden="true" /> : <Pause size={10} aria-hidden="true" />}
                        {it.currentState}
                      </span>
                    </td>
                    <td style={{ padding: '0.75rem 0.6rem' }}>
                      {it.runningHoursMonth !== null && it.scheduledHoursMonth !== null ? (
                        <span>{it.runningHoursMonth}h / {it.scheduledHoursMonth}h</span>
                      ) : (
                        <NullValue state="NOT_APPLICABLE" />
                      )}
                    </td>
                    <td style={{ padding: '0.75rem 0.6rem' }}>
                      {it.adherencePct !== null ? (
                        <span style={{ fontWeight: 600, color: it.adherencePct < 70 ? '#f87171' : '#34d399' }}>
                          {it.adherencePct.toFixed(1)}%
                        </span>
                      ) : (
                        <NullValue state="NOT_APPLICABLE" />
                      )}
                    </td>
                    <td style={{ padding: '0.75rem 0.6rem' }}>
                      {it.outOfHoursWasteCost !== null ? (
                        it.outOfHoursWasteCost > 0 ? (
                          <CostValue
                            amount={it.outOfHoursWasteCost}
                            source="ACTUAL"
                            explanation={createCostExplanation('Out of Hours Energy & Spend Waste')}
                          />
                        ) : (
                          <NullValue state="ZERO" customZeroValue="$0.00" />
                        )
                      ) : (
                        <NullValue state="NOT_APPLICABLE" />
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
export default RuntimeViewPage;
