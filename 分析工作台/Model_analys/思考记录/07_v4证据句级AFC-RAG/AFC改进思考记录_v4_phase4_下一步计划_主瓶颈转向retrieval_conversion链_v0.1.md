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
## AFC v4 Phase4 下一步计划（AI/AJ/AK：弱候选句收口 + 位点命中细化 + fact-like 继续泛化）

### Summary

基于 `AF/AG/AH` 首轮实施结果，下一步不再优先扩 recall，不继续扩上游 `evidence_need_program`，也不碰 `official closure`、`solve_submit.py`、fallback 扩权、few-shot 或 structured outputs。

当前新的真实结论已经比较稳定：

- `afc_0001` 已经不是纯 `raw=0`
- 主 claim 已稳定前移到 `retrieval_readiness`
- `answer_candidate_total > 0`
- 但主阻塞仍落在 `candidate_not_direct`
- 非 opening 场景也已出现同类现象，例如：
  - `afc_0007` 的 `date_role_mismatch`
  - `afc_0004` 的 `event_result` 弱候选句

所以这一轮固定顺序为：

1. **AI：继续压 `slot_hit_but_indirect`，把弱候选句往 `direct_candidate` 推**
2. **AJ：细化 `top_candidate_slot_match`，把“句子弱”和“位点错”拆得更稳**
3. **AK：把这套句层直裁合同继续泛化到更多 fact-like claim**

本轮优先目标是机制继续泛化和收口，不是为了围绕 `afc_0001` 做样本化特修，也不是为了强拉更多 `1`。

### Key Changes

### AI：继续压 `slot_hit_but_indirect`

- 主改 `retrieval.py + evidence.py`
- 只覆盖 `core` 或高风险 `supporting` 的：
  - `numeric_fact`
  - `date_fact`
  - `schedule_fact`
  - `event_result`
- 在现有 `sentence_candidate_profile` 基础上，继续收候选句排序合同：
  - 只命中主体或时间，但仍是概述句、解释句、转述句的，继续压低
  - 同时命中 `subject + time_scope + metric_or_relation/status_or_result` 的句子继续抬高
  - 背景评论句、媒体总结句、结论转述句，不允许长期顶在最前
- 不新增新的大类 profile，只收现有 profile 的排序与消费：
  - `direct_candidate`
  - `slot_hit_but_indirect`
  - `numeric_reference_only`
  - `date_reference_only`
  - `background_commentary`
- 新增或细化内部 debug：
  - `candidate_directness_rank`
  - `candidate_slot_coverage`
  - `direct_candidate_promotion_used`

### AJ：细化 `top_candidate_slot_match`

- 主改 `retrieval.py + evidence.py + solve.py`
- 目标不是新增顶层 stage，而是把当前最强候选句到底命中了哪些事实位点拆得更清楚。
- 固定把 `top_candidate_slot_match` 细化为更稳定的组合表达，至少覆盖：
  - `subject`
  - `time_scope`
  - `metric_or_relation`
  - `status_or_result`
  - `date_role`
  - `result_granularity`
- 消费规则固定：
  - 若主体和时间都命中，但结果位点弱，优先继续落 `candidate_not_direct`
  - 若主体和结果命中，但时间角色错位，优先落 `date_role_mismatch`
  - 若主体、时间、结果都相关，但事实位点不是同一层，优先落 `not_same_fact_slot`
  - 若结果是局部过程、分段结果、盘中状态，而 claim 要最终事实，优先落 `result_granularity_mismatch`
- `insufficient_evidence_reason(...)` 同步继续收口：
  - 不再泛说“有相关材料”
  - 要更明确说清是“句子不够直答”还是“位点打偏了”

### AK：fact-like 继续泛化，而不是停在 opening numeric

- 主改 `evidence.py + solve.py`
- 继续验证这套机制不是只对 opening / intraday / close 这种金融数值位点有效，而是对更一般的 fact-like claim 同样成立。
- 本轮重点泛化到两类：
  - `date_fact / schedule_fact`
    - 发布日 vs 生效日
    - 公告时间 vs 报道时间
    - 举办日 vs 报名/公布日
  - `event_result`
    - 最终结果 vs 过程结果
    - 全场结果 vs 单节/单局/局部结果
