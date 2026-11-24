# Knowledge Hub 開發進度與交接

截至 2026-11-23，M0 至 M6 與整站介面改版已推送到 GitHub 的 `main`。下一個里程碑是 M7 NAS 部署與安全強化。 [M6 提交](https://github.com/ansonku/knowledge-hub/commit/38d0e78) · [介面改版](https://github.com/ansonku/knowledge-hub/commit/a239409)

## 已完成

- **M0 基礎架構**（`fc043e8`）。Docker Compose、Django、Vue、PostgreSQL、Nginx、健康檢查與 CI。
- **M1 帳號與權限**（`905fb57`）。帳號邀請與啟用、密碼登入、角色權限、Google 綁定、TOTP 與復原碼。個人設定與帳號管理採用 PrimeVue Aura。實際 SMTP 寄達與 Google 回呼需使用正式設定驗證。
- **M2 文件管理**（`57b9b38`）。分類與標籤、Markdown／HTML 格式篩選、逐檔批次上傳、指定文件新增版本與下載。舊版檔案保留。Viewer 可閱讀與下載。
- **M3 閱讀、編輯與預覽**（`7ec53a5`）。三種閱讀版型、Monaco 編輯與分割預覽、Mermaid、KaTeX、語法高亮及唯讀任務清單。儲存 Markdown 會新增版本，過期草稿會收到版本衝突提示。本機 30 項後端測試通過，Firefox 已驗證 Markdown 閱讀與分割預覽呈現一致，以及 HTML 沙箱在嵌入和直接開啟時的隔離行為。

HTML 可能引用外部 HTTPS 資源，原本的設計是保留「開啟 HTML 預覽」按鈕，讓使用者選擇何時載入。新介面 `/app/` 改成開啟文件時自動載入，並提供「自動載入」開關，各瀏覽器分別記住設定，關閉後回到按鈕模式（2026-11-24）。可執行預覽目前限本機 HTTP，公開環境的已登入成員可依權限下載附件。對外啟用前仍須完成跨瀏覽器的完整隔離驗收。

## 恢復本機開發

從專案根目錄執行 `docker compose up --build --wait`，然後登入，會進入工作區 `/app/`。開發帳號存在 PostgreSQL 的 `postgres_data`，文件原始檔存在 `document_data`。換電腦後，GitHub 可取得程式碼，原有帳號與文件則需要這兩個資料卷的備份。 [本機工作區](http://localhost:18080/app/) · [環境設定](../README.md)

## M4 版本歷史與還原

文件頁已有版本清單、舊版閱讀與原始檔下載、Monaco 雙版比較，以及 Admin 和 Editor 的還原功能。還原會建立新版本，記錄操作者、還原來源、原先的目前版本和新版本。相同基準的併發還原只接受一筆。33 項後端測試通過，儲存檢查已核對本機版本檔案。 [里程碑計畫](docs/IMPLEMENTATION_PLAN.md#m4--version-history)


## M5 搜尋與回收桶

知識總覽可依標題、分類、標籤及目前版本正文搜尋。中文支援連續字串搜尋，HTML 索引會略過腳本與樣式。回收桶可還原文件與全部版本。永久刪除僅限 Admin，需輸入完整標題，並保留稽核及可重試的清理工作。37 項後端測試通過。 [M4 驗收](https://github.com/ansonku/knowledge-hub/actions/runs/45165226728)


## M6 文章公開與未登入閱讀

既有與新文章預設 Private。Admin 可確認指定版本後發布，首頁與 `/library/` 共用知識總覽，訪客可搜尋與閱讀公開文章。後續內部更新維持未發布狀態，直到 Admin 發布新版。下架或移入回收桶會讓舊公開網址回傳 404。從回收桶還原後維持 Private。公開 HTML 採靜態閱讀版。39 項 Django 測試已通過。Firefox 已驗證 Admin 發布 v2 後，訪客可在無痕視窗從首頁閱讀，且下架後舊網址及 API 立即回傳 404。首頁改版後已再驗證兩個入口的公開搜尋，以及 Visitor、Viewer 與 Admin 的介面。 [M6 實作計畫](docs/IMPLEMENTATION_PLAN.md#m6--article-publication-and-anonymous-reading)

## 整站介面改版

知識總覽以搜尋為主，窄螢幕可展開格式與標籤篩選，並移除已套用的條件。登入後保留「公開／私人」狀態標籤。公開與會員閱讀頁共用樣式，Markdown 標準版的目錄可在窄螢幕收合。登入、個人設定、帳號管理、版本歷史與回收桶共用頁首及主要操作樣式。

39 項 Django 測試通過。Firefox 已在 500、768、1280 px 驗證文章清單、篩選、目錄、鍵盤導覽與角色權限，並確認 OBMF 公開文章的 MMIO SVG 和 GPIO 50 欄圖在窄螢幕可讀。 [介面改版提交](https://github.com/ansonku/knowledge-hub/commit/a239409)

## 介面改版（P1–P5 完成，待合併）

P3 公開知識站、P4 個人設定、成員管理、集合與標籤、稽核紀錄、系統狀態都已完成，舊介面已移除，`/` 依登入狀態導向 `/app/` 或 `/articles/`。P5 完成站台名稱與集合色標、貼邊三欄的公開入口網站（多層集合）、登入頁改版、成員閱讀入口 `/read/`，以及匿名、不記身分的公開熱門文章。後端 80 項測試通過，各頁面以 Playwright 驗證。`ui-redesign` 分支待開 PR 合回 `main`。

以下為早期紀錄：工作區、公開知識站與管理主控台分開設計，在 `ui-redesign` 分支以 `/app/` 路由與現有介面並存開發。P1 已完成：設計 token 與自帶字型、三欄工作區框架、文件清單、文件頁與 Inspector（資訊、版本時間軸與還原、Admin 公開狀態與落後版本），以及可分享的版本比較頁。舊介面與後端未變更。P2 也已完成（首頁、指令面板、上傳匣、批次操作、收藏與最近閱讀、活動紀錄、回收桶、深色模式），後端新增 3 個 model 與 8 項測試，並以 Playwright 完成驗證；P1 已於 2026-11-24 以三種寬度與四種角色完成自動截圖驗證並修正發現的版面問題。討論結論、實作紀錄與分期見 [UI 改版規劃](docs/UI_REDESIGN.md)。

NAS 部署與安全強化順延為 M7，於介面改版完成後進行。 [M7 實作計畫](docs/IMPLEMENTATION_PLAN.md#m7--nas-deployment-and-hardening)
