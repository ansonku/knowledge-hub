# Knowledge Hub

Knowledge Hub 使用 Vue、Django、PostgreSQL 與 Nginx。M1 加入帳號啟用、登入、雙因素驗證與角色權限。
產品規格見 [MVP 規格 v2.1](docs/docs/FINAL_MVP_SPEC_v2.1.md)。

## 啟動

在 Ubuntu 開發機準備 Docker Engine、Compose v2、OpenSSL、curl 和 Python 3。
Django 和 Node.js 的專案相依套件會在映像建置時安裝。

```bash
bash scripts/init-env.sh
docker compose up --build --wait
```

第一次執行會建立包含隨機憑證的 `.env`。已有 `.env` 時可跳過初始化。
如果主機透過 sudo 使用 Docker，把下列各處的 `docker compose` 改成 `sudo docker compose`，
並以 `sudo bash scripts/smoke.sh` 執行 smoke test。

開啟 `http://localhost:18080` 可查看系統狀態。Nginx 只在主機回環介面開放。
若需更換埠，請調整 `.env` 的 `HUB_PORT`。

## 測試

```bash
docker compose config --quiet
docker compose exec -T backend ruff check .
docker compose exec -T backend python manage.py makemigrations --check --dry-run
docker compose exec -T backend python manage.py test
bash scripts/smoke.sh
```

建置 Nginx 映像時會一併執行前端型別檢查。Smoke test 會檢查首頁、前端資產及健康端點，
並短暫重啟開發資料庫，驗證資料保留。自訂埠可傳入參數，例如 `bash scripts/smoke.sh http://localhost:18081`。

## Migration 與資料

後端容器啟動時會執行 `migrate`。M0 的初始 migration 是 `users/0001_initial.py`。
修改模型後，如需在本機產生 migration，可將後端目錄掛入一次性容器：

```bash
docker compose run --rm --user "$(id -u):$(id -g)" \
  --volume "$PWD/backend:/app" backend python manage.py makemigrations
```

`docker compose down` 停止服務並保留 PostgreSQL volume。加上 `-v` 會移除開發資料。

## M1 帳號與登入

啟動服務後，從部署主機建立第一位管理員。指令會互動提示輸入密碼。

```bash
docker compose exec backend python manage.py create_hub_admin <帳號名稱> <電子郵件>
```

