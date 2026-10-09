export const API = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000';
export type Entity = { id: string; kind: string; version: number; status: string; payload: Record<string, any>; created_at: string; is_current?: boolean };
export type Clip = Entity & { mappings: any[]; mapping_revision: number; dependencies: any[]; selection: any | null; take_count: number };
export type Provider = { llm: string; image: string; h3: string; h3_message: string };

export async function request<T = any>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API}/api${path}`, {
    ...options,
    headers: { ...(options.body instanceof FormData ? {} : { 'Content-Type': 'application/json' }), ...options.headers },
    cache: 'no-store',
  });
  if (!response.ok) {
    let payload: any;
    try { payload = await response.json(); } catch { payload = null; }
    const detail = payload?.detail;
    throw new Error(typeof detail === 'string' ? detail : detail?.message || `请求失败 (${response.status})`);
  }
  return response.json();
}
export const get = <T = any>(path: string) => request<T>(path);
export const post = <T = any>(path: string, value: any = {}) => request<T>(path, { method: 'POST', body: JSON.stringify(value) });
export const patch = <T = any>(path: string, value: any) => request<T>(path, { method: 'PATCH', body: JSON.stringify(value) });
export const remove = <T = any>(path: string) => request<T>(path, { method: 'DELETE' });
