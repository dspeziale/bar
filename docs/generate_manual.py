#!/usr/bin/env python3
"""Genera docs/manuale_proprietario.docx con PT Sans Narrow."""

import os
from docx import Document
from docx.shared import Pt, Cm, RGBColor, Emu, Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_ALIGN_VERTICAL, WD_TABLE_ALIGNMENT
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

# ── Palette ──────────────────────────────────────────────────────────────────
RED    = RGBColor(0xe9, 0x45, 0x60)
NAVY   = RGBColor(0x0f, 0x34, 0x60)
DARK   = RGBColor(0x16, 0x21, 0x3e)
DGRAY  = RGBColor(0x34, 0x3a, 0x40)
GRAY   = RGBColor(0x6c, 0x75, 0x7d)
WHITE  = RGBColor(0xff, 0xff, 0xff)

HEX_RED   = 'E94560'
HEX_NAVY  = '0F3460'
HEX_DARK  = '16213E'
HEX_LIGHT = 'F8F9FA'
HEX_WHITE = 'FFFFFF'

FONT = 'PT Sans Narrow'
OUT  = os.path.join(os.path.dirname(__file__), 'manuale_proprietario.docx')


# ── XML helpers ───────────────────────────────────────────────────────────────

def _cell_shd(cell, fill):
    tc = cell._tc
    tcPr = tc.get_or_add_tcPr()
    # remove old shd if present
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


def _page_break(doc):
    p = doc.add_paragraph()
    run = p.add_run()
    run.add_break(__import__('docx.enum.text', fromlist=['WD_BREAK'])
                  .WD_BREAK.PAGE)
    p.paragraph_format.space_after = Pt(0)
    p.paragraph_format.space_before = Pt(0)


def _no_borders(table):
    tbl = table._tbl
    tblPr = tbl.find(qn('w:tblPr'))
    if tblPr is None:
        tblPr = OxmlElement('w:tblPr')
        tbl.insert(0, tblPr)
    for old in tblPr.findall(qn('w:tblBorders')):
        tblPr.remove(old)
    bdr = OxmlElement('w:tblBorders')
    for side in ('top','left','bottom','right','insideH','insideV'):
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


def _run_font(run, size=11, bold=False, color=None, italic=False, font=FONT):
    run.font.name  = font
    run.font.size  = Pt(size)
    run.font.bold  = bold
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


# ── Document helpers ──────────────────────────────────────────────────────────

def body_para(doc, text='', color=None, size=11, bold=False,
              align=WD_ALIGN_PARAGRAPH.LEFT, after=6, before=0):
    p = doc.add_paragraph()
    p.alignment = align
    _p_spacing(p, before=before, after=after)
    if text:
        run = p.add_run(text)
        _run_font(run, size=size, bold=bold, color=color or DGRAY)
    return p


def h1(doc, number, title, icon=''):
    """Heading sezione — grande con bordo inferiore rosso."""
    spacer = doc.add_paragraph()
    _p_spacing(spacer, before=0, after=2)

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.LEFT
    _p_spacing(p, before=10, after=4)

    # Label sezione piccolo in rosso
    label = p.add_run(f'SEZIONE {number}   ')
    _run_font(label, size=8, bold=True, color=RED)

    # Icona + titolo
    if icon:
        ic = p.add_run(icon + '  ')
        _run_font(ic, size=18)
    run = p.add_run(title)
    _run_font(run, size=19, bold=True, color=NAVY)

    _para_border(p, bottom_color=HEX_RED, bottom_sz='8')
    return p


def h2(doc, text):
    """Sottotitolo sezione."""
    p = doc.add_paragraph()
    _p_spacing(p, before=12, after=4)
    run = p.add_run(text)
    _run_font(run, size=13, bold=True, color=DARK)
    return p


def info_box(doc, text, style='tip', label=None):
    """Riquadro colorato con bordo sinistro."""
    BG = {'tip': 'EBF5FB', 'warning': 'FEF0F0', 'success': 'EAFAF1'}
    BD = {'tip': HEX_NAVY, 'warning': HEX_RED, 'success': '27AE60'}
    IC = {'tip': '💡', 'warning': '⚠️', 'success': '✅'}

    bg = BG.get(style, 'EBF5FB')
    bd = BD.get(style, HEX_NAVY)
    ic = IC.get(style, '💡')

    tbl = doc.add_table(rows=1, cols=1)
    _no_borders(tbl)
    _table_width(tbl, 16.5)
    cell = tbl.rows[0].cells[0]
    _cell_shd(cell, bg)
    _cell_border(cell, top='FFFFFF', bottom='FFFFFF', right='FFFFFF', left=bd)
    _cell_margins(cell, top=80, bottom=80, left=120, right=80)

    p = cell.paragraphs[0]
    _p_spacing(p, before=0, after=0)

    prefix_text = f'{ic}  '
    if label:
        prefix_text += f'{label}  '
    prefix = p.add_run(prefix_text)
    _run_font(prefix, size=10, bold=bool(label),
              color=RGBColor(*bytes.fromhex(bd)))

    run = p.add_run(text)
    _run_font(run, size=10, color=DARK)

    doc.add_paragraph().paragraph_format.space_after = Pt(8)
    return tbl


def step_row(doc, num, title, text):
    """Passo numerato: pallino colorato | contenuto."""
    tbl = doc.add_table(rows=1, cols=2)
    _no_borders(tbl)
    _table_width(tbl, 16.5)

    # ── Numero ──
    nc = tbl.rows[0].cells[0]
    _set_col_width(tbl, 0, 1.1)
    _cell_shd(nc, HEX_RED)
    _cell_margins(nc, top=60, bottom=60, left=40, right=40)
    _cell_vAlign(nc, 'center')
    pn = nc.paragraphs[0]
    pn.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _p_spacing(pn, before=0, after=0)
    rn = pn.add_run(str(num))
    _run_font(rn, size=14, bold=True, color=WHITE)

    # ── Contenuto ──
    cc = tbl.rows[0].cells[1]
    _cell_shd(cc, 'F0F4F8')
    _cell_margins(cc, top=60, bottom=60, left=100, right=80)
    pt = cc.paragraphs[0]
    _p_spacing(pt, before=0, after=3)
    rt = pt.add_run(title + '\n')
    _run_font(rt, size=11, bold=True, color=DARK)
    rb = pt.add_run(text)
    _run_font(rb, size=10, color=GRAY)

    doc.add_paragraph().paragraph_format.space_after = Pt(4)
    return tbl


