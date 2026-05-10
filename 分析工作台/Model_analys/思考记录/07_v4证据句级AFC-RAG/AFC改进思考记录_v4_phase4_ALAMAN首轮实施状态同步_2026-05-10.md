## 2026-05-10 AL/AM/AN 首轮实施状态同步

### 分类

证据链路 / Workflow / 测试与回看

### 这次要做什么？

这轮按 `AL -> AM -> AN` 的顺序，先把 supporting structured detail 的逻辑反证通道保回来，再让它和网页 direct evidence 通道稳定共存，最后确认网页主链没有因此被误伤。

对应主改仍收在 `solve.py`：

1. 补 supporting structured detail 的 claim surface 保留
2. 给 high-risk detail claim 补逻辑反证诊断
3. 让最终 reason 和聚合开始消费这组 detail 信号

### 动机是什么？

`AI/AJ/AK` 之后暴露出的真实问题已经很明确：

1. 网页证据链在一部分 fact-like claim 上已经能跑到 `raw -> kept -> candidate`
2. 但 `afc_0002` 这种原本能靠“回答自己前后算不通”判错的 case，又被句层主导逻辑盖过去了

也就是说，这轮不是简单补 recall，而是要把两种本来就该共存的可裁决错误重新拆开：

- 网页 direct evidence 反证
- structured detail 逻辑反证

### 对我们的项目有什么实际作用？

这轮做完后，系统第一次把“回答里自己就能闭合出错的细节”重新接回主判定链，而且不是靠宽松抬 `unsupported structured detail -> 1`，而是靠：

1. 先把 detail claim 保住
2. 再让 `computed` 逻辑点只在同主题 detail 上生效
3. 最后由 `secondary_detail_direct_refutation` 稳定消费

这样后面网页 evidence chain 可以继续推进，但不会再把原本已经可裁决的 structured detail 错误挤没。

### 具体场景又是什么？

最典型的就是 `afc_0002`：

回答里明明写了：

- 黄蜂赢球
- 赛后战绩变化
- 本赛季双方常规赛交锋已全部结束，总战绩为 `2胜2负`

而当前已有 `computed` 逻辑线索已经能稳定推出：

- 此前两次各胜一场 = `1-1`
- 再加上本场一方赢球
- 总计应为 `2-1`
- 不是 `2-2`

以前这一条 detail 在 claim surface 里会丢，或者虽然有句层进展，但没被 detail 通道接住；这轮把这条链真正打通了。

### 我应该怎么去使用？

后面看这类 case，优先多看两组字段：

1. `evidence_first_audit.high_risk_detail_claims`
   - `structured_detail_retained`
   - `logic_refutation_candidate`
   - `logic_refutation_basis`
   - `logic_refutation_gap_reason`

2. `claim_pipeline_diagnostics.items`
   - supporting detail 是否已经前移到 `evidence_decidable_detail_error`
   - 有没有还停在 `provider_recall / retrieval_readiness`

如果看到：

- detail claim 已保留
- `logic_refutation_candidate = true`
- 且 final policy 走到 `secondary_detail_direct_refutation`

那就说明这轮双通道保真已经真正生效。

### 对用户意味着什么？

对最终使用系统的人来说，这轮最直接的变化是：

- 系统不再只会说“网页句子不够 direct”
- 它开始重新识别“你回答里这个细节自己就和前文算不拢”

这会让 `1` 的来源更真实，也更容易区分：

- 是网页直接反证
- 还是回答内部细节逻辑闭合后出错

### 对开发者意味着什么？

对开发侧来说，这轮确认了两个关键事实：

1. `structured detail` 的 claim surface 必须主动保留，不能完全指望大抽取自己记住
2. `computed` 逻辑点必须有严格主题 gate，不然会误伤别的数值 detail

所以这轮虽然恢复了 `0002 -> 1`，但也顺手把“逻辑反证不能泛化成所有 numeric detail”的边界收清楚了。

### 当前结论

这轮首轮落地已经完成，并做了最小验证。

验证命令：

`python .\\solve.py --input .\\output\\afc_phase4_aiajak_sample_subset_input.json --output .\\output\\afc_phase4_alaman_sample_subset_results.json --debug-output .\\output\\afc_phase4_alaman_sample_subset_debug.json --perf-output .\\output\\afc_phase4_alaman_sample_subset_perf.json --workers 1 --no-resume`

验证后得到的真实状态：

1. 已经生效的部分
   - `afc_0002` 恢复为 `1`
   - 且原因回到真正的 supporting structured detail 逻辑反证
   - `logic_refutation_candidate / logic_refutation_basis` 已能稳定透传到 debug

2. 这轮刻意守住的边界
   - 交锋总战绩的 `computed` 逻辑点不再误伤“赛后战绩 40胜36负”这类别的 detail
   - 没有新增 `unsupported structured detail -> 1`

3. 仍然存在的主瓶颈
   - `afc_0001 / 0003 / 0007` 仍然经常停在 recall 或 access
   - `afc_0008 / 0010` 仍主要卡在句层 directness 或同位点 conversion

### 下一步建议

下一轮建议继续收三件事：

1. 先把 `structured detail retained but unresolved` 的 gap reason 再做细
   - 区分“detail 已保留但没拿到逻辑点”
   - 和“逻辑点有了但还没稳定闭合”

2. 再继续推网页主链的 weak direct candidate 晋级
   - 重点仍是 `slot_hit_but_indirect -> direct_candidate`

3. 最后继续补 access / rescue 稳定性
   - 让 `0001` 这类 case 少被环境阻塞拉回纯 recall
