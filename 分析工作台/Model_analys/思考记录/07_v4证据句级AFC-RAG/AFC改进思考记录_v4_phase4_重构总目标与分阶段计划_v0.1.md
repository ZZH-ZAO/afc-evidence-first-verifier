## 2026-05-08 AFC v4 Phase4 重构总目标与分阶段计划

### 分类

证据链路 / Workflow / 检索链路 / 测试与回归 / 提示词

### 这次要做什么？

把当前 AFC v4 主链从“规则已经形成、代码仍偏快速迭代堆叠”的状态，正式收成一份可执行的重构路线图。  
这份文档不是继续补单题，也不是只写原则，而是明确：

1. 当前真正要守住的总目标是什么
2. 现阶段系统最核心的结构问题是什么
3. 重构必须按什么顺序推进
4. 每个阶段具体改哪些文件、解决什么问题
5. 每个阶段做到什么程度才算通过

当前纳入计划的核心文件包括：

- `afc_schema.py`
- `afc_route_markers.py`
- `search_providers.py`
- `retrieval.py`
- `evidence.py`
- `solve.py`
- `solve_submit.py`

### 动机是什么？

这轮分析下来，系统的问题已经不是“还没想到方案”，而是“方案已经出来了，但代码组织没有同步收口”。  
现在的主链已经有了这些正确方向：

1. 证据优先，fallback 只兜风险，不伪装成证据
2. 反证必须满足同一事实位点的 comparability contract
3. `refute` 可以 early exit，`support` 不能 early exit
4. `supporting/peripheral` 的结构化细节，未证实不等于错
5. 官方信源要从 attempted 走到 used，再走到 kept point

但是代码层面还存在四类明显问题：

1. **历史实现和现行实现混叠**  
   尤其是 `evidence.py`，存在同名函数重复定义、后定义覆盖前定义的情况，真实生效逻辑不够一眼可见。

2. **职责边界已经形成，但文件边界还没彻底收干净**  
   `retrieval.py`、`evidence.py`、`solve.py` 之间已经有策略层、证据层、裁决层的分工雏形，但政策判断和证据语义还在交叉。

3. **存在两套总控行为面：`solve.py` 与 `solve_submit.py`**  
   这不是简单的“一个旧一个新”，而是“一个偏开发主链，一个偏收敛提交版”。如果不把差异收口，后面会越来越难对齐。

4. **检索面的问题容易被误判成裁决面问题**  
   现在很多“没找到证据”的症状，实际上可能发生在三层：
   - `search_providers.py` 没抓回来
   - `retrieval.py` 把结果刷掉了
   - `evidence.py` 没把结果转成可裁决点

如果这时候继续直接补规则，短期可能能修个别样本，但长期会把系统变成：

1. 一层层补闸门
2. 一层层加例外
3. 每层都能改标签
4. 最终没人说得清“为什么这题是这个结果”

所以现在最需要的不是继续横向扩功能，而是先纵向收边界。

### 对我们的项目有什么实际作用？

这份重构计划的实际作用，不是“写一份好看的文档”，而是给后面的开发提供一条固定施工顺序，让我们不再一边修样本一边把系统越修越乱。

具体会带来六个直接收益：

1. 后续每轮改动都能明确是在修哪一层，不再一上来就堆最终标签规则
2. `evidence.py` 的真实生效逻辑会变清楚，减少“看着有这个函数，运行时其实用的不是它”的情况
3. `retrieval.py`、`search_providers.py`、`evidence.py` 三层的排障路径会更清楚
4. `solve.py` 和 `solve_submit.py` 的差异能逐步显式化，而不是靠体感判断哪版更好
5. 以后做 targeted regression 时，能更稳定地定位“是召回退了、过滤严了、还是 comparability 太松/太紧”
6. 给下一阶段的代码清理和提交版收口提供可验收的阶段边界

### 具体场景又是什么？

这份重构计划主要是为了解决当前已经反复暴露出来的几个典型场景：

1. `afc_0008` 这类结构化数值题  
   问题不是没有材料，而是不同口径数字被误当成同一事实位点，说明 comparability 还需要更稳定地固化。

2. `afc_0002` 这类核心支持后仍有高风险 detail 的题  
   问题不是支持证据不存在，而是 `support` 锁得太早，剩余 detail 没裁完就整题放过。

3. `afc_0003` 这类排他性 premise 没被显式抽成 claim 的题  
   问题不是 fallback 完全没用，而是 gold 对应错误点没进 claim，最后被别的高风险核心关系顶替了。

4. `afc_0001` 这类 market calendar / market movement 混合题  
   问题不是证据完全没搜到，而是：
   - query anchor 可能退了
   - news 证据可能被 filter 刷掉了
   - 同日不同状态被误看成 support

5. `official_discovery_attempted` 很多、`official_points` 很少的题  
   问题不是完全没做官网链路，而是 discovery 到 retention 的闭环还不稳定。

### 我应该怎么去使用？

后续重构默认按下面这条总原则执行：

**先清边界，再清重复，再收总控，最后再做更大范围的检索增强。**

具体执行时遵循四个使用原则：

1. 不做“大爆炸重写”，每阶段只动一类核心矛盾
2. 不用全量乱跑做反馈，优先用 targeted regression 验证单一改动是否有效
3. 不按样本 id 修题，不按具体域名补硬编码官网表
4. 重构不以“代码更好看”为目标，而以“行为更稳定、链路更可解释”为目标

### 对用户意味着什么？

如果这份计划按阶段真正落地，用户侧最直接的变化会是：

1. 结果更稳定，不会频繁出现“这一版好一点，下一版又退回去”的情况
2. `reason` 会更像真实解释，而不是多层兜底互相覆盖后的拼接文本
3. 结构化细节错和主结论错会分得更清楚
4. “没证据”与“有证据但不可比”会被更明确地区分开
5. 官方页和新闻页会变成两条都可用的证据通道，而不是彼此挤占

### 对开发者意味着什么？

对开发侧，这份计划最重要的价值是把“看起来都在 AFC 主链里”的东西，重新拆成几个能单独收口的面：

1. 搜索驱动层：`search_providers.py`
2. 检索策略层：`retrieval.py`
3. 证据结构化层：`evidence.py`
4. 裁决编排层：`solve.py`
5. 提交收敛层：`solve_submit.py`

这样以后排问题可以按顺序问：

1. 是 provider 没拿回结果吗？
2. 是 retrieval 把结果筛掉了吗？
3. 是 evidence 没把它变成可裁决点吗？
4. 是 solve 的 policy 让它提前放过或误升级了吗？
5. 是 submit 版和开发版总控行为分叉了吗？

这会把“修错题”变成“修哪一层的机制”，长期收益远大于继续补局部规则。

### 当前结论

当前系统可以先明确成下面这个总目标：

## 总目标

把 AFC v4 主链重构成一条**职责清楚、证据边界稳定、检索问题可定位、提交版与开发版差异可解释**的事实核查流水线。

这条总目标再拆成五个子目标：

1. **边界目标**  
   comparability、support/refute、detail 1/2 边界、fallback radius 必须稳定且可解释。

2. **结构目标**  
   `evidence.py` 不再保留运行时覆盖式旧实现；`solve.py` 不再无限承担中间层职责。

3. **链路目标**  
   检索问题能明确区分 provider 召回、retrieval 过滤、evidence 转点、solve 政策四类原因。

4. **收口目标**  
   `solve_submit.py` 逐步从“另一套看起来效果更好的实现”收成“主链的可控收敛版”。

5. **回归目标**  
   后续每次 targeted regression 都能回答：这次改动到底提升了哪层，不靠体感判断。

---

## 分阶段计划

### Phase 0：冻结边界与建立重构基线

**目标**  
先把当前系统“什么是现行有效逻辑、什么是历史残留逻辑、什么是提交版特有逻辑”摸清楚，避免重构第一刀就切错。

**主要工作**

1. 盘点 `solve.py`、`solve_submit.py`、`evidence.py`、`retrieval.py` 的核心入口
2. 标出重复定义、覆盖式 helper、实际生效路径
3. 固定一组最小 targeted regression 样本作为重构锚点
4. 对 `solve.py` 和 `solve_submit.py` 的关键差异做清单

**重点文件**

- `evidence.py`
- `solve.py`
- `solve_submit.py`
- `retrieval.py`

**验收标准**

1. 能明确列出当前 active 入口和重复定义点
2. 能明确列出 5-10 个重构锚点样本
3. 能明确说清 submit 版比开发版当前多收了什么、少收了什么

---

### Phase 1：先清 `evidence.py`，去掉运行时覆盖式旧实现

**目标**  
把 `evidence.py` 从“历史实现 + 末尾 override”改成“一套清晰的现行实现”，先解决最明显的结构脏点。

**主要工作**

1. 合并重复 helper：
   - `is_market_calendar_state_claim`
   - `market_calendar_state_slot`
   - `extract_numbers`
   - `extract_dates`
   - `normalize_date_value`
   - `numeric_sentence_score`
2. 明确保留版 helper 的输入输出合同
3. 把结构化 claim summarizer 的依赖 helper 收成一套
4. 清掉“前面定义、后面覆盖”的旧逻辑

**为什么先做这步**

因为这一步对外部行为的影响最可控，但对后续理解整个系统的帮助最大。  
如果不先清这层，后面改 comparability、改 date/numeric 口径时会一直受影子实现干扰。

**验收标准**

1. `evidence.py` 不再存在同名 helper 的运行时覆盖
2. 回归后行为不应因“清理旧实现”出现大面积漂移
3. evidence 层 debug 输出保持一致或更清楚

---

### Phase 2：收紧证据直裁边界，明确证据层与裁决层分工

**目标**  
把当前已经形成的几条关键裁决原则，进一步从“散落在 solve 里的规则”收成稳定边界。

**主要工作**

1. 固定 comparability contract 的字段和语义
2. 固定 `support` 不 early exit、`refute` 可 early exit 的顺序
3. 固定 `supporting/peripheral detail -> 1/2` 的统一规则
4. 把 evidence 可裁决与 fallback 风险补判分清楚

**重点文件**

- `solve.py`
- `solve_submit.py`
- 必要时少量配合 `evidence.py`

**这一步要解决的核心问题**

不是“某题怎么判”，而是：

1. 什么才算可裁决反证
2. 什么只是相关但不可比
3. 什么只是未证实
4. 什么是真正可以升到 `1`

