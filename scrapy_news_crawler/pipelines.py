"""Persist scraped articles to PostgreSQL with Redis URL de-duplication."""

from __future__ import annotations

import hashlib
import os
import secrets
from datetime import datetime, timezone
from typing import Any

import psycopg
import redis
from itemadapter import ItemAdapter
from psycopg.types.json import Jsonb
from scrapy.exceptions import DropItem


PUBLISHER_MEMBER_ID = 7
PUBLISHER_NAME = "灞波儿奔"


class PostgreSQLRedisPipeline:
    """Write ``ScrapyNewsCrawlerItem`` to ``article_official_info``.

    Redis provides a fast URL de-duplication gate; PostgreSQL is still checked
    before insert because Redis keys may expire or be flushed.
    """

    def __init__(self) -> None:
        self.pg_conn: psycopg.Connection | None = None
        self.redis_client: redis.Redis | None = None
        self.redis_ttl = int(os.getenv("REDIS_DEDUPE_TTL", "2592000"))

    @classmethod
    def from_crawler(cls, crawler):
        return cls()

    def open_spider(self, spider) -> None:
        self.pg_conn = psycopg.connect(
            host=os.getenv("PG_HOST", "192.168.31.201"),
            port=int(os.getenv("PG_PORT", "5452")),
            dbname=os.getenv("PG_DATABASE", "admin_db"),
            user=os.getenv("PG_USER", "postgres"),
            password=os.getenv("PG_PASSWORD", "123456"),
            connect_timeout=int(os.getenv("PG_CONNECT_TIMEOUT", "10")),
        )
        self.redis_client = redis.Redis.from_url(
            os.getenv("REDIS_URL", "redis://192.168.31.201:6379/0"),
            decode_responses=True,
            socket_connect_timeout=int(os.getenv("REDIS_CONNECT_TIMEOUT", "10")),
            socket_timeout=int(os.getenv("REDIS_SOCKET_TIMEOUT", "10")),
        )
        self.redis_client.ping()
        spider.logger.info("PostgreSQL and Redis connections are ready")

    def close_spider(self, spider) -> None:
        if self.pg_conn is not None:
            self.pg_conn.close()
        if self.redis_client is not None:
            self.redis_client.close()

    def process_item(self, item, spider):
        adapter = ItemAdapter(item)
        url = str(adapter.get("url") or "").strip()
        if not url:
            raise DropItem("missing article URL")

        redis_key = self._redis_key(url)
        assert self.redis_client is not None
        if not self.redis_client.set(redis_key, "1", nx=True, ex=self.redis_ttl):
            raise DropItem(f"duplicate URL according to Redis: {url}")

        try:
            assert self.pg_conn is not None
            with self.pg_conn.cursor() as cursor:
                cursor.execute(
                    "SELECT id FROM article_official_info WHERE url = %s LIMIT 1",
                    (url,),
                )
                if cursor.fetchone() is not None:
                    self.pg_conn.commit()
                    raise DropItem(f"duplicate URL according to PostgreSQL: {url}")

                cursor.execute(
                    """
                    INSERT INTO article_official_info (
                        article_no, member_id, publisher_snapshot, url, title,
                        content, image_urls, source, published_at, crawled_at,
                        board, rank, status, view_count, created_at, updated_at
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, 'approved', 0, %s, %s
                    )
                    """,
                    (
                        self._article_no(cursor),
                        PUBLISHER_MEMBER_ID,
                        PUBLISHER_NAME,
                        url,
                        str(adapter.get("title") or "").strip(),
                        str(adapter.get("content") or ""),
                        Jsonb(list(adapter.get("image_urls") or [])),
                        str(adapter.get("source") or "中新网")[:100],
                        self._datetime(adapter.get("published_at")),
                        self._datetime(adapter.get("crawled_at")),
                        self._optional_text(adapter.get("board"), 100),
                        adapter.get("rank"),
                        datetime.now(timezone.utc),
                        datetime.now(timezone.utc),
                    ),
                )
            self.pg_conn.commit()
            return item
        except DropItem:
            raise
        except Exception:
            self.pg_conn.rollback()
            self._delete_dedupe_key(redis_key, spider)
            raise

    @staticmethod
    def _redis_key(url: str) -> str:
        digest = hashlib.sha256(url.encode("utf-8")).hexdigest()
        return f"scrapy_news_crawler:article:url:{digest}"

    @staticmethod
    def _datetime(value: Any) -> datetime:
        if isinstance(value, datetime):
            parsed = value
        elif value:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        else:
            parsed = datetime.now(timezone.utc)
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError("article datetime must be timezone-aware")
        return parsed.astimezone(timezone.utc)

    @staticmethod
    def _optional_text(value: Any, max_length: int) -> str | None:
        if value is None:
            return None
        value = str(value).strip()
        return value[:max_length] or None

    @staticmethod
    def _article_no(cursor) -> str:
        for _ in range(10):
            candidate = f"{secrets.randbelow(10**12):012d}"
            cursor.execute(
                "SELECT 1 FROM article_official_info WHERE article_no = %s LIMIT 1",
                (candidate,),
            )
            if cursor.fetchone() is None:
                return candidate
        raise RuntimeError("could not generate a unique article_no")

    def _delete_dedupe_key(self, key: str, spider) -> None:
        try:
            assert self.redis_client is not None
            self.redis_client.delete(key)
        except Exception:
            spider.logger.warning("failed to release Redis key %s", key, exc_info=True)


# Keep the conventional project pipeline name available for integrations.
ScrapyNewsCrawlerPipeline = PostgreSQLRedisPipeline
