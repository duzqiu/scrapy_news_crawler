import json
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import scrapy

from scrapy_news_crawler.items import ScrapyNewsCrawlerItem


class ChinanewsRssSpider(scrapy.Spider):
    """通过中新网 RSS 发现文章，并抓取文章详情。"""

    name = "chinanews"
    allowed_domains = ["www.chinanews.com.cn"]

    # 先用“要闻导读”验证完整链路，后续可增加其它 RSS。
    start_urls = [
        "https://www.chinanews.com.cn/rss/importnews.xml",
    ]

    def __init__(self, limit=0, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 默认不限制数量，抓取 RSS 当前返回的全部条目。
        self.limit = int(limit)
        if self.limit < 0:
            raise ValueError("limit 必须为非负整数，0 表示全部")

    def parse(self, response):
        """解析 RSS，并继续请求文章详情页。"""
        if response.status != 200:
            self.logger.error("RSS 请求失败 status=%s url=%s", response.status, response.url)
            return

        items = response.xpath("//*[local-name()='item']")
        self.logger.info("RSS=%s 发现 %s 条新闻", response.url, len(items))

        for entry in items[: self.limit] if self.limit else items:
            title = self.clean_text(entry.xpath("./*[local-name()='title']/text()").get())
            article_url = self.clean_text(entry.xpath("./*[local-name()='link']/text()").get())
            description = self.clean_text(
                entry.xpath("./*[local-name()='description']/text()").get()
            )
            published_at = self.parse_date(
                self.clean_text(
                    entry.xpath("./*[local-name()='pubDate']/text()").get()
                )
            )

            if not article_url:
                continue

            yield response.follow(
                article_url,
                callback=self.parse_article,
                cb_kwargs={
                    "rss_title": title,
                    "rss_description": description,
                    "published_at": published_at,
                    "board": "要闻导读",
                },
            )

    def parse_article(
        self,
        response,
        rss_title,
        rss_description,
        published_at,
        board,
    ):
        """解析文章详情页，并按当前 Item 字段打印数据。"""
        title = self.clean_text(
            response.css("h1::text").get()
            or response.css('meta[property="og:title"]::attr(content)').get()
            or rss_title
        )

        # 中新网不同频道页面结构可能不同，按多个正文容器兼容。
        content_nodes = response.css(
            ".content_maincontent_content .left_zw ::text, "
            ".left_zw ::text, "
            ".article-content ::text, "
            "article ::text"
        ).getall()
        content = self.clean_paragraphs(content_nodes)
        if not content:
            content = rss_description

        image_urls = []
        cover = response.css('meta[property="og:image"]::attr(content)').get()
        if cover:
            image_urls.append(response.urljoin(cover.strip()))

        image_sources = response.css(
            ".content_maincontent_content .left_zw img::attr(src), "
            ".content_maincontent_content .left_zw img::attr(data-src), "
            ".left_zw img::attr(src), "
            ".left_zw img::attr(data-src), "
            ".article-content img::attr(src), "
            ".article-content img::attr(data-src), "
            "article img::attr(src), "
            "article img::attr(data-src)"
        ).getall()
        for source in image_sources:
            image_url = response.urljoin(source.strip())
            if image_url.startswith(("http://", "https://")) and image_url not in image_urls:
                image_urls.append(image_url)

        item = ScrapyNewsCrawlerItem(
            url=response.url,
            title=title,
            content=content,
            image_urls=image_urls,
            source="中新网",
            published_at=published_at,
            crawled_at=datetime.now(timezone.utc).isoformat(),
            board=board,
            rank=None,
        )

        # 终端打印，便于先确认字段和解析结果；当前未连接数据库。
        print(json.dumps(dict(item), ensure_ascii=False, indent=2))
        yield item

    @staticmethod
    def parse_date(value):
        if not value:
            return None
        try:
            return parsedate_to_datetime(value).isoformat()
        except (TypeError, ValueError, OverflowError):
            return value

    @staticmethod
    def clean_text(value):
        if not value:
            return ""
        return " ".join(value.split())

    @classmethod
    def clean_paragraphs(cls, values):
        paragraphs = []
        for value in values:
            value = cls.clean_text(value)
            if value and value not in paragraphs:
                paragraphs.append(value)
        return "\n".join(paragraphs)
