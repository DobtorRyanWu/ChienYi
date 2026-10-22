/*
 * 報到台：禮品領取。掛在 assoc_meeting 的 window.AxDesk 上；DOM 一律 textContent。
 *
 * 掃到會員之後自動查一次「他現在領得到什麼」，預設全部勾選、一鍵領走——
 * 四百人的隊伍沒有時間逐項勾。未出席的照樣列出來但不給勾，並寫明原因：
 * 現場最怕「畫面上沒有」，承辦會改用手動，而手動就沒有出席把關了。
 */
(function () {
    'use strict';

    var AxDesk = window.AxDesk;
    if (!AxDesk) { return; }

    var STATUS_TEXT = {
        claimed: '已領取',
        already: '這一份已經領過了',
        not_attended: '尚未報到',
        not_pickup: '這是造冊發放的品項，現場不發',
        no_permission: '沒有領取資格（委託可能已取消）',
        invalid: '找不到這一筆'
    };

    var current = { memberId: null, deskRef: null, rows: [] };
    var el = function (tag, cls, text) { return AxDesk.el(tag, cls, text); };

    function extra() { return AxDesk.root && AxDesk.root.querySelector('[data-ax="desk-extra"]'); }

    function panel() {
        var host = extra();
        if (!host) { return null; }
        var box = host.querySelector('[data-ax="gift-panel"]');
        if (!box) {
            box = el('section', 'ax-card');
            box.setAttribute('data-ax', 'gift-panel');
            host.appendChild(box);
        }
        return box;
    }

    function say(box, text) {
        box.textContent = '';
        box.appendChild(el('div', 'ax-result', text));
    }

    // 結果區**不在**重繪範圍內：領完會自動重查一次，
    // 如果整個面板重繪，剛顯示的「哪幾項領到了」會被當場清掉——承辦來不及看。
    function resultBox() {
        var host = extra();
        if (!host) { return null; }
        var out = host.querySelector('[data-ax="gift-result"]');
        if (!out) {
            out = el('section', 'ax-card ax-result');
            out.setAttribute('data-ax', 'gift-result');
            host.appendChild(out);
        }
        return out;
    }

    function render(res) {
        var box = panel();
        if (!box) { return; }
        box.textContent = '';
        current.rows = res.rows || [];
        if (!current.rows.length) {
            box.hidden = true;
            return;
        }
        box.hidden = false;
        box.appendChild(el('div', 'ax-label', '禮品領取（' + (res.holder_name || '') + '）'));

        var list = el('ul', 'ax-list');
        current.rows.forEach(function (row) {
            var li = el('li');
            var label = el('label');
            var check = document.createElement('input');
            check.type = 'checkbox';
            check.value = String(row.id);
            check.checked = !row.blocked;
            check.disabled = !!row.blocked;
            check.setAttribute('data-ax', 'gift-check');
            label.appendChild(check);
            var text = row.item_name + '　' + row.member_no + ' ' + row.member_name;
            if (!row.is_self) { text += '（代領）'; }
            if (row.blocked) { text += '　— ' + row.blocked_reason; }
            label.appendChild(el('span', null, ' ' + text));
            li.appendChild(label);
            list.appendChild(li);
        });
        box.appendChild(list);

        var claimAll = el('button', 'ax-btn ax-btn--primary', '領取勾選的');
        claimAll.type = 'button';
        claimAll.setAttribute('data-ax', 'gift-claim');
        claimAll.addEventListener('click', function () { claim(box); });
        box.appendChild(claimAll);
        resultBox();
    }

    function claim(box) {
        var checks = box.querySelectorAll('[data-ax="gift-check"]');
        var ids = [];
        Array.prototype.forEach.call(checks, function (node) {
            if (node.checked) { ids.push(parseInt(node.value, 10)); }
        });
        if (!ids.length) {
            say(resultBox() || box, '沒有勾選任何品項。');
            return;
        }
        var params = { member_id: current.memberId, ids: ids, desk_ref: current.deskRef };
        AxDesk.rpc(AxDesk.base + '/gift/claim', params).then(function (res) {
            if (res.status === 'need_reason') {
                var reason = window.prompt('沒有掃到會員卡，請填寫原因（必填）');
                if (!reason) { return; }
                params.reason = reason;
                AxDesk.rpc(AxDesk.base + '/gift/claim', params).then(function (again) {
                    report(box, again);
                });
                return;
            }
            report(box, res);
        });
    }

    function report(box, res) {
        var out = resultBox();
        if (!out) { return; }
        out.textContent = '';
        if (res.status === 'invalid' || res.message) {
            out.appendChild(el('div', null, res.message || '無法領取。'));
            return;
        }
        var byId = {};
        current.rows.forEach(function (row) { byId[row.id] = row; });
        out.appendChild(el('div', 'ax-label', '領取 ' + (res.claimed || 0) + ' 份'));
        (res.results || []).forEach(function (one) {
            var row = byId[one.id] || {};
            var name = (row.item_name || '') + '　' + (row.member_name || '');
            out.appendChild(el('div', null, name + '：' + (STATUS_TEXT[one.status] || one.status)));
        });
        // 領完重查一次：剩下的才是還沒領的，承辦不會對著舊畫面再按一次
        lookup(current.memberId, current.deskRef);
    }

    function lookup(memberId, deskRef) {
        if (!memberId) { return; }
        current.memberId = memberId;
        current.deskRef = deskRef || null;
        AxDesk.rpc(AxDesk.base + '/gift/lookup', { member_id: memberId }).then(function (res) {
            if (res.status === 'no_campaign') {
                var box = panel();
                if (box) { box.hidden = true; }
                return;
            }
            render(res);
        });
    }

    AxDesk.onScan.push(function (res) {
        if (res && res.member_id) {
            lookup(res.member_id, res.desk_ref);
        }
    });
}());
