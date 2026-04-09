'''
Author: JimZhang
Date: 2026-04-09 02:18:56
LastEditors: JimZhang
LastEditTime: 2026-04-09 13:41:00
FilePath: /changshun_dify_test/evaluate/evaluate.py
'''
import os
import json
import time
import pandas as pd
from config.config import cfg, logger
from config.connect_dify import create_tester


class DifyEvaluator:

    def __init__(self):
        self.tester = create_tester(cfg.app_type, cfg.api_key, cfg.base_url)
        self.test_data_path = cfg.test_data_path
        self.result_dir = cfg.result_dir

    def run_batch(self):
        self._print_header()

        try:
            df = pd.read_excel(self.test_data_path)
            df = df.fillna("")
        except Exception as e:
            logger.error(f"读取 Excel 失败: {e}")
            return

        results, trace_results = [], []
        total = len(df)
        success_count = skip_count = fail_count = 0
        start_time = time.time()

        for index, row in df.iterrows():
            item_id = row.get("id", index)
            input_text = str(row.get("input", "")).strip()

            if not input_text:
                skip_count += 1
                results.append("")
                trace_results.append("")
                continue

            self._print_test_start(index + 1, total, item_id, input_text)

            t0 = time.time()
            predict_text, trace_text = self._process_single(input_text, row)
            elapsed = time.time() - t0

            results.append(predict_text)
            trace_results.append(trace_text)

            ok = predict_text and predict_text != "[请求失败]"
            success_count += ok
            fail_count += (not ok)
            self._print_test_result(predict_text, trace_text, elapsed, ok)

        df["predict"] = results
        df["node_traces"] = trace_results

        result_path = os.path.join(self.result_dir, f"result_{cfg.run_timestamp}.xlsx")
        df.to_excel(result_path, index=False)

        total_elapsed = time.time() - start_time
        self._print_summary(total, success_count, skip_count, fail_count, total_elapsed, result_path)
        return result_path

    def _process_single(self, input_text, row):
        if cfg.app_type == "chatflow":
            inputs = {}
            cid = str(row.get("customer_id", "")).strip()
            if cid:
                inputs["customer_id"] = cid
            result = self.tester.run(query=input_text, inputs=inputs)
        else:
            result = self.tester.run(inputs={"text_input": input_text, "language": "zh-CN"})
        return self._parse_result(result)

    def _parse_result(self, result):
        if not result:
            return "[请求失败]", ""

        if "answer" in result:
            predict = result["answer"]
        elif "data" in result and "outputs" in result["data"]:
            outputs = result["data"]["outputs"]
            predict = outputs.get("text", str(outputs))
        else:
            predict = str(result)

        trace = ""
        if result.get("traces"):
            parts = []
            for t in result["traces"]:
                formatted = json.dumps(t['output'], ensure_ascii=False, indent=2)
                parts.append(f"[{t['node']}]:\n{formatted}")
            trace = "\n\n".join(parts)

        return predict, trace

    def _print_header(self):
        logger.info(f"读取测试数据: {self.test_data_path}")
        print()
        print(f"  Dify 批量评测")
        print(f"  {'-'*40}")
        print(f"  模式:   {cfg.app_type.upper()}")
        print(f"  API:    {cfg.base_url}")
        print(f"  数据:   {os.path.basename(self.test_data_path)}")
        print(f"  时间戳: {cfg.run_timestamp}")
        print()

    def _print_test_start(self, current, total, item_id, input_text):
        bar = self._progress_bar(current, total)
        print(f"  测试 [{current}/{total}] {bar}")
        print(f"    ID: {item_id}")
        print(f"    输入: {input_text}")

    def _print_test_result(self, predict_text, trace_text, elapsed, success):
        status = "OK" if success else "FAIL"
        print(f"    结果: {status}  耗时 {elapsed:.2f}s")
        print()
        print(f"    预测:")
        for line in (predict_text or "(空)").split('\n'):
            print(f"      {line}")
        if trace_text:
            print()
            print(f"    节点轨迹:")
            for line in trace_text.split('\n'):
                print(f"      {line}")
        print(f"  {'-'*40}")
        print()

    def _print_summary(self, total, success, skip, fail, elapsed, result_path):
        elapsed_str = f"{elapsed:.2f}s"
        rel_path = os.path.relpath(result_path)
        print()
        print(f"  评测完成")
        print(f"  {'-'*40}")
        print(f"  总计: {total}")
        print(f"  成功: {success}")
        print(f"  跳过: {skip}")
        print(f"  失败: {fail}")
        print(f"  耗时: {elapsed_str}")
        print(f"  结果: {rel_path}")
        print()
        logger.info(f"评测完成: {result_path}")
        logger.info(f"总计 {total} | 成功 {success} | 跳过 {skip} | 失败 {fail} | 耗时 {elapsed_str}")

    @staticmethod
    def _progress_bar(current, total, width=20):
        if total == 0:
            return "[" + "-" * width + "] 0%"
        ratio = current / total
        filled = int(width * ratio)
        return f"[{'#' * filled}{'-' * (width - filled)}] {int(ratio * 100)}%"


def run_evaluate():
    return DifyEvaluator().run_batch()


if __name__ == "__main__":
    run_evaluate()
