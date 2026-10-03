import React, { useState } from 'react';
import {
  SlidersHorizontal,
  ChevronLeft,
  ChevronRight,
  ArrowUpDown,
  ArrowUp,
  ArrowDown,
} from 'lucide-react';
import { TableDensity, TABLE_DENSITIES } from './tokens';
import { DataCell } from './NullValue';
import { EmptyState } from './EmptyState';

export interface ColumnDefinition<T> {
  key: string;
  header: string;
  isNumeric?: boolean;
  align?: 'left' | 'center' | 'right';
  sortable?: boolean;
  currency?: string;
  precision?: number;
  render?: (row: T, idx: number) => React.ReactNode;
  width?: string;
}

export interface DenseTableProps<T> {
  columns: ColumnDefinition<T>[];
  data: T[];
  totalRows?: number;
  page?: number;
  pageSize?: number;
  onPageChange?: (page: number, pageSize: number) => void;
  onSortChange?: (key: string, direction: 'asc' | 'desc') => void;
  defaultDensity?: TableDensity;
  showDensityToggle?: boolean;
  showColumnChooser?: boolean;
  stickyHeader?: boolean;
  ariaCaption?: string;
  className?: string;
}

/**
 * DenseTable Component
 * Enforces BBP Section 31:
 * - "dense but readable tables with a comfortable-density toggle and right-aligned numbers at consistent precision"
 * - "server-side paginated tables with column chooser and sticky headers"
 * - "Do not render a blank cell for any absent value."
 */
