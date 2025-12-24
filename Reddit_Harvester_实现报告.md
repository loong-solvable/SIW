# Reddit Harvester 模块实现报告

> **版本**: v4.1 (修正技术细节)  
> **日期**: 2024-12-24  
> **状态**: 待实施  
> **兼容性**: 与 SIW Intent Brain v0.1.0 完全兼容

---

## 0. v4.0 → v4.1 修正

| 问题 | v4.0 | v4.1 修正 |
|------|------|----------|
| CLI 分支执行 | 使用 `set_defaults(func=...)` | **使用 `args.command == "harvest"` 分支** |
| 测试导入 | `from tests.test_harvester import ...` | **使用 `tests/_fixtures.py` + `tests/__init__.py`（不 import conftest）** |
| doctor 新增检查 | 新增 Harvester 检查行 | **不新增，保持输出不变** |
| 未使用导入 | `E_UPSTREAM_HTTP` 未使用 | **移除该导入** |

---

## 1. 项目规则对齐确认

### 1.1 规则 §13 Harvester Module Rules

```
## 13) Harvester Module Rules (Optional Extension)
- Handle 429/503 errors gracefully with exponential backoff.  ✅ 实现指数退避
- Fail-closed: If harvesting fails, return empty results, do NOT crash.  ✅ 返回空列表
- Harvester output must be compatible with IntentBrain.score() input format.  ✅ 兼容
- Tests must use FakeHarvester with pre-recorded mock responses.  ✅ FakeHarvester
```

### 1.2 规则 §14 Completion Criteria

```
- [If harvester implemented] `siw-brain harvest --sub test --limit 1` works with mock or real data  ✅
```

---

## 2. 模块结构

```
src/siw_intent_brain/
├── harvester/                    # 新增目录
│   ├── __init__.py              # 模块导出
│   └── reddit_client.py         # Reddit 抓取客户端
```

符合当前包结构，不与现有模块冲突。

---

## 3. 核心代码实现

### 3.1 `harvester/reddit_client.py`

```python
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
```

### 3.2 `harvester/__init__.py`

```python
"""
Harvester module - Data collection from external sources.

Currently supports:
  - Reddit (via public .json endpoints)

Per project rules (§13):
  - Uses only public, unauthenticated APIs
  - Handles 429/503 with exponential backoff
  - Fail-closed: returns empty results on failure
"""

from .reddit_client import RedditHarvester, HarvestResult

__all__ = [
    "RedditHarvester",
    "HarvestResult",
]
```

---

## 4. CLI 扩展

### 4.1 cli.py 修改内容

#### 4.1.1 新增 harvester factory（在 `_get_brain` 函数后添加）

```python
# Harvester factory for testing
_harvester_factory: Optional[Callable[[], Any]] = None


def set_harvester_factory(factory: Optional[Callable[[], Any]]) -> None:
    """Set custom harvester factory for testing."""
    global _harvester_factory
    _harvester_factory = factory


def _get_harvester():
    """Get harvester instance (uses factory if set)."""
    if _harvester_factory is not None:
        return _harvester_factory()
    
    from .harvester import RedditHarvester
    return RedditHarvester()
```

#### 4.1.2 新增 harvest 子命令解析器（在 demo_parser 后添加）

```python
    # =========================================================================
    # harvest command
    # =========================================================================
    harvest_parser = subparsers.add_parser(
        "harvest",
        help="Harvest and score Reddit posts",
        description="Fetch posts from Reddit and score them for commercial intent.",
    )
    harvest_parser.add_argument(
        "--sub",
        required=True,
        help="Subreddit name (without r/)",
    )
    harvest_parser.add_argument(
        "--query",
        help="Search query (optional)",
    )
    harvest_parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Maximum number of posts to fetch (default: 10)",
    )
    harvest_parser.add_argument(
        "--sort",
        choices=["new", "hot", "top"],
        default="new",
        help="Sort order (default: new)",
    )
    harvest_parser.add_argument(
        "--config",
        help="Path to config YAML file",
    )
    harvest_parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose output to stderr",
    )
```

