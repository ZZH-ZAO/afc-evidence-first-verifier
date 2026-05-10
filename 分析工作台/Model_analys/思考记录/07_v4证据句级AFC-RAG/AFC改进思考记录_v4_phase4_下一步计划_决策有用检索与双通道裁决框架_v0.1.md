## 2026-05-10 AR/AS/AT 下一步计划：决策有用检索 + 双通道裁决框架

### 分类

证据链路 / Workflow / 测试与回看

### 这次要做什么？

这份文档不是另起一条新主线，而是在以下已有文档基础上继续往前收：

- `AFC改进思考记录_v4_phase4_重构总目标与分阶段计划_v0.1.md`
- `AFC改进思考记录_v4_phase4_下一步计划_主瓶颈转向retrieval_conversion链_v0.1.md`
- `AFC改进思考记录_v4_phase4_AFAGAH首轮实施状态同步_2026-05-10.md`
- `AFC改进思考记录_v4_phase4_ALAMAN首轮实施状态同步_2026-05-10.md`
- `AFC改进思考记录_v4_phase4_AOAPAQ首轮实施状态同步_2026-05-10.md`

基于这些前置结论，这一轮不再把问题笼统归因成“recall 不够”，而是明确把下一步升级目标收成三个包：

1. `AR`：把 query 从“贴 claim”升级成“面向裁决”的 query family
2. `AS`：把当前单主链证据消费升级成“网页直证 + 基础事实闭合”双通道裁决
3. `AT`：把 rerank 和 final reason 从“相关性优先”改成“可裁决性优先”

这轮不是直接做 recall 扩权，也不是做新的 fallback 扩权，而是把“系统到底在找什么证据、为什么找到的证据还不能判”这两件事机制化。

#### AR：Decision-Useful Query Family

当前 query 主要还是两种：

- 贴原 claim 的 `mirror_query`
- 按 `subject/time/metric` 补全的 `slot_query`

下一步需要正式引入三类新 query，并把它们做成固定协议，而不是 case-by-case 临时发挥：

1. `closure_query`
   - 用来找能闭合基础事实的原子证据
   - 典型适用：
     - `date_fact`
     - `schedule_fact`
     - `count_fact`
     - `route_fact`
     - `result_fact`

2. `refute_query`
   - 用来直接找“与原 claim 竞争或冲突”的表述
   - 不要求和原 claim 用同一词面

3. `distinguish_query`
   - 用来区分容易混淆的近邻事实位点
   - 例如：
     - 开盘 vs 盘中 vs 收盘
     - 发布日 vs 生效日
     - 最终结果 vs 过程结果
     - 唯一路径 vs 常见路径

固定要求：

- query family 不是越多越好，而是每种 query 都必须服务一种明确裁决目标
- `core` 和高风险 `supporting` 才进入这套 query 扩展
- 不新增 provider，不做 fallback 扩权，不做新一轮 recall probe 家族泛滥

#### AS：双通道裁决框架

当前系统已经证明：

- `afc_0002` 这类题可以靠 supporting structured detail 的逻辑闭合打出 `1`
- `afc_0001 / 0003` 这类题，很多并不是世界上没有证据，而是没有把“对判错有用的基础事实”稳定召回并消费

所以下一步需要正式承认：可裁决错误至少有两条主通道。

1. 网页直证通道
   - `query -> raw -> kept -> candidate -> point -> final`
   - 适合：
     - numeric/date quote
     - 官方状态
     - 比分/汇率/价格/结果
   - 核心要求是：
     - 同位点
     - 同口径
     - 可直裁

2. 基础事实闭合通道
   - 不要求同一页直接写出“原答案错了”
   - 允许多个基础事实稳定闭合出“原答案不可能成立”
   - 首轮只覆盖：
     - `date_closure`
     - `schedule_closure`
     - `count_closure`
     - `route_closure`
     - `result_closure`

固定 gate：

- 原子事实本身必须可核
- 时间窗必须一致
- 闭合链必须稳定
- 不允许因为只是“相关”或“可疑”就抬成 `1`
- 不允许让旧新闻、弱二手页、错时窗页面直接冒充 closure-ready evidence

这一步不是要推翻现有 evidence-first 主链，而是要把“网页直证通道之外，哪些题也能稳定判错”收进正式合同。

#### AT：Utility-First Rerank and Reason

当前很多失败不是完全没候选，而是：

- 候选句有了，但前排不是最可裁决的
- 页有了，但 bridge evidence 没被稳定顶上来
- final reason 还是习惯把不同前段失败糊成 recall

下一步需要把 rerank 和 reason 的目标从“相关性”换成“可裁决性”：

1. rerank 侧优先补三类 bonus
   - `same-topic closure evidence`
   - `subject + time_scope + status/result` 覆盖更全的句子
   - official calendar / schedule / notice / authoritative tabular page

