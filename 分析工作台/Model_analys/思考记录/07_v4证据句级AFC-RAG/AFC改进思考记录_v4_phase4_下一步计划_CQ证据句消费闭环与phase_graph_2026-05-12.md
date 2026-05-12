# AFC v4 Phase4 下一步计划：CQ 证据句消费闭环与 phase_graph

日期：2026-05-12

关联前序文档：
- `AFC改进思考记录_v4_phase4_下一步计划_CI高风险原子claim路由_2026-05-12.md`
- `AFC改进思考记录_v4_phase4_CL2原子反证转换器实施记录与下一步规划_2026-05-12.md`
- `AFC改进思考记录_v4_phase4_执行计划_CO可反证证据转化率与三类转换器闭环_2026-05-12.md`
- `AFC改进思考记录_v4_phase4_下一步计划_CMCL3受阻原子claim页面消费升级与强反证闭环_2026-05-12.md`

## 1. 本文和前序文档的关系

CI 证明了“高风险原子 claim”这条路线是对的：标准 reason 关心的错点，通常都是小而硬的原子事实。

CL2/CO 证明了部分原子 claim 已经可以被检索和账本消费：`market_calendar_status`、`exclusive_or_only_path` 已经能稳定进入 `atomic_refuted_points`，并推动 `afc_0001 / afc_0003` 这类样本判对。

CP/CO6 暴露了当前短板：系统已经能找到一批候选页和冲突信号，但很多候选停在 `blocked_entry_page_requires_follow / blocked_access_page / blocked_generic_page / page_gate_not_ready`，没能变成同槽可裁证据。典型是 `afc_0004 / afc_0007`。

所以 CQ 不继续扩大题目词或样本规则，而是专门补“候选证据 -> 同槽可裁反证”这一段。

## 2. 分类

证据链 / 页面消费 / 原子 claim / 同槽裁决 / phase_graph / 反过拟合 / 回归验证

## 3. 这次要做什么

本轮目标是打通这条链路：

`atomic claim -> query -> raw/kept/blocked candidate -> evidence sentence reader -> slot judge -> atomic_refuted_points 或明确 unresolved reason`

分三段实施：

1. 入口页正文抽取
   - 对高风险 atomic claim 的前 1-2 个 `entry_page / blocked_page / generic_page` 做受控 reader。
   - 只抽证据句和结构字段，不直接改 label。
   - 输出 `reader_sentence_candidates`，字段包括 `subject_hit / time_hit / role_hit / status_hit / conflict_hint / source_quality / original_gate`。

2. 同槽句子判定
   - 把 reader 抽到的候选句送进风险类型对应的 slot judge。
   - 重点覆盖：
     - `event_result_status`：详细比分 vs 退赛/弃权/不战而胜/取消。
     - `phase_boundary_time`：整体结束、阶段开始、结果公布之间的角色冲突。
     - `current_position_distance`：同对象、同时间窗、同参照点、同单位口径。
     - `exclusive_or_only_path`：唯一/只能/必经 vs 替代路径/管道/港口/绕开。
   - 只有 `same_slot_ready + strong_conflict + source_allowed` 才能进入 `atomic_refuted_points`。

3. phase_graph 跨原子关系消费
   - 对同一事件下的多个阶段原子 claim 建一个轻量阶段图。
   - 识别 `phase_start / phase_end / whole_event_end / result_release`。
   - 如果证据说明“第二阶段在 X 开始”，则不能把 X 直接消费成“整体结束”或“最终结果发布”。
   - 该图谱只服务 `phase_boundary_time`，不直接按题目词判标签。

## 4. 动机是什么

当前失败不是因为完全搜不到，而是因为“搜到了但不敢用”。

这其实是一个健康失败：系统没有绕过 gate，也没有为了分数把普通相关页硬判成反证。但如果长期停在这里，标准 reason 里的小错点就很难被稳定命中。

我们需要补的是证据消费能力，而不是继续给每道题写转换器。真正要提升的是：页面中已有的证据句能否被安全抽出、对齐到同一事实槽位，并被账本追踪。

