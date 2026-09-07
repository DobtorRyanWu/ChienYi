# -*- coding: utf-8 -*-
{
    'name': '工程計價與請款管理',
    # 1.1.0: 併入 GitHub 上游修正 b9677e4 —— previous_approved_qty 納入 archived 估驗
    #        （archived 是「已核定後歸檔」，數量仍有效；原本只認 approved，
    #        前期估驗一歸檔，後期「前期已核定累計」就漏掉該期數量）
    # 附件自動歸類：掛 supervision.attachment.mixin，上傳的附件自動帶所屬工程與文件分類
    # 1.3.0: 移除 payment.estimate.slip_id —— 估驗計價與通報單在功能上無關
    #        （計價表是契約詳細價目表 × 期別的鏡像，通報單不出現在計價單上；
    #          一期橫跨多張通報單、一張通報單的量也會被切到多期，任何單值/多值
    #          關聯都表達不了）。匯入精靈的預約式分支一併移除，兩式行為一致。
    #        通報單的 valuation_count 改為「本工程已估驗次數」（工程層級）。
    #        ⚠ DB 的 payment_estimate.slip_id 欄位不會被 Odoo 自動刪除，
    #          升級後會留成孤兒欄位（全 NULL，無外鍵行為影響），可日後手動清理。
    # 1.4.0: 估驗計價支援照片 —— supervision.photo 新增 estimate_id 來源外鍵、
    #        payment.estimate 加 photo_ids 與「照片」頁籤（批次上傳精靈沿用
    #        construction_photo 的 action_photo_upload_wizard）。
    # 1.4.1: _photo_source_model_code() 由 'other' 改回 'estimate' —— 使用者要求
    #        估驗計價照片要能單獨篩選。原本擋著不加的理由（地圖 JS 的
    #        SOURCE_COLORS / SOURCE_LABELS 寫死、會變成無名灰點）已隨
    #        construction_photo 18.0.3.6.0 一併補上對照表而解除。
    # 1.5.0: 估驗計價明細開放手動編輯「本次估驗金額」（原本只有本次估驗數量可編）。
    #        手動值優先於 單價 × 本次估驗數量：以 is_amount_manual +
    #        manual_estimate_amount 兩個欄位保存人工輸入，數量／單價之後再變動也不會
    #        被系統計算值蓋掉；取消勾選「金額手動輸入」即還原為系統計算值。
    #        本次估驗總金額與累計估驗金額一併沿用手動值。
    # 1.5.1: 估驗計價表欄位已很擠 —— 拿掉「金額手動輸入」勾選欄（改 column_invisible，
    #        手動列以粗體標示），解除手動改走表頭按鈕「解除手動金額」開精靈
    #        （estimate.manual.amount.wizard）：列出所有手動金額工項與系統計算值／差額，
    #        逐項勾選要解除或保留。
    # 1.6.0: 估驗計價支援「非契約工項」（有價廢料變賣收入、物價調整…）。
    #        估驗詳細表的頂層不是只有「壹 發包工程費」——政府工程的估驗表上固定還有
    #        契約工項樹裡沒有的項目，而且行為相反：「貳 物價調整」要計入本次估驗總額
    #        （照樣扣保留款），「參 變賣收入項」不計入（有價廢料的錢另走解繳鏈）。
    #        士林區通河東街1段排水改善工程 111-20-AEF 的 13 期估驗每一期都有這兩種。
    #        新增兩個模型，一列都不寫 project.task：
    #          payment.estimate.extra.item  工程層級的非契約工項（自參照階層，
    #                                       跨期身分＝code，**不是名稱**——「貳」那一列
    #                                       每期顯示名稱都不同，用名稱會讓累計鏈斷掉）
    #          payment.estimate.extra.line  某一期對某一項的估驗（本次數量／本次金額）
    #        payment.estimate 加 extra_line_ids 與三個小計欄
    #        （contract_subtotal / extra_subtotal / extra_excluded_total），
    #        subtotal = 契約工項小計 + 有勾「計入估驗總額」的非契約工項。
    #        沿用到下一期：匯入精靈建立估驗單時自動帶入（數量 0），
    #        也可在表頭按「帶入非契約工項」。
    #        ⚠ include_in_subtotal 目前只影響「本次估驗總金額」。契約附註另一種收取
    #          方式「由工程估驗款內扣抵」（本期應扣金額）在本系統還沒有承載欄位
    #          （payment.estimate 上只有 subtotal，沒有保留款／核發金額／應扣金額），
    #          那一種情境**目前表達不了**，不要用這個旗標硬湊。
    #        ⚠ 金額一律存來源估驗詳細表印的正數（變賣收入雖是廠商付錢給機關，
    #          來源表印的也是正數），方向由 include_in_subtotal 表達。
    # 1.6.1: 「新增非契約工項」改走**精靈對話框**（estimate.extra.item.wizard），
    #        比照 契約變更單 ▸ 匯入工程案件精靈 ▸ 工項列表頁籤 ▸ [新增工項] 的做法。
    #        原本做成「明細列 Many2one 下拉打字快速建立」是錯的順序：這類工項在契約工項
    #        建立時根本不存在，卻要使用者先去一個必然是空的下拉裡找。
    #        🔴 併同修正一個會靜靜改掉已核定金額的設計缺陷：
    #        payment.estimate.extra.line 的 unit_price 與 include_in_subtotal 由
    #        「related 到工項定義（跨期共用一份）」改為**每期各存一份的快照**。
    #        原本在第 11 期把單價 500 改成 600，會連帶把已核定的第 8 期金額重算成
    #        600 × 數量（使用者實例：「XXX回收」同一工項逐期改價）。
    #        規則與契約工項那條路一致 —— payment.estimate.line 的 contract_qty /
    #        approved_qty / unit_price 也都是建列當下抄一次的快照。
    #        累計因此走「金額相加」而非「累計數量 × 單價」，單價中途變動累計仍正確。
    #        工項定義上的那兩欄降級為「建新期別時的預設值」；
    #        `_prepare_line_vals` 帶入時優先沿用**最近一期**的值，不是定義的原始值。
    #        明細清單改為 create="false"（新增一律走精靈）、定義欄位（項目編號／單位／
    #        父項）唯讀，只留「本期」的東西可改。
    # 1.6.2: 使用者實測回饋三項。
    #        ① 清單欄位「非契約工項」→「項目名稱」，顯示 item_display_name
    #           （本期顯示名稱有填就顯示它，留空顯示工項名稱）；原本的 M2O 降為
    #           optional 隱藏欄「工項定義」，仍可點連結去改編號／單位／父項。
    #        ② 🔴 「計入估驗總額」改由**彙總項**決定。原本 subtotal 加總葉列，
    #           結果「勾子項有反應、勾彙總項沒反應」，而且允許同一彙總項底下
    #           一部分計入一部分不計入 —— 使用者指出那在實務上不成立。
    #           改為加總**本期的根列**（彙總列金額本來就是子項合計，加總根列剛好
    #           每筆算一次）；改彙總項旗標會 propagate 到底下所有子列；
    #           子列與父列不一致時 _check_include_matches_parent 直接擋；
    #           清單與精靈裡子列的該欄改唯讀。
    #        ③ 單位「式」→ 本次數量不可超過 1（_check_lump_sum_qty），
    #           比照 construction_daily_log.daily_log_line
    #           ._check_lump_sum_not_over_contract（只擋「式」）。
    #           ⚠ 與日誌那支的差別：那邊是「累計 ≤ 契約量」，這邊沒有契約量可比，
    #             判準是**逐期 ≤ 1**。刻意不做跨期累計 —— 實案「貳 第N次估驗物價調整
    #             累計金額」每期都印數量 1（通河東街 11 期），那不是「一式分期完成」
    #             而是每期各自獨立的金額，套累計限制會把真實資料整批擋掉。
    # 1.6.3: 🔴 明細清單只留**一個**名稱欄。使用者實測：清單上並排「工項名稱」與
    #        「本期顯示名稱」兩欄很反直覺，不知道哪一個才是對的 —— 那等於把
    #        「定義層 ＋ 覆寫層」這個內部實作攤給使用者看。而且它與 1.6.1 的決定
    #        不一致：unit_price 已經是「每期一份的快照」，名稱卻走覆寫。
    #        改為名稱也是快照：payment.estimate.extra.line.name（required），
    #        拿掉 name_override 與 item_display_name。
    #          ・建立時從工項定義的名稱帶入
    #          ・「帶入下一期」沿用**最近一期**的名稱（「第7次…」只要改一個數字，
    #            比回頭用通用名稱好用）
    #          ・在任一期改它只影響那一期，其他期別與工項定義都不動
    #        跨期身分自始至終是 extra_item_id / code，與名稱無關，
    #        所以逐期改名累計鏈不會斷（通河東街 11 期物價調整已實證）。
    #        工項定義上的 name 降級為「第一次建立時的預設值」。
    #        附 migrations/18.0.1.6.3/pre-migrate.py：name 是 required，
    #        既有列若為 NULL 會讓 NOT NULL 那一步直接失敗，故在 ORM 載入前
    #        先用 SQL 建欄並由 name_override／工項名稱填滿。
    # 1.6.4: 使用者實測回饋（刪除行為）。
    #        ① 刪掉明細列後，工項定義變成孤兒 —— 繼續出現在「父工項」下拉裡，
    #           「帶入上期項目」還會把它拉回來。改為：明細列 unlink 之後，
    #           把「完全沒有任何期別在用」的定義**封存**（active=False）。
    #           不是刪掉 —— 要留「誤刪之後加回來」的路：用同一個識別碼重新新增時，
    #           精靈會把封存的定義**復活並沿用**，之前各期的金額與累計鏈原封不動。
    #        ② 「帶入上期項目」原本抓**全工程**的項目，於是在本期刪掉的列一按就整批
    #           回來（使用者：「被我刪除的那 3 個又都出現了」）。而且按鈕名稱寫「上期」、
    #           程式做「全部」，名實不符。改成只帶「上一期實際有的項目」。
    #        ③ 同一父工項底下的**項目編號不可重複**（_check_item_no_unique_among_siblings）。
    #           使用者實測建出了兩個頂層「參」。範圍刻意是「同層」而非「整個工程」：
    #           「參」底下有「1」、「肆」底下也有「1」是正常的。
    #        ④ 精靈的「父工項」下拉只列**本期估驗單上已經有的**項目
    #           （原本列整個工程，所以本期刪掉的照樣出現）。
    #        ⑤ 欄位標籤「父項」→「父工項」。
    #        ⚠ 另一個復活途徑是前端的：在估驗單上刪了列**還沒存檔**就開精靈，
    #          對話框關閉時表單重載會把未存檔的刪除丟掉。伺服器端已確認刪除有生效
    #          （見交付文件的說明），操作上請先存檔再開精靈。
    # 1.6.5: 使用者追問 1.6.4 的「誤刪加回來」在兩種情況下成不成立 —— 實測後：
    #        ① **沒填識別碼時會直接崩潰**（識別碼是選填的，很多人從頭到尾不填）。
    #           `_make_code` 用 `search_count()` 看不到已封存的列，於是「刪光 → 封存 →
    #           同名再建一次」會產生一模一樣的 code，撞上 SQL 的
    #           UNIQUE(project_id, code) 拋 psycopg2.UniqueViolation ——
    #           使用者看到的是完全看不懂的原始 SQL 錯誤。
    #           修法兩層：`_make_code` 改成 `active_test=False`（不會再產生撞號的 code）；
    #           精靈在沒給識別碼時改用**名稱 ＋ 父工項**去找封存的定義來復活。
    #           復活是安全的 —— 定義只在「完全沒有任何期別在用」時才封存，不夾帶舊金額。
    #        ② **封存的項目編號不會擋住新工項**（使用者問的：A 是參.1，全刪之後
    #           新建的 B 也要用參.1）—— 實測確認本來就不擋，因為
    #           `_check_item_no_unique_among_siblings` 用 `search()`，預設排除封存。
    #           已補回歸測試鎖住這個行為，免得日後有人「順手」把它改成 active_test=False。
    # 1.7.0: 🔴 **廢除「封存」，改為徹底刪除** —— 使用者實測後提出，正確。
    #        1.6.4 把「明細列被刪光的定義」改成封存，想留誤刪的回頭路。那是錯的方向：
    #        封存 ＝ **看不見也改不動的隱藏狀態**，配上 UNIQUE(project_id, code)
    #        連續製造兩次事故 ——
    #          ・1.6.5：_make_code() 看不到封存列 → 撞號 → 原始 SQL 錯誤
    #          ・使用者實測：一個工程累積 5 筆封存定義、3 筆同名「廢料變賣」、
    #            「預設計入」互相矛盾；新增子項時繼承到哪一筆看不出來，
    #            使用者在畫面上一個都看不到、也修不了。
    #        改法：
    #          ① extra.line.unlink() → 沒人用的定義**直接刪掉**（仍是由下往上逐層）。
    #             沒有東西會遺失：定義只在「零明細列」時才清，那時沒有金額也沒有累計。
    #          ② **移除 active 欄位本身**，杜絕再度製造隱藏狀態。
    #          ③ 精靈新增「選用已建立的項目」頁籤 —— 本工程其他期別建過、本期還沒有的
    #             項目，勾起來就加進本期。這就是「誤刪加回來」的入口，**而且看得見**。
    #             拿掉所有「用同一個識別碼／同名復活」的隱形邏輯。
    #          ④ 修掉使用者回報的「我明明關掉計入，按下新增卻自動勾起來」：
    #             _onchange_parent_item_id 原本在找不到父列時會**退回工項定義的預設值**，
    #             而定義上的旗標使用者根本看不到。改成只認「父工項在本期的那一列」
    #             （下拉本來就只列本期有的項目，必然存在）。
    #        附 migrations/18.0.1.7.0/pre-migrate.py：刪掉既有的封存孤兒（逐層迴圈）、
    #        把仍被參照的封存列解除封存讓它現形、最後 DROP 掉 active 欄。
    # 1.7.1: 🔴 「上一期」的判定在**同一天建立多期**時整組落空。
    #        使用者實測：兩期都是當天日期，按「帶入上期項目」得到
    #        「上一期沒有非契約工項」。原因是 domain 寫 `estimate_date <`
    #        （嚴格小於）—— 但同日多期是完全正常的操作（補建歷史資料時
    #        一天把十幾期都建出來是常態），日期本身不足以定序。
    #        改成與 `_resequence_estimate_no()`（也就是畫面上的「第N次」）
    #        **完全同一套排序** (estimate_date asc, id asc)，新增
    #        `_estimates_before()` / `_previous_estimate()` 兩個 helper。
    #        `extra.line._prepare_line_vals` 的「沿用最近一期單價／名稱／旗標」
    #        一併改用同一套 —— 它原本用 `estimate_date <=`，同日時甚至可能
    #        撈到排在本期**後面**的那一期。
    #        🔴 順帶查出**既有功能同樣中招**：payment.estimate.line 的
    #        `_compute_previous_approved_qty` 與 `_compute_available_qty` 也用
    #        `estimate_date <`。同日兩期各估 30 / 20 時，第2期的「前期已核定累計」
    #        算成 0、「累計估驗數量」20（應為 50）、累計金額 200（應為 500），
    #        而且**不會報任何錯**。三處一併改用 `_estimates_before()`。
    #        （既有專案多半一期一個月、日期互異，所以這個 bug 一直是休眠的；
    #          它在「一天之內補建多期歷史資料」時才會發作 —— 正是使用者的操作。）
    #        🔴 併同修掉第二個孤兒來源：`extra.line.estimate_id` 是
    #        `ondelete='cascade'`（**資料庫層** ON DELETE CASCADE），刪整張估驗單時
    #        Postgres 直接清掉子列，**Python 的 extra.line.unlink() 不會被呼叫** ——
    #        於是「沒人用的定義一併刪掉」的清理整段跳過，留下孤兒（實測重現）。
    #        payment.estimate 加 unlink() 覆寫，先用 ORM 刪 extra_line_ids。
    'version': '18.0.1.7.2',
    # 1.7.2: 效能：`payment.estimate.line._compute_previous_approved_qty` 與
    #        `extra.line._compute_previous_approved` 加 before_cache ——
    #        原本每一列都要重跑一次 `_estimates_before()`，一張估驗單查上百次。
    #        ⚠ **本版曾加入「同一工程同一估驗日期只能有一張估驗計價單」的約束
    #          （_check_one_estimate_per_date），已依使用者裁示撤掉，不要再加回去。**
    #          兩個理由：
    #          ① 資料庫裡本來就有同日重複的舊資料（地端 system_development 有 2 組：
    #             DEMO-2026-003 / 2026-08-18、PRJ-2026-0017 / 2026-09-07），
    #             擋新的不會讓舊的變乾淨。
    #          ② **補建歷史資料時一天之內建十幾期是常態** —— 那正是匯入工具
    #             （E:\work\匯入 的步驟 14）在做的事。加了約束等於把匯入流程擋死。
    #          正確解法就是 1.7.1 已經做掉的那個：**不要拿日期定序，
    #          走 `_estimates_before()`**（estimate_date asc, id asc，
    #          與畫面上的「第N次」一致）。同日多期在功能上是完整支援的。
    'category': 'Construction',
    'summary': '估驗計價、工項驗收、請款管理',
    'description': """
工程計價與請款管理模組
======================

此模組提供工程專案的計價與請款功能：

主要功能
--------
* 估驗計價 (payment.estimate)
    - 分期估驗計畫與累計追蹤
    - 施工廠商提交，監造審查
    - 預算 vs 實際對比分析

* 工項驗收 (work.acceptance)
    - 監造驗收施工廠商完成的工項
    - 支援部分驗收與完工驗收
    - 驗收通過後可提交估驗計價

* 請款單 (payment.claim)
    - 向業主（政府機關）請款
    - 支援服務費（監造）和工程款（廠商）
    - 基於估驗計價或驗收單產生

設計說明
--------
* 不依賴 purchase 模組，獨立設計驗收與請款流程
* 支援多公司架構（設計監造/施工廠商分離）
* 完整狀態流程與審核機制
    """,
    'author': 'Construction Supervision System',
    'website': '',
    'license': 'LGPL-3',
    'depends': [
        'construction_supervision_base',
        'construction_daily_log',
        'construction_contract_change',
        'construction_notification_slip',
        'construction_progress',
        'construction_photo',
        'mail',
    ],
    'data': [
        # Security
        'security/ir.model.access.csv',
        # Data
        'data/ir_sequence_data.xml',
        # Wizard
        'wizard/progress_activate_wizard_views.xml',
        # Views
        'views/estimate_import_wizard_views.xml',
        'views/estimate_manual_amount_wizard_views.xml',
        'views/estimate_extra_item_wizard_views.xml',
        'views/payment_estimate_extra_views.xml',
        'views/payment_estimate_views.xml',
        'views/work_acceptance_views.xml',
        'views/payment_claim_views.xml',
        'views/supervision_project_views.xml',
        'views/estimate_sync_wizard_views.xml',
        'views/menu.xml',
        'report/payment_estimate_report.xml',
    ],
    'demo': [],
    'installable': True,
    'application': False,
    'auto_install': False,
}
