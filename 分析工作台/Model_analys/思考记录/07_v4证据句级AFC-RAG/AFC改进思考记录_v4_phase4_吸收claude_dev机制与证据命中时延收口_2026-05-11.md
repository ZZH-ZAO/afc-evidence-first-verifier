# AFC v4 Phase4 吸收 claude/dev 机制与证据命中时延收口

## 基于什么架构

本轮继续基于 `受控 Search Tool + Playwright 受控救援 + Page Role Contract + Evidence Consumer Gate + 双通道裁决`。

外部分支 `claude/dev` 的审计结论显示：它的 10 样本准确率和 kept_positive 更好，主要收益来自 Playwright 默认开启、entity_fact 纳入救援、filtered rescue 近失页保留、access_path_state 进入 reason。但它的平均 retrieve 更慢。因此本轮不合并整条分支，只吸收能嵌入当前架构的机制，并保留 codex/dev 已有的诚实消费 gate。

## 实现了什么

代码层完成三类吸收：

- `retrieval.py` 默认开启 `ENABLE_PLAYWRIGHT`，但仍保留每 claim 的救援预算和 ROI 诊断。
- `entity_fact` 进入 Playwright rescue、fact-page review、core second-pass review、pre-filter rescue 的高价值事实类型集合。
- 新增 `filtered_rescue_pool`：当高价值 claim 有原始结果但全被过滤时，只把一个分数最高的近失页作为诊断/二次消费候选，不直接推动标签。
- 对 `sogou_html` 和 `playwright_duckduckgo` 加 timeout cap，并对同一 claim 内的慢 Sogou 路径做 stop-loss，避免成功率靠无上限变慢换来。
- `solve.py` 透出 `filtered_rescue_pool_state/reason/score/promoted`，让 claim diagnostics 能直接看见近失页是否进入消费层。

## 解决了什么

本轮主要解决“证据其实出现过，但救援和近失页没有稳定进入消费层”的问题。

固定 5 锚点对比 BX/BZ 基线：

- raw：`63 -> 111`
- kept：`13 -> 28`
- answer candidates：`29 -> 56`
- stable direct point：`1 -> 3`
- Playwright rescue succeeded：`1 -> 11`
- filtered rescue pool promoted：`0 -> 12`

关键样本：

- `afc_0001` 从 `raw=12 / kept=0 / candidates=0` 变成 `raw=18 / kept=6 / candidates=14`，说明不再是纯入口空转。
- `afc_0002` 保持 `1`，没有被更积极的救援误伤。
- `afc_0008 / afc_0010` 保持 `2`，说明 page-role gate 和 direct evidence gate 仍然挡住了泛页、近失页的误抬。

## 还卡在哪

本轮还没有完全达到“成功率更高且用时更短”的最终停点。

- 平均 `retrieve` 从 BX/BZ 的约 `28.9s` 上升到 `43.9s`，虽然比第一版吸收的 `61.9s` 已经收回不少，但仍慢。
- `afc_0010` 仍是长尾，`retrieve=102.254s`，说明 numeric/rate 类多 claim 仍容易触发多次救援和详情读取。
- `filtered_rescue_pool` 已经把近失页送进 `same_slot_reviewed_but_blocked`，但多数还没有闭合成可直接裁决点，这说明下一层瓶颈转向 point grounding，而不是继续盲目扩检索。

## 现有方案还能不能继续解

能继续解，而且优先在现有方案内解。

下一步不应继续扩大 provider 或放宽裁决，而是做三件事：

1. 对 `numeric_fact` 长尾 claim 加更强的 per-claim rescue/detail 总预算。
2. 对 `filtered_rescue_pool` 进入消费层后的失败原因做分桶：时间不匹配、主体不匹配、指标不匹配、只有背景评论。
3. 对 `afc_0010` 这类汇率/中间价题，把 point grounding 优先级前移到同日、同指标、同口径，而不是继续搜更多泛汇率页。

## 如果不能，再去外部检索

暂时不需要立刻外部检索。当前失败可以被现有框架解释：

- 入口和救援已经有明显进展。
- page-role gate 没有误伤 `afc_0002`。
- 伪证据没有误抬 `afc_0008 / 0010`。
- 剩余问题主要是时间成本和 point grounding，不是现有架构解释不了。

只有当后续发现 `filtered_rescue_pool` 和 point grounding 都无法把同日、同主体、同指标闭合，或者 Playwright 长尾无法通过预算收住，才进入外部检索阶段，重点看 2026 browser-agent、hosted search、grounding 的成本控制和证据页选择策略。

## 项目动机记录

### 分类

证据链 / Workflow / 测试与回归

### 这次要做什么

吸收 `claude/dev` 已经被审计证明有效的检索救援机制，但不合并它的整套更慢链路。

### 动机是什么

当前系统不是完全搜不到，而是很多关键 claim 卡在“搜到一点、过滤掉、Playwright 没接手、上层只看到没证据”。这会让事实核查效果停在可解释但不够有用的状态。

### 对项目有什么实际作用

让检索从“诚实地说失败”推进到“尽量把近失证据送到消费层”，同时仍然防止泛页和伪证据直接推标签。

### 具体场景是什么

像 `afc_0001` 这类开盘事实、`afc_0010` 这类汇率事实，原先可能停在 kept=0 或弱候选。现在能把更多 raw/kept/candidate 送进 same-slot review，再由 gate 决定能不能裁决。

### 应该怎么使用

回看 debug 时重点看：

- `playwright_rescue_state`
- `filtered_rescue_pool_state`
- `filtered_rescue_pool_promoted`
- `readiness_promotion_source`
- `point_consumption_state`
- `direct_evidence_gate_result`

### 对用户意味着什么

用户能看到系统不再只是说“没证据”，而是能区分“证据进来了但还不可裁决”和“入口仍失败”。这让下一轮修复更有方向。

### 对开发者意味着什么

开发者不要再简单放宽过滤器或直接抬标签。近失页可以进消费层，但必须经过 page-role 和 point gate。

### 当前结论

本轮提升了证据进入消费链的能力，但时延仍未完全达标。它是有效吸收，不是最终收口。

### 下一步建议

围绕 `afc_0010` 的长尾和 `filtered_rescue_pool -> same_slot_reviewed_but_blocked` 的失败原因做点位闭合，而不是继续扩大检索入口。

## 验证记录

命令：

```powershell
python -m py_compile retrieval.py solve.py evidence.py
python solve.py --input local_dev/tmp/phase4_bmbnbo_anchor_input_sample0410.json --output local_dev/tmp/phase4_absorb3_anchor_sample0410_output.json --debug-output local_dev/tmp/phase4_absorb3_anchor_sample0410_debug.json --perf-output local_dev/tmp/phase4_absorb3_anchor_sample0410_perf.json --workers 4 --no-resume
```

产物：

- `local_dev/tmp/phase4_absorb3_anchor_sample0410_output.json`
- `local_dev/tmp/phase4_absorb3_anchor_sample0410_debug.json`
- `local_dev/tmp/phase4_absorb3_anchor_sample0410_perf.json`

标签：

- `afc_0001 = 2`
- `afc_0002 = 1`
- `afc_0003 = 2`
- `afc_0008 = 2`
- `afc_0010 = 2`

