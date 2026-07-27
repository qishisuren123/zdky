"""
Twitter/X collector implemented with Scweet.

Scweet authenticates with your own browser cookies/auth_token and scrapes X web
GraphQL endpoints without an official Twitter API key.

Disabled by default (see ``config.example.json``'s ``twitter.enabled``). Using this
collector means using your own X/Twitter account and cookies at your own risk,
subject to X's Terms of Service — this is not an officially sanctioned integration.
"""

import hashlib
import json
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = Path(os.getenv("AUTORESEARCH_CONFIG", REPO_ROOT / "config.local.json"))
DEFAULT_COOKIES_PATH = Path(os.getenv("TWITTER_COOKIES_PATH", REPO_ROOT / "twitter_cookies.local.json"))
DEFAULT_SCWEET_DB_PATH = Path(os.getenv("SCWEET_DB_PATH", REPO_ROOT / "scweet_state.local.db"))
DEFAULT_OUTPUTS_DIR = Path(os.getenv("AUTORESEARCH_OUTPUT_DIR", REPO_ROOT / "outputs"))
DEFAULT_DAILY_REQUESTS_LIMIT = 200
DEFAULT_DAILY_TWEETS_LIMIT = 2000

# AI 领域有影响力的研究者账号（screen_name）
INFLUENTIAL_ACCOUNTS = [
    "karpathy",        # Andrej Karpathy
    "ylecun",          # Yann LeCun
    "fchollet",        # Francois Chollet
    "hardmaru",        # David Ha
    "srush_nlp",       # Alexander Rush
    "rasbt",           # Sebastian Raschka
    "jeremyphoward",   # Jeremy Howard
    "NandoDF",         # Nando de Freitas
    "drfeifei",        # Fei-Fei Li
    "Miles_Brundage",  # Miles Brundage
    "GaryMarcus",      # Gary Marcus
    "poolio",          # Jonathan Frankle
    "cwolferesearch",  # Charles Wolfe
    "huggingface",     # HuggingFace 官方
    "GoogleDeepMind",  # DeepMind 官方
    "OpenAI",          # OpenAI 官方
    "AnthropicAI",     # Anthropic 官方
    "AIatMeta",        # Meta AI 官方
]

# 关键词搜索（每条对应一个查询）
SEARCH_QUERIES = [
    "arxiv lang:en -is:retweet min_faves:20",
    '"new paper" (LLM OR "language model" OR multimodal) lang:en -is:retweet min_faves:10',
    '"reasoning" (arxiv OR benchmark) lang:en -is:retweet min_faves:15',
    "site:arxiv.org lang:en -is:retweet min_faves:10",
]


def _load_config() -> Dict[str, Any]:
    """Read twitter config from the local AutoResearch config file."""
    try:
        cfg = json.loads(CONFIG_PATH.expanduser().read_text())
        twitter_cfg = cfg.get("twitter", {})
        return twitter_cfg if isinstance(twitter_cfg, dict) else {}
    except Exception:
        return {}


def _get_cookies_path(cfg: Optional[Dict[str, Any]] = None) -> Path:
    cfg = cfg if cfg is not None else _load_config()
    configured = cfg.get("cookies_path") or cfg.get("cookies_file") or os.getenv("TWITTER_COOKIES_PATH")
    return Path(configured).expanduser() if configured else DEFAULT_COOKIES_PATH.expanduser()


def _cookies_to_dict(data: Any) -> Dict[str, str]:
    """Normalize common browser-cookie exports to {name: value}."""
    if isinstance(data, dict) and isinstance(data.get("cookies"), list):
        data = data["cookies"]

    if isinstance(data, dict):
        return {str(k): str(v) for k, v in data.items() if v}

    if isinstance(data, list):
        cookies: Dict[str, str] = {}
        for item in data:
            if isinstance(item, dict) and "name" in item and "value" in item:
                cookies[str(item["name"])] = str(item["value"])
        return cookies

    return {}


def _load_cookie_values(path: Path) -> Dict[str, str]:
    if not path.exists():
        return {}
    try:
        return _cookies_to_dict(json.loads(path.read_text()))
    except Exception:
        return {}


def _looks_like_scweet_accounts_file(path: Path) -> bool:
    """Scweet multi-account files are [{username, cookies, proxy?}, ...]."""
    if not path.exists():
        return False
    try:
        data = json.loads(path.read_text())
    except Exception:
        return False
    return isinstance(data, list) and any(
        isinstance(item, dict) and isinstance(item.get("cookies"), dict)
        for item in data
    )


