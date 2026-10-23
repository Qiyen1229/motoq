# MotoQ Synology NAS 架設指南

本專案已預先建立好最高權限管理員帳號：
- **預設帳號**：`qiyen`
- **預設密碼**：請在 `.env` 的 `MOTOQ_DEFAULT_ADMIN_PASSWORD` 自行設定
- **預設權限**：`admin`（最高權限管理員，已啟用）

---

## 部署前確認

1. **連接埠（Port）**：預設使用 `9155`。
2. **連線模式（HTTP / HTTPS）**：
   - 若直接用 NAS 內網 IP（如 `http://192.168.x.x:9155`）或 Tailscale 存取：保持 `.env` 中的 `MOTOQ_COOKIE_SECURE=false`。
   - 若透過 Synology 內建反向代理伺服器掛載 HTTPS 憑證：請將 `.env` 中的 `MOTOQ_COOKIE_SECURE` 改為 `true`。

---

## 方法一：使用 Synology Container Manager（圖形介面，推薦）

### 步驟 1：上傳與解壓縮
1. 開啟 Synology DSM 的 **File Station**。
2. 進入 `docker` 共用資料夾（例如 `/docker`）。
3. 建立資料夾 `motoq`。
4. 將壓縮檔 `motoq-nas.zip` 內的所有檔案解壓縮至 `/docker/motoq` 目錄。
   > 確認目錄下包含 `docker-compose.yml`、`.env`、`Dockerfile`、`backend`、`frontend`、`data` 等檔案。

### 步驟 2：設定資料夾權限
因為容器內部以非 root 使用者（UID 1000）執行，需確保資料庫資料夾具備讀寫權限：
1. 在 File Station 中右鍵點擊 `motoq/data` 資料夾 $\rightarrow$ **內容** $\rightarrow$ **權限**。
2. 給予 `Everyone` 或目前管理者讀寫權限（或於 SSH 下輸入 `chmod -R 777 /volume1/docker/motoq/data`）。

### 步驟 3：建立並啟動專案
1. 開啟 DSM **Container Manager**。
2. 點選左側 **專案 (Project)** $\rightarrow$ **新增**。
3. 設定：
   - **專案名稱**：`motoq`
   - **路徑**：選擇剛才的 `/docker/motoq`
   - **來源**：選擇「使用現有的 docker-compose.yml 建立專案」
4. 點擊 **下一步** $\rightarrow$ **完成**。
5. Container Manager 將自動開始建置映像檔並啟動服務。

### 步驟 4：登入測試
- 瀏覽器開啟：`http://<NAS-IP>:9155`
- 輸入你在 `.env` 設定的管理員帳號與密碼登入。


---

## 方法二：使用 SSH 命令列（極速部屬）

### 步驟 1：連線與解壓縮
```bash
# 切換至 docker 目錄
cd /volume1/docker

# 解壓縮專案（若以 zip 上傳）
unzip motoq-nas.zip -d motoq
cd motoq
```

### 步驟 2：確認資料夾權限
```bash
# 確保資料庫目錄可被容器內 uid 1000 讀寫
chmod -R 777 ./data
```

### 步驟 3：一鍵建置並在背景啟動
```bash
docker compose up -d --build
```

### 步驟 4：檢查容器狀態與日誌
```bash
# 檢查運作狀態
docker compose ps

# 查看即時日誌
docker compose logs -f
```

---

## 常見問題與除錯排查

### 狀況 A：登入後立刻被跳回登入頁面
- **原因**：在非 HTTPS（HTTP 內網環境）下啟用了 Secure Cookie，導致瀏覽器拒絕儲存 Session Cookie。
- **解決方式**：確認 `.env` 檔案內設定為 `MOTOQ_COOKIE_SECURE=false`，並重啟容器：`docker compose restart`。

### 狀況 B：容器日誌出現 `sqlite3.OperationalError: unable to open database file`
- **原因**：宿主機的 `./data` 目錄沒有寫入權限。
- **解決方式**：在 NAS 終端機執行 `chmod -R 777 /volume1/docker/motoq/data` 後重啟容器。

### 狀況 C：忘記或需要重設管理員密碼
- **解決方式**：進入容器執行 CLI 重設指令：
  ```bash
  docker compose exec motoq python -m app.cli reset-password --username qiyen
  ```