2. rerank 侧固定压低三类噪声
   - 背景评论句
   - 与 claim 主题相关但不能裁决的泛分析页
   - 已知会落到 `not_same_fact_slot / date_role_mismatch / result_granularity_mismatch` 的近似误命中

3. final reason 固定先说真实阻塞层
   - access blocked
   - provider recall insufficient
   - kept page lost
   - candidate weak
   - same-slot conversion failed
   - closure evidence not yet stable

### 动机是什么？

前面几轮已经把一个很重要的事实暴露出来了：

1. 现在系统并不是完全不会判 `1`
   - `afc_0002` 已经证明 supporting detail 的稳定逻辑反证通道是能跑通的

2. 现在系统也不是完全没网页证据
   - `0001 / 0003 / 0008 / 0010` 很多时候已经能出现 raw、candidate、甚至 weak point

3. 真正的问题在于：系统还在用“找相关页”的方式找“可裁决证据”

这会带来两个后果：

- 一类题明明能靠基础事实闭合反证，却因为没有同页直答而一直停在 `2`
- 另一类题明明网页里已经有候选句，却因为排序目标不对，最终还是说成“没形成证据”

换句话说，当前缺口不是单纯 recall，不是单纯 candidate 排序，也不是单纯 fallback，而是：

**检索目标、证据形状、最终裁决合同三者还没有完全对齐。**

### 对我们的项目有什么实际作用？

这份计划真正落下去后，会给项目带来四个直接收益：

1. 不再把所有 `2` 都误诊成 recall 问题
2. 不再把所有 weak candidate 都粗暴归成一个 `candidate_not_direct`
3. 不再把“其实能闭合反证”的 date/schedule/count/route/result 题型长期卡死在网页直证通道外
4. 不再让 final reason 和实际瓶颈层错位

这会直接提高两种质量：

- 机制真实性：系统更像真实在判证据，不像在靠经验猜标签
- 泛化稳定性：下一批没测过的题，不至于反复在同一类 family 上漏掉

### 具体场景又是什么？

这份计划最直接对应的就是当前几类已经反复出现的 case family。

#### 场景 1：date / schedule closure

代表：`afc_0001`

当前现状：

- 世界上其实不难找到“4 月 1 日是否休市”“清明节具体落在哪几天”“A股是否正常交易”这类基础事实
- 但系统更偏向找“4 月 1 日 A股休市而港股率先开盘”的整句镜像证据

问题不在于知识不存在，而在于：

- query 没拆成 closure-oriented
- evidence contract 也没有把基础事实闭合作为正式通道

#### 场景 2：route uniqueness / alternative path

代表：`afc_0003`

当前现状：

- 题目不是单纯问某条路径存不存在，而是问“是否只能经过这条路径”
- 这类题天然需要找 alternative route / bypass evidence

问题在于：

- 只搜原 claim，容易搜到“和霍尔木兹海峡相关”的页
- 但不一定搜到“存在绕开通道”这种真正能打穿唯一性的 evidence

#### 场景 3：same-slot conversion

代表：`afc_0008 / 0010`

当前现状：

- 页和候选句并不完全没有
- 但常常卡在：
  - 口径不一致
  - 位点不一致
  - 候选句偏评论或背景

这类题的重点不是继续盲扩 recall，而是：

- 提高 direct candidate 的可裁决排序
- 更早显式化 same-slot mismatch

#### 场景 4：supporting detail stable logic refutation

代表：`afc_0002`

这个 case 最重要的意义不是“它打对了”，而是它证明了：

- 系统并不只能靠网页直证判 `1`
- 只要反证闭合链稳定，supporting structured detail 也可以成为正式裁决来源

所以下一步该做的是泛化和收口，而不是把它当孤例。

### 我应该怎么去使用？

后面看 case、写 debug、定下一轮优先级时，建议按下面顺序判断：

1. 先判这道题更像哪种裁决通道
   - 网页直证通道
   - 基础事实闭合通道
   - 或暂时仍属于解释/归因型，先不强拉进前两类

2. 再看 query family 是否对路
   - 当前只有 `mirror/slot`
   - 还是已经进入 `closure/refute/distinguish`

3. 再看 evidence gap 落在哪层
   - access / provider
   - kept page
   - candidate directness
   - same-slot conversion
   - closure chain instability

4. 最后再决定要改哪一层
   - query
   - retrieval keep/rerank
   - point conversion
   - final aggregation

固定检查项建议新增一组“通道视角”回看：

- `claim_family`
- `intended_decision_channel`
- `query_family_used`
- `bridge_evidence_hits`
- `closure_chain_state`
- `utility_rerank_basis`

这些字段本轮先作为内部设计目标，不要求一步到位全部落代码。

### 对用户意味着什么？

对最终用户来说，这份计划带来的价值不是“系统立刻多刷几个 1”，而是：

- 判不出来时，会更真实地说清为什么判不出来
- 能判错时，不再过度依赖“网页上恰好有一句同义反驳”
- 对日期、赛程、数量、唯一性这类题，会更像人在做核查，而不是只会找相似句子