在 [本機登入頁](http://localhost:18080/accounts/login/) 使用電子郵件和密碼登入。從「帳號管理」邀請使用者。使用者透過啟用信設定密碼，連結有效期為 24 小時，重寄會使舊連結失效。管理員亦可停用或重新啟用帳號、變更角色及寄送密碼重設信。停用會撤銷既有 Session。

- **開發郵件**。未配置 `SMTP_HOST` 時，郵件放於後端容器的 `/tmp/hub-mail`，重建容器會清除這些郵件。用 `docker compose exec backend ls -lt /tmp/hub-mail` 找到檔名，再於本機容器內查看對應郵件。郵件包含一次性連結，請在本機開發環境查看。
- **SMTP**。在 `.env` 設定 `SMTP_HOST`、`SMTP_PORT`、`SMTP_USERNAME`、`SMTP_PASSWORD`、`SMTP_USE_TLS` 與 `SMTP_FROM_EMAIL`。讓 `PUBLIC_ORIGIN` 對應使用者實際開啟的站台網址。
- **Google OIDC**。設定 `GOOGLE_CLIENT_ID` 和 `GOOGLE_CLIENT_SECRET` 後，使用者可從個人設定重新驗證並啟動綁定。Google OAuth 用戶端必須允許完整回呼網址，本機預設為 `http://localhost:18080/accounts/google/login/callback/`。若有更換開發埠，回呼網址也需更新。
- **雙因素驗證**。在個人設定以驗證器掃描 QR Code 並輸入動態密碼。啟用時請保存當次顯示的十組復原碼。無法使用驗證器和復原碼時，由管理員透過獨立管道核對身分並記錄理由後重設。正式部署前設定並安全保存 `MFA_ENCRYPTION_KEY`（Fernet 金鑰）。開發環境預設從 Django 密鑰衍生，變更金鑰時須先規劃現有驗證器資料的遷移。
- **HTTPS**。HTTPS 的 `PUBLIC_ORIGIN` 會啟用安全 Cookie，另請在 `DJANGO_ALLOWED_HOSTS` 保留 `127.0.0.1` 並加入對外的主機名稱。部署時入口代理必須覆寫可信的 `X-Forwarded-Proto`。對外開放前須驗證實際 Google 回呼、SMTP 寄達和入口代理設定。

修改 `.env` 後，執行 `docker compose up --build --wait` 套用設定。Google 回呼的自動化測試以模擬 Google 交換授權碼和驗證權杖執行，其餘流程由 Django 與 PostgreSQL 實際處理。

## M2 文件庫

登入後開啟 [知識總覽](http://localhost:18080/library/)。Admin 和 Editor 可管理分類與標籤、上傳 UTF-8 Markdown 或 HTML，以及更新指定文件的版本。Viewer 可讀取清單與下載原始檔。瀏覽器會逐檔上傳批次中的文件，因此其中一檔失敗時，其他檔案仍可成功儲存。批次中的每個成功項目各自建立一份文件和 v1。

開發環境預設每檔 50 MiB，每批最多 20 檔，可用 `DOCUMENT_MAX_BYTES` 和 `DOCUMENT_MAX_BATCH` 調整。提高單檔上限時，也要同步調整 Nginx 文件路徑的 `client_max_body_size`，並預留 multipart 表單額外大小。

文件原始內容存在 Compose 的 `document_data` volume。備份須同時包含這個 volume 和 PostgreSQL 的 `postgres_data`。HTML 由下載端點以附件提供。文件移入回收桶後會從清單和下載端點隱藏，所有版本仍保留。

可以用以下指令檢查版本檔和資料庫是否一致。若程序在發布檔案後、資料庫完成提交前中止，可加上 `--quarantine` 把沒有實際對應版本的檔案移到同一 volume 的隔離目錄。若有已提交版本缺檔，指令會回報並以失敗狀態結束。

```bash
docker compose exec backend python manage.py check_document_storage
```

## M3 Markdown 閱讀

從知識總覽點選 Markdown 文件標題進入閱讀頁。標準版面包含分類與文章目錄，寬版維持閱讀寬度，全頁使用可用空間。版面偏好儲存在瀏覽器。Viewer 可以閱讀、點選目錄和下載目前版本的原始檔。

Admin 和 Editor 可在 Markdown 閱讀頁切換至 Monaco 編輯器，或以分割模式查看即時預覽。儲存會新增版本並保留舊稿。若另一位使用者已更新目前版本，系統會顯示版本衝突並保留編輯區中的草稿。

### 本機 HTML 預覽

HTML 文件頁可開啟沙箱預覽，也可直接下載原始檔。預覽需要登入，並使用版本專屬的 60 秒一次性連結。iframe 和直接開啟連結收到的 HTML 都受沙箱限制。相容模式允許載入外部 HTTPS 資源，第三方服務可能收到連線資訊。

Compose 的 `LOCAL_HTML_PREVIEW` 預設供本機 HTTP 使用，可設為 `false` 關閉。只有 loopback 的 `PUBLIC_ORIGIN` 與請求主機可開啟預覽。HTTPS、對外主機和 Cloudflare 轉送的請求一律關閉。外部部署應使用實際的公開網址設定 `PUBLIC_ORIGIN`，保留附件下載。

Markdown 閱讀與分割預覽共用渲染器。支援表格、刪除線及唯讀任務清單，並可用 `mermaid` 程式碼區塊繪圖、以 `$...$` 或 `$$...$$` 顯示 KaTeX 公式。指定已支援的語言可顯示程式碼高亮。Mermaid 在只能載入本機靜態資產的沙箱中繪圖，頁面以圖片顯示結果。圖表無法繪製時會保留原始語法。

## M4 版本歷史

文件頁的「版本歷史」列出每個版本的作者、時間、更新說明和來源。可點選版本號閱讀舊版、下載原始檔，或勾選兩版使用 Monaco 比較。舊版 HTML 沿用本機手動開啟的沙箱預覽；公開站點可下載舊版附件。

Admin 和 Editor 可從舊版選擇還原。系統會複製舊版內容，建立下一版並記錄來源及操作者。若確認期間已有其他人更新目前版本，系統會要求重新確認。

## M5 搜尋與回收桶

知識總覽可搜尋標題、分類、標籤及目前版本正文。HTML 索引只擷取文字，略過腳本與樣式。PostgreSQL 全文搜尋處理詞彙比對，中文可用連續字串查詢。啟動後會補建舊文件目前版本的索引；若需手動重試，可執行 `docker compose exec backend python manage.py index_document_search`。

Admin 和 Editor 可在回收桶還原文件及所有版本。只有 Admin 可以永久刪除，必須打開確認視窗並輸入完整文件標題。移入回收桶、還原及永久刪除都會留下稽核紀錄。若檔案清理暫時失敗，系統保留清理工作，可在重新啟動環境時重試，或執行 `docker compose exec backend python manage.py finish_document_deletions`。
