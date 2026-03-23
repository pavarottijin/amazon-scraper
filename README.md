# Amazon Scraper (Scrapy + DrissionPage)

A Scrapy-based Amazon search scraper with UA rotation, proxy rotation, Cloudflare challenge handling, and DrissionPage rendering.

---

## English

### What It Does

- Scrapes Amazon search results by keyword.
- Extracts: `title`, `rating`, `review_nb`, `img`, `url`, `asin`, `prices_main`.
- Rotates User-Agent (UA) per request.
- Rotates proxies and temporarily bans bad ones.
- Detects Cloudflare challenge pages and can use Flaresolverr.
- Uses DrissionPage rendering for suspicious pages.
- Cleans numeric fields in pipeline and exports JSONL.

### Project Structure

```text
amazon_scraper/
  amazon_scraper/
    spiders/amazon_spider.py
    middlewares.py
    pipelines.py
    settings.py
    requirements.txt
  debug.py
  scrapy.cfg
```

### Install

```bash
pip install -r amazon_scraper/requirements.txt
```

### Run

1. CLI

```bash
scrapy crawl AmazonSpider -a keyword=python -a min_products=50
```

2. Debug script

```bash
python debug.py
```

Default output: `output/products.jsonl`

### Spider Arguments

- `keyword`: search keyword
- `min_products`: soft target. Pagination stops after the current page once this target is reached.

### Key Settings

File: `amazon_scraper/settings.py`

- `PROXIES`: proxy list
- `PROXY_TEST_URL`: proxy health-check URL
- `PROXY_BAN_SECONDS`: temporary ban duration for failed proxy
- `PROXY_REQUEST_TIMEOUT`: per-request timeout when using proxy
- `DOWNLOAD_TIMEOUT`: global request timeout
- `USER_AGENTS`: UA pool for random UA rotation
- `DRISSION_HEADLESS`: headless mode for DrissionPage
- `DRISSION_GET_TIMEOUT`: page load timeout for DrissionPage
- `FLARESOLVERR_URL`: Flaresolverr endpoint

### Anti-Bot Details

1. Random UA rotation
- Each request picks one UA from `USER_AGENTS`.

2. Proxy rotation and health checks
- Middleware picks an available proxy from `PROXIES`.
- Proxy health is tested via `PROXY_TEST_URL`.
- Failed proxies are banned for `PROXY_BAN_SECONDS`.
- Timeouts / bad statuses (e.g. 429, 503) can also trigger ban.

3. DrissionPage render decision and cache
- Suspicious pages are rendered with DrissionPage.
- On success, domain is cached and prioritized later.
- Cache file: `amazon_scraper/js_urls_store.json`.

4. Cloudflare + Flaresolverr (optional)
- `CloudflareFlaresolverrMiddleware` detects challenge pages.
- If Flaresolverr is available, solved HTML is returned to spider.
- Flaresolverr is optional: crawler still runs without it, but challenge bypass ability is reduced.
- Middleware checks service availability at startup and auto-skips if unavailable.

Optional Docker startup:

```bash
docker run -d --name flaresolverr -p 8191:8191 ghcr.io/flaresolverr/flaresolverr:latest
```

### Middleware Flow

Request phase (before download):

1. `RotateUserAgentMiddleware` sets random UA.
2. `ProxyMiddleware` picks and sets `request.meta["proxy"]`.
3. Downloader sends request.

Response phase (after download):

1. `DrissionPageMiddleware` may replace response with rendered HTML.
2. `CloudflareFlaresolverrMiddleware` may replace response with solved HTML.
3. `ProxyMiddleware` can ban proxy on bad statuses.
4. Spider `parse()` extracts fields.
5. Pipeline normalizes and writes JSONL.

### Data Cleaning

Handled in `pipelines.py`:

- `rating` -> `float`
- `review_nb` -> `int`
- `prices_main` -> `float`

### Common Notes

1. `url` is null
- Multi-selector + ASIN fallback (`/dp/{asin}`) is implemented.

2. Many `review_nb` are null
- Some products really have no visible review count, and Amazon layout/locale can vary.

3. Stuck near `Using proxy`
- Usually caused by downstream wait (request/render). Timeouts and failover are configured.

4. Proxy auth popup in browser
- DrissionPage has limited support for auth proxy popups. Prefer IP-whitelist proxies or local forwarding proxy.

### Future Updates

The current version decides whether to enable DrissionPage rendering mainly at the `domain` level. This works well for sites like Amazon where anti-bot logic is applied broadly across the site.

In a later update, this will be refined to `url`-level granularity (instead of domain-only rules). That will make it easier to distinguish which pages really need rendering and which can stay on normal HTTP requests, improving portability and extensibility for other target sites.

### Disclaimer

For learning and technical research only. Follow target site terms, robots rules, and applicable laws.

## 中文

一个基于 Scrapy 的 Amazon 搜索页采集项目，支持 UA 轮换、代理轮换、Cloudflare 挑战处理和 DrissionPage 渲染。

