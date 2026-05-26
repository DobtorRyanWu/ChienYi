/** @odoo-module **/

/**
 * DocEditor — Canvas 引擎版主編輯器 (Phase 1)
 *
 * 架構：Odoo Owl Component + canvas-editor.umd.min.js (window.CanvasEditor)
 * 資料流：content_json (Text) 為主要儲存與讀取欄位
 * AutoSave：Debounce(1.5s) + MaxWait(10s) + Idle(3s)
 */

import { Component, useState, onMounted, onWillUnmount, useRef } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { rpc } from "@web/core/network/rpc";
import { AutoSaveManager } from "../../core/auto_save_manager";
import { LeaderElection } from "../../core/leader_election";
import { OfflineManager } from "../../core/offline_manager";
import { installGlobalErrorReporting, mark, reportError } from "../../core/telemetry";
import { DocVersionPanel } from "../doc_version_panel/doc_version_panel";
import { DocFieldPickerDialog } from "../doc_field_picker/doc_field_picker";
// 注意：normalizeMultiCharElements{,InTables} 留在 scanner module 內供未來重啟此方向時使用
// （目前 Sprint T 因 canvas-editor auto-merge 無法用、見 onScanAndReplaceClick 內註解
//  與 docs/phase8_sprint_t_2026-05-24.md）
// IMPORTANT：不要把以上註解搬回 import {} 內部 — Odoo asset compiler 解析 import 解構
// 賦值時不會 strip 行內註解，會輸出 `require({)` 直接讓整個 web.assets_web bundle parse fail
// （Sprint V 才發現的；症狀 = SPA 完全不啟動、console 只有 "Unexpected token ')'"）。
import {
    scanJinja2Variables,
    scanJinja2VariablesWithPositions,
    scanJinja2VariablesInTables,
    analyzeScanResults,
    computeOrphanRecordIds,
    findMarkerPositionsInMain,
    rewriteTdValueWithControls,
    flattenElementsToText,
} from "./jinja2_scanner";

/**
 * Phase 8 Template UI Builder（ADR-022）— Phase 1 視覺風格靠攏。
 *
 * 範本欄位類型清單（Phase 2 接 canvas-editor executeInsertControl 用）。
 * Phase 1 只渲染按鈕、點擊只彈 toast，欄位插入行為留到 Phase 2。
 */
// Sprint Y5：格式化工具列字型 / 字號清單（Google Docs 風）
export const FONT_OPTIONS = [
    { value: "",                 label: "預設" },
    { value: "Microsoft JhengHei", label: "微軟正黑體" },
    { value: "Microsoft YaHei",  label: "微軟雅黑" },
    { value: "PMingLiU",         label: "新細明體" },
    { value: "DFKai-SB",         label: "標楷體" },
    { value: "Noto Sans TC",     label: "思源黑體" },
    { value: "Noto Serif TC",    label: "思源宋體" },
    { value: "Arial",            label: "Arial" },
    { value: "Times New Roman",  label: "Times New Roman" },
    { value: "Courier New",      label: "Courier New" },
    { value: "Helvetica",        label: "Helvetica" },
    { value: "Georgia",          label: "Georgia" },
];
export const FONT_SIZE_OPTIONS = [8, 9, 10, 11, 12, 14, 16, 18, 20, 24, 28, 32, 36, 48, 60, 72];

export const FIELD_TYPES = [
    { key: "name",       label: "名稱",     icon: "A",     ctrlType: "text" },
    { key: "email",      label: "電子郵件", icon: "A",     ctrlType: "text" },
    { key: "phone",      label: "電話",     icon: "A",     ctrlType: "text" },
    { key: "company",    label: "公司",     icon: "A",     ctrlType: "text" },
    { key: "title",      label: "標題",     icon: "A",     ctrlType: "text" },
    { key: "text",       label: "文字",     icon: "A",     ctrlType: "text" },
    { key: "date",       label: "日期",     icon: "fa-calendar", ctrlType: "date" },
    { key: "checkbox",   label: "核取方塊", icon: "fa-check-square-o", ctrlType: "checkbox" },
    { key: "signature",  label: "簽名",     icon: "fa-pencil", ctrlType: "text" },
    { key: "initial",    label: "繕寫簽名", icon: "fa-edit", ctrlType: "text" },
];

export class DocEditor extends Component {
    static template = "dobtor_doc_editor.DocEditor";
    static components = { DocVersionPanel };
    static props = ["*"];

    static FIELD_TYPES = FIELD_TYPES;

    setup() {
        this.notification = useService("notification");

        // action service 在 portal frontend 環境不存在；目前 DocEditor 內部沒呼叫任何
        // this.action 方法（只在 setup 時拿了 service），包 try/catch 才能在 portal mount。
        try {
            this.action = useService("action");
        } catch (e) {
            this.action = null;
        }

        // 嘗試取得 bus_service（多人協作用，可能不存在）
        try {
            this._busService = useService("bus_service");
        } catch (e) {
            this._busService = null;
        }

        // dialog service：用來開啟 DocFieldPickerDialog（Phase 8）
        // portal frontend 環境同 action service 可能不存在，包 try/catch。
        try {
            this.dialog = useService("dialog");
        } catch (e) {
            this.dialog = null;
        }

        // 暴露 FIELD_TYPES 給 template 使用（QWeb t-foreach）
        this.FIELD_TYPES = FIELD_TYPES;
        // Sprint Y5：暴露字型 / 字號清單給格式化工具列 t-foreach 使用
        this.FONT_OPTIONS = FONT_OPTIONS;
        this.FONT_SIZE_OPTIONS = FONT_SIZE_OPTIONS;

        // Portal mount 模式：<owl-component name="..." props='{"docId":123,"readonly":true}'>
        // public_component_service 會把 JSON 解析後當 props 傳進來。
        // backend client action 模式則走 this.props.action.context.doc_id（見下方）。
        this._isReadonly = this.props.readonly === true;

        // Canvas 編輯器容器 ref（始終存在於 DOM，不包在 t-if 內）
        this.canvasContainer = useRef("canvasContainer");

        this.state = useState({
            docId: null,
            docName: "未命名文件",
            editorReady: false,
            isSaving: false,
            statusMsg: "就緒",
            statusType: "saved",
            pageFormat: "A4",
            isOnline: true,
            // 模板引擎狀態
            isTemplateMode: false,
            templateVariables: [],
            templateFilename: "",
            contextJson: "",
            // 版本歷史面板（W7-8 P1-1）
            showVersionPanel: false,
            // ─── Phase 8 Template UI Builder（ADR-022） ───
            // Sub-nav tab：dashboard / requests / templates / settings
            // Phase 1 預設停在 templates，其他 disabled（WIP）。
            activeSubNav: "templates",
            // 當前選中的範本欄位 id（Phase 2 接 doc.template.field）。
            // Phase 1 始終為 null，inspector 顯示「未選取」狀態。
            selectedFieldId: null,
            // 頁碼導航（canvas-editor 多頁狀態，Phase 1 placeholder）。
            pageNo: 1,
            totalPages: 1,
            // 簽約人 chip（Phase 2 從 doc.template.signer 載入）。
            // Phase 1 用空陣列＋預設兩個 placeholder（房東/業務），純視覺。
            signers: [
                { id: -1, name: "房東", color: "#2c2c2c", count: 0 },
                { id: -2, name: "業務", color: "#22c55e", count: 0 },
            ],
            activeSignerId: -1,
            // 已放置欄位計數（Phase 2 接 doc.template.field）。
            fieldCount: 0,
            // Zoom 模式 placeholder（Phase 1 只是視覺，不接 executePageScale）。
            zoomFit: "auto",
            // Phase 2.2a 拖放新增欄位：當前是否有欄位被拖入 workspace
            isDropTarget: false,
            // ─── Sprint A：Sub-nav 分頁殼資料 ───────────────────────
            // 設定分頁：自動儲存開關（預設啟用）
            autoSaveEnabled: true,
            // 請求分頁：填寫請求清單（lazy-load）
            requests: [],
            requestsLoading: false,
            // ─── Sprint B：canvas-editor 當前縮放比例（由 pageScaleChange listener 同步） ───
            currentZoomScale: 1,
            // ─── Sprint C：頁面縮圖清單（debounced，由 _rebuildThumbnails 維護）───
            thumbnails: [],
            // ─── Sprint D：當前欄位插入模式（inline / overlay）───
            layoutMode: "inline",
            // overlay field 變動計數器：push/drag-end/load 時 ++ 強制 OWL re-render
            // （drag 過程不更新此值，靠 DOM transform 避免高頻 render）
            overlayFieldsRev: 0,
            // ─── Sprint N：最近一次「掃描並替換」的 snapshot（供 rollback）───
            // null = 沒可復原的操作；object = {docData, createdFieldIds, replacedCount, timestamp}
            // 覆蓋式單層 undo；rollback 成功 / 再次掃描並替換時被覆蓋
            lastScanReplaceSnapshot: null,
            // ─── Sprint O：inspector 欄位列表 search filter（substring，case-insensitive）───
            // 空字串 = 不過濾；對 odoo_field_name / placeholder_text / field_type 做包含比對
            fieldListFilter: "",
            // ─── Sprint P：inspector 列表的鍵盤焦點 index（在 filteredFieldsList 中）───
            // -1 = 沒焦點；0..length-1 = 對應 row。filter/cache 變動時要 reset
            focusedListIndex: -1,
            // ─── Sprint Y3：Google Docs 風 menu bar ───
            // null = 全部關閉；'file'|'edit'|'view'|'insert'|'format'|'tools' = 該 menu 展開中
            openMenu: null,
            // 查看 menu 的兩個 toggle（初始 true 維持現狀）
            showRuler: true,
            showThumbnails: true,
            // ─── Sprint Y4：尋找／取代 panel ───
            findReplaceMode: false,
            findText: '',
            replaceText: '',
            // ─── Sprint Y6：字色 / 背景色 picker（記住上次選色顯示在 swatch）
            textColor: '#202124',         // 預設黑灰（同 --gd-text）
            highlightColor: '#fff176',    // 預設淡黃（Google Docs 風）
            // ─── Sprint Y7：format toolbar active state（caret/selection 反映目前格式）
            activeBold: false,
            activeItalic: false,
            activeUnderline: false,
            activeStrikeout: false,
            // ─── Sprint Y8：format toolbar active state 延伸（font/size/align/color swatch）
            activeFontFamily: '',           // 空字串 = 預設字型
            activeFontSize: '16',           // canvas-editor 預設 16；select option value 是字串
            activeRowFlex: 'left',          // 'left'|'center'|'right'|'alignment'
        });
        // Sprint C：縮圖重生 timer（debounce、避免每次 contentChange 都全頁 toDataURL）
        this._thumbnailTimer = null;
        // 切到 requests tab 時才 load 一次
        this._requestsLoaded = false;

        // 暫存從後端載入的 content_json，供 _initCanvasEditor 使用
        this._loadedContentJson = null;
        // Canvas 編輯器實例
        this.editor = null;
        this._leaderElection = null;
        // P2-2 樂觀鎖：load 時記下後端 write_date，save 時帶回比對
        this._lastSyncedWriteDate = null;

        // P2-4 監控與遙測：掛全域 error / Web Vitals 監聽
        this._uninstallTelemetry = installGlobalErrorReporting({
            docIdGetter: () => this.state?.docId || null,
        });

        // P3-2 鍵盤導航
        this._onGlobalKey = (event) => {
            // Alt+H：開啟版本歷史
            if (event.altKey && !event.ctrlKey && !event.metaKey
                && (event.key === 'h' || event.key === 'H')) {
                event.preventDefault();
                this.onShowVersionPanel?.();
            }
            // Ctrl+Shift+S：手動建立版本快照
            if ((event.ctrlKey || event.metaKey) && event.shiftKey
                && (event.key === 'S' || event.key === 's')) {
                event.preventDefault();
                this.onSaveVersion?.();
            }
            // Esc：關閉版本面板（若開啟）
            if (event.key === 'Escape' && this.state?.showVersionPanel) {
                this.state.showVersionPanel = false;
            }
            // Sprint Y3：Esc 關閉 menu bar dropdown
            if (event.key === 'Escape' && this.state?.openMenu) {
                this.state.openMenu = null;
            }
            // Sprint Y4：Ctrl/Cmd+F 開尋找、Ctrl/Cmd+H 開取代
            if ((event.ctrlKey || event.metaKey) && !event.shiftKey && !event.altKey
                && (event.key === 'f' || event.key === 'F')) {
                event.preventDefault();
                this.openFindReplace?.('find');
            }
            if ((event.ctrlKey || event.metaKey) && !event.shiftKey && !event.altKey
                && (event.key === 'h' || event.key === 'H')) {
                event.preventDefault();
                this.openFindReplace?.('replace');
            }
        };
        if (typeof window !== 'undefined') {
            window.addEventListener('keydown', this._onGlobalKey);
        }

        // Sprint Y3：menu bar 外部點擊關閉（mousedown 比 click 早觸發，避免 trigger 自身競態）
        this._onGlobalClick = (ev) => {
            if (!this.state || !this.state.openMenu) return;
            try {
                if (!ev.target.closest('.doc-menubar')) {
                    this.state.openMenu = null;
                }
            } catch (e) { /* ignore */ }
        };
        if (typeof document !== 'undefined') {
            document.addEventListener('mousedown', this._onGlobalClick);
        }

        // 取得 doc_id 優先順序：
        //   1. this.props.docId — portal mount 模式（<owl-component props='{"docId":...}'>）
        //   2. backend client action context.doc_id
        //   3. URL query string ?doc_id=N — Sprint V：給 E2E / bookmark / share 用
        //      （client action URL 預設不接 context，這層 fallback 讓
        //       /odoo/action-dobtor_doc_editor.action_doc_editor?doc_id=N 能 work）
        //   4. sessionStorage F5 恢復（backend 內按 F5 刷新時用）
        const context = this.props.action?.context || {};
        const _SESSION_KEY = "dobtor_doc_editor_last_id";
        let _urlDocId = null;
        try {
            const _v = new URLSearchParams(window.location.search).get("doc_id");
            const _n = _v ? parseInt(_v, 10) : 0;
            if (_n > 0) {
                _urlDocId = _n;
            }
        } catch (e) {
            // ignore — fall through to next fallback
        }
        let _storedDocId = null;
        const _stored = sessionStorage.getItem(_SESSION_KEY);
        if (_stored) {
            _storedDocId = parseInt(_stored, 10);
        }
        const docId = this.props.docId || context.doc_id || _urlDocId || _storedDocId;

        // ── AutoSaveManager（以 content_json 為儲存單位）──
        this._autoSave = new AutoSaveManager({
            saveFn: async (json) => {
                if (!this.state.docId) return;
                // Readonly 模式（portal 唯讀 / 公開預覽）：不觸發後端寫入。
                if (this._isReadonly) return;
                const result = await rpc("/dobtor_doc/save", {
                    doc_id: this.state.docId,
                    content_json: json,
                    // P2-2 樂觀鎖
                    if_unmodified_since: this._lastSyncedWriteDate,
                });
                this._handleSaveResult(result, json);
            },
            debounceMs: 1500,
            maxWaitMs: 10000,
            idleMs: 3000,
            isLeaderFn: () => this._leaderElection?.isLeader() ?? true,
            onStatusChange: (status) => {
                const msgs = {
                    unsaved: ["未儲存", "saving"],
                    saving:  ["儲存中...", "saving"],
                    saved:   ["已儲存", "saved"],
                    error:   ["儲存失敗", "error"],
                };
                const [msg, type] = msgs[status] || ["就緒", "saved"];
                this.state.statusMsg = msg;
                this.state.statusType = type;
                this.state.isSaving = status === "saving";
            },
        });

        // ── OfflineManager ──
        this._offlineManager = new OfflineManager();
        this._offlineManager.onStatusChange((isOnline) => {
            this.state.isOnline = isOnline;
            if (isOnline) {
                this.notification.add("已恢復連線，正在同步...", { type: "success" });
                this._syncOfflineBuffer();
            } else {
                this.notification.add(
                    "網路已斷線，編輯內容將在恢復後自動同步",
                    { type: "warning", sticky: true }
                );
            }
        });

        onMounted(async () => {
            // 1. 載入文件資料
            if (docId) {
                await this._loadDocument(docId);
            } else {
                this.state.editorReady = true;
            }

            // 2. 初始化 Canvas 編輯器（資料已暫存於 this._loadedContentJson）
            this._initCanvasEditor();

            // 3. 初始化 LeaderElection（多人協作防止重複存檔）
            if (this._busService && this.state.docId) {
                const channel = `doc.document_${this.state.docId}`;
                const sessionId = Math.random().toString(36).slice(2);
                this._leaderElection = new LeaderElection(
                    this._busService, channel, sessionId
                );
            }
        });

        onWillUnmount(async () => {
            // W4 P0-4：完整記憶體釋放，避免 portal user 反覆開關文件爆 RAM
            // 順序：flush 未存資料 → 解除全域引用 → 解除 listener closure → destroy 子系統
            try {
                await this._autoSave.flush();
            } catch (e) {
                // flush 失敗不應擋住 destroy，但要 log
                console.warn("[DocEditor] flush before unmount failed:", e);
            }
            this._autoSave.destroy();
            this._offlineManager.destroy();
            if (this._leaderElection) this._leaderElection.destroy();

            // 解除全域 DevTools 引用（避免 GC root 持有 editor → 整個文件 retain）
            if (window._docEditor === this.editor) {
                delete window._docEditor;
            }

            // 解除 listener closure（contentChange 內 closure 引用 this，會把 component 整個 retain）
            if (this.editor?.listener) {
                this.editor.listener.contentChange = null;
            }

            // 銷毀 Canvas 編輯器實例（v0.9.128 已提供 destroy 官方 API）
            this.editor?.destroy?.();

            // 清空成員引用，幫助 GC 識別此 component 已不可達
            this.editor = null;
            this._loadedContentJson = null;
            this._lastSyncedWriteDate = null;
            this._autoSave = null;
            this._offlineManager = null;
            this._leaderElection = null;

            // P2-4：卸載 telemetry listener
            try {
                this._uninstallTelemetry?.();
            } catch (e) {
                console.warn("[DocEditor] uninstall telemetry failed:", e);
            }
            this._uninstallTelemetry = null;

            // P3-2：解除鍵盤監聽
            if (typeof window !== 'undefined' && this._onGlobalKey) {
                window.removeEventListener('keydown', this._onGlobalKey);
            }
            this._onGlobalKey = null;

            // Sprint Y3：解除 menu bar 外部點擊監聽
            if (typeof document !== 'undefined' && this._onGlobalClick) {
                document.removeEventListener('mousedown', this._onGlobalClick);
            }
            this._onGlobalClick = null;
        });
    }

    // ─── Canvas 編輯器初始化 ────────────────────────────────────────

