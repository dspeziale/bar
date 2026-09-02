# -*- coding: utf-8 -*-
"""Catalogo delle stampe di QuickLunch, in un unico PDF.

Raccoglie tutte le stampe che l'applicazione produce verso i clienti, il
gestore/la cucina e le aziende convenzionate, ognuna preceduta da una scheda
(chi la riceve, quando si produce, da dove si stampa, su che carta):

- le stampe HTML (tagliando ordine, locandina QR, etichette del cesto,
  registro presenze) sono riprodotte come facsimile fedele al template;
- i PDF veri e propri (report giornaliero, riepilogo mensile, brochure di
  presentazione, transazioni DS Consulting) vengono generati DALL'APP con dati
  di esempio su un database temporaneo e uniti al catalogo pagina per pagina:
  quello che si vede e' l'output reale.

Uso (dalla radice del repo, con un Python che veda l'app):
    python docs/generate_catalogo_stampe.py

Dipendenze oltre a requirements.txt: pypdf (per unire i PDF reali);
qrcode e' facoltativo (senza, i QR dei facsimile diventano segnaposto).
Output: docs/manuali/catalogo_stampe.pdf
"""
import os
import sys
import tempfile
from datetime import date, datetime
from io import BytesIO

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'docs', 'manuali', 'catalogo_stampe.pdf')
FONT_DIR = os.path.join(ROOT, 'app', 'static', 'fonts')

os.environ['DATABASE_URL'] = 'sqlite:///' + os.path.join(
    tempfile.mkdtemp(), 'catalogo.db').replace(os.sep, '/')
os.environ.setdefault('SECRET_KEY', 'catalogo-stampe-chiave-di-servizio!!')
os.chdir(ROOT)
sys.path.insert(0, ROOT)

from fpdf import FPDF                                                   # noqa: E402
from pypdf import PdfReader, PdfWriter                                  # noqa: E402

# ── Palette del kit documentale ──────────────────────────────────────────────
RED = (233, 69, 96)
NAVY = (15, 52, 96)
DARK = (26, 26, 46)
DGRAY = (80, 80, 95)
LGRAY = (200, 200, 210)
VLIGHT = (248, 248, 252)
WHITE = (255, 255, 255)
FONT = 'PTSansNarrow'

MESE_DEMO = (2026, 4)          # aprile 2026: il mese dei dati di esempio
BAR = 'Bar Centrale'


# ═════════════════════════════════════════════════════════════════════════════
# 1. Dati di esempio e PDF reali generati dall'app
# ═════════════════════════════════════════════════════════════════════════════
def prepara_dati():
    """DB temporaneo con un mese di attivita' plausibile per Acme SpA."""
    from app import create_app, db
    from app.models import (User, Tenant, Category, Product, TimeSlot,
                            Order, OrderItem, BancoSession, Transaction,
                            CorporateAccount, CorporateMembership,
                            DailyFixedMeal, CorporateMealBooking, AppSetting)

    app = create_app()
    anno, mese = MESE_DEMO
    with app.app_context():
        tid = Tenant.query.filter_by(slug='default').first().id
        for chiave, valore in [('company_name', BAR),
                               ('company_address', 'Via Roma 12'),
                               ('company_city', '20100 Milano (MI)'),
                               ('company_vat', 'IT01234567890'),
                               ('platform_fee_percentage', '3.5'),
                               ('tenant_monthly_fee', '40')]:
            riga = AppSetting.query.filter_by(key=chiave).first()
            if riga:
                riga.value = valore
            else:
                db.session.add(AppSetting(key=chiave, value=valore))

        slot = TimeSlot(time_str='12:30', max_orders=99, is_active=True,
                        tenant_id=tid)
        db.session.add(slot)
        cat = Category(name='Panini', tenant_id=tid)
        db.session.add(cat)
        db.session.flush()
        prod = Product(name='Panino Crudo e Squacquerone', price=5.50,
                       category_id=cat.id, daily_quantity=20, is_active=True,
                       tenant_id=tid)
        db.session.add(prod)

        corp = CorporateAccount(name='Acme SpA', daily_price=7.50,
                                max_daily_covers=60, is_active=True,
                                tenant_id=tid)
        db.session.add(corp)
        db.session.flush()

        dipendenti = []
        for cog, nom in [('Rossi', 'Mario'), ('Bianchi', 'Lucia'),
                         ('Verdi', 'Anna'), ('Neri', 'Paolo')]:
            u = User(username=nom.lower(), email='%s@acme.local' % nom.lower(),
                     first_name=nom, last_name=cog, is_client=True,
                     is_active=True, wallet_balance=100.0, tenant_id=tid)
            u.set_password('x')
            db.session.add(u)
            db.session.flush()
            db.session.add(CorporateMembership(user_id=u.id,
                                               corporate_id=corp.id,
                                               is_active=True))
            dipendenti.append(u)

        # Otto giornate lavorative di aprile, presenze a scalare
        giorni = [date(anno, mese, g) for g in (1, 2, 3, 6, 7, 8, 9, 10)]
        for i, g in enumerate(giorni):
            meal = DailyFixedMeal(meal_date=g, price=7.50, max_bookings=60,
                                  name='Menu del %s' % g.strftime('%d/%m'),
                                  corporate_id=corp.id, is_active=True,
                                  tenant_id=tid)
            db.session.add(meal)
            db.session.flush()
            for u in dipendenti[:4 - (i % 3)]:
                db.session.add(CorporateMealBooking(
                    user_id=u.id, meal_id=meal.id, slot_id=slot.id,
                    quantity=1, status='consumed'))

        # Ordini, banco e cesto per il PDF delle transazioni
        u0 = dipendenti[0]
        for i, g in enumerate(giorni[:5]):
            ora = datetime(anno, mese, g.day, 12, 10)
            o = Order(user_id=u0.id, slot_id=slot.id, order_date=g,
                      status='completed', total_price=11.00, tenant_id=tid,
                      order_code='QL-%d-%04d' % (anno, 400 + i),
                      created_at=ora)
            db.session.add(o)
            db.session.flush()
            db.session.add(OrderItem(order_id=o.id, product_id=prod.id,
                                     quantity=2, unit_price=5.50))
            db.session.add(BancoSession(
                token='CAT%09d' % i, staff_id=u0.id, customer_id=u0.id,
                items_json='[]', total=2.40, status='paid', created_at=ora,
                expires_at=ora, tenant_id=tid))
            db.session.add(Transaction(
                user_id=u0.id, amount=-3.20, ttype='payment',
                description='Cesto: Tramezzino Tonno', created_at=ora))
        db.session.commit()
        cid = corp.id
    return app, cid


