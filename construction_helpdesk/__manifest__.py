# -*- coding: utf-8 -*-
{
    'name': '工程監造系統 - 客服服務單與系統問題單',
    # 1.0.0: 第一階段 —— 客服群組（由「設定」自動包含）、服務單類別、功能模組、
    #        處理時限設定（P1～P4 固定四筆、全欄位留修改紀錄）與選單骨架
    # 1.1.0: 第二階段 —— 服務單（對話紀錄模式：送出後回報內容任何人不可改、
    #        只能留言／附檔；服務單上的留言任何人不可改、不可刪）、record rules
    #        （系統管理者只看自己建的、只能改「新建」的；客服全部）、客服專屬欄位層級限制
    # 1.1.1: 服務單單號改 no_gap（standard 用 PG sequence，rollback 不退號，測試會讓正式單號跳號）
    # 1.2.0: 第三、四階段 —— 系統問題單（S／U／P 分級、特例最多升一級、資安直接 P1、
    #        降級理由、分級後鎖定只能經「變更等級」改判）、日期制時限（起算日／計算基準日／
    #        預期工作天數／非工作日天數／預定修復日／總處理天數／逾時）、轉問題單與變更等級
    #        兩個對話框、看板、統計選單；結案時若需修正既有資料但未完成則擋下
    # 1.2.1: 逾時補 depends（同一交易內改日期會重算）；統計子選單逐一加客服群組限制
    # 1.3.0: 前台「意見回饋」—— 客戶在前台填客服單（類型必選、含附件），看自己送過的單並在單上
    #        與客服對話（沿用送出後不可改、留言不可改刪）；抽屜佔位改成真入口（inherit，
    #        construction_portal 不需知道本模組）；前台只看得到自己送的；客戶不自動追蹤（不寄 Email）。
    #        「功能模組」改名「發生功能」並加「前台顯示」、類別加「詢問發生功能」；回報管道加「前台」；
    #        後台服務單按「傳送訊息」跳確認（客戶會看到）
    # 1.4.0: B 段實測回饋 —— 客戶公司／回報窗口改為文字欄位（客戶公司、聯絡人；本系統沒有公司主檔）；
    #        發生功能加「前台顯示名稱」與後台專用功能（依後台實際選單）；後台服務單類別必填、
    #        發生功能只在「詢問發生功能」的類別出現（與前台一致）；處理時限設定的修復時限說明
    #        改依天數自動產生、清單改點選開表單（看得到修改紀錄）並調整欄寬
    # 1.5.0: C／D 段實測回饋 —— 修正問題單看板打不開（Selection 的 group_expand 寫錯）；
    #        服務單上的留言連「編輯／刪除」按鈕都不顯示（前後台）；送出後建單人不能改類別／發生功能；
    #        時間欄位不顯示秒；發生功能名稱改以後台名稱為主、前台叫法放「前台顯示名稱」
    # 1.6.0: E～I 段回饋 —— 分級頁與變更等級加「判定標準」參考表（S／U 條件、P 表、P1～P4 層級，
    #        修復期限即時讀處理時限設定）、S／U 選項附簡短條件；「降級理由」改「調整原因」；
    #        改判原因補欄位名稱；轉問題單列出候選問題單（標題／發生功能／等級／服務單數）、可看全部未結案、
    #        可更改關聯問題單；問題單顯示「單號 標題」；資料修正頁加判斷方法
    # 1.6.1: 判斷「是不是同一個問題」改以問題說明＋發生功能為主 —— 問題說明提到問題單第一個頁籤；
    #        轉問題單對照顯示本服務單說明，候選清單只列單號／標題／發生功能／問題說明摘要
    # 1.6.2: 問題單「問題說明」、服務單「詳細說明」頁籤內的欄位補上欄位名稱，提示文字縮短
    # 1.6.3: 轉問題單候選清單為空時顯示原因（同發生功能沒有未結案單 → 提示勾「列出所有」或新建）
    # 1.6.4: 時間欄位的選擇器不再出現「秒」——Odoo 18 的 show_seconds: False 會讓選擇器改成
    #        顯示秒（datetime_field.js：沒給 rounding 時把 rounding 設成 0），一律補 rounding: 1（精確到分）
    'version': '18.0.1.6.4',
    'category': 'Construction/Supervision',
    'summary': '客服服務單、系統問題單分級（S／U／P）與處理時限',
    'description': """
工程監造系統 - 客服服務單與系統問題單
======================================

* 服務單：客戶在前台「意見回饋」填寫（或電話、LINE 聯絡時由客服代為登記）
* 系統問題單：服務單判定為系統問題後轉出，依《系統問題分級與處理時限標準》分級與追蹤
* 客服群組 group_helpdesk_agent：由 base.group_system（設定）自動包含，
  日後要把客服交給非工程師，只要在該帳號加上這個群組

刻意只依賴 Odoo 原生模組（不用 OCA helpdesk_mgmt，也不用 resource 工作行事曆）。

日後分庫：已決定採「集中客服資料庫＋API 收單」，尚未實作。
見 docs/分庫架構_集中客服資料庫.md（程式中相關位置標有【分庫】註解）。
    """,
    'author': 'Engineering Supervision System',
    'website': '',
    'license': 'LGPL-3',
    'depends': [
        'base',
        'mail',
        # 只為了引用「系統管理者」群組
        'construction_supervision_base',
        # 前台「意見回饋」：inherit 抽屜、沿用前台版面與頁首
        'construction_portal',
    ],
    'data': [
        # Security
        'security/helpdesk_security.xml',
        'security/ir.model.access.csv',
        # Data
        'data/service_category_data.xml',
        'data/functional_module_data.xml',
        'data/problem_sla_data.xml',
        'data/ir_sequence_data.xml',
        # Views
        'views/problem_views.xml',
        'views/service_ticket_views.xml',
        'views/report_views.xml',
        'views/service_category_views.xml',
        'views/functional_module_views.xml',
        'views/problem_sla_views.xml',
        'views/menu.xml',
        'views/portal_feedback_templates.xml',
    ],
    'assets': {
        # ⚠️ 傳送訊息防呆只能放後台：前台 chatter 用同一個 Composer，放前台會讓客戶留言也跳提醒
        'web.assets_backend': [
            'construction_helpdesk/static/src/js/ticket_send_confirm.js',
            'construction_helpdesk/static/src/js/message_no_edit.js',
        ],
        # 前台 chatter 是獨立的 bundle，留言按鈕的隱藏要另外放一份
        'portal.assets_chatter': [
            'construction_helpdesk/static/src/js/message_no_edit.js',
        ],
        'web.assets_frontend': [
            'construction_helpdesk/static/src/js/portal_feedback.js',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
}
