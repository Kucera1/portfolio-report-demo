"""Výpočty na malých ručně sestavených datech, kde jde výsledek spočítat z hlavy."""

import math
from datetime import date, timedelta

import pandas as pd
import pytest

from report_demo import formaty
from report_demo.cisteni import LogZmen
from report_demo.nacitani import VycistenaData
from report_demo.report import (dostupne_tydny, nizka_zasoba, rozklad_zmeny_zisku, souhrnna_tabulka,
                                spocitej_report, spocitej_ukazatele, top_produkty, vykyvy)

PONDELI = date(2026, 10, 5)


def _sklad():
    return pd.DataFrame([
        ["A", "Káva A", 100, 10, 60.0],
        ["B", "Káva B", 5, 10, 40.0],
        ["C", "Mlýnek", 50, 5, 500.0],
    ], columns=["sku", "nazev", "skladem", "min_zasoba", "nakupni_cena"])


def _objednavky(radky):
    df = pd.DataFrame(radky, columns=["cislo", "datum", "sku", "mnozstvi", "cena", "stav"])
    df["datum"] = pd.to_datetime(df["datum"])
    df["den"] = df["datum"].dt.normalize()
    df["trzba"] = df["mnozstvi"] * df["cena"]
    return df


def _naklady(radky):
    df = pd.DataFrame(radky, columns=["datum", "kategorie", "popis", "castka"])
    df["datum"] = pd.to_datetime(df["datum"])
    return df


def _data(objednavky, naklady=None, ke_dni=PONDELI + timedelta(days=6)):
    naklady = naklady if naklady is not None else _naklady([])
    return VycistenaData(objednavky, naklady, _sklad(), LogZmen(), ke_dni)


def test_ukazatele_trzby_marze_a_zisk():
    obj = _objednavky([
        ["1", "2026-10-05 10:00", "A", 2, 100.0, "Vyřízeno"],
        ["1", "2026-10-05 10:00", "B", 1, 80.0, "Vyřízeno"],
        ["2", "2026-10-07 12:00", "A", 1, 100.0, "Vyřízeno"],
        ["3", "2026-10-08 12:00", "C", 1, 900.0, "Stornováno"],   # storno se nepočítá
        ["4", "2026-10-12 09:00", "A", 5, 100.0, "Vyřízeno"],     # už další týden
    ])
    nakl = _naklady([["2026-10-06", "Doprava", "Svoz", 50.0], ["2026-10-13", "Doprava", "Svoz", 999.0]])
    u = spocitej_ukazatele(_data(obj, nakl), PONDELI, PONDELI + timedelta(days=6))
    assert u["trzby"] == 380
    assert u["naklady_zbozi"] == 3 * 60 + 40
    assert u["hruba_marze"] == 160
    assert u["marze_pct"] == pytest.approx(160 / 380)
    assert u["provozni_naklady"] == 50
    assert u["provozni_zisk"] == 110
    assert u["pocet_objednavek"] == 2
    assert u["prumerna_objednavka"] == 190
    assert u["stornovane"] == 1


def test_prazdny_tyden_nedeli_nulou():
    u = spocitej_ukazatele(_data(_objednavky([])), PONDELI, PONDELI + timedelta(days=6))
    assert u["trzby"] == 0
    assert math.isnan(u["marze_pct"])
    assert math.isnan(u["prumerna_objednavka"])


def test_top_produkty_poradi_podil_a_zmena():
    obj = _objednavky([
        ["1", "2026-09-28 10:00", "A", 1, 100.0, "Vyřízeno"],     # minulý týden
        ["2", "2026-10-05 10:00", "A", 2, 100.0, "Vyřízeno"],
        ["3", "2026-10-06 10:00", "C", 1, 600.0, "Vyřízeno"],
        ["4", "2026-10-06 11:00", "B", 1, 200.0, "Vyřízeno"],
    ])
    top = top_produkty(_data(obj), PONDELI, PONDELI + timedelta(days=6), pocet=2)
    assert top["Kód"].tolist() == ["C", "A"]
    assert top["Podíl na tržbách"].tolist() == pytest.approx([0.6, 0.2])
    assert math.isnan(top["Změna proti minulému týdnu"].iloc[0])   # C minulý týden neprodáno
    assert top["Změna proti minulému týdnu"].iloc[1] == pytest.approx(1.0)


