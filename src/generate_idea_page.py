"""
生成 Idea Forge 可视化静态页面（按日期 timeline）
路径: ideas.html
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
FORGE_DIR = DATA_DIR / "idea_forge"
KB_DIR = PROJECT_ROOT / "knowledge_base"


def esc(s):
    return html.escape(str(s))


def collect_by_date():
    """
    Returns timeline list sorted by date descending.
    Each entry: {date, seeds: [...], plans: [...], forge_files: [...]}
    """
    by_date = defaultdict(lambda: {"seeds": [], "plans": [], "forge_files": []})
    seen_seed_titles_by_date = defaultdict(set)

    # --- collect seeds from pipeline_v4_*.json ---
    for f in sorted(glob.glob(str(VERIFIED_DIR / "pipeline_v4_*.json"))):
        stem = Path(f).stem  # e.g. pipeline_v4_20260509
        parts = stem.split("_")
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
            if not title or title in seen_seed_titles_by_date[date]:
                continue
            seen_seed_titles_by_date[date].add(title)
            seed_card = {
                "title": title,
                "conclusion": c.get("conclusion") or "",
                "judgment": c.get("llm_judgment") or "",
                "channel": c.get("subreddit") or c.get("source") or c.get("channel") or "",
                "url": c.get("reddit_url") or c.get("hn_url") or c.get("url") or "#",
                "comments": c.get("num_comments") or 0,
                "score": c.get("score") or 0,
            }
            by_date[date]["seeds"].append(seed_card)

    # --- collect plans from forge_*.json ---
    for f in sorted(glob.glob(str(FORGE_DIR / "forge_*.json"))):
        stem = Path(f).stem  # e.g. forge_20260509_1912
        parts = stem.split("_")
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

        forge_fname = Path(f).name
        if forge_fname not in by_date[date]["forge_files"]:
            by_date[date]["forge_files"].append(forge_fname)

        for result in d.get("results", []):
            # seed title: prefer result-level seed_title, fallback to seed dict
            seed_title = (
                result.get("seed_title")
                or result.get("__seed_title")
                or (result.get("seed") or {}).get("title")
                or ""
            )
            for plan in result.get("plans", []):
                forge_file_ref = plan.get("__forge_file") or forge_fname
                plan_card = {
                    "seed_title": (seed_title or "")[:120],
                    "b_domain": plan.get("b_domain") or plan.get("b_direction") or "",
                    "b_problem": plan.get("b_problem") or "",
                    "source_model": plan.get("source_model") or "",
                    "idea_text": plan.get("idea_text") or "",
                    "plan": plan.get("plan") or "",
                    "validation": plan.get("validation"),
                    "freshness_flags": (plan.get("validation") or {}).get("freshness_flags") if isinstance(plan.get("validation"), dict) else [],
                    "consensus_check": plan.get("consensus_check"),
                    "freshness_refresh": plan.get("freshness_refresh"),
                    "forge_file": forge_file_ref,
                }
                by_date[date]["plans"].append(plan_card)

    # sort descending by date
    result_list = []
    for date in sorted(by_date.keys(), reverse=True):
        entry = by_date[date]
        entry["date"] = date
        result_list.append(entry)
    return result_list


def stats_global(timeline):
    """Returns global stats dict."""
    active_days = len(timeline)
    unique_seeds = 0
    strong_seeds = 0
    seen = set()
    for entry in timeline:
        for s in entry["seeds"]:
            t = s["title"]
            if t not in seen:
                seen.add(t)
                unique_seeds += 1
                if "强推荐" in (s.get("conclusion") or ""):
                    strong_seeds += 1

    # kb_count: .md files in KB_DIR excluding README.md
    kb_count = 0
    if KB_DIR.exists():
        kb_count = sum(
            1 for f in KB_DIR.glob("*.md") if f.name.lower() != "readme.md"
        )

    # totals from forge summaries
    total_ideas = 0
    total_validated = 0
    total_plans = 0
    for f in glob.glob(str(FORGE_DIR / "forge_*.json")):
        try:
            d = json.loads(Path(f).read_text(encoding="utf-8"))
        except Exception:
            continue
        s = d.get("summary", {})
        total_ideas += s.get("total_ideas", 0) or s.get("total_ideas_generated", 0)
        total_validated += s.get("total_validated", 0)
        total_plans += s.get("total_plans", 0) or s.get("total_with_plans", 0)

    return {
        "active_days": active_days,
        "unique_seeds": unique_seeds,
        "strong_seeds": strong_seeds,
        "kb_count": kb_count,
        "total_ideas": total_ideas,
        "total_validated": total_validated,
        "total_plans": total_plans,
    }


def render_stats_bar(s):
    return f"""<div class="stats">
  <div class="stat"><div class="n">{s['active_days']}</div><div class="l">活跃天数</div></div>
  <div class="stat"><div class="n">{s['unique_seeds']}</div><div class="l">候选种子（去重）</div></div>
  <div class="stat"><div class="n">{s['strong_seeds']}</div><div class="l">强推荐 A 种子</div></div>
  <div class="stat"><div class="n">{s['kb_count']}</div><div class="l">B 方向知识库</div></div>
  <div class="stat"><div class="n">{s['total_ideas']}</div><div class="l">候选 Idea</div></div>
  <div class="stat"><div class="n">{s['total_validated']}</div><div class="l">通过严格验证</div></div>
  <div class="stat"><div class="n">{s['total_plans']}</div><div class="l">输出计划书</div></div>
