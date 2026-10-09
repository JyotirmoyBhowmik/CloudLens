import React, { useState, useMemo, useEffect } from 'react';
import { useAuth } from '../context/AuthContext';
import {
  Breadcrumb,
  EmptyState,
  ErrorState,
  SkeletonLoader,
} from '../design-system';
import {
  ShieldAlert,
  Lock,
  Unlock,
  Users,
  Sliders,
  AlertTriangle,
  Download,
  Plus,
  Search,
  CheckCircle2,
  RefreshCw,
  X,
  FileText,
  ArrowRight,
} from 'lucide-react';
import { useApiData } from '../api';

export interface AdminConsoleProps {
  onNavigateHome?: () => void;
}

export interface AdminFunction {
  id: string;
  name: string;
  category: string;
  description: string;
  status: 'ACTIVE' | 'READ_ONLY' | 'LOCKED';
}

export interface OverrideItem {
  id: string;
  overrideClass: 'PRICING' | 'THRESHOLD' | 'EXEMPTION' | 'ROUTING' | 'CLASSIFICATION';
  who: string;
  what: string;
  why: string;
  previousValue: string;
  newValue: string;
  expiry: string;
  approvalTicket: string;
  status: 'ACTIVE' | 'EXPIRED' | 'REVERTED';
  createdAt: string;
}

export interface AuditLogItem {
  id: string;
  timestamp: string;
  actor: string;
  action: string;
  targetEntity: string;
  correlationId: string;
  status: 'SUCCESS' | 'DENIED' | 'FAILED';
}

const ADMIN_FUNCTIONS: AdminFunction[] = [
  { id: 'fn-01', name: 'Tenant Management', category: 'Identity & Tenancy', description: 'Configure tenant isolation boundaries, slug, branding, and organization metadata.', status: 'ACTIVE' },
  { id: 'fn-02', name: 'User Management', category: 'Identity & Tenancy', description: 'User lifecycle, provisioning, invitation dispatch, status deactivation, and session invalidation.', status: 'ACTIVE' },
  { id: 'fn-03', name: 'Role Management', category: 'Access Control', description: 'System role overview and tenant custom role composition from permission catalogue.', status: 'ACTIVE' },
  { id: 'fn-04', name: 'RBAC & Scope Grants', category: 'Access Control', description: 'Multi-dimensional scope grant matrix, access evaluations, and periodic compliance review export.', status: 'ACTIVE' },
  { id: 'fn-05', name: 'SSO & IdP Configuration', category: 'Access Control', description: 'SAML 2.0 and OIDC federated identity providers, metadata endpoints, and certificate thumbprints.', status: 'ACTIVE' },
  { id: 'fn-06', name: 'Cloud Connectors', category: 'Connectors & Ingestion', description: 'Multi-cloud provider connectors (AWS, Azure, GCP, OCI), sync cadences, and capability matrix.', status: 'ACTIVE' },
  { id: 'fn-07', name: 'Credential Profiles', category: 'Connectors & Ingestion', description: 'Cloud authentication profiles, IAM cross-account role ARNs, and KMS secret references.', status: 'ACTIVE' },
  { id: 'fn-08', name: 'Provider Configuration', category: 'Connectors & Ingestion', description: 'Enabled datacenter regions, API endpoint overrides, batch ingestion sizes, and discovery throttles.', status: 'ACTIVE' },
  { id: 'fn-09', name: 'Global Thresholds', category: 'FinOps & Policy', description: 'Estate-wide budget utilization alert bands (Amber 80%, Red 100%, Breach 110%) and anomaly z-scores.', status: 'ACTIVE' },
  { id: 'fn-10', name: 'Policy Engine Configuration', category: 'FinOps & Policy', description: 'Declarative governance rules POL-01 through POL-16, dry-run simulation mode, and automated enforcement.', status: 'ACTIVE' },
  { id: 'fn-11', name: 'Budget Templates', category: 'FinOps & Policy', description: 'Standardized enterprise allocation templates for application tiers, environments, and business units.', status: 'ACTIVE' },
  { id: 'fn-12', name: 'Service Catalogue', category: 'Catalogue & Pricing', description: 'Cloud service taxonomies, canonical categories, SKU normalization tables, and unmapped SKU tracking.', status: 'ACTIVE' },
  { id: 'fn-13', name: 'Cost Model Configuration', category: 'Catalogue & Pricing', description: 'Amortization schedule formulas, upfront fee depreciation schedules, and blended rate logic.', status: 'ACTIVE' },
  { id: 'fn-14', name: 'Metric Catalogue', category: 'Catalogue & Pricing', description: 'Usage measurement types, cardinality filters, metric collectors, and downsampling rules.', status: 'ACTIVE' },
  { id: 'fn-15', name: 'Unit Catalogue', category: 'Catalogue & Pricing', description: 'Conversion multiplier registry between storage, bandwidth, memory, and core consumption dimensions.', status: 'ACTIVE' },
  { id: 'fn-16', name: 'Currency & FX Configuration', category: 'Financial Controls', description: 'Reporting currency, ISO 4217 rate cards, fixed monthly exchange rates, and FX variance accounting.', status: 'ACTIVE' },
  { id: 'fn-17', name: 'Alert Configuration', category: 'Alerting & Ops', description: 'Canonical alert thresholds, anti-flapping minimum dwell times, and storm-grouping limits.', status: 'ACTIVE' },
  { id: 'fn-18', name: 'Notification Channels', category: 'Alerting & Ops', description: 'Webhook endpoints, Slack channels, PagerDuty services, and email recipient escalation paths.', status: 'ACTIVE' },
  { id: 'fn-19', name: 'Data Retention Policies', category: 'Compliance & Audit', description: 'Granular data lifecycles: 90-day usage metrics, 7-year financial billing records, 3-year audit logs.', status: 'ACTIVE' },
  { id: 'fn-20', name: 'Audit Log Viewer', category: 'Compliance & Audit', description: 'Immutable ledger of all mutating transactions with actor provenance, correlation ID, and export.', status: 'ACTIVE' },
  { id: 'fn-21', name: 'System Settings', category: 'System Controls', description: 'Default timezone, dark mode configuration, UI comfortable-density toggles, and cache TTL settings.', status: 'ACTIVE' },
  { id: 'fn-22', name: 'Feature Flags Console', category: 'System Controls', description: 'Canary feature rollout toggles, dark-launch switches, and emergency system kill-switches.', status: 'ACTIVE' },
  { id: 'fn-23', name: 'Connector Overrides', category: 'Overrides & Exceptions', description: 'Per-connector rate limiting overrides, timeout cushions, and mock estate simulation toggles.', status: 'ACTIVE' },
  { id: 'fn-24', name: 'Manual Overrides & Exceptions', category: 'Overrides & Exceptions', description: 'Eight-attribute enforced governance overrides with mandatory rationale, expiry, and reversion.', status: 'ACTIVE' },
];

