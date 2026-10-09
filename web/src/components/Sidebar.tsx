import React from 'react';
import { NavLink } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import {
  LayoutDashboard,
  Compass,
  Cloud,
  FolderTree,
  Layers,
  Server,
  Network,
  DollarSign,
  TrendingUp,
  Calculator,
  FileCheck,
  Activity,
  Clock,
  Gauge,
  PiggyBank,
  LineChart,
  ShieldCheck,
  Wrench,
  Package,
  Receipt,
  FileText,
  Scale,
  Building2,
  Plug,
  Users,
  Settings,
  Database,
  HardDrive,
  History,
  Info,
  ChevronLeft,
  ChevronRight,
  X,
  LucideIcon,
} from 'lucide-react';

export interface NavItemConfig {
  label: string;
  to: string;
  icon: LucideIcon;
  capability?: string;
  badge?: string;
}

export interface NavGroupConfig {
  title: string;
  items: NavItemConfig[];
}

export const SIDEBAR_NAV_GROUPS: NavGroupConfig[] = [
  {
    title: 'OVERVIEW',
    items: [
      { label: 'Dashboard', to: '/executive', icon: LayoutDashboard },
      { label: 'Control Tower', to: '/control-tower', icon: Compass, capability: 'platform.observe' },
    ],
  },
  {
    title: 'CLOUD ESTATE',
    items: [
      { label: 'Providers', to: '/provider', icon: Cloud },
      { label: 'Hierarchy', to: '/hierarchy', icon: FolderTree },
      { label: 'Inventory', to: '/inventory', icon: Layers },
      { label: 'Services', to: '/service', icon: Server },
      { label: 'Dependencies', to: '/graph', icon: Network },
    ],
  },
  {
    title: 'COST',
    items: [
      { label: 'Cost Explorer', to: '/cost-explorer', icon: DollarSign },
      { label: 'Cost Increases', to: '/investigation', icon: TrendingUp },
      { label: 'Estimator', to: '/estimator', icon: Calculator },
      { label: 'Commitments', to: '/commitments', icon: FileCheck },
    ],
  },
  {
    title: 'USAGE',
    items: [
      { label: 'Usage', to: '/usage', icon: Activity },
      { label: 'Runtime', to: '/runtime', icon: Clock },
      { label: 'Quotas', to: '/quotas', icon: Gauge },
    ],
  },
  {
    title: 'GOVERNANCE',
    items: [
      { label: 'Budgets', to: '/budgets', icon: PiggyBank },
      { label: 'Budget Planning', to: '/planning', icon: LineChart },
      { label: 'Policies', to: '/policies', icon: ShieldCheck },
      { label: 'Remediation', to: '/remediation', icon: Wrench },
      { label: 'Provisioning', to: '/provisioning', icon: Package },
    ],
  },
  {
    title: 'FINANCE',
    items: [
      { label: 'Statements', to: '/statements', icon: Receipt },
      { label: 'Reports', to: '/reports', icon: FileText },
      { label: 'Reconciliation', to: '/reconciliation', icon: Scale },
    ],
  },
  {
    title: 'ADMINISTRATION',
    items: [
      { label: 'Tenants', to: '/settings', icon: Building2, capability: 'tenants:settings:read' },
      { label: 'Cloud Connections', to: '/connectors', icon: Plug, capability: 'admin:connectors:manage' },
      { label: 'Users & Roles', to: '/users', icon: Users, capability: 'iam:manage' },
      { label: 'Configuration', to: '/admin', icon: Settings, capability: 'admin:access' },
      { label: 'Master Data', to: '/masterdata', icon: Database, capability: 'admin:access' },
      { label: 'Data Sources', to: '/connectors', icon: HardDrive, capability: 'admin:connectors:manage' },
      { label: 'Audit Log', to: '/audit', icon: History, capability: 'audit:read' },
      { label: 'About', to: '/about', icon: Info },
    ],
  },
];

interface SidebarProps {
  collapsed: boolean;
  onToggleCollapse: () => void;
  mobileOpen: boolean;
  onCloseMobile: () => void;
}