def data_table(doc, headers, rows, col_widths=None):
    """Tabella dati con header navy."""
    ncols = len(headers)
    tbl = doc.add_table(rows=1 + len(rows), cols=ncols)
    _table_width(tbl, 16.5)

    # header
    hr = tbl.rows[0]
    for i, h in enumerate(headers):
        c = hr.cells[i]
        _cell_shd(c, HEX_NAVY)
        _cell_border(c)
        _cell_margins(c, top=60, bottom=60, left=80, right=80)
        p = c.paragraphs[0]
        _p_spacing(p, before=0, after=0)
        r = p.add_run(h)
        _run_font(r, size=10, bold=True, color=WHITE)
    if col_widths:
        for i, w in enumerate(col_widths):
            _set_col_width(tbl, i, w)

    # data
    for ri, row_data in enumerate(rows):
        bg = HEX_WHITE if ri % 2 == 0 else 'F8F9FA'
        dr = tbl.rows[ri + 1]
        for ci, val in enumerate(row_data):
            c = dr.cells[ci]
            _cell_shd(c, bg)
            _cell_border(c, bottom='DEE2E6')
            _cell_margins(c, top=50, bottom=50, left=80, right=80)
            p = c.paragraphs[0]
            _p_spacing(p, before=0, after=0)
            bold = (ci == 0)
            r = p.add_run(val)
            _run_font(r, size=10, bold=bold, color=DARK if bold else GRAY)

    doc.add_paragraph().paragraph_format.space_after = Pt(8)
    return tbl


def cred_box(doc, title, rows):
    """Box credenziali su sfondo scuro."""
    tbl = doc.add_table(rows=1 + len(rows), cols=2)
    _no_borders(tbl)
    _table_width(tbl, 16.5)
    _set_col_width(tbl, 0, 4.5)
    _set_col_width(tbl, 1, 12.0)

    # titolo su riga merger
    title_cell = tbl.rows[0].cells[0].merge(tbl.rows[0].cells[1])
    _cell_shd(title_cell, HEX_DARK)
    _cell_margins(title_cell, top=80, bottom=60, left=100, right=100)
    pt = title_cell.paragraphs[0]
    _p_spacing(pt, before=0, after=0)
    rt = pt.add_run('🔑  ' + title)
    _run_font(rt, size=10, bold=True, color=RED)

    for ri, (key, val, highlight) in enumerate(rows):
        row = tbl.rows[ri + 1]
        for ci in range(2):
            _cell_shd(row.cells[ci], '1A1A2E' if ri % 2 == 0 else HEX_DARK)
            _cell_margins(row.cells[ci], top=50, bottom=50, left=100, right=100)

        pk = row.cells[0].paragraphs[0]
        _p_spacing(pk, before=0, after=0)
        _run_font(pk.add_run(key), size=10,
                  color=RGBColor(0x90, 0xa8, 0xbe))

        pv = row.cells[1].paragraphs[0]
        _p_spacing(pv, before=0, after=0)
        vc = RGBColor(0xff, 0xd7, 0x00) if highlight else WHITE
        _run_font(pv.add_run(val), size=10, bold=highlight, color=vc)

    doc.add_paragraph().paragraph_format.space_after = Pt(10)
    return tbl


def role_table(doc, roles):
    """Tabella ruoli: badge colorato | permessi."""
    tbl = doc.add_table(rows=len(roles), cols=2)
    _no_borders(tbl)
    _table_width(tbl, 16.5)
    _set_col_width(tbl, 0, 4.0)
    _set_col_width(tbl, 1, 12.5)

    for ri, (badge_bg, badge_txt, name, perms) in enumerate(roles):
        row = tbl.rows[ri]

        # badge cella
        bc = row.cells[0]
        _cell_shd(bc, badge_bg)
        _cell_margins(bc, top=80, bottom=80, left=100, right=60)
        _cell_vAlign(bc, 'center')
        pb = bc.paragraphs[0]
        pb.alignment = WD_ALIGN_PARAGRAPH.CENTER
        _p_spacing(pb, before=0, after=0)
        _run_font(pb.add_run(name), size=11, bold=True,
                  color=RGBColor(*bytes.fromhex(badge_txt)))

        # permessi cella
        pc = row.cells[1]
        _cell_shd(pc, HEX_WHITE if ri % 2 == 0 else 'F8F9FA')
        _cell_margins(pc, top=80, bottom=80, left=100, right=80)
        pp = pc.paragraphs[0]
        _p_spacing(pp, before=0, after=0)
        _run_font(pp.add_run(perms), size=10, color=GRAY)

    doc.add_paragraph().paragraph_format.space_after = Pt(8)
    return tbl


def workflow_table(doc, steps):
    """Flusso orizzontale di step."""
    ncols = len(steps)
    tbl = doc.add_table(rows=1, cols=ncols)
    _table_width(tbl, 16.5)

    for i, (icon, title, desc) in enumerate(steps):
        c = tbl.rows[0].cells[i]
        bg = HEX_NAVY if i % 2 == 0 else '1A2E50'
        _cell_shd(c, bg)
        _cell_border(c, right='16213E')
        _cell_margins(c, top=100, bottom=100, left=80, right=80)

        p = c.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        _p_spacing(p, before=0, after=4)
        _run_font(p.add_run(icon + '\n'), size=18)
        _run_font(p.add_run(title + '\n'), size=10, bold=True, color=WHITE)
        _run_font(p.add_run(desc), size=9, color=RGBColor(0xb0, 0xc4, 0xd8))

    doc.add_paragraph().paragraph_format.space_after = Pt(8)
    return tbl


