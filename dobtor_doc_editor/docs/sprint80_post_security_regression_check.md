# Sprint 80：Sprint 79 後三層 SOP regression 驗證

**性質**：mechanical（regression check）
**日期**：2026-05-16

## 0. 一句話

Sprint 79 加了 2 個 ir.rule、可能影響既有 backend test。Sprint 80 跑全套三層 SOP 確認無 regression。

## 1. Result

### 1.1 Odoo backend tests (Sprint 72 一鍵)

```bash
$ docker exec odoo18 bash /mnt/extra-addons/dobtor_doc_editor/tests/scripts/run_backend_tests.sh
... 21 tests ...
2026-05-16 04:40:45 odoo.tests.result: 0 failed, 0 error(s) of 21 tests
✓ All 21 tests passed
```

**21 tests 全綠**（font_serve 12 + zip_guard 9）— Sprint 79 record rules 不影響既有 test。

### 1.2 Vitest

```
Test Files  68 passed | 1 skipped (69)
     Tests  976 passed | 1 skipped (977)
```

**vitest 與 Sprint 64b/68/69 結尾一致** — Sprint 79 是純 ACL XML 變動、不影響 frontend。

### 1.3 三層 SOP 對齊

| 層 | 結果 |
|---|---|
| L1 Vitest | 976 passed + 1 skipped ✓ |
| L2 VR | 0.073191 不變（未跑、但 Sprint 79 無 pipeline 變動）|
| L3 XML well-formed | xmllint OK ✓ |
| L4 Odoo backend tests | 21 passed ✓ |
| L5 module upgrade | clean reload ✓ |

## 2. 紀律啟示

### 2.1 紀律 #1 廣域版（Sprint 80 揭示候選 #15）

紀律 #1（Sprint 57）：改 CanvasRenderer 後強制跑全 42-fixture VR。

→ Sprint 80 揭示廣域版：**改 ACL / record rule / security 後也應該強制跑全套 backend test**。

新紀律候選（第 15 條）：**任何 security-affecting 變動（ACL / ir.rule / `auth='...'`）必須跑相關 test class**。Sprint 80 是這條紀律的第一個 explicit 應用、未來 security PR 應預設執行。

### 2.2 「short sprint 也有價值」

Sprint 80 是 5 分鐘 sprint（一個 bash + 一個 npm + 看結果）、無新 code、無新 audit doc 範疇。**這是健康的 regression check sprint**、不是浪費。

→ 對比 Sprint 50-69 期間沒有 explicit「security PR 後跑 regression」紀律、Sprint 79 + 80 範式可以複製到未來。

## 3. 後續 sprint 候選

- Sprint 81+：Sprint 78 Finding B（doc.document portal company rule、需 user 認可）
- Sprint 82+：紀律 #11 廣域應用 — 其他 model `create_uid` 用法 audit

## 4. 一句話結論

**Sprint 80 確認 Sprint 79 ACL 變動無 regression**（21 backend + 976 vitest 全綠）、揭示紀律 #15 候選（security 變動後必跑 test class）。Sprint 50-80 累積 31 sprints。
