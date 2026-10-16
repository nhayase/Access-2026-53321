# -*- coding: utf-8 -*-
"""
Fig. 4 (block yield vs. transistors per functional unit) builder for OriginPro
(Origin 2021 or later, embedded Python).

How to run (inside Origin):
  Window > Script Window, then type (edit the path):
      run -pyf "C:\\path\\to\\fig4_make_origin.py"
  A file dialog opens: choose fig4_origin.csv.

The script creates
  - a workbook "fig4" with the plotted columns
  - a graph "Fig4" with the three yield curves, the four measured points with their
    95 % confidence intervals, the WUJI / W=1 / W=32 dotted lines, labels and legend,
    log-log axes with tick labels as powers of ten.
Each decoration is wrapped so that a failure is reported in the Script window
("[fig4] WARNING ...") and the rest still runs.
"""
import csv
import math
import originpro as op

# ----------------------------------------------------------------- settings
XLIM = (0.69, 50118.72336272725)   # manuscript figure: data range plus a small left margin
YLIM = (1e-5, 1.5)
X_TITLE = r'transistors per functional unit \i(T)'
Y_TITLE = 'yield'
CURVES = [  # (column, color, line style code, width pt)   style: 0 solid, 1 dash, 2 dot, 3 dash-dot
    ('B', '#ff0000', 1, 2.0),   # Poisson, 800 ppm/T
    ('C', '#000000', 0, 3.0),   # NB fit to registers
    ('D', '#808080', 3, 2.0),   # NB, alpha = 1.3 (95 % lower bound)
]
LEGEND = ('\\l(1) Poisson, 800 ppm/T (99.92 % per T)\n'
          '\\l(2) NB fit to registers: 2394 ppm/T, \\i(\\g(a)) = 30\n'
          '\\l(3) NB, \\i(\\g(a)) = 1.3 (95 % lower bound)')
LEGEND_CENTER = (22.0, 4e-5)       # visual estimate from the manuscript figure
ERRBAR_WIDTH_PT = 1.5
POINTS = [  # (y col, x col, symbol kind, color, size)   kind: 1 square, 2 circle, 3 up-triangle
    ('F', 'E', 1, '#ff0000', 11),   # transistor
    ('H', 'G', 3, '#000000', 10),   # inverters
    ('J', 'I', 2, '#000000', 9),    # 8-bit and 64-bit registers
]
VLINE_COLOR = '#808080'
VLINE_WIDTH_PT = 1.0
TEXT_LABELS = [  # (text, x centre, y centre, rotate, color)  positions: visual estimates
    ('inverters', 5.3, 0.56, 0, None),
    ('8-bit reg.', 365.0, 0.92, 0, None),
    ('64-bit reg.', 3200.0, 0.116, 0, None),
]
VLINE_LABEL_POS = {'WUJI': (4690.0, 0.233), 'W=1': (8300.0, 0.227), 'W=32': (21300.0, 0.197)}
VLINE_LABEL_COLOR = '#606060'
# --------------------------------------------------------------------------

DESIGNATION = 'XYYYXYXYXYXY'   # columns A..L


def warn(step, err):
    print('[fig4] WARNING in %s: %s' % (step, err))


def read_csv(path):
    with open(path, newline='', encoding='utf-8-sig') as f:
        rows = list(csv.reader(f))
    head, body = rows[0], rows[1:]
    return head, {h: [r[i] if i < len(r) else '' for r in body] for i, h in enumerate(head)}


def numbers(values):
    out = [float(v) if v != '' else float('nan') for v in values]
    while out and math.isnan(out[-1]):
        out.pop()
    return out