    _initCanvasEditor() {
        const container = this.canvasContainer.el;
        if (!container) {
            console.error("[DocEditor] canvasContainer ref 未找到，Canvas 編輯器無法初始化");
            return;
        }

        // 取得全域 Canvas 編輯器建構子
        // @hufe921/canvas-editor UMD 掛載於 window["canvas-editor"].Editor
        const EditorConstructor = window["canvas-editor"]?.Editor;
        if (!EditorConstructor) {
            container.innerHTML =
                '<p style="color:#dc3545;padding:20px;font-size:14px">' +
                '❌ 錯誤：找不到 Canvas 編輯器（window["canvas-editor"].Editor 未定義）。' +
                '請確認 canvas-editor.umd.min.js 已正確載入。' +
                '</p>';
            console.error("[DocEditor] Canvas 編輯器未載入，請確認 __manifest__.py 中的 lib 路徑");
            return;
        }

        // 解析初始資料（空文件時傳入空陣列）
        let initialData = [];
        if (this._loadedContentJson) {
            try {
                initialData = JSON.parse(this._loadedContentJson);
            } catch (e) {
                console.warn("[DocEditor] content_json 解析失敗，以空白開始：", e);
            }
        }

        // 取得 PageMode / EditorMode 列舉（PAGING = 分頁置中模式，類 Google Docs）
        const CE = window["canvas-editor"];
        const PageMode = CE?.PageMode;
        const EditorMode = CE?.EditorMode;

        // 建立 Canvas 編輯器實例
        // readonly mode：portal 公開預覽或無寫入權限時走 EditorMode.READONLY
        const editorOptions = {
            pageMode: PageMode?.PAGING,
        };
        if (this._isReadonly && EditorMode?.READONLY) {
            editorOptions.mode = EditorMode.READONLY;
        }
        this.editor = new EditorConstructor(container, initialData, editorOptions);

        // Sprint 16：content_json 為空但 content_html 有值（template 自動填充常見情境）
        // → 用 canvas-editor 的 executeSetHTML 把 HTML 轉成 IElement[] 灌入。
        // 觸發 contentChange 後 AutoSave 會把產生的 IElement[] 寫回 content_json，
        // 後續開啟就走 content_json 主路徑，本 fallback 不會重複觸發。
        const isEmptyJson = !this._loadedContentJson || initialData.length === 0;
        const html = (this._loadedContentHtml || "").trim();
        const isPlaceholderHtml = html === "" || html === "<p><br></p>" || html === "<p></p>";
        if (isEmptyJson && !isPlaceholderHtml) {
            try {
                if (typeof this.editor.command.executeSetHTML === "function") {
                    this.editor.command.executeSetHTML({ main: html });
                } else {
                    console.warn("[DocEditor] executeSetHTML 不存在，content_html fallback 失效");
                }
            } catch (err) {
                console.warn("[DocEditor] executeSetHTML 失敗，回退空白：", err);
            }
        }

        // 注冊繁體中文 locale，再切換（register.langMap 是 registerLangMap 的 bound 版本）
        this.editor.register.langMap("zhTW", {
            contextmenu: {
                global: { cut: "剪下", copy: "複製", paste: "貼上", selectAll: "全選", print: "列印" },
                table: {
                    insertRowCol: "插入行列",
                    insertTopRow: "上方插入 1 行",
                    insertBottomRow: "下方插入 1 行",
                    insertLeftCol: "左側插入 1 欄",
                    insertRightCol: "右側插入 1 欄",
                    deleteRowCol: "刪除行列",
                    deleteRow: "刪除 1 行",
                    deleteCol: "刪除 1 欄",
                    deleteTable: "刪除整個表格",
                    mergeCell: "合併儲存格",
                    mergeCancelCell: "取消合併",
                    verticalAlign: "垂直對齊",
                    verticalAlignTop: "靠上對齊",
                    verticalAlignMiddle: "垂直置中",
                    verticalAlignBottom: "靠下對齊",
                    border: "表格框線",
                    borderAll: "所有框線",
                    borderEmpty: "無框線",
                    borderDash: "虛線框線",
                    borderExternal: "外側框線",
                    borderInternal: "內側框線",
                    borderTd: "儲存格框線",
                },
                image: { change: "更換圖片", saveAs: "另存圖片", textWrap: "文字環繞" },
                hyperlink: { delete: "刪除連結", cancel: "取消連結", edit: "編輯連結" },
                control: { delete: "刪除控制項" },
            },
            zone: { headerTip: "頁首區域", footerTip: "頁尾區域" },
        });
        this.editor.command.executeSetLocale("zhTW");

        // 載入 DOCX 匯入/匯出 plugin（window.docx 由 canvas-editor-plugin-docx.umd.js 注入）
        if (window.docx) {
            this.editor.use(window.docx);
        } else {
            console.warn("[DocEditor] canvas-editor-plugin-docx 未載入，DOCX 匯入/匯出功能不可用");
        }

        // 暫時掛載全域，方便 DevTools 除錯（console 輸入 window._docEditor.command.getValue().data）
        window._docEditor = this.editor;
        // Sprint T 除錯後保留：暴露 OWL component instance，方便 E2E 探查 state / cache
        // （Playwright spec 可用 window._docEditorCmp.state.docId 等驗證 state）
        window._docEditorCmp = this;

        // Phase 8 Del 鍵同步：追蹤目前文件上所有 control 的 conceptId 集合，
        // contentChange 觸發時 diff 出消失的 id，批次呼叫後端 delete_field 同步紀錄。
        this._lastControlIds = new Set();

        // 監聽內容變更 → 觸發 AutoSave（使用引擎正式 API）
        this.editor.listener.contentChange = () => {
            try {
                const json = JSON.stringify(this.editor.command.getValue().data);
                if (this._offlineManager.isOnline) {
                    this._autoSave.onContentChange(json);
                } else {
                    this._offlineManager.bufferOperation({ type: "save", json });
                    this.state.statusMsg = "離線緩存中";
                    this.state.statusType = "saving";
                }
            } catch (e) {
                console.error("[DocEditor] contentChange 處理失敗：", e);
            }
            // Phase 8 Del 同步：setTimeout 解耦，先讓 autoSave 入隊再做 diff
            setTimeout(() => this._syncDeletedControls(), 0);
            // Sprint C：debounced 重生縮圖（800ms 避免逐字打抖動）
            this._scheduleRebuildThumbnails(800);
        };

        // Phase 2.1 補項：監聽選區變動 → 反查 control.conceptId → 設 selectedFieldId
        // canvas-editor 在 caret 移動 / 選區變動時觸發 rangeStyleChange listener。
        // 透過 editor.command.getRangeContext() 取當前選區的 element，
        // 再從 element.control.conceptId 反查 doc.template.field.id。
        //
        // 設計：**只在偵測到 control 時 update selectedFieldId，偵測不到時保留現狀**。
        // 不自動 deselect 的原因（E2E 抓到的 bug）：
        //   1. executeInsertControl 後 caret 自動移到 control 之後 → 立刻被誤清為 null
        //   2. user 在 inspector 編輯期間焦點離開 canvas → 不該被誤清
        // user 真要 deselect：點別的 control 切換、或點 inspector 的「刪除」按鈕（內部清）。
        this.editor.listener.rangeStyleChange = () => {
            try {
                const ctx = this.editor.command.getRangeContext();
                if (!ctx) return;
                const el = ctx.startElement || ctx.endElement || ctx.element || null;

                // 既有：control conceptId 反查 → selectedFieldId
                const conceptId = el?.control?.conceptId;
                if (conceptId) {
                    const fieldId = parseInt(conceptId, 10);
                    if (Number.isFinite(fieldId) && this.state.selectedFieldId !== fieldId) {
                        this.state.selectedFieldId = fieldId;
                    }
                }

                // Sprint Y7：根據 selection 起點 element 的格式屬性、更新 format toolbar
                // active state。selection 跨多 element 樣式不一時、目前只看起點（簡化）。
                // 未來可改用 ctx 內彙整資料判斷 indeterminate（部分選中）。
                if (el) {
                    const b = el.bold === true;
                    const i = el.italic === true;
                    const u = el.underline === true;
                    const s = el.strikeout === true;
                    if (this.state.activeBold !== b) this.state.activeBold = b;
                    if (this.state.activeItalic !== i) this.state.activeItalic = i;
                    if (this.state.activeUnderline !== u) this.state.activeUnderline = u;
                    if (this.state.activeStrikeout !== s) this.state.activeStrikeout = s;

                    // Sprint Y8：font/size/color/highlight/rowFlex 也同步反映 caret 狀態
                    const font = el.font || '';
                    const sizeStr = el.size != null ? String(el.size) : '16';
                    if (this.state.activeFontFamily !== font) this.state.activeFontFamily = font;
                    if (this.state.activeFontSize !== sizeStr) this.state.activeFontSize = sizeStr;
                    // 字色 / 背景色：caret 文字真實顏色 → swatch + picker 預設值
                    const color = el.color || '#202124';
                    const hl = el.highlight || '#fff176';
                    if (this.state.textColor !== color) this.state.textColor = color;
                    if (this.state.highlightColor !== hl) this.state.highlightColor = hl;
                    // rowFlex 通常在 element 或 row 上、fallback 到 left
                    const rowFlex = el.rowFlex || ctx?.rowFlex || 'left';
                    if (this.state.activeRowFlex !== rowFlex) this.state.activeRowFlex = rowFlex;
                }
            } catch (e) {
                // 不要讓 listener 抛例外破壞 canvas-editor 內部流程
            }
        };

        // Sprint B：同步 canvas-editor 頁碼狀態到 state，讓 pager / dashboard 即時反映。
        //   intersectionPageNoChange → 滾動時 viewport 可見頁變更
        //   pageSizeChange → 文件分頁數變更（新增/刪除內容導致分頁變化）
        //   pageScaleChange → 縮放比例變更（user 操作或 fit 模式觸發）
        this.editor.listener.intersectionPageNoChange = (pageNo) => {
            try {
                // canvas-editor 用 0-based pageNo；UI 顯示 1-based
                const oneBased = typeof pageNo === "number" ? pageNo + 1 : 1;
                if (this.state.pageNo !== oneBased) {
                    this.state.pageNo = oneBased;
                }
            } catch (e) {
                // 不要讓 listener 抛例外破壞 canvas-editor 內部流程
            }
        };
        this.editor.listener.pageSizeChange = () => {
            try {
                const total = typeof this.editor.command.getPageCount === "function"
                    ? this.editor.command.getPageCount()
                    : null;
                if (typeof total === "number" && total >= 1 && this.state.totalPages !== total) {
                    this.state.totalPages = total;
                }
            } catch (e) {
                // 容錯：API 不存在或拋例外時保留現有 state.totalPages
            }
            // Sprint C：分頁數變更時必更新縮圖
            this._scheduleRebuildThumbnails(600);
        };
        this.editor.listener.pageScaleChange = (scale) => {
            try {
                if (typeof scale === "number" && Number.isFinite(scale)) {
                    this.state.currentZoomScale = scale;
                }
            } catch (e) {
                // 容錯
            }
        };
        // 初始化時讀一次總頁數（避免 listener 沒觸發前 dashboard 顯示 1）
        try {
            const total = typeof this.editor.command.getPageCount === "function"
                ? this.editor.command.getPageCount()
                : 1;
            this.state.totalPages = total || 1;
            const cur = typeof this.editor.command.getPageNo === "function"
                ? this.editor.command.getPageNo()
                : 0;
            this.state.pageNo = (cur || 0) + 1;
        } catch (e) {
            // 容錯
        }

        // Sprint C：縮圖 panel 初始化 + 後續變更時 debounce 重生
        this._scheduleRebuildThumbnails(50);  // 初次延遲 50ms 等 canvas 真渲染
    }

    // ─── Sprint C：頁面縮圖（debounced）─────────────────────────────
    //
    // 設計：每頁 canvas-editor 渲染為獨立 <canvas> 元素，直接用 toDataURL
    // 取縮圖（壓縮品質 0.5 + max 200x283 ≈ A4 縮影）。
    // 重生時機：
    //   1. 初次 _initCanvasEditor 完（50ms 延遲等 canvas 真渲染）
    //   2. contentChange listener 觸發後（已內部 debounce、再加 thumbnail 自家 800ms debounce 避免抖動）
    //   3. pageSizeChange listener（分頁數變更時必更新）

    _scheduleRebuildThumbnails(delayMs = 800) {
        if (this._thumbnailTimer) {
            clearTimeout(this._thumbnailTimer);
        }
        this._thumbnailTimer = setTimeout(() => {
            this._thumbnailTimer = null;
            this._rebuildThumbnails();
        }, delayMs);
    }

    _rebuildThumbnails() {
        if (!this.canvasContainer?.el) {
            return;
        }
        try {
            const pageCanvases = this.canvasContainer.el.querySelectorAll("canvas");
            const MAX_W = 200;
            const thumbs = [];
            for (let i = 0; i < pageCanvases.length; i++) {
                const c = pageCanvases[i];
                // 跳過 0-size canvas（cursor canvas、隱藏 canvas）
                if (!c.width || !c.height) continue;
                let dataUrl;
                try {
                    // canvas-editor 主 page canvas 通常很大（A4 @ 96DPI × pixelRatio）
                    // 直接 toDataURL 對 100 頁文件會卡 UI；用 OffscreenCanvas 縮小
                    if (typeof OffscreenCanvas !== "undefined") {
                        const ratio = MAX_W / c.width;
                        const w = Math.max(1, Math.floor(c.width * ratio));
                        const h = Math.max(1, Math.floor(c.height * ratio));
                        const off = new OffscreenCanvas(w, h);
                        const ctx = off.getContext("2d");
                        ctx.drawImage(c, 0, 0, w, h);
                        // OffscreenCanvas.convertToBlob 是 async；用 toDataURL 退而求其次
                        // → 走 sync 路徑：建臨時 HTMLCanvasElement
                        const tmp = document.createElement("canvas");
                        tmp.width = w;
                        tmp.height = h;
                        tmp.getContext("2d").drawImage(c, 0, 0, w, h);
                        dataUrl = tmp.toDataURL("image/jpeg", 0.5);
                    } else {
                        dataUrl = c.toDataURL("image/jpeg", 0.3);
                    }
                } catch (toDataErr) {
                    // SecurityError / tainted canvas：跳過該頁
                    continue;
                }
                thumbs.push({
                    pageNo: thumbs.length + 1,
                    dataUrl: dataUrl,
                    fieldCount: 0,  // 後續可從 _templateFieldsCache 對應頁數 group by 算
                });
            }
            this.state.thumbnails = thumbs;
        } catch (e) {
            console.warn("[DocEditor] _rebuildThumbnails failed", e);
        }
    }

    // ─── 資料載入 ────────────────────────────────────────────────────

    async _loadDocument(docId) {
        const stopLoadTimer = mark("load_doc_ms");
        try {
            const data = await rpc("/dobtor_doc/load", { doc_id: docId });
            this.state.docId = data.id;
            this.state.docName = data.name;
            // F5 恢復用
            sessionStorage.setItem("dobtor_doc_editor_last_id", data.id);
            this.state.pageFormat = data.page_format || "A4";

            // 暫存 content_json，供 _initCanvasEditor 使用
            this._loadedContentJson = data.content_json || null;
            // Sprint 16：暫存 content_html，當 content_json 空但 HTML 有值（如 template
            // 自動填充情境）時，editor init 後 fallback 用 executeSetHTML 灌入。
            this._loadedContentHtml = data.content_html || "";
            // Phase 8：暫存目標 model_name，供 DocFieldPickerDialog 使用（onOdooFieldClick）
            this._loadedModelName = data.model_name || null;
            // P2-2 樂觀鎖：記下伺服器當前 write_date
            this._lastSyncedWriteDate = data.write_date || null;
            // Phase 8 Template UI Builder（ADR-022）—— 載入範本 signer/field 狀態
            await this._loadTemplateFields();

            // 模板引擎狀態恢復
            if (data.has_template) {
                this.state.isTemplateMode = true;
                this.state.templateVariables = data.template_variables || [];
                this.state.templateFilename = data.template_filename || "";
            }

            this.state.editorReady = true;
            this.state.statusMsg = "已載入";
            this.state.statusType = "saved";
            stopLoadTimer({ docId: this.state.docId });
        } catch (error) {
            this.state.statusMsg = `載入失敗：${error.message || error}`;
            this.state.statusType = "error";
            this.state.editorReady = true; // 避免永遠顯示載入中
            console.error("[DocEditor] Load failed:", error);
            // P2-4 上報 load 失敗
            reportError({
                type: "other",
                message: `Load failed: ${error.message || error}`,
                stackTrace: error?.stack || "",
                docId,
            });
        }
    }

    // ─── 離線同步 ────────────────────────────────────────────────────

    async _syncOfflineBuffer() {
        const ops = this._offlineManager.drainBuffer();
        if (!ops.length || !this.state.docId) return;
        const lastSave = [...ops].reverse().find(op => op.type === "save");
        if (!lastSave) return;
        try {
            const result = await rpc("/dobtor_doc/save", {
                doc_id: this.state.docId,
                content_json: lastSave.json,
                if_unmodified_since: this._lastSyncedWriteDate,
            });
            this._handleSaveResult(result, lastSave.json);
            this.state.statusMsg = "已同步";
            this.state.statusType = "saved";
        } catch (e) {
            this.notification.add(`同步失敗：${e.message}`, { type: "danger" });
        }
    }

    /**
     * P2-2 樂觀鎖：處理 save 結果
     *  - 成功 → 更新 _lastSyncedWriteDate
     *  - 衝突 → 暫存到 IndexedDB（offline_manager），提示使用者，自動 reload
     */
    _handleSaveResult(result, jsonAttempted) {
        if (!result) return;
        if (result.conflict) {
            // 衝突：把當前未存的內容塞進 offline buffer 保留
            try {
                this._offlineManager?.bufferOperation?.({
                    type: "save",
                    json: jsonAttempted,
                    reason: "conflict",
                    ts: new Date().toISOString(),
                });
            } catch (e) {
                console.error("[DocEditor] buffer on conflict failed:", e);
            }
            this.state.statusMsg = "與他人編輯衝突";
            this.state.statusType = "error";
            const author = result.server_author_name || "他人";
            this.notification.add(
                `文件已被「${author}」修改（v${result.server_version_number}）。將重新載入最新內容；您剛才編輯的內容已暫存於離線緩衝。`,
                { type: "warning", sticky: true }
            );
            // 自動 reload 後端最新內容
            if (this.state.docId) {
                this._loadDocument(this.state.docId).then(() => {
                    if (this.editor && this._loadedContentJson) {
                        try {
                            const data = JSON.parse(this._loadedContentJson);
                            this.editor.command.executeSetValue(data);
                        } catch (e) {
                            console.error("[DocEditor] reload after conflict failed:", e);
                        }
                    }
                });
            }
            return;
        }
        if (result.success && result.write_date) {
            this._lastSyncedWriteDate = result.write_date;
        }
    }

    // ─── 手動儲存 ────────────────────────────────────────────────────

    async onSave() {
        if (!this.state.docId || this.state.isSaving) return;
        if (!this.editor) {
            this.notification.add("編輯器尚未初始化", { type: "warning" });
            return;
        }
        sessionStorage.setItem("dobtor_doc_editor_last_id", this.state.docId);
        this.state.isSaving = true;
        this.state.statusMsg = "儲存中...";
        this.state.statusType = "saving";
        const stopSaveTimer = mark("save_latency_ms");
        try {
            const json = JSON.stringify(this.editor.command.getValue().data);
            const result = await rpc("/dobtor_doc/save", {
                doc_id: this.state.docId,
                content_json: json,
                if_unmodified_since: this._lastSyncedWriteDate,
            });
            // P2-2: 衝突時 _handleSaveResult 會處理 reload + 警示
            this._handleSaveResult(result, json);
            if (!result?.conflict) {
                this.state.statusMsg = "已儲存";
                this.state.statusType = "saved";
            }
            stopSaveTimer({ docId: this.state.docId });
        } catch (error) {
            this.state.statusMsg = `儲存失敗：${error.message || error}`;
            this.state.statusType = "error";
            this.notification.add("文件儲存失敗", { type: "danger" });
            reportError({
                type: "save_failure",
                message: error.message || String(error),
                stackTrace: error?.stack || "",
                docId: this.state.docId,
            });
        } finally {
            this.state.isSaving = false;
        }
    }

    // ─── Toolbar 事件 ────────────────────────────────────────────────

    onTitleChange(event) {
        const newName = event.target.value.trim() || "未命名文件";
        this.state.docName = newName;
        if (this.state.docId) {
            rpc("/dobtor_doc/save", { doc_id: this.state.docId, name: newName })
                .catch(() => {});
        }
    }

