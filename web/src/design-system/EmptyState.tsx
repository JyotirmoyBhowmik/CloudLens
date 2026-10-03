import React from 'react';
import {
  Inbox,
  ShieldAlert,
  AlertCircle,
  RefreshCw,
} from 'lucide-react';
import { EmptyStateType, EMPTY_STATES } from './tokens';

export interface EmptyStateProps {
  type: EmptyStateType;
  titleOverride?: string;
  descriptionOverride?: string;
  actionTextOverride?: string;
  onAction?: () => void;
  className?: string;
}

/**
 * Four Distinct Empty States Component
 * Enforces BBP Section 31: "four distinct empty states (no data, no access, not supported, not yet synced)".
 */
export const EmptyState: React.FC<EmptyStateProps> = ({
  type,
  titleOverride,
  descriptionOverride,
  actionTextOverride,
  onAction,
  className = '',
}) => {
  const config = EMPTY_STATES[type] || EMPTY_STATES.NO_DATA;

  const renderVisualIcon = () => {
    const iconSize = 36;
    switch (type) {
      case 'NO_DATA':
        return (
          <div
            style={{
              width: '64px',
              height: '64px',
              borderRadius: '50%',
              backgroundColor: 'rgba(148, 163, 184, 0.1)',
              border: '1px solid rgba(148, 163, 184, 0.2)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: '#94a3b8',
            }}
          >
            <Inbox size={iconSize} aria-hidden="true" />
          </div>
        );
      case 'NO_ACCESS':
        return (
          <div
            style={{
              width: '64px',
              height: '64px',
              borderRadius: '50%',
              backgroundColor: 'rgba(239, 68, 68, 0.1)',
              border: '1px solid rgba(239, 68, 68, 0.25)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: '#f87171',
            }}
          >
            <ShieldAlert size={iconSize} aria-hidden="true" />
          </div>
        );
      case 'NOT_SUPPORTED':
        return (
          <div
            style={{
              width: '64px',
              height: '64px',
              borderRadius: '50%',
              backgroundColor: 'rgba(245, 158, 11, 0.1)',
              border: '1px solid rgba(245, 158, 11, 0.25)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: '#fbbf24',
            }}
          >
            <AlertCircle size={iconSize} aria-hidden="true" />
          </div>
        );
      case 'NOT_YET_SYNCED':
      default:
        return (
          <div
            style={{
              width: '64px',
              height: '64px',
              borderRadius: '50%',
              backgroundColor: 'rgba(56, 189, 248, 0.1)',
              border: '1px solid rgba(56, 189, 248, 0.25)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: '#38bdf8',
            }}
          >
            <RefreshCw size={iconSize} aria-hidden="true" />
          </div>
        );
    }
  };

  return (
    <div
      role="status"
      aria-label={config.accessibleName}
      className={`cloudlens-empty-state empty-state-${type.toLowerCase()} ${className}`}
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        textAlign: 'center',
        padding: '3rem 2rem',
        borderRadius: '8px',
        backgroundColor: 'rgba(0, 0, 0, 0.15)',
        border: '1px dashed var(--border-color)',
        minHeight: '260px',
      }}
    >
      <div style={{ marginBottom: '1rem' }}>{renderVisualIcon()}</div>

      <h3
        style={{
          fontSize: '1.125rem',
          fontWeight: 600,
          margin: '0 0 0.5rem 0',
          color: 'var(--text-primary)',
        }}
      >
        {titleOverride || config.title}
      </h3>

      <p
        style={{
          maxWidth: '460px',
          fontSize: '0.875rem',
          color: 'var(--text-secondary)',
          margin: '0 0 1.25rem 0',
          lineHeight: 1.5,
        }}
      >
        {descriptionOverride || config.description}
      </p>

      {onAction && (
        <button
          type="button"
          onClick={onAction}
          aria-label={actionTextOverride || config.actionText}
          style={{
            padding: '0.45rem 1rem',
            fontSize: '0.8125rem',
            fontWeight: 500,
            borderRadius: '6px',
            border: '1px solid var(--accent-blue, #38bdf8)',
            backgroundColor: 'rgba(56, 189, 248, 0.15)',
            color: 'var(--accent-blue, #38bdf8)',
            cursor: 'pointer',
            transition: 'background-color 0.15s ease',
          }}
          onMouseEnter={(e) => {
            (e.currentTarget as HTMLElement).style.backgroundColor =
              'rgba(56, 189, 248, 0.25)';
          }}
          onMouseLeave={(e) => {
            (e.currentTarget as HTMLElement).style.backgroundColor =
              'rgba(56, 189, 248, 0.15)';
          }}
        >
          {actionTextOverride || config.actionText}
        </button>
      )}
    </div>
  );
};
