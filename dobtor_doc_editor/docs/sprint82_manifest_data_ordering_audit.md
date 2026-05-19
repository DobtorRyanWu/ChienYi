# Sprint 82：`__manifest__.py` data file ordering audit

**性質**：純診斷
**日期**：2026-05-16

## 0. 一句話

Odoo data file 載入順序影響 record refs 是否找得到。Sprint 82 audit dobtor_doc_editor manifest 順序。

## 1. Audit

```python
'data': [
    'security/doc_groups.xml',           # 1. groups 先
    'security/ir.model.access.csv',      # 2. ACL ref groups
    'security/doc_security.xml',         # 3. ir.rule ref groups + models
    'wizards/doc_field_picker_views.xml',
    'wizards/doc_bulk_import_wizard_views.xml',
    'views/doc_document_views.xml',
    'views/doc_template_views.xml',
    'views/portal_templates.xml',
    'views/doc_telemetry_views.xml',
    'views/menu.xml',                    # menu 在 views 後（ref views）✓
    'views/test_layout.xml',
    'data/doc_template_data.xml',
    'data/ir_cron_data.xml',
],
```

## 2. Findings

✓ Security 三檔順序正確（groups → ACL → rule）
✓ menu.xml 在 views 後（菜單 ref views action）
✓ data 最後（template_data / cron 不被 view 依賴）

**無問題**。設計乾淨。

## 3. 結論

純診斷 audit clean、無 dead code / 順序問題。
