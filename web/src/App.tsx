import React, { useEffect, useState, Suspense, lazy } from 'react';
import {
  BrowserRouter,
  Routes,
  Route,
  Link,
  NavLink,
  Navigate,
  useNavigate,
  useParams,
} from 'react-router-dom';

// Core Dashboard & Explorer Pages
import { ExecutiveDashboard } from './pages/ExecutiveDashboard';
import { ProviderDashboard } from './pages/ProviderDashboard';
import { ServiceDashboard } from './pages/ServiceDashboard';
import { HierarchyExplorer } from './pages/HierarchyExplorer';
import { ServiceInventory } from './pages/ServiceInventory';
import { ResourceDetailPage } from './pages/ResourceDetailPage';
import { CostExplorerPage } from './pages/CostExplorerPage';
import { InvestigationViewPage } from './pages/InvestigationViewPage';
import { BudgetManagementPage } from './pages/BudgetManagementPage';
import { PolicyManagementPage } from './pages/PolicyManagementPage';
import { ConnectorManagementPage } from './pages/ConnectorManagementPage';
import { AdminConsolePage } from './pages/AdminConsolePage';
import { MasterDataConsole } from './pages/MasterDataConsole';
import { ControlTowerPage } from './pages/ControlTowerPage';
import { ExplanationLayerView } from './pages/ExplanationLayerView';

// Addendum B Screens (S-21 to S-27)
import { CostEstimatorPage } from './pages/CostEstimatorPage';
import { QuotaHeadroomPage } from './pages/QuotaHeadroomPage';
import { ProvisioningRequestsPage } from './pages/ProvisioningRequestsPage';
import { RemediationBoardPage } from './pages/RemediationBoardPage';
import { ShowbackStatementsPage } from './pages/ShowbackStatementsPage';
import { BudgetPlanningPage } from './pages/BudgetPlanningPage';
import { CommitmentRenewalsPage } from './pages/CommitmentRenewalsPage';

// Portal, Identity, Operations & Governance Screens
import { LoginPage } from './pages/LoginPage';
import { LandingPage } from './pages/LandingPage';
import { UsageDetailPage } from './pages/UsageDetailPage';
import { RuntimeViewPage } from './pages/RuntimeViewPage';
import { OnboardingWizardPage } from './pages/OnboardingWizardPage';
import { UsersRbacPage } from './pages/UsersRbacPage';
import { AuditLogPage } from './pages/AuditLogPage';
import { ReportsPage } from './pages/ReportsPage';
import { SettingsPage } from './pages/SettingsPage';
import { ForbiddenPage } from './pages/ForbiddenPage';
import { NotFoundPage } from './pages/NotFoundPage';
import { AboutPage } from './pages/AboutPage';
import { DemoModeBanner } from './components/DemoModeBanner';
import { MaintenanceModeBanner } from './components/MaintenanceModeBanner';

// Lazy-load heavy screens (Dependency graph & conditional dev showcase)
const DependencyGraphPage = lazy(() =>
  import('./pages/DependencyGraphPage').then((m) => ({ default: m.DependencyGraphPage }))
);

// Conditional Dev Showcase (Pruned from production builds)
const isDevelopment = import.meta.env.DEV;

const DesignSystemShowcase = isDevelopment
  ? lazy(() =>
      import('./pages/DesignSystemShowcase').then((m) => ({
        default: m.DesignSystemShowcase,
      }))
    )
  : null;

export type CanonicalRole =
  | 'SUPER_ADMIN'
  | 'PLATFORM_ADMIN'
  | 'TENANT_ADMIN'
  | 'FINOPS_LEAD'
  | 'FINOPS_ANALYST'
  | 'ENGINEERING_LEAD'
  | 'DEVELOPER'
  | 'FINANCE_CONTROLLER'
  | 'AUDITOR';

interface HealthStatus {
  status: string;
  service: string;
  version: string;
  timestamp: string;
  correlation_id: string;
}

// Role-Shaped Route Authorization Guard
interface ProtectedRouteProps {
  allowedRoles: CanonicalRole[];
  currentRole: CanonicalRole;
  children: React.ReactNode;
}

const ProtectedRoute: React.FC<ProtectedRouteProps> = ({
  allowedRoles,
  currentRole,
  children,
}) => {
  if (!allowedRoles.includes(currentRole)) {
    return <Navigate to="/403" replace />;
  }
  return <>{children}</>;
};