</div>"""


def render_seed_card(idx, c):
    title = esc((c.get("title") or "")[:140])
    url = esc(c.get("url") or "#")
    conclusion = esc((c.get("conclusion") or "")[:300])
    channel = esc(c.get("channel") or "")
    comments = c.get("comments") or 0
    score = c.get("score") or 0
    judgment = (c.get("judgment") or "").replace("**", "")

    con = c.get("conclusion") or ""
    if "强推荐" in con:
        tag_class, tag_text = "tag-strong", "强推荐"
    elif "值得" in con or "深入" in con:
        tag_class, tag_text = "tag-worth", "值得深入"
    elif "不适合" in con:
        tag_class, tag_text = "tag-skip", "不适合"
    else:
        tag_class, tag_text = "tag-skip", "待判断"

    meta_parts = []
    if channel:
        meta_parts.append(f'<span class="ch">{channel}</span>')
    if comments:
        meta_parts.append(f'<span class="hot">{comments} 评论</span>')
    if score:
        meta_parts.append(f'<span>{score}</span>')
    meta = " ".join(meta_parts)

    return f"""
<div class="card seed-card">
  <div class="card-top">
    <span class="rank">{idx}</span>
    <h4><a href="{url}" target="_blank">{title}</a></h4>
    <span class="tag {tag_class}">{tag_text}</span>
  </div>
  <div class="meta">{meta}</div>
  <div class="conclusion"><b>判定：</b>{conclusion}</div>
  <details><summary>完整研判 (点击展开)</summary><pre>{esc(judgment)}</pre></details>
