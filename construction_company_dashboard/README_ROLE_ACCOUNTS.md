# 受限帳號 runbook（公司儀表板 S3，2026-11-11）

給要對某個站「降版、回退、解除安裝公司儀表板、上 S3」的人。指令裡的 `<DB>` 換成那個站的資料庫名；
帳密不要寫進指令列歷史（用環境變數或互動輸入）。

「受限帳號」＝讀取範圍被本模組（`rule_scope`）收窄的帳號：營造廠主管、控台讀取、後台角色帳號（營造老闆／營造主管／
監造老闆／監造主管），以及**前台營造帳號**。本模組一旦不見（解除安裝、降版到沒有這些程式的版本），
它們的範圍限制就跟著不見：內部帳號只剩隱含的「內部使用者」＝看得到整家公司；前台營造帳號回到
「Portal 老闆 (1=1)」看整家監造公司（跨營造廠）。

## 1. 列出受限帳號（唯一清單）

hook 與本 runbook 用這個函式：`res.users.dash_restricted_account_logins()`（`models/restricted_accounts.py`）。
換版工具 `tools/qytech_deploy/qd.py` 的降版硬擋改成呼叫它，是**換版 session 的待辦**；在那之前 qd.py 仍自己查群組
（只看啟用中的內部帳號，不含前台營造帳號與已封存的），降版前請另外手動跑本節。

- 只有系統管理者能呼叫，其他人一律 AccessError；唯讀。
- 回傳 `{'internal': [login, …], 'portal': [login, …]}`：`res.users._dash_is_restricted()`（全系統唯一一份判斷，含前台營造帳號）
  為真的帳號，各含啟用中與**已封存**的，依 login 排序；前台（share）在 portal、其餘在 internal；超級使用者排除。
- **fail-closed**：判斷函式靠 5 個受限群組（`group_contractor_manager`、`group_console_reader`、`group_role_boss`、
  `group_role_manager`、`group_role_supervision`，`models/res_users_guard.py` 的 `CARRIER_GROUP_XMLIDS`）認人；任一個的 xmlid
  找不到（半套解除安裝、手動刪）就 UserError「受限群組定義不完整，無法確認受限帳號」，不回殘缺的清單。先把群組資料修好再列。

odoo shell（本機 dev 或站上容器裡，一行）：

```bash
echo "print(env['res.users'].dash_restricted_account_logins()); env.cr.rollback()" \
  | docker exec -i odoo18 odoo shell -c /etc/odoo/odoo.conf -d <DB> --no-http --log-level=warn
```

RPC（系統管理者帳號；密碼從環境變數讀，不要打在指令列）：

```bash
python3 -c "import os,xmlrpc.client as x; u='https://<站>'; db='<DB>'; who=os.environ['ODOO_LOGIN']; pw=os.environ['ODOO_PASSWORD']; uid=x.ServerProxy(u+'/xmlrpc/2/common').authenticate(db,who,pw,{}); print(x.ServerProxy(u+'/xmlrpc/2/object').execute_kw(db,uid,pw,'res.users','dash_restricted_account_logins',[]))"
```

## 2. 回退、降版、解除安裝之前

**清單（含已封存）必須是空的。** 不空時：

- 解除安裝：`uninstall_hook` 直接拒絕（UserError 會列出兩段 login 與本檔路徑），不會替人封存；清單本身 UserError（群組定義不完整）也拒絕。
- 降版：**換版 session 待辦**——qd.py 的 `downgrade_block` 改成「先判斷有沒有降版，有才呼叫本函式；清單非空或呼叫失敗一律擋」之後，
  才會自動擋。在那之前請手動跑第 1 節，清單（含已封存）為空才降版。

逐一處置：

| 帳號 | 處置 |
|---|---|
| 後台角色帳號（`demo_role_*` 這類，內部） | 使用者表單 → 動作 →「改回前台角色帳號」（S2 的伺服器動作，同一個 user id 逐欄寫回轉換前設定、清掉 `dash_role_origin`）。改回後若是**營造方**前台帳號，仍會列在 portal（見下一列）；監造方改回後不再列出。 |
| 營造廠主管、控台讀取（內部） | 移除載體群組並清掉範圍公司（等於收回這個帳號的身分，先跟使用者確認），或刪除帳號。**只封存不夠**（見下）。 |
| 前台營造帳號（portal） | 沒有安全的「轉換」：拿掉營造標記等於把它變成另一種帳號。實務上**只要庫裡還有營造廠前台帳號，儀表板模組就不能解除安裝**——這是刻意的。真的要拆，先和使用者確認每個帳號要刪除或改成監造方。 |
| 已封存的受限帳號 | 照它原本的種類處置（上面三列）；**只封存不夠**（見下）。 |

