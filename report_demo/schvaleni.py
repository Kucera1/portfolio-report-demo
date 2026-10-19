"""Schvalovací krok: report se nejdřív uloží jako NÁVRH a odejde až po schválení.

Odeslání je v ukázce simulované – soubory se jen zkopírují do složky
„odeslano/“ a vedle nich se uloží text zprávy, která by šla vedení.
Bez zavolání `schval_a_odesli` se do „odeslano/“ nic nezapíše.
"""

import csv
import json
import shutil
from datetime import datetime
from pathlib import Path

from . import formaty
from .export import export_excel, export_pdf, nazev_souboru
from .report import TydenniReport

STAV_NAVRH = "návrh"
STAV_ODESLANO = "odesláno"
STAV_ZAHOZENO = "zahozeno"
SOUBOR_STAVU = "navrh.json"
DENIK_ODESLANI = "odeslane_reporty.csv"
PRIJEMCE = "vedení firmy (simulace – nic se skutečně neodesílá)"


def _nacti(slozka: Path) -> dict:
    return json.loads((Path(slozka) / SOUBOR_STAVU).read_text(encoding="utf-8"))


def _uloz(slozka: Path, stav: dict) -> None:
    (Path(slozka) / SOUBOR_STAVU).write_text(json.dumps(stav, ensure_ascii=False, indent=2), encoding="utf-8")


def nacti_stav(slozka_navrhu: Path) -> dict:
    return _nacti(slozka_navrhu)


def uloz_navrh(report: TydenniReport, slozka_navrhu: Path, ted: datetime | None = None) -> Path:
    """Vytvoří složku s návrhem (Excel + PDF + stav). Nic neodesílá."""
    ted = ted or datetime.now()
    rok, tyden, _ = report.od.isocalendar()
    zaklad = f"report_{rok}-T{tyden:02d}_{ted:%Y%m%d-%H%M%S}"
    slozka = Path(slozka_navrhu) / zaklad
    poradi = 2
    while slozka.exists():
        slozka = Path(slozka_navrhu) / f"{zaklad}-{poradi}"
        poradi += 1
    slozka.mkdir(parents=True)
    excel = export_excel(report, slozka / nazev_souboru(report, "xlsx"))
    pdf = export_pdf(report, slozka / nazev_souboru(report, "pdf"))
    _uloz(slozka, {
        "id": slozka.name,
        "tyden": formaty.popis_tydne(report.od),
        "stav": STAV_NAVRH,
        "vytvoreno": ted.isoformat(timespec="seconds"),
        "soubory": [excel.name, pdf.name],
        "zprava": text_zpravy(report),
    })
    return slozka


def text_zpravy(report: TydenniReport) -> str:
    rok, tyden, _ = report.od.isocalendar()
    radky = [
        f"Komu: {PRIJEMCE}",
        f"Předmět: Týdenní report – týden {tyden}/{rok}",
        "",
        "Dobrý den,",
        "",
        f"posílám týdenní report za týden {tyden}/{rok} "
        f"({formaty.datum(report.od)} – {formaty.datum(report.do)}).",
        "",
        *[f"- {veta}" for veta in report.zjisteni],
        "",
        "Podrobnosti jsou v přiloženém PDF, čísla pro další práci v Excelu.",
    ]
    return "\n".join(radky)


def schval_a_odesli(slozka_navrhu: Path, slozka_odeslano: Path, ted: datetime | None = None) -> Path:
    """Schválí návrh a (simulovaně) ho odešle. Návrh lze odeslat jen jednou."""
    slozka_navrhu = Path(slozka_navrhu)
    stav = _nacti(slozka_navrhu)
    if stav["stav"] != STAV_NAVRH:
        raise ValueError(f"Report nelze odeslat – jeho stav je „{stav['stav']}“.")
    ted = ted or datetime.now()
    cil = Path(slozka_odeslano) / stav["id"]
    cil.mkdir(parents=True, exist_ok=False)
    for soubor in stav["soubory"]:
        shutil.copy2(slozka_navrhu / soubor, cil / soubor)
    (cil / "zprava.txt").write_text(
        "SIMULACE ODESLÁNÍ – v ukázce se nic skutečně neodesílá.\n"
        f"Schváleno a odesláno: {formaty.datum(ted)} {ted:%H:%M}\n\n{stav['zprava']}\n\n"
        f"Přílohy: {', '.join(stav['soubory'])}\n",
        encoding="utf-8",
    )
    denik = Path(slozka_odeslano) / DENIK_ODESLANI
    novy = not denik.exists()
    with open(denik, "a", newline="", encoding="utf-8-sig") as f:
        zapis = csv.writer(f, delimiter=";")
        if novy:
            zapis.writerow(["Odesláno", "Report", "Týden", "Příjemce"])
        zapis.writerow([ted.isoformat(timespec="seconds"), stav["id"], stav["tyden"], PRIJEMCE])
    stav.update({"stav": STAV_ODESLANO, "odeslano": ted.isoformat(timespec="seconds"), "slozka_odeslani": cil.name})
    _uloz(slozka_navrhu, stav)
    return cil


def zahod_navrh(slozka_navrhu: Path) -> None:
    """Návrh se neodešle; soubory zůstávají pro kontrolu."""
    stav = _nacti(slozka_navrhu)
    if stav["stav"] != STAV_NAVRH:
        raise ValueError(f"Návrh nelze zahodit – jeho stav je „{stav['stav']}“.")
    stav["stav"] = STAV_ZAHOZENO
    _uloz(slozka_navrhu, stav)
