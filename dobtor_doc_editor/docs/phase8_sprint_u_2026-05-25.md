# Phase 8 Sprint U — E2E login JSON-RPC 改寫 + canvas-editor replace() 探路報告（2026-05-25）

**性質**：基礎建設修正 + 探路報告（規畫之 Sprint U 改 search()/replace() 路徑，因環境阻擋未完成）。
**範圍**：[admin-dobtor-doc-editor-sprint-ghn.spec.ts](../../../tests/playwright/tests/admin-dobtor-doc-editor-sprint-ghn.spec.ts) `loginAsAdmin` 改用 JSON-RPC、繞過 form-fill 問題。

---

## 1. 動機：跑「你自己驗證」E2E 時撞到的第二層阻擋

Sprint T revert + skip 兩個 fail test 後，再跑剩下的 G.1 也卡：

```
Error: page.fill: Test timeout of 180000ms exceeded.
- locator resolved to <input id="login" type="text" name="login"...>
- fill("admin")
- attempting fill action
- retrying fill action × N
```

probe 揭：construction_portal 客製 login 表單裝了 `web.user_switch` widget、原 `<form>` 帶 `class="oe_login_form d-none"`（display:none），form 內 button 是 visibility-hidden。`force:true` fill 可以寫值、但 click submit 也卡（element not visible）。

跟構件相關，不是 Sprint T 的代碼問題。但**整個 admin E2E suite** 都會撞這個（Sprint F 之前能跑是因為當時 construction_portal 未啟用 user_switch widget，或 cookies remembered）。

---

## 2. 修補

`loginAsAdmin` 改走 JSON-RPC 直接拿 session、避開 DOM 互動：

```js
async function loginAsAdmin(page: Page) {
  const resp = await page.request.post(`${BASE_URL}/web/session/authenticate`, {
    data: {
      jsonrpc: '2.0', method: 'call',
      params: { db: DB, login: ADMIN_USER, password: ADMIN_PASSWORD },
    },
  });
  const json = await resp.json();
  if (json.error || !json.result?.uid) {
    throw new Error(`auth failed: ${JSON.stringify(json)}`);
  }
  await page.goto(`${BASE_URL}/odoo`);
  await page.waitForLoadState('domcontentloaded');
}
```

優點：
- 完全跳過 form-fill / click submit
- 不受 construction_portal 客製 login 影響
- 比 form 流程快（~1s vs 5-10s）

缺點：
- session 走 cookie、不會触發 login 流程的 hooks（如登入 audit log）
- 對「驗證 login UX」類測試不適用——但本 suite 是驗證 doc editor、不是 login

---

## 3. 原 Sprint U 規畫（canvas-editor search/replace 探路）— 未完成

Sprint T §6 列為未來突破口的第一條：**用 search() + replace() 跳過 element 操作**。

probe 計畫：
1. 載入 `<p>{{ project_name }}</p>` (multi-char element)
2. `editor.command.search('{{ project_name }}')`
3. `editor.command.replace('REPLACED_MARKER')`
4. dump `getValue().data.main` 看結構

**未完成原因**：probe 通過 login 後撞第二層問題——`/odoo/action-dobtor_doc_editor.action_doc_editor?doc_id=N` URL 不接 query param（client action context 不從 URL query 取）。要正確開 editor 需要：
- 走 form view 點按鈕（doc_document form），但 form view 在前述 login fix 後仍然 routing 不過去
- 或 web client doAction RPC（複雜、需 wow framework knowledge）

**留 Sprint V+ 處理**：要 probe canvas-editor 內部行為，需要先建一條穩定的 E2E 進入 editor 的途徑。可能方向：
- 用 form view 並用 JSON-RPC 改 doc.document.state 模擬 user 點按鈕
- 加一個 `?open_editor=1` URL handler 給測試專用
- 或直接打 backend Python test 不走瀏覽器

---

## 4. 驗證

### Spec 靜態驗證

```
$ npx playwright test admin-dobtor-doc-editor-sprint-ghn --list
3 tests in 1 file (G.1 active, HN.1/J.1 skip per Sprint T)
```

### Live run 狀態

| Test | Status |
|---|---|
| G.1 — 掃描變數建 record | **login JSON-RPC fix 後可跑**；但接下來開 editor 那段 routing 仍 broken（同 §3 探路撞到的問題）|
| HN.1 / J.1 | `test.skip` per Sprint T（auto-merge 架構衝突）|

換言之：本 sprint **只 deliver 一半**——login 解了，editor URL 沒解。但 login fix 是純基礎建設改進、值得 commit；下次 session 修 editor URL 路徑後就能完整跑。

---

## 5. 進度更新

| Sprint | 狀態 |
|---|---|
| G-S | ✅ |
| T 多字元元素衝突文件化 | ✅ |
| **U E2E login JSON-RPC 修補 + replace() 探路（半完成）** | 🟡 |

預期 Sprint V：修 admin E2E editor URL routing（or pivot 到 backend Python 端 unit test），完整跑 G.1 + 重啟 replace() 探路。
