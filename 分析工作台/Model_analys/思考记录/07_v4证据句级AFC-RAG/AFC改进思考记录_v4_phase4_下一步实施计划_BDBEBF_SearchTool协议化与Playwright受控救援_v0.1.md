# AFC v4 Phase4 下一步实施计划（BD/BE/BF：Search Tool 协议化 + Playwright 受控救援）

## 分类

证据链 / Workflow / 测试与回看

## 这次要做什么

这份文档不是再开一条新的总线，而是把前面已经形成的结论，往前收成一轮真正可实施的计划：

- 前面的文档已经说明，当前真实瓶颈不只是 recall，而是入口层经常让证据进不来、进来太慢，或者失败原因被黑盒化。
- 这份文档要解决的是：如何把现在已有的 query budget、source budget、preferred domains、source health、Playwright rescue 这些零散能力，收成一个更像主流 agent 的 **受控 Search Tool**。

这份文档直接承接下面几份文档：

- `AFC改进思考记录_v4_phase4_下一步计划_入口层修复与反爬绕行实施计划_v0.1.md`
- `AFC改进思考记录_v4_phase4_BABBBC实施补记_入口失败不覆盖已有进展_2026-05-10.md`
- `AFC改进思考记录_v4_phase4_入口层审计与外部检索架构对标_2026-05-11.md`

它和前面文档的关系要说清楚：

- 前面的入口层修复文档，重点是把“入口失败”看见并拆开。
- 外部架构对标文档，重点是说明主流 agent 为什么把 web search 当成受控工具。
- 这份文档，重点是把这两个结论收成一轮内部协议化实施计划。

一句话说，这一轮不是继续扩 recall，而是把“检索”收成一个真正受控、可解释、可补救的工具层。

## 基于什么架构

这一轮基于的是 **受控检索工具架构**，不是无限乱搜架构。

它更接近 OpenAI / Anthropic 这类主流 agent 的做法：

1. search 不是无限调用，而是有预算
2. search 不是黑盒乱试，而是有 source policy
3. search 失败不是一句 recall 不足，而是有明确 failure type
4. 浏览器能力不是全链路默认打开，而是在高价值场景下受控触发
5. 上层裁决器拿到的，不只是网页内容，还有这次 search 到底发生了什么

落到我们这里，就是把当前检索链收成四层：

1. **Search Request 层**
   - 这次 search 是为了哪个 claim、哪个 decision channel、哪个 query family
2. **Search Policy 层**
   - 这次允许搜多少次、搜哪些 source、允许几次 rescue、是否 authority-first
3. **Search Execution 层**
   - 这次实际跑了哪些 source、哪些被跳过、是否被 budget 截断、是否触发 Playwright
4. **Search Outcome 层**
   - 这次拿回了多少 raw、保住了多少 kept、authority entry 是否命中、失败属于哪一类

这个架构和我们已有的 candidate / point / closure 裁决链是上下游关系：

- 它不替代后面的裁决链
- 它负责把后面真正有机会使用的材料，更稳定地送进主链

## 实现了什么

这一轮不是新增对外 schema，也不是引入新的最终判标器，而是把当前已有能力协议化、职责化。

### BD：把现有检索收成统一 Search Tool 协议

固定把当前已有的零散能力，收成 4 组内部语义：

#### 1. Search Request

至少显式带上：

- `claim_id`
- `claim_family`
- `intended_decision_channel`
- `query_family_role`
- `preferred_domains`
- `query_goal`

这一步的作用不是多加字段，而是让后面每一次 source 调用都知道自己“为什么被发起”。

#### 2. Search Policy

固定统一消费现有控制点：

- `claim_query_limit`
- `claim_source_limit`
- `PLAYWRIGHT_MAX_QUERIES_PER_CLAIM`
- `preferred_domains`
- `source_strategy.search_channels`
- `source_health`

同时明确增加一层内部语义：

- 这是一次普通 search
- 这是一次 authority-first search
- 这是一次 rescue-eligible search

#### 3. Search Execution Trace

固定从现有诊断字段收口：

