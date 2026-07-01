/* 千溢科技 QYTech 行銷頁互動邏輯
 * 純 vanilla JS，僅作用於 .qytech-page 範圍內
 * 產品輪播使用 Bootstrap 5 carousel（Odoo 已內建），這裡處理：
 *   1. 導覽列捲動陰影效果
 *   2. 說明中心即時搜尋過濾
 *   3. 登入視窗（自包含 .qy-modal）開關與表單導向 /web/login
 */
(function () {
    "use strict";

    function initNavbarScroll() {
        var navbar = document.querySelector(".qytech-page .qy-navbar");
        if (!navbar) return;
        var onScroll = function () {
            if (window.scrollY > 50) {
                navbar.classList.add("qy-scrolled");
            } else {
                navbar.classList.remove("qy-scrolled");
            }
        };
        window.addEventListener("scroll", onScroll, { passive: true });
        onScroll();
    }

    function initHelpSearch() {
        var input = document.querySelector(".qytech-page #qySearchInput");
        if (!input) return;
        var list = document.querySelector(".qytech-page #qyHelpList");
        var noResults = document.querySelector(".qytech-page #qyNoResults");
        if (!list) return;

        input.addEventListener("keyup", function () {
            var filter = input.value.toUpperCase();
            var items = list.getElementsByClassName("qy-help-item");
            var hasResult = false;

            for (var i = 0; i < items.length; i++) {
                // 比對標題 + 內文 + 隱藏關鍵字（.qy-tags）
                var text = items[i].textContent || items[i].innerText || "";
                if (text.toUpperCase().indexOf(filter) > -1) {
                    items[i].classList.remove("qy-hidden");
                    hasResult = true;
                } else {
                    items[i].classList.add("qy-hidden");
                }
            }
            if (noResults) {
                noResults.classList.toggle("d-none", hasResult);
            }
        });
    }

    function initCarousel() {
        var car = document.querySelector(".qytech-page #qyCarousel");
        if (!car) return;
        var track = car.querySelector("[data-qy-track]");
        if (!track) return;
        var total = track.children.length;
        var dots = Array.prototype.slice.call(document.querySelectorAll(".qytech-page [data-qy-dot]"));
        var cur = 0;

        function update() {
            track.style.transform = "translateX(-" + (cur * 100) + "%)";
            dots.forEach(function (d, i) { d.classList.toggle("active", i === cur); });
        }
        function go(i) { cur = (i + total) % total; update(); }

        document.querySelectorAll(".qytech-page [data-qy-next]").forEach(function (b) {
            b.addEventListener("click", function () { go(cur + 1); });
        });
        document.querySelectorAll(".qytech-page [data-qy-prev]").forEach(function (b) {
            b.addEventListener("click", function () { go(cur - 1); });
        });
        dots.forEach(function (d, i) { d.addEventListener("click", function () { go(i); }); });
        update();
    }

    function initLoginModal() {
        var modal = document.getElementById("qyLoginModal");
        if (!modal) return;

        function openModal(e) {
            if (e) e.preventDefault();
            modal.classList.add("qy-open");
            modal.setAttribute("aria-hidden", "false");
            document.body.style.overflow = "hidden";
        }
        function closeModal() {
            modal.classList.remove("qy-open");
            modal.setAttribute("aria-hidden", "true");
            document.body.style.overflow = "";
        }

        // 開啟：所有帶 data-qy-login 的入口（無 JS 時 href=/web/login 仍可用）
        document.querySelectorAll("[data-qy-login]").forEach(function (el) {
            el.addEventListener("click", openModal);
        });
        // 關閉：背景遮罩、關閉鈕
        modal.querySelectorAll("[data-qy-close]").forEach(function (el) {
            el.addEventListener("click", closeModal);
        });
        // Esc 關閉
        document.addEventListener("keydown", function (e) {
            if (e.key === "Escape" && modal.classList.contains("qy-open")) closeModal();
        });
        // 快速登入表單 → 導向真實 /web/login（帶入 email 預填）
        var form = modal.querySelector("[data-qy-login-form]");
        if (form) {
            form.addEventListener("submit", function (e) {
                e.preventDefault();
                var email = (form.querySelector('input[name="login"]') || {}).value || "";
                var url = "/web/login";
                if (email) url += "?login=" + encodeURIComponent(email);
                window.location.href = url;
            });
        }
    }

    function initManualLink() {
        // 把 Odoo 頁首（.qytech-page 之外、無法直接編輯）中文字為「說明書」的按鈕／連結，
        // 自動導向本頁「使用說明（說明中心）」區塊 #help-center。
        // 同頁有該區塊 → 平滑捲動；不同頁 → 連到 /qytech#help-center。
        var hasHelp = !!document.getElementById("help-center");
        var target = hasHelp ? "#help-center" : "/qytech#help-center";
        var anchors = document.querySelectorAll("a, button");
        anchors.forEach(function (el) {
            if (el.closest(".qytech-page")) return;          // 跳過我自己的導覽列
            var txt = (el.textContent || "").trim();
            if (txt.indexOf("說明書") === -1) return;        // 只認「說明書」
            if (el.tagName === "A") el.setAttribute("href", target);
            el.addEventListener("click", function (e) {
                var sec = document.getElementById("help-center");
                if (sec) { e.preventDefault(); sec.scrollIntoView({ behavior: "smooth" }); }
                else { window.location.href = "/qytech#help-center"; }
            });
        });
    }

    function init() {
        if (!document.querySelector(".qytech-page")) return;
        initNavbarScroll();
        initHelpSearch();
        initCarousel();
        initLoginModal();
        initManualLink();
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
