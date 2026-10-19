"""Výpočet týdenního reportu z vyčištěných dat."""

import math
from datetime import date, timedelta
from typing import NamedTuple

import pandas as pd

from . import formaty
from .nacitani import VycistenaData

# Kategorie, které se mění týden od týdne. Měsíční platby (nájem, mzdy, energie,
# software) by jinak „vyskakovaly“ jako výkyv pokaždé, když jsou zaplaceny.
PROMENLIVE_KATEGORIE = ("Doprava", "Marketing", "Obaly")
# Pravidelné měsíční platby: v týdnu, kdy jsou zaplaceny, sníží zisk skokově, proto je
# report ukazuje odděleně od ostatních provozních nákladů.
MESICNI_KATEGORIE = ("Mzdy", "Nájem", "Energie", "Software")
PRAH_VYSOKE_TRZBY = 2.0      # den s tržbou alespoň dvojnásobnou proti obvyklé úrovni
PRAH_NIZKE_TRZBY = 0.4       # den s tržbou pod 40 % obvyklé úrovně
PRAH_NAKLADY = 1.5           # kategorie nákladů o 50 % nad průměrem
PRAH_NAKLADY_KC = 3000       # ... a zároveň alespoň o 3 000 Kč
REZERVA_DNI = 14             # zboží, které vystačí na méně dní, je potřeba doobjednat
OBJEDNAT_NA_DNI = 30

UKAZATELE = [
    # klíč v ukazatelích, popisek, typ (kc / ks / pct)
    ("trzby", "Tržby (bez DPH)", "kc"),
    ("naklady_zbozi", "Nákupní cena prodaného zboží", "kc"),
    ("hruba_marze", "Hrubá marže", "kc"),
    ("marze_pct", "Hrubá marže v %", "pct"),
    ("provozni_naklady", "Provozní náklady celkem", "kc"),
    ("mesicni_platby", "z toho pravidelné měsíční platby", "kc"),
    ("ostatni_provozni", "z toho ostatní provozní náklady", "kc"),
    ("provozni_zisk", "Provozní zisk", "kc"),
    ("zisk_bez_mesicnich", "Provozní zisk bez měsíčních plateb", "kc"),
    ("pocet_objednavek", "Počet objednávek", "ks"),
    ("prumerna_objednavka", "Průměrná objednávka", "kc"),
    ("stornovane", "Stornované objednávky", "ks"),
]


class TydenniReport(NamedTuple):
    od: date
    do: date
    ukazatele: dict
    ukazatele_minule: dict
    top_produkty: pd.DataFrame
    nizka_zasoba: pd.DataFrame
    vykyvy: pd.DataFrame
    denni_trzby: pd.DataFrame
    naklady_kategorie: pd.DataFrame
    rozklad_zisku: pd.DataFrame
    veta_rozkladu: str
    log_souhrn: pd.DataFrame
    log_detail: pd.DataFrame
    sklad_ke_dni: date
    zjisteni: list
    poznamky: list


def _obdobi(df: pd.DataFrame, sloupec: str, od: date, do: date) -> pd.DataFrame:
    return df[(df[sloupec] >= pd.Timestamp(od)) & (df[sloupec] <= pd.Timestamp(do))]


def _vyrizene(df: pd.DataFrame) -> pd.DataFrame:
    return df[df["stav"] == "Vyřízeno"]


def _podil(a: float, b: float) -> float:
    return a / b if b else math.nan


def _zmena(nove: float, stare: float) -> float:
    return nove / stare - 1 if stare else math.nan


def dostupne_tydny(objednavky: pd.DataFrame) -> list[date]:
    """Pondělí všech úplných týdnů v datech, od nejnovějšího."""
    if objednavky.empty:
        return []
    prvni = objednavky["den"].min().date()
    posledni = objednavky["den"].max().date()
    pondeli = prvni + timedelta(days=(7 - prvni.weekday()) % 7)
    tydny = []
    while pondeli + timedelta(days=6) <= posledni:
        tydny.append(pondeli)
        pondeli += timedelta(days=7)
    return tydny[::-1]


