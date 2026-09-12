"""
vocabulary.py – Medizinisches Vokabular für Whisper-Hotwords und
Fuzzy-Nachkorrektur von Medikamenten- und Fachbegriffen.

Quellen (in dieser Reihenfolge zusammengeführt):
  1. vokabular_medizin.txt neben dem Server-Script (ein Begriff pro Zeile,
     '#' leitet Kommentare ein) – hier kann jede Praxis eigene Begriffe ergänzen.
  2. Eingebaute Grundliste (häufige Hausarzt-Präparate, Wirkstoffe, Diagnosen).
  3. Optional: ../../wissensdatenbank_rag/Medikamente Handelsnamen.json
     (Handelsnamen + Wirkstoffe).

Benötigt: pip install rapidfuzz
"""

import json
import os
import re
from pathlib import Path

try:
    from rapidfuzz import fuzz, process
    HAS_RAPIDFUZZ = True
except ImportError:  # pragma: no cover
    HAS_RAPIDFUZZ = False

VOCAB_FILENAME = "vokabular_medizin.txt"

# Häufige Präparate / Wirkstoffe / Begriffe in der Hausarztpraxis.
# Die ersten Einträge haben Priorität für die (begrenzten) Whisper-Hotwords.
BUILTIN_TERMS = [
    # Herz-Kreislauf
    "Ramipril", "Bisoprolol", "Metoprolol", "Amlodipin", "Candesartan", "Valsartan",
    "Losartan", "Lercanidipin", "Nebivolol", "Carvedilol", "Hydrochlorothiazid", "HCT",
    "Torasemid", "Furosemid", "Spironolacton", "Xipamid", "Atorvastatin", "Simvastatin",
    "Rosuvastatin", "Ezetimib", "Entresto", "Sacubitril", "Digitoxin", "Amiodaron",
    "Molsidomin", "Nitrospray", "Ivabradin", "Eplerenon",
    # Gerinnung
    "Apixaban", "Eliquis", "Rivaroxaban", "Xarelto", "Edoxaban", "Lixiana", "Dabigatran",
    "Marcumar", "Phenprocoumon", "Clopidogrel", "Acetylsalicylsäure", "ASS",
    # Diabetes / Stoffwechsel
    "Metformin", "Sitagliptin", "Empagliflozin", "Jardiance", "Dapagliflozin", "Forxiga",
    "Semaglutid", "Ozempic", "Dulaglutid", "Trulicity", "Liraglutid", "Insulin glargin",
    "Lantus", "Toujeo", "Insulin degludec", "Tresiba", "Novorapid", "Humalog", "Glimepirid",
    "L-Thyroxin", "Levothyroxin", "Euthyrox", "Allopurinol", "Febuxostat", "Colchicin",
    # Magen-Darm
    "Pantoprazol", "Omeprazol", "Esomeprazol", "Macrogol", "Movicol", "Lactulose",
    "Loperamid", "Metoclopramid", "MCP", "Domperidon", "Dimenhydrinat", "Vomex",
    "Butylscopolamin", "Buscopan", "Mesalazin", "Simeticon", "Iberogast",
    # Schmerz
    "Ibuprofen", "Diclofenac", "Naproxen", "Etoricoxib", "Arcoxia", "Celecoxib",
    "Metamizol", "Novalgin", "Novaminsulfon", "Paracetamol", "Tilidin", "Tramadol",
    "Oxycodon", "Targin", "Fentanyl", "Morphin", "Pregabalin", "Lyrica", "Gabapentin",
    "Amitriptylin", "Duloxetin",
    # Antibiotika / Infekt
    "Amoxicillin", "Amoxiclav", "Amoxicillin-Clavulansäure", "Cefuroxim", "Cefpodoxim",
    "Azithromycin", "Clarithromycin", "Doxycyclin", "Ciprofloxacin", "Levofloxacin",
    "Cotrimoxazol", "Nitrofurantoin", "Fosfomycin", "Pivmecillinam", "Clindamycin",
    "Penicillin V", "Aciclovir", "Valaciclovir", "Fluconazol", "Nystatin",
    # Atemwege / Allergie
    "Salbutamol", "Formoterol", "Salmeterol", "Budesonid", "Fluticason", "Beclometason",
    "Tiotropium", "Spiriva", "Symbicort", "Foster", "Trimbow", "Montelukast",
    "Cetirizin", "Loratadin", "Desloratadin", "Fexofenadin", "Mometason", "Nasonex",
    "Xylometazolin", "Ambroxol", "Acetylcystein", "ACC", "Prednisolon", "Dexamethason",
    # Psyche / Neuro
    "Citalopram", "Escitalopram", "Sertralin", "Venlafaxin", "Mirtazapin", "Bupropion",
    "Opipramol", "Trimipramin", "Quetiapin", "Risperidon", "Melperon", "Pipamperon",
    "Promethazin", "Lorazepam", "Tavor", "Diazepam", "Zopiclon", "Zolpidem", "Melatonin",
    "Levodopa", "Madopar", "Memantin", "Donepezil", "Rivastigmin", "Sumatriptan",
    "Topiramat", "Lamotrigin", "Valproat", "Levetiracetam", "Methylphenidat",
    # Urologie / Gyn
    "Tamsulosin", "Finasterid", "Mirabegron", "Trospium", "Solifenacin", "Sildenafil",
    "Tadalafil", "Estradiol", "Progesteron",
    # Knochen / Rheuma
    "Alendronat", "Ibandronat", "Denosumab", "Prolia", "Colecalciferol", "Vitamin D3",
    "Dekristol", "Methotrexat", "MTX", "Folsäure", "Hydroxychloroquin", "Sulfasalazin",
    # Sonstiges
    "Ferro sanol", "Eisen(II)-glycin-sulfat", "Vitamin B12", "Cyanocobalamin",
    "Kaliumchlorid", "Magnesium", "Hydrocortison", "Tacrolimus", "Ciclosporin",
    "Betamethason", "Clotrimazol", "Fusidinsäure", "Octenisept",
    # Diagnosen / Fachbegriffe
    "arterielle Hypertonie", "Diabetes mellitus Typ 2", "koronare Herzkrankheit", "KHK",
    "Vorhofflimmern", "Herzinsuffizienz", "pAVK", "Niereninsuffizienz", "Hypothyreose",
    "Hyperthyreose", "Hyperlipidämie", "Hypercholesterinämie", "Adipositas", "COPD",
    "Asthma bronchiale", "Pneumonie", "Bronchitis", "Sinusitis", "Pharyngitis",
    "Tonsillitis", "Otitis media", "Gastritis", "Refluxösophagitis", "Gastroenteritis",
    "Divertikulitis", "Cholezystitis", "Appendizitis", "Harnwegsinfekt", "Zystitis",
    "Pyelonephritis", "Erysipel", "Herpes zoster", "Borreliose", "Lumbago", "Lumboischialgie",
    "Gonarthrose", "Coxarthrose", "Osteoporose", "Polyneuropathie", "Depression",
    "Angststörung", "Schlafstörung", "Migräne", "Spannungskopfschmerz", "Schwindel",
    "Synkope", "Anämie", "Eisenmangel", "Hyperurikämie", "Gicht", "Ekzem", "Psoriasis",
    # Untersuchungen / Labor / Organisatorisches
    "HbA1c", "Kreatinin", "GFR", "TSH", "CRP", "Leukozyten", "Hämoglobin", "Ferritin",
    "Troponin", "D-Dimer", "INR", "Quick", "Transaminasen", "Gamma-GT", "LDL", "HDL",
    "Triglyceride", "Urinstatus", "Sonographie", "Abdomensonographie", "EKG",
    "Langzeit-EKG", "Langzeit-Blutdruck", "Ergometrie", "Spirometrie", "Röntgen-Thorax",
    "MRT", "CT", "Koloskopie", "Gastroskopie", "Echokardiographie", "Duplexsonographie",
    "DMP", "Arbeitsunfähigkeit", "Überweisung", "Krankenhauseinweisung", "Reha",
    "Physiotherapie", "Krankengymnastik", "manuelle Therapie", "Ergotherapie", "Logopädie",
    "Kardiologe", "Orthopäde", "Gastroenterologe", "Pneumologe", "Neurologe", "Dermatologe",
    "Urologe", "Gynäkologe", "HNO-Arzt", "Psychiater", "Psychotherapie", "Impfung",
    "Tetanus", "Influenza", "Pneumokokken", "Herpes-zoster-Impfung", "FSME", "Auskultation",
    "Palpation", "Perkussion", "Blutdruck", "Puls", "Sauerstoffsättigung",
]

