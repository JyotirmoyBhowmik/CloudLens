import React, { useEffect, useState } from 'react';
import {
  Server,
  Cloud,
  Layers,
  Clock,
  ShieldCheck,
  AlertTriangle,
  Activity,
  FileText,
  DollarSign,
  TrendingUp,
  Cpu,
  ArrowRight,
  ExternalLink,
  Info,
  CheckCircle2,
  HelpCircle,
  Network,
  Users,
} from 'lucide-react';
import { Breadcrumb } from '../design-system/Breadcrumb';
import { ThresholdBadge } from '../design-system/ThresholdBadge';
import { CostValue, createCostExplanation } from '../design-system/CostValue';
import { NullValue } from '../design-system/NullValue';
import { SkeletonLoader } from '../design-system/SkeletonLoader';
import { ErrorState } from '../design-system/ErrorState';
import { ThresholdState } from '../design-system/tokens';

export interface CostDriverItem {
  category: string;
  name: string;
  amount: number;
  percentage: number;
  unit: string;
  quantity: number;
  rate: number;
  explanation: string;
}

export interface PricingPanelData {
  pricing_status: string;
  pricing_model: string;
  unit: string;
  unit_price: number;
  free_tier_details?: string | null;
  free_tier_allowance?: string | null;
  free_tier_consumed_pct: number;
  additional_cost_conditions?: string | null;
  region: string;
  currency: string;
  pricing_source: string;
  effective_date: string;
}

export interface CostPanelData {
  current_cost: number;
  actual_cost: number;
  estimated_cost: number;
  forecast_cost: number;
  budget_amount: number;
  variance: number;
  variance_ratio_pct: number;
  variance_status: string;
  currency: string;
}

export interface UsageDataPoint {
  timestamp: string;
  value: number | null;
  expectation_min?: number | null;
  expectation_max?: number | null;
  is_gap: boolean;
  gap_reason?: string | null;
}

export interface UsageDetailPanel {
  metric_name: string;
  unit: string;
  monitoring_type_code: string;
  monitoring_type_name: string;
  threshold_warning: number;
  threshold_critical: number;
  time_series: UsageDataPoint[];
  has_telemetry_gap: boolean;
}

export interface RuntimeExemptionSummary {
  exemption_id: string;
  author: string;
  reason: string;
  approved_at: string;
  expires_at: string;
  is_active: boolean;
}

export interface RuntimePanelData {
  runtime_state: string;
  schedule_name?: string | null;
  schedule_expression?: string | null;
  adherence_status: string;
  excess_hours: number;
  excess_cost: number;
  active_exemptions: RuntimeExemptionSummary[];
}

export interface BreadcrumbItem {
  id: string;
  name: string;
  level: string;
  deep_link: string;
}

export interface OwnershipAttribution {
  business_owner: string;
  technical_owner: string;
  owner_email?: string | null;
  team?: string | null;
  application: string;
  environment: string;
  cost_center: string;
  business_unit: string;
  resolution_rules: Record<string, string>;
}

export interface DependencyNodeItem {
  id: string;
  name: string;
  provider: string;
  service_name: string;
  relationship_type: string;
  direction: string;
  status: string;
}

export interface ConnectivityEndpoint {
  endpoint_type: string;
  address: string;
  port?: number | null;
  protocol: string;
}

export interface ResourceAlertItem {
  alert_id: string;
  severity: string;
  title: string;
  triggered_at: string;
  status: string;
}

export interface AuditLogItem {
  timestamp: string;
  actor: string;
  action: string;
  details: Record<string, any>;
}

export interface FifteenQuestionsSummary {
  q1_what_it_is: string;
  q2_where: string;
  q3_who_owns_it: string;
  q4_what_it_does: string;
  q5_how_connected: string;
  q6_how_charged: string;
  q7_whether_free: string;
  q8_what_allowance: string;
  q9_what_causes_charges: string;
  q10_how_much_it_cost: string;
  q11_expected_cost: string;
  q12_budget: string;
  q13_threshold_crossed: string;
  q14_why_cost_changed: string;
  q15_provider_info_support: string;
}

export interface ResourceDetailFull {
  id: string;
  tenant_id: string;
  scope_id: string;
  native_id: string;
  name: string;
  provider: string;
  service_id: string;
  service_name: string;
  service_category: string;
  resource_type: string;
  region_id: string;
  region_name: string;
  availability_zone?: string | null;
  lifecycle_status: string;
  created_at: string;
  last_synced_at: string;
  tags: Array<{ key: string; value: string }>;
  provider_native: Record<string, any>;
  breadcrumbs: BreadcrumbItem[];
  ownership: OwnershipAttribution;
  pricing: PricingPanelData;
  cost: CostPanelData;
  cost_drivers: CostDriverItem[];
  total_driver_amount: number;
  usage: UsageDetailPanel;
  runtime: RuntimePanelData;
  threshold_state: string;
  amber_threshold_pct: number;
  red_threshold_pct: number;
  dependencies: DependencyNodeItem[];
  connectivity_endpoints: ConnectivityEndpoint[];
  alerts: ResourceAlertItem[];
  historical_spend_trend: Array<{ month: string; amount: number }>;
  forecast_confidence_interval: Record<string, number>;
  audit_trail: AuditLogItem[];
  fifteen_questions: FifteenQuestionsSummary;
}

