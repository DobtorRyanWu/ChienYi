-- 上 S5 之前各站要查（全部唯讀）。說明在 ../README_ROLE_ACCOUNTS.md §3c。
-- 用法：psql -d <DB> -At -F ' | ' -f construction_company_dashboard/runbook/s5_precheck.sql
--
-- 每一段用「-- [段名]」與「-- [/段名]」包起來：tests/test_company_isolation.py 的
-- test_s5_precheck_sql_covers_every_rule_model 會在測試庫實跑 [S5-1] 那一段，要求每個 S5 規則模型
-- 恰好一列、第一欄＝那個模型的資料表名——新增或拿掉規則模型時，這裡沒跟著改就會紅。
-- 沒裝的模組（例：construction_meeting_record、construction_acceptance）那幾張表不存在，整段會報錯：
-- 把那幾列拿掉再跑，並在換版紀錄寫明哪個模組沒裝。

-- [S5-1]
-- 必須全部是 0：上 S5 後非 sudo 的人全部看不到的紀錄（規則 fail-closed）。路徑與規則相同（子表沿規則用的那個欄位）。
-- * 一般的模型：所屬工程空白、或工程公司空白。
-- * 自主檢查樣板（＋時機、段落、項目、量測）：工程空白＝全域樣板、本來就放行，只數「有工程、但工程公司空白」。
-- * 文件樣板：「有工程、但工程公司空白」，加上「沒有工程、不是系統預設、樣板自己的公司也空白」。
-- * 會議記錄：「有工程、但工程公司空白」，加上「沒有工程、記錄自己的公司也空白」。
SELECT 'self_inspection_type' AS t, count(*) FROM self_inspection_type x JOIN project_project p ON p.id = x.project_id WHERE p.company_id IS NULL
UNION ALL SELECT 'self_inspection_type_timing', count(*) FROM self_inspection_type_timing x JOIN self_inspection_type y ON y.id = x.type_id
          JOIN project_project p ON p.id = y.project_id WHERE p.company_id IS NULL
UNION ALL SELECT 'self_inspection_type_stage', count(*) FROM self_inspection_type_stage x JOIN self_inspection_type y ON y.id = x.type_id
          JOIN project_project p ON p.id = y.project_id WHERE p.company_id IS NULL
UNION ALL SELECT 'self_inspection_type_item', count(*) FROM self_inspection_type_item x JOIN self_inspection_type y ON y.id = x.type_id
          JOIN project_project p ON p.id = y.project_id WHERE p.company_id IS NULL
UNION ALL SELECT 'self_inspection_type_measure', count(*) FROM self_inspection_type_measure x JOIN self_inspection_type y ON y.id = x.type_id
          JOIN project_project p ON p.id = y.project_id WHERE p.company_id IS NULL
UNION ALL SELECT 'defect_improvement_prefix_config', count(*) FROM defect_improvement_prefix_config x
          LEFT JOIN project_project p ON p.id = x.project_id WHERE p.company_id IS NULL
UNION ALL SELECT 'document_template', count(*) FROM document_template x LEFT JOIN project_project p ON p.id = x.project_id
          WHERE (x.project_id IS NOT NULL AND p.company_id IS NULL)
             OR (x.project_id IS NULL AND NOT COALESCE(x.is_default, false) AND x.company_id IS NULL)
UNION ALL SELECT 'construction_meeting_record', count(*) FROM construction_meeting_record x LEFT JOIN project_project p ON p.id = x.project_id
          WHERE (x.project_id IS NOT NULL AND p.company_id IS NULL) OR (x.project_id IS NULL AND x.company_id IS NULL)
UNION ALL SELECT 'construction_weekly_schedule', count(*) FROM construction_weekly_schedule x
          LEFT JOIN project_project p ON p.id = x.project_id WHERE p.company_id IS NULL
UNION ALL SELECT 'construction_weekly_schedule_line', count(*) FROM construction_weekly_schedule_line x
          LEFT JOIN construction_weekly_schedule s ON s.id = x.schedule_id
          LEFT JOIN project_project p ON p.id = s.supervision_project_id WHERE p.company_id IS NULL
UNION ALL SELECT 'acceptance_preliminary', count(*) FROM acceptance_preliminary x LEFT JOIN project_project p ON p.id = x.project_id WHERE p.company_id IS NULL
UNION ALL SELECT 'acceptance_preliminary_line', count(*) FROM acceptance_preliminary_line x LEFT JOIN acceptance_preliminary a ON a.id = x.acceptance_id
          LEFT JOIN project_project p ON p.id = a.project_id WHERE p.company_id IS NULL
UNION ALL SELECT 'acceptance_final', count(*) FROM acceptance_final x LEFT JOIN project_project p ON p.id = x.project_id WHERE p.company_id IS NULL
UNION ALL SELECT 'acceptance_final_line', count(*) FROM acceptance_final_line x LEFT JOIN acceptance_final a ON a.id = x.acceptance_id
          LEFT JOIN project_project p ON p.id = a.project_id WHERE p.company_id IS NULL
