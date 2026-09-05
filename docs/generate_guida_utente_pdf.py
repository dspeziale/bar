#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Genera docs/manuali/guida_utente.pdf — la guida per ruolo, impaginata.

PDF nativo (fpdf2), non una conversione: copertina, indice con i numeri di
pagina veri, una sezione a colori per ogni ruolo, riquadri e tabelle. Stesso
impianto del catalogo delle stampe, con il kit grafico del progetto
(PT Sans Narrow, palette rosso/blu).

    python docs/generate_guida_utente_pdf.py

L'indice ha i numeri di pagina reali: il documento viene costruito due volte,
la prima per sapere dove cadono i titoli, la seconda per stamparli. La pagina
dell'indice e' sempre una, quindi fra i due passaggi nulla si sposta.
"""

import os
import sys

from fpdf import FPDF

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'docs', 'manuali', 'guida_utente.pdf')
FONT_DIR = os.path.join(ROOT, 'app', 'static', 'fonts')

# ── Kit grafico ──────────────────────────────────────────────────────────────
RED = (233, 69, 96)
NAVY = (15, 52, 96)
DARK = (26, 26, 46)
DGRAY = (84, 88, 96)
MGRAY = (140, 145, 155)
LGRAY = (214, 218, 224)
VLIGHT = (247, 248, 251)
WHITE = (255, 255, 255)
GREEN = (39, 152, 96)
ORANGE = (214, 122, 32)
BLUE = (46, 128, 186)
PURPLE = (128, 74, 160)
TEAL = (32, 138, 138)
FONT = 'PTSansNarrow'

EMAIL = 'dspeziale@gmail.com'
CELL = '+39 352 0150489'
CONTATTI = 'DS Consulting · Daniele Speziale · %s · %s' % (EMAIL, CELL)

ML, MR = 16, 16                      # margini laterali
W = 210 - ML - MR                    # larghezza utile: 178 mm


class Guida(FPDF):
    """Pagina con intestazione della sezione corrente e pie' di pagina."""

    sezione = ''
    etichetta_testata = 'QuickLunch · Guida utente'

    def header(self):
        if self.page_no() <= 2:       # copertina e indice restano puliti
            return
        self.set_y(9)
        self.set_font(FONT, '', 8)
        self.set_text_color(*MGRAY)
        self.cell(W / 2, 4, self.etichetta_testata)
        self.set_font(FONT, 'B', 8)
        self.set_text_color(*NAVY)
        self.cell(W / 2, 4, self.sezione, align='R')
        self.ln(5)
        self.set_draw_color(*LGRAY)
        self.set_line_width(0.2)
        self.line(ML, self.get_y(), 210 - MR, self.get_y())
        self.ln(4)

    def footer(self):
        if self.page_no() == 1:
            return
        self.set_y(-15)
        self.set_draw_color(*LGRAY)
        self.set_line_width(0.2)
        self.line(ML, self.get_y(), 210 - MR, self.get_y())
        self.ln(1.6)
        self.set_font(FONT, '', 7.5)
        self.set_text_color(*MGRAY)
        self.cell(W * 0.72, 4, '© 2024–26 DS Consulting  ·  ' + CONTATTI)
        self.set_font(FONT, 'B', 8)
        self.set_text_color(*NAVY)
        self.cell(W * 0.28, 4, '%d' % self.page_no(), align='R')


# ═════════════════════════════════════════════════════════════════════════════
#  Mattoni dell'impaginazione
# ═════════════════════════════════════════════════════════════════════════════

def _spazio(pdf, mm):
    pdf.ln(mm)


def _serve_pagina(pdf, altezza):
    """Va a pagina nuova se il blocco non ci sta: evita titoli orfani."""
    if pdf.get_y() + altezza > 297 - 20:
        pdf.add_page()


def copertina(pdf):
    pdf.add_page()
    pdf.set_fill_color(*NAVY)
    pdf.rect(0, 0, 210, 297, 'F')
    pdf.set_fill_color(*RED)
    pdf.rect(0, 104, 210, 2.4, 'F')

    pdf.set_text_color(*WHITE)
    pdf.set_font(FONT, 'B', 13)
    pdf.set_xy(22, 68)
    pdf.cell(0, 6, 'QUICKLUNCH')
    pdf.set_font(FONT, '', 11)
    pdf.set_xy(22, 76)
    pdf.set_text_color(178, 194, 217)
    pdf.cell(0, 6, 'GUIDA UTENTE · CHI FA CHE COSA')

    pdf.set_text_color(*WHITE)
    pdf.set_font(FONT, 'B', 40)
    pdf.set_xy(22, 86)
    pdf.cell(0, 18, 'Sette ruoli,')
    pdf.set_xy(22, 104)
    pdf.set_font(FONT, 'B', 40)
    pdf.cell(0, 18, 'un servizio')

    pdf.set_xy(22, 132)
    pdf.set_font(FONT, '', 13)
    pdf.set_text_color(214, 223, 234)
    pdf.multi_cell(166, 7,
                   'Ogni persona che tocca QuickLunch — chi governa il '
                   'sistema, chi gestisce il locale, chi sta in cassa, chi '
                   'cucina, chi serve in sala, chi ordina dal telefono e chi '
                   'pranza con la convenzione aziendale — trova qui la sua '
                   'sezione: cosa vede, cosa può fare, dove si trova.')

    # Le sette pastiglie dei ruoli, come anteprima dell'indice
    y = 176
    for i, (nome, colore) in enumerate([
            ('Super admin', RED), ('Gestore', NAVY), ('Cassa', GREEN),
            ('Cucina', ORANGE), ('Sala', TEAL), ('Cliente', BLUE),
            ('Dipendente', PURPLE)]):
        x = 22 + (i % 4) * 42
        if i == 4:
            y += 14
        pdf.set_fill_color(*colore)
        pdf.rect(x, y, 38, 9, 'F')
        pdf.set_xy(x, y + 1.6)
        pdf.set_font(FONT, 'B', 9.5)
        pdf.set_text_color(*WHITE)
        pdf.cell(38, 5, nome, align='C')

    pdf.set_xy(22, 246)
    pdf.set_font(FONT, 'B', 11)
    pdf.set_text_color(*WHITE)
    pdf.cell(0, 6, 'Assistenza')
    pdf.set_xy(22, 253)
    pdf.set_font(FONT, 'B', 11)
    pdf.set_text_color(255, 215, 223)
    pdf.cell(0, 6, CONTATTI)
    pdf.set_xy(22, 264)
    pdf.set_font(FONT, '', 10)
    pdf.set_text_color(178, 194, 217)
    pdf.cell(0, 5, '© 2024–26 DS Consulting')


