{
    'name': 'Dobtor Spreadsheet Editor',
    'version': '18.0.1.0.0',
    'summary': 'Google Sheets / Excel 等級的 xlsx 高保真匯入編輯器',
    'description': """
Dobtor Spreadsheet Editor v1.0（Sprint 0）
==========================================
繼承 OCA spreadsheet_oca + Odoo 原生 o-spreadsheet，對標 Google Sheets / Excel 級 xlsx 高保真匯入：
- OOXML SpreadsheetML 完整 Parser（Phase 1）
- StyleResolver / NumberFormatCompiler（含台灣 locale）（Phase 2）
- FormulaCompiler（R1C1 / structured ref / Excel 函數 shim）（Phase 3）
- Conditional Formatting + Data Validation（Phase 4）
- Pivot / Chart / Drawing 完整解析（Phase 5）
- 雙向 xlsx round-trip（openpyxl 寫入）（Phase 6）
- 與 ChienYi 業務模組整合（估驗計價、契約變更、月報）

開發規劃詳見 dobtor_spreadsheet_editor_高保真匯入開發規劃.md
平行模組：dobtor_doc_editor（docx 高保真匯入）
    """,
    'category': 'Productivity',
    'author': 'Dobtor / ChienYi',
    'license': 'LGPL-3',
    'depends': [
        'base',
        'web',
        'bus',
        'portal',
        'spreadsheet_oca',
    ],
    'data': [
        # Phase 4.5 啟用後加入：
        # 'security/ir.model.access.csv',
        # 'security/spreadsheet_security.xml',
        # 'views/spreadsheet_editor_views.xml',
        # 'data/ir_cron_data.xml',
    ],
    'assets': {
        'web.assets_backend': [
            # Phase 4.5 啟用後加入 CSS / OWL Components
            # 'dobtor_spreadsheet_editor/static/src/css/xlsx_editor.css',
            # 'dobtor_spreadsheet_editor/static/src/components/XlsxImportButton.js',
        ],
        # OCA spreadsheet_oca 已掛 spreadsheet.o_spreadsheet bundle；
        # 本模組的 xlsx parser bundle 在 Phase 4.5 整合時加入
    },
    'external_dependencies': {
        'python': [
            # Phase 4.5 確認後加入：
            # 'openpyxl',          # Phase 6 xlsx 寫入（container 已裝）
            # 'python_calamine',   # 損壞 xlsx fallback reader（container 已裝）
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
}
