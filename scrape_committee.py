#!/usr/bin/env python3
"""
Scraper for SA Parliament Public Works Committee Document Repository.
Extracts folder hierarchy, files, and signed download links using the backend API.
Supports HTTP/HTTPS proxies with automatic retries and exponential backoff.
"""

import sys
import os
import json
import time
import argparse
import urllib.request
import urllib.parse
from typing import Optional, Dict, Any, List

API_BASE = "https://committees-api.parliament.sa.gov.au/api"

DEFAULT_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept': 'application/json, text/plain, */*',
    'Origin': 'https://committees.parliament.sa.gov.au',
    'Referer': 'https://committees.parliament.sa.gov.au/',
}

class CommitteeScraper:
    def __init__(self, committee_id: int = 451, proxy: Optional[str] = None, delay: float = 0.5, max_retries: int = 5):
        self.committee_id = committee_id
        self.proxy = proxy
        self.delay = delay
        self.max_retries = max_retries
        self.opener = self._build_opener()

    def _build_opener(self):
        handlers = []
        if self.proxy:
            handlers.append(urllib.request.ProxyHandler({
                'http': self.proxy,
                'https': self.proxy
            }))
        return urllib.request.build_opener(*handlers)

    def _request_with_retry(self, req: urllib.request.Request) -> bytes:
        last_err = None
        for attempt in range(self.max_retries):
            try:
                with self.opener.open(req, timeout=15) as resp:
                    return resp.read()
            except Exception as e:
                last_err = e
                backoff = (attempt + 1) * 1.5
                time.sleep(backoff)
        raise last_err

    def check_outgoing_ip(self) -> str:
        req = urllib.request.Request("http://icanhazip.com", headers={'User-Agent': 'curl/7.68.0'})
        try:
            return self._request_with_retry(req).decode('utf-8').strip()
        except Exception as e:
            return f"Error verifying IP: {e}"

    def get_folder_contents(self, folder_url: Optional[str] = None) -> Dict[str, Any]:
        params = {"committeeId": self.committee_id}
        if folder_url:
            params["folderURL"] = folder_url
        query = urllib.parse.urlencode(params)
        url = f"{API_BASE}/CommitteePublicFolder?{query}"
        
        req = urllib.request.Request(url, headers=DEFAULT_HEADERS)
        raw = self._request_with_retry(req)
        return json.loads(raw.decode('utf-8'))

    def get_file_download_link(self, file_id: str) -> Optional[str]:
        query = urllib.parse.urlencode({
            "committeeId": self.committee_id,
            "fileId": file_id
        })
        url = f"{API_BASE}/CommitteeFileDownloadLink?{query}"
        req = urllib.request.Request(url, headers=DEFAULT_HEADERS)
        try:
            raw = self._request_with_retry(req)
            data = json.loads(raw.decode('utf-8'))
            return data.get("DownloadLink")
        except Exception as e:
            sys.stderr.write(f"Failed to get download link for {file_id}: {e}\n")
            return None

    def crawl_tree(self, folder_rel_url: Optional[str] = None, folder_name: str = "Public", max_files: int = 10, stats: Optional[Dict[str, int]] = None) -> Dict[str, Any]:
        if stats is None:
            stats = {"file_count": 0}

        node = {
            "type": "folder",
            "name": folder_name,
            "path": folder_rel_url or "",
            "folders": [],
            "files": []
        }

        if stats["file_count"] >= max_files:
            return node

        time.sleep(self.delay)
        try:
            data = self.get_folder_contents(folder_rel_url)
        except Exception as e:
            sys.stderr.write(f"Error reading folder '{folder_rel_url}': {e}\n")
            return node

        # Process files in this folder
        files = data.get("Files") or []
        for f in files:
            if stats["file_count"] >= max_files:
                break

            file_id = f.get("Id")
            file_name = f.get("FileName")
            file_size = f.get("FileSize")

            time.sleep(self.delay)
            download_url = self.get_file_download_link(file_id)
            stats["file_count"] += 1

            node["files"].append({
                "type": "file",
                "id": file_id,
                "name": file_name,
                "size_bytes": file_size,
                "download_url": download_url
            })
            sys.stderr.write(f"[{stats['file_count']}/{max_files}] Indexed file: {file_name}\n")

        # Process subfolders
        subfolders = data.get("Folders") or []
        for sub in subfolders:
            if stats["file_count"] >= max_files:
                break
            sub_url = sub.get("ServerRelativeUrl")
            sub_name = sub.get("FolderName")
            child_node = self.crawl_tree(folder_rel_url=sub_url, folder_name=sub_name, max_files=max_files, stats=stats)
            node["folders"].append(child_node)

        return node

def format_tree_text(node: Dict[str, Any], prefix: str = "", is_last: bool = True) -> List[str]:
    lines = []
    connector = "└── " if is_last else "├── "
    
    if node["type"] == "folder":
        folder_display = f"📁 {node['name']}/"
        if not prefix:  # Root
            lines.append(folder_display)
            child_prefix = ""
        else:
            lines.append(f"{prefix}{connector}{folder_display}")
            child_prefix = prefix + ("    " if is_last else "│   ")

        items = []
        for sf in node.get("folders", []):
            items.append(("folder", sf))
        for f in node.get("files", []):
            items.append(("file", f))

        for idx, (kind, item) in enumerate(items):
            last_item = (idx == len(items) - 1)
            if kind == "folder":
                lines.extend(format_tree_text(item, prefix=child_prefix, is_last=last_item))
            else:
                lines.extend(format_tree_text(item, prefix=child_prefix, is_last=last_item))
    else:
        file_connector = "└── " if is_last else "├── "
        size_kb = f"{(node.get('size_bytes', 0) / 1024):.1f} KB" if node.get('size_bytes') else "unknown size"
        lines.append(f"{prefix}{file_connector}📄 {node['name']} ({size_kb})")
        link_prefix = prefix + ("    " if is_last else "│   ")
        lines.append(f"{link_prefix}    🔗 {node.get('download_url')}")

    return lines


def main():
    parser = argparse.ArgumentParser(description="Scrape SA Parliament Public Works Committee files")
    parser.add_argument("--committee-id", type=int, default=451, help="Committee ID (default 451)")
    parser.add_argument("--limit", type=int, default=10, help="File limit (default 10, set 0 for all)")
    parser.add_argument("--proxy", type=str, default="http://205.237.105.49:3129", help="Proxy URL (e.g. http://ip:port)")
    parser.add_argument("--delay", type=float, default=0.3, help="Request delay in seconds")
    parser.add_argument("--output-json", type=str, default=None, help="Save JSON output to path")
    parser.add_argument("--output-text", type=str, default=None, help="Save formatted tree text to path")
    args = parser.parse_args()

    scraper = CommitteeScraper(committee_id=args.committee_id, proxy=args.proxy, delay=args.delay)

    if args.proxy:
        sys.stderr.write(f"Using proxy: {args.proxy}\n")
        ip = scraper.check_outgoing_ip()
        sys.stderr.write(f"Proxy verified. Outgoing IP: {ip}\n\n")

    max_files = sys.maxsize if args.limit <= 0 else args.limit
    sys.stderr.write(f"Crawling committee {args.committee_id} (limit: {args.limit} files)...\n")
    
    tree = scraper.crawl_tree(max_files=max_files)
    formatted_tree = "\n".join(format_tree_text(tree))

    print("\n" + "="*80)
    print("DIRECTORY TREE INDEX")
    print("="*80)
    print(formatted_tree)
    print("="*80 + "\n")

    if args.output_json:
        with open(args.output_json, "w", encoding="utf-8") as f:
            json.dump(tree, f, indent=2)
        sys.stderr.write(f"Saved JSON tree to {args.output_json}\n")

    if args.output_text:
        with open(args.output_text, "w", encoding="utf-8") as f:
            f.write(formatted_tree + "\n")
        sys.stderr.write(f"Saved text tree to {args.output_text}\n")

if __name__ == "__main__":
    main()
