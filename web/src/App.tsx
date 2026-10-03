import React, { useEffect, useState } from 'react';
import { MasterDataConsole } from './pages/MasterDataConsole';
import { DesignSystemShowcase } from './pages/DesignSystemShowcase';
import { ExecutiveDashboard } from './pages/ExecutiveDashboard';
import { ProviderDashboard } from './pages/ProviderDashboard';
import { ServiceDashboard } from './pages/ServiceDashboard';
import { HierarchyExplorer } from './pages/HierarchyExplorer';
import { ServiceInventory } from './pages/ServiceInventory';
import { ResourceDetailPage } from './pages/ResourceDetailPage';
import { CostExplorerPage } from './pages/CostExplorerPage';
import { InvestigationViewPage } from './pages/InvestigationViewPage';
import { ExplanationLayerView } from './pages/ExplanationLayerView';
import { DependencyGraphPage } from './pages/DependencyGraphPage';
import { BudgetManagementPage } from './pages/BudgetManagementPage';
import { PolicyManagementPage } from './pages/PolicyManagementPage';
import { ConnectorManagementPage } from './pages/ConnectorManagementPage';
import { AdminConsolePage } from './pages/AdminConsolePage';

interface HealthStatus {
  status: string;
  service: string;
  version: string;
  timestamp: string;
  correlation_id: string;
}

