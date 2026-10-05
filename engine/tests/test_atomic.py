"""The engine's atomic-write helper.

The contract is crash-safety, which is only testable by writing the file and
reading back what landed. These assert the file contents and that no `.tmp`
survives, because a leftover tmp is the visible symptom of a failed write.
"""

import json
import os

import pytest

from tempo_engine import atomic


def test_write_json_lands_and_leaves_no_tmp(tmp_path):
    path = tmp_path / "nested" / "a.json"
    atomic.write_json(path, {"b": 2, "a": 1}, sort_keys=True, indent=2)

    assert json.loads(path.read_text(encoding="utf-8")) == {"a": 1, "b": 2}
    assert list(path.parent.glob("*.tmp")) == []


def test_dump_kwargs_reach_the_caller(tmp_path):
    # Callers keep their own formatting; the helper does not impose one.
    path = tmp_path / "a.json"
    atomic.write_json(path, {"b": 1, "a": 2}, sort_keys=True)
    assert path.read_text(encoding="utf-8") == '{"a": 2, "b": 1}'


def test_write_bytes_overwrites_without_truncating(tmp_path):
    path = tmp_path / "a.bin"
    atomic.write_bytes(path, b"first")
    atomic.write_bytes(path, b"second")
    assert path.read_bytes() == b"second"


def test_a_failed_write_leaves_the_previous_file_intact(tmp_path, monkeypatch):
    # The point of tmp + replace: the destination is only ever touched by a
    # complete write, so a crash mid-serialize reads as the old value, not a
    # truncated one.
    path = tmp_path / "a.json"
    atomic.write_json(path, {"n": 1})

    def boom(*args, **kwargs):  # noqa: ARG001
        raise OSError("disk full")

    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(OSError):
        atomic.write_json(path, {"n": 2})

    assert json.loads(path.read_text(encoding="utf-8")) == {"n": 1}
    # The half-written temp is left behind; the caller can clean it or ignore it.
    assert [p.name for p in tmp_path.iterdir() if p.name.endswith(".tmp")] == ["a.json.tmp"]
