# 长顺农服 Dify 测试工具

针对长顺农服 Dify 应用的自动化测试工具，支持 Chatflow 和 Workflow 两种模式。包含单例测试和批量评测功能，支持多轮对话测试、多 Sheet 格式的数据文件，并提供处理超长节点日志的跨列扩展功能。

## 核心特性

- **多轮对话测试**：基于 `conversation_id` 自动串联上下文，还原真实场景。
- **交互式选择**：执行批量测试时，可在终端直接选择想要执行的测试数据所属分类。
- **多 Sheet 报告输出**：根据数据表内 `classified` 字段自动切分测试结果至对应的 Sheet 中，并生成一份汇总的 `ALL` Sheet。
- **自动化统计结果**：评测结束后在命令行打印整体的成功数、失败数、跳过数及分类通过率。
- **第三方大模型评测辅助**：配置第三方 LLM API 后，可自动对 Dify 实际输出回复或执行节点与测试集期望值进行对比打分。
- **Excel 列防截断**：解决 Excel 单个单元格最大 32,767 字符的渲染限制。超过该限制长度的节点日志（如节点 Trace），会在输出报告时拆分写入旁侧的 `node_traces_2`, `node_traces_3` 等新列中。

## 目录结构

```
changshun_dify_test/
├── main.py                          # 入口文件，调度单例测试和批量评测
├── config/
│   ├── conf.ini                     # 配置文件（含 API Key，不提交到仓库）
│   ├── conf copy.ini                # 配置文件模板（用于新环境初始化）
│   ├── config.py                    # 配置读取，统一管理所有配置项和日志初始化
│   ├── connect_dify.py              # Dify API 连接器，Chatflow/Workflow 测试器实现
│   └── llm_client.py                # LLM 评估客户端（OpenAI SDK / requests）支持连通性快速校验
├── evaluate/
│   ├── evaluate.py                  # 批量评测核心逻辑：多轮解析、LLM对齐打分、按 sheet 提取生成/防截断导出
│   └── single_test.py               # 交互式单例测试，支持多轮对话和节点追踪预览
├── data/
│   └── chatflow_multi_turn_test_data.xlsx  # 包含多 Sheet 支持与 classified 字段格式测试数据
├── results/                         # 评测结果多表输出目录（带时间戳）
├── logs/                            # 各级别日志输出目录
├── tests/                           # 各类调试及单向性单元集测试脚本
└── scripts/                         # 系统辅助脚本
```

## 环境准备

### 依赖安装

```bash
pip install requests pandas openpyxl openai
```

### 配置文件

复制模板并填入实际的 API Key 和接口地址：

```bash
cp config/conf\ copy.ini config/conf.ini
```

编辑 `config/conf.ini`：

```ini
[LOG]
CONSOLE_LEVEL = INFO        # 控制台日志级别，可选 DEBUG/INFO/WARNING
FILE_LEVEL = DEBUG          # 文件日志级别，DEBUG 会记录每个节点的完整 JSON 输出
TARGET = both               # 日志输出目标：console / file / both
FILE_PATH = logs/app.log    # 日志文件路径模板，实际文件名会追加时间戳

[EVALUATE]
TEST_FILE_PATH = data/chatflow_multi_turn_test_data.xlsx  # 测试数据文件路径
RESULT_DIR = results                                      # 结果输出目录
MAX_WORKERS = 1             # 并行线程数（多轮对话建议设为 1 以确保顺序追踪）

[DIFY]
API_KEY = app-xxxxxxxxxxxxxxxxxxxxxxxx    # Dify 应用 API Key
BASE_URL = https://api.dify.ai/v1         # Dify API 地址
APP_TYPE = chatflow                       # 应用类型：chatflow 或 workflow

[EVAL_LLM]
CLIENT_METHOD = openai       # LLM 调用方式：openai 或 requests
API_KEY = sk-xxx             # 评估用 LLM 的 API Key
BASE_URL = http://xxx/v1/    # 评估用 LLM 的 API 地址
MODEL_NAME = qwen3-14b       # 模型名称
MAX_TOKEN = 20480
TEMPERATURE = 0
```

> 路径支持相对路径和绝对路径。相对路径基于项目根目录解析。

## 使用方法

### 单例测试（交互式）

启动后进入交互模式，输入提示词即可查看完整的节点执行轨迹和最终回答。Chatflow 模式下支持多轮对话串联。

```bash
python main.py
# 或
python main.py --mode single
```

输入 `quit`、`q` 或 `exit` 退出。

### 批量评测

