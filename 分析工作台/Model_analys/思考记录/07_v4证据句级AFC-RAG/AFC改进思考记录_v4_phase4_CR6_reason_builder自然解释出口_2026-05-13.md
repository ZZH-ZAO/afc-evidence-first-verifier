# AFC v4 Phase4 CR6：reason_builder 自然解释出口

日期：2026-05-13

## 分类

证据链 / Workflow / 报告

## 这次要做什么

在现有 `decision_state -> decision_policy` 之后补一个轻量 `reason_builder.py`。

它只做一件事：把已经形成的裁决状态翻译成自然、可读、可审计的中文 reason 候选，不新增标签判断权。

## 动机是什么

CR1-CR5 已经把证据事件、阶段角色、date-only guard、裁决状态和兜底权限串起来了，但最终 reason 仍然可能出现两类问题：

1. 输出 `direct_refuted / risk_calibrate / date_only_guarded` 这类工程状态词，读起来不像判题解释。
2. 标签已经由 policy 收口，但 reason 仍可能从旧 LLM 或旧 fallback 文本里来，导致“标签口径”和“解释口径”不一致。

所以 CR6 的重点不是继续改标签，而是让解释层真正吃 `decision_state` 和 `decision_policy`。

## 基于什么架构

基于前一阶段形成的主链：

```text
candidate/page/point
-> evidence_event
-> phase_graph
-> decision_state
-> decision_policy
-> reason_builder
```

其中 `reason_builder` 是出口层，不是裁决层。

## 实现什么

新增 `reason_builder.py`：

- 消费 `decision_state_debug.claim_state_rows`
- 消费 `decision_policy_debug.policy_route`
- 将 scope、permission、risk_shape、slot_state 翻译成自然中文
- 对 `date_only_guarded_refutation` 输出“缺少主体、事实关系、时间槽绑定，不能作为同槽反证”
- 对 `risk_calibrate / rubric_fallback` 输出“这是风险校准或受控兜底，不是直接证据反驳”

同时在 `solve.py` 的 `decision_state_reason_candidate(...)` 中优先调用该模块。

## 解决什么问题

解决：

- reason 工程化
- reason 和 label 口径不一致
- date-only guard 虽然拦住了标签，但最终解释仍说不清为什么拦住
- 风险校准和证据直裁混写

## 具体场景

当一个页面只提供发布日期，而没有绑定到具体主体和事实关系时，系统现在可以说：

```text
已有线索主要是日期或页面时间差异，但还没有同时绑定同一主体、事实关系和时间槽。
该线索不能作为同槽反证。
```

而不是输出：

```text
date_only_guarded_refutation / insufficient_until_fact_binding
```

## 对用户意味着什么

用户看到的 reason 会更像一个判题解释，而不是 debug 字段拼接。

尤其是证据不足、受控兜底、风险校准三类情况，会明确说明“为什么没有直接反证仍然可能补判”或“为什么不能补判”。

## 对开发者意味着什么

后续改 reason 时，可以优先改 `reason_builder.py`，而不是继续在 `solve.py` 里散落拼字符串。

这也为后续瘦身 `solve.py` 打基础。

## 风险控制

- 不引入新的标签决策。
- 不按样本 id 写特例。
- 不把 risk_shape 直接升级成标签。
- 仍经过 `llm_reason_is_safe(...)` 和 final reason conflict guard。

## 验证

已运行：

```text
D:\conda\python.exe -m py_compile reason_builder.py solve.py decision_state.py decision_policy.py evidence_event.py evidence.py
```

通过。

并做了纯本地合成校验：

```text
date_only_guarded_refutation -> 自然解释为“缺少事实绑定，不能作为同槽反证”
risk_calibrate + phase_boundary_time -> 自然解释为“风险校准，不是直接证据反驳”
```

## 当前结论

CR6 把“裁决状态已经算出来，但最终 reason 仍旧散落”的问题收了一层。

它不会提升检索召回本身，但会提升输出可读性、口径一致性，以及后续 debug 的可维护性。

## 下一步建议

下一阶段继续沿着指导文档推进：

1. 进一步把散在 `solve.py` 的 fallback reason 拼接收口到 `reason_builder.py`。
2. 将 `decision_policy_debug` 更稳定地写入 ledger/debug，方便每个样本审计“为什么允许或拒绝兜底”。
3. 再观察是否需要抽 `claim_planner.py` 或 `retrieval_diagnostics.py`，但不要在证据状态尚未稳定时做大拆分。
