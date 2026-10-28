#!/usr/bin/env python3
"""
Scraper and Static Catalog Generator for SA Parliament Public Works Committee.
- Scrapes folder hierarchy and file metadata via backend API.
- Stores persistent document records in data/manifest.json.
- Generates:
    - public/data/catalog.json (flat document list + full recursive tree)
    - CATALOG.md (formatted Markdown table index)
- Refreshes dynamic download links and provides fallback direct committee links.
"""

import os
import sys
import json
import time
import argparse
import urllib.request
import urllib.parse
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List

API_BASE = "https://committees-api.parliament.sa.gov.au/api"
COMMITTEE_PAGE_URL = "https://committees.parliament.sa.gov.au/committee/451/Public%20Works%20Committee/56/56th%20Parliament%2005%2F05%2F2026%20-%20Current/56"

DEFAULT_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept': 'application/json, text/plain, */*',
    'Origin': 'https://committees.parliament.sa.gov.au',
    'Referer': 'https://committees.parliament.sa.gov.au/',
}

class CommitteeScraper:
    def __init__(self, committee_id: int = 451, manifest_path: str = "data/manifest.json",
                 delay: float = 0.3, max_runtime_minutes: int = 330):
        self.committee_id = committee_id
        self.manifest_path = manifest_path
        self.delay = delay
        self.max_runtime_seconds = max_runtime_minutes * 60
        self.start_time = time.time()
        self.manifest = self._load_manifest()

    def _load_manifest(self) -> Dict[str, Any]:
        if os.path.exists(self.manifest_path):
            try:
                with open(self.manifest_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    # Clean up old IA fields if present
                    return data
            except Exception as e:
                sys.stderr.write(f"Warning: could not load manifest: {e}. Starting fresh.\n")
        return {
            "metadata": {
                "committee_id": self.committee_id,
                "name": "South Australia Public Works Committee",
                "committee_page": COMMITTEE_PAGE_URL,
                "last_run": None,
                "total_documents": 0
            },
            "documents": {}
        }

    def save_manifest(self):
        self.manifest["metadata"]["last_run"] = datetime.now(timezone.utc).isoformat()
        self.manifest["metadata"]["total_documents"] = len(self.manifest.get("documents", {}))
        os.makedirs(os.path.dirname(os.path.abspath(self.manifest_path)), exist_ok=True)
        with open(self.manifest_path, "w", encoding="utf-8") as f:
            json.dump(self.manifest, f, indent=2)

    def _api_get(self, endpoint: str, params: Dict[str, Any], max_retries: int = 5) -> Dict[str, Any]:
        query = urllib.parse.urlencode(params)
        url = f"{API_BASE}/{endpoint}?{query}"
        req = urllib.request.Request(url, headers=DEFAULT_HEADERS)
        
        last_error = None
        for attempt in range(max_retries):
            if (time.time() - self.start_time) > self.max_runtime_seconds:
                raise TimeoutError("Execution time limit reached. Halting cleanly.")

            try:
                with urllib.request.urlopen(req, timeout=25) as resp:
                    if resp.status == 429:
                        wait = int(resp.headers.get("Retry-After", (attempt + 1) * 3))
                        sys.stderr.write(f"Rate limited (429). Waiting {wait}s...\n")
                        time.sleep(wait)
                        continue
                    return json.loads(resp.read().decode('utf-8'))
            except Exception as e:
                last_error = e
                backoff = (attempt + 1) * 2
                sys.stderr.write(f"Request {endpoint} attempt {attempt+1} failed: {e}. Retrying in {backoff}s...\n")
                time.sleep(backoff)

        raise last_error

    def get_folder_items(self, folder_url: Optional[str] = None) -> Dict[str, Any]:
        time.sleep(self.delay)
        params = {"committeeId": self.committee_id}
        if folder_url:
            params["folderURL"] = folder_url
        return self._api_get("CommitteePublicFolder", params)

    def get_download_link(self, file_id: str) -> Optional[str]:
        time.sleep(self.delay)
        params = {"committeeId": self.committee_id, "fileId": file_id}
        try:
            data = self._api_get("CommitteeFileDownloadLink", params)
            return data.get("DownloadLink")
        except Exception as e:
            sys.stderr.write(f"Warning: Failed to fetch download link for {file_id}: {e}\n")
            return None

    def crawl_folder(self, folder_url: Optional[str] = None, folder_path: str = "",
                     max_files: int = sys.maxsize, stats: Optional[Dict[str, int]] = None) -> Dict[str, Any]:
        if stats is None:
            stats = {"count": 0}

        display_name = folder_path.split("/")[-1] if folder_path else "Public"
        node = {
            "name": display_name,
            "path": folder_path,
            "folders": [],
            "files": []
        }

        if stats["count"] >= max_files:
            return node

        try:
            data = self.get_folder_items(folder_url)
        except Exception as e:
            sys.stderr.write(f"Error reading folder '{folder_path}': {e}\n")
            return node

        # Process files in current folder
        raw_files = data.get("Files") or []
        for f in raw_files:
            if stats["count"] >= max_files:
                break
            stats["count"] += 1

            file_id = f.get("Id")
            file_name = f.get("FileName")
            file_size = f.get("FileSize")

            existing = self.manifest["documents"].get(file_id)
            # If new or previous link missing, fetch signed download link
            if not existing or not existing.get("download_url"):
                download_url = self.get_download_link(file_id)
                record = {
                    "id": file_id,
                    "name": file_name,
                    "size_bytes": file_size,
                    "folder_path": folder_path,
                    "discovered_at": datetime.now(timezone.utc).isoformat(),
                    "download_url": download_url,
                    "direct_api_url": f"{API_BASE}/CommitteeFileDownloadLink?committeeId={self.committee_id}&fileId={file_id}",
                    "committee_url": COMMITTEE_PAGE_URL
                }
            else:
                record = existing
                record["name"] = file_name
                record["size_bytes"] = file_size
                record["folder_path"] = folder_path
                record["direct_api_url"] = f"{API_BASE}/CommitteeFileDownloadLink?committeeId={self.committee_id}&fileId={file_id}"
                record["committee_url"] = COMMITTEE_PAGE_URL

            self.manifest["documents"][file_id] = record
            node["files"].append(record)

        # Recursively crawl subfolders
        raw_folders = data.get("Folders") or []
        for sf in raw_folders:
            if stats["count"] >= max_files:
                break
            sub_url = sf.get("ServerRelativeUrl")
            sub_name = sf.get("FolderName")
            sub_path = f"{folder_path}/{sub_name}".strip("/")
            
            child_node = self.crawl_folder(folder_url=sub_url, folder_path=sub_path, max_files=max_files, stats=stats)
            node["folders"].append(child_node)

        return node

    def build_outputs(self, tree: Dict[str, Any], catalog_json_path: str, catalog_md_path: str):
        all_docs = list(self.manifest["documents"].values())
        
        catalog_data = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "committee": "South Australia Public Works Committee (56th Parliament)",
            "committee_id": self.committee_id,
            "committee_page": COMMITTEE_PAGE_URL,
            "total_documents": len(all_docs),
            "tree": tree,
            "documents": all_docs
        }

        os.makedirs(os.path.dirname(os.path.abspath(catalog_json_path)), exist_ok=True)
        with open(catalog_json_path, "w", encoding="utf-8") as f:
            json.dump(catalog_data, f, indent=2)
        sys.stderr.write(f"Saved catalog JSON to {catalog_json_path}\n")

        # Markdown catalog
        md_lines = [
            "# SA Parliament Public Works Committee Document Catalog",
            "",
            f"**Last Indexed:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}  ",
            f"**Total Indexed Documents:** {len(all_docs)}  ",
            f"**Official Repository:** [SA Parliament Committees Portal]({COMMITTEE_PAGE_URL})  ",
            f"**Web Search Interface:** [Browse Index on GitHub Pages](https://southausarchive.github.io/southausarchive/)  ",
            "",
            "## Document Index",
            "",
            "| Folder | Document Name | Size | Download / Access |",
            "| :--- | :--- | :--- | :--- |"
        ]

        sorted_docs = sorted(all_docs, key=lambda d: (d.get("folder_path", ""), d.get("name", "")))
        for doc in sorted_docs:
            folder = doc.get("folder_path") or "Root"
            name = doc.get("name", "Unnamed")
            size_kb = f"{(doc.get('size_bytes', 0) / 1024):.1f} KB" if doc.get('size_bytes') else "-"
            file_id = doc.get("id")
            api_link = f"https://committees-api.parliament.sa.gov.au/api/CommitteeFileDownloadLink?committeeId=451&fileId={file_id}"
            direct_link = doc.get("download_url")
            link_str = f"[Download]({direct_link})" if direct_link else f"[Fetch Link]({api_link})"
            md_lines.append(f"| `{folder}` | **{name}** | {size_kb} | {link_str} |")

        os.makedirs(os.path.dirname(os.path.abspath(catalog_md_path)), exist_ok=True)
        with open(catalog_md_path, "w", encoding="utf-8") as f:
            f.write("\n".join(md_lines) + "\n")
        sys.stderr.write(f"Saved Markdown catalog to {catalog_md_path}\n")


def main():
    parser = argparse.ArgumentParser(description="Scrape SA Parliament PWC Documents Catalog")
    parser.add_argument("--committee-id", type=int, default=451, help="Committee ID (default 451)")
    parser.add_argument("--limit", type=int, default=0, help="File limit (0 for unlimited)")
    parser.add_argument("--delay", type=float, default=0.25, help="Delay between API requests in seconds")
    parser.add_argument("--manifest", type=str, default="data/manifest.json", help="Path to manifest JSON")
    parser.add_argument("--catalog-json", type=str, default="public/data/catalog.json", help="Catalog JSON path")
    parser.add_argument("--catalog-md", type=str, default="CATALOG.md", help="Markdown catalog path")
    args = parser.parse_args()

    scraper = CommitteeScraper(
        committee_id=args.committee_id,
        manifest_path=args.manifest,
        delay=args.delay
    )

    max_files = sys.maxsize if args.limit <= 0 else args.limit
    sys.stderr.write(f"Starting crawl for committee {args.committee_id} (limit: {args.limit or 'All'})...\n")
    
    tree = scraper.crawl_folder(max_files=max_files)
    scraper.save_manifest()
    scraper.build_outputs(
        tree=tree,
        catalog_json_path=args.catalog_json,
        catalog_md_path=args.catalog_md
    )
    sys.stderr.write("Indexing completed successfully.\n")

if __name__ == "__main__":
    main()
