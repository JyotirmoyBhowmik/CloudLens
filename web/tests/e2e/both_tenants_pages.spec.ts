import { test, expect } from '@playwright/test';

interface PageTestCase {
  route: string;
  name: string;
  apiEndpoint: string;
  emptyTitle: string;
  demoSampleRecord: any;
  populatedAssertionText: string;
}

const PAGE_TEST_CASES: PageTestCase[] = [
  {
    route: '/audit',
    name: 'Audit Log Page',
    apiEndpoint: '/api/v1/audit/events*',
    emptyTitle: 'No Audit Events Recorded',
    demoSampleRecord: [
      {
        id: 'evt-01',
        eventType: 'CONNECTOR_SYNC_COMPLETED',
        event_type: 'CONNECTOR_SYNC_COMPLETED',
        actor: 'system-agent',
        targetEntity: 'AWS Connector',
        timestamp: '2026-10-09T10:00:00Z',
        correlationId: 'cid-001',
      },
    ],
    populatedAssertionText: 'CONNECTOR_SYNC_COMPLETED',
  },
  {
    route: '/planning',
    name: 'Budget Planning Page',
    apiEndpoint: '/api/v1/budgets/plans*',
    emptyTitle: 'No Planning Envelopes Found',
    demoSampleRecord: [
      {
        id: 'plan-01',
        scopeName: 'FY27 Cloud Infrastructure Plan',
        name: 'FY27 Cloud Infrastructure Plan',
        scopeType: 'BUSINESS_UNIT',
        currentRunRate: 350000,
        baseForecast: 450000,
        proposedBudget: 500000,
        status: 'ACTIVE',
      },
    ],
    populatedAssertionText: 'FY27 Cloud Infrastructure Plan',
  },
  {
    route: '/commitments',
    name: 'Commitment Renewals Page',
    apiEndpoint: '/api/v1/commitments*',
    emptyTitle: 'No Commitments Registered',
    demoSampleRecord: [
      {
        id: 'comm-01',
        commitment_id: 'comm-01',
        scope: 'Enterprise Core',
        type: 'SAVINGS_PLAN',
        provider: 'AWS',
        expiration_date: '2027-01-01',
        utilization_pct: 95.5,
        coverage_pct: 88.0,
        hourly_commitment: 50.0,
        status: 'ACTIVE',
      },
    ],
    populatedAssertionText: 'comm-01',
  },
  {
    route: '/budgets',
    name: 'Budget Management Page',
    apiEndpoint: '/api/v1/budgets*',
    emptyTitle: 'No Budgets Found',
    demoSampleRecord: [
      {
        id: 'b-01',
        name: 'Engineering Cloud Ops',
        scope: 'Engineering',
        target_amount: 100000,
        actual_spend: 85000,
        forecast_spend: 95000,
        currency: 'USD',
        alert_threshold_pct: 85,
        status: 'HEALTHY',
      },
    ],
    populatedAssertionText: 'Engineering Cloud Ops',
  },
  {
    route: '/connectors',
    name: 'Connector Management Page',
    apiEndpoint: '/api/v1/connectors*',
    emptyTitle: 'No Connectors Configured',
    demoSampleRecord: [
      {
        id: 'conn-01',
        name: 'AWS Production Core',
        provider: 'AWS',
        status: 'CONNECTED',
        last_sync_time: '2026-10-09T08:00:00Z',
        account_id: '123456789012',
      },
    ],
    populatedAssertionText: 'AWS Production Core',
  },
  {
    route: '/policies',
    name: 'Policy Management Page',
    apiEndpoint: '/api/v1/policies*',
    emptyTitle: 'No Policies Configured',
    demoSampleRecord: [
      {
        id: 'pol-01',
        policy_id: 'pol-01',
        name: 'POL-MAX-INSTANCE-SIZE',
        description: 'Prevent oversized instances',
        severity: 'HIGH',
        status: 'ACTIVE',
        rule_type: 'TAG_ENFORCEMENT',
      },
    ],
    populatedAssertionText: 'POL-MAX-INSTANCE-SIZE',
  },
  {
    route: '/provisioning',
    name: 'Provisioning Requests Page',
    apiEndpoint: '/api/v1/provisioning-requests*',
    emptyTitle: 'No Provisioning Requests',
    demoSampleRecord: [
      {
        id: 'req-pr-1049',
        request_id: 'req-pr-1049',
        service: 'Amazon RDS Multi-AZ',
        requester: 'dev-team',
        environment: 'STAGING',
        monthly_cost_estimate: 420.0,
        status: 'PENDING_APPROVAL',
      },
    ],
    populatedAssertionText: 'req-pr-1049',
  },
  {
    route: '/quotas',
    name: 'Quota Headroom Page',
    apiEndpoint: '/api/v1/quotas*',
    emptyTitle: 'No Quotas Discovered',
    demoSampleRecord: [
      {
        id: 'q-01',
        quota_id: 'q-01',
        service_name: 'Amazon EC2',
        quota_name: 'Running On-Demand Standard vCPU',
        region: 'us-east-1',
        current_usage: 120,
        quota_limit: 200,
        unit: 'vCPU',
        saturation_pct: 60.0,
        headroom_state: 'NORMAL',
      },
    ],
    populatedAssertionText: 'Running On-Demand Standard vCPU',
  },
  {
    route: '/remediation',
    name: 'Remediation Board Page',
    apiEndpoint: '/api/v1/remediation/tasks*',
    emptyTitle: 'No Remediation Tasks',
    demoSampleRecord: [
      {
        id: 'rem-01',
        task_id: 'rem-01',
        title: 'Terminate Unattached EBS Volume',
        service: 'EBS',
        provider: 'AWS',
        estimated_monthly_savings: 45.0,
        severity: 'HIGH',
        status: 'OPEN',
      },
    ],
    populatedAssertionText: 'Terminate Unattached EBS Volume',
  },
  {
    route: '/runtime',
    name: 'Runtime View Page',
    apiEndpoint: '/api/v1/runtime/adherence*',
    emptyTitle: 'No Runtime Resources',
    demoSampleRecord: [
      {
        id: 'rt-01',
        resource_id: 'i-0a98b7c6d5e4f3a21',
        provider: 'AWS',
        environment: 'PRODUCTION',
        declared_schedule: 'CONTINUOUS_24X7',
        current_state: 'RUNNING',
        adherence_pct: 98.5,
        out_of_hours_waste_cost: 0,
      },
    ],
    populatedAssertionText: 'i-0a98b7c6d5e4f3a21',
  },
  {
    route: '/statements',
    name: 'Showback Statements Page',
    apiEndpoint: '/api/v1/statements*',
    emptyTitle: 'No Showback Statements',
    demoSampleRecord: [
      {
        id: 'stmt-2026-09',
        statement_id: 'stmt-2026-09',
        billing_period: '2026-09',
        business_unit: 'Engineering',
        total_allocated_cost: 24500.0,
        disputed_cost: 0,
        status: 'FINALIZED',
      },
    ],
    populatedAssertionText: 'stmt-2026-09',
  },
  {
    route: '/usage',
    name: 'Usage Detail Page',
    apiEndpoint: '/api/v1/usage/metrics*',
    emptyTitle: 'No Telemetry Streams',
    demoSampleRecord: [
      {
        id: 'm-01',
        metric_name: 'CPUUtilization',
        resource_id: 'res-aws-01',
        average_value: 45.2,
        max_value: 88.0,
        unit: 'Percent',
        timestamp: '2026-10-09T08:00:00Z',
      },
    ],
    populatedAssertionText: 'CPUUtilization',
  },
  {
    route: '/users',
    name: 'Users & RBAC Page',
    apiEndpoint: '/api/v1/users*',
    emptyTitle: 'No Users Registered',
    demoSampleRecord: [
      {
        id: 'usr-admin-01',
        user_id: 'usr-admin-01',
        name: 'Admin User',
        email: 'admin@cloudlens.local',
        role: 'SUPER_ADMIN',
        status: 'ACTIVE',
      },
    ],
    populatedAssertionText: 'admin@cloudlens.local',
  },
];

