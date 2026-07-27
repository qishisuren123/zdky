"""
Idea 生成后的外部共识验证
在 idea 通过交叉验证后，再做一次"撞共识检查"：
- 基于 B 方向的知识 MD
- 用 Gemini Pro 严格检查 idea 是否违反了社区共识
- 避免"看起来合理但业内人不会认可"的方案
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from llm_client import call_pro
from idea_forge.b_library import get_b_by_id, load_knowledge


def consensus_check(idea_item):
    """
    检查 idea 是否违反 B 领域社区共识
    返回: (通过?, 理由)
    """
    # 字段名兼容：早期写 "b_direction"，forge 现在写 "b_id"
    b_id = idea_item.get("b_id") or idea_item.get("b_direction", "")
    b = get_b_by_id(b_id)
    if not b:
        return True, "无 B 信息，跳过检查"

    knowledge = load_knowledge(b.get("knowledge_md", ""))
    if not knowledge:
        return True, "无知识 MD，跳过检查"

    idea_text = idea_item.get("idea_text", "")

    prompt = f"""你是 B 领域的资深研究者。请判断以下 idea 是否违反了 B 领域的社区共识和常见误区。

【B 领域常识 & 社区共识】
{knowledge}

【待检查的 idea】
{idea_text}

【检查任务】
请逐条对照【常见错误直觉（避坑）】部分，判断这个 idea 是否撞了任何一条错误直觉。

重要：你不是在鼓励创新，你是在把关——即使 idea 看起来新颖，如果它违反了社区已经验证过的错误直觉，也要果断否决。

请严格输出:

撞了的错误直觉（如果有，列出）:
- ...

业内的人大概率会质疑的点:
- ...

是否违反了 B 领域的可行创新切入点清单？(是/否)
理由:

最终判定（只输出一个词）: 通过 / 不通过
一句话总结理由:"""

    result = call_pro(prompt, temperature=0.1, max_tokens=1500)
    if not result:
        return True, "检查调用失败，默认通过"

    # 解析最终判定
    last_part = result[-500:]
    if "不通过" in last_part.split("判定")[-1][:100]:
        reason = ""
        for line in result.split("\n")[-5:]:
            if "总结" in line or "理由" in line:
                reason = line.split(":", 1)[-1].strip()[:150] if ":" in line else line
                break
        return False, reason or "违反社区共识"
    else:
        return True, "通过共识检查"


def filter_by_consensus(validated_ideas):
    """对所有通过交叉验证的 idea 做共识检查"""
    print(f"\n{'─' * 60}")
    print(f"  Stage 2.5: 社区共识检查 ({len(validated_ideas)} 个)")
    print(f"{'─' * 60}")

    passed = []
    for item in validated_ideas:
        print(f"\n  检查: [{item.get('b_domain','')}] {item.get('source_model','')}...")
        ok, reason = consensus_check(item)
        item["consensus_check"] = {"passed": ok, "reason": reason}
        if ok:
            passed.append(item)
            print(f"    ✅ {reason}")
        else:
            print(f"    ❌ {reason}")
        time.sleep(3)

    print(f"\n  共识检查通过: {len(passed)}/{len(validated_ideas)}")
    return passed


if __name__ == "__main__":
    # 用昨天的 forge 结果做测试
    import json, glob
    files = sorted(glob.glob("data/idea_forge/forge_2026*.json"))
    if files:
        with open(files[-1]) as f:
            data = json.load(f)
        for r in data.get("results", []):
            for p in r.get("plans", []):
                print(f"\n检查: {p.get('b_domain')} / {p.get('source_model')}")
                ok, reason = consensus_check(p)
                print(f"  结果: {'✅' if ok else '❌'} {reason}")
