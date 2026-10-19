from datetime import datetime

import pandas as pd

from report_demo.cisteni import (LogZmen, oprav_kategorii, parse_castka, parse_datum, vycisti_naklady,
                                 vycisti_objednavky, vycisti_sklad)

KODY = ["KAV-ETI-250", "KAV-BRA-250", "KAV-BRA-1000"]


def _objednavky(radky):
    sloupce = ["Číslo objednávky", "Datum", "Kód zboží", "Název zboží", "Množství", "Cena/ks", "Stav"]
    return pd.DataFrame(radky, columns=sloupce)


def _uprav(log):
    return list(log.tabulka()["Úprava"])


DATA = [
    ("3.8.2026", datetime(2026, 8, 3)),
    ("3. 8. 2026", datetime(2026, 8, 3)),
    ("2026-08-05", datetime(2026, 8, 5)),
    ("05/08/2026", datetime(2026, 8, 5)),            # český formát: den/měsíc/rok
    ("05.10.2026 14:32", datetime(2026, 10, 5, 14, 32)),
    (datetime(2026, 9, 1), datetime(2026, 9, 1)),
    (46266, datetime(2026, 9, 1)),                    # pořadové číslo dne z Excelu (1. 1. 2026 = 46023)
]
CASTKY = [
    ("1 250 Kč", 1250.0),
    ("1250,50", 1250.5),
    ("4 250,00 Kč", 4250.0),
    ("1.250,50", 1250.5),
    ("12 500 CZK", 12500.0),
    (990, 990.0),
    ("", None),
    ("neznámo", None),
]
KATEGORIE = [
    ("Doprava", "Doprava"),
    (" doprava ", "Doprava"),
    ("Dopravaa", "Doprava"),
    ("Poštovné", "Doprava"),
    ("Marketng", "Marketing"),
    ("Reklama", "Marketing"),
    ("najem", "Nájem"),
    ("Enrgie", "Energie"),
    ("SW", "Software"),
    ("Kytky do kanceláře", "Ostatní"),
    (None, "Ostatní"),
]


def test_parse_datum_zvladne_ruzne_formaty():
    for vstup, ocekavane in DATA:
        assert parse_datum(vstup) == ocekavane, vstup


def test_parse_datum_neplatne_vraci_none():
    for vstup in ["", None, "zítra", "31.2.2026", float("nan")]:
        assert parse_datum(vstup) is None, vstup


def test_parse_castka():
    for vstup, ocekavane in CASTKY:
        assert parse_castka(vstup) == ocekavane, vstup


def test_oprav_kategorii():
    for vstup, ocekavane in KATEGORIE:
        assert oprav_kategorii(vstup) == ocekavane, vstup


def test_objednavky_sjednoti_kody_a_opravi_preklepy():
    log = LogZmen()
    df = vycisti_objednavky(_objednavky([
        ["1", "05.10.2026 10:00", " kav-eti-250 ", "", "1", "289,00", "Vyřízeno"],
        ["2", "05.10.2026 11:00", "KAV-ETI-25O", "", "2", "289,00", "Vyřízeno"],
        ["3", "05.10.2026 12:00", "KAV-BRA250", "", "1", "219,00", "Vyřízeno"],
    ]), KODY, log)
    assert list(df["sku"]) == ["KAV-ETI-250", "KAV-ETI-250", "KAV-BRA-250"]
    assert _uprav(log).count("opraven překlep v kódu") == 2
    assert "sjednocen zápis kódu" in _uprav(log)


def test_objednavky_vyradi_duplicity_neznamy_kod_a_chybejici_mnozstvi():
    log = LogZmen()
    radek = ["1", "05.10.2026 10:00", "KAV-ETI-250", "", "1", "289,00", "Vyřízeno"]
    df = vycisti_objednavky(_objednavky([
        radek,
        list(radek),                                                         # duplicita z exportu
        ["2", "05.10.2026 11:00", "XYZ-999", "", "1", "100,00", "Vyřízeno"],  # neznámý kód
        ["3", "05.10.2026 12:00", "KAV-BRA-250", "", "", "219,00", "Vyřízeno"],
    ]), KODY, log)
    assert len(df) == 1
    tab = log.tabulka()
    assert set(tab["Úprava"]) == {"duplicitní řádek – vyřazen", "neznámý kód zboží – řádek vyřazen",
                                  "chybí množství – řádek vyřazen"}
    assert list(tab["Řádek v souboru"]) == [3, 4, 5]   # čísla řádků tak, jak je vidí uživatel


