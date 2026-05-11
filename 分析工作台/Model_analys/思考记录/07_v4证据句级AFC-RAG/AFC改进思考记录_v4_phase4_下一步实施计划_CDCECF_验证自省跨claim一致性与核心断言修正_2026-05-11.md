# AFC v4 Phase4 下一步实施计划（CD/CE/CF：验证自省、跨 claim 一致性与核心断言修正）

## 基于什么架构

继续基于现有 `受控 Search Tool + Evidence Page Contract + Page Role Contract + Evidence Consumer Gate + numeric/slot grounding + Evidence Ledger + 双通道裁决`。

本轮不新增 provider，不扩大 fallback，不让 LLM 终判直接越过 gate。上一轮 CB 已经证明：`refutation_target` 能生成，也能进入实际检索执行；多个 claim 已经出现 `raw_positive / kept / candidate / same_slot_ready`。因此下一步不再把主力放在“继续搜更多”，而是把 CB 的证据账本接入验证层、聚合层和 claim 提取反馈层。

这一轮核心目标：

```text
不是让系统凭空制造反证，
而是确认已有证据是否被正确质疑、正确聚合、正确归因。
```

## 和之前文档的关系

### 和《CB：Slot Contract 反证目标检索与证据账本》的关系

CB 已经把反证目标、槽位账本、confirmed/unresolved 账本接起来。但 CB 验证显示：很多 case 已经 `same_slot_ready=true`，却没有 `slot_conflict / refuted_points`。这说明系统已经从“找不到材料”推进到“材料是否构成冲突还不会判断”。

CD/CE/CF 不替代 CB，而是消费 CB 的输出：

- `slot_contract_state`
- `same_slot_ready`
- `refute_slot_ready`
- `confirmed_points`
- `unresolved_points`
- `gate_blocked_pages`
- `refutation_target`
- `refutation_search_result`

这些字段将进入 verifier、自省检查和聚合一致性判断。

### 和《AFC_v4_战略分析_瓶颈根因与方向》的关系

战略文档指出当前主瓶颈不是单纯 retrieval，而是：

- claim 提取抓表面事实，漏核心断言；
- evidence 结构化有时没转成 refuting point；
- LLM 单次验证容易关键词匹配；
- 跨 claim 一致性缺失；
- 聚合层只认强反证，忽略弱但同槽的反证或结构化矛盾。

CD/CE/CF 是对这份战略文档的短期落地版本。它不一次性引入完整多 agent 辩论，而是先做三个低成本高收益动作：

- CD：验证器自省；
- CE：跨 claim 一致性；
- CF：核心断言修正。

### 和 Phase3 Evidence Page Contract 的关系

Phase3 的原则仍然保留：相关页不等于证据页。CD/CE/CF 不放松页面 gate，只在 gate 后判断“证据是否被验证器误读”以及“多个 claim 的证据状态是否互相矛盾”。

## 实现了什么

当前已经实现：

- Page Role Contract 阻断泛页、入口页、伪证据直接消费。
- numeric decision slots grounding 能避免日期数字冒充 claim value。
- CB 已经生成通用 slot contract 和 evidence ledger。
- 固定 5 锚点中，`afc_0008 / afc_0010` 没有误抬标签，`afc_0002` 保持为 `1`。
- 最新 CB 验证中，多数 claim 已经能看到 `refutation_target=ready` 和 `refutation_search_result=raw_positive`。

当前 CB 结果说明：链路可见性已经足够进入下一层判断，不应继续盲目加检索入口。

## 解决什么问题

本轮要解决三个问题。

### CD：验证器自省

当前 verifier 可能只做单次判断，看到关键词相似就 supported，看到证据不足就 uncertain，但不会主动问：

- 证据里有没有和初判矛盾的信息？
- 这个 evidence 是确认外围事实，还是确认核心断言？
- `same_slot_ready=true` 的候选到底是支持、反驳，还是只说明同一话题？
- confirmed point 是否与 claim 的核心 answer role 对齐？

CD 要让 verifier 在最终 verdict 前输出自省结果，而不是只给结论。

### CE：跨 claim 一致性

