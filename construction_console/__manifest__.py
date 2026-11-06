{
    "name": "工程監造系統 - 控台（工程總覽快照）",
    "version": "18.0.1.0.0",
    "category": "Construction/Supervision",
    "summary": "千溢控台：各監造公司庫的工程總覽快照（只裝在控台庫）",
    "description": """
控台（工程總覽快照）
====================

規格：odoo18-docker/docs/architecture/dashboard/實作合約_v2.md §8.3；命名沿用
docs/architecture/console/控台設計_多租戶集中管理.md 第四節。

* console.tenant：租戶（庫名、網址、資料時間、上次成功、上次失敗與原因）
* console.tenant.project：各租戶 dash_console_overview()（§8.1）的工程總覽列，唯讀
* replace_snapshot()：拉資料程式（tools/console_agent/pull_overview.py）在一個交易裡整批替換；
  伺服器端再檢查一次筆數（≠ project_count、或從大於 0 變成 0 → 拒寫、記失敗、舊快照保留）

console.server、console.job、主機代理白名單留給控台專案本身（不在本模組）。
**只裝在控台庫**，不要裝進任何租戶庫。
    """,
    "author": "Engineering Supervision System",
    "license": "LGPL-3",
    "depends": ["base", "web"],
    "data": [
        "security/groups.xml",
        "security/ir.model.access.csv",
        "views/console_views.xml",
    ],
    "installable": True,
    "application": True,
}
