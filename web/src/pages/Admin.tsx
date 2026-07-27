import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

const API_BASE = (import.meta.env.VITE_API_BASE as string) || "";
const ADMIN_KEY_STORAGE = "toolforge_admin_key";

interface Overview {
  tools: { total: number; by_niche: Record<string, number>; by_status: Record<string, number>; live_count: number; draft_count: number };
  orders: { total: number; pending_count: number; paid_count: number; failed_count: number; refunded_count: number; total_revenue_vnd: number };
  licenses: { total: number; active_count: number; revoked_count: number; expired_count: number };
  pipeline: { pending_specs: number; pending_handoffs: number; in_progress_builds: number; done_builds: number };
  scout: { briefs_count: number; latest_brief_date: string | null };
  llm: { total_calls: number; total_tokens: number };
}

interface Order {
  id: string; tool_id: string; tool_name: string; customer_email: string; amount_vnd: number;
  status: string; paid_at: string; created_at: string; license_key: string;
}

interface License {
  key: string; tool_id: string; status: string; customer_email: string; activated_at: string; expires_at: string;
}

interface PendingSpec {
  id: string; tool_id: string; status: string; effort_estimate_hours: number; created_at: string;
}

function formatVnd(n: number) {
  return n.toLocaleString("vi-VN") + " VNĐ";
}

async function adminFetch<T>(path: string, key: string): Promise<T> {
  const resp = await fetch(`${API_BASE}${path}`, {
    headers: { "X-Admin-Key": key, "Content-Type": "application/json" },
  });
  if (!resp.ok) {
    const body = await resp.text();
    throw new Error(`API ${resp.status}: ${body}`);
  }
  return (await resp.json()) as T;
}

type Tab = "overview" | "orders" | "licenses" | "specs" | "briefs" | "builds";

