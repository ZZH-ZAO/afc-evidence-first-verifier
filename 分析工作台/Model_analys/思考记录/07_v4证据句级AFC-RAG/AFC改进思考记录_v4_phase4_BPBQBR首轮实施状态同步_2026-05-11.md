## 2026-05-11 BPBQBR 首轮实施状态同步
### 分类

Workflow / 证据链 / 测试与回归

### 这次要做什么？
这轮承接 `AFC改进思考记录_v4_phase4_下一步实施计划_BPBQBR_页保留效果与same-slot消费打通_v0.1.md`，目标是继续沿着现有主架构往前推两层真实瓶颈：

1. 让 `raw>0 && kept=0` 的 core / 高风险 route near-miss 页更容易进入二次复核
2. 让已经有 partial/direct 候选的 claim，不再轻易掉回 `unresolved`

### 动机是什么？
上一轮已经把问题拆得很清楚：

1. 不是完全搜不回来
2. 而是页没保住，或者句子没消费

所以这轮不值得再换大架构，而应该继续追问：

1. 为什么 second-pass keep 还是救不回关键页
2. 为什么 same-slot 候选已经出现了，结果还会掉成 `unresolved`

### 对我们的项目有什么实际作用？
这轮的实际价值主要在三点：

1. 把 page keep 的硬挡板再往前推一层，验证“是不是 hard drop 口径太死”
2. 把 same-slot 的消费层再往前推一层，验证“是不是候选已经够用了，只是没被承接”
3. 即使效果没打穿，也能更明确地确认下一步要修的是“hard-drop 契约”而不是泛 recall

### 具体场景又是什么？
最典型的就是这几类：

1. `afc_0001`
   - 有原始结果
   - 但关键页被 `structured_noise_high_penalty` 这类 hard drop 打死

2. `afc_0003`
   - route supporting claim 需要更容易进入二次复核
   - 否则 route family 只会停在 filter 层

3. `afc_0010`
   - 已经有 partial/direct candidate
   - 但 slot review 仍可能掉到 `unresolved`

### 我们基于什么架构？
继续基于当前已经落地的主架构推进：

1. 受控 Search Tool
2. authority-first 入口
3. Playwright 受控救援
4. 双通道裁决
5. 诊断驱动的 retrieval / decision 消费

这轮没有新增 provider，也没有引入新的终判器。

### 这轮实际实现了什么？
#### 1. `retrieval.py`

1. 把 route 页型正式纳入 core second-pass 可复核页型：
   - `route_analysis_page`
   - `route_passage_page`

2. 扩了 second-pass 允许范围：
   - 除 core critical 外
   - `route_fact + supporting_high_risk` 也允许进入二次复核

3. 新增 second-pass 信号收口：
   - `core_second_pass_signal_summary(...)`
   - 更显式消费 `route_sentence / relation_evidence / answerability / entity_grounding`

4. 对 `structured_noise_high_penalty` 增加了一个很窄的 structured fact 例外：
   - 只在强页型
   - 且主体/时间/事实位点都更像同槽位材料时才允许继续复核

#### 2. `solve.py`

1. `candidate_decision_useful_score(...)` 更强地奖励：
   - 强页型候选
   - 同槽位覆盖更完整的 near-direct 句子
   - `candidate_not_direct / related_but_not_assertive` 这类“差一点可裁决”的候选

2. `infer_slot_review_outcome(...)` 不再只依赖 `answer_candidate_total`
   - 现在会显式消费：
   - `candidate_sentence_count`
   - `partial_count`
   - `direct_to_uncertain_only / no_direct_candidate`

### 解决了什么？
这轮解决了一个真实的小问题，但还没有解决主问题。

#### 已解决的部分

1. same-slot 消费层比上一轮更诚实了
   - 一些原本会掉回 `unresolved` 的 claim
   - 现在能进入 `weak_candidate_retained` 或 `same_slot_review_not_direct`

2. `afc_0002` 继续稳定为 `1`
3. `afc_0008 / 0010` 没有误抬

#### 还没解决的主问题

1. `second_pass_keep_recovered_count` 仍然是 `0`
2. 关键页成功率没有被真正打通

也就是说，这轮更多是把“候选消费层的漏接”补上了一些，但“关键页没保住”这个最大瓶颈还没穿过去。

### 当前还卡在哪？
这轮回看后，最核心的卡点已经更清楚了：

#### 1. hard-drop 契约还是过强

从锚点回看里最重要的一条新结论是：

1. `afc_0001 c1`
   - `hard_drop_reason = structured_noise_high_penalty`
   - `core_keep_review_block_reason = page_shape_hard_drop`