换句话说，系统会更像“会做证据核查”，而不是“会做相关性搜索”。

### 对开发者意味着什么？

对开发侧来说，这份计划有三层意义：

1. 它把当前最模糊的那层问题讲清楚了
   - 不是 recall 一句话就能概括
   - 也不是简单继续推 AF/AG/AH 那条句层链就够

2. 它把下一轮该改的内容从“散点优化”收成了一组可执行协议
   - query family
   - decision channel
   - utility-first rerank

3. 它给后面的 failure-family eval 集提供了骨架
   - access blocked family
   - raw0 but closure facts available family
   - weak candidate family
   - same-slot mismatch family
   - closure available but not consumed family

这意味着后面每轮优化不再只是盯单个 gold 样本，而是能按错误家族持续压缩。

### 当前结论

结合前面几轮文档、当前 `solve.py` 状态，以及这次补查到的较新外部资料，可以把当前结论收成一句话：

**下一步不该继续把系统当作“普通网页检索 + 句子比对器”去修，而要把它升级成“面向裁决的检索器 + 网页直证/基础事实闭合双通道裁决器”。**

前面几轮已经证明：

- `AL/AM/AN` 让双通道的雏形出现了
- `AO/AP/AQ` 又把 unresolved gap、candidate promotion、access 分层说清了

现在真正缺的是把这些零散能力收成统一框架。

### 下一步建议

下一轮建议固定按 `AR -> AS -> AT` 推进。

1. 先做 `AR`
   - 给 `date_fact / schedule_fact / count_fact / route_fact / result_fact` 引入 `closure_query`
   - 给容易混淆位点的 claim 引入 `distinguish_query`
   - 保持 query 总预算可控，不做无边扩张

2. 再做 `AS`
   - 把 `date_closure / schedule_closure / count_closure / route_closure / result_closure` 正式收进裁决合同
   - 不让这些题型继续被硬塞回单一网页直证链

3. 最后做 `AT`
   - 把 rerank 从 relevance-first 改成 utility-first
   - 把 final reason 固定对齐真实阻塞层

同时，建议单独建一个小规模 failure-family eval 集，至少覆盖：

- access blocked
- raw0 but closure facts available
- raw>0 kept0
- candidate weak
- same-slot mismatch
- closure available but not consumed

## 外部资料补记（2026 方向）

这份计划不是只靠主观判断写的，还吸收了几类与当前问题高度贴近的较新外部思路：

1. `HCQR: Hypothesis-Conditioned Query Rewriting for Decision-Useful Retrieval`
   - 结论：query rewrite 不该只追求相关性，而应服务于裁决目标
   - 链接：`https://arxiv.org/abs/2603.19008`

2. `Adaptive Retrieval for Reasoning-Intensive Retrieval`
   - 结论：要显式考虑 bridge evidence，而不只是与原 query 最像的文档
   - 链接：`https://arxiv.org/abs/2601.04618`

3. `User-Centric Evidence Ranking for Attribution and Fact Verification`
   - 结论：evidence ranking 应优先让“足以裁决”的证据尽早靠前
   - 链接：`https://arxiv.org/abs/2601.21387`
   - PDF：`https://aclanthology.org/2026.eacl-long.340.pdf`

4. `The Alignment Bottleneck in Decomposition-Based Claim Verification`
   - 结论：claim decomposition 只有在 evidence alignment 对齐时才真正带来收益
   - 链接：`https://www.researchgate.net/publication/400704739_The_Alignment_Bottleneck_in_Decomposition-Based_Claim_Verification`

5. `Temporal Fact Verification: Timestamp-Aware Evidence Retrieval and Temporal Entailment for Time-Evolving Claims`
   - 结论：date / schedule / temporal claim 不能只做语义检索，还需要显式 temporal alignment
   - 链接：`https://openreview.net/pdf?id=X3nTGDLg8G`

6. OpenAI Retrieval Guide / Evaluation Best Practices
   - 结论：
     - query 形状确实重要
     - error taxonomy 和 slice-based eval 要尽早成型
   - 链接：
     - `https://platform.openai.com/docs/guides/retrieval`
     - `https://platform.openai.com/docs/guides/evaluation-best-practices`

7. ByteDance Seed1.5 Embedding 官方博客
   - 结论：reasoning-intensive retrieval 不是多堆关键词，而是要对 query-document 的可推理匹配做建模
   - 链接：`https://seed.bytedance.com/en/blog/bytedance-s-seed1-5-embedding-model-achieves-sota-in-retrieval-training-details-unveiled`

## TASK.md 对齐补记（2026-05-10）

### 为什么要加这一层对齐

上面 `AR / AS / AT` 讲的是机制升级方向，但 `TASK.md` 的最终任务定义其实非常朴素：

- 输入是 `question / answer / time / history_question`
- 输出只认三类标签：
  - `0-主需存在事实错误`
  - `1-次需存在事实错误`
  - `2-无事实错误`