def _get_attr(record: Any, *names: str, default: Any = "") -> Any:
    for name in names:
        if isinstance(record, dict) and name in record:
            return record[name]
        if hasattr(record, name):
            return getattr(record, name)
    return default


def _get_user_fields(user: Any) -> Tuple[str, str]:
    if isinstance(user, dict):
        screen_name = user.get("screen_name") or user.get("username") or user.get("id") or ""
        name = user.get("name") or screen_name
        return str(screen_name), str(name)
    screen_name = _get_attr(user, "screen_name", "username", "id", default="")
    name = _get_attr(user, "name", default=screen_name)
    return str(screen_name or ""), str(name or screen_name or "")


def _to_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _tweet_to_post(tweet: Any, source_label: str = "twitter_search") -> Dict[str, Any]:
    """Convert a Scweet tweet record to the pipeline's standard post format."""
    text = str(_get_attr(tweet, "text", "full_text", "raw_text", default="") or "")
    tweet_id = str(_get_attr(tweet, "tweet_id", "id", default="") or "")
    user = _get_attr(tweet, "user", "author", default={})
    screen_name, name = _get_user_fields(user)

    favorite_count = _to_int(_get_attr(tweet, "likes", "favorite_count", "like_count", default=0))
    retweet_count = _to_int(_get_attr(tweet, "retweets", "retweet_count", default=0))
    reply_count = _to_int(_get_attr(tweet, "comments", "reply_count", "replies", default=0))
    created_at = _get_attr(tweet, "timestamp", "created_at", "date", default="") or ""

    url = str(_get_attr(tweet, "tweet_url", "url", default="") or "")
    if not url and tweet_id and screen_name:
        url = f"https://x.com/{screen_name}/status/{tweet_id}"

    engagement = favorite_count + retweet_count * 3 + reply_count * 2
    author = f"{name} (@{screen_name})" if screen_name else name
    title_prefix = f"[{name}@{screen_name}]" if screen_name else f"[{name}]"

    return {
        "source": source_label,
        "source_category": "community",
        "title": f"{title_prefix} {text[:120]}",
        "url": url,
        "score": engagement,
        "num_comments": reply_count,
        "summary": text[:500],
        "author": author,
        "created": str(created_at),
        "favorite_count": favorite_count,
        "retweet_count": retweet_count,
        "collected_at": datetime.now().isoformat(),
        "raw_text": text,
    }


def _get_output_dir(cfg: Optional[Dict[str, Any]] = None) -> Path:
    cfg = cfg if cfg is not None else _load_config()
    configured = cfg.get("output_dir") or cfg.get("save_dir")
    return Path(configured) if configured else DEFAULT_OUTPUTS_DIR


def _fingerprint(value: str, chars: int = 12) -> str:
    return hashlib.sha1(value.encode("utf-8")).hexdigest()[:chars]


def _get_scweet_db_path(cfg: Dict[str, Any], auth_token: str = "") -> Path:
    configured = cfg.get("scweet_db_path") or cfg.get("db_path")
    if configured:
        return Path(configured)
    if auth_token:
        return DEFAULT_SCWEET_DB_PATH.with_name(
            f"{DEFAULT_SCWEET_DB_PATH.stem}_{_fingerprint(auth_token)}{DEFAULT_SCWEET_DB_PATH.suffix}"
        )
    return DEFAULT_SCWEET_DB_PATH


def _is_account_pool_exhausted(exc: BaseException) -> bool:
    return exc.__class__.__name__ == "AccountPoolExhausted"


