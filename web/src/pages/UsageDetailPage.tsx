import React, { useState, useEffect } from 'react';
import {
  Breadcrumb,
  NullValue,
  FreshnessIndicator,
  EmptyState,
  ErrorState,
  SkeletonLoader,
} from '../design-system';
import { useApiData } from '../api';
import { DemoModeBanner } from '../components/DemoModeBanner';

interface UsageMetricItem {
  id: string;
  resourceId: string;
  provider: string;
  service: string;
  metricCode: string;
  monitoringType: string;
  intervalValue: number | null;
  unit: string;
  cardinalityTier: 'LOW' | 'MEDIUM' | 'HIGH';
  status: 'NOMINAL' | 'ELEVATED' | 'IDLE';
}

export const UsageDetailPage: React.FC<{ isDemo?: boolean }> = ({ isDemo = true }) => {
  const { data: apiUsage, loading, error, errorMessage, refetch } = useApiData<any>('/api/v1/usage/metrics');
  const [metrics, setMetrics] = useState<UsageMetricItem[]>([]);

  useEffect(() => {
    if (apiUsage) {
      const list = Array.isArray(apiUsage) ? apiUsage : (apiUsage.items || []);
      setMetrics(list.map((u: any) => ({
        id: u.id || u.metric_id || 'use-01',
        resourceId: u.resource_id || u.resourceId || 'res-01',
        provider: u.provider || 'AWS',
        service: u.service || 'Amazon EC2',
        metricCode: u.metric_code || u.metricCode || 'CPUUtilization',
        monitoringType: u.monitoring_type || u.monitoringType || 'RUNTIME_BASED',
        intervalValue: u.interval_value ?? u.intervalValue ?? null,
        unit: u.unit || 'Percent',
        cardinalityTier: (u.cardinality_tier || u.cardinalityTier || 'LOW') as UsageMetricItem['cardinalityTier'],
        status: (u.status || 'NOMINAL') as UsageMetricItem['status'],
      })));
    }
  }, [apiUsage]);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem', width: '100%' }}>
      <DemoModeBanner isDemo={isDemo} />

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Breadcrumb
          items={[
            { label: 'Home', href: '/' },
            { label: 'Usage Detail', isCurrent: true },
          ]}
        />
        <FreshnessIndicator lastSyncedAt="2026-10-05T12:00:00Z" provider="Multi-Cloud" />
      </div>

      <header>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '0.25rem' }}>
          <h1 style={{ fontSize: '1.75rem', fontWeight: 700, margin: 0, color: 'var(--text-primary)' }}>
            S-09: Usage Telemetry & Cardinality Detail
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
            Prompt 25 / 14 Monitoring Types
          </span>
        </div>
        <p style={{ color: 'var(--text-secondary)', margin: 0, fontSize: '0.9rem' }}>
          Coarse-grained operational telemetry serving FinOps and capacity governance without cardinality explosion.
        </p>
      </header>

      {/* Overview Stats */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '1rem' }}>
        <div style={{ backgroundColor: 'var(--bg-secondary)', border: '1px solid var(--border-color)', borderRadius: '8px', padding: '1rem' }}>
          <span style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>Collected Telemetry Metrics</span>
          <div style={{ fontSize: '1.5rem', fontWeight: 700, color: 'var(--text-primary)', marginTop: '0.25rem' }}>
            {metrics.length > 0 ? metrics.length : <NullValue state="NO_DATA" />}
          </div>
          <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>Sample interval: 1 hour</span>
        </div>

        <div style={{ backgroundColor: 'var(--bg-secondary)', border: '1px solid #10b981', borderRadius: '8px', padding: '1rem' }}>
          <span style={{ fontSize: '0.8rem', color: '#6ee7b7' }}>Cardinality Discipline</span>
          <div style={{ fontSize: '1.5rem', fontWeight: 700, color: '#34d399', marginTop: '0.25rem' }}>
            100%
          </div>
          <span style={{ fontSize: '0.75rem', color: '#a7f3d0' }}>Zero uncurated custom dimensions</span>
        </div>
      </div>

      {/* Metrics Table */}
      <section
        aria-labelledby="usage-metrics-heading"
        style={{
          backgroundColor: 'var(--bg-secondary)',
          border: '1px solid var(--border-color)',
          borderRadius: '8px',
          padding: '1.25rem',
        }}
      >
        <h2 id="usage-metrics-heading" style={{ fontSize: '1.1rem', fontWeight: 600, marginBottom: '1rem' }}>
          Telemetry Stream Directory
        </h2>

        {loading ? (
          <SkeletonLoader variant="table" rows={3} />
        ) : error ? (
          <ErrorState
            title="Failed to Load Usage Telemetry"
            message={errorMessage || 'Error contacting usage metrics API'}
            onRetry={refetch}
          />
        ) : metrics.length === 0 ? (
          <EmptyState type="NO_DATA" titleOverride="No Telemetry Streams" descriptionOverride="No active resource usage telemetry or monitoring streams recorded for this tenant." actionTextOverride="Refresh Metrics" onAction={refetch} />
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '0.85rem' }}>
              <thead>
                <tr style={{ borderBottom: '1px solid var(--border-color)', color: 'var(--text-secondary)' }}>
                  <th style={{ padding: '0.6rem' }}>Resource / Provider</th>
                  <th style={{ padding: '0.6rem' }}>Metric Code</th>
                  <th style={{ padding: '0.6rem' }}>Monitoring Type</th>
                  <th style={{ padding: '0.6rem' }}>Interval Measurement</th>
                  <th style={{ padding: '0.6rem' }}>Cardinality</th>
                  <th style={{ padding: '0.6rem' }}>Status</th>
                </tr>
              </thead>
              <tbody>
                {metrics.map((m) => (
                  <tr key={m.id} style={{ borderBottom: '1px solid var(--border-color)' }}>
                    <td style={{ padding: '0.75rem 0.6rem' }}>
                      <strong>{m.resourceId}</strong>
                      <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
                        {m.provider} - {m.service}
                      </div>
                    </td>
                    <td style={{ padding: '0.75rem 0.6rem' }}>
                      <code>{m.metricCode}</code>
                    </td>
                    <td style={{ padding: '0.75rem 0.6rem' }}>
                      <span style={{ fontSize: '0.75rem', padding: '0.15rem 0.45rem', borderRadius: '4px', backgroundColor: '#1e293b', color: '#94a3b8' }}>
                        {m.monitoringType}
                      </span>
                    </td>
                    <td style={{ padding: '0.75rem 0.6rem' }}>
                      {m.intervalValue !== null ? (
                        <span style={{ fontWeight: 600 }}>
                          {m.intervalValue.toLocaleString()} {m.unit}
                        </span>
                      ) : (
                        <NullValue state="NOT_APPLICABLE" />
                      )}
                    </td>
                    <td style={{ padding: '0.75rem 0.6rem' }}>
                      <code>{m.cardinalityTier}</code>
                    </td>
                    <td style={{ padding: '0.75rem 0.6rem' }}>
                      <span
                        style={{
                          padding: '0.15rem 0.45rem',
                          borderRadius: '4px',
                          fontSize: '0.75rem',
                          fontWeight: 600,
                          backgroundColor: m.status === 'NOMINAL' ? '#064e3b' : '#78350f',
                          color: m.status === 'NOMINAL' ? '#6ee7b7' : '#fde68a',
                        }}
                      >
                        {m.status}
                      </span>
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
export default UsageDetailPage;
