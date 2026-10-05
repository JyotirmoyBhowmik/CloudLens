import React, { useState, useEffect } from 'react';
import {
  Breadcrumb,
  CostValue,
  createCostExplanation,
  NullValue,
  FreshnessIndicator,
} from '../design-system';
import { DemoModeBanner } from '../components/DemoModeBanner';
import { CheckCircle2, XCircle, Zap, Clock } from 'lucide-react';

interface ProvisioningRequestItem {
  id: string;
  requester: string;
  scope: string;
  provider: string;
  service: string;
  sizingSpec: string;
  estimatedMonthlyCost: number | null;
  status: 'APPROVED' | 'PENDING_APPROVAL' | 'BLOCKED_BUDGET' | 'BLOCKED_QUOTA' | 'EMERGENCY_BYPASS' | 'REJECTED';
  quotaPassed: boolean;
  budgetPassed: boolean;
  actualSpendMonth1: number | null;
  actualSpendMonth2: number | null;
  actualSpendMonth3: number | null;
  bypassRationale?: string;
}

const DEMO_REQUESTS: ProvisioningRequestItem[] = [
  {
    id: 'PR-2026-101',
    requester: 'sarah.chen (Engineering Lead)',
    scope: 'APP-CHECKOUT-PROD',
    provider: 'AWS',
    service: 'Amazon EC2',
    sizingSpec: '8x c6i.2xlarge (16 vCPU, 32 GiB)',
    estimatedMonthlyCost: 1989.12,
    status: 'APPROVED',
    quotaPassed: true,
    budgetPassed: true,
    actualSpendMonth1: 1940.50,
    actualSpendMonth2: 1978.20,
    actualSpendMonth3: 2012.00,
  },
  {
    id: 'PR-2026-102',
    requester: 'dev-team-alpha',
    scope: 'APP-SEARCH-INDEXER',
    provider: 'GCP',
    service: 'Cloud Bigtable',
    sizingSpec: '6x SSD Nodes (us-central1)',
    estimatedMonthlyCost: 2835.00,
    status: 'BLOCKED_BUDGET',
    quotaPassed: true,
    budgetPassed: false,
    actualSpendMonth1: null,
    actualSpendMonth2: null,
    actualSpendMonth3: null,
  },
  {
    id: 'PR-2026-103',
    requester: 'ops-oncall (Incident P1-492)',
    scope: 'APP-AUTH-GATEWAY',
    provider: 'AWS',
    service: 'Amazon EC2',
    sizingSpec: '12x m5.2xlarge failover fleet',
    estimatedMonthlyCost: 3450.00,
    status: 'EMERGENCY_BYPASS',
    quotaPassed: false,
    budgetPassed: false,
    actualSpendMonth1: 3410.00,
    actualSpendMonth2: null,
    actualSpendMonth3: null,
    bypassRationale: 'P1 outage mitigating primary auth latency collapse. Post-hoc FinOps review scheduled within 48h.',
  },
  {
    id: 'PR-2026-104',
    requester: 'alex.m (ML Researcher)',
    scope: 'DATA-TRAINING-SANDBOX',
    provider: 'AZURE',
    service: 'Virtual Machines',
    sizingSpec: '4x Standard_NC24ads_A100_v4',
    estimatedMonthlyCost: 11420.00,
    status: 'PENDING_APPROVAL',
    quotaPassed: true,
    budgetPassed: true,
    actualSpendMonth1: null,
    actualSpendMonth2: null,
    actualSpendMonth3: null,
  },
];

