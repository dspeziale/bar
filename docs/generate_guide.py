#!/usr/bin/env python3
"""
Genera docs/guida_utente.docx — Guida Utente Completa per QuickLunch.

Ruoli coperti:
  1. Super Admin
  2. Admin Tenant (gestore locale)
  3. Cassiere / Cassa
  4. Cucina / KDS
  5. Sala (gestione tavoli)
  6. Cliente
  7. Dipendente Aziendale (convenzione pasto fisso)
"""

import os
from docx import Document
from docx.shared import Pt, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH

from docx.oxml.ns import qn
from docx.oxml import OxmlElement

# ── Palette ───────────────────────────────────────────────────────────────────
RED   = RGBColor(0xe9, 0x45, 0x60)
NAVY  = RGBColor(0x0f, 0x34, 0x60)
DARK  = RGBColor(0x16, 0x21, 0x3e)
DGRAY = RGBColor(0x34, 0x3a, 0x40)
GRAY  = RGBColor(0x6c, 0x75, 0x7d)
WHITE = RGBColor(0xff, 0xff, 0xff)
GREEN = RGBColor(0x27, 0xae, 0x60)
PURPL = RGBColor(0x8e, 0x44, 0xad)
TEAL  = RGBColor(0x16, 0xa0, 0x85)
ORNG  = RGBColor(0xe6, 0x7e, 0x22)

HEX_RED   = 'E94560'
HEX_NAVY  = '0F3460'
HEX_DARK  = '16213E'
HEX_LIGHT = 'F8F9FA'
HEX_WHITE = 'FFFFFF'
HEX_GREEN = '27AE60'
HEX_PURPL = '8E44AD'
HEX_TEAL  = '16A085'
HEX_ORNG  = 'E67E22'

FONT = 'PT Sans Narrow'
OUT  = os.path.join(os.path.dirname(__file__), 'guida_utente.docx')


# ── XML helpers ───────────────────────────────────────────────────────────────

def _cell_shd(cell, fill):
    tc = cell._tc
    tcPr = tc.get_or_add_tcPr()
    for old in tcPr.findall(qn('w:shd')):
        tcPr.remove(old)
    shd = OxmlElement('w:shd')
    shd.set(qn('w:val'),   'clear')
    shd.set(qn('w:color'), 'auto')
    shd.set(qn('w:fill'),  fill.lstrip('#'))
    tcPr.append(shd)


def _cell_border(cell, *, top=None, bottom=None, left=None, right=None,
                 sz='8', space='0'):
    tc = cell._tc
    tcPr = tc.get_or_add_tcPr()
    for old in tcPr.findall(qn('w:tcBorders')):
        tcPr.remove(old)
    tcBorders = OxmlElement('w:tcBorders')
    sides = {'top': top, 'bottom': bottom, 'left': left, 'right': right}
    for side, color in sides.items():
        el = OxmlElement(f'w:{side}')
        if color:
            el.set(qn('w:val'),   'single')
            el.set(qn('w:sz'),    sz)
            el.set(qn('w:color'), color.lstrip('#'))
            el.set(qn('w:space'), space)
        else:
            el.set(qn('w:val'), 'nil')
        tcBorders.append(el)
    tcPr.append(tcBorders)


def _cell_vAlign(cell, val='center'):
    tc = cell._tc
    tcPr = tc.get_or_add_tcPr()
    vAlign = OxmlElement('w:vAlign')
    vAlign.set(qn('w:val'), val)
    tcPr.append(vAlign)


def _cell_margins(cell, top=40, bottom=40, left=80, right=80):
    tc = cell._tc
    tcPr = tc.get_or_add_tcPr()
    for old in tcPr.findall(qn('w:tcMar')):
        tcPr.remove(old)
    mar = OxmlElement('w:tcMar')
    for side, val in (('top', top), ('bottom', bottom),
                      ('left', left), ('right', right)):
        el = OxmlElement(f'w:{side}')
        el.set(qn('w:w'),    str(val))
        el.set(qn('w:type'), 'dxa')
        mar.append(el)
    tcPr.append(mar)


def _set_col_width(table, col_idx, width_cm):
    for row in table.rows:
        cell = row.cells[col_idx]
        tc = cell._tc
        tcPr = tc.get_or_add_tcPr()
        tcW = OxmlElement('w:tcW')
        tcW.set(qn('w:w'),    str(int(Cm(width_cm).emu / 914.4)))
        tcW.set(qn('w:type'), 'dxa')
        for old in tcPr.findall(qn('w:tcW')):
            tcPr.remove(old)
        tcPr.append(tcW)


def _no_borders(table):
    tbl = table._tbl
    tblPr = tbl.find(qn('w:tblPr'))
    if tblPr is None:
        tblPr = OxmlElement('w:tblPr')
        tbl.insert(0, tblPr)
    for old in tblPr.findall(qn('w:tblBorders')):
        tblPr.remove(old)
    bdr = OxmlElement('w:tblBorders')
    for side in ('top', 'left', 'bottom', 'right', 'insideH', 'insideV'):
        el = OxmlElement(f'w:{side}')
        el.set(qn('w:val'), 'nil')
        bdr.append(el)
    tblPr.append(bdr)


def _table_width(table, width_cm):
    tbl = table._tbl
    tblPr = tbl.find(qn('w:tblPr'))
    if tblPr is None:
        tblPr = OxmlElement('w:tblPr')
        tbl.insert(0, tblPr)
    for old in tblPr.findall(qn('w:tblW')):
        tblPr.remove(old)
    tblW = OxmlElement('w:tblW')
    tblW.set(qn('w:w'),    str(int(Cm(width_cm).emu / 914.4)))
    tblW.set(qn('w:type'), 'dxa')
    tblPr.append(tblW)


def _para_border(p, *, bottom_color=None, bottom_sz='6'):
    pPr = p._p.get_or_add_pPr()
    for old in pPr.findall(qn('w:pBdr')):
        pPr.remove(old)
    pBdr = OxmlElement('w:pBdr')
    if bottom_color:
        bot = OxmlElement('w:bottom')
        bot.set(qn('w:val'),   'single')
        bot.set(qn('w:sz'),    bottom_sz)
        bot.set(qn('w:color'), bottom_color.lstrip('#'))
        pBdr.append(bot)
    pPr.append(pBdr)


def _page_break(doc):
    p = doc.add_paragraph()
    run = p.add_run()
    run.add_break(__import__('docx.enum.text', fromlist=['WD_BREAK'])
                  .WD_BREAK.PAGE)
    p.paragraph_format.space_after = Pt(0)
    p.paragraph_format.space_before = Pt(0)


def _row_height(row, h_cm):
    tr = row._tr
    trPr = tr.find(qn('w:trPr'))
    if trPr is None:
        trPr = OxmlElement('w:trPr')
        tr.insert(0, trPr)
    trH = OxmlElement('w:trHeight')
    trH.set(qn('w:val'), str(int(Cm(h_cm).emu / 914.4)))
    trH.set(qn('w:hRule'), 'exact')
    trPr.append(trH)


# ── Run helpers ───────────────────────────────────────────────────────────────

def _run_font(run, size=14, bold=False, color=None, italic=False, font=FONT):
    run.font.name   = font
    run.font.size   = Pt(size)
    run.font.bold   = bold
    run.font.italic = italic
    if color:
        run.font.color.rgb = color
    rPr = run._r.get_or_add_rPr()
    rFonts = rPr.find(qn('w:rFonts'))
    if rFonts is None:
        rFonts = OxmlElement('w:rFonts')
        rPr.insert(0, rFonts)
    for attr in ('w:ascii', 'w:hAnsi', 'w:cs', 'w:eastAsia'):
        rFonts.set(qn(attr), font)


def _p_spacing(p, before=0, after=6, line=None):
    p.paragraph_format.space_before = Pt(before)
    p.paragraph_format.space_after  = Pt(after)
    if line:
        p.paragraph_format.line_spacing = Pt(line)


# ── Document-level helpers ─────────────────────────────────────────────────────

def set_document_defaults(doc):
    styles = doc.styles
    normal = styles['Normal']
    normal.font.name = FONT
    normal.font.size = Pt(14)
    normal.font.color.rgb = DGRAY

    sect = doc.sections[0]
    sect.page_width   = Cm(21.0)
    sect.page_height  = Cm(29.7)
    sect.top_margin    = Cm(2.0)
    sect.bottom_margin = Cm(2.0)
    sect.left_margin   = Cm(2.2)
    sect.right_margin  = Cm(2.2)


def body_para(doc, text='', color=None, size=14, bold=False,
              align=WD_ALIGN_PARAGRAPH.LEFT, after=4, before=0):
    p = doc.add_paragraph()
    p.alignment = align
    _p_spacing(p, before=before, after=after)
    if text:
        run = p.add_run(text)
        _run_font(run, size=size, bold=bold, color=color or DGRAY)
    return p


def h1(doc, number, title, icon='', accent=HEX_RED):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.LEFT
    _p_spacing(p, before=10, after=4)
    label = p.add_run(f'SEZIONE {number}   ')
    _run_font(label, size=9, bold=True, color=RED)
    if icon:
        ic = p.add_run(icon + '  ')
        _run_font(ic, size=20)
    run = p.add_run(title)
    _run_font(run, size=22, bold=True, color=NAVY)
    _para_border(p, bottom_color=accent, bottom_sz='8')
    return p


def h2(doc, text, color=None):
    p = doc.add_paragraph()
    _p_spacing(p, before=8, after=3)
    run = p.add_run(text)
    _run_font(run, size=16, bold=True, color=color or DARK)
    return p


def h3(doc, text, color=None):
    p = doc.add_paragraph()
    _p_spacing(p, before=5, after=2)
    run = p.add_run(text)
    _run_font(run, size=14, bold=True, color=color or NAVY)
    return p


def info_box(doc, text, style='tip', label=None):
    IC = {'tip': '💡', 'warning': '⚠️', 'success': '✅', 'info': 'ℹ️'}
    ic = IC.get(style, '💡')
    tbl = doc.add_table(rows=1, cols=1)
    _no_borders(tbl)
    _table_width(tbl, 17.6)
    cell = tbl.rows[0].cells[0]
    _cell_shd(cell, 'F5F5F5')
    _cell_border(cell, top='E8E8E8', bottom='E8E8E8', right='E8E8E8', left=HEX_RED, sz='14')
    _cell_margins(cell, top=70, bottom=70, left=130, right=90)
    p = cell.paragraphs[0]
    _p_spacing(p, before=0, after=0)
    prefix_text = f'{ic}  '
    if label:
        prefix_text += f'{label}  '
    prefix = p.add_run(prefix_text)
    _run_font(prefix, size=13, bold=bool(label), color=RED)
    run = p.add_run(text)
    _run_font(run, size=13, color=DGRAY)
    return tbl


