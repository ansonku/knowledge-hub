# AI Knowledge Hub — 最終 MVP 產品與技術規格書 v2.1

> 狀態：已確認的 MVP 開發基準｜日期：2026-11-23｜本機開發：Ubuntu 26.04 LTS｜正式部署：UGREEN DXP6800 Pro / UGOS Pro
>
> 此文件是開發規格，不代表系統已實作。未列為「已確認」的參數採建議預設值，正式對外上線前須完成安全與部署驗收。

## 1. 產品目標與範圍

打造多人共用的 AI 技術知識庫，集中管理 AI 產生的 HTML/Markdown 技術文章（例如 OpenBMC、AST2700、LTPI、FPGA、OP-TEE）。提供分類、標籤、全文搜尋、互動 HTML 閱讀、Markdown 編輯、不可變版本歷史、差異比較與還原。管理員可發布選定文章，讓訪客從首頁閱讀。正式站點 `https://hub.sharegram.cc`，透過 NAS 上既有 Cloudflare Tunnel 對外提供服務。

**MVP 不包含**：公開註冊、逐篇指定使用者或群組權限、即時多人共同編輯、內建 HTML 原始碼編輯器、AI 自動生成文章、原生手機 App、進階全文搜尋引擎。

## 2. 技術架構（已確認）

| 層級 | 技術 | 備註 |
|---|---|---|
| 開發主機 | Ubuntu 26.04 LTS | 取代先前 macOS 開發規劃；Docker Engine + Compose plugin |
| 前端 | Vue 3、TypeScript、Vite、PrimeVue | Vue Router、Pinia；Monaco Editor |
| 後端 | Python、Django、Django REST Framework | Session Auth、CSRF、後端 RBAC |
| 身分 | Django 密碼登入、Google OAuth 2.0/OIDC | django-allauth 或經審核的等效整合 |
| MFA | 選用 TOTP | 10 組一次性備援碼、管理員核准復原 |
| 資料庫 | PostgreSQL | 中繼資料、稽核、搜尋索引 |
| 入口 | Nginx | Vue SPA、API proxy、預覽入口 |
| 部署 | Docker Compose | Ubuntu 開發、NAS 正式環境共用核心設定 |
| 儲存 | Docker bind mount / volume | 文件不可變版本檔案與 DB 資料持久化 |

### 2.1 系統拓樸

```text
Ubuntu 26.04（開發）                     UGREEN NAS（正式）
Browser -> localhost:18080               Browser -> https://hub.sharegram.cc
           |                                           |
Docker Compose: Nginx                    Cloudflare Tunnel（NAS 主機既有）
  |-- Vue SPA                                         |
  |-- /api -> Django/DRF                     127.0.0.1:18080 -> Nginx
  |-- /accounts -> Django                    |-- Vue SPA
  `-- /preview -> Sandbox handler          |-- Django API / accounts
Django -> PostgreSQL                       `-- Preview handler
Django -> immutable file store             Django -> PostgreSQL + NAS files
Django -> SMTP                             Django -> SMTP / Google OIDC
```

開發環境以 `http://localhost:18080` 為建議入口；Google OAuth 在本機需配置合法測試 redirect URI，或使用獨立開發憑證。正式 Nginx 建議僅對 NAS 主機回環介面映射 `127.0.0.1:18080:80`，先檢查埠是否可用。Cloudflare Tunnel **沿用 NAS 主機既有 cloudflared**，不新增 cloudflared container。資料庫及 Django 服務不直接公開。

## 3. 使用者、登入與權限（已確認）

### 3.1 RBAC

| 操作 | Admin | Editor | Viewer |
|---|:---:|:---:|:---:|
| 閱讀、搜尋、下載 | ✓ | ✓ | ✓ |
| 新增、批次上傳 | ✓ | ✓ | — |
| 更新版本、Markdown 編輯 | ✓ | ✓ | — |
| 管理分類、標籤 | ✓ | ✓ | — |
| 歷史比較、預覽 | ✓ | ✓ | ✓ |
| 還原歷史版本 | ✓ | ✓ | — |
| 移入回收桶、從回收桶還原 | ✓ | ✓ | — |
| 永久刪除 | ✓ | — | — |
| 發布公開文章、發布新版與下架 | ✓ | — | — |
| 建立/停用帳號、變更角色 | ✓ | — | — |

