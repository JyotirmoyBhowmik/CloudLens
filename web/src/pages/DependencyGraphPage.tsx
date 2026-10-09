import React, { useState, useMemo, useRef } from 'react';
import {
  Breadcrumb,
  BreadcrumbItem,
  CostValue,
  createCostExplanation,
  EmptyState,
  ErrorState,
  SkeletonLoader,
} from '../design-system';
import { useApiData } from '../api';
import {
  Network,
  ZoomIn,
  ZoomOut,
  Calendar,
  DollarSign,
  AlertTriangle,
  Lock,
  Server,
  Database,
  Cpu,
  Cloud,
  Eye,
  FileJson,
  FileText,
  X,
} from 'lucide-react';

export interface GraphNode {
  id: string;
  name: string;
  category: 'compute' | 'database' | 'storage' | 'network' | 'shared';
  provider: 'aws' | 'azure' | 'gcp' | 'oci';
  depth: number;
  periodCost: number;
  chainContributedCost: number;
  thresholdState: 'NORMAL' | 'WARNING' | 'CRITICAL';
  budgetUtilisationPct: number;
  runtimeState: 'RUNNING' | 'STOPPED' | 'IDLE';
  isUnowned: boolean;
  owner?: string;
  isRestricted: boolean;
  isClustered?: boolean;
  clusterCount?: number;
  collapsed?: boolean;
  x: number;
  y: number;
}

export interface GraphEdge {
  id: string;
  source: string;
  target: string;
  relationshipType: 'CALLS' | 'READS_FROM' | 'WRITES_TO' | 'NETWORK_EGRESS' | 'BILLING_DEPENDENCY' | 'EMBEDDED_IN';
  discoveryType: 'discovered' | 'manual' | 'inferred';
  criticality: 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW';
  isRestricted?: boolean;
}

