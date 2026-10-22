"""會員證書與照片的上傳與審核（簡報「帳號管理：上傳證書」）。

不用 ir.attachment 當主體：`ir.attachment.check()` 對非內部使用者一律 AccessError，
會員前台（M6）根本讀不到自己的附件。改成自建模型放 Binary 欄位，
前台一律經 controller 驗身分後 sudo 取用。

「現行文件」＝同一類型最新一筆 approved（不另設 superseded 狀態）。
"""

import base64
import hashlib
import io

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tools.mimetypes import guess_mimetype

from ..tools import GUARD, check_created, check_guild_admin, guarded

ADMIN_GROUP = 'assoc_base.group_assoc_admin'
GUARD_REVIEW = 'assoc_doc_review'
# 只能由審核動作寫的欄位（P23：context 旗標會被 RPC 偽造，所以比對哨兵物件）
SYSTEM_FIELDS = frozenset({'state', 'approved_once', 'member_id', 'reviewer_uid', 'reviewed_at'})
DOC_MAX_MB = 10


def image_is_readable(content):
    """圖檔能不能真的解得開。

    只靠 magic bytes 不夠：`ir.attachment._check_contents` 會對圖片跑
    `_postprocess_contents` → `ImageProcess`（ir_attachment.py:345 → tools/image.py:103），
    而 Pillow 對截斷的檔丟 `OSError: Truncated File Read`，Odoo **沒有接住** →
    前台上傳一個壞掉的 PNG 就能讓路由回 500（實測，M6 E2E 逮到）。
    """
    from PIL import Image
    try:
        with Image.open(io.BytesIO(content)) as image:
            image.load()          # verify() 不會讀完整個檔，load() 才會
    except Exception:             # noqa: BLE001  任何解不開都算壞檔
        return False
    return True


ALLOWED_MIMETYPES = {
    'application/pdf': 'pdf',
    'image/jpeg': 'jpg',
    'image/png': 'png',
}


