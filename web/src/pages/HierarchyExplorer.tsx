import React, { useEffect, useState } from 'react';
import {
  Layers,
  Server,
  FolderTree,
  Building,
  Tag as TagIcon,
  Globe,
  User,
  ChevronRight,
  ChevronDown,
  Search,
  Shield,
  Activity,
  DollarSign,
} from 'lucide-react';
import { Breadcrumb } from '../design-system/Breadcrumb';
import { ThresholdBadge } from '../design-system/ThresholdBadge';
import { ThresholdState } from '../design-system/tokens';
import { CostValue } from '../design-system/CostValue';
import { SkeletonLoader } from '../design-system/SkeletonLoader';

export type LateralLensType =
  | 'PROVIDER_HIERARCHY'
  | 'APPLICATION'
  | 'COST_CENTRE'
  | 'ENVIRONMENT'
  | 'OWNER'
  | 'REGION'
  | 'TAG';

export interface HierarchyNode {
  id: string;
  name: string;
  level: string;
  lens_type: LateralLensType;
  provider?: string;
  native_type?: string;
  scope_id?: string;
  aggregate_cost: number;
  budget_amount: number;
  budget_utilisation_pct: number;
  worst_child_threshold_state: 'NORMAL' | 'WARNING' | 'CRITICAL';
  direct_resource_count: number;
  total_descendant_resource_count: number;
  child_count: number;
  children: HierarchyNode[];
  metadata?: Record<string, any>;
}

export interface HierarchyDetailPane {
  node_id: string;
  name: string;
  lens_type: LateralLensType;
  level: string;
  provider?: string;
  native_type?: string;
  aggregate_cost: number;
  budget_amount: number;
  budget_utilisation_pct: number;
  threshold_state: 'NORMAL' | 'WARNING' | 'CRITICAL';
  direct_resources: any[];
  top_contributing_services: Array<{ service_name: string; spend: number }>;
  breadcrumbs: string[];
}

