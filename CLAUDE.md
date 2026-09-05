# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Progetto

QuickLunch: web app Flask multi-tenant per bar/mensa aziendale. Ordini con ritiro a slot,
wallet prepagato con punti fedeltà, builder panino/insalata/poke, POS banco con pagamento
via QR, pasti aziendali convenzionati, prenotazione tavoli a fasce, magazzino consumabili,
backoffice con RBAC a permessi.

UI, commenti e messaggi utente sono in italiano: mantieni la lingua nel codice nuovo.
`docs/app_spec.txt` è la specifica funzionale completa dell'app, utile come riferimento
quando serve capire il comportamento atteso di un flusso.

## Comandi

```bash
# Setup locale (nessun venv è versionato)
python -m venv venv && venv/Scripts/activate      # Windows
pip install -r requirements.txt

python run.py                    # dev server su http://localhost:5300 (debug attivo)
flask --app run.py seed-demo     # resetta e ricarica i dati demo (3 tenant, ~100 clienti)
```

Il DB di default è SQLite (`instance/bar.db`), creato al primo avvio. Per puntare a
PostgreSQL si imposta `DATABASE_URL` (o `POSTGRES_URL`) in `.env` — vedi `.env.example`.

Non esistono test, linter o formatter configurati nel repo.

### Vincoli di versione dell'ambiente

`requirements.txt` è pinnato per il runtime di Vercel (Python 3.11) e **non installa su
Python 3.13**:

- `psycopg2-binary==2.9.9` non ha wheel per 3.13 e tenta la build da sorgente (serve `pg_config`).
- `SQLAlchemy==2.0.30` non è compatibile con 3.13 (`TypeError: Can't replace canonical symbol
  for '__firstlineno__'`); serve >= 2.0.36.

Per lavorare in locale su 3.13: installa senza `psycopg2-binary` (non serve con SQLite) e
aggiorna SQLAlchemy solo nel venv, **senza modificare i pin** di `requirements.txt`, che
governano il deploy.

## Deploy

Vercel, entry point `api/index.py` (non `run.py`): `vercel.json` instrada ogni richiesta a
quel file. `ProxyFix` è obbligatorio lì, altrimenti `url_for(..., _external=True)` genera
`http://` e rompe il callback OAuth di Google. DB in produzione: Neon PostgreSQL.

## Architettura

Factory pattern in `app/__init__.py` (`create_app()`), quattro blueprint:

| Blueprint | Prefisso | File | Ruolo |
|---|---|---|---|
| `auth` | `/auth` | `app/auth/routes.py` | login/registrazione, Google OAuth, MFA TOTP |
| `main` | `/` | `app/main/routes.py` | area cliente |
| `admin` | `/admin` | `app/admin/routes.py` | backoffice (file più grande, ~4000 righe) |
| `tenant` | `/t` | `app/tenant/routes.py` | landing e registrazione per singolo tenant |

Tutti i modelli sono in `app/models.py`. `app/notifications.py` centralizza Telegram, Gmail
SMTP e Web Push (VAPID). `app/demo_seed.py` genera dati demo deterministici (`Random(42)`).

### Schema DB: nessun Alembic

Lo schema è gestito a mano e **ogni chiamata a `create_app()` esegue**, in questo ordine:

1. `db.create_all()` — crea le tabelle nuove.
2. `_migrate_tenant_columns()` — `ALTER TABLE ADD COLUMN` idempotenti tramite l'helper
   `_ensure(tabella, colonna, definizione)`, con traduzione dei tipi SQLite → PostgreSQL.
3. `_seed_defaults()` — permessi, ruoli, superadmin, categorie (18), listino di partenza
   (~75 prodotti da bar caffetteria/mensa), slot, tavoli, articoli banco, ingredienti del
   builder, impostazioni di default. Ogni blocco è idempotente (`if not X.query.first()` o
   `filter_by(...).first()`).

**Per aggiungere una colonna**: dichiarala nel modello *e* aggiungi un `_ensure(...)` in
`_migrate_tenant_columns()`, altrimenti i database esistenti (produzione compresa) non la
riceveranno mai. Lo stesso vale per nuovi permessi, che vanno aggiunti al blocco
idempotente `extra_perms` e non alla lista iniziale (eseguita solo su DB vuoto).

