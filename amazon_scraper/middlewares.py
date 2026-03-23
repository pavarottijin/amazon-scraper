import random
import requests
from scrapy import signals
from scrapy.http import HtmlResponse
from DrissionPage import ChromiumOptions, ChromiumPage
import logging
import time
import os
import json
from urllib.parse import urlparse






# useful for handling different item types with a single interface
from itemadapter import ItemAdapter

#UA轮换中间件，随机选取一个 User-Agent
class RotateUserAgentMiddleware:
    """
    功能：
    - 从 USER_AGENTS 列表中随机选取一个 User-Agent
    - 在 process_request 中设置到请求头
    """
    def __init__(self, user_agents):
        self.user_agents = user_agents

    @classmethod
    def from_crawler(cls, crawler):
        return cls(user_agents=crawler.settings.get("USER_AGENTS", []))

    def process_request(self, request, spider):
        request.headers['User-Agent'] = random.choice(self.user_agents)

#代理轮换中间件，随机选取代理并测试连通性，失败则禁用一段时间
class ProxyMiddleware:
    """
    功能：
    - 随机选取代理
    - 检查是否在禁用池（{self.ban_seconds} 秒）
    - 测试代理连通性（快速 HEAD 请求）
    - 连通失败 → 禁用 {self.ban_seconds} 秒
    - 所有代理都不可用 → 不使用代理
    """

    def __init__(self, proxies, test_url, ban_seconds=600, request_timeout=20):
        self.logger = logging.getLogger(self.__class__.__name__)
        self.proxies = proxies
        self.test_url = test_url
        self.ban_seconds = ban_seconds
        self.request_timeout = request_timeout

        # { proxy_url: ban_until_timestamp }
        self.ban_pool = {}

        self.logger.info(f"[ProxyMiddleware] Loaded {len(self.proxies)} proxies.")

    @classmethod
    def from_crawler(cls, crawler):
        proxies = crawler.settings.get("PROXIES", [])
        test_url = crawler.settings.get("PROXY_TEST_URL", "https://www.google.com/")
        ban_seconds = crawler.settings.getint("PROXY_BAN_SECONDS", 600)
        request_timeout = crawler.settings.getint("PROXY_REQUEST_TIMEOUT", 20)
        return cls(
            proxies=proxies,
            test_url=test_url,
            ban_seconds=ban_seconds,
            request_timeout=request_timeout,
        )

    # ---------------------------
    # 工具函数
    # ---------------------------

    def _is_banned(self, proxy):
        """
        检查代理是否在禁用池中
        """
        ban_until = self.ban_pool.get(proxy)
        if not ban_until:
            return False
        if time.time() >= ban_until:
            del self.ban_pool[proxy]
            return False
        return True

    def _ban_proxy(self, proxy):
        """
        禁用代理 {self.ban_seconds} 秒
        """
        ban_until = time.time() + self.ban_seconds
        self.ban_pool[proxy] = ban_until
        self.logger.warning(f"[ProxyMiddleware] Proxy banned for {self.ban_seconds}s: {proxy}")

    def _test_proxy(self, proxy):
        """
        测试代理是否可用（快速 HEAD 请求）
        """
        try:
            res = requests.head(
                self.test_url,
                proxies={"http": proxy, "https": proxy},
                timeout=10,
            )
            if res.status_code in (200, 301, 302):
                return True
            return False
        except Exception as e:
            return False

    def _choose_working_proxy(self):
        """
        随机选择一个可用代理
        """
        if not self.proxies:
            return None

        candidates = self.proxies.copy()
        random.shuffle(candidates)

        for proxy in candidates:
            if self._is_banned(proxy):
                self.logger.info(f"[ProxyMiddleware] Skip banned proxy: {proxy}")
                continue

            self.logger.info(f"[ProxyMiddleware] Testing proxy: {proxy}")

            if self._test_proxy(proxy):
                self.logger.info(f"[ProxyMiddleware] Proxy OK: {proxy}")
                return proxy

            # 测试失败 → 禁用
            self._ban_proxy(proxy)

        # 全部代理不可用
        self.logger.error("[ProxyMiddleware] All proxies failed. Using local IP.")
        return None

    # ---------------------------
    # Scrapy Hook
    # ---------------------------

    def process_request(self, request, spider):
        # 防止代理“假连通、真卡死”导致请求长时间无响应。
        request.meta.setdefault("download_timeout", self.request_timeout)

        proxy = self._choose_working_proxy()

        if proxy:
            request.meta["proxy"] = proxy
            spider.logger.info(f"[ProxyMiddleware] Using proxy: {proxy}")
        else:
            if "proxy" in request.meta:
                del request.meta["proxy"]
            spider.logger.warning("[ProxyMiddleware] No proxy used (all failed).")

    def process_response(self, request, response, spider):
        proxy = request.meta.get("proxy")
        if not proxy:
            return response

        if response.status in (407, 429, 502, 503, 504):
            self.logger.warning(
                f"[ProxyMiddleware] Bad status {response.status}, ban proxy: {proxy}"
            )
            self._ban_proxy(proxy)

        return response

    def process_exception(self, request, exception, spider):
        proxy = request.meta.get("proxy")
        if proxy:
            self.logger.warning(
                f"[ProxyMiddleware] Exception with proxy {proxy}: {exception}. Ban and retry."
            )
            self._ban_proxy(proxy)
        return None


