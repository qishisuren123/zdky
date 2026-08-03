# 失败场景复现调研：哪些 AutoResearch 批评案例值得复现

目标：不是复现所有 AutoResearch 项目，而是找到**最低成本、最高成功率、最能支撑 AutoResearch V3 两个卖点**的失败场景：

1. **Idea 生成质量**：我们先大量生成，再通过交叉评审筛出 10 个更像真实科学家会考虑的 idea。
2. **无幻觉执行/验证**：系统必须区分“代码跑通 / 有数字”与“科学结论真的成立”，不能把失败包装成成功。

推荐统一命题：

> **在纯文本推理设置下，用有限资源提升小模型推理能力。**
>
> 约束：不做大规模预训练，不做多模态，不依赖大 GPU；允许 prompt/program search、少量 LoRA、数据选择、自一致性、推理时 verifier、小规模 synthetic data；必须报告失败、不显著提升和资源成本。

---

## 总结结论

最适合第一轮复现的不是名气最大的 Sakana，也不是最复杂的 AutoResearchClaw，而是：

1. **GPT Researcher / STORM**：作为报告型 baseline，低成本，用来证明 report agent 不等于 idea due diligence。
2. **Agent Laboratory**：有公开代码和明确 hallucinated-result 失败案例，适合做“科研助手会把报告写得像成功”的对比。
3. **RD-Agent / Gome traces**：有公开 raw traces，尤其适合复现“诊断方向 hallucination”，不一定要完整重跑 GPU 任务。
4. **DeepHalluBench**：不是 AutoResearch 项目本身，但有开源评测框架，适合拿来评估 deep research trajectory 中的 hallucination。

Sakana AI Scientist 和 AutoResearchClaw 名气大，但第一轮复现难度高，建议先作为引用和第二轮对象。

---

## 1. Sakana AI Scientist 独立评估

**他们怎么测**：独立评估围绕 The AI Scientist 的完整研究流程：文献综述、实验执行、代码修改、论文生成。公开摘要/页面中提到的主要结果包括：约 **42% experiments failed due to coding errors**，存在 novelty assessment 问题、弱/误导性结果、论文结构错误、placeholder、缺图，以及 **hallucinated numerical results**。

**有没有代码/日志/轨迹**：Sakana 官方 repo 有 AI Scientist v1/v2 代码、templates、setup、baseline run 指令和示例论文；但独立评估本身没有明显提供“失败案例一键复现包/完整 traces/logs”。Sakana v1 repo 提到有所有 runs/data 的 Drive，但独立评估中的具体失败 case 不是整理好的 benchmark。

**复现难度**：中高。需要 GPU、API key、沙箱、论文生成依赖；workflow 随机性和模型版本会影响是否复现同样失败。

**我们怎么用**：不建议第一轮完整复现 Sakana；更适合引用其独立评估作为“AI Scientist 执行会幻觉/失败”的背景证据。若一定要跑，选择最轻的 NanoGPT/text8/enwiki8 template，只观察是否会把 failed/weak experiment 写成成功。

