# -*- coding: utf-8 -*-
# 移除 18.0.4.8.0 短暫建立過的「13-照片」文件分類（含 4 個子分類）。
#
# 照片由「照片管理」（supervision.photo）專責管理 —— 那邊有 GPS／EXIF／
# 材料分類／標籤／地圖，是完整的業務物件；再給它一套文件分類等於同一批照片
# 有兩套分類體系。所以文件分類樹不設「13-照片」，data/document_category_data.xml
# 也已把那五筆拿掉。
#
# 為什麼需要 migration：那五筆是用 <data noupdate="1"> 建立的，Odoo 升級時
# 清除失效 xmlid 的機制（_process_end）會跳過 noupdate 的記錄，光把 XML 刪掉
# 資料庫裡仍然留著。這裡直接刪，並清掉對應的 ir_model_data。
#
# 刪除前先確認沒有任何文件或附件在用；有的話只停用不刪，避免資料遺失。

PHOTO_CATEGORY_XMLIDS = ('cat_13', 'cat_13_01', 'cat_13_02', 'cat_13_03', 'cat_13_04')


def migrate(cr, version):
    cr.execute("""
        SELECT res_id FROM ir_model_data
         WHERE module = 'construction_supervision_base'
           AND model = 'supervision.document.category'
           AND name IN %s
    """, (PHOTO_CATEGORY_XMLIDS,))
    ids = tuple(row[0] for row in cr.fetchall())
    if not ids:
        return

    cr.execute("SELECT COUNT(*) FROM supervision_document WHERE document_category_id IN %s", (ids,))
    in_use = cr.fetchone()[0]
    cr.execute("SELECT COUNT(*) FROM ir_attachment WHERE document_category_id IN %s", (ids,))
    in_use += cr.fetchone()[0]

    if in_use:
        # 已經有人用了就只停用，資料照舊指得到
        cr.execute("UPDATE supervision_document_category SET active = FALSE WHERE id IN %s", (ids,))
        return

    # 先斷父子關聯再刪，避免 parent_id 的 cascade 順序問題
    cr.execute("UPDATE supervision_document_category SET parent_id = NULL WHERE id IN %s", (ids,))
    cr.execute("DELETE FROM supervision_document_category WHERE id IN %s", (ids,))
    cr.execute("""
        DELETE FROM ir_model_data
         WHERE module = 'construction_supervision_base'
           AND model = 'supervision.document.category'
           AND name IN %s
    """, (PHOTO_CATEGORY_XMLIDS,))
