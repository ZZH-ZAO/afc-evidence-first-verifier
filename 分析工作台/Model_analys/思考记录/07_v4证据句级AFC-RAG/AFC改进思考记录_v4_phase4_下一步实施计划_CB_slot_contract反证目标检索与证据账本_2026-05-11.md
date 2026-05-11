# AFC v4 Phase4 下一步实施计划（CB：Slot Contract 反证目标检索与证据账本）

## 基于什么架构

继续基于现有 `受控 Search Tool + Playwright 受控救援 + authority-first + Evidence Page Contract + Page Role Contract + Evidence Consumer Gate + numeric decision_slots grounding + 双通道裁决`。

本轮不扩 provider，不放松 gate，不让 fallback 绕过证据门控，也不引入 LLM 终判。外部资料给出的共识不是“多搜一点就好”，而是：

- 检索要能返回可追踪来源、受控域和完整 sources。
- fact-checking retrieval 要能区分 support / refute / misleading / unrelated。
- 数值、时间、事件类事实不能只看相关文本，要做同槽位对齐。
- reason 需要把搜索、证据、门控、裁决链路完整展示出来。

所以本轮的核心不是继续堆题型模板，而是把 claim 统一拆成可比较的事实槽位，然后围绕“同一主体、同一时间、同一指标/关系下的冲突值或冲突状态”去找反证。

## 和之前文档的关系

### 和《入口层审计与外部检索架构对标》的关系

《入口层审计与外部检索架构对标》解决的是入口层方向：Search Tool 要受控、source 要有健康度、救援要有预算，失败不能黑盒落回 recall。

CB 文档承接它，但不继续停在入口层。入口层现在已经能解释一部分 raw/kept/blocked 问题，下一步要把“搜到了什么”推进到“这个结果是否能打到错误点”。也就是从 source 执行协议进入 evidence/usefulness 协议。

### 和《BX/BY/BZ：搜到真正可裁决证据》的关系

BX/BY/BZ 已经把页面分成 `evidence_page / entry_page / generic_page / blocked_page`，并且阻断泛页、入口页、讨论页直接进入裁决。

CB 不回滚这个 gate，而是在 gate 之后补“为什么 evidence_page 仍然不能形成反证”的通用判断：是否同主体、同时间、同指标、同对象、同结果。如果不同槽，不能因为看起来相关就消费；如果同槽且冲突，才允许形成 refute。

### 和《CA：numeric decision_slots 同槽 grounding》的关系

CA 证明了数值类证据不能再从 claim 文本里随便拿第一个数字，而要从 `decision_slots / core_binding / direct_evidence_need` 里确定目标值，并排除日期、时间、序号污染。

CB 是 CA 的泛化版：不只处理 numeric value，也要处理日期、赛程、路线、事件结果、状态、对象关系。换句话说，CA 是 `numeric slot grounding`，CB 是 `general slot contract grounding`。

### 和 Phase3 文档的关系

Phase3 的 `Evidence Page Contract`、`authority homepage discovery`、`官网内页命中与表格证据转换` 已经给了两个底座：

- 相关页不等于证据页。
- 入口页要受控下钻到内页、详情页、表格页。

CB 继续沿用这些结论，但避免回到“按题型不断补关键词”的旧路。下一轮只允许增加通用槽位和通用反证目标，不新增单题专用规则。

## 实现了什么

当前已经实现或验证过的状态：

- `afc_0002` 能稳定拿到足够裁决的证据或结构化闭环，标签保持 `1`。
- `afc_0008 / afc_0010` 没有再因为泛页、门户页、当前日期页被误抬标签。
- `afc_0010 / c2` 已经出现一个真实可消费的数值证据点：目标页标题和内容能命中 `4 月 1 日人民币对美元中间价 6.9025、上调 169 个基点`，并通过 numeric slot grounding。
- `entry_page / generic_page / blocked_page / pseudo_evidence` 已经不能直接推动标签。
- debug 里已经有 `page_role`、`direct_evidence_gate_result`、`numeric_slot_grounding_result`、`point_conversion.block_reason` 等关键诊断。

这说明检索和证据门控不是完全无效，问题已经从“完全拿不到”变成“能拿到一部分，但反证链和 reason 还没有稳定表达出来”。

## 解决了什么

前几轮已经解决的是真实性底线：

