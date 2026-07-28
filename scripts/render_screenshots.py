"""Render the showcase + agents pages to PNG screenshots for the README.

Uses Playwright + headless Chromium. Runs locally — no Worker deploy needed.

Usage:
    python scripts/render_screenshots.py

Outputs:
    docs/screenshots/showcase.png  — /showcase dark UI demo
    docs/screenshots/agents.png    — /agents roster page
"""
from pathlib import Path
import sys

# Add repo root to path so we can import the SHOWCASE_HTML constant
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src.handlers.showcase import SHOWCASE_HTML  # noqa: E402
from src.handlers.agents import AGENTS_HTML  # noqa: E402

OUT_DIR = REPO_ROOT / "docs" / "screenshots"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def render(html: str, out_path: Path, width: int = 1280, height: int = 900) -> None:
    """Render an HTML string to a PNG via headless Chromium."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": width, "height": height})
        page = context.new_page()
        page.set_content(html, wait_until="networkidle")
        # Wait an extra beat for fonts + any inline scripts to settle
        page.wait_for_timeout(500)
        page.screenshot(path=str(out_path), full_page=True)
        browser.close()
    print(f"  -> {out_path.relative_to(REPO_ROOT)}")


def main() -> None:
    print(f"Rendering screenshots to {OUT_DIR.relative_to(REPO_ROOT)}/")

    # 1. /showcase — the headline demo
    print("Rendering /showcase ...")
    render(SHOWCASE_HTML, OUT_DIR / "showcase.png", width=1280, height=900)

    # 2. /agents — the roster page
    print("Rendering /agents ...")
    render(AGENTS_HTML, OUT_DIR / "agents.png", width=1280, height=1100)

    print("Done.")


if __name__ == "__main__":
    main()
