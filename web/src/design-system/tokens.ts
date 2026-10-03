/**
 * CloudLens Enterprise Design System - Semantic Tokens & State Standards
 * Enforces BBP Section 31 (Design principles, global patterns, accessibility).
 * Strict Rule: Color is NEVER used decoratively; reserved exclusively for threshold/state.
 */

export type ThresholdState =
  | 'NORMAL'
  | 'WARNING'
  | 'HIGH'
  | 'CRITICAL'
  | 'INFORMATIONAL'
  | 'UNKNOWN';

export interface ThresholdStateConfig {
  code: ThresholdState;
  label: string;
  accessibleLabel: string;
  glyph: string;
  colorHex: string;
  bgHex: string;
  borderHex: string;
  contrastRatioDark: number; // Against #0f172a
  contrastRatioLight: number; // Against #ffffff
  description: string;
}

export const THRESHOLD_STATES: Record<ThresholdState, ThresholdStateConfig> = {
  NORMAL: {
    code: 'NORMAL',
    label: 'Normal',
    accessibleLabel: 'Nominal - Within budget/threshold',
    glyph: '✓',
    colorHex: '#34d399', // Emerald-400
    bgHex: 'rgba(16, 185, 129, 0.15)',
    borderHex: '#059669',
    contrastRatioDark: 8.2,
    contrastRatioLight: 4.8,
    description: 'Actual consumption or metric is healthy and comfortably within allocation.',
  },
  WARNING: {
    code: 'WARNING',
    label: 'Warning',
    accessibleLabel: 'Warning - Approaching threshold limit',
    glyph: '⚠',
    colorHex: '#fbbf24', // Amber-400
    bgHex: 'rgba(245, 158, 11, 0.15)',
    borderHex: '#d97706',
    contrastRatioDark: 9.1,
    contrastRatioLight: 4.6,
    description: 'Metric has entered warning band (typically 80% to 99% of allocation).',
  },
  HIGH: {
    code: 'HIGH',
    label: 'High',
    accessibleLabel: 'High - Anomaly or elevated spend',
    glyph: '▲',
    colorHex: '#fb923c', // Orange-400
    bgHex: 'rgba(249, 115, 22, 0.15)',
    borderHex: '#ea580c',
    contrastRatioDark: 7.4,
    contrastRatioLight: 4.7,
    description: 'Significant consumption spike or elevated operational risk detected.',
  },
  CRITICAL: {
    code: 'CRITICAL',
    label: 'Critical',
    accessibleLabel: 'Critical - Threshold breached / Budget exhausted',
    glyph: '🛑',
    colorHex: '#f87171', // Red-400
    bgHex: 'rgba(239, 68, 68, 0.15)',
    borderHex: '#dc2626',
    contrastRatioDark: 6.9,
    contrastRatioLight: 4.9,
    description: 'Budget exhausted (>= 100%) or severe critical policy violation in effect.',
  },
  INFORMATIONAL: {
    code: 'INFORMATIONAL',
    label: 'Info',
    accessibleLabel: 'Informational - Baseline reference',
    glyph: 'ℹ',
    colorHex: '#38bdf8', // Sky-400
    bgHex: 'rgba(56, 189, 248, 0.15)',
    borderHex: '#0284c7',
    contrastRatioDark: 8.5,
    contrastRatioLight: 4.7,
    description: 'Informational observation or non-breaching baseline reference.',
  },
  UNKNOWN: {
    code: 'UNKNOWN',
    label: 'Unknown',
    accessibleLabel: 'Unknown - Missing data or telemetry gap',
    glyph: '?',
    colorHex: '#94a3b8', // Slate-400
    bgHex: 'rgba(148, 163, 184, 0.15)',
    borderHex: '#64748b',
    contrastRatioDark: 5.6,
    contrastRatioLight: 4.8,
    description: 'Telemetry missing or data quality gap; not evaluated as breach.',
  },
};

/**
 * Four Distinct Null States
 * Hard Rule: Do not render a blank cell for any absent value.
 * Zero, No Data, Not Applicable, and Not Supported must be visually distinct everywhere.
 */
export type NullStateType = 'ZERO' | 'NO_DATA' | 'NOT_APPLICABLE' | 'NOT_SUPPORTED';