- 不再把官网首页、门户频道、百科、知乎话题页当作可裁决证据。
- 不再让旧 fallback 越过 gate 直接生成 `0/1`。
- 不再把日期里的数字、时间里的数字误当作 claim value。
- 检索失败、反爬失败、entry-follow 失败能留下原因。

CB 要解决的是反证命中率和 reason 可读性：

- 当 claim 错在某个具体事实点时，系统要能知道应该找“同槽冲突证据”，而不是泛搜 claim 原文。
- 当找到相关页但不能反证时，reason 要说明是哪个槽不闭合，而不是只说“未拿到同一口径证据”。
- 当某个 claim 已经被确认、另一个 claim 未解决时，reason 要显示 claim 级账本，避免看起来像推理能力没有变化。

## 还卡在哪

当前主要卡点有三层。

第一层：反证目标不够清楚。  
系统知道 claim 里有事实，但没有稳定生成“同一主体 + 同一时间 + 同一指标/关系 + 冲突值/冲突状态”的 refutation target。结果就是搜到相关材料很多，直接打到错误点的证据少。

第二层：候选证据的槽位账不清。  
候选句进入 point conversion 后，debug 能看到一些 block reason，但缺少统一的 slot ledger：这个候选命中了哪些槽、缺了哪些槽、哪些槽冲突、冲突是否足够形成 refute。

第三层：reason 没把内部进展说出来。  
例如一个样本里某个 claim 已经有 direct numeric point，但最终样本标签仍为 `2`，reason 需要说清楚“c2 已确认，c1/c3 未闭合，所以总标签保守为 2”。否则用户看到的仍像是没有推理提升。

## 现有方案还能不能继续解

能继续解，而且应该先用现有方案解。

原因是现在的失败层还能被现有架构解释：

- 如果 raw/kept 没进来，是 Search Tool、source health、Playwright rescue、budget cutoff 的问题。
- 如果 page 进来了但被 gate 挡住，是 Page Role Contract / Evidence Consumer Gate 的问题。
- 如果 evidence_page 进来了但不能形成 point，是 slot grounding 和 point conversion 的问题。
- 如果 point 形成了但 reason 没表现出来，是 evidence ledger reason 的问题。

当前症状主要落在第三、第四类，不应该马上再堆 provider 或交给 LLM 终判。下一轮要做的是 `Slot Contract Engine + Refutation Target Retrieval + Evidence Ledger Reason`。

## 如果不能，再去外部检索

本轮已经做了外部对标，结论是：外部优秀方案支持我们从“题型模板”转向“可追踪检索 + 证据类型区分 + 槽位对齐 + 证据账本”。

后续只有在以下条件出现时，再继续外部检索：

- 已经生成 slot contract，但同槽候选长期为 0。
- 已经生成 refutation target，但搜索结果仍长期只返回泛页。
- 已经有 evidence_page，但 slot ledger 无法解释为什么不能 refute。
- retrieve 耗时超过基线 10%，现有 source health / early stop 收不回来。

外部检索重点不再是“事实核查论文里有什么新模型”，而是找：

- evidence retrieval 如何生成 refuting evidence query。
- numerical / temporal claim verification 如何做 slot alignment。
- browser/search agent 如何做动态过滤和成本控制。
- reason/citation ledger 如何展示 claim-level 证据状态。

## 外部依据映射

### OpenAI Web Search

OpenAI 官方 Web Search 强调三点：模型可调用 web search 获取最新信息；Responses API 支持 domain filtering；`sources` 可以返回实际咨询过的 URL 列表。对我们的启发是：`search_execution_trace`、`allowed/blocked family`、`final_executed_source_order` 和 sources ledger 不是附属 debug，而应当成为检索合同的一部分。

参考：https://developers.openai.com/api/docs/guides/tools-web-search

### Anthropic Web Search

Anthropic 官方 Web Search 在 2026 版本中强调 dynamic filtering、`max_uses`、domain filtering、citation 和错误对象。对我们的启发是：搜索不能无限重试；失败也必须作为工具结果显式返回；动态过滤的思想可以落成我们的 `candidate_slot_coverage` 和 `generic_page_block_reason`。

参考：https://platform.claude.com/docs/en/agents-and-tools/tool-use/web-search-tool

### Google Vertex AI Grounding

