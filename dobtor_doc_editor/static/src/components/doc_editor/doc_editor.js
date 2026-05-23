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

/**
 * Phase 8 Template UI Builder（ADR-022）— Phase 1 視覺風格靠攏。
 *
 * 範本欄位類型清單（Phase 2 接 canvas-editor executeInsertControl 用）。
 * Phase 1 只渲染按鈕、點擊只彈 toast，欄位插入行為留到 Phase 2。
 */
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
        });
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
        };
        if (typeof window !== 'undefined') {
            window.addEventListener('keydown', this._onGlobalKey);
        }

        // 取得 doc_id 優先順序：
        //   1. this.props.docId — portal mount 模式（<owl-component props='{"docId":...}'>）
        //   2. backend client action context.doc_id
        //   3. sessionStorage F5 恢復（backend 內按 F5 刷新時用）
        const context = this.props.action?.context || {};
        const _SESSION_KEY = "dobtor_doc_editor_last_id";
        const docId = this.props.docId || context.doc_id || (() => {
            const stored = sessionStorage.getItem(_SESSION_KEY);
            return stored ? parseInt(stored, 10) : null;
        })();

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
                const conceptId = el?.control?.conceptId;
                if (!conceptId) return;
                const fieldId = parseInt(conceptId, 10);
                if (Number.isFinite(fieldId) && this.state.selectedFieldId !== fieldId) {
                    this.state.selectedFieldId = fieldId;
                }
            } catch (e) {
                // 不要讓 listener 抛例外破壞 canvas-editor 內部流程
            }
        };
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

            const fieldPayload = {
                signer_id: signer.id,
                field_type: field.key,
                page_no: this.state.pageNo || 1,
                required: false,
                placeholder_text: field.label,
                font_size: 12,
            };
            const saveResult = await rpc("/dobtor_doc/template_fields/save_field", {
                doc_id: this.state.docId,
                field: fieldPayload,
            });
            if (!saveResult.success) {
                this.notification.add(`新增欄位失敗：${saveResult.error}`, { type: "danger" });
                return;
            }
            // 後端寫入成功 → 在 canvas-editor 插入 inline control
            this._insertControlForField(saveResult.id, field, signer);

            // 把新建的 field 紀錄 push 進本地 cache，供 Inspector 立即顯示
            if (!this._templateFieldsCache) this._templateFieldsCache = [];
            this._templateFieldsCache.push({
                id: saveResult.id,
                ...fieldPayload,
                odoo_field_name: "",
                width: 120,
                height: 24,
                pos_x: 0,
                pos_y: 0,
            });

            // 同步 state 計數
            this._applySignerCounts(saveResult.signer_field_counts);
            this.state.fieldCount = saveResult.field_count;
            this.state.selectedFieldId = saveResult.id;
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
     */
    _insertControlForField(fieldId, field, signer) {
        const conceptId = String(fieldId);
        const placeholder = `[${signer.name}/${field.label}]`;
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
     * 開啟 Odoo 欄位選擇器 Dialog（DocFieldPickerDialog 復活 from Sprint 89）。
     * 選中欄位後在游標位置插入 `{{ object.field_name }}` 表達式——這是既有 docxtpl
     * 範本流程的延伸（不是新建 doc.template.field），與 isTemplateMode 共用。
     */
    onOdooFieldClick() {
        if (!this.dialog) {
            this.notification.add("Dialog service 未就緒", { type: "warning" });
            return;
        }
        if (!this.editor) {
            this.notification.add("編輯器尚未初始化", { type: "warning" });
            return;
        }
        // 取得當前文件綁定的 model_name（_loadDocument 已寫入 state）。
        // Phase 1 為了讓按鈕始終可點，沒有 modelName 也讓 dialog 開啟並提示。
        const modelName = this._loadedModelName || null;
        this.dialog.add(DocFieldPickerDialog, {
            modelName: modelName,
            docId: this.state.docId,
            onInsert: (expression /* , label */) => {
                // 用 canvas-editor 在游標處插入文字（最簡作法）。
                // canvas-editor 沒有純粹的 "insert text" 命令，用 executeInsertElementList 包裝。
                try {
                    const elements = expression.split("").map(ch => ({ value: ch }));
                    this.editor.command.executeInsertElementList(elements);
                } catch (e) {
                    console.error("[DocEditor] 插入 Odoo 欄位失敗：", e);
                    this.notification.add(`插入失敗：${e.message || e}`, { type: "danger" });
                }
            },
        });
    }

    onSignerClick(signerId) {
        this.state.activeSignerId = signerId;
    }

    onZoomFitChange(event) {
        const mode = event.target.value;
        this.state.zoomFit = mode;
        // canvas-editor 有 executePageScale(number) 但沒有真正的 fit-to-width 概念。
        // Phase 1 把「自動縮放」對應到 1.0、其餘已在 toolbar zoom 處理。
        if (this.editor && mode === "auto") {
            try {
                this.editor.command.executePageScale(1);
            } catch (e) {
                // 忽略
            }
        }
    }

    onPrevPage() {
        if (this.state.pageNo > 1) this.state.pageNo -= 1;
        // Phase 2：editor.command.executePageNo(this.state.pageNo)（若 API 存在）
    }

    onNextPage() {
        if (this.state.pageNo < this.state.totalPages) this.state.pageNo += 1;
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
     */
    onInspectorFieldChange(key, value) {
        const field = this.selectedField;
        if (!field) return;
        // 本地立即更新（樂觀 UI），保證輸入流暢
        if (key === "required") {
            field[key] = !!value;
        } else if (key === "font_size" || key === "signer_id") {
            field[key] = parseInt(value, 10) || field[key];
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
}

registry.category("actions").add("dobtor_doc_editor.action_doc_editor", DocEditor);
