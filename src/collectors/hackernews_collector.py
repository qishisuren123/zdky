"""Hacker News 采集器 - Firebase API 无鉴权"""

import httpx
import json
import time
from datetime import datetime
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from config.settings import HN_API_BASE, HN_AI_KEYWORDS, HN_MIN_SCORE, CANDIDATES_DIR


def get_top_stories(limit=100):
    """获取 HN top stories 中 AI 相关的"""
    ai_stories = []
    try:
        resp = httpx.get(f"{HN_API_BASE}/topstories.json", timeout=15)
        story_ids = resp.json()[:limit]

        for sid in story_ids:
            try:
                item_resp = httpx.get(f"{HN_API_BASE}/item/{sid}.json", timeout=10)
                item = item_resp.json()
                if not item or item.get("type") != "story":
                    continue

                title = item.get("title", "").lower()
                score = item.get("score", 0)

                if score < HN_MIN_SCORE:
                    continue

                is_ai = any(kw.lower() in title for kw in HN_AI_KEYWORDS)
                if not is_ai:
                    continue

                ai_stories.append({
                    "source": "hackernews",
                    "source_category": "engineering",
                    "title": item.get("title", ""),
                    "url": item.get("url", f"https://news.ycombinator.com/item?id={sid}"),
                    "hn_url": f"https://news.ycombinator.com/item?id={sid}",
                    "score": score,
                    "num_comments": item.get("descendants", 0),
                    "author": item.get("by", ""),
                    "time": datetime.fromtimestamp(item.get("time", 0)).isoformat(),
                    "collected_at": datetime.now().isoformat(),
                })
            except Exception:
                continue
            time.sleep(0.05)

        print(f"  [HN] 扫描 {limit} 条 top stories，找到 {len(ai_stories)} 条 AI 相关（score≥{HN_MIN_SCORE}）")
    except Exception as e:
        print(f"  [HN] 失败: {e}")

    return ai_stories


def save_results(stories):
    output_file = CANDIDATES_DIR / f"hackernews_{datetime.now().strftime('%Y%m%d')}.json"
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(stories, f, ensure_ascii=False, indent=2)
    print(f"  [HN] 保存 {len(stories)} 条到 {output_file}")
    return output_file


if __name__ == "__main__":
    print("=" * 60)
    print("Hacker News 采集器测试")
    print("=" * 60)
    stories = get_top_stories(limit=60)
    if stories:
        save_results(stories)
        print(f"\n  Top AI stories:")
        for s in sorted(stories, key=lambda x: x["score"], reverse=True)[:5]:
            print(f"    [{s['score']}pt, {s['num_comments']}评] {s['title'][:60]}")
    else:
        print("  当前 HN top stories 中未找到 AI 相关热帖")
