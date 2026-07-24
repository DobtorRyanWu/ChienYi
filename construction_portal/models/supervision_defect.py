# -*- coding: utf-8 -*-

from odoo import models, fields, api

# C2：general.defect.improvement 風味的欄位/狀態值，用於讓前台共用缺失模板
# 直接讀 supervision.defect（157 筆真資料）而零欄位改名、不影響預約式。
# defect_category(general) ↔ defect_type(supervision) 值對映（有損但可用）
_CATEGORY_TO_TYPE = {
    'material': 'quality', 'workmanship': 'quality', 'dimension': 'quality',
    'safety': 'safety', 'environment': 'environmental',
    'document': 'documentation', 'other': 'quality',
}
_TYPE_TO_CATEGORY = {
    'quality': 'workmanship', 'safety': 'safety', 'environmental': 'environment',
    'schedule': 'other', 'documentation': 'document',
}
# source_type(general) ↔ source(supervision)
_SRC_TO_SUP = {
    'self_inspection': 'self_inspection', 'daily_check': 'daily_check',
    'supervision': 'inspection', 'authority_audit': 'authority_audit', 'other': 'other',
}
_SUP_TO_SRC = {
    'inspection': 'supervision', 'daily_check': 'daily_check',
    'self_inspection': 'self_inspection', 'preliminary_acceptance': 'other',
    'final_acceptance': 'other', 'authority_audit': 'authority_audit', 'other': 'other',
}
# supervision 狀態 → general 前台流程詞彙（模板 workflow gating 用 portal_workflow_state）
_STATE_TO_PORTAL = {
    'open': 'notified', 'investigating': 'improving', 'action_taken': 'improved',
    'verified': 'verified', 'closed': 'closed',
}


