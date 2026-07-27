"""
Idea Forge - 第二模块核心（重构版）
从 A 种子 × B 方向库 → 高质量 A+B idea → 严格交叉验证 → 计划书

核心改进:
- 不让模型自由发挥选 B，而是从 B_LIBRARY 中明确指定 B + 喂足上下文
- idea 生成 prompt 要求深度（必须说清机制同构性）
- 交叉验证保持严格（目标是顶会水平）
- 只有真正好的 idea 才能进入计划书阶段
"""

import json
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from llm_client import call_model, simple_mode_enabled
from idea_forge.b_library import get_b_library, format_b_context
from idea_forge.consensus_check import filter_by_consensus
from idea_forge.freshness import step2_5_freshness_refresh
from idea_forge.gemini_vertex import call_gemini as call_vertex_gemini

# 三个模型各自独立思考；交叉验证时全员评审（包括生成者自己），避免单一模型主导否决。
# 简易模式（只配置了一个 AUTORESEARCH_API_BASE_URL + AUTORESEARCH_API_KEY）下，
# 这三个"角色"仍然保留，但都会路由到同一个端点——用户不需要三个不同的 provider。
IDEA_MODELS = ["gemini-pro", "gpt-5.5", "claude-opus"]
PLAN_MODEL = "gpt-5.5"

FRESHNESS_REQUIREMENT = """【时新性引导 - 尽量遵守，但不必担心被一票否决】
当前时间是 2026 年 5 月。**优先使用 2025-2026 年最新的模型、数据集、benchmark**。
若不确定最新版本是什么，请尽量用你**已知最近**的型号；后续 Step 2.5 会通过 B 库 + arxiv 自动刷新升级，
所以构思时**优先把机制讲清楚**，模型/数据细节稍旧也没关系。

参考方向（B 库可能持续更新，以你知道的最新为准）：
- 多模态：Qwen2.5-VL / InternVL3 / LLaVA-OneVision / Cambrian-1 / NVILA / Molmo（或更新者）
- LLM 推理：DeepSeek-R1/V3.1 / Qwen3 / Llama-4 / QwQ / o-series（或更新者）
- Agent 记忆：MemGPT-v2 / Letta / Mem0 / LangMem 2025（或更新者）
- Benchmark：MMMU-Pro / MEGA-Bench / LiveBench / SWE-Bench-Verified / ARC-AGI-2（或更新者）
- 避免：LLaVA-1.5/1.6、Qwen2-VL、InternVL2、Llama-2、Vicuna、GPT-3.5 等已被替代的型号作主基线
"""


def call_idea_model(model_name, prompt, **kwargs):
    """Idea Forge 内的模型路由。

    简易模式下（只配置了 AUTORESEARCH_API_BASE_URL + AUTORESEARCH_API_KEY），
    所有角色统一走 call_model()，它会自动转发到同一个端点。
    否则 Gemini 固定走 Vertex，其他模型保留原多 provider 路由。
    """
    if not simple_mode_enabled() and model_name.startswith("gemini-"):
        return call_vertex_gemini(
            prompt,
            model=model_name,
            temperature=kwargs.get("temperature", 0.3),
            max_tokens=kwargs.get("max_tokens", 2000),
        )
    return call_model(model_name, prompt, **kwargs)


