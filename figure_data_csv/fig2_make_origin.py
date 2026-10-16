# -*- coding: utf-8 -*-
"""
Fig. 2 (feasibility map, panels a and b) builder for OriginPro
(Origin 2021 or later, embedded Python). The look follows the current
Fig02_32RV.opju graphs as they appear in the manuscript PDF
(fill colors, black boundary lines, yellow star, legend at the left).

How to run (inside Origin):
  Window > Script Window, then type (edit the path):
      run -pyf "C:\\path\\to\\fig2_make_origin.py"
  Two file dialogs open: choose fig2a_origin.csv first, then fig2b_origin.csv.

What the script does for each panel
  - workbook "fig2a" / "fig2b" with the 22 CSV columns (A = X, U = X for the star)
  - PDF hairline fix: one row (gamma_w = 10, B..L = 0.1) is appended so that the shared
    base line of every fill lies on the bottom axis
  - graph "Fig2a" / "Fig2b": P1..P9 filled to the next plot, P10 (white) filled to P11
    (zero area, only gives the "infeasible" legend box), black boundary lines,
    the frontier lines of all nine designs (M..T, also inside the colored regions),
    the 2025 MoS2 star with its label, legend, title, axis titles,
    log-log axes 0.1..10 with tick labels as powers of ten.
Each decoration is wrapped so that a failure is reported in the Script window
("[fig2] WARNING ...") and the rest still runs.
"""
import csv
import originpro as op

# ----------------------------------------------------------------- settings
XLIM = (0.1, 10)
YLIM = (0.1, 10)
# fill color of each plot (fills from that column to the next one), read from the PDF
FILL = {'B': '#006bac',   # P1 -> W=32 r region
        'C': '#004873',   # P2 -> W=32 BK
        'D': '#808000',   # P3 -> W=16 r   (zero width in both panels)
        'E': '#6f510d',   # P4 -> W=16 BK
        'F': '#005e3f',   # P5 -> W=8 r    (almost zero width)
        'G': '#008c5f',   # P6 -> W=8 BK
        'H': '#f4a666',   # P7 -> W=4
        'I': '#f8bf92',   # P8 -> W=2
        'J': '#fbd9bd',   # P9 -> W=1
        'K': '#ffffff'}   # P10 -> P11, zero area: legend box for "infeasible"
LINE_COLOR = '#000000'
LINE_WIDTH_PT = 1.0
P10_LINE = ('#515151', 0.5)        # border of the "infeasible" legend box
# Frontier lines of all nine designs (Eq. (12)). Columns B..L already give the
# region boundaries (P11 = W=1 frontier); M..T (P12..P19) add the frontiers that run
# inside the colored regions, as in the matplotlib figure.
INTERNAL_LINES = True
INTERNAL_LINE = (LINE_COLOR, LINE_WIDTH_PT)
# Legend: text in the original order; each \l(n) points to the plot that really
# fills that region (P1 = W=32 r, P2 = W=32 BK, P3 = W=16 r, P4 = W=16 BK,
# P5 = W=8 r, P6 = W=8 BK). The earlier Origin legend had r and BK swapped.
LEGEND = ('\\l(10) infeasible\n\\l(9) W = 1\n\\l(8) W = 2\n\\l(7) W = 4\n'
          '\\l(5) W = 8 r\n\\l(6) W = 8 BK\n\\l(3) W = 16 r\n\\l(4) W = 16 BK\n'
          '\\l(1) W = 32 r\n\\l(2) W = 32 BK')
LEGEND_CENTER = (0.214, 0.385)     # positions read from the manuscript PDF
STAR = dict(kind=18, size=22, edge='#000000', fill='#ffff00')   # 18 = Star
STAR_LABEL = ('2025 MoS\\-(2)', 1.0, 1.26, '#ffff00')            # text, x, y, color
TITLES = {'a': '(a) register file off the die (configuration A)',
          'b': '(b) register file on the die (configuration B)'}
TITLE_CENTER = (1.0, 13.0)
X_TITLE = r'Wire penalty \g(g)\-(W) (2025 MoS\-(2) = 1)'
Y_TITLE = r'Device-delay penalty \g(g)\-(t) (2025 MoS\-(2) = 1)'
FIX_ROW = True
# --------------------------------------------------------------------------

DESIGNATION = 'X' + 'Y' * 19 + 'XY'    # A..T, U (star_x), V (star_y)
LETTERS = 'ABCDEFGHIJKLMNOPQRSTUV'


