import React, { useState, useEffect } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import {
  Menu,
  Search,
  ChevronRight,
  LogOut,
  User,
} from 'lucide-react';

interface HealthStatus {
  status: string;
  service?: string;
  version?: string;
  timestamp?: string;
  correlation_id?: string;
}

interface TopBarProps {
  onToggleMobileMenu: () => void;
  health: HealthStatus | null;
  loadingHealth: boolean;
  errorHealth: string | null;
}

const ROUTE_LABELS: Record<string, { section: string; title: string }> = {
  '/': { section: 'Home', title: 'FinOps Portal' },
  '/executive': { section: 'Overview', title: 'Dashboard' },
  '/control-tower': { section: 'Overview', title: 'Control Tower' },
  '/provider': { section: 'Cloud Estate', title: 'Providers' },
  '/providers': { section: 'Cloud Estate', title: 'Providers' },
  '/hierarchy': { section: 'Cloud Estate', title: 'Hierarchy' },
  '/inventory': { section: 'Cloud Estate', title: 'Inventory' },
  '/service': { section: 'Cloud Estate', title: 'Services' },
  '/services': { section: 'Cloud Estate', title: 'Services' },
  '/graph': { section: 'Cloud Estate', title: 'Dependencies' },
  '/topology': { section: 'Cloud Estate', title: 'Dependencies' },
  '/cost-explorer': { section: 'Cost', title: 'Cost Explorer' },
  '/investigation': { section: 'Cost', title: 'Cost Increases' },
  '/estimator': { section: 'Cost', title: 'Estimator' },
  '/commitments': { section: 'Cost', title: 'Commitments' },
  '/usage': { section: 'Usage', title: 'Usage' },
  '/runtime': { section: 'Usage', title: 'Runtime' },
  '/quotas': { section: 'Usage', title: 'Quotas' },
  '/budgets': { section: 'Governance', title: 'Budgets' },
  '/planning': { section: 'Governance', title: 'Budget Planning' },
  '/policies': { section: 'Governance', title: 'Policies' },
  '/remediation': { section: 'Governance', title: 'Remediation' },
  '/provisioning': { section: 'Governance', title: 'Provisioning' },
  '/statements': { section: 'Finance', title: 'Statements' },
  '/reports': { section: 'Finance', title: 'Reports' },
  '/reconciliation': { section: 'Finance', title: 'Reconciliation' },
  '/settings': { section: 'Administration', title: 'Tenants' },
  '/connectors': { section: 'Administration', title: 'Cloud Connections' },
  '/users': { section: 'Administration', title: 'Users & Roles' },
  '/admin': { section: 'Administration', title: 'Configuration' },
  '/masterdata': { section: 'Administration', title: 'Master Data' },
  '/audit': { section: 'Administration', title: 'Audit Log' },
  '/about': { section: 'Administration', title: 'About' },
  '/onboarding': { section: 'Onboarding', title: 'Onboarding Wizard' },
  '/resource-detail': { section: 'Cloud Estate', title: 'Resource Detail' },
};

