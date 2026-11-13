-- 上 S4 之前各站要查（全部唯讀）。說明在 ../README_ROLE_ACCOUNTS.md §3b。
-- 用法：psql -d <DB> -At -F ' | ' -f construction_company_dashboard/runbook/s4_precheck.sql
--
-- 每一段用「-- [段名]」與「-- [/段名]」包起來：tests/test_company_isolation.py 的
-- test_s4_precheck_sql_covers_every_rule_model 會在測試庫實跑 [S4-1] 那一段，要求每個 S4 規則模型
-- （SQL 檢視除外）恰好一列、第一欄＝那個模型的資料表名——新增或拿掉規則模型時，這裡沒跟著改就會紅。

-- [S4-1]
-- 必須全部是 0：所屬工程空白、或工程公司空白的紀錄（規則 fail-closed，上 S4 後非 sudo 的人全部看不到）。
-- 路徑與規則相同（子表沿規則用的那個欄位）。「工程空白放行」的四種（檢試驗項目、頻率條件、資料夾、工程文件）與工項
-- 只數「有工程、但工程公司空白」：工程空白的本來就放行（工項＝私人任務）。
SELECT 'supervision_photo' AS t, count(*) FROM supervision_photo x LEFT JOIN project_project p ON p.id = x.project_id WHERE p.company_id IS NULL
UNION ALL SELECT 'daily_log_sheet', count(*) FROM daily_log_sheet x LEFT JOIN project_project p ON p.id = x.project_id WHERE p.company_id IS NULL
UNION ALL SELECT 'daily_log_line', count(*) FROM daily_log_line x LEFT JOIN daily_log_sheet s ON s.id = x.sheet_id
          LEFT JOIN project_project p ON p.id = s.supervision_project_id WHERE p.company_id IS NULL
UNION ALL SELECT 'daily_log_material', count(*) FROM daily_log_material x LEFT JOIN project_project p ON p.id = x.project_id WHERE p.company_id IS NULL
UNION ALL SELECT 'daily_log_specific_item', count(*) FROM daily_log_specific_item x LEFT JOIN project_project p ON p.id = x.project_id WHERE p.company_id IS NULL
UNION ALL SELECT 'daily_log_weather', count(*) FROM daily_log_weather x LEFT JOIN daily_log_sheet s ON s.id = x.sheet_id
          LEFT JOIN project_project p ON p.id = s.supervision_project_id WHERE p.company_id IS NULL
UNION ALL SELECT 'daily_log_man_machine', count(*) FROM daily_log_man_machine x LEFT JOIN project_project p ON p.id = x.project_id WHERE p.company_id IS NULL
UNION ALL SELECT 'daily_log_man_machine_detail', count(*) FROM daily_log_man_machine_detail x LEFT JOIN project_project p ON p.id = x.project_id WHERE p.company_id IS NULL
UNION ALL SELECT 'supervision_test_standard', count(*) FROM supervision_test_standard x JOIN project_project p ON p.id = x.project_id WHERE p.company_id IS NULL
UNION ALL SELECT 'supervision_test_record', count(*) FROM supervision_test_record x LEFT JOIN project_project p ON p.id = x.project_id WHERE p.company_id IS NULL
UNION ALL SELECT 'supervision_test_warning', count(*) FROM supervision_test_warning x LEFT JOIN project_project p ON p.id = x.project_id WHERE p.company_id IS NULL
UNION ALL SELECT 'supervision_test_frequency_condition', count(*) FROM supervision_test_frequency_condition x
          JOIN supervision_test_standard s ON s.id = x.standard_id JOIN project_project p ON p.id = s.project_id WHERE p.company_id IS NULL
UNION ALL SELECT 'general_defect_improvement', count(*) FROM general_defect_improvement x LEFT JOIN project_project p ON p.id = x.project_id WHERE p.company_id IS NULL
UNION ALL SELECT 'general_self_inspection', count(*) FROM general_self_inspection x LEFT JOIN project_project p ON p.id = x.project_id WHERE p.company_id IS NULL
UNION ALL SELECT 'general_self_inspection_item', count(*) FROM general_self_inspection_item x LEFT JOIN general_self_inspection i ON i.id = x.inspection_id
          LEFT JOIN project_project p ON p.id = i.project_id WHERE p.company_id IS NULL
