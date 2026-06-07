# Contributing to dobtor_spreadsheet_editor

> **Sprint 0 起點檔**。22 條紀律完全繼承自 `dobtor_doc_editor/CONTRIBUTING.md §5`（適用本模組），加上 5 條 xlsx 特化候選 X1-X5。
> 隨 sprint 累積會擴充至完整版（同 dobtor docx 模式：紀律編號 + Why + How to apply + Sprint 教訓案例）。

---

## 1. 環境

### 1.1 系統需求
- Docker Desktop（WSL2 backend）
- Odoo 18 container `odoo18` 已啟動、DB `odoo18_dev` 已 init
- node 20+、npm 10+
- WSL host 已裝 LibreOffice 24+（golden 產生用）

### 1.2 容器與資料庫
- 容器名：`odoo18`
- DB：`odoo18_dev`
- container Python 已裝：openpyxl 3.1.2、python-calamine

### 1.3 升級 SOP（兩步驟缺一不可）
```bash
docker exec odoo18 odoo -c /etc/odoo/odoo.conf -d odoo18_dev \
    -u dobtor_spreadsheet_editor --stop-after-init && docker restart odoo18
```
詳見 ChienYi `CLAUDE.md` 的「升級 SOP 兩步驟」說明。

---

## 2. Make targets（Phase 4.5 啟用後加入）

```bash
make build        # rollup + typecheck
make test         # vitest run
make vr           # visual regression（Phase 4+）
make golden       # 重新產生 50 fixture golden PNG + JSON
make health       # 跑 health 檢查（vitest + VR + round-trip）
make upgrade      # docker exec upgrade module
```

---

## 3. 三層測試 SOP

| 層 | 工具 | 通過標準 |
|---|---|---|
| **L1** | Vitest `npm test` | 全綠（0 failed） |
| **L2** | Visual regression `scripts/visual_regression_xlsx.mjs` | mean diff ≤ baseline、0 failed pages |
| **L3** | Round-trip + 人工 | 50 fixture round-trip pass rate > 90%、人工抽檢 3 份 ChienYi xlsx 樣式不退化 |

任何 commit ship 前必須三層全綠。

---

## 4. 程式碼風格

### 4.1 TypeScript（前端）
- ESLint + Prettier（沿用 dobtor_doc_editor 配置）
- 嚴格型別：`strict: true`、不准 `any`（必要時用 `unknown` + narrow）
- 檔案命名：PascalCase 類別、camelCase 函式、kebab-case 目錄
- OOXML 元素 → AST：`<DomainParser>.ts` 命名（如 `WorksheetParser.ts`、`StylesParser.ts`）
- AST 型別：`<Domain>Ast` 後綴（如 `WorkbookAst`、`CellAst`）

### 4.2 Python（後端 controller / model）
- PEP 8
- 欄位 `string` 用繁體中文（Odoo 標籤）
- 欄位 name 英文 snake_case
- 不加無意義 docstring（紀律參考 dobtor docx）

### 4.3 Odoo XML（views / templates）
- 沿用 ChienYi `CLAUDE.md` 規範（chatter、t-attf-class、t-attf-onclick 等）

---

## 5. 開發紀律

### 5.1 從 dobtor_doc_editor 繼承的 22 條紀律

**完整定義見** `/mnt/d/work/odoo18-docker/addons/dobtor_doc_editor/CONTRIBUTING.md §5`。

精簡摘要（依編號）：