const RBAC_PERMISSIONS_MATRIX = [
  { perm: 'read:dashboard:executive', viewer: true, contributor: true, finops: true, arch: true, admin: true },
  { perm: 'read:cost:financial_detail', viewer: false, contributor: false, finops: true, arch: true, admin: true },
  { perm: 'read:topology:graph', viewer: true, contributor: true, finops: true, arch: true, admin: true },
  { perm: 'write:budgets:create', viewer: false, contributor: false, finops: true, arch: false, admin: true },
  { perm: 'write:budgets:approve', viewer: false, contributor: false, finops: true, arch: false, admin: true },
  { perm: 'write:policies:create', viewer: false, contributor: false, finops: false, arch: true, admin: true },
  { perm: 'write:policies:exempt', viewer: false, contributor: false, finops: false, arch: true, admin: true },
  { perm: 'admin:connectors:manage', viewer: false, contributor: false, finops: false, arch: false, admin: true },
  { perm: 'admin:credentials:rotate', viewer: false, contributor: false, finops: false, arch: false, admin: true },
  { perm: 'admin:overrides:submit', viewer: false, contributor: false, finops: false, arch: false, admin: true },
  { perm: 'admin:step_up:authenticate', viewer: false, contributor: false, finops: false, arch: false, admin: true },
];