export const ProvisioningRequestsPage: React.FC<{ isDemo?: boolean }> = ({ isDemo = true }) => {
  const [requests, setRequests] = useState<ProvisioningRequestItem[]>(DEMO_REQUESTS);
  const [statusFilter, setStatusFilter] = useState<string>('ALL');

  useEffect(() => {
    if (!isDemo) {
      setRequests([]);
    } else {
      setRequests(DEMO_REQUESTS);
    }
  }, [isDemo]);

  const filtered = requests.filter((r) => {
    if (statusFilter !== 'ALL' && r.status !== statusFilter) return false;
    return true;
  });

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem', width: '100%' }}>
      <DemoModeBanner isDemo={isDemo} />

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Breadcrumb
          items={[
            { label: 'Home', href: '/' },
            { label: 'Provisioning Requests', isCurrent: true },
          ]}
        />
        <FreshnessIndicator lastSyncedAt="2026-10-05T12:00:00Z" provider="Multi-Cloud" />
      </div>

      <header>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '0.25rem' }}>
          <h1 style={{ fontSize: '1.75rem', fontWeight: 700, margin: 0, color: 'var(--text-primary)' }}>
            S-23: Cost-Aware Provisioning Gate & Approvals
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
            Addendum B / Prompt 55 / API-051
          </span>
        </div>
        <p style={{ color: 'var(--text-secondary)', margin: 0, fontSize: '0.9rem' }}>
          Pre-deployment automated budget and quota validation, emergency bypass governance, and 3-period actuals tracking.
        </p>
      </header>

      {/* KPI Highlight Strip */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '1rem' }}>
        <div style={{ backgroundColor: 'var(--bg-secondary)', border: '1px solid var(--border-color)', borderRadius: '8px', padding: '1rem' }}>
          <span style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>Total Requests</span>
          <div style={{ fontSize: '1.5rem', fontWeight: 700, color: 'var(--text-primary)', marginTop: '0.25rem' }}>
            {requests.length > 0 ? requests.length : <NullValue state="NO_DATA" />}
          </div>
        </div>

        <div style={{ backgroundColor: 'var(--bg-secondary)', border: '1px solid #10b981', borderRadius: '8px', padding: '1rem' }}>
          <span style={{ fontSize: '0.8rem', color: '#6ee7b7' }}>Approved & Tracking</span>
          <div style={{ fontSize: '1.5rem', fontWeight: 700, color: '#34d399', marginTop: '0.25rem' }}>
            {requests.length > 0 ? requests.filter((r) => r.status === 'APPROVED').length : <NullValue state="ZERO" />}
          </div>
        </div>

        <div style={{ backgroundColor: 'var(--bg-secondary)', border: '1px solid #ef4444', borderRadius: '8px', padding: '1rem' }}>
          <span style={{ fontSize: '0.8rem', color: '#f87171' }}>Pre-Flight Blocked</span>
          <div style={{ fontSize: '1.5rem', fontWeight: 700, color: '#ef4444', marginTop: '0.25rem' }}>
            {requests.length > 0 ? requests.filter((r) => r.status.startsWith('BLOCKED')).length : <NullValue state="ZERO" />}
          </div>
        </div>

        <div style={{ backgroundColor: 'var(--bg-secondary)', border: '1px solid #f59e0b', borderRadius: '8px', padding: '1rem' }}>
          <span style={{ fontSize: '0.8rem', color: '#fbbf24' }}>Emergency Bypasses</span>
          <div style={{ fontSize: '1.5rem', fontWeight: 700, color: '#fbbf24', marginTop: '0.25rem' }}>
            {requests.length > 0 ? requests.filter((r) => r.status === 'EMERGENCY_BYPASS').length : <NullValue state="ZERO" />}
          </div>
        </div>
      </div>

      {/* Main Table Card */}
      <section
        aria-labelledby="provisioning-table-heading"
        style={{
          backgroundColor: 'var(--bg-secondary)',
          border: '1px solid var(--border-color)',
          borderRadius: '8px',
          padding: '1.25rem',
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
          <h2 id="provisioning-table-heading" style={{ fontSize: '1.1rem', fontWeight: 600, margin: 0 }}>
            Provisioning Evaluation Queue
          </h2>

          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            aria-label="Filter by status"
            style={{
              padding: '0.4rem 0.6rem',
              fontSize: '0.8rem',
              borderRadius: '6px',
              border: '1px solid var(--border-color)',
              backgroundColor: 'var(--bg-primary)',
              color: 'var(--text-primary)',
            }}
          >
            <option value="ALL">All Statuses</option>
            <option value="APPROVED">Approved</option>
            <option value="PENDING_APPROVAL">Pending Approval</option>
            <option value="BLOCKED_BUDGET">Blocked (Budget)</option>
            <option value="EMERGENCY_BYPASS">Emergency Bypass</option>
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
              No provisioning requests found for this scope.
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
                  <th style={{ padding: '0.6rem' }}>Request ID / Scope</th>
                  <th style={{ padding: '0.6rem' }}>Requester</th>
                  <th style={{ padding: '0.6rem' }}>Requested Sizing</th>
                  <th style={{ padding: '0.6rem' }}>Estimated Cost</th>
                  <th style={{ padding: '0.6rem' }}>Pre-Flight Checks</th>
                  <th style={{ padding: '0.6rem' }}>Gate Decision</th>
                  <th style={{ padding: '0.6rem' }}>3-Period Actuals</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((req) => (
                  <tr key={req.id} style={{ borderBottom: '1px solid var(--border-color)' }}>
                    <td style={{ padding: '0.75rem 0.6rem' }}>
                      <strong>{req.id}</strong>
                      <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>{req.scope}</div>
                    </td>
                    <td style={{ padding: '0.75rem 0.6rem' }}>{req.requester}</td>
                    <td style={{ padding: '0.75rem 0.6rem' }}>
                      <div>{req.sizingSpec}</div>
                      <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>{req.provider} - {req.service}</div>
                    </td>
                    <td style={{ padding: '0.75rem 0.6rem' }}>
                      <CostValue
                        amount={req.estimatedMonthlyCost}
                        source="ESTIMATED"
                        explanation={createCostExplanation('Pre-Flight Sizing Estimate', {
                          pricingSource: 'Retail Rate Card',
                          region: 'us-east-1',
                        })}
                      />
                    </td>
                    <td style={{ padding: '0.75rem 0.6rem' }}>
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.2rem', fontSize: '0.75rem' }}>
                        <span style={{ color: req.budgetPassed ? '#34d399' : '#f87171' }}>
                          Budget: {req.budgetPassed ? 'PASSED' : 'BLOCKED'}
                        </span>
                        <span style={{ color: req.quotaPassed ? '#34d399' : '#f87171' }}>
                          Quota: {req.quotaPassed ? 'PASSED' : 'BLOCKED'}
                        </span>
                      </div>
                    </td>
                    <td style={{ padding: '0.75rem 0.6rem' }}>
                      {req.status === 'APPROVED' ? (
                        <span style={{ display: 'inline-flex', alignItems: 'center', gap: '0.25rem', padding: '0.15rem 0.5rem', borderRadius: '4px', backgroundColor: '#064e3b', color: '#6ee7b7', fontSize: '0.75rem', fontWeight: 600 }}>
                          <CheckCircle2 size={12} aria-hidden="true" /> APPROVED
                        </span>
                      ) : req.status === 'EMERGENCY_BYPASS' ? (
                        <div>
                          <span style={{ display: 'inline-flex', alignItems: 'center', gap: '0.25rem', padding: '0.15rem 0.5rem', borderRadius: '4px', backgroundColor: '#78350f', color: '#fde68a', fontSize: '0.75rem', fontWeight: 600 }}>
                            <Zap size={12} aria-hidden="true" /> EMERGENCY BYPASS
                          </span>
                          {req.bypassRationale && (
                            <div style={{ fontSize: '0.7rem', color: '#fde68a', marginTop: '0.25rem', maxWidth: '200px' }}>
                              {req.bypassRationale}
                            </div>
                          )}
                        </div>
                      ) : req.status.startsWith('BLOCKED') ? (
                        <span style={{ display: 'inline-flex', alignItems: 'center', gap: '0.25rem', padding: '0.15rem 0.5rem', borderRadius: '4px', backgroundColor: '#7f1d1d', color: '#fca5a5', fontSize: '0.75rem', fontWeight: 600 }}>
                          <XCircle size={12} aria-hidden="true" /> {req.status}
                        </span>
                      ) : (
                        <span style={{ display: 'inline-flex', alignItems: 'center', gap: '0.25rem', padding: '0.15rem 0.5rem', borderRadius: '4px', backgroundColor: '#0f172a', color: '#38bdf8', fontSize: '0.75rem', fontWeight: 600, border: '1px solid #38bdf8' }}>
                          <Clock size={12} aria-hidden="true" /> {req.status}
                        </span>
                      )}
                    </td>
                    <td style={{ padding: '0.75rem 0.6rem' }}>
                      {req.status === 'APPROVED' && req.actualSpendMonth1 !== null ? (
                        <div style={{ fontSize: '0.75rem' }}>
                          <div>M1: ${req.actualSpendMonth1.toFixed(2)}</div>
                          <div>M2: {req.actualSpendMonth2 !== null ? `$${req.actualSpendMonth2.toFixed(2)}` : <NullValue state="NO_DATA" />}</div>
                          <div>M3: {req.actualSpendMonth3 !== null ? `$${req.actualSpendMonth3.toFixed(2)}` : <NullValue state="NO_DATA" />}</div>
                        </div>
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
export default ProvisioningRequestsPage;
