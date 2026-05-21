# dobtor_doc_editor — Sprint Audit 索引（INDEX.md）

**抽出自** [規畫書 §12](../dobtor_doc_editor_高保真匯入開發規劃.md) **+ [autonomous_roadmap.md](autonomous_roadmap.md) 進度表（已 archive）/ Sprint 155 catch-up（2026-05-19）**

158 個 sprint audit doc 完整索引(Sprint 1-158)。每個 sprint 的 root cause / 修法 / 三層 SOP / 設計取捨完整記錄在各自獨立 audit doc。

---

## 主題分群

### Phase 1-3 主體（Sprint 2-33）

[sprint2_layout_engine](sprint2_layout_engine.md)、[sprint3_table_layout](sprint3_table_layout.md)、[sprint4_section_float_widow](sprint4_section_float_widow.md)、[sprint5_nested_multicol](sprint5_nested_multicol.md)、[sprint6_wrapsquare_unequal_cols](sprint6_wrapsquare_unequal_cols.md)、[sprint7_midrow_colbreak_nested_style](sprint7_midrow_colbreak_nested_style.md)、[sprint8_renderer_fontmetrics](sprint8_renderer_fontmetrics.md)、[sprint9_browser_canvas_blocks_decoration](sprint9_browser_canvas_blocks_decoration.md)、[sprint10_column_separator_page_field](sprint10_column_separator_page_field.md)、[sprint11_header_footer_render](sprint11_header_footer_render.md)、[sprint12_field_metadata_ops_fingerprint](sprint12_field_metadata_ops_fingerprint.md)、[sprint13_docprops_knuth_plass](sprint13_docprops_knuth_plass.md)、[sprint14_visual_regression](sprint14_visual_regression.md)、[sprint15_image_render](sprint15_image_render.md)、[sprint16_pagination_baseline](sprint16_pagination_baseline.md)、[sprint17_pagination_break](sprint17_pagination_break.md)、[sprint18_pagination_transition](sprint18_pagination_transition.md)、[sprint19_style_merge_visual_rerun](sprint19_style_merge_visual_rerun.md)、[sprint20_cicd_landing](sprint20_cicd_landing.md)、[sprint21_chienyi_mixin_landing](sprint21_chienyi_mixin_landing.md)、[sprint22_chienyi_mixin_round2](sprint22_chienyi_mixin_round2.md)、[sprint23_playwright_admin_e2e](sprint23_playwright_admin_e2e.md)、[sprint24_meeting_record_host](sprint24_meeting_record_host.md)、[sprint25_spacing_line_consume](sprint25_spacing_line_consume.md)、[sprint26_row_height_heuristic](sprint26_row_height_heuristic.md)、[sprint27_cell_keepnext_infra](sprint27_cell_keepnext_infra.md)、[sprint28_cjk_width_empirical](sprint28_cjk_width_empirical.md)、[sprint29_docgrid_snap](sprint29_docgrid_snap.md)、[sprint30_dpi_alignment](sprint30_dpi_alignment.md)、[sprint31_r1_overflow_gating](sprint31_r1_overflow_gating.md)、[sprint32_paragraph_alignment](sprint32_paragraph_alignment.md)、[sprint33_vmerge_anchor_render](sprint33_vmerge_anchor_render.md)

### Phase 3 收斂主軸（Sprint 34-49）

[sprint34_vertical_text](sprint34_vertical_text.md)、[sprint35_cjk_vertical_render](sprint35_cjk_vertical_render.md)、[sprint36_grid_analysis_root_cause](sprint36_grid_analysis_root_cause.md)、[sprint37_anchor_position](sprint37_anchor_position.md)、[sprint38_anchor_textbox](sprint38_anchor_textbox.md)、[sprint39_textbox_fine_tune](sprint39_textbox_fine_tune.md)、[sprint40_image_srcrect](sprint40_image_srcrect.md)、[sprint41_grid_diagnosis](sprint41_grid_diagnosis.md)、[sprint42_valign_landing](sprint42_valign_landing.md)、[sprint43_photo_baseline_diagnosis](sprint43_photo_baseline_diagnosis.md)、[sprint44_image_baseline_fix](sprint44_image_baseline_fix.md)、[sprint45_trheight_valasmin_fix](sprint45_trheight_valasmin_fix.md)、[sprint46_meeting_record_diagnosis](sprint46_meeting_record_diagnosis.md)、[sprint47_valasmin_unsnapped_basis](sprint47_valasmin_unsnapped_basis.md)、[sprint48_image_row_valasmin](sprint48_image_row_valasmin.md)、[sprint49_title_docgrid_snap_diagnosis](sprint49_title_docgrid_snap_diagnosis.md)

