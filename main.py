'''
Author: JimZhang
Date: 2026-04-09 01:56:22
LastEditors: 很拉风的James
LastEditTime: 2026-04-09 02:02:24
FilePath: /changshun_dify_test/main.py
Description: 

'''
import requests
import json
import pandas as pd
from config.config import API_KEY, BASE_URL, TEST_DATA_PATH, logger

from config.connect_dify import DifyWorkflowTester
# ================= 运行测试 =================
if __name__ == "__main__":
    tester = DifyWorkflowTester(api_key=API_KEY, base_url=BASE_URL)

    logger.info(f">>> 正在读取测试数据文件: {TEST_DATA_PATH}...")
    try:
        df = pd.read_excel(TEST_DATA_PATH)
        df = df.fillna("") # 过滤空值
        
        results = []
        trace_results = []
        for index, row in df.iterrows():
            item_id = row.get("id", index)
            input_text = row.get("input", "")
            
            if not str(input_text).strip():
                logger.info(f"--- 忽略空数据 (ID: {item_id}) ---")
                results.append("")
                trace_results.append("")
                continue
                
            logger.info(f"--- 测试记录 ID: {item_id} | 输入: {input_text} ---")
            
            inputs = {
                "text_input": str(input_text), 
                "language": "zh-CN"
            }
            
            result = tester.run_workflow(inputs=inputs)
            
            predict_text = str(result)
            trace_text = ""
            
            if result:
                if "data" in result and "outputs" in result["data"]:
                    outputs = result["data"]["outputs"]
                    predict_text = outputs.get("text", str(outputs))
                
                if "traces" in result:
                    traces = result["traces"]
                    trace_strings = [f"【{t['node']}】: {json.dumps(t['output'], ensure_ascii=False)}" for t in traces]
                    trace_text = "\n -> ".join(trace_strings)
                    
            results.append(predict_text)
            trace_results.append(trace_text)
            
        df["predict"] = results
        df["node_traces"] = trace_results
        df.to_excel(TEST_DATA_PATH, index=False)
        logger.info(">>> 所有测试执行完毕，测试结果以及节点执行轨迹(node_traces)均已回写到 Excel 文件的相应列中！")
        
    except Exception as e:
        logger.error(f"处理 Excel 数据时发生错误: {e}")