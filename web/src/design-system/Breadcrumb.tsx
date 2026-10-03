import React from 'react';
import { ChevronRight } from 'lucide-react';

export interface BreadcrumbItem {
  id?: string;
  label: string;
  href?: string;
  onClick?: () => void;
  isCurrent?: boolean;
}

export interface BreadcrumbProps {
  items: BreadcrumbItem[];
  maxVisible?: number;
  className?: string;
}

/**
 * Hierarchy Navigation with Complete Clickable Breadcrumb
 * Enforces BBP Section 31: "hierarchy is the navigation with a complete clickable breadcrumb".
 * Meets WCAG 2.1 AA landmark and list structure standards.
 */
export const Breadcrumb: React.FC<BreadcrumbProps> = ({
  items,
  maxVisible = 5,
  className = '',
}) => {
  if (!items || items.length === 0) return null;

  // Handle truncation for deep hierarchies
  let displayItems = items;
  const isTruncated = items.length > maxVisible && items.length > 3;

  if (isTruncated) {
    const firstItem = items[0];
    const lastItems = items.slice(-(maxVisible - 2));
    displayItems = [
      firstItem,
      { label: '...', isCurrent: false, id: 'ellipsis' },
      ...lastItems,
    ];
  }

  return (
    <nav
      aria-label="Breadcrumb"
      className={`cloudlens-breadcrumb ${className}`}
      style={{
        display: 'flex',
        alignItems: 'center',
        fontSize: '0.875rem',
        color: 'var(--text-secondary)',
        padding: '0.5rem 0',
      }}
    >
      <ol
        style={{
          display: 'flex',
          alignItems: 'center',
          flexWrap: 'wrap',
          listStyle: 'none',
          margin: 0,
          padding: 0,
          gap: '0.35rem',
        }}
      >
        {displayItems.map((item, idx) => {
          const isLast = idx === displayItems.length - 1 || item.isCurrent;

          return (
            <li
              key={item.id || `${item.label}-${idx}`}
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '0.35rem',
              }}
            >
              {idx > 0 && (
                <ChevronRight
                  size={14}
                  aria-hidden="true"
                  style={{ color: 'var(--text-secondary)', opacity: 0.7 }}
                />
              )}

              {isLast ? (
                <span
                  aria-current="page"
                  style={{
                    fontWeight: 600,
                    color: 'var(--text-primary)',
                    padding: '0.2rem 0.4rem',
                    borderRadius: '4px',
                    backgroundColor: 'rgba(255, 255, 255, 0.05)',
                  }}
                >
                  {item.label}
                </span>
              ) : item.onClick || item.href ? (
                <a
                  href={item.href || '#'}
                  onClick={(e) => {
                    if (item.onClick) {
                      e.preventDefault();
                      item.onClick();
                    }
                  }}
                  style={{
                    color: 'var(--accent-blue, #38bdf8)',
                    textDecoration: 'none',
                    padding: '0.2rem 0.4rem',
                    borderRadius: '4px',
                    transition: 'background-color 0.15s ease',
                  }}
                  onMouseEnter={(e) => {
                    (e.currentTarget as HTMLElement).style.textDecoration = 'underline';
                  }}
                  onMouseLeave={(e) => {
                    (e.currentTarget as HTMLElement).style.textDecoration = 'none';
                  }}
                >
                  {item.label}
                </a>
              ) : (
                <span style={{ color: 'var(--text-secondary)', padding: '0.2rem 0.4rem' }}>
                  {item.label}
                </span>
              )}
            </li>
          );
        })}
      </ol>
    </nav>
  );
};