</div>"""


def render_plan_card(idx, p):
    seed_title = esc((p.get("seed_title") or "")[:120])
    b_domain = esc(p.get("b_domain") or "")
    b_problem = esc(p.get("b_problem") or "")
    source_model = esc(p.get("source_model") or "")
    idea_text = esc(p.get("idea_text") or "")
    plan = esc(p.get("plan") or "")
    forge_file = esc(p.get("forge_file") or "")

    # validation box
    val_box = ""
    validation = p.get("validation")
    if isinstance(validation, dict):
        votes_pass = validation.get("votes", 0)
        total = validation.get("total", 0)
        val_box = f'<div class="val-box">✅ 严格交叉验证通过 ({votes_pass}/{total})</div>'
    elif validation:
        val_box = f'<div class="val-box">✅ 严格交叉验证通过</div>'

    # consensus check
    cc_html = ""
    consensus_check = p.get("consensus_check")
    if consensus_check:
        if isinstance(consensus_check, dict):
            cc_text = esc(str(consensus_check.get("reason") or ""))
        else:
            cc_text = esc(str(consensus_check)[:200])
        if cc_text:
            cc_html = f'<div class="cc-box">🤝 共识检查：{cc_text}</div>'

    # freshness refresh
    fr_html = ""
    fr = p.get("freshness_refresh")
    if isinstance(fr, dict):
        refresher = esc(fr.get("refresher") or "")
        b_library_used = fr.get("b_library_used", False)
        arxiv_used = fr.get("arxiv_used", False)
        stale = fr.get("stale_detected") or []
        stale_str = esc(", ".join(stale) if stale else "（无）")
        fr_html = (
            f'<div class="fr-box">🔄 时新性已升级（用 {refresher} 改写；'
            f'B库参考{b_library_used} arxiv参考{arxiv_used}）'
            f'<br><small>原文中过时项：{stale_str}</small></div>'
        )

    return f"""
<div class="card plan-card">
  <div class="plan-header">
    <span class="plan-rank">{idx}</span>
    <span class="model-tag">{source_model}</span>
    <span class="domain-tag">{b_domain}</span>
    <span class="seed-tag">来自种子：{seed_title}</span>
  </div>
  <div class="b-problem"><b>B 领域问题：</b>{b_problem}</div>
  {val_box}
  {cc_html}
  <details open><summary>📌 Idea 原文</summary><pre>{idea_text}</pre></details>
  <details><summary>📋 完整计划书（预实验 + 完整实验）</summary><pre>{plan}</pre></details>
  {fr_html}
  <div class="src-file"><small>来源：{forge_file}</small></div>
</div>"""


def render_timeline(timeline):
    parts = []
    for entry in timeline:
        date = entry["date"]
        seeds = entry["seeds"]
        plans = entry["plans"]

        d_fmt = f"{date[:4]}-{date[4:6]}-{date[6:]}"
        seed_count = len(seeds)
        strong_count = sum(1 for s in seeds if "强推荐" in (s.get("conclusion") or ""))
        plan_count = len(plans)

        parts.append('<div class="day-block">')
        parts.append('<div class="day-header">')
        parts.append(f'<h3>📅 {d_fmt}</h3>')
        parts.append(
            f'<span class="badge badge-seed">{seed_count} 候选 / <b>{strong_count}</b> 强推荐</span> '
            f'<span class="badge badge-plan">{plan_count} 计划书</span>'
        )
        parts.append('</div>')

        if not seeds and not plans:
            parts.append('<p style="color:#6b7280;">这一天没有数据。</p>')
        else:
            if seeds:
                parts.append('<div class="day-section"><h4>🌱 当天大浪淘沙候选种子</h4>')

                def seed_sort_key(s):
                    con = s.get("conclusion") or ""
                    if "强推荐" in con:
                        return 0
                    if "值得" in con or "深入" in con:
                        return 1
                    if "不适合" in con:
                        return 2
                    return 3

                for i, s in enumerate(sorted(seeds, key=seed_sort_key), 1):
                    parts.append(render_seed_card(i, s))
                parts.append('</div>')

            if plans:
                parts.append('<div class="day-section"><h4>💡 当天 Forge 通过验证 + 产出计划书</h4>')
                for i, p in enumerate(plans, 1):
                    parts.append(render_plan_card(i, p))
                parts.append('</div>')

        parts.append('</div>')

    content = "\n".join(parts)
    return f'<div class="tab-content active" id="tab-timeline">\n{content}\n</div>'


def render_pipeline_tab():
    return """<div class="tab-content" id="tab-pipeline">
