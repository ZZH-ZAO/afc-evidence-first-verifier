## 2026-05-11 BPBQBR 下一步实施计划
### 分类

Workflow / 证据链 / 测试与回归

### 这次要做什么？
这轮承接 `BMBNBO` 的实施状态，不再继续泛补 recall，也不再先换外部检索架构，而是固定收口到两层最真实的瓶颈：

1. `BP`：把 `raw>0 && kept=0` 的 core near-miss 页真正救回来
2. `BQ`：把 route / numeric / schedule 这类强页型的二次页保留做成可命中的效果层
3. `BR`：把 `kept>0 && candidate>0` 但卡在 same-slot 前的 case 往前推一步

主改仍只落在 `retrieval.py` 和 `solve.py`，不扩 provider，不换 `solve_submit.py`，不引入 LLM 终判。

### 动机是什么？
上一轮最关键的价值，不是标签突然变好了，而是我们终于把真实瓶颈看清了：

1. 不是“完全搜不回来”
2. 而是“搜回来了但没保住”
3. 或者“保住了但没转成同一事实位点下可裁决的句子/点”

如果这时候继续泛扩 query 或泛扩救援，系统会继续更忙，但关键证据成功率不一定真涨。  
所以这轮要顺着已经出现的弱进展继续打，不再重新开一个更大的框架。

### 对我们的项目有什么实际作用？
这轮的实际价值很直接：

1. 让 `afc_0001 / 0003 / 0010` 这类 case 不只是“知道卡住了”，而是开始真的多保下一些关键页
2. 让 `afc_0008 / 0010` 这种已经有候选句的 case，别永远停在“相关但不可裁决”
3. 让后续判断“该补入口、补页保留，还是补 candidate/point”更有依据，不会回到黑盒 trial-and-error

### 具体场景又是什么？
这轮主要对应三类真实场景：

1. `afc_0001`
   - 已经拿回过原始结果
   - 但关键页没稳定保住，或保住后候选句仍卡在 opening / same-slot

2. `afc_0003`
   - route 相关页不是完全没有
   - 但常停在 `kept=0`，说明 route 页型、关系句、复核阈值还没真正打通

3. `afc_0010`
   - 有些 claim 已经进入 `retrieval_readiness`
   - 但 top candidate 仍不够可裁决，说明 page->candidate->point 的消费层还偏保守

### 我们基于什么架构？
继续基于已经落地的主架构推进，不换大方向：

1. 受控 Search Tool
2. authority-first 入口
3. Playwright 受控救援
4. 双通道裁决
5. 诊断驱动的 retrieval / decision 消费

这一轮不是改架构，而是在现有架构内把“页保留效果层”和“same-slot 消费层”打得更实。

### 当前已经实现了什么？
截至 `BMBNBO`，系统已经具备下面这些基础：

1. `solve.py`
   - `decision_gate_consumed_diagnostics`
   - `decision_gate_primary_block`
   - `reason_source_layer`
   - `retrieval_effect_review`

2. `retrieval.py`
   - `second_pass_keep_review_used`
   - `second_pass_keep_review_reason`
   - `second_pass_keep_recovered_count`
   - `core_keep_review_block_reason`
   - `detail_rescue_roi_state`

3. 样本回看结论
   - `afc_0002` 稳定为 `1`
   - `afc_0008 / 0010` 没有误抬
   - `afc_0001 / 0003` 已经不再只会黑盒回到“没搜到”

### 已经解决了什么？
前面几轮已经解决了三件很重要的事：

1. 把入口失败、页没保住、候选句没闭合这三层拆开了
2. 证明当前架构方向没有跑偏，问题不是“整套方案错了”
3. 证明当前最值得继续打的，不是再加 recall，而是 `raw -> kept -> candidate`

### 还卡在哪？
当前还卡在三个非常具体的位置：

1. `second_pass_keep_recovered_count` 还几乎没有动起来
   - 说明二次页保留已经接上了
   - 但真正命中的 near-miss 类型还不够准

2. route 页型还不够吃到 core second-pass
   - `afc_0003` 这类 case 说明 route 页虽然进来了，但 route-specific 的 page type / relation sentence 还不够容易被保住

3. `candidate_present_but_not_decidable` 还在堆积
   - 说明 top candidate 已经出现
   - 但 same-slot review 还太弱，很多“差一点直答”的句子没有被稳定消费

### 现有方案还能不能继续解？
还能，而且这一轮仍然应该先在现有方案里继续解。

判断依据是：

1. `raw>0` 已经出现过，说明入口不是全坏
2. `kept>0` 也已经出现过，说明并不是所有页都被策略性拒绝
3. `candidate>0` 甚至 `candidate_present_but_not_decidable` 已经出现，说明并不是完全没有可消费材料

所以当前不是“必须换 hosted search 才有路”，而是“现有链路里已经拿到的弱进展还没被真正吃干净”。

### 如果不能，再去外部检索
只有满足下面任一条件，才再进入下一轮外部架构对标：

1. 二次页保留放宽后，`second_pass_keep_recovered_count` 仍长期为 0
2. route / numeric 强页型仍几乎全部保不下来
3. same-slot 消费增强后，`candidate_present_but_not_decidable` 仍完全不下降
4. 成功率略升，但 retrieval 时延明显恶化到不可接受

