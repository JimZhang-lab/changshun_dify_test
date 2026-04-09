'''
Author: JimZhang
Date: 2026-04-09 02:18:56
LastEditors: 很拉风的James
LastEditTime: 2026-04-09 16:45:00
FilePath: /changshun_dify_test/evaluate/evaluate.py
'''
import os
import json
import time
import pandas as pd
import argparse
import concurrent.futures
from config.config import cfg, logger
from config.connect_dify import create_tester
from config.llm_client import current_api, get_expect_eval_prompt, get_trace_eval_prompt, test_connection


class DifyEvaluator:

    def __init__(self):
        self.tester = create_tester(cfg.app_type, cfg.api_key, cfg.base_url)
        self.test_data_path = cfg.test_data_path
        self.result_dir = cfg.result_dir

    def run_batch(self, use_llm_eval=False):
        self._print_header(use_llm_eval)

        if use_llm_eval:
            is_connected = test_connection()
            if not is_connected:
                logger.error("LLM 连通性测试未通过，批量评测已终止。请检查 config/conf.ini 中的大模型配置。")
                return None

        try:
            df = pd.read_excel(self.test_data_path)
            df = df.fillna("")
        except Exception as e:
            logger.error(f"读取 Excel 失败: {e}")
            return

        total = len(df)
        success_count = 0
        skip_count = 0
        fail_count = 0
        start_time = time.time()

        results = [""] * total
        trace_results = [""] * total
        eval_expect_opts = [""] * total
        eval_expect_reasons = [""] * total
        eval_trace_opts = [""] * total
        eval_trace_reasons = [""] * total

        def process_row(index, row):
            item_id = row.get("id", index)
            input_text = str(row.get("input", "")).strip()
            expect = str(row.get("expect", "")).strip()
            gold_traces = str(row.get("gold_node_traces", "")).strip()

            if not input_text:
                return index, item_id, None, None, None, False, 0.0, "", "", "", ""

            t0 = time.time()
            predict_text, trace_text = self._process_single(input_text, row)
            elapsed = time.time() - t0
            ok = predict_text and predict_text != "[请求失败]"

            # Run LLM evaluation
            exp_opt, exp_reason = "", ""
            trace_opt, trace_reason = "", ""
            
            if use_llm_eval:
                if expect and ok:
                    exp_opt, exp_reason = self._evaluate_with_llm("expect", expect, predict_text)
                
                if gold_traces and ok:
                    trace_opt, trace_reason = self._evaluate_with_llm("trace", gold_traces, trace_text)

            return index, item_id, input_text, predict_text, trace_text, ok, elapsed, exp_opt, exp_reason, trace_opt, trace_reason

        # Using ThreadPoolExecutor
        workers = getattr(cfg, 'max_workers', 5)
        logger.info(f"启动多线程评测，最大线程数: {workers}")
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {executor.submit(process_row, idx, row): idx for idx, row in df.iterrows()}
            completed = 0

            for future in concurrent.futures.as_completed(futures):
                idx = futures[future]
                completed += 1
                try:
                    res = future.result()
                    index, item_id, input_text, predict_text, trace_text, ok, elapsed, exp_opt, exp_reason, tr_opt, tr_reason = res
                    
                    if input_text is None:
                        skip_count += 1
                        continue

                    results[idx] = predict_text
                    trace_results[idx] = trace_text
                    eval_expect_opts[idx] = exp_opt
                    eval_expect_reasons[idx] = exp_reason
                    eval_trace_opts[idx] = tr_opt
                    eval_trace_reasons[idx] = tr_reason

                    success_count += ok
                    fail_count += (not ok)
                    
                    self._print_test_start(completed, total, item_id, input_text)
                    self._print_test_result(predict_text, trace_text, elapsed, ok, exp_opt, tr_opt)

                except Exception as exc:
                    logger.error(f"行 {idx} 处理异常: {exc}")
                    fail_count += 1

        df["predict"] = results
        df["node_traces"] = trace_results

        result_path = os.path.join(self.result_dir, f"result_{cfg.run_timestamp}.xlsx")
        df.to_excel(result_path, index=False)

        if use_llm_eval:
            df["eval_expect_opt"] = eval_expect_opts
            df["eval_expect_reason"] = eval_expect_reasons
            df["eval_trace_opt"] = eval_trace_opts
            df["eval_trace_reason"] = eval_trace_reasons

            compare_path = os.path.join(self.result_dir, f"compare_{cfg.run_timestamp}.xlsx")
            df.to_excel(compare_path, index=False)
            final_path = compare_path
        else:
            final_path = result_path

        total_elapsed = time.time() - start_time
        self._print_summary(total, success_count, skip_count, fail_count, total_elapsed, final_path)
        return final_path

    def _evaluate_with_llm(self, mode, gold, actual):
        if mode == "expect":
            prompt, sys_prompt = get_expect_eval_prompt(gold, actual)
        else:
            prompt, sys_prompt = get_trace_eval_prompt(gold, actual)
        
        response = current_api(prompt, sys_prompt)
        
        option = "未知"
        reason = response
        
        if response:
            lines = [line.strip() for line in response.split('\n') if line.strip()]
            for line in lines:
                if line.startswith("选项:"):
                    opt = line.replace("选项:", "").strip().strip("[]【】")
                    if "不一致" in opt:
                        option = "不一致"
                    elif "基本一致" in opt:
                        option = "基本一致"
                    elif "一致" in opt:
                        option = "一致"
                elif line.startswith("理由:"):
                    reason = line.replace("理由:", "").strip()
            
            if option == "未知":
                if "选项:基本一致" in response or "基本一致" in response[:20]:
                    option = "基本一致"
                elif "选项:不一致" in response or "不一致" in response[:20]:
                    option = "不一致"
                elif "选项:一致" in response or "一致" in response[:20]:
                    option = "一致"
                
                if "理由:" in response:
                    parts = response.split("理由:", 1)
                    if len(parts) > 1:
                        reason = parts[1].strip()

        return option, reason

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

    def _print_header(self, use_llm_eval):
        logger.info(f"读取测试数据: {self.test_data_path}")
        print()
        status_llm = "开启" if use_llm_eval else "关闭"
        print(f"  Dify 批量评测 (并行 & LLM 校验: {status_llm})")
        print(f"  {'-'*40}")
        print(f"  模式:   {cfg.app_type.upper()}")
        print(f"  API:    {cfg.base_url}")
        print(f"  数据:   {os.path.basename(self.test_data_path)}")
        print(f"  线程数: {getattr(cfg, 'max_workers', 5)}")
        print(f"  时间戳: {cfg.run_timestamp}")
        print()

    def _print_test_start(self, current, total, item_id, input_text):
        bar = self._progress_bar(current, total)
        print(f"  进度 [{current}/{total}] {bar}")
        print(f"    ID: {item_id}")
        short_input = input_text[:30] + "..." if len(input_text) > 30 else input_text
        print(f"    输入: {short_input}")

    def _print_test_result(self, predict_text, trace_text, elapsed, success, exp_opt, tr_opt):
        status = "OK" if success else "FAIL"
        llm_status = f" | Expect: {exp_opt or 'N/A'} | Trace: {tr_opt or 'N/A'}"
        print(f"    结果: {status}  耗时 {elapsed:.2f}s{llm_status}")
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


def run_evaluate(use_llm_eval=False):
    return DifyEvaluator().run_batch(use_llm_eval=use_llm_eval)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Dify Evaluation Script")
    parser.add_argument("--use-llm", action="store_true", help="Enable LLM evaluation")
    args = parser.parse_args()
    
    run_evaluate(use_llm_eval=args.use_llm)
