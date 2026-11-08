#!/usr/bin/env python3
"""
SEO, Live Resolver & Static Page Generator for SA Parliament Public Works Committee Archive.
- Generates dedicated static HTML landing pages for every document (/documents/{id}.html).
- Generates permanent live redirect resolvers (/download/{id}.html) for Solution A.
- Links to permanent immutable GitHub Release assets for Solution B.
- Generates crawlable plain-HTML archive catalog (/archive-index.html) for Wayback Machine / Heritrix.
- Embeds Schema.org (JSON-LD) and Dublin Core metadata for Googlebot and Internet Archive.
- Creates XML sitemap (sitemap.xml) and robots.txt.
"""

import os
import sys
import json
import re
import html
from datetime import datetime, timezone
from typing import Dict, Any, List

import signal
signal.signal(signal.SIGTERM, lambda s, f: sys.exit(0))
signal.signal(signal.SIGINT, lambda s, f: sys.exit(0))


BASE_URL = "https://southausarchive.github.io/public-works-committee"
COMMITTEE_PORTAL = "https://committees.parliament.sa.gov.au/committee/451/Public%20Works%20Committee/56/56th%20Parliament%2005%2F05%2F2026%20-%20Current/56"
COMMITTEE_ID = 451
API_BASE = "https://committees-api.parliament.sa.gov.au/api"

def format_bytes(b: int) -> str:
    if not b:
        return "Unknown size"
    k = 1024
    sizes = ["B", "KB", "MB", "GB"]
    import math
    i = int(math.floor(math.log(b) / math.log(k))) if b > 0 else 0
    return f"{(b / (k**i)):.1f} {sizes[i]}"

