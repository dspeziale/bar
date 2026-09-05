# -*- coding: utf-8 -*-
"""Isolamento dei dati fra tenant.

Ogni richiesta lavora dentro un tenant (`g.tenant_scope`), deciso una volta
sola all'inizio (`risolvi_tenant_richiesta`): quello dell'utente collegato,
quello scelto dall'amministratore dei tenant, quello dell'indirizzo
`/t/<slug>` per chi non e' ancora entrato, altrimenti il tenant predefinito.

Da quel momento due ganci di SQLAlchemy fanno il resto, per tutti i modelli
che hanno una colonna `tenant_id`:

- `do_orm_execute` aggiunge a ogni SELECT/UPDATE/DELETE dell'ORM la
  condizione `tenant_id = <tenant corrente>` (`with_loader_criteria`, anche
  sugli alias e sulle join), cosi' una query scritta senza filtro non puo'
  leggere i dati di un altro tenant e `db.get_or_404` su un id altrui da' 404;
- `before_flush` assegna il tenant corrente a ogni riga nuova che non lo ha,
  cosi' non nascono piu' righe orfane.

Chi deve vedere tutto (backup, guadagni per tenant, gestione dei tenant,
seed) lavora dentro `senza_filtro()`; chi deve lavorare in un tenant preciso
fuori da una richiesta (seed di base, automatismi) usa `con_tenant(id)`.
Con scope `None` non c'e' alcun filtro e nessuna assegnazione automatica.

Gli utenti sono l'unica eccezione al filtro stretto: le righe con
`tenant_id NULL` (solo l'amministratore dei tenant) restano visibili, perche'
il suo record deve potersi ricaricare dentro qualunque tenant.
"""
from contextlib import contextmanager

from flask import g, has_app_context, request, session
from sqlalchemy import event
from sqlalchemy.orm import Session, with_loader_criteria

from app import db

_MODELLI = []


def tenant_corrente():
    """L'id del tenant in cui si sta lavorando, o None (nessun filtro)."""
    if not has_app_context():
        return None
    return getattr(g, 'tenant_scope', None)


def imposta_tenant(tid):
    g.tenant_scope = tid


@contextmanager
def con_tenant(tid):
    """Esegue il blocco dentro il tenant `tid` (None = nessun filtro)."""
    precedente = tenant_corrente()
    g.tenant_scope = tid
    try:
        yield
    finally:
        g.tenant_scope = precedente


@contextmanager
def senza_filtro():
    """Esegue il blocco vedendo tutti i tenant: solo per l'amministratore dei
    tenant e per le procedure di sistema (backup, seed, guadagni)."""
    with con_tenant(None):
        yield


def tenant_predefinito():
    """Il tenant di ripiego: slug 'default', altrimenti il primo creato."""
    from app.models import Tenant
    with senza_filtro():
        t = Tenant.query.filter_by(slug='default').first()
        if t is None:
            t = Tenant.query.order_by(Tenant.id).first()
    return t


def modelli_con_tenant():
    """Le classi mappate che hanno la colonna tenant_id (calcolate una volta)."""
    if not _MODELLI:
        for mapper in db.Model.registry.mappers:
            if 'tenant_id' in mapper.columns:
                _MODELLI.append(mapper.class_)
    return _MODELLI


def utente_globale(**filtri):
    """Un utente cercato in tutti i tenant: email e username sono unici a
    livello di installazione, quindi login, registrazione e controlli di
    duplicato non possono fermarsi al tenant corrente."""
    from app.models import User
    with senza_filtro():
        return User.query.filter_by(**filtri).first()


def _criterio(cls, tid):
    from app.models import User
    if cls is User:
        return lambda c: db.or_(c.tenant_id == tid, c.tenant_id.is_(None))
    return lambda c: c.tenant_id == tid


