'''
Author: JimZhang
Date: 2026-04-09 12:38:00
LastEditors: JimZhang
LastEditTime: 2026-04-09 13:41:00
FilePath: /changshun_dify_test/evaluate/single_test.py
'''
import json
import textwrap
from config.config import cfg, logger
from config.connect_dify import create_tester


def _print_node(index, total, name, output):
    formatted = json.dumps(output, ensure_ascii=False, indent=4)
    indented = textwrap.indent(formatted, "      ")
    print(f"  [{index}/{total}] {name}")
    print(indented)
    print()


def _print_answer(answer, conversation_id=""):
    print("  回答:")
    print(f"  {'-'*40}")
    for p in answer.split('\n'):
        if p.strip():
            print(f"    {p}")
        else:
            print()
    print()
    if conversation_id:
        print(f"  会话 ID: {conversation_id}")
        print(f"  (后续输入在此会话中继续)")
    print()


def run_single_test():
    tester = create_tester(cfg.app_type, cfg.api_key, cfg.base_url)

    print()
    print(f"  Dify 单例测试")
    print(f"  {'-'*40}")
    print(f"  模式: {cfg.app_type.upper()}")
    print(f"  API:  {cfg.base_url}")
    print(f"  输入 quit/q 退出")
    print()

    conversation_id = ""

    while True:
        try:
            query = input("  请输入提示词: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n  已退出")
            break

        if query.lower() in ('quit', 'q', 'exit'):
            print("  已退出")
            break

        if not query:
            print("  输入不能为空\n")
            continue

        customer_id = ""
        if cfg.app_type == "chatflow":
            customer_id = input("  customer_id (回车跳过): ").strip()

        print()
        print(f"  提示词: {query}")
        if customer_id:
            print(f"  客户ID: {customer_id}")
        print()

        logger.info(f"单例测试 | 输入: {query} | customer_id: {customer_id}")

        if cfg.app_type == "chatflow":
            inputs = {"customer_id": customer_id} if customer_id else {}
            result = tester.run(query=query, inputs=inputs, conversation_id=conversation_id)
        else:
            result = tester.run(inputs={"text_input": query, "language": "zh-CN"})

        if not result:
            print("  请求失败，请检查日志\n")
            continue

        traces = result.get("traces", [])
        if traces:
            print(f"  节点轨迹 ({len(traces)} 个节点):")
            print(f"  {'-'*40}")
            for i, t in enumerate(traces, 1):
                _print_node(i, len(traces), t["node"], t["output"])
            print(f"  共 {len(traces)} 个节点执行完毕")
            print()

        if "answer" in result:
            _print_answer(result["answer"], result.get("conversation_id", ""))
            conversation_id = result.get("conversation_id", "")
        elif "data" in result and "outputs" in result["data"]:
            print("  输出:")
            print(f"  {'-'*40}")
            print(textwrap.indent(json.dumps(result["data"]["outputs"], ensure_ascii=False, indent=4), "    "))
            print()

        print(f"  {'='*40}")
        print()

    if conversation_id and cfg.app_type == "chatflow":
        print(f"\n  本次会话 ID: {conversation_id}\n")


if __name__ == "__main__":
    run_single_test()
