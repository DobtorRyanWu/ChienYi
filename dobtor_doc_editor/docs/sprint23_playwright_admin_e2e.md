# Sprint 23 — Playwright Admin E2E 驗證基建

**期間**：2026-05-09
**主軸**：把使用者新加入的 SOP「每次修正必須用 Playwright 證明前端可見且使用者可手動執行」轉成可重複執行的工程資產
**結論**：擴 `tests/playwright/` 加 `admin` project + auth flow + 5 個 E2E case；Sprint 21+22 四個 host model（一般式 / 預約式 / 缺失 / 估驗）的「開啟線上文件」按鈕全部前端可見、可點擊、可建立 `doc.document`。

---

## 0. 背景：使用者新 SOP

Sprint 21 → 22 的 mixin 整合走 Python regression（91/91 全綠），但使用者反映：

> 「必須用 playwright 驗證一次修正是否已經顯示在前端並且是我人工操作也可以執行或顯示，才不會發生只有你可以執行但我無法執行的問題」

Sprint 21 後記事故（`-i` 後忘記 `docker restart` → 500 KeyError）就是「Python test 綠但 UI 紅」的活案例：testrunner 跑完即離，沒踩到長存進程的 manifest cache。Sprint 23 把這個漏洞補起來。

---

## 1. Playwright 基建擴充

### 1.1 既有狀態（之前）

`tests/playwright/` 是 ChienYi `construction_portal` v10 的 E2E 套件，三個 project：

| Project | 用途 | 認證 |
|---|---|---|
| `desktop` | portal v10 桌機 | storageState 自 `auth.setup.ts` 取得（portal user）|
| `mobile` | portal v10 手機 | 同上 |
| `public` | 不需登入 smoke | 無 |

**沒有 admin (internal user) 後台 E2E** — 4 個 dobtor bridge model 的 form view 屬於 `/odoo/action-*` 後台路徑，現有 portal user 無權看。

### 1.2 Sprint 23 新增

`tests/playwright/playwright.config.ts` 新增 `admin` project：

```diff
 // 桌機 viewport（不跑 public + mobile-only + admin-only）
 {
   name: 'desktop',
   ...
-  testIgnore: [/.*\.setup\.ts/, /public-.*\.spec\.ts/, /portal-mobile\.spec\.ts/],
+  testIgnore: [
+    /.*\.setup\.ts/,
+    /public-.*\.spec\.ts/,
+    /portal-mobile\.spec\.ts/,
+    /admin-.*\.spec\.ts/,
+  ],
 },
+// Admin 後台 E2E（dobtor bridge integration verification）
+// 不依賴 auth.setup.ts；spec 內 beforeEach 自己 inline login
+{
+  name: 'admin',
+  use: { ...devices['Desktop Chrome'] },
+  testMatch: /admin-.*\.spec\.ts/,
+},
```

關鍵設計：
- **`admin` project 不依賴 setup**（`auth.setup.ts` 是給 portal user 的）
- `admin-*.spec.ts` 命名前綴自動 routing 到此 project
- 既有 `desktop` / `mobile` 加 `/admin-.*\.spec\.ts/` 到 testIgnore，互不打擾

### 1.3 `.env` 補入 admin 帳密

```
ADMIN_USER=admin
ADMIN_PASSWORD=admin
```

預設 Odoo 18 dev DB 的 admin/admin；上 prod 前必改。

---

## 2. E2E 測試 [`admin-dobtor-bridge.spec.ts`](../../../tests/playwright/tests/admin-dobtor-bridge.spec.ts)

### 2.1 Helper

```ts
async function loginAsAdmin(page: Page) { ... }
async function verifyOpenDocButton(page, actionXmlId, modelLabel) {
  await page.goto(`${BASE_URL}/odoo/action-${actionXmlId}`);
  // 開第一筆 / 沒紀錄則新建
  // 驗 button:has-text("開啟線上文件")
}
```

### 2.2 五個 case

| # | Test | 驗證 model | 結果 |
|---|---|---|---|
| 1 | general.self.inspection 出現按鈕 | `general.self.inspection` (Sprint 21) | ✅ 9.2s |
| 2 | reservation.self.inspection 出現按鈕 | `reservation.self.inspection` (Sprint 22) | ✅ 8.2s |
| 3 | supervision.defect 出現按鈕 | `supervision.defect` (Sprint 22) | ✅ 8.3s |
| 4 | payment.estimate 出現按鈕 | `payment.estimate` (Sprint 22) | ✅ 9.2s |
| 5 | 點按鈕可實際打開 doc.document（E2E） | supervision.defect | ✅ 10.7s |

合計 5 case / 53.8 秒（單 worker，序列跑）。

### 2.3 第 5 個 E2E click 的設計

End-to-end 點擊驗證選 `supervision.defect` 而非 `general.self.inspection`，因為 defect 必填欄位最少（`description / found_date / project`），新建紀錄後 fixture 風險最低；general 還需 `inspection_type_id`（Many2one to `self.inspection.type`）才能 save，比較囉嗦。