登入後的文件庫採共享模式，Editor 可編輯所有文章。後端在每次 API 讀取與寫入、下載、預覽及還原時檢查權限。未登入訪客可透過公開端點閱讀已發布的文章。

### 3.2 帳號生命週期

1. Admin 建立帳號（Email 唯一），預設未啟用；**無公開註冊**。
2. 系統寄送**一次性、限時 Email 啟用連結**，建議有效期 24 小時；使用者自行設定密碼，完成啟用。重新寄送須使舊連結失效。
3. 登入可選 Django 密碼或 Google OAuth/OIDC；Google 驗證成功不代表可自動註冊或取得角色。
4. Google 帳號必須由**已登入的使用者**在個人設定啟動綁定，要求近期重新驗證；使用 Google 穩定識別碼 `sub` 綁定，**不得只憑 Email 相同自動合併**。
5. Admin 可停用/啟用帳號、變更角色、觸發密碼重設。停用帳號必須撤銷現有登入能力與有效 Session。
6. 使用者可修改顯示名稱、密碼、檢視/解除綁定登入方式；解除綁定不得導致完全無法登入。
7. 重要操作寫入 Audit Log，且通知安全相關變更。

### 3.3 TOTP MFA 與復原

- MFA 為**選用**；使用者掃描 QR Code、輸入有效 TOTP 後啟用。
- 啟用時發放 **10 組一次性備援碼**，只顯示一次；伺服器僅儲存安全雜湊/驗證值。
- 無論密碼登入或 Google 登入，只要帳號已啟用 MFA，均須通過本地 TOTP 或未使用的備援碼後才建立完整登入 Session。
- 遺失裝置與備援碼時，Admin 必須依**獨立身分核對程序**核准重設，記錄操作者、對象、理由、時間並通知當事人；重設不等於直接授予已完成 MFA 的 Session。
- TOTP Secret 需加密保存；驗證、復原碼及登入皆須限速。密碼重設、Google 綁定與部分驗證 Session 不得繞過 MFA。

## 4. 文件與分類（已確認）

- 支援 `.html`、`.md` UTF-8；保留原始檔案及內嵌 CSS/JS/base64。
- 樹狀分類、手動標籤；標題預填檔名並可編輯。分類為邏輯結構，移動分類不改變實體版本檔案路徑。
- 每篇文章有永久 `Document UUID`；每個版本有獨立 ID、版本號、檔案路徑、SHA-256、大小、建立者、時間、更新說明、來源、還原來源。
- 版本**不可變**，歷史不覆寫。格式在 MVP 固定：HTML 文章更新 HTML；Markdown 文章更新 Markdown。

### 4.1 批次新增

- 批次上傳**只新增文章**，每個檔案建立新的 Document UUID + v1。
- 不以同名檔案推斷為同一篇文章；不自動覆蓋或合併。
- 每檔驗證、顯示進度與成功/失敗；單檔失敗不回滾其他已成功檔案。
- 新文章若 SHA-256 與文件庫既有內容相同，提示重複，但不得靜默合併；是否新增由使用者明確選擇。

### 4.2 單篇更新版本

- 必須先進入指定文章，明確選擇「更新版本」；不得以檔名自動匹配。
- SHA-256 與**目前版本**完全相同：警告並**預設跳過**；使用者明確確認後可強制建立新版本。
- 版本更新需避免併發衝突、重複版本號、資料庫紀錄指向遺失檔案。
- 例：目前 v5，選擇還原 v2 → 建立新 v6（內容複製 v2），v1～v5 仍保留。
- 歷史介面提供時間軸、版本細節、Monaco Diff（文字版本）、安全預覽、下載、還原確認。

### 4.3 回收桶

