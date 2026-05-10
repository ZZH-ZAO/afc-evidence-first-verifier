## 2026-05-10 AX/AY/AZ 首轮实施状态同步

### 分类

证据链路 / Workflow / 测试与回看

### 这次要做什么？

这轮按 `AX -> AY -> AZ` 的顺序，把前面两份文档里已经定下来的“决策有用命中率优先”真正落到 `solve.py` 主基线上：

1. `AX`：不再只让 `query_family_role` 停留在字段层，而是开始影响 query 预算、query 优先级和页面效用判断
2. `AY`：把 `kept page -> candidate -> point` 这条消费链从“看相关性”继续往“看可裁决性”推进
3. `AZ`：把 `closure_refutation` 从单个样本可跑，继续往 family 级收口，并显式接到最终 channel 解释层

这轮只改了 [solve.py](/d:/张子昊/solve.py)，没有碰 `solve_submit.py`，没有新增 provider，也没有放宽 fallback。

### 动机是什么？

前面文档已经把方向讲清楚了，但还差一层最关键的东西：真正能带来效果的落地实现。

我们现在的真实问题，不再是“完全没有框架”，而是：

1. `closure / distinguish / refute` 已经进了协议，但还没有稳定变成更有用的网页命中
2. 页面和句子有时已经拿到了，但没有稳定转成可裁决的 point
3. `closure_refutation` 已经能打中 `afc_0002`，但还没有明显泛化到更多 family

所以这轮不是继续解释“为什么卡住”，而是先把能直接推动效果的中层机制接起来。

### 对我们的项目有什么实际作用？

这轮做完以后，项目多了三层真正可用的东西：

1. query 不再只是“长得像 claim”，而是开始区分“对裁决有没有用”
2. 页面、候选句、same-slot review、point consumption 之间多了一条连续的 utility-first 轨道
3. 最终 `2` 不是纯黑盒了，debug 里能看见它现在更像停在 `direct_web_evidence`、`closure_refutation` 还是 `insufficient_or_unresolved`

这对后续迭代的实际价值很大，因为我们终于能把“没判出来”继续往前拆成：

- 命中质量问题
- 页面保留问题
- 候选句消费问题
- point conversion 问题
- closure 链稳定性问题

### 具体场景又是什么？

这轮最典型的几个场景是：

1. `afc_0002`
   - 继续稳定为 `1`
   - `closure_refutation` 仍然是主导通道
   - 说明 supporting structured detail 的逻辑反证通道没有被新机制冲掉

2. `afc_0001`
   - 仍然是 `2`
   - 但现在能更清楚看到它不是“什么都没搜到”，而是已经有相关材料，只是没有稳定变成同位点、可直裁的证据
   - 这说明问题更像“决策有用命中率还不够”，不是单纯没有框架

3. `afc_0003`
   - 仍然是 `2`
   - 已经开始进入 `refute` 轨道，但还没有稳定留下真正可消费的 `route_closure / route_refute` 页面

4. `afc_0008 / afc_0010`
   - 仍然是 `2`
   - 继续暴露“有相关材料，但同位点 conversion 还不够稳”的后段瓶颈

### 我应该怎么去使用？

后面看这一轮产物，建议按下面顺序读：

1. 先看结果标签和 reason
2. 再看 debug 里的 `final_result`
3. 再看 `claim_pipeline_diagnostics.items`

这轮新增或真正接通的关键观察口包括：

- `query_effective_role`
- `page_utility_score`
- `page_utility_profile`
- `decision_useful_hit`
- `candidate_utility_score`
- `slot_review_outcome`
- `point_consumption_state`
- `closure_chain_state`
- `closure_chain_family`
- `closure_chain_block_reason`
- `label_source_channel`
- `_decision_channel`
- `_channel_label_candidate`

其中最有用的一点是：虽然主结果文件还是只保留 `id / label / reason`，但 debug 里的 `final_result` 已经把这轮新增的 channel 信息带出来了，不会再在最后一步被静默裁掉。

### 对用户意味着什么？