- `effective_source_plan`
- `provider_health_snapshot`
- `source_budget_cutoff`
- `playwright_rescue_trigger`
- `playwright_rescue_state`
- `official_discovery_block_reason`

目标不是多打印 debug，而是让上层能明确知道：

- 这次 search 到底试了什么
- 什么没试到
- 为什么没试到

#### 4. Search Outcome

固定收成面向上层消费的结果：

- `raw_results`
- `kept_web`
- `official_entry_hit`
- `access_path_state`
- `access_block_source`
- `rescue_attempt_state`

这样上层 reason 消费就不必再从很多局部信号里反推。

### BE：把 Playwright 固定成受控救援执行器

这一轮对 Playwright 的定位要收清楚：

- 它不是主检索器
- 它不是新的 provider
- 它不是裁决器
- 它是 **受控救援执行器**

固定只做三类事：

#### 1. SERP rescue

当满足下面条件时允许接手：

- 高优先 source 已跑过
- `raw_results == 0`
- 或命中 `anti_bot_blocked`

这时 Playwright 的职责是：

- 打开搜索结果页
- 取回结果链接
- 把结果重新送回正常的 kept/candidate/point 主链

#### 2. Detail rescue

当满足下面条件时允许接手：

- URL 已经拿到
- `requests` 被拦
- 或正文未成功读出
- 或页需要浏览器渲染后才能读到内容

这时 Playwright 的职责是：

- 打开页
- 拿正文或 HTML
- 返回给现有 evidence 消费链

#### 3. Authority entry opener

对这些 claim family：

- `date_fact`
- `schedule_fact`
- `route_fact`
- `event_result`

如果当前 query family 是：

- `closure`
- `distinguish`
- `refute`

则允许 Playwright 直接去打开高价值 authority 页，而不是再去泛搜更多搜索结果页。

这一轮固定不让 Playwright 做的事：

- 不直接输出标签
- 不替代 `point_conversion`
- 不长链路全程浏览网页
- 不作为默认主通道

### BF：把 authority-first 和 query family 真正联动起来

前面文档已经说明，当前问题不只是 source 少，而是 source 路径经常不对。

这一轮固定把 query family 和入口路径联动起来：

#### `date_fact / schedule_fact`

- `closure` 优先走 official calendar / exchange schedule / notice page
- `distinguish` 优先走能区分发布日期、生效日、交易日的 authority page

#### `route_fact`

- `closure / refute` 优先走 authority relation page / alternative path page

#### `event_result`

- `distinguish / refute` 优先走 official result page / event detail page

#### `numeric_count_detail`

- `closure / refute` 优先走 authoritative table / official record page

在 source 排序上，这一轮要继续压低关键入口对 `sogou_html` 的依赖，不让它承担 authority discovery 主职责。

## 解决了什么

这一轮主要解决的，不是“判得更激进”，而是三类更基础的问题。

### 1. 解决入口失败黑盒化

当前很多 case 不是没有证据，而是：

- 被反爬拦了
- 被 budget 截断了
- rescue 没接手
- authority entry 没真的前移

这一轮会把这些情况继续显式化，而不是统一回成 recall 不足。

### 2. 解决 Playwright 长期像旁路的状态

当前 Playwright 虽然存在，但经常只是代码里“有”。

这一轮要解决的是：

- 什么时候必须救
- 救什么
- 救完怎么回主链
- 救失败如何上报

也就是说，把 Playwright 从旁路 fallback 收成正式救援角色。

### 3. 解决 authority-first 只是概念，还没有真正落地

现在我们已经知道：

- `date/schedule/route/event_result` 很多题真正要的是 authority-shaped 页面
- 但系统实际仍很容易掉回搜索结果页依赖

这一轮要做的，就是把 authority-first 从“方向”变成“入口排序和触发协议”。

### 4. 它解决不了什么

这一点也要写清楚。

这轮做完以后，并不自动解决：

- 候选句不够 direct
- same-slot conversion 不稳定
- `date_role_mismatch`
- `result_granularity_mismatch`
- closure 仍未闭合

