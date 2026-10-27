"""Co se prodává nejvíc a nejméně: nejprodávanější zboží, pomalu se točící zboží,
slovní návrhy a prostor pro slevu.

Návrhy („zvaž slevu“, „zvaž vyřazení“, „zvaž balíček“) jsou jen doporučení podle
jednoduchých pravidel; o tom, co se zbožím udělat, rozhoduje majitel.
"""

import math
from datetime import date, timedelta
from typing import NamedTuple

import pandas as pd

from . import formaty

# ------------------------------------------------------------------ nastavení
# Všechny prahy na jednom místě; změnou hodnot se změní, co se počítá jako pomalé
# zboží a jaký návrh dostane.
NASTAVENI = {
    "obdobi_tydnu": 8,                  # za kolik posledních týdnů se počítá prodej
    "pocet_nejprodavanejsich": 5,
    "pomale_od_tydnu_zasoby": 12,       # zásoba vydrží aspoň tolik týdnů -> pomalé zboží
    "temer_zadny_prodej_ks": 2,         # nejvýš tolik kusů za období -> „téměř žádný prodej“
    "dostatecna_marze": 0.30,           # podíl marže (po poplatcích) na ceně, od kterého má smysl sleva
    "balicek_min_objednavek": 3,        # kolikrát se zboží muselo prodat spolu s jiným produktem
    "balicek_min_podil": 0.40,          # ... a v jaké části svých objednávek
    "platebni_poplatek": 0.015,         # poplatek platební brány z prodejní ceny
}

NAVRH_SLEVA = "zvaž slevu"
NAVRH_VYRAZENI = "zvaž vyřazení"
NAVRH_BALICEK = "zvaž balíček"
SLOUPEC_NAVRHU = "Návrh (doporučení, rozhoduje majitel)"


class Sortiment(NamedTuple):
    od: date
    do: date
    nejprodavanejsi: pd.DataFrame
    pomale: pd.DataFrame
    prehled: pd.DataFrame       # všechny produkty skladu – pro kalkulačku slev
    poznamky: list


# ------------------------------------------------------------------ výpočty

def rychlost_prodeje(prodano_ks: float, tydnu: int) -> float:
    """Průměrně prodaných kusů za týden."""
    return prodano_ks / tydnu if tydnu > 0 else 0.0


def zasoba_na_tydny(skladem: float, za_tyden: float) -> float:
    """Na kolik týdnů vydrží zásoba. Bez zásoby 0, bez prodeje nekonečno."""
    if skladem <= 0:
        return 0.0
    if za_tyden <= 0:
        return math.inf
    return skladem / za_tyden


def zisk_na_kus(cena: float, nakupni: float, poplatek_ks: float,
                platebni_poplatek: float = NASTAVENI["platebni_poplatek"]) -> float:
    """Co zbude z jednoho prodaného kusu po nákupní ceně a poplatcích."""
    return cena * (1 - platebni_poplatek) - nakupni - poplatek_ks


def prostor_pro_slevu(cena: float, nakupni: float, poplatek_ks: float,
                      platebni_poplatek: float = NASTAVENI["platebni_poplatek"]) -> float:
    """Nejvyšší sleva (podíl z ceny), při které produkt ještě nejde do ztráty.

    Spočítaný fakt, ne doporučení. Když už plná cena nepokryje náklady, je prostor 0.
    """
    if not cena or math.isnan(cena) or cena <= 0:
        return math.nan
    mez = 1 - (nakupni + poplatek_ks) / (cena * (1 - platebni_poplatek))
    return max(0.0, mez)


def prepocet_slevy(cena: float, nakupni: float, poplatek_ks: float, sleva: float,
                   platebni_poplatek: float = NASTAVENI["platebni_poplatek"]) -> dict:
    """Kalkulačka: nová cena, zisk na kus a marže po slevě (sleva jako podíl, 0,2 = 20 %)."""
    nova_cena = cena * (1 - sleva)
    zisk = zisk_na_kus(nova_cena, nakupni, poplatek_ks, platebni_poplatek)
    return {
        "nova_cena": nova_cena,
        "zisk_na_kus": zisk,
        "marze": zisk / nova_cena if nova_cena > 0 else math.nan,
        "ve_ztrate": zisk < 0,
    }


