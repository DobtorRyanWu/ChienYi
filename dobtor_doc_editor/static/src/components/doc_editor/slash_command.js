/**
 * slash_command.js — canvas-editor 斜線指令選單
 * ================================================================
 * 代操 2026-08-06 回報：希望鍵入 `/` 時顯示可插入的元素指令（如 /checklist）。
 * 實測 @hufe921/canvas-editor 本身沒有這個功能（鍵入 / 只會插入字面字元），
 * 本模組在編輯器外層補上：偵測 `/` → 於游標處彈 DOM 選單 → 隨輸入過濾 →
 * 選定後刪掉觸發字 `/query` 再執行對應的 editor.command.execute*。
 *
 * 定位：canvas 編輯器把隱藏輸入區 `.ce-inputarea` 定位在游標處，
 *       用它的 getBoundingClientRect() 取游標螢幕座標最穩。
 *
 * 由 doc_editor.js 的 _initCanvasEditor 在建立編輯器後呼叫 init()。
 */
(function () {
    "use strict";

    const CE = window["canvas-editor"];
    if (!CE) {
        return; // canvas-editor 未載入，靜默略過
    }

    // ── 指令清單 ─────────────────────────────────────────────
    // keywords 同時放中文與英文縮寫，讓 `/c` 命中 checklist、`/h` 命中標題。
    function buildCommands(editor) {
        const cmd = editor.command;
        const { ListType, ListStyle, TitleLevel, ElementType } = CE;
        return [
            {
                id: "h1", label: "標題一", hint: "大標題",
                keywords: ["標題一", "標題", "h1", "heading", "title", "biaoti"],
                run: () => cmd.executeInsertTitle(TitleLevel.FIRST),
            },
            {
                id: "h2", label: "標題二", hint: "中標題",
                keywords: ["標題二", "標題", "h2", "heading", "title"],
                run: () => cmd.executeInsertTitle(TitleLevel.SECOND),
            },
            {
                id: "h3", label: "標題三", hint: "小標題",
                keywords: ["標題三", "標題", "h3", "heading", "title"],
                run: () => cmd.executeInsertTitle(TitleLevel.THIRD),
            },
            {
                id: "checklist", label: "核取清單", hint: "可勾選的項目清單",
                keywords: ["核取清單", "清單", "checklist", "check", "todo", "c"],
                run: () => cmd.executeList(ListType.UL, ListStyle.CHECKBOX),
            },
            {
                id: "bullet", label: "項目清單", hint: "圓點清單",
                keywords: ["項目清單", "清單", "bullet", "list", "ul"],
                run: () => cmd.executeList(ListType.UL, ListStyle.DISC),
            },
            {
                id: "number", label: "編號清單", hint: "數字編號清單",
                keywords: ["編號清單", "清單", "number", "ol", "ordered"],
                run: () => cmd.executeList(ListType.OL, ListStyle.DECIMAL),
            },
            {
                id: "table", label: "表格", hint: "插入 3×3 表格",
                keywords: ["表格", "table", "biaoge"],
                run: () => cmd.executeInsertTable(3, 3),
            },
            {
                id: "separator", label: "分隔線", hint: "水平分隔線",
                keywords: ["分隔線", "分隔", "separator", "hr", "line", "fenge"],
                run: () => cmd.executeInsertElementList([{ type: ElementType.SEPARATOR, value: "" }]),
            },
            {
                id: "pagebreak", label: "分頁", hint: "插入分頁符",
                keywords: ["分頁", "pagebreak", "page", "break", "fenye"],
                run: () => cmd.executeInsertElementList([{ type: ElementType.PAGE_BREAK, value: "" }]),
            },
        ];
    }

    // ── 主邏輯 ───────────────────────────────────────────────
    function init(editor, container) {
        if (!editor || !editor.command || container?._slashInited) {
            return;
        }
        // 唯讀模式不啟用
        try {
            if (CE.EditorMode && editor.command.getEditorOption?.()?.mode === CE.EditorMode.READONLY) {
                return;
            }
        } catch (e) { /* 取不到就當可編輯 */ }

        const commands = buildCommands(editor);
        let active = false;      // 是否在斜線模式
        let query = "";          // `/` 後輸入的字串
        let filtered = [];       // 目前符合的指令
        let selected = 0;        // 反白的項目 index

        // 選單 DOM（單例，附到 body 以免被 canvas overflow 裁切）
        const menu = document.createElement("div");
        menu.className = "dobtor-slash-menu";
        menu.style.display = "none";
        menu.setAttribute("role", "listbox");
        document.body.appendChild(menu);

        function inputArea() {
            // .ce-inputarea 可能有多個編輯器實例，取可見的那個
            const areas = document.querySelectorAll(".ce-inputarea");
            for (const a of areas) {
                if (a.offsetParent !== null || a.getClientRects().length) return a;
            }
            return areas[0] || null;
        }

        function filterCommands() {
            const q = query.toLowerCase();
            if (!q) return commands.slice();
            // 兩層排序：關鍵字「開頭命中」優先於「包含命中」，同層維持原順序。
            // 讓 `/h` 先列標題一二三，避免 checklist（含 h）、hr 這類子字串雜訊排前面。
            const scored = [];
            commands.forEach((c, idx) => {
                let score = 0;
                for (const k of c.keywords) {
                    const kl = k.toLowerCase();
                    if (kl.startsWith(q)) { score = 2; break; }
                    if (kl.includes(q)) score = 1;
                }
                if (score > 0) scored.push({ c, score, idx });
            });
            scored.sort((a, b) => (b.score - a.score) || (a.idx - b.idx));
            return scored.map((s) => s.c);
        }

        function render() {
            filtered = filterCommands();
            if (!filtered.length) {
                close(false); // 沒有符合的指令 → 關閉，讓 /query 留成字面文字
                return;
            }
            if (selected >= filtered.length) selected = filtered.length - 1;
            if (selected < 0) selected = 0;
            menu.innerHTML = "";
            filtered.forEach((c, i) => {
                const item = document.createElement("div");
                item.className = "dobtor-slash-item" + (i === selected ? " is-selected" : "");
                item.setAttribute("role", "option");
                item.innerHTML =
                    '<span class="dobtor-slash-label"></span>' +
                    '<span class="dobtor-slash-hint"></span>';
                item.querySelector(".dobtor-slash-label").textContent = c.label;
                item.querySelector(".dobtor-slash-hint").textContent = c.hint;
                item.addEventListener("mousedown", (ev) => {
                    ev.preventDefault(); // 別讓 canvas 失焦
                    execute(c);
                });
                item.addEventListener("mouseenter", () => {
                    selected = i;
                    highlight();
                });
                menu.appendChild(item);
            });
            position();
            menu.style.display = "block";
        }

        function highlight() {
            Array.from(menu.children).forEach((el, i) =>
                el.classList.toggle("is-selected", i === selected));
        }

        function position() {
            const area = inputArea();
            if (!area) return;
            const r = area.getBoundingClientRect();
            // 預設彈在游標下方；空間不足則彈上方
            const menuH = menu.offsetHeight || 240;
            let top = r.bottom + 4;
            if (top + menuH > window.innerHeight) {
                top = r.top - menuH - 4;
            }
            menu.style.left = Math.round(r.left) + "px";
            menu.style.top = Math.round(Math.max(4, top)) + "px";
        }

        function open() {
            active = true;
            query = "";
            selected = 0;
            render();
        }

        // removeTrigger=true 時把 `/query` 從文件刪掉（選定指令前呼叫）
        function close(removeTrigger) {
            if (removeTrigger && active) {
                try {
                    // 刪掉 `/` + query 共 (query.length + 1) 個字元
                    for (let i = 0; i < query.length + 1; i++) {
                        editor.command.executeBackspace();
                    }
                } catch (e) { /* 刪不掉就算了，指令照插 */ }
            }
            active = false;
            query = "";
            menu.style.display = "none";
        }

        function execute(c) {
            close(true);      // 先刪 /query
            try {
                c.run();
            } catch (e) {
                console.warn("[slash] 指令執行失敗：", c.id, e);
            }
        }

        // 斜線模式下攔截鍵盤（capture 階段，搶在 canvas 處理前）
        function onKeydown(ev) {
            const area = inputArea();
            // 只在焦點在編輯器輸入區時作用
            if (document.activeElement !== area && !active) return;

            if (!active) {
                if (ev.key === "/") {
                    // 讓 canvas 先插入 `/`（正常字元），下一個 tick 再開選單
                    setTimeout(open, 0);
                }
                return;
            }

            // 已在斜線模式
            switch (ev.key) {
                case "Escape":
                    ev.preventDefault();
                    close(false);
                    return;
                case "Enter":
                    ev.preventDefault();
                    ev.stopPropagation();
                    if (filtered[selected]) execute(filtered[selected]);
                    return;
                case "ArrowDown":
                    ev.preventDefault();
                    selected = (selected + 1) % filtered.length;
                    highlight();
                    return;
                case "ArrowUp":
                    ev.preventDefault();
                    selected = (selected - 1 + filtered.length) % filtered.length;
                    highlight();
                    return;
                case "Backspace":
                    if (query.length === 0) {
                        // 連 `/` 都要被刪 → 關閉（不刪，讓 canvas 自己刪 `/`）
                        close(false);
                    } else {
                        query = query.slice(0, -1);
                        setTimeout(render, 0);
                    }
                    return;
                case " ":
                case "Tab":
                    close(false); // 空白/Tab 結束斜線模式
                    return;
                default:
                    // 一般可列印字元：併入 query（canvas 也會插入該字，選定時一起刪）
                    if (ev.key.length === 1 && !ev.ctrlKey && !ev.metaKey && !ev.altKey) {
                        query += ev.key;
                        selected = 0;
                        setTimeout(render, 0);
                    }
            }
        }

        // 點選單外 → 關閉
        function onDocMousedown(ev) {
            if (active && !menu.contains(ev.target)) {
                close(false);
            }
        }

        document.addEventListener("keydown", onKeydown, true);
        document.addEventListener("mousedown", onDocMousedown, true);
        window.addEventListener("resize", () => active && position());

        container._slashInited = true;
        // 供 destroy 清理
        editor._slashCleanup = function () {
            document.removeEventListener("keydown", onKeydown, true);
            document.removeEventListener("mousedown", onDocMousedown, true);
            menu.remove();
        };
    }

    window.DobtorSlashCommand = { init };
})();