def pagina_indice(pdf, voci):
    """L'indice su una pagina, due colonne. `voci` = [(livello, testo, pag)]."""
    pdf.add_page()
    pdf.set_y(20)
    pdf.set_x(ML)
    pdf.set_font(FONT, 'B', 22)
    pdf.set_text_color(*NAVY)
    pdf.cell(0, 11, 'Indice')
    pdf.ln(12)
    pdf.set_draw_color(*RED)
    pdf.set_line_width(0.6)
    pdf.line(ML, pdf.get_y(), ML + 40, pdf.get_y())
    pdf.ln(6)

    pdf.set_x(ML)
    pdf.set_font(FONT, '', 10)
    pdf.set_text_color(*DGRAY)
    pdf.multi_cell(W, 5,
                   'Ogni ruolo ha la sua sezione: si legge solo la propria. '
                   'Le sezioni sono indipendenti, quindi la guida si può '
                   'anche stampare a pezzi e consegnare a chi serve.')
    pdf.ln(5)

    if not voci:
        return

    # Due colonne: si spezza dopo la metà delle voci, senza dividere una
    # sezione dalle sue sottovoci.
    meta = (len(voci) + 1) // 2
    while meta < len(voci) and voci[meta][0] == 2:
        meta += 1
    colonne = [voci[:meta], voci[meta:]]
    y0 = pdf.get_y()
    larghezza = (W - 8) / 2

    for ci, colonna in enumerate(colonne):
        x = ML + ci * (larghezza + 8)
        pdf.set_y(y0)
        for livello, testo, pagina in colonna:
            pdf.set_x(x)
            if livello == 1:
                pdf.ln(1.6)
                pdf.set_x(x)
                pdf.set_font(FONT, 'B', 10.5)
                pdf.set_text_color(*NAVY)
            else:
                pdf.set_font(FONT, '', 9.5)
                pdf.set_text_color(*DGRAY)
            etichetta = testo if livello == 1 else '    ' + testo
            largh_testo = larghezza - 10
            pdf.cell(largh_testo, 5.2, etichetta[:52])
            pdf.set_font(FONT, 'B' if livello == 1 else '', 9.5)
            pdf.set_text_color(*(NAVY if livello == 1 else MGRAY))
            pdf.cell(10, 5.2, str(pagina), align='R')
            pdf.ln(5.2)


def apri_sezione(pdf, numero, titolo, sottotitolo, colore, a_chi_serve,
                 indice):
    """Apertura di sezione: banda colorata a piena larghezza."""
    pdf.add_page()
    pdf.sezione = titolo
    indice.append((1, '%s. %s' % (numero, titolo), pdf.page_no()))

    pdf.set_fill_color(*colore)
    pdf.rect(0, 0, 210, 52, 'F')
    pdf.set_fill_color(*RED)
    pdf.rect(0, 52, 210, 1.8, 'F')

    pdf.set_text_color(255, 255, 255)
    pdf.set_font(FONT, 'B', 34)
    pdf.set_xy(ML, 11)
    pdf.cell(20, 16, str(numero))
    pdf.set_font(FONT, 'B', 24)
    pdf.set_xy(ML + 20, 14)
    pdf.cell(0, 11, titolo)
    pdf.set_font(FONT, '', 11.5)
    pdf.set_xy(ML + 20, 27)
    pdf.multi_cell(W - 20, 5.6, sottotitolo)

    pdf.set_y(62)
    pdf.set_x(ML)
    pdf.set_fill_color(*VLIGHT)
    pdf.set_draw_color(*LGRAY)
    pdf.set_font(FONT, 'B', 9)
    pdf.set_text_color(*colore)
    pdf.cell(W, 6.5, '  A CHI SERVE QUESTA SEZIONE', fill=True)
    pdf.ln(6.5)
    pdf.set_x(ML)
    pdf.set_font(FONT, '', 10.5)
    pdf.set_text_color(*DARK)
    pdf.multi_cell(W, 5.2, '  ' + a_chi_serve, fill=True)
    pdf.ln(7)


def h2(pdf, testo, colore, indice=None):
    _serve_pagina(pdf, 26)
    if indice is not None:
        indice.append((2, testo, pdf.page_no()))
    pdf.ln(2)
    pdf.set_x(ML)
    pdf.set_fill_color(*colore)
    pdf.rect(ML, pdf.get_y() + 1.2, 2.6, 5.4, 'F')
    pdf.set_x(ML + 5)
    pdf.set_font(FONT, 'B', 13)
    pdf.set_text_color(*NAVY)
    pdf.cell(0, 8, testo)
    pdf.ln(9.4)


