#!/usr/bin/env python3
"""
Gentle Background Wayback Machine Archiving Engine.
- Submits pages and document links to Wayback Machine Save Page Now (SPN).
- Detects HTTP 429 Too Many Requests and honors Retry-After headers with exponential backoff.
- Conservative rate limiting (default 8.0s delay between requests).
- Prioritizes root, directory index, and newly added/updated documents.
- Records 'wayback_archived_at' timestamp to avoid redundant submissions.
"""

import os
import sys
import json
import time
import argparse
import urllib.request
import urllib.error
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

SPN_ENDPOINT = "https://web.archive.org/save/"
BASE_URL = "https://southausarchive.github.io/public-works-committee"

DEFAULT_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) SouthAusArchive-Bot/1.0',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'
}

class WaybackArchiver:
    def __init__(self, manifest_path: str = "data/manifest.json",
                 changelog_json_path: str = "public/data/changelog.json",
                 base_delay: float = 8.0,
                 max_batch: int = 40,
                 dry_run: bool = False):
        self.manifest_path = manifest_path
        self.changelog_json_path = changelog_json_path
        self.base_delay = base_delay
        self.max_batch = max_batch
        self.dry_run = dry_run
        self.consecutive_rate_limits = 0

    def submit_url(self, target_url: str, max_retries: int = 3) -> bool:
        """Submit a single URL to Save Page Now with 429 handling and backoff."""
        if self.dry_run:
            sys.stderr.write(f"[Dry-run] Would submit to Wayback: {target_url}\n")
            return True

        req_url = f"{SPN_ENDPOINT}{target_url}"
        req = urllib.request.Request(req_url, headers=DEFAULT_HEADERS, method="GET")

        backoff_seconds = 60
        for attempt in range(max_retries):
            try:
                sys.stderr.write(f"Archiving [{attempt + 1}/{max_retries}]: {target_url}\n")
                with urllib.request.urlopen(req, timeout=30) as resp:
                    if resp.status in (200, 301, 302):
                        sys.stderr.write(f"-> Archived successfully (HTTP {resp.status})\n")
                        self.consecutive_rate_limits = 0
                        return True
            except urllib.error.HTTPError as e:
                if e.code == 429:
                    self.consecutive_rate_limits += 1
                    retry_header = e.headers.get("Retry-After")
                    wait_time = int(retry_header) + 5 if (retry_header and retry_header.isdigit()) else backoff_seconds
                    sys.stderr.write(f"-> Rate limit hit (HTTP 429). Sleeping {wait_time}s before retry...\n")
                    time.sleep(wait_time)
                    backoff_seconds = min(backoff_seconds * 2, 300)
                    if self.consecutive_rate_limits >= 3:
                        sys.stderr.write("-> 3 consecutive rate limits encountered. Circuit breaker triggered to prevent account block.\n")
                        return False
                    continue
                elif e.code in (502, 503, 504):
                    sys.stderr.write(f"-> Server error (HTTP {e.code}). Waiting 15s...\n")
                    time.sleep(15)
                    continue
                else:
                    sys.stderr.write(f"-> Wayback submission failed with HTTP {e.code}: {e.reason}\n")
                    return False
            except Exception as ex:
                sys.stderr.write(f"-> Request exception: {ex}\n")
                time.sleep(10)

        return False

    def build_priority_queue(self, manifest: Dict[str, Any]) -> List[Dict[str, str]]:
        """Builds prioritized queue of URLs to submit."""
        queue = []
        seen_urls = set()

        # Priority 1: Site Entrypoints
        entrypoints = [
            {"type": "root", "url": f"{BASE_URL}/"},
            {"type": "archive-index", "url": f"{BASE_URL}/archive-index.html"}
        ]
        for ep in entrypoints:
            queue.append(ep)
            seen_urls.add(ep["url"])

        # Priority 2: Recently Added or Updated Documents
        recent_ids = set()
        if os.path.exists(self.changelog_json_path):
            try:
                with open(self.changelog_json_path, "r", encoding="utf-8") as f:
                    changelog = json.load(f)
                    for item in changelog[:30]:
                        if item.get("file_id"):
                            recent_ids.add(item["file_id"])
            except Exception:
                pass

        documents = manifest.get("documents", {})
        for fid in recent_ids:
            doc = documents.get(fid)
            if doc:
                doc_page_url = f"{BASE_URL}/documents/{fid}.html"
                if doc_page_url not in seen_urls:
                    queue.append({"type": "recent_doc", "id": fid, "url": doc_page_url})
                    seen_urls.add(doc_page_url)

        # Priority 3: Oldest Unarchived Documents
        unarchived = []
        for fid, doc in documents.items():
            doc_page_url = f"{BASE_URL}/documents/{fid}.html"
            if doc_page_url in seen_urls:
                continue
            last_archived = doc.get("wayback_archived_at")
            unarchived.append({
                "type": "doc",
                "id": fid,
                "url": doc_page_url,
                "last_archived": last_archived or ""
            })

        # Sort by oldest last_archived date first
        unarchived.sort(key=lambda x: x["last_archived"])
        queue.extend(unarchived)

        return queue

    def run(self):
        if not os.path.exists(self.manifest_path):
            sys.stderr.write(f"Manifest {self.manifest_path} not found. Skipping Wayback archiving.\n")
            return

        with open(self.manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)

        queue = self.build_priority_queue(manifest)
        total_in_batch = min(len(queue), self.max_batch)
        sys.stderr.write(f"Starting Wayback background archiving: {total_in_batch} URLs queued (Batch limit: {self.max_batch}, Delay: {self.base_delay}s)...\n")

        processed = 0
        succeeded = 0

        for item in queue[:total_in_batch]:
            if self.consecutive_rate_limits >= 3:
                sys.stderr.write("Halting archiving run due to persistent rate limiting.\n")
                break

            target_url = item["url"]
            ok = self.submit_url(target_url)
            processed += 1
            if ok:
                succeeded += 1
                now_iso = datetime.now(timezone.utc).isoformat()
                doc_id = item.get("id")
                if doc_id and doc_id in manifest.get("documents", {}):
                    manifest["documents"][doc_id]["wayback_archived_at"] = now_iso

            # Respect conservative rate limit delay between submissions
            time.sleep(self.base_delay)

        # Save manifest state with updated timestamps
        if not self.dry_run and succeeded > 0:
            with open(self.manifest_path, "w", encoding="utf-8") as f:
                json.dump(manifest, f, indent=2)

        sys.stderr.write(f"Wayback archiving batch complete: {succeeded}/{processed} succeeded.\n")

def main():
    parser = argparse.ArgumentParser(description="Conservative Wayback Machine Archiving Engine")
    parser.add_argument("--manifest", type=str, default="data/manifest.json", help="Path to manifest JSON")
    parser.add_argument("--changelog", type=str, default="public/data/changelog.json", help="Path to changelog JSON")
    parser.add_argument("--delay", type=float, default=8.0, help="Delay between submissions in seconds (default 8.0s)")
    parser.add_argument("--batch-size", type=int, default=40, help="Maximum URLs per archiving batch (default 40)")
    parser.add_argument("--dry-run", action="store_true", help="Simulate without calling Wayback API")
    args = parser.parse_args()

    archiver = WaybackArchiver(
        manifest_path=args.manifest,
        changelog_json_path=args.changelog,
        base_delay=args.delay,
        max_batch=args.batch_size,
        dry_run=args.dry_run
    )
    archiver.run()

if __name__ == "__main__":
    main()
