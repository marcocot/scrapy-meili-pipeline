# 🕷️ Scrapy → Meilisearch Pipeline

[![PyPI](https://img.shields.io/pypi/v/scrapy-meili-pipeline.svg?style=flat-square)](https://pypi.org/project/scrapy-meili-pipeline/)
[![CI](https://github.com/marcocot/scrapy-meili-pipeline/actions/workflows/ci.yml/badge.svg)](https://github.com/marcocot/scrapy-meili-pipeline/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg?style=flat-square)](LICENSE)

A Scrapy pipeline that **batches** items and indexes them into **Meilisearch**, with optional index creation and index settings using the **modern Meilisearch Python client**.

---

## ✨ Features

- ✅ Uses the official **modern** Meilisearch client (TaskInfo / Pydantic models)
- 🧰 Optional **index creation** (with `primaryKey`) and **index settings** update
- 📦 **Batching** of items before insertion
- 🔎 Task tracking with **status check** (failed tasks are logged and stored)
- 🧪 Example Scrapy project + Docker Compose for Meilisearch
- 🧹 Tooling: `uv`, `pytest`, `ruff`, `black`, `mypy`, `just` tasks

---

## 🧠 How batching works (pipeline logic)

The pipeline keeps **two internal buffers**:

1. `_buffer` → a list of items waiting to be sent to Meilisearch
2. `_tasks` → a list of Meilisearch **TaskInfo** objects created by `add_documents()` and `update_settings()`

Flow:

1. `process_item` converts an item to `dict` and pushes it into `_buffer`.
2. When `_buffer` length reaches **`MEILI_BATCH_SIZE`**, the pipeline performs a **flush**:
   - Sends the whole `_buffer` with `index.add_documents(batch)`
   - Appends the returned **TaskInfo** to `_tasks`
   - Calls **`_check_all_tasks()`**: waits on all tasks in `_tasks` via `wait_for_task()` and
     - if any task ends with `status="failed"`, it is moved to `_failed_tasks`
     - otherwise it is discarded (success) — `_tasks` is cleared
3. `close_spider`:
   - If `_buffer` still has items, a final **flush** is executed (and tasks checked)
   - If `_tasks` still contains tasks (e.g., settings only), they are **checked**
   - If any failed tasks were detected, they are **logged** (no exception is raised by design)

Benefits of this approach:
- Minimal memory use (bounded by `MEILI_BATCH_SIZE`)
- Early surfacing of Meilisearch task failures during the crawl
- Predictable and simple control flow

---

## 📦 Installation

From PyPI:

```bash
pip install scrapy-meili-pipeline
```

Using **uv**:

```bash
uv add scrapy-meili-pipeline
```

---

## ⚙️ Settings

Add the pipeline to Scrapy and configure Meilisearch via settings:

```python
ITEM_PIPELINES = {
    "scrapy_meili_pipeline.MeiliSearchPipeline": 300,
}

MEILI_URL = "http://127.0.0.1:7700"
MEILI_API_KEY = "masterKey"          # or None
MEILI_INDEX = "articles"             # required
MEILI_PRIMARY_KEY = "id"             # optional

MEILI_INDEX_SETTINGS = {             # optional
    "filterableAttributes": ["author", "categories", "keywords", "rating"],
    "sortableAttributes": ["published_at", "rating"],
    "searchableAttributes": ["title", "summary", "content", "keywords"],
}

MEILI_BATCH_SIZE = 500
MEILI_TASK_TIMEOUT = 180
MEILI_TASK_INTERVAL = 1
```

> This library supports **ONLY** the modern Meilisearch client and expects TaskInfo objects with a `task_uid` attribute.

---

## 🚀 Quick example (Scrapy spider)

```python
class ArticleSpider(Spider):
    name = "articles"

    custom_settings = {
        "MEILI_INDEX": "news",
        "MEILI_BATCH_SIZE": 200,
        "MEILI_INDEX_SETTINGS": {"filterableAttributes": ["site", "tags"]},
    }

    def parse(self, response):
        yield {
            "id": response.url,
            "title": response.css("h1::text").get(),
            "author": response.css(".author::text").get(),
            "content": response.css("article::text").getall(),
            "rating": 4,
        }
```

---

## 🧪 Example project & Meilisearch (examples/)

This repo ships with a **runnable example** under `examples/` that scrapes the public test site
**https://webscraper.io/test-sites/e-commerce/allinone** and indexes product tiles into Meilisearch.

### Start Meilisearch with Docker

```bash
cd examples
docker compose up -d
```

Meilisearch UI: http://127.0.0.1:7700

### Run the example spider (via Just)

From the repository root:

```bash
just example
```

What the `example` task does:
- switches to `examples/simple_project`
- runs `scrapy crawl demo -s LOG_LEVEL=INFO`

If you prefer running it manually:

```bash
cd examples/simple_project
uv run scrapy crawl demo -s LOG_LEVEL=INFO
```

---

## 🧱 Project structure

```
scrapy-meili-pipeline/
├── src/
│   └── scrapy_meili_pipeline/
│       ├── __init__.py
│       └── meili_pipeline.py
├── tests/
│   └── test_pipeline.py
├── examples/
│   ├── README.md
│   ├── .env.example
│   ├── docker-compose.meilisearch.yml
│   └── simple_project/
│       ├── scrapy.cfg
│       └── simple_project/
│           ├── __init__.py
│           ├── settings.py
│           ├── sitecustomize.py
│           └── spiders/
│               └── demo_spider.py
├── Justfile
├── pyproject.toml
├── README.md
├── LICENSE
└── .github/
    └── workflows/
        ├── ci.yml
        └── publish.yml
```

---

## 🛠️ Development

Using **uv** + **just**:

```bash
just sync            # install all deps (dev included)
just check           # ruff + black --check + mypy + pytest
just test            # run unit tests
just coverage        # terminal coverage
just coverage-html   # HTML coverage at ./htmlcov/index.html
just build           # build wheel + sdist (uv build)
just publish         # publish to PyPI (uv publish)
```

Manual (without just):

```bash
uv sync --all-extras --dev
uv run ruff check .
uv run black --check .
uv run mypy .
uv run pytest
uv run pytest --cov=src --cov-report=html
uv build
uv publish
```

---

## 📜 License

Released under the [MIT License](LICENSE).