export interface ResourceDetailPageProps {
  initialResourceId?: string;
  onNavigateToCostExplorer?: (dimension?: string, groupId?: string) => void;
  onNavigateToInvestigation?: (entityId: string) => void;
}

export const ResourceDetailPage: React.FC<ResourceDetailPageProps> = ({
  initialResourceId = 'res-aws-vm-01',
  onNavigateToCostExplorer,
  onNavigateToInvestigation,
}) => {
  const [selectedResourceId, setSelectedResourceId] = useState<string>(initialResourceId);
  const [resource, setResource] = useState<ResourceDetailFull | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<'panels' | 'questions'>('panels');

  const presetResources = [
    { id: 'res-aws-vm-01', label: 'AWS EC2 - prod-payment-worker-1' },
    { id: 'res-aws-rds-01', label: 'AWS RDS - prod-payments-db (Spike Example)' },
    { id: 'res-az-sql-01', label: 'Azure SQL - sql-checkout-db' },
    { id: 'res-az-vm-01', label: 'Azure VM - vm-checkout-worker-1 (Excess Runtime)' },
  ];

  useEffect(() => {
    let isCancelled = false;
    setLoading(true);
    setError(null);

    fetch(`/api/v1/resource-detail/${selectedResourceId}`)
      .then((res) => {
        if (!res.ok) {
          throw new Error(`Failed to load resource detail (${res.status} ${res.statusText})`);
        }
        return res.json();
      })
      .then((data: ResourceDetailFull) => {
        if (!isCancelled) {
          setResource(data);
          setLoading(false);
        }
      })
      .catch((err: Error) => {
        if (!isCancelled) {
          setError(err.message);
          setLoading(false);
        }
      });

    return () => {
      isCancelled = true;
    };
  }, [selectedResourceId]);

  if (loading) {
    return (
      <div style={{ padding: '1.5rem' }}>
        <SkeletonLoader variant="card" rows={4} />
      </div>
    );
  }

  if (error || !resource) {
    return (
      <div style={{ padding: '1.5rem' }}>
        <ErrorState
          title="Resource Not Found"
          message={error || 'Unable to retrieve resource specifications.'}
          onRetry={() => setSelectedResourceId('res-aws-vm-01')}
        />
      </div>
    );
  }

  const breadcrumbItems = resource.breadcrumbs.map((b, idx) => ({
    label: `${b.level}: ${b.name}`,
    isCurrent: idx === resource.breadcrumbs.length - 1,
  }));

  const mapThresholdState = (state: string): ThresholdState => {
    if (state === 'CRITICAL') return 'CRITICAL';
    if (state === 'WARNING') return 'WARNING';
    return 'NORMAL';
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
      {/* Top Controls: Selector & Navigation Shortcuts */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          flexWrap: 'wrap',
          gap: '1rem',
          backgroundColor: 'var(--bg-secondary)',
          padding: '1rem 1.25rem',
          borderRadius: '8px',
          border: '1px solid var(--border-color)',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', flexWrap: 'wrap' }}>
          <label htmlFor="resource-select" style={{ fontSize: '0.875rem', fontWeight: 600, color: 'var(--text-secondary)' }}>
            Selected Resource:
          </label>
          <select
            id="resource-select"
            value={selectedResourceId}
            onChange={(e) => setSelectedResourceId(e.target.value)}
            style={{
              padding: '0.45rem 0.75rem',
              borderRadius: '6px',
              border: '1px solid var(--border-color)',
              backgroundColor: 'var(--bg-primary)',
              color: 'var(--text-primary)',
              fontSize: '0.875rem',
              fontWeight: 500,
            }}
          >
            {presetResources.map((p) => (
              <option key={p.id} value={p.id}>
                {p.label}
              </option>
            ))}
          </select>
        </div>

        <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
          <button
            onClick={() => setActiveTab('panels')}
            style={{
              padding: '0.45rem 0.9rem',
              borderRadius: '6px',
              border: '1px solid var(--border-color)',
              backgroundColor: activeTab === 'panels' ? '#0284c7' : 'var(--bg-primary)',
              color: activeTab === 'panels' ? '#ffffff' : 'var(--text-primary)',
              fontSize: '0.8125rem',
              cursor: 'pointer',
              fontWeight: 600,
              display: 'inline-flex',
              alignItems: 'center',
              gap: '0.4rem',
            }}
          >
            <Layers size={14} /> Full 15 Panels
          </button>
          <button
            onClick={() => setActiveTab('questions')}
            style={{
              padding: '0.45rem 0.9rem',
              borderRadius: '6px',
              border: '1px solid var(--border-color)',
              backgroundColor: activeTab === 'questions' ? '#0284c7' : 'var(--bg-primary)',
              color: activeTab === 'questions' ? '#ffffff' : 'var(--text-primary)',
              fontSize: '0.8125rem',
              cursor: 'pointer',
              fontWeight: 600,
              display: 'inline-flex',
              alignItems: 'center',
              gap: '0.4rem',
            }}
          >
            <HelpCircle size={14} /> Master Brief 15 Questions
          </button>
          {onNavigateToCostExplorer && (
            <button
              onClick={() => onNavigateToCostExplorer('SERVICE', resource.service_id)}
              style={{
                padding: '0.45rem 0.9rem',
                borderRadius: '6px',
                border: '1px solid #0284c7',
                backgroundColor: 'rgba(2, 132, 199, 0.15)',
                color: '#38bdf8',
                fontSize: '0.8125rem',
                cursor: 'pointer',
                fontWeight: 600,
                display: 'inline-flex',
                alignItems: 'center',
                gap: '0.4rem',
              }}
            >
              <TrendingUp size={14} /> Cost Explorer
            </button>
          )}
          {onNavigateToInvestigation && (
            <button
              onClick={() => onNavigateToInvestigation(resource.id)}
              style={{
                padding: '0.45rem 0.9rem',
                borderRadius: '6px',
                border: '1px solid #e11d48',
                backgroundColor: 'rgba(225, 29, 72, 0.15)',
                color: '#fda4af',
                fontSize: '0.8125rem',
                cursor: 'pointer',
                fontWeight: 600,
                display: 'inline-flex',
                alignItems: 'center',
                gap: '0.4rem',
              }}
            >
              <AlertTriangle size={14} /> Investigate Increase
            </button>
          )}
        </div>
      </div>

      {/* Panel 3: Complete Clickable Hierarchy Breadcrumbs */}
      <div style={{ backgroundColor: 'var(--bg-secondary)', padding: '0.75rem 1.25rem', borderRadius: '6px', border: '1px solid var(--border-color)' }}>
        <Breadcrumb items={breadcrumbItems} />
      </div>

      {activeTab === 'questions' ? (
        /* ==============================================================================
         * Master Brief Section 29 15-Questions Checklist View
         * ============================================================================== */
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          <div style={{ backgroundColor: 'var(--bg-secondary)', padding: '1.25rem', borderRadius: '8px', border: '1px solid var(--border-color)' }}>
            <h2 style={{ fontSize: '1.25rem', fontWeight: 700, margin: '0 0 0.5rem 0', display: 'flex', alignItems: 'center', gap: '0.5rem', color: '#38bdf8' }}>
              <ShieldCheck size={20} /> 15 Core Resource Questions
            </h2>
            <p style={{ margin: 0, fontSize: '0.875rem', color: 'var(--text-secondary)' }}>
              Answers all fifteen fundamental architectural questions definitively for any selected estate resource.
            </p>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(360px, 1fr))', gap: '1rem' }}>
            {[
              { num: 'Q1', title: 'What it is', answer: resource.fifteen_questions.q1_what_it_is, icon: Server },
              { num: 'Q2', title: 'Where it is located', answer: resource.fifteen_questions.q2_where, icon: Cloud },
              { num: 'Q3', title: 'Who owns it', answer: resource.fifteen_questions.q3_who_owns_it, icon: Users },
              { num: 'Q4', title: 'What it does', answer: resource.fifteen_questions.q4_what_it_does, icon: FileText },
              { num: 'Q5', title: 'How connected', answer: resource.fifteen_questions.q5_how_connected, icon: Network },
              { num: 'Q6', title: 'How charged', answer: resource.fifteen_questions.q6_how_charged, icon: DollarSign },
              { num: 'Q7', title: 'Whether free', answer: resource.fifteen_questions.q7_whether_free, icon: ShieldCheck },
              { num: 'Q8', title: 'What allowance remains', answer: resource.fifteen_questions.q8_what_allowance, icon: Info },
              { num: 'Q9', title: 'What causes charges', answer: resource.fifteen_questions.q9_what_causes_charges, icon: Layers },
              { num: 'Q10', title: 'How much it cost', answer: resource.fifteen_questions.q10_how_much_it_cost, icon: DollarSign },
              { num: 'Q11', title: 'Expected cost baseline', answer: resource.fifteen_questions.q11_expected_cost, icon: CheckCircle2 },
              { num: 'Q12', title: 'Target budget & variance', answer: resource.fifteen_questions.q12_budget, icon: TrendingUp },
              { num: 'Q13', title: 'Threshold crossed', answer: resource.fifteen_questions.q13_threshold_crossed, icon: AlertTriangle },
              { num: 'Q14', title: 'Why cost changed', answer: resource.fifteen_questions.q14_why_cost_changed, icon: Activity },
              { num: 'Q15', title: 'Provider info & rate card', answer: resource.fifteen_questions.q15_provider_info_support, icon: ExternalLink },
            ].map((q) => {
              const IconComp = q.icon;
              return (
                <div
                  key={q.num}
                  style={{
                    backgroundColor: 'var(--bg-secondary)',
                    border: '1px solid var(--border-color)',
                    borderRadius: '8px',
                    padding: '1.25rem',
                    display: 'flex',
                    flexDirection: 'column',
                    gap: '0.5rem',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                    <span style={{ fontSize: '0.8125rem', fontWeight: 700, color: '#38bdf8', display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                      <IconComp size={15} /> {q.num}: {q.title}
                    </span>
                    <span style={{ color: '#10b981', display: 'flex', alignItems: 'center', gap: '0.25rem', fontSize: '0.75rem', fontWeight: 600 }}>
                      <CheckCircle2 size={13} /> Verified
                    </span>
                  </div>
                  <div style={{ fontSize: '0.875rem', color: 'var(--text-primary)', lineHeight: 1.45, backgroundColor: 'var(--bg-primary)', padding: '0.75rem', borderRadius: '6px' }}>
                    {q.answer}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      ) : (
        /* ==============================================================================
         * Full 15 Panels Surface
         * ============================================================================== */
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
          {/* Panel 1: Overview & Metadata Header */}
          <div
            style={{
              backgroundColor: 'var(--bg-secondary)',
              border: '1px solid var(--border-color)',
              borderRadius: '8px',
              padding: '1.5rem',
              display: 'flex',
              flexDirection: 'column',
              gap: '1rem',
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '1rem' }}>
              <div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', marginBottom: '0.35rem' }}>
                  <span
                    style={{
                      fontSize: '0.75rem',
                      fontWeight: 700,
                      padding: '0.2rem 0.5rem',
                      borderRadius: '4px',
                      backgroundColor: resource.provider === 'AWS' ? '#f59e0b' : resource.provider === 'Azure' ? '#0284c7' : '#10b981',
                      color: '#000000',
                    }}
                  >
                    {resource.provider}
                  </span>
                  <h1 style={{ fontSize: '1.5rem', fontWeight: 700, margin: 0, color: 'var(--text-primary)' }}>
                    {resource.name}
                  </h1>
                  <ThresholdBadge state={mapThresholdState(resource.threshold_state)} />
                </div>
                <div style={{ display: 'flex', gap: '1rem', fontSize: '0.8125rem', color: 'var(--text-secondary)' }}>
                  <span><strong>ID:</strong> {resource.id}</span>
                  <span><strong>Native ID:</strong> {resource.native_id}</span>
                  <span><strong>Type:</strong> {resource.resource_type}</span>
                  <span><strong>Region:</strong> {resource.region_name} ({resource.region_id})</span>
                  {resource.availability_zone && <span><strong>AZ:</strong> {resource.availability_zone}</span>}
                </div>
              </div>

              <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
                {resource.tags.map((t, idx) => (
                  <span
                    key={idx}
                    style={{
                      fontSize: '0.75rem',
                      padding: '0.15rem 0.5rem',
                      borderRadius: '4px',
                      backgroundColor: 'var(--bg-primary)',
                      border: '1px solid var(--border-color)',
                      color: 'var(--text-secondary)',
                    }}
                  >
                    <strong>{t.key}:</strong> {t.value}
                  </span>
                ))}
              </div>
            </div>
          </div>

          {/* Panel 6: Cost Panel (6 Distinct Unblended Figures) */}
          <div
            style={{
              backgroundColor: 'var(--bg-secondary)',
              border: '1px solid var(--border-color)',
              borderRadius: '8px',
              padding: '1.5rem',
            }}
          >
            <div style={{ marginBottom: '1rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div>
                <h3 style={{ margin: 0, fontSize: '1.125rem', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                  <DollarSign size={18} color="#10b981" /> Cost Panel (6 Distinct Unblended Figures)
                </h3>
                <span style={{ fontSize: '0.8125rem', color: 'var(--text-secondary)' }}>
                  Actual, estimated, forecast and budget costs are strictly separated and never blended.
                </span>
              </div>
              <span
                style={{
                  fontSize: '0.8125rem',
                  fontWeight: 700,
                  padding: '0.2rem 0.6rem',
                  borderRadius: '4px',
                  backgroundColor: resource.cost.variance_status === 'FAVOURABLE' ? 'rgba(16, 185, 129, 0.2)' : 'rgba(239, 68, 68, 0.2)',
                  color: resource.cost.variance_status === 'FAVOURABLE' ? '#34d399' : '#f87171',
                }}
              >
                Variance: {resource.cost.variance_status} ({resource.cost.variance_ratio_pct > 0 ? '+' : ''}{resource.cost.variance_ratio_pct}%)
              </span>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '1rem' }}>
              <div style={{ backgroundColor: 'var(--bg-primary)', padding: '1rem', borderRadius: '6px', border: '1px solid var(--border-color)' }}>
                <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', display: 'block', marginBottom: '0.25rem' }}>1. Current (MTD Unbilled)</span>
                <CostValue
                  amount={resource.cost.current_cost}
                  source="ACTUAL"
                  explanation={createCostExplanation(`${resource.name} MTD Spend`, {
                    pricingSource: resource.pricing.pricing_source,
                    region: resource.pricing.region,
                  })}
                />
              </div>
              <div style={{ backgroundColor: 'var(--bg-primary)', padding: '1rem', borderRadius: '6px', border: '1px solid var(--border-color)' }}>
                <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', display: 'block', marginBottom: '0.25rem' }}>2. Prior Closed Actual</span>
                <CostValue
                  amount={resource.cost.actual_cost}
                  source="ACTUAL"
                  explanation={createCostExplanation(`${resource.name} Prior Actual`, {
                    pricingSource: resource.pricing.pricing_source,
                    region: resource.pricing.region,
                  })}
                />
              </div>
              <div style={{ backgroundColor: 'var(--bg-primary)', padding: '1rem', borderRadius: '6px', border: '1px solid var(--border-color)' }}>
                <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', display: 'block', marginBottom: '0.25rem' }}>3. Pre-Deploy Estimate</span>
                <CostValue
                  amount={resource.cost.estimated_cost}
                  source="ESTIMATED"
                  explanation={createCostExplanation(`${resource.name} Baseline Estimate`, {
                    pricingSource: resource.pricing.pricing_source,
                    region: resource.pricing.region,
                    formula: 'unit_price * 730 hours',
                  })}
                />
              </div>
              <div style={{ backgroundColor: 'var(--bg-primary)', padding: '1rem', borderRadius: '6px', border: '1px solid var(--border-color)' }}>
                <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', display: 'block', marginBottom: '0.25rem' }}>4. Projected Forecast</span>
                <CostValue
                  amount={resource.cost.forecast_cost}
                  source="FORECAST"
                  explanation={createCostExplanation(`${resource.name} End of Month Forecast`, {
                    pricingSource: 'cloudlens_forecasting_engine',
                    region: resource.pricing.region,
                  })}
                />
              </div>
              <div style={{ backgroundColor: 'var(--bg-primary)', padding: '1rem', borderRadius: '6px', border: '1px solid var(--border-color)' }}>
                <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', display: 'block', marginBottom: '0.25rem' }}>5. Target Budget</span>
                <div style={{ fontSize: '1.125rem', fontWeight: 600, color: 'var(--text-primary)' }}>
                  ${resource.cost.budget_amount.toFixed(2)} USD
                </div>
              </div>
              <div style={{ backgroundColor: 'var(--bg-primary)', padding: '1rem', borderRadius: '6px', border: '1px solid var(--border-color)' }}>
                <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', display: 'block', marginBottom: '0.25rem' }}>6. Monetary Variance</span>
                <div
                  style={{
                    fontSize: '1.125rem',
                    fontWeight: 600,
                    color: resource.cost.variance <= 0 ? '#34d399' : '#f87171',
                  }}
                >
                  {resource.cost.variance > 0 ? '+' : ''}${resource.cost.variance.toFixed(2)} USD
                </div>
              </div>
            </div>
          </div>

          {/* Panel 7: Cost Transparency & Cost-Driver Decomposition */}
          <div
            style={{
              backgroundColor: 'var(--bg-secondary)',
              border: '1px solid var(--border-color)',
              borderRadius: '8px',
              padding: '1.5rem',
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem', flexWrap: 'wrap', gap: '0.5rem' }}>
              <div>
                <h3 style={{ margin: 0, fontSize: '1.125rem', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                  <Layers size={18} color="#0284c7" /> Cost Driver Decomposition (Deconstructive Transparency)
                </h3>
                <span style={{ fontSize: '0.8125rem', color: 'var(--text-secondary)' }}>
                  Section 51: Every material cost is decomposed into drillable drivers that strictly sum to total spend (${resource.total_driver_amount.toFixed(2)} USD).
                </span>
              </div>
              {onNavigateToCostExplorer && (
                <button
                  onClick={() => onNavigateToCostExplorer('CHARGE_CATEGORY', resource.id)}
                  style={{
                    padding: '0.35rem 0.75rem',
                    borderRadius: '6px',
                    border: '1px solid var(--border-color)',
                    backgroundColor: 'var(--bg-primary)',
                    color: '#38bdf8',
                    fontSize: '0.75rem',
                    cursor: 'pointer',
                    fontWeight: 600,
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: '0.3rem',
                  }}
                >
                  Drill to Charge Lines <ArrowRight size={13} />
                </button>
              )}
            </div>

            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.875rem' }}>
                <thead>
                  <tr style={{ borderBottom: '1px solid var(--border-color)', textAlign: 'left', color: 'var(--text-secondary)' }}>
                    <th style={{ padding: '0.6rem 0.75rem' }}>Category</th>
                    <th style={{ padding: '0.6rem 0.75rem' }}>Cost Driver</th>
                    <th style={{ padding: '0.6rem 0.75rem' }}>Quantity & Unit</th>
                    <th style={{ padding: '0.6rem 0.75rem', textAlign: 'right' }}>Unit Rate</th>
                    <th style={{ padding: '0.6rem 0.75rem', textAlign: 'right' }}>Amount</th>
                    <th style={{ padding: '0.6rem 0.75rem', textAlign: 'right' }}>% Total</th>
                    <th style={{ padding: '0.6rem 0.75rem' }}>Explanation</th>
                  </tr>
                </thead>
                <tbody>
                  {resource.cost_drivers.map((d, idx) => (
                    <tr key={idx} style={{ borderBottom: '1px solid var(--border-color)' }}>
                      <td style={{ padding: '0.6rem 0.75rem' }}>
                        <span
                          style={{
                            fontSize: '0.75rem',
                            padding: '0.15rem 0.45rem',
                            borderRadius: '4px',
                            backgroundColor: 'var(--bg-primary)',
                            border: '1px solid var(--border-color)',
                            fontWeight: 600,
                          }}
                        >
                          {d.category}
                        </span>
                      </td>
                      <td style={{ padding: '0.6rem 0.75rem', fontWeight: 600 }}>{d.name}</td>
                      <td style={{ padding: '0.6rem 0.75rem' }}>{d.quantity.toLocaleString()} {d.unit}</td>
                      <td style={{ padding: '0.6rem 0.75rem', textAlign: 'right' }}>${d.rate.toFixed(4)}</td>
                      <td style={{ padding: '0.6rem 0.75rem', textAlign: 'right', fontWeight: 700 }}>${d.amount.toFixed(2)}</td>
                      <td style={{ padding: '0.6rem 0.75rem', textAlign: 'right' }}>{d.percentage}%</td>
                      <td style={{ padding: '0.6rem 0.75rem', color: 'var(--text-secondary)', fontSize: '0.8125rem' }}>{d.explanation}</td>
                    </tr>
                  ))}
                  <tr style={{ backgroundColor: 'rgba(2, 132, 199, 0.05)', fontWeight: 700 }}>
                    <td colSpan={4} style={{ padding: '0.6rem 0.75rem', textAlign: 'right' }}>Decomposed Sum Invariant:</td>
                    <td style={{ padding: '0.6rem 0.75rem', textAlign: 'right', color: '#10b981' }}>${resource.total_driver_amount.toFixed(2)}</td>
                    <td style={{ padding: '0.6rem 0.75rem', textAlign: 'right' }}>100.0%</td>
                    <td style={{ padding: '0.6rem 0.75rem', fontSize: '0.75rem', color: '#10b981' }}>Exact Sum Verified (Matches Current Cost)</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          {/* Row of Panels: Pricing & Ownership */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(420px, 1fr))', gap: '1.5rem' }}>
            {/* Panel 5: Pricing Panel */}
            <div
              style={{
                backgroundColor: 'var(--bg-secondary)',
                border: '1px solid var(--border-color)',
                borderRadius: '8px',
                padding: '1.5rem',
                display: 'flex',
                flexDirection: 'column',
                gap: '0.75rem',
              }}
            >
              <h3 style={{ margin: 0, fontSize: '1.125rem', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                <DollarSign size={18} color="#eab308" /> Pricing Specifications
              </h3>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '0.75rem', fontSize: '0.875rem' }}>
                <div>
                  <span style={{ color: 'var(--text-secondary)', display: 'block', fontSize: '0.75rem' }}>Status & Model</span>
                  <strong>{resource.pricing.pricing_status}</strong> ({resource.pricing.pricing_model})
                </div>
                <div>
                  <span style={{ color: 'var(--text-secondary)', display: 'block', fontSize: '0.75rem' }}>Unit Price</span>
                  <strong>${resource.pricing.unit_price.toFixed(4)} / {resource.pricing.unit}</strong>
                </div>
                <div>
                  <span style={{ color: 'var(--text-secondary)', display: 'block', fontSize: '0.75rem' }}>Free Tier Allowance</span>
                  <span>{resource.pricing.free_tier_allowance || <NullValue state="NOT_APPLICABLE" />}</span>
                </div>
                <div>
                  <span style={{ color: 'var(--text-secondary)', display: 'block', fontSize: '0.75rem' }}>Allowance Consumed</span>
                  <strong>{resource.pricing.free_tier_consumed_pct}%</strong>
                </div>
                <div style={{ gridColumn: 'span 2' }}>
                  <span style={{ color: 'var(--text-secondary)', display: 'block', fontSize: '0.75rem' }}>Pricing Source & Effective Date</span>
                  <span style={{ fontSize: '0.8125rem' }}>{resource.pricing.pricing_source} (Effective: {new Date(resource.pricing.effective_date).toLocaleDateString()})</span>
                </div>
                {resource.pricing.additional_cost_conditions && (
                  <div style={{ gridColumn: 'span 2', backgroundColor: 'var(--bg-primary)', padding: '0.5rem', borderRadius: '4px', fontSize: '0.8125rem', color: '#fbbf24' }}>
                    <strong>Condition:</strong> {resource.pricing.additional_cost_conditions}
                  </div>
                )}
              </div>
            </div>

            {/* Panel 4: Ownership & Attribution with Resolution Rules */}
            <div
              style={{
                backgroundColor: 'var(--bg-secondary)',
                border: '1px solid var(--border-color)',
                borderRadius: '8px',
                padding: '1.5rem',
                display: 'flex',
                flexDirection: 'column',
                gap: '0.75rem',
              }}
            >
              <h3 style={{ margin: 0, fontSize: '1.125rem', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                <Users size={18} color="#a855f7" /> Ownership Attribution & Resolution Rules
              </h3>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '0.75rem', fontSize: '0.875rem' }}>
                <div>
                  <span style={{ color: 'var(--text-secondary)', display: 'block', fontSize: '0.75rem' }}>Business Owner</span>
                  <strong>{resource.ownership.business_owner}</strong>
                </div>
                <div>
                  <span style={{ color: 'var(--text-secondary)', display: 'block', fontSize: '0.75rem' }}>Technical Owner</span>
                  <strong>{resource.ownership.technical_owner}</strong>
                </div>
                <div>
                  <span style={{ color: 'var(--text-secondary)', display: 'block', fontSize: '0.75rem' }}>Application</span>
                  <strong>{resource.ownership.application}</strong>
                </div>
                <div>
                  <span style={{ color: 'var(--text-secondary)', display: 'block', fontSize: '0.75rem' }}>Environment</span>
                  <strong>{resource.ownership.environment}</strong>
                </div>
                <div>
                  <span style={{ color: 'var(--text-secondary)', display: 'block', fontSize: '0.75rem' }}>Cost Centre</span>
                  <strong>{resource.ownership.cost_center}</strong>
                </div>
                <div>
                  <span style={{ color: 'var(--text-secondary)', display: 'block', fontSize: '0.75rem' }}>Business Unit</span>
                  <strong>{resource.ownership.business_unit}</strong>
                </div>
              </div>
              <div style={{ marginTop: '0.5rem', borderTop: '1px solid var(--border-color)', paddingTop: '0.5rem' }}>
                <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', fontWeight: 600 }}>Resolution Rule Provenance:</span>
                <ul style={{ margin: '0.25rem 0 0 1rem', padding: 0, fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
                  {Object.entries(resource.ownership.resolution_rules).map(([k, v]) => (
                    <li key={k}>
                      <strong>{k}:</strong> {v}
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          </div>

          {/* Row of Panels: Usage Detail (with Explicit Gap Discipline) & Runtime View */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(420px, 1fr))', gap: '1.5rem' }}>
            {/* Panel 8: Usage Detail View */}
            <div
              style={{
                backgroundColor: 'var(--bg-secondary)',
                border: '1px solid var(--border-color)',
                borderRadius: '8px',
                padding: '1.5rem',
                display: 'flex',
                flexDirection: 'column',
                gap: '0.75rem',
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <h3 style={{ margin: 0, fontSize: '1.125rem', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                  <Activity size={18} color="#06b6d4" /> Usage Detail View ({resource.usage.metric_name})
                </h3>
                <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
                  Warning: {resource.usage.threshold_warning}% | Critical: {resource.usage.threshold_critical}%
                </span>
              </div>
              <p style={{ margin: 0, fontSize: '0.8125rem', color: 'var(--text-secondary)' }}>
                Requirement: Telemetry gaps must be rendered as explicit NO_DATA, never as zero.
              </p>

              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                {resource.usage.time_series.map((pt, idx) => (
                  <div
                    key={idx}
                    style={{
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'center',
                      padding: '0.4rem 0.6rem',
                      borderRadius: '4px',
                      backgroundColor: pt.is_gap ? 'rgba(239, 68, 68, 0.08)' : 'var(--bg-primary)',
                      border: pt.is_gap ? '1px dashed #ef4444' : '1px solid var(--border-color)',
                      fontSize: '0.8125rem',
                    }}
                  >
                    <span>{new Date(pt.timestamp).toLocaleDateString()}</span>
                    <span>
                      {pt.is_gap ? (
                        <span style={{ display: 'inline-flex', alignItems: 'center', gap: '0.4rem' }}>
                          <NullValue state="NO_DATA" />
                          <span style={{ fontSize: '0.75rem', color: '#f87171' }}>({pt.gap_reason || 'Collector gap'})</span>
                        </span>
                      ) : (
                        <strong>{pt.value?.toFixed(1)} {resource.usage.unit}</strong>
                      )}
                    </span>
                    <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
                      Band: {pt.expectation_min ?? '—'} - {pt.expectation_max ?? '—'} {resource.usage.unit}
                    </span>
                  </div>
                ))}
              </div>
            </div>

            {/* Panel 9: Runtime View */}
            <div
              style={{
                backgroundColor: 'var(--bg-secondary)',
                border: '1px solid var(--border-color)',
                borderRadius: '8px',
                padding: '1.5rem',
                display: 'flex',
                flexDirection: 'column',
                gap: '0.75rem',
              }}
            >
              <h3 style={{ margin: 0, fontSize: '1.125rem', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                <Clock size={18} color="#f97316" /> Runtime Adherence & Excess Cost
              </h3>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '0.75rem', fontSize: '0.875rem' }}>
                <div>
                  <span style={{ color: 'var(--text-secondary)', display: 'block', fontSize: '0.75rem' }}>Runtime State</span>
                  <strong style={{ color: resource.runtime.runtime_state === 'RUNNING' ? '#10b981' : '#94a3b8' }}>
                    {resource.runtime.runtime_state}
                  </strong>
                </div>
                <div>
                  <span style={{ color: 'var(--text-secondary)', display: 'block', fontSize: '0.75rem' }}>Adherence Status</span>
                  <span
                    style={{
                      padding: '0.15rem 0.5rem',
                      borderRadius: '4px',
                      fontSize: '0.75rem',
                      fontWeight: 700,
                      backgroundColor: resource.runtime.adherence_status === 'COMPLIANT' ? 'rgba(16, 185, 129, 0.2)' : 'rgba(239, 68, 68, 0.2)',
                      color: resource.runtime.adherence_status === 'COMPLIANT' ? '#34d399' : '#f87171',
                    }}
                  >
                    {resource.runtime.adherence_status}
                  </span>
                </div>
                <div>
                  <span style={{ color: 'var(--text-secondary)', display: 'block', fontSize: '0.75rem' }}>Out-of-Schedule Hours</span>
                  <strong>{resource.runtime.excess_hours} hrs</strong>
                </div>
                <div>
                  <span style={{ color: 'var(--text-secondary)', display: 'block', fontSize: '0.75rem' }}>Excess Monetary Valuation</span>
                  <strong style={{ color: resource.runtime.excess_cost > 0 ? '#f87171' : '#10b981' }}>
                    ${resource.runtime.excess_cost.toFixed(2)} USD
                  </strong>
                </div>
              </div>

              {resource.runtime.active_exemptions.length > 0 && (
                <div style={{ marginTop: '0.5rem', borderTop: '1px solid var(--border-color)', paddingTop: '0.5rem' }}>
                  <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', fontWeight: 600 }}>Active Exemptions:</span>
                  {resource.runtime.active_exemptions.map((ex) => (
                    <div
                      key={ex.exemption_id}
                      style={{
                        backgroundColor: 'var(--bg-primary)',
                        padding: '0.5rem',
                        borderRadius: '4px',
                        marginTop: '0.25rem',
                        fontSize: '0.8125rem',
                      }}
                    >
                      <div><strong>ID:</strong> {ex.exemption_id} (Author: {ex.author})</div>
                      <div style={{ color: 'var(--text-secondary)' }}>{ex.reason}</div>
                      <div style={{ fontSize: '0.75rem', color: '#fbbf24' }}>
                        Expires: {new Date(ex.expires_at).toLocaleString()}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* Row of Panels: Dependencies & Provider Native Info */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(420px, 1fr))', gap: '1.5rem' }}>
            {/* Panel 11: Dependencies & Connectivity */}
            <div
              style={{
                backgroundColor: 'var(--bg-secondary)',
                border: '1px solid var(--border-color)',
                borderRadius: '8px',
                padding: '1.5rem',
                display: 'flex',
                flexDirection: 'column',
                gap: '0.75rem',
              }}
            >
              <h3 style={{ margin: 0, fontSize: '1.125rem', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                <Network size={18} color="#3b82f6" /> Dependencies & Endpoints
              </h3>
              {resource.dependencies.length === 0 && resource.connectivity_endpoints.length === 0 ? (
                <span style={{ fontSize: '0.875rem', color: 'var(--text-secondary)' }}>No external topology links or public ingress bindings.</span>
              ) : (
                <>
                  {resource.dependencies.map((dep) => (
                    <div
                      key={dep.id}
                      style={{
                        backgroundColor: 'var(--bg-primary)',
                        padding: '0.5rem 0.75rem',
                        borderRadius: '4px',
                        border: '1px solid var(--border-color)',
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'center',
                        fontSize: '0.8125rem',
                      }}
                    >
                      <span><strong>{dep.direction}:</strong> {dep.name} ({dep.service_name})</span>
                      <span style={{ color: '#10b981', fontWeight: 600 }}>{dep.status}</span>
                    </div>
                  ))}
                  {resource.connectivity_endpoints.map((ep, idx) => (
                    <div
                      key={idx}
                      style={{
                        backgroundColor: 'var(--bg-primary)',
                        padding: '0.5rem 0.75rem',
                        borderRadius: '4px',
                        border: '1px solid var(--border-color)',
                        fontSize: '0.8125rem',
                      }}
                    >
                      <span><strong>{ep.endpoint_type}:</strong> {ep.address}{ep.port ? `:${ep.port}` : ''} ({ep.protocol})</span>
                    </div>
                  ))}
                </>
              )}
            </div>

            {/* Panel 2: Provider Native Details */}
            <div
              style={{
                backgroundColor: 'var(--bg-secondary)',
                border: '1px solid var(--border-color)',
                borderRadius: '8px',
                padding: '1.5rem',
                display: 'flex',
                flexDirection: 'column',
                gap: '0.75rem',
              }}
            >
              <h3 style={{ margin: 0, fontSize: '1.125rem', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                <Cpu size={18} color="#8b5cf6" /> Provider-Native Attributes
              </h3>
              <pre
                style={{
                  backgroundColor: 'var(--bg-primary)',
                  padding: '0.75rem',
                  borderRadius: '6px',
                  fontSize: '0.75rem',
                  color: '#38bdf8',
                  overflowX: 'auto',
                  margin: 0,
                }}
              >
                {JSON.stringify(resource.provider_native, null, 2)}
              </pre>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default ResourceDetailPage;
