## 2026-05-10 BA/BB/BC 首轮实施状态同步

### 分类

证据链路 / Workflow / 测试与回看

### 这次做了什么？

这轮按 `BA -> BB -> BC` 的顺序，先把入口层修了一刀，主改集中在：

- [retrieval.py](/d:/张子昊/retrieval.py)
- [solve.py](/d:/张子昊/solve.py)

本轮没有碰 `solve_submit.py`，没有新增 provider，也没有做 fallback 扩权。

落下去的核心点有三块：

1. `BA`
   - `source_budget_cutoff` 从隐式现象变成显式诊断
   - `source_health` 从旁路统计更前移到实际 source 排序
   - `provider_health_snapshot / effective_source_plan` 开始进入 claim 级 debug

2. `BB`
   - `playwright_rescue_state / trigger / source / result_count` 进入 claim 级诊断
   - `PLAYWRIGHT_AFTER_SEARCH` 不再把所有 `raw=0` 一刀切跳过
   - 已出现至少 1 个 case 的 `playwright_rescue_succeeded`

3. `BC`
   - `official_discovery` source 顺序改成：
     - `bing_rss`
     - `bing_news_zh_rss`
     - `bing_news_rss`
     - `bing_html`
     - `duckduckgo_html`
     - `sogou_html`
   - `official_discovery_block_reason` 开始显式化
   - `official_entry_attempted / hit / source_family` 开始进入 claim 级 debug

### 动机是什么？

前面几轮文档已经把消费链讲清楚了：

- 怎么让 kept page 更可裁决
- 怎么让 candidate 更 direct
- 怎么让 closure 通道更稳定

但这一轮复盘之后很明确，很多 case 还没走到这些层，就已经先死在入口层了：

- 有的被反爬挡住
- 有的被 source budget 截断
- 有的该触发 Playwright rescue 却没真正接手
- 有的 authority discovery 明明尝试过，但失败信息一直只躺在 logs 里

所以这轮的价值不是“立刻多打出几个 1”，而是把入口层真实失败模式从黑盒拆开。

### 这轮结果怎么样？

验证命令：

```bash
python .\solve.py --input .\output\afc_phase4_aiajak_sample_subset_input.json --output .\output\afc_phase4_babbc_sample_subset_results.json --debug-output .\output\afc_phase4_babbc_sample_subset_debug.json --perf-output .\output\afc_phase4_babbc_sample_subset_perf.json --workers 1 --no-resume
```

本轮锚点标签：

- `afc_0001 -> 2`
- `afc_0002 -> 1`
- `afc_0003 -> 2`
- `afc_0008 -> 2`
- `afc_0010 -> 2`

可以确认已经生效的点：

1. `afc_0002`
   - 继续稳定为 `1`
   - 说明入口层修复没有误伤已有 closure 通道

2. 入口层新诊断已经开始出现在 claim 级输出里
   - `source_budget_cutoff`
   - `playwright_rescue_state`
   - `playwright_rescue_trigger`
   - `official_entry_attempted`
   - `official_entry_hit`
   - `official_discovery_block_reason`

3. `Playwright rescue` 已经不只是代码里有
   - 例如 `afc_0001:c1`
   - `afc_0010:c1`
   - 都已经能打出 `playwright_rescue_succeeded`

4. `raw=0` case 不再只能泛写成 provider recall
   - 例如 `afc_0001:c2`
   - `afc_0003:c1/c2`
   - 已经能显式落出 `source_budget_cutoff`

### 还没有打穿的地方

这轮虽然把入口层真实失败说清楚了，但还没有把最难的几个 case 真正往前推很多：

1. `afc_0001`
   - 仍然是 `2`
   - 目前主问题更像：
     - 已有一些可疑近失页
     - 句层仍偏 `slot_hit_but_indirect / background_commentary`
     - opening 位点还没稳稳顶到 direct candidate

2. `afc_0003`
   - 仍然是 `2`
   - 这轮更清楚地暴露出：
     - 一部分 claim 还是 `source_budget_cutoff`
     - 一部分 claim 即使有 raw，也死在页面保留阶段
   - 说明 route 题下一步不能只补入口，还得继续补 `route_closure / route_refute` 的可消费率

3. `official_discovery_failed`
   - 这轮已经能显式看到
   - 但目前还偏“提醒型信号”
   - 下一步要更谨慎地避免它在已有进展 case 上显得过度主导

### 应该怎么理解这轮的定位？

这份文档不是新总规划，也不是新框架文档。

它和前面文档的关系是：

- `入口层修复与反爬绕行实施计划`
  - 负责定义这轮为什么要修入口层、修哪三包

- `决策有用检索与双通道裁决框架`
  - 负责上层怎么判

- `实际落地提升优先级清单`
  - 负责效果层优先级

- **本文件**
  - 负责记录 BA/BB/BC 首轮到底落了什么、守住了什么、还没打穿什么

换句话说：

**前面的文档讲“为什么修、修哪里”，这份文档讲“这轮实际修到了哪一步”。**

### 当前结论

这轮首刀已经证明了一件很关键的事：

**当前很多“证据没回来”的 case，确实不是世界上没证据，而是入口层在 source budget、authority discovery、playwright rescue 这几处没有把材料稳定送进来。**

现在这件事已经不再只是判断，而是有了可观察的诊断口径。

### 下一步建议

下一轮建议不要再回去泛讲“反爬严重”，而是接着压入口层第二刀，重点放在两件事：

1. 继续压 `source_budget_cutoff`
   - 让高价值 `closure / distinguish / refute / verification_question` query 更少被截断

2. 继续压 `playwright rescue` 的真实接管率
   - 让 `raw=0` 且已执行高优先 source 的 case，更常进入真实 rescue

然后再回到：

3. `afc_0001 / 0010`
   - 继续压 weak candidate -> direct candidate

4. `afc_0003`
   - 继续压 route authority/closure 页面留下来的比例