### Phase 7 效能 + Phase 2 字型（Sprint 50-65）

Sprint 50 perf baseline、Sprint 51-58 cache 五連發 + LayoutCache、Sprint 59 path coalescing、Sprint 60 OffscreenCanvas probe、Sprint 61 BrowserTextMetrics negative、Sprint 62-65 FontMetricsAdapter promote default-on。代表 audit:[sprint65_promote_font_metrics_default_commit](sprint65_promote_font_metrics_default_commit.md)、[sprint68_font_serve_security_boundary](sprint68_font_serve_security_boundary.md)、[sprint67_contributing_md](sprint67_contributing_md.md)

### font_serve + autonomous batch（Sprint 64b-89）

Sprint 64b portal font infra、Sprint 66 font endpoint tests、Sprint 67 CONTRIBUTING.md、Sprint 68 security boundary、Sprint 69 HttpCase runtime + dead code 修正、Sprint 70-89 autonomous batch（廣域應用紀律 / backend test 0→21 / docs glossary）。代表 audit:[sprint82_manifest_data_ordering_audit](sprint82_manifest_data_ordering_audit.md)、[sprint83_disabled_plugins_audit](sprint83_disabled_plugins_audit.md)、[sprint84_to_sprint87_batch](sprint84_to_sprint87_batch.md)、[sprint88_89_autonomous_exhaustion](sprint88_89_autonomous_exhaustion.md)

### Sprint 90-110 revert 事件（紀律 #18 教訓案例）

[sprint90_to_109_revert](sprint90_to_109_revert.md)（esign UI 誤判全 revert、byte-identical）、[sprint111_discipline_sync_after_revert](sprint111_discipline_sync_after_revert.md)（紀律列表同步）、[sprint112_planning_doc_refactor](sprint112_planning_doc_refactor.md)

### Autonomous era 階段 A（Sprint 113-120、autonomous catch-up）

[sprint113_autonomous_roadmap](sprint113_autonomous_roadmap.md)、[sprint114_ci_font_serve_gate](sprint114_ci_font_serve_gate.md)、[sprint115_controller_security_boundary](sprint115_controller_security_boundary.md)、[sprint116_i18n_and_null_byte_fix](sprint116_i18n_and_null_byte_fix.md)、[sprint117_portal_company_rule_closure](sprint117_portal_company_rule_closure.md)、[sprint118_architecture_decision_consolidation](sprint118_architecture_decision_consolidation.md)、[sprint119_glossary_expansion_to_sprint118_era](sprint119_glossary_expansion_to_sprint118_era.md)、[sprint120_sprint50_66_retro_creation](sprint120_sprint50_66_retro_creation.md)

### Autonomous era 階段 B（Sprint 121-135、Phase 1-4 漏項 + probe）

[sprint121_trheight_defensive_parsing](sprint121_trheight_defensive_parsing.md)、[sprint122_ole_pict_fallback](sprint122_ole_pict_fallback.md)、[sprint123_field_code_coverage](sprint123_field_code_coverage.md)、[sprint124_sdt_transparent_unwrap](sprint124_sdt_transparent_unwrap.md)、[sprint125_bookmark_range_coverage](sprint125_bookmark_range_coverage.md)、[sprint126_hyperlink_rels_completeness](sprint126_hyperlink_rels_completeness.md)、[sprint127_fontmetrics_production_probe](sprint127_fontmetrics_production_probe.md)、[sprint128_harfbuzz_wasm_spike](sprint128_harfbuzz_wasm_spike.md)、[sprint130_theme_tint_shade_hsl](sprint130_theme_tint_shade_hsl.md)、[sprint131_tblstylepr_tcpr_propagation](sprint131_tblstylepr_tcpr_propagation.md)、[sprint132_numbering_formatter](sprint132_numbering_formatter.md)、[sprint133_paragraph_border_shading](sprint133_paragraph_border_shading.md)、[sprint134_text_alignment_frame_pr](sprint134_text_alignment_frame_pr.md)、[sprint135_docgrid_snap_probe](sprint135_docgrid_snap_probe.md)