    onZoomChange(event) {
        if (!this.editor) return;
        const scale = parseFloat(event.target.value);
        if (!isNaN(scale)) {
            this.editor.command.executePageScale(scale);
        }
    }

    onPageFormatChange(event) {
        if (!this.editor) return;
        // A4 size in pixels @ 96 DPI
        const PAGE_SIZES = {
            A4:     [794,  1123],
            A3:     [1123, 1587],
            A5:     [559,  794],
            letter: [816,  1056],
            legal:  [816,  1344],
        };
        const format = event.target.value;
        const size = PAGE_SIZES[format];
        if (size) {
            this.editor.command.executePaperSize(size[0], size[1]);
            this.state.pageFormat = format;
        }
    }

    // ─── 匯入 DOCX ───────────────────────────────────────────────────

    onImportClick() {
        const input = document.createElement("input");
        input.type = "file";
        input.accept = ".docx";
        input.onchange = (ev) => this._handleImportFile(ev.target.files[0]);
        input.click();
    }

    async _handleImportFile(file) {
        if (!file) return;

        // 若有 docId，走後端高保真模板路線
        if (this.state.docId) {
            this.state.statusMsg = "上傳模板中...";
            this.state.statusType = "saving";
            try {
                const formData = new FormData();
                formData.append("doc_id", String(this.state.docId));
                formData.append("docx_file", file);

                const resp = await fetch("/dobtor_doc/upload_template", {
                    method: "POST",
                    body: formData,
                });
                const result = await resp.json();

                if (!result.success) throw new Error(result.error || "上傳失敗");

                this.state.isTemplateMode = true;
                this.state.templateVariables = result.variables || [];
                this.state.templateFilename = file.name;
                this.state.statusMsg = `模板就緒（${result.variables.length} 個變數）`;
                this.state.statusType = "saved";
                this.notification.add(
                    `模板上傳成功，偵測到：${result.variables.join(", ") || "（無變數）"}`,
                    { type: "success" }
                );
            } catch (e) {
                this.state.statusMsg = "就緒";
                this.state.statusType = "saved";
                this.notification.add(`上傳失敗：${e.message || e}`, { type: "danger" });
                return;
            }
        }

        // 同時用 canvas-editor 顯示預覽（接受格式偏差，僅供參考）
        if (this.editor && window.docx) {
            try {
                const ab = await file.arrayBuffer();
                await this.editor.command.executeImportDocx({ arrayBuffer: ab });
            } catch (e) {
                console.warn("[DocEditor] canvas 預覽失敗（不影響後端模板功能）：", e);
            }
        }
    }

    /**
     * 用本模組的 TS OOXML Parser（Phase E 並行通道）匯入 .docx。
     *
     * 與 _handleImportFile 的差異：
     *   - _handleImportFile 走 canvas-editor 的 docx plugin（@hufe921 內建）
     *   - importViaTsEngine 走後端 /dobtor_doc/import?engine=ts → 我們自寫的 OoxmlParser → IElement[]
     *
     * 驗收用途：
     *   chichi 在 DevTools 跑 `window._docEditor.importViaTsEngine(file)`
     *   比對兩條解析路徑對同一份 .docx 的渲染差異。
     *
     * @param {File} file 使用者上傳的 .docx File 物件
     * @param {Object} [options] 預留選項，目前無
     * @returns {Promise<{success: boolean, elementCount?: number, error?: string}>}
     */
    async importViaTsEngine(file) {
        if (!file) {
            return { success: false, error: "未提供檔案" };
        }
        if (!this.editor) {
            return { success: false, error: "Canvas editor 尚未初始化" };
        }
        try {
            const formData = new FormData();
            formData.append("file", file);
            formData.append("engine", "ts");

            const resp = await fetch("/dobtor_doc/import", {
                method: "POST",
                body: formData,
            });
            const result = await resp.json();
            if (result.error) throw new Error(result.error);
            if (!Array.isArray(result.elements)) {
                throw new Error("Backend 未回傳 elements 陣列（engine=ts 可能 fallback 到 libreoffice）");
            }

            // 用 canvas-editor 的 setValue 命令直接餵 IElement[]
            this.editor.command.executeSetValue({ main: result.elements });

            this.state.statusMsg = `TS Parser 匯入成功（${result.elements.length} elements）`;
            this.state.statusType = "saved";
            this.notification.add(
                `TS Parser 匯入成功：${result.elements.length} 個 IElement`,
                { type: "success" }
            );
            return { success: true, elementCount: result.elements.length };
        } catch (e) {
            console.error("[DocEditor] importViaTsEngine 失敗：", e);
            this.notification.add(`TS Parser 匯入失敗：${e.message || e}`, { type: "danger" });
            return { success: false, error: e.message || String(e) };
        }
    }

    // ─── 匯出 PDF ────────────────────────────────────────────────────

    _promptTemplateContext() {
        const raw = this.state.contextJson.trim();
        if (!raw) return {};
        try {
            return JSON.parse(raw);
        } catch {
            this.notification.add("Context JSON 格式錯誤，請檢查輸入", { type: "warning" });
            return null;
        }
    }

    async onExportPdf() {
        // 模板模式：後端 docxtpl + LibreOffice headless → 高保真 PDF
        if (this.state.isTemplateMode && this.state.docId) {
            const ctx = this._promptTemplateContext();
            if (ctx === null) return;
            this.state.statusMsg = "匯出 PDF 中...";
            this.state.statusType = "saving";
            try {
                const result = await rpc("/dobtor_doc/fill_template", {
                    doc_id: this.state.docId,
                    context: ctx,
                    output_format: "pdf",
                });
                if (!result.success) throw new Error(result.error);
                this._downloadBase64(result.content, result.filename, result.mimetype);
                this.state.statusMsg = "就緒";
                this.state.statusType = "saved";
            } catch (e) {
                this.state.statusMsg = "就緒";
                this.state.statusType = "saved";
                this.notification.add(`PDF 匯出失敗：${e.message || e}`, { type: "danger" });
            }
            return;
        }
        // 非模板模式：canvas-editor 列印
        if (this.editor) this.editor.command.executePrint();
    }

    // ─── 匯出 DOCX ───────────────────────────────────────────────────

    async onExportDocx() {
        // 模板模式：後端 docxtpl → 填充後原始 DOCX（100% 保真）
        if (this.state.isTemplateMode && this.state.docId) {
            const ctx = this._promptTemplateContext();
            if (ctx === null) return;
            this.state.statusMsg = "匯出 DOCX 中...";
            this.state.statusType = "saving";
            try {
                const result = await rpc("/dobtor_doc/fill_template", {
                    doc_id: this.state.docId,
                    context: ctx,
                    output_format: "docx",
                });
                if (!result.success) throw new Error(result.error);
                this._downloadBase64(result.content, result.filename, result.mimetype);
                this.state.statusMsg = "就緒";
                this.state.statusType = "saved";
            } catch (e) {
                this.state.statusMsg = "就緒";
                this.state.statusType = "saved";
                this.notification.add(`DOCX 匯出失敗：${e.message || e}`, { type: "danger" });
            }
            return;
        }
        // 非模板模式：canvas-editor 原生匯出
        if (!this.editor) return;
        try {
            this.editor.command.executeExportDocx({ fileName: this.state.docName || "document" });
        } catch (e) {
            this.notification.add(`DOCX 匯出失敗：${e.message || e}`, { type: "danger" });
        }
    }

    // ─── 下載工具 ────────────────────────────────────────────────────

    _downloadBase64(b64, filename, mimetype) {
        const bytes = Uint8Array.from(atob(b64), c => c.charCodeAt(0));
        const blob = new Blob([bytes], { type: mimetype });
        const a = document.createElement("a");
        a.href = URL.createObjectURL(blob);
        a.download = filename;
        a.click();
        URL.revokeObjectURL(a.href);
    }

    onClose() {
        history.back();
    }

    // ─── Phase 8 Template UI Builder（ADR-022）/ Sprint A 收口 ──────
    //
    // Sprint A：4 個分頁全部開放、預覽接後端 template_preview 端點。
    // 各分頁殼內容見 doc_editor.xml 的 doc-subnav-panel 區塊。

    onSubNavClick(tab) {
        const allowed = ["dashboard", "requests", "templates", "settings"];
        if (!allowed.includes(tab)) {
            return;
        }
        this.state.activeSubNav = tab;
        // 切到「請求」時 lazy-load 一次填寫請求清單
        if (tab === "requests" && !this._requestsLoaded) {
            this._loadRequests();
        }
    }

    /**
     * Sprint A：開新分頁顯示填值後的範本內容。
     *
     * 流程：
     *   1. 從 state.contextJson 取 user 提供的填值資料（可選）
     *   2. POST /dobtor_doc/template_preview 取得渲染後 HTML
     *   3. window.open 開新分頁、寫入 HTML
     */
    async onPreviewClick() {
        if (!this.state.docId) {
            this.notification.add("請先儲存文件後再預覽。", { type: "warning" });
            return;
        }
        // 解析 user 提供的 context（容錯：解析失敗用空 dict）
        let contextDict = {};
        const ctxRaw = (this.state.contextJson || "").trim();
        if (ctxRaw) {
            try {
                contextDict = JSON.parse(ctxRaw);
            } catch (e) {
                this.notification.add(
                    "Context JSON 格式錯誤，將以空填值預覽。",
                    { type: "warning" }
                );
            }
        }
        try {
            const result = await rpc("/dobtor_doc/template_preview", {
                doc_id: this.state.docId,
                context: contextDict,
            });
            if (!result || !result.success) {
                this.notification.add(
                    `預覽失敗：${(result && result.error) || "未知錯誤"}`,
                    { type: "danger" }
                );
                return;
            }
            const w = window.open("", "_blank", "noopener,noreferrer");
            if (!w) {
                this.notification.add(
                    "瀏覽器阻擋新分頁。請允許彈出視窗後重試。",
                    { type: "warning" }
                );
                return;
            }
            w.document.open();
            w.document.write(result.html);
            w.document.close();
            w.document.title = `預覽：${this.state.docName || "文件"}`;
        } catch (e) {
            console.error("[DocEditor] onPreviewClick failed", e);
            this.notification.add(`預覽失敗：${e.message || e}`, { type: "danger" });
        }
    }

    /**
     * Sprint A：載入此範本的填寫請求清單（lazy，切到 requests tab 時觸發一次）。
     */
    async _loadRequests() {
        if (!this.state.docId) {
            this.state.requests = [];
            this._requestsLoaded = true;
            return;
        }
        this.state.requestsLoading = true;
        try {
            const result = await rpc("/dobtor_doc/template_requests/list", {
                doc_id: this.state.docId,
            });
            this.state.requests = (result && result.requests) || [];
            this._requestsLoaded = true;
        } catch (e) {
            console.error("[DocEditor] load requests failed", e);
            this.state.requests = [];
            this._requestsLoaded = true;
        } finally {
            this.state.requestsLoading = false;
        }
    }

    /**
     * Sprint A：設定分頁 — 切換預設簽約人角色（沿用 onSignerClick 的 state 變動，
     * 但獨立 handler 避免未來分歧）。
     */
    onDefaultSignerChange(event) {
        const newId = parseInt(event.target.value, 10);
        if (!Number.isNaN(newId)) {
            this.state.activeSignerId = newId;
        }
    }

    // ─── Sprint D：Overlay 絕對定位 ──────────────────────────────────

    /**
     * Sprint D：當前頁的 overlay fields（layout_mode='overlay' + page_no=當前）。
     * 依 state.overlayFieldsRev 強制重新計算（OWL 偵測到 state 變動才會 re-render）。
     */
    get overlayFields() {
        // 觸發 OWL 依賴追蹤
        // eslint-disable-next-line no-unused-vars
        const _rev = this.state.overlayFieldsRev;
        const list = this._templateFieldsCache || [];
        const currentPage = this.state.pageNo || 1;
        return list.filter(
            (f) => f.layout_mode === "overlay" && (f.page_no || 1) === currentPage,
        );
    }

    /**
     * Sprint D：切換插入模式（inline / overlay）。
     */
    onLayoutModeToggle(mode) {
        if (mode !== "inline" && mode !== "overlay") return;
        this.state.layoutMode = mode;
        this.notification.add(
            mode === "overlay"
                ? "已切到「浮動」模式：點欄位按鈕後可拖曳到頁面任意位置。"
                : "已切回「行內」模式：點欄位按鈕將插入游標位置。",
            { type: "info" }
        );
    }

    /**
     * Sprint D：overlay field mousedown → 拖曳到新位置 → mouseup 存後端。
     *
     * 設計：拖曳期間直接改 DOM style.left/top（避開 OWL re-render 抖動），
     * mouseup 時才呼叫 save_field 並更新 _templateFieldsCache。
     */
    onOverlayMouseDown(ev, fieldId) {
        ev.stopPropagation();
        ev.preventDefault();
        const overlayEl = ev.currentTarget;
        if (!overlayEl) return;
        const startX = ev.clientX;
        const startY = ev.clientY;
        const origLeft = parseFloat(overlayEl.style.left) || 0;
        const origTop = parseFloat(overlayEl.style.top) || 0;
        const scale = this.state.currentZoomScale || 1;
        // Sprint F：越界 clamp — workspace 邊界相對於 overlay-layer
        const overlayLayer = overlayEl.parentElement;
        const layerRect = overlayLayer?.getBoundingClientRect();
        const fieldW = parseFloat(overlayEl.style.width) || 160;
        const fieldH = parseFloat(overlayEl.style.height) || 32;
        const maxX = layerRect ? Math.max(0, layerRect.width / scale - fieldW) : Number.MAX_VALUE;
        const maxY = layerRect ? Math.max(0, layerRect.height / scale - fieldH) : Number.MAX_VALUE;
        overlayEl.classList.add("is-dragging");
        // 選中該欄位讓 inspector 顯示
        this.state.selectedFieldId = fieldId;

        const clamp = (x, y) => ({
            x: Math.max(0, Math.min(maxX, x)),
            y: Math.max(0, Math.min(maxY, y)),
        });

        const onMove = (mv) => {
            const dx = (mv.clientX - startX) / scale;
            const dy = (mv.clientY - startY) / scale;
            const { x, y } = clamp(origLeft + dx, origTop + dy);
            overlayEl.style.left = `${x}px`;
            overlayEl.style.top = `${y}px`;
        };
        const onUp = async (up) => {
            document.removeEventListener("mousemove", onMove);
            document.removeEventListener("mouseup", onUp);
            overlayEl.classList.remove("is-dragging");
            const { x: newX, y: newY } = clamp(
                origLeft + (up.clientX - startX) / scale,
                origTop + (up.clientY - startY) / scale,
            );
            // save 到後端 + 更新 cache
            try {
                const result = await rpc("/dobtor_doc/template_fields/save_field", {
                    doc_id: this.state.docId,
                    field: { id: fieldId, pos_x: newX, pos_y: newY },
                });
                if (result?.success) {
                    const f = (this._templateFieldsCache || []).find((x) => x.id === fieldId);
                    if (f) {
                        f.pos_x = newX;
                        f.pos_y = newY;
                    }
                } else {
                    this.notification.add(
                        `儲存位置失敗：${result?.error || "未知錯誤"}`,
                        { type: "warning" }
                    );
                }
            } catch (e) {
                console.warn("[DocEditor] overlay drag save failed", e);
            }
        };
        document.addEventListener("mousemove", onMove);
        document.addEventListener("mouseup", onUp);
    }

    /**
     * Sprint D：點 overlay field（不是 drag）→ 設為 selected、inspector 顯示。
     */
    onOverlayFieldClick(fieldId) {
        if (this.state.selectedFieldId !== fieldId) {
            this.state.selectedFieldId = fieldId;
        }
    }

    /**
     * Sprint F：overlay field 右下角 resize handle mousedown → mousemove 改 width/height →
     *           mouseup save_field 持久化。
     *
     * stopPropagation 必要 — 避免冒泡到 .doc-overlay-field 的 onOverlayMouseDown 觸發拖曳。
     */
    onOverlayResizeMouseDown(ev, fieldId) {
        ev.stopPropagation();
        ev.preventDefault();
        const overlayEl = ev.currentTarget.closest(".doc-overlay-field");
        if (!overlayEl) return;
        const startX = ev.clientX;
        const startY = ev.clientY;
        const origWidth = parseFloat(overlayEl.style.width) || 160;
        const origHeight = parseFloat(overlayEl.style.height) || 32;
        const scale = this.state.currentZoomScale || 1;
        const MIN_W = 40;
        const MIN_H = 20;
        overlayEl.classList.add("is-resizing");
        this.state.selectedFieldId = fieldId;

        const onMove = (mv) => {
            const dw = (mv.clientX - startX) / scale;
            const dh = (mv.clientY - startY) / scale;
            overlayEl.style.width = `${Math.max(MIN_W, origWidth + dw)}px`;
            overlayEl.style.height = `${Math.max(MIN_H, origHeight + dh)}px`;
        };
        const onUp = async (up) => {
            document.removeEventListener("mousemove", onMove);
            document.removeEventListener("mouseup", onUp);
            overlayEl.classList.remove("is-resizing");
            const newW = Math.max(MIN_W, origWidth + (up.clientX - startX) / scale);
            const newH = Math.max(MIN_H, origHeight + (up.clientY - startY) / scale);
            try {
                const result = await rpc("/dobtor_doc/template_fields/save_field", {
                    doc_id: this.state.docId,
                    field: { id: fieldId, width: newW, height: newH },
                });
                if (result?.success) {
                    const f = (this._templateFieldsCache || []).find((x) => x.id === fieldId);
                    if (f) {
                        f.width = newW;
                        f.height = newH;
                    }
                }
            } catch (e) {
                console.warn("[DocEditor] overlay resize save failed", e);
            }
        };
        document.addEventListener("mousemove", onMove);
        document.addEventListener("mouseup", onUp);
    }

    /**
     * Sprint A：設定分頁 — 切換自動儲存。
     */
    onAutoSaveToggle(event) {
        const enabled = !!event.target.checked;
        this.state.autoSaveEnabled = enabled;
        if (this._autoSaveManager) {
            if (enabled && typeof this._autoSaveManager.enable === "function") {
                this._autoSaveManager.enable();
            } else if (!enabled && typeof this._autoSaveManager.disable === "function") {
                this._autoSaveManager.disable();
            }
        }
        this.notification.add(
            enabled ? "已啟用自動儲存。" : "已關閉自動儲存（請手動按儲存）。",
            { type: "info" }
        );
    }