def info_box_color(doc, text, bg='EBF5FB', border=HEX_TEAL, icon='ℹ️'):
    tbl = doc.add_table(rows=1, cols=1)
    _no_borders(tbl)
    _table_width(tbl, 17.6)
    cell = tbl.rows[0].cells[0]
    _cell_shd(cell, bg)
    _cell_border(cell, top=border, bottom=border, right=border, left=border, sz='6')
    _cell_margins(cell, top=70, bottom=70, left=130, right=90)
    p = cell.paragraphs[0]
    _p_spacing(p, before=0, after=0)
    r = p.add_run(f'{icon}  {text}')
    _run_font(r, size=13, color=DGRAY)
    return tbl


def step_row(doc, num, title, text, accent=HEX_RED):
    tbl = doc.add_table(rows=1, cols=2)
    _no_borders(tbl)
    _table_width(tbl, 17.6)

    nc = tbl.rows[0].cells[0]
    _set_col_width(tbl, 0, 1.2)
    _cell_shd(nc, accent)
    _cell_margins(nc, top=70, bottom=70, left=40, right=40)
    _cell_vAlign(nc, 'center')
    pn = nc.paragraphs[0]
    pn.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _p_spacing(pn, before=0, after=0)
    rn = pn.add_run(str(num))
    _run_font(rn, size=15, bold=True, color=WHITE)

    cc = tbl.rows[0].cells[1]
    _cell_shd(cc, 'F0F4F8')
    _cell_margins(cc, top=70, bottom=70, left=110, right=90)
    pt = cc.paragraphs[0]
    _p_spacing(pt, before=0, after=3)
    rt = pt.add_run(title + '\n')
    _run_font(rt, size=13, bold=True, color=DARK)
    rb = pt.add_run(text)
    _run_font(rb, size=12, color=GRAY)
    return tbl


def data_table(doc, headers, rows, col_widths=None, accent=HEX_RED):
    ncols = len(headers)
    tbl = doc.add_table(rows=1 + len(rows), cols=ncols)
    _table_width(tbl, 17.6)

    hr = tbl.rows[0]
    for i, h in enumerate(headers):
        c = hr.cells[i]
        _cell_shd(c, accent)
        _cell_border(c)
        _cell_margins(c, top=60, bottom=60, left=80, right=80)
        p = c.paragraphs[0]
        _p_spacing(p, before=0, after=0)
        r = p.add_run(h)
        _run_font(r, size=11, bold=True, color=WHITE)
    if col_widths:
        for i, w in enumerate(col_widths):
            _set_col_width(tbl, i, w)

    for ri, row_data in enumerate(rows):
        bg = HEX_WHITE if ri % 2 == 0 else 'F8F9FA'
        dr = tbl.rows[ri + 1]
        for ci, val in enumerate(row_data):
            c = dr.cells[ci]
            _cell_shd(c, bg)
            _cell_border(c, bottom='DEE2E6')
            _cell_margins(c, top=55, bottom=55, left=80, right=80)
            p = c.paragraphs[0]
            _p_spacing(p, before=0, after=0)
            bold = (ci == 0)
            r = p.add_run(val)
            _run_font(r, size=11, bold=bold, color=DARK if bold else GRAY)
    return tbl


def role_badge(doc, icon, role_name, desc, bg_hex, text_hex='FFFFFF'):
    tbl = doc.add_table(rows=1, cols=2)
    _no_borders(tbl)
    _table_width(tbl, 17.6)
    _set_col_width(tbl, 0, 3.5)
    _set_col_width(tbl, 1, 14.1)

    bc = tbl.rows[0].cells[0]
    _cell_shd(bc, bg_hex)
    _cell_margins(bc, top=80, bottom=80, left=60, right=60)
    _cell_vAlign(bc, 'center')
    pb = bc.paragraphs[0]
    pb.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _p_spacing(pb, before=0, after=0)
    _run_font(pb.add_run(icon + '\n'), size=22)
    _run_font(pb.add_run(role_name), size=10, bold=True,
              color=RGBColor(*bytes.fromhex(text_hex)))

    dc = tbl.rows[0].cells[1]
    _cell_shd(dc, HEX_LIGHT)
    _cell_margins(dc, top=80, bottom=80, left=120, right=90)
    _cell_vAlign(dc, 'center')
    pd = dc.paragraphs[0]
    _p_spacing(pd, before=0, after=0)
    _run_font(pd.add_run(desc), size=13, color=DGRAY)
    return tbl


def workflow_table(doc, steps, accent=HEX_NAVY):
    ncols = len(steps)
    tbl = doc.add_table(rows=1, cols=ncols)
    _table_width(tbl, 17.6)
    for i, (icon, title, desc) in enumerate(steps):
        c = tbl.rows[0].cells[i]
        bg = accent if i % 2 == 0 else '1A2E50'
        _cell_shd(c, bg)
        _cell_border(c, right='16213E')
        _cell_margins(c, top=100, bottom=100, left=80, right=80)
        p = c.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        _p_spacing(p, before=0, after=4)
        _run_font(p.add_run(icon + '\n'), size=18)
        _run_font(p.add_run(title + '\n'), size=10, bold=True, color=WHITE)
        _run_font(p.add_run(desc), size=9, color=RGBColor(0xb0, 0xc4, 0xd8))
    return tbl


def spacer(doc, pts=6):
    p = doc.add_paragraph()
    _p_spacing(p, before=0, after=0)
    p.paragraph_format.space_after = Pt(pts)
    return p


def divider(doc):
    p = doc.add_paragraph()
    _p_spacing(p, before=4, after=4)
    _para_border(p, bottom_color='DEE2E6', bottom_sz='4')
    return p


# ── Cover page ────────────────────────────────────────────────────────────────

def build_cover(doc):
    tbl = doc.add_table(rows=3, cols=1)
    _no_borders(tbl)
    _table_width(tbl, 21.0)
    _row_height(tbl.rows[0], 4.5)
    _row_height(tbl.rows[1], 19.0)
    _row_height(tbl.rows[2], 6.2)

    for row in tbl.rows:
        _cell_shd(row.cells[0], HEX_DARK)
        _cell_margins(row.cells[0], top=0, bottom=0, left=0, right=0)

    # ── Riga centrale ──
    cc = tbl.rows[1].cells[0]
    _cell_shd(cc, HEX_DARK)
    _cell_margins(cc, top=0, bottom=0, left=300, right=300)
    _cell_vAlign(cc, 'center')

    def cp(text='', size=14, bold=False, color=WHITE,
           align=WD_ALIGN_PARAGRAPH.CENTER, after=10):
        p = cc.add_paragraph()
        p.alignment = align
        _p_spacing(p, before=0, after=after)
        if text:
            r = p.add_run(text)
            _run_font(r, size=size, bold=bold, color=color)
        return p

    p0 = cc.paragraphs[0]
    p0.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _p_spacing(p0, before=0, after=16)
    _run_font(p0.add_run('🍽️'), size=56, color=WHITE)

    cp('QuickLunch', size=54, bold=True, color=RED, after=0)
    cp('PRANZO', size=54, bold=True, color=WHITE, after=8)
    cp('GUIDA UTENTE COMPLETA', size=16, bold=True,
       color=RGBColor(0xc0, 0xd0, 0xe0), after=24)
    cp('Sistema di gestione per bar, mense e caffetterie',
       size=13, color=RGBColor(0x90, 0xa8, 0xc0), after=28)

    # Ruoli
    roles = [
        ('👑 Super Admin', HEX_RED),
        ('🏢 Admin Tenant', HEX_NAVY),
        ('💳 Cassiere', HEX_GREEN),
        ('🍳 Cucina / KDS', HEX_ORNG),
        ('🪑 Sala', HEX_TEAL),
        ('👤 Cliente', HEX_PURPL),
        ('🏭 Dipendente Aziendale', '5D6D7E'),
    ]
    pr = cc.add_paragraph()
    pr.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _p_spacing(pr, before=0, after=20)
    for i, (name, _) in enumerate(roles):
        _run_font(pr.add_run(name), size=11, color=RGBColor(0xb0, 0xc8, 0xe0))
        if i < len(roles) - 1:
            _run_font(pr.add_run('  ·  '), size=10, color=RGBColor(0x50, 0x60, 0x70))

    cp('Versione 2.0  ·  2025', size=10,
       color=RGBColor(0x60, 0x70, 0x80), after=0)

    # ── Riga inferiore ──
    bc = tbl.rows[2].cells[0]
    _cell_shd(bc, HEX_RED)
    _cell_margins(bc, top=60, bottom=60, left=300, right=300)
    _cell_vAlign(bc, 'center')
    pb = bc.paragraphs[0]
    pb.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _p_spacing(pb, before=0, after=6)
    _run_font(pb.add_run('⚠️  DOCUMENTO RISERVATO — USO INTERNO'), size=12,
              bold=True, color=WHITE)
    pb2 = bc.add_paragraph()
    pb2.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _p_spacing(pb2, before=0, after=0)
    _run_font(pb2.add_run(
        'Questo documento contiene le procedure operative di QuickLunch. '
        'Non distribuire all\'esterno senza autorizzazione.'),
        size=10, color=RGBColor(0xff, 0xcc, 0xcc))


# ── Table of contents ─────────────────────────────────────────────────────────

