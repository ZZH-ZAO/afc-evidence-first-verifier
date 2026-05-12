# AFC v4 Phase4 CR5 补充：date-only 状态闭环修正

日期：2026-05-13

## 为什么补这一条

CR5 后做了一组本地合成校验，发现一个断层：

```text
evidence_event 已经识别 date-only 风险
但 decision_state 仍然把该 claim 当作 direct_refuted
```

这会导致状态机和证据事件层不一致。

## 修正内容

### 1. `evidence_event` 收紧 date-only guard

如果事件 predicate 已经是 `date/time/publish_time`，并且没有主体或对象绑定，就直接标记：

```text
date_without_subject_or_fact_binding
```

不再依赖复杂日期文本匹配。

### 2. `decision_state` 降级 date-only guarded refutation

如果 claim 原本被看成 `direct_refuted`，但 `phase_graph.date_only_guard_block_count > 0`，则改为：

```text
evidence_state = date_only_guarded_refutation
slot_state = date_only_guarded
decision_permission = insufficient_until_fact_binding
label_candidate = 2-无事实错误
```

## 基于什么架构

这一步补的是：

```text
evidence_event -> phase_graph -> decision_state -> decision_policy
```

四层状态必须一致。

## 实现什么

现在 date-only 假冲突不会在 event 层被发现后，又在 decision_state 层重新变成 direct_refuted。

## 解决什么

解决：

- 网页日期误伤位置/距离/当前状态 claim
- event 层和状态层不一致
- policy 层误以为已有 direct refutation

## 验证

已运行纯本地合成校验：

```text
date-only refuting point
-> evidence_event blocking_risks
-> phase_graph date_only_guard_block_count
-> decision_state date_only_guarded_refutation
-> decision_policy insufficient
```

通过。

