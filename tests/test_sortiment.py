"""Co se prodává nejvíc a nejméně: rychlost prodeje, zásoba, prostor pro slevu a pravidla návrhů."""

import math
from datetime import date, timedelta

import pandas as pd
import pytest

from report_demo.cisteni import LogZmen, vycisti_sklad
from report_demo.generator import vygeneruj_vse
from report_demo.nacitani import nacti_a_vycisti
from report_demo.sortiment import (NASTAVENI, NAVRH_BALICEK, NAVRH_SLEVA, NAVRH_VYRAZENI, SLOUPEC_NAVRHU,
                                   analyzuj_sortiment, navrh, partner_balicku, prepocet_slevy, prostor_pro_slevu,
                                   rychlost_prodeje, zasoba_na_tydny, zisk_na_kus)

KE_DNI = date(2026, 10, 11)


def _objednavky(radky):
    df = pd.DataFrame(radky, columns=["cislo", "datum", "sku", "mnozstvi", "cena", "stav"])
    df["datum"] = pd.to_datetime(df["datum"])
    df["den"] = df["datum"].dt.normalize()
    df["trzba"] = df["mnozstvi"] * df["cena"]
    return df


def test_rychlost_prodeje_a_zasoba_na_tydny():
    assert rychlost_prodeje(16, 8) == 2
    assert rychlost_prodeje(5, 0) == 0
    assert zasoba_na_tydny(20, 2) == 10
    assert zasoba_na_tydny(0, 2) == 0                 # nulová zásoba
    assert zasoba_na_tydny(0, 0) == 0                 # nulová zásoba i prodej
    assert math.isinf(zasoba_na_tydny(30, 0))         # nulový prodej -> zásoba „nevydrží nikdy dojít“


def test_zisk_a_prostor_pro_slevu():
    assert zisk_na_kus(100, 50, 10, platebni_poplatek=0.02) == pytest.approx(38)
    assert prostor_pro_slevu(100, 50, 10, platebni_poplatek=0) == pytest.approx(0.4)
    # Při slevě přesně o prostor je zisk nulový, o kousek víc už je ztráta.
    prostor = prostor_pro_slevu(249, 110, 25)
    assert prepocet_slevy(249, 110, 25, prostor)["zisk_na_kus"] == pytest.approx(0, abs=1e-9)
    assert not prepocet_slevy(249, 110, 25, prostor - 0.001)["ve_ztrate"]
    assert prepocet_slevy(249, 110, 25, prostor + 0.001)["ve_ztrate"]


def test_prostor_pro_slevu_hranicni_pripady():
    assert prostor_pro_slevu(100, 120, 0) == 0        # už plná cena je ve ztrátě
    assert math.isnan(prostor_pro_slevu(math.nan, 50, 5))
    assert math.isnan(prostor_pro_slevu(0, 50, 5))


def test_kalkulacka_slevy():
    vysledek = prepocet_slevy(200, 100, 10, 0.25, platebni_poplatek=0)
    assert vysledek["nova_cena"] == 150
    assert vysledek["zisk_na_kus"] == 40
    assert vysledek["marze"] == pytest.approx(40 / 150)
    assert not vysledek["ve_ztrate"]
    uplna = prepocet_slevy(200, 100, 10, 1.0, platebni_poplatek=0)
    assert uplna["nova_cena"] == 0 and uplna["ve_ztrate"] and math.isnan(uplna["marze"])


def test_pravidla_navrhu():
    hranice = NASTAVENI["dostatecna_marze"]
    malo = NASTAVENI["temer_zadny_prodej_ks"]
    assert navrh(0, 0.10, None)[0] == NAVRH_VYRAZENI            # téměř žádný prodej + nízká marže
    assert navrh(malo, hranice - 0.01, "Dripper")[0] == NAVRH_VYRAZENI   # vyřazení má přednost před balíčkem
    assert navrh(10, 0.10, "Dripper")[0] == f"{NAVRH_BALICEK} s produktem Dripper"
    assert navrh(0, 0.50, None)[0] == NAVRH_SLEVA               # téměř žádný prodej, ale dobrá marže
    assert navrh(50, hranice, None)[0] == NAVRH_SLEVA           # marže přesně na hranici stačí
    assert navrh(50, hranice - 0.01, None)[0] == NAVRH_VYRAZENI  # pomalý prodej, nízká marže
    assert navrh(malo + 1, math.nan, None)[0] == NAVRH_VYRAZENI  # neznámá marže se bere jako nízká


def test_navrhy_jsou_bez_cisel_a_procent():
    for prodano, marze, partner in [(0, 0.1, None), (10, 0.1, "Dripper"), (0, 0.5, None), (50, 0.1, None)]:
        # (název produktu v balíčku může číslice obsahovat, samotný návrh ne)
        for text in navrh(prodano, marze, partner):
            assert not any(znak.isdigit() for znak in text) and "%" not in text, text


