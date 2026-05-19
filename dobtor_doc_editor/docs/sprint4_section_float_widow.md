# Sprint 4 Section break + Float image + Widow rollback

**狀態**：W11+ 主線 Sprint 4 — Layout Engine 進階功能  
**完成日期**：2026-05-07  
**對應規劃**：[dobtor_doc_editor_高保真匯入開發規劃.md §5.4 Phase 3.2 / 3.4](/mnt/d/work/odoo18-docker/addons/dobtor_doc_editor/dobtor_doc_editor_高保真匯入開發規劃.md)  
**前置**：[docs/sprint3_table_layout.md](sprint3_table_layout.md)

---

## 1. 範圍

Sprint 4 補完 Layout Engine 三項殘餘功能：

1. **Section break 全套**（continuous / evenPage / oddPage / nextPage）
2. **Float image entries**（wrapNone / wrapTopAndBottom 完整支援；wrapSquare/Tight/Through 降級 + 警告）
3. **Widow/orphan 完整邏輯**（pre-compute 段落容納行數，整段推下頁防孤行）

落地：

| 檔案 | 變更 | 行數 |
|---|---|---|
| `static/src/core/ooxml/ast/types.ts` | `SectionNode.sectionBreakType?` 新增 optional 欄位 | +13 |
| `static/src/core/ooxml/section/SectionParser.ts` | 抓 `<w:type w:val="continuous|evenPage|oddPage|nextPage">` | +18 |
| `static/src/core/layout/types.ts` | 新增 `FloatImageEntry` | +20 |
| `static/src/core/layout/Paginator.ts` | 重寫 `layoutDocument` + `layParagraph` + `placeFloatImage`；保留 `paginate` 向後相容 | +200 / -40 |
| `static/src/core/layout/index.ts` | 公開 `FloatImageEntry` 型別 | +1 |

**測試**：在 Sprint 3 既有基礎上補 11 個 case。

| 測試檔 | 變更 |
|---|---|
| `tests/unit/layout/SectionBreak.test.ts` | 新檔：11 case（section break / float image / widow） |

**全套**：vitest 497 case 全綠（Sprint 3 後 486 → 497）；Python 54 case 全綠。

---

## 2. 關鍵設計決策

### 2.1 SectionNode `sectionBreakType` optional 設計

OOXML 規格 `<w:type>` 的 `w:val` 預設為 `nextPage`。**SectionParser 只在非預設值時寫入 `sectionBreakType`**，保留 `undefined` 表示 `nextPage`。

理由：避免影響 Sprint 1 建立的 [04_ast_snapshot](../tests/integration/04_ast_snapshot.test.ts) 的 42 份 snapshot — 大部分 fixture 用預設值，不該因為新增欄位炸掉 snapshot。

### 2.2 layoutDocument 全程共用單一 ctx

Sprint 3 的 layoutDocument 為每節創建新 ctx，section 切換時 pages 會丟失（已在 Sprint 4 修復）。Sprint 4 改成：

```
ctx = makeContext(sections[0])
for sec in sections:
  if i > 0:
    if prevBreak === 'continuous' && samePageGeometry: keep ctx
    else: flushPage; ensurePageParity; rebindCtxToSection(sec)
  layoutSectionInto(sec, ctx, options)
flushPage  // 最後收尾
```

`rebindCtxToSection` 只更新 page geometry / margins / sectionIndex，**保留 pages / warnings / pageNumber 累計**。

### 2.3 Section break 行為對照表

| breakType | 行為 |
|---|---|
| `nextPage`（預設） | flush 上節最後一頁，下節從新頁開始 |
| `continuous` | 同 page geometry 時：不 flush，下節從當前 currentY 繼續；不同 geometry 時降級為 nextPage |
| `evenPage` | flush 後若下頁編號為奇數，插一張空白頁；下節從偶數頁開始 |
| `oddPage` | 對稱處理，下節從奇數頁開始 |

### 2.4 Float image：wrap 模式分組處理

OOXML 7 種 wrap 模式 → Sprint 4 分三組：

| wrap mode | 處理 | 對 currentY 影響 |
|---|---|---|
| `topAndBottom` | 完整支援（保留垂直空間） | currentY += img.height |
| `none` / `behindText` / `inFrontOfText` | 完整支援（圖層獨立） | 不擠壓 currentY |
| `square` / `tight` / `through` | 降級為 topAndBottom + warning | currentY += img.height |

**降級理由**：完整 wrapSquare 需要 LineBreaker 支援「lineWidth 隨 y 動態變化」（行寬在圖片左/右側時要扣掉圖寬），這是 Knuth-Plass + box/glue model 的進階用法。Sprint 4 留 warning，標記 Sprint 5 補完。

### 2.5 Widow/orphan 完整邏輯（已可工作版本）

**pre-compute 策略**（不需回退已 push 的 entries，比 Sprint 2 的「不回退簡化版」更可靠）：

1. 段落 break 為 N 行
2. 計算當前頁能容納 K 行（`(contentHeight - currentY - spaceBefore) / lineHeight`）
3. 若 N - K > 0 且 K < orphanMin：整段推下頁（**孤行控制**）
4. 若 N - K > 0 且 N - K < widowMin：整段推下頁（**寡行控制**）
5. 否則：當前頁放 K 行，剩 (N - K) 行進下一頁

