// render_png.ts — HTML → PNG（puppeteer 光柵化，VR pipeline 用）
//
// 僅 Node 端使用（測試/CLI）；不從 index.ts 匯出、不進 frontend rollup bundle。

import puppeteer, { type Browser } from 'puppeteer';

export interface RenderPngOptions {
    width?: number;
    height?: number;
    deviceScaleFactor?: number;
}

/** 啟動一個 headless 瀏覽器（sandbox 關閉以相容 CI/WSL）。*/
export async function launchBrowser(): Promise<Browser> {
    return puppeteer.launch({
        headless: true,
        args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage'],
    });
}

/** 用已開啟的 browser 把 HTML 渲染成 PNG buffer（截 table 元素）。*/
export async function renderHtmlToPng(
    browser: Browser,
    html: string,
    opts: RenderPngOptions = {},
): Promise<Buffer> {
    const page = await browser.newPage();
    try {
        await page.setViewport({
            width: opts.width ?? 1200,
            height: opts.height ?? 800,
            deviceScaleFactor: opts.deviceScaleFactor ?? 1,
        });
        await page.setContent(html, { waitUntil: 'load' });
        const table = await page.$('table');
        const target = table ?? page;
        const buf = (await target.screenshot({ type: 'png' })) as Buffer;
        return buf;
    } finally {
        await page.close();
    }
}