    /**
     * Phase 2.1：點擊欄位工具列按鈕 → 真實插入 inline control。
     *
     * 流程：
     *   1. 確保有 active signer（若 placeholder 簽約人 id < 0，先在後端建立）
     *   2. POST /dobtor_doc/template_fields/save_field 建立 doc.template.field 紀錄
     *   3. 用 canvas-editor `executeInsertControl` 在游標位置插入 control，
     *      conceptId 寫入 field.id 以便日後對應
     *   4. 更新 state.signers count + state.fieldCount
     */
    async onFieldButtonClick(fieldKey) {
        const field = FIELD_TYPES.find(f => f.key === fieldKey);
        if (!field) return;
        if (!this.editor) {
            this.notification.add("編輯器尚未初始化", { type: "warning" });
            return;
        }
        if (!this.state.docId) {
            this.notification.add("請先儲存文件後再新增欄位", { type: "warning" });
            return;
        }
        if (!this._hasTemplate) {
            this.notification.add(
                "此文件未關聯範本。請先在後台 doc.document.template_id 設定範本後再回來。",
                { type: "warning" }
            );
            return;
        }
        try {
            const signer = await this._ensureSignerExists(this.state.activeSignerId);
            if (!signer) return;

            // Sprint D：依 state.layoutMode 決定 inline 或 overlay
            const isOverlay = this.state.layoutMode === "overlay";
            const fieldPayload = {
                signer_id: signer.id,
                field_type: field.key,
                page_no: this.state.pageNo || 1,
                required: false,
                placeholder_text: field.label,
                font_size: 12,
                layout_mode: isOverlay ? "overlay" : "inline",
                pos_x: isOverlay ? 80 : 0,
                pos_y: isOverlay ? 80 : 0,
                width: 160,
                height: 32,
            };
            const saveResult = await rpc("/dobtor_doc/template_fields/save_field", {
                doc_id: this.state.docId,
                field: fieldPayload,
            });
            if (!saveResult.success) {
                this.notification.add(`新增欄位失敗：${saveResult.error}`, { type: "danger" });
                return;
            }
            // Inline 模式才插入 canvas-editor control；overlay 由 overlay layer 渲染
            if (!isOverlay) {
                this._insertControlForField(saveResult.id, field, signer);
            }

            // 把新建的 field 紀錄 push 進本地 cache
            if (!this._templateFieldsCache) this._templateFieldsCache = [];
            this._templateFieldsCache.push({
                id: saveResult.id,
                ...fieldPayload,
                odoo_field_name: "",
            });

            // 同步 state 計數
            this._applySignerCounts(saveResult.signer_field_counts);
            this.state.fieldCount = saveResult.field_count;
            this.state.selectedFieldId = saveResult.id;
            // 觸發 OWL 重 render overlay layer
            if (isOverlay) {
                this.state.overlayFieldsRev++;
                this.notification.add(
                    `已加入浮動 ${field.label} 欄位，請拖曳到目標位置。`,
                    { type: "info" }
                );
            }
        } catch (e) {
            console.error("[DocEditor] onFieldButtonClick failed", e);
            this.notification.add(`新增欄位失敗：${e.message || e}`, { type: "danger" });
        }
    }

    // ─── Phase 2.2a：HTML5 drag & drop ─────────────────────────────
    //
    // 流程：
    //   1. 從欄位工具列 button 開始拖動 → onFieldDragStart 把 fieldKey 寫進 dataTransfer
    //   2. 滑鼠進入 .doc-workspace → onWorkspaceDragOver 接受 drop（preventDefault）+ highlight
    //   3. 滑鼠在 workspace 內釋放 → onWorkspaceDrop 把滑鼠位置轉成 canvas-editor 游標 + insert
    //   4. dragend / dragleave → 清除 highlight
    //
    // canvas-editor 是文字流編輯器、不支援「在空白處放浮動欄位」，
    // 所以 drop 點會 dispatch mousedown/mouseup 給 canvas、讓 canvas-editor 自己把
    // caret 移到最近的游標位置，然後走既有 onFieldButtonClick 流程插入 inline control。

    onFieldDragStart(ev, fieldKey) {
        ev.dataTransfer.setData("text/x-doc-field-type", fieldKey);
        ev.dataTransfer.effectAllowed = "copy";
        // 自訂拖曳影像：用按鈕本身（瀏覽器預設行為已 OK，留空即可）
    }

    onFieldDragEnd() {
        // 拖曳結束（無論成不成功）都清掉 drop target highlight
        this.state.isDropTarget = false;
    }

    onWorkspaceDragOver(ev) {
        // 只接受我們自己工具列拖出的 field type；其他（外部檔案等）不攔
        const types = ev.dataTransfer && ev.dataTransfer.types;
        if (!types || !Array.from(types).includes("text/x-doc-field-type")) return;
        ev.preventDefault();
        ev.dataTransfer.dropEffect = "copy";
        if (!this.state.isDropTarget) {
            this.state.isDropTarget = true;
        }
    }

    onWorkspaceDragLeave(ev) {
        // 只在離開 workspace 元素本身（不是進入子元素）時關 highlight
        if (ev.currentTarget === ev.target ||
            !ev.currentTarget.contains(ev.relatedTarget)) {
            this.state.isDropTarget = false;
        }
    }

    async onWorkspaceDrop(ev) {
        const fieldKey = ev.dataTransfer.getData("text/x-doc-field-type");
        if (!fieldKey) return;
        ev.preventDefault();
        this.state.isDropTarget = false;

        // 把滑鼠位置映射到 canvas-editor 游標位置
        this._moveCaretToPoint(ev.clientX, ev.clientY);

        // 走既有插入流程（後端建紀錄 + executeInsertControl）
        await this.onFieldButtonClick(fieldKey);
    }

    /**
     * 把滑鼠座標 (clientX, clientY) 映射到 canvas-editor 內的游標位置。
     * 作法：dispatch synthetic mousedown + mouseup 到 canvas-editor 的內部 canvas，
     *      canvas-editor 自己會處理 hit-test 並把 caret 移到對應位置。
     *
     * 若找不到 canvas（編輯器尚未 ready），不做事；onFieldButtonClick 會自行擋下。
     */
    _moveCaretToPoint(clientX, clientY) {
        const container = this.canvasContainer?.el;
        if (!container) return;
        // canvas-editor 內可能有多個 canvas（主 page / overlay），用 elementFromPoint
        // 找實際在 (x, y) 下方的元素，若是 canvas 就 dispatch
        const target = document.elementFromPoint(clientX, clientY);
        if (!target || target.tagName !== "CANVAS") return;
        if (!container.contains(target)) return;

        const opts = { bubbles: true, cancelable: true, clientX, clientY, button: 0 };
        try {
            target.dispatchEvent(new MouseEvent("mousedown", opts));
            target.dispatchEvent(new MouseEvent("mouseup", opts));
        } catch (e) {
            console.warn("[DocEditor] 模擬點擊定位游標失敗：", e);
        }
    }

    /**
     * 在 canvas-editor 游標處插入對應 field 的 inline control。
     * conceptId = field.id（字串），日後可從 control 反查 doc.template.field。
     *
     * Sprint E：對 Odoo 欄位（field.key === 'odoo_field'）走特殊 placeholder
     *   `{{ partner_id.name }}` 風格，讓 user 在文件上一眼看出這是動態變數
     *   （與既有 docxtpl `{{ object.xxx }}` jinja2 風格一致）。
     */
    _insertControlForField(fieldId, field, signer) {
        const conceptId = String(fieldId);
        let placeholder = `[${signer.name}/${field.label}]`;
        if (field.key === "odoo_field" && field.odooFieldName) {
            placeholder = `{{ ${field.odooFieldName} }}`;
        }
        // canvas-editor control type 對應（FIELD_TYPES 的 ctrlType）
        const controlPayload = {
            type: field.ctrlType || "text",
            value: null,
            placeholder: placeholder,
            conceptId: conceptId,
            // 必填欄位：在 Phase 2.1 暫不在 control 上 enforce，由 doc.template.field.required 控
            deletable: true,
            disabled: false,
        };
        if (field.ctrlType === "checkbox") {
            // canvas-editor checkbox 需要 value 結構，留空陣列表示未勾選
            controlPayload.value = [{ value: "", code: conceptId, checked: false }];
        }
        try {
            this.editor.command.executeInsertControl(controlPayload);
        } catch (e) {
            console.error("[DocEditor] executeInsertControl failed", e);
            this.notification.add(
                `欄位資料已建立但插入文件失敗：${e.message || e}（可手動 reload 重試）`,
                { type: "warning" }
            );
        }
    }

    /**
     * 若 active signer 是 placeholder（id < 0、來自 state.signers 預設值），
     * 先在後端建立真正的 doc.template.signer 紀錄、回填 state。
     */
    async _ensureSignerExists(signerId) {
        const local = this.state.signers.find(s => s.id === signerId);
        if (!local) {
            this.notification.add("找不到當前簽約人", { type: "warning" });
            return null;
        }
        if (local.id > 0) {
            return local;  // 已是後端紀錄
        }
        const resp = await rpc("/dobtor_doc/template_fields/save_signer", {
            doc_id: this.state.docId,
            signer: {
                name: local.name,
                color: 0,
                sequence: 10,
            },
        });
        if (!resp.success) {
            this.notification.add(`建立簽約人失敗：${resp.error}`, { type: "danger" });
            return null;
        }
        // 把 placeholder 換成真實紀錄
        const updated = { id: resp.id, name: local.name, color: local.color, count: 0 };
        const idx = this.state.signers.findIndex(s => s.id === signerId);
        if (idx >= 0) {
            this.state.signers[idx] = updated;
            this.state.activeSignerId = updated.id;
        }
        return updated;
    }

    /**
     * 用後端回傳的 {signer_id: count} 更新 chip 上的數字。
     * 未在 dict 中的 signer 不動（避免覆蓋未同步的 placeholder）。
     *
     * 防禦：
     *   - JSON RPC 序列化後 dict key 一律 string；s.id 是 number。
     *     同時試 number / string key，並對 0 / null / undefined 嚴謹判斷。
     *   - OWL useState 對「array element 內部物件屬性 set」偵測 lag（E2E 已 reproduce：
     *     delete RPC 成功、後端 count 正確、但 chip DOM 不更新）。
     *     解法：用 map() 重組整個陣列、再 reassign，強制 root state proxy 觸發 re-render。
     */
    _applySignerCounts(counts) {
        if (!counts || typeof counts !== "object") return;
        this.state.signers = this.state.signers.map((s) => {
            let v = counts[s.id];
            if (v === undefined) v = counts[String(s.id)];
            if (v !== undefined && v !== null) {
                return { ...s, count: v };
            }
            return s;
        });
    }

    /**
     * 從後端載入當前 doc 對應 template 的 signers + fields。
     * 在 _loadDocument 之後呼叫，把後端紀錄合併到 state（覆蓋 Phase 1 的 placeholder）。
     */
    async _loadTemplateFields() {
        if (!this.state.docId) return;
        try {
            const data = await rpc("/dobtor_doc/template_fields/load", {
                doc_id: this.state.docId,
            });
            this._hasTemplate = !!data.has_template;
            if (!data.has_template) {
                // 沒範本：保留 placeholder signers 給視覺，但點欄位按鈕時會擋下
                return;
            }
            // 後端 signers 完整覆蓋 state.signers（每筆都附上 count）
            const signerById = {};
            for (const f of (data.fields || [])) {
                signerById[f.signer_id] = (signerById[f.signer_id] || 0) + 1;
            }
            const signers = (data.signers || []).map(s => ({
                id: s.id,
                name: s.name,
                color: this._signerColorHex(s.color),
                count: signerById[s.id] || 0,
            }));
            // 若範本一個 signer 都沒有，給一個預設「簽約人」placeholder（不寫後端、user 拖欄位時才建）
            if (signers.length === 0) {
                signers.push({ id: -1, name: "簽約人", color: "#2c2c2c", count: 0 });
            }
            this.state.signers = signers;
            this.state.activeSignerId = signers[0].id;
            this.state.fieldCount = (data.fields || []).length;
            this._templateFieldsCache = data.fields || [];
            // Phase 8 Del 同步：初始化 control id tracker 為當前已存在的 fields
            this._lastControlIds = new Set(
                this._templateFieldsCache.map(f => f.id)
            );
            // Sprint D：觸發 overlay layer re-render
            this.state.overlayFieldsRev++;
        } catch (e) {
            console.warn("[DocEditor] _loadTemplateFields failed", e);
            // 不擋編輯流程：載入失敗時保留 Phase 1 的 placeholder signers
        }
    }

    /**
     * Phase 8 Del 同步：偵測 canvas-editor 上 control 被刪 → 自動刪後端紀錄。
     *
     * 流程：
     *   1. 從 canvas-editor 取當前所有 control 的 conceptId 集合
     *   2. 與 _lastControlIds diff，找出「上次有、現在沒」的 → 是被刪掉的
     *   3. 對每個失蹤的 id 呼叫 delete_field endpoint（並行）
     *   4. 更新 cache、chip count、選中狀態、_lastControlIds
     *
     * 容錯：getControlList 在某些 canvas-editor 版本可能 throw；包 try/catch、
     *       失敗時不擋編輯流程（autoSave 自己會處理）。
     */
    async _syncDeletedControls() {
        if (!this.state.docId || !this._hasTemplate) return;
        if (this._syncingDeletes) return;  // 重入保護
        let list;
        try {
            list = this.editor?.command?.getControlList?.() || [];
        } catch (e) {
            return;  // API 不可用 → 靜默跳過（使用者仍可從 inspector 手動刪）
        }
        // canvas-editor 不同版本 getControlList 回的 shape 不同，
        // 嘗試多種路徑取 conceptId
        const currentIds = new Set();
        for (const item of list) {
            const cid = item?.control?.conceptId
                     || item?.conceptId
                     || item?.element?.control?.conceptId;
            if (!cid) continue;
            const n = parseInt(cid, 10);
            if (Number.isFinite(n)) currentIds.add(n);
        }
        const lastIds = this._lastControlIds || new Set();
        const deleted = [...lastIds].filter(id => !currentIds.has(id));
        if (deleted.length === 0) {
            this._lastControlIds = currentIds;
            return;
        }

        this._syncingDeletes = true;
        try {
            const results = await Promise.all(deleted.map(async (id) => {
                try {
                    return await rpc("/dobtor_doc/template_fields/delete_field", {
                        doc_id: this.state.docId,
                        field_id: id,
                    });
                } catch (e) {
                    console.warn("[DocEditor] 同步刪除 field", id, "失敗：", e);
                    return { success: false, error: e?.message || String(e) };
                }
            }));
            // 從 cache 移除已被刪的
            this._templateFieldsCache = (this._templateFieldsCache || [])
                .filter(f => !deleted.includes(f.id));
            // 用最後一筆成功的回應更新 chip + total count
            const last = [...results].reverse().find(r => r && r.success);
            if (last) {
                this._applySignerCounts(last.signer_field_counts);
                this.state.fieldCount = last.field_count;
            }
            // 若選中欄位被刪了，清 selectedFieldId 讓 inspector 回空狀態
            if (this.state.selectedFieldId
                && deleted.includes(this.state.selectedFieldId)) {
                this.state.selectedFieldId = null;
            }
            // 不打 notification（避免按 Del 連發 toast 干擾）
        } finally {
            this._lastControlIds = currentIds;
            this._syncingDeletes = false;
        }
    }

    /**
     * Odoo color picker 索引（0-11）→ CSS color。
     * 沿用 Odoo 後台 colour palette 的近似值。
     */
    _signerColorHex(idx) {
        const palette = [
            "#2c2c2c", // 0 default 黑
            "#ef4444", // 1 紅
            "#f97316", // 2 橙
            "#eab308", // 3 黃
            "#22c55e", // 4 綠
            "#06b6d4", // 5 青
            "#3b82f6", // 6 藍
            "#8b5cf6", // 7 紫
            "#ec4899", // 8 粉
            "#10b981", // 9 翡翠
            "#64748b", // 10 灰
            "#714B67", // 11 Odoo 紫
        ];
        return palette[idx] || palette[0];
    }

    /**
     * Sprint E：開啟 Odoo 欄位選擇器 Dialog，user 選好 Odoo 欄位後**建立可編輯的
     * `doc.template.field` 紀錄**（field_type='odoo_field' + odoo_field_name）並
     * 插入帶 conceptId 的 inline control。
     *
     * 與舊版差異：
     *   舊版（Sprint 89 復活）：只插入 `{{ object.partner_id.name }}` 純文字字串，
     *                          無法在 inspector 編輯、無法統計到 signer/field count。
     *   新版（Sprint E）：     完整走 save_field + insertControl 流程，
     *                          user 可在右側 inspector 改填寫者/必填/佔位符/字型大小、
     *                          以及最關鍵的「Odoo 欄位名稱」（XML 已有對應輸入框）。
     */
    async onOdooFieldClick() {
        if (!this.dialog) {
            this.notification.add("Dialog service 未就緒", { type: "warning" });
            return;
        }
        if (!this.editor) {
            this.notification.add("編輯器尚未初始化", { type: "warning" });
            return;
        }
        if (!this.state.docId) {
            this.notification.add("請先儲存文件後再新增 Odoo 欄位", { type: "warning" });
            return;
        }
        if (!this._hasTemplate) {
            this.notification.add(
                "此文件未關聯範本。請先在後台 doc.document.template_id 設定範本後再回來。",
                { type: "warning" }
            );
            return;
        }
        // 取得當前文件綁定的 model_name（_loadDocument 已寫入 state）。
        const modelName = this._loadedModelName || null;
        this.dialog.add(DocFieldPickerDialog, {
            modelName: modelName,
            docId: this.state.docId,
            onInsert: async (expression, label) => {
                // expression 形如 `{{ object.partner_id.name }}`；label 形如 `partner_id.name`。
                // 我們只要 label（純欄位路徑）存到 doc.template.field.odoo_field_name。
                const odooFieldName = (label || "").trim()
                    || (expression || "").replace(/[{}]/g, "").replace(/^\s*object\.\s*/, "").trim();
                if (!odooFieldName) {
                    this.notification.add("欄位名稱解析失敗", { type: "danger" });
                    return;
                }
                try {
                    const signer = await this._ensureSignerExists(this.state.activeSignerId);
                    if (!signer) return;

                    const fieldPayload = {
                        signer_id: signer.id,
                        field_type: "odoo_field",
                        page_no: this.state.pageNo || 1,
                        required: false,
                        placeholder_text: `{{ ${odooFieldName} }}`,
                        font_size: 12,
                        odoo_field_name: odooFieldName,
                    };
                    const saveResult = await rpc("/dobtor_doc/template_fields/save_field", {
                        doc_id: this.state.docId,
                        field: fieldPayload,
                    });
                    if (!saveResult.success) {
                        this.notification.add(
                            `新增 Odoo 欄位失敗：${saveResult.error}`,
                            { type: "danger" }
                        );
                        return;
                    }
                    // 插入 inline control（_insertControlForField 對 odoo_field 走 `{{ x.y }}` placeholder）
                    this._insertControlForField(
                        saveResult.id,
                        {
                            key: "odoo_field",
                            label: `Odoo: ${odooFieldName}`,
                            ctrlType: "text",
                            odooFieldName: odooFieldName,
                        },
                        signer,
                    );
                    // push cache 讓 Inspector 立即顯示
                    if (!this._templateFieldsCache) this._templateFieldsCache = [];
                    this._templateFieldsCache.push({
                        id: saveResult.id,
                        ...fieldPayload,
                        width: 120,
                        height: 24,
                        pos_x: 0,
                        pos_y: 0,
                    });
                    this._applySignerCounts(saveResult.signer_field_counts);
                    this.state.fieldCount = saveResult.field_count;
                    this.state.selectedFieldId = saveResult.id;
                    this.notification.add(
                        `已插入 Odoo 欄位「${odooFieldName}」，可在右側 inspector 編輯。`,
                        { type: "success" }
                    );
                } catch (e) {
                    console.error("[DocEditor] onOdooFieldClick insert failed", e);
                    this.notification.add(
                        `新增 Odoo 欄位失敗：${e.message || e}`,
                        { type: "danger" }
                    );
                }
            },
        });
    }

