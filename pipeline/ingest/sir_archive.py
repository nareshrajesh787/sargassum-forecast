"""NOAA/USF Sargassum Inundation Risk (SIR v1.5) daily archiver.

SIR publishes only the latest products; dated files from past seasons return 404, so history
exists only if we archive it ourselves. For each day in a look-back window this downloads

    KMZ/sargassum_risk_YYYYMMDD.kmz
    KMZ/Sargassum_risk_currents_FA_YYYYMMDD.kmz
    PDF/SIR_YYYYMMDD.pdf

validates each file (zip / PDF magic bytes), records it in ``archive/sir/manifest.csv``
(committed) and stores the bytes under ``archive/sir/files/YYYY/MM/`` (not committed: ~7.4 MB/day,
~2.7 GB/year, too large for git or free LFS). With ``--upload`` each file is also attached to a
monthly GitHub release ``sir-archive-YYYY-MM`` (prerelease), which is the durable store.

A missing file is logged and skipped; the run never fails because a day is missing.
Credit: NOAA AOML / University of South Florida, SIR v1.5 (experimental product).

Usage:  uv run python -m pipeline.ingest.sir_archive [--days 7] [--upload]
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import logging
import subprocess
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import requests

BASE = "https://cwcgom.aoml.noaa.gov/SIR/"
TEMPLATES = (
    "KMZ/sargassum_risk_{d}.kmz",
    "KMZ/Sargassum_risk_currents_FA_{d}.kmz",
    "PDF/SIR_{d}.pdf",
)
MANIFEST_FIELDS = ["date", "file", "bytes", "sha256", "fetched_at_utc", "store"]
USER_AGENT = "sargassum-forecast/0.1 (research; github.com/nareshrajesh787/sargassum-forecast)"
log = logging.getLogger("sir_archive")


@dataclass(frozen=True)
class Item:
    day: date
    rel: str  # path relative to BASE

    @property
    def name(self) -> str:
        return self.rel.split("/")[-1]


def items_for(day: date) -> list[Item]:
    d = day.strftime("%Y%m%d")
    return [Item(day, t.format(d=d)) for t in TEMPLATES]


def looks_valid(name: str, content: bytes) -> bool:
    """KMZ is a zip (PK\\x03\\x04); PDF starts with %PDF. Rejects HTML error pages served as 200."""
    if name.endswith(".kmz"):
        return content[:4] == b"PK\x03\x04"
    if name.endswith(".pdf"):
        return content[:4] == b"%PDF"
    return False


def read_manifest(path: Path) -> set[str]:
    if not path.exists():
        return set()
    with path.open() as f:
        return {row["file"] for row in csv.DictReader(f)}


def append_manifest(path: Path, row: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    new = not path.exists()
    with path.open("a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=MANIFEST_FIELDS)
        if new:
            w.writeheader()
        w.writerow(row)


def gh_upload(file: Path, day: date, repo: str | None) -> str:
    """Attach ``file`` to the monthly prerelease, creating it if needed. Returns the release tag."""
    tag = f"sir-archive-{day:%Y-%m}"
    repo_args = ["--repo", repo] if repo else []
    exists = subprocess.run(["gh", "release", "view", tag, *repo_args], capture_output=True).returncode == 0
    if not exists:
        notes = (
            f"Daily archive of NOAA/USF Sargassum Inundation Risk (SIR v1.5) products for {day:%Y-%m}. "
            "Source: https://cwcgom.aoml.noaa.gov/SIR/ . Credit: NOAA AOML and the University of South "
            "Florida Optical Oceanography Lab. Experimental product, archived unmodified for research."
        )
        subprocess.run(
            ["gh", "release", "create", tag, "--prerelease", "--title", tag, "--notes", notes, *repo_args],
            check=True,
            capture_output=True,
        )
    subprocess.run(
        ["gh", "release", "upload", tag, str(file), "--clobber", *repo_args], check=True, capture_output=True
    )
    return tag


def run(days: int, root: Path, upload: bool, repo: str | None, today: date | None = None) -> dict[str, int]:
    today = today or datetime.now(UTC).date()
    manifest = root / "manifest.csv"
    have = read_manifest(manifest)
    stats = {"archived": 0, "already": 0, "missing": 0, "invalid": 0, "error": 0}
    sess = requests.Session()
    sess.headers["User-Agent"] = USER_AGENT
    for back in range(days, -1, -1):  # oldest first so the manifest stays date-ordered
        day = today - timedelta(days=back)
        for it in items_for(day):
            if it.name in have:
                stats["already"] += 1
                continue
            try:
                r = sess.get(BASE + it.rel, timeout=120)
            except requests.RequestException as e:
                log.warning("error %s: %s", it.rel, e)
                stats["error"] += 1
                continue
            if r.status_code == 404:
                log.info("missing %s (404)", it.rel)
                stats["missing"] += 1
                continue
            if r.status_code != 200 or not looks_valid(it.name, r.content):
                log.warning("invalid %s (HTTP %s, %d bytes)", it.rel, r.status_code, len(r.content))
                stats["invalid"] += 1
                continue
            dest = root / "files" / f"{day:%Y}" / f"{day:%m}" / it.name
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(r.content)
            store = "local"
            if upload:
                try:
                    store = "release:" + gh_upload(dest, day, repo)
                except subprocess.CalledProcessError as e:
                    log.error("upload failed for %s: %s", it.name, (e.stderr or b"").decode()[:300])
                    stats["error"] += 1
                    continue  # not recorded, so the next run retries it
            append_manifest(
                manifest,
                {
                    "date": day.isoformat(),
                    "file": it.name,
                    "bytes": str(len(r.content)),
                    "sha256": hashlib.sha256(r.content).hexdigest(),
                    "fetched_at_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "store": store,
                },
            )
            have.add(it.name)
            stats["archived"] += 1
            log.info("archived %s -> %s", it.rel, store)
    return stats


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=7, help="look-back window in days (catches up after outages)")
    ap.add_argument("--root", type=Path, default=Path("archive/sir"))
    ap.add_argument("--upload", action="store_true", help="attach files to monthly GitHub prereleases")
    ap.add_argument("--repo", default=None, help="owner/name for gh (default: current repo)")
    a = ap.parse_args()
    stats = run(a.days, a.root, a.upload, a.repo)
    print("SIR archive:", stats)  # never exits non-zero for missing days


if __name__ == "__main__":
    main()
