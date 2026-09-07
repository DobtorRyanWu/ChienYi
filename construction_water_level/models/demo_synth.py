# -*- coding: utf-8 -*-
"""示範資料合成器（純函數，不含 model）。

真實水位計還沒有資料進來，但 DM 與客戶展示需要看到「水位在動」。
這支用已匯入的歷史真值當樣本，合成往後的讀數。

⚠️ **它產生的不是量測值。** 場域、站點與來源都會標 `is_demo`，前台有 badge。
   不要讓任何人（包括未來的自己）把這些數字當成證據。

演算法（用水利署 2025 年磺港溪三站實測資料校準過）：

1. **基線重播** —— 取同一站「基線年同月同日同時分」的真值當基線。枯水豐水、
   颱風季的質地全部沿用真實資料，不必自己造一套物理模型。
2. **黏滯** —— 以該站歷史「讀數不變的比例」讓值原地不動。**這一步最關鍵**：
   真實感測器在 0.01 m 解析度下，44%~85% 的刻度讀數完全沒動；少了它，
   合成序列每一步都在抖，一眼就看得出是假的。
3. **AR(1) 均值回歸偏移** —— `off ← φ·off + N(0, σ)`，讓曲線在基線附近呼吸而不漂走。
4. **量化與夾限** —— 0.01 m 解析度、夾在該站歷史 [min, max]。
5. **雨型事件** —— 低機率（或後台手動觸發）疊一段從歷史真實暴漲取樣的漲退曲線，
   讓告警畫面有東西可看。

**可重現性**：亂數全部由 `(device_uid, tick)` 決定，加上偏移量每天重新錨定，
所以重跑一段時間範圍會得到同一批數字——清掉重生、或事後回頭補算，
結果都一樣。（`_fetch_demo_synth` 另外從「這台最後一筆之後」才開始生，
本來就不會重算已經寫進去的格子；可重現性是第二道保險，不是唯一那道。）
遞迴的部分（黏滯沿用前值、單步幅度上限）在跨越錨點後可能還留一個量化單位的尾巴，
所以是「重現到 0.01 公尺」而不是位元級相同。

⚠️ 決定性靠的是 `_seed()` 的 blake2b，**不是內建的 `hash()`**。
   Python 3 對 str 的 `hash()` 帶每個進程隨機化的 PYTHONHASHSEED，
   拿它當種子的話 Odoo 每次重啟就換一組數字，重撈的區間會整段變動。
"""

import collections
import hashlib
import json
import math
import random
import statistics
from datetime import datetime, timedelta

# tick 是全系統共用的時間格子：所有站的 seq_no 都由它算出來，
# 因此改動它等於作廢既有的所有序號，不可以隨便動。
TICK_SECONDS = 600
# naive UTC，與 Odoo 的 Datetime 一致。
# 取 2024-12-31 而不是 2025-01-01：歷史樣本是台北時間的 2025 全年，
# 換成 UTC 之後最早一筆落在 2024-12-31 16:00，epoch 設在 2025 會讓它算出**負的 seq_no**。
TICK_EPOCH = datetime(2024, 12, 31, 0, 0, 0)

