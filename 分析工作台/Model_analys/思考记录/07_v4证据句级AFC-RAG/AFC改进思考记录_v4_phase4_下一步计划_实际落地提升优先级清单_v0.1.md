## 2026-05-10 AX/AY/AZ 下一步计划：实际落地提升优先级清单

### 分类

证据链 / Workflow / 测试与回归

### 这次要做什么

这份文档不再重复解释“问题出在哪”，而是把前面几份文档已经讲清楚的结论，收成一份真正面向实施的硬清单。

这次固定只收三件事：

1. `AX`：提升“对判错有用”的网页命中质量
2. `AY`：提升 `kept page -> candidate sentence -> evidence point` 的消费率
3. `AZ`：提升 closure 通道的泛化稳定性，并补一套 failure-family 验收方式

这份文档和前面文档的关系是：

- 它不是新的总纲，不替代 [AFC改进思考记录_v4_phase4_重构总目标与分阶段计划_v0.1.md](</d:/张子昊/分析工作台/Model_analys/思考记录/07_v4证据句级AFC-RAG/AFC改进思考记录_v4_phase4_重构总目标与分阶段计划_v0.1.md>)
- 它不是新的机制框架，不替代 [AFC改进思考记录_v4_phase4_下一步计划_决策有用检索与双通道裁决框架_v0.1.md](</d:/张子昊/分析工作台/Model_analys/思考记录/07_v4证据句级AFC-RAG/AFC改进思考记录_v4_phase4_下一步计划_决策有用检索与双通道裁决框架_v0.1.md>)
- 它也不是实施复盘，不替代 `AF/AG/AH`、`AL/AM/AN`、`AO/AP/AQ`、`AU/AV/AW` 这些状态同步文档

它的定位更直接：

- 前面文档负责说明方向、协议、边界
- 这份文档负责说明接下来真正要把哪些“效果层缺口”打下来

### 动机是什么

现在最缺的已经不是“再解释一次系统为什么卡住”，而是把已经识别出的缺口变成实际提升。

目前我们已经有：

- 双通道裁决雏形
- decision channel 协议
- closure / refute / distinguish query family
- 句层 directness 和 point conversion 的 debug 骨架

但我们还没有稳定得到下面这些效果：

1. 更常命中“能直接判错”或“能稳定闭合”的网页
2. 更常把保住的页转成真正可消费的候选句
3. 更常把候选句转成同位点、同口径、可直裁的 evidence point
4. 更稳定地把 closure 通道从个例推进成 family 级能力

所以现在缺的不是理论，不是字段，不是新一轮大分析，而是实际落地的提升部分。

### 对我们的项目有什么实际作用

把这份清单真的做下去，会给项目带来四个直接收益：

1. 把“网页相关”逐步推进成“网页可裁决”
2. 把“有候选句”逐步推进成“候选句能消费”
3. 把 `closure_refutation` 从 `afc_0002` 这种样本级现象，推进成更通用的题型能力
4. 让后面的优化不再反复停留在 debug 更清楚、但效果没怎么动

这份文档的价值不在于新增一个漂亮概念，而在于把后面每一轮都钉在真正会涨效果的部位上。

### 具体场景又是什么

#### 场景 1：`afc_0001`

现在的问题已经不只是 `raw=0`，而是：

- 有时能进 `raw`
- 有时能进 `kept`
- 甚至能有 candidate
- 但最后还是缺少能让系统放心判错的网页直证或 closure 闭合

所以它不再是单纯 recall 题，而是：

- query 是否真在找交易日历 / 节假日 / 交易状态这类 closure facts
- 命中的网页是否真对裁决有用
- 候选句是否真能进 opening/date slot 的 point

#### 场景 2：`afc_0003`

这类题不是找“相关页”，而是找“能打穿唯一性”的 alternative path 或 route closure 证据。

现在系统已经开始知道要走 `distinguish / closure` 轨道，但还缺：

- 更像裁决问题的 query
- 更像裁决材料的页保留
- 更敢消费 alternative-path evidence 的 closure 逻辑

#### 场景 3：`afc_0008 / afc_0010`

这类题很多时候页和句子并不是完全没有，而是长期卡在：

- `candidate_not_direct`
- `not_same_fact_slot`
- `result_granularity_mismatch`
- `partial_but_incomparable`

这里真正要打的不是 recall 数量，而是消费率。

#### 场景 4：`afc_0002`

它的意义已经不是“有一个题打对了”，而是证明 supporting structured detail 的 closure 通道可以成为正式裁决来源。

下一步需要做的不是继续把它当孤例，而是把它的路径推广到：