#### 4.1.3 新增命令分支（在 `if args.command == "demo":` 后添加）

```python
    if args.command == "harvest":
        return _cmd_harvest(args)
```

**完整的分支结构变为：**

```python
    if args.command == "score":
        return _cmd_score(args)
    
    if args.command == "validate":
        return _cmd_validate(args.json_file)
    
    if args.command == "doctor":
        return _cmd_doctor()
    
    if args.command == "demo":
        return _cmd_demo(args)
    
    if args.command == "harvest":
        return _cmd_harvest(args)
    
    return 1
```

#### 4.1.4 新增 `_cmd_harvest` 函数

```python
def _cmd_harvest(args: argparse.Namespace) -> int:
    """
    Execute harvest command.
    
    Fetches posts from Reddit and scores them.
    
    Output: JSONL to stdout (one JSON object per line)
    Progress: To stderr
    
    Returns:
      0: Success (may have fewer items than limit)
      1: Config/module error
    """
    # --- Enable logging if --verbose ---
    if getattr(args, "verbose", False):
        from .telemetry.logging import enable_logging
        enable_logging(True)
    
    # --- Get parameters ---
    subreddit = args.sub
    query = getattr(args, "query", None)
    limit = getattr(args, "limit", 10)
    sort = getattr(args, "sort", "new")
    
    # --- Initialize harvester ---
    harvester = _get_harvester()
    
    # --- Initialize brain ---
    try:
        brain = _get_brain(config_path=getattr(args, "config", None))
    except Exception as e:
        error_msg = str(e)
        if "api_key" in error_msg.lower() or "key" in error_msg.lower():
            print("ERROR: Configuration error (check OPENROUTER_API_KEY)", file=sys.stderr)
        else:
            print(f"ERROR: {error_msg}", file=sys.stderr)
        return 1
    
    # --- Harvest ---
    query_info = f" query='{query}'" if query else ""
    print(f"Fetching from r/{subreddit}{query_info}...", file=sys.stderr)
    
    result = harvester.fetch_posts(subreddit, query=query, limit=limit, sort=sort)
    
    # --- Check for errors ---
    if result.error_message:
        print(f"WARN: {result.error_message}", file=sys.stderr)
    
    # --- Score and output ---
    scored_count = 0
    
    for item in result.items:
        # Score
        card = brain.score(text=item["text"], context=item["context"])
        
        # Output (include source_meta)
        output = {
            "card": card,
            "source_meta": item.get("_meta", {}),
        }
        print(json.dumps(output, ensure_ascii=False))
        scored_count += 1
    
    # --- Summary ---
    print(
        f"Done: {scored_count} scored, {result.skipped_count} skipped (empty)",
        file=sys.stderr
    )
    return 0
```

---

## 5. 测试实现

### 5.1 测试共享代码：`tests/_fixtures.py`（推荐）

**原因**：`pytest` 会自动加载 `conftest.py` 的 fixture，但 **`conftest.py` 不是可稳定 import 的模块**（默认不在 import 路径中）。因此需要把可复用的 Fake 类放进一个**可导入模块**里。

同时，为了使用 `from tests._fixtures import ...`，需要将 `tests` 变成包。

#### 5.1.1 新增 `tests/__init__.py`

```python
# Make tests a package so we can import tests._fixtures in test modules.
```

#### 5.1.2 新增 `tests/_fixtures.py`

