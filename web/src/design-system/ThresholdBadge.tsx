import React from 'react';
import {
  CheckCircle,
  AlertTriangle,
  AlertCircle,
  Info,
  HelpCircle,
  ShieldAlert,
} from 'lucide-react';
import { ThresholdState, THRESHOLD_STATES } from './tokens';

export interface ThresholdBadgeProps {
  state: ThresholdState;
  labelOverride?: string;
  size?: 'sm' | 'md' | 'lg';
  showIcon?: boolean;
  className?: string;
}

/**
 * Threshold Colour System Component
 * Enforces BBP Section 31: "colour reserved exclusively for threshold state and always paired with a text label or icon".
 * Enforces WCAG 2.1 AA (1.4.1 Use of Color): Never conveys state by color alone.
 */
export const ThresholdBadge: React.FC<ThresholdBadgeProps> = ({
  state,
  labelOverride,
  size = 'md',
  showIcon = true,
  className = '',
}) => {
  const config = THRESHOLD_STATES[state] || THRESHOLD_STATES.UNKNOWN;

  const renderIcon = (iconSize: number) => {
    switch (state) {
      case 'NORMAL':
        return <CheckCircle size={iconSize} aria-hidden="true" />;
      case 'WARNING':
        return <AlertTriangle size={iconSize} aria-hidden="true" />;
      case 'HIGH':
        return <AlertCircle size={iconSize} aria-hidden="true" />;
      case 'CRITICAL':
        return <ShieldAlert size={iconSize} aria-hidden="true" />;
      case 'INFORMATIONAL':
        return <Info size={iconSize} aria-hidden="true" />;
      case 'UNKNOWN':
      default:
        return <HelpCircle size={iconSize} aria-hidden="true" />;
    }
  };

  const sizeStyles = {
    sm: { padding: '0.15rem 0.4rem', fontSize: '0.75rem', iconSize: 12, gap: '0.25rem' },
    md: { padding: '0.25rem 0.6rem', fontSize: '0.8125rem', iconSize: 14, gap: '0.35rem' },
    lg: { padding: '0.4rem 0.85rem', fontSize: '0.9375rem', iconSize: 16, gap: '0.45rem' },
  }[size];

  return (
    <span
      role="status"
      aria-label={config.accessibleLabel}
      title={`${config.label}: ${config.description}`}
      className={`threshold-badge threshold-${state.toLowerCase()} ${className}`}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: sizeStyles.gap,
        padding: sizeStyles.padding,
        fontSize: sizeStyles.fontSize,
        fontWeight: 600,
        borderRadius: '6px',
        backgroundColor: config.bgHex,
        color: config.colorHex,
        border: `1px solid ${config.borderHex}`,
        lineHeight: 1,
        whiteSpace: 'nowrap',
        userSelect: 'none',
      }}
    >
      {showIcon && renderIcon(sizeStyles.iconSize)}
      <span style={{ letterSpacing: '0.01em' }}>
        {labelOverride || config.label}
      </span>
      {/* Accessible symbol glyph ensures identification even under monochromatic vision */}
      <span
        aria-hidden="true"
        style={{
          fontSize: '0.7em',
          opacity: 0.8,
          marginLeft: '0.1rem',
        }}
      >
        ({config.glyph})
      </span>
    </span>
  );
};
