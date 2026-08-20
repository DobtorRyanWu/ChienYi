# -*- coding: utf-8 -*-
# 解除「11-工程資料 ～ 18-府查核」分類樹的 noupdate 保護，讓 XML 之後說了算。
#
# 背景：這批分類當初以 <data noupdate="1"> 建立，旗標寫在 ir_model_data 這一列上。
# 只要旗標還是 true，之後不管 data/document_category_data.xml 怎麼改，升級時
# 都會被略過（4.8.1 對舊的 24 筆分類已經踩過同一個坑）。
#
# 本次要做的三件事全部卡在這個旗標上：
#   1. 4 筆改名（11_01、17_01、17_02、17_03）
#   2. 2 筆停用（16_01、16_02）
#   3. 11_04 補 extra_folder_names
#
# 為什麼放 pre 而不是 post：
# 升級順序是「pre-migration → 載入 XML → post-migration」。在 pre 階段先清掉旗標，
# 接著載入 XML 時上面三件事就會自動套用，不必在腳本裡再抄一份中文字串
# （name 是 jsonb 欄位，手寫 UPDATE 容易寫壞翻譯結構）。
#
# 這是刻意的取捨：從此這批 is_system 標準分類的名稱以 XML 為準，
# 使用者在後台手動改名會在下次 -u 被還原。它們是全公司共用的標準分類，
# 名稱要跟資料夾樹對得上，本來就不預期各案自行更名。


def migrate(cr, version):
    cr.execute("""
        UPDATE ir_model_data
           SET noupdate = FALSE
         WHERE module = 'construction_supervision_base'
           AND model = 'supervision.document.category'
           AND name LIKE 'cat\\_%%'
    """)
