整体可以按这条主线理解：

1. 全局配置
文件开头先定义：

标签 0/1/2
模型配置
检索配置
cache / checkpoint 配置
一些固定理由模板
这一层的作用就是把“运行环境”和“提交行为”统一起来。

2. 关键词字典
这部分是很多启发式规则的基础材料，比如：

时间词
数字词
绝对化词
路线词
预测词
它们不是直接判题，而是给后面的风险识别和边界修正提供信号。

3. 边界修正器
这一块是一组程序规则，用来修正常见摇摆。
典型用途是：

模型把细节错打成主错
模型把开放列举题打太严
模型把时间题、路线题、身份题的边界打歪
可以把它理解成：

“先让模型判”
“再用程序把已知高频误差拉回来”
4. 检索层
这里决定：

哪些题需要外部证据
是否调用 playwright_retrieval.py
检索拿多少条、要不要详情页
核心思想不是“所有题都联网”，而是只让高风险题联网取证。

5. Claim 抽取与上下文整理
这是你现在流程里很关键的一层。
这里会先把原始问答拆成：

claim_text
core_claim
modifiers
claim_scope
它的作用是避免模型直接把整段 answer 当黑盒来判，而是先问：

这句话真正声称了什么？
6. 风险启发式规则
这里会打 risk_flags，比如：

time_sensitive
numeric_sensitive
route_sensitive
multi_turn_context
forecast_sensitive
这些 flag 决定后面是否：

检索
recheck
走专项 audit
7. 定向审计
这是专门给不稳定题型准备的二次判断层。
现在主要有：

route audit
identity detail audit
open enumeration audit
overprecision audit
它们不是全量执行，只在特定机制风险下触发。

8. LLM 判定阶段
主流程是：

主 prompt 先判一次
必要时 recheck
再做 targeted audit
最后返回标签和 reason
这部分是“模型主导 + 程序收敛”的结合点。

9. 程序聚合
这一层很重要。
不是模型说什么就直接输出，而是程序会再看：

modifiers
targeted audit 结果
boundary fix
某些结构化字段
然后再决定最终 0/1/2。

10. classify 主流程
classify(item) 基本就是总调度器，顺序大概是：

stage1：问题画像
stage2：抽核心 claim
stage3：决定证据策略
stage4：拿证据
stage5：验证并聚合
这就是你整个 AFC pipeline 的骨架。

11. 持久化与批量执行
最后这部分负责：

读取输入
多线程跑题
写 checkpoint
中断续跑
输出 results.json
所以它解决的是工程问题，不是判题逻辑本身。

一句话总结你现在这版：

不是“一个 prompt 直接分类”，而是
先抽 claim -> 再打风险标签 -> 决定要不要检索/复核 -> 再让模型判 -> 最后由程序聚合收敛。