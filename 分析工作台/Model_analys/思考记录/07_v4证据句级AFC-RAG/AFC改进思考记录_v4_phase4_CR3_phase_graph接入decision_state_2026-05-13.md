# AFC v4 Phase4 CR3：phase_graph 接入 decision_state

日期：2026-05-13

关联前序：

- `AFC改进思考记录_v4_phase4_CR1_evidence_event与decision_state只读接入_2026-05-13.md`
- `AFC改进思考记录_v4_phase4_CR2_date_only_conflict_guard接入强反证闸门_2026-05-13.md`

## 本阶段目标

CR1 已经把证据句整理成 `evidence_event`，CR2 已经把 date-only 风险接到强反证前。  
CR3 的目标是让 `phase_graph` 真正参与裁决状态，而不是只在 debug 里展示。

重点是把阶段类 claim 识别得更稳定：

- `phase_start`
- `phase_end`
- `result_release`
- `current_status`
- `whole_event_end_or_result_release`

## 本阶段改动

### 1. `decision_state` 读取 `phase_graph`

`decision_state.py` 现在会把 `phase_graph.claim_role` 直接纳入：

- `slot_state`
- `risk_shape`
- `decision_permission`

### 2. 阶段边界不再只看词面

以前系统只能看到：

- 第一阶段
- 第二阶段
- 开始
- 结束
- 当前

现在它还能看到：

- 这个 claim 是不是阶段起点
- 是不是阶段终点
- 是不是结果发布
- 是不是当前状态
- 有没有 date-only 风险一起出现

### 3. `phase_boundary_conflict` / `phase_boundary_candidate`

CR3 新增了更清晰的 slot 状态：

```text
phase_boundary_conflict
phase_boundary_candidate
```

它们专门处理“阶段边界”类错位，不再让 `slot_mismatch` 一把梭。

### 4. `phase_graph:` 风险形态

`risk_shape` 里现在会出现：

```text
phase_graph:phase_start
phase_graph:phase_end
phase_graph:current_status
phase_graph:whole_event_end_or_result_release
```

这样后面的 `decision_policy` 可以更清楚地知道，当前不是普通数值/日期题，而是阶段边界题。

## 基于什么架构

仍然基于：

```text
evidence_event + phase_graph + decision_state
```

其中 `phase_graph` 是专门服务于阶段/日程/发布时间/结果发布类事实的子图。

## 实现什么

CR3 让阶段类事实变成可结构化判断，而不是靠词表或普通 slot mismatch 乱判。

## 解决什么

主要解决：

- “第二阶段开始”被误当成“普查结束”
- “结果发布日期”被误当成“当前状态”
- “阶段边界”与“当前事实”混槽
- 日期事实和阶段事实没有分层表达

## 风险控制

- 仍然不改最终标签。
- 仍然不改检索预算。
- 仍然不扩大 provider。
- 只是让 `decision_state` 对阶段类 claim 的描述更准确。

## 验证

已运行：

```text
D:\conda\python.exe -m py_compile decision_state.py evidence_event.py
```

通过。

## 下一阶段

CR4 应该开始让 `decision_state` 逐步接管更高层的解释输出：

1. `aggregate_by_confidence` 读取 `decision_state_debug`
2. `reason_builder` 优先使用 `decision_state.reason_basis`
3. `rubric fallback` 只在 `decision_permission` 允许时补位