def _get_scweet_client():
    try:
        from Scweet import Scweet
        from Scweet.config import ScweetConfig
    except ImportError:
        print("  [Twitter] Scweet 未安装：pip install -U Scweet")
        return None

    cfg = _load_config()
    cookies_path = _get_cookies_path(cfg)
    cookie_values = _load_cookie_values(cookies_path)
    auth_token = (
        cookie_values.get("auth_token")
        or cfg.get("auth_token")
        or os.getenv("SCWEET_AUTH_TOKEN")
        or os.getenv("TWITTER_AUTH_TOKEN")
    )
    proxy = (
        cfg.get("proxy")
        or os.getenv("HTTPS_PROXY")
        or os.getenv("https_proxy")
        or os.getenv("HTTP_PROXY")
        or os.getenv("http_proxy")
    )
    db_path = _get_scweet_db_path(cfg, auth_token or "")

    output_dir = _get_output_dir(cfg)
    output_dir.mkdir(parents=True, exist_ok=True)
    scweet_config = ScweetConfig(
        db_path=str(db_path),
        proxy=proxy,
        save_dir=str(output_dir),
        save_format=cfg.get("save_format", "json"),
        daily_requests_limit=int(cfg.get("daily_requests_limit", DEFAULT_DAILY_REQUESTS_LIMIT)),
        daily_tweets_limit=int(cfg.get("daily_tweets_limit", DEFAULT_DAILY_TWEETS_LIMIT)),
        manifest_scrape_on_init=bool(cfg.get("manifest_scrape_on_init", False)),
    )

    kwargs: Dict[str, Any] = {"config": scweet_config, "db_path": str(db_path)}

    if _looks_like_scweet_accounts_file(cookies_path):
        kwargs["cookies_file"] = str(cookies_path)
        auth_desc = f"cookies_file={cookies_path}"
    elif cookie_values.get("auth_token"):
        kwargs["cookies"] = cookie_values
        auth_desc = f"cookies token={_fingerprint(cookie_values['auth_token'], 8)} db={db_path.name}"
    elif auth_token:
        kwargs["auth_token"] = auth_token
        auth_desc = f"auth_token={_fingerprint(auth_token, 8)} db={db_path.name}"
    else:
        print("  [Twitter] 未配置 Scweet 认证信息，返回空。")
        print(f"  [Twitter] 请在 {cookies_path} 放入 auth_token cookie，")
        print("  [Twitter] 或在 config.json['twitter']['auth_token'] / TWITTER_AUTH_TOKEN 中配置。")
        return None

    try:
        client = Scweet(**kwargs)
        print(f"  [Twitter] Scweet 初始化成功: {auth_desc}")
        return client
    except Exception as exc:
        print(f"  [Twitter] Scweet 初始化失败: {type(exc).__name__}: {exc}")
        return None


def _search_tweets(
    client: Any,
    query: str,
    since_date: str,
    count: int,
    save_raw: bool = True,
    save_name: Optional[str] = None,
) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    try:
        tweets = client.search(
            query,
            since=since_date,
            display_type="Latest",
            limit=count,
            save=save_raw,
            save_format="json",
            save_name=save_name,
        )
        for tweet in tweets or []:
            results.append(_tweet_to_post(tweet, source_label="twitter_search"))
        print(f"  [Twitter] 搜索 '{query[:50]}...' -> {len(results)} 条")
    except TypeError:
        try:
            tweets = client.search(
                f"{query} since:{since_date}",
                limit=count,
                save=save_raw,
                save_format="json",
                save_name=save_name,
            )
            for tweet in tweets or []:
                results.append(_tweet_to_post(tweet, source_label="twitter_search"))
            print(f"  [Twitter] 搜索 '{query[:50]}...' -> {len(results)} 条")
        except Exception as exc:
            if _is_account_pool_exhausted(exc):
                raise
            print(f"  [Twitter] 搜索失败 '{query[:50]}': {type(exc).__name__}: {exc!r}")
    except Exception as exc:
        if _is_account_pool_exhausted(exc):
            raise
        print(f"  [Twitter] 搜索失败 '{query[:50]}': {type(exc).__name__}: {exc!r}")
    return results


def _get_user_tweets(
    client: Any,
    screen_name: str,
    count: int,
    save_raw: bool = True,
    save_name: Optional[str] = None,
) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    try:
        tweets = client.get_profile_tweets(
            [screen_name],
            limit=count,
            save=save_raw,
            save_format="json",
            save_name=save_name,
        )
        for tweet in tweets or []:
            results.append(_tweet_to_post(tweet, source_label=f"twitter_@{screen_name}"))
        print(f"  [Twitter] @{screen_name} -> {len(results)} 条推文")
    except Exception as exc:
        if _is_account_pool_exhausted(exc):
            raise
        print(f"  [Twitter] @{screen_name} 获取失败: {type(exc).__name__}: {exc!r}")
    return results