| # | 名稱 | 核心 |
|---|---|---|
| 1 | 改 renderer 強制跑全 VR | 單元測試綠 ≠ VR 綠；改渲染層必跑全 fixture VR |
| 1.a | parser/style/layout 變動仍跑 VR + bundle rebuild | 即使預期 VR 不變、bundle 變動可能引發 surprise |
| 1.b | Spike 後結構性問題必須 scope-down 或完整 revert | 不做「微調 + retry」 |
| 2 | 雙驗紀律 | Unit test 驗 API、VR 驗 pixels — 兩者都綠才算過 |
| 3 | 高風險前先 probe sprint | 診斷 sprint 與實作 sprint 分開 |
| 4 | 負面結果有結構價值 | Audit doc 誠實記錄 hypothesis vs result |
| 5 | vitest ≠ IIFE bundle | IIFE-only smoke test 必跑 |
| 6 | Promote 前做 per-fixture delta | 量化 worst-case regression；0 fixture 退化才 promote |
| 7 | Mechanical commit 內化多 sprint 投資 | 一行改動可能是 5 sprint 累積 |
| 8 | 架構發現 sprint 也要記下來 | 開工前 60 秒 grep 比中途撞牆便宜 |
| 9 | 規畫書 §附錄 A `[ ]` 項是優先選擇 | Autonomous loop 時選未打勾項 |
| 10 | Catch-up sprint 補到當前標準 | 不停在「最低限度」 |
| 11 | Filesystem 路徑 cross-check production | dev 環境 ≠ container |
| 11.a | X-assumes-Y 都需 cross-check | filesystem / library imports / env vars 全適用 |
| 11.b | ACL 也是 access path | record rule audit；create_uid 防偽造、rate limit 防膨脹 |
| 12 | test class 必須 explicit tag | 漏項 = silent skip = dead test |
| 13 | backend test 定期跑機制（候選） | CI gate 才是 closure |
| 14 | docs / audit / ADR 即時同步（候選） | 不要事後 catch-up |
| 14.b | Working tree drift enforce | 每 sprint commit 收口 clean |
| 15 | Security 變動後跑 test class（候選） | ACL / ir.rule / auth 改動 → 必跑相關 test |
| 16 | Disabled code 需 explicit rationale | 註明「為何 disabled、何時可移除」 |
| 17 | **已 revert** | 紀律 #18 取代 |
| 18 | 開工大型新 feature 前必須先對齊規畫書真實 scope | 規畫書 scope 內推進；不順便加新功能 |
| 18.a | 「根據計劃繼續執行」是 scope 限制詞 | 副條款 |
| 21 | optional 欄位空集合不掛 key | AST 對齊規約 |
| 21.a | key 即 binary signal（潛在子原則） | 紀律 #21 例外判斷 |
| 22 | backlog 開工前先 probe sprint | 確認 mental model vs 實況差距 |

**最重要的紀律 #18**：開工大型新 feature 前必須先對齊規畫書真實 scope。新 feature 與規畫書不符 → 優先誠實 revert、不是合理化保留。

### 5.2 xlsx 特化紀律候選（Sprint 0 提出、累積 sprint 教訓後升正）

#### 候選 X1：改 FormulaCompiler 強制跑全 fixture cell value diff
**Why**：FormulaCompiler 是 Phase 3 主戰場。R1C1 / structured ref / array formula 任一改動可能影響整個 sheet 的 cell value。Unit test 綠不代表 50 fixture 的 cell value 全綠。
**How to apply**：改 `formula/FormulaCompiler.ts` 任何函式 → 強制跑 `scripts/cell_value_diff.mjs` 對所有 fixture，0 退化才 ship。

#### 候選 X2：新增缺失函數 shim 必須有對照 Excel 行為的 test case
**Why**：Excel 公式行為在邊界值（空 / 0 / 負 / 文字 / 錯誤值）有獨特方言。盲目 shim 會破壞 ChienYi 估驗試算。
**How to apply**：每個 `MissingFunctions.ts::register*` 必須附 test：normal + empty + zero + negative + text + error 6 個 case。

#### 候選 X3：StyleResolver 改動必須跑 dxf 對照
**Why**：CF 用 dxf（differential format）、cell 用 cellXf（cell format）。兩者邏輯易混淆，曾在 LibreOffice oox parser 出現多個 regression。
**How to apply**：改 `style/StyleResolver.ts` → 跑 04_conditional_format/ 全部 fixture VR + cell style diff。

#### 候選 X4：xlsx round-trip pass rate 退化 > 2% 必須 hold ship
**Why**：Round-trip 是 ChienYi 估驗實際 workflow（編輯後下載）。退化會直接損害 user。
**How to apply**：CI 跑 `scripts/round_trip_test.mjs`、計算 pass rate；與上次 baseline 對比、退化 > 2% 不准 ship。

#### 候選 X5：o-spreadsheet plugin API 變動須 cross-check Odoo upstream
**Why**：策略 (d) Hybrid 依賴 public API。Odoo 18.0.49、18.0.50 升級可能變動 `addFunction` / `CorePlugin` 簽名。
**How to apply**：每月跑 `scripts/check_o_spreadsheet_version.sh` 比對 capability_audit.md 記錄的 API、有變動立即 alert。

---

## 6. CI gates（Phase 4.5 啟用後配置）

```yaml
# .github/workflows/ci.yml（規劃）
jobs:
  test:
    steps:
      - npm test
      - npm run typecheck
      - npm run build:frontend
      - npm run vr  # Phase 4+
      - docker exec odoo18 odoo --test-tags dobtor_spreadsheet_editor --stop-after-init
```

---

## 7. 文件即時同步（紀律 #14）

- ADR 寫完當下決定，不要事後 catch-up
- `docs/INDEX.md`、`docs/progress_snapshot.md` 每 sprint 結尾更新
- `dobtor_spreadsheet_editor_高保真匯入開發規劃.md` 的 `- [ ]` / `- [x]` 隨 sprint 同步打勾
