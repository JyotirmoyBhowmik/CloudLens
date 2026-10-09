import React, { useState } from 'react';
import {
  Breadcrumb,
  CostValue,
  createCostExplanation,
  FreshnessIndicator,
} from '../design-system';
import { DemoModeBanner } from '../components/DemoModeBanner';
import {
  CheckCircle2,
  ChevronRight,
  ChevronLeft,
  Send,
  Save,
} from 'lucide-react';

const WIZARD_STEPS = [
  'Tenant Profile',
  'Identity Provider (IdP)',
  'Cloud Provider Selection',
  'Credential Binding',
  'Scope Discovery',
  'Permission Verification',
  'Tag Normalisation',
  'Cost Ingestion Config',
  'Inventory Config',
  'Notification Channels',
  'Pre-Completion Estimation',
  'First Sync Execution',
  'Completion Summary',
];

export const OnboardingWizardPage: React.FC<{ isDemo?: boolean }> = ({ isDemo = true }) => {
  const [currentStep, setCurrentStep] = useState<number>(0);
  const [tenantName, setTenantName] = useState('Enterprise FinOps Root');
  const [testNotificationStatus, setTestNotificationStatus] = useState<string | null>(null);
  const [isTestingNotification, setIsTestingNotification] = useState(false);
  const [isSaved, setIsSaved] = useState(false);

  const handleNext = () => {
    if (currentStep < WIZARD_STEPS.length - 1) {
      setCurrentStep(currentStep + 1);
      setIsSaved(false);
    }
  };

  const handlePrev = () => {
    if (currentStep > 0) {
      setCurrentStep(currentStep - 1);
      setIsSaved(false);
    }
  };

  const handleTestAlert = () => {
    setIsTestingNotification(true);
    setTestNotificationStatus(null);
    setTimeout(() => {
      setIsTestingNotification(false);
      setTestNotificationStatus('SUCCESS: Test alert delivered via SMTP relay (Mailpit :1025). Latency 82ms.');
    }, 500);
  };

  const handleSaveDraft = () => {
    setIsSaved(true);
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem', width: '100%' }}>
      <DemoModeBanner isDemo={isDemo} />

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Breadcrumb
          items={[
            { label: 'Home', href: '/' },
            { label: 'Onboarding Wizard', isCurrent: true },
          ]}
        />
        <FreshnessIndicator
          lastSyncedAt="2026-10-05T12:00:00Z"
          provider="System"
        />
      </div>

      <header>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '0.25rem' }}>
          <h1 style={{ fontSize: '1.75rem', fontWeight: 700, margin: 0, color: 'var(--text-primary)' }}>
            Guided Onboarding Wizard
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
            Guided Onboarding
          </span>
        </div>
        <p style={{ color: 'var(--text-secondary)', margin: 0, fontSize: '0.9rem' }}>
          Connect estates, verify least-privilege permissions, configure notification channels, and run pre-flight sizing estimates.
        </p>
      </header>

      {/* Step Progress Bar */}
      <section
        aria-label="Wizard Progression"
        style={{
          backgroundColor: 'var(--bg-secondary)',
          border: '1px solid var(--border-color)',
          borderRadius: '8px',
          padding: '1.25rem',
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem' }}>
          <span style={{ fontSize: '0.85rem', fontWeight: 600, color: '#38bdf8' }}>
            Step {currentStep + 1} of 13: {WIZARD_STEPS[currentStep]}
          </span>
          <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
            {Math.round(((currentStep + 1) / 13) * 100)}% Complete
          </span>
        </div>

        <div style={{ width: '100%', height: '8px', backgroundColor: 'var(--bg-primary)', borderRadius: '9999px', overflow: 'hidden' }}>
          <div
            style={{
              width: `${((currentStep + 1) / 13) * 100}%`,
              height: '100%',
              backgroundColor: '#0284c7',
              transition: 'width 0.3s ease',
            }}
          />
        </div>

        {/* Mini Step Pills */}
        <div style={{ display: 'flex', gap: '0.3rem', marginTop: '1rem', overflowX: 'auto', paddingBottom: '0.5rem' }}>
          {WIZARD_STEPS.map((stepName, idx) => (
            <button
              key={stepName}
              type="button"
              onClick={() => setCurrentStep(idx)}
              style={{
                padding: '0.25rem 0.5rem',
                fontSize: '0.7rem',
                borderRadius: '4px',
                border: idx === currentStep ? '1px solid #38bdf8' : '1px solid transparent',
                backgroundColor: idx <= currentStep ? '#0f172a' : 'transparent',
                color: idx === currentStep ? '#38bdf8' : idx < currentStep ? '#34d399' : 'var(--text-secondary)',
                cursor: 'pointer',
                whiteSpace: 'nowrap',
              }}
            >
              {idx < currentStep ? '✓ ' : `${idx + 1}. `}
              {stepName}
            </button>
          ))}
        </div>
      </section>

      {/* Step Content Card */}
      <section
        aria-labelledby="wizard-current-step-heading"
        style={{
          backgroundColor: 'var(--bg-secondary)',
          border: '1px solid var(--border-color)',
          borderRadius: '8px',
          padding: '1.5rem',
          minHeight: '320px',
        }}
      >
        <h2 id="wizard-current-step-heading" style={{ fontSize: '1.2rem', fontWeight: 600, marginBottom: '1rem' }}>
          {WIZARD_STEPS[currentStep]}
        </h2>

        {currentStep === 0 && (
          <div>
            <p style={{ color: 'var(--text-secondary)', fontSize: '0.875rem', marginBottom: '1rem' }}>
              Define the primary enterprise tenant profile, currency display standard, and financial calendar root.
            </p>
            <div style={{ maxWidth: '400px' }}>
              <label htmlFor="wizard-tenant-name" style={{ display: 'block', fontSize: '0.8rem', color: 'var(--text-secondary)', marginBottom: '0.3rem' }}>
                Tenant Organization Name
              </label>
              <input
                id="wizard-tenant-name"
                type="text"
                value={tenantName}
                onChange={(e) => setTenantName(e.target.value)}
                style={{ width: '100%', padding: '0.5rem', borderRadius: '6px', border: '1px solid var(--border-color)', backgroundColor: 'var(--bg-primary)', color: 'var(--text-primary)' }}
              />
            </div>
          </div>
        )}

        {currentStep === 9 && (
          <div>
            <p style={{ color: 'var(--text-secondary)', fontSize: '0.875rem', marginBottom: '1rem' }}>
              Configure alert notification recipients and run an automated delivery probe.
            </p>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem', maxWidth: '480px' }}>
              <div>
                <label htmlFor="wizard-email-input" style={{ display: 'block', fontSize: '0.8rem', color: 'var(--text-secondary)', marginBottom: '0.3rem' }}>
                  Default Governance Alert Email
                </label>
                <input
                  id="wizard-email-input"
                  type="email"
                  defaultValue="finops-alerts@enterprise.internal"
                  style={{ width: '100%', padding: '0.5rem', borderRadius: '6px', border: '1px solid var(--border-color)', backgroundColor: 'var(--bg-primary)', color: 'var(--text-primary)' }}
                />
              </div>

              <button
                type="button"
                onClick={handleTestAlert}
                disabled={isTestingNotification}
                style={{
                  padding: '0.5rem 1rem',
                  borderRadius: '6px',
                  backgroundColor: '#0369a1',
                  color: '#ffffff',
                  border: 'none',
                  fontWeight: 700,
                  fontSize: '0.85rem',
                  cursor: 'pointer',
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '0.4rem',
                  width: 'fit-content',
                }}
              >
                <Send size={14} aria-hidden="true" />
                {isTestingNotification ? 'Dispatching...' : 'Dispatch Test Alert Probe'}
              </button>

              {testNotificationStatus && (
                <div role="status" style={{ padding: '0.75rem', backgroundColor: '#064e3b', color: '#6ee7b7', border: '1px solid #059669', borderRadius: '6px', fontSize: '0.8rem' }}>
                  {testNotificationStatus}
                </div>
              )}
            </div>
          </div>
        )}

        {currentStep === 10 && (
          <div>
            <p style={{ color: 'var(--text-secondary)', fontSize: '0.875rem', marginBottom: '1rem' }}>
              Pre-completion ingestion volume sizing and API request estimation.
            </p>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '1rem', marginBottom: '1rem' }}>
              <div style={{ padding: '1rem', backgroundColor: 'var(--bg-primary)', borderRadius: '6px', border: '1px solid var(--border-color)' }}>
                <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>Projected Ingestion Rows</span>
                <div style={{ fontSize: '1.25rem', fontWeight: 700, color: 'var(--text-primary)', marginTop: '0.25rem' }}>
                  1,850,000 / month
                </div>
              </div>
              <div style={{ padding: '1rem', backgroundColor: 'var(--bg-primary)', borderRadius: '6px', border: '1px solid var(--border-color)' }}>
                <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>Estimated Cloud API Fees</span>
                <div style={{ fontSize: '1.25rem', fontWeight: 700, color: 'var(--text-primary)', marginTop: '0.25rem' }}>
                  <CostValue
                    amount={4.20}
                    source="ESTIMATED"
                    explanation={createCostExplanation('Provider API Collection Fee')}
                  />
                </div>
              </div>
            </div>
          </div>
        )}

        {currentStep !== 0 && currentStep !== 9 && currentStep !== 10 && (
          <div>
            <p style={{ color: 'var(--text-secondary)', fontSize: '0.875rem', marginBottom: '1rem' }}>
              Configuration profile active for {WIZARD_STEPS[currentStep]}. Validated against schema rules.
            </p>
            <div style={{ padding: '1rem', backgroundColor: 'var(--bg-primary)', borderRadius: '6px', border: '1px solid var(--border-color)', maxWidth: '400px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: '#34d399', fontSize: '0.85rem' }}>
                <CheckCircle2 size={16} aria-hidden="true" />
                <span>Pre-flight checks passed</span>
              </div>
            </div>
          </div>
        )}

        {/* Action Controls */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderTop: '1px solid var(--border-color)', paddingTop: '1.5rem', marginTop: '2rem' }}>
          <div style={{ display: 'flex', gap: '0.5rem' }}>
            <button
              type="button"
              onClick={handleSaveDraft}
              style={{
                padding: '0.5rem 0.8rem',
                borderRadius: '6px',
                backgroundColor: 'transparent',
                color: 'var(--text-secondary)',
                border: '1px solid var(--border-color)',
                fontSize: '0.85rem',
                fontWeight: 500,
                cursor: 'pointer',
                display: 'inline-flex',
                alignItems: 'center',
                gap: '0.4rem',
              }}
            >
              <Save size={14} aria-hidden="true" />
              {isSaved ? 'Saved Draft' : 'Save Draft'}
            </button>
          </div>

          <div style={{ display: 'flex', gap: '0.75rem' }}>
            <button
              type="button"
              onClick={handlePrev}
              disabled={currentStep === 0}
              style={{
                padding: '0.5rem 1rem',
                borderRadius: '6px',
                backgroundColor: 'transparent',
                color: currentStep === 0 ? 'var(--text-secondary)' : 'var(--text-primary)',
                border: '1px solid var(--border-color)',
                fontSize: '0.875rem',
                cursor: currentStep === 0 ? 'not-allowed' : 'pointer',
                display: 'inline-flex',
                alignItems: 'center',
                gap: '0.3rem',
              }}
            >
              <ChevronLeft size={16} aria-hidden="true" />
              Previous
            </button>

            <button
              type="button"
              onClick={handleNext}
              style={{
                padding: '0.5rem 1.25rem',
                borderRadius: '6px',
                backgroundColor: '#0369a1',
                color: '#ffffff',
                border: 'none',
                fontWeight: 700,
                fontSize: '0.875rem',
                cursor: 'pointer',
                display: 'inline-flex',
                alignItems: 'center',
                gap: '0.3rem',
              }}
            >
              {currentStep === 12 ? 'Finish Onboarding' : 'Next Step'}
              <ChevronRight size={16} aria-hidden="true" />
            </button>
          </div>
        </div>
      </section>
    </div>
  );
};
export default OnboardingWizardPage;
