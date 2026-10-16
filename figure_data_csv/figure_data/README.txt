論文図の描画データ（CSV）
==========================
対象: Access-hayase-2026v22.docx の Fig. 1〜5
数値は浮動小数点の完全精度（Python repr）で出力。文字コード UTF-8（fig1_texts.csv のみ BOM 付き）。

fig1/  図1（ブロック図）— 新しい fig1_arch_alu.svg の幾何データ
  fig1_shapes.csv   図形ごとの頂点列（SVG 座標, 単位 px, 原点左上, y 下向き, キャンバス 1040x540）
                    矩形は閉じた頂点列に展開し、元の x/y/w/h/rx を description に記載。ALU は shape_id 10 の polygon。
                    配線(path)は始点→終点の順。矢印は終点側。
  fig1_texts.csv    文字列、位置（x, ベースライン y）、text-anchor、フォント

fig2/  図2（実現可能領域マップ）— paper/make_fig2.py
  fig2a_region_map.csv / fig2b_region_map.csv  241x241 格子の各点で選ばれる設計（region_index -1 = infeasible）
  fig2a_frontier_curves.csv / fig2b_...        黒線: gamma_t = 1000/(D0 + D1*gamma_w)
  fig2_coefficients_input.csv                  描画に使った D0, D1, CPI, トランジスタ数
  fig2_markers.csv, fig2_legend.csv            星印（2025 MoS2）、凡例の色

fig3/  図3（歩留まりラダー）— paper/make_fig3.py
  fig3a_curves.csv / fig3b_curves.csv          9 設計（灰線）と包絡線（黒線）, d = 1〜5000 ppm, 600 点
  fig3a/b_design_parameters.csv                各設計の T と d=0 でのスループット
  fig3a/b_shaded_regions_and_lines.csv         網掛け領域・点線・赤線とその範囲

fig4/  図4（ブロック歩留まり）— tools/block_yield.py --fig
  fig4_curves.csv           Poisson 800 ppm/T、NB フィット、NB（alpha 95% 下限）の 3 曲線, 400 点
  fig4_curve_parameters.csv 各曲線の d, alpha（フィット値）
  fig4_data_points.csv      測定点と 95% 信頼区間（Clopper–Pearson）
  fig4_vertical_lines.csv   WUJI / W=1 / W=32 の縦点線

fig5/  図5（静的電力 vs 配線ペナルティ）— study.py figures() の PD-3 と同じ計算
  fig5_region_map.csv              121x121 格子の各点のエネルギー最適設計
  fig5_design_parameters_input.csv 計算に使った D0, D1, セル数, T, ピン数, alpha, CPI
  fig5_reference_line.csv          72.67 nW/T の破線

検証
  図2・図3・図4: CSV を書き出した同じ実行で描いた PNG が、論文 docx 内の画像とバイト単位で一致。
  図5: study.py は合成を要するため、results/study.csv と results/phase.md から同じ式で再計算
       （遅延は fmax_hz から逆算）。同じ描画コードで描いた PNG が同梱の results/figs/fig_pd3.png と画素単位で一致。
       ただし論文の図5を描いたスクリプトは同梱されておらず、論文の図は 121 点より細かい格子で
       描かれているように見える（境界の位置は同じ計算式による）。