**SQLite non impone la lunghezza dei `VARCHAR`, PostgreSQL sì.** Una chiave più lunga della
colonna (`'dimagrimento_forte'`, 18 caratteri, in `obiettivo String(16)`) passa tutti i test in
locale e in produzione muore con `StringDataRightTruncation` al primo salvataggio. Chi aggiunge
valori a una lista di chiavi (`OBIETTIVI_DIETA`, `REGIMI_DIETA`, stati, ecc.) controlli la
lunghezza della colonna; `smoke_dieta` lo verifica per quelle della dieta. Per allargare una
colonna già esistente c'è `_allarga(tabella, colonna, lunghezza)` in `_migrate_tenant_columns()`
(solo PostgreSQL, idempotente): allargare il modello da solo non basta, la tabella in
produzione resta com'era.

Dentro `_seed_defaults()`, subito dopo la creazione del tenant di default, c'è un loop che
assegna `tenant_id = <default>` a **tutte** le righe orfane di `orphan_tables` (users,
orders, table_reservations, prodotti, ecc.), silenziosamente e a ogni avvio. Prima di
scrivere una migrazione o un backfill di `tenant_id`, controlla se quel loop già lo copre.

Quel loop però gira **prima** dei blocchi che creano i dati di base, quindi non li copre:
un blocco di seed che dimentica `tenant_id=default_tenant.id` produce righe invisibili nel
backoffice fino al riavvio *successivo*. Dopo un `reset_totale()` l'effetto è un catalogo
apparentemente vuoto. Tutti i blocchi (categorie, slot, tavoli, categorie ingredienti panino
e poke, articoli del banco) ora passano il tenant esplicitamente: **fallo anche nei blocchi
nuovi**.
Effetto collaterale noto: anche i due superadmin globali, che per progetto hanno
`tenant_id = None`, si ritrovano agganciati al tenant di default dopo un riavvio.

### Vincolo del pool su Vercel (ha già rotto un deploy)

In produzione `SQLALCHEMY_ENGINE_OPTIONS` impone `pool_size=1, max_overflow=0`. Il codice
eseguito durante `create_app()` non deve mai chiedere una **seconda** connessione mentre la
sessione ORM ne tiene una: una query ORM apre una transazione e trattiene la connessione,
quindi un `db.engine.connect()` o un `inspect(db.engine)` successivi vanno in
`QueuePool limit of size 1 overflow 0 reached` dopo 30s e l'import di `api/index.py`
fallisce, con l'intera app offline. In un helper di avvio: o solo ORM, o solo una singola
connessione esplicita (`db.session.remove()` prima di aprirla), mai i due mescolati. La
riproduzione locale si ottiene forzando `poolclass=QueuePool, pool_size=1, max_overflow=0`
sull'engine SQLite.

### Multi-tenancy

Quasi tutte le tabelle hanno `tenant_id` nullable. Il super admin globale ha
`tenant_id = None` e ricade sul tenant di slug `default` tramite due helper gemelli:
`_active_tenant_id()` (admin) e `_effective_tenant_id()` (main).

**Ogni record nuovo che appartiene a un tenant deve ricevere il `tenant_id` esplicitamente
alla creazione**: non esiste un default né un event listener. Le viste del backoffice
filtrano per tenant, quindi un record creato senza `tenant_id` non compare da nessuna parte.

