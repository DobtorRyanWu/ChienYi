/*
 * 手機投票頁：自動領取、圈選上限、名單外搜尋、確認後投出、配對狀態輪詢。
 * DOM 一律 textContent；伺服器回來的會員 id 先驗證為整數再使用。
 */
(function () {
    'use strict';

    var ARM_POLL_MS = 3000;
    var WRITEIN_MIN_CHARS = 2;
    var WRITEIN_DEBOUNCE_MS = 300;
    // 自動送出後過了這麼久頁面還沒離開，才顯示手動按鈕（慢網路下太早出現會讓使用者重複送出）
    var CLAIM_BUTTON_DELAY_MS = 6000;

    function rpc(url, params) {
        return fetch(url, {
            method: 'POST',
            credentials: 'same-origin',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ jsonrpc: '2.0', method: 'call', params: params || {} }),
        }).then(function (r) { return r.json(); }).then(function (data) {
            if (data.error) { throw new Error('伺服器錯誤'); }
            return data.result;
        });
    }

    function el(tag, cls, text) {
        var node = document.createElement(tag);
        if (cls) { node.className = cls; }
        if (text !== undefined && text !== null) { node.textContent = String(text); }
        return node;
    }

    function initClaim(root) {
        var form = root.querySelector('[data-ax="claim-form"]');
        if (!form) { return; }
        var hint = root.querySelector('[data-ax="claim-hint"]');
        var match = /(?:^#|&)t=([A-Za-z0-9_-]+)/.exec(window.location.hash || '');
        if (!match) {
            hint.textContent = '請用手機相機掃描報到台螢幕上的 QR Code 領取選票。';
            return;
        }
        form.querySelector('input[name="t"]').value = match[1];
        // 立刻把領取碼從網址列與瀏覽紀錄移除
        window.history.replaceState(null, '', window.location.pathname);
        var leaving = false;
        var btn = root.querySelector('[data-ax="claim-btn"]');
        window.addEventListener('pagehide', function () { leaving = true; });
        btn.addEventListener('click', function () {
            // 讓按鈕自己的送出照常進行，下一輪事件迴圈再停用，避免連點
            setTimeout(function () { btn.disabled = true; }, 0);
            hint.textContent = '正在領取選票，請稍候…';
        });
        // 用 form.submit()：實測 requestSubmit() 在延遲載入的腳本裡呼叫時不會觸發送出
        form.submit();
        setTimeout(function () {
            if (leaving) { return; }
            hint.textContent = '若畫面沒有自動跳轉，請按「領取選票」。';
            btn.hidden = false;
        }, CLAIM_BUTTON_DELAY_MS);
    }

    function initBallot(root, uuid) {
        var form = root.querySelector('[data-ax="ballot-form"]');
        if (!form) { return; }
        var sections = Array.prototype.slice.call(form.querySelectorAll('[data-office]'));

        function boxes(section) { return Array.prototype.slice.call(section.querySelectorAll('input[type="checkbox"]')); }

        function refresh(section) {
            var max = parseInt(section.getAttribute('data-max'), 10);
            var checked = boxes(section).filter(function (b) { return b.checked; }).length;
            boxes(section).forEach(function (b) {
                b.disabled = !b.checked && checked >= max;
                b.closest('.ax-choice').classList.toggle('ax-choice--checked', b.checked);
            });
            var counter = section.querySelector('[data-ax="counter"]');
            counter.textContent = '已圈選 ' + checked + ' / ' + max;
            counter.classList.toggle('ax-counter--full', checked >= max);
        }

        function addChoice(section, member) {
            var choices = section.querySelector('[data-ax="choices"]');
            var existing = boxes(section).filter(function (b) { return b.value === String(member.id); })[0];
            if (existing) {
                existing.checked = true;
                refresh(section);
                return;
            }
            var label = el('label', 'ax-choice');
            var box = el('input');
            box.type = 'checkbox';
            box.name = section.getAttribute('data-office');
            box.value = String(member.id);
            var max = parseInt(section.getAttribute('data-max'), 10);
            box.checked = boxes(section).filter(function (b) { return b.checked; }).length < max;
            var text = el('span');
            text.appendChild(el('span', null, member.name)).setAttribute('data-ax', 'choice-name');
            text.appendChild(el('span', 'ax-muted', ' ' + member.member_no + '（名單外）'));
            label.appendChild(box);
            label.appendChild(text);
            choices.appendChild(label);
            refresh(section);
        }

        sections.forEach(function (section) {
            section.addEventListener('change', function () { refresh(section); });
            refresh(section);
            var q = section.querySelector('[data-ax="writein-q"]');
            var results = section.querySelector('[data-ax="writein-results"]');
            var timer = null;
            q.addEventListener('input', function () {
                clearTimeout(timer);
                timer = setTimeout(function () {
                    var term = q.value.trim();
                    results.textContent = '';
                    if (term.length < WRITEIN_MIN_CHARS) { return; }
                    rpc('/assoc/vote/' + uuid + '/members', { q: term }).then(function (rows) {
                        results.textContent = '';
                        if (!rows.length) { results.appendChild(el('li', 'ax-muted', '查無符合的會員')); }
                        rows.forEach(function (row) {
                            if (!Number.isInteger(row.id)) { return; }
                            var li = el('li');
                            li.appendChild(el('span', null, row.name + '　' + row.member_no));
                            var btn = el('button', 'ax-btn', '加入');
                            btn.type = 'button';
                            btn.addEventListener('click', function () {
                                addChoice(section, row);
                                q.value = '';
                                results.textContent = '';
                            });
                            li.appendChild(btn);
                            results.appendChild(li);
                        });
                    }, function () { results.appendChild(el('li', 'ax-muted', '搜尋失敗，請稍後再試')); });
                }, WRITEIN_DEBOUNCE_MS);
            });
        });

        var review = form.querySelector('[data-ax="review"]');
        var reviewBody = form.querySelector('[data-ax="review-body"]');
        var toReview = form.querySelector('[data-ax="to-review"]');
        toReview.addEventListener('click', function () {
            reviewBody.textContent = '';
            sections.forEach(function (section) {
                var names = boxes(section).filter(function (b) { return b.checked; }).map(function (b) {
                    return b.closest('.ax-choice').querySelector('[data-ax="choice-name"]').textContent;
                });
                reviewBody.appendChild(el('div', 'ax-label mt-2', section.getAttribute('data-label')));
                reviewBody.appendChild(el('div', null, names.length ? names.join('、') : '（空白：本職位將計為廢票）'));
            });
            review.hidden = false;
            toReview.hidden = true;
            review.scrollIntoView({ behavior: 'smooth' });
        });
        form.querySelector('[data-ax="back"]').addEventListener('click', function () {
            review.hidden = true;
            toReview.hidden = false;
        });
        form.addEventListener('submit', function () {
            form.querySelector('[data-ax="submit"]').disabled = true;
        });

        var armStatus = root.querySelector('[data-ax="arm-status"]');
        if (armStatus && armStatus.getAttribute('data-armed') !== '1') {
            var armTimer = setInterval(function () {
                if (document.hidden) { return; }
                rpc('/assoc/vote/' + uuid + '/status', {}).then(function (res) {
                    if (res.state !== 'issued') {
                        clearInterval(armTimer);
                        window.location.reload();
                    } else if (res.armed) {
                        clearInterval(armTimer);
                        armStatus.textContent = '✓ 已完成配對，可以投票';
                        armStatus.setAttribute('data-armed', '1');
                    }
                });
            }, ARM_POLL_MS);
        }
    }

    function init() {
        var root = document.querySelector('.ax-vote');
        if (!root) { return; }
        var uuid = root.getAttribute('data-uuid');
        if (!/^[0-9a-f-]{36}$/.test(uuid || '')) { return; }
        initClaim(root);
        initBallot(root, uuid);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
