import React, { useState } from 'react';
import { Database, ExternalLink, ShieldCheck, X } from 'lucide-react';
import { CostExplanation } from './tokens';

export interface SourceTraceabilityBadgeProps {
  source: string;
  retrievedAt: string;
  effectiveDate: string;
  region: string;
  currency: string;
  sourceUrl?: string;
  isVerified?: boolean;
  explanation?: CostExplanation;
  compact?: boolean;
  className?: string;
}

/**
 * Source Traceability Badge Component (Prompt 40 Item 162).
 * Renders verified pricing source, retrieval timestamp, region, currency, and effective date.
 */
export const SourceTraceabilityBadge: React.FC<SourceTraceabilityBadgeProps> = ({
  source,
  retrievedAt,
  effectiveDate,
  region,
  currency,
  sourceUrl = 'https://aws.amazon.com/pricing/',
  isVerified = true,
  compact = true,
  className = '',
}) => {
  const [isOpen, setIsOpen] = useState(false);

  const formattedRetrieved = new Date(retrievedAt).toLocaleDateString();
  const formattedEffective = new Date(effectiveDate).toLocaleDateString();

  if (compact) {
    return (
      <span style={{ position: 'relative', display: 'inline-flex', alignItems: 'center' }} className={className}>
        <button
          type="button"
          aria-label={`Source provenance: ${source} (${region}, ${currency})`}
          aria-haspopup="dialog"
          aria-expanded={isOpen}
          onClick={() => setIsOpen(!isOpen)}
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: '0.25rem',
            padding: '0.1rem 0.35rem',
            borderRadius: '4px',
            backgroundColor: 'rgba(56, 189, 248, 0.1)',
            border: '1px solid rgba(56, 189, 248, 0.3)',
            color: 'var(--accent-blue, #38bdf8)',
            fontSize: '0.6875rem',
            fontFamily: 'monospace',
            cursor: 'pointer',
            lineHeight: 1.2,
          }}
          title={`Verified source: ${source} | Region: ${region} | Retrieved: ${formattedRetrieved}`}
        >
          <Database size={10} aria-hidden="true" />
          <span>{source}</span>
          {isVerified && <ShieldCheck size={10} color="#34d399" aria-hidden="true" />}
        </button>

        {isOpen && (
          <div
            role="dialog"
            aria-label="Source Traceability & Legal Effective Date"
            style={{
              position: 'absolute',
              top: 'calc(100% + 4px)',
              left: 0,
              zIndex: 90,
              width: '280px',
              backgroundColor: 'var(--bg-secondary, #1e293b)',
              border: '1px solid var(--border-color, #334155)',
              borderRadius: '6px',
              padding: '0.75rem',
              boxShadow: '0 10px 15px -3px rgba(0, 0, 0, 0.5)',
              fontSize: '0.75rem',
              color: 'var(--text-primary, #f8fafc)',
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
                <ShieldCheck size={14} color="#34d399" aria-hidden="true" />
                <strong style={{ color: 'var(--text-primary, #f8fafc)' }}>Source Traceability</strong>
              </div>
              <button
                type="button"
                onClick={() => setIsOpen(false)}
                style={{ background: 'transparent', border: 'none', color: '#94a3b8', cursor: 'pointer' }}
              >
                <X size={12} aria-hidden="true" />
              </button>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.3rem' }}>
              <div>
                <span style={{ color: 'var(--text-secondary, #94a3b8)' }}>Source Feed: </span>
                <code style={{ color: '#38bdf8' }}>{source}</code>
              </div>
              <div>
                <span style={{ color: 'var(--text-secondary, #94a3b8)' }}>Region: </span>
                <strong>{region}</strong> &bull; Currency: <strong>{currency}</strong>
              </div>
              <div>
                <span style={{ color: 'var(--text-secondary, #94a3b8)' }}>Effective Date: </span>
                <span>{formattedEffective}</span>
              </div>
              <div>
                <span style={{ color: 'var(--text-secondary, #94a3b8)' }}>Ingestion Time: </span>
                <span>{new Date(retrievedAt).toLocaleString()}</span>
              </div>
              <div style={{ marginTop: '0.35rem', paddingTop: '0.35rem', borderTop: '1px solid var(--border-color, #334155)' }}>
                <a
                  href={sourceUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: '0.25rem',
                    color: 'var(--accent-blue, #38bdf8)',
                    textDecoration: 'none',
                    fontWeight: 600,
                  }}
                >
                  <span>Provider Reference Link</span>
                  <ExternalLink size={10} aria-hidden="true" />
                </a>
              </div>
            </div>
          </div>
        )}
      </span>
    );
  }

  return (
    <div
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: '0.5rem',
        padding: '0.3rem 0.6rem',
        borderRadius: '6px',
        backgroundColor: 'rgba(15, 23, 42, 0.6)',
        border: '1px solid var(--border-color, #334155)',
        fontSize: '0.75rem',
      }}
      className={className}
    >
      <Database size={12} color="var(--accent-blue, #38bdf8)" aria-hidden="true" />
      <span>Source: <strong>{source}</strong></span>
      <span>&bull;</span>
      <span>Region: <strong>{region}</strong></span>
      <span>&bull;</span>
      <span>Eff: <strong>{formattedEffective}</strong></span>
      {isVerified && <ShieldCheck size={12} color="#34d399" aria-hidden="true" />}
    </div>
  );
};