# AR(1) 的回歸係數。0.92 在 10 分鐘刻度上約等於「一小時多把偏移拉回一半」，
# 太高會漂走、太低則每一步都獨立跳動。
AR_PHI = 0.92
# 偏移量的夾限倍數（乘上 AR(1) 的穩態標準差）
AR_CLAMP_SIGMA = 3.0
# 水位計的顯示解析度（公尺）。水利署三站的實測資料全部是 0.01 的整數倍。
VALUE_QUANTUM = 0.01
# 雨型事件的形狀樣本至少要這麼長才收進輪廓（10 分鐘 × 6 = 1 小時）
MIN_SURGE_TICKS = 6
# 漲水時黏滯要放鬆——水在漲，讀數不可能一直不動
STICK_RELAX_IN_SURGE = 0.2
# 平時的單步跳幅上限取歷史相鄰差分的這個分位。取 p95 是有意的：
# 「95% 的變化不超過這一步」正是驗收要對上的統計量，參數的定義與判準同源，
# 不是湊出來的。用「有動時的 p90」之類的替代品，兩把尺不同源，怎麼調都對不準。
MAX_STEP_QUANTILE = 0.95
# 一場雨最長演多久（10 分鐘 × 72 = 12 小時）。歷史裡的豐水期可以連續好幾天偏高，
# 但那是季節，不是一場暴漲；照抄整段會把合成的平均值與標準差整個墊高。
MAX_SURGE_TICKS = 72
# 一天有幾個時間格子。偏移量每天重新錨定一次，見 synth_series。
TICKS_PER_DAY = 86400 // TICK_SECONDS
# 單月的暴漲機率最多是平均的幾倍。不設上限的話，某站十月權重會到 11.8，
# 乘上每日機率就變成那個月有六成的日子在下雨。
MAX_MONTH_WEIGHT = 3.0
# 與基線差距超過單步上限的幾倍時，改用比例追趕而不是一格一格爬。
# 分洪入口的基線在 2025 年 6 月永久抬升了半公尺，跨年重播時起點與基線
# 一口氣差 0.6 公尺；用固定步長要爬十小時，那十小時的水位是錯的。
# 真實水位面對上游條件改變是指數收斂，不是等速。
CATCHUP_THRESHOLD = 10.0
CATCHUP_RATE = 0.15
# 自動洪峰最多用掉「起漲點到上限」之間多少空間。留 15% 餘裕給隨機偏移，
# 不留的話峰值剛好等於上限，偏移一疊上去就被夾平，洪峰頂端出現三小時的平台。
SURGE_HEADROOM_RATIO = 0.85
# 黏滯機率的校準：跑幾輪、誤差小於多少就收斂
CALIBRATION_ROUNDS = 6
CALIBRATION_TOLERANCE = 0.005
CALIBRATION_SAMPLE_TICKS = 8000