```python
"""
Shared fakes for offline tests (importable module).

NOTE:
- Do NOT import from conftest.py in tests. Put reusable fakes here instead.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional


# =============================================================================
# Harvest Result Mock
# =============================================================================

@dataclass
class FakeHarvestResult:
    """Mock HarvestResult for testing."""
    items: List[Dict[str, Any]]
    skipped_count: int = 0
    error_message: Optional[str] = None


# =============================================================================
# FakeHarvester Variants
# =============================================================================

class FakeHarvester:
    """
    Fake harvester that returns predefined data.
    
    Per project rules (§13): Tests must use FakeHarvester with pre-recorded mock responses.
    """
    
    def __init__(self, posts: Optional[List[Dict[str, Any]]] = None):
        self._posts = posts if posts is not None else self._default_posts()
    
    def _default_posts(self) -> List[Dict[str, Any]]:
        return [
            {
                "text": "Looking for a cheaper alternative to ToolX. Currently paying $59/mo.",
                "context": {
                    "subreddit": "SaaS",
                    "author": "test_user",
                    "permalink": "/r/SaaS/comments/abc123",
                    "title": "Cheaper ToolX alternative?",
                },
                "_meta": {
                    "created_utc": 1703500000,
                    "score": 42,
                    "num_comments": 15,
                    "id": "abc123",
                },
            },
            {
                "text": "Just discovered Rust and loving it!",
                "context": {
                    "subreddit": "rust",
                    "author": "rust_fan",
                    "permalink": "/r/rust/comments/def456",
                    "title": "Loving Rust",
                },
                "_meta": {
                    "created_utc": 1703400000,
                    "score": 100,
                    "num_comments": 30,
                    "id": "def456",
                },
            },
        ]
    
    def fetch_posts(
        self,
        subreddit: str,
        query: Optional[str] = None,
        limit: int = 10,
        sort: str = "new",
    ) -> FakeHarvestResult:
        """Return mock posts as HarvestResult."""
        items = self._posts[:limit]
        return FakeHarvestResult(items=items, skipped_count=0)


class FakeHarvesterEmpty(FakeHarvester):
    """FakeHarvester that returns empty results (simulates fail-closed)."""
    
    def fetch_posts(self, *args, **kwargs) -> FakeHarvestResult:
        return FakeHarvestResult(
            items=[],
            error_message="Simulated network error",
        )


class FakeHarvesterWithSkips(FakeHarvester):
    """FakeHarvester that simulates skipped empty posts."""
    
    def fetch_posts(self, *args, **kwargs) -> FakeHarvestResult:
        return FakeHarvestResult(
            items=self._default_posts()[:2],
            skipped_count=3,  # 模拟跳过了 3 个空帖子
        )
```

### 5.2 可选：`tests/conftest.py`（仅提供 fixture，不作为 import 目标）

如果你更喜欢 fixture 方式，可用 `conftest.py` **只暴露 fixture**，但测试代码**仍然从 `tests._fixtures` import Fake 类**。

```python
import pytest

from tests._fixtures import FakeHarvester, FakeHarvesterEmpty, FakeHarvesterWithSkips


@pytest.fixture
def fake_harvester():
    return FakeHarvester()


@pytest.fixture
def fake_harvester_empty():
    return FakeHarvesterEmpty()


@pytest.fixture
def fake_harvester_with_skips():
    return FakeHarvesterWithSkips()
```

### 5.3 `tests/test_harvester.py`（单元测试）