def generate_deep_idea_prompt(seed, b_direction):
    """
    构造深度 idea 生成 prompt
    关键变化: 加入 B 方向的完整领域知识 MD，让模型不再"缺常识"
    """
    title = seed.get("title", "")
    judgment = seed.get("llm_judgment", "")
    # 从 judgment 里提取核心 insight 那一行
    core_insight = ""
    for line in judgment.split("\n"):
        line = line.strip()
        if "核心insight" in line or "核心 insight" in line:
            core_insight = line
            break

    b_context = format_b_context(b_direction, include_full_knowledge=True)

    prompt = (
        "你是一位在 B 领域深耕多年的顶级研究者，目标是产出能被 ICLR/NeurIPS/ICML 接收的论文。\n"
        "当前是 2026 年 5 月，你必须使用最新的模型与 benchmark，否则论文会被审稿人秒拒。\n\n"
        "【任务】\n"
        "下面给你一个\"A 种子\"（近期被社区热议的技术 insight）和一个\"B 方向\"（你所在的研究领域）。\n"
        "B 方向附带了**该领域的真实社区共识、路线之争、常见误区**——你必须严格遵守这些常识。\n\n"
        "请思考：A 的核心机制能否真正解决 B 的本质问题？\n\n"
        "【A 种子 - 核心 Insight】\n"
        "标题: " + title + "\n"
        "洞见: " + core_insight + "\n\n"
        "【B 方向 - 包含社区真实共识】\n" + b_context + "\n\n"
        "【硬件约束】\n"
        "- 8 张 L20 GPU（48GB 显存，无 NVLink）\n"
        "- 4 周时间\n"
        "- 只能用公开数据集\n\n"
        + FRESHNESS_REQUIREMENT + "\n\n"
        "【核心要求 - 极其重要，必须严格遵守】\n\n"
        "1. **必须尊重 B 领域的社区共识**：\n"
        "   - 看\"常见错误直觉\"部分！如果你的 idea 撞到了这些错误直觉，直接放弃，输出 NO_MATCH\n"
        "   - 例如：如果 B 是视觉 token 管理，不要说\"按时间衰减\"（因为视觉 token 没时间维度）\n"
        "   - 例如：如果 B 是 Agent 记忆，不要说\"直接套遗忘曲线\"（社区不认同强行遗忘）\n\n"
        "2. **必须从 B 领域\"可行创新切入点\"出发**：\n"
        "   - 在 MD 的\"值得做的方向\"里找你要做的事\n"
        "   - 如果 A 的机制能给这些方向带来新价值，那就是好 idea\n"
        "   - 否则输出 NO_MATCH\n\n"
        "【输出格式】\n"
        "如果有合理映射，请输出：\n\n"
        "核心idea（一句话）: [用 A 的机制解决 B 的某个具体问题]\n\n"
        "机制同构性: [详细解释为什么 A 的机制在 B 领域有效，必须有数学/物理直觉]\n\n"
        "方法简述: [核心修改是什么，3-5句]\n\n"
        "关键实验:\n"
        "- 数据集: [必须是 B 库或 FRESHNESS 中的最新 benchmark]\n"
        "- 基线: [必须是 B 库中的最新基线]\n"
        "- 评估指标: [具体指标]\n"
        "- 预期提升: [定量预期]\n\n"
        "如果没有合理映射，只输出：NO_MATCH"
    )
    return prompt


def step1_deep_ideation(seed, b_directions):
    """
    Step 1: 对每个 A×B 配对，让三个模型各自深度构思
    """
    all_ideas = []
    print("────────────────────────────────────────────────────────────")
    print(f"  Step 1: 深度构思 (A × {len(b_directions)} 个 B 方向 × 3 模型)")
    print(f"  A: {seed.get('title', '')[:100]}")

    for b in b_directions:
        print(f"\n  B方向: {b.get('domain', '')} | {b.get('problem', '')[:50]}")
        prompt = generate_deep_idea_prompt(seed, b)

        for model in IDEA_MODELS:
            print(f"    [{model}] 构思中...")
            result = call_idea_model(model, prompt, max_tokens=2500, temperature=0.3)
            if not result:
                print(f"    [{model}] 调用失败")
                continue
            if "NO_MATCH" in result:
                print(f"    [{model}] → 无合理映射")
                continue

            # 提取核心 idea 行
            core_line = ""
            for line in result.split("\n"):
                line = line.strip()
                if "核心idea" in line:
                    core_line = line[-100:]
                    break

            all_ideas.append({
                "seed_title": seed.get("title", ""),
                "seed_url": seed.get("reddit_url") or seed.get("url", ""),
                "b_domain": b.get("domain", ""),
                "b_id": b.get("id", ""),
                "b_problem": b.get("problem", ""),
                "source_model": model,
                "idea_text": result,
                "core_summary": core_line,
            })
            time.sleep(0.5)

    print(f"\n  共产生 {len(all_ideas)} 个候选 idea")
    return all_ideas


def _parse_verdict(result):
    """从评审输出里提取最终判定。支持中英混写。"""
    if not result:
        return False
    # 查最后 400 个字符
    tail = result[-400:]
    verdict_line = ""
    for line in reversed(tail.splitlines()):
        line = line.strip()
        if line and line.isascii():
            target = line.lower()
            if "verdict" in target or "pass" in target or "accept" in target:
                verdict_line = target
                break
        elif line:
            verdict_line = line
            break

    neg_keys = ["不通过", "否", "fail", "reject", "no", "不合格", "不过", "未通过"]
    for k in neg_keys:
        if k in verdict_line.lower():
            return False
    return bool(verdict_line)


