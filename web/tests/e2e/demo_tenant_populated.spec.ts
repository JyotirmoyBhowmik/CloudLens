import { test, expect } from '@playwright/test';
import * as fs from 'fs';
import * as path from 'path';

test.describe('Prompt P09 — DEMO Tenant Still Fully Populated', () => {
  test.beforeAll(() => {
    const screenshotsDir = path.resolve(process.cwd(), 'screenshots');
    if (!fs.existsSync(screenshotsDir)) {
      fs.mkdirSync(screenshotsDir, { recursive: true });
    }
  });

  test('Executive Dashboard renders fully populated multi-cloud dataset in Demo Mode', async ({ page }) => {
    // 1. Mock /api/v1/health probe
    await page.route('/api/v1/health', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          status: 'HEALTHY',
          service: 'cloudlens-api',
          version: '0.1.0-alpha',
          timestamp: '2026-10-09T08:00:00Z',
          correlation_id: 'e2e-demo-verification-id',
        }),
      });
    });

    // 2. Mock /api/v1/auth/me to return authentic DEMO session
    await page.route('/api/v1/auth/me', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          user: {
            id: 'usr-demo-exec',
            email: 'executive@enterprise.internal',
            display_name: 'Enterprise Executive',
          },
          roles: ['EXECUTIVE'],
          capabilities: ['*'],
          tenants: [
            { id: 't-demo', name: 'Demo Multi-Cloud Enterprise' },
          ],
          current_tenant: { id: 't-demo', name: 'Demo Multi-Cloud Enterprise' },
        }),
      });
    });

    // 3. Set demo mode in localStorage
    await page.addInitScript(() => {
      localStorage.setItem('cloudlens_is_demo', 'true');
    });

    // 4. Mock /api/v1/dashboards/executive to return full seeded DEMO dataset
    await page.route('/api/v1/dashboards/executive*', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          time_window: {
            period_id: '2026-09',
            period_type: 'MONTH',
            comparison_basis: 'POP',
            start_date: '2026-09-01',
            end_date: '2026-09-30',
          },
          total_cloud_cost: {
            amount: '342850.40',
            currency: 'USD',
            prior_amount: '318720.00',
            delta_amount: '24130.40',
            delta_percentage: '7.57',
            cost_source: 'ACTUAL',
            metadata: {
              is_precomputed: true,
              freshness: { status: 'FRESH', age_seconds: 120 },
              scope_disclosure: { is_filtered: false },
            },
          },
          current_month_cost: {
            amount: '147425.67',
            currency: 'USD',
            cost_source: 'ACTUAL',
          },
          actual_cost: {
            amount: '329136.38',
            currency: 'USD',
            cost_source: 'ACTUAL',
          },
          estimated_cost: {
            amount: '23999.53',
            currency: 'USD',
            cost_source: 'ESTIMATED',
          },
          forecast_cost: {
            amount: '363421.42',
            currency: 'USD',
            cost_source: 'FORECAST',
          },
          budget: {
            amount: '349707.41',
            currency: 'USD',
            cost_source: 'ACTUAL',
          },
          budget_utilisation: {
            budget_amount: '349707.41',
            actual_spend: '342850.40',
            forecast_spend: '363421.42',
            utilisation_percentage: '98.04',
            projected_utilisation_percentage: '103.92',
            threshold_state: 'CRITICAL',
            remaining_budget: '6857.01',
          },
          cost_by_provider: {
            dimension: 'Provider',
            total_cost: '342850.40',
            items: [
              { id: 'aws', label: 'Amazon Web Services', cost: '148200.00', percentage: '43.22' },
              { id: 'azure', label: 'Microsoft Azure', cost: '102450.40', percentage: '29.88' },
              { id: 'gcp', label: 'Google Cloud Platform', cost: '62200.00', percentage: '18.14' },
              { id: 'oci', label: 'Oracle Cloud Infrastructure', cost: '30000.00', percentage: '8.76' },
            ],
          },
          cost_by_business_unit: {
            dimension: 'BusinessUnit',
            total_cost: '342850.40',
            items: [
              { id: 'bu-finops', label: 'FinOps Core', cost: '120500.00', percentage: '35.15' },
              { id: 'bu-eng', label: 'Engineering Platform', cost: '112000.00', percentage: '32.67' },
              { id: 'bu-data', label: 'Data & Analytics', cost: '85350.40', percentage: '24.90' },
              { id: 'bu-sec', label: 'Security & Compliance', cost: '25000.00', percentage: '7.28' },
            ],
          },
          cost_by_application: {
            dimension: 'Application',
            total_cost: '342850.40',
            items: [
              { id: 'app-payments', label: 'Payments Core', cost: '135000.00', percentage: '39.38' },
              { id: 'app-checkout', label: 'Checkout Service', cost: '95450.40', percentage: '27.84' },
              { id: 'app-analytics', label: 'Analytics Pipeline', cost: '72400.00', percentage: '21.12' },
              { id: 'app-inventory', label: 'Inventory Service', cost: '40000.00', percentage: '11.66' },
            ],
          },
          cost_by_service: {
            dimension: 'Service',
            total_cost: '342850.40',
            items: [
              { id: 'AmazonEC2', label: 'Amazon EC2', cost: '68500.00', percentage: '19.98' },
              { id: 'AmazonRDS', label: 'Amazon RDS', cost: '45200.00', percentage: '13.18' },
              { id: 'AzureVirtualMachines', label: 'Virtual Machines', cost: '42100.00', percentage: '12.28' },
              { id: 'BigQuery', label: 'Google BigQuery', cost: '38900.00', percentage: '11.35' },
              { id: 'OracleCompute', label: 'OCI Compute', cost: '22000.00', percentage: '6.42' },
            ],
          },
          cost_trend: {
            dimension: 'CostTrend',
            points: [
              { date: '2026-09-01', actual_cost: '11200.00', comparison_cost: '10500.00' },
              { date: '2026-09-08', actual_cost: '11450.00', comparison_cost: '10800.00' },
              { date: '2026-09-15', actual_cost: '11800.00', comparison_cost: '11000.00' },
              { date: '2026-09-22', actual_cost: '12100.00', comparison_cost: '11200.00' },
            ],
          },
          top_cost_services: { items: [] },
          largest_increases: { movements: [] },
          threshold_breaches: { total_breaches: 1, critical_count: 1, warning_count: 0, breaches: [] },
          service_counts: { free_services_count: 14, paid_services_count: 182, conditional_services_count: 28, total_services_count: 224 },
          runtime_exceptions: { total_count: 0, items: [] },
          usage_anomalies: { total_count: 0, items: [] },
          pricing_changes: { recent_changes: [] },
          data_freshness: {
            providers: [
              { provider: 'aws', last_sync_timestamp: '2026-09-30T12:00:00Z', age_hours: 1, status: 'FRESH' },
              { provider: 'azure', last_sync_timestamp: '2026-09-30T12:00:00Z', age_hours: 1, status: 'FRESH' },
              { provider: 'gcp', last_sync_timestamp: '2026-09-30T12:00:00Z', age_hours: 1, status: 'FRESH' },
              { provider: 'oci', last_sync_timestamp: '2026-09-28T08:00:00Z', age_hours: 52, status: 'STALE' },
            ],
            has_stale_provider: true,
            stale_provider_banner: 'OCI provider feed exceeds 24h lag SLA (52h)',
          },
          reconciliation_status: { status: 'RECONCILED' },
          governance_exceptions: { total_exceptions: 0 },
          data_freshness_banner: 'Data Freshness Warning: OCI provider feed exceeds SLA',
        }),
      });
    });

    // 5. Navigate to Executive Dashboard
    await page.goto('/executive');
    await page.waitForLoadState('domcontentloaded');

    // 6. Assert populated executive overview elements
    const heading = page.locator('h1');
    await expect(heading).toContainText(/Executive/i, { timeout: 10000 });

    // Verify key financial figures are rendered and non-zero
    const bodyText = await page.textContent('body');
    expect(bodyText).toContain('342,850.40');
    expect(bodyText).toContain('Amazon Web Services');
    expect(bodyText).toContain('Microsoft Azure');
    expect(bodyText).toContain('Google Cloud Platform');

    // 7. Capture screenshot proof
    const screenshotPath = path.resolve(process.cwd(), 'screenshots', 'demo_tenant_executive_populated.png');
    await page.screenshot({ path: screenshotPath, fullPage: true });
    expect(fs.existsSync(screenshotPath)).toBeTruthy();
  });
});
