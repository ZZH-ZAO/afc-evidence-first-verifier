## AFC v4 Phase4 下一步计划（主瓶颈转向 retrieval conversion 链）

### 背景

结合当前两份 Phase4 主文档、现有主链代码状态，以及本轮对外部最新权威资料的复核，当前可以明确一个判断：

- 现在的主瓶颈已经不再是“上游 `evidence_need_program` 完全不清楚”
- 而是“已经大致知道要什么证据了，但还没有稳定打通 `recall -> retained page -> direct candidate -> point conversion` 这条链”

这意味着下一步不应该继续优先扩上游字段面、再补更多 taxonomy，也不应该急着再做一轮大 prompt 加法。

下一步更值得做的是：把已经形成的证据需求中间层，真正变成稳定抓证据、留证据、转证据的执行合同。

---

## 本轮总目标

把当前 AFC v4 主链从“越来越会解释为什么没判出来”，推进到“越来越能稳定抓到真正可裁决的证据点”。

本轮只围绕这个目标推进，不扩平面功能。

---

## 本轮冻结项

本轮默认不做：

- `official closure` 继续扩张
- `solve_submit.py` 合流
- fallback 扩权
- few-shot 注入
- API 层 `structured outputs` 迁移
- 全量回归

唯一主基线仍是 `solve.py`。

---

## 下一步按 3 个实现包推进

### 实现包 N：统一 slot 真相源，停止 `solve / retrieval / evidence` 三处漂移

#### 目标

把 `decision_slots / required_slot_profile / missing_required_slots` 收成唯一一套主合同。

现在的问题不是没有 slot，而是：

1. `solve.py` 在产出一套
2. `retrieval.py` 在按另一套做 readiness 判断
3. `evidence.py` 又在按自己的方式推断 point conversion block

这会导致同一条 claim 明明只缺一个东西，却在三层报出三种不同解释。

#### 本包怎么做

- `evidence_need_program` 继续作为唯一 slot 合同入口
- 统一 `required_slot_profile` 的产出逻辑，不再让 `retrieval.py` 和 `evidence.py` 再维护一份影子版本
- `missing_required_slots` 改成真正的“两段式判定”：
  1. 先看 program 自己是不是没填
  2. 再看 retrieval / evidence 里是不是已经有同义位点命中
- `point_conversion_block_reason` 和 `missing_required_slots` 解耦：
  - 真缺 slot 才说缺口
  - slot 已有但口径不对，优先落到 `not_same_fact_slot / numeric_not_normalizable / date_role_mismatch / result_granularity_mismatch`

#### 这个包做完后的效果

- 同一个 claim 的 slot 缺口只剩一套解释
- `missing_required_slots` 更像真实缺口，而不是宽提醒
- 后面你看 debug 时，不会再出现“明明 slot 在，但还被说成缺 slot”

#### 重点文件

- `solve.py`
- `retrieval.py`
- `evidence.py`

#### 包级验收

1. `afc_0008 / 0010` 仍保持 `2`，但 `missing_required_slots` 数量继续下降
2. 至少 1 个 retained-page case 能从“缺 slot”收成“slot 已有，但不是同一事实位点/口径”
3. 三层不再出现同一 claim 各报一套 required slot 的情况

---

### 实现包 O：把 `retained page -> direct candidate -> point` 的阻塞链正式协议化

#### 目标

不再只停在“页保住了但没证据”这句话，而是明确卡在：

1. 页层
2. 句层
3. 点层

也就是把 retained-page 之后的真实损耗链收清楚。

#### 本包怎么做

顶层 `claim_pipeline_diagnostics` stage 集合保持不扩张，继续只用现有：

- `provider_recall`
- `retrieval_filter`
- `retrieval_readiness`
- `evidence_partial_but_incomparable`
- `evidence_point_not_convertible`
- `evidence_unsupported`

但在内部 debug 里把阻塞链明确拆成三段：

1. **页层**  
   页虽然被保下来了，但只是 anchor 命中，不是真正 ready material

2. **句层**  
   页里有相关信息，但抽不出能直接回答该 claim 的句子

3. **点层**  
   句子有了，但还转不成同位点可比的 point

同时固定协议边界：

- `retrieval.py` 负责解释“为什么页没准备好”
- `evidence.py` 负责解释“为什么句/点没法直接裁”
- `solve.py` 只消费这些结果，不再自己补第二套解释

#### 这个包做完后的效果

以后你再看一个 case，不会只看到：

- 有页面
- 但没证据

而会更明确看到：

- 页只是在 anchor 上相关
- 页里有句子，但不是 direct assertion
- 句子是 related material，不是同一事实位点
- 点已经抽出来了，但时间/指标/角色口径不一致

#### 重点文件

- `retrieval.py`
- `evidence.py`
- 少量接线 `solve.py`

#### 包级验收

1. 对任一 `raw_results > 0 且 kept_web > 0` 的 claim，不允许最终只剩模糊 `provider_recall`
2. `afc_0001` 之外，至少再有 1 个 fact-like claim 能明确落出“页保住了，但卡在句层或点层”
3. `afc_0008 / 0010` 继续保持 partial incomparable 优先，不因协议细化误升 `1`

---

### 实现包 P：把反爬 / challenge / detail-read failure 升成主链一等健壮性问题

#### 目标

把“环境抓取失败”和“真的没证据”正式拆开。

现在虽然已经接了：

