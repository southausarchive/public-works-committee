#!/usr/bin/env python3
"""
Release Archive Sync Engine for SA Parliament Public Works Committee Archive.
- Archives document files to GitHub Releases under tag 'document-archive' (splitting across multiple releases if asset count >= 900).
- Single-Copy Guarantee: Computes SHA-256 hashes to prevent redundant downloads/uploads.
- Version Tracking: If a file is modified at source, uploads a versioned copy (_v2, _v3).
- No Deletions: Files removed from source remain preserved in GitHub Releases.
- Audit Log: Appends records to CHANGELOG.md and public/data/changelog.json.
"""

import os
import sys
import json
import time
import hashlib
import tempfile
import urllib.request
import subprocess
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

import signal
signal.signal(signal.SIGTERM, lambda s, f: sys.exit(0))
signal.signal(signal.SIGINT, lambda s, f: sys.exit(0))


CHANGELOG_PATH = "CHANGELOG.md"
CHANGELOG_JSON_PATH = "public/data/changelog.json"

DEFAULT_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
}

def calculate_sha256(filepath: str) -> str:
    h = hashlib.sha256()
    with open(filepath, 'rb') as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()

def get_release_status_list(repo_slug: Optional[str] = None) -> List[Dict[str, Any]]:
    cmd = ["gh", "release", "list", "--json", "tagName,assets", "--limit", "100"]
    if repo_slug:
        cmd.extend(["--repo", repo_slug])

    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        return []
    try:
        releases = json.loads(res.stdout)
        valid = []
        for r in releases:
            tag = r.get("tagName", "")
            if tag == "document-archive" or tag.startswith("document-archive-"):
                valid.append(r)
        
        def release_sort_key(rel):
            tag = rel["tagName"]
            if tag == "document-archive":
                return 1
            parts = tag.split("-")
            try:
                return int(parts[-1])
            except ValueError:
                return 999
        valid.sort(key=release_sort_key)
        return valid
    except Exception:
        return []

def get_active_release_tag(repo_slug: Optional[str] = None, max_assets_per_release: int = 900) -> str:
    releases = get_release_status_list(repo_slug)
    if not releases:
        return "document-archive"
    
    latest = releases[-1]
    assets = latest.get("assets", [])
    if len(assets) < max_assets_per_release:
        return latest["tagName"]
    else:
        if latest["tagName"] == "document-archive":
            next_tag = "document-archive-2"
        else:
            parts = latest["tagName"].split("-")
            try:
                next_num = int(parts[-1]) + 1
                next_tag = f"document-archive-{next_num}"
            except ValueError:
                next_tag = f"document-archive-{len(releases) + 1}"
        return next_tag

def ensure_release_exists(tag: str, repo_slug: Optional[str] = None):
    check_cmd = ["gh", "release", "view", tag]
    if repo_slug:
        check_cmd.extend(["--repo", repo_slug])

    res = subprocess.run(check_cmd, capture_output=True, text=True)
    if res.returncode != 0:
        sys.stderr.write(f"Creating GitHub Release '{tag}'...\n")
        title = f"Parliamentary Public Works Committee Document Archive ({tag})"
        create_cmd = [
            "gh", "release", "create", tag,
            "--title", title,
            "--notes", f"Permanent immutable archive of South Australia Public Works Committee documents (Release: {tag}).",
        ]
        if repo_slug:
            create_cmd.extend(["--repo", repo_slug])
        create_res = subprocess.run(create_cmd, capture_output=True, text=True)
        if create_res.returncode != 0:
            sys.stderr.write(f"Warning: Failed to create release {tag} via gh: {create_res.stderr}\n")

def upload_release_asset(tag: str, filepath: str, asset_name: str, repo_slug: Optional[str] = None) -> bool:
    """Upload asset to specific GitHub Release tag using gh CLI."""
    ensure_release_exists(tag, repo_slug)
    cmd = [
        "gh", "release", "upload", tag,
        f"{filepath}#{asset_name}",
        "--clobber"
    ]
    if repo_slug:
        cmd.extend(["--repo", repo_slug])

    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode == 0:
        return True
    sys.stderr.write(f"Failed to upload {asset_name} to release {tag}: {res.stderr}\n")
    return False

