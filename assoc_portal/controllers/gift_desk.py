"""報到台的禮品領取（計畫 §4、§9）。

繼承 `AssocDesk` 只為了沿用 `_desk_meeting` 那道守衛——**不覆寫它的任何方法**
（繼承 controller 後定義同名不同簽章的 method 會污染整個父類別，
見 memory `feedback_customer_portal_method_collision`）。

掃到受託人之後，台面一次列出「本人＋他代領的委託人」所有還沒領的現場品項，
預設全選，按一下全部領走——四百人的隊伍沒有時間逐項勾。
"""

import base64

from odoo import _, http
from odoo.exceptions import AccessError, UserError
from odoo.http import content_disposition, request

from odoo.addons.assoc_base.tools import DESK_SOURCE_SCAN, desk_ref_source
from odoo.addons.assoc_meeting.controllers.desk import EXPORT_TYPES, AssocDesk, _as_id

# 一次領取的上限：一個人身上不可能有幾百份，收斂掉異常大的請求
CLAIM_LIMIT = 100


class AssocGiftDesk(AssocDesk):

    def _open_campaigns(self, meeting):
        return request.env['assoc.gift.campaign'].sudo().search([
            ('meeting_id', '=', meeting.id), ('state', '=', 'open'),
        ])

    def _desk_member(self, meeting, member_id):
        """報到台指名的會員必須在這場大會的名冊上。

        直接 browse 一個任意 id 就能問出別公會會員的姓名，所以要經名冊過一次。
        """
        member = request.env['assoc.meeting.attendance'].sudo().search([
            ('meeting_id', '=', meeting.id), ('member_id', '=', _as_id(member_id)),
        ], limit=1).member_id
        if not member:
            raise UserError(_('這位會員不在本場大會的名冊上。'))
        return member

    @http.route('/assoc/desk/<int:mid>/gift/lookup', type='json', auth='user')
    def desk_gift_lookup(self, mid, member_id=None, **kw):
        """掃到某位會員之後，列出他現在領得到的東西。"""
        meeting = self._desk_meeting(mid)
        campaigns = self._open_campaigns(meeting)
        if not campaigns:
            return {'status': 'no_campaign', 'rows': []}
        try:
            holder = self._desk_member(meeting, member_id)
        except AccessError:
            raise                      # 權限失敗不能被降級成「查無此人」（fail-open）
        except UserError as err:
            return {'status': 'invalid', 'message': str(err), 'rows': []}
        Entitlement = request.env['assoc.gift.entitlement']
        rows = []
        for campaign in campaigns:
            for row in Entitlement._claimable_for(campaign, holder):
                rows.append(dict(row, campaign_id=campaign.id, campaign_name=campaign.name))
        return {'status': 'ok', 'rows': rows, 'holder_name': holder.name,
                'holder_no': holder.member_no}

    @http.route('/assoc/desk/<int:mid>/gift/claim', type='json', auth='user')
    def desk_gift_claim(self, mid, member_id=None, ids=None, desk_ref=None,
                        reason=None, **kw):
        """領取（逐項勾選與「全部領取」走同一條路）。"""
        meeting = self._desk_meeting(mid)
        try:
            holder = self._desk_member(meeting, member_id)
        except AccessError:
            raise
        except UserError as err:
            return {'status': 'invalid', 'message': str(err)}
        if not isinstance(ids, (list, tuple)):
            # 傳純量進來會在 for 迴圈丟 TypeError → 500 traceback
            return {'status': 'invalid', 'message': _('沒有選到任何品項。')}
        wanted = [_as_id(one) for one in ids[:CLAIM_LIMIT] if _as_id(one)]
        if not wanted:
            return {'status': 'invalid', 'message': _('沒有選到任何品項。')}
        # 只有**掃碼**鑄的參照碼才算「卡被掃過」。手動簽到也會鑄一把（讓沒帶卡的
        # 受託人代簽得了），但拿它來領禮品要走手動路徑：填原因、寫稽核、計入手動筆數。
        # 不分來源的話，報到台只要手動簽到某人就等於取得他的掃碼憑證。
        source = desk_ref_source(request.env, desk_ref, request.env.uid, meeting.id, holder.id)
        scanned = source == DESK_SOURCE_SCAN
        reason = (reason or '').strip()
        if not scanned and not reason:
            return {'status': 'need_reason',
                    'message': _('沒有掃到會員卡的話要填寫原因。')}

        Entitlement = request.env['assoc.gift.entitlement']
        rows = Entitlement.sudo().browse(wanted).exists()
        results = {}
        # 一次請求可能橫跨多個活動（同一場大會辦兩個活動）：分開結算，
        # 每個活動的出席與委託條件都由它自己的 `_claim` 判斷
        for campaign in self._open_campaigns(meeting):
            subset = rows.filtered(lambda r: r.campaign_id == campaign)
            if subset:
                results.update(subset._claim(campaign, holder, scanned, reason or None))
        for missing in set(wanted) - set(results):
            results[missing] = 'invalid'
        claimed = sum(1 for status in results.values() if status == 'claimed')
        return {
            'status': 'ok' if claimed else 'none',
            'claimed': claimed,
            'results': [{'id': key, 'status': value} for key, value in results.items()],
        }

    @http.route('/assoc/gift/export/<int:xid>/download', type='http', auth='user')
    def gift_export_download(self, xid, **kw):
        """下載造冊名單：一律給**存檔的那一份**，不重新產生。

        重產會讓「交出去的檔」與「現在算出來的檔」不一致，
        而這份名單是對外的發放依據，對不上就沒得核對。
        """
        export = request.env['assoc.gift.export'].browse(int(xid)).exists()
        if not export:
            raise request.not_found()
        export.check_access('read')
        export._check_admin()
        content = export.sudo().file
        if not content:
            raise request.not_found()
        # 還原過的批次，權利列已經解綁（`export_id` 清掉了）→ `entitlement_ids` 是空的。
        # 用 `count` 補上筆數，否則這筆軌跡會寫成「下載了 0 個人的個資」。
        rows = export.entitlement_ids.member_id
        request.env['assoc.audit.log']._log(
            'gift_export', records=rows, company=export.company_id,
            count=len(rows) or export.row_count,
            detail={'export_id': export.id, 'download': True, 'state': export.state,
                    'sha256': export.sha256})
        raw = base64.b64decode(content)
        file_type = (export.file_name or '').rsplit('.', 1)[-1]
        return request.make_response(raw, headers=[
            ('Content-Type', EXPORT_TYPES.get(file_type, 'application/octet-stream')),
            ('Content-Length', len(raw)),
            ('Content-Disposition', content_disposition(export.file_name or 'gift.xlsx')),
            ('Cache-Control', 'no-store'),
        ])
