"""匯入暫存檔的保護與清除（計畫 §2.1）。

Odoo 核心的 `base_import.import` 是 transient model，上傳的 xlsx 以明文 bytea
存在資料庫（base_import.py:219,225），預設要 12 小時＋每日 autovacuum 才會清掉，
而且 **ACL 開給所有內部使用者、沒有任何 record rule**——別家公會的職員可以直接
`search_read` 讀到含身分證的名冊，或用 `/base_import/set_file` 換掉別人上傳的檔。

三道處理：
1. global record rule `create_uid = user.id`（security/record_rules.xml）。
2. 匯入 assoc.member 成功後立刻刪掉暫存（**只在最後一批**：前端依 nextrow
   會用同一筆暫存續傳，第一批就刪會讓後面整批失敗）。
3. 每小時 cron 清掉放著沒完成的（測試後放棄、或中途關掉視窗）。
"""

import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)

MEMBER_MODEL = 'assoc.member'
STALE_MINUTES = 15


class BaseImportImport(models.TransientModel):
    _inherit = 'base_import.import'

    # 參數名要與核心一致（前端以關鍵字呼叫）；這個方法內不用 odoo.fields
    def execute_import(self, fields, columns, options, dryrun=False):
        result = super().execute_import(fields, columns, options, dryrun=dryrun)
        if dryrun or self.res_model != MEMBER_MODEL:
            return result
        if result.get('ids'):
            # 軌跡與刪除要分開判斷：有警告或分批時也確實匯進了資料，軌跡不能漏記
            self.env['assoc.audit.log']._log(
                'member_import', count=len(result['ids']),
                detail={'columns': [c for c in columns if c], 'partial': bool(result.get('messages'))})
        if result.get('ids') and not result.get('nextrow') and not result.get('messages'):
            # 有錯誤時暫存要留著讓操作員改完重試，交給 cron 在 15 分鐘後清掉
            # ACL 沒給 unlink，固定 sudo；rule 已確保這筆是自己的
            self.sudo().unlink()
        return result

    @api.model
    def _gc_assoc_member_imports(self):
        """清掉沒跑完的會員匯入暫存（含身分證明文）。"""
        deadline = fields.Datetime.subtract(fields.Datetime.now(), minutes=STALE_MINUTES)
        stale = self.sudo().search([
            ('res_model', '=', MEMBER_MODEL),
            ('write_date', '<', deadline),
        ])
        if stale:
            _logger.info('assoc: 清除 %s 筆逾時的會員匯入暫存', len(stale))
            stale.unlink()
        return True
