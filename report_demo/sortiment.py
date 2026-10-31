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
    # Další náklady e-shopu pro zisk na kus, prostor pro slevu a kalkulačku.
    # Výchozí 0 = nepočítají se (ukázková čísla zůstávají stejná).
    "doprava_na_objednavku": 0.0,       # Kč, doprava hrazená e-shopem (např. doprava zdarma)
    "marketing_na_objednavku": 0.0,     # Kč, reklama v přepočtu na jednu objednávku
    "kusu_v_objednavce": 1.0,           # průměr; doprava a reklama se dělí tímto číslem
    "provize": 0.0,                     # provize marketplace nebo srovnávače z prodejní ceny
    "vratnost": 0.0,                    # podíl objednávek, které se vrátí
    "naklad_na_vratku": 0.0,            # Kč na jednu vratku (očekávaný náklad na kus = vratnost × náklad)
    "platce_dph": False,
    "ceny_s_dph": False,                # ceny v ukázkových datech jsou bez DPH
    "sazba_dph": 0.21,
    "cilova_marze": 0.0,                # minimální marže z ceny (bez DPH), pod kterou majitel nechce jít
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


def _s_poplatkem(nastaveni: dict, platebni_poplatek: float | None) -> dict:
    """Kopie nastavení, případně s jiným poplatkem za platbu (kvůli jednoduchým výpočtům v testech)."""
    n = dict(NASTAVENI) | dict(nastaveni)
    if platebni_poplatek is not None:
        n["platebni_poplatek"] = platebni_poplatek
    return n


def podil_bez_dph(nastaveni: dict = NASTAVENI) -> float:
    """Kolik z ceny pro zákazníka zůstane e-shopu po odvodu DPH (1 = celá cena).

    DPH se odečítá jen u plátce, jehož ceny DPH obsahují.
    """
    if nastaveni["platce_dph"] and nastaveni["ceny_s_dph"]:
        return 1 / (1 + nastaveni["sazba_dph"])
    return 1.0


def procentni_naklady(nastaveni: dict = NASTAVENI) -> float:
    """Náklady počítané z ceny pro zákazníka: poplatek za platbu a provize."""
    return nastaveni["platebni_poplatek"] + nastaveni["provize"]


def pevne_naklady_na_kus(nakupni: float, poplatek_ks: float, nastaveni: dict = NASTAVENI) -> dict:
    """Náklady v Kč na jeden prodaný kus, které nezávisí na ceně."""
    kusu = nastaveni["kusu_v_objednavce"]
    if kusu <= 0:
        raise ValueError("Průměrný počet kusů v objednávce musí být větší než nula.")
    return {
        "Nákupní cena": nakupni,
        "Balení a vyřízení": poplatek_ks,
        "Doprava hrazená e-shopem": nastaveni["doprava_na_objednavku"] / kusu,
        "Marketing a reklama": nastaveni["marketing_na_objednavku"] / kusu,
        "Vratky (očekávaný náklad)": nastaveni["vratnost"] * nastaveni["naklad_na_vratku"],
    }


def zisk_na_kus(cena: float, nakupni: float, poplatek_ks: float, platebni_poplatek: float | None = None,
                nastaveni: dict = NASTAVENI) -> float:
    """Co zbude z jednoho prodaného kusu po DPH (u plátce), poplatcích, provizích a nákladech na kus."""
    n = _s_poplatkem(nastaveni, platebni_poplatek)
    return (cena * podil_bez_dph(n) - cena * procentni_naklady(n)
            - sum(pevne_naklady_na_kus(nakupni, poplatek_ks, n).values()))


def marze(cena: float, zisk: float, nastaveni: dict = NASTAVENI) -> float:
    """Marže = zisk na kus jako podíl z prodejní ceny bez DPH."""
    zaklad = cena * podil_bez_dph(nastaveni)
    return zisk / zaklad if zaklad > 0 else math.nan


def prostor_pro_slevu(cena: float, nakupni: float, poplatek_ks: float, platebni_poplatek: float | None = None,
                      nastaveni: dict = NASTAVENI) -> float:
    """Nejvyšší sleva (podíl z ceny), při které produkt ještě nejde do ztráty – hranice nulového zisku.

    Spočítaný fakt, ne doporučení. Když už plná cena nepokryje náklady, je prostor 0.
    """
    if not cena or math.isnan(cena) or cena <= 0:
        return math.nan
    n = _s_poplatkem(nastaveni, platebni_poplatek)
    zbyva_z_ceny = podil_bez_dph(n) - procentni_naklady(n)
    if zbyva_z_ceny <= 0:
        return 0.0
    nulovy_zisk = sum(pevne_naklady_na_kus(nakupni, poplatek_ks, n).values()) / zbyva_z_ceny
    return max(0.0, 1 - nulovy_zisk / cena)


