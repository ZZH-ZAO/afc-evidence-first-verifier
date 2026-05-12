# AFC v4 Phase4 CR1：evidence_event 与 decision_state 只读接入

日期：2026-05-13

关联指导文档：

- `AFC当前瓶颈复盘与架构改进计划_基于近期提交与文档_2026-05-13.md`
- `AFC架构不足与修改计划_前后对比_2026-05-13.md`

## 本阶段目标

本阶段先不改最终标签，也不扩大检索。

目标是把当前“候选句、证据点、slot judge、phase/time 角色”整理成更统一的只读结构：

```text
candidate/page/point
-> evidence_event
-> phase_graph
-> decision_state_debug
```

这样后续再做 date-only guard、phase_graph 消费和 decision_policy 接管时，不需要继续从散乱字段里猜状态。

## 本阶段改动

### 1. 新增 `evidence_event.py`

职责：

- 从 supporting/refuting/uncertain points 和 reader candidates 中生成结构化 evidence event。
- 每个 event 固定包含：
  - `event_id`
  - `claim_id`
  - `source_sentence`
  - `subject`
  - `object`
  - `predicate`
  - `claim_value`
  - `evidence_value`
  - `time_scope`
  - `event_role`
  - `source_type`
  - `page_role`
  - `blocking_risks`

### 2. 初版 date-only guard

本阶段只做只读标记，不改裁决：

```text
date_without_subject_or_fact_binding
```

含义：

> 如果一个候选证据只是日期信号，但没有绑定主体、事实关系或指标，就不能直接当作事实反证。

这对应 `afc_0005` 暴露出的风险：网页日期、文章日期或导航日期不能单独反驳航母位置/距离。

### 3. 初版 `phase_graph`

本阶段只输出调试结构：

- `claim_role`
- `evidence_roles`
- `phase_graph_state`
- `date_only_guard_block_count`

它先帮助观察：

- claim 问的是 `phase_start` 还是 `phase_end`
- 证据句说的是 `result_release` 还是 `current_status`
- 是否存在 date-only 被 guard 拦截

### 4. 新增 `decision_state.py`

本阶段只生成 debug：

```text
scope
evidence_state
slot_state
risk_shape
decision_permission
label_candidate
reason_basis
```

它暂时不接管标签，只是把当前 claim 的裁决状态统一落出来。

### 5. 接入 `evidence.py`

`summarize_claim_evidence` 现在会额外返回：

- `evidence_events`
- `evidence_event_debug`
- `phase_graph`
- `decision_state_debug`

### 6. 接入 `solve.py` 证据账本

`build_evidence_ledger` 现在展示：

- `evidence_events`
- `evidence_event_debug`
- `phase_graph`
- `decision_state_debug`

## 基于什么架构

本阶段基于：

```text
Evidence Event + Decision State Architecture
```

不是把候选句直接喂给标签，而是先转成中间事件，再让状态机读取。

## 实现什么

实现了第一层可观测契约：

```text
证据句到底在说什么
它是什么角色
它是否只有日期信号
它能否进入同槽冲突
当前 claim 的裁决权限是什么
```

## 解决什么

解决当前最直接的结构问题：

- 只看最终 label 不知道证据消费卡在哪里。
- reader candidate 和 slot judge 缺少统一展示。
- date-only 假冲突无法在账本中显式看到。
- decision_state 之前只存在于多个函数的隐含判断里。

## 风险控制

- 不改最终 label。
- 不改检索预算。
- 不扩大 provider。
- date-only guard 只做 debug 标记，不直接影响裁决。
- decision_state 只读输出，不接管 `aggregate_by_confidence`。

## 下一阶段

CR2 应该做：

1. 用 `evidence_event_debug` 复核样本。
2. 将 date-only guard 从 debug 逐步接到冲突转换前。
3. 优先保护 `current_position_distance` 和 `phase_boundary_time` 两类风险槽。