def main():
    print('[fig4] Origin version', op.org_ver())
    path = op.file_dialog('*.csv')
    if not path:
        print('[fig4] cancelled')
        return
    head, cols = read_csv(path)

    # 1) worksheet: A..L ------------------------------------------------------
    wb = op.new_book('w', 'fig4')
    wks = op.find_sheet('w', wb.name)
    wks.cols = 12
    for i, h in enumerate(head[:12]):
        # empty cells inside a column (between error-bar segments) become missing
        # values, so Origin leaves a gap there; trailing empty cells are dropped
        data = numbers(cols[h])
        wks.from_list(i, data, lname=h, axis=DESIGNATION[i])
    print('[fig4] worksheet %s filled' % wb.name)

    # 2) graph ------------------------------------------------------------------
    gp = op.new_graph('Fig4')
    gl = gp[0]
    for col, color, style, width in CURVES:
        p = gl.add_plot(wks, coly=col, colx='A', type='l')
        p.color = color
        p.set_cmd('-d %d' % style, '-w %d' % round(width * 500))
    try:
        p = gl.add_plot(wks, coly='L', colx='K', type='l')     # 95 % CI error bars
        p.color = '#000000'
        p.set_cmd('-d 0', '-w %d' % round(ERRBAR_WIDTH_PT * 500))
    except Exception as e:
        warn('error bars', e)
    for ycol, xcol, kind, color, size in POINTS:
        try:
            p = gl.add_plot(wks, coly=ycol, colx=xcol, type='s')
            p.symbol_kind = kind
            p.color = color
            p.set_float('symbol.size', size)
        except Exception as e:
            warn('points %s' % ycol, e)

    gl.rescale()
    gl.xscale = 'log10'
    gl.yscale = 'log10'
    gl.set_xlim(*XLIM)
    gl.set_ylim(*YLIM)

    try:
        gl.activate()
        if not op.lt_exec('layer.x.label.type = 1; layer.x.label.numFormat = 2;'
                          'layer.y.label.type = 1; layer.y.label.numFormat = 2;'):
            warn('tick label format', 'LabTalk returned failure')
    except Exception as e:
        warn('tick label format', e)

    try:
        gl.axis('x').title = X_TITLE
        gl.axis('y').title = Y_TITLE
    except Exception as e:
        warn('axis titles', e)

    # 3) WUJI / W=1 / W=32 dotted vertical lines (axis reference lines) -----------
    vl = [(float(t), lab) for t, lab in zip(cols['vline_T'], cols['vline_label']) if t != '']
    lt = ['layer.x.reflines.count = %d;' % len(vl)]
    for i, (t, _) in enumerate(vl, 1):
        pre = 'layer.x.refline%d.' % i
        lt += [pre + 'value = %r;' % t, pre + 'labelshow = 0;', pre + 'lineshow = 1;',
               pre + 'lineauto = 0;', pre + 'linecolor = %d;' % op.ocolor(VLINE_COLOR),
               pre + 'linestyle = 2;', pre + 'linethickness = %g;' % VLINE_WIDTH_PT,
               pre + 'filltonext = 0;']
    try:
        gl.activate()
        if not op.lt_exec('\n'.join(lt)):
            warn('vertical lines', 'LabTalk returned failure')
    except Exception as e:
        warn('vertical lines', e)

    # 4) text labels -----------------------------------------------------------------
    def put_label(text, x, y, rotate=0, color=None):
        try:
            lab = gl.add_label(text, x, y)
            lab.set_int('attach', 2)          # 2 = layer and scale
            if rotate:
                lab.set_int('rotate', rotate)
            lab.set_float('x', x)             # centre, in axis units
            lab.set_float('y', y)
            if color:
                lab.color = color
        except Exception as e:
            warn('label "%s"' % text, e)

    for text, x, y, rot, color in TEXT_LABELS:
        put_label(text, x, y, rot, color)
    for _, lab in vl:
        if lab in VLINE_LABEL_POS:
            x, y = VLINE_LABEL_POS[lab]
            put_label(lab, x, y, 90, VLINE_LABEL_COLOR)

    # 5) legend (curves only) ----------------------------------------------------------
    try:
        gl.activate()
        op.lt_exec('legend -r;')
        leg = gl.label('Legend')
        leg.text = LEGEND
        leg.set_int('attach', 2)
        leg.set_float('x', LEGEND_CENTER[0])
        leg.set_float('y', LEGEND_CENTER[1])
    except Exception as e:
        warn('legend (edit it by hand)', e)

    print('[fig4] graph %s done' % gp.name)
    op.messagebox('Fig. 4 created.')


main()