export default function Admin() {
  const [key, setKey] = useState(localStorage.getItem(ADMIN_KEY_STORAGE) || "");
  const [keyInput, setKeyInput] = useState("");
  const [tab, setTab] = useState<Tab>("overview");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const [overview, setOverview] = useState<Overview | null>(null);
  const [orders, setOrders] = useState<Order[]>([]);
  const [licenses, setLicenses] = useState<License[]>([]);
  const [specs, setSpecs] = useState<PendingSpec[]>([]);
  const [briefs, setBriefs] = useState<any[]>([]);
  const [builds, setBuilds] = useState<any[]>([]);

  useEffect(() => {
    if (!key) return;
    setLoading(true);
    setError(null);
    const fetchAll = async () => {
      try {
        if (tab === "overview") {
          const r = await adminFetch<{ ok: boolean; overview: Overview }>("/api/admin/overview", key);
          setOverview(r.overview);
        } else if (tab === "orders") {
          const r = await adminFetch<{ ok: boolean; orders: Order[] }>("/api/admin/orders", key);
          setOrders(r.orders || []);
        } else if (tab === "licenses") {
          const r = await adminFetch<{ ok: boolean; licenses: License[] }>("/api/admin/licenses", key);
          setLicenses(r.licenses || []);
        } else if (tab === "specs") {
          const r = await adminFetch<{ ok: boolean; specs: PendingSpec[] }>("/api/admin/pending-specs", key);
          setSpecs(r.specs || []);
        } else if (tab === "briefs") {
          const r = await adminFetch<{ ok: boolean; briefs: any[] }>("/api/admin/briefs", key);
          setBriefs(r.briefs || []);
        } else if (tab === "builds") {
          const r = await adminFetch<{ ok: boolean; builds: any[] }>("/api/admin/builds", key);
          setBuilds(r.builds || []);
        }
      } catch (e: any) {
        setError(String(e));
        if (String(e).includes("401")) {
          localStorage.removeItem(ADMIN_KEY_STORAGE);
          setKey("");
        }
      } finally {
        setLoading(false);
      }
    };
    fetchAll();
  }, [tab, key]);

  function onLogin() {
    if (keyInput) {
      localStorage.setItem(ADMIN_KEY_STORAGE, keyInput);
      setKey(keyInput);
    }
  }

  function onLogout() {
    localStorage.removeItem(ADMIN_KEY_STORAGE);
    setKey("");
    setOverview(null);
    setOrders([]);
  }

  if (!key) {
    return (
      <div className="container" style={{ maxWidth: 500, padding: "60px 20px" }}>
        <h2>🔐 Admin Login</h2>
        <p style={{ color: "var(--ink-soft)" }}>
          Nhập ADMIN_API_KEY để truy cập dashboard. Key được set qua{" "}
          <code>wrangler secret put ADMIN_API_KEY</code>.
        </p>
        <div style={{ display: "flex", gap: 8, marginTop: 20 }}>
          <input
            type="password"
            placeholder="ADMIN_API_KEY"
            value={keyInput}
            onChange={(e) => setKeyInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && onLogin()}
          />
          <button onClick={onLogin}>Đăng nhập</button>
        </div>
        {error && <div className="error" style={{ marginTop: 16 }}>{error}</div>}
        <p style={{ marginTop: 20 }}>
          <Link to="/">← Về trang chủ</Link>
        </p>
      </div>
    );
  }

  return (
    <div className="container" style={{ padding: "32px 20px" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 24 }}>
        <h1>🛠️ Admin Dashboard</h1>
        <button onClick={onLogout} style={{ background: "#666" }}>Đăng xuất</button>
      </div>

      <div style={{ display: "flex", gap: 8, marginBottom: 24, borderBottom: "1px solid var(--border)", flexWrap: "wrap" }}>
        {(["overview", "orders", "licenses", "specs", "briefs", "builds"] as Tab[]).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            style={{
              background: tab === t ? "var(--primary)" : "transparent",
              color: tab === t ? "white" : "var(--ink)",
              borderRadius: 0,
              padding: "10px 20px",
              textTransform: "capitalize",
            }}
          >
            {t === "overview" ? "📊 Tổng quan" :
             t === "orders" ? "💰 Orders" :
             t === "licenses" ? "🔐 Licenses" :
             t === "specs" ? "📋 Specs pending" :
             t === "briefs" ? "🔭 Briefs" : "🛠️ Builds"}
          </button>
        ))}
      </div>

      {error && <div className="error">⚠️ {error}</div>}
      {loading && <div className="center">Đang tải...</div>}

      {tab === "overview" && overview && (
        <div>
          <div className="stats-bar">
            <div className="stat"><div className="v">{overview.tools.total}</div><div className="l">Tools</div></div>
            <div className="stat"><div className="v">{overview.tools.live_count}</div><div className="l">Live</div></div>
            <div className="stat"><div className="v">{overview.orders.total}</div><div className="l">Orders</div></div>
            <div className="stat"><div className="v">{overview.orders.paid_count}</div><div className="l">Paid</div></div>
            <div className="stat"><div className="v">{formatVnd(overview.orders.total_revenue_vnd)}</div><div className="l">Revenue</div></div>
            <div className="stat"><div className="v">{overview.licenses.active_count}</div><div className="l">Active licenses</div></div>
          </div>

          <h3 style={{ marginTop: 32 }}>🔭 Scout</h3>
          <p>Briefs: {overview.scout.briefs_count} · Latest: {overview.scout.latest_brief_date || "—"}</p>

          <h3 style={{ marginTop: 24 }}>⚙️ Pipeline</h3>
          <p>
            Pending specs: {overview.pipeline.pending_specs} ·
            Pending handoffs: {overview.pipeline.pending_handoffs} ·
            In-progress builds: {overview.pipeline.in_progress_builds} ·
            Done builds: {overview.pipeline.done_builds}
          </p>

          <h3 style={{ marginTop: 24 }}>🤖 LLM usage</h3>
          <p>Total calls: {overview.llm.total_calls} · Total tokens: {overview.llm.total_tokens.toLocaleString()}</p>

          <h3 style={{ marginTop: 24 }}>📦 Tools by niche</h3>
          <ul>
            {Object.entries(overview.tools.by_niche).map(([k, v]) => (
              <li key={k}>{k}: <b>{v}</b></li>
            ))}
          </ul>
        </div>
      )}

      {tab === "orders" && (
        <div>
          <p>Tổng: {orders.length} orders</p>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 14 }}>
            <thead>
              <tr style={{ background: "var(--bg-soft)", textAlign: "left" }}>
                <th style={{ padding: 8 }}>Order ID</th>
                <th>Tool</th>
                <th>Customer</th>
                <th>Amount</th>
                <th>Status</th>
                <th>License</th>
                <th>Created</th>
              </tr>
            </thead>
            <tbody>
              {orders.map((o) => (
                <tr key={o.id} style={{ borderBottom: "1px solid var(--border)" }}>
                  <td style={{ padding: 8, fontFamily: "monospace", fontSize: 12 }}>{o.id}</td>
                  <td>{o.tool_name || o.tool_id}</td>
                  <td>{o.customer_email || "—"}</td>
                  <td>{formatVnd(o.amount_vnd)}</td>
                  <td><span style={{ color: o.status === "paid" ? "var(--success)" : o.status === "pending" ? "var(--amber)" : "var(--ink-faint)" }}>{o.status}</span></td>
                  <td style={{ fontFamily: "monospace", fontSize: 11 }}>{o.license_key || "—"}</td>
                  <td style={{ fontSize: 12 }}>{o.created_at?.slice(0, 10)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {tab === "licenses" && (
        <div>
          <p>Tổng: {licenses.length} licenses</p>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 14 }}>
            <thead>
              <tr style={{ background: "var(--bg-soft)", textAlign: "left" }}>
                <th style={{ padding: 8 }}>Key</th>
                <th>Tool</th>
                <th>Customer</th>
                <th>Status</th>
                <th>Activated</th>
                <th>Expires</th>
              </tr>
            </thead>
            <tbody>
              {licenses.map((l) => (
                <tr key={l.key} style={{ borderBottom: "1px solid var(--border)" }}>
                  <td style={{ padding: 8, fontFamily: "monospace", fontSize: 12 }}>{l.key}</td>
                  <td>{l.tool_id}</td>
                  <td>{l.customer_email || "—"}</td>
                  <td>{l.status}</td>
                  <td style={{ fontSize: 12 }}>{l.activated_at?.slice(0, 10) || "—"}</td>
                  <td style={{ fontSize: 12 }}>{l.expires_at?.slice(0, 10) || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {tab === "specs" && (
        <div>
          <p>Pending: {specs.length} specs cần duyệt</p>
          {specs.length === 0 && <p style={{ color: "var(--ink-faint)" }}>Không có spec nào pending. Đợi Scout → Architect chạy.</p>}
          {specs.map((s) => (
            <div key={s.id} className="detail-build" style={{ marginBottom: 12 }}>
              <h3>{s.tool_id}</h3>
              <div className="kv"><span className="k">Spec ID</span><span><code>{s.id}</code></span></div>
              <div className="kv"><span className="k">Effort estimate</span><span>{s.effort_estimate_hours || "?"} giờ</span></div>
              <div className="kv"><span className="k">Created</span><span>{s.created_at?.slice(0, 16)}</span></div>
              <div style={{ marginTop: 12, display: "flex", gap: 8 }}>
                <a href={`${API_BASE}/api/architect/get?id=${s.id}`} target="_blank" rel="noopener noreferrer">
                  <button style={{ background: "var(--ink-soft)" }}>Xem spec</button>
                </a>
                <a href={`${API_BASE}/api/architect/approve`} target="_blank" rel="noopener noreferrer">
                  <button>Approve (POST)</button>
                </a>
              </div>
            </div>
          ))}
        </div>
      )}

      {tab === "briefs" && (
        <div>
          <p>{briefs.length} briefs</p>
          {briefs.map((b) => (
            <div key={b.id} className="detail-build" style={{ marginBottom: 12 }}>
              <div className="kv"><span className="k">Date</span><span>{b.scout_date}</span></div>
              <div className="kv"><span className="k">Avg severity</span><span>{b.severity_avg || "?"}/10</span></div>
              <div className="kv"><span className="k">Sources scanned</span><span>{b.source_count}</span></div>
              <div className="kv"><span className="k">Created</span><span>{b.created_at?.slice(0, 16)}</span></div>
            </div>
          ))}
        </div>
      )}

      {tab === "builds" && (
        <div>
          <p>{builds.length} builds</p>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 14 }}>
            <thead>
              <tr style={{ background: "var(--bg-soft)", textAlign: "left" }}>
                <th style={{ padding: 8 }}>Build ID</th>
                <th>Tool</th>
                <th>Version</th>
                <th>Test result</th>
                <th>Size</th>
                <th>Created</th>
              </tr>
            </thead>
            <tbody>
              {builds.map((b) => (
                <tr key={b.id} style={{ borderBottom: "1px solid var(--border)" }}>
                  <td style={{ padding: 8, fontFamily: "monospace", fontSize: 12 }}>{b.id}</td>
                  <td>{b.tool_id}</td>
                  <td>{b.version}</td>
                  <td><span style={{ color: b.test_result === "pass" ? "var(--success)" : "var(--ink-faint)" }}>{b.test_result}</span></td>
                  <td>{b.size_bytes ? `${(b.size_bytes / 1024).toFixed(1)} KB` : "—"}</td>
                  <td style={{ fontSize: 12 }}>{b.created_at?.slice(0, 16)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
