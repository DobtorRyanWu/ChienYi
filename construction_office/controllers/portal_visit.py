# -*- coding: utf-8 -*-
"""參觀帳號的專用頁面（淞源 C11）：被指定工程的照片、被指定的公文，全部唯讀。

* 每一支路由都先對照「參觀帳號授權」（res.users._visit_grants，過期就是空的），對得上才以 sudo 取資料——
  參觀帳號本身沒有任何業務模型的讀取權，所以這裡的 sudo 一定要緊跟在授權檢查後面。
* 對不上的一律 404（不分「沒有這一筆」和「不給你看」，不洩漏存在性）。頁面類的 404 用參觀自己的版型
  （系統預設的 404 頁是網站版型，上面的連結與插圖參觀帳號都進不去）。
* 不是參觀帳號的人進來 → 導回一般的前台首頁。
* 參觀帳號能打的網址只有這個檔案裡的（models/ir_http.py 的白名單）。
"""
from werkzeug.exceptions import NotFound

from odoo import http
from odoo.http import request

from odoo.addons.portal.controllers.portal import pager as portal_pager

from ..models.ir_http import VISIT_HOME
from ..models.official_doc import DIRECTION_SELECTION
from ..models.visit_grant import DOC_MODEL, PHOTO_MODEL

PHOTOS_PER_PAGE = 24
PHOTO_ORDER = 'shot_at desc, id desc'
THUMB_SIZE = 320                # 照片牆縮圖的邊長（px）
MAX_IMAGE_SIDE = 2560           # 單張照片最大給到多大（px）；不給原檔，避免把 EXIF 以外的大檔整包搬走


