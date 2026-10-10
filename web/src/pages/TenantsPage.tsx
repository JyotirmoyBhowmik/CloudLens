import React, { useState } from 'react';
import {
  Breadcrumb,
  EmptyState,
  ErrorState,
  FreshnessIndicator,
  SkeletonLoader,
} from '../design-system';
import { useApiData } from '../api';
import { apiClient } from '../api/client';
import { DemoModeBanner } from '../components/DemoModeBanner';
import {
  Plus,
  PauseCircle,
  PlayCircle,
  Users,
  X,
  Search,
} from 'lucide-react';

export interface TenantRecord {
  id: string;
  code: string;
  name: string;
  type: 'PRODUCTION' | 'NON_PRODUCTION' | 'DEMO';
  reporting_currency: string;
  fiscal_year_start: number;
  iana_timezone: string;
  retention_profile: string;
  status: 'ACTIVE' | 'SUSPENDED';
  suspension_reason?: string | null;
  created_at: string;
  updated_at: string;
}

export interface ScopeGrantRecord {
  id: string;
  tenant_id: string;
  grantee_type: string;
  grantee_id: string;
  effect: string;
  providers: string[];
  description?: string;
}

const CURRENCY_OPTIONS = ['USD', 'EUR', 'GBP', 'JPY', 'INR', 'AUD', 'CAD', 'SGD', 'CHF'];
const TYPE_OPTIONS: Array<'PRODUCTION' | 'NON_PRODUCTION' | 'DEMO'> = [
  'PRODUCTION',
  'NON_PRODUCTION',
  'DEMO',
];

