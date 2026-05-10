## 2026-05-10 BA/BB/BC 实施补记：入口失败不覆盖已有进展

### 分类

证据链路 / Workflow / 测试与回看

### 这次补了什么？

在 `BA/BB/BC` 首轮实现完成后，又补了一刀很小但很关键的诊断口径收口：

- `official_discovery_failed` 不再在“其实已经有网页/候选句进展”的 case 里抢主导
- 只有 authority 入口确实没打通，且当前没有形成 `partial_progress_available` 时，才把 access state 落成 `official_discovery_failed`

### 动机是什么？

首轮入口层诊断已经把很多黑盒问题拆开了，但也暴露出一个新偏差：

- 有些 case 明明已经 `raw>0 / kept>0 / candidate>0`
- 只因为 `official discovery` 没成功，就会被描述成“官网发现失败主导”

这样会把我们后续的优化注意力带偏。本来下一步应该继续看：

- 弱候选句为什么没晋级
- point conversion 为什么没闭合
- closure 通道为什么还不稳定

结果会被一条过强的入口层 reason 盖掉。

### 对项目的实际作用

这次补记的价值不是直接抬标签，而是让入口层诊断更诚实：

1. 真没打通官网入口的，继续明说
2. 已经拿回部分材料的，不再假装还停在纯入口失败

这样后面我们回看 `afc_0001 / 0010` 这类 case 时，能更清楚地区分：

- 是入口真没打通
- 还是入口已经进来了，但消费链没有继续往前推

### 具体场景是什么？

典型场景是：

- authority discovery 没命中
- 但别的 source 已经拿回 raw，或者已经留下 candidate

这时系统更应该说“已有进展但还没形成可裁决 point”，而不是继续把锅全扔给 authority discovery。

### 我应该怎么使用？

之后回看 debug 时可以这样读：

- `official_discovery_failed`
  - 说明入口层真卡在 authority 发现
- `partial_progress_available`
  - 说明入口层已经不是主阻塞，后面应该转查 candidate / point / closure

### 对用户意味着什么？

你后面看 reason 会更贴近真实瓶颈，不会再频繁遇到“明明有材料了，系统还一直说没找到入口”的违和感。

### 对开发者意味着什么？

后面继续推进时，诊断层次会更稳定：

- 入口层问题归入口层
- 消费链问题归消费链

不容易再因为入口标签过强，把真正该优化的下一层问题看丢。

### 当前结论

`BA/BB/BC` 这一轮现在可以更明确地拆成两部分：

1. 第一部分解决了“入口失败能不能被看见”
2. 这一补刀解决了“入口失败会不会把已有进展误报成主阻塞”

### 下一步建议

下一轮不要再回到泛 recall 叙事，而是顺着这条口径继续往下推，重点看：

1. `partial_progress_available` 的 case，为什么还停在 weak candidate / point unresolved
2. `official_discovery_failed` 的 case，哪些是真的 authority-first 仍不够，哪些该交给 Playwright rescue