class ConstructionVisitPortal(http.Controller):

    # ── 授權 ──────────────────────────────────────────────────────────────
    def _grants(self):
        """目前登入者有效的授權；不是參觀帳號回 None（呼叫端導回一般首頁）。"""
        user = request.env.user
        if not user._is_visit_account():
            return None
        return user._visit_grants()

    def _grant_for(self, project_id, photos=False):
        """某個工程的授權；沒有（或要看照片但沒開照片）→ 404。"""
        grants = self._grants()
        if grants is None:
            raise NotFound()
        grant = grants.filtered(lambda g: g.project_id.id == project_id)
        if not grant or (photos and not grant.allow_photos):
            raise NotFound()
        return grant

    def _granted_doc(self, doc_id):
        """被指定給目前登入者看、而且現在還掛在授權工程上的公文（sudo 的紀錄）；不是 → 404。"""
        grants = self._grants()
        if not grants:
            raise NotFound()
        doc = grants._visit_docs().filtered(lambda d: d.id == doc_id)
        if not doc:
            raise NotFound()
        return doc

    def _page(self, build):
        """頁面類路由共用：build() 回 (模板, 值)；授權對不上（NotFound）就給參觀版型的 404 頁。"""
        try:
            template, values = build()
        except NotFound:
            user = request.env.user
            if not user._is_visit_account():
                raise
            return request.render('construction_office.portal_visit_not_found', self._base_values(self._grants()),
                                  status=404)
        return request.render(template, values)

    def _base_values(self, grants, **extra):
        user = request.env.user
        values = {'visit_user': user, 'valid_until': user.sudo().portal_valid_until, 'grants': grants,
                  'page_name': 'construction_visit'}
        values.update(extra)
        return values

    # ── 首頁 ──────────────────────────────────────────────────────────────
    @http.route([VISIT_HOME], type='http', auth='user', website=True)
    def visit_home(self, **kw):
        grants = self._grants()
        if grants is None:
            return request.redirect('/my')
        Photo = request.env[PHOTO_MODEL].sudo()
        rows = [{
            'grant': grant,
            'project': grant.project_id,
            'photo_count': Photo.search_count(self._photo_domain(grant.project_id)) if grant.allow_photos else 0,
            'doc_count': len(grant._visit_docs()),
        } for grant in grants]
        return request.render('construction_office.portal_visit_home', self._base_values(grants, rows=rows))

    # ── 照片 ──────────────────────────────────────────────────────────────
    def _photo_domain(self, project):
        return [('project_id', '=', project.id), ('attachment_id.mimetype', '=like', 'image/%')]

    @http.route([VISIT_HOME + '/<int:project_id>/photos', VISIT_HOME + '/<int:project_id>/photos/page/<int:page>'],
                type='http', auth='user', website=True)
    def visit_photos(self, project_id, page=1, **kw):
        def build():
            grant = self._grant_for(project_id, photos=True)
            Photo = request.env[PHOTO_MODEL].sudo()
            domain = self._photo_domain(grant.project_id)
            total = Photo.search_count(domain)
            url = '%s/%s/photos' % (VISIT_HOME, project_id)
            pager = portal_pager(url=url, total=total, page=page, step=PHOTOS_PER_PAGE)
            photos = Photo.search(domain, order=PHOTO_ORDER, limit=PHOTOS_PER_PAGE, offset=pager['offset'])
            return 'construction_office.portal_visit_photos', self._base_values(
                self._grants(), project=grant.project_id, photos=photos, photo_count=total, pager=pager,
                thumb_size=THUMB_SIZE)
        return self._page(build)

    @http.route([VISIT_HOME + '/photo/<int:photo_id>',
                 VISIT_HOME + '/photo/<int:photo_id>/<int:width>x<int:height>'], type='http', auth='user')
    def visit_photo_image(self, photo_id, width=0, height=0, **kw):
        photo = request.env[PHOTO_MODEL].sudo().browse(photo_id).exists()
        # 已封存的照片不給（browse 不看 active；照片牆用 search 本來就不列，兩邊要一致——
        # 2026-11-13 權限審查的重現案例：封存後用編號直接打圖片端點仍拿得到）
        if not photo or not photo.active or not photo.project_id:
            raise NotFound()
        self._grant_for(photo.project_id.id, photos=True)
        attachment = photo.attachment_id
        if not attachment or not (attachment.mimetype or '').startswith('image/'):
            raise NotFound()
        side = max(min(int(width or 0), MAX_IMAGE_SIDE), 0) or MAX_IMAGE_SIDE
        tall = max(min(int(height or 0), MAX_IMAGE_SIDE), 0) or MAX_IMAGE_SIDE
        return request.env['ir.binary'].sudo()._get_image_stream_from(
            attachment, 'raw', width=side, height=tall).get_response()

    # ── 公文 ──────────────────────────────────────────────────────────────
    @http.route([VISIT_HOME + '/<int:project_id>/docs'], type='http', auth='user', website=True)
    def visit_docs(self, project_id, **kw):
        def build():
            grant = self._grant_for(project_id)
            docs = grant._visit_docs().sorted(
                lambda d: (d.doc_date or d.create_date.date(), d.id), reverse=True)
            return 'construction_office.portal_visit_docs', self._base_values(
                self._grants(), project=grant.project_id, docs=docs, direction_labels=dict(DIRECTION_SELECTION))
        return self._page(build)

    @http.route([VISIT_HOME + '/doc/<int:doc_id>'], type='http', auth='user', website=True)
    def visit_doc(self, doc_id, **kw):
        def build():
            doc = self._granted_doc(doc_id)
            return 'construction_office.portal_visit_doc', self._base_values(
                self._grants(), project=doc.project_id, doc=doc, attachments=doc.attachment_ids,
                direction_labels=dict(DIRECTION_SELECTION))
        return self._page(build)

    @http.route([VISIT_HOME + '/doc/<int:doc_id>/file/<int:att_id>'], type='http', auth='user')
    def visit_doc_file(self, doc_id, att_id, **kw):
        doc = self._granted_doc(doc_id)
        attachment = request.env['ir.attachment'].sudo().search([
            ('id', '=', att_id), ('res_model', '=', DOC_MODEL), ('res_id', '=', doc.id)], limit=1)
        if not attachment:
            raise NotFound()
        return request.env['ir.binary'].sudo()._get_stream_from(attachment, 'raw').get_response(as_attachment=True)
