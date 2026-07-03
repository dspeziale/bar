#!/usr/bin/env python3
"""Crea gli account di test crew/staff per le postazioni QuickLunch.
Eseguire dalla root del progetto: python docs/create_test_crew.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app, db
from app.models import User, Role, Tenant

app = create_app()

CREW = [
    # (email, username, password, ruolo, postazione, wallet)
    ('banco@bar.local',   'banco_staff',   'Banco2024!',   'cassiere',   'Tablet Banco POS',   50.0),
    ('cucina@bar.local',  'cuoco_mario',   'Cucina2024!',  'cuoco',      'Display Cucina KDS', 10.0),
    ('sala@bar.local',    'staff_sala',    'Sala2024!',    'manager',    'Tablet Staff Sala',  10.0),
    ('cliente1@bar.local','luca_verdi',    'Cliente1!',    'utente',     'Smartphone Cliente', 30.0),
    ('cliente2@bar.local','anna_rossi',    'Cliente2!',    'utente',     'Smartphone Cliente', 15.0),
]

with app.app_context():
    tenant = Tenant.query.filter_by(slug='default').first()
    if not tenant:
        print('[ERRORE] Tenant default non trovato — avvia almeno una volta il server prima.')
        sys.exit(1)

    created = []
    skipped = []

    for email, username, password, role_name, postazione, wallet in CREW:
        existing = User.query.filter_by(email=email).first()
        if existing:
            skipped.append((email, postazione))
            continue

        role = Role.query.filter_by(name=role_name).first()

        # username univoco
        base = username; n = 2
        while User.query.filter_by(username=username).first():
            username = f'{base}{n}'; n += 1

        u = User(
            username=username,
            email=email,
            is_active=True,
            is_client=(role_name == 'utente'),
            wallet_balance=wallet,
            loyalty_points=0,
            tenant_id=tenant.id,
        )
        u.set_password(password)
        if role:
            u.roles.append(role)
        db.session.add(u)
        created.append((email, username, password, role_name, postazione, wallet))

    db.session.commit()

    print()
    print('=' * 62)
    print('  QuickLunch — Account di test creati')
    print('=' * 62)
    print()

    if created:
        # Header
        print(f"  {'POSTAZIONE':<22} {'EMAIL':<22} {'PASSWORD':<14} {'RUOLO'}")
        print(f"  {'-'*22} {'-'*22} {'-'*14} {'-'*12}")
        for email, username, password, role_name, postazione, wallet in created:
            print(f"  {postazione:<22} {email:<22} {password:<14} {role_name}")
        print()
        print('  Account ADMIN già esistente:')
        print(f"  {'PC Admin / Backoffice':<22} {'admin@bar.local':<22} {'admin123':<14} superadmin")

    if skipped:
        print()
        print('  [GIÀ ESISTENTI — non modificati]')
        for email, postazione in skipped:
            print(f"  {postazione:<22} {email}")

    print()
    print('  Wallet clienti di test:')
    for email, username, password, role_name, postazione, wallet in created:
        if role_name == 'utente':
            print(f"  {username:<20} {wallet:.2f}€")
    print()
    print('=' * 62)
    print()
