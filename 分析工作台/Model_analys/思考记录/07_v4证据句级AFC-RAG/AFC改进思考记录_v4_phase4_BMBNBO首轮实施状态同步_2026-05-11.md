## 2026-05-11 BMBNBO 首轮实施状态同步

### 分类

Workflow / 证据链 / 测试与回归

### 这次要做什么

这轮承接《AFC改进思考记录_v4_phase4_下一步实施计划_BMBNBO_诊断驱动决策与页保留二次收口_v0.1.md》，目标不是再泛补 recall，而是把当前已经拿到的诊断和页级近失信号真正收进主链：

1. 让 `solve.py` 的 decision gate 和最终 reason 真消费 retrieval diagnostics
2. 给 `raw>0 && kept=0` 的 core claim 加一层很窄的二次页保留收口
3. 把 Playwright detail rescue 收紧到更高 ROI 的页型和触发条件

### 动机是什么

前几轮已经证明，当前主问题不再是“完全搜不回来”，而是：

1. 一部分 case 已经能拿回 `raw`
2. 但经常停在 `kept=0`
3. 或者 `kept>0` 后又卡在 `candidate/point`
4. 同时最终 reason 仍会把这些真实阻塞层压扁成笼统的“证据不足”

如果这一步不补，后面继续加 query family 或继续扩救援，都很容易陷入“系统做了更多事，但用户还是只能看到没证据”的假进展。

### 对我们的项目有什么实际作用

这轮的实际价值主要落在三个地方：

1. **判因更真实**
   - `afc_0001 / 0003 / 0010` 这类题不再只会落成黑盒 recall
   - 能明确说出是 access blocked、page not retained、还是 candidate 未闭合

2. **后续优化更可施工**
   - 现在我们终于能把“入口问题”和“消费问题”拆开看
   - 下一轮要补 page keep 还是补 candidate/point，会更有依据

3. **验证效率更高**
   - 新增的 `decision_gate_primary_block / reason_source_layer / second_pass_keep_* / detail_rescue_*`，让我们看单题 debug 时不需要再满链路手翻

### 具体场景又是什么

最典型的就是这几类：

1. `afc_0003`
   - 之前常常只看到“没证据”
   - 这轮能明确落到“访问受阻/反爬因素存在，因此当前主要停在页保留层”

2. `afc_0001`
   - 不再只说泛证据不足
   - 能明确落到“拿回过原始结果，但关键页没有稳定保住”

3. `afc_0008 / 0010`
   - 继续保持 `2`
   - 同时 reason 更像“相关材料有了，但位点/页级保留没闭合”，而不是把问题全丢给 recall

### 我们基于什么架构

继续基于已经落地的主架构推进，没有新增大框架：

1. 受控 Search Tool
2. Playwright 受控救援
3. authority-first 入口
4. 双通道裁决

这轮不是改方向，而是把前面已经做出的信号真正串起来。

### 这轮实际实现了什么

#### 1. `solve.py`

1. `rubric_trigger_gate(...)` 现在开始显式消费：
   - `claim_pipeline_diagnostics`
   - `dominant_pipeline_row`
   - `retrieval_effect_review`

2. 新增并对外挂出：
   - `decision_gate_consumed_diagnostics`
   - `decision_gate_primary_block`
   - `reason_source_layer`

3. 新增 gate 级阻塞识别：
   - `access_blocked_not_evidence_absence`
   - `authority_hit_but_not_retained`
   - `raw_hit_but_page_not_retained`
   - `candidate_present_but_not_decidable`

4. `insufficient_evidence_reason(...)` 开始优先消费：
   - `critical_claim_blocking_state`
   - `retrieval_effect_review`
   - 页保留/候选未闭合诊断

5. `build_claim_pipeline_diagnostics(...)` 新增 claim 级汇总版 `retrieval_effect_review`

#### 2. `retrieval.py`

1. 新增 core-only 二次页保留：
   - `core_second_pass_keep_review_allowed(...)`
   - `maybe_promote_core_second_pass_keep_review(...)`

2. 新增二次页保留 debug：
   - `second_pass_keep_review_used`
   - `second_pass_keep_review_reason`
   - `second_pass_keep_recovered_count`
   - `core_keep_review_block_reason`

3. Playwright detail rescue 收窄为页型受限模式：
   - `should_allow_playwright_detail_rescue(...)`
   - 只对更像 `official_notice / calendar_page / result_page / event_detail / historical_table / current_status_page` 的目标页开放

4. 新增 detail rescue ROI 诊断：
   - `detail_rescue_roi_state`
   - `detail_rescue_target_page_type`
   - `detail_rescue_effect_delta`
   - `detail_rescue_failure_reason`

### 解决了什么

基于 `AFC_sample_data0410` 五个锚点（`afc_0001 / 0002 / 0003 / 0008 / 0010`）的最小验证，这轮已经解决了两件真实问题：

#### A. reason 不再只会塌成泛“没证据”

现在至少已经出现下面这些更真实的落点：

1. `afc_0001`
   - 明确落到：`raw_hit_but_page_not_retained`
   - 最终 reason：已经拿回过原始结果，但关键页还没有稳定保住

