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

開啟 `http://localhost:18080`：已登入的成員會進入工作區 `/app/`，訪客會看到公開知識站 `/articles/`。Nginx 只在主機回環介面開放。
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

第一次啟動、系統裡還沒有管理員時，打開網站會進入**首次設定精靈**（`/setup/`）：介紹系統、確認授權與開發者資訊、建立第一位管理員、網站基本設定與系統檢查，完成後以新管理員進入管理中心。

- 服務啟動後一小時內可以直接設定。超過一小時需要輸入設定碼；設定碼只寫在主機的檔案中（後端記錄只寫出檔案位置）：

  ```bash
  docker compose exec backend cat /var/lib/knowledge-hub/documents/setup-code.txt
  ```

  重新啟動服務會重新開放一小時，並產生新的設定碼。設定完成後設定碼立即失效。
- 也可以不用瀏覽器，直接在主機上建立第一位管理員（指令會互動提示輸入密碼，同樣會讓設定碼失效）：

  ```bash
  docker compose exec backend python manage.py create_hub_admin <帳號名稱> <電子郵件>
  ```

版本、開發者、授權與條款在管理中心的「關於」頁（內容來自 `backend/hub/about.py` 與 `backend/hub/terms.md`）。

在 [本機登入頁](http://localhost:18080/accounts/login/) 使用電子郵件和密碼登入。從「帳號管理」邀請使用者。使用者透過啟用信設定密碼，連結有效期為 24 小時，重寄會使舊連結失效。管理員亦可停用或重新啟用帳號、變更角色及寄送密碼重設信。停用會撤銷既有 Session。

- **開發郵件**。未配置 `SMTP_HOST` 時，郵件放於後端容器的 `/tmp/hub-mail`，重建容器會清除這些郵件。用 `docker compose exec backend ls -lt /tmp/hub-mail` 找到檔名，再於本機容器內查看對應郵件。郵件包含一次性連結，請在本機開發環境查看。
- **SMTP**。在 `.env` 設定 `SMTP_HOST`、`SMTP_PORT`、`SMTP_USERNAME`、`SMTP_PASSWORD`、`SMTP_USE_TLS` 與 `SMTP_FROM_EMAIL`。讓 `PUBLIC_ORIGIN` 對應使用者實際開啟的站台網址。
- **Google OIDC**。設定 `GOOGLE_CLIENT_ID` 和 `GOOGLE_CLIENT_SECRET` 後，使用者可從個人設定重新驗證並啟動綁定。Google OAuth 用戶端必須允許完整回呼網址，本機預設為 `http://localhost:18080/accounts/google/login/callback/`。若有更換開發埠，回呼網址也需更新。
- **雙因素驗證**。在個人設定以驗證器掃描 QR Code 並輸入動態密碼。啟用時請保存當次顯示的十組復原碼。無法使用驗證器和復原碼時，由管理員透過獨立管道核對身分並記錄理由後重設。正式部署前設定並安全保存 `MFA_ENCRYPTION_KEY`（Fernet 金鑰）。開發環境預設從 Django 密鑰衍生，變更金鑰時須先規劃現有驗證器資料的遷移。
- **HTTPS**。HTTPS 的 `PUBLIC_ORIGIN` 會啟用安全 Cookie，另請在 `DJANGO_ALLOWED_HOSTS` 保留 `127.0.0.1` 並加入對外的主機名稱。部署時入口代理必須覆寫可信的 `X-Forwarded-Proto`。對外開放前須驗證實際 Google 回呼、SMTP 寄達和入口代理設定。

修改 `.env` 後，執行 `docker compose up --build --wait` 套用設定。Google 回呼的自動化測試以模擬 Google 交換授權碼和驗證權杖執行，其餘流程由 Django 與 PostgreSQL 實際處理。

## M2 文件庫

登入後開啟 [全部文件](http://localhost:18080/app/library/)。Admin 和 Editor 可管理集合與標籤、上傳 UTF-8 Markdown 或 HTML（可直接把檔案拖進視窗），以及從文件頁或清單列選單更新指定文件的版本。Viewer 可讀取清單與下載原始檔。上傳匣會逐檔上傳，因此其中一檔失敗時，其他檔案仍可成功儲存。每個成功上傳的檔案各自建立一份文件和 v1。

單一檔案的上限由 Admin 在「管理 › 系統狀態 › 儲存空間」設定（Markdown 1～50 MB、HTML 1～100 MB、圖片 1～30 MB、影片 10 MB～1 GB；預設 50、50、10、200 MB），瀏覽器在送出前檢查，伺服器也會再檢查。Nginx 的 `client_max_body_size` 已涵蓋各類範圍的上端，不需要隨設定調整。每批最多 20 檔，可用 `DOCUMENT_MAX_BATCH` 調整。

文件原始內容存在 Compose 的 `document_data` volume。備份須同時包含這個 volume 和 PostgreSQL 的 `postgres_data`。Markdown 中嵌入的影片也在同一個 volume 的 `videos/` 目錄（單檔上限由 Admin 設定，預設 200 MB、最大 1 GB），會讓備份明顯變大。完整的目錄結構、命名規則與清理方式見 [ARCHITECTURE.md 的 File storage](docs/docs/ARCHITECTURE.md#file-storage)。

影片由 Nginx 送出：Django 檢查權限後回應 `X-Accel-Redirect`，Nginx 從內部路徑 `/_protected/videos/` 送檔並處理 Range，播放器才能拖動進度。Nginx 只以唯讀方式掛載 `document_data` 的 `videos/` 子目錄（Compose 的 volume `subpath`，需要 Docker Compose 2.23 以上）；後端服務啟動時會先建立這個目錄。兩個容器透過 gid 2101 的 `media` 群組共用讀取權限，影片目錄為 `0750`、檔案為 `0640`，其他文件檔案 Nginx 讀不到。HTML 由下載端點以附件提供。文件移入回收桶後會從清單和下載端點隱藏，所有版本仍保留。

可以用以下指令檢查版本檔和資料庫是否一致。若程序在發布檔案後、資料庫完成提交前中止，可加上 `--quarantine` 把沒有實際對應版本的檔案移到同一 volume 的隔離目錄。若有已提交版本缺檔，指令會回報並以失敗狀態結束。

```bash
docker compose exec backend python manage.py check_document_storage
```

## M3 Markdown 閱讀

從文件清單點選標題進入文件頁 `/app/docs/<id>/`。正文以適合閱讀的寬度顯示，右側資訊面板提供本頁目錄、版本、活動，以及 Admin 的公開設定。Viewer 可以閱讀、點選目錄和下載目前版本的原始檔。

Admin 和 Editor 可在 Markdown 閱讀頁切換至 Monaco 編輯器，或以分割模式查看即時預覽。儲存會新增版本並保留舊稿。若另一位使用者已更新目前版本，系統會顯示版本衝突並保留編輯區中的草稿。

### 本機 HTML 預覽

HTML 文件頁預設會自動載入沙箱預覽，可用「自動載入」開關改成按鈕載入（設定記在各自的瀏覽器），也可直接下載原始檔。預覽需要登入，並使用版本專屬的 60 秒一次性連結。iframe 和直接開啟連結收到的 HTML 都受沙箱限制。相容模式允許載入外部 HTTPS 資源，第三方服務可能收到連線資訊。

Compose 的 `LOCAL_HTML_PREVIEW` 預設供本機 HTTP 使用，可設為 `false` 關閉。只有 loopback 的 `PUBLIC_ORIGIN` 與請求主機可開啟預覽。HTTPS、對外主機和 Cloudflare 轉送的請求一律關閉。外部部署應使用實際的公開網址設定 `PUBLIC_ORIGIN`，保留附件下載。

Markdown 閱讀與分割預覽共用渲染器。支援表格、刪除線及唯讀任務清單，並可用 `mermaid` 程式碼區塊繪圖、以 `$...$` 或 `$$...$$` 顯示 KaTeX 公式。指定已支援的語言可顯示程式碼高亮。Mermaid 在只能載入本機靜態資產的沙箱中繪圖，頁面以圖片顯示結果。圖表無法繪製時會保留原始語法。

## M4 版本歷史

文件頁資訊面板的「版本」分頁列出每個版本的作者、時間、更新說明和來源。可開啟舊版、下載原始檔，或勾選兩版開啟比較頁 `/app/docs/<id>/compare/`。舊版 HTML 沿用本機手動開啟的沙箱預覽；公開站點可下載舊版附件。

Admin 和 Editor 可從舊版選擇還原。系統會複製舊版內容，建立下一版並記錄來源及操作者。若確認期間已有其他人更新目前版本，系統會要求重新確認。

## M5 搜尋與回收桶

文件清單與 Ctrl／⌘K 指令面板可搜尋標題、集合、標籤及目前版本正文。HTML 索引只擷取文字，略過腳本與樣式。PostgreSQL 全文搜尋處理詞彙比對，中文可用連續字串查詢。啟動後會補建舊文件目前版本的索引；若需手動重試，可執行 `docker compose exec backend python manage.py index_document_search`。

Admin 和 Editor 可在回收桶 `/app/trash/` 還原文件及所有版本，也可批次還原。只有 Admin 可以永久刪除（從每列的「⋯」選單），必須輸入完整文件標題。移入回收桶、還原及永久刪除都會留下稽核紀錄。若檔案清理暫時失敗，系統保留清理工作，可在重新啟動環境時重試，或執行 `docker compose exec backend python manage.py finish_document_deletions`。

## 介面

- **工作區 `/app/`**（登入後）：首頁、全部文件、最近閱讀、收藏、集合、已公開文章、回收桶、個人設定 `/app/settings/`，以及 Admin 的成員管理 `/app/admin/members/`。支援跟隨系統／淺色／深色外觀和 Ctrl／⌘K 指令面板。
- **公開知識站 `/articles/`**（不需登入）：左側集合樹、搜尋、最新文章、熱門文章與依集合瀏覽，文章頁為 `/articles/<id>/`。站名與標語由 Admin 在個人設定的「站台」設定。
- **成員閱讀入口 `/read/`**（登入後）：與公開站相同的閱讀版面，但列出所有不在回收桶的文件（含內部文件），每篇標示「公開」或「內部」，並可跳回工作區編輯。工作區側欄的「閱讀入口」可進入。
- 登入、密碼、雙因素驗證與 Google 綁定仍是 Django 頁面，樣式已改成與新介面一致。
- 改版的規劃與實作紀錄見 [UI_REDESIGN.md](docs/docs/UI_REDESIGN.md)。

## M6 公開文章

既有及新上傳文章預設為 Private。Admin 可從文件頁資訊面板的「公開」分頁，或清單列選單的「公開設定」選擇版本、檢視原稿並確認發布。未登入訪客可在公開知識站搜尋公開標題或正文，也可使用文章的固定網址閱讀。登入後可使用內部分類、標籤、檔案下載與版本歷史，管理操作依角色開放。

公開頁固定顯示確認發布時的標題和版本。內部改名、編輯、上傳及還原版本會保留原公開內容，直到 Admin 再次發布。下架或移入回收桶後，固定網址會回傳 HTTP 404。從回收桶還原的文章維持 Private。

公開 HTML 保留靜態文字和基本排版，可保留 SVG 向量圖及圖表所需的 Grid、Flex 排版與配色，並移除腳本及會自動載入外部資源的元素。公開文章與查詢回應包含 `Cache-Control: no-store`。NAS 部署若使用 CDN，自訂快取規則須略過 `/articles/` 與 `/api/public/`。

### 熱門文章

訪客開啟公開文章時，瀏覽器會送出一次計數；同一個瀏覽器同一天同一篇只算一次。伺服器只保存「文章、日期、次數」，不記錄 IP、不設 Cookie；每個來源每小時最多計 120 次（以 Nginx 提供的真實來源判斷，只在快取暫存雜湊值）。成員在工作區或 `/read/` 的閱讀不計入。公開首頁顯示最近 30 天的前 5 名（至少 3 篇有瀏覽才顯示），不顯示次數；Admin 可在文件頁「公開」分頁看 30 天趨勢。
