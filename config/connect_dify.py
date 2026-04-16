'''
Author: JimZhang
Date: 2026-04-09 02:18:35
LastEditors: JimZhang
LastEditTime: 2026-04-12 16:12:00
FilePath: /changshun_dify_test/config/connect_dify.py
'''
import time
import requests
import json
from .config import logger


def deep_parse_json_values(obj):
    """递归解析展开 JSON 嵌套字符串"""
    if isinstance(obj, dict):
        return {k: deep_parse_json_values(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [deep_parse_json_values(item) for item in obj]
    elif isinstance(obj, str):
        s = obj.strip()
        if (s.startswith('{') and s.endswith('}')) or \
           (s.startswith('[') and s.endswith(']')):
            try:
                return deep_parse_json_values(json.loads(s))
            except (json.JSONDecodeError, ValueError):
                pass
    return obj


def _parse_sse_lines(resp):
    """遍历解析 SSE 数据流行"""
    for line in resp.iter_lines():
        if not line:
            continue
        decoded = line.decode('utf-8')
        if not decoded.startswith("data: "):
            continue
        try:
            yield json.loads(decoded[6:])
        except json.JSONDecodeError:
            pass


def _log_node(title, outputs):
    logger.info(f"  节点 -> [{title}]")
    logger.debug(f"  [{title}] 输出:\n{json.dumps(outputs, ensure_ascii=False, indent=2)}")


class _DifyBaseTester:
    """Dify 接口基类参数注入"""

    def __init__(self, api_key, base_url="https://api.dify.ai/v1"):
        self.api_key = api_key
        self.base_url = base_url.rstrip('/')
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }


class DifyWorkflowTester(_DifyBaseTester):

    def run(self, inputs, user_id="test-user"):
        payload = {
            "inputs": inputs,
            "response_mode": "streaming",
            "user": user_id
        }
        try:
            resp = requests.post(
                f"{self.base_url}/workflows/run",
                headers=self.headers, json=payload, stream=True
            )
            resp.raise_for_status()

            traces = []
            final_outputs = {}

            for data in _parse_sse_lines(resp):
                event = data.get("event")
                if event == "node_finished":
                    nd = data.get("data", {})
                    title = nd.get("title", nd.get("node_type", "Unknown"))
                    outputs = deep_parse_json_values(nd.get("outputs", {}))
                    traces.append({"node": title, "output": outputs})
                    _log_node(title, outputs)
                elif event == "workflow_finished":
                    final_outputs = data.get("data", {}).get("outputs", {})

            return {"data": {"outputs": final_outputs}, "traces": traces}

        except requests.exceptions.RequestException as e:
            logger.error(f"Workflow 请求失败: {e}")
            return None


class DifyChatflowTester(_DifyBaseTester):

    def run(self, query, inputs=None, user_id="abc-123", conversation_id=""):
        payload = {
            "inputs": inputs or {},
            "query": query,
            "response_mode": "streaming",
            "conversation_id": conversation_id,
            "user": user_id,
            "files": []
        }
        try:
            resp = requests.post(
                f"{self.base_url}/chat-messages",
                headers=self.headers, json=payload, stream=True
            )
            resp.raise_for_status()

            traces = []
            answer_parts = []
            result_cid = conversation_id

            for data in _parse_sse_lines(resp):
                event = data.get("event")

                if event == "node_finished":
                    nd = data.get("data", {})
                    title = nd.get("title", nd.get("node_type", "Unknown"))
                    outputs = deep_parse_json_values(nd.get("outputs", {}))
                    traces.append({"node": title, "output": outputs})
                    _log_node(title, outputs)

                elif event in ("agent_message", "message"):
                    chunk = data.get("answer", "")
                    if chunk:
                        answer_parts.append(chunk)
                    cid = data.get("conversation_id", "")
                    if cid:
                        result_cid = cid

                elif event == "message_end":
                    tokens = data.get("metadata", {}).get("usage", {}).get("total_tokens", "?")
                    logger.info(f"完成, tokens: {tokens}")

                elif event == "workflow_finished":
                    logger.info(f"工作流完成: {data.get('data', {}).get('status', '?')}")

                elif event == "error":
                    logger.error(f"错误: {data.get('message', '?')}")

            full_answer = "".join(answer_parts)
            logger.info(f"回答: {full_answer[:200]}{'...' if len(full_answer) > 200 else ''}")

            return {"answer": full_answer, "traces": traces, "conversation_id": result_cid}

        except requests.exceptions.RequestException as e:
            logger.error(f"Chatflow 请求失败: {e}")
            return None

    def run_multi_turn(self, queries, inputs=None, user_id="abc-123"):
        """按序发起多轮对话并用 conversation_id 维系同一次会话"""
        conversation_id = ""
        rounds = []

        for i, query in enumerate(queries):
            round_num = i + 1
            logger.info(f"  多轮对话 [{round_num}/{len(queries)}]: {query[:50]}")

            t0 = time.time()
            # Dify 要求每轮都传入 inputs（如 customer_id），否则返回 400
            result = self.run(
                query=query, inputs=inputs or {},
                user_id=user_id, conversation_id=conversation_id
            )
            elapsed = time.time() - t0

            if not result:
                logger.error(f"  多轮对话第 {round_num} 轮失败，终止后续轮次")
                return None

            conversation_id = result.get("conversation_id", "")
            rounds.append({
                "round": round_num,
                "query": query,
                "answer": result.get("answer", ""),
                "traces": result.get("traces", []),
                "conversation_id": conversation_id,
                "elapsed": elapsed
            })

        return {
            "rounds": rounds,
            "final_answer": rounds[-1]["answer"] if rounds else "",
            "final_traces": rounds[-1]["traces"] if rounds else [],
            "all_traces": [t for r in rounds for t in r["traces"]],
            "conversation_id": conversation_id
        }


def create_tester(app_type, api_key, base_url):
    if app_type == "chatflow":
        return DifyChatflowTester(api_key=api_key, base_url=base_url)
    elif app_type == "workflow":
        return DifyWorkflowTester(api_key=api_key, base_url=base_url)
    else:
        raise ValueError(f"不支持的 app_type: {app_type}")
