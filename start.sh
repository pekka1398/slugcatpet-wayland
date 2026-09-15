#!/bin/bash
# 进入脚本所在目录
cd "$(dirname "$0")"

# 检查虚拟环境是否存在（按常见命名依次探测，认 bin/python 本身而非目录）
PYTHON_BIN="python3"
for venv in .venv venv_sys venv; do
    if [ -x "$venv/bin/python" ]; then
        PYTHON_BIN="./$venv/bin/python"
        break
    fi
done

# 启动桌宠
exec "$PYTHON_BIN" run_slugcatpet.py
