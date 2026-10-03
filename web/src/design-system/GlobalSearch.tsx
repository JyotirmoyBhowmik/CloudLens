import React, { useState, useEffect, useRef } from 'react';
import { Search, X, CornerDownLeft, Box, Folder, Server, FileText } from 'lucide-react';

export interface SearchResultItem {
  id: string;
  title: string;
  category: 'APPLICATION' | 'RESOURCE' | 'COST_CENTRE' | 'BUSINESS_UNIT' | 'REPORT' | 'DOCS';
  subtitle?: string;
  url?: string;
}

export interface GlobalSearchProps {
  items?: SearchResultItem[];
  onSelect?: (item: SearchResultItem) => void;
  placeholder?: string;
  isOpen?: boolean;
  onClose?: () => void;
  className?: string;
}

const DEFAULT_MOCK_ITEMS: SearchResultItem[] = [
  { id: '1', title: 'Customer Mobile Banking', category: 'APPLICATION', subtitle: 'APP-0001 (Retail Banking)' },
  { id: '2', title: 'Core Ledger PostgreSQL RDS', category: 'RESOURCE', subtitle: 'res-rds-ledger-01 (AWS us-east-1)' },
  { id: '3', title: 'Retail Banking Production Systems', category: 'COST_CENTRE', subtitle: 'CC-2001 ($1.2M Budget)' },
  { id: '4', title: 'Retail Banking Business Unit', category: 'BUSINESS_UNIT', subtitle: 'BU_RETAIL_BANKING' },
  { id: '5', title: 'Monthly Executive Summary Report', category: 'REPORT', subtitle: 'RPT-01 (Finance & Operations)' },
  { id: '6', title: 'Kubernetes Cluster EKS NodeGroup', category: 'RESOURCE', subtitle: 'res-eks-nodegroup-prod (AWS)' },
];

/**
 * Global Search Component with Full Keyboard Operability
 * Enforces BBP Section 31: "global search with keyboard access".
 * Shortcut: Press '/' or 'Ctrl+K' / 'Cmd+K' to open anytime.
 */