- 最终评分看的是标签一致率

所以这份文档不能只停在“检索更真实、证据更有用”的中层抽象，还必须补一层：

**这套机制最后如何稳定映射回 `0 / 1 / 2`。**

### 当前总收口

结合 `TASK.md` 后，当前机制升级目标可以重新表述为：

**不是单纯做 decision-useful retrieval，而是做一套能把“可裁决错误”稳定区分成 `core error / secondary error / insufficient evidence` 的检索与裁决框架。**

也就是说：

- `AR / AS / AT` 是机制层
- `0 / 1 / 2` 是任务标签层
- 中间必须有明确的映射协议，不能靠最终口头解释临时补

### 三分类映射原则

#### `0-主需存在事实错误`

只有当错误直接打穿用户对答案**核心理解**时，才允许进入 `0`。

典型特征：

- 打穿的是 core claim，而不是 supporting detail
- 错误会改变用户对事件/状态/结果/因果前提的基本判断
- 即使删掉该错误点，答案主结论也无法继续成立

典型来源：

- 网页直证通道里，核心事实位点被 direct point 明确反驳
- 基础事实闭合通道里，核心时间前提、核心结果前提、核心唯一性前提被稳定打穿

#### `1-次需存在事实错误`

当错误存在，但主要落在**附带细节**，不改写整体主结论时，进入 `1`。

典型特征：

- 错的是 supporting detail、高风险细节、附带数值/日期/数量/交手记录
- 核心结论仍可基本成立
- 删除错误细节后，主回答仍保有主要解释力

典型来源：

- structured detail 逻辑反证
- 非核心 date/count/result/route detail 的稳定闭合反证
- supporting row 的 direct refutation，但未打穿主结论

#### `2-无事实错误`

这里必须明确包含两种状态：

1. 目前没有发现事实错误
2. 证据还不够，不能把它判成错误

这也是为什么当前系统很多 `2` 不是“证明没错”，而是“还没有足够可裁决证据”。

### 两条裁决通道如何映射到三分类

#### 网页直证通道

默认更容易产生 `0`，但也可能只落 `1`。

固定映射：

1. 若 direct point 打穿 core claim
   - 优先进入 `0`

2. 若 direct point 只打穿 supporting/high-risk detail
   - 优先进入 `1`

3. 若只有 related page / weak sentence / same-slot mismatch
   - 不允许硬抬 `0/1`
   - 保持 `2`

#### 基础事实闭合通道

默认更容易先产生 `1`，但在少数情况下也可以升级到 `0`。

固定映射：

1. 若闭合打穿的是 core premise
   - 允许进入 `0`
   - 例如：
     - 核心时间前提根本不成立
     - 核心唯一性主张被 alternative path 稳定推翻
     - 核心结果前提被稳定闭合推翻

2. 若闭合打穿的是附带 detail
   - 进入 `1`
   - 例如：
     - 次要日期
     - 交手总数/总战绩
     - supporting 数量细节

3. 若 closure facts 还不稳定
   - 不允许因为“感觉像错”就抬标
   - 保持 `2`

### 各类 query family 如何服务标签

`TASK.md` 对齐后，query 不只是服务 retrieval，还要服务最终标签粒度。

#### `mirror_query`

- 主要服务网页直证通道
- 更偏帮助判断：
  - 有没有 direct contradiction
  - 是否可能打出 `0`

#### `slot_query`

- 主要服务 same-slot / same-role 核对
- 用来区分：
  - 是真打到了核心 claim
  - 还是只打到了附带相关事实

#### `closure_query`

- 主要服务基础事实闭合通道
- 用来判断：
  - 这次打穿的是 core premise 还是 secondary detail

#### `refute_query`

- 主要服务直接找竞争解释或冲突表述
- 对 `0` 更敏感，但也可能补出 `1`

#### `distinguish_query`

- 主要服务把错误分层，而不是单纯找更多页
- 特别适合避免：
  - `opening vs intraday vs close`
  - `发布日期 vs 生效日`
  - `最终结果 vs 过程结果`

### 当前标签层的最关键补件

后面如果继续实现，建议正式新增一层内部映射规格：

- `claim_family -> intended_decision_channel`
- `decision_channel -> possible_label_band`
- `core_binding_strength`
- `secondary_detail_scope`

这样做的意义是：

- 不是所有 evidence 一旦成立都能进 `0`
- 不是所有 closure contradiction 一旦成立都只能是 `1`
- 必须显式说明它打到的是“核心理解”还是“附带细节”

## LLM 融合策略补记（2026-05-10）

### 当前总判断

LLM 不该只是“最后再判一次”，而应该嵌进 `AR / AS / AT` 的几个关键位点里，分别扮演不同角色。

当前最合适的角色不是：

- 黑箱最终裁判
- 全量 claim 一律 decomposition
- 直接吞长上下文后拍板

当前更合适的角色是：