## 5. 对项目的实际作用

这一步能把“检索有效但裁决失败”的样本转成可审计路径：

- 能反证的，进入 `atomic_refuted_points`。
- 不能反证的，明确卡在 `source_quality / page_gate / slot_match / conflict_strength / phase_graph` 哪一层。
- 无错样本继续不误抬，尤其保护 `afc_0008 / afc_0010` 这类数值口径题。

这会让后续优化从“猜为什么错”变成“看哪一层没过”。

## 6. 具体场景是什么

### 6.1 event_result_status

回答声称某场比赛 `3-0`，候选页标题或正文出现“退赛 / 不战而胜 / withdraw / walkover”。

系统要判断：
- 是不是同一选手/队伍？
- 是不是同一比赛或同一时间窗口？
- 退赛词是否和主体足够接近？
- 来源是否可消费？

目标样本：`afc_0004`。  
通用场景：任何体育、赛事、评奖、比赛结果中的“比分 vs 特殊状态”冲突。

### 6.2 phase_boundary_time

回答把“第二阶段开始时间”误当成“整体结束时间”或“最终结果发布时间”。

系统要判断：
- claim 的角色是 `whole_event_end` 还是 `result_release`？
- 证据句的角色是 `phase_start` 还是 `phase_end`？
- 两者是否属于同一事件？
- 是否能通过 phase_graph 说明它们不能互换？

目标样本：`afc_0007`。  
通用场景：人口普查、项目审批、考试报名、政策执行、工程施工、数据发布等阶段流程。

### 6.3 current_position_distance

回答声称对象当前位置或距离为某数值，候选材料给出另一个距离。

系统要判断：
- 是否同一对象？
- 是否同一日期或可接受时间窗？
- 是否同一参照点？
- 单位是否可转换？
- 是否历史位置或传闻位置？

目标样本：`afc_0005`。  
通用场景：船舶、航班、军舰、台风、火灾、地震、赛事地点等位置/距离事实。

## 7. 应该怎么使用

调试时按这个顺序看：

1. `atomic_claims`
2. `high_risk_atomic_claims`
3. `atomic_query_plan`
4. `atomic_search_results`
5. `reader_rescue_debug`
6. `reader_sentence_candidates`（新增）
7. `slot_sentence_judge_debug`（新增）
8. `phase_graph_debug`（新增）
9. `atomic_refuted_points`
10. `atomic_page_consumption_debug`
11. `final_label_reason`

如果某个样本没判对，优先问：
- 没搜到，还是搜到了没保留？
- 保留了页面，是否没抽出正文句？
- 抽出句子，是否主体/时间/角色没对齐？
- 对齐了，是否冲突强度不够？
- 冲突强，是否被 source/page gate 拦住？

## 8. 对用户意味着什么

用户真正关心的是：系统能不能像人工标准 reason 一样，抓住那种一句话里的小错点。

CQ 的目标不是让系统更激进，而是让它更有证据地变准。  
如果证据足够，应该敢于判错；如果证据不够，应该说清楚卡在哪里，而不是用“可能错”去误伤答案。

## 9. 对开发者意味着什么

开发者后续不要继续按样本 ID 或题面专名加规则。

新增逻辑必须满足：
- 规则只绑定 `risk_type / slot_contract / expected_evidence_shape`。
- 样本只用于回归验证，不作为触发条件。
- `entry_page / generic_page / blocked_page / pseudo_evidence` 不能绕 gate 直接改标签。
- LLM 如果参与，只能输出结构化 evidence verdict，不能直接给最终 label。
- 所有转换都必须能在 ledger/debug 中解释来源、句子、槽位和冲突类型。

## 10. 反过拟合约束

本轮禁止：
- 写 `afc_0004 / afc_0007 / afc_0005` 专用分支。
- 写具体标准答案真值。
- 写具体题目专名触发器。
- 因为 risk_type 高风险就直接改标签。
- 用弱来源标题直接替代正文证据。

