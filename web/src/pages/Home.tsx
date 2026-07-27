import { useEffect, useState } from "react";
import { useSearchParams, Link } from "react-router-dom";
import { getTools, getStats, Tool, CatalogStats } from "../api";

export default function Home() {
  const [searchParams, setSearchParams] = useSearchParams();
  const niche = searchParams.get("niche") || "";
  const q = searchParams.get("q") || "";
  const [search, setSearch] = useState(q);

  const [tools, setTools] = useState<Tool[]>([]);
  const [stats, setStats] = useState<CatalogStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    Promise.all([
      getTools({ niche: niche || undefined, q: q || undefined, limit: 100 }),
      getStats().catch(() => ({ ok: false, stats: null })),
    ])
      .then(([toolsResp, statsResp]) => {
        setTools(toolsResp.tools || []);
        if (statsResp.ok) setStats(statsResp.stats);
      })
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }, [niche, q]);

  function onSearch(e: React.FormEvent) {
    e.preventDefault();
    const next = new URLSearchParams(searchParams);
    if (search) next.set("q", search);
    else next.delete("q");
    setSearchParams(next);
  }

  function onNicheChange(value: string) {
    const next = new URLSearchParams(searchParams);
    if (value) next.set("niche", value);
    else next.delete("niche");
    setSearchParams(next);
  }

  function formatVnd(n: number) {
    if (n === 0) return "Miễn phí";
    return n.toLocaleString("vi-VN") + " VNĐ";
  }

  function nicheLabel(n: string) {
    switch (n) {
      case "mmo_reup": return "MMO Reup";
      case "content_creator": return "Content Creator";
      case "productivity": return "Productivity";
      default: return n;
    }
  }

  return (
    <>
      <section className="hero">
        <div className="container">
          <h1>ToolForge — Kho tool <em>MMO/Creator</em> Việt</h1>
          <p>Phần mềm & công cụ số cho người làm MMO reup, content creator Việt Nam. Mua nhanh, nhận ngay, hỗ trợ rõ ràng.</p>
          <form className="hero-search" onSubmit={onSearch}>
            <input
              type="search"
              placeholder="Tìm kiếm tool... (vd: capcut, voice, content)"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
            <button type="submit">Tìm</button>
          </form>
        </div>
      </section>

      <section className="section">
        <div className="container">
          {stats && (
            <div className="stats-bar">
              <div className="stat">
                <div className="v">{stats.total_tools}</div>
                <div className="l">Tổng tool</div>
              </div>
              <div className="stat">
                <div className="v">{stats.paid_tools}</div>
                <div className="l">Có phí</div>
              </div>
              <div className="stat">
                <div className="v">{stats.free_tools}</div>
                <div className="l">Miễn phí</div>
              </div>
              <div className="stat">
                <div className="v">{stats.total_active_licenses}</div>
                <div className="l">License đang dùng</div>
              </div>
            </div>
          )}

          <div className="filters">
            <select value={niche} onChange={(e) => onNicheChange(e.target.value)}>
              <option value="">Tất cả niche</option>
              <option value="mmo_reup">MMO Reup</option>
              <option value="content_creator">Content Creator</option>
              <option value="productivity">Productivity</option>
            </select>
            <div className="filter-count">
              {loading ? "Đang tải..." : `${tools.length} tool`}
            </div>
          </div>

          {error && <div className="error">⚠️ Lỗi: {error}</div>}

          {!loading && !error && tools.length === 0 && (
            <div className="center">
              <p>Chưa có tool nào trong catalog.</p>
              <p style={{ fontSize: 14 }}>
                Admin: chạy <code>POST /api/store/seed</code> trên Worker backend để seed 7 tool mẫu.
              </p>
            </div>
          )}

          <div className="product-grid">
            {tools.map((tool) => {
              const tags = tool.tags ? tool.tags.split(",") : [];
              return (
                <Link
                  key={tool.id}
                  to={`/tools/${tool.id}`}
                  className="product-card"
                >
                  <span className="niche">{nicheLabel(tool.niche)}</span>
                  <h3>{tool.name}</h3>
                  <p className="desc">{tool.description.slice(0, 160)}{tool.description.length > 160 ? "..." : ""}</p>
                  {tags.length > 0 && (
                    <div className="tags">
                      {tags.slice(0, 4).map((t) => (
                        <span key={t} className="tag">#{t.trim()}</span>
                      ))}
                    </div>
                  )}
                  <div className="meta">
                    <span className={"price" + (tool.pricing_vnd === 0 ? " free" : "")}>
                      {formatVnd(tool.pricing_vnd)}
                    </span>
                    <span style={{ fontSize: 12, color: "var(--ink-faint)" }}>
                      {tool.license_required ? "🔐 Cần license" : "🔓 Free"}
                    </span>
                  </div>
                </Link>
              );
            })}
          </div>
        </div>
      </section>
    </>
  );
}
