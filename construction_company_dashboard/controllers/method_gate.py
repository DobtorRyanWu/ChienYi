# -*- coding: utf-8 -*-
"""受限帳號的自訂方法閘門：攔截外部呼叫路徑（合約 §0b-24；判定在 models/method_gate.py）。

用 Odoo 正常的 controller 繼承（不 monkeypatch 核心），蓋住三條「外部指定模型與方法名」的入口：
1. `/web/dataset/call_kw*`、`/web/dataset/call_button*`（web client；核心 web/controllers/dataset.py）
2. XML-RPC `/xmlrpc/<service>`、`/xmlrpc/2/<service>` 的 object 服務（核心 base/controllers/rpc.py：
   兩條路由都經過 self._xmlrpc() → dispatch_rpc，覆寫 _xmlrpc）
3. JSON-RPC `/jsonrpc` 的 object 服務（同檔 jsonrpc 路由）

**蓋不到的情況（已知限制，寫給部署的人）**：一般模組的 controller 只在「這次請求選到的庫」的路由表裡。
XML-RPC／JSON-RPC 沒有 session，選庫靠 dbfilter：只對到一個庫（mono-db，本專案「一監造公司一庫」的部署）時
路由表是那個庫的、閘門有效；dbfilter 對到兩個以上的庫時請求走 nodb 路由表，只有 server-wide 模組的 controller
（例 rpc_dbfilter_guard）在裡面，這道閘門**不會執行**——要在那種部署擋，得把這個 controller 做成 server-wide 模組。
web client 的 call_kw 一定帶 session 的庫，不受影響。

XML-RPC 的身分在核心 dispatch 裡才驗（security.check）。這裡先以 uid 判定；要拒絕時**先驗帳密**再拒
（帳密錯照核心回 AccessDenied，不讓沒登入的人拿它探測哪個 uid 是受限帳號），放行時不多驗一次（不加成本）。
"""
import xmlrpc.client

from odoo import api, http
from odoo.addons.base.controllers.rpc import RPC, _check_request
from odoo.addons.web.controllers.dataset import DataSet
from odoo.http import request
from odoo.modules.registry import Registry
from odoo.service import security

from ..models.method_gate import check_method_call, gate_verdict

# object 服務指定模型與方法的兩個 RPC 方法（odoo/service/model.py dispatch）與它們的前五個參數
OBJECT_RPC_METHODS = frozenset({'execute', 'execute_kw'})
OBJECT_PARAMS_HEAD = 5      # (db, uid, password, model, method)


def gate_object_rpc(rpc_method, params, via):
    """object 服務（XML-RPC／JSON-RPC）的閘門；參數形狀不對就不管（交給核心報錯）。"""
    if rpc_method not in OBJECT_RPC_METHODS or not isinstance(params, (list, tuple)) \
            or len(params) < OBJECT_PARAMS_HEAD:
        return
    db, uid, passwd, model, method = params[:OBJECT_PARAMS_HEAD]
    if not (isinstance(db, str) and isinstance(model, str) and isinstance(method, str)):
        return
    try:
        uid = int(uid)
    except (TypeError, ValueError):
        return
    # dbfilter 以外的庫不開它的 registry（rpc_dbfilter_guard 會拒；這裡不能替它先載入）
    if not http.db_filter([db]):
        return
    registry = Registry(db)
    if not hasattr(registry.get('ir.rule'), '_dash_scope_kind'):
        return                          # 那個庫沒裝本模組
    # 只讀：判定不寫任何東西（另開唯讀 cursor；身分驗證在 cursor 之外，核心自己開 cursor）
    with registry.cursor(readonly=True) as cr:
        env = api.Environment(cr, uid, {})
        if not env['res.users'].sudo().browse(uid).exists():
            return                      # 核心會拒（帳號不存在）
        if not gate_verdict(env, model, method):
            return
    security.check(db, uid, passwd)     # 帳密錯 → AccessDenied（與核心相同的回應）
    with registry.cursor(readonly=True) as cr:
        check_method_call(api.Environment(cr, uid, {}), model, method, via)


class DashDataSet(DataSet):

    @http.route()
    def call_kw(self, model, method, args, kwargs, path=None):
        check_method_call(request.env, model, method, '/web/dataset/call_kw')
        return super().call_kw(model, method, args, kwargs, path=path)

    @http.route()
    def call_button(self, model, method, args, kwargs, path=None):
        check_method_call(request.env, model, method, '/web/dataset/call_button')
        return super().call_button(model, method, args, kwargs, path=path)


class DashRPC(RPC):

    def _xmlrpc(self, service):
        if service == 'object':
            params, method = xmlrpc.client.loads(request.httprequest.get_data(), use_datetime=True)
            gate_object_rpc(method, params, 'XML-RPC')
        return super()._xmlrpc(service)

    @http.route()
    def jsonrpc(self, service, method, args):
        if service == 'object':
            # 先放掉這次請求的 cursor（核心 jsonrpc 第一步也是這個；_xmlrpc 的路由在呼叫它之前就做了）
            _check_request()
            gate_object_rpc(method, args, 'JSON-RPC')
        return super().jsonrpc(service, method, args)
