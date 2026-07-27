"""
每日完整流水线：大浪淘沙（信息聚合+筛选）→ Idea Forge（A+B 生成+验证+计划书）
后台运行，无需人工干预。
"""

import sys
import json
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))
sys.path.insert(0, str(Path(__file__).parent / "src" / "collectors"))

LOG_DIR = Path(__file__).parent / "logs"
LOG_DIR.mkdir(exist_ok=True)


def log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOG_DIR / f"daily_{datetime.now().strftime('%Y%m%d')}.log", "a") as f:
        f.write(line + "\n")


def run_dalang_taosha():
    """模块一：大浪淘沙 - 信息采集 + 筛选种子"""
    log("=" * 60)
    log("模块一：大浪淘沙 - 信息采集与热点筛选")
    log("=" * 60)

    from pipeline_v4 import run_pipeline_v4
    result = run_pipeline_v4()
    return result


def run_extra_channels():
    """已合并进 pipeline_v4.collect_all_channels()，此函数保留为空壳以防老代码引用"""
    log("  附加渠道已并入 pipeline_v4，跳过独立采集")
    return []


def run_idea_forge(seeds):
    """模块二：Idea Forge - A+B 生成+验证+计划书"""
    log("=" * 60)
    log(f"模块二：Idea Forge - {len(seeds)} 个种子")
    log("=" * 60)

    from idea_forge.forge import run_idea_forge
    from idea_forge.b_library import get_b_library

    # 用全部 B 方向
    b_ids = [b["id"] for b in get_b_library()]
    result = run_idea_forge(seeds, b_ids=b_ids)
    return result


def update_dashboard():
    """更新网页"""
    log("更新网页...")
    from generate_dashboard import generate_html
    generate_html()


def git_push():
    """推送到 GitHub Pages（已暂停使用）"""
    # import subprocess
    # try:
    #     subprocess.run(
    #         ["git", "add", "-A"],
    #         cwd=str(Path(__file__).parent), capture_output=True
    #     )
    #     subprocess.run(
    #         ["git", "commit", "-m", f"Daily auto: {datetime.now().strftime('%Y-%m-%d')}"],
    #         cwd=str(Path(__file__).parent), capture_output=True
    #     )
    #     subprocess.run(
    #         ["git", "push", "origin", "gh-pages"],
    #         cwd=str(Path(__file__).parent), capture_output=True
    #     )
    #     log("  Git push 完成")
    # except Exception as e:
    #     log(f"  Git push 失败: {e}")
    log("  Git push 已暂停")


def run_3month_mode():
    """3个月全量模式：采集→Pro全量研判→强推荐种子→大规模Forge"""
    log("=" * 60)
    log("【3月全量模式】 12渠道 × 90天 → Pro全量研判 → 强推荐种子 → Forge")
    log("=" * 60)

    from pipeline_v4 import run_pipeline_v4
    from idea_forge.forge import run_idea_forge
    from idea_forge.b_library import get_b_library

    tag = f"3month_{datetime.now().strftime('%Y%m%d_%H%M')}"
    result = run_pipeline_v4(
        time_filter="year", time_filter_days=90, arxiv_days=90, hf_days=90,
        top_k=500,  # 允许 Pro 研判全量 insight，top_k=500 相当于不限制
        output_tag=tag,
    )

    # 直接从 Pro 研判结果取强推荐
    final_candidates = result.get("final_candidates", [])
    strong_seeds = [c for c in final_candidates if "强推荐" in c.get("conclusion", "")]
    worth_seeds  = [c for c in final_candidates if "值得" in c.get("conclusion", "") or "深入" in c.get("conclusion", "")]
    top_seeds = (strong_seeds + worth_seeds)[:50]

    log(f"  Pro研判: {len(final_candidates)} 条 → 强推荐 {len(strong_seeds)} + 值得深入 {len(worth_seeds)}")
    log(f"  送入 Forge 种子: {len(top_seeds)} 条")

    b_ids = [b["id"] for b in get_b_library()]
    log(f"  开始大规模Forge: {len(top_seeds)} 种子 × {len(b_ids)} B方向 × 3模型")
    forge_result = run_idea_forge(top_seeds, b_ids=b_ids)
    s = forge_result.get("summary", {})
    log(f"  Forge完成: ideas={s.get('total_ideas')} validated={s.get('total_validated')} plans={s.get('total_plans')}")
    return forge_result