### Phase 4 wire-up 三連 + DEFER cluster（Sprint 136-144）

[sprint136_isintablecell_revert](sprint136_isintablecell_revert.md)、[sprint137_numbering_counter](sprint137_numbering_counter.md)、[sprint138_numbering_mapper_wireup](sprint138_numbering_mapper_wireup.md)、[sprint139_numbering_layout_wireup](sprint139_numbering_layout_wireup.md)、[sprint140_textalign_framepr_probe](sprint140_textalign_framepr_probe.md)、[sprint141_goldens_regen_probe](sprint141_goldens_regen_probe.md)、[sprint142_phase5_scope_probe](sprint142_phase5_scope_probe.md)、[sprint143_discipline_1b_promote](sprint143_discipline_1b_promote.md)、[sprint144_sprint121_142_retro](sprint121_142_retro.md)

### Phase 1 capture-only 九連 cluster（Sprint 145-154、scope audit §3.1 標示為「實質偏離」）

[sprint145_footnotes_capture](sprint145_footnotes_capture.md)、[sprint146_settings_capture](sprint146_settings_capture.md)、[sprint147_fonttable_capture](sprint147_fonttable_capture.md)、[sprint148_websettings_capture](sprint148_websettings_capture.md)、[sprint149_sprint143_148_retro](sprint143_148_retro.md)、[sprint150_appprops_capture](sprint150_appprops_capture.md)、[sprint151_customprops_capture](sprint151_customprops_capture.md)、[sprint152_content_types_capture](sprint152_content_types_capture.md)、[sprint153_latent_styles_capture](sprint153_latent_styles_capture.md)、[sprint154_sprint145_153_retro](sprint145_153_retro.md)

### Sprint 155（glossary catch-up、本 INDEX 抽出 sprint）

[sprint155_glossary_catchup_to_sprint154](sprint155_glossary_catchup_to_sprint154.md)

### Sprint 156-160（snappy-nova plan 啟動 + wire-up 階段 + working tree 大 backfill）

