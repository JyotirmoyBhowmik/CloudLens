import React, { useState, useEffect } from 'react';
import {
  Breadcrumb,
  CostValue,
  createCostExplanation,
  NullValue,
  FreshnessIndicator,
} from '../design-system';
import { DemoModeBanner } from '../components/DemoModeBanner';
import { Calculator } from 'lucide-react';

interface Scenario {
  id: string;
  name: string;
  provider: string;
  service: string;
  region: string;
  instanceType: string;
  monthlyCost: number | null;
  pricingModel: 'ON_DEMAND' | 'RESERVED_1YR' | 'SPOT' | 'SAVINGS_PLAN';
  source: 'ESTIMATED' | 'ACTUAL' | 'FORECAST';
  notes: string;
}

export const CostEstimatorPage: React.FC<{ isDemo?: boolean }> = ({ isDemo = true }) => {
  const [provider, setProvider] = useState<string>('aws');
  const [service, setService] = useState<string>('AmazonEC2');
  const [region, setRegion] = useState<string>('us-east-1');
  const [instanceType, setInstanceType] = useState<string>('m5.xlarge');
  const [quantity, setQuantity] = useState<number>(4);
  const [hoursPerMonth, setHoursPerMonth] = useState<number>(730);
  const [pricingModel] = useState<string>('ON_DEMAND');

  const [scenarios, setScenarios] = useState<Scenario[]>([
    {
      id: 'sc-1',
      name: 'Baseline On-Demand Fleet',
      provider: 'AWS',
      service: 'Amazon EC2',
      region: 'us-east-1',
      instanceType: 'm5.xlarge (4 vCPU, 16 GiB)',
      monthlyCost: 560.64,
      pricingModel: 'ON_DEMAND',
      source: 'ESTIMATED',
      notes: 'Standard pay-as-you-go rate without commitment',
    },
    {
      id: 'sc-2',
      name: '1-Year Compute Savings Plan',
      provider: 'AWS',
      service: 'Amazon EC2',
      region: 'us-east-1',
      instanceType: 'm5.xlarge (4 vCPU, 16 GiB)',
      monthlyCost: 381.24,
      pricingModel: 'SAVINGS_PLAN',
      source: 'ESTIMATED',
      notes: '32% discount for 1-year partial upfront commitment',
    },
    {
      id: 'sc-3',
      name: 'Graviton Architecture (ARM64)',
      provider: 'AWS',
      service: 'Amazon EC2',
      region: 'us-east-1',
      instanceType: 'm6g.xlarge (4 vCPU, 16 GiB)',
      monthlyCost: 322.37,
      pricingModel: 'SAVINGS_PLAN',
      source: 'ESTIMATED',
      notes: '20% lower raw cost + 32% commitment discount',
    },
  ]);

  useEffect(() => {
    if (!isDemo) {
      setScenarios([]);
    }
  }, [isDemo]);

  const estimatedUnitPrice = 0.192;
  const calculatedMonthly = quantity * hoursPerMonth * estimatedUnitPrice;

  const handleAddScenario = () => {
    const newSc: Scenario = {
      id: `sc-${Date.now()}`,
      name: `Custom ${provider.toUpperCase()} ${instanceType}`,
      provider: provider.toUpperCase(),
      service,
      region,
      instanceType,
      monthlyCost: calculatedMonthly,
      pricingModel: pricingModel as any,
      source: 'ESTIMATED',
      notes: `${quantity} units @ ${hoursPerMonth}h/mo under ${pricingModel}`,
    };
    setScenarios([...scenarios, newSc]);
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem', width: '100%' }}>
      <DemoModeBanner isDemo={isDemo} />

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Breadcrumb
          items={[
            { label: 'Home', href: '/' },
            { label: 'Cost Estimator & Scenarios', isCurrent: true },
          ]}
        />
        <FreshnessIndicator lastSyncedAt="2026-10-05T12:00:00Z" provider="Multi-Cloud" />
      </div>

      <header>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '0.25rem' }}>
          <h1 style={{ fontSize: '1.75rem', fontWeight: 700, margin: 0, color: 'var(--text-primary)' }}>
            S-21: Cost Estimator & Scenario Compare
          </h1>
          <span
            style={{
              padding: '0.2rem 0.6rem',
              borderRadius: '9999px',
              backgroundColor: 'rgba(56, 189, 248, 0.15)',
              border: '1px solid rgba(56, 189, 248, 0.3)',
              color: '#38bdf8',
              fontSize: '0.75rem',
              fontWeight: 600,
            }}
          >
            Addendum B / Prompt 55
          </span>
        </div>
        <p style={{ color: 'var(--text-secondary)', margin: 0, fontSize: '0.9rem' }}>
          Model multi-cloud architecture pre-deployment sizing, compare commitment alternatives side-by-side, and quantify savings deltas.
        </p>
      </header>

      {/* Sizing & Modeling Configuration Card */}
      <section
        aria-labelledby="estimator-builder-heading"
        style={{
          backgroundColor: 'var(--bg-secondary)',
          border: '1px solid var(--border-color)',
          borderRadius: '8px',
          padding: '1.25rem',
        }}
      >
        <h2 id="estimator-builder-heading" style={{ fontSize: '1.1rem', fontWeight: 600, marginBottom: '1rem' }}>
          Estimate Configuration Builder
        </h2>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '1rem', marginBottom: '1.25rem' }}>
          <div>
            <label htmlFor="est-provider" style={{ display: 'block', fontSize: '0.8rem', color: 'var(--text-secondary)', marginBottom: '0.3rem' }}>
              Cloud Provider
            </label>
            <select
              id="est-provider"
              value={provider}
              onChange={(e) => setProvider(e.target.value)}
              style={{ width: '100%', padding: '0.45rem', borderRadius: '6px', border: '1px solid var(--border-color)', backgroundColor: 'var(--bg-primary)', color: 'var(--text-primary)' }}
            >
              <option value="aws">AWS (Amazon Web Services)</option>
              <option value="azure">Azure (Microsoft)</option>
              <option value="gcp">GCP (Google Cloud)</option>
              <option value="oci">OCI (Oracle Cloud)</option>
            </select>
          </div>

          <div>
            <label htmlFor="est-service" style={{ display: 'block', fontSize: '0.8rem', color: 'var(--text-secondary)', marginBottom: '0.3rem' }}>
              Cloud Service
            </label>
            <select
              id="est-service"
              value={service}
              onChange={(e) => setService(e.target.value)}
              style={{ width: '100%', padding: '0.45rem', borderRadius: '6px', border: '1px solid var(--border-color)', backgroundColor: 'var(--bg-primary)', color: 'var(--text-primary)' }}
            >
              <option value="AmazonEC2">Elastic Compute (VM / Instances)</option>
              <option value="AmazonRDS">Managed Database (RDS / SQL)</option>
              <option value="AmazonS3">Object Storage (S3 / Blob)</option>
            </select>
          </div>

          <div>
            <label htmlFor="est-region" style={{ display: 'block', fontSize: '0.8rem', color: 'var(--text-secondary)', marginBottom: '0.3rem' }}>
              Region
            </label>
            <input
              id="est-region"
              type="text"
              value={region}
              onChange={(e) => setRegion(e.target.value)}
              aria-label="Datacenter region"
              style={{ width: '100%', padding: '0.45rem', borderRadius: '6px', border: '1px solid var(--border-color)', backgroundColor: 'var(--bg-primary)', color: 'var(--text-primary)' }}
            />
          </div>

          <div>
            <label htmlFor="est-size" style={{ display: 'block', fontSize: '0.8rem', color: 'var(--text-secondary)', marginBottom: '0.3rem' }}>
              SKU Size / Instance Type
            </label>
            <input
              id="est-size"
              type="text"
              value={instanceType}
              onChange={(e) => setInstanceType(e.target.value)}
              aria-label="Instance type or SKU size"
              style={{ width: '100%', padding: '0.45rem', borderRadius: '6px', border: '1px solid var(--border-color)', backgroundColor: 'var(--bg-primary)', color: 'var(--text-primary)' }}
            />
          </div>

          <div>
            <label htmlFor="est-qty" style={{ display: 'block', fontSize: '0.8rem', color: 'var(--text-secondary)', marginBottom: '0.3rem' }}>
              Quantity (Units)
            </label>
            <input
              id="est-qty"
              type="number"
              min="1"
              value={quantity}
              onChange={(e) => setQuantity(parseInt(e.target.value) || 1)}
              aria-label="Quantity of units"
              style={{ width: '100%', padding: '0.45rem', borderRadius: '6px', border: '1px solid var(--border-color)', backgroundColor: 'var(--bg-primary)', color: 'var(--text-primary)' }}
            />
          </div>

          <div>
            <label htmlFor="est-hours" style={{ display: 'block', fontSize: '0.8rem', color: 'var(--text-secondary)', marginBottom: '0.3rem' }}>
              Monthly Hours
            </label>
            <input
              id="est-hours"
              type="number"
              min="1"
              max="744"
              value={hoursPerMonth}
              onChange={(e) => setHoursPerMonth(parseInt(e.target.value) || 730)}
              aria-label="Monthly runtime hours"
              style={{ width: '100%', padding: '0.45rem', borderRadius: '6px', border: '1px solid var(--border-color)', backgroundColor: 'var(--bg-primary)', color: 'var(--text-primary)' }}
            />
          </div>
        </div>

        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderTop: '1px solid var(--border-color)', paddingTop: '1rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
            <span style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>Calculated Sizing Cost:</span>
            <CostValue
              amount={calculatedMonthly}
              source="ESTIMATED"
              explanation={createCostExplanation('Monthly Estimated Cost', {
                pricingSource: 'Cloud Provider Retail Rate Card',
                region,
              })}
            />
          </div>

          <button
            type="button"
            onClick={handleAddScenario}
            style={{
              padding: '0.5rem 1rem',
              borderRadius: '6px',
              backgroundColor: '#0369a1',
              color: '#ffffff',
              fontWeight: 700,
              fontSize: '0.875rem',
              border: 'none',
              cursor: 'pointer',
              display: 'inline-flex',
              alignItems: 'center',
              gap: '0.4rem',
            }}
          >
            <Calculator size={14} aria-hidden="true" />
            Add to Scenario Comparison
          </button>
        </div>
      </section>

      {/* Side-by-Side Comparison Section */}
      <section aria-labelledby="scenario-comparison-heading">
        <h2 id="scenario-comparison-heading" style={{ fontSize: '1.2rem', fontWeight: 600, marginBottom: '0.75rem' }}>
          Scenario Comparison Matrix
        </h2>

        {scenarios.length === 0 ? (
          <div
            style={{
              padding: '2.5rem',
              backgroundColor: 'var(--bg-secondary)',
              borderRadius: '8px',
              border: '1px dashed var(--border-color)',
              textAlign: 'center',
            }}
          >
            <p style={{ color: 'var(--text-secondary)', marginBottom: '0.5rem' }}>
              No scenario estimates configured for this scope.
            </p>
            <div style={{ display: 'inline-flex', alignItems: 'center', gap: '0.5rem' }}>
              <span style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>Empty State Status:</span>
              <NullValue state="NO_DATA" />
            </div>
          </div>
        ) : (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: '1rem' }}>
            {scenarios.map((sc, index) => {
              const baselineCost = scenarios[0]?.monthlyCost || 1;
              const savingsDelta = (sc.monthlyCost !== null && sc.monthlyCost < baselineCost)
                ? baselineCost - sc.monthlyCost
                : 0;

              return (
                <article
                  key={sc.id}
                  style={{
                    backgroundColor: 'var(--bg-secondary)',
                    border: `1px solid ${index === 0 ? '#38bdf8' : 'var(--border-color)'}`,
                    borderRadius: '8px',
                    padding: '1.25rem',
                    display: 'flex',
                    flexDirection: 'column',
                    justifyContent: 'space-between',
                  }}
                >
                  <div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '0.5rem' }}>
                      <h3 style={{ fontSize: '1rem', fontWeight: 600, margin: 0, color: 'var(--text-primary)' }}>
                        {sc.name}
                      </h3>
                      {index === 0 ? (
                        <span style={{ fontSize: '0.7rem', padding: '0.1rem 0.4rem', borderRadius: '4px', backgroundColor: '#0369a1', color: '#e0f2fe' }}>
                          Baseline
                        </span>
                      ) : (
                        <span style={{ fontSize: '0.7rem', padding: '0.1rem 0.4rem', borderRadius: '4px', backgroundColor: '#065f46', color: '#a7f3d0' }}>
                          Alternative #{index}
                        </span>
                      )}
                    </div>

                    <p style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', margin: '0 0 0.75rem 0' }}>
                      {sc.notes}
                    </p>

                    <div style={{ fontSize: '0.8rem', display: 'flex', flexDirection: 'column', gap: '0.35rem', marginBottom: '1rem' }}>
                      <div><strong style={{ color: 'var(--text-secondary)' }}>Provider:</strong> {sc.provider}</div>
                      <div><strong style={{ color: 'var(--text-secondary)' }}>Service:</strong> {sc.service}</div>
                      <div><strong style={{ color: 'var(--text-secondary)' }}>Size:</strong> {sc.instanceType}</div>
                      <div><strong style={{ color: 'var(--text-secondary)' }}>Pricing Model:</strong> {sc.pricingModel}</div>
                    </div>
                  </div>

                  <div style={{ borderTop: '1px solid var(--border-color)', paddingTop: '0.75rem' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.4rem' }}>
                      <span style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>Monthly Cost:</span>
                      <CostValue
                        amount={sc.monthlyCost}
                        source={sc.source}
                        explanation={createCostExplanation('Scenario Monthly Projection', {
                          pricingSource: 'Retail Rate Cards / FOCUS 1.0',
                          region: sc.region,
                        })}
                      />
                    </div>

                    {savingsDelta > 0 && (
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '0.8rem', color: '#34d399' }}>
                        <span>Projected Savings:</span>
                        <span>
                          -${savingsDelta.toFixed(2)}/mo ({((savingsDelta / baselineCost) * 100).toFixed(1)}%)
                        </span>
                      </div>
                    )}
                  </div>
                </article>
              );
            })}
          </div>
        )}
      </section>
    </div>
  );
};
export default CostEstimatorPage;
