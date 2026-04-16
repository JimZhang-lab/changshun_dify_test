'''
Author: JimZhang
Date: 2026-04-09 02:18:56
LastEditors: 很拉风的James
LastEditTime: 2026-04-12 16:15:58
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
    解析 input 列为 JSON 数组格式。支持纯文本后退兼容。
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

    def run_batch(self, use_llm_eval=False, categories=None):
        """
        批量评测。

        Args:
            use_llm_eval: 是否启用 LLM 比对评测
            categories: 要测试的分类列表，None 表示测试所有分类
        """
        self._print_header(use_llm_eval, categories)

        if use_llm_eval:
            is_connected = test_connection()
            if not is_connected:
                logger.error("LLM 连通性测试未通过，批量评测已终止。请检查 config/conf.ini 中的大模型配置。")
                return None

        try:
            df = self._load_test_data(self.test_data_path, categories=categories)
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
        simplify_trace_results = [""] * total
        rounds_list = [0] * total
        all_answers_list = [""] * total
        eval_expect_opts = [""] * total
        eval_expect_reasons = [""] * total
        eval_trace_opts = [""] * total
        eval_trace_reasons = [""] * total
        row_status = [None] * total  # 'ok' / 'fail' / 'skip'

        def process_row(index, row):
            item_id = row.get("id", index)
            raw_input = row.get("input", "")
            expect = str(row.get("expect", "")).strip()
            gold_traces = str(row.get("gold_node_traces", "")).strip()

            input_data = _parse_input(raw_input)
            if not input_data:
                return index, item_id, None, None, None, None, False, 0.0, "", "", "", "", 0, ""

            num_rounds = len(input_data)
            t0 = time.time()
            predict_text, trace_text, all_answers, simplify_trace_text = self._process_single(input_data, row)
            elapsed = time.time() - t0
            ok = bool(predict_text and predict_text != "[请求失败]")

            # Run LLM evaluation
            exp_opt, exp_reason = "", ""
            trace_opt, trace_reason = "", ""
            
            if use_llm_eval:
                if expect and ok:
                    exp_opt, exp_reason = self._evaluate_with_llm("expect", expect, predict_text)
                
                if gold_traces and ok:
                    trace_opt, trace_reason = self._evaluate_with_llm("trace", gold_traces, simplify_trace_text)

            return index, item_id, input_data, predict_text, trace_text, simplify_trace_text, ok, elapsed, exp_opt, exp_reason, trace_opt, trace_reason, num_rounds, all_answers

        # 并发执行
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
                    (index, item_id, input_data, predict_text, trace_text, simplify_trace_text, ok, elapsed,
                     exp_opt, exp_reason, tr_opt, tr_reason, num_rounds, all_answers) = res
                    
                    if input_data is None:
                        skip_count += 1
                        row_status[idx] = 'skip'
                        continue

                    results[idx] = predict_text or ""
                    trace_results[idx] = trace_text or ""
                    simplify_trace_results[idx] = simplify_trace_text or ""
                    rounds_list[idx] = num_rounds
                    all_answers_list[idx] = all_answers or ""
                    eval_expect_opts[idx] = exp_opt
                    eval_expect_reasons[idx] = exp_reason
                    eval_trace_opts[idx] = tr_opt
                    eval_trace_reasons[idx] = tr_reason

                    success_count += ok
                    fail_count += (not ok)
                    row_status[idx] = 'ok' if ok else 'fail'
                    
                    self._print_test_start(completed, total, item_id, input_data)
                    self._print_test_result(predict_text, trace_text, elapsed, ok, exp_opt, tr_opt, num_rounds)

                except Exception as exc:
                    logger.error(f"行 {idx} 处理异常: {exc}")
                    fail_count += 1
                    row_status[idx] = 'fail'

        df["rounds"] = rounds_list
        df["predict"] = results
        df["all_answers"] = all_answers_list
        df["simplify_node_traces"] = simplify_trace_results
        df["node_traces"] = trace_results

        result_path = os.path.join(self.result_dir, f"result_{cfg.run_timestamp}.xlsx")
        self._safe_to_excel_multi_sheet(df, result_path)

        if use_llm_eval:
            df["eval_expect_opt"] = eval_expect_opts
            df["eval_expect_reason"] = eval_expect_reasons
            df["eval_trace_opt"] = eval_trace_opts
            df["eval_trace_reason"] = eval_trace_reasons

            compare_path = os.path.join(self.result_dir, f"compare_{cfg.run_timestamp}.xlsx")
            self._safe_to_excel_multi_sheet(df, compare_path)
            final_path = compare_path
        else:
            final_path = result_path

        # 统计各分类结果
        cat_stats = self._collect_category_stats(df, row_status)

        total_elapsed = time.time() - start_time
        self._print_summary(total, success_count, skip_count, fail_count, total_elapsed, final_path, cat_stats)
        return final_path

    @staticmethod
    def get_categories(path=None):
        """获取所有可用分类及用例数"""
        if path is None:
            path = cfg.test_data_path
        xf = pd.ExcelFile(path)
        sheet_names = xf.sheet_names

        # 多 sheet 结构：直接从各分类 sheet 获取名称和行数，无需读取 ALL
        category_sheets = [s for s in sheet_names if s != 'ALL']
        if len(category_sheets) > 1 or (len(category_sheets) == 1 and 'ALL' in sheet_names):
            result = []
            for s in category_sheets:
                df_sheet = pd.read_excel(xf, sheet_name=s)
                result.append((s, len(df_sheet)))
            return result

        # 单 sheet / 无 ALL：从数据中解析 classified 列
        if len(sheet_names) == 1:
            df = pd.read_excel(xf, sheet_name=sheet_names[0])
        else:
            frames = [pd.read_excel(xf, sheet_name=s) for s in sheet_names]
            df = pd.concat(frames, ignore_index=True)
            if 'id' in df.columns:
                df = df.drop_duplicates(subset='id', keep='first').reset_index(drop=True)

        if 'classified' not in df.columns:
            return []

        df['classified'] = df['classified'].fillna('UNKNOWN').astype(str).str.strip()
        counts = df['classified'].value_counts(sort=False)
        # 按原始出现顺序返回
        seen = []
        for val in df['classified']:
            if val not in seen:
                seen.append(val)
        return [(name, int(counts[name])) for name in seen]

    @staticmethod
    def _load_test_data(path, categories=None):
        """加载 Excel 测试数据，支持按 sheet 或 classified 列过滤分类"""
        xf = pd.ExcelFile(path)
        sheet_names = xf.sheet_names

        # 指定分类时，优先直接从对应 sheet 读取
        if categories:
            matched_sheets = [c for c in categories if c in sheet_names]
            unmatched = [c for c in categories if c not in sheet_names]

            if matched_sheets:
                frames = []
                for s in matched_sheets:
                    df_sheet = pd.read_excel(xf, sheet_name=s)
                    frames.append(df_sheet)
                    logger.info(f"从 sheet '{s}' 读取 {len(df_sheet)} 条数据")
                df = pd.concat(frames, ignore_index=True)

                # 未匹配到 sheet 的分类，尝试从 ALL 中补充
                if unmatched:
                    logger.info(f"分类 {unmatched} 无对应 sheet，尝试从 'ALL' 补充")
                    if 'ALL' in sheet_names:
                        df_all = pd.read_excel(xf, sheet_name='ALL')
                        df_extra = df_all[df_all['classified'].astype(str).str.strip().isin(unmatched)]
                        if len(df_extra) > 0:
                            df = pd.concat([df, df_extra], ignore_index=True)
                            logger.info(f"从 'ALL' 补充 {len(df_extra)} 条")

                df = df.fillna("")
                logger.info(f"加载测试数据: {len(df)} 条 (来自 sheet: {matched_sheets + unmatched})")
                return df

        # 未指定分类 或 所有分类都没有对应 sheet → 回退到原有策略
        if 'ALL' in sheet_names:
            logger.info(f"从 'ALL' 汇总表读取数据")
            df = pd.read_excel(xf, sheet_name='ALL')
        elif len(sheet_names) == 1:
            df = pd.read_excel(xf, sheet_name=sheet_names[0])
        else:
            # 多个 sheet 但没有 ALL → 合并全部
            logger.info(f"合并 {len(sheet_names)} 个 sheet: {sheet_names}")
            frames = [pd.read_excel(xf, sheet_name=s) for s in sheet_names]
            df = pd.concat(frames, ignore_index=True)
            if 'id' in df.columns:
                df = df.drop_duplicates(subset='id', keep='first').reset_index(drop=True)

        df = df.fillna("")

        # 按分类过滤（兜底：当 categories 都没匹配到 sheet 时走这里）
        if categories and 'classified' in df.columns:
            before = len(df)
            df = df[df['classified'].astype(str).str.strip().isin(categories)].reset_index(drop=True)
            logger.info(f"按分类过滤: {categories} → {before} → {len(df)} 条")

        logger.info(f"加载测试数据: {len(df)} 条 (来自 {os.path.basename(path)})")
        return df

    _OVERFLOW_COLUMNS = {'node_traces', 'simplify_node_traces', 'all_answers'}

    @staticmethod
    def _split_long_text(text, max_len=32767):
        """将超长文本按双换行符 '\n\n' 拆分，尽量保证节点完整"""
        if len(text) <= max_len:
            return [text]

        chunks = []
        # 按双换行拆成语义块
        blocks = text.split('\n\n')
        current = ""

        for block in blocks:
            separator = "\n\n" if current else ""
            candidate = current + separator + block

            if len(candidate) <= max_len:
                current = candidate
            else:
                # 当前块放不下了
                if current:
                    chunks.append(current)

                # 如果单个 block 本身就超长，硬切
                if len(block) > max_len:
                    remaining = block
                    while len(remaining) > max_len:
                        chunks.append(remaining[:max_len])
                        remaining = remaining[max_len:]
                    current = remaining
                else:
                    current = block

        if current:
            chunks.append(current)

        return chunks if chunks else [text]

    @staticmethod
    def _expand_overflow_columns(df):
        """处理超长列内容，将其拆分扩展至后续相邻列 (例如 node_traces, node_traces_2)"""
        EXCEL_MAX_CELL = 32767
        df_out = df.copy()

        for col in DifyEvaluator._OVERFLOW_COLUMNS:
            if col not in df_out.columns:
                continue

            # 检查是否有超长内容
            str_col = df_out[col].fillna('').astype(str)
            max_len = str_col.apply(len).max()
            if max_len <= EXCEL_MAX_CELL:
                continue

            # 计算需要的最大分片数
            max_chunks = 1
            all_splits = []
            for val in str_col:
                parts = DifyEvaluator._split_long_text(val, EXCEL_MAX_CELL)
                all_splits.append(parts)
                max_chunks = max(max_chunks, len(parts))

            # 第一片写入原列，其余写入 col_2, col_3, ...
            first_parts = []
            overflow_data = {f"{col}_{i+2}": [] for i in range(max_chunks - 1)}

            for parts in all_splits:
                first_parts.append(parts[0])
                for i in range(max_chunks - 1):
                    overflow_col = f"{col}_{i+2}"
                    overflow_data[overflow_col].append(parts[i+1] if i+1 < len(parts) else "")

            df_out[col] = first_parts

            # 将溢出列插入到原列之后
            col_idx = list(df_out.columns).index(col)
            for i, (overflow_col, data) in enumerate(overflow_data.items()):
                df_out.insert(col_idx + 1 + i, overflow_col, data)

            overflow_count = sum(1 for parts in all_splits if len(parts) > 1)
            logger.info(f"列 '{col}' 有 {overflow_count} 行超长，已拆分为 {max_chunks} 列")

        return df_out

    @staticmethod
    def _sanitize_df(df):
        """清理数据用于 Excel 写入 (处理公式、溢出与长度截断)"""
        EXCEL_MAX_CELL = 32767
        TRUNCATE_SUFFIX = "\n...[内容过长，已截断]"

        # 先做溢出扩展
        df_out = DifyEvaluator._expand_overflow_columns(df)

        # 再做公式转义和兜底截断
        for col in df_out.columns:
            if df_out[col].dtype == object:
                def sanitize(val):
                    if not isinstance(val, str):
                        return val
                    if val.startswith("="):
                        val = " " + val
                    if len(val) > EXCEL_MAX_CELL:
                        val = val[:EXCEL_MAX_CELL - len(TRUNCATE_SUFFIX)] + TRUNCATE_SUFFIX
                    return val
                df_out[col] = df_out[col].map(sanitize)
        return df_out

    @staticmethod
    def _safe_to_excel(df, path):
        """安全写回单 Sheet Excel (向后兼容)"""
        df_out = DifyEvaluator._sanitize_df(df)
        df_out.to_excel(path, index=False)

    @staticmethod
    def _safe_to_excel_multi_sheet(df, path):
        """按 classified 拆分并安全写入多 Sheet Excel"""
        df_out = DifyEvaluator._sanitize_df(df)

        with pd.ExcelWriter(path, engine='openpyxl') as writer:
            # 写入 ALL 汇总表
            df_out.to_excel(writer, sheet_name='ALL', index=False)
            sheet_info = [f"ALL({len(df_out)})"]

            # 按 classified 拆分写入子表
            if 'classified' in df_out.columns:
                for name, group in df_out.groupby('classified', sort=False):
                    sheet_name = str(name)[:31]  # Excel sheet 名最多 31 字符
                    group.to_excel(writer, sheet_name=sheet_name, index=False)
                    sheet_info.append(f"{sheet_name}({len(group)})")

        logger.info(f"写入结果: {os.path.basename(path)} → {', '.join(sheet_info)}")

    @staticmethod
    def _collect_category_stats(df, row_status):
        """按 classified 列统计各分类运行状态"""
        if 'classified' not in df.columns:
            return []

        stats = {}
        for idx, row in df.iterrows():
            cat = str(row.get('classified', 'UNKNOWN')).strip()
            if cat not in stats:
                stats[cat] = {"name": cat, "total": 0, "ok": 0, "fail": 0, "skip": 0}
            stats[cat]["total"] += 1
            status = row_status[idx] if idx < len(row_status) else None
            if status == 'ok':
                stats[cat]["ok"] += 1
            elif status == 'fail':
                stats[cat]["fail"] += 1
            elif status == 'skip':
                stats[cat]["skip"] += 1

        # 保持原始出现顺序
        seen = []
        for cat in df['classified'].astype(str).str.strip():
            if cat not in seen:
                seen.append(cat)
        return [stats[cat] for cat in seen if cat in stats]

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
        """处理单个测试用例（支持单轮或多轮）"""
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
                predict, trace, simplify_trace = self._parse_result(result)
                all_answers = json.dumps([predict], ensure_ascii=False) if predict else "[]"
                return predict, trace, all_answers, simplify_trace
        else:
            # workflow 模式不支持多轮，取第一个输入
            query = input_data[0]
            result = self.tester.run(inputs={"text_input": query, "language": "zh-CN"})
            predict, trace, simplify_trace = self._parse_result(result)
            all_answers = json.dumps([predict], ensure_ascii=False) if predict else "[]"
            return predict, trace, all_answers, simplify_trace

    def _parse_result(self, result):
        if not result:
            return "[请求失败]", "", ""

        if "answer" in result:
            predict = result["answer"]
        elif "data" in result and "outputs" in result["data"]:
            outputs = result["data"]["outputs"]
            predict = outputs.get("text", str(outputs))
        else:
            predict = str(result)

        trace = ""
        simplify_trace = ""
        if result.get("traces"):
            parts = []
            nodes = []
            for t in result["traces"]:
                formatted = json.dumps(t['output'], ensure_ascii=False, indent=2)
                parts.append(f"[{t['node']}]:\n{formatted}")
                nodes.append(t['node'])
            trace = "\n\n".join(parts)
            simplify_trace = " -> ".join(nodes)

        return predict, trace, simplify_trace

    def _parse_multi_turn_result(self, result):
        """解析多轮对话结果为文本特征与原始输出"""
        if not result:
            return "[请求失败]", "", "[]", ""

        predict = result["final_answer"]

        # 收集所有轮次回答
        all_answers = []
        for r in result["rounds"]:
            all_answers.append(r["answer"])

        # traces：每轮用分隔线标记
        # 注意：不以 '=' 开头，避免 openpyxl 将其误判为 Excel 公式
        trace_parts = []
        simplify_trace_parts = []
        for r in result["rounds"]:
            query_short = r["query"][:30] + ("..." if len(r["query"]) > 30 else "")
            header = f"----- 第{r['round']}轮: {query_short} -----"
            if r["traces"]:
                nodes = []
                simp_nodes = []
                for t in r["traces"]:
                    formatted = json.dumps(t['output'], ensure_ascii=False, indent=2)
                    nodes.append(f"[{t['node']}]:\n{formatted}")
                    simp_nodes.append(t['node'])
                trace_parts.append(f"{header}\n" + "\n\n".join(nodes))
                simplify_trace_parts.append(f"{header}\n" + " -> ".join(simp_nodes))
            else:
                trace_parts.append(f"{header}\n[无节点轨迹]")
                simplify_trace_parts.append(f"{header}\n[无节点轨迹]")

        trace = "\n\n".join(trace_parts)
        simplify_trace = "\n\n".join(simplify_trace_parts)
        all_answers_json = json.dumps(all_answers, ensure_ascii=False)
        return predict, trace, all_answers_json, simplify_trace

    def _print_header(self, use_llm_eval, categories=None):
        logger.info(f"读取测试数据: {self.test_data_path}")
        print()
        status_llm = "开启" if use_llm_eval else "关闭"
        cat_info = ", ".join(categories) if categories else "全部"
        print(f"  Dify 批量评测 (并行 & LLM 校验: {status_llm})")
        print(f"  {'-'*40}")
        print(f"  模式:   {cfg.app_type.upper()}")
        print(f"  API:    {cfg.base_url}")
        print(f"  数据:   {os.path.basename(self.test_data_path)}")
        print(f"  分类:   {cat_info}")
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

    def _print_summary(self, total, success, skip, fail, elapsed, result_path, cat_stats=None):
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

        # 按分类输出统计
        if cat_stats:
            print()
            print(f"  分类统计")
            print(f"  {'分类':<20s} {'总计':>4s}  {'成功':>4s}  {'失败':>4s}  {'跳过':>4s}  {'通过率':>6s}")
            print(f"  {'-'*56}")
            for s in cat_stats:
                rate = f"{s['ok'] / s['total'] * 100:.0f}%" if s['total'] > 0 else "N/A"
                print(f"  {s['name']:<20s} {s['total']:>4d}  {s['ok']:>4d}  {s['fail']:>4d}  {s['skip']:>4d}  {rate:>6s}")
            print(f"  {'-'*56}")

        print()
        logger.info(f"评测完成: {result_path}")
        logger.info(f"总计 {total} | 成功 {success} | 跳过 {skip} | 失败 {fail} | 耗时 {elapsed_str}")
        if cat_stats:
            for s in cat_stats:
                rate = f"{s['ok'] / s['total'] * 100:.0f}%" if s['total'] > 0 else "N/A"
                logger.info(f"  [{s['name']}] 总计 {s['total']} | 成功 {s['ok']} | 失败 {s['fail']} | 跳过 {s['skip']} | 通过率 {rate}")

    @staticmethod
    def _progress_bar(current, total, width=20):
        if total == 0:
            return "[" + "-" * width + "] 0%"
        ratio = current / total
        filled = int(width * ratio)
        return f"[{'#' * filled}{'-' * (width - filled)}] {int(ratio * 100)}%"


def run_evaluate(use_llm_eval=False, categories=None):
    return DifyEvaluator().run_batch(use_llm_eval=use_llm_eval, categories=categories)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Dify Evaluation Script")
    parser.add_argument("--use-llm", action="store_true", help="Enable LLM evaluation")
    args = parser.parse_args()
    
    run_evaluate(use_llm_eval=args.use_llm)