由於是 pre-compute，**永不需要回退 ctx.entries**，避免 Sprint 2 的「不回退簡化版」可能殘留的不理想斷點。

代價：必須先算所有 lines（已是現行流程），再決定整段推否。但這已是 LineBreaker 的自然輸出，沒額外開銷。

---

## 3. fixture 統計變化（Sprint 3 → Sprint 4）

| 類別 | Sprint 3 avgPages | Sprint 4 avgPages | 變化 |
|---|---|---|---|
| 01_simple | 1.9 | 1.9 | 持平 |
| 02_std_table | 1.6 | 1.6 | 持平（avgLines 從 10 → 9，widow 整段推下頁） |
| 03_complex_table | 1.0 | 1.0 | 持平 |
| 04_with_image | 2.7 | 2.7 | 持平（fixture 含 inlineImage 為主，無 floatImage） |
| 05_header_footer | 4.2 | 4.2 | 持平 |
| 06_template | 1.3 | 1.3 | 持平 |

**讀法**：
- 大多數 fixture 是單 section 文件，不會經過 section break 路徑
- 42 份 fixture 中**沒有 floatImage**（圖片都是 `inlineImage`），所以 Sprint 4 的 floatImage entry 在 smoke test 觸發為 0 — 由 SectionBreak.test.ts 的合成 fixture 驗證
- 02_std_table avgLines 從 10 → 9：widow 完整邏輯在某些段落把整段推下頁，導致每頁實際排版的 line entry 略減
- 02_std_table avgPages 仍 1.6：widow 推下頁但仍在同一張頁（因為頁內還有空間）

---

## 4. Sprint 4 已知限制（→ Sprint 5+ 補完）

| 限制 | 原因 | 補完 Sprint | 對應規劃 |
|---|---|---|---|
| wrapSquare / wrapTight / wrapThrough 行寬動態變化 | 需 LineBreaker per-y 變寬 | Sprint 5 | §3.4 |
| 多欄 multi-column | Paginator 單欄假設 | Sprint 5 | §3.5 |
| 巢狀表格 | layoutCell 只看 paragraph | Sprint 5 | §3.3 |
| Cell 內部 mid-row break | 簡化跨頁演算法 | Sprint 5 | §3.3 |
| Knuth-Plass 精細斷行 | 貪婪算法 baseline 已穩定 | Sprint 6+ | §3.1 |
| 表格邊框衝突解決（OOXML 17.4.65 8 級優先） | 留 Renderer 處理 | Sprint 5（Renderer） | §3.3 / Phase 4 |
| HarfBuzz 字型實測 metrics | EstimateMetrics 偏差 ±5% | Sprint 6+ | Phase 2 |
| 註腳 / 尾註 | Paginator 無 footnote 區概念 | Sprint 6+ | §3.6 |
| floatImage Y 座標 vs anchor 段落計算 | 簡化為段落 currentY | Sprint 5 | §3.4 |

---

## 5. 對 Sprint 1/2/3 回歸護欄的影響

| 回歸護欄 | 影響 | 結果 |
|---|---|---|
| `04_ast_snapshot.test.ts`（Sprint 1） | SectionNode 新增 optional 欄位，**只在非預設時寫入** | 42 case 全綠 |
| `05_parser_audit.test.ts`（Sprint 1） | 無 | 8 case 全綠 |
| `06_layout_smoke.test.ts`（Sprint 2/3） | 行為微調（widow 完整版） | 48 case 全綠 |
| Sprint 2/3 unit tests | 無打破 | 所有 case 全綠 |
| Python integration（54 case） | 無關 | 全綠 |

**vitest 全套**：29 files / **497 tests pass**（Sprint 3 後 486 → 497，新增 11 case）。

---

## 6. 驗證指令

```bash
# 完整 vitest（28 → 29 files；486 → 497 cases）
cd addons/dobtor_doc_editor && npm test

# 只跑 Sprint 4
npx vitest run tests/unit/layout/SectionBreak.test.ts

# Python 全套
docker exec odoo18 odoo -c /etc/odoo/odoo.conf -d odoo18_dev \
  -u dobtor_doc_editor --test-tags dobtor_doc_editor \
  --stop-after-init --http-port=8169 --workers=0
```

---

## 7. 下個 Sprint（Sprint 5）

依規劃 §3.4 + §3.5 + §3.3 殘餘工作，建議優先：

1. **wrapSquare/Tight 行寬動態**（§3.4）
   - LineBreaker 支援 per-y `lineWidth` callback
   - Float image 成為「行寬侵蝕區域」
2. **多欄 multi-column**（§3.5）
   - Paginator 從單欄改為依 SectionNode.columns 切多欄流
   - Column balancing（末頁欄平衡）
3. **Cell 內部 mid-row break**（§3.3 殘餘）
   - 允許 cell 內 paragraph 跨頁（最複雜）
4. **巢狀表格**（§3.3 殘餘）
   - layoutCell 偵測 cell content 含 TableNode，遞迴呼叫 layoutTable

Sprint 5 完成後預期：
- 真正含浮動圖片的合成 fixture（或 W12 在新 fixture 加入）能 wrapSquare 跑通
- 02_std_table 週報若有多欄區塊能正確排版

---

**附註**：對應計畫檔 [federated-swimming-creek.md](/home/chichi/.claude/plans/federated-swimming-creek.md) 的「W11+ 進入主線 Sprint 1（OOXML Parser 補完）」之後的 Sprint 4。
