import React, { useState } from 'react';
import {
  HelpCircle,
  DollarSign,
  Gift,
  AlertCircle,
  Package,
  Calculator,
  XCircle,
  Database,
  Clock,
  GitCompare,
  Network,
  ExternalLink,
} from 'lucide-react';
import { StandardExplanationPanelData, StandardExplanationPanelType } from './tokens';

export interface StandardExplanationPanelsProps {
  panels: StandardExplanationPanelData[];
  serviceName: string;
  provider?: string;
  region?: string;
  defaultPanel?: StandardExplanationPanelType;
  onClose?: () => void;
  className?: string;
}

const PANEL_ICONS: Record<StandardExplanationPanelType, React.ReactNode> = {
  WHAT_IS_THIS_SERVICE: <HelpCircle size={16} aria-hidden="true" />,
  HOW_IS_IT_PRICED: <DollarSign size={16} aria-hidden="true" />,
  WHY_IS_IT_FREE: <Gift size={16} aria-hidden="true" />,
  WHAT_CAUSES_ADDITIONAL_CHARGES: <AlertCircle size={16} aria-hidden="true" />,
  WHAT_USAGE_IS_INCLUDED_IN_FREE_TIER: <Package size={16} aria-hidden="true" />,
  WHAT_IS_INCLUDED_IN_ESTIMATE: <Calculator size={16} aria-hidden="true" />,
  WHAT_IS_EXCLUDED: <XCircle size={16} aria-hidden="true" />,
  WHAT_PROVIDER_SOURCE_WAS_USED: <Database size={16} aria-hidden="true" />,
  WHEN_WAS_PRICING_LAST_RETRIEVED: <Clock size={16} aria-hidden="true" />,
  WHY_DOES_ACTUAL_BILLING_DIFFER: <GitCompare size={16} aria-hidden="true" />,
  WHAT_DEPENDENCY_IS_RESPONSIBLE: <Network size={16} aria-hidden="true" />,
};

/**
 * Eleven Standard Explanation Panels Component (Prompt 40 / Master Brief Section 50).
 * Provides exhaustive transparency across pricing, estimates, dependencies, and variances.
 */