export const TenantsPage: React.FC<{ isDemo?: boolean }> = ({ isDemo = false }) => {
  const { data: apiTenants, loading, error, errorMessage, refetch } = useApiData<TenantRecord[]>('/api/v1/tenants');

  // Search & Filter state
  const [search, setSearch] = useState('');

  // Create Tenant Modal state
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [newCode, setNewCode] = useState('');
  const [newName, setNewName] = useState('');
  const [newType, setNewType] = useState<'PRODUCTION' | 'NON_PRODUCTION' | 'DEMO'>('PRODUCTION');
  const [newCurrency, setNewCurrency] = useState('USD');
  const [newFyStart, setNewFyStart] = useState(1);
  const [newTimezone, setNewTimezone] = useState('UTC');
  const [newRetention, setNewRetention] = useState('STANDARD');
  const [createError, setCreateError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  // Suspend / Resume Modal state
  const [actionTenant, setActionTenant] = useState<TenantRecord | null>(null);
  const [actionType, setActionType] = useState<'SUSPEND' | 'RESUME' | null>(null);
  const [actionReason, setActionReason] = useState('');
  const [actionError, setActionError] = useState<string | null>(null);

  // Grants Modal state
  const [grantsTenant, setGrantsTenant] = useState<TenantRecord | null>(null);
  const [grantsList, setGrantsList] = useState<ScopeGrantRecord[]>([]);
  const [loadingGrants, setLoadingGrants] = useState(false);
  const [grantGranteeId, setGrantGranteeId] = useState('');
  const [grantDescription, setGrantDescription] = useState('');

  const tenants = Array.isArray(apiTenants) ? apiTenants : [];
  const filtered = tenants.filter(
    (t) =>
      t.name.toLowerCase().includes(search.toLowerCase()) ||
      t.code.toLowerCase().includes(search.toLowerCase()) ||
      t.type.toLowerCase().includes(search.toLowerCase())
  );

  const handleOpenCreate = () => {
    setNewCode('');
    setNewName('');
    setNewType('PRODUCTION');
    setNewCurrency('USD');
    setNewFyStart(1);
    setNewTimezone('UTC');
    setNewRetention('STANDARD');
    setCreateError(null);
    setIsCreateOpen(true);
  };

  const handleCreateSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setCreateError(null);
    setIsSubmitting(true);
    try {
      await apiClient.post('/api/v1/tenants', {
        code: newCode.trim().toUpperCase(),
        name: newName.trim(),
        type: newType,
        reporting_currency: newCurrency,
        fiscal_year_start: Number(newFyStart),
        iana_timezone: newTimezone.trim(),
        retention_profile: newRetention,
      });
      setIsCreateOpen(false);
      await refetch();
    } catch (err: any) {
      setCreateError(err.message || 'Failed to create tenant organization.');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleOpenAction = (tenant: TenantRecord, type: 'SUSPEND' | 'RESUME') => {
    setActionTenant(tenant);
    setActionType(type);
    setActionReason('');
    setActionError(null);
  };

  const handleActionSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!actionTenant || !actionType) return;
    if (actionReason.trim().length < 5) {
      setActionError('A valid rationale of at least 5 characters is required.');
      return;
    }
    setActionError(null);
    setIsSubmitting(true);
    try {
      const endpoint =
        actionType === 'SUSPEND'
          ? `/api/v1/tenants/${actionTenant.id}/suspend`
          : `/api/v1/tenants/${actionTenant.id}/resume`;
      await apiClient.post(endpoint, { reason: actionReason.trim() });
      setActionTenant(null);
      setActionType(null);
      await refetch();
    } catch (err: any) {
      setActionError(err.message || `Failed to ${actionType.toLowerCase()} tenant.`);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleOpenGrants = async (tenant: TenantRecord) => {
    setGrantsTenant(tenant);
    setLoadingGrants(true);
    try {
      const data = await apiClient.get<ScopeGrantRecord[]>(`/api/v1/tenants/${tenant.id}/grants`);
      setGrantsList(Array.isArray(data) ? data : []);
    } catch {
      setGrantsList([]);
    } finally {
      setLoadingGrants(false);
    }
  };

  const handleAddGrant = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!grantsTenant || !grantGranteeId.trim()) return;
    try {
      const newGrant = await apiClient.post<ScopeGrantRecord>(`/api/v1/tenants/${grantsTenant.id}/grants`, {
        grantee_type: 'USER',
        grantee_id: grantGranteeId.trim(),
        effect: 'ALLOW',
        providers: ['*'],
        description: grantDescription.trim() || undefined,
      });
      setGrantsList([...grantsList, newGrant]);
      setGrantGranteeId('');
      setGrantDescription('');
    } catch (err: any) {
      alert(err.message || 'Failed to add grant');
    }
  };

  const handleRevokeGrant = async (grantId: string) => {
    if (!grantsTenant) return;
    try {
      await apiClient.delete(`/api/v1/tenants/${grantsTenant.id}/grants/${grantId}`);
      setGrantsList(grantsList.filter((g) => g.id !== grantId));
    } catch (err: any) {
      alert(err.message || 'Failed to revoke grant');
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem', width: '100%' }}>
      <DemoModeBanner isDemo={isDemo} />

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Breadcrumb
          items={[
            { label: 'Home', href: '/' },
            { label: 'Tenant Administration', isCurrent: true },
          ]}
        />
        <FreshnessIndicator lastSyncedAt={new Date().toISOString()} provider="System" />
      </div>

      <header style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '1rem' }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '0.25rem' }}>
            <h1 style={{ fontSize: '1.75rem', fontWeight: 700, margin: 0, color: 'var(--text-primary)' }}>
              Tenant Administration & Boundaries
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
              Enterprise Governance
            </span>
          </div>
          <p style={{ color: 'var(--text-secondary)', margin: 0, fontSize: '0.9rem' }}>
            Multi-tenant organization boundary configuration, currency standards, fiscal calendars, and tenant lifecycle.
          </p>
        </div>

        <button
          id="create-tenant-open-btn"
          onClick={handleOpenCreate}
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: '0.4rem',
            padding: '0.5rem 1rem',
            backgroundColor: '#0284c7',
            color: '#ffffff',
            border: 'none',
            borderRadius: '6px',
            fontSize: '0.85rem',
            fontWeight: 600,
            cursor: 'pointer',
          }}
        >
          <Plus size={16} aria-hidden="true" />
          Create Tenant
        </button>
      </header>

      {/* Main Table Card */}
      <section
        style={{
          backgroundColor: 'var(--bg-secondary)',
          border: '1px solid var(--border-color)',
          borderRadius: '8px',
          padding: '1.25rem',
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem', flexWrap: 'wrap', gap: '0.75rem' }}>
          <h2 style={{ fontSize: '1.1rem', fontWeight: 600, margin: 0, color: 'var(--text-primary)' }}>
            Organization Directory
          </h2>

          <div style={{ position: 'relative' }}>
            <Search
              size={14}
              style={{ position: 'absolute', left: '0.6rem', top: '0.6rem', color: 'var(--text-secondary)' }}
              aria-hidden="true"
            />
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Filter by name, code, or type..."
              aria-label="Filter tenants"
              style={{
                padding: '0.4rem 0.6rem 0.4rem 2rem',
                fontSize: '0.8rem',
                borderRadius: '6px',
                border: '1px solid var(--border-color)',
                backgroundColor: 'var(--bg-primary)',
                color: 'var(--text-primary)',
              }}
            />
          </div>
        </div>

        {loading ? (
          <SkeletonLoader variant="table" rows={4} />
        ) : error ? (
          <ErrorState
            title="Failed to Load Tenants"
            message={errorMessage || 'Error communicating with tenant administration API'}
            onRetry={refetch}
          />
        ) : filtered.length === 0 ? (
          <EmptyState
            type="NO_DATA"
            titleOverride="No Tenants Registered"
            descriptionOverride="No organization tenants have been provisioned yet. Use the action below to create a tenant."
            actionTextOverride="Create Tenant Organization"
            onAction={handleOpenCreate}
          />
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table
              id="tenants-directory-table"
              style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '0.85rem' }}
            >
              <thead>
                <tr style={{ borderBottom: '1px solid var(--border-color)', color: 'var(--text-secondary)' }}>
                  <th style={{ padding: '0.6rem' }}>Code</th>
                  <th style={{ padding: '0.6rem' }}>Tenant Name</th>
                  <th style={{ padding: '0.6rem' }}>Type</th>
                  <th style={{ padding: '0.6rem' }}>Currency</th>
                  <th style={{ padding: '0.6rem' }}>FY Start</th>
                  <th style={{ padding: '0.6rem' }}>Time Zone</th>
                  <th style={{ padding: '0.6rem' }}>Retention</th>
                  <th style={{ padding: '0.6rem' }}>Status</th>
                  <th style={{ padding: '0.6rem', textAlign: 'right' }}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((t) => (
                  <tr key={t.id} style={{ borderBottom: '1px solid var(--border-color)' }}>
                    <td style={{ padding: '0.75rem 0.6rem' }}>
                      <code style={{ fontSize: '0.8rem', fontWeight: 600, color: '#38bdf8' }}>{t.code}</code>
                    </td>
                    <td style={{ padding: '0.75rem 0.6rem' }}>
                      <strong style={{ color: 'var(--text-primary)' }}>{t.name}</strong>
                      <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>{t.id}</div>
                    </td>
                    <td style={{ padding: '0.75rem 0.6rem' }}>
                      <span
                        style={{
                          padding: '0.15rem 0.5rem',
                          borderRadius: '4px',
                          fontSize: '0.7rem',
                          fontWeight: 600,
                          backgroundColor:
                            t.type === 'PRODUCTION'
                              ? 'rgba(56, 189, 248, 0.2)'
                              : t.type === 'DEMO'
                              ? 'rgba(168, 85, 247, 0.2)'
                              : 'rgba(148, 163, 184, 0.2)',
                          color:
                            t.type === 'PRODUCTION'
                              ? '#38bdf8'
                              : t.type === 'DEMO'
                              ? '#c084fc'
                              : '#94a3b8',
                        }}
                      >
                        {t.type}
                      </span>
                    </td>
                    <td style={{ padding: '0.75rem 0.6rem' }}>{t.reporting_currency}</td>
                    <td style={{ padding: '0.75rem 0.6rem' }}>Month {t.fiscal_year_start}</td>
                    <td style={{ padding: '0.75rem 0.6rem' }}>{t.iana_timezone}</td>
                    <td style={{ padding: '0.75rem 0.6rem' }}>{t.retention_profile}</td>
                    <td style={{ padding: '0.75rem 0.6rem' }}>
                      <span
                        style={{
                          padding: '0.15rem 0.5rem',
                          borderRadius: '4px',
                          fontSize: '0.7rem',
                          fontWeight: 600,
                          backgroundColor: t.status === 'ACTIVE' ? 'rgba(16, 185, 129, 0.2)' : 'rgba(239, 68, 68, 0.2)',
                          color: t.status === 'ACTIVE' ? '#34d399' : '#f87171',
                        }}
                      >
                        {t.status}
                      </span>
                      {t.suspension_reason && (
                        <div style={{ fontSize: '0.7rem', color: '#f87171', marginTop: '0.2rem' }}>
                          Reason: {t.suspension_reason}
                        </div>
                      )}
                    </td>
                    <td style={{ padding: '0.75rem 0.6rem', textAlign: 'right' }}>
                      <div style={{ display: 'inline-flex', gap: '0.4rem' }}>
                        <button
                          id={`grants-tenant-btn-${t.id}`}
                          onClick={() => handleOpenGrants(t)}
                          title="Manage User Grants"
                          style={{
                            padding: '0.3rem 0.5rem',
                            backgroundColor: 'var(--bg-primary)',
                            border: '1px solid var(--border-color)',
                            borderRadius: '4px',
                            color: 'var(--text-primary)',
                            fontSize: '0.75rem',
                            cursor: 'pointer',
                            display: 'inline-flex',
                            alignItems: 'center',
                            gap: '0.2rem',
                          }}
                        >
                          <Users size={12} aria-hidden="true" />
                          Grants
                        </button>

                        {t.status === 'ACTIVE' ? (
                          <button
                            id={`suspend-tenant-btn-${t.id}`}
                            onClick={() => handleOpenAction(t, 'SUSPEND')}
                            title="Suspend Tenant"
                            style={{
                              padding: '0.3rem 0.5rem',
                              backgroundColor: 'rgba(239, 68, 68, 0.1)',
                              border: '1px solid rgba(239, 68, 68, 0.3)',
                              borderRadius: '4px',
                              color: '#f87171',
                              fontSize: '0.75rem',
                              cursor: 'pointer',
                              display: 'inline-flex',
                              alignItems: 'center',
                              gap: '0.2rem',
                            }}
                          >
                            <PauseCircle size={12} aria-hidden="true" />
                            Suspend
                          </button>
                        ) : (
                          <button
                            id={`resume-tenant-btn-${t.id}`}
                            onClick={() => handleOpenAction(t, 'RESUME')}
                            title="Resume Tenant"
                            style={{
                              padding: '0.3rem 0.5rem',
                              backgroundColor: 'rgba(16, 185, 129, 0.1)',
                              border: '1px solid rgba(16, 185, 129, 0.3)',
                              borderRadius: '4px',
                              color: '#34d399',
                              fontSize: '0.75rem',
                              cursor: 'pointer',
                              display: 'inline-flex',
                              alignItems: 'center',
                              gap: '0.2rem',
                            }}
                          >
                            <PlayCircle size={12} aria-hidden="true" />
                            Resume
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {/* Create Tenant Modal */}
      {isCreateOpen && (
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="create-tenant-title"
          style={{
            position: 'fixed',
            inset: 0,
            backgroundColor: 'rgba(0, 0, 0, 0.7)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 1000,
            padding: '1rem',
          }}
        >
          <div
            style={{
              backgroundColor: 'var(--bg-secondary)',
              border: '1px solid var(--border-color)',
              borderRadius: '8px',
              padding: '1.5rem',
              width: '100%',
              maxWidth: '520px',
              boxShadow: '0 20px 25px -5px rgba(0, 0, 0, 0.5)',
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
              <h2 id="create-tenant-title" style={{ fontSize: '1.2rem', fontWeight: 600, margin: 0, color: 'var(--text-primary)' }}>
                Create Tenant Organization
              </h2>
              <button
                onClick={() => setIsCreateOpen(false)}
                style={{ background: 'none', border: 'none', color: 'var(--text-secondary)', cursor: 'pointer' }}
                aria-label="Close modal"
              >
                <X size={18} />
              </button>
            </div>

            {createError && (
              <div
                role="alert"
                style={{
                  padding: '0.6rem 0.8rem',
                  backgroundColor: 'rgba(239, 68, 68, 0.15)',
                  border: '1px solid #ef4444',
                  borderRadius: '6px',
                  color: '#fca5a5',
                  fontSize: '0.8rem',
                  marginBottom: '1rem',
                }}
              >
                {createError}
              </div>
            )}

            <form onSubmit={handleCreateSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '0.9rem' }}>
              <div>
                <label htmlFor="tenant-code-input" style={{ display: 'block', fontSize: '0.8rem', color: 'var(--text-secondary)', marginBottom: '0.25rem' }}>
                  Tenant Code (Unique Identifier) *
                </label>
                <input
                  id="tenant-code-input"
                  type="text"
                  required
                  value={newCode}
                  onChange={(e) => setNewCode(e.target.value.toUpperCase())}
                  placeholder="e.g. SNPL_PROD"
                  style={{
                    width: '100%',
                    padding: '0.45rem',
                    borderRadius: '6px',
                    border: '1px solid var(--border-color)',
                    backgroundColor: 'var(--bg-primary)',
                    color: 'var(--text-primary)',
                    fontSize: '0.85rem',
                  }}
                />
              </div>

              <div>
                <label htmlFor="tenant-name-input" style={{ display: 'block', fontSize: '0.8rem', color: 'var(--text-secondary)', marginBottom: '0.25rem' }}>
                  Tenant Display Name *
                </label>
                <input
                  id="tenant-name-input"
                  type="text"
                  required
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                  placeholder="e.g. SNPL Production"
                  style={{
                    width: '100%',
                    padding: '0.45rem',
                    borderRadius: '6px',
                    border: '1px solid var(--border-color)',
                    backgroundColor: 'var(--bg-primary)',
                    color: 'var(--text-primary)',
                    fontSize: '0.85rem',
                  }}
                />
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem' }}>
                <div>
                  <label htmlFor="tenant-type-select" style={{ display: 'block', fontSize: '0.8rem', color: 'var(--text-secondary)', marginBottom: '0.25rem' }}>
                    Environment Type *
                  </label>
                  <select
                    id="tenant-type-select"
                    value={newType}
                    onChange={(e) => setNewType(e.target.value as any)}
                    style={{
                      width: '100%',
                      padding: '0.45rem',
                      borderRadius: '6px',
                      border: '1px solid var(--border-color)',
                      backgroundColor: 'var(--bg-primary)',
                      color: 'var(--text-primary)',
                      fontSize: '0.85rem',
                    }}
                  >
                    {TYPE_OPTIONS.map((opt) => (
                      <option key={opt} value={opt}>
                        {opt}
                      </option>
                    ))}
                  </select>
                </div>

                <div>
                  <label htmlFor="tenant-currency-select" style={{ display: 'block', fontSize: '0.8rem', color: 'var(--text-secondary)', marginBottom: '0.25rem' }}>
                    Base Currency *
                  </label>
                  <select
                    id="tenant-currency-select"
                    value={newCurrency}
                    onChange={(e) => setNewCurrency(e.target.value)}
                    style={{
                      width: '100%',
                      padding: '0.45rem',
                      borderRadius: '6px',
                      border: '1px solid var(--border-color)',
                      backgroundColor: 'var(--bg-primary)',
                      color: 'var(--text-primary)',
                      fontSize: '0.85rem',
                    }}
                  >
                    {CURRENCY_OPTIONS.map((c) => (
                      <option key={c} value={c}>
                        {c}
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem' }}>
                <div>
                  <label htmlFor="tenant-fystart-input" style={{ display: 'block', fontSize: '0.8rem', color: 'var(--text-secondary)', marginBottom: '0.25rem' }}>
                    Fiscal Year Start Month (1-12)
                  </label>
                  <input
                    id="tenant-fystart-input"
                    type="number"
                    min={1}
                    max={12}
                    value={newFyStart}
                    onChange={(e) => setNewFyStart(Number(e.target.value))}
                    style={{
                      width: '100%',
                      padding: '0.45rem',
                      borderRadius: '6px',
                      border: '1px solid var(--border-color)',
                      backgroundColor: 'var(--bg-primary)',
                      color: 'var(--text-primary)',
                      fontSize: '0.85rem',
                    }}
                  />
                </div>

                <div>
                  <label htmlFor="tenant-timezone-input" style={{ display: 'block', fontSize: '0.8rem', color: 'var(--text-secondary)', marginBottom: '0.25rem' }}>
                    IANA Time Zone
                  </label>
                  <input
                    id="tenant-timezone-input"
                    type="text"
                    value={newTimezone}
                    onChange={(e) => setNewTimezone(e.target.value)}
                    placeholder="UTC"
                    style={{
                      width: '100%',
                      padding: '0.45rem',
                      borderRadius: '6px',
                      border: '1px solid var(--border-color)',
                      backgroundColor: 'var(--bg-primary)',
                      color: 'var(--text-primary)',
                      fontSize: '0.85rem',
                    }}
                  />
                </div>
              </div>

              <div>
                <label htmlFor="tenant-retention-select" style={{ display: 'block', fontSize: '0.8rem', color: 'var(--text-secondary)', marginBottom: '0.25rem' }}>
                  Retention Profile
                </label>
                <select
                  id="tenant-retention-select"
                  value={newRetention}
                  onChange={(e) => setNewRetention(e.target.value)}
                  style={{
                    width: '100%',
                    padding: '0.45rem',
                    borderRadius: '6px',
                    border: '1px solid var(--border-color)',
                    backgroundColor: 'var(--bg-primary)',
                    color: 'var(--text-primary)',
                    fontSize: '0.85rem',
                  }}
                >
                  <option value="STANDARD">STANDARD (1 Year Aggregate)</option>
                  <option value="COMPLIANCE">COMPLIANCE (3 Year Audit)</option>
                  <option value="EXTENDED">EXTENDED (7 Year Regulatory)</option>
                </select>
              </div>

              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.5rem', marginTop: '0.5rem' }}>
                <button
                  type="button"
                  onClick={() => setIsCreateOpen(false)}
                  style={{
                    padding: '0.5rem 0.9rem',
                    backgroundColor: 'transparent',
                    border: '1px solid var(--border-color)',
                    borderRadius: '6px',
                    color: 'var(--text-secondary)',
                    fontSize: '0.85rem',
                    cursor: 'pointer',
                  }}
                >
                  Cancel
                </button>
                <button
                  id="create-tenant-submit-btn"
                  type="submit"
                  disabled={isSubmitting}
                  style={{
                    padding: '0.5rem 1rem',
                    backgroundColor: '#0284c7',
                    border: 'none',
                    borderRadius: '6px',
                    color: '#ffffff',
                    fontSize: '0.85rem',
                    fontWeight: 600,
                    cursor: 'pointer',
                  }}
                >
                  {isSubmitting ? 'Creating...' : 'Create Tenant Organization'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Suspend / Resume Reason Modal */}
      {actionTenant && actionType && (
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="action-tenant-title"
          style={{
            position: 'fixed',
            inset: 0,
            backgroundColor: 'rgba(0, 0, 0, 0.7)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 1000,
            padding: '1rem',
          }}
        >
          <div
            style={{
              backgroundColor: 'var(--bg-secondary)',
              border: '1px solid var(--border-color)',
              borderRadius: '8px',
              padding: '1.5rem',
              width: '100%',
              maxWidth: '460px',
            }}
          >
            <h2 id="action-tenant-title" style={{ fontSize: '1.15rem', fontWeight: 600, margin: '0 0 0.5rem 0', color: 'var(--text-primary)' }}>
              {actionType === 'SUSPEND' ? 'Suspend Tenant Organization' : 'Resume Tenant Organization'}
            </h2>
            <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', marginBottom: '1rem' }}>
              Target: <strong>{actionTenant.name}</strong> ({actionTenant.code})
            </p>

            {actionError && (
              <div role="alert" style={{ padding: '0.5rem 0.75rem', backgroundColor: 'rgba(239, 68, 68, 0.15)', border: '1px solid #ef4444', borderRadius: '6px', color: '#fca5a5', fontSize: '0.8rem', marginBottom: '0.75rem' }}>
                {actionError}
              </div>
            )}

            <form onSubmit={handleActionSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
              <div>
                <label htmlFor="action-reason-input" style={{ display: 'block', fontSize: '0.8rem', color: 'var(--text-secondary)', marginBottom: '0.25rem' }}>
                  Mandatory Audited Reason *
                </label>
                <textarea
                  id="action-reason-input"
                  required
                  rows={3}
                  value={actionReason}
                  onChange={(e) => setActionReason(e.target.value)}
                  placeholder="Enter reason for this governance state change..."
                  style={{
                    width: '100%',
                    padding: '0.45rem',
                    borderRadius: '6px',
                    border: '1px solid var(--border-color)',
                    backgroundColor: 'var(--bg-primary)',
                    color: 'var(--text-primary)',
                    fontSize: '0.85rem',
                  }}
                />
              </div>

              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.5rem', marginTop: '0.5rem' }}>
                <button
                  type="button"
                  onClick={() => setActionTenant(null)}
                  style={{
                    padding: '0.45rem 0.85rem',
                    backgroundColor: 'transparent',
                    border: '1px solid var(--border-color)',
                    borderRadius: '6px',
                    color: 'var(--text-secondary)',
                    fontSize: '0.85rem',
                    cursor: 'pointer',
                  }}
                >
                  Cancel
                </button>
                <button
                  id="action-submit-btn"
                  type="submit"
                  disabled={isSubmitting}
                  style={{
                    padding: '0.45rem 0.95rem',
                    backgroundColor: actionType === 'SUSPEND' ? '#dc2626' : '#059669',
                    border: 'none',
                    borderRadius: '6px',
                    color: '#ffffff',
                    fontSize: '0.85rem',
                    fontWeight: 600,
                    cursor: 'pointer',
                  }}
                >
                  {isSubmitting ? 'Updating...' : `Confirm ${actionType}`}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* User Grants Drawer / Modal */}
      {grantsTenant && (
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="grants-modal-title"
          style={{
            position: 'fixed',
            inset: 0,
            backgroundColor: 'rgba(0, 0, 0, 0.7)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 1000,
            padding: '1rem',
          }}
        >
          <div
            style={{
              backgroundColor: 'var(--bg-secondary)',
              border: '1px solid var(--border-color)',
              borderRadius: '8px',
              padding: '1.5rem',
              width: '100%',
              maxWidth: '640px',
              maxHeight: '85vh',
              overflowY: 'auto',
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
              <div>
                <h2 id="grants-modal-title" style={{ fontSize: '1.2rem', fontWeight: 600, margin: 0, color: 'var(--text-primary)' }}>
                  User Scope Grants
                </h2>
                <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
                  Tenant: {grantsTenant.name} ({grantsTenant.code})
                </div>
              </div>
              <button
                onClick={() => setGrantsTenant(null)}
                style={{ background: 'none', border: 'none', color: 'var(--text-secondary)', cursor: 'pointer' }}
                aria-label="Close grants dialog"
              >
                <X size={18} />
              </button>
            </div>

            {/* Existing Grants List */}
            <div style={{ marginBottom: '1.5rem' }}>
              <h3 style={{ fontSize: '0.9rem', fontWeight: 600, color: 'var(--text-secondary)', marginBottom: '0.5rem' }}>
                Active Grants
              </h3>
              {loadingGrants ? (
                <div style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>Loading grants...</div>
              ) : grantsList.length === 0 ? (
                <div style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', padding: '0.5rem', backgroundColor: 'var(--bg-primary)', borderRadius: '6px' }}>
                  No explicit scope grants configured for this tenant.
                </div>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                  {grantsList.map((g) => (
                    <div
                      key={g.id}
                      style={{
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'center',
                        padding: '0.5rem 0.75rem',
                        backgroundColor: 'var(--bg-primary)',
                        border: '1px solid var(--border-color)',
                        borderRadius: '6px',
                        fontSize: '0.85rem',
                      }}
                    >
                      <div>
                        <strong>{g.grantee_id}</strong> ({g.grantee_type}) &mdash;{' '}
                        <span style={{ color: '#38bdf8' }}>{g.effect}</span>
                        {g.description && <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>{g.description}</div>}
                      </div>
                      <button
                        onClick={() => handleRevokeGrant(g.id)}
                        style={{
                          padding: '0.2rem 0.5rem',
                          backgroundColor: 'rgba(239, 68, 68, 0.1)',
                          color: '#f87171',
                          border: '1px solid rgba(239, 68, 68, 0.3)',
                          borderRadius: '4px',
                          fontSize: '0.75rem',
                          cursor: 'pointer',
                        }}
                      >
                        Revoke
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Add Grant Form */}
            <form onSubmit={handleAddGrant} style={{ borderTop: '1px solid var(--border-color)', paddingTop: '1rem' }}>
              <h3 style={{ fontSize: '0.9rem', fontWeight: 600, color: 'var(--text-secondary)', marginBottom: '0.75rem' }}>
                Grant Scope to User
              </h3>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem', marginBottom: '0.75rem' }}>
                <div>
                  <label htmlFor="grant-user-id" style={{ display: 'block', fontSize: '0.8rem', color: 'var(--text-secondary)', marginBottom: '0.25rem' }}>
                    User ID or Email *
                  </label>
                  <input
                    id="grant-user-id"
                    type="text"
                    required
                    value={grantGranteeId}
                    onChange={(e) => setGrantGranteeId(e.target.value)}
                    placeholder="e.g. user@enterprise.com"
                    style={{
                      width: '100%',
                      padding: '0.4rem',
                      borderRadius: '6px',
                      border: '1px solid var(--border-color)',
                      backgroundColor: 'var(--bg-primary)',
                      color: 'var(--text-primary)',
                      fontSize: '0.85rem',
                    }}
                  />
                </div>
                <div>
                  <label htmlFor="grant-desc" style={{ display: 'block', fontSize: '0.8rem', color: 'var(--text-secondary)', marginBottom: '0.25rem' }}>
                    Grant Description
                  </label>
                  <input
                    id="grant-desc"
                    type="text"
                    value={grantDescription}
                    onChange={(e) => setGrantDescription(e.target.value)}
                    placeholder="e.g. Tenant analyst access"
                    style={{
                      width: '100%',
                      padding: '0.4rem',
                      borderRadius: '6px',
                      border: '1px solid var(--border-color)',
                      backgroundColor: 'var(--bg-primary)',
                      color: 'var(--text-primary)',
                      fontSize: '0.85rem',
                    }}
                  />
                </div>
              </div>
              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.5rem' }}>
                <button
                  type="submit"
                  style={{
                    padding: '0.45rem 0.95rem',
                    backgroundColor: '#0284c7',
                    border: 'none',
                    borderRadius: '6px',
                    color: '#ffffff',
                    fontSize: '0.85rem',
                    fontWeight: 600,
                    cursor: 'pointer',
                  }}
                >
                  Add Scope Grant
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};

export default TenantsPage;
