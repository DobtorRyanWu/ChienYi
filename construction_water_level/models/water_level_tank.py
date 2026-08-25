# -*- coding: utf-8 -*-
"""蓄水池。

社區端真正在乎的不是「水位幾公尺」，是「還剩幾 %」。物業管理員看到 2.26 公尺沒有感覺，
看到「剩 38%」才會去叫水車。所以水位→體積的換算是這個模型的核心。

換算只在 `_volume_at()` 一個函式裡做，任何地方都不准自己重算——散在各處的換算公式
遲早會不一致，而且不一致時沒有任何錯誤訊息。

高程基準：`bottom_elevation` / `full_elevation` 與設備上報換算後的水位高程
（讀值 + 設備的 datum_elevation）用同一個基準。基準沒對齊，整池的儲水率都是垃圾。
"""

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

PERCENT_FULL = 100.0
# 容量曲線至少要幾個點才算得出東西
MIN_CURVE_POINTS = 2


class WaterLevelTank(models.Model):
    _name = 'water.level.tank'
    _description = '蓄水池'
    _inherit = ['mail.thread']
    _order = 'site_id, sequence, id'

    name = fields.Char(string='池名', required=True, tracking=True)
    code = fields.Char(string='池編號', copy=False)
    sequence = fields.Integer(string='排序', default=10)
    active = fields.Boolean(string='啟用', default=True)

    site_id = fields.Many2one(
        'water.level.site', string='監測場域',
        required=True, ondelete='restrict', index=True, tracking=True)

    usage = fields.Selection(
        [('potable', '飲用水'),
         ('fire', '消防'),
         ('recycled', '中水'),
         ('detention', '滯洪')],
        string='用途', default='potable', required=True)

    # === 幾何與容量 ===
    bottom_elevation = fields.Float(
        string='池底高程(m)', digits=(10, 3), required=True,
        help='空池時的水位高程。與設備換算後的水位高程用同一個基準。')
    full_elevation = fields.Float(
        string='滿水位高程(m)', digits=(10, 3), required=True)
    design_volume_m3 = fields.Float(string='設計容量(m³)', digits=(12, 3))
    effective_volume_m3 = fields.Float(
        string='有效容量(m³)', digits=(12, 3),
        help='池底到滿水位之間可用的水量，儲水率以此為分母。')

    volume_method = fields.Selection(
        [('linear', '直壁池（線性）'),
         ('curve', '異形池（容量曲線）')],
        string='容量換算方式', default='linear', required=True)
    curve_ids = fields.One2many(
        'water.level.tank.curve', 'tank_id', string='容量曲線')

    # === 設備 ===
    device_ids = fields.One2many(
        'water.level.device', 'tank_id', string='監測設備')
    primary_device_id = fields.Many2one(
        'water.level.device', string='代表設備',
        ondelete='set null',
        help='一池裝多台時，指定哪一台的讀值代表這個池。留空就取第一台。')

    # === 現況 ===
    current_level = fields.Float(
        string='目前水位高程(m)', digits=(10, 3),
        compute='_compute_storage', store=True)
    current_volume_m3 = fields.Float(
        string='目前水量(m³)', digits=(12, 3),
        compute='_compute_storage', store=True)
    fill_rate = fields.Float(
        string='儲水率(%)', digits=(5, 1),
        compute='_compute_storage', store=True, tracking=True)

    is_stale = fields.Boolean(
        string='資料已過期', compute='_compute_is_stale',
        help='代表設備已斷線。儲水率是最後一次上報算出來的，不是現在的水位——'
             '顯示的地方一定要標出來，不然就是拿一個過期數字冒充現況。')

    low_fill_alert_pct = fields.Float(
        string='低儲水率警戒(%)', digits=(5, 1), default=30.0,
        help='物業管理看的是百分比，不是公尺。')
    high_fill_alert_pct = fields.Float(
        string='高儲水率警戒(%)', digits=(5, 1), default=98.0,
        help='接近滿水位，注意溢流。')

    # ==================== 換算（唯一入口）====================

    def _volume_at(self, elevation):
        """水位高程 → 水量(m³)。這是全模組唯一的換算入口。

        直壁池走線性；異形池用容量曲線做線性內插。
        超出池底／滿水位一律夾回範圍——感測器抖動不該產生負水量或超過滿池的水量。
        """
        self.ensure_one()
        if self.volume_method == 'curve':
            return self._volume_from_curve(elevation)

        span = self.full_elevation - self.bottom_elevation
        if span <= 0 or not self.effective_volume_m3:
            return 0.0
        ratio = (elevation - self.bottom_elevation) / span
        ratio = max(0.0, min(1.0, ratio))
        return self.effective_volume_m3 * ratio

    def _volume_from_curve(self, elevation):
        points = self.curve_ids.sorted('elevation')
        if len(points) < MIN_CURVE_POINTS:
            return 0.0
        if elevation <= points[0].elevation:
            return points[0].volume_m3
        if elevation >= points[-1].elevation:
            return points[-1].volume_m3
        for low, high in zip(points, points[1:]):
            if low.elevation <= elevation <= high.elevation:
                span = high.elevation - low.elevation
                if span <= 0:
                    return low.volume_m3
                ratio = (elevation - low.elevation) / span
                return low.volume_m3 + (high.volume_m3 - low.volume_m3) * ratio
        return points[-1].volume_m3

    def _capacity(self):
        """儲水率的分母。曲線池用曲線最高點，直壁池用有效容量。"""
        self.ensure_one()
        if self.volume_method == 'curve' and self.curve_ids:
            return max(self.curve_ids.mapped('volume_m3') or [0.0])
        return self.effective_volume_m3

    # ==================== Compute ====================

    @api.depends('primary_device_id.last_value', 'device_ids.last_value',
                 'bottom_elevation', 'full_elevation', 'effective_volume_m3',
                 'volume_method', 'curve_ids.elevation', 'curve_ids.volume_m3')
    def _compute_storage(self):
        for tank in self:
            device = tank.primary_device_id or tank.device_ids[:1]
            level = device.last_value if device else 0.0
            tank.current_level = level
            if not device:
                tank.current_volume_m3 = 0.0
                tank.fill_rate = 0.0
                continue
            volume = tank._volume_at(level)
            capacity = tank._capacity()
            tank.current_volume_m3 = volume
            tank.fill_rate = (volume / capacity * PERCENT_FULL) if capacity else 0.0

    def _compute_is_stale(self):
        for tank in self:
            device = tank.primary_device_id or tank.device_ids[:1]
            tank.is_stale = bool(device) and device.is_offline

    # ==================== Constrains ====================

    @api.constrains('bottom_elevation', 'full_elevation')
    def _check_elevations(self):
        for tank in self:
            if tank.full_elevation <= tank.bottom_elevation:
                raise ValidationError(_(
                    '「%s」的滿水位高程必須高於池底高程。', tank.name))

    @api.constrains('design_volume_m3', 'effective_volume_m3')
    def _check_volumes(self):
        for tank in self:
            if tank.design_volume_m3 and tank.effective_volume_m3 > tank.design_volume_m3:
                raise ValidationError(_(
                    '「%s」的有效容量不可大於設計容量。', tank.name))

    @api.constrains('volume_method', 'curve_ids')
    def _check_curve(self):
        for tank in self:
            if tank.volume_method == 'curve' and len(tank.curve_ids) < MIN_CURVE_POINTS:
                raise ValidationError(_(
                    '「%(name)s」選了容量曲線，至少要有 %(n)s 個點才算得出水量。',
                    name=tank.name, n=MIN_CURVE_POINTS))

    @api.constrains('primary_device_id', 'device_ids')
    def _check_primary_device(self):
        for tank in self:
            if tank.primary_device_id and tank.primary_device_id.tank_id != tank:
                raise ValidationError(_(
                    '「%s」的代表設備必須是這個池底下的設備。', tank.name))

    @api.constrains('site_id', 'device_ids')
    def _check_device_site(self):
        """池與它的設備必須屬於同一個場域，否則儲水率會跨場域取值。"""
        for tank in self:
            wrong = tank.device_ids.filtered(lambda d: d.site_id != tank.site_id)
            if wrong:
                raise ValidationError(_(
                    '「%(tank)s」底下有設備不屬於場域「%(site)s」：%(names)s',
                    tank=tank.name, site=tank.site_id.name,
                    names=', '.join(wrong.mapped('name'))))


class WaterLevelTankCurve(models.Model):
    _name = 'water.level.tank.curve'
    _description = '蓄水池容量曲線'
    _order = 'tank_id, elevation'

    tank_id = fields.Many2one(
        'water.level.tank', string='蓄水池',
        required=True, ondelete='cascade', index=True)
    elevation = fields.Float(string='水位高程(m)', digits=(10, 3), required=True)
    volume_m3 = fields.Float(string='累積水量(m³)', digits=(12, 3), required=True)

    _sql_constraints = [
        ('tank_elevation_uniq', 'unique(tank_id, elevation)', '同一個高程只能有一筆。'),
    ]