UNION ALL SELECT 'acceptance_defect', count(*) FROM acceptance_defect x LEFT JOIN project_project p ON p.id = x.project_id WHERE p.company_id IS NULL
UNION ALL SELECT 'project_closure', count(*) FROM project_closure x LEFT JOIN project_project p ON p.id = x.project_id WHERE p.company_id IS NULL
UNION ALL SELECT 'project_closure_document', count(*) FROM project_closure_document x LEFT JOIN project_closure c ON c.id = x.closure_id
          LEFT JOIN project_project p ON p.id = c.project_id WHERE p.company_id IS NULL
UNION ALL SELECT 'supervision_equipment', count(*) FROM supervision_equipment x LEFT JOIN project_project p ON p.id = x.project_id WHERE p.company_id IS NULL
UNION ALL SELECT 'supervision_equipment_request', count(*) FROM supervision_equipment_request x
          LEFT JOIN project_project p ON p.id = x.project_id WHERE p.company_id IS NULL
UNION ALL SELECT 'supervision_plan_control', count(*) FROM supervision_plan_control x LEFT JOIN project_project p ON p.id = x.project_id WHERE p.company_id IS NULL;
-- [/S5-1]

-- [S5-1b]
-- 也必須是 0：規則用的 stored related project_id 與來源不一致（SQL 匯入沒填、或失真；上 S5 後跟著錯的工程走）。
-- `-u` 不會重算既有的 stored related，要先把 project_id 補成來源的值。
SELECT 'construction_weekly_schedule' AS t, count(*) FROM construction_weekly_schedule x
       WHERE x.project_id IS DISTINCT FROM x.supervision_project_id
UNION ALL SELECT 'supervision_equipment_request', count(*) FROM supervision_equipment_request x
          JOIN supervision_equipment e ON e.id = x.equipment_id WHERE x.project_id IS DISTINCT FROM e.project_id;
-- [/S5-1b]

-- [S5-2]
-- 上 S5 後可見範圍會變小的資料，先確認是不是預期（多公司共用的庫最要緊；一庫一公司的站應該都只有一家）：
-- (a) 公司層級的文件樣板（沒有工程、不是系統預設）：上線後只有樣板自己的公司看得到
-- (b) 沒選工程的會議記錄：上線後只有記錄自己的公司看得到
-- (c) 自主檢查用到「別家公司工程的專屬樣板」：上線後填表的人讀不到那份樣板（0 列＝沒有）
-- (d) 專案層級的文件樣板，樣板自己的公司和工程的公司不一樣：上線後看工程的公司（0 列＝沒有）
SELECT '(a) 公司層級文件樣板' AS t, x.company_id, count(*) FROM document_template x
       WHERE x.project_id IS NULL AND NOT COALESCE(x.is_default, false) GROUP BY 1, 2
UNION ALL SELECT '(b) 沒選工程的會議記錄', x.company_id, count(*) FROM construction_meeting_record x WHERE x.project_id IS NULL GROUP BY 1, 2
UNION ALL SELECT '(c) 一般式自檢用到別家公司的專屬樣板', ip.company_id, count(*) FROM general_self_inspection i
          JOIN self_inspection_type y ON y.id = i.inspection_type_id JOIN project_project yp ON yp.id = y.project_id
          JOIN project_project ip ON ip.id = i.project_id WHERE yp.company_id IS DISTINCT FROM ip.company_id GROUP BY 1, 2
UNION ALL SELECT '(c) 預約式自檢用到別家公司的專屬樣板', ip.company_id, count(*) FROM reservation_self_inspection i
          JOIN self_inspection_type y ON y.id = i.inspection_type_id JOIN project_project yp ON yp.id = y.project_id
          JOIN project_project ip ON ip.id = i.project_id WHERE yp.company_id IS DISTINCT FROM ip.company_id GROUP BY 1, 2
UNION ALL SELECT '(d) 專案層級文件樣板：公司與工程公司不同', p.company_id, count(*) FROM document_template x
          JOIN project_project p ON p.id = x.project_id WHERE x.company_id IS DISTINCT FROM p.company_id GROUP BY 1, 2
ORDER BY 1, 2;
-- [/S5-2]

-- [S5-3]
-- 參考：上 S5 前別家公司的後台帳號就讀得到的資料，各工程公司有多少（洞有多大）
SELECT '綁工程的自主檢查樣板' AS t, p.company_id, count(*) FROM self_inspection_type x JOIN project_project p ON p.id = x.project_id GROUP BY 1, 2
UNION ALL SELECT '專案層級文件樣板', p.company_id, count(*) FROM document_template x JOIN project_project p ON p.id = x.project_id GROUP BY 1, 2
UNION ALL SELECT '缺失編號前綴設定', p.company_id, count(*) FROM defect_improvement_prefix_config x JOIN project_project p ON p.id = x.project_id GROUP BY 1, 2
UNION ALL SELECT '週施工排程', p.company_id, count(*) FROM construction_weekly_schedule x JOIN project_project p ON p.id = x.project_id GROUP BY 1, 2
ORDER BY 1, 2;
-- [/S5-3]
