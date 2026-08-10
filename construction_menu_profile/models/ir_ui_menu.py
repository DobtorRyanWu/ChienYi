# -*- coding: utf-8 -*-
"""後台選單設定檔 —— 唯一的「哪些選單要關掉」清單。

清單依 2026-08-10 使用者確認的「預期看到的選單」整理。要把某個選單開回來，
把對應那一行刪掉再 `-u construction_menu_profile` 即可；只在後台勾回 active
是撐不住的——下次升級 `<function>` 會重新套用整份設定檔（這是刻意的，
讓「預設關閉」在每個站台都是一致狀態）。
"""

import logging

from odoo import api, models

_logger = logging.getLogger(__name__)

# 只需列**父層**。Odoo 的 load_menus 從 root 遞迴建樹，父層 active=False 之後
# 它的子選單找不到父節點，整支自然不會出現，不必逐一列出子項。
# 格式：(xml_id, 顯示位置說明, 連帶消失的子項數)
MENUS_OFF = [
    # ---------------------------------------------------------------
    # Odoo 原生／第三方（2026-08-10 使用者點名關閉的 4 個）
    # 討論 / 待辦事項 / Dashboards / 員工 / 測試 依使用者決定**保留**；
    # 應用程式(base.menu_management) 與 設定(base.menu_administration)
    # 絕對不能關，關了就無法管理系統。
    # ---------------------------------------------------------------
    ('contacts.menu_contacts', '頂層 App「聯絡人」', 0),
    ('maintenance.menu_maintenance_title', '頂層 App「保養」', 0),
    ('base_geoengine.geoengine_base_menu', '頂層 App「GeoEngine Backend」', 4),
    # dobtor_spreadsheet_editor.menu_xlsx_import 掛在這支底下，父關即消失
    ('spreadsheet_oca.spreadsheet_spreadsheet_menu', '頂層 App「Spreadsheets」', 1),

    # ---------------------------------------------------------------
    # 本專案：整支關掉的頂層 App
    # ---------------------------------------------------------------
    ('construction_supervision_base.menu_acceptance_root', '頂層 App「驗收結案」', 12),
    ('construction_supervision_base.menu_standard_work_item_root', '頂層 App「標準工項管理」', 0),

    # ---------------------------------------------------------------
    # 工程管理
    # ---------------------------------------------------------------
    ('construction_supervision_base.menu_resource_management', '工程管理 > 資源管理', 7),
    ('construction_supervision_base.menu_reports', '工程管理 > 報表（原為 group_no_one）', 3),
    ('construction_timeline.menu_schedule_analysis', '工程管理 > 進度管理 > 時程分析', 4),
    ('construction_progress.menu_progress_chart_graph',
     '工程管理 > 進度管理 > 進度曲線圖(標準)（原為 group_no_one）', 0),
    # 機具設備／維護請求：2026-08-10 使用者確認關閉。連帶把施工日誌人機明細的
    # 「機具設備」欄改回自由文字（見 construction_equipment 18.0.1.3.0），
    # 否則那個關聯欄會挑不到任何資料。
    ('construction_equipment.menu_equipment_list', '工程管理 > 人機管理 > 機具設備', 2),
    ('construction_equipment.menu_equipment_maintenance', '工程管理 > 人機管理 > 維護請求', 3),

    # ---------------------------------------------------------------
    # 檔案管理
    # ---------------------------------------------------------------
    ('construction_meeting_record.menu_construction_meeting_record',
     '檔案管理 > 文件管理 > 會議記錄', 0),

    # ---------------------------------------------------------------
    # 施工執行
    # ---------------------------------------------------------------
    ('construction_daily_log.menu_daily_log_config', '施工執行 > 施工日誌 > 設定', 2),
    ('construction_supervision_base.menu_timesheet_management', '施工執行 > 工時管理', 2),

    # ---------------------------------------------------------------
    # 計價請款
    # ---------------------------------------------------------------
    # 空殼選單（無 action 無子項），與 construction_cost_analysis.menu_cost_analysis
    # 撞名。Odoo 本來就不會顯示它，明確關掉是為了避免日後查選單時誤判。
    ('construction_supervision_base.menu_cost_analysis',
     '計價請款 > 成本分析（空殼，真正有 action 的是 construction_cost_analysis 那支）', 0),

    # ---------------------------------------------------------------
    # 系統設定
    # ---------------------------------------------------------------
    ('construction_supervision_base.menu_equipment_config', '系統設定 > 設備設定', 2),
    ('construction_supervision_base.menu_basic_config', '系統設定 > 基礎設定', 1),
    ('construction_supervision_base.menu_audit_config', '系統設定 > 稽核管理', 4),
]

# 這些在各自模組裡已經是 active=False，不重複處理，列在這裡只為了讓
# 「後台看不到的東西」有完整交代：
#   construction_timeline.menu_task_timeline           工程管理 > 進度管理 > 工項時程
#   construction_partner.menu_technical_contacts       工程管理 > 資源管理 > 技術聯絡人
#   construction_supervision_base.menu_claim           計價請款 > 請款管理
#   construction_daily_log.menu_daily_log_lines        施工日誌 > 設定 > 日誌明細
#   construction_daily_log.menu_daily_log_weather      施工日誌 > 設定 > 天氣記錄
#   project.menu_main_pm                               頂層 App「專案」
#   hr_timesheet.timesheet_menu_root                   頂層 App「工時表」


class IrUiMenu(models.Model):
    _inherit = 'ir.ui.menu'

    @api.model
    def _apply_chienyi_menu_profile(self):
        """套用 MENUS_OFF。由 data/menu_profile.xml 的 <function> 在每次
        install / upgrade 呼叫。"""
        turned_off, missing = [], []
        for xml_id, label, _children in MENUS_OFF:
            menu = self.env.ref(xml_id, raise_if_not_found=False)
            if not menu:
                # 該模組沒裝（或 xml_id 改名）→ 略過，不讓升級中斷
                missing.append(xml_id)
                continue
            if menu.active:
                menu.active = False
                turned_off.append('%s（%s）' % (xml_id, label))

        if turned_off:
            _logger.info('選單設定檔：關閉 %d 個選單\n  %s',
                         len(turned_off), '\n  '.join(turned_off))
        if missing:
            _logger.warning('選單設定檔：找不到這些 xml_id，已略過 → %s',
                            ', '.join(missing))
        return True