当前 claim 是逐条处理的，聚合层容易忽略同一回答内部的矛盾。例如一个 claim confirmed，另一个同主题 claim refuted 或 unresolved，最终 reason 不一定能反映这种结构。

CE 要让聚合层看 claim 账本：

- core claim 是否只是外围事实 confirmed；
- supporting claim 是否实际承载了核心错误；
- 多个同主题 claim 是否出现冲突；
- 结构化细节错误是否足以构成次需错误。

### CF：核心断言修正

`afc_0001` 这类问题的关键不是没搜到“港股涨约 2%”，而是系统把这个外围事实当成主核查点，漏掉“倒挂/溢价/抢筹解释是否成立”这类核心断言。

CF 要在 claim 提取或提取后审计中识别：

- peripheral fact 被误标为 core；
- 真正 answer conclusion 被标成 supporting；
- confirmed point 只确认外围事实，无法确认 answer 的主结论。

## 还卡在哪

当前最大卡点不是“没有任何网页”，而是三类断点：

- `same_slot_ready=true, conflict=false`：材料在同槽，但可能只是支持/确认，没有被识别为反证；
- `confirmed_points` 存在，但确认的是外围事实，不是主结论；
- `unresolved_points` 与核心断言相关，但聚合层没有因此提高审计优先级。

这说明下一步不应简单继续扩 query，而应审计证据账本和 claim role 是否一致。

## 现有方案还能不能继续解

能继续解，而且应先在现有方案内解。

原因：

- CB 已经提供了 `slot_contract / evidence_ledger / refutation_target`；
- solve.py 已经有 aggregation、calibration、semantic audit、rubric fallback 的接点；
- verification prompt 已经能接收 evidence summary；
- claim 提取 prompt 已经包含 `answer_role_impact / decision_slots / direct_evidence_need`，可以继续收紧核心断言要求。

因此本轮不需要先外部检索，也不需要重写大框架。

## 如果不能，再去外部检索

如果 CD/CE/CF 后仍然出现：

- verifier 自省发现矛盾但聚合仍不消费；
- cross-claim consistency 能发现冲突但无法稳定映射到 `0/1/2`；
- core claim 修正后仍稳定抓不到核心断言；
- 证据账本已有 refuted 或 conflict，但 label 仍被旧逻辑压回 `2`；

再去外部检索对标更完整的 adversarial verification / claim graph / abstention calibration。

本轮暂不再外部检索。

## 下一轮实现计划

### CD：Verifier 自省接线

主改 `solve.py`。

在 `SYSTEM_VERIFY` 或 verify prompt 的输入输出中增加结构化字段：

- `initial_verdict`
- `counter_evidence_check`
- `contradiction_found`
- `verifier_confidence`
- `abstain_reason`
- `evidence_ledger_used`

行为要求：

- verifier 必须优先读取 `evidence_ledger`，不能只看原始 evidence 文本；
- 如果 `same_slot_ready=true` 但没有 conflict，要说明它是 support、neutral 还是 still insufficient；
- 如果 claim 被 supported，但同组 claim 有 refuted/unresolved，必须标记 `needs_consistency_review=true`；
- `confidence < 0.7` 时不允许生成强 verdict，只能 uncertain 或交给聚合层保守处理。

新增 debug：

- `verifier_self_check`
- `verifier_counter_evidence_check`
- `verifier_confidence`
- `verifier_abstain_reason`

### CE：Cross-Claim Consistency Checker

主改 `solve.py` 聚合前后。

新增 claim 级一致性检查：

- 按 `claim_family / evidence_mode / subject / time_scope / answer_role_impact` 分组；
- 统计每组内 confirmed/refuted/unresolved；
- 如果 supporting claim 承载核心事实错误，不能被 core 外围事实 confirmed 覆盖；
- 如果同一组内有 refuted 或 high-risk unresolved，要输出一致性风险。

新增字段：

- `cross_claim_consistency`
- `claim_group_id`
- `claim_role_mismatch`
- `surface_fact_confirmed_but_core_unresolved`
- `same_topic_refute_count`
- `same_topic_unresolved_high_risk_count`
- `consistency_label_pressure`

聚合规则：

