"""
生成大浪淘沙主页 index.html（按日期 timeline 展示每天的种子）
"""

import json
import glob
import html
from datetime import datetime
from pathlib import Path
from collections import defaultdict

PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"
VERIFIED_DIR = DATA_DIR / "verified"
CANDIDATES_DIR = DATA_DIR / "candidates"


def esc(s):
    return html.escape(str(s))


def collect_seeds_by_date():
    """按日期归集 pipeline_v4 的研判结果（含3个月批次文件）"""
    by_date = defaultdict(list)
    seen_titles_by_date = defaultdict(set)  # 同一日期内去重

    for f in sorted(glob.glob(str(VERIFIED_DIR / "pipeline_v4_*.json"))):
        stem = Path(f).stem  # e.g. pipeline_v4_20260518 or pipeline_v4_3month_20260518_1520
        parts = stem.split("_")
        # 找第一个8位数字段作为日期
        date = None
        for p in parts:
            if len(p) == 8 and p.isdigit():
                date = p
                break
        if not date:
            continue
        try:
            d = json.loads(Path(f).read_text(encoding="utf-8"))
        except Exception:
            continue
        for c in d.get("final_candidates", []):
            title = (c.get("title") or "").strip()
            if title and title not in seen_titles_by_date[date]:
                seen_titles_by_date[date].add(title)
                by_date[date].append(c)

    # 降序日期
    return [(date, by_date[date]) for date in sorted(by_date.keys(), reverse=True)]


def render_seed_card(idx, c):
    title = esc((c.get("title") or "")[:140])
    url = esc(c.get("reddit_url") or c.get("hn_url") or c.get("url") or "#")
    conclusion = esc((c.get("conclusion") or "")[:300])
    channel = esc(c.get("subreddit") or c.get("source") or c.get("channel") or "")
    comments = c.get("num_comments") or 0
    score = c.get("score") or 0
    judgment = (c.get("llm_judgment") or "").replace("**", "")

    if "强推荐" in (c.get("conclusion") or ""):
        tag_class, tag_text = "tag-strong", "强推荐做 A 种子"
    elif "值得" in (c.get("conclusion") or "") or "深入" in (c.get("conclusion") or ""):
        tag_class, tag_text = "tag-worth", "值得深入"
    elif "不适合" in (c.get("conclusion") or ""):
        tag_class, tag_text = "tag-skip", "不适合做 A 种子"
    else:
        tag_class, tag_text = "tag-skip", "待判断"

    # judgment 高亮关键词
    jhtml = ""
    if judgment and judgment != "调用失败":
        for line in judgment.split("\n"):
            line = line.strip()
            if not line:
                continue
            line_h = esc(line)
            for lab in ["核心insight", "核心 insight", "社区热议原因", "方法简洁度",
                       "A+B潜力", "A+B 潜力", "可行性", "最终判定"]:
                if lab in line:
                    line_h = line_h.replace(lab, f'<span class="jl">{lab}</span>', 1)
                    break
            jhtml += f'<div>{line_h}</div>'

    meta_parts = []
    if channel:
        meta_parts.append(f'<span class="ch">{channel}</span>')
    if comments:
        meta_parts.append(f'<span class="hot">{comments} 评论</span>')
    if score:
        meta_parts.append(f'<span>{score} 分</span>')

    return f'''<div class="card">
<div class="card-top"><div class="rank">{idx}</div>
<h3><a href="{url}" target="_blank">{title}</a></h3>
<span class="tag {tag_class}">{tag_text}</span></div>
<div class="meta">{" ".join(meta_parts)}</div>
<div class="judgment">{jhtml}</div>
</div>'''


def generate_html():
    timeline = collect_seeds_by_date()
    if not timeline:
        print("No data found")
        return

    # 计算总览统计
    all_unique_titles = set()
    total_strong = 0
    total_worth = 0
    total_skip = 0
    total_records = 0
    for date, seeds in timeline:
        for c in seeds:
            t = (c.get("title") or "").strip()
            if t and t not in all_unique_titles:
                all_unique_titles.add(t)
                con = c.get("conclusion") or ""
                if "强推荐" in con: total_strong += 1
                elif "值得" in con or "深入" in con: total_worth += 1
                elif "不适合" in con: total_skip += 1
            total_records += 1

    # 渲染 timeline
    timeline_html_parts = []
    for date, seeds in timeline:
        d_fmt = f"{date[:4]}-{date[4:6]}-{date[6:]}"
        strong_count = sum(1 for s in seeds if "强推荐" in (s.get("conclusion") or ""))

        timeline_html_parts.append(f'<div class="day-block">')
        timeline_html_parts.append(f'<div class="day-header">')
        timeline_html_parts.append(f'<h3>📅 {d_fmt}</h3>')
        timeline_html_parts.append(f'<div class="day-stats">')
        timeline_html_parts.append(f'<span class="badge badge-info">{len(seeds)} 候选</span> ')
        if strong_count:
            timeline_html_parts.append(f'<span class="badge badge-strong">{strong_count} 强推荐</span>')
        timeline_html_parts.append('</div></div>')

        # 按 strong → worth → skip 排序
        def k(c):
            con = c.get("conclusion") or ""
            if "强推荐" in con: return 0
            if "值得" in con or "深入" in con: return 1
            if "不适合" in con: return 2
            return 3
        seeds_sorted = sorted(seeds, key=k)
        for i, c in enumerate(seeds_sorted, 1):
            timeline_html_parts.append(render_seed_card(i, c))

        timeline_html_parts.append('</div>')

    timeline_html = "\n".join(timeline_html_parts)

    html_page = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>大浪淘沙 - 每日研究热点</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",sans-serif;background:#0f1117;color:#e4e4e7;line-height:1.7;padding:20px}}
