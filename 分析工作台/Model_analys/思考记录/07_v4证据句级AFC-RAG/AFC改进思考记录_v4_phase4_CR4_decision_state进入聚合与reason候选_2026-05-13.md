# AFC v4 Phase4 CR4：decision_state 进入聚合与 reason 候选

日期：2026-05-13

关联前序：

- `AFC改进思考记录_v4_phase4_CR1_evidence_event与decision_state只读接入_2026-05-13.md`
- `AFC改进思考记录_v4_phase4_CR2_date_only_conflict_guard接入强反证闸门_2026-05-13.md`
- `AFC改进思考记录_v4_phase4_CR3_phase_graph接入decision_state_2026-05-13.md`

## 本阶段目标

CR4 让 `decision_state` 从纯账本 debug 进入聚合与 reason 候选层。

注意：本阶段仍不让 `decision_state` 直接改 label。  
它只做两件事：

1. 在 `aggregate_by_confidence` 中落 `_decision_state_debug`。
2. 在 `choose_final_reason` 中提供一个受控的 `decision_state_reason` 候选。

## 本阶段改动

### 1. 聚合对象保留 `_decision_state_debug`

`aggregate_by_confidence` 现在会把 `evidence_summary.decision_state_debug` 写入 verify object。

这样后续分析每条样本时，可以直接看到：

- 每个 claim 的 scope
- evidence_state
- slot_state
- risk_shape
- decision_permission
- label_candidate
- reason_basis

### 2. 新增 `decision_state_reason_candidate`

新增函数：

```text
decision_state_reason_candidate
```

它只在没有直接 evidence reason 接管时提供 reason 候选。

策略：

- 如果 label 是 `2` 且状态是 insufficient，解释为什么不能把未闭合包装成事实错误。
- 如果 label 是 `0/1` 且状态允许 risk/rubric，解释这是补判风险，不是假装直接证据。

### 3. 不覆盖直接证据 reason

如果已经存在直接反证或原子反证，仍然优先使用 evidence reason / ledger reason。

## 基于什么架构

基于：

```text
decision_state -> decision_policy / reason_builder
```

CR4 先接 reason，不急着接 label。

## 实现什么

实现了从状态机到自然 reason 的第一步。

过去 reason 容易来自：

- aggregation 字符串
- semantic audit
- LLM verify
- review

现在多了一个更结构化的候选：

```text
decision_state.reason_basis
```

## 解决什么

主要解决：

- reason 写法和 label 作用域不一致。
- 证据不足时 reason 太笼统。
- 风险校准时 reason 容易看起来像直接证据反驳。

## 风险控制

- 不直接改 label。
- 不覆盖 evidence reason。
- 只有在直接证据 reason 不接管时，才把 decision_state reason 放到候选池。

## 验证

已运行：

```text
D:\conda\python.exe -m py_compile solve.py
```

通过。

## 下一阶段

CR5 应该开始做真正的 `decision_policy` 收口：

1. 把 evidence-first / atomic / risk / rubric / insufficient 的权限统一到一个状态入口。
2. 让 label 变更必须带 `decision_permission`。
3. 让 reason 和 label 都从同一份状态读取。

