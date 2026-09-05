# -*- coding: utf-8 -*-
"""Lettura di un referto di analisi e proposta di dieta.

Il cliente carica il PDF del laboratorio (o scrive i valori a mano); qui si
estraggono i parametri che hanno un legame diretto con il cibo, si
confrontano con gli intervalli di riferimento comunemente stampati dai
laboratori e si traducono in una proposta: quali "attenzioni" accendere nel
profilo dieta, quale equilibrio del pranzo preferire, qualche consiglio in
parole.

Che cosa NON è: una lettura medica. Gli intervalli sono generali, non quelli
del laboratorio del cliente (che possono differire), e un valore fuori
soglia va discusso con il medico. Il file viene letto e scartato: restano
solo i valori che il cliente conferma. Il disclaimer della dieta vale
tutto, anche qui.
"""
import io
import json
import re

# ── I parametri che leggiamo ────────────────────────────────────────────────
# Ogni voce: chiave, etichetta, unità, alias (regex, sul testo minuscolo),
# intervalli per sesso {'M': (min, max), 'F': (min, max), '': (min, max)} con
# None per il lato aperto, soglia "limite" facoltativa (da min/max fino a
# questa soglia il valore è "al limite", oltre è "alto"/"basso").
PARAMETRI = [
    dict(chiave='glicemia', etichetta='Glicemia a digiuno', unita='mg/dL',
         alias=[r'glicemia', r'glucosio'], range={'': (70, 99)}, limite_alto=125),
    dict(chiave='hba1c', etichetta='Emoglobina glicata (HbA1c)', unita='%',
         alias=[r'emoglobina\s+glicata', r'hba1c', r'\bglicata'], range={'': (4.0, 5.6)}, limite_alto=6.4),
    dict(chiave='colesterolo_tot', etichetta='Colesterolo totale', unita='mg/dL',
         alias=[r'colesterolo\s+totale', r'colesterolo(?!\s*(hdl|ldl))'], range={'': (None, 199)}, limite_alto=239),
    dict(chiave='ldl', etichetta='Colesterolo LDL', unita='mg/dL',
         alias=[r'ldl'], range={'': (None, 115)}, limite_alto=159),
    dict(chiave='hdl', etichetta='Colesterolo HDL', unita='mg/dL',
         alias=[r'hdl'], range={'M': (40, None), 'F': (50, None), '': (40, None)}),
    dict(chiave='trigliceridi', etichetta='Trigliceridi', unita='mg/dL',
         alias=[r'trigliceridi'], range={'': (None, 149)}, limite_alto=199),
    dict(chiave='acido_urico', etichetta='Acido urico', unita='mg/dL',
         alias=[r'acido\s+urico', r'uricemia'], range={'M': (3.5, 7.0), 'F': (2.6, 6.0), '': (2.6, 7.0)}),
    dict(chiave='emoglobina', etichetta='Emoglobina', unita='g/dL',
         alias=[r'emoglobina(?!\s*glicata)(?!\s*\()'], range={'M': (13.5, 17.5), 'F': (12.0, 15.5), '': (12.0, 17.5)}),
    dict(chiave='ferritina', etichetta='Ferritina', unita='ng/mL',
         alias=[r'ferritina'], range={'M': (30, 400), 'F': (15, 200), '': (15, 400)}),
    dict(chiave='vitamina_d', etichetta='Vitamina D (25-OH)', unita='ng/mL',
         alias=[r'vitaminad', r'vitamina\s*d\d?'], range={'': (30, 100)}, limite_basso=20),
    dict(chiave='creatinina', etichetta='Creatinina', unita='mg/dL',
         alias=[r'creatinina'], range={'M': (0.7, 1.2), 'F': (0.5, 1.0), '': (0.5, 1.2)}),
    dict(chiave='alt', etichetta='Transaminasi ALT (GPT)', unita='U/L',
         alias=[r'\balt\b', r'\bgpt\b', r'alanina'], range={'': (None, 40)}, limite_alto=80),
    dict(chiave='pressione_sist', etichetta='Pressione sistolica', unita='mmHg',
         alias=[], range={'': (90, 129)}, limite_alto=139),
    dict(chiave='pressione_diast', etichetta='Pressione diastolica', unita='mmHg',
         alias=[], range={'': (60, 84)}, limite_alto=89),
]
PARAMETRI_MAP = {p['chiave']: p for p in PARAMETRI}

