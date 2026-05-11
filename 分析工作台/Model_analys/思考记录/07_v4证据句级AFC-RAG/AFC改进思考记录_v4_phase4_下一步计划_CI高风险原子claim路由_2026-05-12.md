# AFC v4 Phase4 下一步计划：CI 高风险原子 claim 路由

## Summary

上一轮 CG/CH 已经让候选冲突显性化，但仍暴露出一个更前置的问题：系统没有稳定把“真正决定标签的错误原子”优先抽出来。标准 reason 关心的是 `A股是否休市`、`唯一海上通道是否成立`、`退赛却写比分`、`当前距离是否同口径` 这类小而硬的事实断言；而当前链路经常把注意力放到更大的解释性断言上，比如“外资抢筹”“军事施压”“市场定价分化”。

因此下一步不继续堆检索模板，而是增加一层 **High-risk Atomic Claim Router**：先从回答里抽出高风险原子 claim，再把它们送进现有 slot / retrieval / gate / ledger 链路。它不直接判错，只改变核查优先级和检索目标。

## 与前序文档的关系

### 1. 接续 CB：Slot Contract 与证据账本

CB 已经建立了 `subject / time_scope / object / metric_or_relation / status_or_result / comparison_baseline / source_scope` 的通用槽位账本。CI 不重做 slot，而是给每个高风险原子 claim 生成更小、更可裁决的 slot contract。

例如：

- 原回答大 claim：港股比 A 股贵且涨得多，代表外资抢筹。
- CI 原子 claim：`2026-04-01 A股仍因清明节休市`。
- 进入 CB 槽位：`subject=A股`，`time_scope=2026-04-01`，`status_or_result=休市/开市`。

### 2. 接续 CD/CE/CF：核心断言审计

CD/CE/CF 能说明“表层事实确认但核心断言未闭合”。CI 要解决的是：有些标准错误并不是核心解释断言，而是答案中的高风险支撑细节。CI 会把这些支撑细节显式提升，避免被大 claim 淹没。

### 3. 接续 CG/CH：候选冲突挖掘

CG 已能发现候选中的日期、数值、状态、赛果冲突。CI 的作用是让冲突挖掘有更好的输入：先把 `退赛 vs 3-0`、`唯一通道 vs 替代管道`、`当前距离 vs 历史距离` 这类原子 claim 送进去，而不是等系统从泛候选里偶然碰撞出来。

### 4. 保持既有 gate 不变

CI 只改变“查什么”和“先查什么”，不改变“什么能被消费”。`entry_page / generic_page / blocked_page / pseudo_evidence` 仍然不能直接驱动标签。

## 分类

证据链路 / Workflow / 检索路由 / 测试与回归

## 这次要做什么

新增一层 `atomic_claims`，每个原子 claim 至少包含：

- `atomic_claim_id`
- `parent_claim_id`
- `text`
- `risk_type`
- `centrality_hint`
- `expected_evidence_shape`
- `slot_contract`
- `search_priority`
- `refutation_target`
- `do_not_decide_without_gate`

优先支持这些 `risk_type`：

- `market_calendar_status`：开市、休市、交易日、节假日。
- `exclusive_or_only_path`：唯一、只能、没有其他路径、必须经过。
- `event_result_status`：比分、胜负、退赛、弃权、不战而胜。
- `current_position_distance`：当前位置、截至某日距离、舰船/人员/航母位置。
- `phase_boundary_time`：第一阶段、第二阶段、开始、结束、结果公布。
- `reality_vs_fiction_status`：现实发生、虚构剧本、网传、AI生成、未发生。
- `numeric_quote_or_metric`：汇率、买入价、卖出价、中间价、实时价、人数、战绩。

## 动机是什么

标准 reason 和我们当前 reason 的差距不是“完全不会推理”，而是“没有先抓住最硬的错误原子”：

- `afc_0001` 标准打 `4月1日不是清明休市`，我们打成了核心解释未闭合。
- `afc_0003` 标准打 `霍尔木兹不是唯一通道`，我们继续围绕军事配合主线。
- `afc_0004` 标准打 `退赛/不战而胜 vs 3-0比分`，我们只看到泛页赛果冲突。
- `afc_0005` 标准打 `当前距离口径`，我们消费了历史 3月7日距离。

