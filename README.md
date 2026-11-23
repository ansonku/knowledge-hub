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