- 刪除先移入回收桶，文件及**全部版本**保留；Admin/Editor 可還原。
- 僅 Admin 可永久刪除；永久刪除需二次確認及稽核。
- MVP 預設**不自動清空**回收桶。

### 4.4 文章公開與未登入閱讀（M6，已確認）

- 每篇文章可設為 `Private` 或 `Public`。既有文章遷移後與新上傳的文章都預設為 `Private`。`Private` 文章沿用登入後的共享文件庫權限。
- 首頁和 `/library/` 共用知識總覽。未登入訪客可搜尋與閱讀公開文章，登入入口位於右上角。每篇公開文章有可分享的固定網址。訪客只能讀取已發布標題及正文。原始檔下載、版本歷史、內部分類與標籤沿用登入後的權限。
- 只有 Admin 可發布、發布新版或下架。發布前介面須顯示即將公開的版號，經確認後才發布。Editor 可照既有權限編輯、上傳新版和還原內部版本。
- 公開狀態須綁定明確發布的版本和公開標題。內部版本、標題或還原結果更新後，公開頁維持原先發布的內容，直到 Admin 明確發布新版。
- 切回 `Private` 或移入回收桶時，首頁和公開查詢應立即移除該文章，舊的公開網址回傳 404。從回收桶還原時維持 `Private`。發布、發布新版、手動下架和移入回收桶時的下架均記錄操作者、文章、版號及時間。
- 公開列表、正文及查詢由獨立的公開端點提供，每次讀取都檢查發布狀態及回收桶狀態。`Private` 文章的內容、標題與存在性不得藉由公開清單、搜尋、回傳的中繼資料或直連洩漏。公開正文、列表與查詢回應設為 `Cache-Control: no-store`，CDN 跳過快取。
- 公開 Markdown 沿用現有閱讀器、目錄、Mermaid、KaTeX 和程式碼高亮。公開 HTML 由經清理的靜態閱讀版呈現標題、段落、表格等內容，移除可執行內容並阻止自動載入外部資源。靜態呈現可能與原始樣式或互動不同。可執行 HTML 預覽適用第 6 節的隔離驗收。

## 5. 閱讀與編輯介面（已確認）

| 模式 | 佈局 |
|---|---|
| 標準 Standard | 左分類導覽 + 中央文章 + 右側 TOC |
| 寬版 Wide | 隱藏左右側欄，限制閱讀最大寬度 |
| 完整頁 Full Page | 隱藏左右側欄，內容盡可能佔滿可用空間，保留工具列 |

閱讀頁右上角提供「閱讀版面」選單及快速最大化；偏好保存在使用者本機。HTML 預設 Full Page；Markdown 預設 Standard。

Markdown：View / Edit / Split；Monaco、GFM、Mermaid、KaTeX、語法高亮。儲存即建立新版本。HTML：保留互動內容，但 **MVP 不提供站內 HTML 原始碼編輯器**；修改後重新上傳版本。

## 6. HTML Sandbox 與外部資源（已確認方向，對外上線有安全閘門）

**已選方案**：同網域 `hub.sharegram.cc` 的嚴格 sandbox iframe；**預設相容模式**，允許 HTTPS 外部圖片、CSS、字型、JS/CDN 等資源。正式對外前必須安全驗收；若不通過，必須關閉可執行預覽或改用**不同 registrable domain** 的獨立預覽站點。

### 6.1 不可妥協的隔離規則

- iframe 使用 `sandbox="allow-scripts"`；**不可**加入 `allow-same-origin`，也不允許表單提交、彈窗、頂層導頁或下載能力（除非另外經安全設計審核）。
- **每個可執行的預覽 HTTP 回應本身**必須設置 CSP `sandbox allow-scripts`，確保直接開啟預覽 URL 時仍受 sandbox 約束；另限制 `form-action`、`base-uri`、`object-src`、frame/導航等能力並驗證瀏覽器實際行為。
- 不可用 Vue `v-html` 或未隔離 `srcdoc` 注入上傳 HTML；不可由 Nginx 公開 raw file alias。
- 每次預覽讀取須檢查文章/版本權限；短效授權只能限用途、限版本，不得把可重用憑證、Django Session、CSRF Token 注入 HTML/JS 或暴露在易洩漏 URL。
- 預覽 JS 不得取得主站同源權限或已驗證 API 權限。Opaque origin **不保證** Cookie 不會附在網路請求上；必須另做 CSRF、Origin、Fetch Metadata、Cookie 與 API 授權防護。
- 相容模式允許 HTTPS 外部資源，**不能保證阻止外部資料傳輸或第三方追蹤**；介面須顯示相容模式風險提示。