# ── Cover ─────────────────────────────────────────────────────────────────────

def build_cover(doc):
    # Impostazioni margini minimi per la cover
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    # Tabella che copre tutta la pagina: 3 righe (top spacer, content, bottom spacer)
    tbl = doc.add_table(rows=3, cols=1)
    _no_borders(tbl)
    _table_width(tbl, 21.0)

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

    _row_height(tbl.rows[0], 5.0)
    _row_height(tbl.rows[1], 17.5)
    _row_height(tbl.rows[2], 5.0)

    for row in tbl.rows:
        _cell_shd(row.cells[0], HEX_DARK)
        _cell_margins(row.cells[0], top=0, bottom=0, left=0, right=0)

    # ── Riga contenuto ──
    cc = tbl.rows[1].cells[0]
    _cell_shd(cc, HEX_DARK)
    _cell_margins(cc, top=100, bottom=100, left=300, right=300)
    _cell_vAlign(cc, 'center')

    def cp(text='', size=11, bold=False, color=WHITE, align=WD_ALIGN_PARAGRAPH.CENTER, after=10):
        p = cc.add_paragraph()
        p.alignment = align
        _p_spacing(p, before=0, after=after)
        if text:
            r = p.add_run(text)
            _run_font(r, size=size, bold=bold, color=color)
        return p

    # prima del contenuto c'è già un paragrafo vuoto nella cella
    p0 = cc.paragraphs[0]
    p0.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _p_spacing(p0, before=0, after=20)
    r0 = p0.add_run('🍽️')
    _run_font(r0, size=54, color=WHITE)

    cp('BSR',    size=52, bold=True, color=RED,   after=0)
    cp('PRANZO', size=52, bold=True, color=WHITE, after=16)
    cp('Sistema di gestione per bar, mense e caffetterie',
       size=14, color=RGBColor(0xa0, 0xb8, 0xd0), after=32)

    # Feature pills come elenco centrato
    features = ['📦 Ordini & Cucina', '💳 Wallet Digitale', '⭐ Fidelizzazione',
                '🪑 Prenotazione Tavoli', '📊 Report & Statistiche', '📱 Notifiche Telegram']
    pf = cc.add_paragraph()
    pf.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _p_spacing(pf, before=0, after=32)
    for i, feat in enumerate(features):
        r = pf.add_run(feat)
        _run_font(r, size=11, color=RGBColor(0xc8, 0xd8, 0xe8))
        if i < len(features) - 1:
            sep = pf.add_run('   ·   ')
            _run_font(sep, size=11, color=RGBColor(0x40, 0x55, 0x70))

    cp('Manuale del Proprietario  ·  Versione 2.0  ·  Giugno 2026',
       size=9, color=RGBColor(0x40, 0x55, 0x70), after=0)

    _page_break(doc)


# ── Sezioni ───────────────────────────────────────────────────────────────────

def build_toc(doc):
    p = doc.add_paragraph()
    _p_spacing(p, before=0, after=12)
    r = p.add_run('Indice dei contenuti')
    _run_font(r, size=22, bold=True, color=NAVY)
    _para_border(p, bottom_color=HEX_RED, bottom_sz='8')

    toc_items = [
        ('1',  '🍽️',  "Cos'è BSR Pranzo"),
        ('2',  '⚡',  'Funzionalità principali'),
        ('3',  '🚀',  'Come iniziare'),
        ('4',  '📋',  'Gestione ordini'),
        ('5',  '🍕',  'Menu e prodotti'),
        ('6',  '🥪',  'Panino & Insalata builder'),
        ('7',  '💳',  'Wallet digitale e fidelizzazione'),
        ('8',  '🪑',  'Tavoli e prenotazioni'),
        ('9',  '👥',  'Personale e clienti'),
        ('10', '🔐',  'Ruoli e permessi'),
        ('11', '📣',  'Notifiche e sondaggi'),
        ('12', '📊',  'Report e statistiche'),
        ('13', '🏬',  'Multi-sede (Multi-tenant)'),
        ('14', '❓',  'Domande frequenti'),
        ('15', '🔑',  'Credenziali di accesso'),
    ]

    tbl = doc.add_table(rows=len(toc_items), cols=2)
    _no_borders(tbl)
    _table_width(tbl, 16.5)
    _set_col_width(tbl, 0, 1.0)
    _set_col_width(tbl, 1, 15.5)

    for ri, (num, icon, title) in enumerate(toc_items):
        bg = HEX_WHITE if ri % 2 == 0 else 'F0F4F8'
        row = tbl.rows[ri]

        nc = row.cells[0]
        _cell_shd(nc, HEX_RED)
        _cell_margins(nc, top=50, bottom=50, left=60, right=60)
        pn = nc.paragraphs[0]
        pn.alignment = WD_ALIGN_PARAGRAPH.CENTER
        _p_spacing(pn, before=0, after=0)
        _run_font(pn.add_run(num), size=10, bold=True, color=WHITE)

        tc = row.cells[1]
        _cell_shd(tc, bg)
        _cell_margins(tc, top=50, bottom=50, left=100, right=60)
        pt = tc.paragraphs[0]
        _p_spacing(pt, before=0, after=0)
        _run_font(pt.add_run(icon + '  '), size=10)
        _run_font(pt.add_run(title), size=11, bold=False, color=NAVY)

    doc.add_paragraph().paragraph_format.space_after = Pt(6)
    _page_break(doc)


