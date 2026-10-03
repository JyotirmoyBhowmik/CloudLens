import React, { useState } from 'react';
import { ChevronDown, ChevronRight } from 'lucide-react';

export interface ProgressiveDisclosureProps {
  title: string;
  children: React.ReactNode;
  defaultOpen?: boolean;
  badgeText?: string;
  className?: string;
}

/**
 * Accessible Progressive Disclosure Panel Component
 * Enforces BBP Section 31: "progressive disclosure: secondary details collapsed behind accessible toggles".
 */
export const ProgressiveDisclosure: React.FC<ProgressiveDisclosureProps> = ({
  title,
  children,
  defaultOpen = false,
  badgeText,
  className = '',
}) => {
  const [isOpen, setIsOpen] = useState(defaultOpen);
  const panelId = `panel-${Math.random().toString(36).substr(2, 6)}`;

  return (
    <div
      className={`cloudlens-disclosure ${className}`}
      style={{
        border: '1px solid var(--border-color)',
        borderRadius: '6px',
        overflow: 'hidden',
        backgroundColor: 'rgba(0, 0, 0, 0.1)',
      }}
    >
      <button
        type="button"
        aria-expanded={isOpen}
        aria-controls={panelId}
        onClick={() => setIsOpen(!isOpen)}
        style={{
          width: '100%',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '0.6rem 0.8rem',
          backgroundColor: 'transparent',
          border: 'none',
          color: 'var(--text-primary)',
          fontSize: '0.875rem',
          fontWeight: 600,
          cursor: 'pointer',
          textAlign: 'left',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          {isOpen ? (
            <ChevronDown size={14} aria-hidden="true" style={{ color: 'var(--text-secondary)' }} />
          ) : (
            <ChevronRight size={14} aria-hidden="true" style={{ color: 'var(--text-secondary)' }} />
          )}
          <span>{title}</span>
          {badgeText && (
            <span
              style={{
                fontSize: '0.7rem',
                padding: '0.1rem 0.4rem',
                borderRadius: '4px',
                backgroundColor: 'rgba(255, 255, 255, 0.08)',
                color: 'var(--text-secondary)',
              }}
            >
              {badgeText}
            </span>
          )}
        </div>
        <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
          {isOpen ? 'Collapse' : 'Expand'}
        </span>
      </button>

      {isOpen && (
        <div
          id={panelId}
          style={{
            padding: '0.8rem',
            borderTop: '1px solid var(--border-color)',
            backgroundColor: 'rgba(0, 0, 0, 0.2)',
          }}
        >
          {children}
        </div>
      )}
    </div>
  );
};