- query planner
- bridge-fact proposer
- evidence refiner
- incremental reranker
- low-confidence calibrator

### LLM 在 `AR` 层的作用

#### 1. Query Planner

LLM 最适合先做：

- `claim_family` 判定
- `intended_decision_channel` 初判
- `query_family_plan` 生成

输出应固定成小协议，而不是自由发挥长文本：

- `mirror_query`
- `slot_query`
- `closure_query`
- `refute_query`
- `distinguish_query`

并补齐：

- `query_role`
- `expected_evidence_shape`
- `expected_decision_use`

当前更推荐的方式不是“多生成几条相似 query”，而是让 LLM 先回答：

**要把这个 claim 判成 `0/1`，到底缺哪类证据。**

### LLM 在 `AS` 层的作用

#### 2. Bridge-Fact Proposer

对 `date_fact / schedule_fact / route_fact / result_fact / count_fact`，LLM 应该先提出：

- 要稳定闭合，需要哪些基础事实
- 哪些是 bridge facts
- 哪些是容易混淆的假朋友证据

例如 `0001` 这类题，不该只复述原 claim，而应先列出：

- `2026-04-01 是星期几`
- `2026 清明节放假安排`
- `A股 2026-04-01 是否正常交易`

#### 3. Evidence Refiner

LLM 不应直接输出最终 label，而应先把候选 evidence 整理成 evidence card：

- `subject`
- `time_scope`
- `metric_or_relation`
- `status_or_result`
- `date_role`
- `result_granularity`
- `source_type`
- `evidence_directness`
- `possible_confusions`

这一步的好处是：

- 把后面的 same-slot / closure 判断从作文题变成结构题
- 减少“页相关但不可裁决”的噪声对最终标签的污染

### LLM 在 `AT` 层的作用

#### 4. Incremental Reranker

LLM 更适合做“下一条最该选哪条 evidence”，而不是一次性全局重排。

给定：

- 当前 claim
- 已选 evidence
- 当前 gap

LLM 输出：

- 哪条 sentence/page 最能补齐 gap
- 补的是：
  - `time_scope`
  - `status/result`
  - `date_role`
  - `same-slot`
  - `closure chain`

这比 one-shot relevance ranking 更贴当前 Phase4 的真实需要。

#### 5. Low-Confidence Calibrator

LLM 可以做低置信校准，但不应该取代主证据合同。

仅推荐在这些场景触发：

- top-2 evidence path 接近
- direct channel 与 closure channel 给出冲突倾向
- rule-based score 接近阈值
- 不确定该落 `0`、`1` 还是维持 `2`

而且输出不应是开放式长文，而应固定成：

- `core_error_candidate`
- `secondary_error_candidate`
- `insufficient_evidence`
- `abstain`

这样它才能和 `TASK.md` 的三分类目标直接对齐。

### 当前不建议让 LLM 接管的部分

1. 不要让 LLM 直接吞超长上下文后黑箱判
2. 不要让 LLM 成为独立第二判标器
3. 不要对所有 claim 一律先 decomposition
4. 不要把 rerank 完全交给纯 LLM，而丢掉 lexical / diversity / slot coverage guardrail

### 近期最值得落地的三个 LLM 位点

如果后面真要把 LLM 引进来，最优先建议是：

1. `LLM query planner`
   - 先把 `closure_query / distinguish_query / refute_query` 做成稳定协议

2. `LLM evidence refiner`
   - 把 retrieved material 转成 evidence cards

3. `LLM incremental reranker`
   - 让排序目标从“最相关”变成“最能补当前判决缺口”

这三块的优点是：

- 和当前 `solve.py` 架构兼容
- 不需要立刻推翻现有 evidence-first 主链
- 对 `TASK.md` 三分类也更容易做最终标签映射

### LLM 融合后的总收口

结合 `TASK.md` 后，LLM 的最佳角色可以收成一句话：

**LLM 不是替代证据链的黑箱裁判，而是服务于三分类标签的“证据规划器、证据整理器、增量排序器和低置信校准器”。**

也就是：

- 前面帮助系统更好地找到“对 `0/1/2` 有区分力的证据”
- 中间帮助系统把 evidence 变成可消费结构
- 后面只在边界 case 里做有限校准

## 外部资料补记（LLM 融合方向）

1. `HCQR: Hypothesis-Conditioned Query Rewriting for Decision-Useful Retrieval`
   - 启发：query rewrite 应服务裁决目标，而不是只追求 topical relevance
   - 链接：`https://arxiv.org/abs/2603.19008`

2. `Think Then Rewrite: Integrating Reasoning into Conversational Query Rewriting`
   - 启发：rewrite 之前要先 reasoning，尤其要处理 distractor
   - 链接：`https://ojs.aaai.org/index.php/AAAI/article/view/38527`

3. `Retrieve-Refine-Calibrate: A RAG-Enhanced Framework for Fact Verification`
   - 启发：LLM 更适合先 refine evidence，再对低置信结果做 calibration
   - 链接：`https://arxiv.org/abs/2601.16555`

