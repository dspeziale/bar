# -*- coding: utf-8 -*-
"""Locandina A4 con il QR di registrazione, nel kit grafico dei manuali.

Un foglio da appendere al banco: che cos'è QuickLunch in poche righe, il QR
che porta alla registrazione del locale, i tre passi per iscriversi. Viene
generata dall'applicazione con l'indirizzo vero di registrazione e i dati
dell'azienda, quindi è sempre aggiornata: non c'è un file da tenere al passo.

Stesso impianto dei manuali (PT Sans Narrow, banda navy, filetto rosso). Il
QR è disegnato come rettangoli vettoriali a partire dalla matrice di
`qrcode`, così resta nitido a qualsiasi dimensione e non serve un'immagine.
"""
import os

from fpdf import FPDF

NAVY = (15, 52, 96)
RED = (233, 69, 96)
DARK = (26, 26, 46)
DGRAY = (84, 88, 96)
MGRAY = (140, 145, 155)
LGRAY = (214, 218, 224)
GREEN = (39, 152, 96)
BLUE = (46, 128, 186)
ORANGE = (214, 122, 32)
WHITE = (255, 255, 255)
FONT = 'PTSansNarrow'
FONT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'fonts')
ML, MR = 16, 16
W = 210 - ML - MR


def _pulisci(testo):
    """PT Sans Narrow non ha alcuni glifi: si sostituiscono con equivalenti."""
    return (testo or '').replace('→', '>').replace('›', '>').replace('✓', 'v').replace('’', "'")


def _matrice_qr(url):
    import qrcode
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, border=0)
    qr.add_data(url)
    qr.make(fit=True)
    return qr.get_matrix()


def _disegna_qr(pdf, url, x, y, lato):
    """Il QR come quadratini pieni: vettoriale, nitido in stampa."""
    matrice = _matrice_qr(url)
    n = len(matrice)
    modulo = lato / float(n)
    pdf.set_fill_color(*DARK)
    for r, riga in enumerate(matrice):
        for c, acceso in enumerate(riga):
            if acceso:
                pdf.rect(x + c * modulo, y + r * modulo, modulo, modulo, 'F')


