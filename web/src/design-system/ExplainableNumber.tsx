import React, { useState } from 'react';
import { Info, X } from 'lucide-react';
import { CostSourceBadge } from './CostValue';
import { CostSource } from './tokens';

export interface NumberDerivationDetail {
  metricName: string;
  formattedValue: string;
  rawNumericValue: number | string;
  formula?: string;
  costBasis?: 'BILLED' | 'EFFECTIVE' | 'LIST' | 'CONTRACTED' | 'AMORTISED';
  currency?: string;
  exchangeRate?: number;
  includesUnallocated?: boolean;
  unallocatedReason?: string;
  attributionRule?: string;
  pricingSource?: string;
  dataFreshness?: string;
  notes?: string;
  costSource?: CostSource;
  sourceConnection?: string;
  dataset?: string;
  period?: string;
  retrievedAt?: string;
}

export interface ExplainableNumberProps {
  value: number | string;
  detail: NumberDerivationDetail;
  currency?: string;
  precision?: number;
  className?: string;
}

/**
 * Explainable Number Affordance Component
 * Enforces BBP Section 31: "every number explainable through a detail affordance".
 */
export const ExplainableNumber: React.FC<ExplainableNumberProps> = ({
  value,
  detail,
  currency,
  precision = 2,
  className = '',
}) => {
  const [isOpen, setIsOpen] = useState(false);

  const num = typeof value === 'number' ? value : parseFloat(String(value));
  const displayVal = !isNaN(num)
    ? num.toLocaleString(undefined, {
        minimumFractionDigits: precision,
        maximumFractionDigits: precision,
      })
    : String(value);

  const fullDisplay = currency ? `${currency} ${displayVal}` : displayVal;

  return (
    <span
      className={`cloudlens-explainable-number ${className}`}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: '0.3rem',
        position: 'relative',
        fontVariantNumeric: 'tabular-nums',
      }}
    >
      <span style={{ fontWeight: 500 }}>{fullDisplay}</span>

      <button
        type="button"
        aria-label={`Explain derivation of ${detail.metricName}: ${fullDisplay}`}
        aria-haspopup="dialog"
        aria-expanded={isOpen}
        onClick={() => setIsOpen(!isOpen)}
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          justifyContent: 'center',
          width: '18px',
          height: '18px',
          borderRadius: '50%',
          border: '1px solid var(--border-color)',
          backgroundColor: 'transparent',
          color: 'var(--text-secondary)',
          cursor: 'pointer',
          padding: 0,
          transition: 'color 0.15s ease, border-color 0.15s ease',
        }}
        onMouseEnter={(e) => {
          (e.currentTarget as HTMLElement).style.color = 'var(--accent-blue, #38bdf8)';
          (e.currentTarget as HTMLElement).style.borderColor = 'var(--accent-blue, #38bdf8)';
        }}
        onMouseLeave={(e) => {
          (e.currentTarget as HTMLElement).style.color = 'var(--text-secondary)';
          (e.currentTarget as HTMLElement).style.borderColor = 'var(--border-color)';
        }}
      >
        <Info size={11} aria-hidden="true" />
      </button>

      {/* Accessible Detail Popover */}
      {isOpen && (
        <div
          role="dialog"
          aria-label={`Derivation details for ${detail.metricName}`}
          style={{
            position: 'absolute',
            top: 'calc(100% + 6px)',
            right: 0,
            zIndex: 60,
            width: '320px',
            backgroundColor: 'var(--bg-secondary)',
            border: '1px solid var(--border-color)',
            borderRadius: '8px',
            padding: '1rem',
            boxShadow: '0 10px 25px -5px rgba(0, 0, 0, 0.5)',
            fontSize: '0.8125rem',
            textAlign: 'left',
          }}
        >
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'flex-start',
              marginBottom: '0.75rem',
              borderBottom: '1px solid var(--border-color)',
              paddingBottom: '0.5rem',
            }}
          >
            <div>
              <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
                Number Provenance
              </div>
              <strong style={{ fontSize: '0.9375rem', color: 'var(--text-primary)' }}>
                {detail.metricName}
              </strong>
            </div>
            <button
              type="button"
              aria-label="Close number derivation dialog"
              onClick={() => setIsOpen(false)}
              style={{
                background: 'transparent',
                border: 'none',
                color: 'var(--text-secondary)',
                cursor: 'pointer',
                padding: '2px',
              }}
            >
              <X size={14} aria-hidden="true" />
            </button>
          </div>

          <div
            style={{
              display: 'flex',
              flexDirection: 'column',
              gap: '0.5rem',
              color: 'var(--text-primary)',
            }}
          >
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                backgroundColor: 'rgba(0,0,0,0.2)',
                padding: '0.4rem',
                borderRadius: '4px',
              }}
            >
              <span style={{ color: 'var(--text-secondary)' }}>Evaluated Value:</span>
              <strong style={{ fontFamily: 'monospace' }}>
                {detail.formattedValue || fullDisplay}
              </strong>
            </div>

            {detail.sourceConnection && (
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ color: 'var(--text-secondary)' }}>Source Connection:</span>
                <span style={{ fontFamily: 'monospace' }}>{detail.sourceConnection}</span>
              </div>
            )}

            {detail.dataset && (
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ color: 'var(--text-secondary)' }}>Dataset:</span>
                <span>{detail.dataset}</span>
              </div>
            )}

            {detail.period && (
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ color: 'var(--text-secondary)' }}>Period:</span>
                <span>{detail.period}</span>
              </div>
            )}

            {detail.retrievedAt && (
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ color: 'var(--text-secondary)' }}>Retrieved At:</span>
                <span style={{ fontSize: '0.75rem' }}>{detail.retrievedAt}</span>
              </div>
            )}

            {detail.costSource && (
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span style={{ color: 'var(--text-secondary)' }}>Cost Source:</span>
                <CostSourceBadge source={detail.costSource} size="sm" />
              </div>
            )}

            {detail.formula && (
              <div>
                <span style={{ color: 'var(--text-secondary)' }}>Formula:</span>
                <pre
                  style={{
                    margin: '0.2rem 0 0 0',
                    padding: '0.35rem',
                    backgroundColor: '#0f172a',
                    borderRadius: '4px',
                    fontSize: '0.75rem',
                    color: '#38bdf8',
                  }}
                >
                  {detail.formula}
                </pre>
              </div>
            )}

            {detail.costBasis && (
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ color: 'var(--text-secondary)' }}>Cost Basis:</span>
                <strong>{detail.costBasis}</strong>
              </div>
            )}

            {detail.currency && (
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ color: 'var(--text-secondary)' }}>Currency Policy:</span>
                <span>
                  {detail.currency} {detail.exchangeRate ? `(FX Rate: ${detail.exchangeRate})` : ''}
                </span>
              </div>
            )}

            {detail.attributionRule && (
              <div>
                <span style={{ color: 'var(--text-secondary)' }}>Attribution Rule: </span>
                <span>{detail.attributionRule}</span>
              </div>
            )}

            {detail.includesUnallocated !== undefined && (
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ color: 'var(--text-secondary)' }}>Unallocated Spend:</span>
                <span>{detail.includesUnallocated ? 'Included' : 'Excluded'}</span>
              </div>
            )}

            {detail.dataFreshness && (
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ color: 'var(--text-secondary)' }}>Data Freshness:</span>
                <span>{detail.dataFreshness}</span>
              </div>
            )}
          </div>
        </div>
      )}
    </span>
  );
};