**验收标准**

1. `afc_0008` 这类不同口径数字不再误反证
2. `afc_0002 / afc_0010` 这类核心支持后仍会检查高风险 detail
3. fallback 不再轻易把 detail 风险抬成 core 风险

---

### Phase 3：整理检索层边界，拆清 provider、retrieval、evidence 三层责任

**目标**  
让“没找到证据”这类症状可以被明确拆层定位，而不是统称检索不好。

**主要工作**

1. 明确 `search_providers.py` 只负责搜索源适配与结果抓取
2. 明确 `retrieval.py` 只负责 query/source/page/filter/detail 策略
3. 明确 `evidence.py` 只负责把保留下来的结果转成裁决点
4. 补诊断位，区分：
   - provider 空召回
   - retrieval filter 误杀
   - evidence 不可转点

**重点文件**

- `search_providers.py`
- `retrieval.py`
- `evidence.py`

**这一步为什么重要**

因为当前很多回归讨论其实把三类问题混在一起了：

1. 没搜到
2. 搜到了但被刷掉
3. 保留了但不可裁

如果不拆开，后面任何一层改动都很容易被误读。

**验收标准**

1. 针对单个 claim，能从 debug 看出问题停在哪一层
2. 新闻召回退化和 official closure 失败能被区分开
3. 对“证据曾经能召回但这轮没了”的问题，能快速判定是 query 退了还是 filter 严了

---

### Phase 4：补官方信源闭环，但坚持新闻与官网双通道

**目标**  
补强 official 链路，但不以牺牲新闻证据为代价。

**主要工作**

1. 继续推进 `official_discovery_attempted -> used -> official_points`
2. 强化 official-like structured page 识别
3. 改善 discovery candidate 的实体约束，压低假候选
4. 明确哪些 evidence shape 优先官方，哪些必须保留新闻通道

**重点文件**

- `retrieval.py`
- `search_providers.py`

**硬原则**

1. 有官方当然搜官方
2. 但不能因为补官网，就不搜新闻
3. 不能按题型硬绑官网表
4. 只能按 source family 和 evidence shape 泛化

**验收标准**

1. 至少出现真实的 `official_discovery_used -> official point kept`
2. 新闻页不能整体被压没
3. official 提升后，reason 不应该更空，应该更可解释

---

### Phase 5：收口双总控，明确 `solve.py` 与 `solve_submit.py` 的长期关系

**目标**  
不再让 `solve.py` 和 `solve_submit.py` 维持长期隐性分叉。

**主要工作**

1. 列出两者当前关键策略差异
2. 明确哪些差异是 submit 必要收敛，哪些只是主链没同步
3. 把 submit 版验证过更稳的规则，择机回收进主链
4. 最终形成：
   - 一个开发主链
   - 一个轻量提交外壳

**重点文件**

- `solve.py`
- `solve_submit.py`

**为什么不能一直并存两套大分叉**

因为一旦长期并存，后面会出现：

1. 一版回归结论没法迁移到另一版
2. 一版修好了，另一版继续退化
3. 团队内部只能靠体感判断“这版更好”

**验收标准**

1. 能明确解释 submit 版当前为什么更稳
2. 主链与提交版的差异减少到“开关和收敛面”，而不是“另一套世界观”

---

### Phase 6：重构后的回归制度化

**目标**  
把后续验证从“跑一遍看看”收成稳定的回归方法。

**主要工作**

1. 固定重构锚点样本池
2. 固定每阶段只做 targeted regression
3. 固定每轮要看哪些 debug 口径：
   - comparability
   - coverage
   - point conversion
   - source recall / filter / retention
   - official attempted/used/kept
4. 只有阶段稳定后，再考虑更大样本回归

**验收标准**

1. 每轮改动都能说清楚“提升了哪层”
2. 不再频繁出现“全量结果变了，但不知道为什么”

### 下一步建议

默认按下面顺序推进，不并行乱改：

1. 先做 **Phase 0：基线与差异盘点**
2. 再做 **Phase 1：`evidence.py` 去覆盖式旧实现**
3. 再做 **Phase 2：证据直裁边界固化**
4. 再做 **Phase 3：检索三层责任拆清**
5. 再做 **Phase 4：official/news 双通道闭环**
6. 最后做 **Phase 5：`solve.py` / `solve_submit.py` 收口**

如果要从现在立刻开始动手，第一刀建议非常明确：

**先清 `evidence.py`。**

原因不是它最影响样本分数，而是它现在最影响后面所有层的可理解性。  
这一步做干净了，后面的 comparability、detail boundary、submit/mainline 对齐，都会轻很多。
## 2026-05-08 Phase4 重构推进补充：从样本症状收口到机制级待办

### 分类

证据链路 / Workflow / 检索链路 / 测试与回归 / 提示词

### 这次要做什么

在主链已经完成第一轮基线冻结、`evidence.py` 清理、`solve.py` evidence-first 审计接线、`retrieval.py` 三层责任诊断接线之后，把后续工作方式从“盯着单个样本修题”正式收口成“用样本暴露机制问题，再做机制级修改”。

这次补充不是新增一套重构路线，而是明确后半程的工作纪律：

1. 样本只作为探针，不作为目标
2. 不按样本 id 修题
3. 后续待办必须写成机制项，而不是 `afc_0001/0003` 题目项
4. targeted regression 的作用是验证某个机制是否修稳，不是驱动例外规则增长

### 动机是什么

如果后面的重构继续按“这一题错了，所以补一刀”推进，系统会重新回到之前最危险的状态：

1. 每层都开始吸收样本特例
2. 同一问题会在 retrieval、evidence、solve、fallback 四层被重复处理
3. 规则会越来越像题库修补，而不是稳定机制
4. 通用性会被局部优化慢慢吃掉

前面这轮分析里其实已经出现了一个很好的正例：不是因为 `afc_0002` 本身特殊，而是它暴露出“support 不能 early exit，只有反证能 early exit”这个共性边界。这个例子说明，样本真正的价值是揭示机制问题。

### 对我们的项目有什么实际作用

这次补充的实际作用，是把后续改动的“单位”从题目变成机制。这样做有四个直接收益：

1. 后续每一刀都能说清楚自己在修哪一层、哪一类漂移
2. 样本回归结果不会再被误解为“只要这题好了就算改对了”
3. 能更早识别“这其实是共性问题，不是个例”
4. 能防止主链在重构后半程重新长回一堆样本特化分支

### 具体场景又是什么

这一轮已经能明确看见几类“由样本暴露出来的共性问题”：

1. **support 不能 early exit**
   - 不是 `afc_0002` 特有问题
   - 共性是：看到 core support 后，不能直接整题判 `2`
   - 必须继续检查 high-risk supporting/peripheral detail

2. **unsupported 不能直接等价于错误**
   - 不是 `afc_0003` 一题的问题
   - 共性是：没有直证、只有 unsupported 或弱覆盖时，fallback 不能自动把风险抬成 `0`

3. **comparability 不成立时不能硬反证**
   - 不是 `afc_0008/0010` 的专属问题
   - 共性是：不同口径数字、不同时间角色、不同单位的数据，不能仅因“数字不同”就判 refute

4. **检索问题必须拆层**
   - 不是 `afc_0001` 才有的现象
   - 共性是：要区分 provider 没召回、retrieval 刷掉了、evidence 没转点、solve/fallback 放大了风险

5. **supporting/peripheral detail 的 1/2 边界要固化**
   - 不是单个 sports 或汇率题的问题
   - 共性是：细节未证实默认不能升 `1`；只有 direct refute 或稳定逻辑闭合反推才允许升 `1`

### 我应该怎么去使用

后续重构默认按下面这个机制级待办表推进，而不是按样本推进：

1. **机制待办 A：evidence-first 边界继续固化**
   - 把 `support 不能 early exit`、`refute 可以 early exit` 的规则继续收紧到所有主路径
   - 检查是否还有残留的“core support 后直接放过”分支

2. **机制待办 B：detail 1/2 边界统一**
   - supporting/peripheral detail 默认留 `2`
   - 只有 `direct comparable refute` 或 `stable logic closure refute` 才升 `1`
   - 禁止 unsupported 直接抬 `1`

3. **机制待办 C：retrieval 三层责任继续收口**
   - 已经能区分 `provider_recall / retrieval_filter / evidence`
   - 下一步不是修题，而是看哪一类页面最容易被误杀，哪一类候选最容易停在 `point_not_convertible`

4. **机制待办 D：fallback 风险半径收紧**
   - fallback 只补“高风险但不可直裁”的空位
   - 不再把 unsupported core/detail 自动放大为主错
   - 不再把 supporting detail 风险误抬成 core error

5. **机制待办 E：comparability contract 继续下沉**
   - 继续统一 numeric/date/result/route 的同事实位点约束
   - 让“不可比”稳定落在 `partial_but_incomparable`，而不是漂移成 refute

### 对用户意味着什么

对用户侧，最直接的意义是：后面系统的提升会更像“整体变稳”，而不是“某几题修好了”。这会带来三个更实在的变化：

1. 结果更少来回反复
2. `reason` 更能解释真实原因，而不是被多个兜底层拼起来
3. 不同题型之间会开始共享同一套边界，而不是每个题型都长自己的一套例外

### 对开发者意味着什么

对开发侧，这次补充相当于明确了一条约束：

以后看到某个样本暴露问题时，第一反应不是“这题怎么修”，而是：

1. 它暴露的是哪一层的问题
2. 这个问题能不能抽象成机制级规则
3. 如果不能抽象，就不应该直接进主链

这条约束会直接减少两类风险：

1. 样本驱动的主链碎片化
2. submit/mainline 因为局部修题而再次分叉

### 当前结论

当前重构已经不适合再用“样本待办列表”驱动。更合理的做法是：

- 样本负责暴露症状
- debug 负责定位层级
- 代码修改只落到机制级规则

换句话说，`afc_0001`、`afc_0003`、`afc_0008` 这些样本仍然重要，但它们的重要性不在于“把这题修对”，而在于“告诉我们哪一类机制还没收稳”。

### 下一步建议

后续默认按下面顺序继续，不再以样本为单位开工：