    /**
     * Sprint G：批次掃描文件內所有 `{{ var }}` jinja2 變數，為每個 unique 變數
     * 建立 doc.template.field record（field_type='odoo_field' + odoo_field_name=var）。
     *
     * 解決 Sprint E 留下的痛點：「舊文件內既有 `{{ var }}` 文字無法自動轉」——
     * 以前要手動逐個刪掉舊文字再點 Odoo 欄位按鈕重插，5 個變數要點 5 次。
     * 現在點一次「掃描變數」按鈕、後端批次建好 record，user 直接在 inspector 編輯。
     *
     * 設計取捨：
     *   - **不做 in-place text → control 替換**：canvas-editor 的 IElement 位置操作易碎，
     *     替換失敗會破壞文件結構。MVP 只建 record、不動原文，user 在 inspector 看
     *     到後可決定要不要手動刪除舊文字。完整 in-place 替換留 Sprint H+ 視需求加。
     *   - **跳過已存在的 odoo_field_name**：避免重複掃描重複建檔。
     *   - **逐個 save_field 而非 batch 端點**：5-10 個變數的場景下 N 次 RPC 仍 < 1s，
     *     無需新增後端端點。若未來掃 50+ 變數頻繁卡頓再加 batch。
     */
    async onScanVariablesClick() {
        if (!this.editor) {
            this.notification.add("編輯器尚未初始化", { type: "warning" });
            return;
        }
        if (!this.state.docId) {
            this.notification.add("請先儲存文件後再執行掃描", { type: "warning" });
            return;
        }
        if (!this._hasTemplate) {
            this.notification.add(
                "此文件未關聯範本。請先在後台 doc.document.template_id 設定範本後再回來。",
                { type: "warning" }
            );
            return;
        }

        // 取出當前 canvas-editor 完整資料，掃描 main / header / footer
        let data;
        try {
            data = this.editor.command.getValue().data;
        } catch (e) {
            console.error("[DocEditor] onScanVariablesClick getValue failed", e);
            this.notification.add(`讀取文件內容失敗：${e.message || e}`, { type: "danger" });
            return;
        }
        const scanned = scanJinja2Variables(data);
        if (scanned.length === 0) {
            this.notification.add(
                "未找到任何 `{{ var }}` 變數。如需新增，請點「Odoo 欄位」按鈕。",
                { type: "info" }
            );
            return;
        }

        // 已註冊 odoo_field_name 清單（避免重複建檔）
        const existingNames = new Set(
            (this._templateFieldsCache || [])
                .filter(f => f.field_type === "odoo_field" && f.odoo_field_name)
                .map(f => f.odoo_field_name)
        );
        const toCreate = scanned.filter(v => !existingNames.has(v.varName));
        const skipCount = scanned.length - toCreate.length;

        if (toCreate.length === 0) {
            this.notification.add(
                `找到 ${scanned.length} 個變數，但全部已是 Odoo 欄位 record（在 Inspector 中可編輯）。`,
                { type: "info" }
            );
            return;
        }

        // 使用 window.confirm 而非自訂 dialog：portal 環境 dialog service 可能不可用，
        // 且這是一次性確認、不需要複雜 UI。列出將建檔的變數名讓 user 確認。
        const previewList = toCreate
            .slice(0, 10)
            .map(v => `  • ${v.varName}（${v.occurrences} 次）`)
            .join("\n");
        const moreSuffix = toCreate.length > 10 ? `\n  ... 還有 ${toCreate.length - 10} 個` : "";
        const skipMsg = skipCount > 0 ? `\n\n（${skipCount} 個已是 Odoo 欄位、自動略過）` : "";
        const ok = window.confirm(
            `將為以下 ${toCreate.length} 個 jinja2 變數建立 Odoo 欄位 record：\n\n${previewList}${moreSuffix}${skipMsg}\n\n建立後可在右側 Inspector 編輯填寫者、必填、字型大小等屬性。\n\n確定要繼續嗎？`
        );
        if (!ok) return;

        // 先確保 active signer 存在（同 onOdooFieldClick 流程）
        const signer = await this._ensureSignerExists(this.state.activeSignerId);
        if (!signer) return;

        // 逐個 save_field（並行可能造成 race，序列化才安全）
        const created = [];
        const failed = [];
        let lastSaveResult = null;
        for (const v of toCreate) {
            const payload = {
                signer_id: signer.id,
                field_type: "odoo_field",
                page_no: this.state.pageNo || 1,
                required: false,
                placeholder_text: `{{ ${v.varName} }}`,
                font_size: 12,
                odoo_field_name: v.varName,
            };
            try {
                const resp = await rpc("/dobtor_doc/template_fields/save_field", {
                    doc_id: this.state.docId,
                    field: payload,
                });
                if (!resp.success) {
                    failed.push({ varName: v.varName, error: resp.error || "未知錯誤" });
                    continue;
                }
                created.push({ id: resp.id, varName: v.varName });
                lastSaveResult = resp;
                // push cache 讓 inspector 立即看得到
                if (!this._templateFieldsCache) this._templateFieldsCache = [];
                this._templateFieldsCache.push({
                    id: resp.id,
                    ...payload,
                    width: 120,
                    height: 24,
                    pos_x: 0,
                    pos_y: 0,
                });
            } catch (e) {
                console.error("[DocEditor] onScanVariablesClick save_field failed", v.varName, e);
                failed.push({ varName: v.varName, error: e.message || String(e) });
            }
        }

        // 用最後一次的 signer_field_counts / field_count 更新 chips（已涵蓋所有新增）
        if (lastSaveResult) {
            this._applySignerCounts(lastSaveResult.signer_field_counts);
            this.state.fieldCount = lastSaveResult.field_count;
        }

        // 結果通知
        if (failed.length === 0) {
            this.notification.add(
                `已批次建立 ${created.length} 個 Odoo 欄位 record。請至右側 Inspector 編輯詳細屬性。`,
                { type: "success" }
            );
        } else if (created.length === 0) {
            this.notification.add(
                `批次建立失敗：${failed.map(f => f.varName).join(", ")}`,
                { type: "danger" }
            );
        } else {
            this.notification.add(
                `成功 ${created.length} 個、失敗 ${failed.length} 個（${failed.map(f => f.varName).join(", ")}）。`,
                { type: "warning" }
            );
        }
    }

    /**
     * Sprint H：掃描 + 建 record + **in-place 替換**。
     *
     * 在 Sprint G 的基礎上多做一步：對 main 流的每個 `{{ var }}` match，用
     * setRange + backspace + executeInsertControl 把純文字替換為帶 conceptId
     * 的可編輯 control。完成後 user 點文件上的 control 即可在 inspector 編輯，
     * 視覺與 Sprint E onOdooFieldClick 插入的 control 完全一致。
     *
     * 標註為「實驗性」原因：
     *   - canvas-editor 的 setRange + backspace + insertControl 組合在巢狀結構
     *     （table / list / title）內可能失敗、破壞文件結構。本實作只處理 main 流，
     *     跨巢狀結構的 match 在 scanJinja2VariablesWithPositions 已過濾（會在
     *     掃描階段被作廢、不會嘗試替換）。
     *   - 替換過程任何一步丟例外都會中斷後續、但**前面已成功的替換不會回滾**
     *     （canvas-editor 沒提供 transaction API）。確認失敗時 user 可用 Ctrl+Z
     *     回退。
     *   - 萬一 reverse-order 操作仍導致位置失準（極端罕見），fallback 是依靠
     *     vitest 已驗證的位置精度測試 + 第二道 sentinel 防線。
     */
    async onScanAndReplaceClick() {
        if (!this.editor) {
            this.notification.add("編輯器尚未初始化", { type: "warning" });
            return;
        }
        if (!this.state.docId) {
            this.notification.add("請先儲存文件後再執行掃描", { type: "warning" });
            return;
        }
        if (!this._hasTemplate) {
            this.notification.add(
                "此文件未關聯範本。請先在後台 doc.document.template_id 設定範本後再回來。",
                { type: "warning" }
            );
            return;
        }

        let data;
        try {
            data = this.editor.command.getValue().data;
        } catch (e) {
            console.error("[DocEditor] onScanAndReplaceClick getValue failed", e);
            this.notification.add(`讀取文件內容失敗：${e.message || e}`, { type: "danger" });
            return;
        }

        // Sprint G 用的去重清單（含 header/footer/巢狀）— 給 user 看的總數
        const scannedAll = scanJinja2Variables(data);
        // Sprint H 用的位置清單（main 流可替換的單字元元素）
        const mainPositions = scanJinja2VariablesWithPositions(data.main || []);
        // Sprint J 用的位置清單（table 內 td.value 可替換的單字元元素）
        const tablePositions = scanJinja2VariablesInTables(data.main || []);

        // Sprint T (revert): canvas-editor 的 executeSetValue 會自動把連續同樣式的
        // single-char elements **合併**回 multi-char run（measured behavior：傳入
        // [{X},{Y},{Z}] 出來 [{XYZ}]）。所以「normalize 後 setValue 回去 + 再 scan」
        // 不可行。Sprint H/J 對 HTML-imported 內容仍會早退（mainPos=0），這是已知
        // 限制——詳見 docs/phase8_sprint_t_2026-05-24.md。Workaround：user 用
        // 「掃描變數」（Sprint G）建 record，或在 canvas-editor 內手動 type 變數
        // （typed content 是 per-char element、可被 Sprint H/J 替換）。

        // Sprint Q：用純函式 analyzeScanResults 算 positions / uniqueVars / toCreate
        const existingNames = (this._templateFieldsCache || [])
            .filter(f => f.field_type === "odoo_field" && f.odoo_field_name)
            .map(f => f.odoo_field_name);
        const analysis = analyzeScanResults({
            scannedAll,
            mainPositions,
            tablePositions,
            existingOdooFieldNames: existingNames,
        });
        const { positions, uniqueVars, toCreate } = analysis;

        if (scannedAll.length === 0) {
            this.notification.add(
                "未找到任何 `{{ var }}` 變數。",
                { type: "info" }
            );
            return;
        }
        if (positions.length === 0) {
            // Sprint W：Sprint H/J 對 HTML-imported（multi-char）內容會早退。
            // 改走兩階段路徑：先用 canvas-editor 內建的 executeSearch+executeReplace 把
            // `{{ var }}` 文字換成 unique marker，再用 marker 位置 setRange + executeBackspace
            // + executeInsertControl 把 marker 換成 odoo_field control。
            //
            // 為什麼可行（與 Sprint T setValue auto-merge 失敗對比）：
            //   - search/replace 在 element value 字串層替換、不重建 element list
            //   - setRange 對 multi-char element 也以 char 為步長（probe 已驗證 setRange(3, 20)
            //     對 single multi-char element 的 char 3..19 範圍正確 backspace）
            //   - 不經 setValue → 不觸發 canvas-editor 的 single-char element 自動合併
            //
            // 限制：本路徑目前**僅處理 main 流**。table cell 內 `{{ var }}` 仍跳過
            // （留待 Sprint X：multi-arg setRange 對 td 的 char-offset 簽名探路）。
            return await this._sprintWScanAndReplace(scannedAll);
        }

        // 確認 dialog（user 必須意識到「會替換文件內容」）
        const previewList = uniqueVars
            .slice(0, 10)
            .map(v => `  • ${v}`)
            .join("\n");
        const moreSuffix = uniqueVars.length > 10 ? `\n  ... 還有 ${uniqueVars.length - 10} 個` : "";
        // 巢狀（list/title/multi-char）的變數總量 = scannedAll 含的 var 數 − 我們能替換的 uniqueVars 數
        // 注意：scannedAll 計次但去重後與 uniqueVars 數不同；這裡只給粗略提示
        const skippedCount = scannedAll.length - uniqueVars.length;
        const skipReasonNote = skippedCount > 0
            ? `\n\n注意：另有約 ${skippedCount} 個變數位於 list/title 或多字元元素，**不會**被替換（僅 main + table cells）。`
            : "";
        const cacheNote = toCreate.length < uniqueVars.length
            ? `\n（${uniqueVars.length - toCreate.length} 個變數的 record 已存在、會被沿用）`
            : "";
        const sourceNote = tablePositions.length > 0
            ? `\n包含：main 流 ${mainPositions.length} 處、table 內 ${tablePositions.length} 處。`
            : "";
        const ok = window.confirm(
            `【實驗性功能】將為以下 ${uniqueVars.length} 個變數建立 record，並替換 ${positions.length} 處 \`{{ var }}\` 文字為可編輯 control：${sourceNote}\n\n${previewList}${moreSuffix}${cacheNote}${skipReasonNote}\n\n⚠️ 替換為不可回復操作（無 transaction）。如需先建 record 不替換，請按取消後改用「掃描變數」按鈕。\n\n確定要繼續嗎？`
        );
        if (!ok) return;

        // 確保 signer 存在
        const signer = await this._ensureSignerExists(this.state.activeSignerId);
        if (!signer) return;

        // === Sprint N: 動工前捕捉文件快照（給「復原最近一次掃描並替換」用）===
        // JSON 序列化深拷貝避免後續操作意外動到 snapshot
        // 失敗（如循環引用）→ 不捕捉、不擋流程；rollback 按鈕只在 snapshot 存在時顯示
        let preReplaceSnapshot = null;
        try {
            preReplaceSnapshot = JSON.parse(JSON.stringify(data));
        } catch (e) {
            console.warn("[DocEditor] scan-replace snapshot 捕捉失敗（rollback 不可用）", e);
        }

        // === Phase 1: 建 record ===
        const fieldIdByVarName = new Map();
        // 先把已存在的塞進 map
        for (const f of (this._templateFieldsCache || [])) {
            if (f.field_type === "odoo_field" && f.odoo_field_name && !fieldIdByVarName.has(f.odoo_field_name)) {
                fieldIdByVarName.set(f.odoo_field_name, f.id);
            }
        }
        const createFailed = [];
        let lastSaveResult = null;
        for (const varName of toCreate) {
            const payload = {
                signer_id: signer.id,
                field_type: "odoo_field",
                page_no: this.state.pageNo || 1,
                required: false,
                placeholder_text: `{{ ${varName} }}`,
                font_size: 12,
                odoo_field_name: varName,
            };
            try {
                const resp = await rpc("/dobtor_doc/template_fields/save_field", {
                    doc_id: this.state.docId,
                    field: payload,
                });
                if (!resp.success) {
                    createFailed.push({ varName, error: resp.error || "未知錯誤" });
                    continue;
                }
                fieldIdByVarName.set(varName, resp.id);
                lastSaveResult = resp;
                if (!this._templateFieldsCache) this._templateFieldsCache = [];
                this._templateFieldsCache.push({
                    id: resp.id,
                    ...payload,
                    width: 120,
                    height: 24,
                    pos_x: 0,
                    pos_y: 0,
                });
            } catch (e) {
                console.error("[DocEditor] onScanAndReplaceClick save_field failed", varName, e);
                createFailed.push({ varName, error: e.message || String(e) });
            }
        }
        if (lastSaveResult) {
            this._applySignerCounts(lastSaveResult.signer_field_counts);
            this.state.fieldCount = lastSaveResult.field_count;
        }

        // === Phase 2: in-place 替換（reverse order）===
        // 必須 reverse：每次替換改變後續 index、從尾巴開始才能保持前面位置有效。
        // 分兩段處理：
        //   2a. table 內位置（用 multi-arg setRange、按 (tableElementIdx, trIdx, tdIdx, startIdx) 全字典序倒排）
        //   2b. main 流位置（用 2-arg setRange、按 startIdx 倒排）
        // 為什麼分段：table 改動不影響 main element index、main 改動不影響 table 內部
        //   index，但**互相**不安全（如果 main 替換先做、table 元素整個移位、tableElementIdx
        //   失效）。先處理 table（內部）、後處理 main 是安全的單向。
        let replaced = 0;
        const replaceFailed = [];

        const doReplace = (pos, fieldId) => {
            this._insertControlForField(
                fieldId,
                {
                    key: "odoo_field",
                    label: `Odoo: ${pos.varName}`,
                    ctrlType: "text",
                    odooFieldName: pos.varName,
                },
                signer,
            );
        };

        // Phase 2a: table 位置（reverse 全字典序：table 大→小、tr 大→小、td 大→小、startIdx 大→小）
        const tableSorted = tablePositions.slice().sort((a, b) => {
            if (b.tableElementIdx !== a.tableElementIdx) return b.tableElementIdx - a.tableElementIdx;
            if (b.trIdx !== a.trIdx) return b.trIdx - a.trIdx;
            if (b.tdIdx !== a.tdIdx) return b.tdIdx - a.tdIdx;
            return b.startIdx - a.startIdx;
        });
        for (const pos of tableSorted) {
            const fieldId = fieldIdByVarName.get(pos.varName);
            if (!fieldId) {
                replaceFailed.push({ varName: pos.varName, reason: "no_field_id" });
                continue;
            }
            if (!pos.tableId) {
                // canvas-editor 沒給 table id → setRange 多參數簽名無法用
                replaceFailed.push({ varName: pos.varName, reason: "no_table_id" });
                continue;
            }
            try {
                this.editor.command.setRange(
                    pos.startIdx,
                    pos.endIdx + 1,
                    pos.tableId,
                    pos.tdIdx,
                    pos.tdIdx,
                    pos.trIdx,
                    pos.trIdx,
                );
                this.editor.command.backspace();
                doReplace(pos, fieldId);
                replaced++;
            } catch (e) {
                console.error("[DocEditor] onScanAndReplaceClick table replace failed", pos, e);
                replaceFailed.push({ varName: pos.varName, reason: e.message || String(e) });
            }
        }

        // Phase 2b: main 位置（reverse startIdx）
        const mainSorted = mainPositions.slice().sort((a, b) => b.startIdx - a.startIdx);
        for (const pos of mainSorted) {
            const fieldId = fieldIdByVarName.get(pos.varName);
            if (!fieldId) {
                replaceFailed.push({ varName: pos.varName, reason: "no_field_id" });
                continue;
            }
            try {
                this.editor.command.setRange(pos.startIdx, pos.endIdx + 1);
                this.editor.command.backspace();
                doReplace(pos, fieldId);
                replaced++;
            } catch (e) {
                console.error("[DocEditor] onScanAndReplaceClick main replace failed", pos, e);
                replaceFailed.push({ varName: pos.varName, reason: e.message || String(e) });
            }
        }

        // === Sprint N: 存 snapshot + 本輪新建 field id 列表，供 rollback ===
        // 只在「至少 replaced 或 toCreate 有變動」時才存（避免 user 反覆按沒變動的「掃描並替換」覆寫之前有效的 snapshot）
        if (preReplaceSnapshot && (replaced > 0 || toCreate.length > 0)) {
            const createdIds = [];
            for (const varName of toCreate) {
                const id = fieldIdByVarName.get(varName);
                if (id) createdIds.push(id);
            }
            this.state.lastScanReplaceSnapshot = {
                docData: preReplaceSnapshot,
                createdFieldIds: createdIds,
                replacedCount: replaced,
                timestamp: Date.now(),
            };
        }

        // === 結果通知 ===
        const parts = [];
        if (replaced > 0) parts.push(`已替換 ${replaced} 處文字為可編輯 control`);
        if (toCreate.length > 0) parts.push(`新建 ${toCreate.length - createFailed.length}/${toCreate.length} 個 record`);
        if (createFailed.length > 0) parts.push(`record 建立失敗：${createFailed.map(f => f.varName).join(", ")}`);
        if (replaceFailed.length > 0) parts.push(`替換失敗 ${replaceFailed.length} 處（${replaceFailed.map(r => r.varName).slice(0, 3).join(", ")}${replaceFailed.length > 3 ? "..." : ""}）`);
        const summary = parts.join("；") || "未做任何變動";
        const ntype = (createFailed.length || replaceFailed.length) > 0 ? "warning" : "success";
        const rollbackHint = (this.state.lastScanReplaceSnapshot && (replaced > 0 || toCreate.length > 0))
            ? "（如需復原請點右上角『復原』按鈕）"
            : "";
        this.notification.add(`【掃描並替換】${summary}${rollbackHint ? "。" + rollbackHint : "。"}`, { type: ntype });
    }

