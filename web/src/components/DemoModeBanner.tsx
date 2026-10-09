import React from 'react';
import { Sparkles, ShieldCheck } from 'lucide-react';

export interface DemoModeBannerProps {
  isDemo?: boolean;
  tenantId?: string;
  onExitDemo?: () => void;
  className?: string;
}

export const DemoModeBanner: React.FC<DemoModeBannerProps> = ({
  isDemo = true,
  tenantId = 'tenant-demo',
  className = '',
}) => {
  if (!isDemo) return null;

  return (
    <div
      role="status"
      aria-label="Demo Mode Active Banner"
      className={`cloudlens-demo-banner ${className}`}
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '0.5rem 1.5rem',
        backgroundColor: 'rgba(14, 165, 233, 0.12)',
        borderBottom: '1px solid rgba(14, 165, 233, 0.3)',
        color: '#38bdf8',
        fontSize: '0.8125rem',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
        <Sparkles size={16} aria-hidden="true" style={{ color: '#38bdf8', flexShrink: 0 }} />
        <div>
          <strong style={{ color: '#f0f9ff' }}>Demo Mode Active:</strong>
          <span style={{ marginLeft: '0.5rem', color: '#bae6fd' }}>
            Deterministic synthetic estate active for tenant <code>{tenantId}</code> (Seed 42). Zero cloud credentials accessed.
          </span>
        </div>
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
        <span
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: '0.25rem',
            padding: '0.15rem 0.5rem',
            borderRadius: '9999px',
            backgroundColor: 'rgba(56, 189, 248, 0.2)',
            border: '1px solid rgba(56, 189, 248, 0.4)',
            fontSize: '0.7rem',
            fontWeight: 600,
            color: '#e0f2fe',
          }}
        >
          <ShieldCheck size={12} aria-hidden="true" />
          FOCUS 1.0 Synthetic
        </span>
      </div>
    </div>
  );
};