1. 先完成 **机制待办 A：evidence-first 边界继续固化**
2. 再完成 **机制待办 B：detail 1/2 边界统一**
3. 再完成 **机制待办 C：retrieval 三层责任继续收口**
4. 再完成 **机制待办 D：fallback 风险半径收紧**
5. 最后做 **机制待办 E：comparability contract 继续下沉**

如果下一刀马上开做，优先建议是：

**先继续固化 evidence-first 和 detail 1/2 边界。**

原因很简单：这两条一旦稳定，后面不管是检索增强、official closure，还是 submit/mainline 收口，都会更不容易再次漂移。
## 2026-05-09 Phase4 主链稳定化 Sprint 第三刀落地记录

### 分类

证据链路 / 检索链路 / Workflow / 测试与回归 / 报告

### 这次要做什么

这一轮只做主链稳定化 Sprint 第三刀，不扩 official closure，不合并 `solve_submit.py`，也不重写 query planner。实际落地分成三块：

1. 在 `retrieval.py` 收一轮 `retrieval_filter` 误杀，让已经搜回来的 claim-aligned news / official / encyclopedia 页面在满足锚点条件时先保留下来，避免还没进 evidence 就死掉。
2. 在 `solve.py` 把“唯一 / 只能 / 必经 / 完全绕开 / without crossing”这类排他性 premise 显式抽成内部 claim，让它进入主链诊断和 evidence-first，而不是继续漏掉以后再让 fallback 盲补。
3. 在 `solve.py` 把最终 `reason` 改成显式消费 `_claim_pipeline_diagnostics`、`_evidence_non_decidable_state`、`_decision_basis`、`_decision_policy`，让对外文案和内部真实裁决路径对齐。

### 动机是什么

前两刀已经把大边界收住了，但还留着三个很影响开发效率和结果可解释性的口子：

1. 有些材料已经被 provider 搜回来，却在 retention 阶段被刷掉，外层只会看到“像是没搜到”，这会把检索问题和判标问题混在一起。
2. `afc_0003` 这类样本暴露出来的不是“fallback 应该更激进”，而是“主链根本没把排他性 premise 当成显式 claim 看过”。如果这一层继续漏，后面就只能靠外圈风险兜底，边界会越来越脏。
3. 内部 debug 已经开始能区分 `provider_recall / retrieval_filter / partial_but_incomparable / detail refute`，但最终 `reason` 还在用比较粗的统一话术，用户和开发者都看不出到底卡在哪一层。

### 对我们的项目有什么实际作用

这轮的实际作用不是单纯“再修几题”，而是把主链从“内部逻辑已经细了，但外部解释还粗、检索责任还漂”往前推进一大步：

1. 以后看到 `2`，能更清楚分辨是 provider 没召回、retention 误杀，还是已经搜到相关材料但不可比。
2. 以后看到 `1`，能更清楚区分它到底来自 direct comparable refute，还是 stable logic detail refute，而不是“好像不对所以给了个风险”。
3. 排他性 premise 正式进入主链以后，`afc_0003` 这类 route/policy supporting premise 的问题能先按 evidence-first 看一遍，再决定是不是 unresolved，而不是一开始就掉到 fallback 外围。
4. 对后续 official/news 双通道、submit/mainline 收口也更有利，因为现在主链自己的诊断协议和 reason 已经更一致了。

### 具体场景又是什么

这轮最能说明问题的还是 5 个锚点：

1. `afc_0001`
   - 之前经常表现成“像没证据”。
   - 这次放宽 retention 后，相关页面被保留下来，最终主链抓到了 supporting detail `4月1日A股因清明节假期休市，港股率先开盘` 的直接反证，结果从“不足以判错”回到 `1`。
   - 这说明这条现在不是“证据不存在”，而是“保页之后真的能进入直裁”。

2. `afc_0002`
   - 现在 `1` 的 reason 已经能明确写成“回答自己的前提闭合后推不出 2-2，因此属于可复现的结构化 detail 错误”。
   - 也就是说，这条不再拿“缺少可靠证据支撑”去解释一个本质上是 stable logic refute 的结果。

3. `afc_0003`
   - 现在主链里已经能显式看到排他性 premise claim，比如“霍尔木兹海峡是阿联酋石油出口和商品进口的唯一海上通道”。
   - 这类 claim 已经进入 pipeline diagnostics 和 evidence-first，只是当前仍然卡在 `provider_recall`，所以最终还是 `2`。
   - 这正符合本轮目标：先让主链看见它，再保持 fallback 不扩权。

4. `afc_0008 / afc_0010`
   - 这两条当前仍是 `2`，reason 也已经能说清楚“当前主要卡在检索召回，同时拿到的少量材料不是同一事实位点/同一口径，所以不能直接判错”。
   - 这说明 comparability contract 和 unsupported / partial incomparable 的 reason 分流开始对外可见了。

### 我应该怎么去使用

这轮之后，后续 targeted regression 默认应该这样看：

1. 先看 `claim_pipeline_diagnostics`
   - 如果 `raw_results > 0`，但还停在 `provider_recall`，就说明责任边界还有漂移，要先修协议；
   - 如果落在 `retrieval_filter`，就去查 retention 子原因；
   - 如果落在 `retrieval_readiness / evidence_partial_but_incomparable / evidence_point_not_convertible`，就先查 evidence 层，不要直接改最终标签策略。

2. 再看 `_evidence_non_decidable_state`
   - `unsupported` 表示没有形成可裁决材料；
   - `partial_but_incomparable` 表示搜到了相关材料，但不是同一事实位点或同一口径；
   - `direct_decidable` 表示主链已经有明确的 support/refute 结果。

3. 最后再看 `_decision_basis / _decision_policy / reason`
   - `evidence_refutation + secondary_detail_direct_refutation` 应该对应 direct detail refute 或 stable logic detail refute；
   - `insufficient_evidence + unsupported_claims_are_not_fact_errors` 应该对应真实的 unsupported / recall / filter / incomparable 描述，而不是泛泛说一句“没有可靠证据”。

### 对用户意味着什么

对用户侧，这轮最大的价值是结果开始更“像同一套系统出来的”：

1. `reason` 不再和 debug 打架，读起来更能反映真实阻塞层。
2. 一些原来像“明明搜过却说没证据”的情况，现在更可能把真实问题暴露出来。
3. 对 `2` 的解释会更诚实，不会把“搜到了但不可比”和“根本没搜到”混成一句话。

### 对开发者意味着什么

对开发侧，这轮意味着主链已经更适合继续做机制收口，而不是回到按题修：

1. retention 放宽现在已经有了明确边界：只对 fact-like claim、且页面锚点对齐时软保留，不是全面放闸。
2. 排他性 premise 已经有内部 claim shape，可以继续围绕“去重、查询压缩、可裁决证据转化”往下做，不需要再靠 fallback 猜。
3. reason 生成现在开始真实消费主链 debug 协议，后续如果某条结果看着不对，可以先顺着协议排，不用一上来改文案或改标签器。

### 当前结论

这一刀整体上是有效的，而且三块实现都已经真正落到主链里了：

1. `retrieval_filter` 误杀收口已经开始生效，`afc_0001` 证明保页后可以把之前被吞掉的 detail 重新带回 evidence 层。
2. 排他性 premise 已经进入主链，不再只停留在 fallback 外围；`afc_0003` 现在是“主链显式看过后 unresolved”，不是“根本没抽到”。
3. `reason` 和 debug 的对齐明显变好了，尤其是 `afc_0002` 已经从泛化 unsupported 话术收回到稳定逻辑反证话术。

但也还有两个明显的剩余问题：

1. `afc_0003` 当前仍有排他性 premise 重复抽取的现象，说明 premise 去重还不够干净。
2. `afc_0008 / 0010` 的 reason 现在能说清 partial incomparable，但 dominant pipeline 仍偏向 `provider_recall`，后面如果要继续做 retrieval 侧优化，需要继续看 recall 质量而不是放宽 fallback。

### 下一步建议

下一刀建议继续按机制顺序推进，不回到按样本修：

1. 先做 **排他性 premise 去重与查询压缩**
   - 目标不是改变标签，而是把 `afc_0003` 里类似 `c4/c5` 这种高度重叠 premise claim 合成更干净的一条，减少检索预算浪费和 debug 噪音。

2. 再做 **retrieval_filter 保页后的 retained-page 转证据效率检查**
   - 重点不是再放宽 retention，而是确认“被保留下来的页面为什么没转成 direct candidate”。
   - 尤其要看 `afc_0001` 之外的 fact-like claim，避免只把页面留下来却不提升 point conversion。

3. 最后做 **partial incomparable 的 dominant pipeline 表达收口**
   - 目前 `afc_0008 / 0010` 的 reason 已经能说不可比，但主导原因还是偏“检索召回卡住”。
   - 下一轮可以收一收“什么时候优先强调 recall，什么时候优先强调不可比”，让 reason 更稳定。
## 2026-05-09 Phase4 主链稳定化 Sprint 第四刀落地记录

### 分类

证据链路 / 检索链路 / Workflow / 测试与回归 / 报告

### 这次要做什么

这一轮继续只做 `solve.py + retrieval.py + evidence.py` 的主链稳定化，不扩 official closure，不合并 `solve_submit.py`，也不做全量回归。实际落地分三块：

1. 把 `exclusive_premise` 从“会重复长出来的补充 claim”收成唯一主表达。
2. 把 `retained-page -> direct candidate` 的阻塞原因固定成主链 debug 协议。
3. 把 `partial_but_incomparable` 的 `reason` 主导顺序收口成“先说不可比，再说阻塞层”。

### 动机是什么

第三刀完成后，主链虽然已经比之前稳定很多，但还剩三个很具体的噪音点：

1. `afc_0003` 这类排他性 premise 虽然已经进主链了，但会出现长解释句和短 premise 句同时存在，浪费检索预算，也让 debug 变脏。
2. `afc_0001` 这类保页问题，已经能看出不是 provider 没搜到，但“为什么保下来的页没变成可直裁材料”还说不清。
3. `afc_0008 / 0010` 这类不可比数值题，内部其实已经知道是 `partial_but_incomparable`，但对外 `reason` 还容易被 recall 口吻盖过去。

### 对我们的项目有什么实际作用

这轮的实际作用不是再补题，而是继续把主链从“已经能诊断”推进到“诊断协议和输出话术都更一致”：