def scarica_pdf_reali(app, cid):
    """Scarica dall'app, da superadmin, i quattro PDF con i dati di esempio."""
    import re
    anno, mese = MESE_DEMO
    c = app.test_client()
    pagina = c.get('/auth/login').data
    token = re.search(rb'name="csrf_token" value="([A-Za-z0-9._-]+)"',
                      pagina).group(1).decode()
    c.post('/auth/login', data={'email': 'admin@bar.local',
                                'password': 'admin123', 'csrf_token': token})

    rotte = {
        'giornaliero': '/admin/convenzioni/%d/report-pdf?d=%d-%02d-01'
                       % (cid, anno, mese),
        'mensile': '/admin/convenzioni/%d/report-mensile-pdf?m=%d-%02d'
                   % (cid, anno, mese),
        'brochure': '/admin/convenzioni/presentazione-pdf',
        'transazioni': '/admin/superadmin/guadagni/scontrini/pdf'
                       '?year=%d&month=%d' % (anno, mese),
    }
    reali = {}
    for nome, url in rotte.items():
        r = c.get(url)
        assert r.status_code == 200 and r.data[:5] == b'%PDF-', \
            'PDF %s non generato (%d da %s)' % (nome, r.status_code, url)
        reali[nome] = r.data
        print('  scaricato %-12s %6d byte  %s' % (nome, len(r.data), url))
    return reali


# ═════════════════════════════════════════════════════════════════════════════
# 2. Impianto grafico del catalogo
# ═════════════════════════════════════════════════════════════════════════════
class Catalogo(FPDF):
    """Pagine disegnate del catalogo; niente numeri di pagina, perche' le
    pagine unite dai PDF reali hanno gia' i loro pie' di pagina."""

    def footer(self):
        if self.page_no() == 1:
            return
        self.set_y(-12)
        self.set_font(FONT, '', 8)
        self.set_text_color(*DGRAY)
        self.cell(0, 5, 'Catalogo delle stampe QuickLunch — '
                        '© 2024–26 DS Consulting', align='C')


def qr_immagine(testo, lato_px=270):
    """PNG in memoria di un QR reale; None se la libreria manca."""
    try:
        import qrcode
    except ImportError:
        return None
    qr = qrcode.QRCode(border=1, box_size=8)
    qr.add_data(testo)
    qr.make(fit=True)
    img = qr.make_image(fill_color='black', back_color='white')
    buf = BytesIO()
    img.resize((lato_px, lato_px)).save(buf, format='PNG')
    buf.seek(0)
    return buf


def disegna_qr(pdf, x, y, lato, testo):
    """QR vero se possibile, altrimenti un segnaposto riconoscibile."""
    buf = qr_immagine(testo)
    if buf is not None:
        pdf.image(buf, x=x, y=y, w=lato, h=lato)
        return
    pdf.set_draw_color(*DARK)
    pdf.set_line_width(0.4)
    pdf.rect(x, y, lato, lato)
    for fx, fy in ((0, 0), (lato * 0.68, 0), (0, lato * 0.68)):
        pdf.rect(x + fx + lato * 0.06, y + fy + lato * 0.06,
                 lato * 0.26, lato * 0.26)
    pdf.set_font(FONT, '', 6)
    pdf.set_xy(x, y + lato / 2 - 2)
    pdf.cell(lato, 4, 'QR', align='C')


