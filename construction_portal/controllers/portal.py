# -*- coding: utf-8 -*-

from odoo import http, _
from odoo.http import request
from odoo.addons.portal.controllers.portal import CustomerPortal, pager as portal_pager
from odoo.exceptions import AccessError, MissingError
from odoo.osv.expression import AND


class ConstructionPortal(CustomerPortal):
    """
    工程監造系統 Portal Controller

    提供承包廠商 Portal 用戶存取:
    - 工程案件列表與詳情
    - 自主檢查填寫與查詢
    - 缺失改善提交
    - 照片上傳
    """

    def _prepare_home_portal_values(self, counters):
        """Portal 首頁計數器"""
        values = super()._prepare_home_portal_values(counters)
        partner = request.env.user.partner_id

        if 'construction_count' in counters:
            domain = request.env['supervision.project']._get_portal_projects_domain(partner)
            values['construction_count'] = request.env['supervision.project'].search_count(domain)

        return values

    def _get_construction_projects_domain(self, partner):
        """取得 Portal 用戶可存取的工程案件 domain"""
        return request.env['supervision.project']._get_portal_projects_domain(partner)

    # ==================== 工程案件 ====================

    @http.route(['/my/construction', '/my/construction/page/<int:page>'],
                type='http', auth='user', website=True)
    def portal_my_construction_projects(self, page=1, sortby=None, **kw):
        """工程案件列表"""
        partner = request.env.user.partner_id
        Project = request.env['supervision.project']

        domain = self._get_construction_projects_domain(partner)

        # 排序選項
        searchbar_sortings = {
            'date': {'label': _('最新'), 'order': 'create_date desc'},
            'name': {'label': _('名稱'), 'order': 'name'},
            'state': {'label': _('狀態'), 'order': 'state'},
        }
        if not sortby:
            sortby = 'date'
        order = searchbar_sortings[sortby]['order']

        # 計數與分頁
        project_count = Project.search_count(domain)
        pager = portal_pager(
            url='/my/construction',
            total=project_count,
            page=page,
            step=self._items_per_page,
            url_args={'sortby': sortby},
        )

        projects = Project.search(
            domain,
            order=order,
            limit=self._items_per_page,
            offset=pager['offset']
        )

        values = {
            'projects': projects,
            'page_name': 'construction',
            'pager': pager,
            'default_url': '/my/construction',
            'searchbar_sortings': searchbar_sortings,
            'sortby': sortby,
        }

        return request.render('construction_portal.portal_my_construction_projects', values)

    @http.route(['/my/construction/<int:project_id>'],
                type='http', auth='user', website=True)
    def portal_construction_project_detail(self, project_id, **kw):
        """工程案件詳情"""
        partner = request.env.user.partner_id

        try:
            project = self._document_check_access(
                'supervision.project', project_id,
                access_token=kw.get('access_token')
            )
        except (AccessError, MissingError):
            return request.redirect('/my')

        # 取得相關資料
        inspections = request.env['general.self.inspection'].search([
            ('project_id', '=', project.id)
        ], limit=10, order='create_date desc')

        defects = request.env['supervision.defect'].search([
            ('project_id', '=', project.id)
        ], limit=10, order='create_date desc')

        photos = request.env['supervision.photo'].search([
            ('project_id', '=', project.id)
        ], limit=12, order='create_date desc')

        values = {
            'project': project,
            'inspections': inspections,
            'defects': defects,
            'photos': photos,
            'page_name': 'construction_detail',
        }

        return request.render('construction_portal.portal_construction_project_detail', values)

    # ==================== 自主檢查 ====================

    @http.route(['/my/construction/<int:project_id>/inspections',
                 '/my/construction/<int:project_id>/inspections/page/<int:page>'],
                type='http', auth='user', website=True)
    def portal_construction_inspections(self, project_id, page=1, **kw):
        """自主檢查列表"""
        partner = request.env.user.partner_id

        try:
            project = self._document_check_access('supervision.project', project_id)
        except (AccessError, MissingError):
            return request.redirect('/my')

        Inspection = request.env['general.self.inspection']
        domain = [('project_id', '=', project.id)]

        inspection_count = Inspection.search_count(domain)
        pager = portal_pager(
            url=f'/my/construction/{project_id}/inspections',
            total=inspection_count,
            page=page,
            step=self._items_per_page,
        )

        inspections = Inspection.search(
            domain,
            order='create_date desc',
            limit=self._items_per_page,
            offset=pager['offset']
        )

        values = {
            'project': project,
            'inspections': inspections,
            'page_name': 'construction_inspections',
            'pager': pager,
            'default_url': f'/my/construction/{project_id}/inspections',
        }

        return request.render('construction_portal.portal_construction_inspections', values)

    @http.route(['/my/construction/<int:project_id>/inspection/new'],
                type='http', auth='user', website=True)
    def portal_construction_inspection_new(self, project_id, **kw):
        """新增自主檢查表單"""
        partner = request.env.user.partner_id

        try:
            project = self._document_check_access('supervision.project', project_id)
        except (AccessError, MissingError):
            return request.redirect('/my')

        # 取得可用的檢查類型
        inspection_types = request.env['self.inspection.type'].sudo().search([])

        values = {
            'project': project,
            'inspection_types': inspection_types,
            'page_name': 'construction_inspection_new',
        }

        return request.render('construction_portal.portal_construction_inspection_form', values)

    @http.route(['/my/construction/inspection/create'],
                type='http', auth='user', website=True, methods=['POST'])
    def portal_construction_inspection_create(self, **post):
        """建立自主檢查"""
        partner = request.env.user.partner_id
        project_id = int(post.get('project_id', 0))

        try:
            project = self._document_check_access('supervision.project', project_id)
        except (AccessError, MissingError):
            return request.redirect('/my')

        vals = {
            'project_id': project_id,
            'inspection_type_id': int(post.get('inspection_type_id', 0)) or False,
            'inspection_date': post.get('inspection_date'),
            'inspection_location': post.get('location', ''),
            'note': post.get('note', ''),
        }

        Inspection = request.env['general.self.inspection']
        inspection = Inspection.create_from_portal(vals, partner)

        return request.redirect(f'/my/construction/inspection/{inspection.id}')

    @http.route(['/my/construction/inspection/<int:inspection_id>'],
                type='http', auth='user', website=True)
    def portal_construction_inspection_detail(self, inspection_id, **kw):
        """自主檢查詳情"""
        try:
            inspection = self._document_check_access(
                'general.self.inspection', inspection_id,
                access_token=kw.get('access_token')
            )
        except (AccessError, MissingError):
            return request.redirect('/my')

        values = {
            'inspection': inspection,
            'project': inspection.project_id,
            'page_name': 'construction_inspection_detail',
        }

        return request.render('construction_portal.portal_construction_inspection_detail', values)

    # ==================== 缺失管理 ====================

    @http.route(['/my/construction/<int:project_id>/defects',
                 '/my/construction/<int:project_id>/defects/page/<int:page>'],
                type='http', auth='user', website=True)
    def portal_construction_defects(self, project_id, page=1, filterby=None, **kw):
        """缺失列表"""
        try:
            project = self._document_check_access('supervision.project', project_id)
        except (AccessError, MissingError):
            return request.redirect('/my')

        Defect = request.env['supervision.defect']
        domain = [('project_id', '=', project.id)]

        # 篩選選項
        searchbar_filters = {
            'all': {'label': _('全部'), 'domain': []},
            'open': {'label': _('待處理'), 'domain': [('state', 'not in', ['verified', 'closed'])]},
            'closed': {'label': _('已結案'), 'domain': [('state', 'in', ['verified', 'closed'])]},
        }
        if not filterby:
            filterby = 'all'
        domain = AND([domain, searchbar_filters[filterby]['domain']])

        defect_count = Defect.search_count(domain)
        pager = portal_pager(
            url=f'/my/construction/{project_id}/defects',
            total=defect_count,
            page=page,
            step=self._items_per_page,
            url_args={'filterby': filterby},
        )

        defects = Defect.search(
            domain,
            order='create_date desc',
            limit=self._items_per_page,
            offset=pager['offset']
        )

        values = {
            'project': project,
            'defects': defects,
            'page_name': 'construction_defects',
            'pager': pager,
            'default_url': f'/my/construction/{project_id}/defects',
            'searchbar_filters': searchbar_filters,
            'filterby': filterby,
        }

        return request.render('construction_portal.portal_construction_defects', values)

    @http.route(['/my/construction/defect/<int:defect_id>'],
                type='http', auth='user', website=True)
    def portal_construction_defect_detail(self, defect_id, **kw):
        """缺失詳情"""
        try:
            defect = self._document_check_access(
                'supervision.defect', defect_id,
                access_token=kw.get('access_token')
            )
        except (AccessError, MissingError):
            return request.redirect('/my')

        values = {
            'defect': defect,
            'project': defect.project_id,
            'page_name': 'construction_defect_detail',
        }

        return request.render('construction_portal.portal_construction_defect_detail', values)

    @http.route(['/my/construction/defect/<int:defect_id>/improve'],
                type='http', auth='user', website=True, methods=['POST'])
    def portal_construction_defect_improve(self, defect_id, **post):
        """提交缺失改善"""
        partner = request.env.user.partner_id

        try:
            defect = self._document_check_access('supervision.defect', defect_id)
        except (AccessError, MissingError):
            return request.redirect('/my')

        improvement_text = post.get('improvement_description', '')
        defect.portal_submit_improvement(improvement_text, partner)

        return request.redirect(f'/my/construction/defect/{defect_id}?message=success')

    # ==================== 照片管理 ====================

    @http.route(['/my/construction/<int:project_id>/photos',
                 '/my/construction/<int:project_id>/photos/page/<int:page>'],
                type='http', auth='user', website=True)
    def portal_construction_photos(self, project_id, page=1, **kw):
        """照片列表"""
        try:
            project = self._document_check_access('supervision.project', project_id)
        except (AccessError, MissingError):
            return request.redirect('/my')

        Photo = request.env['supervision.photo']
        domain = [('project_id', '=', project.id)]

        photo_count = Photo.search_count(domain)
        pager = portal_pager(
            url=f'/my/construction/{project_id}/photos',
            total=photo_count,
            page=page,
            step=24,  # 照片用較多的 items per page
        )

        photos = Photo.search(
            domain,
            order='create_date desc',
            limit=24,
            offset=pager['offset']
        )

        values = {
            'project': project,
            'photos': photos,
            'page_name': 'construction_photos',
            'pager': pager,
            'default_url': f'/my/construction/{project_id}/photos',
        }

        return request.render('construction_portal.portal_construction_photos', values)

    @http.route(['/my/construction/<int:project_id>/photo/upload'],
                type='http', auth='user', website=True)
    def portal_construction_photo_upload_form(self, project_id, **kw):
        """照片上傳表單"""
        try:
            project = self._document_check_access('supervision.project', project_id)
        except (AccessError, MissingError):
            return request.redirect('/my')

        values = {
            'project': project,
            'page_name': 'construction_photo_upload',
        }

        return request.render('construction_portal.portal_construction_photo_upload', values)

    @http.route(['/my/construction/photo/upload'],
                type='http', auth='user', website=True, methods=['POST'], csrf=True)
    def portal_construction_photo_upload(self, **post):
        """處理照片上傳"""
        partner = request.env.user.partner_id
        project_id = int(post.get('project_id', 0))

        try:
            project = self._document_check_access('supervision.project', project_id)
        except (AccessError, MissingError):
            return request.redirect('/my')

        # 處理上傳的檔案
        uploaded_file = post.get('photo')
        if uploaded_file:
            import base64
            file_data = base64.b64encode(uploaded_file.read())

            vals = {
                'project_id': project_id,
                'filename': uploaded_file.filename,
                'description': post.get('description', ''),
                'photo_date': post.get('photo_date'),
            }

            Photo = request.env['supervision.photo']
            photo = Photo.create_from_portal(vals, partner, file_data)

            return request.redirect(f'/my/construction/{project_id}/photos?message=uploaded')

        return request.redirect(f'/my/construction/{project_id}/photo/upload?error=no_file')

    @http.route(['/my/construction/photo/<int:photo_id>'],
                type='http', auth='user', website=True)
    def portal_construction_photo_detail(self, photo_id, **kw):
        """照片詳情"""
        try:
            photo = self._document_check_access(
                'supervision.photo', photo_id,
                access_token=kw.get('access_token')
            )
        except (AccessError, MissingError):
            return request.redirect('/my')

        values = {
            'photo': photo,
            'project': photo.project_id,
            'page_name': 'construction_photo_detail',
        }

        return request.render('construction_portal.portal_construction_photo_detail', values)