def testo(pdf, corpo, dimensione=10.5):
    pdf.set_x(ML)
    pdf.set_font(FONT, '', dimensione)
    pdf.set_text_color(*DGRAY)
    pdf.multi_cell(W, 5, corpo)
    pdf.ln(2.4)


def elenco(pdf, voci):
    """Elenco con il pallino disegnato: il font non ha i bullet."""
    pdf.set_font(FONT, '', 10.5)
    for voce in voci:
        _serve_pagina(pdf, 12)
        y = pdf.get_y()
        pdf.set_fill_color(*RED)
        pdf.ellipse(ML + 1.6, y + 1.9, 1.5, 1.5, 'F')
        pdf.set_x(ML + 6)
        if isinstance(voce, tuple):
            grassetto, resto = voce
            pdf.set_font(FONT, 'B', 10.5)
            pdf.set_text_color(*DARK)
            larghezza_g = pdf.get_string_width(grassetto)
            pdf.cell(larghezza_g, 5, grassetto)
            pdf.set_font(FONT, '', 10.5)
            pdf.set_text_color(*DGRAY)
            pdf.multi_cell(W - 6 - larghezza_g, 5, resto)
        else:
            pdf.set_font(FONT, '', 10.5)
            pdf.set_text_color(*DGRAY)
            pdf.multi_cell(W - 6, 5, voce)
        pdf.ln(0.8)
    pdf.ln(1.6)


def passi(pdf, elenco_passi, colore):
    """Passi numerati: pastiglia col numero e testo accanto."""
    for i, (titolo, corpo) in enumerate(elenco_passi, 1):
        _serve_pagina(pdf, 20)
        y = pdf.get_y()
        pdf.set_fill_color(*colore)
        pdf.rect(ML, y, 8, 8, 'F')
        pdf.set_xy(ML, y + 1.4)
        pdf.set_font(FONT, 'B', 10.5)
        pdf.set_text_color(*WHITE)
        pdf.cell(8, 5, str(i), align='C')

        pdf.set_xy(ML + 12, y)
        pdf.set_font(FONT, 'B', 11)
        pdf.set_text_color(*DARK)
        pdf.multi_cell(W - 12, 5.2, titolo)
        pdf.set_x(ML + 12)
        pdf.set_font(FONT, '', 10.5)
        pdf.set_text_color(*DGRAY)
        pdf.multi_cell(W - 12, 5, corpo)
        pdf.ln(2.6)
    pdf.ln(1)


def tabella(pdf, intestazioni, righe, larghezze, colore):
    """Tabella a righe alternate; l'ultima colonna va a capo se serve."""
    _serve_pagina(pdf, 24)
    scala = W / float(sum(larghezze))
    larghezze = [l * scala for l in larghezze]

    pdf.set_x(ML)
    pdf.set_fill_color(*colore)
    pdf.set_text_color(*WHITE)
    pdf.set_font(FONT, 'B', 8.5)
    for i, intest in enumerate(intestazioni):
        pdf.cell(larghezze[i], 7, '  ' + intest.upper(), fill=True)
    pdf.ln(7)

    pdf.set_font(FONT, '', 9.5)
    for n, riga in enumerate(righe):
        # Altezza della riga: la cella piu' alta comanda
        altezze = []
        for i, cella in enumerate(riga):
            pdf.set_font(FONT, 'B' if i == 0 else '', 9.5)
            linee = pdf.multi_cell(larghezze[i] - 3, 4.6, str(cella),
                                   dry_run=True, output='LINES')
            altezze.append(len(linee) * 4.6 + 2.6)
        alta = max(altezze)
        _serve_pagina(pdf, alta + 4)

        y = pdf.get_y()
        pdf.set_fill_color(*(VLIGHT if n % 2 == 0 else WHITE))
        pdf.rect(ML, y, W, alta, 'F')
        x = ML
        for i, cella in enumerate(riga):
            pdf.set_xy(x + 1.6, y + 1.3)
            pdf.set_font(FONT, 'B' if i == 0 else '', 9.5)
            pdf.set_text_color(*(DARK if i == 0 else DGRAY))
            pdf.multi_cell(larghezze[i] - 3, 4.6, str(cella))
            x += larghezze[i]
        pdf.set_draw_color(*LGRAY)
        pdf.set_line_width(0.15)
        pdf.line(ML, y + alta, ML + W, y + alta)
        pdf.set_y(y + alta)
    pdf.ln(4)


def callout(pdf, etichetta, corpo, colore=ORANGE, fondo=(253, 246, 231)):
    _serve_pagina(pdf, 24)
    pdf.set_x(ML)
    y0 = pdf.get_y()
    pdf.set_fill_color(*fondo)
    pdf.set_font(FONT, 'B', 8.5)
    pdf.set_text_color(*colore)
    pdf.set_xy(ML + 4, y0 + 1.8)
    pdf.cell(W - 8, 4.6, etichetta.upper(), fill=False)
    pdf.set_xy(ML + 4, y0 + 6.6)
    pdf.set_font(FONT, '', 10)
    pdf.set_text_color(*DARK)
    pdf.multi_cell(W - 8, 4.8, corpo)
    fine = pdf.get_y() + 2
    # Il fondo si disegna dopo, per conoscere l'altezza: si ridisegna il testo
    # sopra un rettangolo colorato.
    pdf.set_fill_color(*fondo)
    pdf.rect(ML, y0, W, fine - y0, 'F')
    pdf.set_fill_color(*colore)
    pdf.rect(ML, y0, 2.2, fine - y0, 'F')
    pdf.set_xy(ML + 5.5, y0 + 1.8)
    pdf.set_font(FONT, 'B', 8.5)
    pdf.set_text_color(*colore)
    pdf.cell(W - 10, 4.6, etichetta.upper())
    pdf.set_xy(ML + 5.5, y0 + 6.6)
    pdf.set_font(FONT, '', 10)
    pdf.set_text_color(*DARK)
    pdf.multi_cell(W - 10, 4.8, corpo)
    pdf.set_y(fine + 3)