- 不新增新的 point block reason 大枚举，只继续优先消费现有：
  - `candidate_not_direct`
  - `not_same_fact_slot`
  - `date_role_mismatch`
  - `result_granularity_mismatch`
- 核心要求：
  - 已有候选句时，不允许大量回退成泛 `related_but_not_assertive`
  - 已进入 retained/readiness 的 fact-like row，不允许又被纯 `provider_recall` 抢主导

### Important Internal Changes

- 无外部提交 schema 变化
- 无 label schema 变化
- 无新增顶层 pipeline stage
- 允许新增内部 debug/诊断字段：
  - `candidate_directness_rank`
  - `candidate_slot_coverage`
  - `direct_candidate_promotion_used`

### Test Plan

固定继续回看 5 个锚点：

- `afc_0001`
- `afc_0002`
- `afc_0003`
- `afc_0008`
- `afc_0010`

再补 2 个非 gold fact-like 烟测，优先各选 1 个：

- `date_fact / schedule_fact`
- `event_result`

固定检查项：

- `claim_pipeline_diagnostics.items`
- `answer_candidate_total`
- `sentence_candidate_profile`
- `top_candidate_slot_match`
- `candidate_directness_rank`
- `candidate_slot_coverage`
- `direct_candidate_gap_reason`
- `readiness_block_reason`
- `point_conversion.block_reason`
- `_decision_basis`
- `_decision_policy`

### Acceptance Criteria

1. **AI 包**
   - 至少 1 个 case 的最强候选句从 `slot_hit_but_indirect` 更明确前移到更高 directness 排序
   - 评论句、背景句不再长期顶在最前

2. **AJ 包**
   - 至少 1 个 case 能更稳定地区分：
     - 句子不够 direct
     - 时间/日期角色错位
     - 结果粒度不一致
     - 同相关但不同事实位点
   - `insufficient_evidence_reason(...)` 不再泛化成“有材料但不足”

3. **AK 包**
   - 至少 1 个非金融 fact-like claim 能稳定落出句层或点层阻塞，而不是退回泛 unsupported
   - `afc_0001` 若仍为 `2` 也接受，但继续停在句层/点层，不回退到 recall/filter 主导
   - `afc_0002` 继续稳定为 `1`
   - `afc_0008 / 0010` 继续保持 `2`
   - `afc_0003` 不被误伤
   - 不允许新增 `unsupported structured detail -> 1`

### Assumptions

- 主基线仍只有 `solve.py`
- 当前 `N/O/P`、`Q/R/S`、`T/U/V`、`W/X/Y`、`Z/AA/AB`、`AC/AD/AE`、`AF/AG/AH` 默认有效，不回滚
- 本轮默认不做：
  - 新一轮 recall probe 扩张
  - rescue 字段面继续扩张
  - fallback 扩权
  - `solve_submit.py` 合流
  - few-shot
  - structured outputs
  - 上游 program 新字段
- 本轮默认选择“句层直裁合同继续收口 + fact-like 继续泛化优先”，不是回头重启大规模 recall 扩张

## AI/AJ/AK 首轮实施补记（2026-05-10）

这轮已经完成首轮代码实现与最小验证，当前需要明确两点：

1. 这轮已经证明有效的部分
   - `candidate_directness_rank`
   - `candidate_slot_coverage`
   - `direct_candidate_promotion_used`
   这三类句层诊断已经能稳定透传到 `retrieval.py -> evidence.py -> solve.py`
   - `date_role_mismatch`
   - `numeric_not_normalizable`
   - `candidate_not_direct`
   这些阻塞原因已经开始比之前更稳定地落出来

2. 这轮验证后确认的新瓶颈
   - 主瓶颈仍然不是回头补大规模 recall
   - 更真实的新问题是：
     - 很多 row 的位点命中已经够强
     - 但最强候选句仍停在 `slot_hit_but_indirect`
     - 同时 `afc_0002` 暴露出一个新回退：可裁决的 structured detail 错误没有被当前句层主导逻辑稳定接住

所以从总文档和这轮状态合起来看，下一步优先级应该收成：

