import React, { useState } from 'react';
import {
  Clock,
  CheckCircle2,
  AlertTriangle,
  AlertOctagon,
  RefreshCw,
  Database,
  Layers,
  Activity,
  FileText,
} from 'lucide-react';
import { FreshnessSurfaceData, FreshnessSurfaceItemData } from './tokens';

export interface FreshnessSurfaceProps {
  data?: FreshnessSurfaceData;
  onRefresh?: () => void;
  compact?: boolean;
  className?: string;
}

const DEFAULT_FRESHNESS_DATA: FreshnessSurfaceData = {
  evaluated_at: new Date().toISOString(),
  has_staleness_warning: false,
  stale_count: 0,
  items: [
    {
      data_class: 'PRICING',
      label: 'Pricing Catalogue',
      stated_time_text: 'Pricing retrieved 3.5 hours ago',
      last_retrieved_at: new Date(Date.now() - 3.5 * 3600 * 1000).toISOString(),
      age_hours: 3.5,
      staleness_threshold_hours: 168.0,
      is_stale: false,
      provider: 'CloudLens Pricing Engine',
      status: 'FRESH',
    },
    {
      data_class: 'BILLING_ACTUALS',
      label: 'Provider Billing Data',
      stated_time_text: `Provider billing data through ${new Date(Date.now() - 86400000).toLocaleDateString()}`,
      last_retrieved_at: new Date(Date.now() - 8 * 3600 * 1000).toISOString(),
      age_hours: 8.0,
      staleness_threshold_hours: 24.0,
      is_stale: false,
      provider: 'FOCUS Invoiced Actuals',
      status: 'FRESH',
    },
    {
      data_class: 'USAGE_METRICS',
      label: 'Usage Telemetry',
      stated_time_text: 'Usage updated 45 minutes ago',
      last_retrieved_at: new Date(Date.now() - 45 * 60 * 1000).toISOString(),
      age_hours: 0.75,
      staleness_threshold_hours: 4.0,
      is_stale: false,
      provider: 'CloudLens Metric Collector',
      status: 'FRESH',
    },
    {
      data_class: 'INVENTORY',
      label: 'Inventory Discovery',
      stated_time_text: 'Inventory last synchronised 1.2 hours ago',
      last_retrieved_at: new Date(Date.now() - 1.2 * 3600 * 1000).toISOString(),
      age_hours: 1.2,
      staleness_threshold_hours: 6.0,
      is_stale: false,
      provider: 'Multi-Cloud Asset Sync',
      status: 'FRESH',
    },
  ],
};

const CLASS_ICONS: Record<string, React.ReactNode> = {
  PRICING: <Database size={14} aria-hidden="true" />,
  BILLING_ACTUALS: <FileText size={14} aria-hidden="true" />,
  USAGE_METRICS: <Activity size={14} aria-hidden="true" />,
  INVENTORY: <Layers size={14} aria-hidden="true" />,
};

/**
 * Data Freshness Surface Component (Prompt 40 Item 163).
 * Visualizes the 4 product-wide data freshness streams with prominent staleness warnings.
 */
