import React from 'react';
import {
  PieChart,
  DollarSign,
  TrendingUp,
  Cpu,
  FileCheck,
  Settings,
  Shield,
} from 'lucide-react';

export type UserRole = string;

export interface NavItem {
  id: string;
  label: string;
  path: string;
  icon?: string;
  badge?: string;
}

export const ROLE_NAVIGATION_SECTIONS: Record<
  string,
  { roleTitle: string; description: string; scopeGrant: string; items: NavItem[] }
> = {
  EXECUTIVE: {
    roleTitle: 'Executive Leadership',
    description: 'High-level cloud estate summaries, macro budget forecasts, and governance posture.',
    scopeGrant: 'Global Enterprise Scope',
    items: [
      { id: 'exec-summary', label: 'Executive Summary', path: '/executive/summary' },
      { id: 'exec-forecast', label: 'Macro Cloud Forecast', path: '/executive/forecast' },
      { id: 'exec-budgets', label: 'Portfolio Budget Health', path: '/executive/budgets' },
      { id: 'exec-freshness', label: 'Provider Freshness Radar', path: '/executive/freshness' },
    ],
  },
  FINANCE: {
    roleTitle: 'Finance & Accounting',
    description: 'Cost allocation packs, showback/chargeback statements, general ledger journals, FX policies.',
    scopeGrant: 'Cost Centres & Business Units',
    items: [
      { id: 'fin-allocations', label: 'Cost Allocation Engine', path: '/finance/allocations' },
      { id: 'fin-showback', label: 'Showback / Chargeback Packs', path: '/finance/showback' },
      { id: 'fin-budgets', label: 'Budget Allocations & Variance', path: '/finance/budgets' },
      { id: 'fin-rates', label: 'Currency FX & Rate Cards', path: '/finance/rates' },
    ],
  },
  FINOPS: {
    roleTitle: 'FinOps Practitioner',
    description: 'Waste remediation, commitment discounting, unit economics, and anomaly detection.',
    scopeGrant: 'All Cloud Accounts & Tags',
    items: [
      { id: 'finops-waste', label: 'Idle & Orphaned Resources', path: '/finops/waste', badge: '12 new' },
      { id: 'finops-commitments', label: 'Commitment Optimizer', path: '/finops/commitments' },
      { id: 'finops-anomalies', label: 'Real-time Cost Anomalies', path: '/finops/anomalies', badge: '3 alerts' },
      { id: 'finops-unit', label: 'Unit Economics & KPI Ratios', path: '/finops/unit-economics' },
    ],
  },
  ENGINEERING: {
    roleTitle: 'Engineering & DevOps',
    description: 'Application services, dependency maps, quotas, and pre-deployment provisioning gates.',
    scopeGrant: 'Application Tier & Workspaces',
    items: [
      { id: 'eng-apps', label: 'Applications & Services', path: '/engineering/apps' },
      { id: 'eng-topology', label: 'Service Dependency Graph', path: '/engineering/topology' },
      { id: 'eng-gates', label: 'Cost-Aware Provisioning Gate', path: '/engineering/gates' },
      { id: 'eng-quotas', label: 'Cloud Provider Quotas', path: '/engineering/quotas' },
    ],
  },
  AUDITOR: {
    roleTitle: 'Internal Audit & Governance',
    description: 'Immutable provenance logs, policy breaches, master data compliance, and access reviews.',
    scopeGrant: 'Read-Only Audit Trail',
    items: [
      { id: 'audit-log', label: 'Immutable Audit Trail', path: '/audit/trail' },
      { id: 'audit-policies', label: 'Tag Policy & Governance Exceptions', path: '/audit/policies' },
      { id: 'audit-access', label: 'RBAC Access Reviews', path: '/audit/access' },
      { id: 'audit-master', label: 'Master Data Integrity', path: '/audit/masterdata' },
    ],
  },
  TENANT_ADMIN: {
    roleTitle: 'Tenant Administrator',
    description: 'Tenant isolation settings, cloud connectors, bulk data onboarding, and user roles.',
    scopeGrant: 'Tenant Root (Full Admin)',
    items: [
      { id: 'admin-connectors', label: 'Provider Connectors', path: '/admin/connectors' },
      { id: 'admin-imports', label: 'Bulk Import & Onboarding', path: '/admin/imports' },
      { id: 'admin-users', label: 'Identity & Scope Grants', path: '/admin/users' },
      { id: 'admin-system', label: 'System Health & Metrics', path: '/admin/system' },
    ],
  },
};

export interface RoleShapedNavProps {
  currentRole: UserRole;
  onRoleChange?: (role: UserRole) => void;
  activePath?: string;
  onNavigate?: (path: string) => void;
  className?: string;
}

/**
 * Role-Shaped Navigation Component
 * Enforces BBP Section 31: "role-shaped navigation: navigation tailored to role personas".
 */