def spocitej_ukazatele(data: VycistenaData, od: date, do: date) -> dict:
    vse = _obdobi(data.objednavky, "den", od, do)
    obj = _vyrizene(vse)
    nakupni = obj["sku"].map(data.sklad.set_index("sku")["nakupni_cena"])
    trzby = float(obj["trzba"].sum())
    naklady_zbozi = float((obj["mnozstvi"] * nakupni).sum())
    naklady = _obdobi(data.naklady, "datum", od, do)
    provozni = float(naklady["castka"].sum())
    mesicni = float(naklady.loc[naklady["kategorie"].isin(MESICNI_KATEGORIE), "castka"].sum())
    pocet = int(obj["cislo"].nunique())
    hruba = trzby - naklady_zbozi
    return {
        "trzby": trzby,
        "naklady_zbozi": naklady_zbozi,
        "hruba_marze": hruba,
        "marze_pct": _podil(hruba, trzby),
        "provozni_naklady": provozni,
        "mesicni_platby": mesicni,
        "ostatni_provozni": provozni - mesicni,
        "provozni_zisk": hruba - provozni,
        "zisk_bez_mesicnich": hruba - (provozni - mesicni),
        "marketing": float(naklady.loc[naklady["kategorie"] == "Marketing", "castka"].sum()),
        "pocet_objednavek": pocet,
        "prumerna_objednavka": _podil(trzby, pocet),
        "stornovane": int(vse.loc[vse["stav"] == "Stornováno", "cislo"].nunique()),
    }


def top_produkty(data: VycistenaData, od: date, do: date, pocet: int = 5) -> pd.DataFrame:
    tyden = _vyrizene(_obdobi(data.objednavky, "den", od, do))
    minule = _vyrizene(_obdobi(data.objednavky, "den", od - timedelta(days=7), do - timedelta(days=7)))
    souhrn = tyden.groupby("sku").agg(kusy=("mnozstvi", "sum"), trzby=("trzba", "sum"))
    trzby_minule = minule.groupby("sku")["trzba"].sum()
    souhrn = souhrn.sort_values("trzby", ascending=False).head(pocet)
    celkem = tyden["trzba"].sum()
    nazvy = data.sklad.set_index("sku")["nazev"]
    return pd.DataFrame({
        "Produkt": souhrn.index.map(nazvy),
        "Kód": souhrn.index,
        "Prodáno ks": souhrn["kusy"].astype(int).values,
        "Tržby": souhrn["trzby"].values,
        "Podíl na tržbách": (souhrn["trzby"] / celkem).values if celkem else math.nan,
        "Změna proti minulému týdnu": [_zmena(t, trzby_minule.get(k, 0)) for k, t in souhrn["trzby"].items()],
    })


def nizka_zasoba(data: VycistenaData, ke_dni: date, dni_historie: int = 28) -> pd.DataFrame:
    """Zboží pod minimální zásobou nebo s rezervou na méně než REZERVA_DNI dní."""
    prodeje = _vyrizene(_obdobi(data.objednavky, "den", ke_dni - timedelta(days=dni_historie - 1), ke_dni))
    za_den = prodeje.groupby("sku")["mnozstvi"].sum() / dni_historie
    sklad = data.sklad.copy()
    sklad["za_den"] = sklad["sku"].map(za_den).fillna(0.0)
    sklad["vystaci"] = [s / d if d > 0 else math.inf for s, d in zip(sklad["skladem"], sklad["za_den"])]
    nizke = sklad[(sklad["skladem"] < sklad["min_zasoba"]) | (sklad["vystaci"] < REZERVA_DNI)]
    nizke = nizke.sort_values("vystaci")
    cil = [max(d * OBJEDNAT_NA_DNI, m) for d, m in zip(nizke["za_den"], nizke["min_zasoba"])]
    return pd.DataFrame({
        "Produkt": nizke["nazev"].values,
        "Kód": nizke["sku"].values,
        "Skladem ks": nizke["skladem"].values,
        "Minimální zásoba": nizke["min_zasoba"].values,
        "Prodej za den (ø 4 týdny)": nizke["za_den"].round(1).values,
        "Vystačí na dní": nizke["vystaci"].round(1).values,
        "Doporučeno objednat ks": [max(0, math.ceil(c - s)) for c, s in zip(cil, nizke["skladem"])],
    })


def _denni_rada(data: VycistenaData, do: date) -> pd.Series:
    obj = _vyrizene(data.objednavky)
    if obj.empty:
        return pd.Series(dtype=float)
    rada = obj.groupby("den")["trzba"].sum()
    dny = pd.date_range(data.objednavky["den"].min(), pd.Timestamp(do), freq="D")
    return rada.reindex(dny, fill_value=0.0)


