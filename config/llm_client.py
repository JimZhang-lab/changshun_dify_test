'''
Author: JimZhang
Date: 2026-04-09 16:13:20
LastEditors: 很拉风的James
LastEditTime: 2026-04-09 16:32:40
FilePath: /changshun_dify_test/config/llm_client.py
Description: OpenAI and Requests client configuration and initialization
'''

import os
import requests
from openai import OpenAI
from .config import cfg
import logging

def test_connection() -> bool:
    """测试当前大语言模型接口连通性"""
    logging.info(f"正在进行 LLM连通性测试 ({cfg.eval_client_method}) ...")
    resp = current_api("ping", "你是一个测试助手。无论我说什么，请只回复'OK'这两个字母，不带标点。")
    if resp and "ok" in resp.lower():
        logging.info("LLM 连通性测试通过！")
        return True
    
    logging.error(f"LLM 连通性测试失败！响应为: '{resp}'")
    return False

def current_api(
    question: str,
    system_prompt: str = "You are Qwen, created by Alibaba Cloud. You are a helpful assistant."
) -> str:
    """根据配置分发 HTTP 或 SDK 的大模型调用"""
    if cfg.eval_client_method == "requests":
        return _call_api_with_requests(question, system_prompt)
    return _call_api_with_openai(question, system_prompt)


def _call_api_with_openai(question: str, system_prompt: str) -> str:
    """使用 OpenAI SDK 调用 API"""
    client = OpenAI(
        api_key=cfg.eval_api_key,
        base_url=cfg.eval_base_url,
        timeout=cfg.eval_timeout,
        max_retries=cfg.eval_max_retries
    )
    
    extra_body = {}
    if cfg.eval_enable_thinking:
        extra_body["chat_template_kwargs"] = {"enable_thinking": cfg.eval_enable_thinking}
    
    try:
        response = client.chat.completions.create(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": question}
            ],
            model=cfg.eval_model_name,
            max_tokens=cfg.eval_max_token,
            temperature=cfg.eval_temperature,
            extra_body=extra_body if extra_body else None
        )
        return response.choices[0].message.content
    except Exception as e:
        logging.error(f"=================Error: OpenAI SDK 请求异常({e})！==================")
        return ""


def _call_api_with_requests(question: str, system_prompt: str) -> str:
    """使用 requests 库调用 API"""
    url = cfg.eval_base_url.rstrip('/')
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {cfg.eval_api_key}"
    }
    
    payload = {
        "model": cfg.eval_model_name,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": question}
        ],
        "max_tokens": cfg.eval_max_token,
        "temperature": cfg.eval_temperature
    }
    
    # 添加 enable_thinking 配置
    if cfg.eval_enable_thinking:
        payload["chat_template_kwargs"] = {"enable_thinking": cfg.eval_enable_thinking}
    
    for attempt in range(cfg.eval_max_retries + 1):
        try:
            response = requests.post(
                url,
                headers=headers,
                json=payload,
                timeout=cfg.eval_timeout
            )
            response.raise_for_status()
            result = response.json()
            return result["choices"][0]["message"]["content"]
        except requests.exceptions.Timeout:
            logging.warning(f"请求超时，第 {attempt + 1}/{cfg.eval_max_retries + 1} 次尝试")
        except requests.exceptions.HTTPError as e:
            logging.error(f"HTTP 错误: {e}, 状态码: {response.status_code}")
            break
        except requests.exceptions.RequestException as e:
            logging.warning(f"请求异常: {e}，第 {attempt + 1}/{cfg.eval_max_retries + 1} 次尝试")
        except (KeyError, IndexError) as e:
            logging.error(f"响应解析错误: {e}")
            break
    
    logging.error("=================Error: requests 请求失败！==================")
    return ""


def get_expect_eval_prompt(gold: str, actual: str):
    """装配预期结果比对评测提示词"""
    sys_prompt = "你是一个专业的评测专家。你需要对比两段文本的语义是否一致。"
    prompt = (
        f"对比以下两段文本是否一致。\n"
        f"期望结果: {gold}\n"
        f"实际结果: {actual}\n\n"
        f"请严格按照以下格式输出：\n"
        f"选项: [此处填写: 一致, 基本一致, 不一致其中的一个]\n"
        f"理由: [给出详细的判断，比如哪里不一致，可能是什么原因导致的等详细说明]"
    )
    return prompt, sys_prompt


def get_trace_eval_prompt(gold: str, actual: str):
    """装配执行轨迹比对评测提示词"""
    sys_prompt = "你是一个专业的AI评测专家。你需要对比两段执行轨迹(Node Traces)的逻辑和执行节点是否一致。"
    prompt = (
        f"对比以下两段执行轨迹信息。\n"
        f"期望轨迹: {gold}\n"
        f"实际轨迹: {actual}\n\n"
        f"请严格按照以下格式输出：\n"
        f"选项: [此处填写: 一致, 基本一致, 不一致其中的一个]\n"
        f"理由: [给出详细的判断，比如哪里不一致，可能有什么节点的差异等详细说明]"
    )
    return prompt, sys_prompt
