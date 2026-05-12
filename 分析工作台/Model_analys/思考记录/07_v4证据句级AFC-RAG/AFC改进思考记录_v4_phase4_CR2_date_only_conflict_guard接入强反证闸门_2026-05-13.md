# AFC v4 Phase4 CR2：date-only conflict guard 接入强反证闸门

日期：2026-05-13

关联前序：

- `AFC改进思考记录_v4_phase4_CR1_evidence_event与decision_state只读接入_2026-05-13.md`
- `AFC当前瓶颈复盘与架构改进计划_基于近期提交与文档_2026-05-13.md`

## 本阶段目标

CR1 已经把 date-only 风险落到 `phase_graph.date_only_guard_block_count`。  
CR2 把这个 guard 接到强反证闸门前，避免非日期/日程类 claim 被“网页日期”或“孤立日期差异”误伤。

## 本阶段改动

### 1. 新增强反证保护函数

在 `solve.py` 中新增：

```text
direct_refutation_blocked_by_date_only_guard
```

它判断：

- 当前 claim 不是 `date_fact / schedule_fact`
- `phase_graph` 已经发现 date-only guard 风险
- 当前直接反证点全部都是 date/time 类型冲突

只有同时满足时，才阻止该反证进入 `claim_has_new_scheme_strong_refutation`。

### 2. 接入 `claim_has_new_scheme_strong_refutation`

在强反证判断里，如果 date-only guard 命中，直接返回 `False`。

这意味着：

> 日期本身不能单独反驳位置、距离、当前状态、赛事状态等非日期事实。

## 基于什么架构

基于 CR1 的：

```text
evidence_event -> phase_graph -> decision_state
```

本阶段开始让 `phase_graph` 的风险信号进入证据直裁前的安全闸门。

## 实现什么

实现了一个通用保护：

```text
非日期类 claim 的事实错误，不能只靠日期差异成立。
```

它不依赖具体样本 id，也不写死“林肯号”等实体。

## 解决什么

主要解决近期 CQ 文档暴露的问题：

> `afc_0005` 出现“网页头部日期被当作航母位置事实反证”的假阳性。

泛化场景：

- 当前距离/位置题
- 当前状态题
- 航班/比赛/政策状态题
- 页面发布日期与事实日期容易混淆的新闻题

## 风险控制

- 对 `date_fact / schedule_fact` 不启用该阻断，因为这些题本来就以日期为核心事实槽。
- 只有当直接反证点全部是 date/time 冲突时才阻断。
- 如果证据同时命中主体、事实关系、指标或状态，后续仍可通过其他反证通道进入裁决。

## 验证

已运行：

```text
D:\conda\python.exe -m py_compile solve.py
```

通过。

## 下一阶段

CR3 应继续补 `phase_graph` 的消费能力：

- 区分 `phase_start`
- 区分 `phase_end`
- 区分 `result_release`
- 区分 `current_status`
- 防止“第二阶段开始”被消费成“整体结束”