export function DenseTable<T extends Record<string, any>>({
  columns,
  data,
  totalRows,
  page = 1,
  pageSize = 10,
  onPageChange,
  onSortChange,
  defaultDensity = 'compact',
  showDensityToggle = true,
  showColumnChooser = true,
  stickyHeader = true,
  ariaCaption = 'CloudLens Analytical Data Table',
  className = '',
}: DenseTableProps<T>) {
  const [density, setDensity] = useState<TableDensity>(defaultDensity);
  const [columnVisibility, setColumnVisibility] = useState<Record<string, boolean>>(
    () => {
      const init: Record<string, boolean> = {};
      columns.forEach((c) => {
        init[c.key] = true;
      });
      return init;
    }
  );
  const [showChooserMenu, setShowChooserMenu] = useState(false);
  const [sortKey, setSortKey] = useState<string | null>(null);
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('asc');

  const densityConfig = TABLE_DENSITIES[density];
  const visibleColumns = columns.filter((c) => columnVisibility[c.key] !== false);

  const effectiveTotal = totalRows !== undefined ? totalRows : data.length;
  const totalPages = Math.max(1, Math.ceil(effectiveTotal / pageSize));

  // Client-side pagination if onPageChange is not provided
  const displayData = onPageChange
    ? data
    : data.slice((page - 1) * pageSize, page * pageSize);

  const handleSort = (key: string) => {
    let nextDir: 'asc' | 'desc' = 'asc';
    if (sortKey === key) {
      nextDir = sortDir === 'asc' ? 'desc' : 'asc';
    }
    setSortKey(key);
    setSortDir(nextDir);
    if (onSortChange) {
      onSortChange(key, nextDir);
    }
  };

  const toggleColumn = (key: string) => {
    // Prevent hiding all columns
    const activeCount = Object.values(columnVisibility).filter(Boolean).length;
    if (columnVisibility[key] && activeCount <= 1) return;

    setColumnVisibility((prev) => ({
      ...prev,
      [key]: !prev[key],
    }));
  };

  return (
    <div
      className={`cloudlens-table-container ${className}`}
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: '0.75rem',
        width: '100%',
        backgroundColor: 'var(--bg-secondary)',
        border: '1px solid var(--border-color)',
        borderRadius: '8px',
        overflow: 'hidden',
      }}
    >
      {/* Table Action Bar */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          padding: '0.6rem 1rem',
          borderBottom: '1px solid var(--border-color)',
          backgroundColor: 'rgba(0, 0, 0, 0.2)',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <span style={{ fontSize: '0.8125rem', color: 'var(--text-secondary)' }}>
            Total records: <strong style={{ color: 'var(--text-primary)' }}>{effectiveTotal}</strong>
          </span>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
          {/* Density Toggle */}
          {showDensityToggle && (
            <div
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                backgroundColor: 'rgba(255, 255, 255, 0.05)',
                borderRadius: '6px',
                padding: '2px',
                border: '1px solid var(--border-color)',
              }}
            >
              <button
                type="button"
                onClick={() => setDensity('compact')}
                aria-pressed={density === 'compact'}
                aria-label="Set compact table density"
                style={{
                  padding: '0.2rem 0.5rem',
                  fontSize: '0.75rem',
                  fontWeight: 500,
                  borderRadius: '4px',
                  border: 'none',
                  backgroundColor:
                    density === 'compact' ? 'var(--accent-blue, #38bdf8)' : 'transparent',
                  color: density === 'compact' ? '#0f172a' : 'var(--text-secondary)',
                  cursor: 'pointer',
                }}
              >
                Compact
              </button>
              <button
                type="button"
                onClick={() => setDensity('comfortable')}
                aria-pressed={density === 'comfortable'}
                aria-label="Set comfortable table density"
                style={{
                  padding: '0.2rem 0.5rem',
                  fontSize: '0.75rem',
                  fontWeight: 500,
                  borderRadius: '4px',
                  border: 'none',
                  backgroundColor:
                    density === 'comfortable' ? 'var(--accent-blue, #38bdf8)' : 'transparent',
                  color: density === 'comfortable' ? '#0f172a' : 'var(--text-secondary)',
                  cursor: 'pointer',
                }}
              >
                Comfortable
              </button>
            </div>
          )}

          {/* Column Chooser Popover */}
          {showColumnChooser && (
            <div style={{ position: 'relative' }}>
              <button
                type="button"
                onClick={() => setShowChooserMenu(!showChooserMenu)}
                aria-haspopup="dialog"
                aria-expanded={showChooserMenu}
                aria-label="Choose visible table columns"
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '0.35rem',
                  padding: '0.3rem 0.6rem',
                  fontSize: '0.75rem',
                  borderRadius: '6px',
                  border: '1px solid var(--border-color)',
                  backgroundColor: 'transparent',
                  color: 'var(--text-secondary)',
                  cursor: 'pointer',
                }}
              >
                <SlidersHorizontal size={13} aria-hidden="true" />
                <span>Columns</span>
              </button>

              {showChooserMenu && (
                <div
                  role="dialog"
                  aria-label="Toggle visible columns"
                  style={{
                    position: 'absolute',
                    top: 'calc(100% + 4px)',
                    right: 0,
                    zIndex: 40,
                    width: '200px',
                    backgroundColor: 'var(--bg-secondary)',
                    border: '1px solid var(--border-color)',
                    borderRadius: '6px',
                    padding: '0.5rem',
                    boxShadow: '0 10px 20px rgba(0,0,0,0.5)',
                  }}
                >
                  <div
                    style={{
                      fontSize: '0.75rem',
                      fontWeight: 600,
                      marginBottom: '0.4rem',
                      color: 'var(--text-primary)',
                      borderBottom: '1px solid var(--border-color)',
                      paddingBottom: '0.25rem',
                    }}
                  >
                    Visible Columns
                  </div>
                  {columns.map((col) => {
                    const isVisible = columnVisibility[col.key] !== false;
                    return (
                      <label
                        key={col.key}
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          gap: '0.4rem',
                          padding: '0.25rem 0.2rem',
                          fontSize: '0.75rem',
                          cursor: 'pointer',
                          color: isVisible ? 'var(--text-primary)' : 'var(--text-secondary)',
                        }}
                      >
                        <input
                          type="checkbox"
                          checked={isVisible}
                          onChange={() => toggleColumn(col.key)}
                          style={{ cursor: 'pointer' }}
                        />
                        <span>{col.header}</span>
                      </label>
                    );
                  })}
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Responsive Table Scroll View */}
      <div style={{ overflowX: 'auto', width: '100%', maxHeight: '600px' }}>
        {displayData.length === 0 ? (
          <EmptyState type="NO_DATA" />
        ) : (
          <table
            style={{
              width: '100%',
              borderCollapse: 'collapse',
              fontSize: densityConfig.fontSize,
              lineHeight: densityConfig.lineHeight,
              textAlign: 'left',
            }}
          >
            <caption className="sr-only" style={{ display: 'none' }}>
              {ariaCaption}
            </caption>
            <thead
              style={{
                backgroundColor: 'var(--bg-primary, #0f172a)',
                position: stickyHeader ? 'sticky' : 'static',
                top: 0,
                zIndex: 10,
                borderBottom: '2px solid var(--border-color)',
              }}
            >
              <tr>
                {visibleColumns.map((col) => {
                  const isRight = col.isNumeric || col.align === 'right';
                  const isCenter = col.align === 'center';
                  const textAlign = isRight ? 'right' : isCenter ? 'center' : 'left';

                  return (
                    <th
                      key={col.key}
                      scope="col"
                      style={{
                        padding: densityConfig.rowPadding,
                        textAlign,
                        fontWeight: 600,
                        color: 'var(--text-secondary)',
                        letterSpacing: '0.02em',
                        width: col.width,
                        userSelect: 'none',
                        whiteSpace: 'nowrap',
                      }}
                    >
                      {col.sortable ? (
                        <button
                          type="button"
                          onClick={() => handleSort(col.key)}
                          aria-label={`Sort by ${col.header} ${sortKey === col.key ? (sortDir === 'asc' ? 'descending' : 'ascending') : ''}`}
                          style={{
                            display: 'inline-flex',
                            alignItems: 'center',
                            gap: '0.3rem',
                            background: 'transparent',
                            border: 'none',
                            color: 'inherit',
                            font: 'inherit',
                            fontWeight: 'inherit',
                            cursor: 'pointer',
                            padding: 0,
                          }}
                        >
                          <span>{col.header}</span>
                          {sortKey === col.key ? (
                            sortDir === 'asc' ? (
                              <ArrowUp size={12} aria-hidden="true" />
                            ) : (
                              <ArrowDown size={12} aria-hidden="true" />
                            )
                          ) : (
                            <ArrowUpDown size={12} aria-hidden="true" opacity={0.5} />
                          )}
                        </button>
                      ) : (
                        col.header
                      )}
                    </th>
                  );
                })}
              </tr>
            </thead>
            <tbody>
              {displayData.map((row, rowIdx) => (
                <tr
                  key={row.id || row.code || `row-${rowIdx}`}
                  style={{
                    borderBottom: '1px solid var(--border-color)',
                    backgroundColor:
                      rowIdx % 2 === 0 ? 'transparent' : 'rgba(255, 255, 255, 0.02)',
                    transition: 'background-color 0.1s ease',
                  }}
                  onMouseEnter={(e) => {
                    (e.currentTarget as HTMLElement).style.backgroundColor =
                      'rgba(255, 255, 255, 0.05)';
                  }}
                  onMouseLeave={(e) => {
                    (e.currentTarget as HTMLElement).style.backgroundColor =
                      rowIdx % 2 === 0 ? 'transparent' : 'rgba(255, 255, 255, 0.02)';
                  }}
                >
                  {visibleColumns.map((col) => {
                    const isRight = col.isNumeric || col.align === 'right';
                    const isCenter = col.align === 'center';
                    const textAlign = isRight ? 'right' : isCenter ? 'center' : 'left';
                    const rawVal = row[col.key];

                    return (
                      <td
                        key={col.key}
                        style={{
                          padding: densityConfig.rowPadding,
                          textAlign,
                          fontVariantNumeric: isRight ? 'tabular-nums' : 'normal',
                          color: 'var(--text-primary)',
                        }}
                      >
                        {col.render ? (
                          col.render(row, rowIdx)
                        ) : (
                          <DataCell
                            value={rawVal}
                            currency={col.currency}
                            precision={col.precision !== undefined ? col.precision : 2}
                          />
                        )}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Pagination Footer */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          padding: '0.6rem 1rem',
          borderTop: '1px solid var(--border-color)',
          fontSize: '0.8125rem',
          color: 'var(--text-secondary)',
        }}
      >
        <div>
          Page <strong style={{ color: 'var(--text-primary)' }}>{page}</strong> of{' '}
          <strong>{totalPages}</strong>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
          <button
            type="button"
            disabled={page <= 1}
            onClick={() => onPageChange && onPageChange(page - 1, pageSize)}
            aria-label="Previous page"
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              justifyContent: 'center',
              width: '28px',
              height: '28px',
              borderRadius: '4px',
              border: '1px solid var(--border-color)',
              backgroundColor: 'transparent',
              color: page <= 1 ? 'var(--border-color)' : 'var(--text-primary)',
              cursor: page <= 1 ? 'not-allowed' : 'pointer',
            }}
          >
            <ChevronLeft size={14} aria-hidden="true" />
          </button>

          <button
            type="button"
            disabled={page >= totalPages}
            onClick={() => onPageChange && onPageChange(page + 1, pageSize)}
            aria-label="Next page"
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              justifyContent: 'center',
              width: '28px',
              height: '28px',
              borderRadius: '4px',
              border: '1px solid var(--border-color)',
              backgroundColor: 'transparent',
              color: page >= totalPages ? 'var(--border-color)' : 'var(--text-primary)',
              cursor: page >= totalPages ? 'not-allowed' : 'pointer',
            }}
          >
            <ChevronRight size={14} aria-hidden="true" />
          </button>
        </div>
      </div>
    </div>
  );
}
