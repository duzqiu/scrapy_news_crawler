"""抓取 IT之家滚动新闻第一页文章。"""

from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

import scrapy

from scrapy_news_crawler.items import ScrapyNewsCrawlerItem


class ITHomeTechSpider(scrapy.Spider):
    name = "ithome_tech"
    allowed_domains = ["ithome.com", "www.ithome.com"]
    start_urls = ["https://www.ithome.com/list/"]

    def parse(self, response):
        # The current /list/ document is the first page. Only its article rows
        # are followed; pagination and category pages are ignored.
        seen = set()
        scheduled = 0
        for row in response.css("ul.datel li"):
            anchor = row.css("a.t[href]")[:1]
            if not anchor:
                continue
            url = response.urljoin(anchor.attrib.get("href", "").strip())
            title = self.clean_text(anchor.xpath("string(.)").get())
            published = self.clean_text(row.css("i::text").get())
            host = urlsplit(url).hostname or ""
            if (
                not title
                or host not in {"ithome.com", "www.ithome.com"}
                or not urlsplit(url).path.startswith("/1/")
                or url in seen
            ):
                continue
            seen.add(url)
            scheduled += 1
            yield response.follow(
                url,
                callback=self.parse_article,
                cb_kwargs={"list_title": title, "list_date": published, "rank": scheduled},
            )

        self.logger.info("IT之家第一页发现 %d 篇，调度 %d 篇", len(seen), scheduled)

    def parse_article(self, response, list_title, list_date, rank):
        # IT之家部分列表项属于“好物广告”。判断详情页面包屑最后一层，
        # 命中后直接丢弃，避免广告文章进入后续 Pipeline。
        breadcrumb = [
            self.clean_text(text)
            for text in response.css(".cv a::text").getall()
            if self.clean_text(text)
        ]
        if breadcrumb and breadcrumb[-1] == "好物广告":
            self.logger.info("跳过好物广告：%s", response.url)
            return

        body = response.css(".post_content")[:1]
        if not body:
            self.logger.warning("IT之家正文容器不存在：%s", response.url)
            return

        paragraphs = body.xpath(".//p[not(ancestor::script) and not(ancestor::style)]")
        content = "\n".join(
            text
            for node in paragraphs
            if (text := self.clean_text(node.xpath(".//text()").getall()))
        ) or self.clean_text(body.xpath("string(.)").get())
        if not content:
            self.logger.warning("IT之家正文为空：%s", response.url)
            return

        images = []
        for src in body.css("img::attr(src), img::attr(data-src)").getall():
            image_url = response.urljoin(src.strip())
            if image_url.startswith(("http://", "https://")) and image_url not in images:
                images.append(image_url)

        yield ScrapyNewsCrawlerItem(
            url=response.url,
            title=self.clean_text(response.css("h1").xpath("string(.)").get()) or list_title,
            content=content,
            image_urls=images,
            source="IT之家",
            published_at=self.parse_date(list_date),
            crawled_at=datetime.now(timezone.utc).isoformat(),
            board="科技",
            rank=rank,
        )

    @staticmethod
    def clean_text(value):
        if isinstance(value, (list, tuple)):
            value = " ".join(value)
        return " ".join((value or "").split())

    @staticmethod
    def parse_date(value):
        if not value:
            return None
        try:
            parsed = datetime.strptime(value.strip(), "%Y-%m-%d %H:%M:%S")
            return parsed.replace(tzinfo=timezone(timedelta(hours=8))).astimezone(timezone.utc).isoformat()
        except ValueError:
            return None