Per i **clienti** servono due campi insieme, perché `clients_dt` filtra
`is_client=True, tenant_id=<tenant>`: senza `tenant_id` l'utente è invisibile finché il loop
`orphan_tables` non lo aggancia al riavvio (su Vercel, imprevedibile); senza `is_client=True`
— che nel modello ha default **False** — non compare mai. È già capitato su tutti e cinque i
punti che creano un cliente: `auth.register` e `auth.google_callback` (che non hanno un
tenant nel contesto e usano l'helper `_tenant_predefinito()`), `tenant.register` e
`tenant.google_callback` (che hanno `tenant.id` ma dimenticavano `is_client`) e
`admin.client_new`. Effetto tipico: la notifica Telegram di nuova registrazione arriva —
`send_telegram` non filtra nulla — ma il titolare non trova il cliente e non può attivarlo.
Se aggiungi un percorso di registrazione, valorizza entrambi i campi e la coppia
`is_active`/redirect: una pagina che promette "in attesa di attivazione" richiede
`is_active=False`, altrimenti l'utente entra scavalcando l'approvazione.

Lo scoping non è ancora uniforme: gli endpoint DataTables (`*_dt`) filtrano per tenant,
mentre alcune viste (dashboard, tavoli, prodotti) interrogano senza filtro. In uno scenario
multi-tenant reale questo mescola i dati fra tenant.

### RBAC

`User → Role → Permission` con due tabelle di associazione. `is_admin=True` bypassa ogni
controllo (`has_permission()` ritorna sempre `True`). Decoratori in `app/admin/routes.py`:
`@staff_required` (admin o qualunque permesso di backoffice) e
`@require_permission('nome_permesso')`. `User.is_staff` deriva dall'appartenenza a un
insieme di permessi elencato inline nel modello.

La sidebar in `base.html` è guidata dagli stessi permessi via lo shorthand
`{% set p = current_user.has_permission %}`: una voce di menu nuova va condizionata con
`{% if p('...') %}`.

### CSRF

`CSRFProtect` è attivo su tutta l'app. Convenzioni da rispettare nel codice nuovo:

- **Form renderizzato da Jinja**: aggiungi `{{ csrf_field() }}` subito dentro il `<form>`.
  Il global è registrato in `create_app()`.
- **Form costruito da JavaScript**: usa `qlPostForm()` invece di `$('<form method="POST">')`;
  restituisce già il form con il token. Per chi genera HTML come stringa (renderer
  DataTables) c'è `qlCsrfInputHtml()`.
- **fetch/AJAX non-GET**: passa il token nell'header `X-CSRFToken` (o come campo
  `csrf_token` nel FormData). In pagina è disponibile come `window.QL_CSRF`.

Gli helper sono definiti in `base.html`, insieme a un listener `submit` di sicurezza che
aggiunge il token ai form POST che ne fossero privi. I template che **non** estendono
`base.html` (pagine `auth/`, `cesto_scan.html`, `tenant/`, pagine di stampa) non hanno
quegli helper: lì il token deve arrivare da `{{ csrf_field() }}`.

`WTF_CSRF_TIME_LIMIT = None` in `config.py`: il token vive quanto la sessione (8h), perché
il default di un'ora scadeva sulle schermate POS/KDS lasciate aperte per tutto il turno.

### Funzionalità attivabili (feature flag)

I moduli disattivabili sono `AppSetting` con valore `'1'`/`'0'`, gestiti dal tab
**Funzionalità** di `/admin/settings`. Oggi ce ne sono quattro: `tables_enabled` (gestione
tavoli e prenotazioni), `cesto_enabled` (cesto cucina con etichette QR), `wallet_enabled`
(portafoglio prepagato e fedeltà — vedi la sezione Wallet) e `dieta_enabled` (dieta
settimanale dei clienti — vedi la sezione Dieta). Gli helper
passano tutti da `_funzione_attiva(chiave)` in `app/__init__.py`: un flag nuovo aggiunge
solo una funzione di una riga, non un'altra copia della cache su `g`. Per aggiungerne un
altro servono cinque punti:

1. la chiave in `default_settings` dentro `_seed_defaults()`, con default `'1'` per non
   cambiare il comportamento delle installazioni esistenti;
2. la chiave in `all_keys` della vista `admin.settings`;
3. una card con checkbox nel tab Funzionalità — **serve un `<input type="hidden" name="X"
   value="0">` prima della checkbox**, altrimenti una casella deselezionata non invia nulla
   e `get_setting()` restituirebbe il default (cioè "attivo"). `settings_save` legge
   `getlist(k)[-1]`, quindi vince il valore della checkbox quando è selezionata;
4. un helper di una riga in `app/__init__.py` che chiama `_funzione_attiva('chiave')` e il
   flag nel context processor `_inject_feature_flags`, così i template lo vedono senza che
   ogni vista lo passi;