# ═════════════════════════════════════════════════════════════════════════════
#  Le sezioni, una per ruolo
# ═════════════════════════════════════════════════════════════════════════════

def sez_super_admin(pdf, idx):
    C = RED
    apri_sezione(pdf, 1, 'Super admin', 'Governa la piattaforma: locali, '
                 'condizioni economiche, funzioni attive, dati.', C,
                 'A chi amministra QuickLunch per conto di DS Consulting, non '
                 'al personale del bar. E il solo ruolo che vede piu locali e '
                 'i conti della piattaforma.', idx)

    h2(pdf, 'Che cosa vede solo lui', C, idx)
    elenco(pdf, [
        ('Guadagni DS Consulting: ', 'canone mensile e quota sugli incassi, '
         'con il dettaglio delle transazioni del mese e il PDF da allegare '
         'alla fattura.'),
        ('Locali (tenant): ', 'ogni bar ha il suo spazio, i suoi clienti e il '
         'suo catalogo. Il super admin senza locale assegnato lavora sul '
         'locale predefinito.'),
        ('Strumenti sui dati: ', 'carico di prova di un mese, azzeramento '
         'completo del database, backup e ripristino.'),
        ('Funzionalita attivabili: ', 'tavoli, cesto, portafoglio prepagato '
         'e dieta settimanale si accendono e si spengono da un interruttore.'),
    ])

    h2(pdf, 'Le quattro funzioni che cambiano il volto dell\'app', C, idx)
    tabella(pdf, ['Interruttore', 'Se spento', 'Dove'],
            [['Gestione tavoli', 'Spariscono prenotazioni e piantina della '
              'sala, per chi fa solo asporto.',
              'Impostazioni > Funzionalita'],
             ['Cesto cucina', 'Niente etichette QR ne acquisto self-service; '
              'le vendite passate restano nei report.',
              'Impostazioni > Funzionalita'],
             ['Portafoglio prepagato', 'L\'app non muove denaro: nessun '
              'saldo, ricarica o punto, si paga alla cassa. Le vendite '
              'restano registrate.', 'Impostazioni > Funzionalita'],
             ['Dieta settimanale', 'Spariscono la pagina del cliente, i '
              'giudizi nel menu e nel carrello e la pagina Diete clienti; le '
              'preferenze salvate restano.', 'Impostazioni > Funzionalita']],
            [30, 48, 26], C)

    callout(pdf, 'Prima di aprire al pubblico',
            'Il primo avvio crea due utenze amministrative con password '
            'predefinite: cambiale subito, insieme alla chiave di sicurezza '
            'dell\'ambiente. Il backup scaricabile contiene dati personali '
            'dei clienti e credenziali di servizio: conservalo come un '
            'registro contabile.', RED, (253, 238, 240))

    h2(pdf, 'Dati di prova e azzeramento', C, idx)
    passi(pdf, [
        ('Carica un mese di prova',
         'Impostazioni > Dati genera un mese di attivita verosimile - pasti '
         'aziendali, ordini, caffe al banco, prodotti del builder - con le '
         'quantita giornaliere che decidi. Serve a vedere report e andamenti '
         'prima di avere dati veri.'),
        ('Elimina il carico quando hai finito',
         'Ogni carico resta elencato e si cancella per intero con un '
         'pulsante: non lascia residui e non tocca i saldi.'),
        ('Azzera il database una volta sola',
         'Il passaggio dalla prova al servizio reale: svuota tutto e ricrea '
         'i dati di base, catalogo compreso. Chiede di scrivere AZZERA e '
         'riporta le utenze amministrative ai valori predefiniti.'),
    ], C)

    h2(pdf, 'Backup e ripristino', C, idx)
    passi(pdf, [
        ('Scarica il backup ogni settimana',
         'Un solo file JSON con tutte le tabelle: clienti, ordini, catalogo '
         'con i valori nutrizionali, convenzioni, diete, impostazioni. La '
         'pagina mostra la data dell\'ultimo backup e il venerdi, se ne sono '
         'passati piu di sei giorni, il canale Telegram dello staff riceve un '
         'promemoria. Il file contiene dati personali e credenziali: va '
         'conservato fuori dal server, come un registro contabile.'),
        ('Guarda l\'anteprima prima di ripristinare',
         'Scelto il file, la pagina dice quando e stato creato, quante '
         'tabelle e righe contiene, e avvisa se e vecchio o precedente a una '
         'funzione: in quel caso il contenuto attuale di quella funzione '
         'andrebbe perso.'),
        ('Ripristina a locale chiuso',
         'Prima di cancellare, lo stato attuale viene inviato per email a chi '
         'ripristina: se l\'invio non riesce ci si ferma, salvo scelta '
         'esplicita di procedere. Al termine il messaggio elenca righe '
         'caricate, tabelle svuotate e colonne ignorate, e si viene '
         'disconnessi perche anche gli utenti sono stati sostituiti. I dati '
         'di base (permessi, impostazioni, valori nutrizionali del listino) '
         'vengono ricontrollati subito, come all\'avvio.'),
    ], C)


