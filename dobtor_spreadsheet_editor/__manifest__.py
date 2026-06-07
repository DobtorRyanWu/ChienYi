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
        'views/menu.xml',
    ],
    'assets': {
        'web.assets_backend': [
            # parser UMD bundle（暴露 window.DobtorSpreadsheetEditor）— 須先於 OWL component 載入
            'dobtor_spreadsheet_editor/static/src/lib/dobtor_spreadsheet_editor.umd.js',
            # Phase 4.5 Xlsx 匯入預覽 client action
            'dobtor_spreadsheet_editor/static/src/components/xlsx_import/xlsx_import.js',
            'dobtor_spreadsheet_editor/static/src/components/xlsx_import/xlsx_import.xml',
        ],
        # OCA spreadsheet_oca 已掛 spreadsheet.o_spreadsheet bundle；
        # 本模組 xlsx parser → o-spreadsheet model commands 對接於後續 sprint
    },
    'external_dependencies': {
        'python': [
            # Phase 4.5 確認後加入：
            # 'openpyxl',          # Phase 6 xlsx 寫入（container 已裝）
            # 'python_calamine',   # 損壞 xlsx fallback reader（container 已裝）
        ],
    },
    'installable': True,
    # 不另立 top-level App：繼承 OCA spreadsheet_oca、選單掛其底下（見 views/menu.xml）
    'application': False,
    'auto_install': False,
}