def step2_strict_validation(ideas):
    """
    Step 2: 严格交叉验证（目标顶会水平）
    全员评审：所有 IDEA_MODELS（包括生成者自己）都参与打分，避免单一模型主导否决。

    通过/不通过判定**只看 D1/D2/D3（机制深度、方法简洁、实验充分）**：3 票里 ≥2 票通过。
    D4（时新性）仅记录为 freshness_flags，**不再一票否决**——因为旧模型/数据可在
    Step 2.5 通过 B 库 + arxiv 搜索就地刷新升级，不应击杀好计划。
    """
    validated = []
    print("────────────────────────────────────────────────────────────")
    print(f"  Step 2: 严格交叉验证 ({len(ideas)} 个候选 × {len(IDEA_MODELS)} 评审员/全员评审)")
    print("  通过门槛：D1/D2/D3 ≥2 评审员通过；D4 仅作软警告供 Step 2.5 刷新")

    for idx, item in enumerate(ideas):
        source = item.get("source_model", "unknown")
        idea_text = item.get("idea_text", "")
        reviewers = list(IDEA_MODELS)  # 全员评审（含生成者）

        votes_pass = 0
        total_reviews = 0
        reviews = []
        freshness_flags = []

        for reviewer in reviewers:
            tag = "(self)" if reviewer == source else ""
            review_prompt = (
                "你是一位顶级 AI 会议（NeurIPS/ICLR/ICML/CVPR）的资深审稿人。\n"
                "当前是 2026 年 5 月。请严格按四个维度评审下面的研究方案。\n\n"
                "=== 方案 ===\n" + idea_text[:700] + "\n=== 方案结束 ===\n\n"
                "【评审维度 - 必须逐项给出明确判断】\n\n"
                "[D1] 机制深度: 机制映射是否有数学或物理直觉上的深层道理，而非表面类比硬凑？\n"
                "[D2] 方法简洁: 方法是否能用 2-3 句说清楚核心贡献？过度复杂会扣分。\n"
                "[D3] 实验充分: 实验设计能否 convincingly 验证假设？是否包含必要的消融与对照？\n"
                "[D4] 时新性（仅作软警告，不影响通过判定）:\n"
                "     提到的模型/数据/benchmark 是否是 2025-2026 最新的？\n"
                "     若发现过时项（如 LLaVA-1.5/1.6、Qwen2-VL、InternVL2、Llama-2、Vicuna、GPT-3.5），请列出。\n\n"
                "请逐项输出：D1通过/不通过 + 理由（1句）；D2通过/不通过 + 理由；D3通过/不通过 + 理由；"
                "D4时新性问题（如有则列出，无则写\"无\"）。\n"
                "最后一行输出：verdict: 通过 或 verdict: 不通过\n"
                "（verdict 只基于 D1/D2/D3，D4 不计入）"
            )

            result = call_idea_model(reviewer, review_prompt, max_tokens=700, temperature=0.2)
            if not result:
                print(f"    [{reviewer}{tag}] ⚠️ 调用失败")
                continue

            total_reviews += 1
            passed = _parse_verdict(result)
            if passed:
                votes_pass += 1

            # 检查 D4 时新性警告
            d4_stale = False
            for line in result.splitlines():
                line = line.strip().lower()
                if "d4" in line and "无" not in line and len(line) > 10:
                    d4_stale = True
                    freshness_flags.append(line[:80])

            reviews.append({
                "reviewer": reviewer,
                "passed": passed,
                "review": result[:160],
            })

            reason = "✅ 通过" if passed else "❌"
            print(f"    [{reviewer}{tag}] → {reason} | D4: {'有警告' if d4_stale else 'OK'}")
            time.sleep(0.5)

        pass_rate = votes_pass / max(total_reviews, 1)
        verdict_pass = votes_pass >= 2  # ≥2/3 通过

        if verdict_pass:
            item["validation"] = {
                "votes_pass": votes_pass,
                "total_reviews": total_reviews,
                "pass_rate": pass_rate,
                "reviews": reviews,
            }
            item["freshness_flags"] = freshness_flags
            validated.append(item)
            print(f"  → ✅ 通过 ({votes_pass}/{total_reviews}){' [时新性有警告]' if freshness_flags else ''}")
        else:
            print(f"  → ❌ 未通过 ({votes_pass}/{total_reviews})")

    print(f"\n  通过验证: {len(validated)}/{len(ideas)}")
    return validated


