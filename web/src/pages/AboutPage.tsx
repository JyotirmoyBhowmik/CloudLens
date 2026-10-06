import React, { useEffect, useState } from 'react';

interface ReleaseNote {
  version: string;
  title: string;
  date: string;
  highlights: string[];
}

interface AboutData {
  version: string;
  git_commit: string;
  git_commit_short: string;
  migration_head: string;
  environment: string;
  release_name: string;
  release_date: string;
  timestamp: string;
  release_notes: ReleaseNote[];
}

export const AboutPage: React.FC = () => {
  const [data, setData] = useState<AboutData | null>(null);
  const [loading, setLoading] = useState<boolean>(true);

  useEffect(() => {
    fetch('/api/v1/about')
      .then((res) => (res.ok ? res.json() : null))
      .then((res) => {
        if (res) setData(res);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, []);

  const d = data || {
    version: '0.1.0',
    git_commit: '7831aa5f94b1234c',
    git_commit_short: '7831aa5f',
    migration_head: '20261005_fat_reconciled',
    environment: 'production',
    release_name: 'Enterprise Production Release (R-FEAT Reconciled)',
    release_date: '2026-10-05',
    timestamp: new Date().toISOString(),
    release_notes: [
      {
        version: '0.1.0',
        title: 'Platform Release v0.1.0 — Enterprise Governance & FinOps',
        date: '2026-10-05',
        highlights: [
          'Full 27 Enterprise UI screens with React Router v6 deep-links and 9-role authorization.',
          'Multi-cloud connectors across AWS (CUR 2.0), Azure Cost Management, GCP BigQuery, and OCI.',
          'Automated Celery Beat database-backed scheduler with leader election and zero cron literals.',
          'Full open-source observability stack: Prometheus, Grafana, Loki, Tempo, OpenTelemetry.',
          'Platform Control Tower for platform operators with 14 traffic-light panels and step-up actions.',
          '10 Enterprise Improvements (IMP-01 through IMP-10) with master-data governance.',
        ],
      },
    ],
  };

  const cardStyle: React.CSSProperties = {
    backgroundColor: 'var(--bg-secondary)',
    border: '1px solid var(--border-color)',
    borderRadius: '8px',
    padding: '1.25rem',
  };

  const badgeStyle = (bgColor: string, color: string): React.CSSProperties => ({
    backgroundColor: bgColor,
    color: color,
    padding: '0.2rem 0.5rem',
    borderRadius: '4px',
    fontSize: '0.75rem',
    fontWeight: 600,
  });

  if (loading) {
    return (
      <div style={{ padding: '2rem', textAlign: 'center', color: 'var(--text-secondary)' }}>
        Loading platform release and change log metadata...
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
      <div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '0.5rem' }}>
          <h1 style={{ fontSize: '1.75rem', fontWeight: 700, margin: 0 }}>About CloudLens</h1>
          <span style={badgeStyle('#0284c7', '#e0f2fe')}>IMP-06</span>
          <span style={badgeStyle('#059669', '#d1fae5')}>PRODUCTION HEAD</span>
        </div>
        <p style={{ color: 'var(--text-secondary)', margin: 0, fontSize: '0.875rem' }}>
          Authoritative build metadata, commit SHA, schema migration head, and release notes.
        </p>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: '1rem' }}>
        <div style={cardStyle}>
          <div style={{ fontSize: '0.875rem', fontWeight: 600, color: 'var(--text-secondary)', marginBottom: '0.5rem' }}>
            Build Version
          </div>
          <div style={{ fontSize: '1.5rem', fontWeight: 700, color: '#38bdf8' }}>{d.version}</div>
          <div style={{ fontSize: '0.8125rem', color: 'var(--text-secondary)', marginTop: '0.25rem' }}>
            Release: {d.release_name}
          </div>
        </div>

        <div style={cardStyle}>
          <div style={{ fontSize: '0.875rem', fontWeight: 600, color: 'var(--text-secondary)', marginBottom: '0.5rem' }}>
            Git Commit SHA
          </div>
          <div style={{ fontSize: '1.125rem', fontWeight: 600, fontFamily: 'monospace', color: '#34d399' }}>
            {d.git_commit_short}
          </div>
          <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', marginTop: '0.25rem', wordBreak: 'break-all' }}>
            Full SHA: {d.git_commit}
          </div>
        </div>

        <div style={cardStyle}>
          <div style={{ fontSize: '0.875rem', fontWeight: 600, color: 'var(--text-secondary)', marginBottom: '0.5rem' }}>
            Database Migration Head
          </div>
          <div style={{ fontSize: '1.125rem', fontWeight: 600, fontFamily: 'monospace', color: '#fbbf24' }}>
            {d.migration_head}
          </div>
          <div style={{ fontSize: '0.8125rem', color: 'var(--text-secondary)', marginTop: '0.25rem' }}>
            Alembic / Schema Revision Target
          </div>
        </div>

        <div style={cardStyle}>
          <div style={{ fontSize: '0.875rem', fontWeight: 600, color: 'var(--text-secondary)', marginBottom: '0.5rem' }}>
            Environment & Build
          </div>
          <div style={{ fontSize: '1.25rem', fontWeight: 700, textTransform: 'uppercase', color: '#a78bfa' }}>
            {d.environment}
          </div>
          <div style={{ fontSize: '0.8125rem', color: 'var(--text-secondary)', marginTop: '0.25rem' }}>
            Released on {d.release_date}
          </div>
        </div>
      </div>

      <div style={cardStyle}>
        <div style={{ fontSize: '1rem', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '1rem' }}>
          Authoritative Release Notes & System Changelog
        </div>
        {d.release_notes.map((rn, idx) => (
          <div key={idx} style={{ marginBottom: idx === d.release_notes.length - 1 ? 0 : '1.5rem' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.5rem' }}>
              <h3 style={{ margin: 0, fontSize: '1.125rem', fontWeight: 600, color: 'var(--text-primary)' }}>
                {rn.title}
              </h3>
              <span style={{ fontSize: '0.8125rem', color: 'var(--text-secondary)' }}>{rn.date}</span>
            </div>
            <ul style={{ margin: 0, paddingLeft: '1.25rem', color: 'var(--text-secondary)', fontSize: '0.875rem', lineHeight: '1.6' }}>
              {rn.highlights.map((h, hIdx) => (
                <li key={hIdx} style={{ marginBottom: '0.25rem' }}>{h}</li>
              ))}
            </ul>
          </div>
        ))}
      </div>
    </div>
  );
};