export const GlobalSearch: React.FC<GlobalSearchProps> = ({
  items = DEFAULT_MOCK_ITEMS,
  onSelect,
  placeholder = 'Search applications, resources, cost centres, reports... (Ctrl+K or /)',
  isOpen: controlledIsOpen,
  onClose,
  className = '',
}) => {
  const [internalIsOpen, setInternalIsOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [activeIndex, setActiveIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  const isModalOpen = controlledIsOpen !== undefined ? controlledIsOpen : internalIsOpen;

  const handleOpen = () => {
    setInternalIsOpen(true);
    setQuery('');
    setActiveIndex(0);
  };

  const handleClose = () => {
    if (onClose) onClose();
    setInternalIsOpen(false);
  };

  // Keyboard shortcut listener ('/' or 'Ctrl+K' / 'Cmd+K')
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Avoid triggering when user is already typing in an input/textarea
      const targetTag = (e.target as HTMLElement)?.tagName?.toLowerCase();
      const isInput = targetTag === 'input' || targetTag === 'textarea' || targetTag === 'select';

      if ((e.key === '/' && !isInput) || ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k')) {
        e.preventDefault();
        handleOpen();
      }

      if (e.key === 'Escape' && isModalOpen) {
        e.preventDefault();
        handleClose();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isModalOpen]);

  // Autofocus input when modal opens
  useEffect(() => {
    if (isModalOpen) {
      setTimeout(() => inputRef.current?.focus(), 50);
    }
  }, [isModalOpen]);

  // Filter items
  const filtered = query.trim()
    ? items.filter(
        (i) =>
          i.title.toLowerCase().includes(query.toLowerCase()) ||
          (i.subtitle && i.subtitle.toLowerCase().includes(query.toLowerCase())) ||
          i.category.toLowerCase().includes(query.toLowerCase())
      )
    : items;

  // Key navigation in result list
  const handleInputKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setActiveIndex((prev) => (prev + 1) % Math.max(1, filtered.length));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setActiveIndex((prev) => (prev - 1 + filtered.length) % Math.max(1, filtered.length));
    } else if (e.key === 'Enter') {
      e.preventDefault();
      if (filtered[activeIndex]) {
        if (onSelect) onSelect(filtered[activeIndex]);
        handleClose();
      }
    }
  };

  const getCategoryIcon = (category: SearchResultItem['category']) => {
    switch (category) {
      case 'APPLICATION':
        return <Box size={14} aria-hidden="true" />;
      case 'RESOURCE':
        return <Server size={14} aria-hidden="true" />;
      case 'COST_CENTRE':
      case 'BUSINESS_UNIT':
        return <Folder size={14} aria-hidden="true" />;
      case 'REPORT':
      case 'DOCS':
      default:
        return <FileText size={14} aria-hidden="true" />;
    }
  };

  return (
    <>
      {/* Search Input Trigger in Toolbar */}
      <button
        type="button"
        onClick={handleOpen}
        aria-label="Open global search (shortcut: / or Ctrl+K)"
        className={`cloudlens-search-trigger ${className}`}
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: '0.5rem',
          padding: '0.4rem 0.8rem',
          borderRadius: '6px',
          border: '1px solid var(--border-color)',
          backgroundColor: 'var(--bg-primary, #0f172a)',
          color: 'var(--text-secondary)',
          cursor: 'pointer',
          fontSize: '0.8125rem',
          width: '260px',
          justifyContent: 'space-between',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
          <Search size={14} aria-hidden="true" />
          <span>Search...</span>
        </div>
        <kbd
          style={{
            fontSize: '0.7rem',
            padding: '0.1rem 0.35rem',
            borderRadius: '4px',
            backgroundColor: 'rgba(255, 255, 255, 0.1)',
            color: 'var(--text-secondary)',
            border: '1px solid var(--border-color)',
          }}
        >
          /
        </kbd>
      </button>

      {/* Accessible Command Palette Dialog */}
      {isModalOpen && (
        <div
          role="dialog"
          aria-modal="true"
          aria-label="Global Search Command Palette"
          style={{
            position: 'fixed',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            backgroundColor: 'rgba(0, 0, 0, 0.7)',
            backdropFilter: 'blur(3px)',
            display: 'flex',
            alignItems: 'flex-start',
            justifyContent: 'center',
            paddingTop: '10vh',
            zIndex: 1000,
          }}
          onClick={(e) => {
            if (e.target === e.currentTarget) handleClose();
          }}
        >
          <div
            style={{
              width: '100%',
              maxWidth: '600px',
              backgroundColor: 'var(--bg-secondary)',
              border: '1px solid var(--border-color)',
              borderRadius: '10px',
              boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.7)',
              overflow: 'hidden',
              display: 'flex',
              flexDirection: 'column',
            }}
          >
            {/* Search Input Bar */}
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '0.75rem',
                padding: '0.85rem 1rem',
                borderBottom: '1px solid var(--border-color)',
              }}
            >
              <Search size={18} aria-hidden="true" style={{ color: 'var(--text-secondary)' }} />
              <input
                ref={inputRef}
                type="text"
                role="combobox"
                aria-expanded={filtered.length > 0}
                aria-autocomplete="list"
                aria-controls="search-results-list"
                aria-activedescendant={
                  filtered[activeIndex] ? `search-item-${filtered[activeIndex].id}` : undefined
                }
                value={query}
                onChange={(e) => {
                  setQuery(e.target.value);
                  setActiveIndex(0);
                }}
                onKeyDown={handleInputKeyDown}
                placeholder={placeholder}
                style={{
                  flex: 1,
                  backgroundColor: 'transparent',
                  border: 'none',
                  outline: 'none',
                  color: 'var(--text-primary)',
                  fontSize: '1rem',
                }}
              />
              <button
                type="button"
                onClick={handleClose}
                aria-label="Close global search"
                style={{
                  background: 'transparent',
                  border: 'none',
                  color: 'var(--text-secondary)',
                  cursor: 'pointer',
                  padding: '2px',
                }}
              >
                <X size={16} aria-hidden="true" />
              </button>
            </div>

            {/* Results List */}
            <ul
              id="search-results-list"
              role="listbox"
              aria-label="Search suggestions"
              style={{
                listStyle: 'none',
                margin: 0,
                padding: '0.5rem',
                maxHeight: '340px',
                overflowY: 'auto',
              }}
            >
              {filtered.length === 0 ? (
                <li
                  style={{
                    padding: '2rem 1rem',
                    textAlign: 'center',
                    color: 'var(--text-secondary)',
                    fontSize: '0.875rem',
                  }}
                >
                  No matching results for "{query}"
                </li>
              ) : (
                filtered.map((item, idx) => {
                  const isActive = idx === activeIndex;
                  return (
                    <li
                      key={item.id}
                      id={`search-item-${item.id}`}
                      role="option"
                      aria-selected={isActive}
                      onClick={() => {
                        if (onSelect) onSelect(item);
                        handleClose();
                      }}
                      onMouseEnter={() => setActiveIndex(idx)}
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                        padding: '0.6rem 0.8rem',
                        borderRadius: '6px',
                        backgroundColor: isActive
                          ? 'rgba(56, 189, 248, 0.15)'
                          : 'transparent',
                        color: isActive ? 'var(--text-primary)' : 'var(--text-secondary)',
                        cursor: 'pointer',
                        transition: 'background-color 0.1s ease',
                      }}
                    >
                      <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
                        <div
                          style={{
                            color: isActive ? 'var(--accent-blue, #38bdf8)' : 'var(--text-secondary)',
                          }}
                        >
                          {getCategoryIcon(item.category)}
                        </div>
                        <div>
                          <div
                            style={{
                              fontWeight: 500,
                              color: isActive ? 'var(--text-primary)' : 'var(--text-primary)',
                              fontSize: '0.875rem',
                            }}
                          >
                            {item.title}
                          </div>
                          {item.subtitle && (
                            <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
                              {item.subtitle}
                            </div>
                          )}
                        </div>
                      </div>

                      <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                        <span
                          style={{
                            fontSize: '0.7rem',
                            padding: '0.1rem 0.4rem',
                            borderRadius: '4px',
                            backgroundColor: 'rgba(255, 255, 255, 0.05)',
                            border: '1px solid var(--border-color)',
                          }}
                        >
                          {item.category}
                        </span>
                        {isActive && (
                          <CornerDownLeft size={12} aria-hidden="true" style={{ opacity: 0.7 }} />
                        )}
                      </div>
                    </li>
                  );
                })
              )}
            </ul>

            {/* Keyboard Guide Footer */}
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                padding: '0.5rem 1rem',
                borderTop: '1px solid var(--border-color)',
                fontSize: '0.75rem',
                color: 'var(--text-secondary)',
                backgroundColor: 'rgba(0, 0, 0, 0.2)',
              }}
            >
              <span>
                Use <strong>↑</strong> <strong>↓</strong> to navigate, <strong>Enter</strong> to select
              </span>
              <span>
                <strong>Esc</strong> to close
              </span>
            </div>
          </div>
        </div>
      )}
    </>
  );
};