#Cloudflare反爬检测中间件，自动通过 Flaresolverr 获取 HTML
class CloudflareFlaresolverrMiddleware:
    """
    功能：
    - 检测 Cloudflare 验证页面（403/429/503 或特征文本）
    - 自动使用 Flaresolverr 规避反爬
    - 启动时自动测试 Flaresolverr 是否可用
    - 如果 Flaresolverr 不可用，则自动禁用，不再尝试调用
    """

    def __init__(self, flaresolverr_url):
        self.logger = logging.getLogger(self.__class__.__name__)
        self.flaresolverr_url = flaresolverr_url.rstrip("/")
        self.flaresolverr_available = self._test_flaresolverr()

    @classmethod
    def from_crawler(cls, crawler):
        url = crawler.settings.get("FLARESOLVERR_URL", "http://localhost:8191/v1")
        return cls(flaresolverr_url=url)

    # ----------------------------------------------------------------------
    # 工具函数
    # ----------------------------------------------------------------------

    def _test_flaresolverr(self):
        """
        测试 Flaresolverr 是否可用：
        - 发送空请求
        - 如果失败，则标记为不可用
        """
        test_url = self.flaresolverr_url

        try:
            r = requests.post(test_url, json={"cmd": "sessions.list"}, timeout=10)
            if r.status_code == 200:
                return True
        except Exception as e:
            self.logger.error(f"[CloudflareFlaresolverrMiddleware] Error testing Flaresolverr: {e}")

        return False

    def is_cloudflare_challenge(self, response):
        """
        判断当前响应是否为 Cloudflare 验证页面
        """
        text = response.text.lower()

        # 常见 Cloudflare 状态码
        if response.status in [403, 429, 503]:
            return True

        # 文本特征
        if "cloudflare" in text and (
            "checking your browser" in text
            or "ray id" in text
            or "cf-turnstile" in text
        ):
            return True

        return False

    # ----------------------------------------------------------------------
    # Scrapy Hook
    # ----------------------------------------------------------------------

    def process_response(self, request, response, spider):
        """
        Scrapy 在收到响应后会调用此方法。
        功能：
        1. 如果 Flaresolverr 不可用 → 直接返回原始响应
        2. 如果已经用 Flaresolverr 处理过 → 不重复处理
        3. 如果检测到 Cloudflare → 调用 Flaresolverr 获取真实 HTML
        """
        # Flaresolverr 不可用 → 不处理
        if not self.flaresolverr_available:
            return response

        # 已经处理过
        if request.meta.get("flaresolverr_used"):
            return response

        # 检测 Cloudflare
        if self.is_cloudflare_challenge(response):
            spider.logger.warning(f"[CloudflareFlaresolverrMiddleware] Detected on {response.url}, using Flaresolverr...")

            try:
                payload = {
                    "cmd": "request.get",
                    "url": response.url,
                    "maxTimeout": 60000,
                }

                r = requests.post(
                    f"{self.flaresolverr_url}/v1",
                    json=payload,
                    timeout=70
                )
                data = r.json()
                html = data["solution"]["response"]

                spider.logger.info(f"[CloudflareFlaresolverrMiddleware] Flaresolverr solved: {response.url}")

                # 返回新的 HTMLResponse
                return HtmlResponse(
                    url=response.url,
                    body=html,
                    encoding="utf-8",
                    request=request.replace(meta={**request.meta, "flaresolverr_used": True}),
                )

            except Exception as e:
                spider.logger.error(f"[CloudflareFlaresolverrMiddleware] Flaresolverr error: {e}")
                # 出错后禁用 Flaresolverr，避免重复尝试
                self.flaresolverr_available = False
                return response

        return response

