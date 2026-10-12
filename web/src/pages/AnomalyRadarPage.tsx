import React, { useState } from 'react';
import {
  CheckCircle,
  Activity,
  Play,
  RotateCcw,
} from 'lucide-react';

export interface AnomalyItem {
  id: string;
  provider: 'AWS' | 'Azure' | 'GCP' | 'OCI';
  severity: 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW';
  title: string;
  resourceId: string;
  service: string;
  region: string;
  monthlyCost: number;
  velocity: string;
  detectionType: 'HEURISTIC' | 'PROPHET_ML' | 'RULE_BREACH';
  status: 'ACTIVE' | 'ACKNOWLEDGED' | 'REMEDIATED';
  detectedAt: string;
}

const INITIAL_ANOMALIES: AnomalyItem[] = [
  {
    id: 'anom-101',
    provider: 'AWS',
    severity: 'CRITICAL',
    title: 'Unattached gp3 EBS Volume IOPS Provisioning Burst',
    resourceId: 'vol-0a8bf89ce4b912a',
    service: 'Amazon EC2 EBS',
    region: 'us-east-1',
    monthlyCost: 4250,
    velocity: '+340% spike in 4h',
    detectionType: 'HEURISTIC',
    status: 'ACTIVE',
    detectedAt: '12m ago',
  },
  {
    id: 'anom-102',
    provider: 'GCP',
    severity: 'HIGH',
    title: 'Idle Vertex AI Custom Training Cluster with A100 GPUs',
    resourceId: 'gke-vertex-gpu-pool-prod',
    service: 'Google Kubernetes Engine / Vertex AI',
    region: 'europe-west1',
    monthlyCost: 6800,
    velocity: '0% GPU utilisation for 18h',
    detectionType: 'PROPHET_ML',
    status: 'ACTIVE',
    detectedAt: '34m ago',
  },
  {
    id: 'anom-103',
    provider: 'Azure',
    severity: 'MEDIUM',
    title: 'Cross-Region Inter-VNet Gateway Egress Spike',
    resourceId: 'vnet-gw-prod-westeurope',
    service: 'Virtual Network Gateway',
    region: 'westeurope',
    monthlyCost: 2150,
    velocity: '+185 GB/h outbound transfer',
    detectionType: 'RULE_BREACH',
    status: 'ACTIVE',
    detectedAt: '1h ago',
  },
  {
    id: 'anom-104',
    provider: 'OCI',
    severity: 'LOW',
    title: 'Orphaned Database Backup Snapshot Accumulation',
    resourceId: 'ocid1.volume.oc1.iad.abuwclj',
    service: 'Oracle Block Volumes',
    region: 'us-ashburn-1',
    monthlyCost: 1620,
    velocity: 'Retention policy exceeded by 45d',
    detectionType: 'HEURISTIC',
    status: 'ACTIVE',
    detectedAt: '3h ago',
  },
];