1. 先补 `supporting structured detail` 的保留和消费闭环
   - 防止 `0002` 这类原本可以靠逻辑闭合判 `1` 的 case 被句层进展盖掉

2. 再补 `slot_hit_but_indirect -> direct_candidate` 的真晋级
   - 不是再加一层解释，而是把已经命中主体/时间/结果位点的句子更稳定地推进到可直裁候选

3. 最后继续向非金融 fact-like claim 泛化
   - 重点盯：
     - `date_role_mismatch`
     - `result_granularity_mismatch`
     - `not_same_fact_slot`

一句话收口：

AI/AJ/AK 这轮已经把句层诊断做真了，但也把新的收口问题暴露得更彻底了。下一轮最该补的，不是 recall 数量，而是“弱候选句晋级”和“structured detail 可裁决错误不要丢”。

---

## AFC v4 Phase4 总的下一步计划（AL/AM/AN：双通道保真 + 逻辑反证保留 + 网页证据链继续推进）

### Summary

基于当前总文档、`AI/AJ/AK` 首轮状态、以及这次重新确认的 `afc_0002` 类回退，本轮需要把下一步计划正式收成一版“总计划”，不再把问题只看成单一的网页检索链问题。

当前已经可以明确：

1. 系统里至少存在两种真实、都应被保留的“可裁决错误”来源
   - **网页 direct evidence 通道**
     - 找到网页
     - 保住页面
     - 抽出 direct candidate
     - 转成同位点 point
   - **supporting structured detail 逻辑反证通道**
     - 不一定依赖最强网页直裁句
     - 但若题面中的细节 claim 本身已经形成稳定逻辑闭合
     - 且现有证据足以推出“这个细节说法和事实拼不起来”
     - 也应该稳定落到 `secondary_detail_direct_refutation`

2. 这两条通道现在并没有很好共存
   - `0001 / 0008 / 0010` 暴露的是网页 evidence chain 还在继续打磨
   - `0002` 暴露的是 structured detail 的逻辑反证被句层主导逻辑盖过去了

所以本轮的目标不是“多判一次”，而是把这两条本来就该共存的判错通道真正协议化，避免：

- 一边继续推进网页 direct evidence
- 一边又把原本可裁决的 structured detail 错误弄丢

固定顺序：

1. **AL：先把 structured detail 逻辑反证通道保回来**
2. **AM：再把双通道的聚合优先级和互不吞噬关系写稳**
3. **AN：最后继续沿网页 evidence chain 收真瓶颈**

### Key Changes

### AL：supporting structured detail 的保留与逻辑反证恢复

- 目标不是放宽 `unsupported structured detail -> 1`
- 目标是只把**本来就可裁决的 structured detail 错误**稳定保留下来

- 只重点覆盖：
  - `supporting structured detail claim`
  - 其内容属于可核对的：
    - 数量
    - 日期
    - 比分/战绩
    - 身份/归属
    - 金额/数值

- 固定恢复两件事：
  1. **claim surface 保留**
     - 不让 `0002` 这类“2胜2负”细节在 claim 拆分、句层重排、supporting row 竞争中被悄悄冲掉
  2. **stable logic refutation 再次可触发**
     - 若 supporting detail 本身已经是明确事实位点
     - 且现有网页/结构化句子已经足够推出逻辑闭合冲突
     - 则允许继续落：
       - `stable_logic_refutation`
       - 最终 `secondary_detail_direct_refutation`

- 恢复原则固定为：
  - 必须是“细节本身可核对”
  - 必须是“逻辑闭合后稳定冲突”
  - 不能只是“看着不对劲”
  - 不能因为没有 direct evidence point 就把 unsupported detail 硬抬成 `1`

- 允许补充的内部 debug：
  - `structured_detail_retained`
  - `logic_refutation_candidate`
  - `logic_refutation_basis`
  - `logic_refutation_gap_reason`

### AM：双通道聚合合同，禁止互相吞掉

- 主改 `solve.py`，但不改顶层 label schema，不新增第二判标器。

- 固定把最终可裁决错误分成两条来源：
  1. **direct evidence refutation**
     - 有 direct webpage point
     - 同位点、同口径、可直接裁
  2. **structured-detail logic refutation**
     - 主需未必被 direct point 正面打穿
     - 但 supporting detail 本身已经能被稳定逻辑反证