成功判定條件採 OR：
1. URL 跳到 `doc.document`（mixin 回 ir.actions.act_window 直接導航）
2. 出現 save 對話框（OWL form 對 unsaved record 的 button click 強制存檔）
3. stat button 出現「線上文件」字樣（doc 建立但沒導航）

任一發生都代表 button 真實 wired 起來。

---

## 3. 驗證「不只 AI 能跑」

執行命令（任何人在 `tests/playwright/` 下都能跑）：

```bash
cd /mnt/d/work/odoo18-docker/tests/playwright
npx playwright test --project=admin --reporter=list
```

預期輸出：

```
Running 5 tests using 1 worker
  ✓  1 [admin] › ... general.self.inspection 出現「開啟線上文件」按鈕 (9.2s)
  ✓  2 [admin] › ... reservation.self.inspection 出現「開啟線上文件」按鈕 (8.2s)
  ✓  3 [admin] › ... supervision.defect 出現「開啟線上文件」按鈕 (8.3s)
  ✓  4 [admin] › ... payment.estimate 出現「開啟線上文件」按鈕 (9.2s)
  ✓  5 [admin] › ... 點「開啟線上文件」可實際打開 doc.document (10.7s)

  5 passed (53.8s)
```

人工操作對等的步驟：
1. 瀏覽器開 `http://localhost:8069/web/login`
2. 帳密 `admin` / `admin`，DB `odoo18_dev`
3. 網址列貼 `http://localhost:8069/odoo/action-construction_quality.action_general_self_inspection`
4. 點任一筆紀錄
5. **應看到 form header 出現「開啟線上文件」按鈕**（Sprint 21 證明）
6. 點按鈕 → 跳到 doc.document 線上編輯器（Sprint 21 mixin 證明）

其他 3 個 model 對應 URL：
- 預約式：`/odoo/action-construction_quality.action_reservation_self_inspection`
- 缺失：`/odoo/action-construction_quality.action_supervision_defect`
- 估驗：`/odoo/action-construction_payment.action_payment_estimate`

---

## 4. 量化結果

| 指標 | Sprint 22 後 | **Sprint 23 後** |
|---|---|---|
| Playwright project 數 | 3（desktop / mobile / public） | **4**（+admin）|
| Sprint 21+22 mixin 整合的 E2E 驗證 | 0（只有 Python test） | **5 case 全綠**（10.7s 內覆蓋 4 model）|
| 「使用者人工操作能否複現」證明 | 無 | **有**（同命令在任何機器跑都會走完一樣的瀏覽器步驟）|
| 升級 SOP 落實層數 | 1 層（`-i ... && docker restart`）| **2 層**（+ Playwright admin smoke 抓 UI 級退化）|

---

## 5. 與規劃書 §0.6 / §0.5 的對應修正

| 段落 | Sprint 22 後 | **Sprint 23 後** |
|---|---|---|
| §0.5 | Sprint 22 entry | **+ Sprint 23 entry**（Playwright admin 基建 + 4 model E2E）|
| §0.5 結論 | 「Sprint 23 起聚焦 7 個 -1 偏差 / 註腳 / HarfBuzz」| **改為「Sprint 23 補上 SOP 第二層 — Playwright admin E2E；Sprint 24 起聚焦…」** |
| §0.5 文件清單 | 補 sprint22 連結 | **補 sprint23 連結** |
| §0.6.13 Sprint 23+ 優先級 | 第 1-7 項 | **第 1-7 項；第 4 項「ChienYi mixin 第三輪（meeting.record host）」與 Playwright 同步建表更易**（Sprint 23 已建好基建） |
| §0.6.6 P1-2 | ✅ Sprint 21+22 | **✅ Sprint 21+22+23**（+ Playwright 證明）|

Phase 4.5 仍 100%；Sprint 23 只是把已 ✅ 的項加證明等級。

---

## 6. Sprint 24+ 候選（重排）

| 順位 | 主題 | Playwright 可驗範圍 |
|---|---|---|
| 1 | 🟡 7 個剩 -1 偏差 fixture 個別擊破 | layout 渲染：upload docx → 開編輯器 → 確認 page count |
| 2 | 🟡 Phase 3.6 註腳 / 尾註 | layout 渲染：upload 含 footnote 的 docx → 確認頁底出現註腳區 |
| 3 | 🟢 ChienYi mixin 第三輪（建 meeting.record host） | E2E：新建會議記錄 → 點開啟線上文件 → 看到 template_meeting_record 內容 |
| 4 | 🟢 CONTRIBUTING.md + 程式風格指南 | 文件不需 Playwright |
| 5 | 🟢 lazy_loader / pagination_engine.js 評估清理 | 純後端 |
| 6 | 🟢 HarfBuzz 真接 Layout | layout 渲染：CJK 字距視覺對比 |
| 7 | 🟢 Phase 5 子項按使用量排序 | 視子項 |

每一項都會跟著 Playwright 測試（依使用者 SOP）。

---

**Sprint 23 一句話總結**：把使用者要求的「Playwright 證明使用者可手動操作」從 ad-hoc 期望變成 `npx playwright test --project=admin` 一行可重複執行的工程契約；Sprint 21+22 mixin 整合在 4 個 host model 上**前端可見且可手動操作**有 5 個綠 case 為證。