    /**
     * Sprint N：復原最近一次掃描並替換。
     *
     * 兩步驟：
     *   1. setValue(snapshot.docData) → 把文件還原到掃描前狀態（control 變回 {{ var }} 文字）
     *   2. delete_field(每個 createdFieldIds) → 刪掉本次新建的 record
     *      （Sprint H/J 已存在的 record 不動，避免吞掉 user 之前手動建的）
     *
     * 限制：只支援單層 undo（覆蓋式 snapshot）。snapshot 在以下情況清除：
     *   - rollback 成功後（不可再次 rollback）
     *   - user 再按一次「掃描並替換」（snapshot 被覆蓋）
     *   - editor reload（state 重置）
     *
     * 不處理：snapshot 之後的 autosave / 其他 edit。canvas-editor undo stack
     *   會被 setValue 清空（這是 canvas-editor 本身的行為、不在我們控制範圍）。
     */
    async onRollbackScanReplaceClick() {
        const snap = this.state.lastScanReplaceSnapshot;
        if (!snap) {
            this.notification.add("沒有可復原的掃描並替換操作。", { type: "info" });
            return;
        }
        const ageSec = Math.round((Date.now() - snap.timestamp) / 1000);
        const ok = window.confirm(
            `將復原最近一次「掃描並替換」：\n\n` +
            `  • 還原文件內容到掃描前狀態（${snap.replacedCount} 處 control 變回 {{ var }} 文字）\n` +
            `  • 刪除本次新建的 ${snap.createdFieldIds.length} 個 record\n\n` +
            `（執行於 ${ageSec} 秒前；本操作會覆寫期間其他編輯）\n\n確定要復原嗎？`
        );
        if (!ok) return;

        // Step 1: 還原文件
        // 注意：snap.docData 經 OWL state 包裝後是 Proxy；canvas-editor 內部會
        // 呼叫 structuredClone()，structuredClone 不接受 Proxy 會 DataCloneError。
        // 先用 JSON 深拷一份純物件交給 setValue。
        let plainDocData;
        try {
            plainDocData = JSON.parse(JSON.stringify(snap.docData));
        } catch (e) {
            console.error("[DocEditor] onRollbackScanReplaceClick deep-clone snap failed", e);
            this.notification.add(`快照解封失敗：${e.message || e}`, { type: "danger" });
            return;
        }
        try {
            this.editor.command.executeSetValue(plainDocData);
        } catch (e) {
            console.error("[DocEditor] onRollbackScanReplaceClick setValue failed", e);
            this.notification.add(`還原文件失敗：${e.message || e}`, { type: "danger" });
            return;
        }

        // Step 2: 刪除本次新建的 record
        let deleted = 0;
        const failed = [];
        let lastSuccess = null;
        for (const id of snap.createdFieldIds) {
            try {
                const r = await rpc("/dobtor_doc/template_fields/delete_field", {
                    doc_id: this.state.docId,
                    field_id: id,
                });
                if (r && r.success) {
                    deleted++;
                    lastSuccess = r;
                } else {
                    failed.push({ id, error: r?.error || "未知錯誤" });
                }
            } catch (e) {
                failed.push({ id, error: e?.message || String(e) });
            }
        }
        // 從 cache / _lastControlIds / selectedFieldId 同步移除
        const deletedSet = new Set(snap.createdFieldIds.filter((_, i) => i < deleted));
        this._templateFieldsCache = (this._templateFieldsCache || [])
            .filter(f => !snap.createdFieldIds.includes(f.id));
        for (const id of snap.createdFieldIds) this._lastControlIds?.delete(id);
        if (this.state.selectedFieldId && snap.createdFieldIds.includes(this.state.selectedFieldId)) {
            this.state.selectedFieldId = null;
        }
        if (lastSuccess) {
            this._applySignerCounts(lastSuccess.signer_field_counts);
            this.state.fieldCount = lastSuccess.field_count;
        }

        // 清 snapshot
        this.state.lastScanReplaceSnapshot = null;

        if (failed.length === 0) {
            this.notification.add(
                `已復原：文件還原 + ${deleted} 個 record 刪除。`,
                { type: "success" }
            );
        } else {
            this.notification.add(
                `部分復原：文件已還原、${deleted}/${snap.createdFieldIds.length} 個 record 刪除成功、${failed.length} 個失敗。`,
                { type: "warning" }
            );
        }
    }

    /**
     * Sprint W：對 HTML-imported（multi-char element）內容的「掃描並替換」
     * 兩階段路徑。被 onScanAndReplaceClick 在 Sprint H 位置陣列為空時 dispatch。
     *
     * Stage 1：對每個 unique varName，呼叫 canvas-editor 的 executeSearch + executeReplace
     *   把所有 `{{ varName }}` 出現處換成 unique marker 字串。canvas-editor 的 replace 在
     *   element value 字串層做替換、不重建 element list，因此不會觸發 Sprint T 發現的
     *   setValue auto-merge 問題。
     *
     * Stage 2：getValue 拿 marker-含 main，用 findMarkerPositionsInMain 找各 marker 的
     *   flat char-offset。reverse order 對每個 marker 做：
     *     setRange(start, end) → executeBackspace() → executeInsertControl(controlPayload)
     *   probe-search-control-insertion.spec.ts 證實這組合在 multi-char element 內 work。
     *
     * 限制（留待 Sprint X+）：
     *   - 不處理 table cell 內 `{{ var }}`（setRange 的 td 簽名需以 td-internal char offset 為單位）
     *   - 不處理 list / title 內變數（valueList 結構複雜，setRange 簽名待研究）
     *   - 不處理 header / footer
     */
    async _sprintWScanAndReplace(scannedAll) {
        const cmd = this.editor.command;

        // 抓 main 流的 unique varNames（只看 main、不含 header/footer/table 內變數）
        let data;
        try {
            data = cmd.getValue().data;
        } catch (e) {
            this.notification.add(`讀取文件內容失敗：${e.message || e}`, { type: "danger" });
            return;
        }
        const mainOnlyAll = scanJinja2Variables({ main: data.main });
        const mainVarNames = mainOnlyAll.map(v => v.varName);
        if (mainVarNames.length === 0) {
            this.notification.add(
                `找到 ${scannedAll.length} 個變數，但都不在 main 流（可能在 list / title 內）。請改用「掃描變數」（只建 record）。`,
                { type: "warning" }
            );
            return;
        }

        // 確認 dialog
        const previewList = mainVarNames.slice(0, 10).map(v => `  • ${v}`).join("\n");
        const more = mainVarNames.length > 10 ? `\n  ... 還有 ${mainVarNames.length - 10} 個` : "";
        const skipNote = mainVarNames.length < scannedAll.length
            ? `\n\n注意：另有約 ${scannedAll.length - mainVarNames.length} 個變數位於 list / title 內，**不會**被替換（main + table 皆會處理）。`
            : "";
        const ok = window.confirm(
            `【Sprint W/X — HTML-imported 替換】將 ${mainVarNames.length} 個變數的所有出現處替換為可編輯 control（main + table cell 皆支援）：\n\n${previewList}${more}${skipNote}\n\n⚠️ 此操作會修改文件內容（如需復原請用右上角「復原」按鈕）。\n\n確定要繼續嗎？`
        );
        if (!ok) return;

        // signer
        const signer = await this._ensureSignerExists(this.state.activeSignerId);
        if (!signer) return;

        // Snapshot for Sprint N rollback
        let preReplaceSnapshot = null;
        try {
            preReplaceSnapshot = JSON.parse(JSON.stringify(data));
        } catch (e) {
            console.warn("[DocEditor.Sprint W] snapshot 捕捉失敗（rollback 不可用）", e);
        }

        // Phase 1: 建/沿用 record
        const fieldIdByVarName = new Map();
        for (const f of (this._templateFieldsCache || [])) {
            if (f.field_type === "odoo_field" && f.odoo_field_name && !fieldIdByVarName.has(f.odoo_field_name)) {
                fieldIdByVarName.set(f.odoo_field_name, f.id);
            }
        }
        const toCreate = mainVarNames.filter(v => !fieldIdByVarName.has(v));
        const createFailed = [];
        let lastSaveResult = null;
        for (const varName of toCreate) {
            const payload = {
                signer_id: signer.id,
                field_type: "odoo_field",
                page_no: this.state.pageNo || 1,
                required: false,
                placeholder_text: `{{ ${varName} }}`,
                font_size: 12,
                odoo_field_name: varName,
            };
            try {
                const resp = await rpc("/dobtor_doc/template_fields/save_field", {
                    doc_id: this.state.docId,
                    field: payload,
                });
                if (!resp.success) {
                    createFailed.push({ varName, error: resp.error || "未知錯誤" });
                    continue;
                }
                fieldIdByVarName.set(varName, resp.id);
                lastSaveResult = resp;
                if (!this._templateFieldsCache) this._templateFieldsCache = [];
                this._templateFieldsCache.push({
                    id: resp.id,
                    ...payload,
                    width: 120,
                    height: 24,
                    pos_x: 0,
                    pos_y: 0,
                });
            } catch (e) {
                console.error("[DocEditor.Sprint W] save_field failed", varName, e);
                createFailed.push({ varName, error: e.message || String(e) });
            }
        }
        if (lastSaveResult) {
            this._applySignerCounts(lastSaveResult.signer_field_counts);
            this.state.fieldCount = lastSaveResult.field_count;
        }

        // Phase 2 / Stage 1: search/replace `{{ var }}` → unique marker per var
        // 用迴圈 + 防無窮跑（最多每變數 50 次 / 出現過 var 名相同 marker 即不重複）
        const markerByVar = new Map();   // varName -> markerText
        // 用全 ASCII marker：避免不可見字（如 U+2063）被 canvas-editor 正規化掉、
        // 也避免與使用者中文內容衝突。`__` 開頭 + `__` 結尾不會在 jinja2 var 中
        // 出現，sanitize-過的 var 名（只允許 `[A-Za-z_][\w]*`）也不會包含 `__CYSWM__` 前後綴
        for (const varName of mainVarNames) {
            // 安全 varName 含 `[\w.]` ⊆ ASCII，組合後 marker 為純 ASCII
            const safe = varName.replace(/[^A-Za-z0-9_.]/g, "_");
            markerByVar.set(varName, `__CYSWM__${safe}__`);
        }
        const REPLACE_SAFE_GUARD = 50;
        for (const varName of mainVarNames) {
            const marker = markerByVar.get(varName);
            const searchText = `{{ ${varName} }}`;
            for (let i = 0; i < REPLACE_SAFE_GUARD; i++) {
                // 檢查還有沒有 `{{ varName }}` 文字。必須用 flattenElementsToText 遞迴
                // 含 table cells（Sprint X bug：原本只看 top-level main IElements 的 .value，
                // 漏了 td.value 內的 marker → table-only vars safe-guard 直接 break、
                // search/replace 沒跑、Stage 2b 找不到 marker → 0 control）
                const curMain = cmd.getValue().data.main || [];
                const flat = flattenElementsToText(curMain);
                if (flat.indexOf(searchText) < 0) break;
                try {
                    cmd.executeSearch(searchText);
                    cmd.executeReplace(marker);
                } catch (e) {
                    console.error("[DocEditor.Sprint W] search/replace failed", varName, e);
                    break;
                }
            }
        }

        // Stage 2: 用 marker 位置 setRange + backspace + insertControl
        let replaced = 0;
        const replaceFailed = [];
        // 累計每 var 的位置（多 var 各自掃）→ 合併後按 startIdx 倒排（後面動前面不影響）
        const allMarkerPositions = [];
        // re-fetch main（前面 search/replace 已改）
        let curMain;
        try {
            curMain = cmd.getValue().data.main || [];
        } catch (e) {
            console.error("[DocEditor.Sprint W] getValue after stage 1 failed", e);
            this.notification.add(`Stage 1 後讀取文件失敗：${e.message || e}`, { type: "danger" });
            return;
        }
        for (const varName of mainVarNames) {
            const marker = markerByVar.get(varName);
            const positions = findMarkerPositionsInMain(curMain, marker);
            for (const pos of positions) {
                allMarkerPositions.push({ ...pos, varName });
            }
        }
        allMarkerPositions.sort((a, b) => b.startIdx - a.startIdx);

        // Sprint W：直接 inline 插入（用 canvas-editor 正式 IElement-with-control 包裝）。
        // 為什麼不走既有 _insertControlForField：它把 IControlBasic 直接當 payload 傳，
        // canvas-editor 把它寫入 main 變成 `type: "text"` 而非 `type: "control"`，
        // 結果 getControlList 看不到、Sprint M 孤兒檢查永遠把它判為孤兒。Sprint W 用
        // 正式結構 `{type: "control", control: {...}}` 解此問題（probe-sprint-w-handler
        // 已驗證 getControlList 數量正確）。Sprint E 的 _insertControlForField 暫不動、
        // 留到後續 sprint 對齊（風險：怕影響 user 手動點按鈕已生產的文件）。
        for (const pos of allMarkerPositions) {
            const fieldId = fieldIdByVarName.get(pos.varName);
            if (!fieldId) {
                replaceFailed.push({ varName: pos.varName, reason: "no_field_id" });
                continue;
            }
            try {
                cmd.executeSetRange ? cmd.executeSetRange(pos.startIdx, pos.endIdx) : cmd.setRange(pos.startIdx, pos.endIdx);
                cmd.executeBackspace();
                const placeholder = `{{ ${pos.varName} }}`;
                cmd.executeInsertControl({
                    type: "control",
                    value: null,
                    control: {
                        type: "text",
                        value: null,
                        placeholder,
                        conceptId: String(fieldId),
                        deletable: true,
                        disabled: false,
                    },
                });
                replaced++;
            } catch (e) {
                console.error("[DocEditor.Sprint W] setRange/backspace/insertControl failed", pos, e);
                replaceFailed.push({ varName: pos.varName, reason: e.message || String(e) });
            }
        }

        // ── Sprint X Stage 2b：table cell 內 marker 直接 mutate td.value + setValue ──
        // Stage 2a 走的 setRange+executeBackspace+executeInsertControl 路徑在 table cell
        // 第二次 insert 後會丟 "Cannot read properties of undefined (reading 'controlId')"
        // （probe-sprint-x-table 驗證、原因見 jinja2_scanner.js rewriteTdValueWithControls 註解）。
        // 改用直接 IElement 陣列 mutate + executeSetValue：對 table cell 4/4 OK。
        //
        // 注意：setValue 會 reset 整份 data，所以這段必須在 Stage 2a（main setRange+insert
        // 已完成、control 已在 data 內）之後做、用 getValue 取最新 data 為基礎、不能 reuse
        // preReplaceSnapshot（那是掃描前狀態、會丟掉 main 已插入的 control）。
        let tableReplaced = 0;
        const tableReplaceFailed = [];
        try {
            const latestData = cmd.getValue().data;
            // 反向 markerByVar → markerToField，給 rewriteTdValueWithControls 用
            const markerToField = new Map();
            for (const [varName, marker] of markerByVar.entries()) {
                const fieldId = fieldIdByVarName.get(varName);
                if (fieldId) markerToField.set(marker, { fieldId, varName });
            }
            const buildControlElement = (varName, fieldId) => ({
                type: "control",
                value: null,
                control: {
                    type: "text",
                    value: null,
                    placeholder: `{{ ${varName} }}`,
                    conceptId: String(fieldId),
                    deletable: true,
                    disabled: false,
                },
            });
            // 深拷主流（避免 OWL state Proxy + 也避免 setValue 動到原物件）
            const mutatedMain = JSON.parse(JSON.stringify(latestData.main || []));
            let anyTableChanged = false;
            for (const el of mutatedMain) {
                if (!el || el.type !== "table" || !Array.isArray(el.trList)) continue;
                for (const tr of el.trList) {
                    if (!tr || !Array.isArray(tr.tdList)) continue;
                    for (const td of tr.tdList) {
                        if (!td || !Array.isArray(td.value)) continue;
                        const { newValue, replaced: nRepl } = rewriteTdValueWithControls(
                            td.value, markerToField, buildControlElement,
                        );
                        if (nRepl > 0) {
                            td.value = newValue;
                            tableReplaced += nRepl;
                            anyTableChanged = true;
                        }
                    }
                }
            }
            if (anyTableChanged) {
                // 同樣深拷整個 data：避免 OWL Proxy + structuredClone DataCloneError（Sprint W 教訓）
                const plainData = {
                    ...latestData,
                    main: mutatedMain,
                };
                // header / footer / graffiti 若是 Proxy，executeSetValue 內部 structuredClone 也會炸
                const safePlain = JSON.parse(JSON.stringify(plainData));
                cmd.executeSetValue(safePlain);
            }
        } catch (e) {
            console.error("[DocEditor.Sprint X] table cell rewrite failed", e);
            tableReplaceFailed.push({ reason: e.message || String(e) });
        }
        replaced += tableReplaced;

        // Sprint N snapshot
        if (preReplaceSnapshot && (replaced > 0 || toCreate.length > 0)) {
            const createdIds = [];
            for (const varName of toCreate) {
                const id = fieldIdByVarName.get(varName);
                if (id) createdIds.push(id);
            }
            this.state.lastScanReplaceSnapshot = {
                docData: preReplaceSnapshot,
                createdFieldIds: createdIds,
                replacedCount: replaced,
                timestamp: Date.now(),
            };
        }

        // 結果通知
        const parts = [];
        if (replaced > 0) parts.push(`已替換 ${replaced} 處 \`{{ var }}\` 為 control（含 table ${tableReplaced} 處）`);
        if (toCreate.length > 0) parts.push(`新建 ${toCreate.length - createFailed.length}/${toCreate.length} 個 record`);
        if (createFailed.length > 0) parts.push(`record 失敗：${createFailed.map(f => f.varName).join(", ")}`);
        if (replaceFailed.length > 0) parts.push(`main 替換失敗 ${replaceFailed.length} 處`);
        if (tableReplaceFailed.length > 0) parts.push(`table 替換失敗`);
        const summary = parts.join("；") || "未做任何變動";
        const ntype = (createFailed.length || replaceFailed.length || tableReplaceFailed.length) > 0 ? "warning" : "success";
        const hint = (this.state.lastScanReplaceSnapshot && (replaced > 0 || toCreate.length > 0))
            ? "（如需復原請點右上角『復原』按鈕）" : "";
        this.notification.add(`【Sprint W/X 掃描並替換】${summary}${hint ? "。" + hint : "。"}`, { type: ntype });
    }

    /**
     * Sprint K：預覽變數 — 用 canvas-editor 的 search() API 把所有 `{{ var }}`
     * 在文件內加上高亮，**不做任何破壞性修改**。
     *
     * 用途：在按「掃描變數」/「掃描並替換」前先看一眼「哪些位置會被掃到」。
     * 補位 Sprint H/J 的破壞性操作的可見性缺口。
     *
     * 行為：
     *   - 已高亮 → 清除（toggle）
     *   - 未高亮 → 用 regex `\{\{\s*\w+(?:\.\w+)*\s*\}\}` 搜尋並高亮
     *   - 通知：「找到 N 個變數，已高亮。再按一次清除高亮。」
     *
     * 不需要 docId / template / signer——純文件內搜尋。
     */
    onPreviewVariablesClick() {
        if (!this.editor) {
            this.notification.add("編輯器尚未初始化", { type: "warning" });
            return;
        }
        // toggle：用實例旗標記住目前是高亮中還是清除中
        if (this._previewVarsActive) {
            try {
                this.editor.command.search(null);  // 清除高亮
            } catch (e) {
                console.error("[DocEditor] onPreviewVariablesClick clear failed", e);
            }
            this._previewVarsActive = false;
            this.notification.add("已清除變數高亮。", { type: "info" });
            return;
        }
        try {
            this.editor.command.search(
                "\\{\\{\\s*[A-Za-z_][\\w]*(?:\\.[A-Za-z_][\\w]*)*\\s*\\}\\}",
                { isRegEnable: true },
            );
            this._previewVarsActive = true;
            // 也跑一次掃描算數量、給 user 知道找到幾個
            try {
                const data = this.editor.command.getValue().data;
                const all = scanJinja2Variables(data);
                const total = all.reduce((sum, v) => sum + v.occurrences, 0);
                this.notification.add(
                    `找到 ${all.length} 個變數（共 ${total} 處）已高亮。再按一次清除高亮。`,
                    { type: "success" }
                );
            } catch (e) {
                // search 已成功，計數失敗時只給簡單通知
                this.notification.add("已高亮所有 `{{ var }}`。再按一次清除高亮。", { type: "success" });
            }
        } catch (e) {
            console.error("[DocEditor] onPreviewVariablesClick search failed", e);
            this.notification.add(`預覽失敗：${e.message || e}`, { type: "danger" });
        }
    }

