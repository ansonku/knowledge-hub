# Knowledge Hub 介面改版規劃

狀態：P1、P2 完成並通過驗證，P2 待使用者審閱後 push（2026-11-24）· 分支：`ui-redesign` · Mockup：[Knowledge Hub 改版 Mockup](https://claude.ai/artifact/31WMjnFJBKW53DTCnq1vjr)（私人連結，需由擁有者分享）

本文件記錄介面改版的討論結論、mockup 內容與實作分期。改版只涉及前端呈現與資訊架構；後端 RBAC、HTML 沙箱與公開發布語意維持 `FINAL_MVP_SPEC_v2.1.md` 的規定，不因本規劃放寬。

## 1. 現況問題

依 M6 與「整站介面改版」後的前端（`frontend/src/*.vue`）盤點：

1. **沒有共用的 App Shell。** 每頁各自實作 `site-header`，導覽內容不一致：知識總覽有個人設定／帳號管理／登出，閱讀頁、版本歷史與回收桶只有「知識總覽」，帳號管理以 `<a href="/">` 整頁重載。進入文件後失去帳號選單與所在位置。
2. **功能入口分散且過深。** 回收桶與分類標籤管理是知識總覽標題旁的按鈕，帳號管理在頁首。「管理文件」對話框同時承擔改資料、公開設定、新增版本與移入回收桶；閱讀頁內無法執行這些操作。
3. **文件頁結構鬆散。** 版面選單、最大化、版本歷史（純文字連結）與下載混在同一列；左側「分類導覽」僅一兩個連結且與麵包屑重複；版本歷史是獨立頁、比較是彈窗，三者沒有被視為同一份文件的不同面向。
4. **清單能力不足。** 分類以全形空白模擬縮排，無法收合、無文件數；表格 7 欄、最小寬度 49rem，不能排序或批次選取；分頁只有上一頁／下一頁；上傳需先選「單檔／批次」模式。
5. **訪客與成員共用同一張管理表格。** 公開文章沒有摘要與日期，左欄只有「全部文件」。
6. **視覺與回饋細節。** 已定義 `--hub-*` token 但各頁仍寫死色碼；`darkModeSelector: false`；字型僅 `system-ui`，未指定中文字型；成功訊息常駐不消失；危險操作以「按兩次按鈕」確認。

## 2. 產品定位：三個介面

| 介面 | 對象 | 參考方向 | 設計重點 |
|---|---|---|---|
| 工作區 `/app/` | Viewer／Editor／Admin | Notion、Confluence、Outline | 資訊密度高、操作快、以文件為中心 |
| 公開知識站 `/` | 未登入訪客 | GitBook、Mintlify | 適合閱讀、品牌感、利於搜尋引擎、方便分享 |
| 管理主控台 `/app/admin/` | Admin（部分 Editor） | Linear 設定頁、GitHub Settings | 結構清楚、可稽核、危險操作明確隔離 |

三者共用設計 token，但版型、字級與密度各自獨立。

## 3. 資訊架構與路由

新介面在改版期間掛在 `/app/` 之下，與現有路由並存（見第 9 節）。

| 區域 | 路由 | 說明 |
|---|---|---|
| 工作區首頁 | `/app/` | 繼續閱讀、團隊最近更新、需要注意事項、集合概覽 |
| 全部文件 | `/app/library/` | 可排序、批次選取、每列「⋯」選單；篩選條件反映在網址 |
| 集合 | `/app/collections/:id/` | 集合說明加文件清單（取代「分類」的命名） |
| 文件 | `/app/docs/:id/` | 閱讀／編輯／分割預覽，右側 Inspector |
| 版本比較 | `/app/docs/:id/compare/?from=&to=` | 獨立整頁，可分享連結 |
| 已公開文章 | `/app/published/` | 公開版本與內部最新版本並列，標示落後 |
| 回收桶 | `/app/trash/` | 表格形式，支援批次還原 |
| 管理主控台 | `/app/admin/members/`、`/app/admin/taxonomy/`、`/app/admin/audit/`、`/app/admin/system/` | 見第 6 節 |
| 個人設定 | `/app/settings/` | 由頭像選單進入 |
| 公開站 | `/`、`/articles/:id/` | 獨立的 `PublicLayout` |

Django 範本頁面（登入、密碼重設、MFA、Google 綁定）維持由後端提供，只套用一致的品牌樣式。

## 4. 工作區設計

### 4.1 App Shell（三欄）

```
┌────────┬──────────────────────────────────────┬─────────────────┐
│ ◆ Hub  │ 技術 / 後端                     ☆  ⋯  │ 資訊 版本 公開 活動│
│ 🔍 ⌘K  │ API 設計規範                          │ 狀態  ● 公開 v5  │
│ 首頁    │ Markdown · v7 · 陳怡君 · 3 天前        │       ⚠ 落後 2 版│
│ 全部文件 │ ──────────────────────────────────── │       [發布 v7]  │
│ 最近閱讀 │   正文（閱讀字級 17px，行寬 72ch）      │ 集合  技術/後端   │
│ 收藏    │                                      │ 標籤  API  規範   │
│ 集合 ▾  │                                      │ 本頁目錄          │
│ 已公開   │                                      │                 │
│ 回收桶   │                                      │                 │
│ 管理    │                                      │                 │
│ (頭像)  │                                      │                 │
└────────┴──────────────────────────────────────┴─────────────────┘
```

- **左側欄：** 品牌、⌘K 搜尋入口、首頁／全部文件／最近閱讀／收藏、集合樹（圖示、文件數、可收合、未分類）、已公開文章（顯示落後數）、回收桶、管理主控台、頭像選單（個人設定、登出）。依角色隱藏無權限項目，僅為整潔，權限仍由後端判斷。
- **中欄：** 只放內容本身。窄螢幕時左側欄堆疊或收合為抽屜。
- **右側 Inspector：** 與目前文件有關的資訊與操作，可收合。

### 4.2 文件頁

- 頂列：麵包屑、收藏、「公開設定」（開啟 Inspector 的公開分頁）、「編輯」（主要按鈕）、「⋯」（新增版本、下載原始檔、移入回收桶）、Inspector 開關。
- 標題區：標題、格式、版本、公開狀態（含「落後 N 版」）、最後更新者與時間。
- 檢視模式：閱讀／編輯／分割預覽的分段控制。編輯時上方顯示「尚未儲存的變更」、更新說明輸入框、「儲存為 vN」。
- 版面：拿掉左側分類欄（App Shell 已提供），版面寬度切換縮成單一圖示按鈕。
- **Inspector 分頁：**
  - 資訊：集合、標籤可直接編輯；格式與大小；建立與更新者；本頁目錄。
  - 版本：垂直時間軸（版本號、目前版本／公開中標記、更新說明、作者與來源、時間）。勾選兩個版本後出現「比較 vA → vB」，比較結果以整頁差異檢視顯示。可從此處還原（Editor 以上）。
  - 公開（Admin）：狀態卡顯示公開版本、內部最新版本與落後數；公開網址與複製；選擇要發布的版本；「比較公開版與最新版」；「發布 vN…」仍需確認步驟；下架放在分隔後的危險區。
  - 活動：此文件的上傳、編輯、還原、發布與標籤異動紀錄。
- HTML 文件：沿用現有沙箱 iframe（`sandbox="allow-scripts"` 與獨立預覽網址）及相容模式警示，不改變安全邊界。

### 4.3 工作區首頁

- 標題區：日期、問候、「新增 Markdown」、「上傳文件」。
- 繼續閱讀：最近開啟的 4 份文件卡片。
- 團隊最近更新：活動流，可篩選「全部／我的／發布」，顯示更新說明。
- 需要注意：公開文章落後內部版本的數量與清單、回收桶文件數。
- 集合概覽：各集合說明與文件數。

### 4.4 文件清單

- 標題區：文件數、集合數、「上傳」。
- 篩選列：搜尋框、集合／格式／標籤／可見性／更新者等 facet 下拉、排序。條件寫入網址，可存成「已儲存的檢視」（後續）。
- 表格欄位：選取、文件（格式圖示、標題、集合路徑）、標籤、可見性（公開／私人／公開·落後）、版本、更新（時間與更新者）、「⋯」選單。
- 批次操作列：勾選後浮出，提供移動到集合、加標籤、下載、移入回收桶、取消選取。
- 分頁：顯示筆數範圍與頁碼。
- **上傳匣：** 檔案拖入視窗任何位置即開始上傳，右下角非模態面板顯示每個檔案的進度、完成狀態與重複檔處理（略過／仍要新增）；依檔案數自動判斷單檔或批次，不再需要模式切換。新增版本仍需從指定文件發起，維持「不以檔名自動配對版本」的規定。

### 4.5 指令面板（⌘K）

搜尋文件並可直接執行動作（上傳、前往回收桶、切換集合、開啟設定）。第一階段僅搜尋文件與導覽。

## 5. 公開知識站

- 頁首：品牌、公開集合連結、「成員登入」。
- 首屏：標題、說明、大型搜尋框。
- 依集合瀏覽：集合卡片（說明、文章數）。
- 最新文章：集合標籤、發布日期、預估閱讀時間、標題、摘要；可依集合篩選。
- 文章頁：左側集合目錄、正文、右側本頁目錄；底部上一篇／下一篇、複製連結、更新日期。移除「標準／寬版／全頁」選單，改用單一良好預設。
- 公開 HTML 維持靜態閱讀版與 `sandbox=""`。
- SEO meta 與 Open Graph 需要後端輸出，與 `backend/documents/public_html.py` 一併評估。

## 6. 管理主控台

| 頁面 | 內容 |
|---|---|
| 成員 | 搜尋、依角色或狀態篩選；邀請改為右側滑出面板；成員詳細頁分「資料／安全／活動」 |
| 集合與標籤 | 樹狀拖拉編輯、合併標籤、顯示使用次數 |
| 發布管理 | 所有公開文章，公開版本與內部最新版本並列並標示落後 |
| 稽核紀錄 | 整合帳號、還原、刪除、發布等紀錄，可篩選與匯出 |
| 系統狀態 | 儲存空間、搜尋索引狀態、待處理的刪除工作 |

停用帳號、重設 MFA 等操作統一放在頁面底部的危險區，並保留現有的身分核對與理由欄位。

## 7. 視覺系統

| 項目 | 規格 |
|---|---|
| 字型 | `Inter`, `Noto Sans TC`, system-ui；程式碼 `JetBrains Mono` |
| 字級 | 工作區介面 14px；閱讀正文 17px、行高 1.8、行寬 72ch；頁面標題 26–32px |
| 間距與圓角 | 8pt 網格；按鈕與輸入框圓角 8px、卡片 12px |
| 底色 | 側欄 `#F5F6F8`、內容 `#FFFFFF`、次層 `#F9FAFB`／`#FCFCFD` |
| 文字 | 主文字 `#101828`、次要 `#344054`、輔助 `#5D6B82` |
| 邊框 | `#E4E7EC`、輸入框 `#D0D5DD` |
| 主色 | `#1D4ED8`，懸停 `#1A3FB0`，淡底 `#EEF3FF`／`#E6ECFB` |
| 狀態色 | 公開 `#067647` on `#E7F6EE`；落後 `#8A4B00` on `#FFF1D6`；私人 `#344054` on `#F2F4F7`；危險 `#B42318` |
| 集合色 | 技術藍、產品橘 `#9A3D0A` on `#FDE7D6`、營運綠 `#0B6B45` on `#D8F3E6` |

- 所有色值收斂為 CSS token，並對應到 PrimeVue Aura preset；提供深色模式。
- 文字對比至少 4.5:1；觸控目標至少 44px；圖示按鈕必須有 `aria-label`。
- 共用元件：PageHeader、EmptyState、Skeleton、Toast（取代常駐成功訊息）、ConfirmDialog（危險操作；永久刪除維持輸入完整標題）。
- 保留跳至內容連結、鍵盤導覽與焦點樣式。

## 8. 後端影響

| 功能 | 範圍 |
|---|---|
| App Shell、Inspector、⌘K（文件搜尋）、上傳匣、公開站版型、Toast／Confirm、深色模式 | 僅前端 |
| 集合說明與圖示、文件數、清單排序參數、清單中的公開落後版本資訊 | 小幅後端 |
| 最近閱讀、收藏、首頁活動流、整合稽核紀錄、批次操作 API、SEO meta | 新 model 或 API |

所有新端點須沿用後端 RBAC 檢查並附測試；不得以前端顯示與否作為權限依據。

## 9. 開發策略

- 在同一個 repo 的 `ui-redesign` 分支開發，不另開 repo 或 fork：後端、Compose、Nginx、CI 與規範文件共用，改版以 PR 合回 `main`。
- 新介面掛在 `/app/`，舊介面 `/library/` 等路由照常運作，`main` 隨時可部署。新版驗收後再將首頁與舊路由導向新版，最後移除舊頁面。
- M7 NAS 部署在 `main` 進行；`ui-redesign` 定期 rebase 跟上 `main`。需要同時執行兩版對照時使用 git worktree。

## 10. 分期

| 階段 | 內容 | 後端 |
|---|---|---|
| P1 | 設計 token 與字型、`AppLayout`／`PublicLayout`、`/app/` 巢狀路由、Toast 與 ConfirmDialog、文件頁與 Inspector | 無 |
| P2 | 工作區首頁、⌘K、上傳匣、清單排序與批次操作、集合頁、收藏與最近閱讀、活動紀錄、回收桶、深色模式（細項見 10.1） | 新 model 與 API |
| P3 | 公開知識站首頁與文章頁、SEO meta（細項見 10.2） | 小幅 |
| P4 | 管理主控台各頁、切換預設路由並移除舊頁面 | 新 API |

### 10.1 P2 細項

| 子階段 | 內容 |
|---|---|
| P2a 後端基礎 | 新 model：`Favorite`（使用者 × 文件唯一）、`DocumentView`（使用者 × 文件唯一，只更新時間，每人保留 50 筆）、`DocumentActivity`（上傳、編輯、還原、資料變更、回收桶、發布與下架；以資料遷移從 `Version`、`DocumentTrashAudit`、`ArticlePublicationAudit` 回填，資料變更只從上線後記錄）；`Category` 新增 `description`、`color`。API：`PUT/DELETE /api/documents/:id/favorite/`、`POST /api/documents/:id/view/`、`GET /api/me/recent/`、`GET /api/documents/:id/activity/`、`GET /api/activity/?scope=all|mine|publish`；文件清單新增 `ordering`、`visibility=public|private|lagging`、`favorite=1` 參數與 `is_favorite`、`published_version` 欄位；集合清單新增 `document_count`；`POST /api/documents/bulk/`（移動集合、加／移除標籤、移入回收桶；Editor 以上、上限 100 份、單一交易、逐份走服務層）；`/api/auth/me` 回傳上傳 `limits`。每個端點附四種角色的權限測試 |
| P2b 首頁與導覽 | `/app/` 工作區首頁（繼續閱讀、團隊最近更新、需要注意、集合概覽）；側欄新增首頁、最近閱讀、收藏、集合色標與文件數、已公開文章（清單篩選）；⌘K 指令面板（文件搜尋、最近閱讀、導覽與動作）；深色模式切換（跟隨系統／淺色／深色）與深色程式碼高亮 |
| P2c 清單、集合頁、上傳匣 | 清單排序、可見性篩選、收藏星號、批次操作列；集合頁說明與色標（Editor 以上可編輯）；全視窗拖放的上傳匣（非模態、逐檔進度、重複檔處理）；新增版本仍須從指定文件發起 |
| P2d 文件頁與回收桶 | Inspector「活動」分頁、標題旁收藏星號、開啟時記錄最近閱讀；`/app/trash/` 回收桶（批次還原；永久刪除限 Admin 並輸入完整標題） |

不納入 P2：批次下載 ZIP（與 M7 的部署限制一併評估）、集合拖拉排序（P4 集合管理）。

每個階段開始前提出檔案異動計畫；完成後列出異動檔案、測試結果與殘餘風險，並在 Firefox 以 500、768、1280 px 驗證 Visitor、Viewer、Editor 與 Admin。

### 10.2 P3 細項

P3 的範圍：公開知識站首頁、文章頁、SEO meta。只動公開的部分，成員介面 `/app/` 和舊頁面都不受影響。

| 子階段 | 內容 |
|---|---|
| P3a 後端 | 見下方「P3a 後端」 |
| P3b 公開首頁 | 見下方「P3b 公開首頁」 |
| P3c 文章頁與 SEO | 見下方「P3c 文章頁與 SEO」 |

**P3a 後端**

- 公開文章清單 `GET /api/public/articles/`：
  - 每篇文章新增 `excerpt`、`reading_minutes`、`published_at`、`collection` 四個欄位：
    - `excerpt`：取自 `search_text` 的前 120 字。
    - `reading_minutes`：中文以每分鐘 400 字估算。
    - `collection`：只有 `{id, name, color}`。
  - 新增 `collection=<id>` 參數，用來依集合篩選。
- 新增 `GET /api/public/collections/`：只列出有公開文章的集合，包含名稱、色標和公開文章數。
- 單篇 `GET /api/public/articles/:id/`：
  - 新增 `published_at`、`reading_minutes`、`collection` 三個欄位。
  - 新增 `siblings`：同一集合裡的公開文章，只回傳 id 和標題，依發布時間排序，前端用來做上一篇／下一篇和左側目錄。
- Django 新增 `/articles/`，跟現有的 `/articles/<id>/` 一樣，用 X-Accel 送出 SPA。
- 不需要資料遷移。所有新欄位都在查詢時計算，從既有的 `ArticlePublication` 和文件目前所在的集合取得。
- 每個端點都要測：
  - 訪客可以讀取。
  - 未公開、已下架、在回收桶的文件，以及沒有公開文章的集合，都不能出現在回應中。
  - 回應不可以包含內部欄位：集合說明、內部文件數、子集合、作者、標籤。

**P3b 公開首頁**

- 網址是 `/articles/`，使用 `PublicLayout`。
- 頁首：品牌、「成員登入」；已登入的人則顯示「進入工作區」。
- 首屏：標題、說明、大搜尋框。
- 「依集合瀏覽」卡片：顯示名稱、色標、公開文章數。
- 「最新文章」：可依集合篩選，每篇顯示集合、發布日期、閱讀時間、標題、摘要，並且可以分頁。
- 支援深色模式、手機版，以及搜尋結果為空的狀態。

**P3c 文章頁與 SEO**

- 文章頁 `/articles/<id>/`：
  - 左側是同一集合的文章目錄。
  - 正文使用單一閱讀版型，拿掉現在的「標準／寬版／全頁」選單。
  - 右側是本頁目錄。
  - 底部有上一篇／下一篇、複製連結、更新日期。
- 公開的 HTML 文章維持靜態閱讀版，iframe 用 `sandbox=""`。
- SEO：後端在 `/articles/` 和 `/articles/<id>/` 的 HTML 輸出 `<title>`、`description`、Open Graph（`og:title`、`og:description`、`og:type`、`og:url`）。
  - 優先嘗試的做法：Django 在 X-Accel 回應的 header 裡帶 meta，非 ASCII 字元先轉成 HTML 實體，再由 Nginx `sub_filter` 插入 `index.html`。
  - 如果 Nginx 在內部轉址後讀不到 upstream header，改用備案：讓後端讀取建置出來的 `index.html`，自己插入 meta。
  - 不論哪種做法，插入的內容都要經過 HTML escape，並且要測試惡意標題（例如含 `<script>`）。
- 舊的 `PublicArticle.vue` 等到 P4 切換路由時才移除。P3 完成後，`/articles/<id>/` 會直接改用新頁面。

**不納入 P3**

- sitemap 和 RSS。
- 集合的「公開顯示」開關，也就是第 12 節第 5 點的選項 B。
- `/` 的導向。這要在 P4 決定。
- 文章留言和瀏覽統計。

**驗證**

- 後端：權限測試，以及上面列的資料外露測試。
- Playwright：
  - 角色：訪客、Viewer、Admin。
  - 寬度：500、768、1280、1920 px。
  - 外觀：淺色、深色。
  - 檢查項目：首頁、集合篩選、搜尋、文章頁（Markdown 和 HTML 各一篇）、上一篇／下一篇、SEO meta。
  - 這些都只讀取「UI 測試」集合和使用者已公開的文章，不做任何發布或下架。

## 11. Mockup 對照

| 畫面 | 對應章節 | 可互動部分 |
|---|---|---|
| 文件頁 · 三欄 + Inspector | 4.1、4.2 | 檢視模式切換、Inspector 分頁、版本勾選比較、面板收合 |
| 工作區首頁 | 4.3 | 活動流篩選 |
| 文件清單 · 批次操作與上傳匣 | 4.4 | 列選取與全選、批次操作列、上傳匣開關 |
| 公開知識站首頁 | 5 | 依集合篩選最新文章 |
| 元件 · 工作區側欄 | 4.1 | 畫面間導覽 |

Mockup 中的人名、文件與數字均為示意資料；頁尾 `[團隊名稱]` 待定。尚未涵蓋：管理主控台、公開文章頁、版本比較整頁、深色模式與手機版細節。

## 12. 決定事項（2026-11-24）

1. 收藏與最近閱讀納入 P2。
2. 「分類」在介面上一律改稱「集合」；後端 model 與 API 欄位維持 `category`，避免遷移與舊頁面中斷。
3. M7 NAS 部署延後，先完成介面改版。
4. HTML 預覽改為開啟文件時自動載入，並提供「自動載入」開關讓使用者關閉，關閉後回到按鈕載入。設定記在各自的瀏覽器（`localStorage`，key `knowledge-hub.app.html-autopreview`），預設為開啟。iframe 沙箱、一次性預覽網址和只限本機的限制都不變（2026-11-24）。
5. P3 公開首頁放在 `/articles/`，`/` 暫時不動，P4 再決定訪客和成員各自導向哪裡（2026-11-24）。
6. 公開站顯示集合，採選項 A：只顯示有公開文章的集合，而且只顯示集合本身的名稱、色標和公開文章數。不顯示集合說明、內部文件數、上層路徑，以及沒有公開文章的子集合（2026-11-24）。
7. SEO 只做基本 meta 和 Open Graph，不做 sitemap（2026-11-24）。

**名詞對照**

| 介面用語 | 後端名稱 |
|---|---|
| 集合 | `Category`、`category`、`/api/categories/` |
| 標籤 | `Tag`、`tags`、`/api/tags/` |
| 公開／下架 | `ArticlePublication`、`/publication/` |
| 最近閱讀 | `DocumentView`、`/api/me/recent/` |
| 收藏 | `Favorite`、`/favorite/` |

## 13. 實作紀錄

### P1（2026-11-23 完成）

| 子階段 | 提交 | 內容 |
|---|---|---|
| P1a 基礎建設 | `7ffc54e` | `--ui-*` 設計 token（含深色值）、自行打包 Inter／Noto Sans TC／JetBrains Mono、`api.ts`、Pinia `session` store、Toast 與 ConfirmDialog 服務 |
| P1b App Shell 與文件清單 | `7b00c2b` | `AppLayout`、`AppSidebar`（集合樹、角色導覽、頭像選單、手機版抽屜）、`/app/library/` 與 `/app/collections/:id/`、上傳／文件資料／集合與標籤對話框 |
| P1c 文件頁與 Inspector | `962e3af` | `/app/docs/:id/`（閱讀／編輯／分割預覽、舊版檢視、HTML 沙箱預覽）、Inspector（資訊、版本、公開）、`/app/docs/:id/compare/` |

主要檔案位於 `frontend/src/app/`；共用狀態在 `frontend/src/stores/`，token 在 `frontend/src/styles/tokens.css`。舊介面檔案未修改，Nginx 與後端未變更。

**與規劃不同或暫時的做法**

- `/app/` 巢狀路由由 P1a 移到 P1b，與 `AppLayout` 一起加入。
- 版本比較路由為 `/app/docs/:id/compare/?from=&to=`（結尾斜線與既有路由一致）。
- 舊版閱讀頁的「標準／寬版／全頁」選單不再提供，改由 Inspector 開關調整正文寬度；寬度 1100px 以下 Inspector 改為右側覆蓋面板。
- ⌘K／Ctrl K 在 P1 只聚焦文件清單的搜尋框，指令面板留待 P2。
- 側欄的回收桶與帳號管理仍連到舊版頁面（分別於 P2、P4 改版）；頭像選單提供「切換到舊版介面」。
- Inspector 的「活動」分頁缺少 API，留待 P2；「公開」分頁與公開狀態標籤僅 Admin 可見，因為文件詳細 API 不含公開狀態。
- 側欄集合不顯示文件數（需後端支援，P2）。
- 文件頁「上傳新版本」暫以 50 MB 作為前端提示上限，實際限制由後端檢查。
- 深色 token 已備妥，切換開關排在 P2。
- `app.css` 的全域 `main`、`nav` 規則會影響新版面，已在 `.hub-app` 範圍內重設。

**驗證**

- 每個子階段皆在 `node:24-alpine` 容器執行 `npm run build`（含 `vue-tsc`）通過，並以分支重建 Nginx 確認新舊路由回應 200；P1a 另執行 `scripts/smoke.sh` 通過。
- 使用者已在瀏覽器檢查 P1b 與 P1c 介面，依截圖回饋調整版面（`9ffa0bc`）。
- 2026-11-24 完成第 10 節的系統性驗證，結果見下方「P1 驗證」。

### P1 驗證（2026-11-24）

**方法**：在開發資料庫建立 `uitest-admin`、`uitest-editor`、`uitest-viewer` 三個測試帳號（Email 為 `@example.invalid`，密碼只保存在本機，不進 repo），並以 Editor 建立「UI 測試」集合與含標題、清單、程式碼、表格、引言、Mermaid 的「UI 測試文件」（v1、v2）。以 `mcr.microsoft.com/playwright/python:v1.49.0-noble` 無頭 Chromium，對三種角色在 500、768、1280 px 截取文件清單、側欄抽屜、Markdown 閱讀與分割預覽、Inspector 各分頁、HTML 預覽、版本比較與列選單，共 76 張；另檢查訪客導向、console 錯誤與頁面水平溢出。腳本放在本機 scratchpad，未納入 repo。

**角色檢查**

| 角色 | 上傳 | 編輯 | 公開設定 | 還原版本 | Inspector 可編輯 | 列選單 |
|---|---|---|---|---|---|---|
| Admin | 有 | 有 | 有 | 有 | 有 | 開啟、下載、版本歷史、編輯資料、新增版本、公開設定、移入回收桶 |
| Editor | 有 | 有 | 無 | 有 | 有 | 同上，不含公開設定 |
| Viewer | 無 | 無 | 無 | 無 | 無 | 開啟、下載、版本歷史 |
| Visitor | `/app/` 導向 `/accounts/login/?next=` | | | | | |

所有頁面沒有 console 錯誤或未處理例外。

**發現並修正的問題**

| 問題 | 修正 |
|---|---|
| 清單頁在 500／768 px 寬度溢出到 770px | 表格捲動容器加上 `position: relative`，避免絕對定位的隱藏表頭文字跑出容器 |
| 窄螢幕表格需橫向捲動，捲動時標題消失、列選單無法開啟 | 860px 以下改為卡片排列 |
| Markdown 開頭 H1 與文件標題重複，目錄也重複 | 開頭 H1 與標題相同時隱藏，目錄移除該項並以最淺層級為縮排基準 |
| 分割預覽在 Inspector 開啟時兩欄各約 300px | 進入編輯／分割預覽時暫時收起 Inspector，回到閱讀恢復偏好 |
| 版本比較將相同內容全部展開 | `VersionDiff.vue` 新增 `compact` 選項（折疊未變更區段、自動換行），僅新比較頁啟用，舊版對話框不變 |
| 沒有標籤的列在桌面版錯位 | 儲存格 class 與空白狀態的 `.empty` 撞名，改名為 `no-tags` |

**測試資料**：測試帳號與「UI 測試」集合、文件仍保留在開發資料庫，供後續階段重跑截圖；改版結束前停用帳號並將文件移入回收桶。

### P2（2026-11-24 完成）

使用者授權在其休息期間自行實作與驗證；各子階段於本機 commit，尚未 push，待使用者審閱。

| 子階段 | 提交 | 內容 |
|---|---|---|
| P2a 後端基礎 | `c63edc5` | `Favorite`、`DocumentView`、`DocumentActivity`（遷移 0007）與活動回填（遷移 0008）；集合 `description`、`color`、`document_count`；清單 `ordering`、`visibility`、`favorite` 與 `is_favorite`、`published_version`；收藏、最近閱讀、活動、批次 API；`/api/auth/me` 上傳限制；8 項新測試 |
| P2b 首頁與導覽 | `01f6823` | `/app/` 首頁、`/app/recent/`、`/app/favorites/`、`/app/published/`；側欄色標、文件數與落後徽章；Ctrl／⌘K 指令面板；跟隨系統／淺色／深色外觀（含 Monaco 與程式碼高亮） |
| P2c 清單、集合頁、上傳匣 | `05a4da4` | 全視窗拖放與非模態上傳匣；清單排序、可見性篩選、收藏星號、勾選與批次移動／標籤／回收桶；集合頁色標與說明編輯 |
| P2d 文件頁與回收桶 | `2eae434` | Inspector「活動」分頁、文件頁收藏星號、開啟時記錄最近閱讀、所有成員可見公開狀態；`/app/trash/` 批次還原與 Admin 輸入標題永久刪除 |

**實作說明**

- 活動紀錄只顯示未在回收桶的文件；永久刪除時隨文件一併刪除。標題、集合、標籤的變更從 P2 上線後開始記錄。
- 上傳匣一律建立新文件；新增版本仍從文件頁或清單列選單對指定文件上傳，不以檔名配對。
- 上傳匣不在上傳時指定標籤，預設放入目前檢視的集合；上傳後可用批次操作加標籤。
- 批次還原在前端逐份呼叫既有的還原 API（後端未新增批次還原端點）。
- 深色模式只在新介面生效；離開 `/app/` 時移除 `.hub-dark`，舊頁面維持淺色。
- Viewer 開啟 `/app/trash/` 時直接顯示權限說明，不送出必定失敗的請求。

**驗證**

- 後端：47 項測試通過（原 39 項 + 8 項 P2），`ruff` 與 `makemigrations --check` 通過；遷移已套用至開發資料庫，回填 16 筆歷史活動。
- 前端：每個子階段 `npm run build`（含 `vue-tsc`）通過並重建 Nginx。
- Playwright：P2b 首頁、指令面板、最近閱讀、收藏、已公開文章與深色模式（Admin／Editor／Viewer，500／768／1280 px）；P2c 上傳匣（新增、重複、格式錯誤）、拖放遮罩、集合編輯、排序、可見性篩選、收藏、批次加標籤、手機卡片與 Viewer 權限；P2d 活動分頁、收藏星號、最近閱讀紀錄、回收桶還原與永久刪除、Viewer 權限；最後重跑 P1 的 76 張截圖與溢出檢查，結果與 P1 一致，無 console 錯誤。`scripts/smoke.sh` 通過，舊介面路由正常。
- 寫入動作只針對「UI 測試」集合內的測試文件；驗證中建立的上傳匣測試文件一份已還原、一份已永久刪除。使用者原有的回收桶文件未被變更。

### P2 審閱後調整（2026-11-24）

- HTML 預覽改成自動載入，並加上開關（見第 12 節第 4 點）。切換文件或版本時，晚回來的舊預覽請求會被丟棄，不會覆蓋目前的預覽。
- Playwright（Viewer，1280／500 px）驗證項目，全部通過：
  - 預設不用點按鈕就會載入，開啟時只發出一張預覽票證。
  - 歷史版本會改用新的票證。
  - 關掉開關時，目前的預覽保留；重新整理後不載入預覽，也不發出票證，但仍可用按鈕手動開啟。
  - 重新打開開關時，預覽立刻載入。
  - iframe 的 `sandbox`、`referrerpolicy` 都沒變。
  - 沒有頁面溢出，也沒有 console 錯誤。
- 寬螢幕版面：
  - 首頁內容區改成置中。寬度上限用 `clamp(76rem, 100vw − 側欄 − 10rem, 90rem)`，所以 1280 px 時跟原本一樣，1920 px 時約 1440 px。
  - 視窗寬度 ≥1600 px 時，右欄從 18rem 放寬到 22rem。活動流則維持適合閱讀的寬度。
  - 首頁集合的說明最多顯示兩行。
  - 「繼續閱讀」的卡片最多 4 欄，用 `auto-fit` 讓現有的卡片撐滿整列。
  - 文件庫、文件頁不變。回收桶之後改成跟文件庫一致，見下方。
  - Playwright（Admin，1920／1600／1280／768／500 px）驗證通過，沒有溢出，也沒有 console 錯誤。
- 最近閱讀和收藏的風格統一：
  - `/app/recent/` 改用 `LibraryPage` 的 `recent` preset，跟收藏、已公開文章共用同一套表格，包括手機卡片、星號、列選單和批次操作。原本的 `RecentPage.vue` 已移除。
  - 資料來自 `/api/me/recent/?limit=50`，依閱讀時間排序。日期欄改成「閱讀」，不顯示搜尋、篩選、排序和分頁。後端沒有改。
  - 文件庫系列的頁面現在都會把分頁標題設成「〈頁名〉 · Knowledge Hub」。
  - Playwright（Admin 1920／1280／500 px、Viewer 1280 px）驗證通過：
    - Viewer 看不到勾選欄。
    - 收藏和全部文件的工具列、日期欄沒有變。
    - 沒有溢出，也沒有 console 錯誤。
- 回收桶風格對齊文件庫：
  - 版面改成跟文件庫一樣：靠左、最寬 100rem，標題下方顯示「N 份文件 · 說明」。
  - 新增「移入者」欄。集合改顯示完整路徑。如果集合已經不存在，退回顯示 API 給的名稱。
  - 每列只留「還原」按鈕。「永久刪除」移到「⋯」選單，只有 Admin 看得到，確認時一樣要輸入完整標題。
  - 後端 `/api/trash/` 新增兩個欄位：`trashed_by` 取最近一次 `DocumentActivity` 的 trashed actor，`category_id` 給新頁面用。原本的 `category`（集合名稱）保留，舊頁面 `/library/trash/` 不受影響。另加 1 項測試，後端共 48 項通過。
  - Playwright（Admin 1920／1280／500 px、Editor 與 Viewer 1280 px）驗證通過：
    - Editor 沒有「⋯」選單，Viewer 看到權限說明。
    - 永久刪除對話框在輸入標題前，確認按鈕維持停用。驗證時按了取消，沒有刪除任何東西。
    - 舊版回收桶正常，沒有溢出，也沒有 console 錯誤。

### P3a 後端（2026-11-24）

- `documents/publication.py`：
  - `GET /api/public/articles/`：每篇文章新增 `excerpt`、`reading_minutes`、`published_at`、`collection`、`format` 五個欄位，回應多了 `count`。新增 `collection=<uuid>` 參數篩選集合，不是合法 UUID 時回 400。
  - 新增 `GET /api/public/collections/`：只列出有公開文章的集合，每個集合回傳 `{id, name, color, article_count}`。
  - `GET /api/public/articles/:id/`：新增 `published_at`、`reading_minutes`、`collection`，以及 `siblings`（同一集合的公開文章，只有 `document_id` 和 `title`，依發布時間排序，最多 200 篇）。
- 摘要與閱讀時間：
  - 摘要取 `search_text` 的前 2000 字當樣本。Markdown 會先去掉圖片、連結網址、程式碼區塊、標題和清單符號、表格分隔線、強調符號，再去掉跟文章標題重複的開頭，最後截成 120 字。
  - 閱讀時間依樣本裡中日韓文字的比例估算：中日韓文字每分鐘 400 字，拉丁字母每分鐘 1000 字，最少 1 分鐘。
  - 這些都在查詢時計算，不需要資料遷移。
- `hub/urls.py` 新增 `/articles/`，用 X-Accel 送出 SPA，只接受 GET 和 HEAD。
- 原有欄位（`document_id`、`title`、`format`、`body`、`page`、`pages`）都保留，所以舊的 `Library.vue` 訪客清單和 `PublicArticle.vue` 不受影響。
- 測試：
  - 新增 `documents/test_public_site.py`，共 4 項。
    - 訪客只拿得到白名單裡的欄位。
    - 集合父層、集合說明、沒有公開文章的集合、作者、標籤、私人文件，都不會出現在任何公開回應裡。
    - 已下架和在回收桶的文章，會從清單、集合、同集合清單裡消失，單篇也回 404。
    - 驗證入口頁和 HTTP 方法限制，以及摘要和閱讀時間的計算。
  - 原有的發布測試改成只比對既有欄位。
  - 後端 52 項測試全部通過，`ruff` 和 `makemigrations --check` 也通過，`smoke.sh` 通過。

### P3b 公開首頁（2026-11-24）

- 新增 `frontend/src/site/`：
  - `PublicLayout.vue`：
    - 頁首有品牌、前 5 個公開集合（手機上隱藏）、淺色／深色切換，以及「成員登入」。已登入的人改顯示「進入工作區」，這只影響顯示，權限一律由後端判斷。
    - 頁尾、跳至內容連結。
    - 深色模式沿用 `theme` store。
  - `SiteHome.vue`：
    - 首屏標題和大搜尋框。
    - 「依集合瀏覽」卡片，搜尋時隱藏。
    - 「最新文章」清單：每篇顯示集合標籤、發布日期、閱讀時間、標題、摘要。
    - 集合篩選 chip：有兩個以上集合，或已經選了某個集合時才顯示。
    - 分頁，以及空狀態、錯誤狀態。
    - 搜尋、集合、頁碼都寫在網址的 query 裡（`q`、`collection`、`page`），可以直接分享。
  - `public.ts`：公開 API 的型別和 `publicApi()` fetch 輔助函式。
- 路由：`/articles/` 套用 `PublicLayout`，子頁面是 `site-home`。`/articles/:id/` 暫時仍是舊的 `PublicArticle.vue`，P3c 再替換。
- 新增 router `scrollBehavior`：只有公開首頁帶 hash 時才捲動，例如點集合會捲到 `#latest`。其他路由維持原本不捲動的行為。
- 訪客進入頁面時會呼叫 `/api/auth/me` 判斷要顯示哪個按鈕，得到的 403 會出現在瀏覽器 console。這是預期的行為，跟舊的訪客清單一樣。
- Playwright（訪客：1920／1280／768／500 px，淺色和深色；Viewer：1280 px）共 51 項全部通過：
  - 搜尋、搜尋無結果、回到全部、集合卡片篩選、無效集合參數顯示錯誤、文章連結格式。
  - 已登入成員看到「進入工作區」。
  - 沒有溢出，也沒有預期以外的 console 錯誤。

### P3c 文章頁與 SEO（2026-11-24）

- `frontend/src/site/SiteArticle.vue`：`/articles/:id/` 改為 `PublicLayout` 的子路由，路由名稱沿用 `public-article`，所以舊的 `Library.vue`、`PublicationDialog.vue`、`PublishTab.vue` 裡的連結都不用改。
  - 版面三欄：左側同集合文章（目前這篇反白）、中間正文、右側本頁目錄。
  - 寬度 ≤1200 px 時拿掉目錄；≤900 px 時改成單欄，同集合清單移到文章下方。沒有集合的文章不顯示左欄。
  - Markdown：跟文件頁一樣，隱藏和標題重複的開頭 H1。點目錄會更新 `#section-N`，重新整理後也會捲回原位置。
  - HTML：沿用舊頁的靜態閱讀方式，`<iframe sandbox="">` 加上 `srcdoc` 內的 CSP（`default-src 'none'`），以及 `referrerpolicy="no-referrer"`。iframe 固定高度 78vh，內容在裡面捲動。
  - 頁尾：更新日期、複製連結、上一篇／下一篇（依同集合的發布順序）。
  - 拿掉「標準／寬版／全頁」選單。
  - `PublicArticle.vue` 已經沒有路由使用，檔案留到 P4 再刪除。
  - 正文寬度：Markdown 文章維持 48rem 的閱讀寬度。HTML 文章常有圖表和寬表格，所以正文填滿左欄以外的寬度（整頁最寬 90rem）；沒有集合的 HTML 文章最寬 72rem。
  - 文章頁的頁首和頁尾寬度跟著放寬到 90rem，跟三欄版面對齊。首頁維持 70rem。
- SEO：
  - `documents/publication.py`：`/articles/` 和 `/articles/<id>/` 的 X-Accel 回應會帶 `X-Hub-Head`，內容是 `<title>`、`description`、`og:site_name`、`og:type`、`og:title`、`og:description`、`og:url`。
    - 每個值都先正規化空白、限制在 120 字，再 `html.escape`，非 ASCII 字元轉成數字字元參照，所以 header 只會有 ASCII。
    - `og:url` 使用 `PUBLIC_ORIGIN`。
    - 未公開、已下架的文章維持回 404，不帶 header。
  - `nginx/default.conf`：
    - 用 `map $upstream_http_x_hub_head $hub_head` 取出 header，在 `location = /index.html` 以 `sub_filter` 取代 `<title>Knowledge Hub</title>`。沒有這個 header 時保留原本的標題，所以 `/app/`、`/` 等頁面不受影響。
    - 實測確認：upstream header 經過內部轉址後仍讀得到；`X-Hub-Head` 不會出現在給瀏覽器的回應 header 裡。
    - `/articles/` 的 `proxy_buffer_size` 調大到 16k（`proxy_buffers 8 16k`、`proxy_busy_buffers_size 32k`），避免標題很長時 header 超出預設緩衝區。
- 測試：
  - 後端新增 2 項：含 `"><script>`、`&`、`<b>` 的惡意標題會被 escape，header 只有 ASCII，所有屬性值都留在引號內，下架後不再帶 header；另外測試長度上限。後端共 54 項通過。
  - Playwright 共 90 項通過：
    - 訪客，1920／1280／768／500 px，淺色和深色。
    - HTML 文章：`sandbox=""`、CSP、集合導覽。
    - Markdown 文章：用攔截的 API 回應模擬，不寫進資料庫。檢查隱藏開頭 H1、內文的 `<script>` 不會執行、目錄只在寬螢幕顯示、上一篇／下一篇、目錄跳轉和重新整理後回到 hash 位置。
    - 未分類文章、複製連結、首頁點進文章、找不到的文章、舊介面的路由。
    - 沒有溢出，也沒有預期以外的 console 錯誤。
  - `smoke.sh` 通過。
