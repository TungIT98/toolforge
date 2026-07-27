import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { getTool, Tool } from "../api";

export default function ToolDetail() {
  const { id } = useParams<{ id: string }>();
  const [tool, setTool] = useState<Tool | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!id) return;
    setLoading(true);
    getTool(id)
      .then((r) => setTool(r.tool))
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }, [id]);

  function formatVnd(n: number) {
    if (n === 0) return "Miễn phí";
    return n.toLocaleString("vi-VN") + " VNĐ";
  }

  if (loading) return <div className="center">Đang tải...</div>;
  if (error) return <div className="center"><div className="error">⚠️ Lỗi: {error}</div></div>;
  if (!tool) return <div className="center">Tool không tồn tại. <Link to="/">← Về trang chủ</Link></div>;

  const tags = tool.tags ? tool.tags.split(",") : [];

  return (
    <div className="container detail-page">
      <p style={{ fontSize: 13, marginBottom: 8 }}>
        <Link to="/">← Trang chủ</Link>
      </p>
      <h1>{tool.name}</h1>
      <div className="detail-meta">
        <span className={"price" + (tool.pricing_vnd === 0 ? " free" : "")}>
          {formatVnd(tool.pricing_vnd)}
        </span>
        <span className="niche" style={{ background: "var(--bg-soft)", padding: "4px 12px", borderRadius: 12, fontSize: 12 }}>
          {tool.niche}
        </span>
        {tool.license_required === 1 && (
          <span style={{ color: "var(--ink-faint)", fontSize: 14 }}>🔐 Yêu cầu license</span>
        )}
      </div>
      <div className="detail-actions">
        {tool.binary_url && (
          <a href={tool.binary_url} target="_blank" rel="noopener noreferrer">
            <button>Tải xuống</button>
          </a>
        )}
        <a href="https://t.me/toolforge_support" target="_blank" rel="noopener noreferrer">
          <button style={{ background: "#0088cc" }}>Liên hệ Telegram</button>
        </a>
      </div>
      <p className="detail-desc">{tool.description}</p>
      {tags.length > 0 && (
        <div className="tags" style={{ margin: "24px 0" }}>
          {tags.map((t) => (
            <span key={t} className="tag" style={{ fontSize: 13, padding: "4px 10px" }}>#{t.trim()}</span>
          ))}
        </div>
      )}

      {tool.latest_build && (
        <div className="detail-build">
          <h3>📦 Phiên bản mới nhất</h3>
          <div className="kv"><span className="k">Version</span><span>{tool.latest_build.version}</span></div>
          <div className="kv"><span className="k">Test result</span><span>{tool.latest_build.test_result}</span></div>
          <div className="kv"><span className="k">Built at</span><span>{tool.latest_build.created_at}</span></div>
        </div>
      )}

      <div className="detail-build" style={{ marginTop: 16 }}>
        <h3>📊 Thông tin</h3>
        <div className="kv"><span className="k">Tool ID</span><span><code>{tool.id}</code></span></div>
        <div className="kv"><span className="k">Active licenses</span><span>{tool.active_license_count ?? 0}</span></div>
        <div className="kv"><span className="k">Created</span><span>{tool.created_at}</span></div>
        <div className="kv"><span className="k">Updated</span><span>{tool.updated_at}</span></div>
      </div>
    </div>
  );
}