class SupervisionDefectPortal(models.Model):
    """
    缺失管理 Portal 擴展

    設計說明：
    - 繼承 portal.mixin 提供 Portal 存取功能
    - Portal 用戶可查看並填寫改善說明
    - C2 相容層：加上 general schema 風味的別名欄位/狀態，讓前台共用缺失模板改讀
      supervision.defect 時零欄位改名、且不影響預約式（見檔頭對映常數）
    """
    _inherit = ['supervision.defect', 'portal.mixin']
    _name = 'supervision.defect'

    def _compute_access_url(self):
        super()._compute_access_url()
        for defect in self:
            defect.access_url = f'/construction/defect/{defect.id}'

    # ==================== C2 前台相容層 ====================
    # 直接改名的欄位：可寫 related（讀寫都橋接到 supervision 真欄位）
    defect_description = fields.Text(related='description', readonly=False,
                                     string='缺失說明(前台相容)')
    defect_location = fields.Char(related='location', readonly=False,
                                  string='位置(前台相容)')
    defect_cause = fields.Text(related='root_cause', readonly=False,
                               string='缺失原因(前台相容)')
    improvement_result = fields.Text(related='improvement_description', readonly=False,
                                     string='改善成果(前台相容)')
    improvement_action = fields.Text(related='corrective_action', readonly=False,
                                     string='矯正措施(前台相容)')
    prevention_action = fields.Text(related='preventive_action', readonly=False,
                                    string='預防措施(前台相容)')
    # supervision 無 check_type：dummy（compute 回空、inverse 吸收 create 傳入值不寫）
    check_type = fields.Char(string='檢查類型(前台相容,無)',
                             compute='_compute_portal_check_type',
                             inverse='_inverse_portal_noop', store=False)
    # Selection 值集不同 → computed + inverse 做值對映
    defect_category = fields.Selection(
        [('material', '材料'), ('workmanship', '工藝'), ('dimension', '尺寸'),
         ('safety', '安全'), ('environment', '環境'), ('document', '文件'),
         ('other', '其他')],
        string='缺失類別(前台相容)', store=False,
        compute='_compute_defect_category', inverse='_inverse_defect_category')
    source_type = fields.Selection(
        [('self_inspection', '自主檢查'), ('daily_check', '每日巡檢'),
         ('supervision', '監造抽查'), ('authority_audit', '主管機關稽核'),
         ('other', '其他')],
        string='來源(前台相容)', store=False,
        compute='_compute_source_type', inverse='_inverse_source_type')
    # 前台流程狀態詞彙（模板 workflow 按鈕/改善表單 gating 用此，避免直接比 supervision state）
    portal_workflow_state = fields.Char(
        string='前台流程狀態', compute='_compute_portal_workflow_state', store=False)

    def _compute_portal_check_type(self):
        for r in self:
            r.check_type = False

    def _inverse_portal_noop(self):
        pass  # 吸收 create 傳入的 check_type，不寫入任何真欄位

    @api.depends('defect_type')
    def _compute_defect_category(self):
        for r in self:
            r.defect_category = _TYPE_TO_CATEGORY.get(r.defect_type, 'other')

    def _inverse_defect_category(self):
        for r in self:
            if r.defect_category:
                r.defect_type = _CATEGORY_TO_TYPE.get(r.defect_category, 'quality')

    @api.depends('source')
    def _compute_source_type(self):
        for r in self:
            r.source_type = _SUP_TO_SRC.get(r.source, 'other')

    def _inverse_source_type(self):
        for r in self:
            if r.source_type:
                r.source = _SRC_TO_SUP.get(r.source_type, 'other')

    @api.depends('state')
    def _compute_portal_workflow_state(self):
        for r in self:
            r.portal_workflow_state = _STATE_TO_PORTAL.get(r.state, r.state)

    @api.model_create_multi
    def create(self, vals_list):
        # C2：把前台傳入的 general 欄位名/值 remap 成 supervision 真欄位。
        # writeable related 於 create 時太晚寫（NOT NULL 的 description 在 INSERT 當下仍為空
        # → 違反約束），故在 super().create 前先搬移。
        _ALIAS = {
            'defect_description': 'description', 'defect_location': 'location',
            'defect_cause': 'root_cause', 'improvement_result': 'improvement_description',
            'improvement_action': 'corrective_action', 'prevention_action': 'preventive_action',
        }
        for vals in vals_list:
            for src, dst in _ALIAS.items():
                if src in vals:
                    vals.setdefault(dst, vals.pop(src))
            if 'defect_category' in vals:
                vals.setdefault('defect_type',
                                _CATEGORY_TO_TYPE.get(vals.pop('defect_category'), 'quality'))
            if 'source_type' in vals:
                vals.setdefault('source',
                                _SRC_TO_SUP.get(vals.pop('source_type'), 'other'))
            vals.pop('check_type', None)  # supervision 無此概念
        return super().create(vals_list)

    # 方法別名：讓前台共用路由（為 general 寫）在 supervision 也可呼叫
    def action_verify_pass(self):
        return self.action_verify()

    def action_notify(self):
        # supervision 無「通知」概念，映射為「開始調查」(open→investigating)
        return self.action_start_investigation()

    # === Portal 專用欄位 ===
    portal_improver_id = fields.Many2one(
        'res.partner',
        string='Portal 改善人',
        help='由 Portal 用戶填寫改善說明時記錄')

    portal_improvement_note = fields.Text(
        string='Portal 改善說明',
        help='Portal 用戶填寫的改善說明')

    portal_updated_date = fields.Datetime(
        string='Portal 更新時間',
        help='Portal 用戶最後更新時間')

    @api.model
    def _get_portal_defects_domain(self, partner, project_ids=None):
        """
        取得 Portal 用戶可存取的缺失 domain
        """
        domain = []
        if project_ids:
            domain.append(('project_id', 'in', project_ids))
        return domain

    def portal_submit_improvement(self, improvement_text, partner,
                                   after_photos=None,
                                   corrective_action=None,
                                   preventive_action=None):
        """
        Portal 用戶提交改善說明

        Args:
            improvement_text: 改善說明文字
            partner: Portal 用戶的 partner
            after_photos: 改善後照片附件 IDs
            corrective_action: 矯正措施
            preventive_action: 預防措施
        """
        self.ensure_one()

        vals = {
            'portal_improver_id': partner.id,
            'portal_improvement_note': improvement_text,
            'portal_updated_date': fields.Datetime.now(),
            'improvement_description': improvement_text,
        }

        if corrective_action:
            vals['corrective_action'] = corrective_action
        if preventive_action:
            vals['preventive_action'] = preventive_action
        if after_photos:
            vals['after_photo_ids'] = [(4, pid) for pid in after_photos]

        self.sudo().write(vals)

        # C2：提交改善即推進狀態 open/investigating → action_taken，讓監造「驗證」按鈕出現
        # （portal_workflow_state: action_taken → 'improved'，模板驗證鈕條件成立）
        if self.state in ('open', 'investigating'):
            self.sudo().write({'state': 'action_taken'})

        # 組訊息正文（含有填的欄位都一併通知）
        body_lines = [f'承包廠商 {partner.name} 已提交改善：']
        body_lines.append(f'【改善說明】\n{improvement_text or "(未填)"}')
        if corrective_action:
            body_lines.append(f'【矯正措施】\n{corrective_action}')
        if preventive_action:
            body_lines.append(f'【預防措施】\n{preventive_action}')
        if after_photos:
            body_lines.append(f'【改善後照片】已上傳 {len(after_photos)} 張')

        self.sudo().message_post(
            body='\n\n'.join(body_lines).replace('\n', '<br/>'),
            message_type='comment',
            subtype_xmlid='mail.mt_comment',
            attachment_ids=list(after_photos) if after_photos else None,
        )

        return True