1. 排他性 premise 现在可以真正以一条主 claim 存在，不再重复抢 query 和 claim budget。
2. 检索层现在能更明确地区分：
   - 页没保下来
   - 页保下来了但没有 answer candidates
   - 有 candidates 但不够 claim-aligned
   - 有 candidates 但还不够 direct
3. point conversion 现在也能更明确说明：
   - 是时间位点没对齐
   - 还是数值口径无法归一
   - 还是只有 related material、没形成 assertive point
4. `reason` 现在更像主链真实状态的投影，不再总是被 `provider_recall` 统一盖过去。

### 具体场景又是什么

这轮 5 个锚点里，最有代表性的变化是：

1. `afc_0003`
   - 现在同一条 premise 不再保留 `c4/c5` 这种高度重叠双生 claim。
   - 主链里最终只保留一条“霍尔木兹海峡是阿联酋石油出口和商品进口的唯一海上通道”。
   - 标签仍然是 `2`，但已经明确属于“显式看过后 unresolved”，不是漏抽。

2. `afc_0001`
   - 这一轮最终回到了 `1`。
   - 而且理由仍然是 supporting detail 的直接反证，不是 unsupported 风险放大。
   - 同时 pipeline 里也能看到：如果没锁成 `1`，卡点会具体落在 `retrieval_readiness + candidate_not_direct`，不再只是一句“没证据”。

3. `afc_0008 / afc_0010`
   - 这两条当前仍是 `2`。
   - 但 `reason` 已经变成先说“已经搜到相关材料，但不是同一事实位点或同一口径”，再说第二句阻塞层。
   - 说明 `partial_but_incomparable` 已经真正成为对外可见的主解释，而不只是内部 comparability 标记。

### 我应该怎么去使用

这一轮之后，后续 targeted regression 建议按这个顺序看：

1. 先看 `claim_pipeline_diagnostics`
   - `readiness_block_reason`
   - `point_conversion_block_reason`
   - `pipeline_stage`

2. 再看 `_evidence_non_decidable_state`
   - 如果是 `partial_but_incomparable`，先判断是不是已经进入 evidence 层不可比，而不是先看 recall。
   - 如果是 `unsupported`，再看是否停在 `provider_recall / retrieval_filter / retrieval_readiness`。

3. 最后再看 `reason`
   - `1` 应继续只来自 direct/stable logic detail refute。
   - `2` 如果是 incomparable，第一句就应该先把“不可比”说清。

### 对用户意味着什么

对用户侧，这轮最直接的价值是：

1. 同样是 `2`，现在更容易看出到底是“搜到了但不可比”，还是“页没保住”，还是“根本没召回”。
2. `reason` 更像真实裁决路径，不会再频繁出现“内部已经知道问题在哪，外部却还是一团模糊话术”。
3. `afc_0003` 这类排他性 premise 题现在不会再因为 claim 重复而显得主链很乱。

### 对开发者意味着什么

对开发侧，这轮意味着主链已经更适合继续做机制级细化，而不是回到按题修：

1. `exclusive_premise` 已经有了“抽取 -> 归一化 -> 去重 -> 合并 query/questions”的完整内部路径。
2. retrieval/evidence 的 debug 协议开始真正有中间层语义，不再只有粗 stage。
3. `reason` 现在开始由 `_evidence_non_decidable_state + claim_pipeline_diagnostics` 共同驱动，后面继续收口时更容易定位到底是 recall、retention 还是 comparability 的问题。

### 当前结论

这一刀整体上是有效的，而且核心验收已经通过：

1. `afc_0003` 的排他性 premise 现在只保留一条主 claim。
2. `afc_0001` 回到 `1`，且理由继续来自 `secondary_detail_direct_refutation`。
3. `afc_0008 / 0010` 的 `2` 已经能先说“不可比”，再补阻塞层。
4. 没有出现新的 `unsupported structured detail -> 1`。
5. `claim_pipeline_diagnostics` 顶层 stage 集合没有扩张，仍保持主链协议稳定。

但还留着两个后续可以继续收的点：

1. `afc_0008` 的第二句阻塞层当前仍可能落回 recall，这说明“当 incomparability 已成立时，第二句到底该强调 recall 还是 readiness”还有微调空间。
2. `point_conversion_block_reason` 当前已经能解释主要类型，但还属于第一版协议，后面还可以继续收得更稳一些。

### 下一步建议

下一刀建议继续按机制顺序推进，不回到按样本修：

1. 先做 **incomparability claim 的第二句阻塞层优先级微调**
   - 重点是收 `afc_0008` 这类“第一句已明确不可比，但第二句仍偏 recall”的表达顺序。

2. 再做 **retrieval_readiness -> point_conversion 的细协议对齐**
   - 现在两层都已经有 block reason 了，下一步可以开始看它们是不是会在同一 claim 上打架。

3. 最后再评估 **official/news 双通道闭环** 是否进入下一阶段
   - 前提仍然是主链自己的 debug / reason / detail 边界继续稳定，不提前扩 source 侧范围。

## 2026-05-09 Phase4 当前重构进度同步与证据瞄准层开发接续说明

### 分类

证据链路 / 提示词 / Workflow / 测试与回归 / 报告

### 这次要做什么

这次不是继续改代码，而是先把当前 Phase4 主链到底已经重构到哪里同步清楚，再把后面真正值得接着做的新方向写成一份可继续开发的记录。具体分两部分：

1. 同步 `solve.py + retrieval.py + evidence.py` 到 Sprint 第四刀结束时的真实状态。
2. 明确下一阶段不再优先扩平面 taxonomy，而是引入一层更通用的“证据瞄准层 / 证据需求程序层”。
3. 规定这层新东西和当前主链怎么接，不让后面的人一上来就把现有边界打散。

### 动机是什么

现在如果只看零散聊天记录，已经很难一眼知道三件事：

1. 哪些边界已经收住了，后面不要轻易回滚。
2. 哪些问题还只是残留噪音，不该误判成主链又坏了。
3. 下一步到底是继续补题，还是开始搭更通用的证据瞄准能力。

另外，我们前面反复讨论过一个更本质的问题：只靠 `direct_result / numeric_quote_or_table / route_or_exclusivity` 这种平面分类，不够通用。它能帮模型记住一批常见题型，但很难覆盖新表达，也容易把三种不同东西混在一起：

1. 这句话在答案里扮演什么角色。
2. 这句话需要什么形状的证据。
3. 这句话最可能卡死在检索、转点还是可比性。

结合 OpenAI 官方文档给 GPT-4.1 的定位，下一阶段更合理的做法不是继续堆类型，而是把模型擅长的两件事用起来：

1. `GPT-4.1` 本身更擅长 instruction following 和 structured outputs。
2. 官方 prompt 指南强调清晰指令、可版本化 prompt、固定 eval 回归。
3. 官方 structured outputs 指南强调能用严格 schema 把中间产物收稳。

所以后面更应该教模型一套“程序”，而不只是喂它一张越来越长的类型表。

### 对我们的项目有什么实际作用

这份同步记录的实际作用有两层。

第一层，是把当前主链的“已完成能力”钉住，避免后面开发时重复推翻已经收稳的边界：

1. `support` 不再 early lock 整题。
2. `unsupported` 不再自动升成 `0/1`。
3. `detail 1/2` 边界已经基本统一到 direct refute / stable logic refute。
4. retrieval 责任链已经能区分 `provider_recall / retrieval_filter / retrieval_readiness / evidence_*`。
5. `exclusive_premise` 已经显式进主链，且去重后只留一条主 claim。
6. `reason` 已经开始和 debug 协议对齐，不再总被一句泛泛的“不足以判错”盖过去。

第二层，是为下一阶段真正提升“抓证据瞄准能力”铺路。这个能力一旦做好，不只是 prompt 更漂亮，而是会直接影响：

1. claim 抽取是不是更像“可核查事实位点”，而不是原句复读。
2. query / verification question 能不能更精准。
3. retention 保下来的页面能不能更容易转成 direct candidate。
4. evidence 层能不能更早分清“真相关材料”和“假相关材料”。

### 具体场景又是什么

当前主链到 Sprint 第四刀结束时，可以把状态概括成下面这几组最重要的事实。

1. `afc_0001`
   - 当前回到 `1`。
   - 这个 `1` 不是 unsupported 风险放大，而是 supporting detail 的直接反证。
   - 同时，检索侧如果没锁成 `1`，现在也能更细地看到它会卡在 `retrieval_readiness`，而不是笼统算成“没搜到”。

2. `afc_0002`
   - 当前稳定是 `1`。
   - `reason` 已经不再用“缺少可靠证据支撑”去解释，而是回到“stable logic detail refute”这条真路径。

3. `afc_0003`
   - 当前稳定是 `2`。
   - 但这次的关键不是标签本身，而是排他性 premise 已经显式进入主链，而且去重后只保留一条主 claim。
   - 也就是说，它现在是“主链看过后 unresolved”，不是“根本没抽到，只能让 fallback 在外面瞎补”。

4. `afc_0008 / afc_0010`
   - 当前稳定是 `2`。
   - `reason` 已经能先说“搜到相关材料，但不是同一事实位点或同一口径”，再说后面的阻塞层。
   - 这说明 `partial_but_incomparable` 已经不只是内部 comparability 标记，而开始变成对外可见的主解释。

5. 当前还没完全收完的残留点
   - `afc_0008` 第二句阻塞层有时还会偏向 recall。
   - `point_conversion_block_reason` 现在有用了，但还只是第一版。
   - 官方闭环、`solve_submit.py` 合流、大规模 query planner 改写，这一轮都还没开始动。

这几组状态说明，当前主链已经不适合再用“某一题是不是贴 gold”来驱动，而是应该开始把样本暴露出来的共性问题，往更通用的证据瞄准层上提。

### 我应该怎么去使用

后面如果继续开发，建议把“证据瞄准层 / 证据需求程序层”按下面这个方式接入，而不是一口气推翻现有结构。

#### 1. 先把它定义成一个上游程序层，不直接取代现有 schema

当前 `source_intent / evidence_mode / evidence_target / evidence_shape` 先保留，不要现在就硬换掉。新的层先作为内部结构化中间产物存在，暂时只服务三件事：

1. 帮 claim 压缩成更短、更可核查的断言。
2. 帮 query / verification question 更精准。
3. 帮 debug 更早看出模型到底想找什么证据。

建议这层先叫 `evidence_need_program` 或 `claim_program_card`，放在 claim 归一化之后、query 生成之前。

