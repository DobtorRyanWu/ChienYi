# -*- coding: utf-8 -*-
"""前台「意見回饋」：客戶填客服單（服務單）、看自己送過的單、在單上與客服對話。

流程圖《客戶服務流程》主圖：客戶建立客服單（含截圖，類型必選）→ 系統產生工單 → 依類型分派。

權限：以前台使用者本人身分建立（不走 sudo），由 ACL＋record rule 把關
（只看得到、只建得了自己送的；不能改、不能刪）。送出後的補充一律走留言。

【分庫】日後每個客戶一個資料庫時，服務單集中到自家的「客服資料庫」，
本檔的建單／列表／詳情／對話都要改成透過 API 向客服資料庫讀寫（已決定方向，尚未實作）。
詳見 docs/分庫架構_集中客服資料庫.md。
"""
from odoo import _, fields, http
from odoo.exceptions import AccessError, MissingError, UserError, ValidationError
from odoo.http import request
from odoo.tools import plaintext2html

from odoo.addons.construction_portal.controllers.portal import ConstructionPortal

TICKET = 'construction.service.ticket'

# 客戶看到的狀態用字（後台的「新建」「待客戶確認」是內部用語）
CUSTOMER_STATE_LABELS = {
    'new': '已送出，待受理',
    'processing': '處理中',
    'waiting_customer': '待您確認',
    'done': '已結案',
    'cancel': '已取消',
}

MAX_FILES = 10


