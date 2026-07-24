# -*- coding: utf-8 -*-
"""M0.6：把既有前台「照片」附件 public=True 收成 False（跨 DB 可重現）。

背景（稽核 M-c）：前台照片附件原一律 public=True → 短網址 /web/content/<id>
繞過 record rule，任何登入者可連號枚舉全庫照片。程式碼改動已讓「新」照片
public=False 並改走帶權限的 /construction/img，本 post-migration 在每次升級
（每個 DB，含各租戶庫）自動回填「既有」照片，取代一次性手動 SQL。
（文件庫附件的對應回填見 18.0.2.2.1。）

刻意的允許清單：只收 image mimetype、且屬前台照片綁定型別，避免動到 website
資產(ir.ui.view)、HR、文件範本、supervision.document、chatter 等。冪等。
"""


def migrate(cr, version):
    cr.execute(
        """
        UPDATE ir_attachment SET public = false
        WHERE public = true
          AND mimetype LIKE 'image/%%'
          AND (
                id IN (SELECT attachment_id FROM supervision_photo
                       WHERE attachment_id IS NOT NULL)
                OR (res_model IN (
                        'supervision.photo', 'project.project', 'daily.log.sheet',
                        'general.self.inspection', 'reservation.notification.slip',
                        'supervision.defect', 'acceptance.defect')
                    AND res_field IS NULL)
                OR (res_model LIKE '%%.improvement.photo' AND res_field = 'image')
          )
        """
    )