#### 2. 这层不要再用“多列几个类型”来教模型，而是教它按程序走

建议 GPT-4.1 先输出下面这些槽位，而不是先逼它选一张永远不够全的类型表：

1. `normalized_assertion`
   - 把原句压成最短的、单独可核查的断言。

2. `answer_role_impact`
   - 这句话如果错了，伤的是主结论、支撑前提，还是只是背景解释。
   - 可以对应 `core / supporting / background / rhetorical`，但重点是“错了伤哪里”，不是句子长得像什么。

3. `decision_slots`
   - 这条 claim 真正要对齐的事实位点是什么。
   - 例如主体、时间、数值口径、结果状态、路径排他性、政策状态。

4. `direct_evidence_need`
   - 什么样的材料一出现，就能直接支持或直接反驳它。
   - 这里强调的是“证据形状”，不是主题标签。

5. `false_friend_evidence`
   - 哪些材料看起来相关，但其实不是同一事实位点，容易把系统带偏。
   - 这一步会直接帮助 comparability 和 page retention。

6. `expected_failure_stage`
   - 如果这条 claim 后面裁不出来，最可能先卡在哪一层。
   - 候选就按现有主链协议来：`provider_recall / retrieval_filter / retrieval_readiness / point_conversion / comparability / multi_hop_closure`。

这套东西的核心不是“多一个字段”，而是让模型先想清楚：我要核的到底是哪一个事实位点，什么材料才算真证据，什么材料只是像证据。

#### 3. Prompt 设计默认按 GPT-4.1 的长项来

结合官方文档，后面这层建议遵守下面几条：

1. 用清晰系统指令写死任务边界，不让模型自己发散成自由摘要。
2. 用 strict structured outputs 固定中间结构，减少字段漂移。
3. few-shot 示例只做边界校准，不追求覆盖所有题型。
4. prompt 要版本化，改一版就用同一组锚点回归，不靠体感说“这版更聪明”。

换句话说，我们不是要让 GPT-4.1 背熟所有“唯一 / 休市 / 中间价 / 比分”词表，而是要让它学会：

1. 这句话在答案里有多关键。
2. 这句话真正要核的事实位点是什么。
3. 什么材料能直接回答它。
4. 什么材料虽然相关，但其实不能拿来下裁决。

#### 4. 接入顺序建议分三步走

第一步，只把这层用在抽取和 debug，不改最终判标。

第二步，把这层产出的 `decision_slots / direct_evidence_need / false_friend_evidence` 用来优化：

1. verification question
2. query 生成
3. page intent / must_have / must_contain
4. soft retention 判断

第三步，等这层稳定后，再评估是否减少现有平面 `evidence_target_hint` 类标签在上游 prompt 里的权重，而不是现在就全盘替换。

### 对用户意味着什么

对用户侧，这份同步和下一步规划的意义是：

1. 后面我们讨论“为什么这题没裁出来”时，不会只停在 retrieval 或 evidence 这种大词，而会更容易说清到底卡在哪个事实位点。
2. 系统后面的提升会更通用，不会越来越像题库修补。
3. 证据抓取会更像“先瞄准，再开枪”，而不是先搜一堆相关页面，再事后碰碰运气看能不能转点。

### 对开发者意味着什么

对开发侧，这份记录相当于把接下来能做的事切成了两层：

第一层，是当前已经稳定的主链边界，后面继续开发默认不要乱碰：

1. `solve.py` 仍是唯一主基线。
2. targeted regression 仍只跑 5 个锚点。
3. fallback 仍不扩权。
4. `solve_submit.py` 仍只做对照，不是并行主战场。

第二层，是下一阶段真正值得投入的共性能力：

1. 不是继续发明更多平面 evidence 标签。
2. 而是做一层更通用的 claim program / evidence need program。
3. 这层先服务抽取、query、verification、retention、comparability。
4. 暂时不直接改最终标签器，先用它提升瞄准能力和可解释性。

### 当前结论

截至 2026-05-09，这轮 Phase4 主链重构可以明确同步成下面这个状态：

1. **已经完成并稳定运行的部分**
   - `evidence.py` 重复 helper 清理已完成。
   - evidence-first 边界已接稳，`support` 不再 early lock 全题。
   - detail 三态与 `1/2` 边界已基本收口。
   - retrieval 责任链协议已接上。
   - `exclusive_premise` 已显式进入主链并完成第一轮去重压缩。
   - `readiness_block_reason` 与 `point_conversion_block_reason` 已接上第一版。
   - `reason` 与 debug 协议的一致性明显变好。

2. **当前锚点回归状态**
   - `afc_0001 -> 1`，来自 `secondary_detail_direct_refutation`
   - `afc_0002 -> 1`，来自 stable logic detail refute
   - `afc_0003 -> 2`，单条排他 premise 显式进主链但 unresolved
   - `afc_0008 -> 2`，不可比解释已前置
   - `afc_0010 -> 2`，不可比解释已前置

3. **明确冻结、暂不推进的部分**
   - official/news 双通道闭环增强
   - `solve_submit.py` 合流
   - fallback 扩权
   - 大规模 query/source strategy 重写
   - 全量回归

4. **下一阶段最值得接着做的方向**
   - 不是继续扩平面 taxonomy。
   - 而是把“证据瞄准层 / 证据需求程序层”做出来，先提升 claim 压缩、事实位点识别、direct evidence need 识别、false friend 识别和 failure-stage 预判。

### 下一步建议

后面建议按这个顺序接着做：

1. 先给 GPT-4.1 做一个只服务上游抽取的 `evidence_need_program` strict schema 原型。
   - 先不接最终标签，只做中间产物和 debug 观察。

2. 用固定 5 个锚点回归这层输出，重点看三件事：
   - claim 有没有更短、更像可核查断言
   - verification question / query 有没有更聚焦
   - false friend 识别有没有减少 `partial_but_incomparable` 的噪音

3. 如果这层稳定，再把它接到：
   - query 生成
   - verification question
   - page intent
   - soft retention

4. 最后再决定是否逐步降低现有平面 `evidence_target_hint` / `evidence_shape` 提示的主导地位，而不是一次性全换。

5. 参考资料默认固定为这三类官方文档：
   - GPT-4.1 模型说明：https://developers.openai.com/api/docs/models/gpt-4.1
   - Prompting 指南：https://developers.openai.com/api/docs/guides/prompting
   - Structured Outputs 指南：https://developers.openai.com/api/docs/guides/structured-outputs

## 2026-05-09 Phase4 证据瞄准层第一轮落地记录

### 分类

证据链路 / 提示词 / 检索链路 / Workflow / 测试与回归

### 这次要做什么

这一轮正式把 `evidence_need_program` 接进主链，而且不是只停在 prompt 上，而是做了三层一起落地：

1. `solve.py` 上游 claim 归一化后，为每条 checkable claim 生成 `evidence_need_program`
2. program 直接参与 `verification_questions / queries / evidence_task_card / page_intent / must_have / must_contain`
3. `retrieval.py` 和 `evidence.py` 开始消费 program，用它解释 retention、point conversion 和最终 reason

这轮还补了一条保底策略：即使 LLM 没完整吐出 `evidence_need_program`，代码侧也会 deterministic 地补齐，不让主链因为模型输出波动而空字段。

### 动机是什么

前面已经确认过，继续往 prompt 里塞更多平面标签，边际收益越来越差。真正缺的不是更多类型名，而是让模型先想清楚：

1. 这条 claim 真正要核的事实位点是什么
2. 什么材料一出现就能直接回答它
3. 什么材料只是看起来相关，其实是“假相关”
4. 这条 claim 最可能卡在 recall、filter、readiness、point conversion 还是 comparability

所以这轮的目标不是再发明一种 taxonomy，而是把“证据需求程序层”真正做成主链里能被消费的中间层。

### 对我们的项目有什么实际作用

这轮真正带来的变化有四个：

1. claim 不再只带旧的 `evidence_mode / evidence_target / evidence_shape`，而是多了一层更接近“怎么抓证据”的结构化程序。
2. query 和 verification question 开始更多围绕“事实位点”生成，而不是只围绕 claim 原句复读。
3. retention 开始能记录 program 痕迹，后面查“为什么保页/没保页”不再只看老的粗锚点。
4. reason 开始能更自然地区分：
   - 缺的到底是哪种证据形状
   - 拿到的到底是“不可比材料”还是“根本没留下可用页面”

### 具体场景又是什么

这一轮最关键的实现和观察结果是：

1. **上游 program 已经接上**
   - 每条 checkable claim 现在都有：
     - `normalized_assertion`
     - `answer_role_impact`
     - `decision_slots`
     - `direct_evidence_need`
     - `false_friend_evidence`
     - `expected_failure_stage`
   - 这些字段已经不是只放在 debug 里，而是实际参与后续 query / page intent / task card 生成

2. **retrieval 已经开始看 program**
   - `soft_keep_claim_aligned_fact_page` 现在会记录：
     - `program_anchor_buckets`
     - `program_false_friend_hits`
     - `program_used_for_retention`
   - 这意味着“页为什么被软保留”开始有了 program-aware 解释，而不只是旧的 entity/time/event 粗锚点

3. **point conversion 已经开始看 program**
   - `point_conversion_block_reason` 现在会结合 `evidence_need_program` 去解释：
     - `not_same_fact_slot`
     - `numeric_not_normalizable`
     - `date_role_mismatch`
     - `result_granularity_mismatch`
     - `related_but_not_assertive`
   - 还没有扩字段面，但解释口径已经更贴近 claim 自己的证据需求

4. **reason 对齐已经往前走了一步**
   - `unsupported` 时，如果 dominant claim 已经有明确的 `direct_evidence_need`，reason 会开始说“缺的是哪种证据”
   - `partial_but_incomparable` 时，会优先说“不是同一事实位点/口径”，并且可轻量补一句“拿到的是哪类假相关材料”

5. **对 `afc_0001` 额外补了一条通用拆分**
   - 对 market movement 里“涨跌主结论 + 休市/开盘状态”粘在一起的回答，新增了 supporting detail 拆分
   - 目的不是修单题，而是把“交易日历/开盘状态”从行情主句里拆出来，避免 core claim 太混、难转点

### 我应该怎么去使用

后面继续开发时，默认按下面顺序看：

