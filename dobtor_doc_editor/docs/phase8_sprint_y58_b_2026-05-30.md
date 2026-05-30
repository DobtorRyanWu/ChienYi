# Sprint Y58 — B：CLI flag + Python controller 透傳

- **建立日期**：2026-05-30
- **前置**：Sprint Y58 A（commit `6143330`）—— mapper 兩個 opt-in flag、預設 false
- **狀態**：Sprint B 完成、停下待 user review；未進 Sprint C

---

## 1. 範圍

Sprint A 把 mapper 兩個新 option 接上但**整條 Phase E controller 路徑沒人會傳 flag**。Sprint B 把 CLI 與 Python controller 的 opt-in 介面補完，預設行為與 Sprint Y58 A 完全相同 — 不傳 flag 等於什麼都沒發生。

## 2. 改動檔案

| 檔案 | 性質 | 改動摘要 |
|---|---|---|
| `tools/parse_docx_cli.ts` | 既有 | 加 `--float-textbox` / `--anchored-image` 兩個 flag、CliArgs 介面對應擴張、ToCanvasEditor 構造帶上 mapper 兩個 option、stdout `OK:` 加 `flags=...` 摘要、usage 訊息更新、檔頭註解列出新 flag |
| `tools/dist/parse_docx_cli.cjs` | 既有 build artifact | `npm run build:cli` 重 bundle（38.3s） |
| `controllers/doc_controller.py` `_ts_parse_docx_to_elements` | 既有 | function signature 加 `float_textbox=False, anchored_image=False` 兩個 kwarg、subprocess argv 條件性 append flag、docstring 更新 |
| `controllers/doc_controller.py` `/dobtor_doc/import` route | 既有 | 從 form / query string 解析 `float_textbox` / `anchored_image`（接受 `1/true/yes/on` 為 true）、往下游 `_ts_parse_docx_to_elements` 透傳 |
| `controllers/doc_controller.py` `/dobtor_doc_editor/test_data` route | 既有 | JSON-RPC 多接 `float_textbox` / `anchored_image` 兩個 kwarg，給 Phase F visual_regression_harness 用 |
| `tests/integration/sprint_y58_cli_flags.test.ts` | 新檔 | 9 個 spawnSync 真實 CLI 整合測試 |

## 3. 設計決策

### 3.1 兩 flag 預設 false / 向後相容
- `_ts_parse_docx_to_elements` kwarg 預設 `False` → 既有 caller（例如未來其他模組叫這條 helper）不需改
- subprocess argv 條件性 append → 舊版 CLI 二進位**也能正常跑**（舊 CLI 遇未知 flag 靜默忽略、不 crash，由 sprint Y58 第 7 個整合 test 鎖死）
- HTTP route opt-in：用 `_truthy()` helper 接受 `1/true/yes/on` 五種寫法（前端 `?float_textbox=1` 與 RPC payload `{float_textbox: true}` 都吃）

### 3.2 stdout `flags=...` 摘要（review 階段提出的補強）
```
OK: parsed in.docx → out.json (mode=elements, flags=float-textbox+anchored-image, 281427 bytes)
OK: parsed in.docx → out.json (mode=elements, flags=none, 273470 bytes)
```
- Odoo log 直接看得到「controller 真的傳對 flag 了沒」
- 無 flag 時印 `flags=none` 而非空字串，避免文字截斷誤解
- Sprint Y58 整合測試 6 個案例都鎖這個格式

### 3.3 部署落差安全網（已存在 Sprint 358-359 紀律 + 本 sprint 新測試）
```python
# 舊版 CLI 遇未知旗標會優雅忽略、不 crash，故部署落差安全。  ← 既有註解
argv = ['node', cli_path, in_path, out_path, '--elements', '--svg-graphics']
if float_textbox: argv.append('--float-textbox')      # Sprint Y58
if anchored_image: argv.append('--anchored-image')    # Sprint Y58
```
若 Python controller 已升級但 CLI 尚未 rebuild，Sprint Y58 整合測試案例 7（`遇到未知 flag 不 crash、靜默忽略`）覆蓋此情境。

### 3.4 `test_data` route 同步透傳
Phase F visual_regression_harness 透過 RPC `/dobtor_doc_editor/test_data` 取 IElement[]，Sprint C 端對端真實渲染會 reuse 這條路徑、需要能傳 flag。本 sprint 一起補上避免 Sprint C 又改 controller。

## 4. 驗證

### 4.1 真實 CLI 對 Sprint Y57 fixture 跑通

```
$ node tools/dist/parse_docx_cli.cjs 03.1120815-監造會議記錄.docx out_y58.json \
    --elements --float-textbox --anchored-image
OK: parsed ... → ... (mode=elements, flags=float-textbox+anchored-image, 281427 bytes)
```

Python 遞迴掃輸出 JSON：

| 指標 | Y57 audit（無 flag） | Sprint Y58 B（兩 flag） |
|---|---|---|
| `"第X頁，共Y頁"` 正則匹配 | **0** | **4**（4 個非空 anchor 全展平） |
| 帶 `.anchor` extension 的 IElement | **0** | **5**（4 非空 + 1 空 `\n` 終止符） |

5 個 anchor source 全是 `floatTextBox`，符合 fixture 內容（無嵌入圖片）。

