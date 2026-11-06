# -*- coding: utf-8 -*-
"""受限帳號的自訂方法閘門：判定（合約 §0b-24；線 I）。呼叫路徑的攔截在 controllers/method_gate.py。

受限帳號＝ir.rule._dash_scope_kind() 不為 None：營造方（後台營造廠主管、前台營造帳號）與控台讀取帳號。
營造廠主管與控台讀取帳號隱含 base.group_user，於是繼承了內部帳號「從外部呼叫每個自訂模組公開方法」的路徑；
這些方法裡常以 sudo 讀寫（ir.rule 擋不到，11-06 抗辯：資料夾上傳精靈改掛任意附件），逐一檢查一定會漏，
所以把能力拿掉（judgment-rubrics L4：多加一道檢查不如把能力拿掉）：

外部呼叫的方法，只要**模型類別 MRO 上任何一層定義了這個名稱的類別**來自自訂模組（CORE_ADDONS_DIR 之外），就拒絕。例外：
* ORM_READ_API：ORM 的讀取／介面 API（名稱照放行）。
* ORM_WRITE_API：寫建刪的名稱照放行，交給拒寫規則（rule_scope）拒。
* DASHBOARD_METHODS：儀表板自己的方法，(模型, 方法) 逐一列。
只由 Odoo 官方模組實作的方法不經過這道閘門（照原本的 ACL 與規則；例：啟用兩步驟驗證、改密碼、建 API 金鑰）。
伺服器動作（/web/action/run、ir.actions.server.run）是第四條路，另見 server_action_gate.py。
監造方與其他帳號完全不受影響。
"""
import functools
import logging
import os

import odoo
from odoo.exceptions import AccessError
from odoo.modules.module import get_module_path

_logger = logging.getLogger(__name__)

# 「核心」＝Odoo 官方發行版的模組，全部在 odoo 套件目錄的 addons/ 下（容器 /usr/lib/python3/dist-packages/odoo/addons，
# 含 base、web、mail、auth_totp）。本專案模組在 /mnt/extra-addons（construction_*、dobtor_*、water_level_*…），
# 第三方在 /mnt/3rd-party-addons（uptime_monitor、base_geoengine、spreadsheet_oca…），都不在這裡 → 自訂。
# 以來源目錄判定、不用名稱前綴：之後新裝的任何非官方模組自動落在閘門內（預設拒絕，同 §0b-1 的精神）。
CORE_ADDONS_DIR = os.path.realpath(os.path.join(os.path.dirname(odoo.__file__), 'addons'))
ADDON_PACKAGE_PREFIX = 'odoo.addons.'