export const RoleShapedNav: React.FC<RoleShapedNavProps> = ({
  currentRole,
  onRoleChange,
  activePath,
  onNavigate,
  className = '',
}) => {
  const roleConfig = ROLE_NAVIGATION_SECTIONS[currentRole];

  const getRoleIcon = (role: UserRole) => {
    switch (role) {
      case 'EXECUTIVE':
        return <PieChart size={14} aria-hidden="true" />;
      case 'FINANCE':
        return <DollarSign size={14} aria-hidden="true" />;
      case 'FINOPS':
        return <TrendingUp size={14} aria-hidden="true" />;
      case 'ENGINEERING':
        return <Cpu size={14} aria-hidden="true" />;
      case 'AUDITOR':
        return <FileCheck size={14} aria-hidden="true" />;
      case 'TENANT_ADMIN':
      default:
        return <Settings size={14} aria-hidden="true" />;
    }
  };

  return (
    <nav
      aria-label="Role Navigation"
      className={`cloudlens-role-nav ${className}`}
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: '0.75rem',
        padding: '1rem',
        backgroundColor: 'var(--bg-secondary)',
        border: '1px solid var(--border-color)',
        borderRadius: '8px',
      }}
    >
      {/* Role Selector & Persona Context */}
      <div
        style={{
          display: 'flex',
          flexDirection: 'column',
          gap: '0.4rem',
          borderBottom: '1px solid var(--border-color)',
          paddingBottom: '0.75rem',
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
            <Shield size={14} style={{ color: 'var(--accent-blue, #38bdf8)' }} aria-hidden="true" />
            <span style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-secondary)' }}>
              Active Persona:
            </span>
          </div>

          {onRoleChange && (
            <div>
              <label htmlFor="role-persona-select" className="sr-only" style={{ display: 'none' }}>
                Switch role persona
              </label>
              <select
                id="role-persona-select"
                value={currentRole}
                onChange={(e) => onRoleChange(e.target.value as UserRole)}
                aria-label="Switch active role persona"
                style={{
                  padding: '0.2rem 0.4rem',
                  fontSize: '0.75rem',
                  borderRadius: '4px',
                  border: '1px solid var(--border-color)',
                  backgroundColor: 'var(--bg-primary)',
                  color: 'var(--text-primary)',
                  cursor: 'pointer',
                }}
              >
                {Object.keys(ROLE_NAVIGATION_SECTIONS).map((roleKey) => (
                  <option key={roleKey} value={roleKey}>
                    {ROLE_NAVIGATION_SECTIONS[roleKey]?.roleTitle || roleKey}
                  </option>
                ))}
              </select>
            </div>
          )}
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginTop: '0.2rem' }}>
          <div style={{ color: 'var(--accent-blue, #38bdf8)' }}>{getRoleIcon(currentRole)}</div>
          <div>
            <strong style={{ fontSize: '0.875rem', color: 'var(--text-primary)' }}>
              {roleConfig.roleTitle}
            </strong>
            <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
              Scope: {roleConfig.scopeGrant}
            </div>
          </div>
        </div>
      </div>

      {/* Role-Specific Navigation Links */}
      <ul
        style={{
          listStyle: 'none',
          margin: 0,
          padding: 0,
          display: 'flex',
          flexDirection: 'column',
          gap: '0.25rem',
        }}
      >
        {roleConfig.items.map((item) => {
          const isActive = activePath === item.path;

          return (
            <li key={item.id}>
              <button
                type="button"
                onClick={() => onNavigate && onNavigate(item.path)}
                aria-current={isActive ? 'page' : undefined}
                style={{
                  width: '100%',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  padding: '0.5rem 0.75rem',
                  borderRadius: '6px',
                  border: 'none',
                  backgroundColor: isActive ? 'rgba(56, 189, 248, 0.15)' : 'transparent',
                  color: isActive ? 'var(--accent-blue, #38bdf8)' : 'var(--text-secondary)',
                  fontWeight: isActive ? 600 : 500,
                  fontSize: '0.8125rem',
                  cursor: 'pointer',
                  textAlign: 'left',
                  transition: 'all 0.15s ease',
                }}
                onMouseEnter={(e) => {
                  if (!isActive) {
                    (e.currentTarget as HTMLElement).style.backgroundColor =
                      'rgba(255, 255, 255, 0.05)';
                    (e.currentTarget as HTMLElement).style.color = 'var(--text-primary)';
                  }
                }}
                onMouseLeave={(e) => {
                  if (!isActive) {
                    (e.currentTarget as HTMLElement).style.backgroundColor = 'transparent';
                    (e.currentTarget as HTMLElement).style.color = 'var(--text-secondary)';
                  }
                }}
              >
                <span>{item.label}</span>
                {item.badge && (
                  <span
                    style={{
                      fontSize: '0.7rem',
                      padding: '0.1rem 0.35rem',
                      borderRadius: '4px',
                      backgroundColor: 'rgba(239, 68, 68, 0.2)',
                      color: '#f87171',
                      border: '1px solid rgba(239, 68, 68, 0.4)',
                    }}
                  >
                    {item.badge}
                  </span>
                )}
              </button>
            </li>
          );
        })}
      </ul>
    </nav>
  );
};
