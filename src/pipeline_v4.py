"""
AutoResearch Pipeline v4 - 以社区真实讨论为核心

核心逻辑反转:
- 之前: 从论文库出发 → 看有没有人讨论 (大部分没有)
- 现在: 从社区讨论出发 → 找到被真实热议的工作 → LLM 判断是否有 insight

入口信号:
1. Reddit r/MachineLearning 近1个月 [Research] 高讨论帖
2. Reddit r/LocalLLaMA 近1个月技术向高讨论帖
3. Hacker News 近1个月 AI 高评论帖
4. 中文媒体最近报道中能找到对应社区讨论的

筛选标准:
- 必须有真实社区讨论（评论数 > 阈值，且评论内容是技术性的）
- 不要"又大又全的工程系统"，要有具体的 insight / 方法创新
- LLM(Pro) 最终判断是否真正有洞见
"""

import json
import re
import sys
import time
import httpx
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "src" / "collectors"))
from config.settings import CANDIDATES_DIR, VERIFIED_DIR, REDDIT_USER_AGENT
from llm_client import call_flash, call_pro
try:
    from idea_forge.influential_people import get_boost_score
except ImportError:
    def get_boost_score(text):
        return 1.0, []


def normalize_post(item, source_type="community"):
    """将各采集器输出统一为 pipeline 内部格式: title, url, num_comments, score, summary, source, source_type
source_type: 'community' | 'academic' | 'media'"""
    title = item.get("title", "").strip()
    url = item.get("url") or item.get("reddit_url") or item.get("pdf_url") or item.get("hn_url") or ""
    url = url.strip() if url else ""
    summary = item.get("summary") or item.get("abstract") or item.get("selftext") or ""
    summary = summary.strip() if summary else ""
    source = item.get("source", "unknown")

    try:
        num_comments = int(item.get("num_comments", 0) or 0)
    except (ValueError, TypeError):
        num_comments = 0

    try:
        score = int(item.get("score", 0) or 0)
    except (ValueError, TypeError):
        score = 0

    normalized = {
        "title": title,
        "url": url,
        "num_comments": num_comments,
        "score": score,
        "summary": summary,
        "source": source,
        "source_type": source_type,
    }

    # Carry over any extra fields that may be useful downstream
    for k, v in item.items():
        if k not in normalized:
            normalized[k] = v

    return normalized


def _normalize_title(t):
    """归一化 title 用于模糊匹配：去掉常见前缀/标点/空白，统一小写，保留前 60 字符"""
    if not t:
        return ""
    # Strip common Reddit/HN prefixes
    t = re.sub(r'^\[(P|D|R|N|Q|L|Research|Discussion|Project|News)\]\s*', '', t, flags=re.IGNORECASE)
    t = re.sub(r'^(Ask HN|Show HN|Tell HN)\s*:\s*', '', t, flags=re.IGNORECASE)
    # Remove punctuation/whitespace noise
    t = re.sub(r'[\s\-_/\(\)\[\]\.,\'":;!?]+', ' ', t)
    t = t.strip().lower()
    return t[:60]


def load_processed_keys():
    """扫描 verified/pipeline_v4_*.json，把所有已经被 final_pro_judgment 处理过的帖子的 url/reddit_url/hn_url/title 收集成集合，作为黑名单。

返回 (urls_set, titles_set, normalized_titles_set)。
任何帖子只要 url、原 title、或归一化 title 命中其一就视作"已处理"。"""
    urls_set = set()
    titles_set = set()
    normalized_titles_set = set()

    VERIFIED_DIR.mkdir(parents=True, exist_ok=True)
    pattern_files = list(VERIFIED_DIR.glob("pipeline_v4_*.json"))

    for fpath in pattern_files:
        try:
            with open(fpath, encoding="utf-8") as f:
                data = json.load(f)
            candidates = data.get("final_candidates", [])
            for c in candidates:
                url = c.get("url", "")
                if url:
                    urls_set.add(url)
                # Also capture reddit_url / hn_url if present
                for field in ("reddit_url", "hn_url", "pdf_url"):
                    extra_url = c.get(field, "")
                    if extra_url:
                        urls_set.add(extra_url)
                title = c.get("title", "")
                if title:
                    titles_set.add(title)
                    normalized_titles_set.add(_normalize_title(title))
        except Exception:
            continue

    return urls_set, titles_set, normalized_titles_set


