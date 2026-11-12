# -*- coding: utf-8 -*-
{
    'name': '工程監造系統 - 行政（公文、行事曆）',
    'version': '18.0.1.2.0',  # 1.2.0（2026-11-12，淞源 C5／C7）：行事曆的「時間說法」與「幾天內」條件搬到模型（_office_local_when、_office_upcoming_domain、_office_upcoming），手機行事曆頁與公司儀表板的行事曆區塊共用；畫面與資料不變。 1.1.0（2026-11-12，淞源 1110 會議 C7）：主管行事曆——事項、類型、起訖時間、權責人、地點、所屬工程；後台月曆（可拖曳改時間）；手機行事曆（新增與改時間限老闆／主管）；公文可按「建立行事曆事項」。不用 Odoo 原生 calendar.event（不寄邀請信）。 1.0.0（2026-11-12，淞源 1110 會議 C10）：公文登錄與搜尋——後台總表（依工程分組、可搜主旨／文號／機關、依公文日期篩期間）、手機列表＋搜尋＋詳情＋附件下載＋新增。公文屬於「所屬公司」，同一工程上的另一方看不到。
    'category': 'Construction',
    'summary': '公文登錄與搜尋：依工程分開＋總表；日期、機關、文號、主旨關鍵字；手機可查',
    'description': """
行政：公文
==========

淞源 2026-11-10 會議的需求（記錄 C10）：能用時間或關鍵字找到公文，在外面用手機也找得到。

* 登錄收文／發文：公文日期、機關、文號、主旨、說明、附件，可掛工程。
* 後台「檔案管理 > 公文」：總表預設依工程分組；搜尋列一次比對主旨、文號、機關，可依公文日期篩期間。
* 手機：工程底下的「公文」與跨工程的「公文總表」，可搜尋、看詳情、下載附件、新增。
* 選填辦理期限與狀態（待辦／已辦／存查），給期限提醒用。

不做：簽辦流程、電子公文交換、電子簽章（會議決定暫緩或不做）。

誰看得到：公文屬於「所屬公司」。同一個工程上的監造與營造廠彼此看不到對方的公文；
前台成員只看自己參與工程的；沒掛工程的只有老闆與後台人員看得到。
受限帳號（營造方、後台角色帳號）的範圍由 construction_company_dashboard 的 rule_scope 決定。
    """,
    'author': 'ChienYi',
    'license': 'LGPL-3',
    'depends': [
        'construction_supervision_base',
        'construction_portal',
        'mail',
    ],
    'data': [
        'security/ir.model.access.csv',
        'security/office_rules.xml',
        'views/official_doc_views.xml',
        'views/menu.xml',
        'views/portal_official_doc_templates.xml',
        'views/calendar_event_views.xml',
        'views/portal_calendar_templates.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
