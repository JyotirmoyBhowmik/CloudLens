import React from 'react';
import { XCircle } from 'lucide-react';

export interface SkeletonLoaderProps {
  variant?: 'table' | 'card' | 'text';
  rows?: number;
  onCancel?: () => void;
  loadingMessage?: string;
  className?: string;
}

/**
 * Accessible Skeleton Loader with Cancel Affordance
 * Enforces BBP Section 31: "skeleton loading with cancel".
 */
export const SkeletonLoader: React.FC<SkeletonLoaderProps> = ({
  variant = 'table',
  rows = 4,
  onCancel,
  loadingMessage = 'Loading CloudLens dataset...',
  className = '',
}) => {
  return (
    <div
      role="status"
      aria-busy="true"
      aria-live="polite"
      className={`cloudlens-skeleton-container ${className}`}
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: '0.75rem',
        width: '100%',
        padding: '1.25rem',
        backgroundColor: 'var(--bg-secondary)',
        border: '1px solid var(--border-color)',
        borderRadius: '8px',
      }}
    >
      {/* Top Header & Cancel Button */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginBottom: '0.25rem',
        }}
      >
        <span style={{ fontSize: '0.8125rem', color: 'var(--text-secondary)' }}>
          {loadingMessage}
        </span>

        {onCancel && (
          <button
            type="button"
            onClick={onCancel}
            aria-label="Cancel in-flight request"
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '0.35rem',
              padding: '0.25rem 0.6rem',
              fontSize: '0.75rem',
              borderRadius: '4px',
              border: '1px solid var(--border-color)',
              backgroundColor: 'transparent',
              color: 'var(--text-secondary)',
              cursor: 'pointer',
              transition: 'all 0.15s ease',
            }}
          >
            <XCircle size={13} aria-hidden="true" />
            <span>Cancel</span>
          </button>
        )}
      </div>

      {/* Shimmer Placeholder Lines */}
      {variant === 'table' ? (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.6rem' }}>
          {/* Header shimmer */}
          <div
            className="cloudlens-shimmer"
            style={{
              height: '24px',
              backgroundColor: 'rgba(255, 255, 255, 0.08)',
              borderRadius: '4px',
              width: '100%',
            }}
          />
          {/* Rows shimmer */}
          {Array.from({ length: rows }).map((_, i) => (
            <div
              key={i}
              className="cloudlens-shimmer"
              style={{
                height: '32px',
                backgroundColor: 'rgba(255, 255, 255, 0.04)',
                borderRadius: '4px',
                width: '100%',
              }}
            />
          ))}
        </div>
      ) : variant === 'card' ? (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '1rem' }}>
          {Array.from({ length: 3 }).map((_, i) => (
            <div
              key={i}
              className="cloudlens-shimmer"
              style={{
                height: '100px',
                backgroundColor: 'rgba(255, 255, 255, 0.05)',
                borderRadius: '6px',
              }}
            />
          ))}
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
          <div
            className="cloudlens-shimmer"
            style={{ height: '16px', width: '80%', backgroundColor: 'rgba(255, 255, 255, 0.05)', borderRadius: '4px' }}
          />
          <div
            className="cloudlens-shimmer"
            style={{ height: '16px', width: '60%', backgroundColor: 'rgba(255, 255, 255, 0.05)', borderRadius: '4px' }}
          />
        </div>
      )}
    </div>
  );
};