这说明问题不是 second-pass 根本没接，而是它接到了之后，仍被 hard-drop 契约直接挡死。

#### 2. route family 还没有真正兑现到 kept

`afc_0003` 里：

1. route supporting claim 已经允许进入更宽的 second-pass 范围
2. 但 `kept_web` 仍没有起来

说明 route 页型进入范围还不够，或者 route family 的 page contract 仍偏严。

#### 3. same-slot 有所改善，但还只是诊断层进展

这轮出现了更多：

1. `weak_candidate_retained`
2. `same_slot_review_not_direct`

这能证明 `solve.py` 这层承接更顺了，但它没有反过来带来明显的 evidence success uplift。

### 现有方案还能不能继续解？
还能，但下一步已经不该继续泛放宽，而要更精准地打 hard-drop 契约。

判断依据：

1. second-pass 逻辑已经接上了
2. same-slot 消费逻辑也已经往前推了一截
3. 但关键页仍被 `structured_noise_high_penalty / page_shape_hard_drop` 一刀切挡死

所以当前最值得打的，不是继续加 source，也不是继续泛扩 query，而是：

1. hard-drop 是否要拆成“真噪声”和“结构化强页误杀”
2. route / structured fact 的 page contract 是否该进一步细分

### 如果不能，再去外部检索
这轮之后，只有在下面条件继续成立时，才值得再去补外部架构：

1. hard-drop 契约拆分后，`second_pass_keep_recovered_count` 仍长期为 0
2. route / numeric 强页型仍几乎没有 kept 提升
3. same-slot 消费继续改善，但标签和关键证据成功率始终不动

### 这对用户意味着什么？
对最终用户来说，这轮最大的真实变化不是“结果更好了”，而是系统更少把“已经有候选句”误写成“什么都没有”。

这能让失败理由更贴近真实链路，但还没有把关键证据成功率打穿。

### 这对开发者意味着什么？
对开发者来说，这轮最大的价值是把下一步施工点继续压缩：

1. 不是 recall
2. 不是 Playwright
3. 而是 hard-drop / page contract

这比继续盲试别的检索源要更有确定性。

### 最小验证
本轮使用锚点：

- `afc_0001`
- `afc_0002`
- `afc_0003`
- `afc_0008`
- `afc_0010`

验证产物：

- `local_dev/tmp/phase4_bpbqbr_sample0410_output.json`
- `local_dev/tmp/phase4_bpbqbr_sample0410_debug.json`
- `local_dev/tmp/phase4_bpbqbr_sample0410_perf.json`
- `local_dev/tmp/phase4_bpbqbr_r2_sample0410_output.json`
- `local_dev/tmp/phase4_bpbqbr_r2_sample0410_debug.json`
- `local_dev/tmp/phase4_bpbqbr_r2_sample0410_perf.json`

第二次 rerun 的结果：

1. `afc_0001 -> 2`
2. `afc_0002 -> 1`
3. `afc_0003 -> 2`
4. `afc_0008 -> 2`
5. `afc_0010 -> 2`

性能上，第二次 rerun 大致为：

1. `retrieve` 平均约 `25.846s`
2. 总耗时平均约 `113.308s`

说明 retrieval 自身并没有继续恶化，但整轮总耗时没有收住，而且核心成功率也还没起来。

### 当前结论
这轮 **没有把“关键证据成功率”真正打通**。

但它也不是空转，真实产出是：

1. same-slot 消费层更顺了
2. `second-pass keep` 失败的真正挡板暴露出来了
3. 下一步已经可以更明确地收口到 hard-drop / page contract，而不是继续泛补 recall

### 和前面文档的关系
#### 和《BPBQBR 页保留效果与same-slot消费打通计划》的关系

那份文档是施工计划。  
这份文档是首轮实施后的状态同步，回答的是：

1. 哪些实现已经落了
2. 哪些问题开始动了
3. 哪些问题还完全没被打穿

#### 和《BMBNBO 首轮实施状态同步》的关系

`BMBNBO` 把诊断接进了决策，并搭起了 second-pass 骨架。  
这份状态同步证明：

1. 骨架是接上了
2. 但骨架上方的 hard-drop 契约还太硬

### 下一步建议
下一步不建议再泛补入口，而建议直接打下面这件事：

1. **hard-drop 分层收口**
   - 把 `structured_noise_high_penalty` 这类 hard drop 拆成：
   - 真噪声
   - 结构化强页误杀

2. **route / structured fact page contract 细分**
   - 让 strong page type 不再被统一的噪声口径一刀切

3. **保持 same-slot 这层现有进展，不回滚**
   - 因为它至少已经让“有候选句但没闭合”的链路更诚实了