UNION ALL SELECT 'general_self_inspection_measure_line', count(*) FROM general_self_inspection_measure_line x
          LEFT JOIN general_self_inspection i ON i.id = x.inspection_id LEFT JOIN project_project p ON p.id = i.project_id WHERE p.company_id IS NULL
UNION ALL SELECT 'reservation_defect_improvement', count(*) FROM reservation_defect_improvement x LEFT JOIN project_project p ON p.id = x.project_id WHERE p.company_id IS NULL
UNION ALL SELECT 'reservation_self_inspection', count(*) FROM reservation_self_inspection x LEFT JOIN project_project p ON p.id = x.project_id WHERE p.company_id IS NULL
UNION ALL SELECT 'reservation_self_inspection_item', count(*) FROM reservation_self_inspection_item x
          LEFT JOIN reservation_self_inspection i ON i.id = x.inspection_id LEFT JOIN project_project p ON p.id = i.project_id WHERE p.company_id IS NULL
UNION ALL SELECT 'reservation_self_inspection_measure_line', count(*) FROM reservation_self_inspection_measure_line x
          LEFT JOIN reservation_self_inspection i ON i.id = x.inspection_id LEFT JOIN project_project p ON p.id = i.project_id WHERE p.company_id IS NULL
UNION ALL SELECT 'reservation_notification_slip', count(*) FROM reservation_notification_slip x LEFT JOIN project_project p ON p.id = x.project_id WHERE p.company_id IS NULL
UNION ALL SELECT 'reservation_notification_slip_line', count(*) FROM reservation_notification_slip_line x LEFT JOIN project_project p ON p.id = x.project_id WHERE p.company_id IS NULL
UNION ALL SELECT 'reservation_notification_slip_suspension', count(*) FROM reservation_notification_slip_suspension x
          LEFT JOIN reservation_notification_slip s ON s.id = x.slip_id LEFT JOIN project_project p ON p.id = s.project_id WHERE p.company_id IS NULL
UNION ALL SELECT 'supervision_folder', count(*) FROM supervision_folder x JOIN project_project p ON p.id = x.project_id WHERE p.company_id IS NULL
UNION ALL SELECT 'supervision_project_member', count(*) FROM supervision_project_member x LEFT JOIN project_project p ON p.id = x.project_id WHERE p.company_id IS NULL
UNION ALL SELECT 'supervision_review_application', count(*) FROM supervision_review_application x LEFT JOIN project_project p ON p.id = x.project_id WHERE p.company_id IS NULL
UNION ALL SELECT 'supervision_document', count(*) FROM supervision_document x JOIN project_project p ON p.id = x.project_id WHERE p.company_id IS NULL
UNION ALL SELECT 'project_task', count(*) FROM project_task x JOIN project_project p ON p.id = x.project_id WHERE p.company_id IS NULL;
-- [/S4-1]

-- [S4-1b]
-- 也必須是 0：規則用的 stored related project_id 與父單（施工日誌的 supervision_project_id、通報單的 project_id）不一致
-- （SQL 匯入沒填、或失真；上 S4 後跟著錯的工程走）。`-u` 不會重算既有的 stored related，要先把 project_id 補成父單的值。
SELECT 'daily_log_sheet' AS t, count(*) FROM daily_log_sheet x WHERE x.project_id IS DISTINCT FROM x.supervision_project_id
UNION ALL SELECT 'daily_log_material', count(*) FROM daily_log_material x JOIN daily_log_sheet s ON s.id = x.daily_log_id
          WHERE x.project_id IS DISTINCT FROM s.supervision_project_id
UNION ALL SELECT 'daily_log_specific_item', count(*) FROM daily_log_specific_item x JOIN daily_log_sheet s ON s.id = x.daily_log_id
          WHERE x.project_id IS DISTINCT FROM s.supervision_project_id
