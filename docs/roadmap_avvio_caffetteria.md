# Roadmap — Avvio QuickLunch in Caffetteria

> Documento operativo per mettere in produzione il sistema dalla prima configurazione
> al primo giorno di servizio completo.

---

## Fase 0 — Prerequisiti tecnici (prima di tutto)

| # | Attività | Note |
|---|----------|------|
| 0.1 | Deploy su Vercel (o server proprio) | Assicurarsi che l'URL sia HTTPS — obbligatorio per fotocamera e OAuth |
| 0.2 | Database PostgreSQL attivo | Vercel Storage, Supabase, Neon, ecc. |
| 0.3 | Variabili d'ambiente impostate | `DATABASE_URL`, `SECRET_KEY`, `TELEGRAM_BOT_TOKEN` (opzionale) |
| 0.4 | Primo avvio: `db.create_all()` eseguito | Accedere all'app una volta — crea tutte le tabelle automaticamente |
| 0.5 | Account superadmin creato | Registrarsi e assegnare il ruolo `superadmin` direttamente sul DB |

---

## Fase 1 — Configurazione base (Giorno 1 — solo admin)

### 1.1 Tenant e identità visiva
- Admin → Impostazioni → **Tenant**
- Impostare: nome caffetteria, colore primario, logo (se supportato)

### 1.2 Categorie prodotti
Creare almeno le categorie base, ad esempio:

| Categoria | Icona suggerita |
|-----------|----------------|
| Panini & Tramezzini | `fa-bread-slice` |
| Insalate | `fa-leaf` |
| Bevande | `fa-mug-hot` |
| Dolci & Snack | `fa-cookie-bite` |
| Menu Fisso | `fa-utensils` |

### 1.3 Catalogo prodotti
Per ogni prodotto inserire:
- Nome, descrizione, prezzo
- Categoria, quantità giornaliera (stock)
- Allergeni (importante per etichette cesto)
- Barcode EAN (solo per prodotti confezionati da scansionare al cesto — lattine, snack)

### 1.4 Slot orari
- Admin → Slot → creare le fasce di ritiro (es: 12:00, 12:30, 13:00, 13:30)
- Impostare il numero massimo di ordini per slot

### 1.5 Ruoli e utenti staff
| Ruolo | Chi | Permessi chiave |
|-------|-----|-----------------|
| `superadmin` | Proprietario / IT | Tutto |
| `manager` | Responsabile caffetteria | Ordini, prodotti, report |
| `cuoco` | Personale cucina | Cesto Cucina, Prenotazioni |
| `cassiere` | Banco | Banco scan, wallet |

---

## Fase 2 — Configurazioni avanzate (Giorni 2-3)

