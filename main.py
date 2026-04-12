'''
Author: JimZhang
Date: 2026-04-09 01:56:22
LastEditors: 很拉风的James
LastEditTime: 2026-04-12 16:34:00
FilePath: /changshun_dify_test/main.py
'''
import argparse
import sys


def _select_categories():
    """交互提示用户选择要执行的测试分类"""
    from evaluate.evaluate import DifyEvaluator

    categories = DifyEvaluator.get_categories()
    if not categories:
        print("  未检测到分类信息，将测试所有用例。")
        return None

    total = sum(count for _, count in categories)
    print()
    print(f"  可用测试分类 (共 {total} 条用例)")
    print(f"  {'-'*40}")
    for i, (name, count) in enumerate(categories, 1):
        print(f"    {i}. {name:<20s} ({count} 条)")
    print(f"  {'-'*40}")
    print(f"  输入序号选择分类 (多个用逗号或空格分隔)")
    print(f"  直接回车 = 测试所有分类")
    print()

    try:
        raw = input("  请选择: ").strip()
    except (EOFError, KeyboardInterrupt):
        print("\n  已取消。")
        sys.exit(0)

    if not raw:
        return None

    # 解析输入：支持 "1,2,3" 或 "1 2 3" 或 "1, 3"
    raw = raw.replace(",", " ")
    selected = []
    for token in raw.split():
        try:
            idx = int(token)
            if 1 <= idx <= len(categories):
                selected.append(categories[idx - 1][0])
            else:
                print(f"  序号 {idx} 超出范围 (1-{len(categories)})，已忽略。")
        except ValueError:
            print(f"  无法识别输入 '{token}'，已忽略。")

    if not selected:
        print("  未选择有效分类，将测试所有用例。")
        return None

    # 去重并保留顺序
    seen = set()
    unique = []
    for cat in selected:
        if cat not in seen:
            seen.add(cat)
            unique.append(cat)

    selected_count = sum(count for name, count in categories if name in seen)
    print(f"\n  已选择: {', '.join(unique)} ({selected_count} 条用例)")
    return unique


def main():
    parser = argparse.ArgumentParser(
        description="Dify 测试工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python main.py                  # 单例测试（默认）
  python main.py --mode single    # 单例测试
  python main.py --mode batch     # 批量评测
        """
    )
    parser.add_argument(
        "--mode", "-m",
        choices=["single", "batch"],
        default="single",
        help="运行模式: single=单例测试(默认), batch=批量评测"
    )
    parser.add_argument(
        "--use-llm", action="store_true", help="在 batch 模式下，启用大模型比对评测"
    )
    parser.add_argument(
        "--category", "-c",
        nargs="*",
        default=None,
        help="指定测试分类 (如: --category SHOPPING PLOT)。不指定时交互式选择。"
    )

    args = parser.parse_args()

    if args.mode == "batch":
        from evaluate.evaluate import run_evaluate
        from config.config import cfg, logger
        logger.info(f"批量评测开始 [{cfg.run_timestamp}]")

        # 确定测试分类
        if args.category is not None:
            # 命令行已指定分类
            categories = args.category if args.category else None
        else:
            # 交互式选择
            categories = _select_categories()

        result_path = run_evaluate(use_llm_eval=args.use_llm, categories=categories)
        if result_path:
            logger.info(f"批量评测结束: {result_path}")
        else:
            logger.error("批量评测异常结束")
            sys.exit(1)

    elif args.mode == "single":
        from evaluate.single_test import run_single_test
        run_single_test()


if __name__ == "__main__":
    main()