DOCUMENT_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{page_title}</title>
  <meta name="description" content="{meta_description}">
  <link rel="canonical" href="{canonical_url}">
  
  <!-- OpenGraph / Social Meta -->
  <meta property="og:title" content="{escaped_title}">
  <meta property="og:description" content="{meta_description}">
  <meta property="og:url" content="{canonical_url}">
  <meta property="og:type" content="article">
  <meta property="og:site_name" content="SA Parliament Public Works Committee Archive">

  <!-- Dublin Core Archival Metadata for Internet Archive / Wayback Machine -->
  <meta name="DC.title" content="{escaped_title}">
  <meta name="DC.creator" content="Parliament of South Australia Public Works Committee">
  <meta name="DC.date" content="{date_display}">
  <meta name="DC.format" content="application/pdf">
  <meta name="DC.identifier" content="{canonical_url}">

  <!-- Schema.org JSON-LD for Search Engines -->
  <script type="application/ld+json">
  {schema_json}
  </script>

  <!-- Enclosure hint for web crawlers and archival indexers -->
  {crawler_enclosures}

  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
  <style>
    :root {{
      --bg: #0d1117;
      --card-bg: #161b22;
      --border: #30363d;
      --text-main: #c9d1d9;
      --text-muted: #8b949e;
      --heading: #f0f6fc;
      --primary: #58a6ff;
      --accent-live: #238636;
      --accent-live-hover: #2ea043;
      --accent-archive: #1f6feb;
      --accent-archive-hover: #388bfd;
      --radius: 8px;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      background-color: var(--bg);
      color: var(--text-main);
      line-height: 1.6;
      padding: 2rem 1rem;
    }}
    .container {{
      max-width: 850px;
      margin: 0 auto;
    }}
    .breadcrumb {{
      font-size: 0.85rem;
      color: var(--text-muted);
      margin-bottom: 1.5rem;
    }}
    .breadcrumb a {{ color: var(--primary); text-decoration: none; }}
    .breadcrumb a:hover {{ text-decoration: underline; }}
    .card {{
      background: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      padding: 2rem;
      margin-bottom: 2rem;
      box-shadow: 0 4px 12px rgba(0,0,0,0.15);
    }}
    h1 {{
      font-size: 1.5rem;
      color: var(--heading);
      margin-bottom: 0.5rem;
      line-height: 1.3;
      word-break: break-word;
    }}
    .meta-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
      gap: 1.25rem;
      margin: 1.75rem 0;
      padding: 1.25rem 0;
      border-top: 1px solid var(--border);
      border-bottom: 1px solid var(--border);
    }}
    .meta-item-label {{
      font-size: 0.75rem;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      color: var(--text-muted);
      margin-bottom: 0.25rem;
    }}
    .meta-item-value {{
      font-weight: 500;
      color: var(--heading);
      font-size: 0.95rem;
    }}
    .meta-hash {{
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.8rem;
      color: var(--text-muted);
      word-break: break-all;
      background: rgba(0,0,0,0.25);
      padding: 0.5rem 0.75rem;
      border-radius: 4px;
      border: 1px solid var(--border);
      margin-top: 0.5rem;
    }}
    .download-action {{
      display: flex;
      flex-wrap: wrap;
      gap: 0.85rem;
      margin-top: 1.5rem;
    }}
    .btn-download-live {{
      background: var(--accent-live);
      color: #fff;
      padding: 0.75rem 1.25rem;
      border-radius: 6px;
      font-weight: 600;
      font-size: 0.9rem;
      text-decoration: none;
      display: inline-flex;
      align-items: center;
      gap: 0.5rem;
      transition: background 0.15s ease;
    }}
    .btn-download-live:hover {{ background: var(--accent-live-hover); }}
    .btn-download-archive {{
      background: var(--accent-archive);
      color: #fff;
      padding: 0.75rem 1.25rem;
      border-radius: 6px;
      font-weight: 600;
      font-size: 0.9rem;
      text-decoration: none;
      display: inline-flex;
      align-items: center;
      gap: 0.5rem;
      transition: background 0.15s ease;
    }}
    .btn-download-archive:hover {{ background: var(--accent-archive-hover); }}
    .btn-portal {{
      background: transparent;
      border: 1px solid var(--border);
      color: var(--text-main);
      padding: 0.75rem 1.25rem;
      border-radius: 6px;
      font-weight: 500;
      font-size: 0.9rem;
      text-decoration: none;
      display: inline-flex;
      align-items: center;
      gap: 0.5rem;
      transition: all 0.15s ease;
    }}
    .btn-portal:hover {{ background: #30363d; color: var(--heading); }}
    
    footer {{
      margin-top: 3rem;
      text-align: center;
      font-size: 0.85rem;
      color: var(--text-muted);
      border-top: 1px solid var(--border);
      padding-top: 1.5rem;
    }}
    footer a {{ color: var(--primary); text-decoration: none; }}
  </style>
</head>
<body>
  <div class="container">
    <div class="breadcrumb">
      <a href="{base_url}/">Home</a> &rsaquo; <span>{breadcrumb_folder}</span> &rsaquo; <span>Document</span>
    </div>

    <div class="card">
      <h1>{escaped_title}</h1>
      <p style="color:var(--text-muted);">Parliament of South Australia &bull; Public Works Committee (56th Parliament)</p>

      <div class="meta-grid">
        <div>
          <div class="meta-item-label">Category / Inquiry</div>
          <div class="meta-item-value">{folder_display}</div>
        </div>
        <div>
          <div class="meta-item-label">File Format</div>
          <div class="meta-item-value">{ext_display}</div>
        </div>
        <div>
          <div class="meta-item-label">File Size</div>
          <div class="meta-item-value">{size_display}</div>
        </div>
        <div>
          <div class="meta-item-label">Modified Date</div>
          <div class="meta-item-value">{date_display}</div>
        </div>
      </div>

      <div>
        <div class="meta-item-label">Document Verification (SHA-256 Fingerprint)</div>
        <div class="meta-hash">{sha256_display}</div>
      </div>

      <div class="download-action">
        <a class="btn-download-live" href="{live_resolver_url}" target="_blank" rel="noopener noreferrer">
          ⚡ Download Live Version
        </a>
        {archive_button_html}
        <a href="{committee_portal}" target="_blank" rel="noopener" class="btn-portal">
          🏛️ View on Committee Portal ↗
        </a>
      </div>
    </div>

    <footer>
      <p><a href="{base_url}/">&larr; Back to Searchable Catalog</a> &bull; <a href="{base_url}/archive-index.html">Permanent Document Index</a></p>
      <p style="margin-top:0.5rem;">Archive managed for public research • Source: Parliament of South Australia</p>
    </footer>
  </div>
</body>
</html>
"""

RESOLVER_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Opening: {escaped_title}</title>
  <meta http-equiv="refresh" content="0; url={target_url}">
  <link rel="canonical" href="{canonical_url}">
  <script>
    window.location.replace("{target_url_escaped}");
  </script>
  <style>
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      background: #0d1117;
      color: #c9d1d9;
      display: flex;
      align-items: center;
      justify-content: center;
      height: 100vh;
      margin: 0;
      text-align: center;
      padding: 1rem;
    }}
    .box {{
      background: #161b22;
      border: 1px solid #30363d;
      padding: 2rem;
      border-radius: 8px;
      max-width: 500px;
    }}
    a {{ color: #58a6ff; text-decoration: none; font-weight: 600; }}
    a:hover {{ text-decoration: underline; }}
  </style>
</head>
<body>
  <div class="box">
    <h2>Redirecting to Document...</h2>
    <p style="margin: 1rem 0; color: #8b949e;">If your download does not begin automatically, please click below:</p>
    <p><a href="{target_url}">⬇ Download {escaped_title}</a></p>
    <p style="margin-top: 1.5rem; font-size: 0.85rem;"><a href="{canonical_url}">&larr; View Document Details & Metadata</a></p>
  </div>
</body>
</html>
"""

ARCHIVE_INDEX_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Permanent Document Index - SA Parliament Public Works Committee Archive</title>
  <meta name="description" content="Complete static directory listing of all public submissions and inquiries from the South Australia Public Works Committee. Optimized for archival crawlers and research.">
  <link rel="canonical" href="{base_url}/archive-index.html">
  <style>
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      background: #0d1117;
      color: #c9d1d9;
      line-height: 1.6;
      padding: 2rem 1rem;
    }}
    .container {{ max-width: 1000px; margin: 0 auto; }}
    h1 {{ color: #f0f6fc; margin-bottom: 0.5rem; }}
    .subtitle {{ color: #8b949e; margin-bottom: 2rem; }}
    table {{ width: 100%; border-collapse: collapse; margin-top: 1rem; background: #161b22; border: 1px solid #30363d; border-radius: 6px; overflow: hidden; }}
    th, td {{ padding: 0.75rem 1rem; text-align: left; border-bottom: 1px solid #30363d; font-size: 0.875rem; }}
    th {{ background: #21262d; color: #f0f6fc; font-weight: 600; }}
    tr:hover td {{ background: rgba(255,255,255,0.02); }}
    a {{ color: #58a6ff; text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    .badge {{ font-family: monospace; font-size: 0.8rem; background: rgba(255,255,255,0.05); padding: 0.15rem 0.4rem; border-radius: 3px; }}
    footer {{ margin-top: 3rem; text-align: center; color: #8b949e; font-size: 0.85rem; border-top: 1px solid #30363d; padding-top: 1.5rem; }}
  </style>
</head>
<body>
  <div class="container">
    <h1>Permanent Document Archive Directory</h1>
    <p class="subtitle">Complete crawlable listing of all {total_count} documents &bull; Optimized for Internet Archive (Wayback Machine) and researchers</p>
    <p><a href="{base_url}/">&larr; Switch to Interactive Search & Filter Catalog</a></p>

    <table>
      <thead>
        <tr>
          <th>Category / Folder</th>
          <th>Document Title</th>
          <th>Format</th>
          <th>Size</th>
          <th>Live Source</th>
          <th>Permanent Archive</th>
        </tr>
      </thead>
      <tbody>
        {table_rows}
      </tbody>
    </table>

    <footer>
      <p>South Australia Public Works Committee Archive &bull; <a href="{base_url}/">Home</a> &bull; <a href="{base_url}/sitemap.xml">XML Sitemap</a></p>
    </footer>
  </div>
</body>
</html>
"""

def generate_seo_assets(manifest_path: str = "data/manifest.json",
                        catalog_path: str = "public/data/catalog.json",
                        output_dir: str = "public"):
    # Load document records preferring manifest (which has archive hash data) or catalog.json
    docs_map = {}
    if os.path.exists(manifest_path):
        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                manifest_data = json.load(f)
                docs_map = manifest_data.get("documents", {})
        except Exception as e:
            sys.stderr.write(f"Warning reading manifest: {e}\n")

    if not docs_map and os.path.exists(catalog_path):
        try:
            with open(catalog_path, "r", encoding="utf-8") as f:
                cat_data = json.load(f)
                docs = cat_data.get("documents", [])
                docs_map = {d["id"]: d for d in docs if "id" in d}
        except Exception as e:
            sys.stderr.write(f"Warning reading catalog: {e}\n")

    if not docs_map:
        sys.stderr.write(f"Error: No documents found to generate SEO and resolver assets.\n")
        return

    docs = list(docs_map.values())
    docs_dir = os.path.join(output_dir, "documents")
    download_dir = os.path.join(output_dir, "download")
    os.makedirs(docs_dir, exist_ok=True)
    os.makedirs(download_dir, exist_ok=True)

    sitemap_urls = [
        {"loc": f"{BASE_URL}/", "lastmod": datetime.now(timezone.utc).strftime("%Y-%m-%d"), "priority": "1.0"},
        {"loc": f"{BASE_URL}/archive-index.html", "lastmod": datetime.now(timezone.utc).strftime("%Y-%m-%d"), "priority": "0.9"}
    ]

    sys.stderr.write(f"Generating landing pages and live resolvers for {len(docs)} documents...\n")
    archive_rows = []

    for doc in docs:
        file_id = doc.get("id")
        file_name = doc.get("name", "Document")
        clean_title = os.path.splitext(file_name)[0]
        folder = doc.get("folder_path") or "General"
        ext = doc.get("extension") or os.path.splitext(file_name)[1]
        size_bytes = doc.get("size_bytes", 0)
        size_str = format_bytes(size_bytes)
        mod_date = (doc.get("last_modified") or "")[:10]
        download_url = doc.get("download_url") or doc.get("direct_api_url") or COMMITTEE_PORTAL

        archive_meta = doc.get("archive", {})
        release_url = archive_meta.get("release_url")
        sha256_hash = archive_meta.get("sha256") or "Computed during GitHub Release sync"

        canonical_url = f"{BASE_URL}/documents/{file_id}.html"
        live_resolver_url = f"{BASE_URL}/download/{file_id}.html"

        # Crawler enclosure hints
        enclosures = []
        if release_url:
            enclosures.append(f'<link rel="enclosure" type="application/pdf" href="{release_url}">')
        if download_url and "blob.core.windows.net" in download_url:
            enclosures.append(f'<link rel="enclosure" type="application/pdf" href="{download_url}">')
        crawler_enclosures = "\n  ".join(enclosures)

        # Archive button
        if release_url:
            archive_button_html = f'<a class="btn-download-archive" href="{release_url}" target="_blank" rel="noopener noreferrer">📦 Permanent Archive (PDF)</a>'
        else:
            archive_button_html = f'<a class="btn-download-archive" href="{live_resolver_url}" target="_blank" rel="noopener noreferrer">📦 Permanent Live Link</a>'

        page_title = f"{file_name} - SA Parliament Public Works Committee Archive"
        meta_desc = f"Public document submission: {file_name} in category '{folder}'. South Australia Parliament Public Works Committee."

        schema = {
            "@context": "https://schema.org",
            "@type": "GovernmentPermit",
            "name": file_name,
            "description": meta_desc,
            "dateModified": mod_date if mod_date else None,
            "url": canonical_url,
            "publisher": {
                "@type": "GovernmentOrganization",
                "name": "South Australia Public Works Committee",
                "url": "https://committees.parliament.sa.gov.au"
            }
        }

        # 1. Generate Static Landing Page
        html_content = DOCUMENT_TEMPLATE.format(
            page_title=html.escape(page_title),
            meta_description=html.escape(meta_desc),
            canonical_url=canonical_url,
            escaped_title=html.escape(file_name),
            schema_json=json.dumps(schema, indent=2),
            base_url=BASE_URL,
            breadcrumb_folder=html.escape(folder),
            folder_display=html.escape(folder),
            ext_display=html.escape(ext.upper().lstrip('.')),
            size_display=html.escape(size_str),
            date_display=html.escape(mod_date or "Unknown"),
            sha256_display=html.escape(sha256_hash),
            file_id=file_id,
            live_resolver_url=live_resolver_url,
            archive_button_html=archive_button_html,
            crawler_enclosures=crawler_enclosures,
            committee_portal=COMMITTEE_PORTAL
        )

        doc_html_path = os.path.join(docs_dir, f"{file_id}.html")
        with open(doc_html_path, "w", encoding="utf-8") as f:
            f.write(html_content)

        # 2. Generate Solution A Live Resolver Page (/download/{id}.html)
        target_live_url = download_url
        resolver_content = RESOLVER_TEMPLATE.format(
            escaped_title=html.escape(file_name),
            target_url=html.escape(target_live_url),
            target_url_escaped=target_live_url.replace('"', '\\"'),
            canonical_url=canonical_url
        )
        resolver_path = os.path.join(download_dir, f"{file_id}.html")
        with open(resolver_path, "w", encoding="utf-8") as f:
            f.write(resolver_content)

        # 3. Add row for Archive Directory
        perm_archive_link = f'<a href="{release_url}">Download PDF</a>' if release_url else '-'
        archive_rows.append(
            f"<tr>"
            f"<td><code>{html.escape(folder)}</code></td>"
            f"<td><a href='documents/{file_id}.html'><strong>{html.escape(file_name)}</strong></a></td>"
            f"<td><span class='badge'>{html.escape(ext)}</span></td>"
            f"<td>{html.escape(size_str)}</td>"
            f"<td><a href='download/{file_id}.html'>Live Resolver</a></td>"
            f"<td>{perm_archive_link}</td>"
            f"</tr>"
        )

        sitemap_urls.append({
            "loc": canonical_url,
            "lastmod": mod_date if len(mod_date) == 10 else datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "priority": "0.8"
        })
        sitemap_urls.append({
            "loc": live_resolver_url,
            "lastmod": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "priority": "0.7"
        })

    # 4. Generate Archive Index Page (archive-index.html)
    archive_index_content = ARCHIVE_INDEX_TEMPLATE.format(
        base_url=BASE_URL,
        total_count=len(docs),
        table_rows="\n        ".join(archive_rows)
    )
    with open(os.path.join(output_dir, "archive-index.html"), "w", encoding="utf-8") as f:
        f.write(archive_index_content)
    sys.stderr.write(f"Saved crawlable archive index to {os.path.join(output_dir, 'archive-index.html')}\n")

    # 5. Generate sitemap.xml
    sitemap_lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
    ]
    for item in sitemap_urls:
        sitemap_lines.append("  <url>")
        sitemap_lines.append(f"    <loc>{item['loc']}</loc>")
        sitemap_lines.append(f"    <lastmod>{item['lastmod']}</lastmod>")
        sitemap_lines.append(f"    <priority>{item['priority']}</priority>")
        sitemap_lines.append("  </url>")
    sitemap_lines.append("</urlset>")

    sitemap_path = os.path.join(output_dir, "sitemap.xml")
    with open(sitemap_path, "w", encoding="utf-8") as f:
        f.write("\n".join(sitemap_lines) + "\n")
    sys.stderr.write(f"Saved sitemap with {len(sitemap_urls)} entries to {sitemap_path}\n")

    # 6. Generate robots.txt
    robots_content = f"""User-agent: *
Allow: /

User-agent: ia_archiver
Allow: /

User-agent: archive.org_bot
Allow: /

Sitemap: {BASE_URL}/sitemap.xml
"""
    robots_path = os.path.join(output_dir, "robots.txt")
    with open(robots_path, "w", encoding="utf-8") as f:
        f.write(robots_content)
    sys.stderr.write(f"Saved robots.txt to {robots_path}\n")

if __name__ == "__main__":
    generate_seo_assets()
