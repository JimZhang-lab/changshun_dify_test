# 长顺农服 Dify 测试工具

针对长顺农服 Dify 应用的自动化测试工具，支持 Chatflow 和 Workflow 两种模式。提供交互式单例测试和批量评测两种运行方式，能够追踪每个节点的执行过程并自动解析嵌套 JSON 输出。

## 目录结构

```
changshun_dify_test/
├── main.py                          # 入口文件，调度单例测试和批量评测
├── config/
│   ├── __init__.py
│   ├── conf.ini                     # 配置文件（含 API Key，不提交到仓库）
│   ├── conf copy.ini                # 配置文件模板（用于新环境初始化）
│   ├── config.py                    # 配置读取，统一管理所有配置项和日志初始化
│   └── connect_dify.py              # Dify API 连接器，Chatflow/Workflow 测试器实现
├── evaluate/
│   ├── __init__.py
│   ├── evaluate.py                  # 批量评测逻辑，读取 Excel 数据，逐条测试并输出结果
│   └── single_test.py               # 交互式单例测试，支持多轮对话和节点追踪
├── data/
│   └── chatflow_test_data.xlsx      # 测试数据（Excel 格式）
├── results/                         # 评测结果输出目录（自动创建）
│   └── result_MMDDHHMMSS.xlsx       # 带时间戳的评测结果文件
├── logs/                            # 日志输出目录（自动创建）
│   └── app_MMDDHHMMSS.log          # 带时间戳的日志文件
├── scripts/
│   ├── start_evaluate.sh            # 批量评测启动脚本
│   └── siege.sh                     # 压测脚本（预留）
├── .gitignore
├── LICENSE
└── README.md
```

## 环境准备

### 依赖安装

```bash
pip install requests pandas openpyxl
```

### 配置文件

复制模板并填入实际的 API Key 和接口地址：

```bash
cp config/conf\ copy.ini config/conf.ini
```

编辑 `config/conf.ini`：

```ini
[log]
level = INFO
console_level = INFO       # 控制台日志级别，可选 DEBUG/INFO/WARNING
file_level = DEBUG          # 文件日志级别，DEBUG 会记录每个节点的完整 JSON 输出
target = both               # 日志输出目标：console / file / both
file_path = logs/app.log    # 日志文件路径模板，实际文件名会追加时间戳

[evaluate]
test_file_path = data/chatflow_test_data.xlsx   # 测试数据文件路径
result_dir = results                             # 结果输出目录

[Dify]
api_key = app-xxxxxxxxxxxxxxxxxxxxxxxx           # Dify 应用 API Key
base_url = https://api.dify.ai/v1                # Dify API 地址
app_type = chatflow                              # 应用类型：chatflow 或 workflow
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
  +-- [1/14] 用户输入
  |     { "sys.query": "买三包化肥", ... }
  +-- [2/14] 路由判断
  |     { "text": { "intent": "SHOPPING", "confidence": 99 } }
  ...
  +-- 全部 14 个节点执行完毕

  回答:
  我找到这些商品，您可以回复'第几个商品'继续查看：
  1. 赤天化尿素（95元/袋，库存212）
  2. 西洋复合肥（15:15:15）（142.5元/袋，库存195）
  ...
```

输入 `quit`、`q` 或 `exit` 退出。

### 批量评测

从 Excel 文件读取测试用例，逐条发送请求，将预测结果和节点轨迹写入结果文件。

```bash
python main.py --mode batch
# 或
bash scripts/start_evaluate.sh
```

评测完成后，结果保存在 `results/result_MMDDHHMMSS.xlsx`，日志保存在 `logs/app_MMDDHHMMSS.log`。

## 测试数据格式

测试数据为 Excel 文件，必须包含以下列：

| 列名                 | 必填 | 说明                                             |
| -------------------- | ---- | ------------------------------------------------ |
| `id`               | 是   | 测试用例编号                                     |
| `input`            | 是   | 用户输入的提示词                                 |
| `expect`           | 否   | 期望的回答（用于人工比对）                       |
| `gold_node_traces` | 否   | 期望的节点执行路径（用于人工比对）               |
| `customer_id`      | 否   | Chatflow 模式下的客户 ID（作为 inputs 参数传入） |

批量评测后，会在 Excel 中追加两列：

| 列名            | 说明                            |
| --------------- | ------------------------------- |
| `predict`     | Dify 返回的实际回答             |
| `node_traces` | 各节点的完整输出（格式化 JSON） |

## 文件说明

### config/config.py

统一配置管理。从 `conf.ini` 读取所有配置项并封装为 `Config` 类的实例 `cfg`。负责路径解析（相对路径转绝对路径）、目录自动创建、日志初始化。

导出：

- `cfg` — 配置实例，通过 `cfg.api_key`、`cfg.base_url` 等访问
- `logger` — 全局日志对象，控制台和文件使用独立的日志级别

### config/connect_dify.py

Dify API 连接器。包含：

- `DifyChatflowTester` — Chatflow 测试器，调用 `/v1/chat-messages`，SSE 流式解析
- `DifyWorkflowTester` — Workflow 测试器，调用 `/v1/workflows/run`，SSE 流式解析
- `deep_parse_json_values()` — 递归解析嵌套的 JSON 字符串值，将 `"{\"key\":\"val\"}"` 展开为原生 dict
- `create_tester()` — 工厂函数，根据 `app_type` 创建对应的测试器实例

### evaluate/evaluate.py

批量评测执行器 `DifyEvaluator`，流程：读取 Excel → 逐条发送请求 → 收集结果和节点轨迹 → 写入带时间戳的结果文件。

### evaluate/single_test.py

交互式单例测试。在命令行输入提示词后，展示每个节点的执行输出和最终回答。Chatflow 模式下自动维护 `conversation_id` 实现多轮对话。

### tests/test.py

原始的 API 调用测试脚本，用于直接调试 Dify 接口。不依赖项目模块，可独立运行。

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

如需在控制台也查看完整 JSON，将 `conf.ini` 中的 `console_level` 改为 `DEBUG`。