- 聚合时固定几个规则：
  - 如果 row 已经进入 `raw>0 && kept>0 && answer_candidate_total>0`
    - 不能再被纯 `provider_recall` 抢主导
  - 如果 supporting detail 已形成稳定逻辑反证
    - 不能再被“句层还不够 direct”整行压掉
  - 如果只有 weak sentence progress，没有可裁决逻辑反证
    - 不能反过来假装成 `secondary_detail_direct_refutation`

- 也就是说，最终不是“谁声音大谁赢”，而是：
  - direct point 够，就走 direct point
  - direct point 不够，但 structured detail 已稳定逻辑反证，就走 detail refutation
  - 两边都不够，就老老实实留在 `2`

- `insufficient_evidence_reason(...)` 也要同步收口：
  - 有网页候选句但不够直裁：说句层/位点阻塞
  - structured detail 已被保留但还不足以闭合：明确说“细节已保留，但还未形成稳定逻辑反证”

### AN：网页证据链继续推进，但只打真瓶颈

- 这部分继续沿当前 Phase4 主线推进，但不再把它当成唯一主线。

- 固定只补三件事：
  1. **access / rescue 稳定性**
     - 减少 `source_access_blocked_without_rescue`
     - 区分“世界上没证据”和“我们没拿到页”
  2. **weak direct candidate 晋级**
     - 继续压 `slot_hit_but_indirect`
     - 让命中 `subject + time_scope + metric/status` 的句子更稳定升到 `direct_candidate`
  3. **same-slot / same-role conversion 收口**
     - 更稳定落出：
       - `not_same_fact_slot`
       - `date_role_mismatch`
       - `result_granularity_mismatch`
       - `numeric_not_normalizable`

- 固定原则：
  - 网页 evidence chain 继续推进
  - 但它不能再把 structured detail 可裁决错误挤没
  - structured detail 通道恢复后，也不能倒过来污染网页 direct evidence 的真实性要求

### Important Internal Changes / Interfaces

- 无外部提交 schema 变化
- 无 label schema 变化
- 无 `solve_submit.py` 合流
- 无新增顶层 pipeline stage
- 允许新增内部 debug 字段：
  - `structured_detail_retained`
  - `logic_refutation_candidate`
  - `logic_refutation_basis`
  - `logic_refutation_gap_reason`

### Test Plan

固定继续回看 5 个锚点：

- `afc_0001`
- `afc_0002`
- `afc_0003`
- `afc_0008`
- `afc_0010`

再补 2 个烟测：

- 1 个 supporting structured detail 明显可做逻辑闭合反证的 case
- 1 个 `date_fact / event_result` 非金融 fact-like case

固定检查项：

- `claim_pipeline_diagnostics.items`
- `answer_candidate_total`
- `sentence_candidate_profile`
- `top_candidate_slot_match`
- `direct_candidate_gap_reason`
- `structured_detail_retained`
- `logic_refutation_candidate`
- `logic_refutation_basis`
- `point_conversion.block_reason`
- `_decision_basis`
- `_decision_policy`

### Acceptance Criteria

1. **AL 包**
   - `afc_0002` 这类原本可由 supporting detail 稳定逻辑反证落 `1` 的 case，至少恢复 1 个
   - 但不允许新增 `unsupported structured detail -> 1`
   - “2胜2负”这类逻辑闭合 detail 不再因为句层重排被静默丢失

2. **AM 包**
   - direct evidence 通道和 structured detail 通道能同时存在，不再互相吞掉
   - 已有候选句的 row，不再把所有问题都打回泛 recall
   - 已有稳定逻辑反证的 supporting detail，不再被泛 `candidate_not_direct` 压过去

3. **AN 包**
   - `afc_0001` 若仍为 `2` 也接受，但主因要真实停在 access / 句层 / 点层，不再混回黑盒 recall
   - `afc_0008 / 0010` 继续保持 `2`，并维持 conversion / incomparability 主导
   - 至少 1 个 fact-like case 的最强候选句继续向 `direct_candidate` 前移
   - `afc_0003` 不被误伤

### Assumptions

