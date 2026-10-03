import React, { useState } from 'react';
import { Info, X, ExternalLink, ShieldCheck, AlertTriangle } from 'lucide-react';
import { PricingInformationPanelData, CostExplanation } from './tokens';

export interface InformationIconProps {
  /**
   * Complete 17-field structured information panel or concise cost explanation
   */
  panelData?: Partial<PricingInformationPanelData>;
  explanation?: CostExplanation;
  metricLabel?: string;
  size?: 'sm' | 'md' | 'lg';
  onOpenFullPanels?: () => void;
  className?: string;
}

/**
 * Information Icon Component (Prompt 40 / Prompt 21 Item 164)
 * Renders the authoritative 17-field structured content model with official provider documentation link.
 */
export const InformationIcon: React.FC<InformationIconProps> = ({
  panelData,
  explanation,
  metricLabel,
  size = 'md',
  onOpenFullPanels,
  className = '',
}) => {
  const [isOpen, setIsOpen] = useState(false);

  // Synthesize or extract the 17 fields
  const service = panelData?.service || explanation?.metricName || metricLabel || 'Cloud Resource';
  const pricingModel = panelData?.pricing_model || 'On-Demand';
  const region = panelData?.region || explanation?.region || 'us-east-1';
  const configuration = panelData?.configuration || { tier: 'General Purpose' };
  const unitRate = panelData?.unit_rate ?? explanation?.rate ?? 0.192;
  const currency = panelData?.currency || explanation?.currency || 'USD';
  const billingUnit = panelData?.billing_unit || explanation?.unit || 'Hrs';
  const monthlyEstimate = panelData?.monthly_estimate ?? (unitRate ? Number((unitRate * 730).toFixed(2)) : null);
  const freeTierStatus = panelData?.free_tier_status || 'Standard Paid Service';
  const freeAllowance = panelData?.free_tier_allowance;
  const additionalUsageRate = panelData?.additional_usage_rate ?? unitRate;
  const dataTransferNote =
    panelData?.data_transfer_note || 'Standard internet egress charges apply beyond free allowances.';
  const storageNote =
    panelData?.storage_note || 'Persistent storage billed independently from compute runtime.';
  const discountApplicability = panelData?.discount_applicability || 'No contract discounts applied';
  const commitmentApplicability = panelData?.commitment_applicability || 'Eligible for 1-Year or 3-Year Commitments';
  const taxTreatment = panelData?.tax_treatment || 'Exclusive of applicable statutory sales tax or VAT.';
  const pricingSource = panelData?.source_traceability?.pricing_source || explanation?.pricingSource || 'aws_price_list_bulk';
  const sourceUrl =
    panelData?.source_traceability?.source_url || explanation?.sourceUrl || 'https://aws.amazon.com/pricing/';
  const lastUpdated =
    panelData?.source_traceability?.retrieval_timestamp || explanation?.retrievalTimestamp || new Date().toISOString();
  const effectiveDate =
    panelData?.source_traceability?.effective_date || explanation?.effectiveDate || new Date().toISOString();
  const isStale = panelData?.freshness?.is_stale || explanation?.isStale || false;

  const iconDimension = size === 'sm' ? 12 : size === 'lg' ? 16 : 14;

  return (
    <span style={{ position: 'relative', display: 'inline-flex', alignItems: 'center' }} className={className}>
      <button
        type="button"
        aria-label={`Inspect 17-field pricing details and official source for ${service}`}
        aria-haspopup="dialog"
        aria-expanded={isOpen}
        onClick={() => setIsOpen(!isOpen)}
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          justifyContent: 'center',
          width: iconDimension + 6,
          height: iconDimension + 6,
          borderRadius: '50%',
          border: '1px solid var(--border-color, #334155)',
          backgroundColor: isOpen ? 'var(--accent-blue, #38bdf8)' : 'transparent',
          color: isOpen ? '#0f172a' : 'var(--text-secondary, #94a3b8)',
          cursor: 'pointer',
          padding: 0,
          transition: 'all 0.15s ease',
        }}
        title={`View pricing specification and official source for ${service}`}
      >
        <Info size={iconDimension} aria-hidden="true" />
      </button>

      {/* Accessible 17-Field Popover Modal */}
      {isOpen && (
        <div
          role="dialog"
          aria-label={`Pricing Content Model: ${service}`}
          style={{
            position: 'absolute',
            top: 'calc(100% + 8px)',
            left: 0,
            zIndex: 100,
            width: '420px',
            maxWidth: '90vw',
            backgroundColor: 'var(--bg-secondary, #1e293b)',
            border: '1px solid var(--border-color, #334155)',
            borderRadius: '10px',
            padding: '1.25rem',
            boxShadow: '0 20px 25px -5px rgba(0, 0, 0, 0.5), 0 8px 10px -6px rgba(0, 0, 0, 0.4)',
            fontSize: '0.8125rem',
            color: 'var(--text-primary, #f8fafc)',
            textAlign: 'left',
          }}
        >
          {/* Header */}
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'flex-start',
              borderBottom: '1px solid var(--border-color, #334155)',
              paddingBottom: '0.75rem',
              marginBottom: '0.75rem',
            }}
          >
            <div>
              <div style={{ fontSize: '0.7rem', textTransform: 'uppercase', color: 'var(--accent-blue, #38bdf8)', fontWeight: 700 }}>
                Prompt 21 Content Model (17 Fields)
              </div>
              <strong style={{ fontSize: '1rem', color: 'var(--text-primary, #f8fafc)' }}>
                {service}
              </strong>
            </div>
            <button
              type="button"
              aria-label="Close pricing information panel"
              onClick={() => setIsOpen(false)}
              style={{
                background: 'transparent',
                border: 'none',
                color: 'var(--text-secondary, #94a3b8)',
                cursor: 'pointer',
                padding: '2px',
              }}
            >
              <X size={16} aria-hidden="true" />
            </button>
          </div>

          {/* Stale Warning Banner if applicable */}
          {isStale && (
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '0.5rem',
                backgroundColor: 'rgba(239, 68, 68, 0.15)',
                border: '1px solid #dc2626',
                color: '#f87171',
                borderRadius: '6px',
                padding: '0.5rem',
                marginBottom: '0.75rem',
                fontSize: '0.75rem',
              }}
            >
              <AlertTriangle size={14} aria-hidden="true" />
              <span>Warning: Rate card exceeds staleness threshold. Last retrieval: {new Date(lastUpdated).toLocaleDateString()}</span>
            </div>
          )}

          {/* The 17 Fields Grid */}
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: '1fr 1fr',
              gap: '0.5rem 1rem',
              maxHeight: '340px',
              overflowY: 'auto',
              paddingRight: '0.25rem',
            }}
          >
            {/* 1. Pricing Model */}
            <div>
              <span style={{ color: 'var(--text-secondary, #94a3b8)', fontSize: '0.75rem' }}>1. Pricing Model</span>
              <div style={{ fontWeight: 600 }}>{pricingModel}</div>
            </div>

            {/* 2. Region */}
            <div>
              <span style={{ color: 'var(--text-secondary, #94a3b8)', fontSize: '0.75rem' }}>2. Region</span>
              <div style={{ fontWeight: 600 }}>{region}</div>
            </div>

            {/* 3. Configuration */}
            <div style={{ gridColumn: 'span 2' }}>
              <span style={{ color: 'var(--text-secondary, #94a3b8)', fontSize: '0.75rem' }}>3. Configuration</span>
              <div style={{ fontFamily: 'monospace', fontSize: '0.75rem', color: '#cbd5e1' }}>
                {Object.entries(configuration)
                  .map(([k, v]) => `${k}: ${v}`)
                  .join(' | ')}
              </div>
            </div>

            {/* 4. Unit Rate */}
            <div>
              <span style={{ color: 'var(--text-secondary, #94a3b8)', fontSize: '0.75rem' }}>4. Unit Rate</span>
              <div style={{ fontWeight: 600, color: '#38bdf8' }}>
                {currency} {Number(unitRate).toFixed(4)}
              </div>
            </div>

            {/* 5. Monthly Estimate */}
            <div>
              <span style={{ color: 'var(--text-secondary, #94a3b8)', fontSize: '0.75rem' }}>5. Monthly Estimate</span>
              <div style={{ fontWeight: 600, color: '#34d399' }}>
                {monthlyEstimate !== null ? `${currency} ${Number(monthlyEstimate).toFixed(2)}` : 'N/A'}
              </div>
            </div>

            {/* 6. Free Tier Status */}
            <div>
              <span style={{ color: 'var(--text-secondary, #94a3b8)', fontSize: '0.75rem' }}>6. Free-Tier Status</span>
              <div>{freeTierStatus}</div>
            </div>

            {/* 7. Free Tier Allowance */}
            <div>
              <span style={{ color: 'var(--text-secondary, #94a3b8)', fontSize: '0.75rem' }}>7. Free Allowance</span>
              <div>{freeAllowance ? `${freeAllowance.quantity} ${freeAllowance.unit}` : 'None'}</div>
            </div>

            {/* 8. Additional Usage Rate */}
            <div>
              <span style={{ color: 'var(--text-secondary, #94a3b8)', fontSize: '0.75rem' }}>8. Additional Rate</span>
              <div>{currency} {Number(additionalUsageRate).toFixed(4)}/{billingUnit}</div>
            </div>

            {/* 9. Currency */}
            <div>
              <span style={{ color: 'var(--text-secondary, #94a3b8)', fontSize: '0.75rem' }}>9. Currency</span>
              <div>{currency} (ISO 4217)</div>
            </div>

            {/* 10. Billing Unit */}
            <div>
              <span style={{ color: 'var(--text-secondary, #94a3b8)', fontSize: '0.75rem' }}>10. Billing Unit</span>
              <div>{billingUnit}</div>
            </div>

            {/* 11. Data Transfer Note */}
            <div style={{ gridColumn: 'span 2' }}>
              <span style={{ color: 'var(--text-secondary, #94a3b8)', fontSize: '0.75rem' }}>11. Data Transfer Note</span>
              <div style={{ fontSize: '0.75rem' }}>{dataTransferNote}</div>
            </div>

            {/* 12. Storage Note */}
            <div style={{ gridColumn: 'span 2' }}>
              <span style={{ color: 'var(--text-secondary, #94a3b8)', fontSize: '0.75rem' }}>12. Storage Note</span>
              <div style={{ fontSize: '0.75rem' }}>{storageNote}</div>
            </div>

            {/* 13. Discount Applicability */}
            <div style={{ gridColumn: 'span 2' }}>
              <span style={{ color: 'var(--text-secondary, #94a3b8)', fontSize: '0.75rem' }}>13. Discount Applicability</span>
              <div style={{ fontSize: '0.75rem' }}>{discountApplicability}</div>
            </div>

            {/* 14. Commitment Applicability */}
            <div style={{ gridColumn: 'span 2' }}>
              <span style={{ color: 'var(--text-secondary, #94a3b8)', fontSize: '0.75rem' }}>14. Commitment Applicability</span>
              <div style={{ fontSize: '0.75rem' }}>{commitmentApplicability}</div>
            </div>

            {/* 15. Tax Treatment */}
            <div style={{ gridColumn: 'span 2' }}>
              <span style={{ color: 'var(--text-secondary, #94a3b8)', fontSize: '0.75rem' }}>15. Tax Treatment</span>
              <div style={{ fontSize: '0.75rem' }}>{taxTreatment}</div>
            </div>

            {/* 16. Pricing Source */}
            <div>
              <span style={{ color: 'var(--text-secondary, #94a3b8)', fontSize: '0.75rem' }}>16. Pricing Source</span>
              <div style={{ fontFamily: 'monospace', fontSize: '0.75rem' }}>{pricingSource}</div>
            </div>

            {/* 17. Last Updated & Effective Date */}
            <div>
              <span style={{ color: 'var(--text-secondary, #94a3b8)', fontSize: '0.75rem' }}>17. Ingested & Effective</span>
              <div style={{ fontSize: '0.75rem' }}>
                {new Date(lastUpdated).toLocaleDateString()} (Eff: {new Date(effectiveDate).toLocaleDateString()})
              </div>
            </div>
          </div>

          {/* Action Row */}
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              borderTop: '1px solid var(--border-color, #334155)',
              paddingTop: '0.75rem',
              marginTop: '0.75rem',
            }}
          >
            <a
              href={sourceUrl}
              target="_blank"
              rel="noopener noreferrer"
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '0.35rem',
                color: 'var(--accent-blue, #38bdf8)',
                textDecoration: 'none',
                fontWeight: 600,
                fontSize: '0.75rem',
              }}
            >
              <span>Official Provider Docs</span>
              <ExternalLink size={12} aria-hidden="true" />
            </a>

            {onOpenFullPanels && (
              <button
                type="button"
                onClick={() => {
                  setIsOpen(false);
                  onOpenFullPanels();
                }}
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '0.35rem',
                  padding: '0.35rem 0.65rem',
                  backgroundColor: 'rgba(56, 189, 248, 0.1)',
                  border: '1px solid #38bdf8',
                  color: '#38bdf8',
                  borderRadius: '4px',
                  cursor: 'pointer',
                  fontSize: '0.75rem',
                  fontWeight: 600,
                }}
              >
                <ShieldCheck size={12} aria-hidden="true" />
                <span>View All 11 Explanation Panels</span>
              </button>
            )}
          </div>
        </div>
      )}
    </span>
  );
};