class AssocMemberDocument(models.Model):
    _name = 'assoc.member.document'
    _description = '會員證明文件'
    _order = 'member_id, doc_type, id desc'
    # `check_company=True` **單獨放在欄位上是靜默無效的**：核心 models.py:4860／:5076
    # 只在 `_check_company_auto` 為真時才跑那道約束（實查）。第十四輪加了十個
    # `check_company=True` 之後測試仍然紅，就是漏了這一行。
    _check_company_auto = True

    member_id = fields.Many2one(
        'assoc.member', check_company=True, string='會員', required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one(
        'res.company', string='公會', related='member_id.company_id', store=True, index=True)
    doc_type = fields.Selection(
        [('engineer_cert', '技師證書'),
         ('practice_license', '執業執照'),
         ('education', '學經歷證明'),
         ('photo', '會員照片'),
         ('other', '其他')],
        string='文件類型', required=True)
    cert_no = fields.Char(string='證號')
    issue_date = fields.Date(string='發證日期')
    expiry_date = fields.Date(string='有效期限')
    file = fields.Binary(string='檔案', required=True, attachment=True, groups=ADMIN_GROUP)
    file_name = fields.Char(string='檔名')
    sha256 = fields.Char(string='檔案指紋', readonly=True, copy=False)
    state = fields.Selection(
        [('submitted', '待審核'), ('approved', '已核准'), ('rejected', '已退回')],
        string='狀態', default='submitted', required=True, index=True)
    submitted_via = fields.Selection(
        [('portal', '會員前台'), ('backend', '後台')], string='來源', default='backend')
    reviewer_uid = fields.Many2one('res.users', string='審核人', readonly=True)
    reviewed_at = fields.Datetime(string='審核時間', readonly=True)
    reject_reason = fields.Char(string='退回原因')
    approved_once = fields.Boolean(string='曾經核准', readonly=True, copy=False)

    @api.constrains('file', 'file_name')
    def _check_file(self):
        for doc in self:
            raw = doc.sudo().file
            if not raw:
                continue
            content = base64.b64decode(raw)
            if len(content) > DOC_MAX_MB * 1024 * 1024:
                raise ValidationError(_('檔案不可超過 %s MB。', DOC_MAX_MB))
            mimetype = guess_mimetype(content)
            if mimetype not in ALLOWED_MIMETYPES:
                raise ValidationError(_('只接受 PDF、JPG、PNG 檔。'))
            if doc.doc_type == 'photo' and not mimetype.startswith('image/'):
                # 照片核准時直接寫進 partner.image_1920，PDF 會炸在 Odoo 的解碼錯誤
                raise ValidationError(_('會員照片只接受 JPG 或 PNG。'))
            if mimetype.startswith('image/') and not image_is_readable(content):
                raise ValidationError(_('這個圖檔解不開，請重新輸出後再上傳。'))

    def _compute_sha256(self):
        for doc in self:
            content = base64.b64decode(doc.sudo().file) if doc.sudo().file else b''
            doc.sha256 = hashlib.sha256(content).hexdigest() if content else False

    @api.model_create_multi
    def create(self, vals_list):
        docs = super().create(vals_list)
        # 驗結果不驗輸入：context 的 default_state 或 ir.default 都能改初值
        check_created(docs, {'state': 'submitted', 'approved_once': False,
                             'reviewer_uid': False}, GUARD_REVIEW)
        docs._compute_sha256()
        return docs

    def write(self, vals):
        # 狀態與歸屬只能由審核方法改：少了這道，RPC 先把 approved 改回 submitted
        # 就能繞過「已核准不可改」，改 member_id 還能把文件搬到別的公會。
        if SYSTEM_FIELDS & set(vals) and not guarded(self.env, GUARD_REVIEW):
            raise UserError(_('文件狀態與歸屬只能由審核動作變更。'))
        locked = {'file', 'file_name', 'doc_type', 'cert_no', 'issue_date', 'expiry_date'}
        if locked & set(vals):
            for doc in self:
                if doc.state == 'approved' or doc.approved_once:
                    raise UserError(_('已核准的文件不可修改，請改為新增一份。'))
        res = super().write(vals)
        if 'file' in vals:
            self._compute_sha256()
        return res

    def unlink(self):
        # 看「曾經核准」而不是當下狀態：否則改回 submitted 就能刪掉審核軌跡
        if any(doc.state == 'approved' or doc.approved_once for doc in self):
            raise UserError(_('已核准的文件不可刪除（審核軌跡）。'))
        return super().unlink()

    def _check_admin(self):
        check_guild_admin(self, _('只有公會管理員可以審核文件。'))

    def action_approve(self):
        self._check_admin()
        for doc in self:
            if doc.state == 'approved':
                continue
            doc.with_context(**{GUARD_REVIEW: GUARD}).write({
                'state': 'approved',
                'approved_once': True,
                'reviewer_uid': self.env.uid,
                'reviewed_at': fields.Datetime.now(),
                'reject_reason': False,
            })
            if doc.doc_type == 'photo':
                # 照片核准後才套用到會員：報到台核對本人、動態 QR 防轉傳都靠這張照片
                doc.member_id.sudo().partner_id.image_1920 = doc.sudo().file
            self.env['assoc.audit.log']._log(
                'doc_review', records=doc.member_id,
                detail={'doc_id': doc.id, 'doc_type': doc.doc_type, 'result': 'approved'})
        return True

    def action_reject(self):
        self._check_admin()
        for doc in self:
            if not doc.reject_reason:
                raise UserError(_('請填寫退回原因。'))
            doc.with_context(**{GUARD_REVIEW: GUARD}).write({
                'state': 'rejected',
                'reviewer_uid': self.env.uid,
                'reviewed_at': fields.Datetime.now(),
            })
            self.env['assoc.audit.log']._log(
                'doc_review', records=doc.member_id,
                detail={'doc_id': doc.id, 'doc_type': doc.doc_type, 'result': 'rejected'})
        return True

    @api.model
    def _current_document(self, member, doc_type):
        """同一類型最新一筆已核准的文件。"""
        return self.sudo().search(
            [('member_id', '=', member.id), ('doc_type', '=', doc_type), ('state', '=', 'approved')],
            order='id desc', limit=1)
