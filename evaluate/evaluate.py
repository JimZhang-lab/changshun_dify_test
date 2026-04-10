'''
Author: JimZhang
Date: 2026-04-09 02:18:56
LastEditors: JimZhang
LastEditTime: 2026-04-10 15:28:00
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


def _parse_input(raw_input):
    """
    解析 input 列，统一使用 JSON 数组格式。
    
    支持格式：
    1. JSON 数组: '["买复合肥", "第1个", "确认下单"]'
    2. 纯文本（向后兼容，自动包装为单元素数组）: '买两袋复合肥' → ["买两袋复合肥"]
    
    Returns:
        list[str] 或 None（空输入时）
    """
    raw = str(raw_input).strip()
    if not raw:
        return None

    # 尝试解析为 JSON 数组
    if raw.startswith("["):
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list) and all(isinstance(x, str) for x in parsed):
                items = [q.strip() for q in parsed if q.strip()]
                return items if items else None
        except json.JSONDecodeError:
            pass

    # 纯文本 → 自动包装为单元素数组（向后兼容）
    return [raw]


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
            return None

        total = len(df)
        success_count = 0
        skip_count = 0
        fail_count = 0
        start_time = time.time()

        results = [""] * total
        trace_results = [""] * total
        rounds_list = [0] * total
        all_answers_list = [""] * total
        eval_expect_opts = [""] * total
        eval_expect_reasons = [""] * total
        eval_trace_opts = [""] * total
        eval_trace_reasons = [""] * total

        def process_row(index, row):
            item_id = row.get("id", index)
            raw_input = row.get("input", "")
            expect = str(row.get("expect", "")).strip()
            gold_traces = str(row.get("gold_node_traces", "")).strip()

            input_data = _parse_input(raw_input)
            if not input_data:
                return index, item_id, None, None, None, False, 0.0, "", "", "", "", 0, ""

            num_rounds = len(input_data)
            t0 = time.time()
            predict_text, trace_text, all_answers = self._process_single(input_data, row)
            elapsed = time.time() - t0
            ok = bool(predict_text and predict_text != "[请求失败]")

            # Run LLM evaluation
            exp_opt, exp_reason = "", ""
            trace_opt, trace_reason = "", ""
            
            if use_llm_eval:
                if expect and ok:
                    exp_opt, exp_reason = self._evaluate_with_llm("expect", expect, predict_text)
                
                if gold_traces and ok:
                    trace_opt, trace_reason = self._evaluate_with_llm("trace", gold_traces, trace_text)

            return index, item_id, input_data, predict_text, trace_text, ok, elapsed, exp_opt, exp_reason, trace_opt, trace_reason, num_rounds, all_answers

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
                    (index, item_id, input_data, predict_text, trace_text, ok, elapsed,
                     exp_opt, exp_reason, tr_opt, tr_reason, num_rounds, all_answers) = res
                    
                    if input_data is None:
                        skip_count += 1
                        continue

                    results[idx] = predict_text or ""
                    trace_results[idx] = trace_text or ""
                    rounds_list[idx] = num_rounds
                    all_answers_list[idx] = all_answers or ""
                    eval_expect_opts[idx] = exp_opt
                    eval_expect_reasons[idx] = exp_reason
                    eval_trace_opts[idx] = tr_opt
                    eval_trace_reasons[idx] = tr_reason

                    success_count += ok
                    fail_count += (not ok)
                    
                    self._print_test_start(completed, total, item_id, input_data)
                    self._print_test_result(predict_text, trace_text, elapsed, ok, exp_opt, tr_opt, num_rounds)

                except Exception as exc:
                    logger.error(f"行 {idx} 处理异常: {exc}")
                    fail_count += 1

        df["rounds"] = rounds_list
        df["predict"] = results
        df["all_answers"] = all_answers_list
        df["node_traces"] = trace_results

        result_path = os.path.join(self.result_dir, f"result_{cfg.run_timestamp}.xlsx")
        self._safe_to_excel(df, result_path)

        if use_llm_eval:
            df["eval_expect_opt"] = eval_expect_opts
            df["eval_expect_reason"] = eval_expect_reasons
            df["eval_trace_opt"] = eval_trace_opts
            df["eval_trace_reason"] = eval_trace_reasons

            compare_path = os.path.join(self.result_dir, f"compare_{cfg.run_timestamp}.xlsx")
            self._safe_to_excel(df, compare_path)
            final_path = compare_path
        else:
            final_path = result_path

        total_elapsed = time.time() - start_time
        self._print_summary(total, success_count, skip_count, fail_count, total_elapsed, final_path)
        return final_path

    @staticmethod
    def _safe_to_excel(df, path):
        """
        安全写入 Excel，处理两个潜在问题：
        1. 以 '=' 开头的字符串会被 Excel/openpyxl 误判为公式 → 前缀空格
        2. 超过 32767 字符的单元格会被截断 → 主动截断并标注
        """
        EXCEL_MAX_CELL = 32767
        TRUNCATE_SUFFIX = "\n...[内容过长，已截断]"

        df_out = df.copy()
        for col in df_out.columns:
            if df_out[col].dtype == object:
                def sanitize(val):
                    if not isinstance(val, str):
                        return val
                    # 避免 '=' 开头被解析为公式
                    if val.startswith("="):
                        val = " " + val
                    # 截断超长内容
                    if len(val) > EXCEL_MAX_CELL:
                        val = val[:EXCEL_MAX_CELL - len(TRUNCATE_SUFFIX)] + TRUNCATE_SUFFIX
                    return val
                df_out[col] = df_out[col].map(sanitize)

        df_out.to_excel(path, index=False)

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

    def _process_single(self, input_data, row):
        """
        处理单个测试用例（支持单轮和多轮）。
        
        Args:
            input_data: list[str]，用户输入列表
            row: DataFrame 行数据
            
        Returns:
            (predict_text, trace_text, all_answers_json)
        """
        if cfg.app_type == "chatflow":
            inputs = {}
            cid = str(row.get("customer_id", "")).strip()
            if cid:
                inputs["customer_id"] = cid

            if len(input_data) > 1:
                # 多轮对话
                result = self.tester.run_multi_turn(queries=input_data, inputs=inputs)
                return self._parse_multi_turn_result(result)
            else:
                # 单轮
                result = self.tester.run(query=input_data[0], inputs=inputs)
                predict, trace = self._parse_result(result)
                all_answers = json.dumps([predict], ensure_ascii=False) if predict else "[]"
                return predict, trace, all_answers
        else:
            # workflow 模式不支持多轮，取第一个输入
            query = input_data[0]
            result = self.tester.run(inputs={"text_input": query, "language": "zh-CN"})
            predict, trace = self._parse_result(result)
            all_answers = json.dumps([predict], ensure_ascii=False) if predict else "[]"
            return predict, trace, all_answers

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

    def _parse_multi_turn_result(self, result):
        """
        解析多轮对话结果。
        
        Returns:
            (predict_text, trace_text, all_answers_json)
            predict_text: 最后一轮的回答
            trace_text: 所有轮次的节点轨迹（带轮次标记）
            all_answers_json: 所有轮次回答的 JSON 字符串
        """
        if not result:
            return "[请求失败]", "", "[]"

        predict = result["final_answer"]

        # 收集所有轮次回答
        all_answers = []
        for r in result["rounds"]:
            all_answers.append(r["answer"])

        # traces：每轮用分隔线标记
        # 注意：不以 '=' 开头，避免 openpyxl 将其误判为 Excel 公式
        trace_parts = []
        for r in result["rounds"]:
            query_short = r["query"][:30] + ("..." if len(r["query"]) > 30 else "")
            header = f"----- 第{r['round']}轮: {query_short} -----"
            if r["traces"]:
                nodes = []
                for t in r["traces"]:
                    formatted = json.dumps(t['output'], ensure_ascii=False, indent=2)
                    nodes.append(f"[{t['node']}]:\n{formatted}")
                trace_parts.append(f"{header}\n" + "\n\n".join(nodes))
            else:
                trace_parts.append(f"{header}\n[无节点轨迹]")

        trace = "\n\n".join(trace_parts)
        all_answers_json = json.dumps(all_answers, ensure_ascii=False)
        return predict, trace, all_answers_json

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

    def _print_test_start(self, current, total, item_id, input_data):
        bar = self._progress_bar(current, total)
        print(f"  进度 [{current}/{total}] {bar}")
        print(f"    ID: {item_id}")
        if isinstance(input_data, list) and len(input_data) > 1:
            short_first = input_data[0][:20] + ("..." if len(input_data[0]) > 20 else "")
            short_last = input_data[-1][:20] + ("..." if len(input_data[-1]) > 20 else "")
            print(f"    输入: [{short_first} → ... → {short_last}] ({len(input_data)}轮)")
        else:
            text = input_data[0] if isinstance(input_data, list) else str(input_data)
            short_input = text[:30] + "..." if len(text) > 30 else text
            print(f"    输入: {short_input}")

    def _print_test_result(self, predict_text, trace_text, elapsed, success, exp_opt, tr_opt, num_rounds=1):
        status = "OK" if success else "FAIL"
        rounds_info = f" ({num_rounds}轮)" if num_rounds > 1 else ""
        llm_status = f" | Expect: {exp_opt or 'N/A'} | Trace: {tr_opt or 'N/A'}"
        print(f"    结果: {status}{rounds_info}  耗时 {elapsed:.2f}s{llm_status}")
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
