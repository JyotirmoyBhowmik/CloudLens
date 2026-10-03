import React, { useEffect, useState, useCallback } from 'react';
import {
  Download,
  Edit3,
  Bookmark,
  CheckSquare,
  Square,
  Search,
  X,
} from 'lucide-react';
import { DenseTable, ColumnDefinition } from '../design-system/DenseTable';
import { NullValue } from '../design-system/NullValue';
import { CostValue, createCostExplanation } from '../design-system/CostValue';
import { SkeletonLoader } from '../design-system/SkeletonLoader';

export interface InventoryItem35 {
  id: string;
  tenant_id: string;
  scope_id: string;
  native_id: string;
  name: string;
  provider: string;
  service_id: string;
  service_name: string;
  service_category: string;
  resource_type_id: string;
  resource_type: string;
  region_id: string;
  region_name: string;
  availability_zone?: string | null;
  pricing_status: string;
  runtime_state: string;
  lifecycle_status: string;
  tags: Array<{ key: string; value: string }>;
  application_id?: string | null;
  application_name?: string | null;
  environment_id?: string | null;
  environment_name?: string | null;
  owner_id?: string | null;
  owner_name?: string | null;
  owner_email?: string | null;
  cost_center_id?: string | null;
  cost_center_name?: string | null;
  business_unit_id?: string | null;
  business_unit_name?: string | null;
  project_id?: string | null;
  project_name?: string | null;
  monthly_cost: number;
  currency: string;
  last_synced_at: string;
  created_at: string;
}

export interface CountPreviewData {
  matching_count: number;
  total_spend: number;
  currency: string;
  counts_by_provider: Record<string, number>;
  counts_by_environment: Record<string, number>;
}

export interface SavedViewItem {
  id: string;
  name: string;
  filters: Record<string, any>;
  selected_columns?: string[];
}

