import React from 'react';
import { useApiData } from '../api';
import { SkeletonLoader, ErrorState, EmptyState } from '../design-system';

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
  release_notes?: ReleaseNote[];
}

export const AboutPage: React.FC = () => {
  const { data, loading, error, errorMessage, refetch } = useApiData<AboutData>('/api/v1/about');

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

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem', width: '100%' }}>
      <div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '0.5rem' }}>
          <h1 style={{ fontSize: '1.75rem', fontWeight: 700, margin: 0 }}>About CloudLens</h1>
          {data?.environment && (
            <span style={badgeStyle('#059669', '#d1fae5')}>
              {data.environment.toUpperCase()}
            </span>
          )}
        </div>
        <p style={{ color: 'var(--text-secondary)', margin: 0, fontSize: '0.875rem' }}>
          Platform build metadata, commit SHA, database migration head, and release notes from API.
        </p>
      </div>

      {loading ? (
        <SkeletonLoader variant="card" rows={3} />
      ) : error ? (
        <ErrorState
          title="Failed to Load Release Information"
          message={errorMessage || 'Error fetching platform metadata from /api/v1/about'}
          onRetry={refetch}
        />
      ) : !data ? (
        <EmptyState
          type="NO_DATA"
          titleOverride="No Release Metadata Available"
          descriptionOverride="Release information endpoint returned empty response."
          actionTextOverride="Retry Query"
          onAction={refetch}
        />
      ) : (
        <>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: '1rem' }}>
            <div style={cardStyle}>
              <div style={{ fontSize: '0.875rem', fontWeight: 600, color: 'var(--text-secondary)', marginBottom: '0.5rem' }}>
                Build Version
              </div>
              <div style={{ fontSize: '1.5rem', fontWeight: 700, color: '#38bdf8' }}>{data.version}</div>
              <div style={{ fontSize: '0.8125rem', color: 'var(--text-secondary)', marginTop: '0.25rem' }}>
                Release: {data.release_name}
              </div>
            </div>

            <div style={cardStyle}>
              <div style={{ fontSize: '0.875rem', fontWeight: 600, color: 'var(--text-secondary)', marginBottom: '0.5rem' }}>
                Git Commit SHA
              </div>
              <div style={{ fontSize: '1.125rem', fontWeight: 600, fontFamily: 'monospace', color: '#34d399' }}>
                {data.git_commit_short || (data.git_commit ? data.git_commit.substring(0, 8) : 'HEAD')}
              </div>
              <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', marginTop: '0.25rem', wordBreak: 'break-all' }}>
                Full SHA: {data.git_commit}
              </div>
            </div>

            <div style={cardStyle}>
              <div style={{ fontSize: '0.875rem', fontWeight: 600, color: 'var(--text-secondary)', marginBottom: '0.5rem' }}>
                Database Migration Head
              </div>
              <div style={{ fontSize: '1.125rem', fontWeight: 600, fontFamily: 'monospace', color: '#fbbf24' }}>
                {data.migration_head}
              </div>
              <div style={{ fontSize: '0.8125rem', color: 'var(--text-secondary)', marginTop: '0.25rem' }}>
                Alembic / Schema Revision Target
              </div>
            </div>

            <div style={cardStyle}>
              <div style={{ fontSize: '0.875rem', fontWeight: 600, color: 'var(--text-secondary)', marginBottom: '0.5rem' }}>
                Environment &amp; Build
              </div>
              <div style={{ fontSize: '1.25rem', fontWeight: 700, textTransform: 'uppercase', color: '#a78bfa' }}>
                {data.environment}
              </div>
              <div style={{ fontSize: '0.8125rem', color: 'var(--text-secondary)', marginTop: '0.25rem' }}>
                Released on {data.release_date}
              </div>
            </div>
          </div>

          {data.release_notes && data.release_notes.length > 0 && (
            <div style={cardStyle}>
              <div style={{ fontSize: '1rem', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '1rem' }}>
                Release Notes &amp; System Changelog
              </div>
              {data.release_notes.map((rn, idx) => (
                <div key={idx} style={{ marginBottom: idx === data.release_notes!.length - 1 ? 0 : '1.5rem' }}>
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
          )}
        </>
      )}
    </div>
  );
};
export default AboutPage;
