# -*- coding: utf-8 -*-
"""
Fig. 5 (energy-optimal width vs. wire penalty and static power) builder for OriginPro
(Origin 2021 or later, embedded Python).

How to run (inside Origin):
  Window > Script Window, then type (edit the path):
      run -pyf "C:\\path\\to\\fig5_make_origin.py"
  A file dialog opens: choose fig5_origin.csv.

The script creates
  - a workbook "fig5" with columns A (gamma_w, X) and B..F (Y)
  - a graph "Fig5": three filled regions (W=32 r, W=32 BK, W=16 BK) with black
    boundary lines, the 72.67 nW/T dashed reference line and its label, the legend,
    log-log axes with tick labels as powers of ten.

PDF hairline fix (same cause as Fig. 2): one row (gamma_w = 10, B..E = 0.01) is appended,
so every fill ends by dropping to the bottom axis at the right edge and the shared base
line of each fill lies on the bottom axis instead of crossing the plot.

Each step is wrapped so that a failure is reported in the Script window
("[fig5] WARNING ...") and the rest still runs.
"""
import csv
import math
import originpro as op

# ----------------------------------------------------------------- settings
XLIM = (0.1, 10)
YLIM = (0.01, 100)
# Fill colors as in the current manuscript PDF (Origin palette used for Fig. 2).
# The original matplotlib colors were W=32 r #4f8fba, W=32 BK #3c5e8b, W=16 BK #25562e.
FILL = {'B': '#006bac',   # W=32 r   (region between B and C)
        'C': '#004873',   # W=32 BK  (between C and D)
        'D': '#005e3f'}   # W=16 BK  (between D and E)
BOUNDARY_COLOR = '#000000'
BOUNDARY_WIDTH_PT = 1.0
REF_COLOR = '#ffffff'      # white dashed line, as in the manuscript PDF
REF_WIDTH_PT = 1.0
REF_LABEL = 'E/D NMOS, 72.67 nW/T'
REF_LABEL_CENTER = (0.259, 49.8)    # read from the manuscript PDF
LEGEND = '\\l(3) W = 16 BK\n\\l(2) W = 32 BK\n\\l(1) W = 32 r'
LEGEND_CENTER = (4.33, 0.031)       # read from the manuscript PDF (lower right)
X_TITLE = r'Wire penalty \i(\g(g))\-(W) (2025 MoS\-(2) = 1)'
Y_TITLE = r'Static power per transistor \i(p)\-(s) (nW)'
FIX_ROW = True             # append (10, 0.01) to A..E to remove the PDF hairlines
# --------------------------------------------------------------------------

DESIGNATION = 'XYYYYY'     # A..F


def warn(step, err):
    print('[fig5] WARNING in %s: %s' % (step, err))


def read_csv(path):
    with open(path, newline='', encoding='utf-8-sig') as f:
        rows = list(csv.reader(f))
    head, body = rows[0], rows[1:]
    return head, {h: [r[i] if i < len(r) else '' for r in body] for i, h in enumerate(head)}


def numbers(values):
    out = [float(v) for v in values if v != '']
    return out


def main():
    print('[fig5] Origin version', op.org_ver())
    path = op.file_dialog('*.csv')
    if not path:
        print('[fig5] cancelled')
        return
    head, cols = read_csv(path)
    if len(head) < 6 or not head[1].startswith('P1 ') or not head[5].startswith('P5 '):
        op.messagebox('Unexpected file: choose fig5_origin.csv')
        return

    # 1) worksheet A..F ---------------------------------------------------------
    wb = op.new_book('w', 'fig5')
    wks = op.find_sheet('w', wb.name)
    wks.cols = 6
    data = [numbers(cols[h]) for h in head[:6]]
    n = len(data[0])
    if FIX_ROW:
        data[0].append(float(XLIM[1]))          # gamma_w = 10
        for c in range(1, 5):                   # B..E (fill boundaries)
            data[c].append(float(YLIM[0]))      # 0.01 = bottom of the axis
        # F (reference line) is not extended
    for i, h in enumerate(head[:6]):
        wks.from_list(i, data[i], lname=h, axis=DESIGNATION[i])
    print('[fig5] worksheet %s filled (%d rows%s)' % (wb.name, len(data[0]),
                                                     ', hairline-fix row added' if FIX_ROW else ''))

    # 2) graph: boundaries B..E (consecutive, so "next plot" is correct), then F ---
    gp = op.new_graph('Fig5')
    gl = gp[0]
    for col in 'BCDE':
        p = gl.add_plot(wks, coly=col, colx='A', type='l')
        p.color = BOUNDARY_COLOR
        p.set_cmd('-d 0', '-w %d' % round(BOUNDARY_WIDTH_PT * 500))
        if col in FILL:
            oc = op.ocolor(FILL[col])
            try:
                # Fill Area Under Curve on, "Fill to next data plot - Above Below Colors",
                # same color above and below (the curves never cross)
                p.set_cmd('-pf 1', '-pfv 9', '-pfb %d' % oc, '-p2fb %d' % oc)
            except Exception as e:
                warn('fill of column %s (set it in Plot Details > Line/Pattern)' % col, e)
    try:
        p = gl.add_plot(wks, coly='F', colx='A', type='l')
        p.color = REF_COLOR
        p.set_cmd('-d 1', '-w %d' % round(REF_WIDTH_PT * 500))     # 1 = dash
    except Exception as e:
        warn('reference line', e)

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

    # 3) reference-line label ------------------------------------------------------
    try:
        lab = gl.add_label(REF_LABEL, *REF_LABEL_CENTER)
        lab.set_int('attach', 2)          # 2 = layer and scale
        lab.set_float('x', REF_LABEL_CENTER[0])
        lab.set_float('y', REF_LABEL_CENTER[1])
        lab.color = REF_COLOR
    except Exception as e:
        warn('reference label', e)

    # 4) legend ------------------------------------------------------------------
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

    print('[fig5] graph %s done' % gp.name)
    op.messagebox('Fig. 5 created.')


main()