def s01(doc):
    h1(doc, 1, "Cos'è BSR Pranzo", '🍽️')
    body_para(doc,
        "BSR Pranzo è una piattaforma web completa progettata per semplificare la gestione "
        "quotidiana di bar, mense aziendali e caffetterie. Funziona direttamente dal browser — "
        "senza installazioni, senza app da aggiornare — ed è accessibile da qualsiasi dispositivo: "
        "computer, tablet o smartphone.")
    body_para(doc,
        "I clienti possono sfogliare il menu, comporre il proprio pasto su misura e preordinare "
        "con anticipo scegliendo lo slot orario di ritiro. Il personale riceve gli ordini in tempo "
        "reale e gestisce la cucina da un pannello dedicato. Il proprietario ha visibilità completa "
        "su incassi, prodotti più venduti e clienti fidelizzati.")
    info_box(doc,
        "Il sistema elimina il listino cartaceo, le ordinazioni verbali e le incomprensioni: "
        "ogni ordine è digitale, tracciato e confermato automaticamente.",
        style='success', label='Zero carta, zero code.')

    h2(doc, 'A chi è rivolto')
    data_table(doc,
        ['Tipo di attività', 'Caso d\'uso principale'],
        [
            ['🏢 Bar aziendale / Mensa',
             'Gestione turni pranzo, slot orari, preordini del mattino, wallet prepagato'],
            ['☕ Caffetteria / Tavola Calda',
             'Ordini veloci al banco, panini personalizzati, fidelizzazione con punti e premi'],
            ['🏬 Catena multi-sede',
             'Ogni punto vendita indipendente con menu, clienti e staff separati'],
        ],
        col_widths=[5.5, 11.0])


def s02(doc):
    h1(doc, 2, 'Funzionalità principali', '⚡')
    features = [
        ('📋', 'Ordini online',
         'I clienti ordinano da telefono o PC, scelgono lo slot orario e ricevono conferma immediata.'),
        ('👨‍🍳', 'Cucina / KDS',
         'Pannello cucina dedicato con ordini per slot, avanzamento stato in un clic.'),
        ('🥪', 'Builder personalizzato',
         'Il cliente compone panino o insalata ingrediente per ingrediente. Prezzi calcolati in automatico.'),
        ('💳', 'Wallet digitale',
         'Ogni cliente ha un portafoglio prepagato. Ricarica in pochi secondi dal pannello admin.'),
        ('⭐', 'Punti fedeltà',
         'Accumulo automatico a ogni acquisto. Soglia personalizzabile di riscatto in buono sconto.'),
        ('🪑', 'Prenotazione tavoli',
         'I clienti prenotano il posto con slot e coperti. Vista disponibilità real-time.'),
        ('📦', 'Stock giornaliero',
         "Imposta le quantità disponibili ogni mattina. Quando finiscono, il prodotto si disattiva da solo."),
        ('📊', 'Report e statistiche',
         'Incasso degli ultimi 30 giorni, prodotti più venduti, andamento giornaliero in grafici.'),
        ('📣', 'Comunicazioni',
         'Notifiche Telegram o email a tutti gli utenti con un clic. Sondaggi interattivi.'),
        ('👤', 'Gestione clienti',
         'Anagrafica completa: nome, contatti, data di nascita, indirizzo, Telegram Chat ID.'),
        ('🔐', 'Ruoli e permessi',
         'Ogni membro del personale vede solo ciò che gli compete: cassiere, cuoco, manager, admin.'),
        ('🔑', 'Accesso Google',
         'I clienti possono registrarsi e accedere con il loro account Google, senza password.'),
    ]
    data_table(doc,
        ['', 'Funzione', 'Descrizione'],
        [(ic, fn, desc) for ic, fn, desc in features],
        col_widths=[0.8, 3.7, 12.0])


def s03(doc):
    h1(doc, 3, 'Come iniziare', '🚀')
    body_para(doc,
        "Per attivare il sistema nel proprio locale bastano pochi passaggi, "
        "eseguibili tutti dal pannello admin senza bisogno di assistenza tecnica.")

    steps = [
        ('Accedere come amministratore',
         'Apri il link del sistema e accedi con le credenziali admin. '
         'Le credenziali iniziali sono nella sezione 15 di questo manuale. '
         'Cambia la password al primo accesso.'),
        ('Crea le categorie del menu',
         'Vai su Admin → Prodotti → Categorie. Aggiungi le macro-categorie del tuo menu '
         '(es. Panini, Primi, Dolci, Bevande). Assegna icona e colore a ognuna.'),
        ('Inserisci i prodotti',
         'Vai su Admin → Prodotti. Per ogni voce inserisci nome, descrizione, prezzo e '
         'quantità giornaliera disponibile. Puoi attivare e disattivare ogni prodotto in qualsiasi momento.'),
        ('Configura gli slot orari',
         'Vai su Admin → Slot orari. Gli slot determinano quando i clienti possono ritirare '
         '(es. 12:00 – 12:15 – 12:30…). Imposta la capienza massima per fascia oraria.'),
        ('Aggiungi il personale',
         'Vai su Admin → Persone → Personale. Crea un account per ogni dipendente e assegna '
         'il ruolo corretto (cassiere, cuoco, manager). Ognuno vedrà solo le sezioni di sua competenza.'),
        ('Condividi il link ai clienti',
         'Il link di registrazione è nella forma /t/slug-locale/register. '
         'Trovalo in Admin → Tenant. Metti un QR code sul banco o sui tavoli per registrazioni veloci.'),
    ]
    for i, (title, text) in enumerate(steps, 1):
        step_row(doc, i, title, text)

    info_box(doc,
        "Stampa o incornicia il QR code del link di registrazione e mettilo sul banco o sui tavoli. "
        "I clienti si registrano in 30 secondi con il cellulare.",
        style='tip', label='Suggerimento:')


