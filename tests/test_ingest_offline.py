"""Offline tests for the Phase 0 adapters (no network)."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from pipeline.ingest import fiu, sir_archive


def test_sir_items_for_day() -> None:
    names = [it.rel for it in sir_archive.items_for(date(2026, 11, 9))]
    assert names == [
        "KMZ/sargassum_risk_20261109.kmz",
        "KMZ/Sargassum_risk_currents_FA_20261109.kmz",
        "PDF/SIR_20261109.pdf",
    ]


@pytest.mark.parametrize(
    ("name", "content", "ok"),
    [
        ("a.kmz", b"PK\x03\x04rest", True),
        ("a.kmz", b"<html>404</html>", False),
        ("a.pdf", b"%PDF-1.7", True),
        ("a.pdf", b"<!DOCTYPE html>", False),
        ("a.txt", b"PK\x03\x04", False),
    ],
)
def test_sir_validation(name: str, content: bytes, ok: bool) -> None:
    assert sir_archive.looks_valid(name, content) is ok


def test_sir_manifest_roundtrip(tmp_path: Path) -> None:
    m = tmp_path / "manifest.csv"
    assert sir_archive.read_manifest(m) == set()
    row = {
        "date": "2026-11-09",
        "file": "x.kmz",
        "bytes": "1",
        "sha256": "0",
        "fetched_at_utc": "t",
        "store": "local",
    }
    sir_archive.append_manifest(m, row)
    sir_archive.append_manifest(m, {**row, "file": "y.pdf"})
    assert sir_archive.read_manifest(m) == {"x.kmz", "y.pdf"}
    assert m.read_text().count("date,file") == 1


class _Resp:
    def __init__(self, status: int, payload: dict | None = None, headers: dict | None = None) -> None:
        self.status_code = status
        self._payload = payload or {}
        self.headers = headers or {}

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            import requests

            raise requests.HTTPError(str(self.status_code))

    def json(self) -> dict:
        return self._payload


def test_fiu_fetch_honours_429(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[int] = []
    sleeps: list[float] = []

    class Sess:
        def get(self, *a: object, **k: object) -> _Resp:
            calls.append(1)
            if len(calls) == 1:
                return _Resp(429, headers={"Retry-After": "3"})
            return _Resp(200, {"ok": True})

    monkeypatch.setattr(fiu.time, "sleep", lambda s: sleeps.append(s))
    assert fiu.fetch_page(1, session=Sess()) == {"ok": True}
    assert sleeps == [4.0]


def test_fiu_load_entries_dedupes(tmp_path: Path) -> None:
    for i, uuids in enumerate([["a", "b"], ["b", "c"]], start=1):
        page = {"data": {"entries": [{"ec5_uuid": u, "v": i} for u in uuids]}}
        (tmp_path / f"page_{i:03d}.json").write_text(json.dumps(page))
    entries = fiu.load_entries(tmp_path)
    assert sorted(e["ec5_uuid"] for e in entries) == ["a", "b", "c"]
    assert fiu.content_hash(entries) == fiu.content_hash(list(reversed(entries)))