def genera_locandina(url_registrazione, nome_locale='', indirizzo='', telefono='',
                     bot='dslunch_bot', wallet_attivo=True, dieta_attiva=True,
                     partita_iva='', email=''):
    """Il PDF della locandina come bytes.

    E' un foglio del locale, non del fornitore: in pie' di pagina vanno i dati
    completi dell'azienda (ragione sociale, indirizzo, partita IVA, telefono,
    email) e nessun riferimento a chi ha fatto l'applicazione.
    """
    pdf = FPDF(format='A4')
    pdf.set_auto_page_break(False)
    pdf.add_font(FONT, '', os.path.join(FONT_DIR, 'PTSansNarrow-Regular.ttf'))
    pdf.add_font(FONT, 'B', os.path.join(FONT_DIR, 'PTSansNarrow-Bold.ttf'))
    pdf.add_page()
    nome_locale = _pulisci(nome_locale) or 'il tuo bar'

    # ── Banda navy in testa ──────────────────────────────────────────────
    pdf.set_fill_color(*NAVY)
    pdf.rect(0, 0, 210, 74, 'F')
    pdf.set_fill_color(*RED)
    pdf.rect(0, 74, 210, 2.4, 'F')
    pdf.set_text_color(178, 194, 217)
    pdf.set_font(FONT, 'B', 12)
    pdf.set_xy(ML, 14)
    pdf.cell(0, 6, 'QUICKLUNCH · %s' % nome_locale.upper())
    pdf.set_text_color(*WHITE)
    pdf.set_font(FONT, 'B', 38)
    pdf.set_xy(ML, 24)
    pdf.cell(0, 16, 'Il pranzo, senza coda.')
    pdf.set_font(FONT, '', 14)
    pdf.set_text_color(214, 223, 234)
    pdf.set_xy(ML, 43)
    pdf.multi_cell(W, 7, _pulisci(
        'Ordini dal telefono quando vuoi, scegli l\'orario in cui passi a ritirare e '
        'trovi tutto pronto. Registrarsi e gratuito e richiede un minuto: inquadra il '
        'codice qui sotto.'))

    # ── Colonna sinistra: che cos'e ──────────────────────────────────────
    y0 = 86
    col_sx = 104
    pdf.set_xy(ML, y0)
    pdf.set_font(FONT, 'B', 17)
    pdf.set_text_color(*NAVY)
    pdf.cell(col_sx, 8, 'Che cos\'e QuickLunch')
    pdf.set_draw_color(*RED)
    pdf.set_line_width(0.6)
    pdf.line(ML, y0 + 9.5, ML + 34, y0 + 9.5)

    voci = [
        ('Il menu del giorno sul telefono', 'con allergeni e valori nutrizionali di ogni piatto, '
         'e la disponibilita in tempo reale.'),
        ('Ordini all\'orario che vuoi', 'scegli lo slot di ritiro fra quelli liberi: al banco '
         'trovi tutto pronto, senza fila.'),
        ('Panino, insalata o poke su misura', 'ingrediente per ingrediente, con il prezzo e '
         'le calorie che si aggiornano mentre componi.'),
        ('Avvisi sul telefono', 'quando l\'ordine e in preparazione e quando e pronto, su '
         'Telegram (@%s) o con una notifica.' % _pulisci(bot)),
        ('Il pasto aziendale', 'se la tua azienda e convenzionata: prenoti il menu del '
         'giorno e ritiri con il tuo codice.'),
    ]
    if dieta_attiva:
        voci.append(('La tua dieta, se vuoi', 'dichiari esigenze e gusti e ricevi un piano '
                     'dei pranzi della settimana da ordinare con un tocco.'))
    voci.append(('Il pagamento', 'con il portafoglio prepagato che ricarichi in cassa, e i punti '
                 'fedelta che maturano da soli.' if wallet_attivo else
                 'comodo: ordini dall\'app e paghi alla cassa quando ritiri.'))

    y = y0 + 15
    for titolo, corpo in voci:
        pdf.set_fill_color(*RED)
        pdf.rect(ML, y + 1.6, 2.2, 2.2, 'F')
        pdf.set_xy(ML + 5, y)
        pdf.set_font(FONT, 'B', 11.5)
        pdf.set_text_color(*DARK)
        pdf.cell(col_sx - 5, 5.6, _pulisci(titolo))
        pdf.set_xy(ML + 5, y + 5.4)
        pdf.set_font(FONT, '', 10.5)
        pdf.set_text_color(*DGRAY)
        pdf.multi_cell(col_sx - 5, 5, _pulisci(corpo))
        y = pdf.get_y() + 3.2

    # ── Colonna destra: il QR ────────────────────────────────────────────
    x_dx = ML + col_sx + 6
    larg_dx = W - col_sx - 6
    pdf.set_fill_color(247, 248, 251)
    pdf.set_draw_color(*LGRAY)
    pdf.set_line_width(0.3)
    pdf.rect(x_dx, y0, larg_dx, 112, 'DF')
    pdf.set_xy(x_dx, y0 + 6)
    pdf.set_font(FONT, 'B', 15)
    pdf.set_text_color(*NAVY)
    pdf.cell(larg_dx, 7, 'Inquadra e registrati', align='C')
    lato = 50
    _disegna_qr(pdf, url_registrazione, x_dx + (larg_dx - lato) / 2, y0 + 17, lato)
    pdf.set_xy(x_dx + 4, y0 + 71)
    pdf.set_font(FONT, '', 9)
    pdf.set_text_color(*MGRAY)
    pdf.multi_cell(larg_dx - 8, 4.4, 'Oppure apri dal browser:', align='C')
    pdf.set_x(x_dx + 4)
    pdf.set_font(FONT, 'B', 9.5)
    pdf.set_text_color(*BLUE)
    pdf.multi_cell(larg_dx - 8, 4.6, _pulisci(url_registrazione), align='C')
    pdf.set_x(x_dx + 4)
    pdf.set_font(FONT, '', 9)
    pdf.set_text_color(*MGRAY)
    pdf.multi_cell(larg_dx - 8, 4.4, 'Con Google in un tocco, oppure con email e password.',
                   align='C')

    # ── I tre passi ──────────────────────────────────────────────────────
    y = max(y, y0 + 118) + 4
    pdf.set_xy(ML, y)
    pdf.set_font(FONT, 'B', 17)
    pdf.set_text_color(*NAVY)
    pdf.cell(W, 8, 'Tre passi')
    pdf.set_draw_color(*RED)
    pdf.set_line_width(0.6)
    pdf.line(ML, y + 9.5, ML + 34, y + 9.5)
    y += 15
    passi = [
        ('Inquadra il QR', 'Si apre la pagina di registrazione di %s.' % nome_locale, GREEN),
        ('Registrati', 'Con l\'account Google in un tocco, o con nome, email e una password.', BLUE),
        ('Attendi l\'attivazione', 'Il personale attiva il tuo account in giornata: ricevi '
         'un\'email con la guida e da quel momento puoi ordinare.', ORANGE),
    ]
    larg = (W - 8) / 3
    for i, (titolo, corpo, colore) in enumerate(passi):
        x = ML + i * (larg + 4)
        pdf.set_fill_color(*colore)
        pdf.rect(x, y, 9, 9, 'F')
        pdf.set_xy(x, y + 1.6)
        pdf.set_font(FONT, 'B', 11)
        pdf.set_text_color(*WHITE)
        pdf.cell(9, 5.5, str(i + 1), align='C')
        pdf.set_xy(x + 12, y + 0.5)
        pdf.set_font(FONT, 'B', 11.5)
        pdf.set_text_color(*DARK)
        pdf.cell(larg - 12, 5.5, _pulisci(titolo))
        pdf.set_xy(x, y + 12)
        pdf.set_font(FONT, '', 10)
        pdf.set_text_color(*DGRAY)
        pdf.multi_cell(larg, 4.8, _pulisci(corpo))

    # ── Riquadro finale e pie' di pagina ─────────────────────────────────
    y = 246
    pdf.set_fill_color(240, 250, 244)
    pdf.set_draw_color(*GREEN)
    pdf.set_line_width(0.4)
    pdf.rect(ML, y, W, 20, 'DF')
    pdf.set_fill_color(*GREEN)
    pdf.rect(ML, y, 2.2, 20, 'F')
    pdf.set_xy(ML + 6, y + 3)
    pdf.set_font(FONT, 'B', 12)
    pdf.set_text_color(*GREEN)
    pdf.cell(W - 8, 6, 'Registrarsi e gratuito. Nessun costo, nessun abbonamento.')
    pdf.set_xy(ML + 6, y + 10)
    pdf.set_font(FONT, '', 10)
    pdf.set_text_color(*DGRAY)
    pdf.multi_cell(W - 8, 4.8, _pulisci(
        'I tuoi dati restano al locale e servono solo per il servizio. Per qualsiasi '
        'dubbio, chiedi al banco: siamo qui.'))

    # Pie' di pagina: i dati completi dell'azienda, e nulla di chi ha fatto l'app.
    pdf.set_draw_color(*LGRAY)
    pdf.set_line_width(0.2)
    pdf.line(ML, 273, 210 - MR, 273)
    pdf.set_xy(ML, 275)
    pdf.set_font(FONT, 'B', 11)
    pdf.set_text_color(*NAVY)
    pdf.cell(W, 5.5, nome_locale)
    riga1 = ' · '.join(p for p in (_pulisci(indirizzo),
                                   ('P. IVA %s' % _pulisci(partita_iva)) if partita_iva else '') if p)
    riga2 = ' · '.join(p for p in (('Tel. %s' % _pulisci(telefono)) if telefono else '',
                                   _pulisci(email)) if p)
    pdf.set_font(FONT, '', 9.5)
    pdf.set_text_color(*DGRAY)
    y_f = 281
    for riga in (riga1, riga2):
        if riga:
            pdf.set_xy(ML, y_f)
            pdf.cell(W, 4.6, riga)
            y_f += 4.6
    pdf.set_xy(ML, 290)
    pdf.set_font(FONT, '', 7.5)
    pdf.set_text_color(*MGRAY)
    pdf.cell(W, 4, 'Servizio di ordinazione e ritiro QuickLunch')

    return bytes(pdf.output())
