# 線 A1：讀取範圍與拒寫、營造廠歸屬、監造方不變
from . import test_scope_rules
from . import test_attribution
from . import test_supervision_unchanged
# 線 A1'：帳號設定、選單允許清單
from . import test_account_setup
from . import test_menu_allowlist
# 線 B：工作天、指標
from . import test_workday
from . import test_dashboard_indicators
# 線 C：後台畫面
from . import test_dashboard_views
# 線 D：前台公司儀表板、前台審核按鈕隱藏
from . import test_portal_dashboard
# 線 E：控台取資料方法
from . import test_console_overview
# 線 F1：RPC 呼叫路徑（覆寫保留 _api）
from . import test_rpc_dispatch
# 線 F1：合約 §0b-20（檢試驗預警歸工程層級、營造方藏入口）
from . import test_contract_0b20
# 線 F1：範本使用者加群組不推給受限帳號（合約 §10 F 列的風險）
from . import test_template_groups
# 主迴圈 11-06：呼叫端自帶的 context 旗標不能打開範圍規則
from . import test_context_spoof
# 主迴圈 11-06：本庫主公司不算營造廠（新庫 1 號公司預設是施工廠商）
from . import test_main_company_not_contractor
# 線 H：呼叫端給的關聯 id 不能拿來以 sudo 讀資料（11-06 抗辯 F1–F6、F9，各種帳號）
from . import test_relational_input_guard_roles
# 線 I：受限帳號收回能力（精靈、自訂方法閘門、公開頻道、內部備註、共用篩選、回填、歸屬約束；合約 §0b-24～26）
from . import test_restricted_capabilities
from . import test_method_gate_http
from . import test_invited_docs  # 合約 §0b-29 受邀協作
from . import test_company_type_choice  # 合約 §0b-30 新建公司必選類型
# 主迴圈 11-06：「儀表板」App 的兩個入口（合約 §0b-32）
from . import test_spreadsheet_dashboard
