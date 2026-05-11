## 2026-05-11 BSBTBU 下一步实施计划

### 分类

Workflow / 证据链 / 测试与回归

### 这次要做什么？

这轮承接 `BPBQBR` 的实施状态，不再继续泛补 recall，也不再优先扩入口层，而是固定打两件最贴近“证据真的能被消费”的事：

1. `BS`：把 `structured_noise_high_penalty` 从一刀切 hard-drop 拆成“真噪声”与“可复核强结构页”
2. `BT`：让 strong structured page / near-miss kept page 更容易真正进入 `kept>0`
3. `BU`：让 `solve.py` 不只说“有弱候选”，而是显式承接“来自已保留页的候选消费进展”

主改仍只落在 `retrieval.py` 和 `solve.py`，不加 provider，不碰 `solve_submit.py`，不引入新的 LLM 终判。

### 动机是什么？

上一轮最重要的收获不是标签变好了，而是我们终于把主瓶颈进一步压缩清楚了：

1. 不是纯入口问题
2. 不是纯 Playwright 问题
3. 也不只是 same-slot 太保守
4. 而是很多 case 已经 `raw>0`，但页在 `structured_noise_high_penalty / page_shape_hard_drop` 被整批打掉
5. 即便有候选句，系统也更像在记录“看见了”，还没有把“来自已保留页的候选进展”明确消费出来

如果这时继续泛扩 query、泛放 source，系统会更忙，但未必更接近关键证据成功率打通。

### 对我们的项目有什么实际作用？

这轮的实际价值很直接：

1. 把 `raw>0 && kept=0` 的一部分真实 near-miss 强页救回来
2. 让 debug 和 reason 能更诚实地表达“不是没证据，而是已经进到 kept/candidate 但还没闭合”
3. 给下一轮判断“该继续修页保留，还是该修 point conversion”提供更硬的依据

### 具体场景又是什么？

当前最典型的是两类：

1. `afc_0001`
   - 已经能拿回原始结果
   - 但大部分结果是日历噪声页，被 `structured_noise_high_penalty` 打掉
   - 这类 case 需要继续维持 hard-drop 的严格性，不能误放垃圾页

2. `afc_0010`
   - 已经出现高页分、强结构形态的 numeric page
   - 但仍可能因为 entity hit / structured penalty 口径过死，被当成 hard drop
   - 这类 case 需要把“可复核强页”从 hard-drop 口径中拆出来

3. `afc_0003`
   - route 仍然脆弱
   - 但本轮优先级不是再开 route 新框架，而是先把“保留下来之后能否真实消费”这条链收口

### 我们基于什么架构？

继续基于已经落地的主架构推进，不换大方向：

1. 受控 Search Tool
2. authority-first 入口
3. Playwright 受控救援
4. 双通道裁决
5. page keep / candidate / point 三层消费链

这轮不是改架构，而是在现有架构内把“页级 hard-drop 合约”和“候选消费兑现层”打得更准。

### 当前已经实现了什么？

截至 `BPBQBR`，系统已经具备这些骨架：

1. `retrieval.py`
   - `second_pass_keep_review_used`
   - `second_pass_keep_recovered_count`
   - `page_keep_review_state`
   - `core_keep_review_block_reason`
   - `soft_keep_structured_metric_table_candidate`
   - `soft_keep_claim_aligned_fact_page`

2. `solve.py`
   - `candidate_utility_score`
   - `slot_review_outcome`
   - `point_consumption_state`
   - `candidate_present_but_not_decidable`

3. 样本层面
   - `afc_0002` 仍稳定为 `1`
   - `afc_0008 / 0010` 没有误抬
   - `afc_0001 / 0003 / 0010` 不再只会黑盒落回“没搜到”

### 已经解决了什么？

前面几轮已经解决了三件重要的事：

1. 入口失败、页保留失败、候选消费失败已经被拆层
2. `same-slot` 这层开始更诚实，不再把所有 near-miss 都抹平成 `unresolved`
3. 证明当前最该继续打的不是 broad recall，而是 `raw -> kept -> candidate` 的兑现

### 还卡在哪？

当前还卡在两个非常具体的位置：

1. `structured_noise_high_penalty` 仍然过于粗暴
   - 对真垃圾页这是对的
   - 但对少数强结构页，它会把“可复核 near-miss”也一起打成 hard-drop

2. `solve.py` 现在更像在说“有候选了”
   - 但还不够显式地区分
   - “只是弱候选”
   - 和“已经从 kept page 里消费出同位点候选，但还没闭合”

### 现有方案还能不能继续解？

还能，而且这轮仍然应该先在现有方案里继续解。

判断依据是：

1. 不是所有 case 都 `raw=0`
2. 不是所有 case 都 `kept=0`
3. 已经存在 `kept>0 && candidate>0` 的样本
4. 说明不是整条链都坏掉了，而是中间的 hard-drop 合约和消费表达还不够细

