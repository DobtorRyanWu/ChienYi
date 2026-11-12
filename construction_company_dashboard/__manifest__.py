{
    "name": "工程監造系統 - 公司儀表板",
    # 2.1.0（2026-11-10，S1）：後台角色帳號（營造老闆／營造主管／監造老闆／監造主管，後台唯讀）——群組三個＋營造廠主管改名「營造方（後台唯讀）」、
    #        讀取 ACL、rule_scope 的角色帳號範圍（kind 只看群組、絕不為 None）、選單白名單、即時損益放行讀取方法；
    #        內部備註不再通知受限帳號、受限內部帳號不可改 email 通知（營造廠主管一起修）。沒有新的 stored 欄位，不需 migration。
    #        fix1（同日，審查修正）：受限內部帳號不能在業務紀錄上留言／傳附件／通知（對話照常）、內部備註的附件讀不到、
    #        主管排除未開始／終止工程套到所有子資料、「受限帳號」判斷只留 base 一份、閘門與 TOTP 提示文字。
    #        fix2（同日）：受限內部帳號的訊息不寄 email／簡訊、不通知也不加入對話成員以外的人；不能改、刪業務紀錄上的訊息與加表情回應；
    #        內部備註不通知改用 NOT_INTERNAL_NOTE（含 is_internal）；營造方角色帳號的自主檢查樣板也套工程條件；拿掉多餘的通知建立守衛。
    #        fix2-X（同日）：方法閘門加 ROLE_ONLY_METHODS——後台角色帳號可以按估驗表單的四顆匯出按鈕（守衛在 construction_template）。
    #        2.2.0（2026-11-11，S2）：角色帳號手機能力接回（能力判斷在 construction_supervision_base res.users._portal_*）、
    #        前台老闆／主管 ↔ 角色帳號的轉換與改回（伺服器動作，同一個 user id）、沒開 TOTP 的手機提示與 OdooBot 初始化、
    #        登入先到手機、手機「電腦版後台」與後台「手機版」入口、手機動作的通知照核心收件人（restricted_mail 檔頭七）、
    #        範圍不合格的受限內部帳號讀不到也收不到業務訊息、監造方角色帳號看得到範圍內工程的水位（唯讀）。
    #        新欄位 res.users.dash_role_origin（Json，可空）由 -u 建立，不需 migration。
    #        S2 fix1（同日，未換版號）：轉換記下群組、兩個組織旗標、範圍公司、主要／允許公司，改回逐欄寫回（只記了公司的舊紀錄照層級／方別推）；
    #        _dash_sender_is_restricted 改名 _dash_narrow_recipients（restricted_mail 檔頭三補「例外見七」）。
    #        S2 fix2（同日，未換版號；使用者 11-11 追加）：U 唯讀帳號在私訊／群組對話 @ 讀得到的內部同事（站內通知、不寄信；暫定）；
    #        W 意見回饋開給範圍合格的監造方角色帳號（data/feedback_acl.xml 讀取權）；Z 先不強制兩步驟驗證
    #        （res_users_guard.DASH_REQUIRE_TOTP＝False，使用者 11-11 暫定；改回 True 即恢復）。
    #        2.3.0（2026-11-11，S3）：受限帳號唯一清單 res.users.dash_restricted_account_logins()（多訊號聯集，系統管理者限定；
    #        qd.py 與 runbook 共用）、uninstall_hook 有受限帳號（含前台營造帳號、已封存）就拒絕解除安裝、
    #        runbook README_ROLE_ACCOUNTS.md。A 的 18 條全域公司規則在各模型所屬模組（測試在本模組 tests/test_company_isolation.py）。
    #        2.3.1（2026-11-11，S3 fix1）：受限帳號清單簡化成只看 _dash_is_restricted()（拿掉群組 SQL 與 origin／scope 兩個訊號），
    #        5 個受限群組 xmlid 任一個找不到就 UserError（fail-closed）；hook 訊息與 runbook 更正（解除安裝失敗只失敗一次）；寫入面測試。
    #        2.3.2（2026-11-11，S2 fix3）：@ 對話外內部同事沒有 email 也收站內通知（同事那一列自己組）、可 @ 的同事只留
    #        _dash_colleagues 一份（前端只顯示後端回的）、編輯訊息也收窄 partner_ids、受限內部帳號（營造廠主管、後台角色帳號、
    #        控台讀取）的 XML-RPC／JSON-RPC 只收 API key（_rpc_api_keys_only；瀏覽器登入照常只要密碼）、改回前台帳號拿掉
    #        舊格式紀錄的相容路徑、意見回饋 ACL 模型名從 rule_scope 匯入、過時的 TOTP 註解。沒有新欄位。
    #        2.3.3（2026-11-12，S3 fix2）：寫入面測試補齊（寫後檢查的欄位表鎖在資料庫規則上、每個規則欄位一格行為測試、
    #        related 欄位不能直接寫）；runbook／hook 訊息更正（回滾範圍、qd.py 已改呼叫清單函式、營造廠主管的處置、
    #        XML-RPC／JSON-RPC 只收 API key 不等於密碼不能跑程式）。沒有新欄位。
    "version": "18.0.2.3.4",
    "category": "Construction/Supervision",
    "summary": "公司儀表板：營造廠主管（唯讀）／監造主管／千溢內部各看各的；營造廠歸屬、工作天、指標",
    "description": """
公司儀表板
==========

規格以 odoo18-docker/docs/architecture/dashboard/實作合約_v2.md 為準。

* 營造廠主管唯讀群組與範圍規則（§2、§3）
* 子資料營造廠歸屬（§3.5）
* 工作天與政府辦公日曆（§4）
* 指標（§5）、後台三頁：總覽／單一工程／標案地圖（§6、§0b-33）、前台頁（§7）
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
        # 標案地圖（合約 §0b-33）：OCA 的 Leaflet 函式庫（web.assets_backend 直接載入 window.L）
        "web_leaflet_lib",
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
        # S2 fix2-W：後台角色帳號讀意見回饋的讀取權（construction_helpdesk 有裝才建）
        "data/feedback_acl.xml",
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
        # 線 C：後台畫面（11-07 合約 §0b-33：看板換成雛型版三頁的 client action）
        "views/dashboard_page.xml",
        "views/menu.xml",
        # 「儀表板」App 的試算表儀表板（11-06；群組要在 security 之後、JSON 由 tools/dashboard 產生）
        "data/spreadsheet_dashboard.xml",
        "views/project_form_rest_days.xml",
        # 線 D：前台公司儀表板頁與抽屜入口
        "views/portal_dashboard_templates.xml",
        # S2：角色帳號在手機的兩步驟驗證提示、電腦版後台入口
        "views/portal_role_templates.xml",
    ],
    "assets": {
        # 線 D：前台儀表板樣式（只用 --wb-*）
        "web.assets_frontend": [
            "construction_company_dashboard/static/src/portal/dashboard.css",
        ],
        "web.assets_backend": [
            "construction_company_dashboard/static/src/backend/company_service_patch.js",
            # S2 fix2-U（使用者 11-11 暫定）：唯讀帳號在私訊／群組對話的 @ 建議名單另列讀得到的內部同事
            "construction_company_dashboard/static/src/backend/mention_colleagues_patch.js",
            # 線 C → 11-07 合約 §0b-33：雛型版三頁（總覽／單一工程／標案地圖）
            "construction_company_dashboard/static/src/dashboard_page/dashboard_page.scss",
            "construction_company_dashboard/static/src/dashboard_page/dash_common.js",
            "construction_company_dashboard/static/src/dashboard_page/overview.js",
            "construction_company_dashboard/static/src/dashboard_page/overview.xml",
            "construction_company_dashboard/static/src/dashboard_page/project.js",
            "construction_company_dashboard/static/src/dashboard_page/project.xml",
            "construction_company_dashboard/static/src/dashboard_page/map.js",
            "construction_company_dashboard/static/src/dashboard_page/map.xml",
            "construction_company_dashboard/static/src/progress_dashboard_ext/progress_dashboard_patch.js",
            "construction_company_dashboard/static/src/progress_dashboard_ext/progress_dashboard_patch.xml",
        ],
    },
    # 線 A1：營造廠歸屬回填＋驗算（合約 §3.5）
    "post_init_hook": "post_init_hook",
    # S3-B：有受限帳號就拒絕解除安裝（hooks.py 檔尾；runbook README_ROLE_ACCOUNTS.md）
    "uninstall_hook": "uninstall_hook",
    "installable": True,
    "application": False,
}
