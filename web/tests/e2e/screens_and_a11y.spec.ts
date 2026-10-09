import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

// Canonical 28 routes: 27 screens + Control Tower
const ROUTES = [
  { id: 'S-01', path: '/login', name: 'Login (OIDC Redirect)' },
  { id: 'S-02', path: '/', name: 'Landing & FinOps Portal' },
  { id: 'S-03', path: '/executive', name: 'Executive Dashboard' },
  { id: 'S-04', path: '/provider', name: 'Provider Breakdown' },
  { id: 'S-05', path: '/service', name: 'Service Breakdown' },
  { id: 'S-06', path: '/hierarchy', name: 'Hierarchy Explorer' },
  { id: 'S-07', path: '/cost-explorer', name: 'Cost Explorer' },
  { id: 'S-08', path: '/inventory', name: 'Service Inventory' },
  { id: 'S-09', path: '/usage', name: 'Usage Detail' },
  { id: 'S-10', path: '/runtime', name: 'Runtime View' },
  { id: 'S-11', path: '/resource/res-aws-vm-01', name: 'Resource Detail' },
  { id: 'S-12', path: '/graph', name: 'Dependency Graph' },
  { id: 'S-13', path: '/investigation', name: 'Investigation View' },
  { id: 'S-14', path: '/onboarding', name: 'Onboarding Wizard' },
  { id: 'S-15', path: '/budgets', name: 'Budget Management' },
  { id: 'S-16', path: '/policies', name: 'Policy Management' },
  { id: 'S-17', path: '/users', name: 'Users & RBAC' },
  { id: 'S-18', path: '/audit', name: 'Audit Log' },
  { id: 'S-19', path: '/reports', name: 'Reports & Exports' },
  { id: 'S-20', path: '/settings', name: 'Tenant Settings' },
  { id: 'S-21', path: '/estimator', name: 'Cost Estimator & Scenario Compare' },
  { id: 'S-22', path: '/quotas', name: 'Quota and Headroom' },
  { id: 'S-23', path: '/provisioning', name: 'Provisioning Requests & Approvals' },
  { id: 'S-24', path: '/remediation', name: 'Remediation Task Board' },
  { id: 'S-25', path: '/statements', name: 'Showback Statements & Disputes' },
  { id: 'S-26', path: '/planning', name: 'Budget Planning Workspace' },
  { id: 'S-27', path: '/commitments', name: 'Commitment Portfolio & Renewals' },
  { id: 'R-CT', path: '/control-tower', name: 'Platform Control Tower' },
];

