/**
 * 前台「意見回饋」新增表單：
 * 只有勾了「詢問發生功能」的類別（操作疑問、系統問題）才顯示「在哪個功能遇到問題？」。
 * 切到其他類別時清掉已選的值，避免帳務類的單帶著一個不相干的功能送出去。
 */
(function () {
    "use strict";

    function setup() {
        var category = document.getElementById("cy_fb_category");
        var wrap = document.getElementById("cy_fb_module_wrap");
        var module = document.getElementById("cy_fb_module");
        if (!category || !wrap || !module) {
            return;
        }
        function refresh() {
            var opt = category.options[category.selectedIndex];
            var ask = opt && opt.getAttribute("data-ask-module") === "1";
            wrap.style.display = ask ? "" : "none";
            if (!ask) {
                module.value = "";
            }
        }
        category.addEventListener("change", refresh);
        refresh();
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", setup);
    } else {
        setup();
    }
})();