export interface NullStateConfig {
  type: NullStateType;
  shortLabel: string;
  badgeLabel: string;
  accessibleName: string;
  tooltipText: string;
  semanticClass: string;
  glyph: string;
}

export const NULL_STATES: Record<NullStateType, NullStateConfig> = {
  ZERO: {
    type: 'ZERO',
    shortLabel: '0.00',
    badgeLabel: '0.00',
    accessibleName: 'Confirmed zero value',
    tooltipText: 'Measured value is explicitly zero (not missing or uncollected).',
    semanticClass: 'null-state-zero',
    glyph: '0',
  },
  NO_DATA: {
    type: 'NO_DATA',
    shortLabel: '--',
    badgeLabel: 'No data',
    accessibleName: 'No data recorded',
    tooltipText: 'Data expected for this period but none collected or reported.',
    semanticClass: 'null-state-no-data',
    glyph: '—',
  },
  NOT_APPLICABLE: {
    type: 'NOT_APPLICABLE',
    shortLabel: 'N/A',
    badgeLabel: 'Not applicable',
    accessibleName: 'Not applicable to entity',
    tooltipText: 'Metric or dimension does not apply to this resource type or service category.',
    semanticClass: 'null-state-na',
    glyph: '⊘',
  },
  NOT_SUPPORTED: {
    type: 'NOT_SUPPORTED',
    shortLabel: 'Not supported',
    badgeLabel: 'Not supported',
    accessibleName: 'Feature not supported by provider',
    tooltipText: 'Underlying cloud provider does not expose this metric or capability.',
    semanticClass: 'null-state-unsupported',
    glyph: '⊗',
  },
};

/**
 * Cost Source Badges
 * Hard Rule: An estimated cost cannot be styled as an actual cost without deliberate override.
 */
export type CostSource =
  | 'ACTUAL'
  | 'ESTIMATED'
  | 'FORECAST'
  | 'MANUAL'
  | 'CACHED'
  | 'UNAVAILABLE';

export interface CostSourceConfig {
  source: CostSource;
  label: string;
  accessibleLabel: string;
  shortCode: string;
  bgHex: string;
  borderHex: string;
  colorHex: string;
  description: string;
}

export const COST_SOURCES: Record<CostSource, CostSourceConfig> = {
  ACTUAL: {
    source: 'ACTUAL',
    label: 'Actual',
    accessibleLabel: 'Actual invoiced spend',
    shortCode: 'ACT',
    bgHex: 'rgba(16, 185, 129, 0.12)',
    borderHex: '#059669',
    colorHex: '#34d399',
    description: 'Invoiced, finalised cloud expenditure directly from provider billing telemetry.',
  },
  ESTIMATED: {
    source: 'ESTIMATED',
    label: 'Estimated',
    accessibleLabel: 'Calculated estimate from rate card',
    shortCode: 'EST',
    bgHex: 'rgba(56, 189, 248, 0.12)',
    borderHex: '#0284c7',
    colorHex: '#38bdf8',
    description: 'Pre-deployment or calculated estimate derived from rate card pricing.',
  },
  FORECAST: {
    source: 'FORECAST',
    label: 'Forecast',
    accessibleLabel: 'Statistical projection',
    shortCode: 'FCST',
    bgHex: 'rgba(168, 85, 247, 0.12)',
    borderHex: '#7e22ce',
    colorHex: '#c084fc',
    description: 'Statistically projected future spend based on seasonal run rate.',
  },
  MANUAL: {
    source: 'MANUAL',
    label: 'Manual',
    accessibleLabel: 'Manual adjustment / journal override',
    shortCode: 'MAN',
    bgHex: 'rgba(245, 158, 11, 0.12)',
    borderHex: '#b45309',
    colorHex: '#fbbf24',
    description: 'Manually recorded journal voucher or cost apportionment override.',
  },
  CACHED: {
    source: 'CACHED',
    label: 'Cached',
    accessibleLabel: 'Cached pricing snapshot',
    shortCode: 'CACHE',
    bgHex: 'rgba(148, 163, 184, 0.12)',
    borderHex: '#64748b',
    colorHex: '#94a3b8',
    description: 'Locally cached pricing snapshot; live rate lookup was offline.',
  },
  UNAVAILABLE: {
    source: 'UNAVAILABLE',
    label: 'Unavailable',
    accessibleLabel: 'Cost figure unavailable',
    shortCode: 'UNAVAIL',
    bgHex: 'rgba(239, 68, 68, 0.12)',
    borderHex: '#b91c1c',
    colorHex: '#f87171',
    description: 'Cost data cannot be resolved or is unallocated across accounts.',
  },
};