这些问题的共同根因是：回答中有些小断言比大段解释更可裁决、更容易反证，但它们没有被稳定提升。

## 对项目有什么实际作用

1. 提高错误点命中率：优先核查最可能导致标签变化的小事实。
2. 降低泛搜成本：检索目标从整段解释变成可搜索的原子断言。
3. 提高 reason 可读性：最终 reason 能写“哪个原子 claim 被证伪”，而不是笼统说“核心断言未闭合”。
4. 保持通用性：抽的是风险类型，不是样本答案。

## 具体场景是什么

### afc_0001

原回答中应抽出：

- `今天（2026-04-01）A股因清明节假期休市`
- risk_type: `market_calendar_status`
- 查询目标：`2026-04-01 A股 交易日 清明节 休市 开市`

标准错误点：4月1日是正常交易日，并非清明节。

### afc_0003

原回答中应抽出：

- `霍尔木兹海峡是阿联酋石油出口和商品进口的唯一海上通道`
- risk_type: `exclusive_or_only_path`
- 查询目标：`UAE oil export bypass Strait of Hormuz pipeline Fujairah Oman Gulf`

标准错误点：阿联酋有陆上管道和阿曼湾港口通道，可绕开霍尔木兹。

### afc_0004

原回答中应抽出：

- `覃予萱 3-0 战胜 安妮特·考夫蔓`
- risk_type: `event_result_status`
- 查询目标：`覃予萱 考夫蔓 退赛 不战而胜 3-0 澳门世界杯`

标准错误点：考夫蔓因伤退赛，覃予萱不战而胜，模型虚构具体比分。

### afc_0005

原回答中应抽出：

- `截至2026-03-30 林肯号距离伊朗海岸约350公里`
- risk_type: `current_position_distance`
- 查询目标：`USS Abraham Lincoln 2026-03-30 distance Iran coast 350 1100 km`

标准错误点：当前距离口径不是单点约350公里，而是从约340到1100公里的动态范围。

### afc_0007

原回答中应抽出：

- `印度人口普查预计2027年3月结束`
- risk_type: `phase_boundary_time`
- 查询目标：`India census 2027 March phase begins ends result`

标准错误点：2027年3月1日是第二阶段开启，不是人口普查结束或结果公布。

## 应该怎么使用

在 pipeline 中新增顺序：

1. 原 answer 抽取普通 claims。
2. 从普通 claims 和 answer 原文中抽取 `atomic_claims`。
3. 给原子 claim 打 `risk_type` 和 `search_priority`。
4. 高风险原子 claim 进入 retrieval plan，优先级高于解释性大 claim。
5. 检索结果仍走 Page Role Contract、Evidence Page Contract、Gate、Slot Contract。
6. 证据账本新增：
   - `atomic_confirmed_points`
   - `atomic_refuted_points`
   - `atomic_unresolved_points`
   - `high_risk_atomic_claims`
   - `atomic_claim_route_debug`
7. 最终 reason 优先引用 `atomic_refuted_points`。

## 不应该怎么用

不能写样本专用规则：

- 不写死 `2026-04-01 A股正常交易`。
- 不写死 `考夫蔓退赛`。
- 不写死 `阿联酋有某条管道`。
- 不写死 `林肯号 340-1100 公里`。

只能写通用模式：

- 交易日/休市状态要查交易日历。
- 唯一性断言要查替代路径。
- 赛果比分要同时查退赛/弃权/不战而胜。
- 当前距离要绑定日期和时间口径。
- 阶段结束/开始要区分 start / end / result release。

## 对用户意味着什么

用户会看到更接近人工标准 reason 的输出：不是只说“没拿到证据”，而是能指出“答案中哪个小事实最可疑、查到了什么、为什么足以或不足以判错”。

## 对开发者意味着什么

开发者下一轮要关注的不是 query 数量，而是 `atomic_claims` 的质量：

- 是否抽到了标准 reason 关心的小断言？
- 是否给了正确的 `risk_type`？
- 是否生成了正确的 `refutation_target`？
- 是否因为 gate 合理阻断，还是误杀了可裁决证据？

## 实施计划

### CJ：Atomic Claim Extractor

主改 `solve.py`，必要时补 `evidence.py` helper。

输出：

- `atomic_claims`
- `high_risk_atomic_claims`
- `atomic_claim_route_debug`

规则：

