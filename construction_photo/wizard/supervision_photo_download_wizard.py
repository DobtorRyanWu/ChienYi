# -*- coding: utf-8 -*-
"""後台批次下載照片精靈。

兩段式流程（比照 construction_batch.batch.download.wizard）：
    設定條件 →（可選）預覽縮圖 → 打包 zip → 下載

兩種取件方式，由 `selected_photo_ids` 有沒有值決定：
  1. **選取模式**：從「工程照片」清單勾選幾張後按頂端的「批次下載」，
     active_ids 會帶進來，直接打包那幾張，下面的篩選條件整組略過。
  2. **篩選模式**：從選單「照片管理 > 批次下載照片」進來，什麼都沒選，
     用工程案件 + 拍攝日期區間 + 分類/標籤/階段篩。

⚠️ 刻意不做的事（見 construction_supervision_base/__manifest__.py 註記 4.8.2）：
本精靈不碰 supervision.attachment.mixin、不產生 folder_id、不把照片放進
「工程資料夾樹」。照片的分類體系只有一套，就是 supervision.photo.category。
"""

import base64
import io
import logging
import re
import zipfile
from datetime import datetime, time

import pytz

from odoo import models, fields, api
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# 整包 zip 是在記憶體裡組出來的。**實測**（2026-08-20，DRYRUN-RSV-P11001
# 全案 455 張 / 原始 128.6 MB）：tracemalloc 峰值 483 MB、耗時 3.6 秒，
# 也就是原始總量的 **3.76 倍**（BytesIO 成長時的搬移 + getvalue() 的副本
# + base64 編碼後的另一份 171.5 MB）。
#
# odoo.conf 的 limit_memory_soft 是 2 GB，且本環境 workers=0（單一行程，
# 所有請求共用這塊記憶體）。300 MB × 3.76 ≈ 1.13 GB，還留得下餘裕；
# 原本估 2.5 倍時寫的 500 MB 會衝到 1.9 GB，太貼邊，故下修。
# 現有最大案件 128.6 MB，離上限還有 2.3 倍空間。
# 真的常態超過時再改成「寫暫存檔 + 串流」，屆時這個常數會整個拿掉。
MAX_TOTAL_BYTES = 300 * 1024 * 1024

# 檔名／資料夾名的非法字元。以 Windows 的規則為準（最嚴），
# 因為使用者十之八九是在 Windows 上解壓縮。
ILLEGAL_CHARS = re.compile(r'[\\/:*?"<>|\r\n\t]+')

# 分不出分類／日期時的收容資料夾。前綴底線讓它在檔案總管裡排在最前面，
# 一眼就看得出「這些是資料沒填完的」。
FOLDER_NO_CATEGORY = '_未分類'
FOLDER_NO_DATE = '_無拍攝日期'

# 設定畫面「範例」那一行用的示範值。資料夾部分不寫死 —— 交給 _folder_for()
# 依當下選的 folder_mode 算，與實際打包共用同一份規則。
EXAMPLE_LOCAL = datetime(2021, 11, 5, 14, 32)
EXAMPLE_CATEGORY = 'DEF_缺失'
EXAMPLE_FILENAME = '20211105_1432_原檔名.jpg'


def _photo_selection(field_name):
    """借用 supervision.photo 上同名欄位的選項清單。

    直接抄一份到這裡會漂移（模型加了新來源、精靈的下拉卻沒有），
    改成執行期去問模型本尊，一處定義兩處通用。
    """
    def _get(self):
        return self.env['supervision.photo']._fields[field_name].selection
    return _get


