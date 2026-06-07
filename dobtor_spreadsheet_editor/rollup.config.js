// rollup.config.js — dobtor_spreadsheet_editor Frontend Build
//
// 輸入：static/src/core/ooxmlspreadsheet/index.ts（OOXML SpreadsheetML Parser 入口）
// 輸出：static/src/lib/dobtor_spreadsheet_editor.umd.js
//
// 打包策略：
//   將 OOXML SpreadsheetML Parser + Style/Formula/Render 轉換層打包成單一 UMD bundle。
//   Odoo asset 系統直接引用此 bundle，不需要 npm 工具鏈於部署環境。
//   o-spreadsheet 不打進 bundle（由 Odoo 原生 spreadsheet 模組提供），
//   而是透過 plugin / commands API 在 runtime 對接。
//
// 注意：Phase 1 開始前 static/src/core/ooxmlspreadsheet/ 仍為空殼，
//   build 會輸出空 bundle——這是預期行為。Phase 1 建立 Parser 後 bundle 才會有實體內容。

import typescript from '@rollup/plugin-typescript';
import resolve from '@rollup/plugin-node-resolve';
import commonjs from '@rollup/plugin-commonjs';

export default {
  input: 'static/src/core/ooxmlspreadsheet/index.ts',

  output: {
    file: 'static/src/lib/dobtor_spreadsheet_editor.umd.js',
    format: 'umd',
    name: 'DobtorSpreadsheetEditor',
    sourcemap: true,
  },

  // o-spreadsheet 為 Odoo 原生提供、不打包進 bundle
  // 透過 window['@odoo/o-spreadsheet'] / Odoo module loader 在 runtime 取得
  external: ['@odoo/o-spreadsheet'],

  plugins: [
    resolve({ browser: true }),
    commonjs(),
    typescript({ tsconfig: './tsconfig.json' }),
  ],
};