所以这套方案对我们来说是 **必要条件，不是充分条件**。

- 没有它，后面的裁决链经常吃不到材料
- 只有它，也不会自动把大量 `2` 直接抬成 `1/0`

## 具体场景

### 场景 1：`afc_0001`

这类题的真实问题，经常不是世界上没有 closure facts，而是：

- authority facts 本来不难找
- 入口层容易先挂在 SERP、反爬、budget 上
- 或者 authority 页没有真正前移

所以这轮对 `0001` 的价值，不是直接保它变 `1`，而是让它至少更真实地停在：

- access blocked
- rescue failed
- closure facts insufficient
- candidate / point unresolved

而不是回成黑盒 recall。

### 场景 2：`afc_0003`

这类 route uniqueness 题，本来就不适合只找泛相关页，而要找：

- alternative path
- route relation
- authority explanation

这轮的意义是让 `route_closure / route_refute` 更容易走到真正像样的入口页。

### 场景 3：`afc_0008 / afc_0010`

这两类题主要还是消费链后段问题，但入口层修好之后：

- 更容易拿到结果页、明细页、权威页
- 后面的 point conversion 才有更高概率在强材料上工作

### 场景 4：`sogou_html -> anti_bot_blocked:http_403`

这类 case 最能说明当前不是 recall，而是入口路径问题。

这轮要让系统后续能明确说：

- 是入口被拦
- 是否尝试过 rescue
- rescue 是否成功
- 是否其实有更好的 authority-first 路径没被前置

## 我应该怎么去使用

后面回看这轮是否有效，固定按这个顺序判断：

1. 先看是不是入口层失败，不要先说 recall 不够
2. 再看失败属于：
   - `anti_bot_blocked`
   - `provider_no_raw`
   - `source_budget_cutoff`
   - `playwright_skipped`
   - `playwright_failed`
   - `official_discovery_failed`
   - `access_blocked_but_rescuable`
   - `access_blocked_and_unresolved`
3. 如果入口层已经有进展，再继续看：
   - candidate 是否够强
   - same-slot 是否成立
   - point/closure 是否闭合

这一轮的验收不看“是不是立刻多很多 1”，而看：

- 入口失败是不是更真实
- authority-first 是不是真的前移
- Playwright 是不是真的接手了关键 case

## 对用户意味着什么

这轮做下去以后，对最终用户最直接的价值不是“标签立刻大涨”，而是：

1. 系统更少出现“网上明明有材料，但像什么都没看到”
2. 判不出来时，系统会更真实地说清楚是入口阻塞，还是后面没有完成点层转化
3. 对日期、赛程、结果、唯一性这种题，系统更像在真的查证，而不是只会搜相似句

## 对开发者意味着什么

这份文档对开发侧的定位很明确：

- 它不是新的总方向文档
- 它不是新的最终裁决框架文档
- 它是把入口层修复继续推进成“检索工具协议化”的实施计划

这一轮最重要的工程含义是：

1. 以后检索不再只是函数串联，而是更像一层受控工具协议
2. 以后 Playwright 不再只是备用分支，而是有明确职责和预算的救援执行器
3. 以后 authority-first 不再只是原则，而是 source 排序和 query family 联动策略

## 当前结论

这套方案对我们来说值得做，而且应该做，但要定位准确：

- 它是后面裁决链继续变强的必要条件
- 它不是单独就能把系统变成强 fact-checker 的充分条件

这一轮最值得推进的，不是再多搜一点，而是把：

- Search Tool 协议
- Playwright 受控救援
- authority-first 入口联动

这三件事真正落成内部稳定能力。

## 下一步建议

下一轮固定按 `BD -> BE -> BF` 推进：

1. **BD：Search Tool 协议化**
   - 先把 request / policy / execution trace / outcome 收成统一内部协议
2. **BE：Playwright 受控救援**
   - 再把 Playwright 从旁路 fallback 收成正式 rescue executor
3. **BF：authority-first 真联动**
   - 最后把 query family 和 authority entry 路径真正绑定起来

固定回看锚点：

