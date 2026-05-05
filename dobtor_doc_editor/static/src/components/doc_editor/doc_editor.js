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

export class DocEditor extends Component {
    static template = "dobtor_doc_editor.DocEditor";
    static components = {};
    static props = ["*"];

    setup() {
        this.notification = useService("notification");
        this.action = useService("action");

        // 嘗試取得 bus_service（多人協作用，可能不存在）
        try {
            this._busService = useService("bus_service");
        } catch (e) {
            this._busService = null;
        }

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
        });

        // 暫存從後端載入的 content_json，供 _initCanvasEditor 使用
        this._loadedContentJson = null;
        // Canvas 編輯器實例
        this.editor = null;
        this._leaderElection = null;

        // 取得 doc_id（優先 action context，F5 後從 sessionStorage 恢復）
        const context = this.props.action?.context || {};
        const _SESSION_KEY = "dobtor_doc_editor_last_id";
        const docId = context.doc_id || (() => {
            const stored = sessionStorage.getItem(_SESSION_KEY);
            return stored ? parseInt(stored, 10) : null;
        })();

        // ── AutoSaveManager（以 content_json 為儲存單位）──
        this._autoSave = new AutoSaveManager({
            saveFn: async (json) => {
                if (!this.state.docId) return;
                await rpc("/dobtor_doc/save", {
                    doc_id: this.state.docId,
                    content_json: json,
                });
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
            await this._autoSave.flush();
            this._autoSave.destroy();
            this._offlineManager.destroy();
            if (this._leaderElection) this._leaderElection.destroy();
            // 銷毀 Canvas 編輯器實例（若引擎有提供 destroy）
            this.editor?.destroy?.();
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

        // 取得 PageMode 列舉（PAGING = 分頁置中模式，類 Google Docs）
        const CE = window["canvas-editor"];
        const PageMode = CE?.PageMode;

        // 建立 Canvas 編輯器實例
        this.editor = new EditorConstructor(container, initialData, {
            pageMode: PageMode?.PAGING,
        });

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
        };
    }

    // ─── 資料載入 ────────────────────────────────────────────────────

    async _loadDocument(docId) {
        try {
            const data = await rpc("/dobtor_doc/load", { doc_id: docId });
            this.state.docId = data.id;
            this.state.docName = data.name;
            // F5 恢復用
            sessionStorage.setItem("dobtor_doc_editor_last_id", data.id);
            this.state.pageFormat = data.page_format || "A4";

            // 暫存 content_json，供 _initCanvasEditor 使用
            this._loadedContentJson = data.content_json || null;

            // 模板引擎狀態恢復
            if (data.has_template) {
                this.state.isTemplateMode = true;
                this.state.templateVariables = data.template_variables || [];
                this.state.templateFilename = data.template_filename || "";
            }

            this.state.editorReady = true;
            this.state.statusMsg = "已載入";
            this.state.statusType = "saved";
        } catch (error) {
            this.state.statusMsg = `載入失敗：${error.message || error}`;
            this.state.statusType = "error";
            this.state.editorReady = true; // 避免永遠顯示載入中
            console.error("[DocEditor] Load failed:", error);
        }
    }

    // ─── 離線同步 ────────────────────────────────────────────────────

    async _syncOfflineBuffer() {
        const ops = this._offlineManager.drainBuffer();
        if (!ops.length || !this.state.docId) return;
        const lastSave = [...ops].reverse().find(op => op.type === "save");
        if (!lastSave) return;
        try {
            await rpc("/dobtor_doc/save", {
                doc_id: this.state.docId,
                content_json: lastSave.json,
            });
            this.state.statusMsg = "已同步";
            this.state.statusType = "saved";
        } catch (e) {
            this.notification.add(`同步失敗：${e.message}`, { type: "danger" });
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
        try {
            const json = JSON.stringify(this.editor.command.getValue().data);
            await rpc("/dobtor_doc/save", {
                doc_id: this.state.docId,
                content_json: json,
            });
            this.state.statusMsg = "已儲存";
            this.state.statusType = "saved";
        } catch (error) {
            this.state.statusMsg = `儲存失敗：${error.message || error}`;
            this.state.statusType = "error";
            this.notification.add("文件儲存失敗", { type: "danger" });
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
