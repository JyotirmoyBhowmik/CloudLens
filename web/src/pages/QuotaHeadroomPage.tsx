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
import { ShieldAlert, AlertTriangle, CheckCircle2, Clock, Search } from 'lucide-react';

interface QuotaItem {
  id: string;
  provider: 'AWS' | 'AZURE' | 'GCP' | 'OCI';
  service: string;
  quotaName: string;
  region: string;
  currentUsage: number | null;
  limit: number | null;
  unit: string;
  saturationPct: number | null;
  headroomState: 'NORMAL' | 'WARNING' | 'IMMINENT_BREACH' | 'NOT_SUPPORTED';
  daysToExhaustion: number | null;
  adjustable: boolean;
}

export const QuotaHeadroomPage: React.FC<{ isDemo?: boolean }> = ({ isDemo = true }) => {
  const { data: apiQuotas, loading, error, errorMessage, refetch } = useApiData<any>('/api/v1/quotas');
  const [quotas, setQuotas] = useState<QuotaItem[]>([]);
  const [selectedProvider, setSelectedProvider] = useState<string>('ALL');
  const [selectedState, setSelectedState] = useState<string>('ALL');
  const [searchQuery, setSearchQuery] = useState<string>('');

  useEffect(() => {
    if (apiQuotas) {
      const list = Array.isArray(apiQuotas) ? apiQuotas : (apiQuotas.items || []);
      setQuotas(list.map((q: any) => ({
        id: q.id || q.quota_id || 'q-default',
        provider: (q.provider || 'AWS') as QuotaItem['provider'],
        service: q.service_name || q.service || 'Cloud Service',
        quotaName: q.quota_name || q.quotaName || 'Resource Limit',
        region: q.region || 'global',
        currentUsage: q.current_usage ?? q.currentUsage ?? null,
        limit: q.quota_limit ?? q.limit ?? null,
        unit: q.unit || 'units',
        saturationPct: q.saturation_pct ?? q.saturationPct ?? null,
        headroomState: (q.headroom_state || q.headroomState || 'NORMAL') as QuotaItem['headroomState'],
        daysToExhaustion: q.days_to_exhaustion ?? q.daysToExhaustion ?? null,
        adjustable: q.adjustable !== undefined ? q.adjustable : true,
      })));
    }
  }, [apiQuotas]);

  const filteredQuotas = quotas.filter((q) => {
    if (selectedProvider !== 'ALL' && q.provider !== selectedProvider) return false;
    if (selectedState !== 'ALL' && q.headroomState !== selectedState) return false;
    if (searchQuery) {
      const qText = `${q.service} ${q.quotaName} ${q.region}`.toLowerCase();
      if (!qText.includes(searchQuery.toLowerCase())) return false;
    }
    return true;
  });

  const breachCount = quotas.filter((q) => q.headroomState === 'IMMINENT_BREACH').length;
  const warningCount = quotas.filter((q) => q.headroomState === 'WARNING').length;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem', width: '100%' }}>
      <DemoModeBanner isDemo={isDemo} />

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Breadcrumb
          items={[
            { label: 'Home', href: '/' },
            { label: 'Quota & Headroom', isCurrent: true },
          ]}
        />
        <FreshnessIndicator lastSyncedAt="2026-10-05T12:00:00Z" provider="Multi-Cloud" />
      </div>

      <header>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '0.25rem' }}>
          <h1 style={{ fontSize: '1.75rem', fontWeight: 700, margin: 0, color: 'var(--text-primary)' }}>
            Service Quotas & Headroom Console
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
            Quota Monitoring
          </span>
        </div>
        <p style={{ color: 'var(--text-secondary)', margin: 0, fontSize: '0.9rem' }}>
          Monitor provider service limits, project consumption burn rates, and track lead-time to exhaustion before deployments fail.
        </p>
      </header>

      {/* KPI Highlight Panels */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '1rem' }}>
        <div style={{ backgroundColor: 'var(--bg-secondary)', border: '1px solid var(--border-color)', borderRadius: '8px', padding: '1rem' }}>
          <span style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>Tracked Quotas</span>
          <div style={{ fontSize: '1.5rem', fontWeight: 700, color: 'var(--text-primary)', marginTop: '0.25rem' }}>
            {quotas.length > 0 ? quotas.length : <NullValue state="NO_DATA" />}
          </div>
          <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>Across AWS, Azure, GCP, OCI</span>
        </div>

        <div style={{ backgroundColor: 'var(--bg-secondary)', border: '1px solid #ef4444', borderRadius: '8px', padding: '1rem' }}>
          <span style={{ fontSize: '0.8rem', color: '#f87171' }}>Imminent Breach (&lt;14 Days)</span>
          <div style={{ fontSize: '1.5rem', fontWeight: 700, color: '#f87171', marginTop: '0.25rem' }}>
            {quotas.length > 0 ? breachCount : <NullValue state="ZERO" />}
          </div>
          <span style={{ fontSize: '0.75rem', color: '#fca5a5' }}>Requires urgent increase escalation</span>
        </div>

        <div style={{ backgroundColor: 'var(--bg-secondary)', border: '1px solid #f59e0b', borderRadius: '8px', padding: '1rem' }}>
          <span style={{ fontSize: '0.8rem', color: '#fbbf24' }}>Warning Saturation (&gt;80%)</span>
          <div style={{ fontSize: '1.5rem', fontWeight: 700, color: '#fbbf24', marginTop: '0.25rem' }}>
            {quotas.length > 0 ? warningCount : <NullValue state="ZERO" />}
          </div>
          <span style={{ fontSize: '0.75rem', color: '#fde68a' }}>Approaching service ceiling</span>
        </div>
      </div>

      {/* Filter and Table Section */}
      <section
        aria-labelledby="quotas-list-heading"
        style={{
          backgroundColor: 'var(--bg-secondary)',
          border: '1px solid var(--border-color)',
          borderRadius: '8px',
          padding: '1.25rem',
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem', flexWrap: 'wrap', gap: '0.75rem' }}>
          <h2 id="quotas-list-heading" style={{ fontSize: '1.1rem', fontWeight: 600, margin: 0 }}>
            Active Quota Headroom Inventory
          </h2>

          <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
            <div style={{ position: 'relative' }}>
              <Search size={14} style={{ position: 'absolute', left: '0.6rem', top: '0.6rem', color: 'var(--text-secondary)' }} aria-hidden="true" />
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search quota..."
                aria-label="Search quotas"
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

            <select
              value={selectedProvider}
              onChange={(e) => setSelectedProvider(e.target.value)}
              aria-label="Filter by provider"
              style={{
                padding: '0.4rem 0.6rem',
                fontSize: '0.8rem',
                borderRadius: '6px',
                border: '1px solid var(--border-color)',
                backgroundColor: 'var(--bg-primary)',
                color: 'var(--text-primary)',
              }}
            >
              <option value="ALL">All Providers</option>
              <option value="AWS">AWS</option>
              <option value="AZURE">Azure</option>
              <option value="GCP">GCP</option>
              <option value="OCI">OCI</option>
            </select>

            <select
              value={selectedState}
              onChange={(e) => setSelectedState(e.target.value)}
              aria-label="Filter by headroom state"
              style={{
                padding: '0.4rem 0.6rem',
                fontSize: '0.8rem',
                borderRadius: '6px',
                border: '1px solid var(--border-color)',
                backgroundColor: 'var(--bg-primary)',
                color: 'var(--text-primary)',
              }}
            >
              <option value="ALL">All States</option>
              <option value="IMMINENT_BREACH">Imminent Breach</option>
              <option value="WARNING">Warning</option>
              <option value="NORMAL">Normal</option>
              <option value="NOT_SUPPORTED">Not Supported</option>
            </select>
          </div>
        </div>

        {loading ? (
          <SkeletonLoader variant="table" rows={3} />
        ) : error ? (
          <ErrorState
            title="Failed to Load Quotas"
            message={errorMessage || 'Error contacting service quotas API'}
            onRetry={refetch}
          />
        ) : filteredQuotas.length === 0 ? (
          <EmptyState type="NO_DATA" titleOverride="No Quotas Discovered" descriptionOverride="No cloud service quotas or limits tracked for this tenant." actionTextOverride="Refresh Quotas" onAction={refetch} />
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '0.85rem' }}>
              <thead>
                <tr style={{ borderBottom: '1px solid var(--border-color)', color: 'var(--text-secondary)' }}>
                  <th style={{ padding: '0.6rem' }}>Provider / Service</th>
                  <th style={{ padding: '0.6rem' }}>Quota Name & Scope</th>
                  <th style={{ padding: '0.6rem' }}>Usage / Limit</th>
                  <th style={{ padding: '0.6rem' }}>Saturation</th>
                  <th style={{ padding: '0.6rem' }}>Headroom State</th>
                  <th style={{ padding: '0.6rem' }}>Exhaustion Lead-Time</th>
                  <th style={{ padding: '0.6rem' }}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {filteredQuotas.map((q) => {
                  return (
                    <tr key={q.id} style={{ borderBottom: '1px solid var(--border-color)' }}>
                      <td style={{ padding: '0.75rem 0.6rem' }}>
                        <strong>{q.provider}</strong>
                        <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>{q.service}</div>
                      </td>
                      <td style={{ padding: '0.75rem 0.6rem' }}>
                        <div>{q.quotaName}</div>
                        <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>Region: {q.region}</div>
                      </td>
                      <td style={{ padding: '0.75rem 0.6rem' }}>
                        {q.currentUsage !== null && q.limit !== null ? (
                          <span>
                            {q.currentUsage} / {q.limit} {q.unit}
                          </span>
                        ) : (
                          <NullValue state="NOT_SUPPORTED" />
                        )}
                      </td>
                      <td style={{ padding: '0.75rem 0.6rem' }}>
                        {q.saturationPct !== null ? (
                          <span style={{ fontWeight: 600, color: q.saturationPct >= 90 ? '#f87171' : q.saturationPct >= 80 ? '#f59e0b' : 'var(--text-primary)' }}>
                            {q.saturationPct.toFixed(1)}%
                          </span>
                        ) : (
                          <NullValue state="NOT_SUPPORTED" />
                        )}
                      </td>
                      <td style={{ padding: '0.75rem 0.6rem' }}>
                        {q.headroomState === 'IMMINENT_BREACH' ? (
                          <span style={{ display: 'inline-flex', alignItems: 'center', gap: '0.25rem', padding: '0.15rem 0.5rem', borderRadius: '4px', backgroundColor: '#7f1d1d', color: '#fca5a5', fontSize: '0.75rem', fontWeight: 600 }}>
                            <ShieldAlert size={12} aria-hidden="true" /> Imminent Breach
                          </span>
                        ) : q.headroomState === 'WARNING' ? (
                          <span style={{ display: 'inline-flex', alignItems: 'center', gap: '0.25rem', padding: '0.15rem 0.5rem', borderRadius: '4px', backgroundColor: '#78350f', color: '#fde68a', fontSize: '0.75rem', fontWeight: 600 }}>
                            <AlertTriangle size={12} aria-hidden="true" /> Warning
                          </span>
                        ) : q.headroomState === 'NORMAL' ? (
                          <span style={{ display: 'inline-flex', alignItems: 'center', gap: '0.25rem', padding: '0.15rem 0.5rem', borderRadius: '4px', backgroundColor: '#064e3b', color: '#6ee7b7', fontSize: '0.75rem', fontWeight: 600 }}>
                            <CheckCircle2 size={12} aria-hidden="true" /> Normal
                          </span>
                        ) : (
                          <NullValue state="NOT_SUPPORTED" />
                        )}
                      </td>
                      <td style={{ padding: '0.75rem 0.6rem' }}>
                        {q.daysToExhaustion !== null ? (
                          <span style={{ display: 'inline-flex', alignItems: 'center', gap: '0.25rem', color: q.daysToExhaustion <= 7 ? '#f87171' : 'var(--text-secondary)' }}>
                            <Clock size={12} aria-hidden="true" /> &lt;{q.daysToExhaustion} days
                          </span>
                        ) : (
                          <NullValue state="NOT_APPLICABLE" />
                        )}
                      </td>
                      <td style={{ padding: '0.75rem 0.6rem' }}>
                        {q.adjustable ? (
                          <button
                            type="button"
                            aria-label={`Request increase for ${q.quotaName}`}
                            style={{
                              padding: '0.25rem 0.6rem',
                              borderRadius: '4px',
                              backgroundColor: '#0369a1',
                              color: '#ffffff',
                              border: 'none',
                              fontSize: '0.75rem',
                              fontWeight: 700,
                              cursor: 'pointer',
                            }}
                          >
                            Request Increase
                          </button>
                        ) : (
                          <NullValue state="NOT_APPLICABLE" />
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
};
export default QuotaHeadroomPage;
