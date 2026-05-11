## 2026-05-11 BSBTBU 首轮实施状态同步

### 分类

Workflow / 证据链 / 测试与回归

### 这次要做什么？

这轮承接 `AFC改进思考记录_v4_phase4_下一步实施计划_BSBTBU_harddrop分层与证据消费真收口_v0.1.md`，目标不是再补入口，而是验证两件事：

1. `structured_noise_high_penalty` 拆层后，是否能让部分强结构页从 `raw` 真正进入 `kept`
2. `solve.py` 是否能显式承接“证据已经从 kept page 走到 candidate 层”的进展

### 动机是什么？

前一轮已经证明主瓶颈不再是纯 recall，而是：

1. 页被 hard-drop 误杀
2. 候选虽出现，但消费表达不够诚实

所以这轮的价值不是把系统做得更忙，而是验证“现有链路里已经出现的近失证据，能不能被真保下来、真消费出来”。

### 对我们的项目有什么实际作用？

这轮最大的实际价值是把“证据成功率打通”这件事第一次从口头判断，推进到可观察现象：

1. 有没有 case 从 `kept=0` 变成 `kept>0`
2. 有没有 case 从 `weak_candidate` 进入更明确的消费状态
3. final reason 能不能承认“现在不是没证据，而是候选/point 还没闭合”

### 具体场景又是什么？

最关键的仍然是：

1. `afc_0001`
   - 之前代表 `raw 有了，但 page 没保住`
2. `afc_0008 / 0010`
   - 之前代表 `有 kept / candidate 痕迹，但消费表达偏弱`
3. `afc_0003`
   - 继续代表 route 侧还没打通

### 我们基于什么架构？

仍然基于现有主架构推进：

1. 受控 Search Tool
2. authority-first 入口
3. Playwright 受控救援
4. 双通道裁决
5. 页保留 -> candidate -> point 三层消费链

这轮没有换架构，也没有接新 provider。

### 这轮实际实现了什么？

#### 1. `retrieval.py`

1. 新增 `structured_title_marker_hit(...)`
2. 新增 `is_recoverable_structured_penalty_item(...)`
3. 把一部分 structured hard-drop 拆成新口径：
   - `structured_noise_review_candidate`
4. `should_soft_keep_structured_metric_item(...)` 开始真实承接这类可复核强页
5. 新增 `annotate_soft_kept_structured_metric_item(...)`
6. `fact_page_keep_review` 被提升成功时，也会显式打出：
   - `page_keep_review_state`
   - `page_keep_review_reason`
   - `kept_progress_from_raw`

#### 2. `solve.py`

1. 新增 `slot_review_outcome = kept_page_candidate_progress`
2. 新增 `point_consumption_state = candidate_progress_from_kept_page`
3. `insufficient_evidence_reason(...)` 开始能显式承认：
   - 当前已经从保留下来的页面里消费出候选句
   - 只是还没有闭合到直裁点

### 解决了什么？

这轮最重要的结论是：**我们第一次看到了“证据真的被消费了”的现象**。

以首轮回归 `phase4_bsbtbu_sample0410_*` 为准：

1. `afc_0001 / c1`
   - `raw_results = 6`
   - `kept_web = 3`
   - `slot_review_outcome = kept_page_candidate_progress`
   - `point_consumption_state = candidate_progress_from_kept_page`

2. `afc_0008 / c2`
   - `kept_web = 2`
   - `point_consumption_state = candidate_progress_from_kept_page`

3. `afc_0010 / c2`
   - `kept_web = 1`
   - `point_consumption_state = candidate_progress_from_kept_page`

这说明这轮至少已经完成了一件此前没发生过的事：

1. 不只是 `raw` 回来了
2. 也不只是“有弱候选”
3. 而是页级保留和 candidate 消费链真的往前走了一段

同时，`afc_0002` 继续稳定为 `1`，说明主正确样本没有被误伤。

### 还卡在哪？

这轮没有把问题彻底打通，主要还卡在两点：

1. **成功率还不稳定**
   - 第二次 rerun（`phase4_bsbtbu_r2_sample0410_*`）出现明显漂移
   - `afc_0001` 从首轮的 `kept=3` 又掉回 `kept=0`
   - 说明外部检索结果和页保留入口仍有较大波动

2. **route 仍没打开**
   - `afc_0003` 依旧没有进入稳定的 kept/candidate 轨道