# Valori plausibili: fuori da qui il numero letto dal PDF è un'altra cosa
# (una data, un codice, l'intervallo del laboratorio).
PLAUSIBILI = {
    'glicemia': (40, 500), 'hba1c': (3, 15), 'colesterolo_tot': (80, 500), 'ldl': (20, 400),
    'hdl': (10, 150), 'trigliceridi': (30, 1500), 'acido_urico': (1, 15), 'emoglobina': (5, 22),
    'ferritina': (1, 2000), 'vitamina_d': (3, 200), 'creatinina': (0.2, 10), 'alt': (3, 1000),
    'pressione_sist': (70, 250), 'pressione_diast': (40, 150),
}

_NUMERO = r'(?P<v>\d{1,4}(?:[.,]\d{1,2})?)'


def leggi_testo(contenuto, nome_file=''):
    """Il testo di un PDF o di un file di testo; '' se non si riesce a leggerlo."""
    nome = (nome_file or '').lower()
    if nome.endswith('.txt') or nome.endswith('.csv'):
        try:
            return contenuto.decode('utf-8', 'replace')
        except Exception:
            return ''
    try:
        from pypdf import PdfReader
    except ImportError:
        return ''
    try:
        lettore = PdfReader(io.BytesIO(contenuto))
        return '\n'.join((pagina.extract_text() or '') for pagina in lettore.pages)
    except Exception:
        return ''


def _numero(s):
    try:
        return float(s.replace(',', '.'))
    except (ValueError, AttributeError):
        return None


def estrai_valori(testo):
    """{chiave: valore} per i parametri trovati nel testo. Prende il primo
    numero plausibile che segue l'etichetta, entro pochi caratteri: nei
    referti il risultato precede l'intervallo di riferimento."""
    t = (testo or '').lower().replace('\xa0', ' ')
    # "25-OH vitamina D": il 25 non e' un valore, e' il nome dell'esame.
    t = re.sub(r'25[\s-]*oh[\s-]*(?:vitamina\s*d\d?|d\d?)?', ' vitaminad ', t)
    t = re.sub(r'vitamina\s*d\d?\s*\(?\s*vitaminad\s*\)?', ' vitaminad ', t)
    trovati = {}
    for p in PARAMETRI:
        if not p['alias']:
            continue
        for alias in p['alias']:
            for m in re.finditer(alias + r'[^\d\n]{0,45}?' + _NUMERO, t):
                v = _numero(m.group('v'))
                lo, hi = PLAUSIBILI[p['chiave']]
                if v is not None and lo <= v <= hi:
                    trovati[p['chiave']] = v
                    break
            if p['chiave'] in trovati:
                break
    # Pressione: "130/85" dopo la parola pressione (o "pa")
    m = re.search(r'(?:pressione|p\.?a\.?)[^\d\n]{0,30}?(\d{2,3})\s*/\s*(\d{2,3})', t)
    if m:
        s, d = int(m.group(1)), int(m.group(2))
        if 70 <= s <= 250 and 40 <= d <= 150:
            trovati['pressione_sist'] = float(s)
            trovati['pressione_diast'] = float(d)
    return trovati


def _riferimento(p, sesso):
    return p['range'].get(sesso if sesso in ('M', 'F') else '', p['range'].get(''))


def valuta(valori, sesso=''):
    """Per ogni valore: stato ('ok', 'limite', 'alto', 'basso') e la soglia usata."""
    esiti = []
    for p in PARAMETRI:
        v = valori.get(p['chiave'])
        if v is None:
            continue
        lo, hi = _riferimento(p, sesso)
        stato = 'ok'
        if hi is not None and v > hi:
            stato = 'limite' if (p.get('limite_alto') is not None and v <= p['limite_alto']) else 'alto'
        elif lo is not None and v < lo:
            stato = 'limite' if (p.get('limite_basso') is not None and v >= p['limite_basso']) else 'basso'
        rif = ('%s–%s' % (_fmt(lo), _fmt(hi)) if lo is not None and hi is not None
               else ('fino a %s' % _fmt(hi) if hi is not None else 'almeno %s' % _fmt(lo)))
        esiti.append({'chiave': p['chiave'], 'etichetta': p['etichetta'], 'unita': p['unita'],
                      'valore': v, 'stato': stato, 'riferimento': rif})
    return esiti


def _fmt(v):
    if v is None:
        return ''
    return ('%d' % v) if float(v).is_integer() else ('%.1f' % v).replace('.', ',')