    onSignerClick(signerId) {
        this.state.activeSignerId = signerId;
    }

    /**
     * Sprint B：縮放模式切換。
     *   auto  → executePageScaleRecovery（canvas-editor 預設值，通常 = 1）
     *   width → 計算 workspace_width / page_native_width × 0.95 後呼叫 executePageScale
     *   page  → min(workspace_w/page_w, workspace_h/page_h) × 0.95
     *
     * canvas-editor 沒有原生 fit-to-width，靠 DOM 量測 + executePageScale 達成。
     */
    onZoomFitChange(event) {
        const mode = event.target.value;
        this.state.zoomFit = mode;
        if (!this.editor) {
            return;
        }
        try {
            if (mode === "auto") {
                if (typeof this.editor.command.executePageScaleRecovery === "function") {
                    this.editor.command.executePageScaleRecovery();
                } else {
                    this.editor.command.executePageScale(1);
                }
                return;
            }
            const workspaceEl = this.canvasContainer?.el?.closest(".doc-workspace")
                || this.canvasContainer?.el?.parentElement;
            if (!workspaceEl) {
                this.notification.add("無法取得工作區尺寸，縮放未變更。", { type: "warning" });
                return;
            }
            // 找出實際 page canvas 量測原生尺寸（每頁有一個 <canvas>）
            const pageCanvas = this.canvasContainer.el.querySelector("canvas");
            if (!pageCanvas) {
                this.notification.add("找不到頁面元素，縮放未變更。", { type: "warning" });
                return;
            }
            // canvas-editor 用 devicePixelRatio 放大 canvas backing store；
            // pageCanvas.width/.height 是 backing pixels，需除以 pixelRatio 還原邏輯尺寸
            const ratio = (typeof this.editor.command.getPagePixelRatio === "function"
                ? this.editor.command.getPagePixelRatio()
                : (window.devicePixelRatio || 1)) || 1;
            // 當前縮放：state.currentZoomScale 由 pageScaleChange listener 同步
            const currentScale = this.state.currentZoomScale || 1;
            const logicalPageWidth = pageCanvas.width / ratio / currentScale;
            const logicalPageHeight = pageCanvas.height / ratio / currentScale;
            const workspaceRect = workspaceEl.getBoundingClientRect();
            // 預留 5% margin 給 scrollbar 與視覺留白
            const PADDING = 0.95;
            let newScale = 1;
            if (mode === "width") {
                newScale = (workspaceRect.width * PADDING) / logicalPageWidth;
            } else if (mode === "page") {
                newScale = Math.min(
                    (workspaceRect.width * PADDING) / logicalPageWidth,
                    (workspaceRect.height * PADDING) / logicalPageHeight,
                );
            }
            // canvas-editor executePageScale 範圍：0.5 ~ 3
            newScale = Math.max(0.5, Math.min(3, newScale));
            this.editor.command.executePageScale(newScale);
        } catch (e) {
            console.warn("[DocEditor] onZoomFitChange failed", e);
            this.notification.add(`縮放切換失敗：${e.message || e}`, { type: "warning" });
        }
    }

    /**
     * Sprint B：上一頁／下一頁。
     *
     * canvas-editor 沒有暴露 `editor.command.executePageNo`，但每頁渲染為獨立
     * `<canvas>` 元素於容器內。透過 `scrollIntoView` 把對應頁滾入視野，
     * 隨後由 `intersectionPageNoChange` listener 回寫 state.pageNo。
     */
    onPrevPage() {
        if (this.state.pageNo > 1) {
            this._scrollToPage(this.state.pageNo - 1);
        }
    }

    onNextPage() {
        if (this.state.pageNo < this.state.totalPages) {
            this._scrollToPage(this.state.pageNo + 1);
        }
    }

    /**
     * Sprint B 共用：把指定頁（1-based）滾入視野。
     */
    _scrollToPage(targetPageOneBased) {
        if (!this.editor || !this.canvasContainer?.el) {
            return;
        }
        const target = parseInt(targetPageOneBased, 10);
        if (!Number.isFinite(target) || target < 1) {
            return;
        }
        try {
            // canvas-editor 每頁渲染為一個 <canvas>；用 nth-of-type 選第 N 個
            const pageCanvases = this.canvasContainer.el.querySelectorAll("canvas");
            const idx = target - 1;
            if (idx < 0 || idx >= pageCanvases.length) {
                this.notification.add(
                    `第 ${target} 頁不存在（文件共 ${pageCanvases.length} 頁）`,
                    { type: "warning" }
                );
                return;
            }
            pageCanvases[idx].scrollIntoView({ behavior: "smooth", block: "start" });
            // 樂觀更新 state.pageNo；intersectionPageNoChange listener 隨後會校正
            this.state.pageNo = target;
        } catch (e) {
            console.warn("[DocEditor] _scrollToPage failed", e);
        }
    }

    // ─── 版本管理（W7-8 P1-1）─────────────────────────────────────

    async onSaveVersion() {
        if (!this.state.docId) return;
        const label = prompt("請輸入版本標籤（可空白）：") || "";
        try {
            const result = await rpc("/dobtor_doc/save_version", {
                doc_id: this.state.docId,
                label: label,
            });
            if (result?.success) {
                this.notification.add(
                    `版本 v${result.version_number} 已儲存`,
                    { type: "success" }
                );
            }
        } catch (e) {
            this.notification.add(`版本儲存失敗：${e.message || e}`, { type: "danger" });
        }
    }

    onShowVersionPanel() {
        if (!this.state.docId) {
            this.notification.add("請先儲存文件後再查看版本歷史。", { type: "warning" });
            return;
        }
        this.state.showVersionPanel = true;
    }

    onCloseVersionPanel() {
        this.state.showVersionPanel = false;
    }

    async onVersionRestored(result) {
        // 還原成功後重新載入文件內容
        this.state.showVersionPanel = false;
        this.notification.add(
            `已還原至 v${result.restored_version}（當前 v${result.new_current_version}）`,
            { type: "success" }
        );
        if (this.state.docId) {
            await this._loadDocument(this.state.docId);
            // 用新內容重新初始化 canvas-editor
            if (this.editor && this._loadedContentJson) {
                try {
                    const data = JSON.parse(this._loadedContentJson);
                    this.editor.command.executeSetValue(data);
                } catch (e) {
                    console.error("[DocEditor] 還原後重設 canvas content 失敗", e);
                }
            }
        }
    }

    // ─── Phase 2.1 補項：Inspector 雙向綁定 ──────────────────────────

    /**
     * 從 _templateFieldsCache 找當前選中的 field record。
     * 若找不到（cache 過期 / 還沒重新載），回 null，inspector 顯示空狀態。
     */
    get selectedField() {
        if (!this.state.selectedFieldId) return null;
        const list = this._templateFieldsCache || [];
        return list.find(f => f.id === this.state.selectedFieldId) || null;
    }

    /**
     * Sprint L：給 inspector 上方顯示「所有欄位」列表用的 getter。
     *
     * 從 _templateFieldsCache 取出排序穩定的列表：
     *   - 主排序：page_no 升冪（一頁文件、跨頁範本對齊瀏覽順序）
     *   - 次排序：id 升冪（同頁照建檔順序，新建檔的排後）
     *
     * 不做 dedup（每個 record 都是獨立欄位、即便 odoo_field_name 相同也代表
     * 文件內多處對應）。
     */
    get fieldsList() {
        const list = this._templateFieldsCache || [];
        return [...list].sort((a, b) => {
            const pa = a.page_no || 1;
            const pb = b.page_no || 1;
            if (pa !== pb) return pa - pb;
            return (a.id || 0) - (b.id || 0);
        });
    }

    /**
     * Sprint O：套用 state.fieldListFilter 對 fieldsList 做 substring filter。
     *
     * 三個欄位都會被比對（case-insensitive）：
     *   - odoo_field_name（如 `partner_id.name`）
     *   - placeholder_text（如 `{{ project_name }}`）
     *   - field_type（如 `odoo_field`、`text`、`signature`）
     *
     * 空字串 → 回 fieldsList 原樣（不過濾）。
     */
    get filteredFieldsList() {
        const filter = (this.state.fieldListFilter || "").trim().toLowerCase();
        if (!filter) return this.fieldsList;
        return this.fieldsList.filter((f) => {
            const haystack = [
                f.odoo_field_name || "",
                f.placeholder_text || "",
                f.field_type || "",
            ].join(" ").toLowerCase();
            return haystack.includes(filter);
        });
    }

    /**
     * Sprint O：filter input 變更時觸發。直接寫 state，OWL 自動 re-render。
     * 不做 debounce —— 純記憶體 substring 比對在 < 500 fields 規模下 < 0.1ms。
     *
     * Sprint P：filter 變動時 reset focusedListIndex（避免指向不存在的 row）。
     */
    onFieldListFilterInput(value) {
        this.state.fieldListFilter = value || "";
        this.state.focusedListIndex = -1;
    }

    /**
     * Sprint P：inspector 列表的鍵盤導航。
     *
     * 綁在 ul.doc-inspector-fields-list-items 的 keydown listener 上：
     *   - ↓ / ↑   ：focusedListIndex ± 1（clamp 到 [0, length-1]）；scrollIntoView
     *   - Home    ：focusedListIndex = 0
     *   - End     ：focusedListIndex = length - 1
     *   - Enter   ：呼叫 onFieldListRowClick(filteredFieldsList[focused].id)
     *   - Escape  ：focusedListIndex = -1，blur ul
     *
     * 設計：focusedListIndex 與 selectedFieldId 分離 —— 鍵盤導覽時可以「先標
     * 在某 row 上不選」（focused），按 Enter 才真正 select + locateControl。
     * 與 selectedFieldId 視覺對比：focused = 藍框 / selected = 紫底。
     */
    onFieldListKeyDown(ev) {
        const list = this.filteredFieldsList;
        if (!list || list.length === 0) return;
        const cur = this.state.focusedListIndex;
        let next = cur;
        switch (ev.key) {
            case "ArrowDown":
                next = cur < 0 ? 0 : Math.min(cur + 1, list.length - 1);
                break;
            case "ArrowUp":
                next = cur < 0 ? list.length - 1 : Math.max(cur - 1, 0);
                break;
            case "Home":
                next = 0;
                break;
            case "End":
                next = list.length - 1;
                break;
            case "Enter":
                if (cur >= 0 && cur < list.length) {
                    this.onFieldListRowClick(list[cur].id);
                    ev.preventDefault();
                }
                return;
            case "Escape":
                this.state.focusedListIndex = -1;
                ev.target?.blur?.();
                ev.preventDefault();
                return;
            default:
                return;  // 其他鍵不擋（讓 user 輸入到 filter 走別的 listener）
        }
        if (next !== cur) {
            this.state.focusedListIndex = next;
            ev.preventDefault();
            // scrollIntoView：等下次 microtask、DOM 更新後再 scroll
            Promise.resolve().then(() => {
                try {
                    const ul = ev.currentTarget;
                    const li = ul?.querySelectorAll?.("li.doc-inspector-fields-list-item")?.[next];
                    li?.scrollIntoView?.({ block: "nearest" });
                } catch (e) {
                    // 任何 DOM 操作失敗都不擋
                }
            });
        }
    }

    /**
     * Sprint M：在 _templateFieldsCache 中、但沒有對應 control 在文件內的
     * field id 集合（孤兒 record）。
     *
     * 形成原因：
     *   1. user 用 Sprint G「掃描變數」只建 record、文件仍是純 `{{ var }}` 文字
     *   2. user 手動刪掉某個 control 但 Phase 8 Del 同步因故沒同步（極罕見 race）
     *   3. record 透過 inspector「刪除」清掉、但對應 control 還在（反向 race）
     *
     * 效能：每次 render 都會走 getControlList() + Set.has() × cache.length。
     *      10-50 個 control 的常態下 < 1ms；> 500 時可改用 state.controlListRev
     *      memoize（目前 KISS）。
     */
    get orphanRecordIds() {
        const cache = this._templateFieldsCache || [];
        if (cache.length === 0) return new Set();
        // 從 canvas-editor 抽當前 control list 的 conceptId 集合（IO 部分）
        let controlIds;
        try {
            const list = this.editor?.command?.getControlList?.() || [];
            controlIds = new Set();
            for (const item of list) {
                const cid = item?.control?.conceptId
                         || item?.conceptId
                         || item?.element?.control?.conceptId;
                if (!cid) continue;
                const n = parseInt(cid, 10);
                if (Number.isFinite(n)) controlIds.add(n);
            }
        } catch (e) {
            // getControlList 在某些 canvas-editor 版本可能 throw → 退化：不標孤兒
            return new Set();
        }
        // 純函式做 diff（Sprint Q 抽出至 jinja2_scanner.js，方便單測）
        return computeOrphanRecordIds(cache, controlIds);
    }

    /**
     * Sprint M：批次刪除所有孤兒 record。
     *   - 列出將被刪的 id + 變數名（top 5）讓 user 確認
     *   - Promise.all 並行 delete_field
     *   - 從 cache / _lastControlIds / selectedFieldId 移除
     *   - 用最後一次 success response 更新 signer count + field count
     */
    async onCleanupOrphansClick() {
        if (!this.state.docId || !this._hasTemplate) {
            this.notification.add("此文件未關聯範本", { type: "warning" });
            return;
        }
        const orphans = this.orphanRecordIds;
        if (orphans.size === 0) {
            this.notification.add("沒有孤兒 record 需要清理。", { type: "info" });
            return;
        }
        const cache = this._templateFieldsCache || [];
        const orphanFields = cache.filter(f => orphans.has(f.id));
        const preview = orphanFields
            .slice(0, 5)
            .map(f => `  • ${f.odoo_field_name || f.placeholder_text || f.field_type} (#${f.id})`)
            .join("\n");
        const moreSuffix = orphanFields.length > 5 ? `\n  ... 還有 ${orphanFields.length - 5} 個` : "";
        const ok = window.confirm(
            `將刪除 ${orphans.size} 個沒有文件內 control 對應的孤兒 record：\n\n${preview}${moreSuffix}\n\n確定要繼續嗎？`
        );
        if (!ok) return;

        const ids = [...orphans];
        let lastSuccess = null;
        const failed = [];
        const results = await Promise.all(ids.map(async (id) => {
            try {
                const r = await rpc("/dobtor_doc/template_fields/delete_field", {
                    doc_id: this.state.docId,
                    field_id: id,
                });
                if (r && r.success) {
                    lastSuccess = r;
                    return { id, ok: true };
                }
                failed.push({ id, error: r?.error || "未知錯誤" });
                return { id, ok: false };
            } catch (e) {
                failed.push({ id, error: e?.message || String(e) });
                return { id, ok: false };
            }
        }));

        const deleted = results.filter(r => r.ok).map(r => r.id);
        if (deleted.length > 0) {
            this._templateFieldsCache = (this._templateFieldsCache || [])
                .filter(f => !deleted.includes(f.id));
            for (const id of deleted) this._lastControlIds?.delete(id);
            if (this.state.selectedFieldId && deleted.includes(this.state.selectedFieldId)) {
                this.state.selectedFieldId = null;
            }
            if (lastSuccess) {
                this._applySignerCounts(lastSuccess.signer_field_counts);
                this.state.fieldCount = lastSuccess.field_count;
            }
        }
        if (failed.length === 0) {
            this.notification.add(`已清理 ${deleted.length} 個孤兒 record。`, { type: "success" });
        } else {
            this.notification.add(
                `清理 ${deleted.length}/${orphans.size} 個，${failed.length} 個失敗（${failed.map(f => `#${f.id}`).slice(0, 3).join(", ")}${failed.length > 3 ? "..." : ""}）`,
                { type: "warning" }
            );
        }
    }

    /**
     * Sprint L：點 inspector 欄位列表的 row 時觸發。
     *   1. 設 selectedFieldId（讓下方屬性區顯示該 field 的編輯欄位）
     *   2. 呼叫 canvas-editor locationControl(conceptId) 把游標 / 視窗
     *      跳到文件內對應 control 位置（reverse 上：原本是「點 control 跳
     *      inspector」、此處反向「點 inspector 跳 control」）
     *
     * 容錯：locationControl 在某些 canvas-editor 版本可能不存在或 throw、
     *       靜默 catch、selectedFieldId 仍會被設好（inspector 編輯仍可用）。
     */
    onFieldListRowClick(fieldId) {
        if (!fieldId) return;
        // 設 selectedFieldId（讓 inspector 屬性區顯示此欄位）
        if (this.state.selectedFieldId !== fieldId) {
            this.state.selectedFieldId = fieldId;
        }
        // 跳到文件內對應 control
        try {
            this.editor?.command?.locationControl?.(String(fieldId));
        } catch (e) {
            // 該 fieldId 在文件內沒有對應 control（記錄存在但 control 未插入
            // 或已被刪），locationControl 會 throw、靜默忽略
            console.debug("[DocEditor] locationControl skipped for field", fieldId, e?.message);
        }
    }

    /**
     * 從 FIELD_TYPES 拿到選中 field 的 label（顯示在 inspector header）。
     */
    get selectedFieldLabel() {
        const f = this.selectedField;
        if (!f) return "";
        const meta = FIELD_TYPES.find(x => x.key === f.field_type);
        return meta ? meta.label : f.field_type;
    }

    /**
     * Inspector 內欄位變動時呼叫，debounce 500ms 後送後端 save_field。
     * key: 'placeholder_text' | 'required' | 'font_size' | 'odoo_field_name' | 'signer_id'
     *      | 'pos_x' | 'pos_y' | 'width' | 'height'（Sprint F：overlay 模式可改）
     */
    onInspectorFieldChange(key, value) {
        const field = this.selectedField;
        if (!field) return;
        // 本地立即更新（樂觀 UI），保證輸入流暢
        if (key === "required") {
            field[key] = !!value;
        } else if (key === "font_size" || key === "signer_id") {
            field[key] = parseInt(value, 10) || field[key];
        } else if (key === "pos_x" || key === "pos_y" || key === "width" || key === "height") {
            // Sprint F：浮點數，但 user 輸入整數即可
            const n = parseFloat(value);
            if (Number.isFinite(n)) {
                field[key] = Math.max(0, n);
            }
            // 強制 OWL re-render overlay layer 以反映新位置/尺寸
            this.state.overlayFieldsRev++;
        } else {
            field[key] = value;
        }

        // debounce save
        if (this._inspectorSaveTimer) clearTimeout(this._inspectorSaveTimer);
        this._inspectorSaveTimer = setTimeout(async () => {
            try {
                const payload = {
                    id: field.id,
                    signer_id: field.signer_id,
                    field_type: field.field_type,
                    page_no: field.page_no,
                    required: field.required,
                    placeholder_text: field.placeholder_text,
                    font_size: field.font_size,
                    odoo_field_name: field.odoo_field_name,
                    // Sprint F：overlay 幾何屬性
                    pos_x: field.pos_x,
                    pos_y: field.pos_y,
                    width: field.width,
                    height: field.height,
                };
                const result = await rpc("/dobtor_doc/template_fields/save_field", {
                    doc_id: this.state.docId,
                    field: payload,
                });
                if (!result.success) {
                    this.notification.add(`欄位更新失敗：${result.error}`, { type: "danger" });
                    return;
                }
                this._applySignerCounts(result.signer_field_counts);
                this.state.fieldCount = result.field_count;
            } catch (e) {
                console.error("[DocEditor] onInspectorFieldChange save failed", e);
                this.notification.add(`欄位更新失敗：${e.message || e}`, { type: "danger" });
            }
        }, 500);
    }