def test_objednavky_sjednoti_stav_a_spocita_trzbu():
    log = LogZmen()
    df = vycisti_objednavky(_objednavky([
        ["1", "05.10.2026 10:00", "KAV-ETI-250", "", "2", "289,00", "VYRIZENO"],
        ["2", "2026-10-05 11:00:00", "KAV-ETI-250", "", "1", "289,00", "storno"],
    ]), KODY, log)
    assert list(df["stav"]) == ["Vyřízeno", "Stornováno"]
    assert df["trzba"].tolist() == [578.0, 289.0]
    assert df["den"].tolist() == [pd.Timestamp("2026-10-05")] * 2


def test_naklady_vyradi_prazdne_radky_mezisoucty_a_duplicity():
    log = LogZmen()
    surova = pd.DataFrame([
        [datetime(2026, 8, 4), "Doprava", "Svoz", 4200, 5],
        [None, None, None, None, 6],
        ["5.8.2026", "Marketng", "Reklama", "5 000 Kč", 7],
        ["5.8.2026", "marketing", "Reklama", 5000, 8],                 # stejná položka podruhé
        ["", "", "Celkem srpen", 14200, 9],
        ["neznámé", "Obaly", "Krabice", 100, 10],
    ], columns=["Datum", "Kategorie ", "Popis", "Částka", "radek"])
    df = vycisti_naklady(surova, log)
    assert len(df) == 2
    assert df["castka"].sum() == 9200
    assert set(df["kategorie"]) == {"Doprava", "Marketing"}
    uprav = _uprav(log)
    for ocekavana in ["prázdný řádek – vyřazen", "duplicitní záznam – vyřazen", "opravena kategorie",
                      "mezisoučet – vyřazen, aby se náklady nepočítaly dvakrát", "datum převedeno z textu",
                      "částka převedena z textu", "neplatné datum – řádek vyřazen"]:
        assert ocekavana in uprav
    assert log.tabulka().loc[log.tabulka()["Úprava"] == "prázdný řádek – vyřazen", "Řádek v souboru"].item() == 6


def test_sklad_opravi_zaporny_stav_chybejici_minimum_a_duplicitu():
    log = LogZmen()
    surova = pd.DataFrame([
        [" kav-eti-250", "Etiopie", "50", "80", "150"],
        ["KAV-BRA-250", "Brazílie", "-2", "", "110"],
        ["KAV-ETI-250", "Etiopie", "60", "80", "135,50"],     # novější řádek téhož kódu
    ], columns=["sku", "nazev", "skladem_ks", "min_zasoba", "nakupni_cena"])
    df = vycisti_sklad(surova, log).set_index("sku")
    assert list(df.index) == ["KAV-ETI-250", "KAV-BRA-250"]
    assert df.loc["KAV-ETI-250", "skladem"] == 60
    assert df.loc["KAV-ETI-250", "nakupni_cena"] == 135.5
    assert df.loc["KAV-BRA-250", "skladem"] == 0
    assert df.loc["KAV-BRA-250", "min_zasoba"] == 10
    assert len(log) == 4


def test_souhrn_logu_seskupi_upravy():
    log = LogZmen()
    for radek in (2, 3, 4):
        log.zapis("Objednávky", radek, "Stav", "vyrizeno", "Vyřízeno", "sjednocen zápis stavu")
    log.zapis("Sklad", 2, "sku", "a", "A", "sjednocen zápis kódu")
    souhrn = log.souhrn()
    assert souhrn["Počet"].tolist() == [3, 1]