def _dedupe_posts(posts: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen = set()
    unique: List[Dict[str, Any]] = []
    for post in posts:
        key = post.get("url") or (post.get("author"), post.get("created"), post.get("raw_text"))
        if key in seen:
            continue
        seen.add(key)
        unique.append(post)
    return unique


def _save_standard_posts(posts: List[Dict[str, Any]], output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    today = datetime.now().strftime("%Y%m%d")
    dated_path = output_dir / f"twitter_posts_{today}.json"
    latest_path = output_dir / "twitter_posts_latest.json"
    payload = json.dumps(posts, ensure_ascii=False, indent=2)
    dated_path.write_text(payload, encoding="utf-8")
    latest_path.write_text(payload, encoding="utf-8")
    return dated_path


def collect_twitter(
    search_days: int = 7,
    max_per_query: int = 20,
    max_per_account: int = 8,
    accounts: Optional[List[str]] = None,
    queries: Optional[List[str]] = None,
    min_engagement: int = 5,
    save: bool = True,
    save_raw: bool = True,
    save_empty: bool = False,
) -> List[Dict[str, Any]]:
    """
    Collect Twitter/X posts using Scweet and return AutoResearch standard posts.

    Parameters match src/collectors/twitter_collector.py:
      search_days     - search tweets from the most recent N days
      max_per_query   - maximum tweets per search query
      max_per_account - maximum tweets per influential account
      accounts        - optional override for INFLUENTIAL_ACCOUNTS
      queries         - optional override for SEARCH_QUERIES
      min_engagement  - filter posts with score lower than this value
      save            - save standardized posts to AutoResearch/outputs
      save_raw        - let Scweet save raw search/profile results to AutoResearch/outputs
      save_empty      - overwrite output files even when zero posts are collected
    """
    cfg = _load_config()
    output_dir = _get_output_dir(cfg)
    client = _get_scweet_client()
    if client is None:
        return []

    selected_accounts = accounts if accounts is not None else INFLUENTIAL_ACCOUNTS
    selected_queries = queries if queries is not None else SEARCH_QUERIES
    since_date = (datetime.now(timezone.utc) - timedelta(days=search_days)).strftime("%Y-%m-%d")

    posts: List[Dict[str, Any]] = []

    exhausted = False

    for idx, query in enumerate(selected_queries, start=1):
        save_name = f"twitter_search_{idx}_{since_date}"
        try:
            posts.extend(_search_tweets(client, query, since_date, max_per_query, save_raw, save_name))
        except Exception as exc:
            if not _is_account_pool_exhausted(exc):
                raise
            exhausted = True
            print(f"  [Twitter] 账号池已耗尽，停止本轮采集: {exc}")
            break
        time.sleep(1.5)

    if not exhausted:
        for screen_name in selected_accounts:
            save_name = f"twitter_profile_{screen_name}"
            try:
                posts.extend(_get_user_tweets(client, screen_name, max_per_account, save_raw, save_name))
            except Exception as exc:
                if not _is_account_pool_exhausted(exc):
                    raise
                exhausted = True
                print(f"  [Twitter] 账号池已耗尽，停止本轮采集: {exc}")
                break
            time.sleep(1.0)

    unique = _dedupe_posts(posts)
    filtered = [post for post in unique if post.get("score", 0) >= min_engagement]
    filtered = [post for post in filtered if not post.get("raw_text", "").startswith("RT @")]

    if save and (filtered or save_empty):
        saved_path = _save_standard_posts(filtered, output_dir)
        print(f"  [Twitter] 标准结果已保存: {saved_path}")
    elif save and not filtered:
        print("  [Twitter] 本轮没有结果，保留 outputs 中已有的 Twitter 输出文件。")

    print(f"  [Twitter] 合计: {len(filtered)} 条（原始 {len(unique)} 条，去低互动后）")
    return filtered


if __name__ == "__main__":
    print("=" * 60)
    print("Twitter/X 采集器测试（Scweet）")
    print("=" * 60)
    posts = collect_twitter(search_days=3, max_per_query=10, max_per_account=5)
    if posts:
        top_posts = sorted(posts, key=lambda item: item.get("score", 0), reverse=True)[:5]
        print("\nTop-5 推文（按互动量）:")
        for post in top_posts:
            print(f"  [{post['score']}互动] {post['title'][:80]}")
    else:
        print("  未获取到推文（请检查 Scweet 安装和 cookie 配置）")