export const AnomalyRadarPage: React.FC = () => {
  const [items, setItems] = useState<AnomalyItem[]>(INITIAL_ANOMALIES);
  const [selectedProvider, setSelectedProvider] = useState<string>('ALL');
  const [selectedSeverity, setSelectedSeverity] = useState<string>('ALL');
  const [notification, setNotification] = useState<string | null>(null);

  const activeItems = items.filter((i) => i.status !== 'REMEDIATED');
  const totalImpact = activeItems.reduce((acc, curr) => acc + curr.monthlyCost, 0);

  const filteredItems = items.filter((item) => {
    if (selectedProvider !== 'ALL' && item.provider !== selectedProvider) return false;
    if (selectedSeverity !== 'ALL' && item.severity !== selectedSeverity) return false;
    return true;
  });

  const handleRemediate = (id: string) => {
    setItems((prev) =>
      prev.map((i) => (i.id === id ? { ...i, status: 'REMEDIATED' } : i))
    );
    const target = items.find((i) => i.id === id);
    setNotification(`Remediation task dispatched for ${target?.title || id}. Condition queued for verification.`);
    setTimeout(() => setNotification(null), 4000);
  };

  const handleAcknowledge = (id: string) => {
    setItems((prev) =>
      prev.map((i) => (i.id === id ? { ...i, status: 'ACKNOWLEDGED' } : i))
    );
  };

  const handleInjectSimulated = () => {
    const clouds: Array<'AWS' | 'Azure' | 'GCP' | 'OCI'> = ['AWS', 'Azure', 'GCP', 'OCI'];
    const prov = clouds[Math.floor(Math.random() * clouds.length)];
    const cost = Math.floor(Math.random() * 4500) + 1500;
    const newAnom: AnomalyItem = {
      id: `anom-${Date.now().toString().slice(-4)}`,
      provider: prov,
      severity: 'HIGH',
      title: 'Automated Replica Loop Rapid Autoscaling Anomaly',
      resourceId: `res-k8s-pod-${Math.random().toString(36).substring(7)}`,
      service: 'Managed Kubernetes Autoscaler',
      region: 'global',
      monthlyCost: cost,
      velocity: '+280% sudden rate increase',
      detectionType: 'PROPHET_ML',
      status: 'ACTIVE',
      detectedAt: 'Just now',
    };
    setItems((prev) => [newAnom, ...prev]);
    setNotification(`Simulated real-time spend anomaly injected: ${newAnom.title} (${prov})`);
    setTimeout(() => setNotification(null), 4000);
  };

  const handleReset = () => {
    setItems(INITIAL_ANOMALIES);
    setNotification('Anomaly Radar state reset to baseline.');
    setTimeout(() => setNotification(null), 3000);
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem', paddingBottom: '2rem' }}>
      {/* Top Banner */}
      <div
        style={{
          backgroundColor: 'var(--bg-secondary, #1a202c)',
          border: '1px solid var(--border-color, #2d3748)',
          borderRadius: '12px',
          padding: '1.5rem',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          flexWrap: 'wrap',
          gap: '1rem',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
          <div
            style={{
              width: '48px',
              height: '48px',
              borderRadius: '10px',
              backgroundColor: 'rgba(16, 185, 129, 0.15)',
              border: '1px solid rgba(16, 185, 129, 0.3)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: '#10b981',
            }}
          >
            <Activity size={24} />
          </div>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
              <h1 style={{ fontSize: '1.35rem', fontWeight: '700', margin: 0, color: 'var(--text-primary, #fff)' }}>
                Multi-Cloud FinOps Anomaly Radar
              </h1>
              <span
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '0.35rem',
                  padding: '0.2rem 0.6rem',
                  borderRadius: '9999px',
                  fontSize: '0.75rem',
                  fontWeight: '600',
                  backgroundColor: 'rgba(16, 185, 129, 0.15)',
                  color: '#10b981',
                  border: '1px solid rgba(16, 185, 129, 0.3)',
                }}
              >
                <span
                  style={{
                    width: '6px',
                    height: '6px',
                    borderRadius: '50%',
                    backgroundColor: '#10b981',
                  }}
                />
                Live Stream Active
              </span>
            </div>
            <p style={{ margin: '0.25rem 0 0 0', fontSize: '0.85rem', color: 'var(--text-secondary, #a0aec0)' }}>
              Continuous heuristic & statistical Prophet ML stream evaluating spend drift across connected cloud estates.
            </p>
          </div>
        </div>

        <div style={{ display: 'flex', gap: '0.75rem' }}>
          <button
            onClick={handleInjectSimulated}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '0.5rem',
              padding: '0.5rem 1rem',
              borderRadius: '8px',
              fontSize: '0.85rem',
              fontWeight: '600',
              backgroundColor: 'var(--bg-tertiary, #2d3748)',
              color: 'var(--text-primary, #fff)',
              border: '1px solid var(--border-color, #4a5568)',
              cursor: 'pointer',
            }}
          >
            <Play size={15} />
            + Inject Simulated Anomaly
          </button>
          <button
            onClick={handleReset}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '0.5rem',
              padding: '0.5rem 0.85rem',
              borderRadius: '8px',
              fontSize: '0.85rem',
              fontWeight: '600',
              backgroundColor: 'transparent',
              color: 'var(--text-secondary, #a0aec0)',
              border: '1px solid var(--border-color, #4a5568)',
              cursor: 'pointer',
            }}
          >
            <RotateCcw size={14} />
            Reset
          </button>
        </div>
      </div>

      {notification && (
        <div
          style={{
            padding: '0.75rem 1.25rem',
            borderRadius: '8px',
            backgroundColor: 'rgba(59, 130, 246, 0.15)',
            border: '1px solid rgba(59, 130, 246, 0.3)',
            color: '#60a5fa',
            fontSize: '0.85rem',
            display: 'flex',
            alignItems: 'center',
            gap: '0.5rem',
          }}
        >
          <CheckCircle size={16} />
          {notification}
        </div>
      )}

      {/* Metric Cards Grid */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
          gap: '1rem',
        }}
      >
        <div
          style={{
            backgroundColor: 'var(--bg-secondary, #1a202c)',
            border: '1px solid var(--border-color, #2d3748)',
            borderRadius: '10px',
            padding: '1.25rem',
          }}
        >
          <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary, #a0aec0)', fontWeight: '600', textTransform: 'uppercase' }}>
            Active Waste Impact
          </div>
          <div style={{ fontSize: '1.65rem', fontWeight: '800', color: '#f59e0b', margin: '0.35rem 0' }}>
            ${totalImpact.toLocaleString()} / mo
          </div>
          <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary, #a0aec0)' }}>
            Across {activeItems.length} active anomalies
          </div>
        </div>

        <div
          style={{
            backgroundColor: 'var(--bg-secondary, #1a202c)',
            border: '1px solid var(--border-color, #2d3748)',
            borderRadius: '10px',
            padding: '1.25rem',
          }}
        >
          <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary, #a0aec0)', fontWeight: '600', textTransform: 'uppercase' }}>
            Peak Spike Velocity
          </div>
          <div style={{ fontSize: '1.65rem', fontWeight: '800', color: '#f43f5e', margin: '0.35rem 0' }}>
            +340%
          </div>
          <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary, #a0aec0)' }}>
            AWS EBS gp3 IOPS in us-east-1
          </div>
        </div>

        <div
          style={{
            backgroundColor: 'var(--bg-secondary, #1a202c)',
            border: '1px solid var(--border-color, #2d3748)',
            borderRadius: '10px',
            padding: '1.25rem',
          }}
        >
          <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary, #a0aec0)', fontWeight: '600', textTransform: 'uppercase' }}>
            Auto-Remediable Rate
          </div>
          <div style={{ fontSize: '1.65rem', fontWeight: '800', color: '#10b981', margin: '0.35rem 0' }}>
            75%
          </div>
          <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary, #a0aec0)' }}>
            3 of 4 support automated rollbacks
          </div>
        </div>

        <div
          style={{
            backgroundColor: 'var(--bg-secondary, #1a202c)',
            border: '1px solid var(--border-color, #2d3748)',
            borderRadius: '10px',
            padding: '1.25rem',
          }}
        >
          <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary, #a0aec0)', fontWeight: '600', textTransform: 'uppercase' }}>
            Detection Engine
          </div>
          <div style={{ fontSize: '1.65rem', fontWeight: '800', color: '#60a5fa', margin: '0.35rem 0' }}>
            Hybrid
          </div>
          <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary, #a0aec0)' }}>
            Heuristic rules + Prophet ML
          </div>
        </div>
      </div>

      {/* Filter Toolbar */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          backgroundColor: 'var(--bg-secondary, #1a202c)',
          border: '1px solid var(--border-color, #2d3748)',
          borderRadius: '8px',
          padding: '0.75rem 1.25rem',
          flexWrap: 'wrap',
          gap: '0.75rem',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <span style={{ fontSize: '0.8rem', color: 'var(--text-secondary, #a0aec0)', fontWeight: '600' }}>Cloud:</span>
          {['ALL', 'AWS', 'Azure', 'GCP', 'OCI'].map((prov) => (
            <button
              key={prov}
              onClick={() => setSelectedProvider(prov)}
              style={{
                padding: '0.3rem 0.75rem',
                borderRadius: '6px',
                fontSize: '0.8rem',
                fontWeight: '600',
                border: 'none',
                cursor: 'pointer',
                backgroundColor: selectedProvider === prov ? 'var(--accent-primary, #3182ce)' : 'transparent',
                color: selectedProvider === prov ? '#fff' : 'var(--text-secondary, #a0aec0)',
              }}
            >
              {prov}
            </button>
          ))}
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <span style={{ fontSize: '0.8rem', color: 'var(--text-secondary, #a0aec0)', fontWeight: '600' }}>Severity:</span>
          {['ALL', 'CRITICAL', 'HIGH', 'MEDIUM', 'LOW'].map((sev) => (
            <button
              key={sev}
              onClick={() => setSelectedSeverity(sev)}
              style={{
                padding: '0.3rem 0.65rem',
                borderRadius: '6px',
                fontSize: '0.8rem',
                fontWeight: '600',
                border: 'none',
                cursor: 'pointer',
                backgroundColor: selectedSeverity === sev ? 'var(--accent-primary, #3182ce)' : 'transparent',
                color: selectedSeverity === sev ? '#fff' : 'var(--text-secondary, #a0aec0)',
              }}
            >
              {sev}
            </button>
          ))}
        </div>
      </div>

      {/* Anomaly Stream Table */}
      <div
        style={{
          backgroundColor: 'var(--bg-secondary, #1a202c)',
          border: '1px solid var(--border-color, #2d3748)',
          borderRadius: '12px',
          overflow: 'hidden',
        }}
      >
        <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '0.85rem' }}>
          <thead>
            <tr style={{ backgroundColor: 'var(--bg-tertiary, #2d3748)', borderBottom: '1px solid var(--border-color, #4a5568)' }}>
              <th style={{ padding: '0.85rem 1rem', color: 'var(--text-secondary, #a0aec0)', fontWeight: '600' }}>SEVERITY</th>
              <th style={{ padding: '0.85rem 1rem', color: 'var(--text-secondary, #a0aec0)', fontWeight: '600' }}>ANOMALY / ROOT CAUSE</th>
              <th style={{ padding: '0.85rem 1rem', color: 'var(--text-secondary, #a0aec0)', fontWeight: '600' }}>RESOURCE / SERVICE</th>
              <th style={{ padding: '0.85rem 1rem', color: 'var(--text-secondary, #a0aec0)', fontWeight: '600' }}>VELOCITY SPIKE</th>
              <th style={{ padding: '0.85rem 1rem', color: 'var(--text-secondary, #a0aec0)', fontWeight: '600' }}>RUN-RATE COST</th>
              <th style={{ padding: '0.85rem 1rem', color: 'var(--text-secondary, #a0aec0)', fontWeight: '600', textAlign: 'right' }}>ACTIONS</th>
            </tr>
          </thead>
          <tbody>
            {filteredItems.length === 0 ? (
              <tr>
                <td colSpan={6} style={{ padding: '3rem', textAlign: 'center', color: 'var(--text-secondary, #a0aec0)' }}>
                  ✨ No anomalies found matching the selected filters.
                </td>
              </tr>
            ) : (
              filteredItems.map((item) => {
                const isRemediated = item.status === 'REMEDIATED';
                const sevColor =
                  item.severity === 'CRITICAL'
                    ? { bg: 'rgba(244, 63, 94, 0.15)', text: '#f43f5e', border: 'rgba(244, 63, 94, 0.3)' }
                    : item.severity === 'HIGH'
                    ? { bg: 'rgba(245, 158, 11, 0.15)', text: '#f59e0b', border: 'rgba(245, 158, 11, 0.3)' }
                    : item.severity === 'MEDIUM'
                    ? { bg: 'rgba(59, 130, 246, 0.15)', text: '#60a5fa', border: 'rgba(59, 130, 246, 0.3)' }
                    : { bg: 'rgba(156, 163, 175, 0.15)', text: '#9ca3af', border: 'rgba(156, 163, 175, 0.3)' };

                return (
                  <tr
                    key={item.id}
                    style={{
                      borderBottom: '1px solid var(--border-color, #2d3748)',
                      opacity: isRemediated ? 0.45 : 1,
                      backgroundColor: isRemediated ? 'rgba(0,0,0,0.1)' : 'transparent',
                    }}
                  >
                    <td style={{ padding: '1rem' }}>
                      <span
                        style={{
                          display: 'inline-block',
                          padding: '0.2rem 0.55rem',
                          borderRadius: '4px',
                          fontSize: '0.72rem',
                          fontWeight: '700',
                          backgroundColor: sevColor.bg,
                          color: sevColor.text,
                          border: `1px solid ${sevColor.border}`,
                        }}
                      >
                        {item.severity}
                      </span>
                    </td>
                    <td style={{ padding: '1rem' }}>
                      <div style={{ fontWeight: '600', color: 'var(--text-primary, #fff)', marginBottom: '0.2rem' }}>
                        {item.title}
                      </div>
                      <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary, #a0aec0)' }}>
                        Detected via {item.detectionType} • {item.detectedAt}
                      </div>
                    </td>
                    <td style={{ padding: '1rem' }}>
                      <div style={{ fontFamily: 'monospace', color: '#93c5fd', fontSize: '0.8rem' }}>
                        {item.resourceId}
                      </div>
                      <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary, #a0aec0)' }}>
                        {item.provider} • {item.service} ({item.region})
                      </div>
                    </td>
                    <td style={{ padding: '1rem', color: '#f43f5e', fontWeight: '600' }}>
                      {item.velocity}
                    </td>
                    <td style={{ padding: '1rem' }}>
                      <div style={{ fontWeight: '700', color: 'var(--text-primary, #fff)' }}>
                        ${item.monthlyCost.toLocaleString()} / mo
                      </div>
                      <div style={{ fontSize: '0.7rem', color: 'var(--text-secondary, #a0aec0)' }}>
                        Recoverable
                      </div>
                    </td>
                    <td style={{ padding: '1rem', textAlign: 'right' }}>
                      {isRemediated ? (
                        <span style={{ fontSize: '0.8rem', color: '#10b981', fontWeight: '600' }}>
                          ✓ Resolved
                        </span>
                      ) : (
                        <div style={{ display: 'flex', gap: '0.5rem', justifyContent: 'flex-end' }}>
                          <button
                            onClick={() => handleAcknowledge(item.id)}
                            style={{
                              padding: '0.35rem 0.65rem',
                              borderRadius: '6px',
                              fontSize: '0.75rem',
                              fontWeight: '600',
                              backgroundColor: 'transparent',
                              border: '1px solid var(--border-color, #4a5568)',
                              color: 'var(--text-secondary, #a0aec0)',
                              cursor: 'pointer',
                            }}
                          >
                            Ack
                          </button>
                          <button
                            onClick={() => handleRemediate(item.id)}
                            style={{
                              padding: '0.35rem 0.85rem',
                              borderRadius: '6px',
                              fontSize: '0.75rem',
                              fontWeight: '600',
                              backgroundColor: '#10b981',
                              color: '#fff',
                              border: 'none',
                              cursor: 'pointer',
                            }}
                          >
                            Remediate
                          </button>
                        </div>
                      )}
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
};