- core confirmed 但只是外围事实，且核心断言 unresolved，不允许把 reason 写成“关键 claim 已支持”；
- supporting refuted 若 `answer_role_impact=core` 或 `centrality` 被判断为 role mismatch，应提升为主链审计对象；
- 多个同主题 supporting refuted 可稳定支持 `LABEL_1`，但不能无证据升到 `LABEL_0`。

### CF：核心断言修正

主改 claim finalize / prompt 后处理，仍在 `solve.py`。

新增 claim role audit：

- `core_assertion_audit`
- `surface_fact_risk`
- `missed_core_assertion_hint`
- `claim_role_rewrite_suggestion`

规则：

- 如果 core claim 只包含数字/日期/背景事实，但 answer 里还有解释性主结论，则把解释性主结论提升为 core 或至少 high-risk supporting；
- 如果 confirmed point 只覆盖外围事实，而未覆盖 answer 的主结论，则 reason 必须说“外围事实已确认，核心判断未闭合”；
- 不按样本硬编码“港股倒挂”，而是通用识别：`说明/意味着/代表/因此/主要因为/反映/表明` 后面的事实性解释若影响主结论，不能被当作纯背景。

新增 debug：

- `core_assertion_audit`
- `claim_role_before_after`
- `surface_fact_confirmed_core_unresolved`
- `claim_role_fix_reason`

## 验收计划

固定锚点：

- `afc_0001`
- `afc_0002`
- `afc_0003`
- `afc_0008`
- `afc_0010`

建议补充战略文档点名样本：

- `afc_0004`
- `afc_0005`

固定运行：

```powershell
python solve.py --input local_dev/tmp/phase4_bmbnbo_anchor_input_sample0410.json --output local_dev/tmp/phase4_cdcecf_anchor_sample0410_output.json --debug-output local_dev/tmp/phase4_cdcecf_anchor_sample0410_debug.json --perf-output local_dev/tmp/phase4_cdcecf_anchor_sample0410_perf.json --workers 4 --no-resume
```

检查项：

- `evidence_ledger`
- `verifier_self_check`
- `cross_claim_consistency`
- `core_assertion_audit`
- `surface_fact_confirmed_but_core_unresolved`
- `claim_role_mismatch`
- `verifier_confidence`
- `_decision_basis`
- `_decision_policy`
- final reason

验收标准：

- `afc_0002` 继续稳定为 `1`。
- `afc_0008 / afc_0010` 不因 confirmed peripheral point 误抬标签。
- `afc_0001` 的 reason 必须明确区分“港股涨幅外围事实已确认”和“倒挂/溢价/抢筹核心判断未闭合”。
- 至少 1 个样本出现 `cross_claim_consistency` 非空并被 reason 或聚合 debug 消费。
- 如果 `afc_0004 / afc_0005` 参与验证，已存在的结构化 refuting evidence 不允许被 LLM supported 直接覆盖。
- retrieve 平均耗时不应因本轮明显上升；本轮主要增加 verify/aggregation 成本，不增加检索成本。

## 项目动机记录

### 分类

证据链 / Workflow / 测试与回归

### 这次要做什么

把 AFC v4 从“检索更多证据”转向“更会验证和聚合证据”。本轮不追求新增更多网页入口，而是让 verifier、聚合层和 claim role 审计真正消费 CB 已经产出的证据账本。

### 动机是什么

CB 结果说明，系统已经能搜到同槽或近同槽材料，但没有稳定形成反证。继续堆检索容易增加时延，却不一定解决“外围事实被确认、核心断言仍未闭合”的问题。战略文档也指出，当前瓶颈在验证层、跨 claim 一致性和核心断言提取。

### 对我们的项目有什么实际作用

这会减少两类错误：一类是证据已经有冲突但被 LLM 或聚合层忽略；另一类是系统确认了外围事实，却误以为回答核心结论已被支持。对 AFC 来说，这比继续增加搜索源更接近实际准确率提升。

### 具体场景又是什么

例如回答里说“港股涨约 2%，说明港股相对 A 股倒挂并代表外资抢筹”。系统即使确认了“涨约 2%”，也不能说核心判断被确认。它必须继续标记“倒挂/抢筹解释未闭合”，并在 reason 里讲清楚。

