import React, { useState, useEffect } from 'react';
import { Filter, X, Bookmark, Save, Trash2, ShieldAlert } from 'lucide-react';

export interface FilterItem {
  id: string;
  field: string;
  operator: 'eq' | 'neq' | 'contains' | 'in';
  value: string;
  displayLabel?: string;
}

export interface SavedView {
  id: string;
  name: string;
  filters: FilterItem[];
}

export interface FilterBarProps {
  filters: FilterItem[];
  onChange: (filters: FilterItem[]) => void;
  availableFields?: Array<{ key: string; label: string; options?: string[] }>;
  rbacScopeDisclosure?: string;
  totalRecordsCount?: number;
  filteredRecordsCount?: number;
  onClearAll?: () => void;
  enableUrlSync?: boolean;
  className?: string;
}

/**
 * Utility: Encodes FilterItem array into a clean URL search param string.
 */
export function serializeFiltersToQuery(filters: FilterItem[]): string {
  if (!filters || filters.length === 0) return '';
  return encodeURIComponent(JSON.stringify(filters));
}

/**
 * Utility: Parses FilterItem array from a URL search query string.
 */
export function parseFiltersFromQuery(queryString: string): FilterItem[] {
  if (!queryString) return [];
  try {
    const parsed = JSON.parse(decodeURIComponent(queryString));
    if (Array.isArray(parsed)) return parsed;
    return [];
  } catch {
    return [];
  }
}

/**
 * FilterBar Component
 * Enforces BBP Section 31:
 * - "persistent combinable filter bar with chip display, saved views and URL-encoded state"
 * - "no silent filtering: disclose when filtering has occurred"
 * Acceptance: "Filter state round-trips through the URL and restores exactly."
 */