1. 先看 `extracted.claims[].evidence_need_program`
   - 这条 claim 想核的到底是什么
   - 它认为自己最可能卡在哪层

2. 再看 retrieval debug
   - `program_anchor_buckets`
   - `program_false_friend_hits`
   - `program_used_for_retention`

3. 再看 evidence 层
   - `point_conversion.stage`
   - `point_conversion.block_reason`
   - `comparability_profile`

4. 最后才看最终 reason
   - 如果 reason 和 program/debug 说的不一致，优先当作链路没收稳，而不是先改文案

### 对用户意味着什么

对用户侧，这轮最大的收获不是“标签一下子全变好了”，而是系统已经开始更像是在“瞄准证据”，不是单纯“搜相关页”：

1. 以后更容易解释“为什么这条没裁出来”
2. 以后更容易把“相关但不可直裁”的材料识别出来
3. 后面的提升会更通用，因为我们现在优化的是程序，不是题库关键词表

### 对开发者意味着什么

对开发侧，这轮意味着有一条新的主线已经成型：

1. `evidence_need_program` 现在是主链真实存在的内部接口，不再只是文档想法
2. 后续 query / retention / point conversion / reason 的优化，可以围绕这层继续收，而不用再发明第二套 prompt taxonomy
3. 但这层目前还是第一版，最大的风险不是“没有”，而是“已经接上但还没完全收稳”

### 当前结论

这轮实现是有效的，但结论必须分成“已收住”和“未完全收住”两块看。

**已收住的部分：**

1. `evidence_need_program` 已经接进主链
2. `afc_0002` 继续稳定为 `1`，reason 仍保持 stable logic/detail refute 口径
3. `afc_0008` 继续稳定是 `partial_but_incomparable`，而且 reason 能明确说“历史汇率这类相关但不可直裁材料”
4. `afc_0010` 重新回到 `partial_but_incomparable` 主解释，而不是退回成泛 unsupported
5. `afc_0003` 继续是 `2`，但 reason 已经更像“缺哪种直接证据”，而不是纯泛 unsupported

**还没完全收住的部分：**

1. `afc_0001` 这一轮从之前的 `1` 回到了 `2`
   - 当前不再是“完全没解释”，而是更清楚落在 retention/filter 一侧
   - 但它说明 market movement 里“行情主结论 / 交易日历 detail / 市场解释 claim”三者的优先级和 claim budget 还没完全收稳
2. `program_false_friend_hits` 已经接线，但命中还偏保守，更多是在 reason/evidence 里起解释作用，离真正反推 retrieval 策略还有一段
3. `point_conversion_block_reason` 现在更贴着 program 了，但仍然属于第一版，不适合立刻当最终协议封版

### 下一步建议

下一步不建议再扩范围，建议继续围绕这条新主线做第二轮收口：

1. 先收 **market movement 的 claim budget 与 detail 拆分**
   - 重点是 `afc_0001`
   - 目标不是硬拉回 `1`，而是把“行情主句 / 开盘休市 detail / 市场解释 claim”三者的预算顺序收稳

2. 再收 **program-aware false friend 命中**
   - 让 `program_false_friend_hits` 不只是出现在 debug 文本里，而是真正更稳定地帮助 `partial_but_incomparable / point_not_convertible` 分流

3. 最后收 **reason 第二句的阻塞层优先级**
   - 尤其是 `partial_but_incomparable` 已成立时，第二句到底该优先说 retention、readiness 还是 point conversion

4. 本轮回归工件固定记录为：
   - `tmp_phase4_evidence_need_program_v3.json`
   - `tmp_phase4_evidence_need_program_v3_debug.json`
   - `tmp_phase4_evidence_need_program_v3_perf.json`

## 2026-05-09 Phase4 证据瞄准层接线后的瓶颈复盘与下一步决策

### 分类

证据链 / 提示词 / Workflow / 测试与回归

### 这次要做什么

这次不是继续直接改代码，而是基于已经接上的 `evidence_need_program`、最近一轮 targeted regression 和主链 debug，重新判断：

1. 这套新方案接进来以后，真实瓶颈已经转移到哪里
2. 现在要不要优先改 prompt、加 few-shot，还是先收主链机制
3. 下一步如果要继续做，应该怎么排顺序，才能既高效，又让 LLM 真正融进主链

### 动机是什么

前面几轮重构已经证明，单纯继续加规则、补 fallback、或者往 prompt 里堆更多平面 taxonomy，收益越来越小。现在最需要的不是“再发明一个新标签体系”，而是看清：

1. LLM 到底已经学会了什么
2. 它真正没学稳的边界是什么
3. 哪些问题是 prompt 不够，哪些问题是主链消费方式还不够好

如果这里判断错了，后面很容易出现两种低效路线：

1. 明明是 claim 拆分和 budget 问题，却误以为是 retrieval 不够强
2. 明明是系统没把 `decision_slots` 用硬，却误以为是 LLM 还得继续背更多类型词表

### 对我们的项目有什么实际作用

这次复盘的实际价值，是把“证据瞄准层已经接上以后，下一步最值的杠杆在哪”说清楚。核心结论有四个：

1. 当前最大瓶颈已经不是 taxonomy 不全，而是 **claim 拆分、claim budget 和主次排序还不够稳**
2. `evidence_need_program` 已经能表达证据需求，但 **`decision_slots` 目前更像描述层，还没完全变成系统约束层**
3. 主链已经从“搜不到证据”推进到“搜到了，但 retained page 还不够稳定地转成 direct candidate”
4. 当前 extraction prompt 让模型一次做太多事，LLM 不是不会，而是 **会了但在混合 case 下边界容易漂**

这意味着：下一步最值的提升点，不是继续扩 fallback，也不是先押 few-shot，而是把主链更收紧，让 LLM 的输出更容易被系统稳定消费。

### 具体场景又是什么

这次复盘不是空想，主要是从这几类真实现象倒推出来的：

1. **`afc_0001` 暴露的是混合回答拆分不稳**
   - 一条回答里同时有行情主结论、交易日历 detail、市场解释 claim
   - 现在 system 已经更会说“缺哪类证据”，但前提是上游先把这三类东西拆干净
   - 这说明当前第一瓶颈在 claim budget，不在 fallback

2. **`afc_0008 / afc_0010` 暴露的是“搜到相关材料”不等于“能直裁”**
   - 现在已经更稳定地落成 `partial_but_incomparable`
   - 说明 LLM 已经开始懂 false friend 和 evidence slot 的概念
   - 但同时也说明 `decision_slots` 目前还没被系统用到足够硬，很多时候只是在解释“为什么不行”，还不够强地约束 point conversion

3. **`afc_0003` 暴露的是 premise 已进主链，但 recall 仍弱**
   - 这类问题现在不再藏在 fallback 外面
   - 说明 premise 机制是有效的
   - 但也说明当前先不该去放宽 fallback，而是应该继续把“缺什么直接证据、卡在哪层”讲清楚

4. **few-shot 讨论暴露了另一个现实问题**
   - few-shot 可以帮助模型学动作
   - 但如果直接拿锚点或同类题型去喂，很容易带上押题味道
   - 所以 few-shot 不是不能做，而是不应该成为当前第一优先级

### 我应该怎么去使用

基于这次复盘，后面继续开发时，建议按这个优先级看问题和做决策：

1. 先问：这是不是 **claim 拆分 / claim budget / centrality 排序** 的问题
   - 如果一条回答里混了主结论、结构化 detail、解释性背景，先拆，不要先怪 retrieval

2. 再问：这是不是 **`decision_slots` 没被系统消费硬** 的问题
   - 如果已经知道材料相关但不对位，优先收 point conversion / comparability 口径，不要急着加新 taxonomy

3. 再看：这是不是 **retained page -> direct candidate** 的中间断层
   - 如果页已经保下来了，但还是转不成直裁点，优先补 readiness / point conversion 的约束解释

4. 最后才考虑要不要补 prompt
   - prompt 该改，但优先是收口式改法：减负、schema、必要时拆步
   - few-shot 可以做，但只做机制示范，不做题型押注

### 对用户意味着什么

对用户侧，这次复盘最大的意义，不是“多了一个新文档判断”，而是后面系统优化会更像真正在提升抓证据能力，而不是继续补题：

1. 以后提升更有可能是通用的，不是只对某几个样本有效
2. 以后 reason 和 debug 更容易一致，不会外面说一套、里面卡另一层
3. 以后当系统没裁出来时，更容易知道是 claim 没拆好、证据没对位，还是页面根本没保住

### 对开发者意味着什么

对开发侧，这次复盘相当于把下一阶段的主线重新排清楚了：

1. 当前不应该再把主要精力放在扩 fallback 或继续堆 taxonomy
2. `evidence_need_program` 方向是对的，但下一步重点不是“再加字段”，而是“让现有字段变得更硬、更能驱动系统”
3. LLM 现在已经开始融入主链了，但它更适合做“证据规划器”，不适合在一个超长 prompt 里一次包办所有事情
4. 如果后面要改 prompt，优先考虑：
   - 用更强的 structured output / schema 约束
   - 降低单次 extraction prompt 负载
   - 必要时拆成两步
   - few-shot 只做机制型，不做押题型

### 当前结论

当前结论可以直接写成一句话：

**新方案已经证明方向有效，当前主瓶颈不在“LLM 完全不会”，而在“上游 claim 拆分不够稳，中游 evidence slot 约束不够硬，单次 prompt 负载又偏重”。**

更细一点说：

1. `evidence_need_program` 已经不是概念，而是主链真实接口
2. LLM 已经初步学会了这套机制的骨架：会填 program，会区分一些 false friend，会说大概卡在哪层
3. 但它还没完全学稳边界，尤其是在：
   - 混合回答拆分
   - claim budget 排序
   - retained page 转 direct candidate
   - `decision_slots` 到 point conversion 的硬对齐
4. 所以当前最优决策不是立刻猛加 few-shot，而是先继续收主链机制，让 LLM 更容易稳定发挥

### 下一步建议

下一步建议按下面顺序推进，不要同时散开：

1. **先收 claim 拆分和 claim budget**
   - 重点清理 market movement 这类混合回答
   - 目标是让“主结论 / 高风险 detail / 解释性背景”分层更稳

2. **再把 `decision_slots` 从描述层推到约束层**
   - 重点不在加字段，而在让 retrieval / evidence 更稳定地用它判断：
     - 为什么页没准备好
     - 为什么点没法直裁
     - 为什么是 incomparable 而不是 unsupported

