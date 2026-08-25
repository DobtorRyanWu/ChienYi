# -*- coding: utf-8 -*-
"""水位時序紀錄（append-only）。

DM 對客戶承諾「純追加式寫入」與「連續序號核對，缺號自動索取補送」，
所以這張表有兩個性質跟一般 Odoo 模型不一樣：

1. **量測資料寫進去就不能改也不能刪**。三層防護：
   - ir.model.access：所有群組 write=0、unlink=0（含系統管理者）
   - model 層 write()/unlink() override（擋得住 sudo）
   - 資料庫 trigger（擋得住原生 SQL 與 psql 直連）
   三層都有各自擋不住的東西，疊起來才完整。細節見 `init()`。

2. **序號是設備給的**，不是資料庫序號。`(device_id, seq_no)` 唯一，
   跳號代表資料在路上掉了，由 water.level.gap 追蹤補送。

量體：每分鐘一筆、保存兩年 = 單台約 105 萬筆。目前規模（10 台以內）單表即可；
未來要切 range partition 時，`(device_id, seq_no)` 這條唯一約束會擋路（分割表的
唯一約束必須含分割鍵 ts），屆時要重新決策。這裡選擇合規優先。
"""

import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# 開啟維護視窗用的 PostgreSQL 設定名稱。設成 'on' 之後 trigger 放行。
MAINTENANCE_SETTING = 'water_level.maintenance'
MAINTENANCE_ON = 'on'

# 寫入後就不准再變動的欄位。改這些等於竄改量測結果。
IMMUTABLE_FIELDS = ('device_id', 'ts', 'value', 'raw_value', 'seq_no', 'chain_hash')