5. il decoratore `@tables_required` — definito in `admin/routes.py` e in `main/routes.py`,
   con redirect diverso — su **tutte** le rotte del modulo, non solo sulle viste: nascondere
   la voce di menu non basta a rendere una pagina irraggiungibile.

### Strumenti sui dati (`app/data_tools.py`)

Tre procedure per il solo super admin, esposte dal tab **Dati** di `/admin/settings`:

- **Carico mensile**: `genera_carico()` crea un mese di attività (pasti aziendali, ordini
  panino/bevanda, caffè al banco, prodotti builder) con quantità giornaliere configurabili
  dalle impostazioni `sim_*_min` / `sim_*_max`. Ogni riga creata viene annotata in
  `CaricoMensileRiga` (entità + chiave primaria): è quel registro che rende l'operazione
  annullabile. Non tocca i saldi dei wallet, così l'eliminazione è un annullamento completo.
- **Reset totale**: `reset_totale()` svuota tutte le tabelle e riesegue `_seed_defaults()`.
  Diverso dal `reset_all` della pagina Manutenzione, che è **parziale** (non tocca
  impostazioni, slot, tavoli e articoli del banco) ma che ora richiama a sua volta
  `_seed_defaults()` in coda.

**Ogni percorso che cancella il catalogo deve ripassare dal seed.** Sono tre e sono in file
diversi — `reset_totale()` in `data_tools.py`, `reset_all` in `admin/routes.py`,
`reset_demo_data()`+`seed_demo_data()` in `demo_seed.py` — ed è facile correggerne uno solo:
`reset_all` cancellava categorie e ingredienti senza ricrearli, lasciando il gestore con un
catalogo vuoto (e apparentemente un bug) fino al riavvio successivo, quando il seed li
ripristinava da sé. Le pulizie selettive della Manutenzione (`clear_catalog`,
`clear_ingredients`) restano invece senza seed, perché svuotare è proprio quello che
chiedono: lì il messaggio spiega come riavere i valori predefiniti.
- **Backup/restore**: `esporta_backup()` / `importa_backup()`, JSON tabella per tabella,
  indipendente dal motore. Su PostgreSQL il restore riallinea le sequenze
  (`_sistema_sequenze()`), altrimenti i nuovi inserimenti collidono sugli id.
  Il file porta anche `schema` (colonne per tabella), `righe` e `app`; la versione resta `1`
  perché il formato è compatibile in entrambe le direzioni. `analizza_backup()` confronta un
  file col database senza toccare nulla ed è ciò che alimenta le **note** del restore:
  tabelle del file sconosciute, tabelle del database che il file non conosce (svuotate, con
  quante righe avevano — è il caso di un backup precedente a una funzione, come la dieta),
  colonne ignorate. `_deserializza()` dà a tutte le righe di una tabella le stesse chiavi,
  perché l'insert a blocchi le vuole omogenee. In coda al restore gira `_seed_defaults()`:
  permessi, impostazioni e valori nutrizionali mancanti tornano subito, non al riavvio
  successivo (su Vercel imprevedibile). Dopo il restore la rotta fa `logout_user()`
  esplicito: l'id di chi ripristina esiste ancora nel file, il login lo rimanderebbe alla
  dashboard e il messaggio d'esito si perderebbe.
  La rotta manda prima per email lo stato attuale (`copia_di_sicurezza_pre_restore()`,
  allegato temporaneo rimosso subito) e senza quella copia **si ferma**, salvo la casella
  "procedi anche senza copia". `registra_backup_eseguito()` annota `ultimo_backup_il`;
  `_check_backup_reminder()` (venerdì ≥ 9, `backup_promemoria_il` contro i doppi) avvisa il
  canale staff se l'ultimo backup ha più di sei giorni. L'anteprima del file nella pagina
  Dati è JavaScript nel browser (FileReader), così non serve un upload di prova.

**L'ordine di cancellazione si ricava dai metadati**, non a mano:
`reversed(db.metadata.sorted_tables)` rispetta le chiavi esterne e si adatta ai modelli
nuovi. Usalo ogni volta che serve svuotare più tabelle.