def max_sleva_pri_cilove_marzi(cena: float, nakupni: float, poplatek_ks: float,
                               nastaveni: dict = NASTAVENI) -> dict:
    """Doporučená maximální sleva, aby marže neklesla pod cílovou.

    Nejnižší cena = pevné náklady na kus / (podíl bez DPH × (1 − cílová marže) − poplatek − provize);
    bez DPH je to pevné náklady / (1 − poplatek − provize − cílová marže).
    Vrací slevu (podíl), nejnižší cenu a případně srozumitelnou hlášku, proč to nejde.
    """
    vysledek = {"sleva": math.nan, "nejnizsi_cena": math.nan, "hlaska": None}
    if not cena or math.isnan(cena) or cena <= 0:
        return vysledek
    jmenovatel = podil_bez_dph(nastaveni) * (1 - nastaveni["cilova_marze"]) - procentni_naklady(nastaveni)
    if jmenovatel <= 0:
        vysledek["hlaska"] = ("Cílová marže je nedosažitelná při jakékoli ceně: spolu s poplatky a provizemi "
                              "by z ceny nezbylo nic na nákup a další náklady.")
        return vysledek
    nejnizsi = sum(pevne_naklady_na_kus(nakupni, poplatek_ks, nastaveni).values()) / jmenovatel
    vysledek["nejnizsi_cena"] = nejnizsi
    if nejnizsi > cena:
        vysledek["hlaska"] = (f"Cílové marže nejde dosáhnout ani bez slevy – produkt by musel stát "
                              f"aspoň {formaty.kc(nejnizsi, 2)}.")
        return vysledek
    vysledek["sleva"] = 1 - nejnizsi / cena
    return vysledek


def rozpis_ceny(cena_po_sleve: float, nakupni: float, poplatek_ks: float, nastaveni: dict = NASTAVENI) -> pd.DataFrame:
    """Co všechno se z ceny pro zákazníka odečte, než zbude zisk na kus."""
    zaklad = cena_po_sleve * podil_bez_dph(nastaveni)
    radky = [("Cena pro zákazníka", cena_po_sleve),
             ("DPH (odvede se státu)", -(cena_po_sleve - zaklad)),
             ("Poplatek za platbu", -cena_po_sleve * nastaveni["platebni_poplatek"]),
             ("Provize marketplace nebo srovnávače", -cena_po_sleve * nastaveni["provize"])]
    radky += [(nazev, -hodnota) for nazev, hodnota in pevne_naklady_na_kus(nakupni, poplatek_ks, nastaveni).items()]
    radky.append(("Zisk na kus", sum(hodnota for _, hodnota in radky)))
    return pd.DataFrame([(nazev, hodnota + 0.0) for nazev, hodnota in radky], columns=["Položka", "Kč na kus"])


def prepocet_slevy(cena: float, nakupni: float, poplatek_ks: float, sleva: float,
                   platebni_poplatek: float | None = None, nastaveni: dict = NASTAVENI) -> dict:
    """Kalkulačka: nová cena, zisk na kus, marže a rozpis po slevě (sleva jako podíl, 0,2 = 20 %)."""
    n = _s_poplatkem(nastaveni, platebni_poplatek)
    nova_cena = cena * (1 - sleva)
    zisk = zisk_na_kus(nova_cena, nakupni, poplatek_ks, nastaveni=n)
    return {
        "nova_cena": nova_cena,
        "zisk_na_kus": zisk,
        "marze": marze(nova_cena, zisk, n),
        "ve_ztrate": zisk < 0,
        "rozpis": rozpis_ceny(nova_cena, nakupni, poplatek_ks, n),
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
    nastaveni = dict(NASTAVENI) | dict(nastaveni)

    radky = []
    for polozka in sklad.itertuples(index=False):
        sku = polozka.sku
        ks = float(prodano.get(sku, 0))
        za_tyden = rychlost_prodeje(ks, tydnu)
        cena = float(ceny.get(sku, math.nan))
        poplatek = float(poplatky.get(sku, 0.0) or 0.0)
        zisk = (zisk_na_kus(cena, polozka.nakupni_cena, poplatek, nastaveni=nastaveni)
                if not math.isnan(cena) else math.nan)
        radky.append({
            "Produkt": polozka.nazev, "Kód": sku, "Prodáno ks": int(ks), "Tržby": float(trzby.get(sku, 0.0)),
            "Prodej za týden (ks)": za_tyden, "Skladem ks": int(polozka.skladem),
            "Zásoba vydrží (týdnů)": zasoba_na_tydny(polozka.skladem, za_tyden),
            "Běžná cena": cena, "Nákupní cena": float(polozka.nakupni_cena), "Náklady na kus": poplatek,
            "Zisk na kus": zisk, "Marže": marze(cena, zisk, nastaveni) if not math.isnan(cena) else math.nan,
            "Prostor pro slevu": prostor_pro_slevu(cena, polozka.nakupni_cena, poplatek, nastaveni=nastaveni),
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
