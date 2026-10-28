# South Australia Parliament - Public Works Committee Document Catalog

An automated, serverless scraper and interactive catalog running entirely for free on **GitHub Actions** and hosted on **GitHub Pages**.

It crawls and indexes all documents from the [South Australia Parliament Public Works Committee Portal](https://committees.parliament.sa.gov.au/committee/451/Public%20Works%20Committee/56/56th%20Parliament%2005%2F05%2F2026%20-%20Current/56), provides direct document access, and presents a responsive search engine with both Table View and interactive Tree View.

---

## Features

- **Automated Cloud Scraping**: Runs via GitHub Actions weekly (`cron`) or on-demand (`workflow_dispatch`).
- **Interactive Directory Hierarchy**: Full collapsible tree view organizing files into categories, inquiries, submissions, and reports.
- **Fast Client-Side Search**: Filter documents instantaneously by name, topic, or subfolder.
- **Always-Accessible Document Links**: Downloads dynamically generate fresh, unexpired access tokens on click with automatic fallback.
- **Open Data & Markdown Catalog**: Maintains a complete document list in [`CATALOG.md`](CATALOG.md) and machine-readable JSON in `public/data/catalog.json`.

---

## Local Development & Testing

### Scrape Catalog Locally
```bash
# Scrape the first 20 files
python3 scrape_catalog.py --limit 20

# Scrape all committee files
python3 scrape_catalog.py --limit 0
```

### Preview Static Site Locally
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
│       └── scrape-and-archive.yml   # Scheduled & manual GitHub Actions workflow
├── data/
│   └── manifest.json                # Persistent index of all discovered documents
├── public/
│   ├── index.html                   # Searchable catalog application (GitHub Pages)
│   └── data/
│       └── catalog.json             # Structured document index and folder tree
├── scrape_catalog.py                # Core scraping engine
├── CATALOG.md                       # Auto-generated Markdown catalog table
└── README.md                        # Documentation
```
