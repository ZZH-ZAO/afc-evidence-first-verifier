## 2026-05-10 AF/AG/AH 首轮实施状态同步

### 分类

证据链路 / Workflow / 测试与回归

### 这次要做什么？

这轮不再继续优先补 recall，也不再继续扩上游 `evidence_need_program` 字段，而是把主链真正推进到句层和点层之间：

1. AF：给 fact-like claim 的候选句收一个稳定的 directness 合同
2. AG：把“有句但不是同一事实位点”显式化，不再混成泛 unsupported
3. AH：让 `solve.py` 稳定消费句层/点层进展，不再退回泛 recall 解释

对应代码主改：

- `retrieval.py`
- `evidence.py`
- `solve.py`

### 动机是什么？

`AC/AD/AE` 之后，`afc_0001` 已经不是“搜不回来”了，而是“页保住了、句子也有了，但这些句子还不能稳定变成可裁决 point”。

也就是说，真正的主瓶颈已经从：

- recall 不够

转成了：

- 句层不够 direct
- 或句子不是同一事实位点
- 或数值/日期/结果口径不一致

如果这一步不收，后面系统就会反复把“句子弱”“位点错”说成“没有证据”。

### 对我们的项目有什么实际作用？

这轮做完后，主链第一次把“句层候选长什么样”和“为什么还不能裁”收成了更稳定的内部协议：

1. 候选句开始有统一档位：
   - `direct_candidate`
   - `slot_hit_but_indirect`
   - `numeric_reference_only`
   - `date_reference_only`
   - `background_commentary`

2. 主链开始显式输出：
   - `sentence_candidate_profile`
   - `top_candidate_slot_match`
   - `direct_candidate_gap_reason`

3. `point_conversion_block_reason` 更少再退回泛 `related_but_not_assertive`

4. `solve.py` 开始优先按真实句层/点层阻塞写 reason，而不是把所有问题都揉回“没有形成证据”

### 具体场景又是什么？

最关键还是 `afc_0001`：

- 以前：要么 `raw=0`，要么搜回来了但又死在 filter
- 现在：已经能稳定停在 `retrieval_readiness`
- 这轮继续把它收成：
  - 有候选句
  - 候选句不够 direct
  - 当前更多是相关位点或弱表达，不是直接可裁决句

同时这轮不是只盯 `0001`，还看了：

- `afc_0007`：日期角色错位
- `afc_0008 / 0010`：conversion / incomparability
- `afc_0004`：event result 类句层候选

### 我应该怎么去使用？

后面看 debug 时，优先看这些字段：

1. `claim_pipeline_diagnostics.items`
2. `sentence_candidate_profile`
3. `top_candidate_slot_match`
4. `direct_candidate_gap_reason`
5. `readiness_block_reason`
6. `point_conversion.block_reason`

推荐这样理解：

- `sentence_candidate_profile`：句层候选现在大多是什么类型
- `top_candidate_slot_match`：最强候选句打到了哪些关键位点
- `direct_candidate_gap_reason`：为什么它还不能算直裁句

如果：

- `answer_candidate_total > 0`
- 但还是 `2`

那就别再先怀疑 recall，而是优先看是不是：

- 句层不够 direct
- 位点错了
- 口径还不能归一

### 对用户意味着什么？

对最终使用系统的人来说，这轮最直接的变化是：

系统更少把“其实已经有相关句子了，但句子还不够直”说成“完全没证据”。

这样 `2` 的 reason 会更真，也更方便区分：

- 真没搜到
- 搜到了但没保住
- 保住了但句层不够 direct
- 有句子但不是同一事实位点

### 对开发者意味着什么？

对开发侧，这轮最重要的价值是把句层到 point 的尾差第一次拆开了：

1. `retrieval.py`
   - 候选句开始带 profile / slot match / gap reason
   - `answer_candidate_quality_score` 也会消费这些档位

2. `evidence.py`
   - 把候选句从“只是有句子”继续拆成：
     - 直答句
     - 弱直答句
     - 纯数值/日期痕迹句
     - 背景评论句
   - conversion block reason 更优先说真实错位点

3. `solve.py`
   - `claim_pipeline_diagnostics.items` 能直接带出新的句层字段
   - unsupported / readiness / point conversion 的 reason 更像真实阻塞解释

### 当前结论

这轮首轮落地是有效的，而且已经有验证结果：

1. `afc_0001`
   - 继续保持 `2`
   - 主因继续停在 `retrieval_readiness`
   - reason 已经变成“有候选句，但句层还不够 direct”

2. `afc_0002`
   - 继续稳定为 `1`

3. `afc_0003`
   - 继续 `2`
   - 没被这轮 fact-like 机制误伤

4. `afc_0008 / 0010`
   - 继续保持 `2`
   - conversion / incomparability 逻辑没有回退

5. `afc_0007`
   - 出现了 `date_role_mismatch`
   - 说明这轮不是只对 opening numeric 生效，日期角色错位也开始能显式收出来

本轮关键输出文件：

- `output/afc_phase4_afagah_sample_subset_results.json`
- `output/afc_phase4_afagah_sample_subset_debug.json`

### 下一步建议

下一步不该再回去优先补 recall，而是继续往后收：

1. 继续压 `slot_hit_but_indirect`
   - 让更多候选句从“打到一部分位点”推进成真正的 `direct_candidate`

2. 继续细化 `top_candidate_slot_match`
   - 让“主体+时间+结果”与“只有主体+结果”这类差异更稳定地影响 point conversion

3. 继续盯 fact-like 泛化
   - 重点看 `date_fact / schedule_fact / event_result`
   - 确认这套句层合同不会只停留在行情/数值题上

一句话说：

这轮已经把主瓶颈继续往后推到了“候选句怎么稳定变成直裁句和同位点 point”，下一轮就该围着这条尾差继续收，而不是再回头大补 recall。