def _obvykla_uroven(rada: pd.Series, den: pd.Timestamp) -> float:
    """Medián tržby ve stejný den v týdnu za předchozí 4 týdny (stačí 3 z nich)."""
    historie = [den - pd.Timedelta(days=7 * k) for k in range(1, 5)]
    hodnoty = [rada[h] for h in historie if h in rada.index]
    return float(pd.Series(hodnoty).median()) if len(hodnoty) >= 3 else math.nan


def denni_trzby(data: VycistenaData, od: date, do: date) -> pd.DataFrame:
    rada = _denni_rada(data, do)
    dny = pd.date_range(pd.Timestamp(od), pd.Timestamp(do), freq="D")
    return pd.DataFrame({
        "Den": dny,
        "Tržby": [float(rada.get(d, 0.0)) for d in dny],
        "Obvyklá úroveň": [_obvykla_uroven(rada, d) for d in dny],
    })


def vykyvy(data: VycistenaData, od: date, do: date) -> pd.DataFrame:
    radky = []
    obj = _vyrizene(data.objednavky)
    for _, den in denni_trzby(data, od, do).iterrows():
        skutecnost, obvykle = den["Tržby"], den["Obvyklá úroveň"]
        if math.isnan(obvykle) or obvykle <= 0:
            continue
        pomer = skutecnost / obvykle
        if pomer >= PRAH_VYSOKE_TRZBY:
            objednavky_dne = obj[obj["den"] == den["Den"]].groupby("cislo")["trzba"].sum()
            nejvetsi = objednavky_dne.idxmax()
            poznamka = (f"Největší objednávka č. {nejvetsi}: {formaty.kc(objednavky_dne[nejvetsi])} "
                        f"({formaty.procento(objednavky_dne[nejvetsi] / skutecnost, 0)} tržby dne).")
            radky.append(["Tržby nezvykle vysoké", formaty.datum_kratce(den["Den"]), skutecnost, obvykle,
                          pomer - 1, poznamka])
        elif pomer <= PRAH_NIZKE_TRZBY:
            radky.append(["Tržby nezvykle nízké", formaty.datum_kratce(den["Den"]), skutecnost, obvykle,
                          pomer - 1, "Ověřte, zda ten den fungoval e-shop a platby."])

    naklady = data.naklady
    for kategorie in PROMENLIVE_KATEGORIE if not naklady.empty else ():
        v_kategorii = naklady[naklady["kategorie"] == kategorie]
        tento = _obdobi(v_kategorii, "datum", od, do)
        predchozi = [
            _obdobi(v_kategorii, "datum", od - timedelta(days=7 * k), do - timedelta(days=7 * k))["castka"].sum()
            for k in range(1, 5)
            if od - timedelta(days=7 * k) >= naklady["datum"].min().date()
        ]
        if len(predchozi) < 2:
            continue
        prumer = sum(predchozi) / len(predchozi)
        soucet = tento["castka"].sum()
        if prumer > 0 and soucet >= PRAH_NAKLADY * prumer and soucet - prumer >= PRAH_NAKLADY_KC:
            nejvetsi = tento.loc[tento["castka"].idxmax()]
            radky.append([f"Náklady nezvykle vysoké: {kategorie}", "celý týden", soucet, prumer,
                          soucet / prumer - 1,
                          f"Největší položka: {nejvetsi['popis']} ({formaty.kc(nejvetsi['castka'])})."])
    return pd.DataFrame(radky, columns=["Co", "Kdy", "Skutečnost", "Obvyklá úroveň", "Odchylka", "Poznámka"])


def naklady_podle_kategorii(data: VycistenaData, od: date, do: date) -> pd.DataFrame:
    tyden = _obdobi(data.naklady, "datum", od, do).groupby("kategorie")["castka"].sum()
    predchozi = _obdobi(data.naklady, "datum", od - timedelta(days=28), od - timedelta(days=1))
    prumer = predchozi.groupby("kategorie")["castka"].sum() / 4
    kategorie = sorted(set(tyden.index) | set(prumer.index))
    return pd.DataFrame({
        "Kategorie": kategorie,
        "Typ": ["pravidelná měsíční platba" if k in MESICNI_KATEGORIE else "ostatní provozní" for k in kategorie],
        "Tento týden": [float(tyden.get(k, 0.0)) for k in kategorie],
        "Průměr za týden (předchozí 4 týdny)": [float(prumer.get(k, 0.0)) for k in kategorie],
    })


