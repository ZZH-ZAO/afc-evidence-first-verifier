# AFC v4 Phase4 CR5：decision_policy 收口与兜底权限统一

日期：2026-05-13

关联前序：

- `AFC改进思考记录_v4_phase4_CR1_evidence_event与decision_state只读接入_2026-05-13.md`
- `AFC改进思考记录_v4_phase4_CR2_date_only_conflict_guard接入强反证闸门_2026-05-13.md`
- `AFC改进思考记录_v4_phase4_CR3_phase_graph接入decision_state_2026-05-13.md`
- `AFC改进思考记录_v4_phase4_CR4_decision_state进入聚合与reason候选_2026-05-13.md`

## 本阶段目标

CR5 开始把“谁有权进入 fallback / 谁有权改标签”统一起来。

之前虽然已经有：

- evidence-first
- atomic refutation
- risk calibration
- rubric fallback

但这些权限仍然分散在不同函数里。  
CR5 把它们收口到一个读 `decision_state_debug` 的策略层：

```text
decision_state_debug
-> decision_policy_debug
-> fallback permission
-> aggregate / rubric gate
```

## 本阶段改动

### 1. 新增 `decision_policy.py`

它根据 `decision_state_debug` 生成：

- `policy_route`
- `allow_rubric_fallback`
- `dominant_scope`
- `dominant_reason_basis`
- `state_counts`
- `permission_counts`

### 2. 聚合层保留 `_decision_policy_debug`

`aggregate_by_confidence` 现在会保存这份策略调试信息。

### 3. 兜底权限统一

在进入 legacy preview / rubric fallback 之前，先看：

```text
decision_policy_debug.allow_rubric_fallback
```

如果状态机没有授权，就不再默认尝试 rubric fallback。

这一步的意义是：

> 证据不足且无风险授权时，直接回 2，不再让旧兜底先抢位。

## 基于什么架构

基于：

```text
decision_state -> decision_policy -> fallback gate
```

也就是：

- 状态先统一
- 策略再统一
- 最后才是具体 fallback 实现

## 实现什么

CR5 让系统开始具备“权限型裁决”：

- 不是所有分支都能兜底
- 不是所有证据不足都先试 rubric
- 不是所有强肯定都可以直接转成主需错误

## 解决什么

主要解决：

- fallback 触发条件不统一
- 证据不足时仍被旧兜底抢位
- 风险校准与 rubric fallback 之间边界不清
- “无证据”与“有风险但未闭合”混为一谈

## 风险控制

- 只读先验和策略收口优先，不直接扩大规则集。
- 仍然保留 direct evidence path。
- 兜底权限收口后，若样本没有风险授权，会更保守地回 2。

## 验证

已运行：

```text
D:\conda\python.exe -m py_compile decision_policy.py solve.py
```

通过。

## 下一阶段

CR6 应该开始做更细的输出收口：

1. `reason_builder` 优先从 `decision_state.reason_basis` 和 `decision_policy.policy_route` 生成自然 reason。
2. 清理一部分散在 `solve.py` 的 fallback reason 拼接。
3. 视回归情况决定是否继续拆 `claim_planner.py` / `retrieval_diagnostics.py`。