- `afc_0001`
- `afc_0002`
- `afc_0003`
- `afc_0008`
- `afc_0010`

固定检查项：

- `access_path_state`
- `access_block_source`
- `source_budget_cutoff`
- `provider_health_snapshot`
- `effective_source_plan`
- `playwright_rescue_state`
- `playwright_rescue_trigger`
- `official_entry_hit`
- `query_family_role`
- `decision_useful_hit`
- `label_source_channel`

## 2026-05-11 首轮实现状态同步（Search Tool 协议化 + Playwright 受控救援）

### 基于什么架构

这一轮继续严格基于前面已经定下来的三层入口架构：

1. `受控 Search Tool`
2. `Playwright 受控救援执行器`
3. `authority-first 入口前移`

这次不是再补一个新框架，而是把前面文档里的方向真正落到主基线代码里。

### 实现了什么

这轮实际已经落到 `retrieval.py` 和 `solve.py`：

1. 在 `retrieval.py` 里把入口层收成了 4 组内部协议摘要：
   - `search_request`
   - `search_policy`
   - `search_execution_trace`
   - `search_outcome`

2. 让 `source_plan_for_query_goal(...)` 更明确地消费 authority-first：
   - `closure / distinguish / refute`
   - `verification_question` 下的 `date_fact / schedule_fact / route_fact / event_result / numeric_fact`
   这些 query role 会更明显地把 `domain_sitemap / bing_rss / bing_news / bing_html / duckduckgo_html` 前移；
   `sogou_html` 在 authority-first 路径里被继续压到更后面。

3. 让 Playwright 的职责变得更像受控救援，而不是旁路：
   - 细节页读取被拦时，显式记录 `detail_rescue`
   - query 级搜索在 `anti_bot_blocked` 或 `high_priority_sources_no_raw` 时，允许追加 `playwright_duckduckgo`
   - 同时留下 `playwright_rescue_trigger` 和 `playwright_roles`

4. 在 `solve.py` 里把这组协议继续往上接：
   - claim pipeline diagnostics 里直接保留 `search_request / search_policy / search_execution_trace / search_outcome`
   - 新增 `retrieval_effect_review`，把这轮最关心的效果面先收口成：
     - 有多少 claim 出现 `raw>0`
     - 有多少 claim 出现 `kept>0`
     - 有多少 claim 命中 `official_entry_hit`
     - 有多少 claim 落到 access/anti-bot 类阻塞
     - `retrieve` 和 `total_so_far` 的时间

### 解决了什么

这轮已经解决的，不是“标签一下子涨很多”，而是下面这些更底层的问题：

1. **入口失败不再完全黑盒**
   - 上层现在能更直接看到这是：
     - `official_discovery_failed`
     - `source_budget_cutoff`
     - `access_blocked_but_rescuable`
     - `access_blocked_and_unresolved`
   而不是继续一股脑掉回“没搜到”。

2. **Playwright 至少开始留下真实接手痕迹**
   - 现在不只是“代码里有 Playwright”；
   - 而是会在 diagnostics 里留下：
     - `playwright_rescue_state`
     - `playwright_rescue_trigger`
     - `playwright_roles`

3. **authority-first 已经开始真影响入口**
   - 不是只停在文档原则；
   - 而是开始影响 query role 对 source 的前移和 `sogou_html` 的降权。

### 这轮最小验证看到了什么

本轮用 5 个锚点做了最小验证：

- `afc_0001`
- `afc_0002`
- `afc_0003`
- `afc_0008`
- `afc_0010`

当前验证结果可以先记三点：

1. `afc_0002` 继续稳定为 `1`
   - 说明 closure/structured detail 这条线没有被入口层改动误伤。

2. `afc_0008 / afc_0010` 继续保持 `2`
   - 且仍主要停在 conversion / comparability / readiness 层，没有因为入口放松被误抬。

3. 入口层确实开始给出更真实的状态
   - `afc_0008 / afc_0010` 已经出现 `official_entry_hit = true`
   - `afc_0010` 已经出现显式 `playwright_rescue_failed + anti_bot_blocked`
   - `afc_0001` 已经能看到至少一条 `date_fact / closure` 相关 claim 进入 `raw>0 && kept>0`，不再是全黑盒 recall

