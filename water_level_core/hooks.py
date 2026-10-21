# -*- coding: utf-8 -*-
"""2026-10 拆模組：把既有庫的「歸屬」從 construction_water_level 改掛到新模組。

背景
----
2.x 時整套水位都在 construction_water_level。3.0 拆成三個模組，**模型、資料表、欄位
一律不動**，只改 Odoo 記帳用的「這筆東西屬於哪個模組」：

* ir_model_data.module        —— xmlid（模型、欄位、ACL、rule、view、menu、cron……）
* ir_model_constraint.module  —— SQL 約束與外鍵（模組被移除時 Odoo 依這欄決定 DROP 誰）
* ir_model_relation.module    —— Many2many 關聯表（同上）

為什麼一定要在**新模組的 pre_init_hook** 做（而不是舊模組的 migration）
--------------------------------------------------------------------
升級 construction_water_level 時，依賴的核心會**先**被安裝，之後才輪到舊模組的 migration。
如果到那時才改名，核心安裝當下找不到同名 xmlid，會**新建**一份 cron／序號／選單，
舊的再被 `_process_end` 刪掉——後果是：
* 事件序號 ir.sequence 重建 → 編號從 1 重來，與既有事件撞號
* cron 重建 → 手動啟用的「從資料來源撈取」變回停用，正式站從此不再拉資料而且沒有錯誤

而沒改 ir_model_constraint.module 的話，既有的**外鍵**會一直掛在舊模組名下（外鍵規格沒變時
Odoo 不會重新登記，registry.check_foreign_keys），日後移除工程模組時就被 DROP——
reading.device_id 的外鍵沒了，「刪監測站要先過保存期」的 restrict 保護跟著失效。
（_sql_constraints 不會：核心安裝時會以自己的名義再登記一份，移除時 Odoo 看到還有別的
模組擁有就不 DROP。一起搬是為了帳目乾淨，不是靠它保命。）

安裝模式（init）會用 XML 的值覆寫既有紀錄、**不管 noupdate**，所以 cron 的
active／間隔會被 XML 蓋回預設。pre_init_hook 先記下來，post_init_hook 再寫回去。

空庫安裝（從來沒有 construction_water_level 2.x 的資料）時，兩個 hook 都是 no-op。
"""

import json
import logging

from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

OLD_MODULE = 'construction_water_level'
CORE_MODULE = 'water_level_core'
ENGINEERING_MODULE = 'construction_water_level'
COMMUNITY_MODULE = 'community_water_level'

CRON_STASH_PARAM = 'water_level_core.split_cron_state'
# 等線上正在執行的水位排程跑完的上限。ir.cron.write() 一律先 FOR NO KEY UPDATE NOWAIT，
# 線上伺服器剛好在跑某支排程時，安裝模式重寫 cron 會直接失敗；先「等待式」鎖住就不會撞。
CRON_LOCK_TIMEOUT = '300s'
# 安裝模式會被 XML 覆寫、所以要先記下來的 cron 欄位（nextcall 不在 XML 裡，不會被動到）
CRON_STASH_FIELDS = ('active', 'interval_number', 'interval_type')

# 工程水位 3.0 仍由自己定義的 xmlid：三個 project_id 欄位、六條工程 rule、十五條前台 ACL。
# 名稱要與 construction_water_level 的 CSV／XML 完全一致，否則那筆會被當成「不再定義」而刪掉。
ENGINEERING_XMLIDS = frozenset({
    'field_water_level_site__project_id',
    'field_water_level_device__project_id',
    'field_water_level_reading__project_id',
    'water_level_device_portal_member_rule',
    'water_level_device_portal_boss_rule',
    'water_level_reading_portal_member_rule',
    'water_level_reading_portal_boss_rule',
    'water_level_site_portal_member_rule',
    'water_level_site_portal_boss_rule',
    'access_water_level_device_subscriber',
    'access_water_level_device_leader',
    'access_water_level_device_user',
    'access_water_level_device_viewer',
    'access_water_level_reading_subscriber',
    'access_water_level_reading_leader',
    'access_water_level_reading_user',
    'access_water_level_reading_viewer',
    'access_water_level_site_subscriber',
    'access_water_level_site_leader',
    'access_water_level_site_user',
    'access_water_level_site_viewer',
    'access_water_level_site_portal_base',
    'access_water_level_device_portal_base',
    'access_water_level_reading_portal_base',
})

# 社區水位的 xmlid：名稱含 tank 的全部（核心與工程沒有任何 tank 開頭或含 tank 的東西），
# 再加上這幾個不含 tank 的。注意不能用「含 community」判斷——
# 核心的 selection__water_level_site__site_type__community 也含這個字。
COMMUNITY_XMLIDS = frozenset({
    'field_water_level_site__owner_partner_id',
    'field_water_level_site__member_user_ids',
    'action_water_level_community_overview',
    'menu_water_level_community_overview',
    'water_level_site_community_member_rule',
    'water_level_device_community_member_rule',
    'water_level_reading_community_member_rule',
    'access_water_level_event_portal',
    'access_water_level_event_frame_portal',
    'access_water_level_daily_portal',
})