- `date_fact`
- `schedule_fact`
- `route_fact`
- `event_result`
- `count / numeric supporting detail`

### 我应该怎么去使用

后面每一轮规划和验收，建议都按这三包看：

#### `AX`：网页命中质量

目标不是多搜回页，而是多搜回“对判错有用”的页。

优先做：

1. 收 `closure / refute / distinguish` query family 的实际命中质量
2. 给 official calendar / schedule / notice / tabular page 更稳定的保留优势
3. 压低容易把系统带去背景分析、评论、泛新闻总结的 query 变体

最低验收看：

- 至少 1 个 `date/schedule/route` case 的 `closure/distinguish` row 能稳定进 `raw>0 && kept>0`
- 不再大量只命中背景解释页

#### `AY`：页到句到点的消费率

目标不是“有候选句就算进展”，而是让候选句更常变成可裁决 point。

优先做：

1. 把 utility-first rerank 真正落到候选句排序
2. 让 `direct_candidate` 的提升更依赖 `subject + time_scope + status/result` 完整命中
3. 让 evidence refiner 的结构化结果更稳定参与：
   - `candidate_not_direct`
   - `not_same_fact_slot`
   - `date_role_mismatch`
   - `result_granularity_mismatch`
4. 对高价值 fact-like claim 做受控放松：
   - 不是放宽为“相关就消费”
   - 而是放宽为“近直答句优先进入同位点复核”

最低验收看：

- 至少 1 个 fact-like case 的 top candidate 明显比评论句更像直裁句
- 至少 1 个 case 从 weak candidate 更稳定前移到 same-slot review 或 point conversion

#### `AZ`：closure 泛化与验收

目标不是再多造一条闭合通道，而是把现在已经存在的 closure 能力做成可复用 family。

优先做：

1. 把 closure state 从个例调试字段，收成 family 级观察口径
2. 先固定覆盖：
   - `date_closure`
   - `schedule_closure`
   - `route_closure`
   - `result_closure`
   - `count_closure`
3. 为每个 family 补至少 1 个失败样本和 1 个成功样本
4. 建一组小规模 `failure-family eval`
   - access blocked
   - raw0 but closure facts available
   - raw>0 kept0
   - candidate weak
   - same-slot mismatch
   - closure available but not consumed

最低验收看：

- 不只 `afc_0002`，至少再有 1 个非同题型 case 能显式走进 closure 候选轨道
- 不允许因为 closure 泛化，反向放大 `unsupported structured detail -> 1`

### 对用户意味着什么

对最终用户来说，这份清单如果落下去，最大的变化不是“系统突然多判很多 `1`”，而是：

1. 系统更容易拿到真正能反驳的网页证据
2. 就算暂时还判不出来，也会更真实地停在某一层，而不是一句黑盒 recall
3. 对日期、赛程、路径唯一性、结果粒度这类题，系统会更像真正在做事实核查，而不是只找相似句

### 对开发者意味着什么

对开发侧，这份文档相当于把“接下来该做什么”从宽泛方向收成了一份施工清单。

它要求我们后面少做三类事：

1. 少做纯分析复述
2. 少做只加 debug、不加效果的协议扩张
3. 少做为个别样本特修的短期补丁

它要求我们后面多做三类事：

1. 多看 query 是否真的把系统带到可裁决网页
2. 多看页和句子为什么没被消费，而不是只看有没有命中
3. 多用 family eval 看泛化，不只看单个锚点是否偶然变好

### 当前结论

当前阶段，前面文档已经把“问题是什么”讲得足够清楚了。

现在真正缺的，是下面这三个效果层提升：

1. `AX`：把决策有用网页命中率打上去
2. `AY`：把页到句到点的消费率打上去
3. `AZ`：把 closure 通道从样本能力打成 family 能力

所以这份文档的定位不是再开一条新理论线，而是把前面文档沉淀出来的结论，转成后续开发的实施优先级清单。

### 下一步建议

固定建议按 `AX -> AY -> AZ` 顺序推进，不要乱序散开：

1. 先做 `AX`
   - 因为网页命中质量不起来，后面句层和 point 层只能一直在弱材料上打转

2. 再做 `AY`
   - 因为即使命中了更好的页，如果消费率不升，最终标签还是起不来

3. 最后做 `AZ`
   - 因为 closure 泛化必须建立在前两层至少部分稳定后，否则容易又变成个例通道

建议下一轮产出物固定包含：

1. 代码修改
2. 最小验证
3. 这份清单对应项的完成状态回写
4. 一次提交

一句话收口：

**前面文档已经把方向找到了，现在最该补的不是“再看懂一点”，而是“把命中质量、消费率、closure 泛化这三件事真正做上去”。**