# ORM 的讀取／介面 API：自訂模組常覆寫它們（加欄位、改預設值；base_geoengine 對每個模型覆寫 fields_get），
# 但它們只讀資料、受 ACL 與 ir.rule 管，後台每一頁都要用。
ORM_READ_API = frozenset({
    # 經典讀取 API（XML-RPC 用戶端、控台拉資料）
    'read', 'search', 'search_read', 'search_count', 'name_search', 'read_group',
    # 18.0 web client 的清單／表單／看板／分組讀取
    'web_search_read', 'web_read', 'web_read_group', 'read_progress_bar',
    # 搜尋面板
    'search_panel_select_range', 'search_panel_select_multi_range',
    # 畫面定義、新紀錄預設值、表單的 onchange（偏好設定、啟用兩步驟驗證的表單都會叫；
    # onchange 帶範圍外 id 讀 sudo 值由線 H 的守衛擋，合約 §0b-23）
    'fields_get', 'get_views', 'default_get', 'onchange',
    # 權限查詢（只回准不准）
    'check_access', 'has_access', 'check_access_rights', 'check_access_rule',
})
# 寫建刪的入口名稱：照放行，交給拒寫規則（rule_scope：受限帳號對業務模型寫建刪一律拒，精靈只留帳號自助）。
# copy、action_archive 這類「會寫但不是寫建刪名稱」的，自訂模組覆寫時一樣被閘門拒（核心實作照舊走規則）。
ORM_WRITE_API = frozenset({'create', 'write', 'unlink', 'web_save', 'name_create'})
# 儀表板自己的方法（方法內以看的人的權限計算，或先查群組／check_access）
DASHBOARD_METHODS = frozenset({
    ('project.project', 'get_dash_company_kpis'),       # 公司儀表板看板的公司合計（company_dashboard_kanban.js）
    ('project.project', 'action_dash_drilldown'),       # 看板卡片下鑽（同上；先 check_access 再回動作）
    ('project.project', 'get_project_dashboard_data'),  # 單一工程頁（progress_dashboard.js、progress_dashboard_patch.js；先 check_access）
    ('project.project', 'get_progress_chart_data'),     # 進度表圖表（progress_chart.js、progress_dashboard.js；以本人身分讀進度表）
    ('project.project', 'dash_console_overview'),       # 控台取資料（合約 §8.1；非控台讀取帳號一律 AccessError）
    # 更新公告（construction_release，後台啟動時叫）：讀已發布公告；按「知道了」只把呼叫者自己加進已讀名單（release.py:422-436）
    ('construction.release', 'get_startup_notices'),
    ('construction.release', 'mark_announcements_read'),
})
# 被拒訊息的開頭（測試與 rpc_scope_check 用它認「是閘門擋的」）
GATE_NOTE = '公司儀表板方法閘門'


def _addon_of(cls):
    """類別所屬的 Odoo 模組名；不在 odoo.addons 底下（odoo.models 等 Odoo 本體）回 None。"""
    name = getattr(cls, '__module__', '') or ''
    if not name.startswith(ADDON_PACKAGE_PREFIX):
        return None
    return name[len(ADDON_PACKAGE_PREFIX):].split('.', 1)[0]


@functools.lru_cache(maxsize=None)
def is_custom_module(module):
    """模組來源不在 CORE_ADDONS_DIR 底下＝自訂；找不到來源也當自訂（拒絕方向）。"""
    path = get_module_path(module, display_warning=False)
    if not path:
        return True
    return not os.path.realpath(path).startswith(CORE_ADDONS_DIR + os.sep)


def custom_implementations(model_class, method):
    """模型類別 MRO 上「定義了 method 的類別」之中來自自訂模組的模組名（MRO 順序、不重複）。"""
    modules = []
    for cls in model_class.mro():
        if method in vars(cls):
            module = _addon_of(cls)
            if module and is_custom_module(module) and module not in modules:
                modules.append(module)
    return modules


def gate_verdict(env, model_name, method):
    """env.user 呼叫 model_name.method 會不會被閘門拒：拒回自訂實作的模組清單，放行回空清單。"""
    if env.su or not isinstance(model_name, str) or not isinstance(method, str):
        return []
    if not env['ir.rule']._dash_scope_kind():
        return []                       # 監造方與其他帳號：不受影響
    if method in ORM_READ_API or method in ORM_WRITE_API or (model_name, method) in DASHBOARD_METHODS:
        return []
    model_class = env.registry.get(model_name)
    if model_class is None:
        return []                       # 模型不存在：交給核心報錯
    return custom_implementations(model_class, method)


def check_method_call(env, model_name, method, via):
    """閘門：受限帳號呼叫自訂實作的方法 → 記 WARNING 並丟 AccessError；其他情況不做事。"""
    modules = gate_verdict(env, model_name, method)
    if not modules:
        return
    user = env.user
    _logger.warning('%s擋下：帳號 %s（id %s）經 %s 呼叫 %s.%s（自訂模組 %s 實作）',
                    GATE_NOTE, user.login, user.id, via, model_name, method, '、'.join(modules))
    description = env[model_name]._description or model_name
    raise AccessError(
        f'{GATE_NOTE}：您的帳號是唯讀的營造廠／控台讀取帳號，不能執行「{description}」的「{method}」'
        f'（{model_name}.{method}）。這個操作限監造單位使用，如有需要請洽監造單位。')
