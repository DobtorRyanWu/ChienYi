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
    'version': '18.0.3.12.1',  # 3.12.1（2026-11-07）: 新北附表12「□改善完成 □未完成改善」：缺失的成果確認存「已矯正」時勾改善完成（原本兩格都空白；上面「符合要求／逾時未矯正／未矯正／其他」四格照 EAGLE 仍不勾）。只改套印對照表，沒有資料或樣板變動。 3.12.0（2026-11-06）: 矯正與預防處理紀錄的「缺失改善成果確認」改成缺失上有存「成果確認」（construction_quality 6.7.0 outcome_result）就照它勾，沒填才照舊依狀態＋期限判斷；「其他」格（isOther）也會勾了；「已矯正」四格都不勾（照 EAGLE）。原因：回填的 EAGLE 缺失要印得和 EAGLE 一樣（例：EAGLE 存未矯正、期限已過，自動判斷會印逾時未矯正）。需 construction_quality 18.0.6.7.0。 3.11.0（2026-11-06）: (a) 矯正與預防處理紀錄：同一階段不只一張照片時，第 2 張起印在照片紀錄表的續頁（原本每階段只印一張，而且取的是最新那張；改依拍攝先後，與自主檢查表單張共用 ordered_photos）；表頭頁碼改 page.no／page.total；migration 換系統預設樣板（被人換過的不動），舊樣板（$record.images）照舊只印第一頁。(b) 套印出來的 xlsx 一律拿掉 calcChain（工程／公司層自己上傳的樣板若帶著殘留，Excel 正常模式打不開；3.9.0 只換了系統預設）。(c) 工程估驗計價單：本次與累計各列四捨五入後加總等於合計（尾差調整，最大餘數法；差額超過列數視為資料不一致不調）；四捨五入改 ROUND_HALF_UP（.0f 是銀行家捨入）。(d) 自主檢查表單張的檢查時機名稱比對加關鍵字：施工前／施工中／施工後、施工完成、完工後、查驗停留、隨機（原本只認預設全名）。 3.10.0: 跑版檢查修正（2026-11-05，Word 16／Excel 16 實印 178 份樣板，報告 .claude/scratch/20261105-template-layout/report.md）。(a) docx 套印後結尾多一頁白紙（使用者上傳的自主檢查樣板 89／93 種、自主檢查表單張、管制表、矯正與預防處理紀錄、估驗照片）：docx_render.strip_trailing_blank() 存檔前拿掉文件結尾的空段落、分頁符號與空的最後一節。(b) xlsx 百分比印成 0.2098999…（營造版日誌二、進度報告）：整格只有一個 ${...} 且值是數字時寫成數值儲存格（xlsx_placeholder.fill_cell），樣板的 0.00% 格式才生效。(c) 自主檢查總表每隔一頁多一張只有一條直線的紙：分頁複製的工作表沒帶列印範圍（xlsx_sheets 複製 Print_Area／Print_Titles 給每一頁）。(d) 守門：樣板段落編號跳號（復舊工程 stages[0]+stages[2]）原本放行、套印才爆英文錯誤；沒有任何檢查項目標記的樣板（40 種上傳樣板）原本放行、結果整欄空白——兩者改為擋下並說明（template_probe.check_fit）。(e) 送審管制總表沒有編號時「項次」改印流水號（原本印名稱，一字一行）。檢（試）驗管制總表每頁估算行數維持 13：EAGLE 是固定筆數、溢出就讓它溢出，不多花紙（使用者 11-05 裁示照 EAGLE）。(f) 換 7 份系統預設樣板（migration 18.0.3.10.0，被人換過的不覆蓋）：監造日報表二工程名稱被合併儲存格蓋住＋多一條空白列、三份管制表表頭跨頁重複、新北附表8-1／8-2 日期格 10pt、附表7 送審日期去粗體。營造版日誌一不改：EAGLE 原檔就是整張縮成一頁（使用者 11-05 裁示照 EAGLE）。 3.9.0: 正式表單產出 5 個錯誤（2026-11-05 簡報 v4 發現）＋估驗計價表打不開。(a) 照片：docx 套印時照片格的段落拿掉固定行高（矯正與預防處理紀錄 16pt、使用者上傳的 117 份自主檢查樣板 25pt，LibreOffice 會把照片裁成一條）；矯正與預防處理紀錄照樣板標記 {height:6} 縮成高 6 cm、寬上限 12 cm（原本 14×10 cm，Word 上右邊被格子切掉）。(b) 監造日報表第一聯第 13–16 列 1.5pt（施工項目印不出來）：客戶原始表單也是壓扁的、一頁，改高會變兩頁，使用者裁示維持原始版面、不改。(c) 缺失改善成果確認 □符合要求 □逾時未矯正 □未矯正 改成 EAGLE 式只勾一格：已驗證／結案＝符合要求、已改善待驗證三格不勾、未改善依逾期與否擇一（原本已改善勾未矯正、結案三格全空、逾期兩格一起勾）；新北附表12 的改善完成／未完成同一套。(d) 自主檢查表單張的檢查時機：時機沒有舊代碼（複製出來的檢查類型）就依名稱對應（原本四格全空）；「測試樣板」預覽同一套。(e) 工程估驗計價單：分類改成葉節點依工項樹最上層祖先分組（原本用項次前綴找子項，壹／一／(一)／1 對不到 → 0；子類混列；只有葉節點的估驗單整段空白），金額用進度報告的 _amounts()，補累計欄；合計（僅合約項）改用契約工項小計（原本含非契約工項）。(f) 估驗計價表樣板拿掉殘留的 calcChain（e9ae543 起 Excel 正常模式打不開）。migration 依 git 歷史 checksum 換 estimate_report 預設樣板，被人換過的不動；seed_default_templates 換檔時舊附件還被別的樣板（「複製樣板」的副本）指著，就各複製一份掛到那些樣板自己身上（原本直接刪掉、副本靜靜變空；多公司庫裡也不能只掛一份，別家公司會讀不到）。 3.8.3: 匯出的日期提醒拿掉原樣顯示的 markdown 星號。3.8.2: (T5) 業主機關沒填印空白（原本回退印某一家機關）；材料試驗報告送審函不再印死任泰的負責人與 email（email 接監造公司，負責人留空）；預設空白樣板清掉出貨者內網路徑、舊案外部連結路徑、建立者帳號；migration 把舊版預設樣板換成新版（被人換過的不覆蓋）。(T7) 預設樣板附件改非公開（原本未登入可用 /web/content/<連號 id> 下載），migration 一併把既有附件設非公開並回填 res_id。 3.8.1: 升級補灌系統預設「自主檢查表（單張）」樣板（原本只有全新安裝才建，升級上來的庫 0 筆，匯出跳「找不到可用的自主檢查表樣板」）；既有的一律不覆蓋。 3.8.0: 實際進度照說明書改成「本日實際進度」每日增量的加總（只算已填寫／鎖定，與進度表同步相同）；有舊系統 xlsm 匯入的累計值時以最後一張為基準、只加之後的增量（舊日誌重印與換版前相同）——撤回 3.6.0「最後一次有填的累計值」。自主檢查套印：結果欄位不是標準樣式時依勾選印欄，新增 partialMark（不足欄）；測試樣板輪流給該樣式的勾選。需 construction_quality 18.0.6.6.0。 3.7.0: 新北市政府工程契約附表 10 種（只帶表頭，其餘手填）：施工計畫／品質計畫審查意見表（附表4／5）、計畫送審核章表（附表6-2，帶計畫送審的提報、審查、核定日期文號）、材料設備申請及審查紀錄表（附表7，帶送審項目與審查結果）、廠商品管人員／工地相關人員登錄表（附表8-1／8-2）、施工品質評量表（契約附表八）、專任工程人員督察紀錄表（附表10-1）、施工日誌之技術士簽章表、土石方運送附件（第九條附件一、二、四）。表頭共用 mappings/project_header.py；批次下載中心「契約附表」與計畫送審／材料送審表單按鈕在 construction_batch 2.10.0。審查修正：docx 沙箱另擋 Odoo 記錄的屬性與以鍵取值（record.x、record['x'] 都直接 SecurityError）；估驗附件填表日期固定用台北時區換日期；累計預定進度改依日期自己累加（不依賴 cumulative_planned，序號相同時不重複計算）。 3.6.0: 新北市政府工程契約表單（2026-10-25，樣板由 tools/ntpc_forms/ 從契約 Word 原表切出）。(a) 營造版施工日誌第一聯 daily_log_c1：第四項技術士、第五項(一)勤前教育／防護具原本寫死勾選、新進勞工 ${value9-*} 沒供值——不管日誌填什麼都印同一個答案；改成依資料印 ■／□，補「表報編號：」與註 8。(b) 營造版與監造版日誌的預定進度改印累計（原本印的是當日份額，dev 最大 0.23%）、實際進度改印當天或之前最後一次有填的累計（utils/progress.py）。(c) 缺失改善對照表加 foundAt／location／recheckAt／doneBox／undoneBox／supervisorCompany（附表12 用；舊 key 不動）。(d) 自主檢查單張加分欄勾記 item.passMark／defectMark／naMark、inspection.inspector／defectCount／note／timingBox（新北固定清單檢查表用；守門與「測試樣板」共用 checklist_item()，測試假資料輪流給合格／缺失／無此項目）。(e) 新類型 material_inspection_record（附表11）、estimate_progress_report（第五條附件一＋二）各一支對照表、系統預設樣板、按鈕。(f) docx 套印改用 jinja2 SandboxedEnvironment（樣板注入可在主機執行運算式；dev 123 份樣板回歸產出相同）。(g) seed_default_templates 加 types／replaceable：migration 只灌新類型與 c1，系統裡被人換過的預設樣板不覆蓋。(h) zip_patch 加 removals。 3.5.5: 施工日誌-第一聯（daily_log_1）「三、查核材料規格及品質」——只印沒有連結契約材料清單的列（人工手填＝加這個功能之前的全部列；filter）。連結列（construction_daily_log 18.0.2.10.0 自動帶入的約定重要材料）是營造廠的工地材料使用量，印在營造版第一聯 daily_log_c1；印在監造的查核材料這一節語意不對，還會搶預留的 5 列、把查核紀錄擠出報表。max_rows 不動；daily_log_c1 不動。 3.5.4: 估驗計價單表單的「匯出進度報告」按鈕暫時隱藏（使用者 2026-10-19 裁示；invisible="1"，程式與對照表都保留，恢復方式寫在 views/payment_estimate_export_views.xml）。原因：這份以估驗單明細為工項清單，匯入建的估驗單只有工作簿有填的工項、契約變更後的「同步估驗計價工項」要手動按且不更新單價 → 完成百分率分母可能不完整。進度報告改用「工程管理 > 進度管理 > 進度報告」（報表／下載中心也是那一份），不受影響。 3.5.3: 契約變更刪掉的工項（估驗明細變更後核定數量 0）—— `approved_qty or contract_qty` 把 0 當成沒填、退回原契約數量 → 進度報告完成百分率的分母多算（開發庫 test-P11001 多 1,486,432.50，1.15、1.32）、估驗詳細表（二）欄與進度報告契約數量欄印原數量。改：變更後核定數量 0 且工項現在的契約數量也是 0 → 當成真的 0（分母不算、兩張表印 0）；變更後沒填、工項現在不是 0 的舊資料照舊退回原契約數量。 3.5.2: 「匯出進度報告」（估驗單為期間錨點）完成百分率的分母（契約金額）—— 原本一律 Σ 核定數量 × 單價，自主品管費、稅什費這類沒有單價的工項（整包項 xml_amount／比例項 比例×基數）不在分母、卻在分子 → 百分率偏高；construction_payment 18.0.1.8.1 把累計金額改對之後更明顯（開發庫 111-20-AEF-V 第13期累計 99.52%，應為 89.66%）。沒有單價的葉節點改用工項的 planned_amount，有單價的照舊。新增 tests/test_progress_report_amounts.py。估驗詳細表（三）單價欄依使用者裁示維持空白。 3.5.1: 施工日誌-第一聯（監造日報表第一聯，daily_log_1）對照表兩處調整：四（一）施工前檢查——施工日誌三個小題（safety_pre_work_education／safety_labor_insurance_check／safety_ppe_check）都有勾選（不論勾什麼）勾「■完成」，任何一題沒勾勾「■未完成」；五、其他約定監造事項——除了 notes 再加 subcontractor_notification，兩個都有值時各以「●」開頭分段。 3.5.0: 🔴 照片印出來的順序是**反的** —— supervision.photo 的 _order 是 'shot_at desc, id desc'（照片管理的清單要最新在前，那是對的），但列印到檢查表上時第 1 張應該是現場先拍的那張。三張照片實際印成 3→2→1（2026-09-14 使用者照手冊逐格驗證時發現）。⚠️ 我的自動測試只數了「有幾張圖」、沒有檢查順序，所以完全沒抓到。_images() 改為依 shot_date → shot_at → id 遞增排序（拍攝日期常常沒填，id 遞增＝建立順序＝先拍先傳）。 3.4.0: 🔴 反推的「請先清空」對量測區塊是**死結** —— 區塊一旦被檢查紀錄的量測列用過就刪不掉（ondelete='restrict'），要求先清空等於要求使用者先去刪歷史量測資料（使用者實測撞上：「此量測區塊已被 3 筆『一般式自主檢查量測列』使用」，當下以為整個檢查類型廢了）。改為：只擋「預設檢查項目」，量測區塊**同名沿用、一個欄位都不動**——句型尤其不能覆蓋，反推只給得出佔位句型，而既有區塊的句型往往已經被使用者填成正確的了。 3.3.0: 使用者拿 10 份測試樣板去按「從樣板匯入設定」（那批其實是設計來測「匯出」的守門），打出反推路徑的三個問題：(a) 🔴「已有資料」只檢查 default_item_ids、**漏了 measure_ids** —— 反推一次建了量測區塊、照訊息清掉預設檢查項目後再反推，這一關放行卻撞 UNIQUE，使用者看到的是「同一檢查類型內的量測區塊標題不可重複！」這種不知道要幹嘛的訊息；現在會列出「已經有：量測區塊 N 個」並說兩個分頁都要清。(b) 沒有佔位符的空白紙本被說成「這份樣板是動態表格格式」—— 兩種情況原因完全不同，訊息已分流。(c) 反推路徑沒檢查副檔名，上傳 .xlsx 會直接噴 zip 的英文錯誤。 3.2.0: 為了回答「79 份以外的新樣板有什麼限制」而逐條造正反例實測，又打出兩個缺陷：(a) 量測區塊的延續列，那 79 份用 vMerge、使用者自己做的樣板則常把標題格**留白**——兩者在紙上一模一樣，但原本只認 vMerge，留白會讓一個 8 列的區塊裂成 1+7 兩個，套印時後半段還會把前半段填好的量測資料整個蓋成空白（完全吻合的樣板反而被擋下，說「只有 7 項」）；(b) 樣板裡沒有量測段落時，已填的量測記錄**靜靜消失且不報錯**——新增 Probe.has_measure_slot()（硬編看單欄位連續列、動態看 inspection.measures 迴圈），有量測列但樣板印不出來就擋下並說明兩種處理方式。 3.1.0: 新增「樣板欄位名稱守門」(utils/template_tokens.py) —— 使用者問「79 份以外的新樣板能不能用」，實測造了 5 份新樣板才發現兩個靜默失敗：(a) 把空白紙本當樣板上傳(完全沒有佔位符) (b) 欄位名稱拼錯或自己發明(projectTitle / item.detail)。兩者 docxtpl 都不報錯 —— Jinja2 的 Undefined 直接印成空字串，產出一份「每一格都空白但看起來很正常」的檔案，使用者只會以為是自己沒填資料。現在套印前會先驗欄位名稱：認得 {{ }}/{%% for %%}/+++INS+++/+++FOR+++/+++IMAGE+++ 五種寫法，會追蹤迴圈變數的綁定(item.standard → inspection.stages[].items[].standard)，對照 mappings 的 TOKEN_SCHEMA。實測 79 份既有樣板＋系統預設樣板誤報 0，兩份刻意寫錯的都被精確指出是哪幾個欄位。 3.0.1: 使用者用真實鋼筋樣板實測打出四個缺陷 —— (a) 反推後要按 F5 才看得到新項目（action 補 next: reload）；(b) 反推的 sequence 每段各自從 10 起算，而「預設檢查項目」清單有 handle widget、前端只依 sequence 排序不看 stage_sequence → 畫面上段落整個交錯（改全域遞增，與既有匯入資料的慣例一致）；(c) 測試樣板每格都填「測試」兩個字，錯位完全看不出來 → 標準欄改填項目名稱、情形欄改填段-項編號；(d) 🔴 照片完全沒進去 —— IMAGE_RE 只認數字索引 images[0]，但 79 份自主檢查樣板全部用 images[$evenIndex] 與 [$evenIndex + 1]；連 IF_RE 也因為條件式含 '+' 而匹配不到。兩個 regex 都改成非貪婪；另外奇數張照片時最後一格會越界拋 UndefinedError（EAGLE 原靠 +++IF+++ 擋，而我們會移除它），改為補一格空白照片。同時：硬編樣板的量測列不足時**補空白**補到樣板列數（紙本預印 8 列實填 2 列是常態，原本會被守門誤判成「資料比樣板少」）。 3.0.0: 新增「自主檢查表（單張）」套印 —— 一張檢查紀錄一份 Word 檔。 樣板兩層來源：檢查類型上傳的 template_file 優先，沒上傳才用 document.template 的 self_inspection_form（上傳的樣板不放 document.template，因為它有 UNIQUE(template_type, project_id)，幾十種檢查表塞不進去）。 新增 mappings/self_inspection_form.py（context 必須用 SimpleNamespace——Jinja2 的 . 存取先找 attribute，dict 的 items 會蓋掉同名資料鍵）、utils/template_probe.py（偵測硬編/動態樣板＋逐列比對名稱的守門＋反推）、檢查類型的「測試樣板」與「從樣板匯入設定」按鈕。docx_render._swap_images 同步支援 SimpleNamespace，否則巢狀在 namespace 裡的照片標記換不到 InlineImage、照片會靜靜不見。 2.9.0: 預約式回報單樣板——彙總列不印單價數量，預估金額改「手填優先、沒填才用明細預估合計」。
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
        'report/daily_log_report_progress.xml',
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