def filter_already_processed(posts, processed_urls, processed_titles, processed_norm, label=""):
    """剔除历史已研判过的帖子；url 精确 + title 精确 + 归一化 title 模糊三路兜底。"""
    fresh = []
    filtered_count = 0
    for p in posts:
        url = p.get("url", "")
        title = p.get("title", "")
        norm = _normalize_title(title)

        if (url and url in processed_urls) or \
           (title and title in processed_titles) or \
           (norm and norm in processed_norm):
            filtered_count += 1
            continue
        fresh.append(p)

    if filtered_count:
        tag = f"[{label}] " if label else ""
        print(f"  {tag}历史去重: 剔除 {filtered_count} 条，剩余 {len(fresh)} 条")
    return fresh


def search_reddit_research(subreddit, query, time_filter="month", limit=50):
    """在 Reddit 搜索研究相关帖子（看近1个月）"""
    url = f"https://www.reddit.com/r/{subreddit}/search.json"
    params = {
        "q": query,
        "sort": "relevance",
        "t": time_filter,
        "limit": limit,
        "restrict_sr": 1,
    }
    headers = {"User-Agent": REDDIT_USER_AGENT}
    results = []
    try:
        resp = httpx.get(url, params=params, headers=headers, timeout=20)
        if resp.status_code != 200:
            print(f"  [Reddit/{subreddit}] HTTP {resp.status_code}")
            return []
        data = resp.json()
        children = data.get("data", {}).get("children", [])
        for child in children:
            post = child.get("data", {})
            if not post:
                continue
            post_id = post.get("id", "")
            reddit_url = f"https://www.reddit.com{post.get('permalink', '')}"
            external_url = post.get("url", "")
            # Prefer external link (paper) URL over reddit thread URL
            final_url = external_url if external_url and not external_url.startswith("https://www.reddit.com") else reddit_url
            results.append({
                "source": f"reddit_{subreddit.lower()}",
                "title": post.get("title", "").strip(),
                "url": final_url,
                "reddit_url": reddit_url,
                "score": post.get("score", 0),
                "num_comments": post.get("num_comments", 0),
                "summary": (post.get("selftext") or "")[:500],
                "author": post.get("author", ""),
            })
    except Exception as e:
        print(f"  [Reddit/{subreddit}] 失败: {e}")
    return results


def get_reddit_hot_research(time_filter="month"):
    """获取近1个月内有真实技术讨论的研究帖
重点: 评论数要高（说明真的有人在讨论）"""
    all_posts = []
    seen_urls = set()
    seen_titles = set()

    # r/MachineLearning
    ml_queries = [
        "paper OR research OR method OR architecture",
        "benchmark OR evaluation OR training trick",
    ]
    for q in ml_queries:
        posts = search_reddit_research("MachineLearning", q, time_filter=time_filter)
        for p in posts:
            u = p.get("url", "")
            t = p.get("title", "")
            if (u and u in seen_urls) or (t and t in seen_titles):
                continue
            if u:
                seen_urls.add(u)
            if t:
                seen_titles.add(t)
            all_posts.append(p)
        time.sleep(2)

    # r/LocalLLaMA
    local_posts = search_reddit_research("LocalLLaMA", "research OR paper OR method OR technique", time_filter=time_filter)
    for p in local_posts:
        u = p.get("url", "")
        t = p.get("title", "")
        if (u and u in seen_urls) or (t and t in seen_titles):
            continue
        if u:
            seen_urls.add(u)
        if t:
            seen_titles.add(t)
        all_posts.append(p)

    return all_posts