def test_nizka_zasoba_pod_minimem_i_rychle_dochazejici():
    ke_dni = date(2026, 10, 11)
    # A: prodá se 28 × 3 ks za 4 týdny = 3 ks/den, 100 ks vystačí na 33 dní -> v pořádku
    # C – 2 ks/den, 50 ks vystačí na 25 dní -> v pořádku; B: 5 ks < minimum 10 -> doobjednat
    radky = []
    for i in range(28):
        den = (ke_dni - timedelta(days=i)).isoformat()
        radky += [[f"a{i}", den, "A", 3, 100.0, "Vyřízeno"], [f"c{i}", den, "C", 2, 900.0, "Vyřízeno"]]
    zasoba = nizka_zasoba(_data(_objednavky(radky)), ke_dni)
    assert zasoba["Kód"].tolist() == ["B"]
    assert zasoba["Doporučeno objednat ks"].tolist() == [5]       # doplnit do minima 10

    radky += [[f"x{i}", (ke_dni - timedelta(days=i)).isoformat(), "A", 1, 100.0, "Vyřízeno"] for i in range(28)]
    zasoba = nizka_zasoba(_data(_objednavky(radky)), ke_dni)        # A teď 4 ks/den -> 25 dní, stále OK
    assert "A" not in zasoba["Kód"].tolist()


def test_vykyvy_najdou_spicku_propad_i_drahy_tyden_nakladu():
    radky = []
    for tyden in range(5):
        for den in range(7):
            d = date(2026, 9, 7) + timedelta(days=7 * tyden + den)
            radky.append([f"{tyden}-{den}", f"{d.isoformat()} 10:00", "A", 10, 100.0, "Vyřízeno"])
    obj = _objednavky(radky)
    obj.loc[obj["den"] == pd.Timestamp("2026-10-06"), "trzba"] = 200.0          # propad
    obj.loc[obj["den"] == pd.Timestamp("2026-10-08"), "trzba"] = 3500.0         # špička
    naklady = _naklady(
        [[(date(2026, 9, 10) + timedelta(days=7 * k)).isoformat(), "Marketing", "Reklama", 5000.0] for k in range(5)]
        + [["2026-10-07", "Marketing", "Kampaň", 22000.0], ["2026-10-01", "Nájem", "Nájem", 32000.0]]
    )
    tab = vykyvy(_data(obj, naklady), PONDELI, PONDELI + timedelta(days=6))
    assert tab["Co"].tolist() == ["Tržby nezvykle nízké", "Tržby nezvykle vysoké",
                                  "Náklady nezvykle vysoké: Marketing"]
    assert tab["Kdy"].tolist()[:2] == ["út 6. 10.", "čt 8. 10."]
    assert "Kampaň" in tab["Poznámka"].iloc[2]


def test_dostupne_tydny_jen_cele_tydny_od_nejnovejsiho():
    obj = _objednavky([
        ["1", "2026-09-30 10:00", "A", 1, 100.0, "Vyřízeno"],   # středa – neúplný týden
        ["2", "2026-10-18 10:00", "A", 1, 100.0, "Vyřízeno"],   # neděle
    ])
    assert dostupne_tydny(obj) == [date(2026, 10, 12), date(2026, 10, 5)]


def test_celý_report_a_souhrnna_tabulka():
    obj = _objednavky([
        ["1", "2026-09-29 10:00", "A", 1, 100.0, "Vyřízeno"],
        ["2", "2026-10-06 10:00", "A", 2, 100.0, "Vyřízeno"],
    ])
    report = spocitej_report(_data(obj), PONDELI)
    souhrn = souhrnna_tabulka(report).set_index("Ukazatel")
    assert souhrn.loc["Tržby (bez DPH)", "Změna"] == pytest.approx(1.0)
    assert souhrn.loc["Hrubá marže v %", "Změna"] == pytest.approx(0.0)    # rozdíl v p. b.
    assert report.zjisteni[0].startswith("Tržby vzrostly o 100,0")


