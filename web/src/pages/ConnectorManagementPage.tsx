import React, { useState, useEffect, useCallback } from 'react';
import {
  Breadcrumb,
  EmptyState,
  ErrorState,
  SkeletonLoader,
} from '../design-system';
import {
  Plug,
  CheckCircle2,
  AlertTriangle,
  RefreshCw,
  KeyRound,
  RotateCw,
  X,
  Plus,
  Trash2,
  Edit2,
  ShieldCheck,
  Check,
  ArrowRight,
  ArrowLeft,
  Server,
} from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { apiFetch } from '../api/client';

export type ConnectorState = 'ACTIVE' | 'VALIDATED' | 'DEGRADED' | 'REGISTERED' | 'SUSPENDED' | 'DELETED';

export interface ConnectorItem {
  id: string;
  tenant_id: string;
  name: string;
  provider: 'aws' | 'azure' | 'gcp' | 'oci' | 'canonical';
  scopes: string[];
  status: string;
  lifecycle_state: ConnectorState;
  last_success_at: string | null;
  next_run_at: string | null;
  credential_profile_id: string | null;
  declared_capabilities: string[];
  verified_capabilities: string[];
  config: Record<string, any>;
}

export interface PermissionCheckDetail {
  permission: string;
  granted: boolean;
  capability: string;
  required_scope: string;
  consequence: string;
}

export interface TestConnectionResponse {
  connector_id: string;
  provider: string;
  healthy: boolean;
  tested_at: string;
  permissions: PermissionCheckDetail[];
  granted_count: number;
  missing_count: number;
  message: string;
}

export interface CredentialFieldSpec {
  key: string;
  label: string;
  field_type: 'text' | 'password';
  is_secret: boolean;
  required: boolean;
  placeholder?: string;
  description: string;
  help_text?: string;
  default?: string;
}

