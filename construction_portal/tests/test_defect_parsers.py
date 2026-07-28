# -*- coding: utf-8 -*-
"""缺失匯入解析器測試（通用化後）。

舊版兩支 parser 的格式假設是硬編碼的，只有 A 標可用：
  xlsx  工作表名須含「不合格品/缺失」、表頭固定 R2、第一欄須為數字、欄位順序固定
  docx  檔名開頭須為 7 位民國日期，register_no 被捏造成 `Q01-` + 日期

通用化後改為「依表頭名稱讀欄」與「literal 抽取編號」。本測試鎖定兩份真實檔案
的實際形狀（不需要檔案本身，直接餵解析函式對應的資料結構）：

  A 標    表頭 R2、`編號|登錄編號|改正單位|改正事項|通知\\r\\n改正日期|…`
          登錄編號 Q01-1121007 或 Q01-1130506-2（同日多筆帶序號）
  P11001  表頭 R4、`文件編號|工程缺失事項|通知改正日期|…`、無「改正單位」欄
          工作表名 QA / QR 即監造／營造
"""

from datetime import date

from odoo.tests.common import TransactionCase, tagged

from odoo.addons.construction_portal.utils import defect_xlsm_parser as X
from odoo.addons.construction_portal.utils import defect_docx_parser as D


# 兩份真實檔案的表頭形狀
A_HEADER = ['編號', '登錄編號', '改正單位', '改正事項',
            '通知\r\n改正日期', '限定完成\r\n改善日期', '確認完成\r\n改善日期']
P_HEADER = ['文件編號', '工程缺失事項', '通知改正日期',
            '限定完成\r\n改善日期', '確認完成\r\n改善日期', '備註']


class _FakeDefect:
    """假的缺失記錄，供索引/比對測試用（不進 DB）。"""

    def __init__(self, rec_id, source_description, found_date, description=''):
        self.id = rec_id
        self.source_description = source_description
        self.found_date = found_date
        self.defect_description = description


@tagged('post_install', '-at_install', 'construction_portal')
class TestDefectXlsxParser(TransactionCase):

    # ── 日期 ────────────────────────────────────────────────────
    def test_roc_date_with_dots(self):
        self.assertEqual(X._parse_date('112.10.07'), date(2023, 10, 7))

    def test_roc_date_with_slashes(self):
        self.assertEqual(X._parse_date('110/08/03'), date(2021, 8, 3))

    def test_roc_date_single_digit_parts(self):
        self.assertEqual(X._parse_date('113.3.11'), date(2024, 3, 11))

    def test_ad_date(self):
        self.assertEqual(X._parse_date('2024/09/19'), date(2024, 9, 19))

    def test_real_date_passthrough(self):
        self.assertEqual(X._parse_date(date(2024, 1, 2)), date(2024, 1, 2))

    def test_garbage_date(self):
        for bad in (None, '', '未填', '112.99.99', 'abc'):
            self.assertIsNone(X._parse_date(bad), f'{bad!r} 不該解析成日期')

    # ── 表頭正規化 ──────────────────────────────────────────────
    def test_header_normalisation_strips_newlines(self):
        self.assertEqual(X._norm_header('通知\r\n改正日期'), '通知改正日期')

    def test_header_normalisation_strips_fullwidth_space(self):
        self.assertEqual(X._norm_header('限定完成　改善日期'), '限定完成改善日期')

    # ── 表頭定位 ────────────────────────────────────────────────
    def test_locate_header_a_biao(self):
        """A 標：表頭在 R2（索引 1），標題列在 R1。"""
        rows = [['磺港溪再造C段護岸及步道整建工程'], A_HEADER,
                ['1', 'Q01-1121007', '職安', '安全帽未有反光帶。',
                 '112.10.07', '112.10.12', '112.10.07']]
        idx, colmap = X._locate_header(rows)
        self.assertEqual(idx, 1)
        self.assertEqual(colmap['seq_or_register'], 0)
        self.assertEqual(colmap['register_no'], 1)     # 「登錄編號」不能被「編號」搶走
        self.assertEqual(colmap['unit'], 2)
        self.assertEqual(colmap['description'], 3)
        self.assertEqual(colmap['found_date'], 4)
        self.assertEqual(colmap['deadline'], 5)
        self.assertEqual(colmap['improvement_date'], 6)

    def test_locate_header_p11001(self):
        """P11001：表頭在 R4（索引 3），前面有公司名與空列。"""
        rows = [['任泰技術顧問有限公司'], ['            '], [], P_HEADER,
                ['QA-001', '護坦灌漿後遇雨未覆蓋', '110/08/03',
                 '110/08/03', '110/08/03']]
        idx, colmap = X._locate_header(rows)
        self.assertEqual(idx, 3)
        self.assertEqual(colmap['register_no'], 0)     # 「文件編號」→ 登錄編號
        self.assertEqual(colmap['description'], 1)
        self.assertNotIn('unit', colmap)               # 這份沒有「改正單位」欄

    def test_locate_header_rejects_non_defect_sheet(self):
        """統計圖／工作表2 這種不是缺失表的，必須認不出表頭而被略過。"""
        for rows in (
            [['112年度全市堤坡及護岸綠化工程'], ['缺失項目', '14'],
             ['施工', '49'], ['職安', '29']],
            [['0', '類號', '填表日期', '契約規範標準', '檢驗測試結果',
              '主要缺失', '次要缺失', '不合格原因分析']],
        ):
            idx, colmap = X._locate_header(rows)
            self.assertIsNone(colmap, f'不該把這張表當成缺失表：{rows[0]}')

    # ── 改正單位 → 缺失類別 ─────────────────────────────────────
    def test_unit_to_category(self):
        self.assertEqual(X.UNIT_TO_CATEGORY['施工'], 'workmanship')
        self.assertEqual(X.UNIT_TO_CATEGORY['品質'], 'workmanship')
        self.assertEqual(X.UNIT_TO_CATEGORY['職安'], 'safety')
        self.assertEqual(X.UNIT_TO_CATEGORY['勞安'], 'safety')
        self.assertEqual(X.UNIT_TO_CATEGORY['環境'], 'environment')

    def test_sheet_to_category_fallback(self):
        """沒有「改正單位」欄時才由工作表名 QA/QR 推論。"""
        self.assertEqual(X._SHEET_TO_CATEGORY['QA'], 'workmanship')
        self.assertEqual(X._SHEET_TO_CATEGORY['QR'], 'safety')