class HelpdeskPortal(ConstructionPortal):

    # ------------------------------------------------------------------
    # 共用
    # ------------------------------------------------------------------
    def _feedback_project(self, project_id):
        """從哪個工程進來（抽屜連結帶 from_project）。看不到的工程一律當作沒有。"""
        try:
            pid = int(project_id or 0)
        except (TypeError, ValueError):
            return request.env['project.project']
        if not pid:
            return request.env['project.project']
        project = request.env['project.project'].sudo().browse(pid).exists()
        if not project or not self._user_can_see_project(project):
            return request.env['project.project']
        return project

    def _feedback_layout_values(self, project):
        """頁首 HUD／抽屜／底部導覽需要的值；不在工程裡時只顯示頁首與抽屜。"""
        values = {'project': project or False}
        if project:
            values.update({
                'day_count': self._get_project_day_count(project),
                'nav_badges': self._get_nav_badges(project),
            })
        return values

    def _feedback_url(self, path, project):
        return path + ('?from_project=%s' % project.id if project else '')

    # ------------------------------------------------------------------
    # 列表
    # ------------------------------------------------------------------
    @http.route(['/construction/feedback'], type='http', auth='user', website=True)
    def portal_feedback_list(self, from_project=None, **kw):
        project = self._feedback_project(from_project)
        tickets = request.env[TICKET].search(
            [('create_uid', '=', request.env.uid)], order='report_datetime desc, id desc')
        values = self._feedback_layout_values(project)
        values.update({
            'page_name': 'helpdesk_feedback',
            'tickets': tickets,
            'state_labels': CUSTOMER_STATE_LABELS,
            'new_url': self._feedback_url('/construction/feedback/new', project),
            'from_project_qs': ('?from_project=%s' % project.id) if project else '',
            'message': kw.get('message'),
        })
        return request.render('construction_helpdesk.portal_feedback_list', values)

    # ------------------------------------------------------------------
    # 新增
    # ------------------------------------------------------------------
    @http.route(['/construction/feedback/new'], type='http', auth='user', website=True)
    def portal_feedback_new(self, from_project=None, **kw):
        project = self._feedback_project(from_project)
        values = self._feedback_layout_values(project)
        values.update({
            'page_name': 'helpdesk_feedback_new',
            'categories': request.env['construction.service.category'].search([]),
            'modules': request.env['construction.functional.module'].search(
                [('show_in_portal', '=', True)]),
            'list_url': self._feedback_url('/construction/feedback', project),
            'error': kw.get('error'),
            'max_files': MAX_FILES,
        })
        return request.render('construction_helpdesk.portal_feedback_new', values)

    @http.route(['/construction/feedback/create'], type='http', auth='user', website=True,
                methods=['POST'])
    def portal_feedback_create(self, **post):
        env = request.env
        project = self._feedback_project(post.get('from_project'))
        back = self._feedback_url('/construction/feedback/new', project)
        sep = '&' if '?' in back else '?'

        category = env['construction.service.category'].browse(
            int(post.get('category_id') or 0)).exists()
        subject = (post.get('subject') or '').strip()
        detail = (post.get('description') or '').strip()
        if not category or not subject or not detail:
            return request.redirect(back + sep + 'error=missing')

        module = env['construction.functional.module']
        if category.ask_functional_module and post.get('functional_module_id'):
            # 只接受前台清單裡的項目（防止改 HTML 送進後台專用項目）
            module = module.search([('id', '=', int(post['functional_module_id'])),
                                    ('show_in_portal', '=', True)], limit=1)

        files = [f for f in request.httprequest.files.getlist('attachments') if f and f.filename]
        if len(files) > MAX_FILES:
            return request.redirect(back + sep + 'error=too_many_files')

        user = env.user
        partner = user.partner_id
        # 客戶公司：本系統沒有公司主檔，前台帳號若掛在某個公司聯絡人底下就帶它的名稱，否則留空讓客服補
        # sudo：前台帳號不一定讀得到自己所屬公司的聯絡人資料，只取名稱
        company_name = (partner.sudo().parent_id.name or partner.sudo().company_name or '').strip()
        vals = {
            'subject': subject[:200],
            'description': plaintext2html(detail),
            'category_id': category.id,
            'functional_module_id': module.id or False,
            'channel': 'portal',
            'report_datetime': fields.Datetime.now(),
            'contact_name': user.name,
            'customer_company': company_name or False,
        }
        if project:
            vals.update({'project_name': project.name, 'project_code': project.code or False})

        # 【分庫】分庫後這裡改為呼叫客服資料庫的建單 API（附件一併上傳），見 docs/分庫架構_集中客服資料庫.md
        # 以本人身分建立（不 sudo）：權限由 ACL＋record rule 把關。
        # mail_create_nosubscribe：客戶不自動成為追蹤者 → 客服回覆時不寄 Email（已決定暫不寄送）。
        # 客戶仍可在前台看到客服的回覆（存取依紀錄讀取權，不依追蹤）。
        try:
            ticket = env[TICKET].with_context(mail_create_nosubscribe=True).create(vals)
            if files:
                ticket.with_context(mail_post_autofollow=False).message_post(
                    body=_('建單時附上的檔案'),
                    attachments=[(f.filename, f.read()) for f in files],
                    message_type='comment', subtype_xmlid='mail.mt_comment')
        except (AccessError, UserError, ValidationError):
            return request.redirect(back + sep + 'error=denied')
        return request.redirect('/construction/feedback/%s?message=created' % ticket.id)

    # ------------------------------------------------------------------
    # 詳情（含對話）
    # ------------------------------------------------------------------
    @http.route(['/construction/feedback/<int:ticket_id>'], type='http', auth='user', website=True)
    def portal_feedback_detail(self, ticket_id, **kw):
        try:
            ticket = request.env[TICKET].browse(ticket_id).exists()
            if not ticket:
                raise MissingError(_('找不到這張服務單'))
            ticket.check_access('read')
        except (AccessError, MissingError):
            return request.redirect('/construction/feedback')
        values = self._feedback_layout_values(False)
        values.update({
            'page_name': 'helpdesk_feedback_detail',
            'ticket': ticket,
            'state_label': CUSTOMER_STATE_LABELS.get(ticket.state, ticket.state),
            'message': kw.get('message'),
            # 前台 chatter（Odoo 原生 portal.message_thread）
            'object': ticket,
            'disable_composer': ticket.state == 'cancel',
            'message_per_page': 20,
        })
        return request.render('construction_helpdesk.portal_feedback_detail', values)