def proposta(esiti, profilo=None):
    """Dagli esiti alla proposta: attenzioni da accendere, equilibrio del
    pranzo, consigli. Regole semplici e dichiarate; niente diagnosi."""
    stati = {e['chiave']: e['stato'] for e in esiti}
    attenzioni = []
    consigli = []
    equilibrio = None

    def fuori(chiave, *quali):
        return stati.get(chiave) in quali

    def accendi(k):
        if k not in attenzioni:
            attenzioni.append(k)

    if fuori('glicemia', 'alto', 'limite') or fuori('hba1c', 'alto', 'limite'):
        accendi('glicemia')
        consigli.append('Zuccheri: il piano evita dolci, bibite zuccherate e cioccolato; '
                        'preferisci pane e pasta integrali e la frutta come chiusura.')
    if (fuori('colesterolo_tot', 'alto', 'limite') or fuori('ldl', 'alto', 'limite')
            or fuori('trigliceridi', 'alto', 'limite')):
        accendi('colesterolo')
        equilibrio = 'mediterraneo'
        consigli.append('Grassi: meno fritti, salumi e formaggi grassi; più pesce, legumi, '
                        'verdure e olio d\'oliva a crudo.')
        if fuori('trigliceridi', 'alto', 'limite'):
            consigli.append('Trigliceridi: pesano soprattutto zuccheri semplici e alcolici, '
                            'più dei grassi.')
    if fuori('hdl', 'basso'):
        equilibrio = equilibrio or 'mediterraneo'
        consigli.append('HDL basso: aiutano il movimento quotidiano, il pesce e la frutta '
                        'secca; il piano sceglie l\'equilibrio mediterraneo.')
    if fuori('acido_urico', 'alto'):
        accendi('acido_urico')
        consigli.append('Acido urico: il piano limita carne rossa, crostacei, salumi, alcolici '
                        'e bibite zuccherate; bevi molta acqua.')
    if fuori('emoglobina', 'basso') or fuori('ferritina', 'basso'):
        consigli.append('Ferro: privilegia carne magra, pesce, legumi e verdure a foglia, '
                        'abbinati a una fonte di vitamina C (agrumi, pomodoro); il caffè '
                        'subito dopo il pasto ne riduce l\'assorbimento.')
        if profilo is not None and (profilo.regime or 'onnivoro') == 'vegano':
            consigli.append('Con un regime vegano il ferro va seguito con più attenzione: '
                            'parlane con il medico.')
    if fuori('vitamina_d', 'basso', 'limite'):
        consigli.append('Vitamina D: pesce grasso, uova e latticini aiutano, ma la fonte '
                        'principale è la luce del sole; l\'eventuale integrazione la decide il medico.')
    if fuori('creatinina', 'alto'):
        consigli.append('Creatinina alta: non aumentare le proteine per conto tuo; il piano '
                        'resta bilanciato. Questo valore va discusso con il medico.')
        if profilo is not None and profilo.equilibrio == 'proteico':
            equilibrio = 'bilanciato'
    if fuori('pressione_sist', 'alto', 'limite') or fuori('pressione_diast', 'alto', 'limite'):
        accendi('pressione')
        consigli.append('Pressione: il piano limita il sale (salumi, formaggi stagionati, fritti, '
                        'salse pronte); attenzione anche a caffè e alcolici.')
    if fuori('alt', 'alto', 'limite'):
        accendi('fegato')
        consigli.append('Transaminasi: niente alcolici, pochi fritti e dolci, porzioni moderate.')

    if profilo is not None and profilo.peso_kg and profilo.altezza_cm:
        m = profilo.altezza_cm / 100.0
        bmi = profilo.peso_kg / (m * m)
        if bmi >= 25 and (profilo.obiettivo or 'mantenimento') == 'mantenimento' and attenzioni:
            consigli.append('Con questi valori e un indice di massa corporea sopra 25, l\'obiettivo '
                            '"Perdere peso" aiuta: puoi sceglierlo nelle preferenze.')

    if not attenzioni and not consigli:
        consigli.append('I valori letti rientrano negli intervalli di riferimento generali: '
                        'nessuna modifica proposta alla dieta.')
    return {'attenzioni': attenzioni, 'equilibrio': equilibrio, 'consigli': consigli}


def applica(profilo, prop):
    """Accende le attenzioni proposte e, se c'è, l'equilibrio. Ritorna le
    modifiche fatte (per il messaggio)."""
    fatte = []
    attuali = [a for a in (profilo.attenzioni or '').split(',') if a]
    for k in prop.get('attenzioni') or []:
        if k not in attuali:
            attuali.append(k)
            fatte.append(k)
    profilo.attenzioni = ','.join(attuali)
    eq = prop.get('equilibrio')
    if eq and eq != (profilo.equilibrio or 'bilanciato'):
        profilo.equilibrio = eq
        fatte.append('equilibrio:%s' % eq)
    return fatte


def a_json(d):
    return json.dumps(d, ensure_ascii=False)


def da_json(s, default):
    try:
        return json.loads(s) if s else default
    except ValueError:
        return default
