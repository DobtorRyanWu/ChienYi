# -*- coding: utf-8 -*-
"""手機公文頁（淞源 C10）：依工程的列表＋搜尋、跨工程總表、詳情、附件下載、新增、標為已辦。

* 讀取一律以登入者自己的權限查（不 sudo）：看不看得到由 ACL 與 security/office_rules.xml 決定，
  受限帳號再由 construction_company_dashboard 的 rule_scope 收窄。這支 controller 不自己判斷「誰看得到」。
* 寫入（新增、標為已辦）走 sudo＋守衛：前台帳號沒有寫入 ACL（2026-11-04 起前台 ORM 寫入權全部收回）。
  守衛＝工程看得到（_document_check_access）＋不是閱覽角色（_require_write）＋那筆公文本人讀得到。
* 附件下載：先以本人身分找到公文，再確認附件真的掛在那筆公文上，才用 sudo 串流；其餘一律 404。
* 獨立類別（不繼承 ConstructionPortal）：同名方法會污染整個前台；要用它的守衛時呼叫 PORTAL 這個實例。
"""
import base64
import logging

from werkzeug.exceptions import NotFound

from odoo import _, fields, http
from odoo.exceptions import AccessError, MissingError, UserError, ValidationError
from odoo.http import request

from odoo.addons.construction_portal.controllers.portal import ConstructionPortal
from odoo.addons.portal.controllers.portal import pager as portal_pager

from ..models.official_doc import DIRECTION_INCOMING, DIRECTION_SELECTION, STATE_PENDING, STATE_SELECTION

_logger = logging.getLogger(__name__)

PORTAL = ConstructionPortal()
DOC_MODEL = 'construction.official.doc'
DOCS_PER_PAGE = 20
MAX_UPLOAD_FILES = 10               # 一次新增最多附幾個檔
SEARCH_PARAMS = ('q', 'date_from', 'date_to', 'direction', 'state')
# 新增表單可填的文字欄位（其餘欄位一律不收：所屬公司、狀態等由伺服器決定）
CREATE_TEXT_FIELDS = ('subject', 'organization', 'doc_number', 'summary')
CREATE_DATE_FIELDS = ('doc_date', 'receive_date', 'reply_deadline')
# 網址上的訊息代碼 → 固定文字（網址參數原文不印）
MESSAGES = {
    'created': ('ok', '公文已新增'),
    'done': ('ok', '已標為已辦'),
    'no_subject': ('bad', '請填主旨'),
    'bad_date': ('bad', '日期格式不正確'),
    'too_many_files': ('bad', '一次最多附 %s 個檔' % MAX_UPLOAD_FILES),
    'invalid': ('bad', '資料不正確，沒有存檔'),
    'forbidden': ('bad', '權限不足'),
}


def _clean_date(value):
    """'YYYY-MM-DD' → date；空白回 False；格式不對丟 ValueError。"""
    value = (value or '').strip()
    return fields.Date.to_date(value) if value else False