本轮允许：
- 增加通用结构词桥接，例如 `phase/start/end/release` 与中文阶段词的对齐。
- 对 entry/blocked 页面做受控正文句抽取。
- 对同一事件下多个阶段原子 claim 做 phase_graph。
- 把强同槽冲突转换为 `atomic_refuted_points`。

## 11. Test Plan

固定回归：
- `afc_0001`
- `afc_0002`
- `afc_0003`
- `afc_0004`
- `afc_0005`
- `afc_0007`
- `afc_0008`
- `afc_0010`

守门目标：
- `afc_0001 = 1`
- `afc_0002 = 1`
- `afc_0003 = 1`
- `afc_0008 = 2`
- `afc_0010 = 2`

推进目标：
- `afc_0004` 至少重新进入稳定 `atomic_refuted_points`，最好恢复为 `0`。
- `afc_0007` 至少出现 `phase_graph_debug`，并能解释“阶段开始不能等同整体结束/结果发布”。
- `afc_0005` 至少明确卡在对象、时间窗、参照点或单位口径，而不是泛泛 `page_gate_not_ready`。
- 至少 2 个当前卡住样本从 `page_gate_not_ready` 推进到更细粒度的 `slot_sentence_judge_debug`。

性能目标：
- 8 样本 retrieve 均值尽量不超过当前 CP6 回归 10%。
- 如果超过，保留 debug，但不让新增 reader 参与标签聚合。

## 12. 当前结论

当前系统已经证明：原子 claim 路线不是错的，检索也不是完全无效。真正短板在证据消费层。

CQ 的任务就是把“搜到了但不能用”的候选材料，变成可审计、可对齐、可裁决的证据句。  
这一步做对了，后续标签提升才会来自证据链，而不是来自押题规则。

## 13. 下一步建议

立即开始 CQ1：

1. 在 `solve.py` 中新增 `reader_sentence_candidates` 展示层。
2. 对 `blocked_entry_page_requires_follow / blocked_access_page / blocked_generic_page` 的高风险 atomic claim 做受控抽句。
3. 新增 `slot_sentence_judge_debug`，先只展示，不直接改标签。
4. 单跑 `afc_0004 / afc_0007 / afc_0005`，确认卡点能被拆细。
5. 再开启转换到 `atomic_refuted_points`，最后跑 8 样本守门。

## 14. CQ1 执行记录：reader 句子候选与 slot judge 展示层

日期：2026-05-12

### 分类

证据链 / 页面消费 / 原子 claim / 回归验证 / 反过拟合

### 这次实际做了什么

本轮已在 `solve.py` 增加 CQ1 只读诊断层：

- 在 `apply_blocked_page_reader_rescue` 内记录逐句 reader 候选，不再只保留 best sentence。
- 新增 `reader_sentence_candidates`，展示每个候选句的 `atomic_claim_id / parent_claim_id / risk_type / sentence / source / original_gate / subject_hit / time_hit / role_hit / status_hit / conflict_hint / source_allowed / judge_state / conflict_slot`。
- 新增 `slot_sentence_judge_debug`，把 slot judge 的中间态单独落到账本，方便看出是主体、时间、角色、状态、来源还是 gate 卡住。
- 接入 `build_evidence_ledger`，新增字段只用于展示和诊断，不直接改变最终标签。

### 动机是什么

上一轮短板不是“完全搜不到”，而是“候选页和候选句已经出现，但系统不知道为什么不能消费”。  
如果只看最终标签，会误以为要继续扩大检索；但实际问题常常在候选句已经命中后，卡在 source/page gate、slot 对齐、角色判断或冲突强度。  
CQ1 的目标就是把这段黑盒拆开，让下一步能针对真实卡点补能力。

### 对项目的实际作用

这轮改动把证据消费链路从一个结果型字段，拆成了可审计路径：

`blocked page -> reader sentence -> slot judge -> candidate/debug -> ledger`

以后看失败样本时，可以直接判断：

