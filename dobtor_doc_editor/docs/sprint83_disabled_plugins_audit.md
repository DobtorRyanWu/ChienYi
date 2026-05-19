# Sprint 83：disabled plugin files audit（HTML/Wysiwyg era 遺物）

**性質**：純診斷
**日期**：2026-05-16

## 0. 一句話

`__manifest__.py` line 73-85 disabled 10 個 plugin files（HTML/Wysiwyg 時代遺物）、實體檔案仍在 disk 上 76KB。Sprint 83 audit 是否可刪。

## 1. Findings

Disabled in manifest（assets bundle 不引用）：

| 路徑 | 大小 | 用途（已停用）|
|---|---|---|
| `static/src/plugins/` | 52KB | font-family / font-size / line-height / multi-column / table-merge / list-type / formatting_plugins.xml |
| `static/src/js/plugins/` | 24KB | doc_page_format / doc_export / doc_odoo_field |

→ 合計 76KB disk、0 KB bundle（disabled）→ **no production impact**、只是 repo bloat。

## 2. 修法評估

| 選項 | 評估 |
|---|---|
| A. 直接刪 | 風險：未來想復用得 git revert，但 disabled 已 4+ sprint、回去機率低 |
| B. 移到 `archive/` 目錄 | 留檔保留 history、明確標 dead |
| C. 留著不動 | 76KB 不算 bloat |

考慮 ChienYi 多人開發、選 **C** — 註解已 explicit 標「HTML/Wysiwyg 時代舊資源，已停用（保留備查）」、足夠 communicate intent。

## 3. 結論

Disabled plugins 是 **由設計保留**、不是 dead code blocker。Sprint 83 audit 確認 "intentional dead code with rationale"、無需動。

→ 紀律候選（第 16 條）：**disabled code 必須有 explicit rationale 註解**、否則應該刪。當前 dobtor_doc_editor 符合（line 71 「以下為 HTML/Wysiwyg 時代舊資源」）。