def intestazione_sezione(pdf, numero, titolo, sottotitolo):
    pdf.add_page()
    pdf.set_fill_color(*NAVY)
    pdf.rect(0, 0, 210, 42, 'F')
    pdf.set_fill_color(*RED)
    pdf.rect(0, 42, 210, 2.2, 'F')
    pdf.set_text_color(*WHITE)
    pdf.set_font(FONT, 'B', 11)
    pdf.set_xy(14, 9)
    pdf.cell(0, 6, 'SEZIONE %d' % numero)
    pdf.set_font(FONT, 'B', 24)
    pdf.set_xy(14, 16)
    pdf.cell(0, 11, titolo)
    pdf.set_font(FONT, '', 12)
    pdf.set_xy(14, 28)
    pdf.cell(0, 7, sottotitolo)
    pdf.set_y(54)


def scheda(pdf, num, titolo, righe, descrizione, origine):
    """La carta d'identita' di una stampa: chi, quando, da dove, come."""
    pdf.set_x(14)
    pdf.set_fill_color(*RED)
    pdf.set_text_color(*WHITE)
    pdf.set_font(FONT, 'B', 13)
    pdf.cell(11, 9, str(num), align='C', fill=True)
    pdf.set_fill_color(*DARK)
    pdf.cell(171, 9, '  ' + titolo, fill=True)
    pdf.ln(9)

    pdf.set_draw_color(*LGRAY)
    pdf.set_line_width(0.25)
    for etichetta, valore in righe:
        pdf.set_x(14)
        pdf.set_fill_color(*VLIGHT)
        pdf.set_text_color(*NAVY)
        pdf.set_font(FONT, 'B', 10)
        pdf.cell(38, 7.5, '  ' + etichetta, border=1, fill=True)
        pdf.set_text_color(*DARK)
        pdf.set_font(FONT, '', 10)
        pdf.multi_cell(144, 7.5, ' ' + valore, border=1)
    pdf.ln(2.5)

    pdf.set_x(14)
    pdf.set_text_color(*DGRAY)
    pdf.set_font(FONT, '', 10.5)
    pdf.multi_cell(182, 5.2, descrizione)
    pdf.ln(1.5)

    pdf.set_x(14)
    pdf.set_fill_color(255, 243, 231)
    pdf.set_text_color(150, 84, 15)
    pdf.set_font(FONT, 'B', 9.5)
    pdf.multi_cell(182, 6.5, '  ' + origine, fill=True)
    pdf.ln(4)


# ═════════════════════════════════════════════════════════════════════════════
# 3. Facsimile delle stampe HTML
# ═════════════════════════════════════════════════════════════════════════════
def _mono(pdf, stile='', dim=9):
    """Courier New di sistema se c'e' (serve per il simbolo €), Courier core
    con 'EUR' come ripiego."""
    pdf.set_font('CourierUni' if pdf._mono_unicode else 'Courier', stile, dim)


def _eur_mono(pdf, valore):
    testo = ('%0.2f' % valore).replace('.', ',')
    return testo + ('€' if pdf._mono_unicode else ' EUR')


def facsimile_tagliando(pdf):
    """Il tagliando ordine come esce dalla termica 80 mm (order_slip.html)."""
    X, W = 65, 80          # il rotolo da 80 mm, al centro della pagina
    pdf.set_fill_color(*WHITE)
    pdf.set_draw_color(*LGRAY)
    pdf.set_line_width(0.3)
    pdf.rect(X, pdf.get_y(), W, 132, 'DF')
    pdf.set_y(pdf.get_y() + 5)

    def riga(testo, stile='', dim=9, align='L', avanza=4.2):
        _mono(pdf, stile, dim)
        pdf.set_text_color(0, 0, 0)
        pdf.set_x(X + 4)
        pdf.cell(W - 8, avanza, testo, align=align)
        pdf.ln(avanza)

    def separatore(tratteggio=False):
        y = pdf.get_y() + 1
        pdf.set_draw_color(85, 85, 85) if tratteggio else pdf.set_draw_color(0, 0, 0)
        pdf.set_line_width(0.25 if tratteggio else 0.55)
        if tratteggio:
            pdf.set_dash_pattern(dash=1.2, gap=1.2)
        pdf.line(X + 4, y, X + W - 4, y)
        pdf.set_dash_pattern()
        pdf.set_y(y + 1.6)

    def voce(sx, dx, stile='', dim=9):
        _mono(pdf, stile, dim)
        pdf.set_text_color(0, 0, 0)
        pdf.set_x(X + 4)
        pdf.cell((W - 8) * 0.62, 4.2, sx)
        pdf.cell((W - 8) * 0.38, 4.2, dx, align='R')
        pdf.ln(4.2)

    riga('QuickLunch UFFICIO', 'B', 12, 'C', 5.5)
    riga('Bar Self-Service Ristoro', '', 7, 'C', 3.6)
    separatore()
    riga('QL-2026-0412', 'B', 14, 'C', 7)
    separatore()
    voce('Data:', '15/04/2026')
    voce('Utente:', 'mario')
    voce('Orario ritiro:', '12:30', 'B', 10)
    voce('Note:', 'senza cipolla')
    separatore(True)
    riga('ARTICOLI', 'B', 7, 'L', 4)
    voce('2x Panino Crudo e Squacq.', _eur_mono(pdf, 11.00))
    voce('1x Acqua Naturale 50cl', _eur_mono(pdf, 1.00))
    pdf.ln(1)
    voce('PANINO CUSTOM', _eur_mono(pdf, 6.20), 'B')
    for ing in ('- Ciabatta', '- Prosciutto cotto',
                '- Brie +0,50' + ('€' if pdf._mono_unicode else ' EUR')):
        riga('  ' + ing, '', 7.5, 'L', 3.6)
    separatore()
    voce('TOTALE', _eur_mono(pdf, 18.20), 'B', 12)
    separatore()
    riga('Buon appetito!', '', 7, 'C', 3.6)
    riga('Stampato: 15/04/2026 12:11', '', 7, 'C', 3.6)