def sez_gestore(pdf, idx):
    C = NAVY
    apri_sezione(pdf, 2, 'Gestore del locale', 'Il catalogo, il servizio, le '
                 'convenzioni, i clienti, i numeri della giornata.', C,
                 'Al titolare e a chi amministra il bar. E il ruolo con piu '
                 'pagine: qui c\'e tutto quello che si decide prima che il '
                 'servizio cominci.', idx)

    h2(pdf, 'Il catalogo', C, idx)
    testo(pdf, 'L\'installazione parte con 18 categorie e un listino di '
               'circa 75 prodotti da bar caffetteria con mensa, ognuno con '
               'prezzo, quantita giornaliera e allergeni. Il lavoro e di '
               'correzione, non di creazione: disattiva quello che non '
               'vendi, allinea i prezzi e aggiungi le tue specialita.')
    elenco(pdf, [
        ('Prodotti: ', 'nome, categoria, prezzo, quantita del giorno, '
         'allergeni e codice a barre.'),
        ('Disponibilita del giorno: ', 'la pagina Stock parte dalla quantita '
         'di listino e va corretta con quello che hai davvero prodotto. E '
         'l\'unico numero che impedisce di vendere pezzi che non esistono.'),
        ('Ingredienti del builder: ', 'pane, proteine, verdure, salse ed '
         'extra, con le scorte per singolo ingrediente.'),
        ('Slot di ritiro: ', 'otto fasce da 11:45 a 13:30 ogni quarto d\'ora, '
         'con la capienza in ordini. Disattiva quelle che non usi.'),
    ])

    h2(pdf, 'Le convenzioni aziendali', C, idx)
    passi(pdf, [
        ('Pubblica il menu del giorno',
         'Convenzioni > Pasto del giorno: primo, secondo, contorno, bevanda, '
         'caffe, allergeni, prezzo e coperti massimi. I menu ricorrenti si '
         'salvano come modelli.'),
        ('Lascia prenotare i dipendenti',
         'Prenotano dal telefono e possono disdire fino a 30 minuti prima '
         'dell\'orario scelto: la cucina lavora su numeri veri.'),
        ('Stampa la lista di produzione',
         'Elenco nominativo per azienda, ordinato per cognome. I nomi sono '
         'in forma abbreviata - "Mario R." - cosi la lista si puo appendere '
         'in cucina.'),
        ('Chiudi il mese',
         'Il riepilogo mensile in PDF riporta i pasti per dipendente, il '
         'dettaglio giorno per giorno e il totale fatturabile: e pensato '
         'per essere allegato alla fattura.'),
    ], C)

    h2(pdf, 'I clienti', C, idx)
    tabella(pdf, ['Cosa fare', 'Dove', 'Nota'],
            [['Attivare chi si e registrato', 'Clienti > Attiva',
              'Finche non lo attivi non puo entrare. Il contatore e sulla '
              'dashboard.'],
             ['Associare a una convenzione', 'Clienti > Attiva o Modifica',
              'Da quel momento vede il pasto del giorno della sua azienda.'],
             ['Ricaricare il credito', 'Clienti > Ricarica',
              'Solo con il portafoglio prepagato attivo.'],
             ['Concedere un fido', 'Clienti > Modifica',
              'Consente di ordinare andando in rosso fino alla soglia '
              'scelta.'],
             ['Rimandare l\'email con la guida', 'Clienti > icona busta',
              'Utile se il cliente dice di non aver ricevuto nulla: il '
              'messaggio riporta l\'esito reale dell\'invio.']],
            [34, 32, 38], C)

    callout(pdf, 'Perche un cliente non riceve le email',
            'Serve Gmail configurata in Impostazioni > Notifiche: senza '
            'quella nessuna email parte. Quando un invio non riesce, ora '
            'arriva un avviso sul canale Telegram dello staff con il motivo.',
            ORANGE)

    h2(pdf, 'La giornata in breve', C, idx)
    testo(pdf, 'Il pomeriggio prima si decide cosa si vendera domani; la '
               'mattina si mette in condizione la macchina di funzionare. '
               'La scaletta completa, con gli orari limite di ogni attivita, '
               'e nel Manuale del gestore: qui basta ricordare le tre cose '
               'che, se salti, si vedono.')
    elenco(pdf, [
        'Pubblicare il pasto aziendale del giorno dopo entro il pomeriggio.',
        'Attivare i clienti in attesa, altrimenti domani non possono '
        'ordinare.',
        'Generare le etichette del cesto la mattina stessa: valgono 24 ore.',
    ])


def sez_cassa(pdf, idx):
    C = GREEN
    apri_sezione(pdf, 3, 'Cassa e banco', 'Il conto veloce col QR, le '
                 'ricariche, la consegna.', C,
                 'A chi sta al bancone. Tre gesti in tutto, pensati per '
                 'l\'ora di punta.', idx)

    h2(pdf, 'Il conto al banco con il QR', C, idx)
    passi(pdf, [
        ('Componi il conto sul tablet',
         'Gli articoli rapidi - caffe, cappuccino, brioche - si toccano una '
         'volta. Il totale si aggiorna a ogni tocco.'),
        ('Mostra il QR al cliente',
         'Sullo schermo compare un QR: il cliente lo inquadra col telefono e '
         'vede il riepilogo.'),
        ('Il cliente conferma',
         'Con il portafoglio attivo l\'importo viene scalato dal suo credito '
         'e il tablet mostra "Pagato". Senza portafoglio la consumazione '
         'viene registrata e si incassa in cassa.'),
    ], C)

    callout(pdf, 'Il QR scade',
            'Ogni QR vale pochi minuti: se il cliente tarda, si genera di '
            'nuovo. E una misura di sicurezza, non un difetto.', ORANGE)

    h2(pdf, 'Consegna e ritiro', C, idx)
    elenco(pdf, [
        ('Ordini a slot: ', 'arrivano al banco gia pagati (o da saldare in '
         'cassa, se il portafoglio e spento). Si consegna il pacchetto con '
         'il tagliando e lo scontrino e si segna Consegnato.'),
        ('Pasti aziendali: ', 'il dipendente mostra il suo codice di ritiro; '
         'lo si cerca in Pasti > Ritiro e si conferma la consegna.'),
        ('Ricariche: ', 'si incassa il contante e si carica l\'importo dalla '
         'scheda del cliente. Ogni movimento resta nello storico.'),
    ])