def test_partner_balicku():
    nazvy = pd.Series({"A": "Dripper", "B": "Filtry", "S": "Šálek"})
    radky = []
    for i in range(1, 5):                    # šálek ve 4 objednávkách, 3× s dripperem
        radky.append([f"o{i}", "2026-10-01 10:00", "S", 1, 249.0, "Vyřízeno"])
        radky.append([f"o{i}", "2026-10-01 10:00", "A" if i <= 3 else "B", 1, 549.0, "Vyřízeno"])
    obj = _objednavky(radky)
    assert partner_balicku(obj, "S", nazvy) == "Dripper"
    assert partner_balicku(obj, "S", nazvy, NASTAVENI | {"balicek_min_objednavek": 4}) is None
    assert partner_balicku(obj, "S", nazvy, NASTAVENI | {"balicek_min_podil": 0.8}) is None
    assert partner_balicku(obj, "X", nazvy) is None          # zboží bez objednávek
    samotny = _objednavky([["o9", "2026-10-01 10:00", "S", 1, 249.0, "Vyřízeno"]])
    assert partner_balicku(samotny, "S", nazvy) is None       # kupuje se jen samostatně


def test_analyza_sortimentu_na_malych_datech():
    sklad = pd.DataFrame([
        ["A", "Rychlá káva", 40, 10, 100.0],
        ["B", "Předzásobená káva", 500, 10, 100.0],
        ["C", "Neprodávaný sirup", 30, 5, 150.0],
        ["D", "Vyprodaný mlýnek", 0, 2, 600.0],
    ], columns=["sku", "nazev", "skladem", "min_zasoba", "nakupni_cena"])   # bez ceny a poplatků
    radky = []
    for tyden in range(8):
        den = (KE_DNI - timedelta(days=7 * tyden)).isoformat()
        radky += [[f"a{tyden}", f"{den} 10:00", "A", 10, 250.0, "Vyřízeno"],
                  [f"b{tyden}", f"{den} 11:00", "B", 4, 300.0, "Vyřízeno"]]
    radky.append(["c0", "2026-07-01 10:00", "C", 1, 180.0, "Vyřízeno"])   # mimo sledované období
    radky.append(["x", f"{KE_DNI.isoformat()} 12:00", "A", 99, 250.0, "Stornováno"])
    vysledek = analyzuj_sortiment(_objednavky(radky), sklad, KE_DNI)

    assert vysledek.od == KE_DNI - timedelta(days=55)
    assert vysledek.nejprodavanejsi["Kód"].tolist() == ["A", "B"]
    assert vysledek.nejprodavanejsi["Prodáno ks"].tolist() == [80, 32]      # storno se nepočítá
    prehled = vysledek.prehled.set_index("Kód")
    assert prehled.loc["A", "Prodej za týden (ks)"] == 10
    assert prehled.loc["B", "Zásoba vydrží (týdnů)"] == 125
    assert prehled.loc["B", "Běžná cena"] == 300                             # cena z objednávek
    assert prehled.loc["B", "Náklady na kus"] == 0
    assert prehled.loc["D", "Zásoba vydrží (týdnů)"] == 0
    pomale = vysledek.pomale.set_index("Kód")
    assert set(pomale.index) == {"B", "C"}                                   # vyprodané D tam není
    assert math.isinf(pomale.loc["C", "Zásoba vydrží (týdnů)"])
    assert pomale.loc["B", SLOUPEC_NAVRHU] == NAVRH_SLEVA
    assert pomale.loc["C", SLOUPEC_NAVRHU] == NAVRH_VYRAZENI                 # marže 180 vs 150 je nízká
    assert any("rozhoduje majitel" in veta for veta in vysledek.poznamky)


def test_sklad_cte_prodejni_cenu_a_naklady_na_kus():
    log = LogZmen()
    surova = pd.DataFrame([
        ["A", "Káva", "10", "5", "100", "250", "12"],
        ["B", "Šálek", "5", "2", "110", "", ""],
    ], columns=["sku", "nazev", "skladem_ks", "min_zasoba", "nakupni_cena", "prodejni_cena", "poplatek_ks"])
    df = vycisti_sklad(surova, log).set_index("sku")
    assert df.loc["A", "prodejni_cena"] == 250 and df.loc["A", "poplatek_ks"] == 12
    assert math.isnan(df.loc["B", "prodejni_cena"]) and df.loc["B", "poplatek_ks"] == 0
    assert set(log.tabulka()["Úprava"]) == {"chybí prodejní cena – použije se cena z objednávek",
                                            "chybí náklady na kus – počítá se s nulou"}


def test_sortiment_na_syntetickych_datech(tmp_path):
    data = nacti_a_vycisti(vygeneruj_vse(tmp_path / "vstupy"))
    vysledek = analyzuj_sortiment(data.objednavky, data.sklad, data.sklad_ke_dni)
    navrhy = dict(zip(vysledek.pomale["Kód"], vysledek.pomale[SLOUPEC_NAVRHU]))
    assert navrhy["PRI-SAL-200"] == f"{NAVRH_BALICEK} s produktem Dripper V60 keramický"
    assert navrhy["PRI-SIR-KAR"] == NAVRH_VYRAZENI
    assert navrhy["PRI-KRA-DAR"] == NAVRH_SLEVA
    assert navrhy["KAV-KEN-250"] == NAVRH_SLEVA
    assert "KAV-ETI-250" in set(vysledek.nejprodavanejsi["Kód"])
    assert (vysledek.prehled["Prostor pro slevu"] >= 0).all()