### 6.2 安全驗收測試

必測：直接開啟預覽 URL、iframe sandbox escape、XSS、惡意 HTML、CSRF/帶 Cookie 請求、未授權版本讀取、跨使用者權限、短效憑證洩漏、CSP、生效的外部資源政策、導頁、popup、下載、iframe 與父頁互動。**若無法驗證安全隔離，禁止對外啟用可執行 HTML Preview。**

## 7. 搜尋（已確認）

搜尋標題、分類、標籤與文章全文；HTML 先抽取可搜尋文字，不執行 JS。MVP 採 PostgreSQL 全文搜尋；中文斷詞與召回率需實測，必要時改善索引策略。內部搜尋遵守 RBAC 與回收桶可見性。M6 的公開查詢僅使用已發布標題與已發布版本的公開正文。

## 8. 資料模型與檔案配置（實作基準）

```text
User(id UUID, email UNIQUE, username, display_name, role, is_active, timestamps)
SocialAccount(user_id, provider='google', provider_uid=Google sub)
Category(id UUID, parent_id?, name, slug, sort_order)
Tag(id UUID, name UNIQUE)
Document(id UUID, title, format, category_id, tags[], current_version_id,
         visibility, published_version_id?, published_title?, published_at?,
         is_trashed, created_by, timestamps)
DocumentVersion(id UUID, document_id, version_number, storage_path,
                sha256, byte_size, change_note, source, restored_from_id?,
                created_by, created_at)
AuditLog(id UUID, actor_id, action, target_type, target_id,
         redacted_metadata, created_at)
```

`UNIQUE(document_id, version_number)`；自訂 User Model 必須在第一個 migration 前決定。建議路徑：`documents/<document_uuid>/versions/v0001.html`。版本檔案不可覆寫；以暫存檔 + 原子搬移、DB transaction、鎖定與失敗清理/對帳避免不一致。NAS 真實 bind mount 路徑須現場確認。

## 9. API 介面建議（供 Codex 設計，非已固定 URL 合約）

| 領域 | 端點示例 | 權限 |
|---|---|---|
| 登入 | `/accounts/`、`/api/auth/me` | 公開入口/已登入 |
| 帳號管理 | `/api/users/`、`/api/users/{id}/disable` | Admin |
| 分類與標籤 | `/api/categories/`、`/api/tags/` | 讀取全員；寫入 Admin/Editor |
| 文件 | `/api/documents/`、`/api/documents/{id}/` | 讀取全員；修改 Admin/Editor |
| 公開閱讀 | `/api/public/articles/`、`/api/public/articles/{id}/` | 訪客可讀取已發布且未下架的內容 |
| 發布與下架 | `/api/documents/{id}/publication/` | Admin，寫入須驗證 CSRF 並稽核 |
| 批次新增 | `/api/documents/batch-upload` | Admin/Editor |
| 更新版本 | `/api/documents/{id}/versions` | Admin/Editor |
| 版本比較/還原 | `/api/documents/{id}/versions/{version}/...` | 依操作 RBAC |
| 預覽與下載 | `/preview/...`、`/api/documents/{id}/download` | 已登入且有權限 |
| 搜尋/回收桶 | `/api/search`、`/api/trash` | 依操作 RBAC |
| 健康檢查 | `/api/health` | 不洩漏秘密或 DB 細節 |

API 要有分頁、驗證、錯誤格式、CSRF、速率限制、稽核與測試；以上路徑僅為建議，Codex 可在保持功能合約的前提下統一命名。

