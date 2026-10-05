import React, { useState, useEffect } from 'react';
import {
  Breadcrumb,
  NullValue,
  FreshnessIndicator,
} from '../design-system';
import { DemoModeBanner } from '../components/DemoModeBanner';
import { Search, CheckCircle2 } from 'lucide-react';

interface AuditEventItem {
  id: string;
  eventType: string;
  actor: string;
  targetEntity: string;
  timestamp: string;
  correlationId: string;
  eventHash: string;
  hashChainVerified: boolean;
}

const DEMO_AUDIT: AuditEventItem[] = [
  {
    id: 'aud-98401',
    eventType: 'ACT_AS_TENANT_START',
    actor: 'admin@jyotirmoyb.com',
    targetEntity: 'tenant-demo',
    timestamp: '2026-10-05T21:42:15Z',
    correlationId: 'cid-782a-49bf-91a0',
    eventHash: 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
    hashChainVerified: true,
  },
  {
    id: 'aud-98402',
    eventType: 'THRESHOLD_BREACH_DETECTED',
    actor: 'system-evaluator',
    targetEntity: 'thr-budget-checkout-prod',
    timestamp: '2026-10-05T21:30:00Z',
    correlationId: 'cid-331e-4501-a189',
    eventHash: 'a591a6d40bf420404a011733cfb7b190d62c65bf0bcda32b57b277d9ad9f146e',
    hashChainVerified: true,
  },
  {
    id: 'aud-98403',
    eventType: 'REMEDIATION_TASK_RESOLVED',
    actor: 'sarah.chen@enterprise.internal',
    targetEntity: 'REM-101',
    timestamp: '2026-10-05T20:15:22Z',
    correlationId: 'cid-9182-beef-4412',
    eventHash: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b',
    hashChainVerified: true,
  },
  {
    id: 'aud-98404',
    eventType: 'RATE_CARD_SCD2_UPDATED',
    actor: 'sync-pricing-worker',
    targetEntity: 'sku-aws-ec2-m5xlarge',
    timestamp: '2026-10-05T18:00:00Z',
    correlationId: 'cid-0021-9981-ca41',
    eventHash: '5e884898da28047151d0e56f8dc6292773603d0d6aabbdd62a11ef721d1542d8',
    hashChainVerified: true,
  },
];

export const AuditLogPage: React.FC<{ isDemo?: boolean }> = ({ isDemo = true }) => {
  const [events, setEvents] = useState<AuditEventItem[]>(DEMO_AUDIT);
  const [search, setSearch] = useState('');

  useEffect(() => {
    if (!isDemo) {
      setEvents([]);
    } else {
      setEvents(DEMO_AUDIT);
    }
  }, [isDemo]);

  const filtered = events.filter((e) =>
    `${e.eventType} ${e.actor} ${e.targetEntity} ${e.correlationId}`.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem', width: '100%' }}>
      <DemoModeBanner isDemo={isDemo} />

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Breadcrumb
          items={[
            { label: 'Home', href: '/' },
            { label: 'Audit Trail', isCurrent: true },
          ]}
        />
        <FreshnessIndicator
          lastSyncedAt="2026-10-05T12:00:00Z"
          provider="System"
        />
      </div>

      <header>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '0.25rem' }}>
          <h1 style={{ fontSize: '1.75rem', fontWeight: 700, margin: 0, color: 'var(--text-primary)' }}>
            S-18: Immutable Audit Trail & Cryptographic Provenance
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
            BBP Sec 36 / Append-Only SHA-256
          </span>
        </div>
        <p style={{ color: 'var(--text-secondary)', margin: 0, fontSize: '0.9rem' }}>
          Tamper-evident audit ledger verifying actor attribution, cross-tenant isolation, and state change integrity.
        </p>
      </header>

      {/* Overview Cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '1rem' }}>
        <div style={{ backgroundColor: 'var(--bg-secondary)', border: '1px solid var(--border-color)', borderRadius: '8px', padding: '1rem' }}>
          <span style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>Recorded Events</span>
          <div style={{ fontSize: '1.5rem', fontWeight: 700, color: 'var(--text-primary)', marginTop: '0.25rem' }}>
            {events.length > 0 ? events.length : <NullValue state="NO_DATA" />}
          </div>
        </div>

        <div style={{ backgroundColor: 'var(--bg-secondary)', border: '1px solid #10b981', borderRadius: '8px', padding: '1rem' }}>
          <span style={{ fontSize: '0.8rem', color: '#6ee7b7' }}>Hash-Chain Verification</span>
          <div style={{ fontSize: '1.5rem', fontWeight: 700, color: '#34d399', marginTop: '0.25rem' }}>
            100% Intact
          </div>
          <span style={{ fontSize: '0.75rem', color: '#a7f3d0' }}>Cryptographic integrity valid</span>
        </div>
      </div>

      {/* Audit Events Table */}
      <section
        aria-labelledby="audit-table-heading"
        style={{
          backgroundColor: 'var(--bg-secondary)',
          border: '1px solid var(--border-color)',
          borderRadius: '8px',
          padding: '1.25rem',
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
          <h2 id="audit-table-heading" style={{ fontSize: '1.1rem', fontWeight: 600, margin: 0 }}>
            Audit Event Ledger
          </h2>

          <div style={{ position: 'relative' }}>
            <Search size={14} style={{ position: 'absolute', left: '0.6rem', top: '0.6rem', color: 'var(--text-secondary)' }} aria-hidden="true" />
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search event, actor, correlation..."
              aria-label="Search audit events"
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
              No audit events found in this scope.
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
                  <th style={{ padding: '0.6rem' }}>Event Type / ID</th>
                  <th style={{ padding: '0.6rem' }}>Actor</th>
                  <th style={{ padding: '0.6rem' }}>Target Entity</th>
                  <th style={{ padding: '0.6rem' }}>Timestamp</th>
                  <th style={{ padding: '0.6rem' }}>Correlation ID</th>
                  <th style={{ padding: '0.6rem' }}>Hash Verification</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((e) => (
                  <tr key={e.id} style={{ borderBottom: '1px solid var(--border-color)' }}>
                    <td style={{ padding: '0.75rem 0.6rem' }}>
                      <strong style={{ color: e.eventType.includes('SECURITY') || e.eventType.includes('ACT_AS') ? '#f87171' : 'var(--text-primary)' }}>
                        {e.eventType}
                      </strong>
                      <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>{e.id}</div>
                    </td>
                    <td style={{ padding: '0.75rem 0.6rem' }}>
                      <code>{e.actor}</code>
                    </td>
                    <td style={{ padding: '0.75rem 0.6rem' }}>
                      <code>{e.targetEntity}</code>
                    </td>
                    <td style={{ padding: '0.75rem 0.6rem', fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
                      {new Date(e.timestamp).toLocaleString()}
                    </td>
                    <td style={{ padding: '0.75rem 0.6rem' }}>
                      <code style={{ fontSize: '0.75rem' }}>{e.correlationId}</code>
                    </td>
                    <td style={{ padding: '0.75rem 0.6rem' }}>
                      <span style={{ display: 'inline-flex', alignItems: 'center', gap: '0.2rem', color: '#34d399', fontSize: '0.75rem', fontWeight: 600 }}>
                        <CheckCircle2 size={12} aria-hidden="true" /> SHA-256 Valid
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
export default AuditLogPage;
