# -*- coding: utf-8 -*-
# 修補 supervision.document 走 create 路徑上傳、res_id 卡在 0 的孤兒附件。
#
# 成因（已在 5.10.0 的程式碼修掉）：
#   many2many_binary widget 在記錄尚未儲存時上傳，送出的是 res_id: 0。
#   supervision.document.write() 原本有補正 res_id，**create() 完全沒有**，
#   所以「新增文件 → 上傳附件 → 存檔」產生的附件 res_id 永遠是 0。
#   _compute_attachments() 用 res_model/res_id 找附件，自然一個都找不到，
#   按「標記為已上傳」就報「請先上傳至少一個附件檔案」。
#
# 這些附件的歸屬其實沒有遺失——M2M 中間表
# supervision_document_upload_attachment_rel 記得它們屬於哪份文件，
# 所以可以完整還原 res_id，並順便補上工程／分類／資料夾三個歸類欄位
# （它們同樣因為沒走過補正流程而全是 NULL，在「工程檔案」清單裡是孤兒）。
#
# 一律「已有值不動」：只填空白欄位，不覆蓋任何既有值。

import logging

from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})

    cr.execute("""
        SELECT r.document_id, array_agg(r.attachment_id)
          FROM supervision_document_upload_attachment_rel r
          JOIN ir_attachment a ON a.id = r.attachment_id
         WHERE a.res_model IS DISTINCT FROM 'supervision.document'
            OR a.res_id IS NULL
            OR a.res_id = 0
            OR a.res_id <> r.document_id
         GROUP BY r.document_id
    """)
    rows = cr.fetchall()
    if not rows:
        _logger.info('supervision.document：沒有需要修補的孤兒附件')
        return

    fixed = 0
    for document_id, attachment_ids in rows:
        document = env['supervision.document'].browse(document_id).exists()
        if not document:
            continue
        attachments = env['ir.attachment'].browse(attachment_ids).exists()
        if not attachments:
            continue

        # 依文件分類在該工程的資料夾樹上定位（不存在就建），與程式碼走同一條路徑
        folder = document._document_folder()

        for attachment in attachments:
            vals = {}
            if attachment.res_model != 'supervision.document' \
                    or attachment.res_id != document.id:
                vals['res_model'] = 'supervision.document'
                vals['res_id'] = document.id
            if document.project_id and not attachment.supervision_project_id:
                vals['supervision_project_id'] = document.project_id.id
            if document.document_category_id and not attachment.document_category_id:
                vals['document_category_id'] = document.document_category_id.id
            if folder and not attachment.folder_id:
                vals['folder_id'] = folder.id
            if vals:
                attachment.write(vals)
                fixed += 1

    _logger.info('supervision.document：修補了 %s 個孤兒附件（涵蓋 %s 份文件）',
                 fixed, len(rows))
