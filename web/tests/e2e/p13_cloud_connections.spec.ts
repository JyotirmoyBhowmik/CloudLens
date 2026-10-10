import { test, expect } from '@playwright/test';
import * as fs from 'fs';
import * as path from 'path';
import * as child_process from 'child_process';

test.describe('Prompt P13 — Real Cloud Connections & Live Inventory Integration', () => {
  let tokenData = { token: '', csrf_token: 'csrf-e2e-valid-token' };
  const tokenPath = path.resolve(process.cwd(), 'tests/e2e/test_token.json');
  if (fs.existsSync(tokenPath)) {
    tokenData = JSON.parse(fs.readFileSync(tokenPath, 'utf-8'));
  } else {
    const pythonCmd = 'python -c "import sys; sys.path.insert(0, \'.\'); from domain.identity.service import get_identity_service; from domain.models.enums import SystemRole; print(get_identity_service().token_engine.issue_access_token(\'user-admin-17bd57\', \'tenant-snpl-prod-17bd57\', \'admin@snpl.com\', [SystemRole.SUPER_ADMIN, SystemRole.TENANT_ADMIN], [\'*\'], \'sess-e2e\', \'fam-e2e\'))"';
    const rootDir = path.resolve(process.cwd(), '..');
    const token = child_process.execSync(pythonCmd, { cwd: rootDir }).toString().trim();
    tokenData = { token, csrf_token: 'csrf-e2e-valid-token' };
  }

  test.beforeEach(async ({ context, page }) => {
    // Add real authentication cookies to context
    const cookieUrls = ['http://127.0.0.1:4173', 'http://localhost:4173', 'http://127.0.0.1:8000', 'http://localhost:8000'];
    for (const url of cookieUrls) {
      await context.addCookies([
        {
          name: 'cloudlens_access_token',
          value: tokenData.token,
          url,
          httpOnly: false,
          sameSite: 'Lax',
        },
        {
          name: 'cloudlens_csrf_token',
          value: tokenData.csrf_token,
          url,
          httpOnly: false,
          sameSite: 'Lax',
        },
      ]);
    }
  });

  test('Live account resources visible in Service Inventory and captured', async ({ page }) => {
    // Navigate to /inventory
    await page.goto('/inventory');

    // Wait for inventory data to load
    await page.waitForSelector('text=cloudlens-cur-112233445566', { timeout: 20000 });

    // Verify resources from live AWS account appear in the inventory
    const content = await page.textContent('body');
    expect(content).toContain('cloudlens-cur-112233445566');
    expect(content).toContain('AWS');

    // Save screenshots
    const dirs = [
      path.resolve(process.cwd(), 'screenshots'),
      path.resolve(process.cwd(), '..', 'tests', 'playwright', 'screenshots'),
    ];
    for (const dir of dirs) {
      if (!fs.existsSync(dir)) {
        fs.mkdirSync(dir, { recursive: true });
      }
      const screenshotPath = path.join(dir, 'p13_inventory_resources.png');
      await page.screenshot({ path: screenshotPath, fullPage: true });
      expect(fs.existsSync(screenshotPath)).toBe(true);
    }
  });

  test('Cloud Connections UI displays real connector, permissions diagnostics, and credential replacement', async ({ page }) => {
    // Navigate to /connectors
    await page.goto('/connectors');

    // Wait for real connector to be rendered
    await page.waitForSelector('text=AWS Production Management Account', { timeout: 20000 });

    const content = await page.textContent('body');
    expect(content).toContain('AWS Production Management Account');
    expect(content).toContain('ACTIVE');
    expect(content).toContain('Hourly (00:00 UTC)');

    // 1. Test Connection Diagnostics Drawer
    const testButton = page.locator('button:has-text("Test")').first();
    await testButton.click();

    // Verify itemized permissions
    await page.waitForSelector('text=Permission Diagnostics & Verification', { timeout: 10000 });
    await page.waitForSelector('text=organizations:DescribeOrganization', { timeout: 15000 });
    const diagnosticsContent = await page.textContent('body');
    expect(diagnosticsContent).toContain('organizations:DescribeOrganization');
    expect(diagnosticsContent).toContain('Hierarchy Discovery');

    // Close Diagnostics
    const closeDiagnosticsBtn = page.locator('button:has-text("Close")').last();
    await closeDiagnosticsBtn.click();

    // 2. Rotate Credential Modal
    const rotateBtn = page.locator('button:has-text("Rotate")').first();
    await rotateBtn.click();

    await page.waitForSelector('text=Rotate Credential Without Downtime', { timeout: 10000 });
    const rotateContent = await page.textContent('body');
    expect(rotateContent).toContain('Replace');
    expect(rotateContent).toContain('OpenBao');

    // Close Rotate Modal
    const cancelRotateBtn = page.locator('button:has-text("Cancel")').first();
    await cancelRotateBtn.click();

    // Save screenshots
    const dirs = [
      path.resolve(process.cwd(), 'screenshots'),
      path.resolve(process.cwd(), '..', 'tests', 'playwright', 'screenshots'),
    ];
    for (const dir of dirs) {
      if (!fs.existsSync(dir)) {
        fs.mkdirSync(dir, { recursive: true });
      }
      const screenshotPath = path.join(dir, 'p13_cloud_connections.png');
      await page.screenshot({ path: screenshotPath, fullPage: true });
      expect(fs.existsSync(screenshotPath)).toBe(true);
    }
  });
});
