# 长顺农服 Dify 测试工具

针对长顺农服 Dify 应用的自动化测试工具，支持 Chatflow 和 Workflow 两种模式。提供交互式单例测试和批量评测两种运行方式，支持**多轮对话**测试、节点轨迹追踪、多 Sheet 分类评测、及突破 Excel 极根的超大节点跨列扩展功能。

## 核心特性

- **支持多轮对话**：通过 `conversation_id` 自动串联多轮请求。
- **动态交互式体验**：执行批量测试时可通过终端直接选择（单选/多选）想要执行的测试用例大类。
- **多 Sheet 结构输出**：自动按 `classified` 类目切分原始测试表并输出带有 `ALL` 及全量特定子类工作表的结果报告。
- **结果统计分析**：运行时智能捕获各项特征并在终端输出成功、失败、跳过、通过率的类目打宽表格统计。
- **大模型双路评测 (LLM Eval)**：可配置第三方模型引擎对接进行文本响应准确度及执行节点路径自动化校验打分。
- **Excel 容量智能扩展**：彻底解决节点回溯过多带来的超单个单元格物理极大限制 32,767，系统会自动在节点边界 (`\n\n`) 进行语义断句并将超大 JSON 延展输出至同行右侧的新增列中(`node_traces_2`, `node_traces_3`)。无损保留全量 Trace 日志。

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

从多 Sheet 数据结构中选读取特定分类，跑多轮并发后对全部细节写入新的同类目结果文件中（并在 `ALL` 列留痕）。

#### 交互式启动：

若不加分类参数，直接启动后会有交互式问询弹窗，列出所有发现的分类标签，输入序号以指引执行对应的子集分类：

```bash
python main.py --mode batch
```

#### 命令行自动启：

支持静默后台调度直接传参分类名称（或 `ALL`）：

```bash
python main.py --mode batch -c SHOPPING PLOT
# 启用 LLM 自动评估打分校对 (会先做探测)：
python main.py --mode batch --use-llm
```

评测完成后，结果保存在 `results/result_MMDDHHMMSS.xlsx`。分类结果报表也会直接在 Terminal 中打宽成表格打印。

## 测试数据格式

测试数据为 Excel 文件（`.xlsx`），需要且推荐包含 `classified` 用于数据分类规划。目前支持单 Sheet 或以 `ALL` / 类别分类构建的多 Sheet 结构，`input` 列推荐**使用 JSON 数组格式**，向后兼容单文普通 String。

### 多轮对话示例

| id | classified | input                                           | expect       | customer_id |
| -- | ---------- | ----------------------------------------------- | ------------ | ----------- |
| 1  | SHOPPING   | `["买两袋复合肥", "就选第1个吧", "确认下单"]` | 确认已下单。 | 201166...   |
| 2  | PLOT       | `["帮我看看地块情况"]`                        | CHAT         | 201166...   |

### 评测输出列及防截断机制

| 列名                   | 说明                                                                                                                                                         |
| ---------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `rounds`             | 该用例的对话轮次数                                                                                                                                           |
| `predict`            | 最后一轮 Dify 返回的实际回答                                                                                                                                 |
| `all_answers`        | 所有轮次回答的结构快照数组（若过大会向后续单元格防暴破推演）                                                                                                 |
| `node_traces`        | **防截断优化核心区域**。此列保留节点的 JSON 轨迹。`<br>`当字符逼近 32767 时，自动向右方挤出至 `node_traces_2`/`node_traces_3` 保存绝不断裂数据。 |
| `eval_expect_opt`    | LLM 评估结果：一致 / 基本一致 / 不一致（需 `--use-llm`）                                                                                                   |
| `eval_expect_reason` | LLM 评估详细理由记录                                                                                                                                         |

### 文件说明

- **`config.py`** — 读取所有的环境注入等参数解析、控制日志分离及输出。
- **`connect_dify.py`** — 构造基于 requests/SSE 为底座的基础轮询，处理对话/单轮模式逻辑。
- **`evaluate.py`** — 内嵌多表解析/生成、数据过长自适应分片降级写入机制的中心引擎。
- **`llm_client.py`** — OpenAI 和 Request双模式下提供给文本相似校验的连接驱动模块。

## 日志说明

系统通过控制台及文件实施分发式管理。
在控制台中往往以 `INFO` 提供执行时间线与成功进度回显、并以结构化展现分类。
而在 `logs/app_*XX.log` 等日志目录则全量收录以 `DEBUG` 抓取到的所有环节请求原信息，方便运维分析。
建议保持目前默认。若全看需切 `[LOG] CONSOLE_LEVEL = DEBUG`。
