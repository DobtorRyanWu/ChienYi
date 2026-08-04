# -*- coding: utf-8 -*-
# 停用舊版的 24 筆系統預設文件分類。
#
# 它們是憑空設計的分類，與實際案件的歸檔資料夾對不上，已由
# 「11-工程資料 ～ 18-府查核」的新分類樹取代（data/document_category_data.xml）。
#
# 為什麼需要 migration 而不是在 XML 加 active=False 就好：
# 這 24 筆當初是用 <data noupdate="1"> 建立的，noupdate 旗標寫在
# ir_model_data 這一列上；只要那個旗標還是 true，之後不管 XML 怎麼改，
# 升級時都會被略過（實測 -u 後 24 筆仍是 active）。所以這裡直接改資料，
# 並順手把 noupdate 清掉，讓 XML 之後才真的說了算。
#
# 只停用不刪除：既有文件的 document_category_id 仍指向它們，
# 刪掉會造成資料遺失；active=False 只是不再出現在下拉選單。

OLD_CATEGORY_XMLIDS = (
    'category_pre_construction',
    'category_construction',
    'category_completion',
    'category_acceptance',
    'category_other',
    'category_personnel_list',
    'category_schedule',
    'category_construction_plan',
    'category_quality_plan',
    'category_safety_plan',
    'category_insurance',
    'category_daily_log',
    'category_supervision_report',
    'category_test_report',
    'category_inspection_record',
    'category_photo',
    'category_meeting_minutes',
    'category_completion_drawing',
    'category_completion_settlement',
    'category_supervision_final_report',
    'category_quality_certificate',
    'category_warranty_certificate',
    'category_correspondence',
    'category_change_order',
)


def migrate(cr, version):
    cr.execute("""
        SELECT res_id FROM ir_model_data
         WHERE module = 'construction_supervision_base'
           AND model = 'supervision.document.category'
           AND name IN %s
    """, (OLD_CATEGORY_XMLIDS,))
    ids = [row[0] for row in cr.fetchall()]
    if not ids:
        return

    cr.execute("""
        UPDATE supervision_document_category SET active = FALSE WHERE id IN %s
    """, (tuple(ids),))

    cr.execute("""
        UPDATE ir_model_data SET noupdate = FALSE
         WHERE module = 'construction_supervision_base'
           AND model = 'supervision.document.category'
           AND name IN %s
    """, (OLD_CATEGORY_XMLIDS,))