export const FilterBar: React.FC<FilterBarProps> = ({
  filters,
  onChange,
  availableFields = [
    { key: 'provider', label: 'Cloud Provider', options: ['AWS', 'AZURE', 'GCP', 'OCI'] },
    { key: 'environment', label: 'Environment', options: ['PROD', 'STAGING', 'DEV', 'TEST'] },
    { key: 'thresholdState', label: 'Threshold Band', options: ['NORMAL', 'WARNING', 'HIGH', 'CRITICAL'] },
    { key: 'costSource', label: 'Cost Source', options: ['ACTUAL', 'ESTIMATED', 'FORECAST', 'MANUAL'] },
  ],
  rbacScopeDisclosure,
  totalRecordsCount,
  filteredRecordsCount,
  onClearAll,
  enableUrlSync = true,
  className = '',
}) => {
  const [selectedField, setSelectedField] = useState<string>(availableFields[0]?.key || 'provider');
  const [filterValue, setFilterValue] = useState<string>('');
  const [savedViews, setSavedViews] = useState<SavedView[]>(() => {
    try {
      const stored = localStorage.getItem('cloudlens_saved_views');
      return stored ? JSON.parse(stored) : [];
    } catch {
      return [];
    }
  });
  const [newViewName, setNewViewName] = useState('');
  const [showSaveModal, setShowSaveModal] = useState(false);
  const [selectedViewId, setSelectedViewId] = useState<string | null>(null);

  // 1. URL Sync Round-Trip
  useEffect(() => {
    if (!enableUrlSync) return;

    // On initial mount, restore filters from URL if present
    const params = new URLSearchParams(window.location.search);
    const filterQuery = params.get('filters');
    if (filterQuery) {
      const restored = parseFiltersFromQuery(filterQuery);
      if (restored.length > 0 && JSON.stringify(restored) !== JSON.stringify(filters)) {
        onChange(restored);
      }
    }
  }, []);

  // Update URL search params when filters change
  useEffect(() => {
    if (!enableUrlSync) return;

    const params = new URLSearchParams(window.location.search);
    if (filters.length > 0) {
      params.set('filters', serializeFiltersToQuery(filters));
    } else {
      params.delete('filters');
    }

    const newUrl = `${window.location.pathname}${params.toString() ? '?' + params.toString() : ''}`;
    window.history.replaceState(null, '', newUrl);
  }, [filters, enableUrlSync]);

  const addFilter = () => {
    if (!filterValue.trim()) return;

    const fieldConfig = availableFields.find((f) => f.key === selectedField);
    const fieldLabel = fieldConfig ? fieldConfig.label : selectedField;

    const newFilter: FilterItem = {
      id: `flt-${Date.now()}-${Math.random().toString(36).substr(2, 4)}`,
      field: selectedField,
      operator: 'eq',
      value: filterValue.trim(),
      displayLabel: `${fieldLabel}: ${filterValue.trim()}`,
    };

    // Avoid duplicate filters
    if (filters.some((f) => f.field === newFilter.field && f.value === newFilter.value)) {
      return;
    }

    onChange([...filters, newFilter]);
    setFilterValue('');
  };

  const removeFilter = (id: string) => {
    onChange(filters.filter((f) => f.id !== id));
  };

  const handleClearAll = () => {
    if (onClearAll) {
      onClearAll();
    } else {
      onChange([]);
    }
  };

  const handleSaveView = () => {
    if (!newViewName.trim()) return;
    const view: SavedView = {
      id: `view-${Date.now()}`,
      name: newViewName.trim(),
      filters: [...filters],
    };
    const updated = [...savedViews, view];
    setSavedViews(updated);
    try {
      localStorage.setItem('cloudlens_saved_views', JSON.stringify(updated));
    } catch {
      // localStorage failure fallback
    }
    setNewViewName('');
    setShowSaveModal(false);
  };

  const handleLoadView = (view: SavedView) => {
    onChange(view.filters);
  };

  const handleDeleteView = (viewId: string) => {
    const updated = savedViews.filter((v) => v.id !== viewId);
    setSavedViews(updated);
    try {
      localStorage.setItem('cloudlens_saved_views', JSON.stringify(updated));
    } catch {
      // fallback
    }
  };

  const currentFieldOptions = availableFields.find((f) => f.key === selectedField)?.options;

  return (
    <div
      className={`cloudlens-filter-bar ${className}`}
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: '0.6rem',
        padding: '0.75rem 1rem',
        backgroundColor: 'var(--bg-secondary)',
        border: '1px solid var(--border-color)',
        borderRadius: '8px',
      }}
    >
      {/* RBAC Scope Disclosure Banner (No Silent Filtering) */}
      {rbacScopeDisclosure && (
        <div
          role="note"
          aria-label="RBAC Scope Filtering Disclosure"
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '0.45rem',
            padding: '0.35rem 0.75rem',
            borderRadius: '6px',
            backgroundColor: 'rgba(2, 132, 199, 0.1)',
            border: '1px solid rgba(2, 132, 199, 0.3)',
            color: '#38bdf8',
            fontSize: '0.8125rem',
          }}
        >
          <ShieldAlert size={14} aria-hidden="true" />
          <span>
            <strong>Scope Disclosure:</strong> {rbacScopeDisclosure}
          </span>
        </div>
      )}

      {/* Primary Filter Input Controls */}
      <div
        style={{
          display: 'flex',
          flexWrap: 'wrap',
          alignItems: 'center',
          gap: '0.5rem',
          justifyContent: 'space-between',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.35rem', color: 'var(--text-secondary)' }}>
            <Filter size={14} aria-hidden="true" />
            <span style={{ fontSize: '0.8125rem', fontWeight: 600 }}>Filter by:</span>
          </div>

          <label htmlFor="filter-field-select" className="sr-only" style={{ display: 'none' }}>
            Select field to filter
          </label>
          <select
            id="filter-field-select"
            value={selectedField}
            onChange={(e) => setSelectedField(e.target.value)}
            aria-label="Select field to filter"
            style={{
              padding: '0.35rem 0.6rem',
              borderRadius: '6px',
              border: '1px solid var(--border-color)',
              backgroundColor: 'var(--bg-primary, #0f172a)',
              color: 'var(--text-primary)',
              fontSize: '0.8125rem',
            }}
          >
            {availableFields.map((f) => (
              <option key={f.key} value={f.key}>
                {f.label}
              </option>
            ))}
          </select>

          {currentFieldOptions ? (
            <select
              value={filterValue}
              onChange={(e) => setFilterValue(e.target.value)}
              aria-label="Select filter value"
              style={{
                padding: '0.35rem 0.6rem',
                borderRadius: '6px',
                border: '1px solid var(--border-color)',
                backgroundColor: 'var(--bg-primary, #0f172a)',
                color: 'var(--text-primary)',
                fontSize: '0.8125rem',
              }}
            >
              <option value="">-- Choose Value --</option>
              {currentFieldOptions.map((opt) => (
                <option key={opt} value={opt}>
                  {opt}
                </option>
              ))}
            </select>
          ) : (
            <input
              type="text"
              placeholder="Enter value..."
              value={filterValue}
              onChange={(e) => setFilterValue(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') addFilter();
              }}
              aria-label="Enter filter value"
              style={{
                padding: '0.35rem 0.6rem',
                borderRadius: '6px',
                border: '1px solid var(--border-color)',
                backgroundColor: 'var(--bg-primary, #0f172a)',
                color: 'var(--text-primary)',
                fontSize: '0.8125rem',
                width: '160px',
              }}
            />
          )}

          <button
            type="button"
            onClick={addFilter}
            aria-label="Apply filter criteria"
            style={{
              padding: '0.35rem 0.75rem',
              borderRadius: '6px',
              border: '1px solid var(--accent-blue, #38bdf8)',
              backgroundColor: 'rgba(56, 189, 248, 0.15)',
              color: 'var(--accent-blue, #38bdf8)',
              fontSize: '0.8125rem',
              fontWeight: 500,
              cursor: 'pointer',
            }}
          >
            Add Filter
          </button>
        </div>

        {/* Saved Views Control */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          {savedViews.length > 0 && (
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.3rem' }}>
              <Bookmark size={13} aria-hidden="true" style={{ color: 'var(--text-secondary)' }} />
              <label htmlFor="saved-view-select" className="sr-only" style={{ display: 'none' }}>
                Load saved view
              </label>
              <select
                id="saved-view-select"
                value={selectedViewId || ''}
                onChange={(e) => {
                  const val = e.target.value;
                  setSelectedViewId(val);
                  const view = savedViews.find((v) => v.id === val);
                  if (view) handleLoadView(view);
                }}
                aria-label="Load saved view"
                style={{
                  padding: '0.3rem 0.5rem',
                  borderRadius: '6px',
                  border: '1px solid var(--border-color)',
                  backgroundColor: 'var(--bg-primary)',
                  color: 'var(--text-secondary)',
                  fontSize: '0.75rem',
                }}
              >
                <option value="" disabled>
                  Load Saved View...
                </option>
                {savedViews.map((v) => (
                  <option key={v.id} value={v.id}>
                    {v.name} ({v.filters.length} filters)
                  </option>
                ))}
              </select>

              {selectedViewId && (
                <button
                  type="button"
                  onClick={() => {
                    handleDeleteView(selectedViewId);
                    setSelectedViewId(null);
                  }}
                  aria-label="Delete selected saved view preset"
                  title="Delete saved view"
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    padding: '0.3rem',
                    borderRadius: '4px',
                    border: '1px solid var(--border-color)',
                    backgroundColor: 'transparent',
                    color: '#f87171',
                    cursor: 'pointer',
                  }}
                >
                  <Trash2 size={12} aria-hidden="true" />
                </button>
              )}
            </div>
          )}

          <button
            type="button"
            onClick={() => setShowSaveModal(true)}
            disabled={filters.length === 0}
            aria-label="Save current view"
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '0.3rem',
              padding: '0.3rem 0.6rem',
              borderRadius: '6px',
              border: '1px solid var(--border-color)',
              backgroundColor: 'transparent',
              color: filters.length === 0 ? 'var(--border-color)' : 'var(--text-secondary)',
              fontSize: '0.75rem',
              cursor: filters.length === 0 ? 'not-allowed' : 'pointer',
            }}
          >
            <Save size={12} aria-hidden="true" />
            <span>Save View</span>
          </button>
        </div>
      </div>

      {/* Active Filter Chips & Result Count (No Silent Filtering) */}
      <div
        style={{
          display: 'flex',
          flexWrap: 'wrap',
          alignItems: 'center',
          gap: '0.4rem',
          minHeight: '26px',
          borderTop: '1px solid rgba(255, 255, 255, 0.05)',
          paddingTop: '0.4rem',
        }}
      >
        <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', marginRight: '0.4rem' }}>
          {filteredRecordsCount !== undefined && totalRecordsCount !== undefined ? (
            <span>
              Showing <strong>{filteredRecordsCount}</strong> of <strong>{totalRecordsCount}</strong> records
              {filters.length > 0 && ' (filtered)'}
            </span>
          ) : (
            <span>{filters.length} active filter(s)</span>
          )}
        </div>

        {filters.map((filter) => (
          <span
            key={filter.id}
            role="status"
            aria-label={`Active filter: ${filter.displayLabel || `${filter.field} equals ${filter.value}`}`}
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '0.3rem',
              padding: '0.15rem 0.5rem',
              borderRadius: '9999px',
              fontSize: '0.75rem',
              fontWeight: 500,
              backgroundColor: 'rgba(56, 189, 248, 0.1)',
              border: '1px solid rgba(56, 189, 248, 0.3)',
              color: '#38bdf8',
            }}
          >
            <span>{filter.displayLabel || `${filter.field}: ${filter.value}`}</span>
            <button
              type="button"
              onClick={() => removeFilter(filter.id)}
              aria-label={`Remove filter ${filter.displayLabel || filter.field}`}
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                justifyContent: 'center',
                background: 'transparent',
                border: 'none',
                color: 'inherit',
                cursor: 'pointer',
                padding: 0,
                borderRadius: '50%',
              }}
            >
              <X size={11} aria-hidden="true" />
            </button>
          </span>
        ))}

        {filters.length > 0 && (
          <button
            type="button"
            onClick={handleClearAll}
            aria-label="Clear all applied filters"
            style={{
              padding: '0.15rem 0.5rem',
              fontSize: '0.75rem',
              color: 'var(--text-secondary)',
              backgroundColor: 'transparent',
              border: 'none',
              cursor: 'pointer',
              textDecoration: 'underline',
              marginLeft: '0.5rem',
            }}
          >
            Clear all
          </button>
        )}
      </div>

      {/* Save View Modal / Popover */}
      {showSaveModal && (
        <div
          role="dialog"
          aria-label="Save view preset dialog"
          style={{
            position: 'fixed',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            backgroundColor: 'rgba(0, 0, 0, 0.6)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 100,
          }}
        >
          <div
            style={{
              width: '340px',
              backgroundColor: 'var(--bg-secondary)',
              border: '1px solid var(--border-color)',
              borderRadius: '8px',
              padding: '1.25rem',
              boxShadow: '0 20px 25px -5px rgba(0, 0, 0, 0.5)',
            }}
          >
            <h4 style={{ margin: '0 0 0.5rem 0', color: 'var(--text-primary)' }}>Save View Preset</h4>
            <p style={{ margin: '0 0 1rem 0', fontSize: '0.8125rem', color: 'var(--text-secondary)' }}>
              Save current set of {filters.length} filters for quick recall.
            </p>

            <label htmlFor="save-view-name-input" className="sr-only" style={{ display: 'none' }}>
              View name
            </label>
            <input
              id="save-view-name-input"
              type="text"
              placeholder="e.g., Production AWS High Breaches"
              value={newViewName}
              onChange={(e) => setNewViewName(e.target.value)}
              aria-label="View name"
              style={{
                width: '100%',
                padding: '0.5rem',
                borderRadius: '6px',
                border: '1px solid var(--border-color)',
                backgroundColor: 'var(--bg-primary)',
                color: 'var(--text-primary)',
                fontSize: '0.875rem',
                marginBottom: '1rem',
              }}
            />

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.5rem' }}>
              <button
                type="button"
                onClick={() => setShowSaveModal(false)}
                aria-label="Cancel saving view"
                style={{
                  padding: '0.4rem 0.8rem',
                  borderRadius: '6px',
                  border: '1px solid var(--border-color)',
                  backgroundColor: 'transparent',
                  color: 'var(--text-secondary)',
                  cursor: 'pointer',
                  fontSize: '0.8125rem',
                }}
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleSaveView}
                aria-label="Confirm save view"
                style={{
                  padding: '0.4rem 0.8rem',
                  borderRadius: '6px',
                  border: 'none',
                  backgroundColor: 'var(--accent-blue, #38bdf8)',
                  color: '#0f172a',
                  fontWeight: 600,
                  cursor: 'pointer',
                  fontSize: '0.8125rem',
                }}
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
