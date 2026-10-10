import React, { useEffect, useState, useCallback } from 'react';
import { Breadcrumb, FreshnessIndicator } from '../design-system';
import { DemoModeBanner } from '../components/DemoModeBanner';
import { useAuth } from '../context/AuthContext';
import {
  Settings,
  Save,
  RotateCcw,
  History,
  Bell,
  Shield,
  Clock,
  Coins,
  Sliders,
  Database,
  Plus,
  Edit2,
  Trash2,
  Search,
  CheckCircle2,
  AlertTriangle,
  X,
} from 'lucide-react';

interface AuditHistoryItem {
  id: string;
  timestamp: string;
  actor: string;
  action: string;
  details: Record<string, any>;
}

export const SettingsPage: React.FC<{ isDemo?: boolean }> = ({ isDemo = false }) => {
  const { currentTenant } = useAuth();
  const tenantId = currentTenant?.id || 'tenant-snpl-prod-17bd57';

  const [activeTab, setActiveTab] = useState<
    'general' | 'schedules' | 'thresholds' | 'notifications' | 'security' | 'currency' | 'maintenance' | 'objects'
  >('general');

  // Loading & ETag State
  const [loading, setLoading] = useState<boolean>(true);
  const [currentETag, setCurrentETag] = useState<string>('');
  const [saveStatus, setSaveStatus] = useState<{ type: 'success' | 'error'; message: string } | null>(null);
  const [validationErrors, setValidationErrors] = useState<string[]>([]);

  // History Drawer State
  const [historyOpen, setHistoryOpen] = useState<boolean>(false);
  const [historyItems, setHistoryItems] = useState<AuditHistoryItem[]>([]);
  const [historyLoading, setHistoryLoading] = useState<boolean>(false);

  // Notification Test Feedback State
  const [testStatus, setTestStatus] = useState<{ type: 'success' | 'error'; message: string } | null>(null);
  const [testLoading, setTestLoading] = useState<boolean>(false);

  // Configuration Form State
  const [config, setConfig] = useState({
    // General
    reporting_currency: 'USD',
    fiscal_calendar_start_month: 1,
    default_time_zone: 'UTC',
    cost_basis_default: 'billed',
    forecast_method_default: 'linear',

    // Sync schedules
    default_cron_expression: '0 */6 * * *',
    sync_batch_size: 500,
    sync_timeout_seconds: 3600,
    sync_retry_attempts: 3,
    sync_backoff_factor: 2.0,

    // Threshold bands
    anomaly_percentage_threshold: 20.0,
    budget_alert_thresholds: '80, 100, 120',
    unit_cost_variance_threshold: 15.0,
    idle_cpu_threshold: 5.0,

    // Notifications
    smtp_host: 'mailpit.internal',
    smtp_port: 1025,
    smtp_sender: 'alerts@cloudlens.internal',
    smtp_use_tls: false,
    webhook_url: 'https://webhook.internal/cloudlens/events',
    webhook_signing_secret_ref: 'vault://secret/notifications/webhook_signing_key',

    // Security
    session_idle_timeout_seconds: 1800,
    session_absolute_lifetime_seconds: 28800,
    access_token_ttl_seconds: 900,
    step_up_token_ttl_seconds: 300,
    mfa_required_roles: 'SUPER_ADMIN, PLATFORM_ADMIN',
    act_as_duration_minutes: 60,

    // Currency & FX
    presentation_currencies: 'USD, EUR, GBP, JPY',
    fx_rate_provider: 'MASTER_DATA',
    fx_refresh_cadence_hours: 24,
    fx_variance_threshold_percentage: 5.0,

    // Maintenance Mode
    maintenance_enabled: false,
    maintenance_banner_message: 'CloudLens is currently undergoing scheduled platform maintenance. Mutating operations are paused.',
    maintenance_allowed_roles: 'SUPER_ADMIN',
  });

  const [initialConfig, setInitialConfig] = useState(config);

  // Business Objects State
  const [selectedEntity, setSelectedEntity] = useState<string>('applications');
  const [objectsList, setObjectsList] = useState<any[]>([]);
  const [objectsTotal, setObjectsTotal] = useState<number>(0);
  const [objectsPage, setObjectsPage] = useState<number>(0);
  const [objectsSearch, setObjectsSearch] = useState<string>('');
  const [objectsSortCol, setObjectsSortCol] = useState<string>('created_at');
  const [objectsSortDir, setObjectsSortDir] = useState<'asc' | 'desc'>('desc');
  const [objectsLoading, setObjectsLoading] = useState<boolean>(false);

  // Business Object Modal State (Create / Edit)
  const [modalOpen, setModalOpen] = useState<boolean>(false);
  const [editingObject, setEditingObject] = useState<any | null>(null);
  const [editingETag, setEditingETag] = useState<string>('');
  const [formData, setFormData] = useState<Record<string, any>>({});
  const [modalError, setModalError] = useState<string | null>(null);

  // Load Settings from API
  const fetchSettings = useCallback(async () => {
    setLoading(true);
    setSaveStatus(null);
    try {
      const res = await fetch(`/api/v1/tenants/${tenantId}/settings`);
      if (res.ok) {
        const etag = res.headers.get('ETag') || '';
        setCurrentETag(etag);
        const data = await res.json();

        const notif = data.notification_settings || {};
        const sec = data.security_settings || {};
        const cfx = data.currency_fx_settings || {};
        const mm = data.maintenance_mode_settings || {};
        const syn = data.sync_schedule_settings || {};
        const th = data.threshold_defaults || {};

        const loaded = {
          reporting_currency: data.reporting_currency || cfx.reporting_currency || 'USD',
          fiscal_calendar_start_month: data.fiscal_calendar_start_month || 1,
          default_time_zone: data.default_time_zone || 'UTC',
          cost_basis_default: data.cost_basis_default || 'billed',
          forecast_method_default: data.forecast_method_default || 'linear',

          default_cron_expression: syn.default_cron_expression || '0 */6 * * *',
          sync_batch_size: syn.batch_size || 500,
          sync_timeout_seconds: syn.timeout_seconds || 3600,
          sync_retry_attempts: syn.max_retries || 3,
          sync_backoff_factor: syn.backoff_factor || 2.0,

          anomaly_percentage_threshold: th.anomaly_percentage_threshold || 20.0,
          budget_alert_thresholds: Array.isArray(th.budget_alert_thresholds)
            ? th.budget_alert_thresholds.join(', ')
            : '80, 100, 120',
          unit_cost_variance_threshold: th.unit_cost_variance_threshold || 15.0,
          idle_cpu_threshold: 5.0,

          smtp_host: notif.smtp_host || 'mailpit.internal',
          smtp_port: notif.smtp_port || 1025,
          smtp_sender: notif.smtp_sender || 'alerts@cloudlens.internal',
          smtp_use_tls: Boolean(notif.smtp_use_tls),
          webhook_url: notif.webhook_url || 'https://webhook.internal/cloudlens/events',
          webhook_signing_secret_ref: notif.webhook_signing_secret_ref || 'vault://secret/notifications/webhook_signing_key',

          session_idle_timeout_seconds: sec.session_idle_timeout_seconds || data.session_idle_timeout_seconds || 1800,
          session_absolute_lifetime_seconds: sec.session_absolute_lifetime_seconds || data.session_absolute_lifetime_seconds || 28800,
          access_token_ttl_seconds: sec.access_token_ttl_seconds || data.access_token_ttl_seconds || 900,
          step_up_token_ttl_seconds: sec.step_up_token_ttl_seconds || data.step_up_token_ttl_seconds || 300,
          mfa_required_roles: Array.isArray(sec.mfa_required_roles)
            ? sec.mfa_required_roles.join(', ')
            : Array.isArray(data.mfa_required_roles)
            ? data.mfa_required_roles.join(', ')
            : 'SUPER_ADMIN, PLATFORM_ADMIN',
          act_as_duration_minutes: sec.act_as_duration_minutes || data.act_as_duration_minutes || 60,

          presentation_currencies: Array.isArray(cfx.presentation_currencies)
            ? cfx.presentation_currencies.join(', ')
            : 'USD, EUR, GBP, JPY',
          fx_rate_provider: cfx.fx_rate_provider || 'MASTER_DATA',
          fx_refresh_cadence_hours: cfx.fx_refresh_cadence_hours || 24,
          fx_variance_threshold_percentage: cfx.fx_variance_threshold_percentage || 5.0,

          maintenance_enabled: Boolean(mm.enabled),
          maintenance_banner_message: mm.banner_message || 'CloudLens is currently undergoing scheduled platform maintenance. Mutating operations are paused.',
          maintenance_allowed_roles: Array.isArray(mm.allowed_roles) ? mm.allowed_roles.join(', ') : 'SUPER_ADMIN',
        };

        setConfig(loaded);
        setInitialConfig(loaded);
      }
    } catch (err: any) {
      setSaveStatus({ type: 'error', message: `Failed to load settings: ${err.message}` });
    } finally {
      setLoading(false);
    }
  }, [tenantId]);

  useEffect(() => {
    fetchSettings();
  }, [fetchSettings]);

  // Validate form before save
  const validateSettings = (): boolean => {
    const errors: string[] = [];
    if (!config.reporting_currency || config.reporting_currency.trim().length !== 3) {
      errors.push('Reporting currency must be a valid 3-letter ISO code (e.g., USD, EUR, GBP).');
    }
    if (config.fiscal_calendar_start_month < 1 || config.fiscal_calendar_start_month > 12) {
      errors.push('Fiscal calendar start month must be between 1 and 12.');
    }
    if (config.session_idle_timeout_seconds <= 0) {
      errors.push('Session idle timeout must be greater than 0 seconds.');
    }
    if (config.session_absolute_lifetime_seconds <= 0) {
      errors.push('Session absolute lifetime must be greater than 0 seconds.');
    }
    if (config.act_as_duration_minutes <= 0) {
      errors.push('Act-as administrative session duration must be greater than 0 minutes.');
    }
    if (config.smtp_port <= 0 || config.smtp_port > 65535) {
      errors.push('SMTP port must be a valid port number (1-65535).');
    }
    setValidationErrors(errors);
    return errors.length === 0;
  };

  // Save Settings to API with ETag If-Match header
  const handleSaveSettings = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!validateSettings()) {
      return;
    }

    setSaveStatus(null);
    try {
      const payload = {
        reporting_currency: config.reporting_currency.toUpperCase().trim(),
        fiscal_calendar_start_month: Number(config.fiscal_calendar_start_month),
        default_time_zone: config.default_time_zone.trim(),
        cost_basis_default: config.cost_basis_default,
        forecast_method_default: config.forecast_method_default,

        sync_schedule_settings: {
          default_cron_expression: config.default_cron_expression,
          batch_size: Number(config.sync_batch_size),
          timeout_seconds: Number(config.sync_timeout_seconds),
          max_retries: Number(config.sync_retry_attempts),
          backoff_factor: Number(config.sync_backoff_factor),
        },

        threshold_defaults: {
          anomaly_percentage_threshold: Number(config.anomaly_percentage_threshold),
          budget_alert_thresholds: config.budget_alert_thresholds
            .split(',')
            .map((s) => parseFloat(s.trim()))
            .filter((n) => !isNaN(n)),
          unit_cost_variance_threshold: Number(config.unit_cost_variance_threshold),
        },

        notification_settings: {
          smtp_host: config.smtp_host.trim(),
          smtp_port: Number(config.smtp_port),
          smtp_sender: config.smtp_sender.trim(),
          smtp_use_tls: config.smtp_use_tls,
          webhook_url: config.webhook_url.trim(),
          webhook_signing_secret_ref: config.webhook_signing_secret_ref.trim(),
        },

        security_settings: {
          session_idle_timeout_seconds: Number(config.session_idle_timeout_seconds),
          session_absolute_lifetime_seconds: Number(config.session_absolute_lifetime_seconds),
          access_token_ttl_seconds: Number(config.access_token_ttl_seconds),
          step_up_token_ttl_seconds: Number(config.step_up_token_ttl_seconds),
          mfa_required_roles: config.mfa_required_roles
            .split(',')
            .map((s) => s.trim().toUpperCase())
            .filter(Boolean),
          act_as_duration_minutes: Number(config.act_as_duration_minutes),
        },

        currency_fx_settings: {
          reporting_currency: config.reporting_currency.toUpperCase().trim(),
          presentation_currencies: config.presentation_currencies
            .split(',')
            .map((s) => s.trim().toUpperCase())
            .filter(Boolean),
          fx_rate_provider: config.fx_rate_provider,
          fx_refresh_cadence_hours: Number(config.fx_refresh_cadence_hours),
          fx_variance_threshold_percentage: Number(config.fx_variance_threshold_percentage),
        },

        maintenance_mode_settings: {
          enabled: config.maintenance_enabled,
          banner_message: config.maintenance_banner_message.trim(),
          allowed_roles: config.maintenance_allowed_roles
            .split(',')
            .map((s) => s.trim().toUpperCase())
            .filter(Boolean),
        },
      };

      const res = await fetch(`/api/v1/tenants/${tenantId}/settings`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          'If-Match': currentETag,
        },
        body: JSON.stringify(payload),
      });

      if (res.status === 412) {
        setSaveStatus({
          type: 'error',
          message: 'Precondition Failed (412): Configuration was modified concurrently by another administrative session. Please refresh and review changes before saving.',
        });
        return;
      }

      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.detail || `Server returned error ${res.status}`);
      }

      const newETag = res.headers.get('ETag') || '';
      if (newETag) setCurrentETag(newETag);
      setInitialConfig({ ...config });
      setSaveStatus({
        type: 'success',
        message: 'Tenant settings successfully updated and cryptographically audited to PostgreSQL.',
      });
    } catch (err: any) {
      setSaveStatus({ type: 'error', message: err.message || 'Failed to update configuration.' });
    }
  };

  // Reset form to last loaded values
  const handleResetSettings = () => {
    setConfig({ ...initialConfig });
    setValidationErrors([]);
    setSaveStatus(null);
  };

  // Notification Test (SMTP or Webhook)
  const handleTestNotification = async (type: 'SMTP' | 'WEBHOOK') => {
    setTestLoading(true);
    setTestStatus(null);
    try {
      const target = type === 'SMTP' ? config.smtp_sender : config.webhook_url;
      const res = await fetch('/api/v1/config/test-notification', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ type, target }),
      });
      const data = await res.json();
      if (res.ok && data.success) {
        setTestStatus({ type: 'success', message: `${type} Test Successful: ${data.message}` });
      } else {
        setTestStatus({ type: 'error', message: `${type} Test Failed: ${data.detail || 'Relay check failed'}` });
      }
    } catch (err: any) {
      setTestStatus({ type: 'error', message: `Test dispatch error: ${err.message}` });
    } finally {
      setTestLoading(false);
    }
  };

  // Fetch Audit Change History
  const handleOpenHistory = async () => {
    setHistoryOpen(true);
    setHistoryLoading(true);
    try {
      const res = await fetch(`/api/v1/tenants/${tenantId}/settings/history`);
      if (res.ok) {
        const items = await res.json();
        setHistoryItems(items);
      }
    } catch {
      setHistoryItems([]);
    } finally {
      setHistoryLoading(false);
    }
  };

  // Load Business Objects List
  const fetchObjects = useCallback(async () => {
    setObjectsLoading(true);
    try {
      const params = new URLSearchParams({
        limit: '10',
        offset: String(objectsPage * 10),
        sort_by: objectsSortCol,
        sort_order: objectsSortDir,
      });
      if (objectsSearch.trim()) {
        params.set('search', objectsSearch.trim());
      }
      const res = await fetch(`/api/v1/business-objects/${selectedEntity}?${params.toString()}`);
      if (res.ok) {
        const data = await res.json();
        setObjectsList(data.items || []);
        setObjectsTotal(data.total || 0);
      } else {
        setObjectsList([]);
        setObjectsTotal(0);
      }
    } catch {
      setObjectsList([]);
      setObjectsTotal(0);
    } finally {
      setObjectsLoading(false);
    }
  }, [selectedEntity, objectsPage, objectsSortCol, objectsSortDir, objectsSearch]);

  useEffect(() => {
    if (activeTab === 'objects') {
      fetchObjects();
    }
  }, [activeTab, fetchObjects]);

  // Business Object Modal Open (Create / Edit)
  const handleOpenCreateModal = () => {
    setEditingObject(null);
    setEditingETag('');
    setModalError(null);

    // Default template per entity
    const defaults: Record<string, any> = {
      applications: { code: 'APP-PROD-01', name: 'Billing Service', criticality: 'BUSINESS_CRITICAL' },
      owners: { name: 'FinOps Guild', email: 'finops@cloudlens.internal', department: 'Engineering' },
      cost_centers: { code: 'CC-ENG-01', name: 'Cloud Infrastructure' },
      business_units: { code: 'BU-ENG', name: 'Digital Platforms' },
      environments: { name: 'Production West', category: 'PRODUCTION' },
      runtime_schedules: { name: 'Nightly Non-Prod Halt', schedule_payload: { cron: '0 20 * * 1-5', action: 'STOP' } },
      remediation_tasks: { title: 'Idle EBS Volume Termination', category: 'STORAGE_HYGIENE', priority: 'HIGH', state: 'OPEN' },
      provisioning_requests: { target_scope: 'AWS-GLOBAL-PROD', status: 'PENDING' },
      users: { email: 'ops.lead@cloudlens.internal', display_name: 'Lead Operations Engineer', roles: ['FINOPS_ANALYST'] },
      budgets: { name: 'FY26 Core Platform Budget', amount: 50000.0, currency: 'USD', period: 'MONTHLY' },
      policies: { name: 'Mandatory Resource Tagging', rule_type: 'TAG_REQUIRED', severity: 'HIGH' },
    };

    setFormData(defaults[selectedEntity] || { name: 'New Record' });
    setModalOpen(true);
  };

  const handleOpenEditModal = async (obj: any) => {
    setEditingObject(obj);
    setModalError(null);
    try {
      const res = await fetch(`/api/v1/business-objects/${selectedEntity}/${obj.id}`);
      if (res.ok) {
        const etag = res.headers.get('ETag') || '';
        setEditingETag(etag);
        const data = await res.json();
        setFormData(data);
      } else {
        setFormData(obj);
      }
    } catch {
      setFormData(obj);
    }
    setModalOpen(true);
  };

  const handleSaveModal = async (e: React.FormEvent) => {
    e.preventDefault();
    setModalError(null);
    try {
      const isEdit = Boolean(editingObject);
      const url = isEdit
        ? `/api/v1/business-objects/${selectedEntity}/${editingObject.id}`
        : `/api/v1/business-objects/${selectedEntity}`;
      const method = isEdit ? 'PUT' : 'POST';

      const headers: Record<string, string> = { 'Content-Type': 'application/json' };
      if (isEdit && editingETag) {
        headers['If-Match'] = editingETag;
      }

      const res = await fetch(url, {
        method,
        headers,
        body: JSON.stringify(formData),
      });

      if (res.status === 412) {
        setModalError('Precondition Failed (412): Item modified concurrently. Please reload.');
        return;
      }
      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.detail || `Server error: ${res.status}`);
      }

      setModalOpen(false);
      fetchObjects();
    } catch (err: any) {
      setModalError(err.message || 'Operation failed');
    }
  };

  const handleDeleteObject = async (id: string) => {
    if (!window.confirm(`Are you sure you want to delete ${selectedEntity} item '${id}'?`)) return;
    try {
      const res = await fetch(`/api/v1/business-objects/${selectedEntity}/${id}`, {
        method: 'DELETE',
      });
      if (res.ok || res.status === 204) {
        fetchObjects();
      } else {
        alert('Failed to delete item.');
      }
    } catch (err: any) {
      alert(`Delete error: ${err.message}`);
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem', width: '100%' }}>
      <DemoModeBanner isDemo={isDemo} />

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Breadcrumb
          items={[
            { label: 'Home', href: '/' },
            { label: 'Configuration & Settings', isCurrent: true },
          ]}
        />
        <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center' }}>
          <button
            data-testid="history-open-btn"
            onClick={handleOpenHistory}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '0.4rem',
              padding: '0.4rem 0.8rem',
              borderRadius: '6px',
              border: '1px solid var(--border-color)',
              backgroundColor: 'var(--bg-secondary)',
              color: 'var(--text-primary)',
              cursor: 'pointer',
              fontSize: '0.8125rem',
              fontWeight: 500,
            }}
          >
            <History size={15} />
            <span>Audit History</span>
          </button>
          <FreshnessIndicator lastSyncedAt={new Date().toISOString()} provider="System Configuration" />
        </div>
      </div>

      <header style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '0.25rem' }}>
            <h1 style={{ fontSize: '1.75rem', fontWeight: 700, margin: 0, color: 'var(--text-primary)' }}>
              Configuration Panel & Business Objects
            </h1>
            <span
              style={{
                padding: '0.2rem 0.6rem',
                borderRadius: '9999px',
                backgroundColor: 'rgba(56, 189, 248, 0.15)',
                border: '1px solid rgba(56, 189, 248, 0.3)',
                color: '#38bdf8',
                fontSize: '0.75rem',
                fontWeight: 600,
              }}
            >
              ETag Concurrency Protected
            </span>
          </div>
          <p style={{ color: 'var(--text-secondary)', margin: 0, fontSize: '0.9rem' }}>
            Enterprise tenant parameters, schedules, thresholds, credentials, notifications, and editable business objects.
          </p>
        </div>

        {/* Global Action Bar for Configuration Form */}
        {activeTab !== 'objects' && (
          <div style={{ display: 'flex', gap: '0.75rem' }}>
            <button
              type="button"
              data-testid="cancel-config-btn"
              onClick={handleResetSettings}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '0.4rem',
                padding: '0.5rem 1rem',
                borderRadius: '6px',
                border: '1px solid var(--border-color)',
                backgroundColor: 'transparent',
                color: 'var(--text-secondary)',
                cursor: 'pointer',
                fontWeight: 600,
                fontSize: '0.875rem',
              }}
            >
              <RotateCcw size={16} />
              <span>Cancel</span>
            </button>
            <button
              type="button"
              data-testid="save-config-btn"
              onClick={handleSaveSettings}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '0.4rem',
                padding: '0.5rem 1.25rem',
                borderRadius: '6px',
                border: 'none',
                backgroundColor: '#0284c7',
                color: '#ffffff',
                cursor: 'pointer',
                fontWeight: 600,
                fontSize: '0.875rem',
              }}
            >
              <Save size={16} />
              <span>Save Changes</span>
            </button>
          </div>
        )}
      </header>

      {/* Validation and Status Feedback Banners */}
      {validationErrors.length > 0 && (
        <div
          data-testid="validation-errors-box"
          style={{
            padding: '0.75rem 1rem',
            backgroundColor: '#450a0a',
            border: '1px solid #b91c1c',
            borderRadius: '6px',
            color: '#fca5a5',
            fontSize: '0.875rem',
          }}
        >
          <div style={{ fontWeight: 600, marginBottom: '0.25rem' }}>Please correct the following errors:</div>
          <ul style={{ margin: 0, paddingLeft: '1.25rem' }}>
            {validationErrors.map((err, idx) => (
              <li key={idx}>{err}</li>
            ))}
          </ul>
        </div>
      )}

      {saveStatus && (
        <div
          data-testid="save-status-banner"
          role="status"
          style={{
            padding: '0.75rem 1rem',
            borderRadius: '6px',
            fontSize: '0.875rem',
            display: 'flex',
            alignItems: 'center',
            gap: '0.5rem',
            backgroundColor: saveStatus.type === 'success' ? '#064e3b' : '#7f1d1d',
            border: `1px solid ${saveStatus.type === 'success' ? '#059669' : '#dc2626'}`,
            color: saveStatus.type === 'success' ? '#6ee7b7' : '#fca5a5',
          }}
        >
          {saveStatus.type === 'success' ? <CheckCircle2 size={18} /> : <AlertTriangle size={18} />}
          <span>{saveStatus.message}</span>
        </div>
      )}

      {/* 8-Tab Navigation Bar */}
      <div style={{ borderBottom: '1px solid var(--border-color)', display: 'flex', gap: '0.5rem', overflowX: 'auto' }}>
        {[
          { id: 'general', label: 'General', icon: Sliders },
          { id: 'schedules', label: 'Sync Schedules', icon: Clock },
          { id: 'thresholds', label: 'Threshold Bands', icon: Settings },
          { id: 'notifications', label: 'Notifications', icon: Bell },
          { id: 'security', label: 'Security', icon: Shield },
          { id: 'currency', label: 'Currency & FX', icon: Coins },
          { id: 'maintenance', label: 'Maintenance Mode', icon: AlertTriangle },
          { id: 'objects', label: 'Business Objects', icon: Database },
        ].map((tab) => {
          const Icon = tab.icon;
          const isActive = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              data-testid={`tab-${tab.id}`}
              onClick={() => setActiveTab(tab.id as any)}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '0.5rem',
                padding: '0.6rem 1rem',
                backgroundColor: 'transparent',
                border: 'none',
                borderBottom: isActive ? '2px solid #0284c7' : '2px solid transparent',
                color: isActive ? '#38bdf8' : 'var(--text-secondary)',
                fontWeight: isActive ? 600 : 500,
                cursor: 'pointer',
                fontSize: '0.875rem',
                whiteSpace: 'nowrap',
              }}
            >
              <Icon size={16} />
              <span>{tab.label}</span>
            </button>
          );
        })}
      </div>

      {loading ? (
        <div style={{ padding: '3rem', textAlign: 'center', color: 'var(--text-secondary)' }}>
          Loading configuration state...
        </div>
      ) : (
        <div>
          {/* TAB 1: GENERAL */}
          {activeTab === 'general' && (
            <section
              style={{
                backgroundColor: 'var(--bg-secondary)',
                borderRadius: '8px',
                border: '1px solid var(--border-color)',
                padding: '1.5rem',
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
                gap: '1.25rem',
              }}
            >
              <div>
                <label style={{ display: 'block', fontSize: '0.8125rem', color: 'var(--text-secondary)', marginBottom: '0.35rem' }}>
                  Canonical Reporting Currency (ISO 4217)
                </label>
                <input
                  type="text"
                  data-testid="input-reporting-currency"
                  value={config.reporting_currency}
                  onChange={(e) => setConfig({ ...config, reporting_currency: e.target.value })}
                  style={{ width: '100%', padding: '0.5rem', borderRadius: '6px', border: '1px solid var(--border-color)', backgroundColor: 'var(--bg-primary)', color: 'var(--text-primary)' }}
                />
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '0.8125rem', color: 'var(--text-secondary)', marginBottom: '0.35rem' }}>
                  Fiscal Calendar Start Month (1 - 12)
                </label>
                <input
                  type="number"
                  min="1"
                  max="12"
                  data-testid="input-fiscal-month"
                  value={config.fiscal_calendar_start_month}
                  onChange={(e) => setConfig({ ...config, fiscal_calendar_start_month: parseInt(e.target.value) || 1 })}
                  style={{ width: '100%', padding: '0.5rem', borderRadius: '6px', border: '1px solid var(--border-color)', backgroundColor: 'var(--bg-primary)', color: 'var(--text-primary)' }}
                />
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '0.8125rem', color: 'var(--text-secondary)', marginBottom: '0.35rem' }}>
                  Default Platform Time Zone (IANA)
                </label>
                <input
                  type="text"
                  value={config.default_time_zone}
                  onChange={(e) => setConfig({ ...config, default_time_zone: e.target.value })}
                  style={{ width: '100%', padding: '0.5rem', borderRadius: '6px', border: '1px solid var(--border-color)', backgroundColor: 'var(--bg-primary)', color: 'var(--text-primary)' }}
                />
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '0.8125rem', color: 'var(--text-secondary)', marginBottom: '0.35rem' }}>
                  Cost Basis Default Representation
                </label>
                <select
                  value={config.cost_basis_default}
                  onChange={(e) => setConfig({ ...config, cost_basis_default: e.target.value })}
                  style={{ width: '100%', padding: '0.5rem', borderRadius: '6px', border: '1px solid var(--border-color)', backgroundColor: 'var(--bg-primary)', color: 'var(--text-primary)' }}
                >
                  <option value="billed">Billed (Invoice / Cash Flow)</option>
                  <option value="amortised">Amortised (Accrual / Commitment Spreading)</option>
                </select>
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '0.8125rem', color: 'var(--text-secondary)', marginBottom: '0.35rem' }}>
                  Forecasting Default Algorithm
                </label>
                <select
                  value={config.forecast_method_default}
                  onChange={(e) => setConfig({ ...config, forecast_method_default: e.target.value })}
                  style={{ width: '100%', padding: '0.5rem', borderRadius: '6px', border: '1px solid var(--border-color)', backgroundColor: 'var(--bg-primary)', color: 'var(--text-primary)' }}
                >
                  <option value="linear">Linear Regression</option>
                  <option value="exponential">Exponential Smoothing</option>
                  <option value="arima">ARIMA Statistical Model</option>
                </select>
              </div>
            </section>
          )}

          {/* TAB 2: SYNC SCHEDULES */}
          {activeTab === 'schedules' && (
            <section
              style={{
                backgroundColor: 'var(--bg-secondary)',
                borderRadius: '8px',
                border: '1px solid var(--border-color)',
                padding: '1.5rem',
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
                gap: '1.25rem',
              }}
            >
              <div>
                <label style={{ display: 'block', fontSize: '0.8125rem', color: 'var(--text-secondary)', marginBottom: '0.35rem' }}>
                  Default Connector Cron Expression
                </label>
                <input
                  type="text"
                  data-testid="input-cron-expression"
                  value={config.default_cron_expression}
                  onChange={(e) => setConfig({ ...config, default_cron_expression: e.target.value })}
                  style={{ width: '100%', padding: '0.5rem', borderRadius: '6px', border: '1px solid var(--border-color)', backgroundColor: 'var(--bg-primary)', color: 'var(--text-primary)' }}
                />
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '0.8125rem', color: 'var(--text-secondary)', marginBottom: '0.35rem' }}>
                  Pipeline Ingestion Batch Size
                </label>
                <input
                  type="number"
                  value={config.sync_batch_size}
                  onChange={(e) => setConfig({ ...config, sync_batch_size: parseInt(e.target.value) || 500 })}
                  style={{ width: '100%', padding: '0.5rem', borderRadius: '6px', border: '1px solid var(--border-color)', backgroundColor: 'var(--bg-primary)', color: 'var(--text-primary)' }}
                />
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '0.8125rem', color: 'var(--text-secondary)', marginBottom: '0.35rem' }}>
                  Execution Timeout (Seconds)
                </label>
                <input
                  type="number"
                  value={config.sync_timeout_seconds}
                  onChange={(e) => setConfig({ ...config, sync_timeout_seconds: parseInt(e.target.value) || 3600 })}
                  style={{ width: '100%', padding: '0.5rem', borderRadius: '6px', border: '1px solid var(--border-color)', backgroundColor: 'var(--bg-primary)', color: 'var(--text-primary)' }}
                />
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '0.8125rem', color: 'var(--text-secondary)', marginBottom: '0.35rem' }}>
                  Maximum Ingestion Retry Attempts
                </label>
                <input
                  type="number"
                  value={config.sync_retry_attempts}
                  onChange={(e) => setConfig({ ...config, sync_retry_attempts: parseInt(e.target.value) || 3 })}
                  style={{ width: '100%', padding: '0.5rem', borderRadius: '6px', border: '1px solid var(--border-color)', backgroundColor: 'var(--bg-primary)', color: 'var(--text-primary)' }}
                />
              </div>
            </section>
          )}

          {/* TAB 3: THRESHOLD BANDS */}
          {activeTab === 'thresholds' && (
            <section
              style={{
                backgroundColor: 'var(--bg-secondary)',
                borderRadius: '8px',
                border: '1px solid var(--border-color)',
                padding: '1.5rem',
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
                gap: '1.25rem',
              }}
            >
              <div>
                <label style={{ display: 'block', fontSize: '0.8125rem', color: 'var(--text-secondary)', marginBottom: '0.35rem' }}>
                  Cost Anomaly Spike Threshold (%)
                </label>
                <input
                  type="number"
                  step="0.1"
                  value={config.anomaly_percentage_threshold}
                  onChange={(e) => setConfig({ ...config, anomaly_percentage_threshold: parseFloat(e.target.value) || 20.0 })}
                  style={{ width: '100%', padding: '0.5rem', borderRadius: '6px', border: '1px solid var(--border-color)', backgroundColor: 'var(--bg-primary)', color: 'var(--text-primary)' }}
                />
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '0.8125rem', color: 'var(--text-secondary)', marginBottom: '0.35rem' }}>
                  Budget Alert Notification Bands (Comma-separated %)
                </label>
                <input
                  type="text"
                  value={config.budget_alert_thresholds}
                  onChange={(e) => setConfig({ ...config, budget_alert_thresholds: e.target.value })}
                  style={{ width: '100%', padding: '0.5rem', borderRadius: '6px', border: '1px solid var(--border-color)', backgroundColor: 'var(--bg-primary)', color: 'var(--text-primary)' }}
                />
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '0.8125rem', color: 'var(--text-secondary)', marginBottom: '0.35rem' }}>
                  Unit Cost Variance Warning (%)
                </label>
                <input
                  type="number"
                  step="0.1"
                  value={config.unit_cost_variance_threshold}
                  onChange={(e) => setConfig({ ...config, unit_cost_variance_threshold: parseFloat(e.target.value) || 15.0 })}
                  style={{ width: '100%', padding: '0.5rem', borderRadius: '6px', border: '1px solid var(--border-color)', backgroundColor: 'var(--bg-primary)', color: 'var(--text-primary)' }}
                />
              </div>
            </section>
          )}

          {/* TAB 4: NOTIFICATIONS */}
          {activeTab === 'notifications' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
              <section
                style={{
                  backgroundColor: 'var(--bg-secondary)',
                  borderRadius: '8px',
                  border: '1px solid var(--border-color)',
                  padding: '1.5rem',
                  display: 'grid',
                  gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
                  gap: '1.25rem',
                }}
              >
                <div>
                  <label style={{ display: 'block', fontSize: '0.8125rem', color: 'var(--text-secondary)', marginBottom: '0.35rem' }}>
                    SMTP Relay Host
                  </label>
                  <input
                    type="text"
                    value={config.smtp_host}
                    onChange={(e) => setConfig({ ...config, smtp_host: e.target.value })}
                    style={{ width: '100%', padding: '0.5rem', borderRadius: '6px', border: '1px solid var(--border-color)', backgroundColor: 'var(--bg-primary)', color: 'var(--text-primary)' }}
                  />
                </div>

                <div>
                  <label style={{ display: 'block', fontSize: '0.8125rem', color: 'var(--text-secondary)', marginBottom: '0.35rem' }}>
                    SMTP Relay Port
                  </label>
                  <input
                    type="number"
                    value={config.smtp_port}
                    onChange={(e) => setConfig({ ...config, smtp_port: parseInt(e.target.value) || 1025 })}
                    style={{ width: '100%', padding: '0.5rem', borderRadius: '6px', border: '1px solid var(--border-color)', backgroundColor: 'var(--bg-primary)', color: 'var(--text-primary)' }}
                  />
                </div>

                <div>
                  <label style={{ display: 'block', fontSize: '0.8125rem', color: 'var(--text-secondary)', marginBottom: '0.35rem' }}>
                    Notification Sender Email
                  </label>
                  <input
                    type="email"
                    value={config.smtp_sender}
                    onChange={(e) => setConfig({ ...config, smtp_sender: e.target.value })}
                    style={{ width: '100%', padding: '0.5rem', borderRadius: '6px', border: '1px solid var(--border-color)', backgroundColor: 'var(--bg-primary)', color: 'var(--text-primary)' }}
                  />
                </div>

                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', paddingTop: '1.25rem' }}>
                  <input
                    type="checkbox"
                    id="smtp-tls"
                    checked={config.smtp_use_tls}
                    onChange={(e) => setConfig({ ...config, smtp_use_tls: e.target.checked })}
                  />
                  <label htmlFor="smtp-tls" style={{ fontSize: '0.875rem', color: 'var(--text-primary)' }}>
                    Enforce TLS Relay Encryption
                  </label>
                </div>

                <div style={{ gridColumn: '1 / -1' }}>
                  <label style={{ display: 'block', fontSize: '0.8125rem', color: 'var(--text-secondary)', marginBottom: '0.35rem' }}>
                    Outbound Webhook Delivery Endpoint
                  </label>
                  <input
                    type="url"
                    value={config.webhook_url}
                    onChange={(e) => setConfig({ ...config, webhook_url: e.target.value })}
                    style={{ width: '100%', padding: '0.5rem', borderRadius: '6px', border: '1px solid var(--border-color)', backgroundColor: 'var(--bg-primary)', color: 'var(--text-primary)' }}
                  />
                </div>

                <div style={{ gridColumn: '1 / -1' }}>
                  <label style={{ display: 'block', fontSize: '0.8125rem', color: 'var(--text-secondary)', marginBottom: '0.35rem' }}>
                    Webhook HMAC Signing Key (Vault Reference)
                  </label>
                  <input
                    type="text"
                    value={config.webhook_signing_secret_ref}
                    onChange={(e) => setConfig({ ...config, webhook_signing_secret_ref: e.target.value })}
                    style={{ width: '100%', padding: '0.5rem', borderRadius: '6px', border: '1px solid var(--border-color)', backgroundColor: 'var(--bg-primary)', color: 'var(--text-primary)' }}
                  />
                </div>
              </section>

              {/* Live Test Trigger Section */}
              <div
                style={{
                  backgroundColor: 'var(--bg-secondary)',
                  borderRadius: '8px',
                  border: '1px solid var(--border-color)',
                  padding: '1.25rem',
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                }}
              >
                <div>
                  <h3 style={{ margin: '0 0 0.25rem 0', fontSize: '0.9375rem' }}>Channel Connectivity Verification</h3>
                  <p style={{ margin: 0, color: 'var(--text-secondary)', fontSize: '0.8125rem' }}>
                    Dispatches a probe message to verify SMTP or webhook relay with cryptographic audit recording.
                  </p>
                </div>
                <div style={{ display: 'flex', gap: '0.75rem' }}>
                  <button
                    type="button"
                    data-testid="test-smtp-btn"
                    disabled={testLoading}
                    onClick={() => handleTestNotification('SMTP')}
                    style={{
                      padding: '0.4rem 0.8rem',
                      borderRadius: '6px',
                      border: '1px solid #0284c7',
                      backgroundColor: 'rgba(2, 132, 199, 0.1)',
                      color: '#38bdf8',
                      cursor: 'pointer',
                      fontSize: '0.8125rem',
                      fontWeight: 600,
                    }}
                  >
                    Test SMTP Relay
                  </button>
                  <button
                    type="button"
                    data-testid="test-webhook-btn"
                    disabled={testLoading}
                    onClick={() => handleTestNotification('WEBHOOK')}
                    style={{
                      padding: '0.4rem 0.8rem',
                      borderRadius: '6px',
                      border: '1px solid #10b981',
                      backgroundColor: 'rgba(16, 185, 129, 0.1)',
                      color: '#34d399',
                      cursor: 'pointer',
                      fontSize: '0.8125rem',
                      fontWeight: 600,
                    }}
                  >
                    Test Webhook
                  </button>
                </div>
              </div>

              {testStatus && (
                <div
                  data-testid="notification-test-feedback"
                  style={{
                    padding: '0.75rem 1rem',
                    borderRadius: '6px',
                    fontSize: '0.875rem',
                    backgroundColor: testStatus.type === 'success' ? '#064e3b' : '#7f1d1d',
                    border: `1px solid ${testStatus.type === 'success' ? '#059669' : '#dc2626'}`,
                    color: testStatus.type === 'success' ? '#6ee7b7' : '#fca5a5',
                  }}
                >
                  {testStatus.message}
                </div>
              )}
            </div>
          )}

          {/* TAB 5: SECURITY */}
          {activeTab === 'security' && (
            <section
              style={{
                backgroundColor: 'var(--bg-secondary)',
                borderRadius: '8px',
                border: '1px solid var(--border-color)',
                padding: '1.5rem',
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
                gap: '1.25rem',
              }}
            >
              <div>
                <label style={{ display: 'block', fontSize: '0.8125rem', color: 'var(--text-secondary)', marginBottom: '0.35rem' }}>
                  Session Idle Timeout (Seconds)
                </label>
                <input
                  type="number"
                  data-testid="input-idle-timeout"
                  value={config.session_idle_timeout_seconds}
                  onChange={(e) => setConfig({ ...config, session_idle_timeout_seconds: parseInt(e.target.value) || 1800 })}
                  style={{ width: '100%', padding: '0.5rem', borderRadius: '6px', border: '1px solid var(--border-color)', backgroundColor: 'var(--bg-primary)', color: 'var(--text-primary)' }}
                />
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '0.8125rem', color: 'var(--text-secondary)', marginBottom: '0.35rem' }}>
                  Session Absolute Lifetime (Seconds)
                </label>
                <input
                  type="number"
                  value={config.session_absolute_lifetime_seconds}
                  onChange={(e) => setConfig({ ...config, session_absolute_lifetime_seconds: parseInt(e.target.value) || 28800 })}
                  style={{ width: '100%', padding: '0.5rem', borderRadius: '6px', border: '1px solid var(--border-color)', backgroundColor: 'var(--bg-primary)', color: 'var(--text-primary)' }}
                />
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '0.8125rem', color: 'var(--text-secondary)', marginBottom: '0.35rem' }}>
                  Access Token TTL (Seconds)
                </label>
                <input
                  type="number"
                  value={config.access_token_ttl_seconds}
                  onChange={(e) => setConfig({ ...config, access_token_ttl_seconds: parseInt(e.target.value) || 900 })}
                  style={{ width: '100%', padding: '0.5rem', borderRadius: '6px', border: '1px solid var(--border-color)', backgroundColor: 'var(--bg-primary)', color: 'var(--text-primary)' }}
                />
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '0.8125rem', color: 'var(--text-secondary)', marginBottom: '0.35rem' }}>
                  Step-Up Elevation Token TTL (Seconds)
                </label>
                <input
                  type="number"
                  value={config.step_up_token_ttl_seconds}
                  onChange={(e) => setConfig({ ...config, step_up_token_ttl_seconds: parseInt(e.target.value) || 300 })}
                  style={{ width: '100%', padding: '0.5rem', borderRadius: '6px', border: '1px solid var(--border-color)', backgroundColor: 'var(--bg-primary)', color: 'var(--text-primary)' }}
                />
              </div>

              <div style={{ gridColumn: '1 / -1' }}>
                <label style={{ display: 'block', fontSize: '0.8125rem', color: 'var(--text-secondary)', marginBottom: '0.35rem' }}>
                  MFA Mandatory Roles (Comma-separated)
                </label>
                <input
                  type="text"
                  data-testid="input-mfa-roles"
                  value={config.mfa_required_roles}
                  onChange={(e) => setConfig({ ...config, mfa_required_roles: e.target.value })}
                  style={{ width: '100%', padding: '0.5rem', borderRadius: '6px', border: '1px solid var(--border-color)', backgroundColor: 'var(--bg-primary)', color: 'var(--text-primary)' }}
                />
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '0.8125rem', color: 'var(--text-secondary)', marginBottom: '0.35rem' }}>
                  Act-As Administrative Duration (Minutes)
                </label>
                <input
                  type="number"
                  value={config.act_as_duration_minutes}
                  onChange={(e) => setConfig({ ...config, act_as_duration_minutes: parseInt(e.target.value) || 60 })}
                  style={{ width: '100%', padding: '0.5rem', borderRadius: '6px', border: '1px solid var(--border-color)', backgroundColor: 'var(--bg-primary)', color: 'var(--text-primary)' }}
                />
              </div>
            </section>
          )}

          {/* TAB 6: CURRENCY & FX */}
          {activeTab === 'currency' && (
            <section
              style={{
                backgroundColor: 'var(--bg-secondary)',
                borderRadius: '8px',
                border: '1px solid var(--border-color)',
                padding: '1.5rem',
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
                gap: '1.25rem',
              }}
            >
              <div>
                <label style={{ display: 'block', fontSize: '0.8125rem', color: 'var(--text-secondary)', marginBottom: '0.35rem' }}>
                  Base Currency
                </label>
                <input
                  type="text"
                  value={config.reporting_currency}
                  onChange={(e) => setConfig({ ...config, reporting_currency: e.target.value })}
                  style={{ width: '100%', padding: '0.5rem', borderRadius: '6px', border: '1px solid var(--border-color)', backgroundColor: 'var(--bg-primary)', color: 'var(--text-primary)' }}
                />
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '0.8125rem', color: 'var(--text-secondary)', marginBottom: '0.35rem' }}>
                  Presentation Currencies (Comma-separated)
                </label>
                <input
                  type="text"
                  value={config.presentation_currencies}
                  onChange={(e) => setConfig({ ...config, presentation_currencies: e.target.value })}
                  style={{ width: '100%', padding: '0.5rem', borderRadius: '6px', border: '1px solid var(--border-color)', backgroundColor: 'var(--bg-primary)', color: 'var(--text-primary)' }}
                />
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '0.8125rem', color: 'var(--text-secondary)', marginBottom: '0.35rem' }}>
                  Exchange Rate Provider Standard
                </label>
                <select
                  value={config.fx_rate_provider}
                  onChange={(e) => setConfig({ ...config, fx_rate_provider: e.target.value })}
                  style={{ width: '100%', padding: '0.5rem', borderRadius: '6px', border: '1px solid var(--border-color)', backgroundColor: 'var(--bg-primary)', color: 'var(--text-primary)' }}
                >
                  <option value="MASTER_DATA">Master Data Rate Cards</option>
                  <option value="ECB">European Central Bank Public Feed</option>
                  <option value="FIXED">Fixed Commercial Contract Rate</option>
                </select>
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '0.8125rem', color: 'var(--text-secondary)', marginBottom: '0.35rem' }}>
                  FX Refresh Cadence (Hours)
                </label>
                <input
                  type="number"
                  value={config.fx_refresh_cadence_hours}
                  onChange={(e) => setConfig({ ...config, fx_refresh_cadence_hours: parseInt(e.target.value) || 24 })}
                  style={{ width: '100%', padding: '0.5rem', borderRadius: '6px', border: '1px solid var(--border-color)', backgroundColor: 'var(--bg-primary)', color: 'var(--text-primary)' }}
                />
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '0.8125rem', color: 'var(--text-secondary)', marginBottom: '0.35rem' }}>
                  Rate Swing Variance Warning (%)
                </label>
                <input
                  type="number"
                  step="0.1"
                  value={config.fx_variance_threshold_percentage}
                  onChange={(e) => setConfig({ ...config, fx_variance_threshold_percentage: parseFloat(e.target.value) || 5.0 })}
                  style={{ width: '100%', padding: '0.5rem', borderRadius: '6px', border: '1px solid var(--border-color)', backgroundColor: 'var(--bg-primary)', color: 'var(--text-primary)' }}
                />
              </div>
            </section>
          )}

          {/* TAB 7: MAINTENANCE MODE */}
          {activeTab === 'maintenance' && (
            <section
              style={{
                backgroundColor: 'var(--bg-secondary)',
                borderRadius: '8px',
                border: '1px solid var(--border-color)',
                padding: '1.5rem',
                display: 'flex',
                flexDirection: 'column',
                gap: '1.25rem',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                <input
                  type="checkbox"
                  id="maint-mode-toggle"
                  data-testid="maint-mode-toggle"
                  checked={config.maintenance_enabled}
                  onChange={(e) => setConfig({ ...config, maintenance_enabled: e.target.checked })}
                  style={{ width: '1.25rem', height: '1.25rem' }}
                />
                <label htmlFor="maint-mode-toggle" style={{ fontWeight: 600, fontSize: '1rem', color: 'var(--text-primary)' }}>
                  Activate Platform Maintenance Mode
                </label>
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '0.8125rem', color: 'var(--text-secondary)', marginBottom: '0.35rem' }}>
                  Platform Banner Notice Message
                </label>
                <textarea
                  data-testid="input-maint-message"
                  rows={3}
                  value={config.maintenance_banner_message}
                  onChange={(e) => setConfig({ ...config, maintenance_banner_message: e.target.value })}
                  style={{ width: '100%', padding: '0.5rem', borderRadius: '6px', border: '1px solid var(--border-color)', backgroundColor: 'var(--bg-primary)', color: 'var(--text-primary)' }}
                />
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '0.8125rem', color: 'var(--text-secondary)', marginBottom: '0.35rem' }}>
                  Allowed Administrative Roles (Bypass Mode)
                </label>
                <input
                  type="text"
                  value={config.maintenance_allowed_roles}
                  onChange={(e) => setConfig({ ...config, maintenance_allowed_roles: e.target.value })}
                  style={{ width: '100%', padding: '0.5rem', borderRadius: '6px', border: '1px solid var(--border-color)', backgroundColor: 'var(--bg-primary)', color: 'var(--text-primary)' }}
                />
              </div>
            </section>
          )}

          {/* TAB 8: BUSINESS OBJECTS CONSOLE */}
          {activeTab === 'objects' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
              {/* Entity Selector Bar & Controls */}
              <div
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  backgroundColor: 'var(--bg-secondary)',
                  padding: '0.75rem 1rem',
                  borderRadius: '8px',
                  border: '1px solid var(--border-color)',
                  flexWrap: 'wrap',
                  gap: '0.75rem',
                }}
              >
                <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center' }}>
                  <label htmlFor="entity-type-select" style={{ fontSize: '0.875rem', fontWeight: 600, color: 'var(--text-secondary)' }}>
                    Business Object:
                  </label>
                  <select
                    id="entity-type-select"
                    data-testid="business-object-selector"
                    value={selectedEntity}
                    onChange={(e) => {
                      setSelectedEntity(e.target.value);
                      setObjectsPage(0);
                    }}
                    style={{
                      padding: '0.4rem 0.8rem',
                      borderRadius: '6px',
                      border: '1px solid var(--border-color)',
                      backgroundColor: 'var(--bg-primary)',
                      color: 'var(--text-primary)',
                      fontSize: '0.875rem',
                      fontWeight: 500,
                    }}
                  >
                    <option value="applications">Applications</option>
                    <option value="owners">Owners / Teams</option>
                    <option value="cost_centers">Cost Centres</option>
                    <option value="business_units">Business Units</option>
                    <option value="environments">Environments</option>
                    <option value="budgets">Budgets</option>
                    <option value="policies">Policies</option>
                    <option value="runtime_schedules">Runtime Schedules</option>
                    <option value="remediation_tasks">Remediation Tasks</option>
                    <option value="provisioning_requests">Provisioning Requests</option>
                    <option value="users">Users</option>
                  </select>
                </div>

                <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center' }}>
                  <div style={{ position: 'relative' }}>
                    <Search size={15} style={{ position: 'absolute', left: '0.6rem', top: '50%', transform: 'translateY(-50%)', color: 'var(--text-secondary)' }} />
                    <input
                      type="text"
                      data-testid="business-object-search"
                      placeholder={`Search ${selectedEntity}...`}
                      value={objectsSearch}
                      onChange={(e) => {
                        setObjectsSearch(e.target.value);
                        setObjectsPage(0);
                      }}
                      style={{
                        padding: '0.4rem 0.6rem 0.4rem 2rem',
                        borderRadius: '6px',
                        border: '1px solid var(--border-color)',
                        backgroundColor: 'var(--bg-primary)',
                        color: 'var(--text-primary)',
                        fontSize: '0.8125rem',
                        width: '220px',
                      }}
                    />
                  </div>

                  <button
                    data-testid="create-object-btn"
                    onClick={handleOpenCreateModal}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '0.35rem',
                      padding: '0.4rem 0.8rem',
                      borderRadius: '6px',
                      border: 'none',
                      backgroundColor: '#0284c7',
                      color: '#ffffff',
                      cursor: 'pointer',
                      fontSize: '0.8125rem',
                      fontWeight: 600,
                    }}
                  >
                    <Plus size={15} />
                    <span>Create Record</span>
                  </button>
                </div>
              </div>

              {/* Data Table */}
              <div style={{ border: '1px solid var(--border-color)', borderRadius: '8px', overflow: 'hidden' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.875rem' }}>
                  <thead>
                    <tr style={{ backgroundColor: 'var(--bg-secondary)', borderBottom: '1px solid var(--border-color)', textAlign: 'left' }}>
                      <th onClick={() => { setObjectsSortCol('id'); setObjectsSortDir(objectsSortDir === 'asc' ? 'desc' : 'asc'); }} style={{ padding: '0.6rem 0.8rem', cursor: 'pointer' }}>Identifier</th>
                      <th onClick={() => { setObjectsSortCol('name'); setObjectsSortDir(objectsSortDir === 'asc' ? 'desc' : 'asc'); }} style={{ padding: '0.6rem 0.8rem', cursor: 'pointer' }}>Name / Title</th>
                      <th style={{ padding: '0.6rem 0.8rem' }}>Primary Attribute</th>
                      <th style={{ padding: '0.6rem 0.8rem' }}>Secondary Attribute</th>
                      <th style={{ padding: '0.6rem 0.8rem', textAlign: 'right' }}>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {objectsLoading ? (
                      <tr>
                        <td colSpan={5} style={{ padding: '2rem', textAlign: 'center', color: 'var(--text-secondary)' }}>
                          Loading {selectedEntity}...
                        </td>
                      </tr>
                    ) : objectsList.length === 0 ? (
                      <tr>
                        <td colSpan={5} data-testid="empty-objects-row" style={{ padding: '2rem', textAlign: 'center', color: 'var(--text-secondary)' }}>
                          No {selectedEntity} records found.
                        </td>
                      </tr>
                    ) : (
                      objectsList.map((obj) => {
                        const prim = obj.code || obj.email || obj.amount || obj.rule_type || obj.state || obj.status || obj.category || '-';
                        const sec = obj.criticality || obj.department || obj.currency || obj.severity || obj.priority || obj.target_scope || (Array.isArray(obj.roles) ? obj.roles.join(', ') : '-');
                        return (
                          <tr key={obj.id} data-testid={`object-row-${obj.id}`} style={{ borderBottom: '1px solid var(--border-color)' }}>
                            <td style={{ padding: '0.6rem 0.8rem', fontWeight: 600, color: '#38bdf8' }}>{obj.id}</td>
                            <td style={{ padding: '0.6rem 0.8rem' }}>{obj.name || obj.title || obj.display_name || obj.code || obj.id}</td>
                            <td style={{ padding: '0.6rem 0.8rem' }}>{String(prim)}</td>
                            <td style={{ padding: '0.6rem 0.8rem' }}>{String(sec)}</td>
                            <td style={{ padding: '0.6rem 0.8rem', textAlign: 'right' }}>
                              <div style={{ display: 'inline-flex', gap: '0.5rem' }}>
                                <button
                                  data-testid={`edit-btn-${obj.id}`}
                                  onClick={() => handleOpenEditModal(obj)}
                                  style={{
                                    padding: '0.25rem 0.5rem',
                                    borderRadius: '4px',
                                    border: '1px solid var(--border-color)',
                                    backgroundColor: 'transparent',
                                    color: 'var(--text-primary)',
                                    cursor: 'pointer',
                                    fontSize: '0.75rem',
                                  }}
                                >
                                  <Edit2 size={13} />
                                </button>
                                <button
                                  data-testid={`delete-btn-${obj.id}`}
                                  onClick={() => handleDeleteObject(obj.id)}
                                  style={{
                                    padding: '0.25rem 0.5rem',
                                    borderRadius: '4px',
                                    border: '1px solid #dc2626',
                                    backgroundColor: 'rgba(220, 38, 38, 0.1)',
                                    color: '#f87171',
                                    cursor: 'pointer',
                                    fontSize: '0.75rem',
                                  }}
                                >
                                  <Trash2 size={13} />
                                </button>
                              </div>
                            </td>
                          </tr>
                        );
                      })
                    )}
                  </tbody>
                </table>
              </div>

              {/* Server-Side Pagination Bar */}
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '0.8125rem', color: 'var(--text-secondary)' }}>
                <span>
                  Showing {objectsList.length} of {objectsTotal} records
                </span>
                <div style={{ display: 'flex', gap: '0.5rem' }}>
                  <button
                    disabled={objectsPage === 0}
                    onClick={() => setObjectsPage((p) => Math.max(0, p - 1))}
                    style={{
                      padding: '0.3rem 0.6rem',
                      borderRadius: '4px',
                      border: '1px solid var(--border-color)',
                      backgroundColor: 'var(--bg-secondary)',
                      color: 'var(--text-primary)',
                      cursor: objectsPage === 0 ? 'not-allowed' : 'pointer',
                      opacity: objectsPage === 0 ? 0.5 : 1,
                    }}
                  >
                    Previous
                  </button>
                  <span style={{ alignSelf: 'center' }}>
                    Page {objectsPage + 1} of {Math.max(1, Math.ceil(objectsTotal / 10))}
                  </span>
                  <button
                    disabled={(objectsPage + 1) * 10 >= objectsTotal}
                    onClick={() => setObjectsPage((p) => p + 1)}
                    style={{
                      padding: '0.3rem 0.6rem',
                      borderRadius: '4px',
                      border: '1px solid var(--border-color)',
                      backgroundColor: 'var(--bg-secondary)',
                      color: 'var(--text-primary)',
                      cursor: (objectsPage + 1) * 10 >= objectsTotal ? 'not-allowed' : 'pointer',
                      opacity: (objectsPage + 1) * 10 >= objectsTotal ? 0.5 : 1,
                    }}
                  >
                    Next
                  </button>
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* History Drawer Modal */}
      {historyOpen && (
        <div
          data-testid="history-drawer"
          style={{
            position: 'fixed',
            inset: 0,
            backgroundColor: 'rgba(0,0,0,0.6)',
            display: 'flex',
            justifyContent: 'flex-end',
            zIndex: 1000,
          }}
        >
          <div
            style={{
              width: '450px',
              backgroundColor: 'var(--bg-primary)',
              height: '100%',
              padding: '1.5rem',
              boxSizing: 'border-box',
              display: 'flex',
              flexDirection: 'column',
              boxShadow: '-4px 0 20px rgba(0,0,0,0.5)',
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.25rem' }}>
              <h2 style={{ fontSize: '1.25rem', fontWeight: 700, margin: 0 }}>Configuration Change History</h2>
              <button
                onClick={() => setHistoryOpen(false)}
                style={{ background: 'none', border: 'none', color: 'var(--text-secondary)', cursor: 'pointer' }}
              >
                <X size={20} />
              </button>
            </div>

            <div style={{ flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
              {historyLoading ? (
                <div style={{ textAlign: 'center', color: 'var(--text-secondary)' }}>Loading audit history...</div>
              ) : historyItems.length === 0 ? (
                <div style={{ textAlign: 'center', color: 'var(--text-secondary)' }}>No configuration changes recorded yet.</div>
              ) : (
                historyItems.map((item) => (
                  <div
                    key={item.id}
                    style={{
                      padding: '0.8rem',
                      backgroundColor: 'var(--bg-secondary)',
                      borderRadius: '6px',
                      border: '1px solid var(--border-color)',
                      fontSize: '0.8125rem',
                    }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.25rem' }}>
                      <span style={{ fontWeight: 600, color: '#38bdf8' }}>{item.action}</span>
                      <span style={{ color: 'var(--text-secondary)' }}>{new Date(item.timestamp).toLocaleTimeString()}</span>
                    </div>
                    <div style={{ color: 'var(--text-secondary)' }}>By: <strong>{item.actor}</strong></div>
                    <pre style={{ backgroundColor: '#0f172a', padding: '0.4rem', borderRadius: '4px', marginTop: '0.4rem', fontSize: '0.75rem', overflowX: 'auto' }}>
                      {JSON.stringify(item.details, null, 2)}
                    </pre>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      )}

      {/* Business Object Create/Edit Modal */}
      {modalOpen && (
        <div
          data-testid="business-object-modal"
          style={{
            position: 'fixed',
            inset: 0,
            backgroundColor: 'rgba(0,0,0,0.7)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 1000,
          }}
        >
          <div
            style={{
              backgroundColor: 'var(--bg-secondary)',
              borderRadius: '8px',
              border: '1px solid var(--border-color)',
              padding: '1.5rem',
              width: '500px',
              maxWidth: '90vw',
              maxHeight: '90vh',
              overflowY: 'auto',
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
              <h3 style={{ margin: 0, fontSize: '1.125rem' }}>
                {editingObject ? `Edit ${selectedEntity}: ${editingObject.id}` : `Create New ${selectedEntity}`}
              </h3>
              <button
                onClick={() => setModalOpen(false)}
                style={{ background: 'none', border: 'none', color: 'var(--text-secondary)', cursor: 'pointer' }}
              >
                <X size={18} />
              </button>
            </div>

            {modalError && (
              <div style={{ padding: '0.5rem 0.75rem', backgroundColor: '#7f1d1d', color: '#fca5a5', borderRadius: '6px', fontSize: '0.8125rem', marginBottom: '1rem' }}>
                {modalError}
              </div>
            )}

            <form onSubmit={handleSaveModal} style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
              {/* Common Name or Title */}
              {(selectedEntity !== 'users' && selectedEntity !== 'provisioning_requests') && (
                <div>
                  <label style={{ display: 'block', fontSize: '0.8125rem', color: 'var(--text-secondary)', marginBottom: '0.25rem' }}>
                    {selectedEntity === 'remediation_tasks' ? 'Task Title' : 'Name'}
                  </label>
                  <input
                    type="text"
                    data-testid="modal-input-name"
                    required
                    value={formData.name || formData.title || ''}
                    onChange={(e) => {
                      if (selectedEntity === 'remediation_tasks') {
                        setFormData({ ...formData, title: e.target.value });
                      } else {
                        setFormData({ ...formData, name: e.target.value });
                      }
                    }}
                    style={{ width: '100%', padding: '0.45rem', borderRadius: '6px', border: '1px solid var(--border-color)', backgroundColor: 'var(--bg-primary)', color: 'var(--text-primary)' }}
                  />
                </div>
              )}

              {/* Code field for applications, cost_centers, business_units */}
              {['applications', 'cost_centers', 'business_units'].includes(selectedEntity) && (
                <div>
                  <label style={{ display: 'block', fontSize: '0.8125rem', color: 'var(--text-secondary)', marginBottom: '0.25rem' }}>
                    Unique Business Code
                  </label>
                  <input
                    type="text"
                    data-testid="modal-input-code"
                    required
                    value={formData.code || ''}
                    onChange={(e) => setFormData({ ...formData, code: e.target.value })}
                    style={{ width: '100%', padding: '0.45rem', borderRadius: '6px', border: '1px solid var(--border-color)', backgroundColor: 'var(--bg-primary)', color: 'var(--text-primary)' }}
                  />
                </div>
              )}

              {/* Email field for owners and users */}
              {['owners', 'users'].includes(selectedEntity) && (
                <div>
                  <label style={{ display: 'block', fontSize: '0.8125rem', color: 'var(--text-secondary)', marginBottom: '0.25rem' }}>
                    Email Address
                  </label>
                  <input
                    type="email"
                    data-testid="modal-input-email"
                    required
                    value={formData.email || ''}
                    onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                    style={{ width: '100%', padding: '0.45rem', borderRadius: '6px', border: '1px solid var(--border-color)', backgroundColor: 'var(--bg-primary)', color: 'var(--text-primary)' }}
                  />
                </div>
              )}

              {/* User display name */}
              {selectedEntity === 'users' && (
                <div>
                  <label style={{ display: 'block', fontSize: '0.8125rem', color: 'var(--text-secondary)', marginBottom: '0.25rem' }}>
                    Display Name
                  </label>
                  <input
                    type="text"
                    data-testid="modal-input-display-name"
                    required
                    value={formData.display_name || ''}
                    onChange={(e) => setFormData({ ...formData, display_name: e.target.value })}
                    style={{ width: '100%', padding: '0.45rem', borderRadius: '6px', border: '1px solid var(--border-color)', backgroundColor: 'var(--bg-primary)', color: 'var(--text-primary)' }}
                  />
                </div>
              )}

              {/* Budgets amount */}
              {selectedEntity === 'budgets' && (
                <div>
                  <label style={{ display: 'block', fontSize: '0.8125rem', color: 'var(--text-secondary)', marginBottom: '0.25rem' }}>
                    Budget Allocated Ceiling Amount
                  </label>
                  <input
                    type="number"
                    step="0.01"
                    data-testid="modal-input-amount"
                    required
                    value={formData.amount || ''}
                    onChange={(e) => setFormData({ ...formData, amount: parseFloat(e.target.value) || 0 })}
                    style={{ width: '100%', padding: '0.45rem', borderRadius: '6px', border: '1px solid var(--border-color)', backgroundColor: 'var(--bg-primary)', color: 'var(--text-primary)' }}
                  />
                </div>
              )}

              {/* Policies rule type */}
              {selectedEntity === 'policies' && (
                <div>
                  <label style={{ display: 'block', fontSize: '0.8125rem', color: 'var(--text-secondary)', marginBottom: '0.25rem' }}>
                    Rule Type
                  </label>
                  <input
                    type="text"
                    data-testid="modal-input-rule-type"
                    required
                    value={formData.rule_type || 'TAG_REQUIRED'}
                    onChange={(e) => setFormData({ ...formData, rule_type: e.target.value })}
                    style={{ width: '100%', padding: '0.45rem', borderRadius: '6px', border: '1px solid var(--border-color)', backgroundColor: 'var(--bg-primary)', color: 'var(--text-primary)' }}
                  />
                </div>
              )}

              {/* Remediation Category */}
              {selectedEntity === 'remediation_tasks' && (
                <div>
                  <label style={{ display: 'block', fontSize: '0.8125rem', color: 'var(--text-secondary)', marginBottom: '0.25rem' }}>
                    Category
                  </label>
                  <input
                    type="text"
                    data-testid="modal-input-category"
                    required
                    value={formData.category || 'STORAGE_HYGIENE'}
                    onChange={(e) => setFormData({ ...formData, category: e.target.value })}
                    style={{ width: '100%', padding: '0.45rem', borderRadius: '6px', border: '1px solid var(--border-color)', backgroundColor: 'var(--bg-primary)', color: 'var(--text-primary)' }}
                  />
                </div>
              )}

              {/* Provisioning Target Scope */}
              {selectedEntity === 'provisioning_requests' && (
                <div>
                  <label style={{ display: 'block', fontSize: '0.8125rem', color: 'var(--text-secondary)', marginBottom: '0.25rem' }}>
                    Target Cloud Scope
                  </label>
                  <input
                    type="text"
                    data-testid="modal-input-target-scope"
                    required
                    value={formData.target_scope || 'AWS-GLOBAL-PROD'}
                    onChange={(e) => setFormData({ ...formData, target_scope: e.target.value })}
                    style={{ width: '100%', padding: '0.45rem', borderRadius: '6px', border: '1px solid var(--border-color)', backgroundColor: 'var(--bg-primary)', color: 'var(--text-primary)' }}
                  />
                </div>
              )}

              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.75rem', marginTop: '1rem' }}>
                <button
                  type="button"
                  onClick={() => setModalOpen(false)}
                  style={{
                    padding: '0.4rem 0.8rem',
                    borderRadius: '6px',
                    border: '1px solid var(--border-color)',
                    backgroundColor: 'transparent',
                    color: 'var(--text-secondary)',
                    cursor: 'pointer',
                  }}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  data-testid="modal-submit-btn"
                  style={{
                    padding: '0.4rem 1rem',
                    borderRadius: '6px',
                    border: 'none',
                    backgroundColor: '#0284c7',
                    color: '#ffffff',
                    cursor: 'pointer',
                    fontWeight: 600,
                  }}
                >
                  {editingObject ? 'Save Modifications' : 'Create Record'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
