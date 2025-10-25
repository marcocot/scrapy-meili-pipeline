from __future__ import annotations

from typing import Any, Dict
from unittest.mock import MagicMock, patch

import pytest
from scrapy import Spider
from scrapy.settings import Settings

from scrapy_meili_pipeline import MeiliSearchPipeline


class ErrorInfoMock:
    def __init__(self, code: str | None, message: str | None, link: str | None = None):
        self.code = code
        self.message = message
        self.link = link


class TaskInfoMock:
    def __init__(self, task_uid: int, status: str = "enqueued", error: ErrorInfoMock | None = None):
        self.task_uid = task_uid
        self.status = status
        self.error = error


class DummySpider(Spider):
    name = "dummy"


def make_settings(overrides: Dict[str, Any] | None = None) -> Settings:
    s = Settings()
    s.set("MEILI_URL", "http://localhost:7700")
    s.set("MEILI_INDEX", "test-index")
    s.set("MEILI_PRIMARY_KEY", "id")
    s.set("MEILI_BATCH_SIZE", 2)
    s.set("MEILI_TASK_TIMEOUT", 1)
    s.set("MEILI_TASK_INTERVAL", 0)
    s.set("MEILI_INDEX_SETTINGS", {"filterableAttributes": ["category", "rating"]})
    if overrides:
        for k, v in overrides.items():
            s.set(k, v)
    return s


# ---------------------------
# Test
# ---------------------------


@patch("scrapy_meili_pipeline.meili_pipeline.meilisearch.Client")
def test_open_spider_creates_index_if_missing(mock_client_cls: MagicMock):
    mock_client = MagicMock()
    mock_index = MagicMock()
    mock_client_cls.return_value = mock_client

    from meilisearch.errors import MeilisearchApiError

    resp = MagicMock()
    resp.status_code = 404
    resp.text = '{"message":"index not found"}'
    resp.json.return_value = {"message": "index not found"}
    mock_client.get_index.side_effect = MeilisearchApiError({"message": "index not found"}, resp)
    mock_client.create_index.return_value = TaskInfoMock(task_uid=111, status="enqueued")
    mock_client.wait_for_task.return_value = TaskInfoMock(task_uid=111, status="succeeded")
    mock_client.index.return_value = mock_index

    s = make_settings()
    pipe = MeiliSearchPipeline.from_crawler(type("C", (), {"settings": s}))
    pipe.open_spider(DummySpider())

    mock_client_cls.assert_called_once_with("http://localhost:7700", None)
    mock_client.create_index.assert_called_once()
    mock_client.wait_for_task.assert_called_once()
    assert pipe._index is mock_index


@patch("scrapy_meili_pipeline.meili_pipeline.meilisearch.Client")
def test_open_spider_applies_index_settings_and_stashes_task(mock_client_cls: MagicMock):
    mock_client = MagicMock()
    mock_index = MagicMock()
    mock_client_cls.return_value = mock_client

    mock_client.get_index.return_value = object()
    mock_client.index.return_value = mock_index
    mock_index.update_settings.return_value = TaskInfoMock(task_uid=222, status="enqueued")

    s = make_settings()
    pipe = MeiliSearchPipeline.from_crawler(type("C", (), {"settings": s}))
    pipe.open_spider(DummySpider())

    assert len(pipe._tasks) == 1
    assert isinstance(pipe._tasks[0], TaskInfoMock)
    assert pipe._tasks[0].task_uid == 222


@patch("scrapy_meili_pipeline.meili_pipeline.meilisearch.Client")
def test_batching_success_flow_no_raise(mock_client_cls: MagicMock, caplog):
    mock_client = MagicMock()
    mock_index = MagicMock()
    mock_client_cls.return_value = mock_client

    mock_client.get_index.return_value = object()
    mock_client.index.return_value = mock_index

    # Task per settings + add_documents
    mock_index.update_settings.return_value = TaskInfoMock(task_uid=10, status="enqueued")
    mock_index.add_documents.return_value = TaskInfoMock(task_uid=123, status="enqueued")

    mock_client.wait_for_task.side_effect = [
        TaskInfoMock(task_uid=10, status="succeeded"),
        TaskInfoMock(task_uid=123, status="succeeded"),
    ]

    s = make_settings({"MEILI_BATCH_SIZE": 2})
    pipe = MeiliSearchPipeline.from_crawler(type("C", (), {"settings": s}))
    spider = DummySpider()
    pipe.open_spider(spider)

    pipe.process_item({"id": 1, "title": "A"}, spider)
    pipe.process_item({"id": 2, "title": "B"}, spider)  # flush + check_all_tasks

    assert pipe._tasks == []
    assert pipe._failed_tasks == []

    pipe.close_spider(spider)