def sez_cucina(pdf, idx):
    C = ORANGE
    apri_sezione(pdf, 4, 'Cucina', 'Il display degli ordini, il cesto, le '
                 'liste di produzione.', C,
                 'A chi prepara. Il display si aggiorna da se e avvisa con '
                 'un suono: va tenuto acceso e con l\'audio attivo.', idx)

    h2(pdf, 'Il display degli ordini', C, idx)
    tabella(pdf, ['Colonna', 'Significato', 'Cosa sa il cliente'],
            [['Da preparare', 'Ordini confermati, non ancora presi in '
              'carico.', 'Ha ricevuto la conferma con l\'orario di ritiro.'],
             ['In preparazione', 'Premuto il tasto: la cucina ci sta '
              'lavorando.', 'Riceve la notifica che l\'ordine e in '
              'lavorazione.'],
             ['Pronto', 'Il prodotto e finito e attende al banco.',
              'Riceve la notifica che puo ritirarlo.'],
             ['Consegnato', 'Ritirato dal cliente: esce dal display.', '-']],
            [26, 40, 38], C)

    testo(pdf, 'Ogni scheda porta il codice ordine, l\'orario di ritiro in '
               'evidenza, il cliente in forma abbreviata ("Mario R.") e - '
               'per i prodotti composti dal cliente - l\'elenco completo '
               'degli ingredienti scelti. Si lavora in ordine di orario di '
               'ritiro, non di arrivo.')

    callout(pdf, 'La regola fissa',
            'A ogni prodotto preparato vanno allegati il tagliando ordine di '
            'QuickLunch e lo scontrino del registratore di cassa, che e un '
            'apparecchio separato: QuickLunch non lo stampa.', RED,
            (253, 238, 240))

    h2(pdf, 'Il cesto dei pezzi pronti', C, idx)
    passi(pdf, [
        ('Prepara i pezzi in lotti omogenei',
         'Un lotto per tipo di prodotto: tramezzini con i tramezzini.'),
        ('Genera e stampa le etichette',
         'Cucina > Cesto Cucina: scegli il prodotto e la quantita. La pagina '
         'di stampa si apre da sola; si taglia e si applica un\'etichetta '
         'per pezzo, col QR ben visibile.'),
        ('Esponi il cesto',
         'Da quel momento la vendita e automatica: il cliente inquadra e '
         'paga dal telefono, oppure registra l\'acquisto e salda in cassa.'),
        ('Ritira l\'invenduto alla chiusura',
         'Le etichette rimaste si annullano una per una. Non usare "Annulla '
         'tutto": cancella dal registro anche le vendite della giornata.'),
    ], C)

    callout(pdf, 'Le etichette valgono 24 ore',
            'Un\'etichetta piu vecchia di 24 ore scade alla prima scansione e '
            'il pezzo non e piu vendibile: si generano la mattina stessa.',
            ORANGE)

    h2(pdf, 'Se un cliente disdice il pasto', C, idx)
    testo(pdf, 'Il promemoria del pasto aziendale ha due bottoni. Quando un '
               'dipendente risponde "No, non vengo", sul canale Telegram '
               'dello staff arriva "Pasto annullato dal cliente" con nome, '
               'menu e orario: quel pasto non va preparato, la prenotazione '
               'e gia annullata e non compare piu nella lista.')


def sez_sala(pdf, idx):
    C = TEAL
    apri_sezione(pdf, 5, 'Sala', 'Tavoli, fasce orarie, prenotazioni e '
                 'arrivi.', C,
                 'A chi gestisce i tavoli. La sezione esiste solo se la '
                 'gestione tavoli e attiva nelle Impostazioni: chi fa solo '
                 'asporto puo saltarla.', idx)

    h2(pdf, 'Come funziona la prenotazione', C, idx)
    elenco(pdf, [
        ('Tavoli: ', 'numero, posti e collocazione (finestra, centro, '
         'bancone).'),
        ('Fasce orarie: ', 'si definiscono inizio, fine e durata del turno; '
         'il sistema propone al cliente solo le fasce con posto.'),
        ('Prenotazioni: ', 'arrivano dai clienti o si inseriscono a mano dal '
         'backoffice, con numero di persone e note.'),
        ('Arrivo: ', 'alla presentazione si segna il check-in, cosi la '
         'piantina mostra a colpo d\'occhio chi c\'e e chi manca.'),
    ])

    h2(pdf, 'La piantina', C, idx)
    testo(pdf, 'La griglia dei tavoli mostra le prenotazioni della giornata '
               'con il nome abbreviato del cliente e il numero di persone. '
               'Un promemoria automatico avvisa il cliente poco prima '
               'dell\'orario prenotato.')


