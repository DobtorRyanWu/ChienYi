# -*- coding: utf-8 -*-
{
    'name': '工程監造系統 - 核心基礎模組',
    # 4.6.0: 修 total_approved_duration 重複計算展延 —— 基數改用 original_duration
    #        （開工時凍結）而非 contract_duration（會隨 contract_end_date 移動、
    #        本身已含展延）。P11001 實測 178 → 164
    # 4.7.0: 併入 GitHub 上游修正 8f0bf84 —— _resolve_uom_id 自動建 uom.category/uom.uom
    #        改用 sudo（uom 是全域參照資料；原本要求 Administration/Settings 群組，
    #        非管理員如代操帳號建含新單位工項／套用引進新單位的契約變更時 AccessError）
    # 4.8.0: 四件事——(a) 契約工項 actual_amount 改為與 planned_amount 同一套三分支
    #        並向上滾動（實際完成數量本身由 construction_daily_log 計算）；
    #        (b) ir.attachment 加 supervision_project_id / document_category_id 兩欄
    #        並新增 supervision.attachment.mixin，各業務單據的附件自動歸類，
    #        新增「檔案管理 > 文件管理 > 全部工程附件」清單；
    #        (c) 文件分類改以實際案件歸檔資料夾為準（11-工程資料、12-文書資料、
    #        14-變更設計～18-府查核；照片另有「照片管理」專責故不設分類），
    #        舊 24 筆系統分類停用不刪；
    #        (d) supervision.document / category 的 name_get 改 _compute_display_name
    #        （Odoo 17 起 name_get 已移除，原本那兩段從未被呼叫過）
    # 4.8.1: 舊 24 筆文件分類補 post-migration 才真的停用得了
    #        （當初以 noupdate="1" 建立，旗標存在 ir_model_data 上，改 XML 無效）
    # 4.8.2: 拿掉「13-照片」文件分類（含 4 子分類）—— 照片由「照片管理」專責，
    #        不再給它第二套分類體系；supervision.photo 也不掛附件歸類 mixin
    # 5.5.0: 文件分類樹 31→44（新增 15、改名 4、停用 2），category 加
    #        create_folder / extra_folder_names，_compute_display_name 改遞迴顯示完整路徑；
    #        pre-migrate 清掉 cat_* 的 noupdate 旗標，此後標準分類以 XML 為準
    # 5.6.0: 新增 supervision.folder（工程檔案資料夾，per-project 樹狀）
    #        + ir.attachment.folder_id + 上傳精靈；「全部工程附件」改名「工程檔案」
    #        並加上左側資料夾樹 searchpanel
    # 5.7.0: 工程案件加「建立標準資料夾」按鈕（依文件分類樹產生 44+2 個資料夾）
    #        與「資料夾」smart button；清單主欄改縮排名稱 tree_name、
    #        searchpanel 側欄改用 hierarchical_naming 只顯示短名
    # 5.8.0: supervision.attachment.mixin 加 _attachment_default_folder /
    #        _attachment_category_folder / _get_or_create_folder，各業務單據的附件
    #        自動歸位到資料夾樹；路徑由分類的祖先鏈推導（不寫死中文字串，
    #        分類改名會自動跟著改）
    # 5.9.0: 工程檔案批次下載 wizard（zip 內結構＝資料夾樹、500 MB 上限、排除照片）
    # 5.10.0: 修 supervision.document 走 create 上傳附件的 bug（res_id 卡 0）、
    #         計數欄改非儲存並移除 ir.attachment 的三個補算覆寫、post-migrate 修 20 筆孤兒附件
    # 5.11.0: 「工程文件」改名「應交文件管制表」並隱藏所有入口（模型與資料保留）
    # 6.2.5: 前台三個角色（老闆／主管／現場）的 ORM 寫入權收回（ir.model.access.csv 改 1,0,0,0）。前台頁面一律走 sudo＋controller 守衛寫入，不受影響；營造廠帳號不能再繞過前台直接打 RPC 改資料
    # 6.2.6: 前台成員讀取規則補到掛在工程底下的業務資料（老闆另加公司範圍）：原本前台讀得到、沒有任何前台規則，非成員經 RPC 讀得到別案：工程文件、資料夾（不屬任何工程的照常可讀；新檔 security/portal_rules.xml，要排在前台群組定義之後）
    # 6.3.0: 公司儀表板身分判定（合約 docs/architecture/dashboard/實作合約_v2.md §2）——res.users 加「範圍公司」dash_scope_company_id（只有系統管理者能寫、寫入清規則快取）、_dash_is_contractor_side／_dash_scope_ok／_is_supervision_side、範圍公司有值必須是營造廠（可空白＝預設拒絕，§0b-4）、主要公司是營造廠也算營造方（§0b-5）；res.company 改公司類型清規則快取；post-migrate 回填既有營造方帳號（主要公司是營造廠才填，其餘留空並列 log）
    # 6.4.0（2026-11-10，S1 後台角色帳號）：res.users 加角色帳號判定 _role_level_raw／_role_side／_is_role_account／
    #        _role_supervision_company_ids／_is_backend_staff／_construction_org_side；_is_supervision_side 改等於 _is_backend_staff；
    #        _dash_scope_ok 對角色帳號依方別判定（群組定義在 construction_company_dashboard，沒裝時一律為否）
    #        fix1（同日）：_dash_is_restricted 搬到這裡（全系統唯一一份），_is_backend_staff＝內部且不受限。
    #        fix2（同日）：_dash_is_restricted_internal（受限的內部帳號，全系統唯一一份）。
    'version': '18.0.6.14.0',  # 6.14.0（2026-11-22，使用者逐條決定，對照鈺鈞的意見表）：加回 SQL 約束 contract_dates_check（契約完工日不早於開工日，清單 PJ-12）；後台工程表單的工程編號開工後也能改（清單 PJ-16，舊系統隨時可改）。
    #        6.13.0（2026-11-20 回復原版 補 3，使用者決定，清單 PJ-10）：契約金額有工項之後、開工之後都可以手改（原本 inverse 擋「已匯入工項…無法手動修改」「只有未開始階段可以手動設定」，表單開工後唯讀）；新增 contract_amount_manual（契約金額手動輸入）——手改成和工項合計不一樣的數字就記下，compute 不再覆蓋，取消勾選改回工項合計；填的數字等於工項合計不算手動。 6.12.0（2026-11-20 回復原版 5/6）：契約完工日可以早於開工日（拿掉資料庫 CHECK）、契約數量與單價可以是負數。 6.11.0（2026-11-20 回復原版 3/6）：開工後工程名稱、年份、主辦機關、地點、監造單位、契約編號、實際日期、座標在表單上不再唯讀（工程類型、契約日期照舊）。 6.10.0（2026-11-20 回復原版，1118 會議）：開始施工不再要求契約開工日與六項初始化完成，「開始施工」按鈕不再因初始化未完成而隱藏。 6.9.0（2026-11-20；origin 上原編 6.8.0，與本機另一批異動的版號相撞，合併時重編）：開工後（而且進度表啟用過）契約開工日、預定契約完工日不能手動改（write 擋，後台表單、提出更正、前台都走這裡；進度表啟用寫回展延後完工日帶 context 放行；值沒變不擋）；新增 progress_ever_activated（第一次啟用進度表時記下）；開始施工要求至少一個契約工項；刪掉 res.users._portal_owns_or_may_edit／_portal_can_edit_record（前台「現場人員只能改自己建的」拿掉）；公司隔離寫後檢查表的預約式缺失、自主檢查改成只看 project_id。 6.8.0（2026-11-18，S5）：寫後檢查表（company_rule_write_guard.COMPANY_RULE_FIELDS）加 S5 的 20 個模型——自主檢查樣板與子表、缺失編號前綴、文件樣板、會議記錄、週施工排程、驗收與結案、機具、計畫書送審管制；指向它們的 many2one 跟著由 relational_input_guard 守。 6.7.6（2026-11-16）：取號可帶單據日期；新增 ir.sequence._backfill_slash_numbers（「/」舊單補號，給 migration 用）。 6.7.5（2026-11-16）：新增 ir.sequence._next_by_code_for_project，單號依工程所屬公司取號；文件單號改用它。 6.7.4（2026-11-16）：migration 把空的 project_task.item_no 依專案補成 1、2…，-u 才設得上 NOT NULL（jt 6 列 hr_timesheet 內部任務）。 6.7.3（2026-11-13）：連結線上文件欄位（linked_doc_id → doc.document）納入關聯 id 守衛、守衛說明更正；1b 的「單據」改成掛在工程底下的任何資料（表外直接指向工程的模型也算，從 registry 掃；空資料夾與成員名單照舊不算）。 6.7.2（2026-11-13）：1b 放寬——開案時系統自己產生的不算單據（空的資料夾、工程成員名單），只有這些的工程，有工程寫權的人可以改公司（company_rule_write_guard）。
    #        6.7.1（2026-11-13，S4 fix1）：relational_input_guard 的守衛欄位多一種——comodel 是公司隔離模型（寫後檢查表的鍵＋工程）的 many2one，讀不到的 id 填不進去（核心 many2one 的顯示名稱以 sudo 讀，S4 第一輪審查 red-team F1）。 6.7.0（2026-11-12，S4）：資料夾、工程成員、工程文件、工項（project.task，核心規則 85 保留）補全域公司規則（security/company_rules.xml，走工程的公司；資料夾、文件、工項工程空白放行）；本輪 29 個模型加進寫後檢查的欄位表（company_rule_write_guard.COMPANY_RULE_FIELDS）——1b 的「單據」跟著變大（照片、日誌、資料夾等都算）。 6.6.4（2026-11-12，1b 追加）：代操作員也能改有單據的工程的公司。 6.6.3（2026-11-12，S3 1b）：寫入面加第 4 點——已經有估驗等單據（寫後檢查表上的模型，含封存）的工程，非 sudo 改公司只有系統管理者（base.group_system）能改，其他人（含同屬兩家公司的工程後台使用者）UserError（S3 第三輪 red-team R1）。 6.6.2（2026-11-12，S3 fix2）：寫入面加第 3 點——規則用得到的 related 欄位（company_id＝工程的公司、非契約工項明細的 project_id）非 sudo 不能直接寫（UserError；同屬兩家公司的帳號也一樣，審查 skeptic F2）；欄位表加註「規則 domain 的第二份、由測試鎖住」。 6.6.1（2026-11-11，S3 fix1）：S3 全域公司規則的寫入面（models/company_rule_write_guard.py）——非 sudo 的 write 改到規則用得到的欄位（工程、父單、工項）後以寫入者身分再檢查一次（核心 write 只在寫前檢查），有工程的估驗／變更單（明細）不能改成工程空白；5 份 company_rules.xml 的說明收在本模組那一份。 6.6.0（2026-11-11，S3）：工項版本、工項分析（核心 SQL 檢視）補全域公司規則（security/company_rules.xml；工項版本原本沒有任何規則，工項分析的核心規則放行公司空白的列）。  # 6.5.0（2026-11-11，S2；fix1 同日未換版號：前台角色→群組只留 PORTAL_ROLE_GROUPS 一張表、層級值收成一組（閱覽者 'viewer'→'observer'）、新增 _portal_owns_or_may_edit）：手機（前台）能力的唯一來源 res.users._portal_*（層級、管理權、寫入、審核、解鎖、「其他」類頁、手機首頁），後台角色帳號照它的層級（範圍合格才有）；組織旗標只對前台帳號同步組織群組（F5）；_construction_org_side 接上缺失類型。 6.2.4: 系統帳號 OdooBot 改名「系統」（名字仍是 OdooBot 才改）；內建 Chart.js 外掛四支（static/lib/chartjs_plugins）；契約工項表單工程案件必填；專案契約工項清單拿掉拖了也不會改順序的把手。6.2.3: 代操作員再帶 product.group_product_manager（標單匯入建品項）。6.2.2: 代操作員加 project.group_project_user（標單匯入要建 project.task）；_resolve_uom_id 查詢改 sudo（前台角色讀不到 uom）。6.2.0: 權限群組調整——新增「工程管理者」(＝代操作員＋設定)，原下拉的「系統管理者」(group_supervisor_admin，xmlid 不變、190 處引用不動) 改名「工程後台使用者」並移出特殊權限分類；下拉變成「代操作員／工程管理者」。使用者表單加「降級為代操作員」按鈕（只改下拉會殘留設定與它帶入的 6 個群組）。migration 把「設定＋系統管理者、非代操作員」的帳號遷為工程管理者，首頁維持原狀。 6.1.3: 文件分類的 display_name 補宣告 recursive=True（依賴上層 display_name 的自我遞迴依賴；消除載入時的 UserWarning，並讓上層改名時失效一路傳到所有下層）。⚠️ display_name 是魔法欄位，覆寫時要完整寫出 compute/search，只寫 recursive=True 會把它變成沒有 compute 的 stored 欄位。 6.1.2: 覆蓋確認的提示文字精簡（拿掉「否則工項會整套重複，契約金額變成兩倍」）。 6.1.1: 覆蓋確認的勾選框補 <label>（原本是沒有文字的裸方框，使用者找不到）。 6.1.0: 標單匯入精靈四項修正——重複匯入防呆（偵測既有工項→檢查下游引用→勾「確認覆蓋」才刪舊重建）、itemKind="subtotal" 小計列自動勾「不計入契約金額」、依 <Remark> 公式回填「比例基數」、補寫 description。 6.0.0: 契約工項加「整包費用項」旗標（金額走 xml_amount，不被寫髒的 unit_price 影響）與「比例基數」多選（基數限同層前置工項，故不需循環偵測）；整包項的實際金額改跟基數完成比例走。 5.14.0: 契約工項加「不計入契約金額」（預備單價項目），工程加「契約金額調整」——契約金額＝頂層工項合計＋調整累計。 5.13.0: 檔案總覽/資料夾加單檔下載鈕、勾選後可打包 zip
    # 5.4.0: 營造廠商移到基本資訊區
    # 5.3.0: 契約工項選取對話框
    #        顯示欄位改為 項次/父工項/項目及說明/單位/契約數量/契約單價/備註——代操回報
    #        「各大項未區隔，項目會混淆」，選取對話框只列葉節點看不出屬於哪個大項。
    #        契約複價改預設隱藏、移除 sequence 拖曳把手（default_order 是 item_no_sort，
    #        拖曳本來就不會生效）。本 view 由 6 個「選擇施工項目」對話框共用，一起改。
    #        5.0.0: 代操作員(group_operator)登入落地頁設為「工程案件」——
    #        Odoo 只有 per-user 的 action_id(偏好設定>首頁動作)、沒有 per-group 設定，
    #        故在 create/群組異動時代設，只填空的不覆蓋使用者自訂；post-migrate 回填既有帳號。
    #        4.5.0: 工程案件新增經緯度範圍 constrains（原本完全沒有，實際存過非法緯度 121.51；且告示牌照片會繼承這組座標，錯值會擴散）；4.4.0: 新增 res.users.portal_role 自訂欄位管理前台角色(取代原生下拉,對Portal使用者可見可改;設定角色自動轉乾淨Portal,admin除外);角色群組移除 category_id；4.3.0: 前台四角色往下合併（boss/manager/field/observer 併入 subscriber/leader/user/viewer 並改名為 老闆/主管/現場人員/定期閱覽者、刪除新群組、到期邏輯解耦）post-migrate；4.1.1: 業主欄位 authority_id→authority_name 純文字化資料回填 post-migrate；4.1.0: project_task 必填欄位 NULL 回填 pre-migrate
    'category': 'Construction/Supervision',
    'summary': '工程監造與施工協作管理系統核心模組',
    'description': """
工程監造系統 - 核心基礎模組
============================

此模組提供工程監造系統的核心功能：

主要功能
--------
* 工程案件主檔管理 (supervision.project)
* 契約工項管理 (project.task 擴展)
* 工程文件管理與審核流程
* 多公司架構支援 (設計監造/施工廠商)
* 資料隔離與權限控制

技術特點
--------
* 繼承 Odoo 18 project 模組
* 支援一般式與預約式工程類型
* 完整的狀態機與工作流程
* 多層級權限控制
    """,
    'author': 'Engineering Supervision System',
    'website': '',
    'license': 'LGPL-3',
    'depends': [
        'base',
        'project',
        'hr_timesheet',
        'contacts',
        'mail',
        'resource',
        'uom',
        'product',
    ],
    'data': [
        # Security
        # 注意：必須先建立群組，才能載入 ir.model.access.csv
        'security/security.xml',
        'security/portal_groups.xml',  # 包含 group_operator 定義
        'security/new_portal_groups.xml',  # 前台四角色（老闆/主管/現場人員/定期閱覽者）+ 2 個組織類型
        'security/portal_rules.xml',  # 前台成員讀取規則（引用上面的群組）
        'security/ir.model.access.csv',
        'security/company_rules.xml',  # 全域公司隔離（S3）
        # Data
        'data/ir_sequence_data.xml',
        'data/document_category_data.xml',
        'data/ir_cron_data.xml',
        'data/portal_account_cron.xml',  # 臨時帳號到期自動停用
        'data/system_partner_data.xml',  # 訊息記錄作者 OdooBot 改名「系統」
        # Wizard
        'wizard/tender_import_wizard_views.xml',
        'wizard/document_replace_attachment_wizard_views.xml',
        'wizard/supervision_folder_upload_wizard_views.xml',  # 需在 folder views 之前（form 引用其 action）
        'wizard/supervision_attachment_download_wizard_views.xml',  # 同上
        # Views
        'views/res_company_views.xml',
        'views/res_users_views.xml',  # 新架構：組織身分欄位
        'views/supervision_project_views.xml',
        'views/project_task_views.xml',
        'views/supervision_document_views.xml',
        'views/product_views.xml',
        'views/menu.xml',
        'views/supervision_document_category_views.xml',
        'views/supervision_folder_views.xml',  # 需 menu.xml 的 menu_document_management
        'views/supervision_attachment_views.xml',  # 需 menu.xml 的 menu_document_management
        'views/hide_official_menus.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'construction_supervision_base/static/src/css/backend.css',
        ],
    },
    'demo': [],
    'installable': True,
    'application': True,
    'auto_install': False,
    'sequence': 1,
    'post_migrate': 'construction_supervision_base.hooks.post_migrate',
}