def s04(doc):
    h1(doc, 4, 'Gestione ordini', '📋')
    h2(doc, 'Flusso di un ordine')
    workflow_table(doc, [
        ('📱', 'Cliente ordina', 'Sceglie prodotti e slot dal proprio dispositivo'),
        ('💳', 'Pagamento',      'Il costo scala dal wallet automaticamente'),
        ('👨‍🍳', 'Cucina',         'L\'ordine appare nel pannello KDS'),
        ('🔔', 'Pronto',         'Lo stato passa a "Pronto" per il ritiro'),
        ('✅', 'Completato',     'Il cassiere segna consegnato, punti accreditati'),
    ])

    h2(doc, 'Pannello Cucina (KDS)')
    body_para(doc,
        "Il pannello cucina (Admin → Cucina / KDS) mostra gli ordini del giorno divisi "
        "in tre colonne: Da preparare, In preparazione e Pronti. Con un clic il cuoco "
        "fa avanzare ogni ordine. Non serve stampante termica: il display basta da solo.")

    h2(doc, 'Annullamento e rimborso')
    body_para(doc,
        "Se un ordine viene annullato dall'admin, l'importo pagato viene rimborsato "
        "automaticamente sul wallet del cliente, senza operazioni manuali.")

    h2(doc, 'Filtri e scontrino')
    body_para(doc,
        "In Admin → Ordini puoi filtrare per data e per stato (in attesa, confermato, "
        "in preparazione, pronto, completato, annullato). Ogni ordine ha una scheda di "
        "prelievo stampabile con il riepilogo completo.")


def s05(doc):
    h1(doc, 5, 'Menu e prodotti', '🍕')
    h2(doc, 'Categorie')
    body_para(doc,
        "Ogni prodotto appartiene a una categoria (es. Panini, Primo Piatto, Dolci, Bevande). "
        "Le categorie hanno un'icona Font Awesome e un colore di accento. "
        "Puoi creare tutte le categorie che vuoi da Admin → Prodotti → Categorie.")

    h2(doc, 'Campi di un prodotto')
    data_table(doc,
        ['Campo', 'Descrizione', 'Obbligatorio'],
        [
            ['Nome',                'Nome che vedono i clienti nel menu',                          '✅'],
            ['Descrizione',         'Ingredienti, allergeni, note',                                'No'],
            ['Prezzo',              'In euro con decimali (es. 4,50)',                             '✅'],
            ['Categoria',           'Dove appare nel menu',                                        '✅'],
            ['Quantità giornaliera','Pezzi disponibili ogni giorno',                               '✅'],
            ['Attivo / Disattivo',  'Nasconde il prodotto senza eliminarlo dallo storico',         '—'],
        ],
        col_widths=[4.0, 10.0, 2.5])

    h2(doc, 'Stock giornaliero')
    body_para(doc,
        "Ogni mattina vai su Admin → Stock giornaliero e aggiusta le quantità disponibili "
        "per il giorno. Quando i pezzi si esauriscono, il prodotto sparisce automaticamente "
        "dal menu dei clienti. La dashboard mostra in rosso i prodotti con meno di 3 pezzi rimasti.")
    info_box(doc,
        "Per i prodotti con quantità illimitata (es. acqua, caffè) imposta una quantità "
        "alta come 999. Non apparirà mai in esaurimento.",
        style='tip')


def s06(doc):
    h1(doc, 6, 'Panino & Insalata builder', '🥪')
    body_para(doc,
        "Il builder è la funzione più apprezzata dai clienti: permette di comporre "
        "il panino o l'insalata personalizzati scegliendo gli ingredienti uno a uno. "
        "Il prezzo finale si calcola in automatico sommando i prezzi degli ingredienti "
        "extra scelti al prezzo base del prodotto.")

    h2(doc, "Come funziona per il cliente")
    body_para(doc,
        "Il cliente clicca su «Componi il tuo panino» o «Componi la tua insalata» nel menu "
        "e viene guidato passo passo: tipo di pane → proteina → verdure → salse → extra. "
        "Ogni categoria ha un numero minimo e massimo di scelte configurabile.")

    h2(doc, "Configurazione ingredienti — Admin → Ingredienti Builder")
    data_table(doc,
        ['Campo', 'Descrizione'],
        [
            ['Nome',         'Es. «Pane integrale», «Prosciutto crudo»'],
            ['Prezzo extra', 'Sovrapprezzo rispetto al base (0 = incluso nel prezzo)'],
            ['Vegetariano',  'Mostra il simbolo 🌿 nell\'interfaccia cliente'],
            ['Allergeni',    'Testo libero: «glutine, latte, uova»'],
            ['Attivo',       'Disattiva temporaneamente se esaurito'],
        ],
        col_widths=[4.5, 12.0])
    info_box(doc,
        "Gli ingredienti con prezzo extra > 0 vengono sommati al prezzo base. "
        "Il prezzo base del panino e dell'insalata è definito nella configurazione dell'applicazione.",
        style='warning')


def s07(doc):
    h1(doc, 7, 'Wallet digitale e fidelizzazione', '💳')
    h2(doc, 'Come funziona il wallet')
    body_para(doc,
        "Ogni cliente ha un portafoglio digitale con saldo in euro. Prima di ordinare "
        "deve ricaricare il wallet. Il pagamento avviene automaticamente al momento "
        "dell'ordine scalando il saldo. Se il saldo è insufficiente, l'ordine non viene accettato.")

    h2(doc, 'Ricaricare un wallet')
    for i, (t, tx) in enumerate([
        ('Vai su Admin → Persone → Clienti (o Personale)', 'Cerca l\'utente nella lista.'),
        ('Clicca su "+ Ricarica"',
         'Si apre un popup. Inserisci l\'importo e la causale (es. «Ricarica mensile»).'),
        ('Conferma',
         'Il saldo viene aggiornato immediatamente e la transazione è tracciata nello storico.'),
    ], 1):
        step_row(doc, i, t, tx)

    h2(doc, 'Programma fedeltà')
    body_para(doc,
        "Ad ogni acquisto il cliente accumula punti fedeltà proporzionali alla spesa. "
        "Quando raggiunge la soglia configurata, può riscattare i punti in un buono "
        "sconto accreditato automaticamente sul wallet.")
    data_table(doc,
        ['Parametro', 'Valore predefinito', 'Come cambiarlo'],
        [
            ['Punti per ogni € speso', '10 punti / €', 'config.py → LOYALTY_POINTS_PER_EURO'],
            ['Punti necessari per il premio', '100 punti', 'config.py → LOYALTY_REWARD_POINTS'],
            ['Valore del premio', '1,00 €', 'config.py → LOYALTY_REWARD_AMOUNT'],
        ],
        col_widths=[6.0, 4.5, 6.0])
    info_box(doc,
        "Con i valori predefiniti: spendendo 10 € si accumulano 100 punti e si ottiene 1 € di buono "
        "(sconto del 10%). I valori si personalizzano in config.py.",
        style='tip')


