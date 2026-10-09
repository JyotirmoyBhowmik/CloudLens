import React from 'react';

interface MaintenanceModeBannerProps {
  active?: boolean;
  message?: string;
  retryAfterSeconds?: number;
}

export const MaintenanceModeBanner: React.FC<MaintenanceModeBannerProps> = ({
  active = false,
  message = 'CloudLens is currently undergoing scheduled platform maintenance. Mutating operations are paused.',
  retryAfterSeconds = 300,
}) => {
  if (!active) return null;

  return (
    <div
      role="alert"
      aria-live="assertive"
      style={{
        backgroundColor: '#78350f',
        color: '#fef3c7',
        borderBottom: '2px solid #b45309',
        padding: '0.625rem 1.5rem',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        fontSize: '0.875rem',
        fontWeight: 600,
        zIndex: 100,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
        <span
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            justifyContent: 'center',
            width: '20px',
            height: '20px',
            borderRadius: '50%',
            backgroundColor: '#f59e0b',
            color: '#78350f',
            fontWeight: 800,
            fontSize: '0.75rem',
          }}
        >
          !
        </span>
        <span>
          <strong>MAINTENANCE MODE ACTIVE:</strong> {message} (Read-only browsing operational. Auto-retry in {retryAfterSeconds}s).
        </span>
      </div>
      <div style={{ fontSize: '0.75rem', opacity: 0.9 }}>
        Governed by Control Tower
      </div>
    </div>
  );
};
