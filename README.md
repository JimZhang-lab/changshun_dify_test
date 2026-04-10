# 长顺农服 Dify 测试工具

针对长顺农服 Dify 应用的自动化测试工具，支持 Chatflow 和 Workflow 两种模式。提供交互式单例测试和批量评测两种运行方式，支持**多轮对话**测试和节点轨迹追踪。

## 目录结构

```
changshun_dify_test/
├── main.py                          # 入口文件，调度单例测试和批量评测
├── config/
│   ├── __init__.py
│   ├── conf.ini                     # 配置文件（含 API Key，不提交到仓库）
│   ├── conf copy.ini                # 配置文件模板（用于新环境初始化）
│   ├── config.py                    # 配置读取，统一管理所有配置项和日志初始化
│   ├── connect_dify.py              # Dify API 连接器，Chatflow/Workflow 测试器实现
│   └── llm_client.py                # LLM 评估客户端（OpenAI SDK / requests）
├── evaluate/
│   ├── __init__.py
│   ├── evaluate.py                  # 批量评测逻辑，支持多轮对话和 LLM 自动评估
│   └── single_test.py               # 交互式单例测试，支持多轮对话和节点追踪
├── data/
│   ├── chatflow_test_data.xlsx      # 测试数据（单轮格式，旧版）
│   └── chatflow_multi_turn_test_data.xlsx  # 测试数据（多轮对话格式）
├── results/                         # 评测结果输出目录（自动创建）
├── logs/                            # 日志输出目录（自动创建）
├── tests/
│   ├── test_multi_turn.py           # 多轮对话功能测试
│   └── ...                          # 其他测试脚本
├── scripts/
│   └── start_evaluate.sh            # 批量评测启动脚本
├── .gitignore
├── LICENSE
└── README.md
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
CONSOLE_LEVEL = INFO       # 控制台日志级别，可选 DEBUG/INFO/WARNING
FILE_LEVEL = DEBUG          # 文件日志级别，DEBUG 会记录每个节点的完整 JSON 输出
TARGET = both               # 日志输出目标：console / file / both
FILE_PATH = logs/app.log    # 日志文件路径模板，实际文件名会追加时间戳

[EVALUATE]
TEST_FILE_PATH = data/chatflow_multi_turn_test_data.xlsx  # 测试数据文件路径
RESULT_DIR = results                                       # 结果输出目录
MAX_WORKERS = 1              # 并行线程数（多轮对话建议设为 1）

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

启动后进入交互模式，输入提示词即可查看完整的节点执行轨迹和最终回答。Chatflow 模式下支持多轮对话。

```bash
python main.py
# 或
python main.py --mode single
```

运行示例：

```
  请输入提示词: 买三包化肥
  customer_id (回车跳过): 11111

  节点轨迹 (14 个节点):
    [1/14] 用户输入
      { "sys.query": "买三包化肥", ... }
    [2/14] 路由判断
      { "text": { "intent": "SHOPPING", "confidence": 99 } }
    ...

  回答:
  我找到这些商品，您可以回复'第几个商品'继续查看：
  1. 赤天化尿素（95元/袋，库存212）
  ...

  会话 ID: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
  (后续输入在此会话中继续)
