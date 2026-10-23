#!/bin/sh
set -e

# 自動修正掛載資料夾權限（解決 NAS Volume UID 不一致導致的 readonly database 問題）
if [ -d "/data" ]; then
    chown -R motoq:motoq /data 2>/dev/null || true
    chmod -R 777 /data 2>/dev/null || true
fi

# 切換至 motoq 使用者執行主程序
exec gosu motoq "$@"
