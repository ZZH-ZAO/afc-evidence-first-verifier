# AFC v4 Phase4 BX/BY/BZ 实施状态同步：Page Role Contract 与可裁决证据消费

## 基于什么架构

本轮继续基于 `受控 Search Tool + authority-first 入口 + Evidence Page Contract + 双通道裁决`。

关键判断是：现在主要问题不是“完全搜不到”，而是“搜到的页面经常只是入口页、官网首页、门户页、泛新闻或背景评论页”。这些页面和 claim 相关，但不能直接裁决 `subject + time + metric/result/status`。

因此本轮把页面分成四类：

- `evidence_page`：可以直接进入候选句和 point 消费。
- `entry_page`：只能作为入口，需要继续跟内页、详情页、表格页。
- `generic_page`：只保留诊断，不允许推动裁决。
- `blocked_page`：进入访问/反爬诊断。

## 实现了什么

代码层已完成首轮接入：

- `retrieval.py`
  - 新增 `page_role / page_role_reason / page_role_contract_score`。
  - 新增 `entry_page_follow_required / evidence_page_ready / generic_page_block_reason`。
  - 在 `page_utility_features(...)` 后接入 `page_role_contract_features(...)`。
  - 扩展 `expand_official_inner_link_candidates(...)`，把官网首页/入口页跟进显式记为 `entry_follow_state / entry_follow_trigger / entry_follow_candidates / entry_follow_block_reason / entry_follow_latency_ms`。
  - diagnostics 增加 `page_roles / raw_page_roles / entry_follow_state / entry_follow_kept_evidence_pages` 等字段。

- `solve.py`
  - 新增 page-role 消费闸门。
  - 把 `evidence_bundle` 里的页面角色映射回候选句和 supporting/refuting point。
  - `entry_page / generic_page / blocked_page / pseudo evidence` 不再允许触发 `decision_useful_hit`。
  - 如果 direct point 来自非 `evidence_page`，会降级为诊断候选，并写出 `direct_evidence_gate_result`。

## 解决了什么

本轮解决的是“泛页污染裁决”的结构问题：

- 官网首页不再因为 `official` 身份自动变成可裁决证据。
- 知乎、百科、门户频道、背景评论页不再能推动 `stable_direct_point`。
- `candidate_progress_from_kept_page` 必须来自真正可消费页面或合格结构化表格点。
- `afc_0008 / afc_0010` 这类容易被当前牌价页、门户页、讨论页污染的样本，会更明确地停在 page role gate，而不是误抬标签。

## 还卡在哪

最小验证时，`afc_0002` 出现了一次外部入口波动：多个 claim 的 `raw_results=0`，主要落在 `sogou_html anti_bot` 和高优先源无 raw，导致没有 web page 进入 page-role 消费层。

这说明本轮 page-role gate 已能防伪证据，但还不能单独解决“入口完全没 raw”的网络/反爬问题。也就是说：

```text
入口没进来 -> page_role 无法发挥作用
入口进来了但泛 -> page_role/entry-follow 才能发挥作用
```

## 现有方案还能不能继续解

能继续解，但要分层：

- 如果 `raw=0`，继续回入口层：source health、Playwright rescue、非 Sogou authority-first。
- 如果 `raw>0 && kept=0`，继续看过滤层和 entry-follow。
- 如果 `kept>0` 但 `page_role=entry_page/generic_page`，继续做内页跟进和表格抽取。
- 如果 `page_role=evidence_page` 但 point 不成立，才进入 candidate/point/closure 消费层。

本轮之后，不应该再把“泛页很多”误判成“证据已经够了”。它只说明入口有进展，但证据页还没打通。

## 如果不能，再去外部检索

如果后续连续验证出现：

- authority-first 仍稳定拿不到 raw；
- entry-follow 候选一直为空；
- 表格页能打开但抽不出结构化点；
- Playwright rescue 成本高但收益低；

才进入外部检索阶段，重点查 2026 最新的 hosted search / grounding / browser-agent 实践，而不是继续堆本地规则。

## 当前结论

BX/BY/BZ 第一刀已经把“页面是否可裁决”接进主链。它的价值不是立刻让所有样本有证据，而是让系统不再把入口页、泛页、伪证据当成可裁决证据。

下一步最该跑固定锚点，重点看：

- 至少一个样本是否出现 `entry_page -> evidence_page` 跟进；
- `afc_0008 / 0010` 是否继续不误抬；
- `afc_0002` 在网络正常时是否仍能保持 `1`；
- 若仍无证据，失败是否明确落在 `raw=0`、`entry_follow_block_reason`、`direct_evidence_gate_result` 之一。

## 2026-05-11 最小验证补记

已跑固定 5 个锚点：

- 输出：`local_dev/tmp/phase4_bxbz_anchor_output.json`
- debug：`local_dev/tmp/phase4_bxbz_anchor_debug.json`

结果：

- `afc_0002` 保持 `1`，`c1` 出现 `page_role=evidence_page`，`direct_evidence_gate_result=allowed_evidence_page`，没有被 page-role gate 误伤。
- `afc_0008 / afc_0010` 保持 `2`，没有因为入口页、门户页、泛页误抬。
- `afc_0008` 出现 `entry_follow`，并在补跑中看到 `entry_follow_succeeded`，但 point 仍停在 same-slot/口径不可比，不直接判错。
- `afc_0010` 至少一个 claim 出现 `evidence_page` 被消费为 `candidate_progress_from_kept_page`，但最终仍因不足以闭合主裁决而保持 `2`。
- `afc_0001` 仍主要卡在 raw/kept 与页保留层，未打通直接证据。

补跑 `afc_0008` 单题后，修正了一个诊断口径：`entry_follow_kept_evidence_pages` 只统计真正 `page_role=evidence_page` 的内链页，不再把保留下来的入口页算作 evidence page。

当前判断：

本轮达到了“防泛页误消费”和“至少有 entry-follow / evidence-page 消费痕迹”的首轮目标，但还没有完全打通 `afc_0001 / 0003` 的关键证据成功率。下一轮如果继续推进，重点不应回到泛 query，而应审计：

- 为什么 `raw_page_roles` 里出现 `evidence_page` 后没有稳定进入 kept；
- 为什么 entry-follow 有时能找到内页，但 point 仍停在 same-slot/口径不可比；
- 哪些 source 的 raw=0 仍由 anti-bot 或 budget cutoff 主导。