def classify_xmlid(name):
    """舊模組名下的一個 xmlid（不含模組前綴）在 3.0 歸哪個模組。"""
    if name in ENGINEERING_XMLIDS:
        return ENGINEERING_MODULE
    if 'tank' in name or name in COMMUNITY_XMLIDS:
        return COMMUNITY_MODULE
    return CORE_MODULE


def classify_db_object(name):
    """約束或關聯表的名稱（PostgreSQL 物件名）歸哪個模組。

    外鍵名是 <表>_<欄>_fkey；關聯表是 water_level_site_member_rel 與它自己的兩條外鍵。
    """
    if 'project_id' in name:
        return ENGINEERING_MODULE
    if 'tank' in name or 'owner_partner_id' in name or name.startswith('water_level_site_member_rel'):
        return COMMUNITY_MODULE
    return CORE_MODULE


def _module_state(cr, name):
    cr.execute("SELECT state FROM ir_module_module WHERE name = %s", [name])
    row = cr.fetchone()
    return row[0] if row else None


def _table_exists(cr, table):
    cr.execute("SELECT to_regclass(%s) IS NOT NULL", [table])
    return cr.fetchone()[0]


def ensure_community_module_scheduled(env):
    """庫裡有社區資料、這次卻沒有一起裝社區模組 → 自動排入安裝；排不進去就中止升級。

    工程水位 3.0 不再定義蓄水池與社區欄位；社區模組沒接手的話，升級結尾 Odoo 會把
    「已經沒人定義」的欄位刪掉（裝置與事件的蓄水池、場域的管委會），而且沒有提示、不可逆。

    為什麼是自動排入而不是直接中止：標準升級工具（tools/upgrade_databases.sh、CorPaaS）
    只會下 -u，不會加 -i community_water_level。中止的話核心會被打回未安裝，而磁碟上已是
    3.0 程式——容器一重啟，工程水位缺依賴被略過、construction_portal 跟著整串不載入。
    Odoo 的 load_marked_modules 每輪都重新查 state，這裡排入的模組會在同一次載入、
    _process_end 之前裝好（odoo/modules/loading.py load_marked_modules 的 while 迴圈）。
    """
    cr = env.cr
    if _module_state(cr, COMMUNITY_MODULE) in ('installed', 'to install', 'to upgrade'):
        return
    reasons = _community_data(cr)
    if not reasons:
        return
    module = env['ir.module.module'].search([('name', '=', COMMUNITY_MODULE)])
    if module:
        module.button_install()
    if _module_state(cr, COMMUNITY_MODULE) != 'to install':
        raise UserError(
            '這個資料庫有%s，但找不到可安裝的「社區水位」模組（%s）。'
            '2026-10-21 起社區水位是獨立專案 water-odoo，不在 ChienYi 這個 repo。'
            '直接升級會刪掉蓄水池與社區場域的欄位（不可逆），已中止：'
            '要保留社區資料就到裝得到社區模組的環境升級；確定不要，先刪掉社區資料再升級。'
            % ('、'.join(reasons), COMMUNITY_MODULE))
    _logger.warning('水位拆模組：這個庫有%s，已自動排入安裝 %s（否則升級結尾會刪掉社區欄位）',
                    '、'.join(reasons), COMMUNITY_MODULE)


def _community_data(cr):
    """庫裡現有的社區資料（給人看的描述清單）。沒有就回空清單。"""
    reasons = []
    if _table_exists(cr, 'water_level_tank'):
        cr.execute("SELECT count(*) FROM water_level_tank")
        tanks = cr.fetchone()[0]
        if tanks:
            reasons.append('%s 個蓄水池' % tanks)
    if _table_exists(cr, 'water_level_site'):
        cr.execute("SELECT count(*) FROM water_level_site WHERE site_type = 'community'")
        sites = cr.fetchone()[0]
        if sites:
            reasons.append('%s 個社區場域' % sites)
    return reasons