class WaterLevelReading(models.Model):
    _name = 'water.level.reading'
    _description = '水位紀錄'
    _order = 'ts desc'
    _log_access = False

    device_id = fields.Many2one(
        'water.level.device', string='監測站',
        required=True, ondelete='cascade', index=True)
    project_id = fields.Many2one(
        'project.project', string='工程案件',
        related='device_id.project_id', store=True, index=True)
    ts = fields.Datetime(
        string='時間', required=True, index=True,
        help='設備量測當下的時間，一律存 naive UTC。顯示時 Odoo 自動換算使用者時區，'
             '程式碼裡不要再手動加減時差。')
    received_at = fields.Datetime(
        string='收到時間',
        help='Odoo 實際收到的時間。與量測時間分開存：斷網補送時兩者會差很多，'
             '這是判斷「這批是不是補送」的依據，也是告警要不要發的判準。')
    value = fields.Float(
        string='水位高程(m)', digits=(10, 3), aggregator='max',
        help='設備上報值加上該站基準高程後的水位高程。圖表與警戒門檻都用這個。')
    raw_value = fields.Float(
        string='設備上報值(m)', digits=(10, 3),
        help='設備原樣送來的量測值，沒有加基準高程。雜湊鏈是對這個值算的——'
             '設備算雜湊時不知道我們的基準高程，而且基準高程日後可能修正，'
             '鏈不能因為我們改設定就整段變紅。')

    seq_no = fields.Integer(
        string='設備序號', index=True,
        help='設備端的連續流水號。跳號代表資料掉了，由缺號稽核追補。'
             '舊資料與不支援序號的設備為空。')
    chain_hash = fields.Char(
        string='雜湊鏈', size=64, index=False,
        help='設備端計算的雜湊鏈值，前一筆的 chain_hash 就是本筆的 prev。'
             '不另存 prev_hash——驗證本來就要按序讀，存兩份只是浪費空間。')

    _sql_constraints = [
        ('device_ts_uniq', 'unique(device_id, ts)', '同一監測站的同一時間點已有紀錄。'),
        ('device_seq_uniq', 'unique(device_id, seq_no)', '同一監測站的同一序號已有紀錄。'),
    ]

    @api.depends('device_id.name', 'ts')
    def _compute_display_name(self):
        for reading in self:
            reading.display_name = '%s %s' % (reading.device_id.name or '', reading.ts or '')

    # ==================== append-only ====================

    def write(self, vals):
        """量測欄位一律不准改；project_id 這種歸屬欄位放行（stored related 會需要重算）。"""
        touched = [name for name in IMMUTABLE_FIELDS if name in vals]
        if touched and not self._maintenance_open():
            raise UserError(_(
                '水位紀錄是純追加式資料，不可修改 %s。'
                '真的要修正歷史資料，請開啟維護視窗並留下稽核紀錄。',
                '、'.join(touched)))
        return super().write(vals)

    def unlink(self):
        if not self._maintenance_open():
            raise UserError(_(
                '水位紀錄不可刪除——這套系統對客戶承諾依法保存兩年。'
                '到期要封存請走封存流程，不要刪資料。'))
        return super().unlink()

    def _maintenance_open(self):
        """維護視窗是否已開。與資料庫 trigger 看同一個開關，兩層不會各說各話。"""
        self.env.cr.execute("SELECT current_setting(%s, true)", (MAINTENANCE_SETTING,))
        return (self.env.cr.fetchone()[0] or '') == MAINTENANCE_ON

    @api.model
    def _open_maintenance_window(self, reason):
        """開啟維護視窗（只在當前交易內有效，交易結束自動關閉）。

        呼叫端必須說明理由，理由會進 log；之後完整性稽核模型上線後也會留一筆紀錄。
        """
        if not reason:
            raise UserError(_('開啟維護視窗必須說明理由。'))
        # 用 set_config 而不是 SET LOCAL：PostgreSQL 的 SET 不吃參數綁定，
        # 硬拼字串就是把設定名稱與值直接插進 SQL。第三個參數 true = 只在本交易有效。
        self.env.cr.execute(
            "SELECT set_config(%s, %s, true)", (MAINTENANCE_SETTING, MAINTENANCE_ON))
        _logger.warning('水位紀錄維護視窗已開啟（僅本交易有效）：%s', reason)

    @api.model
    def _append_only_trigger_exists(self):
        """給 cron 每日確認 trigger 還在。有人 DROP 之後忘了加回來，比一開始就沒有更糟。"""
        self.env.cr.execute("""
            SELECT count(*) FROM pg_trigger
             WHERE tgname = 'water_level_reading_append_only_trg'
               AND NOT tgisinternal
        """)
        return bool(self.env.cr.fetchone()[0])

    def init(self):
        """資料庫層的 append-only 保護。

        為什麼不是「任何 UPDATE 都擋」：Odoo 自己會因為 stored related 重算而 UPDATE
        project_id，一律擋掉會讓自家的升級與遷移直接卡死，然後有人就會去 DROP TRIGGER
        ——而 drop 之後多半忘記加回來。所以只保護量測欄位，其餘放行。

        逃生門：`SET LOCAL water_level.maintenance = 'on'`，只在該交易內有效。
        """
        self.env.cr.execute("""
            -- 注意：這段 SQL 不帶 psycopg2 參數，所以 RAISE 的格式符號寫單一 %，
            -- 寫成 %% 會原樣進到 plpgsql，變成兩個佔位符只有一個引數而編譯失敗。
            CREATE OR REPLACE FUNCTION water_level_reading_append_only()
            RETURNS trigger AS $trg$
            BEGIN
                IF current_setting('water_level.maintenance', true) = 'on' THEN
                    IF TG_OP = 'DELETE' THEN RETURN OLD; ELSE RETURN NEW; END IF;
                END IF;

                IF TG_OP = 'DELETE' THEN
                    RAISE EXCEPTION '水位紀錄不可刪除（append-only）。id=%', OLD.id
                        USING ERRCODE = 'restrict_violation';
                END IF;

                IF NEW.device_id IS DISTINCT FROM OLD.device_id
                   OR NEW.ts IS DISTINCT FROM OLD.ts
                   OR NEW.value IS DISTINCT FROM OLD.value
                   OR NEW.raw_value IS DISTINCT FROM OLD.raw_value
                   OR NEW.seq_no IS DISTINCT FROM OLD.seq_no
                   OR NEW.chain_hash IS DISTINCT FROM OLD.chain_hash THEN
                    RAISE EXCEPTION '水位紀錄的量測欄位不可修改（append-only）。id=%', OLD.id
                        USING ERRCODE = 'restrict_violation';
                END IF;

                RETURN NEW;
            END;
            $trg$ LANGUAGE plpgsql;
        """)
        self.env.cr.execute("""
            DROP TRIGGER IF EXISTS water_level_reading_append_only_trg
                ON water_level_reading
        """)
        self.env.cr.execute("""
            CREATE TRIGGER water_level_reading_append_only_trg
                BEFORE UPDATE OR DELETE ON water_level_reading
                FOR EACH ROW EXECUTE FUNCTION water_level_reading_append_only()
        """)