```python
"""
Tests for harvester module.

All tests are OFFLINE - use FakeHarvester with mock data.
Per project rules (§8): Tests must run offline with FakeHarvester.
"""

from __future__ import annotations

import json

from siw_intent_brain import validate_lead_card
from siw_intent_brain.config import BrainConfig
from siw_intent_brain.brain import IntentBrain
from siw_intent_brain.llm.types import ChatRequest, ChatResponse

from tests._fixtures import FakeHarvester, FakeHarvesterEmpty, FakeHarvesterWithSkips


# =============================================================================
# FakeClient for Brain Testing
# =============================================================================

class FakeClient:
    """Fake LLM client for offline testing."""
    
    def complete(self, req: ChatRequest) -> ChatResponse:
        return ChatResponse(
            content=json.dumps({
                "scores": {
                    "urgency": 0.7,
                    "pain_point_intensity": 0.8,
                    "commercial_relevance": 0.9,
                    "solution_seeking": 0.95,
                },
                "confidence": 0.9,
                "lead_tier": "S",
                "recommended_next_step": "offer_resource",
                "rationale": "High intent.",
                "extracted_signals": {
                    "problem_summary": "User seeking alternative",
                    "constraints": ["budget"],
                    "budget_hints": ["$59/mo"],
                    "tooling_stack": ["ToolX"],
                    "keywords": ["alternative", "cheaper"],
                },
                "safety_notes": [],
            }),
            raw={},
            latency_ms=50,
            retries=0,
            status_code=200,
        )


# =============================================================================
# Tests
# =============================================================================

class TestFakeHarvester:
    """Tests for FakeHarvester mock."""

    def test_returns_posts(self) -> None:
        harvester = FakeHarvester()
        result = harvester.fetch_posts("test")
        
        assert len(result.items) == 2
        assert result.items[0]["text"]
        assert result.items[0]["context"]["subreddit"]
        assert result.error_message is None

    def test_respects_limit(self) -> None:
        harvester = FakeHarvester()
        result = harvester.fetch_posts("test", limit=1)
        
        assert len(result.items) == 1


class TestFakeHarvesterEmpty:
    """Tests for fail-closed behavior (empty results)."""

    def test_returns_empty_on_error(self) -> None:
        harvester = FakeHarvesterEmpty()
        result = harvester.fetch_posts("test")
        
        assert result.items == []
        assert result.error_message is not None


class TestFakeHarvesterWithSkips:
    """Tests for skipped posts handling."""

    def test_reports_skipped_count(self) -> None:
        harvester = FakeHarvesterWithSkips()
        result = harvester.fetch_posts("test")
        
        assert len(result.items) == 2
        assert result.skipped_count == 3


class TestHarvestIntegration:
    """Integration tests using FakeHarvester + FakeClient."""

    def test_harvest_and_score_offline(self) -> None:
        """Full pipeline: harvest → score → validate."""
        # Setup
        harvester = FakeHarvester()
        cfg = BrainConfig(api_key="test-key")
        brain = IntentBrain(cfg, client=FakeClient())
        
        # Harvest
        result = harvester.fetch_posts("SaaS", limit=2)
        
        # Score each post
        for item in result.items:
            card = brain.score(text=item["text"], context=item["context"])
            
            # Validate
            errors = validate_lead_card(card)
            assert errors == [], f"Validation failed: {errors}"
            assert card["meta"]["model"] == "openai/gpt-4o-mini"

    def test_empty_harvest_no_crash(self) -> None:
        """Empty harvest result should not crash (fail-closed)."""
        harvester = FakeHarvesterEmpty()
        result = harvester.fetch_posts("test")
        
        assert result.items == []
        # No crash, just empty results
```

### 5.4 `tests/test_cli.py` 新增内容

