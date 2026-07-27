"""
B 方向库 - 各子领域的公认本质问题
关键: 每个方向现在关联一个 knowledge_base/ 下的 .md 文件
这样 LLM 不只看到问题陈述，还能看到社区共识、路线之争、常见误区

维护说明（2026-05-13）:
  - `baselines` 和 `datasets` 字段是 freshness.py 的权威最新参考，会在 Step 2.5
    时新性刷新中被读取，用来升级 idea 中过时的模型/数据。
  - **请定期更新这里的 baselines / datasets 列表**（建议每月一次或当出现新 SOTA 时）。
  - 若新模型/benchmark 尚未进入 B 库，freshness.py 会兜底走 arxiv 实时搜索。
"""

from pathlib import Path

KNOWLEDGE_BASE_DIR = Path(__file__).parent.parent.parent / "knowledge_base"


def load_knowledge(md_filename):
    """加载对应的知识 MD 文件"""
    path = KNOWLEDGE_BASE_DIR / md_filename
    if path.exists():
        return path.read_text(encoding="utf-8")
    return ""


B_LIBRARY = [
    {
        "id": "mllm_fusion",
        "domain": "多模态大模型 - 模态融合",
        "problem": "视觉信息与文本信息的深层融合机制",
        "knowledge_md": "mllm_fusion.md",
        "datasets": ["MMMU-Pro", "MEGA-Bench", "MathVista", "HallusionBench", "MMBench-V2", "BLINK"],
        "baselines": ["Qwen2.5-VL-7B/72B", "InternVL3-8B/78B", "LLaVA-OneVision-7B", "Cambrian-1-8B", "NVILA-8B", "Molmo-7B"],
    },
    {
        "id": "mllm_visual_tokens",
        "domain": "多模态大模型 - 视觉 Token 管理",
        "problem": "视觉 token 的数量、层间动态、查询相关性",
        "knowledge_md": "mllm_visual_tokens.md",
        "datasets": ["MMBench-V2", "GQA", "POPE", "OCRBench", "DocVQA", "ChartQA"],
        "baselines": ["Qwen2.5-VL", "InternVL3", "LLaVA-OneVision", "FastV-2025", "VisionZip", "PyramidDrop"],
    },
    {
        "id": "llm_reasoning",
        "domain": "LLM 推理与测试时计算",
        "problem": "如何在有限推理预算下最大化推理能力",
        "knowledge_md": "llm_reasoning.md",
        "datasets": ["MATH-500", "AIME 2024/2025", "LiveCodeBench-v6", "ARC-AGI-2", "FrontierMath", "HumanEval-V"],
        "baselines": ["DeepSeek-R1", "DeepSeek-V3.1", "Qwen3-32B", "Llama-4-Scout", "QwQ-32B", "o3-mini-style"],
    },
    {
        "id": "agent_memory",
        "domain": "LLM Agent 长期记忆",
        "problem": "Agent 在长任务中的记忆管理",
        "knowledge_md": "agent_memory.md",
        "datasets": ["LoCoMo", "LongMemEval", "RULER-128K", "InfiniteBench", "SWE-Bench-Verified"],
        "baselines": ["MemGPT-v2", "A-Mem", "Letta", "LangMem 2025", "Mem0", "RAG-2025"],
    },
]


def get_b_library():
    return B_LIBRARY


def get_b_by_id(b_id):
    for b in B_LIBRARY:
        if b["id"] == b_id:
            return b
    return None


def format_b_context(b_direction, include_full_knowledge=True):
    """
    格式化 B 方向的上下文
    include_full_knowledge=True: 包含完整的 MD 知识（长但深）
    """
    ctx = ""
    ctx += "\n领域: " + b_direction.get("domain", "")
    ctx += "\n本质问题: " + b_direction.get("problem", "")
    ctx += "\n可用数据集: " + ", ".join(b_direction.get("datasets", []))
    ctx += "\n基线方法: " + ", ".join(b_direction.get("baselines", []))

    if include_full_knowledge:
        md = load_knowledge(b_direction.get("knowledge_md", ""))
        if md:
            ctx += "\n\n【社区深度知识 - 必读！】\n" + md

    return ctx


if __name__ == "__main__":
    for b in get_b_library():
        md = load_knowledge(b["knowledge_md"])
        domain = b["domain"]
        knowledge_md = b.get("knowledge_md", "")
        if md:
            print(f"  知识MD: ✅ {knowledge_md} ({len(md)} 字符)")
        else:
            print(f"  知识MD: ❌ 缺失 ({knowledge_md})")
