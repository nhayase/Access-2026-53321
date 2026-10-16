# -*- coding: utf-8 -*-
"""
Fig. 3 (yield ladder) builder for OriginPro (Origin 2021 or later, embedded Python).

How to run (inside Origin):
  Window > Script Window, then type (edit the path):
      run -pyf "C:\\path\\to\\fig3_make_origin.py"
  Two file dialogs open: choose fig3a_origin.csv first, then fig3b_origin.csv.

The script creates, for each panel:
  - a workbook "fig3a" / "fig3b" with the curve data (A = X, B..K = Y)
  - a graph "Fig3a" / "Fig3b" with 9 gray curves, the black envelope,
    log-log axes with tick labels as powers of ten (10^n),
    axis titles (the Y title on both panels), shaded regions
    and vertical lines (axis reference lines), and the region labels.
Each step is wrapped so that a failure in one decoration is reported in the
Messages / Script window and the rest still runs.
"""
import csv
import math
import originpro as op

# ----------------------------------------------------------------- settings
GRAY = '#aaaaaa'          # thin curves (value not recorded in the source data)
GRAY_WIDTH_PT = 1.0
ENV_COLOR = '#000000'     # envelope
ENV_WIDTH_PT = 2.5
XLIM = (1, 5000)
YLIM = (1e-4, 1e3)
REGION_LABEL_Y = 7e-4     # vertical centre of the rotated region labels (visual estimate)
TITLES = {'a': '(a) delay-budget reading, Table 2 netlists, 1 kHz',
          'b': '(b) cascade reading, Table 4 netlists, 5,847 Hz'}
X_TITLE = r'defect density \i(d) (defects per 10\+(6) transistors)'
Y_TITLE = 'Expected throughput per die (instr/s)'   # used in both (a) and (b)
# Red labels drawn only in panel (b), as in the manuscript figure.
# Text follows the manuscript figure; the source CSV says "800 ppm (99.92 % per T)".
RED_LABELS_B = [  # (x centre, y centre, text)  positions are visual estimates
    (800 * 1.12, 15.0, '800 ppm/T (99.92 % per T)'),
    (1112 * 1.12, 3.0, '898/900 inverters'),
    (2378 * 1.12, 6.0, '144-T registers, 71 %'),
]
LINESTYLE = {'solid': 0, 'dash': 1, 'dot': 2, 'dash-dot': 3}   # Origin line-style codes
# --------------------------------------------------------------------------


def warn(step, err):
    print('[fig3] WARNING in %s: %s' % (step, err))


def read_table(path):
    with open(path, newline='', encoding='utf-8-sig') as f:
        rows = list(csv.reader(f))
    head, body = rows[0], rows[1:]
    cols = {h: [r[i] if i < len(r) else '' for r in body] for i, h in enumerate(head)}
    return head, cols


