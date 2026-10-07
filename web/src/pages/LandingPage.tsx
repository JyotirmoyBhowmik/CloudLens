import React from 'react';
import { useAuth } from '../context/AuthContext';
import {
  Breadcrumb,
  CostValue,
  createCostExplanation,
  NullValue,
  FreshnessIndicator,
} from '../design-system';
import { DemoModeBanner } from '../components/DemoModeBanner';
import {
  PieChart,
  Layers,
  TrendingUp,
  ArrowRight,
  ShieldAlert,
} from 'lucide-react';
import { useNavigate } from 'react-router-dom';

export interface LandingPageProps {
  userRole?: string;
  isDemo?: boolean;
}

export const LandingPage: React.FC<LandingPageProps> = ({
  userRole,
  isDemo = true,
}) => {
  const navigate = useNavigate();
  const auth = useAuth();
  const activeRoleDisplay = userRole || (auth.roles.length > 0 ? auth.roles.join(', ') : 'Authenticated User');

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem', width: '100%' }}>
      <DemoModeBanner isDemo={isDemo} />

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Breadcrumb
          items={[{ label: 'Home', isCurrent: true }]}
        />
        <FreshnessIndicator
          lastSyncedAt="2026-10-05T12:00:00Z"
          provider="System"
        />
      </div>

      <header>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '0.25rem' }}>
          <h1 style={{ fontSize: '1.75rem', fontWeight: 700, margin: 0, color: 'var(--text-primary)' }}>
            S-02: CloudLens Governance & FinOps Portal
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
            Role Landing: {activeRoleDisplay}
          </span>
        </div>
        <p style={{ color: 'var(--text-secondary)', margin: 0, fontSize: '0.9rem' }}>
          Welcome back. Unified governance, telemetry, rate breakdown, and financial visibility across all connected estates.
        </p>
      </header>

      {/* Primary KPI Header */}
      <section aria-label="Estate Summary Statistics" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '1rem' }}>
        <div style={{ backgroundColor: 'var(--bg-secondary)', border: '1px solid var(--border-color)', borderRadius: '8px', padding: '1.25rem' }}>
          <span style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>Total Monthly Spend (Billed)</span>
          <div style={{ fontSize: '1.5rem', fontWeight: 700, color: 'var(--text-primary)', marginTop: '0.35rem' }}>
            {isDemo ? (
              <CostValue
                amount={428950.00}
                source="ACTUAL"
                explanation={createCostExplanation('Current Month Multi-Cloud Aggregated Spend')}
              />
            ) : (
              <NullValue state="NO_DATA" />
            )}
          </div>
          <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>FOCUS 1.0 Normalised</span>
        </div>

        <div style={{ backgroundColor: 'var(--bg-secondary)', border: '1px solid var(--border-color)', borderRadius: '8px', padding: '1.25rem' }}>
          <span style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>Discovered Cloud Assets</span>
          <div style={{ fontSize: '1.5rem', fontWeight: 700, color: 'var(--text-primary)', marginTop: '0.35rem' }}>
            {isDemo ? '1,428' : <NullValue state="NO_DATA" />}
          </div>
          <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>Across 4 Cloud Providers</span>
        </div>

        <div style={{ backgroundColor: 'var(--bg-secondary)', border: '1px solid var(--border-color)', borderRadius: '8px', padding: '1.25rem' }}>
          <span style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>Policy Compliance</span>
          <div style={{ fontSize: '1.5rem', fontWeight: 700, color: '#34d399', marginTop: '0.35rem' }}>
            {isDemo ? '94.2%' : <NullValue state="NOT_APPLICABLE" />}
          </div>
          <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>18 Declarative Rules</span>
        </div>

        <div style={{ backgroundColor: 'var(--bg-secondary)', border: '1px solid var(--border-color)', borderRadius: '8px', padding: '1.25rem' }}>
          <span style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>Identified Waste Pipeline</span>
          <div style={{ fontSize: '1.5rem', fontWeight: 700, color: '#38bdf8', marginTop: '0.35rem' }}>
            {isDemo ? (
              <CostValue
                amount={28450.00}
                source="ESTIMATED"
                explanation={createCostExplanation('Identified Actionable Waste Pipeline')}
              />
            ) : (
              <NullValue state="ZERO" />
            )}
          </div>
          <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>In Remediation Backlog</span>
        </div>
      </section>

      {/* Persona Fast Navigation Hub */}
      <section aria-labelledby="quick-nav-heading">
        <h2 id="quick-nav-heading" style={{ fontSize: '1.2rem', fontWeight: 600, marginBottom: '1rem', color: 'var(--text-primary)' }}>
          Quick Access by Operational Area
        </h2>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '1rem' }}>
          <article
            style={{
              backgroundColor: 'var(--bg-secondary)',
              border: '1px solid var(--border-color)',
              borderRadius: '8px',
              padding: '1.25rem',
              display: 'flex',
              flexDirection: 'column',
              justifyContent: 'space-between',
              cursor: 'pointer',
            }}
            onClick={() => navigate('/executive')}
          >
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: '#38bdf8', marginBottom: '0.5rem' }}>
                <PieChart size={18} aria-hidden="true" />
                <h3 style={{ fontSize: '1rem', fontWeight: 600, margin: 0, color: 'var(--text-primary)' }}>
                  Executive Cost Pulse (S-03)
                </h3>
              </div>
              <p style={{ fontSize: '0.8125rem', color: 'var(--text-secondary)', margin: '0 0 1rem 0' }}>
                Macro spend trajectory, provider distribution, budget variance, and quarterly burn rate.
              </p>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.25rem', color: '#38bdf8', fontSize: '0.8125rem', fontWeight: 600 }}>
              <span>Open Executive Dashboard</span>
              <ArrowRight size={14} aria-hidden="true" />
            </div>
          </article>

          <article
            style={{
              backgroundColor: 'var(--bg-secondary)',
              border: '1px solid var(--border-color)',
              borderRadius: '8px',
              padding: '1.25rem',
              display: 'flex',
              flexDirection: 'column',
              justifyContent: 'space-between',
              cursor: 'pointer',
            }}
            onClick={() => navigate('/inventory')}
          >
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: '#34d399', marginBottom: '0.5rem' }}>
                <Layers size={18} aria-hidden="true" />
                <h3 style={{ fontSize: '1rem', fontWeight: 600, margin: 0, color: 'var(--text-primary)' }}>
                  Cloud Inventory Explorer (S-07)
                </h3>
              </div>
              <p style={{ fontSize: '0.8125rem', color: 'var(--text-secondary)', margin: '0 0 1rem 0' }}>
                Comprehensive 35-field inventory schema, tags, ownership attributions, and lateral lenses.
              </p>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.25rem', color: '#34d399', fontSize: '0.8125rem', fontWeight: 600 }}>
              <span>Search Inventory</span>
              <ArrowRight size={14} aria-hidden="true" />
            </div>
          </article>

          <article
            style={{
              backgroundColor: 'var(--bg-secondary)',
              border: '1px solid var(--border-color)',
              borderRadius: '8px',
              padding: '1.25rem',
              display: 'flex',
              flexDirection: 'column',
              justifyContent: 'space-between',
              cursor: 'pointer',
            }}
            onClick={() => navigate('/remediation')}
          >
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: '#fbbf24', marginBottom: '0.5rem' }}>
                <TrendingUp size={18} aria-hidden="true" />
                <h3 style={{ fontSize: '1rem', fontWeight: 600, margin: 0, color: 'var(--text-primary)' }}>
                  Remediation Board (S-24)
                </h3>
              </div>
              <p style={{ fontSize: '0.8125rem', color: 'var(--text-secondary)', margin: '0 0 1rem 0' }}>
                Actionable waste tasks, verified savings ledgers, and automated condition re-testing.
              </p>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.25rem', color: '#fbbf24', fontSize: '0.8125rem', fontWeight: 600 }}>
              <span>View Tasks</span>
              <ArrowRight size={14} aria-hidden="true" />
            </div>
          </article>

          <article
            style={{
              backgroundColor: 'var(--bg-secondary)',
              border: '1px solid var(--border-color)',
              borderRadius: '8px',
              padding: '1.25rem',
              display: 'flex',
              flexDirection: 'column',
              justifyContent: 'space-between',
              cursor: 'pointer',
            }}
            onClick={() => navigate('/control-tower')}
          >
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: '#fca5a5', marginBottom: '0.5rem' }}>
                <ShieldAlert size={18} aria-hidden="true" />
                <h3 style={{ fontSize: '1rem', fontWeight: 600, margin: 0, color: 'var(--text-primary)' }}>
                  Platform Control Tower
                </h3>
              </div>
              <p style={{ fontSize: '0.8125rem', color: 'var(--text-secondary)', margin: '0 0 1rem 0' }}>
                14 real-time telemetry panels, cross-tenant operational health, and superuser actions.
              </p>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.25rem', color: '#fca5a5', fontSize: '0.8125rem', fontWeight: 600 }}>
              <span>Launch Control Tower</span>
              <ArrowRight size={14} aria-hidden="true" />
            </div>
          </article>
        </div>
      </section>
    </div>
  );
};
export default LandingPage;
