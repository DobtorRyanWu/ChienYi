# -*- coding: utf-8 -*-

from odoo import api, models

# 前台詳情頁有「訊息」留言區（t-call="portal.message_thread"）的模型。
# 用名稱比對而不是各自 _inherit：supervision.test.record 在 construction_test，
# 本模組沒有依賴它（檢試驗頁是有裝才顯示）。名單有測試守著（test_c_comment_models_exist）。
PORTAL_COMMENT_MODELS = frozenset({
    'daily.log.sheet',
    'general.defect.improvement',
    'reservation.defect.improvement',
    'reservation.notification.slip',
    'general.self.inspection',
    'supervision.test.record',
})
# 老闆 → 主管 → 現場人員 逐層繼承（new_portal_groups.xml），所以問現場人員群組就涵蓋三個角色；
# 定期閱覽者在現場人員之下，不在內，維持唯讀不能留言
PORTAL_COMMENTER_GROUP = 'construction_supervision_base.group_portal_user'


class MailThread(models.AbstractModel):
    _inherit = 'mail.thread'

    def _is_portal_commenter(self, model_name=None):
        return ((model_name or self._name) in PORTAL_COMMENT_MODELS
                and self.env.user.has_group(PORTAL_COMMENTER_GROUP))

    @api.model
    def _get_mail_message_access(self, res_ids, operation, model_name=None):
        """前台留言改看「讀得到」，不再看「寫得進去」。

        Odoo 預設發留言要對那筆紀錄有寫入權。2026-11-04 前台角色的 ORM 寫入權全部收回
        （tests/test_portal_orm_readonly.py），不改這裡前台留言會全部失效。
        誰讀得到由各模型的讀取規則決定：缺失、自主檢查有成員規則；日誌、通報單、檢試驗目前
        沒有前台成員規則（庫內前台帳號都讀得到），與改動前「有寫入權就能留言」的範圍相同。
        留言附檔（mail/controllers/attachment.py）走同一個判斷。
        """
        access = super()._get_mail_message_access(res_ids, operation, model_name=model_name)
        if operation == 'create' and access == 'write' and self._is_portal_commenter(model_name):
            return 'read'
        return access
    # 留言者自動關注放在 controllers/portal.py 的 ConstructionThreadController（只管留言路由），
    # 不覆寫 message_post：覆寫它會影響所有模型的 RPC 回傳值與伺服器動作的「不自動關注」
