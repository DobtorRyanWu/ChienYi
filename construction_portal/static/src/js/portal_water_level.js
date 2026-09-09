/**
 * 水位監測前台（v11）—— vanilla JS，不用 OWL、不用 jQuery。
 *
 * 幾件事寫在前面：
 * - Chart.js 不進 assets_frontend：它 570KB，掛進 bundle 等於每一頁 portal 都揹著它。
 *   這裡只在本頁動態載入 Odoo 內建的 /web/static/lib/Chart/Chart.js（v4.4.1）。
 * - x 軸用 category（後端已把 label 格式化好），不用 time 軸——Chart.js v4 的 time 軸
 *   要另外載 date adapter，為了一條折線背一個外部相依不划算。
 * - Leaflet 已由 web_leaflet_lib 掛進 frontend bundle，這裡直接用 window.L。
 * - 30 秒輪詢。水位資料 30 秒跟即時沒有實質差別，維護成本差一個數量級。
 */
(function () {
    'use strict';

    var POLL_INTERVAL_MS = 30000;
    var CHART_LIB_URL = '/web/static/lib/Chart/Chart.js';
    var HOURS_PER_DAY = 24;
    var RANGE_WEEK_HOURS = 24 * 7;
    var RANGE_MONTH_HOURS = 24 * 30;
    // 匯出圖上方的抬頭：站名一行 + 區間一行；示範站再多一行紅色警語
    var PNG_HEADER_PX = 44;
    var PNG_HEADER_PX_DEMO = 62;
    var GAUGE_HEADROOM = 1.15;      // 水尺頂端留的餘裕（相對最高警戒線）
    var GAUGE_MIN_TOP = 1.0;        // 沒有任何警戒值時的最小量程（公尺）
    var MINOR_TICK_M = 0.1;         // 10 公分一格
    var MAJOR_TICK_M = 1.0;         // 1 公尺一個數字
    var MAX_TICKS = 120;            // 量程太大時不要畫到瀏覽器跪下
    var TILE_PRIMARY = 'https://tile.openstreetmap.org/{z}/{x}/{y}.png';
    var TILE_FALLBACK = 'https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png';
    var TILE_FAIL_THRESHOLD = 3;
    var TILE_MAX_ZOOM = 19;
    var MAP_PIN_ZOOM = 15;

    // 狀態標籤。低水位（社區蓄水池缺水）與高水位（工程河川漲水）共用同一個 state 欄位。
    var STATE_LABEL = {
        normal: '正常',
        lv3: '三級警戒', lv2: '二級警戒', lv1: '一級警戒',
        low3: '低水位注意', low2: '低水位警戒', low1: '嚴重缺水',
        offline: '斷線',
    };
    var CHIP_LABEL = {
        normal: '正常',
        lv3: '三級', lv2: '二級', lv1: '一級',
        low3: '低3', low2: '低2', low1: '低1',
        offline: '斷線',
    };
    // 未知狀態的顯示。**不要 fallback 成「正常」**——後端加了新狀態而前端沒跟上時，
    // 缺水會被標成正常，這種「錯得像對的」比直接壞掉更危險。
    var UNKNOWN_LABEL = '未知狀態';

    var app = null;
    var state = {
        // 'project' = 工程河川頁（水尺 + 上下游站台）；'community' = 社區蓄水池頁（儲水率卡片）
        mode: 'project',
        endpoint: null,
        projectId: null,
        hours: 24,
        selectedId: null,
        devices: [],
        chart: null,
        map: null,
        markers: {},
        timer: null,
        // 自訂區間：{dateFrom, hourFrom, dateTo, hourTo}。一旦設定就停掉輪詢——
        // 歷史區間不會有新資料，繼續輪詢只會在使用者手指底下重繪表格。
        custom: null,
        lastSeries: null,
        pending: false,
    };

    function $(id) { return document.getElementById(id); }

    function cssVar(name) {
        return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
    }

    function rpc(url, params) {
        return fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ jsonrpc: '2.0', method: 'call', params: params || {} }),
        }).then(function (r) { return r.json(); })
          .then(function (data) { return (data && data.result) || {}; });
    }

    function loadChartLib() {
        if (window.Chart) { return Promise.resolve(); }
        return new Promise(function (resolve, reject) {
            var s = document.createElement('script');
            s.src = CHART_LIB_URL;
            s.onload = resolve;
            s.onerror = function () { reject(new Error('Chart.js 載入失敗')); };
            document.head.appendChild(s);
        });
    }

    // ==================== 水尺 ====================

    function gaugeTop(device) {
        var levels = device.levels || {};
        var candidates = [levels.lv1, levels.lv2, levels.lv3, device.value];
        var top = 0;
        candidates.forEach(function (v) { if (v && v > top) { top = v; } });
        return Math.max(top * GAUGE_HEADROOM, GAUGE_MIN_TOP);
    }

    function renderGauge(device) {
        var ticksEl = $('wlGaugeTicks');
        var linesEl = $('wlHeroLines');
        var waterEl = $('wlGaugeWater');
        var surfaceEl = $('wlGaugeSurface');
        if (!ticksEl || !linesEl || !waterEl) { return; }

        var top = gaugeTop(device);
        var pct = function (v) { return Math.max(0, Math.min(100, (v / top) * 100)); };

        // 刻度
        var html = '';
        var stepCount = Math.round(top / MINOR_TICK_M);
        var step = stepCount > MAX_TICKS ? MAJOR_TICK_M : MINOR_TICK_M;
        for (var v = 0; v <= top + 1e-9; v += step) {
            var isMajor = Math.abs(v / MAJOR_TICK_M - Math.round(v / MAJOR_TICK_M)) < 1e-6;
            var width = isMajor ? 18 : 10;
            html += '<div class="wl-gauge-tick' + (isMajor ? ' is-major' : '') +
                    '" style="bottom:' + pct(v) + '%;width:' + width + 'px"></div>';
            if (isMajor && v > 0) {
                html += '<div class="wl-gauge-tick-label" style="bottom:' + pct(v) + '%">' +
                        v.toFixed(0) + '</div>';
            }
        }
        ticksEl.innerHTML = html;

        // 三條警戒線：橫穿水尺再延伸到右邊，右端標等級與數值
        var levels = device.levels || {};
        var lineLabel = { lv3: '三級', lv2: '二級', lv1: '一級' };
        var lineHtml = '';
        ['lv3', 'lv2', 'lv1'].forEach(function (key) {
            if (!levels[key]) { return; }
            var bottom = pct(levels[key]);
            lineHtml += '<div class="wl-hero-line is-' + key + '" style="bottom:' + bottom + '%"></div>' +
                        '<div class="wl-hero-line-label is-' + key + '" style="bottom:' + bottom + '%">' +
                        lineLabel[key] + ' ' + levels[key].toFixed(2) + '</div>';
        });
        linesEl.innerHTML = lineHtml;

        // 水面（斷線時不要畫出一個看起來很正常的水位）
        var hasValue = device.value !== null && device.value !== undefined;
        waterEl.style.height = hasValue ? pct(device.value) + '%' : '0%';
        if (surfaceEl) {
            surfaceEl.classList.toggle('is-shown', hasValue);
            surfaceEl.style.bottom = hasValue ? pct(device.value) + '%' : '0%';
        }
    }

    // ==================== 摘要 ====================

    function renderHero(device) {
        if (!$('wlStationName')) { return; }   // 社區頁沒有水尺區塊
        $('wlStationName').textContent = device.name;
        $('wlValue').textContent = (device.value === null || device.value === undefined)
            ? '—' : device.value.toFixed(2);
        var statusEl = $('wlStatus');
        statusEl.textContent = STATE_LABEL[device.state] || (UNKNOWN_LABEL + '（' + device.state + '）');
        statusEl.className = 'wl-status is-' + device.state;
        $('wlSeen').textContent = device.last_seen;

        // 警戒值已經標在水尺的線上了，這裡只在「一條都沒設」時出面提醒，不重複佔版面
        var levels = device.levels || {};
        var hasLevel = levels.lv1 || levels.lv2 || levels.lv3;
        $('wlLevels').textContent = hasLevel ? '' : '本站尚未設定警戒水位';
        renderGauge(device);
    }

    function renderStations(devices) {
        var wrap = $('wlStations');
        if (!wrap) { return; }
        var html = '';
        devices.forEach(function (d, idx) {
            var cls = 'wl-station' + (d.id === state.selectedId ? ' is-active' : '') +
                      (d.state === 'offline' ? ' is-offline' : '');
            var value = (d.value === null || d.value === undefined)
                ? '—' : d.value.toFixed(2) + '<small> m</small>';
            var chipLabel = CHIP_LABEL[d.state] || UNKNOWN_LABEL;
            html += '<button type="button" class="' + cls + '" data-device-id="' + d.id + '">' +
                    '<span class="wl-station-flow"><span class="wl-station-dot"></span>' +
                    (idx < devices.length - 1 ? '<span class="wl-station-line"></span>' : '') +
                    '</span>' +
                    '<span class="wl-station-body">' +
                    '<span class="wl-station-name"></span>' +
                    '<span class="wl-station-seen"></span></span>' +
                    '<span class="wl-station-value">' + value + '</span>' +
                    '<span class="wl-chip wl-chip-' + d.state + '">' + chipLabel + '</span>' +
                    '</button>';
        });
        wrap.innerHTML = html;
        // 站名與時間走 textContent，避免站名帶 HTML 造成注入
        Array.prototype.forEach.call(wrap.querySelectorAll('.wl-station'), function (el, idx) {
            el.querySelector('.wl-station-name').textContent = devices[idx].name;
            el.querySelector('.wl-station-seen').textContent = devices[idx].last_seen;
        });
    }

    // ==================== 圖表 ====================

    function renderChart(series) {
        var canvas = $('wlChart');
        var emptyEl = $('wlChartEmpty');
        if (!canvas || !window.Chart) { return; }

        var hasData = series && series.values && series.values.length;
        emptyEl.classList.toggle('is-shown', !hasData);
        $('wlChartNote').textContent = chartNoteText(series);

        var device = state.devices.filter(function (d) { return d.id === state.selectedId; })[0] || {};
        var levels = device.levels || {};
        var annotations = [];
        [['lv3', '--wb-wl-lv3'], ['lv2', '--wb-wl-lv2'], ['lv1', '--wb-wl-lv1']].forEach(function (pair) {
            if (levels[pair[0]]) {
                annotations.push({ value: levels[pair[0]], color: cssVar(pair[1]) });
            }
        });

        // 警戒線用自訂 plugin 畫，不引入 annotation plugin（那是外部相依）
        var levelLinePlugin = {
            id: 'wlLevelLines',
            afterDatasetsDraw: function (chart) {
                var yScale = chart.scales.y;
                var ctx = chart.ctx;
                annotations.forEach(function (a) {
                    if (a.value < yScale.min || a.value > yScale.max) { return; }
                    var y = yScale.getPixelForValue(a.value);
                    ctx.save();
                    ctx.strokeStyle = a.color;
                    ctx.setLineDash([5, 4]);
                    ctx.lineWidth = 1.5;
                    ctx.beginPath();
                    ctx.moveTo(chart.chartArea.left, y);
                    ctx.lineTo(chart.chartArea.right, y);
                    ctx.stroke();
                    ctx.restore();
                });
            },
        };

        var data = {
            labels: (series && series.labels) || [],
            datasets: [{
                data: (series && series.values) || [],
                borderColor: cssVar('--wb-wl-water'),
                backgroundColor: 'rgba(118,159,205,.14)',
                borderWidth: 2,
                tension: 0.3,
                pointRadius: 0,
                fill: true,
            }],
        };

        if (state.chart) {
            state.chart.data = data;
            state.chart.options.plugins.wlLevelLines = {};
            state.chart.update('none');
            return;
        }
        state.chart = new window.Chart(canvas, {
            type: 'line',
            data: data,
            options: {
                responsive: true,
                maintainAspectRatio: false,
                animation: false,
                interaction: { intersect: false, mode: 'index' },
                plugins: { legend: { display: false } },
                scales: {
                    x: { grid: { display: false }, ticks: { maxTicksLimit: 6, color: cssVar('--wb-t3') } },
                    y: {
                        title: { display: true, text: '水位 (m)', color: cssVar('--wb-t3') },
                        ticks: { color: cssVar('--wb-t3') },
                        grid: { color: 'rgba(128,128,128,.16)' },
                    },
                },
            },
            plugins: [levelLinePlugin],
        });
    }

    // ==================== 社區：水池儲水率卡片 ====================

    function renderTanks(tanks) {
        var wrap = $('wlTanks');
        if (!wrap) { return; }
        var html = '';
        tanks.forEach(function (t) {
            var cls = 'wl-tank is-' + t.status +
                      (t.id === state.selectedId ? ' is-active' : '') +
                      (t.has_device ? '' : ' is-none');
            html += '<button type="button" class="' + cls + '" data-tank-id="' + t.id + '">' +
                    '<span class="wl-tank-head">' +
                    '<span class="wl-tank-name"></span>' +
                    '<span class="wl-tank-usage"></span></span>';
            if (t.has_device) {
                var rate = (t.fill_rate === null || t.fill_rate === undefined)
                    ? '—' : t.fill_rate.toFixed(1) + '<small>%</small>';
                var width = Math.min(100, Math.max(0, t.fill_rate || 0));
                var sub = (t.volume === null || t.volume === undefined)
                    ? '目前無資料'
                    : t.volume.toFixed(1) + ' / ' + t.capacity.toFixed(1) + ' m³';
                html += '<span class="wl-tank-rate">' + rate + '</span>' +
                        '<span class="wl-tank-bar"><span class="wl-tank-bar-fill" style="width:' +
                        width + '%"></span></span>' +
                        '<span class="wl-tank-sub" data-sub="' + sub + '"></span>';
            } else {
                html += '<span class="wl-tank-none">尚未裝表</span>' +
                        '<span class="wl-tank-sub" data-sub="有效容量 ' +
                        t.capacity.toFixed(1) + ' m³"></span>';
            }
            html += '</button>';
        });
        wrap.innerHTML = html;
        // 池名與時間走 textContent，避免名稱帶 HTML 造成注入
        Array.prototype.forEach.call(wrap.querySelectorAll('.wl-tank'), function (el, idx) {
            var t = tanks[idx];
            el.querySelector('.wl-tank-name').textContent = t.name;
            el.querySelector('.wl-tank-usage').textContent = t.usage || '';
            var sub = el.querySelector('.wl-tank-sub');
            sub.textContent = (sub.dataset.sub || '') + ' · ' + t.last_seen;
        });
    }

    // ==================== 地圖 ====================

    function itemStatus(item) {
        // 工程站用 state（normal/lv1…/offline）；社區池用 status（ok/low/high/offline/none）
        return item.state || item.status || 'normal';
    }

    function markerIcon(item) {
        var cls = 'wl-marker is-' + itemStatus(item) +
                  (item.id === state.selectedId ? ' is-active' : '');
        // 有設短標籤就用它（例如 A1），沒設就沿用上下游序——留空的站行為不變
        var label = item.map_label || item.seq || '';
        if (state.mode === 'community') {
            label = (item.fill_rate === null || item.fill_rate === undefined)
                ? '—' : Math.round(item.fill_rate);
        }
        return window.L.divIcon({
            className: '',
            html: '<div class="' + cls + '">' + label + '</div>',
            iconSize: [26, 26],
            iconAnchor: [13, 13],
        });
    }

    function initMap(devices) {
        var el = $('wlMap');
        if (!el || !window.L) { return; }
        var located = devices.filter(function (d) { return d.latitude && d.longitude; });
        if (!located.length) {
            var card = $('wlMapCard');
            if (card) {
                card.style.display = 'none';   // 社區頁沒座標就整張卡收起來
            } else {
                el.style.display = 'none';
                $('wlMapHint').textContent = '站點尚未設定座標（後台可在地圖上點一下標記）';
            }
            return;
        }
        state.map = window.L.map(el, { zoomControl: false });
        window.L.control.zoom({ position: 'topleft' }).addTo(state.map);
        addTiles();
        var bounds = [];
        located.forEach(function (d) {
            var marker = window.L.marker([d.latitude, d.longitude], { icon: markerIcon(d) })
                .addTo(state.map)
                .on('click', function () { selectDevice(d.id); });
            state.markers[d.id] = marker;
            bounds.push([d.latitude, d.longitude]);
        });
        if (bounds.length === 1) {
            state.map.setView(bounds[0], MAP_PIN_ZOOM);
        } else {
            state.map.fitBounds(bounds, { padding: [30, 30] });
        }
        setTimeout(function () { state.map.invalidateSize(); }, 0);
    }

    function addTiles() {
        var failCount = 0;
        var switched = false;
        var primary = window.L.tileLayer(TILE_PRIMARY, {
            attribution: '&copy; OpenStreetMap',
            maxZoom: TILE_MAX_ZOOM,
            crossOrigin: true,
        });
        primary.on('tileerror', function () {
            failCount += 1;
            if (!switched && failCount >= TILE_FAIL_THRESHOLD) {
                switched = true;
                state.map.removeLayer(primary);
                window.L.tileLayer(TILE_FALLBACK, {
                    attribution: '&copy; OpenStreetMap &copy; CARTO',
                    maxZoom: TILE_MAX_ZOOM,
                    subdomains: 'abcd',
                    crossOrigin: true,
                }).addTo(state.map);
            }
        });
        primary.addTo(state.map);
    }

    function refreshMarkers(devices) {
        devices.forEach(function (d) {
            var marker = state.markers[d.id];
            if (marker) { marker.setIcon(markerIcon(d)); }
        });
    }

    // ==================== 區間摘要 / 逐筆表 / 匯出 ====================
    // 這一段的每支 render 都先確認自己的 DOM 在不在：同一支 JS 也服務社區蓄水池頁，
    // 那一頁沒有這些區塊，找不到就整支跳過（與上面 renderTanks / renderStations 同一套做法）。

    function currentDevice() {
        return state.devices.filter(function (d) { return d.id === state.selectedId; })[0] || {};
    }

    function fmtValue(v) {
        return (v === null || v === undefined) ? '--' : Number(v).toFixed(2);
    }

    function chartNoteText(series) {
        var base = series && series.granularity === 'raw'
            ? '每筆原始資料'
            : '每' + (series && series.granularity === 'day' ? '日' : '小時') + '最高水位';
        if (state.custom && series && series.window) {
            return base + '｜' + series.window.from + ' ~ ' + series.window.to + '・暫停自動更新';
        }
        return base;
    }

    function renderStats(series) {
        if (!$('wlStats')) { return; }
        var stats = (series && series.stats) || {};
        var has = stats.count > 0;
        $('wlStatMax').textContent = has ? fmtValue(stats.max) : '--';
        $('wlStatMin').textContent = has ? fmtValue(stats.min) : '--';
        $('wlStatAvg').textContent = has ? fmtValue(stats.avg) : '--';
        $('wlStatCount').textContent = has ? String(stats.count) : '--';
    }

    /** 超過警戒值的列標色。用與圖上警戒線同一組語意色，不另外發明顏色。 */
    function rowLevelClass(value, levels) {
        if (value === null || value === undefined || !levels) { return ''; }
        if (levels.lv1 && value >= levels.lv1) { return 'is-lv1'; }
        if (levels.lv2 && value >= levels.lv2) { return 'is-lv2'; }
        if (levels.lv3 && value >= levels.lv3) { return 'is-lv3'; }
        return '';
    }

    function tableHeadText(series) {
        if (series && series.granularity === 'day') { return '每日最高 (m)'; }
        if (series && series.granularity === 'hour') { return '每小時最高 (m)'; }
        return '水位 (m)';
    }

    function renderTable(series) {
        var body = $('wlTableBody');
        if (!body) { return; }
        var rows = (series && series.rows) || [];
        var levels = currentDevice().levels;
        var wrap = $('wlTableWrap');
        // 輪詢重繪不該把使用者捲到哪裡看的位置吃掉
        var keepScroll = wrap ? wrap.scrollTop : 0;

        var frag = document.createDocumentFragment();
        rows.forEach(function (row) {
            var tr = document.createElement('tr');
            var cls = rowLevelClass(row[1], levels);
            if (cls) { tr.className = cls; }
            var tdTime = document.createElement('td');
            tdTime.textContent = row[0];
            var tdValue = document.createElement('td');
            tdValue.className = 'wl-table-value';
            tdValue.textContent = fmtValue(row[1]);
            tr.appendChild(tdTime);
            tr.appendChild(tdValue);
            frag.appendChild(tr);
        });
        body.textContent = '';
        body.appendChild(frag);
        if (wrap) { wrap.scrollTop = keepScroll; }

        $('wlTableValueHead').textContent = tableHeadText(series);
        $('wlTableEmpty').classList.toggle('is-shown', rows.length === 0);
        $('wlTableNote').textContent = series
            ? ('區間內共 ' + (series.raw_total || 0) + ' 筆') : '';

        var more = $('wlTableMore');
        var truncated = !!(series && series.row_truncated);
        more.hidden = !truncated;
        if (truncated) {
            more.textContent = '只列出最新 ' + rows.length + ' 筆，完整資料請用「匯出表」下載。';
        }
    }

    /** 空圖不能只說「沒有資料」——要說最後一筆是什麼時候，並給一個看得到東西的去處。 */
    function renderEmptyState(series) {
        var titleEl = $('wlChartEmptyTitle');
        if (!titleEl) { return; }   // 社區頁的空狀態是純文字版，不動它
        var subEl = $('wlChartEmptySub');
        var cta = $('wlChartEmptyCta');
        if (series && series.values && series.values.length) {
            cta.hidden = true;
            return;
        }
        var device = currentDevice();
        titleEl.textContent = '這段期間沒有資料';
        subEl.textContent = device.last_ts
            ? ('這一站最後一筆是 ' + device.last_ts + '（' + device.last_seen + '）')
            : '這一站還沒有任何上報紀錄';

        // 建議一個一定看得到資料的快捷區間；自訂區間是使用者自己選的，不越俎代庖
        var age = device.last_ts_age_h;
        var suggest = null;
        if (!state.custom && age !== null && age !== undefined) {
            if (age < RANGE_WEEK_HOURS && state.hours < RANGE_WEEK_HOURS) {
                suggest = RANGE_WEEK_HOURS;
            } else if (age < RANGE_MONTH_HOURS && state.hours < RANGE_MONTH_HOURS) {
                suggest = RANGE_MONTH_HOURS;
            }
        }
        cta.hidden = !suggest;
        if (suggest) {
            cta.textContent = '改看最近 ' + (suggest / HOURS_PER_DAY) + ' 天';
            cta.dataset.hours = String(suggest);
        }
    }

    function renderCustomNote(series) {
        var note = $('wlCustomNote');
        if (!note) { return; }
        if (!state.custom) {
            note.textContent = note.dataset.default || '';
            note.classList.remove('is-warn');
            return;
        }
        var win = (series && series.window) || {};
        note.textContent = win.notice
            ? (win.notice + '：目前顯示 ' + win.from + ' ~ ' + win.to)
            : ('目前顯示 ' + win.from + ' ~ ' + win.to);
        note.classList.toggle('is-warn', !!win.notice);
    }

    /** CSV 走 GET 連結而不是 fetch＋Blob：手機（尤其 iOS）對 blob: 下載的支援不一致。 */
    function syncExportHref() {
        var link = $('wlExportCsv');
        if (!link) { return; }
        var params = ['device_id=' + encodeURIComponent(state.selectedId || '')];
        if (state.custom) {
            params.push('date_from=' + encodeURIComponent(state.custom.dateFrom));
            params.push('hour_from=' + encodeURIComponent(state.custom.hourFrom));
            params.push('date_to=' + encodeURIComponent(state.custom.dateTo));
            params.push('hour_to=' + encodeURIComponent(state.custom.hourTo));
        } else {
            params.push('hours=' + state.hours);
        }
        link.href = '/construction/' + state.projectId + '/water-level/export.csv?' +
                    params.join('&');
    }

    function exportFilename(device) {
        var win = (state.lastSeries && state.lastSeries.window) || {};
        var stamp = (win.from || '') + '-' + (win.to || '');
        return ((device.is_demo ? '示範資料_' : '') + '水位_' + (device.name || '') + '_' +
                stamp).replace(/[\\/:*?"<>|\s]/g, '_') + '.png';
    }

    function ellipsize(ctx, text, maxWidth) {
        if (ctx.measureText(text).width <= maxWidth) { return text; }
        var cut = text;
        while (cut.length > 1 && ctx.measureText(cut + '…').width > maxWidth) {
            cut = cut.slice(0, -1);
        }
        return cut + '…';
    }

    /** 匯出的圖會離開這一頁單獨流傳，所以站名、區間、示範警語都要畫進像素裡。 */
    function exportPng() {
        if (!state.chart) { return; }
        var src = state.chart.canvas;
        var device = currentDevice();
        var ratio = src.clientWidth ? (src.width / src.clientWidth) : 1;
        var headerH = Math.round(
            (device.is_demo ? PNG_HEADER_PX_DEMO : PNG_HEADER_PX) * ratio);
        var out = document.createElement('canvas');
        out.width = src.width;
        out.height = src.height + headerH;
        var ctx = out.getContext('2d');
        // Chart.js 的 canvas 是透明的，直接存圖在深色背景上會看不到線
        ctx.fillStyle = cssVar('--wb-bg2') || '#ffffff';
        ctx.fillRect(0, 0, out.width, out.height);
        ctx.drawImage(src, 0, headerH);

        // 分行寫，不要擠成一行——站名可以很長，擠在一行會被畫布右緣切掉
        var win = (state.lastSeries && state.lastSeries.window) || {};
        var pad = 12 * ratio;
        var maxWidth = out.width - pad * 2;
        ctx.fillStyle = cssVar('--wb-t1') || '#222222';
        ctx.font = Math.round(14 * ratio) + 'px sans-serif';
        ctx.fillText(ellipsize(ctx, device.name || '', maxWidth), pad, 17 * ratio);
        ctx.fillStyle = cssVar('--wb-t3') || '#666666';
        ctx.font = Math.round(11 * ratio) + 'px sans-serif';
        ctx.fillText(ellipsize(ctx, (win.from || '') + ' ~ ' + (win.to || ''), maxWidth),
                     pad, 34 * ratio);
        if (device.is_demo) {
            ctx.fillStyle = cssVar('--wb-wl-lv1') || '#c0392b';
            ctx.fillText(ellipsize(ctx, '示範資料／系統模擬，不是現場量測值', maxWidth),
                         pad, 52 * ratio);
        }
        deliverPng(out.toDataURL('image/png'), exportFilename(device));
    }

    /** iOS 對 <a download> 的行為不一致（連 data: 都可能直接開新頁），
     *  所以 iOS 一律走「把圖顯示出來讓使用者長按儲存」這條一定成立的路。 */
    function deliverPng(dataUrl, filename) {
        var a = document.createElement('a');
        var isIOS = /iP(hone|ad|od)/.test(navigator.userAgent);
        if (('download' in a) && !isIOS) {
            a.href = dataUrl;
            a.download = filename;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            return;
        }
        var img = $('wlPngPreview');
        if (!img) { window.open(dataUrl, '_blank'); return; }
        img.src = dataUrl;
        img.hidden = false;
        $('wlPngHint').hidden = false;
        img.scrollIntoView({ block: 'nearest' });
    }

    // ==================== 區間切換 ====================

    function setRangeButtonsActive(hours) {
        Array.prototype.forEach.call(
            document.querySelectorAll('.wl-range'),
            function (el) {
                el.classList.toggle('is-active',
                    hours !== null && parseInt(el.dataset.hours, 10) === hours);
            });
    }

    function applyCustomRange() {
        var dateFrom = $('wlDateFrom');
        var dateTo = $('wlDateTo');
        if (!dateFrom || !dateTo || !dateFrom.value || !dateTo.value) { return; }
        state.custom = {
            dateFrom: dateFrom.value,
            hourFrom: $('wlHourFrom').value,
            dateTo: dateTo.value,
            hourTo: $('wlHourTo').value,
        };
        stopPolling();
        setRangeButtonsActive(null);
        fetchData();
    }

    function clearCustomRange() {
        if (!state.custom) { return; }
        state.custom = null;
        setRangeButtonsActive(state.hours);
        startPolling();
        fetchData();
    }

    function selectQuickRange(hours) {
        state.custom = null;
        state.hours = hours;
        setRangeButtonsActive(hours);
        startPolling();
        fetchData();
    }

    function stopPolling() {
        if (state.timer) {
            clearInterval(state.timer);
            state.timer = null;
        }
    }

    function startPolling() {
        stopPolling();
        state.timer = setInterval(function () {
            // 分頁在背景時不要打——手機切出去再回來會累積一串沒人看的請求
            if (!document.hidden) { fetchData(); }
        }, POLL_INTERVAL_MS);
    }

    // ==================== 資料流 ====================

    function requestParams() {
        // 社區頁提早 return：它的端點不吃自訂區間，這裡用結構擋住，不靠註解提醒
        if (state.mode === 'community') {
            return { hours: state.hours, tank_id: state.selectedId };
        }
        var params = { hours: state.hours, device_id: state.selectedId };
        if (state.custom) {
            params.date_from = state.custom.dateFrom;
            params.hour_from = state.custom.hourFrom;
            params.date_to = state.custom.dateTo;
            params.hour_to = state.custom.hourTo;
        }
        return params;
    }

    /** 兩種模式的回應長得不一樣，但都是「一組項目 + 選定項目的時序」 */
    function applyData(res) {
        if (!res || res.error) { return false; }
        var items = state.mode === 'community' ? res.tanks : res.devices;
        if (!items) { return false; }
        state.devices = items;
        state.selectedId = res.selected_id;
        if (state.mode === 'community') {
            renderTanks(items);
        } else {
            var selected = items.filter(function (d) { return d.id === state.selectedId; })[0];
            if (selected) { renderHero(selected); }
            renderStations(items);
        }
        refreshMarkers(items);
        state.lastSeries = res.series;
        renderChart(res.series);
        // 以下四支在社區頁沒有對應 DOM，會自己 no-op
        renderStats(res.series);
        renderTable(res.series);
        renderEmptyState(res.series);
        renderCustomNote(res.series);
        syncExportHref();
        return true;
    }

    function fetchData() {
        // 上一發還沒回來就不要疊——切站時連點會讓回應亂序，畫面停在舊站的資料
        if (state.pending) { return Promise.resolve(false); }
        state.pending = true;
        return rpc(state.endpoint, requestParams()).then(function (res) {
            state.pending = false;
            return applyData(res);
        }, function (err) {
            state.pending = false;
            throw err;
        });
    }

    function selectDevice(deviceId) {
        state.selectedId = deviceId;
        fetchData();
    }

    function bindEvents() {
        var stations = $('wlStations');
        if (stations) {
            stations.addEventListener('click', function (ev) {
                var btn = ev.target.closest('.wl-station');
                if (btn) { selectDevice(parseInt(btn.dataset.deviceId, 10)); }
            });
        }
        var tanks = $('wlTanks');
        if (tanks) {
            tanks.addEventListener('click', function (ev) {
                var btn = ev.target.closest('.wl-tank');
                // 沒裝表的池沒有資料可看，點了不換
                if (btn && !btn.classList.contains('is-none')) {
                    selectDevice(parseInt(btn.dataset.tankId, 10));
                }
            });
        }
        $('wlRanges').addEventListener('click', function (ev) {
            var btn = ev.target.closest('.wl-range');
            if (!btn) { return; }
            selectQuickRange(parseInt(btn.dataset.hours, 10));
        });

        // 以下都是工程頁才有的控制項，社區頁抓不到就不綁
        var toggle = $('wlCustomToggle');
        if (toggle) {
            toggle.addEventListener('click', function () {
                var body = $('wlCustomBody');
                var opening = body.hidden;
                body.hidden = !opening;
                toggle.setAttribute('aria-expanded', opening ? 'true' : 'false');
                toggle.classList.toggle('is-open', opening);
            });
        }
        var apply = $('wlCustomApply');
        if (apply) { apply.addEventListener('click', applyCustomRange); }
        var clear = $('wlCustomClear');
        if (clear) { clear.addEventListener('click', clearCustomRange); }
        var png = $('wlExportPng');
        if (png) { png.addEventListener('click', exportPng); }
        var cta = $('wlChartEmptyCta');
        if (cta) {
            cta.addEventListener('click', function () {
                var hours = parseInt(cta.dataset.hours, 10);
                if (hours) { selectQuickRange(hours); }
            });
        }
    }

    function start() {
        app = $('wlApp');
        if (!app) { return; }   // 不是水位頁就什麼都不做
        state.mode = app.dataset.mode === 'community' ? 'community' : 'project';
        state.projectId = parseInt(app.dataset.projectId, 10);
        // 端點由模板給，同一支 JS 服務工程頁與社區頁
        state.endpoint = app.dataset.endpoint ||
            ('/construction/' + state.projectId + '/water-level/data');
        state.hours = parseInt(app.dataset.defaultHours, 10) || 24;

        // 自訂區間提示列的原始文字要留著——切回快捷區間時得還原
        var customNote = $('wlCustomNote');
        if (customNote) { customNote.dataset.default = customNote.textContent.trim(); }

        bindEvents();
        loadChartLib().catch(function (err) {
            if (window.console) { console.warn('[water-level]', err); }
        }).then(function () {
            return rpc(state.endpoint, { hours: state.hours });
        }).then(function (res) {
            var items = res && (state.mode === 'community' ? res.tanks : res.devices);
            if (!items) { return; }
            initMap(items);
            applyData(res);
            startPolling();
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', start);
    } else {
        start();
    }
})();
