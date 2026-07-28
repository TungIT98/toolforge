"""D1 binding shim — auto-converts pyodide JsProxy to native Python.

CF Python Workers runs Python on top of Pyodide. D1 prepared statement
results are returned as `pyodide.ffi.JsProxy` objects wrapping the
underlying JS D1 response. Direct iteration / `.get()` access from
Python raises:

    TypeError: 'pyodide.ffi.JsProxy' object is not iterable
    AttributeError: 'JsProxy' object has no attribute 'get'

This shim wraps the D1 binding so that `.first()` and `.all()` return
native Python dicts / lists, transparent to handler code. Existing
`db.prepare(sql).bind(*params).all() / .first()` chains work unchanged.

Wrapped at worker entry (`worker.py` → `on_fetch` / `on_scheduled`),
so every handler that reads `env.DB` gets the wrapped version.

The shim is also a no-op for tests: FakeD1 returns native dicts/lists
already, and `wrap_db` is idempotent (returns the same object if
already wrapped, or returns FakeD1 as-is because it has `.prepare()`).
"""
from __future__ import annotations

from typing import Any


def wrap_db(db: "object" | None) -> "object" | None:
    """Wrap a D1 binding so `.prepare()` returns auto-converting statements.

    - Returns None if db is None.
    - Returns the db unchanged if it's already wrapped.
    - Returns the db unchanged if it has no `.prepare()` method (defensive).
    - Otherwise returns a `_D1Wrapper` around the real D1 binding.

    Safe to call multiple times on the same db (idempotent).
    """
    if db is None:
        return None
    if isinstance(db, _D1Wrapper):
        return db
    if not hasattr(db, "prepare"):
        # Not a D1 binding (e.g. FakeD1 subclass? unlikely) — leave alone
        return db
    return _D1Wrapper(db)


class _D1Wrapper:
    """Wraps a D1 binding. `.prepare()` returns a `_WrappedStatement`."""

    __slots__ = ("_db",)

    def __init__(self, db):
        self._db = db

    def prepare(self, sql: str) -> "_WrappedStatement":
        return _WrappedStatement(self._db.prepare(sql))


class _WrappedStatement:
    """Wraps a D1 prepared statement. Auto-converts JsProxy results.

    Chainable: `.bind(*args)` returns self, like the real D1 statement.
    """

    __slots__ = ("_stmt",)

    def __init__(self, stmt):
        self._stmt = stmt

    def bind(self, *args) -> "_WrappedStatement":
        # D1's bind() returns a (possibly new) statement; update ref.
        self._stmt = self._stmt.bind(*args)
        return self

    async def first(self) -> dict[str, Any] | None:
        """Run the query and return the first row as a native dict (or None)."""
        result = await self._stmt.first()
        if result is None:
            return None
        return _to_python(result)

    async def all(self) -> list[dict[str, Any]]:
        """Run the query and return all rows as a list of native dicts."""
        result = await self._stmt.all()
        if result is None:
            return []
        # result is an iterable of rows; convert each
        return [_to_python(r) for r in result]

    async def run(self) -> dict[str, Any]:
        """Execute a write statement and return metadata as a native dict.

        D1's run() returns {meta, success, etc.}. JsProxy unwraps the same.
        """
        result = await self._stmt.run()
        if result is None:
            return {}
        return _to_python(result)


def _to_python(obj: Any) -> Any:
    """Convert a JsProxy (or native Python) object to native Python.

    Strategy:
    1. None / native primitive / dict / list → returned as-is (or recursed).
    2. JsProxy with `.to_py()` → call it.
    3. JsProxy with `.keys()` / indexable → build dict from keys.
    4. JsProxy iterable → recurse over items.
    5. Fallback: return obj unchanged (caller decides).
    """
    if obj is None:
        return None

    # Already a native Python primitive or container — done
    if isinstance(obj, (str, int, float, bool, bytes)):
        return obj
    if isinstance(obj, dict):
        # Recurse to handle nested JsProxy values
        return {k: _to_python(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_to_python(x) for x in obj]

    # Best path: pyodide's own to_py() conversion (deep, native)
    to_py = getattr(obj, "to_py", None)
    if callable(to_py):
        try:
            return to_py()
        except Exception:
            pass  # fall through to manual unwrap

    # Manual unwrap: JsProxy is indexable like a dict and has keys()
    keys = getattr(obj, "keys", None)
    if callable(keys):
        try:
            return {k: _to_python(obj[k]) for k in keys()}
        except Exception:
            pass

    # Manual unwrap: iterable
    if hasattr(obj, "__iter__") and not isinstance(obj, (str, bytes)):
        try:
            return [_to_python(x) for x in obj]
        except Exception:
            pass

    # Last resort: return as-is. Caller may have to handle.
    return obj
