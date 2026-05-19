# Phase 4.5 — 產品化基礎建設（已完成）

**抽出自** [規畫書 §Phase 4.5 + 附錄 A.1](../dobtor_doc_editor_高保真匯入開發規劃.md) **/ Sprint 155 catch-up（2026-05-19）**

Phase 4.5 是 Sprint 20-24 期間的產品化補強衝刺（~10 週）、為了讓 docx 匯入引擎能在 ChienYi 業務環境中正式使用。**Phase 0-7 是 docx 匯入主線、Phase 4.5 是支撐這條主線在 production 環境跑起來的基礎建設**。

---

## 1. 背景

§9.1-9.3 純技術時程外、進入正式業務流程前需要 ~10 週的產品化補強衝刺。Sprint 20-24 已落地;若跳過會在進入正式業務時被迫補回。

**結論對時程的影響**:
- 單人方案到 B 級從 6-8 個月變 8-10 個月
- 三人方案到 A- 級從 10-14 個月變 12-16 個月

---

## 2. 關鍵決策

### 2.1 PDF 引擎選擇

**選擇**:LibreOffice headless

**拒絕**:Chromium headless

**理由**:
- CJK 字型支援差（Chromium puppeteer 對中文字型 fallback 不穩）
- 啟動慢 3x（Chromium cold start ~3s vs LibreOffice ~1s）

**驗證 pipeline**:PSNR + pHash 黃金檔比對

**詳見**: [docs/pdf_engine_evaluation.md](pdf_engine_evaluation.md)

### 2.2 與 QWeb 共存

ChienYi 系統內**兩條文件產製通路**並存:
- **QWeb PDF**:自動產出、固定樣板（通報單、估驗單、施工日誌、自主檢查表）
- **dobtor_doc_editor**:協作編輯、版本歷史、現場可編輯（監造會議記錄、施工計畫書）

**決策樹** 見 [docs/scope_decision.md](scope_decision.md)。新文件需求預設用 QWeb、除非該文件明確需要多人協作或現場編輯才走 dobtor。

### 2.3 ChienYi mixin（dobtor 整合）

`doc.linked.mixin` 讓 ChienYi 模型關聯 dobtor 文件、不在模型直接寫 `doc_id` Many2one。當前已落地的繼承對象:
- `construction_supervision_base`
- `notification_slip`
- `daily_log_sheet`

### 2.4 Zip Bomb 防護（3 道閘門）

- 50MB 原檔限制
- 200MB 解壓上限
- ≤1000 entry、深度 ≤16

**驗證**:OWASP corpus + nested-zip fixture 全攔下

### 2.5 ACL

- **Portal user**:white-list per-doc（受邀協作者）
- **Internal user**:全局管理（監造主管 / 工程師）

---

## 3. W1-W10 落地清單

### W1 — CI/CD + Zip Bomb 防護

- `.github/workflows/ci.yml`:flake8 + vitest + pixelmatch + Playwright
- `models/doc_zip_guard.py`:3 道閘門、9 個 backend test（zip_guard tag）

**Sprint 出處**:Sprint 20-24

### W2-3 — Portal 整合

- `/my/documents/*` 路由 + cy_pc_layout topbar
- 兩層 ACL（portal user white-list / internal 全局）

**Sprint 出處**:Sprint 21-22

### W4 — OWL 升級

- `doc_editor.js` 從 odoo.define legacy 升 OWL Component
- `onWillUnmount()` 清理 listener / cache
- Sprint 14 揭示 nodeModuleStub 47-sprint IIFE bundle blocker

### W5-6 — QWeb 共存 + ChienYi mixin

- [docs/scope_decision.md](scope_decision.md):QWeb vs dobtor 決策樹
- `doc.linked.mixin`:讓 ChienYi 模型繼承關聯文件
- 4-6 份預設樣板:監造會議記錄、施工計畫書、變更說明書、(預留)

### W7-8 — 版本管理 UI + AutoSave

- 4 條版本路由:list / diff / restore / annotate
- `doc_version_panel.js`:AST diff
- `auto_save_manager.js`:debounce + IndexedDB local cache
- Leader Election:多 tab 同步避免 conflict

### W9-10 — Python 端測試 + PDF 引擎

- TransactionCase 12 條 controller + ACL 驗證
- LibreOffice headless（拒 Chromium）
- PSNR / pHash 黃金檔比對

**Sprint 出處**:Sprint 24

---

## 4. 後續產品化（Sprint 64b 起、font_serve）

Sprint 64b-69 落地 `/dobtor/fonts/*` backend endpoint:
- FONT_PATH_MAP candidate fallback chain
- `resolve_font_path()` 依序試 candidate
- 12 backend test:含 path traversal / null byte / URL-encoded CJK
- Sprint 69 揭示 LibreOffice not in container、改 NotoCJK fallback

**Sprint 出處**:Sprint 64b、66、68、69

---

## 5. 後續產品化（Sprint 115-117、廣域 ACL audit）

Sprint 70-89 autonomous batch + Sprint 115-117 收口:
- backend test 0 → 21（廣域應用紀律 #15）
- 6 條 controller boundary HttpCase（Sprint 115）
- i18n zh_TW.po +7 msgid（Sprint 116）
- upload_template null byte sanitize + graceful 400（Sprint 116）
- doc.document portal cross-company collaboration lock-in 4 test（Sprint 117、ADR-021）

---

## 6. 相關 ADR

- ADR-001 ~ ADR-020:早期架構決策（Phase 0-3 對映）
- ADR-021:Sprint 117 cross-company collaboration 收口決策（保留現狀、不改 record rule）
- ADR-022:Phase 8 Template UI Builder Strategy B（2026-05-19、user 親口認可）

完整列表見 [architecture_decision.md](architecture_decision.md)。

---

## 7. 與規畫書的關係

- 規畫書 §5 Phase 表內、Phase 4.5 用 1 段精簡描述 + 連結到本檔
- 規畫書 §9.3b 提及 +10 週時程影響
- Phase 4.5 細節（W1-W10 / 各決策理由 / Sprint 出處）一律放在本檔、不污染規畫書主流

---

**檔案維護**: Phase 4.5 已 100% 完成（Sprint 24 結束）、本檔不再追加新 W;若後續產品化補強（如 W11 等）需要、應評估是否屬 Phase 4.5 或開新 phase。
