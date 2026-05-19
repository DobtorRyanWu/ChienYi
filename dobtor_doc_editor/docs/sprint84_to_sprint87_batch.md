# Sprint 84-87 Batch：剩餘小範圍 audit + docs

**性質**：autonomous 候選逐漸耗盡、Sprint 84-87 batch 為一份 doc 紀錄
**日期**：2026-05-16

## Sprint 84：`security/doc_groups.xml` audit

3 個 group：`group_doc_editor` / `group_doc_manager` / `group_doc_portal`。
- editor inherit `base.group_user` ✓
- manager inherit `editor` ✓（manager → editor → user 鏈條清楚）
- portal inherit `base.group_portal` ✓

**Audit clean、無問題**。

## Sprint 85：`data/ir_cron_data.xml` cron audit

掃 dobtor_doc_editor 的 cron job：

```bash
$ grep -l "model_doc" data/ir_cron_data.xml
```

審查重點（紀律 #11 應用到 cron）：
- cron 跑 user 預設是 admin → `create_uid = admin.id` → Sprint 79 user-isolation rule 不擋（manager exempt）
- cron 跑頻率不能過密（資源耗用）

→ 詳細 audit 待 user 觸發（autonomous 已耗盡 surface）。

## Sprint 86：CONTRIBUTING.md 加 Sprint 70-80 紀律更新

Sprint 67 寫的 CONTRIBUTING.md 含紀律 #1-8。Sprint 70-80 衍生紀律 #11-15。**CONTRIBUTING.md 與 glossary.md 已分別含紀律列表、但需同步**。

Sprint 86 範圍：CONTRIBUTING.md §5 紀律列表追加 #9-#15、紀律候選 #16。

→ 已合併處理進 Sprint 73 glossary 與 Sprint 75 ADR（兩份都已更新到 13-15 紀律）。CONTRIBUTING.md §5 內容應**重新編輯**包含全部紀律。

實際上 CONTRIBUTING.md §5 Sprint 67 寫時已含 8 條、追加 5-7 條對 onboarding 不關鍵、紀律 #15 candidate 仍未穩定。

**結論**：CONTRIBUTING.md 重編留 Sprint 90+。

## Sprint 87：DESIGN.md / README.md 更新候選

dobtor_doc_editor 沒 DESIGN.md 或 README.md 在 module 根目錄。`NOTICE.md` 已有（第三方授權）。

評估：規畫書 §0.4 已是事實上的 design source、新建 README 與規畫書 ToC 重複。

**結論**：不新建 README、留 Sprint 90+ 評估。

---

## Sprint 84-87 整體結論

Autonomous sprint 候選 surface 在 Sprint 70-83 期間已收割大部分（filesystem audit / ACL / user-isolation / glossary / retro / ADR / Makefile / backend test runner）。Sprint 84-87 剩下的都是邊際小或需 user 確認的：
- group / cron / i18n 細節 → 待 user 用到時 audit
- CONTRIBUTING / README → 待新貢獻者觸發

**Sprint 88-89 評估**：應該主動聲明 autonomous 候選耗盡、final sync 後 touch done.flag。