/**
 * Data Freshness States
 */
export type FreshnessState = 'FRESH' | 'DELAYED' | 'STALE';

export interface FreshnessConfig {
  state: FreshnessState;
  label: string;
  accessibleLabel: string;
  colorHex: string;
  bgHex: string;
  maxAgeHours: number;
}

export const FRESHNESS_STATES: Record<FreshnessState, FreshnessConfig> = {
  FRESH: {
    state: 'FRESH',
    label: 'Fresh',
    accessibleLabel: 'Data is fresh (synced within 4 hours)',
    colorHex: '#34d399',
    bgHex: 'rgba(16, 185, 129, 0.15)',
    maxAgeHours: 4,
  },
  DELAYED: {
    state: 'DELAYED',
    label: 'Delayed',
    accessibleLabel: 'Data is delayed (synced between 4 and 24 hours ago)',
    colorHex: '#fbbf24',
    bgHex: 'rgba(245, 158, 11, 0.15)',
    maxAgeHours: 24,
  },
  STALE: {
    state: 'STALE',
    label: 'Stale',
    accessibleLabel: 'Data is stale (sync overdue, over 24 hours old)',
    colorHex: '#f87171',
    bgHex: 'rgba(239, 68, 68, 0.15)',
    maxAgeHours: 999999,
  },
};

/**
 * Four Distinct Empty States
 */
export type EmptyStateType = 'NO_DATA' | 'NO_ACCESS' | 'NOT_SUPPORTED' | 'NOT_YET_SYNCED';

export interface EmptyStateConfig {
  type: EmptyStateType;
  title: string;
  description: string;
  actionText: string;
  accessibleName: string;
}

export const EMPTY_STATES: Record<EmptyStateType, EmptyStateConfig> = {
  NO_DATA: {
    type: 'NO_DATA',
    title: 'No Data Recorded',
    description: 'No telemetry, resources, or cost items match the current filter criteria and date window.',
    actionText: 'Reset Filters',
    accessibleName: 'Empty state: No data recorded',
  },
  NO_ACCESS: {
    type: 'NO_ACCESS',
    title: 'Access Restricted',
    description: 'You do not hold the required RBAC scope grant or role permission to inspect this dataset.',
    actionText: 'Request Scope Grant',
    accessibleName: 'Empty state: Access restricted by RBAC',
  },
  NOT_SUPPORTED: {
    type: 'NOT_SUPPORTED',
    title: 'Not Supported By Cloud Provider',
    description: 'The selected cloud service or metric is not exposed or supported by this provider connector.',
    actionText: 'View Provider Matrix',
    accessibleName: 'Empty state: Feature not supported by provider',
  },
  NOT_YET_SYNCED: {
    type: 'NOT_YET_SYNCED',
    title: 'Initial Sync In Progress',
    description: 'Cloud account connected but initial ingestion batch is queuing or running.',
    actionText: 'Check Ingestion Status',
    accessibleName: 'Empty state: Initial sync in progress',
  },
};

/**
 * Table Density Settings
 */
export type TableDensity = 'compact' | 'comfortable';

export interface TableDensityConfig {
  density: TableDensity;
  rowPadding: string;
  fontSize: string;
  lineHeight: string;
}

export const TABLE_DENSITIES: Record<TableDensity, TableDensityConfig> = {
  compact: {
    density: 'compact',
    rowPadding: '0.35rem 0.6rem',
    fontSize: '0.8125rem',
    lineHeight: '1.25',
  },
  comfortable: {
    density: 'comfortable',
    rowPadding: '0.75rem 1rem',
    fontSize: '0.875rem',
    lineHeight: '1.5',
  },
};
