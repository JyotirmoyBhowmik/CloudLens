import React, { useState } from 'react';
import { Table, BarChart2 } from 'lucide-react';

export interface ChartDataPoint {
  label: string;
  value: number;
  secondaryValue?: number;
  category?: string;
  formattedValue?: string;
}

export interface AccessibleChartProps {
  title: string;
  description: string;
  data: ChartDataPoint[];
  metricName?: string;
  currency?: string;
  initialViewMode?: 'chart' | 'table';
  height?: number;
  className?: string;
}

/**
 * Accessible Chart Component with Integrated Data-Table Alternative
 * Enforces BBP Section 31 & WCAG 2.1 AA:
 * - "accessible charts with a data-table alternative"
 * - "semantic structure with ARIA labels on charts"
 * - "no information by colour alone"
 */
export const AccessibleChart: React.FC<AccessibleChartProps> = ({
  title,
  description,
  data,
  metricName = 'Spend',
  currency = 'USD',
  initialViewMode = 'chart',
  height = 220,
  className = '',
}) => {
  const [viewMode, setViewMode] = useState<'chart' | 'table'>(initialViewMode);

  const maxValue = Math.max(1, ...data.map((d) => d.value));

  return (
    <div
      role="region"
      aria-label={`${title} container`}
      className={`cloudlens-accessible-chart ${className}`}
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: '0.75rem',
        padding: '1rem',
        backgroundColor: 'var(--bg-secondary)',
        border: '1px solid var(--border-color)',
        borderRadius: '8px',
      }}
    >
      {/* Chart Header & Data Table Toggle */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          flexWrap: 'wrap',
          gap: '0.5rem',
          borderBottom: '1px solid var(--border-color)',
          paddingBottom: '0.6rem',
        }}
      >
        <div>
          <h4 style={{ margin: 0, fontSize: '1rem', fontWeight: 600, color: 'var(--text-primary)' }}>
            {title}
          </h4>
          <p style={{ margin: '0.2rem 0 0 0', fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
            {description}
          </p>
        </div>

        <button
          type="button"
          onClick={() => setViewMode(viewMode === 'chart' ? 'table' : 'chart')}
          aria-pressed={viewMode === 'table'}
          aria-label={
            viewMode === 'chart'
              ? 'Switch to accessible data table representation'
              : 'Switch to visual SVG chart representation'
          }
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: '0.4rem',
            padding: '0.3rem 0.7rem',
            fontSize: '0.75rem',
            fontWeight: 500,
            borderRadius: '6px',
            border: '1px solid var(--border-color)',
            backgroundColor: 'rgba(255, 255, 255, 0.05)',
            color: 'var(--text-primary)',
            cursor: 'pointer',
          }}
        >
          {viewMode === 'chart' ? (
            <>
              <Table size={13} aria-hidden="true" />
              <span>Show as Data Table</span>
            </>
          ) : (
            <>
              <BarChart2 size={13} aria-hidden="true" />
              <span>Show as Visual Chart</span>
            </>
          )}
        </button>
      </div>

      {/* View Mode 1: High-Contrast Accessible SVG Bar Chart */}
      {viewMode === 'chart' ? (
        <div style={{ position: 'relative', width: '100%', height: `${height}px` }}>
          <svg
            role="img"
            aria-label={`${title}: ${description}`}
            style={{ width: '100%', height: '100%', overflow: 'visible' }}
          >
            <desc>{description}</desc>
            {data.map((item, idx) => {
              const barWidth = 100 / (data.length * 1.5);
              const xPercent = (idx / data.length) * 100 + barWidth * 0.25;
              const barHeightPercent = (item.value / maxValue) * 75;
              const yPercent = 85 - barHeightPercent;

              return (
                <g key={item.label}>
                  {/* Accessible tooltip / hover focus outline */}
                  <rect
                    x={`${xPercent}%`}
                    y={`${yPercent}%`}
                    width={`${barWidth}%`}
                    height={`${barHeightPercent}%`}
                    fill="var(--accent-blue, #38bdf8)"
                    rx="3"
                    stroke="#0284c7"
                    strokeWidth="1"
                    tabIndex={0}
                    role="graphics-symbol"
                    aria-label={`${item.label}: ${currency} ${item.formattedValue || item.value.toLocaleString()}`}
                    style={{ outline: 'none', transition: 'fill 0.15s ease' }}
                  />
                  {/* Value label above bar */}
                  <text
                    x={`${xPercent + barWidth / 2}%`}
                    y={`${Math.max(12, yPercent - 4)}%`}
                    textAnchor="middle"
                    fill="var(--text-secondary)"
                    fontSize="10"
                    fontFamily="monospace"
                  >
                    {item.formattedValue || item.value.toLocaleString()}
                  </text>
                  {/* Category label below baseline */}
                  <text
                    x={`${xPercent + barWidth / 2}%`}
                    y="98%"
                    textAnchor="middle"
                    fill="var(--text-secondary)"
                    fontSize="11"
                    fontWeight="500"
                  >
                    {item.label}
                  </text>
                </g>
              );
            })}
            {/* Baseline horizontal rule */}
            <line
              x1="0%"
              y1="85%"
              x2="100%"
              y2="85%"
              stroke="var(--border-color)"
              strokeWidth="1"
            />
          </svg>
        </div>
      ) : (
        /* View Mode 2: Screen-Reader and Keyboard Accessible Semantic HTML Table */
        <div style={{ overflowX: 'auto', width: '100%' }}>
          <table
            style={{
              width: '100%',
              borderCollapse: 'collapse',
              fontSize: '0.8125rem',
              textAlign: 'left',
            }}
          >
            <caption className="sr-only" style={{ display: 'none' }}>
              {title} - Tabular data alternative
            </caption>
            <thead>
              <tr style={{ borderBottom: '2px solid var(--border-color)' }}>
                <th scope="col" style={{ padding: '0.5rem', color: 'var(--text-secondary)' }}>
                  Dimension / Period
                </th>
                <th
                  scope="col"
                  style={{
                    padding: '0.5rem',
                    textAlign: 'right',
                    color: 'var(--text-secondary)',
                  }}
                >
                  {metricName} ({currency})
                </th>
                <th
                  scope="col"
                  style={{
                    padding: '0.5rem',
                    textAlign: 'right',
                    color: 'var(--text-secondary)',
                  }}
                >
                  % of Peak
                </th>
              </tr>
            </thead>
            <tbody>
              {data.map((item, idx) => {
                const pct = ((item.value / maxValue) * 100).toFixed(1);
                return (
                  <tr
                    key={item.label}
                    style={{
                      borderBottom: '1px solid var(--border-color)',
                      backgroundColor:
                        idx % 2 === 0 ? 'transparent' : 'rgba(255, 255, 255, 0.02)',
                    }}
                  >
                    <td style={{ padding: '0.5rem', fontWeight: 500 }}>{item.label}</td>
                    <td
                      style={{
                        padding: '0.5rem',
                        textAlign: 'right',
                        fontVariantNumeric: 'tabular-nums',
                        fontFamily: 'monospace',
                      }}
                    >
                      {item.formattedValue ||
                        `${currency} ${item.value.toLocaleString(undefined, { minimumFractionDigits: 2 })}`}
                    </td>
                    <td
                      style={{
                        padding: '0.5rem',
                        textAlign: 'right',
                        fontVariantNumeric: 'tabular-nums',
                        fontFamily: 'monospace',
                        color: 'var(--text-secondary)',
                      }}
                    >
                      {pct}%
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};