def main():
    start = time.time()
    today = datetime.now().strftime("%Y-%m-%d")
    log(f"{'═' * 60}")
    log(f"每日全流程开始: {today}")
    log(f"{'═' * 60}")

    # 检测3月全量触发文件
    trigger = Path(__file__).parent / "trigger_3month.txt"
    if trigger.exists():
        log("  检测到 trigger_3month.txt，切换到3月全量模式")
        trigger.unlink()  # 删除触发文件，避免重复执行
        try:
            run_3month_mode()
        except Exception as e:
            log(f"  3月全量模式失败: {e}")
        update_dashboard()
        try:
            from generate_idea_page import generate as gen_idea
            gen_idea()
        except Exception as e:
            log(f"Idea页面更新失败: {e}")
        git_push()
        elapsed = time.time() - start
        log(f"全流程完成，耗时 {elapsed/60:.1f} 分钟")
        return

    # 1. 大浪淘沙
    try:
        v4_result = run_dalang_taosha()
    except Exception as e:
        log(f"大浪淘沙失败: {e}")
        v4_result = None

    # 2. 附加渠道
    try:
        extra = run_extra_channels()
    except Exception as e:
        log(f"附加渠道失败: {e}")
        extra = []

    # 3. 提取强推荐种子（优先用 all_insightful 批量评分，fallback 到 final_candidates）
    seeds = []
    if v4_result:
        all_insights = v4_result.get("all_insightful", [])
        if len(all_insights) >= 20:
            # 有足够insight，批量评分选top15
            import re, json as _json
            from llm_client import simple_mode_enabled, call_model as _call_model

            def _rank_call(prompt, **kwargs):
                """批量打分用的排名模型调用：简易模式走统一端点，否则走 Vertex Gemini。"""
                if simple_mode_enabled():
                    return _call_model("gemini-flash", prompt, **kwargs)
                from idea_forge.gemini_vertex import call_gemini as _call_vertex_gemini
                return _call_vertex_gemini(prompt, model="gemini-flash", **kwargs)

            log(f"  使用 all_insightful 批量评分 ({len(all_insights)} 条)")
            for i in range(0, len(all_insights), 20):
                batch = all_insights[i:i+20]
                numbered = "\n".join(f"{j+1}. {it['title'][:80]}" for j, it in enumerate(batch))
                r = _rank_call(
                    f"对以下研究内容打分1-10（创新价值）：\n{numbered}\n\n只返回JSON数组。",
                    max_tokens=200, temperature=0)
                try:
                    m = re.search(r'\[[\d\s,\.]+\]', r or "")
                    scores = _json.loads(m.group()) if m else []
                    for it, sc in zip(batch, scores):
                        it["_rank_score"] = float(sc)
                except Exception:
                    for it in batch:
                        it.setdefault("_rank_score", 5.0)
            for it in all_insights:
                it.setdefault("_rank_score", 5.0)
            all_insights.sort(key=lambda x: x.get("_rank_score", 0), reverse=True)
            seeds = all_insights[:15]
            log(f"  批量评分选出 {len(seeds)} 个种子（分数: {seeds[-1]['_rank_score']:.1f}~{seeds[0]['_rank_score']:.1f}）")
        else:
            # insight 数量少，直接用强推荐
            candidates = v4_result.get("final_candidates", [])
            seeds = [c for c in candidates if "强推荐" in c.get("conclusion", "")]
    log(f"强推荐种子: {len(seeds)} 个")

    # 如果今天没有新种子，翻历史文件找（从最近往前）
    if not seeds:
        import glob
        verified_dir = Path(__file__).parent / "data" / "verified"
        all_files = sorted(
            glob.glob(str(verified_dir / "final_*.json")) +
            glob.glob(str(verified_dir / "pipeline_v4_*.json")) +
            glob.glob(str(verified_dir / "pipeline_v5_*.json")),
            reverse=True
        )
        all_seeds = {}  # title -> seed dict
        for fpath in all_files[:10]:
            try:
                with open(fpath) as f:
                    fdata = json.load(f)
                cands = fdata.get("final_candidates", fdata.get("top_candidates", []))
                for c in cands:
                    if "强推荐" in c.get("conclusion", ""):
                        title = c.get("title", "")
                        if title and title not in all_seeds:
                            all_seeds[title] = c
            except Exception as e:
                continue
        seeds = list(all_seeds.values())
        log(f"从历史文件累积强推荐种子: {len(seeds)} 个")

    # 4. Idea Forge（对所有强推荐种子跑 A+B）
    if seeds:
        try:
            forge_result = run_idea_forge(seeds)
            log(f"Forge 结果: {forge_result['summary']}")
        except Exception as e:
            log(f"Idea Forge 失败: {e}")
    else:
        log("无种子可处理，跳过 Forge")

    # 5. 更新网页（主页 + Idea Forge 页）
    try:
        update_dashboard()
    except Exception as e:
        log(f"主页更新失败: {e}")

    try:
        from generate_idea_page import generate as gen_idea
        gen_idea()
        log("Idea Forge 页面已更新")
    except Exception as e:
        log(f"Idea 页面更新失败: {e}")

    # 6. 推送
    git_push()

    elapsed = time.time() - start
    log(f"{'═' * 60}")
    log(f"全流程完成，耗时 {elapsed/60:.1f} 分钟")
    log(f"{'═' * 60}")


if __name__ == "__main__":
    main()