- 先基于正则/关键词做 deterministic extractor。
- 不引入 LLM 终判。
- 原子 claim 不直接改标签。

### CK：Atomic Risk Router

主改 `retrieval.py`。

根据 `risk_type` 生成检索目标：

- `market_calendar_status`：交易日历、休市、开市、节假日。
- `exclusive_or_only_path`：替代路径、管道、港口、绕开、bypass、alternative route。
- `event_result_status`：result、score、retired、walkover、withdrawal、退赛、不战而胜。
- `current_position_distance`：current position、distance、as of date、location。
- `phase_boundary_time`：phase begins、phase ends、result release、completion。

每个样本最多提升 2 个高风险原子 claim，避免时延爆炸。

### CL：Atomic Ledger Consumer

主改 `solve.py`。

新增账本字段：

- `atomic_confirmed_points`
- `atomic_refuted_points`
- `atomic_unresolved_points`
- `atomic_gate_blocked_points`
- `atomic_final_label_pressure`

聚合原则：

- 若高风险原子 claim 被同槽强反证，允许推动标签。
- 若只是候选冲突但 gate 未过，只写 reason，不推动标签。
- 若主需求原子 claim 被反证，标签压力为 `0`。
- 若支撑细节原子 claim 被反证，标签压力为 `1`。

## Test Plan

固定回归：

- `afc_0001`
- `afc_0002`
- `afc_0003`
- `afc_0004`
- `afc_0005`
- `afc_0007`
- `afc_0008`
- `afc_0010`

继续使用：

- `--workers 4`

重点检查字段：

- `atomic_claims`
- `high_risk_atomic_claims`
- `risk_type`
- `atomic_claim_route_debug`
- `atomic_refuted_points`
- `atomic_unresolved_points`
- `atomic_final_label_pressure`
- `final_label_reason`

验收标准：

- `afc_0002` 继续稳定为 `1`。
- `afc_0008 / afc_0010` 不误抬标签。
- 至少 `afc_0001 / afc_0003 / afc_0004 / afc_0005 / afc_0007` 中 2 个样本抽到标准 reason 对应的高风险原子 claim。
- 至少 1 个样本从“核心断言未闭合”升级为“某个高风险原子 claim 被证伪或明确卡在某 gate”。
- 不允许无证据直接靠 risk_type 改标签。
- retrieve 均值不能超过当前 CG/CH 基线 10%；若超过，先保留 extractor 和 ledger，不放开更多 atomic retrieval。

## 风险与边界

### 可能过拟合的地方

如果实现时把样本里的具体答案写成规则，就是过拟合。

### 避免过拟合的方法

1. 只写 `risk_type` 级别模式。
2. 只生成检索目标，不直接判错。
3. 所有消费继续走 gate。
4. 在非样本题上检查相同风险类型是否也能生成合理 query。

## 当前结论

CI 是下一步最值得做的方向。它不是替代检索，也不是替代 gate，而是把检索和 gate 的输入从“大段解释 claim”变成“小而硬的高风险原子 claim”。这能解释为什么标准 reason 和我们当前 reason 不一致，也能给后续泛化提供一条不靠样本答案硬编码的路线。

## 下一步建议

先实现 CJ 的只读抽取和账本展示，不急着让它改标签。  
第一轮目标是看 `atomic_claims` 是否能抓到标准 reason 对应错误原子；如果抓不到，就先修 extractor。只有当原子 claim 抽取稳定后，再打开 CK 的高优先级检索和 CL 的标签压力。

---

## 2026-05-12 CI 第一版落地记录：只读 atomic claim 抽取与账本展示

### 分类

证据链路 / 路由 / 测试与回归

### 这次要做什么

这次完成的是 CI 中的 CJ 子阶段：在 `solve.py` 增加只读 `atomic_claims` 抽取层，并把结果挂到 `evidence_ledger`。同时在 `retrieval.py` 增加 planned-only 的 atomic query plan 入口，但默认不执行、不扩大检索成本。

新增展示字段包括：

- `atomic_claims`
- `high_risk_atomic_claims`
- `atomic_claim_route_debug`
- `atomic_refuted_points`
- `atomic_unresolved_points`

### 动机是什么

前一轮 CD/CE/CF/CG/CH 已经能说明“核心断言未闭合”或“候选冲突未成型”，但仍容易错过人工标准 reason 里真正关键的小断言，例如：