4. `User-Centric Evidence Ranking for Attribution and Fact Verification`
   - 启发：incremental ranking 优于 one-shot ranking，适合补互补证据
   - 链接：`https://arxiv.org/abs/2601.21387`
   - PDF：`https://aclanthology.org/2026.eacl-long.340.pdf`

5. `Diagnosing LLM Reranker Behavior Under Fixed Evidence Pools`
   - 启发：LLM reranker 不能无 guardrail 地直接取代传统排序
   - 链接：`https://arxiv.org/abs/2602.18613`

6. `Context Shapes LLMs Retrieval-Augmented Fact-Checking Effectiveness`
   - 启发：长上下文不是越长越好，证据编排位置和压缩方式会显著影响效果
   - 链接：`https://arxiv.org/abs/2602.14044`

7. `Distill and Align Decomposition: Small Models for Scalable and Valid Fact-Checking`
   - 启发：对齐好的 decomposition 很有用，但必须与 evidence alignment 一起看
   - 链接：`https://arxiv.org/abs/2602.21857`

8. `The Alignment Bottleneck in Decomposition-Based Claim Verification`
   - 启发：若 evidence 不对齐，分解本身会放大误差；abstention 往往优于激进误判
   - 链接：`https://arxiv.org/abs/2602.10380`

9. OpenAI Retrieval Guide / Evaluation Best Practices
   - 启发：
     - 官方明确支持 query rewrite
     - judge 设计更适合 pass/fail、pairwise、reasoning-first 的校准形式
   - 链接：
     - `https://developers.openai.com/api/docs/guides/retrieval`
     - `https://developers.openai.com/api/docs/guides/evaluation-best-practices`

## 当前代码现状审计补记（2026-05-10）

### 这次审计想回答什么

这段补记不是新增方向，而是回答一个更现实的问题：

**当前 `solve.py` 到底已经走到哪一步了，和上面这份 `AR / AS / AT + TASK 对齐 + LLM 融合` 计划之间，还差几层。**

如果不把这层写清楚，文档很容易看起来像“下一步已经定义好了”，但实际落代码时会因为现状判断不清而再次回到样本修补。

### 当前代码里已经稳定存在的能力

#### 1. `AO / AP / AQ` 这条 debug 分层已经在代码里落稳

当前 `solve.py` 里已经有比较完整的 debug/诊断字段，至少包括：

- `structured_detail_retained`
- `logic_refutation_candidate`
- `logic_refutation_basis`
- `logic_refutation_state`
- `logic_refutation_closure_stage`
- `logic_refutation_block_reason`
- `sentence_candidate_profile`
- `top_candidate_slot_match`
- `direct_candidate_gap_reason`
- `direct_candidate_promotion_basis`
- `candidate_promotion_block_reason`
- `candidate_slot_coverage_summary`
- `access_path_state`
- `access_block_source`
- `rescue_attempt_state`

这说明当前系统已经不是“完全黑盒 recall”，而是已经能把：

- detail 侧 unresolved
- candidate 侧 weak/direct gap
- access / rescue / recall 差异

显式写进 claim-level diagnostics。

#### 2. 双通道已经有雏形，但还不是完整框架

当前代码里已经存在的“双通道雏形”主要是：

1. 网页 direct evidence 通道
   - 通过 `has_direct_refuting_evidence(...)`
   - 最终能进入 `evidence_refutation`

2. structured detail logic refutation 通道
   - 通过 `secondary_detail_direct_refutation`
   - 已能把部分 supporting detail 稳定打成 `1`

这说明：

- “只有网页 direct point 才能判错”这件事，代码层已经被部分打破
- 但它目前还主要停留在 supporting detail 逻辑反证，不等于完整的 `date_closure / route_closure / result_closure / count_closure` 框架已经落地

#### 3. `TASK.md` 的标签层已经被部分显式消费

当前标签不是完全靠最后一层自由生成 reason 决定的，而是已经有一套显式 policy 分流：

- `evidence_refutation`
- `evidence_support`
- `insufficient_evidence`
- `secondary_detail_direct_refutation`
- `rubric_fallback`

同时，代码中已经有不少按任务标签粒度写的硬门槛，例如：

- core unsupported 某些场景直接打 `0`
- supporting absolute detail 某些场景打 `1`
- 无足够 direct evidence 时回退 `2`

这说明当前代码并不是完全没有 label mapping，而是：

**已经有 label mapping，但它还是分散的、半启发式的，还没有收成统一协议。**

### 当前代码里还没有正式出现的能力

#### 1. 还没有正式的 `query family` 协议

虽然代码里已经有 query 生成和部分 `query_variant_origin / fact_slot_query` 之类的演化，但当前并没有显式实现这套计划中的字段或协议：

- `closure_query`
- `refute_query`
- `distinguish_query`
- `query_role`
- `expected_decision_use`

也就是说：