```python
# =============================================================================
# 在文件顶部添加导入
# =============================================================================

from tests._fixtures import FakeHarvester, FakeHarvesterEmpty, FakeHarvesterWithSkips


# =============================================================================
# Test: harvest command（添加到文件末尾）
# =============================================================================

class TestHarvest:
    """Tests for harvest command (offline with FakeHarvester)."""

    @pytest.fixture(autouse=True)
    def reset_factories(self):
        """Reset factories after each test."""
        yield
        from siw_intent_brain.cli import set_brain_factory, set_harvester_factory
        set_brain_factory(None)
        set_harvester_factory(None)

    def test_harvest_returns_zero(self, capsys) -> None:
        """harvest command returns 0."""
        from siw_intent_brain.cli import main, set_brain_factory, set_harvester_factory
        
        set_brain_factory(make_fake_brain_factory())
        set_harvester_factory(lambda: FakeHarvester())
        
        result = main(["harvest", "--sub", "test", "--limit", "2"])
        
        assert result == 0

    def test_harvest_outputs_jsonl(self, capsys) -> None:
        """harvest outputs JSONL to stdout."""
        from siw_intent_brain.cli import main, set_brain_factory, set_harvester_factory
        
        set_brain_factory(make_fake_brain_factory())
        set_harvester_factory(lambda: FakeHarvester())
        
        main(["harvest", "--sub", "test", "--limit", "2"])
        
        captured = capsys.readouterr()
        # Each line should be valid JSON
        lines = [l for l in captured.out.strip().split("\n") if l]
        assert len(lines) == 2
        
        for line in lines:
            obj = json.loads(line)
            assert "card" in obj
            assert "source_meta" in obj

    def test_harvest_cards_are_valid(self, capsys) -> None:
        """harvest output cards pass validation."""
        from siw_intent_brain.cli import main, set_brain_factory, set_harvester_factory
        from siw_intent_brain import validate_lead_card
        
        set_brain_factory(make_fake_brain_factory())
        set_harvester_factory(lambda: FakeHarvester())
        
        main(["harvest", "--sub", "test", "--limit", "2"])
        
        captured = capsys.readouterr()
        lines = [l for l in captured.out.strip().split("\n") if l]
        
        for line in lines:
            obj = json.loads(line)
            errors = validate_lead_card(obj["card"])
            assert errors == []

    def test_harvest_reports_skipped(self, capsys) -> None:
        """harvest reports skipped posts to stderr."""
        from siw_intent_brain.cli import main, set_brain_factory, set_harvester_factory
        
        set_brain_factory(make_fake_brain_factory())
        set_harvester_factory(lambda: FakeHarvesterWithSkips())
        
        main(["harvest", "--sub", "test", "--limit", "5"])
        
        captured = capsys.readouterr()
        # stderr should mention skipped count
        assert "skipped" in captured.err.lower()

    def test_harvest_handles_empty_result(self, capsys) -> None:
        """harvest handles empty results gracefully (fail-closed)."""
        from siw_intent_brain.cli import main, set_brain_factory, set_harvester_factory
        
        set_brain_factory(make_fake_brain_factory())
        set_harvester_factory(lambda: FakeHarvesterEmpty())
        
        result = main(["harvest", "--sub", "test"])
        
        # Should still return 0 (fail-closed, not crash)
        assert result == 0
        captured = capsys.readouterr()
        # stderr should mention error/warning
        assert "warn" in captured.err.lower()
        # stdout should be empty (no cards)
        lines = [l for l in captured.out.strip().split("\n") if l]
        assert len(lines) == 0

    def test_harvest_requires_sub(self, capsys) -> None:
        """harvest requires --sub argument."""
        from siw_intent_brain.cli import main
        
        result = main(["harvest"])
        # argparse will print error and return 2
        assert result != 0
```

---

## 6. README.md 更新

在 CLI Reference 章节，`### siw-brain demo` 后添加：

```markdown
### `siw-brain harvest`

Harvest and score Reddit posts (optional module).

```bash
siw-brain harvest --sub SaaS --query "alternative" --limit 10
```

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `--sub` | Yes | — | Subreddit name (without r/) |
| `--query` | No | — | Search query |
| `--limit` | No | 10 | Maximum posts to fetch |
| `--sort` | No | new | Sort order (new, hot, top) |
| `--config` | No | — | Path to config YAML |
| `--verbose` | No | — | Enable verbose output |

Output: JSONL to stdout (one JSON object per line)

```json
{"card": {...}, "source_meta": {"created_utc": 1703500000, "score": 42}}
```

Notes:
- Requires `OPENROUTER_API_KEY` for scoring
- Some posts may be skipped if empty; actual count may be less than `--limit`
- Respects Reddit rate limits (1-2s per request)
```

**不修改 doctor 输出示例** - 保持现有内容不变。

---

## 7. 验收标准

### 7.1 自动化测试

```bash
# 1. 现有测试不受影响
pytest -q
# Expected: 400+ passed ✅

# 2. 新增测试全部通过
pytest tests/test_harvester.py tests/test_cli.py::TestHarvest -v
# Expected: all passed ✅
```

### 7.2 手动验收

