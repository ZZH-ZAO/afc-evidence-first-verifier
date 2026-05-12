# AFC v4 Phase4 CR7：decision_policy_debug 写回 ledger

日期：2026-05-13

## 分类

证据链 / Workflow / 测试与回归

## 这次要做什么

把 `decision_policy_debug`、`decision_policy_route`、`decision_permission_gate` 稳定写回 `_evidence_ledger`。

这一步不改变标签，也不新增兜底逻辑，只增强最终 debug 和证据账本的可审计性。

## 动机是什么

CR5 已经让 fallback 是否允许由 `decision_policy` 统一控制，CR6 又让 reason 可以读取 `decision_state / decision_policy`。

但如果最终 ledger 里看不到 policy 的路由结果，复盘样本时仍然要在 `verify_obj` 的内部 `_decision_policy_debug` 字段里翻，链路不够清楚。

## 基于什么架构

继续基于：

```text
evidence_event
-> phase_graph
-> decision_state
-> decision_policy
-> evidence_ledger / reason_builder
```

`decision_policy` 是“是否允许兜底”的统一授权层，ledger 应该记录这个授权结果。

## 实现什么

在 `build_evidence_ledger(...)` 的默认 ledger 结构里新增：

```text
decision_policy_debug
decision_policy_route
decision_permission_gate
```

在最终 reason 写回 ledger 时，把 `verify_obj._decision_policy_debug` 同步回 `_evidence_ledger`。

## 解决什么问题

解决：

- 最终 reason 已经用了 policy，但 ledger 看不到 policy 的来源。
- 回归时难以区分 `fallback_allowed` 与 `fallback_blocked`。
- 样本判 2 时，难以判断是“纯证据不足”还是“date-only guard / policy 拒绝兜底”。

## 对用户意味着什么

用户看 debug 时可以直接从 evidence ledger 里看到：

```text
证据状态是什么
policy 走哪条 route
兜底有没有被允许
最终 reason 为什么这么写
```

## 对开发者意味着什么

后续分析一条样本不再需要跨多个内部字段拼状态。

这也让之后做回归统计更容易，比如统计：

- `policy_route=evidence_decide`
- `policy_route=risk_calibrate`
- `policy_route=insufficient`
- `decision_permission_gate=fallback_blocked`

## 风险控制

- 只写 debug，不改判题。
- 不新增样本级条件。
- 不改变 `decision_policy` 的授权结果。

## 验证

已计划运行：

```text
D:\conda\python.exe -m py_compile solve.py reason_builder.py decision_policy.py decision_state.py evidence_event.py evidence.py
```

通过后提交。

## 当前结论

CR7 让 CR5/CR6 的状态更容易被人看见。

它本身不提升召回，也不提高正确率，但会提高下一轮定位瓶颈的速度。

## 下一步建议

下一阶段可以开始做受控回归统计：

1. 统计每个样本的 `policy_route`。
2. 统计 reason 来源是否来自 `decision_state_reason`。
3. 找出仍然落到 `insufficient` 但标准答案需要 0/1 的样本，再判断是检索问题、事件转换问题，还是风险授权问题。
