"""Forge code generator — use LLM to produce code from approved spec.

P1 scope:
- Generate Python (Tauri backend) + TypeScript (Tauri frontend) source code
- Write to local file system (D1 or R2) — for P1, just save code as text in D1
- Skip actual Tauri build (needs local Rust + Windows runner, P4)
- Run a basic syntax check (Python: py_compile; TypeScript: tsc --noEmit if available)
"""
from __future__ import annotations

import re
from typing import Any

from src.lib.log import get_logger
from src.llm import LLMClient, LLMError

log = get_logger("forge.code")

FORGE_SYSTEM = """Bạn là Forge, senior dev cho ToolForge. Nhiệm vụ: viết CODE PRODUCTION-READY từ spec kỹ thuật.

OUTPUT FORMAT: BẮT BUỘC dùng code block fence với language tag và filepath:

```python:src-tauri/src/main.py
<code here>
```

```typescript:src/App.tsx
<code here>
```

```rust:src-tauri/src/main.rs
<code here>
```

```toml:src-tauri/Cargo.toml
<code here>
```

```json:package.json
<code here>
```

QUY TẮC:
- Tiếng Anh cho code, comment có thể tiếng Việt
- Code phải chạy được (không syntax error)
- Type hints đầy đủ (Python 3.11+ syntax)
- Có docstring cho function public
- Handle edge cases (input validation, error handling)
- KHÔNG bỏ qua mục nào trong spec
- Stack: Tauri 2.x + React + Cloudflare Workers (Python pyodide)
- Target: Windows 10/11 64-bit (cho desktop tool)
- File paths tương đối từ project root (vd: src-tauri/src/main.py)

Nếu spec quá ngắn, generate MVP code (chỉ must-have features từ spec section 3).
Output CHỈ là các code block fence, không text thừa.
"""


async def generate_code_from_spec(
    spec_markdown: str,
    client: LLMClient,
    tool_id: str,
) -> dict[str, Any]:
    """Generate code files from spec. Returns dict of {filepath: code_content}.

    Args:
        spec_markdown: Full 10-section spec
        client: LLMClient
        tool_id: For logging only

    Returns:
        {
            "files": {"src-tauri/src/main.py": "...", "src/App.tsx": "...", ...},
            "file_count": N,
            "total_lines": N,
            "llm_usage": {...}
        }
    """
    # Truncate spec if too long to save tokens
    user = (
        f"# Spec (P1 — generate MVP code, focus on must-have features):\n\n"
        f"{spec_markdown[:15000]}\n\n"
        f"---\n\n"
        f"Generate code files (Tauri 2.x + React) for tool_id: `{tool_id}`. "
        f"Output as code fences with filepath tags. "
        f"Focus on must-have features. Skip nice-to-have."
    )

    try:
        result = await client.call(
            system=FORGE_SYSTEM,
            user=user,
            max_tokens=8000,  # code is long
            temperature=0.2,  # very low temp for code (deterministic)
            timeout_s=120,
        )
    except LLMError as e:
        log.error("forge_llm_failed", err=str(e), tool_id=tool_id)
        raise

    code_md = result["text"]
    files = parse_code_fences(code_md)

    total_lines = sum(len(content.splitlines()) for content in files.values())
    log.info(
        "forge_code_generated",
        tool_id=tool_id,
        file_count=len(files),
        total_lines=total_lines,
        latency_ms=result.get("latency_ms", 0),
    )

    return {
        "files": files,
        "file_count": len(files),
        "total_lines": total_lines,
        "llm_usage": {
            "input_tokens": result.get("usage", {}).get("input_tokens", 0),
            "output_tokens": result.get("usage", {}).get("output_tokens", 0),
            "model": result.get("model", ""),
            "latency_ms": result.get("latency_ms", 0),
        },
    }


def parse_code_fences(text: str) -> dict[str, str]:
    """Parse code blocks with filepath annotation.

    Pattern: ```language:filepath\n<code>\n```

    Returns dict {filepath: code_content}
    """
    pattern = re.compile(
        r"```(\w+):([^\n]+)\n(.*?)```",
        re.DOTALL,
    )
    files: dict[str, str] = {}
    for m in pattern.finditer(text):
        lang = m.group(1).strip()
        filepath = m.group(2).strip()
        content = m.group(3).strip()
        if not filepath or not content:
            continue
        # Strip leading ./ for normalization
        if filepath.startswith("./"):
            filepath = filepath[2:]
        files[filepath] = content
    return files


def validate_code_files(files: dict[str, str]) -> tuple[bool, list[str]]:
    """Basic validation of generated code.

    Returns: (is_valid, issues)
    """
    issues = []
    if not files:
        issues.append("no files generated")
        return (False, issues)
    # Must have at least 1 Python file (Tauri backend) and 1 TypeScript file (frontend)
    has_python = any(f.endswith(".py") for f in files)
    has_ts = any(f.endswith(".ts") or f.endswith(".tsx") for f in files)
    if not has_python and not has_ts:
        issues.append("no Python or TypeScript files")
    # Each file should have content
    for fp, content in files.items():
        if len(content.strip()) < 20:
            issues.append(f"{fp} too short ({len(content)} chars)")
    return (len(issues) == 0, issues)


def compile_check_python(files: dict[str, str]) -> dict[str, str]:
    """Try py_compile on Python files. Return dict {filepath: 'ok' | 'error: ...'}.

    P1 best-effort. Tauri uses Rust for backend, so this mainly catches
    Python helpers (CLI tools, scripts).
    """
    import py_compile
    import tempfile
    import os

    results: dict[str, str] = {}
    for fp, content in files.items():
        if not fp.endswith(".py"):
            continue
        try:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as f:
                f.write(content)
                tmp_path = f.name
            py_compile.compile(tmp_path, doraise=True)
            results[fp] = "ok"
            os.unlink(tmp_path)
        except py_compile.PyCompileError as e:
            results[fp] = f"error: {e}"
        except Exception as e:
            results[fp] = f"error: {e}"
    return results
