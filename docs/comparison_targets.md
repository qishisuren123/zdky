# AutoResearch V3 对比对象与低资源评测设计

本文档记录最适合与 AutoResearch V3 对比的 5 个对象，以及每个对象已有公开资料中暴露出的可利用 failure case。目标不是全量 benchmark，而是围绕 AutoResearch 当前主打的两个卖点做快速、可解释、一次成功率高的对比：

1. **Idea 生成质量**：同一命题下生成 10 个研究 idea，比较 insight、novelty、可实验性、风险意识和筛选后命中率。
2. **无幻觉执行/验证**：在低资源任务上验证系统是否会把失败、不充分证据或未执行结果误标为成功。

推荐统一命题：

> **在纯文本推理设置下，用有限资源提升小模型推理能力。**
>
> 约束：不使用大规模 GPU 训练；允许 prompt/program search、少量 LoRA、数据选择、推理时策略、验证集重排、小型 benchmark；必须报告失败、不显著提升和资源成本。

这个命题比多模态/GPU-heavy 任务更适合第一轮对比：成本低、失败可观察、容易发现 hallucinated success，也更贴合“帮科学家筛掉不值得做的 idea”的叙事。

---

## 1. Sakana AI Scientist / AI Scientist v2

**为什么选它**：它是端到端自动科研最知名的标杆之一，覆盖 idea、代码、实验、论文和自动评审；作为“full AI scientist”代表非常有说服力。  
**已知 failure case**：独立评估报告指出 The AI Scientist 有约 **42% experiment failure rate**，并出现 **hallucinated numerical results**；Sakana 自己关于 peer-reviewed paper 的公告也承认 3 篇里只有 1 篇过 workshop 阈值、未达到其内部 ICLR 主会标准且存在 citation errors。

**适合怎么打擂台**：让它在同一低资源文本推理命题下生成 idea 并尝试执行，重点看它是否把代码跑通/指标波动误写成科学成功。  
**我们要抓的点**：AutoResearch 先生成大量候选，再交叉筛出 10 个；执行验证阶段如果提升不显著，应明确标失败或“证据不足”，而不是写成 paper-style success。

