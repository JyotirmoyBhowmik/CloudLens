import React, { useEffect, useState } from 'react';
import { Plus, Upload } from 'lucide-react';

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

interface DryRunResult {
  valid: boolean;
  total_records: number;
  to_add: number;
  to_update: number;
  errors: string[];
  warnings: string[];
}

export const MasterDataConsole: React.FC = () => {
  const [registry, setRegistry] = useState<MasterRegistryEntry[]>([]);
  const [selectedMaster, setSelectedMaster] = useState<string>('APPLICATION');
  const [records, setRecords] = useState<MasterDataRecord[]>([]);
  const [health, setHealth] = useState<MasterDataHealthReport | null>(null);
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [activeTab, setActiveTab] = useState<'records' | 'health'>('records');
  const [loading, setLoading] = useState<boolean>(true);
  const [selectedRecord, setSelectedRecord] = useState<MasterDataRecord | null>(null);

  // Edit Modal State
  const [editModalOpen, setEditModalOpen] = useState<boolean>(false);
  const [editRecord, setEditRecord] = useState<MasterDataRecord | null>(null);
  const [editETag, setEditETag] = useState<string>('');
  const [editDisplayName, setEditDisplayName] = useState<string>('');
  const [editDescription, setEditDescription] = useState<string>('');
  const [editChangeReason, setEditChangeReason] = useState<string>('Master data standard alignment');
  const [editError, setEditError] = useState<string | null>(null);

  // Create Modal State
  const [createModalOpen, setCreateModalOpen] = useState<boolean>(false);
  const [newCode, setNewCode] = useState<string>('');
  const [newDisplayName, setNewDisplayName] = useState<string>('');
  const [newDescription, setNewDescription] = useState<string>('');
  const [createError, setCreateError] = useState<string | null>(null);

  // CSV Import Modal State
  const [importModalOpen, setImportModalOpen] = useState<boolean>(false);
  const [csvContent, setCsvContent] = useState<string>(
    'code,display_name,description\nTEST_ITEM_01,Test Master Item 01,Created via CSV Import\nTEST_ITEM_02,Test Master Item 02,Created via CSV Import'
  );
  const [dryRunResult, setDryRunResult] = useState<DryRunResult | null>(null);
  const [importLoading, setImportLoading] = useState<boolean>(false);
  const [importMessage, setImportMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  const fetchRecords = () => {
    if (!selectedMaster) return;
    setLoading(true);
    fetch(`/api/v1/masterdata/${selectedMaster}?include_inactive=true`)
      .then((r) => (r.ok ? r.json() : []))
      .then((data: MasterDataRecord[]) => {
        setRecords(data);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  };

  useEffect(() => {
    Promise.all([
      fetch('/api/v1/masterdata/registry').then((r) => (r.ok ? r.json() : [])),
      fetch('/api/v1/masterdata/health').then((r) => (r.ok ? r.json() : null)),
    ])
      .then(([regData, healthData]) => {
        setRegistry(regData);
        if (regData.length > 0 && !regData.some((r: any) => r.code === selectedMaster)) {
          setSelectedMaster(regData[0].code);
        }
        setHealth(healthData);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, []);

  useEffect(() => {
    fetchRecords();
  }, [selectedMaster]);

  const filteredRecords = records.filter(
    (r) =>
      r.code.toLowerCase().includes(searchQuery.toLowerCase()) ||
      r.display_name.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const currentManifest = registry.find((m) => m.code === selectedMaster);

  // Open Edit Modal & Fetch ETag
  const handleOpenEdit = async (rec: MasterDataRecord) => {
    setEditRecord(rec);
    setEditDisplayName(rec.display_name);
    setEditDescription(rec.description || '');
    setEditChangeReason('Versioned update for business domain standardization');
    setEditError(null);

    try {
      const res = await fetch(`/api/v1/masterdata/records/${selectedMaster}/${rec.code}`);
      if (res.ok) {
        const etag = res.headers.get('ETag') || '';
        setEditETag(etag);
      }
    } catch {
      setEditETag('');
    }
    setEditModalOpen(true);
  };

  // Submit Edit with If-Match check
  const handleSaveEdit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editRecord) return;
    setEditError(null);

    try {
      const headers: Record<string, string> = { 'Content-Type': 'application/json' };
      if (editETag) {
        headers['If-Match'] = editETag;
      }

      const res = await fetch(`/api/v1/masterdata/${selectedMaster}/${editRecord.code}`, {
        method: 'PUT',
        headers,
        body: JSON.stringify({
          display_name: editDisplayName,
          description: editDescription,
          change_reason: editChangeReason,
        }),
      });

      if (res.status === 412) {
        setEditError('Precondition Failed (412): Record modified concurrently. Please reload.');
        return;
      }

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || `HTTP error ${res.status}`);
      }

      setEditModalOpen(false);
      fetchRecords();
    } catch (err: any) {
      setEditError(err.message || 'Update failed');
    }
  };

  // Create new Master Record
  const handleSaveCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    setCreateError(null);

    try {
      const res = await fetch(`/api/v1/masterdata/${selectedMaster}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          code: newCode.trim().toUpperCase(),
          display_name: newDisplayName.trim(),
          description: newDescription.trim(),
        }),
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || `HTTP error ${res.status}`);
      }

      setCreateModalOpen(false);
      setNewCode('');
      setNewDisplayName('');
      setNewDescription('');
      fetchRecords();
    } catch (err: any) {
      setCreateError(err.message || 'Create failed');
    }
  };

  // Dry Run CSV Import Validation
  const handleValidateDryRun = async () => {
    setImportLoading(true);
    setImportMessage(null);
    setDryRunResult(null);

    try {
      const res = await fetch(`/api/v1/masterdata/${selectedMaster}/import/validate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ format: 'csv', content: csvContent }),
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || 'Validation failed');
      }

      const data = await res.json();
      setDryRunResult(data);
    } catch (err: any) {
      setImportMessage({ type: 'error', text: err.message || 'Validation request failed' });
    } finally {
      setImportLoading(false);
    }
  };

  // Execute CSV Import
  const handleExecuteImport = async () => {
    setImportLoading(true);
    setImportMessage(null);

    try {
      const res = await fetch(`/api/v1/masterdata/${selectedMaster}/import`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ format: 'csv', content: csvContent }),
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || 'Import execution failed');
      }

      const data = await res.json();
      setImportMessage({
        type: 'success',
        text: `Import successful: ${data.added || 0} records created, ${data.updated || 0} records updated.`,
      });
      fetchRecords();
    } catch (err: any) {
      setImportMessage({ type: 'error', text: err.message || 'Import execution failed' });
    } finally {
      setImportLoading(false);
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem', width: '100%' }}>
      {/* Top Header & Health Badge */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid var(--border-color)', paddingBottom: '1rem' }}>
        <div>
          <h2 style={{ fontSize: '1.5rem', fontWeight: 700, margin: '0 0 0.25rem 0' }}>
            Master Data Console
          </h2>
          <p style={{ margin: 0, color: 'var(--text-secondary)', fontSize: '0.875rem' }}>
            Single authoritative administrative interface for every catalogue, enumeration, unit, and reference value.
          </p>
        </div>
        <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center' }}>
          <div
            style={{
              padding: '0.4rem 0.8rem',
              borderRadius: '6px',
              backgroundColor: health && health.overall_health_score >= 90 ? '#064e3b' : '#7f1d1d',
              color: health && health.overall_health_score >= 90 ? '#6ee7b7' : '#fca5a5',
              fontSize: '0.875rem',
              fontWeight: 600,
            }}
          >
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
                data-testid={`manifest-btn-${m.code}`}
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
                    <button
                      data-testid="open-create-master-btn"
                      onClick={() => setCreateModalOpen(true)}
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: '0.3rem',
                        padding: '0.35rem 0.7rem',
                        borderRadius: '4px',
                        border: 'none',
                        backgroundColor: '#0284c7',
                        color: '#ffffff',
                        fontSize: '0.75rem',
                        fontWeight: 600,
                        cursor: 'pointer',
                      }}
                    >
                      <Plus size={13} />
                      <span>New Record</span>
                    </button>
                    <button
                      data-testid="open-import-modal-btn"
                      onClick={() => {
                        setImportModalOpen(true);
                        setDryRunResult(null);
                        setImportMessage(null);
                      }}
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: '0.3rem',
                        padding: '0.35rem 0.7rem',
                        borderRadius: '4px',
                        border: '1px solid var(--border-color)',
                        backgroundColor: 'var(--bg-primary)',
                        color: '#38bdf8',
                        fontSize: '0.75rem',
                        fontWeight: 600,
                        cursor: 'pointer',
                      }}
                    >
                      <Upload size={13} />
                      <span>Import CSV (Dry Run)</span>
                    </button>
                    <a
                      href={`/api/v1/masterdata/${selectedMaster}/export?format=json`}
                      download={`${selectedMaster.toLowerCase()}.json`}
                      style={{ padding: '0.35rem 0.6rem', borderRadius: '4px', border: '1px solid var(--border-color)', fontSize: '0.75rem', textDecoration: 'none', color: '#94a3b8' }}
                    >
                      Export JSON
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
              data-testid="master-search-input"
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
                    <th style={{ padding: '0.6rem 0.8rem', textAlign: 'right' }}>Actions</th>
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
                      <tr key={r.id || r.code} data-testid={`master-row-${r.code}`} style={{ borderBottom: '1px solid var(--border-color)' }}>
                        <td style={{ padding: '0.6rem 0.8rem', fontWeight: 600, color: '#38bdf8' }}>{r.code}</td>
                        <td style={{ padding: '0.6rem 0.8rem' }}>{r.display_name}</td>
                        <td style={{ padding: '0.6rem 0.8rem' }}>
                          <span
                            style={{
                              padding: '0.15rem 0.4rem',
                              borderRadius: '4px',
                              fontSize: '0.75rem',
                              backgroundColor: r.is_active ? '#064e3b' : '#7f1d1d',
                              color: r.is_active ? '#6ee7b7' : '#fca5a5',
                            }}
                          >
                            {r.is_active ? r.lifecycle_status || 'ACTIVE' : 'INACTIVE'}
                          </span>
                        </td>
                        <td style={{ padding: '0.6rem 0.8rem' }}>v{r.version}</td>
                        <td style={{ padding: '0.6rem 0.8rem' }}>{r.is_system ? 'Yes' : 'No'}</td>
                        <td style={{ padding: '0.6rem 0.8rem', textAlign: 'right' }}>
                          <div style={{ display: 'inline-flex', gap: '0.4rem' }}>
                            <button
                              data-testid={`edit-master-btn-${r.code}`}
                              onClick={() => handleOpenEdit(r)}
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
                              Edit
                            </button>
                            <button
                              onClick={() => setSelectedRecord(r)}
                              style={{
                                padding: '0.2rem 0.5rem',
                                fontSize: '0.75rem',
                                borderRadius: '4px',
                                border: '1px solid var(--border-color)',
                                backgroundColor: 'transparent',
                                color: 'var(--text-secondary)',
                                cursor: 'pointer',
                              }}
                            >
                              Details
                            </button>
                          </div>
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

      {/* Edit Master Record Modal (Versioned + If-Match) */}
      {editModalOpen && editRecord && (
        <div
          data-testid="edit-master-modal"
          style={{
            position: 'fixed',
            inset: 0,
            backgroundColor: 'rgba(0,0,0,0.7)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 1000,
          }}
        >
          <div
            style={{
              backgroundColor: 'var(--bg-secondary)',
              borderRadius: '8px',
              border: '1px solid var(--border-color)',
              padding: '1.5rem',
              width: '460px',
              maxWidth: '90vw',
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
              <h3 style={{ margin: 0 }}>Versioned Edit: {editRecord.code} (v{editRecord.version})</h3>
              <button onClick={() => setEditModalOpen(false)} style={{ background: 'none', border: 'none', color: '#94a3b8', cursor: 'pointer' }}>✕</button>
            </div>

            {editError && (
              <div style={{ padding: '0.5rem 0.75rem', backgroundColor: '#7f1d1d', color: '#fca5a5', borderRadius: '6px', fontSize: '0.8125rem', marginBottom: '1rem' }}>
                {editError}
              </div>
            )}

            <form onSubmit={handleSaveEdit} style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
              <div>
                <label style={{ display: 'block', fontSize: '0.8125rem', color: 'var(--text-secondary)', marginBottom: '0.25rem' }}>
                  Display Name
                </label>
                <input
                  type="text"
                  data-testid="edit-master-name-input"
                  required
                  value={editDisplayName}
                  onChange={(e) => setEditDisplayName(e.target.value)}
                  style={{ width: '100%', padding: '0.45rem', borderRadius: '6px', border: '1px solid var(--border-color)', backgroundColor: 'var(--bg-primary)', color: 'var(--text-primary)' }}
                />
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '0.8125rem', color: 'var(--text-secondary)', marginBottom: '0.25rem' }}>
                  Description
                </label>
                <input
                  type="text"
                  value={editDescription}
                  onChange={(e) => setEditDescription(e.target.value)}
                  style={{ width: '100%', padding: '0.45rem', borderRadius: '6px', border: '1px solid var(--border-color)', backgroundColor: 'var(--bg-primary)', color: 'var(--text-primary)' }}
                />
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '0.8125rem', color: 'var(--text-secondary)', marginBottom: '0.25rem' }}>
                  Change Reason (Mandatory Audit Versioning Note)
                </label>
                <textarea
                  rows={2}
                  data-testid="edit-master-reason-input"
                  required
                  value={editChangeReason}
                  onChange={(e) => setEditChangeReason(e.target.value)}
                  style={{ width: '100%', padding: '0.45rem', borderRadius: '6px', border: '1px solid var(--border-color)', backgroundColor: 'var(--bg-primary)', color: 'var(--text-primary)' }}
                />
              </div>

              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.75rem', marginTop: '0.5rem' }}>
                <button
                  type="button"
                  onClick={() => setEditModalOpen(false)}
                  style={{ padding: '0.4rem 0.8rem', borderRadius: '6px', border: '1px solid var(--border-color)', backgroundColor: 'transparent', color: 'var(--text-secondary)', cursor: 'pointer' }}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  data-testid="save-master-edit-btn"
                  style={{ padding: '0.4rem 1rem', borderRadius: '6px', border: 'none', backgroundColor: '#0284c7', color: '#ffffff', cursor: 'pointer', fontWeight: 600 }}
                >
                  Save Version
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Create Master Record Modal */}
      {createModalOpen && (
        <div
          data-testid="create-master-modal"
          style={{
            position: 'fixed',
            inset: 0,
            backgroundColor: 'rgba(0,0,0,0.7)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 1000,
          }}
        >
          <div
            style={{
              backgroundColor: 'var(--bg-secondary)',
              borderRadius: '8px',
              border: '1px solid var(--border-color)',
              padding: '1.5rem',
              width: '460px',
              maxWidth: '90vw',
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
              <h3 style={{ margin: 0 }}>Add New {selectedMaster} Record</h3>
              <button onClick={() => setCreateModalOpen(false)} style={{ background: 'none', border: 'none', color: '#94a3b8', cursor: 'pointer' }}>✕</button>
            </div>

            {createError && (
              <div style={{ padding: '0.5rem 0.75rem', backgroundColor: '#7f1d1d', color: '#fca5a5', borderRadius: '6px', fontSize: '0.8125rem', marginBottom: '1rem' }}>
                {createError}
              </div>
            )}

            <form onSubmit={handleSaveCreate} style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
              <div>
                <label style={{ display: 'block', fontSize: '0.8125rem', color: 'var(--text-secondary)', marginBottom: '0.25rem' }}>
                  Unique Code Identifier
                </label>
                <input
                  type="text"
                  data-testid="create-master-code-input"
                  required
                  placeholder="e.g. CORE_PAYMENTS"
                  value={newCode}
                  onChange={(e) => setNewCode(e.target.value)}
                  style={{ width: '100%', padding: '0.45rem', borderRadius: '6px', border: '1px solid var(--border-color)', backgroundColor: 'var(--bg-primary)', color: 'var(--text-primary)' }}
                />
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '0.8125rem', color: 'var(--text-secondary)', marginBottom: '0.25rem' }}>
                  Display Name
                </label>
                <input
                  type="text"
                  data-testid="create-master-name-input"
                  required
                  placeholder="e.g. Core Payments Service"
                  value={newDisplayName}
                  onChange={(e) => setNewDisplayName(e.target.value)}
                  style={{ width: '100%', padding: '0.45rem', borderRadius: '6px', border: '1px solid var(--border-color)', backgroundColor: 'var(--bg-primary)', color: 'var(--text-primary)' }}
                />
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '0.8125rem', color: 'var(--text-secondary)', marginBottom: '0.25rem' }}>
                  Description (Optional)
                </label>
                <input
                  type="text"
                  value={newDescription}
                  onChange={(e) => setNewDescription(e.target.value)}
                  style={{ width: '100%', padding: '0.45rem', borderRadius: '6px', border: '1px solid var(--border-color)', backgroundColor: 'var(--bg-primary)', color: 'var(--text-primary)' }}
                />
              </div>

              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.75rem', marginTop: '0.5rem' }}>
                <button
                  type="button"
                  onClick={() => setCreateModalOpen(false)}
                  style={{ padding: '0.4rem 0.8rem', borderRadius: '6px', border: '1px solid var(--border-color)', backgroundColor: 'transparent', color: 'var(--text-secondary)', cursor: 'pointer' }}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  data-testid="create-master-submit-btn"
                  style={{ padding: '0.4rem 1rem', borderRadius: '6px', border: 'none', backgroundColor: '#0284c7', color: '#ffffff', cursor: 'pointer', fontWeight: 600 }}
                >
                  Create Record
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* CSV Import with Dry Run Modal */}
      {importModalOpen && (
        <div
          data-testid="import-master-modal"
          style={{
            position: 'fixed',
            inset: 0,
            backgroundColor: 'rgba(0,0,0,0.7)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 1000,
          }}
        >
          <div
            style={{
              backgroundColor: 'var(--bg-secondary)',
              borderRadius: '8px',
              border: '1px solid var(--border-color)',
              padding: '1.5rem',
              width: '600px',
              maxWidth: '90vw',
              maxHeight: '90vh',
              overflowY: 'auto',
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
              <h3 style={{ margin: 0 }}>Import CSV with Dry Run: {selectedMaster}</h3>
              <button onClick={() => setImportModalOpen(false)} style={{ background: 'none', border: 'none', color: '#94a3b8', cursor: 'pointer' }}>✕</button>
            </div>

            <p style={{ margin: '0 0 1rem 0', fontSize: '0.8125rem', color: 'var(--text-secondary)' }}>
              Paste CSV text formatted with header columns <code>code,display_name,description</code>. You can perform a non-mutating dry run to preview changes before execution.
            </p>

            <textarea
              rows={6}
              data-testid="import-csv-textarea"
              value={csvContent}
              onChange={(e) => setCsvContent(e.target.value)}
              style={{
                width: '100%',
                padding: '0.5rem',
                borderRadius: '6px',
                border: '1px solid var(--border-color)',
                backgroundColor: '#0f172a',
                color: '#e2e8f0',
                fontFamily: 'monospace',
                fontSize: '0.8125rem',
                boxSizing: 'border-box',
              }}
            />

            {/* Dry Run Preview Summary */}
            {dryRunResult && (
              <div
                data-testid="dry-run-result-box"
                style={{
                  marginTop: '1rem',
                  padding: '1rem',
                  backgroundColor: dryRunResult.valid ? 'rgba(16, 185, 129, 0.1)' : 'rgba(239, 68, 68, 0.1)',
                  borderRadius: '6px',
                  border: `1px solid ${dryRunResult.valid ? '#10b981' : '#ef4444'}`,
                  fontSize: '0.8125rem',
                }}
              >
                <div style={{ fontWeight: 600, color: dryRunResult.valid ? '#34d399' : '#f87171', marginBottom: '0.5rem' }}>
                  {dryRunResult.valid ? '✓ Dry Run Validation Passed' : '✗ Dry Run Validation Failed'}
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.5rem' }}>
                  <div>Total parsed: <strong>{dryRunResult.total_records}</strong></div>
                  <div>Records to add: <strong style={{ color: '#34d399' }}>{dryRunResult.to_add}</strong></div>
                  <div>Records to update: <strong style={{ color: '#38bdf8' }}>{dryRunResult.to_update}</strong></div>
                </div>
                {dryRunResult.errors.length > 0 && (
                  <div style={{ marginTop: '0.5rem', color: '#f87171' }}>
                    <strong>Errors:</strong> {dryRunResult.errors.join('; ')}
                  </div>
                )}
                {dryRunResult.warnings.length > 0 && (
                  <div style={{ marginTop: '0.5rem', color: '#fbbf24' }}>
                    <strong>Warnings:</strong> {dryRunResult.warnings.join('; ')}
                  </div>
                )}
              </div>
            )}

            {importMessage && (
              <div
                data-testid="import-status-message"
                style={{
                  marginTop: '1rem',
                  padding: '0.75rem',
                  borderRadius: '6px',
                  fontSize: '0.8125rem',
                  backgroundColor: importMessage.type === 'success' ? '#064e3b' : '#7f1d1d',
                  color: importMessage.type === 'success' ? '#6ee7b7' : '#fca5a5',
                }}
              >
                {importMessage.text}
              </div>
            )}

            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '1.25rem' }}>
              <button
                type="button"
                data-testid="dry-run-validate-btn"
                disabled={importLoading}
                onClick={handleValidateDryRun}
                style={{
                  padding: '0.45rem 0.9rem',
                  borderRadius: '6px',
                  border: '1px solid #0284c7',
                  backgroundColor: 'rgba(2, 132, 199, 0.15)',
                  color: '#38bdf8',
                  cursor: 'pointer',
                  fontWeight: 600,
                  fontSize: '0.8125rem',
                }}
              >
                Validate Dry Run
              </button>

              <div style={{ display: 'flex', gap: '0.5rem' }}>
                <button
                  type="button"
                  onClick={() => setImportModalOpen(false)}
                  style={{ padding: '0.45rem 0.8rem', borderRadius: '6px', border: '1px solid var(--border-color)', backgroundColor: 'transparent', color: 'var(--text-secondary)', cursor: 'pointer' }}
                >
                  Close
                </button>
                <button
                  type="button"
                  data-testid="execute-import-btn"
                  disabled={importLoading || !dryRunResult?.valid}
                  onClick={handleExecuteImport}
                  style={{
                    padding: '0.45rem 1rem',
                    borderRadius: '6px',
                    border: 'none',
                    backgroundColor: dryRunResult?.valid ? '#10b981' : '#475569',
                    color: '#ffffff',
                    cursor: dryRunResult?.valid ? 'pointer' : 'not-allowed',
                    fontWeight: 600,
                    fontSize: '0.8125rem',
                  }}
                >
                  Execute Import
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
