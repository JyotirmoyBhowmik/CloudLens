import React from 'react';
import { ShieldAlert, ArrowLeft } from 'lucide-react';
import { useNavigate } from 'react-router-dom';

export const ForbiddenPage: React.FC = () => {
  const navigate = useNavigate();

  return (
    <main
      style={{
        display: 'flex',
        minHeight: '70vh',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '2rem',
      }}
    >
      <div
        style={{
          maxWidth: '500px',
          backgroundColor: 'var(--bg-secondary)',
          border: '1px solid #7f1d1d',
          borderRadius: '12px',
          padding: '2.5rem',
          textAlign: 'center',
        }}
      >
        <div
          style={{
            width: '56px',
            height: '56px',
            borderRadius: '12px',
            backgroundColor: '#450a0a',
            color: '#f87171',
            display: 'inline-flex',
            alignItems: 'center',
            justifyContent: 'center',
            marginBottom: '1.25rem',
          }}
        >
          <ShieldAlert size={32} aria-hidden="true" />
        </div>

        <h1 style={{ fontSize: '1.5rem', fontWeight: 700, margin: '0 0 0.5rem 0', color: '#fca5a5' }}>
          403 — Forbidden Access
        </h1>
        <p style={{ color: 'var(--text-secondary)', fontSize: '0.875rem', marginBottom: '1.5rem' }}>
          Your active identity or persona lacks the necessary permissions or scope grants to view this resource.
          Cross-tenant boundary or restricted capability enforcement triggered.
        </p>

        <button
          type="button"
          onClick={() => navigate('/')}
          style={{
            padding: '0.6rem 1.25rem',
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
          }}
        >
          <ArrowLeft size={16} aria-hidden="true" />
          Return to Portal
        </button>
      </div>
    </main>
  );
};
export default ForbiddenPage;
