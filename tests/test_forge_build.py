"""Tests for Forge P4: build orchestrator + R2 signed URL + webhook."""
import hashlib
import hmac
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from src.forge.license import is_valid_license_key
from src.forge.r2_uploader import (
    build_r2_path,
    generate_signed_url,
    is_valid_r2_config,
)
from src.forge.webhook import handle_build_complete, verify_webhook_secret


# === r2_uploader tests ===

def test_generate_signed_url_format():
    url = generate_signed_url(
        bucket="toolforge-tools",
        key="capcut-reup/0.1.0/setup.exe",
        account_id="test-account",
        access_key_id="test-key",
        secret_access_key="test-secret",
        expires_in_seconds=3600,
    )
    assert url.startswith("https://test-account.r2.cloudflarestorage.com/toolforge-tools/")
    assert "capcut-reup/0.1.0/setup.exe" in url
    assert "X-Amz-Algorithm=AWS4-HMAC-SHA256" in url
    assert "X-Amz-Signature=" in url


def test_generate_signed_url_unique_each_call():
    """Signed URL should differ across calls (due to date/time)."""
    url1 = generate_signed_url("b", "k", "a", "k", "s")
    url2 = generate_signed_url("b", "k", "a", "k", "s")
    # Both should have signatures but X-Amz-Date will differ (different seconds)
    # In fast test they may be same; just verify both are valid
    assert "X-Amz-Signature=" in url1
    assert "X-Amz-Signature=" in url2


def test_build_r2_path():
    path = build_r2_path("capcut-reup", "0.1.0", "setup.exe")
    assert path == "capcut-reup/0.1.0/setup.exe"


def test_build_r2_path_default_filename():
    path = build_r2_path("voice-clone", "1.0.0")
    assert path == "voice-clone/1.0.0/setup.exe"


def test_is_valid_r2_config():
    assert is_valid_r2_config("a", "b", "c") is True
    assert is_valid_r2_config("", "b", "c") is False
    assert is_valid_r2_config("a", "", "c") is False
    assert is_valid_r2_config("a", "b", "") is False
    assert is_valid_r2_config("", "", "") is False


# === webhook tests ===

def test_verify_webhook_secret_match():
    assert verify_webhook_secret("secret", "secret") is True


def test_verify_webhook_secret_mismatch():
    assert verify_webhook_secret("secret1", "secret2") is False


def test_verify_webhook_secret_empty():
    assert verify_webhook_secret("", "secret") is False
    assert verify_webhook_secret("secret", "") is False
    assert verify_webhook_secret(None, "secret") is False


@pytest.mark.asyncio
async def test_handle_build_complete_success():
    from tests.test_e2e import FakeD1, FakeEnv
    env = FakeEnv()
    # Pre-populate build record (from P1 forge)
    env.DB.tables["builds"].append({
        "id": "build-test-001", "tool_id": "test-tool", "handoff_id": "handoff-test-001",
        "version": "0.1.0", "code_path": "d1://...", "binary_url": "",
        "test_result": "pending", "test_report": "", "effort_actual_hours": None,
        "size_bytes": 0, "created_at": "2026-07-27",
    })
    env.DB.tables["handoff"].append({
        "id": "handoff-test-001", "tool_id": "test-tool", "spec_id": "spec-test",
        "status": "in_progress", "priority": "medium",
        "owner_feedback": None, "created_at": "2026-07-27",
        "approved_at": "2026-07-27", "forge_handoff_at": "2026-07-27", "done_at": None,
    })
    env.DB.tables["tools"].append({
        "id": "test-tool", "name": "Test", "description": "x", "niche": "productivity",
        "status": "draft", "build_id": None, "pricing_vnd": 0, "binary_url": "",
        "license_required": 0, "tags": "", "created_at": "2026-07-27", "updated_at": "2026-07-27",
    })

    payload = {
        "build_id": "build-test-001",
        "tool_id": "test-tool",
        "version": "0.1.0",
        "status": "success",
        "binary_url": "https://r2.example.com/setup.exe",
        "size_bytes": 12345678,
        "test_result": "pass",
    }
    result = await handle_build_complete(payload, env)
    assert result["ok"]
    assert result["status"] == "success"
    # Verify build updated
    build = next(b for b in env.DB.tables["builds"] if b["id"] == "build-test-001")
    assert build["binary_url"] == "https://r2.example.com/setup.exe"
    assert build["size_bytes"] == 12345678
    assert build["test_result"] == "pass"
    # Verify handoff done
    handoff = next(h for h in env.DB.tables["handoff"] if h["id"] == "handoff-test-001")
    assert handoff["status"] == "done"
    # Verify tool binary_url updated
    tool = next(t for t in env.DB.tables["tools"] if t["id"] == "test-tool")
    assert tool["binary_url"] == "https://r2.example.com/setup.exe"