Il contro-esempio è `_delete_tenant_data()` in `demo_seed.py`, che ha l'ordine scritto a
mano: quando sono stati aggiunti `prep_labels`, `prenotazioni`, `push_subscriptions` e
`meal_configurations` nessuno l'ha aggiornata, e in produzione il reset demo è morto con
`ForeignKeyViolation` su `prep_labels_product_id_fkey`. **Se aggiungi un modello con una FK
verso prodotti, utenti o convenzioni, aggiorna anche quella funzione** — o meglio, portala
sull'ordinamento da metadati.

### Come si mostra il nome di un cliente

`User` ha due proprietà e non sono interscambiabili:

- **`display_name`** — `'Mario R.'`, nome per esteso e cognome ridotto alle iniziali
  (`'De Luca'` → `'D. L.'`). È la forma da usare in **ogni pagina e stampa** in cui il
  cliente è visibile a qualcun altro: display di cucina, tagliando ordine, liste di
  produzione, registro presenze, report PDF, tabelle del backoffice.
- **`full_name`** — nome e cognome per intero. Resta solo dove serve il dato vero: i campi
  dei form che modificano l'anagrafica (`clients_dt` espone `first_name`/`last_name` proprio
  per quelli) e le pagine in cui l'utente vede sé stesso (navbar, profilo).

Ordinamenti e ricerche vanno sempre sulle colonne reali (`last_name`, `first_name`), non
sulla stringa mostrata: il PDF mensile delle convenzioni, per esempio, mostra il nome
puntato ma ordina per cognome vero tramite una chiave separata.

### Wallet e fedeltà

Il saldo si muove **solo** attraverso i metodi di `User` (`credit_wallet`, `debit_wallet`,
`add_points`, `redeem_points`): ognuno crea la `Transaction` corrispondente, così lo storico
resta coerente.

Il portafoglio è **opzionale**: col flag `wallet_enabled` a `'0'` l'app non muove denaro
(niente controlli di capienza, addebiti, rimborsi, ricariche, bonus di benvenuto o punti) e
si paga alla cassa. Le vendite però restano registrate: ordini e sessioni banco esistono
come righe proprie, mentre il cesto passa da `User.registra_consumo()` — crea la
`Transaction` di vendita **senza** toccare il saldo — perché `ds_guadagni` conta il cesto
proprio dalle transazioni `Cesto: %`. I saldi esistenti non vengono azzerati: spegnere il
flag li nasconde soltanto. Ogni nuovo punto di pagamento deve gestire entrambe le modalità. `wallet_overdraft` è il rosso massimo consentito per utente e va sempre
sommato al saldo nei controlli di capienza. I parametri economici (punti per euro, soglia
premio, prezzi base builder, bonus registrazione) stanno in `AppSetting`, leggibili con
`get_numeric_setting(key, default)`: non usare le costanti di `config.py`, che sono solo
fallback storici.

### Bot Telegram: bottoni, webhook, collegamento

Il promemoria del pasto aziendale porta due bottoni inline (Sì / No) costruiti da
`tastiera_conferma_pasto()`; `send_telegram_to_user` e `send_reminder_to_user` accettano
`reply_markup`. La risposta torna sul webhook `main.telegram_webhook`, che:

- è **esente da CSRF** (`csrf.exempt` in `create_app()`): Telegram non ha sessione né token;
- si autentica con il segreto nel percorso (`AppSetting('telegram_webhook_secret')`,
  generato all'attivazione e confrontato con `compare_digest`);
- verifica che il `chat.id` del callback sia quello del proprietario della prenotazione,
  altrimenti chiunque potrebbe annullare il pasto di un altro;
- su "No" mette la prenotazione a `cancelled` — è il modo in cui il cliente **blocca la
  produzione** — e avvisa il canale dello staff, perché la cucina sta per prepararlo;
- gestisce anche i messaggi in chat: `/start <chiave>` collega il `telegram_chat_id`,
  accettando **prima** il codice breve (`User.telegram_link_code`, formato `QL-XXXXXX`) e
  poi il token firmato con `SECRET_KEY` dei vecchi deep link; `/id` risponde col chat id,
  ma non è più il percorso consigliato (vedi sotto).

Il webhook va registrato una volta da **Impostazioni → Notifiche → Attiva le risposte**
(`setWebhook`): senza quel passaggio i bottoni compaiono ma la risposta non arriva. Telegram
pretende HTTPS, quindi l'attivazione funziona solo in produzione. Per i metodi diversi da
`sendMessage` c'è `telegram_api(metodo, payload)`.

#### Il cliente si collega col proprio codice, non con l'ID

Chiedere al cliente il proprio "ID Telegram" **non funzionava**: il bot risponde a `/id`
solo se il webhook è registrato, quindi le istruzioni via email cadevano nel vuoto. Il
percorso attuale è `/telegram/collega` (`main.telegram_collega`, più
`telegram_collega_verifica` e `telegram_scollega`), raggiungibile dal profilo e dal pulsante
delle due email:

1. la pagina mostra il codice personale — `codice_collegamento(user)`, alfabeto
   `CARATTERI_CODICE` senza `I`, `O`, `0` e `1` perché va letto e ribattuto — e il deep link
   `link_avvio_bot(user)` che lo precompila;
2. il cliente lo invia al bot;
3. `collega_telegram_da_messaggi(user)` lo cerca in `getUpdates` e salva il `chat_id`.

`getUpdates` e il webhook sono **mutuamente esclusivi**: col webhook attivo Telegram
risponde `409 Conflict`, e la funzione lo traduce in "premi Avvia e riprova", perché in quel
caso il collegamento arriva da sé sul webhook. Chi tocca queste funzioni tenga presente che
devono funzionare in **entrambe** le configurazioni.

#### La prova del canale va in due direzioni

`invia_domanda_prova()` (Impostazioni → Notifiche → *Invia una domanda di prova*) manda sul
canale una **domanda** coi due bottoni, non un semplice "connessione funzionante": è
`leggi_risposta_prova()` a dire se la risposta è tornata, leggendola dall'impostazione se
l'ha registrata il webhook (`registra_risposta_prova()`, ramo `prova:` del callback) o da
`getUpdates` se le risposte non sono attive. È la diagnosi del guasto più insidioso: i
bottoni del promemoria si vedono sempre, ma senza `setWebhook` il "No" del cliente non
annulla nulla e la cucina prepara comunque.

Le chiavi `telegram_prova_codice`, `telegram_prova_risposta` e `telegram_prova_chi` sono di
servizio e stanno **fuori** da `all_keys` di `admin.settings`: quella lista la riscrive
`settings_save`, che le azzererebbe a ogni salvataggio. Lo stato arriva al template come
variabile `prova`.

Quando la risposta non torna, `motivo_mancata_risposta()` e la pagina
`/admin/settings/telegram-diagnostica` (`diagnostica_canale()`) chiedono a **Telegram** che
cosa sta succedendo con `getWebhookInfo`: indirizzo registrato — confrontato con quello di
questa installazione, perché un webhook rimasto su un deploy precedente manda le risposte
altrove — aggiornamenti in coda e `last_error_message`, cioè il motivo per cui la consegna
fallisce. "In attesa di risposta" da solo non distingue "nessuno ha premuto" da "non riesco
a consegnare".

**`import json as _json` sta in testa al modulo, fuori dal `try/except ImportError`.** Era
solo nel ramo di ripiego (quello senza `requests`), quindi in produzione — dove `requests`
c'è — ogni messaggio con `reply_markup` moriva in `NameError` **prima** della chiamata HTTP:
i bottoni dei promemoria non partivano affatto, e i test non lo vedevano perché
sostituivano `send_telegram_to_user`. Quando sostituisci una funzione di invio in un test,
verifica a parte che quella vera sia almeno importabile ed eseguibile.

### Dieta settimanale (`app/dieta.py`)

Il cliente dichiara condizioni e allergie in `/dieta` (`DietProfile`), riceve il fabbisogno
(Mifflin-St Jeor × attività × obiettivo, o le kcal che scrive lui) e un piano dei pranzi
(`DietPlan` + `DietPlanDay`, voci in JSON). Menu, carrello, home e pasto aziendale ne tengono
conto; il backoffice ha `/admin/diete`. Flag `dieta_enabled`, quarto della lista.

- **Un valore nutrizionale mancante è `NULL`, non zero**, e resta tale: `nutrienti()` lo
  segnala come `noto=False`, il compositore scarta il prodotto, il carrello lo conta a parte.
  Il form del backoffice (`_nutrizione_da_form`) salva `NULL` per il campo vuoto: non
  "normalizzare" a 0, altrimenti un piatto senza dati diventa il più leggero del menu.
- `_backfill_nutrizione()` completa **per nome** i prodotti e gli ingredienti del listino di
  partenza con `kcal IS NULL`, a ogni avvio e in due passate (gli ingredienti poke nascono
  dopo la prima). Non tocca ciò che il gestore ha già scritto. È lì che il pane del builder
  riceve l'allergene `glutine`, che il seed non dichiarava: senza, un celiaco vedeva ogni
  panino "adatto".
- Gli allergeni degli ingredienti sono testo libero (`'uova, latte'`, `'frutta a guscio'`):
  passano sempre da `chiavi_allergeni()`, mai confrontati alla lettera.
- Il regime si applica ai flag `is_vegetarian`/`is_vegan`, che hanno default `False`: un
  prodotto del gestore non marcato risulta "non indicato come vegetariano". È voluto (lato
  sicuro) e il messaggio lo dice; la soluzione è compilare la scheda, non ammorbidire il
  controllo.
- Il compositore penalizza il **principale** ripetuto nella settimana (0,35) molto più di
  contorno e frutta (0,08): con lo stesso peso preferiva un pranzo troppo leggero pur di
  variare la frutta. Il caso rompe i pareggi; i test passano `seed=` e `oggi=`.
- **Gusti ≠ esigenze.** `gradimento(oggetto, profilo)` è separata da `compatibilita()`: le
  famiglie non gradite (`NON_GRADITI`: parole cercate in nome/descrizione/categoria più gli
  allergeni che le implicano, es. il pesce da `crostacei`) e i piatti esclusi uno per uno
  (`DietProfile.prodotti_esclusi`, id del listino) escludono dal piano e dalle alternative,
  ma nel menu danno un'etichetta **grigia** e nel carrello una nota "è un gusto, non un
  rischio"; non entrano in `ha_incompatibili`, quindi non chiedono la conferma al checkout.
  Solo gli allergeni esclusi sono rossi e bloccanti: non mescolare i due percorsi.
- Quattro obiettivi (`OBIETTIVI_DIETA`, descrizioni in `OBIETTIVI_DESCRIZIONE`). **Ogni
  deficit è fermato al metabolismo basale** quando è calcolabile: sotto non si scende senza
  un medico, e la spiegazione lo dice. `dimagrimento_forte` (−25%) è "bilanciato" per
  costruzione, non per etichetta: nel compositore la soglia sopra la quota scende dal 25% al
  10% e si penalizzano meno di 25 g di proteine, grassi oltre il 35% delle kcal, l'assenza di
  un contorno, la chiusura che non sia frutta (morbida: lo yogurt resta ammesso) e il dolce
  (forte). Chi aggiunge un obiettivo lo aggiunga alla lista e alle descrizioni, non a un
  secondo elenco nel template.
- L'ordine con un allergene escluso nel carrello richiede `conferma_dieta=1`: è un avviso da
  leggere, non un divieto. Il collegamento giorno→ordine passa da `session['dieta_giorno_id']`.
- L'avviso del lunedì gira nel polling dei promemoria (`_check_diet_weekly`, dopo le 7 di
  Roma) e usa `DietPlan.notificato` contro i doppi invii; accetta `adesso=` per i test.
