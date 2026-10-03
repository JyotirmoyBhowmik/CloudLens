import React, { useState } from 'react';
import {
  Info,
  Gift,
  DollarSign,
  TrendingUp,
  RefreshCw,
  AlertOctagon,
  Check,
  X,
  ShieldCheck,
} from 'lucide-react';
import { ContextualAlertData, ContextualAlertType } from './tokens';

export interface ContextualAlertBannerProps {
  alert: ContextualAlertData;
  onAcknowledge?: (alertId: string, actor: string, note?: string) => Promise<void> | void;
  onDismiss?: (alertId: string) => Promise<void> | void;
  currentUser?: string;
  className?: string;
}

const ALERT_CONFIG: Record<
  ContextualAlertType,
  { label: string; bg: string; border: string; color: string; icon: React.ReactNode }
> = {
  COST_INFORMATION: {
    label: 'Cost Information',
    bg: 'rgba(56, 189, 248, 0.1)',
    border: '#0284c7',
    color: '#38bdf8',
    icon: <Info size={16} aria-hidden="true" />,
  },
  FREE_TIER: {
    label: 'Free Tier',
    bg: 'rgba(52, 211, 153, 0.1)',
    border: '#059669',
    color: '#34d399',
    icon: <Gift size={16} aria-hidden="true" />,
  },
  BUDGET: {
    label: 'Budget Alert',
    bg: 'rgba(251, 191, 36, 0.1)',
    border: '#d97706',
    color: '#fbbf24',
    icon: <DollarSign size={16} aria-hidden="true" />,
  },
  FORECAST: {
    label: 'Forecast Trend',
    bg: 'rgba(249, 115, 22, 0.1)',
    border: '#ea580c',
    color: '#fb923c',
    icon: <TrendingUp size={16} aria-hidden="true" />,
  },
  PRICING_CHANGE: {
    label: 'Pricing Change',
    bg: 'rgba(168, 85, 247, 0.1)',
    border: '#9333ea',
    color: '#c084fc',
    icon: <RefreshCw size={16} aria-hidden="true" />,
  },
  PRICING_UNAVAILABLE: {
    label: 'Pricing Unavailable',
    bg: 'rgba(239, 68, 68, 0.1)',
    border: '#dc2626',
    color: '#f87171',
    icon: <AlertOctagon size={16} aria-hidden="true" />,
  },
};

/**
 * Inline Contextual Alert Component (Prompt 40 / Prompt 31 Section 4).
 * Supports the 6 canonical alert types with visibility, acknowledgement, and audit trail.
 */
