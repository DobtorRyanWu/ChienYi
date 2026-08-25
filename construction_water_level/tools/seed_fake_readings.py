# -*- coding: utf-8 -*-
"""灌假水位資料，讓後台圖表在接真設備之前就能看。

用法（在主機上跑）：
    docker exec -i odoo18 odoo shell -c /etc/odoo/odoo.conf -d odoo18_dev \
        < addons/construction_water_level/tools/seed_fake_readings.py

會做三件事：
1. 在第一個非草稿工程案件底下建（或沿用）三個測試站 WL-DEMO-01/02/03
2. 每站灌 24 小時、每 5 分鐘一筆的隨機遊走水位
3. 把「送出去的原始值」寫到 /tmp/wl_seed_expected.json，
   給 tools/verify_readings.py 反查比對用（寫入端自己說成功不算驗證）

重跑是安全的：(監測站, 時間) 唯一，重複的會被 ON CONFLICT 擋掉。
"""

import json
import random
from datetime import datetime, timedelta

SAMPLE_INTERVAL_MIN = 5
SAMPLE_HOURS = 24
SAMPLE_COUNT = SAMPLE_HOURS * 60 // SAMPLE_INTERVAL_MIN

# 磺港溪一帶的座標，只是為了讓地圖有東西看
DEMO_STATIONS = [
    # (設備碼, 站名, 上下游序, 緯度, 經度, 基準高程, 三級, 二級, 一級)
    ('WL-DEMO-01', 'WL-01 上游', 10, 25.128705, 121.503104, 0.0, 3.5, 4.0, 4.5),
    ('WL-DEMO-02', 'WL-02 中游', 20, 25.126100, 121.505400, 0.0, 3.5, 4.0, 4.5),
    ('WL-DEMO-03', 'WL-03 下游', 30, 25.123500, 121.507800, 0.0, 3.5, 4.0, 4.5),
]

WATER_MIN, WATER_MAX = 1.0, 5.0
STEP_MIN, STEP_MAX = -0.06, 0.07
EXPECTED_PATH = '/tmp/wl_seed_expected.json'

random.seed(20260819)  # 固定種子，重跑產生同一組值，方便比對

project = env['project.project'].search(
    [('state', 'not in', ['draft', 'terminated'])], limit=1)
if not project:
    project = env['project.project'].search([], limit=1)
if not project:
    raise SystemExit('資料庫裡沒有任何工程案件，先建一個再跑。')

# 把基準時間對齊到取樣格點（例如 5 分鐘），同一個時窗內重跑會產生一模一樣的時間戳，
# 配上固定亂數種子就真的冪等——這樣「重跑安全」才是事實，不是說說而已。
now = datetime.utcnow().replace(second=0, microsecond=0)
now -= timedelta(minutes=now.minute % SAMPLE_INTERVAL_MIN)
expected = []

for uid, name, seq, lat, lng, datum, lv3, lv2, lv1 in DEMO_STATIONS:
    device = env['water.level.device'].search([('device_uid', '=', uid)], limit=1)
    if not device:
        device = env['water.level.device'].create({
            'name': name,
            'project_id': project.id,
            'device_uid': uid,
            'seq': seq,
            'latitude': lat,
            'longitude': lng,
            'datum_elevation': datum,
            'level_3': lv3,
            'level_2': lv2,
            'level_1': lv1,
        })

    value = random.uniform(2.0, 3.0)
    rows = []
    for i in range(SAMPLE_COUNT):
        value = max(WATER_MIN, min(WATER_MAX, value + random.uniform(STEP_MIN, STEP_MAX)))
        ts = now - timedelta(minutes=SAMPLE_INTERVAL_MIN * i)
        rows.append((ts, round(value, 3)))

    result = device.ingest_readings(rows)
    print('%s：收 %s 筆、重複 %s 筆' % (uid, result['accepted'], result['duplicated']))

    expected.extend({
        'device_uid': uid,
        'ts': ts.strftime('%Y-%m-%d %H:%M:%S'),
        'raw_value': value,
        'datum_elevation': datum,
    } for ts, value in rows)

with open(EXPECTED_PATH, 'w', encoding='utf-8') as fh:
    json.dump(expected, fh)

env.cr.commit()
print('已寫出 %s 筆期望值到 %s' % (len(expected), EXPECTED_PATH))
