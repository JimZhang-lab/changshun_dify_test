#!/bin/bash
# 批量评测启动脚本
cd "$(dirname "$0")/.." || exit 1
python3 main.py --mode batch
