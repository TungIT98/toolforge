"""Store seed data — mock tool catalog for first-time setup.

Based on 1Touch Pro catalog (https://aff.1touch.pro) — adapted to ToolForge
naming. Use this to seed D1 on first deploy via POST /api/store/seed.

In production, owner can edit/replace via admin dashboard (P2.4) or
auto-crawl from 1Touch (P2.1c).
"""
from __future__ import annotations

# Each tool: id, name, description, niche, pricing_vnd, license_required, tags
SEED_TOOLS: list[dict] = [
    {
        "id": "capcut-desktop-reup",
        "name": "Capcut Desktop - Reup Phim China Cho Máy Cấu Hình Yếu",
        "description": (
            "Bạn đang làm MMO, xây kênh TikTok, YouTube Reels, hay chuyên dịch thuật phim/video (Subbing)? "
            "ToolForge Capcut Reup giúp bạn tự động tải video từ Douyin/TikTok Trung Quốc, "
            "edit watermark, chèn sub tiếng Việt, render MP4 chất lượng cao — tất cả trong 1 click. "
            "Tối ưu cho máy cấu hình yếu (4GB RAM, không cần GPU)."
        ),
        "niche": "mmo_reup",
        "pricing_vnd": 1_000_000,
        "license_required": 1,
        "tags": ["capcut", "reup", "tiktok", "douyin", "video", "mmo"],
        "binary_url": "https://github.com/TungIT98/toolforge/releases/download/capcut-reup-v0.1.0/capcut-reup-setup.exe",
    },
    {
        "id": "voice-clone-desktop",
        "name": "Voice Clone Desktop - Công cụ Clone Giọng Nói Offline",
        "description": (
            "Giải pháp clone giọng nói offline chuyên nghiệp, tối ưu chi phí & bảo mật tuyệt đối "
            "cho Content Creator Việt. Hỗ trợ tiếng Việt tốt (Bắc/Trung/Nam), "
            "clone từ 30s mẫu, render trong 1 phút. Không gửi data lên cloud."
        ),
        "niche": "content_creator",
        "pricing_vnd": 1_000_000,
        "license_required": 1,
        "tags": ["voice", "tts", "clone", "offline", "vietnamese"],
        "binary_url": "https://github.com/TungIT98/toolforge/releases/download/voice-clone-v0.1.0/voice-clone-setup.exe",
    },
    {
        "id": "storyclone-writer",
        "name": "StoryClone - Viết Tiểu Thuyết & Truyện Dài Bằng AI",
        "description": (
            "Tác giả, nhà sáng tạo nội dung, publisher muốn sản xuất hàng loạt truyện "
            "dài (kiếm hiệp, ngôn tình, đô thị) — StoryClone giúp bạn generate chương "
            "5000-15000 từ trong 2 phút, nhất quán nhân vật, đa dạng bối cảnh."
        ),
        "niche": "content_creator",
        "pricing_vnd": 1_000_000,
        "license_required": 1,
        "tags": ["ai", "writing", "novel", "story", "content"],
        "binary_url": "https://github.com/TungIT98/toolforge/releases/download/storyclone-v0.1.0/storyclone-setup.exe",
    },
    {
        "id": "flow-captcha-veo3",
        "name": "Flow Captcha Premium - Giải Captcha Cho Veo3",
        "description": (
            "Content Creator làm video ngắn (TikTok, YouTube Shorts, Reels), "
            "nhà thiết kế quảng cáo — tool giải captcha tự động giúp bạn bypass "
            "Google reCAPTCHA, hCaptcha khi dùng Veo3, Sora, các AI gen khác. "
            "Tốc độ 0.8-2s/captcha, độ chính xác 95%+."
        ),
        "niche": "productivity",
        "pricing_vnd": 800_000,
        "license_required": 1,
        "tags": ["captcha", "automation", "veo3", "ai"],
        "binary_url": "https://github.com/TungIT98/toolforge/releases/download/flow-captcha-v0.1.0/flow-captcha-setup.exe",
    },
    {
        "id": "cloudflare-manager-pro",
        "name": "Cloudflare Manager Pro 2.0 - Quản Lý DNS & Zero Trust",
        "description": (
            "Ứng dụng desktop quản lý Cloudflare DNS & Zero Trust Tunnel — gọn, nhanh, "
            "dùng ngay trên Windows. Thêm/sửa/xóa DNS record, quản lý tunnel, "
            "xem analytics real-time. Phù hợp dev + admin quản nhiều domain."
        ),
        "niche": "productivity",
        "pricing_vnd": 0,  # Free
        "license_required": 0,
        "tags": ["cloudflare", "dns", "tunnel", "devops", "free"],
        "binary_url": "https://github.com/TungIT98/toolforge/releases/download/cf-manager-v0.1.0/cf-manager-setup.exe",
    },
    {
        "id": "1touchdrive-pro",
        "name": "1TouchDrive Pro - Sao Chép Google Drive Hàng Loạt",
        "description": (
            "Bạn thường xuyên cần sao chép dữ liệu giữa các thư mục Google Drive? "
            "1TouchDrive Pro giúp tự động copy/sync hàng nghìn file, giữ nguyên structure, "
            "hỗ trợ scheduled sync. Tiết kiệm 5-10 giờ/tuần cho team marketing, agency."
        ),
        "niche": "productivity",
        "pricing_vnd": 200_000,
        "license_required": 1,
        "tags": ["gdrive", "google-drive", "sync", "backup", "productivity"],
        "binary_url": "https://github.com/TungIT98/toolforge/releases/download/1touchdrive-v0.1.0/1touchdrive-setup.exe",
    },
    {
        "id": "antidetect-browser",
        "name": "1Touch Browse Antidetect - Quản Lý Nhiều Profile Trình Duyệt",
        "description": (
            "Bạn cần quản lý nhiều tài khoản trên cùng một máy tính mà vẫn đảm bảo dữ liệu "
            "trình duyệt được tách biệt? Antidetect browser giúp tạo profile riêng cho mỗi "
            "account, fingerprint khác nhau, cookie isolated."
        ),
        "niche": "mmo_reup",
        "pricing_vnd": 0,  # Free
        "license_required": 0,
        "tags": ["antidetect", "browser", "multi-account", "free", "mmo"],
        "binary_url": "https://github.com/TungIT98/toolforge/releases/download/antidetect-v0.1.0/antidetect-setup.exe",
    },
]


async def seed_to_d1(db: "object") -> dict:
    """Insert seed tools into D1. Idempotent (uses INSERT OR REPLACE).

    Args:
        db: D1 binding (env.DB)

    Returns:
        dict with inserted/skipped counts
    """
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()

    inserted = 0
    skipped = 0
    for tool in SEED_TOOLS:
        try:
            # Check if already exists
            existing = await db.prepare(
                "SELECT id FROM tools WHERE id = ?"
            ).bind(tool["id"]).first()
            if existing:
                skipped += 1
                continue
            await db.prepare(
                """INSERT INTO tools
                   (id, name, description, niche, status, pricing_vnd, binary_url,
                    license_required, tags, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"""
            ).bind(
                tool["id"],
                tool["name"],
                tool["description"],
                tool["niche"],
                "live",  # mark as live for seed data
                tool["pricing_vnd"],
                tool["binary_url"],
                tool["license_required"],
                ",".join(tool["tags"]),
                now,
                now,
            ).run()
            inserted += 1
        except Exception:
            skipped += 1
    return {"inserted": inserted, "skipped": skipped, "total": len(SEED_TOOLS)}