@patch("scrapy_meili_pipeline.meili_pipeline.meilisearch.Client")
def test_failed_task_is_logged_and_no_raise(mock_client_cls: MagicMock, caplog):
    mock_client = MagicMock()
    mock_index = MagicMock()
    mock_client_cls.return_value = mock_client

    mock_client.get_index.return_value = object()
    mock_client.index.return_value = mock_index

    # Task: settings (failed) e batch (succeeded)
    mock_index.update_settings.return_value = TaskInfoMock(task_uid=20, status="enqueued")
    mock_index.add_documents.return_value = TaskInfoMock(task_uid=30, status="enqueued")

    mock_client.wait_for_task.side_effect = [
        TaskInfoMock(task_uid=20, status="failed", error=ErrorInfoMock("ESET", "settings-error")),
        TaskInfoMock(task_uid=30, status="succeeded"),
    ]

    s = make_settings({"MEILI_BATCH_SIZE": 1})
    pipe = MeiliSearchPipeline.from_crawler(type("C", (), {"settings": s}))
    spider = DummySpider()
    pipe.open_spider(spider)

    with caplog.at_level("ERROR"):
        pipe.process_item({"id": 1, "title": "X"}, spider)  # flush -> check_all_tasks

    assert len(pipe._failed_tasks) == 1
    assert pipe._failed_tasks[0].status == "failed"

    with caplog.at_level("ERROR"):
        pipe.close_spider(spider)

    assert any("Meilisearch failed task" in rec.message for rec in caplog.records)


@patch("scrapy_meili_pipeline.meili_pipeline.meilisearch.Client")
def test_wait_for_task_exception_produces_failed_stub_but_no_raise(mock_client_cls: MagicMock, caplog):
    mock_client = MagicMock()
    mock_index = MagicMock()
    mock_client_cls.return_value = mock_client

    mock_client.get_index.return_value = object()
    mock_client.index.return_value = mock_index

    s = make_settings({"MEILI_INDEX_SETTINGS": {}, "MEILI_BATCH_SIZE": 2})
    pipe = MeiliSearchPipeline.from_crawler(type("C", (), {"settings": s}))
    spider = DummySpider()
    pipe.open_spider(spider)

    mock_index.add_documents.return_value = TaskInfoMock(task_uid=77, status="enqueued")
    mock_client.wait_for_task.side_effect = RuntimeError("network timeout")

    with caplog.at_level("WARNING"):
        pipe.process_item({"id": 1}, spider)
        pipe.process_item({"id": 2}, spider)  # flush -> wait_for_task -> exception -> stub

    assert len(pipe._failed_tasks) == 1
    assert getattr(pipe._failed_tasks[0], "status", None) == "failed"

    pipe.close_spider(spider)


@patch("scrapy_meili_pipeline.meili_pipeline.meilisearch.Client")
def test_task_without_task_uid_raises_immediately_on_flush(mock_client_cls: MagicMock):
    mock_client = MagicMock()
    mock_index = MagicMock()
    mock_client_cls.return_value = mock_client

    mock_client.get_index.return_value = object()
    mock_client.index.return_value = mock_index

    class BadTask:
        pass

    mock_index.add_documents.return_value = BadTask()

    s = make_settings({"MEILI_INDEX_SETTINGS": {}, "MEILI_BATCH_SIZE": 1})
    pipe = MeiliSearchPipeline.from_crawler(type("C", (), {"settings": s}))
    spider = DummySpider()
    pipe.open_spider(spider)

    with pytest.raises(RuntimeError, match="Task object has no uid"):
        pipe.process_item({"id": 1}, spider)