def tick_of(ts):
    """時間 → tick 索引。同時也是 reading 的 seq_no。"""
    return int((ts - TICK_EPOCH).total_seconds() // TICK_SECONDS)


def ts_of(tick):
    """tick 索引 → 時間（該格子的起點）。"""
    return TICK_EPOCH + timedelta(seconds=tick * TICK_SECONDS)


def baseline_key(moment, year):
    """要合成的時刻 → 去基線年的哪一格取真值。

    這條規則有三個呼叫點（來源適配層、補歷史腳本、新站建置腳本），
    **必須是同一份**——之前分成兩份寫，同一格算出過兩個答案。

    兩個容易錯的地方：
    * 要合成的區間有一小段落在基線年自己身上（歷史最後一筆是台北 12/31 23:50，
      換成 UTC 之後那天還剩八小時），對這一段做 `replace(year=基線年)` 等於查它自己、
      永遠查不到，所以基線年當年的時刻要再往前推一年。
    * 2/29 在非閏年沒有對應，退到 2/28。
    """
    target_year = year if moment.year > year else moment.year - 1
    try:
        return moment.replace(year=target_year)
    except ValueError:
        return moment.replace(year=target_year, day=28)


def _seed(*parts):
    """穩定亂數種子：同樣的輸入在任何進程、任何機器都得到同一個數。

    不要換成內建 hash()——見模組 docstring 的警告。
    """
    raw = '|'.join(str(part) for part in parts).encode('utf-8')
    return int.from_bytes(hashlib.blake2b(raw, digest_size=8).digest(), 'big')


# ==================== 從歷史序列萃取統計輪廓 ====================

def build_profile(rows, surge_quantile=0.995, max_shapes=3):
    """把一站的歷史序列壓成合成器要用的統計輪廓。

    :param rows: [(ts, value), ...] 已排序、已剔除異常值
    :return: dict，直接 json.dumps 存進 device.demo_profile
    """
    values = [value for _, value in rows]
    if len(values) < 2:
        raise ValueError('歷史資料不足以建立統計輪廓（只有 %d 筆）' % len(values))

    # 只取「相鄰一個 tick」的差分，中間有缺漏的不算——
    # 跨越 3 小時空窗的那一步不是真實的變化速度。
    deltas = [
        rows[i][1] - rows[i - 1][1]
        for i in range(1, len(rows))
        if (rows[i][0] - rows[i - 1][0]).total_seconds() == TICK_SECONDS
    ]
    moved = [d for d in deltas if abs(d) > 1e-9]
    if not moved:
        raise ValueError('歷史資料整段沒有變化，無法估計波動幅度')

    # σ 取「有動的那些步」的 |Δ| 中位數，不是標準差。
    # 標準差會被少數暴漲的大跳動撐大——實測用標準差會讓平時的抖動比真實大一倍。
    sigma = statistics.median(abs(d) for d in moved)
    # 單步最大跳幅。沒有這個上限，合成的 |Δ| p95 會是歷史的兩倍——
    # 基線與偏移可以同時變，一步就跨兩格。
    # 取的是**所有**相鄰差分（含沒動的那些）的分位數，與驗收判準同一把尺。
    all_deltas = sorted(abs(d) for d in deltas)
    max_step = all_deltas[int(len(all_deltas) * MAX_STEP_QUANTILE)]

    return {
        'p_zero': 1.0 - len(moved) / len(deltas),   # 讀數原地不動的比例
        'sigma': sigma,
        'max_step': max_step,
        'min': min(values),
        'max': max(values),
        'median': statistics.median(values),
        'surge_shapes': _extract_surge_shapes(rows, surge_quantile, max_shapes),
        'surge_month_weights': _surge_month_weights(rows, surge_quantile),
    }


def _surge_month_weights(rows, quantile):
    """各月發生暴漲的相對頻率（平均為 1）。

    不加這個權重的話，雨型會平均散佈在一年裡——實測合成資料的暴漲全落在
    1~6 月，而歷史上這三站的高水位事件集中在 7、10、12 月。
    颱風季一場雨都沒有、二月卻有洪峰，對水利顧問客戶是一眼的破綻。

    算的是**有幾天發生**，不是有幾格超標：一場持續三天的大水會讓「格子比例」
    虛高十倍以上，乘進機率後那個月會變成天天下雨。
    """
    values = sorted(value for _, value in rows)
    threshold = values[min(int(len(values) * quantile), len(values) - 1)]

    days = collections.defaultdict(set)
    high_days = collections.defaultdict(set)
    for ts, value in rows:
        days[ts.month].add(ts.day)
        if value >= threshold:
            high_days[ts.month].add(ts.day)

    total_days = sum(len(v) for v in days.values())
    total_high = sum(len(v) for v in high_days.values())
    if not total_days or not total_high:
        return {}
    overall = total_high / total_days

    weights = {}
    for month, month_days in days.items():
        ratio = len(high_days[month]) / len(month_days) if month_days else 0.0
        weights[str(month)] = round(min(ratio / overall, MAX_MONTH_WEIGHT), 4)
    return weights


def _extract_surge_shapes(rows, quantile, max_shapes):
    """抓歷史裡真實的暴漲片段，存成「相對事件前水位的增量序列」。

    存增量而不是絕對值：套用時直接疊在當時的基線上，
    枯水期也能演一場和豐水期一樣形狀的漲水。
    """
    values = sorted(value for _, value in rows)
    threshold = values[min(int(len(values) * quantile), len(values) - 1)]

    shapes = []
    run = []
    for index, (ts, value) in enumerate(rows):
        # 「陣列上的前一筆」不等於「時間上的前一格」：薇閣的資料裡有一段四天的空窗，
        # 拿空窗另一頭的那筆當起漲基準，算出來的斜率是假的。時間不連續就切斷。
        # （附帶一提：這三站真的會在十分鐘內漲一公尺——薇閣 2025-12-07 08:50
        #  單格 +0.97 m，分洪入口單格最大 +1.53 m。看到合成資料陡升不要以為是 bug，
        #  先查歷史。用抽樣算出來的「最大變化」會嚴重低估這種事件。）
        contiguous = index > 0 and (ts - rows[index - 1][0]).total_seconds() == TICK_SECONDS
        if value >= threshold and (not run or contiguous):
            if not run:
                # 事件起點往前退一格當基準，才抓得到起漲的那一段；
                # 前一格接不上就從自己開始（shape 的第一個值是 0）
                run = [index - 1] if contiguous else [index]
            run.append(index)
        elif run:
            shapes.append(run)
            run = []
    if run:
        shapes.append(run)

    result = []
    for indices in sorted(shapes, key=len, reverse=True):
        if len(indices) < MIN_SURGE_TICKS:
            continue
        base = rows[indices[0]][1]
        shape = [round(rows[i][1] - base, 3) for i in indices[:MAX_SURGE_TICKS]]
        # 尾巴補一段退水，避免曲線在高點被硬切斷
        peak = max(shape)
        tail = max(len(shape) // 2, MIN_SURGE_TICKS)
        shape += [round(peak * (1 - (step + 1) / tail) ** 2, 3) for step in range(tail)]
        result.append(shape)
        if len(result) >= max_shapes:
            break
    return result


# ==================== 合成 ====================

def _surge_offset(profile, device_uid, tick, surge_probability, manual_start_tick,
                  manual_peak_rise=None, baseline=None, ceiling=None):
    """這個 tick 要不要疊雨型，疊多少。

    自動觸發由「哪一天」決定，不是每個 tick 擲骰子——
    否則暴漲會每 10 分鐘開始一次，而不是幾天一場雨。

    `manual_peak_rise` 讓**手動**觸發的那一場把形狀等比縮放到指定的漲幅。
    手動按鈕的用途就是展示告警；若照歷史原樣演一場、峰值差警戒線 0.01 公尺
    而沒告警，這個按鈕就沒達成它存在的目的。自動觸發不受影響，維持真實幅度。

    `ceiling` 是這站的水位上限。自動觸發的洪峰會先按「起漲點到上限還有多少空間」
    等比縮小，而不是照原樣疊上去再被夾平——被夾平的洪峰會精確停在歷史最大值
    十幾個小時，真實的洪峰是尖的，不會剛好卡在某個數字上。
    """
    shapes = profile.get('surge_shapes') or []
    if not shapes:
        return 0.0

    candidates = []
    if manual_start_tick:
        candidates.append(('manual', int(manual_start_tick)))

    month_weights = profile.get('surge_month_weights') or {}
    # 只看今天與昨天：一場雨最長不會超過一天多
    for day in (tick // TICKS_PER_DAY, tick // TICKS_PER_DAY - 1):
        rnd = random.Random(_seed(device_uid, 'surge-day', day))
        # 依月份加權：颱風季本來就比枯水期容易下大雨
        weight = month_weights.get(str(ts_of(day * TICKS_PER_DAY).month), 1.0)
        if rnd.random() < (surge_probability or 0.0) * weight:
            candidates.append(('auto', day * TICKS_PER_DAY + rnd.randrange(TICKS_PER_DAY)))

    total = 0.0
    for kind, start in candidates:
        offset = tick - start
        if offset < 0:
            continue
        shape = random.Random(_seed(device_uid, kind, start)).choice(shapes)
        if offset >= len(shape):
            continue
        rise = shape[offset]
        peak = max(shape)
        if kind == 'manual' and manual_peak_rise:
            if peak > 0:
                rise *= manual_peak_rise / peak
        elif ceiling is not None and peak > 0:
            base_at_start = (baseline(start) if baseline else None) or profile['median']
            headroom = (ceiling - base_at_start) * SURGE_HEADROOM_RATIO
            if 0 < headroom < peak:
                rise *= headroom / peak
        total += rise
    return total


def synth_series(device_uid, profile, baseline, start_tick, end_tick,
                 surge_probability=0.0, manual_start_tick=0, manual_peak_rise=None,
                 initial_value=None, shape_uid=None, warmup_ticks=144):
    """合成 [start_tick, end_tick) 的讀數。

    :param baseline: callable(tick) -> float|None，回傳基線年同月日時分的真值
    :param initial_value: 前一筆已經存在的讀數。合成要接在它後面，不是憑空起跳——
                          少了它，暖身期若剛好取不到基線就會退回「全年中位數」，
                          在枯水期造出高出半公尺的起點，再花好幾小時慢慢爬回來
    :param shape_uid: **事件層**的亂數種子（雨型、每日錨點）。向鄰站借基線的站要把它
                      設成被借那一台，否則兩站會各下各的雨——實測 34 公尺外的兩站
                      相關係數只有 0.50、十一場暴漲有七場只有一站在漲，
                      而真實的相鄰測站幾乎同漲同退。留空就用自己的 uid。
                      每 10 分鐘的抖動仍以 `device_uid` 為種子，那是各自的量測雜訊，
                      本來就該獨立
    :param warmup_ticks: 往前空跑幾格。預設一整天，剛好涵蓋到最近一個「每日錨點」，
                         任何一格都能重現（見迴圈裡的重錨說明）；
                         同時也讓偏移量收斂到穩態，接縫處不會出現不自然的平段
    :return: [(ts, value, seq_no), ...]
    """
    # 黏滯機率用校準過的值（見 calibrate_stickiness）；沒校準過就退回 p_zero
    p_stick_base = profile.get('p_stick', profile['p_zero'])
    sigma = profile['sigma']
    max_step = profile.get('max_step') or sigma
    lo, hi = profile['min'], profile['max']
    # 夾限比歷史最大值高一格：夾限剛好等於歷史峰值時，重播到峰頂的那幾格
    # 只要偏移量是正的就會被削掉，峰頂被拉成一段平台（實測歷史停 4 格、
    # 合成停 18 格）。洪峰的可用空間仍以歷史峰值 hi 為準，只有夾限放寬。
    clamp_hi = hi + max_step
    median = profile['median']
    clamp = AR_CLAMP_SIGMA * sigma / math.sqrt(1 - AR_PHI ** 2)

    shape_uid = shape_uid or device_uid
    rows = []
    off = 0.0
    previous = initial_value
    last_base = initial_value
    for tick in range(start_tick - warmup_ticks, end_tick):
        # 每個 tick 自己一顆種子 → 同一個 tick 不論被算幾次都得到同一串亂數
        rnd = random.Random(_seed(device_uid, tick))
        if tick % TICKS_PER_DAY == 0:
            # 每天把偏移量重新錨定一次。AR(1) 是遞迴的——不重錨的話，
            # 「某一格的值」其實取決於是從哪一格開始算的，重算一段就會得到不同的數字。
            # 錨點只由 (形狀來源, 第幾天) 決定，所以往前多跑一天（預設的 warmup）
            # 就足以重現任何一格。用 shape_uid 是為了讓借基線的站與母本站
            # 在「日」這個尺度上一起高一起低，而不是各自漂。
            off = random.Random(
                _seed(shape_uid, 'day-anchor', tick // TICKS_PER_DAY)).gauss(0, sigma)
        base = baseline(tick)
        if base is None:
            # ⚠️ 基線有洞的時候**不能拿前一個輸出值頂替**。那會讓 AR(1) 的偏移從
            #    「圍繞基線的回歸項」變成「每格累加的速度項」：值朝同一個方向一路
            #    走滿單步上限，幾小時內就撞到夾限並平頂在歷史最大值。
            #    實測分洪入口有一段 113 小時的基線空洞，這樣寫會讓三站在同一天
            #    同時衝到各自的歷史最高水位、超警戒四十幾小時——展示時無法解釋。
            #    正確做法是固定在最後一個有效基線上，讓偏移繼續當回歸項用。
            base = last_base if last_base is not None else median
        else:
            last_base = base
        # 雨型用 shape_uid：同一條河上的兩站不會各下各的雨
        surge = _surge_offset(
            profile, shape_uid, tick, surge_probability, manual_start_tick,
            manual_peak_rise, baseline=baseline, ceiling=hi)
        if surge > 0 and not manual_peak_rise:
            # 連著兩天各下一場雨時，兩條曲線會疊加而衝破上限、在頂端壓出一段平台。
            # 單場已經按可用空間縮過，總量也要一起收——手動觸發不受限，
            # 它的幅度是刻意設定來越過警戒線的。
            surge = min(surge, (hi - base) * SURGE_HEADROOM_RATIO)

        # 黏滯：讀數不動時，偏移量**也一起凍結**。
        # 只凍結讀數卻讓偏移量繼續漂，解除黏滯的那一刻就得一次追上漂掉的距離，
        # 跳幅因此固定偏大一格（實測分洪入口的 |Δ| p95 是歷史的兩倍）。
        # 反過來只凍結偏移量也不行——基線自己每格都在變，讀數照樣會動。
        # 漲水時放鬆黏滯，否則水在漲、讀數卻卡住。
        stick = p_stick_base * (STICK_RELAX_IN_SURGE if surge else 1.0)
        if previous is not None and rnd.random() < stick:
            value = previous
        else:
            off = max(-clamp, min(clamp, AR_PHI * off + rnd.gauss(0, sigma)))
            target = min(clamp_hi, max(lo, base + off + surge))
            if previous is None or surge:
                # 漲水時不限速：雨型的形狀是從歷史真實暴漲取樣來的，
                # 它的斜率就是真實斜率（分洪入口實測單格漲過 0.48 公尺），
                # 再套平時的步幅上限只會把真實的漲勢削成一條斜坡。
                value = target
            else:
                gap = target - previous
                if abs(gap) > CATCHUP_THRESHOLD * max_step:
                    # 離基線太遠（跨年重播、長缺口之後）：指數收斂追上去
                    value = previous + gap * CATCHUP_RATE
                else:
                    # 平時一步最多走 max_step：真實水位不會瞬移
                    value = previous + max(-max_step, min(max_step, gap))

        value = round(
            round(min(clamp_hi, max(lo, value)) / VALUE_QUANTUM) * VALUE_QUANTUM, 2)
        previous = value

        if tick >= start_tick:
            rows.append((ts_of(tick), value, tick))
    return rows


def calibrate_stickiness(device_uid, profile, rows):
    """用歷史樣本把「黏滯機率」訓練到讓合成的零變化比例對上歷史。

    為什麼不能直接拿 p_zero 當黏滯機率：量化到 0.01 公尺這件事本身就會製造一批
    「算出來有動、但四捨五入後同值」的格子。兩種來源疊在一起，實測會偏離目標
    好幾個百分點（中和橋偏高 10.8、薇閣偏低 6.1）。與其推導解析解，不如照著
    樣本跑幾輪、量出來、往回調——這就是拿歷史資料訓練參數。

    :param rows: [(ts, value), ...] 與 build_profile 用的是同一份
    :return: 校準後的黏滯機率
    """
    history = {tick_of(ts): value for ts, value in rows}
    ticks = sorted(history)
    if len(ticks) < CALIBRATION_SAMPLE_TICKS:
        return profile['p_zero']
    # 取中段：年初年末的資料可能不完整，兩端的樣本代表性較差
    start = ticks[len(ticks) // 4]
    end = start + CALIBRATION_SAMPLE_TICKS

    target = profile['p_zero']
    p_stick = target
    for _ in range(CALIBRATION_ROUNDS):
        probe = dict(profile, p_stick=p_stick)
        # 校準時關掉雨型：要調的是平時的黏滯，不是事件
        series = synth_series(device_uid, probe, history.get, start, end,
                              surge_probability=0.0)
        values = [value for _ts, value, _seq in series]
        unchanged = sum(1 for i in range(1, len(values))
                        if abs(values[i] - values[i - 1]) < 1e-9)
        measured = unchanged / (len(values) - 1)
        if abs(measured - target) < CALIBRATION_TOLERANCE:
            break
        p_stick = max(0.0, min(0.99, p_stick + (target - measured)))
    return p_stick


def load_profile(raw):
    """device.demo_profile（JSON 字串）→ dict。壞掉就明講，不要靜默用預設值跑。"""
    if not raw:
        raise ValueError('這台監測站沒有示範資料統計輪廓（demo_profile 是空的），'
                         '請先用 tools/water_level_demo/load_history.py 匯入歷史資料。')
    profile = json.loads(raw)
    for key in ('p_zero', 'sigma', 'min', 'max', 'median'):
        if key not in profile:
            raise ValueError('示範資料統計輪廓缺少必要欄位「%s」' % key)
    return profile