## 10. Ubuntu 26.04 LTS 開發環境（新增已確認）

**開發主機：Ubuntu 26.04 LTS**；優先使用 Docker Engine、Docker Compose plugin、Git、VS Code（選用）、Codex CLI。Python、Node、PostgreSQL、Nginx 優先在 container 內運行，避免主機環境污染。Dockerfile/Compose 應使用支援 Linux amd64 與 arm64 的映像，確認 NAS CPU 架構及映像相容性。

### 10.1 前置檢查

```bash
lsb_release -a
uname -m
git --version
docker --version
docker compose version
codex --version
```

如尚未安裝，先依各工具官方 Ubuntu 26.04 相容性說明安裝；**不要在未確認套件來源與支援版本前執行來源不明的安裝腳本**。將目前使用者加入 docker 群組等同授予高權限，需自行評估；也可使用 sudo 或 rootless Docker。

### 10.2 本機環境

- 建議使用 `compose.yaml` + `compose.dev.yaml`，正式環境 `compose.prod.yaml`；共用相同 Dockerfile 與主要服務設定。
- 開發入口 `http://localhost:18080`（可透過 `.env` 調整）。前端 HMR 可在容器內執行，必要時由 Nginx 代理 WebSocket。
- `.env` 與憑證不可 commit；提供 `.env.example`；測試用 SMTP catcher 可在 dev profile 啟用，正式使用實際 SMTP。
- `docker compose up -d --build`、`docker compose ps`、`docker compose logs -f` 等指令以實際生成的 Compose 設定為準。
- Google OAuth 的 localhost 測試與正式網域使用**不同** OAuth Client 設定；正式 redirect URI 依 allauth 實際路由設定。

## 11. 正式部署與備份（方向已確認，實際參數待驗證）

- NAS：UGREEN DXP6800 Pro、UGOS Pro；Docker Compose 啟動 Nginx、Django、PostgreSQL 與必要的預覽處理元件。
- `hub.sharegram.cc` -> NAS 主機既有 Cloudflare Tunnel -> `http://localhost:18080`；不重建 cloudflared。Cloudflare Tunnel 不等於 Cloudflare Access，登入由 Django 負責。
- HTTPS、Secure/HttpOnly/SameSite Cookie、CSRF、可信代理/Host、HSTS（正式確認後）、登入限速、敏感事件 Audit Log。
- 文件與 PostgreSQL 分別持久化及備份；資料庫備份需一致性快照或 pg_dump，文件與 DB 需可對應恢復；定期實測還原。
- 正式 NAS Bind Mount 目錄、UID/GID、權限、磁碟空間、18080 埠、SMTP 寄達率、Google OAuth callback 皆須驗證。

## 12. MVP 開發里程碑與驗收

| 階段 | 實作 | 最低驗收 |
|---|---|---|
| M0 Foundation | Repo、Docker Compose、Nginx、Vue、Django、PostgreSQL、health | Ubuntu 一鍵啟動、服務健康、基本 CI/測試 |
| M1 Auth/RBAC | Admin 建帳、Email 啟用、雙登入、Google 綁定、選用 TOTP/復原、RBAC | 未核准帳號不能登入；角色/API/雙登入 MFA 測試 |
| M2 Documents | 分類、標籤、批次新增、單篇更新、SHA-256、儲存一致性 | 批次逐檔結果、同名不覆蓋、相同內容預設跳過 |
| M3 Reader | 三種版面、Markdown View/Edit/Split、HTML Sandbox | 偏好記憶、編輯產生新版本、預覽隔離測試 |
| M4 History | 版本時間軸、Diff、預覽、還原 | 還原只新增版本、不可覆寫歷史 |
| M5 Search/Trash | 全文搜尋、回收桶、稽核 | 搜尋權限、刪除/還原/永久刪除測試 |
| M6 公開文章 | Public／Private、首頁公開清單、發布版號、下架與稽核 | 無痕視窗可閱讀已發布文章；Private、下架與未發布新版不出現在公開端點；HTML 以靜態正文公開 |
| M7 Deployment | NAS、Tunnel、備份、安全強化 | 正式域名、還原演練；可執行 HTML 預覽須通過安全閘門才可啟用 |