```

输入 `quit`、`q` 或 `exit` 退出。

### 批量评测

从 Excel 文件读取测试用例，支持多轮对话，将预测结果和节点轨迹写入结果文件。

```bash
python main.py --mode batch
# 启用 LLM 自动评估
python main.py --mode batch --use-llm
```

评测完成后，结果保存在 `results/result_MMDDHHMMSS.xlsx`。

## 测试数据格式

测试数据为 Excel 文件（`.xlsx`），`input` 列**统一使用 JSON 数组格式**：

### 多轮对话示例

每个测试用例的 `input` 列为 JSON 数组，每个元素代表一轮用户输入：

| id | input | expect | customer_id |
|----|-------|--------|-------------|
| 1 | `["买两袋复合肥", "就选第1个吧", "数量改成5包", "确认下单"]` | SHOPPING | 2011662594422755329 |
| 2 | `["看看肥料都有哪些分类", "第一个分类"]` | SHOPPING | 2011662594422755329 |
| 3 | `["你好"]` | CHAT | 2011662594422755329 |

### 列说明

| 列名 | 必填 | 说明 |
|------|------|------|
| `id` | 是 | 测试用例编号 |
| `input` | 是 | JSON 数组格式的用户输入，每个元素代表一轮对话 |
| `expect` | 否 | 期望结果（对应最后一轮的回答，类别标签或语义描述） |
| `gold_node_traces` | 否 | 期望的节点执行路径（对应最后一轮） |
| `customer_id` | 否 | Chatflow 模式下的客户 ID |

### 评测输出列

批量评测后，结果 Excel 中会追加以下列：

| 列名 | 说明 |
|------|------|
| `rounds` | 该用例的对话轮次数 |
| `predict` | 最后一轮 Dify 返回的实际回答 |
| `all_answers` | 所有轮次回答的 JSON 数组（用于排查中间轮次问题） |
| `node_traces` | 所有轮次的节点执行轨迹（每轮带分隔标记） |
| `eval_expect_opt` | LLM 评估结果：一致 / 基本一致 / 不一致（需 `--use-llm`） |
| `eval_expect_reason` | LLM 评估理由（需 `--use-llm`） |

### 多轮对话执行机制

- Chatflow 模式下，同一测试用例的多轮输入**串行执行**，自动传递 `conversation_id` 保持对话上下文
- `inputs`（如 `customer_id`）在**每一轮**请求中都会传入（Dify 要求）
- 不同测试用例之间可**并行**执行（通过 `MAX_WORKERS` 配置线程数）
- Workflow 模式**不支持多轮**，仅取数组中第一个元素执行

## 文件说明

### config/config.py

统一配置管理。从 `conf.ini` 读取所有配置项并封装为 `Config` 类的实例 `cfg`。负责路径解析（相对路径转绝对路径）、目录自动创建、日志初始化。

导出：
- `cfg` — 配置实例，通过 `cfg.api_key`、`cfg.base_url` 等访问
- `logger` — 全局日志对象，控制台和文件使用独立的日志级别

### config/connect_dify.py

Dify API 连接器。包含：
- `DifyChatflowTester` — Chatflow 测试器，调用 `/v1/chat-messages`，SSE 流式解析
  - `run()` — 单轮对话
  - `run_multi_turn()` — 多轮对话，串行执行并自动传递 `conversation_id`
- `DifyWorkflowTester` — Workflow 测试器，调用 `/v1/workflows/run`，SSE 流式解析
- `deep_parse_json_values()` — 递归解析嵌套的 JSON 字符串值
- `create_tester()` — 工厂函数，根据 `app_type` 创建对应的测试器实例

### config/llm_client.py

LLM 评估客户端，支持 OpenAI SDK 和 requests 两种调用方式。用于批量评测时自动对比期望结果和实际结果。

### evaluate/evaluate.py

批量评测执行器 `DifyEvaluator`，流程：
1. 读取 Excel 测试数据
2. 解析 `input` 列的 JSON 数组
3. 根据数组长度自动选择单轮/多轮执行
4. 收集结果、节点轨迹和所有轮次回答
5. 可选：调用 LLM 进行语义评估
6. 写入带时间戳的结果 Excel（自动处理 Excel 公式字符和单元格长度限制）

### evaluate/single_test.py

交互式单例测试。在命令行输入提示词后，展示每个节点的执行输出和最终回答。Chatflow 模式下自动维护 `conversation_id` 实现多轮对话。

## 运行测试

```bash
# 运行所有测试
python tests/test_multi_turn.py

# 运行单项测试
python tests/test_multi_turn.py --test parse    # 输入解析测试
python tests/test_multi_turn.py --test result   # 结果解析测试
python tests/test_multi_turn.py --test api      # API 多轮对话测试
python tests/test_multi_turn.py --test batch    # 端到端 batch 测试
```

## 日志说明

日志分两路输出，级别独立控制：

- **控制台** — 默认 `INFO` 级别，只显示节点名称和关键状态信息
- **日志文件** — 默认 `DEBUG` 级别，记录每个节点的完整 JSON 输出

日志文件示例（DEBUG 级别）：

```
2026-04-09 13:30:59 - INFO -   节点 -> [用户输入]
2026-04-09 13:30:59 - DEBUG -   [用户输入] 输出:
{
  "customer_id": "11111",
  "sys.query": "买三包化肥",
  "sys.dialogue_count": 1
}
2026-04-09 13:31:03 - INFO -   节点 -> [路由判断]
2026-04-09 13:31:03 - DEBUG -   [路由判断] 输出:
{
  "text": {
    "intent": "SHOPPING",
    "confidence": 99
  }
}
```

如需在控制台也查看完整 JSON，将 `conf.ini` 中的 `CONSOLE_LEVEL` 改为 `DEBUG`。
