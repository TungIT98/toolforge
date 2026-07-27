"""Tests for Forge code generator + license + capcut reup seed (mocked LLM)."""
import json
import textwrap
from unittest.mock import AsyncMock, patch

import pytest

from src.forge.code_generator import (
    compile_check_python,
    generate_code_from_spec,
    parse_code_fences,
    validate_code_files,
)
from src.forge.license import generate_license_key, is_valid_license_key
from src.llm import LLMClient


SAMPLE_CODE_RESPONSE = textwrap.dedent("""\
    Here's the code:

    ```python:src-tauri/src/main.py
    def hello():
        print("Hello from ToolForge")
    ```

    ```typescript:src/App.tsx
    export default function App() {
        return <div>Hello</div>;
    }
    ```

    ```toml:src-tauri/Cargo.toml
    [package]
    name = "capcut-reup"
    version = "0.1.0"
    ```
    """)


# === parse_code_fences tests ===

def test_parse_code_fences_extracts_files():
    files = parse_code_fences(SAMPLE_CODE_RESPONSE)
    assert len(files) == 3
    assert "src-tauri/src/main.py" in files
    assert "src/App.tsx" in files
    assert "src-tauri/Cargo.toml" in files
    assert "hello()" in files["src-tauri/src/main.py"]


def test_parse_code_fences_strips_leading_dot_slash():
    text = "```python:./main.py\nx = 1\n```"
    files = parse_code_fences(text)
    assert "main.py" in files
    assert "./main.py" not in files


def test_parse_code_fences_empty_input():
    assert parse_code_fences("") == {}
    assert parse_code_fences("No code blocks here") == {}


def test_parse_code_fences_skips_empty_content():
    text = "```python:main.py\n\n```"
    files = parse_code_fences(text)
    # Empty content → skipped
    assert files == {}


# === validate_code_files tests ===

def test_validate_code_files_valid():
    files = {
        "main.py": "x = 1\n" * 20,
        "App.tsx": "export const x = 1;\n" * 20,
    }
    is_valid, issues = validate_code_files(files)
    assert is_valid
    assert issues == []


def test_validate_code_files_empty():
    is_valid, issues = validate_code_files({})
    assert not is_valid
    assert "no files generated" in issues


def test_validate_code_files_no_python_or_ts():
    files = {"config.toml": "x = 1"}
    is_valid, issues = validate_code_files(files)
    assert not is_valid
    assert any("no Python" in i for i in issues)


def test_validate_code_files_too_short():
    files = {"main.py": "x=1"}  # < 20 chars
    is_valid, issues = validate_code_files(files)
    assert not is_valid
    assert any("too short" in i for i in issues)


# === compile_check_python tests ===

def test_compile_check_python_valid():
    files = {"main.py": "def hello():\n    print('hi')\n"}
    result = compile_check_python(files)
    assert result["main.py"] == "ok"


def test_compile_check_python_syntax_error():
    files = {"bad.py": "def hello(:\n    print('hi')\n"}  # syntax error
    result = compile_check_python(files)
    assert "error" in result["bad.py"]


def test_compile_check_python_skips_non_py():
    files = {"main.py": "x=1", "App.tsx": "x=1"}
    result = compile_check_python(files)
    assert "main.py" in result
    assert "App.tsx" not in result


# === generate_code_from_spec test ===

@pytest.mark.asyncio
async def test_generate_code_from_spec():
    """LLM returns code blocks → parsed correctly."""
    fake_response = {
        "text": SAMPLE_CODE_RESPONSE,
        "usage": {"input_tokens": 1000, "output_tokens": 500},
        "model": "minimax/MiniMax-M3",
        "latency_ms": 8000,
    }

    with patch.object(LLMClient, "call", new=AsyncMock(return_value=fake_response)):
        client = LLMClient(api_key="test", agent_name="test")
        result = await generate_code_from_spec("spec text", client, "capcut-reup")

    assert result["file_count"] == 3
    assert result["total_lines"] > 0
    assert "src-tauri/src/main.py" in result["files"]


# === license tests ===

def test_generate_license_key_format():
    key = generate_license_key()
    parts = key.split("-")
    assert len(parts) == 4
    for p in parts:
        assert len(p) == 4
        # All hex chars
        int(p, 16)


def test_generate_license_key_unique():
    keys = {generate_license_key() for _ in range(100)}
    assert len(keys) == 100  # all unique


def test_is_valid_license_key_valid():
    assert is_valid_license_key("ABCD-1234-EF56-7890")
    assert is_valid_license_key("0000-0000-0000-0000")
    assert is_valid_license_key("FFFF-AAAA-5555-0001")


def test_is_valid_license_key_invalid():
    assert not is_valid_license_key("invalid")
    assert not is_valid_license_key("ABCD-1234-EF56")  # too few groups
    assert not is_valid_license_key("ABCD-1234-EF56-78901")  # too long
    assert not is_valid_license_key("ZZZZ-1234-EF56-7890")  # non-hex
    assert not is_valid_license_key("")
    assert not is_valid_license_key(None)
    assert not is_valid_license_key(123)