def build_toc(doc):
    h2(doc, '📋  Indice dei contenuti')
    spacer(doc, 4)

    toc_items = [
        ('1', '👑  Super Admin', 'Configurazione piattaforma, creazione tenant, utenti staff'),
        ('2', '🏢  Admin Tenant', 'Gestione prodotti, slot, magazzino, convenzioni, report'),
        ('3', '💳  Cassiere / Cassa', 'Punto vendita, pagamenti, wallet — come pagare un caffè'),
        ('4', '🍳  Cucina / KDS', 'Schermo cucina, gestione ordini, stati preparazione'),
        ('5', '🪑  Sala', 'Prenotazioni tavoli, check-in, monitoraggio tempo sosta'),
        ('6', '👤  Cliente', 'Auto-ordine, wallet, fidelizzazione, prenotazione tavoli'),
        ('7', '🏭  Dipendente Aziendale', 'Prenotazione pasto fisso convenzione aziendale'),
    ]

    tbl = doc.add_table(rows=len(toc_items), cols=3)
    _no_borders(tbl)
    _table_width(tbl, 17.6)
    _set_col_width(tbl, 0, 1.2)
    _set_col_width(tbl, 1, 5.8)
    _set_col_width(tbl, 2, 10.6)

    for ri, (num, title, desc) in enumerate(toc_items):
        bg = HEX_LIGHT if ri % 2 == 0 else HEX_WHITE
        row = tbl.rows[ri]
        _cell_shd(row.cells[0], HEX_RED)
        _cell_margins(row.cells[0], top=70, bottom=70, left=60, right=60)
        _cell_vAlign(row.cells[0], 'center')
        pn = row.cells[0].paragraphs[0]
        pn.alignment = WD_ALIGN_PARAGRAPH.CENTER
        _p_spacing(pn, before=0, after=0)
        _run_font(pn.add_run(num), size=14, bold=True, color=WHITE)

        _cell_shd(row.cells[1], bg)
        _cell_margins(row.cells[1], top=70, bottom=70, left=100, right=60)
        _cell_border(row.cells[1], bottom='DEE2E6')
        pt = row.cells[1].paragraphs[0]
        _p_spacing(pt, before=0, after=0)
        _run_font(pt.add_run(title), size=12, bold=True, color=DARK)

        _cell_shd(row.cells[2], bg)
        _cell_margins(row.cells[2], top=70, bottom=70, left=100, right=60)
        _cell_border(row.cells[2], bottom='DEE2E6')
        pd = row.cells[2].paragraphs[0]
        _p_spacing(pd, before=0, after=0)
        _run_font(pd.add_run(desc), size=11, color=GRAY)


# ══════════════════════════════════════════════════════════════════════════════
# SEZIONE 1 — SUPER ADMIN
# ══════════════════════════════════════════════════════════════════════════════

def s_super_admin(doc):
    h1(doc, '1', 'Super Admin', '👑')

    role_badge(doc, '👑', 'Super Admin',
               'Il Super Admin ha accesso illimitato alla piattaforma. '
               'Gestisce tenant, utenti globali e configurazioni di sistema. '
               'Accede alla stessa interfaccia Admin ma con visibilità su tutti i locali.',
               HEX_RED)
    spacer(doc, 8)

    h2(doc, '1.1  Primo accesso e login')
    step_row(doc, 1, 'Apri il browser', 'Vai all\'URL della piattaforma (es. https://pranzo.miodominio.it)')
    spacer(doc, 4)
    step_row(doc, 2, 'Inserisci le credenziali', 'Username e password fornite al momento dell\'installazione')
    spacer(doc, 4)
    step_row(doc, 3, 'Dashboard principale', 'Vedrai la Dashboard con KPI globali: ordini, wallet, prodotti attivi, avvisi magazzino')
    spacer(doc, 8)

    info_box(doc, 'Il Super Admin vede i dati di TUTTI i tenant. '
             'Per lavorare su un locale specifico, non è necessario cambiare tenant — '
             'le schermate Admin mostrano già il contesto giusto.', style='info')
    spacer(doc, 8)

    h2(doc, '1.2  Creare un nuovo tenant (locale)')
    body_para(doc, 'Ogni locale (bar, mensa, caffetteria) è un "tenant" indipendente con i propri prodotti, utenti e impostazioni.')
    spacer(doc, 4)

    data_table(doc,
        ['Campo', 'Descrizione', 'Esempio'],
        [
            ['Nome locale', 'Nome commerciale del bar/mensa', 'Bar Centrale'],
            ['Slug / Codice', 'Identificativo URL, solo lettere minuscole e trattini', 'bar-centrale'],
            ['Email contatto', 'Email del gestore principale', 'info@barcentrale.it'],
            ['Token Telegram', 'Bot token per notifiche (opzionale)', '123456:ABC...'],
            ['Chat ID Telegram', 'ID gruppo/canale notifiche cucina', '-100123456789'],
        ],
        col_widths=[3.8, 7.2, 6.6])
    spacer(doc, 8)

    h2(doc, '1.3  Gestione utenti staff')
    body_para(doc, 'Per ogni tenant si creano gli utenti con i ruoli appropriati. '
              'Solo gli utenti con il flag "is_admin" accedono all\'area Admin.')
    spacer(doc, 4)

    data_table(doc,
        ['Ruolo', 'Flag', 'Cosa può fare'],
        [
            ['Super Admin',        'is_admin + superadmin', 'Tutto, su tutti i tenant'],
            ['Admin Tenant',       'is_admin',              'Tutto sul proprio tenant'],
            ['Cassiere',           'manage_orders',         'Cassa, ordini, wallet clienti'],
            ['Cucina / KDS',       'manage_kitchen',        'Schermo cucina, stati ordine'],
            ['Sala',               'manage_reservations',   'Prenotazioni e tavoli'],
            ['Cliente',            '(nessuno)',              'Auto-ordine, wallet, punti fedeltà'],
            ['Dipendente Aziendale','(nessuno + convenzione)', 'Solo pasto fisso aziendale'],
        ],
        col_widths=[4.2, 4.0, 9.4])
    spacer(doc, 8)

    info_box(doc, 'Un utente può avere più ruoli contemporaneamente. '
             'Esempio: un Admin Tenant può anche fare da Cassiere attivando entrambi i flag.',
             style='tip')
    spacer(doc, 8)

    h2(doc, '1.4  Configurazioni globali di sistema')
    step_row(doc, 1, 'Impostazioni email', 'Configura SMTP in config.py o variabili d\'ambiente per le email automatiche (avvisi magazzino)')
    spacer(doc, 4)
    step_row(doc, 2, 'Bot Telegram', 'Inserisci TELEGRAM_TOKEN nelle variabili di ambiente. Ogni tenant ha il proprio Chat ID')
    spacer(doc, 4)
    step_row(doc, 3, 'Backup database', 'Il file SQLite si trova in instance/bar.db — pianifica backup giornalieri')
    spacer(doc, 4)
    step_row(doc, 4, 'Aggiornamenti', 'Esegui git pull + pip install -r requirements.txt + riavvio del server applicativo')
    spacer(doc, 8)

    info_box(doc, 'Prima di ogni aggiornamento, esegui sempre il backup del database. '
             'I run di migrazione automatici (_ensure) aggiungono colonne in sicurezza senza perdere dati.',
             style='warning')


# ══════════════════════════════════════════════════════════════════════════════
# SEZIONE 2 — ADMIN TENANT
# ══════════════════════════════════════════════════════════════════════════════