def facsimile_locandina(pdf):
    """La locandina con il QR di registrazione (registration_qr.html)."""
    X, W, y0 = 55, 100, pdf.get_y()
    pdf.set_fill_color(*WHITE)
    pdf.set_draw_color(*LGRAY)
    pdf.set_line_width(0.35)
    pdf.rect(X, y0, W, 128, 'DF')

    pdf.set_y(y0 + 8)
    pdf.set_text_color(*RED)
    pdf.set_font(FONT, 'B', 19)
    pdf.set_x(X)
    pdf.cell(W, 9, BAR, align='C')
    pdf.ln(9)
    pdf.set_text_color(*DGRAY)
    pdf.set_font(FONT, '', 10.5)
    pdf.set_x(X)
    pdf.cell(W, 6, 'Scansiona per registrarti come cliente', align='C')
    pdf.ln(9)

    lato = 52
    disegna_qr(pdf, X + (W - lato) / 2, pdf.get_y(), lato,
               'https://quicklunch.example/t/default/join')
    pdf.set_y(pdf.get_y() + lato + 3)
    pdf.set_font(FONT, '', 7.5)
    pdf.set_text_color(150, 150, 150)
    pdf.set_x(X)
    pdf.cell(W, 4, 'https://quicklunch.example/t/default/join', align='C')
    pdf.ln(7)

    pdf.set_fill_color(*VLIGHT)
    pdf.rect(X + 8, pdf.get_y(), W - 16, 32, 'F')
    pdf.set_y(pdf.get_y() + 2.5)
    pdf.set_x(X + 12)
    pdf.set_text_color(*DARK)
    pdf.set_font(FONT, 'B', 9.5)
    pdf.cell(0, 5, 'Come registrarsi:')
    pdf.ln(5.5)
    pdf.set_font(FONT, '', 9.5)
    for i, passo in enumerate([
            'Inquadra il QR con la fotocamera del telefono',
            'Scegli "Registrati con Email" o continua con Google',
            'Compila nome, cognome e password',
            "Attendi l'approvazione dell'amministratore"], 1):
        pdf.set_x(X + 12)
        pdf.cell(0, 5.5, '%d.  %s' % (i, passo))
        pdf.ln(5.5)


def facsimile_etichette(pdf):
    """Il foglio A4 con le etichette QR del cesto (cesto_stampa.html)."""
    LW, LH, GAP = 58, 42, 5
    x0 = (210 - 3 * LW - 2 * GAP) / 2
    y0 = pdf.get_y()
    campioni = [('Tramezzino Tonno e Carciofini', 3.20, ['GLUTINE', 'PESCE'],
                 'CES-4F7A2B'),
                ('Panino Crudo e Squacquerone', 5.50, ['GLUTINE', 'LATTE'],
                 'CES-9C31E8'),
                ('Focaccia Farcita Vegetariana', 4.80, [], 'CES-D204B7')]
    for r in range(2):
        for c in range(3):
            nome, prezzo, allergeni, codice = campioni[(r * 3 + c) % 3]
            x, y = x0 + c * (LW + GAP), y0 + r * (LH + GAP)
            pdf.set_draw_color(68, 68, 68)
            pdf.set_line_width(0.4)
            pdf.set_fill_color(*WHITE)
            pdf.rect(x, y, LW, LH, 'DF')
            pdf.set_fill_color(*RED)
            pdf.rect(x, y, LW, 5, 'F')
            pdf.set_text_color(*WHITE)
            pdf.set_font(FONT, 'B', 8)
            pdf.set_xy(x, y + 0.6)
            pdf.cell(LW, 4, BAR.upper(), align='C')

            corpo_w = LW - (6 if allergeni else 4)
            disegna_qr(pdf, x + (corpo_w - 17) / 2, y + 7, 17,
                       'https://quicklunch.example/cesto/' + codice)
            pdf.set_xy(x + 2, y + 25)
            pdf.set_text_color(*DARK)
            pdf.set_font(FONT, 'B', 8)
            pdf.cell(corpo_w - 4, 3.6, nome[:34], align='C')
            pdf.set_xy(x + 2, y + 29)
            pdf.set_text_color(*RED)
            pdf.set_font(FONT, 'B', 11)
            pdf.cell(corpo_w - 4, 5, ('%0.2f' % prezzo).replace('.', ',') + ' €',
                     align='C')

            if allergeni:
                pdf.set_draw_color(*LGRAY)
                pdf.set_line_width(0.2)
                pdf.line(x + LW - 6, y + 5, x + LW - 6, y + LH - 6)
                pdf.set_font(FONT, 'B', 5)
                pdf.set_text_color(60, 60, 60)
                with pdf.rotation(90, x + LW - 3, y + LH / 2 + 3):
                    pdf.set_xy(x + LW - 3 - 10, y + LH / 2)
                    pdf.cell(20, 3, ' / '.join(allergeni), align='C')

            pdf.set_draw_color(*LGRAY)
            pdf.set_dash_pattern(dash=1, gap=1)
            pdf.line(x, y + LH - 6, x + LW, y + LH - 6)
            pdf.set_dash_pattern()
            pdf.set_xy(x + 2, y + LH - 5)
            pdf.set_font('Courier', '', 6.5)
            pdf.set_text_color(70, 70, 70)
            pdf.cell(24, 4, codice)
            pdf.set_font(FONT, 'B', 7.5)
            pdf.set_text_color(*DARK)
            pdf.cell(LW - 28, 4, '15/04/2026   08:45', align='R')
    pdf.set_y(y0 + 2 * (LH + GAP) + 3)
    pdf.set_x(14)
    pdf.set_font(FONT, '', 9)
    pdf.set_text_color(*DGRAY)
    pdf.multi_cell(182, 4.8, 'Il foglio reale contiene un\'etichetta per ogni '
                             'pezzo del lotto generato (griglia di 3 colonne, '
                             'quante righe servono). Data e ora sono '
                             'disattivabili prima della stampa.')


