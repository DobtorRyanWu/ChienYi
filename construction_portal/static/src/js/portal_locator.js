/**
 * /construction 定位 splash (v11.1 純 GPS 入口)
 *
 * 流程:
 * 1. 取得瀏覽器 GPS 座標
 * 2. POST /construction/nearest → 拿到 nearest project_id
 * 3. 找到 → 立刻跳轉(無倒數);找不到 / 失敗 → 跳工程列表
 *
 * 「手動選擇」入口在 drawer 的「工程列表」(/construction?view=list)
 * 與 HUD topbar 的下拉切換器,跟此 splash 路徑完全分離。
 */
(function () {
    'use strict';

    function go(url) {
        window.location.replace(url);
    }

    function gotoList() {
        go('/construction?view=list');
    }

    function setStatus(title, hint) {
        var t = document.getElementById('cy-locator-title');
        var h = document.getElementById('cy-locator-hint');
        if (t) { t.textContent = title; }
        if (h) { h.textContent = hint; }
    }

    function fetchNearest(lat, lng) {
        return fetch('/construction/nearest', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'same-origin',
            body: JSON.stringify({
                jsonrpc: '2.0',
                method: 'call',
                params: { lat: lat, lng: lng },
            }),
        }).then(function (resp) {
            return resp.json();
        }).then(function (data) {
            var result = data && data.result;
            if (result && result.project_id) {
                go('/construction/' + result.project_id);
            } else {
                gotoList();
            }
        }).catch(function () {
            gotoList();
        });
    }

    function init() {
        if (!document.querySelector('.cy-locator')) {
            return;
        }

        if (!navigator.geolocation) {
            setStatus('此瀏覽器不支援定位', '改為顯示工程列表…');
            setTimeout(gotoList, 400);
            return;
        }

        navigator.geolocation.getCurrentPosition(
            function (pos) {
                setStatus('已取得位置,正在比對最近的案件…', '');
                fetchNearest(pos.coords.latitude, pos.coords.longitude);
            },
            function () {
                setStatus('無法取得位置', '改為顯示工程列表…');
                setTimeout(gotoList, 400);
            },
            { enableHighAccuracy: true, timeout: 8000, maximumAge: 60000 }
        );
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