def s08(doc):
    h1(doc, 8, 'Tavoli e prenotazioni', '🪑')
    body_para(doc,
        "Il modulo tavoli permette ai clienti di prenotare un posto a sedere scegliendo "
        "data, fascia oraria e numero di coperti. L'admin vede in tempo reale la "
        "disponibilità di ogni tavolo per ogni slot.")

    h2(doc, 'Configurare i tavoli — Admin → Tavoli')
    body_para(doc,
        "Per ogni tavolo imposta: numero identificativo, posti disponibili e zona "
        "(es. Finestra, Centro, Bancone). Puoi aggiungere o disattivare tavoli in qualsiasi momento.")

    h2(doc, 'Gestire le prenotazioni — Admin → Prenotazioni')
    body_para(doc,
        "La vista disponibilità mostra una griglia tavoli × slot. Le celle libere sono verdi, "
        "quelle occupate mostrano il nome del cliente. Da Admin → Prenotazioni puoi vedere "
        "l'elenco completo e annullare una prenotazione se necessario.")
    info_box(doc,
        "La prenotazione tavolo è indipendente dall'ordine pasto. Un cliente può prenotare "
        "un posto senza ordinare online (e viceversa).",
        style='tip')


def s09(doc):
    h1(doc, 9, 'Personale e clienti', '👥')
    body_para(doc,
        "Il sistema distingue due tipologie di utenti: il personale interno (dipendenti "
        "che usano il backoffice) e i clienti (chi ordina). Entrambi si gestiscono da Admin → Persone.")

    h2(doc, 'Personale (utenti interni)')
    body_para(doc,
        "Gli utenti personale accedono al pannello admin con il loro account e vedono "
        "solo le sezioni corrispondenti al loro ruolo. Non hanno anagrafica estesa. "
        "Per crearli: Admin → Persone → Personale → Crea nuovo utente.")

    h2(doc, 'Clienti — anagrafica completa')
    data_table(doc,
        ['Campo', 'Obbligatorio', 'Note'],
        [
            ['Nome e Cognome',     '✅ Sì', 'Visualizzati nel pannello admin e nelle comunicazioni'],
            ['Email',              '✅ Sì', 'Usata per l\'accesso e le comunicazioni'],
            ['Telefono',           'No',    'Visualizzato in lista clienti, cliccabile'],
            ['Data di nascita',    'No',    'Utile per promozioni birthday'],
            ['Indirizzo',          'No',    'Per eventuali consegne o corrispondenza'],
            ['Telegram Chat ID',   'No',    'Per notifiche personalizzate via Telegram'],
        ],
        col_widths=[4.5, 2.5, 9.5])
    body_para(doc,
        "I clienti possono registrarsi autonomamente dal link pubblico del locale, "
        "oppure essere inseriti dall'admin da Admin → Persone → Clienti → Registra nuovo cliente.")


def s10(doc):
    h1(doc, 10, 'Ruoli e permessi', '🔐')
    body_para(doc,
        "Ogni membro del personale ha uno o più ruoli che determinano a quali sezioni "
        "del pannello admin può accedere. Il sistema è preconfigurato con i ruoli più comuni, "
        "ma puoi crearne di personalizzati da Admin → Persone → Ruoli & Permessi.")

    h2(doc, 'Ruoli predefiniti')
    role_table(doc, [
        ('E94560', HEX_WHITE, '👑  Super Admin',
         'Accesso totale, gestione tenant, unico account globale.'),
        (HEX_NAVY, HEX_WHITE, '🏢  Manager',
         'Ordini, cucina, prodotti, stock, tavoli, slot, report.'),
        ('E67E22', HEX_WHITE, '💰  Cassiere',
         'Visualizza e gestisce stato ordini, vede i report.'),
        ('27AE60', HEX_WHITE, '👨‍🍳  Cuoco',
         'Pannello cucina, avanza stato ordini, solo vista cucina.'),
        ('6C757D', HEX_WHITE, '👤  Utente',
         'Nessun accesso admin, solo area clienti.'),
    ])
    info_box(doc,
        "Per creare un ruolo personalizzato (es. «Responsabile Comunicazioni» che invia notifiche "
        "e sondaggi), vai su Admin → Persone → Ruoli & Permessi → Nuovo ruolo e seleziona "
        "i permessi dalla lista granulare.",
        style='tip')


def s11(doc):
    h1(doc, 11, 'Notifiche e sondaggi', '📣')
    h2(doc, 'Notifiche Telegram')
    body_para(doc,
        "Collega il sistema al tuo Bot Telegram per inviare messaggi a tutti i clienti "
        "con un clic. Utile per avvisare del menu del giorno, chiusure straordinarie o promozioni.")
    body_para(doc,
        "Configurazione: Admin → Impostazioni → Token Bot Telegram. Inserisci il token "
        "del bot (ottenuto da @BotFather) e il Chat ID del gruppo o canale. "
        "Usa il pulsante «Test connessione» per verificare.")

    h2(doc, 'Notifiche Email')
    body_para(doc,
        "Per le comunicazioni via email configura le credenziali Gmail in Admin → Impostazioni. "
        "Inserisci l'indirizzo Gmail e la App Password (non la password normale — si ottiene "
        "dalle impostazioni di sicurezza di Google con autenticazione a 2 fattori attiva).")

    h2(doc, 'Sondaggi')
    body_para(doc,
        "I sondaggi permettono di chiedere ai clienti cosa vogliono mangiare domani. "
        "Vai su Admin → Comunicazioni → Sondaggi → Nuovo sondaggio. Seleziona i prodotti "
        "del giorno seguente, poi invia il link via Telegram o email. "
        "I clienti votano e i risultati si aggiornano in tempo reale.")
    info_box(doc,
        "Usa i sondaggi per pianificare la produzione. Sapere in anticipo quanti voti "
        "ha ricevuto ogni piatto aiuta a preparare le giuste quantità, riducendo gli sprechi.",
        style='success', label='Suggerimento produzione:')