- A股是否休市。
- 霍尔木兹是否为唯一通道。
- 退赛/不战而胜和 3-0 比分是否冲突。
- 当前距离是否是单点距离还是范围口径。
- 第二阶段开始时间是否被误写成普查结束时间。

这些不是大段解释 claim，而是“小而硬”的原子事实。CI 的意义就是先把这些小事实稳定抽出来，再进入后续检索和 gate。

### 对我们的项目有什么实际作用

这次改动不追求立刻提高标签，而是把“为什么没打到标准错点”变成可观察问题。现在可以直接在 debug 里看：

- 系统有没有抽到标准错点。
- 标准错点被归到哪种 `risk_type`。
- 后续应该查什么证据形态。
- 为什么本轮仍不能用它改标签。

这让下一步 CK/CL 不再盲目扩大 query，而是围绕高风险原子 claim 精准加路由。

### 具体场景是什么

以本轮回归为例：

- `afc_0001` 抽到了“4月1日 A股还在清明节假期休市，港股率先开盘”，风险类型为 `market_calendar_status`。
- `afc_0003` 抽到了“霍尔木兹海峡是阿联酋石油出口和商品进口的唯一海上通道”，风险类型为 `exclusive_or_only_path`。
- `afc_0004` 抽到了覃予萱 vs 考夫蔓的 3-0 赛果表，风险类型为 `event_result_status`。
- `afc_0005` 抽到了“林肯号距伊朗海岸约 350 公里”，风险类型为 `current_position_distance`。
- `afc_0007` 抽到了“2027年3月才会结束 / 结果之后公布”和两阶段描述，风险类型为 `phase_boundary_time`。

同时修正了一个泛化噪声：`300-500公里`、`6.88-6.90`、`09:15` 不应被误识别成比分。现在比分型原子 claim 需要同时满足“比分形态 + 赛事上下文”。

### 我应该怎么使用

调试时优先看 `debug.evidence_ledger.high_risk_atomic_claims` 和 `debug.evidence_ledger.atomic_claim_route_debug`。

判断顺序建议是：

1. 先看标准错点是否在 `atomic_claims`。
2. 再看 `risk_type` 是否合理。
3. 再看 `slot_contract` 是否给出了主体、时间、指标、状态。
4. 最后看 `refutation_target.query` 是否适合下一轮 CK 路由。

本轮不要用 `risk_type` 或 `atomic_unresolved_points` 改标签。

### 对用户意味着什么

用户暂时不会看到标签大幅变化，但 reason 和 debug 的可解释性更强了。后续一旦 CK/CL 打通，系统会更容易指出“具体哪个小事实错了”，而不是笼统说“证据不足”。

### 对开发者意味着什么

开发者下一轮可以把工作切得更小：

- CK 只负责把高风险 atomic claim 变成检索 query。
- CL 只负责把 gate 通过的 atomic 反证变成标签压力。
- 当前 CJ 只负责抽取和展示，不承担裁决责任。

这样能降低过拟合风险，也方便单独评估每层是否真的有效。

### 当前结论

CI 第一版已经达到“只读抽取 + 账本展示”的目标。8 样本回归中，至少 5 个样本抽到了标准 reason 相关的高风险原子 claim；`afc_0002` 仍为 `1`，`afc_0008 / afc_0010` 仍为 `2`，没有因为 `risk_type` 直接改标签。

同口径 5 锚点性能对比：

- CG/CH 基线 retrieve 均值：`56.904s`
- CI 5 锚点 retrieve 均值：`57.496s`

retrieve 增幅约 `1.0%`，没有超过 10% 阈值。8 样本整体 retrieve 均值为 `66.175s`，主要因为加入 `0004/0005/0007` 后样本结构不同，不作为同口径性能基线。

### 下一步建议

下一步进入 CK，但仍要保守：只对 `high_risk_atomic_claims` 中 priority 最高的 1-2 个原子 claim 开 atomic route，并继续强制 gate。优先处理三类最接近标准 reason 的路由：

1. `market_calendar_status`：交易所日历/休市公告。
2. `exclusive_or_only_path`：替代通道/管道/港口/绕开。
3. `event_result_status`：退赛/不战而胜/官方赛果页。

如果 CK 后 retrieve 超过 10%，就只保留 planned query 和 route debug，不让 atomic route 进入实际搜索。