对最终使用系统的人来说，这轮最大的变化不是标签突然大幅上涨，而是“系统现在更诚实了”：

1. 能更明确地区分是 closure 通道在工作，还是 direct web 通道在工作
2. 判不出来时，更容易看出卡在页面、句子还是 point，而不是一概写成没证据
3. `afc_0002` 这种 supporting detail 逻辑反证型错误，现在仍然能稳定打出来

换句话说，这轮先提升了系统的“可解释、可调、可定位”，这是后面继续提效果必须先补的一层。

### 对开发者意味着什么？

对开发侧来说，这轮最重要的不是某一个样本涨了，而是几个协议终于真正接上线了：

1. `AX` 不再只是 query family 的概念层，已经进入 budget 和 utility 评分层
2. `AY` 不再只是候选句 debug，而是开始真的影响 candidate rerank、slot review 和 point consumption 状态
3. `AZ` 不再只是 `closure_refutation` 的散落 heuristic，而是开始显式产出：
   - `closure_chain_family`
   - `closure_chain_state`
   - `label_source_channel`

同时，这轮也把“输出层丢字段”的问题补上了。现在 debug 最终结果里可以直接看到这轮新增协议的最终消费情况，后面排查就不会在最后一步断线。

### 当前结论

这轮首轮落地已经完成，并做了最小验证。

验证命令：

```bash
python .\solve.py --input .\output\afc_phase4_aiajak_sample_subset_input.json --output .\output\afc_phase4_axayaz_sample_subset_results.json --debug-output .\output\afc_phase4_axayaz_sample_subset_debug.json --perf-output .\output\afc_phase4_axayaz_sample_subset_perf.json --workers 1 --no-resume
```

本轮锚点结果：

- `afc_0001 -> 2`
- `afc_0002 -> 1`
- `afc_0003 -> 2`
- `afc_0008 -> 2`
- `afc_0010 -> 2`

可以确认已经生效的部分：

1. `afc_0002` 继续稳定为 `1`
2. debug `final_result` 中已经能看到：
   - `_decision_channel`
   - `_channel_decision_candidate`
   - `_channel_label_candidate`
   - `label_source_channel`
3. `closure_chain_family / closure_chain_state` 已经开始在非单一行上稳定出现
4. `page_utility_score / candidate_utility_score / slot_review_outcome / point_consumption_state` 已经进入 claim 级诊断

这轮没有完全打穿的地方也很明确：

1. `afc_0001` 仍然没有出现稳定的 `closure/distinguish` 高质量保留结果
2. `afc_0003` 虽然进入了 `refute` 轨道，但没有稳定保留到可消费页面
3. `afc_0008 / 0010` 的后段 conversion 仍然比前段命中更弱

所以这轮的真实效果是：

**它把“决策有用命中率优先”从文档变成了代码里可观察、可消费、可继续压测的中层协议，但还没有把最难的几个 case 直接推成更多 `1`。**

### 下一步建议

下一步不该再开新大框架，而是沿这轮已经接好的接口继续压三件事：

1. 先压 `AX` 的真实命中效果
   - 重点盯 `afc_0001 / afc_0003`
   - 不是再加字段，而是让 `closure / distinguish / refute` 真正带来 `raw>0 && kept>0`

2. 再压 `AY` 的消费率
   - 重点盯 `afc_0008 / afc_0010`
   - 让 `slot_review_outcome` 更少停在 `unresolved`
   - 让 `candidate_utility_score` 更常转成可消费 point

3. 最后压 `AZ` 的泛化
   - 不只守住 `afc_0002`
   - 至少再打出 1 个非 `afc_0002` 的 closure family 稳定轨道

这份文档和前面两份文档的关系也要固定下来：

- `决策有用检索与双通道裁决框架`：负责讲为什么要这样改、总框架是什么
- `实际落地提升优先级清单`：负责讲这一阶段应该优先打哪几个效果缺口
- **本文件**：负责记录这一轮到底落了什么、守住了什么、还没打穿什么

也就是说，这份不是新的总规划文，而是前两份计划文档的首轮实施回执。
