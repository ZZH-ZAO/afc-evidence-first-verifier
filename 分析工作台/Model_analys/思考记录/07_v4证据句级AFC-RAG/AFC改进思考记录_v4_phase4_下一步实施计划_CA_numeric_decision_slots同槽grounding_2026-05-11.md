# AFC v4 Phase4 下一步实施计划（CA：numeric decision_slots 同槽 grounding）

## 基于什么架构

继续基于 `受控 Search Tool + authority-first 入口 + Evidence Page Contract + Page Role Contract + Evidence Consumer Gate + 双通道裁决`。

这轮不新增 provider，不扩大 fallback，不引入 LLM 终判，也不回滚前面已经落下的 page role / title-level fact evidence 规则。上一轮已经证明：检索入口和证据页识别开始有效，部分官方/权威标题级事实页可以进入 `evidence_page -> candidate -> point` 链路；但数值点还没有稳定对齐到 claim 的同一事实位点。

## 实现了什么

当前已经实现：

- `official_discovery` 在通过 Page Role Contract 后可以进入消费链，而不是永远 discovery-only。
- `entry_page/generic_page` 不能直接推动标签，只能用于诊断或受控跟进。
- 标题级事实页如果包含主体、时间、指标、数值/结果，可以成为 `evidence_page`。
- `afc_0008` 已经出现 `allowed_evidence_page / stable_direct_point` 这类真实消费迹象。
- `afc_0002` 稳定，`afc_0008 / afc_0010` 没有因为泛页放开而误抬。

## 解决了什么

前几轮主要解决了“证据是不是可以进来”的问题：泛页被挡住，入口页不再冒充证据页，官方发现页在满足事实页条件时可以进入消费。

这轮要解决的是下一层：“进来的数值证据是否和 claim 的同一个事实槽对齐”。

具体说，numeric summarizer 不能再只从 claim 文本里顺序取第一个非年份数字。它必须优先读取：

- `evidence_need_program.decision_slots.object`
- `evidence_need_program.decision_slots.status_or_result`
- `source_intent.core_binding.object_entity`
- `source_strategy.must_have`
- `direct_evidence_need.must_include`

然后再回退到 claim 文本数字，并且回退时必须剔除日期/时间数字。

## 还卡在哪

当前卡在 `point grounding` 层，而不是纯入口层：

- 检索已经能拿到一些权威/新闻/标题级事实页。
- 候选句已经能进入 `evidence_sentence_candidates`。
- 但 numeric point 可能把日期中的月/日、时间戳、年份、榜单序号等当成 claim_value。
- 对汇率、中间价、涨跌基点、行情开盘涨幅这类 claim，真正该比较的是 `object/status_or_result` 中的数值，而不是文本里最早出现的数字。

因此下一刀应该落在 `evidence.py` 的 numeric summarizer，而不是继续堆 query。

## 现有方案还能不能继续解

能继续解。

原因是失败层仍能被现有架构解释：

- 如果页面没有进来，是 Search Tool / authority-first / entry-follow 的问题。
- 如果页面进来了但被挡住，是 Page Role Contract / Evidence Consumer Gate 的问题。
- 如果页面进来了、候选句也有了，但不能裁决，就是 point grounding 的问题。
- 当前症状正是第三类：候选句和标题级事实已经有进展，但数值位点没有稳住。

所以这轮先不外部检索。只有在同槽 grounding 完成后，仍然稳定拿不到或消费不了证据，才进入外部资料对标。

## 如果不能，再去外部检索

外部检索触发条件固定为：

- `numeric_target_slots` 已经从 decision_slots 生成，但所有候选证据仍无法命中目标数值。
- 已经排除日期/时间数字污染，仍然无法形成 `numeric_match / numeric_mismatch`。
- 官方/权威页能取回，但表格或标题级事实仍无法结构化。
- 检索成功率有提升但 retrieve 时延不可接受，现有 source health / early stop 无法收住。

到那时再查 2026 最新 hosted search、grounding、fact-checking retrieval、browser-agent 的做法。

## 本轮实现计划

### CA1：生成 numeric_target_slots

在 `evidence.py` 中新增内部目标槽：

- `numeric_target_slots`
- `numeric_claim_value_source`
- `numeric_date_number_excluded`

目标数值优先级：

