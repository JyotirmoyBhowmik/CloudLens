import React, { useState, useEffect } from 'react';
import {
  Breadcrumb,
  NullValue,
  FreshnessIndicator,
} from '../design-system';
import { DemoModeBanner } from '../components/DemoModeBanner';
import { CheckCircle2, Search } from 'lucide-react';

interface UserItem {
  id: string;
  email: string;
  name: string;
  role: string;
  scopeGrant: string;
  mfaEnabled: boolean;
  status: 'ACTIVE' | 'DEACTIVATED';
  lastLogin: string;
}

const DEMO_USERS: UserItem[] = [
  {
    id: 'usr-01',
    email: 'admin@jyotirmoyb.com',
    name: 'Super Administrator',
    role: 'SUPER_ADMIN',
    scopeGrant: 'PLATFORM (Global Root)',
    mfaEnabled: true,
    status: 'ACTIVE',
    lastLogin: '2026-10-05T21:40:00Z',
  },
  {
    id: 'usr-02',
    email: 'sarah.chen@enterprise.internal',
    name: 'Sarah Chen',
    role: 'FINOPS_LEAD',
    scopeGrant: 'All Scopes (Tenant Wide)',
    mfaEnabled: true,
    status: 'ACTIVE',
    lastLogin: '2026-10-05T19:15:00Z',
  },
  {
    id: 'usr-03',
    email: 'marcus.v@enterprise.internal',
    name: 'Marcus Vance',
    role: 'FINANCE_CONTROLLER',
    scopeGrant: 'Cost Centres & Business Units',
    mfaEnabled: true,
    status: 'ACTIVE',
    lastLogin: '2026-10-04T14:20:00Z',
  },
  {
    id: 'usr-04',
    email: 'alex.m@enterprise.internal',
    name: 'Alex Mercer',
    role: 'DEVELOPER',
    scopeGrant: 'APP-CHECKOUT-PROD',
    mfaEnabled: true,
    status: 'ACTIVE',
    lastLogin: '2026-10-05T11:00:00Z',
  },
  {
    id: 'usr-05',
    email: 'auditor.lead@enterprise.internal',
    name: 'Compliance Auditor',
    role: 'AUDITOR',
    scopeGrant: 'Read-Only Audit Ledger',
    mfaEnabled: true,
    status: 'ACTIVE',
    lastLogin: '2026-10-03T16:00:00Z',
  },
];