### 12.1 跨模組測試

- Django unit/integration/API permission tests；Vue component/E2E tests；Docker smoke test。
- 上傳惡意檔案、超限檔案、重複 SHA、併發版本、失敗中斷、DB/檔案復原。
- Google 未授權帳號、Email 自動綁定攻擊、TOTP 旁路、備援碼重放、Admin MFA 重設稽核。
- M6 公開首頁與直連、Private／回收桶文章的 404、Viewer 和 Editor 不可發布、未發布新版隔離、舊網址下架；公開 HTML 不執行腳本或自動載入外部資源。
- HTML Preview 直接導頁、惡意 JS、CSP、Cookie/CSRF、外部 HTTPS 資源與跨角色讀取。

## 13. 最後未定案事項與決策分類

### A. 不阻擋 Ubuntu 本機開發（採預設值）

| 項目 | MVP 預設 |
|---|---|
| 單檔大小 / 每批數量 | 50 MB / 20 檔，可配置 |
| 回收桶 | 不自動清空 |
| 中文搜尋 | PostgreSQL 起步，實測後改善 |
| 文件權限 | 登入後共享文件庫；每篇預設 Private，由 Admin 明確發布到首頁 |
| Email 啟用連結 | 24 小時、一次性、重新寄送失效 |
| API 路徑、細部 UI 文案 | 由實作統一，需維持行為與權限 |

### B. 正式部署前必須填入/驗證

1. NAS 真實 bind mount 目錄、權限與容量；Ubuntu/NAS CPU 架構及 container image 相容性。
2. NAS `18080` 埠與既有 Cloudflare Tunnel 路由。
3. SMTP 服務商、寄件網域與 Email deliverability。
4. Google OAuth Client ID/Secret、授權網域與 callback URI。
5. 備份頻率、保留期限、異地備份策略及實際還原演練。
6. 管理員身分核對與 MFA 重設作業流程（SOP）；正式環境密鑰輪替、登入限速與告警。

### C. **可執行 HTML 預覽的對外啟用閘門**

**同網域可執行 HTML Preview 的安全驗收**。若測試不能證明隔離足夠，必須停用對外 JS Preview，或遷移至不同 registrable domain 的獨立預覽站點；不得因相容模式而放寬此要求。

## 14. Codex CLI 開發規範

- Codex 每次先閱讀 `AGENTS.md`、本規格、架構及計畫；**一次只做一個里程碑**。
- 先列變更計畫，再實作；補測試、執行測試、回報通過/失敗與未完成風險。
- 不可擅自變更已定案的權限、雙登入、版本不可變、批次只新增、Sandbox 規則。
- 未完成的安全設計不得標示「已安全」或直接部署公開。
- 任何 `.env`、SMTP/OAuth 密鑰、TOTP Secret、Recovery Code 不得寫入版本庫或日誌。

**M0 建議交付指令：**

```text
請先閱讀 AGENTS.md、docs/PRD.md、docs/ARCHITECTURE.md 與
 docs/IMPLEMENTATION_PLAN.md。開發主機為 Ubuntu 26.04 LTS。
只實作 M0 Foundation：Docker Compose、Django/DRF、Vue 3/TS/Vite/
PrimeVue、PostgreSQL、Nginx、Health Check、.env.example、README、
基礎測試。開發入口預設 http://localhost:18080。
先提出檔案與實作計畫，再建立程式碼；完成後執行測試並報告。
不要提前實作 M1～M7，也不要修改已確認的 MVP 產品決策。
```

---

**版本紀錄**：v2.0 確認安全規格與 Codex 文件；v2.1 更新 Ubuntu 26.04 開發環境，合併完整產品需求、安全驗收、部署條件與 Codex 開發交付標準。MVP 後續決議納入 M6 公開文章，原部署工作順延至 M7。