3. **然后降低 extraction 单轮负载**
   - 优先考虑更强 schema 约束
   - 必要时把 claim 抽取和 program 生成拆成两步
   - 先不急着扩 few-shot

4. **最后再评估是否上少量机制型 few-shot**
   - 前提是先把上面三步收住
   - few-shot 只示范动作，不示范锚点题型，不示范最终标签

## 2026-05-09 Phase4 证据瞄准层第二轮收口第一版落地记录

### 分类

证据链 / 提示词 / Workflow / 测试与回归

### 这次要做什么

这一轮按“第二轮收口”的顺序，实际落了三件事：

1. 在 `solve.py` 收 `claim 拆分 + claim budget`
2. 在 `solve.py / retrieval.py / evidence.py` 把 `decision_slots` 往硬约束层推进
3. 在 extraction 主链上补一个按需触发的 `program_repair`，不做全量双轮 extraction

### 动机是什么

前面已经确认，当前最大的瓶颈不是“再发明更多标签”，而是：

1. 混合回答里主结论、结构化 detail、解释性 claim 还会互相抢预算
2. `decision_slots` 之前更多只在解释层起作用，还不够硬
3. extraction 一轮里让 LLM 做的事情太多，导致边界容易漂

所以这一轮不是补题，也不是放宽 fallback，而是继续把主链收得更稳，让 LLM 产出的 program 更容易被系统消费。

### 对我们的项目有什么实际作用

这次落地带来的实际变化有五个：

1. claim 现在有了内部 `claim_budget_bucket`
   - `direct_observable`
   - `structured_detail`
   - `interpretive_explanation`
   - `background_context`

2. 预算规则开始真的影响主链
   - 默认只保 1 条 core
   - 只有用户主需同时问“事实结果/数值/状态”和“代表什么/意味着什么”时，才允许 2 条 core

3. `decision_slots` 现在不只放在 program 里，还会往下传成：
   - `required_slot_profile`
   - `missing_required_slots`
   - `slot_alignment_status`

4. retained page 和 point conversion 之间的断层，现在至少开始能说清“缺哪个位点”

5. extraction 主链新增了按需 `program_repair`
   - 只修 program
   - 不重做整题 extraction
   - 不改 label，不开 fallback 新分支

### 具体场景又是什么

这轮实际落地后，5 个锚点里最有代表性的现象是：

1. **`afc_0001`**
   - 现在能更明确地把“开盘涨约 2%”和“代表什么”拆成不同预算对象
   - 但当前结果仍回到 `2`
   - 说明 claim budget 的方向是对的，但 retrieval_filter 误杀和 numeric/date slot 还没收稳

2. **`afc_0002`**
   - 继续稳定为 `1`
   - detail refute 主链没有被这轮 program / budget 改动冲掉
   - 这说明这轮没有破坏已经收住的 detail 1/2 边界

3. **`afc_0003`**
   - premise 继续显式在主链里
   - 当前仍是 `2`
   - 但主阻塞已经更多落在 `provider_recall / retrieval_filter`，不是又掉回 fallback 外围

4. **`afc_0008 / afc_0010`**
   - 继续保持 `2`
   - `reason` 仍然优先说“不是同一事实位点/口径”
   - 并且开始能结合 `missing_required_slots / point_conversion_block_reason` 去解释为什么还没转成可裁决点

### 我应该怎么去使用

后面继续开发时，这一轮新增字段建议按下面顺序看：

1. `extracted.claims[].claim_budget_bucket`
   - 看主链到底把这条 claim 当成直接结果、结构化 detail，还是解释性 claim

2. `evidence_need_program.required_slot_profile`
   - 看这条 claim 理论上必须对齐哪些位点

3. retrieval debug 里的：
   - `missing_required_slots`
   - `slot_alignment_status`
   - `readiness_block_reason`

4. evidence 层里的：
   - `point_conversion.block_reason`
   - `comparability_profile`

5. 最后才看最终 reason
   - 如果 reason 和上面这几层不一致，优先当作链路还没完全收稳

### 对用户意味着什么

对用户侧，这轮的价值不是“结果一下子都贴 gold 了”，而是：

1. 以后更容易知道系统到底缺的是哪种证据
2. 以后更容易区分“搜不到”和“搜到了但不是同一事实位点”
3. 后续继续优化时，更可能提升泛化，而不是继续补样本

### 对开发者意味着什么

对开发侧，这轮意味着：

1. `evidence_need_program` 已经从“解释层”继续推进到了“预算 + slot + diagnostics”层
2. `program_repair` 已经是主链里真实存在的一步，不再只是纸面想法
3. 但 `required_slot_profile / missing_required_slots` 目前还是第一版，命中偏保守，不能直接当最终协议封版
4. `augment_mixed_detail_claims(...)` 虽然有效，但目前还偏粗，仍有把 detail 拆得太多的风险

### 当前结论

这轮可以分成“已经收住的部分”和“还没完全收住的部分”来看。

**已经收住的部分：**

1. `claim_budget_bucket`、`required_slot_profile`、`program_repair_used` 已经接进主链
2. `afc_0002` 继续稳定为 `1`
3. `afc_0008 / 0010` 继续是“不可比优先”的解释，不是退回泛 unsupported
4. `afc_0003` 没有因为这轮改动重新打开 fallback 扩权

**还没完全收住的部分：**

1. `afc_0001` 这轮又回到了 `2`
   - 说明主链解释力继续变强
   - 但 retrieval/filter 到 direct point 的转化还没追回来

2. `missing_required_slots` 当前命中偏保守
   - 它现在更像“提醒我们缺哪些位点”
   - 还不是最终稳定的 slot 合同解释

3. `augment_mixed_detail_claims(...)` 现在虽然限制了适用范围，但仍然偏粗
   - 下一轮需要继续压重复和压噪音

4. `program_repair` 已经有效，但平均耗时会上升
   - 本轮 5 个锚点平均耗时约 `71.7s`
   - 后面要继续盯它是否值得长期保留在默认链路里

### 下一步建议

下一步建议继续按当前主线收，但重点改成更窄的三件事：

1. **先收 `missing_required_slots` 命中口径**
   - 目标不是让它更敏感，而是让它更少误报、更接近真实 slot 缺口

2. **再收 `augment_mixed_detail_claims(...)`**
   - 重点压重复、压噪音
   - 避免为了补 detail 又把 claim budget 搅乱

3. **最后收 `program_repair` 的触发门槛**
   - 让它更少触发
   - 只在真的“claim 混 + slot 缺 + 断言不短”时才出手

4. 当前这轮回归工件固定记录为：
   - `tmp_phase4_second_cut_results_v2.json`
   - `tmp_phase4_second_cut_debug_v2.json`
   - `tmp_phase4_second_cut_perf_v2.json`

## 2026-05-09 Phase4 证据瞄准层第二轮收口第二刀落地记录

### 分类

证据链 / 提示词 / Workflow / 测试与回归

### 这次要做什么

这一刀没有再扩新能力，而是专门收三个已经暴露出来的老问题：

1. 把 `missing_required_slots` 从“提醒项”继续收成更接近真实缺口的字段
2. 把 `augment_mixed_detail_claims(...)` 长出来的重复 claim 和标题噪音压掉
3. 把 `program_repair` 的触发门槛再抬高，减少额外 LLM 开销

实际代码落点是：

- `solve.py`
  - `required_slot_profile_for_mode(...)`
  - `infer_missing_required_slots(...)`
  - `augment_mixed_detail_claims(...)`
  - `claim_needs_program_repair(...)`
  - `maybe_apply_program_repair(...)`
- `retrieval.py`
  - `infer_missing_required_slots_for_claim(...)`
- `evidence.py`
  - `infer_point_conversion_block_reason(...)`

### 动机是什么

上一版已经把 `claim_budget_bucket`、`required_slot_profile`、`missing_required_slots`、`slot_alignment_status` 和按需 `program_repair` 接进主链了，但马上暴露出三个很现实的问题：

1. `missing_required_slots` 还是偏保守，很多明明已经有位点信息的 case，也会被报成“缺 slot”
2. mixed detail augment 有时会把 answer 里的 markdown 标题、解释性分句也误当成 detail claim，反过来把 budget 搅乱
3. `program_repair` 虽然能补 program，但如果触发太宽，LLM 额外开销会上去，而且收益不稳定

所以这轮不是再发明新字段，而是把已经接上的机制收干净，先让它更准、更省、更不扰动主链。

### 对我们的项目有什么实际作用

这轮真正带来的作用主要有四个：

1. `missing_required_slots` 明显更像“真实缺口”了，不再大面积把已有位点误报成缺
2. mixed detail augment 变得更克制了，不再轻易长出“core-like supporting”或标题碎片 claim
3. `program_repair` 这一步基本退回到“真有必要才出手”，不会默认给 extraction 叠第二轮负担
4. 平均耗时从上一轮的 `71.679s` 降到本轮最终回归的 `63.236s`

### 具体场景又是什么

这轮 5 个锚点里，最有代表性的现象是：

1. **`afc_0001`**
   - claim 列表从 5 条收到了 2 条
   - 之前错误长出来的 mixed detail 标题噪音被去掉了
   - 现在主链更清楚地只保留“开盘是否涨约 2%”和“这代表什么”两类核心对象
   - 但它当前仍是 `2`，说明主瓶颈已经更明确地回到 recall，而不是 claim 污染

2. **`afc_0002`**
   - 继续稳定为 `1`
   - detail refute 主链没有被这轮 slot / repair / mixed cleanup 破坏
   - 说明这轮收紧没有把已经成立的 detail 决策口径冲掉

3. **`afc_0003`**
   - `exclusive_premise` 还在主链里，而且没有再被 mixed detail augment 污染
   - 仍然是 `2`
   - 但这次更清楚地看到，它的问题不是 premise 没抽到，而是 premise 和主 claim 还没拿到足够可直裁材料

4. **`afc_0008 / afc_0010`**
   - 继续保持 `2`
   - 最终 reason 仍然优先保留“搜到相关材料，但不是同一事实位点/同一口径”这层解释
   - 这说明我们没有因为收紧 slot 和 repair，就把 `partial_but_incomparable` 又打回泛 unsupported

### 我应该怎么去使用