.container{{max-width:1200px;margin:0 auto}}
header{{background:linear-gradient(135deg,#1a1b2e,#16213e);border:1px solid #2a2d3e;border-radius:14px;padding:28px;margin-bottom:20px;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:12px}}
header h1{{font-size:24px;background:linear-gradient(90deg,#60a5fa,#a78bfa);-webkit-background-clip:text;-webkit-text-fill-color:transparent}}
header .sub{{color:#9ca3af;font-size:12px;margin-top:6px}}
header .sub a{{color:#a78bfa;text-decoration:none}}header .sub a:hover{{text-decoration:underline}}

.info{{background:#111827;border:1px solid #2a2d3e;border-radius:8px;padding:14px 18px;margin-bottom:18px;font-size:12.5px;color:#9ca3af;line-height:1.9}}
.info strong{{color:#60a5fa}}

.stats{{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:10px;margin-bottom:20px}}
.stat{{background:#1a1b2e;border:1px solid #2a2d3e;border-radius:10px;padding:14px;text-align:center}}
.stat .n{{font-size:26px;font-weight:700;color:#60a5fa}}
.stat .l{{color:#9ca3af;font-size:11px;margin-top:2px}}

.day-block{{margin-bottom:28px}}
.day-header{{
  background:linear-gradient(135deg,#1a1b2e,#16213e);
  border:1px solid #2a2d3e;border-radius:10px;
  padding:14px 20px;margin-bottom:12px;
  display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px;
}}
.day-header h3{{font-size:18px;color:#60a5fa;margin:0}}
.day-stats{{display:flex;gap:6px;flex-wrap:wrap}}
.badge{{padding:3px 10px;border-radius:12px;font-size:11px;font-weight:500}}
.badge-strong{{background:#064e3b;color:#34d399}}
.badge-info{{background:#1e293b;color:#9ca3af}}

.card{{background:#1a1b2e;border:1px solid #2a2d3e;border-radius:10px;padding:16px 18px;margin-bottom:10px;margin-left:14px;transition:border-color .2s}}
.card:hover{{border-color:#3b82f6}}
.card-top{{display:flex;align-items:center;gap:8px;margin-bottom:6px;flex-wrap:wrap}}
.rank{{background:#111827;color:#60a5fa;font-weight:700;font-size:12px;min-width:24px;height:24px;border-radius:5px;display:flex;align-items:center;justify-content:center;flex-shrink:0}}
.card h3{{font-size:13.5px;color:#f4f4f5;line-height:1.4;flex:1;min-width:200px;font-weight:600}}
.card h3 a{{color:#f4f4f5;text-decoration:none}}.card h3 a:hover{{color:#60a5fa}}
.meta{{font-size:11px;color:#6b7280;margin-bottom:8px;display:flex;gap:10px;flex-wrap:wrap}}
.meta .ch{{color:#a78bfa;font-weight:500}}.meta .hot{{color:#f59e0b}}
.tag{{display:inline-block;padding:3px 10px;border-radius:4px;font-size:11px;font-weight:600;flex-shrink:0}}
.tag-strong{{background:#064e3b;color:#34d399}}.tag-worth{{background:#422006;color:#fbbf24}}.tag-skip{{background:#1f2937;color:#6b7280}}
.judgment{{background:#111827;border-radius:6px;padding:12px;font-size:11.5px;line-height:1.8;color:#d1d5db}}
.judgment .jl{{color:#60a5fa;font-weight:600}}
a{{color:#60a5fa;text-decoration:none}}a:hover{{text-decoration:underline}}
</style>
</head>
<body><div class="container">
<header>
<div>
<h1>🌊 大浪淘沙 · 每日研究热点</h1>
<div class="sub">{datetime.now().strftime('%Y-%m-%d %H:%M')} (UTC+8) · 累计 {len(timeline)} 个采集日 · <a href="./ideas.html">→ Idea Forge Timeline</a></div>
</div>
</header>

<div class="info">
<strong>信号源:</strong> Reddit / Hacker News 社区讨论 · OpenAI / DeepMind / BAIR / Google Research / MSR / Karpathy / Simon Willison / Sebastian Raschka 等研究者博客 · 量子位 / Leiphone / MarkTechPost / VentureBeat / Paper Digest · arXiv / HuggingFace Daily Papers · GitHub Trending · Twitter/X 大佬推文<br>
<strong>筛选漏斗:</strong> 跨天去重 → 规则初筛 → LLM(Gemini Flash) insight 过滤 → LLM(Gemini Pro) A+B 迁移研判
</div>

<div class="stats">
<div class="stat"><div class="n">{len(timeline)}</div><div class="l">采集日数</div></div>
<div class="stat"><div class="n">{len(all_unique_titles)}</div><div class="l">候选(去重)</div></div>
<div class="stat"><div class="n">{total_strong}</div><div class="l">强推荐 A 种子</div></div>
<div class="stat"><div class="n">{total_worth}</div><div class="l">值得深入</div></div>
<div class="stat"><div class="n">{total_skip}</div><div class="l">不适合 A 种子</div></div>
<div class="stat"><div class="n">{total_records}</div><div class="l">研判记录</div></div>
</div>

{timeline_html}

</div></body></html>'''

    output_file = PROJECT_ROOT / "index.html"
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(html_page)
    print(f"Generated {output_file} ({len(html_page)} bytes)")


if __name__ == "__main__":
    generate_html()