class ConstructionOfficialDocPortal(http.Controller):

    # ── 共用 ──────────────────────────────────────────────────────────────
    def _project(self, project_id):
        """看得到的工程；看不到回 None（呼叫端導回首頁）。"""
        try:
            return PORTAL._document_check_access('project.project', project_id)
        except (AccessError, MissingError):
            return None

    def _search_values(self, params):
        """網址上的搜尋條件 → (條件 dict, domain)。日期格式不對的當成沒填。"""
        values = {name: (params.get(name) or '').strip() for name in SEARCH_PARAMS}
        dates = {}
        for name in ('date_from', 'date_to'):
            try:
                dates[name] = _clean_date(values[name])
            except ValueError:
                dates[name], values[name] = False, ''
        domain = request.env[DOC_MODEL]._search_domain(
            keyword=values['q'], date_from=dates['date_from'], date_to=dates['date_to'],
            direction=values['direction'], state=values['state'])
        return values, domain

    def _list_values(self, base_domain, base_url, page, params):
        """列表頁共用：以本人身分搜尋＋分頁。沒有讀取權 → no_access（頁面顯示原因，不是 500）。"""
        search, domain = self._search_values(params)
        Doc = request.env[DOC_MODEL]
        url_args = {name: value for name, value in search.items() if value}
        try:
            total = Doc.search_count(base_domain + domain)
            pager = portal_pager(url=base_url, total=total, page=page, step=DOCS_PER_PAGE, url_args=url_args)
            docs = Doc.search(base_domain + domain, limit=DOCS_PER_PAGE, offset=pager['offset'])
            no_access = False
        except AccessError:
            total, docs, no_access = 0, Doc.browse(), True
            pager = portal_pager(url=base_url, total=0, page=1, step=DOCS_PER_PAGE, url_args=url_args)
        tone, text = MESSAGES.get(params.get('message') or params.get('error') or '', (False, False))
        return {
            'docs': docs,
            'doc_count': total,
            'no_access': no_access,
            'search': search,
            'has_search': bool(url_args),
            'pager': pager,
            'default_url': base_url,
            'directions': DIRECTION_SELECTION,
            'states': STATE_SELECTION,
            'direction_labels': dict(DIRECTION_SELECTION),
            'state_labels': dict(STATE_SELECTION),
            'flash_tone': tone,
            'flash_text': text,
            'can_write': request.env.user._portal_can_write(),
        }

    def _readable_doc(self, doc_id, project=None):
        """以本人身分找公文（規則擋掉或沒有讀取權都回空）；給了工程就要屬於那個工程。"""
        domain = [('id', '=', doc_id)]
        if project:
            domain.append(('project_id', '=', project.id))
        try:
            return request.env[DOC_MODEL].search(domain, limit=1)
        except AccessError:
            return request.env[DOC_MODEL].browse()

    # ── 列表＋搜尋 ────────────────────────────────────────────────────────
    @http.route(['/construction/<int:project_id>/official-docs',
                 '/construction/<int:project_id>/official-docs/page/<int:page>'],
                type='http', auth='user', website=True)
    def official_docs(self, project_id, page=1, **kw):
        """單一工程的公文列表與搜尋。"""
        project = self._project(project_id)
        if not project:
            return request.redirect('/my')
        base_url = f'/construction/{project.id}/official-docs'
        values = self._list_values([('project_id', '=', project.id)], base_url, page, kw)
        values.update({
            'project': project,
            'page_name': 'construction_official_docs',
            'day_count': PORTAL._get_project_day_count(project),
            'nav_badges': PORTAL._get_nav_badges(project),
        })
        return request.render('construction_office.portal_official_docs', values)

    @http.route(['/construction/official-docs', '/construction/official-docs/page/<int:page>'],
                type='http', auth='user', website=True)
    def official_docs_all(self, page=1, **kw):
        """跨工程總表：本人看得到的全部公文（含沒掛工程的，如果規則讓他看得到）。"""
        values = self._list_values([], '/construction/official-docs', page, kw)
        values.update({'project': False, 'page_name': 'construction_official_docs_all'})
        return request.render('construction_office.portal_official_docs_all', values)

    # ── 詳情、附件 ────────────────────────────────────────────────────────
    def _doc_url(self, doc, project):
        """詳情頁網址：掛工程的走工程底下；沒掛工程的（公司共通）走不帶工程的網址。"""
        if project:
            return f'/construction/{project.id}/official-doc/{doc.id}'
        return f'/construction/official-doc/{doc.id}'

    def _doc_context(self, project_id, doc_id):
        """(工程或 False, 公文或空, 找不到時要導去的網址)。
        帶工程的網址：工程要看得到、公文要屬於那個工程；不帶工程的網址：只給沒掛工程的公文
        （掛了工程的導去工程底下的網址，讓工程的可見性檢查照常跑）。"""
        if project_id:
            project = self._project(project_id)
            if not project:
                return False, request.env[DOC_MODEL].browse(), '/my'
            return project, self._readable_doc(doc_id, project), f'/construction/{project.id}/official-docs'
        doc = self._readable_doc(doc_id)
        if doc and doc.project_id:
            return False, request.env[DOC_MODEL].browse(), f'/construction/{doc.project_id.id}/official-doc/{doc.id}'
        return False, doc, '/construction/official-docs'

    @http.route(['/construction/<int:project_id>/official-doc/<int:doc_id>',
                 '/construction/official-doc/<int:doc_id>'],
                type='http', auth='user', website=True)
    def official_doc_detail(self, doc_id, project_id=None, **kw):
        project, doc, fallback = self._doc_context(project_id, doc_id)
        if not doc:
            return request.redirect(fallback)
        tone, text = MESSAGES.get(kw.get('message') or kw.get('error') or '', (False, False))
        values = {
            'project': project,
            'doc': doc,
            'doc_url': self._doc_url(doc, project),
            # sudo 只讀附件的檔名與大小：doc 已由上面以本人身分確認讀得到，附件限定掛在這筆公文上
            'attachments': doc.sudo().attachment_ids,
            'direction_labels': dict(DIRECTION_SELECTION),
            'state_labels': dict(STATE_SELECTION),
            'can_mark_done': request.env.user._portal_can_write() and doc.state == STATE_PENDING,
            'flash_tone': tone,
            'flash_text': text,
            'page_name': 'construction_official_doc_detail',
        }
        if project:
            values.update(day_count=PORTAL._get_project_day_count(project), nav_badges=PORTAL._get_nav_badges(project))
        return request.render('construction_office.portal_official_doc_detail', values)

    def _downloadable_attachment(self, doc_id, att_id):
        """可以下載的附件：公文本人讀得到，而且附件確實掛在那筆公文上；其餘一律 NotFound（不洩漏存在性）。
        回傳的是 sudo 的附件紀錄（前台帳號本身沒有 ir.attachment 讀取權）。"""
        doc = self._readable_doc(doc_id)
        if not doc:
            raise NotFound()
        attachment = request.env['ir.attachment'].sudo().search([
            ('id', '=', att_id), ('res_model', '=', DOC_MODEL), ('res_id', '=', doc.id)], limit=1)
        if not attachment:
            raise NotFound()
        return attachment

    @http.route(['/construction/official-doc/<int:doc_id>/file/<int:att_id>'], type='http', auth='user')
    def official_doc_file(self, doc_id, att_id, **kw):
        """下載公文附件（把關在 _downloadable_attachment）。"""
        attachment = self._downloadable_attachment(doc_id, att_id)
        return request.env['ir.binary'].sudo()._get_stream_from(attachment, 'raw').get_response(as_attachment=True)

    # ── 新增 ──────────────────────────────────────────────────────────────
    @http.route(['/construction/<int:project_id>/official-doc/new'], type='http', auth='user', website=True)
    def official_doc_new(self, project_id, **kw):
        project = self._project(project_id)
        if not project:
            return request.redirect('/my')
        if not request.env.user._portal_can_write():
            return request.redirect(f'/construction/{project.id}/official-docs?error=forbidden')
        tone, text = MESSAGES.get(kw.get('error') or '', (False, False))
        values = {
            'project': project,
            'directions': DIRECTION_SELECTION,
            'default_direction': DIRECTION_INCOMING,
            'today': fields.Date.to_string(fields.Date.context_today(request.env.user)),
            'max_files': MAX_UPLOAD_FILES,
            'flash_tone': tone,
            'flash_text': text,
            'page_name': 'construction_official_doc_new',
            'day_count': PORTAL._get_project_day_count(project),
            'nav_badges': PORTAL._get_nav_badges(project),
        }
        return request.render('construction_office.portal_official_doc_form', values)

    @http.route(['/construction/<int:project_id>/official-doc/create'],
                type='http', auth='user', website=True, methods=['POST'], csrf=True)
    def official_doc_create(self, project_id, **post):
        project = self._project(project_id)
        if not project:
            return request.redirect('/my')
        PORTAL._require_write(_('權限不足：閱覽角色不可新增公文'))
        back = f'/construction/{project.id}/official-doc/new'
        subject = (post.get('subject') or '').strip()
        if not subject:
            return request.redirect(back + '?error=no_subject')
        vals = {'project_id': project.id, 'subject': subject}
        for name in CREATE_TEXT_FIELDS[1:]:
            vals[name] = (post.get(name) or '').strip() or False
        try:
            for name in CREATE_DATE_FIELDS:
                vals[name] = _clean_date(post.get(name))
        except ValueError:
            return request.redirect(back + '?error=bad_date')
        if not vals['doc_date']:
            vals.pop('doc_date')            # 沒填就用模型預設（今天）
        if post.get('direction') in dict(DIRECTION_SELECTION):
            vals['direction'] = post['direction']
        files = [f for f in request.httprequest.files.getlist('files') if f and f.filename]
        if len(files) > MAX_UPLOAD_FILES:
            return request.redirect(back + '?error=too_many_files')
        # sudo 建立：前台帳號沒有寫入 ACL。所屬公司不收表單值——營造方由模型強制成自己的範圍公司，
        # 其他帳號用自己的公司（模型預設）；工程已由上面確認本人看得到
        try:
            with request.env.cr.savepoint():
                doc = request.env[DOC_MODEL].sudo().create(vals)
                for upload in files:
                    request.env['ir.attachment'].sudo().create({
                        'name': upload.filename,
                        'datas': base64.b64encode(upload.read()),
                        'type': 'binary',
                        'public': False,
                        'res_model': DOC_MODEL,
                        'res_id': doc.id,
                    })
        except (UserError, ValidationError, AccessError) as exc:
            _logger.info('前台新增公文失敗（工程 %s，使用者 %s）：%s', project.id, request.env.uid, exc)
            return request.redirect(back + '?error=invalid')
        return request.redirect(f'/construction/{project.id}/official-doc/{doc.id}?message=created')

    @http.route(['/construction/<int:project_id>/official-doc/<int:doc_id>/done',
                 '/construction/official-doc/<int:doc_id>/done'],
                type='http', auth='user', website=True, methods=['POST'], csrf=True)
    def official_doc_done(self, doc_id, project_id=None, **post):
        project, doc, fallback = self._doc_context(project_id, doc_id)
        if not doc:
            return request.redirect(fallback)
        PORTAL._require_write(_('權限不足：閱覽角色不可修改公文'))
        if doc.state == STATE_PENDING:
            doc.sudo().action_mark_done()       # doc 已由 _doc_context 以本人身分確認讀得到（有工程時也屬於那個工程）
        return request.redirect(self._doc_url(doc, project) + '?message=done')