### 还没解决什么

这轮没有解决的，也要明确写下来：

1. **Playwright 真实“救成”的比例还不高**
   - 现在更多是留下了“试过/失败/为什么失败”的痕迹；
   - 但还没有稳定把更多 `raw=0` case 拉回 `raw>0 && kept>0`。

2. **authority-first 命中还不够稳定**
   - 有些 claim 已经能命中 `official_entry_hit`
   - 但 `afc_0001 / afc_0003` 这类关键题仍经常卡在：
     - `official_discovery_failed`
     - `source_budget_cutoff`
     - `access_blocked_but_rescuable`

3. **时间还没有达到“明显更短”的停点**
   - 这轮 5 个样本的 `retrieve` 平均耗时约 `19.1s`
   - 总平均耗时约 `73.7s`
   - 说明“成功率真实性”开始变好，但“用时短”这一目标还没有完成

### 这说明当前卡在哪一层

按我们固定的思考链，这轮之后的主问题已经更清楚：

1. 不是先卡 candidate/point
2. 也不再只是模糊 recall
3. 现在主卡点更像是：
   - `入口进来了一部分，但 authority 命中还不稳`
   - `被反爬拦住后，Playwright 还不够常救成`
   - `有些 query 仍会被 source budget 提前截断`

### 这一层现有方案还能不能继续解

当前判断：**还能继续在现有方案内解一轮，不需要马上换大架构**。

原因是：

1. 现有协议已经能解释失败来自哪
2. 失败还主要落在：
   - source policy
   - source budget
   - authority-first 执行力度
   - rescue 成功率
3. 这说明还没有走到“现有架构完全解释不了”的阶段

### 跟前面文档的关系

这份文档现在的定位要明确：

1. `AFC改进思考记录_v4_phase4_入口层审计与外部检索架构对标_2026-05-11.md`
   - 负责回答：为什么我们要把入口层改成受控 Search Tool
   - 它是“审计 + 外部对标”文档

2. 本文档
   - 负责回答：基于那个架构，这一轮在主代码里到底落了什么、验证到了什么、还差什么
   - 它是“实施计划 + 首轮实现状态同步”文档

也就是说：
- 前一份文档更像“方向依据”
- 这份文档更像“施工与验收依据”

### 下一步建议

下一步不要跳去大改候选句层，先继续沿入口层把这三件事做实：

1. 继续压 `source_budget_cutoff`
   - 重点看为什么 `route / date / closure` 题还会被高价值 source 裁掉

2. 继续提高 `Playwright rescue` 的救成率
   - 不是只留下 failed 状态
   - 而是要尽量换成至少 1 个稳定 `playwright_rescue_succeeded`

3. 继续压 `retrieve` 长尾耗时
   - 先从高阻塞 source 的止损和 authority-first 提前命中做起
   - 让“成功率更真实”之后，再把“更快”收回来

## 2026-05-11 �����ܽ᣺Ϊʲô��һ�ֵ�ʱ����ͣ

### ����

֤���� / Workflow / ������ؿ�

### ���Ҫ��ʲô

�������� BDBEBF ����ʵ��֮�����ʵ���ۣ��ر���˵��Ϊʲô����������һ�֡����ܵ��ڡ���һ������ɡ������Ѻ�����С�޳��ԡ��ع��������˽���д�����

### ������ʲô

�������ķ��ղ��ǵ��� bug�����ǽ׶��жϴ��������Ѿ��� Search Tool Э�顢authority-first �� Playwright rescue �ĹǼܽ����ˣ����û�Ҫ���ͣ�㲻�ǡ��Ǽܽ��ϡ������ǣ�

1. ��ʵ�˲���Ч��
2. �����ɹ��ʸ���
3. ������ƽ����ʱ����

���������Ŀ��û��ͬʱ���㣬�Ͳ��ܰѽ׶�״̬д�ɡ�����ɡ������������жϻᱻ��ƫ��

### �����ǵ���Ŀ��ʲôʵ������

