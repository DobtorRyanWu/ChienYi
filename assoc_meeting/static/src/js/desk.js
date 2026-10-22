/*
 * 公會報到台：掃會員卡報到、手動簽到、出席輪詢。
 * 選舉模組透過 window.AxDesk 的 onScan / onPoll / pollParams 掛上自己的邏輯。
 * DOM 一律用 textContent 寫入（掃碼槍輸入與會員姓名都不可信）。
 */
(function () {
    'use strict';

    var DEFAULT_POLL_MS = 3000;
    var SEARCH_DEBOUNCE_MS = 300;
    var SCAN_STATUS_TEXT = {
        confirmed: '報到完成',
        already: '已報到過',
        invalid: '查無此會員卡（或不在本次名冊）',
        not_open: '本場會議尚未開放報到',
        // 動態報到碼（§6）
        pass_expired: '手機上的碼過期了，請請會員重新整理頁面',
        static_not_allowed: '本場只收手機動態碼，請會員出示電子會員證',
        // 研討會簽退（§8）
        checked_out: '簽退完成',
        already_out: '已經簽退過',
        checkout_early: '還沒到簽退時間',
        checkout_closed: '已超過簽退時間，請洽承辦後台補登',
        // 委託書掃碼（計畫 v14 M11）
        proxy_found: '找到這張委託書，請核對後按「確認已收紙本」',
        proxy_already_active: '這張委託書已經生效過了',
        proxy_closed: '這張委託書已經取消或退回',
        // 候補與「本人已到場」都**不是**取消或退回：橫幅那句是承辦唸給會員聽的，
        // 唸錯之後重新登錄還會撞 assoc_proxy_principal，報到台就卡住
        proxy_waiting: '候補中（親自出席人數還不夠）。若還沒收紙本，請按「確認已收紙本」，開議時會自動遞補生效',
        proxy_superseded: '委託人本人已經到場報到，這張委託書已自動失效',
        proxy_other_meeting: '這張委託書不是本場的',
    };
    var SCAN_STATUS_CLASS = {
        confirmed: 'ok', checked_out: 'ok',
        already: 'warn', already_out: 'warn', checkout_early: 'warn',
        pass_expired: 'warn', static_not_allowed: 'warn',
        invalid: 'error', not_open: 'error', checkout_closed: 'error', error: 'error',
        proxy_found: 'ok',
        proxy_already_active: 'warn', proxy_closed: 'warn', proxy_other_meeting: 'error',
        proxy_waiting: 'warn', proxy_superseded: 'warn',
    };
    var METHOD_TEXT = {
        qr_static: '會員卡', qr_dynamic: '手機動態碼', manual: '手動', proxy: '委託代簽',
    };
    var PROXY_STATUS_TEXT = {
        active: '代簽完成',
        waiting: '候補中（親自出席人數還不夠，委託不得超過 1/3）',
        rejected: '受託人已代理 1 人，不能再代',
        need_paper: '尚未收到書面委託書，不能生效',
        need_scan: '請先掃描受託人的會員卡或動態碼',
        meeting_closed: '大會已經結束，不能再登錄委託書（請洽公會管理員後台補登）',
        failed: '登錄失敗，請重試或洽公會管理員',
        invalid: '查無這張委託書',
    };

    // 「已收書面」是人民團體法 §38 那 1/3 分母的入口，而它翻下去就**不可逆地**
    // 把一個沒到場的人算進出席。三條路徑（打字搜尋、掃委託人編號、掃委託書）
    // 全部要問這一句，所以文字與呼叫都只有這一份：原本打字那條寫「紙本委託書」、
    // 掃委託書那條寫「委託人簽名的紙本委託書」，而掃委託人編號那條**根本沒問**
    // ——誤掃一次會員編號＋誤點一次就成立（第十三輪 skeptic）。
    var PAPER_CONFIRM = '已經收到委託人簽名的紙本委託書了嗎？（按「確定」會把這位委託人算進出席人數）';

    function confirmPaper() {
        return window.confirm(PAPER_CONFIRM);
    }

    function rpc(url, params) {
        return fetch(url, {
            method: 'POST',
            credentials: 'same-origin',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ jsonrpc: '2.0', method: 'call', params: params || {} }),
        }).then(function (r) {
            if (!r.ok) { throw new Error('HTTP ' + r.status); }
            return r.json();
        }).then(function (data) {
            if (data.error) {
                throw new Error((data.error.data && data.error.data.message) || data.error.message || '伺服器錯誤');
            }
            return data.result;
        });
    }

    function el(tag, className, text) {
        var node = document.createElement(tag);
        if (className) { node.className = className; }
        if (text !== undefined && text !== null) { node.textContent = String(text); }
        return node;
    }

    function safeImg(src) {
        if (!src || src.indexOf('data:image/') !== 0) { return null; }
        var img = el('img');
        img.src = src;
        img.alt = '';
        return img;
    }

    var AxDesk = window.AxDesk = window.AxDesk || {};
    AxDesk.rpc = rpc;
    AxDesk.statusText = SCAN_STATUS_TEXT;
    AxDesk.methodText = METHOD_TEXT;
    AxDesk.proxyStatusText = PROXY_STATUS_TEXT;
    AxDesk.el = el;
    AxDesk.safeImg = safeImg;
    AxDesk.onScan = AxDesk.onScan || [];
    AxDesk.onPoll = AxDesk.onPoll || [];
    AxDesk.pollParams = AxDesk.pollParams || [];

    function init() {
        var root = document.querySelector('.ax-desk');
        if (!root) { return; }
        var meetingId = root.getAttribute('data-meeting-id');
        var pollMs = parseInt(root.getAttribute('data-poll-ms'), 10) || DEFAULT_POLL_MS;
        var base = '/assoc/desk/' + meetingId;
        AxDesk.meetingId = meetingId;
        AxDesk.base = base;
        AxDesk.root = root;

        function q(name) { return root.querySelector('[data-ax="' + name + '"]'); }
        var scanInput = document.getElementById('ax-scan');
        var scanResult = q('scan-result');
        var state = { pending: false, timer: null };

        function renderScan(res, message) {
            // message 給的話就用它：代簽的結果跟報到共用同一塊畫面，
            // 讓狀態表蓋過去的話，按「代簽」會顯示「報到完成」，
            // 報到台人員分不出自己剛才做了哪一件事。
            scanResult.textContent = '';
            var status = (res && res.status) || 'error';
            scanResult.className = 'ax-result ax-result--' + (SCAN_STATUS_CLASS[status] || 'error');
            var img = safeImg(res && res.photo);
            if (img) {
                scanResult.appendChild(img);
            } else if (res && res.member_id) {
                // 動態碼擋不了「即時把畫面轉傳給別人」，照片是唯一的人工關卡
                scanResult.appendChild(el('span', 'ax-warn', '無照片，請核對證件　'));
            }
            var label = message || SCAN_STATUS_TEXT[status] || (res && res.message) || '發生錯誤';
            var who = res && res.name ? res.name + '（' + res.member_no + '）' : '';
            scanResult.appendChild(el('span', null, who ? who + '　' + label : label));
        }

        // 「確認已收紙本並生效」那一顆。**兩個地方共用**：
        //   ① 掃到委託書的卡片 ② 掃到受託人之後列出的他身上的委託
        // 原本只有 ① 有，而 ② 對 `channel='portal' && !paper_received` 只印一行警告字
        // ——於是前台送出的委託在報到台是**死路**（`action_receive_paper` 是 admin-only，
        // `/proxy/register` 會撞 assoc_proxy_principal），承辦只能請管理員上後台。
        function paperButton(proxyId, deskRef, name, memberNo, onDone) {
            var btn = el('button', 'ax-btn', '確認已收紙本並生效');
            btn.type = 'button';
            btn.addEventListener('click', function () {
                if (!confirmPaper()) { return; }
                rpc(base + '/proxy/receive', {
                    proxy_id: proxyId, desk_ref: deskRef,
                }).then(function (out) {
                    renderScan({ status: out.status === 'active' ? 'confirmed' : 'already',
                                 name: name, member_no: memberNo },
                               PROXY_STATUS_TEXT[out.status] || out.message || out.status);
                    if (onDone) { onDone(); }
                    poll();
                }, function (err) {
                    renderScan({ status: 'error' }, err.message);
                });
            });
            return btn;
        }

        function renderProxies(res) {
            var panel = q('proxy-panel');
            if (!panel) { return; }
            panel.textContent = '';
            if (!res || !res.member_id || !res.desk_ref) { return; }
            var rows = res.proxies || [];
            if (!rows.length) {
                panel.appendChild(registerForm(res));
                return;
            }
            panel.appendChild(el('h2', 'ax-label', '這位會員身上的委託'));
            var list = el('ul', 'ax-list');
            rows.forEach(function (row) {
                var li = el('li');
                li.appendChild(el('span', null,
                    row.principal_no + '　' + row.principal_name
                    + '（' + (row.purpose === 'gift' ? '禮品代領' : '大會出席') + '）'));
                if (row.channel === 'portal' && !row.paper_received) {
                    li.appendChild(el('span', 'ax-warn', '　待收書面委託書　'));
                    li.appendChild(paperButton(row.proxy_id, res.desk_ref,
                                               row.principal_name, row.principal_no));
                } else {
                    var btn = el('button', 'ax-btn', '代簽');
                    btn.type = 'button';
                    btn.addEventListener('click', function () {
                        rpc(base + '/proxy/activate', {
                            proxy_id: row.proxy_id, desk_ref: res.desk_ref,
                        }).then(function (out) {
                            renderScan({
                                status: out.status === 'active' ? 'confirmed' : 'already',
                                name: row.principal_name, member_no: row.principal_no,
                            }, PROXY_STATUS_TEXT[out.status] || out.message || out.status);
                            poll();
                        }, function (err) {
                            renderScan({ status: 'error' }, err.message);
                        });
                    });
                    li.appendChild(btn);
                }
                list.appendChild(li);
            });
            panel.appendChild(list);
            panel.appendChild(registerForm(res));
        }

        function registerForm(res) {
            // 現場登錄紙本委託書：掃受託人 → 搜委託人 → 勾「已收書面」→ 立刻嘗試生效
            var box = el('div', 'ax-proxy-register');
            var summary = el('details');
            summary.appendChild(el('summary', 'ax-label', '登錄紙本委託書（這位會員代理他人）'));
            var input = el('input', 'ax-input');
            input.setAttribute('placeholder', '輸入委託人的會員編號或姓名');
            input.setAttribute('autocomplete', 'off');
            var results = el('ul', 'ax-list');
            var debounceId = null;
            input.addEventListener('input', function () {
                clearTimeout(debounceId);
                debounceId = setTimeout(function () {
                    var term = input.value.trim();
                    results.textContent = '';
                    if (!term) { return; }
                    rpc(base + '/search', { q: term }).then(function (rows) {
                        results.textContent = '';
                        rows.forEach(function (row) {
                            if (row.member_id === res.member_id) { return; }
                            var li = el('li');
                            li.appendChild(el('span', null, row.member_no + '　' + row.name));
                            ['attend', 'gift'].forEach(function (purpose) {
                                var btn = el('button', 'ax-btn',
                                             purpose === 'attend' ? '登錄（出席）' : '登錄（禮品）');
                                btn.type = 'button';
                                btn.addEventListener('click', function () {
                                    if (!confirmPaper()) { return; }
                                    rpc(base + '/proxy/register', {
                                        holder_member_id: res.member_id,
                                        principal_member_id: row.member_id,
                                        purpose: purpose, desk_ref: res.desk_ref,
                                    }).then(function (out) {
                                        renderScan({ status: out.status === 'active' ? 'confirmed' : 'already',
                                                     name: row.name, member_no: row.member_no },
                                                   PROXY_STATUS_TEXT[out.status] || out.message || out.status);
                                        input.value = '';
                                        results.textContent = '';
                                        poll();
                                    }, function (err) {
                                        renderScan({ status: 'error' }, err.message);
                                    });
                                });
                                li.appendChild(btn);
                            });
                            results.appendChild(li);
                        });
                    });
                }, SEARCH_DEBOUNCE_MS);
            });
            // 空白委託書那一條路：委託人在紙上貼／寫自己的**會員編號**條碼。
            // **這一格與主掃描框的形狀無法在伺服器端分辨**（會員編號就是會員編號），
            // 唯一的區分是「承辦掃進哪一格」——所以這條路由只做 id 解析、
            // 不寫任何資料，誤掃進去最壞的結果是畫面上多出一個人名。
            var scanBox = el('div', 'ax-proxy-scan');
            scanBox.appendChild(el('span', 'ax-label', '或掃描空白委託書上的委託人會員編號'));
            var scanPrincipal = el('input', 'ax-input');
            scanPrincipal.setAttribute('placeholder', '掃描委託人的會員編號條碼');
            scanPrincipal.setAttribute('autocomplete', 'off');
            scanPrincipal.addEventListener('keydown', function (ev) {
                if (ev.key !== 'Enter') { return; }
                ev.preventDefault();
                var code = scanPrincipal.value.trim();
                scanPrincipal.value = '';
                if (!code) { return; }
                rpc(base + '/proxy/principal_lookup', {
                    code: code, desk_ref: res.desk_ref, holder_member_id: res.member_id,
                }).then(function (out) {
                    results.textContent = '';
                    if (out.status !== 'found') {
                        results.appendChild(el('li', 'ax-warn',
                            '查無這個會員編號（或不在本次名冊）'));
                        return;
                    }
                    // 掃到之後走與打字搜尋**完全同一條**登錄路徑：
                    // 兩邊都是先確認人、再由承辦按用途鍵，守衛一行都不必改。
                    var li = el('li');
                    li.appendChild(el('span', null, out.principal_no + '　' + out.principal_name));
                    ['attend', 'gift'].forEach(function (purpose) {
                        var btn = el('button', 'ax-btn',
                            purpose === 'attend' ? '代理出席' : '代領禮品');
                        btn.type = 'button';
                        btn.addEventListener('click', function () {
                            if (!confirmPaper()) { return; }
                            rpc(base + '/proxy/register', {
                                holder_member_id: res.member_id,
                                principal_member_id: out.principal_member_id,
                                purpose: purpose, desk_ref: res.desk_ref,
                            }).then(function (done) {
                                renderScan({ status: done.status === 'active' ? 'confirmed' : 'already',
                                             name: out.principal_name,
                                             member_no: out.principal_no },
                                           PROXY_STATUS_TEXT[done.status] || done.message || done.status);
                                results.textContent = '';
                                poll();
                            }, function (err) {
                                renderScan({ status: 'error' }, err.message);
                            });
                        });
                        li.appendChild(btn);
                    });
                    results.appendChild(li);
                }, function (err) {
                    renderScan({ status: 'error' }, err.message);
                });
            });
            scanBox.appendChild(scanPrincipal);

            summary.appendChild(input);
            summary.appendChild(scanBox);
            summary.appendChild(results);
            box.appendChild(summary);
            return box;
        }

        // 最後一次掃到（或手動點名）的會員與他的 desk_ref。
        // 掃委託書**刻意不回** member_id、也不鑄 desk_ref（否則翻拍一張委託單
        // 就能換到受託人的禮品領取憑證），所以「確認已收紙本」那一鍵要靠
        // 這裡記住的那張憑證——也就是承辦必須先掃過受託人的卡。
        var lastScan = { member_id: null, desk_ref: null, name: '', member_no: '' };

        function renderProxyCard(res) {
            var panel = q('proxy-panel');
            if (!panel) { return; }
            panel.textContent = '';
            var proxy = res && res.proxy;
            if (!proxy) { return; }
            panel.appendChild(el('h2', 'ax-label', '掃到的委託書'));
            var list = el('ul', 'ax-list');
            var li = el('li');
            li.appendChild(el('span', null,
                proxy.principal_no + '　' + proxy.principal_name
                + '　→　' + proxy.holder_no + '　' + proxy.holder_name
                + '　' + proxy.purpose_label + '　' + proxy.state_label));
            // `proxy_waiting` 也要能按：候補中的前台委託帶紙來現場，
            // 書面旗標不翻的話開議時 `_activate_waiting_proxies()` 仍過不了
            // `channel='portal'` 那道閘門，這張紙永遠沒有用途。
            if (res.status === 'proxy_found' || (res.status === 'proxy_waiting'
                                                && !proxy.paper_received)) {
                if (lastScan.member_id === proxy.holder_member_id && lastScan.desk_ref) {
                    // **傳委託人、不是受託人**：被算進出席人數的是委託人，
                    // 而 renderScan 會把這兩個值印成「〈姓名〉（〈編號〉）　代簽完成」。
                    // 另一個呼叫端（renderProxies 那一列）傳的本來就是委託人。
                    li.appendChild(paperButton(proxy.id, lastScan.desk_ref,
                                               proxy.principal_name, proxy.principal_no,
                                               function () { panel.textContent = ''; }));
                } else {
                    li.appendChild(el('span', 'ax-warn',
                        '　請先掃描受託人 ' + proxy.holder_name + ' 的會員卡'));
                }
            }
            list.appendChild(li);
            panel.appendChild(list);
        }

        function dispatchScan(res) {
            var status = res && res.status;
            if (status && status.indexOf('proxy_') === 0) {
                // 委託書：走自己的卡片，不要丟給 renderProxies（它等的是 member_id）
                renderProxyCard(res);
            } else {
                if (res && res.member_id && res.desk_ref) {
                    lastScan = { member_id: res.member_id, desk_ref: res.desk_ref,
                                 name: res.name || '', member_no: res.member_no || '' };
                }
                renderProxies(res);
            }
            AxDesk.onScan.forEach(function (fn) { fn(res); });
        }

        scanInput.addEventListener('keydown', function (ev) {
            if (ev.key !== 'Enter') { return; }
            ev.preventDefault();
            var barcode = scanInput.value.trim();
            scanInput.value = '';
            if (!barcode) { return; }
            rpc(base + '/scan', { barcode: barcode }).then(function (res) {
                renderScan(res);
                dispatchScan(res);
                poll();
            }, function (err) {
                renderScan({ status: 'error' }, err.message);
            });
        });

        // 手動簽到
        var manualQ = q('manual-q');
        var manualResults = q('manual-results');
        var debounce = null;
        manualQ.addEventListener('input', function () {
            clearTimeout(debounce);
            debounce = setTimeout(function () {
                var term = manualQ.value.trim();
                manualResults.textContent = '';
                if (!term) { return; }
                rpc(base + '/search', { q: term }).then(function (rows) {
                    manualResults.textContent = '';
                    rows.forEach(function (row) {
                        var li = el('li');
                        li.appendChild(el('span', null, row.member_no + '　' + row.name));
                        if (row.state === 'absent') {
                            var btn = el('button', 'ax-btn', '手動簽到');
                            btn.type = 'button';
                            btn.addEventListener('click', function () {
                                var reason = window.prompt('手動簽到原因（必填，例：未帶會員卡，已核對身分證）');
                                if (!reason || !reason.trim()) { return; }
                                rpc(base + '/manual', { attendance_id: row.attendance_id, reason: reason }).then(function (res) {
                                    renderScan(res);
                                    dispatchScan(res);
                                    manualQ.value = '';
                                    manualResults.textContent = '';
                                    poll();
                                }, function (err) { renderScan({ status: 'error' }, err.message); });
                            });
                            li.appendChild(btn);
                        } else {
                            li.appendChild(el('span', 'ax-badge ax-badge--ok', '已報到'));
                            var pick = el('button', 'ax-btn', '選取');
                            pick.type = 'button';
                            pick.addEventListener('click', function () {
                                row.status = 'already';
                                renderScan(row);
                                dispatchScan(row);
                            });
                            li.appendChild(pick);
                        }
                        manualResults.appendChild(li);
                    });
                });
            }, SEARCH_DEBOUNCE_MS);
        });

        // 輪詢出席統計
        function renderPoll(res) {
            q('attending').textContent = String(res.present_count + res.proxy_count);
            q('members').textContent = String(res.member_count);
            var badge = q('quorum');
            badge.textContent = res.quorum_met ? '已達法定人數' : '未達法定人數';
            badge.className = 'ax-badge' + (res.quorum_met ? ' ax-badge--ok' : '');
            var recent = q('recent');
            recent.textContent = '';
            res.recent.forEach(function (row) {
                var li = el('li');
                li.appendChild(el('span', null, row.member_no + '　' + row.name));
                li.appendChild(el('span', 'ax-muted', METHOD_TEXT[row.method] || ''));
                recent.appendChild(li);
            });
        }

        function poll() {
            if (state.pending) { return; }
            state.pending = true;
            var params = {};
            AxDesk.pollParams.forEach(function (fn) { Object.assign(params, fn() || {}); });
            rpc(base + '/poll', params).then(function (res) {
                state.pending = false;
                renderPoll(res);
                AxDesk.onPoll.forEach(function (fn) { fn(res); });
            }, function () {
                state.pending = false;
            });
        }
        AxDesk.poll = poll;

        state.timer = setInterval(function () {
            // 分頁在背景時不打，切回來的下一個 tick 就會補上
            if (!document.hidden) { poll(); }
        }, pollMs);
        poll();
        scanInput.focus();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
