# AI Knowledge Hub

M0 提供本機開發用的 Vue、Django、PostgreSQL 與 Nginx 基礎架構。
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
