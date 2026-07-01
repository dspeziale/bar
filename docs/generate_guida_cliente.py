#!/usr/bin/env python3
"""
Genera docs/guida_cliente.docx — Guida Cliente Completa per QuickLunch.

Guida dedicata esclusivamente al ruolo Cliente: dopo averla letta, un cliente
deve essere in grado di registrarsi, ordinare, pagare, prenotare un tavolo,
gestire wallet e punti fedeltà, votare i sondaggi e usare il pasto aziendale
(se dipendente convenzionato) senza bisogno di assistenza.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from docx import Document
from docx.shared import RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH

from generate_guide import (
    set_document_defaults, _page_break, h1, h2, h3, body_para,
    info_box, info_box_color, step_row, data_table, role_badge,
    workflow_table, spacer, divider,
    _no_borders, _table_width, _row_height, _cell_shd, _cell_margins,
    _cell_vAlign, _run_font, _p_spacing, _cell_border, _set_col_width,
    HEX_RED, HEX_NAVY, HEX_DARK, HEX_LIGHT, HEX_WHITE, HEX_GREEN,
    HEX_PURPL, HEX_TEAL, HEX_ORNG,
    RED, NAVY, DARK, DGRAY, GRAY, WHITE, GREEN, PURPL, TEAL, ORNG,
)

OUT = os.path.join(os.path.dirname(__file__), 'guida_cliente.docx')


# ── Cover page dedicata al cliente ──────────────────────────────────────────

def build_cover_cliente(doc):
    tbl = doc.add_table(rows=3, cols=1)
    _no_borders(tbl)
    _table_width(tbl, 21.0)
    _row_height(tbl.rows[0], 4.5)
    _row_height(tbl.rows[1], 19.0)
    _row_height(tbl.rows[2], 6.2)

    for row in tbl.rows:
        _cell_shd(row.cells[0], HEX_DARK)
        _cell_margins(row.cells[0], top=0, bottom=0, left=0, right=0)

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
    _run_font(p0.add_run('👤🍽️'), size=56, color=WHITE)

    cp('QuickLunch', size=54, bold=True, color=RGBColor(0x8e, 0x44, 0xad), after=0)
    cp('PRANZO', size=54, bold=True, color=WHITE, after=8)
    cp('GUIDA CLIENTE COMPLETA', size=18, bold=True,
       color=RGBColor(0xc0, 0xd0, 0xe0), after=24)
    cp('Tutto quello che ti serve per ordinare, pagare,\n'
       'prenotare un tavolo e usare i punti fedeltà — da solo, in pochi minuti.',
       size=13, color=RGBColor(0x90, 0xa8, 0xc0), after=28)

    bullets = [
        '🍽️  Ordinare dal menu', '💳  Pagare con il wallet',
        '🥪  Comporre panino/insalata/poke', '🪑  Prenotare un tavolo',
        '⭐  Punti fedeltà e premi', '🗳️  Votare i sondaggi',
    ]
    pr = cc.add_paragraph()
    pr.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _p_spacing(pr, before=0, after=20)
    for i, name in enumerate(bullets):
        _run_font(pr.add_run(name), size=11, color=RGBColor(0xb0, 0xc8, 0xe0))
        if i < len(bullets) - 1:
            _run_font(pr.add_run('  ·  '), size=10, color=RGBColor(0x50, 0x60, 0x70))

    cp('Versione 1.0  ·  2026', size=10,
       color=RGBColor(0x60, 0x70, 0x80), after=0)

    bc = tbl.rows[2].cells[0]
    _cell_shd(bc, HEX_PURPL)
    _cell_margins(bc, top=60, bottom=60, left=300, right=300)
    _cell_vAlign(bc, 'center')
    pb = bc.paragraphs[0]
    pb.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _p_spacing(pb, before=0, after=6)
    _run_font(pb.add_run('📱  NON SERVE INSTALLARE NIENTE — FUNZIONA DAL BROWSER'),
              size=12, bold=True, color=WHITE)
    pb2 = bc.add_paragraph()
    pb2.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _p_spacing(pb2, before=0, after=0)
    _run_font(pb2.add_run(
        'Apri il link del tuo locale dal telefono o dal computer e segui questa guida passo passo.'),
        size=10, color=RGBColor(0xff, 0xff, 0xff))


def build_toc_cliente(doc):
    h2(doc, '📋  Indice dei contenuti')
    spacer(doc, 4)

    toc_items = [
        ('1', '🚀  Iniziare', 'Registrazione, accesso, panoramica home'),
        ('2', '🍽️  Ordinare dal menu', 'Sfoglia, carrello, slot di ritiro — esempio: pagare un caffè'),
        ('3', '🥪  Crea il tuo piatto', 'Builder panino, insalata, poke su misura'),
        ('4', '📦  I miei ordini', 'Storico, stati, annullamento e rimborso'),
        ('5', '💳  Wallet e punti fedeltà', 'Saldo, ricarica, storico, riscatto premi'),
        ('6', '🪑  Prenotare un tavolo', 'Disponibilità, prenotazione, check-in, annullamento'),
        ('7', '🗳️  Votare i sondaggi', 'Esprimi la tua preferenza sul menu'),
        ('8', '🏢  Pasto Aziendale', 'Solo dipendenti con convenzione attiva'),
        ('9', '🔔  Notifiche Telegram', 'Come ricevere conferme e avvisi'),
        ('10', '❓  Domande frequenti', 'Problemi comuni e soluzioni rapide'),
        ('11', '🧭  Scheda riassuntiva', 'Tutte le azioni in una tabella'),
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
        _cell_shd(row.cells[0], HEX_PURPL)
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
# SEZIONE 1 — INIZIARE
# ══════════════════════════════════════════════════════════════════════════════

def s1_iniziare(doc):
    h1(doc, '1', 'Iniziare', '🚀', accent=HEX_PURPL)

    role_badge(doc, '👤', 'Cliente',
               'QuickLunch Pranzo è l\'app del tuo locale: ordini il pranzo, lo paghi dal telefono '
               'con il tuo wallet, prenoti un tavolo e accumuli punti fedeltà. Non serve scaricare '
               'nessuna applicazione: funziona direttamente nel browser dello smartphone o del computer.',
               HEX_PURPL)
    spacer(doc, 8)

    h2(doc, '1.1  Registrazione (solo la prima volta)')
    step_row(doc, 1, 'Apri il link del locale', 'Il tuo bar/mensa ti fornisce un indirizzo web (es. https://pranzo.barcentrale.it). Aprilo dal browser del telefono o del PC')
    spacer(doc, 4)
    step_row(doc, 2, 'Tocca "Registrati"', 'Sotto al modulo di accesso trovi il link per creare un nuovo account')
    spacer(doc, 4)
    step_row(doc, 3, 'Inserisci email e password', 'La password deve avere almeno 6 caratteri. Ripetila nel campo "Conferma password"')
    spacer(doc, 4)
    step_row(doc, 4, 'Tocca "Registrati"', 'Il sistema crea il tuo account, ti assegna uno username automatico e ti fa entrare subito, già loggato')
    spacer(doc, 8)

    info_box(doc, 'Se l\'email è già registrata, il sistema te lo segnala: in quel caso usa "Accedi" con la password che avevi scelto. '
             'Se l\'hai dimenticata, chiedi all\'amministratore del locale di reimpostarla dal pannello clienti.',
             style='tip')
    spacer(doc, 8)

    h2(doc, '1.2  Accesso (tutte le volte successive)')
    step_row(doc, 1, 'Apri il link del locale', 'Stesso indirizzo della registrazione')
    spacer(doc, 4)
    step_row(doc, 2, 'Inserisci email e password', 'Quelle scelte in fase di registrazione')
    spacer(doc, 4)
    step_row(doc, 3, 'Tocca "Accedi"', 'Il sistema ti ricorda per circa 30 giorni: non dovrai rifare il login ogni volta')
    spacer(doc, 8)

    info_box_color(doc,
        'Consiglio: dal menu del browser scegli "Aggiungi a schermata Home" (o "Installa app"). '
        'Otterrai un\'icona come una vera app, senza dover riscrivere l\'indirizzo ogni volta.',
        bg='EBF5FB', border=HEX_TEAL, icon='💡')
    spacer(doc, 8)

    h2(doc, '1.3  La Home: cosa trovi appena entri')
    body_para(doc, 'La Home (dashboard) è la tua pagina di partenza. Da lì vedi in un colpo d\'occhio:')
    spacer(doc, 4)
    data_table(doc,
        ['Riquadro', 'Cosa mostra'],
        [
            ['Ordini di oggi',        'Gli ordini che hai fatto oggi e il loro stato (confermato, in preparazione, pronto)'],
            ['Prenotazioni di oggi',  'I tavoli che hai prenotato per oggi, se presenti'],
            ['Ultime transazioni',    'Gli ultimi movimenti del tuo wallet (pagamenti, ricariche, rimborsi)'],
            ['Punti fedeltà',         'Quanto manca al prossimo premio fedeltà'],
        ],
        col_widths=[5.0, 12.6])
    spacer(doc, 6)

    body_para(doc, 'Dal menu laterale (icona ☰ in alto a sinistra su telefono) raggiungi tutte le sezioni: '
              'Menu, Carrello, I Miei Ordini, Wallet & Fedeltà, Tavoli, Le Mie Prenotazioni, Vota il Menu '
              'e — se sei un dipendente con convenzione aziendale attiva — Pasto Aziendale.')


# ══════════════════════════════════════════════════════════════════════════════
# SEZIONE 2 — ORDINARE DAL MENU
# ══════════════════════════════════════════════════════════════════════════════

def s2_ordinare(doc):
    h1(doc, '2', 'Ordinare dal menu', '🍽️', accent=HEX_PURPL)

    workflow_table(doc, [
        ('🍽️', 'Apri Menu', 'Sfoglia categorie'),
        ('➕', 'Aggiungi', 'Tocca il prodotto'),
        ('🛒', 'Carrello', 'Scegli lo slot'),
        ('💳', 'Paga', 'Wallet'),
        ('✅', 'Conferma', 'Ricevi il codice ordine'),
    ], accent=HEX_NAVY)
    spacer(doc, 8)

    h2(doc, '2.1  Sfogliare il menu')
    step_row(doc, 1, 'Vai in "Menu"', 'Dal menu laterale, o dal bottone in Home')
    spacer(doc, 4)
    step_row(doc, 2, 'Scegli una categoria', 'Es. Primi, Secondi, Contorni, Bevande, Dolci, Senza Glutine — ogni categoria ha un\'icona colorata')
    spacer(doc, 4)
    step_row(doc, 3, 'Guarda i dettagli del prodotto', 'Nome, descrizione, prezzo e disponibilità residua per oggi sono sempre visibili')
    spacer(doc, 8)

    info_box(doc, 'I prodotti con disponibilità "0" per oggi sono esauriti e non si possono più aggiungere al carrello. '
             'La disponibilità si rinnova ogni giorno.', style='info')
    spacer(doc, 8)

    h2(doc, '2.2  Aggiungere prodotti al carrello')
    step_row(doc, 1, 'Imposta la quantità', 'Accanto al prodotto trovi un campo numerico, di default è 1')
    spacer(doc, 4)
    step_row(doc, 2, 'Tocca "Aggiungi"', 'Il prodotto entra nel carrello: vedi un messaggio di conferma in alto')
    spacer(doc, 4)
    step_row(doc, 3, 'Ripeti per altri prodotti', 'Puoi mischiare prodotti di categorie diverse nello stesso ordine')
    spacer(doc, 8)

    h2(doc, '2.3  Gestire il carrello')
    step_row(doc, 1, 'Apri "Carrello"', 'Icona carrello nel menu, o link diretto')
    spacer(doc, 4)
    step_row(doc, 2, 'Modifica le quantità', 'Cambia il numero accanto a ogni riga e conferma: il totale si aggiorna da solo')
    spacer(doc, 4)
    step_row(doc, 3, 'Rimuovi un prodotto', 'Tocca l\'icona cestino sulla riga che vuoi togliere')
    spacer(doc, 4)
    step_row(doc, 4, 'Controlla il totale', 'In fondo al carrello vedi il totale da pagare e il tuo saldo wallet attuale')
    spacer(doc, 8)

    divider(doc)
    spacer(doc, 6)

    h2(doc, '2.4  ESEMPIO PRATICO — Come ordinare e pagare un caffè', color=PURPL)
    info_box_color(doc,
        'Questo è l\'esempio più semplice possibile: lo trovi qui passo dopo passo, '
        'esattamente come lo vedrai sullo schermo.',
        bg='F4ECF7', border=HEX_PURPL, icon='☕')
    spacer(doc, 6)

    step_row(doc, 1, 'Apri "Menu"', 'Tocca la categoria "Bevande" (o quella che contiene il caffè)', accent=HEX_PURPL)
    spacer(doc, 4)
    step_row(doc, 2, 'Trova "Caffè"', 'Vedi il prezzo, ad esempio 1,00€, e la quantità "1" già impostata', accent=HEX_PURPL)
    spacer(doc, 4)
    step_row(doc, 3, 'Tocca "Aggiungi"', 'Il caffè entra nel carrello — appare un messaggio verde di conferma', accent=HEX_PURPL)
    spacer(doc, 4)
    step_row(doc, 4, 'Vai al "Carrello"', 'Vedi una riga: "Caffè × 1 — 1,00€" e il totale ordine: 1,00€', accent=HEX_PURPL)
    spacer(doc, 4)
    step_row(doc, 5, 'Scegli lo slot di ritiro', 'Seleziona l\'orario in cui passerai a ritirarlo, es. 11:45', accent=HEX_PURPL)
    spacer(doc, 4)
    step_row(doc, 6, 'Tocca "Conferma ordine"', 'Se il tuo saldo wallet è di almeno 1,00€, l\'ordine va a buon fine all\'istante', accent=HEX_PURPL)
    spacer(doc, 4)
    step_row(doc, 7, 'Ricevi conferma', 'Vedi il codice ordine (es. QuickLunch-260630-1145-0042) e — se hai Telegram collegato — una notifica con orario di ritiro', accent=HEX_PURPL)
    spacer(doc, 4)
    step_row(doc, 8, 'Ritira alla cassa', 'All\'orario scelto, mostra il codice ordine (o il tuo nome) al cassiere o aspetta che venga chiamato', accent=HEX_PURPL)
    spacer(doc, 8)

    divider(doc)
    spacer(doc, 6)

    h2(doc, '2.5  Pagamento: cosa succede se il saldo non basta')
    body_para(doc, 'QuickLunch paga sempre con il wallet: non puoi confermare un ordine se il saldo è inferiore al totale.')
    spacer(doc, 4)
    info_box(doc, 'Se il messaggio dice "Saldo wallet insufficiente", vieni reindirizzato automaticamente alla pagina Wallet. '
             'Chiedi al cassiere di ricaricare il tuo wallet (vedi Sezione 5), poi torna nel carrello e conferma di nuovo: '
             'i prodotti restano salvati.', style='warning')
    spacer(doc, 8)

    h2(doc, '2.6  Dopo la conferma: cosa ricevi')
    data_table(doc,
        ['Cosa ricevi', 'Dove lo trovi'],
        [
            ['Codice ordine univoco',  'Messaggio di conferma e in "I Miei Ordini"'],
            ['Addebito sul wallet',    'Storico transazioni in Wallet & Fedeltà'],
            ['Punti fedeltà',          '10 punti per ogni euro speso, accreditati subito'],
            ['Notifica Telegram',      'Se hai il bot collegato, ricevi orario di ritiro e totale pagato'],
        ],
        col_widths=[6.0, 11.6])


# ══════════════════════════════════════════════════════════════════════════════
# SEZIONE 3 — CREA IL TUO PIATTO (BUILDER)
# ══════════════════════════════════════════════════════════════════════════════

def s3_builder(doc):
    h1(doc, '3', 'Crea il tuo piatto', '🥪', accent=HEX_PURPL)

    role_badge(doc, '🥪', 'Builder',
               'Oltre ai prodotti già pronti del menu, puoi comporre tu stesso un panino, '
               'un\'insalata o una poke bowl, scegliendo ogni ingrediente. Il prezzo si calcola automaticamente.',
               HEX_ORNG)
    spacer(doc, 8)

    h2(doc, '3.1  Come si usa')
    step_row(doc, 1, 'Vai in "Componi il tuo piatto"', 'Dal menu laterale o dal pulsante in Menu')
    spacer(doc, 4)
    step_row(doc, 2, 'Scegli il tipo', 'Panino (da 3,50€), Insalata (da 3,00€) o Poke (da 4,00€) — il prezzo base è già incluso')
    spacer(doc, 4)
    step_row(doc, 3, 'Seleziona gli ingredienti per categoria', 'Pane/base, proteine, verdure, salse, extra — ogni categoria mostra quante scelte sono permesse')
    spacer(doc, 4)
    step_row(doc, 4, 'Rispetta le categorie obbligatorie', 'Alcune categorie (es. "Scegli il pane") sono obbligatorie: senza una scelta non puoi proseguire')
    spacer(doc, 4)
    step_row(doc, 5, 'Per il panino: opzione "Alla griglia"', 'Se disponibile, puoi spuntare la casella per farlo scaldare/grigliare')
    spacer(doc, 4)
    step_row(doc, 6, 'Controlla il prezzo totale', 'Si aggiorna automaticamente: prezzo base + costo extra di ogni ingrediente scelto')
    spacer(doc, 4)
    step_row(doc, 7, 'Tocca "Aggiungi al carrello"', 'Il piatto personalizzato entra nel carrello con un nome descrittivo (es. "Panino personalizzato 🔥: Pane integrale, Pollo, Lattuga, Maionese")')
    spacer(doc, 8)

    info_box(doc, 'Se una categoria ammette al massimo, ad esempio, 2 scelte e ne selezioni 3, il sistema ti blocca '
             'e ti chiede di toglierne una prima di continuare.', style='warning')
    spacer(doc, 8)

    h2(doc, '3.2  ESEMPIO PRATICO — Comporre un panino', color=ORNG)
    step_row(doc, 1, 'Tipo: Panino', 'Prezzo base 3,50€', accent=HEX_ORNG)
    spacer(doc, 4)
    step_row(doc, 2, 'Pane: Pane integrale', 'Categoria obbligatoria, nessun costo extra', accent=HEX_ORNG)
    spacer(doc, 4)
    step_row(doc, 3, 'Proteina: Petto di pollo', '+1,00€', accent=HEX_ORNG)
    spacer(doc, 4)
    step_row(doc, 4, 'Verdure: Lattuga e pomodoro', 'Nessun costo extra', accent=HEX_ORNG)
    spacer(doc, 5)
    step_row(doc, 5, 'Salsa: Maionese', 'Nessun costo extra', accent=HEX_ORNG)
    spacer(doc, 4)
    step_row(doc, 6, 'Alla griglia: sì', 'Spunta la casella 🔥', accent=HEX_ORNG)
    spacer(doc, 4)
    step_row(doc, 7, 'Totale: 4,50€', 'Aggiunto al carrello, poi si procede come un ordine normale (slot + conferma)', accent=HEX_ORNG)
    spacer(doc, 8)

    body_para(doc, 'Il piatto personalizzato viaggia insieme agli altri prodotti nello stesso carrello: '
              'puoi avere, ad esempio, un panino fatto da te più una bevanda del menu nello stesso ordine.')


# ══════════════════════════════════════════════════════════════════════════════
# SEZIONE 4 — I MIEI ORDINI
# ══════════════════════════════════════════════════════════════════════════════

def s4_ordini(doc):
    h1(doc, '4', 'I miei ordini', '📦', accent=HEX_PURPL)

    h2(doc, '4.1  Vedere lo storico')
    step_row(doc, 1, 'Vai in "I Miei Ordini"', 'Dal menu laterale')
    spacer(doc, 4)
    step_row(doc, 2, 'Scorri la lista', 'Vedi gli ultimi 50 ordini, dal più recente: data, codice, prodotti, totale, stato')
    spacer(doc, 8)

    h3(doc, 'Stati possibili di un ordine')
    data_table(doc,
        ['Stato', 'Significato'],
        [
            ['Confermato',  'L\'ordine è stato pagato ed è in coda per la preparazione'],
            ['In preparazione', 'La cucina ha iniziato a prepararlo'],
            ['Pronto',      'Puoi ritirarlo alla cassa/bancone'],
            ['Consegnato',  'L\'ordine è stato ritirato'],
            ['Annullato',   'L\'ordine è stato cancellato e l\'importo rimborsato'],
        ],
        col_widths=[4.5, 13.1])
    spacer(doc, 8)

    h2(doc, '4.2  Annullare un ordine')
    step_row(doc, 1, 'Apri "I Miei Ordini"', 'Trova l\'ordine da annullare')
    spacer(doc, 4)
    step_row(doc, 2, 'Tocca "Annulla"', 'Disponibile solo se l\'ordine è ancora "Confermato" — non puoi più annullare un ordine già "In preparazione" o "Pronto"')
    spacer(doc, 4)
    step_row(doc, 3, 'Conferma', 'L\'importo torna subito sul tuo wallet e i punti fedeltà guadagnati con quell\'ordine vengono tolti')
    spacer(doc, 8)

    info_box(doc, 'Se hai cambiato idea ma l\'ordine è già "In preparazione", non puoi annullarlo da solo: '
             'rivolgiti subito al cassiere o alla cucina mostrando il codice ordine.', style='warning')
    spacer(doc, 8)

    h2(doc, '4.3  Qualcosa non torna? Come segnalarlo')
    info_box(doc, 'Se un ordine non è arrivato, è sbagliato o c\'è un addebito che non riconosci, vai in "I Miei Ordini", '
             'individua il numero ordine e mostralo al cassiere: con quel codice trova e corregge il problema in pochi secondi.',
             style='tip')


# ══════════════════════════════════════════════════════════════════════════════
# SEZIONE 5 — WALLET E PUNTI FEDELTÀ
# ══════════════════════════════════════════════════════════════════════════════

def s5_wallet(doc):
    h1(doc, '5', 'Wallet e punti fedeltà', '💳', accent=HEX_PURPL)

    role_badge(doc, '💳', 'Wallet',
               'Il wallet è il tuo portafoglio digitale nel locale: ci carichi credito e paghi i tuoi ordini '
               'in un tocco, senza contanti o carta ogni volta.',
               HEX_NAVY)
    spacer(doc, 8)

    h2(doc, '5.1  Vedere saldo e storico')
    step_row(doc, 1, 'Vai in "Wallet & Fedeltà"', 'Dal menu laterale')
    spacer(doc, 4)
    step_row(doc, 2, 'Saldo disponibile', 'In alto, in grande, il credito che puoi spendere ora')
    spacer(doc, 4)
    step_row(doc, 3, 'Storico transazioni', 'Sotto trovi data, tipo (pagamento, ricarica, rimborso, riscatto punti), descrizione e importo di ogni movimento')
    spacer(doc, 8)

    h2(doc, '5.2  Come ricaricare il wallet')
    info_box(doc, 'La ricarica del wallet non si fa dall\'app cliente: chiedi al cassiere di ricaricarti '
             'l\'importo che preferisci (es. 10€, 20€, 50€) — verrà accreditato all\'istante e lo vedrai subito '
             'nello storico transazioni come "Ricarica".', style='info')
    spacer(doc, 8)

    h2(doc, '5.3  Punti fedeltà: come si accumulano')
    data_table(doc,
        ['Regola', 'Dettaglio'],
        [
            ['Accumulo',        'Guadagni 10 punti per ogni euro speso con il wallet'],
            ['Premio',          'Ogni 100 punti raggiunti, puoi riscattare +1,00€ di credito wallet'],
            ['Riscatti multipli', 'Se hai accumulato, ad esempio, 250 punti, puoi riscattare 2 blocchi da 100 = +2,00€ (restano 50 punti)'],
            ['Annullamento ordine', 'Se annulli un ordine, i punti guadagnati con quell\'ordine vengono tolti'],
        ],
        col_widths=[4.8, 12.8])
    spacer(doc, 8)

    h2(doc, '5.4  ESEMPIO PRATICO — Riscattare i punti', color=NAVY)
    step_row(doc, 1, 'Vai in "Wallet & Fedeltà"', 'Vedi la barra di avanzamento verso il prossimo premio')
    spacer(doc, 4)
    step_row(doc, 2, 'Raggiungi almeno 100 punti', 'Quando arrivi alla soglia, compare il pulsante "Riscatta"')
    spacer(doc, 4)
    step_row(doc, 3, 'Tocca "Riscatta punti"', 'Il sistema converte tutti i blocchi da 100 punti disponibili in credito wallet')
    spacer(doc, 4)
    step_row(doc, 4, 'Credito accreditato subito', 'Vedi il nuovo saldo aggiornato e una riga "Riscatto punti" nello storico')
    spacer(doc, 8)

    info_box_color(doc,
        'I punti restanti sotto i 100 (es. 50 punti dopo un riscatto da 250) non vengono persi: '
        'restano in conto per il prossimo premio.',
        bg='EBF5FB', border=HEX_TEAL, icon='💡')


# ══════════════════════════════════════════════════════════════════════════════
# SEZIONE 6 — PRENOTARE UN TAVOLO
# ══════════════════════════════════════════════════════════════════════════════

def s6_tavoli(doc):
    h1(doc, '6', 'Prenotare un tavolo', '🪑', accent=HEX_PURPL)

    body_para(doc,
        'La prenotazione di un tavolo funziona per FASCE ORARIE: ogni fascia è un blocco di tempo '
        '(es. 11:25–12:30) suddiviso in sessioni della stessa durata (es. 30 min). '
        'Prenoti un tavolo per una sessione specifica.')
    spacer(doc, 6)

    h2(doc, '6.1  Scegliere il giorno')
    step_row(doc, 1, 'Vai in "Tavoli" dal menu laterale', 'Si apre la pagina di prenotazione tavoli')
    spacer(doc, 4)
    step_row(doc, 2, 'Usa le frecce ‹ › per scegliere il giorno', 'O inserisci la data nel campo in alto. Di default vedi oggi')
    spacer(doc, 8)

    h2(doc, '6.2  Scegliere la sessione e il tavolo')
    step_row(doc, 1, 'Leggi le fasce orarie', 'Ogni fascia (es. "11:25 – 12:30 · 30 min a seduta") mostra le sessioni disponibili')
    spacer(doc, 4)
    step_row(doc, 2, 'Scegli la sessione di inizio', 'Es. 11:25 oppure 11:55 oppure 12:25 — ogni sessione dura 30 minuti')
    spacer(doc, 4)
    step_row(doc, 3, 'Guarda i tavoli disponibili', 'Verde = libero (puoi prenotare), rosso = occupato, blu = già tuo')
    spacer(doc, 4)
    step_row(doc, 4, 'Tocca un tavolo verde', 'Si apre la scheda di prenotazione con i dettagli della sessione')
    spacer(doc, 4)
    step_row(doc, 5, 'Indica il numero di persone', 'Non puoi superare i posti disponibili al tavolo (es. tavolo da 4 → massimo 4)')
    spacer(doc, 4)
    step_row(doc, 6, 'Aggiungi eventuali note (facoltativo)', 'Es. "Seggiolone per bambino", "Vicino alla finestra"')
    spacer(doc, 4)
    step_row(doc, 7, 'Tocca "Prenota"', 'Conferma immediata: la sessione è riservata per te')
    spacer(doc, 8)

    h2(doc, '6.3  Le mie prenotazioni')
    step_row(doc, 1, 'Vai in "Le Mie Prenotazioni"', 'Vedi tutte le prenotazioni fatte, dalla più recente')
    spacer(doc, 4)
    step_row(doc, 2, 'All\'arrivo al locale', 'Comunica il tuo nome o il numero tavolo al personale: registreranno il tuo check-in')
    spacer(doc, 4)
    step_row(doc, 3, 'Per annullare', 'Tocca "Annulla" nella prenotazione — il tavolo torna disponibile per altri clienti')
    spacer(doc, 8)

    info_box(doc, 'Non puoi prenotare due tavoli nella stessa sessione oraria. '
             'Puoi invece prenotare tavoli in sessioni diverse (es. una prenotazione alle 11:25 '
             'e una alle 12:30 sono ammesse).', style='warning')


# ══════════════════════════════════════════════════════════════════════════════
# SEZIONE 7 — VOTARE I SONDAGGI
# ══════════════════════════════════════════════════════════════════════════════

def s7_sondaggi(doc):
    h1(doc, '7', 'Votare i sondaggi', '🗳️', accent=HEX_PURPL)

    body_para(doc, 'Il locale può aprire sondaggi per capire cosa i clienti vorrebbero trovare nel menu. '
              'Votando, aiuti a scegliere i prossimi piatti.')
    spacer(doc, 6)

    step_row(doc, 1, 'Vai in "Vota il Menu"', 'Dal menu laterale: se c\'è un sondaggio attivo, si apre direttamente')
    spacer(doc, 4)
    step_row(doc, 2, 'Leggi la domanda e le opzioni', 'Ogni opzione ha un\'emoji e un testo descrittivo')
    spacer(doc, 4)
    step_row(doc, 3, 'Tocca l\'opzione che preferisci', 'Il voto è immediato e definitivo')
    spacer(doc, 4)
    step_row(doc, 4, 'Guarda i risultati', 'Dopo aver votato vedi come si sta orientando la preferenza di tutti i clienti')
    spacer(doc, 8)

    info_box(doc, 'Puoi votare una sola volta per ogni sondaggio: dopo il voto l\'opzione scelta resta evidenziata '
             'e non potrai cambiarla.', style='info')
    spacer(doc, 6)

    info_box_color(doc,
        'Se non vedi nessun sondaggio, significa che il locale non ne ha aperti al momento: ricontrolla più avanti.',
        bg='F4ECF7', border=HEX_PURPL, icon='ℹ️')


# ══════════════════════════════════════════════════════════════════════════════
# SEZIONE 8 — PASTO AZIENDALE
# ══════════════════════════════════════════════════════════════════════════════

def s8_pasto_aziendale(doc):
    h1(doc, '8', 'Pasto Aziendale', '🏢', accent=HEX_PURPL)

    role_badge(doc, '🏢', 'Dipendente convenzionato',
               'Se la tua azienda ha una convenzione attiva con il locale, vedrai una voce in più nel menu: '
               '"Pasto Aziendale". Da lì prenoti il pasto fisso del giorno al prezzo speciale aziendale, '
               'senza passare dal menu normale.',
               HEX_PURPL)
    spacer(doc, 8)

    h2(doc, '8.1  Come funziona')
    step_row(doc, 1, 'Vai in "Pasto Aziendale"', 'Visibile solo se sei associato a una convenzione attiva')
    spacer(doc, 4)
    step_row(doc, 2, 'Guarda il menu di oggi', 'Il piatto fisso del giorno, con nome, descrizione e posti rimasti')
    spacer(doc, 4)
    step_row(doc, 3, '(Facoltativo) Scegli uno slot orario', 'Se non scegli nulla, vale "Qualsiasi orario"')
    spacer(doc, 4)
    step_row(doc, 4, 'Tocca "Prenota il mio pasto"', 'La prenotazione è immediata: un posto in meno per gli altri colleghi')
    spacer(doc, 4)
    step_row(doc, 5, 'All\'orario di ritiro', 'Vai al locale e ritira il pasto mostrando, se richiesto, il tuo nome')
    spacer(doc, 8)

    h2(doc, '8.2  Annullare la prenotazione')
    step_row(doc, 1, 'Apri "Pasto Aziendale"', 'Vedi la tua prenotazione attiva per oggi')
    spacer(doc, 4)
    step_row(doc, 2, 'Tocca "Annulla prenotazione"', 'Il posto torna disponibile per un collega — possibile solo prima del ritiro')
    spacer(doc, 8)

    info_box(doc, 'Se il messaggio dice "Posti esauriti per oggi" significa che il numero massimo di pasti prenotabili è stato raggiunto: '
             'riprova il giorno successivo o contatta l\'amministratore aziendale.', style='warning')
    spacer(doc, 6)

    info_box_color(doc,
        'Se non vedi la voce "Pasto Aziendale" nel menu, la tua azienda non ha (ancora) attivato la convenzione, '
        'oppure il tuo account non è stato associato: chiedi al referente aziendale o all\'amministratore del locale.',
        bg='EBF5FB', border=HEX_TEAL, icon='ℹ️')


# ══════════════════════════════════════════════════════════════════════════════
# SEZIONE 9 — NOTIFICHE TELEGRAM
# ══════════════════════════════════════════════════════════════════════════════

def s9_notifiche(doc):
    h1(doc, '9', 'Notifiche Telegram', '🔔', accent=HEX_PURPL)

    body_para(doc, 'QuickLunch può avvisarti via Telegram quando confermi un ordine, quando lo annulli '
              'o quando prenoti un pasto aziendale — senza bisogno di tenere l\'app aperta.')
    spacer(doc, 6)

    data_table(doc,
        ['Quando ricevi una notifica', 'Cosa contiene'],
        [
            ['Conferma ordine',     'Codice ordine, orario di ritiro, totale pagato'],
            ['Annullamento ordine', 'Numero ordine e importo rimborsato'],
            ['Prenotazione pasto aziendale', 'Nome del piatto, azienda, data'],
        ],
        col_widths=[7.0, 10.6])
    spacer(doc, 8)

    info_box(doc, 'Il collegamento con Telegram viene impostato dallo staff del locale sul tuo profilo cliente: '
             'se vuoi ricevere le notifiche, comunica al cassiere o all\'amministratore il tuo contatto Telegram. '
             'Se non lo colleghi, l\'app funziona comunque normalmente: controlla semplicemente "I Miei Ordini" per gli aggiornamenti.',
             style='tip')


# ══════════════════════════════════════════════════════════════════════════════
# SEZIONE 10 — DOMANDE FREQUENTI
# ══════════════════════════════════════════════════════════════════════════════

def s10_faq(doc):
    h1(doc, '10', 'Domande frequenti', '❓', accent=HEX_PURPL)

    faqs = [
        ('Ho dimenticato la password, cosa faccio?',
         'L\'app non ha ancora il "recupero password" automatico: chiedi all\'amministratore del locale di reimpostartela dal pannello clienti.'),
        ('"Saldo wallet insufficiente": cosa significa?',
         'Il tuo credito wallet è inferiore al totale dell\'ordine. Chiedi al cassiere una ricarica, poi torna nel carrello: i prodotti restano salvati.'),
        ('Posso pagare in contanti o con carta dall\'app?',
         'No: i pagamenti sull\'app passano sempre dal wallet. Per pagare in contanti o carta, ordina direttamente alla cassa con il cassiere.'),
        ('Ho sbagliato a confermare un ordine, posso annullarlo?',
         'Sì, finché è in stato "Confermato" (vedi Sezione 4.2). Una volta "In preparazione" devi rivolgerti al personale.'),
        ('Il prodotto che voglio non si aggiunge al carrello',
         'Probabilmente è esaurito per oggi (disponibilità a 0). Riprova il giorno successivo o scegli un\'alternativa.'),
        ('Non trovo più uno slot orario libero',
         'Gli slot hanno un numero massimo di ordini: se sono pieni, scegline un altro vicino o prova a ordinare un po\' prima/dopo.'),
        ('Il tavolo che volevo è bloccato per quello slot',
         'Significa che è già prenotato da un altro cliente: scegli un altro tavolo o un altro slot orario.'),
        ('Ho votato per sbaglio l\'opzione sbagliata nel sondaggio',
         'Il voto è definitivo e non modificabile dal cliente: contatta l\'amministratore del locale se serve una correzione.'),
        ('Non vedo "Pasto Aziendale" nel menu',
         'La tua azienda non ha una convenzione attiva oppure il tuo account non è ancora collegato: parla con il referente aziendale.'),
        ('Un ordine annullato, quando rivedo i soldi sul wallet?',
         'Il rimborso è immediato e automatico: lo trovi subito nello storico transazioni in Wallet & Fedeltà.'),
    ]

    for i, (q, a) in enumerate(faqs):
        h3(doc, f'{i+1}.  {q}', color=PURPL)
        body_para(doc, a, size=13)
        if i < len(faqs) - 1:
            spacer(doc, 4)


# ══════════════════════════════════════════════════════════════════════════════
# SEZIONE 11 — SCHEDA RIASSUNTIVA
# ══════════════════════════════════════════════════════════════════════════════

def s11_riassunto(doc):
    h1(doc, '11', 'Scheda riassuntiva rapida', '🧭', accent=HEX_PURPL)

    body_para(doc, 'Tieni questa pagina come riferimento veloce: ogni azione e dove trovarla nel menu laterale.')
    spacer(doc, 6)

    data_table(doc,
        ['Voglio...', 'Dove vado', 'Sezione'],
        [
            ['Registrarmi o accedere',          'Pagina di login / "Registrati"',          '1'],
            ['Ordinare dal menu',                'Menu',                                    '2'],
            ['Pagare un ordine',                 'Carrello → Conferma ordine',              '2'],
            ['Comporre un panino/insalata/poke', 'Componi il tuo piatto',                   '3'],
            ['Vedere i miei ordini passati',     'I Miei Ordini',                           '4'],
            ['Annullare un ordine',              'I Miei Ordini → Annulla',                 '4'],
            ['Vedere saldo e punti',             'Wallet & Fedeltà',                        '5'],
            ['Ricaricare il wallet',             'Chiedi al cassiere',                      '5'],
            ['Riscattare punti fedeltà',         'Wallet & Fedeltà → Riscatta',              '5'],
            ['Prenotare un tavolo',              'Tavoli',                                  '6'],
            ['Vedere/annullare prenotazioni',    'Le Mie Prenotazioni',                     '6'],
            ['Votare un sondaggio',              'Vota il Menu',                            '7'],
            ['Prenotare il pasto aziendale',     'Pasto Aziendale',                         '8'],
        ],
        col_widths=[6.5, 6.5, 4.6])
    spacer(doc, 10)

    info_box_color(doc,
        'Hai letto tutta la guida? Allora sai già fare tutto quello che serve: ordinare, pagare, '
        'prenotare un tavolo e usare i tuoi punti fedeltà, da solo, senza bisogno di chiedere aiuto. '
        'Buon pranzo! 🍽️',
        bg='F4ECF7', border=HEX_PURPL, icon='🎉')


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    doc = Document()
    set_document_defaults(doc)

    build_cover_cliente(doc)
    _page_break(doc)

    build_toc_cliente(doc)
    _page_break(doc)

    s1_iniziare(doc)
    _page_break(doc)

    s2_ordinare(doc)
    _page_break(doc)

    s3_builder(doc)
    _page_break(doc)

    s4_ordini(doc)
    _page_break(doc)

    s5_wallet(doc)
    _page_break(doc)

    s6_tavoli(doc)
    _page_break(doc)

    s7_sondaggi(doc)
    _page_break(doc)

    s8_pasto_aziendale(doc)
    _page_break(doc)

    s9_notifiche(doc)
    _page_break(doc)

    s10_faq(doc)
    _page_break(doc)

    s11_riassunto(doc)

    doc.save(OUT)
    print(f'OK  Guida cliente salvata in: {OUT}')


if __name__ == '__main__':
    main()