所以这轮不需要先跳到外部新架构，而是应该继续把现有链路里的“误杀”和“未兑现进展”吃干净。

### 如果不能，再去外部检索

只有满足下面任一条件，才值得再去补外部方案：

1. hard-drop 分层后，`second_pass_keep_recovered_count` 仍长期为 0
2. 强结构页放行后，`kept>0` 仍没有任何新增
3. kept 和 candidate 已有新增，但 final reason 与 point state 仍完全表达不出这层进展
4. 成功率有提升，但误放垃圾页明显增多，说明当前页级 contract 已经不够解释

### 这轮实际要实现什么？

#### BS：hard-drop 分层

主改 `retrieval.py`。

实现要求：

1. 把 `structured_noise_high_penalty` 拆成两类：
   - 真 hard noise
   - recoverable structured review candidate
2. 只有垃圾 general calendar / landing / 背景页继续走 hard-drop
3. 对 high page score、strong structured marker、answer candidate 强的页，允许进入后续 soft-keep / second-pass 复核轨道

#### BT：强结构页保留兑现

主改 `retrieval.py`。

实现要求：

1. `should_soft_keep_structured_metric_item(...)` 真实承接 recoverable structured candidate
2. 不再把 `entity_match_count == 0` 直接当成必死条件
3. 对高页分、强 answer candidate、明确 structured marker 的页，允许保留
4. 但不放开低页分 general page，避免把 `afc_0001` 的日历噪声一起放进来

#### BU：证据消费真收口

主改 `solve.py`。

实现要求：

1. 对 `kept>0 && candidate>0` 且 top candidate 来自强页的 case
   - 不再只归成 `weak_candidate_retained`
   - 显式进入“kept page candidate progress”一类状态
2. 最终 reason 要能体现：
   - 页已经保下来了
   - 候选已经消费出来了
   - 但当前卡在 same-slot / directness / point conversion 的哪一层

### 这轮解决什么问题？

如果实施顺利，这轮应该解决下面这些问题：

1. 至少一部分 `structured_noise_high_penalty` 不再是黑盒硬打死
2. 至少一个样本能从 `raw>0 && kept=0` 前进到 `kept>0`
3. 至少一个样本能在 debug / reason 里明确表现出“证据已经被消费到 candidate 层”

### 我们应该怎么用这轮能力？

回看时固定看这几项：

1. `structured_noise_high_penalty`
2. `recoverable_filter_reason`
3. `page_keep_review_state`
4. `second_pass_keep_recovered_count`
5. `slot_review_outcome`
6. `point_consumption_state`
7. `candidate_utility_score`

判断顺序固定为：

1. `raw` 有没有回来
2. `kept` 有没有增加
3. 有 kept 后，候选是不是进入了比 `weak_candidate_retained` 更强的消费状态
4. 如果仍失败，失败停在页保留，还是 point conversion

### 这对用户意味着什么？

对最终使用者来说，这轮最重要的不是“系统看起来更忙”，而是：

1. 更容易真的保住关键结构页
2. 更容易看到“证据已经进到候选层”
3. 失败理由会更贴近真实链路，而不是继续泛化成“没证据”

### 这对开发者意味着什么？

对开发者来说，这轮最大的意义是把下一步施工面继续压缩：

1. 如果这轮能打出 `kept>0` 新进展，说明 hard-drop 分层方向对
2. 如果 kept 有了但 point 仍不闭合，下一轮就该继续打 `candidate -> point`
3. 如果这轮仍然完全不动，再去外部检索新架构才更有把握

### 当前结论

当前最值得继续推进的，不是换检索架构，而是把现有链路里“已经拿到的近失证据”真正保下来并消费出来。

更具体地说：

1. 架构方向没错
2. 现在缺的是 hard-drop 分层
3. 以及 kept page 候选消费的真收口

### 和前面文档的关系

#### 和《入口层审计与外部检索架构对标》的关系

那份文档回答的是“当前主架构为什么还值得继续走”。  
这份文档回答的是“既然主架构还值得走，下一步怎样把页保留与证据消费这条链再往前推一段”。

#### 和《BDBEBF Search Tool 协议化与 Playwright 受控救援》的关系

`BDBEBF` 解决的是入口与协议层。  
这份文档解决的是入口之后的页保留与消费兑现层。

#### 和《BPBQBR 页保留效果与 same-slot 消费打通》的关系

`BPBQBR` 已经把 same-slot 和 page keep 的骨架接上了。  
这份文档是在它的真实 debug 结果基础上，继续把主瓶颈从“骨架存在”推进到“真正开始打通证据消费”。

### 下一步建议

固定按下面顺序执行：

1. 先改 `retrieval.py`，拆 hard-drop，放出 recoverable structured candidate
2. 再改 `solve.py`，把 kept page 候选消费状态显式化
3. 然后跑 `AFC_sample_data0410` 五个锚点最小回归
4. 如果 `kept>0` 和消费状态仍完全不动，再决定是否进入下一轮外部对标