def filter_by_discussion_quality(posts, min_comments=15, min_score=50):
    """只保留有真实讨论的帖子:
- 评论数 >= 15（有人真的在讨论）
- score >= 50（社区认可）
- 排除纯 meme / 纯问答"""
    meme_keywords = [
        "hot take", "am i wrong", "shower thought", "unpopular opinion",
        "eli5", "change my mind", "fight me", "controversial", "rant",
        "meme", "humor", "funny", "joke", "lol",
    ]
    quality = []
    for p in posts:
        num_comments = p.get("num_comments", 0) or 0
        score = p.get("score", 0) or 0
        title_lower = (p.get("title", "") or "").lower()

        if num_comments < min_comments:
            continue
        if score < min_score:
            continue
        if len(title_lower) < 10:
            continue
        if any(kw in title_lower for kw in meme_keywords):
            continue
        quality.append(p)
    return quality


def get_hn_discussed(time_filter_days=30):
    """从 HN Algolia API 获取近 N 天内 AI 高讨论帖"""
    cutoff_ts = int(time.time()) - time_filter_days * 86400
    queries = [
        "LLM",
        "machine learning",
        "neural network",
        "AI research",
        "language model",
        "diffusion",
        "reasoning",
    ]
    seen_ids = set()
    results = []

    for q in queries:
        try:
            params = {
                "query": q,
                "tags": "story",
                "numericFilters": f"num_comments>20,created_at_i>{cutoff_ts}",
                "hitsPerPage": 30,
            }
            resp = httpx.get(
                "https://hn.algolia.com/api/v1/search",
                params=params,
                timeout=20,
            )
            if resp.status_code != 200:
                continue
            hits = resp.json().get("hits", [])
            for hit in hits:
                hn_id = hit.get("objectID", "")
                if hn_id in seen_ids:
                    continue
                seen_ids.add(hn_id)
                results.append({
                    "source": "hackernews",
                    "title": hit.get("title", "").strip(),
                    "url": hit.get("url") or f"https://news.ycombinator.com/item?id={hn_id}",
                    "hn_url": f"https://news.ycombinator.com/item?id={hn_id}",
                    "score": hit.get("points", 0) or 0,
                    "num_comments": hit.get("num_comments", 0) or 0,
                    "summary": "",
                })
        except Exception as e:
            print(f"  [HN/{q}] 失败: {e}")
            continue

    return results


def llm_insight_filter(posts, source_label="Reddit"):
    """对帖子列表做 LLM insight 过滤，返回有洞见的帖子列表。
VIP bypass: 提及大佬（boost_score > 1.5）的帖子直接通过，不走 LLM。"""
    if not posts:
        return []

    insightful = []
    batch_size = 30

    # VIP bypass pass
    remaining = []
    for p in posts:
        text = (p.get("title", "") or "") + " " + (p.get("summary", "") or "")
        boost_score, mentions = get_boost_score(text)
        if boost_score > 1.5:
            p["_vip_boost"] = boost_score
            p["_vip_mentions"] = [m["person"] for m in mentions]
            insightful.append(p)
        else:
            remaining.append(p)

    if len(insightful) > 0:
        print(f"  [{source_label}] VIP bypass: {len(insightful)} 条直接通过")

    # Batch LLM filter for non-VIP posts
    for batch_start in range(0, len(remaining), batch_size):
        batch = remaining[batch_start: batch_start + batch_size]
        numbered = "\n".join(
            f"{i+1}. {p.get('title', '')} (评论:{p.get('num_comments',0)}, score:{p.get('score',0)})"
            for i, p in enumerate(batch)
        )

        prompt = (
            f"以下是 {source_label} 上社区引发真实讨论的帖子。\n\n"
            "请判断哪些讨论的是**有 genuine insight 的研究方法/发现**，而不是：\n"
            "- 又大又全的工程系统（如[我们发布了一个新平台]）\n"
            "- 纯产品发布（如[GPT-X 发布了]）\n"
            "- 排行榜刷分（如[我们在 X benchmark 上达到了 SOTA]）\n"
            "- 纯应用展示（如[用 AI 做了 XXX]）\n"
            "- 行业新闻/八卦\n\n"
            "我要的是：\n"
            "- 提出了一个新颖的、具体的技术 insight（如[发现 attention 在某种条件下可以被简化]）\n"
            "- 对现有方法有深刻的改进思路（不是简单的 scale up）\n"
            "- 揭示了某个反直觉的现象或规律\n"
            "- 提出了一个简洁但有力的新方法\n\n"
            f"帖子列表（共 {len(batch)} 条）：\n{numbered}\n\n"
            "请返回有 genuine insight 的帖子编号，用逗号分隔（如 1,3,5）。"
            "如果全都没有洞见，返回空字符串。只返回编号，不要解释。"
        )

        try:
            resp = call_flash(prompt, max_tokens=2500)
            if resp:
                # Parse comma-separated numbers
                numbers = re.findall(r'\d+', resp)
                for n_str in numbers:
                    idx = int(n_str) - 1
                    if 0 <= idx < len(batch):
                        insightful.append(batch[idx])
        except Exception as e:
            print(f"  [{source_label}] LLM 过滤批次 {batch_start//batch_size + 1} 失败: {e}")

        if batch_start + batch_size < len(remaining):
            time.sleep(0.5)

    return insightful