export const StandardExplanationPanels: React.FC<StandardExplanationPanelsProps> = ({
  panels,
  serviceName,
  provider = 'AWS',
  region = 'us-east-1',
  defaultPanel = 'WHAT_IS_THIS_SERVICE',
  onClose,
  className = '',
}) => {
  const [selectedType, setSelectedType] = useState<StandardExplanationPanelType>(defaultPanel);

  const activePanel = panels.find((p) => p.panel_type === selectedType) || panels[0];

  return (
    <div
      className={`cloudlens-explanation-panels ${className}`}
      style={{
        display: 'flex',
        flexDirection: 'column',
        backgroundColor: 'var(--bg-secondary, #1e293b)',
        border: '1px solid var(--border-color, #334155)',
        borderRadius: '12px',
        overflow: 'hidden',
        boxShadow: '0 20px 25px -5px rgba(0, 0, 0, 0.5)',
      }}
    >
      {/* Top Header */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          padding: '1rem 1.5rem',
          borderBottom: '1px solid var(--border-color, #334155)',
          backgroundColor: 'rgba(15, 23, 42, 0.6)',
        }}
      >
        <div>
          <div style={{ fontSize: '0.75rem', textTransform: 'uppercase', color: 'var(--accent-blue, #38bdf8)', fontWeight: 700 }}>
            Master Brief Section 50 Explanation Layer
          </div>
          <h2 style={{ margin: 0, fontSize: '1.25rem', color: 'var(--text-primary, #f8fafc)' }}>
            {serviceName} &bull; Eleven Standard Explanation Panels
          </h2>
          <span style={{ fontSize: '0.8125rem', color: 'var(--text-secondary, #94a3b8)' }}>
            Provider: {provider.toUpperCase()} &bull; Region: {region}
          </span>
        </div>
        {onClose && (
          <button
            type="button"
            onClick={onClose}
            aria-label="Close explanation panels"
            style={{
              padding: '0.5rem 1rem',
              backgroundColor: 'transparent',
              border: '1px solid var(--border-color, #334155)',
              borderRadius: '6px',
              color: 'var(--text-secondary, #94a3b8)',
              cursor: 'pointer',
              fontWeight: 500,
            }}
          >
            Close
          </button>
        )}
      </div>

      {/* Main Body: 11 Tabs on Left, Active Detail on Right */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: '320px 1fr',
          minHeight: '520px',
        }}
      >
        {/* Navigation Sidebar (All 11 Panels) */}
        <div
          role="tablist"
          aria-label="Eleven Standard Explanation Panels"
          style={{
            borderRight: '1px solid var(--border-color, #334155)',
            backgroundColor: 'rgba(15, 23, 42, 0.3)',
            padding: '0.75rem 0',
            overflowY: 'auto',
          }}
        >
          {panels.map((p, idx) => {
            const isSelected = p.panel_type === selectedType;
            return (
              <button
                key={p.panel_type}
                role="tab"
                id={`tab-${p.panel_type}`}
                aria-selected={isSelected}
                aria-controls={`panel-${p.panel_type}`}
                type="button"
                onClick={() => setSelectedType(p.panel_type)}
                style={{
                  width: '100%',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.65rem',
                  padding: '0.75rem 1.25rem',
                  textAlign: 'left',
                  border: 'none',
                  borderLeft: isSelected ? '4px solid var(--accent-blue, #38bdf8)' : '4px solid transparent',
                  backgroundColor: isSelected ? 'rgba(56, 189, 248, 0.12)' : 'transparent',
                  color: isSelected ? 'var(--text-primary, #f8fafc)' : 'var(--text-secondary, #94a3b8)',
                  fontWeight: isSelected ? 600 : 400,
                  fontSize: '0.8125rem',
                  cursor: 'pointer',
                  transition: 'background-color 0.15s ease',
                }}
              >
                <span style={{ color: isSelected ? 'var(--accent-blue, #38bdf8)' : 'inherit' }}>
                  {PANEL_ICONS[p.panel_type]}
                </span>
                <span style={{ flex: 1, lineHeight: 1.3 }}>
                  <span style={{ fontSize: '0.7rem', color: 'var(--text-secondary, #64748b)', display: 'block' }}>
                    Panel {idx + 1}
                  </span>
                  {p.title}
                </span>
              </button>
            );
          })}
        </div>

        {/* Detail Panel */}
        {activePanel && (
          <div
            role="tabpanel"
            id={`panel-${activePanel.panel_type}`}
            aria-labelledby={`tab-${activePanel.panel_type}`}
            style={{
              padding: '1.75rem',
              overflowY: 'auto',
              display: 'flex',
              flexDirection: 'column',
              gap: '1.25rem',
            }}
          >
            {/* Headline Card */}
            <div
              style={{
                backgroundColor: 'rgba(56, 189, 248, 0.08)',
                border: '1px solid rgba(56, 189, 248, 0.25)',
                borderRadius: '8px',
                padding: '1rem 1.25rem',
              }}
            >
              <div style={{ fontSize: '0.75rem', textTransform: 'uppercase', color: 'var(--accent-blue, #38bdf8)', fontWeight: 700 }}>
                {activePanel.title}
              </div>
              <h3 style={{ margin: '0.35rem 0 0', fontSize: '1.125rem', color: 'var(--text-primary, #f8fafc)' }}>
                {activePanel.headline}
              </h3>
            </div>

            {/* Narrative Paragraph */}
            <div>
              <h4 style={{ margin: '0 0 0.5rem', fontSize: '0.875rem', color: 'var(--text-secondary, #94a3b8)', textTransform: 'uppercase' }}>
                Defensible Derivation &amp; Narrative
              </h4>
              <p
                style={{
                  fontSize: '0.9375rem',
                  lineHeight: 1.6,
                  color: 'var(--text-primary, #f8fafc)',
                  margin: 0,
                  backgroundColor: 'rgba(15, 23, 42, 0.4)',
                  padding: '1rem',
                  borderRadius: '6px',
                  border: '1px solid var(--border-color, #334155)',
                }}
              >
                {activePanel.narrative}
              </p>
            </div>

            {/* Key Facts Structured Table */}
            <div>
              <h4 style={{ margin: '0 0 0.5rem', fontSize: '0.875rem', color: 'var(--text-secondary, #94a3b8)', textTransform: 'uppercase' }}>
                Key Facts & Evidence
              </h4>
              <div
                style={{
                  border: '1px solid var(--border-color, #334155)',
                  borderRadius: '6px',
                  overflow: 'hidden',
                }}
              >
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.8125rem' }}>
                  <tbody>
                    {Object.entries(activePanel.key_facts).map(([key, val], i) => (
                      <tr
                        key={key}
                        style={{
                          backgroundColor: i % 2 === 0 ? 'rgba(15, 23, 42, 0.3)' : 'transparent',
                          borderBottom: '1px solid var(--border-color, #334155)',
                        }}
                      >
                        <td
                          style={{
                            padding: '0.5rem 1rem',
                            fontWeight: 600,
                            color: 'var(--text-secondary, #94a3b8)',
                            width: '40%',
                            textTransform: 'capitalize',
                          }}
                        >
                          {key.replace(/_/g, ' ')}
                        </td>
                        <td
                          style={{
                            padding: '0.5rem 1rem',
                            color: 'var(--text-primary, #f8fafc)',
                            fontFamily: typeof val === 'number' || typeof val === 'boolean' ? 'monospace' : 'inherit',
                          }}
                        >
                          {typeof val === 'object' && val !== null
                            ? JSON.stringify(val)
                            : String(val)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            {/* Conditions / Qualifications */}
            {activePanel.conditions && activePanel.conditions.length > 0 && (
              <div>
                <h4 style={{ margin: '0 0 0.5rem', fontSize: '0.875rem', color: 'var(--text-secondary, #94a3b8)', textTransform: 'uppercase' }}>
                  Qualification Conditions &amp; Limits
                </h4>
                <ul
                  style={{
                    margin: 0,
                    paddingLeft: '1.25rem',
                    color: 'var(--text-primary, #f8fafc)',
                    fontSize: '0.8125rem',
                    lineHeight: 1.5,
                  }}
                >
                  {activePanel.conditions.map((c, idx) => (
                    <li key={idx}>{c}</li>
                  ))}
                </ul>
              </div>
            )}

            {/* Provenance & Citation Footer */}
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                paddingTop: '1rem',
                borderTop: '1px solid var(--border-color, #334155)',
                fontSize: '0.75rem',
                color: 'var(--text-secondary, #94a3b8)',
              }}
            >
              <div>
                <span>Source Citation: </span>
                <strong style={{ color: 'var(--text-primary, #f8fafc)' }}>{activePanel.source_citation}</strong>
                {activePanel.rule_reference && (
                  <span style={{ marginLeft: '0.5rem', color: 'var(--accent-blue, #38bdf8)' }}>
                    [{activePanel.rule_reference}]
                  </span>
                )}
              </div>
              <a
                href={activePanel.source_url}
                target="_blank"
                rel="noopener noreferrer"
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '0.35rem',
                  color: 'var(--accent-blue, #38bdf8)',
                  textDecoration: 'none',
                  fontWeight: 600,
                }}
              >
                <span>Official Provider Documentation</span>
                <ExternalLink size={12} aria-hidden="true" />
              </a>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