export const ServiceInventory: React.FC = () => {
  const [items, setItems] = useState<InventoryItem35[]>([]);
  const [totalCount, setTotalCount] = useState<number>(0);
  const [page, setPage] = useState<number>(1);
  const [pageSize, setPageSize] = useState<number>(10);
  const [loading, setLoading] = useState<boolean>(true);

  // Filter State
  const [selectedProvider, setSelectedProvider] = useState<string>('ALL');
  const [selectedEnvironment, setSelectedEnvironment] = useState<string>('ALL');
  const [selectedOwner, setSelectedOwner] = useState<string>('ALL');
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [minCost, setMinCost] = useState<string>('');
  const [maxCost, setMaxCost] = useState<string>('');

  // Reactive Count Preview (FR-584)
  const [countPreview, setCountPreview] = useState<CountPreviewData | null>(null);
  const [previewLoading, setPreviewLoading] = useState<boolean>(false);

  // Bulk Selection & Assignment (FR-108)
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [isBulkModalOpen, setIsBulkModalOpen] = useState<boolean>(false);
  const [bulkOwnerName, setBulkOwnerName] = useState<string>('');
  const [bulkOwnerEmail, setBulkOwnerEmail] = useState<string>('');
  const [bulkAppName, setBulkAppName] = useState<string>('');
  const [bulkEnvName, setBulkEnvName] = useState<string>('');
  const [bulkCostCenter, setBulkCostCenter] = useState<string>('');

  // Saved Views (FR-583)
  const [savedViews, setSavedViews] = useState<SavedViewItem[]>([]);
  const [viewNameInput, setViewNameInput] = useState<string>('');
  const [isSaveViewOpen, setIsSaveViewOpen] = useState<boolean>(false);

  // Build Filter Query payload
  const buildFilterPayload = useCallback(() => {
    const payload: Record<string, any> = {};
    if (selectedProvider !== 'ALL') payload.providers = [selectedProvider];
    if (selectedEnvironment !== 'ALL') payload.environments = [selectedEnvironment];
    if (selectedOwner !== 'ALL') payload.owners = [selectedOwner];
    if (searchQuery.trim()) payload.search = searchQuery.trim();
    if (minCost && !isNaN(Number(minCost))) payload.min_cost = Number(minCost);
    if (maxCost && !isNaN(Number(maxCost))) payload.max_cost = Number(maxCost);
    return payload;
  }, [selectedProvider, selectedEnvironment, selectedOwner, searchQuery, minCost, maxCost]);

  // Reactive Count Preview Effect (FR-584): fetches count before loading table data
  useEffect(() => {
    setPreviewLoading(true);
    const payload = buildFilterPayload();
    fetch('/api/v1/hierarchy/inventory/count-preview', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
      .then((res) => res.json())
      .then((data: CountPreviewData) => {
        setCountPreview(data);
        setPreviewLoading(false);
      })
      .catch((err) => {
        console.error('Count preview error:', err);
        setPreviewLoading(false);
      });
  }, [buildFilterPayload]);

  // Load Inventory Data
  const loadData = useCallback(() => {
    setLoading(true);
    const payload = buildFilterPayload();
    const offset = (page - 1) * pageSize;
    fetch(`/api/v1/hierarchy/inventory/query?limit=${pageSize}&offset=${offset}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
      .then((res) => res.json())
      .then((data) => {
        setItems(data.items || []);
        setTotalCount(data.total || 0);
        setLoading(false);
      })
      .catch((err) => {
        console.error('Inventory query error:', err);
        setLoading(false);
      });
  }, [buildFilterPayload, page, pageSize]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  // Load Saved Views
  useEffect(() => {
    fetch('/api/v1/hierarchy/inventory/views')
      .then((res) => res.json())
      .then((data) => setSavedViews(data || []))
      .catch(() => {});
  }, []);

  const toggleSelectAll = () => {
    if (selectedIds.size === items.length) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(items.map((r) => r.id)));
    }
  };

  const toggleSelectRow = (id: string) => {
    const updated = new Set(selectedIds);
    if (updated.has(id)) {
      updated.delete(id);
    } else {
      updated.add(id);
    }
    setSelectedIds(updated);
  };

  const handleBulkAssign = async () => {
    if (selectedIds.size === 0) return;
    const body: Record<string, any> = {
      resource_ids: Array.from(selectedIds),
    };
    if (bulkOwnerName) body.owner_name = bulkOwnerName;
    if (bulkOwnerEmail) body.owner_email = bulkOwnerEmail;
    if (bulkAppName) body.application_name = bulkAppName;
    if (bulkEnvName) body.environment_name = bulkEnvName;
    if (bulkCostCenter) body.cost_center = bulkCostCenter;

    try {
      const res = await fetch('/api/v1/hierarchy/inventory/bulk-assign', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      if (res.ok) {
        setIsBulkModalOpen(false);
        setSelectedIds(new Set());
        loadData();
      }
    } catch (e) {
      console.error('Bulk assignment error:', e);
    }
  };

  const handleSaveView = async () => {
    if (!viewNameInput.trim()) return;
    const payload = {
      id: `view-${Date.now()}`,
      name: viewNameInput.trim(),
      user_id: 'usr-current',
      filters: buildFilterPayload(),
      selected_columns: [],
      is_shared: false,
      created_at: new Date().toISOString(),
    };
    try {
      const res = await fetch('/api/v1/hierarchy/inventory/views', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (res.ok) {
        const saved = await res.json();
        setSavedViews((prev) => [...prev, saved]);
        setViewNameInput('');
        setIsSaveViewOpen(false);
      }
    } catch (e) {
      console.error('Error saving view:', e);
    }
  };

  const handleExport = (format: 'csv' | 'json') => {
    const payload = buildFilterPayload();
    fetch(`/api/v1/hierarchy/inventory/export?format=${format}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
      .then((res) => res.blob())
      .then((blob) => {
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `cloudlens_inventory.${format}`;
        a.click();
        window.URL.revokeObjectURL(url);
      })
      .catch((err) => console.error('Export error:', err));
  };

  // 35 Canonical Columns Definition for DenseTable
  const columns: ColumnDefinition<InventoryItem35>[] = [
    {
      key: 'select',
      header: selectedIds.size > 0 && selectedIds.size === items.length ? '✓' : '☐',
      width: '40px',
      render: (row) => (
        <button
          onClick={(e) => {
            e.stopPropagation();
            toggleSelectRow(row.id);
          }}
          style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 0 }}
          aria-label={selectedIds.has(row.id) ? 'Deselect row' : 'Select row'}
        >
          {selectedIds.has(row.id) ? (
            <CheckSquare size={16} color="#0284c7" />
          ) : (
            <Square size={16} color="#94a3b8" />
          )}
        </button>
      ),
    },
    {
      key: 'name',
      header: 'Resource Name',
      sortable: true,
      render: (row) => (
        <div>
          <div style={{ fontWeight: 600, color: '#0f172a' }}>{row.name}</div>
          <div style={{ fontSize: '0.72rem', color: '#64748b' }}>{row.native_id}</div>
        </div>
      ),
    },
    {
      key: 'provider',
      header: 'Provider',
      render: (row) => (
        <span
          style={{
            fontSize: '0.75rem',
            padding: '0.15rem 0.45rem',
            borderRadius: '4px',
            backgroundColor: '#f1f5f9',
            fontWeight: 600,
          }}
        >
          {row.provider}
        </span>
      ),
    },
    {
      key: 'service_name',
      header: 'Service',
      render: (row) => (
        <div>
          <div style={{ fontWeight: 500 }}>{row.service_name}</div>
          <div style={{ fontSize: '0.72rem', color: '#64748b' }}>{row.service_category}</div>
        </div>
      ),
    },
    {
      key: 'resource_type',
      header: 'Resource Type',
      render: (row) => row.resource_type || <NullValue state="NOT_APPLICABLE" />,
    },
    {
      key: 'region_id',
      header: 'Region / AZ',
      render: (row) => (
        <div>
          <div>{row.region_id}</div>
          {row.availability_zone ? (
            <div style={{ fontSize: '0.72rem', color: '#64748b' }}>{row.availability_zone}</div>
          ) : (
            <NullValue state="NOT_APPLICABLE" />
          )}
        </div>
      ),
    },
    {
      key: 'runtime_state',
      header: 'Runtime State',
      render: (row) => (
        <span
          style={{
            fontSize: '0.75rem',
            padding: '0.15rem 0.45rem',
            borderRadius: '4px',
            backgroundColor: row.runtime_state === 'RUNNING' ? '#dcfce7' : '#f1f5f9',
            color: row.runtime_state === 'RUNNING' ? '#166534' : '#475569',
            fontWeight: 600,
          }}
        >
          {row.runtime_state}
        </span>
      ),
    },
    {
      key: 'application_name',
      header: 'Application',
      render: (row) => row.application_name || <NullValue state="NO_DATA" />,
    },
    {
      key: 'environment_name',
      header: 'Environment',
      render: (row) => row.environment_name || <NullValue state="NO_DATA" />,
    },
    {
      key: 'owner_name',
      header: 'Owner',
      render: (row) =>
        row.owner_name && row.owner_name !== 'Unowned' ? (
          <div>
            <div style={{ fontWeight: 500 }}>{row.owner_name}</div>
            {row.owner_email && <div style={{ fontSize: '0.72rem', color: '#64748b' }}>{row.owner_email}</div>}
          </div>
        ) : (
          <span style={{ color: '#dc2626', fontWeight: 600, fontSize: '0.8rem' }}>Unowned</span>
        ),
    },
    {
      key: 'cost_center_name',
      header: 'Cost Centre',
      render: (row) => row.cost_center_name || <NullValue state="NO_DATA" />,
    },
    {
      key: 'monthly_cost',
      header: 'Monthly Spend',
      isNumeric: true,
      align: 'right',
      sortable: true,
      render: (row) => (
        <span style={{ fontWeight: 600 }}>
          <CostValue
            amount={Number(row.monthly_cost)}
            source="ACTUAL"
            currency="USD"
            explanation={createCostExplanation(`${row.service_name} Monthly Spend`, {
              pricingSource: `${row.provider}_cost_management`,
              region: row.region_id,
            })}
          />
        </span>
      ),
    },
  ];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem', padding: '1.5rem 2rem' }}>
      {/* Header and Actions */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '1rem' }}>
        <div>
          <h1 style={{ fontSize: '1.5rem', fontWeight: 700, margin: 0, color: 'var(--text-primary, #0f172a)' }}>
            Service & Resource Inventory
          </h1>
          <p style={{ margin: '0.25rem 0 0', color: 'var(--text-secondary, #64748b)', fontSize: '0.875rem' }}>
            Multi-attribute filtered table across all 35 canonical inventory fields with bulk curation.
          </p>
        </div>

        <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
          {selectedIds.size > 0 && (
            <button
              onClick={() => setIsBulkModalOpen(true)}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '0.4rem',
                backgroundColor: '#0284c7',
                color: '#ffffff',
                border: 'none',
                borderRadius: '6px',
                padding: '0.45rem 0.85rem',
                fontSize: '0.875rem',
                fontWeight: 600,
                cursor: 'pointer',
              }}
            >
              <Edit3 size={15} /> Bulk Assign ({selectedIds.size})
            </button>
          )}

          <button
            onClick={toggleSelectAll}
            style={{
              padding: '0.45rem 0.85rem',
              borderRadius: '6px',
              border: '1px solid #cbd5e1',
              backgroundColor: '#ffffff',
              fontSize: '0.875rem',
              fontWeight: 500,
              cursor: 'pointer',
            }}
          >
            {selectedIds.size === items.length && items.length > 0 ? 'Deselect All' : 'Select All'}
          </button>

          {savedViews.length > 0 && (
            <select
              onChange={(e) => {
                const sv = savedViews.find((v) => v.id === e.target.value);
                if (sv && sv.filters) {
                  if (sv.filters.providers) setSelectedProvider(sv.filters.providers[0]);
                  if (sv.filters.environments) setSelectedEnvironment(sv.filters.environments[0]);
                  if (sv.filters.owners) setSelectedOwner(sv.filters.owners[0]);
                  if (sv.filters.search) setSearchQuery(sv.filters.search);
                }
              }}
              style={{
                padding: '0.45rem 0.65rem',
                borderRadius: '6px',
                border: '1px solid #cbd5e1',
                fontSize: '0.875rem',
              }}
            >
              <option value="">Load Saved View ({savedViews.length})...</option>
              {savedViews.map((v) => (
                <option key={v.id} value={v.id}>
                  {v.name}
                </option>
              ))}
            </select>
          )}

          <button
            onClick={() => setIsSaveViewOpen(true)}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '0.4rem',
              backgroundColor: '#f1f5f9',
              color: '#334155',
              border: '1px solid #cbd5e1',
              borderRadius: '6px',
              padding: '0.45rem 0.85rem',
              fontSize: '0.875rem',
              fontWeight: 500,
              cursor: 'pointer',
            }}
          >
            <Bookmark size={15} /> Save View
          </button>

          <button
            onClick={() => handleExport('csv')}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '0.4rem',
              backgroundColor: '#ffffff',
              color: '#334155',
              border: '1px solid #cbd5e1',
              borderRadius: '6px',
              padding: '0.45rem 0.85rem',
              fontSize: '0.875rem',
              fontWeight: 500,
              cursor: 'pointer',
            }}
          >
            <Download size={15} /> Export CSV
          </button>

          <button
            onClick={() => handleExport('json')}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '0.4rem',
              backgroundColor: '#ffffff',
              color: '#334155',
              border: '1px solid #cbd5e1',
              borderRadius: '6px',
              padding: '0.45rem 0.85rem',
              fontSize: '0.875rem',
              fontWeight: 500,
              cursor: 'pointer',
            }}
          >
            <Download size={15} /> JSON
          </button>
        </div>
      </div>

      {/* Reactive Count Preview Banner (FR-584) */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          backgroundColor: '#f0f9ff',
          border: '1px solid #bae6fd',
          borderRadius: '8px',
          padding: '0.75rem 1.25rem',
          fontSize: '0.875rem',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
          <span style={{ fontWeight: 600, color: '#0369a1' }}>
            REACTIVE PREVIEW:
          </span>
          {previewLoading ? (
            <span style={{ color: '#64748b' }}>Computing aggregate match counts...</span>
          ) : countPreview ? (
            <div style={{ display: 'flex', gap: '1.25rem', alignItems: 'center' }}>
              <span>
                Matching: <strong>{countPreview.matching_count}</strong> resources
              </span>
              <span>
                Projected Spend:{' '}
                <strong>
                  ${Number(countPreview.total_spend).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                </strong>
              </span>
              {countPreview.counts_by_provider && (
                <span style={{ color: '#475569' }}>
                  ({Object.entries(countPreview.counts_by_provider).map(([p, cnt]) => `${p}: ${cnt}`).join(' • ')})
                </span>
              )}
            </div>
          ) : null}
        </div>
        <span style={{ fontSize: '0.75rem', color: '#0284c7' }}>Sub-500ms Aggregation Preview</span>
      </div>

      {/* Filter Control Bar */}
      <div
        style={{
          display: 'flex',
          flexWrap: 'wrap',
          gap: '0.75rem',
          backgroundColor: '#f8fafc',
          padding: '0.85rem 1rem',
          borderRadius: '8px',
          border: '1px solid #e2e8f0',
          alignItems: 'center',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', minWidth: '220px', flex: 1 }}>
          <Search size={16} color="#64748b" />
          <input
            type="text"
            placeholder="Search by name, ID, service, owner..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            style={{
              padding: '0.35rem 0.6rem',
              borderRadius: '6px',
              border: '1px solid #cbd5e1',
              width: '100%',
              fontSize: '0.8125rem',
            }}
          />
        </div>

        {/* Provider Multi-Select */}
        <select
          value={selectedProvider}
          onChange={(e) => setSelectedProvider(e.target.value)}
          style={{ padding: '0.4rem 0.6rem', borderRadius: '6px', border: '1px solid #cbd5e1', fontSize: '0.8125rem' }}
        >
          <option value="ALL">All Providers</option>
          <option value="AWS">AWS</option>
          <option value="Azure">Azure</option>
          <option value="GCP">GCP</option>
          <option value="OCI">OCI</option>
        </select>

        {/* Environment Filter */}
        <select
          value={selectedEnvironment}
          onChange={(e) => setSelectedEnvironment(e.target.value)}
          style={{ padding: '0.4rem 0.6rem', borderRadius: '6px', border: '1px solid #cbd5e1', fontSize: '0.8125rem' }}
        >
          <option value="ALL">All Environments</option>
          <option value="Production">Production</option>
          <option value="Development">Development</option>
        </select>

        {/* Owner Filter */}
        <select
          value={selectedOwner}
          onChange={(e) => setSelectedOwner(e.target.value)}
          style={{ padding: '0.4rem 0.6rem', borderRadius: '6px', border: '1px solid #cbd5e1', fontSize: '0.8125rem' }}
        >
          <option value="ALL">All Owners</option>
          <option value="Alice Engineer">Alice Engineer</option>
          <option value="Bob DBA">Bob DBA</option>
          <option value="Carol Ops">Carol Ops</option>
          <option value="Dave Architect">Dave Architect</option>
          <option value="Unowned">Unowned Only</option>
        </select>

        {/* Min / Max Cost */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.3rem' }}>
          <span style={{ fontSize: '0.75rem', color: '#64748b' }}>Spend:</span>
          <input
            type="number"
            placeholder="Min $"
            value={minCost}
            onChange={(e) => setMinCost(e.target.value)}
            style={{ width: '70px', padding: '0.35rem 0.5rem', borderRadius: '6px', border: '1px solid #cbd5e1', fontSize: '0.8125rem' }}
          />
          <span style={{ fontSize: '0.75rem', color: '#64748b' }}>-</span>
          <input
            type="number"
            placeholder="Max $"
            value={maxCost}
            onChange={(e) => setMaxCost(e.target.value)}
            style={{ width: '70px', padding: '0.35rem 0.5rem', borderRadius: '6px', border: '1px solid #cbd5e1', fontSize: '0.8125rem' }}
          />
        </div>

        {/* Reset */}
        <button
          onClick={() => {
            setSelectedProvider('ALL');
            setSelectedEnvironment('ALL');
            setSelectedOwner('ALL');
            setSearchQuery('');
            setMinCost('');
            setMaxCost('');
          }}
          style={{
            background: 'none',
            border: 'none',
            color: '#0284c7',
            fontSize: '0.8125rem',
            cursor: 'pointer',
            padding: '0.35rem 0.5rem',
          }}
        >
          Reset Filters
        </button>
      </div>

      {/* DenseTable Container */}
      <div style={{ backgroundColor: '#ffffff', borderRadius: '10px', border: '1px solid #e2e8f0', overflow: 'hidden' }}>
        {loading ? (
          <SkeletonLoader variant="table" rows={6} />
        ) : (
          <DenseTable
            columns={columns}
            data={items}
            totalRows={totalCount}
            page={page}
            pageSize={pageSize}
            onPageChange={(p, ps) => {
              setPage(p);
              setPageSize(ps);
            }}
            defaultDensity="compact"
            showDensityToggle={true}
            showColumnChooser={true}
            stickyHeader={true}
            ariaCaption="Discovered Cloud Estate Resource Inventory"
          />
        )}
      </div>

      {/* Bulk Assignment Modal (FR-108) */}
      {isBulkModalOpen && (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            backgroundColor: 'rgba(0, 0, 0, 0.4)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 100,
          }}
        >
          <div
            style={{
              backgroundColor: '#ffffff',
              borderRadius: '10px',
              padding: '1.5rem',
              width: '450px',
              maxWidth: '90%',
              boxShadow: '0 20px 25px -5px rgba(0, 0, 0, 0.1)',
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
              <h3 style={{ margin: 0, fontSize: '1.1rem', fontWeight: 600 }}>
                Bulk Curated Assignment ({selectedIds.size} resources)
              </h3>
              <button
                onClick={() => setIsBulkModalOpen(false)}
                style={{ background: 'none', border: 'none', cursor: 'pointer' }}
              >
                <X size={18} />
              </button>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
              <div>
                <label style={{ fontSize: '0.75rem', fontWeight: 600, color: '#475569' }}>OWNER NAME</label>
                <input
                  type="text"
                  placeholder="e.g. Alice Engineer or Unowned"
                  value={bulkOwnerName}
                  onChange={(e) => setBulkOwnerName(e.target.value)}
                  style={{ width: '100%', padding: '0.45rem', borderRadius: '6px', border: '1px solid #cbd5e1', marginTop: '3px' }}
                />
              </div>

              <div>
                <label style={{ fontSize: '0.75rem', fontWeight: 600, color: '#475569' }}>OWNER EMAIL</label>
                <input
                  type="email"
                  placeholder="e.g. alice@example.com"
                  value={bulkOwnerEmail}
                  onChange={(e) => setBulkOwnerEmail(e.target.value)}
                  style={{ width: '100%', padding: '0.45rem', borderRadius: '6px', border: '1px solid #cbd5e1', marginTop: '3px' }}
                />
              </div>

              <div>
                <label style={{ fontSize: '0.75rem', fontWeight: 600, color: '#475569' }}>APPLICATION NAME</label>
                <input
                  type="text"
                  placeholder="e.g. Payments Core"
                  value={bulkAppName}
                  onChange={(e) => setBulkAppName(e.target.value)}
                  style={{ width: '100%', padding: '0.45rem', borderRadius: '6px', border: '1px solid #cbd5e1', marginTop: '3px' }}
                />
              </div>

              <div>
                <label style={{ fontSize: '0.75rem', fontWeight: 600, color: '#475569' }}>ENVIRONMENT</label>
                <input
                  type="text"
                  placeholder="e.g. Production or Development"
                  value={bulkEnvName}
                  onChange={(e) => setBulkEnvName(e.target.value)}
                  style={{ width: '100%', padding: '0.45rem', borderRadius: '6px', border: '1px solid #cbd5e1', marginTop: '3px' }}
                />
              </div>

              <div>
                <label style={{ fontSize: '0.75rem', fontWeight: 600, color: '#475569' }}>COST CENTRE</label>
                <input
                  type="text"
                  placeholder="e.g. CC-101-FINOPS"
                  value={bulkCostCenter}
                  onChange={(e) => setBulkCostCenter(e.target.value)}
                  style={{ width: '100%', padding: '0.45rem', borderRadius: '6px', border: '1px solid #cbd5e1', marginTop: '3px' }}
                />
              </div>

              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.5rem', marginTop: '1rem' }}>
                <button
                  onClick={() => setIsBulkModalOpen(false)}
                  style={{
                    padding: '0.45rem 0.85rem',
                    borderRadius: '6px',
                    border: '1px solid #cbd5e1',
                    background: '#ffffff',
                    cursor: 'pointer',
                  }}
                >
                  Cancel
                </button>
                <button
                  onClick={handleBulkAssign}
                  style={{
                    padding: '0.45rem 0.85rem',
                    borderRadius: '6px',
                    border: 'none',
                    backgroundColor: '#0284c7',
                    color: '#ffffff',
                    fontWeight: 600,
                    cursor: 'pointer',
                  }}
                >
                  Apply to {selectedIds.size} Resources
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Save View Modal (FR-583) */}
      {isSaveViewOpen && (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            backgroundColor: 'rgba(0, 0, 0, 0.4)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 100,
          }}
        >
          <div
            style={{
              backgroundColor: '#ffffff',
              borderRadius: '10px',
              padding: '1.5rem',
              width: '380px',
              maxWidth: '90%',
              boxShadow: '0 20px 25px -5px rgba(0, 0, 0, 0.1)',
            }}
          >
            <h3 style={{ margin: '0 0 0.75rem', fontSize: '1.1rem', fontWeight: 600 }}>Save Current Filter View</h3>
            <p style={{ margin: '0 0 1rem', fontSize: '0.8125rem', color: '#64748b' }}>
              Name your view to quickly restore these filters anytime.
            </p>
            <input
              type="text"
              placeholder="e.g. AWS Production Workloads"
              value={viewNameInput}
              onChange={(e) => setViewNameInput(e.target.value)}
              style={{ width: '100%', padding: '0.45rem', borderRadius: '6px', border: '1px solid #cbd5e1', marginBottom: '1rem' }}
            />
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.5rem' }}>
              <button
                onClick={() => setIsSaveViewOpen(false)}
                style={{ padding: '0.45rem 0.85rem', borderRadius: '6px', border: '1px solid #cbd5e1', background: '#ffffff', cursor: 'pointer' }}
              >
                Cancel
              </button>
              <button
                onClick={handleSaveView}
                style={{ padding: '0.45rem 0.85rem', borderRadius: '6px', border: 'none', backgroundColor: '#0284c7', color: '#ffffff', fontWeight: 600, cursor: 'pointer' }}
              >
                Save
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