def final_pro_judgment(candidates, top_k=10):
    """对候选帖子逐一用 Pro 模型做深度研判，返回带判断结果的列表。"""
    if not candidates:
        return []

    judged = []
    for i, c in enumerate(candidates[:top_k]):
        title = c.get("title", "")
        url = c.get("url", "")
        summary = c.get("summary", "") or ""
        source = c.get("source", "")
        num_comments = c.get("num_comments", 0)
        score = c.get("score", 0)

        prompt = (
            "你是一位AI研究顾问。以下是一个在社区被真实热议的研究工作（"
            f"来源: {source}，评论数: {num_comments}，score: {score}）：\n\n"
            f"标题: {title}\n"
            f"链接: {url}\n"
            f"摘要/内容: {summary[:500] if summary else '(无)'}\n\n"
            "请从以下维度评估这项工作：\n"
            "1. 核心insight: 这个工作最核心的技术洞见是什么？\n"
            "2. 社区热议原因: 为什么社区在讨论它？是真的有价值还是只是噱头？\n"
            "3. 方法简洁度: 方法是否简洁优雅，还是又大又全的工程堆砌？\n"
            "4. A+B迁移潜力: 这个insight能否与其他领域/方法组合产生新想法？\n"
            "5. 资源可行性: 复现/实验需要多少资源？学术组能做吗？\n"
            "6. 最终判定: 【强推荐 / 值得深入 / 不适合做A种子】+ 一句话理由\n\n"
            "格式:\n"
            "核心insight: ...\n"
            "社区热议原因: ...\n"
            "方法简洁度: ...\n"
            "A+B迁移潜力: ...\n"
            "资源可行性: ...\n"
            "最终判定: ..."
        )

        try:
            resp = call_pro(prompt, max_tokens=2500)
            judgment = resp or ""
        except Exception as e:
            print(f"  [Pro判断 {i+1}/{min(len(candidates), top_k)}] 失败: {e}")
            judgment = ""

        # Parse conclusion: 找"最终判定"所在行或其下一行（Gemini 有时分两行输出）
        conclusion = ""
        lines = judgment.splitlines()
        for idx, line in enumerate(lines):
            stripped = line.strip()
            if "最终判定" in stripped:
                # 先看同行是否已含判定词
                for kw in ["强推荐", "值得深入", "值得", "不适合"]:
                    if kw in stripped:
                        conclusion = stripped
                        break
                # 同行没有，看下一行
                if not conclusion and idx + 1 < len(lines):
                    next_line = lines[idx + 1].strip()
                    for kw in ["强推荐", "值得深入", "值得", "不适合"]:
                        if kw in next_line:
                            conclusion = next_line
                            break
                if conclusion:
                    break

        c_out = dict(c)
        c_out["llm_judgment"] = judgment
        c_out["conclusion"] = conclusion
        judged.append(c_out)

        print(f"  [Pro {i+1}/{min(len(candidates), top_k)}] {title[:60]} → {conclusion[:60] if conclusion else '(无结论)'}")

    return judged


