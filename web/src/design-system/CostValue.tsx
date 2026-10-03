import React from 'react';
import {
  CheckCircle,
  Calculator,
  TrendingUp,
  Edit3,
  Database,
  Slash,
  AlertTriangle,
} from 'lucide-react';
import { CostSource, COST_SOURCES, CostExplanation } from './tokens';
import { NullValue } from './NullValue';
import { InformationIcon } from './InformationIcon';

export interface CostSourceBadgeProps {
  source: CostSource;
  size?: 'sm' | 'md';
  className?: string;
}

/**
 * Cost Source Badge Component
 * Displays distinct badge for ACTUAL, ESTIMATED, FORECAST, MANUAL, CACHED, UNAVAILABLE.
 */
export const CostSourceBadge: React.FC<CostSourceBadgeProps> = ({
  source,
  size = 'md',
  className = '',
}) => {
  const config = COST_SOURCES[source] || COST_SOURCES.UNAVAILABLE;

  const renderIcon = (iconSize: number) => {
    switch (source) {
      case 'ACTUAL':
        return <CheckCircle size={iconSize} aria-hidden="true" />;
      case 'ESTIMATED':
        return <Calculator size={iconSize} aria-hidden="true" />;
      case 'FORECAST':
        return <TrendingUp size={iconSize} aria-hidden="true" />;
      case 'MANUAL':
        return <Edit3 size={iconSize} aria-hidden="true" />;
      case 'CACHED':
        return <Database size={iconSize} aria-hidden="true" />;
      case 'UNAVAILABLE':
      default:
        return <Slash size={iconSize} aria-hidden="true" />;
    }
  };

  const isSmall = size === 'sm';

  return (
    <span
      role="status"
      aria-label={config.accessibleLabel}
      title={`${config.label} Cost: ${config.description}`}
      className={`cost-source-badge cost-source-${source.toLowerCase()} ${className}`}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: isSmall ? '0.2rem' : '0.3rem',
        padding: isSmall ? '0.1rem 0.35rem' : '0.15rem 0.5rem',
        fontSize: isSmall ? '0.7rem' : '0.75rem',
        fontWeight: 600,
        borderRadius: '4px',
        backgroundColor: config.bgHex,
        border: `1px solid ${config.borderHex}`,
        color: config.colorHex,
        lineHeight: 1.2,
        userSelect: 'none',
        whiteSpace: 'nowrap',
      }}
    >
      {renderIcon(isSmall ? 10 : 12)}
      <span>{config.label}</span>
    </span>
  );
};

export interface CostValueProps {
  amount: number | null | undefined;
  /**
   * Mandatory CostSource to satisfy Acceptance:
   * "An estimated cost cannot be styled as an actual cost without deliberately overriding the component."
   */
  source: CostSource;
  /**
   * Mandatory explanation payload (Prompt 40 Mechanical Enforcement):
   * "A component rendering a cost without an explanation payload fails the build."
   */
  explanation: CostExplanation;
  currency?: string;
  precision?: number;
  showBadge?: boolean;
  showInfoIcon?: boolean;
  onOpenFullPanels?: () => void;
  className?: string;
}

/**
 * Universal Cost Value Display Component (Prompt 36 & Prompt 40)
 * Enforces mandatory source tagging, distinct visual styling per cost source,
 * and reachable explanation within one interaction.
 */
export const CostValue: React.FC<CostValueProps> = ({
  amount,
  source,
  explanation,
  currency = 'USD',
  precision = 2,
  showBadge = true,
  showInfoIcon = true,
  onOpenFullPanels,
  className = '',
}) => {
  // If explanation is null/undefined at runtime, enforce mechanical guard
  if (!explanation) {
    throw new Error(
      `Mechanical violation: CostValue component rendered without mandatory explanation payload.`
    );
  }

  const isStale = explanation.isStale || false;

  if (amount === null || amount === undefined) {
    return (
      <span
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: '0.4rem',
        }}
        className={className}
      >
        <NullValue state={source === 'UNAVAILABLE' ? 'NOT_SUPPORTED' : 'NO_DATA'} />
        {showBadge && <CostSourceBadge source={source} size="sm" />}
        {showInfoIcon && (
          <InformationIcon
            explanation={explanation}
            size="sm"
            onOpenFullPanels={onOpenFullPanels}
          />
        )}
      </span>
    );
  }

  const isZero = amount === 0;
  const formatted = amount.toLocaleString(undefined, {
    minimumFractionDigits: precision,
    maximumFractionDigits: precision,
  });

  // Source-specific visual traits
  const prefixTilde = source === 'ESTIMATED' || source === 'FORECAST';
  const isMuted = source === 'CACHED' || source === 'UNAVAILABLE';

  return (
    <span
      className={`cloudlens-cost-value cost-type-${source.toLowerCase()} ${className}`}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: '0.45rem',
        fontVariantNumeric: 'tabular-nums',
        fontFamily: 'monospace',
        whiteSpace: 'nowrap',
      }}
    >
      <span
        style={{
          fontWeight: 600,
          color: isMuted ? 'var(--text-secondary)' : 'var(--text-primary)',
          opacity: source === 'CACHED' ? 0.8 : 1,
        }}
      >
        {prefixTilde && (
          <span
            title="Estimated or projected approximation"
            style={{ marginRight: '0.15rem', color: 'var(--text-secondary)' }}
          >
            ~
          </span>
        )}
        {currency} {isZero ? `0.${'0'.repeat(precision)}` : formatted}
      </span>

      {/* Staleness Warning Indicator */}
      {isStale && (
        <span
          title={`Stale pricing: Retrieved ${new Date(explanation.retrievalTimestamp).toLocaleDateString()}. ${explanation.stalenessWarning || 'Exceeds SLA threshold.'}`}
          style={{ color: '#f87171', display: 'inline-flex', alignItems: 'center' }}
        >
          <AlertTriangle size={12} aria-hidden="true" />
        </span>
      )}

      {showBadge && <CostSourceBadge source={source} size="sm" />}

      {/* Reachable Explanation Icon (Accessible within one interaction) */}
      {showInfoIcon && (
        <InformationIcon
          explanation={explanation}
          size="sm"
          onOpenFullPanels={onOpenFullPanels}
        />
      )}
    </span>
  );
};

/**
 * Convenience helper to create defensible CostExplanation payloads with defaults.
 */
export function createCostExplanation(
  metricName: string,
  overrides?: Partial<CostExplanation>
): CostExplanation {
  return {
    metricName,
    pricingSource: overrides?.pricingSource || 'aws_price_list_bulk',
    retrievalTimestamp: overrides?.retrievalTimestamp || '2026-10-02T12:00:00Z',
    effectiveDate: overrides?.effectiveDate || '2026-09-01T00:00:00Z',
    region: overrides?.region || 'us-east-1',
    currency: overrides?.currency || 'USD',
    ...overrides,
  };
}
