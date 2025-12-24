"""
Reddit data harvester for SIW Intent Brain.

Uses Reddit's public .json endpoints (no authentication required).
Respects rate limits and handles errors gracefully.

Per project rules (§13):
- Handle 429/503 with exponential backoff
- Fail-closed: return empty results on failure, do NOT crash
- Output compatible with IntentBrain.score() input format
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import requests


# Module-level logger (INFO level per §13)
_logger = logging.getLogger(__name__)


@dataclass
class HarvestResult:
    """
    抓取结果。
    
    Attributes:
        items: 成功抓取的帖子列表
        skipped_count: 跳过的空帖子数
        error_message: 如果抓取失败，错误信息（用于日志/stderr）
    """
    items: List[Dict[str, Any]]
    skipped_count: int = 0
    error_message: Optional[str] = None


class RedditHarvester:
    """
    Reddit 帖子抓取器。
    
    使用公开 .json 接口，无需认证。
    
    行为规则（符合 §13）：
    - 遵守速率限制（1-2s/请求）
    - 429/503 指数退避重试
    - 失败时返回空结果，不 crash
    """
    
    BASE_URL = "https://www.reddit.com"
    DEFAULT_USER_AGENT = "SIW-Harvester/1.0 (Intent Scoring Tool)"
    REQUEST_DELAY = 1.5  # 秒
    TIMEOUT = 10  # 秒
    MAX_RETRIES = 3
    BACKOFF_BASE = 2.0  # 指数退避基数
    
    # 可重试的状态码
    RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
    
    def __init__(
        self,
        user_agent: Optional[str] = None,
        request_delay: float = REQUEST_DELAY,
        timeout: int = TIMEOUT,
        max_retries: int = MAX_RETRIES,
    ):
        self.user_agent = user_agent or self.DEFAULT_USER_AGENT
        self.request_delay = request_delay
        self.timeout = timeout
        self.max_retries = max_retries
        self._last_request_time: float = 0
    
    def fetch_posts(
        self,
        subreddit: str,
        query: Optional[str] = None,
        limit: int = 10,
        sort: str = "new",
    ) -> HarvestResult:
        """
        抓取 Reddit 帖子。
        
        Args:
            subreddit: 子版块名称（不含 r/）
            query: 搜索关键词（可选）
            limit: 最大抓取数量
            sort: 排序方式 (new, hot, top)
        
        Returns:
            HarvestResult:
              - items: 可评分的帖子列表 [{"text": ..., "context": ..., "_meta": ...}, ...]
              - skipped_count: 跳过的空帖子数
              - error_message: 错误信息（如果失败）
        
        Fail-closed behavior (§13):
            失败时返回空列表，不抛异常。
        """
        # 构建 URL
        if query:
            url = f"{self.BASE_URL}/r/{subreddit}/search.json"
            params = {"q": query, "sort": sort, "limit": limit, "restrict_sr": "true"}
        else:
            url = f"{self.BASE_URL}/r/{subreddit}/{sort}.json"
            params = {"limit": limit}
        
        # 发起请求（带指数退避）
        response = self._request_with_backoff(url, params)
        
        if response is None:
            # 失败 → 返回空结果（fail-closed）
            return HarvestResult(
                items=[],
                error_message="Request failed after retries",
            )
        
        # 解析响应
        try:
            data = response.json()
            children = data.get("data", {}).get("children", [])
        except (ValueError, KeyError) as e:
            _logger.warning(f"Invalid JSON response from {url}: {e}")
            return HarvestResult(
                items=[],
                error_message=f"Invalid JSON response: {e}",
            )
        
        # 转换为可评分格式
        items: List[Dict[str, Any]] = []
        skipped_count = 0
        
        for child in children:
            post = child.get("data", {})
            item = self._build_scorable_item(post)
            if item is None:
                skipped_count += 1
            else:
                items.append(item)
        
        _logger.info(f"Fetched {len(items)} posts from r/{subreddit} (skipped {skipped_count} empty)")
        
        return HarvestResult(
            items=items,
            skipped_count=skipped_count,
        )
    
    def _request_with_backoff(
        self,
        url: str,
        params: Dict[str, Any],
    ) -> Optional[requests.Response]:
        """
        带指数退避的 HTTP 请求。
        
        429/503 等可重试错误会指数退避重试。
        最终失败返回 None（fail-closed）。
        """
        for attempt in range(self.max_retries + 1):
            try:
                # 速率限制
                self._rate_limit()
                
                _logger.info(f"Requesting {url} (attempt {attempt + 1}/{self.max_retries + 1})")
                
                response = requests.get(
                    url,
                    params=params,
                    headers={"User-Agent": self.user_agent},
                    timeout=self.timeout,
                )
                
                # 成功
                if response.status_code == 200:
                    return response
                
                # 可重试错误
                if response.status_code in self.RETRYABLE_STATUS_CODES:
                    if attempt < self.max_retries:
                        delay = self.BACKOFF_BASE ** attempt
                        _logger.warning(
                            f"Got {response.status_code}, retrying in {delay:.1f}s..."
                        )
                        time.sleep(delay)
                        continue
                
                # 不可重试错误
                _logger.warning(f"Request failed with status {response.status_code}")
                return None
                
            except requests.Timeout:
                if attempt < self.max_retries:
                    delay = self.BACKOFF_BASE ** attempt
                    _logger.warning(f"Timeout, retrying in {delay:.1f}s...")
                    time.sleep(delay)
                    continue
                _logger.warning(f"Request timeout after {self.max_retries + 1} attempts")
                return None
                
            except requests.RequestException as e:
                _logger.warning(f"Request failed: {type(e).__name__}: {e}")
                return None
        
        return None
    
    def _build_scorable_item(self, post: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        将 Reddit 帖子转换为 IntentBrain.score() 可接受的格式。
        
        输出格式（符合 §13）：
        - text: The content to analyze (title + body)
        - context: Metadata dict (subreddit, author, permalink, etc.)
        
        策略：
        - 如果 title + selftext 都为空 → 返回 None（跳过）
        - 如果只有 selftext 为空 → 只用 title
        """
        title = (post.get("title") or "").strip()
        selftext = (post.get("selftext") or "").strip()
        
        # 跳过被删除/移除的帖子
        if selftext in ("[removed]", "[deleted]"):
            selftext = ""
        
        # 组合文本
        if title and selftext:
            text = f"{title}\n\n{selftext}"
        elif title:
            text = title
        elif selftext:
            text = selftext
        else:
            return None  # 跳过完全空的帖子
        
        return {
            "text": text,
            "context": {
                "subreddit": post.get("subreddit", ""),
                "author": post.get("author", ""),
                "permalink": post.get("permalink", ""),
                "title": title,
            },
            # 额外元数据（不传给 LLM，供下游使用）
            "_meta": {
                "created_utc": post.get("created_utc", 0),
                "score": post.get("score", 0),
                "num_comments": post.get("num_comments", 0),
                "id": post.get("id", ""),
                "url": post.get("url", ""),
            },
        }
    
    def _rate_limit(self) -> None:
        """遵守速率限制"""
        elapsed = time.time() - self._last_request_time
        if elapsed < self.request_delay:
            time.sleep(self.request_delay - elapsed)
        self._last_request_time = time.time()

