# The Compose file uses the GitHub repository as the build context.
# Docker therefore receives the latest repository files directly and does not
# need Git or a separate source stage inside the image.
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN python -m pip install --upgrade pip \
    && python -m pip install -r /app/requirements.txt

COPY scrapy.cfg /app/scrapy.cfg
COPY scrapy_news_crawler /app/scrapy_news_crawler
COPY run-all-spiders.sh /app/run-all-spiders.sh
RUN chmod +x /app/run-all-spiders.sh

CMD ["/app/run-all-spiders.sh"]