<h2>🔄 系统流程</h2>
<h3>模块一：大浪淘沙（信息聚合 + 热点筛选）</h3>
<div class="info-box">
<strong>14 个白色合规渠道：</strong>
<ul>
<li><b>社区讨论</b>: Reddit (r/MachineLearning, r/LocalLLaMA, r/singularity) + Hacker News</li>
<li><b>研究者博客</b>: OpenAI / DeepMind / Google Research / MSR / BAIR / Sebastian Raschka / Karpathy / Simon Willison / HF Blog</li>
<li><b>媒体源</b>: 量子位 RSS / Leiphone / MarkTechPost / VentureBeat / Paper Digest</li>
<li><b>学术</b>: arXiv (cs.AI/LG/CL/CV/MA) / HuggingFace Daily Papers / OpenReview / Emergent Mind</li>
<li><b>代码</b>: GitHub Trending (monthly)</li>
<li><b>社交</b>: Twitter/X 大佬推文 (twikit)</li>
</ul>
</div>
<h3>筛选漏斗</h3>
<div class="info-box">
<ul>
<li>跨天去重 → 规则初筛 → LLM (Gemini Flash) insight 过滤 → LLM (Gemini Pro) A+B 迁移研判</li>
<li>最终输出：强推荐 / 值得深入 / 不适合 三级结论</li>
</ul>
</div>
<h3>模块二：Idea Forge（创意生成 + 严格交叉验证）</h3>
<div class="info-box">
<ul>
<li>以强推荐种子为输入，结合 B 领域知识库，生成迁移 Idea</li>
<li>多模型交叉验证（D1 机制深度 / D2 方法简洁 / D3 实验充分 / D4 时新性）</li>
<li>通过验证的 Idea 输出完整计划书（预实验 + 完整实验）</li>
<li>可选：时新性升级（检测过时基准 / 数据集并用最新替换）</li>
</ul>
</div>
</div>"""


def render_kb_tab():
    parts = ['<div class="tab-content" id="tab-kb">']
    parts.append('<h2>📘 B 领域知识库</h2>')

    if not KB_DIR.exists():
        parts.append('<p style="color:#6b7280;">知识库目录不存在。</p>')
        parts.append('</div>')
        return "\n".join(parts)

    md_files = sorted(
        f for f in KB_DIR.glob("*.md") if f.name.lower() != "readme.md"
    )

    if not md_files:
        parts.append('<p style="color:#6b7280;">暂无知识库文件。</p>')
    else:
        for mf in md_files:
            try:
                content = mf.read_text(encoding="utf-8")
            except Exception:
                content = "(读取失败)"
            char_count = len(content)
            line_count = content.count("\n") + 1
            parts.append(f'<div class="kb-entry">')
            parts.append(
                f'<details><summary><b>{esc(mf.name)}</b> '
                f'<span class="kb-meta">{char_count} 字符 / {line_count} 行</span></summary>'
                f'<pre class="kb-content">{esc(content)}</pre></details>'
            )
            parts.append('</div>')

    parts.append('</div>')
    return "\n".join(parts)


def generate():
    timeline = collect_by_date()
    s = stats_global(timeline)

    stats_html = render_stats_bar(s)
    timeline_html = render_timeline(timeline)
    pipeline_html = render_pipeline_tab()
    kb_html = render_kb_tab()

    now_str = datetime.now().strftime('%Y-%m-%d %H:%M')

    page = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>AutoResearch · Idea Forge Timeline</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{
  font-family: -apple-system, BlinkMacSystemFont, "PingFang SC", "Microsoft YaHei", sans-serif;
  background: #0f1117; color: #e4e4e7; line-height: 1.6; padding: 20px;
}}
.container {{ max-width: 1280px; margin: 0 auto; }}
header {{
  background: linear-gradient(135deg, #1a1b2e, #16213e);
  border: 1px solid #2a2d3e; border-radius: 14px;
  padding: 28px; margin-bottom: 20px;
  display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 12px;
}}
header h1 {{
  font-size: 24px;
  background: linear-gradient(90deg, #60a5fa, #a78bfa);
  -webkit-background-clip: text; -webkit-text-fill-color: transparent;
}}
header .sub {{ color: #9ca3af; font-size: 12px; margin-top: 6px; }}
header .sub a {{ color: #a78bfa; text-decoration: none; }}
header .sub a:hover {{ text-decoration: underline; }}

.stats {{
  display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: 10px; margin-bottom: 20px;
}}
.stat {{
  background: #1a1b2e; border: 1px solid #2a2d3e;
  border-radius: 10px; padding: 14px; text-align: center;
}}
.stat .n {{ font-size: 26px; font-weight: 700; color: #60a5fa; }}
.stat .l {{ color: #9ca3af; font-size: 11px; margin-top: 2px; }}

.tabs {{ margin-bottom: 20px; display: flex; gap: 8px; flex-wrap: wrap; }}
.tab-btn {{
  background: #1a1b2e; border: 1px solid #2a2d3e; color: #9ca3af;
  border-radius: 8px; padding: 8px 16px; cursor: pointer; font-size: 13px;
  transition: all .2s;
}}
.tab-btn:hover {{ border-color: #3b82f6; color: #e4e4e7; }}
.tab-btn.active {{ background: #1e3a5f; border-color: #3b82f6; color: #60a5fa; font-weight: 600; }}
.tab-content {{ display: none; }}
.tab-content.active {{ display: block; }}

.day-block {{ margin-bottom: 32px; }}
.day-header {{
  background: linear-gradient(135deg, #1a1b2e, #16213e);
  border: 1px solid #2a2d3e; border-radius: 10px;
  padding: 14px 20px; margin-bottom: 12px;
  display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 8px;
}}
.day-header h3 {{ font-size: 18px; color: #60a5fa; margin: 0; }}
.badge {{ padding: 3px 10px; border-radius: 12px; font-size: 11px; font-weight: 500; }}
.badge-seed {{ background: #1e293b; color: #9ca3af; }}
.badge-seed b {{ color: #34d399; }}
.badge-plan {{ background: #1e3a5f; color: #60a5fa; }}

.day-section {{ margin-left: 14px; margin-bottom: 16px; }}
.day-section h4 {{ color: #a78bfa; font-size: 14px; margin-bottom: 8px; }}

.card {{
  background: #1a1b2e; border: 1px solid #2a2d3e;
  border-radius: 10px; padding: 16px 18px; margin-bottom: 10px;
  transition: border-color .2s;
}}
.card:hover {{ border-color: #3b82f6; }}

/* Seed card */
.seed-card .card-top {{
  display: flex; align-items: center; gap: 8px; margin-bottom: 6px; flex-wrap: wrap;
}}
.rank {{
  background: #111827; color: #60a5fa; font-weight: 700; font-size: 12px;
  min-width: 24px; height: 24px; border-radius: 5px;
  display: flex; align-items: center; justify-content: center; flex-shrink: 0;
}}
.seed-card h4 {{ font-size: 13.5px; color: #f4f4f5; flex: 1; min-width: 200px; font-weight: 600; }}
.seed-card h4 a {{ color: #f4f4f5; text-decoration: none; }}
.seed-card h4 a:hover {{ color: #60a5fa; }}
.meta {{ font-size: 11px; color: #6b7280; margin-bottom: 6px; display: flex; gap: 10px; flex-wrap: wrap; }}
.meta .ch {{ color: #a78bfa; font-weight: 500; }}
.meta .hot {{ color: #f59e0b; }}
.conclusion {{ font-size: 12px; color: #d1d5db; margin-bottom: 6px; }}
.tag {{
  display: inline-block; padding: 3px 10px; border-radius: 4px;
  font-size: 11px; font-weight: 600; flex-shrink: 0;
}}
.tag-strong {{ background: #064e3b; color: #34d399; }}
.tag-worth {{ background: #422006; color: #fbbf24; }}
.tag-skip {{ background: #1f2937; color: #6b7280; }}

details {{ margin-top: 6px; }}
summary {{ cursor: pointer; color: #9ca3af; font-size: 12px; }}
summary:hover {{ color: #60a5fa; }}
pre {{
  background: #111827; border-radius: 6px; padding: 12px;
  font-size: 11.5px; line-height: 1.7; color: #d1d5db;
  white-space: pre-wrap; word-break: break-word; margin-top: 6px;
  max-height: 400px; overflow-y: auto;
}}

/* Plan card */
.plan-card .plan-header {{
  display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-bottom: 8px;
}}
.plan-rank {{
  background: #111827; color: #a78bfa; font-weight: 700; font-size: 12px;
  min-width: 24px; height: 24px; border-radius: 5px;
  display: flex; align-items: center; justify-content: center; flex-shrink: 0;
}}
.model-tag {{
  background: #1e3a5f; color: #60a5fa; border-radius: 4px;
  padding: 2px 8px; font-size: 11px; font-weight: 600;
}}
.domain-tag {{
  background: #2d1f47; color: #a78bfa; border-radius: 4px;
  padding: 2px 8px; font-size: 11px; font-weight: 600;
}}
.seed-tag {{ color: #9ca3af; font-size: 11px; }}
.b-problem {{ font-size: 12px; color: #d1d5db; margin-bottom: 8px; }}
.val-box {{
  background: #064e3b; color: #34d399; border-radius: 6px;
  padding: 6px 12px; font-size: 12px; margin-bottom: 8px;
}}
.cc-box {{
  background: #1e3a5f; color: #93c5fd; border-radius: 6px;
  padding: 6px 12px; font-size: 12px; margin-bottom: 8px;
}}
.fr-box {{
  background: #1c1f2e; border: 1px solid #374151; color: #9ca3af;
  border-radius: 6px; padding: 6px 12px; font-size: 11px; margin-top: 8px;
}}
.src-file {{ margin-top: 8px; color: #6b7280; }}

h2 {{ font-size: 20px; color: #60a5fa; margin-bottom: 16px; }}
h3 {{ font-size: 16px; color: #a78bfa; margin: 16px 0 8px; }}

.info-box {{
  background: #111827; border: 1px solid #2a2d3e; border-radius: 8px;
  padding: 14px 18px; margin-bottom: 14px; font-size: 13px; color: #d1d5db; line-height: 1.9;
}}
.info-box ul {{ padding-left: 20px; }}
.info-box li {{ margin-bottom: 4px; }}

.kb-entry {{ margin-bottom: 12px; }}
.kb-meta {{ color: #6b7280; font-size: 11px; font-weight: normal; margin-left: 8px; }}
.kb-content {{ max-height: 600px; overflow-y: auto; }}

a {{ color: #60a5fa; text-decoration: none; }}
a:hover {{ text-decoration: underline; }}
</style>
</head>
<body>
<div class="container">

<header>
<div>
<h1>AutoResearch · Idea Forge Timeline</h1>
<div class="sub">{now_str} (UTC+8) &nbsp;·&nbsp; <a href="./index.html">← 返回大浪淘沙主页</a></div>
</div>
</header>

{stats_html}


<div class="tabs">
<button class="tab-btn active" onclick="showTab(event, 'timeline')">📅 每日 Timeline（种子 + 计划书）</button>
<button class="tab-btn" onclick="showTab(event, 'pipeline')">🔄 系统流程</button>
<button class="tab-btn" onclick="showTab(event, 'kb')">📘 B 领域知识库</button>
</div>

{timeline_html}
{pipeline_html}
{kb_html}

</div>
<script>
function showTab(ev, name) {{
  document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
  document.querySelectorAll('.tab-btn').forEach(el => el.classList.remove('active'));
  document.getElementById('tab-' + name).classList.add('active');
  ev.currentTarget.classList.add('active');
}}
</script>
</body></html>
"""

    output_path = PROJECT_ROOT / "ideas.html"
    output_path.write_text(page, encoding="utf-8")
    print(f"生成 {output_path} ({len(page.encode('utf-8'))} 字节)")


if __name__ == "__main__":
    generate()
