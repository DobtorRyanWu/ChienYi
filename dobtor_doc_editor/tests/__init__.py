from . import test_zip_guard
from . import test_versions
from . import test_doc_linked_mixin
from . import test_security
from . import test_jinja_sandbox
from . import test_ssti_render
from . import test_collision
from . import test_controllers
from . import test_optimistic_lock
from . import test_telemetry
from . import test_bulk_import
from . import test_template_autofill
from . import test_font_serve  # Sprint 66 — Sprint 64b font_serve backend tests
from . import test_template_field  # Phase 8 ADR-022 — doc.template.signer/field
from . import test_portal_home_counter  # /my 首頁 doc_count counter 權限保護
from . import test_available_fields_access
from . import test_manual_fixes_20261102  # 版本訊息 Markup、B25 預設篩選（2026-11-02）
from . import test_portal_protected_fields  # 前台協作者不能改別名運算式、樣板檔、綁定對象、協作者（2026-11-04）
from . import test_internal_expression_sandbox  # 預覽別名與套印 docx 改用加固沙箱（內部編輯者不能經運算式提權／執行程式）
from . import test_render_field_groups  # 匯出沙箱要守欄位 groups（TOTP 金鑰）
from . import test_export_log_portal  # 前台帳號讀不到匯出紀錄（2026-11-16）
from . import test_doc_sanitizer  # 文件內容不能帶會執行的 HTML／canvas 區塊（doc.sanitizer 失效修補，2026-11-17）
from . import test_followups_20261125  # 大文件附件權限（I1）、版本備註（I2）（2026-11-25）