@event.listens_for(Session, 'do_orm_execute')
def _filtro_tenant(stato):
    if not (stato.is_select or stato.is_update or stato.is_delete):
        return
    # Ricaricare gli attributi di un oggetto gia' in sessione o seguire una
    # relazione parte da una riga che e' gia' del tenant: qui il filtro non
    # serve e potrebbe solo nascondere il record a meta' strada.
    if stato.is_column_load or stato.is_relationship_load:
        return
    tid = tenant_corrente()
    if tid is None:
        return
    stato.statement = stato.statement.options(*[
        with_loader_criteria(cls, _criterio(cls, tid), include_aliases=True,
                             propagate_to_loaders=False)
        for cls in modelli_con_tenant()])


def _genitori():
    """Per le tabelle figlie il tenant e' quello del genitore: si usa quando
    non c'e' uno scope (riga di comando, test, procedure di sistema)."""
    from app.models import (Transaction, PushSubscription, DailyStock, ConsumableMovement,
                            CorporateMembership, CorporateMealBooking, User, Product,
                            ConsumableItem, CorporateAccount, DailyFixedMeal, DietPlan,
                            DietProfile, DietReferto, Comunicazione, Order, TableReservation,
                            BancoSession, Prenotazione)
    return {
        Transaction: ('user_id', User), PushSubscription: ('user_id', User),
        DailyStock: ('product_id', Product), ConsumableMovement: ('item_id', ConsumableItem),
        CorporateMembership: ('corporate_id', CorporateAccount),
        CorporateMealBooking: ('meal_id', DailyFixedMeal), DietPlan: ('user_id', User),
        DietProfile: ('user_id', User), DietReferto: ('user_id', User),
        Comunicazione: ('creata_da', User), Order: ('user_id', User),
        TableReservation: ('user_id', User), BancoSession: ('staff_id', User),
        Prenotazione: ('user_id', User),
    }


@event.listens_for(Session, 'before_flush')
def _assegna_tenant(sessione, _ctx, _istanze):
    tid = tenant_corrente()
    from app.models import User
    classi = set(modelli_con_tenant())
    genitori = _genitori()
    with sessione.no_autoflush:
        for obj in sessione.new:
            if type(obj) not in classi or getattr(obj, 'tenant_id', None) is not None:
                continue
            if isinstance(obj, User) and getattr(obj, 'is_superadmin', False):
                continue
            if tid is not None:
                obj.tenant_id = tid
                continue
            # Nessuno scope: il figlio eredita il tenant del genitore, se c'e'.
            padre = genitori.get(type(obj))
            if padre is None:
                continue
            fk, classe = padre
            pid = getattr(obj, fk, None)
            if pid is None:
                continue
            gen = sessione.get(classe, pid)
            if gen is not None and getattr(gen, 'tenant_id', None) is not None:
                obj.tenant_id = gen.tenant_id


def risolvi_tenant_richiesta():
    """Decide il tenant della richiesta e lo mette in g.tenant_scope.

    Gira in before_request. Durante la risoluzione lo scope e' None, cosi'
    il caricamento dell'utente collegato (che e' una query) non viene filtrato.
    """
    if request.endpoint == 'static':
        return
    g.tenant_scope = None
    from flask_login import current_user
    from app.models import Tenant

    tid = None
    try:
        autenticato = current_user.is_authenticated
    except Exception:
        autenticato = False
    if autenticato:
        if getattr(current_user, 'is_superadmin', False):
            tid = session.get('tenant_attivo')
            if tid is not None and db.session.get(Tenant, tid) is None:
                tid = None
                session.pop('tenant_attivo', None)
        else:
            tid = current_user.tenant_id
    if tid is None and request.blueprint == 'tenant':
        slug = (request.view_args or {}).get('slug')
        if slug:
            t = Tenant.query.filter_by(slug=slug).first()
            if t is not None:
                tid = t.id
    if tid is None:
        t = tenant_predefinito()
        tid = t.id if t is not None else None
    g.tenant_scope = tid