def collect_all_channels(time_filter="month", time_filter_days=30, arxiv_days=7, hf_days=7):
    """
    调用所有可用采集器，返回归一化后的 post 列表。
    参数:
      time_filter      - Reddit sort time filter ("month"/"year" 等)
      time_filter_days - HN 回溯天数
      arxiv_days       - arXiv 回溯天数
      hf_days          - HF Papers 回溯天数
    """
    all_posts = []
    collectors_dir = Path(__file__).parent / "collectors"
    sys.path.insert(0, str(collectors_dir))

    # ── 1. Reddit ──────────────────────────────────────────────
    reddit_posts = get_reddit_hot_research(time_filter=time_filter)
    all_posts.extend([normalize_post(p, "community") for p in reddit_posts])
    print(f"  [Reddit] {len(reddit_posts)} 帖")

    # ── 2. Hacker News ─────────────────────────────────────────
    hn_posts = get_hn_discussed(time_filter_days=time_filter_days)
    all_posts.extend([normalize_post(p, "community") for p in hn_posts])
    print(f"  [HN] {len(hn_posts)} 帖")

    # ── 3. arXiv ───────────────────────────────────────────────
    try:
        from arxiv_collector import collect_recent_papers
        arxiv_papers = collect_recent_papers(days_back=arxiv_days, max_per_category=20)
        all_posts.extend([normalize_post(p, "academic") for p in arxiv_papers])
        print(f"  [arXiv] {len(arxiv_papers)} 篇")
    except Exception as e:
        print(f"  [arXiv] 失败: {e}")

    # ── 4. HuggingFace Daily Papers ────────────────────────────
    try:
        from hf_papers_collector import collect_daily_papers
        hf_papers = collect_daily_papers(days_back=hf_days)
        all_posts.extend([normalize_post(p, "academic") for p in hf_papers])
        print(f"  [HF Papers] {len(hf_papers)} 篇")
    except Exception as e:
        print(f"  [HF Papers] 失败: {e}")

    # ── 5. GitHub Trending ─────────────────────────────────────
    try:
        from github_trending_collector import collect_trending
        since_map = {"month": "monthly", "week": "weekly", "year": "monthly"}
        gh_repos = collect_trending(since=since_map.get(time_filter, "monthly"))
        all_posts.extend([normalize_post(r, "community") for r in gh_repos])
        print(f"  [GitHub Trending] {len(gh_repos)} 个项目")
    except Exception as e:
        print(f"  [GitHub Trending] 失败: {e}")

    # ── 6. Emergent Mind ───────────────────────────────────────
    try:
        from emergent_mind_collector import collect_emergent_mind
        em_items = collect_emergent_mind()
        all_posts.extend([normalize_post(i, "academic") for i in em_items])
        print(f"  [Emergent Mind] {len(em_items)} 篇")
    except Exception as e:
        print(f"  [Emergent Mind] 失败: {e}")

    # ── 7. Paper Digest ────────────────────────────────────────
    try:
        from paper_digest_collector import collect_paper_digest
        pd_items = collect_paper_digest()
        all_posts.extend([normalize_post(i, "academic") for i in pd_items])
        print(f"  [Paper Digest] {len(pd_items)} 篇")
    except Exception as e:
        print(f"  [Paper Digest] 失败: {e}")

    # ── 8. RSS 源 ──────────────────────────────────────────────
    try:
        from rss_collector import collect_all_feeds
        rss_items, _ = collect_all_feeds()
        all_posts.extend([normalize_post(i, "media") for i in rss_items])
        print(f"  [RSS] {len(rss_items)} 篇")
    except Exception as e:
        print(f"  [RSS] 失败: {e}")

    # ── 9. Influential Voices（研究博客 + 顶会亮点）─────────────
    try:
        from influential_voices import collect_research_blogs, collect_conference_highlights
        blogs = collect_research_blogs(max_days=time_filter_days)
        confs = collect_conference_highlights()
        all_posts.extend([normalize_post(i, "academic") for i in blogs + confs])
        print(f"  [Influential Voices] 博客={len(blogs)} 顶会={len(confs)}")
    except Exception as e:
        print(f"  [Influential Voices] 失败: {e}")

    # ── 10. OpenReview ─────────────────────────────────────────
    try:
        from openreview_collector import collect_all_venues
        or_papers = collect_all_venues()
        all_posts.extend([normalize_post(p, "academic") for p in or_papers])
        print(f"  [OpenReview] {len(or_papers)} 篇")
    except Exception as e:
        print(f"  [OpenReview] 失败: {e}")

    # ── 11. Jina 中文媒体 ──────────────────────────────────────
    try:
        from jina_chinese_media import collect_chinese_media
        jina_items = collect_chinese_media(first_run=False)
        all_posts.extend([normalize_post(i, "media") for i in jina_items])
        print(f"  [Jina 中文媒体] {len(jina_items)} 篇")
    except Exception as e:
        print(f"  [Jina 中文媒体] 失败: {e}")

    # ── 12. Twitter/X（twikit，需 cookie 配置）─────────────────
    try:
        from twitter_collector import collect_twitter
        tw_days = min(time_filter_days, 7)  # Twitter 搜索最多回溯7天
        tw_items = collect_twitter(search_days=tw_days, max_per_query=20, max_per_account=8)
        all_posts.extend([normalize_post(i, "community") for i in tw_items])
        print(f"  [Twitter/X] {len(tw_items)} 条")
    except Exception as e:
        print(f"  [Twitter/X] 失败: {e}")

    # ── 全局去重（url + title）─────────────────────────────────
    seen_url   = set()
    seen_title = set()
    unique = []
    for p in all_posts:
        u = p.get("url", "")
        t = _normalize_title(p.get("title", ""))
        if (u and u in seen_url) or (t and t in seen_title):
            continue
        if u:
            seen_url.add(u)
        if t:
            seen_title.add(t)
        unique.append(p)

    print(f"\n  ✅ 全渠道去重后: {len(unique)} 条（原始 {len(all_posts)} 条）")
    return unique