export const App: React.FC = () => {
  const [health, setHealth] = useState<HealthStatus | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [currentView, setCurrentView] = useState<
    | 'overview'
    | 'executive'
    | 'provider'
    | 'service'
    | 'hierarchy'
    | 'inventory'
    | 'resource-detail'
    | 'cost-explorer'
    | 'investigation'
    | 'topology'
    | 'budgets'
    | 'policies'
    | 'connectors'
    | 'admin'
    | 'masterdata'
    | 'design-system'
    | 'explanation'
  >('executive');
  const [userRole, setUserRole] = useState<'EXECUTIVE' | 'FINOPS' | 'ENGINEERING' | 'TENANT_ADMIN'>('TENANT_ADMIN');
  const [activeResourceId, setActiveResourceId] = useState<string>('res-aws-vm-01');
  const [explorerDimension, setExplorerDimension] = useState<string>('SERVICE');
  const [explorerGroupId, setExplorerGroupId] = useState<string | undefined>(undefined);
  const [investigationEntityId, setInvestigationEntityId] = useState<string>('res-aws-rds-01');

  useEffect(() => {
    fetch('/api/v1/health')
      .then((res) => {
        if (!res.ok) {
          throw new Error(`HTTP error ${res.status}`);
        }
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

    // Resolve Role-based Default Landing (FR-503)
    fetch('/api/v1/dashboards/landing?role=EXECUTIVE')
      .then((res) => res.json())
      .then((landing) => {
        if (landing && landing.default_dashboard) {
          const map: Record<string, 'executive' | 'provider' | 'service'> = {
            EXECUTIVE: 'executive',
            PROVIDER: 'provider',
            SERVICE: 'service',
          };
          if (map[landing.default_dashboard]) {
            setCurrentView(map[landing.default_dashboard]);
          }
        }
      })
      .catch(() => {});
  }, []);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', minHeight: '100vh' }}>
      <header
        style={{
          borderBottom: '1px solid var(--border-color)',
          padding: '1rem 2rem',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          backgroundColor: 'var(--bg-secondary)',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
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
          <span style={{ fontSize: '1.25rem', fontWeight: 600, letterSpacing: '-0.02em' }}>
            CloudLens
          </span>
          <span
            style={{
              fontSize: '0.75rem',
              backgroundColor: '#0369a1',
              color: '#e0f2fe',
              padding: '0.15rem 0.5rem',
              borderRadius: '9999px',
            }}
          >
            v0.1.0-alpha
          </span>
        </div>
        <nav style={{ display: 'flex', gap: '0.4rem', flexWrap: 'wrap' }}>
          <button
            onClick={() => setCurrentView('executive')}
            style={{
              padding: '0.4rem 0.8rem',
              borderRadius: '6px',
              border: 'none',
              backgroundColor: currentView === 'executive' ? '#0284c7' : 'transparent',
              color: currentView === 'executive' ? '#ffffff' : 'var(--text-secondary)',
              cursor: 'pointer',
              fontWeight: 500,
              fontSize: '0.875rem',
            }}
          >
            Executive
          </button>
          <button
            onClick={() => setCurrentView('provider')}
            style={{
              padding: '0.4rem 0.8rem',
              borderRadius: '6px',
              border: 'none',
              backgroundColor: currentView === 'provider' ? '#0284c7' : 'transparent',
              color: currentView === 'provider' ? '#ffffff' : 'var(--text-secondary)',
              cursor: 'pointer',
              fontWeight: 500,
              fontSize: '0.875rem',
            }}
          >
            Providers
          </button>
          <button
            onClick={() => setCurrentView('service')}
            style={{
              padding: '0.4rem 0.8rem',
              borderRadius: '6px',
              border: 'none',
              backgroundColor: currentView === 'service' ? '#0284c7' : 'transparent',
              color: currentView === 'service' ? '#ffffff' : 'var(--text-secondary)',
              cursor: 'pointer',
              fontWeight: 500,
              fontSize: '0.875rem',
            }}
          >
            Services
          </button>
          <button
            onClick={() => setCurrentView('hierarchy')}
            style={{
              padding: '0.4rem 0.8rem',
              borderRadius: '6px',
              border: 'none',
              backgroundColor: currentView === 'hierarchy' ? '#0284c7' : 'transparent',
              color: currentView === 'hierarchy' ? '#ffffff' : 'var(--text-secondary)',
              cursor: 'pointer',
              fontWeight: 500,
              fontSize: '0.875rem',
            }}
          >
            Hierarchy
          </button>
          <button
            onClick={() => setCurrentView('inventory')}
            style={{
              padding: '0.4rem 0.8rem',
              borderRadius: '6px',
              border: 'none',
              backgroundColor: currentView === 'inventory' ? '#0284c7' : 'transparent',
              color: currentView === 'inventory' ? '#ffffff' : 'var(--text-secondary)',
              cursor: 'pointer',
              fontWeight: 500,
              fontSize: '0.875rem',
            }}
          >
            Inventory
          </button>
          <button
            onClick={() => setCurrentView('resource-detail')}
            style={{
              padding: '0.4rem 0.8rem',
              borderRadius: '6px',
              border: 'none',
              backgroundColor: currentView === 'resource-detail' ? '#0284c7' : 'transparent',
              color: currentView === 'resource-detail' ? '#ffffff' : 'var(--text-secondary)',
              cursor: 'pointer',
              fontWeight: 500,
              fontSize: '0.875rem',
            }}
          >
            Resource Detail
          </button>
          <button
            onClick={() => setCurrentView('cost-explorer')}
            style={{
              padding: '0.4rem 0.8rem',
              borderRadius: '6px',
              border: 'none',
              backgroundColor: currentView === 'cost-explorer' ? '#0284c7' : 'transparent',
              color: currentView === 'cost-explorer' ? '#ffffff' : 'var(--text-secondary)',
              cursor: 'pointer',
              fontWeight: 500,
              fontSize: '0.875rem',
            }}
          >
            Cost Explorer
          </button>
          <button
            onClick={() => setCurrentView('investigation')}
            style={{
              padding: '0.4rem 0.8rem',
              borderRadius: '6px',
              border: 'none',
              backgroundColor: currentView === 'investigation' ? '#0284c7' : 'transparent',
              color: currentView === 'investigation' ? '#ffffff' : 'var(--text-secondary)',
              cursor: 'pointer',
              fontWeight: 500,
              fontSize: '0.875rem',
            }}
          >
            Increases
          </button>
          <button
            onClick={() => setCurrentView('topology')}
            style={{
              padding: '0.4rem 0.8rem',
              borderRadius: '6px',
              border: 'none',
              backgroundColor: currentView === 'topology' ? '#0284c7' : 'transparent',
              color: currentView === 'topology' ? '#ffffff' : 'var(--text-secondary)',
              cursor: 'pointer',
              fontWeight: 500,
              fontSize: '0.875rem',
            }}
          >
            Topology
          </button>
          <button
            onClick={() => setCurrentView('budgets')}
            style={{
              padding: '0.4rem 0.8rem',
              borderRadius: '6px',
              border: 'none',
              backgroundColor: currentView === 'budgets' ? '#0284c7' : 'transparent',
              color: currentView === 'budgets' ? '#ffffff' : 'var(--text-secondary)',
              cursor: 'pointer',
              fontWeight: 500,
              fontSize: '0.875rem',
            }}
          >
            Budgets
          </button>
          <button
            onClick={() => setCurrentView('policies')}
            style={{
              padding: '0.4rem 0.8rem',
              borderRadius: '6px',
              border: 'none',
              backgroundColor: currentView === 'policies' ? '#0284c7' : 'transparent',
              color: currentView === 'policies' ? '#ffffff' : 'var(--text-secondary)',
              cursor: 'pointer',
              fontWeight: 500,
              fontSize: '0.875rem',
            }}
          >
            Policies
          </button>
          <button
            onClick={() => setCurrentView('connectors')}
            style={{
              padding: '0.4rem 0.8rem',
              borderRadius: '6px',
              border: 'none',
              backgroundColor: currentView === 'connectors' ? '#0284c7' : 'transparent',
              color: currentView === 'connectors' ? '#ffffff' : 'var(--text-secondary)',
              cursor: 'pointer',
              fontWeight: 500,
              fontSize: '0.875rem',
            }}
          >
            Connectors
          </button>
          {userRole === 'TENANT_ADMIN' && (
            <button
              onClick={() => setCurrentView('admin')}
              style={{
                padding: '0.4rem 0.8rem',
                borderRadius: '6px',
                border: 'none',
                backgroundColor: currentView === 'admin' ? '#ef4444' : '#450a0a',
                color: currentView === 'admin' ? '#ffffff' : '#fca5a5',
                cursor: 'pointer',
                fontWeight: 600,
                fontSize: '0.875rem',
              }}
            >
              Admin Console
            </button>
          )}
          <button
            onClick={() => setCurrentView('overview')}
            style={{
              padding: '0.4rem 0.8rem',
              borderRadius: '6px',
              border: 'none',
              backgroundColor: currentView === 'overview' ? '#0284c7' : 'transparent',
              color: currentView === 'overview' ? '#ffffff' : 'var(--text-secondary)',
              cursor: 'pointer',
              fontWeight: 500,
              fontSize: '0.875rem',
            }}
          >
            Overview
          </button>
          <button
            onClick={() => setCurrentView('design-system')}
            style={{
              padding: '0.4rem 0.8rem',
              borderRadius: '6px',
              border: 'none',
              backgroundColor: currentView === 'design-system' ? '#0284c7' : 'transparent',
              color: currentView === 'design-system' ? '#ffffff' : 'var(--text-secondary)',
              cursor: 'pointer',
              fontWeight: 500,
              fontSize: '0.875rem',
            }}
          >
            Design System
          </button>
          <button
            onClick={() => setCurrentView('explanation')}
            style={{
              padding: '0.4rem 0.8rem',
              borderRadius: '6px',
              border: 'none',
              backgroundColor: currentView === 'explanation' ? '#0284c7' : 'transparent',
              color: currentView === 'explanation' ? '#ffffff' : 'var(--text-secondary)',
              cursor: 'pointer',
              fontWeight: 500,
              fontSize: '0.875rem',
            }}
          >
            Explanation Layer
          </button>
          <button
            onClick={() => setCurrentView('masterdata')}
            style={{
              padding: '0.4rem 0.8rem',
              borderRadius: '6px',
              border: 'none',
              backgroundColor: currentView === 'masterdata' ? '#0284c7' : 'transparent',
              color: currentView === 'masterdata' ? '#ffffff' : 'var(--text-secondary)',
              cursor: 'pointer',
              fontWeight: 500,
              fontSize: '0.875rem',
            }}
          >
            Master Data
          </button>
        </nav>
        <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', fontSize: '0.8125rem' }}>
            <span style={{ color: 'var(--text-secondary)' }}>Role:</span>
            <select
              value={userRole}
              onChange={(e) => setUserRole(e.target.value as any)}
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
              <option value="EXECUTIVE">EXECUTIVE</option>
              <option value="FINOPS">FINOPS</option>
              <option value="ENGINEERING">ENGINEERING</option>
              <option value="TENANT_ADMIN">TENANT_ADMIN</option>
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
      </header>

      <main style={{ flex: 1, padding: currentView === 'overview' ? '2.5rem' : '1.5rem', maxWidth: '1400px', margin: '0 auto', width: '100%' }}>
        {currentView === 'executive' ? (
          <ExecutiveDashboard />
        ) : currentView === 'provider' ? (
          <ProviderDashboard />
        ) : currentView === 'service' ? (
          <ServiceDashboard />
        ) : currentView === 'hierarchy' ? (
          <HierarchyExplorer />
        ) : currentView === 'inventory' ? (
          <ServiceInventory />
        ) : currentView === 'resource-detail' ? (
          <ResourceDetailPage
            initialResourceId={activeResourceId}
            onNavigateToCostExplorer={(dim, gId) => {
              if (dim) setExplorerDimension(dim);
              setExplorerGroupId(gId);
              setCurrentView('cost-explorer');
            }}
            onNavigateToInvestigation={(entId) => {
              setInvestigationEntityId(entId);
              setCurrentView('investigation');
            }}
          />
        ) : currentView === 'cost-explorer' ? (
          <CostExplorerPage
            initialDimension={explorerDimension}
            initialGroupId={explorerGroupId}
            onNavigateToResourceDetail={(resId) => {
              setActiveResourceId(resId);
              setCurrentView('resource-detail');
            }}
          />
        ) : currentView === 'investigation' ? (
          <InvestigationViewPage
            initialEntityId={investigationEntityId}
            onNavigateToResourceDetail={(resId) => {
              setActiveResourceId(resId);
              setCurrentView('resource-detail');
            }}
          />
        ) : currentView === 'topology' ? (
          <DependencyGraphPage />
        ) : currentView === 'budgets' ? (
          <BudgetManagementPage />
        ) : currentView === 'policies' ? (
          <PolicyManagementPage />
        ) : currentView === 'connectors' ? (
          <ConnectorManagementPage />
        ) : currentView === 'admin' ? (
          <AdminConsolePage
            userRole={userRole}
            onNavigateHome={() => setCurrentView('executive')}
          />
        ) : currentView === 'design-system' ? (
          <DesignSystemShowcase />
        ) : currentView === 'explanation' ? (
          <ExplanationLayerView />
        ) : currentView === 'masterdata' ? (
          <MasterDataConsole />
        ) : (
          <>
            <div style={{ marginBottom: '2rem' }}>
              <h1 style={{ fontSize: '2rem', fontWeight: 700, margin: '0 0 0.5rem 0' }}>
                Multi-Cloud Governance & FinOps Platform
              </h1>
              <p style={{ color: 'var(--text-secondary)', fontSize: '1rem', margin: 0 }}>
                Unified governance, service inventory, pricing catalog, and cost management across Azure, AWS, GCP, and OCI.
              </p>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '1.5rem', marginBottom: '2.5rem' }}>
              <div style={{ backgroundColor: 'var(--bg-secondary)', border: '1px solid var(--border-color)', borderRadius: '10px', padding: '1.5rem' }}>
                <h3 style={{ margin: '0 0 0.5rem 0', color: '#38bdf8' }}>Architecture Layers</h3>
                <p style={{ fontSize: '0.875rem', color: 'var(--text-secondary)', margin: 0 }}>
                  Strict layering: presentation → application → domain → normalisation → ingestion → connector → provider.
                </p>
              </div>
              <div style={{ backgroundColor: 'var(--bg-secondary)', border: '1px solid var(--border-color)', borderRadius: '10px', padding: '1.5rem' }}>
                <h3 style={{ margin: '0 0 0.5rem 0', color: '#34d399' }}>Requirement Register</h3>
                <p style={{ fontSize: '0.875rem', color: 'var(--text-secondary)', margin: 0 }}>
                  458 verified requirements across all 13 prefixes (BR, FR, PR, CST, USE, RUN, DEP, CON, API, SEC, NFR, DR, AC).
                </p>
              </div>
              <div style={{ backgroundColor: 'var(--bg-secondary)', border: '1px solid var(--border-color)', borderRadius: '10px', padding: '1.5rem' }}>
                <h3 style={{ margin: '0 0 0.5rem 0', color: '#fbbf24' }}>Pricing Dimensions</h3>
                <p style={{ fontSize: '0.875rem', color: 'var(--text-secondary)', margin: 0 }}>
                  29 reconciled dimensions and qualifiers (D-06 closed) across consumption units, structural models, and modifiers.
                </p>
              </div>
            </div>

            <div style={{ backgroundColor: 'var(--bg-secondary)', border: '1px solid var(--border-color)', borderRadius: '10px', padding: '1.5rem' }}>
              <h2 style={{ fontSize: '1.125rem', fontWeight: 600, margin: '0 0 1rem 0' }}>API Connection Telemetry</h2>
              {loading ? (
                <p style={{ color: 'var(--text-secondary)' }}>Connecting to local API daemon...</p>
              ) : error ? (
                <div style={{ padding: '1rem', backgroundColor: '#450a0a', border: '1px solid #7f1d1d', borderRadius: '6px' }}>
                  <strong style={{ color: '#fca5a5' }}>Connection status:</strong> {error}
                  <div style={{ fontSize: '0.8125rem', color: '#f87171', marginTop: '0.5rem' }}>
                    Ensure the FastAPI backend is running via <code>python -m uvicorn api.cloudlens_api.main:app --port 8000</code> or <code>pnpm bootstrap</code>.
                  </div>
                </div>
              ) : (
                <pre style={{ backgroundColor: '#0f172a', padding: '1rem', borderRadius: '6px', overflowX: 'auto', fontSize: '0.875rem', color: '#38bdf8' }}>
                  {JSON.stringify(health, null, 2)}
                </pre>
              )}
            </div>
          </>
        )}
      </main>

      <footer style={{ borderTop: '1px solid var(--border-color)', padding: '1rem 2rem', textAlign: 'center', fontSize: '0.8125rem', color: 'var(--text-secondary)' }}>
        CloudLens Platform &copy; 2026. Enterprise Production Standard.
      </footer>
    </div>
  );
};

export default App;
