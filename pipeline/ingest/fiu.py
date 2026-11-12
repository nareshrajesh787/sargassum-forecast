"""FIU Sargassum Watch (Epicollect5) adapter.

Pages through the public export API and saves raw JSON snapshots under
``data/raw/fiu/<fetch_utc>/page_NNN.json``. ``data/`` is never committed: FIU raw reports and
photos must not be republished (CLAUDE.md rule 8). Photo URLs stay in the raw snapshot only;
photo files are never downloaded.

The API rate-limits bursts (HTTP 429 after ~5 quick pages), so requests are paced, ``Retry-After``
is honoured, and an interrupted snapshot resumes from ``<fetch_utc>.partial/``.

Usage:  uv run python -m pipeline.ingest.fiu [--out data/raw/fiu]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import requests

API = "https://five.epicollect.net/api/export/entries/sargassum-watch"
PER_PAGE = 1000  # API maximum
USER_AGENT = "sargassum-forecast/0.1 (research; github.com/nareshrajesh787/sargassum-forecast)"
log = logging.getLogger("fiu")


def fetch_page(
    page: int, per_page: int = PER_PAGE, retries: int = 8, timeout: int = 120, session: Any = requests
) -> dict[str, Any]:
    """Fetch one page. Honours ``Retry-After`` on 429; exponential backoff otherwise."""
    last: Exception | str | None = None
    for attempt in range(retries):
        try:
            r = session.get(
                API,
                params={"per_page": per_page, "page": page},
                headers={"User-Agent": USER_AGENT},
                timeout=timeout,
            )
            if r.status_code == 429:
                wait = float(r.headers.get("Retry-After", 0) or 0) or min(120.0, 5 * 2**attempt)
                log.warning("page %d: 429, sleeping %.0fs", page, wait)
                last = "HTTP 429"
                time.sleep(wait + 1)
                continue
            r.raise_for_status()
            payload: dict[str, Any] = r.json()
            return payload
        except (requests.RequestException, ValueError) as e:  # ValueError: bad JSON
            last = e
            time.sleep(min(120.0, 5 * 2**attempt))
    raise RuntimeError(f"FIU page {page} failed after {retries} attempts: {last}")


def snapshot(out_root: Path, pause_s: float = 13.0) -> Path:
    """Download every page into a timestamped snapshot dir (resuming a ``.partial`` one if present)."""
    out_root.mkdir(parents=True, exist_ok=True)
    partials = sorted(out_root.glob("*.partial"))
    if partials:
        work = partials[-1]
        log.info("resuming %s", work)
    else:
        work = out_root / (datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + ".partial")
        work.mkdir()
    first_p = work / "page_001.json"
    if first_p.exists():
        first = json.loads(first_p.read_text())
    else:
        first = fetch_page(1)
        first_p.write_text(json.dumps(first))
    last_page = int(first["meta"]["last_page"])
    timings: list[float] = []
    for page in range(2, last_page + 1):
        p = work / f"page_{page:03d}.json"
        if p.exists():
            continue
        time.sleep(pause_s)
        t0 = time.monotonic()
        payload = fetch_page(page)
        timings.append(time.monotonic() - t0)
        p.write_text(json.dumps(payload))
    entries = load_entries(work)
    meta = {
        "fetched_at_utc": work.name.removesuffix(".partial"),
        "completed_at_utc": datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ"),
        "api": API,
        "per_page": PER_PAGE,
        "api_meta": first["meta"],
        "pages": last_page,
        "unique_entries": len(entries),
        "content_sha256": content_hash(entries),
        "seconds_per_page_mean": (sum(timings) / len(timings)) if timings else None,
    }
    (work / "_meta.json").write_text(json.dumps(meta, indent=2))
    final = work.with_name(meta["fetched_at_utc"])
    work.rename(final)
    return final


def content_hash(entries: list[dict[str, Any]]) -> str:
    """Order-independent hash of a snapshot's entries (for manifests and change detection)."""
    canon = sorted(json.dumps(e, sort_keys=True) for e in entries)
    return hashlib.sha256("\n".join(canon).encode()).hexdigest()


def load_entries(snapshot_dir: Path) -> list[dict[str, Any]]:
    """Load all entries from a snapshot directory, de-duplicated on ``ec5_uuid``."""
    seen: dict[str, dict[str, Any]] = {}
    for p in sorted(snapshot_dir.glob("page_*.json")):
        for e in json.loads(p.read_text())["data"]["entries"]:
            seen[e["ec5_uuid"]] = e
    return list(seen.values())


def latest_snapshot(out_root: Path) -> Path:
    snaps = sorted(
        d for d in out_root.iterdir() if d.is_dir() and not d.name.endswith(".partial") and (d / "_meta.json").exists()
    )
    if not snaps:
        raise FileNotFoundError(f"No complete FIU snapshot under {out_root}; run `python -m pipeline.ingest.fiu`")
    return snaps[-1]


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=Path("data/raw/fiu"))
    ap.add_argument("--manifest", type=Path, default=None, help="append a summary row (no raw content) here")
    a = ap.parse_args()
    d = snapshot(a.out)
    meta = json.loads((d / "_meta.json").read_text())
    print(f"saved {d} ({meta['unique_entries']} unique entries)")
    if a.manifest:
        a.manifest.parent.mkdir(parents=True, exist_ok=True)
        new = not a.manifest.exists()
        with a.manifest.open("a") as f:
            if new:
                f.write("fetched_at_utc,unique_entries,api_total,newest,oldest,content_sha256\n")
            m = meta["api_meta"]
            f.write(
                f"{meta['fetched_at_utc']},{meta['unique_entries']},{m['total']},{m['newest']},{m['oldest']},"
                f"{meta['content_sha256']}\n"
            )


if __name__ == "__main__":
    main()