def run_pipeline_v4(time_filter="month", time_filter_days=30, arxiv_days=7, hf_days=7, top_k=15, output_tag=None):
    """v4 主流程：多渠道采集 → 跨天去重 → insight 过滤 → Pro 研判"""
    print(f"\n{'='*60}")
    print(f"Pipeline v4 开始 [{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}]")
    print(f"{'='*60}")
    print(f"参数: time_filter={time_filter}, time_filter_days={time_filter_days}, "
          f"arxiv_days={arxiv_days}, hf_days={hf_days}, top_k={top_k}")
    print("\n[Step 1] 多渠道采集...")

    all_posts = collect_all_channels(
        time_filter=time_filter,
        time_filter_days=time_filter_days,
        arxiv_days=arxiv_days,
        hf_days=hf_days,
    )
    total_raw = len(all_posts)

    # Split by source type
    community = [p for p in all_posts if p.get("source_type") == "community"]
    non_community = [p for p in all_posts if p.get("source_type") != "community"]

    # Count raw HN and Reddit
    hn_raw = sum(1 for p in all_posts if "hackernews" in p.get("source", ""))
    reddit_raw = sum(1 for p in all_posts if "reddit" in p.get("source", ""))

    print(f"\n[Step 2] 讨论质量过滤 (community: min_comments=15, min_score=50)...")
    community_quality = filter_by_discussion_quality(community, min_comments=15, min_score=50)
    # Non-community posts (academic/media) get through with a more lenient filter
    non_community_quality = filter_by_discussion_quality(non_community, min_comments=0, min_score=0)
    all_quality = community_quality + non_community_quality
    after_quality_filter = len(all_quality)
    print(f"  质量过滤后: community={len(community_quality)}, academic/media={len(non_community_quality)}, 合计={after_quality_filter}")

    print(f"\n[Step 3] 跨天去重（剔除历史已研判帖子）...")
    processed_urls, processed_titles, processed_norm = load_processed_keys()
    print(f"  历史黑名单: {len(processed_urls)} URLs, {len(processed_titles)} 标题")
    all_quality = filter_already_processed(
        all_quality, processed_urls, processed_titles, processed_norm, label="全渠道"
    )

    print(f"\n[Step 4] LLM insight 过滤...")
    community_posts_q = [p for p in all_quality if p.get("source_type") == "community"]
    academic_posts_q  = [p for p in all_quality if p.get("source_type") != "community"]

    community_insightful = llm_insight_filter(community_posts_q, source_label="社区")
    academic_insightful  = llm_insight_filter(academic_posts_q,  source_label="学术/媒体")

    all_insightful_full = community_insightful + academic_insightful
    after_insight_filter = len(all_insightful_full)
    print(f"  insight 过滤后: community={len(community_insightful)}, academic={len(academic_insightful)}, 合计={after_insight_filter}")

    # Pro 研判全量 insightful（不截断）
    # top_k 仍作为每日模式的软上限：日常运行时 insight 数量少，全量即可；
    # 3个月模式 insight 可能数百条，由调用方传入 top_k 控制上限（默认15~20）。
    # 按社区热度排序，保证最热的优先被 Pro 看到。
    all_insightful_full.sort(
        key=lambda p: p.get("num_comments", 0) * 2 + p.get("score", 0), reverse=True
    )
    pro_candidates = all_insightful_full[:max(top_k, len(all_insightful_full))]

    print(f"\n[Step 5] Pro 深度研判 ({len(pro_candidates)} 候选，全量)...")
    judged = final_pro_judgment(pro_candidates, top_k=len(pro_candidates))
    final_judged = len(judged)

    # Build output
    tag = output_tag if output_tag else datetime.now().strftime("%Y%m%d")
    output_file = VERIFIED_DIR / f"pipeline_v4_{tag}.json"
    VERIFIED_DIR.mkdir(parents=True, exist_ok=True)

    output = {
        "generated_at": datetime.now().isoformat(),
        "pipeline_version": "v4",
        "approach": "community-first: 从社区真实讨论出发 → LLM insight 过滤 → Pro 研判",
        "stats": {
            "total_raw": total_raw,
            "after_quality_filter": after_quality_filter,
            "after_insight_filter": after_insight_filter,
            "final_judged": final_judged,
            "hn_raw": hn_raw,
            "reddit_raw": reddit_raw,
        },
        "final_candidates": judged,
        "all_insightful": all_insightful_full,
    }

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n{'='*60}")
    print(f"Pipeline v4 完成")
    print(f"  原始: {total_raw} → 质量过滤: {after_quality_filter} → insight: {after_insight_filter} → Pro研判: {final_judged}")
    print(f"  输出: {output_file}")
    print(f"{'='*60}\n")

    return output


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="AutoResearch Pipeline v4")
    parser.add_argument("--time-filter", default="month", help="Reddit time filter (month/year/week)")
    parser.add_argument("--days", type=int, default=30, help="HN lookback days")
    parser.add_argument("--arxiv-days", type=int, default=7, help="arXiv lookback days")
    parser.add_argument("--hf-days", type=int, default=7, help="HF Papers lookback days")
    parser.add_argument("--top-k", type=int, default=15, help="Top K for Pro judgment")
    parser.add_argument("--tag", default=None, help="Output file tag")
    args = parser.parse_args()

    result = run_pipeline_v4(
        time_filter=args.time_filter,
        time_filter_days=args.days,
        arxiv_days=args.arxiv_days,
        hf_days=args.hf_days,
        top_k=args.top_k,
        output_tag=args.tag,
    )

    candidates = result.get("final_candidates", [])
    strong = [c for c in candidates if "强推荐" in c.get("conclusion", "")]
    print(f"\n强推荐: {len(strong)} 个")
    for c in strong:
        print(f"  - {c.get('title', '')[:80]}")
        print(f"    → {c.get('conclusion', '')[:100]}")