def _mesicni_platby_text(data: VycistenaData, od: date, do: date) -> str:
    """'mzdy 58 000 Kč, software 1 490 Kč' – měsíční platby zaplacené v daném týdnu."""
    naklady = _obdobi(data.naklady, "datum", od, do)
    platby = naklady[naklady["kategorie"].isin(MESICNI_KATEGORIE)].groupby("kategorie")["castka"].sum()
    poradi = [k for k in MESICNI_KATEGORIE if k in platby.index]
    return ", ".join(f"{k.lower()} {formaty.kc(platby[k])}" for k in poradi) or "žádné"


def rozklad_zmeny_zisku(data: VycistenaData, od: date, do: date, ukazatele: dict,
                        minule: dict) -> tuple[pd.DataFrame, str]:
    """Kolik ze změny provozního zisku proti minulému týdnu způsobily měsíční platby,
    kolik marketing a kolik všechno ostatní (marže, doprava, obaly…)."""
    zmena = ukazatele["provozni_zisk"] - minule["provozni_zisk"]
    vliv_mesicni = -(ukazatele["mesicni_platby"] - minule["mesicni_platby"])
    vliv_marketing = -(ukazatele["marketing"] - minule["marketing"])
    vliv_ostatni = zmena - vliv_mesicni - vliv_marketing
    tento_text = _mesicni_platby_text(data, od, do)
    minule_text = _mesicni_platby_text(data, od - timedelta(days=7), do - timedelta(days=7))
    tabulka = pd.DataFrame({
        "Vliv": ["Pravidelné měsíční platby", "Marketing", "Ostatní vlivy (hrubá marže, doprava, obaly…)",
                 "Změna provozního zisku celkem"],
        "Dopad na zisk": [vliv_mesicni, vliv_marketing, vliv_ostatni, zmena],
        "Vysvětlení": [
            f"tento týden {tento_text}; minulý týden {minule_text}",
            f"tento týden {formaty.kc(ukazatele['marketing'])}, minulý týden {formaty.kc(minule['marketing'])}",
            f"hrubá marže {formaty.kc_znamenko(ukazatele['hruba_marze'] - minule['hruba_marze'])}, "
            f"doprava, obaly a další {formaty.kc_znamenko(vliv_ostatni - (ukazatele['hruba_marze'] - minule['hruba_marze']))}",
            f"z {formaty.kc(minule['provozni_zisk'])} na {formaty.kc(ukazatele['provozni_zisk'])}",
        ],
    })
    smer = "Pokles" if zmena < 0 else "Nárůst"
    veta = (f"{smer} provozního zisku o {formaty.kc(abs(zmena))}: měsíční platby "
            f"{formaty.kc_znamenko(vliv_mesicni)} (tento týden {tento_text}; minulý týden {minule_text}), "
            f"marketing {formaty.kc_znamenko(vliv_marketing)}, ostatní vlivy {formaty.kc_znamenko(vliv_ostatni)}.")
    return tabulka, veta


