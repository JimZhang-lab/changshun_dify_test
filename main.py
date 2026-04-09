'''
Author: JimZhang
Date: 2026-04-09 01:56:22
LastEditors: JimZhang
LastEditTime: 2026-04-09 12:55:00
FilePath: /changshun_dify_test/main.py
'''
import argparse
import sys


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

    args = parser.parse_args()

    if args.mode == "batch":
        from evaluate.evaluate import run_evaluate
        from config.config import cfg, logger
        logger.info(f"批量评测开始 [{cfg.run_timestamp}]")
        result_path = run_evaluate()
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