```bash
# 1. doctor 仍返回 0
siw-brain doctor
# Expected: exit code 0, 输出与 README 示例一致 ✅

# 2. harvest 命令输出 JSONL（需要网络 + API key）
# Linux/macOS:
export OPENROUTER_API_KEY="sk-or-v1-..."
# Windows PowerShell:
$env:OPENROUTER_API_KEY="sk-or-v1-..."

siw-brain harvest --sub SaaS --query "alternative" --limit 3
# Expected: 3 lines of JSONL to stdout ✅
# stderr: "Done: 3 scored, 0 skipped (empty)" ✅

# 3. 验收标准 §14
siw-brain harvest --sub test --limit 1
# Expected: works with real data ✅
```

---

## 8. 文件变更清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `src/siw_intent_brain/harvester/__init__.py` | **新增** | 模块导出 |
| `src/siw_intent_brain/harvester/reddit_client.py` | **新增** | Reddit 抓取客户端（含指数退避） |
| `src/siw_intent_brain/cli.py` | **修改** | 新增 harvest 命令分支 + set_harvester_factory |
| `tests/__init__.py` | **新增** | 使 tests 成为可导入包 |
| `tests/_fixtures.py` | **新增** | FakeHarvester 等共享 Fake 类（可导入模块） |
| `tests/conftest.py` | **修改**（可选） | 仅注册 fixture，从 `_fixtures` 导入 Fake 类 |
| `tests/test_harvester.py` | **新增** | Harvester 离线测试 |
| `tests/test_cli.py` | **修改** | harvest 命令测试 |
| `README.md` | **修改** | CLI Reference 添加 harvest 说明 |

**不修改：**
- ❌ `brain.py`
- ❌ `contracts.py`
- ❌ `prompt/builder.py`
- ❌ `errors.py`
- ❌ doctor 输出格式/检查项

---

## 9. 实施顺序

1. **创建 `harvester/` 模块**
   - `src/siw_intent_brain/harvester/__init__.py`
   - `src/siw_intent_brain/harvester/reddit_client.py`（含指数退避，无未使用导入）

2. **创建测试共享模块**
   - `tests/__init__.py`（空文件，使 tests 成为包）
   - `tests/_fixtures.py`（FakeHarvester 等 Fake 类）

3. **（可选）修改 `tests/conftest.py`**
   - 从 `tests._fixtures` 导入 Fake 类
   - 仅注册 pytest fixture

4. **创建 `tests/test_harvester.py`**
   - 从 `tests._fixtures` 导入 FakeHarvester

5. **修改 `src/siw_intent_brain/cli.py`**
   - 添加 set_harvester_factory
   - 添加 harvest 子命令解析器
   - 添加 `if args.command == "harvest":` 分支
   - 添加 `_cmd_harvest` 函数

6. **修改 `tests/test_cli.py`**
   - 从 `tests._fixtures` 导入 FakeHarvester
   - 添加 TestHarvest 类

7. **更新 `README.md`**
   - CLI Reference 添加 harvest 说明

8. **运行验证**
   - `pytest -q` 全绿
   - 手动验收

---

## 10. 对齐确认清单

| 规则/问题 | 状态 |
|-----------|------|
| §13 429/503 指数退避 | ✅ `_request_with_backoff` 实现 |
| §13 Fail-closed 返回空结果 | ✅ `HarvestResult(items=[])` |
| §13 输出兼容 IntentBrain.score() | ✅ `{"text": ..., "context": ...}` |
| §8 测试离线 + FakeHarvester | ✅ `tests/_fixtures.py` + `test_harvester.py` |
| §14 `siw-brain harvest --sub test --limit 1` | ✅ 命令实现 |
| CLI 使用 `args.command` 分支 | ✅ 不使用 set_defaults |
| 测试导入使用 `tests._fixtures` | ✅ 不 import conftest |
| doctor 输出不变 | ✅ 不新增检查行 |
| 无未使用导入 | ✅ 移除 E_UPSTREAM_HTTP |

---

**报告完成。所有技术细节已修正并对齐项目规则。**