### 4.2 新 integration test（9 個全綠）

```
tests/integration/sprint_y58_cli_flags.test.ts (9 tests) 3241ms

CLI flag 真實路徑透傳
  ✓ 預設無 flag：CLI 不展平頁碼 textbox（與 Y57 audit 一致）
  ✓ --float-textbox：4 個非空 anchor 頁碼字串都展平進 IElement
  ✓ --anchored-image 單獨：textbox 不展平故沒有對應 IElement，故無 anchor 透傳
  ✓ --float-textbox + --anchored-image：頁碼字串展平 + anchor.source=floatTextBox
  ✓ --svg-graphics + --float-textbox + --anchored-image：三 flag 都能正確透傳

CLI 部署落差安全網
  ✓ 缺參數時 usage 訊息包含 --float-textbox / --anchored-image
  ✓ 遇到未知 flag 不 crash、靜默忽略

模擬 Python controller subprocess 真實呼叫
  ✓ controller 預設不傳兩 flag：產出與 Sprint 358-359 後路徑 byte-identical
  ✓ controller opt-in（兩 flag=true）：真實 controller subprocess argv 達成完整透傳
```

實作方式：每個 case 用 `child_process.spawnSync('node', [CLI, FIXTURE, out, ...flags])`，直接驅動已 build 的 `tools/dist/parse_docx_cli.cjs`，等同 Python controller subprocess 路徑。**不 mock 任何環節**。

### 4.3 既有測試不退步

| 套件 | Sprint A 後 | Sprint B 後 |
|---|---|---|
| `tests/unit/ToCanvasEditor.test.ts` | 46 passed | 46 passed |
| `tests/unit/sprint_y58_float_textbox_anchor.test.ts` | 9 passed | 9 passed |
| `tests/integration/03_e2e_mapper.test.ts`（67 fixture） | 67 passed | 67 passed |
| `tests/integration/sprint38_anchor_textbox_real.test.ts` | 1 passed | 1 passed |
| **全 test suite** | 3150 / 8 skipped | **3159 / 8 skipped / 0 failed**（+9 from Sprint B） |

`03_e2e_mapper` 67 份 fixture IElement 平均數與 baseline 完全一致 → mapper 預設行為 byte-identical 保證。

### 4.4 Python lint
```
$ flake8 --max-line-length=120 --extend-ignore=E501,W503 --select=E9,F63,F7,F82 \
    addons/dobtor_doc_editor/controllers/doc_controller.py
(no output)

$ python3 -c "import ast; ast.parse(open('controllers/doc_controller.py').read())"
AST parse OK
```

## 5. 範圍紀律

### 已做
- CLI `--float-textbox` / `--anchored-image` flag + stdout 摘要
- rebuild `tools/dist/parse_docx_cli.cjs`
- Python `_ts_parse_docx_to_elements` 兩個 kwarg
- HTTP route `/dobtor_doc/import` 與 RPC `/dobtor_doc_editor/test_data` 接收 query/form
- 9 個 spawnSync 真實 CLI 整合測試

### 沒做（留給 Sprint C / D）
- **前端 `doc_editor.js` 不會傳新 flag**：前端 default behavior 不變、production import 仍走「無 flag」路徑。要 ship 給使用者要再加 1 個 UI 開關或預設改 true，這是 Sprint C/D 後的 product decision
- **15 份 ChienYi docx 端對端真實渲染**：Sprint C 把 9 monitoring docx 加上 6 個（5 監造會議 + 5 週報 + 5 查驗 - 1120815 = 14 + 1 = 15 個 case）跑 headless canvas-editor 截圖
- **commit-lock integration test**：Sprint D（與 Sprint B 整合測試的分工：B 鎖 CLI flag 透傳機制；D 鎖 15 份 docx 真實視覺）

## 6. Sprint C 預告

範圍：
1. 設計 puppeteer + canvas-editor UMD harness（reuse `tests/integration/sprint_y58_cli_flags.test.ts` 拿 IElement[] → 餵 visual_regression_v14 pipeline）
2. 15 份 fixture：
   - `01_simple/`：1120210 / 1120815 / 1120822 / 1120829 / 1120905（5 監造會議）
   - `02_std_table/`：1120928 / 1121006 / 1121013 / 1121020 / 1121027（5 週報）
   - `03_complex_table/`：1121229-全套管 / 1130105-全套管 / 1130109-全套管 / 1130112-全套管 / 1130516-共月橋 P3（5 查驗）
3. 對每份跑「無 flag」與「兩 flag」兩條截圖、比對：
   - 有 flag：textbox 文字應在頁面上看得到（OCR 或 IElement 文字 spot check）
   - 預設：與既有 golden 一致（VR mean 不退步）
4. 產出 `tests/fixtures/sprint_y58_vr_report.json`

預估改動 ~50 行（多半在新 mjs script + harness HTML）+ 不動 production code。

## 7. 等待 user review

- [ ] Sprint B CLI flag 命名與 stdout 摘要格式（user 是否要不同命名 / 不同訊息？）
- [ ] HTTP route query string 接受 `1/true/yes/on` 五種 truthy（避免太鬆 / 太緊）
- [ ] 是否要 commit Sprint B 再進 Sprint C
- [ ] Sprint C 範圍是否如上預告