Google Vertex AI Grounding 把 grounding 定义为把模型输出连接到可验证来源，并强调降低幻觉、锚定数据源和可审计 source links。对我们的启发是：最终 reason 不应该只报标签，而要展示 grounding 支撑和未闭合的槽位。

参考：https://docs.cloud.google.com/vertex-ai/generative-ai/docs/grounding/overview

### FactIR

FactIR 把 fact-checking retrieval 的难点放在“既要找支持证据，也要找反驳证据”，并指出真实开放域场景里相关信息不等于可验证证据。对我们的启发是：下一步必须明确 refutation target，不能只提高 recall。

参考：https://arxiv.org/abs/2502.06006

### RAGuard

RAGuard 关注 misleading retrieval：检索结果可能支持、误导或无关，RAG 在噪声证据下可能比不检索更差。对我们的启发是：gate 不能放松，泛页不能被 fallback 消费，否则会提升假阳性。

参考：https://arxiv.org/abs/2502.16101

### ClaimCheck / ClaimIQ

ClaimCheck 代表实时事实核查 pipeline，ClaimIQ 代表数值 claim verification 的方向。它们对我们的共同启发是：事实核查不能只靠最终分类器，必须把 claim decomposition、retrieval、evidence selection、numerical/temporal verification 分阶段展示。

参考：https://arxiv.org/abs/2510.01226  
参考：https://arxiv.org/abs/2509.11492

## 下一轮实施计划

### CB1：通用 Slot Contract Engine

主改 `evidence.py` 和必要的 `solve.py` 字段消费，不先大改 `retrieval.py`。

为每个 claim 和每个候选 point 统一生成槽位：

- `subject`
- `time_scope`
- `object`
- `metric_or_relation`
- `status_or_result`
- `comparison_baseline`
- `source_scope`

每个候选证据都要输出：

- `slot_contract_state`
- `slot_coverage`
- `slot_missing`
- `slot_mismatch`
- `slot_conflict`
- `same_slot_ready`
- `refute_slot_ready`

通过条件：

- support 必须是同槽一致。
- refute 必须是同槽冲突。
- unresolved 必须说明缺的是哪个槽。

### CB2：Refutation Target Retrieval

主改 `retrieval.py` 的 query planning / retry guidance，不新增 provider。

生成反证目标时不按题型写死，而按槽位缺口来写：

- 缺时间：增加 target date / period / historical / official notice 约束。
- 缺指标：增加 metric / relation / status 约束。
- 缺主体：增加 subject alias / official domain / source_scope 约束。
- 命中泛页：不直接丢弃，先判定能否 entry-follow；不能 follow 才降为 diagnostics。
- 找反证：固定搜索同主体、同时间、同指标下的 alternative value / actual result / official result / correction / notice。

新增 debug：

- `refutation_target`
- `refutation_query_plan`
- `refutation_retry_trigger`
- `refutation_slot_gap`
- `refutation_search_result`
- `refutation_retrieval_stop_reason`

### CB3：Evidence Ledger Reason

主改 `solve.py` reason 汇总。

最终 reason 不再只输出泛化不足原因，而要输出 claim 级账本：

- `confirmed_points`
- `refuted_points`
- `unresolved_points`
- `gate_blocked_pages`
- `slot_blocked_candidates`
- `fallback_scope`
- `final_label_reason`

样本级 reason 规则：

- 只要有同槽 refute，优先说明错误点是什么，为什么足以支持 `1`。
- 如果只有同槽 support，但其他 claim 未闭合，说明哪些点已确认、哪些点仍 unresolved。
- 如果没有同槽证据，标签可保守为 `2`，但 reason 必须落在具体槽位缺口，而不是黑盒 recall。
- fallback 只能说明保守兜底或内部逻辑闭环，不能绕过 gate 制造证据。

### CB4：时延与泛化边界

本轮不接受“为了找反证无限变慢”。

控制方式：

- 每个 core claim 最多触发 1 次 refutation retry。
- 已有同槽 refute/support 后，不继续搜同类 query。
- `generic_page` 只能贡献 diagnostics，不触发多轮深挖。
- `entry_page` 最多 follow 3 个候选内链。
- `source_latency_profile` 和 `retrieval_cost_review` 必须继续保留。

## 验收计划

