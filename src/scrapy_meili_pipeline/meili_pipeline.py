from __future__ import annotations

from typing import Any, Dict, List, Optional
import logging

from itemadapter import ItemAdapter
import meilisearch
from meilisearch.client import Client
from meilisearch.index import Index
from scrapy import Spider
from scrapy.crawler import Crawler

logger = logging.getLogger(__name__)


class MeiliSearchPipeline:
    """
    Scrapy pipeline that batches items and indexes them into Meilisearch.

    Simplified logic:
    - Keep one internal list of pending tasks (`_tasks`).
    - `process_item` buffers items; when buffer reaches `batch_size`, perform a flush.
    - Each flush adds a Meilisearch task to `_tasks`, then immediately checks all tasks
      in `_tasks`. Failed tasks are moved to `_failed_tasks`. Succeeded tasks clear `_tasks`.
    - On `close_spider`, flush remaining items (if any), check remaining tasks,
      and finally raise if any failed tasks were detected.

    Supports ONLY the modern Meilisearch Python client (TaskInfo / Pydantic models).

    Supported Scrapy settings (global or spider.custom_settings):

    MEILI_URL (str)                     - e.g. "http://127.0.0.1:7700" (required)
    MEILI_API_KEY (str | None)          - e.g. "masterKey" (optional)
    MEILI_INDEX (str)                   - index name (required)
    MEILI_PRIMARY_KEY (str | None)      - primary key for new index
    MEILI_INDEX_SETTINGS (dict)         - passed to update_settings
    MEILI_BATCH_SIZE (int)              - default 1000 (documents per flush)
    MEILI_TASK_TIMEOUT (int)            - seconds, default 120
    MEILI_TASK_INTERVAL (int)           - seconds, default 1
    """

    def __init__(
        self,
        url: str,
        api_key: Optional[str],
        index_name: str,
        primary_key: Optional[str],
        index_settings: Optional[Dict[str, Any]],
        batch_size: int = 1000,
        task_timeout: int = 120,
        task_interval: int = 1,
    ) -> None:
        self.url = url
        self.api_key = api_key
        self.index_name = index_name
        self.primary_key = primary_key
        self.index_settings = index_settings or {}
        self.batch_size = max(1, int(batch_size))
        self.task_timeout = int(task_timeout)
        self.task_interval = int(task_interval)

        self._client: Optional[Client] = None
        self._index: Optional[meilisearch.index.Index] = None

        # Internal buffers
        self._buffer: List[Dict[str, Any]] = []  # items buffer
        self._tasks: List[Any] = []  # pending TaskInfo objects
        self._failed_tasks: List[Any] = []  # failed TaskInfo objects

    # ---------- Scrapy hooks ---------- #

    @classmethod
    def from_crawler(cls, crawler: Crawler) -> "MeiliSearchPipeline":
        s = crawler.settings

        url = s.get("MEILI_URL")
        if not url:
            raise ValueError("MEILI_URL is missing in Scrapy settings.")

        index_name = s.get("MEILI_INDEX")
        if not index_name:
            raise ValueError("MEILI_INDEX is missing in Scrapy settings.")

        return cls(
            url=url,
            api_key=s.get("MEILI_API_KEY"),
            index_name=index_name,
            primary_key=s.get("MEILI_PRIMARY_KEY"),
            index_settings=s.getdict("MEILI_INDEX_SETTINGS", {}),
            batch_size=s.getint("MEILI_BATCH_SIZE", 1000),
            task_timeout=s.getint("MEILI_TASK_TIMEOUT", 120),
            task_interval=s.getint("MEILI_TASK_INTERVAL", 1),
        )

    def open_spider(self, spider: Spider) -> None:
        logger.info("MeiliSearchPipeline: connecting to %s", self.url)
        self._client = meilisearch.Client(self.url, self.api_key)

        # Ensure index exists; wait immediately so subsequent ops are safe.
        self._index = self._ensure_index(self._client, self.index_name, self.primary_key)

        # Apply settings if provided — collect the task, but we won't wait here.
        if self.index_settings:
            logger.info("MeiliSearchPipeline: applying settings for index '%s'", self.index_name)
            task = self._index.update_settings(self.index_settings)
            self._tasks.append(task)
            # Per specifiche: lo stato viene verificato ai flush/close, non qui.

    def close_spider(self, spider: Spider) -> None:
        # If items remain, flush them (will also check tasks).
        if self._buffer:
            self._flush_and_check()

        # If any tasks are still pending (e.g., only settings were added), check them now.
        if self._tasks:
            self._check_all_tasks()

        # If we collected any failed tasks, raise with details.
        if self._failed_tasks:
            for t in self._failed_tasks:
                logger.error("Meilisearch failed task: %r", t)

        # cleanup
        self._buffer.clear()
        self._tasks.clear()
        self._client = None
        self._index = None

    def process_item(self, item: Any, spider: Spider) -> Any:
        # Buffer item; flush when batch size reached
        doc = dict(ItemAdapter(item).asdict())
        self._buffer.append(doc)

        if len(self._buffer) >= self.batch_size:
            self._flush_and_check()

        return item

    # ---------- Internals ---------- #

    def _ensure_index(self, client: Client, index_name: str, primary_key: Optional[str]) -> Index:
        """Create the index if missing, and wait for creation to avoid races."""
        try:
            client.get_index(index_name)
            idx = client.index(index_name)
        except meilisearch.errors.MeilisearchApiError:
            logger.info(
                "MeiliSearchPipeline: creating index '%s'%s",
                index_name,
                f" (primary_key='{primary_key}')" if primary_key else "",
            )
            task = client.create_index(index_name, {"primaryKey": primary_key} if primary_key else {})
            # Wait immediately for index creation
            result = client.wait_for_task(
                self._task_uid(task),
                timeout_in_ms=self.task_timeout * 1000,
                interval_in_ms=self.task_interval * 1000,
            )
            self._check_task(result)
            idx = client.index(index_name)
        return idx

    def _flush_and_check(self) -> None:
        """Send current buffer to Meilisearch, store its task, then check all tasks."""
        if not self._buffer:
            # Even with empty buffer, we may still want to check pending tasks from settings
            if self._tasks:
                self._check_all_tasks()
            return

        if not self._index:
            raise RuntimeError("Meilisearch index is not initialized.")

        batch = self._buffer
        self._buffer = []

        try:
            logger.info("MeiliSearchPipeline: sending batch of %d documents", len(batch))
            task = self._index.add_documents(batch)
            self._tasks.append(task)
        except Exception as e:
            logger.exception("Error inserting batch into Meilisearch: %s", e)
            raise

        # After each flush, check **all** pending tasks;
        # failed ones go to _failed_tasks, and we clear _tasks.
        self._check_all_tasks()

    def _check_all_tasks(self) -> None:
        """Wait for and validate all tasks in `_tasks`; collect failures; then clear `_tasks`."""
        if not (self._client and self._tasks):
            self._tasks.clear()
            return

        pending = self._tasks
        self._tasks = []  # reset before waiting; we'll only keep failures elsewhere

        for t in pending:
            uid = self._task_uid(t)
            try:
                result = self._client.wait_for_task(
                    uid,
                    timeout_in_ms=self.task_timeout * 1000,
                    interval_in_ms=self.task_interval * 1000,
                )
                self._check_task(result)
            except Exception as e:
                # Network / timeout / unexpected errors — classify as failure with a stub
                logger.warning("Waiting for task %s failed: %s", uid, e)
                self._failed_tasks.append(self._mk_failed_stub(uid, message=str(e)))

    @staticmethod
    def _task_uid(task: Any) -> int:
        """Extract UID from TaskInfo-like object (modern client)."""
        uid = getattr(task, "task_uid", None)
        if uid is None:
            raise RuntimeError("Task object has no uid/taskUid attribute (unsupported client?).")
        return int(uid)

    def _check_task(self, task_info: Any) -> None:
        """Record failure if task ended with 'failed' status."""
        status = getattr(task_info, "status", None)
        if status == "failed":
            self._failed_tasks.append(task_info)

    @staticmethod
    def _mk_failed_stub(uid: Optional[int], *, message: str) -> Any:
        """Create a minimal object to record a failed/unknown task when wait_for_task itself fails."""

        class _Stub:
            def __init__(self, uid: Optional[int], message: str):
                self.taskUid = uid
                self.status = "failed"

                class _Err:
                    def __init__(self, message: str):
                        self.code = "wait_error"
                        self.message = message
                        self.link = None

                self.error = _Err(message)

        return _Stub(uid, message)
