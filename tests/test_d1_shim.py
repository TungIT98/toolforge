"""Tests for src/lib/d1.py shim.

Verifies that wrap_db correctly converts pyodide JsProxy-like objects
into native Python dicts/lists. We don't need real Pyodide; we mock
JsProxy behavior with classes that mimic the relevant surface.

Also verifies that the shim is transparent for FakeD1 (no behavior
change, no double-wrapping).
"""
from __future__ import annotations

import pytest

from src.lib.d1 import (
    _D1Wrapper,
    _WrappedStatement,
    _to_python,
    wrap_db,
)


# === Mock JsProxy row — mimics pyodide.ffi.JsProxy surface ===

class FakeJsProxy:
    """Mimics pyodide.ffi.JsProxy: indexable, has .keys(), to_py() optional."""

    def __init__(self, data, with_to_py=True):
        self._data = data
        self._with_to_py = with_to_py

    def to_py(self):
        if not self._with_to_py:
            raise RuntimeError("to_py() not supported")
        return self._data

    def keys(self):
        return list(self._data.keys())

    def __getitem__(self, k):
        return self._data[k]

    def __iter__(self):
        return iter(self._data.items())


class FakeJsProxyIterable:
    """Mimics JsProxy wrapping an array of rows (no to_py, just iterable)."""

    def __init__(self, rows):
        self._rows = rows

    def __iter__(self):
        return iter(self._rows)


# === Mock D1 binding ===

class FakeD1Statement:
    """Mock a real D1 prepared statement: bind()/first()/all()/run() return JsProxy."""

    def __init__(self, first_result=None, all_result=None, run_result=None):
        self._first = first_result
        self._all = all_result
        self._run = run_result

    def bind(self, *args):
        return self  # chainable

    async def first(self):
        return self._first

    async def all(self):
        return self._all

    async def run(self):
        return self._run


class FakeRealD1:
    """Mock a real CF D1 binding (returns JsProxy)."""

    def __init__(self, first_result=None, all_result=None, run_result=None):
        self._first = first_result
        self._all = all_result
        self._run = run_result
        self.prepare_calls = []

    def prepare(self, sql):
        self.prepare_calls.append(sql)
        return FakeD1Statement(
            first_result=self._first,
            all_result=self._all,
            run_result=self._run,
        )


# === _to_python tests ===

def test_to_python_none():
    assert _to_python(None) is None


def test_to_python_native_primitives():
    assert _to_python("hello") == "hello"
    assert _to_python(42) == 42
    assert _to_python(3.14) == 3.14
    assert _to_python(True) is True


def test_to_python_native_dict_with_native_values():
    result = _to_python({"a": 1, "b": "x"})
    assert result == {"a": 1, "b": "x"}


def test_to_python_native_dict_with_nested_jsproxy():
    inner = FakeJsProxy({"id": 1, "name": "tool"})
    outer = {"row": inner, "count": 5}
    result = _to_python(outer)
    assert result == {"row": {"id": 1, "name": "tool"}, "count": 5}


def test_to_python_jsproxy_with_to_py():
    row = FakeJsProxy({"id": 1, "name": "tool"})
    result = _to_python(row)
    assert result == {"id": 1, "name": "tool"}


def test_to_python_jsproxy_without_to_py():
    row = FakeJsProxy({"id": 2, "niche": "mmo_reup"}, with_to_py=False)
    result = _to_python(row)
    assert result == {"id": 2, "niche": "mmo_reup"}


def test_to_python_jsproxy_iterable():
    rows = FakeJsProxyIterable([
        FakeJsProxy({"id": 1}),
        FakeJsProxy({"id": 2}),
        FakeJsProxy({"id": 3}),
    ])
    result = _to_python(rows)
    assert result == [{"id": 1}, {"id": 2}, {"id": 3}]


def test_to_python_native_list():
    assert _to_python([1, 2, 3]) == [1, 2, 3]


def test_to_python_native_list_with_jsproxy_items():
    items = [FakeJsProxy({"id": 1}), FakeJsProxy({"id": 2})]
    result = _to_python(items)
    assert result == [{"id": 1}, {"id": 2}]


# === wrap_db tests ===

def test_wrap_db_none():
    assert wrap_db(None) is None


def test_wrap_db_already_wrapped():
    db = FakeRealD1()
    wrapped = wrap_db(db)
    wrapped2 = wrap_db(wrapped)
    assert wrapped is wrapped2  # idempotent


