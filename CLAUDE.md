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
3. `_seed_defaults()` — permessi, ruoli, superadmin, categorie, slot, tavoli, articoli banco,
   impostazioni di default. Ogni blocco è idempotente (`if not X.query.first()` o
   `filter_by(...).first()`).
4. `_backfill_tenant_ids()` — assegna il `tenant_id` a ordini e prenotazioni tavolo legacy.

**Per aggiungere una colonna**: dichiarala nel modello *e* aggiungi un `_ensure(...)` in
`_migrate_tenant_columns()`, altrimenti i database esistenti (produzione compresa) non la
riceveranno mai. Lo stesso vale per nuovi permessi, che vanno aggiunti al blocco
idempotente `extra_perms` e non alla lista iniziale (eseguita solo su DB vuoto).

### Multi-tenancy

Quasi tutte le tabelle hanno `tenant_id` nullable. Il super admin globale ha
`tenant_id = None` e ricade sul tenant di slug `default` tramite due helper gemelli:
`_active_tenant_id()` (admin) e `_effective_tenant_id()` (main).

**Ogni record nuovo che appartiene a un tenant deve ricevere il `tenant_id` esplicitamente
alla creazione**: non esiste un default né un event listener. Le viste del backoffice
filtrano per tenant, quindi un record creato senza `tenant_id` non compare da nessuna parte.

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

### Wallet e fedeltà

Il saldo si muove **solo** attraverso i metodi di `User` (`credit_wallet`, `debit_wallet`,
`add_points`, `redeem_points`): ognuno crea la `Transaction` corrispondente, così lo storico
resta coerente. `wallet_overdraft` è il rosso massimo consentito per utente e va sempre
sommato al saldo nei controlli di capienza. I parametri economici (punti per euro, soglia
premio, prezzi base builder, bonus registrazione) stanno in `AppSetting`, leggibili con
`get_numeric_setting(key, default)`: non usare le costanti di `config.py`, che sono solo
fallback storici.

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