def hlavni_zjisteni(ukazatele: dict, minule: dict, top: pd.DataFrame, zasoba: pd.DataFrame,
                    vykyvy_tab: pd.DataFrame, veta_rozkladu: str = "") -> list[str]:
    """Pár vět srozumitelných bez tabulek – to první, co si vedení přečte."""
    vety = []
    zmena = _zmena(ukazatele["trzby"], minule["trzby"])
    if math.isnan(zmena):
        vety.append(f"Tržby za týden: {formaty.kc(ukazatele['trzby'])}.")
    else:
        smer = "vzrostly" if zmena >= 0 else "klesly"
        vety.append(f"Tržby {smer} o {formaty.procento(abs(zmena))} na {formaty.kc(ukazatele['trzby'])} "
                    f"(minulý týden {formaty.kc(minule['trzby'])}).")
    vety.append(f"Provozní zisk: {formaty.kc(ukazatele['provozni_zisk'])}, "
                f"hrubá marže {formaty.procento(ukazatele['marze_pct'])}.")
    if veta_rozkladu:
        vety.append(veta_rozkladu)
    zmena_bez = _zmena(ukazatele["zisk_bez_mesicnich"], minule["zisk_bez_mesicnich"])
    vety.append("Bez pravidelných měsíčních plateb by byl provozní zisk "
                f"{formaty.kc(ukazatele['zisk_bez_mesicnich'])} "
                f"(minulý týden {formaty.kc(minule['zisk_bez_mesicnich'])}"
                + ("" if math.isnan(zmena_bez) else f", {formaty.procento(zmena_bez, znamenko=True)}") + ").")
    if not top.empty:
        vety.append(f"Nejprodávanější: {top.iloc[0]['Produkt']} ({formaty.kc(top.iloc[0]['Tržby'])}).")
    if zasoba.empty:
        vety.append("Zásoby jsou v pořádku.")
    else:
        vety.append(f"Doobjednat je potřeba {len(zasoba)} položky: {', '.join(zasoba['Produkt'])}."
                    if len(zasoba) < 5 else
                    f"Doobjednat je potřeba {len(zasoba)} položek (seznam níže).")
    if vykyvy_tab.empty:
        vety.append("Žádné nezvyklé výkyvy.")
    else:
        vety.append(f"Nezvyklé výkyvy: {len(vykyvy_tab)} (" + "; ".join(
            f"{c.lower()} – {k}" for c, k in zip(vykyvy_tab["Co"], vykyvy_tab["Kdy"])) + ").")
    return vety


def spocitej_report(data: VycistenaData, od: date) -> TydenniReport:
    do = od + timedelta(days=6)
    ukazatele = spocitej_ukazatele(data, od, do)
    minule = spocitej_ukazatele(data, od - timedelta(days=7), do - timedelta(days=7))
    top = top_produkty(data, od, do)
    zasoba = nizka_zasoba(data, data.sklad_ke_dni)
    vykyvy_tab = vykyvy(data, od, do)
    rozklad, veta = rozklad_zmeny_zisku(data, od, do, ukazatele, minule)
    poznamky = [
        f"Stav skladu je z posledního exportu (k {formaty.datum(data.sklad_ke_dni)}).",
        f"Při zpracování dat bylo automaticky opraveno nebo vyřazeno {len(data.log)} záznamů "
        "– podrobnosti jsou v Excelu na listu „Úpravy dat (detail)“.",
        "Tržby i náklady jsou bez DPH. Stornované objednávky se do tržeb nepočítají.",
        "Pravidelné měsíční platby (mzdy, nájem, energie, software) se projeví v týdnu, kdy byly zaplaceny; "
        "proto report ukazuje i provozní zisk bez nich, který jde porovnat týden po týdnu.",
    ]
    return TydenniReport(
        od=od, do=do, ukazatele=ukazatele, ukazatele_minule=minule, top_produkty=top,
        nizka_zasoba=zasoba, vykyvy=vykyvy_tab, denni_trzby=denni_trzby(data, od, do),
        naklady_kategorie=naklady_podle_kategorii(data, od, do), rozklad_zisku=rozklad, veta_rozkladu=veta,
        log_souhrn=data.log.souhrn(), log_detail=data.log.tabulka(), sklad_ke_dni=data.sklad_ke_dni,
        zjisteni=hlavni_zjisteni(ukazatele, minule, top, zasoba, vykyvy_tab, veta), poznamky=poznamky,
    )


def souhrnna_tabulka(report: TydenniReport) -> pd.DataFrame:
    """Ukazatele: tento týden, minulý týden a změna (u marže v procentních bodech)."""
    radky = []
    for klic, popisek, typ in UKAZATELE:
        nove, stare = report.ukazatele[klic], report.ukazatele_minule[klic]
        zmena = (nove - stare) if typ == "pct" else _zmena(nove, stare)
        radky.append({"Ukazatel": popisek, "Tento týden": nove, "Minulý týden": stare, "Změna": zmena, "typ": typ})
    return pd.DataFrame(radky)


def formatuj_hodnotu(hodnota, typ: str) -> str:
    return {"kc": formaty.kc, "pct": formaty.procento, "ks": formaty.cislo}[typ](hodnota)


def formatuj_zmenu(hodnota, typ: str) -> str:
    if typ == "pct":
        if hodnota is None or math.isnan(hodnota):
            return "–"
        return f"{hodnota * 100:+.1f}".replace(".", ",") + f"{formaty.NBSP}p. b."
    return formaty.procento(hodnota, znamenko=True)
