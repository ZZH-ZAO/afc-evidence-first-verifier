## 2026-05-10 AO/AP/AQ 首轮实施状态同步
### 分类

证据链路 / Workflow / 测试与回看

### 这次要做什么？

这轮按 `AO -> AP -> AQ` 的顺序，继续沿双通道保真主线往前收：

1. 先把 supporting structured detail retained-but-unresolved 的 gap 拆细
2. 再把 weak direct candidate 往真正可直裁候选推
3. 最后把 access / rescue / recall 三类阻塞显式拆开

对应主改仍集中在 `solve.py`：

1. 细化 logic refutation 未闭合状态
2. 补候选句 promotion 的 basis / block diagnostics
3. 补 access path / rescue attempt diagnostics
4. 同步收 reason 消费，防止又回成黑盒 recall

### 动机是什么？

`AL/AM/AN` 之后，真实问题已经不是“网页都找不回来”，也不是“只要继续抬 directness 分数就行”，而是三层瓶颈混在一起：

1. 一批 structured detail 已经保住了，但没法看出到底卡在“没 logic point”还是“logic point 不可消费”
2. 一批网页 case 已经跑到 `kept -> candidate`，但最强句子还是弱候选
3. 还有一批 case 明明是 access / rescue 问题，却总被最后写成泛 recall

所以这轮不是继续扩链，而是把“卡在哪一层”说清楚。

### 对我们的项目有什么实际作用？

这轮做完之后，系统第一次能更稳定地区分三种不同的未完成状态：

1. `structured detail` 已保留，但逻辑闭合还差哪一步
2. 页面和候选句已有，但为什么还没成为 `direct_candidate`
3. 到底是 provider 没召回、外站被拦、还是正文读不下来

这会直接减少后续优化时的误判：

- 不会再把所有 `2` 都当 recall 问题
- 不会再把所有弱候选句都当成同一种 `candidate_not_direct`
- 不会再把 retained structured detail 只剩一个粗糙的 unresolved 标签

### 具体场景又是什么？

这轮最典型的几个样本是：

1. `afc_0002`
   - 继续稳定为 `1`
   - `logic_refutation_state = stable_logic_refutation_ready`
   - 说明 supporting structured detail 的逻辑闭合通道还在，而且没被新改动冲掉

2. `afc_0007`
   - 仍为 `2`
   - 但已经能明确看到：
     - detail 已保留
     - 当前仍未形成稳定逻辑反证
   - 说明 `retained-but-unresolved` 不再是黑盒

3. `afc_0001`
   - 中途一度被 supporting date detail 误抬到 `1`
   - 根因是旧的 `date_mismatch` detail refutation gate 太松
   - 收紧后已回到 `2`
   - 这说明 AO 这轮不仅补了新分层，也顺手收住了 supporting date detail 的误伤边界

### 我应该怎么去使用？

后面回看这类 case，建议优先看三组字段：

1. supporting detail 侧
   - `structured_detail_retained`
   - `logic_refutation_state`
   - `logic_refutation_closure_stage`
   - `logic_refutation_block_reason`

2. candidate promotion 侧
   - `direct_candidate_promotion_basis`
   - `candidate_promotion_block_reason`
   - `candidate_slot_coverage_summary`

3. access / rescue 侧
   - `access_path_state`
   - `access_block_source`
   - `rescue_attempt_state`

如果能明确回答：

- detail 是不是保住了
- 逻辑点有没有、同不同题、稳不稳定
- 候选句是不是已经打到关键位点
- 是 access 问题还是 recall 问题

那这轮机制就算真的起效了。

### 对用户意味着什么？

对最终使用系统的人来说，这轮最直接的变化不是标签突然大跳，而是 reason 和 debug 变得更像真实工程状态：

- 会明确告诉你“细节保住了，但逻辑还没闭合”
- 会明确告诉你“候选句打到了关键位点，但还不够直裁”
- 会明确告诉你“其实是外站访问受阻，不是世界上没有证据”

这会让后续每一轮优化更可控，也更容易判断是该补网页链、补句层，还是补 detail 闭合。

### 对开发者意味着什么？

对开发侧来说，这轮确认了三件很重要的事：

1. `structured detail` 的 unresolved 不能只留一个总标签，必须拆成 closure stage
2. weak candidate 的问题不能只看最终 `candidate_not_direct`，还要看 promotion basis 和 block reason
3. `provider_recall` 不能继续包办所有前段失败，不然 access / rescue 永远看不清

另外，这轮也证明了 supporting detail 的 `date_mismatch` 直裁门槛必须更保守，尤其是 supporting `date_fact / schedule_fact` 场景，不能让非官方旧新闻页轻易顶掉主链判断。

### 当前结论

这轮首轮落地已经完成，并做了最小验证。

验证命令：
`python .\\solve.py --input .\\output\\afc_phase4_aiajak_sample_subset_input.json --output .\\output\\afc_phase4_aoapaq_sample_subset_results.json --debug-output .\\output\\afc_phase4_aoapaq_sample_subset_debug.json --perf-output .\\output\\afc_phase4_aoapaq_sample_subset_perf.json --workers 1 --no-resume`

验证后的真实状态：

1. 已确认生效的部分
   - `afc_0002` 继续稳定为 `1`
   - `afc_0007` 这类 case 已能显式落出 retained-but-unresolved
   - `0001 / 0003 / 0008 / 0010` 的 access / recall / candidate / detail 状态分层更清楚

2. 这轮顺手守住的边界
   - `afc_0001` 已从误抬的 `1` 收回到 `2`
   - 没有新增 `unsupported structured detail -> 1`

3. 仍然存在的主瓶颈
   - `0001 / 0003 / 0007` 仍偏前段 access / recall / filter
   - `0008 / 0010` 仍偏后段 weak candidate / same-slot conversion

### 下一步建议

下一轮建议继续固定按下面顺序推进：

1. 先收 `same_topic_logic_point_unstable`
   - 明确到底还差哪种闭合条件

2. 再收 weak candidate 的真晋级
   - 重点继续压 `slot_hit_but_indirect`
   - 让命中 `subject + time_scope + metric/status` 的句子更稳定升到 `direct_candidate`

3. 最后继续补 access 侧最终话术一致性
   - 让 `source_access_blocked`
   - `provider_recall_insufficient`
   - `page_access_or_read_blocked`
   在最终 reason 中更稳定地区分出来