- 是没有检索结果；
- 是 raw 有但 kept 没有；
- 是 kept 有但 gate 阻断；
- 是句子抽到了但 subject/time/role/status 没对齐；
- 是对齐了但来源不允许裁决；
- 是冲突已经强，但还不能越过 gate。

### 具体场景

焦点回归 `afc_0004 / afc_0007 / afc_0003` 已能看到新增字段：

- `afc_0004`：`event_result_status` 候选句出现 `退赛/不战而胜`，`judge_state=strong_conflict`，能看清“比分 claim vs 退赛证据”的冲突结构。
- `afc_0007`：`phase_boundary_time` 候选句能显示 `claim_role=whole_event_end`、`evidence_role=result_release` 或相关角色信息，但仍卡在 `role_or_time_not_conflicting / raw_only`，说明下一步要补 phase_graph，而不是继续盲搜。
- `afc_0003`：`exclusive_or_only_path` 能看到未消费候选为何卡在 `slot_mismatch` 或来源限制。

### 应该怎么使用

后续调试顺序：

1. 先看 `atomic_page_consumption_debug` 判断 retrieval/page gate 卡点。
2. 再看 `reader_sentence_candidates` 判断是否抽到了可能有用的句子。
3. 再看 `slot_sentence_judge_debug` 判断 subject/time/role/status 哪个槽没对齐。
4. 最后才看 `atomic_refuted_points` 是否形成同槽可裁决反证。

不要把 `reader_sentence_candidates` 或 `slot_sentence_judge_debug` 直接当标签依据。它们只是下一步 CQ2/CQ3 的输入诊断。

### 对用户意味着什么

用户现在能看到系统为什么“明明搜到了材料却没有判错”。  
这比直接加规则更稳，因为它不押具体样本，而是解释证据链缺口。

### 对开发者意味着什么

开发者下一步不应该按 `afc_0004 / afc_0007 / afc_0005` 写专用逻辑，而应该按以下三类通用缺口补能力：

- `event_result_status`：比分/正常完赛 vs 退赛/弃权/不战而胜。
- `phase_boundary_time`：阶段开始、整体结束、结果发布之间的角色图谱。
- `current_position_distance`：同对象、同时间窗、同参照点、同单位口径的距离冲突。

### 回归结果

已跑：

- `python -m py_compile solve.py retrieval.py`
- `phase4_cq1_focus_output/debug/perf`
- `phase4_cq1_8sample_output/debug/perf`

观察：

- `afc_0001 = 1`
- `afc_0002 = 1`
- `afc_0003 = 1`
- `afc_0008 = 2`
- `afc_0010 = 2`
- `reader_sentence_candidates / slot_sentence_judge_debug` 在 `afc_0002 / afc_0003 / afc_0004 / afc_0007` 上均有可见诊断。

同时暴露两个问题：

- `afc_0004` 在焦点跑能进入主需反证，但 8 样本跑仍不稳定，说明来源和 reader rescue 的消费链还需要更稳定的 gate 策略。
- `afc_0005` 出现“网页头部日期被当作航母位置事实反证”的假阳性，说明下一步必须收紧 date-only conflict，不能让无关页面日期直接驱动事实错误。

### 当前结论

CQ1 成功补出了可观察性：现在能看见候选句、slot judge 状态和 gate 阻断原因。  
但它还不是最终提分层，不能把诊断字段直接用于标签。  
下一步应进入 CQ2：把“强同槽证据”和“伪日期/无关页”分开，尤其要补 `phase_graph` 和 `date-only conflict guard`。

### 下一步建议

1. 给 `date_conflict` 增加通用保护：只有当证据句同时命中主体和事实关系/指标时，日期差异才可作为反证；网页发布时间、导航日期、政策发布日期不能单独反驳位置/距离/状态 claim。
2. 给 `phase_boundary_time` 增加 `phase_graph_debug`：区分 `phase_start / phase_end / whole_event_end / result_release`。
3. 给 `current_position_distance` 增加同槽 reader judge：要求同对象、同参照点、同时间窗、同单位口径后，才允许距离数值冲突进入 `atomic_refuted_points`。
