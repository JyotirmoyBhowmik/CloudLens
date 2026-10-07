/**
 * Unified CloudLens API Client (Prompt P02 Item 3).
 *
 * Enforces:
 * 1. Automatic credentials: 'include' for HttpOnly BFF session cookies.
 * 2. Automatic X-CSRF-Token header injection for mutating requests (POST, PUT, PATCH, DELETE).
 * 3. Transparent 401 handling -> triggers re-authentication / redirect to /login.
 * 4. Transparent 403 handling -> triggers redirection to /403 Forbidden page.
 */

function getCsrfToken(): string | null {
  if (typeof document === 'undefined') return null;
  const match = document.cookie.match(/(^|;)\s*cloudlens_csrf_token\s*=\s*([^;]+)/);
  return match ? decodeURIComponent(match[2]) : null;
}

export class ApiError extends Error {
  status: number;
  data: any;

  constructor(message: string, status: number, data?: any) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.data = data;
  }
}

export async function apiFetch<T = any>(input: RequestInfo | URL, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers || {});

  // Add CSRF token for mutating requests
  const method = (init.method || 'GET').toUpperCase();
  if (['POST', 'PUT', 'PATCH', 'DELETE'].includes(method)) {
    const csrf = getCsrfToken();
    if (csrf && !headers.has('X-CSRF-Token')) {
      headers.set('X-CSRF-Token', csrf);
    }
  }

  // Ensure JSON content type if body is object and header not set
  if (init.body && typeof init.body === 'string' && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json');
  }

  const response = await fetch(input, {
    ...init,
    headers,
    credentials: init.credentials || 'include',
  });

  if (response.status === 401) {
    const currentPath = typeof window !== 'undefined' ? window.location.pathname : '';
    const urlStr = typeof input === 'string' ? input : input.toString();
    if (!currentPath.startsWith('/login') && !urlStr.includes('/auth/me')) {
      if (typeof window !== 'undefined') {
        window.location.href = '/login';
      }
    }
    throw new ApiError('Unauthorized: 401', 401);
  }

  if (response.status === 403) {
    const currentPath = typeof window !== 'undefined' ? window.location.pathname : '';
    if (currentPath !== '/403') {
      if (typeof window !== 'undefined') {
        window.location.href = '/403';
      }
    }
    throw new ApiError('Forbidden: 403', 403);
  }

  if (!response.ok) {
    let errData: any = null;
    try {
      errData = await response.json();
    } catch {
      // non-json response body
    }
    throw new ApiError(errData?.detail || `HTTP error ${response.status}`, response.status, errData);
  }

  const contentType = response.headers.get('content-type');
  if (contentType && contentType.includes('application/json')) {
    return response.json();
  }
  return response.text() as any;
}

export const apiClient = {
  get: <T = any>(url: string, init?: RequestInit) => apiFetch<T>(url, { ...init, method: 'GET' }),
  post: <T = any>(url: string, body?: any, init?: RequestInit) =>
    apiFetch<T>(url, {
      ...init,
      method: 'POST',
      body: body !== undefined ? (typeof body === 'string' ? body : JSON.stringify(body)) : undefined,
    }),
  put: <T = any>(url: string, body?: any, init?: RequestInit) =>
    apiFetch<T>(url, {
      ...init,
      method: 'PUT',
      body: body !== undefined ? (typeof body === 'string' ? body : JSON.stringify(body)) : undefined,
    }),
  patch: <T = any>(url: string, body?: any, init?: RequestInit) =>
    apiFetch<T>(url, {
      ...init,
      method: 'PATCH',
      body: body !== undefined ? (typeof body === 'string' ? body : JSON.stringify(body)) : undefined,
    }),
  delete: <T = any>(url: string, init?: RequestInit) => apiFetch<T>(url, { ...init, method: 'DELETE' }),
};