# DrissionPage 渲染中间件，自动检测是否需要 JS 渲染，并使用 DrissionPage 获取 HTML
class DrissionPageMiddleware:
    """
    Scrapy Downloader Middleware
    功能：
    - 自动检测页面是否需要 JS 渲染
    - 对于已记录为 JS 页面（js_urls_store.json 中的 domain），直接使用 DrissionPage 渲染
    - 对于疑似 JS 渲染失败的页面（内容过短、结构异常），尝试 DrissionPage 渲染
    - 渲染成功后自动记录domain，下次直接使用 DrissionPage
    """
    JS_URL_STORE = os.path.join(
        os.path.dirname(__file__), "js_urls_store.json"
    )

    def __init__(self, headless=False, get_timeout=20):
        self.js_urls = self._load_js_urls()
        self.headless = headless
        self.get_timeout = get_timeout
        self.logger = logging.getLogger(self.__class__.__name__)

    @classmethod
    def from_crawler(cls, crawler):
        headless = crawler.settings.getbool("DRISSION_HEADLESS", False)
        get_timeout = crawler.settings.getint("DRISSION_GET_TIMEOUT", 20)
        return cls(headless=headless, get_timeout=get_timeout)

    # ----------------------------------------------------------------------
    # 工具函数
    # ----------------------------------------------------------------------

    def _load_js_urls(self):
        """
        加载 js_urls_store.json
        """
        if not os.path.exists(self.JS_URL_STORE):
            return set()
        try:
            with open(self.JS_URL_STORE, "r", encoding="utf-8") as f:
                return set(json.load(f))
        except Exception:
            return set()

    def _save_js_urls(self):
        """
        保存 js_urls_store.json
        """
        with open(self.JS_URL_STORE, "w", encoding="utf-8") as f:
            json.dump(list(self.js_urls), f, ensure_ascii=False, indent=2)

    def _extract_domain(self, url):
        """
        从 URL 提取根域名
        """
        try:
            return url.split("//")[1].split("/")[0]
        except:
            return None


    def _render_with_drission(self, url, ua=None, proxy=None):
        """
        使用 ChromiumPage 渲染页面并返回 HTML
        """
        co = ChromiumOptions()
        co.headless(self.headless)

        # 设置代理
        if proxy:
            try:
                parsed = urlparse(proxy)
                has_auth = bool(parsed.username or parsed.password)
                if has_auth:
                    self.logger.warning(
                        "[DrissionPageMiddleware] Auth proxy is not supported by DrissionPage, skip proxy for render: %s",
                        proxy,
                    )
                    proxy = None

                if hasattr(co, "set_proxy"):
                    if proxy:
                        co.set_proxy(proxy)
                else:
                    if proxy:
                        co.set_argument("--proxy-server", proxy)
            except Exception as e:
                self.logger.warning(f"[DrissionPageMiddleware] Set proxy failed: {proxy}, error: {e}")

        page = None
        try:
            page = ChromiumPage(addr_or_opts=co)

            # 设置 UA
            if ua:
                page.set.headers({'User-Agent': ua})

            # 加载页面
            page.get(url, timeout=self.get_timeout)
            if hasattr(page.wait, "doc_loaded"):
                page.wait.doc_loaded()
            elif hasattr(page.wait, "load_complete"):
                page.wait.load_complete()

            # 获取 HTML
            return page.html
        finally:
            if page is not None:
                try:
                    if hasattr(page, "quit"):
                        page.quit()
                    else:
                        page.close()
                except Exception as e:
                    # 页面已断开时，关闭动作可能抛异常；清理失败不应影响抓取流程。
                    self.logger.warning(f"[DrissionPageMiddleware] Ignore close error: {e}")

    def _is_suspicious_page(self, response):
        """
        判断页面是否异常，可能需要 JS 渲染来自动化抓取：
        - Robot Check
        - CAPTCHA
        - Sign in
        - The request could not be satisfied
        - 反爬壳页面（大量 JS，无商品结构）
        - 页面没有搜索结果关键 DOM
        """
        text = (response.text or "").lower()
        body_len = len(text)
        status = response.status

        # 先看硬命中：这些通常就是挑战/反爬页，直接判可疑。
        hard_patterns = [
            "robot check",
            "captcha",
            "cf-challenge",
            "cf-turnstile",
            "the request could not be satisfied",
            "to discuss automated access to amazon data",
            "api-services-support@amazon.com",
            "sorry, we just need to make sure you're not a robot",
            "checking your browser",
            "access denied",
        ]
        if status in (403, 429, 503):
            return True
        if any(p in text for p in hard_patterns):
            return True

        score = 0

        # 文本太短通常是拦截页或跳转壳页。
        if body_len < 4000:
            score += 2

        # 存在前端埋点脚本，但缺少商品结构，往往是异常页。
        suspicious_js_signals = ["ue_t0", "ue_id", "ue_url", "ue_navtiming", "ue_furl", "ue_surl"]
        has_js_shell_signal = any(js in text for js in suspicious_js_signals)
        has_result_dom = (
            "data-component-type=\"s-search-result\"" in text
            or "s-result-item" in text
            or "s-main-slot" in text
        )
        if has_js_shell_signal and not has_result_dom:
            score += 2

        # 常见搜索页关键字段命中不足也可加分。
        expected_signals = [
            "s-search-result",
            "a-size-base-plus",
            "a-price",
            "s-pagination-next",
            "data-asin",
        ]
        hit_count = sum(1 for k in expected_signals if k in text)
        if hit_count <= 1:
            score += 2
        elif hit_count <= 2:
            score += 1

        # 登录/风控引导页信号。
        soft_anti_patterns = [
            "sign in",
            "verify",
            "unusual traffic",
            "automated access",
        ]
        if any(p in text for p in soft_anti_patterns):
            score += 1

        # 阈值留一点余量，避免误判正常但简化的页面。
        return score >= 3


    # ----------------------------------------------------------------------
    # Scrapy Hook
    # ----------------------------------------------------------------------

    def process_response(self, request, response, spider):
        url = response.url
        domain = self._extract_domain(url)

        # 从 Scrapy request 中获取 UA
        ua = request.headers.get("User-Agent", b"").decode() 

        # 从 Scrapy request 中获取 proxy
        proxy = request.meta.get("proxy")

        # -------------------------------
        # 1. 已知 JS 页面 → 直接渲染
        # -------------------------------
        if domain  in self.js_urls:
            spider.logger.info(f"[DrissionPageMiddleware] Known JS page, rendering: {url}")
            try:
                html = self._render_with_drission(url, ua=ua, proxy=proxy)
                return HtmlResponse(
                    url=url,
                    body=html,
                    encoding="utf-8",
                    request=request,
                )
            except Exception as e:
                spider.logger.error(f"[DrissionPageMiddleware] Render error on known JS page: {e}")
                return response

        # -------------------------------
        # 2. 可疑页面 → 尝试 JS 渲染
        # -------------------------------
        if self._is_suspicious_page(response):
            spider.logger.warning(f"[DrissionPageMiddleware] Suspicious page detected, trying JS render: {url}")

            try:
                html = self._render_with_drission(url, ua=ua, proxy=proxy)

                
                spider.logger.info(f"[DrissionPageMiddleware] JS render success, marking DOMAIN as JS page: {domain}")
                self.js_urls.add(domain)
                self._save_js_urls()

                return HtmlResponse(
                    url=url,
                    body=html,
                    encoding="utf-8",
                    request=request,
                )

            except Exception as e:
                spider.logger.error(f"[DrissionPageMiddleware] Render error: {e}")
                return response

        return response





