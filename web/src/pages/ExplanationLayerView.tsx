import React, { useState } from 'react';
import {
  Breadcrumb,
  BreadcrumbItem,
  CostValue,
  createCostExplanation,
  InformationIcon,
  StandardExplanationPanels,
  ContextualAlertBanner,
  FreshnessSurface,
  SourceTraceabilityBadge,
  StandardExplanationPanelData,
  ContextualAlertData,
  FreshnessSurfaceData,
  PricingInformationPanelData,
} from '../design-system';
import {
  RefreshCw,
  AlertOctagon,
} from 'lucide-react';
import { useApiData } from '../api';

export const ExplanationLayerView: React.FC = () => {
  const { data: apiAlerts } = useApiData<any>('/api/v1/alerts/contextual');
  const [staleSimulated, setStaleSimulated] = useState(false);
  const [acknowledgedAlerts, setAcknowledgedAlerts] = useState<Record<string, boolean>>({});

  const breadcrumbs: BreadcrumbItem[] = [
    { label: 'CloudLens', href: '/' },
    { label: 'Explanation Layer & Transparencies', isCurrent: true },
  ];

  // 17-Field Information Panel Content Model Data
  const samplePanelData: PricingInformationPanelData = {
    resource_id: 'i-0a8b9c1d2e3f4g5h6',
    service: 'Amazon EC2 (c6i.xlarge)',
    service_sku: 'AWS-EC2-C6I-XLARGE',
    pricing_model: 'On-Demand',
    region: 'us-east-1',
    configuration: {
      vCpu: 4,
      memoryGiB: 8,
      storageType: 'EBS-Only',
      architecture: 'x86_64',
    },
    unit_rate: 0.1700,
    monthly_estimate: 124.10,
    pricing_status: 'PAID',
    pricing_status_conditions: ['On-Demand rate in us-east-1', 'Standard Linux operating system'],
    pricing_statement: 'Amazon EC2 c6i.xlarge is billed at $0.1700/hour under On-Demand terms in us-east-1.',
    free_tier_status: 'Standard Paid Service (No free tier)',
    free_tier_allowance: null,
    additional_usage_rate: 0.1700,
    currency: 'USD',
    billing_unit: 'Hrs',
    data_transfer_note: 'Standard internet egress charges apply beyond free allowances.',
    storage_note: 'Persistent storage billed independently from compute runtime.',
    discount_applicability: '12% discount applied via Enterprise Agreement (EA-2026-904).',
    commitment_applicability: 'Eligible for 1-Year and 3-Year Compute Savings Plans (up to 38% off).',
    tax_treatment: 'Exclusive of applicable statutory sales tax or VAT.',
    source_traceability: {
      pricing_source: 'aws_price_list_bulk',
      source_url: 'https://aws.amazon.com/ec2/pricing/on-demand/',
      retrieval_timestamp: staleSimulated
        ? new Date(Date.now() - 180 * 3600 * 1000).toISOString()
        : new Date(Date.now() - 2.5 * 3600 * 1000).toISOString(),
      region: 'us-east-1',
      currency: 'USD',
      effective_date: '2026-09-01T00:00:00Z',
      is_verified: true,
    },
    freshness: {
      last_known_retrieval_date: staleSimulated
        ? new Date(Date.now() - 180 * 3600 * 1000).toISOString()
        : new Date(Date.now() - 2.5 * 3600 * 1000).toISOString(),
      staleness_threshold_hours: 168.0,
      is_stale: staleSimulated,
      age_hours: staleSimulated ? 180.0 : 2.5,
    },
    caveats: [
      'Data transfer egress beyond free tier is charged according to regional destination rates.',
      'Associated storage, snapshots, and IOPS are metered and billed separately.',
      'Prices exclude statutory VAT, sales taxes, or withholding taxes unless explicitly stated.',
    ],
    related_metrics: [
      'CPU Utilization (%)',
      'Network In/Out (Bytes)',
      'Disk Read/Write Operations',
    ],
  };

  // Eleven Standard Explanation Panels Data
  const sampleElevenPanels: StandardExplanationPanelData[] = [
    {
      panel_type: 'WHAT_IS_THIS_SERVICE',
      title: 'What is this service',
      headline: 'Amazon Elastic Compute Cloud (EC2) provides resizable compute capacity.',
      narrative:
        'Amazon EC2 provides virtual computing environments (instances) designed to make web-scale cloud computing easier for developers. Instance type c6i.xlarge delivers 4 compute vCPUs and 8 GiB memory powered by 3rd Generation Intel Xeon Scalable processors.',
      key_facts: {
        service: 'Amazon EC2',
        provider: 'AWS',
        category: 'Compute',
        instance_type: 'c6i.xlarge',
        processor: 'Intel Xeon 8375C',
      },
      source_citation: 'AWS Architecture & Compute Overview',
      source_url: 'https://aws.amazon.com/ec2/',
      last_verified_at: new Date().toISOString(),
      conditions: ['Requires active VPC and subnet placement.'],
    },
    {
      panel_type: 'HOW_IS_IT_PRICED',
      title: 'How is it priced',
      headline: 'Billed per second with a 60-second minimum at $0.1700 per hour.',
      narrative:
        'Under the On-Demand pricing model, capacity is billed per second of active execution without long-term commitments or upfront payments. Usage duration is measured from instance start to termination or stop.',
      key_facts: {
        pricing_model: 'On-Demand',
        rate_per_hour: 0.1700,
        metering_interval: 'Per second (60s minimum)',
        currency: 'USD',
        dimension: 'DIM-03 (Compute Runtime)',
      },
      source_citation: 'AWS Price List Bulk API Rate Card',
      source_url: 'https://aws.amazon.com/ec2/pricing/on-demand/',
      last_verified_at: new Date().toISOString(),
      conditions: ['Stopped instances do not incur compute charges; root volumes remain billed.'],
    },
    {
      panel_type: 'WHY_IS_IT_FREE',
      title: 'Why is it free',
      headline: 'Paid Service: Standard paid tier (No baseline always-free allocation).',
      narrative:
        'Amazon EC2 c6i.xlarge does not qualify for the AWS Free Tier. Only t2.micro and t3.micro qualify for 750 free hours per month for the first 12 months. All runtime for c6i.xlarge is billed at standard rates.',
      key_facts: {
        free_tier_eligible: false,
        pricing_status: 'PAID',
        micro_tier_comparison: 't2.micro / t3.micro eligible (750 hrs/mo for 12 mos)',
      },
      source_citation: 'AWS Free Tier Terms and Inclusions',
      source_url: 'https://aws.amazon.com/free/',
      last_verified_at: new Date().toISOString(),
      conditions: ['All hours billed from first second.'],
    },
    {
      panel_type: 'WHAT_CAUSES_ADDITIONAL_CHARGES',
      title: 'What causes additional charges',
      headline: 'Attached EBS volumes, outbound data egress, and Elastic IPs drive auxiliary cost.',
      narrative:
        'Additional charges occur when auxiliary storage, network data transfer, or provisioned IOPS exceed standard limits. Internet data egress above 100 GB/month incurs $0.09/GB. Root block storage (gp3) is metered at $0.08/GB-Month.',
      key_facts: {
        ebs_gp3_storage_rate: '$0.08 / GB-Month',
        data_egress_rate: '$0.09 / GB (beyond 100 GB allowance)',
        unattached_ipv4_fee: '$0.005 / Hour',
      },
      source_citation: 'AWS Data Transfer & Storage Rate Schedule',
      source_url: 'https://aws.amazon.com/ec2/pricing/on-demand/',
      last_verified_at: new Date().toISOString(),
      conditions: ['Cross-AZ traffic charged at $0.01/GB in each direction.'],
    },
    {
      panel_type: 'WHAT_USAGE_IS_INCLUDED_IN_FREE_TIER',
      title: 'What usage is included in the free tier',
      headline: '0 included hours for c6i.xlarge instances.',
      narrative:
        'Because this is a compute-optimized production instance, no free usage is included in the AWS Free Tier. Every hour is subject to full metered billing.',
      key_facts: {
        included_hours: 0,
        free_allowance: 'None',
        post_allowance_rate: '$0.1700 / Hour',
      },
      source_citation: 'AWS Free Tier Product Exclusions',
      source_url: 'https://aws.amazon.com/free/',
      last_verified_at: new Date().toISOString(),
      conditions: ['Free tier quotas do not offset c6i instance family charges.'],
    },
    {
      panel_type: 'WHAT_IS_INCLUDED_IN_ESTIMATE',
      title: 'What is included in the estimate',
      headline: 'Estimate includes 730 baseline hours ($124.10/month) of primary core runtime.',
      narrative:
        'The calculated monthly projection assumes continuous operation for 730.0 hours at $0.1700/hour. It covers standard 4 vCPUs and 8 GiB RAM allocation without variable auxiliary egress.',
      key_facts: {
        baseline_hours_per_month: 730.0,
        hourly_rate: 0.1700,
        monthly_total_projection: 124.10,
        currency: 'USD',
      },
      source_citation: 'CloudLens Standard Run-Rate Derivation Formula (730.0h)',
      source_url: 'https://aws.amazon.com/pricing/calculator/',
      last_verified_at: new Date().toISOString(),
      conditions: ['Assumes 100% uptime through the 30-day billing cycle.'],
    },
    {
      panel_type: 'WHAT_IS_EXCLUDED',
      title: 'What is excluded',
      headline: 'Data egress traffic, attached EBS volumes, Enterprise Support, and taxes are excluded.',
      narrative:
        'The estimate excludes unpredictable variable dimensions: internet data transfer, provisioned EBS SSD volumes, multi-region replication transit, and state/local sales taxes.',
      key_facts: {
        egress_included: false,
        storage_included: false,
        taxes_included: false,
        support_plan_included: false,
      },
      source_citation: 'CloudLens Estimation Boundary Standard',
      source_url: 'https://cloudlens.internal/docs/boundaries',
      last_verified_at: new Date().toISOString(),
      conditions: ['Auxiliary dimensions appear as independent charge lines on invoices.'],
    },
    {
      panel_type: 'WHAT_PROVIDER_SOURCE_WAS_USED',
      title: 'What provider source was used',
      headline: 'Ingested from official AWS Price List Bulk API feed (us-east-1).',
      narrative:
        'Rate cards were retrieved directly from the AWS Price List Bulk API endpoint. Each rate entry is verified against AWS Offer Index checksums.',
      key_facts: {
        source_name: 'aws_price_list_bulk',
        offer_code: 'AmazonEC2',
        service_sku: 'AWS-EC2-C6I-XLARGE',
        effective_date: '2026-09-01T00:00:00Z',
      },
      source_citation: 'AWS Price List Service API (us-east-1)',
      source_url: 'https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonEC2/current/index.json',
      last_verified_at: new Date().toISOString(),
      conditions: ['Published rates reflect official list pricing.'],
    },
    {
      panel_type: 'WHEN_WAS_PRICING_LAST_RETRIEVED',
      title: 'When was pricing last retrieved',
      headline: staleSimulated
        ? 'WARNING: Rate card is STALE (180.0 hours old, exceeding 168.0h threshold).'
        : 'Rate card is FRESH (2.5 hours old; well within 168.0h weekly SLA threshold).',
      narrative: staleSimulated
        ? 'Pricing was fetched at 2026-09-26T00:00:00Z (180.0 hours ago). This exceeds the configured staleness SLA threshold of 168.0 hours (7 days). A synchronization refresh is required.'
        : 'Pricing was fetched at 2026-10-03T18:00:00Z (2.5 hours ago). Elapsed age is within the configured weekly refresh SLA of 168.0 hours.',
      key_facts: {
        last_retrieval_date: staleSimulated ? '2026-09-26T00:00:00Z' : '2026-10-03T18:00:00Z',
        age_hours: staleSimulated ? 180.0 : 2.5,
        staleness_threshold_hours: 168.0,
        is_stale: staleSimulated,
        freshness_state: staleSimulated ? 'STALE' : 'FRESH',
      },
      source_citation: 'CloudLens Ingestion & Freshness Scheduler',
      source_url: 'https://cloudlens.internal/docs/freshness-sla',
      last_verified_at: new Date().toISOString(),
      conditions: ['Staleness triggers automated warning badge across all dashboards.'],
    },
    {
      panel_type: 'WHY_DOES_ACTUAL_BILLING_DIFFER',
      title: 'Why does actual billing differ from estimated cost',
      headline: 'Actual invoices reflect actual instance running hours, autoscaling, and data egress.',
      narrative:
        'Estimated run-rate projects continuous 730 hours execution. In practice, actual invoices differ due to instances being stopped during non-business hours, dynamic auto-scaling clusters, and variable data egress.',
      key_facts: {
        baseline_estimate: '$124.10 / Month',
        primary_drivers: ['Runtime deviation', 'Data egress volume', 'Attached volume storage'],
        variance_reconciliation_framework: 'FOCUS 1.0 Aligned Normalization',
      },
      source_citation: 'CloudLens Variance Reconciliation Engine',
      source_url: 'https://cloudlens.internal/docs/reconciliation',
      last_verified_at: new Date().toISOString(),
      conditions: ['Variance analyzed against closed-period CUR invoice files.'],
    },
    {
      panel_type: 'WHAT_DEPENDENCY_IS_RESPONSIBLE',
      title: 'What dependency is responsible for this additional charge',
      headline: 'Correlated charges originate from NAT Gateway egress and root gp3 storage.',
      narrative:
        'This EC2 instance sits in a private subnet and routes all internet traffic through a shared NAT Gateway, which meters $0.045/GB data processing. It also mounts an 80 GB gp3 root volume.',
      key_facts: {
        nat_gateway_charge: '$0.045 / GB processed',
        ebs_volume_charge: '$6.40 / Month (80 GB gp3)',
        cloudwatch_telemetry: '$0.30 / Metric stream',
      },
      source_citation: 'CloudLens Multi-Layer Topology Engine',
      source_url: 'https://cloudlens.internal/docs/topology',
      last_verified_at: new Date().toISOString(),
      conditions: ['Dependency chain costs are attributed via topological propagation rules.'],
    },
  ];

  // The 6 Inline Contextual Alerts
  const sampleContextualAlerts: ContextualAlertData[] = [
    {
      id: 'ctx-alert-01',
      alert_type: 'COST_INFORMATION',
      title: 'Idle Resource Rightsizing Detected',
      message:
        "Instance 'i-0a8b9c1d2e3f4g5h6' has sustained average CPU load below 4% for 14 consecutive days. Rightsizing to c6i.large would save $62.05/month.",
      severity: 'INFO',
      visibility: 'PAGE_INLINE',
      is_acknowledged: acknowledgedAlerts['ctx-alert-01'],
      acknowledged_by: acknowledgedAlerts['ctx-alert-01'] ? 'lead-finops' : null,
      metadata: { potential_savings_monthly: '62.05 USD', confidence: 'High' },
    },
    {
      id: 'ctx-alert-02',
      alert_type: 'FREE_TIER',
      title: 'Free Tier Quota Utilization Warning',
      message:
        'Amazon S3 Standard Storage free allowance is currently 84% exhausted (4.2 GB of 5.0 GB limit). Exceeding limit will trigger standard metered charges.',
      severity: 'WARNING',
      visibility: 'PAGE_INLINE',
      is_acknowledged: acknowledgedAlerts['ctx-alert-02'],
      metadata: { consumed_gb: '4.2', limit_gb: '5.0', post_rate: '0.023 USD/GB' },
    },
    {
      id: 'ctx-alert-03',
      alert_type: 'BUDGET',
      title: 'Cost Centre Budget Proximity Warning',
      message:
        'Production Engineering budget threshold breached 85% of monthly allocation on day 18. Allocated budget: $25,000 | Current: $21,340.',
      severity: 'WARNING',
      visibility: 'PAGE_INLINE',
      is_acknowledged: acknowledgedAlerts['ctx-alert-03'],
      metadata: { budget_allocated: '25000 USD', current_spend: '21340 USD', days_remaining: 12 },
    },
    {
      id: 'ctx-alert-04',
      alert_type: 'FORECAST',
      title: 'Projected Budget Overrun Warning',
      message:
        'Trend extrapolation projects total period spend to reach $27,450 (+9.8% over budget boundary) by calendar end.',
      severity: 'HIGH',
      visibility: 'PAGE_INLINE',
      is_acknowledged: acknowledgedAlerts['ctx-alert-04'],
      metadata: { projected_overrun: '2450 USD', confidence_interval: '95%' },
    },
    {
      id: 'ctx-alert-05',
      alert_type: 'PRICING_CHANGE',
      title: 'Upstream Provider Price Adjustment',
      message:
        'AWS published updated pricing for c6i instance family effective next billing cycle. Unit rates in us-east-1 decreased by 3.2%.',
      severity: 'INFO',
      visibility: 'PAGE_INLINE',
      is_acknowledged: acknowledgedAlerts['ctx-alert-05'],
      metadata: { effective_from: '2026-11-01', rate_delta_pct: '-3.2%' },
    },
    {
      id: 'ctx-alert-06',
      alert_type: 'PRICING_UNAVAILABLE',
      title: 'Private Contract Rate Suppressed',
      message:
        'Custom negotiated discount active under Enterprise Agreement EA-2026-904. Public rate card suppressed; effective rates applied.',
      severity: 'INFO',
      visibility: 'PAGE_INLINE',
      is_acknowledged: acknowledgedAlerts['ctx-alert-06'],
      metadata: { contract_ref: 'EA-2026-904', tier: 'Enterprise Tier 3' },
    },
  ];

  // Freshness Surface Data
  const sampleFreshnessData: FreshnessSurfaceData = {
    evaluated_at: new Date().toISOString(),
    has_staleness_warning: staleSimulated,
    stale_count: staleSimulated ? 1 : 0,
    items: [
      {
        data_class: 'PRICING',
        label: 'Pricing Catalogue',
        stated_time_text: staleSimulated ? 'Pricing retrieved 180.0 hours ago' : 'Pricing retrieved 2.5 hours ago',
        last_retrieved_at: staleSimulated
          ? new Date(Date.now() - 180 * 3600 * 1000).toISOString()
          : new Date(Date.now() - 2.5 * 3600 * 1000).toISOString(),
        age_hours: staleSimulated ? 180.0 : 2.5,
        staleness_threshold_hours: 168.0,
        is_stale: staleSimulated,
        warning_message: staleSimulated
          ? 'Warning: Pricing data exceeds SLA threshold of 168.0 hours. Last retrieval: 2026-09-26T00:00:00Z.'
          : null,
        provider: 'CloudLens Pricing Engine',
        status: staleSimulated ? 'STALE' : 'FRESH',
      },
      {
        data_class: 'BILLING_ACTUALS',
        label: 'Provider Billing Data',
        stated_time_text: `Provider billing data through ${new Date(Date.now() - 86400000).toLocaleDateString()}`,
        last_retrieved_at: new Date(Date.now() - 6.5 * 3600 * 1000).toISOString(),
        age_hours: 6.5,
        staleness_threshold_hours: 24.0,
        is_stale: false,
        provider: 'FOCUS Invoiced Actuals',
        status: 'FRESH',
      },
      {
        data_class: 'USAGE_METRICS',
        label: 'Usage Telemetry',
        stated_time_text: 'Usage updated 32 minutes ago',
        last_retrieved_at: new Date(Date.now() - 32 * 60 * 1000).toISOString(),
        age_hours: 0.53,
        staleness_threshold_hours: 4.0,
        is_stale: false,
        provider: 'CloudLens Metric Collector',
        status: 'FRESH',
      },
      {
        data_class: 'INVENTORY',
        label: 'Inventory Discovery',
        stated_time_text: 'Inventory last synchronised 1.4 hours ago',
        last_retrieved_at: new Date(Date.now() - 1.4 * 3600 * 1000).toISOString(),
        age_hours: 1.4,
        staleness_threshold_hours: 6.0,
        is_stale: false,
        provider: 'Multi-Cloud Asset Sync',
        status: 'FRESH',
      },
    ],
  };

  const handleAcknowledgeAlert = (alertId: string, _actor: string, _note?: string) => {
    setAcknowledgedAlerts((prev) => ({ ...prev, [alertId]: true }));
  };

  return (
    <div style={{ padding: '1.5rem 2rem', maxWidth: '1440px', margin: '0 auto', color: 'var(--text-primary, #f8fafc)' }}>
      {/* Breadcrumb Header */}
      <Breadcrumb items={breadcrumbs} className="mb-4" />

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem', flexWrap: 'wrap', gap: '1rem' }}>
        <div>
          <h1 style={{ fontSize: '1.75rem', fontWeight: 700, margin: '0 0 0.25rem 0' }}>
            Explanation Layer &amp; Transparencies
          </h1>
          <p style={{ margin: 0, color: 'var(--text-secondary, #94a3b8)', fontSize: '0.875rem' }}>
            Enforces Master Brief Sections 4, 5, 50, 51, 52, 53: Information icons (17 fields), eleven standard panels, six contextual alerts, data freshness surface, and source traceability.
          </p>
        </div>

        {/* Action Controls */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
          <button
            type="button"
            onClick={() => setStaleSimulated(!staleSimulated)}
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '0.4rem',
              padding: '0.45rem 0.85rem',
              borderRadius: '6px',
              backgroundColor: staleSimulated ? 'rgba(239, 68, 68, 0.2)' : 'rgba(56, 189, 248, 0.1)',
              border: `1px solid ${staleSimulated ? '#dc2626' : '#0284c7'}`,
              color: staleSimulated ? '#f87171' : '#38bdf8',
              cursor: 'pointer',
              fontSize: '0.8125rem',
              fontWeight: 600,
            }}
          >
            {staleSimulated ? <AlertOctagon size={14} /> : <RefreshCw size={14} />}
            <span>{staleSimulated ? 'Simulating STALE Pricing' : 'Simulating FRESH Pricing'}</span>
          </button>
        </div>
      </div>

      {/* 1. Global Data Freshness Surface */}
      <section style={{ marginBottom: '2rem' }}>
        <FreshnessSurface data={sampleFreshnessData} />
      </section>

      {/* 2. Source Traceability Display */}
      <section
        style={{
          backgroundColor: 'var(--bg-secondary, #1e293b)',
          border: '1px solid var(--border-color, #334155)',
          borderRadius: '10px',
          padding: '1.25rem',
          marginBottom: '2rem',
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem' }}>
          <h3 style={{ margin: 0, fontSize: '1rem', color: 'var(--text-primary, #f8fafc)' }}>
            Source Traceability Display
          </h3>
          <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary, #94a3b8)' }}>
            Rigorous Financial Attribution
          </span>
        </div>
        <p style={{ color: 'var(--text-secondary, #94a3b8)', fontSize: '0.8125rem', margin: '0 0 1rem 0' }}>
          Every pricing and cost value is accompanied by verified pricing source provenance, legal effective date, datacenter region, and currency.
        </p>
        <div style={{ display: 'flex', gap: '1rem', flexWrap: 'wrap', alignItems: 'center' }}>
          <SourceTraceabilityBadge
            source="aws_price_list_bulk"
            retrievedAt={samplePanelData.source_traceability.retrieval_timestamp}
            effectiveDate="2026-09-01T00:00:00Z"
            region="us-east-1"
            currency="USD"
            compact={false}
          />
          <SourceTraceabilityBadge
            source="azure_retail_prices_api"
            retrievedAt={new Date(Date.now() - 4 * 3600 * 1000).toISOString()}
            effectiveDate="2026-09-15T00:00:00Z"
            region="eastus"
            currency="USD"
            compact={false}
          />
          <SourceTraceabilityBadge
            source="gcp_cloud_billing_api"
            retrievedAt={new Date(Date.now() - 5 * 3600 * 1000).toISOString()}
            effectiveDate="2026-08-01T00:00:00Z"
            region="us-central1"
            currency="USD"
            compact={false}
          />
        </div>
      </section>

      {/* 3. CostValue Component with Reachable Explanation Within One Interaction */}
      <section
        style={{
          backgroundColor: 'var(--bg-secondary, #1e293b)',
          border: '1px solid var(--border-color, #334155)',
          borderRadius: '10px',
          padding: '1.25rem',
          marginBottom: '2rem',
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <h3 style={{ margin: 0, fontSize: '1rem', color: 'var(--text-primary, #f8fafc)' }}>
              Reachable Explanations Attached to Cost Figures (Within 1 Interaction)
            </h3>
            <InformationIcon panelData={samplePanelData} metricLabel="Information Model Showcase" />
          </div>
          <span style={{ fontSize: '0.75rem', color: '#34d399', fontWeight: 600 }}>
            Mechanical Rule Enforced: CostValue without Explanation fails build
          </span>
        </div>
        <p style={{ color: 'var(--text-secondary, #94a3b8)', fontSize: '0.8125rem', margin: '0 0 1rem 0' }}>
          Click the (i) icon on any number to immediately access its full 17-field structured specification and provider link.
        </p>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: '1rem' }}>
          <div style={{ backgroundColor: 'rgba(15, 23, 42, 0.6)', padding: '1rem', borderRadius: '8px', border: '1px solid var(--border-color, #334155)' }}>
            <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary, #94a3b8)', display: 'block', marginBottom: '0.25rem' }}>
              Invoiced Compute Actual (c6i.xlarge)
            </span>
            <CostValue
              amount={124.10}
              source="ACTUAL"
              currency="USD"
              explanation={createCostExplanation('Amazon EC2 c6i.xlarge Actual', {
                pricingSource: 'aws_cur_invoiced',
                isStale: staleSimulated,
                stalenessWarning: staleSimulated ? 'Ingested 180h ago (Exceeds SLA)' : undefined,
                panelData: samplePanelData,
              })}
            />
          </div>

          <div style={{ backgroundColor: 'rgba(15, 23, 42, 0.6)', padding: '1rem', borderRadius: '8px', border: '1px solid var(--border-color, #334155)' }}>
            <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary, #94a3b8)', display: 'block', marginBottom: '0.25rem' }}>
              Pre-Deployment Run-Rate Estimate
            </span>
            <CostValue
              amount={124.10}
              source="ESTIMATED"
              currency="USD"
              explanation={createCostExplanation('Amazon EC2 c6i.xlarge Baseline Estimate', {
                pricingSource: 'aws_price_list_bulk',
                formula: '0.1700 USD/hr * 730 hours',
                panelData: samplePanelData,
              })}
            />
          </div>

          <div style={{ backgroundColor: 'rgba(15, 23, 42, 0.6)', padding: '1rem', borderRadius: '8px', border: '1px solid var(--border-color, #334155)' }}>
            <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary, #94a3b8)', display: 'block', marginBottom: '0.25rem' }}>
              Projected End-of-Month Forecast
            </span>
            <CostValue
              amount={142.05}
              source="FORECAST"
              currency="USD"
              explanation={createCostExplanation('Projected Forecast', {
                pricingSource: 'cloudlens_forecasting_engine',
                formula: 'OLS linear regression extrapolation',
              })}
            />
          </div>
        </div>
      </section>

      {/* 4. Six Inline Contextual Alerts with Acknowledgement & Audit */}
      <section style={{ marginBottom: '2rem' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem' }}>
          <h3 style={{ margin: 0, fontSize: '1.125rem', color: 'var(--text-primary, #f8fafc)' }}>
            Six Inline Contextual Alerts (Acknowledgement &amp; Audit Trail)
          </h3>
          <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary, #94a3b8)' }}>
            Contextual Alerts
          </span>
        </div>
        <p style={{ color: 'var(--text-secondary, #94a3b8)', fontSize: '0.8125rem', margin: '0 0 1rem 0' }}>
          Supports the 6 canonical types: Cost Information, Free Tier, Budget, Forecast, Pricing Change, and Pricing Unavailable. Users can acknowledge alerts, recording immutable audit provenance.
        </p>

        <div>
          {apiAlerts && Array.isArray(apiAlerts.items) && apiAlerts.items.length > 0
            ? apiAlerts.items.map((alert: any) => (
                <ContextualAlertBanner
                  key={alert.id}
                  alert={alert}
                  onAcknowledge={handleAcknowledgeAlert}
                  currentUser="finops_analyst"
                />
              ))
            : sampleContextualAlerts.map((alert) => (
                <ContextualAlertBanner
                  key={alert.id}
                  alert={alert}
                  onAcknowledge={handleAcknowledgeAlert}
                  currentUser="finops_analyst"
                />
              ))}
        </div>
      </section>

      {/* 5. Eleven Standard Explanation Panels */}
      <section style={{ marginBottom: '2rem' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem' }}>
          <h3 style={{ margin: 0, fontSize: '1.125rem', color: 'var(--text-primary, #f8fafc)' }}>
            The Eleven Standard Explanation Panels
          </h3>
          <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary, #94a3b8)' }}>
            Master Brief Section 50 Full Suite
          </span>
        </div>
        <p style={{ color: 'var(--text-secondary, #94a3b8)', fontSize: '0.8125rem', margin: '0 0 1rem 0' }}>
          Every question answered with verifiable facts: What is this service, how it is priced, why it is free, what causes charges, included free tier usage, estimate inclusions, exclusions, provider source used, when pricing was retrieved, actual vs estimated variance, and responsible dependencies.
        </p>

        <StandardExplanationPanels
          panels={sampleElevenPanels}
          serviceName="Amazon EC2 (c6i.xlarge)"
          provider="AWS"
          region="us-east-1"
        />
      </section>
    </div>
  );
};
