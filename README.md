# South Australia Parliament - Public Works Committee Document Archive & Catalog

An automated, serverless pipeline designed to run on **GitHub Actions**. It scrapes and synchronizes documents from the [South Australia Parliament Public Works Committee document repository](https://committees.parliament.sa.gov.au/committee/451/Public%20Works%20Committee/56/56th%20Parliament%2005%2F05%2F2026%20-%20Current/56), preserves them indefinitely on the **[Internet Archive (Archive.org)](https://archive.org)** with rich metadata, and publishes a public, searchable catalog on **GitHub Pages**.

---

## Features

- **Runs 100% Free on GitHub Actions**: Automatically executed on a weekly schedule (`cron`) or manually via the "Run workflow" button.
- **Permanent Archival on Archive.org**: Uploads documents via the official `internetarchive` tool with structured metadata (creator, titles, subjects, parliamentary tags).
- **Incremental & State-Preserving**: Keeps track of already-archived files in `data/manifest.json`. Future runs only inspect and upload new or modified files without re-scraping existing documents.
- **Polite Rate Limiting & Execution Bounds**: Incorporates exponential backoff retries, request pacing, and safety runtime guards (stops cleanly well within GitHub's 6-hour job ceiling).
- **Lightweight GitHub Pages Searchable Catalog**: A zero-dependency, dark-mode web application in `public/index.html` offering instant search, filtering, table view, and tree view.
- **Git-Native Open Catalog**: Generates a human-readable [`CATALOG.md`](CATALOG.md) and machine-readable `public/data/catalog.json`.

---

## Setup Instructions

### 1. Configure Internet Archive Secrets in GitHub

To enable automatic uploads to Archive.org, generate S3 credentials for your Internet Archive account:
1. Log into [Archive.org](https://archive.org) and visit [archive.org/account/s3.php](https://archive.org/account/s3.php).
2. Generate your **Access Key** and **Secret Key**.
3. In your GitHub repository, navigate to:
   **Settings > Secrets and variables > Actions > New repository secret**
4. Add:
   - `IA_ACCESS_KEY`: *Your Internet Archive S3 Access Key*
   - `IA_SECRET_KEY`: *Your Internet Archive S3 Secret Key*

> **Note:** If these secrets are not configured, the workflow automatically runs in **dry-run mode**, updating the catalog and simulating uploads without failing.

### 2. Enable GitHub Pages

1. In your GitHub repository, go to **Settings > Pages**.
2. Under **Build and deployment > Source**, select **GitHub Actions**.
3. Once the workflow completes, your catalog will be publicly accessible at `https://<username>.github.io/<repo-name>/`.

---

## Manual Execution & Local Testing

### Run locally (Dry Run)
```bash
# Test with a limit of 5 documents without uploading to Archive.org
python3 archive_sync.py --limit 5 --dry-run
```

### Full Local Sync (With Archive.org credentials)
```bash
export IA_ACCESS_KEY="your_access_key"
export IA_SECRET_KEY="your_secret_key"
python3 archive_sync.py --limit 0
```

### Preview the Static Catalog Locally
```bash
cd public
python3 -m http.server 8000
# Open http://localhost:8000 in your browser
```

---

## Repository Structure

```
├── .github/
│   └── workflows/
│       └── scrape-and-archive.yml   # Scheduled & manual GitHub Actions pipeline
├── data/
│   └── manifest.json                # State file tracking all archived documents & IDs
├── public/
│   ├── index.html                   # Searchable frontend for GitHub Pages
│   └── data/
│       └── catalog.json             # Flat & tree JSON catalog consumed by frontend
├── archive_sync.py                  # Core scraping, retry, and Archive.org sync engine
├── CATALOG.md                       # Auto-generated Markdown catalog
└── README.md                        # Documentation and setup instructions
```