- 主基线仍只有 `solve.py`
- 当前 `N/O/P`、`Q/R/S`、`T/U/V`、`W/X/Y`、`Z/AA/AB`、`AC/AD/AE`、`AF/AG/AH`、`AI/AJ/AK` 默认有效，不回滚
- 本轮默认不做：
  - 新一轮 recall probe 扩张
  - rescue 字段面继续扩张
  - fallback 扩权
  - `solve_submit.py` 合流
  - few-shot
  - structured outputs
  - 上游 program 新字段

- 本轮总原则固定为：
  - **网页证据链继续推进**
  - **structured detail 逻辑反证必须保留**
  - **两条通道都要真实，谁也不能靠吞掉另一条来“看起来更强”**

## AL/AM/AN 首轮实施补记（2026-05-10）

这轮已经完成首轮代码落地与最小验证，当前可以明确三点：

1. 已经确认生效的部分
   - `afc_0002` 已恢复为 `1`
   - 且这次不是靠宽松抬 unsupported detail，而是靠：
     - supporting structured detail claim 被保留
     - `computed` 逻辑点被同主题 detail claim 消费
     - 最终重新落到 `secondary_detail_direct_refutation`
   - `structured_detail_retained / logic_refutation_candidate / logic_refutation_basis / logic_refutation_gap_reason`
     已经能稳定透传到 debug

2. 这轮顺手收住的新边界
   - 交锋总战绩的逻辑反证不能泛化误伤“赛后战绩 40胜36负”这类别的 numeric detail
   - 没有新增 `unsupported structured detail -> 1`

3. 仍然没变的主瓶颈
   - `0001 / 0003 / 0007` 仍大量停在 recall / access
   - `0008 / 0010` 仍主要卡在句层 directness 或同位点 conversion

所以从这轮结果反推，下一步优先级可以继续保持不变，但重点更清晰了：

1. 先把 `structured detail retained but unresolved` 的 gap 再细化
2. 再继续推 `slot_hit_but_indirect -> direct_candidate`
3. 最后继续补 access / rescue 稳定性

## AO/AP/AQ 首轮实施补记（2026-05-10）

这轮已经完成首轮代码落地与最小验证，当前可以明确四点：

1. 已经确认生效的部分
   - `afc_0002` 继续稳定为 `1`
   - supporting structured detail 的 retained-but-unresolved 不再只剩一个粗粒度 `no_logic_refutation_candidate`
   - `claim_pipeline_diagnostics.items` 已能透出：
     - `logic_refutation_state`
     - `logic_refutation_closure_stage`
     - `logic_refutation_block_reason`
     - `direct_candidate_promotion_basis`
     - `candidate_promotion_block_reason`
     - `candidate_slot_coverage_summary`
     - `access_path_state`
     - `access_block_source`
     - `rescue_attempt_state`

2. 这轮顺手收住的新边界
   - `afc_0001` 一度因为 supporting date detail 被旧新闻页误打成 `1`，现已收回到 `2`
   - 对 supporting `date_fact / schedule_fact`，非官方且与现有 supporting signal 自相冲突的 `date_mismatch` 不再直接抬成 `secondary_detail_direct_refutation`
   - 没有新增 `unsupported structured detail -> 1`

3. 这轮得到的更真实瓶颈分层
   - `structured detail` 侧已经能区分：
     - `retained_without_logic_point`
     - `logic_point_topic_mismatch`
     - `same_topic_logic_point_unstable`
     - `shadowed_by_direct_channel`
   - 网页链路侧已经能区分：
     - `source_access_blocked`
     - `provider_recall_insufficient`
     - `page_access_or_read_blocked`
     - `partial_progress_available`

4. 仍然没变的主瓶颈
   - `0001 / 0003 / 0007` 仍大量停在 access / recall / filter 前段
   - `0008 / 0010` 仍主要卡在 weak candidate 到 same-slot conversion 的后段

所以从这轮结果反推，下一步优先级可以继续保持不变，但重点已经更清楚：

1. 继续收 `same_topic_logic_point_unstable` 的闭合条件
2. 继续把 `slot_hit_but_indirect` 稳定推向 `direct_candidate`
3. 继续把 access blocked、provider recall insufficient、page read failed 的最终 reason 说得更一致