def s12(doc):
    h1(doc, 12, 'Report e statistiche', '📊')
    body_para(doc,
        "Il modulo report (Admin → Report) mostra una panoramica degli ultimi 30 giorni "
        "di attività con grafici interattivi.")
    data_table(doc,
        ['Dato', 'Cosa mostra'],
        [
            ['Incasso giornaliero',
             'Grafico a barre degli ultimi 30 giorni (ordini non annullati)'],
            ['Numero ordini',
             'Trend del volume ordini giorno per giorno'],
            ['Top 10 prodotti',
             'I prodotti più venduti per quantità totale'],
        ],
        col_widths=[5.0, 11.5])

    h2(doc, 'Dashboard')
    body_para(doc,
        "La dashboard (Admin → Dashboard) è il cruscotto quotidiano con i dati del giorno "
        "in corso: incasso odierno, ordini aperti, numero clienti, prodotti attivi, "
        "prenotazioni tavoli e alert prodotti in esaurimento (< 3 pezzi rimasti).")


def s13(doc):
    h1(doc, 13, 'Multi-sede (Multi-tenant)', '🏬')
    body_para(doc,
        "Se gestisci più punti vendita (bar in sedi diverse, mense in aziende diverse), "
        "il sistema supporta nativamente la multi-sede tramite il concetto di tenant. "
        "Ogni tenant è un'istanza completamente separata con il proprio menu, clienti, "
        "staff e configurazioni.")

    h2(doc, 'Gerarchia degli accessi')
    step_row(doc, '👑', 'Super Admin — admin@bar.local',
             "Un solo account globale. Crea e gestisce tutti i tenant. Vede tutti i dati "
             "di tutte le sedi. Non appartiene a nessun tenant specifico.")
    step_row(doc, '🏢', 'Admin Tenant',
             "Un account per ogni sede. Gestisce menu, personale e clienti del proprio locale. "
             "Non può accedere agli altri tenant né alla gestione globale.")
    step_row(doc, '👤', 'Personale & Clienti',
             "Appartengono a un singolo tenant e vedono solo i dati della propria sede.")

    h2(doc, 'Creare una nuova sede')
    body_para(doc,
        "Accedi come Super Admin e vai su Admin → Tenant → Nuovo tenant. Inserisci nome, "
        "slug URL e colore. Poi clicca su «Crea admin» nella riga del tenant appena creato: "
        "il sistema genera automaticamente le credenziali dell'admin di quella sede "
        "e le mostra una sola volta.")
    info_box(doc,
        "La password dell'admin tenant viene mostrata una sola volta al momento della creazione. "
        "Annotala subito e consegnala al responsabile della sede.",
        style='warning')


def s14(doc):
    h1(doc, 14, 'Domande frequenti', '❓')
    faqs = [
        ('Un cliente ha dimenticato la password. Come faccio?',
         "Vai su Admin → Persone → Clienti, clicca «Modifica» per quel cliente e inserisci "
         "una nuova password nel campo apposito. Il cliente può poi cambiarla dal suo profilo."),
        ('Posso disattivare un prodotto temporaneamente senza eliminarlo?',
         "Sì. In Admin → Prodotti clicca l'interruttore (attiva/disattiva) accanto al prodotto. "
         "Sparisce dal menu clienti ma rimane nel sistema con tutto lo storico degli ordini."),
        ('Come faccio a chiudere il servizio per un giorno festivo?',
         "Disattiva tutti gli slot orari da Admin → Slot orari: senza slot attivi, i clienti "
         "non possono effettuare ordini. Ricordati di riattivarli il giorno prima della riapertura."),
        ('Un cliente vuole un rimborso. Come si gestisce?',
         "Se l'ordine è ancora aperto, annullalo da Admin → Ordini: il rimborso viene accreditato "
         "automaticamente sul wallet. Se l'ordine è già completato, usa la ricarica manuale "
         "del wallet con causale «Rimborso ordine #XXX»."),
        ('Il sistema funziona anche da smartphone?',
         "Sì. Sia il pannello admin che l'area clienti sono responsivi e funzionano da qualsiasi "
         "browser mobile. Non serve installare nessuna app."),
        ('Come cambio il colore e il logo del mio locale?',
         "Il Super Admin può modificare colore primario e URL logo di ogni tenant da "
         "Admin → Tenant → Modifica. Il colore cambia l'accento grafico su tutta l'interfaccia."),
        ('Posso avere più admin per lo stesso locale?',
         "Sì. Crea un utente personale e assegnagli il ruolo superadmin. "
         "Avrà gli stessi permessi dell'admin tenant senza essere l'account principale."),
        ('I dati sono al sicuro? Dove vengono salvati?',
         "I dati sono su Neon PostgreSQL, un database cloud con backup automatici e crittografia "
         "a riposo e in transito. Il sito è su Vercel con HTTPS obbligatorio."),
        ('Cosa succede se Internet va giù durante il servizio?',
         "Il sistema è cloud. Se la connessione del locale cade, non sarà temporaneamente "
         "accessibile. Si raccomanda una SIM di backup per ambienti critici."),
        ('Posso esportare i dati per la contabilità?',
         "Al momento non c'è un export diretto in Excel. I dati storici sono consultabili "
         "filtrando per data nella pagina Admin → Ordini."),
    ]

    tbl = doc.add_table(rows=len(faqs), cols=2)
    _no_borders(tbl)
    _table_width(tbl, 16.5)
    _set_col_width(tbl, 0, 0.6)
    _set_col_width(tbl, 1, 15.9)

    for ri, (q, a) in enumerate(faqs):
        bg = HEX_WHITE if ri % 2 == 0 else 'F4F6F9'
        row = tbl.rows[ri]

        # D. / R. colonna
        dc = row.cells[0]
        _cell_shd(dc, HEX_RED if ri % 2 == 0 else 'C73452')
        _cell_margins(dc, top=60, bottom=0, left=60, right=60)
        pd = dc.paragraphs[0]
        pd.alignment = WD_ALIGN_PARAGRAPH.CENTER
        _p_spacing(pd, before=0, after=0)
        _run_font(pd.add_run('D'), size=9, bold=True, color=WHITE)

        # Contenuto colonna
        qc = row.cells[1]
        _cell_shd(qc, bg)
        _cell_margins(qc, top=60, bottom=60, left=100, right=80)
        pq = qc.paragraphs[0]
        _p_spacing(pq, before=0, after=4)
        _run_font(pq.add_run(q), size=10, bold=True, color=NAVY)
        pa = qc.add_paragraph()
        _p_spacing(pa, before=0, after=0)
        _run_font(pa.add_run(a), size=10, color=GRAY)

    doc.add_paragraph().paragraph_format.space_after = Pt(6)