def s_admin_tenant(doc):
    h1(doc, '2', 'Admin Tenant — Gestore del Locale', '🏢')

    role_badge(doc, '🏢', 'Admin Tenant',
               'Gestisce tutto ciò che riguarda il proprio locale: menu, fasce orarie, '
               'magazzino, convenzioni aziendali, staff e report economici.',
               HEX_NAVY)
    spacer(doc, 8)

    h2(doc, '2.1  Dashboard — panoramica giornaliera')
    body_para(doc, 'La Dashboard è la prima schermata dopo il login. '
              'Mostra in tempo reale tutti i KPI del locale.')
    spacer(doc, 6)

    data_table(doc,
        ['KPI', 'Icona', 'Cosa indica'],
        [
            ['Ordini del giorno',    '🛒', 'Numero di ordini ricevuti oggi'],
            ['Incasso del giorno',   '💰', 'Totale incassato oggi (contanti + wallet)'],
            ['Wallet clienti totale','💜', 'Somma di tutti i saldi wallet dei clienti'],
            ['Prenotazioni oggi',    '🪑', 'Tavoli prenotati per oggi'],
            ['Avvisi magazzino',     '🔴', 'Materiali sotto la soglia minima'],
            ['Prodotti attivi',      '📦', 'Prodotti disponibili nel menu'],
            ['Pasti Aziendali Oggi', '🏭', 'Card con prenotazioni/posti per ogni opzione, barra avanzamento e il proprio pasto prenotato (se applicabile)'],
        ],
        col_widths=[5.2, 1.5, 10.9])
    spacer(doc, 8)

    h2(doc, '2.2  Gestione prodotti e menu')
    workflow_table(doc, [
        ('📝', 'Crea prodotto', 'Nome, prezzo, categoria'),
        ('🏷️', 'Aggiungi tag', 'Vegano, senza glutine…'),
        ('📸', 'Foto prodotto', 'JPG/PNG consigliato'),
        ('✅', 'Attiva', 'Rende visibile al cliente'),
    ])
    spacer(doc, 8)

    step_row(doc, 1, 'Vai a Menu → Prodotti', 'Nel menu laterale Admin, sezione "Menu"')
    spacer(doc, 4)
    step_row(doc, 2, 'Clicca "+ Nuovo Prodotto"', 'Si apre il form di creazione')
    spacer(doc, 4)
    step_row(doc, 3, 'Compila i campi obbligatori', 'Nome, prezzo, categoria. Il campo "disponibile" attiva la visibilità')
    spacer(doc, 4)
    step_row(doc, 4, 'Salva e verifica', 'Il prodotto appare immediatamente nel menu cliente')
    spacer(doc, 8)

    info_box(doc, 'I prodotti possono essere temporaneamente disattivati senza eliminarli. '
             'Utile per prodotti stagionali o temporaneamente esauriti.', style='tip')
    spacer(doc, 8)

    h2(doc, '2.3  Gestione Tavoli — due sistemi distinti')
    body_para(doc, 'Admin → Tavoli è una pagina con quattro tab. '
              'È fondamentale capire la differenza tra i due sistemi di orari:')
    spacer(doc, 4)

    data_table(doc,
        ['Sistema', 'Scopo', 'Dove si configura'],
        [
            ['Slot ordini',    'Orari di ritiro del cibo (es. 12:00, 12:15…). '
                               'Capienza max ordini per non sovraccaricare la cucina.',  'Tab "Slot ordini"'],
            ['Fasce orarie',   'Blocchi di tempo per prenotare un tavolo. '
                               'Ogni fascia ha inizio, fine e durata seduta in minuti.',  'Tab "Fasce orarie"'],
        ],
        col_widths=[3.5, 10.5, 3.5])
    spacer(doc, 6)

    body_para(doc, 'Le fasce orarie generano automaticamente le sessioni prenotabili: '
              'una fascia 11:25–12:30 con 30 min crea le sessioni 11:25, 11:55 e 12:25. '
              'I clienti scelgono data + sessione + tavolo disponibile.')
    spacer(doc, 4)

    info_box(doc, 'La durata di permanenza (campo nella fascia oraria) determina quando viene inviata '
             'la notifica Telegram al responsabile sala: l\'avviso parte 10 minuti prima della scadenza.',
             style='warning')
    spacer(doc, 8)

    h3(doc, 'Aggiungere e rimuovere slot ordini')
    body_para(doc, 'Nel tab "Slot Ordini" (Admin → Tavoli) è possibile creare nuovi slot e '
              'rimuovere quelli non più necessari direttamente dalla stessa pagina.')
    spacer(doc, 4)

    step_row(doc, 1, 'Apri il tab "Slot Ordini"', 'Admin → Tavoli → tab Slot Ordini')
    spacer(doc, 4)
    step_row(doc, 2, 'Compila il form in cima alla pagina', 'Inserisci l\'orario (time picker) e la capacità massima di ordini per quello slot')
    spacer(doc, 4)
    step_row(doc, 3, 'Clicca "Aggiungi slot"', 'Lo slot viene creato immediatamente e appare nella lista')
    spacer(doc, 4)
    step_row(doc, 4, 'Eliminare uno slot esistente', 'Clicca il pulsante "Elimina" a fianco dello slot desiderato — viene rimosso senza conferma aggiuntiva')
    spacer(doc, 8)

    info_box(doc, 'Ogni slot ordine ha una capacità massima: una volta raggiunto il numero di ordini '
             'configurato, lo slot non è più selezionabile dai clienti. Calibra la capacità in base '
             'al ritmo di preparazione della cucina.', style='tip')
    spacer(doc, 8)

    h2(doc, '2.4  Magazzino — Materiali di consumo')
    body_para(doc, 'Il magazzino tiene traccia dei materiali di consumo (forchette, ciotoline, bicchieri, ecc.) '
              'e avvisa automaticamente il fornitore via email quando le scorte scendono sotto la soglia.')
    spacer(doc, 6)

    workflow_table(doc, [
        ('📦', 'Registra item', 'Nome, unità, soglia min'),
        ('🏭', 'Associa fornitore', 'Email per avvisi auto'),
        ('➕', 'Carico merce', 'Aggiorna le scorte'),
        ('🔴', 'Soglia raggiunta', 'Email al fornitore auto'),
        ('✅', 'Rifornimento', 'Alert si azzera'),
    ])
    spacer(doc, 8)

    step_row(doc, 1, 'Vai a Magazzino → Consumabili', 'Sezione Magazzino nel menu Admin')
    spacer(doc, 4)
    step_row(doc, 2, 'Crea un fornitore (opzionale)', 'Magazzino → Fornitori. Inserisci nome e email. Sarà avvisato automaticamente')
    spacer(doc, 4)
    step_row(doc, 3, 'Crea il materiale', '+ Nuovo: nome, unità di misura (pz, kg, lt), soglia minima, fornitore associato')
    spacer(doc, 4)
    step_row(doc, 4, 'Registra movimenti', 'Usa il bottone "➕ Movimento" per caricare o scaricare scorte')
    spacer(doc, 4)
    step_row(doc, 5, 'Monitoraggio', 'Dashboard mostra il badge rosso con quanti item sono sotto soglia')
    spacer(doc, 8)

    info_box(doc, 'Il sistema invia UNA SOLA email di avviso per ogni carenza. '
             'Una seconda email viene inviata solo dopo che le scorte sono tornate sopra soglia '
             'e poi sono nuovamente scese. Questo evita spam al fornitore.', style='info')
    spacer(doc, 8)

    h2(doc, '2.5  Convenzioni Aziendali')
    body_para(doc, 'Le convenzioni permettono a dipendenti di aziende convenzionate di prenotare '
              'un pasto fisso giornaliero a prezzo concordato, senza usare il menu standard.')
    spacer(doc, 4)

    step_row(doc, 1, 'Crea l\'azienda convenzionata', 'Convenzioni → Aziende → + Nuova. Inserisci nome, prezzo giornaliero, max coperti')
    spacer(doc, 4)
    step_row(doc, 2, 'Aggiungi i dipendenti', 'Nella scheda azienda, spunta i clienti già registrati da associare come dipendenti')
    spacer(doc, 4)
    step_row(doc, 3, 'Crea il pasto del giorno', 'Convenzioni → nome azienda → "Pasto del giorno". Inserisci nome, descrizione, prezzo, max prenotazioni')
    spacer(doc, 4)
    step_row(doc, 4, 'I dipendenti prenotano', 'Ogni dipendente vede "Pasto Aziendale" nel suo menu e sceglie lo slot orario')
    spacer(doc, 4)
    step_row(doc, 5, 'Segna come consumato', 'Nella lista prenotazioni, clicca "✔ Consumato" per ogni dipendente che ha ritirato il pasto')
    spacer(doc, 4)
    step_row(doc, 6, 'Verifica totale fatturabile', 'In fondo alla lista prenotazioni compare il totale: N coperti × prezzo')
    spacer(doc, 8)

    h2(doc, '2.6  Report e statistiche')
    data_table(doc,
        ['Report', 'Percorso', 'Contenuto'],
        [
            ['Vendite giornaliere',    'Admin → Report → Giornaliero', 'Ordini, incasso, prodotti venduti'],
            ['Andamento mensile',      'Admin → Report → Mensile',     'Grafico trend, confronto mesi'],
            ['Prodotti più venduti',   'Admin → Report → Top prodotti','Ranking per quantità e fatturato'],
            ['Wallet e punti fedeltà', 'Admin → Clienti',              'Saldo wallet e punti per ogni cliente'],
            ['Magazzino',              'Admin → Magazzino',             'Stock attuale e storico movimenti'],
        ],
        col_widths=[4.2, 5.5, 7.9])
    spacer(doc, 8)

    h2(doc, '2.7  Banco POS — Gestione articoli')
    body_para(doc, 'Il Banco POS è uno strumento di cassa rapida per pagamenti al bancone tramite QR. '
              'L\'Admin configura la griglia degli articoli disponibili raggiungibile da '
              'Admin → Banco → pulsante "Gestisci" (oppure direttamente su /admin/banco/items).')
    spacer(doc, 6)

    data_table(doc,
        ['Azione', 'Come fare', 'Nota'],
        [
            ['Aggiungere articolo', 'Form inline: inserisci nome, prezzo, icona Font Awesome e colore → "Salva"',
             'Appare subito nella griglia del Banco'],
            ['Modificare articolo', 'Clicca sull\'articolo nella lista → si apre modal di modifica → "Salva"',
             'Modifica immediata senza ricaricare'],
            ['Rimuovere articolo',  'Pulsante "Elimina" a fianco dell\'articolo',
             'Eliminazione soft: is_active=false (non persi i dati storici)'],
        ],
        col_widths=[3.8, 8.2, 5.6])
    spacer(doc, 6)

    info_box(doc, 'Scegli icone Font Awesome per rendere la griglia più intuitiva per lo staff: '
             'ad esempio "fa-coffee" per il caffè, "fa-bread-slice" per la brioche. '
             'Il colore del pulsante aiuta a distinguere le categorie a colpo d\'occhio.', style='tip')


# ══════════════════════════════════════════════════════════════════════════════
# SEZIONE 3 — CASSIERE / CASSA
# ══════════════════════════════════════════════════════════════════════════════

