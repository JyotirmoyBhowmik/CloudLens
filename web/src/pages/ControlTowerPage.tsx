import React, { useEffect, useState } from 'react';
import {
  AlertTriangle,
  CheckCircle,
  Clock,
  RefreshCw,
  Terminal,
  ExternalLink,
  ChevronRight,
  X,
  AlertOctagon,
  Wrench,
  Radio,
} from 'lucide-react';


interface PanelMetric {
  [key: string]: any;
}

interface Panel {
  id: string;
  name: string;
  status: 'green' | 'amber' | 'red' | 'grey';
  status_label: string;
  reason: string;
  metrics: PanelMetric;
  last_updated: string;
  grafana_url: string;
}

interface OverviewData {
  overall_status: 'green' | 'amber' | 'red' | 'grey';
  overall_label: string;
  maintenance_mode: boolean;
  panels: Panel[];
  timestamp: string;
}

interface BlastRadius {
  action: string;
  affected_tenants: string[];
  affected_connectors?: string[];
  affected_queues?: string[];
  impact_summary: string;
  requires_confirmation: boolean;
}

interface AuditEventItem {
  id: string;
  event_type: string;
  action: string;
  resource_type: string;
  actor_roles: string[];
  timestamp: string;
}

export const ControlTowerPage: React.FC = () => {
  const [overview, setOverview] = useState<OverviewData | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedPanel, setSelectedPanel] = useState<Panel | null>(null);
  const [auditTail, setAuditTail] = useState<AuditEventItem[]>([]);
  const [auditFilter, setAuditFilter] = useState<string>('');
  const [streamActive, setStreamActive] = useState<boolean>(false);

  // Operator capabilities & Actions
  const [hasOperatePermission] = useState<boolean>(true); // Superuser holds platform.operate
  const [actionModal, setActionModal] = useState<string | null>(null);
  const [actionReason, setActionReason] = useState<string>('Routine scheduled maintenance and sync operational validation');
  const [stepUpToken, setStepUpToken] = useState<string>('stepup-mfa-token-valid-9988');
  const [actionParams, setActionParams] = useState<Record<string, any>>({});
  const [blastRadius, setBlastRadius] = useState<BlastRadius | null>(null);
  const [actionFeedback, setActionFeedback] = useState<string | null>(null);
  const [actionLoading, setActionLoading] = useState<boolean>(false);

  // Fetch overview
  const fetchOverview = async () => {
    try {
      const res = await fetch('/api/v1/control-tower/overview', {
        headers: {
          'X-User-Roles': 'SUPER_ADMIN',
          'X-Scope-Grants': 'platform.observe,platform.operate',
        },
      });
      if (!res.ok) {
        throw new Error(`Failed to load Control Tower overview (HTTP ${res.status})`);
      }
      const data: OverviewData = await res.json();
      setOverview(data);
      setError(null);
    } catch (err: any) {
      setError(err.message || 'Unknown network error loading Control Tower');
    } finally {
      setLoading(false);
    }
  };

  // Fetch audit tail
  const fetchAuditTail = async () => {
    try {
      const res = await fetch('/api/v1/control-tower/audit/tail?limit=50', {
        headers: {
          'X-User-Roles': 'SUPER_ADMIN',
          'X-Scope-Grants': 'platform.observe',
        },
      });
      if (res.ok) {
        const data = await res.json();
        setAuditTail(data.events || []);
      }
    } catch {
      // Ignore background audit fetch failure
    }
  };

  useEffect(() => {
    fetchOverview();
    fetchAuditTail();

    // Setup Server-Sent Events stream
    let eventSource: EventSource | null = null;
    try {
      eventSource = new EventSource('/api/v1/control-tower/stream');
      eventSource.addEventListener('status_update', (e) => {
        try {
          JSON.parse(e.data);
          setStreamActive(true);
          // Refetch fresh overview data on push
          fetchOverview();
        } catch {}

      });
      eventSource.onopen = () => setStreamActive(true);
      eventSource.onerror = () => setStreamActive(false);
    } catch {
      setStreamActive(false);
    }

    const interval = setInterval(() => {
      fetchOverview();
      fetchAuditTail();
    }, 15000);

    return () => {
      clearInterval(interval);
      if (eventSource) eventSource.close();
    };
  }, []);

  // Request action blast radius
  const handleStageAction = async (actionName: string, defaultParams: Record<string, any> = {}) => {
    setActionModal(actionName);
    setActionParams(defaultParams);
    setActionFeedback(null);
    setBlastRadius(null);
    setActionLoading(true);

    try {
      const res = await fetch(`/api/v1/control-tower/actions/${actionName}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-User-Roles': 'SUPER_ADMIN',
          'X-Scope-Grants': 'platform.operate',
        },
        body: JSON.stringify({
          action: actionName,
          params: defaultParams,
          reason: actionReason,
          confirm: false,
        }),
      });
      const data = await res.json();
      if (data.blast_radius) {
        setBlastRadius(data.blast_radius);
      }
    } catch (err: any) {
      setActionFeedback(`Error evaluating blast radius: ${err.message}`);
    } finally {
      setActionLoading(false);
    }
  };

  // Execute confirmed action
  const handleConfirmAction = async () => {
    if (!actionModal) return;
    if (actionReason.trim().length < 20) {
      setActionFeedback('Operational reason must be at least 20 characters long.');
      return;
    }

    setActionLoading(true);
    setActionFeedback(null);

    try {
      const res = await fetch(`/api/v1/control-tower/actions/${actionModal}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Step-Up-Token': stepUpToken,
          'X-User-Roles': 'SUPER_ADMIN',
          'X-Scope-Grants': 'platform.operate',
        },
        body: JSON.stringify({
          action: actionModal,
          params: actionParams,
          reason: actionReason,
          step_up_token: stepUpToken,
          confirm: true,
        }),
      });

      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || `Action failed with status ${res.status}`);
      }

      setActionFeedback(`Action '${actionModal}' executed successfully! AuditEvent: ${data.audit_event_id}`);
      fetchOverview();
      fetchAuditTail();
      setTimeout(() => {
        setActionModal(null);
        setBlastRadius(null);
      }, 2500);
    } catch (err: any) {
      setActionFeedback(`Execution error: ${err.message}`);
    } finally {
      setActionLoading(false);
    }
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'green':
        return '#10b981';
      case 'amber':
        return '#f59e0b';
      case 'red':
        return '#ef4444';
      default:
        return '#6b7280';
    }
  };

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'green':
        return <CheckCircle size={18} color="#10b981" aria-hidden="true" />;
      case 'amber':
        return <AlertTriangle size={18} color="#f59e0b" aria-hidden="true" />;
      case 'red':
        return <AlertOctagon size={18} color="#ef4444" aria-hidden="true" />;
      default:
        return <Clock size={18} color="#6b7280" aria-hidden="true" />;
    }
  };

  const filteredAuditEvents = auditTail.filter(
    (ev) =>
      ev.action.toLowerCase().includes(auditFilter.toLowerCase()) ||
      ev.event_type.toLowerCase().includes(auditFilter.toLowerCase()) ||
      ev.resource_type.toLowerCase().includes(auditFilter.toLowerCase())
  );

  return (
    <div style={{ padding: '1.5rem', maxWidth: '1400px', margin: '0 auto', color: '#f8fafc' }}>
      {/* Maintenance Mode Banner */}
      {overview?.maintenance_mode && (
        <div
          role="alert"
          style={{
            backgroundColor: '#b45309',
            border: '1px solid #f59e0b',
            color: '#ffffff',
            padding: '1rem',
            borderRadius: '8px',
            marginBottom: '1.5rem',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
            <AlertOctagon size={24} color="#fef3c7" />
            <div>
              <strong style={{ fontSize: '1rem' }}>PLATFORM MAINTENANCE MODE ENGAGED</strong>
              <div style={{ fontSize: '0.875rem' }}>
                Non-administrative traffic is paused. Only operators with platform.operate may execute actions.
              </div>
            </div>
          </div>
          {hasOperatePermission && (
            <button
              onClick={() => handleStageAction('maintenance-mode', { enabled: false })}
              style={{
                backgroundColor: '#ffffff',
                color: '#b45309',
                border: 'none',
                padding: '0.5rem 1rem',
                borderRadius: '6px',
                fontWeight: 600,
                cursor: 'pointer',
              }}
            >
              Disable Maintenance Mode
            </button>
          )}
        </div>
      )}

      {/* Control Tower Header */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'flex-start',
          borderBottom: '1px solid #334155',
          paddingBottom: '1.25rem',
          marginBottom: '1.5rem',
          flexWrap: 'wrap',
          gap: '1rem',
        }}
      >
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
            <h1 style={{ fontSize: '1.75rem', fontWeight: 700, margin: 0, color: '#38bdf8' }}>
              Platform Control Tower
            </h1>
            <span
              style={{
                backgroundColor: '#0369a1',
                color: '#e0f2fe',
                padding: '0.2rem 0.6rem',
                borderRadius: '9999px',
                fontSize: '0.75rem',
                fontWeight: 600,
              }}
            >
              SUPERUSER CONTEXT
            </span>
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '0.35rem',
                fontSize: '0.75rem',
                color: streamActive ? '#10b981' : '#94a3b8',
              }}
            >
              <Radio size={14} />
              <span>{streamActive ? 'SSE LIVE' : 'STREAM CONNECTING'}</span>
            </div>
          </div>
          <p style={{ color: '#94a3b8', margin: '0.5rem 0 0 0', fontSize: '0.9rem' }}>
            Unified operational oversight, telemetry aggregation, and emergency control plane.
          </p>
        </div>

        {/* Global Controls & Status */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', flexWrap: 'wrap' }}>
          {overview && (
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '0.5rem',
                backgroundColor: '#1e293b',
                padding: '0.5rem 1rem',
                borderRadius: '8px',
                border: `1px solid ${getStatusColor(overview.overall_status)}`,
              }}
            >
              {getStatusIcon(overview.overall_status)}
              <div>
                <div style={{ fontSize: '0.75rem', color: '#94a3b8' }}>OVERALL PLATFORM</div>
                <div
                  style={{
                    fontSize: '0.9rem',
                    fontWeight: 700,
                    color: getStatusColor(overview.overall_status),
                  }}
                >
                  [{overview.overall_label}]
                </div>
              </div>
            </div>
          )}

          <a
            href="http://localhost:3001/d/cloudlens-platform-overview?orgId=1"
            target="_blank"
            rel="noopener noreferrer"
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '0.4rem',
              backgroundColor: '#0369a1',
              color: '#ffffff',
              padding: '0.55rem 1rem',
              borderRadius: '6px',
              textDecoration: 'none',
              fontWeight: 700,
              fontSize: '0.875rem',
            }}
          >
            Open in Grafana <ExternalLink size={14} />
          </a>

          <button
            onClick={() => {
              setLoading(true);
              fetchOverview();
              fetchAuditTail();
            }}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '0.4rem',
              backgroundColor: '#334155',
              color: '#f8fafc',
              border: 'none',
              padding: '0.55rem 0.9rem',
              borderRadius: '6px',
              cursor: 'pointer',
              fontSize: '0.875rem',
            }}
          >
            <RefreshCw size={14} /> Refresh
          </button>
        </div>
      </div>

      {/* Operator Action Bar (Visible with platform.operate) */}
      {hasOperatePermission && (
        <div
          style={{
            backgroundColor: '#0f172a',
            border: '1px solid #334155',
            borderRadius: '10px',
            padding: '1rem 1.25rem',
            marginBottom: '1.75rem',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            flexWrap: 'wrap',
            gap: '1rem',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
            <Wrench size={18} color="#38bdf8" />
            <strong style={{ fontSize: '0.9rem', color: '#e2e8f0' }}>Operator Actions (platform.operate):</strong>
          </div>

          <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
            <button
              onClick={() => handleStageAction('force-sync', { connector_id: 'aws-cur' })}
              style={{
                backgroundColor: '#1e293b',
                color: '#38bdf8',
                border: '1px solid #0284c7',
                padding: '0.4rem 0.8rem',
                borderRadius: '6px',
                cursor: 'pointer',
                fontSize: '0.8rem',
                fontWeight: 500,
              }}
            >
              Force Sync
            </button>
            <button
              onClick={() => handleStageAction('retry-job', { job_id: 'latest-failed-job' })}
              style={{
                backgroundColor: '#1e293b',
                color: '#38bdf8',
                border: '1px solid #0284c7',
                padding: '0.4rem 0.8rem',
                borderRadius: '6px',
                cursor: 'pointer',
                fontSize: '0.8rem',
                fontWeight: 500,
              }}
            >
              Retry Job
            </button>
            <button
              onClick={() => handleStageAction('trigger-backup')}
              style={{
                backgroundColor: '#1e293b',
                color: '#38bdf8',
                border: '1px solid #0284c7',
                padding: '0.4rem 0.8rem',
                borderRadius: '6px',
                cursor: 'pointer',
                fontSize: '0.8rem',
                fontWeight: 500,
              }}
            >
              Trigger Backup
            </button>
            <button
              onClick={() => handleStageAction('trigger-reconciliation')}
              style={{
                backgroundColor: '#1e293b',
                color: '#38bdf8',
                border: '1px solid #0284c7',
                padding: '0.4rem 0.8rem',
                borderRadius: '6px',
                cursor: 'pointer',
                fontSize: '0.8rem',
                fontWeight: 500,
              }}
            >
              Trigger Reconciliation
            </button>
            <button
              onClick={() => handleStageAction('maintenance-mode', { enabled: !overview?.maintenance_mode })}
              style={{
                backgroundColor: overview?.maintenance_mode ? '#10b981' : '#b45309',
                color: '#ffffff',
                border: 'none',
                padding: '0.4rem 0.8rem',
                borderRadius: '6px',
                cursor: 'pointer',
                fontSize: '0.8rem',
                fontWeight: 600,
              }}
            >
              {overview?.maintenance_mode ? 'End Maint Mode' : 'Toggle Maint Mode'}
            </button>
          </div>
        </div>
      )}

      {loading && !overview ? (
        <div style={{ textAlign: 'center', padding: '3rem', color: '#94a3b8' }}>
          <RefreshCw size={32} className="spin" style={{ animation: 'spin 1s linear infinite' }} />
          <p style={{ marginTop: '1rem' }}>Aggregating Control Tower telemetry from 14 operational panels...</p>
        </div>
      ) : error ? (
        <div
          style={{
            backgroundColor: '#450a0a',
            border: '1px solid #ef4444',
            padding: '1.5rem',
            borderRadius: '8px',
            color: '#fca5a5',
          }}
        >
          <strong>Error loading Control Tower:</strong> {error}
        </div>
      ) : (
        <>
          {/* 14 Panels Grid */}
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))',
              gap: '1.25rem',
              marginBottom: '2.5rem',
            }}
          >
            {overview?.panels.map((panel) => (
              <div
                key={panel.id}
                onClick={() => setSelectedPanel(panel)}
                style={{
                  backgroundColor: '#1e293b',
                  border: `1px solid ${panel.status === 'red' ? '#ef4444' : panel.status === 'amber' ? '#f59e0b' : '#334155'}`,
                  borderRadius: '10px',
                  padding: '1.25rem',
                  cursor: 'pointer',
                  transition: 'all 0.2s ease',
                  position: 'relative',
                  overflow: 'hidden',
                }}
              >
                {/* Status indicator bar */}
                <div
                  style={{
                    position: 'absolute',
                    top: 0,
                    left: 0,
                    right: 0,
                    height: '4px',
                    backgroundColor: getStatusColor(panel.status),
                  }}
                />

                <div
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'flex-start',
                    marginBottom: '0.75rem',
                  }}
                >
                  <h3 style={{ fontSize: '1rem', fontWeight: 600, margin: 0, color: '#f1f5f9' }}>
                    {panel.name}
                  </h3>
                  <div
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '0.35rem',
                      backgroundColor: '#0f172a',
                      padding: '0.2rem 0.5rem',
                      borderRadius: '4px',
                      fontSize: '0.75rem',
                      fontWeight: 700,
                      color: getStatusColor(panel.status),
                      border: `1px solid ${getStatusColor(panel.status)}`,
                    }}
                  >
                    {getStatusIcon(panel.status)}
                    <span>[{panel.status_label}]</span>
                  </div>
                </div>

                <p
                  style={{
                    fontSize: '0.85rem',
                    color: '#94a3b8',
                    lineHeight: '1.4',
                    minHeight: '2.4rem',
                    margin: '0 0 1rem 0',
                  }}
                >
                  {panel.reason}
                </p>

                {/* Metric snippets */}
                <div
                  style={{
                    display: 'flex',
                    flexWrap: 'wrap',
                    gap: '0.5rem',
                    fontSize: '0.75rem',
                    color: '#cbd5e1',
                    marginBottom: '0.75rem',
                  }}
                >
                  {Object.entries(panel.metrics)
                    .slice(0, 3)
                    .map(([k, v]) => (
                      <span
                        key={k}
                        style={{
                          backgroundColor: '#0f172a',
                          padding: '0.2rem 0.5rem',
                          borderRadius: '4px',
                          border: '1px solid #334155',
                        }}
                      >
                        <strong>{k}:</strong> {String(v)}
                      </span>
                    ))}
                </div>

                <div
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    fontSize: '0.75rem',
                    color: '#64748b',
                    borderTop: '1px solid #334155',
                    paddingTop: '0.6rem',
                  }}
                >
                  <span>Updated: {new Date(panel.last_updated).toLocaleTimeString()}</span>
                  <span
                    style={{
                      color: '#38bdf8',
                      display: 'flex',
                      alignItems: 'center',
                      gap: '0.2rem',
                      fontWeight: 500,
                    }}
                  >
                    Drill down <ChevronRight size={14} />
                  </span>
                </div>
              </div>
            ))}
          </div>

          {/* Drill Down Drawer / Modal */}
          {selectedPanel && (
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
                padding: '1rem',
              }}
            >
              <div
                style={{
                  backgroundColor: '#1e293b',
                  border: '1px solid #334155',
                  borderRadius: '12px',
                  width: '100%',
                  maxWidth: '650px',
                  padding: '1.75rem',
                  position: 'relative',
                }}
              >
                <button
                  onClick={() => setSelectedPanel(null)}
                  style={{
                    position: 'absolute',
                    top: '1rem',
                    right: '1rem',
                    background: 'transparent',
                    border: 'none',
                    color: '#94a3b8',
                    cursor: 'pointer',
                  }}
                >
                  <X size={20} />
                </button>

                <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', marginBottom: '0.75rem' }}>
                  {getStatusIcon(selectedPanel.status)}
                  <h2 style={{ fontSize: '1.25rem', fontWeight: 700, margin: 0, color: '#f8fafc' }}>
                    {selectedPanel.name}
                  </h2>
                </div>

                <div
                  style={{
                    backgroundColor: '#0f172a',
                    padding: '0.8rem 1rem',
                    borderRadius: '6px',
                    marginBottom: '1.25rem',
                    borderLeft: `4px solid ${getStatusColor(selectedPanel.status)}`,
                  }}
                >
                  <strong style={{ fontSize: '0.85rem', color: getStatusColor(selectedPanel.status) }}>
                    STATUS: [{selectedPanel.status_label}]
                  </strong>
                  <p style={{ margin: '0.35rem 0 0 0', fontSize: '0.875rem', color: '#cbd5e1' }}>
                    {selectedPanel.reason}
                  </p>
                </div>

                <h4 style={{ fontSize: '0.9rem', color: '#94a3b8', margin: '0 0 0.5rem 0' }}>
                  Detailed Operational Telemetry:
                </h4>
                <pre
                  style={{
                    backgroundColor: '#0f172a',
                    padding: '1rem',
                    borderRadius: '6px',
                    fontSize: '0.825rem',
                    color: '#38bdf8',
                    overflowX: 'auto',
                    border: '1px solid #334155',
                    marginBottom: '1.5rem',
                  }}
                >
                  {JSON.stringify(selectedPanel.metrics, null, 2)}
                </pre>

                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <a
                    href={selectedPanel.grafana_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '0.4rem',
                      backgroundColor: '#0369a1',
                      color: '#ffffff',
                      padding: '0.55rem 1rem',
                      borderRadius: '6px',
                      textDecoration: 'none',
                      fontWeight: 700,
                      fontSize: '0.85rem',
                    }}
                  >
                    Open Panel in Grafana <ExternalLink size={14} />
                  </a>

                  <button
                    onClick={() => setSelectedPanel(null)}
                    style={{
                      backgroundColor: '#334155',
                      color: '#f8fafc',
                      border: 'none',
                      padding: '0.55rem 1rem',
                      borderRadius: '6px',
                      cursor: 'pointer',
                      fontSize: '0.85rem',
                    }}
                  >
                    Close
                  </button>
                </div>
              </div>
            </div>
          )}

          {/* Action Modal (Confirmation & Blast Radius Step) */}
          {actionModal && (
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
                zIndex: 1100,
                padding: '1rem',
              }}
            >
              <div
                style={{
                  backgroundColor: '#1e293b',
                  border: '1px solid #f59e0b',
                  borderRadius: '12px',
                  width: '100%',
                  maxWidth: '650px',
                  padding: '1.75rem',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '1rem' }}>
                  <Wrench size={22} color="#f59e0b" />
                  <h2 style={{ fontSize: '1.25rem', fontWeight: 700, margin: 0, color: '#f8fafc' }}>
                    Confirm Action: {actionModal}
                  </h2>
                </div>

                <div
                  style={{
                    backgroundColor: '#451a03',
                    border: '1px solid #78350f',
                    padding: '0.75rem 1rem',
                    borderRadius: '6px',
                    marginBottom: '1.25rem',
                    color: '#fde68a',
                    fontSize: '0.85rem',
                  }}
                >
                  <strong>CONFIRMATION STEP REQUIRED:</strong> Review the predicted blast radius before executing.
                  All actions are logged in the immutable audit ledger with the specified justification.
                </div>

                {blastRadius && (
                  <div
                    style={{
                      backgroundColor: '#0f172a',
                      padding: '1rem',
                      borderRadius: '8px',
                      marginBottom: '1.25rem',
                      border: '1px solid #334155',
                    }}
                  >
                    <h4 style={{ margin: '0 0 0.5rem 0', color: '#38bdf8', fontSize: '0.9rem' }}>
                      Predicted Blast Radius:
                    </h4>
                    <p style={{ margin: '0 0 0.75rem 0', fontSize: '0.85rem', color: '#e2e8f0' }}>
                      {blastRadius.impact_summary}
                    </p>
                    <div style={{ fontSize: '0.8rem', color: '#94a3b8' }}>
                      <div>Affected Tenants: {blastRadius.affected_tenants.join(', ')}</div>
                      {blastRadius.affected_connectors && blastRadius.affected_connectors.length > 0 && (
                        <div>Affected Connectors: {blastRadius.affected_connectors.join(', ')}</div>
                      )}
                      {blastRadius.affected_queues && blastRadius.affected_queues.length > 0 && (
                        <div>Affected Queues: {blastRadius.affected_queues.join(', ')}</div>
                      )}
                    </div>
                  </div>
                )}

                <div style={{ marginBottom: '1rem' }}>
                  <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 600, marginBottom: '0.35rem' }}>
                    Operational Reason (min 20 characters):
                  </label>
                  <textarea
                    value={actionReason}
                    onChange={(e) => setActionReason(e.target.value)}
                    rows={3}
                    style={{
                      width: '100%',
                      backgroundColor: '#0f172a',
                      border: '1px solid #334155',
                      borderRadius: '6px',
                      padding: '0.5rem',
                      color: '#f8fafc',
                      fontSize: '0.85rem',
                    }}
                  />
                  <div style={{ fontSize: '0.75rem', color: actionReason.length >= 20 ? '#10b981' : '#f87171', marginTop: '0.2rem' }}>
                    {actionReason.length} / 20 characters minimum
                  </div>
                </div>

                <div style={{ marginBottom: '1.25rem' }}>
                  <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 600, marginBottom: '0.35rem' }}>
                    Step-Up MFA Authentication Token:
                  </label>
                  <input
                    type="password"
                    value={stepUpToken}
                    onChange={(e) => setStepUpToken(e.target.value)}
                    style={{
                      width: '100%',
                      backgroundColor: '#0f172a',
                      border: '1px solid #334155',
                      borderRadius: '6px',
                      padding: '0.5rem',
                      color: '#f8fafc',
                      fontSize: '0.85rem',
                    }}
                  />
                </div>

                {actionFeedback && (
                  <div
                    style={{
                      padding: '0.75rem',
                      borderRadius: '6px',
                      marginBottom: '1rem',
                      fontSize: '0.85rem',
                      backgroundColor: actionFeedback.includes('Error') ? '#450a0a' : '#064e3b',
                      color: actionFeedback.includes('Error') ? '#fca5a5' : '#a7f3d0',
                    }}
                  >
                    {actionFeedback}
                  </div>
                )}

                <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.75rem' }}>
                  <button
                    onClick={() => {
                      setActionModal(null);
                      setBlastRadius(null);
                    }}
                    style={{
                      backgroundColor: '#334155',
                      color: '#f8fafc',
                      border: 'none',
                      padding: '0.55rem 1.25rem',
                      borderRadius: '6px',
                      cursor: 'pointer',
                    }}
                  >
                    Cancel
                  </button>
                  <button
                    onClick={handleConfirmAction}
                    disabled={actionLoading || actionReason.length < 20}
                    style={{
                      backgroundColor: actionReason.length >= 20 ? '#d97706' : '#64748b',
                      color: '#ffffff',
                      border: 'none',
                      padding: '0.55rem 1.25rem',
                      borderRadius: '6px',
                      fontWeight: 600,
                      cursor: actionReason.length >= 20 ? 'pointer' : 'not-allowed',
                    }}
                  >
                    {actionLoading ? 'Executing...' : 'Confirm & Execute'}
                  </button>
                </div>
              </div>
            </div>
          )}

          {/* Live Audit Tail Section */}
          <div
            style={{
              backgroundColor: '#1e293b',
              border: '1px solid #334155',
              borderRadius: '10px',
              padding: '1.5rem',
            }}
          >
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                marginBottom: '1rem',
                flexWrap: 'wrap',
                gap: '0.75rem',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <Terminal size={18} color="#38bdf8" />
                <h3 style={{ margin: 0, fontSize: '1.1rem', fontWeight: 600 }}>
                  Live Audit Tail (Prompt R-CT Inspection)
                </h3>
              </div>
              <input
                type="text"
                placeholder="Filter by action, type, or resource..."
                value={auditFilter}
                onChange={(e) => setAuditFilter(e.target.value)}
                style={{
                  backgroundColor: '#0f172a',
                  border: '1px solid #334155',
                  borderRadius: '6px',
                  padding: '0.4rem 0.8rem',
                  color: '#f8fafc',
                  fontSize: '0.85rem',
                  minWidth: '260px',
                }}
              />
            </div>

            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.85rem' }}>
                <thead>
                  <tr style={{ borderBottom: '1px solid #334155', color: '#94a3b8', textAlign: 'left' }}>
                    <th style={{ padding: '0.6rem 0.8rem' }}>Event ID</th>
                    <th style={{ padding: '0.6rem 0.8rem' }}>Event Type</th>
                    <th style={{ padding: '0.6rem 0.8rem' }}>Action</th>
                    <th style={{ padding: '0.6rem 0.8rem' }}>Resource Type</th>
                    <th style={{ padding: '0.6rem 0.8rem' }}>Actor Roles</th>
                    <th style={{ padding: '0.6rem 0.8rem' }}>Timestamp</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredAuditEvents.length === 0 ? (
                    <tr>
                      <td colSpan={6} style={{ padding: '1.5rem', textAlign: 'center', color: '#64748b' }}>
                        No audit events matching current filter.
                      </td>
                    </tr>
                  ) : (
                    filteredAuditEvents.slice(0, 15).map((ev) => (
                      <tr key={ev.id} style={{ borderBottom: '1px solid #293548' }}>
                        <td style={{ padding: '0.6rem 0.8rem', fontFamily: 'monospace', color: '#38bdf8' }}>
                          {ev.id.slice(0, 12)}...
                        </td>
                        <td style={{ padding: '0.6rem 0.8rem', fontWeight: 600 }}>{ev.event_type}</td>
                        <td style={{ padding: '0.6rem 0.8rem', color: '#cbd5e1' }}>{ev.action}</td>
                        <td style={{ padding: '0.6rem 0.8rem', color: '#94a3b8' }}>{ev.resource_type}</td>
                        <td style={{ padding: '0.6rem 0.8rem', color: '#94a3b8' }}>{ev.actor_roles?.join(', ')}</td>
                        <td style={{ padding: '0.6rem 0.8rem', color: '#64748b' }}>
                          {new Date(ev.timestamp).toLocaleString()}
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </div>
  );
};
