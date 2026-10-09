import React, { useState } from 'react';
import {
  Breadcrumb,
  FreshnessIndicator,
} from '../design-system';
import { DemoModeBanner } from '../components/DemoModeBanner';
import { Settings, Save, Bell, Key } from 'lucide-react';

export const SettingsPage: React.FC<{ isDemo?: boolean }> = ({ isDemo = true }) => {
  const [currency, setCurrency] = useState('USD');
  const [retentionDays, setRetentionDays] = useState(365);
  const [smtpServer, setSmtpServer] = useState('mailpit.internal');
  const [smtpPort, setSmtpPort] = useState(1025);
  const [openBaoMount, setOpenBaoMount] = useState('secret/data/cloudlens');
  const [isSaved, setIsSaved] = useState(false);

  const handleSave = (e: React.FormEvent) => {
    e.preventDefault();
    setIsSaved(true);
    setTimeout(() => setIsSaved(false), 3000);
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem', width: '100%' }}>
      <DemoModeBanner isDemo={isDemo} />

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Breadcrumb
          items={[
            { label: 'Home', href: '/' },
            { label: 'Tenant Settings', isCurrent: true },
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
            Tenant Configuration & Platform Settings
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
            Secure Configuration
          </span>
        </div>
        <p style={{ color: 'var(--text-secondary)', margin: 0, fontSize: '0.9rem' }}>
          Platform global parameters, currency handling, secret store paths, and notification infrastructure.
        </p>
      </header>

      {isSaved && (
        <div role="status" style={{ padding: '0.75rem 1rem', backgroundColor: '#064e3b', color: '#6ee7b7', border: '1px solid #059669', borderRadius: '6px', fontSize: '0.85rem' }}>
          Settings successfully persisted to master configuration registry.
        </div>
      )}

      <form onSubmit={handleSave} style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem', maxWidth: '800px' }}>
        {/* Currency & Financial Preferences */}
        <section
          style={{
            backgroundColor: 'var(--bg-secondary)',
            border: '1px solid var(--border-color)',
            borderRadius: '8px',
            padding: '1.25rem',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '1rem', color: '#38bdf8' }}>
            <Settings size={18} aria-hidden="true" />
            <h2 style={{ fontSize: '1.1rem', fontWeight: 600, margin: 0, color: 'var(--text-primary)' }}>
              Financial Standards & Display
            </h2>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: '1rem' }}>
            <div>
              <label htmlFor="settings-currency" style={{ display: 'block', fontSize: '0.8rem', color: 'var(--text-secondary)', marginBottom: '0.3rem' }}>
                Default Currency Standard (ISO 4217)
              </label>
              <select
                id="settings-currency"
                value={currency}
                onChange={(e) => setCurrency(e.target.value)}
                style={{ width: '100%', padding: '0.45rem', borderRadius: '6px', border: '1px solid var(--border-color)', backgroundColor: 'var(--bg-primary)', color: 'var(--text-primary)' }}
              >
                <option value="USD">USD ($) - US Dollar</option>
                <option value="EUR">EUR (€) - Euro</option>
                <option value="GBP">GBP (£) - British Pound</option>
                <option value="JPY">JPY (¥) - Japanese Yen</option>
              </select>
            </div>

            <div>
              <label htmlFor="settings-retention" style={{ display: 'block', fontSize: '0.8rem', color: 'var(--text-secondary)', marginBottom: '0.3rem' }}>
                Detailed Cost Fact Retention (Days)
              </label>
              <input
                id="settings-retention"
                type="number"
                value={retentionDays}
                onChange={(e) => setRetentionDays(parseInt(e.target.value) || 365)}
                style={{ width: '100%', padding: '0.45rem', borderRadius: '6px', border: '1px solid var(--border-color)', backgroundColor: 'var(--bg-primary)', color: 'var(--text-primary)' }}
              />
            </div>
          </div>
        </section>

        {/* Security & Secret Store */}
        <section
          style={{
            backgroundColor: 'var(--bg-secondary)',
            border: '1px solid var(--border-color)',
            borderRadius: '8px',
            padding: '1.25rem',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '1rem', color: '#10b981' }}>
            <Key size={18} aria-hidden="true" />
            <h2 style={{ fontSize: '1.1rem', fontWeight: 600, margin: 0, color: 'var(--text-primary)' }}>
              OpenBao Secret Engine Reference
            </h2>
          </div>

          <div>
            <label htmlFor="settings-openbao" style={{ display: 'block', fontSize: '0.8rem', color: 'var(--text-secondary)', marginBottom: '0.3rem' }}>
              Secret Mount Path (Zero plaintext passwords)
            </label>
            <input
              id="settings-openbao"
              type="text"
              value={openBaoMount}
              onChange={(e) => setOpenBaoMount(e.target.value)}
              style={{ width: '100%', padding: '0.45rem', borderRadius: '6px', border: '1px solid var(--border-color)', backgroundColor: 'var(--bg-primary)', color: 'var(--text-primary)' }}
            />
          </div>
        </section>

        {/* Notifications */}
        <section
          style={{
            backgroundColor: 'var(--bg-secondary)',
            border: '1px solid var(--border-color)',
            borderRadius: '8px',
            padding: '1.25rem',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '1rem', color: '#f59e0b' }}>
            <Bell size={18} aria-hidden="true" />
            <h2 style={{ fontSize: '1.1rem', fontWeight: 600, margin: 0, color: 'var(--text-primary)' }}>
              Notification SMTP Infrastructure
            </h2>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: '1rem' }}>
            <div>
              <label htmlFor="settings-smtp-host" style={{ display: 'block', fontSize: '0.8rem', color: 'var(--text-secondary)', marginBottom: '0.3rem' }}>
                SMTP Relay Host
              </label>
              <input
                id="settings-smtp-host"
                type="text"
                value={smtpServer}
                onChange={(e) => setSmtpServer(e.target.value)}
                style={{ width: '100%', padding: '0.45rem', borderRadius: '6px', border: '1px solid var(--border-color)', backgroundColor: 'var(--bg-primary)', color: 'var(--text-primary)' }}
              />
            </div>

            <div>
              <label htmlFor="settings-smtp-port" style={{ display: 'block', fontSize: '0.8rem', color: 'var(--text-secondary)', marginBottom: '0.3rem' }}>
                SMTP Port
              </label>
              <input
                id="settings-smtp-port"
                type="number"
                value={smtpPort}
                onChange={(e) => setSmtpPort(parseInt(e.target.value) || 1025)}
                style={{ width: '100%', padding: '0.45rem', borderRadius: '6px', border: '1px solid var(--border-color)', backgroundColor: 'var(--bg-primary)', color: 'var(--text-primary)' }}
              />
            </div>
          </div>
        </section>

        <button
          type="submit"
          style={{
            padding: '0.65rem 1.5rem',
            borderRadius: '6px',
            backgroundColor: '#0369a1',
            color: '#ffffff',
            border: 'none',
            fontWeight: 700,
            fontSize: '0.875rem',
            cursor: 'pointer',
            display: 'inline-flex',
            alignItems: 'center',
            gap: '0.4rem',
            width: 'fit-content',
          }}
        >
          <Save size={16} aria-hidden="true" />
          Save Platform Settings
        </button>
      </form>
    </div>
  );
};
export default SettingsPage;
