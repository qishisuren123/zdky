"""
中文AI媒体采集器 - 通过 Jina Reader (r.jinaai.cn) 抓取网页正文
覆盖: 机器之心、新智元、智东西、量子位（RSS已有，这里作为补充）

⚠️ 法律/合规风险提示：
Jina Reader 本身是一个免费公开的网页转 Markdown 服务，但本模块的目标站点之一
（机器之心）已明确部署反爬措施并要求使用其付费数据服务获取内容（参见同目录下
jiqizhixin_collector.py 的说明）。使用本模块间接获取该类站点内容，可能违反目标
站点的服务条款（ToS），风险由使用者自行承担；建议在生产使用前确认目标站点的
robots.txt、ToS 以及是否有官方 API/数据服务可用，优先使用官方渠道。

灵感来自 github.com/qhlx/SciDataDaily
"""

import re
import json
import httpx
from datetime import datetime
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from config.settings import CANDIDATES_DIR

CHINESE_MEDIA_URLS = {
    "jiqizhixin": {
        "name": "机器之心",
        "base_url": "https://www.jiqizhixin.com/articles",
        "paginate": True,
        "max_pages_first_run": 15,  # 首次跑15页 ≈ 一个月
        "max_pages_daily": 1,       # 每天只跑1页（增量）
        "weight": "high",
    },
    "xinzhiyuan": {
        "name": "新智元",
        "base_url": "https://www.36kr.com/user/986414617",
        "paginate": False,
        "weight": "high",
    },
    "zhidongxi": {
        "name": "智东西",
        "base_url": "https://zhidx.com/",
        "paginate": False,
        "weight": "medium",
    },
}


def fetch_via_jina(url):
    """通过 Jina Reader 获取网页的 Markdown 表示"""
    jina_url = f"https://r.jinaai.cn/{url}"
    try:
        resp = httpx.get(jina_url, timeout=30, follow_redirects=True)
        if resp.status_code == 200:
            return resp.text
        return None
    except Exception as e:
        print(f"    Jina 请求失败: {e}")
        return None


def parse_jiqizhixin(markdown):
    """解析机器之心的 Markdown 内容"""
    articles = []
    lines = markdown.split("\n")

    current_title = None
    for line in lines:
        line = line.strip()
        if not line:
            continue
        # 跳过图片和链接行
        if line.startswith("![") or line.startswith("Image"):
            continue
        # 跳过日期行
        if line in ("今天", "昨天") or re.match(r"^\d+天前$", line) or re.match(r"^\d{4}-", line):
            continue
        # 跳过标签行（短且没有标点）
        if len(line) < 10 and not any(c in line for c in "。，！？"):
            continue

        # 较长的行作为标题候选
        if len(line) >= 10 and not line.startswith("http"):
            # 过滤掉明显的非标题
            if any(skip in line for skip in [
                "imageView", "uploads/", "http", "Markdown Content",
                "URL Source", "Title:", "Image ", "img",
            ]):
                continue
            # 过滤掉纯英文短标签（如 "AI for Science", "OpenAI"）
            if len(line) < 15 and re.match(r'^[A-Za-z\s]+$', line):
                continue
            articles.append({
                "title": line,
                "source": "jiqizhixin_jina",
                "source_category": "chinese_media",
                "source_name": "机器之心",
            })

    # 去重
    seen = set()
    unique = []
    for a in articles:
        if a["title"] not in seen:
            seen.add(a["title"])
            unique.append(a)

    return unique


def collect_chinese_media(first_run=False):
    """
    采集所有中文AI媒体
    first_run=True: 翻多页，查前一个月
    first_run=False: 只查第一页（增量）
    """
    import os
    import time

    # 通过环境变量判断是否首次
    lookback = int(os.environ.get("AUTORESEARCH_LOOKBACK_DAYS", "1"))
    is_first = first_run or lookback >= 30

    print(f"\n  --- 中文AI媒体 (Jina Reader) {'[首次:查前1月]' if is_first else '[增量]'} ---")
    all_articles = []

    for media_id, info in CHINESE_MEDIA_URLS.items():
        if info.get("paginate") and media_id == "jiqizhixin":
            max_pages = info["max_pages_first_run"] if is_first else info["max_pages_daily"]
            articles = []
            for page in range(1, max_pages + 1):
                url = info["base_url"] if page == 1 else f"{info['base_url']}?page={page}"
                markdown = fetch_via_jina(url)
                if not markdown:
                    break
                page_articles = parse_jiqizhixin(markdown)
                articles.extend(page_articles)
                if page < max_pages:
                    time.sleep(2)  # 控频
            print(f"    {info['name']}: ✅ {len(articles)} 篇 ({max_pages} 页)")
        else:
            markdown = fetch_via_jina(info["base_url"])
            if not markdown:
                print(f"    {info['name']}: ❌ 获取失败")
                continue

            # 通用解析
            articles = []
            for line in markdown.split("\n"):
                line = line.strip()
                if len(line) >= 10 and not line.startswith(("!", "http", "Image", "[")):
                    if not any(skip in line for skip in [
                        "imageView", "uploads/", "svg", "png", "jpg",
                        "Markdown Content", "URL Source", "Title:"
                    ]):
                        articles.append({
                            "title": line,
                            "source": f"{media_id}_jina",
                            "source_category": "chinese_media",
                            "source_name": info["name"],
                        })

            # 去重
            seen = set()
            articles = [a for a in articles if a["title"] not in seen and not seen.add(a["title"])]
            print(f"    {info['name']}: ✅ {len(articles)} 篇")

        for a in articles:
            a["collected_at"] = datetime.now().isoformat()
            a["url"] = info.get("base_url", "")
            if "source" not in a:
                a["source"] = f"{media_id}_jina"
            if "source_category" not in a:
                a["source_category"] = "chinese_media"
            if "source_name" not in a:
                a["source_name"] = info["name"]

        all_articles.extend(articles)

    return all_articles


if __name__ == "__main__":
    print("=" * 60)
    print("  中文AI媒体采集器 (Jina Reader) 测试")
    print("=" * 60)
    articles = collect_chinese_media()
    print(f"\n  总计: {len(articles)} 篇")
    for a in articles[:10]:
        print(f"    [{a['source_name']}] {a['title'][:50]}")