def facsimile_presenze(pdf):
    """Il registro presenze come esce dalla stampa della pagina
    (convenzione_presenze.html con il CSS @media print)."""
    pdf.set_x(14)
    pdf.set_text_color(*DARK)
    pdf.set_font(FONT, 'B', 13)
    pdf.cell(0, 7, 'Presenze aziendali — Acme SpA')
    pdf.ln(7)
    pdf.set_x(14)
    pdf.set_font(FONT, '', 11)
    pdf.set_text_color(*DGRAY)
    pdf.cell(0, 6, 'aprile 2026')
    pdf.ln(9)

    valori = [('Pasti serviti', '24', (39, 174, 96)),
              ('Giorni con menù', '8', (0, 123, 255)),
              ('Fatturato mese', '180,00€', (255, 193, 7)),
              ('Azienda', 'Acme SpA', (23, 162, 184))]
    bw = 44
    for i, (lbl, val, colore) in enumerate(valori):
        x = 14 + i * (bw + 2)
        pdf.set_fill_color(*colore)
        pdf.rect(x, pdf.get_y(), bw, 15, 'F')
        pdf.set_text_color(*WHITE)
        pdf.set_xy(x + 2, pdf.get_y() + 1.5)
        pdf.set_font(FONT, '', 8)
        pdf.cell(bw - 4, 4, lbl)
        pdf.set_xy(x + 2, pdf.get_y() + 5.5)
        pdf.set_font(FONT, 'B', 12)
        pdf.cell(bw - 4, 6, val)
        pdf.set_y(pdf.get_y() - 7)
    pdf.ln(20)

    giorni = [('Mercoledì 1 aprile', 'Menu del 01/04',
               [('Rossi Mario', '12:30'), ('Bianchi Lucia', '12:30'),
                ('Verdi Anna', '13:00'), ('Neri Paolo', '13:00')]),
              ('Giovedì 2 aprile', 'Menu del 02/04',
               [('Rossi Mario', '12:30'), ('Bianchi Lucia', '13:00'),
                ('Verdi Anna', '13:00')])]
    for titolo_g, menu, persone in giorni:
        pdf.set_x(14)
        pdf.set_draw_color(*LGRAY)
        pdf.set_line_width(0.3)
        y0 = pdf.get_y()
        h = 14 + len(persone) * 6 + 7
        pdf.rect(14, y0, 182, h)
        pdf.set_fill_color(*VLIGHT)
        pdf.rect(14, y0, 182, 7, 'F')
        pdf.set_xy(16, y0 + 1)
        pdf.set_text_color(*DARK)
        pdf.set_font(FONT, 'B', 10)
        pdf.cell(90, 5, titolo_g + '   ')
        pdf.set_font(FONT, '', 9.5)
        pdf.set_text_color(*DGRAY)
        pdf.cell(50, 5, menu)
        pdf.set_font(FONT, 'B', 9.5)
        pdf.set_text_color(39, 174, 96)
        pdf.cell(38, 5, '%d consumati' % len(persone), align='R')
        pdf.set_y(y0 + 8)
        pdf.set_x(16)
        pdf.set_font(FONT, 'B', 8.5)
        pdf.set_text_color(*DGRAY)
        pdf.cell(10, 5, '#')
        pdf.cell(110, 5, 'DIPENDENTE')
        pdf.cell(30, 5, 'SLOT')
        pdf.ln(5.4)
        pdf.set_font(FONT, '', 9.5)
        pdf.set_text_color(*DARK)
        for i, (nome, slot) in enumerate(persone, 1):
            pdf.set_x(16)
            pdf.cell(10, 5.6, str(i))
            pdf.cell(110, 5.6, nome)
            pdf.cell(30, 5.6, slot)
            pdf.ln(5.6)
        pdf.set_x(16)
        pdf.set_font(FONT, '', 9)
        pdf.set_text_color(*DGRAY)
        pdf.cell(0, 6, 'Totale fatturabile: %s€  (%d × 7,50€)'
                 % (('%0.2f' % (len(persone) * 7.5)).replace('.', ','),
                    len(persone)))
        pdf.set_y(y0 + h + 4)
    pdf.set_x(14)
    pdf.set_font(FONT, '', 9)
    pdf.set_text_color(*DGRAY)
    pdf.multi_cell(182, 4.8, 'Il registro reale elenca tutti i giorni del '
                             'mese con menù, uno sotto l\'altro, con anche i '
                             'prenotati non ancora segnati e gli annullati.')