从已配置的测试数据表格中读取用例数据，并发执行。完成后将各分类结果按 Sheet 格式写入输出目录下的新 Excel 文件中。

#### 交互式启动：

若直接启动时不传递类别参数，程序会在终端列出所有发现的分类供用户输入序号进行选择：

```bash
python main.py --mode batch
```

#### 命令行自动启：

支持在命令行直接传入要测试的分类名称（或输入 `ALL` 测试全部数据）：

```bash
python main.py --mode batch -c SHOPPING PLOT
# 若需启用大模型对比校验打分：
python main.py --mode batch --use-llm
```

评测完成后，结果默认保存在 `results/result_MMDDHHMMSS.xlsx` 文件中，同时终端会输出各分类相关的统计信息与整体通过率。

## 测试数据格式

测试数据应使用 Excel 文件（`.xlsx`），建议使用 `classified` 列对数据进行规划分类，以支持拆分输出多 Sheet 结构。
多轮对话测试用例需要 `input` 列为 **JSON 数组格式**，普通单轮文本用例向后兼容纯文本字符串格式。

### 多轮对话示例

| id | classified | input                                           | expect       | customer_id |
| -- | ---------- | ----------------------------------------------- | ------------ | ----------- |
| 1  | SHOPPING   | `["买两袋复合肥", "就选第1个吧", "确认下单"]` | 确认已下单。 | 201166...   |
| 2  | PLOT       | `["帮我看看地块情况"]`                        | CHAT         | 201166...   |

### 评测输出结果列名说明

在**不使用 LLM 评测**（默认带模式运行的 `main.py --mode batch`）时，生成的结果文件名为 `result_YYYYMMDDHHMMSS.xlsx`。此时，系统除了保留输入表格中自带的所有列外，会向右补充输出以下内容：

| 列名                   | 说明                                                                                                                                                         |
| ---------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `rounds`             | 该测试请求发生的实际对话轮次数                                                                                                                               |
| `predict`            | 最后一轮 Dify 返回的文本回复结果                                                                                                                             |
| `all_answers`        | 所有轮次的回复内容集合 JSON 数组（遇到单单元格过长时，会自动向后续相邻列扩展）                                                                               |
| `simplify_node_traces`| 节点流转的简化轨迹图（例如 `[Start] -> [LLM] -> [End]`），仅保留节点名称记录。                                                                               |
| `node_traces`        | 包含运行中各节点原始详情输出的完整 JSON 日志。`<br>`为了避免被 Excel 的 32,767 字数限制截断，当排版超长时内容会被自动推拉切割，写入紧随其后的 `node_traces_2`/3 等新列中。|

<br>

在**开启 LLM 评测**（包含 `--use-llm`）时，系统会在记录完实际跑出结果之后，调用外部配置的大模型与测试用例设定好的 `expect` 及 `gold_node_traces` 期望预留值进行交叉比对与打分。输出的新文件则带有 `compare_` 前缀。此时会额外再往右补充以下列：

| 列名                   | 说明                                                                                                                                                         |
| ---------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `eval_expect_opt`    | 文本预期结果的大模型判定结论（基于 `expect` 列对比 `predict` 列得出）：一致 / 基本一致 / 不一致                                                              |
| `eval_expect_reason` | 大模型评估当前文本回复预期的详细解析过程与理由                                                                                                               |
| `eval_trace_opt`     | 执行轨迹路线的大模型判定结论（基于 `gold_node_traces` 对比 `simplify_node_traces` 简化路线图得出）：一致 / 基本一致 / 不一致                                 |
| `eval_trace_reason`  | 大模型评判此处流程执行路线合规性的详细思考过程和理由                                                                                                         |

### 文件说明

- **`config.py`** — 配置读取逻辑与基础日志行为的初始化。
- **`connect_dify.py`** — 处理目标 Dify 服务的直接请求调用以及流式（SSE）结果解析回包。
- **`evaluate.py`** — 包含运行读取、循环调度、统计日志采集与结果表的防截断拆列写入重组。
- **`llm_client.py`** — 对接第三方 OpenAI 标准模型与 API 响应，作为文本与流程验证测试使用的中间工具。

## 日志说明

系统提供配置项，支持将日志分别定向到终端控制台与生成的本地日记文件中：
- 默认设置下，终端主要以 `INFO` 级别即时输出流程节点跳动与表格类统计概要，反馈直观执行情况。
- 如果需要细查如原始网络报文级别的调试信息，可以查阅 `logs/` 目录中的日志文件，该内录留了底层节点的冗长 `DEBUG` 日志。
可在 `config.ini` 中的 `[LOG]` 中分别调节相关开关项级别进行个性定制。