### 我应该怎么去使用

后续看结果时，不只看 `raw/kept/candidate`，还要看：

- verifier 是否读了 evidence ledger；
- cross-claim consistency 是否发现角色错位；
- core assertion audit 是否识别外围事实和核心断言；
- final reason 是否把“已确认”和“未闭合”分开。

### 对用户意味着什么

用户会看到更像真实事实核查的解释：系统不再把“某个外围事实是真的”误说成“整个回答没有问题”，也不会在证据不足时假装已经反证。

### 对开发者意味着什么

开发者可以按验证层问题排查，而不是继续无方向地改 query。失败可以被分到 verifier、自省、一致性、claim role 或 aggregation，而不是都回到 retrieval。

### 当前结论

现有方案还能继续解，但下一步主战场应从 retrieval 转到 verification 和 aggregation。CD/CE/CF 是战略文档建议的低成本落地版。

### 下一步建议

先实现 CE 的 cross-claim consistency 和 CF 的 core assertion audit，因为它们主要是代码逻辑和 debug，不需要增加 LLM 调用；再谨慎改 CD 的 verifier prompt，避免成本和不稳定性一次性上升。
## 2026-05-11 CD/CE/CF 首轮实施状态同步

### 分类

证据链 / Workflow / 测试与回归

### 这次要做什么

本轮把 `evidence_ledger` 继续往后接到 verifier、聚合层和最终 reason：新增 `core_assertion_audit` 识别表层事实与核心断言错位，新增 `cross_claim_consistency` 汇总跨 claim 的同题未闭合状态，并让 verifier 输出 `counter_evidence_check / needs_consistency_review / evidence_ledger_used` 等自省字段。

### 动机是什么

前一轮 CB 证明系统已经不总是“搜不到”：很多样本有 raw、kept、candidate，甚至有 confirmed surface point，但仍没有变成真正可裁决的错误点。继续扩大检索会增加成本，却不能解决“确认了边角事实，但核心解释还没闭合”的问题。因此这一轮转向验证层和聚合层。

### 对项目有什么实际作用

它让错误分析更可读：系统现在能说明“哪些事实已确认、哪些核心断言仍没闭合、为什么不能把未闭合当成反证”。这比单纯输出 `2` 更有用，也能避免把 supporting/peripheral 的支持误当成整个回答正确。

### 具体场景是什么

在 `afc_0001` 中，系统确认了“2026-04-01 港股开盘上涨约 2%”这类表层事实，但同时标出“港股比 A 股贵且涨得更多，主要被解释为外资和机构资金抢筹优质核心资产”仍未闭合。最终 reason 不再像黑盒 recall，而是明确区分表层命中和核心未闭合。

### 我应该怎么使用

后续看调试结果时，优先检查：`core_assertion_audit.state`、`cross_claim_consistency.state`、`surface_fact_confirmed_but_core_unresolved`、`verify.claim_verdicts[].counter_evidence_check`、`verify._final_reason_source`。如果 `_final_reason_source=cross_claim_consistency_reason`，说明本轮中层判断已经真正参与最终解释。

### 对用户意味着什么

用户会看到更诚实的事实核查解释：不是“没证据所以放过”，也不是“有一个相关事实为真所以全对”，而是说明核心断言是否真的被证据覆盖。

### 对开发者意味着什么

开发者可以把失败点从“检索差”进一步拆开：是核心断言没抽出来、表层事实遮蔽了核心、跨 claim 没聚合，还是确实没有同槽证据。下一轮调优会更有靶心。

### 当前结论

首轮实施有效接通了 CD/CE/CF 的诊断和 reason 链路。5 个锚点中 `afc_0001` 和 `afc_0003` 出现 `cross_claim_consistency=needs_review`，`afc_0001` 的最终 reason 已能区分表层事实确认与核心断言未闭合；`afc_0002` 保持为 `1`，`afc_0008 / afc_0010` 未误抬标签。

### 下一步建议

下一步不要继续泛化检索模板，应优先扩大 CD/CE/CF 的样本回归到 `afc_0004 / afc_0005`，确认“已有结构化反证但被 verifier 覆盖”的场景能否被同一套自省和一致性机制拦住。