export const ContextualAlertBanner: React.FC<ContextualAlertBannerProps> = ({
  alert,
  onAcknowledge,
  onDismiss,
  currentUser = 'finops_operator',
  className = '',
}) => {
  const [isAcknowledging, setIsAcknowledging] = useState(false);
  const [ackNote, setAckNote] = useState('');
  const [showNoteInput, setShowNoteInput] = useState(false);
  const [localAcknowledged, setLocalAcknowledged] = useState(alert.is_acknowledged || false);
  const [acknowledgedBy, setAcknowledgedBy] = useState(alert.acknowledged_by || null);

  const cfg = ALERT_CONFIG[alert.alert_type] || ALERT_CONFIG.COST_INFORMATION;

  const handleAcknowledge = async () => {
    setIsAcknowledging(true);
    try {
      if (onAcknowledge) {
        await onAcknowledge(alert.id, currentUser, ackNote || undefined);
      }
      setLocalAcknowledged(true);
      setAcknowledgedBy(currentUser);
      setShowNoteInput(false);
    } finally {
      setIsAcknowledging(false);
    }
  };

  return (
    <div
      role="region"
      aria-label={`${cfg.label}: ${alert.title}`}
      className={`cloudlens-contextual-alert alert-${alert.alert_type.toLowerCase()} ${className}`}
      style={{
        display: 'flex',
        alignItems: 'flex-start',
        gap: '0.875rem',
        padding: '0.875rem 1.125rem',
        borderRadius: '8px',
        backgroundColor: cfg.bg,
        border: `1px solid ${cfg.border}`,
        color: 'var(--text-primary, #f8fafc)',
        fontSize: '0.8125rem',
        position: 'relative',
        marginBottom: '0.75rem',
      }}
    >
      {/* Alert Icon */}
      <span style={{ color: cfg.color, marginTop: '2px', display: 'flex', alignItems: 'center' }}>
        {cfg.icon}
      </span>

      {/* Content */}
      <div style={{ flex: 1 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.25rem' }}>
          <span
            style={{
              padding: '0.15rem 0.4rem',
              borderRadius: '4px',
              backgroundColor: cfg.border,
              color: '#ffffff',
              fontSize: '0.7rem',
              fontWeight: 700,
              textTransform: 'uppercase',
            }}
          >
            {cfg.label}
          </span>
          <strong style={{ fontSize: '0.875rem', color: 'var(--text-primary, #f8fafc)' }}>
            {alert.title}
          </strong>
        </div>

        <p style={{ margin: '0 0 0.5rem', color: '#cbd5e1', lineHeight: 1.4 }}>
          {alert.message}
        </p>

        {/* Acknowledgement Status or Form */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', flexWrap: 'wrap' }}>
          {localAcknowledged ? (
            <span
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '0.3rem',
                color: '#34d399',
                fontSize: '0.75rem',
                fontWeight: 600,
              }}
            >
              <ShieldCheck size={14} aria-hidden="true" />
              <span>Acknowledged by {acknowledgedBy || currentUser} (Audited)</span>
            </span>
          ) : (
            <>
              {showNoteInput ? (
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginTop: '0.25rem' }}>
                  <input
                    type="text"
                    placeholder="Optional acknowledgement note..."
                    value={ackNote}
                    onChange={(e) => setAckNote(e.target.value)}
                    style={{
                      padding: '0.25rem 0.5rem',
                      fontSize: '0.75rem',
                      borderRadius: '4px',
                      border: '1px solid var(--border-color, #334155)',
                      backgroundColor: 'rgba(15, 23, 42, 0.6)',
                      color: '#ffffff',
                    }}
                  />
                  <button
                    type="button"
                    disabled={isAcknowledging}
                    onClick={handleAcknowledge}
                    style={{
                      padding: '0.25rem 0.6rem',
                      fontSize: '0.75rem',
                      fontWeight: 600,
                      borderRadius: '4px',
                      border: 'none',
                      backgroundColor: cfg.color,
                      color: '#0f172a',
                      cursor: 'pointer',
                    }}
                  >
                    Confirm
                  </button>
                  <button
                    type="button"
                    onClick={() => setShowNoteInput(false)}
                    style={{
                      background: 'transparent',
                      border: 'none',
                      color: 'var(--text-secondary, #94a3b8)',
                      cursor: 'pointer',
                      fontSize: '0.75rem',
                    }}
                  >
                    Cancel
                  </button>
                </div>
              ) : (
                <button
                  type="button"
                  onClick={() => setShowNoteInput(true)}
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: '0.3rem',
                    padding: '0.25rem 0.6rem',
                    fontSize: '0.75rem',
                    fontWeight: 600,
                    borderRadius: '4px',
                    backgroundColor: 'rgba(255, 255, 255, 0.1)',
                    border: `1px solid ${cfg.border}`,
                    color: cfg.color,
                    cursor: 'pointer',
                  }}
                >
                  <Check size={12} aria-hidden="true" />
                  <span>Acknowledge</span>
                </button>
              )}
            </>
          )}

          {alert.metadata && Object.keys(alert.metadata).length > 0 && (
            <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary, #94a3b8)', fontFamily: 'monospace' }}>
              {Object.entries(alert.metadata)
                .map(([k, v]) => `${k}: ${v}`)
                .join(' | ')}
            </span>
          )}
        </div>
      </div>

      {/* Dismiss Button if dismissible */}
      {alert.is_dismissed !== true && onDismiss && (
        <button
          type="button"
          aria-label={`Dismiss ${alert.title}`}
          onClick={() => onDismiss(alert.id)}
          style={{
            background: 'transparent',
            border: 'none',
            color: 'var(--text-secondary, #94a3b8)',
            cursor: 'pointer',
            padding: '2px',
          }}
        >
          <X size={16} aria-hidden="true" />
        </button>
      )}
    </div>
  );
};