**為什麼只封存不夠**：清單含已封存的帳號，所以封存之後 hook（與之後的 qd.py）照樣擋。這樣擋是對的——限制它的群組、規則與
`rule_scope` 都屬於本模組，解除安裝或降版後它們全都不在了；之後只要有人把這個帳號解封，它就是一個看得到整家公司的內部帳號
（前台營造帳號則看整家監造公司），而且沒有任何東西會再提醒。封存只是「現在登不進來」，不是「這個帳號不再受限」。

**放行條件：清單（含已封存）為空。** 處置完再跑一次第 1 節，確認 `{'internal': [], 'portal': []}`。

### hook 拒絕之後（已知副作用；S3 fix1 依核心原始碼更正）

- hook 在核心刪模組資料之前執行（`odoo/modules/loading.py` STEP 5），raise 會讓**這次解除安裝**回滾。
- 載入失敗時核心呼叫 `reset_modules_state()`（`odoo/modules/registry.py` 的 `Registry.new` → `loading.py` `reset_modules_state`），
  把「待解除安裝」「待升級」一律改回「已安裝」：**只失敗這一次**，模組不會卡在待解除安裝，之後的 `-u` 不會因為這道檢查失敗，
  也沒有「取消解除安裝」要按。
- 同一輪若也升級了其他模組：各模組的資料在載入時**逐模組 commit**（`loading.py` 每個模組載完 `env.cr.commit()`），
  但每個模組的「已安裝＋新版本號」標記是在它自己 commit **之後**才寫、要等下一個模組 commit 才落地
  ——所以**最後一個**被升級的模組，資料已寫入、版本標記被回滾（`latest_version` 停在舊版，`check_schema_sync`／qd.py 會判它落後）。
  處理完帳號後再跑一次那個模組的 `-u`。

## 3. 上 S3 之前各站要查（換版 precheck 也會擋）

S3 在 18 個模型（估驗、請款、計量驗收、非契約工項、契約變更、預定進度、進度報告、即時損益、損益支出、工項版本、
工項分析）加了**全域公司規則**：紀錄所屬工程的公司要在使用者目前選取的公司裡。工程公司空白不放行。
讀取、刪除、建立由規則擋；寫入另由寫後檢查擋（改掛到別家公司的工程／父單、把有工程的估驗／變更單改成工程空白都會被拒，
`construction_supervision_base/models/company_rule_write_guard.py`）。

```sql
-- (1) 必須是 0：工程公司空白的工程，底下的估驗等會對所有非 sudo 的人消失（沒有錯誤訊息，列表就是空的）
SELECT count(*) FROM project_project WHERE company_id IS NULL;

-- (2) 前台成員：參與的工程，其公司不在帳號允許公司裡（上 S3 後讀不到該工程的估驗等；核心工程規則本來就要求同一件事）
SELECT u.login, p.code, p.company_id
FROM supervision_project_member m
JOIN res_users u ON u.id = m.user_id
JOIN project_project p ON p.id = m.project_id
WHERE u.active
  AND NOT EXISTS (SELECT 1 FROM res_company_users_rel r WHERE r.user_id = u.id AND r.cid = p.company_id);

-- (2b) 前台老闆（group_portal_subscriber）：前台列工程是 sudo、全庫都列（一庫一公司的設計），之後「以本人身分再過一次 ir.rule」，
--      上 S3 後只剩允許公司裡的工程讀得到估驗等。列出「有工程、但不在老闆允許公司裡」的公司（多公司庫 jt 會列很多，確認是不是預期）
SELECT u.login, c.id AS company_id, c.name AS company
FROM res_users u
JOIN res_groups_users_rel g ON g.uid = u.id
JOIN ir_model_data d ON d.model = 'res.groups' AND d.res_id = g.gid
     AND d.module = 'construction_supervision_base' AND d.name = 'group_portal_subscriber'
CROSS JOIN (SELECT DISTINCT company_id FROM project_project WHERE active) pc
JOIN res_company c ON c.id = pc.company_id
WHERE u.active AND u.share
  AND NOT EXISTS (SELECT 1 FROM res_company_users_rel r WHERE r.user_id = u.id AND r.cid = pc.company_id)
ORDER BY 1, 2;

-- (3) 工程後台使用者／代操作員：有工程的公司裡，哪些不在他的允許公司（上 S3 後他看不到那些公司的估驗等——確認是不是預期）
SELECT u.login, c.id AS company_id, c.name AS company
FROM res_users u
JOIN res_groups_users_rel g ON g.uid = u.id
JOIN ir_model_data d ON d.model = 'res.groups' AND d.res_id = g.gid
     AND d.module = 'construction_supervision_base' AND d.name = 'group_supervisor_admin'
CROSS JOIN (SELECT DISTINCT company_id FROM project_project WHERE active) pc
JOIN res_company c ON c.id = pc.company_id
WHERE u.active AND NOT u.share AND u.id <> 1
  AND NOT EXISTS (SELECT 1 FROM res_company_users_rel r WHERE r.user_id = u.id AND r.cid = pc.company_id)
ORDER BY 1, 2;

-- (4) 參考：工程公司以外的工項公司空白（核心工項規則放行公司空白；S3 只對工項版本與工項分析以工程公司為準）
SELECT count(*) FILTER (WHERE t.active) AS active_blank, count(*) AS all_blank
FROM project_task t WHERE t.company_id IS NULL AND t.project_id IS NOT NULL;
```