def warn(step, err):
    print('[fig2] WARNING in %s: %s' % (step, err))


def read_csv(path):
    with open(path, newline='', encoding='utf-8-sig') as f:
        rows = list(csv.reader(f))
    head, body = rows[0], rows[1:]
    return head, {h: [r[i] if i < len(r) else '' for r in body] for i, h in enumerate(head)}


def build_panel(p, path):
    head, cols = read_csv(path)
    if len(head) != 22 or not head[1].startswith('P1 ') or head[20] != 'star_x':
        raise RuntimeError('unexpected file %s (choose fig2%s_origin.csv)' % (path, p))

    # 1) worksheet -----------------------------------------------------------
    wb = op.new_book('w', 'fig2' + p)
    wks = op.find_sheet('w', wb.name)
    wks.cols = 22
    data = [[float(v) for v in cols[h] if v != ''] for h in head]
    if FIX_ROW:
        data[0].append(float(XLIM[1]))
        for c in range(1, 12):                 # B..L = P1..P11
            data[c].append(float(YLIM[0]))
    for i, h in enumerate(head):
        wks.from_list(i, data[i], lname=h, axis=DESIGNATION[i])
    print('[fig2] %s: worksheet %s filled' % (p, wb.name))

    # 2) graph: P1..P11 in this order (fill "to next plot" depends on it) -------
    gp = op.new_graph('Fig2' + p)
    gl = gp[0]
    for c in LETTERS[1:12]:                    # B..L
        plot = gl.add_plot(wks, coly=c, colx='A', type='l')
        color, width = (P10_LINE if c == 'K' else (LINE_COLOR, LINE_WIDTH_PT))
        plot.color = color
        plot.set_cmd('-d 0', '-w %d' % round(width * 500))
        if c in FILL:
            oc = op.ocolor(FILL[c])
            try:
                # Fill Area Under Curve on, "Fill to next data plot - Above Below Colors",
                # same color above and below (the boundaries never cross)
                plot.set_cmd('-pf 1', '-pfv 9', '-pfb %d' % oc, '-p2fb %d' % oc)
            except Exception as e:
                warn('fill of column %s' % c, e)

    # frontier lines inside the regions: M..T = P12..P19 (no fill, no extra row),
    # added after P11 so that "fill to next plot" of P1..P10 is unchanged
    if INTERNAL_LINES:
        for c in LETTERS[12:20]:               # M..T
            try:
                plot = gl.add_plot(wks, coly=c, colx='A', type='l')
                plot.color = INTERNAL_LINE[0]
                plot.set_cmd('-d 0', '-w %d' % round(INTERNAL_LINE[1] * 500))
            except Exception as e:
                warn('frontier line %s' % c, e)

    # star (last plot, drawn on top)
    try:
        s = gl.add_plot(wks, coly='V', colx='U', type='s')
        s.color = STAR['edge']                 # edge color
        s.set_cmd('-k %d' % STAR['kind'], '-kf 1', '-z %d' % STAR['size'],
                  '-csf %d' % op.ocolor(STAR['fill']))
    except Exception as e:
        warn('star', e)

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

    # 3) text: star label and title ----------------------------------------------
    def put_label(text, x, y, color=None):
        try:
            lab = gl.add_label(text, x, y)
            lab.set_int('attach', 2)           # 2 = layer and scale
            lab.set_float('x', x)              # centre, in axis units
            lab.set_float('y', y)
            if color:
                lab.color = color
        except Exception as e:
            warn('label "%s"' % text, e)

    put_label(STAR_LABEL[0], STAR_LABEL[1], STAR_LABEL[2], STAR_LABEL[3])
    put_label(TITLES[p], *TITLE_CENTER)

    # 4) legend ------------------------------------------------------------------------
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

    print('[fig2] %s: graph %s done' % (p, gp.name))


def main():
    print('[fig2] Origin version', op.org_ver())
    for p in 'ab':
        op.messagebox('Select fig2%s_origin.csv' % p)
        path = op.file_dialog('*.csv')
        if not path:
            print('[fig2] cancelled at panel', p)
            return
        try:
            build_panel(p, path)
        except Exception as e:
            op.messagebox('Fig. 2 (%s): %s' % (p, e))
            return
    op.messagebox('Fig. 2 (a) and (b) created.\nNext: Graph > Merge Graph Windows.')


main()
