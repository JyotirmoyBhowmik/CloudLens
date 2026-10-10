import { test, expect } from '@playwright/test';
import * as fs from 'fs';
import * as path from 'path';

test.describe('Prompt P12 — Tenant Administration & First-Run Setup Suite', () => {
  test.beforeEach(async ({ page }) => {
    // Health probe
    await page.route('/api/v1/health', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          status: 'HEALTHY',
          service: 'cloudlens-api',
          version: '0.1.0-alpha',
          timestamp: '2026-10-10T02:00:00Z',
          correlation_id: 'p12-verification',
        }),
      });
    });
  });

  test('Super Admin creates "SNPL Production" via UI and captures screenshot', async ({ page }) => {
    let tenantsList = [
      {
        id: 'tenant-system',
        code: 'SYSTEM',
        name: 'System Root Tenant',
        type: 'PRODUCTION',
        reporting_currency: 'USD',
        fiscal_year_start: 1,
        iana_timezone: 'UTC',
        retention_profile: 'EXTENDED',
        status: 'ACTIVE',
        created_at: '2026-10-01T00:00:00Z',
        suspension_reason: null,
      },
    ];

    // Authenticated Super Admin
    await page.route('/api/v1/auth/me', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          user: {
            id: 'usr-super-admin',
            email: 'admin@cloudlens.internal',
            display_name: 'Platform Super Administrator',
          },
          roles: ['SUPER_ADMIN'],
          capabilities: ['*'],
          tenants: tenantsList.map((t) => ({ id: t.id, name: t.name })),
          current_tenant: { id: 'tenant-system', name: 'System Root Tenant' },
        }),
      });
    });

    // Tenants API endpoint handling
    await page.route('/api/v1/tenants', async (route) => {
      if (route.request().method() === 'GET') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(tenantsList),
        });
      } else if (route.request().method() === 'POST') {
        const payload = route.request().postDataJSON();
        const createdTenant = {
          id: 'tenant-snpl-prod',
          code: payload.code || 'SNPL_PROD',
          name: payload.name || 'SNPL Production',
          type: payload.type || 'PRODUCTION',
          reporting_currency: payload.reporting_currency || 'USD',
          fiscal_year_start: payload.fiscal_year_start || 1,
          iana_timezone: payload.iana_timezone || 'UTC',
          retention_profile: payload.retention_profile || 'STANDARD',
          status: 'ACTIVE',
          created_at: new Date().toISOString(),
          suspension_reason: null,
        };
        tenantsList.push(createdTenant);
        await route.fulfill({
          status: 201,
          contentType: 'application/json',
          body: JSON.stringify(createdTenant),
        });
      } else {
        await route.fallback();
      }
    });

    // Fallback for auxiliary endpoints
    await page.route('/api/v1/**', async (route) => {
      const url = route.request().url();
      if (url.includes('/api/v1/health') || url.includes('/api/v1/auth/me') || url.includes('/api/v1/tenants')) {
        return route.fallback();
      }
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([]),
      });
    });

    // 1. Navigate to Tenants Administration
    await page.goto('/tenants');
    await expect(page.locator('h1')).toContainText('Tenant Administration & Boundaries');

    // 2. Open Create Tenant modal
    const openBtn = page.locator('#create-tenant-open-btn');
    await expect(openBtn).toBeVisible();
    await openBtn.click();

    // 3. Modal should appear
    const modalTitle = page.locator('#create-tenant-title');
    await expect(modalTitle).toBeVisible();

    // 4. Fill in Tenant form for "SNPL Production"
    await page.fill('#tenant-code-input', 'SNPL_PROD');
    await page.fill('#tenant-name-input', 'SNPL Production');
    await page.selectOption('#tenant-type-select', 'PRODUCTION');
    await page.selectOption('#tenant-currency-select', 'USD');
    await page.fill('#tenant-fystart-input', '1');
    await page.fill('#tenant-timezone-input', 'UTC');
    await page.selectOption('#tenant-retention-select', 'STANDARD');

    // 5. Submit creation
    const submitBtn = page.locator('#create-tenant-submit-btn');
    await submitBtn.click();

    // 6. Modal closes and table displays "SNPL Production"
    await expect(modalTitle).not.toBeVisible();
    await expect(page.getByText('SNPL Production')).toBeVisible();
    await expect(page.getByText('SNPL_PROD')).toBeVisible();
    await expect(page.getByText('PRODUCTION', { exact: true }).first()).toBeVisible();

    // 7. Ensure screenshots directory exists and capture UI
    const screenshotDir = path.resolve(process.cwd(), 'screenshots');
    if (!fs.existsSync(screenshotDir)) {
      fs.mkdirSync(screenshotDir, { recursive: true });
    }
    const screenshotPath = path.join(screenshotDir, 'snpl_production_created.png');
    await page.screenshot({ path: screenshotPath, fullPage: true });

    // Verify screenshot file exists
    expect(fs.existsSync(screenshotPath)).toBe(true);
  });

  test('First-Run Setup Wizard Flow creates tenant and delegates Platform Admin', async ({ page }) => {
    let wizardTenantCreated = false;

    await page.route('/api/v1/auth/me', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          user: {
            id: 'usr-super-admin',
            email: 'admin@cloudlens.internal',
            display_name: 'Platform Super Administrator',
          },
          roles: ['SUPER_ADMIN'],
          capabilities: ['*'],
          tenants: [],
          current_tenant: null,
        }),
      });
    });

    await page.route('/api/v1/tenants', async (route) => {
      if (route.request().method() === 'POST') {
        wizardTenantCreated = true;
        await route.fulfill({
          status: 201,
          contentType: 'application/json',
          body: JSON.stringify({
            id: 'tenant-snpl-prod',
            code: 'SNPL_PROD',
            name: 'SNPL Production',
            type: 'PRODUCTION',
            reporting_currency: 'USD',
          }),
        });
      } else {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify([]),
        });
      }
    });

    await page.route('/api/v1/tenants/tenant-snpl-prod/users', async (route) => {
      await route.fulfill({
        status: 201,
        contentType: 'application/json',
        body: JSON.stringify({
          id: 'usr-delegated-admin',
          email: 'admin@snpl.internal',
          display_name: 'Platform Administrator',
          roles: ['PLATFORM_ADMIN'],
        }),
      });
    });

    await page.route('/api/v1/**', async (route) => {
      const url = route.request().url();
      if (url.includes('/api/v1/health') || url.includes('/api/v1/auth/me') || url.includes('/api/v1/tenants')) {
        return route.fallback();
      }
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([]),
      });
    });

    // 1. Navigate to /setup
    await page.goto('/setup');
    await expect(page.locator('h1')).toContainText('First-Run Platform Setup');

    // 2. Step 1: Create Tenant
    await page.fill('#setup-tenant-code', 'SNPL_PROD');
    await page.fill('#setup-tenant-name', 'SNPL Production');
    await page.click('#setup-tenant-next-btn');

    // 3. Step 2: Connect Cloud
    await expect(page.getByText('Step 2: Connect Cloud Provider')).toBeVisible();
    await page.click('#setup-cloud-next-btn');

    // 4. Step 3: Invite Users
    await expect(page.getByText('Step 3: Invite Initial Users')).toBeVisible();
    await page.click('#setup-invite-next-btn');

    // 5. Step 4: Delegated Platform Admin
    await expect(page.getByText('Step 4: Create Delegated Platform Admin')).toBeVisible();
    await page.click('#create-delegated-admin-btn');

    // 6. Assert success view
    await expect(page.getByText('First-Run Setup & Platform Admin Delegated!')).toBeVisible();
    expect(wizardTenantCreated).toBe(true);
  });

  test('Non-Admin user receives HTTP 403 Forbidden', async ({ page }) => {
    // Authenticated non-admin FinOps Analyst
    await page.route('/api/v1/auth/me', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          user: {
            id: 'usr-finops-analyst',
            email: 'analyst@snpl.internal',
            display_name: 'FinOps Analyst',
          },
          roles: ['FINANCE_USER'],
          capabilities: ['reports:read', 'cost:read'],
          tenants: [{ id: 'tenant-snpl-prod', name: 'SNPL Production' }],
          current_tenant: { id: 'tenant-snpl-prod', name: 'SNPL Production' },
        }),
      });
    });

    // Backend denies /api/v1/tenants with 403 Forbidden
    await page.route('/api/v1/tenants**', async (route) => {
      await route.fulfill({
        status: 403,
        contentType: 'application/json',
        body: JSON.stringify({
          detail: 'Forbidden: Requires Platform or Super Administrator authority.',
          error_code: 'INSUFFICIENT_PERMISSIONS',
        }),
      });
    });

    await page.route('/api/v1/**', async (route) => {
      const url = route.request().url();
      if (url.includes('/api/v1/health') || url.includes('/api/v1/auth/me') || url.includes('/api/v1/tenants')) {
        return route.fallback();
      }
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([]),
      });
    });

    // 1. Non-admin navigates to /tenants -> Guard redirects to /403
    await page.goto('/tenants');
    await expect(page).toHaveURL(/.*\/403/);
    await expect(page.getByText('403 — Forbidden Access')).toBeVisible();

    // 2. Direct API call from browser context to /api/v1/tenants returns 403
    const response = await page.evaluate(async () => {
      const res = await fetch('/api/v1/tenants');
      const data = await res.json();
      return { status: res.status, data };
    });
    expect(response.status).toBe(403);
    expect(response.data.detail).toContain('Forbidden: Requires Platform or Super Administrator authority.');
  });
});