def sez_cliente(pdf, idx):
    C = BLUE
    apri_sezione(pdf, 6, 'Cliente', 'Registrarsi, ordinare, pagare, '
                 'ritirare.', C,
                 'A chi usa il servizio dal telefono. E la sezione da '
                 'consegnare ai clienti: esiste anche come Guida del cliente '
                 'in PDF, allegata all\'email di registrazione.', idx)

    h2(pdf, 'Iscriversi', C, idx)
    passi(pdf, [
        ('Inquadra il QR del locale',
         'La locandina appesa vicino alla cassa porta alla pagina di '
         'iscrizione. Si entra con email e password oppure con l\'account '
         'Google.'),
        ('Controlla la posta',
         'Arriva subito un\'email di conferma con la guida in PDF allegata e '
         'il pulsante per collegare Telegram. L\'account resta in attesa: '
         'appena il personale lo attiva arriva la seconda email.'),
        ('Collega Telegram (facoltativo)',
         'Il pulsante dell\'email porta alla pagina Collega Telegram, che '
         'mostra un codice personale: si invia al bot e il collegamento e '
         'fatto, senza cercare numeri di identificazione. Senza Telegram '
         'gli avvisi arrivano per email.'),
    ], C)

    h2(pdf, 'Ordinare', C, idx)
    elenco(pdf, [
        ('Dal menu: ', 'foto, prezzi e allergeni; si aggiunge al carrello e '
         'si scegle l\'orario di ritiro fra le fasce libere.'),
        ('Componendo il tuo piatto: ', 'panino, insalata o poke ingrediente '
         'per ingrediente, con il prezzo che si aggiorna in diretta.'),
        ('Dal cesto: ', 'si prende il pezzo pronto, si inquadra il QR '
         'dell\'etichetta e si conferma.'),
        ('Al banco: ', 'il personale compone il conto e mostra un QR da '
         'inquadrare.'),
    ])

    h2(pdf, 'Pagare', C, idx)
    testo(pdf, 'Nei locali che usano il portafoglio prepagato si ricarica il '
               'credito in cassa e ogni acquisto scala dal saldo, con i '
               'punti fedelta che maturano da soli. Nei locali che hanno '
               'scelto il pagamento in cassa non c\'e nessun saldo: si '
               'ordina e si paga al ritiro. Lo si capisce subito, perche in '
               'quel caso la voce Wallet non appare nel menu.')

    h2(pdf, 'La dieta settimanale', C, idx)
    testo(pdf, 'Da La mia dieta il cliente dichiara condizioni e allergie '
               '(celiachia, lattosio, uova, frutta a guscio, pesce, soia), '
               'regime e obiettivo, e riceve il fabbisogno calorico. Il menu '
               'mostra "Adatto a te" o il motivo contrario, il carrello '
               'confronta le calorie con la quota del pranzo e chiede una '
               'conferma se c\'e un allergene escluso, e il piano della '
               'settimana propone un pranzo per ogni giorno, ordinabile con '
               'un tocco. Funziona sui piatti con i valori nutrizionali '
               'compilati: il listino di partenza li ha, i piatti del gestore '
               'li ricevono dalla scheda prodotto. I valori (kcal, proteine, '
               'carboidrati, grassi, vegetariano/vegano) sono visibili a tutti '
               'i clienti nel menu, nel carrello, nel cesto e nel builder. Il '
               'backoffice li riassume in Clienti > Diete clienti.')

    callout(pdf, 'Avvertenza: nessuna validita medica',
            'La dieta settimanale e un aiuto a scegliere dal listino, non uno '
            'strumento sanitario: le sue indicazioni sono stime automatiche '
            'su valori dichiarati dal locale e formule generali, senza alcuna '
            'validita medica, e non sostituiscono medico o nutrizionista. Al '
            'cliente si apre in una finestra alla prima visita e va accettata '
            'prima di impostare la dieta; lo staff lo trova in testa alla pagina Diete '
            'clienti. L\'applicazione segnala gli allergeni dichiarati ma non '
            'puo garantire l\'assenza di contaminazioni: per chi ha allergie '
            'gravi la sicurezza sta nella preparazione e nella parola del '
            'personale, non nei badge dell\'applicazione.',
            RED, (253, 238, 240))

    callout(pdf, 'Il tuo nome sulle liste',
            'Sul display della cucina, sul tagliando e sulle liste stampate '
            'compari con il nome e la sola iniziale del cognome - "Mario R." '
            '- mentre nella tua area personale il nome resta per intero.',
            BLUE, (240, 247, 253))

    h2(pdf, 'Gli avvisi', C, idx)
    tabella(pdf, ['Quando', 'Che cosa ricevi'],
            [['Ordine confermato', 'Codice, orario di ritiro e totale.'],
             ['Ordine in preparazione', 'La cucina ha iniziato.'],
             ['Ordine pronto', 'Puoi ritirarlo al banco.'],
             ['Poco prima del ritiro', 'Un promemoria, con i bottoni per '
              'confermare o disdire se si tratta del pasto aziendale.']],
            [34, 70], C)


