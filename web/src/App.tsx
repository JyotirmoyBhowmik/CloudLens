import React, { useEffect, useState, Suspense, lazy } from 'react';
import { AuthProvider, useAuth } from './context/AuthContext';
import {
  BrowserRouter,
  Routes,
  Route,
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

// Advanced FinOps & Governance Screens
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
import { TenantsPage } from './pages/TenantsPage';
import { SetupWizardPage } from './pages/SetupWizardPage';
import { ForbiddenPage } from './pages/ForbiddenPage';
import { NotFoundPage } from './pages/NotFoundPage';
import { AboutPage } from './pages/AboutPage';
import { DemoModeBanner } from './components/DemoModeBanner';
import { MaintenanceModeBanner } from './components/MaintenanceModeBanner';
import { TopBar } from './components/TopBar';
import { Sidebar } from './components/Sidebar';

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

interface HealthStatus {
  status: string;
  service: string;
  version: string;
  timestamp: string;
  correlation_id: string;
}

// Capability-Driven Route Authorization Guard
interface ProtectedRouteProps {
  requiredCapability?: string;
  requiredCapabilities?: string[];
  children: React.ReactNode;
}

const ProtectedRoute: React.FC<ProtectedRouteProps> = ({
  requiredCapability,
  requiredCapabilities,
  children,
}) => {
  const { hasCapability, isLoading, isAuthenticated } = useAuth();

  if (isLoading) {
    return <div style={{ padding: '2rem', color: 'var(--text-secondary)' }}>Verifying authorization...</div>;
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  if (requiredCapability && !hasCapability(requiredCapability)) {
    return <Navigate to="/403" replace />;
  }

  if (requiredCapabilities && !requiredCapabilities.some((cap) => hasCapability(cap))) {
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
  const auth = useAuth();
  const navigate = useNavigate();
  const [health, setHealth] = useState<HealthStatus | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [isDemo] = useState<boolean>(true);

  const [isMaintenanceMode, setIsMaintenanceMode] = useState<boolean>(false);
  const [maintMessage, setMaintMessage] = useState<string>('CloudLens is currently undergoing scheduled platform maintenance. Mutating operations are paused.');

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

    // Check maintenance mode
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


  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState<boolean>(() => {
    try {
      return localStorage.getItem('cloudlens_sidebar_collapsed') === 'true';
    } catch {
      return false;
    }
  });

  const [mobileDrawerOpen, setMobileDrawerOpen] = useState<boolean>(false);

  const toggleSidebarCollapse = () => {
    setIsSidebarCollapsed((prev) => {
      const next = !prev;
      try {
        localStorage.setItem('cloudlens_sidebar_collapsed', String(next));
      } catch {}
      return next;
    });
  };

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        minHeight: '100vh',
        width: '100%',
        boxSizing: 'border-box',
        overflowX: 'hidden',
      }}
    >
      <TopBar
        onToggleMobileMenu={() => setMobileDrawerOpen((prev) => !prev)}
        health={health}
        loadingHealth={loading}
        errorHealth={error}
      />

      <MaintenanceModeBanner active={isMaintenanceMode} message={maintMessage} />
      <DemoModeBanner isDemo={isDemo} />

      {auth.isAuthenticated &&
        (auth.hasRole('SUPER_ADMIN') || auth.roles.includes('SUPER_ADMIN')) &&
        (auth.tenants.length === 0 || (auth.tenants.length === 1 && auth.tenants[0].id === 'tenant-system')) && (
          <div
            data-testid="first-run-banner"
            style={{
              backgroundColor: '#eff6ff',
              borderBottom: '1px solid #bfdbfe',
              color: '#1e40af',
              padding: '0.625rem 1.25rem',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              fontSize: '0.875rem',
              fontWeight: 500,
            }}
          >
            <span>
              First-Run Setup Required: Super Administrator detected with no organizational tenants configured. Complete setup to initialize your environment.
            </span>
            <button
              id="first-run-setup-btn"
              onClick={() => navigate('/setup')}
              style={{
                padding: '0.25rem 0.75rem',
                borderRadius: '0.25rem',
                backgroundColor: '#2563eb',
                color: '#ffffff',
                border: 'none',
                cursor: 'pointer',
                fontWeight: 600,
              }}
            >
              Start Setup
            </button>
          </div>
        )}

      <div
        style={{
          display: 'flex',
          flex: 1,
          minHeight: 0,
          width: '100%',
          minWidth: 0,
          boxSizing: 'border-box',
        }}
      >
        <Sidebar
          collapsed={isSidebarCollapsed}
          onToggleCollapse={toggleSidebarCollapse}
          mobileOpen={mobileDrawerOpen}
          onCloseMobile={() => setMobileDrawerOpen(false)}
        />

        <main
          style={{
            flex: 1,
            minWidth: 0,
            padding: '1.5rem',
            width: '100%',
            boxSizing: 'border-box',
            overflowY: 'auto',
          }}
        >
          <Routes>
            {/* Login */}
            <Route path="/login" element={<LoginPage />} />

            {/* Landing */}
            <Route path="/" element={<LandingPage isDemo={isDemo} />} />
            <Route path="/landing" element={<LandingPage isDemo={isDemo} />} />

            {/* Executive Summary */}
            <Route path="/executive" element={<ExecutiveDashboard />} />

            {/* Provider Dashboard */}
            <Route path="/providers" element={<ProviderDashboard />} />
            <Route path="/provider" element={<ProviderDashboard />} />

            {/* Service Dashboard */}
            <Route path="/services" element={<ServiceDashboard />} />
            <Route path="/service" element={<ServiceDashboard />} />

            {/* Hierarchy Explorer */}
            <Route path="/hierarchy" element={<HierarchyExplorer />} />

            {/* Cloud Inventory Explorer */}
            <Route path="/inventory" element={<ServiceInventory />} />

            {/* Resource Detail 360 */}
            <Route path="/resources/:id" element={<ResourceDetailWrapper />} />
            <Route path="/resource/:id" element={<ResourceDetailWrapper />} />
            <Route path="/resource-detail" element={<ResourceDetailWrapper />} />

            {/* Usage Telemetry & Cardinality Detail */}
            <Route path="/usage" element={<UsageDetailPage isDemo={isDemo} />} />

            {/* Resource Runtime & Schedule Adherence */}
            <Route path="/runtime" element={<RuntimeViewPage isDemo={isDemo} />} />

            {/* Cost Explorer */}
            <Route path="/cost-explorer" element={<CostExplorerPage />} />

            {/* Investigation View */}
            <Route path="/investigation" element={<InvestigationViewPage />} />

            {/* Dependency Topology (Lazy Loaded) */}
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

            {/* Onboarding Wizard */}
            <Route path="/onboarding" element={<OnboardingWizardPage isDemo={isDemo} />} />

            {/* Budgets & Allocations */}
            <Route path="/budgets" element={<BudgetManagementPage />} />

            {/* Governance Policies & Compliance */}
            <Route path="/policies" element={<PolicyManagementPage />} />

            {/* Users & RBAC */}
            <Route
              path="/users"
              element={
                <ProtectedRoute requiredCapability="iam:manage">
                  <UsersRbacPage isDemo={isDemo} />
                </ProtectedRoute>
              }
            />

            {/* Immutable Audit Trail */}
            <Route
              path="/audit"
              element={
                <ProtectedRoute requiredCapability="audit:read">
                  <AuditLogPage isDemo={isDemo} />
                </ProtectedRoute>
              }
            />

            {/* Standard Reports */}
            <Route path="/reports" element={<ReportsPage isDemo={isDemo} />} />

            {/* Settings */}
            <Route
              path="/settings"
              element={
                <ProtectedRoute requiredCapability="tenants:settings:read">
                  <SettingsPage isDemo={isDemo} />
                </ProtectedRoute>
              }
            />

            {/* Tenants Administration */}
            <Route
              path="/tenants"
              element={
                <ProtectedRoute requiredCapability="tenants:settings:read">
                  <TenantsPage isDemo={isDemo} />
                </ProtectedRoute>
              }
            />

            {/* First-Run Setup Wizard */}
            <Route
              path="/setup"
              element={
                <ProtectedRoute requiredCapability="admin:access">
                  <SetupWizardPage isDemo={isDemo} />
                </ProtectedRoute>
              }
            />

            {/* Cost Estimator + Scenario Compare */}
            <Route path="/estimator" element={<CostEstimatorPage isDemo={isDemo} />} />

            {/* Quota & Headroom Console */}
            <Route path="/quotas" element={<QuotaHeadroomPage isDemo={isDemo} />} />

            {/* Provisioning Requests + Approvals */}
            <Route path="/provisioning" element={<ProvisioningRequestsPage isDemo={isDemo} />} />

            {/* Remediation Task Board */}
            <Route path="/remediation" element={<RemediationBoardPage isDemo={isDemo} />} />

            {/* Showback Statements + Disputes */}
            <Route path="/statements" element={<ShowbackStatementsPage isDemo={isDemo} />} />
            <Route path="/reconciliation" element={<ShowbackStatementsPage isDemo={isDemo} />} />

            {/* Budget Planning Workspace */}
            <Route path="/planning" element={<BudgetPlanningPage isDemo={isDemo} />} />

            {/* Commitment Portfolio + Renewals */}
            <Route path="/commitments" element={<CommitmentRenewalsPage isDemo={isDemo} />} />

            {/* Control Tower Route (Guarded for platform.observe) */}
            <Route
              path="/control-tower"
              element={
                <ProtectedRoute requiredCapability="platform.observe">
                  <ControlTowerPage />
                </ProtectedRoute>
              }
            />

            {/* Auxiliary Routes */}
            <Route path="/connectors" element={<ConnectorManagementPage />} />
            <Route
              path="/admin"
              element={
                <ProtectedRoute requiredCapability="admin:access">
                  <AdminConsolePage onNavigateHome={() => {}} />
                </ProtectedRoute>
              }
            />
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
      </div>

      <footer
        style={{
          borderTop: '1px solid var(--border-color)',
          padding: '1rem 2rem',
          textAlign: 'center',
          fontSize: '0.8125rem',
          color: 'var(--text-secondary)',
          backgroundColor: 'var(--bg-secondary)',
        }}
      >
        CloudLens Platform &copy; 2026.
      </footer>
    </div>
  );
};

export const App: React.FC = () => {
  return (
    <BrowserRouter>
      <AuthProvider>
        <AppLayout />
      </AuthProvider>
    </BrowserRouter>
  );
};

export default App;
