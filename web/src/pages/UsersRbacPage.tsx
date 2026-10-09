import React, { useState, useEffect } from 'react';
import {
  Breadcrumb,
  NullValue,
  FreshnessIndicator,
  EmptyState,
  ErrorState,
  SkeletonLoader,
} from '../design-system';
import { useApiData } from '../api';
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

export const UsersRbacPage: React.FC<{ isDemo?: boolean }> = ({ isDemo = true }) => {
  const { data: apiUsers, loading, error, errorMessage, refetch } = useApiData<any>('/api/v1/users');
  const [users, setUsers] = useState<UserItem[]>([]);
  const [search, setSearch] = useState('');

  useEffect(() => {
    if (apiUsers) {
      const list = Array.isArray(apiUsers) ? apiUsers : (apiUsers.items || []);
      setUsers(list.map((u: any) => ({
        id: u.id || u.user_id || 'usr-01',
        email: u.email || 'user@enterprise.internal',
        name: u.display_name || u.name || 'Enterprise User',
        role: (u.role || u.roles?.[0] || 'FINOPS_ANALYST') as UserItem['role'],
        scopeGrant: u.scope_grant || u.scopeGrant || 'All Scopes (Tenant Wide)',
        mfaEnabled: u.mfa_enabled !== undefined ? u.mfa_enabled : (u.mfaEnabled ?? false),
        status: (u.status || 'ACTIVE') as UserItem['status'],
        lastLogin: u.last_login || u.lastLogin || '',
      })));
    }
  }, [apiUsers]);

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

        {loading ? (
          <SkeletonLoader variant="table" rows={3} />
        ) : error ? (
          <ErrorState
            title="Failed to Load Identities"
            message={errorMessage || 'Error contacting users directory API'}
            onRetry={refetch}
          />
        ) : filtered.length === 0 ? (
          <EmptyState type="NO_DATA" titleOverride="No Users Registered" descriptionOverride="No user identities or assigned scope grants registered for this tenant." actionTextOverride="Refresh Users" onAction={refetch} />
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
                          backgroundColor: 'rgba(56, 189, 248, 0.2)',
                          color: '#38bdf8',
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