# Whisper-Hotwords teilen sich das Prompt-Fenster (max. ~224 Tokens).
# Darum wird die Hotword-Liste auf ein Zeichenbudget begrenzt.
HOTWORD_CHAR_BUDGET = 700


def _vocab_path(base_dir: str) -> Path:
    return Path(base_dir) / VOCAB_FILENAME


def _load_rag_json(base_dir: str) -> list:
    """Lädt Handelsnamen/Wirkstoffe aus der RAG-JSON des Repos, falls vorhanden."""
    candidates = [
        Path(base_dir) / "Medikamente Handelsnamen.json",
        Path(base_dir).parent.parent / "wissensdatenbank_rag" / "Medikamente Handelsnamen.json",
    ]
    terms = []
    for p in candidates:
        if p.exists():
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                for entry in data:
                    w = entry.get("Wirkstoff")
                    if w:
                        terms.append(w)
                    for h in entry.get("Handelsname", []) or []:
                        terms.append(h)
                break
            except Exception as e:  # pragma: no cover
                print(f"[VOCAB] RAG-JSON konnte nicht gelesen werden: {e}")
    return terms


def ensure_vocab_file(base_dir: str) -> Path:
    """Erzeugt vokabular_medizin.txt beim ersten Start aus der Grundliste."""
    p = _vocab_path(base_dir)
    if not p.exists():
        lines = [
            "# Asklaion – medizinisches Vokabular (ein Begriff pro Zeile).",
            "# Wird für Whisper-Hotwords (obere Einträge haben Vorrang) und für die",
            "# automatische Korrektur ähnlich klingender Wörter genutzt.",
            "# Eigene Präparate, Ortsnamen, Kollegen etc. einfach ergänzen.",
            "",
        ] + BUILTIN_TERMS
        p.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"[VOCAB] Vokabular-Datei erstellt: {p}")
    return p


