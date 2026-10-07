import { test, expect } from '@playwright/test';
import * as fs from 'fs';
import * as path from 'path';

test.describe('Prompt P02 — Real Sign-In and Authorization E2E', () => {
  test.beforeAll(() => {
    const screenshotsDir = path.resolve(process.cwd(), 'screenshots');
    if (!fs.existsSync(screenshotsDir)) {
      fs.mkdirSync(screenshotsDir, { recursive: true });
    }
  });

  test('1. Header displays user name and tenant switcher without role dropdown', async ({ page }) => {
    // Mock /api/v1/health probe
    await page.route('/api/v1/health', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          status: 'HEALTHY',
          service: 'cloudlens-api',
          version: '0.1.0-alpha',
          timestamp: '2026-10-05T22:00:00Z',
          correlation_id: 'e2e-header-test-id',
        }),
      });
    });

    // Mock /api/v1/auth/me to return authentic user session with granted tenants
    await page.route('/api/v1/auth/me', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          user: {
            id: 'usr-finops-lead',
            email: 'sarah.chen@enterprise.internal',
            display_name: 'Sarah Chen',
          },
          roles: ['FINOPS_ADMINISTRATOR'],
          capabilities: ['analytics:read', 'cost:read', 'budgets:write'],
          tenants: [
            { id: 't-prod-01', name: 'Production Estate' },
            { id: 't-stage-02', name: 'Staging Estate' },
          ],
          current_tenant: { id: 't-prod-01', name: 'Production Estate' },
        }),
      });
    });

    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');

    // 1. Verify user display name
    const userDisplay = page.locator('#header-user-display');
    await expect(userDisplay).toBeVisible({ timeout: 5000 });
    await expect(userDisplay).toHaveText('Sarah Chen');

    // 2. Verify tenant switcher lists only granted tenants
    const tenantSwitcher = page.locator('#tenant-switcher');
    await expect(tenantSwitcher).toBeVisible();
    const options = await tenantSwitcher.locator('option').allTextContents();
    expect(options).toEqual(['Production Estate', 'Staging Estate']);

    // 3. Verify sign out button is present
    const signoutBtn = page.locator('#header-signout-btn');
    await expect(signoutBtn).toBeVisible();

    // 4. Verify NO role dropdown exists anywhere in the header or DOM
    const roleSelect = page.locator('select#role-switcher, select[name="role"], select#user-role');
    await expect(roleSelect).toHaveCount(0);

    // 5. Verify localStorage does NOT contain cloudlens_user_role
    const storedRole = await page.evaluate(() => localStorage.getItem('cloudlens_user_role'));
    expect(storedRole).toBeNull();

    // Capture screenshot of the clean header without role dropdown
    await page.screenshot({ path: 'screenshots/header-without-role-dropdown.png', fullPage: false });
  });

  test('2. READ_ONLY user cannot see Administration link and receives 403 on direct URL', async ({ page }) => {
    // Mock /api/v1/health probe
    await page.route('/api/v1/health', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          status: 'HEALTHY',
          service: 'cloudlens-api',
          version: '0.1.0-alpha',
          timestamp: '2026-10-05T22:00:00Z',
          correlation_id: 'e2e-readonly-test-id',
        }),
      });
    });

    // Mock /api/v1/auth/me with READ_ONLY_USER role and read-only capabilities (no admin:access)
    await page.route('/api/v1/auth/me', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          user: {
            id: 'usr-readonly-01',
            email: 'readonly@cloudlens.local',
            display_name: 'Read Only Auditor',
          },
          roles: ['READ_ONLY_USER'],
          capabilities: ['reports:read', 'analytics:read'],
          tenants: [{ id: 't-demo-01', name: 'Demo Estate' }],
          current_tenant: { id: 't-demo-01', name: 'Demo Estate' },
        }),
      });
    });

    // 1. Visit landing page
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');

    // 2. Verify Administration link is NOT visible in the navigation strip
    const adminNavLink = page.locator('nav a[href="/admin"]');
    await expect(adminNavLink).toHaveCount(0);

    // 3. Attempt direct URL navigation to /admin
    await page.goto('/admin');
    await page.waitForLoadState('domcontentloaded');

    // 4. Assert URL redirects to /403 or renders Forbidden page
    await expect(page).toHaveURL(/\/403$/);

    const forbiddenHeading = page.locator('h1, h2, div', {
      hasText: /403|Access Denied|Forbidden/i,
    });
    await expect(forbiddenHeading.first()).toBeVisible({ timeout: 5000 });

    // Capture screenshot of 403 Forbidden page
    await page.screenshot({ path: 'screenshots/readonly-403-forbidden.png', fullPage: true });
  });

  test('3. Admin sign-in shows Keycloak OTP step', async ({ page }) => {
    // Navigate directly to Keycloak auth endpoint for cloudlens realm
    const keycloakAuthUrl =
      'http://localhost:8081/realms/cloudlens/protocol/openid-connect/auth?' +
      'client_id=cloudlens-api&response_type=code&scope=openid%20profile%20email&redirect_uri=http%3A%2F%2Flocalhost%3A8000%2Fapi%2Fv1%2Fauth%2Foidc%2Fcallback';

    await page.goto(keycloakAuthUrl);
    await page.waitForLoadState('domcontentloaded');

    // Fill credentials for admin@jyotirmoyb.com
    await page.fill('#username', 'admin@jyotirmoyb.com');
    await page.fill('#password', 'TestKeycloakPassword123!');
    await page.click('#kc-login');

    // Wait for Keycloak required action: CONFIGURE_TOTP
    await page.waitForLoadState('networkidle');

    // Assert URL or page contains CONFIGURE_TOTP / Mobile Authenticator Setup
    const pageUrl = page.url();
    expect(pageUrl).toContain('CONFIGURE_TOTP');

    const otpSetupHeader = page.locator('h1, h2, #kc-page-title', {
      hasText: /Mobile Authenticator Setup|Authenticator|Scan barcode/i,
    });
    await expect(otpSetupHeader.first()).toBeVisible({ timeout: 10000 });

    // Capture screenshot of the Keycloak OTP configuration step
    await page.screenshot({ path: 'screenshots/admin-keycloak-otp-step.png', fullPage: true });
  });
});
