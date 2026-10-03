import React from 'react';
import { AlertTriangle, RefreshCw } from 'lucide-react';

export interface ProviderErrorDetail {
  provider: string; // e.g., 'AWS', 'AZURE', 'GCP', 'OCI'
  upstreamCode?: string; // e.g., 'AccessDenied', 'ResourceNotFound'
  upstreamMessage?: string;
  requestId?: string;
}

export interface ErrorStateProps {
  title?: string;
  message: string;
  errorCode?: string;
  correlationId?: string;
  providerError?: ProviderErrorDetail;
  onRetry?: () => void;
  secondaryAction?: {
    label: string;
    onClick: () => void;
  };
  className?: string;
}

/**
 * Enterprise Error State Component
 * Enforces BBP Section 31 & Rule 2.4:
 * "error states carrying the provider error and a next action"
 * "Safe sanitized error response without exposing internal server paths"
 */
export const ErrorState: React.FC<ErrorStateProps> = ({
  title = 'Operation Failed',
  message,
  errorCode = 'INTERNAL_ERROR',
  correlationId,
  providerError,
  onRetry,
  secondaryAction,
  className = '',
}) => {
  return (
    <div
      role="alert"
      aria-live="assertive"
      className={`cloudlens-error-state ${className}`}
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: '1rem',
        padding: '1.5rem',
        borderRadius: '8px',
        backgroundColor: 'rgba(127, 29, 29, 0.2)',
        border: '1px solid #991b1b',
        color: '#fca5a5',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: '0.75rem' }}>
        <div
          style={{
            padding: '0.4rem',
            borderRadius: '6px',
            backgroundColor: 'rgba(239, 68, 68, 0.2)',
            color: '#f87171',
            flexShrink: 0,
          }}
        >
          <AlertTriangle size={20} aria-hidden="true" />
        </div>

        <div style={{ flex: 1 }}>
          <h4 style={{ margin: '0 0 0.25rem 0', color: '#fef2f2', fontSize: '1rem', fontWeight: 600 }}>
            {title}
          </h4>
          <p style={{ margin: '0 0 0.5rem 0', fontSize: '0.875rem', color: '#fca5a5', lineHeight: 1.5 }}>
            {message}
          </p>

          {/* Diagnostic Metadata & Correlation ID (Rule 2.4) */}
          <div
            style={{
              display: 'flex',
              flexWrap: 'wrap',
              gap: '1rem',
              fontSize: '0.75rem',
              color: '#f87171',
              fontFamily: 'monospace',
              marginTop: '0.4rem',
            }}
          >
            <span>Error Code: {errorCode}</span>
            {correlationId && <span>Correlation ID: {correlationId}</span>}
          </div>

          {/* Upstream Provider Error Carrier */}
          {providerError && (
            <div
              style={{
                marginTop: '0.75rem',
                padding: '0.6rem 0.8rem',
                borderRadius: '6px',
                backgroundColor: 'rgba(0, 0, 0, 0.3)',
                border: '1px solid rgba(239, 68, 68, 0.3)',
                fontSize: '0.8125rem',
              }}
            >
              <div style={{ fontWeight: 600, color: '#fca5a5', marginBottom: '0.2rem' }}>
                Upstream {providerError.provider} Provider Fault:
              </div>
              <div style={{ color: '#fecaca', fontSize: '0.75rem', fontFamily: 'monospace' }}>
                {providerError.upstreamCode && `[${providerError.upstreamCode}] `}
                {providerError.upstreamMessage || 'Provider reported unhandled telemetry fault.'}
              </div>
              {providerError.requestId && (
                <div style={{ color: '#f87171', fontSize: '0.7rem', marginTop: '0.2rem' }}>
                  Provider Request ID: {providerError.requestId}
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Action Next Step Buttons */}
      <div
        style={{
          display: 'flex',
          gap: '0.6rem',
          alignItems: 'center',
          justifyContent: 'flex-end',
          borderTop: '1px solid rgba(239, 68, 68, 0.2)',
          paddingTop: '0.75rem',
        }}
      >
        {secondaryAction && (
          <button
            type="button"
            onClick={secondaryAction.onClick}
            aria-label={secondaryAction.label}
            style={{
              padding: '0.35rem 0.75rem',
              borderRadius: '6px',
              border: '1px solid var(--border-color)',
              backgroundColor: 'transparent',
              color: '#fef2f2',
              fontSize: '0.8125rem',
              cursor: 'pointer',
            }}
          >
            {secondaryAction.label}
          </button>
        )}

        {onRetry && (
          <button
            type="button"
            onClick={onRetry}
            aria-label="Retry failed operation"
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '0.35rem',
              padding: '0.35rem 0.85rem',
              borderRadius: '6px',
              border: 'none',
              backgroundColor: '#ef4444',
              color: '#ffffff',
              fontSize: '0.8125rem',
              fontWeight: 600,
              cursor: 'pointer',
            }}
          >
            <RefreshCw size={13} aria-hidden="true" />
            <span>Retry</span>
          </button>
        )}
      </div>
    </div>
  );
};