1. `decision_slots.object`
2. `decision_slots.status_or_result`
3. `core_binding.object_entity`
4. `direct_evidence_need.must_include`
5. `source_strategy.must_have`
6. claim 文本数字回退，但排除日期/时间数字

### CA2：候选句做同槽 grounding

每个 numeric point 必须记录：

- `numeric_slot_grounding_result`
- `numeric_point_block_reason`

同槽通过条件：

- 证据句命中目标数值，或结构化表格点命中目标数值。
- 证据句不只命中日期/时间数字。
- 时间、主体、指标至少不能明显冲突。
- 汇率/中间价类不能被在岸价、离岸价、隔天报价、预测值替代。

### CA3：消费门控保持严格

`solve.py` 现有 Evidence Consumer Gate 不放松。只有 `evidence_page` 或合格结构化点才能推动 direct point；`entry_page/generic_page` 继续只能进入 diagnostics。

## 验收计划

固定用 4 workers 跑：

- `afc_0001`
- `afc_0002`
- `afc_0003`
- `afc_0008`
- `afc_0010`

验收看：

- `numeric_target_slots`
- `numeric_claim_value_source`
- `numeric_date_number_excluded`
- `numeric_slot_grounding_result`
- `numeric_point_block_reason`
- `direct_evidence_gate_result`
- `point_conversion.block_reason`
- `retrieval_effect_review`
- `timing.retrieve`

通过标准：

- `afc_0002` 继续稳定为 `1`。
- `afc_0008 / afc_0010` 不因泛页或日期数字误抬。
- 至少 1 个 numeric claim 的 `claim_value` 不再来自日期/时间数字，而来自 decision slot 或非日期目标数值。
- 如果仍不能裁决，reason 必须明确停在 `numeric_target_not_found`、`numeric_slot_not_grounded`、`time_scope_mismatch` 或 `page/candidate unresolved`，不能回黑盒 recall。

## 项目动机记录

### 分类

证据链、Workflow、测试与回归

### 这次要做什么

把 numeric evidence 从“页面相关”推进到“同一事实位点可比较”。核心动作是让数值裁决优先绑定 decision_slots，而不是从 claim 文本里随手拿第一个数字。

### 动机是什么

现在最危险的问题不是没搜到，而是搜到了以后把错误数字当成 claim_value。日期里的月/日、年份、发布时间、序号都可能污染数值点，导致证据明明相关却不能稳定消费，甚至未来可能误判。

### 对我们的项目有什么实际作用

这会把 AFC 的事实核查从“粗相关检索”推进到“可裁决证据”。尤其是汇率、行情、涨跌幅、基点、得分、距离这类题，必须先解决同槽数值对齐，后面再优化检索才有意义。

### 具体场景又是什么

例如用户问某天人民币兑美元中间价是否为某个数值、是否上调若干基点。页面标题或正文可能同时出现日期、年份、数值、基点。如果系统把日期数字当成 claim_value，它就会错过真正的中间价或涨跌基点。

### 我应该怎么去使用

后续看 debug 时，先看 `numeric_target_slots` 和 `numeric_claim_value_source`。如果来源是 `decision_slot_object` 或 `decision_slot_status_or_result`，说明目标数值绑定正确；如果只能回退到 claim 文本，要检查 `numeric_date_number_excluded` 是否剔除了日期污染。

### 对用户意味着什么

用户会更少遇到“证据页看起来对，但系统说不能裁决”的情况；同时系统不会把同一页面里的旁路数字误当成事实结论。

### 对开发者意味着什么

开发者排查失败时可以明确区分：是目标数值没抽出来、证据句没命中目标数值、时间/指标不对，还是页面本身不合格。这样后续不再盲目改 query。

### 当前结论

现有方案还能继续解，下一步应优先实现 numeric decision_slots 同槽 grounding。

### 下一步建议

实现 CA1-CA3 后立刻用 5 个锚点并发回归；若证据仍不消费，再审计 `numeric_target_slots` 与候选句命中关系，而不是先外部检索。

## 实施状态同步（2026-05-11 晚）

### 基于什么架构

仍基于 `Evidence Page Contract + Page Role Contract + Evidence Consumer Gate + numeric decision_slots grounding`，没有新增 provider，没有碰 `solve_submit.py`，也没有放松泛页/入口页消费门控。

### 实现了什么

本轮已在 `evidence.py` 落地：

- `numeric_target_slots`
- `numeric_claim_value_source`
- `numeric_date_number_excluded`
- `numeric_slot_grounding_result`
- `numeric_point_block_reason`

