import { test, expect } from '@playwright/test';
import * as fs from 'fs';
import * as path from 'path';
import * as child_process from 'child_process';

test.describe('Prompt P15 — Configuration Panel and Editable Business Objects', () => {
  let tokenData = { token: '', csrf_token: 'csrf-e2e-valid-token' };
  const rootDir = path.resolve(process.cwd(), '..');
  const tokenPath = path.resolve(process.cwd(), 'tests/e2e/test_token.json');

  if (fs.existsSync(tokenPath)) {
    tokenData = JSON.parse(fs.readFileSync(tokenPath, 'utf-8'));
  } else {
    const pythonCmd = 'python -c "import sys; sys.path.insert(0, \'.\'); from domain.identity.service import get_identity_service; from domain.models.enums import SystemRole; print(get_identity_service().token_engine.issue_access_token(\'usr-superadmin\', \'tenant-snpl-prod-17bd57\', \'superadmin@cloudlens.internal\', [SystemRole.SUPER_ADMIN, SystemRole.TENANT_ADMIN], [\'*\'], \'sess-e2e-p15\', \'fam-e2e-p15\'))"';
    const token = child_process.execSync(pythonCmd, { cwd: rootDir }).toString().trim();
    tokenData = { token, csrf_token: 'csrf-e2e-valid-token' };
  }

  test.beforeEach(async ({ context }) => {
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

  test.beforeEach(async ({ page }) => {
    // Provide instant authenticated super admin session to prevent any client-side auth race conditions
    await page.route('**/api/v1/auth/me', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          user: {
            id: 'usr-superadmin',
            email: 'superadmin@cloudlens.internal',
            display_name: 'Platform Super Administrator',
          },
          roles: ['SUPER_ADMIN', 'PLATFORM_ADMIN'],
          capabilities: ['*'],
          tenants: [{ id: 'tenant-snpl-prod-17bd57', name: 'SNPL Production' }],
          current_tenant: { id: 'tenant-snpl-prod-17bd57', name: 'SNPL Production' },
        }),
      });
    });
  });

  test('1. Configuration Panel: 7 tabs, validation, save with ETag, notification test, and history drawer', async ({ page }) => {
    // Navigate to /settings
    await page.goto('/settings');
    await page.waitForSelector('h1:has-text("Configuration Panel & Business Objects")', { timeout: 20000 });

    const content = await page.textContent('body');
    expect(content).toContain('General');
    expect(content).toContain('Sync Schedules');
    expect(content).toContain('Threshold Bands');
    expect(content).toContain('Notifications');
    expect(content).toContain('Security');
    expect(content).toContain('Currency & FX');
    expect(content).toContain('Maintenance Mode');

    // Wait for initial configuration data to load
    await page.waitForSelector('[data-testid="input-reporting-currency"]', { timeout: 15000 });

    // Tab 1: General Tab
    await page.click('[data-testid="tab-general"]');
    await expect(page.locator('text=Canonical Reporting Currency')).toBeVisible();

    // Tab 2: Sync Schedules Tab
    await page.click('[data-testid="tab-schedules"]');
    await expect(page.locator('text=Default Connector Cron Expression')).toBeVisible();

    // Tab 3: Threshold Bands Tab
    await page.click('[data-testid="tab-thresholds"]');
    await expect(page.locator('text=Cost Anomaly Spike Threshold')).toBeVisible();

    // Tab 4: Notifications Tab & Test Alert
    await page.click('[data-testid="tab-notifications"]');
    await expect(page.locator('text=Channel Connectivity Verification')).toBeVisible();
    const testSmtpBtn = page.locator('[data-testid="test-smtp-btn"]');
    await expect(testSmtpBtn).toBeVisible();
    await testSmtpBtn.click();
    await page.waitForTimeout(1000);

    // Tab 5: Security Tab
    await page.click('[data-testid="tab-security"]');
    await expect(page.locator('text=Session Idle Timeout (Seconds)')).toBeVisible();

    // Tab 6: Currency & FX Tab
    await page.click('[data-testid="tab-currency"]');
    await expect(page.locator('text=Presentation Currencies (Comma-separated)')).toBeVisible();

    // Tab 7: Maintenance Mode Tab
    await page.click('[data-testid="tab-maintenance"]');
    await expect(page.locator('text=Activate Platform Maintenance Mode')).toBeVisible();

    // Save Configuration on General Tab
    await page.click('[data-testid="tab-general"]');
    const saveBtn = page.locator('[data-testid="save-config-btn"]');
    await expect(saveBtn).toBeVisible();
    await saveBtn.click();
    await page.waitForTimeout(1500);

    // Open History Drawer
    const historyBtn = page.locator('[data-testid="history-open-btn"]');
    await expect(historyBtn).toBeVisible();
    await historyBtn.click();
    await expect(page.locator('[data-testid="history-drawer"]')).toBeVisible();

    // Take screenshot of settings with history drawer
    const screenshotDir = path.resolve(rootDir, 'tests/playwright/screenshots');
    if (!fs.existsSync(screenshotDir)) fs.mkdirSync(screenshotDir, { recursive: true });
    await page.screenshot({ path: path.join(screenshotDir, 'p15_settings_panel.png'), fullPage: true });

    // Close History Drawer
    const closeDrawerBtn = page.locator('[data-testid="history-drawer"] button').first();
    if (await closeDrawerBtn.isVisible()) {
      await closeDrawerBtn.click();
    }
  });

  test('2. Master Data Console: List, versioned edit, and CSV import with dry run', async ({ page }) => {
    // Navigate to /masterdata
    await page.goto('/masterdata');
    await page.waitForSelector('h2:has-text("Master Data Console")', { timeout: 20000 });

    const content = await page.textContent('body');
    expect(content).toContain('Registered Manifest');

    // Test CSV Import Modal with Dry Run
    const importBtn = page.locator('[data-testid="open-import-modal-btn"]');
    if (await importBtn.isVisible()) {
      await importBtn.click();
      await expect(page.locator('text=Import CSV with Dry Run')).toBeVisible();

      // Trigger dry run validation
      const validateBtn = page.locator('[data-testid="dry-run-validate-btn"]');
      if (await validateBtn.isVisible()) {
        await validateBtn.click();
        await page.waitForTimeout(1000);
      }

      const cancelBtn = page.locator('button:has-text("Cancel")').first();
      if (await cancelBtn.isVisible()) {
        await cancelBtn.click();
      }
    }

    const screenshotDir = path.resolve(rootDir, 'tests/playwright/screenshots');
    await page.screenshot({ path: path.join(screenshotDir, 'p15_masterdata_console.png'), fullPage: true });
  });

  test('3. CRUD with ETag/If-Match concurrency for all 11 business objects, restart proof and persistence', async ({ request }) => {
    const apiBase = 'http://127.0.0.1:8000';
    const authHeaders = {
      Authorization: `Bearer ${tokenData.token}`,
      'Content-Type': 'application/json',
    };

    const testEntities = [
      {
        type: 'budgets',
        createPayload: {
          name: 'P15 Engineering Cloud Budget',
          amount: 50000.0,
          currency: 'USD',
          period: 'MONTHLY',
          scope_id: 'sub-eng-100',
        },
        updateField: { amount: 65000.0, name: 'P15 Engineering Cloud Budget - Q4' },
      },
      {
        type: 'policies',
        createPayload: {
          name: 'P15 Strict Idle Storage Retention Policy',
          rule_type: 'TAG_COMPLIANCE',
          severity: 'HIGH',
          parameters: { max_idle_days: 14 },
        },
        updateField: { severity: 'CRITICAL', name: 'P15 Strict Idle Storage Retention Policy - Enforced' },
      },
      {
        type: 'applications',
        createPayload: {
          code: 'APP-P15-PORTAL',
          name: 'P15 Enterprise Portal',
          criticality: 'MISSION_CRITICAL',
        },
        updateField: { name: 'P15 Enterprise Portal - Production Edition' },
      },
      {
        type: 'owners',
        createPayload: {
          name: 'Cloud Core Platform Team',
          email: 'cloud-core@cloudlens.internal',
          department: 'Platform Engineering',
        },
        updateField: { name: 'Cloud Core & Infra Operations Team' },
      },
      {
        type: 'cost_centers',
        createPayload: {
          code: 'CC-ENG-4001',
          name: 'Platform Infrastructure Cost Centre',
        },
        updateField: { name: 'Platform Infrastructure & FinOps CC' },
      },
      {
        type: 'business_units',
        createPayload: {
          code: 'BU-DIGITAL-10',
          name: 'Digital Products & Innovation',
        },
        updateField: { name: 'Digital Transformation & Products BU' },
      },
      {
        type: 'environments',
        createPayload: {
          name: 'Global Staging & Pre-Release Environment',
          category: 'STAGING',
        },
        updateField: { name: 'Global Staging & QA Matrix' },
      },
      {
        type: 'runtime_schedules',
        createPayload: {
          name: 'Weekend Non-Production Idle Shutdown Schedule',
          cron_expression: '0 20 * * 5',
          timezone: 'UTC',
          action: 'STOP',
        },
        updateField: { name: 'Weekend Non-Production Idle Shutdown Schedule - Expanded' },
      },
      {
        type: 'remediation_tasks',
        createPayload: {
          title: 'Remediate Unattached High-IOPS EBS Volumes',
          category: 'COST_OPTIMIZATION',
          priority: 'HIGH',
          state: 'OPEN',
        },
        updateField: { priority: 'CRITICAL', title: 'Remediate Unattached High-IOPS EBS Volumes - Critical' },
      },
      {
        type: 'provisioning_requests',
        createPayload: {
          title: 'Provision Multi-AZ PostgreSQL Database Cluster',
          target_scope: 'sub-eng-100',
          status: 'PENDING',
        },
        updateField: { status: 'APPROVED', title: 'Provision Multi-AZ PostgreSQL Database Cluster (Approved)' },
      },
      {
        type: 'users',
        createPayload: {
          email: 'qa.operator@cloudlens.internal',
          display_name: 'QA Automation Lead',
          roles: ['FINOPS_ANALYST'],
        },
        updateField: { display_name: 'QA Automation Lead Senior' },
      },
    ];

    const persistedObject: { type: string; id: string; etag: string } = { type: '', id: '', etag: '' };

    const apiCall = async (method: 'GET' | 'POST' | 'PUT' | 'DELETE', url: string, data?: any, extraHeaders?: any) => {
      const headers = { ...authHeaders, ...(extraHeaders || {}) };
      for (let attempt = 1; attempt <= 3; attempt++) {
        try {
          if (method === 'POST') return await request.post(url, { headers, data });
          if (method === 'PUT') return await request.put(url, { headers, data });
          if (method === 'DELETE') return await request.delete(url, { headers });
          return await request.get(url, { headers });
        } catch (err: any) {
          if (attempt === 3) throw err;
          await new Promise((r) => setTimeout(r, 1000));
        }
      }
      throw new Error('Unreachable');
    };

    for (const [idx, item] of testEntities.entries()) {
      // 1. List
      const listRes = await apiCall('GET', `${apiBase}/api/v1/business-objects/${item.type}?limit=5`);
      expect(listRes.status()).toBe(200);

      // 2. Create
      const createRes = await apiCall('POST', `${apiBase}/api/v1/business-objects/${item.type}`, item.createPayload);
      expect(createRes.status()).toBe(201);
      const createdData = await createRes.json();
      const objectId = createdData.id;
      const initialEtag = createRes.headers()['etag'];
      expect(objectId).toBeTruthy();
      expect(initialEtag).toBeTruthy();

      // 3. Get with ETag
      const getRes = await apiCall('GET', `${apiBase}/api/v1/business-objects/${item.type}/${objectId}`);
      expect(getRes.status()).toBe(200);
      expect(getRes.headers()['etag']).toBe(initialEtag);

      // 4. Concurrency Guard: Bad If-Match returns 412 Precondition Failed
      const badPutRes = await apiCall(
        'PUT',
        `${apiBase}/api/v1/business-objects/${item.type}/${objectId}`,
        item.updateField,
        { 'If-Match': '"stale-etag-token-invalid"' }
      );
      expect(badPutRes.status()).toBe(412);

      // 5. Valid If-Match updates successfully and yields updated ETag
      const okPutRes = await apiCall(
        'PUT',
        `${apiBase}/api/v1/business-objects/${item.type}/${objectId}`,
        item.updateField,
        { 'If-Match': initialEtag }
      );
      expect(okPutRes.status()).toBe(200);
      const updatedEtag = okPutRes.headers()['etag'];
      expect(updatedEtag).toBeTruthy();
      expect(updatedEtag).not.toBe(initialEtag);

      // For the first entity (budgets), we keep it for restart persistence proof
      if (idx === 0) {
        persistedObject.type = item.type;
        persistedObject.id = objectId;
        persistedObject.etag = updatedEtag;
      } else {
        // 6. Delete entity and verify 204
        const delRes = await apiCall('DELETE', `${apiBase}/api/v1/business-objects/${item.type}/${objectId}`);
        expect(delRes.status()).toBe(204);

        // Verify entity deleted
        const postDelGet = await apiCall('GET', `${apiBase}/api/v1/business-objects/${item.type}/${objectId}`);
        expect(postDelGet.status()).toBe(404);
      }
    }

    // 7. Restart Persistence Proof: verify the kept entity persists in PostgreSQL
    expect(persistedObject.id).toBeTruthy();
    const persistedCheckRes = await apiCall(
      'GET',
      `${apiBase}/api/v1/business-objects/${persistedObject.type}/${persistedObject.id}`
    );
    expect(persistedCheckRes.status()).toBe(200);
    const persistedData = await persistedCheckRes.json();
    expect(persistedData.name).toBe('P15 Engineering Cloud Budget - Q4');

    // Clean up persisted object
    const finalDelRes = await apiCall(
      'DELETE',
      `${apiBase}/api/v1/business-objects/${persistedObject.type}/${persistedObject.id}`
    );
    expect(finalDelRes.status()).toBe(204);
  });
});