export const TopBar: React.FC<TopBarProps> = ({
  onToggleMobileMenu,
  health,
  loadingHealth,
  errorHealth,
}) => {
  const auth = useAuth();
  const location = useLocation();
  const [searchQuery, setSearchQuery] = useState('');

  // Global Ctrl+K / Cmd+K listener
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        const searchInput = document.getElementById('global-topbar-search');
        if (searchInput) searchInput.focus();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  // Compute breadcrumb segments
  const path = location.pathname.startsWith('/resource/')
    ? '/resource-detail'
    : location.pathname;
  const currentRouteMeta = ROUTE_LABELS[path] || { section: 'Platform', title: 'Details' };

  return (
    <header
      role="banner"
      style={{
        position: 'sticky',
        top: 0,
        zIndex: 40,
        height: '60px',
        backgroundColor: 'var(--bg-secondary)',
        borderBottom: '1px solid var(--border-color)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '0 1.25rem',
        boxSizing: 'border-box',
        width: '100%',
      }}
    >
      {/* Left: Mobile Toggle + Logo + Breadcrumbs */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', minWidth: 0 }}>
        {/* Mobile drawer toggle (< 1024px) */}
        <button
          type="button"
          onClick={onToggleMobileMenu}
          aria-label="Toggle navigation drawer"
          className="mobile-drawer-btn"
          style={{
            display: 'none',
            alignItems: 'center',
            justifyContent: 'center',
            background: 'transparent',
            border: 'none',
            color: 'var(--text-primary)',
            cursor: 'pointer',
            padding: '0.4rem',
            borderRadius: '6px',
          }}
        >
          <Menu size={20} />
        </button>

        {/* Logo */}
        <Link
          to="/"
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '0.6rem',
            textDecoration: 'none',
            flexShrink: 0,
          }}
        >
          <div
            style={{
              width: '32px',
              height: '32px',
              borderRadius: '8px',
              background: 'linear-gradient(135deg, #0284c7, #06b6d4)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontWeight: 'bold',
              color: '#fff',
              fontSize: '0.9rem',
            }}
          >
            CL
          </div>
          <span
            style={{
              fontSize: '1.25rem',
              fontWeight: 700,
              letterSpacing: '-0.02em',
              color: 'var(--text-primary)',
            }}
          >
            CloudLens
          </span>
        </Link>

        {/* Version Badge */}
        <span
          style={{
            fontSize: '0.75rem',
            backgroundColor: '#0369a1',
            color: '#e0f2fe',
            padding: '0.15rem 0.5rem',
            borderRadius: '9999px',
            fontWeight: 600,
            flexShrink: 0,
          }}
        >
          {health ? `v${health.version}` : 'v0.1.0'}
        </span>

        {/* Top bar breadcrumb trail */}
        <nav
          aria-label="Breadcrumb navigation"
          className="topbar-breadcrumbs"
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '0.35rem',
            marginLeft: '0.75rem',
            fontSize: '0.8125rem',
            color: 'var(--text-secondary)',
            whiteSpace: 'nowrap',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
          }}
        >
          <Link
            to="/"
            style={{
              color: 'var(--text-secondary)',
              textDecoration: 'none',
              fontWeight: 500,
            }}
          >
            Home
          </Link>
          {path !== '/' && (
            <>
              <ChevronRight size={13} style={{ opacity: 0.6 }} aria-hidden="true" />
              <span>{currentRouteMeta.section}</span>
              <ChevronRight size={13} style={{ opacity: 0.6 }} aria-hidden="true" />
              <span style={{ color: 'var(--text-primary)', fontWeight: 600 }}>
                {currentRouteMeta.title}
              </span>
            </>
          )}
        </nav>
      </div>

      {/* Center: Global Search */}
      <div
        className="topbar-search-container"
        style={{
          flex: '0 1 360px',
          margin: '0 1rem',
          position: 'relative',
        }}
      >
        <Search
          size={14}
          style={{
            position: 'absolute',
            left: '0.75rem',
            top: '50%',
            transform: 'translateY(-50%)',
            color: 'var(--text-secondary)',
            pointerEvents: 'none',
          }}
          aria-hidden="true"
        />
        <input
          id="global-topbar-search"
          type="text"
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          placeholder="Search resources, metrics, budgets... (Ctrl+K)"
          aria-label="Search resources, metrics, and budgets"
          style={{
            width: '100%',
            backgroundColor: 'var(--bg-primary)',
            color: 'var(--text-primary)',
            border: '1px solid var(--border-color)',
            borderRadius: '6px',
            padding: '0.35rem 0.6rem 0.35rem 2.2rem',
            fontSize: '0.8125rem',
            outline: 'none',
            boxSizing: 'border-box',
          }}
        />
      </div>

      {/* Right: Tenant Switcher + API Health + User Menu */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.85rem', flexShrink: 0 }}>
        {/* API Health Probe Badge */}
        <div
          role="status"
          aria-label={loadingHealth ? 'API Probing' : errorHealth ? 'API Offline' : 'API Healthy'}
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: '0.35rem',
            fontSize: '0.75rem',
            padding: '0.2rem 0.55rem',
            borderRadius: '6px',
            backgroundColor: loadingHealth ? '#475569' : errorHealth ? '#7f1d1d' : '#064e3b',
            color: loadingHealth ? '#cbd5e1' : errorHealth ? '#fca5a5' : '#6ee7b7',
            fontWeight: 600,
          }}
        >
          <span
            style={{
              width: '7px',
              height: '7px',
              borderRadius: '50%',
              backgroundColor: loadingHealth ? '#94a3b8' : errorHealth ? '#ef4444' : '#10b981',
            }}
          />
          {loadingHealth ? 'Probing...' : errorHealth ? 'API Offline' : 'API Healthy'}
        </div>

        {/* Tenant Switcher */}
        {auth.tenants && auth.tenants.length > 0 && (
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.3rem' }}>
            <label
              htmlFor="tenant-switcher"
              style={{
                color: 'var(--text-secondary)',
                fontSize: '0.75rem',
                fontWeight: 500,
              }}
            >
              Tenant:
            </label>
            <select
              id="tenant-switcher"
              value={auth.currentTenant?.id || ''}
              onChange={(e) => auth.switchTenant(e.target.value)}
              style={{
                backgroundColor: 'var(--bg-primary)',
                color: 'var(--text-primary)',
                border: '1px solid var(--border-color)',
                borderRadius: '6px',
                padding: '0.25rem 0.5rem',
                fontSize: '0.75rem',
                fontWeight: 600,
                outline: 'none',
                cursor: 'pointer',
              }}
            >
              {auth.tenants.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.name}
                </option>
              ))}
            </select>
          </div>
        )}

        {/* User Profile Display and Sign Out */}
        {auth.isAuthenticated && (
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '0.35rem',
                fontSize: '0.8125rem',
              }}
            >
              <User size={14} style={{ color: 'var(--text-secondary)' }} aria-hidden="true" />
              <span
                id="header-user-display"
                style={{
                  color: 'var(--text-primary)',
                  fontWeight: 600,
                  maxWidth: '140px',
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  whiteSpace: 'nowrap',
                }}
              >
                {auth.user?.display_name || auth.user?.email}
              </span>
            </div>

            <button
              type="button"
              id="header-signout-btn"
              onClick={() => auth.signOut()}
              aria-label="Sign out of CloudLens"
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '0.25rem',
                backgroundColor: 'transparent',
                color: 'var(--text-secondary)',
                border: '1px solid var(--border-color)',
                borderRadius: '6px',
                padding: '0.25rem 0.55rem',
                fontSize: '0.75rem',
                cursor: 'pointer',
                fontWeight: 500,
              }}
            >
              <LogOut size={12} aria-hidden="true" />
              <span>Sign out</span>
            </button>
          </div>
        )}
      </div>
    </header>
  );
};