def navrh(prodano_ks: float, marze: float, partner_balicku: str | None,
          nastaveni: dict = NASTAVENI) -> tuple[str, str]:
    """Slovní návrh pro pomalu se točící zboží a jeho důvod (bez čísel).

    Pořadí pravidel:
    1. téměř žádný prodej a nízká marže  -> zvaž vyřazení
    2. často se kupuje s jiným produktem  -> zvaž balíček
    3. dostatečná marže                   -> zvaž slevu
    4. jinak (nízká marže)                -> zvaž vyřazení
    """
    nizka_marze = math.isnan(marze) or marze < nastaveni["dostatecna_marze"]
    if prodano_ks <= nastaveni["temer_zadny_prodej_ks"] and nizka_marze:
        return NAVRH_VYRAZENI, "Téměř se neprodává a marže je nízká, sleva by nepomohla."
    if partner_balicku:
        return (f"{NAVRH_BALICEK} s produktem {partner_balicku}",
                "Zákazníci ho často kupují spolu s tímto produktem.")
    if not nizka_marze:
        return NAVRH_SLEVA, "Zásoba vydrží dlouho a marže dovoluje zlevnit."
    return NAVRH_VYRAZENI, "Prodává se pomalu a marže je nízká, na slevu není prostor."


def partner_balicku(objednavky: pd.DataFrame, sku: str, nazvy: pd.Series,
                    nastaveni: dict = NASTAVENI) -> str | None:
    """Produkt, se kterým se zboží v objednávkách kupuje nejčastěji – pokud dost často."""
    s_produktem = set(objednavky.loc[objednavky["sku"] == sku, "cislo"])
    if not s_produktem:
        return None
    ostatni = objednavky[objednavky["cislo"].isin(s_produktem) & (objednavky["sku"] != sku)]
    if ostatni.empty:
        return None
    spolu = ostatni.groupby("sku")["cislo"].nunique().sort_values(ascending=False)
    nejcastejsi, pocet = spolu.index[0], int(spolu.iloc[0])
    if pocet >= nastaveni["balicek_min_objednavek"] and pocet / len(s_produktem) >= nastaveni["balicek_min_podil"]:
        return str(nazvy.get(nejcastejsi, nejcastejsi))
    return None


def _bezna_cena(sklad: pd.DataFrame, prodeje: pd.DataFrame) -> pd.Series:
    """Prodejní cena ze skladu; když chybí, medián ceny z objednávek."""
    ze_skladu = sklad.set_index("sku")["prodejni_cena"] if "prodejni_cena" in sklad else pd.Series(dtype=float)
    z_objednavek = prodeje.groupby("sku")["cena"].median()
    return pd.Series({sku: ze_skladu.get(sku, math.nan) if not pd.isna(ze_skladu.get(sku, math.nan))
                      else z_objednavek.get(sku, math.nan) for sku in sklad["sku"]})