class SupervisionPhotoDownloadWizard(models.TransientModel):
    _name = 'supervision.photo.download.wizard'
    _description = '批次下載照片'

    # === 取件範圍 ===
    project_id = fields.Many2one(
        'project.project',
        string='工程案件',
        help='要下載哪一個工程案件的照片。')

    selected_photo_ids = fields.Many2many(
        'supervision.photo',
        'supervision_photo_download_wizard_rel',
        'wizard_id', 'photo_id',
        string='已選取的照片',
        help='從照片清單勾選帶進來的照片。有值時直接打包這些，忽略下方篩選條件。')

    # === 篩選條件（選取模式下不使用）===
    date_from = fields.Date(
        string='拍攝日期起',
        help='依「拍攝日期」篩選，不是上傳時間。')
    date_to = fields.Date(string='拍攝日期迄')

    category_id = fields.Many2one(
        'supervision.photo.category', string='照片分類')

    tag_ids = fields.Many2many(
        'supervision.photo.tag',
        'supervision_photo_download_wizard_tag_rel',
        'wizard_id', 'tag_id',
        string='標籤',
        help='多選為「或」：帶有其中任一標籤的照片都會被選進來。')

    # 「這張照片是從哪個單據來的」。使用者口中的「功能類型」指的就是這個，
    # 不是標籤 —— 標籤（supervision.photo.tag）全庫 8 個都是工項類
    # （雙孔箱涵／鋼筋綁紮／AC鋪設…），沒有功能類型的標籤。
    source_model = fields.Selection(
        selection=_photo_selection('source_model'),
        string='來源分類',
        help='照片掛在哪一種單據上。\n'
             '注意：直接上傳到「照片管理」而沒有掛任何單據的照片，'
             '這個欄位是空的（目前 470 張裡有 49 張），選了任何一項都篩不到它們。\n'
             '「其他」是集合項，估驗計價與工程告示牌的照片都落在這裡。')

    # 缺失改善專用。model 的 help 就是這樣寫的，實際資料也一致：
    # 有 photo_stage 的 19 張，source_model 全部是 defect。
    # 因此這個條件只有在「來源分類＝缺失改善」時才有意義，
    # 其餘情況隱藏起來（並在 onchange 清空，避免留著看不見的條件把結果篩成 0）。
    photo_stage = fields.Selection(
        selection=_photo_selection('photo_stage'),
        string='照片階段',
        help='缺失改善的矯正前／中／後三階段。')

    # ⚠️ 這裡刻意沒有 construction_phase（施工階段）。
    # 2026-08-20 全 addons 掃過：整個系統**沒有任何地方寫入**這個欄位，
    # 只有 construction_geoengine 的照片地圖與 construction_portal 的
    # _portal_map_build_domain() 拿它當篩選條件 —— 也就是說它永遠是 NULL
    # （實測全庫 470 張皆空）。放進來只會做出一個永遠篩不到東西的下拉。
    # 它與舊的 category Selection 同屬遺留欄位，要清理是另一件事。

    # === 輸出設定 ===
    # 選項只留名稱，實際長相交給下方的 path_example 那一行動態顯示
    folder_mode = fields.Selection([
        ('month', '依拍攝月份'),
        ('month_category', '依月份再分分類'),
        ('category_date', '依分類再分拍攝日'),
    ], string='zip 內目錄結構', default='month', required=True,
       help='照片分類目前多數未填，選後兩種會出現大量「_未分類」資料夾。')

    path_example = fields.Char(
        string='範例', compute='_compute_path_example',
        help='依目前選的目錄結構，照片在 zip 裡會長成這樣。')

    # === 結果 ===
    # attachment=True：檔案存進 filestore 而不是 transient 表的 bytea 欄位。
    # construction_batch 那支用 attachment=False，但它產的是幾百 KB 的
    # docx/xlsx；照片動輒上百 MB，塞進資料庫欄位是另一回事。
    result_file = fields.Binary(string='下載檔案', readonly=True, attachment=True)
    result_filename = fields.Char(string='檔案名稱', readonly=True)

    # === 統計（設定畫面即時顯示，不必按預覽就看得到）===
    photo_count = fields.Integer(
        string='照片張數', compute='_compute_summary')
    total_size = fields.Float(
        string='合計大小 (MB)', compute='_compute_summary', digits=(12, 1))
    size_warning = fields.Char(
        string='容量提醒', compute='_compute_summary')

    state = fields.Selection([
        ('draft', '設定'),
        ('done', '完成'),
    ], string='狀態', default='draft')

    # -------------------------------------------------------------------------
    # 預設值：從照片清單的批次動作帶進來的選取
    # -------------------------------------------------------------------------

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        ctx = self.env.context
        if ctx.get('active_model') != 'supervision.photo':
            return res

        photos = self.env['supervision.photo'].browse(
            ctx.get('active_ids') or []).exists()
        if not photos:
            return res

        res['selected_photo_ids'] = [(6, 0, photos.ids)]
        # 選取的照片同屬一個工程時把工程帶出來（畫面上要看得到打包的是哪個案子）；
        # 跨工程選取仍然允許，只是標題列不顯示工程名。
        projects = photos.mapped('project_id')
        if len(projects) == 1:
            res['project_id'] = projects.id
        return res

    # -------------------------------------------------------------------------
    # 取件
    # -------------------------------------------------------------------------

    def _get_photos(self):
        """本次會被打包的照片。

        選取模式直接回傳勾選的那些；篩選模式才去 search。
        兩者都會過使用者自己的存取權（沒有 sudo），看不到的照片就下載不到。
        """
        self.ensure_one()
        if self.selected_photo_ids:
            return self.selected_photo_ids
        if not self.project_id:
            return self.env['supervision.photo']
        return self.env['supervision.photo'].search(self._get_domain())

    def _get_domain(self):
        """篩選模式的 domain。"""
        self.ensure_one()
        domain = [
            ('project_id', '=', self.project_id.id),
            ('attachment_id', '!=', False),
        ]

        # 日期用 shot_at 配時區邊界，不直接比 shot_date。
        # shot_date 是 `shot_at.date()` 算出來的，那是 **UTC 的日期**；
        # 台北時間下午 4 點以後拍的照片，它的 shot_date 會早一天
        # （現有 470 張裡有 4 張是這種）。若拿 shot_date 篩，就會出現
        # 「篩 12/01 卻篩不到 12/01 早上 7 點拍的照片」，而且它在 zip 裡
        # 還是會被放進 12 月的資料夾 —— 篩選跟資料夾對不起來。
        # 改用時區換算後的 shot_at 邊界，篩選／資料夾／檔名三者才一致。
        start, end = self._utc_bounds()
        if start:
            domain.append(('shot_at', '>=', start))
        if end:
            domain.append(('shot_at', '<=', end))

        if self.category_id:
            domain.append(('category_id', '=', self.category_id.id))
        if self.tag_ids:
            domain.append(('tag_ids', 'in', self.tag_ids.ids))
        if self.source_model:
            domain.append(('source_model', '=', self.source_model))
        # 只在缺失改善下成立；其他來源時這個值會被 onchange 清掉
        if self.photo_stage and self.source_model == 'defect':
            domain.append(('photo_stage', '=', self.photo_stage))
        return domain

    def _tz(self):
        return pytz.timezone(self.env.user.tz or 'UTC')

    def _utc_bounds(self):
        """把使用者時區的 date_from / date_to 換成 shot_at 的 UTC 查詢邊界。"""
        self.ensure_one()
        tz = self._tz()
        start = end = False
        if self.date_from:
            start = tz.localize(
                datetime.combine(self.date_from, time.min)
            ).astimezone(pytz.utc).replace(tzinfo=None)
        if self.date_to:
            end = tz.localize(
                datetime.combine(self.date_to, time.max)
            ).astimezone(pytz.utc).replace(tzinfo=None)
        return start, end

    def _to_local(self, value):
        """UTC datetime → 使用者時區的 naive datetime；空值回 None。"""
        if not value:
            return None
        return pytz.utc.localize(value).astimezone(self._tz()).replace(tzinfo=None)

    # -------------------------------------------------------------------------
    # 統計與驗證
    # -------------------------------------------------------------------------

    @api.depends('folder_mode')
    def _compute_path_example(self):
        """設定畫面上「範例」那一行，隨目錄結構的選擇即時變化。

        資料夾部分呼叫 _folder_for() —— 就是實際打包在用的那個函式，
        所以範例不可能跟真正產出的結構不一致。
        """
        for wizard in self:
            folder = wizard._folder_for(EXAMPLE_LOCAL, EXAMPLE_CATEGORY)
            wizard.path_example = ('%s/%s' % (folder, EXAMPLE_FILENAME)
                                   if folder else EXAMPLE_FILENAME)

    @api.onchange('source_model')
    def _onchange_source_model(self):
        """來源不是缺失改善時清掉照片階段。

        欄位在畫面上會被 invisible 藏起來，但**值還在**，
        domain 照樣會用到它 —— 使用者只會看到「明明沒設什麼條件卻篩不到照片」。
        """
        if self.source_model != 'defect':
            self.photo_stage = False

    @api.depends('project_id', 'selected_photo_ids', 'date_from', 'date_to',
                 'category_id', 'tag_ids', 'source_model', 'photo_stage')
    def _compute_summary(self):
        for wizard in self:
            photos = wizard._get_photos()
            # file_size 是 related 到 ir.attachment 的非儲存欄位，不能 read_group；
            # mapped 會一次把附件 prefetch 起來，455 張是一個查詢的事。
            total = sum(photos.mapped('attachment_id.file_size'))
            wizard.photo_count = len(photos)
            wizard.total_size = total / 1048576.0
            if total > MAX_TOTAL_BYTES:
                wizard.size_warning = (
                    '合計 %.1f MB，超過單次 %s MB 的上限。'
                    '請縮小日期區間、加上分類條件，或分批下載。'
                    % (total / 1048576.0, MAX_TOTAL_BYTES // 1048576))
            else:
                wizard.size_warning = False

    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        for wizard in self:
            if wizard.date_from and wizard.date_to and wizard.date_from > wizard.date_to:
                raise UserError('「拍攝日期起」不能晚於「拍攝日期迄」。')

    # -------------------------------------------------------------------------
    # Action
    # -------------------------------------------------------------------------

    def action_preview(self):
        """另開預覽視窗，用照片自己的看板／清單檢視這次會打包哪些照片。

        為什麼包一層 supervision.photo.download.preview 而不是直接對
        supervision.photo 開 act_window：Odoo 的 action 對話框不會堆疊
        （action_service.js 的 _updateUI 會先 _removeDialog()），直接開照片清單
        等於把精靈丟掉，設定全部要重來；而照片自己的 list view 上也沒地方掛
        「返回設定」。包一層之後靠 wizard_id._reopen() 把同一筆精靈叫回來。
        """
        self.ensure_one()
        photos = self._get_photos()
        if not photos:
            raise UserError('目前的條件沒有符合的照片，沒有東西可以預覽。')

        preview = self.env['supervision.photo.download.preview'].create({
            'wizard_id': self.id,
            'photo_ids': [(6, 0, photos.ids)],
            'summary': '共 %s 張，合計 %.1f MB' % (
                len(photos),
                sum(photos.mapped('attachment_id.file_size')) / 1048576.0),
        })
        return {
            'type': 'ir.actions.act_window',
            'name': '預覽照片',
            'res_model': 'supervision.photo.download.preview',
            'res_id': preview.id,
            'view_mode': 'form',
            'views': [(self.env.ref(
                'construction_photo.supervision_photo_download_preview_form').id,
                'form')],
            'target': 'new',
        }

    def action_download(self):
        """打包並產生下載檔。"""
        self.ensure_one()
        photos = self._get_photos()
        if not photos:
            raise UserError('目前的條件沒有符合的照片。請放寬條件後再試。')

        total = sum(photos.mapped('attachment_id.file_size'))
        if total > MAX_TOTAL_BYTES:
            # 設定畫面已經用 size_warning 提醒過，這裡是真的擋下來
            raise UserError(
                '這次要打包 %s 張、合計 %.1f MB，超過單次 %s MB 的上限。\n\n'
                '整包 zip 是在伺服器記憶體裡組出來的，超過上限有拖垮服務的風險。\n'
                '請用日期區間或分類把範圍縮小後分批下載。'
                % (len(photos), total / 1048576.0, MAX_TOTAL_BYTES // 1048576))

        content, skipped = self._build_zip(photos)
        self.write({
            'state': 'done',
            'result_file': base64.b64encode(content),
            'result_filename': self._zip_filename(photos),
        })
        _logger.info('照片批次下載：%s 張、原始 %.1f MB、zip %.1f MB、略過 %s 張',
                     len(photos), total / 1048576.0,
                     len(content) / 1048576.0, len(skipped))
        return self._wrap_with_warnings(self._get_download_action(), skipped)

    def action_clear_selection(self):
        """清掉勾選帶進來的照片，切回用條件篩選。"""
        self.ensure_one()
        self.selected_photo_ids = [(5, 0, 0)]
        return self._reopen()

    def action_reset(self):
        """回到設定畫面重下條件。"""
        self.ensure_one()
        self.write({
            'state': 'draft',
            'result_file': False,
            'result_filename': False,
        })
        return self._reopen()

    # -------------------------------------------------------------------------
    # 打包
    # -------------------------------------------------------------------------

    def _build_zip(self, photos):
        """把照片打包成 zip。

        :return: (zip 的 bytes, 被略過的照片說明清單)
        """
        self.ensure_one()
        output = io.BytesIO()
        used_paths = {}
        skipped = []

        # ZIP_STORED 不是偷懶：JPEG/PNG 本身就是壓縮格式，再 deflate 一次
        # 幾乎不會變小（實測 128 MB 的照片壓完仍是 128 MB），卻要多花一倍 CPU
        # 與一份額外的記憶體。
        with zipfile.ZipFile(output, 'w', zipfile.ZIP_STORED) as zf:
            for photo in photos:
                # 附件的 res_id 是 0（見上傳精靈的 _detach_attachment），
                # ir.attachment.check() 對 res_id=0 不會擋，這裡 sudo 只是
                # 讓權限判斷單一化：能不能拿到這張照片，前面 search 已經決定了。
                raw = photo.attachment_id.sudo().raw
                if not raw:
                    skipped.append('#%s %s（檔案內容遺失）' % (
                        photo.id, photo.display_name))
                    continue
                path = self._zip_path(photo, used_paths)
                zf.writestr(path, raw)

        output.seek(0)
        return output.getvalue(), skipped

    def _zip_path(self, photo, used_paths):
        """算出這張照片在 zip 裡的完整路徑，並處理同名去重。

        `used_paths` 由呼叫端持有，key 用小寫路徑 —— Windows 的檔案系統不分
        大小寫，`IMG_1.JPG` 與 `img_1.jpg` 解壓縮時會互相覆蓋。
        """
        folder = self._zip_folder(photo)
        filename = self._zip_basename(photo)
        path = '%s/%s' % (folder, filename) if folder else filename

        key = path.lower()
        count = used_paths.get(key, 0)
        used_paths[key] = count + 1
        if count:
            stem, dot, ext = filename.rpartition('.')
            filename = ('%s_%s%s%s' % (stem, count + 1, dot, ext)
                        if dot else '%s_%s' % (filename, count + 1))
            path = '%s/%s' % (folder, filename) if folder else filename
            used_paths[path.lower()] = 1
        return path

    def _zip_folder(self, photo):
        """依 folder_mode 算出這張照片的資料夾。"""
        self.ensure_one()
        return self._folder_for(self._to_local(photo.shot_at),
                                self._category_folder(photo))

    def _folder_for(self, local, category):
        """資料夾規則本體，只吃「本地拍攝時間」與「分類資料夾名」。

        刻意不直接吃 photo：設定畫面的「範例」那一行要顯示同樣的規則，
        拆開之後範例與實際打包共用這一份邏輯，不會各寫一份而漂移。
        """
        self.ensure_one()
        if not local:
            # 拍攝日期空白（現有資料 0 筆，防呆用）：日期那一層換成 _無拍攝日期，
            # 分類那一層維持原本的位置，三種模式的層數才不會忽多忽少。
            if self.folder_mode == 'month':
                return FOLDER_NO_DATE
            if self.folder_mode == 'month_category':
                return '%s/%s' % (FOLDER_NO_DATE, category)
            return '%s/%s' % (category, FOLDER_NO_DATE)

        if self.folder_mode == 'month':
            return local.strftime('%Y-%m')
        if self.folder_mode == 'month_category':
            return '%s/%s' % (local.strftime('%Y-%m'), category)
        return '%s/%s' % (category, local.strftime('%Y-%m-%d'))

    def _category_folder(self, photo):
        """分類資料夾名，格式 `DEF_缺失`。沒填分類的收進 `_未分類`。"""
        if not photo.category_id:
            return FOLDER_NO_CATEGORY
        return self._sanitize('%s_%s' % (
            photo.category_id.code or 'NA', photo.category_id.name or ''))

    def _zip_basename(self, photo):
        """檔名：`20211105_1432_原檔名.jpg`。

        日期時間一律用使用者時區換算後的拍攝時間（與資料夾同一個時間軸）。
        原檔名保留在後面，因為現場常靠原檔名跟相機／手機裡的檔案對照。
        """
        local = self._to_local(photo.shot_at)
        original = self._sanitize(
            photo.attachment_id.name or ('photo_%s' % photo.id))
        if not original:
            original = 'photo_%s' % photo.id
        if not local:
            return original
        return '%s_%s' % (local.strftime('%Y%m%d_%H%M'), original)

    def _zip_filename(self, photos):
        """zip 本身的檔名，帶工程代碼與實際涵蓋的日期範圍。"""
        self.ensure_one()
        project = self.project_id or photos.mapped('project_id')[:1]
        label = self._sanitize(
            (project.code or project.display_name or '照片') if project else '照片')

        dates = [self._to_local(p.shot_at) for p in photos]
        dates = sorted(d for d in dates if d)
        if dates:
            span = ('%s-%s' % (dates[0].strftime('%Y%m%d'),
                               dates[-1].strftime('%Y%m%d'))
                    if dates[0].date() != dates[-1].date()
                    else dates[0].strftime('%Y%m%d'))
        else:
            span = fields.Date.context_today(self).strftime('%Y%m%d')
        return '照片_%s_%s.zip' % (label, span)

    @staticmethod
    def _sanitize(name):
        """清掉檔名／資料夾名不能用的字元，並砍掉尾端的點與空白。

        尾端的點與空白是 Windows 專屬地雷：`工項.` 這種資料夾在 Windows 上
        建不出來，解壓縮會直接失敗。
        """
        cleaned = ILLEGAL_CHARS.sub('_', name or '').strip()
        cleaned = cleaned.rstrip('. ')
        # 過長的檔名在 Windows 的 260 字元路徑限制下容易出事，留點餘裕
        return cleaned[:120]

    # -------------------------------------------------------------------------
    # 畫面流轉
    # -------------------------------------------------------------------------

    def _reopen(self):
        """把精靈本身再開一次（同一筆記錄，設定全部留著）。

        **按鈕方法不能回傳 None**：web/.../action_service.js 的 doActionButton 把
        非物件的回傳值當成 act_window_close，在對話框裡就是把精靈關掉。
        又因為 action 對話框不會堆疊，也不能另開一個，所以「留在原地」
        只能靠重開自己。（這段是 construction_batch 那支踩過的坑。）
        """
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': '批次下載照片',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'views': [(self.env.ref(
                'construction_photo.supervision_photo_download_wizard_form').id,
                'form')],
            'target': 'new',
        }

    def _get_download_action(self):
        """下載結果畫面。

        ⚠️ `views` 一定要自己填。本方法的回傳值可能被 _wrap_with_warnings()
        塞進 display_notification 的 `params.next`，而 **next 不經過
        clean_action()**，少了 views 前端 _preprocessAction() 的
        `action.views.map(...)` 會噴 "Cannot read properties of undefined"。
        """
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'views': [(self.env.ref(
                'construction_photo.supervision_photo_download_wizard_result_form').id,
                'form')],
            'target': 'new',
        }

    def _wrap_with_warnings(self, action, skipped):
        """有照片被略過就先跳 sticky 通知，再進到下載畫面。"""
        self.ensure_one()
        if not skipped:
            return action
        _logger.warning('照片批次下載略過 %s 張：%s', len(skipped), '；'.join(skipped))
        shown = skipped[:10]
        message = '\n'.join(shown)
        if len(skipped) > len(shown):
            message += '\n（另有 %s 張，詳見伺服器日誌）' % (len(skipped) - len(shown))
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': '檔案已產生，但有 %s 張照片沒放進去' % len(skipped),
                'message': message,
                'type': 'warning',
                'sticky': True,
                'next': action,
            },
        }


class SupervisionPhotoDownloadPreview(models.TransientModel):
    """批次下載的「預覽照片」視窗。

    照片用 Many2many 裝著，畫面上顯示的就是 supervision.photo 原本的看板
    （有縮圖，真的看得到要下載什麼），可以點進去看單張詳情再退回來。
    """
    _name = 'supervision.photo.download.preview'
    _description = '批次下載照片預覽'

    wizard_id = fields.Many2one(
        'supervision.photo.download.wizard',
        string='來源精靈', required=True, ondelete='cascade')

    photo_ids = fields.Many2many(
        'supervision.photo',
        'supervision_photo_download_preview_rel',
        'preview_id', 'photo_id',
        string='照片')

    summary = fields.Char(string='摘要', readonly=True)

    def action_back(self):
        """回到設定畫面（同一筆精靈，條件全部留著）。"""
        self.ensure_one()
        return self.wizard_id._reopen()

    def action_download(self):
        """在預覽畫面直接按下載，不用退回設定頁。"""
        self.ensure_one()
        return self.wizard_id.action_download()
