"""抓取人民网科技频道第一页文章。"""

from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

import scrapy

from scrapy_news_crawler.items import ScrapyNewsCrawlerItem


class PeopleTechSpider(scrapy.Spider):
    name = "people_tech"
    allowed_domains = ["people.com.cn"]
    start_urls = ["http://scitech.people.com.cn/index1.html"]

    def parse(self, response):
        # Select only the first-page list. There is intentionally no pagination
        # or “load more” request.
        links = response.css(".ej_list_box ul.list_16 li")
        seen = set()
        scheduled = 0
        for row in links:
            anchor = row.css("a[href]")[:1]
            href = anchor.attrib.get("href", "").strip() if anchor else ""
            title = self.clean_text(anchor.xpath("string(.)").get()) if anchor else ""
            list_date = self.clean_text(row.css("em::text").get())
            url = response.urljoin(href)
            host = urlsplit(url).hostname or ""
            if (
                not title
                or host not in {"people.com.cn", "www.people.com.cn", "scitech.people.com.cn", "finance.people.com.cn"}
                or "/n1/" not in urlsplit(url).path
                or not urlsplit(url).path.endswith(".html")
                or url in seen
            ):
                continue
            seen.add(url)
            scheduled += 1
            yield response.follow(
                url,
                callback=self.parse_article,
                cb_kwargs={"list_title": title, "list_date": list_date, "rank": scheduled},
            )

        self.logger.info("人民网科技第一页发现 %d 篇，调度 %d 篇", len(seen), scheduled)

    def parse_article(self, response, list_title, list_date, rank):
        body = response.css(".rm_txt_con #rm_txt_zw")[:1]
        if not body:
            self.logger.warning("人民网科技正文容器不存在：%s", response.url)
            return

        paragraphs = body.xpath(".//p[not(ancestor::script) and not(ancestor::style)]")
        content = "\n".join(
            text
            for node in paragraphs
            if (text := self.clean_text(node.xpath(".//text()").getall()))
        ) or self.clean_text(body.xpath("string(.)").get())
        if not content:
            self.logger.warning("人民网科技正文为空：%s", response.url)
            return

        images = []
        for src in body.css("img::attr(src), img::attr(data-src)").getall():
            image_url = response.urljoin(src.strip())
            if image_url.startswith(("http://", "https://")) and image_url not in images:
                images.append(image_url)

        published = response.css('meta[name="publishdate"]::attr(content)').get() or list_date
        yield ScrapyNewsCrawlerItem(
            url=response.url,
            title=self.clean_text(response.css("h1").xpath("string(.)").get()) or list_title,
            content=content,
            image_urls=images,
            source="人民网科技",
            published_at=self.parse_date(published),
            crawled_at=datetime.now(timezone.utc).isoformat(),
            board="科技",
            rank=rank,
        )

    @staticmethod
    def clean_text(value):
        if isinstance(value, (list, tuple)):
            value = " ".join(value)
        return " ".join((value or "").split())

    def parse_date(self, value):
        if not value:
            return None
        try:
            parsed = datetime.fromisoformat(value.strip())
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone(timedelta(hours=8)))
            return parsed.astimezone(timezone.utc).isoformat()
        except ValueError:
            self.logger.warning("无法解析人民网科技发布时间：%r", value)
            return None