### 这轮实际要实现什么？
#### BP：core near-miss 页保留效果层

主改 `retrieval.py`。

实现要求：

1. `core_second_pass_keep_review` 不再只吃非常窄的一类 page type
2. 对强页型做分层阈值：
   - `quote_page / calendar_page / historical_table / official_notice / result_page / event_detail`
   - 允许更低但仍可控的 retention / utility 阈值
3. 对 `numeric_fact / date_fact / schedule_fact / event_result`，显式消费：
   - `answer_candidate_quality_score`
   - `evidence_contract_status`
   - `structured_point_contract_status`
   - `opening slot` 等关键位点

新增目标不是简单放松，而是更精准地把“差一点可用”的页保下来。

#### BQ：route 页保留二次收口

主改 `retrieval.py`。

实现要求：

1. `route_fact` 正式进入 core second-pass 可消费页型
2. 允许：
   - `route_analysis_page`
   - `route_passage_page`
   - `mixed_page`
   作为 route near-miss 二次复核对象
3. route 复核时显式消费：
   - `route_sentence`
   - `route_rerank_score`
   - `relation_evidence`
   - `answerability`
4. `afc_0003` 至少要能更稳定进入“页保留后再看 candidate”的轨道，而不是永远停在 filter 层

#### BR：same-slot 候选消费增强

主改 `solve.py`。

实现要求：

1. `candidate_decision_useful_score(...)` 开始更强地奖励：
   - 强页型候选
   - slot 覆盖足够的 near-direct 句子
   - `date_role_mismatch / result_granularity_mismatch / related_but_not_assertive` 这类“差一点同位点”的候选

2. `infer_slot_review_outcome(...)` 不再只把它们模糊归成弱候选
   - 对 strong page + same-slot near miss 的情况，显式进入 `same_slot_review_blocked` 轨道

3. 目标不是直接放宽终判，而是让 top candidate 更像真正可裁决候选，而不是背景评论句

### 这轮解决什么问题？
如果实施顺利，这轮应该解决下面这些问题：

1. `raw>0 && kept=0` 不再一动不动
2. `route_fact` 不再天然吃亏于二次页保留
3. `candidate_present_but_not_decidable` 至少会更明确地收缩到少数真实不可裁决的情况

### 我们应该怎么用这轮能力？
这轮完成后，回看 debug 时重点看：

1. `second_pass_keep_recovered_count`
2. `core_keep_review_block_reason`
3. `page_keep_review_state`
4. `slot_review_outcome`
5. `point_consumption_state`
6. `candidate_utility_score`

判断顺序固定为：

1. 是否已经 `raw>0`
2. 是否已经 `kept>0`
3. 若 `kept>0`，top candidate 是否进入 same-slot review 轨道
4. 若仍失败，失败是页保留问题还是 point conversion 问题

### 这对用户意味着什么？
对最终使用者来说，这轮最重要的不是系统看起来更忙，而是：

1. 更容易真的拿回关键页
2. 更容易把“差一点”的证据变成可解释的阻塞，而不是空泛无证据
3. 关键 case 的失败理由会更贴近真实链路，而不是继续模糊化

### 这对开发者意味着什么？
对开发者来说，这轮最大的意义是把下一步调优面进一步缩小：

1. 如果 `second_pass_keep_recovered_count` 起来了，说明页保留方向对
2. 如果 `slot_review_outcome` 更常进入 blocked/same-slot 轨道，说明候选消费开始起作用
3. 如果两边都不动，再去外部检索新的 search/grounding 架构才有必要

### 当前结论
当前最值得继续推进的，不是换一整套检索架构，而是把现有链路里已经出现的弱进展彻底吃透。

更具体地说：

1. 架构方向没错
2. 已经实现的诊断也不是摆设
3. 现在真正缺的是页保留效果层和 same-slot 消费层的兑现

### 和前面文档的关系
#### 和《入口层审计与外部检索架构对标》的关系

那份文档回答的是“当前主架构为什么仍值得继续走”。  
这份文档回答的是“既然主架构还值得走，下一轮最该在哪两层继续打”。

#### 和《BDBEBF Search Tool 协议化与 Playwright 受控救援》的关系

`BDBEBF` 解决的是协议层和入口层。  
这份文档解决的是协议层之后的效果兑现层。

#### 和《BMBNBO 诊断驱动决策与页保留二次收口》的关系

`BMBNBO` 是把诊断接进决策，并搭起二次页保留骨架。  
这份文档是基于 `BMBNBO` 的真实 debug 结果，把下一轮聚焦到：

1. 让二次页保留真的命中
2. 让 same-slot 候选真的开始消费

### 下一步建议
下一步固定按下面顺序执行：

1. 先改 `retrieval.py`，让 core / route second-pass keep 真正更容易命中
2. 再改 `solve.py`，让 same-slot near miss 候选更容易进入 blocked-but-useful 轨道
3. 然后跑 `AFC_sample_data0410` 五个锚点最小回归
4. 如果 `second_pass_keep_recovered_count` 和 `candidate_present_but_not_decidable` 仍完全不动，再进入下一轮外部方案补架构
