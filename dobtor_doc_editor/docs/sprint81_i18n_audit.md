# Sprint 81：i18n 翻譯完整性 audit

**性質**：純診斷
**日期**：2026-05-16

## 0. 一句話

`i18n/dobtor_doc_editor.pot` 有 27 個 msgid、`zh_TW.po` 有 20 個 msgstr — **缺 7 個翻譯**。Sprint 50-72 期間加的新 user-facing strings（如 Sprint 70 PDF error / Sprint 64b font_serve note）可能沒進 .pot。

## 1. Method

```bash
$ grep -c "msgid " i18n/dobtor_doc_editor.pot  # 27
$ grep -c "msgstr " i18n/zh_TW.po               # 20
$ grep -rE "_\(['\"]" controllers/*.py models/*.py wizards/*.py | wc -l  # 9
```

## 2. Findings

- .pot 比 zh_TW.po 多 7 個 msgid → 翻譯不完整
- code 內 `_()` 呼叫 9 處、但 .pot 27 個 msgid → 其他 18 個來自 XML / views
- Sprint 50-80 期間 audit doc 7 個（Sprint 70/79 等加了 user-facing error strings）但 .pot 未 regenerate

## 3. 修法評估

需要 Odoo 跑 `make i18n-extract`：

```bash
docker exec odoo18 odoo -d odoo18_dev --i18n-export=zh_TW \
    --modules=dobtor_doc_editor --i18n-overwrite \
    > /tmp/dobtor_zh_TW.po
```

這個 sprint **不直接 regenerate**（需手動翻譯 7 個新 msgid、scope 跨 user 確認用詞）。標為 Sprint 82+ 候選（半 user-decision、半 autonomous）。

## 4. 三層 SOP

| 層 | 結果 |
|---|---|
| L1-4 | 不適用（純 audit）|
| .pot vs .po diff | 7 missing |

## 5. 結論

i18n 完整性 gap = 7 個 missing translations。修法需 regenerate .pot + 翻譯，後者需要 user 確認用詞、屬半 autonomous sprint。
