import React, { useState, useMemo } from 'react';
import {
  Breadcrumb,
  BreadcrumbItem,
} from '../design-system';
import {
  AlertTriangle,
  CheckCircle2,
  XCircle,
  Plus,
  Search,
  X,
} from 'lucide-react';

export interface BudgetItem {
  id: string;
  name: string;
  scopeType: 'APPLICATION' | 'COST_CENTRE' | 'BUSINESS_UNIT' | 'ENVIRONMENT' | 'RESOURCE_GROUP';
  scopeName: string;
  amount: number;
  currency: string;
  period: 'MONTHLY' | 'QUARTERLY' | 'ANNUAL';
  currentSpend: number;
  forecastSpend: number;
  utilisationPct: number;
  status: 'ACTIVE' | 'IN_REVIEW' | 'DRAFT' | 'APPROVED' | 'REJECTED';
  hasOverlapWarning?: boolean;
  overlapWarningText?: string;
  hasOverAllocation?: boolean;
  overAllocationText?: string;
  owner: string;
}

const INITIAL_BUDGETS: BudgetItem[] = [
  {
    id: 'bgt-ecommerce-prod',
    name: 'Production E-Commerce Platform',
    scopeType: 'APPLICATION',
    scopeName: 'E-Commerce Core Suite',
    amount: 15000.0,
    currency: 'USD',
    period: 'MONTHLY',
    currentSpend: 11840.5,
    forecastSpend: 14920.0,
    utilisationPct: 78.9,
    status: 'ACTIVE',
    owner: 'Platform Lead (sarah.chen)',
  },
  {
    id: 'bgt-checkout-squad',
    name: 'Checkout & Cart Microservices',
    scopeType: 'APPLICATION',
    scopeName: 'Order Processing Squad',
    amount: 8500.0,
    currency: 'USD',
    period: 'MONTHLY',
    currentSpend: 7820.0,
    forecastSpend: 9240.0,
    utilisationPct: 92.0,
    status: 'ACTIVE',
    hasOverAllocation: true,
    overAllocationText: 'Forecast ($9,240.00) projects an 8.7% breach over allocated ceiling before billing cycle concludes.',
    owner: 'Checkout Squad (alex.m)',
  },
  {
    id: 'bgt-data-lake-analytics',
    name: 'Enterprise Big Data & Telemetry',
    scopeType: 'COST_CENTRE',
    scopeName: 'CC-DATA-ENG-402',
    amount: 25000.0,
    currency: 'USD',
    period: 'MONTHLY',
    currentSpend: 18450.0,
    forecastSpend: 24100.0,
    utilisationPct: 73.8,
    status: 'ACTIVE',
    hasOverlapWarning: true,
    overlapWarningText: 'Scope overlaps with BigData Sandbox budget (bgt-sandbox-09) covering identical S3 analytical buckets.',
    owner: 'Head of Data (marcus.v)',
  },
  {
    id: 'bgt-q4-cloud-migration',
    name: 'Q4 AWS to OCI Migration Staging',
    scopeType: 'ENVIRONMENT',
    scopeName: 'Staging & Load Testing',
    amount: 6000.0,
    currency: 'USD',
    period: 'MONTHLY',
    currentSpend: 1200.0,
    forecastSpend: 5400.0,
    utilisationPct: 20.0,
    status: 'IN_REVIEW',
    owner: 'DevOps Lead (raj.patel)',
  },
  {
    id: 'bgt-dev-sandbox-general',
    name: 'Corporate Engineering Sandbox Pool',
    scopeType: 'BUSINESS_UNIT',
    scopeName: 'Global Engineering BU',
    amount: 12000.0,
    currency: 'USD',
    period: 'MONTHLY',
    currentSpend: 4320.0,
    forecastSpend: 9800.0,
    utilisationPct: 36.0,
    status: 'ACTIVE',
    owner: 'VP Engineering (elena.rostova)',
  },
];