def step3_plan_generation(validated_ideas):
    """
    Step 3: 为通过验证的 idea 生成详细计划书（预实验 + 完整计划）
    """
    print("────────────────────────────────────────────────────────────")
    print(f"  Step 3: 生成计划书 ({len(validated_ideas)} 个通过验证的 idea)")

    for item in validated_ideas:
        prompt = (
            "你是一位有丰富实验经验的 AI 研究者。请为以下通过同行评审的 idea 制定可执行计划书。\n\n"
            "=== Idea ===\n" + item.get("idea_text", "") + "\n===\n\n"
            "硬件: 8 张 L20 (48GB, 无NVLink)，3TB 存储，总计 4 周。\n\n"
            "请输出极具执行力的计划（每一步都具体到可以直接执行）:\n\n"
            "## 预实验计划（第 1 周）\n"
            "目标: 用最小成本验证\"这个 idea 有没有信号\"。做完后能明确判断是否继续。\n\n"
            "1. 环境搭建:（哪个代码库、什么 Python 环境、如何配置）\n"
            "2. 数据准备:（数据集名称、下载命令、预处理步骤）\n"
            "3. 基线运行:（先跑一个 vanilla baseline 确认环境 OK）\n"
            "4. 核心验证实验:（最小改动实现核心 idea，跑一个小规模实验）\n"
            "5. 成功标准:（什么指标达到多少，或什么现象出现，算预实验通过）\n\n"
            "## 完整实验计划（第 2-4 周）\n"
            "1. 完整实现:（具体代码改动点）\n"
            "2. 消融实验:（必须做的消融，每个消融的目的）\n"
            "3. 对比实验:（与哪些 SOTA 对比，用哪些 benchmark）\n"
            "4. 分析实验:（可视化/case study/误差分析）\n"
            "5. 预期结果:（定量数字，论文贡献声明）"
        )

        # 优先用 PLAN_MODEL，失败轮换
        plan_model = PLAN_MODEL
        result = call_idea_model(plan_model, prompt, max_tokens=3000, temperature=0.3)
        if not result:
            for mtok in [m for m in IDEA_MODELS if m != plan_model]:
                print(f"  生成计划: {item.get('b_domain', '')} [{item.get('source_model', '')}]... 失败，尝试下一个...")
                result = call_idea_model(mtok, prompt, max_tokens=3000, temperature=0.3)
                if result:
                    break

        if result:
            item["plan"] = result
            print(f"    ✅ {item.get('b_domain', '')} [{item.get('source_model', '')}]")
        else:
            item["plan"] = "生成失败"
            print(f"    ❌ 所有模型均失败")

        time.sleep(3)

    return validated_ideas


def run_idea_forge(seeds, b_ids=None):
    """
    Idea Forge 主流程
    seeds: 大浪淘沙输出的强推荐种子
    b_ids: 指定用哪些 B 方向（None = 全部）
    """
    b_library = get_b_library()
    if b_ids:
        b_library = [b for b in b_library if b["id"] in b_ids]

    print("════════════════════════════════════════════════════════════")
    print("  Idea Forge - 研究方案锻造")
    print(f"  A 种子: {len(seeds)}")
    print(f"  B 方向: {len(b_library)} ({', '.join(b['id'] for b in b_library)})")
    print(f"  模型: {', '.join(IDEA_MODELS)}")
    print("  目标: 顶会级别论文")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    all_results = []

    for i, seed in enumerate(seeds):
        print(f"\n[{i+1}/{len(seeds)}] A: {seed.get('title', '')[:55]}")

        # Step 1: 深度构思
        ideas = step1_deep_ideation(seed, b_library)
        if not ideas:
            print("  无有效 idea，跳过")
            continue

        # Step 2: 严格交叉验证
        validated = step2_strict_validation(ideas)
        if not validated:
            print("  无 idea 通过验证")
            continue

        # Step 2.5: 时新性刷新
        validated = step2_5_freshness_refresh(validated, enable_arxiv=True)

        # 共识检查（防撞 B 领域常识）
        consensus_passed = filter_by_consensus(validated)
        if not consensus_passed:
            print("  无 idea 通过共识检查")
            continue

        # Step 3: 计划书生成
        with_plans = step3_plan_generation(consensus_passed)

        all_results.append({
            "seed_title": seed.get("title", ""),
            "seed_url": seed.get("reddit_url") or seed.get("url", ""),
            "total_ideas": len(ideas),
            "validated": len(validated),
            "plans": len([p for p in with_plans if p.get("plan") and p["plan"] != "生成失败"]),
            "results": with_plans,
        })

    # 保存结果
    output_dir = Path(__file__).parent.parent.parent / "data" / "idea_forge"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / f"forge_{datetime.now().strftime('%Y%m%d_%H%M')}.json"

    output = {
        "generated_at": datetime.now().isoformat(),
        "module": "idea_forge",
        "config": {
            "idea_models": IDEA_MODELS,
            "plan_model": PLAN_MODEL,
            "validation": "strict (顶会标准, >50% 通过)",
        },
        "results": all_results,
        "summary": {
            "seeds_processed": len(seeds),
            "total_ideas": sum(r.get("total_ideas", 0) for r in all_results),
            "total_validated": sum(r.get("validated", 0) for r in all_results),
            "total_plans": sum(r.get("plans", 0) for r in all_results),
        },
    }

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    s = output["summary"]
    print("\n  Forge 完成")
    print(f"  生成 idea: {s['total_ideas']}")
    print(f"  通过验证: {s['total_validated']}")
    print(f"  产出计划: {s['total_plans']}")
    print(f"  保存: {output_file}")

    return output