def s_cassiere(doc):
    h1(doc, '3', 'Cassiere / Cassa', '💳')

    role_badge(doc, '💳', 'Cassiere',
               'Il Cassiere gestisce il punto vendita fisico: riceve gli ordini, '
               'incassa i pagamenti, gestisce i wallet dei clienti e supporta i clienti '
               'che non usano l\'app. È la figura più operativa del sistema.',
               HEX_GREEN)
    spacer(doc, 8)

    info_box(doc,
             'IL CASSIERE NON HA BISOGNO DI CONOSCERE TUTTA LA PIATTAFORMA. '
             'Basta padroneggiare tre azioni: creare ordini, incassare pagamenti, ricaricare wallet.',
             style='warning', label='FOCUS OPERATIVO')
    spacer(doc, 10)

    # ── COME PAGARE UN CAFFÈ ─────────────────────────────────────────────────
    h2(doc, '☕  Come pagare un caffè — Procedura passo per passo')
    body_para(doc, 'Questo è lo scenario più comune. Un cliente si avvicina alla cassa e vuole pagare un caffè.')
    spacer(doc, 6)

    info_box_color(doc,
                   'SCENARIO: Mario si avvicina alla cassa e dice "Un caffè, per favore".',
                   bg='EAF7EA', border=HEX_GREEN, icon='☕')
    spacer(doc, 8)

    step_row(doc, 1, 'Accedi alla Cassa', 'Vai in Admin → Cassa (o clicca sull\'icona cassa nel menu). '
             'Se non sei loggato, inserisci le tue credenziali da Cassiere.', accent=HEX_GREEN)
    spacer(doc, 4)
    step_row(doc, 2, 'Seleziona il cliente (opzionale)', 'Se Mario ha un account, cercalo per nome o scansiona il suo QR. '
             'Se è anonimo, puoi procedere senza selezionare un cliente.', accent=HEX_GREEN)
    spacer(doc, 4)
    step_row(doc, 3, 'Aggiungi il caffè all\'ordine', 'Clicca su "Caffè espresso" (o la categoria Bevande calde → Caffè). '
             'Il prodotto appare nel riepilogo ordine a destra.', accent=HEX_GREEN)
    spacer(doc, 4)
    step_row(doc, 4, 'Verifica il totale', 'In basso nel riepilogo compare: Caffè espresso × 1 = 1,20 € '
             '(il prezzo dipende dalla configurazione del prodotto).', accent=HEX_GREEN)
    spacer(doc, 4)
    step_row(doc, 5, 'Scegli il metodo di pagamento', 'Hai tre opzioni:\n'
             '• CONTANTI → inserisci l\'importo ricevuto, il sistema calcola il resto\n'
             '• WALLET → il saldo viene scalato dal wallet del cliente\n'
             '• MISTO → parte contanti, parte wallet', accent=HEX_GREEN)
    spacer(doc, 4)
    step_row(doc, 6, 'Conferma il pagamento', 'Clicca "Conferma e incassa". '
             'Il sistema registra la transazione e aggiorna il saldo se usato il wallet.', accent=HEX_GREEN)
    spacer(doc, 4)
    step_row(doc, 7, 'Stampa o mostra scontrino (opzionale)', 'Se Mario vuole lo scontrino, clicca "Stampa". '
             'Se ha l\'app, la transazione appare già nel suo storico ordini.', accent=HEX_GREEN)
    spacer(doc, 8)

    info_box_color(doc,
                   'Mario ha pagato il caffè in 15 secondi. '
                   'Se Mario usa il wallet e ha i punti fedeltà attivi, '
                   'guadagnerà automaticamente punti su questo acquisto.',
                   bg='EAF7EA', border=HEX_GREEN, icon='✅')
    spacer(doc, 10)

    # ── PAGAMENTO CON WALLET ──────────────────────────────────────────────────
    h2(doc, '💜  Pagamento con Wallet digitale')
    body_para(doc, 'Il wallet è il portafoglio digitale del cliente caricato dall\'Admin o dal cliente stesso tramite app.')
    spacer(doc, 4)

    step_row(doc, 1, 'Cerca il cliente', 'Digita il nome o scansiona il codice QR del cliente nell\'app cassa')
    spacer(doc, 4)
    step_row(doc, 2, 'Verifica il saldo', 'Il saldo wallet del cliente appare accanto al nome (es. Mario Rossi — 💜 12,50€)')
    spacer(doc, 4)
    step_row(doc, 3, 'Aggiungi prodotti all\'ordine', 'Seleziona i prodotti normalmente dal catalogo')
    spacer(doc, 4)
    step_row(doc, 4, 'Seleziona pagamento: WALLET', 'Clicca "Wallet" come metodo di pagamento')
    spacer(doc, 4)
    step_row(doc, 5, 'Conferma', 'Se il saldo è sufficiente, la transazione viene completata. '
             'Se il saldo non basta, il sistema avvisa e propone pagamento misto.')
    spacer(doc, 8)

    info_box(doc, 'Il saldo wallet non può andare in negativo per default. '
             'Se il cliente vuole un prodotto ma non ha saldo sufficiente, '
             'proponigli di ricaricare prima (vedi sezione 3.3) oppure pagare la differenza in contanti.', style='tip')
    spacer(doc, 8)

    # ── RICARICA WALLET ───────────────────────────────────────────────────────
    h2(doc, '🔋  Ricaricare il wallet di un cliente')
    step_row(doc, 1, 'Vai in Admin → Clienti', 'Oppure usa la ricerca rapida nella cassa')
    spacer(doc, 4)
    step_row(doc, 2, 'Trova il cliente', 'Cerca per nome o email')
    spacer(doc, 4)
    step_row(doc, 3, 'Clicca "Ricarica Wallet"', 'Si apre il pannello di ricarica')
    spacer(doc, 4)
    step_row(doc, 4, 'Inserisci l\'importo', 'Es. 20,00€ — il cliente paga in contanti o carta')
    spacer(doc, 4)
    step_row(doc, 5, 'Conferma', 'Il saldo viene aggiornato immediatamente. Il cliente riceve notifica Telegram (se configurato)')
    spacer(doc, 8)

    # ── GESTIONE ORDINI WALK-IN ────────────────────────────────────────────────
    h2(doc, '📋  Gestione ordini al banco (walk-in)')
    body_para(doc, 'Per i clienti che ordinano direttamente al bancone senza usare l\'app:')
    spacer(doc, 4)

    step_row(doc, 1, 'Apri un nuovo ordine', 'Cassa → Nuovo Ordine (oppure "+" in alto)')
    spacer(doc, 4)
    step_row(doc, 2, 'Seleziona prodotti', 'Clicca sui prodotti del catalogo. Usa la barra di ricerca per trovare velocemente')
    spacer(doc, 4)
    step_row(doc, 3, 'Modifica quantità', 'Clicca sul prodotto nell\'ordine per aumentare/diminuire la quantità')
    spacer(doc, 4)
    step_row(doc, 4, 'Aggiungi note (opzionale)', 'Es. "senza zucchero", "al latte di soia" — visibile in cucina')
    spacer(doc, 4)
    step_row(doc, 5, 'Invia in cucina', 'Clicca "Invia ordine" — l\'ordine appare sullo schermo cucina (KDS)')
    spacer(doc, 4)
    step_row(doc, 6, 'Incassa', 'Quando il cliente ritira, incassa con il metodo scelto')
    spacer(doc, 8)

    # ── CASI SPECIALI ─────────────────────────────────────────────────────────
    h2(doc, '⚡  Scenari frequenti alla cassa')
    data_table(doc,
        ['Scenario', 'Azione', 'Nota'],
        [
            ['Cliente vuole annullare', 'Ordini → trova ordine → Annulla',
             'Solo se non ancora preparato in cucina'],
            ['Errore di prodotto',      'Apri ordine → Modifica → Salva',
             'Prima che vada in cucina'],
            ['Cliente senza app',       'Crea ordine manuale dalla cassa',
             'Non serve che il cliente sia registrato'],
            ['Scontrino già chiuso',    'Report → Transazioni → Stampa copia',
             'Disponibile per 30 giorni'],
            ['Resto da dare',           'Inserisci importo ricevuto → il sistema calcola',
             'Campo "Importo ricevuto" nel form pagamento'],
        ],
        col_widths=[4.2, 7.0, 6.4])
    spacer(doc, 8)

    info_box(doc, 'In caso di dubbio, usa sempre il tasto "Annulla" invece di forzare una transazione errata. '
             'È sempre possibile riaprire un ordine e correggerlo prima del pagamento finale.', style='warning')
    spacer(doc, 10)

    # ── BANCO POS — PAGAMENTO QR ──────────────────────────────────────────────
    h2(doc, '☕  Banco POS — Pagamento QR')
    body_para(doc, 'Il Banco POS è la modalità di cassa rapida per pagamenti al bancone: '
              'lo staff compone l\'ordine su una griglia articoli e genera un QR che il cliente '
              'scansiona con l\'app per pagare istantaneamente. '
              'Si accede da Admin → Banco (icona tazza nel menu laterale).')
    spacer(doc, 6)

    info_box_color(doc,
                   'SCENARIO: Un cliente si avvicina al bancone e chiede un caffè e una brioche. '
                   'Lo staff tocca gli articoli, genera il QR e il cliente paga con il telefono in pochi secondi.',
                   bg='EAF7EA', border=HEX_GREEN, icon='☕')
    spacer(doc, 8)

    h3(doc, 'Composizione dell\'ordine al banco')
    step_row(doc, 1, 'Accedi al Banco', 'Vai in Admin → Banco. La schermata è divisa: griglia articoli a sinistra, riepilogo + QR a destra.', accent=HEX_GREEN)
    spacer(doc, 4)
    step_row(doc, 2, 'Tocca gli articoli desiderati', 'Ogni tocco aggiunge 1 unità. Il badge sul pulsante mostra la quantità corrente.', accent=HEX_GREEN)
    spacer(doc, 4)
    step_row(doc, 3, 'Rivedi il riepilogo', 'A destra compaiono gli articoli aggiunti con quantità. Usa il pulsante "−" per rimuovere unità.', accent=HEX_GREEN)
    spacer(doc, 4)
    step_row(doc, 4, 'Verifica il totale', 'Il totale si aggiorna in tempo reale ad ogni modifica del carrello.', accent=HEX_GREEN)
    spacer(doc, 8)

    h3(doc, 'Generazione del QR e incasso')
    step_row(doc, 5, 'Tocca "Genera QR"', 'Si apre un modal con: totale in grande, QR code e countdown di 10 minuti.', accent=HEX_GREEN)
    spacer(doc, 4)
    step_row(doc, 6, 'Mostra il QR al cliente', 'Il modal mostra "In attesa di pagamento…" mentre aspetta la scansione.', accent=HEX_GREEN)
    spacer(doc, 4)
    step_row(doc, 7, 'Il cliente scansiona e paga', 'Dall\'app cliente → "Paga al Banco", il cliente inquadra il QR e conferma il pagamento.', accent=HEX_GREEN)
    spacer(doc, 4)
    step_row(doc, 8, 'Conferma pagamento ricevuta', 'Il modal mostra "✓ Pagato da [Nome Cliente]". Il carrello si svuota automaticamente per il prossimo cliente.', accent=HEX_GREEN)
    spacer(doc, 8)

    info_box(doc, 'Il QR scade dopo 10 minuti (countdown visibile nel modal). '
             'Se il cliente non riesce a scansionare in tempo, tocca "Annulla sessione" e genera un nuovo QR.', style='warning')
    spacer(doc, 8)

    data_table(doc,
        ['Situazione', 'Cosa fare'],
        [
            ['Cliente non ha l\'app',        'Usa la cassa tradizionale (sezione 3.1) con pagamento contanti o wallet'],
            ['QR scaduto',                    'Tocca "Annulla sessione" nel modal, poi "Genera QR" di nuovo'],
            ['Cliente vuole annullare',       'Tocca "Annulla sessione" — il carrello rimane per eventuale nuovo tentativo'],
            ['Articolo non presente in griglia', 'Aggiungi l\'articolo da Admin → Banco → "Gestisci" (vedi sez. 2.7)'],
        ],
        col_widths=[5.0, 12.6])


# ══════════════════════════════════════════════════════════════════════════════
# SEZIONE 4 — CUCINA / KDS
# ══════════════════════════════════════════════════════════════════════════════

