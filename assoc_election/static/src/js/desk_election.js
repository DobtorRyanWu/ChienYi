/*
 * 報到台：選舉領票（產生 QR）、配對確認、作廢重發。
 * 掛在 assoc_meeting 的 window.AxDesk 上；DOM 一律 textContent。
 * 配對碼刻意不從伺服器取得：選務必須看會員手機並手動輸入。
 */
(function () {
    'use strict';

    var AxDesk = window.AxDesk;
    if (!AxDesk) { return; }

    var PAIR_CODE_DIGITS = 4;
    var STATE_TEXT = { eligible: '未領票', issued: '已領票', voted: '已投票', voided: '已作廢，待重新領票' };

    var watched = [];        // 目前台面上這位會員的 voter_id
    var lastRendered = {};   // voter_id → 上次渲染的鍵；沒變就不重繪，避免清掉輸入到一半的配對碼
    var qrByVoter = {};      // voter_id → { src, expiresAt }

    AxDesk.pollParams.push(function () { return watched.length ? { voter_ids: watched } : {}; });

    function extra() { return AxDesk.root && AxDesk.root.querySelector('[data-ax="desk-extra"]'); }
    function cardsBox() { var x = extra(); return x && x.querySelector('[data-ax="voter-cards"]'); }
    function canReissue() { var x = extra(); return !!x && x.getAttribute('data-can-reissue') === '1'; }
    var el = function (tag, cls, text) { return AxDesk.el(tag, cls, text); };

    function qrActive(card) {
        var qr = qrByVoter[card.voter_id];
        return !!qr && Date.now() < qr.expiresAt && card.state === 'issued' && !card.claimed;
    }

    function renderStats(elections) {
        var box = extra() && extra().querySelector('[data-ax="election-stats"]');
        if (!box) { return; }
        box.textContent = '';
        box.hidden = !elections.length;
        elections.forEach(function (e) {
            var line = el('div', null, e.name + '｜已投 ' + e.voted_count + ' / 名冊 ' + e.voter_count +
                '｜已領未投 ' + e.issued_count + '｜未領 ' + e.unissued_count);
            if (e.conflict_count) {
                line.appendChild(el('span', 'ax-badge ms-2', '領取衝突 ' + e.conflict_count));
            }
            if (e.state === 'closing') {
                line.appendChild(el('span', 'ax-badge ms-2', '已停止領票'));
            }
            box.appendChild(line);
        });
    }

    function showError(section, message) {
        var old = section.querySelector('[data-ax="card-error"]');
        if (old) { old.remove(); }
        var box = el('div', 'ax-result ax-result--error', message);
        box.setAttribute('data-ax', 'card-error');
        section.appendChild(box);
    }

    function renderCard(card, force) {
        var box = cardsBox();
        if (!box) { return; }
        var key = JSON.stringify(card) + (qrActive(card) ? '|qr' : '');
        if (!force && lastRendered[card.voter_id] === key) { return; }
        lastRendered[card.voter_id] = key;

        var section = box.querySelector('[data-voter="' + Number(card.voter_id) + '"]');
        if (!section) {
            section = el('section', 'ax-card');
            section.setAttribute('data-voter', String(Number(card.voter_id)));
            box.appendChild(section);
        }
        section.textContent = '';
        section.appendChild(el('h2', 'ax-label', card.election_name + '｜' + card.name + '（' + card.member_no + '）'));
        section.appendChild(el('div', 'ax-muted', '選票狀態：' + (STATE_TEXT[card.state] || card.state)));

        var open = card.election_state === 'open';
        var canIssue = open && (card.state === 'eligible' || card.state === 'voided' ||
                                (card.state === 'issued' && !card.claimed));

        if (card.state === 'voted') {
            section.appendChild(el('div', 'ax-result ax-result--ok', '✓ 已投票'));
        } else if (card.conflict) {
            section.appendChild(el('div', 'ax-result ax-result--error',
                '⚠ 領取衝突：這張選票已被其他裝置領取。請選務人員作廢重發。'));
        } else if (card.state === 'issued' && card.armed) {
            section.appendChild(el('div', 'ax-result ax-result--ok', '✓ 已完成配對，會員可以投票'));
        } else if (card.state === 'issued' && card.claimed) {
            section.appendChild(renderArm(card, section));
        } else if (qrActive(card)) {
            var img = AxDesk.safeImg(qrByVoter[card.voter_id].src);
            if (img) { img.className = 'ax-qr'; section.appendChild(img); }
            section.appendChild(el('div', 'ax-muted text-center', '請會員用手機相機掃描（' +
                Math.round((qrByVoter[card.voter_id].expiresAt - Date.now()) / 1000) + ' 秒內有效）'));
        } else if (card.state === 'issued') {
            section.appendChild(el('div', 'ax-result ax-result--warn', 'QR 已過期，請重新產生'));
        }

        var actions = el('div', 'd-flex gap-2 mt-2 flex-wrap');
        if (canIssue) {
            var issueBtn = el('button', 'ax-btn ax-btn--primary',
                card.state === 'issued' ? '重新產生 QR' : '領票（產生 QR）');
            issueBtn.type = 'button';
            issueBtn.addEventListener('click', function () {
                issueBtn.disabled = true;
                AxDesk.rpc(AxDesk.base + '/issue', { voter_id: card.voter_id }).then(function (res) {
                    if (res.status === 'issued') {
                        qrByVoter[card.voter_id] = { src: res.qr, expiresAt: Date.now() + res.expires_in * 1000 };
                        renderCard(res.card, true);
                    } else {
                        renderCard(res.card, true);
                        showError(box.querySelector('[data-voter="' + Number(card.voter_id) + '"]'), res.message);
                    }
                }, function (err) { issueBtn.disabled = false; showError(section, err.message); });
            });
            actions.appendChild(issueBtn);
        } else if (!open && card.state !== 'voted' && !(card.state === 'issued' && card.claimed)) {
            section.appendChild(el('div', 'ax-muted', '目前不是領票時段'));
        }
        if (canReissue() && card.state === 'issued' && open) {
            var voidBtn = el('button', 'ax-btn ax-btn--danger', '作廢重發');
            voidBtn.type = 'button';
            voidBtn.addEventListener('click', function () {
                var reason = window.prompt('作廢重發原因（必填，會寫入稽核鏈）');
                if (!reason || !reason.trim()) { return; }
                AxDesk.rpc(AxDesk.base + '/reissue', { voter_id: card.voter_id, reason: reason }).then(function (res) {
                    delete qrByVoter[card.voter_id];
                    renderCard(res.card, true);
                    if (res.status !== 'voided') {
                        showError(box.querySelector('[data-voter="' + Number(card.voter_id) + '"]'), res.message);
                    }
                }, function (err) { showError(section, err.message); });
            });
            actions.appendChild(voidBtn);
        }
        if (actions.childNodes.length) { section.appendChild(actions); }
    }

    function renderArm(card, section) {
        var wrap = el('div', 'mt-2');
        wrap.appendChild(el('label', 'ax-label', '請看會員手機，輸入畫面上的 ' + PAIR_CODE_DIGITS + ' 位配對碼'));
        var row = el('div', 'd-flex gap-2 align-items-center');
        var input = el('input', 'ax-input ax-input--code');
        input.inputMode = 'numeric';
        input.maxLength = PAIR_CODE_DIGITS;
        input.autocomplete = 'off';
        var btn = el('button', 'ax-btn ax-btn--primary', '確認配對');
        btn.type = 'button';
        function submit() {
            var code = input.value.trim();
            if (!new RegExp('^\\d{' + PAIR_CODE_DIGITS + '}$').test(code)) {
                showError(section, '配對碼是 ' + PAIR_CODE_DIGITS + ' 位數字');
                return;
            }
            btn.disabled = true;
            AxDesk.rpc(AxDesk.base + '/arm', { voter_id: card.voter_id, pair_code: code }).then(function (res) {
                if (res.status === 'armed') {
                    renderCard(res.card, true);
                } else {
                    btn.disabled = false;
                    input.value = '';
                    showError(section, '配對碼不符，或這張選票已有衝突／尚未領取');
                }
            }, function (err) { btn.disabled = false; showError(section, err.message); });
        }
        btn.addEventListener('click', submit);
        input.addEventListener('keydown', function (ev) { if (ev.key === 'Enter') { ev.preventDefault(); submit(); } });
        row.appendChild(input);
        row.appendChild(btn);
        wrap.appendChild(row);
        setTimeout(function () { input.focus(); }, 0);
        return wrap;
    }

    AxDesk.onScan.push(function (res) {
        if (!res || !res.member_id) { return; }
        AxDesk.rpc(AxDesk.base + '/voters', { member_id: res.member_id }).then(function (cards) {
            watched = cards.map(function (card) { return card.voter_id; });
            lastRendered = {};
            qrByVoter = {};
            var box = cardsBox();
            if (box) { box.textContent = ''; }
            cards.forEach(function (card) { renderCard(card, true); });
        });
    });

    AxDesk.onPoll.push(function (res) {
        if (res.elections) { renderStats(res.elections); }
        (res.voters || []).forEach(function (card) {
            if (watched.indexOf(card.voter_id) !== -1) { renderCard(card, false); }
        });
    });
})();