def _dva_tydny_s_mesicnimi_platbami():
    """Minulý týden nájem a běžný marketing, tento týden mzdy + software a drahá kampaň.
    Tržby i marže jsou v obou týdnech stejné, takže změnu zisku dělají jen náklady."""
    obj = _objednavky([
        ["1", "2026-09-29 10:00", "A", 10, 100.0, "Vyřízeno"],
        ["2", "2026-10-06 10:00", "A", 10, 100.0, "Vyřízeno"],
    ])
    naklady = _naklady([
        ["2026-10-01", "Nájem", "Nájem", 32000.0],
        ["2026-10-01", "Marketing", "Reklama", 5000.0],
        ["2026-10-02", "Doprava", "Svoz", 1000.0],
        ["2026-10-05", "Software", "Předplatné", 1490.0],
        ["2026-10-07", "Marketing", "Kampaň", 27000.0],
        ["2026-10-09", "Doprava", "Svoz", 1000.0],
        ["2026-10-10", "Mzdy", "Mzdy", 58000.0],
    ])
    return _data(obj, naklady)


def test_mesicni_platby_jsou_oddelene_od_ostatnich_nakladu():
    data = _dva_tydny_s_mesicnimi_platbami()
    u = spocitej_ukazatele(data, PONDELI, PONDELI + timedelta(days=6))
    assert u["provozni_naklady"] == 1490 + 27000 + 1000 + 58000
    assert u["mesicni_platby"] == 58000 + 1490
    assert u["ostatni_provozni"] == 27000 + 1000
    assert u["provozni_zisk"] == 400 - 87490                  # hrubá marže 10 × (100 - 60) = 400
    assert u["zisk_bez_mesicnich"] == 400 - 28000


def test_rozklad_zmeny_zisku_na_mesicni_platby_marketing_a_zbytek():
    data = _dva_tydny_s_mesicnimi_platbami()
    od, do = PONDELI, PONDELI + timedelta(days=6)
    tento = spocitej_ukazatele(data, od, do)
    minule = spocitej_ukazatele(data, od - timedelta(days=7), do - timedelta(days=7))
    tabulka, veta = rozklad_zmeny_zisku(data, od, do, tento, minule)
    dopady = dict(zip(tabulka["Vliv"], tabulka["Dopad na zisk"]))
    assert dopady["Pravidelné měsíční platby"] == -(59490 - 32000)
    assert dopady["Marketing"] == -(27000 - 5000)
    assert dopady["Ostatní vlivy (hrubá marže, doprava, obaly…)"] == 0
    assert dopady["Změna provozního zisku celkem"] == tento["provozni_zisk"] - minule["provozni_zisk"]
    assert veta.startswith("Pokles provozního zisku o 49\u00a0490\u00a0Kč")
    assert "mzdy 58\u00a0000\u00a0Kč, software 1\u00a0490\u00a0Kč" in veta
    assert "minulý týden nájem 32\u00a0000\u00a0Kč" in veta


def test_report_obsahuje_vetu_o_rozkladu_a_zisk_bez_mesicnich_plateb():
    report = spocitej_report(_dva_tydny_s_mesicnimi_platbami(), PONDELI)
    assert report.veta_rozkladu in report.zjisteni
    assert any(v.startswith("Bez pravidelných měsíčních plateb by byl provozní zisk") for v in report.zjisteni)
    souhrn = souhrnna_tabulka(report).set_index("Ukazatel")
    assert souhrn.loc["z toho pravidelné měsíční platby", "Tento týden"] == 59490
    assert souhrn.loc["Provozní zisk bez měsíčních plateb", "Minulý týden"] == 400 - 6000
    typy = dict(zip(report.naklady_kategorie["Kategorie"], report.naklady_kategorie["Typ"]))
    assert typy["Mzdy"] == "pravidelná měsíční platba" and typy["Marketing"] == "ostatní provozní"


def test_ceske_formaty():
    assert formaty.kc(1234567.4) == "1 234 567 Kč"
    assert formaty.procento(0.125) == "12,5 %"
    assert formaty.procento(-0.05, znamenko=True) == "-5,0 %"
    assert formaty.datum(date(2026, 10, 5)) == "5. 10. 2026"
    assert formaty.popis_tydne(PONDELI) == "Týden 41/2026 (5. 10. 2026 – 11. 10. 2026)"
    assert formaty.kc(float("nan")) == "–"
    assert formaty.kc_znamenko(8805) == "+8\u00a0805\u00a0Kč"
    assert formaty.kc_znamenko(-27490) == "-27\u00a0490\u00a0Kč"