def s_cucina(doc):
    h1(doc, '4', 'Cucina / KDS — Kitchen Display System', '🍳')

    role_badge(doc, '🍳', 'Cucina / KDS',
               'La cucina riceve gli ordini in tempo reale sullo schermo KDS. '
               'L\'obiettivo è preparare gli ordini nell\'ordine giusto e '
               'aggiornare lo stato in modo che la sala e il cassiere sappiano cosa è pronto.',
               HEX_ORNG)
    spacer(doc, 8)

    h2(doc, '4.1  Accesso alla schermata KDS')
    step_row(doc, 1, 'Apri il browser sullo schermo cucina', 'Vai su: URL-locale/kds oppure Admin → Cucina/KDS')
    spacer(doc, 4)
    step_row(doc, 2, 'Login con credenziali cucina', 'Username e password del profilo Cucina (forniti dall\'Admin)')
    spacer(doc, 4)
    step_row(doc, 3, 'Schermo sempre attivo', 'La pagina KDS si aggiorna automaticamente ogni 30 secondi. Non chiudere il browser')
    spacer(doc, 8)

    h2(doc, '4.2  Lettura della schermata KDS')
    body_para(doc, 'Gli ordini appaiono come schede colorate. Ogni scheda contiene:')
    spacer(doc, 4)

    data_table(doc,
        ['Elemento', 'Significato'],
        [
            ['🕐 Orario ordine',    'Quando è stato inviato l\'ordine dal cliente/cassa'],
            ['👤 Cliente/Tavolo',   'Chi ha ordinato e a quale tavolo (se prenotato)'],
            ['📋 Lista prodotti',   'Ogni prodotto con quantità e note speciali'],
            ['🟡 NUOVO',            'Ordine appena arrivato — da iniziare a preparare'],
            ['🔵 IN PREPARAZIONE',  'Ordine preso in carico dalla cucina'],
            ['🟢 PRONTO',           'Piatto pronto per essere servito o ritirato'],
        ],
        col_widths=[4.5, 13.1])
    spacer(doc, 8)

    h2(doc, '4.3  Flusso operativo cucina')
    workflow_table(doc, [
        ('🟡', 'NUOVO', 'Ordine arriva'),
        ('👆', 'PRENDI', 'Clicca "In preparazione"'),
        ('🍳', 'PREPARA', 'Cucina il piatto'),
        ('✅', 'PRONTO', 'Clicca "Pronto"'),
        ('🔔', 'NOTIFICA', 'Sala avvisata'),
    ], accent=HEX_ORNG)
    spacer(doc, 8)

    step_row(doc, 1, 'Vedi un nuovo ordine (giallo)', 'Leggi i prodotti richiesti. Se hai dubbi sulle note, chiedi alla cassa', accent=HEX_ORNG)
    spacer(doc, 4)
    step_row(doc, 2, 'Clicca "In preparazione"', 'L\'ordine diventa blu — segnale che la cucina l\'ha preso in carico', accent=HEX_ORNG)
    spacer(doc, 4)
    step_row(doc, 3, 'Prepara i piatti', 'Segui l\'ordine di arrivo, salvo priorità decise internamente', accent=HEX_ORNG)
    spacer(doc, 4)
    step_row(doc, 4, 'Clicca "Pronto"', 'L\'ordine diventa verde. Il cliente/sala riceve notifica Telegram se configurata', accent=HEX_ORNG)
    spacer(doc, 4)
    step_row(doc, 5, 'L\'ordine scompare dal KDS', 'Dopo il ritiro da parte della sala, l\'ordine viene archiviato', accent=HEX_ORNG)
    spacer(doc, 8)

    info_box(doc, 'Non saltare lo step "In preparazione". '
             'Serve alla cassa per capire che l\'ordine è stato visto dalla cucina '
             'e non rischiare di inviarlo di nuovo.', style='warning')
    spacer(doc, 8)

    h2(doc, '4.4  Gestione ordini complessi')
    data_table(doc,
        ['Situazione', 'Cosa fare'],
        [
            ['Ordine con più piatti diversi',
             'Prepara tutto insieme per lo stesso cliente prima di segnare "pronto"'],
            ['Cliente ha aggiunto note speciali',
             'Le note appaiono sotto il prodotto in corsivo — leggile sempre'],
            ['Prodotto non disponibile',
             'Avvisa immediatamente la cassa via interfono/telefono — la cassa gestirà il cliente'],
            ['Ordine in ritardo',
             'Il KDS mostra il tempo trascorso in rosso dopo 15 minuti — prioritizza'],
            ['Schermo bloccato',
             'Ricarica la pagina (F5). Se il problema persiste, avvisa l\'Admin'],
        ],
        col_widths=[5.0, 12.6])
    spacer(doc, 8)

    h2(doc, '4.5  Notifiche Telegram alla cucina')
    body_para(doc, 'Se l\'Admin ha configurato il bot Telegram, la cucina riceve automaticamente:')
    spacer(doc, 4)

    data_table(doc,
        ['Evento', 'Notifica'],
        [
            ['Nuovo ordine',              '🛒 Nuovo ordine #123 — Mario Rossi: 1x Risotto, 2x Acqua'],
            ['Ordine urgente (ritardato)', '⚠️ Ordine #120 in attesa da 20 minuti!'],
            ['Annullamento ordine',       '❌ Ordine #121 ANNULLATO — Mario Rossi'],
        ],
        col_widths=[5.5, 12.1])


# ══════════════════════════════════════════════════════════════════════════════
# SEZIONE 5 — SALA
# ══════════════════════════════════════════════════════════════════════════════

def s_sala(doc):
    h1(doc, '5', 'Sala — Gestione Tavoli e Permanenza', '🪑')

    role_badge(doc, '🪑', 'Sala',
               'Il personale sala gestisce le prenotazioni dei tavoli, il check-in dei clienti '
               'e il monitoraggio del tempo di permanenza. Riceve avvisi Telegram quando '
               'un tavolo sta per superare il tempo massimo consentito.',
               HEX_TEAL)
    spacer(doc, 8)

    h2(doc, '5.1  Come funzionano le fasce orarie')
    body_para(doc, 'Il sistema di prenotazione tavoli è organizzato per FASCE ORARIE, '
              'non per singoli slot. L\'admin crea fasce come «11:25–12:30 con 30 min a seduta»; '
              'il sistema calcola automaticamente le sessioni disponibili: 11:25, 11:55, 12:25. '
              'I clienti prenotano un tavolo a una sessione specifica.')
    spacer(doc, 6)

    info_box(doc, 'Gli SLOT ORDINI (tab "Slot ordini" in Admin → Tavoli) sono SEPARATI '
             'dalle fasce orarie tavoli: regolano solo il ritiro del cibo ordinato, '
             'non la prenotazione dei posti a sedere.',
             style='warning')
    spacer(doc, 8)

    h2(doc, '5.2  Visualizzare la panoramica del giorno')
    step_row(doc, 1, 'Vai in Admin → Tavoli → tab Panoramica', 'Vedi tutte le fasce orarie del giorno corrente')
    spacer(doc, 4)
    step_row(doc, 2, 'Naviga tra i giorni', 'Usa le frecce ‹ › o il selettore data per vedere un altro giorno')
    spacer(doc, 4)
    step_row(doc, 3, 'Leggi i chip colorati', 'Verde = tavolo libero in quella sessione; rosso = occupato con il nome del cliente')
    spacer(doc, 8)

    h2(doc, '5.3  Check-in all\'arrivo del cliente')
    body_para(doc, 'Quando un cliente con prenotazione arriva fisicamente al locale, '
              'registra il suo check-in per avviare il conteggio del tempo di permanenza.')
    spacer(doc, 4)

    step_row(doc, 1, 'Trova la prenotazione in Panoramica o nella lista', 'Cerca il cliente per nome o per orario sessione')
    spacer(doc, 4)
    step_row(doc, 2, 'Clicca il pulsante check-in (icona porta)', 'Il sistema registra l\'orario esatto di arrivo del cliente')
    spacer(doc, 4)
    step_row(doc, 3, 'Il timer parte', 'Accanto alla prenotazione appare l\'orario di check-in')
    spacer(doc, 4)
    step_row(doc, 4, 'Accompagna il cliente al tavolo prenotato', 'Il numero tavolo è visibile sulla prenotazione')
    spacer(doc, 8)

    info_box(doc, 'Il check-in è fondamentale per far funzionare gli avvisi di tempo. '
             'Senza check-in, il timer non parte e non arriverà nessuna notifica Telegram.',
             style='warning')
    spacer(doc, 8)

    h2(doc, '5.4  Avvisi di tempo — Notifiche Telegram')
    body_para(doc, 'Quando un cliente è in sala da più di (durata fascia - 10 minuti), '
              'il sistema invia un avviso Telegram al canale sala/admin.')
    spacer(doc, 4)

    info_box_color(doc,
                   'Esempio: Fascia 11:25–12:30 con 30 min di durata.\n'
                   'Cliente fa check-in alle 11:25.\n'
                   'Alle 11:45 (dopo 20 min, cioè 10 min prima della scadenza) → avviso:\n'
                   '⏰ Tavolo 3 — Mario Rossi. Tempo rimasto: ~10 min.',
                   bg='FEF9E7', border=HEX_ORNG, icon='⏰')
    spacer(doc, 8)

    step_row(doc, 1, 'Ricevi la notifica Telegram', 'Arriva sul canale configurato dall\'Admin (gruppo sala/admin)')
    spacer(doc, 4)
    step_row(doc, 2, 'Avvicina il cliente con discrezione', 'Informa gentilmente il cliente che presto libererà il tavolo')
    spacer(doc, 4)
    step_row(doc, 3, 'Se il cliente ha ancora ordini da consumare', 'Dai priorità — non frettolizzare se ha appena ricevuto il piatto')
    spacer(doc, 4)
    step_row(doc, 4, 'Chiudi la prenotazione', 'Quando il cliente lascia, segna la prenotazione come "Completata" nella lista')
    spacer(doc, 8)

    h2(doc, '5.4  Configurare le durate per slot orario')
    body_para(doc, 'L\'Admin può impostare durate diverse per ogni fascia oraria. '
              'Esempio: slot 12:00 = 45 minuti, slot 13:00 = 30 minuti (flusso più veloce).')
    spacer(doc, 4)

    step_row(doc, 1, 'Vai in Admin → Slot Orari', 'Menu → Fasce Orarie')
    spacer(doc, 4)
    step_row(doc, 2, 'Clicca sull\'orario da modificare', 'Si apre il form di modifica')
    spacer(doc, 4)
    step_row(doc, 3, 'Imposta "Durata permanenza (min)"', 'Inserisci i minuti. Metti 0 per nessun limite di tempo')
    spacer(doc, 4)
    step_row(doc, 4, 'Salva', 'La nuova durata si applica alle prossime prenotazioni')
    spacer(doc, 8)

    h2(doc, '5.5  Polling avvisi tavoli')
    body_para(doc, 'La pagina KDS può essere configurata per controllare automaticamente '
              'ogni 60 secondi se ci sono tavoli con poco tempo rimasto. '
              'Questo avviene tramite l\'endpoint /admin/tavoli/ping-alerts.')
    spacer(doc, 4)

    info_box(doc, 'L\'endpoint di ping-alert è già integrato nella pagina KDS. '
             'Basta tenere aperta la pagina cucina/KDS su uno schermo — '
             'controlla automaticamente i tavoli e invia i Telegram necessari.', style='tip')
    spacer(doc, 8)

    data_table(doc,
        ['Stato tavolo', 'Tempo rimasto', 'Azione sistema'],
        [
            ['🟢 Tranquillo',   '> 15 minuti',       'Nessuna azione'],
            ['🟡 Attenzione',   '10-15 minuti',       'Telegram avviso preparazione'],
            ['🔴 Urgente',      '< 10 minuti',        'Telegram avviso liberazione'],
            ['⬛ Scaduto',      '0 o negativo',       'Telegram avviso immediato + check manuale'],
        ],
        col_widths=[3.5, 3.5, 10.6])


