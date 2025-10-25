from __future__ import annotations

BOT_NAME = "simple_project"

SPIDER_MODULES = ["simple_project.spiders"]
NEWSPIDER_MODULE = "simple_project.spiders"

# Log
LOG_LEVEL = "INFO"

# Respect robots? (example demo spider is synthetic, no network I/O)
ROBOTSTXT_OBEY = False

# --- Pipeline configuration (reads from environment) ---
ITEM_PIPELINES = {
    "scrapy_meili_pipeline.MeiliSearchPipeline": 100,
}

MEILI_URL = "http://127.0.0.1:7700"
MEILI_API_KEY = "masterkey"
MEILI_INDEX = "products"
MEILI_PRIMARY_KEY = "id"

# Example index settings
MEILI_INDEX_SETTINGS = {
    "filterableAttributes": ["author", "categories", "rating"],
    "sortableAttributes": ["published_at", "rating"],
    "searchableAttributes": ["title", "summary", "content", "keywords"],
}

# Small batch to see multiple add_documents calls in logs
MEILI_BATCH_SIZE = 3
MEILI_WAIT_FOR_TASKS = True  # wait for tasks at spider close
MEILI_TASK_TIMEOUT = 30
MEILI_TASK_INTERVAL = 1
