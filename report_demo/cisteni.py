"""Čištění vstupních dat.

Každá úprava se zapisuje do logu změn (zdroj, řádek v souboru, původní a nová
hodnota, důvod), aby bylo vždy dohledatelné, co program na datech změnil.
"""

import difflib
import math
import re
import unicodedata
from datetime import date, datetime, timedelta

import pandas as pd

from . import formaty

KATEGORIE = ["Doprava", "Energie", "Marketing", "Mzdy", "Nájem", "Obaly", "Software", "Ostatní"]
# Jiné názvy, které lidé pro stejnou kategorii běžně používají (bez diakritiky, malými písmeny).
ALIASY_KATEGORII = {
    "postovne": "Doprava",
    "preprava": "Doprava",
    "reklama": "Marketing",
    "sw": "Software",
    "elektrina": "Energie",
    "najemne": "Nájem",
}
# Česká data jsou vždy den-měsíc-rok; "05/08/2026" je tedy 5. srpna.
FORMATY_DATA = [
    "%d.%m.%Y %H:%M",
    "%d.%m.%Y %H:%M:%S",
    "%d.%m.%Y",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%d",
    "%d/%m/%Y",
]
VYCHOZI_MIN_ZASOBA = 10
SHODA_KODU = 0.85
SHODA_KATEGORIE = 0.75

SLOUPCE_LOGU = ["Zdroj", "Řádek v souboru", "Sloupec", "Původní hodnota", "Nová hodnota", "Úprava"]
SLOUPCE_OBJEDNAVEK = {
    "Číslo objednávky": "cislo",
    "Datum": "datum",
    "Kód zboží": "sku",
    "Název zboží": "nazev",
    "Množství": "mnozstvi",
    "Cena/ks": "cena",
    "Stav": "stav",
}
SLOUPCE_NAKLADU = {"Datum": "datum", "Kategorie": "kategorie", "Popis": "popis", "Částka": "castka"}
SLOUPCE_SKLADU = {
    "sku": "sku",
    "nazev": "nazev",
    "skladem_ks": "skladem",
    "min_zasoba": "min_zasoba",
    "nakupni_cena": "nakupni_cena",
}
# Volitelné sloupce skladu: běžná prodejní cena a náklady na balení a vyřízení jednoho kusu.
VOLITELNE_SLOUPCE_SKLADU = {"prodejni_cena": "prodejni_cena", "poplatek_ks": "poplatek_ks"}


class LogZmen:
    """Seznam všech úprav provedených při čištění."""

    def __init__(self):
        self._zaznamy: list[dict] = []

    def zapis(self, zdroj, radek, sloupec, puvodni, nova, uprava) -> None:
        self._zaznamy.append(
            dict(zip(SLOUPCE_LOGU, [zdroj, radek, sloupec, _text(puvodni), _text(nova), uprava]))
        )

    def __len__(self) -> int:
        return len(self._zaznamy)

    def tabulka(self) -> pd.DataFrame:
        return pd.DataFrame(self._zaznamy, columns=SLOUPCE_LOGU)

    def souhrn(self) -> pd.DataFrame:
        tab = self.tabulka()
        if tab.empty:
            return pd.DataFrame(columns=["Zdroj", "Úprava", "Počet"])
        return (
            tab.groupby(["Zdroj", "Úprava"], sort=False).size().reset_index(name="Počet")
            .sort_values(["Zdroj", "Počet"], ascending=[True, False], ignore_index=True)
        )


def _text(hodnota) -> str:
    if je_prazdne(hodnota):
        return ""
    if isinstance(hodnota, datetime):
        return hodnota.strftime("%Y-%m-%d %H:%M") if hodnota.hour or hodnota.minute else formaty.datum(hodnota)
    if isinstance(hodnota, float) and hodnota.is_integer():
        return str(int(hodnota))
    return str(hodnota)


def je_prazdne(hodnota) -> bool:
    if hodnota is None:
        return True
    if isinstance(hodnota, str):
        return not hodnota.strip()
    try:
        return bool(pd.isna(hodnota))
    except (TypeError, ValueError):
        return False


