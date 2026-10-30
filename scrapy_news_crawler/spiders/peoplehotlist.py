"""抓取人民日报热榜页面展示的 20 条新闻，仅用于终端预览。"""

import json
from datetime import datetime, timezone

import scrapy

from scrapy_news_crawler.items import ScrapyNewsCrawlerItem


class PeopleHotlistSpider(scrapy.Spider):
    name = "peoplehotlist"
    allowed_domains = ["peopleapp.com"]
    start_urls = ["https://www.peopleapp.com/atv/peoplehotlist/2"]

    # Preview only: do not write the hot-list records to PostgreSQL or Redis.
    # custom_settings = {
    #     "ITEM_PIPELINES": {},
    # }

    def parse(self, response):
        payload_text = response.css("#__NUXT_DATA__::text").get()
        if not payload_text:
            self.logger.error("页面没有找到 __NUXT_DATA__：%s", response.url)
            return

        try:
            payload = json.loads(payload_text)
            hot_list = next(
                value for value in payload
                if isinstance(value, dict)
                and "list" in value
                and "showNum" in value
                and "title" in value
            )
            records = self.resolve(payload, hot_list["list"])
        except (ValueError, StopIteration, TypeError, IndexError) as exc:
            self.logger.error("解析人民热榜 SSR 数据失败：%s", exc)
            return

        self.logger.info("人民热榜共发现 %d 条新闻（首页 17 条 + 更多 3 条）", len(records))
        for rank, record in enumerate(records, start=1):
            if not isinstance(record, dict):
                continue
            title = self.clean(record.get("newsTitle"))
            object_id = self.clean(record.get("objectId"))
            if not title or not object_id:
                continue

            # The list payload only contains the title/summary. Request the
            # official detail API so content is not replaced by the title.
            yield scrapy.Request(
                response.urljoin(
                    "/api/rmrb-bff-display-zh/content/zh/c/pc/content/detail"
                ) + f"?contentId={object_id}", 
                callback=self.parse_detail,
                headers=self.detail_headers,
                cb_kwargs={
                    "rank": rank,
                    "object_id": object_id,
                    "list_record": record,
                    "article_url": f"https://www.peopleapp.com/rmharticle/{object_id}",
                },
            )

    @property
    def detail_headers(self):
        return {
            "Authorization": "AppCode 2faaf721ed424694bc63bdaec811a580",
            "X-Ca-Stage": "RELEASE",
            "plat": "web",
            "system": "PC",
            "versionCode": "7422",
        }

    def parse_detail(self, response, rank, object_id, list_record, article_url):
        if response.status != 200:
            self.logger.warning("详情接口返回 %s：%s", response.status, object_id)
            return
        try:
            payload = response.json()
            detail = (payload.get("data") or [{}])[0]
        except (ValueError, TypeError, IndexError) as exc:
            self.logger.warning("详情 JSON 解析失败 %s：%s", object_id, exc)
            return

        title = self.clean(detail.get("newsTitle")) or self.clean(
            list_record.get("newsTitle")
        )
        content_html = detail.get("newsContent") or detail.get("newsContentBak") or ""
        content, detail_images = self.extract_content(content_html)
        if not content:
            self.logger.warning("详情正文为空，使用摘要：%s", object_id)
            content = self.clean(detail.get("newsSummary")) or title
        images = self.image_urls(list_record) + detail_images
        images = list(dict.fromkeys(images))
        item = ScrapyNewsCrawlerItem(
            url=article_url,
            title=title,
            content=content,
            image_urls=images,
            source=self.clean(detail.get("newsSourceName")) or "人民日报",
            published_at=self.parse_detail_date(detail.get("publishTime")),
            crawled_at=datetime.now(timezone.utc).isoformat(),
            board="人民热榜",
            rank=rank,
        )
        print(json.dumps(dict(item), ensure_ascii=False, indent=2), flush=True)
        yield item

    def extract_content(self, content_html):
        selector = scrapy.Selector(text=content_html or "")
        text = self.clean(selector.xpath("string(.)").get())
        images = []
        for src in selector.css("img::attr(src), img::attr(data-src)").getall():
            src = self.clean(src)
            if src.startswith(("http://", "https://")) and src not in images:
                images.append(src)
        return text, images

    @staticmethod
    def resolve(payload, value):
        """Resolve Nuxt's compact integer-reference payload."""
        if isinstance(value, int):
            if value == 537:
                return None
            if value == 533:
                return True
            if value == 567:
                return False
            target = payload[value]
            # Nuxt stores primitive numbers as table values too; do not treat
            # a resolved numeric value as another table reference.
            if isinstance(target, int):
                return target
            return PeopleHotlistSpider.resolve(payload, target)
        if isinstance(value, list):
            return [PeopleHotlistSpider.resolve(payload, item) for item in value]
        if isinstance(value, dict):
            return {
                key: PeopleHotlistSpider.resolve(payload, item)
                for key, item in value.items()
            }
        return value

    @staticmethod
    def clean(value):
        return " ".join(str(value or "").split())

    @staticmethod
    def parse_timestamp(value):
        try:
            return datetime.fromtimestamp(int(value) / 1000, tz=timezone.utc).isoformat()
        except (TypeError, ValueError, OverflowError):
            return None

    @staticmethod
    def parse_detail_date(value):
        if not value:
            return None
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc).isoformat()
        except ValueError:
            return None

    def image_urls(self, record):
        values = [record.get("coverUrl")]
        images = []
        for value in values:
            value = self.clean(value)
            if value.startswith(("http://", "https://")) and value not in images:
                images.append(value)
        return images