# ═════════════════════════════════════════════════════════════════════════════
# 4. Montaggio del catalogo
# ═════════════════════════════════════════════════════════════════════════════
def costruisci(reali):
    pdf = Catalogo(format='A4')
    pdf.add_font(FONT, '', os.path.join(FONT_DIR, 'PTSansNarrow-Regular.ttf'))
    pdf.add_font(FONT, 'B', os.path.join(FONT_DIR, 'PTSansNarrow-Bold.ttf'))
    cour = r'C:\Windows\Fonts\cour.ttf'
    pdf._mono_unicode = os.path.isfile(cour)
    if pdf._mono_unicode:
        pdf.add_font('CourierUni', '', cour)
        pdf.add_font('CourierUni', 'B', r'C:\Windows\Fonts\courbd.ttf')
    pdf.set_auto_page_break(True, margin=16)
    inserzioni = []          # (dopo_pagina, nome del PDF reale da unire)

    # ── Copertina ────────────────────────────────────────────────────────────
    pdf.add_page()
    pdf.set_fill_color(*NAVY)
    pdf.rect(0, 0, 210, 297, 'F')
    pdf.set_fill_color(*RED)
    pdf.rect(0, 96, 210, 3, 'F')
    pdf.set_text_color(*WHITE)
    pdf.set_font(FONT, 'B', 15)
    pdf.set_xy(20, 62)
    pdf.cell(0, 8, 'QUICKLUNCH')
    pdf.set_font(FONT, 'B', 34)
    pdf.set_xy(20, 72)
    pdf.cell(0, 16, 'Catalogo delle stampe')
    pdf.set_font(FONT, '', 14)
    pdf.set_xy(20, 106)
    pdf.multi_cell(170, 7.5,
                   'Tutte le stampe che l\'applicazione produce verso i '
                   'clienti, il gestore e le aziende convenzionate: per '
                   'ognuna la scheda (chi la riceve, quando, da dove si '
                   'stampa, su che carta) e un esempio completo.')
    pdf.set_xy(20, 262)
    pdf.set_font(FONT, '', 11)
    pdf.cell(0, 6, '© 2024–26 DS Consulting')

    # ── Come leggere il catalogo + indice ────────────────────────────────────
    pdf.add_page()
    pdf.set_y(20)
    pdf.set_x(14)
    pdf.set_text_color(*NAVY)
    pdf.set_font(FONT, 'B', 18)
    pdf.cell(0, 9, 'Come leggere il catalogo')
    pdf.ln(11)
    pdf.set_x(14)
    pdf.set_text_color(*DARK)
    pdf.set_font(FONT, '', 11)
    pdf.multi_cell(182, 5.8,
                   'Ogni stampa ha una scheda con il destinatario, il momento '
                   'in cui si produce, il punto dell\'applicazione da cui si '
                   'stampa e il tipo di carta. Subito dopo la scheda c\'è '
                   'l\'esempio:\n'
                   '•  per le stampe di pagina (tagliando, locandina QR, '
                   'etichette del cesto, registro presenze) è un facsimile '
                   'fedele al risultato di stampa;\n'
                   '•  per i documenti PDF è l\'output reale generato '
                   'dall\'applicazione con i dati di esempio del catalogo '
                   '(il bar "Bar Centrale" e l\'azienda convenzionata '
                   '"Acme SpA", aprile 2026).\n\n'
                   'Ricorda la regola fissa del servizio: a ogni prodotto '
                   'preparato vanno allegati il tagliando ordine di '
                   'QuickLunch e lo scontrino del registratore di cassa, che '
                   'è un apparecchio fiscale separato e non viene stampato '
                   'da QuickLunch (per questo non compare nel catalogo).')
    pdf.ln(4)

    indice = [
        ('1', 'Verso i clienti', ''),
        ('1.1', 'Tagliando ordine (termica 80 mm)', 'facsimile'),
        ('1.2', 'Locandina QR di registrazione', 'facsimile'),
        ('2', 'Verso la cucina e il gestore', ''),
        ('2.1', 'Etichette QR del cesto', 'facsimile'),
        ('3', 'Verso le aziende convenzionate', ''),
        ('3.1', 'Registro presenze mensile', 'facsimile'),
        ('3.2', 'Report giornaliero dei pasti (PDF)', 'output reale'),
        ('3.3', 'Riepilogo mensile per la fattura (PDF)', 'output reale'),
        ('3.4', 'Brochure di presentazione del servizio (PDF)', 'output reale'),
        ('4', 'Verso DS Consulting', ''),
        ('4.1', 'Transazioni del mese con provvigioni (PDF)', 'output reale'),
    ]
    pdf.set_x(14)
    pdf.set_text_color(*NAVY)
    pdf.set_font(FONT, 'B', 14)
    pdf.cell(0, 8, 'Indice')
    pdf.ln(9)
    pdf.set_draw_color(*LGRAY)
    for num, voce, tipo in indice:
        pdf.set_x(14)
        capitolo = '.' not in num
        pdf.set_font(FONT, 'B' if capitolo else '', 11.5 if capitolo else 10.5)
        pdf.set_text_color(*(NAVY if capitolo else DARK))
        pdf.cell(12, 6.4, num)
        pdf.cell(138, 6.4, voce)
        pdf.set_font(FONT, '', 9.5)
        pdf.set_text_color(*DGRAY)
        pdf.cell(32, 6.4, tipo, align='R')
        pdf.ln(6.4)
        if capitolo:
            pdf.line(14, pdf.get_y(), 196, pdf.get_y())
            pdf.set_y(pdf.get_y() + 1)

    # ── Sezione 1: clienti ───────────────────────────────────────────────────
    intestazione_sezione(pdf, 1, 'Verso i clienti',
                         'Quello che il cliente riceve in mano o vede appeso')
    scheda(pdf, 1, 'Tagliando ordine',
           [('Chi la riceve', 'Il cliente, attaccata al prodotto preparato'),
            ('Quando si produce', 'Alla preparazione di ogni ordine (ritiro a '
                                  'slot e builder)'),
            ('Da dove si stampa', 'Backoffice › Ordini › pulsante Stampa '
                                  '(si apre e stampa da sola)'),
            ('Carta e formato', 'Stampante termica, rotolo 80 mm')],
           'È il documento di lavoro che identifica l\'ordine: codice grande '
           'leggibile a colpo d\'occhio, orario di ritiro, elenco degli '
           'articoli con i prodotti del builder scomposti per ingrediente. '
           'Regola fissa: si allega al prodotto insieme allo scontrino del '
           'registratore di cassa.',
           'Rotta: /admin/orders/<id>/slip — template order_slip.html')
    facsimile_tagliando(pdf)

    pdf.add_page()
    scheda(pdf, 2, 'Locandina QR di registrazione',
           [('Chi la riceve', 'I nuovi clienti: si appende in bar, vicino '
                              'alla cassa'),
            ('Quando si produce', 'Una volta sola, all\'avvio del servizio '
                                  '(o quando cambia l\'indirizzo)'),
            ('Da dove si stampa', 'Backoffice › Clienti › QR Registrazione › '
                                  'Stampa / Salva PDF'),
            ('Carta e formato', 'A4, dalla stampa del browser')],
           'Il QR porta alla pagina di iscrizione del bar: il cliente si '
           'registra da solo con email o Google e l\'account si attiva dopo '
           'l\'approvazione (con avviso via email e Telegram). La stessa '
           'pagina di iscrizione ha a sua volta un pulsante di stampa.',
           'Rotta: /admin/clients/registration-qr — template '
           'registration_qr.html')
    facsimile_locandina(pdf)

    # ── Sezione 2: cucina e gestore ──────────────────────────────────────────
    intestazione_sezione(pdf, 2, 'Verso la cucina e il gestore',
                         'Le stampe operative della giornata')
    scheda(pdf, 3, 'Etichette QR del cesto',
           [('Chi la riceve', 'La cucina; l\'etichetta finisce sul prodotto '
                              'e il QR lo paga il cliente'),
            ('Quando si produce', 'Alla generazione di ogni lotto di pezzi '
                                  'pre-preparati'),
            ('Da dove si stampa', 'Backoffice › Cucina › Cesto Cucina › '
                                  'Genera etichette'),
            ('Carta e formato', 'A4 da ritagliare (griglia 3 colonne) o '
                                'etichette adesive')],
           'Ogni etichetta ha il QR di acquisto (il cliente lo inquadra e '
           'paga dal wallet), nome, prezzo, allergeni, codice del pezzo e '
           'data/ora di preparazione. Se la funzione "Gestione cesto" è '
           'spenta nelle Impostazioni, le etichette non si generano e i QR '
           'già stampati non sono acquistabili.',
           'Rotta: /admin/cesto/stampa/<lotto> — template cesto_stampa.html')
    facsimile_etichette(pdf)

    # ── Sezione 3: aziende convenzionate ─────────────────────────────────────
    intestazione_sezione(pdf, 3, 'Verso le aziende convenzionate',
                         'Presenze, report e documenti da allegare alla '
                         'fattura')
    scheda(pdf, 4, 'Registro presenze mensile',
           [('Chi la riceve', 'L\'azienda convenzionata (e il gestore per '
                              'controllo)'),
            ('Quando si produce', 'A fine mese o su richiesta dell\'azienda'),
            ('Da dove si stampa', 'Backoffice › Convenzioni › Presenze › '
                                  'Stampa registro presenze'),
            ('Carta e formato', 'A4, dalla stampa del browser')],
           'Il mese giorno per giorno: menù servito, dipendenti presenti con '
           'lo slot di ritiro, totale fatturabile per giornata e riepilogo '
           'in testa (pasti serviti, giorni con menù, fatturato del mese).',
           'Rotta: /admin/convenzioni/<id>/presenze — template '
           'convenzione_presenze.html')
    facsimile_presenze(pdf)

    pdf.add_page()
    scheda(pdf, 5, 'Report giornaliero dei pasti (PDF)',
           [('Chi la riceve', 'L\'azienda convenzionata, a conferma della '
                              'singola giornata'),
            ('Quando si produce', 'A fine servizio, per il giorno scelto'),
            ('Da dove si stampa', 'Backoffice › Convenzioni › Report PDF '
                                  '(con la data)'),
            ('Carta e formato', 'PDF A4, pronto da inviare via email')],
           'Elenco nominativo dei pasti del giorno con stato '
           '(consumato/prenotato), slot e importi. Le pagine che seguono '
           'sono l\'output reale generato dall\'applicazione per il 1° '
           'aprile 2026 dei dati di esempio.',
           'Rotta: /admin/convenzioni/<id>/report-pdf?d=AAAA-MM-GG')
    inserzioni.append((pdf.page_no(), 'giornaliero'))

    pdf.add_page()
    scheda(pdf, 6, 'Riepilogo mensile per la fattura (PDF)',
           [('Chi la riceve', 'L\'azienda convenzionata, come allegato alla '
                              'fattura del mese'),
            ('Quando si produce', 'A fine mese, prima della fatturazione'),
            ('Da dove si stampa', 'Backoffice › Convenzioni › Riepilogo '
                                  'mensile (scegliendo il mese)'),
            ('Carta e formato', 'PDF A4')],
           'Totali del mese per dipendente (ordinati per cognome) e per '
           'giorno, con il totale fatturabile della convenzione. Segue '
           'l\'output reale per aprile 2026.',
           'Rotta: /admin/convenzioni/<id>/report-mensile-pdf?m=AAAA-MM')
    inserzioni.append((pdf.page_no(), 'mensile'))

    pdf.add_page()
    scheda(pdf, 7, 'Brochure di presentazione del servizio (PDF)',
           [('Chi la riceve', 'Le aziende a cui si propone la convenzione'),
            ('Quando si produce', 'In fase commerciale, quando serve'),
            ('Da dove si stampa', 'Backoffice › Convenzioni › '
                                  'Presentazione PDF'),
            ('Carta e formato', 'PDF A4, anche da inviare via email')],
           'La presentazione del modulo Pasti Aziendali da lasciare '
           'all\'azienda. Dalla stessa pagina si scarica anche l\'abstract '
           'in formato Word (documento, non stampa: non è nel catalogo). '
           'Seguono le pagine reali della brochure.',
           'Rotta: /admin/convenzioni/presentazione-pdf')
    inserzioni.append((pdf.page_no(), 'brochure'))

    # ── Sezione 4: DS Consulting ─────────────────────────────────────────────
    intestazione_sezione(pdf, 4, 'Verso DS Consulting',
                         'La rendicontazione del canone e delle provvigioni')
    scheda(pdf, 8, 'Transazioni del mese con provvigioni (PDF)',
           [('Chi la riceve', 'DS Consulting, a supporto della fattura '
                              'del canone + fee'),
            ('Quando si produce', 'A fine mese, dal super amministratore'),
            ('Da dove si stampa', 'Backoffice › Guadagni DS Consulting › '
                                  'PDF transazioni'),
            ('Carta e formato', 'PDF A4 orizzontale')],
           'Tutte le transazioni del mese (ordini, banco, cesto, pasti '
           'aziendali) con imponibile e provvigione riga per riga, '
           'riconciliate con la pagina Guadagni. Segue l\'output reale per '
           'aprile 2026.',
           'Rotta: /admin/superadmin/guadagni/scontrini/pdf?year=&month=')
    inserzioni.append((pdf.page_no(), 'transazioni'))

    return bytes(pdf.output()), inserzioni


def unisci(catalogo_bytes, inserzioni, reali):
    """Il catalogo disegnato + le pagine dei PDF reali nei punti giusti."""
    base = PdfReader(BytesIO(catalogo_bytes))
    writer = PdfWriter()
    per_pagina = dict(inserzioni)
    for i, pagina in enumerate(base.pages, 1):
        writer.add_page(pagina)
        if i in per_pagina:
            for reale in PdfReader(BytesIO(reali[per_pagina[i]])).pages:
                writer.add_page(reale)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, 'wb') as f:
        writer.write(f)
    return len(writer.pages)


if __name__ == '__main__':
    print('1. dati di esempio…')
    flask_app, cid = prepara_dati()
    print('2. PDF reali dall\'app:')
    reali = scarica_pdf_reali(flask_app, cid)
    print('3. catalogo…')
    catalogo, inserzioni = costruisci(reali)
    tot = unisci(catalogo, inserzioni, reali)
    print('OK: %s (%d pagine)' % (OUT, tot))
