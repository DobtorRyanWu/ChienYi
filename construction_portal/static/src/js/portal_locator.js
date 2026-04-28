/**
 * /construction 定位中介頁
 *
 * 流程:
 * 1. 若 localStorage.cy_skip_locator === '1' → 直接跳列表
 * 2. 取得瀏覽器 GPS 座標
 * 3. POST /construction/nearest → 拿到 project_id
 * 4. 跳轉到 /construction/<id>(找不到則跳列表)
 * 5. 任何錯誤 / timeout / 拒絕授權 → 跳列表
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
        // Odoo type='json' route 走 JSON-RPC 2.0 包裝
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
        // 只在 splash 頁啟動
        if (!document.querySelector('.cy-locator')) {
            return;
        }

        // 使用者上次選擇「改用列表」
        try {
            if (window.localStorage && localStorage.getItem('cy_skip_locator') === '1') {
                gotoList();
                return;
            }
        } catch (e) { /* localStorage 不可用就忽略 */ }

        // 「改用列表」按鈕:記住偏好
        var skipBtn = document.getElementById('cy-locator-skip');
        if (skipBtn) {
            skipBtn.addEventListener('click', function () {
                try { localStorage.setItem('cy_skip_locator', '1'); } catch (e) {}
            });
        }

        if (!navigator.geolocation) {
            setStatus('此瀏覽器不支援定位', '改為顯示工程案件列表…');
            setTimeout(gotoList, 600);
            return;
        }

        navigator.geolocation.getCurrentPosition(
            function (pos) {
                setStatus('已取得位置,正在比對最近的案件…', '');
                fetchNearest(pos.coords.latitude, pos.coords.longitude);
            },
            function () {
                setStatus('無法取得位置', '改為顯示工程案件列表…');
                setTimeout(gotoList, 600);
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