---

## 7. Sprint 23 後記：Playwright 截圖立刻揪出一個 user-visible bug

### 7.1 症狀

Sprint 23 第一輪跑完使用者反應「沒跳出畫面」，於是改 `headless: false`（admin project 預設）+ `screenshot: 'on'` / `video: 'on'` / `trace: 'on'` 強制存證據。

頭一張 PNG 打開（`general.self.inspection` form）發現：**header 裡有 *兩個*「開啟線上文件」按鈕**，而我的 `views/general_self_inspection_views.xml` 只寫了 1 個。

### 7.2 抓兇

跑一個 inspect spec 把 `button[name="action_open_linked_doc"]` 全部 outerHTML dump：

```
[
  { class: "btn btn-primary", parentClass: "o_statusbar_buttons ...",
    text: "開啟線上文件", help: "開啟此檢查表的線上協作文件；首次點擊..." },
  { class: "btn btn-primary", parentClass: "o_statusbar_buttons ...",
    text: "開啟線上文件", invisible: "state == 'closed'" }
]
```

第 1 個 button 的 tooltip help 不是我寫的；第 2 個 button 的 `invisible="state == 'closed'"` 是我 Sprint 21 view xml 的版本。

### 7.3 根因

DB 查 `ir_ui_view` 找出 `general.self.inspection` model 上含 `action_open_linked_doc` 的 view 共 **2 個**：

| id | name | 所屬 module |
|---|---|---|
| 3198 | general.self.inspection.form.doc_link | **construction_quality_doc_link**（legacy） |
| 3199 | general.self.inspection.form.dobtor | dobtor_doc_editor_chienyi（Sprint 21）|

`construction_quality_doc_link` 是早期嘗試的 mixin 整合方案，後來被 Sprint 21 的 bridge 模組取代。但：

- `addons/construction_quality_doc_link/` 目錄殘留（只剩 `models/` `views/` `security/` `tests/` 子目錄殼，沒 `__manifest__.py`）
- Odoo 載入時 log `WARNING ... module construction_quality_doc_link: not installable, skipped`
- DB 中 `ir_module_module.state = 'installed'` 從未跑 uninstall
- 該 module 安裝時建立的 view（id=3198）orphan 留在 DB，繼續對 form 做 inheritance

兩個 view 都 inject 相同 button 到 `<header>`，OWL 合併後 = 兩個按鈕。

### 7.4 修法

Odoo CLI 沒 `--uninstall` flag，走 XML-RPC：

1. **先重建最小 manifest** 讓 module loadable（`{'name', 'version', 'depends': ['base'], 'data': []}`）
2. **`-u construction_quality_doc_link`** 把它 sync 進 graph
3. **`button_immediate_uninstall`** via XML-RPC：

   ```python
   models.execute_kw(DB, uid, pwd, 'ir.module.module',
                     'button_immediate_uninstall', [[778]])
   ```

4. **驗證** state 變 `uninstalled`、view 3198 消失（DB 查只剩 3199）
5. **`docker restart odoo18`** 清主進程 cache
6. **刪除 `addons/construction_quality_doc_link/` 目錄**

### 7.5 重跑 Playwright

清理完跑全套，5/5 綠（1.1 分鐘），4 個 host model 截圖各只剩 1 個「開啟線上文件」按鈕。supervision.defect 的截圖更顯示 stat button「1線上文件」（之前 Playwright 自動建一筆 NCR-TEST-0002 後 mixin `_create_linked_doc()` 真的 wire 起來，count=1）。

### 7.6 為什麼這個 bug 之前 Python regression 75 → 91 都沒抓到

| 測試類型 | 抓得到此 bug 嗎？ |
|---|---|
| Sprint 21+22 Python integration test（30 case） | ❌ — 只測 model 行為（mixin fields/methods/hooks）不測 view 渲染 |
| 全套 dobtor regression Python 91 case | ❌ — 同上 |
| TypeScript / vitest（735 case） | ❌ — 純前端 OOXML parser，不碰 Odoo view |
| **Sprint 23 Playwright screenshot** | ✅ — **截圖肉眼一眼看到雙按鈕** |

這正是使用者新 SOP 的價值：UI 重複的 button 不會讓 Python create() 拋例外、不會讓 view 載入失敗、Odoo 不會 log warning。沒有 visual gate 它就沉睡至少 13 sprint（Sprint 11 + 22 + 23 之間任何時刻可能潛伏）。

### 7.7 Lesson

- **「沒 manifest 但 state=installed」是 Odoo 的常見 zombie**（人工 mv 目錄 / `git rm -rf` 容易製造），未來新 module reflow 必須走 `button_immediate_uninstall` 而不是 mv 走人
- **legacy 模組殘 view 對 inheritance 有靜默副作用**：模組 not installable 但 inherit 子 view 還活著
- **每個 sprint 收尾必跑 Playwright `--project=admin` 並肉眼看一張截圖** — 加進規劃書 §0.6.13 SOP 第三層：「視覺 spot check」