def s15(doc):
    h1(doc, 15, 'Credenziali di accesso', '🔑')
    info_box(doc,
        "Cambia tutte le password predefinite al primo accesso. "
        "Le credenziali qui sotto sono quelle iniziali di configurazione.",
        style='warning')

    h2(doc, 'Super Admin — accesso globale')
    cred_box(doc, 'Super Admin — un solo account, accesso totale', [
        ('URL',       'https://tuo-dominio.vercel.app/admin', True),
        ('Email',     'admin@bar.local',                      False),
        ('Password',  'admin123',                             True),
    ])

    h2(doc, 'Admin tenant (dati demo)')
    cred_box(doc, 'Admin per ogni sede — password identica sui tre tenant demo', [
        ('Bar Centrale',      'admin@bar-centrale.local',      False),
        ('Mensa AziendaTech', 'admin@mensa-tech.local',        False),
        ('Caffetteria Duomo', 'admin@caffetteria-duomo.local', False),
        ('Password comune',   'demo1234',                      True),
    ])

    h2(doc, 'Clienti demo')
    cred_box(doc, '36 clienti demo con anagrafica completa', [
        ('Email',    'nome.cognome@gmail.com (vedi lista clienti)', False),
        ('Password', 'cliente123',                                   True),
    ])

    h2(doc, 'Link di registrazione clienti')
    data_table(doc,
        ['Sede', 'Link di registrazione'],
        [
            ['Bar Centrale',      '/t/bar-centrale/register'],
            ['Mensa AziendaTech', '/t/mensa-tech/register'],
            ['Caffetteria Duomo', '/t/caffetteria-duomo/register'],
        ],
        col_widths=[5.5, 11.0])

    info_box(doc,
        "Per creare le credenziali di un nuovo admin tenant (in produzione), usa il pulsante "
        "«Crea admin» nella pagina Admin → Tenant. Il sistema genera una password casuale "
        "sicura e la mostra una sola volta.",
        style='success')


# ── Impostazioni documento ────────────────────────────────────────────────────

def set_document_defaults(doc):
    # Margini pagina 2.2 cm su tutti i lati
    for section in doc.sections:
        section.top_margin    = Cm(2.2)
        section.bottom_margin = Cm(2.2)
        section.left_margin   = Cm(2.5)
        section.right_margin  = Cm(2.5)

    # Stile di default: PT Sans Narrow 11pt
    style = doc.styles['Normal']
    style.font.name = FONT
    style.font.size = Pt(11)

    # Header con nome documento
    for section in doc.sections:
        header = section.header
        header.is_linked_to_previous = False
        p = header.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        _p_spacing(p, before=0, after=4)
        _para_border(p, bottom_color='DEE2E6', bottom_sz='4')
        r1 = p.add_run('BSR Pranzo  ')
        _run_font(r1, size=8, bold=True, color=RED)
        r2 = p.add_run('· Manuale del Proprietario')
        _run_font(r2, size=8, color=GRAY)

    # Footer con numero di pagina
    for section in doc.sections:
        footer = section.footer
        footer.is_linked_to_previous = False
        p = footer.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        _p_spacing(p, before=4, after=0)
        _para_border(p, bottom_color=None)
        r = p.add_run('— ')
        _run_font(r, size=8, color=GRAY)
        # Campo numero pagina
        fldChar1 = OxmlElement('w:fldChar')
        fldChar1.set(qn('w:fldCharType'), 'begin')
        instrText = OxmlElement('w:instrText')
        instrText.text = ' PAGE '
        fldChar3 = OxmlElement('w:fldChar')
        fldChar3.set(qn('w:fldCharType'), 'end')
        run_el = p.add_run()._r
        run_el.append(fldChar1)
        run_el.append(instrText)
        run_el.append(fldChar3)
        _run_font(p.runs[-1], size=8, color=GRAY)
        r2 = p.add_run(' —')
        _run_font(r2, size=8, color=GRAY)


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    doc = Document()
    set_document_defaults(doc)

    build_cover(doc)
    build_toc(doc)

    sections = [s01, s02, s03, s04, s05, s06, s07,
                s08, s09, s10, s11, s12, s13, s14, s15]

    for i, fn in enumerate(sections):
        fn(doc)
        if i < len(sections) - 1:
            _page_break(doc)

    # Footer finale
    p = doc.add_paragraph()
    _p_spacing(p, before=20, after=0)
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _para_border(p, bottom_color=None)
    r = p.add_run('BSR Pranzo  ·  Sistema di gestione bar e mense  ·  v2.0  ·  Giugno 2026')
    _run_font(r, size=9, color=GRAY)

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    doc.save(OUT)
    print(f'[OK] Documento salvato in: {OUT}')


if __name__ == '__main__':
    main()