export const FreshnessSurface: React.FC<FreshnessSurfaceProps> = ({
  data = DEFAULT_FRESHNESS_DATA,
  onRefresh,
  compact = false,
  className = '',
}) => {
  const [isOpen, setIsOpen] = useState(false);

  const hasWarning = data.has_staleness_warning || data.items.some((i) => i.is_stale);

  if (compact) {
    return (
      <div style={{ position: 'relative', display: 'inline-block' }} className={className}>
        <button
          type="button"
          aria-label={`Data Freshness Status: ${hasWarning ? 'Staleness warning active' : 'All streams fresh'}`}
          aria-haspopup="dialog"
          aria-expanded={isOpen}
          onClick={() => setIsOpen(!isOpen)}
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: '0.4rem',
            padding: '0.25rem 0.65rem',
            borderRadius: '9999px',
            backgroundColor: hasWarning ? 'rgba(239, 68, 68, 0.15)' : 'rgba(16, 185, 129, 0.15)',
            border: `1px solid ${hasWarning ? '#dc2626' : '#059669'}`,
            color: hasWarning ? '#f87171' : '#34d399',
            fontSize: '0.75rem',
            fontWeight: 600,
            cursor: 'pointer',
          }}
        >
          {hasWarning ? <AlertTriangle size={12} aria-hidden="true" /> : <Clock size={12} aria-hidden="true" />}
          <span>{hasWarning ? `${data.stale_count} Stale Stream(s)` : 'Estate Fresh'}</span>
        </button>

        {isOpen && (
          <div
            role="dialog"
            aria-label="Estate Data Freshness Surface"
            style={{
              position: 'absolute',
              top: 'calc(100% + 6px)',
              right: 0,
              zIndex: 80,
              width: '360px',
              backgroundColor: 'var(--bg-secondary, #1e293b)',
              border: '1px solid var(--border-color, #334155)',
              borderRadius: '8px',
              padding: '1rem',
              boxShadow: '0 10px 25px -5px rgba(0, 0, 0, 0.5)',
              fontSize: '0.8125rem',
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem' }}>
              <strong style={{ color: 'var(--text-primary, #f8fafc)' }}>Data Freshness Surface</strong>
              {onRefresh && (
                <button
                  type="button"
                  onClick={onRefresh}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '0.25rem',
                    background: 'transparent',
                    border: 'none',
                    color: 'var(--accent-blue, #38bdf8)',
                    cursor: 'pointer',
                    fontSize: '0.75rem',
                  }}
                >
                  <RefreshCw size={11} aria-hidden="true" />
                  <span>Sync</span>
                </button>
              )}
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.65rem' }}>
              {data.items.map((item) => (
                <FreshnessItemRow key={item.data_class} item={item} />
              ))}
            </div>
          </div>
        )}
      </div>
    );
  }

  return (
    <div
      className={`cloudlens-freshness-surface ${className}`}
      style={{
        backgroundColor: 'var(--bg-secondary, #1e293b)',
        border: '1px solid var(--border-color, #334155)',
        borderRadius: '10px',
        padding: '1.25rem',
        marginBottom: '1.25rem',
      }}
    >
      {/* Header */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginBottom: '1rem',
          borderBottom: '1px solid var(--border-color, #334155)',
          paddingBottom: '0.75rem',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <Clock size={18} color="var(--accent-blue, #38bdf8)" aria-hidden="true" />
          <h3 style={{ margin: 0, fontSize: '1rem', color: 'var(--text-primary, #f8fafc)' }}>
            Data Freshness Surface Across Product
          </h3>
        </div>
        {hasWarning ? (
          <span
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '0.35rem',
              padding: '0.25rem 0.6rem',
              borderRadius: '4px',
              backgroundColor: 'rgba(239, 68, 68, 0.15)',
              border: '1px solid #dc2626',
              color: '#f87171',
              fontSize: '0.75rem',
              fontWeight: 700,
            }}
          >
            <AlertOctagon size={13} aria-hidden="true" />
            <span>STALENESS WARNING ACTIVE</span>
          </span>
        ) : (
          <span
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '0.35rem',
              padding: '0.25rem 0.6rem',
              borderRadius: '4px',
              backgroundColor: 'rgba(52, 211, 153, 0.15)',
              border: '1px solid #059669',
              color: '#34d399',
              fontSize: '0.75rem',
              fontWeight: 700,
            }}
          >
            <CheckCircle2 size={13} aria-hidden="true" />
            <span>ALL DATA STREAMS FRESH</span>
          </span>
        )}
      </div>

      {/* 4 Streams Grid */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))',
          gap: '1rem',
        }}
      >
        {data.items.map((item) => (
          <FreshnessItemCard key={item.data_class} item={item} />
        ))}
      </div>
    </div>
  );
};

const FreshnessItemCard: React.FC<{ item: FreshnessSurfaceItemData }> = ({ item }) => {
  return (
    <div
      style={{
        padding: '0.875rem 1rem',
        borderRadius: '8px',
        backgroundColor: item.is_stale ? 'rgba(239, 68, 68, 0.08)' : 'rgba(15, 23, 42, 0.5)',
        border: `1px solid ${item.is_stale ? '#dc2626' : 'var(--border-color, #334155)'}`,
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.35rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', color: 'var(--accent-blue, #38bdf8)' }}>
          {CLASS_ICONS[item.data_class]}
          <strong style={{ fontSize: '0.8125rem', color: 'var(--text-primary, #f8fafc)' }}>
            {item.label}
          </strong>
        </div>
        <span
          style={{
            fontSize: '0.7rem',
            fontWeight: 700,
            color: item.is_stale ? '#f87171' : '#34d399',
          }}
        >
          {item.status}
        </span>
      </div>

      <div style={{ fontSize: '0.875rem', fontWeight: 600, color: 'var(--text-primary, #f8fafc)', margin: '0.25rem 0' }}>
        {item.stated_time_text}
      </div>

      <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary, #94a3b8)', marginTop: '0.25rem' }}>
        SLA Threshold: &lt;{item.staleness_threshold_hours}h | Elapsed: {item.age_hours.toFixed(1)}h
      </div>

      {item.is_stale && (
        <div
          style={{
            marginTop: '0.5rem',
            padding: '0.35rem 0.5rem',
            borderRadius: '4px',
            backgroundColor: 'rgba(239, 68, 68, 0.2)',
            color: '#f87171',
            fontSize: '0.7rem',
            fontWeight: 600,
          }}
        >
          Warning: Last retrieval {new Date(item.last_retrieved_at).toISOString()}
        </div>
      )}
    </div>
  );
};

const FreshnessItemRow: React.FC<{ item: FreshnessSurfaceItemData }> = ({ item }) => {
  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: '0.15rem',
        padding: '0.4rem 0.6rem',
        borderRadius: '6px',
        backgroundColor: item.is_stale ? 'rgba(239, 68, 68, 0.1)' : 'rgba(15, 23, 42, 0.4)',
        border: `1px solid ${item.is_stale ? '#dc2626' : 'var(--border-color, #334155)'}`,
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-primary, #f8fafc)' }}>
          {item.label}
        </span>
        <span style={{ fontSize: '0.7rem', fontWeight: 700, color: item.is_stale ? '#f87171' : '#34d399' }}>
          {item.status}
        </span>
      </div>
      <div style={{ fontSize: '0.75rem', color: '#cbd5e1' }}>{item.stated_time_text}</div>
      {item.is_stale && (
        <span style={{ fontSize: '0.6875rem', color: '#f87171' }}>
          Exceeds {item.staleness_threshold_hours}h SLA limit
        </span>
      )}
    </div>
  );
};