2. `afc_0003`
   - 明确落到：`access_blocked_and_unresolved`
   - 最终 reason：主阻塞包含访问受阻/反爬因素，不再被写成纯 recall

3. `afc_0008 / 0010`
   - 保持 `2`
   - 同时 reason 已能把“不可直裁材料”和“页面保留未闭合”说清楚

#### B. 核心标签稳定性没有被误伤

1. `afc_0002` 继续稳定为 `1`
2. `afc_0008 / 0010` 没有被误抬

### 当前还卡在哪

这轮没有把“关键证据成功率”真正打穿，主瓶颈仍然很清楚：

#### 1. 二次页保留机制已经接上，但还没有真正救回本轮锚点

从本轮 sample0410 debug 看：

1. `second_pass_keep_recovered_count` 仍基本为 `0`
2. 说明我们已经把“二次页保留合同”接进主链
3. 但当前阈值和触发面还没有把关键 near-miss 页真实保下来

也就是说，这轮把“该在哪补”钉准了，但“补回来多少”还不够。

#### 2. Playwright 仍然主要改善在入口诊断，不是 detail ROI 兑现

这轮 sample0410 中：

1. `afc_0001 / 0010` 出现了 `playwright_rescue_succeeded`
2. 但更多仍体现在 `search_result_recovered`
3. `detail_rescue_roi_state` 还没有稳定长成“候选句增长/页保住”的强信号

说明 rescue 还在“入口层留痕强于消费层兑现”的状态。

#### 3. 主阻塞已经更像 `raw -> kept -> candidate`

sample0410 回看里最值得注意的是：

1. `afc_0001`：`raw>0, kept>0, ans>0`，但停在 `candidate_present_but_not_decidable`
2. `afc_0003`：`raw>0, kept=0`
3. `afc_0010`：部分 claim 已到 `retrieval_readiness`，但另一些仍停在 `raw_hit_but_page_not_retained`

所以当前真实主瓶颈已经不是一句“检索入口全挂了”能概括的。

### 现有方案还能不能继续解

还能继续解，而且下一步仍建议先在现有方案内迭代，不要马上换大框架。

原因有三个：

1. 这轮已经证明 diagnostics 能带来更真实的决策层解释
2. `afc_0001 / 0003` 这类 case 的主阻塞已经被拆到了可施工层
3. `afc_0002` 继续稳定，说明这轮没有破坏已有 closure 通道收益

换句话说，现在不是“方向错了”，而是“页保留二次收口和 kept->candidate 消费还没兑现成效果”。

### 这对用户意味着什么

对最终使用者来说，这轮最大的变化不是标签本身，而是系统开始更像一个诚实的 fact-checker：

1. 拿不到证据时，更能区分是访问受阻、页没保住，还是候选句没闭合
2. 不会把所有失败都混写成一句“没有证据”
3. 这能减少误导性的过度自信，也更方便后续人工接管

### 这对开发者意味着什么

对开发者来说，这轮最大的收益是“可施工性”变强了：

1. 现在看 debug，可以直接知道下一步该补：
   - source access
   - page keep
   - candidate utility
   - point conversion

2. 不需要再手工从长日志里猜“到底卡在哪一层”

3. 后续做 AB 对比时，可以直接围绕：
   - `decision_gate_primary_block`
   - `second_pass_keep_recovered_count`
   - `detail_rescue_roi_state`
   来看有没有真进展

### 当前结论

这轮 **完成了“诊断进判决层”的首轮闭环**，也把“页保留二次收口”和“窄版 detail rescue”正式接到了主链上。

但它还 **没有完成“关键证据成功率打通”**。当前更准确的结论是：

1. 解释性明显变强了
2. 标签稳定性守住了
3. 主瓶颈已经从黑盒 recall 进一步拆到了 `raw -> kept -> candidate`
4. 真正的效果提升还需要下一轮把二次页保留和 kept->candidate 消费做强

### 和前面文档的关系

#### 和《AFC改进思考记录_v4_phase4_架构合理性审计与外部对标_v0.1.md》的关系

那份文档回答“方向对不对”。  
这份状态同步回答“沿这个方向实现后，这轮到底打到了哪一层，还没打到哪一层”。

#### 和《AFC改进思考记录_v4_phase4_下一步实施计划_BMBNBO_诊断驱动决策与页保留二次收口_v0.1.md》的关系

那份是施工计划。  
这份是该计划的首轮实施回执，告诉我们：

1. 哪些已经落地
2. 哪些已经开始起作用
3. 哪些还只是骨架，尚未产生真实 throughput 提升

### 下一步建议

下一轮建议不要再扩新的入口方案，直接收口到两个更实的方向：

1. **页保留效果层**
   - 专门审 `raw>0 && kept=0` 的 near-miss 页
   - 围绕 `core_keep_review_block_reason` 做窄放宽

2. **kept -> candidate 消费层**
   - 优先处理 `candidate_present_but_not_decidable`
   - 尤其是 `afc_0001` 这种已经拿到候选句但没闭合的 case

如果这两层继续迭代后，`second_pass_keep_recovered_count` 和 `detail_rescue_roi_state` 仍长期没有正进展，再进入下一轮外部检索与架构对标。