const BUDGET_TEMPLATES = [
  {
    id: 'tpl-prod-baseline',
    name: 'Production Tier Enterprise Baseline',
    scopeType: 'APPLICATION',
    defaultAmount: 20000,
    thresholds: 'Amber 80% / Red 100% / Breach 110%',
    description: 'Standard baseline with multi-tier notification routing to FinOps Lead and application owner.',
  },
  {
    id: 'tpl-dev-sandbox',
    name: 'Development Sandbox Strict Ceiling',
    scopeType: 'ENVIRONMENT',
    defaultAmount: 3000,
    thresholds: 'Amber 75% / Red 90% / Hard Stop 100%',
    description: 'Enforces strict ceiling with auto-stopping alert triggers for non-production environments.',
  },
  {
    id: 'tpl-microservice',
    name: 'Single Microservice Allocation',
    scopeType: 'APPLICATION',
    defaultAmount: 5000,
    thresholds: 'Amber 85% / Red 100%',
    description: 'Lightweight monthly allocation suitable for individual microservice or container task.',
  },
];

export const BudgetManagementPage: React.FC = () => {
  const [activeTab, setActiveTab] = useState<'budgets' | 'approvals' | 'templates'>('budgets');
  const [searchTerm, setSearchTerm] = useState('');
  const [statusFilter, setStatusFilter] = useState<string>('ALL');
  const [budgets, setBudgets] = useState<BudgetItem[]>(INITIAL_BUDGETS);
  const [isWizardOpen, setIsWizardOpen] = useState(false);
  const [wizardStep, setWizardStep] = useState<number>(1);
  const [approvalDecisionNotes, setApprovalDecisionNotes] = useState<Record<string, string>>({});

  // Wizard Form State
  const [newBudgetName, setNewBudgetName] = useState('');
  const [newScopeType, setNewScopeType] = useState<'APPLICATION' | 'COST_CENTRE' | 'BUSINESS_UNIT' | 'ENVIRONMENT'>('APPLICATION');
  const [newScopeName, setNewScopeName] = useState('');
  const [newAmount, setNewAmount] = useState<number>(10000);
  const [newPeriod, setNewPeriod] = useState<'MONTHLY' | 'QUARTERLY'>('MONTHLY');
  const [newOwner, setNewOwner] = useState('');

  const breadcrumbs: BreadcrumbItem[] = [
    { label: 'CloudLens', href: '/' },
    { label: 'Budget Management & Allocations', isCurrent: true },
  ];

  const filteredBudgets = useMemo(() => {
    return budgets.filter((b) => {
      if (statusFilter !== 'ALL' && b.status !== statusFilter) return false;
      if (searchTerm) {
        const query = searchTerm.toLowerCase();
        return (
          b.name.toLowerCase().includes(query) ||
          b.scopeName.toLowerCase().includes(query) ||
          b.owner.toLowerCase().includes(query)
        );
      }
      return true;
    });
  }, [budgets, statusFilter, searchTerm]);

  const pendingApprovals = useMemo(() => {
    return budgets.filter((b) => b.status === 'IN_REVIEW');
  }, [budgets]);

  const handleApprove = (id: string) => {
    setBudgets((prev) =>
      prev.map((b) => (b.id === id ? { ...b, status: 'ACTIVE' } : b))
    );
  };

  const handleReject = (id: string) => {
    setBudgets((prev) =>
      prev.map((b) => (b.id === id ? { ...b, status: 'REJECTED' } : b))
    );
  };

  const handleApplyTemplate = (tpl: typeof BUDGET_TEMPLATES[0]) => {
    setNewBudgetName(`${tpl.name} - ${new Date().toLocaleString('default', { month: 'short', year: 'numeric' })}`);
    setNewScopeType(tpl.scopeType as any);
    setNewAmount(tpl.defaultAmount);
    setIsWizardOpen(true);
    setWizardStep(1);
    setActiveTab('budgets');
  };

  const handleCreateBudgetSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const newBudget: BudgetItem = {
      id: `bgt-${Date.now()}`,
      name: newBudgetName || 'New Budget Allocation',
      scopeType: newScopeType,
      scopeName: newScopeName || 'Unassigned Scope',
      amount: newAmount,
      currency: 'USD',
      period: newPeriod,
      currentSpend: 0,
      forecastSpend: Number((newAmount * 0.85).toFixed(2)),
      utilisationPct: 0,
      status: 'ACTIVE',
      owner: newOwner || 'Current User (admin)',
    };

    setBudgets([newBudget, ...budgets]);
    setIsWizardOpen(false);
    setWizardStep(1);
    setNewBudgetName('');
    setNewScopeName('');
  };

  return (
    <div style={{ padding: '1.5rem 2rem', maxWidth: '1440px', margin: '0 auto', color: 'var(--text-primary, #f8fafc)' }}>
      {/* Breadcrumb Header */}
      <Breadcrumb items={breadcrumbs} className="mb-4" />

      {/* Title & Toolbar */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem', flexWrap: 'wrap', gap: '1rem' }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
            <h1 style={{ fontSize: '1.75rem', fontWeight: 700, margin: 0 }}>
              Budget Management &amp; Allocation Controls
            </h1>
            <span style={{ fontSize: '0.75rem', backgroundColor: '#0284c7', color: '#e0f2fe', padding: '0.2rem 0.6rem', borderRadius: '9999px', fontWeight: 600 }}>
              Prompt 41 / Prompts 28, 32
            </span>
          </div>
          <p style={{ margin: '0.25rem 0 0 0', color: 'var(--text-secondary, #94a3b8)', fontSize: '0.875rem' }}>
            Multi-tier budget thresholds, approval workflows, forecast utilization, template libraries, and automated overlap warnings.
          </p>
        </div>

        {/* Create Button */}
        <button
          type="button"
          onClick={() => {
            setIsWizardOpen(true);
            setWizardStep(1);
          }}
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: '0.4rem',
            padding: '0.5rem 1rem',
            borderRadius: '6px',
            backgroundColor: '#0284c7',
            color: '#ffffff',
            border: 'none',
            fontSize: '0.875rem',
            fontWeight: 600,
            cursor: 'pointer',
          }}
        >
          <Plus size={16} /> Create Budget Allocation
        </button>
      </div>

      {/* Navigation Tabs */}
      <div style={{ display: 'flex', borderBottom: '1px solid var(--border-color, #334155)', marginBottom: '1.5rem', gap: '0.5rem' }}>
        <button
          type="button"
          onClick={() => setActiveTab('budgets')}
          style={{
            padding: '0.6rem 1rem',
            borderBottom: activeTab === 'budgets' ? '2px solid #0284c7' : '2px solid transparent',
            color: activeTab === 'budgets' ? '#ffffff' : 'var(--text-secondary, #94a3b8)',
            backgroundColor: 'transparent',
            borderTop: 'none',
            borderLeft: 'none',
            borderRight: 'none',
            fontWeight: 600,
            fontSize: '0.875rem',
            cursor: 'pointer',
          }}
        >
          All Allocations ({budgets.length})
        </button>

        <button
          type="button"
          onClick={() => setActiveTab('approvals')}
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: '0.4rem',
            padding: '0.6rem 1rem',
            borderBottom: activeTab === 'approvals' ? '2px solid #0284c7' : '2px solid transparent',
            color: activeTab === 'approvals' ? '#ffffff' : 'var(--text-secondary, #94a3b8)',
            backgroundColor: 'transparent',
            borderTop: 'none',
            borderLeft: 'none',
            borderRight: 'none',
            fontWeight: 600,
            fontSize: '0.875rem',
            cursor: 'pointer',
          }}
        >
          Approval Queue
          {pendingApprovals.length > 0 && (
            <span style={{ fontSize: '0.75rem', backgroundColor: '#e11d48', color: '#fff', padding: '0.1rem 0.45rem', borderRadius: '9999px' }}>
              {pendingApprovals.length}
            </span>
          )}
        </button>

        <button
          type="button"
          onClick={() => setActiveTab('templates')}
          style={{
            padding: '0.6rem 1rem',
            borderBottom: activeTab === 'templates' ? '2px solid #0284c7' : '2px solid transparent',
            color: activeTab === 'templates' ? '#ffffff' : 'var(--text-secondary, #94a3b8)',
            backgroundColor: 'transparent',
            borderTop: 'none',
            borderLeft: 'none',
            borderRight: 'none',
            fontWeight: 600,
            fontSize: '0.875rem',
            cursor: 'pointer',
          }}
        >
          Enterprise Templates ({BUDGET_TEMPLATES.length})
        </button>
      </div>

      {/* TAB 1: Budget List */}
      {activeTab === 'budgets' && (
        <div>
          {/* Filter Bar */}
          <div style={{ display: 'flex', gap: '1rem', marginBottom: '1.25rem', flexWrap: 'wrap' }}>
            <div style={{ position: 'relative', flex: '1', minWidth: '240px' }}>
              <Search size={16} style={{ position: 'absolute', left: '10px', top: '10px', color: '#64748b' }} />
              <input
                type="text"
                placeholder="Search by budget name, scope, or owner..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                style={{
                  width: '100%',
                  padding: '0.45rem 0.75rem 0.45rem 2.25rem',
                  borderRadius: '6px',
                  backgroundColor: 'var(--bg-secondary, #1e293b)',
                  border: '1px solid var(--border-color, #334155)',
                  color: 'var(--text-primary, #f8fafc)',
                  fontSize: '0.875rem',
                }}
              />
            </div>

            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              style={{
                padding: '0.45rem 0.85rem',
                borderRadius: '6px',
                backgroundColor: 'var(--bg-secondary, #1e293b)',
                border: '1px solid var(--border-color, #334155)',
                color: 'var(--text-primary, #f8fafc)',
                fontSize: '0.875rem',
                cursor: 'pointer',
              }}
            >
              <option value="ALL">All Statuses</option>
              <option value="ACTIVE">Active</option>
              <option value="IN_REVIEW">In Review</option>
              <option value="REJECTED">Rejected</option>
            </select>
          </div>

          {/* Budget Cards Table */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
            {filteredBudgets.map((budget) => {
              const isOverUtilised = budget.utilisationPct > 90;
              const isWarning = budget.utilisationPct >= 75 && budget.utilisationPct <= 90;

              return (
                <div
                  key={budget.id}
                  style={{
                    backgroundColor: 'var(--bg-secondary, #1e293b)',
                    border: '1px solid var(--border-color, #334155)',
                    borderRadius: '8px',
                    padding: '1.25rem',
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '0.75rem', flexWrap: 'wrap', gap: '0.5rem' }}>
                    <div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                        <h3 style={{ margin: 0, fontSize: '1.1rem', fontWeight: 600 }}>{budget.name}</h3>
                        <span
                          style={{
                            fontSize: '0.75rem',
                            padding: '0.15rem 0.5rem',
                            borderRadius: '4px',
                            backgroundColor: budget.status === 'ACTIVE' ? '#064e3b' : '#7f1d1d',
                            color: budget.status === 'ACTIVE' ? '#6ee7b7' : '#fca5a5',
                            fontWeight: 600,
                          }}
                        >
                          {budget.status}
                        </span>
                        <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary, #94a3b8)' }}>
                          • {budget.scopeType}: <strong>{budget.scopeName}</strong>
                        </span>
                      </div>
                      <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary, #94a3b8)' }}>
                        Owner: {budget.owner} • Period: {budget.period}
                      </span>
                    </div>

                    <div style={{ textAlign: 'right' }}>
                      <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary, #94a3b8)', display: 'block' }}>
                        Budget Ceiling
                      </span>
                      <strong style={{ fontSize: '1.2rem', color: '#f8fafc' }}>
                        ${budget.amount.toLocaleString('en-US', { minimumFractionDigits: 2 })}
                      </strong>
                    </div>
                  </div>

                  {/* Utilization Progress Bar */}
                  <div style={{ marginBottom: '0.75rem' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.75rem', marginBottom: '0.25rem' }}>
                      <span style={{ color: 'var(--text-secondary, #94a3b8)' }}>
                        Current MTD Spend: <strong>${budget.currentSpend.toLocaleString('en-US', { minimumFractionDigits: 2 })}</strong>
                      </span>
                      <span style={{ fontWeight: 600, color: isOverUtilised ? '#ef4444' : isWarning ? '#f59e0b' : '#10b981' }}>
                        {budget.utilisationPct}% Consumed
                      </span>
                    </div>

                    <div style={{ width: '100%', height: '8px', backgroundColor: '#334155', borderRadius: '4px', overflow: 'hidden' }}>
                      <div
                        style={{
                          width: `${Math.min(100, budget.utilisationPct)}%`,
                          height: '100%',
                          backgroundColor: isOverUtilised ? '#ef4444' : isWarning ? '#f59e0b' : '#10b981',
                          borderRadius: '4px',
                        }}
                      />
                    </div>
                  </div>

                  {/* Overlap & Over-Allocation Warnings */}
                  {budget.hasOverAllocation && (
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', backgroundColor: 'rgba(239, 68, 68, 0.1)', border: '1px solid #dc2626', padding: '0.5rem 0.75rem', borderRadius: '4px', fontSize: '0.8125rem', color: '#fca5a5', marginBottom: '0.5rem' }}>
                      <AlertTriangle size={14} />
                      <strong>Over-allocation Warning:</strong> {budget.overAllocationText}
                    </div>
                  )}

                  {budget.hasOverlapWarning && (
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', backgroundColor: 'rgba(245, 158, 11, 0.1)', border: '1px solid #d97706', padding: '0.5rem 0.75rem', borderRadius: '4px', fontSize: '0.8125rem', color: '#fcd34d' }}>
                      <AlertTriangle size={14} />
                      <strong>Scope Overlap Warning:</strong> {budget.overlapWarningText}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* TAB 2: Approval Queue */}
      {activeTab === 'approvals' && (
        <div>
          {pendingApprovals.length === 0 ? (
            <div style={{ textAlign: 'center', padding: '3rem', backgroundColor: 'var(--bg-secondary, #1e293b)', borderRadius: '8px', border: '1px solid var(--border-color, #334155)' }}>
              <CheckCircle2 size={32} color="#10b981" style={{ margin: '0 auto 0.5rem auto' }} />
              <h3 style={{ margin: '0 0 0.25rem 0' }}>Approval Queue Clean</h3>
              <p style={{ color: 'var(--text-secondary, #94a3b8)', fontSize: '0.875rem', margin: 0 }}>
                All pending budget requests and threshold amendments have been evaluated.
              </p>
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
              {pendingApprovals.map((req) => (
                <div
                  key={req.id}
                  style={{
                    backgroundColor: 'var(--bg-secondary, #1e293b)',
                    border: '1px solid var(--border-color, #334155)',
                    borderRadius: '8px',
                    padding: '1.25rem',
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '0.75rem' }}>
                    <div>
                      <h3 style={{ margin: '0 0 0.25rem 0', fontSize: '1.1rem' }}>{req.name}</h3>
                      <span style={{ fontSize: '0.8125rem', color: 'var(--text-secondary, #94a3b8)' }}>
                        Requested by: <strong>{req.owner}</strong> • Scope: {req.scopeType} ({req.scopeName})
                      </span>
                    </div>

                    <div style={{ textAlign: 'right' }}>
                      <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary, #94a3b8)', display: 'block' }}>
                        Requested Amount
                      </span>
                      <strong style={{ fontSize: '1.2rem', color: '#38bdf8' }}>
                        ${req.amount.toLocaleString('en-US', { minimumFractionDigits: 2 })} / mo
                      </strong>
                    </div>
                  </div>

                  {/* Decision Controls */}
                  <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center', borderTop: '1px solid var(--border-color, #334155)', paddingTop: '0.75rem' }}>
                    <input
                      type="text"
                      placeholder="Enter review decision rationale..."
                      value={approvalDecisionNotes[req.id] || ''}
                      onChange={(e) =>
                        setApprovalDecisionNotes({ ...approvalDecisionNotes, [req.id]: e.target.value })
                      }
                      style={{
                        flex: 1,
                        padding: '0.4rem 0.6rem',
                        borderRadius: '4px',
                        border: '1px solid var(--border-color, #334155)',
                        backgroundColor: '#0f172a',
                        color: 'var(--text-primary, #f8fafc)',
                        fontSize: '0.8125rem',
                      }}
                    />

                    <button
                      type="button"
                      onClick={() => handleApprove(req.id)}
                      style={{
                        display: 'inline-flex',
                        alignItems: 'center',
                        gap: '0.3rem',
                        padding: '0.4rem 0.8rem',
                        borderRadius: '4px',
                        backgroundColor: '#16a34a',
                        color: '#fff',
                        border: 'none',
                        fontSize: '0.8125rem',
                        fontWeight: 600,
                        cursor: 'pointer',
                      }}
                    >
                      <CheckCircle2 size={14} /> Approve Allocation
                    </button>

                    <button
                      type="button"
                      onClick={() => handleReject(req.id)}
                      style={{
                        display: 'inline-flex',
                        alignItems: 'center',
                        gap: '0.3rem',
                        padding: '0.4rem 0.8rem',
                        borderRadius: '4px',
                        backgroundColor: '#dc2626',
                        color: '#fff',
                        border: 'none',
                        fontSize: '0.8125rem',
                        fontWeight: 600,
                        cursor: 'pointer',
                      }}
                    >
                      <XCircle size={14} /> Reject
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* TAB 3: Enterprise Templates */}
      {activeTab === 'templates' && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: '1.25rem' }}>
          {BUDGET_TEMPLATES.map((tpl) => (
            <div
              key={tpl.id}
              style={{
                backgroundColor: 'var(--bg-secondary, #1e293b)',
                border: '1px solid var(--border-color, #334155)',
                borderRadius: '8px',
                padding: '1.25rem',
                display: 'flex',
                flexDirection: 'column',
                justifyContent: 'space-between',
              }}
            >
              <div>
                <span style={{ fontSize: '0.75rem', color: '#38bdf8', fontWeight: 600, textTransform: 'uppercase' }}>
                  {tpl.scopeType} Template
                </span>
                <h3 style={{ margin: '0.25rem 0 0.5rem 0', fontSize: '1.1rem' }}>{tpl.name}</h3>
                <p style={{ fontSize: '0.8125rem', color: 'var(--text-secondary, #94a3b8)', margin: '0 0 1rem 0' }}>
                  {tpl.description}
                </p>

                <div style={{ backgroundColor: 'rgba(15, 23, 42, 0.5)', padding: '0.75rem', borderRadius: '6px', fontSize: '0.8125rem', marginBottom: '1rem' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.25rem' }}>
                    <span style={{ color: 'var(--text-secondary, #94a3b8)' }}>Default Baseline:</span>
                    <strong>${tpl.defaultAmount.toLocaleString()} / mo</strong>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span style={{ color: 'var(--text-secondary, #94a3b8)' }}>Notch Bands:</span>
                    <span style={{ color: '#fbbf24', fontSize: '0.75rem' }}>{tpl.thresholds}</span>
                  </div>
                </div>
              </div>

              <button
                type="button"
                onClick={() => handleApplyTemplate(tpl)}
                style={{
                  width: '100%',
                  padding: '0.5rem',
                  borderRadius: '6px',
                  backgroundColor: 'rgba(56, 189, 248, 0.1)',
                  border: '1px solid #0284c7',
                  color: '#38bdf8',
                  fontWeight: 600,
                  fontSize: '0.8125rem',
                  cursor: 'pointer',
                }}
              >
                Apply Template to New Allocation
              </button>
            </div>
          ))}
        </div>
      )}

      {/* Creation Wizard Modal */}
      {isWizardOpen && (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            backgroundColor: 'rgba(0, 0, 0, 0.75)',
            backdropFilter: 'blur(4px)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 100,
            padding: '1rem',
          }}
        >
          <div
            style={{
              backgroundColor: '#0f172a',
              border: '1px solid var(--border-color, #334155)',
              borderRadius: '12px',
              padding: '1.75rem',
              width: '100%',
              maxWidth: '540px',
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.25rem' }}>
              <div>
                <span style={{ fontSize: '0.75rem', color: '#38bdf8', fontWeight: 600 }}>STEP {wizardStep} OF 3</span>
                <h3 style={{ margin: 0, fontSize: '1.2rem' }}>
                  {wizardStep === 1 ? 'Scope & Amount' : wizardStep === 2 ? 'Threshold Bands' : 'Confirmation'}
                </h3>
              </div>
              <button
                type="button"
                onClick={() => setIsWizardOpen(false)}
                style={{ background: 'none', border: 'none', color: '#94a3b8', cursor: 'pointer' }}
              >
                <X size={18} />
              </button>
            </div>

            <form onSubmit={handleCreateBudgetSubmit}>
              {wizardStep === 1 && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.85rem' }}>
                  <div>
                    <label style={{ fontSize: '0.8125rem', color: 'var(--text-secondary, #94a3b8)', display: 'block', marginBottom: '0.25rem' }}>
                      Budget Allocation Title *
                    </label>
                    <input
                      type="text"
                      required
                      value={newBudgetName}
                      onChange={(e) => setNewBudgetName(e.target.value)}
                      placeholder="e.g. Core Checkout API Production"
                      style={{
                        width: '100%',
                        padding: '0.5rem',
                        borderRadius: '6px',
                        backgroundColor: '#1e293b',
                        border: '1px solid #334155',
                        color: '#f8fafc',
                        fontSize: '0.875rem',
                      }}
                    />
                  </div>

                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem' }}>
                    <div>
                      <label style={{ fontSize: '0.8125rem', color: 'var(--text-secondary, #94a3b8)', display: 'block', marginBottom: '0.25rem' }}>
                        Scope Type *
                      </label>
                      <select
                        value={newScopeType}
                        onChange={(e) => setNewScopeType(e.target.value as any)}
                        style={{
                          width: '100%',
                          padding: '0.5rem',
                          borderRadius: '6px',
                          backgroundColor: '#1e293b',
                          border: '1px solid #334155',
                          color: '#f8fafc',
                          fontSize: '0.875rem',
                        }}
                      >
                        <option value="APPLICATION">APPLICATION</option>
                        <option value="COST_CENTRE">COST_CENTRE</option>
                        <option value="BUSINESS_UNIT">BUSINESS_UNIT</option>
                        <option value="ENVIRONMENT">ENVIRONMENT</option>
                      </select>
                    </div>

                    <div>
                      <label style={{ fontSize: '0.8125rem', color: 'var(--text-secondary, #94a3b8)', display: 'block', marginBottom: '0.25rem' }}>
                        Scope Target Identifier *
                      </label>
                      <input
                        type="text"
                        required
                        value={newScopeName}
                        onChange={(e) => setNewScopeName(e.target.value)}
                        placeholder="e.g. app-ecommerce-01"
                        style={{
                          width: '100%',
                          padding: '0.5rem',
                          borderRadius: '6px',
                          backgroundColor: '#1e293b',
                          border: '1px solid #334155',
                          color: '#f8fafc',
                          fontSize: '0.875rem',
                        }}
                      />
                    </div>
                  </div>

                  <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: '0.75rem' }}>
                    <div>
                      <label style={{ fontSize: '0.8125rem', color: 'var(--text-secondary, #94a3b8)', display: 'block', marginBottom: '0.25rem' }}>
                        Amount Limit (USD) *
                      </label>
                      <input
                        type="number"
                        min="100"
                        step="100"
                        required
                        value={newAmount}
                        onChange={(e) => setNewAmount(Number(e.target.value))}
                        style={{
                          width: '100%',
                          padding: '0.5rem',
                          borderRadius: '6px',
                          backgroundColor: '#1e293b',
                          border: '1px solid #334155',
                          color: '#f8fafc',
                          fontSize: '0.875rem',
                        }}
                      />
                    </div>

                    <div>
                      <label style={{ fontSize: '0.8125rem', color: 'var(--text-secondary, #94a3b8)', display: 'block', marginBottom: '0.25rem' }}>
                        Period
                      </label>
                      <select
                        value={newPeriod}
                        onChange={(e) => setNewPeriod(e.target.value as any)}
                        style={{
                          width: '100%',
                          padding: '0.5rem',
                          borderRadius: '6px',
                          backgroundColor: '#1e293b',
                          border: '1px solid #334155',
                          color: '#f8fafc',
                          fontSize: '0.875rem',
                        }}
                      >
                        <option value="MONTHLY">Monthly</option>
                        <option value="QUARTERLY">Quarterly</option>
                      </select>
                    </div>
                  </div>

                  <div>
                    <label style={{ fontSize: '0.8125rem', color: 'var(--text-secondary, #94a3b8)', display: 'block', marginBottom: '0.25rem' }}>
                      Accountable Owner Email *
                    </label>
                    <input
                      type="email"
                      required
                      value={newOwner}
                      onChange={(e) => setNewOwner(e.target.value)}
                      placeholder="e.g. lead@enterprise.com"
                      style={{
                        width: '100%',
                        padding: '0.5rem',
                        borderRadius: '6px',
                        backgroundColor: '#1e293b',
                        border: '1px solid #334155',
                        color: '#f8fafc',
                        fontSize: '0.875rem',
                      }}
                    />
                  </div>
                </div>
              )}

              {wizardStep === 2 && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                  <div style={{ backgroundColor: 'rgba(15, 23, 42, 0.6)', padding: '1rem', borderRadius: '6px', border: '1px solid #334155' }}>
                    <h4 style={{ margin: '0 0 0.5rem 0', fontSize: '0.9rem', color: '#fbbf24' }}>Multi-Tier Notification Bands</h4>
                    <p style={{ margin: '0 0 0.75rem 0', fontSize: '0.8125rem', color: 'var(--text-secondary, #94a3b8)' }}>
                      Automated alerts are published to Slack and PagerDuty when consumption crosses threshold boundaries:
                    </p>
                    <ul style={{ margin: 0, paddingLeft: '1.25rem', fontSize: '0.8125rem', color: '#cbd5e1' }}>
                      <li><strong>Amber Advisory (80%):</strong> ${(newAmount * 0.8).toFixed(2)} - Informs owner squad.</li>
                      <li><strong>Red Warning (100%):</strong> ${(newAmount * 1.0).toFixed(2)} - Escalates to FinOps Lead.</li>
                      <li><strong>Critical Breach (110%):</strong> ${(newAmount * 1.1).toFixed(2)} - Triggers incident review.</li>
                    </ul>
                  </div>
                </div>
              )}

              {wizardStep === 3 && (
                <div style={{ backgroundColor: 'rgba(15, 23, 42, 0.6)', padding: '1rem', borderRadius: '6px', border: '1px solid #334155', fontSize: '0.875rem' }}>
                  <h4 style={{ margin: '0 0 0.5rem 0', color: '#38bdf8' }}>Ready to Activate Allocation</h4>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.25rem' }}>
                    <span style={{ color: 'var(--text-secondary, #94a3b8)' }}>Title:</span>
                    <strong>{newBudgetName}</strong>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.25rem' }}>
                    <span style={{ color: 'var(--text-secondary, #94a3b8)' }}>Scope:</span>
                    <strong>{newScopeType} ({newScopeName})</strong>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.25rem' }}>
                    <span style={{ color: 'var(--text-secondary, #94a3b8)' }}>Limit:</span>
                    <strong style={{ color: '#10b981' }}>${newAmount.toLocaleString()} USD / {newPeriod}</strong>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span style={{ color: 'var(--text-secondary, #94a3b8)' }}>Owner:</span>
                    <strong>{newOwner}</strong>
                  </div>
                </div>
              )}

              {/* Wizard Action Buttons */}
              <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: '1.5rem' }}>
                {wizardStep > 1 ? (
                  <button
                    type="button"
                    onClick={() => setWizardStep(wizardStep - 1)}
                    style={{
                      padding: '0.45rem 0.85rem',
                      borderRadius: '6px',
                      backgroundColor: 'transparent',
                      border: '1px solid #334155',
                      color: '#94a3b8',
                      cursor: 'pointer',
                    }}
                  >
                    Back
                  </button>
                ) : (
                  <div />
                )}

                {wizardStep < 3 ? (
                  <button
                    type="button"
                    onClick={() => setWizardStep(wizardStep + 1)}
                    style={{
                      padding: '0.45rem 1rem',
                      borderRadius: '6px',
                      backgroundColor: '#0284c7',
                      color: '#fff',
                      border: 'none',
                      fontWeight: 600,
                      cursor: 'pointer',
                    }}
                  >
                    Next Step
                  </button>
                ) : (
                  <button
                    type="submit"
                    style={{
                      padding: '0.45rem 1.25rem',
                      borderRadius: '6px',
                      backgroundColor: '#16a34a',
                      color: '#fff',
                      border: 'none',
                      fontWeight: 600,
                      cursor: 'pointer',
                    }}
                  >
                    Confirm &amp; Activate Budget
                  </button>
                )}
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