def test_wrap_db_no_prepare_method():
    """Defensive: objects without .prepare() pass through unwrapped."""
    obj = object()  # no .prepare
    assert wrap_db(obj) is obj


def test_wrap_db_real_d1_returns_wrapper():
    db = FakeRealD1()
    wrapped = wrap_db(db)
    assert isinstance(wrapped, _D1Wrapper)
    # Original is preserved
    assert wrapped._db is db


# === Wrapped statement behavior ===

@pytest.mark.asyncio
async def test_wrapped_first_returns_native_dict():
    db = FakeRealD1(first_result=FakeJsProxy({"id": 1, "name": "tool"}))
    wrapped = wrap_db(db)
    stmt = wrapped.prepare("SELECT * FROM tools WHERE id = ?")
    stmt.bind(1)
    result = await stmt.first()
    assert result == {"id": 1, "name": "tool"}
    assert isinstance(result, dict)


@pytest.mark.asyncio
async def test_wrapped_first_returns_none():
    db = FakeRealD1(first_result=None)
    wrapped = wrap_db(db)
    stmt = wrapped.prepare("SELECT * FROM tools WHERE id = ?").bind(999)
    result = await stmt.first()
    assert result is None


@pytest.mark.asyncio
async def test_wrapped_all_returns_list_of_dicts():
    rows = FakeJsProxyIterable([
        FakeJsProxy({"id": 1, "name": "a"}),
        FakeJsProxy({"id": 2, "name": "b"}),
    ])
    db = FakeRealD1(all_result=rows)
    wrapped = wrap_db(db)
    stmt = wrapped.prepare("SELECT * FROM tools").bind()
    result = await stmt.all()
    assert result == [{"id": 1, "name": "a"}, {"id": 2, "name": "b"}]
    assert isinstance(result, list)
    assert all(isinstance(r, dict) for r in result)


@pytest.mark.asyncio
async def test_wrapped_all_with_none():
    db = FakeRealD1(all_result=None)
    wrapped = wrap_db(db)
    stmt = wrapped.prepare("SELECT * FROM tools").bind()
    result = await stmt.all()
    assert result == []


@pytest.mark.asyncio
async def test_wrapped_run_returns_native_dict():
    db = FakeRealD1(run_result=FakeJsProxy({"meta": {"duration": 5}, "success": True}))
    wrapped = wrap_db(db)
    stmt = wrapped.prepare("INSERT INTO tools VALUES (?)").bind("x")
    result = await stmt.run()
    assert result == {"meta": {"duration": 5}, "success": True}


@pytest.mark.asyncio
async def test_wrapped_prepare_forwards_sql():
    db = FakeRealD1()
    wrapped = wrap_db(db)
    wrapped.prepare("SELECT 1")
    assert db.prepare_calls == ["SELECT 1"]


@pytest.mark.asyncio
async def test_chained_prepare_bind_first():
    """Mimics the most common usage pattern: prepare().bind().first()."""
    db = FakeRealD1(first_result=FakeJsProxy({"n": 7}))
    wrapped = wrap_db(db)
    result = await wrapped.prepare("SELECT COUNT(*) AS n FROM x").bind().first()
    assert result == {"n": 7}


@pytest.mark.asyncio
async def test_chained_prepare_bind_all():
    """Mimics: prepare().bind(*params).all()."""
    rows = FakeJsProxyIterable([FakeJsProxy({"id": 1, "niche": "mmo_reup"})])
    db = FakeRealD1(all_result=rows)
    wrapped = wrap_db(db)
    result = await wrapped.prepare("SELECT * FROM tools WHERE niche = ?").bind("mmo_reup").all()
    assert result == [{"id": 1, "niche": "mmo_reup"}]


# === Compatibility with tests/test_e2e.py FakeD1 ===

def test_compat_with_fake_d1():
    """The shim must NOT break FakeD1 (used by all existing tests)."""
    from tests.test_e2e import FakeD1

    db = FakeD1()
    wrapped = wrap_db(db)
    # FakeD1 has .prepare() so it gets wrapped (this is fine — its methods
    # are still callable, and `_to_python` is a no-op on native dicts).
    assert isinstance(wrapped, _D1Wrapper)
    # Calling prepare on the wrapped db returns a wrapped statement
    stmt = wrapped.prepare("SELECT 1")
    assert isinstance(stmt, _WrappedStatement)
