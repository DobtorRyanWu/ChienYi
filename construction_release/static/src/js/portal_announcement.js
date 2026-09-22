/** 前台更新公告跳窗：自動開一次；按「知道了」才寫入已讀（與後台共用同一份名單）。
 *
 * ⚠️ 這個環境的前台**沒有 Bootstrap 的 JavaScript**（construction_portal 的抽屜也是自己用
 *    原生 JS 接管的），所以 modal 的開關要自己做，不能用 bootstrap.Modal。
 * ⚠️ 前台的 JS 是延後載入的，掛 DOMContentLoaded 時事件常常已經過了 → 要先判 readyState。
 */
(function () {
    "use strict";

    function syncBannerHeight() {
        // 照片中心的地圖頁有 position: fixed 的工具列會蓋住橫幅 →
        // 量出橫幅高度寫進 CSS 變數，由 portal_announcement.css 把那些元件往下推
        var banner = document.querySelector(".cy-maint-banner");
        if (!banner) {
            document.body.classList.remove("cy-has-maint");
            return;
        }
        document.body.classList.add("cy-has-maint");
        document.body.style.setProperty("--cy-maint-h", banner.offsetHeight + "px");
    }

    function showModal(el) {
        el.classList.add("show");
        el.style.display = "block";
        el.removeAttribute("aria-hidden");
        document.body.classList.add("modal-open");
        var backdrop = document.createElement("div");
        backdrop.className = "modal-backdrop fade show";
        backdrop.id = "cyReleaseAnnouncementBackdrop";
        document.body.appendChild(backdrop);
    }

    function hideModal(el) {
        el.classList.remove("show");
        el.style.display = "none";
        el.setAttribute("aria-hidden", "true");
        document.body.classList.remove("modal-open");
        var backdrop = document.getElementById("cyReleaseAnnouncementBackdrop");
        if (backdrop) {
            backdrop.remove();
        }
    }

    function init() {
        syncBannerHeight();
        window.addEventListener("resize", syncBannerHeight);

        var el = document.getElementById("cyReleaseAnnouncement");
        if (!el) {
            return;
        }
        var ids = (el.getAttribute("data-cy-release-ids") || "")
            .split(",")
            .filter(function (s) { return s; })
            .map(function (s) { return parseInt(s, 10); });
        showModal(el);

        var btn = document.getElementById("cyReleaseAnnouncementAck");
        if (!btn) {
            return;
        }
        btn.addEventListener("click", function () {
            btn.disabled = true;
            fetch("/construction/announcements/read", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    jsonrpc: "2.0",
                    method: "call",
                    params: { release_ids: ids },
                }),
            })
                .catch(function () { /* 寫不進去就下次再跳，不要卡住使用者 */ })
                .then(function () { hideModal(el); });
        });
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