class AmazonScraperSpiderMiddleware:
    # Not all methods need to be defined. If a method is not defined,
    # scrapy acts as if the spider middleware does not modify the
    # passed objects.

    @classmethod
    def from_crawler(cls, crawler):
        # This method is used by Scrapy to create your spiders.
        s = cls()
        crawler.signals.connect(s.spider_opened, signal=signals.spider_opened)
        return s

    def process_spider_input(self, response, spider):
        # Called for each response that goes through the spider
        # middleware and into the spider.

        # Should return None or raise an exception.
        return None

    def process_spider_output(self, response, result, spider):
        # Called with the results returned from the Spider, after
        # it has processed the response.

        # Must return an iterable of Request, or item objects.
        for i in result:
            yield i

    def process_spider_exception(self, response, exception, spider):
        # Called when a spider or process_spider_input() method
        # (from other spider middleware) raises an exception.

        # Should return either None or an iterable of Request or item objects.
        pass

    async def process_start(self, start):
        # Called with an async iterator over the spider start() method or the
        # maching method of an earlier spider middleware.
        async for item_or_request in start:
            yield item_or_request

    def spider_opened(self, spider):
        spider.logger.info("Spider opened: %s" % spider.name)


class AmazonScraperDownloaderMiddleware:
    # Not all methods need to be defined. If a method is not defined,
    # scrapy acts as if the downloader middleware does not modify the
    # passed objects.

    @classmethod
    def from_crawler(cls, crawler):
        # This method is used by Scrapy to create your spiders.
        s = cls()
        crawler.signals.connect(s.spider_opened, signal=signals.spider_opened)
        return s

    def process_request(self, request, spider):
        # Called for each request that goes through the downloader
        # middleware.

        # Must either:
        # - return None: continue processing this request
        # - or return a Response object
        # - or return a Request object
        # - or raise IgnoreRequest: process_exception() methods of
        #   installed downloader middleware will be called
        return None

    def process_response(self, request, response, spider):
        # Called with the response returned from the downloader.

        # Must either;
        # - return a Response object
        # - return a Request object
        # - or raise IgnoreRequest
        return response

    def process_exception(self, request, exception, spider):
        # Called when a download handler or a process_request()
        # (from other downloader middleware) raises an exception.

        # Must either:
        # - return None: continue processing this exception
        # - return a Response object: stops process_exception() chain
        # - return a Request object: stops process_exception() chain
        pass

    def spider_opened(self, spider):
        spider.logger.info("Spider opened: %s" % spider.name)