def bez_diakritiky(text: str) -> str:
    rozlozeny = unicodedata.normalize("NFKD", text)
    return "".join(z for z in rozlozeny if not unicodedata.combining(z))


def parse_datum(hodnota) -> datetime | None:
    """Převede buňku z Excelu nebo text v libovolném z běžných formátů na datum."""
    if je_prazdne(hodnota):
        return None
    if isinstance(hodnota, pd.Timestamp):
        return hodnota.to_pydatetime()
    if isinstance(hodnota, datetime):
        return hodnota
    if isinstance(hodnota, date):
        return datetime(hodnota.year, hodnota.month, hodnota.day)
    if isinstance(hodnota, (int, float)) and not isinstance(hodnota, bool):
        # Datum uložené v Excelu jako pořadové číslo dne (např. 46238).
        if 20000 < hodnota < 80000:
            return datetime(1899, 12, 30) + timedelta(days=float(hodnota))
        return None
    text = re.sub(r"\s*([./])\s*", r"\1", str(hodnota).strip())  # "3. 8. 2026" -> "3.8.2026"
    for vzor in FORMATY_DATA:
        try:
            return datetime.strptime(text, vzor)
        except ValueError:
            continue
    return None


def parse_castka(hodnota) -> float | None:
    """'1 250,50 Kč' -> 1250.5; '1.250,50' -> 1250.5; čísla vrací beze změny."""
    if je_prazdne(hodnota):
        return None
    if isinstance(hodnota, (int, float)) and not isinstance(hodnota, bool):
        return None if math.isnan(hodnota) else float(hodnota)
    text = str(hodnota).replace(formaty.NBSP, " ")
    text = re.sub(r"(?i)kč|czk", "", text).replace(" ", "")
    if "," in text and "." in text:
        text = text.replace(".", "")
    text = text.replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return None


def oprav_kategorii(hodnota) -> str:
    """Překlepy, velikost písmen a jiné názvy převede na jednu z KATEGORIE."""
    if je_prazdne(hodnota):
        return "Ostatní"
    norm = " ".join(bez_diakritiky(str(hodnota)).lower().split())
    kanonicke = {bez_diakritiky(k).lower(): k for k in KATEGORIE}
    if norm in kanonicke:
        return kanonicke[norm]
    if norm in ALIASY_KATEGORII:
        return ALIASY_KATEGORII[norm]
    shoda = difflib.get_close_matches(norm, list(kanonicke), n=1, cutoff=SHODA_KATEGORIE)
    return kanonicke[shoda[0]] if shoda else "Ostatní"


def normalizuj_stav(hodnota) -> str:
    text = "" if je_prazdne(hodnota) else bez_diakritiky(str(hodnota)).lower().strip()
    if text.startswith("vyri") or text in ("dokonceno", "doruceno"):
        return "Vyřízeno"
    if text.startswith("storn") or text == "zruseno":
        return "Stornováno"
    return "Neznámý"


def normalizuj_kod(hodnota) -> str:
    return "" if je_prazdne(hodnota) else str(hodnota).strip().upper().replace(" ", "")


def _pripravit(surova: pd.DataFrame, prejmenovani: dict) -> list[dict]:
    df = surova.copy()
    df.columns = [str(c).strip() for c in df.columns]
    df = df.rename(columns=prejmenovani)
    if "radek" not in df.columns:
        df["radek"] = range(2, len(df) + 2)  # řádek 1 je záhlaví
    for sloupec in prejmenovani.values():
        if sloupec not in df.columns:
            df[sloupec] = None
    return df.to_dict("records")