(1) 不是 0 就不准上，先替那些工程補公司。(2)(2b)(3) 有列出來的，先確認是不是預期（多公司庫 jt 最要緊）。

## 4. 已知限制

- **兩步驟驗證目前不強制**：使用者 11-11 暫定（`res_users_guard.DASH_REQUIRE_TOTP = False`）；改回 True 即恢復。
- **受限內部帳號的程式介面只收 API key**（S2 fix3，使用者 11-11）：營造廠主管、後台角色帳號、控台讀取走 XML-RPC（`/xmlrpc/2`）、
  JSON-RPC（`/jsonrpc`）用密碼一律被拒（`res_users_guard._rpc_api_keys_only`，與核心對「開了 TOTP 的帳號」同一個機制）；
  瀏覽器、手機登入照常只要密碼，不要求開兩步驟驗證。要讓這些帳號跑程式（例：控台拉資料）就替它在偏好設定建一把 API key
  （dev 的 `console_reader` 本來就是用 API key）。上站前若有人用這類帳號＋密碼跑腳本，換版後會登入失敗——先查、改用 API key。
- **意見回饋的讀取權（ACL）是升級本模組時建的**（`res_users_guard._dash_sync_feedback_acl`，`data/feedback_acl.xml`）：
  本模組不依賴 construction_helpdesk，所以**之後才裝 construction_helpdesk 的庫，要再 `-u construction_company_dashboard` 一次**，
  監造方角色帳號才讀得到自己的客服單（沒做：入口看得到、建單後列表是空的）。
- 意見回饋是角色帳號「後台唯讀」原則下的寫入例外（使用者 11-11）：前台建單、在自己的單上留言、驗證（問題已解決／仍有問題），
  三個都只限本人的單；ORM／RPC 直接寫照舊全拒（`construction_helpdesk/models/service_ticket.py` `_role_feedback_allowed`）。
- **A 的規則所在模組降版會把洞放回來**：18 條規則分在 construction_payment、construction_contract_change、construction_progress、
  construction_general、construction_supervision_base 的 `security/company_rules.xml`（noupdate＝0）。任一個降版到 S3 之前的版本，
  `-u` 會把它那幾條規則刪掉，公司隔離的洞回來、沒有任何 log（red-team F2）。qd.py 目前不擋這種降版（待使用者決定）；
  控台「下載」、NAS 手動換包不經 qd.py。
- 切換器只選一家公司是**介面慣例，不是安全邊界**：不帶 `allowed_company_ids` 的路徑（RPC、報表下載、排程以該使用者身分跑）
  看的是帳號全部允許公司。要硬隔離，就不要讓一個帳號同屬兩家公司（red-team F8）。
- S3 只做**公司隔離**，不做工程隱私：同公司的人讀得到「只限追蹤者」工程底下的估驗（現況就如此）。
- 工程空白的估驗、變更單（與其明細）只有**建立者**看得到。建立者是 OdooBot 或已封存的人時，只有 sudo／SQL 處理得到
  （dev 的 contract.change.order id=27 就是工程空白的草稿）。有工程的估驗、變更單不能再改成工程空白，變更明細也不能改掛到
  沒有工程的變更單（S3 fix1，非 sudo 一律 UserError；建立者自己也一樣）。
- 工項版本掛在「沒有工程的工項」（私人任務）時規則放行所有人（定案表 #17）；把工項版本改掛到這種工項不會被寫後檢查擋。
- 受限帳號清單是 fail-closed：受限群組 xmlid 不完整時函式直接 UserError（見第 1 節），不會回一份漏人的清單。
