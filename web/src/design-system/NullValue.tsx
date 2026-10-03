import React from 'react';
import { NullStateType, NULL_STATES } from './tokens';

export interface NullValueProps {
  state: NullStateType;
  customZeroValue?: string | number;
  showTooltip?: boolean;
  className?: string;
}

/**
 * Four-State Null Rendering Component
 * Enforces BBP Section 31 & NFR-064:
 * "Zero, no data, not applicable and not supported are visually distinct everywhere,
 * and a developer cannot accidentally render one as another."
 * Strict Rule: Never renders a blank cell for any absent value.
 */
export const NullValue: React.FC<NullValueProps> = ({
  state,
  customZeroValue,
  showTooltip = true,
  className = '',
}) => {
  const config = NULL_STATES[state] || NULL_STATES.NO_DATA;

  if (state === 'ZERO') {
    // 1. Confirmed Numeric Zero (Valid measurement, styled as real number, not missing)
    const displayVal =
      customZeroValue !== undefined ? String(customZeroValue) : config.shortLabel;
    return (
      <span
        className={`cloudlens-null-zero ${className}`}
        aria-label={config.accessibleName}
        title={showTooltip ? config.tooltipText : undefined}
        style={{
          fontVariantNumeric: 'tabular-nums',
          fontFamily: 'monospace',
          fontWeight: 600,
          color: 'var(--text-primary)',
          letterSpacing: '-0.02em',
        }}
      >
        {displayVal}
      </span>
    );
  }

  if (state === 'NO_DATA') {
    // 2. No Data (Expected telemetry is missing / empty collection)
    return (
      <span
        className={`cloudlens-null-no-data ${className}`}
        aria-label={config.accessibleName}
        title={showTooltip ? config.tooltipText : undefined}
        style={{
          color: 'var(--text-secondary)',
          fontStyle: 'normal',
          opacity: 0.75,
          borderBottom: '1px dashed var(--border-color)',
          paddingBottom: '1px',
          cursor: 'help',
        }}
      >
        --
      </span>
    );
  }

  if (state === 'NOT_APPLICABLE') {
    // 3. Not Applicable (Concept does not apply to this resource type)
    return (
      <span
        className={`cloudlens-null-na ${className}`}
        aria-label={config.accessibleName}
        title={showTooltip ? config.tooltipText : undefined}
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: '0.2rem',
          fontSize: '0.75rem',
          fontWeight: 600,
          color: 'var(--text-secondary)',
          backgroundColor: 'rgba(148, 163, 184, 0.12)',
          border: '1px solid rgba(148, 163, 184, 0.25)',
          padding: '0.1rem 0.4rem',
          borderRadius: '4px',
          cursor: 'help',
        }}
      >
        <span aria-hidden="true" style={{ fontSize: '0.85em' }}>
          {config.glyph}
        </span>
        <span>N/A</span>
      </span>
    );
  }

  // 4. Not Supported (Underlying cloud provider does not expose capability)
  if (state === 'NOT_SUPPORTED') {
    return (
      <span
        className={`cloudlens-null-unsupported ${className}`}
        aria-label={config.accessibleName}
        title={showTooltip ? config.tooltipText : undefined}
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: '0.25rem',
          fontSize: '0.75rem',
          fontWeight: 600,
          color: '#94a3b8',
          backgroundColor: 'rgba(71, 85, 105, 0.25)',
          border: '1px solid rgba(100, 116, 139, 0.4)',
          padding: '0.15rem 0.45rem',
          borderRadius: '4px',
          cursor: 'help',
        }}
      >
        <span aria-hidden="true" style={{ fontSize: '0.9em' }}>
          {config.glyph}
        </span>
        <span>Not supported</span>
      </span>
    );
  }

  return (
    <span
      className={`cloudlens-null-no-data ${className}`}
      aria-label={config.accessibleName}
      title={showTooltip ? config.tooltipText : undefined}
    >
      --
    </span>
  );
};

export interface DataCellProps {
  value: number | string | null | undefined;
  nullType?: NullStateType;
  currency?: string;
  precision?: number;
  className?: string;
}

/**
 * Universal DataCell component ensuring a cell NEVER renders blank.
 */
export const DataCell: React.FC<DataCellProps> = ({
  value,
  nullType,
  currency,
  precision = 2,
  className = '',
}) => {
  // If explicitly designated null state
  if (nullType && nullType !== 'ZERO') {
    return <NullValue state={nullType} className={className} />;
  }

  // Value missing or undefined -> Fallback to NO_DATA, NEVER blank!
  if (value === null || value === undefined || value === '') {
    return <NullValue state="NO_DATA" className={className} />;
  }

  // Check for confirmed numeric zero
  const num = typeof value === 'number' ? value : parseFloat(String(value));
  if (!isNaN(num) && num === 0) {
    const zeroFormatted = currency
      ? `${currency} 0.${'0'.repeat(precision)}`
      : `0.${'0'.repeat(precision)}`;
    return (
      <NullValue
        state="ZERO"
        customZeroValue={zeroFormatted}
        className={className}
      />
    );
  }

  // Valid number rendering
  if (!isNaN(num)) {
    const formatted = num.toLocaleString(undefined, {
      minimumFractionDigits: precision,
      maximumFractionDigits: precision,
    });
    return (
      <span
        className={`cloudlens-data-value ${className}`}
        style={{
          fontVariantNumeric: 'tabular-nums',
          fontFamily: 'monospace',
          fontWeight: 500,
        }}
      >
        {currency ? `${currency} ${formatted}` : formatted}
      </span>
    );
  }

  // Valid string rendering
  return <span className={className}>{String(value)}</span>;
};
