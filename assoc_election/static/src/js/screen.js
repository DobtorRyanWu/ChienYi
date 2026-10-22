/*
 * 大螢幕與跑馬燈的輪詢。DOM 一律 textContent（候選人姓名是使用者資料）。
 *
 * 兩個刻意的行為：
 *   - `document.hidden` 時跳過輪詢：投影機常常被切到別的畫面，
 *     沒必要在那段時間繼續打伺服器（投票尖峰每一個連線都算）。
 *   - `pending` 旗標：上一次還沒回來就不發下一次，避免網路慢的時候排隊。
 */
(function () {
    'use strict';

    var DEFAULT_POLL_MS = 5000;
    var RESULT_TEXT = { elected: '當選', alternate: '候補', none: '未當選' };

    function rpc(url, params) {
        return fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ jsonrpc: '2.0', method: 'call', params: params || {} })
        }).then(function (response) {
            return response.json();
        }).then(function (data) {
            if (data.error) { throw new Error(data.error.message || 'rpc'); }
            return data.result;
        });
    }

    function el(tag, className, text) {
        var node = document.createElement(tag);
        if (className) { node.className = className; }
        if (text !== undefined && text !== null) { node.textContent = String(text); }
        return node;
    }

    function poller(intervalMs, tick) {
        var state = { pending: false };
        function run() {
            if (state.pending || document.hidden) { return; }
            state.pending = true;
            tick().catch(function () { /* 網路瞬斷不必洗版，下一輪會再試 */ })
                .then(function () { state.pending = false; });
        }
        run();
        window.setInterval(run, intervalMs);
    }

    // ---------------- 大螢幕 ----------------
    function initScreen() {
        var root = document.querySelector('.ax-screen');
        if (!root) { return; }
        var uuid = root.getAttribute('data-uuid');
        var intervalMs = parseInt(root.getAttribute('data-poll-ms'), 10) || DEFAULT_POLL_MS;
        var q = function (name) { return root.querySelector('[data-ax="' + name + '"]'); };

        function render(res) {
            q('title').textContent = res.name || '';
            q('company').textContent = res.company || '';
            q('message').textContent = res.message || '';

            var stats = q('stats');
            stats.textContent = '';
            if (res.draw_entropy) {
                // 上牆是為了讓全場看到「承辦用的就是剛剛擲出來的那一組」
                stats.appendChild(el('span', null, '號次抽籤亂數 '));
                stats.appendChild(el('span', 'ax-screen__big', res.draw_entropy));
                stats.appendChild(el('span', null, '　'));
            }
            if (res.voted !== undefined) {
                stats.appendChild(el('span', 'ax-screen__big', res.voted));
                stats.appendChild(el('span', null, ' / ' + res.roster));
            } else if (res.roster !== undefined) {
                stats.appendChild(el('span', null, '名冊 '));
                stats.appendChild(el('span', 'ax-screen__big', res.roster));
                stats.appendChild(el('span', null, ' 人'));
            }

            // 沒有鏈頭的狀態（草稿、名冊審定）整列收起來：
            // 顯示「—」看起來像壞掉，而這是要投在會場前方的畫面
            var chain = q('chain');
            var chainRow = chain.closest('.ax-screen__chain');
            chain.textContent = res.chain_head
                ? (res.chain_head + '…（第 ' + res.chain_length + ' 筆）') : '';
            if (chainRow) { chainRow.hidden = !res.chain_head; }

            var box = q('result');
            box.textContent = '';
            ((res.result && res.result.offices) || []).forEach(function (office) {
                box.appendChild(el('h2', null,
                    office.label + '（應選 ' + office.seats + '、候補 ' + office.alternates + '）'));
                var list = el('ol', 'ax-screen__ranking');
                office.rows.forEach(function (row) {
                    var line = el('li');
                    line.appendChild(el('span', 'ax-screen__name', row.name));
                    line.appendChild(el('span', 'ax-screen__votes', row.votes + ' 票'));
                    line.appendChild(el('span', 'ax-screen__outcome',
                        RESULT_TEXT[row.result] || row.result));
                    list.appendChild(line);
                });
                box.appendChild(list);
            });
        }

        poller(intervalMs, function () {
            return rpc('/assoc/screen/' + uuid + '/poll', {}).then(render);
        });
    }

    // ---------------- 跑馬燈 ----------------
    function initTicker() {
        var root = document.querySelector('.ax-ticker');
        if (!root) { return; }
        var companies = root.getAttribute('data-companies') || '';
        var intervalMs = parseInt(root.getAttribute('data-poll-ms'), 10) || DEFAULT_POLL_MS;
        var track = root.querySelector('[data-ax="ticker"]');

        poller(intervalMs, function () {
            return rpc('/assoc/ticker/poll', { c: companies }).then(function (res) {
                track.textContent = '';
                if (!res.items.length) {
                    track.appendChild(el('span', null, '目前沒有已公告的選舉結果。'));
                    return;
                }
                res.items.forEach(function (item) {
                    var chunk = el('span', 'ax-ticker__item');
                    chunk.appendChild(el('strong', null,
                        item.company + '　' + item.name + '（' + item.published_at + '）'));
                    item.winners.forEach(function (winner) {
                        chunk.appendChild(el('span', null,
                            '　' + winner.name + ' ' + winner.votes + ' 票 '
                            + (RESULT_TEXT[winner.result] || '')));
                    });
                    track.appendChild(chunk);
                });
            });
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function () { initScreen(); initTicker(); });
    } else {
        initScreen();
        initTicker();
    }
}());