export const UsersRbacPage: React.FC<{ isDemo?: boolean }> = ({ isDemo = true }) => {
  const [users, setUsers] = useState<UserItem[]>(DEMO_USERS);
  const [search, setSearch] = useState('');

  useEffect(() => {
    if (!isDemo) {
      setUsers([]);
    } else {
      setUsers(DEMO_USERS);
    }
  }, [isDemo]);

  const filtered = users.filter((u) =>
    `${u.email} ${u.name} ${u.role}`.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem', width: '100%' }}>
      <DemoModeBanner isDemo={isDemo} />

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Breadcrumb
          items={[
            { label: 'Home', href: '/' },
            { label: 'Users & RBAC', isCurrent: true },
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
            S-17: Users, Roles & RBAC Matrix
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
            Prompt R-ROLES / 9 Canonical Roles
          </span>
        </div>
        <p style={{ color: 'var(--text-secondary)', margin: 0, fontSize: '0.9rem' }}>
          Identity provisioning, 8-dimensional scope grant evaluation, and strict multi-tenant access control.
        </p>
      </header>

      {/* Overview Cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '1rem' }}>
        <div style={{ backgroundColor: 'var(--bg-secondary)', border: '1px solid var(--border-color)', borderRadius: '8px', padding: '1rem' }}>
          <span style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>Active Identities</span>
          <div style={{ fontSize: '1.5rem', fontWeight: 700, color: 'var(--text-primary)', marginTop: '0.25rem' }}>
            {users.length > 0 ? users.length : <NullValue state="NO_DATA" />}
          </div>
        </div>

        <div style={{ backgroundColor: 'var(--bg-secondary)', border: '1px solid #10b981', borderRadius: '8px', padding: '1rem' }}>
          <span style={{ fontSize: '0.8rem', color: '#6ee7b7' }}>MFA Enforcement</span>
          <div style={{ fontSize: '1.5rem', fontWeight: 700, color: '#34d399', marginTop: '0.25rem' }}>
            100%
          </div>
          <span style={{ fontSize: '0.75rem', color: '#a7f3d0' }}>Mandatory TOTP / WebAuthn</span>
        </div>

        <div style={{ backgroundColor: 'var(--bg-secondary)', border: '1px solid var(--border-color)', borderRadius: '8px', padding: '1rem' }}>
          <span style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>Canonical System Roles</span>
          <div style={{ fontSize: '1.5rem', fontWeight: 700, color: 'var(--text-primary)', marginTop: '0.25rem' }}>
            9
          </div>
          <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>BBP Section 31 Matrix</span>
        </div>
      </div>

      {/* Users Directory Table */}
      <section
        aria-labelledby="users-table-heading"
        style={{
          backgroundColor: 'var(--bg-secondary)',
          border: '1px solid var(--border-color)',
          borderRadius: '8px',
          padding: '1.25rem',
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
          <h2 id="users-table-heading" style={{ fontSize: '1.1rem', fontWeight: 600, margin: 0 }}>
            Identity & Scope Grants
          </h2>

          <div style={{ position: 'relative' }}>
            <Search size={14} style={{ position: 'absolute', left: '0.6rem', top: '0.6rem', color: 'var(--text-secondary)' }} aria-hidden="true" />
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search user or role..."
              aria-label="Search users"
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

        {filtered.length === 0 ? (
          <div
            style={{
              padding: '2.5rem',
              borderRadius: '6px',
              border: '1px dashed var(--border-color)',
              textAlign: 'center',
            }}
          >
            <p style={{ color: 'var(--text-secondary)', marginBottom: '0.5rem' }}>
              No identities recorded in this tenant context.
            </p>
            <div style={{ display: 'inline-flex', alignItems: 'center', gap: '0.5rem' }}>
              <span style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>Status:</span>
              <NullValue state="NO_DATA" />
            </div>
          </div>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '0.85rem' }}>
              <thead>
                <tr style={{ borderBottom: '1px solid var(--border-color)', color: 'var(--text-secondary)' }}>
                  <th style={{ padding: '0.6rem' }}>User / Email</th>
                  <th style={{ padding: '0.6rem' }}>Canonical Role</th>
                  <th style={{ padding: '0.6rem' }}>Assigned Scope Grant</th>
                  <th style={{ padding: '0.6rem' }}>MFA Status</th>
                  <th style={{ padding: '0.6rem' }}>Last Activity</th>
                  <th style={{ padding: '0.6rem' }}>Status</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((u) => (
                  <tr key={u.id} style={{ borderBottom: '1px solid var(--border-color)' }}>
                    <td style={{ padding: '0.75rem 0.6rem' }}>
                      <strong>{u.name}</strong>
                      <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>{u.email}</div>
                    </td>
                    <td style={{ padding: '0.75rem 0.6rem' }}>
                      <span
                        style={{
                          padding: '0.15rem 0.5rem',
                          borderRadius: '4px',
                          fontSize: '0.75rem',
                          fontWeight: 600,
                          backgroundColor: u.role === 'SUPER_ADMIN' ? '#7f1d1d' : '#0369a1',
                          color: u.role === 'SUPER_ADMIN' ? '#fca5a5' : '#e0f2fe',
                        }}
                      >
                        {u.role}
                      </span>
                    </td>
                    <td style={{ padding: '0.75rem 0.6rem' }}>
                      <code>{u.scopeGrant}</code>
                    </td>
                    <td style={{ padding: '0.75rem 0.6rem' }}>
                      <span style={{ display: 'inline-flex', alignItems: 'center', gap: '0.2rem', color: '#34d399', fontSize: '0.75rem' }}>
                        <CheckCircle2 size={12} aria-hidden="true" /> MFA Enforced
                      </span>
                    </td>
                    <td style={{ padding: '0.75rem 0.6rem', fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
                      {new Date(u.lastLogin).toLocaleString()}
                    </td>
                    <td style={{ padding: '0.75rem 0.6rem' }}>
                      <span style={{ padding: '0.1rem 0.4rem', borderRadius: '4px', backgroundColor: '#064e3b', color: '#6ee7b7', fontSize: '0.7rem', fontWeight: 600 }}>
                        {u.status}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
};
export default UsersRbacPage;
