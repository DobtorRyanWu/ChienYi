# -*- coding: utf-8 -*-
"""反查驗證：DB 裡的值是不是真的等於當初送進去的值。

用法：
    docker exec -i odoo18 odoo shell -c /etc/odoo/odoo.conf -d odoo18_dev \
        < addons/construction_water_level/tools/verify_readings.py

為什麼要有這支：寫入端回報「成功 N 筆」完全不能當驗證。Odoo 的 Datetime 會依
連線使用者時區換算，整批位移 8 小時時，寫入一樣回報成功，只有反查才看得出來。
（教訓來源：2026-08-07 生產站 4,346 筆照片時間整批 −8 小時。）
"""

import json

EXPECTED_PATH = '/tmp/wl_seed_expected.json'
VALUE_TOLERANCE = 0.0005  # digits=(10,3) 的四捨五入誤差

with open(EXPECTED_PATH, encoding='utf-8') as fh:
    expected = json.load(fh)

by_uid = {}
for row in expected:
    by_uid.setdefault(row['device_uid'], []).append(row)

total = 0
mismatch = []
missing = []

for uid, rows in by_uid.items():
    device = env['water.level.device'].search([('device_uid', '=', uid)], limit=1)
    if not device:
        missing.append('%s：站不存在' % uid)
        continue
    readings = env['water.level.reading'].search_read(
        [('device_id', '=', device.id)], ['ts', 'value'])
    actual = {str(r['ts']): r['value'] for r in readings}
    for row in rows:
        total += 1
        got = actual.get(row['ts'])
        if got is None:
            missing.append('%s %s 查無資料' % (uid, row['ts']))
            continue
        want = row['raw_value'] + row['datum_elevation']
        if abs(got - want) > VALUE_TOLERANCE:
            mismatch.append('%s %s 期望 %.3f 實得 %.3f' % (uid, row['ts'], want, got))

print('比對 %s 筆' % total)
print('查無資料：%s 筆' % len(missing))
print('數值不符：%s 筆' % len(mismatch))
for line in (missing[:5] + mismatch[:5]):
    print('  -', line)
print('RESULT:', 'PASS' if not missing and not mismatch else 'FAIL')