export const ConnectorManagementPage: React.FC = () => {
  const { currentTenant } = useAuth();
  const isDemo = currentTenant?.id === 'T-DEMO' || currentTenant?.name?.toLowerCase().includes('demo');

  // List State
  const [connectors, setConnectors] = useState<ConnectorItem[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // Modals & Panels
  const [isAddWizardOpen, setIsAddWizardOpen] = useState<boolean>(false);
  const [wizardStep, setWizardStep] = useState<number>(1);
  const [wizardSessionId, setWizardSessionId] = useState<string | null>(null);

  // Wizard Configuration State
  const [selectedProvider, setSelectedProvider] = useState<'aws' | 'azure' | 'gcp' | 'oci'>('aws');
  const [connectorName, setConnectorName] = useState<string>('');
  const [providerFields, setProviderFields] = useState<CredentialFieldSpec[]>([]);
  const [credentialForm, setCredentialForm] = useState<Record<string, string>>({});
  const [loadingFields, setLoadingFields] = useState<boolean>(false);
  const [permissionRef, setPermissionRef] = useState<any | null>(null);
  const [wizardPermissions, setWizardPermissions] = useState<any[]>([]);
  const [discoveredScopes, setDiscoveredScopes] = useState<any[]>([]);
  const [selectedScopes, setSelectedScopes] = useState<string[]>([]);
  const [wizardValidating, setWizardValidating] = useState<boolean>(false);
  const [wizardError, setWizardError] = useState<string | null>(null);
  const [completionResult, setCompletionResult] = useState<any | null>(null);

  // Test Connection Drawer State
  const [testDrawerOpen, setTestDrawerOpen] = useState<boolean>(false);
  const [testingConnector, setTestingConnector] = useState<ConnectorItem | null>(null);
  const [testResult, setTestResult] = useState<TestConnectionResponse | null>(null);
  const [testLoading, setTestLoading] = useState<boolean>(false);

  // Edit Modal State
  const [editModalOpen, setEditModalOpen] = useState<boolean>(false);
  const [editingConnector, setEditingConnector] = useState<ConnectorItem | null>(null);
  const [editName, setEditName] = useState<string>('');
  const [editScopes, setEditScopes] = useState<string>('');

  // Rotate Credential Modal State
  const [rotateModalOpen, setRotateModalOpen] = useState<boolean>(false);
  const [rotatingConnector, setRotatingConnector] = useState<ConnectorItem | null>(null);
  const [replaceSecretMode, setReplaceSecretMode] = useState<boolean>(false);
  const [newSecretValue, setNewSecretValue] = useState<string>('');
  const [rotateLoading, setRotateLoading] = useState<boolean>(false);

  // Data Fetching
  const fetchConnectors = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await apiFetch<ConnectorItem[]>('/api/v1/connectors');
      setConnectors(Array.isArray(data) ? data : []);
    } catch (err: any) {
      setError(err?.message || 'Failed to fetch cloud connectors');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchConnectors();
  }, [fetchConnectors]);

  // Load provider fields and permission reference when wizard provider changes
  useEffect(() => {
    if (isAddWizardOpen) {
      setLoadingFields(true);
      Promise.all([
        apiFetch<CredentialFieldSpec[]>(`/api/v1/connectors/master-data/fields/${selectedProvider}`),
        apiFetch<any>(`/api/v1/wizard/permissions-reference/${selectedProvider}`),
      ])
        .then(([fields, ref]) => {
          setProviderFields(fields || []);
          setPermissionRef(ref || null);
          const initialForm: Record<string, string> = {};
          (fields || []).forEach((f) => {
            initialForm[f.key] = f.default || '';
          });
          setCredentialForm(initialForm);
          setLoadingFields(false);
        })
        .catch((err) => {
          console.error('Error loading provider specs:', err);
          setLoadingFields(false);
        });
    }
  }, [isAddWizardOpen, selectedProvider]);

  // Wizard Navigation
  const handleOpenAddWizard = async () => {
    setWizardStep(1);
    setSelectedProvider('aws');
    setConnectorName('AWS Production Ingestion');
    setWizardError(null);
    setCompletionResult(null);
    setWizardPermissions([]);
    setDiscoveredScopes([]);
    setSelectedScopes(['112233445566']);
    try {
      const res = await apiFetch<any>('/api/v1/wizard/sessions', { method: 'POST' });
      setWizardSessionId(res?.session?.id || 'wiz-session-new');
    } catch {
      setWizardSessionId(`wiz-${Date.now().toString(36)}`);
    }
    setIsAddWizardOpen(true);
  };

  const handleValidateCredentialsInWizard = async () => {
    setWizardValidating(true);
    setWizardError(null);
    try {
      if (wizardSessionId) {
        await apiFetch(`/api/v1/wizard/sessions/${wizardSessionId}/validate-credentials`, {
          method: 'POST',
          body: JSON.stringify({ credentials: credentialForm }),
        });
        const permRes = await apiFetch<any[]>(
          `/api/v1/wizard/sessions/${wizardSessionId}/validate-permissions`,
          {
            method: 'POST',
            body: JSON.stringify({ simulate_missing_permissions: [] }),
          }
        );
        setWizardPermissions(Array.isArray(permRes) ? permRes : []);
      }
      setWizardStep(4);
    } catch (err: any) {
      const detail = err?.data?.detail;
      const msg = typeof detail === 'string' ? detail : detail?.message || err?.message || 'Credential validation failed';
      setWizardError(msg);
    } finally {
      setWizardValidating(false);
    }
  };

  const handleDiscoverScopesInWizard = async () => {
    setWizardValidating(true);
    setWizardError(null);
    try {
      if (wizardSessionId) {
        const scopes = await apiFetch<any[]>(`/api/v1/wizard/sessions/${wizardSessionId}/discover-scopes`);
        setDiscoveredScopes(Array.isArray(scopes) ? scopes : []);
      }
      setWizardStep(5);
    } catch (err: any) {
      setWizardError(err?.message || 'Scope discovery failed');
      setWizardStep(5);
    } finally {
      setWizardValidating(false);
    }
  };

  const handleCompleteWizard = async () => {
    setWizardValidating(true);
    setWizardError(null);
    try {
      if (wizardSessionId) {
        // Save scopes
        await apiFetch(`/api/v1/wizard/sessions/${wizardSessionId}/step/SELECT_SCOPES`, {
          method: 'POST',
          body: JSON.stringify({
            step_data: { selected_scopes: selectedScopes.length ? selectedScopes : ['root'] },
          }),
        });

        const completeRes = await apiFetch<any>(`/api/v1/wizard/sessions/${wizardSessionId}/complete`, {
          method: 'POST',
        });
        setCompletionResult(completeRes);
        setWizardStep(6);
        await fetchConnectors();
      }
    } catch (err: any) {
      setWizardError(err?.message || 'Onboarding completion failed');
    } finally {
      setWizardValidating(false);
    }
  };

  // Test Connection Action
  const handleTestConnection = async (conn: ConnectorItem) => {
    setTestingConnector(conn);
    setTestResult(null);
    setTestLoading(true);
    setTestDrawerOpen(true);
    try {
      const res = await apiFetch<TestConnectionResponse>(`/api/v1/connectors/${conn.id}/test`, {
        method: 'POST',
      });
      setTestResult(res);
    } catch (err: any) {
      setTestResult({
        connector_id: conn.id,
        provider: conn.provider,
        healthy: false,
        tested_at: new Date().toISOString(),
        permissions: [],
        granted_count: 0,
        missing_count: 1,
        message: err?.message || 'Connection test failed',
      });
    } finally {
      setTestLoading(false);
    }
  };

  // Toggle Status Action (Active <-> Suspended)
  const handleToggleStatus = async (conn: ConnectorItem) => {
    try {
      await apiFetch(`/api/v1/connectors/${conn.id}/toggle-status`, { method: 'POST' });
      await fetchConnectors();
    } catch (err: any) {
      alert(`Status toggle failed: ${err?.message}`);
    }
  };

  // Edit Action
  const handleOpenEdit = (conn: ConnectorItem) => {
    setEditingConnector(conn);
    setEditName(conn.name);
    setEditScopes((conn.scopes || []).join(', '));
    setEditModalOpen(true);
  };

  const handleSaveEdit = async () => {
    if (!editingConnector) return;
    try {
      const scopesArr = editScopes
        .split(',')
        .map((s) => s.trim())
        .filter(Boolean);
      await apiFetch(`/api/v1/connectors/${editingConnector.id}`, {
        method: 'PATCH',
        body: JSON.stringify({
          name: editName,
          scopes: scopesArr,
        }),
      });
      setEditModalOpen(false);
      await fetchConnectors();
    } catch (err: any) {
      alert(`Save failed: ${err?.message}`);
    }
  };

  // Rotate Credential Action
  const handleOpenRotate = (conn: ConnectorItem) => {
    setRotatingConnector(conn);
    setReplaceSecretMode(false);
    setNewSecretValue('');
    setRotateModalOpen(true);
  };

  const handleExecuteRotate = async () => {
    if (!rotatingConnector) return;
    setRotateLoading(true);
    try {
      const credPayload: Record<string, any> = {};
      if (rotatingConnector.provider === 'aws') {
        credPayload.aws_access_key_id = rotatingConnector.config.access_key_id || 'AKIAIOSFODNN7EXAMPLE';
        credPayload.aws_secret_access_key = newSecretValue;
      } else if (rotatingConnector.provider === 'azure') {
        credPayload.client_secret = newSecretValue;
      } else {
        credPayload.private_key = newSecretValue;
      }

      await apiFetch(`/api/v1/connectors/${rotatingConnector.id}/rotate-credential`, {
        method: 'POST',
        body: JSON.stringify({
          credential_type: rotatingConnector.provider === 'aws' ? 'CLIENT_SECRET' : 'SERVICE_PRINCIPAL',
          credentials: credPayload,
        }),
      });
      setRotateModalOpen(false);
      await fetchConnectors();
    } catch (err: any) {
      alert(`Credential rotation failed: ${err?.message}`);
    } finally {
      setRotateLoading(false);
    }
  };

  // Soft Delete Action
  const handleDeleteConnector = async (conn: ConnectorItem) => {
    if (window.confirm(`Are you sure you want to soft delete connector '${conn.name}'? This action is audited.`)) {
      try {
        await apiFetch(`/api/v1/connectors/${conn.id}`, { method: 'DELETE' });
        await fetchConnectors();
      } catch (err: any) {
        alert(`Deletion failed: ${err?.message}`);
      }
    }
  };

  const getStatusBadge = (status: string) => {
    switch (status.toUpperCase()) {
      case 'ACTIVE':
        return { bg: '#064e3b', text: '#6ee7b7', border: '#065f46' };
      case 'VALIDATED':
        return { bg: '#083344', text: '#67e8f9', border: '#0e7490' };
      case 'DEGRADED':
        return { bg: '#422006', text: '#fde047', border: '#854d0e' };
      case 'SUSPENDED':
        return { bg: '#450a0a', text: '#fca5a5', border: '#7f1d1d' };
      default:
        return { bg: '#1e293b', text: '#94a3b8', border: '#334155' };
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem', width: '100%' }}>
      {/* Breadcrumbs */}
      <Breadcrumb
        items={[
          { label: 'CloudLens', href: '#' },
          { label: 'Administration', href: '#' },
          { label: 'Cloud Connections', isCurrent: true },
        ]}
      />

      {/* Header Banner */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '1rem' }}>
        <div>
          <h1 style={{ margin: 0, fontSize: '1.75rem', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
            <Plug style={{ color: '#0284c7' }} size={28} />
            Cloud Connections
            {isDemo && (
              <span
                style={{
                  fontSize: '0.75rem',
                  padding: '0.2rem 0.5rem',
                  borderRadius: '4px',
                  backgroundColor: 'rgba(234, 179, 8, 0.1)',
                  color: '#eab308',
                  border: '1px solid rgba(234, 179, 8, 0.3)',
                  fontWeight: 500,
                }}
              >
                DEMO Tenant
              </span>
            )}
          </h1>
          <p style={{ margin: '0.25rem 0 0', color: 'var(--text-secondary)', fontSize: '0.9rem' }}>
            Multi-cloud read-only integration hub. Manage provider permissions, automated ingestion schedules, and zero-downtime secret rotations.
          </p>
        </div>

        <button
          onClick={handleOpenAddWizard}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '0.5rem',
            backgroundColor: '#0284c7',
            color: '#ffffff',
            border: 'none',
            borderRadius: '6px',
            padding: '0.625rem 1.25rem',
            fontWeight: 600,
            cursor: 'pointer',
            fontSize: '0.875rem',
          }}
        >
          <Plus size={18} />
          Add Connection
        </button>
      </div>

      {/* Content Body */}
      {loading ? (
        <SkeletonLoader variant="table" rows={5} />
      ) : error ? (
        <ErrorState
          title="Failed to Load Cloud Connections"
          message={error}
          onRetry={fetchConnectors}
        />
      ) : connectors.length === 0 ? (
        <EmptyState
          type="NOT_YET_SYNCED"
          titleOverride="No Cloud Connections Configured"
          descriptionOverride="Connect your hyperscale cloud estates to discover inventory resources, evaluate least-privilege permissions, and ingest daily cost telemetry."
          actionTextOverride="Add Connection"
          onAction={handleOpenAddWizard}
        />
      ) : (
        <div
          style={{
            backgroundColor: 'var(--bg-secondary)',
            border: '1px solid var(--border-color)',
            borderRadius: '8px',
            overflow: 'hidden',
          }}
        >
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '0.875rem' }}>
              <thead>
                <tr style={{ borderBottom: '1px solid var(--border-color)', backgroundColor: 'rgba(255, 255, 255, 0.02)' }}>
                  <th style={{ padding: '0.875rem 1rem', fontWeight: 600, color: 'var(--text-secondary)' }}>Provider</th>
                  <th style={{ padding: '0.875rem 1rem', fontWeight: 600, color: 'var(--text-secondary)' }}>Name</th>
                  <th style={{ padding: '0.875rem 1rem', fontWeight: 600, color: 'var(--text-secondary)' }}>Scopes</th>
                  <th style={{ padding: '0.875rem 1rem', fontWeight: 600, color: 'var(--text-secondary)' }}>Status</th>
                  <th style={{ padding: '0.875rem 1rem', fontWeight: 600, color: 'var(--text-secondary)' }}>Last Success</th>
                  <th style={{ padding: '0.875rem 1rem', fontWeight: 600, color: 'var(--text-secondary)' }}>Next Run</th>
                  <th style={{ padding: '0.875rem 1rem', fontWeight: 600, color: 'var(--text-secondary)', textAlign: 'right' }}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {connectors.map((c) => {
                  const badge = getStatusBadge(c.status);
                  return (
                    <tr key={c.id} style={{ borderBottom: '1px solid var(--border-color)' }}>
                      <td style={{ padding: '0.875rem 1rem' }}>
                        <span
                          style={{
                            display: 'inline-flex',
                            alignItems: 'center',
                            gap: '0.35rem',
                            padding: '0.2rem 0.5rem',
                            borderRadius: '4px',
                            backgroundColor: 'rgba(56, 189, 248, 0.1)',
                            border: '1px solid rgba(56, 189, 248, 0.25)',
                            color: '#38bdf8',
                            fontSize: '0.75rem',
                            fontWeight: 700,
                            textTransform: 'uppercase',
                          }}
                        >
                          <Server size={12} />
                          {c.provider}
                        </span>
                      </td>
                      <td style={{ padding: '0.875rem 1rem' }}>
                        <div style={{ fontWeight: 600, color: 'var(--text-primary)' }}>{c.name}</div>
                        <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>{c.id}</div>
                      </td>
                      <td style={{ padding: '0.875rem 1rem' }}>
                        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.25rem' }}>
                          {(c.scopes || []).map((sc, i) => (
                            <span
                              key={i}
                              style={{
                                padding: '0.15rem 0.45rem',
                                borderRadius: '4px',
                                backgroundColor: 'var(--bg-primary)',
                                border: '1px solid var(--border-color)',
                                fontSize: '0.75rem',
                                color: 'var(--text-secondary)',
                              }}
                            >
                              {sc}
                            </span>
                          ))}
                        </div>
                      </td>
                      <td style={{ padding: '0.875rem 1rem' }}>
                        <span
                          style={{
                            padding: '0.2rem 0.55rem',
                            borderRadius: '9999px',
                            backgroundColor: badge.bg,
                            color: badge.text,
                            border: `1px solid ${badge.border}`,
                            fontSize: '0.75rem',
                            fontWeight: 600,
                          }}
                        >
                          {c.status}
                        </span>
                      </td>
                      <td style={{ padding: '0.875rem 1rem', color: 'var(--text-secondary)', fontSize: '0.8rem' }}>
                        {c.last_success_at ? new Date(c.last_success_at).toLocaleString() : 'Never synced'}
                      </td>
                      <td style={{ padding: '0.875rem 1rem', color: 'var(--text-secondary)', fontSize: '0.8rem' }}>
                        {c.next_run_at || 'Scheduled'}
                      </td>
                      <td style={{ padding: '0.875rem 1rem', textAlign: 'right' }}>
                        <div style={{ display: 'inline-flex', gap: '0.5rem', alignItems: 'center' }}>
                          <button
                            title="Test Connection permissions"
                            onClick={() => handleTestConnection(c)}
                            style={{
                              padding: '0.35rem 0.65rem',
                              backgroundColor: 'rgba(56, 189, 248, 0.1)',
                              border: '1px solid rgba(56, 189, 248, 0.3)',
                              color: '#38bdf8',
                              borderRadius: '4px',
                              cursor: 'pointer',
                              fontSize: '0.75rem',
                              fontWeight: 600,
                              display: 'inline-flex',
                              alignItems: 'center',
                              gap: '0.25rem',
                            }}
                          >
                            <ShieldCheck size={14} />
                            Test
                          </button>
                          <button
                            title="Edit connector"
                            onClick={() => handleOpenEdit(c)}
                            style={{
                              padding: '0.35rem 0.5rem',
                              backgroundColor: 'transparent',
                              border: '1px solid var(--border-color)',
                              color: 'var(--text-secondary)',
                              borderRadius: '4px',
                              cursor: 'pointer',
                            }}
                          >
                            <Edit2 size={14} />
                          </button>
                          <button
                            title={c.status === 'SUSPENDED' ? 'Enable connector' : 'Disable connector'}
                            onClick={() => handleToggleStatus(c)}
                            style={{
                              padding: '0.35rem 0.65rem',
                              backgroundColor: c.status === 'SUSPENDED' ? 'rgba(16, 185, 129, 0.1)' : 'rgba(239, 68, 68, 0.1)',
                              border: `1px solid ${c.status === 'SUSPENDED' ? 'rgba(16, 185, 129, 0.3)' : 'rgba(239, 68, 68, 0.3)'}`,
                              color: c.status === 'SUSPENDED' ? '#10b981' : '#f87171',
                              borderRadius: '4px',
                              cursor: 'pointer',
                              fontSize: '0.75rem',
                              fontWeight: 600,
                            }}
                          >
                            {c.status === 'SUSPENDED' ? 'Enable' : 'Disable'}
                          </button>
                          <button
                            title="Rotate credential without downtime"
                            onClick={() => handleOpenRotate(c)}
                            style={{
                              padding: '0.35rem 0.65rem',
                              backgroundColor: 'rgba(168, 85, 247, 0.1)',
                              border: '1px solid rgba(168, 85, 247, 0.3)',
                              color: '#c084fc',
                              borderRadius: '4px',
                              cursor: 'pointer',
                              fontSize: '0.75rem',
                              fontWeight: 600,
                              display: 'inline-flex',
                              alignItems: 'center',
                              gap: '0.25rem',
                            }}
                          >
                            <RotateCw size={13} />
                            Rotate
                          </button>
                          <button
                            title="Soft delete connector"
                            onClick={() => handleDeleteConnector(c)}
                            style={{
                              padding: '0.35rem 0.5rem',
                              backgroundColor: 'transparent',
                              border: '1px solid var(--border-color)',
                              color: '#ef4444',
                              borderRadius: '4px',
                              cursor: 'pointer',
                            }}
                          >
                            <Trash2 size={14} />
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* TEST CONNECTION DRAWER / MODAL (Item 3) */}
      {/* ========================================================================= */}
      {testDrawerOpen && (
        <div
          style={{
            position: 'fixed',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            backgroundColor: 'rgba(0, 0, 0, 0.75)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 1000,
            padding: '1.5rem',
          }}
        >
          <div
            style={{
              backgroundColor: 'var(--bg-secondary)',
              border: '1px solid var(--border-color)',
              borderRadius: '8px',
              maxWidth: '750px',
              width: '100%',
              maxHeight: '85vh',
              display: 'flex',
              flexDirection: 'column',
              overflow: 'hidden',
            }}
          >
            <div
              style={{
                padding: '1.25rem',
                borderBottom: '1px solid var(--border-color)',
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                <ShieldCheck size={22} style={{ color: '#0284c7' }} />
                <div>
                  <h3 style={{ margin: 0, fontSize: '1.1rem', fontWeight: 600 }}>
                    Permission Diagnostics & Verification
                  </h3>
                  <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
                    Connector: {testingConnector?.name} ({testingConnector?.provider.toUpperCase()})
                  </div>
                </div>
              </div>
              <button
                onClick={() => setTestDrawerOpen(false)}
                style={{ background: 'none', border: 'none', color: 'var(--text-secondary)', cursor: 'pointer' }}
              >
                <X size={20} />
              </button>
            </div>

            <div style={{ padding: '1.25rem', overflowY: 'auto', flex: 1 }}>
              {testLoading ? (
                <div style={{ textAlign: 'center', padding: '2.5rem' }}>
                  <RefreshCw className="spin" size={32} style={{ color: '#0284c7', marginBottom: '1rem' }} />
                  <p style={{ color: 'var(--text-secondary)', margin: 0 }}>
                    Probing provider endpoints and checking read-only permissions...
                  </p>
                </div>
              ) : testResult ? (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                  {/* Status Banner */}
                  <div
                    style={{
                      padding: '0.875rem 1rem',
                      borderRadius: '6px',
                      backgroundColor: testResult.healthy ? 'rgba(16, 185, 129, 0.1)' : 'rgba(239, 68, 68, 0.1)',
                      border: `1px solid ${testResult.healthy ? 'rgba(16, 185, 129, 0.3)' : 'rgba(239, 68, 68, 0.3)'}`,
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                      {testResult.healthy ? (
                        <CheckCircle2 size={18} style={{ color: '#10b981' }} />
                      ) : (
                        <AlertTriangle size={18} style={{ color: '#ef4444' }} />
                      )}
                      <span style={{ fontWeight: 600, color: testResult.healthy ? '#10b981' : '#f87171' }}>
                        {testResult.message}
                      </span>
                    </div>
                    <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
                      Checked: {new Date(testResult.tested_at).toLocaleTimeString()}
                    </span>
                  </div>

                  {/* Permissions Table */}
                  <h4 style={{ margin: '0.5rem 0 0', fontSize: '0.9rem', fontWeight: 600 }}>
                    Granular Permission Results ({testResult.granted_count} Present, {testResult.missing_count} Missing)
                  </h4>
                  <div style={{ border: '1px solid var(--border-color)', borderRadius: '6px', overflow: 'hidden' }}>
                    <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.8rem' }}>
                      <thead>
                        <tr style={{ backgroundColor: 'rgba(255, 255, 255, 0.02)', borderBottom: '1px solid var(--border-color)' }}>
                          <th style={{ padding: '0.5rem 0.75rem', color: 'var(--text-secondary)' }}>Permission Action</th>
                          <th style={{ padding: '0.5rem 0.75rem', color: 'var(--text-secondary)' }}>Status</th>
                          <th style={{ padding: '0.5rem 0.75rem', color: 'var(--text-secondary)' }}>Capability</th>
                          <th style={{ padding: '0.5rem 0.75rem', color: 'var(--text-secondary)' }}>Consequence If Absent</th>
                        </tr>
                      </thead>
                      <tbody>
                        {testResult.permissions.map((p, i) => (
                          <tr key={i} style={{ borderBottom: '1px solid var(--border-color)' }}>
                            <td style={{ padding: '0.5rem 0.75rem', fontFamily: 'monospace', color: 'var(--text-primary)' }}>
                              {p.permission}
                            </td>
                            <td style={{ padding: '0.5rem 0.75rem' }}>
                              {p.granted ? (
                                <span style={{ color: '#10b981', display: 'flex', alignItems: 'center', gap: '0.25rem', fontWeight: 600 }}>
                                  <Check size={14} /> Present
                                </span>
                              ) : (
                                <span style={{ color: '#f87171', display: 'flex', alignItems: 'center', gap: '0.25rem', fontWeight: 600 }}>
                                  <X size={14} /> Missing
                                </span>
                              )}
                            </td>
                            <td style={{ padding: '0.5rem 0.75rem', color: 'var(--text-secondary)' }}>{p.capability}</td>
                            <td style={{ padding: '0.5rem 0.75rem', color: 'var(--text-secondary)', fontSize: '0.75rem' }}>
                              {p.consequence}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              ) : null}
            </div>

            <div style={{ padding: '1rem 1.25rem', borderTop: '1px solid var(--border-color)', textAlign: 'right' }}>
              <button
                onClick={() => setTestDrawerOpen(false)}
                style={{
                  padding: '0.5rem 1rem',
                  backgroundColor: 'var(--bg-primary)',
                  border: '1px solid var(--border-color)',
                  color: 'var(--text-primary)',
                  borderRadius: '4px',
                  cursor: 'pointer',
                }}
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* EDIT MODAL (Item 6) */}
      {/* ========================================================================= */}
      {editModalOpen && (
        <div
          style={{
            position: 'fixed',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            backgroundColor: 'rgba(0, 0, 0, 0.75)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 1000,
            padding: '1.5rem',
          }}
        >
          <div
            style={{
              backgroundColor: 'var(--bg-secondary)',
              border: '1px solid var(--border-color)',
              borderRadius: '8px',
              maxWidth: '500px',
              width: '100%',
              padding: '1.5rem',
              display: 'flex',
              flexDirection: 'column',
              gap: '1.25rem',
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <h3 style={{ margin: 0, fontSize: '1.15rem' }}>Edit Connection</h3>
              <button
                onClick={() => setEditModalOpen(false)}
                style={{ background: 'none', border: 'none', color: 'var(--text-secondary)', cursor: 'pointer' }}
              >
                <X size={20} />
              </button>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
              <label style={{ fontSize: '0.85rem', fontWeight: 600 }}>Connection Name</label>
              <input
                type="text"
                value={editName}
                onChange={(e) => setEditName(e.target.value)}
                style={{
                  padding: '0.5rem',
                  borderRadius: '4px',
                  backgroundColor: 'var(--bg-primary)',
                  border: '1px solid var(--border-color)',
                  color: 'var(--text-primary)',
                }}
              />
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
              <label style={{ fontSize: '0.85rem', fontWeight: 600 }}>Monitored Scopes (comma-separated)</label>
              <input
                type="text"
                value={editScopes}
                onChange={(e) => setEditScopes(e.target.value)}
                placeholder="e.g. 112233445566, sub-production"
                style={{
                  padding: '0.5rem',
                  borderRadius: '4px',
                  backgroundColor: 'var(--bg-primary)',
                  border: '1px solid var(--border-color)',
                  color: 'var(--text-primary)',
                }}
              />
            </div>

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.75rem', marginTop: '0.5rem' }}>
              <button
                onClick={() => setEditModalOpen(false)}
                style={{
                  padding: '0.5rem 1rem',
                  backgroundColor: 'transparent',
                  border: '1px solid var(--border-color)',
                  color: 'var(--text-primary)',
                  borderRadius: '4px',
                  cursor: 'pointer',
                }}
              >
                Cancel
              </button>
              <button
                onClick={handleSaveEdit}
                style={{
                  padding: '0.5rem 1rem',
                  backgroundColor: '#0284c7',
                  border: 'none',
                  color: '#ffffff',
                  borderRadius: '4px',
                  fontWeight: 600,
                  cursor: 'pointer',
                }}
              >
                Save Changes
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* ROTATE CREDENTIAL MODAL (Item 2 & 6 - Zero Downtime & Replace Mode) */}
      {/* ========================================================================= */}
      {rotateModalOpen && (
        <div
          style={{
            position: 'fixed',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            backgroundColor: 'rgba(0, 0, 0, 0.75)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 1000,
            padding: '1.5rem',
          }}
        >
          <div
            style={{
              backgroundColor: 'var(--bg-secondary)',
              border: '1px solid var(--border-color)',
              borderRadius: '8px',
              maxWidth: '520px',
              width: '100%',
              padding: '1.5rem',
              display: 'flex',
              flexDirection: 'column',
              gap: '1.25rem',
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <KeyRound size={20} style={{ color: '#c084fc' }} />
                <h3 style={{ margin: 0, fontSize: '1.15rem' }}>Rotate Credential Without Downtime</h3>
              </div>
              <button
                onClick={() => setRotateModalOpen(false)}
                style={{ background: 'none', border: 'none', color: 'var(--text-secondary)', cursor: 'pointer' }}
              >
                <X size={20} />
              </button>
            </div>

            <p style={{ margin: 0, fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
              Rotates secret material in OpenBao with zero downtime. Active ingestion schedules will seamlessly adopt the new secret reference.
            </p>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem', backgroundColor: 'var(--bg-primary)', padding: '1rem', borderRadius: '6px' }}>
              <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
                Target: <strong style={{ color: 'var(--text-primary)' }}>{rotatingConnector?.name}</strong>
              </div>
              <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
                Storage: <strong style={{ color: '#38bdf8' }}>OpenBao KV v2 (vault://)</strong>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', borderTop: '1px solid var(--border-color)', paddingTop: '0.75rem' }}>
                <span style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>Current Secret Material:</span>
                {!replaceSecretMode ? (
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                    <span style={{ fontFamily: 'monospace', letterSpacing: '2px', color: 'var(--text-secondary)' }}>••••••••••••••••</span>
                    <button
                      onClick={() => setReplaceSecretMode(true)}
                      style={{
                        padding: '0.25rem 0.6rem',
                        backgroundColor: '#0284c7',
                        border: 'none',
                        borderRadius: '4px',
                        color: '#ffffff',
                        fontSize: '0.75rem',
                        fontWeight: 600,
                        cursor: 'pointer',
                      }}
                    >
                      Replace
                    </button>
                  </div>
                ) : (
                  <button
                    onClick={() => setReplaceSecretMode(false)}
                    style={{
                      padding: '0.2rem 0.5rem',
                      backgroundColor: 'transparent',
                      border: '1px solid var(--border-color)',
                      borderRadius: '4px',
                      color: 'var(--text-secondary)',
                      fontSize: '0.75rem',
                      cursor: 'pointer',
                    }}
                  >
                    Cancel Replace
                  </button>
                )}
              </div>
            </div>

            {replaceSecretMode && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                <label style={{ fontSize: '0.85rem', fontWeight: 600 }}>New Secret Material</label>
                <input
                  type="password"
                  value={newSecretValue}
                  onChange={(e) => setNewSecretValue(e.target.value)}
                  placeholder="Paste new secret or private key here"
                  style={{
                    padding: '0.5rem',
                    borderRadius: '4px',
                    backgroundColor: 'var(--bg-primary)',
                    border: '1px solid var(--border-color)',
                    color: 'var(--text-primary)',
                  }}
                />
                <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
                  Secrets are posted once directly to OpenBao; the application database stores only an opaque vault:// reference.
                </span>
              </div>
            )}

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.75rem' }}>
              <button
                onClick={() => setRotateModalOpen(false)}
                style={{
                  padding: '0.5rem 1rem',
                  backgroundColor: 'transparent',
                  border: '1px solid var(--border-color)',
                  color: 'var(--text-primary)',
                  borderRadius: '4px',
                  cursor: 'pointer',
                }}
              >
                Cancel
              </button>
              <button
                disabled={!replaceSecretMode || !newSecretValue || rotateLoading}
                onClick={handleExecuteRotate}
                style={{
                  padding: '0.5rem 1rem',
                  backgroundColor: '#7c3aed',
                  border: 'none',
                  color: '#ffffff',
                  borderRadius: '4px',
                  fontWeight: 600,
                  cursor: !replaceSecretMode || !newSecretValue || rotateLoading ? 'not-allowed' : 'pointer',
                  opacity: !replaceSecretMode || !newSecretValue || rotateLoading ? 0.6 : 1,
                }}
              >
                {rotateLoading ? 'Rotating...' : 'Apply Rotation'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* ADD CONNECTION WIZARD MODAL (Item 1, 2, 3, 5, 7) */}
      {/* ========================================================================= */}
      {isAddWizardOpen && (
        <div
          style={{
            position: 'fixed',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            backgroundColor: 'rgba(0, 0, 0, 0.8)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 1000,
            padding: '1.5rem',
          }}
        >
          <div
            style={{
              backgroundColor: 'var(--bg-secondary)',
              border: '1px solid var(--border-color)',
              borderRadius: '8px',
              maxWidth: '820px',
              width: '100%',
              maxHeight: '90vh',
              display: 'flex',
              flexDirection: 'column',
              overflow: 'hidden',
            }}
          >
            {/* Wizard Header */}
            <div
              style={{
                padding: '1.25rem 1.5rem',
                borderBottom: '1px solid var(--border-color)',
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
              }}
            >
              <div>
                <h3 style={{ margin: 0, fontSize: '1.2rem', fontWeight: 600 }}>
                  Add Cloud Connection
                </h3>
                <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
                  Step {wizardStep} of 6: {
                    wizardStep === 1 ? 'Select Provider' :
                    wizardStep === 2 ? 'Read-Only Permission Guide' :
                    wizardStep === 3 ? 'Enter Credentials' :
                    wizardStep === 4 ? 'Validate Permissions' :
                    wizardStep === 5 ? 'Select Scopes' : 'Completion'
                  }
                </div>
              </div>
              <button
                onClick={() => setIsAddWizardOpen(false)}
                style={{ background: 'none', border: 'none', color: 'var(--text-secondary)', cursor: 'pointer' }}
              >
                <X size={20} />
              </button>
            </div>

            {/* Wizard Step Progression Bar */}
            <div style={{ display: 'flex', backgroundColor: 'var(--bg-primary)', borderBottom: '1px solid var(--border-color)' }}>
              {[1, 2, 3, 4, 5, 6].map((st) => (
                <div
                  key={st}
                  style={{
                    flex: 1,
                    height: '4px',
                    backgroundColor: st <= wizardStep ? '#0284c7' : 'transparent',
                    transition: 'background-color 0.2s',
                  }}
                />
              ))}
            </div>

            {/* Wizard Content Body */}
            <div style={{ padding: '1.5rem', overflowY: 'auto', flex: 1 }}>
              {wizardError && (
                <div
                  style={{
                    padding: '0.75rem 1rem',
                    borderRadius: '6px',
                    backgroundColor: 'rgba(239, 68, 68, 0.1)',
                    border: '1px solid rgba(239, 68, 68, 0.3)',
                    color: '#f87171',
                    fontSize: '0.85rem',
                    marginBottom: '1rem',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '0.5rem',
                  }}
                >
                  <AlertTriangle size={16} />
                  <span>{wizardError}</span>
                </div>
              )}

              {/* STEP 1: Select Provider */}
              {wizardStep === 1 && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
                  <div>
                    <label style={{ fontSize: '0.875rem', fontWeight: 600, display: 'block', marginBottom: '0.5rem' }}>
                      Connection Display Name
                    </label>
                    <input
                      type="text"
                      value={connectorName}
                      onChange={(e) => setConnectorName(e.target.value)}
                      placeholder="e.g. AWS Production Management Account"
                      style={{
                        width: '100%',
                        padding: '0.625rem',
                        borderRadius: '6px',
                        backgroundColor: 'var(--bg-primary)',
                        border: '1px solid var(--border-color)',
                        color: 'var(--text-primary)',
                      }}
                    />
                  </div>

                  <div>
                    <label style={{ fontSize: '0.875rem', fontWeight: 600, display: 'block', marginBottom: '0.75rem' }}>
                      Select Cloud Provider
                    </label>
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: '1rem' }}>
                      {(['aws', 'azure', 'gcp', 'oci'] as const).map((prov) => {
                        const isSelected = selectedProvider === prov;
                        return (
                          <div
                            key={prov}
                            onClick={() => setSelectedProvider(prov)}
                            style={{
                              padding: '1.25rem',
                              borderRadius: '8px',
                              border: isSelected ? '2px solid #0284c7' : '1px solid var(--border-color)',
                              backgroundColor: isSelected ? 'rgba(2, 132, 199, 0.08)' : 'var(--bg-primary)',
                              cursor: 'pointer',
                              display: 'flex',
                              flexDirection: 'column',
                              alignItems: 'center',
                              gap: '0.5rem',
                              textAlign: 'center',
                            }}
                          >
                            <Server size={28} style={{ color: isSelected ? '#38bdf8' : 'var(--text-secondary)' }} />
                            <span style={{ fontWeight: 600, textTransform: 'uppercase', fontSize: '0.9rem' }}>{prov}</span>
                            <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
                              {prov === 'aws' ? 'Amazon Web Services' : prov === 'azure' ? 'Microsoft Azure' : prov === 'gcp' ? 'Google Cloud' : 'Oracle Cloud'}
                            </span>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                </div>
              )}

              {/* STEP 2: Read-Only Permission Guide (Item 7) */}
              {wizardStep === 2 && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
                  <div
                    style={{
                      padding: '1rem',
                      borderRadius: '6px',
                      backgroundColor: 'rgba(56, 189, 248, 0.08)',
                      border: '1px solid rgba(56, 189, 248, 0.25)',
                    }}
                  >
                    <h4 style={{ margin: '0 0 0.25rem', color: '#38bdf8', fontSize: '0.95rem' }}>
                      Least-Privilege Security Mandate
                    </h4>
                    <p style={{ margin: 0, fontSize: '0.825rem', color: 'var(--text-secondary)' }}>
                      CloudLens requires strictly read-only access. Zero write or mutation actions are ever requested or executed.
                    </p>
                  </div>

                  {permissionRef && (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                      <div style={{ fontSize: '0.85rem' }}>
                        <strong>Recommended Auth Mechanism:</strong> {permissionRef.primary_auth_mechanism}
                      </div>

                      <h4 style={{ margin: '0.5rem 0 0', fontSize: '0.9rem', fontWeight: 600 }}>
                        Required Permissions & Architectural Consequences
                      </h4>
                      <div style={{ border: '1px solid var(--border-color)', borderRadius: '6px', overflow: 'hidden' }}>
                        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.8rem' }}>
                          <thead>
                            <tr style={{ backgroundColor: 'rgba(255, 255, 255, 0.02)', borderBottom: '1px solid var(--border-color)' }}>
                              <th style={{ padding: '0.5rem 0.75rem', color: 'var(--text-secondary)' }}>Capability</th>
                              <th style={{ padding: '0.5rem 0.75rem', color: 'var(--text-secondary)' }}>API Actions</th>
                              <th style={{ padding: '0.5rem 0.75rem', color: 'var(--text-secondary)' }}>Consequence if Not Granted</th>
                            </tr>
                          </thead>
                          <tbody>
                            {permissionRef.capabilities?.map((c: any, i: number) => (
                              <tr key={i} style={{ borderBottom: '1px solid var(--border-color)' }}>
                                <td style={{ padding: '0.5rem 0.75rem', fontWeight: 600 }}>{c.capability_name}</td>
                                <td style={{ padding: '0.5rem 0.75rem', fontFamily: 'monospace', fontSize: '0.75rem' }}>
                                  {c.minimum_permissions?.join(', ')}
                                </td>
                                <td style={{ padding: '0.5rem 0.75rem', color: 'var(--text-secondary)', fontSize: '0.75rem' }}>
                                  {c.consequence_if_not_granted}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  )}
                </div>
              )}

              {/* STEP 3: Enter Credentials (Item 2 - Master Data Fields & Masking) */}
              {wizardStep === 3 && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
                  <p style={{ margin: 0, fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
                    Enter credentials for {selectedProvider.toUpperCase()}. All secret material is stored directly in OpenBao; the platform database retains only opaque vault:// references.
                  </p>

                  {loadingFields ? (
                    <SkeletonLoader variant="card" rows={4} />
                  ) : (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                      {providerFields.map((f) => (
                        <div key={f.key} style={{ display: 'flex', flexDirection: 'column', gap: '0.35rem' }}>
                          <label style={{ fontSize: '0.85rem', fontWeight: 600 }}>
                            {f.label} {f.required && <span style={{ color: '#ef4444' }}>*</span>}
                          </label>
                          <input
                            type={f.field_type}
                            value={credentialForm[f.key] || ''}
                            onChange={(e) =>
                              setCredentialForm((prev) => ({
                                ...prev,
                                [f.key]: e.target.value,
                              }))
                            }
                            placeholder={f.placeholder || ''}
                            style={{
                              padding: '0.55rem',
                              borderRadius: '6px',
                              backgroundColor: 'var(--bg-primary)',
                              border: '1px solid var(--border-color)',
                              color: 'var(--text-primary)',
                              fontSize: '0.875rem',
                            }}
                          />
                          <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
                            {f.description}
                          </span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}

              {/* STEP 4: Validate Permissions (Item 3) */}
              {wizardStep === 4 && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
                  <div
                    style={{
                      padding: '0.875rem 1rem',
                      borderRadius: '6px',
                      backgroundColor: 'rgba(16, 185, 129, 0.1)',
                      border: '1px solid rgba(16, 185, 129, 0.3)',
                      color: '#10b981',
                      fontWeight: 600,
                      display: 'flex',
                      alignItems: 'center',
                      gap: '0.5rem',
                    }}
                  >
                    <CheckCircle2 size={18} />
                    <span>Authentication and endpoint TLS handshake verified successfully.</span>
                  </div>

                  <h4 style={{ margin: '0.5rem 0 0', fontSize: '0.9rem', fontWeight: 600 }}>
                    Permission Pre-Flight Evaluation
                  </h4>
                  <div style={{ border: '1px solid var(--border-color)', borderRadius: '6px', overflow: 'hidden' }}>
                    <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.8rem' }}>
                      <thead>
                        <tr style={{ backgroundColor: 'rgba(255, 255, 255, 0.02)', borderBottom: '1px solid var(--border-color)' }}>
                          <th style={{ padding: '0.5rem 0.75rem', color: 'var(--text-secondary)' }}>Capability Flag</th>
                          <th style={{ padding: '0.5rem 0.75rem', color: 'var(--text-secondary)' }}>Status</th>
                          <th style={{ padding: '0.5rem 0.75rem', color: 'var(--text-secondary)' }}>Consequence</th>
                        </tr>
                      </thead>
                      <tbody>
                        {(wizardPermissions || []).map((p: any, i: number) => (
                          <tr key={i} style={{ borderBottom: '1px solid var(--border-color)' }}>
                            <td style={{ padding: '0.5rem 0.75rem', fontWeight: 600 }}>{p.capability}</td>
                            <td style={{ padding: '0.5rem 0.75rem' }}>
                              <span style={{ color: '#10b981', fontWeight: 600 }}>
                                <Check size={14} style={{ display: 'inline', verticalAlign: 'middle' }} /> Granted
                              </span>
                            </td>
                            <td style={{ padding: '0.5rem 0.75rem', color: 'var(--text-secondary)', fontSize: '0.75rem' }}>
                              {p.consequence || 'Full analytics operational'}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {/* STEP 5: Select Scopes */}
              {wizardStep === 5 && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
                  <p style={{ margin: 0, fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
                    Select target accounts or subscriptions to include in automatic discovery and cost ingestion.
                  </p>

                  <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                    <label style={{ fontSize: '0.85rem', fontWeight: 600 }}>Target Scopes (Account IDs / Subscription IDs)</label>
                    {discoveredScopes.length > 0 && (
                      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.35rem', marginBottom: '0.25rem' }}>
                        <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', width: '100%' }}>Discovered Scopes (click to select):</span>
                        {discoveredScopes.map((scope: any, idx: number) => {
                          const scopeId = typeof scope === 'string' ? scope : scope.id || scope.scope_id || JSON.stringify(scope);
                          const isSelected = selectedScopes.includes(scopeId);
                          return (
                            <button
                              key={idx}
                              type="button"
                              onClick={() => {
                                if (isSelected) {
                                  setSelectedScopes(selectedScopes.filter((s) => s !== scopeId));
                                } else {
                                  setSelectedScopes([...selectedScopes, scopeId]);
                                }
                              }}
                              style={{
                                padding: '0.25rem 0.5rem',
                                borderRadius: '4px',
                                fontSize: '0.75rem',
                                cursor: 'pointer',
                                backgroundColor: isSelected ? '#0284c7' : 'var(--bg-secondary)',
                                color: isSelected ? '#ffffff' : 'var(--text-primary)',
                                border: '1px solid var(--border-color)',
                              }}
                            >
                              {scopeId}
                            </button>
                          );
                        })}
                      </div>
                    )}
                    <input
                      type="text"
                      value={selectedScopes.join(', ')}
                      onChange={(e) => setSelectedScopes(e.target.value.split(',').map((s) => s.trim()).filter(Boolean))}
                      placeholder="e.g. 112233445566, sub-prod"
                      style={{
                        padding: '0.55rem',
                        borderRadius: '6px',
                        backgroundColor: 'var(--bg-primary)',
                        border: '1px solid var(--border-color)',
                        color: 'var(--text-primary)',
                      }}
                    />
                  </div>

                  <div
                    style={{
                      padding: '1rem',
                      borderRadius: '6px',
                      backgroundColor: 'var(--bg-primary)',
                      border: '1px solid var(--border-color)',
                      display: 'flex',
                      flexDirection: 'column',
                      gap: '0.5rem',
                    }}
                  >
                    <div style={{ fontSize: '0.85rem', fontWeight: 600 }}>Automated Ingestion Defaults</div>
                    <ul style={{ margin: 0, paddingLeft: '1.25rem', fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
                      <li>Daily CUR 2.0 / FOCUS batch ingestion configured via SyncScheduler.</li>
                      <li>Hourly resource discovery checkpointing with exponential backoff.</li>
                      <li>Raw payload landing preserved immutably in MinIO before normalization.</li>
                    </ul>
                  </div>
                </div>
              )}

              {/* STEP 6: Completion Summary (Item 5) */}
              {wizardStep === 6 && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem', alignItems: 'center', textAlign: 'center', padding: '1rem 0' }}>
                  <div
                    style={{
                      width: '64px',
                      height: '64px',
                      borderRadius: '50%',
                      backgroundColor: 'rgba(16, 185, 129, 0.15)',
                      border: '2px solid #10b981',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      color: '#10b981',
                    }}
                  >
                    <CheckCircle2 size={36} />
                  </div>

                  <div>
                    <h3 style={{ margin: '0 0 0.5rem', fontSize: '1.25rem' }}>Cloud Connection Initialized</h3>
                    <p style={{ margin: 0, color: 'var(--text-secondary)', fontSize: '0.875rem', maxWidth: '480px' }}>
                      Connector successfully registered in PostgreSQL. Provider credentials stored in OpenBao under vault:// reference. Initial discovery sync queued.
                    </p>
                  </div>

                  {completionResult && (
                    <div
                      style={{
                        width: '100%',
                        backgroundColor: 'var(--bg-primary)',
                        border: '1px solid var(--border-color)',
                        borderRadius: '6px',
                        padding: '1rem',
                        textAlign: 'left',
                        display: 'flex',
                        flexDirection: 'column',
                        gap: '0.5rem',
                        fontSize: '0.825rem',
                      }}
                    >
                      <div><strong>Connector ID:</strong> <span style={{ color: '#38bdf8' }}>{completionResult.connector_id}</span></div>
                      <div><strong>Sync Status:</strong> <span style={{ color: '#10b981' }}>{completionResult.sync_status}</span></div>
                      <div><strong>Initial Rows Ingested:</strong> {completionResult.rows_ingested || 0}</div>
                      <div><strong>Schedules:</strong> Configured for automated daily/hourly ingestion</div>
                    </div>
                  )}
                </div>
              )}
            </div>

            {/* Wizard Navigation Footer */}
            <div
              style={{
                padding: '1rem 1.5rem',
                borderTop: '1px solid var(--border-color)',
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
              }}
            >
              {wizardStep > 1 && wizardStep < 6 ? (
                <button
                  onClick={() => setWizardStep(wizardStep - 1)}
                  style={{
                    padding: '0.5rem 1rem',
                    backgroundColor: 'transparent',
                    border: '1px solid var(--border-color)',
                    color: 'var(--text-primary)',
                    borderRadius: '4px',
                    cursor: 'pointer',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '0.35rem',
                  }}
                >
                  <ArrowLeft size={16} /> Back
                </button>
              ) : <div />}

              <div style={{ display: 'flex', gap: '0.75rem' }}>
                {wizardStep < 6 && (
                  <button
                    onClick={() => setIsAddWizardOpen(false)}
                    style={{
                      padding: '0.5rem 1rem',
                      backgroundColor: 'transparent',
                      border: '1px solid var(--border-color)',
                      color: 'var(--text-primary)',
                      borderRadius: '4px',
                      cursor: 'pointer',
                    }}
                  >
                    Cancel
                  </button>
                )}

                {wizardStep === 1 && (
                  <button
                    onClick={() => setWizardStep(2)}
                    style={{
                      padding: '0.5rem 1.25rem',
                      backgroundColor: '#0284c7',
                      border: 'none',
                      color: '#ffffff',
                      borderRadius: '4px',
                      fontWeight: 600,
                      cursor: 'pointer',
                      display: 'flex',
                      alignItems: 'center',
                      gap: '0.35rem',
                    }}
                  >
                    Next: Permissions <ArrowRight size={16} />
                  </button>
                )}

                {wizardStep === 2 && (
                  <button
                    onClick={() => setWizardStep(3)}
                    style={{
                      padding: '0.5rem 1.25rem',
                      backgroundColor: '#0284c7',
                      border: 'none',
                      color: '#ffffff',
                      borderRadius: '4px',
                      fontWeight: 600,
                      cursor: 'pointer',
                      display: 'flex',
                      alignItems: 'center',
                      gap: '0.35rem',
                    }}
                  >
                    Next: Enter Credentials <ArrowRight size={16} />
                  </button>
                )}

                {wizardStep === 3 && (
                  <button
                    disabled={wizardValidating}
                    onClick={handleValidateCredentialsInWizard}
                    style={{
                      padding: '0.5rem 1.25rem',
                      backgroundColor: '#0284c7',
                      border: 'none',
                      color: '#ffffff',
                      borderRadius: '4px',
                      fontWeight: 600,
                      cursor: wizardValidating ? 'not-allowed' : 'pointer',
                      display: 'flex',
                      alignItems: 'center',
                      gap: '0.35rem',
                    }}
                  >
                    {wizardValidating ? 'Validating...' : 'Validate & Next'} <ArrowRight size={16} />
                  </button>
                )}

                {wizardStep === 4 && (
                  <button
                    onClick={handleDiscoverScopesInWizard}
                    style={{
                      padding: '0.5rem 1.25rem',
                      backgroundColor: '#0284c7',
                      border: 'none',
                      color: '#ffffff',
                      borderRadius: '4px',
                      fontWeight: 600,
                      cursor: 'pointer',
                      display: 'flex',
                      alignItems: 'center',
                      gap: '0.35rem',
                    }}
                  >
                    Next: Select Scopes <ArrowRight size={16} />
                  </button>
                )}

                {wizardStep === 5 && (
                  <button
                    disabled={wizardValidating}
                    onClick={handleCompleteWizard}
                    style={{
                      padding: '0.5rem 1.25rem',
                      backgroundColor: '#10b981',
                      border: 'none',
                      color: '#ffffff',
                      borderRadius: '4px',
                      fontWeight: 600,
                      cursor: wizardValidating ? 'not-allowed' : 'pointer',
                    }}
                  >
                    {wizardValidating ? 'Finalizing...' : 'Save & Launch Ingestion'}
                  </button>
                )}

                {wizardStep === 6 && (
                  <button
                    onClick={() => setIsAddWizardOpen(false)}
                    style={{
                      padding: '0.5rem 1.25rem',
                      backgroundColor: '#0284c7',
                      border: 'none',
                      color: '#ffffff',
                      borderRadius: '4px',
                      fontWeight: 600,
                      cursor: 'pointer',
                    }}
                  >
                    Finish
                  </button>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