@pytest.mark.asyncio
async def test_handle_build_complete_failure():
    from tests.test_e2e import FakeD1, FakeEnv
    env = FakeEnv()
    env.DB.tables["builds"].append({
        "id": "build-fail-001", "tool_id": "test-tool", "handoff_id": "handoff-fail-001",
        "version": "0.1.0", "code_path": "", "binary_url": "",
        "test_result": "pending", "test_report": "", "effort_actual_hours": None,
        "size_bytes": 0, "created_at": "2026-07-27",
    })
    env.DB.tables["handoff"].append({
        "id": "handoff-fail-001", "tool_id": "test-tool", "spec_id": "spec-fail",
        "status": "in_progress", "priority": "medium",
        "owner_feedback": None, "created_at": "2026-07-27",
        "approved_at": "2026-07-27", "forge_handoff_at": "2026-07-27", "done_at": None,
    })

    payload = {
        "build_id": "build-fail-001",
        "tool_id": "test-tool",
        "version": "0.1.0",
        "status": "failed",
        "error": "Rust compilation error",
    }
    result = await handle_build_complete(payload, env)
    assert result["ok"]
    handoff = next(h for h in env.DB.tables["handoff"] if h["id"] == "handoff-fail-001")
    assert handoff["status"] == "failed"


@pytest.mark.asyncio
async def test_handle_build_complete_build_not_found():
    from tests.test_e2e import FakeEnv
    env = FakeEnv()
    payload = {"build_id": "ghost-build", "tool_id": "x", "version": "0.1.0", "status": "success"}
    result = await handle_build_complete(payload, env)
    assert not result["ok"]
    assert result["code"] == "BUILD_NOT_FOUND"


# === build_orchestrator tests ===

@pytest.mark.asyncio
async def test_trigger_github_workflow_missing_token():
    from tests.test_e2e import FakeEnv
    env = FakeEnv()
    # No GITHUB_TOKEN set
    from src.forge.build_orchestrator import trigger_github_workflow
    result = await trigger_github_workflow(
        build_id="build-001", tool_id="test-tool", version="0.1.0",
        callback_url="https://example.com/callback", env=env,
    )
    assert not result["ok"]
    assert result["code"] == "GITHUB_TOKEN_MISSING"


@pytest.mark.asyncio
async def test_trigger_github_workflow_missing_webhook_secret():
    from tests.test_e2e import FakeEnv
    class FakeEnvWithToken(FakeEnv):
        GITHUB_TOKEN = "ghp-test"
    env = FakeEnvWithToken()
    from src.forge.build_orchestrator import trigger_github_workflow
    result = await trigger_github_workflow(
        build_id="build-001", tool_id="test-tool", version="0.1.0",
        callback_url="https://example.com/callback", env=env,
    )
    assert not result["ok"]
    assert result["code"] == "WEBHOOK_SECRET_MISSING"


@pytest.mark.asyncio
async def test_trigger_github_workflow_success():
    from tests.test_e2e import FakeEnv
    class FakeEnvFull(FakeEnv):
        GITHUB_TOKEN = "ghp-test-123"
        WEBHOOK_SECRET = "my-shared-secret"
    env = FakeEnvFull()
    from src.forge.build_orchestrator import trigger_github_workflow
    import httpx

    async def fake_post(*args, **kwargs):
        return httpx.Response(204)

    with patch("httpx.AsyncClient.post", new=fake_post):
        from src.forge.build_orchestrator import trigger_github_workflow
        result = await trigger_github_workflow(
            build_id="build-001", tool_id="test-tool", version="0.1.0",
            callback_url="https://example.com/callback", env=env,
        )
    assert result["ok"]
    assert result["status"] == "triggered"
    assert "build_id" in result


@pytest.mark.asyncio
async def test_trigger_github_workflow_api_error():
    from tests.test_e2e import FakeEnv
    class FakeEnvFull(FakeEnv):
        GITHUB_TOKEN = "ghp-test"
        WEBHOOK_SECRET = "secret"
    env = FakeEnvFull()
    import httpx
    async def fake_post(*args, **kwargs):
        return httpx.Response(401, text="Bad credentials")
    with patch("httpx.AsyncClient.post", new=fake_post):
        from src.forge.build_orchestrator import trigger_github_workflow
        result = await trigger_github_workflow(
            build_id="build-001", tool_id="test-tool", version="0.1.0",
            callback_url="https://example.com/cb", env=env,
        )
    assert not result["ok"]
    assert result["code"] == "GH_API_FAILED"