def vycisti_objednavky(surova: pd.DataFrame, platne_kody: list[str], log: LogZmen,
                       zdroj: str = "Objednávky") -> pd.DataFrame:
    platne = set(platne_kody)
    videne: dict[tuple, int] = {}
    radky = []
    for z in _pripravit(surova, SLOUPCE_OBJEDNAVEK):
        radek = z["radek"]

        def zmena(sloupec, puvodni, nova, uprava):
            log.zapis(zdroj, radek, sloupec, puvodni, nova, uprava)

        puvodni_kod = "" if je_prazdne(z["sku"]) else str(z["sku"])
        kod = normalizuj_kod(puvodni_kod)
        if kod != puvodni_kod:
            zmena("Kód zboží", puvodni_kod, kod, "sjednocen zápis kódu")
        if kod not in platne:
            shoda = difflib.get_close_matches(kod, sorted(platne), n=1, cutoff=SHODA_KODU)
            if not shoda:
                zmena("Kód zboží", kod, "", "neznámý kód zboží – řádek vyřazen")
                continue
            zmena("Kód zboží", kod, shoda[0], "opraven překlep v kódu")
            kod = shoda[0]

        okamzik = parse_datum(z["datum"])
        if okamzik is None:
            zmena("Datum", z["datum"], "", "neplatné datum – řádek vyřazen")
            continue
        mnozstvi = parse_castka(z["mnozstvi"])
        if mnozstvi is None or mnozstvi <= 0:
            zmena("Množství", z["mnozstvi"], "", "chybí množství – řádek vyřazen")
            continue
        cena = parse_castka(z["cena"])
        if cena is None:
            zmena("Cena/ks", z["cena"], "", "chybí cena – řádek vyřazen")
            continue

        stav = normalizuj_stav(z["stav"])
        if stav != _text(z["stav"]):
            zmena("Stav", z["stav"], stav, "sjednocen zápis stavu")

        cislo = _text(z["cislo"]).strip()
        otisk = (cislo, kod, okamzik, mnozstvi, cena, stav)
        if otisk in videne:
            zmena("celý řádek", f"obj. {cislo}, {kod} (shodný s řádkem {videne[otisk]})", "",
                  "duplicitní řádek – vyřazen")
            continue
        videne[otisk] = radek
        radky.append({"cislo": cislo, "datum": okamzik, "sku": kod, "mnozstvi": int(mnozstvi),
                      "cena": cena, "trzba": mnozstvi * cena, "stav": stav})

    df = pd.DataFrame(radky, columns=["cislo", "datum", "sku", "mnozstvi", "cena", "trzba", "stav"])
    df["datum"] = pd.to_datetime(df["datum"])
    df["den"] = df["datum"].dt.normalize()
    return df


def vycisti_naklady(surova: pd.DataFrame, log: LogZmen, zdroj: str = "Náklady") -> pd.DataFrame:
    videne: dict[tuple, int] = {}
    radky = []
    for z in _pripravit(surova, SLOUPCE_NAKLADU):
        radek = z["radek"]

        def zmena(sloupec, puvodni, nova, uprava):
            log.zapis(zdroj, radek, sloupec, puvodni, nova, uprava)

        if all(je_prazdne(z[s]) for s in SLOUPCE_NAKLADU.values()):
            zmena("celý řádek", "", "", "prázdný řádek – vyřazen")
            continue
        popis = "" if je_prazdne(z["popis"]) else " ".join(str(z["popis"]).split())
        if "celkem" in bez_diakritiky(f"{popis} {_text(z['datum'])}").lower():
            zmena("Popis", popis, "", "mezisoučet – vyřazen, aby se náklady nepočítaly dvakrát")
            continue

        okamzik = parse_datum(z["datum"])
        if okamzik is None:
            zmena("Datum", z["datum"], "", "neplatné datum – řádek vyřazen")
            continue
        if isinstance(z["datum"], str):
            zmena("Datum", z["datum"], formaty.datum(okamzik), "datum převedeno z textu")

        kategorie = oprav_kategorii(z["kategorie"])
        if kategorie != _text(z["kategorie"]):
            uprava = "neznámá kategorie → Ostatní" if kategorie == "Ostatní" else "opravena kategorie"
            zmena("Kategorie", z["kategorie"], kategorie, uprava)

        castka = parse_castka(z["castka"])
        if castka is None:
            zmena("Částka", z["castka"], "", "chybí částka – řádek vyřazen")
            continue
        if isinstance(z["castka"], str):
            zmena("Částka", z["castka"], formaty.kc(castka, 2), "částka převedena z textu")

        otisk = (okamzik.date(), kategorie, popis, castka)
        if otisk in videne:
            zmena("celý řádek", f"{popis}, {formaty.kc(castka)} (shodný s řádkem {videne[otisk]})", "",
                  "duplicitní záznam – vyřazen")
            continue
        videne[otisk] = radek
        radky.append({"datum": okamzik, "kategorie": kategorie, "popis": popis, "castka": castka})

    df = pd.DataFrame(radky, columns=["datum", "kategorie", "popis", "castka"])
    df["datum"] = pd.to_datetime(df["datum"]).dt.normalize()
    return df