@tagged('post_install', '-at_install', 'construction_portal')
class TestDefectDocxParser(TransactionCase):

    # ── 登錄編號 literal 抽取（四種寫法） ───────────────────────
    def test_register_paren_with_number(self):
        self.assertEqual(
            D.derive_register_no('1-0803-缺失矯正改善追蹤回報表(護坦灌漿)(QA-001).docx'),
            'QA-001')

    def test_register_hyphen_with_number(self):
        self.assertEqual(
            D.derive_register_no('1100824-缺失矯正改善追蹤表-QR-001(109.8.24).docx'),
            'QR-001')

    def test_register_leading(self):
        self.assertEqual(
            D.derive_register_no('QA-11309191-缺失矯正改善追蹤回報表-xxx.docx'),
            'QA-11309191')

    def test_register_absent(self):
        """A 標慣例只有日期、沒有編號 —— 不可捏造。"""
        self.assertIsNone(
            D.derive_register_no('1121025-磺港溪缺失矯正改善(勞安).docx'))

    def test_register_no_longer_fabricates_q01(self):
        """回歸：舊版會把日期捏造成 Q01-1121025，那是 A 標專屬、換案場即錯。"""
        reg = D.derive_register_no('1121025-磺港溪缺失矯正改善(勞安).docx')
        self.assertNotEqual(reg, 'Q01-1121025')

    # ── record_type ─────────────────────────────────────────────
    def test_record_type_from_all_four_shapes(self):
        cases = [
            ('1-0803-回報表(護坦)(QA-001).docx', 'supervision'),
            ('1100824-追蹤表-QR-001(109.8.24).docx', 'contractor'),
            ('QA-11309191-回報表.docx', 'supervision'),
            ('1100517缺失矯正改善追蹤回報表(QR)(雜草清除).docx', 'contractor'),
        ]
        for filename, expect in cases:
            self.assertEqual(D.derive_record_type(filename), expect, filename)

    def test_record_type_none_when_unmarked(self):
        self.assertIsNone(
            D.derive_record_type('1121025-磺港溪缺失矯正改善(勞安).docx'))

    # ── 日期 ────────────────────────────────────────────────────
    def test_found_date_leading(self):
        self.assertEqual(
            D.derive_found_date('1121025-磺港溪缺失矯正改善(勞安).docx'),
            date(2023, 10, 25))

    def test_found_date_not_required_at_start(self):
        """真實 zip 可能帶前綴，日期不一定在開頭。"""
        self.assertEqual(
            D.derive_found_date('磺港溪_1121025_缺失改善.docx'),
            date(2023, 10, 25))

    def test_found_date_from_register(self):
        self.assertEqual(
            D.derive_found_date('QA-11309191-回報表.docx'), date(2024, 9, 19))

    def test_found_date_none_when_no_year(self):
        """`1-0803-…` 只有月日沒有年 —— 推不出，不能亂猜。"""
        self.assertIsNone(
            D.derive_found_date('1-0803-回報表(護坦灌漿)(QA-001).docx'))

    # ── 比對鍵 ──────────────────────────────────────────────────
    def test_docx_keys_prefers_literal_register(self):
        keys = D.docx_match_keys('1-0803-回報表(護坦)(QA-001).docx')
        self.assertEqual(keys[0], 'QA-001')

    def test_docx_keys_include_daily_sequence(self):
        """同日多筆：`1130925-1 xxx.docx` 要產生帶序號的鍵，且比純日期鍵前面。"""
        keys = D.docx_match_keys('1130925-1 護欄鋼筋未綁紮牢固.docx')
        self.assertEqual(keys, ['DATE:1130925#1', 'DATE:1130925'])

    def test_docx_keys_date_only(self):
        self.assertEqual(
            D.docx_match_keys('1121025-磺港溪缺失矯正改善(勞安).docx'),
            ['DATE:1121025'])

    def test_defect_index_keys_tiers(self):
        keys = D.defect_index_keys('Q01-1130506-2', date(2024, 5, 6))
        self.assertEqual(keys['register'], 'Q01-1130506-2')
        self.assertEqual(keys['register_date_seq'], 'DATE:1130506#2')
        self.assertEqual(keys['register_date'], 'DATE:1130506')
        self.assertEqual(keys['found_date'], 'DATE:1130506')

    def test_defect_index_keys_without_sequence(self):
        keys = D.defect_index_keys('Q01-1121007', date(2023, 10, 7))
        self.assertNotIn('register_date_seq', keys)
        self.assertEqual(keys['register_date'], 'DATE:1121007')

    # ── 分層比對 ────────────────────────────────────────────────
    def test_match_by_literal_register(self):
        defects = [_FakeDefect(1, 'QA-001', date(2021, 8, 3), '護坦灌漿後遇雨未覆蓋')]
        index, ambiguous = D.build_defect_index(defects)
        target, _ = D.match_defect(['QA-001'], index, ambiguous)
        self.assertIsNotNone(target)
        self.assertEqual(target.id, 1)

    def test_match_by_daily_sequence_beats_date_collision(self):
        """同一天 3 筆時，帶序號的鍵要能精準命中，不能落到歧義。"""
        defects = [
            _FakeDefect(1, 'Q01-1130506-1', date(2024, 5, 6), '新設河道似有積水情形'),
            _FakeDefect(2, 'Q01-1130506-2', date(2024, 5, 6), '砌石護岸未符合圍砌'),
            _FakeDefect(3, 'Q01-1130506-3', date(2024, 5, 6), '便橋與防洪牆間缺口'),
        ]
        index, ambiguous = D.build_defect_index(defects)
        target, amb = D.match_defect(
            D.docx_match_keys('1130506-2 砌石護岸.docx'), index, ambiguous)
        self.assertIsNotNone(target, f'應命中第 2 筆，卻卡在歧義 {amb}')
        self.assertEqual(target.id, 2)

    def test_match_disambiguates_by_description(self):
        """檔名沒帶序號、但帶缺失內容時，用文字相似度拆解同日多筆。"""
        defects = [
            _FakeDefect(1, 'Q01-1131028', date(2024, 10, 28),
                        '雙孔箱涵施工縫止水帶未妥善搭接'),
            _FakeDefect(2, 'Q01-1131028', date(2024, 10, 28),
                        '高壓氣體容器應未依規定儲存及設置滅火器'),
        ]
        index, ambiguous = D.build_defect_index(defects)
        row = {'filename': '1131028高壓氣體容器未依規定儲存及設置滅火器.docx',
               'description': '高壓氣體容器未依規定儲存及設置滅火器。'}
        target, _ = D.match_defect(
            D.docx_match_keys(row['filename']), index, ambiguous,
            hint=D.docx_hint_text(row))
        self.assertIsNotNone(target)
        self.assertEqual(target.id, 2)

    def test_match_refuses_when_text_does_not_fit(self):
        """內容對不上任何候選時，寧可不配也不要亂配。"""
        defects = [
            _FakeDefect(1, 'Q01-1130506', date(2024, 5, 6), '砌石護岸洩水管間距不一'),
            _FakeDefect(2, 'Q01-1130506-1', date(2024, 5, 6), '新設河道似有積水情形'),
        ]
        index, ambiguous = D.build_defect_index(defects)
        row = {'filename': 'QR-11305061-安全護欄損壞.docx',
               'description': '工區五安全護欄損壞，請改善。'}
        target, amb = D.match_defect(
            D.docx_match_keys(row['filename']), index, ambiguous,
            hint=D.docx_hint_text(row))
        self.assertIsNone(target, '內容明顯不同，不該配上去')
        self.assertIsNotNone(amb)

    def test_match_returns_none_for_unknown_key(self):
        defects = [_FakeDefect(1, 'QA-001', date(2021, 8, 3), 'x')]
        index, ambiguous = D.build_defect_index(defects)
        target, amb = D.match_defect(['QA-999'], index, ambiguous)
        self.assertIsNone(target)
        self.assertIsNone(amb)
