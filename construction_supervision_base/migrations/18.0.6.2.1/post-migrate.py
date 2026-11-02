# -*- coding: utf-8 -*-
# 18.0.6.2.1：舊版 24 筆文件分類的 xmlid 改回 noupdate，修好升級收尾失敗。
#
# 18.0.4.8.1 把它們設成 noupdate=FALSE，而 XML 裡已經沒有這些紀錄，於是每次
# -u 本模組，核心 _process_end 都把它們當成「被刪掉的資料」去 unlink，撞上
# 系統分類的刪除守衛，整次升級在最後一步 rc=255（模組其實已升完，後面的
# 測試與清理都沒跑）。
#
# 紀錄本身要留著：既有文件的 document_category_id 還指向它們。
# 設回 noupdate 後 _process_end 就不會碰它們，xmlid 也還在，
# _deactivate_legacy_categories 照常找得到。

LEGACY_CATEGORY_XMLIDS = (
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
        UPDATE ir_model_data SET noupdate = TRUE
         WHERE module = 'construction_supervision_base'
           AND model = 'supervision.document.category'
           AND name IN %s
    """, (LEGACY_CATEGORY_XMLIDS,))
