# -*- coding: utf-8 -*-
"""M0.6：把既有前台「文件庫」附件 public=True 收成 False（跨 DB 可重現）。

背景（抗辯 finding）：文件庫（supervision.document）上傳附件與照片同屬
public=True 的 /web/content 枚舉破口，且合約 / 計價 PDF 敏感度往往更高。
程式碼改動已讓「新」文件附件 public=False 並改走帶權限的 /construction/doc，
本 post-migration 回填「既有」文件附件。冪等：只改仍為 public=True 者。

允許清單：只收「屬某 supervision.document.upload_attachment_ids」的附件（任何
mimetype），避免動到其他 public 附件。
"""


def migrate(cr, version):
    cr.execute(
        """
        UPDATE ir_attachment SET public = false
        WHERE public = true
          AND id IN (SELECT attachment_id
                     FROM supervision_document_upload_attachment_rel)
        """
    )
