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

export const ProvisioningRequestsPage: React.FC<{ isDemo?: boolean }> = ({ isDemo = true }) => {
  const { data: apiRequests, loading, error, errorMessage, refetch } = useApiData<any>('/api/v1/provisioning-requests');
  const [requests, setRequests] = useState<ProvisioningRequestItem[]>([]);
  const [statusFilter, setStatusFilter] = useState<string>('ALL');

  useEffect(() => {
    if (apiRequests) {
      const list = Array.isArray(apiRequests) ? apiRequests : (apiRequests.items || []);
      setRequests(list.map((r: any) => ({
        id: r.id || r.request_id || 'PR-01',
        requester: r.owner_email || r.requester || 'user@enterprise.internal',
        scope: r.target_scope || r.scope || 'APP-PROD',
        provider: r.provider || 'AWS',
        service: r.service || 'Amazon EC2',
        sizingSpec: r.sizing_spec || r.sizingSpec || `${r.intended_application || 'Application'} Workload`,
        estimatedMonthlyCost: r.monthly_cost !== undefined ? Number(r.monthly_cost) : (r.estimatedMonthlyCost ?? null),
        status: (r.status || 'PENDING_APPROVAL') as ProvisioningRequestItem['status'],
        quotaPassed: r.quota_passed !== undefined ? r.quota_passed : true,
        budgetPassed: r.budget_passed !== undefined ? r.budget_passed : true,
        actualSpendMonth1: r.actual_spend_month1 ?? null,
        actualSpendMonth2: r.actual_spend_month2 ?? null,
        actualSpendMonth3: r.actual_spend_month3 ?? null,
        bypassRationale: r.bypass_rationale || r.bypassRationale,
      })));
    }
  }, [apiRequests]);

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
            Cost-Aware Provisioning Gate & Approvals
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
            Provisioning Governance
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

        {loading ? (
          <SkeletonLoader variant="table" rows={3} />
        ) : error ? (
          <ErrorState
            title="Failed to Load Provisioning Requests"
            message={errorMessage || 'Error contacting provisioning requests API'}
            onRetry={refetch}
          />
        ) : filtered.length === 0 ? (
          <EmptyState type="NO_DATA" titleOverride="No Provisioning Requests" descriptionOverride="No pre-deployment sizing requests found for this scope or filter." actionTextOverride="Refresh Requests" onAction={refetch} />
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