# ══════════════════════════════════════════════════════════════════════════════
# SEZIONE 6 — CLIENTE
# ══════════════════════════════════════════════════════════════════════════════

def s_cliente(doc):
    h1(doc, '6', 'Cliente — App e Auto-ordine', '👤')

    role_badge(doc, '👤', 'Cliente',
               'Il cliente usa l\'app web per ordinare in autonomia, gestire il suo wallet, '
               'accumulare punti fedeltà, prenotare un tavolo e votare il menu. '
               'Non serve scaricare niente: funziona direttamente dal browser dello smartphone.',
               HEX_PURPL)
    spacer(doc, 8)

    h2(doc, '6.1  Registrazione e primo accesso')
    step_row(doc, 1, 'Apri il browser sul telefono', 'Vai all\'URL del locale (es. https://pranzo.barcentrale.it)')
    spacer(doc, 4)
    step_row(doc, 2, 'Clicca "Registrati"', 'Inserisci nome, email e scegli una password sicura')
    spacer(doc, 4)
    step_row(doc, 3, 'Accedi', 'Inserisci email e password. Il sistema ricorda il login per 30 giorni')
    spacer(doc, 4)
    step_row(doc, 4, 'Opzionale: aggiungi al telefono', 'Tocca "Aggiungi alla schermata home" nel browser per averla come app')
    spacer(doc, 8)

    h2(doc, '6.2  Come ordinare dal menu')
    workflow_table(doc, [
        ('🍽️', 'Apri Menu', 'Sfoglia categorie'),
        ('➕', 'Aggiungi', 'Clicca sul prodotto'),
        ('🛒', 'Carrello', 'Rivedi ordine'),
        ('💳', 'Paga', 'Wallet o cassa'),
        ('⏳', 'Attendi', 'Notifica quando pronto'),
    ], accent=HEX_PURPL)
    spacer(doc, 8)

    step_row(doc, 1, 'Vai in Menu', 'Dal menu laterale o dalla home, tocca "Menu"')
    spacer(doc, 4)
    step_row(doc, 2, 'Sfoglia per categoria', 'Primo, Secondo, Contorno, Bevande, Dolci — tocca la categoria')
    spacer(doc, 4)
    step_row(doc, 3, 'Aggiungi al carrello', 'Tocca il prodotto → "+" per aggiungere. Ripeti per più prodotti')
    spacer(doc, 4)
    step_row(doc, 4, 'Vai al carrello', 'Tocca l\'icona carrello o vai in Ordina → Carrello')
    spacer(doc, 4)
    step_row(doc, 5, 'Scegli come pagare', 'Se hai saldo wallet: seleziona "Wallet". Altrimenti "Paga alla cassa"')
    spacer(doc, 4)
    step_row(doc, 6, 'Conferma l\'ordine', 'Tocca "Invia ordine". Ricevi conferma e numero ordine')
    spacer(doc, 4)
    step_row(doc, 7, 'Attendi la notifica', 'Telegram (se hai collegato il bot) o controlla "I miei ordini" nell\'app')
    spacer(doc, 8)

    info_box(doc, 'Per il pagamento con wallet, devi avere saldo sufficiente. '
             'Chiedi al cassiere di ricaricare il wallet o fallo tramite il tuo profilo (se disponibile il pagamento online).',
             style='tip')
    spacer(doc, 8)

    h2(doc, '6.3  Wallet e punti fedeltà')
    body_para(doc, 'Il wallet è il tuo portafoglio digitale nel locale. '
              'Puoi caricare credito in anticipo e pagare più velocemente. '
              'Ogni acquisto con wallet accumula punti fedeltà.')
    spacer(doc, 4)

    data_table(doc,
        ['Funzione', 'Come si usa', 'Vantaggi'],
        [
            ['Saldo wallet',         'Wallet & Fedeltà → Saldo attuale',  'Pagamenti rapidi senza contanti'],
            ['Storico transazioni',  'Wallet & Fedeltà → Movimenti',       'Tieni traccia di ogni spesa'],
            ['Punti fedeltà',        'Wallet & Fedeltà → I tuoi punti',    'Accumula e ottieni premi'],
            ['Ricarica wallet',      'Chiedi al cassiere o online',         'Ricarica per importi multipli'],
        ],
        col_widths=[4.0, 6.5, 7.1])
    spacer(doc, 8)

    h2(doc, '6.4  Prenotare un tavolo')
    step_row(doc, 1, 'Vai in Tavoli → Prenota Tavolo', 'Dal menu laterale')
    spacer(doc, 4)
    step_row(doc, 2, 'Scegli la data e lo slot orario', 'Sono mostrati solo gli slot con posti disponibili')
    spacer(doc, 4)
    step_row(doc, 3, 'Indica il numero di persone', 'Inserisci quante persone siete')
    spacer(doc, 4)
    step_row(doc, 4, 'Conferma prenotazione', 'Ricevi un codice di prenotazione e una notifica Telegram')
    spacer(doc, 4)
    step_row(doc, 5, 'All\'arrivo al locale', 'Mostra il codice alla sala o dichiara il tuo nome per il check-in')
    spacer(doc, 8)

    h2(doc, '6.5  Votare il menu (sondaggio)')
    body_para(doc, 'Il locale può aprire sondaggi per sapere cosa vorresti nel menu. '
              'La tua opinione influenza le scelte dell\'Admin!')
    spacer(doc, 4)

    step_row(doc, 1, 'Vai in "Vota il Menu"', 'Dal menu laterale cliente')
    spacer(doc, 4)
    step_row(doc, 2, 'Vedi i sondaggi aperti', 'Ogni sondaggio ha una domanda e più opzioni di risposta')
    spacer(doc, 4)
    step_row(doc, 3, 'Esprimi la tua preferenza', 'Clicca sull\'opzione preferita e conferma')
    spacer(doc, 4)
    step_row(doc, 4, 'Visualizza i risultati', 'Dopo il voto puoi vedere come stanno andando le preferenze')
    spacer(doc, 8)

    h2(doc, '6.6  I miei ordini — storico')
    body_para(doc, 'Trovi tutto lo storico dei tuoi ordini in Ordina → I Miei Ordini. '
              'Per ogni ordine puoi vedere: data, prodotti, importo pagato, stato.')
    spacer(doc, 4)

    info_box(doc, 'Se un ordine non è arrivato o c\'è un errore, '
             'mostra al cassiere il numero ordine visibile in "I miei ordini". '
             'Il numero ordine permette al cassiere di trovare e correggere il problema in pochi secondi.',
             style='tip')
    spacer(doc, 10)

    h2(doc, '6.7  Adesso al banco — ordine senza slot')
    body_para(doc, 'Se sei fisicamente al bancone e vuoi che il tuo ordine venga preparato subito, '
              'scegli "Adesso al banco" nel carrello invece di uno slot di ritiro.')
    spacer(doc, 6)

    step_row(doc, 1, 'Aggiungi prodotti al carrello', 'Componi l\'ordine normalmente dal menu')
    spacer(doc, 4)
    step_row(doc, 2, 'Vai al carrello', 'Tocca l\'icona carrello o vai in Ordina → Carrello')
    spacer(doc, 4)
    step_row(doc, 3, 'Seleziona "Adesso al banco"', 'Prima delle opzioni di slot, trovi un\'opzione radio "Adesso al banco" — selezionala')
    spacer(doc, 4)
    step_row(doc, 4, 'Conferma l\'ordine', 'Il tuo ordine viene inviato in cucina immediatamente, senza prenotare uno slot orario')
    spacer(doc, 6)

    info_box_color(doc,
                   'Il codice ordine generato con questa modalità include il tag BANCO: '
                   'QuickLunch-AAMMGG-BANCO-NNNN. Mostralo allo staff per il ritiro.',
                   bg='EBF5FB', border=HEX_TEAL, icon='ℹ️')
    spacer(doc, 10)

    h2(doc, '6.8  Paga al Banco — scanner QR')
    body_para(doc, 'Quando sei al bancone e lo staff ti mostra un QR generato dal Banco POS, '
              'puoi pagarlo direttamente dall\'app senza contanti e senza usare il wallet.')
    spacer(doc, 6)

    step_row(doc, 1, 'Vai nella tua Dashboard', 'Dalla home o dal menu laterale')
    spacer(doc, 4)
    step_row(doc, 2, 'Tocca "Paga al Banco"', 'Il pulsante si trova nella dashboard principale del cliente')
    spacer(doc, 4)
    step_row(doc, 3, 'Autorizza la fotocamera', 'Alla prima apertura il browser chiede il permesso per usare la fotocamera — consenti')
    spacer(doc, 4)
    step_row(doc, 4, 'Inquadra il QR dello staff', 'Punta la fotocamera sul QR mostrato dallo staff al bancone')
    spacer(doc, 4)
    step_row(doc, 5, 'Rivedi l\'importo e conferma', 'Vedi il totale da pagare e tocca "Conferma pagamento"')
    spacer(doc, 4)
    step_row(doc, 6, 'Pagamento completato', 'Lo schermo del banco si aggiorna mostrando "✓ Pagato da [Il tuo nome]"')
    spacer(doc, 8)

    info_box(doc, 'Il QR generato dallo staff ha una validità di 10 minuti. '
             'Se scade prima che tu riesca a scansionarlo, chiedi allo staff di generarne uno nuovo.', style='warning')


# ══════════════════════════════════════════════════════════════════════════════
# SEZIONE 7 — DIPENDENTE AZIENDALE
# ══════════════════════════════════════════════════════════════════════════════

