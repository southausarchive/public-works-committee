#!/usr/bin/env python3
"""
SEO & Static Page Generator for SA Parliament Public Works Committee Archive.
- Generates dedicated static HTML landing pages for every document (/documents/{id}.html).
- Embeds Schema.org (JSON-LD) structured metadata for Google Rich Results.
- Creates XML sitemap (sitemap.xml) and robots.txt for Googlebot crawler discovery.
- Includes client-side token renewal for seamless file access.
"""

import os
import sys
import json
import re
import html
from datetime import datetime, timezone
from typing import Dict, Any, List

BASE_URL = "https://southausarchive.github.io/public-works-committee"
COMMITTEE_PORTAL = "https://committees.parliament.sa.gov.au/committee/451/Public%20Works%20Committee/56/56th%20Parliament%2005%2F05%2F2026%20-%20Current/56"
COMMITTEE_ID = 451
API_BASE = "https://committees-api.parliament.sa.gov.au/api"

def slugify(text: str) -> str:
    text = re.sub(r'[^a-zA-Z0-9_\-\s]', '', text)
    text = re.sub(r'[\s_]+', '-', text.strip())
    return text.lower()[:80]

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

  <!-- Schema.org JSON-LD for Googlebot -->
  <script type="application/ld+json">
  {schema_json}
  </script>

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
      --accent: #238636;
      --accent-hover: #2ea043;
      --badge-bg: #21262d;
      --folder-color: #f1e05a;
      --font-sans: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      --font-mono: 'JetBrains Mono', monospace;
    }}

    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      background-color: var(--bg);
      color: var(--text-main);
      font-family: var(--font-sans);
      line-height: 1.6;
      padding: 2rem 1rem;
    }}
    .container {{
      max-width: 900px;
      margin: 0 auto;
    }}
    .breadcrumb {{
      font-size: 0.88rem;
      margin-bottom: 1.5rem;
      color: var(--text-muted);
    }}
    .breadcrumb a {{
      color: var(--primary);
      text-decoration: none;
    }}
    .breadcrumb a:hover {{ text-decoration: underline; }}
    
    .card {{
      background: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 2rem;
      margin-bottom: 2rem;
    }}
    h1 {{
      font-size: 1.65rem;
      color: var(--heading);
      margin-bottom: 0.75rem;
      line-height: 1.3;
    }}
    .meta-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
      gap: 1.25rem;
      margin: 1.5rem 0;
      padding: 1.25rem;
      background: rgba(255, 255, 255, 0.02);
      border: 1px solid var(--border);
      border-radius: 6px;
    }}
    .meta-item-label {{
      font-size: 0.75rem;
      text-transform: uppercase;
      letter-spacing: 0.04em;
      color: var(--text-muted);
      margin-bottom: 0.25rem;
    }}
    .meta-item-value {{
      font-size: 0.95rem;
      color: var(--heading);
      font-weight: 500;
    }}
    .download-action {{
      display: flex;
      gap: 1rem;
      align-items: center;
      flex-wrap: wrap;
      margin-top: 1.75rem;
    }}
    .btn-download {{
      background: var(--accent);
      color: #fff;
      padding: 0.75rem 1.5rem;
      border-radius: 6px;
      text-decoration: none;
      font-weight: 600;
      font-size: 1rem;
      display: inline-flex;
      align-items: center;
      gap: 0.5rem;
      border: none;
      cursor: pointer;
      transition: background 0.2s;
    }}
    .btn-download:hover {{ background: var(--accent-hover); }}
    .btn-download.loading {{ background: #388bfd; cursor: wait; }}
    .btn-portal {{
      background: var(--badge-bg);
      color: var(--text-main);
      padding: 0.75rem 1.25rem;
      border-radius: 6px;
      text-decoration: none;
      font-size: 0.9rem;
      border: 1px solid var(--border);
      transition: background 0.2s;
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

      <div class="download-action">
        <button id="dlBtn" class="btn-download" onclick="triggerDownload()">⬇ Download Document</button>
        <a href="{committee_portal}" target="_blank" rel="noopener" class="btn-portal">🏛️ View on Committee Portal ↗</a>
      </div>
    </div>

    <footer>
      <p><a href="{base_url}/">&larr; Back to Full Document Index</a></p>
      <p style="margin-top:0.5rem;">Archive managed for public research • Source: Parliament of South Australia</p>
    </footer>
  </div>

  <script>
    const FILE_ID = "{file_id}";
    const COMMITTEE_ID = 451;
    const API_BASE = "https://committees-api.parliament.sa.gov.au/api";
    const FALLBACK_URL = "{cached_download_url}";

    async function triggerDownload() {{
      const btn = document.getElementById('dlBtn');
      btn.classList.add('loading');
      btn.textContent = 'Resolving Access Token...';

      try {{
        const resp = await fetch(`${{API_BASE}}/CommitteeFileDownloadLink?committeeId=${{COMMITTEE_ID}}&fileId=${{FILE_ID}}`);
        if (resp.ok) {{
          const data = await resp.json();
          if (data && data.DownloadLink) {{
            window.location.href = data.DownloadLink;
            btn.classList.remove('loading');
            btn.textContent = '⬇ Download Document';
            return;
          }}
        }}
      }} catch(e) {{
        console.warn('Direct token acquisition failed, attempting cached link', e);
      }}

      if (FALLBACK_URL) {{
        window.location.href = FALLBACK_URL;
      }} else {{
        window.open("{committee_portal}", "_blank");
      }}
      btn.classList.remove('loading');
      btn.textContent = '⬇ Download Document';
    }}
  </script>
</body>
</html>
"""

def generate_seo_assets(catalog_path: str = "public/data/catalog.json", output_dir: str = "public"):
    if not os.path.exists(catalog_path):
        sys.stderr.write(f"Error: {catalog_path} not found.\n")
        return

    with open(catalog_path, "r", encoding="utf-8") as f:
        catalog = json.load(f)

    docs = catalog.get("documents", [])
    docs_dir = os.path.join(output_dir, "documents")
    os.makedirs(docs_dir, exist_ok=True)

    sitemap_urls = [
        {"loc": f"{BASE_URL}/", "lastmod": datetime.now(timezone.utc).strftime("%Y-%m-%d"), "priority": "1.0"}
    ]

    sys.stderr.write(f"Generating static landing pages for {len(docs)} documents...\n")

    for doc in docs:
        file_id = doc.get("id")
        file_name = doc.get("name", "Document")
        clean_title = os.path.splitext(file_name)[0]
        folder = doc.get("folder_path") or "General"
        ext = doc.get("extension") or os.path.splitext(file_name)[1]
        size_bytes = doc.get("size_bytes", 0)
        size_str = format_bytes(size_bytes)
        mod_date = doc.get("last_modified", "")[:10] or doc.get("discovered_at", "")[:10] or "Unknown"

        canonical_url = f"{BASE_URL}/documents/{file_id}.html"
        page_title = f"{file_name} - South Australia Public Works Committee"
        meta_desc = f"Public document '{file_name}' ({size_str}, {ext}) published by the South Australia Parliament Public Works Committee in category {folder}."

        schema = {
            "@context": "https://schema.org",
            "@type": "GovernmentPermit",
            "name": file_name,
            "description": meta_desc,
            "url": canonical_url,
            "dateModified": doc.get("last_modified") or datetime.now(timezone.utc).isoformat(),
            "encodingFormat": "application/pdf" if ext.lower() == ".pdf" else "application/octet-stream",
            "publisher": {
                "@type": "GovernmentOrganization",
                "name": "Parliament of South Australia Public Works Committee",
                "url": COMMITTEE_PORTAL
            }
        }

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
            date_display=html.escape(mod_date),
            file_id=file_id,
            cached_download_url=doc.get("download_url") or "",
            committee_portal=COMMITTEE_PORTAL
        )

        doc_html_path = os.path.join(docs_dir, f"{file_id}.html")
        with open(doc_html_path, "w", encoding="utf-8") as f:
            f.write(html_content)

        sitemap_urls.append({
            "loc": canonical_url,
            "lastmod": mod_date if len(mod_date) == 10 else datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "priority": "0.8"
        })

    # Generate sitemap.xml
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

    # Generate robots.txt
    robots_content = f"""User-agent: *
Allow: /

Sitemap: {BASE_URL}/sitemap.xml
"""
    robots_path = os.path.join(output_dir, "robots.txt")
    with open(robots_path, "w", encoding="utf-8") as f:
        f.write(robots_content)
    sys.stderr.write(f"Saved robots.txt to {robots_path}\n")

if __name__ == "__main__":
    generate_seo_assets()