- 现在的 query 仍主要是“围着 claim 长”
- 还没有正式变成“围着裁决缺口长”

#### 2. 还没有正式的 `decision channel` 内部对象

文档里提出的这些设计目标：

- `claim_family`
- `intended_decision_channel`
- `bridge_evidence_hits`
- `closure_chain_state`
- `utility_rerank_basis`
- `core_binding_strength`
- `secondary_detail_scope`

目前都还没有成为 `solve.py` 里的统一字段或统一消费层。

换句话说：

- 现在代码已经在做很多“像 decision channel 的事”
- 但还没有明确承认自己在走哪条 channel

#### 3. 还没有完整的 `bridge evidence` 消费框架

当前 structured detail 逻辑反证已经能处理一部分“由已有材料闭合出来的错误”，但更广义的 bridge evidence 机制还没有正式落地，例如：

- 先找“星期几 / 放假安排 / 正常交易日”
- 再把这些基础事实闭合成核心 date contradiction

也就是说，`0001` 这类题还没真正进入“基础事实闭合主通道”，而是仍然停在：

- retention
- partial logic point
- 或 unsupported time detail

#### 4. 还没有 LLM 的结构化中层角色

当前代码里虽然大量使用 LLM 做抽取/验证，但还没有正式分出文档里建议的几种角色：

- `LLM query planner`
- `LLM bridge-fact proposer`
- `LLM evidence refiner`
- `LLM incremental reranker`
- `LLM low-confidence calibrator`

现状更像是：

- LLM 参与了抽取、判断和 fallback
- 但没有按职责拆成更稳定的可替换模块

### 当前最值得警惕的代码现实

#### 1. 任务标签映射目前仍偏“分散启发式”

当前 `0 / 1 / 2` 并不是统一从一个“core vs secondary vs insufficient”层映射出来的。

更真实的现状是：

- 一部分来自 evidence 直判
- 一部分来自 secondary detail 通道
- 一部分来自 domain-specific heuristic
- 一部分来自 insufficient evidence 回退

这意味着：

- 文档里说的“统一标签映射层”现在还没有
- 这是下一步必须补的总装层，而不是可选装饰

#### 2. 领域特化规则仍然很多

当前标签收口里，仍能看到不少偏领域 heuristics 的分支，例如：

- `market_movement`
- `sports_result`
- `geopolitical`
- `finance_need`
- `schedule_time`

这些规则并不一定错，但它们意味着：

**当前代码仍然有较重的“任务家族特化判标带”，还没有完全迁移到统一的 decision-useful retrieval / dual-channel 框架里。**

这也是为什么下一步不能只加新层，还要考虑怎么迁移旧规则。

#### 3. `decision_basis` 还没有显式区分 `core_error` 和 `secondary_error`

当前 `classify_decision_basis(...)` 主要区分的是：

- `evidence_refutation`
- `evidence_support`
- `insufficient_evidence`
- `rubric_fallback`

但它并没有再往下显式分出：

- `core_error_candidate`
- `secondary_error_candidate`

这说明 `TASK.md` 里最关键的三分类粒度，目前还没有被一个统一 basis 层承接。

### 因此，文档里最该补充的不是新方向，而是三种边界说明

#### 补件 1：实现边界

要明确区分：

1. 已在代码里稳定存在的
2. 已有雏形但还没收成统一协议的
3. 仍属于下一轮设计目标的

否则后面容易把“代码已有 debug 字段”误当成“机制已经完成”。

#### 补件 2：迁移边界

要明确写出：

- 哪些旧 heuristic 先不动
- 哪些旧 heuristic 要逐步迁到 decision channel
- 哪些标签规则最终应退出 domain-specific 分支，改由统一映射层消费

这一步很关键，因为不写迁移边界，后面实现时很容易：

- 新框架加了一层
- 旧规则还在底下继续改标签
- 最终变成“双层互相打架”

#### 补件 3：验收边界

除了看 `0001 / 0002 / 0003 / 0008 / 0010`，还应该补一条更工程化的验收标准：

- 新增机制后，最终 label 的来源要更可解释，而不是更复杂
- 至少能说清：
  - 是哪个 channel 在主导
  - 它为什么有资格进入 `0` 或 `1`
  - 为什么另一个 channel 没接管

### 当前审计后的总结

当前代码现状可以概括成一句话：

**代码已经走出了“纯 recall + 纯 fallback”的阶段，已经具备双通道雏形和多层 debug 能力；但它还没有真正拥有“统一的 decision channel 协议、统一的标签映射层、统一的 LLM 模块分工”。**

所以这份文档下一步最该补的，不是再扩更多未来设想，而是始终坚持三句话：

1. 哪些东西代码里已经有
2. 哪些只是雏形，还没算完成
3. 哪些是下一轮必须收成统一协议的总装层

## 2026-05-10 AU/AV/AW 首轮实施补充

### 分类
证据链 / Workflow / 提示词

