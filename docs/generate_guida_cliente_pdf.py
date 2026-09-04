#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Genera la Guida del cliente in PDF, impaginata come la Guida utente.

E' il documento che i clienti ricevono davvero: viene allegato all'email di
registrazione e a quella di attivazione. Percio' scrive in due posti:

    docs/manuali/guida_cliente.pdf      copia editoriale
    app/static/docs/guida_cliente.pdf   copia che l'applicazione allega

I mattoni dell'impaginazione (copertina, indice con le pagine vere, sezioni
a colori, riquadri, tabelle) arrivano da generate_guida_utente_pdf: qui ci
sono solo la copertina dedicata e i contenuti per il cliente.

    python docs/generate_guida_cliente_pdf.py
"""

import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from generate_guida_utente_pdf import (                      # noqa: E402
    Guida, apri_sezione, callout, elenco, h2, pagina_indice, passi,
    tabella, testo, _spazio,
    FONT, FONT_DIR, ML, W,
    RED, NAVY, DARK, DGRAY, MGRAY, WHITE, GREEN, ORANGE, BLUE, PURPLE, TEAL,
    EMAIL, CELL, CONTATTI,
)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'docs', 'manuali', 'guida_cliente.pdf')
OUT_APP = os.path.join(ROOT, 'app', 'static', 'docs', 'guida_cliente.pdf')


def copertina_cliente(pdf):
    pdf.add_page()
    pdf.set_fill_color(*NAVY)
    pdf.rect(0, 0, 210, 297, 'F')
    pdf.set_fill_color(*RED)
    pdf.rect(0, 108, 210, 2.4, 'F')

    pdf.set_text_color(*WHITE)
    pdf.set_font(FONT, 'B', 13)
    pdf.set_xy(22, 70)
    pdf.cell(0, 6, 'QUICKLUNCH')
    pdf.set_font(FONT, '', 11)
    pdf.set_xy(22, 78)
    pdf.set_text_color(178, 194, 217)
    pdf.cell(0, 6, 'GUIDA DEL CLIENTE')

    pdf.set_text_color(*WHITE)
    pdf.set_font(FONT, 'B', 40)
    pdf.set_xy(22, 88)
    pdf.cell(0, 18, 'Il pranzo,')
    pdf.set_xy(22, 106)
    pdf.cell(0, 18, 'senza coda')

    pdf.set_xy(22, 136)
    pdf.set_font(FONT, '', 13)
    pdf.set_text_color(214, 223, 234)
    pdf.multi_cell(166, 7,
                   'Ordini dal telefono quando vuoi, scegli l\'orario in cui '
                   'passi a ritirare e trovi tutto pronto. Questa guida ti '
                   'accompagna dalla prima iscrizione al primo pranzo, e ti '
                   'resta utile per le due o tre cose che si dimenticano '
                   'sempre.')

    y = 182
    for i, (nome, colore) in enumerate([
            ('Iscriviti', GREEN), ('Ordina', BLUE), ('Ritira', ORANGE),
            ('Paga', PURPLE)]):
        x = 22 + i * 42
        pdf.set_fill_color(*colore)
        pdf.rect(x, y, 38, 9, 'F')
        pdf.set_xy(x, y + 1.6)
        pdf.set_font(FONT, 'B', 9.5)
        pdf.set_text_color(*WHITE)
        pdf.cell(38, 5, nome, align='C')

    pdf.set_xy(22, 208)
    pdf.set_font(FONT, '', 11)
    pdf.set_text_color(178, 194, 217)
    pdf.multi_cell(166, 6,
                   'Alcune funzioni dipendono da come il tuo locale ha '
                   'scelto di lavorare: se una voce non compare nel menu '
                   'dell\'app, in quel bar non e attiva. Nel dubbio, chiedi '
                   'al banco.')

    pdf.set_xy(22, 250)
    pdf.set_font(FONT, 'B', 11)
    pdf.set_text_color(*WHITE)
    pdf.cell(0, 6, 'Assistenza')
    pdf.set_xy(22, 257)
    pdf.set_text_color(255, 215, 223)
    pdf.cell(0, 6, CONTATTI)
    pdf.set_xy(22, 268)
    pdf.set_font(FONT, '', 10)
    pdf.set_text_color(178, 194, 217)
    pdf.cell(0, 5, '© 2024–26 DS Consulting')


# ═════════════════════════════════════════════════════════════════════════════
#  Le sezioni
# ═════════════════════════════════════════════════════════════════════════════

def sez_iscrizione(pdf, idx):
    C = GREEN
    apri_sezione(pdf, 1, 'Iscriviti', 'Dalla locandina al primo accesso.', C,
                 'Si fa una volta sola, dal telefono, in un paio di minuti.',
                 idx)

    h2(pdf, 'I tre passi', C, idx)
    passi(pdf, [
        ('Inquadra il QR del locale',
         'La locandina appesa vicino alla cassa apre la pagina di '
         'iscrizione. Puoi entrare con la tua email scegliendo una password, '
         'oppure con l\'account Google: in quel caso non devi ricordare '
         'nessuna password nuova.'),
        ('Compila nome e cognome',
         'Servono al banco per riconoscere il tuo ordine quando passi a '
         'ritirarlo. Il resto (telefono, data di nascita) e facoltativo.'),
        ('Attendi il via libera',
         'Il personale approva le nuove iscrizioni: appena il tuo account e '
         'attivo ricevi un\'email e puoi ordinare. Se hai fretta, dillo al '
         'banco: e questione di un clic.'),
    ], C)

    h2(pdf, 'Le email che ricevi', C, idx)
    tabella(pdf, ['Quando', 'Che cosa contiene'],
            [['Appena ti iscrivi', 'La conferma che la registrazione e '
              'arrivata, questa guida in allegato e il pulsante per '
              'collegare Telegram.'],
             ['Quando ti attivano', 'Il via libera all\'accesso, con i primi '
              'passi da fare.']],
            [30, 74], C)

    callout(pdf, 'Non hai ricevuto niente?',
            'Controlla la posta indesiderata: le email con allegato ci '
            'finiscono spesso. Se non c\'e nulla nemmeno la, chiedi al banco '
            'di rimandartela: dalla scheda del tuo profilo lo fanno in un '
            'clic.', ORANGE)


def sez_telegram(pdf, idx):
    C = TEAL
    apri_sezione(pdf, 2, 'Collega Telegram', 'Gli avvisi sul telefono, e la '
                 'conferma del pasto con un tocco.', C,
                 'Facoltativo ma consigliato: senza Telegram gli avvisi ti '
                 'arrivano per email, che e piu lenta.', idx)

    h2(pdf, 'Dove si fa', C, idx)
    testo(pdf, 'Nell\'email che hai ricevuto premi "Collega Telegram", '
               'oppure apri Profilo > Collega Telegram: e la pagina che '
               'guida il collegamento e ti mostra il tuo codice personale.')

    h2(pdf, 'I tre passi', C, idx)
    passi(pdf, [
        ('Apri il bot',
         'Dal telefono premi il pulsante "Apri il bot": la chat si apre col '
         'codice gia scritto. Dal computer cerca il bot su Telegram, il suo '
         'nome e indicato nella pagina.'),
        ('Premi Avvia e invia il codice',
         'Il codice e quello mostrato in pagina, sei caratteri come '
         'QL-K7M2PX. Vale solo per te e non scade.'),
        ('Torna in pagina e conferma',
         'Premi "Ho inviato il codice": riconosciamo il tuo messaggio e il '
         'collegamento e fatto. Non serve nessun numero di '
         'identificazione.'),
    ], C)

    h2(pdf, 'Che cosa ti arriva', C, idx)
    tabella(pdf, ['Quando', 'Messaggio'],
            [['Ordine confermato', 'Codice, orario di ritiro e totale.'],
             ['La cucina inizia', 'Il tuo ordine e in preparazione.'],
             ['Ordine pronto', 'Puoi passare a ritirarlo al banco.'],
             ['Prima del ritiro', 'Un promemoria; per il pasto aziendale con '
              'i due bottoni per confermare o disdire.']],
            [30, 74], C)


def sez_ordinare(pdf, idx):
    C = BLUE
    apri_sezione(pdf, 3, 'Ordina', 'Dal menu, o componendo il piatto come '
                 'lo vuoi tu.', C,
                 'Il cuore del servizio: si ordina quando si vuole, anche la '
                 'sera prima, e si scegle l\'ora in cui passare.', idx)

    h2(pdf, 'Dal menu', C, idx)
    passi(pdf, [
        ('Sfoglia le categorie',
         'Colazione, panini, primi, insalate, bevande e le altre. Ogni '
         'prodotto mostra prezzo e allergeni.'),
        ('Aggiungi al carrello',
         'Puoi cambiare le quantita fino alla conferma.'),
        ('Scegli l\'orario di ritiro',
         'Compaiono solo le fasce con posto libero: se una manca, e perche e '
         'piena.'),
        ('Conferma',
         'Ricevi il codice dell\'ordine. Da quel momento lo segui in "I miei '
         'ordini" e ti avvisiamo quando e pronto.'),
    ], C)

    h2(pdf, 'Componi il tuo piatto', C, idx)
    testo(pdf, 'Panino, insalata o poke: scegli la base e poi ingrediente '
               'per ingrediente, con il prezzo che si aggiorna mentre '
               'aggiungi. Gli extra a pagamento sono segnalati. Quello che '
               'scegli arriva in cucina per esteso, quindi trovi esattamente '
               'il piatto che hai composto.')

    callout(pdf, 'Se un ingrediente non c\'e',
            'Gli ingredienti finiti spariscono dalle scelte: non e un '
            'errore dell\'app, e il bar che ha esaurito quella scorta per '
            'oggi.', BLUE, (240, 247, 253))

    h2(pdf, 'Annullare un ordine', C, idx)
    testo(pdf, 'Finche la cucina non lo prende in carico puoi annullarlo da '
               '"I miei ordini". Dopo, no: il prodotto e gia in '
               'preparazione. Se hai un problema, chiedi al banco.')


def sez_ritirare(pdf, idx):
    C = ORANGE
    apri_sezione(pdf, 4, 'Ritira', 'Il cesto, il banco col QR, il tuo '
                 'ordine pronto.', C,
                 'Tre modi di prendere quello che hai ordinato, o di '
                 'comprare al volo quello che vedi.', idx)

    h2(pdf, 'Il tuo ordine', C, idx)
    testo(pdf, 'All\'orario che hai scelto passi al banco: il pacchetto '
               'porta il tuo nome (nella forma abbreviata, per esempio '
               '"Mario R.") e il codice dell\'ordine. Se sei in ritardo '
               'avvisa: il prodotto ti aspetta, ma la cucina lavora per '
               'orari.')

    h2(pdf, 'Il cesto dei pezzi pronti', C, idx)
    passi(pdf, [
        ('Prendi il pezzo che ti piace',
         'Nel cesto ci sono tramezzini, panini e altro, preparati poco '
         'prima. Ogni pezzo ha un\'etichetta con prezzo e allergeni.'),
        ('Inquadra il QR dell\'etichetta',
         'Si apre la pagina di acquisto con il prodotto gia riconosciuto.'),
        ('Conferma',
         'Se vuoi, aggiungi una bevanda inquadrando il suo codice a barre. '
         'Poi confermi: hai finito.'),
    ], C)

    h2(pdf, 'Il conto al banco', C, idx)
    testo(pdf, 'Per il caffe e gli acquisti veloci fa tutto il personale: '
               'compone il conto sul tablet e ti mostra un QR. Lo inquadri, '
               'controlli il riepilogo e confermi.')

    callout(pdf, 'Il QR dura pochi minuti',
            'Se ci metti troppo scade e il personale te ne genera un altro: '
            'serve a evitare che qualcun altro paghi il tuo conto per '
            'sbaglio.', ORANGE)


def sez_pagare(pdf, idx):
    C = PURPLE
    apri_sezione(pdf, 5, 'Paga', 'Portafoglio prepagato o pagamento in '
                 'cassa, secondo il locale.', C,
                 'Due modi possibili: lo capisci da come e fatto il menu '
                 'dell\'app.', idx)

    h2(pdf, 'Con il portafoglio prepagato', C, idx)
    elenco(pdf, [
        ('Ricarichi in cassa: ', 'lasci l\'importo al banco e te lo caricano '
         'sul tuo credito. Dieci o venti euro coprono diversi pranzi.'),
        ('Ogni acquisto scala dal saldo: ', 'ordini, cesto e banco. Al ritiro '
         'non paghi nulla, e cosi non c\'e coda alla cassa.'),
        ('Vedi tutto: ', 'saldo e storico dei movimenti sono nella pagina '
         'Wallet.'),
        ('Accumuli punti: ', 'ogni euro speso vale punti; alla soglia si '
         'trasformano in credito.'),
    ])

    h2(pdf, 'Con il pagamento in cassa', C, idx)
    testo(pdf, 'Alcuni locali preferiscono non gestire credito: in quel caso '
               'nel menu dell\'app non trovi la voce Wallet. Ordini come '
               'sempre e paghi al banco quando ritiri. Tutto il resto — '
               'menu, orari, avvisi, pasto aziendale — funziona allo stesso '
               'modo.')

    callout(pdf, 'Come capire quale dei due',
            'Se nel menu c\'e "Wallet & Fedelta", il locale usa il '
            'portafoglio prepagato. Se non c\'e, si paga alla cassa.',
            PURPLE, (247, 242, 250))


def sez_pasto(pdf, idx):
    C = RED
    apri_sezione(pdf, 6, 'Il pasto aziendale', 'Il menu del giorno della tua '
                 'azienda, a prezzo convenzionato.', C,
                 'A chi lavora in un\'azienda convenzionata col locale. La '
                 'voce compare solo se il tuo account e stato associato alla '
                 'convenzione: se non la vedi, chiedi al banco.', idx)

    h2(pdf, 'Prenotare', C, idx)
    passi(pdf, [
        ('Guarda il menu del giorno',
         'Primo, secondo, contorno, bevanda e caffe, con gli allergeni e il '
         'prezzo concordato dalla tua azienda.'),
        ('Scegli l\'orario',
         'I posti per fascia sono limitati: prima prenoti, piu scelta hai.'),
        ('Ritira col tuo codice',
         'Nella prenotazione trovi un codice: lo mostri al banco e ti '
         'consegnano il pasto.'),
    ], C)

    h2(pdf, 'Se non riesci a venire, disdici', C, idx)
    testo(pdf, 'Puoi disdire fino a 30 minuti prima dell\'orario che hai '
               'scelto. Poco prima del ritiro ricevi su Telegram un '
               'promemoria con due bottoni: "Si, lo ritiro" conferma, "No, '
               'non vengo" annulla la prenotazione e la cucina non prepara '
               'il tuo pasto.')

    callout(pdf, 'Perche disdire conta',
            'Un pasto preparato e non ritirato si butta. Un tocco sul '
            'bottone No, appena sai che salta il pranzo, evita uno spreco e '
            'lascia il posto a un collega.', GREEN, (240, 250, 244))


def sez_domande(pdf, idx):
    C = NAVY
    apri_sezione(pdf, 7, 'Domande frequenti', 'Le cose che si chiedono piu '
                 'spesso al banco.', C,
                 'A tutti: cinque minuti di lettura che fanno risparmiare '
                 'una domanda alla cassa.', idx)

    h2(pdf, 'Sul servizio', C, idx)
    tabella(pdf, ['Domanda', 'Risposta'],
            [['Posso ordinare la sera prima?',
              'Si. Scegli una fascia di ritiro del giorno dopo: la cucina '
              'vede l\'ordine e lo prepara al momento giusto.'],
             ['Ho sbagliato l\'orario di ritiro.',
              'Annulla l\'ordine se non e ancora in preparazione e rifallo. '
              'Altrimenti avvisa il banco.'],
             ['Perche non vedo la fascia che voglio?',
              'E piena: ogni fascia ha un numero massimo di ordini, per non '
              'far accumulare la cucina.'],
             ['Il locale ha i tavoli?',
              'Se il menu mostra la voce Tavoli si, e puoi prenotare a '
              'fasce. Altrimenti quel locale fa solo asporto.']],
            [38, 66], C)

    h2(pdf, 'Su avvisi e account', C, idx)
    tabella(pdf, ['Domanda', 'Risposta'],
            [['Non ricevo gli avvisi.',
              'Se non hai collegato Telegram arrivano per email: controlla '
              'anche la posta indesiderata. Con Telegram collegato sono '
              'immediati.'],
             ['Voglio cambiare email o password.',
              'Dal tuo Profilo. Se sei entrato con Google, l\'accesso resta '
              'quello di Google.'],
             ['Come cancello il mio account?',
              'Dal Profilo, in fondo. Se hai ancora credito nel '
              'portafoglio, chiedi prima il rimborso al banco.'],
             ['Chi vede il mio nome?',
              'Sulle liste di cucina e sui tagliandi compare in forma '
              'abbreviata ("Mario R."); per intero lo vedi solo tu nella '
              'tua area.']],
            [38, 66], C)

    _spazio(pdf, 3)
    callout(pdf, 'Buon pranzo',
            'Per qualsiasi dubbio chiedi al banco: chi ci lavora ha la '
            'stessa guida, con una sezione in piu dedicata a loro.', RED,
            (253, 238, 240))


# ═════════════════════════════════════════════════════════════════════════════
#  Montaggio
# ═════════════════════════════════════════════════════════════════════════════

def costruisci(voci_indice=None):
    pdf = Guida(format='A4')
    pdf.add_font(FONT, '', os.path.join(FONT_DIR, 'PTSansNarrow-Regular.ttf'))
    pdf.add_font(FONT, 'B', os.path.join(FONT_DIR, 'PTSansNarrow-Bold.ttf'))
    pdf.set_margins(ML, 18, 16)
    pdf.set_auto_page_break(True, margin=20)
    pdf.etichetta_testata = 'QuickLunch · Guida del cliente'

    copertina_cliente(pdf)
    pagina_indice(pdf, voci_indice)

    raccolte = []
    for sezione in (sez_iscrizione, sez_telegram, sez_ordinare, sez_ritirare,
                    sez_pagare, sez_pasto, sez_domande):
        sezione(pdf, raccolte)
    return pdf, raccolte


def main():
    _pdf, voci = costruisci(None)
    pdf, _ = costruisci(voci)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    pdf.output(OUT)
    os.makedirs(os.path.dirname(OUT_APP), exist_ok=True)
    shutil.copyfile(OUT, OUT_APP)
    print('[OK] %s' % OUT)
    print('     %d pagine, %d byte, %d voci di indice'
          % (len(pdf.pages), os.path.getsize(OUT), len(voci)))
    print('     copia per l\'email in %s' % OUT_APP)


if __name__ == '__main__':
    main()
