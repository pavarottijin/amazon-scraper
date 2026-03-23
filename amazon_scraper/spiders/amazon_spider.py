from urllib.parse import parse_qs, quote_plus, urlencode, urljoin, urlparse, urlunparse

import scrapy

from amazon_scraper.items import AmazonScraperItem


class AmazonSpider(scrapy.Spider):
    name = "AmazonSpider"
    allowed_domains = ["amazon.com"]

    def __init__(self, keyword="python", min_products=50, *args, **kwargs):
        """
        初始化参数：
        - keyword: 搜索关键词
        - min_products: 最小抓取数量，达到该数量后在当前页结束时停止翻页
        """
        super().__init__(*args, **kwargs)
        self.keyword = keyword
        self.min_products = max(0, int(min_products))
        self.count = 0
        self.found_any_product = False
        self.base_url = "https://www.amazon.com/"

    # ----------------------------------------------------------------------
    # 起始请求
    # ----------------------------------------------------------------------

    def start_requests(self):
        url = f"{self.base_url}s?k={quote_plus(self.keyword)}"
        yield scrapy.Request(
            url,
            callback=self.parse
        )

    def _build_fallback_next_url(self, current_url):
        parsed = urlparse(current_url)
        q = parse_qs(parsed.query)

        try:
            current_page = int(q.get("page", ["1"])[0])
        except ValueError:
            current_page = 1

        q["page"] = [str(current_page + 1)]
        if "k" not in q:
            q["k"] = [self.keyword]

        new_query = urlencode(q, doseq=True)
        return urlunparse(parsed._replace(query=new_query))

    # ----------------------------------------------------------------------
    # 解析搜索结果页
    # ----------------------------------------------------------------------
    
    def parse(self, response):
        # 只抓真实商品卡片，避免抓到容器/广告占位节点
        products = response.css('div.s-main-slot div[data-component-type="s-search-result"][data-asin]')
        products = [p for p in products if p.attrib.get("data-asin")]
        
        if not products:
            self.logger.error(f"[Spider] No products found on page: {response.url}")
            title = response.css("title::text").get()
            self.logger.info(f"[Spider] Page title: {title}")
            if self.found_any_product and self.count < self.min_products:
                self.logger.warning(
                    f"[Spider] Crawl stopped at {self.count} items, below min_products={self.min_products}."
                )
            elif not self.found_any_product:
                self.logger.warning("[Spider] No products found at all, skip min_products check.")
            return

        self.logger.info(f"[Spider] Product cards found: {len(products)}")

        # ------------------------------------------------------------------
        # 遍历每个商品
        # ------------------------------------------------------------------
        for p in products:

            try:
                item = AmazonScraperItem()

                # ------------------ 标题 ------------------
                title = p.css("h2 span::text").get()
                item["title"] = title.strip() if title else None

                # ------------------ 评分 ------------------
                rating_text = (
                    p.css('span[aria-label*="out of 5 stars"]::attr(aria-label)').get()
                    or p.css("span.a-icon-alt::text").get()
                )
                item["rating"] = rating_text

                # ------------------ 评论数 ------------------
                review_text = (
                    p.css('a[href*="#customerReviews"] span.a-size-base::text').get()
                    or p.css('a[href*="#customerReviews"] span::text').get()
                    or p.css('a[href*="customerReviews"] span.a-size-base::text').get()
                    or p.css('a[href*="customerReviews"]::attr(aria-label)').get()
                    or p.css("span.a-size-base.s-underline-text::text").get()
                    or p.css('span[aria-label*="ratings"]::attr(aria-label)').get()
                    or p.css('span[aria-label*="reviews"]::attr(aria-label)').get()
                    or p.css('span[aria-label*="评分"]::attr(aria-label)').get()
                    or p.css('span[aria-label*="评价"]::attr(aria-label)').get()
                    or p.xpath('.//*[contains(@aria-label, "ratings") or contains(@aria-label, "reviews") or contains(@aria-label, "评分") or contains(@aria-label, "评价")]/@aria-label').get()
                )
                item["review_nb"] = review_text

                # ------------------ 图片 ------------------
                item["img"] = p.css("img.s-image::attr(src)").get()

                # ------------------ URL & ASIN ------------------
                asin = p.attrib.get("data-asin")
                href = (
                    p.css("h2 a::attr(href)").get()
                    or p.css('a.a-link-normal.s-no-outline::attr(href)').get()
                    or p.css('a[href*="/dp/"]::attr(href)').get()
                )
                if href:
                    full_url = urljoin(self.base_url, href)
                    # 去掉跟踪参数，保留主链接。
                    clean_url = full_url.split("?")[0].split("/ref=")[0]
                    item["url"] = clean_url
                elif asin:
                    # 页面结构变化时，至少可由 ASIN 组装稳定商品链接。
                    item["url"] = f"{self.base_url}dp/{asin}"
                else:
                    item["url"] = None
                item["asin"] = asin

                # ------------------ 价格 ------------------
                price_text = (
                    p.css("span.a-price span.a-offscreen::text").get()
                    or p.css("span.a-offscreen::text").get()
                )
                item["prices_main"] = price_text

                self.count += 1
                self.found_any_product = True
                yield item

            except Exception as e:
                self.logger.error(f"[Spider] Error parsing product: {e}")

        # ------------------------------------------------------------------
        # 下一页
        # ------------------------------------------------------------------
        if self.count >= self.min_products:
            self.logger.info(
                f"[Spider] Reached min_products={self.min_products}, stop at current page with {self.count} items."
            )
            return

        next_page = (
            response.css("a.s-pagination-next::attr(href)").get()
            or response.css("ul.a-pagination li.a-last a::attr(href)").get()
            or response.css('a[aria-label*="next" i]::attr(href)').get()
            or response.css('a[aria-label*="下一页"]::attr(href)').get()
        )
        if next_page:
            next_url = urljoin(self.base_url, next_page)
            self.logger.info(f"[Spider] Next page: {next_url}")
            yield scrapy.Request(next_url, callback=self.parse)
        else:
            fallback_url = self._build_fallback_next_url(response.url)
            self.logger.warning(
                f"[Spider] Next page link not found, fallback page url: {fallback_url}"
            )
            yield scrapy.Request(fallback_url, callback=self.parse)
