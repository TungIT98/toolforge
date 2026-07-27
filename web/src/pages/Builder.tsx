import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";

const API_BASE = (import.meta.env.VITE_API_BASE as string) || "";

interface Message {
  role: "user" | "assistant";
  content: string;
  ts?: string;
}

interface ChatResponse {
  ok: boolean;
  session_id: string;
  assistant_message: string;
  status: "chatting" | "ready_to_build" | "building" | "done" | "failed";
  tool_name?: string;
  spec?: any;
  spec_markdown?: string;
  messages_count?: number;
}

interface BuildResponse {
  ok: boolean;
  job_id: string;
  tool_name: string;
  file_count: number;
  total_lines: number;
  test_result: string;
  files: Record<string, string>;
  files_preview: Record<string, string>;
}

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
  });
  if (!resp.ok) {
    const body = await resp.text();
    throw new Error(`API ${resp.status}: ${body}`);
  }
  return (await resp.json()) as T;
}

export default function Builder() {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [status, setStatus] = useState<"chatting" | "ready_to_build" | "building" | "done" | "failed">("chatting");
  const [toolName, setToolName] = useState<string | null>(null);
  const [buildResult, setBuildResult] = useState<BuildResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedFile, setSelectedFile] = useState<string | null>(null);
  const chatEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  async function startSession() {
    try {
      setLoading(true);
      setError(null);
      const r = await api<{ ok: boolean; session_id: string }>("/api/builder/session", { method: "POST", body: JSON.stringify({}) });
      setSessionId(r.session_id);
    } catch (e: any) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }

  async function sendMessage() {
    if (!input.trim() || !sessionId || loading) return;
    const userMsg: Message = { role: "user", content: input };
    setMessages((m) => [...m, userMsg]);
    setInput("");
    setLoading(true);
    setError(null);
    try {
      const r = await api<ChatResponse>(`/api/builder/session/${sessionId}/message`, {
        method: "POST",
        body: JSON.stringify({ message: userMsg.content }),
      });
      setMessages((m) => [...m, { role: "assistant", content: r.assistant_message }]);
      setStatus(r.status);
      if (r.tool_name) setToolName(r.tool_name);
    } catch (e: any) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }

  async function triggerBuild() {
    if (!sessionId || loading) return;
    setLoading(true);
    setError(null);
    setStatus("building");
    try {
      const r = await api<BuildResponse>(`/api/builder/session/${sessionId}/build`, {
        method: "POST",
        body: JSON.stringify({}),
      });
      setBuildResult(r);
      setStatus("done");
      setSelectedFile(Object.keys(r.files)[0] || null);
    } catch (e: any) {
      setError(String(e));
      setStatus("failed");
    } finally {
      setLoading(false);
    }
  }

  function reset() {
    setSessionId(null);
    setMessages([]);
    setStatus("chatting");
    setToolName(null);
    setBuildResult(null);
    setSelectedFile(null);
    setError(null);
  }

  function downloadFile(filepath: string) {
    if (!buildResult) return;
    const content = buildResult.files[filepath] || "";
    const blob = new Blob([content], { type: "text/plain" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filepath.split("/").pop() || "file";
    a.click();
    URL.revokeObjectURL(url);
  }

  function downloadAllAsZip() {
    // Simple: download each file individually. (P5: real ZIP)
    if (!buildResult) return;
    Object.keys(buildResult.files).forEach((fp, i) => {
      setTimeout(() => downloadFile(fp), i * 100);
    });
  }

  // Initial state: no session
  if (!sessionId) {
    return (
      <div className="container" style={{ maxWidth: 700, padding: "60px 20px" }}>
        <h1>🛠️ ToolForge Builder</h1>
        <p style={{ color: "var(--ink-soft)", fontSize: 18 }}>
          Mô tả tool bạn cần — AI sẽ hỏi thêm và build code cho bạn trong vài phút.
        </p>
        <div className="detail-build" style={{ marginTop: 24 }}>
          <h3>💡 Ví dụ:</h3>
          <ul style={{ paddingLeft: 20, color: "var(--ink-soft)" }}>
            <li>"Tôi cần tool download video TikTok từ URL, lưu thành MP4"</li>
            <li>"App gửi email hàng loạt từ danh sách CSV, có tracking open rate"</li>
            <li>"Script convert ảnh HEIC sang JPG, batch từ folder"</li>
            <li>"Crawler lấy giá sản phẩm từ shopee, lưu Excel mỗi ngày"</li>
          </ul>
        </div>
        <button
          onClick={startSession}
          disabled={loading}
          style={{ marginTop: 24, padding: "12px 24px", fontSize: 16 }}
        >
          {loading ? "Đang tạo..." : "🚀 Bắt đầu"}
        </button>
        {error && <div className="error" style={{ marginTop: 16 }}>⚠️ {error}</div>}
        <p style={{ marginTop: 24 }}>
          <Link to="/">← Về trang chủ</Link>
        </p>
      </div>
    );
  }

  // Chat / build view
  return (
    <div className="container" style={{ maxWidth: 900, padding: "32px 20px" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
        <h1>🛠️ ToolForge Builder {toolName && <span style={{ fontSize: 18, color: "var(--ink-soft)" }}>· {toolName}</span>}</h1>
        <button onClick={reset} style={{ background: "#666", fontSize: 12 }}>Bắt đầu lại</button>
      </div>

      <div style={{ background: "var(--bg-soft)", borderRadius: "var(--radius)", padding: 16, marginBottom: 16 }}>
        <div style={{ fontSize: 13, color: "var(--ink-soft)" }}>
          Session: <code style={{ fontSize: 12 }}>{sessionId}</code> · Status: <b style={{ color: status === "ready_to_build" ? "var(--success)" : status === "failed" ? "var(--primary)" : "var(--ink)" }}>{status}</b>
        </div>
      </div>

      {/* Chat messages */}
      <div style={{ maxHeight: 400, overflowY: "auto", border: "1px solid var(--border)", borderRadius: "var(--radius)", padding: 16, marginBottom: 16, background: "white" }}>
        {messages.length === 0 && (
          <div style={{ color: "var(--ink-faint)", textAlign: "center", padding: 20 }}>
            Chat trống. Bắt đầu mô tả tool bạn cần!
          </div>
        )}
        {messages.map((m, i) => (
          <div
            key={i}
            style={{
              marginBottom: 12,
              padding: 12,
              borderRadius: "var(--radius)",
              background: m.role === "user" ? "#e3f2fd" : "#f5f5f5",
              marginLeft: m.role === "user" ? 40 : 0,
              marginRight: m.role === "assistant" ? 40 : 0,
            }}
          >
            <div style={{ fontSize: 12, color: "var(--ink-soft)", marginBottom: 4 }}>
              {m.role === "user" ? "👤 Bạn" : "🤖 Builder AI"}
            </div>
            <div style={{ whiteSpace: "pre-wrap" }}>{m.content}</div>
          </div>
        ))}
        <div ref={chatEndRef} />
      </div>

      {/* Input */}
      {status === "chatting" && (
        <div style={{ display: "flex", gap: 8, marginBottom: 16 }}>
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && sendMessage()}
            placeholder="Mô tả tool bạn cần hoặc trả lời câu hỏi của AI..."
            disabled={loading}
            style={{ flex: 1 }}
          />
          <button onClick={sendMessage} disabled={loading || !input.trim()}>
            {loading ? "..." : "Gửi"}
          </button>
        </div>
      )}

      {error && <div className="error">⚠️ {error}</div>}

      {/* Ready to build */}
      {status === "ready_to_build" && (
        <div className="detail-build" style={{ background: "#e8f5e9", borderColor: "var(--success)" }}>
          <h3>✅ AI đã có đủ thông tin!</h3>
          <p>Spec kỹ thuật đã sẵn sàng. Click nút dưới để AI generate code.</p>
          <button onClick={triggerBuild} disabled={loading} style={{ background: "var(--success)" }}>
            {loading ? "Đang build code..." : "🔨 Build code ngay"}
          </button>
        </div>
      )}

      {status === "building" && (
        <div className="detail-build" style={{ textAlign: "center" }}>
          <p>⏳ AI đang generate code, đợi 10-30s...</p>
        </div>
      )}

      {/* Build result */}
      {buildResult && (
        <div>
          <h2 style={{ marginTop: 32 }}>📦 Code đã sẵn sàng!</h2>
          <div className="stats-bar">
            <div className="stat"><div className="v">{buildResult.file_count}</div><div className="l">Files</div></div>
            <div className="stat"><div className="v">{buildResult.total_lines}</div><div className="l">Lines</div></div>
            <div className="stat"><div className="v" style={{ color: buildResult.test_result === "pass" ? "var(--success)" : "var(--amber)" }}>{buildResult.test_result}</div><div className="l">Test</div></div>
          </div>

          <div style={{ display: "flex", gap: 8, margin: "16px 0", flexWrap: "wrap" }}>
            <button onClick={downloadAllAsZip} style={{ background: "var(--success)" }}>
              ⬇ Tải tất cả file
            </button>
            {Object.keys(buildResult.files).map((fp) => (
              <button key={fp} onClick={() => downloadFile(fp)} style={{ background: "var(--ink-soft)", fontSize: 12 }}>
                📄 {fp}
              </button>
            ))}
          </div>

          {selectedFile && buildResult.files[selectedFile] && (
            <div className="detail-build" style={{ marginTop: 16 }}>
              <h3>📄 {selectedFile}</h3>
              <pre style={{
                background: "#1a1a1a",
                color: "#e0e0e0",
                padding: 16,
                borderRadius: 4,
                overflow: "auto",
                fontSize: 12,
                fontFamily: "monospace",
                maxHeight: 500,
                margin: 0,
              }}>
                {buildResult.files[selectedFile]}
              </pre>
              <button
                onClick={() => navigator.clipboard.writeText(buildResult.files[selectedFile])}
                style={{ marginTop: 8, fontSize: 12, background: "var(--ink-soft)" }}
              >
                📋 Copy
              </button>
              <span style={{ marginLeft: 12, fontSize: 13, color: "var(--ink-soft)" }}>
                Click file name ở trên để xem file khác
              </span>
            </div>
          )}
        </div>
      )}

      <p style={{ marginTop: 32, fontSize: 13, color: "var(--ink-faint)" }}>
        💡 Tip: Có thể nói "Build đi" hoặc "OK đủ rồi" để ép AI generate spec.
        Hoặc trả lời thêm câu hỏi của AI.
      </p>
    </div>
  );
}
