/** @odoo-module **/

/**
 * Telemetry — 前端錯誤回報 + 效能指標收集（P2-4）
 *
 * 設計：
 *   - reportError(type, payload)：呼叫 /dobtor_doc/telemetry/error
 *   - reportMetric(type, value, extra)：呼叫 /dobtor_doc/telemetry/metric
 *   - install(component)：自動掛 window.onerror / unhandledrejection / WebVitals
 *   - uninstall()：unmount 時呼叫，清掉 listener
 *
 * 失敗策略：
 *   - 所有 RPC 失敗都靜默吞掉，遙測絕不擾斷使用者體驗
 *   - 上報前去重 + rate limit（避免短時間重複錯誤洗爆 DB）
 */

import { rpc } from "@web/core/network/rpc";

const ERROR_RATE_LIMIT_MS = 5000; // 同樣訊息 5 秒內只送一次
const _recentErrors = new Map(); // key=signature → ts

function _sigOf(type, message) {
    return `${type}::${(message || "").slice(0, 120)}`;
}

function _shouldThrottle(sig) {
    const now = Date.now();
    const last = _recentErrors.get(sig);
    if (last && now - last < ERROR_RATE_LIMIT_MS) {
        return true;
    }
    _recentErrors.set(sig, now);
    // GC：保持 map < 100
    if (_recentErrors.size > 100) {
        const oldestKey = _recentErrors.keys().next().value;
        _recentErrors.delete(oldestKey);
    }
    return false;
}

export async function reportError({
    type = "other",
    message = "",
    stackTrace = "",
    docId = null,
    extra = null,
} = {}) {
    if (_shouldThrottle(_sigOf(type, message))) return;
    try {
        await rpc("/dobtor_doc/telemetry/error", {
            error_type: type,
            message: String(message || "").slice(0, 500),
            stack_trace: String(stackTrace || "").slice(0, 8000),
            user_agent: (typeof navigator !== "undefined" && navigator.userAgent) || "",
            url: (typeof location !== "undefined" && location.href) || "",
            doc_id: docId,
            extra: extra || {},
        });
    } catch {
        // 遙測失敗 → 靜默
    }
}

export async function reportMetric(metricType, value, { docId = null, pageCount = null, extra = null } = {}) {
    if (typeof value !== "number" || !Number.isFinite(value)) return;
    try {
        await rpc("/dobtor_doc/telemetry/metric", {
            metric_type: metricType,
            value: value,
            doc_id: docId,
            page_count: pageCount,
            extra: extra || {},
        });
    } catch {
        // 遙測失敗 → 靜默
    }
}

/**
 * 計時器：用法
 *   const stop = mark("load_doc_ms");
 *   ... do work ...
 *   stop({ docId, pageCount });    // 自動上報耗時
 */
export function mark(metricType) {
    const t0 = (typeof performance !== "undefined" && performance.now) ? performance.now() : Date.now();
    return (opts = {}) => {
        const t1 = (typeof performance !== "undefined" && performance.now) ? performance.now() : Date.now();
        reportMetric(metricType, t1 - t0, opts);
    };
}

/**
 * Install：在 doc_editor.js setup 時呼叫，自動掛全域 listener。
 *
 * 回傳一個 cleanup function，給 onWillUnmount 用。
 */
export function installGlobalErrorReporting({ docIdGetter = () => null } = {}) {
    const onError = (event) => {
        const docId = docIdGetter();
        reportError({
            type: "js_error",
            message: event?.message || String(event),
            stackTrace: event?.error?.stack || "",
            docId,
            extra: {
                filename: event?.filename,
                lineno: event?.lineno,
                colno: event?.colno,
            },
        });
    };
    const onRejection = (event) => {
        const docId = docIdGetter();
        const reason = event?.reason;
        reportError({
            type: "promise_rejection",
            message: (reason && reason.message) || String(reason || "unknown"),
            stackTrace: (reason && reason.stack) || "",
            docId,
        });
    };

    if (typeof window !== "undefined") {
        window.addEventListener("error", onError);
        window.addEventListener("unhandledrejection", onRejection);
    }

    // Web Vitals 觀測（LCP / FID / CLS）— 用 PerformanceObserver
    let lcpObserver, clsObserver, fidObserver;
    let cumulativeCLS = 0;
    if (typeof PerformanceObserver !== "undefined") {
        try {
            lcpObserver = new PerformanceObserver((list) => {
                const entries = list.getEntries();
                const last = entries[entries.length - 1];
                if (last) {
                    reportMetric("web_vitals_lcp_ms", last.renderTime || last.loadTime || last.startTime, {
                        docId: docIdGetter(),
                    });
                }
            });
            lcpObserver.observe({ type: "largest-contentful-paint", buffered: true });
        } catch {
            lcpObserver = null;
        }
        try {
            clsObserver = new PerformanceObserver((list) => {
                for (const entry of list.getEntries()) {
                    if (!entry.hadRecentInput) {
                        cumulativeCLS += entry.value;
                    }
                }
            });
            clsObserver.observe({ type: "layout-shift", buffered: true });
        } catch {
            clsObserver = null;
        }
        try {
            fidObserver = new PerformanceObserver((list) => {
                for (const entry of list.getEntries()) {
                    reportMetric("web_vitals_fid_ms", entry.processingStart - entry.startTime, {
                        docId: docIdGetter(),
                    });
                }
            });
            fidObserver.observe({ type: "first-input", buffered: true });
        } catch {
            fidObserver = null;
        }
    }

    return function uninstall() {
        if (typeof window !== "undefined") {
            window.removeEventListener("error", onError);
            window.removeEventListener("unhandledrejection", onRejection);
        }
        // CLS 在 unmount 時上報最終值
        if (cumulativeCLS > 0) {
            reportMetric("web_vitals_cls", cumulativeCLS, { docId: docIdGetter() });
        }
        try { lcpObserver?.disconnect(); } catch (e) { void e; }
        try { clsObserver?.disconnect(); } catch (e) { void e; }
        try { fidObserver?.disconnect(); } catch (e) { void e; }
    };
}
