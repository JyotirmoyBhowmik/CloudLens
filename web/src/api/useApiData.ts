/**
 * Universal Data Hook for CloudLens Web (Prompt P10 Item 2).
 * 
 * Enforces:
 * - Direct typed client API calls without hardcoded fallback records.
 * - Loading, Error (with retry), and Empty (with action) states.
 * - Automatic query string serialization and error handling.
 */

import { useState, useEffect, useCallback } from 'react';
import { apiFetch } from './client';

export interface UseApiDataOptions<T> {
  initialData?: T | null;
  params?: Record<string, string | number | boolean | undefined | null>;
  enabled?: boolean;
}

export interface UseApiDataResult<T> {
  data: T | null;
  loading: boolean;
  error: Error | null;
  errorMessage: string | null;
  refetch: () => Promise<void>;
  isEmpty: boolean;
  setData: React.Dispatch<React.SetStateAction<T | null>>;
}

export function useApiData<T = any>(
  endpoint: string,
  options: UseApiDataOptions<T> = {}
): UseApiDataResult<T> {
  const { initialData = null, params, enabled = true } = options;
  const [data, setData] = useState<T | null>(initialData);
  const [loading, setLoading] = useState<boolean>(enabled);
  const [error, setError] = useState<Error | null>(null);

  const fetchData = useCallback(async () => {
    if (!enabled) return;
    setLoading(true);
    setError(null);
    try {
      let url = endpoint;
      if (params) {
        const query = new URLSearchParams();
        Object.entries(params).forEach(([k, v]) => {
          if (v !== undefined && v !== null) {
            query.append(k, String(v));
          }
        });
        const qs = query.toString();
        if (qs) {
          url += (url.includes('?') ? '&' : '?') + qs;
        }
      }
      const result = await apiFetch<T>(url);
      setData(result);
    } catch (err: any) {
      console.error(`API fetch error for ${endpoint}:`, err);
      setError(err instanceof Error ? err : new Error(String(err?.message || err)));
    } finally {
      setLoading(false);
    }
  }, [endpoint, JSON.stringify(params), enabled]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const isEmpty =
    !data ||
    (Array.isArray(data) && data.length === 0) ||
    (typeof data === 'object' && 'items' in (data as any) && Array.isArray((data as any).items) && (data as any).items.length === 0) ||
    (typeof data === 'object' && 'nodes' in (data as any) && Array.isArray((data as any).nodes) && (data as any).nodes.length === 0) ||
    (typeof data === 'object' && 'total' in (data as any) && (data as any).total === 0);

  return {
    data,
    loading,
    error,
    errorMessage: error?.message || null,
    refetch: fetchData,
    isEmpty,
    setData,
  };
}
