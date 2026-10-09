import React, { useState } from 'react';
import {
  Breadcrumb,
  FreshnessIndicator,
} from '../design-system';
import { DemoModeBanner } from '../components/DemoModeBanner';
import { FileText, Download, CheckCircle2, Search } from 'lucide-react';

interface ReportTemplateItem {
  id: string;
  code: string;
  name: string;
  category: string;
  format: 'PDF' | 'CSV' | 'PARQUET' | 'JSON';
  lastRun: string;
  status: 'READY' | 'GENERATING';
}

const STANDARD_REPORTS: ReportTemplateItem[] = [
  { id: 'rpt-01', code: 'RPT-01', name: 'Monthly Multi-Cloud Billed Spend Summary', category: 'Financial', format: 'PDF', lastRun: '2026-10-01T00:00:00Z', status: 'READY' },
  { id: 'rpt-02', code: 'RPT-02', name: 'Shared Cost Allocation & Apportionment Pack', category: 'Finance', format: 'CSV', lastRun: '2026-10-01T00:00:00Z', status: 'READY' },
  { id: 'rpt-03', code: 'RPT-03', name: 'Actionable Waste & Idle Resource Inventory', category: 'FinOps', format: 'CSV', lastRun: '2026-10-05T06:00:00Z', status: 'READY' },
  { id: 'rpt-04', code: 'RPT-04', name: 'Tag Governance & Ownership Missingness Audit', category: 'Governance', format: 'PDF', lastRun: '2026-10-04T12:00:00Z', status: 'READY' },
  { id: 'rpt-05', code: 'RPT-05', name: 'Commitment Expiration & Renewal Pipeline', category: 'FinOps', format: 'CSV', lastRun: '2026-10-05T12:00:00Z', status: 'READY' },
  { id: 'rpt-06', code: 'RPT-06', name: 'Service Quota & Headroom Saturation Forecast', category: 'Operations', format: 'CSV', lastRun: '2026-10-05T12:00:00Z', status: 'READY' },
  { id: 'rpt-07', code: 'RPT-07', name: 'Periodic Identity & Scope Access Review', category: 'Security', format: 'PDF', lastRun: '2026-10-01T00:00:00Z', status: 'READY' },
  { id: 'rpt-08', code: 'RPT-08', name: 'FOCUS 1.0 Normalized Star-Schema Conformed Extract', category: 'Analytics', format: 'PARQUET', lastRun: '2026-10-05T00:00:00Z', status: 'READY' },
];

export const ReportsPage: React.FC<{ isDemo?: boolean }> = ({ isDemo = true }) => {
  const [reports] = useState<ReportTemplateItem[]>(STANDARD_REPORTS);
  const [search, setSearch] = useState('');

  const filtered = reports.filter((r) =>
    `${r.code} ${r.name} ${r.category}`.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem', width: '100%' }}>
      <DemoModeBanner isDemo={isDemo} />

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Breadcrumb
          items={[
            { label: 'Home', href: '/' },
            { label: 'Reports & Exports', isCurrent: true },
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
            Standard Reports & Export Center
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
            16 Standard Reports / Cryptographic Provenance
          </span>
        </div>
        <p style={{ color: 'var(--text-secondary)', margin: 0, fontSize: '0.9rem' }}>
          Curated governance reports and analytical data export packages with verifiable cryptographic provenance.
        </p>
      </header>

      {/* Reports Directory */}
      <section
        aria-labelledby="reports-list-heading"
        style={{
          backgroundColor: 'var(--bg-secondary)',
          border: '1px solid var(--border-color)',
          borderRadius: '8px',
          padding: '1.25rem',
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
          <h2 id="reports-list-heading" style={{ fontSize: '1.1rem', fontWeight: 600, margin: 0 }}>
            Standard Report Library
          </h2>

          <div style={{ position: 'relative' }}>
            <Search size={14} style={{ position: 'absolute', left: '0.6rem', top: '0.6rem', color: 'var(--text-secondary)' }} aria-hidden="true" />
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search reports..."
              aria-label="Search reports"
              style={{
                padding: '0.4rem 0.6rem 0.4rem 2rem',
                fontSize: '0.8rem',
                borderRadius: '6px',
                border: '1px solid var(--border-color)',
                backgroundColor: 'var(--bg-primary)',
                color: 'var(--text-primary)',
              }}
            />
          </div>
        </div>

        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '0.85rem' }}>
            <thead>
              <tr style={{ borderBottom: '1px solid var(--border-color)', color: 'var(--text-secondary)' }}>
                <th style={{ padding: '0.6rem' }}>Code & Report Name</th>
                <th style={{ padding: '0.6rem' }}>Category</th>
                <th style={{ padding: '0.6rem' }}>Export Format</th>
                <th style={{ padding: '0.6rem' }}>Last Executed</th>
                <th style={{ padding: '0.6rem' }}>Status</th>
                <th style={{ padding: '0.6rem' }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((r) => (
                <tr key={r.id} style={{ borderBottom: '1px solid var(--border-color)' }}>
                  <td style={{ padding: '0.75rem 0.6rem' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                      <FileText size={16} style={{ color: '#38bdf8' }} aria-hidden="true" />
                      <div>
                        <strong>{r.name}</strong>
                        <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>{r.code}</div>
                      </div>
                    </div>
                  </td>
                  <td style={{ padding: '0.75rem 0.6rem' }}>
                    <code>{r.category}</code>
                  </td>
                  <td style={{ padding: '0.75rem 0.6rem' }}>
                    <span style={{ fontSize: '0.75rem', padding: '0.15rem 0.4rem', borderRadius: '4px', backgroundColor: '#1e293b', color: '#94a3b8' }}>
                      {r.format}
                    </span>
                  </td>
                  <td style={{ padding: '0.75rem 0.6rem', fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
                    {new Date(r.lastRun).toLocaleDateString()}
                  </td>
                  <td style={{ padding: '0.75rem 0.6rem' }}>
                    <span style={{ display: 'inline-flex', alignItems: 'center', gap: '0.2rem', color: '#34d399', fontSize: '0.75rem', fontWeight: 600 }}>
                      <CheckCircle2 size={12} aria-hidden="true" /> READY
                    </span>
                  </td>
                  <td style={{ padding: '0.75rem 0.6rem' }}>
                    <button
                      type="button"
                      aria-label={`Export report ${r.code}`}
                      style={{
                        padding: '0.3rem 0.6rem',
                        borderRadius: '4px',
                        backgroundColor: '#0369a1',
                        color: '#ffffff',
                        border: 'none',
                        fontSize: '0.75rem',
                        fontWeight: 700,
                        cursor: 'pointer',
                        display: 'inline-flex',
                        alignItems: 'center',
                        gap: '0.3rem',
                      }}
                    >
                      <Download size={12} aria-hidden="true" />
                      Export
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
};
export default ReportsPage;
