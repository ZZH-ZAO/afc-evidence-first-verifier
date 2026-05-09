---
name: afc-factcheck-zhangzihao
description: >
  使用当前提交目录中的 solve_submit.py 执行 AFC 标准提交流程。标准输入为 data.json，
  标准输出为 output/results.json。适用于直接运行提交版脚本、检查输出是否生成且条数匹配。
  不适用于绕过 solve_submit.py / solve.py 手工判题、修改标签或切换到其他目录执行。
---

# AFC 事实核查 Skill

## 目标

在当前提交目录内按标准流程执行：

```text
data.json -> python solve_submit.py --workers 4 -> output/results.json
```

成功标准：

- `output/results.json` 生成成功
- 输出是合法 JSON 数组
- 输出条数与 `data.json` 输入条数一致
- 每条结果至少包含 `id`、`label`，可保留脚本生成的 `reason`
- 不手工修改 `output/results.json`

## 强约束

1. 只在当前提交目录执行，不切换到其他目录。
2. 不绕过 `solve_submit.py` / `solve.py` 手工生成标签。
3. 不手工改写 `output/results.json`。
4. 不把 debug、report、eval 文件当作正式输出。
5. 若旧输出存在，重跑时优先使用脚本断点续跑，不人工编辑旧输出。

## 当前正式链路

- `solve_submit.py`：提交版主入口，默认提交运行优先使用它。
- `solve.py`：开发主入口，用于调试、分析和非提交态验证。
- `retrieval.py`：检索模块，负责网页搜索、详情页读取、候选证据句抽取、缓存和必要兜底。
- `search_providers.py`：检索源 provider 层，负责封装免费搜索源、回退源和后续可扩展接口。
- `evidence.py`：证据模块，负责 claim 级证据摘要、支持点、反驳点、不确定点和覆盖度整理。
- `afc_schema.py`：全局 schema / enum 协议层，影响 evidence mode、directness、coverage 等通用字段。
- `afc_route_markers.py`：route 共享 marker 层，影响 route 类 query、候选句抽取和诊断。
- `output/results.json`：正式输出文件。

## 标准执行命令

优先使用：

```bash
python solve_submit.py --workers 4
```

如需显式指定输入输出：

```bash
python solve_submit.py --input data.json --output output/results.json --workers 4
```

如需强制全量重跑，不复用旧结果：

```bash
python solve_submit.py --workers 4 --no-resume
```

开发态调试可使用：

```bash
python solve.py --input data.json --output output/results.json --workers 4
```

## 执行步骤

1. 进入当前提交目录。
2. 确认关键文件存在：

```bash
dir data.json solve_submit.py solve.py retrieval.py evidence.py search_providers.py afc_schema.py afc_route_markers.py
```

3. 确认环境变量或 `.env` 已配置模型 Key。
4. 首次运行前安装依赖：

```bash
pip install openai requests python-dotenv playwright
```

5. 若没有可用 Chrome，再执行：

```bash
python -m playwright install chromium
```

6. 正式运行：

```bash
python solve_submit.py --input data.json --output output/results.json --workers 4
```

7. 若中断或失败，优先重跑同一命令，不手工修改结果文件。
8. 运行结束后检查输出：

```bash
python -c "import json; a=json.load(open('data.json',encoding='utf-8')); b=json.load(open('output/results.json',encoding='utf-8')); print(len(a), len(b)); assert len(a)==len(b)"
```

## 并行、重试与断点

- 默认并发为 `4`，属于保守并行。
- `solve_submit.py` 会持续刷新 `output/results.json`，避免中断后全部重跑。
- 默认允许断点续跑；若已有合法输出，重跑时会跳过已完成样本。
- LLM 调用只做有限重试，不做无限重试。
- 若评测环境明显限流，可临时下调到 `--workers 2`，优先保证稳定完成。

## 环境变量

模型与接口可通过环境变量或 `.env` 配置：

```env
LLM_API_KEY=your_api_key
API_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4.1
V2_WORKERS=4
V2_RESUME_OUTPUT=1
LLM_RETRIES=1
LLM_TIMEOUT=45
V2_RETRIEVAL_TIMEOUT=3
```

不要在命令输出、日志、截图或提交文件中暴露真实 API Key。

## 执行后检查

1. `output/results.json` 是否存在。
2. 是否能正常解析为 JSON。
3. 输出条数是否与输入条数一致。
4. 每条是否包含 `id`、`label`。
5. `label` 是否属于合法三分类标签。

## 失败处理

若执行失败，按顺序处理：

1. 确认当前目录存在 `data.json`、`solve_submit.py`、`solve.py`、`retrieval.py`、`evidence.py`、`search_providers.py`、`afc_schema.py`、`afc_route_markers.py`。
2. 确认模型环境变量和依赖可用。
3. 若属于瞬时错误，如连接超时、网关异常或外部检索临时失败，按原命令有限重试 `1-2` 次。
4. 若中途终止，直接重跑原命令，优先复用已有合法结果继续跑。
5. 若连续失败，再报告失败步骤、报错摘要、缺失依赖或环境问题。

不要擅自改题、补标签、绕过脚本，也不要切换到其他目录寻找替代实现。