后面继续开发时，这轮新增和收紧后的字段建议按这个顺序看：

1. `extracted.claims`
   - 先看 claim 列表有没有被清干净
   - 特别看是不是还长出多余 mixed detail 或标题噪音

2. `claim_budget_bucket`
   - 看每条 claim 现在到底被当成 `direct_observable`、`structured_detail`、`interpretive_explanation` 还是 `background_context`

3. `evidence_need_program.required_slot_profile`
   - 看系统理论上要求对齐哪些位点

4. `evidence_need_program.missing_required_slots`
   - 这一步现在可以更放心地当成“真实缺口提示”来看，而不只是保守提醒

5. `claim_pipeline_diagnostics`
   - 重点看：
     - `slot_alignment_status`
     - `readiness_block_reason`
     - `point_conversion_block_reason`

6. 最后再看 `reason`
   - 如果 `reason` 和上面这些字段对不上，优先认为链路还没完全收稳

### 对用户意味着什么

对用户侧，这轮的价值不是“标签一下子全贴 gold 了”，而是：

1. 系统更不容易因为 claim 污染把注意力浪费在假 detail 上
2. 当它说“现在还不能判错”时，解释会更像真的机制阻塞，而不是一锅粥式地说“证据不够”
3. 后面继续提抓证据能力时，我们更容易知道该补 recall、补 retention，还是补 point conversion

### 对开发者意味着什么

对开发侧，这轮有两个很实在的结论：

1. **上游清洁度比继续堆提示词更重要**
   - 只要 mixed detail 污染和 repair 宽触发没收住，后面 retrieval/evidence 再细也会被噪音拖垮

2. **当前主瓶颈已经更清楚了**
   - 这轮之后，很多 case 不再卡在“slot 没填”
   - 更像是：
     - `provider_recall`
     - 或“有原始材料但没转成 direct candidate / comparable point”
   - 这比以前更有价值，因为我们终于能把注意力从“字段有没有写满”转到“证据为什么没拿到位”

### 当前结论

这轮可以明确说是有效进展，而且是机制层面的有效进展。

已经收住的部分：

1. `missing_required_slots` 的误报显著下降
   - 从上一轮 debug 看，5 个锚点里原来合计有大量 `missing_required_slots`
   - 这轮最终回归里，固定锚点的这类误报基本被压掉了

2. `program_repair` 明显收住了
   - 上一轮还有样本触发 repair
   - 这轮最终回归 5 个锚点里，`program_repair_used = false`，`program_repair_changed = 0`
   - 说明“按需修 program”还在，但已经不再轻易介入

3. mixed detail augment 更干净了
   - `afc_0001` 之前错误长出来的 `mix5` 标题噪音已经去掉
   - `afc_0003` 也没有再被 mixed detail augment 污染

4. 平均耗时下降了
   - 上一轮：`71.679s`
   - 这轮最终：`63.236s`

还没完全收住的部分：

1. `afc_0001` 还是 `2`
   - 说明把 claim 和 slot 收干净，不等于证据自动就能抓回来
   - 主瓶颈已经更像 recall / raw material 不足

2. `afc_0008` 虽然整体解释仍维持“不可比优先”，但 claim 级 pipeline 里 provider_recall 仍偏重
   - 说明 comparability / direct candidate 这层还可以继续收

3. `missing_required_slots` 现在虽然更准了，但也出现了“几乎不再报缺”的新倾向
   - 这意味着下一轮要继续确认：它是真的更准了，还是有些 case 被压得过头

### 下一步建议

下一步不要回去放宽 fallback，也不要急着上 few-shot。更值得做的是继续沿着这轮已经暴露出来的真瓶颈往下收：

1. **先收 recall / raw material 不足**
   - 这轮之后，很多 case 的主问题已经不是“slot 没填”，而是“根本没拿到足够原始材料”
   - 所以下一步更值得看：
     - query 是否还不够直指主 claim
     - retention 是否保住了真正该保的页
     - retained page 为什么没转成 direct candidate

2. **再收 comparability / point conversion**
   - 特别盯 `afc_0008 / afc_0010`
   - 看能不能让“相关但不可直裁”这层更稳定落在 claim 级 pipeline，而不是只在最终 reason 里体现

3. **继续保持 repair 克制**
   - 本轮已经证明，repair 不是越多越好
   - 后面应继续把它当作兜底的小修复，而不是默认第二轮 extraction

4. 当前这轮最终回归工件固定记录为：
   - `tmp_phase4_second_cut_results_v3b.json`
   - `tmp_phase4_second_cut_debug_v3b.json`
   - `tmp_phase4_second_cut_perf_v3b.json`

## 2026-05-09 Phase4 检索链反爬鲁棒性补强记录

### 分类

证据链 / Workflow / 测试与回归

### 这次要做什么

这次不是继续改标签边界，而是补检索链的运行鲁棒性，重点处理“同学本地跑的时候被反爬虫拦住，结果被系统误当成没证据”的问题。

实际改动主要落在：

- `retrieval.py`
- `playwright_retrieval.py`

补的点包括：

1. 识别 403 / 429 / 503 这类明显阻塞
2. 识别验证码、人机验证、Cloudflare、安全校验等拦截页
3. 对 detail fetch 加更稳的降级路径
4. 把反爬阻塞和普通 provider_error / detail_error 区分开

### 动机是什么

之前代码里已经能看见 `provider_error`、`detail_error`，但没有把“被反爬拦住”稳定当成一种单独的失败类型处理。

这会带来两个很现实的问题：

1. 同样是没拿到 detail，有时候是真的没证据，有时候只是被网站拦了
2. 如果两者都被混成普通 `unsupported` 或普通 `provider_error`，我们就会误判主瓶颈，甚至误以为 claim / query / slot 设计有问题

所以这次补强的核心不是“更会爬”，而是先把“环境阻塞”和“证据缺失”分清。

### 对我们的项目有什么实际作用

这次补强后，主链会更健壮地处理这类运行场景：

1. 请求命中反爬页时，不再默默掉成空结果
2. detail 抓取被拦时，会优先尝试更稳的 Playwright 取页方式
3. 即使最后还是失败，debug 里也更容易看出这是 `anti_bot_blocked`，而不只是模糊的 `detail_error`
4. source health 和 source recall 诊断里，反爬阻塞会留下痕迹，后续更容易调 source plan

### 具体场景又是什么

最典型的场景是：

1. 搜索源返回了 403 / 429
   - 以前：可能只表现为没有 raw results
   - 现在：会更明确落成疑似反爬或安全校验阻塞

2. 页面正文抓取时拿到的不是正文，而是验证码页 / Cloudflare challenge
   - 以前：常常只是一个普通 `detail_error`
   - 现在：会标成 `detail_error_type = anti_bot_blocked`

3. 普通 requests 被拦，但页面其实还能被浏览器环境打开
   - 现在会优先尝试 Playwright 兜底取页，而不是直接宣告 detail fetch 失败

### 我应该怎么去使用

后面如果再遇到“跑出来像 unsupported，但怀疑是环境问题”的 case，建议按下面顺序看：

1. `source_pollution_stats`
   - 看 `errors`
   - 看 `anti_bot_blocks`

2. `claim_pipeline_diagnostics`
   - 看是不是 provider 层被阻塞

3. 页面级 item
   - 看 `detail_error`
   - 看 `detail_error_type`

4. `all_logs`
   - 看 source 级异常里有没有 `anti_bot_blocked`

如果这些字段都在报反爬，那就先别急着怀疑 claim / slot / reason 链，先确认是不是运行环境被网站拦了。

### 对用户意味着什么

对用户侧，这次补强最直接的价值是：

1. 同样一条题，不会因为某位同学本地刚好被反爬拦住，就更容易掉成“没有证据”
2. 就算失败，系统也更容易说明白“这是抓取受阻”，而不是把责任都推给事实核查主链

### 对开发者意味着什么

对开发侧，这次补强意味着：

1. 以后看 recall / filter / detail fetch 问题时，终于可以把“反爬阻塞”单独从普通失败里拆出来
2. 我们对 source health 的理解会更准，不会把某些源误以为“天生没结果”，其实只是最近被拦
3. 后面如果要继续做更细的 provider fallback、代理层、浏览器上下文策略，这次算是先把失败类型地基打出来了

### 当前结论

这次补强已经完成以下内容：

1. `retrieval.py` 增加了反爬信号识别
2. 搜索请求和 detail fetch 增加了 guarded request 检查
3. detail fetch 在疑似反爬时会优先尝试 Playwright 兜底
4. `source_pollution_stats` 新增 `anti_bot_blocks`
5. detail 错误会区分 `anti_bot_blocked` 和普通 `fetch_error`
6. `playwright_retrieval.py` 也同步补了同类检测

本轮做了：

- `python -m py_compile solve.py retrieval.py evidence.py playwright_retrieval.py`
- 反爬关键词识别烟雾测试

还没有做的是：

- 在真实被 Cloudflare / 验证码拦截的网站上跑一轮实战回归

所以这次可以认为“机制已接好，真实拦截场景还需要后续顺手验证”。

### 下一步建议

下一步如果继续做这条线，最值得补的是：

1. 在 debug 里把“request blocked but playwright rescued”单独显式记出来
2. 给 source health / fallback policy 增加对 `anti_bot_blocks` 的更主动降权
3. 找 1 到 2 个经常触发拦截的真实站点做小回归，确认这次补强在实战里真的能减少误判

---

## Phase4 协作分支与提交基线

为了避免主链开发、实验轮次、提交版本和回归结论相互污染，Phase4 后续默认采用以下 Git 基线：

1. 主仓库远端：
   - `https://github.com/ZZH-ZAO/afc-evidence-first-verifier`

2. 分支职责：
   - `main`：阶段主基线
   - `codex/dev`：Codex 持续开发分支

3. 提交粒度：
   - 默认每完成一轮完整机制实现与验证，做一次提交
   - 不要求每个小函数改动单独提交
   - 也不把多个无关轮次堆进同一次提交

4. 执行原则：
   - 开发前先确认当前分支
   - 开发后先验证，再提交
   - 文档同步视为每轮 done-definition 的一部分

这样做的目的，是让后续每一轮 Phase4 改动都能回答三件事：
- 这一轮到底改了什么
- 这一轮是否完成了最小验证
- 这一轮是基于哪条稳定开发线推进的