Sources: [Sakana AI Scientist](https://sakana.ai/ai-scientist/), [Evaluating Sakana's AI Scientist](https://arxiv.org/abs/2502.14297), [Sakana first peer-reviewed publication note](https://sakana.ai/ai-scientist-first-publication/)

---

## 2. Agent Laboratory

**为什么选它**：它是开源多 agent 科研助手代表，覆盖 literature review、experimentation、report writing，和 AutoResearch 的“idea + 验证 + 报告”叙事最接近。  
**已知 failure case**：原论文 limitations 和后续评估都提到 hallucinated experimental results；有例子显示它会在论文中写出实际没有发生的实验设置/结果，甚至生成完整 manuscript 但结果不匹配真实代码或输出。

**适合怎么打擂台**：让它在低资源文本推理任务上产出 10 个 idea，并选其中一个执行小实验。  
**我们要抓的点**：检查它是否把“生成了 plausible report”当成“实验成功”；AutoResearch 的强项应该是把 weak/unsupported idea 提前筛掉，并在执行结果不足时不包装成功。

Sources: [Agent Laboratory paper](https://arxiv.org/abs/2501.04227), [ACL Anthology](https://aclanthology.org/2025.findings-emnlp.320/), [Can AI Conduct Autonomous Scientific Research?](https://www.biorxiv.org/content/10.64898/2026.01.05.697809v1.full)

---

## 3. Microsoft RD-Agent / Gome

**为什么选它**：微软背书、工程化程度高，适合代表“有真实实验 loop 的 AI R&D agent”；尤其在 Kaggle/MLE-Bench 风格任务上有硬指标。  
**已知 failure case**：Gome / RD-Agent 相关论文在 `stanford-covid-vaccine` 任务上报告过 failure mode distribution，其中 **Gradient Hallucination 35/90 iterations (38.9%)**，即 reasoning module 给出自信但错误的改进方向。

**适合怎么打擂台**：把“有限资源提升小模型文本推理能力”转成一个小型 MLE 任务：固定小模型、固定验证集、固定预算，要求提出并执行改进。  
**我们要抓的点**：RD-Agent 强在实验优化，但可能在诊断/改进方向上 hallucinate；AutoResearch 可以强调“idea due diligence”在执行前先过滤方向，降低无效迭代。

Sources: [Microsoft RD-Agent](https://github.com/microsoft/RD-Agent), [Reasoning as Gradient](https://aclanthology.org/2026.findings-acl.438/), [OpenReview PDF with failure distribution](https://openreview.net/pdf?id=TnjlvLY30w)

---

## 4. GPT Researcher / STORM（报告型 baseline）

**为什么选它们**：它们很知名，但本质是 deep research / knowledge curation / report generation，不是实验执行系统；正好可以作为“报告型 agent”对比。  
**已知 failure case**：GPT Researcher 在独立 case study 中被评价为能生成概念描述和 outline，但无法完成计算/实验验证，甚至会输出没有计算支撑的 illustrative values；STORM 的公开定位也主要是生成带引用的长文报告，而非提出并执行可验证实验。

**适合怎么打擂台**：第一阶段让它们也针对低资源文本推理任务生成 10 个 idea。  
**我们要抓的点**：它们往往会产出“综述/建议列表”，而 AutoResearch 应产出“带风险、baseline、验证路径、可执行计划的筛选后 idea”。它们不适合第二阶段执行对比，除非明确标为 report baseline。

Sources: [GPT Researcher](https://github.com/assafelovic/gpt-researcher), [STORM](https://github.com/stanford-oval/storm), [Can AI Conduct Autonomous Scientific Research?](https://www.biorxiv.org/content/10.64898/2026.01.05.697809v1.full)

---

## 5. AutoResearchClaw

**为什么选它**：它是名字和叙事上最像直接竞品的系统，号称 23-stage pipeline，覆盖选题、文献、实验、写作、审查、LaTeX；如果能跑通，对比价值很高。  
**已知 failure case**：其论文/alphaXiv 页面提到 ARC-Bench T10 中 Full-Auto 出现 **silent semantic collapse**：看起来有完整 manuscript 和数字日志，但所有 CV strategies 都给出 identical zero-bias outputs；另有 failure analysis 指出 11/13 invalid HITL runs 卡在 Stage 17 paper drafting，因为上游没有 usable metrics。

**适合怎么打擂台**：作为第二批或备用对比对象，不建议第一轮押宝，因为工程复杂、跑一次成本可能高。  
**我们要抓的点**：它也强调 verified reporting，但公开 case 显示“数字存在”不等于“实验回答了研究问题”；AutoResearch 应强调 semantic validation：不只是有没有数，而是数是否支持结论。

Sources: [AutoResearchClaw arXiv](https://arxiv.org/abs/2605.20025), [AutoResearchClaw GitHub](https://github.com/aiming-lab/AutoResearchClaw), [alphaXiv view](https://www.alphaxiv.org/abs/2605.20025v1), [independent run blog](https://themenonlab.blog/blog/autoresearchclaw-autonomous-research-pipeline/)

---

# 推荐第一轮实际测试组合

不要一次测所有 5 个。第一轮只测 3 类，保证一次成功：

1. **Report baseline**：GPT Researcher 或 STORM（二选一即可）  
   用于证明“报告型 agent 不是 idea due diligence”。

2. **Open autonomous research baseline**：Agent Laboratory  
   用于比较 idea 生成 + 小实验执行，重点观察 hallucinated experimental success。

3. **Execution/metric baseline**：RD-Agent 或 karpathy/autoresearch（二选一）  
   如果做低资源文本推理，优先 RD-Agent；如果想要极清晰硬指标和低复杂度，优先 karpathy/autoresearch 风格的固定预算指标 loop。

Sakana AI Scientist 和 AutoResearchClaw 留作第二轮或展示性引用：名气大，但第一轮跑通风险、成本和不可控性更高。

---

# 低资源纯文本推理命题设计

## 任务

> 给定一个小模型和一组文本推理 benchmark，设计低成本方法提升推理表现。

## 资源约束

- 不做大规模预训练。
- 不使用重型多模态模型。
- 允许：prompt/program search、少量 LoRA、数据选择、self-consistency、小规模 synthetic data、推理时 verifier、题目重写、错误类型分析。
- 固定预算：例如单机 CPU 或单张消费级 GPU，运行时间不超过 2-6 小时。

## 输出要求

每个系统必须产出：

1. 10 个 idea。
2. 每个 idea 的风险、baseline、预期验证方式。
3. 选 1-2 个 idea 实际执行或给出可执行脚本。
4. 明确结论：成功 / 失败 / 证据不足。

## 评分维度

### Idea 质量

- Insight：是否抓住文本推理能力提升的真实瓶颈。
- Novelty：是否不是普通 prompt engineering 套话。
- Experimentability：是否能在低资源下验证。
- Baseline awareness：是否知道该和什么比。
- Risk awareness：是否主动指出失败模式。

### 无幻觉执行

- 是否真的运行了实验。
- 是否引用了真实日志/指标。
- 是否把代码跑通误当成科学结论成立。
- 是否在没有显著提升时承认失败。
- 是否区分“指标波动”与“稳定提升”。

---

# AutoResearch V3 应该主打的赢法

不是说“我们一定生成最强 idea”，而是说：

> AutoResearch 先广泛生成，再经过交叉评审筛出 10 个；它的价值是替人类科学家减少无效 idea 和 AI hallucinated success 的干扰。

最终对外口径：

> **Report agents summarize. AI Scientist agents execute. AutoResearch V3 does idea due diligence before execution.**

中文：

> **报告型 agent 负责总结，AI Scientist 负责尝试执行，AutoResearch V3 负责在执行前给 idea 做尽调。**