export const Sidebar: React.FC<SidebarProps> = ({
  collapsed,
  onToggleCollapse,
  mobileOpen,
  onCloseMobile,
}) => {
  const auth = useAuth();

  // Helper to check capability filter
  const isItemVisible = (item: NavItemConfig) => {
    if (!item.capability) return true;
    return auth.hasCapability(item.capability);
  };

  const navContent = (isDrawer = false) => (
    <nav
      aria-label="Sidebar Primary Navigation"
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: '1.25rem',
        padding: isDrawer ? '1rem 0.75rem' : collapsed ? '1rem 0.5rem' : '1.25rem 0.85rem',
        width: '100%',
        boxSizing: 'border-box',
      }}
    >
      {SIDEBAR_NAV_GROUPS.map((group) => {
        const visibleItems = group.items.filter(isItemVisible);
        if (visibleItems.length === 0) return null;

        return (
          <div key={group.title} style={{ display: 'flex', flexDirection: 'column', gap: '0.2rem' }}>
            {(!collapsed || isDrawer) ? (
              <div
                style={{
                  fontSize: '0.6875rem',
                  fontWeight: 700,
                  letterSpacing: '0.06em',
                  color: 'var(--text-secondary)',
                  padding: '0.25rem 0.5rem',
                  textTransform: 'uppercase',
                }}
              >
                {group.title}
              </div>
            ) : (
              <div
                style={{
                  height: '1px',
                  backgroundColor: 'var(--border-color)',
                  margin: '0.4rem 0.25rem',
                  opacity: 0.5,
                }}
              />
            )}

            {visibleItems.map((item) => {
              const Icon = item.icon;
              return (
                <NavLink
                  key={item.label + item.to}
                  to={item.to}
                  onClick={() => {
                    if (isDrawer) onCloseMobile();
                  }}
                  title={collapsed && !isDrawer ? item.label : undefined}
                  style={({ isActive }) => ({
                    display: 'flex',
                    alignItems: 'center',
                    gap: collapsed && !isDrawer ? 0 : '0.65rem',
                    justifyContent: collapsed && !isDrawer ? 'center' : 'flex-start',
                    padding: collapsed && !isDrawer ? '0.5rem' : '0.45rem 0.65rem',
                    borderRadius: '6px',
                    textDecoration: 'none',
                    fontSize: '0.8125rem',
                    fontWeight: isActive ? 600 : 500,
                    backgroundColor: isActive ? '#0369a1' : 'transparent',
                    color: isActive ? '#ffffff' : 'var(--text-secondary)',
                    transition: 'all 0.12s ease',
                    whiteSpace: 'nowrap',
                    position: 'relative',
                  })}
                >
                  <Icon size={16} style={{ flexShrink: 0 }} />
                  {(!collapsed || isDrawer) && (
                    <span style={{ overflow: 'hidden', textOverflow: 'ellipsis' }}>
                      {item.label}
                    </span>
                  )}
                </NavLink>
              );
            })}
          </div>
        );
      })}
    </nav>
  );

  return (
    <>
      {/* 1. Desktop Fixed Sidebar (>= 1024px) */}
      <aside
        id="desktop-left-sidebar"
        aria-label="Desktop Navigation Sidebar"
        className="cloudlens-desktop-sidebar"
        style={{
          width: collapsed ? '68px' : '240px',
          minWidth: collapsed ? '68px' : '240px',
          maxWidth: collapsed ? '68px' : '240px',
          transition: 'width 0.2s cubic-bezier(0.4, 0, 0.2, 1), min-width 0.2s cubic-bezier(0.4, 0, 0.2, 1)',
          backgroundColor: 'var(--bg-secondary)',
          borderRight: '1px solid var(--border-color)',
          display: 'flex',
          flexDirection: 'column',
          justifyContent: 'space-between',
          position: 'sticky',
          top: '60px',
          height: 'calc(100vh - 60px)',
          overflowY: 'auto',
          overflowX: 'hidden',
          flexShrink: 0,
          boxSizing: 'border-box',
          zIndex: 30,
        }}
      >
        <div style={{ flex: 1 }}>{navContent(false)}</div>

        {/* Collapse / Expand Toggle Button Footer */}
        <div
          style={{
            borderTop: '1px solid var(--border-color)',
            padding: '0.75rem',
            display: 'flex',
            justifyContent: collapsed ? 'center' : 'flex-end',
            backgroundColor: 'var(--bg-secondary)',
          }}
        >
          <button
            type="button"
            id="sidebar-collapse-toggle-btn"
            onClick={onToggleCollapse}
            aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
            title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: '0.4rem',
              backgroundColor: 'transparent',
              border: '1px solid var(--border-color)',
              color: 'var(--text-secondary)',
              borderRadius: '6px',
              padding: '0.35rem 0.55rem',
              fontSize: '0.75rem',
              cursor: 'pointer',
              fontWeight: 500,
            }}
          >
            {collapsed ? (
              <ChevronRight size={14} />
            ) : (
              <>
                <ChevronLeft size={14} />
                <span>Collapse</span>
              </>
            )}
          </button>
        </div>
      </aside>

      {/* 2. Mobile Drawer (< 1024px) */}
      {mobileOpen && (
        <div
          id="mobile-nav-drawer"
          role="dialog"
          aria-modal="true"
          aria-label="Navigation Drawer"
          style={{
            position: 'fixed',
            inset: 0,
            zIndex: 100,
            display: 'flex',
          }}
        >
          {/* Backdrop Overlay */}
          <div
            onClick={onCloseMobile}
            style={{
              position: 'fixed',
              inset: 0,
              backgroundColor: 'rgba(0, 0, 0, 0.65)',
              backdropFilter: 'blur(2px)',
            }}
          />

          {/* Drawer Panel */}
          <aside
            style={{
              position: 'relative',
              width: '280px',
              maxWidth: '85vw',
              height: '100%',
              backgroundColor: 'var(--bg-secondary)',
              borderRight: '1px solid var(--border-color)',
              display: 'flex',
              flexDirection: 'column',
              zIndex: 101,
              overflowY: 'auto',
              boxShadow: '4px 0 24px rgba(0, 0, 0, 0.4)',
            }}
          >
            {/* Drawer Header */}
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                padding: '1rem',
                borderBottom: '1px solid var(--border-color)',
              }}
            >
              <span style={{ fontWeight: 700, fontSize: '1rem', color: 'var(--text-primary)' }}>
                Navigation
              </span>
              <button
                type="button"
                onClick={onCloseMobile}
                aria-label="Close navigation drawer"
                style={{
                  background: 'transparent',
                  border: 'none',
                  color: 'var(--text-secondary)',
                  cursor: 'pointer',
                  padding: '0.3rem',
                  borderRadius: '6px',
                }}
              >
                <X size={18} />
              </button>
            </div>

            <div style={{ flex: 1 }}>{navContent(true)}</div>
          </aside>
        </div>
      )}
    </>
  );
};