// Resource detail wrapper with parameter extraction
const ResourceDetailWrapper: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();

  return (
    <ResourceDetailPage
      initialResourceId={id || 'res-aws-vm-01'}
      onNavigateToCostExplorer={(dim, gId) => {
        navigate(`/cost-explorer?dimension=${dim || 'SERVICE'}&group=${gId || ''}`);
      }}
      onNavigateToInvestigation={(entId) => {
        navigate(`/investigation?entity=${entId}`);
      }}
    />
  );
};

// Main App Layout & Router Shell
const AppLayout: React.FC = () => {
  const [health, setHealth] = useState<HealthStatus | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [userRole, setUserRole] = useState<CanonicalRole>(() => {
    return (localStorage.getItem('cloudlens_user_role') as CanonicalRole) || 'SUPER_ADMIN';
  });
  const [isDemo, setIsDemo] = useState<boolean>(() => {
    const saved = localStorage.getItem('cloudlens_is_demo');
    return saved !== null ? saved === 'true' : true;
  });

  const [isMaintenanceMode, setIsMaintenanceMode] = useState<boolean>(false);
  const [maintMessage, setMaintMessage] = useState<string>('CloudLens is currently undergoing scheduled platform maintenance. Mutating operations are paused.');

  const handleRoleChange = (role: CanonicalRole) => {
    setUserRole(role);
    localStorage.setItem('cloudlens_user_role', role);
  };

  const handleToggleDemo = () => {
    const next = !isDemo;
    setIsDemo(next);
    localStorage.setItem('cloudlens_is_demo', String(next));
  };

  useEffect(() => {
    fetch('/api/v1/health')
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP error ${res.status}`);
        return res.json();
      })
      .then((data: HealthStatus) => {
        setHealth(data);
        setLoading(false);
      })
      .catch((err: Error) => {
        setError(err.message);
        setLoading(false);
      });

    // Check maintenance mode (IMP-01)
    fetch('/api/v1/control-tower/overview')
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => {
        if (data && data.maintenance_mode) {
          setIsMaintenanceMode(true);
          if (data.maintenance_reason) {
            setMaintMessage(data.maintenance_reason);
          }
        }
      })
      .catch(() => {});
  }, []);


  const navLinkStyle = ({ isActive }: { isActive: boolean }) => ({
    padding: '0.35rem 0.65rem',
    borderRadius: '6px',
    textDecoration: 'none',
    fontSize: '0.8125rem',
    fontWeight: isActive ? 600 : 500,
    backgroundColor: isActive ? '#0369a1' : 'transparent',
    color: isActive ? '#ffffff' : 'var(--text-secondary)',
    transition: 'all 0.15s ease',
    whiteSpace: 'nowrap' as const,
  });

  return (
    <div style={{ display: 'flex', flexDirection: 'column', minHeight: '100vh' }}>
      <header
        style={{
          borderBottom: '1px solid var(--border-color)',
          padding: '0.75rem 1.5rem',
          display: 'flex',
          flexDirection: 'column',
          gap: '0.6rem',
          backgroundColor: 'var(--bg-secondary)',
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
            <Link to="/" style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', textDecoration: 'none' }}>
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
                }}
              >
                CL
              </div>
              <span style={{ fontSize: '1.25rem', fontWeight: 600, letterSpacing: '-0.02em', color: 'var(--text-primary)' }}>
                CloudLens
              </span>
            </Link>
            <span
              style={{
                fontSize: '0.75rem',
                backgroundColor: '#0369a1',
                color: '#e0f2fe',
                padding: '0.15rem 0.5rem',
                borderRadius: '9999px',
                fontWeight: 600,
              }}
            >
              {health ? `v${health.version}` : 'v0.1.0-alpha'}
            </span>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', fontSize: '0.8125rem' }}>
              <span style={{ color: 'var(--text-secondary)' }}>Tenant Mode:</span>
              <button
                type="button"
                onClick={handleToggleDemo}
                aria-label="Toggle demo mode"
                style={{
                  padding: '0.2rem 0.5rem',
                  borderRadius: '4px',
                  fontSize: '0.75rem',
                  fontWeight: 600,
                  cursor: 'pointer',
                  border: isDemo ? '1px solid #38bdf8' : '1px solid var(--border-color)',
                  backgroundColor: isDemo ? 'rgba(56, 189, 248, 0.2)' : 'var(--bg-primary)',
                  color: isDemo ? '#38bdf8' : 'var(--text-secondary)',
                }}
              >
                {isDemo ? 'Demo Mode (M3)' : 'Live Mode (Empty)'}
              </button>
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', fontSize: '0.8125rem' }}>
              <label htmlFor="user-role-select" style={{ color: 'var(--text-secondary)' }}>
                Role:
              </label>
              <select
                id="user-role-select"
                value={userRole}
                onChange={(e) => handleRoleChange(e.target.value as CanonicalRole)}
                style={{
                  backgroundColor: 'var(--bg-primary)',
                  color: 'var(--text-primary)',
                  border: '1px solid var(--border-color)',
                  borderRadius: '6px',
                  padding: '0.2rem 0.5rem',
                  fontSize: '0.75rem',
                  fontWeight: 600,
                }}
              >
                <option value="SUPER_ADMIN">SUPER_ADMIN</option>
                <option value="PLATFORM_ADMIN">PLATFORM_ADMIN</option>
                <option value="TENANT_ADMIN">TENANT_ADMIN</option>
                <option value="FINOPS_LEAD">FINOPS_LEAD</option>
                <option value="FINOPS_ANALYST">FINOPS_ANALYST</option>
                <option value="ENGINEERING_LEAD">ENGINEERING_LEAD</option>
                <option value="DEVELOPER">DEVELOPER</option>
                <option value="FINANCE_CONTROLLER">FINANCE_CONTROLLER</option>
                <option value="AUDITOR">AUDITOR</option>
              </select>
            </div>

            <div
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '0.35rem',
                fontSize: '0.8125rem',
                padding: '0.2rem 0.6rem',
                borderRadius: '6px',
                backgroundColor: loading ? '#475569' : error ? '#7f1d1d' : '#064e3b',
                color: loading ? '#cbd5e1' : error ? '#fca5a5' : '#6ee7b7',
              }}
            >
              <span
                style={{
                  width: '8px',
                  height: '8px',
                  borderRadius: '50%',
                  backgroundColor: loading ? '#94a3b8' : error ? '#ef4444' : '#10b981',
                }}
              />
              {loading ? 'Probing API...' : error ? 'API Offline' : 'API Healthy'}
            </div>
          </div>
        </div>

        {/* Global Navigation Strip */}
        <nav
          aria-label="Primary Navigation"
          style={{
            display: 'flex',
            gap: '0.3rem',
            overflowX: 'auto',
            paddingBottom: '0.2rem',
          }}
        >
          {/* Platform Control Tower (SUPER_ADMIN / PLATFORM_ADMIN) */}
          {(userRole === 'SUPER_ADMIN' || userRole === 'PLATFORM_ADMIN') && (
            <NavLink
              to="/control-tower"
              style={({ isActive }) => ({
                ...navLinkStyle({ isActive }),
                border: '1px solid #38bdf8',
                backgroundColor: isActive ? '#0369a1' : '#0f172a',
                color: isActive ? '#ffffff' : '#38bdf8',
                fontWeight: 600,
              })}
            >
              Control Tower
            </NavLink>
          )}

          <NavLink to="/executive" style={navLinkStyle}>
            Executive (S-03)
          </NavLink>
          <NavLink to="/providers" style={navLinkStyle}>
            Providers (S-04)
          </NavLink>
          <NavLink to="/services" style={navLinkStyle}>
            Services (S-05)
          </NavLink>
          <NavLink to="/hierarchy" style={navLinkStyle}>
            Hierarchy (S-06)
          </NavLink>
          <NavLink to="/inventory" style={navLinkStyle}>
            Inventory (S-07)
          </NavLink>
          <NavLink to="/resource-detail" style={navLinkStyle}>
            Detail (S-08)
          </NavLink>
          <NavLink to="/usage" style={navLinkStyle}>
            Usage (S-09)
          </NavLink>
          <NavLink to="/runtime" style={navLinkStyle}>
            Runtime (S-10)
          </NavLink>
          <NavLink to="/cost-explorer" style={navLinkStyle}>
            Cost (S-11)
          </NavLink>
          <NavLink to="/investigation" style={navLinkStyle}>
            Increases (S-12)
          </NavLink>
          <NavLink to="/topology" style={navLinkStyle}>
            Topology (S-13)
          </NavLink>
          <NavLink to="/onboarding" style={navLinkStyle}>
            Onboarding (S-14)
          </NavLink>
          <NavLink to="/budgets" style={navLinkStyle}>
            Budgets (S-15)
          </NavLink>
          <NavLink to="/policies" style={navLinkStyle}>
            Policies (S-16)
          </NavLink>
          <NavLink to="/users" style={navLinkStyle}>
            Users (S-17)
          </NavLink>
          <NavLink to="/audit" style={navLinkStyle}>
            Audit (S-18)
          </NavLink>
          <NavLink to="/reports" style={navLinkStyle}>
            Reports (S-19)
          </NavLink>
          <NavLink to="/settings" style={navLinkStyle}>
            Settings (S-20)
          </NavLink>

          {/* Addendum B Screens */}
          <NavLink to="/estimator" style={navLinkStyle}>
            Estimator (S-21)
          </NavLink>
          <NavLink to="/quotas" style={navLinkStyle}>
            Quotas (S-22)
          </NavLink>
          <NavLink to="/provisioning" style={navLinkStyle}>
            Provisioning (S-23)
          </NavLink>
          <NavLink to="/remediation" style={navLinkStyle}>
            Remediation (S-24)
          </NavLink>
          <NavLink to="/statements" style={navLinkStyle}>
            Statements (S-25)
          </NavLink>
          <NavLink to="/planning" style={navLinkStyle}>
            Planning (S-26)
          </NavLink>
          <NavLink to="/commitments" style={navLinkStyle}>
            Commitments (S-27)
          </NavLink>

          <NavLink to="/about" style={navLinkStyle}>
            About (IMP-06)
          </NavLink>

          {/* Development Showcase (Only visible in development) */}
          {isDevelopment && DesignSystemShowcase && (
            <NavLink
              to="/dev"
              style={({ isActive }) => ({
                ...navLinkStyle({ isActive }),
                backgroundColor: isActive ? '#f59e0b' : 'rgba(245, 158, 11, 0.1)',
                color: isActive ? '#ffffff' : '#fbbf24',
              })}
            >
              Dev Showcase
            </NavLink>
          )}
        </nav>
      </header>

      <MaintenanceModeBanner active={isMaintenanceMode} message={maintMessage} />
      <DemoModeBanner isDemo={isDemo} />

      <main style={{ flex: 1, padding: '1.5rem', maxWidth: '1440px', margin: '0 auto', width: '100%' }}>
        <Routes>
          {/* S-01: Login */}
          <Route path="/login" element={<LoginPage />} />

          {/* S-02: Landing */}
          <Route path="/" element={<LandingPage isDemo={isDemo} userRole={userRole} />} />
          <Route path="/landing" element={<LandingPage isDemo={isDemo} userRole={userRole} />} />

          {/* S-03: Executive Summary */}
          <Route path="/executive" element={<ExecutiveDashboard />} />

          {/* S-04: Provider Dashboard */}
          <Route path="/providers" element={<ProviderDashboard />} />
          <Route path="/provider" element={<ProviderDashboard />} />

          {/* S-05: Service Dashboard */}
          <Route path="/services" element={<ServiceDashboard />} />
          <Route path="/service" element={<ServiceDashboard />} />

          {/* S-06: Hierarchy Explorer */}
          <Route path="/hierarchy" element={<HierarchyExplorer />} />

          {/* S-07: Cloud Inventory Explorer */}
          <Route path="/inventory" element={<ServiceInventory />} />

          {/* S-08: Resource Detail 360 */}
          <Route path="/resources/:id" element={<ResourceDetailWrapper />} />
          <Route path="/resource/:id" element={<ResourceDetailWrapper />} />
          <Route path="/resource-detail" element={<ResourceDetailWrapper />} />

          {/* S-09: Usage Telemetry & Cardinality Detail */}
          <Route path="/usage" element={<UsageDetailPage isDemo={isDemo} />} />

          {/* S-10: Resource Runtime & Schedule Adherence */}
          <Route path="/runtime" element={<RuntimeViewPage isDemo={isDemo} />} />

          {/* S-11: Cost Explorer */}
          <Route path="/cost-explorer" element={<CostExplorerPage />} />

          {/* S-12: Investigation View */}
          <Route path="/investigation" element={<InvestigationViewPage />} />

          {/* S-13: Dependency Topology (Lazy Loaded) */}
          <Route
            path="/topology"
            element={
              <Suspense fallback={<div style={{ padding: '2rem' }}>Loading Dependency Graph...</div>}>
                <DependencyGraphPage />
              </Suspense>
            }
          />
          <Route
            path="/graph"
            element={
              <Suspense fallback={<div style={{ padding: '2rem' }}>Loading Dependency Graph...</div>}>
                <DependencyGraphPage />
              </Suspense>
            }
          />

          {/* S-14: Onboarding Wizard */}
          <Route path="/onboarding" element={<OnboardingWizardPage isDemo={isDemo} />} />

          {/* S-15: Budgets & Allocations */}
          <Route path="/budgets" element={<BudgetManagementPage />} />

          {/* S-16: Governance Policies & Compliance */}
          <Route path="/policies" element={<PolicyManagementPage />} />

          {/* S-17: Users & RBAC */}
          <Route
            path="/users"
            element={
              <ProtectedRoute allowedRoles={['SUPER_ADMIN', 'PLATFORM_ADMIN', 'TENANT_ADMIN']} currentRole={userRole}>
                <UsersRbacPage isDemo={isDemo} />
              </ProtectedRoute>
            }
          />

          {/* S-18: Immutable Audit Trail */}
          <Route
            path="/audit"
            element={
              <ProtectedRoute allowedRoles={['SUPER_ADMIN', 'PLATFORM_ADMIN', 'TENANT_ADMIN', 'AUDITOR']} currentRole={userRole}>
                <AuditLogPage isDemo={isDemo} />
              </ProtectedRoute>
            }
          />

          {/* S-19: Standard Reports */}
          <Route path="/reports" element={<ReportsPage isDemo={isDemo} />} />

          {/* S-20: Settings */}
          <Route
            path="/settings"
            element={
              <ProtectedRoute allowedRoles={['SUPER_ADMIN', 'PLATFORM_ADMIN', 'TENANT_ADMIN']} currentRole={userRole}>
                <SettingsPage isDemo={isDemo} />
              </ProtectedRoute>
            }
          />

          {/* S-21: Cost Estimator + Scenario Compare */}
          <Route path="/estimator" element={<CostEstimatorPage isDemo={isDemo} />} />

          {/* S-22: Quota & Headroom Console */}
          <Route path="/quotas" element={<QuotaHeadroomPage isDemo={isDemo} />} />

          {/* S-23: Provisioning Requests + Approvals */}
          <Route path="/provisioning" element={<ProvisioningRequestsPage isDemo={isDemo} />} />

          {/* S-24: Remediation Task Board */}
          <Route path="/remediation" element={<RemediationBoardPage isDemo={isDemo} />} />

          {/* S-25: Showback Statements + Disputes */}
          <Route path="/statements" element={<ShowbackStatementsPage isDemo={isDemo} />} />

          {/* S-26: Budget Planning Workspace */}
          <Route path="/planning" element={<BudgetPlanningPage isDemo={isDemo} />} />

          {/* S-27: Commitment Portfolio + Renewals */}
          <Route path="/commitments" element={<CommitmentRenewalsPage isDemo={isDemo} />} />

          {/* Control Tower Route (Guarded for SUPER_ADMIN / PLATFORM_ADMIN) */}
          <Route
            path="/control-tower"
            element={
              <ProtectedRoute allowedRoles={['SUPER_ADMIN', 'PLATFORM_ADMIN']} currentRole={userRole}>
                <ControlTowerPage />
              </ProtectedRoute>
            }
          />

          {/* Auxiliary Routes */}
          <Route path="/connectors" element={<ConnectorManagementPage />} />
          <Route path="/admin" element={<AdminConsolePage userRole={userRole as any} onNavigateHome={() => {}} />} />
          <Route path="/masterdata" element={<MasterDataConsole />} />
          <Route path="/explanation" element={<ExplanationLayerView />} />
          <Route path="/about" element={<AboutPage />} />

          {/* Development Showcase (Omitted from production builds) */}
          {isDevelopment && DesignSystemShowcase && (
            <Route
              path="/dev"
              element={
                <Suspense fallback={<div style={{ padding: '2rem' }}>Loading Design System Showcase...</div>}>
                  <DesignSystemShowcase />
                </Suspense>
              }
            />
          )}

          {/* Error & Fallback Routes */}
          <Route path="/403" element={<ForbiddenPage />} />
          <Route path="/404" element={<NotFoundPage />} />
          <Route path="*" element={<NotFoundPage />} />
        </Routes>
      </main>

      <footer
        style={{
          borderTop: '1px solid var(--border-color)',
          padding: '1rem 2rem',
          textAlign: 'center',
          fontSize: '0.8125rem',
          color: 'var(--text-secondary)',
        }}
      >
        CloudLens Platform &copy; 2026. Enterprise Production Standard.
      </footer>
    </div>
  );
};

export const App: React.FC = () => {
  return (
    <BrowserRouter>
      <AppLayout />
    </BrowserRouter>
  );
};

export default App;
