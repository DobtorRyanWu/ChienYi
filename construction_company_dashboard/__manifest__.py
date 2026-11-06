{
    "name": "工程監造系統 - 公司儀表板",
    "version": "18.0.1.2.0",
    "category": "Construction/Supervision",
    "summary": "公司儀表板：營造廠主管（唯讀）／監造主管／千溢內部各看各的；營造廠歸屬、工作天、指標",
    "description": """
公司儀表板
==========

規格以 odoo18-docker/docs/architecture/dashboard/實作合約_v2.md 為準。

* 營造廠主管唯讀群組與範圍規則（§2、§3）
* 子資料營造廠歸屬（§3.5）
* 工作天與政府辦公日曆（§4）
* 指標（§5）、後台看板（§6）、前台頁（§7）
    """,
    "author": "Engineering Supervision System",
    "license": "LGPL-3",
    # 依賴：general→quality／photo／payment，payment→daily_log／progress；test、portal 另列（合約 §0a-c）
    "depends": [
        "construction_general",
        "construction_test",
        "construction_portal",
        "construction_progress",
        "auth_totp",
        # 「儀表板」App 的選單入口與試算表儀表板（11-06）
        "spreadsheet_dashboard",
    ],
    # 資料檔由主迴圈依各工作線回報加入（合約 §10）
    "data": [
        # 線 A1：群組要排在 ACL 之前
        "security/groups.xml",
        "security/ir.model.access.csv",
        # 線 A3：選裝模組模型的營造廠主管讀取 ACL（要在群組之後；合約 §0b-10）
        "security/optional_access.xml",
        # 線 A1'：帳號設定
        "views/res_users_views.xml",
        # 主迴圈 11-06：新建公司必選公司類型（合約 §0b-30）
        "views/res_company_views.xml",
        "data/server_actions.xml",
        # 線 I：受限帳號移出公開頻道（每次升級重跑；合約 §0b-25）
        "data/restricted_channels.xml",
        # 線 B：政府辦公日曆（tools/dashboard/convert_dgpa_calendar.py 產生；年度表在前，例外日依年度一檔）
        "data/construction.official.calendar.year.csv",
        "data/construction.official.calendar-2017.csv",
        "data/construction.official.calendar-2018.csv",
        "data/construction.official.calendar-2019.csv",
        "data/construction.official.calendar-2020.csv",
        "data/construction.official.calendar-2021.csv",
        "data/construction.official.calendar-2022.csv",
        "data/construction.official.calendar-2023.csv",
        "data/construction.official.calendar-2024.csv",
        "data/construction.official.calendar-2025.csv",
        "data/construction.official.calendar-2026.csv",
        "data/construction.official.calendar-2027.csv",
        # 線 C：後台畫面
        "views/dashboard_kanban.xml",
        "views/menu.xml",
        # 「儀表板」App 的試算表儀表板（11-06；群組要在 security 之後、JSON 由 tools/dashboard 產生）
        "data/spreadsheet_dashboard.xml",
        "views/project_form_rest_days.xml",
        # 線 D：前台公司儀表板頁與抽屜入口
        "views/portal_dashboard_templates.xml",
    ],
    "assets": {
        # 線 D：前台儀表板樣式（只用 --wb-*）
        "web.assets_frontend": [
            "construction_company_dashboard/static/src/portal/dashboard.css",
        ],
        "web.assets_backend": [
            "construction_company_dashboard/static/src/backend/company_service_patch.js",
            # 線 C
            "construction_company_dashboard/static/src/backend/company_dashboard_kanban.js",
            "construction_company_dashboard/static/src/backend/company_dashboard_kanban.xml",
            "construction_company_dashboard/static/src/backend/company_dashboard.scss",
            "construction_company_dashboard/static/src/progress_dashboard_ext/progress_dashboard_patch.js",
            "construction_company_dashboard/static/src/progress_dashboard_ext/progress_dashboard_patch.xml",
        ],
    },
    # 線 A1：營造廠歸屬回填＋驗算（合約 §3.5）
    "post_init_hook": "post_init_hook",
    "installable": True,
    "application": False,
}