Sources: [Evaluating Sakana's AI Scientist](https://arxiv.org/abs/2502.14297), [SakanaAI/AI-Scientist](https://github.com/SakanaAI/AI-Scientist), [SakanaAI/AI-Scientist-v2](https://github.com/sakanaai/ai-scientist-v2), [Nature AI Scientist article](https://www.nature.com/articles/s41586-026-10265-5)

---

## 2. Agent Laboratory / AgentRxiv 失败案例

**他们怎么测**：Agent Laboratory 本身按 Literature Review → Experimentation → Report Writing 工作流运行；AgentRxiv/MATH-500 设置里有公开 config，要求评估 HuggingFaceH4/MATH-500 的 500 道测试题。公开材料指出，Agent Laboratory 可能生成与真实实验/代码不一致的报告，有时 code repair 删除或替换核心功能，却仍输出看起来合理的结果。

**具体 failure case**：原论文 limitations 提到某些模型生成的 paper 包含未发生的实验细节；后续 AgentRxiv 材料提到 MATH-500 相关任务中，部分 Agent Laboratory papers 报告的结果不匹配实际实验或代码。另一个独立 bioRxiv case study 指出 Agent Laboratory 会生成完整 manuscript 和 fabricated results。

**有没有代码/日志/轨迹**：Agent Laboratory GitHub 有代码、安装步骤、实验 configs，包括 MATH 相关 config；但页面没显示完整公开 trajectories/logs。它会本地保存 `state_saves`，因此我们自己跑可以留下过程证据。

**复现难度**：中等。比 Sakana 更现实：开源、可配置、可选模型；但完整跑 MATH-500 成本不低。可以把 MATH-500 改成 20-50 题小子集，专门测“报告是否忠实于真实输出”。

**我们怎么用**：第一轮推荐测。设置为低资源文本推理任务，要求它生成 10 个 idea，并选 1 个在 MATH-500 小子集或 GSM8K/BBH 小子集上执行；最终核对 report 里的数字是否来自真实 logs。

Sources: [Agent Laboratory](https://github.com/SamuelSchmidgall/AgentLaboratory), [Agent Laboratory paper](https://arxiv.org/abs/2501.04227), [ACL Anthology](https://aclanthology.org/2025.findings-emnlp.320/), [AgentRxiv](https://arxiv.org/abs/2503.18102), [AgentRxiv project](https://agentrxiv.github.io/), [MATH AgentRxiv config](https://github.com/SamuelSchmidgall/AgentLaboratory/blob/main/experiment_configs/MATH_agentrxiv.yaml)

---

## 3. GPT Researcher / STORM 报告型 baseline

**他们怎么测**：独立 bioRxiv case study 用两个真实科学复现/扩展任务测试了八个开源 AI research frameworks，包括 GPT Researcher、Agent Laboratory 等。结论是这些系统擅长 planning/summarization，但没有完成完整科学研究闭环；GPT Researcher 具体被指出生成概念描述和 outline，但没能完成计算/指标验证，可能输出没有计算支撑的 illustrative values。

**有没有代码/日志/轨迹**：GPT Researcher 和 STORM 都有成熟开源 repo，容易运行；但它们本来不是实验执行系统，因此“复现失败”主要是证明它们不适合执行验证，而不是证明代码坏。bioRxiv 文章没有明显给出一键复现脚本/全量轨迹包。

**复现难度**：低。只要给同一个命题，让它们输出 10 个 idea 或 research report，再人工/LLM rubric 判断输出是否停留在综述层。

**我们怎么用**：第一轮强烈推荐作为报告型 baseline。它们能证明：report agent 可以把背景讲清楚，但不一定能给科学家筛出 experiment-ready ideas。

Sources: [GPT Researcher](https://github.com/assafelovic/gpt-researcher), [STORM](https://github.com/stanford-oval/storm), [Can AI Conduct Autonomous Scientific Research?](https://www.biorxiv.org/content/10.64898/2026.01.05.697809v1.full)

---

## 4. Microsoft RD-Agent / Gome traces

**他们怎么测**：Gome/RD-Agent 用 MLE-Bench/Kaggle-style 任务，在 12h single-V100 closed-world protocol 下做多轮 ML engineering。公开 failure analysis 中，`stanford-covid-vaccine` 任务的 90 iterations 里有 **Gradient Hallucination 35/90 (38.9%)**：reasoning module 给出自信但错误的改进方向。

**有没有代码/日志/轨迹**：有。Microsoft RD-Agent GitHub 公开代码；Gome GPT-5 traces 在 HuggingFace 发布，约 545 MB，包含 40 个 Kaggle competitions 的 raw parallel-trace execution logs，记录 hypothesis → code → execution → feedback 过程。但它不包含 final multi-seed selection step，因此适合分析失败过程，不适合完整复现最终 leaderboard 结果。

**复现难度**：两种路线不同。完整重跑 RD-Agent/Gome：高成本，需要 Kaggle/MLE-Bench 环境和较长 GPU 预算；只分析公开 traces 复现“gradient hallucination”类型：低到中等，适合第一轮。

**我们怎么用**：第一轮建议不完整重跑，而是下载/抽样 traces，展示“即使有真实实验 loop，agent 的诊断方向也会 hallucinate”。然后让 AutoResearch 在同类低资源文本推理任务上先做 idea due diligence，比较是否能提前识别高风险方向。

Sources: [Microsoft RD-Agent](https://github.com/microsoft/RD-Agent), [Reasoning as Gradient](https://arxiv.org/abs/2603.01692), [Microsoft Research page](https://www.microsoft.com/en-us/research/publication/reasoning-as-gradient-scaling-mle-agents-beyond-tree-search/), [Gome GPT-5 Traces](https://huggingface.co/datasets/amstrongzyf/Gome-GPT5-Traces), [OpenReview PDF](https://openreview.net/pdf?id=TnjlvLY30w)

---

## 5. AutoResearchClaw / ARC-Bench

**他们怎么测**：AutoResearchClaw 用 ARC-Bench 做 autonomous-research benchmark。ARC-Bench 数据集公开在 HuggingFace，包含 55 topics，覆盖 ML、HEP、quantum、systems biology、statistics；每个 topic 有 manifests/rubrics。其论文/alphaXiv 页面报告过 failure cases，例如 ARC-Bench T10 的 Full-Auto 出现 **silent semantic collapse**：有数字和 manuscript，但 CV strategies 结果语义上塌缩；另有 11/13 invalid HITL runs 卡在 Stage 17 paper drafting，因为上游没有 usable metrics。

**有没有代码/日志/轨迹**：代码和 benchmark harness 在 GitHub；ARC-Bench 数据集有 manifests/rubrics；但公开页面未显示完整失败 run 的 logs/traces 一键包。要复现失败，需要 repo、配置、API key、topic manifest、执行 artifacts，并可能要跑完整 23-stage pipeline。

**复现难度**：中高。比 Sakana 更贴近我们，但工程链条长、阶段多、一次运行成本和不确定性较高。

**我们怎么用**：不建议第一轮押宝完整复现。可以先引用 ARC-Bench T10 和 Stage 17 missing metrics failure，作为“有数字不等于有科学结论”的公开案例；第二轮再挑一个低资源 ML/text topic 跑。

Sources: [AutoResearchClaw arXiv](https://arxiv.org/abs/2605.20025), [AutoResearchClaw GitHub](https://github.com/aiming-lab/AutoResearchClaw), [ARC-Bench dataset](https://huggingface.co/datasets/AIMING-Lab-UNC/ARC-Bench), [alphaXiv view](https://www.alphaxiv.org/abs/2605.20025v1), [AutoResearchClaw integration guide](https://github.com/aiming-lab/AutoResearchClaw/blob/main/docs/integration-guide.md)

---

## 6. DeepHalluBench（不是竞品，但值得用作评测器）

**它怎么测**：DeepHalluBench 是 deep research agent hallucination evaluation toolkit，用 PING taxonomy 评估 full research trajectory：Propagation、Intent、Noise-induced、Grounding hallucinations。它需要输入 research query、final report、source links、cited links、reasoning steps、search results 等轨迹数据。

**有没有代码/数据/轨迹**：有 GitHub repo、100-task benchmark JSONL、demo trajectory JSON、CLI/API evaluator、parsers 和 checkers。但它不直接提供某个 AutoResearch agent 的完整 runner；我们需要自己把 AutoResearch/GPT Researcher/STORM 等输出转换成它要求的 trajectory 格式。

**复现难度**：中等。作为“评测器”很有用；作为“复现某个竞品失败”不够直接。

**我们怎么用**：可作为第二层证据：把我们和 baseline 的 final report/trajectory 输入 DeepHalluBench，看谁更容易出现 unsupported claims、fabrication、misattribution、constraint neglect。

Sources: [DeepHalluBench paper](https://arxiv.org/abs/2601.22984), [DeepHalluBench GitHub](https://github.com/yuhao-zhan/DeepHalluBench), [DeepHalluBench data](https://github.com/yuhao-zhan/DeepHalluBench/blob/main/data/DeepHalluBench.jsonl)

---

# 复现优先级

## 第一优先级：最容易、最能出图

1. **GPT Researcher/STORM report baseline**  
   - 好做：低成本、容易跑、输出稳定。
   - 价值：证明 report ≠ idea due diligence。

2. **Agent Laboratory 小子集执行**  
   - 好做程度：中等。
   - 价值：最贴近“生成 manuscript 但结果可能不忠实”的失败点。

3. **RD-Agent/Gome public traces 分析**  
   - 好做程度：中等偏低成本，不必完整重跑。
   - 价值：有公开 raw traces，可以直接展示 gradient hallucination。

## 第二优先级：名气大，但跑通风险高

4. **Sakana AI Scientist**  
   - 名气最大，但复现具体失败不稳定，成本较高。

5. **AutoResearchClaw**  
   - 直接竞品感强，但 23-stage pipeline 和 ARC-Bench 完整复现成本高。

## 辅助评测

6. **DeepHalluBench**  
   - 不是竞品，但适合做 hallucination evaluator。

---

# 推荐我们自己的最小复现实验

## 命题

> 在纯文本推理设置下，用有限资源提升小模型推理能力。

## 数据/任务建议

- MATH-500 小子集：20-50 题。
- GSM8K 小子集：50-100 题。
- BBH / StrategyQA 小子集：20-50 题。
- 固定小模型：一个开源 7B/14B 或通过统一 API 调同一个小模型。

## 对比流程

1. 每个系统产出 10 个 idea。
2. 评审团按 insight、novelty、experimentability、baseline awareness、risk awareness 打分。
3. 每个系统选择 1 个 idea 执行或给可执行脚本。
4. 我们只承认有真实日志/指标支撑的结论。
5. 如果没有显著提升，必须标为“失败/证据不足”。

## 我们最想复现的失败类型

- **Report hallucination**：报告里有漂亮结论，但没有真实计算。
- **Metric hallucination**：写出数字，但数字不是脚本真实输出。
- **Semantic collapse**：有数字，但实验没有回答原问题。
- **Diagnostic hallucination**：agent 自信提出错误改进方向。
- **Success overclaim**：微小波动/不显著提升被写成成功。

---

# 战略判断

复现失败场景本身必须纳入对比设计，否则容易出现“我们也只是自己说别人会幻觉”的问题。最稳路线不是完整重跑每个系统，而是：

1. 用 GPT Researcher/STORM 做报告型 baseline；
2. 用 Agent Laboratory 跑一个小型执行任务；
3. 用 RD-Agent/Gome 公开 traces 做 failure replay；
4. 用 DeepHalluBench 或自定义 rubric 检查 hallucination；
5. 把 Sakana/AutoResearchClaw 放在第二轮或作为公开文献证据。

这样成本最低，也最贴合 AutoResearch V3 的主张：

> **我们不是保证每个 idea 成功，而是帮科学家更早识别哪些 idea 不值得继续相信。**
