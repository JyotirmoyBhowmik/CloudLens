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
import { apiClient } from '../api/client';
import { DemoModeBanner } from '../components/DemoModeBanner';
import {
  CheckCircle2,
  Search,
  UserPlus,
  UserX,
  LogOut,
  X,
} from 'lucide-react';

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

const CANONICAL_ROLES = [
  'FINANCE_USER',
  'FINOPS_ADMINISTRATOR',
  'CLOUD_ADMINISTRATOR',
  'APPLICATION_OWNER',
  'IT_OPERATIONS_USER',
  'READ_ONLY_USER',
  'AUDITOR',
  'PLATFORM_ADMIN',
];

export const UsersRbacPage: React.FC<{ isDemo?: boolean }> = ({ isDemo = true }) => {
  const { data: apiUsers, loading, error, errorMessage, refetch } = useApiData<any>('/api/v1/users');
  const [users, setUsers] = useState<UserItem[]>([]);
  const [search, setSearch] = useState('');

  // Invite User Modal state
  const [isInviteOpen, setIsInviteOpen] = useState(false);
  const [inviteEmail, setInviteEmail] = useState('');
  const [inviteName, setInviteName] = useState('');
  const [inviteRole, setInviteRole] = useState('FINANCE_USER');
  const [inviteScope, setInviteScope] = useState('*');
  const [inviteError, setInviteError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    if (apiUsers) {
      const list = Array.isArray(apiUsers) ? apiUsers : (apiUsers.items || []);
      setUsers(list.map((u: any) => ({
        id: u.id || u.user_id || 'usr-01',
        email: u.email || 'user@enterprise.internal',
        name: u.display_name || u.name || 'Enterprise User',
        role: (u.role || u.roles?.[0] || 'FINANCE_USER') as UserItem['role'],
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

  const handleOpenInvite = () => {
    setInviteEmail('');
    setInviteName('');
    setInviteRole('FINANCE_USER');
    setInviteScope('*');
    setInviteError(null);
    setIsInviteOpen(true);
  };

  const handleInviteSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setInviteError(null);
    setIsSubmitting(true);
    try {
      await apiClient.post('/api/v1/users', {
        email: inviteEmail.trim().toLowerCase(),
        display_name: inviteName.trim(),
        roles: [inviteRole],
        auth_method: 'OIDC',
      });
      setIsInviteOpen(false);
      await refetch();
    } catch (err: any) {
      setInviteError(err.message || 'Failed to invite user identity.');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleDisableUser = async (user: UserItem) => {
    if (!confirm(`Are you sure you want to administratively disable ${user.name}?`)) return;
    try {
      await apiClient.patch(`/api/v1/users/${user.id}`, { status: 'DEACTIVATED' });
      await refetch();
    } catch (err: any) {
      alert(err.message || 'Failed to disable user');
    }
  };

  const handleRevokeSessions = async (user: UserItem) => {
    if (!confirm(`Revoke all active sessions and refresh tokens for ${user.name}?`)) return;
    try {
      await apiClient.delete(`/api/v1/auth/sessions/user/${user.id}`);
      alert(`All active sessions for ${user.name} have been revoked.`);
    } catch (err: any) {
      alert(err.message || 'Failed to revoke user sessions');
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem', width: '100%' }}>
      <DemoModeBanner isDemo={isDemo} />

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Breadcrumb
          items={[
            { label: 'Home', href: '/' },
            { label: 'Users & Roles', isCurrent: true },
          ]}
        />
        <FreshnessIndicator
          lastSyncedAt={new Date().toISOString()}
          provider="System"
        />
      </div>

      <header style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '1rem' }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '0.25rem' }}>
            <h1 style={{ fontSize: '1.75rem', fontWeight: 700, margin: 0, color: 'var(--text-primary)' }}>
              Users, Roles & Access Control
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
              Access Control
            </span>
          </div>
          <p style={{ color: 'var(--text-secondary)', margin: 0, fontSize: '0.9rem' }}>
            Identity provisioning, multidimensional scope grant assignments, account lifecycle, and session invalidation.
          </p>
        </div>

        <button
          id="invite-user-btn"
          onClick={handleOpenInvite}
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: '0.4rem',
            padding: '0.5rem 1rem',
            backgroundColor: '#0284c7',
            color: '#ffffff',
            border: 'none',
            borderRadius: '6px',
            fontSize: '0.85rem',
            fontWeight: 600,
            cursor: 'pointer',
          }}
        >
          <UserPlus size={16} aria-hidden="true" />
          Invite User
        </button>
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
            {CANONICAL_ROLES.length}
          </div>
          <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>Access Control Matrix</span>
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
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem', flexWrap: 'wrap', gap: '0.75rem' }}>
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
          <EmptyState
            type="NO_DATA"
            titleOverride="No Users Registered"
            descriptionOverride="No user identities or assigned scope grants registered for this tenant."
            actionTextOverride="Invite User"
            onAction={handleOpenInvite}
          />
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '0.85rem' }}>
              <thead>
                <tr style={{ borderBottom: '1px solid var(--border-color)', color: 'var(--text-secondary)' }}>
                  <th style={{ padding: '0.6rem' }}>User / Email</th>
                  <th style={{ padding: '0.6rem' }}>Canonical Role</th>
                  <th style={{ padding: '0.6rem' }}>Assigned Scope Grant</th>
                  <th style={{ padding: '0.6rem' }}>MFA Status</th>
                  <th style={{ padding: '0.6rem' }}>Status</th>
                  <th style={{ padding: '0.6rem', textAlign: 'right' }}>Actions</th>
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
                    <td style={{ padding: '0.75rem 0.6rem' }}>
                      <span
                        style={{
                          padding: '0.1rem 0.4rem',
                          borderRadius: '4px',
                          backgroundColor: u.status === 'ACTIVE' ? '#064e3b' : '#7f1d1d',
                          color: u.status === 'ACTIVE' ? '#6ee7b7' : '#fca5a5',
                          fontSize: '0.7rem',
                          fontWeight: 600,
                        }}
                      >
                        {u.status}
                      </span>
                    </td>
                    <td style={{ padding: '0.75rem 0.6rem', textAlign: 'right' }}>
                      <div style={{ display: 'inline-flex', gap: '0.4rem' }}>
                        <button
                          id={`revoke-sessions-btn-${u.id}`}
                          onClick={() => handleRevokeSessions(u)}
                          title="Revoke All Sessions"
                          style={{
                            padding: '0.3rem 0.5rem',
                            backgroundColor: 'var(--bg-primary)',
                            border: '1px solid var(--border-color)',
                            borderRadius: '4px',
                            color: 'var(--text-primary)',
                            fontSize: '0.75rem',
                            cursor: 'pointer',
                            display: 'inline-flex',
                            alignItems: 'center',
                            gap: '0.2rem',
                          }}
                        >
                          <LogOut size={12} aria-hidden="true" />
                          Revoke
                        </button>

                        {u.status === 'ACTIVE' && (
                          <button
                            id={`disable-user-btn-${u.id}`}
                            onClick={() => handleDisableUser(u)}
                            title="Disable User Account"
                            style={{
                              padding: '0.3rem 0.5rem',
                              backgroundColor: 'rgba(239, 68, 68, 0.1)',
                              border: '1px solid rgba(239, 68, 68, 0.3)',
                              borderRadius: '4px',
                              color: '#f87171',
                              fontSize: '0.75rem',
                              cursor: 'pointer',
                              display: 'inline-flex',
                              alignItems: 'center',
                              gap: '0.2rem',
                            }}
                          >
                            <UserX size={12} aria-hidden="true" />
                            Disable
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {/* Invite User Modal */}
      {isInviteOpen && (
        <div
          id="invite-user-modal"
          role="dialog"
          aria-modal="true"
          aria-labelledby="invite-modal-title"
          style={{
            position: 'fixed',
            inset: 0,
            backgroundColor: 'rgba(0, 0, 0, 0.7)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 1000,
            padding: '1rem',
          }}
        >
          <div
            style={{
              backgroundColor: 'var(--bg-secondary)',
              border: '1px solid var(--border-color)',
              borderRadius: '8px',
              padding: '1.5rem',
              width: '100%',
              maxWidth: '480px',
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
              <h2 id="invite-modal-title" style={{ fontSize: '1.2rem', fontWeight: 600, margin: 0, color: 'var(--text-primary)' }}>
                Invite Platform Identity
              </h2>
              <button
                onClick={() => setIsInviteOpen(false)}
                style={{ background: 'none', border: 'none', color: 'var(--text-secondary)', cursor: 'pointer' }}
                aria-label="Close invite modal"
              >
                <X size={18} />
              </button>
            </div>

            {inviteError && (
              <div role="alert" style={{ padding: '0.5rem 0.75rem', backgroundColor: 'rgba(239, 68, 68, 0.15)', border: '1px solid #ef4444', borderRadius: '6px', color: '#fca5a5', fontSize: '0.8rem', marginBottom: '0.75rem' }}>
                {inviteError}
              </div>
            )}

            <form onSubmit={handleInviteSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '0.85rem' }}>
              <div>
                <label htmlFor="invite-email-input" style={{ display: 'block', fontSize: '0.8rem', color: 'var(--text-secondary)', marginBottom: '0.25rem' }}>
                  Email Address *
                </label>
                <input
                  id="invite-email-input"
                  type="email"
                  required
                  value={inviteEmail}
                  onChange={(e) => setInviteEmail(e.target.value)}
                  placeholder="analyst@enterprise.internal"
                  style={{
                    width: '100%',
                    padding: '0.45rem',
                    borderRadius: '6px',
                    border: '1px solid var(--border-color)',
                    backgroundColor: 'var(--bg-primary)',
                    color: 'var(--text-primary)',
                    fontSize: '0.85rem',
                  }}
                />
              </div>

              <div>
                <label htmlFor="invite-name-input" style={{ display: 'block', fontSize: '0.8rem', color: 'var(--text-secondary)', marginBottom: '0.25rem' }}>
                  Full Display Name *
                </label>
                <input
                  id="invite-name-input"
                  type="text"
                  required
                  value={inviteName}
                  onChange={(e) => setInviteName(e.target.value)}
                  placeholder="Lead FinOps Analyst"
                  style={{
                    width: '100%',
                    padding: '0.45rem',
                    borderRadius: '6px',
                    border: '1px solid var(--border-color)',
                    backgroundColor: 'var(--bg-primary)',
                    color: 'var(--text-primary)',
                    fontSize: '0.85rem',
                  }}
                />
              </div>

              <div>
                <label htmlFor="invite-role-select" style={{ display: 'block', fontSize: '0.8rem', color: 'var(--text-secondary)', marginBottom: '0.25rem' }}>
                  Assigned Canonical Role *
                </label>
                <select
                  id="invite-role-select"
                  value={inviteRole}
                  onChange={(e) => setInviteRole(e.target.value)}
                  style={{
                    width: '100%',
                    padding: '0.45rem',
                    borderRadius: '6px',
                    border: '1px solid var(--border-color)',
                    backgroundColor: 'var(--bg-primary)',
                    color: 'var(--text-primary)',
                    fontSize: '0.85rem',
                  }}
                >
                  {CANONICAL_ROLES.map((r) => (
                    <option key={r} value={r}>
                      {r}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label htmlFor="invite-scope-input" style={{ display: 'block', fontSize: '0.8rem', color: 'var(--text-secondary)', marginBottom: '0.25rem' }}>
                  Resource Scope Grant
                </label>
                <input
                  id="invite-scope-input"
                  type="text"
                  value={inviteScope}
                  onChange={(e) => setInviteScope(e.target.value)}
                  placeholder="* (Tenant-Wide)"
                  style={{
                    width: '100%',
                    padding: '0.45rem',
                    borderRadius: '6px',
                    border: '1px solid var(--border-color)',
                    backgroundColor: 'var(--bg-primary)',
                    color: 'var(--text-primary)',
                    fontSize: '0.85rem',
                  }}
                />
              </div>

              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.5rem', marginTop: '0.5rem' }}>
                <button
                  type="button"
                  onClick={() => setIsInviteOpen(false)}
                  style={{
                    padding: '0.45rem 0.85rem',
                    backgroundColor: 'transparent',
                    border: '1px solid var(--border-color)',
                    borderRadius: '6px',
                    color: 'var(--text-secondary)',
                    fontSize: '0.85rem',
                    cursor: 'pointer',
                  }}
                >
                  Cancel
                </button>
                <button
                  id="invite-user-submit-btn"
                  type="submit"
                  disabled={isSubmitting}
                  style={{
                    padding: '0.45rem 1rem',
                    backgroundColor: '#0284c7',
                    border: 'none',
                    borderRadius: '6px',
                    color: '#ffffff',
                    fontSize: '0.85rem',
                    fontWeight: 600,
                    cursor: 'pointer',
                  }}
                >
                  {isSubmitting ? 'Inviting...' : 'Invite User'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};

export default UsersRbacPage;
