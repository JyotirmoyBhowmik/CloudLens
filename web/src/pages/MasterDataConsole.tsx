import React, { useEffect, useState } from 'react';

interface MasterRegistryEntry {
  code: string;
  name: string;
  purpose: string;
  is_tenant_scoped: boolean;
  is_editable: boolean;
  requires_approval: boolean;
  consuming_modules: string[];
  seed_file: string;
  expected_review_period_days: number;
}

interface MasterDataRecord {
  id: string;
  master_type: string;
  code: string;
  display_name: string;
  description?: string;
  sort_order: number;
  is_system: boolean;
  is_active: boolean;
  effective_from: string;
  effective_to?: string;
  version: number;
  parent_code?: string;
  attributes: Record<string, unknown>;
  lifecycle_status: string;
}

interface MasterDataHealthReport {
  total_masters_registered: number;
  total_records: number;
  active_records: number;
  inactive_records: number;
  empty_masters: string[];
  unreferenced_values: Array<{ master_type: string; code: string }>;
  referenced_inactive_values: Array<{ master_type: string; code: string; references: Record<string, number> }>;
  stale_masters: Array<{ master_type: string; last_updated: string; expected_review_days: number }>;
  overall_health_score: number;
}

export const MasterDataConsole: React.FC = () => {
  const [registry, setRegistry] = useState<MasterRegistryEntry[]>([]);
  const [selectedMaster, setSelectedMaster] = useState<string>('SERVICE_CATEGORY');
  const [records, setRecords] = useState<MasterDataRecord[]>([]);
  const [health, setHealth] = useState<MasterDataHealthReport | null>(null);
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [activeTab, setActiveTab] = useState<'records' | 'health'>('records');
  const [loading, setLoading] = useState<boolean>(true);
  const [selectedRecord, setSelectedRecord] = useState<MasterDataRecord | null>(null);

  useEffect(() => {
    // Fetch Registry Manifest and Health
    Promise.all([
      fetch('/api/v1/masterdata/registry').then((r) => (r.ok ? r.json() : [])),
      fetch('/api/v1/masterdata/health').then((r) => (r.ok ? r.json() : null)),
    ]).then(([regData, healthData]) => {
      setRegistry(regData);
      setHealth(healthData);
      setLoading(false);
    }).catch(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (!selectedMaster) return;
    setLoading(true);
    fetch(`/api/v1/masterdata/${selectedMaster}?include_inactive=true`)
      .then((r) => (r.ok ? r.json() : []))
      .then((data: MasterDataRecord[]) => {
        setRecords(data);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, [selectedMaster]);

  const filteredRecords = records.filter(
    (r) =>
      r.code.toLowerCase().includes(searchQuery.toLowerCase()) ||
      r.display_name.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const currentManifest = registry.find((m) => m.code === selectedMaster);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem', width: '100%' }}>
      {/* Top Header & Health Badge */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid var(--border-color)', paddingBottom: '1rem' }}>
        <div>
          <h2 style={{ fontSize: '1.5rem', fontWeight: 700, margin: '0 0 0.25rem 0' }}>
            Master Data Console
          </h2>
          <p style={{ margin: 0, color: 'var(--text-secondary)', fontSize: '0.875rem' }}>
            Single administrative interface for every catalogue, enumeration, unit, and reference value.
          </p>
        </div>
        <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center' }}>
          <div style={{
            padding: '0.4rem 0.8rem',
            borderRadius: '6px',
            backgroundColor: health && health.overall_health_score >= 90 ? '#064e3b' : '#7f1d1d',
            color: health && health.overall_health_score >= 90 ? '#6ee7b7' : '#fca5a5',
            fontSize: '0.875rem',
            fontWeight: 600,
          }}>
            Health Score: {health ? `${health.overall_health_score}%` : '100%'}
          </div>
          <button
            onClick={() => setActiveTab(activeTab === 'records' ? 'health' : 'records')}
            style={{
              padding: '0.4rem 0.8rem',
              borderRadius: '6px',
              border: '1px solid var(--border-color)',
              backgroundColor: 'var(--bg-secondary)',
              color: 'var(--text-primary)',
              cursor: 'pointer',
              fontSize: '0.875rem',
            }}
          >
            {activeTab === 'records' ? 'View Health Report' : 'View Master Records'}
          </button>
        </div>
      </div>

      {activeTab === 'health' && health ? (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '1rem' }}>
            <div style={{ padding: '1rem', backgroundColor: 'var(--bg-secondary)', borderRadius: '8px', border: '1px solid var(--border-color)' }}>
              <div style={{ color: 'var(--text-secondary)', fontSize: '0.8125rem' }}>Registered Masters</div>
              <div style={{ fontSize: '1.5rem', fontWeight: 700, marginTop: '0.25rem' }}>{health.total_masters_registered}</div>
            </div>
            <div style={{ padding: '1rem', backgroundColor: 'var(--bg-secondary)', borderRadius: '8px', border: '1px solid var(--border-color)' }}>
              <div style={{ color: 'var(--text-secondary)', fontSize: '0.8125rem' }}>Active Master Values</div>
              <div style={{ fontSize: '1.5rem', fontWeight: 700, marginTop: '0.25rem', color: '#10b981' }}>{health.active_records}</div>
            </div>
            <div style={{ padding: '1rem', backgroundColor: 'var(--bg-secondary)', borderRadius: '8px', border: '1px solid var(--border-color)' }}>
              <div style={{ color: 'var(--text-secondary)', fontSize: '0.8125rem' }}>Unreferenced Values</div>
              <div style={{ fontSize: '1.5rem', fontWeight: 700, marginTop: '0.25rem', color: '#f59e0b' }}>{health.unreferenced_values.length}</div>
            </div>
            <div style={{ padding: '1rem', backgroundColor: 'var(--bg-secondary)', borderRadius: '8px', border: '1px solid var(--border-color)' }}>
              <div style={{ color: 'var(--text-secondary)', fontSize: '0.8125rem' }}>Empty Masters</div>
              <div style={{ fontSize: '1.5rem', fontWeight: 700, marginTop: '0.25rem', color: health.empty_masters.length ? '#ef4444' : '#10b981' }}>
                {health.empty_masters.length}
              </div>
            </div>
          </div>
        </div>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: '280px 1fr', gap: '1.5rem' }}>
          {/* Master Selector Sidebar */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem', maxHeight: '800px', overflowY: 'auto', paddingRight: '0.5rem' }}>
            <span style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
              Registered Manifest ({registry.length})
            </span>
            {registry.map((m) => (
              <button
                key={m.code}
                onClick={() => setSelectedMaster(m.code)}
                style={{
                  textAlign: 'left',
                  padding: '0.6rem 0.8rem',
                  borderRadius: '6px',
                  border: '1px solid',
                  borderColor: selectedMaster === m.code ? '#0284c7' : 'transparent',
                  backgroundColor: selectedMaster === m.code ? '#0369a1' : 'var(--bg-secondary)',
                  color: selectedMaster === m.code ? '#ffffff' : 'var(--text-primary)',
                  cursor: 'pointer',
                  fontSize: '0.875rem',
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                }}
              >
                <span>{m.name}</span>
                {m.requires_approval && (
                  <span style={{ fontSize: '0.6875rem', padding: '0.1rem 0.35rem', borderRadius: '4px', backgroundColor: '#475569' }}>
                    Approval
                  </span>
                )}
              </button>
            ))}
          </div>

          {/* Master Records Main Pane */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
            {currentManifest && (
              <div style={{ padding: '1rem', backgroundColor: 'var(--bg-secondary)', borderRadius: '8px', border: '1px solid var(--border-color)' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <h3 style={{ margin: 0, fontSize: '1.125rem' }}>{currentManifest.name}</h3>
                  <div style={{ display: 'flex', gap: '0.5rem' }}>
                    <a
                      href={`/api/v1/masterdata/${selectedMaster}/export?format=json`}
                      download={`${selectedMaster.toLowerCase()}.json`}
                      style={{ padding: '0.3rem 0.6rem', borderRadius: '4px', border: '1px solid var(--border-color)', fontSize: '0.75rem', textDecoration: 'none', color: '#38bdf8' }}
                    >
                      Export JSON
                    </a>
                    <a
                      href={`/api/v1/masterdata/${selectedMaster}/export?format=csv`}
                      download={`${selectedMaster.toLowerCase()}.csv`}
                      style={{ padding: '0.3rem 0.6rem', borderRadius: '4px', border: '1px solid var(--border-color)', fontSize: '0.75rem', textDecoration: 'none', color: '#34d399' }}
                    >
                      Export CSV
                    </a>
                  </div>
                </div>
                <p style={{ margin: '0.5rem 0 0 0', fontSize: '0.8125rem', color: 'var(--text-secondary)' }}>
                  {currentManifest.purpose}
                </p>
                <div style={{ display: 'flex', gap: '1rem', marginTop: '0.5rem', fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
                  <span>Consuming Modules: <strong>{currentManifest.consuming_modules.join(', ')}</strong></span>
                  <span>Scope: <strong>{currentManifest.is_tenant_scoped ? 'Tenant Customizable' : 'Global Unified'}</strong></span>
                </div>
              </div>
            )}

            {/* Search filter */}
            <input
              type="text"
              placeholder={`Search ${selectedMaster} records by code or name...`}
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              style={{
                padding: '0.5rem 0.8rem',
                borderRadius: '6px',
                border: '1px solid var(--border-color)',
                backgroundColor: 'var(--bg-secondary)',
                color: 'var(--text-primary)',
                fontSize: '0.875rem',
              }}
            />

            {/* Records Table */}
            <div style={{ border: '1px solid var(--border-color)', borderRadius: '8px', overflow: 'hidden' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.875rem' }}>
                <thead>
                  <tr style={{ backgroundColor: 'var(--bg-secondary)', borderBottom: '1px solid var(--border-color)', textAlign: 'left' }}>
                    <th style={{ padding: '0.6rem 0.8rem' }}>Code</th>
                    <th style={{ padding: '0.6rem 0.8rem' }}>Display Name</th>
                    <th style={{ padding: '0.6rem 0.8rem' }}>Status</th>
                    <th style={{ padding: '0.6rem 0.8rem' }}>Version</th>
                    <th style={{ padding: '0.6rem 0.8rem' }}>System</th>
                    <th style={{ padding: '0.6rem 0.8rem' }}>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {loading ? (
                    <tr>
                      <td colSpan={6} style={{ padding: '2rem', textAlign: 'center', color: 'var(--text-secondary)' }}>
                        Loading master records...
                      </td>
                    </tr>
                  ) : filteredRecords.length === 0 ? (
                    <tr>
                      <td colSpan={6} style={{ padding: '2rem', textAlign: 'center', color: 'var(--text-secondary)' }}>
                        No records found.
                      </td>
                    </tr>
                  ) : (
                    filteredRecords.map((r) => (
                      <tr key={r.id} style={{ borderBottom: '1px solid var(--border-color)' }}>
                        <td style={{ padding: '0.6rem 0.8rem', fontWeight: 600, color: '#38bdf8' }}>{r.code}</td>
                        <td style={{ padding: '0.6rem 0.8rem' }}>{r.display_name}</td>
                        <td style={{ padding: '0.6rem 0.8rem' }}>
                          <span style={{
                            padding: '0.15rem 0.4rem',
                            borderRadius: '4px',
                            fontSize: '0.75rem',
                            backgroundColor: r.is_active ? '#064e3b' : '#7f1d1d',
                            color: r.is_active ? '#6ee7b7' : '#fca5a5',
                          }}>
                            {r.is_active ? r.lifecycle_status : 'INACTIVE'}
                          </span>
                        </td>
                        <td style={{ padding: '0.6rem 0.8rem' }}>v{r.version}</td>
                        <td style={{ padding: '0.6rem 0.8rem' }}>{r.is_system ? 'Yes' : 'No'}</td>
                        <td style={{ padding: '0.6rem 0.8rem' }}>
                          <button
                            onClick={() => setSelectedRecord(r)}
                            style={{
                              padding: '0.2rem 0.5rem',
                              fontSize: '0.75rem',
                              borderRadius: '4px',
                              border: '1px solid var(--border-color)',
                              backgroundColor: 'transparent',
                              color: 'var(--text-primary)',
                              cursor: 'pointer',
                            }}
                          >
                            Details
                          </button>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>

            {/* Record Inspector Drawer */}
            {selectedRecord && (
              <div style={{ padding: '1rem', backgroundColor: 'var(--bg-secondary)', borderRadius: '8px', border: '1px solid var(--border-color)', marginTop: '1rem' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <h4 style={{ margin: 0 }}>Record Inspection: {selectedRecord.code}</h4>
                  <button onClick={() => setSelectedRecord(null)} style={{ border: 'none', background: 'transparent', color: '#94a3b8', cursor: 'pointer' }}>✕</button>
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem', marginTop: '0.75rem', fontSize: '0.8125rem' }}>
                  <div>
                    <div><strong>Display Name:</strong> {selectedRecord.display_name}</div>
                    <div><strong>Description:</strong> {selectedRecord.description || 'None'}</div>
                    <div><strong>Effective Interval:</strong> {selectedRecord.effective_from} to {selectedRecord.effective_to || 'Indefinite'}</div>
                  </div>
                  <div>
                    <div><strong>Attributes:</strong></div>
                    <pre style={{ backgroundColor: '#0f172a', padding: '0.5rem', borderRadius: '4px', overflowX: 'auto', fontSize: '0.75rem' }}>
                      {JSON.stringify(selectedRecord.attributes, null, 2)}
                    </pre>
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};