def sync_release_archive(manifest_path: str = "data/manifest.json",
                         repo_slug: Optional[str] = None,
                         dry_run: bool = False,
                         max_downloads: int = sys.maxsize) -> Dict[str, Any]:
    if not os.path.exists(manifest_path):
        sys.stderr.write(f"Manifest {manifest_path} not found. Skipping archive sync.\n")
        return {"processed": 0, "added": 0, "updated": 0, "unchanged": 0}

    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    if not repo_slug:
        repo_slug = os.environ.get("GITHUB_REPOSITORY", "southausarchive/public-works-committee")

    documents = manifest.get("documents", {})
    stats = {"processed": 0, "added": 0, "updated": 0, "unchanged": 0, "events": []}
    current_time_iso = datetime.now(timezone.utc).isoformat()
    current_date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    download_count = 0

    with tempfile.TemporaryDirectory() as tmpdir:
        for file_id, doc in documents.items():
            if download_count >= max_downloads:
                break

            doc_name = doc.get("name", "document.pdf")
            ext = doc.get("extension") or os.path.splitext(doc_name)[1] or ".pdf"
            download_url = doc.get("download_url")

            existing_archive = doc.get("archive", {})
            existing_hash = existing_archive.get("sha256")
            current_version = existing_archive.get("version", 1)

            if not download_url:
                continue

            stats["processed"] += 1

            # Download file to verify hash and archive
            tmp_file_path = os.path.join(tmpdir, f"{file_id}{ext}")
            req = urllib.request.Request(download_url, headers=DEFAULT_HEADERS)
            try:
                with urllib.request.urlopen(req, timeout=30) as resp, open(tmp_file_path, "wb") as out_file:
                    out_file.write(resp.read())
                download_count += 1
            except Exception as e:
                sys.stderr.write(f"Failed to download {doc_name} ({file_id}) for archiving: {e}\n")
                continue

            new_hash = calculate_sha256(tmp_file_path)

            if existing_hash and existing_hash == new_hash:
                # Content identical: Single-copy guarantee, skip re-upload
                stats["unchanged"] += 1
                try:
                    os.remove(tmp_file_path)
                except OSError:
                    pass
                continue

            # File is either new or content hash changed
            if not existing_hash:
                version = 1
                asset_name = f"{file_id}{ext}"
                event_type = "ADDED"
            else:
                version = current_version + 1
                asset_name = f"{file_id}_v{version}{ext}"
                event_type = "UPDATED"

            # Determine active release tag (handles splitting across releases when >= 900 assets)
            active_tag = "document-archive"
            if not dry_run and os.environ.get("GITHUB_ACTIONS") == "true":
                active_tag = get_active_release_tag(repo_slug)

            release_asset_url = f"https://github.com/{repo_slug}/releases/download/{active_tag}/{asset_name}"

            upload_success = True
            if not dry_run:
                upload_success = upload_release_asset(active_tag, tmp_file_path, asset_name, repo_slug=repo_slug)

            try:
                os.remove(tmp_file_path)
            except OSError:
                pass

            if upload_success:
                doc["archive"] = {
                    "sha256": new_hash,
                    "release_tag": active_tag,
                    "asset_name": asset_name,
                    "release_url": release_asset_url,
                    "archived_at": current_time_iso,
                    "version": version
                }

                if event_type == "ADDED":
                    stats["added"] += 1
                else:
                    stats["updated"] += 1

                stats["events"].append({
                    "date": current_date_str,
                    "timestamp": current_time_iso,
                    "event": event_type,
                    "file_id": file_id,
                    "name": doc_name,
                    "version": version,
                    "sha256": new_hash,
                    "size_bytes": doc.get("size_bytes"),
                    "release_url": release_asset_url
                })

    # Save updated manifest
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    # Append to CHANGELOG.md and public/data/changelog.json if events occurred
    if stats["events"]:
        write_changelog(stats["events"], current_date_str)

    sys.stderr.write(f"Archive sync finished: {stats['added']} added, {stats['updated']} updated, {stats['unchanged']} unchanged.\n")
    return stats

def write_changelog(events: List[Dict[str, Any]], date_str: str):
    os.makedirs(os.path.dirname(os.path.abspath(CHANGELOG_JSON_PATH)), exist_ok=True)
    existing_json = []
    if os.path.exists(CHANGELOG_JSON_PATH):
        try:
            with open(CHANGELOG_JSON_PATH, "r", encoding="utf-8") as f:
                existing_json = json.load(f)
        except Exception:
            existing_json = []

    all_json = events + existing_json
    with open(CHANGELOG_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(all_json, f, indent=2)

    md_header = "# Public Works Committee Document Archive Changelog\n\n"
    existing_md = ""
    if os.path.exists(CHANGELOG_PATH):
        try:
            with open(CHANGELOG_PATH, "r", encoding="utf-8") as f:
                content = f.read()
                if content.startswith(md_header):
                    existing_md = content[len(md_header):]
                else:
                    existing_md = content
        except Exception:
            pass

    new_md_lines = [f"## [{date_str}]"]
    for ev in events:
        size_str = f"{(ev.get('size_bytes', 0)/1024):.1f} KB" if ev.get("size_bytes") else "Unknown size"
        sha_short = ev.get("sha256", "")[:12]
        new_md_lines.append(
            f"- **{ev['event']}**: [{ev['name']}]({ev['release_url']}) (Version {ev['version']}, {size_str}, SHA-256: `{sha_short}...`)"
        )
    new_md_lines.append("")

    with open(CHANGELOG_PATH, "w", encoding="utf-8") as f:
        f.write(md_header + "\n".join(new_md_lines) + "\n" + existing_md)

if __name__ == "__main__":
    limit = 0
    if len(sys.argv) > 1 and sys.argv[1].isdigit():
        limit = int(sys.argv[1])
    max_dls = sys.maxsize if limit <= 0 else limit
    sync_release_archive(max_downloads=max_dls)
