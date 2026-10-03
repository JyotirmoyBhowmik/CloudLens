import React, { useState } from 'react';
import { Clock, CheckCircle2, AlertTriangle, AlertOctagon } from 'lucide-react';
import { FreshnessState, FRESHNESS_STATES } from './tokens';

export interface FreshnessIndicatorProps {
  lastSyncedAt: string | Date;
  provider?: string;
  jobId?: string;
  maxFreshHours?: number;
  maxDelayedHours?: number;
  showPopover?: boolean;
  className?: string;
}

/**
 * Data Freshness Indicator Component
 * Enforces BBP Section 31: "Implement the freshness indicator component used on every provider-derived value."
 */
export const FreshnessIndicator: React.FC<FreshnessIndicatorProps> = ({
  lastSyncedAt,
  provider = 'CloudLens Aggregator',
  jobId,
  maxFreshHours = 4,
  maxDelayedHours = 24,
  showPopover = true,
  className = '',
}) => {
  const [isOpen, setIsOpen] = useState(false);

  const syncDate =
    typeof lastSyncedAt === 'string' ? new Date(lastSyncedAt) : lastSyncedAt;
  const now = new Date();
  const diffMs = Math.max(0, now.getTime() - syncDate.getTime());
  const diffMinutes = Math.floor(diffMs / (1000 * 60));
  const diffHours = Math.floor(diffMinutes / 60);

  let state: FreshnessState = 'FRESH';
  if (diffHours >= maxDelayedHours) {
    state = 'STALE';
  } else if (diffHours >= maxFreshHours) {
    state = 'DELAYED';
  }

  const config = FRESHNESS_STATES[state];

  const getRelativeText = (): string => {
    if (diffMinutes < 1) return 'Synced just now';
    if (diffMinutes < 60) return `Synced ${diffMinutes}m ago`;
    if (diffHours < 24) return `Synced ${diffHours}h ago`;
    const days = Math.floor(diffHours / 24);
    return `Synced ${days}d ago`;
  };

  const renderStatusIcon = () => {
    switch (state) {
      case 'FRESH':
        return <CheckCircle2 size={12} color="#34d399" aria-hidden="true" />;
      case 'DELAYED':
        return <AlertTriangle size={12} color="#fbbf24" aria-hidden="true" />;
      case 'STALE':
      default:
        return <AlertOctagon size={12} color="#f87171" aria-hidden="true" />;
    }
  };

  return (
    <div
      className={`freshness-indicator-container ${className}`}
      style={{ position: 'relative', display: 'inline-block' }}
    >
      <button
        type="button"
        aria-label={`${config.label} - ${getRelativeText()} from ${provider}`}
        aria-haspopup="dialog"
        aria-expanded={isOpen}
        onClick={() => showPopover && setIsOpen(!isOpen)}
        onKeyDown={(e) => {
          if (e.key === 'Escape') setIsOpen(false);
        }}
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: '0.35rem',
          padding: '0.2rem 0.5rem',
          fontSize: '0.75rem',
          fontWeight: 500,
          borderRadius: '9999px',
          backgroundColor: config.bgHex,
          border: '1px solid var(--border-color)',
          color: 'var(--text-secondary)',
          cursor: showPopover ? 'pointer' : 'default',
          transition: 'all 0.15s ease',
        }}
      >
        <span
          style={{
            width: '6px',
            height: '6px',
            borderRadius: '50%',
            backgroundColor: config.colorHex,
            boxShadow: state === 'FRESH' ? `0 0 6px ${config.colorHex}` : 'none',
          }}
        />
        <Clock size={12} aria-hidden="true" style={{ opacity: 0.8 }} />
        <span style={{ color: 'var(--text-primary)' }}>{getRelativeText()}</span>
      </button>

      {/* Accessible Detail Popover */}
      {showPopover && isOpen && (
        <div
          role="dialog"
          aria-label="Data Freshness Details"
          style={{
            position: 'absolute',
            top: 'calc(100% + 6px)',
            left: 0,
            zIndex: 50,
            width: '280px',
            backgroundColor: 'var(--bg-secondary)',
            border: '1px solid var(--border-color)',
            borderRadius: '8px',
            padding: '1rem',
            boxShadow: '0 10px 25px -5px rgba(0, 0, 0, 0.5)',
            fontSize: '0.8125rem',
          }}
        >
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              marginBottom: '0.75rem',
              borderBottom: '1px solid var(--border-color)',
              paddingBottom: '0.5rem',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
              {renderStatusIcon()}
              <strong style={{ color: config.colorHex }}>{config.label}</strong>
            </div>
            <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
              SLA: &lt;{maxFreshHours}h
            </span>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
            <div>
              <span style={{ color: 'var(--text-secondary)' }}>Provider: </span>
              <strong>{provider}</strong>
            </div>
            <div>
              <span style={{ color: 'var(--text-secondary)' }}>UTC Time: </span>
              <code style={{ fontSize: '0.75rem' }}>{syncDate.toUTCString()}</code>
            </div>
            <div>
              <span style={{ color: 'var(--text-secondary)' }}>Local Time: </span>
              <code style={{ fontSize: '0.75rem' }}>{syncDate.toLocaleString()}</code>
            </div>
            {jobId && (
              <div>
                <span style={{ color: 'var(--text-secondary)' }}>Job Run ID: </span>
                <code style={{ fontSize: '0.75rem' }}>{jobId}</code>
              </div>
            )}
          </div>

          <button
            type="button"
            onClick={() => setIsOpen(false)}
            aria-label="Close freshness details popover"
            style={{
              marginTop: '0.75rem',
              width: '100%',
              padding: '0.3rem',
              borderRadius: '4px',
              border: '1px solid var(--border-color)',
              backgroundColor: 'transparent',
              color: 'var(--text-primary)',
              cursor: 'pointer',
              fontSize: '0.75rem',
            }}
          >
            Close
          </button>
        </div>
      )}
    </div>
  );
};
