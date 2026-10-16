#!/usr/bin/env python3
"""
Automated Archival & Synchronization Engine for SA Parliament Public Works Committee.
- Traverses folder hierarchy via the SA Parliament backend API.
- Respects rate limits, exponential backoffs, and execution time limits.
- Supports incremental updates via a persistent manifest (only fetches/uploads new or modified files).
- Uploads documents to Internet Archive (Archive.org) using metadata tags.
- Exports structured catalog data (JSON & Markdown) for GitHub Pages and indexing.
"""

import os
import sys
import json
import time
import re
import argparse
import urllib.request
import urllib.parse
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List

API_BASE = "https://committees-api.parliament.sa.gov.au/api"

DEFAULT_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept': 'application/json, text/plain, */*',
    'Origin': 'https://committees.parliament.sa.gov.au',
    'Referer': 'https://committees.parliament.sa.gov.au/',
}

def sanitize_identifier(text: str) -> str:
    """Create clean, valid Internet Archive identifier slug."""
    text = re.sub(r'[^a-zA-Z0-9_\-\.]', '_', text.strip())
    text = re.sub(r'_+', '_', text)
    return text.strip('_')[:80]

class CommitteeArchiver:
    def __init__(self, committee_id: int = 451, manifest_path: str = "data/manifest.json",
                 delay: float = 0.5, max_runtime_minutes: int = 330, dry_run: bool = False):
        self.committee_id = committee_id
        self.manifest_path = manifest_path
        self.delay = delay
        self.max_runtime_seconds = max_runtime_minutes * 60
        self.start_time = time.time()
        self.dry_run = dry_run
        
        self.manifest = self._load_manifest()
        self.ia_session = self._init_ia_session()
        self.download_cache_dir = "tmp_downloads"
        os.makedirs(self.download_cache_dir, exist_ok=True)

    def _load_manifest(self) -> Dict[str, Any]:
        if os.path.exists(self.manifest_path):
            try:
                with open(self.manifest_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                sys.stderr.write(f"Warning: could not load manifest: {e}. Starting fresh.\n")
        return {
            "metadata": {
                "committee_id": self.committee_id,
                "name": "South Australia Public Works Committee",
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

    def _init_ia_session(self):
        ia_access = os.getenv("IA_ACCESS_KEY")
        ia_secret = os.getenv("IA_SECRET_KEY")
        if not ia_access or not ia_secret:
            if not self.dry_run:
                sys.stderr.write("Note: IA_ACCESS_KEY or IA_SECRET_KEY not set. Archive.org uploads will be simulated (dry-run).\n")
            return None
        try:
            import internetarchive
            session = internetarchive.get_session(config={
                's3': {'access': ia_access, 'secret': ia_secret}
            })
            return session
        except Exception as e:
            sys.stderr.write(f"Warning: Failed to initialize Internet Archive session: {e}\n")
            return None

    def _api_get(self, endpoint: str, params: Dict[str, Any], max_retries: int = 5) -> Dict[str, Any]:
        """Perform API GET request with automatic retry and exponential backoff."""
        query = urllib.parse.urlencode(params)
        url = f"{API_BASE}/{endpoint}?{query}"
        req = urllib.request.Request(url, headers=DEFAULT_HEADERS)
        
        last_error = None
        for attempt in range(max_retries):
            # Check elapsed time
            if (time.time() - self.start_time) > self.max_runtime_seconds:
                raise TimeoutError("Execution time limit reached. Halting cleanly to preserve progress.")

            try:
                with urllib.request.urlopen(req, timeout=20) as resp:
                    # Check for rate limit status (HTTP 429)
                    if resp.status == 429:
                        wait = int(resp.headers.get("Retry-After", (attempt + 1) * 3))
                        sys.stderr.write(f"Rate limited (429). Backing off for {wait}s...\n")
                        time.sleep(wait)
                        continue
                    return json.loads(resp.read().decode('utf-8'))
            except Exception as e:
                last_error = e
                backoff = (attempt + 1) * 2
                sys.stderr.write(f"Request {endpoint} attempt {attempt+1} failed: {e}. Backing off {backoff}s...\n")
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
            sys.stderr.write(f"Failed to retrieve download link for {file_id}: {e}\n")
            return None

    def upload_to_archive_org(self, file_path: str, file_record: Dict[str, Any]) -> Optional[str]:
        """Uploads document to Archive.org using official metadata standard."""
        file_id = file_record["id"]
        clean_name = sanitize_identifier(os.path.splitext(file_record["name"])[0])
        # Generate predictable, unique identifier
        ia_identifier = f"sa-parliament-pwc-{file_id[:8]}-{clean_name}"[:80].rstrip('-')
        
        md = {
            'collection': 'opensource_media',
            'mediatype': 'texts',
            'creator': 'Public Works Committee, Parliament of South Australia',
            'title': file_record["name"],
            'description': f"Public document from the Parliament of South Australia Public Works Committee repository. Original path: {file_record['folder_path']}/{file_record['name']}",
            'subject': ['South Australia', 'Parliament', 'Public Works Committee', 'Capital Works', 'Infrastructure'],
            'date': file_record.get("discovered_at", datetime.now(timezone.utc).strftime("%Y-%m-%d")),
            'originalurl': file_record.get("download_url") or "",
            'sa_parliament_file_id': file_id,
            'sa_parliament_folder': file_record.get("folder_path") or ""
        }

        if self.dry_run or not self.ia_session:
            sys.stderr.write(f"[DRY-RUN] Simulating upload for {file_record['name']} -> {ia_identifier}\n")
            return f"https://archive.org/details/{ia_identifier}"

        import internetarchive
        try:
            item = self.ia_session.get_item(ia_identifier)
            sys.stderr.write(f"Uploading {file_record['name']} to Archive.org item '{ia_identifier}'...\n")
            item.upload(
                file_path,
                metadata=md,
                retries=3,
                verify=True,
                verbose=False
            )
            item_url = f"https://archive.org/details/{ia_identifier}"
            sys.stderr.write(f"Successfully uploaded: {item_url}\n")
            return item_url
        except Exception as e:
            sys.stderr.write(f"Archive.org upload failed for {ia_identifier}: {e}\n")
            return None

    def process_file(self, file_info: Dict[str, Any], folder_path: str) -> Dict[str, Any]:
        file_id = file_info.get("Id")
        file_name = file_info.get("FileName")
        file_size = file_info.get("FileSize")
        
        # Check if already present in manifest
        existing = self.manifest["documents"].get(file_id)
        if existing and existing.get("ia_url"):
            # Already archived
            return existing

        sys.stderr.write(f"\nProcessing new/unarchived file: {file_name} ({folder_path})\n")
        download_url = self.get_download_link(file_id)
        
        record = {
            "id": file_id,
            "name": file_name,
            "size_bytes": file_size,
            "folder_path": folder_path,
            "discovered_at": datetime.now(timezone.utc).isoformat(),
            "download_url": download_url,
            "ia_url": None,
            "status": "pending"
        }

        if not download_url:
            record["status"] = "failed_link"
            self.manifest["documents"][file_id] = record
            return record

        local_path = os.path.join(self.download_cache_dir, f"{file_id}_{file_name}")
        try:
            req = urllib.request.Request(download_url, headers=DEFAULT_HEADERS)
            with urllib.request.urlopen(req, timeout=30) as resp, open(local_path, "wb") as out:
                out.write(resp.read())

            ia_url = self.upload_to_archive_org(local_path, record)
            if ia_url:
                record["ia_url"] = ia_url
                record["status"] = "archived"
                record["archived_at"] = datetime.now(timezone.utc).isoformat()
            else:
                record["status"] = "upload_failed"
        except Exception as e:
            sys.stderr.write(f"Error handling download/upload for {file_name}: {e}\n")
            record["status"] = "download_error"
        finally:
            if os.path.exists(local_path):
                os.remove(local_path)

        self.manifest["documents"][file_id] = record
        self.save_manifest()
        return record

    def sync_tree(self, folder_url: Optional[str] = None, folder_path: str = "",
                  max_files: int = sys.maxsize, stats: Optional[Dict[str, int]] = None) -> Dict[str, Any]:
        if stats is None:
            stats = {"processed": 0, "new": 0}

        display_name = folder_path.split("/")[-1] if folder_path else "Public"
        node = {
            "name": display_name,
            "path": folder_path,
            "folders": [],
            "files": []
        }

        if stats["processed"] >= max_files:
            return node

        try:
            data = self.get_folder_items(folder_url)
        except TimeoutError:
            raise
        except Exception as e:
            sys.stderr.write(f"Error retrieving folder '{folder_path}': {e}\n")
            return node

        # Process files in current folder
        for f in (data.get("Files") or []):
            if stats["processed"] >= max_files:
                break
            stats["processed"] += 1
            file_record = self.process_file(f, folder_path=folder_path)
            node["files"].append(file_record)

        # Process child folders
        for sf in (data.get("Folders") or []):
            if stats["processed"] >= max_files:
                break
            sub_url = sf.get("ServerRelativeUrl")
            sub_name = sf.get("FolderName")
            sub_path = f"{folder_path}/{sub_name}".strip("/")
            child_node = self.sync_tree(folder_url=sub_url, folder_path=sub_path, max_files=max_files, stats=stats)
            node["folders"].append(child_node)

        return node

    def build_catalog_outputs(self, tree: Dict[str, Any], catalog_json_path: str, catalog_md_path: str):
        """Exports tree and flat document catalog into clean formats for GitHub and GitHub Pages."""
        all_docs = list(self.manifest["documents"].values())
        
        catalog_data = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "committee": "South Australia Public Works Committee (56th Parliament)",
            "committee_id": self.committee_id,
            "total_documents": len(all_docs),
            "tree": tree,
            "documents": all_docs
        }
        
        os.makedirs(os.path.dirname(os.path.abspath(catalog_json_path)), exist_ok=True)
        with open(catalog_json_path, "w", encoding="utf-8") as f:
            json.dump(catalog_data, f, indent=2)
        sys.stderr.write(f"Saved catalog JSON to {catalog_json_path}\n")

        # Build Markdown catalog
        md_lines = [
            "# SA Parliament Public Works Committee Document Archive",
            "",
            f"**Last Updated:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}  ",
            f"**Total Indexed Documents:** {len(all_docs)}  ",
            f"**Permanent Storage:** [Internet Archive (Archive.org)](https://archive.org)",
            "",
            "## Document Catalog",
            "",
            "| Folder | Document Title | Size | Archive.org Link | Original SA Parliament Source |",
            "| :--- | :--- | :--- | :--- | :--- |"
        ]

        # Sort documents by folder then name
        sorted_docs = sorted(all_docs, key=lambda d: (d.get("folder_path", ""), d.get("name", "")))
        for doc in sorted_docs:
            folder = doc.get("folder_path") or "Root"
            name = doc.get("name", "Unnamed")
            size_kb = f"{(doc.get('size_bytes', 0) / 1024):.1f} KB" if doc.get('size_bytes') else "-"
            ia_url = doc.get("ia_url")
            ia_link = f"[Archive.org Item]({ia_url})" if ia_url else "*Pending upload*"
            orig_url = doc.get("download_url")
            orig_link = f"[Direct Link]({orig_url})" if orig_url else "*Expired/None*"
            md_lines.append(f"| `{folder}` | **{name}** | {size_kb} | {ia_link} | {orig_link} |")

        os.makedirs(os.path.dirname(os.path.abspath(catalog_md_path)), exist_ok=True)
        with open(catalog_md_path, "w", encoding="utf-8") as f:
            f.write("\n".join(md_lines) + "\n")
        sys.stderr.write(f"Saved Markdown catalog to {catalog_md_path}\n")


def main():
    parser = argparse.ArgumentParser(description="Scrape and archive SA Parliament PWC documents")
    parser.add_argument("--committee-id", type=int, default=451, help="Committee ID (default 451)")
    parser.add_argument("--limit", type=int, default=0, help="Max files to process in this run (0 for unlimited)")
    parser.add_argument("--delay", type=float, default=0.4, help="Delay between API queries (default 0.4s)")
    parser.add_argument("--max-runtime", type=int, default=330, help="Max runtime in minutes (default 330 mins for GHA)")
    parser.add_argument("--dry-run", action="store_true", help="Simulate Archive.org uploads without sending")
    parser.add_argument("--manifest", type=str, default="data/manifest.json", help="Path to manifest JSON")
    parser.add_argument("--catalog-json", type=str, default="public/data/catalog.json", help="Path to catalog JSON output")
    parser.add_argument("--catalog-md", type=str, default="CATALOG.md", help="Path to Markdown catalog output")
    args = parser.parse_args()

    archiver = CommitteeArchiver(
        committee_id=args.committee_id,
        manifest_path=args.manifest,
        delay=args.delay,
        max_runtime_minutes=args.max_runtime,
        dry_run=args.dry_run
    )

    max_files = sys.maxsize if args.limit <= 0 else args.limit
    sys.stderr.write(f"Starting archival run (limit: {args.limit if args.limit > 0 else 'All'}, dry_run: {args.dry_run})...\n")

    try:
        tree = archiver.sync_tree(max_files=max_files)
    except TimeoutError as te:
        sys.stderr.write(f"\n{te}\n")
    finally:
        archiver.save_manifest()
        archiver.build_catalog_outputs(
            tree=tree if 'tree' in locals() else {"name": "Public", "folders": [], "files": []},
            catalog_json_path=args.catalog_json,
            catalog_md_path=args.catalog_md
        )

    sys.stderr.write("Archival sync complete.\n")

if __name__ == "__main__":
    main()