[sprint156_phase1_checkbox_audit](sprint156_phase1_checkbox_audit.md)（Phase 1 §5 內 52 [x] / 17 [ ] checkbox audit、docs-only、揭發真實 wire-up 75%）、[sprint157_fonttable_altname_wireup](sprint157_fonttable_altname_wireup.md)（Phase 2 §2.2 第 1 個 `[x]`、FontLoader altName fallback、+ Sprint 64b backfill 1 file）、[sprint158_working_tree_backfill_audit](sprint158_working_tree_backfill_audit.md)（**Sprint 0-157 整片 working tree drift 揭發 + 5 batch backfill commit、353 件進 git、紀律 #14.b retroactive enforce**）、[sprint160_v2_instrtext_render_wireup](sprint160_v2_instrtext_render_wireup.md)（Phase 1 §1.9 `<w:instrText>` → ToCanvasEditor render 消費 wire-up、`fieldType` placeholder、mapper 不在 VR pipeline、vitest 1340→1342）、[sprint161_defaulttabstop_linebreaker_engine](sprint161_defaulttabstop_linebreaker_engine.md)（`settings.defaultTabStop` → LineBreaker tab stop 解析引擎、`makeLine` 內 resolveTabStops、Strategy C opt-in、VR byte-identical 第 25 連、vitest 1342→1353）、[sprint162_defaulttabstop_production_wireup](sprint162_defaulttabstop_production_wireup.md)（tab stop production 接線 layoutDocument/Paginator/TableLayout + VR pipeline `--tab-stops` opt-in 量測：aggregate delta +4.8e-7 可忽略、Strategy C 維持 opt-in、VR byte-identical 第 26 連、vitest 1353→1358）、[sprint163_box_fieldtype_alignment](sprint163_box_fieldtype_alignment.md)（`Box.fieldType` 型別對齊 AST `FieldNode['fieldType']` 11 型、純型別清理、`tsc` error 4→2、VR byte-identical 第 27 連、vitest 1358→1361）、[sprint164_bookmark_render_defer](sprint164_bookmark_render_defer.md)（bookmark render wire-up probe → honest DEFER：canvas-editor 無 bookmark/anchor element type、§5 L358 改標 Phase 1 optional、render 消費屬 Phase 2 decision 2B、docs-only 0 行 production code）、[sprint165_phase1_exit_reverify](sprint165_phase1_exit_reverify.md)（**Phase 1 Exit re-verify 第 2 次通過**：4 條 Exit Criteria 全過、42 fixture 0 parse error、0 個非-optional `[ ]`、Phase 1 必做 scope 52/52 100%、13 項 Phase 1 optional 延後 Phase 2·5.4、docs-only 0 行 production code）、[sprint166_cjk_fallback_chain_wireup](sprint166_cjk_fallback_chain_wireup.md)（**CJK fallback chain → FontLoader wire-up**、規畫書 §2.2 L406 `[ ]`→`[x]`：主+altName 失敗且 `fontTable.charset` 判定 CJK 時試 思源黑體→微軟正黑體→新細明體 chain、charset '80'/'81'/'86'/'88' 才套用、+10 test、vitest 1361→1371、font_loader 不在 VR 路徑、同 Sprint 157 caller-side infrastructure 定位）、[sprint167_textalignment_render_wireup](sprint167_textalignment_render_wireup.md)（**`<w:textAlignment>` 行內垂直對齊 render 消費 wire-up**、decision A part 1/2、規畫書 §5 L517 `[ ]`→`[x]`：新檔 `verticalAlignShift.ts` 純函式 + `CanvasRenderer.renderLine` wire-up、依行內 box 高度差算 y 位移、等高行位移恆 0、Strategy C、42 fixture VR byte-identical 第 28 連、+14 test、vitest 1371→1385、framePr 留 Sprint 168）

> Sprint 159 / 160 v1 為 docs-only follow-up（§5 Phase 1 scope 重構 / footnote-endnote scope 釐清）、無獨立 audit doc；見 [autonomous_roadmap.md 進度追蹤表](autonomous_roadmap.md)。

---

## Cluster Retro（4 次）

| Retro | 範圍 | 觸發點 |
|---|---|---|
| [sprint50_66_retro](sprint50_66_retro.md) | Sprint 50-66、17 sprint | cache + FontMetricsAdapter 方法論萃取 |
| [sprint121_142_retro](sprint121_142_retro.md) | Sprint 121-142、22 sprint | wire-up + autonomous 邊界 |
| [sprint143_148_retro](sprint143_148_retro.md) | Sprint 143-148、6 sprint | capture-only 模式成熟 |
| [sprint145_153_retro](sprint145_153_retro.md) | Sprint 145-153、9 sprint | 整數里程碑 + 進階變體 explicit + scope drift 揭示 |

按 [scope_audit_2026-05-19.md §4.3](scope_audit_2026-05-19.md) 建議:Sprint 156+ 起 cluster ≥ 20 sprint 才寫 retro。

---

## 主題分群、Phase 對映、cross-reference

完整 sprint → Phase 對映、ADR 連結、紀律編號出處見:
- [progress_snapshot.md §3 Phase 完成度](progress_snapshot.md) — Phase 0-8 各自完成度 + 代表 sprint
- [../CONTRIBUTING.md §5 + §6](../CONTRIBUTING.md) — 22 條紀律 + 6 子 + 1 候選 + 1 潛在子的 sprint 出處
- [architecture_decision.md](architecture_decision.md) — 22 個 ADR（含 ADR-022 Phase 8 / ADR-021 Sprint 117 cross-company / ADR-001-020 早期）
- [scope_audit_2026-05-19.md](scope_audit_2026-05-19.md) — 11 個嫌疑 sprint 群組（G1-G11）的去留判定

---

**索引維護**: Sprint 156+ 新 audit doc append 到對應主題分群末尾;新 cluster 須 ≥ 20 sprint 才啟動 retro 寫法。