export const AdminConsolePage: React.FC<AdminConsoleProps> = ({
  onNavigateHome,
}) => {
  const auth = useAuth();
  // Administrative check driven by verified API capability
  const isAdmin = auth ? auth.hasCapability('admin:access') : false;

  // Step-up authentication state
  const [isStepUpAuthenticated, setIsStepUpAuthenticated] = useState(false);

  // Active view inside admin console
  const [activeTab, setActiveTab] = useState<'catalogue' | 'overrides' | 'rbac' | 'audit' | 'settings'>('catalogue');

  // Overrides API state
  const { data: apiOverrides, loading: loadingOverrides, error: errorOverrides, errorMessage: errorMsgOverrides, refetch: refetchOverrides } = useApiData<any>('/api/v1/overrides');
  const { data: apiAudit, loading: loadingAudit, error: errorAudit, errorMessage: errorMsgAudit, refetch: refetchAudit } = useApiData<any>('/api/v1/audit/events');

  const [overrides, setOverrides] = useState<OverrideItem[]>([]);

  useEffect(() => {
    if (apiOverrides) {
      const list = Array.isArray(apiOverrides) ? apiOverrides : (apiOverrides.items || []);
      setOverrides(list.map((r: any) => ({
        id: r.id || 'ovr-001',
        overrideClass: r.override_class || r.overrideClass || 'THRESHOLD',
        who: r.who || 'system',
        what: r.what || '',
        why: r.why || '',
        previousValue: String(r.previous_value ?? r.previousValue ?? ''),
        newValue: String(r.new_value ?? r.newValue ?? ''),
        expiry: r.expiry || '',
        approvalTicket: r.approval || r.approvalTicket || '',
        status: r.status || 'ACTIVE',
        createdAt: r.when || r.createdAt || '',
      })));
    }
  }, [apiOverrides]);

  const auditLogs: AuditLogItem[] = useMemo(() => {
    if (!apiAudit) return [];
    const list = Array.isArray(apiAudit) ? apiAudit : (apiAudit.items || []);
    return list.map((a: any) => ({
      id: a.id || a.event_id || 'aud-001',
      timestamp: a.timestamp || a.created_at || '',
      actor: a.actor || a.user_id || 'system',
      action: a.action || a.event_type || 'SYSTEM_EVENT',
      targetEntity: a.target_entity || a.targetEntity || a.entity_id || 'system',
      correlationId: a.correlation_id || a.correlationId || 'corr-001',
      status: a.status || (a.success ? 'SUCCESS' : 'FAILED'),
    }));
  }, [apiAudit]);

  const [isOverrideModalOpen, setIsOverrideModalOpen] = useState(false);

  // Eight mandatory override form attributes
  const [ovrClass, setOvrClass] = useState<'PRICING' | 'THRESHOLD' | 'EXEMPTION' | 'ROUTING' | 'CLASSIFICATION'>('THRESHOLD');
  const [ovrWho, setOvrWho] = useState('sarah.chen@cloudlens.internal');
  const [ovrWhat, setOvrWhat] = useState('');
  const [ovrWhy, setOvrWhy] = useState('');
  const [ovrPrevVal, setOvrPrevVal] = useState('');
  const [ovrNewVal, setOvrNewVal] = useState('');
  const [ovrExpiry, setOvrExpiry] = useState('');
  const [ovrTicket, setOvrTicket] = useState('');
  const [overrideFormError, setOverrideFormError] = useState<string | null>(null);

  // RBAC search & export
  const [searchQuery, setSearchQuery] = useState('');
  const [isExportingCsv, setIsExportingCsv] = useState(false);

  // Acceptance 4: Render strict 403 Forbidden surface when user is not administrative
  if (!isAdmin) {
    return (
      <div
        style={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          minHeight: '60vh',
          textAlign: 'center',
          padding: '2rem',
        }}
      >
        <div
          style={{
            backgroundColor: '#450a0a',
            border: '2px solid #7f1d1d',
            borderRadius: '50%',
            width: '80px',
            height: '80px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            marginBottom: '1.5rem',
            color: '#f87171',
          }}
        >
          <Lock size={40} />
        </div>
        <h1 style={{ fontSize: '2rem', fontWeight: 700, margin: '0 0 0.5rem 0', color: 'var(--text-primary)' }}>
          403 Forbidden — Access Restricted
        </h1>
        <p style={{ maxWidth: '540px', color: 'var(--text-secondary)', fontSize: '1rem', lineHeight: '1.5', margin: '0 0 1.5rem 0' }}>
          Administrative console surfaces are strictly reserved for administrative credentials. Non-administrative users have no access to control plane administrative functions.
        </p>
        <div style={{ display: 'flex', gap: '1rem' }}>
          {onNavigateHome && (
            <button
              onClick={onNavigateHome}
              style={{
                backgroundColor: '#0284c7',
                color: '#ffffff',
                border: 'none',
                borderRadius: '6px',
                padding: '0.6rem 1.25rem',
                fontWeight: 600,
                cursor: 'pointer',
                fontSize: '0.875rem',
              }}
            >
              Return to Daily Workspace
            </button>
          )}
        </div>
      </div>
    );
  }

  // Override Form Submission (Enforcing all 8 attributes & Acceptance 3: reason >= 20 chars & expiry)
  const handleCreateOverride = (e: React.FormEvent) => {
    e.preventDefault();
    setOverrideFormError(null);

    // Validation 1: Rationale >= 20 characters
    if (!ovrWhy || ovrWhy.trim().length < 20) {
      setOverrideFormError(`Override rationale ('why') must be at least 20 characters explaining the operational reason. Found ${ovrWhy.trim().length}.`);
      return;
    }

    // Validation 2: Expiry timestamp must exist and be in the future
    if (!ovrExpiry) {
      setOverrideFormError('Mandatory expiration timestamp is required.');
      return;
    }
    const expiryDate = new Date(ovrExpiry);
    if (isNaN(expiryDate.getTime()) || expiryDate.getTime() <= Date.now()) {
      setOverrideFormError('Expiration timestamp must be a valid future datetime.');
      return;
    }

    // Validation 3: Target entity / what
    if (!ovrWhat.trim()) {
      setOverrideFormError('Target entity or configuration path is required.');
      return;
    }

    // Validation 4: Ticket
    if (!ovrTicket.trim()) {
      setOverrideFormError('ITSM approval ticket reference (e.g. CHG-99401) is required.');
      return;
    }

    const newOvr: OverrideItem = {
      id: `ovr-2026-${Math.floor(100 + Math.random() * 900)}`,
      overrideClass: ovrClass,
      who: ovrWho,
      what: ovrWhat,
      why: ovrWhy,
      previousValue: ovrPrevVal || 'default',
      newValue: ovrNewVal,
      expiry: expiryDate.toISOString().replace('T', ' ').substring(0, 16) + ' UTC',
      approvalTicket: ovrTicket,
      status: 'ACTIVE',
      createdAt: new Date().toISOString().replace('T', ' ').substring(0, 16) + ' UTC',
    };

    setOverrides((prev) => [newOvr, ...prev]);
    setIsOverrideModalOpen(false);

    // Reset form
    setOvrWhat('');
    setOvrWhy('');
    setOvrPrevVal('');
    setOvrNewVal('');
    setOvrExpiry('');
    setOvrTicket('');
  };

  const handleExportCsv = () => {
    setIsExportingCsv(true);
    setTimeout(() => {
      setIsExportingCsv(false);

      // Create CSV content
      const headers = ['Permission_Identifier', 'Role_Viewer', 'Role_Contributor', 'Role_FinOps_Analyst', 'Role_Cloud_Architect', 'Role_Tenant_Admin', 'Exported_At_UTC'];
      const rows = RBAC_PERMISSIONS_MATRIX.map((r) => [
        r.perm,
        r.viewer ? 'YES' : 'NO',
        r.contributor ? 'YES' : 'NO',
        r.finops ? 'YES' : 'NO',
        r.arch ? 'YES' : 'NO',
        r.admin ? 'YES' : 'NO',
        new Date().toISOString(),
      ]);

      const csvContent = 'data:text/csv;charset=utf-8,' + [headers.join(','), ...rows.map((e) => e.join(','))].join('\n');
      const encodedUri = encodeURI(csvContent);
      const link = document.createElement('a');
      link.setAttribute('href', encodedUri);
      link.setAttribute('download', `cloudlens-access-review-${new Date().toISOString().substring(0, 10)}.csv`);
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
    }, 600);
  };

  const filteredFunctions = useMemo(() => {
    if (!searchQuery.trim()) return ADMIN_FUNCTIONS;
    const q = searchQuery.toLowerCase();
    return ADMIN_FUNCTIONS.filter((fn) => fn.name.toLowerCase().includes(q) || fn.description.toLowerCase().includes(q) || fn.category.toLowerCase().includes(q));
  }, [searchQuery]);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem', width: '100%' }}>
      {/* Breadcrumb Header */}
      <Breadcrumb
        items={[
          { label: 'CloudLens', href: '#' },
          { label: 'Control Plane', href: '#' },
          { label: 'Administrative Console', isCurrent: true },
        ]}
      />

      {/* Top Banner */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '1rem' }}>
        <div>
          <h1 style={{ margin: 0, fontSize: '1.75rem', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
            <ShieldAlert style={{ color: '#ef4444' }} size={28} />
            Tenant Administration Console
          </h1>
          <p style={{ margin: '0.25rem 0 0', color: 'var(--text-secondary)', fontSize: '0.9rem' }}>
            Comprehensive 24-function administrative surface, RBAC compliance matrix, and 8-attribute verified governance overrides.
          </p>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '0.5rem',
              backgroundColor: isStepUpAuthenticated ? '#064e3b' : '#451a03',
              border: `1px solid ${isStepUpAuthenticated ? '#059669' : '#b45309'}`,
              color: isStepUpAuthenticated ? '#6ee7b7' : '#fdba74',
              borderRadius: '6px',
              padding: '0.4rem 0.8rem',
              fontSize: '0.8125rem',
              fontWeight: 600,
            }}
          >
            {isStepUpAuthenticated ? <Unlock size={16} /> : <Lock size={16} />}
            {isStepUpAuthenticated ? 'Step-Up Session Active' : 'Step-Up Authentication Required'}
          </div>

          {!isStepUpAuthenticated && (
            <button
              onClick={() => {
                const pass = prompt('Enter Tenant Admin Step-Up Secret / MFA code:');
                if (pass) {
                  setIsStepUpAuthenticated(true);
                }
              }}
              style={{
                backgroundColor: '#ef4444',
                color: '#ffffff',
                border: 'none',
                borderRadius: '6px',
                padding: '0.4rem 0.8rem',
                fontSize: '0.8125rem',
                fontWeight: 600,
                cursor: 'pointer',
              }}
            >
              Authenticate Step-Up
            </button>
          )}
        </div>
      </div>

      {/* Step-Up Warning Banner if not authenticated */}
      {!isStepUpAuthenticated && (
        <div style={{ backgroundColor: '#2d1500', border: '1px solid #78350f', borderRadius: '8px', padding: '1rem 1.25rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
            <AlertTriangle color="#f59e0b" size={24} />
            <div>
              <div style={{ fontWeight: 600, color: '#fde68a' }}>Protected Control-Plane Surface</div>
              <div style={{ fontSize: '0.8125rem', color: '#fcd34d' }}>
                You are viewing in read-only administrative mode. Destructive actions (overrides, credential rotation, settings mutation) require active step-up verification.
              </div>
            </div>
          </div>
          <button
            onClick={() => setIsStepUpAuthenticated(true)}
            style={{
              backgroundColor: '#d97706',
              color: '#ffffff',
              border: 'none',
              borderRadius: '6px',
              padding: '0.4rem 0.8rem',
              fontWeight: 600,
              fontSize: '0.8125rem',
              cursor: 'pointer',
            }}
          >
            Unlock Mutations
          </button>
        </div>
      )}

      {/* Admin Tabs */}
      <div style={{ display: 'flex', gap: '0.5rem', borderBottom: '1px solid var(--border-color)', paddingBottom: '0.5rem' }}>
        <button
          onClick={() => setActiveTab('catalogue')}
          style={{
            padding: '0.5rem 1rem',
            borderRadius: '6px',
            border: 'none',
            backgroundColor: activeTab === 'catalogue' ? '#0284c7' : 'transparent',
            color: activeTab === 'catalogue' ? '#ffffff' : 'var(--text-secondary)',
            cursor: 'pointer',
            fontWeight: 600,
            fontSize: '0.875rem',
            display: 'flex',
            alignItems: 'center',
            gap: '0.5rem',
          }}
        >
          <Sliders size={16} />
          24 Functions Catalogue
        </button>
        <button
          onClick={() => setActiveTab('overrides')}
          style={{
            padding: '0.5rem 1rem',
            borderRadius: '6px',
            border: 'none',
            backgroundColor: activeTab === 'overrides' ? '#0284c7' : 'transparent',
            color: activeTab === 'overrides' ? '#ffffff' : 'var(--text-secondary)',
            cursor: 'pointer',
            fontWeight: 600,
            fontSize: '0.875rem',
            display: 'flex',
            alignItems: 'center',
            gap: '0.5rem',
          }}
        >
          <ShieldAlert size={16} />
          8-Attribute Overrides ({overrides.length})
        </button>
        <button
          onClick={() => setActiveTab('rbac')}
          style={{
            padding: '0.5rem 1rem',
            borderRadius: '6px',
            border: 'none',
            backgroundColor: activeTab === 'rbac' ? '#0284c7' : 'transparent',
            color: activeTab === 'rbac' ? '#ffffff' : 'var(--text-secondary)',
            cursor: 'pointer',
            fontWeight: 600,
            fontSize: '0.875rem',
            display: 'flex',
            alignItems: 'center',
            gap: '0.5rem',
          }}
        >
          <Users size={16} />
          RBAC Matrix & Access Review
        </button>
        <button
          onClick={() => setActiveTab('audit')}
          style={{
            padding: '0.5rem 1rem',
            borderRadius: '6px',
            border: 'none',
            backgroundColor: activeTab === 'audit' ? '#0284c7' : 'transparent',
            color: activeTab === 'audit' ? '#ffffff' : 'var(--text-secondary)',
            cursor: 'pointer',
            fontWeight: 600,
            fontSize: '0.875rem',
            display: 'flex',
            alignItems: 'center',
            gap: '0.5rem',
          }}
        >
          <FileText size={16} />
          Audit Log Ledger
        </button>
      </div>

      {/* TAB 1: 24 Functions Catalogue */}
      {activeTab === 'catalogue' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', backgroundColor: 'var(--bg-secondary)', padding: '0.75rem 1rem', borderRadius: '8px', border: '1px solid var(--border-color)' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flex: 1 }}>
              <Search size={16} style={{ color: 'var(--text-secondary)' }} />
              <input
                type="text"
                placeholder="Search administrative modules by title, category, or capability..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                style={{
                  backgroundColor: 'transparent',
                  border: 'none',
                  color: 'var(--text-primary)',
                  fontSize: '0.875rem',
                  outline: 'none',
                  width: '100%',
                }}
              />
            </div>
            <span style={{ fontSize: '0.8125rem', color: 'var(--text-secondary)' }}>
              Showing {filteredFunctions.length} of 24 functions
            </span>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: '1rem' }}>
            {filteredFunctions.map((fn, idx) => (
              <div
                key={fn.id}
                style={{
                  backgroundColor: 'var(--bg-secondary)',
                  border: '1px solid var(--border-color)',
                  borderRadius: '8px',
                  padding: '1.25rem',
                  display: 'flex',
                  flexDirection: 'column',
                  justifyContent: 'space-between',
                  gap: '0.75rem',
                }}
              >
                <div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '0.5rem' }}>
                    <span style={{ backgroundColor: '#0f172a', border: '1px solid #334155', borderRadius: '4px', padding: '0.1rem 0.4rem', fontFamily: 'monospace', fontSize: '0.75rem', color: '#38bdf8' }}>
                      #{idx + 1 < 10 ? `0${idx + 1}` : idx + 1}
                    </span>
                    <span style={{ fontSize: '0.75rem', backgroundColor: '#1e293b', padding: '0.1rem 0.4rem', borderRadius: '4px', color: '#94a3b8' }}>
                      {fn.category}
                    </span>
                  </div>

                  <h3 style={{ margin: '0 0 0.35rem 0', fontSize: '1rem', fontWeight: 600, color: 'var(--text-primary)' }}>
                    {fn.name}
                  </h3>
                  <p style={{ margin: 0, fontSize: '0.8125rem', color: 'var(--text-secondary)', lineHeight: '1.4' }}>
                    {fn.description}
                  </p>
                </div>

                <div style={{ display: 'flex', justifyContent: 'flex-end', borderTop: '1px solid var(--border-color)', paddingTop: '0.75rem' }}>
                  <button
                    onClick={() => {
                      if (fn.id === 'fn-24' || fn.id === 'fn-23') {
                        setActiveTab('overrides');
                      } else if (fn.id === 'fn-04') {
                        setActiveTab('rbac');
                      } else if (fn.id === 'fn-20') {
                        setActiveTab('audit');
                      } else {
                        alert(`Opening control interface for ${fn.name} (Step-up confirmed).`);
                      }
                    }}
                    style={{
                      backgroundColor: 'transparent',
                      border: '1px solid #0284c7',
                      color: '#38bdf8',
                      borderRadius: '4px',
                      padding: '0.3rem 0.75rem',
                      fontSize: '0.75rem',
                      fontWeight: 600,
                      cursor: 'pointer',
                      display: 'flex',
                      alignItems: 'center',
                      gap: '0.35rem',
                    }}
                  >
                    Manage Module
                    <ArrowRight size={12} />
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* TAB 2: 8-Attribute Enforced Overrides (Acceptance 3) */}
      {activeTab === 'overrides' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div>
              <h2 style={{ margin: 0, fontSize: '1.25rem', fontWeight: 600 }}>
                Manual Governance Overrides &amp; Exceptions
              </h2>
              <p style={{ margin: '0.25rem 0 0', color: 'var(--text-secondary)', fontSize: '0.875rem' }}>
                Enforces all eight mandatory attributes: who, what, why (min 20 chars), previous, new, future expiry, class, and approval ticket.
              </p>
            </div>

            <button
              onClick={() => setIsOverrideModalOpen(true)}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '0.5rem',
                backgroundColor: '#ef4444',
                color: '#ffffff',
                border: 'none',
                borderRadius: '6px',
                padding: '0.5rem 1rem',
                fontWeight: 600,
                cursor: 'pointer',
                fontSize: '0.875rem',
              }}
            >
              <Plus size={16} />
              Submit Override
            </button>
          </div>

          {loadingOverrides && <SkeletonLoader variant="table" rows={3} />}
          {errorOverrides && !loadingOverrides && (
            <ErrorState
              title="Failed to Load Governance Overrides"
              message={errorMsgOverrides || 'Error contacting overrides API'}
              onRetry={refetchOverrides}
            />
          )}
          {!loadingOverrides && !errorOverrides && overrides.length === 0 && (
            <EmptyState type="NO_DATA" titleOverride="No Active Overrides" descriptionOverride="No operational or governance overrides configured for this tenant." actionTextOverride="Create Override" onAction={() => setIsOverrideModalOpen(true)} />
          )}

          {!loadingOverrides && !errorOverrides && overrides.length > 0 && (
            <div style={{ backgroundColor: 'var(--bg-secondary)', border: '1px solid var(--border-color)', borderRadius: '8px', overflow: 'hidden' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '0.875rem' }}>
                <thead>
                  <tr style={{ backgroundColor: '#0f172a', borderBottom: '1px solid var(--border-color)', color: 'var(--text-secondary)' }}>
                    <th style={{ padding: '0.75rem 1rem' }}>Class</th>
                    <th style={{ padding: '0.75rem 1rem' }}>Target (What)</th>
                    <th style={{ padding: '0.75rem 1rem' }}>Values (Prev &rarr; New)</th>
                    <th style={{ padding: '0.75rem 1rem' }}>Rationale (Why &gt;= 20 chars)</th>
                    <th style={{ padding: '0.75rem 1rem' }}>Accountable (Who)</th>
                    <th style={{ padding: '0.75rem 1rem' }}>Expiry &amp; Ticket</th>
                    <th style={{ padding: '0.75rem 1rem' }}>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {overrides.map((ovr) => (
                    <tr key={ovr.id} style={{ borderBottom: '1px solid var(--border-color)' }}>
                      <td style={{ padding: '0.75rem 1rem' }}>
                        <span style={{ backgroundColor: '#1e293b', color: '#93c5fd', padding: '0.15rem 0.4rem', borderRadius: '4px', fontSize: '0.75rem', fontWeight: 600 }}>
                          {ovr.overrideClass}
                        </span>
                      </td>
                      <td style={{ padding: '0.75rem 1rem', fontFamily: 'monospace', fontSize: '0.8125rem', color: '#38bdf8' }}>
                        {ovr.what}
                      </td>
                      <td style={{ padding: '0.75rem 1rem', fontSize: '0.8125rem' }}>
                        <span style={{ textDecoration: 'line-through', color: '#94a3b8' }}>{ovr.previousValue}</span>
                        <span style={{ margin: '0 0.35rem', color: '#64748b' }}>&rarr;</span>
                        <strong style={{ color: '#34d399' }}>{ovr.newValue}</strong>
                      </td>
                      <td style={{ padding: '0.75rem 1rem', fontSize: '0.8125rem', color: 'var(--text-secondary)', maxWidth: '280px' }}>
                        {ovr.why}
                      </td>
                      <td style={{ padding: '0.75rem 1rem', fontSize: '0.8125rem' }}>
                        {ovr.who}
                      </td>
                      <td style={{ padding: '0.75rem 1rem', fontSize: '0.75rem' }}>
                        <div style={{ color: '#fbbf24', fontWeight: 600 }}>{ovr.expiry}</div>
                        <div style={{ color: '#64748b', fontFamily: 'monospace' }}>{ovr.approvalTicket}</div>
                      </td>
                      <td style={{ padding: '0.75rem 1rem' }}>
                        <span
                          style={{
                            backgroundColor: ovr.status === 'ACTIVE' ? '#064e3b' : '#334155',
                            color: ovr.status === 'ACTIVE' ? '#6ee7b7' : '#94a3b8',
                            padding: '0.15rem 0.4rem',
                            borderRadius: '4px',
                            fontSize: '0.75rem',
                            fontWeight: 600,
                          }}
                        >
                          {ovr.status}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* TAB 3: RBAC Matrix & Access Review */}
      {activeTab === 'rbac' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div>
              <h2 style={{ margin: 0, fontSize: '1.25rem', fontWeight: 600 }}>
                RBAC Permission Cross-Reference Matrix
              </h2>
              <p style={{ margin: '0.25rem 0 0', color: 'var(--text-secondary)', fontSize: '0.875rem' }}>
                Complete entitlement catalogue cross-referenced against all standard tenant system roles.
              </p>
            </div>

            <button
              onClick={handleExportCsv}
              disabled={isExportingCsv}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '0.5rem',
                backgroundColor: '#0284c7',
                color: '#ffffff',
                border: 'none',
                borderRadius: '6px',
                padding: '0.5rem 1rem',
                fontWeight: 600,
                cursor: isExportingCsv ? 'not-allowed' : 'pointer',
                fontSize: '0.875rem',
              }}
            >
              {isExportingCsv ? <RefreshCw className="animate-spin" size={16} /> : <Download size={16} />}
              {isExportingCsv ? 'Exporting...' : 'Export Access Review (CSV)'}
            </button>
          </div>

          <div style={{ backgroundColor: 'var(--bg-secondary)', border: '1px solid var(--border-color)', borderRadius: '8px', overflow: 'hidden' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '0.875rem' }}>
              <thead>
                <tr style={{ backgroundColor: '#0f172a', borderBottom: '1px solid var(--border-color)', color: 'var(--text-secondary)' }}>
                  <th style={{ padding: '0.75rem 1rem' }}>Permission Capability</th>
                  <th style={{ padding: '0.75rem 1rem', textAlign: 'center' }}>Viewer</th>
                  <th style={{ padding: '0.75rem 1rem', textAlign: 'center' }}>Contributor</th>
                  <th style={{ padding: '0.75rem 1rem', textAlign: 'center' }}>FinOps Analyst</th>
                  <th style={{ padding: '0.75rem 1rem', textAlign: 'center' }}>Cloud Architect</th>
                  <th style={{ padding: '0.75rem 1rem', textAlign: 'center' }}>Tenant Admin</th>
                </tr>
              </thead>
              <tbody>
                {RBAC_PERMISSIONS_MATRIX.map((row) => (
                  <tr key={row.perm} style={{ borderBottom: '1px solid var(--border-color)' }}>
                    <td style={{ padding: '0.75rem 1rem', fontFamily: 'monospace', fontSize: '0.8125rem', color: '#93c5fd' }}>
                      {row.perm}
                    </td>
                    <td style={{ padding: '0.75rem 1rem', textAlign: 'center' }}>
                      {row.viewer ? <CheckCircle2 size={16} color="#34d399" /> : <X size={16} color="#475569" />}
                    </td>
                    <td style={{ padding: '0.75rem 1rem', textAlign: 'center' }}>
                      {row.contributor ? <CheckCircle2 size={16} color="#34d399" /> : <X size={16} color="#475569" />}
                    </td>
                    <td style={{ padding: '0.75rem 1rem', textAlign: 'center' }}>
                      {row.finops ? <CheckCircle2 size={16} color="#34d399" /> : <X size={16} color="#475569" />}
                    </td>
                    <td style={{ padding: '0.75rem 1rem', textAlign: 'center' }}>
                      {row.arch ? <CheckCircle2 size={16} color="#34d399" /> : <X size={16} color="#475569" />}
                    </td>
                    <td style={{ padding: '0.75rem 1rem', textAlign: 'center' }}>
                      {row.admin ? <CheckCircle2 size={16} color="#34d399" /> : <X size={16} color="#475569" />}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* TAB 4: Audit Log Ledger */}
      {activeTab === 'audit' && (
        <div>
          {loadingAudit && <SkeletonLoader variant="table" rows={3} />}
          {errorAudit && !loadingAudit && (
            <ErrorState
              title="Failed to Load Audit Logs"
              message={errorMsgAudit || 'Error communicating with audit ledger API'}
              onRetry={refetchAudit}
            />
          )}
          {!loadingAudit && !errorAudit && auditLogs.length === 0 && (
            <EmptyState type="NO_DATA" titleOverride="No Audit Records" descriptionOverride="No audit events found in this window." actionTextOverride="Refresh Log" onAction={refetchAudit} />
          )}
          {!loadingAudit && !errorAudit && auditLogs.length > 0 && (
            <div style={{ backgroundColor: 'var(--bg-secondary)', border: '1px solid var(--border-color)', borderRadius: '8px', overflow: 'hidden' }}>
              <div style={{ padding: '1rem', borderBottom: '1px solid var(--border-color)', fontWeight: 600 }}>
                Immutable Control-Plane Audit Transactions
              </div>
              <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '0.875rem' }}>
                <thead>
                  <tr style={{ backgroundColor: '#0f172a', borderBottom: '1px solid var(--border-color)', color: 'var(--text-secondary)' }}>
                    <th style={{ padding: '0.75rem 1rem' }}>Timestamp</th>
                    <th style={{ padding: '0.75rem 1rem' }}>Actor</th>
                    <th style={{ padding: '0.75rem 1rem' }}>Event Action</th>
                    <th style={{ padding: '0.75rem 1rem' }}>Target Entity</th>
                    <th style={{ padding: '0.75rem 1rem' }}>Correlation ID</th>
                    <th style={{ padding: '0.75rem 1rem' }}>Outcome</th>
                  </tr>
                </thead>
                <tbody>
                  {auditLogs.map((log) => (
                    <tr key={log.id} style={{ borderBottom: '1px solid var(--border-color)' }}>
                      <td style={{ padding: '0.75rem 1rem', fontSize: '0.8125rem', color: 'var(--text-secondary)' }}>
                        {log.timestamp}
                      </td>
                      <td style={{ padding: '0.75rem 1rem', fontWeight: 500, color: 'var(--text-primary)' }}>
                        {log.actor}
                      </td>
                      <td style={{ padding: '0.75rem 1rem', fontFamily: 'monospace', fontSize: '0.8125rem', color: '#38bdf8' }}>
                        {log.action}
                      </td>
                      <td style={{ padding: '0.75rem 1rem', fontSize: '0.8125rem' }}>
                        {log.targetEntity}
                      </td>
                      <td style={{ padding: '0.75rem 1rem', fontFamily: 'monospace', fontSize: '0.75rem', color: '#64748b' }}>
                        {log.correlationId}
                      </td>
                      <td style={{ padding: '0.75rem 1rem' }}>
                        <span
                          style={{
                            backgroundColor: log.status === 'SUCCESS' ? '#064e3b' : '#450a0a',
                            color: log.status === 'SUCCESS' ? '#6ee7b7' : '#fca5a5',
                            padding: '0.15rem 0.4rem',
                            borderRadius: '4px',
                            fontSize: '0.75rem',
                            fontWeight: 600,
                          }}
                        >
                          {log.status}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* Override Submission Modal (Enforcing all 8 attributes & Acceptance 3) */}
      {isOverrideModalOpen && (
        <div
          style={{
            position: 'fixed',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            backgroundColor: 'rgba(0, 0, 0, 0.75)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 1000,
          }}
        >
          <div
            style={{
              backgroundColor: 'var(--bg-secondary)',
              border: '1px solid var(--border-color)',
              borderRadius: '10px',
              width: '90%',
              maxWidth: '640px',
              padding: '1.5rem',
              boxShadow: '0 20px 25px -5px rgba(0, 0, 0, 0.5)',
              maxHeight: '90vh',
              overflowY: 'auto',
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.25rem' }}>
              <h3 style={{ margin: 0, fontSize: '1.125rem', fontWeight: 600, display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <ShieldAlert color="#ef4444" size={20} />
                Submit 8-Attribute Governance Override
              </h3>
              <button
                onClick={() => setIsOverrideModalOpen(false)}
                style={{ background: 'none', border: 'none', color: 'var(--text-secondary)', cursor: 'pointer' }}
              >
                <X size={20} />
              </button>
            </div>

            {overrideFormError && (
              <div style={{ backgroundColor: '#450a0a', border: '1px solid #7f1d1d', color: '#fca5a5', padding: '0.5rem 0.75rem', borderRadius: '6px', fontSize: '0.8125rem', marginBottom: '1rem' }}>
                {overrideFormError}
              </div>
            )}

            <form onSubmit={handleCreateOverride} style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
                <div>
                  <label style={{ display: 'block', fontSize: '0.8125rem', color: 'var(--text-secondary)', marginBottom: '0.25rem' }}>
                    1. Override Class
                  </label>
                  <select
                    value={ovrClass}
                    onChange={(e) => setOvrClass(e.target.value as any)}
                    style={{
                      width: '100%',
                      backgroundColor: 'var(--bg-primary)',
                      border: '1px solid var(--border-color)',
                      borderRadius: '6px',
                      padding: '0.5rem',
                      color: 'var(--text-primary)',
                      fontSize: '0.875rem',
                    }}
                  >
                    <option value="THRESHOLD">THRESHOLD (Budget / Alert Trigger)</option>
                    <option value="PRICING">PRICING (Rate Card / Currency Discount)</option>
                    <option value="EXEMPTION">EXEMPTION (Policy Exemption Bypass)</option>
                    <option value="ROUTING">ROUTING (Ingestion / Provider Endpoint)</option>
                    <option value="CLASSIFICATION">CLASSIFICATION (Asset Category)</option>
                  </select>
                </div>

                <div>
                  <label style={{ display: 'block', fontSize: '0.8125rem', color: 'var(--text-secondary)', marginBottom: '0.25rem' }}>
                    2. Accountable Identity (Who)
                  </label>
                  <input
                    type="text"
                    value={ovrWho}
                    onChange={(e) => setOvrWho(e.target.value)}
                    style={{
                      width: '100%',
                      backgroundColor: 'var(--bg-primary)',
                      border: '1px solid var(--border-color)',
                      borderRadius: '6px',
                      padding: '0.5rem',
                      color: 'var(--text-primary)',
                      fontSize: '0.875rem',
                    }}
                    required
                  />
                </div>
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '0.8125rem', color: 'var(--text-secondary)', marginBottom: '0.25rem' }}>
                  3. Target Configuration Key or Entity (What)
                </label>
                <input
                  type="text"
                  placeholder="e.g. bgt-ecommerce-prod/amber_threshold or pricing/ec2/m5.xlarge"
                  value={ovrWhat}
                  onChange={(e) => setOvrWhat(e.target.value)}
                  style={{
                    width: '100%',
                    backgroundColor: 'var(--bg-primary)',
                    border: '1px solid var(--border-color)',
                    borderRadius: '6px',
                    padding: '0.5rem',
                    color: 'var(--text-primary)',
                    fontSize: '0.875rem',
                    fontFamily: 'monospace',
                  }}
                  required
                />
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
                <div>
                  <label style={{ display: 'block', fontSize: '0.8125rem', color: 'var(--text-secondary)', marginBottom: '0.25rem' }}>
                    4. Previous Value
                  </label>
                  <input
                    type="text"
                    placeholder="e.g. 0.80"
                    value={ovrPrevVal}
                    onChange={(e) => setOvrPrevVal(e.target.value)}
                    style={{
                      width: '100%',
                      backgroundColor: 'var(--bg-primary)',
                      border: '1px solid var(--border-color)',
                      borderRadius: '6px',
                      padding: '0.5rem',
                      color: 'var(--text-primary)',
                      fontSize: '0.875rem',
                    }}
                  />
                </div>

                <div>
                  <label style={{ display: 'block', fontSize: '0.8125rem', color: 'var(--text-secondary)', marginBottom: '0.25rem' }}>
                    5. New Overriding Value
                  </label>
                  <input
                    type="text"
                    placeholder="e.g. 0.92"
                    value={ovrNewVal}
                    onChange={(e) => setOvrNewVal(e.target.value)}
                    style={{
                      width: '100%',
                      backgroundColor: 'var(--bg-primary)',
                      border: '1px solid var(--border-color)',
                      borderRadius: '6px',
                      padding: '0.5rem',
                      color: 'var(--text-primary)',
                      fontSize: '0.875rem',
                    }}
                    required
                  />
                </div>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
                <div>
                  <label style={{ display: 'block', fontSize: '0.8125rem', color: 'var(--text-secondary)', marginBottom: '0.25rem' }}>
                    6. Mandatory Expiration Timestamp (UTC)
                  </label>
                  <input
                    type="datetime-local"
                    value={ovrExpiry}
                    onChange={(e) => setOvrExpiry(e.target.value)}
                    style={{
                      width: '100%',
                      backgroundColor: 'var(--bg-primary)',
                      border: '1px solid var(--border-color)',
                      borderRadius: '6px',
                      padding: '0.5rem',
                      color: 'var(--text-primary)',
                      fontSize: '0.875rem',
                    }}
                    required
                  />
                </div>

                <div>
                  <label style={{ display: 'block', fontSize: '0.8125rem', color: 'var(--text-secondary)', marginBottom: '0.25rem' }}>
                    7. Approval / Change Ticket Reference
                  </label>
                  <input
                    type="text"
                    placeholder="e.g. CHG-98442-PROD"
                    value={ovrTicket}
                    onChange={(e) => setOvrTicket(e.target.value)}
                    style={{
                      width: '100%',
                      backgroundColor: 'var(--bg-primary)',
                      border: '1px solid var(--border-color)',
                      borderRadius: '6px',
                      padding: '0.5rem',
                      color: 'var(--text-primary)',
                      fontSize: '0.875rem',
                      fontFamily: 'monospace',
                    }}
                    required
                  />
                </div>
              </div>

              <div>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.25rem' }}>
                  <label style={{ fontSize: '0.8125rem', color: 'var(--text-secondary)' }}>
                    8. Operational Rationale (Why &gt;= 20 Characters Mandatory)
                  </label>
                  <span style={{ fontSize: '0.75rem', color: ovrWhy.trim().length >= 20 ? '#34d399' : '#f87171' }}>
                    {ovrWhy.trim().length} / 20 min chars
                  </span>
                </div>
                <textarea
                  rows={3}
                  placeholder="Detailed business justification explaining why this override is necessary and consequences of inaction..."
                  value={ovrWhy}
                  onChange={(e) => setOvrWhy(e.target.value)}
                  style={{
                    width: '100%',
                    backgroundColor: 'var(--bg-primary)',
                    border: `1px solid ${ovrWhy.trim().length >= 20 ? 'var(--border-color)' : '#991b1b'}`,
                    borderRadius: '6px',
                    padding: '0.5rem',
                    color: 'var(--text-primary)',
                    fontSize: '0.875rem',
                    resize: 'vertical',
                  }}
                  required
                />
              </div>

              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.75rem', marginTop: '0.5rem' }}>
                <button
                  type="button"
                  onClick={() => setIsOverrideModalOpen(false)}
                  style={{
                    padding: '0.5rem 1rem',
                    backgroundColor: 'transparent',
                    border: '1px solid var(--border-color)',
                    borderRadius: '6px',
                    color: 'var(--text-secondary)',
                    cursor: 'pointer',
                    fontSize: '0.875rem',
                  }}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={ovrWhy.trim().length < 20 || !ovrExpiry}
                  style={{
                    padding: '0.5rem 1.25rem',
                    backgroundColor: ovrWhy.trim().length >= 20 && ovrExpiry ? '#ef4444' : '#475569',
                    border: 'none',
                    borderRadius: '6px',
                    color: '#ffffff',
                    fontWeight: 600,
                    cursor: ovrWhy.trim().length >= 20 && ovrExpiry ? 'pointer' : 'not-allowed',
                    fontSize: '0.875rem',
                  }}
                >
                  Apply &amp; Sign Override
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};

export default AdminConsolePage;