也就是说，这轮已经证明“现有方案能产生真实消费进展”，但还没有把这种进展收成稳定成功率。

### 现有方案还能不能继续解？

还能，而且下一步仍然应该优先在现有方案里继续解。

判断依据是：

1. 首轮回归已经打出真实进展，不是空跑
2. 说明 hard-drop 分层和消费显式化方向有效
3. 现在更像是“效果已出现但不稳定”，不是“方向错了”

所以当前还不值得直接换大架构，更值得继续追问：

1. 为什么同一批样本在 rerun 时会从 `kept>0` 掉回 `kept=0`
2. 是 source 波动、外站结果漂移，还是页级 contract 还不够稳

### 如果不能，再去外部检索

只有出现下面情况，才值得进入下一轮外部对标：

1. 对成功 run 和失败 run 做 source-level 对比后，仍无法解释漂移
2. 现有 hard-drop / page keep contract 调整后，`kept>0` 仍无法稳定复现
3. route 侧继续完全不动，现有 contract 已解释不了

### 对用户意味着什么？

对使用者来说，这轮最关键的不是标签立刻涨了多少，而是：

1. 系统第一次真正把一部分证据推进到了 `kept -> candidate`
2. reason 开始更像真实链路，而不是继续泛成“没证据”

### 对开发者意味着什么？

对开发者来说，这轮最重要的意义是把下一步问题继续压缩成一句话：

**不是“能不能出现成功进展”，而是“为什么成功进展还不能稳定复现”。**

### 最小验证

回归产物：

1. 首轮：
   - `local_dev/tmp/phase4_bsbtbu_sample0410_output.json`
   - `local_dev/tmp/phase4_bsbtbu_sample0410_debug.json`
   - `local_dev/tmp/phase4_bsbtbu_sample0410_perf.json`

2. 第二次 rerun：
   - `local_dev/tmp/phase4_bsbtbu_r2_sample0410_output.json`
   - `local_dev/tmp/phase4_bsbtbu_r2_sample0410_debug.json`
   - `local_dev/tmp/phase4_bsbtbu_r2_sample0410_perf.json`

首轮结果：

1. `afc_0001 -> 2`
2. `afc_0002 -> 1`
3. `afc_0003 -> 2`
4. `afc_0008 -> 2`
5. `afc_0010 -> 2`

但首轮最重要的不是标签，而是：

1. `afc_0001 / c1` 从 `kept=0` 打到 `kept=3`
2. 多个 case 出现 `candidate_progress_from_kept_page`

性能上，首轮相对上一轮锚点回归也有进展：

1. `retrieve` 平均约从 `25.846s` 降到 `16.855s`
2. 总平均约从 `113.308s` 降到 `75.791s`

第二次 rerun：

1. 总平均继续降到约 `73.009s`
2. 但 `retrieve` 回到约 `26.147s`
3. 关键 kept 进展没有稳定复现

这说明本轮已经不是纯性能问题，而是**外部检索波动 + 页保留稳定性**问题。

### 当前结论

这轮不是终局，但不是空转。

最核心的新增结论是：

1. 现有方案已经可以产生“证据真的被消费”的真实现象
2. 当前主问题从“能不能打出效果”转成了“为什么效果还不稳定”

### 和前面文档的关系

#### 和《BSBTBU hard-drop分层与证据消费真收口计划》的关系

那份文档是施工计划。  
这份文档是首轮实施后的状态同步，回答的是：

1. 哪些点已经落地
2. 哪些效果已经真实出现
3. 哪些问题还没稳定收住

#### 和《BPBQBR 页保留效果与 same-slot 消费打通》的关系

`BPBQBR` 证明了骨架可以接上。  
这份状态同步证明了骨架上第一次出现了真实消费进展，但稳定性还没收好。

### 下一步建议

下一步不建议重新回到泛 recall，而是固定做一轮**成功 run vs 失败 rerun 的 source / keep 差分审计**：

1. 对比 `phase4_bsbtbu_sample0410_debug.json` 和 `phase4_bsbtbu_r2_sample0410_debug.json`
2. 只盯：
   - 同一个 claim 的 source 是否漂移
   - 哪些页首轮能 kept、二轮不能 kept
   - 是 source 返回变了，还是 keep contract 还不稳
3. 先把成功进展的稳定复现收住，再继续往 route 或 point conversion 深打