def build_panel(p, path):
    head, cols = read_table(path)
    curve_heads = head[:11]                       # A = X, B..J = 9 designs, K = envelope

    # 1) worksheet --------------------------------------------------------
    wb = op.new_book('w', 'fig3' + p)
    wks = op.find_sheet('w', wb.name)
    wks.cols = 11
    for i, h in enumerate(curve_heads):
        data = [float(v) for v in cols[h] if v != '']
        wks.from_list(i, data, lname=h, axis='X' if i == 0 else 'Y')
    print('[fig3] %s: worksheet %s filled (%d rows)' % (p, wb.name, len(cols[curve_heads[0]])))

    # 2) graph and curves ---------------------------------------------------
    gp = op.new_graph('Fig3' + p)
    gl = gp[0]
    letters = 'ABCDEFGHIJK'
    for i in range(1, 11):
        plot = gl.add_plot(wks, coly=letters[i], colx='A', type='l')
        if i < 10:
            plot.color = GRAY
            plot.set_cmd('-w %d' % round(GRAY_WIDTH_PT * 500))   # -w: width in pt x 500
        else:
            plot.color = ENV_COLOR
            plot.set_cmd('-w %d' % round(ENV_WIDTH_PT * 500))
    gl.rescale()
    gl.xscale = 'log10'
    gl.yscale = 'log10'
    gl.set_xlim(*XLIM)
    gl.set_ylim(*YLIM)

    # tick labels as powers of ten (Tick Labels > Display = "Scientific: 10^3")
    # LabTalk layer.axis.label.numFormat: 1 decimal, 2 scientific, 3 engineering, 4 decimal with commas
    try:
        gl.activate()
        ok = op.lt_exec('layer.x.label.type = 1; layer.x.label.numFormat = 2;'
                        'layer.y.label.type = 1; layer.y.label.numFormat = 2;')
        if not ok:
            warn('tick label format', 'LabTalk returned failure')
    except Exception as e:
        warn('tick label format', e)

    try:
        gl.remove_label('Legend')
    except Exception as e:
        warn('remove legend (delete it by hand if it is still there)', e)

    try:
        gl.axis('x').title = X_TITLE
        gl.axis('y').title = Y_TITLE
    except Exception as e:
        warn('axis titles', e)

    # 3) reference lines (shaded regions, ladder boundaries, red lines) ------
    vals = [v for v in cols['refline_value'] if v != '']
    n = len(vals)
    value_to_index = {}
    for i, v in enumerate(vals, 1):
        value_to_index.setdefault(float(v), i)
    lt = ['layer.x.reflines.count = %d;' % n]
    for i in range(1, n + 1):
        r = {k[len('refline_'):]: cols[k][i - 1] for k in head if k.startswith('refline_')}
        pre = 'layer.x.refline%d.' % i
        lt.append(pre + 'value = %s;' % r['value'])
        lt.append(pre + 'labelshow = 0;')
        if r['show_line'] == 'yes':
            lt.append(pre + 'lineshow = 1;')
            lt.append(pre + 'lineauto = 0;')
            lt.append(pre + 'linecolor = %d;' % op.ocolor(r['line_color']))
            lt.append(pre + 'linestyle = %d;' % LINESTYLE[r['line_style']])
            lt.append(pre + 'linethickness = %s;' % r['line_width_pt'])
        else:
            lt.append(pre + 'lineshow = 0;')
        if r['fill_to'] != '':
            lt.append(pre + 'filltonext = %d;' % value_to_index[float(r['fill_to'])])
            lt.append(pre + 'fillcolor = %d;' % op.ocolor(r['fill_color']))
            lt.append(pre + 'filltrans = %s;' % r['fill_transparency_pct'])
        else:
            lt.append(pre + 'filltonext = 0;')
    try:
        gl.activate()
        ok = op.lt_exec('\n'.join(lt))
        if not ok:
            warn('reference lines', 'LabTalk returned failure')
    except Exception as e:
        warn('reference lines', e)

    # 4) region labels (rotated 90 deg, attached to axis scale) ---------------
    def put_label(text, x, y, color=None):
        try:
            lab = gl.add_label(text, x, y)
            lab.set_int('attach', 2)      # 2 = layer and scale
            lab.set_int('rotate', 90)
            lab.set_float('x', x)         # centre, in axis units
            lab.set_float('y', y)
            if color:
                lab.color = color
        except Exception as e:
            warn('label "%s"' % text, e)

    for t, x in zip(cols['label_text'], cols['label_x']):
        if t != '':
            put_label(t, float(x), REGION_LABEL_Y)
    if p == 'b':
        for x, y, t in RED_LABELS_B:
            put_label(t, x, y, '#ff0000')

    # 5) title above the frame ------------------------------------------------
    try:
        tl = gl.add_label(TITLES[p], math.sqrt(XLIM[0] * XLIM[1]), YLIM[1] * 2.5)
        tl.set_int('attach', 2)
        tl.set_float('x', math.sqrt(XLIM[0] * XLIM[1]))
        tl.set_float('y', YLIM[1] * 2.5)
    except Exception as e:
        warn('title', e)

    print('[fig3] %s: graph %s done' % (p, gp.name))
    return gp


def main():
    print('[fig3] Origin version', op.org_ver())
    for p in 'ab':
        op.messagebox('Select fig3%s_origin.csv' % p)
        path = op.file_dialog('*.csv')
        if not path:
            print('[fig3] cancelled at panel', p)
            return
        build_panel(p, path)
    op.messagebox('Fig. 3 (a) and (b) created.\nNext: merge with Graph > Merge Graph Windows.')


main()
