"""Builder Tool code generator — turn spec into code files.

Reuses pattern from src/forge/code_generator.py with simpler prompt
appropriate for user-facing tool (typically simpler than Owner Brain tools).
"""
from __future__ import annotations

import json
import re
from typing import Any

from src.forge.code_generator import parse_code_fences, validate_code_files
from src.lib.log import get_logger
from src.llm import LLMClient, LLMError

log = get_logger("builder.generator")

GENERATOR_SYSTEM = """Bạn là ToolForge Code Generator. Nhiệm vụ: viết CODE PRODUCTION-READY từ spec user cung cấp.

QUY TẮC BẮT BUỘC:
- Output dùng code fence với language:filepath, ví dụ: ```python:main.py
- Code phải chạy được (Python 3.11+ syntax)
- Type hints + docstring cho function public
- Error handling đầy đủ (try/except, input validation)
- Không dùng thư viện obscure — chỉ stdlib + 1-2 thư viện phổ biến (requests, typer, rich, opencv-python, pydub, etc.)
- File structure đơn giản: 1-3 file Python (main + helper nếu cần), 1 requirements.txt
- Tên file thường: main.py, utils.py, README.md, requirements.txt

Platform hint:
- "windows" / "desktop" → Tauri (skip) hoặc Python + tkinter
- "web" → Python Flask + HTML
- "cli" → Python + typer
- "mac" → Python + tkinter

Mặc định: nếu không rõ → Python CLI (typer) cho MVP. User có thể nâng cấp sau.

Output CHỈ là các code block fence, không text thừa. Có thể có 2-4 file.
"""


async def generate_code_from_spec(
    spec_markdown: str,
    client: LLMClient,
    tool_name: str = "Tool",
) -> dict[str, Any]:
    """Generate code from user-facing spec.

    Returns: {
        files: {filepath: content},
        file_count,
        total_lines,
        llm_usage
    }
    """
    user = (
        f"# Spec từ user (ToolForge Builder):\n\n{spec_markdown[:12000]}\n\n"
        f"---\n\n"
        f"Tool name: `{tool_name}`. "
        f"Generate code Python production-ready. Ưu tiên đơn giản, dễ chạy, MVP. "
        f"Output dạng code block fence với language:filepath. "
        f"Recommend CLI (typer) hoặc Web (Flask) cho MVP."
    )

    try:
        result = await client.call(
            system=GENERATOR_SYSTEM,
            user=user,
            max_tokens=6000,
            temperature=0.2,
            timeout_s=120,
        )
    except LLMError as e:
        log.error("generator_llm_failed", err=str(e))
        raise

    files = parse_code_fences(result["text"])
    total_lines = sum(len(c.splitlines()) for c in files.values())
    log.info("generator_done", tool=tool_name, files=len(files), lines=total_lines)

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
