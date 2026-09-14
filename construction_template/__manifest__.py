# -*- coding: utf-8 -*-
{
    'name': '工程監造系統 - 樣板設定',
    # 2.4.0: 計畫書/分項計畫/施工圖三張管制表共用一份樣板
    # 2.5.0: 檢試驗管制表換成工程會新版格式（含預定/實際進場日期），
    #        並修正項次、規定抽樣頻率、會同人員三處欄位對應
    # 2.6.0: 檢試驗管制表項次改階層編號、規定抽樣頻率同項目跨列合併（POSTPROCESS
    #        hook）、切頁改依內容高度估算；用編輯器開啟 .docx 時帶入紙張格式與方向
    # 2.7.0: 所有管制表的「施工廠商／承攬廠商」統一改由 formatters.contractor_name()
    #        取值：先 project.contractor_company_name（純文字），沒填才退回承包廠商
    #        公司的聯絡人。一庫一公司下 contractor_company_ids 多半沒設，原本 7 支
    #        對照表只讀 contractor_partner_ids → 廠商欄整格空白（自主檢查總表實測）。
    #        受影響：self_inspection / daily_log_c1(+c2,progress_report) /
    #        defect_control / defect_improvement / estimate_report / review_control /
    #        test_control；plan_control 原本就對，一併收斂到同一支函式
    # 2.8.0: 施工日誌第一聯（營造版）的 ${table:specificConstructionItems.*}
    #        接上新的「營造業特定項目」頁籤（daily.log.specific.item）；
    #        原本硬寫 [] 導致該區永遠只印一列空白
    'version': '18.0.3.5.0',  # 3.5.0: 🔴 照片印出來的順序是**反的** —— supervision.photo 的 _order 是 'shot_at desc, id desc'（照片管理的清單要最新在前，那是對的），但列印到檢查表上時第 1 張應該是現場先拍的那張。三張照片實際印成 3→2→1（2026-09-14 使用者照手冊逐格驗證時發現）。⚠️ 我的自動測試只數了「有幾張圖」、沒有檢查順序，所以完全沒抓到。_images() 改為依 shot_date → shot_at → id 遞增排序（拍攝日期常常沒填，id 遞增＝建立順序＝先拍先傳）。 3.4.0: 🔴 反推的「請先清空」對量測區塊是**死結** —— 區塊一旦被檢查紀錄的量測列用過就刪不掉（ondelete='restrict'），要求先清空等於要求使用者先去刪歷史量測資料（使用者實測撞上：「此量測區塊已被 3 筆『一般式自主檢查量測列』使用」，當下以為整個檢查類型廢了）。改為：只擋「預設檢查項目」，量測區塊**同名沿用、一個欄位都不動**——句型尤其不能覆蓋，反推只給得出佔位句型，而既有區塊的句型往往已經被使用者填成正確的了。 3.3.0: 使用者拿 10 份測試樣板去按「從樣板匯入設定」（那批其實是設計來測「匯出」的守門），打出反推路徑的三個問題：(a) 🔴「已有資料」只檢查 default_item_ids、**漏了 measure_ids** —— 反推一次建了量測區塊、照訊息清掉預設檢查項目後再反推，這一關放行卻撞 UNIQUE，使用者看到的是「同一檢查類型內的量測區塊標題不可重複！」這種不知道要幹嘛的訊息；現在會列出「已經有：量測區塊 N 個」並說兩個分頁都要清。(b) 沒有佔位符的空白紙本被說成「這份樣板是動態表格格式」—— 兩種情況原因完全不同，訊息已分流。(c) 反推路徑沒檢查副檔名，上傳 .xlsx 會直接噴 zip 的英文錯誤。 3.2.0: 為了回答「79 份以外的新樣板有什麼限制」而逐條造正反例實測，又打出兩個缺陷：(a) 量測區塊的延續列，那 79 份用 vMerge、使用者自己做的樣板則常把標題格**留白**——兩者在紙上一模一樣，但原本只認 vMerge，留白會讓一個 8 列的區塊裂成 1+7 兩個，套印時後半段還會把前半段填好的量測資料整個蓋成空白（完全吻合的樣板反而被擋下，說「只有 7 項」）；(b) 樣板裡沒有量測段落時，已填的量測記錄**靜靜消失且不報錯**——新增 Probe.has_measure_slot()（硬編看單欄位連續列、動態看 inspection.measures 迴圈），有量測列但樣板印不出來就擋下並說明兩種處理方式。 3.1.0: 新增「樣板欄位名稱守門」(utils/template_tokens.py) —— 使用者問「79 份以外的新樣板能不能用」，實測造了 5 份新樣板才發現兩個靜默失敗：(a) 把空白紙本當樣板上傳(完全沒有佔位符) (b) 欄位名稱拼錯或自己發明(projectTitle / item.detail)。兩者 docxtpl 都不報錯 —— Jinja2 的 Undefined 直接印成空字串，產出一份「每一格都空白但看起來很正常」的檔案，使用者只會以為是自己沒填資料。現在套印前會先驗欄位名稱：認得 {{ }}/{%% for %%}/+++INS+++/+++FOR+++/+++IMAGE+++ 五種寫法，會追蹤迴圈變數的綁定(item.standard → inspection.stages[].items[].standard)，對照 mappings 的 TOKEN_SCHEMA。實測 79 份既有樣板＋系統預設樣板誤報 0，兩份刻意寫錯的都被精確指出是哪幾個欄位。 3.0.1: 使用者用真實鋼筋樣板實測打出四個缺陷 —— (a) 反推後要按 F5 才看得到新項目（action 補 next: reload）；(b) 反推的 sequence 每段各自從 10 起算，而「預設檢查項目」清單有 handle widget、前端只依 sequence 排序不看 stage_sequence → 畫面上段落整個交錯（改全域遞增，與既有匯入資料的慣例一致）；(c) 測試樣板每格都填「測試」兩個字，錯位完全看不出來 → 標準欄改填項目名稱、情形欄改填段-項編號；(d) 🔴 照片完全沒進去 —— IMAGE_RE 只認數字索引 images[0]，但 79 份自主檢查樣板全部用 images[$evenIndex] 與 [$evenIndex + 1]；連 IF_RE 也因為條件式含 '+' 而匹配不到。兩個 regex 都改成非貪婪；另外奇數張照片時最後一格會越界拋 UndefinedError（EAGLE 原靠 +++IF+++ 擋，而我們會移除它），改為補一格空白照片。同時：硬編樣板的量測列不足時**補空白**補到樣板列數（紙本預印 8 列實填 2 列是常態，原本會被守門誤判成「資料比樣板少」）。 3.0.0: 新增「自主檢查表（單張）」套印 —— 一張檢查紀錄一份 Word 檔。 樣板兩層來源：檢查類型上傳的 template_file 優先，沒上傳才用 document.template 的 self_inspection_form（上傳的樣板不放 document.template，因為它有 UNIQUE(template_type, project_id)，幾十種檢查表塞不進去）。 新增 mappings/self_inspection_form.py（context 必須用 SimpleNamespace——Jinja2 的 . 存取先找 attribute，dict 的 items 會蓋掉同名資料鍵）、utils/template_probe.py（偵測硬編/動態樣板＋逐列比對名稱的守門＋反推）、檢查類型的「測試樣板」與「從樣板匯入設定」按鈕。docx_render._swap_images 同步支援 SimpleNamespace，否則巢狀在 namespace 裡的照片標記換不到 InlineImage、照片會靜靜不見。 2.9.0: 預約式回報單樣板——彙總列不印單價數量，預估金額改「手填優先、沒填才用明細預估合計」。
    'category': 'Construction/Supervision',
    'summary': '文件樣板管理與設定',
    'description': """
工程監造系統 - 樣板設定模組
============================

此模組提供文件樣板管理功能：

主要功能
--------
* 文件樣板管理 (document.template)
* 支援多種樣板類型：施工日誌、自主檢查、缺失改善、進度表、估驗計價表等
* 系統預設樣板與專案自訂樣板
* 樣板上傳、下載、測試功能
* 欄位對照表設定 (JSON 格式)

技術特點
--------
* 多層級樣板優先順序：專案專屬 > 公司預設 > 系統預設
* 支援 Excel/Word 樣板格式
* 完整的權限控制
* 上傳樣板時檢查檔案格式與樣板類型是否相符（docx 類型不能傳 xlsx）
* 專案層級彙總表可由呼叫端用 context 指定日期區間；日期空白的記錄一律列入
  並回報，不會被靜默排除
    """,
    'author': 'Engineering Supervision System',
    'website': '',
    'license': 'LGPL-3',
    'depends': [
        'construction_supervision_base',
        # 樣板套印需要在施工日誌表單加匯出按鈕。
        # 反向不成立（daily_log 不依賴 template），無循環依賴。
        'construction_daily_log',
        'construction_notification_slip',
        'construction_payment',
        'construction_acceptance',
        'construction_test',
        # 自主檢查表（單張）的套印：兩式檢查紀錄加匯出按鈕、檢查類型加測試/反推按鈕。
        # 反向不成立（construction_quality 不依賴 template），無循環依賴。
        'construction_quality',
        # docx 樣板的 +++INS+++ → docxtpl Jinja2 轉換器在這個模組裡。
        # dobtor_doc_editor 只依賴 base/web/mail/html_editor/bus/portal，不會循環。
        'dobtor_doc_editor',
    ],
    'data': [
        # Security
        'security/security.xml',
        'security/ir.model.access.csv',
        # Views
        'views/document_template_views.xml',
        'views/daily_log_export_views.xml',
        'views/project_export_views.xml',
        'views/notification_slip_export_views.xml',
        'views/payment_estimate_export_views.xml',
        'views/acceptance_test_export_views.xml',
        'views/self_inspection_export_views.xml',
        'views/menu.xml',
    ],
    'demo': [],
    # 安裝時把 data/templates_blank/ 的 13 個空白範本灌成系統預設樣板
    'post_init_hook': 'post_init_hook',
    'installable': True,
    'application': False,
    'auto_install': False,
    'sequence': 50,
}
