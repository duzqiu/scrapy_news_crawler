# Docker 爬虫部署

本项目使用 Docker Compose 手动启动一次性爬虫任务：

```text
docker compose run --rm crawler -> run-all-spiders.sh -> 执行全部 Spider
```

部署容器会自动发现并依次执行 `spiders/` 目录下的全部 Scrapy Spider。抓取到的 Item 通过 `PostgreSQLRedisPipeline` 写入 FastAPI 后台的 `article_official_info` 表，并用 Redis 按文章 URL 去重。

## 1. 服务器准备

安装 Docker Engine 和 Compose Plugin，然后将项目代码放到服务器上：

```bash
cd /opt
# 可以通过 git clone、上传压缩包或其他方式取得项目
cd /opt/scrapy_news_crawler
```

## 2. 配置密钥

```bash
cp .env.example .env
chmod 600 .env
vi .env
```

`.env` 不会被提交到 Git。请在 `.env` 中配置 PostgreSQL 和 Redis；`.env.example` 已提供 `192.168.31.201` 的示例地址。密码仅为示例，生产环境请替换。

## 3. 手动构建并启动爬虫

需要拉取 GitHub 最新代码并启动定时爬取服务时，在项目目录执行：

```bash
cd /opt/scrapy_news_crawler
docker compose build --pull --no-cache crawler
docker compose up -d crawler
```

Compose 会把 `.env` 中的 `GIT_REPOSITORY` 和 `GIT_REF` 作为远程 Git 构建上下文，直接从 GitHub 获取 Dockerfile、requirements 和爬虫源码，再构建镜像。容器启动后会立即执行一次全部 Spider，随后每次随机等待 2 到 4 小时，再执行下一轮。

容器使用 `restart: unless-stopped`，爬虫服务会持续运行；手动停止前不会自动退出。

如果使用固定分支，构建时会获取该分支当前提交；生产环境也可以把 `GIT_REF` 改成具体 tag 或 commit，以保证版本可复现。

查看已构建镜像：

```bash
docker image ls scrapy-news-crawler
```

## 4. 查看日志和清理

```bash
docker compose logs -f crawler
docker ps -a --filter name=scrapy-news-crawler
docker image prune
```

容器默认会通过 `run-scheduled-spiders.sh` 启动定时循环；每轮调用 `run-all-spiders.sh`，执行 `scrapy list` 返回的全部 Spider，并按顺序逐个运行。新增 Spider 文件到 `scrapy_news_crawler/spiders/` 后，无需修改 Docker 或 Compose 配置。

如果需要单独调试某个 Spider，可以覆盖容器命令：

```bash
docker compose run --rm --no-deps crawler scrapy crawl chinanews -a limit=3
```

## 5. PostgreSQL 和 Redis 配置

默认配置如下：

```dotenv
PG_HOST=192.168.31.201
PG_PORT=5452
PG_DATABASE=admin_db
PG_USER=postgres
PG_PASSWORD=123456
REDIS_URL=redis://192.168.31.201:6379/0
```

Pipeline 写入后台的 `article_official_info` 表，初始审核状态为 `approved`（已通过），固定使用 `member_id=7`、`publisher_snapshot=灞波儿奔`。请确保后台 PostgreSQL 的 `member_account_info` 中存在主键为 7 的会员，否则外键约束会拒绝插入。Redis 使用文章 URL 的 SHA-256 作为去重键，默认保留 30 天；即使 Redis key 过期，也会再次检查 PostgreSQL 中的 URL。

可在运行前检查网络连通性：

```bash
nc -vz 192.168.31.201 5452
redis-cli -h 192.168.31.201 -p 6379 ping
```

本地没有 PostgreSQL 和 Redis，因此本次只进行了 Python 编译和 Shell 静态检查，没有实际连接或写入远程服务。