��β��ǵ�ʵ�����ã��ǰѡ�Э����չ���͡�Ч�����ꡱ��ȷ�𿪡����������һؿ���һ����ʷʱ����������Ϊ��ڲ������Ѿ������ֻʣ���������⡣

����������ʵ������һ������Ҫ�ı߽磺�Ժ����ٰѡ�������͵ø�����ˡ���д�ɡ������Ѿ�����ˡ���

### ���峡������ʲô

�������͵ĳ�����������

1. `afc_0001 / 0003 / 0010`
   - debug �Ѿ�����ǰ��ʵ�ܶ࣬��ʼ�ܿ��� authority-first��budget cutoff��access blocked��rescue failed
   - �����ղ�û���ȶ����ûؿɲþ���ҳ

2. ʱ��ָ��
   - ������֤ʱ `retrieve` ƽ��Լ 19.129 �룬��ƽ��Լ 73.74 ��
   - �ڶ�����֤ʱ `retrieve` ƽ��Լ 26.251 �룬��ƽ��Լ 78.869 ��
   - ˵����û��ʵ�֡����족����������

������������һ�ָ�������С�ޣ���ǿ�� authority-first �͸߼�ֵ source ������;��ɢ�������ܺ��һ���񻯣�

- `retrieve` ƽ��Լ 46.221 ��
- ��ƽ��Լ 93.203 ��

���� `afc_0001 / 0008` ���������˻����������ֳ����Ѿ����ˣ�û�б����ڵ�ǰ�����

### ��Ӧ����ôȥʹ��

��������ٻؿ� BDBEBF ��һ�֣�Ӧ�ð�������������ã�

1. ��ǰ���������ĳɹ����� Search Tool Э�黯�����ʧ����ʽ�ֲ㡢authority-first ǰ�ơ�Playwright rescue ���ܿؽ���Ǽ�
2. ��ǰû����ɵĲ��֣��ǡ��ɹ����������� + ��ʱ�����½���
3. ���������������Χ����ʵͣ���ƽ��������Ǽ���ͣ��Э���

### ���û���ζ��ʲô

���û���˵������ζ�ţ�

1. ���ֲ�����Ч��������ڲ�ȷʵ�Ѿ����ɽ���
2. ��Ҳ���ܰ����󵱳ɡ�Ч���Ѿ������ˡ�
3. ��ǰ���ʵ��״̬�ǣ�������ʵ�������ˣ��������ɹ��ʺ�ʱ�ӻ�û�ﵽ��ͣ��

### �Կ�������ζ��ʲô

�Կ�������˵����β�����ȷ�������£�

1. �Ժ�ÿ������жϣ������ȿ�Ч����ָ�꣬�ٿ�Э����Ƿ�Ư��
2. ���������ܴ󿪴�ϵؼ����� source ������ţ���Ҫ����С���ȵĵ����޸��� A/B ��֤�������ٰ�ʱ������

### ��ǰ����

��ǰ����״̬Ӧ���������壺

1. BDBEBF ����ʵ�ֻ���Ч�����ع�
2. ֮������Ϊ��ǿ�� authority-first/�߼�ֵ source �ļ������ԣ��Ѿ���֤Ϊ�ع鲢�ѻ���
3. ��ǰ�׶β���д�ɡ��ﵽͣ�㡱��ֻ��д�ɡ�Э�����ɣ�Ч����δ��꣬�����ƽ���

### ��һ������

��һ���������������ƽ������������·�ɢ��

1. ֻ��һ����ʵƿ����`source_plan -> budgeted_source_jobs -> ����ִ�� source` ֮������Ѹ߼�ֵ��ڴ�ɢ��
2. ÿ��ֻ��һ���㣬�̶��ؿ���
   - `afc_0001`
   - `afc_0003`
   - `afc_0010`
   - `retrieve`
   - `raw_positive_claims / kept_positive_claims / authority_hit_claims`
3. �����һ��������Ͳ���ʧ�ܣ��ٰ��ȶ�˼·�ص��ⲿ���ϼ�������äĿ�� recall
