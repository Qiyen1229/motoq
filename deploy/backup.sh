#!/bin/sh
# MotoQ 備份：SQLite 一致性快照 + 單據圖片，打包成 tar.gz，保留最近 N 份。
# 用法（於專案目錄，建議放進 NAS 的排程）：
#   ./deploy/backup.sh            # 備份到 ./data/backups
#   AGE_RECIPIENT=age1xxxx ./deploy/backup.sh   # 若已安裝 age，額外加密並刪除明文檔
set -eu
cd "$(dirname "$0")/.."
KEEP="${KEEP:-14}"

docker compose exec -T motoq python -m app.cli backup --out /data/backups --keep "$KEEP"

if [ -n "${AGE_RECIPIENT:-}" ] && command -v age >/dev/null 2>&1; then
  latest="$(ls -1t data/backups/motoq-backup-*.tar.gz | head -n 1)"
  age -r "$AGE_RECIPIENT" -o "$latest.age" "$latest" && rm -f "$latest"
  echo "encrypted: $latest.age"
fi
