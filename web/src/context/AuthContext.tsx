import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { apiFetch, apiClient } from '../api/client';

export interface UserSummary {
  id: string;
  email: string;
  display_name: string;
}

export interface TenantSummary {
  id: string;
  name: string;
}

export interface AuthContextType {
  user: UserSummary | null;
  roles: string[];
  capabilities: string[];
  tenants: TenantSummary[];
  currentTenant: TenantSummary | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  switchTenant: (tenantId: string) => Promise<void>;
  signOut: () => Promise<void>;
  hasCapability: (capability: string) => boolean;
  hasRole: (role: string) => boolean;
  refreshAuth: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<UserSummary | null>(null);
  const [roles, setRoles] = useState<string[]>([]);
  const [capabilities, setCapabilities] = useState<string[]>([]);
  const [tenants, setTenants] = useState<TenantSummary[]>([]);
  const [currentTenant, setCurrentTenant] = useState<TenantSummary | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);

  const fetchAuthContext = useCallback(async () => {
    try {
      const data = await apiFetch('/api/v1/auth/me');
      if (data && data.user) {
        setUser(data.user);
        setRoles(data.roles || []);
        setCapabilities(data.capabilities || []);
        setTenants(data.tenants || []);
        setCurrentTenant(data.current_tenant || null);
      } else {
        setUser(null);
        setRoles([]);
        setCapabilities([]);
        setTenants([]);
        setCurrentTenant(null);
      }
    } catch {
      setUser(null);
      setRoles([]);
      setCapabilities([]);
      setTenants([]);
      setCurrentTenant(null);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchAuthContext();
  }, [fetchAuthContext]);

  const switchTenant = async (tenantId: string) => {
    setIsLoading(true);
    try {
      await apiClient.post('/api/v1/auth/switch-tenant', { tenant_id: tenantId });
      await fetchAuthContext();
    } finally {
      setIsLoading(false);
    }
  };

  const signOut = async () => {
    setIsLoading(true);
    try {
      await apiClient.post('/api/v1/auth/logout', {});
    } catch {
      // Ignore logout errors
    } finally {
      setUser(null);
      setRoles([]);
      setCapabilities([]);
      setTenants([]);
      setCurrentTenant(null);
      setIsLoading(false);
      window.location.href = '/login';
    }
  };

  const hasCapability = useCallback(
    (cap: string) => {
      if (capabilities.includes('*')) return true;
      return capabilities.includes(cap);
    },
    [capabilities]
  );

  const hasRole = useCallback(
    (role: string) => {
      return roles.includes(role);
    },
    [roles]
  );

  const value: AuthContextType = {
    user,
    roles,
    capabilities,
    tenants,
    currentTenant,
    isAuthenticated: !!user,
    isLoading,
    switchTenant,
    signOut,
    hasCapability,
    hasRole,
    refreshAuth: fetchAuthContext,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};

export const useAuth = (): AuthContextType => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};