固定 5 个锚点，运行时继续使用 `--workers 4`：

- `afc_0001`
- `afc_0002`
- `afc_0003`
- `afc_0008`
- `afc_0010`

重点检查：

- `slot_contract_state`
- `slot_coverage`
- `slot_mismatch`
- `slot_conflict`
- `same_slot_ready`
- `refute_slot_ready`
- `refutation_target`
- `refutation_query_plan`
- `direct_evidence_gate_result`
- `numeric_slot_grounding_result`
- `evidence_page_consumption_state`
- `confirmed_points`
- `refuted_points`
- `unresolved_points`
- `final_label_reason`
- `timing.retrieve`

验收标准：

- `afc_0002` 继续稳定为 `1`。
- `afc_0008 / afc_0010` 不允许因为泛页、入口页、当前日期页误抬标签。
- 至少 1 个 `afc_0001 / afc_0003 / afc_0008 / afc_0010` claim 出现明确 `refutation_target`。
- 至少 1 个 claim 的 reason 从“未拿到同一口径证据”升级为具体槽位账本。
- 如果有同槽冲突证据，必须进入 `refuted_points`，不能被普通 unresolved 淹没。
- 如果没有证据，最终 `2` 可以保留，但必须说明缺的是 subject/time/metric/object/status 哪个槽。
- 平均 `retrieve` 耗时不超过当前 CA 基线 10%；超过则本轮只算诊断成功，不算效果验收通过。

## 项目动机记录

### 分类

证据链 / Workflow / 测试与回归

### 这次要做什么

把下一轮方向从“继续按题型补检索规则”收束到“通用事实槽位、同槽反证目标、证据账本 reason”。目标是让系统更稳定地打到错误点，同时让没有打到的原因也能被看见。

### 动机是什么

现在的主要矛盾不是完全没有检索能力，而是检索回来的材料经常只相关、不够裁决；即使局部 claim 已有证据，最终 reason 也没有把这份进展讲清楚。继续加题型模板会变成无底洞，不能满足项目要做通用事实核查链路的目标。

### 对我们的项目有什么实际作用

它把 AFC 从“页面相关性系统”推进到“事实槽位验证系统”。后续无论是汇率、赛程、路线、事件结果还是数值指标，都先落到同一套槽位合同，而不是每来一类题就写一批专门规则。

### 具体场景又是什么

比如一个 claim 说某天某指标是某个数值。系统应先识别主体、日期、指标和值，再去找同主体同日期同指标的官方或权威证据。如果证据值不同，就形成反证；如果只找到另一天、另一个指标或泛讨论页，就只能记为槽位不闭合。

### 我应该怎么去使用

后续看 debug 时，不再只问 raw/kept 数量，而是先看 `refutation_target` 是否生成，再看候选证据的 `slot_coverage / slot_conflict`。看 reason 时，要检查是否列出 confirmed/refuted/unresolved 账本。

### 对用户意味着什么

用户会更容易看懂“系统到底识别到了哪个错误点”。如果证据不足，用户看到的也不再是笼统的 recall 失败，而是哪个事实槽位没有拿到可裁决证据。

### 对开发者意味着什么

开发者排查失败时可以按槽位定位：是没搜到同一时间、没命中同一主体、指标混了、值没抽出来，还是 gate 正确阻断了泛页。这样后续改动更像工程收口，而不是凭直觉改 query。

### 当前结论

现有方案还能继续解，下一轮应优先实施 CB1-CB3。外部对标支持这个方向：可追踪检索、证据类型区分、槽位对齐、证据账本，比继续堆题型模板更通用。

### 下一步建议

先实现通用 slot contract 和 evidence ledger reason，再做一次 5 锚点 `--workers 4` 回归。若仍然拿不到反证，再基于 `refutation_query_plan / refutation_slot_gap` 判断是检索计划问题、source 问题、页面抽取问题，还是消费 gate 误杀。

## 实施状态同步（2026-05-11 夜）

### 基于什么架构

本轮实现仍基于 `Evidence Page Contract + Page Role Contract + Evidence Consumer Gate + numeric decision_slots grounding + 双通道裁决`，没有新增 provider，没有扩大 fallback，没有引入 LLM 终判，也没有改 `solve_submit.py`。

### 实现了什么

已完成首轮 CB 接线：