def vycisti_sklad(surova: pd.DataFrame, log: LogZmen, zdroj: str = "Sklad") -> pd.DataFrame:
    polozky: dict[str, dict] = {}
    sloupce_souboru = {str(c).strip() for c in surova.columns}
    for z in _pripravit(surova, SLOUPCE_SKLADU | VOLITELNE_SLOUPCE_SKLADU):
        radek = z["radek"]

        def zmena(sloupec, puvodni, nova, uprava):
            log.zapis(zdroj, radek, sloupec, puvodni, nova, uprava)

        if all(je_prazdne(z[s]) for s in SLOUPCE_SKLADU.values()):
            zmena("celý řádek", "", "", "prázdný řádek – vyřazen")
            continue
        puvodni_kod = "" if je_prazdne(z["sku"]) else str(z["sku"])
        kod = normalizuj_kod(puvodni_kod)
        if not kod:
            zmena("sku", "", "", "chybí kód zboží – řádek vyřazen")
            continue
        if kod != puvodni_kod:
            zmena("sku", puvodni_kod, kod, "sjednocen zápis kódu")

        nakupni = parse_castka(z["nakupni_cena"])
        if nakupni is None:
            zmena("nakupni_cena", z["nakupni_cena"], "", "chybí nákupní cena – řádek vyřazen")
            continue
        skladem = parse_castka(z["skladem"])
        if skladem is None:
            zmena("skladem_ks", "", 0, "chybí stav zásoby – nastaveno 0")
            skladem = 0
        elif skladem < 0:
            zmena("skladem_ks", z["skladem"], 0, "záporný stav opraven na 0 (ověřte inventuru)")
            skladem = 0
        minimum = parse_castka(z["min_zasoba"])
        if minimum is None:
            zmena("min_zasoba", "", VYCHOZI_MIN_ZASOBA, "chybí minimální zásoba – použita výchozí")
            minimum = VYCHOZI_MIN_ZASOBA
        prodejni = parse_castka(z["prodejni_cena"])
        if prodejni is None and "prodejni_cena" in sloupce_souboru:
            zmena("prodejni_cena", "", "", "chybí prodejní cena – použije se cena z objednávek")
        poplatek = parse_castka(z["poplatek_ks"])
        if poplatek is None:
            if "poplatek_ks" in sloupce_souboru:
                zmena("poplatek_ks", "", 0, "chybí náklady na kus – počítá se s nulou")
            poplatek = 0.0

        if kod in polozky:
            zmena("sku", f"{kod} (nahrazuje řádek {polozky[kod]['radek']})", "",
                  "kód je v souboru vícekrát – platí poslední záznam")
        polozky[kod] = {"radek": radek, "sku": kod,
                        "nazev": "" if je_prazdne(z["nazev"]) else str(z["nazev"]).strip(),
                        "skladem": int(skladem), "min_zasoba": int(minimum), "nakupni_cena": nakupni,
                        "prodejni_cena": math.nan if prodejni is None else prodejni, "poplatek_ks": poplatek}

    df = pd.DataFrame(list(polozky.values()),
                      columns=["radek", "sku", "nazev", "skladem", "min_zasoba", "nakupni_cena",
                               "prodejni_cena", "poplatek_ks"])
    return df.drop(columns="radek").reset_index(drop=True)