def sez_dipendente(pdf, idx):
    C = PURPLE
    apri_sezione(pdf, 7, 'Dipendente convenzionato', 'Il pasto del giorno '
                 'della tua azienda.', C,
                 'A chi lavora in un\'azienda che ha la convenzione col '
                 'locale. La voce Pasto Aziendale appare solo se il tuo '
                 'account e stato associato alla convenzione.', idx)

    h2(pdf, 'Prenotare', C, idx)
    passi(pdf, [
        ('Guarda il menu del giorno',
         'Primo, secondo, contorno, bevanda e caffe, con gli allergeni e il '
         'prezzo concordato dalla tua azienda.'),
        ('Scegli l\'orario di ritiro',
         'Fra le fasce disponibili. I posti sono limitati: prima prenoti, '
         'piu scelta hai.'),
        ('Disdici se non vieni',
         'Fino a 30 minuti prima dell\'orario scelto. Disdire in tempo '
         'evita che il pasto venga preparato e buttato.'),
        ('Ritira col tuo codice',
         'Al banco mostri il codice di ritiro che trovi nella prenotazione.'),
    ], C)

    h2(pdf, 'Il promemoria con i due bottoni', C, idx)
    testo(pdf, 'Poco prima dell\'orario di ritiro arriva un promemoria su '
               'Telegram con due bottoni. "Si, lo ritiro" conferma; "No, non '
               'vengo" annulla la prenotazione e la cucina non prepara il '
               'tuo pasto. E il modo piu rapido di avvisare quando salta una '
               'riunione: un tocco, e nessuno cucina a vuoto.')

    callout(pdf, 'Se non hai Telegram',
            'Il promemoria arriva per email e la disdetta si fa dalla pagina '
            'Pasto Aziendale, con lo stesso effetto.', PURPLE,
            (247, 242, 250))


def sez_appendice(pdf, idx):
    apri_sezione(pdf, 'A', 'Appendice', 'Permessi, funzioni attivabili, '
                 'primo accesso.', NAVY,
                 'A chi assegna i ruoli e configura il sistema.', idx)

    h2(pdf, 'Chi vede che cosa', NAVY, idx)
    testo(pdf, 'I permessi si assegnano per ruolo: un collaboratore vede '
               'soltanto le pagine che gli servono. Un amministratore vede '
               'tutto.')
    tabella(pdf, ['Area', 'Cassa', 'Cucina', 'Sala', 'Gestore'],
            [['Ordini e display', 'si', 'si', 'no', 'si'],
             ['Banco QR e ricariche', 'si', 'no', 'no', 'si'],
             ['Cesto ed etichette', 'no', 'si', 'no', 'si'],
             ['Tavoli e prenotazioni', 'no', 'no', 'si', 'si'],
             ['Catalogo e prezzi', 'no', 'no', 'no', 'si'],
             ['Convenzioni e report', 'no', 'no', 'no', 'si'],
             ['Impostazioni e dati', 'no', 'no', 'no', 'si']],
            [42, 14, 14, 14, 16], NAVY)

    h2(pdf, 'Al primo accesso', NAVY, idx)
    elenco(pdf, [
        'Cambia le password delle utenze amministrative create '
        'dall\'installazione.',
        'Compila l\'anagrafica del locale in Impostazioni: compare su tutte '
        'le stampe e i report.',
        'Configura Gmail, altrimenti nessuna email parte - nemmeno quella '
        'con la guida ai nuovi clienti.',
        'Configura il bot Telegram e attiva le risposte ai bottoni, se vuoi '
        'la conferma del pasto con un tocco.',
        'Decidi le funzioni attive: tavoli, cesto, portafoglio prepagato.',
    ])

    h2(pdf, 'Gli altri documenti', NAVY, idx)
    tabella(pdf, ['Documento', 'A chi serve'],
            [['Manuale del gestore', 'La giornata ora per ora, con gli orari '
              'limite di ogni attivita.'],
             ['Manuale operativo di cucina', 'I tre flussi di preparazione, '
              'passo per passo.'],
             ['Onboarding del cliente', 'Come portare un cliente dalla '
              'registrazione al primo ordine.'],
             ['Guida del cliente', 'Da consegnare ai clienti finali: e '
              'allegata all\'email di registrazione.'],
             ['Dotazione e postazioni', 'Quali dispositivi servono e dove.'],
             ['Catalogo delle stampe', 'Tutte le stampe del sistema, con '
              'esempi reali.']],
            [40, 64], NAVY)

    _spazio(pdf, 4)
    callout(pdf, 'Assistenza',
            'Daniele Speziale - DS Consulting\n%s  ·  %s' % (EMAIL, CELL),
            RED, (253, 238, 240))


# ═════════════════════════════════════════════════════════════════════════════
#  Montaggio: due passaggi, per avere l'indice con le pagine giuste
# ═════════════════════════════════════════════════════════════════════════════

def costruisci(voci_indice=None):
    pdf = Guida(format='A4')
    pdf.add_font(FONT, '', os.path.join(FONT_DIR, 'PTSansNarrow-Regular.ttf'))
    pdf.add_font(FONT, 'B', os.path.join(FONT_DIR, 'PTSansNarrow-Bold.ttf'))
    pdf.set_margins(ML, 18, MR)
    pdf.set_auto_page_break(True, margin=20)

    copertina(pdf)
    pagina_indice(pdf, voci_indice)      # None al primo giro: solo la testa

    raccolte = []
    for sezione in (sez_super_admin, sez_gestore, sez_cassa, sez_cucina,
                    sez_sala, sez_cliente, sez_dipendente, sez_appendice):
        sezione(pdf, raccolte)
    return pdf, raccolte


def main():
    _pdf, voci = costruisci(None)        # primo giro: dove cadono i titoli
    pdf, _ = costruisci(voci)            # secondo giro: indice compilato
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    pdf.output(OUT)
    print('[OK] %s' % OUT)
    print('     %d pagine, %d byte, %d voci di indice'
          % (len(pdf.pages), os.path.getsize(OUT), len(voci)))


if __name__ == '__main__':
    main()