- Le nuove tabelle hanno FK verso utenti e ordini: `_delete_tenant_data()` in `demo_seed.py`
  le cancella prima di ordini e utenti. Chi aggiunge un modello alla dieta aggiorni anche lì.
- **I valori nutrizionali sono espliciti ovunque si veda un piatto**, anche senza dieta: la
  macro `nutrizione(o, compatto, mostra_regime)` di `templates/_nutrizione.html` (kcal in
  evidenza, P/C/G in grammi, bollino vegetariano/vegano, oppure "valori nutrizionali non
  indicati") va usata in menu, carrello, cesto, pasto aziendale e in ogni nuova vista; il
  listino staff ha la colonna *Valori* (`col_map` 5 = `Product.kcal`). Nei due builder ogni
  ingrediente porta `data-kcal` e il totale delle calorie si aggiorna in JavaScript sommando
  gli elementi selezionati: gli ingredienti senza valore vengono contati come "senza valori",
  non come zero.
- **Disclaimer**: `DISCLAIMER_DIETA` in `models.py` è l'unico testo (nessuna validità medica,
  non sostituisce medico o nutrizionista, nessuna garanzia sulle contaminazioni) ed è in ogni
  template come `disclaimer_dieta`. Compare in testa a `/dieta`, nel pannello del carrello,
  nel menu con dieta attiva, in testa a `/admin/diete`, in coda al piano inviato
  (`testo_piano`) e nei manuali. `dieta_profilo` rifiuta il salvataggio senza
  `presa_atto=1`: la casella è obbligatoria e i test la inviano esplicitamente. Non
  ammorbidirlo e non renderlo opzionale.