实现细节是：numeric summarizer 先从 `evidence_need_program.decision_slots`、`core_binding`、`direct_evidence_need.must_include`、`source_strategy.must_have` 读取目标数值；只有这些都没有时，才回退到 claim 文本数字。回退时按数字出现位置剔除日期/时间片段，避免 `4月1日` 里的 `4` 或 `1` 冒充待裁决数值。

### 解决了什么

这轮已经解决一个关键旧问题：`afc_0010 / c2` 不再把日期数字当成 claim value。

最新回归里，`afc_0010 / c2` 已经出现真实可消费 direct point：

- `claim_value = 6.9025`
- `evidence_value = 6.9025`
- `source_type = official`
- `title = 4月1日人民币对美元中间价报6.9025 上调169个基点`
- `numeric_slot_grounding_result.state = passed`
- `target_hits` 同时命中 `6.9025` 和 `169`

同时，`离岸人民币汇率升破6.8` 这类近似但不同指标页被挡在：

- `numeric_point_block_reason = false_friend_metric`

这说明证据层已经不是只会“相关页保留”，而是能把同槽数值事实消费成 direct point。

### 还卡在哪

整体标签还没有因为单个 claim 的 direct point 立刻改变，原因是最终裁决仍要求主问题整体闭合：

- `afc_0010` 仍有其它数值 claim 没有稳定拿到同槽证据。
- `afc_0008` 的部分汇率/牌价 claim 仍主要卡在入口页、其它银行牌价、历史口径不一致。
- `retrieve` 仍偏慢，最新 5 题平均 `retrieve = 69.293s`，比上一轮 `phase4_titlefact6` 的约 `61.232s` 高，但相对第一版 CA rerun 的 `74.442s` 已经收回一部分。

### 现有方案还能不能继续解

能继续解。

这次已经证明 current architecture 能把“标题级事实页 -> evidence_page -> same-slot numeric point”打通。剩余问题不是方案解释不了，而是还需要继续做两件事：

1. 把 `numeric_target_slots` 的优先级再细化，避免辅助对象如 `100美元` 抢在真正指标数值前面。
2. 对汇率/牌价类 claim 增加更强的 metric field binding，例如中间价、在岸价、离岸价、现汇买入、现钞买入、卖出价必须分槽。

### 如果不能，再去外部检索

暂时不需要外部检索。外部检索触发条件保持不变：如果 metric field binding 做完后，官方/权威页仍无法转成可消费点，或者 retrieve 时延无法通过 source health / early stop 收住，再去查 2026 最新 grounding / browser-agent / hosted search 方案。

### 本轮验证

验证命令：

```powershell
python solve.py --input local_dev/tmp/phase4_bmbnbo_anchor_input_sample0410.json --output local_dev/tmp/phase4_ca_numeric_slots2_anchor_sample0410_output.json --debug-output local_dev/tmp/phase4_ca_numeric_slots2_anchor_sample0410_debug.json --perf-output local_dev/tmp/phase4_ca_numeric_slots2_anchor_sample0410_perf.json --workers 4 --no-resume
```

验证输出：

- `local_dev/tmp/phase4_ca_numeric_slots2_anchor_sample0410_output.json`
- `local_dev/tmp/phase4_ca_numeric_slots2_anchor_sample0410_debug.json`
- `local_dev/tmp/phase4_ca_numeric_slots2_anchor_sample0410_perf.json`

结果摘要：

- `afc_0002` 继续稳定为 `1`。
- `afc_0008 / afc_0010` 没有因为泛页或日期数字误抬。
- `afc_0010 / c2` 已有官方 direct numeric point。
- `4月1日` 中的日期数字已从 fallback 目标槽中排除。
- 平均 `retrieve = 69.293s`，时延仍需下一轮收口。

### 当前结论

这轮是实质进展：证据层已经能消费到真正可裁决的数值证据，但整体答案是否翻转还取决于其它 core claim 是否同样闭合。

### 下一步建议

下一轮不再泛化调 query，而是做 `CB：metric field binding`：

- 汇率类分清 `中间价 / 在岸价 / 离岸价 / 现汇买入 / 现钞买入 / 卖出价`。
- 数值点必须同时命中 `target value + metric field + time scope`。
- 命中一个 direct point 后，对同类低价值 rescue/source 做早停，优先把 retrieve 时延收回来。
