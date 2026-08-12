const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000';
const API_KEY = import.meta.env.VITE_API_KEY || '';

export function apiFetch(path, options = {}) {
  const headers = new Headers(options.headers);
  if (API_KEY) headers.set('X-API-Key', API_KEY);
  return fetch(`${API_BASE}${path}`, { ...options, headers });
}

export function wsUrl(path) {
  const url = new URL(path, API_BASE);
  url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
  if (API_KEY) url.searchParams.set('api_key', API_KEY);
  return url.toString();
}