class Vocabulary:
    def __init__(self, base_dir: str):
        self.base_dir = base_dir
        self.terms: list = []          # Reihenfolge = Priorität
        self._lower_map: dict = {}     # lower -> kanonische Schreibweise
        self._fuzzy_pool: list = []    # lowercase-Begriffe, die für Fuzzy geeignet sind
        self.reload()

    def reload(self):
        ensure_vocab_file(self.base_dir)
        seen = set()
        terms = []

        def add(t):
            t = t.strip()
            if not t or t.startswith("#"):
                return
            key = t.lower()
            if key not in seen:
                seen.add(key)
                terms.append(t)

        for line in _vocab_path(self.base_dir).read_text(encoding="utf-8").splitlines():
            add(line)
        for t in BUILTIN_TERMS:
            add(t)
        for t in _load_rag_json(self.base_dir):
            add(t)

        self.terms = terms
        self._lower_map = {t.lower(): t for t in terms}
        # Für Fuzzy nur Einzelwörter ab 7 Zeichen (vermeidet Treffer wie "reisen" -> "Eisen")
        self._fuzzy_pool = [t.lower() for t in terms if len(t) >= 7 and " " not in t]
        print(f"[VOCAB] {len(self.terms)} Begriffe geladen ({len(self._fuzzy_pool)} fuzzy-fähig)")

    # ------------------------------------------------------------------
    # Hotwords für Whisper
    # ------------------------------------------------------------------
    def hotwords(self, context_terms=None, budget: int = HOTWORD_CHAR_BUDGET) -> str:
        """
        Baut den Hotword-String: zuerst Kontextbegriffe der Sitzung
        (z. B. Medikationsplan des Patienten), dann das Praxisvokabular
        nach Priorität, bis das Zeichenbudget erschöpft ist.
        """
        out = []
        used = 0
        seen = set()
        for t in list(context_terms or []) + self.terms:
            t = str(t).strip()
            key = t.lower()
            if not t or key in seen:
                continue
            if used + len(t) + 2 > budget:
                if context_terms and t in context_terms:
                    continue  # Kontext hat Vorrang, aber Budget hart einhalten
                break
            seen.add(key)
            out.append(t)
            used += len(t) + 2
        return ", ".join(out)

    # ------------------------------------------------------------------
    # Fuzzy-Nachkorrektur
    # ------------------------------------------------------------------
    _WORD_RE = re.compile(r"[A-Za-zÄÖÜäöüß][A-Za-zÄÖÜäöüß\-]*")

    def correct_word(self, word: str, extra_terms=None, cutoff: int = 86):
        """
        Gibt (korrigiertes Wort, geändert?) zurück. Korrigiert nur
        großgeschriebene Wörter ab 7 Buchstaben (deutsche Substantive, also
        typischerweise Präparatenamen), die einem Vokabular-Eintrag sehr
        ähnlich sind (z. B. "Raemipril" -> "Ramipril", "Ra-Emipril" -> "Ramipril").
        """
        if not HAS_RAPIDFUZZ:
            return word, False
        m = self._WORD_RE.search(word)
        if not m:
            return word, False
        core = m.group(0)
        prefix, suffix = word[:m.start()], word[m.end():]
        if len(core) < 7 or not core[0].isupper():
            return word, False
        key = core.lower()
        pool_extra = [t.lower() for t in (extra_terms or []) if len(t) >= 7 and " " not in t]
        if key in self._lower_map or key in pool_extra:
            return word, False
        cand_key = key.replace("-", "")
        pool = pool_extra + self._fuzzy_pool
        if not pool:
            return word, False
        best = process.extractOne(cand_key, pool, scorer=fuzz.ratio, score_cutoff=cutoff)
        if not best:
            return word, False
        match = best[0]
        canonical = self._lower_map.get(match)
        if canonical is None:
            for t in (extra_terms or []):
                if t.lower() == match:
                    canonical = t
                    break
        if canonical is None:
            return word, False
        return prefix + canonical + suffix, True

    def correct_text(self, text: str, extra_terms=None) -> str:
        if not text:
            return text
        parts = re.split(r"(\s+)", text)
        out = []
        for p in parts:
            if p and not p.isspace():
                p, _ = self.correct_word(p, extra_terms)
            out.append(p)
        return "".join(out)