def s_dipendente(doc):
    h1(doc, '7', 'Dipendente Aziendale — Pasto Fisso Convenzionato', '🏭')

    role_badge(doc, '🏭', 'Dipendente Aziendale',
               'Sei un dipendente di un\'azienda convenzionata con questo locale. '
               'L\'azienda ha concordato un pasto completo a prezzo fisso ogni giorno. '
               'Il tuo compito è semplicissimo: prenotare il pasto del giorno e ritirarlo.',
               '5D6D7E')
    spacer(doc, 8)

    info_box_color(doc,
                   'Come funziona in breve:\n'
                   '1. L\'amministratore del locale crea ogni mattina il "pasto del giorno" per la tua azienda\n'
                   '2. Tu lo prenoti scegliendo uno slot orario\n'
                   '3. Arrivi al locale nello slot scelto e ritiri il pasto\n'
                   '4. Non paghi nulla: paga direttamente la tua azienda a fine mese',
                   bg='EBF5FB', border=HEX_TEAL, icon='🏭')
    spacer(doc, 10)

    h2(doc, '7.1  Primo accesso come dipendente aziendale')
    step_row(doc, 1, 'Registrati come cliente normale', 'Vai all\'URL del locale, clicca "Registrati" e crea il tuo account')
    spacer(doc, 4)
    step_row(doc, 2, 'Comunica il tuo username all\'Admin', 'L\'Admin deve associarti alla tua azienda. Invia il tuo username o email')
    spacer(doc, 4)
    step_row(doc, 3, 'Attendi l\'associazione', 'L\'Admin ti aggiunge alla convenzione aziendale. Di solito avviene entro poche ore')
    spacer(doc, 4)
    step_row(doc, 4, 'Comparirà "Pasto Aziendale" nel menu', 'La voce appare nel menu laterale solo per i dipendenti convenzionati')
    spacer(doc, 8)

    h2(doc, '7.2  Prenotare il pasto del giorno')
    workflow_table(doc, [
        ('📱', 'Apri app', 'Accedi con le tue credenziali'),
        ('🍽️', 'Pasto Aziendale', 'Menu laterale → Pasto Aziendale'),
        ('👁️', 'Vedi menu', 'Il pasto di oggi è già pronto'),
        ('🕐', 'Scegli slot', 'Seleziona l\'orario che preferisci'),
        ('✅', 'Prenota', 'Conferma la prenotazione'),
    ], accent=HEX_TEAL)
    spacer(doc, 8)

    step_row(doc, 1, 'Vai in "Pasto Aziendale"', 'Menu laterale dell\'app → icona edificio viola "Pasto Aziendale"')
    spacer(doc, 4)
    step_row(doc, 2, 'Leggi il pasto del giorno', 'Trovi il nome del piatto, la descrizione e gli eventuali allergeni')
    spacer(doc, 4)
    step_row(doc, 3, 'Controlla i posti rimasti', 'In alto a destra della scheda compare "X posti rimasti". Se è 0, posti esauriti')
    spacer(doc, 4)
    step_row(doc, 4, 'Scegli lo slot orario', 'Dal menu a tendina seleziona quando vuoi venire a ritirare il pasto')
    spacer(doc, 4)
    step_row(doc, 5, 'Clicca "Prenota il mio pasto"', 'La prenotazione è confermata. Ricevi una notifica Telegram con il riepilogo')
    spacer(doc, 4)
    step_row(doc, 6, 'Arriva al locale', 'Presentati nello slot scelto. Dichiara il tuo nome — il cassiere trova la tua prenotazione')
    spacer(doc, 8)

    info_box(doc, 'Puoi prenotare una sola volta al giorno. '
             'Se vuoi cambiare orario, annulla la prenotazione e rifalla scegliendo un altro slot. '
             'Puoi annullare fino a un\'ora prima dello slot scelto.', style='tip')
    spacer(doc, 8)

    h2(doc, '7.3  Annullare una prenotazione')
    step_row(doc, 1, 'Vai in "Pasto Aziendale"', 'La tua prenotazione attiva è mostrata con un badge verde')
    spacer(doc, 4)
    step_row(doc, 2, 'Clicca "Annulla prenotazione"', 'Bottone rosso sotto la scheda prenotazione')
    spacer(doc, 4)
    step_row(doc, 3, 'Conferma l\'annullamento', 'Un popup chiede conferma — clicca OK')
    spacer(doc, 4)
    step_row(doc, 4, 'Il posto si libera', 'Il posto torna disponibile per un altro collega')
    spacer(doc, 8)

    h2(doc, '7.4  Cosa vedere nella schermata Pasto Aziendale')
    data_table(doc,
        ['Elemento', 'Significato'],
        [
            ['Nome azienda (in alto)',      'Conferma che sei associato alla convenzione corretta'],
            ['Banner del pasto',             'Il nome e la descrizione del pasto di oggi'],
            ['Badge posti rimasti',          'Verde = disponibile, Giallo = quasi esaurito, Rosso = esaurito'],
            ['Badge stato prenotazione',     'Verde "Prenotato", Arancio "Consumato", Grigio "Annullato"'],
            ['Slot orario prenotato',        'L\'orario che hai scelto — ricordati di rispettarlo'],
            ['"Nessun pasto disponibile"',   'L\'Admin non ha ancora pubblicato il menu oggi — ricontrolla più tardi'],
        ],
        col_widths=[5.0, 12.6])
    spacer(doc, 8)

    info_box(doc, 'Se non vedi "Pasto Aziendale" nel menu, significa che non sei ancora '
             'associato a nessuna convenzione. Contatta l\'amministratore del locale '
             'per farti aggiungere.', style='warning')
    spacer(doc, 8)

    h2(doc, '7.5  FAQ Dipendente Aziendale')
    data_table(doc,
        ['Domanda', 'Risposta'],
        [
            ['Posso ordinare anche dal menu normale?',
             'Sì, il pasto aziendale è aggiuntivo. Puoi comunque usare il menu standard e pagare normalmente.'],
            ['Cosa succede se non mi presento?',
             'La prenotazione rimane come "prenotata". Nessuna penale, ma il posto è andato perso.'],
            ['Il prezzo varia ogni giorno?',
             'No, il prezzo è fisso per contratto. Può cambiare solo se l\'azienda rinnova la convenzione.'],
            ['Posso prenotare per un collega?',
             'No, ogni dipendente prenota solo per sé stesso. Ogni account è personale.'],
            ['Ho dimenticato la password',
             'Clicca "Password dimenticata?" nella pagina di login oppure contatta l\'Admin del locale.'],
        ],
        col_widths=[6.2, 11.4])


# ══════════════════════════════════════════════════════════════════════════════
# APPENDICE — Riepilogo ruoli e permessi
# ══════════════════════════════════════════════════════════════════════════════

def s_appendice(doc):
    h1(doc, 'A', 'Appendice — Riepilogo Ruoli e Flussi', '📎')

    h2(doc, 'A.1  Matrice permessi per ruolo')
    data_table(doc,
        ['Funzione', '👑\nSuper', '🏢\nAdmin', '💳\nCassa', '🍳\nKDS', '🪑\nSala', '👤\nCliente', '🏭\nDip.'],
        [
            ['Login area Admin',         '✅', '✅', '✅', '✅', '✅', '❌', '❌'],
            ['Gestione prodotti menu',   '✅', '✅', '❌', '❌', '❌', '❌', '❌'],
            ['Creazione ordini',         '✅', '✅', '✅', '❌', '❌', '✅', '❌'],
            ['Incasso pagamenti',        '✅', '✅', '✅', '❌', '❌', '❌', '❌'],
            ['Stato ordine (KDS)',        '✅', '✅', '❌', '✅', '❌', '❌', '❌'],
            ['Prenotazioni tavoli',      '✅', '✅', '❌', '❌', '✅', '✅', '❌'],
            ['Check-in tavolo',          '✅', '✅', '❌', '❌', '✅', '❌', '❌'],
            ['Wallet clienti',           '✅', '✅', '✅', '❌', '❌', '✅', '❌'],
            ['Magazzino consumabili',    '✅', '✅', '❌', '❌', '❌', '❌', '❌'],
            ['Convenzioni aziendali',    '✅', '✅', '❌', '❌', '❌', '❌', '❌'],
            ['Pasto aziendale fisso',    '✅', '✅', '❌', '❌', '❌', '❌', '✅'],
            ['Report e statistiche',     '✅', '✅', '❌', '❌', '❌', '❌', '❌'],
            ['Voto menu (sondaggio)',     '❌', '✅', '❌', '❌', '❌', '✅', '❌'],
            ['Banco POS (genera QR)',     '✅', '✅', '✅', '❌', '❌', '❌', '❌'],
            ['Paga al Banco (scan QR)',   '❌', '❌', '❌', '❌', '❌', '✅', '✅'],
        ],
        col_widths=[5.0, 1.8, 1.8, 1.8, 1.8, 1.8, 2.0, 2.6])
    spacer(doc, 10)

    h2(doc, 'A.2  Flusso giornaliero tipo — bar/mensa')
    workflow_table(doc, [
        ('🌅', 'Apertura', 'Admin: crea pasto aziendale, verifica stock'),
        ('💳', 'Pre-pranzo', 'Cassa: ordini walk-in, ricariche wallet'),
        ('🍳', 'Servizio', 'KDS: gestisce ordini, sala: check-in tavoli'),
        ('⏰', 'Avvisi', 'Telegram: tavoli in scadenza, stock basso'),
        ('📊', 'Chiusura', 'Admin: report giornaliero, aggiorna stock'),
    ])
    spacer(doc, 10)

    h2(doc, 'A.3  Contatti e supporto')
    body_para(doc, 'Per problemi tecnici o richieste di assistenza, contatta il supporto QuickLunch:')
    spacer(doc, 4)

    data_table(doc,
        ['Canale', 'Quando usarlo', 'Tempo risposta'],
        [
            ['Email supporto',    'Bug, richieste funzionalità, account bloccati', '24 ore lavorative'],
            ['Admin del locale',  'Password dimenticata, errori ordini, wallet',   'Immediato (di persona)'],
            ['Telegram bot',      'Notifiche automatiche — non risponde',           'N/A'],
        ],
        col_widths=[4.0, 8.5, 5.1])
    spacer(doc, 8)

    info_box(doc, 'Per qualsiasi problema operativo durante il servizio, il primo contatto '
             'deve sempre essere l\'Admin Tenant del proprio locale. '
             'Solo per problemi tecnici gravi si escalate al supporto centrale.', style='tip')


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main():
    doc = Document()
    set_document_defaults(doc)

    # ── Cover ──
    build_cover(doc)
    _page_break(doc)

    # ── Indice ──
    build_toc(doc)
    _page_break(doc)

    # ── Sezioni ──
    s_super_admin(doc)
    _page_break(doc)

    s_admin_tenant(doc)
    _page_break(doc)

    s_cassiere(doc)
    _page_break(doc)

    s_cucina(doc)
    _page_break(doc)

    s_sala(doc)
    _page_break(doc)

    s_cliente(doc)
    _page_break(doc)

    s_dipendente(doc)
    _page_break(doc)

    s_appendice(doc)

    doc.save(OUT)
    print(f'OK  Guida utente salvata in: {OUT}')


if __name__ == '__main__':
    main()