### Email ai clienti: due momenti, nessun silenzio

Il cliente riceve **due** email, entrambe con la guida in PDF allegata:
`send_registration_received_email()` appena si registra (da tutti i percorsi, Google
compreso) e `send_account_activated_email()` quando il titolare lo attiva.

Due trappole già capitate, entrambe da tenere presenti se tocchi questi flussi:

- **Chi riprova a iscriversi mentre è in attesa non stava ricevendo nulla**, perché il
  secondo accesso finisce nel ramo "utente esistente" e non è una registrazione. Ora
  `auth.google_callback`, `tenant.google_callback` e `auth.login` (password giusta ma
  account non attivo) rimandano la conferma e portano a `/auth/pending`. Prima, il login
  con password su un account in attesa rispondeva "Credenziali non valide".
- **Un invio fallito era invisibile**: il valore di ritorno di `send_email` veniva ignorato
  e senza Gmail configurata non partiva niente, senza traccia. Ora
  `avvisa_staff_email_non_inviata()` scrive sul canale Telegram destinatario e motivo, e
  dalla lista clienti l'icona a busta (`admin.client_reinvia_email`) rimanda l'email
  mostrando l'esito reale: è lo strumento con cui si diagnostica in dieci secondi.

### PDF dei manuali e allegati email

`send_email(..., allegati=[percorsi])` allega file; gli allegati mancanti vengono ignorati,
perché non devono impedire l'invio. L'email di benvenuto allega
`app/static/docs/guida_cliente.pdf`.

Quel PDF è **versionato**: in produzione non ci sono Word né LibreOffice per convertire un
`.docx` al momento dell'invio. Lo produce `docs/genera_pdf_manuali.py`, che rilegge il
`.docx` con python-docx e lo ricompone con fpdf2 — così il contenuto resta uno solo, quello
del generatore `.docx`. **Dopo aver modificato un manuale, rigenera il `.docx` e poi quel
comando**, altrimenti il PDF allegato resta indietro.

### Reminder: nessuno scheduler

I promemoria (tavoli, ritiro ordini, pasti aziendali) girano in un `@app.before_request` con
time-gate di 60 secondi **per processo** (`_reminder_last_run`). Su Vercel questo dipende dal
traffico e dal riciclo dei worker: non è un cron e non va trattato come tale.

## Note operative

- `tips.txt` contiene URL di produzione e credenziali in chiaro, ed è versionato.
- Il seed crea due superadmin con password hardcoded (`admin@bar.local` / `admin@dsconsulting.it`);
  il `SECRET_KEY` di default in `config.py` è un placeholder da sostituire via env.
- `config.py` fa `.lstrip(BOM)` su ogni variabile d'ambiente: alcune vengono incollate con un
  BOM iniziale dal pannello Vercel.
- Diversi file sorgente iniziano con un BOM UTF-8: preservalo quando riscrivi un file intero.