### 2.1 Google OAuth (login social — facoltativo)
- Admin → Impostazioni → **OAuth Google**
- Creare progetto su [console.cloud.google.com](https://console.cloud.google.com)
- Aggiungere URI di callback indicato nella pagina impostazioni
- Incollare `Client ID` e `Client Secret`

### 2.2 Notifiche Telegram (facoltativo ma consigliato)
- Creare bot con @BotFather
- Impostare `TELEGRAM_BOT_TOKEN` nelle variabili d'ambiente
- Utile per notifiche ordini e alert cucina

### 2.3 Wallet e ricariche
- Decidere la politica: ricarica solo da admin, o anche tramite pagamento online
- Impostare eventuale **fido** (saldo negativo consentito) per dipendenti fidati
- Admin → Utenti → selezionare utente → Wallet

### 2.4 Convenzioni aziendali (se applicabile)
- Admin → Convenzioni → creare account aziendali per dipendenti convenzionati
- Utili per pasto aziendale a prezzo fisso

---

## Fase 3 — Onboarding clienti (Settimana 1)

### 3.1 Registrazione clienti
**Opzione A — Autonoma:** il cliente si registra da solo all'URL dell'app
**Opzione B — Assistita:** il cassiere crea l'account e carica il primo credito wallet

### 3.2 Primo credito wallet
- Ogni nuovo cliente deve avere credito per ordinare
- Consigliato: ricarica minima iniziale di 10-20 € come benvenuto
- Il cassiere accede ad Admin → Utenti → seleziona → Ricarica Wallet

### 3.3 Comunicazione ai clienti
Stampare e affiggere (vedi `manuali/device_layout.docx` per layout suggerito):
- QR code dell'URL dell'app con istruzioni di registrazione
- Spiegazione del wallet (si ricarica in cassa o online)
- Istruzioni per ordinare e per il Cesto Cucina

---

## Fase 4 — Operatività giornaliera (Regime normale)

### Mattina (cucina/gestore)
| Orario | Attività |
|--------|----------|
| Apertura | Verificare Admin → **Prenotazioni Cucina** — cosa è stato prenotato per oggi |
| Prima della pausa | Preparare i panini/tramezzini prenotati + il cesto del giorno |
| Durante preparazione | Admin → **Cesto Cucina** → generare etichette QR → stampare → attaccare agli involucri |

### Durante il servizio (banco/cassa)
| Scenario | Come gestirlo |
|----------|---------------|
| Cliente ordina da app | Ordine appare in Admin → Ordini; cliente ritira allo slot scelto |
| Cliente vuole pagare al banco | Cassiere usa **Banco** → genera QR → cliente scansiona con l'app |
| Cliente prende dal cesto autonomamente | Scansiona QR sull'involucro → paga da app |
| Cliente vuole aggiungere una lattina | Sulla pagina di conferma cesto → "Aggiungi bevanda" → scansiona barcode |
| Ricarica wallet | Admin → Utenti → seleziona → Ricarica |

### Fine giornata (gestore)
- Admin → Cesto Cucina → **Cancella tutte** le etichette rimaste (non vendute)
- Verificare gli ordini evasi e quelli pendenti
- Admin → Report → Convenzioni (se applicabile) → scaricare PDF mensile

---

## Fase 5 — Funzionalità avanzate (Mese 2+)

| Funzionalità | Quando attivarla |
|-------------|-----------------|
| **Builder Visuale** (componi panino custom) | Quando il catalogo base è rodato |
| **Prenotazioni future** | Da subito se i clienti chiedono di prenotare in anticipo |
| **Pasto Aziendale / Convenzioni** | Se si hanno aziende clienti con contratto |
| **Sondaggi** (Poll) | Per raccogliere feedback su nuovi prodotti |
| **Prenotazione tavoli** | Se ci sono tavoli con servizio al posto |

---

## Checklist go-live

```
INFRASTRUTTURA
☐ URL HTTPS attivo e raggiungibile
☐ Database connesso e tabelle create
☐ Variabili d'ambiente impostate
☐ Superadmin configurato

CONFIGURAZIONE
☐ Tenant creato con nome caffetteria
☐ Categorie prodotti create
☐ Catalogo prodotti inserito (con allergeni e barcode EAN sulle bevande)
☐ Slot orari configurati
☐ Ruoli staff creati e assegnati

STAFF
☐ Account cuoco creato e testato (vede Cesto Cucina e Prenotazioni)
☐ Account cassiere creato e testato (vede Banco)
☐ Flusso ordine testato end-to-end (ordina → cucina vede → ritiro)
☐ Flusso Banco testato (QR banco → pagamento da app)
☐ Flusso Cesto testato (etichetta stampata → scansione → acquisto)

CLIENTI
☐ QR registrazione affisso in cassa
☐ Istruzioni wallet spiegate allo staff
☐ Test con 2-3 clienti pilota prima dell'apertura ufficiale
```

---

## Contatti e supporto

| Problema | Dove guardare |
|----------|---------------|
| Errore DB | Log Vercel → Functions |
| OAuth non funziona | Admin → Impostazioni → OAuth Google (callback URI corretto?) |
| Cliente non vede ordini | Verificare `tenant_id` dell'utente = tenant attivo |
| Cesto non legge barcode | Verificare che il prodotto abbia il campo **Barcode EAN** compilato |
| Prenotazione non visibile in cucina | Verificare `status != cancelled` e `pickup_date >= oggi` |

---

*Documento generato il 13/07/2026 — QuickLunch v1.x*