UNION ALL SELECT 'daily_log_man_machine_detail', count(*) FROM daily_log_man_machine_detail x JOIN daily_log_sheet s ON s.id = x.daily_log_id
          WHERE x.project_id IS DISTINCT FROM s.supervision_project_id
UNION ALL SELECT 'reservation_defect_improvement', count(*) FROM reservation_defect_improvement x
          JOIN reservation_notification_slip s ON s.id = x.slip_id WHERE x.project_id IS DISTINCT FROM s.project_id
UNION ALL SELECT 'reservation_self_inspection', count(*) FROM reservation_self_inspection x
          JOIN reservation_notification_slip s ON s.id = x.slip_id WHERE x.project_id IS DISTINCT FROM s.project_id
UNION ALL SELECT 'reservation_notification_slip_line', count(*) FROM reservation_notification_slip_line x
          JOIN reservation_notification_slip s ON s.id = x.slip_id WHERE x.project_id IS DISTINCT FROM s.project_id;
-- [/S4-1b]

-- [S4-2]
-- 允許公司涵蓋：最近 180 天「自己建立」的照片／日誌／缺失／自主檢查／通報單／送審，工程公司不在本人允許公司裡
-- ——上 S4 後他看不到自己建的這些（列出來的先補允許公司，或確認是預期）。0 列＝沒有這種人。
SELECT u.login, x.t, p.company_id, count(*) AS rows
FROM (
  SELECT 'photo' AS t, create_uid, project_id, create_date FROM supervision_photo
  UNION ALL SELECT 'daily_log', create_uid, project_id, create_date FROM daily_log_sheet
  UNION ALL SELECT 'gen_defect', create_uid, project_id, create_date FROM general_defect_improvement
  UNION ALL SELECT 'gen_inspect', create_uid, project_id, create_date FROM general_self_inspection
  UNION ALL SELECT 'res_defect', create_uid, project_id, create_date FROM reservation_defect_improvement
  UNION ALL SELECT 'res_inspect', create_uid, project_id, create_date FROM reservation_self_inspection
  UNION ALL SELECT 'slip', create_uid, project_id, create_date FROM reservation_notification_slip
  UNION ALL SELECT 'review', create_uid, project_id, create_date FROM supervision_review_application
) x
JOIN res_users u ON u.id = x.create_uid
JOIN project_project p ON p.id = x.project_id
WHERE u.active AND u.id > 2 AND x.create_date > now() - interval '180 days'
  AND NOT EXISTS (SELECT 1 FROM res_company_users_rel r WHERE r.user_id = u.id AND r.cid = p.company_id)
GROUP BY 1, 2, 3 ORDER BY 1, 2, 3;
-- [/S4-2]

-- [S4-3]
-- 工項的被指派人：允許公司不含工程公司的（上 S4 後他在「我的工項」看不到它）。0 列＝沒有。
SELECT u.login, p.company_id, count(*) AS tasks
FROM project_task_user_rel r
JOIN project_task t ON t.id = r.task_id AND t.active
JOIN project_project p ON p.id = t.project_id
JOIN res_users u ON u.id = r.user_id AND u.active
WHERE NOT EXISTS (SELECT 1 FROM res_company_users_rel c WHERE c.user_id = u.id AND c.cid = p.company_id)
GROUP BY 1, 2 ORDER BY 1, 2;
-- [/S4-3]

-- [S4-4]
-- 參考：上 S4 前「一般內部帳號」就讀得到的資料夾、工程成員、公司空白的工項，各工程公司有多少（洞有多大）
SELECT 'folder' AS t, p.company_id, count(*) FROM supervision_folder x JOIN project_project p ON p.id = x.project_id GROUP BY 1, 2
UNION ALL SELECT 'member', p.company_id, count(*) FROM supervision_project_member x JOIN project_project p ON p.id = x.project_id GROUP BY 1, 2
UNION ALL SELECT 'task(公司空白)', p.company_id, count(*) FROM project_task x JOIN project_project p ON p.id = x.project_id
          WHERE x.company_id IS NULL GROUP BY 1, 2
ORDER BY 1, 2;
-- [/S4-4]