    /**
     * Inspector 「刪除欄位」按鈕：刪後端紀錄 + 從 cache 移除 + 清 selectedFieldId。
     * 注意 canvas-editor 上的 inline control 不會自動同步刪除（user 需自行按 Del 鍵）。
     */
    async onInspectorDeleteField() {
        const field = this.selectedField;
        if (!field) return;
        try {
            const result = await rpc("/dobtor_doc/template_fields/delete_field", {
                doc_id: this.state.docId,
                field_id: field.id,
            });
            if (!result.success) {
                this.notification.add(`刪除失敗：${result.error}`, { type: "danger" });
                return;
            }
            // 從 cache 移除
            this._templateFieldsCache = (this._templateFieldsCache || []).filter(f => f.id !== field.id);
            // 從 control id tracker 移除（避免 contentChange 誤發無效 RPC）
            this._lastControlIds?.delete(field.id);
            this._applySignerCounts(result.signer_field_counts);
            this.state.fieldCount = result.field_count;
            this.state.selectedFieldId = null;
            this.notification.add(
                "後端欄位紀錄已刪除。文件上的占位符請按 [Del] 移除。",
                { type: "info" }
            );
        } catch (e) {
            this.notification.add(`刪除失敗：${e.message || e}`, { type: "danger" });
        }
    }

    // ─── 工具方法 ────────────────────────────────────────────────────

    get statusClass() {
        const map = {
            saved:  "doc-statusbar-saved",
            saving: "doc-statusbar-saving",
            error:  "doc-statusbar-error",
        };
        return map[this.state.statusType] || "";
    }

    get offlineBadge() {
        return !this.state.isOnline;
    }

    // ─── Sprint Y2：ruler 動態跟 paper size + zoom 同步 ──────────────
    /**
     * 目前 paper width（公分）。1cm = 96/2.54 ≈ 37.795 px @ 96 DPI；
     * 反算現有 onPageFormatChange 的 PAGE_SIZES px → cm。
     */
    get _paperWidthCm() {
        const PAPER_W_CM = {
            A4: 21.0,
            A3: 29.7,
            A5: 14.8,
            letter: 21.59,
            legal: 21.59,
        };
        return PAPER_W_CM[this.state.pageFormat] || 21.0;
    }

    /**
     * ruler tick label 陣列（1, 2, ..., ceil(paperWidthCm)）。
     * 取整數公分，最後一格可能略超出紙張寬（視覺無妨）。
     */
    get rulerTicks() {
        const n = Math.ceil(this._paperWidthCm);
        const out = [];
        for (let i = 1; i <= n; i++) out.push(i);
        return out;
    }

    /**
     * ruler inline style：`--ruler-cm-px` 跟 zoom scale 同步（37.8px × zoom）。
     * CSS 用 `flex: 0 0 var(--ruler-cm-px)` 撐每個 tick 寬、整個 ruler 寬度
     * = ticks × cm-px = 跟 canvas 紙張視覺寬同步。
     */
    get rulerStyle() {
        const CM_PX_BASE = 37.795;   // 96 DPI / 2.54
        const scale = this.state.currentZoomScale || 1;
        const cmPx = (CM_PX_BASE * scale).toFixed(2);
        return `--ruler-cm-px: ${cmPx}px;`;
    }

    // ─── Sprint Y3：Google Docs 風 功能 menu bar ──────────────────
    // 6 個下拉 menu（檔案/編輯/查看/插入/格式/工具），互動：
    //   1. 點 trigger 開/關 dropdown
    //   2. dropdown 開著時 hover 其他 trigger → 切換到該 menu（Google Docs 行為）
    //   3. 點 menu-item → 跑 action 後關閉
    //   4. 點外 / 按 Escape → 關閉（listener 在 setup 註冊）

    onMenuTriggerClick(name) {
        this.state.openMenu = (this.state.openMenu === name) ? null : name;
    }

    onMenuTriggerHover(name) {
        // 只在已有 menu 開著時才 hover-switch（避免單純滑過 trigger 就自動展開）
        if (this.state.openMenu && this.state.openMenu !== name) {
            this.state.openMenu = name;
        }
    }

    onMenuItemClick(action) {
        this.state.openMenu = null;
        if (!action) return;
        try {
            switch (action) {
                case 'file:rename': this._focusTitleInput(); break;
                case 'file:import': this.onImportClick(); break;
                case 'file:export-pdf': this.onExportPdf(); break;
                case 'file:export-docx': this.onExportDocx(); break;
                case 'file:print': this._executeCmd('executePrint'); break;
                case 'file:preview': this.onPreviewClick(); break;
                case 'file:save': this.onSave(); break;
                case 'file:close': this.onClose(); break;

                case 'edit:undo': this._executeCmd('executeUndo'); break;
                case 'edit:redo': this._executeCmd('executeRedo'); break;
                case 'edit:cut': this._tryExecCommand('cut'); break;
                case 'edit:copy': this._tryExecCommand('copy'); break;
                case 'edit:paste': this._tryExecCommand('paste'); break;
                case 'edit:find': this.openFindReplace('find'); break;
                case 'edit:replace': this.openFindReplace('replace'); break;

                case 'view:toggle-ruler': this.state.showRuler = !this.state.showRuler; break;
                case 'view:toggle-thumbnails': this.state.showThumbnails = !this.state.showThumbnails; break;
                case 'view:zoom-50': this._setZoom(0.5); break;
                case 'view:zoom-100': this._setZoom(1); break;
                case 'view:zoom-150': this._setZoom(1.5); break;
                case 'view:zoom-200': this._setZoom(2); break;
                case 'view:zoom-fit': this.onZoomFitChange({ target: { value: 'width' } }); break;
                case 'view:fullscreen': this._requestFullscreen(); break;

                case 'insert:table': this._executeCmd('executeInsertTable', 3, 3); break;
                case 'insert:image': this._insertImagePicker(); break;
                case 'insert:var-text': this.onFieldButtonClick('text'); break;
                case 'insert:var-date': this.onFieldButtonClick('date'); break;
                case 'insert:var-checkbox': this.onFieldButtonClick('checkbox'); break;

                case 'format:bold': this._executeCmd('executeBold'); break;
                case 'format:italic': this._executeCmd('executeItalic'); break;
                case 'format:underline': this._executeCmd('executeUnderline'); break;
                case 'format:strikeout': this._executeCmd('executeStrikeout'); break;
                case 'format:align-left': this._executeCmd('executeRowFlex', 'left'); break;
                case 'format:align-center': this._executeCmd('executeRowFlex', 'center'); break;
                case 'format:align-right': this._executeCmd('executeRowFlex', 'right'); break;
                case 'format:align-justify': this._executeCmd('executeRowFlex', 'alignment'); break;
                case 'format:clear-format': this._executeCmd('executePainterStyle', {}); break;

                case 'tools:scan-vars': this.onScanVariablesClick(); break;
                case 'tools:scan-replace': this.onScanAndReplaceClick(); break;
                case 'tools:preview-vars': this.onPreviewVariablesClick(); break;
                case 'tools:rollback': this.onRollbackScanReplaceClick(); break;
                case 'tools:word-count': this._countWords(); break;
                case 'tools:version-history': this.onShowVersionPanel(); break;
            }
        } catch (e) {
            console.error('[DocEditor.menubar] action failed:', action, e);
            this.notification?.add?.(`動作執行失敗：${action}`, { type: 'warning' });
        }
    }

    // ─── menu 動作底層 helpers ───
    _executeCmd(name, ...args) {
        try {
            const fn = this.editor?.command?.[name];
            if (typeof fn === 'function') {
                fn.apply(this.editor.command, args);
                return true;
            }
            this.notification?.add?.(`canvas-editor 不支援命令：${name}`, { type: 'warning' });
            return false;
        } catch (e) {
            console.error('[DocEditor._executeCmd]', name, e);
            this.notification?.add?.(`命令執行失敗：${name}`, { type: 'warning' });
            return false;
        }
    }

    _tryExecCommand(cmd) {
        try {
            const ok = document.execCommand(cmd);
            if (!ok) {
                this.notification?.add?.(`瀏覽器拒絕執行：${cmd}（請改用快捷鍵）`, { type: 'info' });
            }
        } catch (e) { /* ignore */ }
    }

    _setZoom(scale) {
        try {
            if (this.editor?.command?.executePageScale) {
                this.editor.command.executePageScale(scale);
            }
            this.state.currentZoomScale = scale;
        } catch (e) {
            console.error('[DocEditor._setZoom]', e);
        }
    }

    _countWords() {
        try {
            const data = this.editor?.command?.getValue?.()?.data;
            if (!data) return;
            const flat = flattenElementsToText(data.main || []);
            const chars = flat.length;
            const words = flat.trim().split(/\s+/).filter(Boolean).length;
            this.notification?.add?.(`字數統計：${chars} 字（含空白）／${words} 詞`, { type: 'info' });
        } catch (e) {
            console.error('[DocEditor._countWords]', e);
        }
    }

    _focusTitleInput() {
        try {
            const el = document.querySelector('.o_dobtor_doc_editor .doc-header-title');
            el?.focus?.();
            el?.select?.();
        } catch (e) { /* ignore */ }
    }

    _requestFullscreen() {
        try {
            if (document.fullscreenElement) {
                document.exitFullscreen?.();
            } else {
                document.documentElement.requestFullscreen?.();
            }
        } catch (e) { /* ignore */ }
    }

    _insertImagePicker() {
        try {
            const input = document.createElement('input');
            input.type = 'file';
            input.accept = 'image/*';
            input.onchange = () => {
                const file = input.files?.[0];
                if (!file) return;
                const reader = new FileReader();
                reader.onload = () => {
                    const dataUrl = reader.result;
                    const fn = this.editor?.command?.executeInsertImage;
                    if (typeof fn !== 'function') {
                        this.notification?.add?.('canvas-editor 不支援插入圖片', { type: 'warning' });
                        return;
                    }
                    const img = new Image();
                    img.onload = () => {
                        const maxW = 600;
                        const w = Math.min(img.naturalWidth, maxW);
                        const h = (img.naturalHeight / img.naturalWidth) * w;
                        try {
                            this.editor.command.executeInsertImage({ value: dataUrl, width: w, height: h });
                        } catch (e) {
                            console.error('[DocEditor._insertImagePicker] insert failed', e);
                        }
                    };
                    img.src = dataUrl;
                };
                reader.readAsDataURL(file);
            };
            input.click();
        } catch (e) {
            console.error('[DocEditor._insertImagePicker]', e);
        }
    }

    // ─── Sprint Y4：尋找／取代 panel handlers ─────────────────────
    // canvas-editor API：executeSearch(text|null) / executeReplace(newText) /
    // executeSearchNavigateNext / executeSearchNavigatePre
    openFindReplace(mode) {
        this.state.findReplaceMode = mode;
        this.state.openMenu = null;
        // OWL render 是非同步 — 用 setTimeout 跳到下一輪 macrotask 才 focus 到新 DOM。
        // Promise.resolve().then() 在 OWL commit 之前就執行了、抓不到 input。
        setTimeout(() => {
            const el = document.querySelector('.o_dobtor_doc_editor .doc-find-input');
            if (el) { el.focus(); el.select(); }
        }, 50);
        if (this.state.findText) {
            try { this.editor?.command?.executeSearch?.(this.state.findText); } catch (e) { /* ignore */ }
        }
    }

    closeFindReplace() {
        this.state.findReplaceMode = false;
        try { this.editor?.command?.executeSearch?.(null); } catch (e) { /* ignore */ }
    }

    onFindTextInput(ev) {
        this.state.findText = ev.target.value;
        try {
            this.editor?.command?.executeSearch?.(this.state.findText || null);
        } catch (e) { /* ignore */ }
    }

    onReplaceTextInput(ev) {
        this.state.replaceText = ev.target.value;
    }

    onFindNext() {
        if (!this.state.findText) return;
        this._executeCmd('executeSearchNavigateNext');
    }

    onFindPrev() {
        if (!this.state.findText) return;
        this._executeCmd('executeSearchNavigatePre');
    }

    onReplaceOnce() {
        if (!this.state.findText) return;
        try {
            this.editor?.command?.executeSearch?.(this.state.findText);
            this.editor?.command?.executeReplace?.(this.state.replaceText || '');
        } catch (e) {
            console.error('[DocEditor] replace once failed', e);
            this.notification?.add?.(`取代失敗：${e.message || e}`, { type: 'warning' });
        }
    }

    // executeReplace 只取代當前一個 match，要 replaceAll 須 loop。
    // 用 flatten text indexOf 判斷停止條件 + SAFE_GUARD 避免無限 loop（同 Sprint W 模式）。
    onReplaceAll() {
        if (!this.state.findText) return;
        const SAFE_GUARD = 500;
        let count = 0;
        try {
            for (let i = 0; i < SAFE_GUARD; i++) {
                const data = this.editor?.command?.getValue?.()?.data;
                if (!data) break;
                const flat = flattenElementsToText(data.main || []);
                if (flat.indexOf(this.state.findText) < 0) break;
                this.editor.command.executeSearch(this.state.findText);
                this.editor.command.executeReplace(this.state.replaceText || '');
                count++;
            }
            this.notification?.add?.(`已取代 ${count} 個項目`, { type: 'info' });
            try { this.editor?.command?.executeSearch?.(null); } catch (e) { /* ignore */ }
        } catch (e) {
            console.error('[DocEditor] replace all failed', e);
            this.notification?.add?.(`取代失敗：${e.message || e}`, { type: 'warning' });
        }
    }

    // ─── Sprint Y5：格式化工具列 handlers ─────────────────────────
    // 字型 / 字號 select 變動時直接接 canvas-editor cmd；按鈕（B/I/U/align/clear）
    // 在 XML 用 inline t-on-click="() => this._executeCmd(...)" 不用獨立 method。

    onFontFamilyChange(ev) {
        const v = ev.target.value;
        if (!v) return;
        this._executeCmd('executeFont', v);
    }

    onFontSizeChange(ev) {
        const s = parseInt(ev.target.value, 10);
        if (!s || s <= 0) return;
        this._executeCmd('executeSize', s);
    }

    // ─── Sprint Y6：字色 / 背景色 ───
    onTextColorChange(ev) {
        const c = ev.target.value;
        if (!c) return;
        this.state.textColor = c;       // 同步 UI swatch
        this._executeCmd('executeColor', c);
    }

    onHighlightColorChange(ev) {
        const c = ev.target.value;
        if (!c) return;
        this.state.highlightColor = c;
        this._executeCmd('executeHighlight', c);
    }

    onFindInputKeyDown(ev) {
        if (ev.key === 'Enter') {
            ev.preventDefault();
            if (ev.shiftKey) this.onFindPrev();
            else this.onFindNext();
        } else if (ev.key === 'Escape') {
            ev.preventDefault();
            this.closeFindReplace();
        }
    }

    // 6 個 menu × N item 的設定表；XML 用 t-foreach 渲染
    get menuConfig() {
        return [
            {
                name: 'file', label: '檔案',
                items: [
                    { label: '新增空白文件', disabled: true },
                    { label: '開啟最近文件...', disabled: true },
                    { label: '重新命名', action: 'file:rename' },
                    { type: 'separator' },
                    { label: '匯入 DOCX...', action: 'file:import' },
                    { label: '匯出為 PDF', action: 'file:export-pdf' },
                    { label: '匯出為 DOCX', action: 'file:export-docx' },
                    { type: 'separator' },
                    { label: '列印', action: 'file:print' },
                    { label: '預覽', action: 'file:preview' },
                    { label: '儲存', action: 'file:save', shortcut: 'Ctrl+S' },
                    { label: '關閉', action: 'file:close' },
                ],
            },
            {
                name: 'edit', label: '編輯',
                items: [
                    { label: '復原', action: 'edit:undo', shortcut: 'Ctrl+Z' },
                    { label: '重做', action: 'edit:redo', shortcut: 'Ctrl+Y' },
                    { type: 'separator' },
                    { label: '剪下', action: 'edit:cut', shortcut: 'Ctrl+X' },
                    { label: '複製', action: 'edit:copy', shortcut: 'Ctrl+C' },
                    { label: '貼上', action: 'edit:paste', shortcut: 'Ctrl+V' },
                    { type: 'separator' },
                    { label: '尋找', action: 'edit:find', shortcut: 'Ctrl+F' },
                    { label: '取代', action: 'edit:replace', shortcut: 'Ctrl+H' },
                ],
            },
            {
                name: 'view', label: '查看',
                items: [
                    { label: this.state.showRuler ? '✓ 顯示尺規' : '   顯示尺規', action: 'view:toggle-ruler' },
                    { label: this.state.showThumbnails ? '✓ 顯示縮圖' : '   顯示縮圖', action: 'view:toggle-thumbnails' },
                    { type: 'separator' },
                    { label: '縮放 50%', action: 'view:zoom-50' },
                    { label: '縮放 100%', action: 'view:zoom-100' },
                    { label: '縮放 150%', action: 'view:zoom-150' },
                    { label: '縮放 200%', action: 'view:zoom-200' },
                    { label: '符合寬度', action: 'view:zoom-fit' },
                    { type: 'separator' },
                    { label: '全螢幕', action: 'view:fullscreen', shortcut: 'F11' },
                ],
            },
            {
                name: 'insert', label: '插入',
                items: [
                    { label: '表格（3×3）', action: 'insert:table' },
                    { label: '圖片...', action: 'insert:image' },
                    { type: 'separator' },
                    { label: '變數欄位（文字）', action: 'insert:var-text' },
                    { label: '變數欄位（日期）', action: 'insert:var-date' },
                    { label: '變數欄位（核取方塊）', action: 'insert:var-checkbox' },
                    { type: 'separator' },
                    { label: '簽名欄位', disabled: true },
                    { label: '頁碼', disabled: true },
                    { label: '頁首／頁尾', disabled: true },
                ],
            },
            {
                name: 'format', label: '格式',
                items: [
                    { label: '粗體', action: 'format:bold', shortcut: 'Ctrl+B' },
                    { label: '斜體', action: 'format:italic', shortcut: 'Ctrl+I' },
                    { label: '底線', action: 'format:underline', shortcut: 'Ctrl+U' },
                    { label: '刪除線', action: 'format:strikeout' },
                    { type: 'separator' },
                    { label: '靠左對齊', action: 'format:align-left' },
                    { label: '置中對齊', action: 'format:align-center' },
                    { label: '靠右對齊', action: 'format:align-right' },
                    { label: '兩端對齊', action: 'format:align-justify' },
                    { type: 'separator' },
                    { label: '段落間距', disabled: true },
                    { label: '行距', disabled: true },
                    { label: '清除格式', action: 'format:clear-format' },
                ],
            },
            {
                name: 'tools', label: '工具',
                items: [
                    { label: '掃描變數', action: 'tools:scan-vars' },
                    { label: '掃描並替換變數', action: 'tools:scan-replace' },
                    { label: '預覽變數效果', action: 'tools:preview-vars' },
                    { label: '復原變數替換', action: 'tools:rollback' },
                    { type: 'separator' },
                    { label: '字數統計', action: 'tools:word-count' },
                    { label: '拼字檢查', disabled: true },
                    { type: 'separator' },
                    { label: '版本歷史', action: 'tools:version-history', shortcut: 'Alt+H' },
                    { label: '文件設定', disabled: true },
                ],
            },
        ];
    }
}

registry.category("actions").add("dobtor_doc_editor.action_doc_editor", DocEditor);
