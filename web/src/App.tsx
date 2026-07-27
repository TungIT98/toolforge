import { Routes, Route, Link } from "react-router-dom";
import Home from "./pages/Home";
import ToolDetail from "./pages/ToolDetail";
import Admin from "./pages/Admin";

export default function App() {
  return (
    <>
      <header className="site-header">
        <div className="container">
          <Link to="/" className="brand">Tool<span>Forge</span></Link>
          <nav className="nav-links">
            <Link to="/?niche=mmo_reup">MMO Reup</Link>
            <Link to="/?niche=content_creator">Content Creator</Link>
            <Link to="/?niche=productivity">Productivity</Link>
            <Link to="/admin">Admin</Link>
          </nav>
        </div>
      </header>
      <main>
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/tools/:id" element={<ToolDetail />} />
          <Route path="/admin" element={<Admin />} />
        </Routes>
      </main>
      <footer className="site-footer">
        <div className="container">
          <p>ToolForge 🛠️ — Kho tool MMO/Creator Việt Nam · © 2026</p>
          <p style={{ fontSize: 12, marginTop: 8 }}>
            Mua nhanh · Nhận ngay · Hỗ trợ qua Facebook/Telegram
          </p>
        </div>
      </footer>
    </>
  );
}
