# AFC v4 Phase4 CG/CH：候选冲突挖掘与对照式反证检索落地记录

## 与前序文档的关系

本记录接在 CB「通用 Slot Contract 反证目标检索与证据账本」和 CD/CE/CF「核心断言裁决」之后。

前序 CB 解决的是：每条 claim 要有槽位账本，知道 subject / time / metric / result 缺在哪里。  
前序 CD/CE/CF 解决的是：即使表层事实被证实，也要能说明核心断言是否仍未闭合。  
本轮 CG/CH 解决的是：当候选材料已经出现时，不再只说“未闭合”，而是尽量抽出候选中的日期、数值、状态、结果冲突，并把这些冲突写到账本。

本轮不替代 Page Role Contract、Evidence Gate、numeric grounding，也不放宽 `entry_page / generic_page / pseudo_evidence` 的消费限制。

## 分类

证据链路 / Workflow / 测试与回归

## 这次要做什么

1. 在 `evidence.py` 增加 Candidate Conflict Miner。
2. 在 `retrieval.py` 增加 Contrastive Retrieval 的查询计划字段。
3. 在 `solve.py` 把冲突画像写进 claim 诊断、证据账本和最终 reason。
4. 继续保持 gate：只有同槽、强冲突、页面可裁决时，才允许推动反证；中弱冲突只进入 diagnostics 和 reason。

## 动机是什么

前几轮已经能区分“泛页不能裁决”和“核心断言未闭合”，但用户真正关心的是：系统能不能更早识别错误点。

如果候选句里已经出现不同日期、不同数值、不同状态、不同赛果，却仍然只输出“没有证据”，那么链路对错误点的敏感度不够。本轮的动机就是把这些候选冲突显性化，让后续调试知道是“没搜到”，还是“搜到了但 gate 没让它进入反证”。

## 对项目有什么实际作用

1. 错误点识别更可读：`candidate_conflict_points` 能看到冲突槽位、claim 值、evidence 值、原句和 URL。
2. 泛页污染更可控：冲突来自泛页时只进入账本，不会绕过 gate 推标签。
3. 后续优化更有靶子：如果大量冲突卡在 `page_gate_not_ready`，下一步应修页面角色或证据页抽取；如果卡在 `conflict_strength_not_strong`，下一步应修同槽对齐和数值规范化。

## 具体场景是什么

固定锚点回归：

- `afc_0001`：港股表层开盘事实可确认，但核心“外资机构抢筹/定价分化”仍未闭合。
- `afc_0002`：继续稳定为 `1`，不被新 gate 破坏。
- `afc_0008 / afc_0010`：汇率类样本出现候选冲突诊断，但未因不同口径或页面 gate 误抬标签。
- `afc_0004 / afc_0005`：战略补跑能看到候选冲突，但仍未形成强同槽反证，说明 CG 有诊断价值，CH 执行还不能放开。

## 应该怎么使用

看结果时优先看这些字段：

- `candidate_conflict_profile`
- `conflict_type`
- `conflict_strength`
- `conflict_slot`
- `claim_value`
- `evidence_value`
- `same_slot_conflict_ready`
- `candidate_conflict_points`
- `contrastive_query_plan`
- `contrastive_search_result`
- `contrastive_stop_reason`

如果 `candidate_conflict_points` 非空但 `same_slot_conflict_ready=false`，不要把它当反证，只把它当调试入口。  
如果 `contrastive_search_result=execution_disabled`，说明本轮只生成了对照检索计划，没有扩大真实检索执行。

## 对用户意味着什么

用户现在能看到“系统为什么觉得这里可能有冲突”，而不是只看到“没拿到同一口径证据”。这让错误点定位更透明，也避免把弱冲突、泛页冲突包装成事实错误。

## 对开发者意味着什么

开发者下一步不应该盲目加题型模板，而应该按 block reason 定位：

- `page_gate_not_ready`：修 Evidence Page Contract 或详情页抽取。
- `blocked_generic_page`：不要消费，需要找到可裁决来源。
- `blocked_entry_page_requires_follow`：修 entry page 下钻。
- `conflict_strength_not_strong`：修冲突强度判断和同槽比较。
- `slot_context_not_aligned`：修 slot contract 或候选句抽取。

## 本轮实现结果

代码改动范围：

- `evidence.py`
- `retrieval.py`
- `solve.py`

没有修改：

- `solve_submit.py`
- provider
- fallback
- LLM 终判结构

主要输出文件：

- `local_dev/tmp/phase4_cgch_anchor_sample0410_output.json`
- `local_dev/tmp/phase4_cgch_anchor_sample0410_debug.json`
- `local_dev/tmp/phase4_cgch_anchor_sample0410_perf.json`
- `local_dev/tmp/phase4_cgch_strategy_0004_0005_output.json`
- `local_dev/tmp/phase4_cgch_strategy_0004_0005_debug.json`
- `local_dev/tmp/phase4_cgch_strategy_0004_0005_perf.json`

5 个锚点结果：

- `afc_0001 = 2`
- `afc_0002 = 1`
- `afc_0003 = 2`
- `afc_0008 = 2`
- `afc_0010 = 2`

补跑战略样本：

- `afc_0004 = 2`
- `afc_0005 = 2`

本轮有效提升：

- 至少 1 个样本出现 `candidate_conflict_profile`。
- 多个样本出现 `candidate_conflict_points`。
- 多个样本出现 `contrastive_query_plan`。
- `afc_0008 / afc_0010` 没有因不同口径或页面 gate 被误抬标签。
- reason 从“黑盒未拿到证据”升级为“候选冲突存在，但卡在某个 gate / 槽位 / 强度层”。

本轮未通过点：

- `retrieve` 均值为约 `56.904s`，相对 CD/CE/CF 基线 `50.577s` 略超 10% 阈值。
- 因此 CH 的真实额外执行默认关闭，只保留 `contrastive_query_plan` 诊断。开关为 `V2_ENABLE_CONTRASTIVE_RETRIEVAL=1`。
- `afc_0004 / afc_0005` 仍没有被拉成事实错误，说明目前只是识别到候选冲突，还没有稳定拿到可消费的强同槽反证。

## 当前结论

CG 是有效的：它让“候选材料里到底有没有冲突”变得可见。  
CH 只能算诊断落地：对照检索计划已经生成，但真实执行会拉高 retrieve 耗时，因此默认不开。

这轮不是最终效果增强，而是把下一步的瓶颈从“看不懂为什么没反证”推进到“知道冲突卡在 page gate、entry follow、强度判断还是同槽对齐”。

## 下一步建议

下一轮不要继续扩大 query，而应做小范围精准修复：

1. 优先审计 `page_gate_not_ready` 的候选，看是不是 evidence page 被误判。
2. 对 `blocked_entry_page_requires_follow` 做 entry follow 的内链候选质量检查。
3. 对汇率和赛果类样本，把 `medium` 冲突升级条件限定在“同日期、同指标、同来源口径”上。
4. CH 只有在 retrieve 均值回到 10% 阈值内后，再打开 `V2_ENABLE_CONTRASTIVE_RETRIEVAL=1` 做小样本试跑。