- anti-bot status 识别
- challenge / captcha / Cloudflare 文本识别
- requests 失败后的 Playwright fallback
- `anti_bot_blocks` 统计

但它还更像抓取层内部能力，没有完全升级成主链正式可见的失败类型。

#### 本包怎么做

- 继续保留现有 anti-bot / challenge / Playwright fallback 机制
- 把以下状态正式纳入主链可见 debug：
  - 真 recall 不足
  - detail 页被 challenge 替代
  - detail 空正文
  - requests 失败但 Playwright rescue 成功
  - requests 和 Playwright 都失败
- source health 和 source reorder 开始显式消费：
  - `anti_bot_blocks`
  - `detail_read_failed`
  - `playwright_rescued`
- reason 层固定原则：
  - 如果主要阻塞是环境抓取失败，不要直接把话术写成 claim unsupported
  - 先说当前是访问/读取受阻，再说这导致哪一层无法形成证据

#### 这个包做完后的效果

以后同学跑出来一个“明明像有材料，但系统说没证据”的 case，至少能先区分：

1. 真没搜到
2. 搜到了但被过滤掉
3. 页保住了但正文没拿下来
4. 正文拿下来了但没转成 direct point

这样就不会把环境问题误怪到 claim / slot / prompt 头上。

#### 重点文件

- `retrieval.py`
- `playwright_retrieval.py`
- 少量接线 `solve.py`

#### 包级验收

1. 至少 1 个 challenge / anti-bot case 能显式打出环境阻塞痕迹
2. 如果 Playwright rescue 成功，debug 能看出“原始请求失败，但浏览器兜底成功”
3. 不再大面积把 challenge 页、空正文、403/429 误并成普通 unsupported

---

## Test Plan

继续只跑固定 5 个锚点：

- `afc_0001`
- `afc_0002`
- `afc_0003`
- `afc_0008`
- `afc_0010`

在这 5 个锚点之外，额外补 1 到 2 个容易触发反爬或 detail-read failure 的真实站点烟测，不作为 gold 对齐样本，只作为健壮性样本。

固定检查面：

- `evidence_need_program`
- `required_slot_profile`
- `missing_required_slots`
- `slot_alignment_status`
- `claim_pipeline_diagnostics`
- `readiness_block_reason`
- `point_conversion.block_reason`
- `source_pollution_stats`
- `anti_bot_blocks`
- `playwright_reasons / playwright_skipped_reasons`
- `_evidence_non_decidable_state`
- `_decision_basis`
- `_decision_policy`

---

## 本轮通过标准

### 1. slot 真相源通过标准

- 同一 claim 的 required slot 不再在三层漂移
- `missing_required_slots` 更接近真实缺口，而不是宽提醒

### 2. retained-page 转换链通过标准

- 对 `raw_results > 0 且 kept_web > 0` 的 case，主阻塞必须能稳定落在：
  - `retrieval_readiness`
  - `evidence_point_not_convertible`
  - `evidence_partial_but_incomparable`

其中之一，不再只剩一句模糊“缺证据”

### 3. 反爬健壮性通过标准

- challenge / anti-bot / detail blocked 能和普通 recall 区分开
- rescue 成功与 rescue 失败都能在 debug 里留下痕迹
- 不因为补健壮性而放宽标签边界

---

## 当前结论

下一步不需要推翻现有 `evidence_need_program` 路线，也不需要重新发明一套上游 prompt 架构。

真正该换的是发力点：

- 不再继续优先扩“模型怎么描述证据需求”
- 转而优先打通“系统怎么把这个需求变成真的证据点”

一句话说，就是把主链从：

**会解释**

推进到：

**会抓证据**

---

## 下一步建议

开发顺序建议固定为：

1. 先做 **N：slot 真相源统一**
2. 再做 **O：retained-page 转换链协议化**
3. 最后做 **P：反爬 / detail-read 主链化**

不要倒过来做。  
因为如果 slot 合同本身还漂，后面你很难判断一个 blocked case 到底是环境问题、页面问题，还是 slot 定义本身就不一致。

---

## Git / 分支 / 提交约定

从当前阶段开始，AFC v4 Phase4 主链默认采用以下协作方式：

1. 远端主仓库：
   - `origin = https://github.com/ZZH-ZAO/afc-evidence-first-verifier`

2. 长期开发分支：
   - 默认开发分支为 `codex/dev`
   - `main` 作为主基线保留，不在其上持续堆叠每轮实验性改动

3. 每轮开发完成后的默认动作：
   - 先完成本轮最小验证
   - 再做一次提交
   - 默认按“每轮一个提交”收口，不把多轮无关改动混在同一个 commit 里

4. 提交约定：
   - 提交信息应直接反映本轮机制变化
   - 推荐使用：
     - `feat(phase4): ...`
     - `fix(retrieval): ...`
     - `refactor(evidence): ...`
     - `docs(phase4): ...`

5. Codex 默认执行口径：
   - 后续只要进入可执行开发阶段，默认优先检查当前是否位于 `codex/dev`
   - 若本地尚未建立 `codex/dev`，则以当前 `main` 基线创建并切换
   - 每轮实现完成后，默认把“代码 + 验证 + 必要文档同步”作为一次提交的 done-definition

这条约定的目的不是增加 Git 流程负担，而是保证：
- `main` 始终保持清晰基线
- `codex/dev` 承接持续开发
- 每轮机制变化都能稳定回看、对账和审计
