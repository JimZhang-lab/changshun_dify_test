'''
Author: JimZhang
Date: 2026-04-09 02:18:35
LastEditors: 很拉风的James
LastEditTime: 2026-04-09 02:19:38
FilePath: /changshun_dify_test/config/connect_dify.py
Description: 

'''
import requests
import json
from .config import logger

class DifyWorkflowTester:
    def __init__(self, api_key: str, base_url: str = "https://api.dify.ai/v1"):
        self.api_key = api_key
        self.base_url = base_url.rstrip('/')
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

    def run_workflow(self, inputs: dict, user_id: str = "test-user"):
        endpoint = f"{self.base_url}/workflows/run"
        
        # 强制使用 streaming 来捕捉流程中每个节点的独立输出
        payload = {
            "inputs": inputs,
            "response_mode": "streaming",
            "user": user_id
        }

        try:
            response = requests.post(
                endpoint, 
                headers=self.headers, 
                json=payload, 
                stream=True
            )
            response.raise_for_status() 

            traces = []
            final_outputs = {}

            logger.info("开始追踪工作流节点...")
            for line in response.iter_lines():
                if line:
                    decoded_line = line.decode('utf-8')
                    if decoded_line.startswith("data: "):
                        data_str = decoded_line[6:]
                        try:
                            data_json = json.loads(data_str)
                            event = data_json.get("event")
                            
                            # 拦截中间节点
                            if event == "node_finished":
                                node_data = data_json.get("data", {})
                                node_title = node_data.get("title", node_data.get("node_type", "Unknown_Node"))
                                node_outputs = node_data.get("outputs", {})
                                
                                traces.append({
                                    "node": node_title,
                                    "output": node_outputs
                                })
                                logger.info(f" 节点追踪 -> [{node_title}] 输出: {json.dumps(node_outputs, ensure_ascii=False)}")
                                
                            # 拦截最终整体完成事件
                            elif event == "workflow_finished":
                                final_outputs = data_json.get("data", {}).get("outputs", {})
                                logger.info(f"工作流全部执行完成")
                        except json.JSONDecodeError:
                            pass
            
            return {
                "data": {"outputs": final_outputs},
                "traces": traces
            }

        except requests.exceptions.RequestException as e:
            logger.error(f"请求失败: {e}")
            if e.response is not None:
                logger.error(f"服务器返回信息: {e.response.text}")
            return None