def analyzuj_sortiment(objednavky: pd.DataFrame, sklad: pd.DataFrame, ke_dni: date,
                       nastaveni: dict = NASTAVENI) -> Sortiment:
    tydnu = nastaveni["obdobi_tydnu"]
    od = ke_dni - timedelta(days=7 * tydnu - 1)
    vyrizene = objednavky[objednavky["stav"] == "Vyřízeno"]
    v_obdobi = vyrizene[(vyrizene["den"] >= pd.Timestamp(od)) & (vyrizene["den"] <= pd.Timestamp(ke_dni))]
    prodano = v_obdobi.groupby("sku")["mnozstvi"].sum()
    trzby = v_obdobi.groupby("sku")["trzba"].sum()
    nazvy = sklad.set_index("sku")["nazev"]
    ceny = _bezna_cena(sklad, vyrizene)
    poplatky = sklad.set_index("sku")["poplatek_ks"] if "poplatek_ks" in sklad else pd.Series(0.0, index=sklad["sku"])
    pct = nastaveni["platebni_poplatek"]

    radky = []
    for polozka in sklad.itertuples(index=False):
        sku = polozka.sku
        ks = float(prodano.get(sku, 0))
        za_tyden = rychlost_prodeje(ks, tydnu)
        cena = float(ceny.get(sku, math.nan))
        poplatek = float(poplatky.get(sku, 0.0) or 0.0)
        zisk = zisk_na_kus(cena, polozka.nakupni_cena, poplatek, pct) if not math.isnan(cena) else math.nan
        radky.append({
            "Produkt": polozka.nazev, "Kód": sku, "Prodáno ks": int(ks), "Tržby": float(trzby.get(sku, 0.0)),
            "Prodej za týden (ks)": za_tyden, "Skladem ks": int(polozka.skladem),
            "Zásoba vydrží (týdnů)": zasoba_na_tydny(polozka.skladem, za_tyden),
            "Běžná cena": cena, "Nákupní cena": float(polozka.nakupni_cena), "Náklady na kus": poplatek,
            "Zisk na kus": zisk, "Marže": zisk / cena if cena and not math.isnan(cena) else math.nan,
            "Prostor pro slevu": prostor_pro_slevu(cena, polozka.nakupni_cena, poplatek, pct),
        })
    prehled = pd.DataFrame(radky)

    nejprodavanejsi = (prehled[prehled["Prodáno ks"] > 0]
                       .sort_values(["Prodáno ks", "Tržby"], ascending=False)
                       .head(nastaveni["pocet_nejprodavanejsich"])
                       [["Produkt", "Kód", "Prodáno ks", "Tržby", "Prodej za týden (ks)"]]
                       .reset_index(drop=True))

    je_pomale = (prehled["Skladem ks"] > 0) & (
        (prehled["Zásoba vydrží (týdnů)"] >= nastaveni["pomale_od_tydnu_zasoby"])
        | (prehled["Prodáno ks"] <= nastaveni["temer_zadny_prodej_ks"]))
    pomale = prehled[je_pomale].sort_values("Zásoba vydrží (týdnů)", ascending=False).copy()
    pomale_nazvy = set(pomale["Produkt"])
    navrhy, duvody = [], []
    for polozka in pomale.itertuples(index=False):
        partner = partner_balicku(v_obdobi, polozka.Kód, nazvy, nastaveni)
        if partner in pomale_nazvy:
            partner = None          # balíček jen s produktem, který se prodává dobře
        prodano_ks = polozka[2]     # sloupec „Prodáno ks“
        text, duvod = navrh(prodano_ks, polozka.Marže, partner, nastaveni)
        navrhy.append(text)
        duvody.append(duvod)
    pomale[SLOUPEC_NAVRHU] = navrhy
    pomale["Proč"] = duvody
    pomale = pomale[["Produkt", "Kód", "Prodáno ks", "Skladem ks", "Prodej za týden (ks)", "Zásoba vydrží (týdnů)",
                     "Běžná cena", "Zisk na kus", "Marže", "Prostor pro slevu", SLOUPEC_NAVRHU, "Proč"]]

    poznamky = [
        f"Prodej za posledních {tydnu} týdnů ({formaty.datum(od)} – {formaty.datum(ke_dni)}), "
        f"zásoba podle posledního exportu skladu.",
        "Pomalu se točící zboží: zásoba vydrží aspoň "
        f"{nastaveni['pomale_od_tydnu_zasoby']} týdnů, nebo se za celé období prodaly nejvýš "
        f"{nastaveni['temer_zadny_prodej_ks']} kusy.",
        "Zisk na kus a marže jsou po nákupní ceně, nákladech na balení a vyřízení a poplatku za platbu "
        f"({formaty.procento(pct)} z ceny).",
        "Prostor pro slevu = nejvyšší sleva, při které produkt ještě neprodělává. Je to spočítaný fakt, ne doporučení.",
        "Návrhy jsou jen doporučení podle jednoduchých pravidel – o tom, co se zbožím udělat, rozhoduje majitel.",
    ]
    return Sortiment(od, ke_dni, nejprodavanejsi, pomale.reset_index(drop=True), prehled, poznamky)
