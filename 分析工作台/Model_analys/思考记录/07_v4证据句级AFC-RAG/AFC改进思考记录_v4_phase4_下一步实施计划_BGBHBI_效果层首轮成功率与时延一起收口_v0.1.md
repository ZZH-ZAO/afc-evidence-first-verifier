# AFC v4 Phase4 下一步实施计划（BG/BH/BI：效果层首轮，成功率与时延一起收口）

## 2026-05-11 BGBHBI 效果层首轮实施单

### 分类

Workflow / 证据链 / 测试与回归

### 基于什么架构

继续基于已经落地的四层主架构推进：

1. 受控 Search Tool
2. Playwright 受控救援
3. authority-first 入口
4. 双通道裁决

这份文档不再讨论要不要换大框架，而是承接前面的协议层结果，把“入口更可解释”继续推进到“效果开始可见、成本开始受控”。

### 实现了什么

本轮实现目标是把下面三件事从概念变成代码里的真实约束：

1. source 顺序合同收口  
   把 `planned_source_order -> post_role_priority_order -> post_budget_selected_order -> final_executed_source_order` 串起来，避免高价值入口在预算、重排和执行阶段被静默打散。

2. Playwright rescue ROI 化  
   把 Playwright 固定成受控救援，而不是“能跑就跑”的旁路手段，明确区分：
   - 什么 trigger 允许救
   - 每个 claim 能救几次
   - 救完有没有回报
   - 哪些 family 已经失败，不该反复再救

3. retrieval 时延止损  
   把检索成本拆到：
   - official discovery
   - search
   - detail fetch
   
   同时让 source health 和 claim 级 stop-loss 真正参与早停。

### 解决了什么

这轮要解决的不是“标签立刻大涨”，而是三个更前置、更关键的问题：

1. 为什么高价值 source 明明规划进来了，最后却没有执行到
2. 为什么 Playwright 看起来参与了，但实际没有形成有效救援
3. 为什么成功率还没明显变好之前，retrieve 已经先变慢了

如果这三件事不先压住，后面的 candidate/point/closure 消费层会一直被入口层噪音污染。

### 还卡在哪

到这一步，系统仍然可能卡在四层中的任意一层：

1. 入口没进来
2. 入口进来了但页没保住
3. 页保住了但 candidate 不可裁决
4. candidate 有了但 point/closure 不成立

本轮只承诺优先打第 1 层和第 2 层，同时把时间代价一起纳入验收，不再允许“靠更慢换一点点成功率”。

### 现有方案还能不能继续解

还能继续解，原因是当前失败仍然大多能被现有框架解释：

1. source 顺序被预算或重排吞掉
2. authority/html 关键 pair 没被稳定保住
3. Playwright 触发了但没有预算边界和失败记忆
4. slow / empty / anti-bot family 还没有在 claim 内被及时止损

这些都属于现有 Search Tool 协议、source policy、rescue policy、source health 可以继续处理的范围，还不需要直接切到新 provider 或新检索范式。

### 如果不能，再去外部检索

只有出现下面情况，才继续触发外部对标：

1. authority-first 入口稳定保住后，仍然大面积 `raw=0`
2. Playwright rescue 已经严格受控，但成功率收益极低
3. success 有改善，但时间始终压不下来
4. 当前 source family 在真实样本上持续整体失效

那时再优先对标 2026 最新官方资料和大厂 agent/search/grounding 实践。

### 和前面文档的关系

#### 和《入口层审计与外部检索架构对标》的关系

那份文档负责回答“我们现在的入口层到底卡在哪里、外部优秀架构怎么做”。  
这份文档负责把那个方向变成效果层施工，不再停留在架构解释。

#### 和《BDBEBF Search Tool 协议化与 Playwright 受控救援》的关系

BDBEBF 解决的是协议层首轮：字段、状态、责任边界先立住。  
BGBHBI 解决的是协议层之后的效果层首轮：让协议真正改变命中率和时延，而不是只增加 debug 可见性。

### 当前结论

当前最合理的推进方式仍然是：

1. 不扩 provider
2. 不引入 LLM 终判
3. 先让高价值 source 真执行、Playwright 真有 ROI、慢源真能止损
4. 只在入口层确实改善后，再继续压 candidate/point/closure

### 下一步建议

1. 先重跑当前代码，生成新的同组 baseline
2. 落地 BGBHBI 三项代码修改
3. 再用同组样本回看：
   - `afc_0001`
   - `afc_0002`
   - `afc_0003`
   - `afc_0008`
   - `afc_0010`
4. 只和这次 baseline 比：
   - 成功率有没有真实改善
   - Playwright 有没有至少 1 个成功救援
   - retrieve 平均耗时有没有失控

### 本轮最小验证结果

本轮已经完成一次 baseline 重跑和三轮实现后回看，当前更接近可继续推进的版本是 `v3`。

#### 已经做到的

1. `afc_0002` 继续稳定为 `1`
2. `afc_0008 / 0010` 没有被误抬
3. `afc_0001` 至少出现了 `raw>0 && kept>0` 的 claim，不再全是纯空转
4. `source_order_trace / final_executed_source_order / retrieval_cost_review / claim_retrieve_stop_reason` 已经进入结果诊断
5. `retrieve` 平均耗时相对新 baseline 仍在可接受区间内上升，没有超过 10%

#### 还没有做到的

1. `Playwright rescue` 还没有跑出稳定的 `playwright_rescue_succeeded`
2. 提升还没有集中打到最关键的 core claim，上升更多体现在“链路更真实、局部 raw/kept 恢复”
3. `official_discovery` 仍然是长尾成本的重要来源，虽然已经收敛，但还不够稳

#### 当前结论

这说明现有方案还能继续解，但还停在“效果层首轮部分通过”，没有到完全验收通过。  
下一轮最值得继续打的，不是再扩新框架，而是：

1. 继续压 `official_discovery` 的长尾成本
2. 把 Playwright rescue 从“失败留痕”推进到“至少 1 个稳定救成”
3. 把已经恢复的 `raw/kept` 更集中地推到关键 core claim 上