---

### 项目功能

- 按关键词抓取 Amazon 搜索结果商品。
- 抽取字段：`title`, `rating`, `review_nb`, `img`, `url`, `asin`, `prices_main`。
- 支持每个请求随机 UA 轮换。
- 支持代理轮换，并对异常代理临时 ban。
- 检测 Cloudflare 挑战页，并可接入 Flaresolverr。
- 对可疑页面使用 DrissionPage 渲染。
- 在 pipeline 中完成数值清洗并输出 JSONL。

### 目录结构

```text
amazon_scraper/
  amazon_scraper/
    spiders/amazon_spider.py
    middlewares.py
    pipelines.py
    settings.py
    requirements.txt
  debug.py
  scrapy.cfg
```

### 安装

```bash
pip install -r amazon_scraper/requirements.txt
```

### 运行

1. 命令行运行

```bash
scrapy crawl AmazonSpider -a keyword=python -a min_products=50
```

2. 调试脚本运行

```bash
python debug.py
```

默认输出文件：`output/products.jsonl`

### Spider 参数

- `keyword`：搜索关键词
- `min_products`：最小抓取目标。达到后会在当前页处理完时停止翻页。

### 关键配置

文件：`amazon_scraper/settings.py`

- `PROXIES`：代理列表
- `PROXY_TEST_URL`：代理连通性测试地址
- `PROXY_BAN_SECONDS`：代理临时禁用时长
- `PROXY_REQUEST_TIMEOUT`：代理请求超时
- `DOWNLOAD_TIMEOUT`：全局下载超时
- `USER_AGENTS`：UA 列表（随机轮换）
- `DRISSION_HEADLESS`：DrissionPage 是否无头
- `DRISSION_GET_TIMEOUT`：DrissionPage 页面加载超时
- `FLARESOLVERR_URL`：Flaresolverr 服务地址

### 反爬策略细节

1. UA 随机轮换
- 每个请求会从 `USER_AGENTS` 随机选择一个 UA。

2. 代理轮换与健康检测
- 从 `PROXIES` 中选择可用代理。
- 使用 `PROXY_TEST_URL` 快速检测连通性。
- 失败代理按 `PROXY_BAN_SECONDS` 临时禁用。
- 超时或异常状态（例如 429、503）也会触发 ban。

3. DrissionPage 渲染判定与记录
- 可疑页面会尝试 DrissionPage 渲染。
- 渲染成功后记录域名，后续优先使用 DrissionPage。
- 缓存文件：`amazon_scraper/js_urls_store.json`。

4. Cloudflare + Flaresolverr（可选）
- `CloudflareFlaresolverrMiddleware` 会检测挑战页。
- 如果 Flaresolverr 可用，会返回挑战后的 HTML 给 spider。
- Flaresolverr 不是必需组件，不安装也能运行，只是 Cloudflare 绕过能力会下降。
- 中间件启动时会测试服务可用性，不可用则自动跳过。

可选 Docker 启动示例：

```bash
docker run -d --name flaresolverr -p 8191:8191 ghcr.io/flaresolverr/flaresolverr:latest
```

### 中间件流程

请求阶段（发请求前）：

1. `RotateUserAgentMiddleware` 设置随机 UA。
2. `ProxyMiddleware` 选择并设置 `request.meta["proxy"]`。
3. 下载器发起请求。

响应阶段（收到响应后）：

1. `DrissionPageMiddleware` 可能用渲染后的 HTML 替换响应。
2. `CloudflareFlaresolverrMiddleware` 可能用解挑战后的 HTML 替换响应。
3. `ProxyMiddleware` 可根据异常状态 ban 代理。
4. Spider `parse()` 提取字段。
5. Pipeline 清洗并写入 JSONL。

### 数据清洗

在 `pipelines.py` 中完成：

- `rating` -> `float`
- `review_nb` -> `int`
- `prices_main` -> `float`

### 常见问题说明

1. `url` 为空
- 已实现多选择器 + ASIN 兜底（`/dp/{asin}`）。

2. `review_nb` 为空较多
- 部分商品确实无评论数展示，同时 Amazon 结构与语言会变化。

3. 日志卡在 `Using proxy`
- 常见是后续请求/渲染等待导致，已配置超时与失败切换。

4. 代理认证弹窗
- DrissionPage 对认证代理弹窗支持有限，建议使用 IP 白名单代理或本地转发代理。

### 后续更新

当前按 `domain` 维度判断是否启用 DrissionPage 渲染。这个策略对 Amazon 这类全站反爬较强的网站更实用，能较快稳定下来。
后续计划升级为按 `url` 维度做更细粒度判定（而不是只按域名）。这样在抓取其他网站时，可以更精准地区分哪些页面需要渲染、哪些页面可直接走普通请求，从而提升项目的通用性和可扩展性。

### 免责声明

本项目仅用于学习与技术研究，请遵守目标网站条款、robots 规则和相关法律法规。