- `evidence.py` 增加通用 slot contract，给候选句和 point 写出 `slot_contract_state / slot_coverage / slot_missing / slot_mismatch / slot_conflict / same_slot_ready / refute_slot_ready`。
- `retrieval.py` 增加 `refutation_target / refutation_query_plan / refutation_retry_trigger / refutation_slot_gap / refutation_search_result / refutation_retrieval_stop_reason`，并让每个 claim 最多 1 条 refutation target 进入受控 execution plan。
- `solve.py` 增加 evidence ledger reason，debug 中输出 `confirmed_points / refuted_points / unresolved_points / gate_blocked_pages / slot_blocked_candidates / fallback_scope / final_label_reason`。
- 现有 gate 保持严格：`entry_page / generic_page / blocked_page / pseudo_evidence` 仍不能直接推动标签，fallback 仍只做保守兜底。

### 解决了什么

首轮解决的是“链路可见性”和“reason 表达”：

- `refutation_target` 不再只是纸面字段，已经进入实际检索执行计划。
- reason 不再只说“没拿到同一口径证据”，而能写出“已确认哪些点、未闭合哪些点、缺口在哪些 slot”。
- 对 `afc_0008 / afc_0010`，系统能展示已确认的汇率/中间价点，同时仍因为其他 claim 未闭合而保守为 `2`，没有误抬标签。

### 还卡在哪

当前还没有形成新的稳定 `refuted_points`。也就是说，本轮主要把“反证目标”和“账本 reason”打通了，但反证证据本身仍然不够多。

典型状态：

- `afc_0001`：有 refutation target 和 raw positive，但仍没有同槽反证。
- `afc_0003`：仍多停在相关但不可直裁。
- `afc_0008 / afc_0010`：能确认部分数值事实，但没有把其他错误点稳定打成 refute。

### 现有方案还能不能继续解

还能继续解。当前不是架构失效，而是下一步要利用新字段定位：

- 如果 `refutation_target=ready` 且 `refutation_search_result=raw_positive`，但没有 refute，说明问题在 page keep、candidate extraction 或 slot conflict 判定。
- 如果 `same_slot_ready=true` 但没有 `refute_slot_ready`，说明候选证据支持/确认了某个点，但没有找到冲突值或冲突状态。
- 如果 `slot_missing` 长期集中在 `time_scope`，下一轮应优先修时间槽位绑定，而不是继续泛搜。

### 如果不能，再去外部检索

本轮暂不需要继续外部检索。外部方向已经支持“slot contract + refutation retrieval + ledger reason”。下一次外部检索触发条件是：连续多轮 `refutation_target` 已执行但没有任何同槽 conflict，且本地 debug 无法解释是页面、句子还是槽位判定问题。

### 验证结果

固定 5 锚点，命令：

```powershell
python solve.py --input local_dev/tmp/phase4_bmbnbo_anchor_input_sample0410.json --output local_dev/tmp/phase4_cb_slot_contract2_anchor_sample0410_output.json --debug-output local_dev/tmp/phase4_cb_slot_contract2_anchor_sample0410_debug.json --perf-output local_dev/tmp/phase4_cb_slot_contract2_anchor_sample0410_perf.json --workers 4 --no-resume
```

结果：

- `afc_0001 = 2`
- `afc_0002 = 1`
- `afc_0003 = 2`
- `afc_0008 = 2`
- `afc_0010 = 2`

字段验收：

- 5 个样本均出现 `refutation_target`。
- 多个 claim 出现 `refutation_query_plan`，且 `refutation_search_result=raw_positive`。
- 多个样本出现 `confirmed_points / unresolved_points` 账本。
- `slot_contract_state / slot_missing / slot_mismatch / same_slot_ready` 已进入 claim pipeline diagnostics。

耗时：

- 本轮 `retrieve` 平均 68.054s。
- CA 新基线约 69.293s。
- 本轮 retrieve 没有超过基线 10%。

### 当前结论

CB 首轮算“诊断链和 reason 链通过”，但还不是“反证成功率显著提升”。下一步不应回到泛搜，而应按新 debug 做二次收口：优先审计 `refutation_target=ready + raw_positive + same_slot_ready=true` 却没有 `refute_slot_ready` 的 claim，判断是证据本身支持了原 claim，还是 conflict 判定太弱。
