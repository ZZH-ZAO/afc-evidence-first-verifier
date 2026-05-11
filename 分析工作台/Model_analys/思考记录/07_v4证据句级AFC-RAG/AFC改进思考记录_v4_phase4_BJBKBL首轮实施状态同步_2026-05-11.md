# AFC v4 Phase4 BJBKBL首轮实施状态同步

## 2026-05-11 关键证据成功率首轮实施同步

### 分类

Workflow / 证据链 / 测试与回归

### 基于什么架构

这一轮严格基于现有四层主架构推进，没有新增 provider，也没有引入黑箱终判：

1. 受控 Search Tool
2. Playwright 受控救援
3. authority-first 入口
4. 双通道裁决

这意味着本轮目标不是继续泛泛讨论“为什么卡住”，而是直接在现有主链里验证：关键证据 throughput 能不能被真正往前推。

### 实现了什么

这轮代码层实际落了三类改动。

1. 在 `retrieval.py` 增加关键证据页保留复核
   - 新增 `KEY_EVIDENCE_KEEP_PAGE_TYPES`
   - 新增 `should_soft_keep_key_evidence_page(...)`
   - 新增 `annotate_key_evidence_page_keep(...)`
   - 并接入 official discovery 与常规 search 两条页过滤链

2. 在 `retrieval.py` 补齐 Playwright rescue 的 claim 级成功/失败信号
   - `rescue_progress_delta`
   - `rescue_success_gate`
   - `rescue_target_page_type`
   - `rescue_non_roi_reason`
   - 同时扩展 `infer_playwright_rescue_state(...)` 的成功识别条件

3. 在 `solve.py` 把关键 claim 预算优先级和 retrieval 新信号真正消费起来
   - `claim_budget_priority`
   - `core_claim_budget_reserved`
   - `supporting_claim_deprioritized`
   - `critical_claim_blocking_state`
   - 并把 `page_keep_review_state / kept_progress_from_raw / rescue_success_gate` 等字段并入 `claim_pipeline_diagnostic(...)` 与 `insufficient_evidence_reason(...)`

### 解决了什么

这轮确实解决了两个之前看不清的问题。

1. 关键 core claim 不再只能黑盒停在“没搜到”
   - 例如 `afc_0001` 的核心 claim，已经能从 baseline 的 `provider_recall/raw=0`
   - 推进到首轮实现版里的 `retrieval_filter/raw>0/kept=0`
   - 说明入口命中不是完全没有起色，主瓶颈开始收敛到 page retention

2. 关键阻塞状态更真实
   - 不再只是泛 recall
   - 而是能明确落到 `raw_hit_but_page_not_retained`
   - 或 `access_blocked_and_unresolved`
   - 或 `candidate_present_but_not_decidable`

另外，锚点稳定性守住了：

- `afc_0002` 继续稳定为 `1`
- `afc_0008 / afc_0010` 没有误抬

### 还卡在哪

这轮还没有达到“关键证据成功率打通”的停点，卡点也很明确。

1. 还没有稳定打出 `raw>0 && kept>0`
   - 首轮实现版里，`afc_0001 / 0003` 的关键 core claim 主要仍停在 `raw>0 && kept=0`
   - 说明入口改善后，真正的主瓶颈已经收敛到“页保不住”

2. Playwright rescue 还没有稳定变成高 ROI 能力
   - 首轮实现版没有产出稳定的 `playwright_rescue_succeeded`
   - 我做过一次更激进的 source contract 对照试验，虽然短暂打出过一次 rescue succeeded
   - 但它同时把 `afc_0001 / 0003` 打回了更早的 recall 层，所以不能收进主线

3. 时延还没有收住
   - fresh baseline 的 `retrieve` 平均耗时约 `19.436s`
   - 首轮实现版升到约 `31.384s`
   - 说明这轮没有达到“成功率更高且用时更短”的停点

### 现有方案还能不能继续解

还能继续解，而且下一轮仍然优先留在现有架构内做，不需要立刻切到新的外部 hosted search 方案。

原因是：

1. 我们已经看到 `raw=0 -> raw>0` 的真实推进
2. 当前失败仍然可以被现有框架直接解释为
   - page retention 过严
   - rescue ROI 不稳
   - core claim throughput 不够集中
3. 更激进的 source 全局重排已经做过小实验，收益不稳且副作用明显，说明下一轮应该做更窄、更稳的局部增强

### 如果不能，再去外部检索

目前还没到必须重新外部对标的点。

只有在下面条件出现时，才触发下一轮外部检索：

1. `raw>0 && kept=0` 在 page retention 增强后仍几乎不改善
2. Playwright 在更窄 trigger 下仍完全救不成
3. core-first 预算继续收紧后，关键 claim 仍没有 throughput 提升
4. 成功率略升，但 retrieval 时延继续明显恶化

### 当前结论

这轮不是“关键证据成功率已经打通”的一轮，而是把主瓶颈继续从黑盒 recall 压缩到：

- page retention
- rescue ROI
- core throughput

也就是说：

- 架构方向没有走偏
- 代码已经真实落地
- 锚点稳定性守住了
- 但关键停点还没有达到

### 下一步建议

下一轮不再做 source family 的全局激进重排，而是更聚焦地做两件事：

1. 只针对 `raw>0 && kept=0` 的 core claim 做 page retention 二次收口
   - 只放宽“页型对、位点半对、但 directness 不够”的 near-miss 页面
   - 不碰明显噪声页

2. 把 Playwright rescue 缩成更窄的 detail-read 场景
   - 不再追求“多场景都能救”
   - 先追求在一类 detail blocked case 上稳定打出一次高 ROI 成功

### 和前面文档的关系

这份文档不是新的总方案文档，而是对当前实现轮次的真实状态同步。

它和前面文档的关系是：

1. 相对 `AFC改进思考记录_v4_phase4_下一步实施计划_BJBKBL_关键证据成功率打通_v0.1.md`
   - 那份文档负责定义这一轮要做什么
   - 这份文档负责同步这一轮实际做成了什么、没做成什么

2. 相对 `AFC改进思考记录_v4_phase4_入口层审计与外部检索架构对标_2026-05-11.md`
   - 那份文档负责解释大方向和外部架构参照
   - 这份文档负责回答：在不换架构的前提下，本轮代码推进后的真实效果如何

3. 相对 `AFC改进思考记录_v4_phase4_下一步实施计划_BGBHBI_效果层首轮成功率与时延一起收口_v0.1.md`
   - 那份文档是效果层首轮的施工计划
   - 这份文档是 BJBKBL 首轮实施后的落地复盘