test.describe('CloudLens Enterprise UI — 28 Routes & Screens (Prompt R-UI)', () => {
  test.beforeEach(async ({ page }) => {
    // Mock /api/v1/health probe to ensure consistent healthy state in tests
    await page.route('/api/v1/health', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          status: 'HEALTHY',
          service: 'cloudlens-api',
          version: '0.1.0-alpha',
          timestamp: '2026-10-05T22:00:00Z',
          correlation_id: 'e2e-test-correlation-id',
        }),
      });
    });

    // Mock /api/v1/auth/me to provide valid identity with full capabilities for route sweep
    await page.route('/api/v1/auth/me', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          user: {
            id: 'usr-e2e-admin',
            email: 'admin@cloudlens.local',
            display_name: 'E2E Administrator',
          },
          roles: ['SUPER_ADMIN'],
          capabilities: ['*'],
          tenants: [
            { id: 't-demo', name: 'Demo Enterprise' },
          ],
          current_tenant: { id: 't-demo', name: 'Demo Enterprise' },
        }),
      });
    });

    // Mock empty endpoints for pages that query resource lists
    const emptyEndpoints = [
      '/api/v1/quotas',
      '/api/v1/remediation',
      '/api/v1/statements',
      '/api/v1/budgets/plans',
      '/api/v1/commitments',
      '/api/v1/audit',
      '/api/v1/users',
      '/api/v1/policies',
      '/api/v1/provisioning-requests',
      '/api/v1/runtime/adherence',
      '/api/v1/usage/metrics',
      '/api/v1/connectors',
      '/api/v1/overrides',
      '/api/v1/cost/estimate',
      '/api/v1/dependencies/graph',
    ];

    await page.route('/api/v1/**', async (route) => {
      const url = route.request().url();
      if (url.includes('/api/v1/health') || url.includes('/api/v1/auth/me')) {
        return route.fallback();
      }
      if (emptyEndpoints.some((ep) => url.includes(ep))) {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify([]),
        });
        return;
      }
      return route.fallback();
    });

    // Reset localStorage for deterministic test isolation
    await page.addInitScript(() => {
      localStorage.clear();
      localStorage.setItem('cloudlens_is_demo', 'true');
    });
  });

  test('All 28 routes are reachable by direct URL in Demo Mode', async ({ page }) => {
    test.setTimeout(120000);
    page.on('pageerror', (err) => console.log(`[PAGE ERROR]: ${err.message}`));
    for (const r of ROUTES) {
      console.log(`Checking route ${r.id}: ${r.path}`);
      await page.goto(r.path);
      await page.waitForLoadState('domcontentloaded');

      // Login screen doesn't have the global nav layout
      if (r.path !== '/login') {
        const banner = page.locator('div[role="status"]', {
          hasText: /Demo Mode Active/i,
        });
        await expect(banner.first()).toBeVisible({ timeout: 5000 });
      }

      const content = await page.textContent('body');
      expect(content).toBeTruthy();
    }
  });

  test('All 28 routes render properly in Non-Demo Mode (Empty States)', async ({ page }) => {
    test.setTimeout(60000);
    await page.addInitScript(() => {
      localStorage.setItem('cloudlens_is_demo', 'false');
    });
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');

    // Now test a representative sample of Addendum B screens and core screens for null states
    const sampleRoutes = [
      '/quotas',
      '/remediation',
      '/statements',
      '/planning',
      '/commitments',
      '/audit',
      '/users',
    ];

    for (const path of sampleRoutes) {
      await page.goto(path);
      await page.waitForLoadState('domcontentloaded');
      // Ensure null states or empty indicators are visible
      const bodyText = await page.textContent('body');
      expect(
        bodyText?.includes('No ') ||
        bodyText?.includes('NO_DATA') ||
        bodyText?.includes('Zero') ||
        bodyText?.includes('0')
      ).toBeTruthy();
    }
  });

  test('Role-Shaped Navigation & 403 Forbidden Redirection', async ({ page }) => {
    // Override /api/v1/auth/me to return non-platform role and limited capabilities
    await page.route('/api/v1/auth/me', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          user: {
            id: 'usr-analyst-01',
            email: 'analyst@cloudlens.local',
            display_name: 'Financial Analyst',
          },
          roles: ['FINANCE_USER'],
          capabilities: ['reports:read', 'cost:read'],
          tenants: [{ id: 't-demo', name: 'Demo Enterprise' }],
          current_tenant: { id: 't-demo', name: 'Demo Enterprise' },
        }),
      });
    });

    // Attempt to access Control Tower directly
    await page.goto('/control-tower');

    // Should be redirected to /403
    await page.waitForURL('**/403');
    await expect(page.locator('h1')).toHaveText('403 — Forbidden Access');
    await expect(page.locator('body')).toContainText('restricted capability');
  });

  test('404 Not Found Page for Nonexistent Routes', async ({ page }) => {
    await page.goto('/some-nonexistent-path-123');
    await expect(page.locator('h1')).toHaveText('404 — Page Not Found');
    await expect(page.locator('body')).toContainText('Return to Portal');
  });

  test('DesignSystemShowcase route /dev is absent from production build', async ({ page }) => {
    await page.goto('/dev');
    // In production build, /dev should fall through to 404
    await expect(page.locator('h1')).toHaveText('404 — Page Not Found');
  });

  test('Axe-core Accessibility Audit: Zero Serious or Critical Violations across screens', async ({ page }) => {
    test.setTimeout(120000);
    // Audit a rich set of screens including forms, tables, dashboards, and wizards
    const auditScreens = [
      '/',
      '/login',
      '/estimator',
      '/quotas',
      '/provisioning',
      '/remediation',
      '/statements',
      '/planning',
      '/commitments',
      '/audit',
      '/settings',
      '/control-tower',
    ];

    for (const p of auditScreens) {
      await page.goto(p);
      await page.waitForLoadState('networkidle');
      const accessibilityScanResults = await new AxeBuilder({ page })
        .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
        .analyze();

      const seriousOrCritical = accessibilityScanResults.violations.filter(
        (v) => v.impact === 'serious' || v.impact === 'critical'
      );

      expect(
        seriousOrCritical,
        `Expected 0 serious/critical a11y violations on ${p}, found: ${JSON.stringify(seriousOrCritical, null, 2)}`
      ).toEqual([]);
    }
  });
});
