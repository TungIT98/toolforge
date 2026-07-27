/**
 * API client for ToolForge Worker backend.
 *
 * In dev: Vite proxy /api/* to local Worker (wrangler dev on 8787).
 * In prod: Worker URL is set via VITE_API_BASE env var, or use relative path
 *          when Pages and Worker share the same domain.
 */

const API_BASE = (import.meta.env.VITE_API_BASE as string) || "";

export interface Tool {
  id: string;
  name: string;
  description: string;
  niche: string;
  status: string;
  pricing_vnd: number;
  binary_url: string;
  license_required: number;
  tags: string;
  created_at: string;
  updated_at: string;
  latest_build?: any;
  active_license_count?: number;
}

export interface CatalogStats {
  total_tools: number;
  by_niche: Record<string, number>;
  by_status: Record<string, number>;
  free_tools: number;
  paid_tools: number;
  total_active_licenses: number;
  estimated_total_revenue_vnd: number;
}

async function http<T>(path: string, init?: RequestInit): Promise<T> {
  const url = `${API_BASE}${path}`;
  const resp = await fetch(url, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers || {}),
    },
  });
  if (!resp.ok) {
    const body = await resp.text();
    throw new Error(`API ${resp.status}: ${body}`);
  }
  return (await resp.json()) as T;
}

export async function getTools(params: {
  niche?: string;
  status?: string;
  q?: string;
  limit?: number;
} = {}): Promise<{ ok: boolean; count: number; tools: Tool[] }> {
  const search = new URLSearchParams();
  if (params.niche) search.set("niche", params.niche);
  if (params.status) search.set("status", params.status);
  if (params.q) search.set("q", params.q);
  if (params.limit) search.set("limit", String(params.limit));
  const qs = search.toString();
  return http(`/api/store/tools${qs ? "?" + qs : ""}`);
}

export async function getTool(id: string): Promise<{ ok: boolean; tool: Tool }> {
  return http(`/api/store/tools/${id}`);
}

export async function getStats(): Promise<{ ok: boolean; stats: CatalogStats }> {
  return http("/api/store/stats");
}

export async function getHealth(): Promise<{ ok: boolean; status: string }> {
  return http("/api/health");
}
