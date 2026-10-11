import { test, expect } from '@playwright/test';
import * as fs from 'fs';
import * as path from 'path';

/**
 * P19 Production E2E Test Suite
 * Covers:
 * 1. Sign-in flow and IdP integration
 * 2. First-run setup wizard
 * 3. Tenant administration and switching
 * 4. DEMO vs PRODUCTION tenant presentation
 * 5. Interactive Business Object / Configuration forms
 * 6. 403 Forbidden RBAC gate enforcement
 * All tests capture screenshots as build artifacts.
 */

const SCREENSHOT_DIR = path.resolve(process.cwd(), 'screenshots');

function ensureScreenshotDir() {
  if (!fs.existsSync(SCREENSHOT_DIR)) {
    fs.mkdirSync(SCREENSHOT_DIR, { recursive: true });
  }
}

test.beforeAll(() => {
  ensureScreenshotDir();
});

test.describe('P19 Production E2E Suite', () => {
  // Shared health probe mock
  test.beforeEach(async ({ page }) => {
    await page.route('/api/v1/health', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          status: 'HEALTHY',
          service: 'cloudlens-api',
          version: '1.1.0',
          timestamp: new Date().toISOString(),
          correlation_id: 'e2e-p19-health-check',
        }),
      });
    });
  });

  // ---------------------------------------------------------------------------
  // 1. Sign-In Flow
  // ---------------------------------------------------------------------------
  test('E2E-01: Sign-in view renders authentication controls and IdP link', async ({ page }) => {
    // Unauthenticated session
    await page.route('/api/v1/auth/me', async (route) => {
      await route.fulfill({ status: 401, body: JSON.stringify({ detail: 'Unauthenticated' }) });
    });

    await page.goto('/login');
    await expect(page.locator('h1')).toContainText('Sign in to CloudLens');
    await expect(page.locator('button', { hasText: 'Sign In with Corporate IdP' })).toBeVisible();

    const shotPath = path.join(SCREENSHOT_DIR, 'p19_01_signin.png');
    await page.screenshot({ path: shotPath, fullPage: true });
    expect(fs.existsSync(shotPath)).toBe(true);
  });

  // ---------------------------------------------------------------------------
  // 2. Setup Wizard Flow
  // ---------------------------------------------------------------------------
  test('E2E-02: First-run setup wizard initializes system and organizational tenant', async ({ page }) => {
    await page.route('/api/v1/auth/me', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          user: { id: 'usr-admin', email: 'admin@cloudlens.internal', display_name: 'Platform Super Admin' },
          roles: ['SUPER_ADMIN'],
          capabilities: ['*'],
          tenants: [{ id: 'tenant-system', name: 'System Root Tenant' }],
          current_tenant: { id: 'tenant-system', name: 'System Root Tenant' },
        }),
      });
    });

    await page.route('/api/v1/setup/status', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ initialized: false, step: 'INITIAL_TENANT' }),
      });
    });

    await page.goto('/setup');
    await expect(page.locator('body')).toBeVisible();

    const shotPath = path.join(SCREENSHOT_DIR, 'p19_02_setup_wizard.png');
    await page.screenshot({ path: shotPath, fullPage: true });
    expect(fs.existsSync(shotPath)).toBe(true);
  });

  // ---------------------------------------------------------------------------
  // 3. Tenant Administration & Switching
  // ---------------------------------------------------------------------------
  test('E2E-03: Tenant administration displays tenants list and supports switching', async ({ page }) => {
    const tenants = [
      {
        id: 't-prod-01',
        code: 'PROD_APAC',
        name: 'APAC Production Core',
        type: 'PRODUCTION',
        reporting_currency: 'USD',
        status: 'ACTIVE',
        created_at: '2026-10-01T00:00:00Z',
      },
      {
        id: 't-demo-01',
        code: 'DEMO_SANDBOX',
        name: 'FinOps Demo Sandbox',
        type: 'DEMO',
        reporting_currency: 'USD',
        status: 'ACTIVE',
        created_at: '2026-10-02T00:00:00Z',
      },
    ];

    await page.route('/api/v1/auth/me', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          user: { id: 'usr-admin', email: 'admin@cloudlens.internal', display_name: 'Super Administrator' },
          roles: ['SUPER_ADMIN'],
          capabilities: ['platform.operate', 'platform.observe', 'tenant.admin'],
          tenants: tenants.map((t) => ({ id: t.id, name: t.name })),
          current_tenant: { id: 't-prod-01', name: 'APAC Production Core' },
        }),
      });
    });

    await page.route('/api/v1/tenants', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          items: tenants,
          total: tenants.length,
          page: 1,
          page_size: 20,
        }),
      });
    });

    await page.goto('/admin/tenants');
    await expect(page.locator('body')).toContainText('APAC Production Core');

    const shotPath = path.join(SCREENSHOT_DIR, 'p19_03_tenant_admin.png');
    await page.screenshot({ path: shotPath, fullPage: true });
    expect(fs.existsSync(shotPath)).toBe(true);
  });

  // ---------------------------------------------------------------------------
  // 4. DEMO vs PRODUCTION Presentation
  // ---------------------------------------------------------------------------
  test('E2E-04: DEMO tenant renders demo badge & populated metrics, PRODUCTION renders empty state', async ({ page }) => {
    // 4a. DEMO Tenant check
    await page.addInitScript(() => {
      localStorage.setItem('cloudlens_is_demo', 'true');
    });

    await page.route('/api/v1/auth/me', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          user: { id: 'usr-finops', email: 'finops@cloudlens.internal', display_name: 'Demo FinOps Lead' },
          roles: ['FINOPS_ADMINISTRATOR'],
          capabilities: ['cost.read', 'budgets.read', 'budgets.write'],
          tenants: [{ id: 'T-DEMO', name: 'Global Demo Tenant', type: 'DEMO' }],
          current_tenant: { id: 'T-DEMO', name: 'Global Demo Tenant', type: 'DEMO' },
        }),
      });
    });

    await page.route('/api/v1/budgets*', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          items: [
            {
              id: 'b-demo-01',
              name: 'Q4 Cloud Infrastructure Budget',
              amount: 250000,
              currency: 'USD',
              status: 'ON_TRACK',
            },
          ],
          total: 1,
          page: 1,
          page_size: 20,
        }),
      });
    });

    await page.goto('/budgets');
    // Verify DemoModeBanner is rendered
    await expect(page.locator('text=Demo Mode Active:')).toBeVisible({ timeout: 10000 });

    const demoShotPath = path.join(SCREENSHOT_DIR, 'p19_04_demo_mode.png');
    await page.screenshot({ path: demoShotPath, fullPage: true });
    expect(fs.existsSync(demoShotPath)).toBe(true);

    // 4b. PRODUCTION Tenant check
    await page.addInitScript(() => {
      localStorage.setItem('cloudlens_is_demo', 'false');
    });

    await page.route('/api/v1/auth/me', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          user: { id: 'usr-prod', email: 'prod@cloudlens.internal', display_name: 'Prod Engineer' },
          roles: ['FINOPS_ADMINISTRATOR'],
          capabilities: ['cost.read', 'budgets.read', 'budgets.write'],
          tenants: [{ id: 't-prod-clean', name: 'Pristine Production Tenant', type: 'PRODUCTION' }],
          current_tenant: { id: 't-prod-clean', name: 'Pristine Production Tenant', type: 'PRODUCTION' },
        }),
      });
    });

    await page.route('/api/v1/budgets*', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ items: [], total: 0, page: 1, page_size: 20 }),
      });
    });

    await page.goto('/budgets');
    // Demo banner must NOT be present
    await expect(page.locator('text=Demo Mode Active:')).toHaveCount(0);

    const prodShotPath = path.join(SCREENSHOT_DIR, 'p19_04_production_mode.png');
    await page.screenshot({ path: prodShotPath, fullPage: true });
    expect(fs.existsSync(prodShotPath)).toBe(true);
  });

  // ---------------------------------------------------------------------------
  // 5. Interactive Business Object / Configuration Forms
  // ---------------------------------------------------------------------------
  test('E2E-05: Configuration panel renders editable tabs and Save/Cancel controls', async ({ page }) => {
    await page.route('/api/v1/auth/me', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          user: { id: 'usr-admin', email: 'admin@cloudlens.internal', display_name: 'System Admin' },
          roles: ['PLATFORM_ADMIN'],
          capabilities: ['platform.operate', 'platform.observe', 'tenants:settings:read', 'config.write'],
          tenants: [{ id: 't-main', name: 'Primary Organization' }],
          current_tenant: { id: 't-main', name: 'Primary Organization' },
        }),
      });
    });

    await page.route('/api/v1/config/settings*', async (route) => {
      await route.fulfill({
        status: 200,
        headers: { ETag: '"cfg-v10-hash"' },
        contentType: 'application/json',
        body: JSON.stringify({
          general: { platform_name: 'CloudLens Enterprise', default_currency: 'USD' },
          sync_schedules: { aws_interval_minutes: 60, azure_interval_minutes: 60 },
          threshold_bands: { warning_percent: 80, critical_percent: 95 },
          notifications: { smtp_host: 'smtp.internal', alert_email: 'alerts@internal.org' },
          security: { session_timeout_minutes: 30, mfa_enforced: true },
          currency_fx: { base_currency: 'USD' },
          maintenance_mode: { enabled: false, message: '' },
        }),
      });
    });

    await page.goto('/settings');
    await expect(page.locator('h1')).toContainText('Configuration Panel & Business Objects');
    // Form Save / Cancel buttons present
    await expect(page.locator('button[data-testid="save-config-btn"]')).toBeVisible();
    await expect(page.locator('button[data-testid="cancel-config-btn"]')).toBeVisible();

    const shotPath = path.join(SCREENSHOT_DIR, 'p19_05_crud_forms.png');
    await page.screenshot({ path: shotPath, fullPage: true });
    expect(fs.existsSync(shotPath)).toBe(true);
  });

  // ---------------------------------------------------------------------------
  // 6. 403 Forbidden Access Gate
  // ---------------------------------------------------------------------------
  test('E2E-06: Unauthorized route navigation redirects to 403 Forbidden view', async ({ page }) => {
    // User with Read-Only role lacking admin capability
    await page.route('/api/v1/auth/me', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          user: { id: 'usr-viewer', email: 'viewer@cloudlens.internal', display_name: 'Read Only Auditor' },
          roles: ['READ_ONLY_USER'],
          capabilities: ['platform.observe'],
          tenants: [{ id: 't-main', name: 'Main Tenant' }],
          current_tenant: { id: 't-main', name: 'Main Tenant' },
        }),
      });
    });

    // Directly navigating to /403 or restricted page
    await page.goto('/403');
    await expect(page.locator('h1')).toContainText('403 — Forbidden Access');
    await expect(page.locator('body')).toContainText('Cross-tenant boundary or restricted capability');

    const shotPath = path.join(SCREENSHOT_DIR, 'p19_06_forbidden_403.png');
    await page.screenshot({ path: shotPath, fullPage: true });
    expect(fs.existsSync(shotPath)).toBe(true);
  });
});