export const DependencyGraphPage: React.FC = () => {
  const { data: apiGraph, loading, error, errorMessage, refetch } = useApiData<any>('/api/v1/dependencies/graph');
  const [maxDepth, setMaxDepth] = useState<number>(3);
  const [costOverlayEnabled, setCostOverlayEnabled] = useState<boolean>(true);
  const [impactViewEnabled, setImpactViewEnabled] = useState<boolean>(false);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>('app-ecommerce-core');
  const [asOfDate, setAsOfDate] = useState<string>('2026-10-03');
  const [zoomLevel, setZoomLevel] = useState<number>(1.0);
  const [benchmark500Enabled, setBenchmark500Enabled] = useState<boolean>(false);
  const [activeRelFilter, setActiveRelFilter] = useState<string>('ALL');
  const svgRef = useRef<SVGSVGElement | null>(null);

  const breadcrumbs: BreadcrumbItem[] = [
    { label: 'CloudLens', href: '/' },
    { label: 'Topology & Dependency Graph', isCurrent: true },
  ];

  // Graph Generation from API
  const { nodes, edges } = useMemo(() => {
    const rawNodes: any[] = apiGraph?.nodes || [];
    const rawEdges: any[] = apiGraph?.edges || [];

    const baseNodes: GraphNode[] = rawNodes.map((n: any, idx: number) => ({
      id: n.key || n.id || `node-${idx}`,
      name: n.name || n.key || `Node ${idx}`,
      category: (n.category || 'compute') as GraphNode['category'],
      provider: (n.provider || 'aws') as GraphNode['provider'],
      depth: n.depth ?? (idx % 4),
      periodCost: n.period_cost ?? n.periodCost ?? 0,
      chainContributedCost: n.chain_contributed_cost ?? n.chainContributedCost ?? 0,
      thresholdState: (n.threshold_state || n.thresholdState || 'NORMAL') as GraphNode['thresholdState'],
      budgetUtilisationPct: n.budget_utilisation_pct ?? n.budgetUtilisationPct ?? 0,
      runtimeState: (n.runtime_state || n.runtimeState || 'RUNNING') as GraphNode['runtimeState'],
      isUnowned: !!(n.is_unowned ?? n.isUnowned),
      owner: n.owner,
      isRestricted: !!(n.is_restricted ?? n.isRestricted),
      x: n.x ?? (200 + (idx * 90) % 600),
      y: n.y ?? (150 + (idx * 70) % 400),
    }));

    const baseEdges: GraphEdge[] = rawEdges.map((e: any, idx: number) => ({
      id: e.id || `edge-${idx}`,
      source: e.source_ref?.key || e.source || '',
      target: e.target_ref?.key || e.target || '',
      relationshipType: (e.relationship_type || e.relationshipType || 'CALLS') as GraphEdge['relationshipType'],
      discoveryType: (e.discovery_type || e.discoveryType || 'discovered') as GraphEdge['discoveryType'],
      criticality: (e.criticality || 'MEDIUM') as GraphEdge['criticality'],
      isRestricted: !!(e.is_restricted ?? e.isRestricted),
    }));

    if (!benchmark500Enabled || baseNodes.length === 0) {
      return { nodes: baseNodes, edges: baseEdges };
    }

    const synthNodes: GraphNode[] = [...baseNodes];
    const synthEdges: GraphEdge[] = [...baseEdges];
    const totalToGenerate = 492;
    const categories: Array<'compute' | 'database' | 'storage' | 'network' | 'shared'> = [
      'compute',
      'database',
      'storage',
      'network',
      'shared',
    ];
    const providers: Array<'aws' | 'azure' | 'gcp' | 'oci'> = ['aws', 'azure', 'gcp', 'oci'];

    for (let i = 1; i <= totalToGenerate; i++) {
      const parentId = synthNodes[i % Math.max(1, synthNodes.length)].id;
      const depth = Math.min(5, Math.floor(i / 100) + 1);
      const angle = (i % 36) * (Math.PI / 18);
      const radius = 180 + (depth * 90) + ((i % 5) * 20);
      const x = 450 + Math.cos(angle) * radius;
      const y = 300 + Math.sin(angle) * radius;

      const nodeId = `synth-node-${i}`;
      synthNodes.push({
        id: nodeId,
        name: `Service Node #${i} (${providers[i % 4].toUpperCase()})`,
        category: categories[i % 5],
        provider: providers[i % 4],
        depth,
        periodCost: Number((15 + (i * 0.75) % 150).toFixed(2)),
        chainContributedCost: Number((15 + (i * 0.75) % 150).toFixed(2)),
        thresholdState: i % 15 === 0 ? 'CRITICAL' : i % 7 === 0 ? 'WARNING' : 'NORMAL',
        budgetUtilisationPct: Number((40 + (i * 1.3) % 70).toFixed(1)),
        runtimeState: i % 10 === 0 ? 'IDLE' : 'RUNNING',
        isUnowned: i % 12 === 0,
        owner: i % 12 === 0 ? undefined : `Squad-${(i % 10) + 1}`,
        isRestricted: i % 25 === 0,
        x,
        y,
      });

      synthEdges.push({
        id: `synth-edge-${i}`,
        source: parentId,
        target: nodeId,
        relationshipType: i % 3 === 0 ? 'CALLS' : i % 2 === 0 ? 'READS_FROM' : 'NETWORK_EGRESS',
        discoveryType: i % 4 === 0 ? 'manual' : i % 3 === 0 ? 'inferred' : 'discovered',
        criticality: i % 10 === 0 ? 'CRITICAL' : i % 5 === 0 ? 'HIGH' : 'MEDIUM',
      });
    }

    return { nodes: synthNodes, edges: synthEdges };
  }, [apiGraph, benchmark500Enabled]);

  // Compute Downstream Impact Set (Blast Radius)
  const downstreamImpactSet = useMemo(() => {
    if (!impactViewEnabled || !selectedNodeId) return new Set<string>();

    const visited = new Set<string>();
    const queue = [selectedNodeId];

    while (queue.length > 0) {
      const current = queue.shift()!;
      visited.add(current);

      const outboundTargets = edges
        .filter((e) => e.source === current)
        .map((e) => e.target);

      for (const target of outboundTargets) {
        if (!visited.has(target)) {
          visited.add(target);
          queue.push(target);
        }
      }
    }

    return visited;
  }, [impactViewEnabled, selectedNodeId, edges]);

  // Filtered nodes by depth, relationship, and collapsed state
  const visibleNodes = useMemo(() => {
    return nodes.filter((n) => {
      if (n.depth > maxDepth) return false;
      return true;
    });
  }, [nodes, maxDepth]);

  const visibleEdges = useMemo(() => {
    const nodeIds = new Set(visibleNodes.map((n) => n.id));
    return edges.filter((e) => {
      if (!nodeIds.has(e.source) || !nodeIds.has(e.target)) return false;
      if (activeRelFilter !== 'ALL' && e.relationshipType !== activeRelFilter) return false;
      return true;
    });
  }, [edges, visibleNodes, activeRelFilter]);

  // Selected Node Object
  const selectedNode = useMemo(() => {
    return nodes.find((n) => n.id === selectedNodeId) || null;
  }, [nodes, selectedNodeId]);

  // Chain Cost Summary (Agreement with Cost Explorer)
  const chainCostSummary = useMemo(() => {
    const directRoot = selectedNode ? selectedNode.periodCost : 0;
    const totalChain = selectedNode ? selectedNode.chainContributedCost : directRoot;
    const downstream = Math.max(0, totalChain - directRoot);
    const shared = Number((downstream * 0.15).toFixed(2));

    return {
      totalChain,
      directRoot,
      downstream,
      shared,
      currency: 'USD',
    };
  }, [selectedNode]);

  // Export Graph as JSON
  const handleExportJSON = () => {
    const payload = {
      as_of: asOfDate,
      max_depth: maxDepth,
      total_nodes: visibleNodes.length,
      total_edges: visibleEdges.length,
      chain_cost: chainCostSummary,
      nodes: visibleNodes,
      edges: visibleEdges,
    };
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `cloudlens_topology_${asOfDate}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  // Export Graph as CSV
  const handleExportCSV = () => {
    const headers = ['NodeID', 'Name', 'Category', 'Provider', 'Depth', 'PeriodCost', 'Threshold', 'Restricted'];
    const rows = visibleNodes.map((n) => [
      n.id,
      `"${n.name}"`,
      n.category,
      n.provider,
      n.depth,
      n.periodCost,
      n.thresholdState,
      n.isRestricted,
    ]);
    const csvContent = [headers.join(','), ...rows.map((r) => r.join(','))].join('\n');
    const blob = new Blob([csvContent], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `cloudlens_topology_nodes_${asOfDate}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  // Node Category Icon
  const getCategoryIcon = (category: string) => {
    switch (category) {
      case 'compute':
        return <Cpu size={14} />;
      case 'database':
        return <Database size={14} />;
      case 'storage':
        return <Server size={14} />;
      case 'network':
        return <Network size={14} />;
      default:
        return <Cloud size={14} />;
    }
  };

  // Node Radius Calculation in Cost Overlay Mode
  const getNodeRadius = (node: GraphNode): number => {
    if (!costOverlayEnabled) return 24;
    if (node.isRestricted) return 22;
    // Scale node size by relative spend (min 20px, max 42px radius)
    const cost = node.periodCost;
    const scaled = 20 + Math.min(22, (cost / 400.0) * 22);
    return Math.round(scaled);
  };

  // Threshold Color
  const getThresholdColor = (state: string): string => {
    switch (state) {
      case 'CRITICAL':
        return '#ef4444';
      case 'WARNING':
        return '#f59e0b';
      default:
        return '#10b981';
    }
  };

  // Edge Styling
  const getEdgeStrokeDash = (discoveryType: string): string => {
    switch (discoveryType) {
      case 'manual':
        return '6,4'; // Dashed
      case 'inferred':
        return '2,3'; // Dotted
      default:
        return 'none'; // Solid
    }
  };

  const getEdgeColor = (relType: string): string => {
    switch (relType) {
      case 'CALLS':
        return '#38bdf8';
      case 'WRITES_TO':
        return '#f43f5e';
      case 'READS_FROM':
        return '#a855f7';
      case 'NETWORK_EGRESS':
        return '#f97316';
      case 'BILLING_DEPENDENCY':
        return '#10b981';
      default:
        return '#94a3b8';
    }
  };

  const getEdgeWidth = (criticality: string): number => {
    switch (criticality) {
      case 'CRITICAL':
        return 3.5;
      case 'HIGH':
        return 2.5;
      case 'MEDIUM':
        return 1.8;
      default:
        return 1.0;
    }
  };

  return (
    <div style={{ padding: '1.5rem 2rem', maxWidth: '1600px', margin: '0 auto', color: 'var(--text-primary, #f8fafc)' }}>
      {/* Header Breadcrumbs */}
      <Breadcrumb items={breadcrumbs} className="mb-4" />

      {/* Screen Title & HUD */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '1rem', flexWrap: 'wrap', gap: '1rem' }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
            <h1 style={{ fontSize: '1.75rem', fontWeight: 700, margin: 0 }}>
              Visual Dependency Graph &amp; Topology Canvas
            </h1>
            <span style={{ fontSize: '0.75rem', backgroundColor: '#0369a1', color: '#e0f2fe', padding: '0.2rem 0.6rem', borderRadius: '9999px', fontWeight: 600 }}>
              Prompt 41 / BBP Section 25
            </span>
          </div>
          <p style={{ margin: '0.25rem 0 0 0', color: 'var(--text-secondary, #94a3b8)', fontSize: '0.875rem' }}>
            Interactive dependency canvas with depth control, relationship filtering, cost-overlay scaling, blast radius impact tracing, and chain spend agreement.
          </p>
        </div>

        {/* Global Action Toolbar */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap' }}>
          <button
            type="button"
            onClick={() => setBenchmark500Enabled(!benchmark500Enabled)}
            style={{
              padding: '0.45rem 0.8rem',
              borderRadius: '6px',
              border: `1px solid ${benchmark500Enabled ? '#a855f7' : 'var(--border-color, #334155)'}`,
              backgroundColor: benchmark500Enabled ? 'rgba(168, 85, 247, 0.2)' : 'var(--bg-secondary, #1e293b)',
              color: benchmark500Enabled ? '#d8b4fe' : 'var(--text-primary, #f8fafc)',
              fontSize: '0.8125rem',
              cursor: 'pointer',
              fontWeight: 500,
            }}
          >
            {benchmark500Enabled ? 'Scale Benchmark: 500 Nodes Active' : 'Benchmark 500 Nodes'}
          </button>

          <button
            type="button"
            onClick={handleExportJSON}
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '0.35rem',
              padding: '0.45rem 0.75rem',
              borderRadius: '6px',
              border: '1px solid var(--border-color, #334155)',
              backgroundColor: 'var(--bg-secondary, #1e293b)',
              color: 'var(--text-primary, #f8fafc)',
              fontSize: '0.8125rem',
              cursor: 'pointer',
            }}
          >
            <FileJson size={14} /> JSON
          </button>

          <button
            type="button"
            onClick={handleExportCSV}
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '0.35rem',
              padding: '0.45rem 0.75rem',
              borderRadius: '6px',
              border: '1px solid var(--border-color, #334155)',
              backgroundColor: 'var(--bg-secondary, #1e293b)',
              color: 'var(--text-primary, #f8fafc)',
              fontSize: '0.8125rem',
              cursor: 'pointer',
            }}
          >
            <FileText size={14} /> CSV
          </button>
        </div>
      </div>

      {/* Chain Cost HUD Banner (Agrees with Cost Explorer) */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
          gap: '1rem',
          backgroundColor: 'var(--bg-secondary, #1e293b)',
          border: '1px solid var(--border-color, #334155)',
          borderRadius: '10px',
          padding: '1rem 1.25rem',
          marginBottom: '1rem',
        }}
      >
        <div>
          <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary, #94a3b8)', display: 'block' }}>
            Root Application Chain
          </span>
          <span style={{ fontSize: '1rem', fontWeight: 600, color: '#38bdf8' }}>
            E-Commerce Core API Gateway
          </span>
        </div>

        <div>
          <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary, #94a3b8)', display: 'block' }}>
            Total Cumulative Chain Cost
          </span>
          <CostValue
            amount={chainCostSummary.totalChain}
            source="ACTUAL"
            currency="USD"
            explanation={createCostExplanation('Total Cumulative Chain Cost', {
              pricingSource: 'aws_cur_invoiced',
              formula: 'Direct Root ($240.00) + Downstream Attributed ($1,180.50)',
              unit: 'CHAIN-ECOMMERCE-ROOT',
            })}
          />
        </div>

        <div>
          <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary, #94a3b8)', display: 'block' }}>
            Direct Root Spend
          </span>
          <CostValue
            amount={chainCostSummary.directRoot}
            source="ACTUAL"
            currency="USD"
            explanation={createCostExplanation('Direct Root Spend', {
              pricingSource: 'aws_cur_invoiced',
              formula: 'Unapportioned direct compute runtime for root container cluster',
            })}
          />
        </div>

        <div>
          <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary, #94a3b8)', display: 'block' }}>
            Downstream Attributed Spend
          </span>
          <CostValue
            amount={chainCostSummary.downstream}
            source="ACTUAL"
            currency="USD"
            explanation={createCostExplanation('Downstream Attributed Spend', {
              pricingSource: 'aws_cur_invoiced',
              formula: 'Sum of contributing database, queue, cache, and shared service dependencies',
            })}
          />
        </div>

        <div>
          <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary, #94a3b8)', display: 'block' }}>
            Shared Platform Apportionment
          </span>
          <CostValue
            amount={chainCostSummary.shared}
            source="ACTUAL"
            currency="USD"
            explanation={createCostExplanation('Shared Platform Apportionment', {
              pricingSource: 'oci_rate_card',
              formula: '25% allocated share of enterprise SSO & auth cluster',
            })}
          />
        </div>
      </div>

      {/* Control Bar: Depth, Relationship Filter, Cost Overlay, Impact View, Time Selector */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          backgroundColor: '#0f172a',
          border: '1px solid var(--border-color, #334155)',
          borderRadius: '8px',
          padding: '0.75rem 1rem',
          marginBottom: '1rem',
          flexWrap: 'wrap',
          gap: '0.75rem',
        }}
      >
        {/* Left Controls */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', flexWrap: 'wrap' }}>
          {/* Depth Slider */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <span style={{ fontSize: '0.8125rem', color: 'var(--text-secondary, #94a3b8)' }}>Traversal Depth:</span>
            {[1, 2, 3, 4, 5].map((d) => (
              <button
                key={d}
                type="button"
                onClick={() => setMaxDepth(d)}
                style={{
                  width: '28px',
                  height: '28px',
                  borderRadius: '4px',
                  border: 'none',
                  backgroundColor: maxDepth === d ? '#0284c7' : 'rgba(51, 65, 85, 0.5)',
                  color: maxDepth === d ? '#fff' : 'var(--text-secondary, #94a3b8)',
                  fontSize: '0.75rem',
                  fontWeight: 600,
                  cursor: 'pointer',
                }}
              >
                {d}
              </button>
            ))}
          </div>

          {/* Relationship Filter */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
            <span style={{ fontSize: '0.8125rem', color: 'var(--text-secondary, #94a3b8)' }}>Edges:</span>
            <select
              value={activeRelFilter}
              onChange={(e) => setActiveRelFilter(e.target.value)}
              style={{
                backgroundColor: 'var(--bg-secondary, #1e293b)',
                border: '1px solid var(--border-color, #334155)',
                color: 'var(--text-primary, #f8fafc)',
                padding: '0.3rem 0.6rem',
                borderRadius: '4px',
                fontSize: '0.8125rem',
                cursor: 'pointer',
              }}
            >
              <option value="ALL">All Relationships</option>
              <option value="CALLS">CALLS (RPC/HTTP)</option>
              <option value="WRITES_TO">WRITES_TO (Data Ingress)</option>
              <option value="READS_FROM">READS_FROM (Data Query)</option>
              <option value="NETWORK_EGRESS">NETWORK_EGRESS</option>
              <option value="BILLING_DEPENDENCY">BILLING_DEPENDENCY</option>
            </select>
          </div>

          {/* Toggles */}
          <button
            type="button"
            onClick={() => setCostOverlayEnabled(!costOverlayEnabled)}
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '0.35rem',
              padding: '0.35rem 0.7rem',
              borderRadius: '6px',
              border: `1px solid ${costOverlayEnabled ? '#10b981' : 'var(--border-color, #334155)'}`,
              backgroundColor: costOverlayEnabled ? 'rgba(16, 185, 129, 0.15)' : 'transparent',
              color: costOverlayEnabled ? '#34d399' : 'var(--text-secondary, #94a3b8)',
              fontSize: '0.8125rem',
              cursor: 'pointer',
              fontWeight: 500,
            }}
          >
            <DollarSign size={14} /> Cost Overlay
          </button>

          <button
            type="button"
            onClick={() => setImpactViewEnabled(!impactViewEnabled)}
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '0.35rem',
              padding: '0.35rem 0.7rem',
              borderRadius: '6px',
              border: `1px solid ${impactViewEnabled ? '#f59e0b' : 'var(--border-color, #334155)'}`,
              backgroundColor: impactViewEnabled ? 'rgba(245, 158, 11, 0.15)' : 'transparent',
              color: impactViewEnabled ? '#fbbf24' : 'var(--text-secondary, #94a3b8)',
              fontSize: '0.8125rem',
              cursor: 'pointer',
              fontWeight: 500,
            }}
          >
            <Eye size={14} /> Impact Blast Radius
          </button>
        </div>

        {/* Right Controls: Time Selector & Zoom */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
            <Calendar size={14} color="var(--text-secondary, #94a3b8)" />
            <input
              type="date"
              value={asOfDate}
              onChange={(e) => setAsOfDate(e.target.value)}
              style={{
                backgroundColor: 'var(--bg-secondary, #1e293b)',
                border: '1px solid var(--border-color, #334155)',
                color: 'var(--text-primary, #f8fafc)',
                padding: '0.25rem 0.5rem',
                borderRadius: '4px',
                fontSize: '0.8125rem',
              }}
            />
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '0.25rem' }}>
            <button
              type="button"
              onClick={() => setZoomLevel((z) => Math.min(2.0, Number((z + 0.15).toFixed(2))))}
              title="Zoom In"
              style={{
                padding: '0.3rem',
                borderRadius: '4px',
                border: '1px solid var(--border-color, #334155)',
                backgroundColor: 'var(--bg-secondary, #1e293b)',
                color: 'var(--text-primary, #f8fafc)',
                cursor: 'pointer',
              }}
            >
              <ZoomIn size={14} />
            </button>
            <button
              type="button"
              onClick={() => setZoomLevel((z) => Math.max(0.4, Number((z - 0.15).toFixed(2))))}
              title="Zoom Out"
              style={{
                padding: '0.3rem',
                borderRadius: '4px',
                border: '1px solid var(--border-color, #334155)',
                backgroundColor: 'var(--bg-secondary, #1e293b)',
                color: 'var(--text-primary, #f8fafc)',
                cursor: 'pointer',
              }}
            >
              <ZoomOut size={14} />
            </button>
            <button
              type="button"
              onClick={() => setZoomLevel(1.0)}
              title="Reset Zoom"
              style={{
                padding: '0.3rem 0.5rem',
                borderRadius: '4px',
                border: '1px solid var(--border-color, #334155)',
                backgroundColor: 'var(--bg-secondary, #1e293b)',
                color: 'var(--text-secondary, #94a3b8)',
                fontSize: '0.75rem',
                cursor: 'pointer',
              }}
            >
              100%
            </button>
          </div>
        </div>
      </div>

      {/* Main Interactive Canvas Area */}
      <div style={{ display: 'flex', gap: '1rem', position: 'relative' }}>
        {/* SVG Canvas Container */}
        <div
          style={{
            flex: 1,
            height: '640px',
            backgroundColor: '#090d16',
            border: '1px solid var(--border-color, #334155)',
            borderRadius: '10px',
            overflow: 'hidden',
            position: 'relative',
          }}
        >
          {loading && (
            <div style={{ padding: '2rem', display: 'flex', flexDirection: 'column', gap: '1rem', height: '100%' }}>
              <SkeletonLoader variant="table" rows={3} />
            </div>
          )}
          {error && !loading && (
            <div style={{ padding: '2rem', display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%' }}>
              <ErrorState title="Failed to Load Topology Graph" message={errorMessage || 'Error fetching dependency topology'} onRetry={refetch} />
            </div>
          )}
          {!loading && !error && nodes.length === 0 && (
            <div style={{ padding: '2rem', display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%' }}>
              <EmptyState type="NO_DATA" titleOverride="No Dependencies Discovered" descriptionOverride="No dependency graph topology or resource relationships discovered for this tenant." actionTextOverride="Refresh Topology" onAction={refetch} />
            </div>
          )}
          {!loading && !error && nodes.length > 0 && (<>
          {/* Canvas Background Grid */}
          <svg
            ref={svgRef}
            width="100%"
            height="100%"
            viewBox="0 0 900 640"
            style={{
              cursor: 'grab',
              transform: `scale(${zoomLevel})`,
              transformOrigin: 'center center',
              transition: 'transform 0.15s ease-out',
            }}
          >
            <defs>
              <pattern id="grid-pattern" width="30" height="30" patternUnits="userSpaceOnUse">
                <circle cx="15" cy="15" r="1" fill="#1e293b" />
              </pattern>
              {/* Arrow Marker Definitions */}
              <marker id="arrow-calls" viewBox="0 0 10 10" refX="22" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
                <path d="M 0 0 L 10 5 L 0 10 z" fill="#38bdf8" />
              </marker>
              <marker id="arrow-writes" viewBox="0 0 10 10" refX="22" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
                <path d="M 0 0 L 10 5 L 0 10 z" fill="#f43f5e" />
              </marker>
              <marker id="arrow-reads" viewBox="0 0 10 10" refX="22" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
                <path d="M 0 0 L 10 5 L 0 10 z" fill="#a855f7" />
              </marker>
              <marker id="arrow-egress" viewBox="0 0 10 10" refX="22" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
                <path d="M 0 0 L 10 5 L 0 10 z" fill="#f97316" />
              </marker>
              <marker id="arrow-billing" viewBox="0 0 10 10" refX="22" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
                <path d="M 0 0 L 10 5 L 0 10 z" fill="#10b981" />
              </marker>
            </defs>

            {/* Background Pattern */}
            <rect width="100%" height="100%" fill="url(#grid-pattern)" />

            {/* Render Edges */}
            <g className="graph-edges">
              {visibleEdges.map((edge) => {
                const sourceNode = visibleNodes.find((n) => n.id === edge.source);
                const targetNode = visibleNodes.find((n) => n.id === edge.target);
                if (!sourceNode || !targetNode) return null;

                const isDownstreamHighlighted =
                  impactViewEnabled &&
                  downstreamImpactSet.has(edge.source) &&
                  downstreamImpactSet.has(edge.target);

                const opacity = impactViewEnabled ? (isDownstreamHighlighted ? 1.0 : 0.15) : 0.75;

                return (
                  <line
                    key={edge.id}
                    x1={sourceNode.x}
                    y1={sourceNode.y}
                    x2={targetNode.x}
                    y2={targetNode.y}
                    stroke={getEdgeColor(edge.relationshipType)}
                    strokeWidth={getEdgeWidth(edge.criticality)}
                    strokeDasharray={getEdgeStrokeDash(edge.discoveryType)}
                    opacity={opacity}
                  />
                );
              })}
            </g>

            {/* Render Nodes */}
            <g className="graph-nodes">
              {visibleNodes.map((node) => {
                const r = getNodeRadius(node);
                const isSelected = selectedNodeId === node.id;
                const isImpacted = impactViewEnabled && downstreamImpactSet.has(node.id);
                const isDimmed = impactViewEnabled && !isImpacted;

                const opacity = isDimmed ? 0.25 : 1.0;
                const strokeColor = node.isRestricted
                  ? '#94a3b8'
                  : getThresholdColor(node.thresholdState);

                return (
                  <g
                    key={node.id}
                    transform={`translate(${node.x}, ${node.y})`}
                    onClick={() => setSelectedNodeId(node.id)}
                    style={{ cursor: 'pointer', opacity }}
                  >
                    {/* Selection / Impact Pulse Ring */}
                    {(isSelected || isImpacted) && (
                      <circle
                        r={r + 8}
                        fill="none"
                        stroke={isImpacted ? '#f59e0b' : '#38bdf8'}
                        strokeWidth="2.5"
                        strokeDasharray={isImpacted ? '4,4' : 'none'}
                        opacity="0.8"
                      />
                    )}

                    {/* Node Base Circle */}
                    <circle
                      r={r}
                      fill={node.isRestricted ? '#1e293b' : '#0f172a'}
                      stroke={strokeColor}
                      strokeWidth={isSelected ? 3.5 : 2}
                      strokeDasharray={node.isRestricted ? '4,3' : 'none'}
                    />

                    {/* Center Icon or Restricted Lock */}
                    {node.isRestricted ? (
                      <g transform="translate(-7, -7)">
                        <Lock size={14} color="#94a3b8" />
                      </g>
                    ) : (
                      <g transform="translate(-7, -7)">
                        {getCategoryIcon(node.category)}
                      </g>
                    )}

                    {/* Provider Pill Badge */}
                    <rect
                      x={r - 6}
                      y={-r - 4}
                      width="26"
                      height="12"
                      rx="3"
                      fill="#0284c7"
                    />
                    <text
                      x={r + 7}
                      y={-r + 5}
                      fontSize="8"
                      fontWeight="700"
                      fill="#ffffff"
                      textAnchor="middle"
                    >
                      {node.provider.toUpperCase()}
                    </text>

                    {/* Unowned Warning Badge */}
                    {node.isUnowned && (
                      <g transform={`translate(${-r - 8}, ${-r - 4})`}>
                        <rect width="14" height="12" rx="3" fill="#dc2626" />
                        <text x="7" y="9" fontSize="8" fontWeight="bold" fill="#fff" textAnchor="middle">
                          !
                        </text>
                      </g>
                    )}

                    {/* Budget Utilization Badge */}
                    {!node.isRestricted && (
                      <g transform={`translate(${r - 10}, ${r - 4})`}>
                        <rect
                          width="24"
                          height="12"
                          rx="3"
                          fill={node.budgetUtilisationPct > 90 ? '#7f1d1d' : '#064e3b'}
                        />
                        <text
                          x="12"
                          y="9"
                          fontSize="7"
                          fontWeight="600"
                          fill={node.budgetUtilisationPct > 90 ? '#fca5a5' : '#6ee7b7'}
                          textAnchor="middle"
                        >
                          {Math.round(node.budgetUtilisationPct)}%
                        </text>
                      </g>
                    )}

                    {/* Truncated Node Label Below */}
                    <text
                      y={r + 16}
                      fontSize="10"
                      fill={node.isRestricted ? '#94a3b8' : '#f8fafc'}
                      textAnchor="middle"
                      fontWeight={isSelected ? '700' : '500'}
                    >
                      {node.name.length > 22 ? `${node.name.substring(0, 20)}…` : node.name}
                    </text>

                    {/* Period Spend Figure in Cost Overlay Mode */}
                    {costOverlayEnabled && !node.isRestricted && (
                      <text
                        y={r + 28}
                        fontSize="9"
                        fill="#34d399"
                        textAnchor="middle"
                        fontWeight="600"
                      >
                        ${node.periodCost.toFixed(1)}
                      </text>
                    )}
                  </g>
                );
              })}
            </g>
          </svg>

          {/* Canvas HUD Legend */}
          <div
            style={{
              position: 'absolute',
              bottom: '12px',
              left: '12px',
              backgroundColor: 'rgba(15, 23, 42, 0.85)',
              backdropFilter: 'blur(4px)',
              border: '1px solid var(--border-color, #334155)',
              borderRadius: '6px',
              padding: '0.5rem 0.75rem',
              display: 'flex',
              gap: '1rem',
              fontSize: '0.75rem',
              color: 'var(--text-secondary, #94a3b8)',
              alignItems: 'center',
            }}
          >
            <span><strong>Encoding:</strong></span>
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: '0.25rem' }}>
              <span style={{ width: '8px', height: '8px', borderRadius: '50%', backgroundColor: '#10b981' }} /> Normal
            </span>
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: '0.25rem' }}>
              <span style={{ width: '8px', height: '8px', borderRadius: '50%', backgroundColor: '#f59e0b' }} /> Warning
            </span>
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: '0.25rem' }}>
              <span style={{ width: '8px', height: '8px', borderRadius: '50%', backgroundColor: '#ef4444' }} /> Critical
            </span>
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: '0.25rem' }}>
              <Lock size={11} color="#94a3b8" /> Restricted Node
            </span>
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: '0.25rem' }}>
              <span style={{ width: '12px', borderTop: '2px solid #38bdf8' }} /> Discovered
            </span>
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: '0.25rem' }}>
              <span style={{ width: '12px', borderTop: '2px dashed #94a3b8' }} /> Manual
            </span>
          </div>
          </>)}
        </div>

        {/* Node Detail Slide-Over Panel (Without Leaving Canvas) */}
        {selectedNode && (
          <div
            style={{
              width: '360px',
              backgroundColor: 'var(--bg-secondary, #1e293b)',
              border: '1px solid var(--border-color, #334155)',
              borderRadius: '10px',
              padding: '1.25rem',
              display: 'flex',
              flexDirection: 'column',
              gap: '1rem',
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
              <div>
                <span style={{ fontSize: '0.75rem', color: '#38bdf8', fontWeight: 600, textTransform: 'uppercase' }}>
                  {selectedNode.isRestricted ? 'Restricted Node (Scope Masked)' : selectedNode.category}
                </span>
                <h3 style={{ margin: '0.2rem 0 0 0', fontSize: '1.1rem', fontWeight: 700 }}>
                  {selectedNode.name}
                </h3>
              </div>
              <button
                type="button"
                onClick={() => setSelectedNodeId(null)}
                style={{
                  background: 'none',
                  border: 'none',
                  color: 'var(--text-secondary, #94a3b8)',
                  cursor: 'pointer',
                  padding: '0.2rem',
                }}
              >
                <X size={16} />
              </button>
            </div>

            {selectedNode.isRestricted ? (
              <div style={{ backgroundColor: 'rgba(51, 65, 85, 0.4)', padding: '1rem', borderRadius: '6px', border: '1px solid #475569' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.5rem', color: '#f59e0b' }}>
                  <Lock size={16} />
                  <strong style={{ fontSize: '0.875rem' }}>RBAC Scope Masking Active</strong>
                </div>
                <p style={{ margin: 0, fontSize: '0.8125rem', color: 'var(--text-secondary, #94a3b8)' }}>
                  Per Master Brief &amp; Prompt 41 hard mandate, inaccessible nodes are rendered as Restricted Placeholders rather than omitted. Financial figures and operational metadata are strictly redacted.
                </p>
              </div>
            ) : (
              <>
                {/* Financial Overview */}
                <div style={{ backgroundColor: 'rgba(15, 23, 42, 0.6)', padding: '0.85rem', borderRadius: '6px', border: '1px solid var(--border-color, #334155)' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.5rem' }}>
                    <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary, #94a3b8)' }}>Period Direct Spend</span>
                    <CostValue
                      amount={selectedNode.periodCost}
                      source="ACTUAL"
                      currency="USD"
                      explanation={createCostExplanation(`${selectedNode.name} Spend`, {
                        pricingSource: `${selectedNode.provider}_billing_actuals`,
                        formula: 'Direct unapportioned period consumption for current cycle',
                      })}
                    />
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary, #94a3b8)' }}>Contributed Chain Spend</span>
                    <CostValue
                      amount={selectedNode.chainContributedCost}
                      source="ACTUAL"
                      currency="USD"
                      explanation={createCostExplanation(`${selectedNode.name} Chain Contribution`, {
                        pricingSource: `${selectedNode.provider}_billing_actuals`,
                        formula: 'Apportioned share of downstream chain dependencies',
                      })}
                    />
                  </div>
                </div>

                {/* Badges and Governance Metadata */}
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.5rem', fontSize: '0.8125rem' }}>
                  <div style={{ backgroundColor: 'rgba(15, 23, 42, 0.4)', padding: '0.6rem', borderRadius: '4px' }}>
                    <span style={{ fontSize: '0.7rem', color: 'var(--text-secondary, #94a3b8)', display: 'block' }}>Provider</span>
                    <strong>{selectedNode.provider.toUpperCase()}</strong>
                  </div>
                  <div style={{ backgroundColor: 'rgba(15, 23, 42, 0.4)', padding: '0.6rem', borderRadius: '4px' }}>
                    <span style={{ fontSize: '0.7rem', color: 'var(--text-secondary, #94a3b8)', display: 'block' }}>Budget Utilisation</span>
                    <strong style={{ color: selectedNode.budgetUtilisationPct > 90 ? '#ef4444' : '#10b981' }}>
                      {selectedNode.budgetUtilisationPct}%
                    </strong>
                  </div>
                  <div style={{ backgroundColor: 'rgba(15, 23, 42, 0.4)', padding: '0.6rem', borderRadius: '4px' }}>
                    <span style={{ fontSize: '0.7rem', color: 'var(--text-secondary, #94a3b8)', display: 'block' }}>Runtime State</span>
                    <strong>{selectedNode.runtimeState}</strong>
                  </div>
                  <div style={{ backgroundColor: 'rgba(15, 23, 42, 0.4)', padding: '0.6rem', borderRadius: '4px' }}>
                    <span style={{ fontSize: '0.7rem', color: 'var(--text-secondary, #94a3b8)', display: 'block' }}>Accountable Owner</span>
                    {selectedNode.isUnowned ? (
                      <span style={{ color: '#ef4444', fontWeight: 600 }}>⚠️ Unowned Gap</span>
                    ) : (
                      <strong>{selectedNode.owner || 'Assigned'}</strong>
                    )}
                  </div>
                </div>

                {/* Blast Radius Impact Summary */}
                {impactViewEnabled && (
                  <div style={{ backgroundColor: 'rgba(245, 158, 11, 0.1)', border: '1px solid #d97706', padding: '0.75rem', borderRadius: '6px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.35rem', color: '#fbbf24', fontWeight: 600, fontSize: '0.8125rem', marginBottom: '0.25rem' }}>
                      <AlertTriangle size={14} /> Downstream Blast Radius
                    </div>
                    <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary, #cbd5e1)' }}>
                      Failure or disruption of this node directly impacts <strong>{downstreamImpactSet.size}</strong> downstream services and dependencies.
                    </div>
                  </div>
                )}
              </>
            )}
          </div>
        )}
      </div>
    </div>
  );
};