### 这次要做什么？
在 `solve.py` 里把上一版文档里提出的 `AU/AV/AW` 先落成第一版可运行实现：
1. 给 claim 级诊断补一层统一的 decision channel 协议。
2. 给 query 生成补 `closure / refute / distinguish` family，并把 `query_family_role` 保留下来。
3. 让 LLM 进入中层，只做 query planner 和 evidence refiner，不直接给最终标签。

### 动机是什么？
前几轮代码已经有双通道雏形，但问题一直是“能力散在很多启发式里”。
如果没有统一协议，我们虽然能看出某些 case 已经进入 closure 或 direct candidate 轨道，但最终 reason、label 映射、query 设计还是各走各的，后面继续扩机制会越来越难解释，也更难判断到底是哪一层真的起作用。

### 对我们的项目有什么实际作用？
这次不是单纯再加一点 recall，而是把“为了裁决有用”这件事更明确地写进主链：
- query 不再只围着 claim 原句打转，而是开始围着 closure gap 和 distinguish gap 发问；
- supporting structured detail 的 closure 通道不再只是 debug 影子，而是有了更清楚的 channel 表达；
- LLM 不再一上来就碰 final label，而是先承担规划和句层整理这两个更稳的中层工作。

### 具体场景又是什么？
1. `afc_0002` 这类题，核心结论未必被网页 direct point 直接打穿，但 supporting detail 自己能逻辑闭合出矛盾，需要 closure 通道稳定承接。
2. `afc_0003` 这类 route 题，真正有用的不是继续堆泛 query，而是显式去找“替代路径 / 并非唯一 / route distinguish”这类 closure gap。
3. `afc_0001 / 0008 / 0010` 这类题，网页链路经常不是完全没搜到，而是候选句、位点、口径没有被整理成更可消费的中层结构。

### 我应该怎么去使用？
这轮之后，读 debug 时优先看这些字段：
- `claim_family`
- `intended_decision_channel`
- `channel_decision_candidate`
- `channel_decision_confidence`
- `query_family_role`
- `query_planner_hint`
- `point_conversion.llm_evidence_refiner`
- `point_conversion.llm_refined_gap_reason`

如果一个 case 还是 `2`，先不要只看“有没有搜到”，而是先看它最后停在：
- direct_web_evidence 通道的哪一层；
- closure_refutation 通道有没有 candidate 但没闭合；
- query family 有没有真正切到 closure / distinguish。

### 对用户意味着什么？
用户看到的最终标签不会因为这轮就突然大变，但中间链路会更可解释：
- 为什么这题被当成 direct_web_evidence 来处理；
- 为什么那题更像 closure_refutation；
- 为什么虽然还是 `2`，但已经从黑盒 recall 退回成更真实的句层/位点/closure 阻塞。

### 对开发者意味着什么？
这轮最大的意义不是“多刷几个 1”，而是把后续开发的承重面搭出来：
- 以后想继续做 closure facts、bridge evidence、route alternative path，不用再从零找挂点；
- 以后想看某个标签为什么来的，至少能先从 channel 协议查起；
- 以后接更强的 reranker / calibrator，也有明确的中层接口，而不是直接碰 final label。

### 当前结论
这轮已经落下来的东西：
- `AU`：claim 级诊断新增 `claim_family / intended_decision_channel / core_binding_strength / secondary_detail_scope / channel_decision_candidate / channel_decision_confidence`，并在聚合结果里补 `_decision_channel` 等内部字段。
- `AV`：query 生成新增 `closure_query / refute_query / distinguish_query` 首轮能力，query row 保留 `query_family_role`，并引入轻量 `query_planner_hint`。
- `AW`：新增 `LLM query planner` 与 `LLM evidence refiner`，只做中层结构化，不允许直接输出最终 `0/1/2`。

这轮明确没有做的：
- 没有让 LLM 直接判标签；
- 没有把 `incremental reranker / calibrator` 接进主链；
- 没有新增 provider、fallback 扩权或 `solve_submit.py` 合流。

本轮最小验证结果：
- `afc_0001 -> 2`，但主因前移到页面到句子转换，不再只是黑盒 recall。
- `afc_0002 -> 1`，继续稳定由 supporting structured detail 的 closure 反证承接。
- `afc_0003 -> 2`，但 route claim 已显式进入 `distinguish / closure` query 轨道。
- `afc_0008 -> 2`
- `afc_0010 -> 2`

### 下一步建议
下一轮优先不再泛泛扩 recall，而是顺着这轮已经露出来的三件事继续推进：
1. 收 `route_fact / date_fact / schedule_fact` 的 family query 质量，减少 planner 给出角色但实际 query 仍偏泛的情况。
2. 让 evidence refiner 的结构化卡片更稳定参与 point conversion 的错位归因，尤其是 `date_role_mismatch / not_same_fact_slot / result_granularity_mismatch`。
3. 继续把 top-level label 的来源说明往“channel + scope + closure state”统一，而不是继续散落在 domain heuristic 里。
