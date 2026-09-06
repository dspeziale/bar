#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Genera docs/manuali/manuale_gestore.pdf — il manuale completo del gestore.

Tutte le funzionalita' del backoffice viste da chi amministra il locale:
come si imposta l'applicazione prima di aprire, gli orari da cui discende la
giornata, il catalogo con i valori nutrizionali, i clienti e le loro diete,
ordini e cucina, cesto, banco, tavoli, convenzioni, portafoglio, magazzino,
comunicazioni, report, dati e sicurezza, e i problemi tipici con la loro
soluzione.

    python docs/generate_manuale_gestore_pdf.py

Stesso kit grafico di guida utente e catalogo (PT Sans Narrow, rosso/blu),
indice con i numeri di pagina veri (due passaggi). Il manuale della giornata
(manuale_gestore_giornata.docx) resta: e' la scaletta oraria, questo e' il
riferimento completo.
"""

import os
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
OUT = os.path.join(ROOT, 'docs', 'manuali', 'manuale_gestore.pdf')


# ═════════════════════════════════════════════════════════════════════════════
#  Copertina
# ═════════════════════════════════════════════════════════════════════════════
def copertina_gestore(pdf):
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
    pdf.cell(0, 6, 'MANUALE DEL GESTORE · TUTTE LE FUNZIONALITA')

    pdf.set_text_color(*WHITE)
    pdf.set_font(FONT, 'B', 40)
    pdf.set_xy(22, 88)
    pdf.cell(0, 18, 'Il locale,')
    pdf.set_xy(22, 106)
    pdf.cell(0, 18, 'in una sola app')

    pdf.set_xy(22, 136)
    pdf.set_font(FONT, '', 13)
    pdf.set_text_color(214, 223, 234)
    pdf.multi_cell(166, 7,
                   'Come si imposta QuickLunch prima di aprire, come si '
                   'governa la giornata dagli orari, come si tengono catalogo, '
                   'clienti, ordini, cucina, banco, tavoli, convenzioni, '
                   'portafoglio e magazzino, e come si proteggono i dati. '
                   'Ogni sezione dice dove si trova la funzione, cosa fa e '
                   'cosa succede se la si spegne.')

    y = 182
    aree = [('Impostare', RED), ('Orari', NAVY), ('Catalogo', GREEN), ('Clienti', BLUE),
            ('Servizio', ORANGE), ('Convenzioni', PURPLE), ('Dati', TEAL)]
    for i, (nome, colore) in enumerate(aree):
        x = 22 + (i % 4) * 42
        if i == 4:
            y += 14
        pdf.set_fill_color(*colore)
        pdf.rect(x, y, 38, 9, 'F')
        pdf.set_xy(x, y + 1.6)
        pdf.set_font(FONT, 'B', 9.5)
        pdf.set_text_color(*WHITE)
        pdf.cell(38, 5, nome, align='C')

    pdf.set_xy(22, 222)
    pdf.set_font(FONT, '', 10.5)
    pdf.set_text_color(178, 194, 217)
    pdf.multi_cell(166, 5.6,
                   'Cinque moduli si accendono e si spengono da un interruttore: tavoli, '
                   'cesto, portafoglio prepagato, dieta settimanale, magazzino. Le sezioni '
                   'che li riguardano valgono solo se il modulo e acceso.')

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
#  Sezioni
# ═════════════════════════════════════════════════════════════════════════════
def sez_prima_di_aprire(pdf, idx):
    C = RED
    apri_sezione(pdf, 1, 'Prima di aprire', 'Le cose da sistemare una volta '
                 'sola, in ordine.', C,
                 'Al titolare, il primo giorno. Un\'ora di lavoro che evita '
                 'settimane di domande al banco.', idx)

    h2(pdf, 'Accesso e sicurezza', C, idx)
    passi(pdf, [
        ('Entra con l\'utenza dell\'amministratore del locale e cambia subito la password',
         'Ogni locale (tenant) e un mondo a parte: catalogo, clienti, ordini, impostazioni, '
         'bot Telegram e orari sono suoi e nessun altro locale li vede. L\'amministratore '
         'dei tenant (DS Consulting) crea il locale con il catalogo di partenza e consegna '
         'al titolare le credenziali del suo amministratore, che ha tutti i permessi ma solo '
         'sui dati del proprio locale. Dal Profilo si cambia la password e si attiva la '
         'verifica in due passi (MFA con app di autenticazione). Fallo prima di dare '
         'l\'indirizzo a chiunque.'),
        ('Gli indirizzi del locale: ognuno entra dalla sua porta',
         'Impostazioni > Azienda > Indirizzi del locale mostra i due indirizzi da dare in giro: '
         '/t/<slug>/login per personale e clienti, /t/<slug>/register per iscriversi (e il QR '
         'della locandina). La pagina porta nome e colore del locale, cosi nessuno si chiede '
         'dove sta entrando; dopo l\'accesso, in alto compare "Locale: <nome>". L\'indirizzo '
         'globale /auth/login e neutro: non nomina nessun locale, funziona per tutti e porta '
         'ciascuno nel proprio. Nessun locale vede o conosce gli altri: chi sbaglia porta '
         'riceve solo un avviso generico. Dopo la prima visita alla pagina del locale il '
         'telefono del cliente se lo ricorda (un anno): anche tornando da un indirizzo '
         'globale o dall\'icona salvata in home, "Accedi con Google" e il login vanno dritti '
         'al suo locale, senza altri passaggi.'),
        ('Crea il personale con il ruolo giusto',
         'Persone > Personale: cassiere, cuoco, manager sono ruoli pronti con i loro '
         'permessi; Persone > Ruoli & Permessi li adatta o ne crea altri. Un utente vede '
         'solo le voci di menu che i suoi permessi consentono.'),
        ('Compila l\'anagrafica del locale',
         'Impostazioni > Azienda: ragione sociale, indirizzo, partita IVA, telefono, '
         'email. La ragione sociale compare in testa a scontrini, etichette e report; '
         'vuota, i documenti stampano "QuickLunch".'),
    ], C)

    h2(pdf, 'Notifiche: Telegram ed email', C, idx)
    passi(pdf, [
        ('Telegram: token del bot e chat dello staff',
         'Impostazioni > Notifiche. Il token viene da @BotFather, la chat e il gruppo o '
         'canale dove volete gli avvisi (nuovo cliente, nuovo ordine, sottoscorta, '
         'promemoria backup). Il nome del bot (predefinito @dslunch_bot) compare nelle '
         'email ai clienti.'),
        ('Invia una domanda di prova e leggi la risposta',
         'Il messaggio di prova porta gli stessi bottoni dei promemoria: rispondete con '
         'un tocco e premete "Leggi la risposta". Se torna, il canale funziona in '
         'entrambe le direzioni. La pagina Diagnostica chiede a Telegram lo stato del '
         'webhook e l\'ultimo errore di consegna: e il posto dove si capisce un silenzio.'),
        ('Attiva le risposte ai bottoni',
         'Serve una volta, dall\'ambiente di produzione (Telegram vuole HTTPS): senza, i '
         'bottoni Si/No del promemoria pasto compaiono ma la risposta non arriva, il '
         'cliente crede di aver disdetto e la cucina prepara comunque.'),
        ('Gmail per le email ai clienti',
         'Utente Gmail e password per le app: da qui partono le due email di iscrizione e '
         'attivazione con la guida in PDF allegata, il piano della dieta a chi lo vuole per '
         'email e la copia di sicurezza prima di un ripristino. Senza Gmail un invio '
         'fallito viene segnalato sul canale Telegram e si puo rimandare dalla lista clienti.'),
        ('Google (facoltativo)',
         'Client ID e secret consentono ai clienti di iscriversi con l\'account Google. In '
         'produzione il callback richiede HTTPS.'),
    ], C)

    h2(pdf, 'Funzionalita: i cinque interruttori', C, idx)
    testo(pdf, 'Impostazioni > Funzionalita. Ogni modulo si accende e si spegne senza '
               'perdere dati: spegnere nasconde le pagine e ne blocca le rotte, riaccendere '
               'riporta tutto com\'era.')
    tabella(pdf, ['Modulo', 'Se spento', 'Da sapere'],
            [['Gestione tavoli', 'Spariscono tavoli, fasce e prenotazioni; la durata della '
              'seduta esce dagli slot.', 'Per chi fa solo asporto.'],
             ['Cesto cucina', 'Niente etichette QR ne acquisto self-service; le vendite '
              'passate restano nei report.', 'Le etichette gia stampate non sono piu '
              'acquistabili finche resta spento.'],
             ['Portafoglio prepagato', 'L\'app non muove denaro: niente saldi, ricariche, fidi, '
              'punti, bonus. Sparisce anche il Banco con il QR, che e un pagamento dal '
              'portafoglio.', 'Si paga alla cassa; ordini e cesto restano registrati.'],
             ['Dieta settimanale', 'Spariscono la pagina del cliente, i giudizi nel menu e '
              'nel carrello e la pagina Diete clienti.', 'Le preferenze salvate restano; i '
              'valori nutrizionali si vedono comunque.'],
             ['Gestione magazzino', 'Spariscono consumabili, fornitori, avvisi di sottoscorta '
              'e la colonna Giacenza degli ingredienti; gli ordini non scaricano piu nulla.',
              'I dati restano.']],
            [30, 74, 42], C)

    callout(pdf, 'L\'ordine consigliato',
            'Sicurezza e personale, poi Azienda, poi Notifiche con la domanda di prova, poi '
            'Funzionalita, poi Orari (sezione seguente), poi il catalogo. Solo a questo '
            'punto si stampa il QR di registrazione e si invitano i clienti.',
            GREEN, (240, 250, 244))


def sez_orari(pdf, idx):
    C = NAVY
    apri_sezione(pdf, 2, 'Gli orari e la giornata', 'Una tabella sola: tutto '
                 'il resto ne discende.', C,
                 'Al titolare. E la pagina che governa il servizio: cambiare '
                 'un orario qui cambia il comportamento ovunque.', idx)

    testo(pdf, 'Impostazioni > Orari raccoglie ogni orario del locale in sette gruppi. Non '
               'esistono altri orari nascosti nell\'applicazione: se un comportamento '
               'dipende da un\'ora, quell\'ora e qui.')
    tabella(pdf, ['Gruppo', 'Che cosa contiene', 'Che cosa ne discende'],
            [['Il locale', 'Apertura e chiusura, giorni di apertura, chiusure '
              'straordinarie (date).', 'Nei giorni chiusi non si ordina, la dieta non '
              'pianifica, il menu lo dice.'],
             ['Ordini e ritiro', 'Dalle/entro quando si ordina per oggi, minuti minimi fra '
              'ordine e ritiro, primo e ultimo slot, intervallo, capienza, anticipo della '
              'cucina.', 'La griglia degli slot di ritiro; il carrello mostra solo gli slot '
              'raggiungibili; l\'ordine fuori finestra e rifiutato con il motivo.'],
             ['Pasto aziendale', 'Prenotazione entro le..., disdetta fino a ... minuti '
              'prima.', 'Dopo l\'ora la prenotazione e chiusa; il promemoria con i bottoni '
              'rispetta il limite di disdetta.'],
             ['Tavoli', 'Prima fascia, fine dell\'ultima, durata.', 'Le fasce delle '
              'prenotazioni.'],
             ['Banco e cesto', 'Quanto vale il QR di un conto; dopo quante ore scade '
              'un\'etichetta.', 'Il POS e il cesto.'],
             ['Appuntamenti della settimana', 'Giorno e ora dell\'avviso dieta e del '
              'promemoria backup.', 'Quando partono gli avvisi automatici.'],
             ['Promemoria', 'Anticipo in minuti di tavolo, ritiro ordine, pasto.',
              'I messaggi Telegram/email ai clienti.']],
            [30, 66, 50], C)

    h2(pdf, 'Dagli orari alle righe', C, idx)
    passi(pdf, [
        ('Salva gli orari',
         'Con incoerenze non si salva nulla e la pagina elenca cosa non torna: un ultimo '
         'ordine dopo l\'ultimo slot, un pasto da prenotare dopo il primo ritiro, slot dopo '
         'la chiusura, un giorno di apertura mancante.'),
        ('Sincronizza gli slot',
         'Crea gli slot mancanti con la capienza impostata, riattiva quelli previsti, '
         'disattiva quelli fuori griglia. Non cancella nulla: uno slot disattivato resta '
         'per lo storico degli ordini, e le capienze gia ritoccate a mano non vengono '
         'toccate.'),
        ('Crea le fasce mancanti (con i tavoli attivi)',
         'Aggiunge solo le fasce che non esistono: quelle presenti hanno prenotazioni che '
         'le puntano e non si toccano.'),
        ('Leggi "La giornata che ne discende"',
         'A destra la scaletta oraria calcolata dai valori: apertura, apertura ordini, '
         'ultimo momento per il pasto aziendale, inizio cucina, primo slot, prima fascia, '
         'ultimo ordine, ultimo slot, chiusura. Se non corrisponde alla vostra giornata, e '
         'un orario da correggere.'),
    ], C)

    callout(pdf, 'I valori di partenza',
            'Aperto lunedi-venerdi 07:00-17:30; ordini dalle 07:30 alle 13:15 con 20 minuti '
            'di anticipo; slot 11:45-13:30 ogni 15 minuti da 20 ordini; cucina 15 minuti '
            'prima; pasto aziendale entro le 10:30, disdetta fino a 30 minuti prima; tavoli '
            '12:00-14:30 a fasce da 30; QR del banco 10 minuti; etichette 24 ore; dieta il '
            'lunedi dalle 07:00; backup il venerdi dalle 09:00; promemoria 10/15/15 minuti. '
            'Finche non li cambiate, il servizio si comporta cosi.', NAVY, (240, 244, 250))


def sez_catalogo(pdf, idx):
    C = GREEN
    apri_sezione(pdf, 3, 'Il catalogo', 'Categorie, prodotti con i valori '
                 'nutrizionali, ingredienti del builder, articoli del banco.', C,
                 'A chi tiene il listino. Il catalogo di partenza c\'e gia: 18 '
                 'categorie e circa 75 prodotti da bar caffetteria con servizio '
                 'mensa, con i valori nutrizionali compilati.', idx)

    h2(pdf, 'Prodotti', C, idx)
    passi(pdf, [
        ('Prodotti > Prodotti: la scheda',
         'Nome, descrizione, prezzo, quantita al giorno, categoria, allergeni (i 14 ufficiali, '
         'a spunta), barcode EAN per la scansione al cesto, attivo/inattivo.'),
        ('Valori per porzione',
         'Calorie (kcal), proteine (g), carboidrati (g), grassi (g), vegetariano, vegano. Sono '
         'visibili a tutti i clienti nel menu, nel carrello, nel cesto e nel pasto aziendale '
         'come etichetta (kcal in evidenza, tre pastiglie con la parola intera). Un campo '
         'vuoto vale "non indicato", non zero: quel piatto non entra nei piani della dieta e '
         'nel carrello viene conteggiato a parte. La colonna Valori del listino mostra quali '
         'mancano.'),
        ('Categorie e stock giornaliero',
         'Prodotti > Categorie per nome, icona e colore; Prodotti > Stock Giornaliero per la '
         'disponibilita di oggi, che scende a ogni ordine e si vede nel menu ("Ultime 3!", '
         '"Esaurito").'),
    ], C)

    h2(pdf, 'Ingredienti del builder', C, idx)
    testo(pdf, 'Prodotti > Ingredienti Builder: i clienti compongono panino, insalata e poke '
               'ingrediente per ingrediente. Ogni ingrediente ha prezzo extra, allergeni, '
               'vegetariano/vegano, kcal e macro per porzione (il totale del piatto composto '
               'si aggiorna mentre il cliente sceglie) e, con il magazzino attivo, grammi per '
               'porzione e giacenza. Il pane dichiara il glutine: senza, un celiaco vedrebbe '
               'ogni panino "adatto". I prezzi base dei tre builder sono in Impostazioni > '
               'Prezzi Menu.')

    h2(pdf, 'Articoli del banco', C, idx)
    testo(pdf, 'Con il portafoglio attivo, Banco > articoli: i tasti rapidi del POS (caffe, '
               'cappuccino, brioche...) con prezzo, icona e ordine. Sono separati dal listino '
               'degli ordini: un caffe al banco non e un prodotto ordinabile a slot.')

    h2(pdf, 'Caricamento massivo da Excel', C, idx)
    passi(pdf, [
        ('Prodotti > Importa da Excel: sei modelli',
         'Prodotti del listino, ingredienti del builder, articoli del banco, consumabili del '
         'magazzino, clienti, piatti delle convenzioni. Ogni modello .xlsx ha tre fogli: Dati '
         '(da compilare), Esempio (due righe gia compilate, non importate) e Istruzioni '
         '(colonna per colonna, con le categorie, i fornitori e le convenzioni gia presenti).'),
        ('Compila e ricarica',
         'Le colonne in rosso con l\'asterisco sono obbligatorie; le altre si possono lasciare '
         'vuote o togliere: le colonne si riconoscono dal nome, non dalla posizione. SI/NO per le '
         'caselle, prezzi con virgola o punto, allergeni con le chiavi o le etichette separate da '
         'virgola. Una riga con lo stesso nome di un elemento gia presente lo aggiorna.'),
        ('Solo verifica, poi il resoconto',
         'Con "Solo verifica" il file viene controllato senza scrivere nulla. Il resoconto dice '
         'quante righe sono state create, aggiornate e quali hanno errori, riga per riga e con il '
         'motivo ("manca Prezzo", "allergene sconosciuto", "convenzione non trovata"): si '
         'correggono e si ricaricano solo quelle. Le categorie e i fornitori che non esistono '
         'vengono creati; le convenzioni no, vanno create prima.'),
    ], C)

    callout(pdf, 'Dopo un azzeramento',
            'Il reset totale e il reset della Manutenzione ricreano il catalogo di partenza '
            'con i valori nutrizionali. Se un catalogo appare vuoto subito dopo un reset, '
            'ricaricare la pagina: i dati di base tornano al primo avvio successivo.',
            ORANGE, (255, 247, 235))


def sez_clienti(pdf, idx):
    C = BLUE
    apri_sezione(pdf, 4, 'I clienti', 'Registrazione, attivazione, email, '
                 'Telegram, diete.', C,
                 'A chi accoglie i clienti e li attiva. Il passaggio che sblocca '
                 'tutto e l\'attivazione: va fatto in fretta.', idx)

    h2(pdf, 'Dall\'invito all\'attivazione', C, idx)
    passi(pdf, [
        ('Stampa e affiggi la locandina con il QR',
         'Impostazioni > Azienda > Scarica la locandina: un A4 nel kit dei manuali con che '
         'cos\'e QuickLunch, il QR di registrazione del locale, i tre passi e i vostri '
         'recapiti, generato al momento con l\'indirizzo vero. In alternativa Clienti > QR '
         'registrazione, da stampare dal browser. Dopo la registrazione il cliente torna alla '
         'pagina di accesso e resta in attesa.'),
        ('Attiva dalla lista clienti',
         'Persone > Clienti: i non attivi sono evidenziati e contati sulla dashboard. Con '
         'Attiva il cliente entra; se appartiene a un\'azienda convenzionata lo si associa '
         'alla convenzione nello stesso momento.'),
        ('Le due email, con la guida allegata',
         '"Registrazione ricevuta" appena si iscrive (da qualunque via) e "Il tuo account e '
         'attivo" quando lo attivi, entrambe con la Guida del cliente in PDF e il pulsante '
         'per collegare Telegram. Un invio fallito viene segnalato sul canale Telegram; '
         'l\'icona a busta nella lista clienti rimanda l\'email e mostra l\'esito reale.'),
        ('Telegram: si collega col codice',
         'Il cliente apre Collega Telegram (dall\'email o dal profilo), riceve un codice '
         'personale e il pulsante per aprire il bot, invia il codice, torna e conferma. '
         'Nessun "ID Telegram" da cercare. Da collegato riceve avvisi e promemoria con i '
         'bottoni.'),
        ('Clienti creati dal backoffice',
         'Persone > Clienti > Nuovo crea l\'account gia attivo: assegna sempre una password, '
         'altrimenti il cliente entra solo con Google.'),
        ('Molti clienti insieme: da Excel',
         'Prodotti > Importa da Excel > Clienti: nome, cognome, email, telefono, data di nascita, '
         'reparto, azienda convenzionata, attivo. A ogni cliente nuovo viene assegnata una '
         'password provvisoria, mostrata una sola volta nel resoconto: va comunicata a mano. '
         'Utile per i dipendenti di un\'azienda convenzionata, che vengono iscritti alla '
         'convenzione nello stesso passaggio.'),
        ('Che cosa scrive il cliente nel profilo',
         'Oltre a nome, telefono, data di nascita e indirizzo: il reparto o ufficio (per '
         'consegne e ritiri), come preferisce ricevere gli avvisi (Telegram se collegato, '
         'altrimenti email; solo Telegram; solo email) e se accetta le comunicazioni del locale. '
         'Chi dice di no non riceve novita, sondaggi e promozioni; gli avvisi di servizio '
         'arrivano comunque.'),
    ], C)

    h2(pdf, 'Come compaiono i nomi', C, idx)
    testo(pdf, 'Ovunque un cliente e visibile ad altri — display di cucina, tagliandi, liste '
               'di produzione, registri, report, tabelle — compare con il nome per esteso e '
               'il cognome puntato: "Mario R.". Il nome intero resta nei moduli che modificano '
               'l\'anagrafica e nell\'area personale del cliente.')

    h2(pdf, 'Diete clienti', C, idx)
    testo(pdf, 'Persone > Diete clienti (con la dieta attiva): chi ha dichiarato cosa — '
               'condizioni come celiachia o intolleranza al lattosio in rosso, allergeni '
               'esclusi in giallo, attenzioni (glicemia, pressione, colesterolo, gravidanza, '
               'reflusso, acido urico, fegato) in arancione, gusti in grigio (pesce, carne, '
               'formaggi, ... e le parole libere del cliente) — con fabbisogno, equilibrio del '
               'pranzo, porzione, giorni e note per il locale; i pranzi del piano di oggi '
               '(proposti e ordinati) e il conteggio dei prodotti senza valori nutrizionali, '
               'che la dieta non puo proporre.')
    callout(pdf, 'Non e uno strumento sanitario',
            'La dieta e un aiuto a scegliere dal listino: stime automatiche su valori '
            'dichiarati dal locale e formule generali, senza alcuna validita medica. Il '
            'cliente la accetta in una finestra prima di impostare le preferenze; lo staff '
            'lo trova in testa alla pagina Diete clienti. Per chi ha allergie gravi la '
            'sicurezza sta nella preparazione e nella parola del personale, non nei badge '
            'dell\'applicazione: l\'app segnala gli allergeni dichiarati, non garantisce '
            'l\'assenza di contaminazioni.', RED, (253, 238, 240))


def sez_ordini(pdf, idx):
    C = ORANGE
    apri_sezione(pdf, 5, 'Ordini e cucina', 'Dallo slot al ritiro.', C,
                 'A chi sta in cucina e al banco durante il servizio. Il flusso '
                 'e lo stesso ogni giorno: vale la pena conoscerlo bene.', idx)

    h2(pdf, 'Come nasce un ordine', C, idx)
    elenco(pdf, [
        ('Dal menu o dal builder: ', 'il cliente sceglie, il carrello mostra solo gli slot '
         'ancora raggiungibili (anticipo minimo dagli Orari) e, con la dieta attiva, le kcal '
         'del pranzo rispetto alla sua quota.'),
        ('Slot o "Adesso al banco": ', 'l\'ordine a slot ha codice QL-data-ora; quello '
         'immediato codice BANCO- e va trattato come priorita.'),
        ('Fuori finestra: ', 'nei giorni chiusi, prima dell\'apertura ordini o dopo l\'ultimo '
         'ordine la conferma e rifiutata con il motivo; il menu lo dice gia in testa.'),
        ('Pagamento: ', 'con il portafoglio attivo il totale scala dal saldo e maturano i '
         'punti; altrimenti "pagamento alla cassa al ritiro".'),
    ])

    h2(pdf, 'Cucina e ritiro', C, idx)
    passi(pdf, [
        ('Cucina / KDS',
         'Gli ordini in colonne: da preparare, in preparazione, pronto. Un tocco avanza lo '
         'stato e il cliente riceve l\'avviso ("in preparazione", "pronto") su Telegram o '
         'push. Il cliente e indicato con il cognome puntato.'),
        ('Gestione Ordini',
         'La lista completa con ricerca, stati, note e annullamento; con il portafoglio '
         'attivo l\'annullo rimborsa e toglie i punti.'),
        ('Tagliando e scontrino',
         'Sul prodotto vanno il tagliando con codice, orario e composizione e lo scontrino '
         'fiscale della cassa (non un foglio di QuickLunch). Il catalogo delle stampe '
         'raccoglie tutti i documenti che l\'applicazione produce.'),
        ('Promemoria di ritiro',
         'Qualche minuto prima dello slot (Orari > Promemoria) il cliente riceve il '
         'promemoria; per il pasto aziendale con i bottoni Si/No.'),
    ], C)

    h2(pdf, 'Slot di ritiro', C, idx)
    testo(pdf, 'Slot di Ritiro elenca la griglia, con capienza e attivo/inattivo per ogni '
               'slot e il conteggio degli ordini di oggi. La griglia nasce dagli Orari: '
               'cambiare primo slot, ultimo slot e intervallo e poi sincronizzare e la via '
               'giusta; aggiungere uno slot a mano serve per le eccezioni. Uno slot pieno non '
               'e selezionabile dal cliente.')

    h2(pdf, 'Limite di spesa giornaliero', C, idx)
    testo(pdf, 'Impostazioni > Prezzi Menu fissa quanto un cliente puo ordinare in una '
               'giornata (0 o vuoto = nessun limite per il locale). Nella scheda di ogni '
               'cliente si puo impostare un importo diverso solo per lui: vuoto usa quello '
               'del locale, uno zero esplicito toglie il limite solo a quel cliente.')
    elenco(pdf, [
        ('Quando il carrello supera il limite: ', 'non nasce un ordine ma una richiesta in '
         'attesa; il gestore riceve un avviso Telegram con due bottoni Approva/Rifiuta, '
         'stesso meccanismo del promemoria del pasto aziendale, e puo decidere anche da '
         'Ordini > Richieste di spesa.'),
        ('Solo il menu: ', 'il controllo vale solo per gli ordini dal menu/builder (place '
         'order, "adesso al banco" compreso). Il POS al banco con QR e il cesto restano '
         'fuori: sono canali di acquisto rapido a se stanti, per scelta e non per '
         'dimenticanza.'),
    ])


def sez_cesto(pdf, idx):
    C = GREEN
    apri_sezione(pdf, 6, 'Il cesto cucina', 'Pezzi preparati in anticipo, '
                 'venduti con un QR.', C,
                 'A chi prepara e a chi tiene la cassa, nei locali con il '
                 'modulo acceso.', idx)
    passi(pdf, [
        ('Genera le etichette',
         'Cucina > Cesto Cucina: scegli il prodotto e quanti pezzi; l\'applicazione stampa '
         'etichette con codice e QR, prodotto e prezzo. Qui non esiste ancora un ordine: la '
         'vendita nasce quando il cliente inquadra e paga.'),
        ('Il cliente inquadra e conferma',
         'Con il portafoglio attivo il prezzo scala dal saldo; altrimenti la consumazione '
         'viene registrata e si paga alla cassa. Il pezzo passa a "venduto".'),
        ('Ritiri e scadenze',
         'Un pezzo ritirato dal cesto (caduto, invenduto) si annulla dalla sua riga. Le '
         'etichette scadono da sole dopo le ore impostate negli Orari (24 di partenza) alla '
         'prima scansione.'),
        ('Nei report',
         'Le vendite del cesto entrano nei report e nei guadagni anche a portafoglio spento, '
         'perche vengono registrate come movimento di sola registrazione.'),
    ], C)


def sez_banco(pdf, idx):
    C = TEAL
    apri_sezione(pdf, 7, 'Il banco con il QR', 'Il conto veloce, pagato dal '
                 'portafoglio del cliente.', C,
                 'A chi sta al bancone, solo con il portafoglio prepagato '
                 'attivo: senza, il Banco non compare e il conto si salda '
                 'come in qualunque bar.', idx)
    passi(pdf, [
        ('Componi il conto',
         'Banco: gli articoli rapidi si toccano una volta, il totale si aggiorna. Il QR vale '
         'i minuti impostati negli Orari (10 di partenza), poi scade.'),
        ('Il cliente inquadra e conferma',
         'Vede il riepilogo e conferma dal telefono: il saldo scala, la sessione si chiude '
         'come pagata e compare nei report.'),
        ('Ritiro del pasto aziendale dal banco',
         'Dalla stessa pagina si cerca il codice di ritiro di una prenotazione e si '
         'registra la consegna, senza cambiare pagina durante la punta.'),
    ], C)
    callout(pdf, 'Perche sparisce senza portafoglio',
            'Il QR del banco e un pagamento dal credito prepagato. Dove si paga in cassa non '
            'ha senso: le 14 pagine del banco (cliente e staff) si spengono con il '
            'portafoglio e tornano quando lo si riaccende.', TEAL, (236, 246, 246))


def sez_tavoli(pdf, idx):
    C = PURPLE
    apri_sezione(pdf, 8, 'Tavoli e prenotazioni', 'Fasce, tavoli, promemoria.', C,
                 'A chi gestisce la sala, con il modulo acceso.', idx)
    passi(pdf, [
        ('Le fasce',
         'Gestione Tavoli > Fasce: nascono dagli Orari (prima fascia, fine, durata) con '
         '"Crea le fasce mancanti"; si aggiungono a mano per le eccezioni. Una fascia con '
         'prenotazioni non si tocca.'),
        ('I tavoli e la durata della seduta',
         'Nome, posti, attivo. La durata della seduta in minuti sugli slot compare solo con '
         'i tavoli attivi.'),
        ('Prenotazioni',
         'Il cliente sceglie fascia e tavolo; la sala vede la piantina e le prenotazioni di '
         'oggi; il promemoria parte con l\'anticipo impostato. Le prenotazioni si confermano '
         'anche dal voto di un sondaggio, se il locale lo chiede.'),
    ], C)


def sez_convenzioni(pdf, idx):
    C = PURPLE
    apri_sezione(pdf, 9, 'Convenzioni e pasto aziendale', 'Le aziende, il menu '
                 'del giorno, le prenotazioni, il ritiro, i report.', C,
                 'A chi gestisce i rapporti con le aziende e a chi consegna i '
                 'pasti.', idx)
    passi(pdf, [
        ('Aziende',
         'Convenzioni > Aziende: nome, prezzo concordato del pasto, coperti massimi al '
         'giorno, attiva. I dipendenti si associano dalla lista clienti (all\'attivazione o '
         'dopo) e vedono la voce Pasto Aziendale.'),
        ('Configurazioni e pasto del giorno',
         'Per ogni azienda si salvano configurazioni riutilizzabili (primo, secondo, contorno, '
         'bevanda, caffe, allergeni, prezzo, posti, valori nutrizionali) e da esse si '
         'pubblica il pasto del giorno, anche in piu opzioni.'),
        ('Prenotazioni',
         'Il dipendente prenota entro l\'ora degli Orari (10:30 di partenza), sceglie lo slot e '
         'la quantita, riceve un codice di ritiro; puo disdire fino ai minuti impostati. Poco '
         'prima del ritiro arriva il promemoria con i bottoni: il No annulla e avvisa il '
         'canale, cosi la cucina non prepara.'),
        ('Ritiro e report',
         'Convenzioni > Ritiro Pasti registra la consegna col codice; Report Giornaliero '
         'conta i pasti per azienda; il PDF mensile per azienda elenca i pasti per '
         'dipendente (cognome puntato, ordinato per cognome vero) e il totale da fatturare.'),
    ], C)
    callout(pdf, 'I bottoni rispondono solo con le risposte attive',
            'Il promemoria porta Si e No, ma la risposta torna all\'applicazione solo dopo '
            'aver premuto una volta Impostazioni > Notifiche > Attiva le risposte. La '
            'domanda di prova e il modo di accertarsene.', ORANGE, (255, 247, 235))


def sez_wallet(pdf, idx):
    C = GREEN
    apri_sezione(pdf, 10, 'Portafoglio e fedelta', 'Ricariche, fido, punti, '
                 'bonus. Oppure la cassa.', C,
                 'Al titolare e a chi ricarica in cassa, nei locali con il '
                 'portafoglio acceso.', idx)
    elenco(pdf, [
        ('Ricarica: ', 'dalla scheda cliente, l\'importo consegnato in cassa; il saldo si '
         'aggiorna e il movimento resta nello storico.'),
        ('Fido: ', 'il rosso massimo consentito a un cliente, sommato al saldo nei controlli '
         'di capienza: utile per il personale interno o chi salda a fine mese.'),
        ('Punti e premio: ', 'Impostazioni > Fedelta: punti per euro, soglia e valore del '
         'premio; il cliente riscatta dal proprio Wallet.'),
        ('Bonus di benvenuto: ', 'accreditato a ogni nuovo cliente, da qualunque via si '
         'registri; il valore predefinito e zero.'),
        ('Storico: ', 'ogni movimento e una transazione; il saldo si muove solo attraverso '
         'ricariche, addebiti, rimborsi e riscatti, cosi lo storico e sempre coerente.'),
    ])
    callout(pdf, 'Senza portafoglio',
            'Spento il modulo, l\'app non muove denaro: si ordina e si paga alla cassa, il '
            'banco con il QR sparisce, ordini e cesto restano nei report. I saldi esistenti '
            'non si azzerano: riaccendendo tornano visibili.', GREEN, (240, 250, 244))


def sez_magazzino(pdf, idx):
    C = PURPLE
    apri_sezione(pdf, 11, 'Il magazzino', 'Consumabili, fornitori, giacenze '
                 'degli ingredienti.', C,
                 'A chi fa gli ordini ai fornitori, con il modulo acceso.', idx)
    passi(pdf, [
        ('Consumabili',
         'Magazzino > Consumabili: articolo, unita, quantita, soglia minima, fornitore. '
         'Sotto soglia l\'articolo va in allerta (riquadro "Alert magazzino" in dashboard) e '
         'con un movimento si puo avvisare il fornitore per email.'),
        ('Fornitori',
         'Magazzino > Fornitori: anagrafica con email e telefono, collegata ai consumabili.'),
        ('Giacenza degli ingredienti',
         'Negli Ingredienti Builder: grammi per porzione e giacenza in grammi; ogni ordine '
         'con il builder scarica la giacenza in automatico e la colonna Giacenza segnala la '
         'scorta bassa. Con il modulo spento non si scarica nulla.'),
    ], C)


def sez_comunicazioni(pdf, idx):
    C = BLUE
    apri_sezione(pdf, 12, 'Comunicazioni', 'Campagne per gruppi di clienti, modelli '
                 'pronti, automatismi, sondaggi, notifiche.', C,
                 'A chi parla con i clienti. La regola: pochi messaggi, mirati, con un '
                 'motivo; e mai a chi ha detto di no.', idx)

    h2(pdf, 'Campagne: scrivere ai clienti', C, idx)
    passi(pdf, [
        ('Scegli un modello',
         'Comunicazioni > Campagne: dodici modelli gia scritti, ognuno con il gruppo di clienti e '
         'il canale consigliati — Benvenuto (ai nuovi iscritti), Menu della settimana, Novita nel '
         'menu, Ci manchi (a chi non ordina da un mese), Buon compleanno, Invito a votare (per un '
         'sondaggio), Avviso di chiusura, Prenota i pasti della settimana (ai convenzionati), La tua '
         'dieta settimanale (a chi non l\'ha provata), Collega Telegram (a chi riceve tutto per '
         'email), Grazie (ai clienti abituali), Messaggio libero.'),
        ('Adatta il testo',
         'Oggetto, testo, pulsante con link. I segnaposto in graffe si compilano per ciascun '
         'destinatario: {nome}, {locale}, {orari} (dalla scheda Orari), {link_menu}, {link_dieta}, '
         '{link_telegram}, {sondaggio}, {link_sondaggio}... Basta un clic sul segnaposto per '
         'inserirlo. Una riga vuota separa i paragrafi; le righe che iniziano con "- " diventano '
         'un elenco.'),
        ('Scegli a chi e come',
         'I gruppi: tutti, clienti abituali (hanno ordinato negli ultimi 30 giorni), chi non '
         'ordina da un mese, registrati senza ordini, iscritti da meno di 7 giorni, convenzionati, '
         'con o senza dieta, compleanno entro 7 giorni, collegati o no a Telegram. Accanto a '
         'ognuno il numero di persone. Il canale Automatico manda su Telegram a chi l\'ha '
         'collegato e per email agli altri, rispettando la preferenza scritta nel profilo; in '
         'alternativa solo email, solo Telegram (chi non e collegato viene saltato) o entrambi.'),
        ('Prova, anteprima, invio',
         '"Prova su di me" manda il messaggio a te; "Anteprima" mostra l\'email come la vedra il '
         'cliente. Poi "Invia ora" (con conferma e numero di destinatari), oppure "Programma" con '
         'giorno e ora: la campagna parte alla prima visita di qualcuno dopo quell\'ora, come i '
         'promemoria. Una campagna inviata non si modifica: si duplica.'),
        ('Il registro',
         'Ogni campagna inviata mostra a chi e arrivata e su quale canale, chi e stato saltato e '
         'perche (Telegram non collegato, senza email), e i fallimenti con il motivo del server.'),
    ], C)

    h2(pdf, 'Automatismi', C, idx)
    testo(pdf, 'Tre interruttori, spenti di partenza: Benvenuto dopo 7 giorni (a chi si e '
               'iscritto una settimana fa), Auguri di compleanno (il giorno stesso, una volta '
               'l\'anno), "Ci manchi" dopo 30 giorni (a chi non ordina da 30-45 giorni, non piu '
               'di una volta ogni due mesi). Partono una volta al giorno dall\'ora impostata in '
               'Impostazioni > Orari > Appuntamenti della settimana (le 10:00 di partenza) e ogni '
               'giro crea una campagna che resta nell\'elenco con il suo registro.')

    h2(pdf, 'Il consenso del cliente', C, idx)
    callout(pdf, 'Chi dice no non riceve nulla',
            'Nel profilo il cliente sceglie se ricevere le comunicazioni del locale e in fondo a '
            'ogni email c\'e il link "Non voglio piu ricevere le comunicazioni", che funziona '
            'senza accesso. Le campagne e gli automatismi lo rispettano sempre; gli avvisi di '
            'servizio (ordine pronto, promemoria del pasto, piano della dieta richiesto dal '
            'cliente) non passano da qui e continuano ad arrivare. Per i link nelle email degli '
            'automatismi serve l\'indirizzo pubblico dell\'app in Impostazioni > Azienda.',
            BLUE, (235, 243, 252))

    h2(pdf, 'Sondaggi, broadcast, notifiche', C, idx)
    passi(pdf, [
        ('Sondaggi',
         'Comunicazioni > Sondaggi: una domanda con opzioni (emoji e testo), voto unico per '
         'cliente, risultati in tempo reale; si puo chiedere di confermare la prenotazione del '
         'tavolo con il voto. Il pulsante "Invita a votare" apre una campagna gia compilata con '
         'titolo, scelte e link del sondaggio; restano anche l\'avviso sul canale Telegram dello '
         'staff e l\'email a tutti.'),
        ('Broadcast',
         'Impostazioni > Broadcast: un messaggio a tutti, subito, sul canale Telegram e per '
         'email. Per i gruppi, i modelli e la programmazione si usano le Campagne.'),
        ('Notifiche automatiche',
         'Nuovo cliente e nuovo ordine sul canale dello staff; al cliente conferma d\'ordine '
         '(con le kcal se ha la dieta), stati della cucina, promemoria, piano della dieta, '
         'avvisi di ricarica; notifiche push dal browser per chi le attiva dalla campanella.'),
    ], C)


def sez_dieta(pdf, idx):
    C = GREEN
    apri_sezione(pdf, 13, 'La dieta settimanale', 'Cosa vede il cliente, cosa '
                 'serve al locale.', C,
                 'Al titolare, per capire il modulo e cosa gli chiede.', idx)
    elenco(pdf, [
        ('Il cliente dichiara: ', 'condizioni (celiachia, lattosio, uova, frutta a guscio, '
         'pesce e frutti di mare, soia), altri allergeni, regime (onnivoro, vegetariano, '
         'vegano), obiettivo (mantenere, perdere -15%, perdere piu in fretta restando '
         'bilanciato -25% mai sotto il metabolismo basale, aumentare), attenzioni (glicemia '
         'alta o diabete, pressione alta, colesterolo alto, gravidanza o allattamento, '
         'reflusso, digestione lenta, acido urico alto, fegato affaticato: ognuna fa evitare '
         'al piano certe famiglie di piatti e le segnala nel menu), equilibrio del pranzo '
         '(bilanciato, piu proteine, pochi carboidrati, mediterraneo), quando si allena, dati '
         'corporei facoltativi (sesso, peso, altezza, peso obiettivo, girovita, pasti al '
         'giorno, porzione piccola/normale/abbondante, colazione al bar), gusti non graditi '
         'per gruppo e parole libere, piatti esclusi, giorni in cui pranza qui, budget.'),
        ('Il referto delle analisi: ', 'dalla pagina della dieta il cliente puo caricare il PDF '
         'del laboratorio o scrivere i valori a mano (glicemia, emoglobina glicata, '
         'colesterolo totale/HDL/LDL, trigliceridi, acido urico, emoglobina, ferritina, '
         'vitamina D, creatinina, transaminasi, pressione). L\'applicazione li confronta con '
         'intervalli di riferimento generali e propone quali attenzioni accendere e quale '
         'equilibrio del pranzo usare, con qualche consiglio in parole; "Applica" aggiorna il '
         'profilo e rifa il piano. Il file viene letto e scartato: restano solo i valori, che il '
         'cliente puo cancellare. Nessuna lettura medica: ogni valore fuori soglia va discusso '
         'con il medico, e la pagina lo ripete.'),
        ('Riceve: ', 'il fabbisogno (Mifflin-St Jeor per attivita e obiettivo, o le kcal del '
         'nutrizionista, con la quota del pranzo modulata da porzione e allenamento), gli '
         'indicatori generali (indice di massa corporea, rapporto vita/altezza) e una stima di '
         'quante settimane servono per il peso obiettivo a quel ritmo, il menu con "Adatto a te" '
         'o il motivo, i gusti e le attenzioni in grigio, il '
         'carrello con le kcal rispetto alla quota e la conferma esplicita se c\'e un '
         'allergene escluso, il piano della settimana ordinabile con un tocco, le calorie di '
         'oggi in home, l\'avviso settimanale.'),
        ('Serve al locale: ', 'i valori nutrizionali sui prodotti (il listino di partenza li '
         'ha; i vostri piatti li ricevono dalla scheda). Un piatto senza valori non entra nei '
         'piani. La pagina Diete clienti riassume esigenze e pranzi del giorno per la cucina.'),
        ('Il disclaimer: ', 'nessuna validita medica; il cliente lo accetta in finestra prima '
         'di salvare, lo staff lo legge in testa a Diete clienti. Non va ammorbidito.'),
    ])


def sez_report(pdf, idx):
    C = NAVY
    apri_sezione(pdf, 14, 'Report e guadagni', 'I numeri della giornata e del '
                 'mese.', C,
                 'Al titolare e a chi tiene la contabilita.', idx)
    elenco(pdf, [
        ('Dashboard: ', 'ordini di oggi, clienti da attivare, alert magazzino (con il modulo), '
         'prenotazioni, andamento.'),
        ('Report: ', 'vendite per periodo, prodotto e categoria; con il portafoglio, ricariche '
         'e saldi; esportazioni.'),
        ('Guadagni: ', 'il quadro economico del gestore, con il cesto contato dalle vendite '
         'registrate anche a portafoglio spento.'),
        ('Report Giornaliero e PDF mensile delle convenzioni: ', 'i pasti per azienda, il '
         'documento da allegare alla fattura.'),
        ('Carico mensile di prova: ', 'Impostazioni > Dati genera un mese di attivita '
         'verosimile per vedere report e andamenti prima dei dati veri; si elimina per '
         'intero con un pulsante e non tocca i saldi.'),
    ])


def sez_dati(pdf, idx):
    C = TEAL
    apri_sezione(pdf, 15, 'Dati e sicurezza', 'Backup, ripristino, '
                 'azzeramento, ruoli.', C,
                 'All\'amministratore dei tenant (DS Consulting), che e il solo a '
                 'vedere il tab Dati, e al titolare per sapere che cosa chiedere. '
                 'Sono le operazioni che non si fanno ogni giorno ma che salvano '
                 'la settimana.', idx)

    h2(pdf, 'Backup e ripristino', C, idx)
    passi(pdf, [
        ('Scarica il backup ogni settimana',
         'Impostazioni > Dati > Scarica il backup: un file JSON con tutte le tabelle di '
         'tutti i locali, clienti, ordini, catalogo con i valori nutrizionali, convenzioni, '
         'diete, impostazioni. La pagina mostra la data dell\'ultimo backup e nel giorno '
         'scelto negli Orari, se ne sono passati piu di sei, il canale Telegram del locale '
         'predefinito riceve un promemoria. Il file contiene dati personali e credenziali: '
         'conservalo come un registro contabile, fuori dal server.'),
        ('Guarda l\'anteprima prima di ripristinare',
         'Scelto il file, la pagina dice quando e stato creato, tabelle, righe, utenti, ordini '
         'e prodotti, e avvisa se e vecchio o precedente a una funzione (per esempio la '
         'dieta), il cui contenuto attuale andrebbe perso.'),
        ('Ripristina a locale chiuso',
         'Prima di cancellare, lo stato attuale viene inviato per email a chi ripristina: '
         'senza quella copia il ripristino si ferma, salvo scelta esplicita. Al termine il '
         'messaggio elenca righe caricate, tabelle svuotate e colonne ignorate; i dati di '
         'base vengono ricontrollati subito e si viene disconnessi.'),
    ], C)

    h2(pdf, 'Azzeramento e manutenzione', C, idx)
    testo(pdf, 'Impostazioni > Dati > Reset totale svuota tutto e ricrea i dati di base '
               '(chiede di scrivere AZZERA e riporta le utenze amministrative ai valori '
               'predefiniti: cambiate le password subito dopo). Manutenzione offre pulizie '
               'parziali (ordini, catalogo, ingredienti, dati demo): dopo un reset parziale il '
               'catalogo di partenza torna da solo. Scaricare un backup prima, sempre.')

    h2(pdf, 'Ruoli e permessi', C, idx)
    tabella(pdf, ['Ruolo', 'Che cosa fa', 'Permessi tipici'],
            [['Amministratore dei tenant', 'Uno solo, senza locale: crea i locali, entra in '
              'ciascuno dal selettore in alto, nomina il loro amministratore; e il solo che '
              'vede Dati, Tenant, Guadagni, Manutenzione.', 'Nessun controllo: bypassa i permessi.'],
             ['Amministratore del locale', 'Tutto, ma solo sui dati del proprio locale: '
              'catalogo, clienti, personale, impostazioni, report.', 'Nessun controllo dentro '
              'il locale; non vede gli altri locali ne il tab Dati.'],
             ['Manager', 'Amministra il locale: catalogo, clienti, convenzioni, '
              'impostazioni, report.', 'Gestione prodotti, categorie, ingredienti, stock, '
              'tavoli, slot, clienti, sondaggi, notifiche, impostazioni, report.'],
             ['Cassiere', 'Banco, ordini, clienti al banco, ricariche.', 'Vedi/gestisci ordini, '
              'clienti, stock.'],
             ['Cuoco', 'Cucina/KDS, cesto, stati degli ordini.', 'Vedi/gestisci ordini, cesto.']],
            [26, 62, 58], C)
    testo(pdf, 'Persone > Ruoli & Permessi: i ruoli di sistema si adattano, gli altri si '
               'creano. Una voce di menu compare solo a chi ha il permesso; una rotta non '
               'coperta da permesso e comunque raggiungibile solo dallo staff. La verifica in '
               'due passi (MFA) si attiva dal profilo di ciascuno.', 9.5)


def sez_problemi(pdf, idx):
    C = RED
    apri_sezione(pdf, 16, 'Problemi tipici', 'Cosa succede, perche, cosa fare.', C,
                 'A chiunque risponda al telefono quando qualcosa non va.', idx)
    tabella(pdf, ['Sintomo', 'Causa', 'Cosa fare'],
            [['Il cliente dice di essersi iscritto ma non e in lista', 'Registrazione arrivata '
              'ma non ancora nella lista del locale (raro, dopo un riavvio).', 'Ricarica la '
              'pagina Clienti; se manca ancora, cerca per email; da Nuovo cliente si crea '
              'gia attivo.'],
             ['Il cliente non ha ricevuto l\'email', 'Gmail non configurata, indirizzo '
              'sbagliato, posta indesiderata.', 'Impostazioni > Notifiche; icona a busta nella '
              'lista clienti per rimandarla e vedere l\'esito.'],
             ['I bottoni Si/No del pasto non fanno nulla', 'Risposte ai bottoni non attivate '
              '(webhook).', 'Impostazioni > Notifiche > Attiva le risposte; poi Domanda di '
              'prova e Diagnostica.'],
             ['Un ordine viene rifiutato', 'Fuori finestra, giorno chiuso o slot troppo '
              'vicino: il messaggio dice quale.', 'Impostazioni > Orari; il carrello mostra il '
              'motivo al cliente.'],
             ['Nel carrello non ci sono slot', 'Tutti gli slot restanti sono sotto l\'anticipo '
              'minimo, o la griglia e cambiata.', 'Orari > anticipo e griglia; Sincronizza gli '
              'slot; "Adesso al banco" se aperto.'],
             ['La dieta non propone un piatto', 'Valori nutrizionali non indicati, allergene '
              'escluso o gusto non gradito.', 'Compila la scheda prodotto; Diete clienti '
              'conta i piatti senza valori.'],
             ['Il catalogo e vuoto dopo un reset', 'I dati di base tornano all\'avvio '
              'successivo.', 'Ricarica; su Vercel puo servire qualche minuto.'],
             ['Il Banco e sparito', 'Portafoglio prepagato spento.', 'E voluto: il QR paga dal '
              'credito. Riaccendi il portafoglio se serve.'],
             ['Vecchio backup ripristinato: preferenze dieta sparite', 'Il file era precedente '
              'alla dieta: la tabella e stata svuotata (il messaggio lo dice).', 'Usa la copia '
              'inviata per email prima del ripristino.']],
            [44, 52, 50], C)

    _spazio(pdf, 4)
    callout(pdf, 'Assistenza',
            'DS Consulting · Daniele Speziale · %s · %s. Per i problemi tecnici allegate '
            'lo screenshot del messaggio e, se c\'e, l\'esito della pagina Diagnostica.'
            % (EMAIL, CELL), NAVY, (240, 244, 250))


# ═════════════════════════════════════════════════════════════════════════════
def costruisci(voci_indice=None):
    pdf = Guida(format='A4')
    pdf.add_font(FONT, '', os.path.join(FONT_DIR, 'PTSansNarrow-Regular.ttf'))
    pdf.add_font(FONT, 'B', os.path.join(FONT_DIR, 'PTSansNarrow-Bold.ttf'))
    pdf.set_margins(ML, 18, 16)
    pdf.set_auto_page_break(True, margin=20)
    pdf.etichetta_testata = 'QuickLunch · Manuale del gestore'

    copertina_gestore(pdf)
    pagina_indice(pdf, voci_indice)

    raccolte = []
    for sezione in (sez_prima_di_aprire, sez_orari, sez_catalogo, sez_clienti, sez_ordini,
                    sez_cesto, sez_banco, sez_tavoli, sez_convenzioni, sez_wallet,
                    sez_magazzino, sez_comunicazioni, sez_dieta, sez_report, sez_dati,
                    sez_problemi):
        sezione(pdf, raccolte)
    return pdf, raccolte


def main():
    _pdf, voci = costruisci(None)
    pdf, _ = costruisci(voci)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    pdf.output(OUT)
    print('[OK] %s' % OUT)
    print('     %d pagine, %d byte, %d voci di indice'
          % (len(pdf.pages), os.path.getsize(OUT), len(voci)))


if __name__ == '__main__':
    main()
