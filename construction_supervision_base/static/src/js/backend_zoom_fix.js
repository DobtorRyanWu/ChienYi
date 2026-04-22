/**
 * 修正 CSS zoom: 1.25 造成 Odoo 下拉選單/Tooltip 定位偏移的問題。
 *
 * 根因：getBoundingClientRect() 回傳視口座標（已乘 zoom），
 * 但 Odoo 將此值直接用於 style.left/top（CSS 座標），導致位置再乘一次。
 * 解法：patch getBoundingClientRect，將回傳值除以 zoom factor。
 */
(function () {
    const ZOOM = 1.25;
    const _getBCR = Element.prototype.getBoundingClientRect;

    Element.prototype.getBoundingClientRect = function () {
        const r = _getBCR.call(this);
        return DOMRect.fromRect({
            x: r.x / ZOOM,
            y: r.y / ZOOM,
            width: r.width / ZOOM,
            height: r.height / ZOOM,
        });
    };
})();