test.describe('Prompt P10 — Both-Tenant Verification Suite', () => {
  test.beforeEach(async ({ page }) => {
    // Standard healthy probe
    await page.route('/api/v1/health', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          status: 'HEALTHY',
          service: 'cloudlens-api',
          version: '0.1.0-alpha',
          timestamp: '2026-10-10T02:00:00Z',
          correlation_id: 'both-tenant-verification',
        }),
      });
    });

    // Provide authenticated super admin session with all capabilities
    await page.route('/api/v1/auth/me', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          user: {
            id: 'usr-p10-tester',
            email: 'tester@enterprise.cloudlens',
            display_name: 'P10 Test Harness',
          },
          roles: ['SUPER_ADMIN'],
          capabilities: ['*'],
          tenants: [
            { id: 't-prod', name: 'Fresh Production Enterprise' },
            { id: 't-demo', name: 'Demo Enterprise' },
          ],
          current_tenant: { id: 't-prod', name: 'Fresh Production Enterprise' },
        }),
      });
    });

    // Fallback handler for auxiliary API routes so pages don't hang
    await page.route('/api/v1/**', async (route) => {
      const url = route.request().url();
      if (url.includes('/api/v1/health') || url.includes('/api/v1/auth/me')) {
        return route.fallback();
      }
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([]),
      });
    });
  });

  test('Tenant 1 (Fresh PRODUCTION): Every page renders clean EmptyState with action', async ({ page }) => {
    test.setTimeout(90000);

    // Set production tenant mode
    await page.addInitScript(() => {
      localStorage.setItem('cloudlens_is_demo', 'false');
    });

    // Mock target endpoints with empty data []
    for (const c of PAGE_TEST_CASES) {
      await page.route(c.apiEndpoint, async (route) => {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify([]),
        });
      });
    }

    // Verify empty state across all pages
    for (const c of PAGE_TEST_CASES) {
      console.log(`[PRODUCTION TEST] Visiting ${c.name} (${c.route})`);
      await page.goto(c.route, { waitUntil: 'domcontentloaded' });

      // The EmptyState component renders with role="status" and the customized empty title
      const emptyElement = page.locator('div[role="status"]', {
        hasText: new RegExp(c.emptyTitle, 'i'),
      });
      await expect(
        emptyElement.first(),
        `Expected ${c.name} on fresh production tenant to show empty state with title "${c.emptyTitle}"`
      ).toBeVisible({ timeout: 10000 });
    }
  });

  test('Tenant 2 (DEMO): Every page renders populated business records without empty state', async ({ page }) => {
    test.setTimeout(90000);

    // Set demo mode
    await page.addInitScript(() => {
      localStorage.setItem('cloudlens_is_demo', 'true');
    });

    // Mock target endpoints with populated records
    for (const c of PAGE_TEST_CASES) {
      await page.route(c.apiEndpoint, async (route) => {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(c.demoSampleRecord),
        });
      });
    }

    // Verify populated records rendered across all pages
    for (const c of PAGE_TEST_CASES) {
      console.log(`[DEMO TEST] Visiting ${c.name} (${c.route})`);
      await page.goto(c.route, { waitUntil: 'domcontentloaded' });

      // 1. Verify populated business record text is visible in page body
      await expect(
        page.locator('body'),
        `Expected ${c.name} on DEMO tenant to contain record text "${c.populatedAssertionText}"`
      ).toContainText(c.populatedAssertionText, { timeout: 10000 });

      // 2. Verify empty state is NOT displayed
      const emptyElement = page.locator('div[role="status"]', {
        hasText: new RegExp(c.emptyTitle, 'i'),
      });
      await expect(emptyElement).toHaveCount(0);
    }
  });
});