export const HierarchyExplorer: React.FC = () => {
  const [activeLens, setActiveLens] = useState<LateralLensType>('PROVIDER_HIERARCHY');
  const [treeData, setTreeData] = useState<HierarchyNode | null>(null);
  const [selectedNodeId, setSelectedNodeId] = useState<string>('root-estate');
  const [detailPane, setDetailPane] = useState<HierarchyDetailPane | null>(null);
  const [expandedNodes, setExpandedNodes] = useState<Record<string, boolean>>({
    'root-estate': true,
    'prov-aws': true,
    'aws-org-root': true,
  });
  const [loadingTree, setLoadingTree] = useState<boolean>(true);
  const [loadingDetail, setLoadingDetail] = useState<boolean>(false);
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [searchResults, setSearchResults] = useState<any[]>([]);
  const [isSearching, setIsSearching] = useState<boolean>(false);

  // Fetch Hierarchy Tree when active lens changes
  useEffect(() => {
    setLoadingTree(true);
    fetch(`/api/v1/hierarchy/tree?lens_type=${activeLens}`)
      .then((res) => {
        if (!res.ok) throw new Error('Failed to fetch tree');
        return res.json();
      })
      .then((data: HierarchyNode) => {
        setTreeData(data);
        setSelectedNodeId(data.id);
        setExpandedNodes((prev) => ({ ...prev, [data.id]: true }));
        setLoadingTree(false);
      })
      .catch((err) => {
        console.error('Error loading tree:', err);
        setLoadingTree(false);
      });
  }, [activeLens]);

  // Fetch Detail Pane when selected node or active lens changes
  useEffect(() => {
    if (!selectedNodeId) return;
    setLoadingDetail(true);
    fetch(`/api/v1/hierarchy/nodes/${encodeURIComponent(selectedNodeId)}?lens_type=${activeLens}`)
      .then((res) => {
        if (!res.ok) throw new Error('Failed to load node detail');
        return res.json();
      })
      .then((data: HierarchyDetailPane) => {
        setDetailPane(data);
        setLoadingDetail(false);
      })
      .catch((err) => {
        console.error('Error loading node detail:', err);
        setLoadingDetail(false);
      });
  }, [selectedNodeId, activeLens]);

  const toggleExpand = (nodeId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    setExpandedNodes((prev) => ({ ...prev, [nodeId]: !prev[nodeId] }));
  };

  const handleSearch = (q: string) => {
    setSearchQuery(q);
    if (!q.trim()) {
      setSearchResults([]);
      return;
    }
    setIsSearching(true);
    fetch(`/api/v1/hierarchy/search?q=${encodeURIComponent(q.trim())}`)
      .then((res) => res.json())
      .then((data) => {
        setSearchResults(data.results || []);
        setIsSearching(false);
      })
      .catch(() => setIsSearching(false));
  };

  // Recursive Tree Node Renderer
  const renderTreeNode = (node: HierarchyNode, depth: number = 0) => {
    const isExpanded = !!expandedNodes[node.id];
    const isSelected = selectedNodeId === node.id;
    const hasChildren = node.children && node.children.length > 0;

    const thresholdBadgeState: ThresholdState =
      node.worst_child_threshold_state === 'CRITICAL'
        ? 'CRITICAL'
        : node.worst_child_threshold_state === 'WARNING'
        ? 'WARNING'
        : 'NORMAL';

    return (
      <div key={node.id} style={{ display: 'flex', flexDirection: 'column' }}>
        <div
          onClick={() => setSelectedNodeId(node.id)}
          style={{
            display: 'flex',
            alignItems: 'center',
            padding: '0.45rem 0.6rem',
            paddingLeft: `${depth * 1.2 + 0.5}rem`,
            backgroundColor: isSelected ? 'var(--bg-tertiary, #e0f2fe)' : 'transparent',
            borderRadius: '6px',
            cursor: 'pointer',
            transition: 'background-color 0.15s ease',
            borderLeft: isSelected ? '3px solid #0284c7' : '3px solid transparent',
            gap: '0.5rem',
          }}
          role="treeitem"
          aria-selected={isSelected}
          aria-expanded={hasChildren ? isExpanded : undefined}
        >
          {hasChildren ? (
            <button
              onClick={(e) => toggleExpand(node.id, e)}
              style={{
                background: 'none',
                border: 'none',
                padding: '2px',
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                color: 'var(--text-secondary, #64748b)',
              }}
              aria-label={isExpanded ? 'Collapse' : 'Expand'}
            >
              {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
            </button>
          ) : (
            <span style={{ width: 14, display: 'inline-block' }} />
          )}

          <div style={{ display: 'flex', alignItems: 'center', flex: 1, minWidth: 0, gap: '0.4rem' }}>
            <span
              style={{
                fontSize: '0.7rem',
                padding: '0.1rem 0.35rem',
                borderRadius: '4px',
                backgroundColor: 'var(--bg-secondary, #f1f5f9)',
                color: 'var(--text-secondary, #475569)',
                fontWeight: 600,
              }}
            >
              {node.level}
            </span>
            <span
              style={{
                fontWeight: isSelected ? 600 : 400,
                fontSize: '0.875rem',
                color: isSelected ? '#0369a1' : 'var(--text-primary, #0f172a)',
                whiteSpace: 'nowrap',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
              }}
              title={node.name}
            >
              {node.name}
            </span>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', marginLeft: 'auto' }}>
            <span style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-primary, #1e293b)' }}>
              ${Number(node.aggregate_cost).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
            </span>
            {node.budget_utilisation_pct > 0 && (
              <span style={{ fontSize: '0.75rem', color: '#64748b' }}>
                ({node.budget_utilisation_pct}%)
              </span>
            )}
            <ThresholdBadge state={thresholdBadgeState} labelOverride={node.worst_child_threshold_state} size="sm" />
          </div>
        </div>

        {hasChildren && isExpanded && (
          <div role="group">
            {node.children.map((child) => renderTreeNode(child, depth + 1))}
          </div>
        )}
      </div>
    );
  };

  const lenses: Array<{ key: LateralLensType; label: string; icon: React.ReactNode }> = [
    { key: 'PROVIDER_HIERARCHY', label: 'Provider Hierarchy', icon: <Server size={14} /> },
    { key: 'APPLICATION', label: 'Application', icon: <Layers size={14} /> },
    { key: 'COST_CENTRE', label: 'Cost Centre', icon: <Building size={14} /> },
    { key: 'ENVIRONMENT', label: 'Environment', icon: <FolderTree size={14} /> },
    { key: 'OWNER', label: 'Owner', icon: <User size={14} /> },
    { key: 'REGION', label: 'Region', icon: <Globe size={14} /> },
    { key: 'TAG', label: 'Tag', icon: <TagIcon size={14} /> },
  ];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem', padding: '1.5rem 2rem' }}>
      {/* Top Header & Search Bar */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '1rem' }}>
        <div>
          <h1 style={{ fontSize: '1.5rem', fontWeight: 700, margin: 0, color: 'var(--text-primary, #0f172a)' }}>
            Cloud Hierarchy Explorer
          </h1>
          <p style={{ margin: '0.25rem 0 0', color: 'var(--text-secondary, #64748b)', fontSize: '0.875rem' }}>
            Multi-cloud navigation model with recursive budget roll-ups and worst-child threshold bubbling.
          </p>
        </div>

        {/* Global Scope-Safe Search (FR-580, FR-585) */}
        <div style={{ position: 'relative', width: '360px' }}>
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              backgroundColor: 'var(--bg-secondary, #f8fafc)',
              border: '1px solid var(--border-color, #cbd5e1)',
              borderRadius: '8px',
              padding: '0.4rem 0.75rem',
              gap: '0.5rem',
            }}
          >
            <Search size={16} color="#64748b" />
            <input
              type="text"
              placeholder="Scope-safe search across 9 entity types..."
              value={searchQuery}
              onChange={(e) => handleSearch(e.target.value)}
              style={{
                border: 'none',
                background: 'transparent',
                outline: 'none',
                width: '100%',
                fontSize: '0.875rem',
                color: 'var(--text-primary, #0f172a)',
              }}
            />
          </div>

          {/* Search Dropdown Results */}
          {searchQuery && (
            <div
              style={{
                position: 'absolute',
                top: '110%',
                left: 0,
                right: 0,
                backgroundColor: '#ffffff',
                border: '1px solid #e2e8f0',
                borderRadius: '8px',
                boxShadow: '0 10px 15px -3px rgba(0, 0, 0, 0.1)',
                zIndex: 50,
                maxHeight: '320px',
                overflowY: 'auto',
                padding: '0.5rem',
              }}
            >
              {isSearching ? (
                <div style={{ padding: '0.75rem', textAlign: 'center', color: '#64748b' }}>Searching...</div>
              ) : searchResults.length === 0 ? (
                <div style={{ padding: '0.75rem', textAlign: 'center', color: '#64748b' }}>
                  No matches found within authorized scope grants.
                </div>
              ) : (
                searchResults.map((item) => (
                  <div
                    key={item.id}
                    onClick={() => {
                      setSearchQuery('');
                      if (item.entity_type === 'RESOURCE') {
                        setSelectedNodeId(item.id);
                      }
                    }}
                    style={{
                      padding: '0.5rem 0.75rem',
                      borderRadius: '6px',
                      cursor: 'pointer',
                      borderBottom: '1px solid #f1f5f9',
                    }}
                    onMouseEnter={(e) => (e.currentTarget.style.backgroundColor = '#f8fafc')}
                    onMouseLeave={(e) => (e.currentTarget.style.backgroundColor = 'transparent')}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                      <span style={{ fontWeight: 600, fontSize: '0.875rem' }}>{item.title}</span>
                      <span
                        style={{
                          fontSize: '0.7rem',
                          backgroundColor: item.rank_score === 1.0 ? '#dcfce7' : '#f1f5f9',
                          color: item.rank_score === 1.0 ? '#15803d' : '#475569',
                          padding: '0.1rem 0.35rem',
                          borderRadius: '4px',
                          fontWeight: 600,
                        }}
                      >
                        {item.entity_type} {item.rank_score === 1.0 && '• Exact'}
                      </span>
                    </div>
                    <div style={{ fontSize: '0.75rem', color: '#64748b', marginTop: '2px' }}>
                      {item.subtitle} (Identifier: <code>{item.identifier}</code>)
                    </div>
                  </div>
                ))
              )}
            </div>
          )}
        </div>
      </div>

      {/* Lateral Lens Switcher Bar (Prompt 38) */}
      <div
        style={{
          display: 'flex',
          gap: '0.5rem',
          backgroundColor: 'var(--bg-secondary, #f8fafc)',
          padding: '0.4rem',
          borderRadius: '8px',
          border: '1px solid var(--border-color, #e2e8f0)',
          overflowX: 'auto',
        }}
        role="tablist"
        aria-label="Lateral Lens Switcher"
      >
        {lenses.map((lens) => {
          const isActive = activeLens === lens.key;
          return (
            <button
              key={lens.key}
              role="tab"
              aria-selected={isActive}
              onClick={() => setActiveLens(lens.key)}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '0.4rem',
                padding: '0.45rem 0.85rem',
                borderRadius: '6px',
                border: 'none',
                backgroundColor: isActive ? '#0284c7' : 'transparent',
                color: isActive ? '#ffffff' : 'var(--text-secondary, #475569)',
                fontWeight: isActive ? 600 : 500,
                fontSize: '0.8125rem',
                cursor: 'pointer',
                whiteSpace: 'nowrap',
                transition: 'all 0.15s ease',
              }}
            >
              {lens.icon}
              {lens.label}
            </button>
          );
        })}
      </div>

      {/* Main Split-Pane Surface: Tree + Detail Pane */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'minmax(340px, 1fr) minmax(460px, 1.4fr)',
          gap: '1.25rem',
          minHeight: '620px',
        }}
      >
        {/* Left Pane: Tree View */}
        <div
          style={{
            backgroundColor: '#ffffff',
            border: '1px solid var(--border-color, #e2e8f0)',
            borderRadius: '10px',
            padding: '1rem',
            overflowY: 'auto',
            maxHeight: '760px',
          }}
          role="tree"
          aria-label="Cloud Estate Hierarchy Tree"
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.75rem', paddingBottom: '0.5rem', borderBottom: '1px solid #f1f5f9' }}>
            <span style={{ fontSize: '0.8125rem', fontWeight: 600, color: '#475569' }}>ESTATE STRUCTURE</span>
            <span style={{ fontSize: '0.75rem', color: '#64748b' }}>Spend / Utilisation / Threshold</span>
          </div>

          {loadingTree ? (
            <SkeletonLoader variant="table" rows={6} />
          ) : treeData ? (
            renderTreeNode(treeData)
          ) : (
            <div style={{ padding: '2rem', textAlign: 'center', color: '#64748b' }}>No hierarchy nodes available.</div>
          )}
        </div>

        {/* Right Pane: Detail Pane */}
        <div
          style={{
            backgroundColor: '#ffffff',
            border: '1px solid var(--border-color, #e2e8f0)',
            borderRadius: '10px',
            padding: '1.25rem',
            display: 'flex',
            flexDirection: 'column',
            gap: '1rem',
            overflowY: 'auto',
            maxHeight: '760px',
          }}
        >
          {loadingDetail ? (
            <SkeletonLoader variant="card" rows={4} />
          ) : detailPane ? (
            <>
              {/* Breadcrumbs Navigation */}
              {detailPane.breadcrumbs && detailPane.breadcrumbs.length > 0 && (
                <div style={{ paddingBottom: '0.5rem', borderBottom: '1px solid #f1f5f9' }}>
                  <Breadcrumb
                    items={detailPane.breadcrumbs.map((b, i) => ({
                      id: String(i),
                      label: b,
                    }))}
                  />
                </div>
              )}

              {/* Node Overview Header */}
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '0.75rem' }}>
                <div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                    <span
                      style={{
                        fontSize: '0.75rem',
                        padding: '0.15rem 0.5rem',
                        borderRadius: '4px',
                        backgroundColor: '#e0f2fe',
                        color: '#0369a1',
                        fontWeight: 600,
                      }}
                    >
                      {detailPane.level}
                    </span>
                    {detailPane.provider && (
                      <span
                        style={{
                          fontSize: '0.75rem',
                          padding: '0.15rem 0.5rem',
                          borderRadius: '4px',
                          backgroundColor: '#f1f5f9',
                          color: '#475569',
                          fontWeight: 500,
                        }}
                      >
                        {detailPane.provider}
                      </span>
                    )}
                    {detailPane.native_type && (
                      <span style={{ fontSize: '0.75rem', color: '#64748b' }}>
                        Native: <code>{detailPane.native_type}</code>
                      </span>
                    )}
                  </div>
                  <h2 style={{ fontSize: '1.25rem', fontWeight: 700, margin: '0.4rem 0 0', color: 'var(--text-primary, #0f172a)' }}>
                    {detailPane.name}
                  </h2>
                </div>

                <ThresholdBadge
                  state={
                    detailPane.threshold_state === 'CRITICAL'
                      ? 'CRITICAL'
                      : detailPane.threshold_state === 'WARNING'
                      ? 'WARNING'
                      : 'NORMAL'
                  }
                  labelOverride={`Threshold: ${detailPane.threshold_state}`}
                  size="md"
                />
              </div>

              {/* Financial Roll-up Cards */}
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '0.75rem' }}>
                <div style={{ backgroundColor: '#f8fafc', padding: '0.85rem', borderRadius: '8px', border: '1px solid #e2e8f0' }}>
                  <div style={{ fontSize: '0.75rem', color: '#64748b', fontWeight: 500, display: 'flex', alignItems: 'center', gap: '0.3rem' }}>
                    <DollarSign size={14} /> AGGREGATE SPEND
                  </div>
                  <div style={{ fontSize: '1.35rem', fontWeight: 700, marginTop: '0.3rem', color: '#0f172a' }}>
                    <CostValue amount={Number(detailPane.aggregate_cost)} source="ACTUAL" currency="USD" />
                  </div>
                  <div style={{ fontSize: '0.7rem', color: '#64748b', marginTop: '0.2rem' }}>All descendants rolled up</div>
                </div>

                <div style={{ backgroundColor: '#f8fafc', padding: '0.85rem', borderRadius: '8px', border: '1px solid #e2e8f0' }}>
                  <div style={{ fontSize: '0.75rem', color: '#64748b', fontWeight: 500, display: 'flex', alignItems: 'center', gap: '0.3rem' }}>
                    <Shield size={14} /> BUDGET ALLOCATION
                  </div>
                  <div style={{ fontSize: '1.35rem', fontWeight: 700, marginTop: '0.3rem', color: '#0f172a' }}>
                    <CostValue amount={Number(detailPane.budget_amount)} source="ACTUAL" currency="USD" />
                  </div>
                  <div style={{ fontSize: '0.7rem', color: '#64748b', marginTop: '0.2rem' }}>Target threshold boundary</div>
                </div>

                <div style={{ backgroundColor: '#f8fafc', padding: '0.85rem', borderRadius: '8px', border: '1px solid #e2e8f0' }}>
                  <div style={{ fontSize: '0.75rem', color: '#64748b', fontWeight: 500, display: 'flex', alignItems: 'center', gap: '0.3rem' }}>
                    <Activity size={14} /> UTILISATION RATIO
                  </div>
                  <div style={{ fontSize: '1.35rem', fontWeight: 700, marginTop: '0.3rem', color: detailPane.budget_utilisation_pct > 80 ? '#dc2626' : '#0f172a' }}>
                    {detailPane.budget_utilisation_pct}%
                  </div>
                  <div style={{ fontSize: '0.7rem', color: '#64748b', marginTop: '0.2rem' }}>Of allocated budget</div>
                </div>
              </div>

              {/* Top Contributing Services */}
              {detailPane.top_contributing_services && detailPane.top_contributing_services.length > 0 && (
                <div style={{ border: '1px solid #e2e8f0', borderRadius: '8px', padding: '0.85rem' }}>
                  <h3 style={{ fontSize: '0.875rem', fontWeight: 600, margin: '0 0 0.5rem', color: '#334155' }}>
                    Top Contributing Services
                  </h3>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
                    {detailPane.top_contributing_services.map((svc) => (
                      <div
                        key={svc.service_name}
                        style={{
                          display: 'flex',
                          justifyContent: 'space-between',
                          alignItems: 'center',
                          padding: '0.35rem 0.5rem',
                          backgroundColor: '#f8fafc',
                          borderRadius: '4px',
                          fontSize: '0.8125rem',
                        }}
                      >
                        <span style={{ fontWeight: 500 }}>{svc.service_name}</span>
                        <span style={{ fontWeight: 600, color: '#0284c7' }}>
                          ${svc.spend.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Direct or Descendant Resources List */}
              <div style={{ border: '1px solid #e2e8f0', borderRadius: '8px', padding: '0.85rem' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
                  <h3 style={{ fontSize: '0.875rem', fontWeight: 600, margin: 0, color: '#334155' }}>
                    Discovered Resources ({detailPane.direct_resources ? detailPane.direct_resources.length : 0})
                  </h3>
                  <span style={{ fontSize: '0.75rem', color: '#64748b' }}>Canonical 35-field inventory entries</span>
                </div>

                {detailPane.direct_resources && detailPane.direct_resources.length > 0 ? (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem', maxHeight: '280px', overflowY: 'auto' }}>
                    {detailPane.direct_resources.map((res: any) => (
                      <div
                        key={res.id}
                        style={{
                          display: 'flex',
                          justifyContent: 'space-between',
                          alignItems: 'center',
                          padding: '0.45rem 0.6rem',
                          borderRadius: '6px',
                          border: '1px solid #f1f5f9',
                          backgroundColor: '#ffffff',
                          fontSize: '0.8125rem',
                        }}
                      >
                        <div>
                          <div style={{ fontWeight: 600, color: '#0f172a' }}>{res.name}</div>
                          <div style={{ fontSize: '0.72rem', color: '#64748b' }}>
                            {res.provider} • {res.service_name} • {res.region_id} • Owner: {res.owner_name}
                          </div>
                        </div>
                        <div style={{ textAlign: 'right' }}>
                          <div style={{ fontWeight: 600, color: '#0f172a' }}>
                            ${Number(res.monthly_cost).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}/mo
                          </div>
                          <span
                            style={{
                              fontSize: '0.68rem',
                              backgroundColor: res.runtime_state === 'RUNNING' ? '#dcfce7' : '#f1f5f9',
                              color: res.runtime_state === 'RUNNING' ? '#166534' : '#475569',
                              padding: '0.1rem 0.3rem',
                              borderRadius: '4px',
                            }}
                          >
                            {res.runtime_state}
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div style={{ padding: '1rem', textAlign: 'center', color: '#64748b', fontSize: '0.8125rem' }}>
                    No direct resources assigned at this node level.
                  </div>
                )}
              </div>
            </>
          ) : (
            <div style={{ padding: '2rem', textAlign: 'center', color: '#64748b' }}>Select a node in the tree to view details.</div>
          )}
        </div>
      </div>
    </div>
  );
};