def move_ownership(cr, target):
    """把舊模組名下、歸 target 的 xmlid／約束／關聯表改掛到 target。回傳各搬了幾筆。"""
    cr.execute("SELECT id, name FROM ir_model_data WHERE module = %s", [OLD_MODULE])
    xmlid_ids = [row_id for row_id, name in cr.fetchall() if classify_xmlid(name) == target]
    if xmlid_ids:
        cr.execute("UPDATE ir_model_data SET module = %s WHERE id = ANY(%s)", [target, xmlid_ids])

    cr.execute("SELECT id FROM ir_module_module WHERE name = %s", [OLD_MODULE])
    old_row = cr.fetchone()
    cr.execute("SELECT id FROM ir_module_module WHERE name = %s", [target])
    target_row = cr.fetchone()
    moved = {'xmlid': len(xmlid_ids), 'constraint': 0, 'relation': 0}
    if not old_row or not target_row:
        return moved
    for table, key in (('ir_model_constraint', 'constraint'), ('ir_model_relation', 'relation')):
        cr.execute("SELECT id, name FROM %s WHERE module = %%s" % table, [old_row[0]])
        ids = [row_id for row_id, name in cr.fetchall() if classify_db_object(name) == target]
        if ids:
            cr.execute("UPDATE %s SET module = %%s WHERE id = ANY(%%s)" % table, [target_row[0], ids])
        moved[key] = len(ids)
    return moved


def pre_init_hook(env):
    cr = env.cr
    cr.execute("SELECT count(*) FROM ir_model_data WHERE module = %s", [OLD_MODULE])
    if not cr.fetchone()[0]:
        return  # 空庫安裝：沒有舊資料要接手

    ensure_community_module_scheduled(env)

    # 先記 cron 狀態（改名之前用舊模組名查）。只記會搬到核心的那些。
    cr.execute("""
        SELECT d.name, c.id, c.active, c.interval_number, c.interval_type
          FROM ir_cron c
          JOIN ir_model_data d ON d.res_id = c.id AND d.model = 'ir.cron'
         WHERE d.module = %s
    """, [OLD_MODULE])
    rows = [row for row in cr.fetchall() if classify_xmlid(row[0]) == CORE_MODULE]
    stash = {name: dict(zip(CRON_STASH_FIELDS, values)) for name, _cron_id, *values in rows}
    _lock_crons(cr, [row[1] for row in rows])

    moved = move_ownership(cr, CORE_MODULE)
    # 這幾筆在 XML 裡宣告為 noupdate，但舊庫的 ir_model_data 不一定標了（dev 實查有一支
    # cron 是 false）——沒標的話以後每次升級核心都會把它的啟用狀態蓋回 XML 預設值。
    cr.execute("""
        UPDATE ir_model_data SET noupdate = true
         WHERE module = %s AND model IN ('ir.cron', 'ir.actions.server', 'ir.sequence')
           AND (name LIKE 'cron_water_level%%' OR name = 'seq_water_level_event')
    """, [CORE_MODULE])
    _logger.info('水位拆模組：歸屬改掛到 %s：%s；記下 %s 個 cron 的狀態',
                 CORE_MODULE, moved, len(stash))
    if stash:
        env['ir.config_parameter'].sudo().set_param(CRON_STASH_PARAM, json.dumps(stash))


def _lock_crons(cr, cron_ids):
    """等線上正在執行的這幾支排程跑完，然後在本交易內鎖住它們的列。

    線上伺服器的排程器取工作時用 SKIP LOCKED，所以鎖住期間它只會先跳過這幾支；
    鎖在核心模組載入完 commit 時釋放（odoo/modules/loading.py 每個模組 commit 一次）。
    等超過 CRON_LOCK_TIMEOUT 就讓升級失敗，訊息會說是在等排程。
    """
    if not cron_ids:
        return
    cr.execute("SELECT current_setting('lock_timeout')")
    previous = cr.fetchone()[0]
    cr.execute("SELECT set_config('lock_timeout', %s, true)", [CRON_LOCK_TIMEOUT])
    try:
        cr.execute("SELECT id FROM ir_cron WHERE id = ANY(%s) FOR NO KEY UPDATE", [cron_ids])
    except Exception as exc:
        raise UserError('水位拆模組：等了 %s 仍有水位排程在執行，無法鎖定（%s）。請稍後重跑升級。'
                        % (CRON_LOCK_TIMEOUT, exc)) from exc
    cr.execute("SELECT set_config('lock_timeout', %s, true)", [previous])


def post_init_hook(env):
    Param = env['ir.config_parameter'].sudo()
    raw = Param.get_param(CRON_STASH_PARAM)
    if not raw:
        return
    for name, vals in json.loads(raw).items():
        cron = env.ref('%s.%s' % (CORE_MODULE, name), raise_if_not_found=False)
        if not cron:
            _logger.warning('水位拆模組：找不到 cron %s.%s，無法還原狀態 %s', CORE_MODULE, name, vals)
            continue
        changed = {k: v for k, v in vals.items() if cron[k] != v}
        if changed:
            cron.write(changed)
            _logger.info('水位拆模組：cron %s 還原為升級前狀態 %s', name, changed)
    # 參數用完即刪：留著的話，下次有人重裝核心會拿一份過期狀態去蓋現況
    Param.search([('key', '=', CRON_STASH_PARAM)]).unlink()
