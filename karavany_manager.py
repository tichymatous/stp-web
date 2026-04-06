#!/usr/bin/env python3
"""
Interaktivní správce rezervací karavanů uložených v souboru:

    data/karavany-availability.json

Funkce:
- Přidání rezervace se stavem "reserved" nebo "tentative"
- Smazání existující rezervace
- Založení nové sezóny s archivací předchozí
- Zobrazení aktuálních rezervací

Důležité pravidlo pro datumy:
Rezervace se vyhodnocují jako polootevřené intervaly [od, do).

To znamená, že bez konfliktu může:
- jedna rezervace končit 2026-07-07
- a jiná rezervace začínat 2026-07-07

Blokují se tedy jen skutečné překryvy.

Ovládání při zadávání:
- napište "zpet" pro návrat o jeden krok zpět
- napište "menu" pro návrat do hlavního menu
"""

from __future__ import annotations

import copy
import json
import sys
import os
import unicodedata
from datetime import date, datetime
from pathlib import Path
from typing import Any


DATA_PATH = Path(__file__).resolve().parent / "data" / "karavany-availability.json"
VALID_STATUSES = {"reserved", "tentative"}
STATUS_LABELS = {
    "reserved": "rezervováno",
    "tentative": "předběžně",
}
YES_VALUES = {"a", "ano", "y", "yes"}
BACK = "__BACK__"
MENU = "__MENU__"
BACK_VALUES = {"zpet", "zpět", "back"}
MENU_VALUES = {"menu", "hlavni menu", "hlavní menu", "hlavni", "hlavní"}

def clear_screen() -> None:
    os.system("cls" if os.name == "nt" else "clear")

def today_iso() -> str:
    return date.today().isoformat()


def normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value.strip().lower())
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"Neplatné datum '{value}'. Použijte formát RRRR-MM-DD.") from exc


def parse_month(value: str) -> str:
    try:
        dt = datetime.strptime(value, "%Y-%m")
    except ValueError as exc:
        raise ValueError(f"Neplatný měsíc '{value}'. Použijte formát RRRR-MM.") from exc
    return dt.strftime("%Y-%m")


def month_start(year: int, month: int) -> date:
    return date(year, month, 1)


def add_month(year: int, month: int) -> tuple[int, int]:
    if month == 12:
        return year + 1, 1
    return year, month + 1


def generate_months(start_str: str, end_str: str) -> list[str]:
    start = parse_date(start_str)
    end = parse_date(end_str)
    months: list[str] = []

    year = start.year
    month = start.month

    while True:
        current = month_start(year, month)
        if current > end:
            break
        months.append(current.strftime("%Y-%m"))
        year, month = add_month(year, month)

    return months


def load_data(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"JSON soubor nebyl nalezen: {path}")

    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    validate_data_shape(data)
    return data


def validate_data_shape(data: dict[str, Any]) -> None:
    required_top_keys = {"meta", "caravans", "months", "availability", "archive"}
    missing = required_top_keys - set(data.keys())
    if missing:
        raise ValueError(f"V JSON chybí klíče nejvyšší úrovně: {', '.join(sorted(missing))}")

    meta = data["meta"]
    for key in ("seasonStart", "seasonEnd", "lastUpdated"):
        if key not in meta:
            raise ValueError(f"V JSON chybí meta.{key}.")

    parse_date(meta["seasonStart"])
    parse_date(meta["seasonEnd"])
    parse_date(meta["lastUpdated"])

    if not isinstance(data["caravans"], list):
        raise ValueError("'caravans' musí být seznam.")
    if not isinstance(data["months"], list):
        raise ValueError("'months' musí být seznam.")
    if not isinstance(data["availability"], dict):
        raise ValueError("'availability' musí být objekt.")
    if not isinstance(data["archive"], dict):
        raise ValueError("'archive' musí být objekt.")

    for caravan in data["caravans"]:
        if caravan not in data["availability"]:
            data["availability"][caravan] = []

    for caravan, reservations in data["availability"].items():
        if not isinstance(reservations, list):
            raise ValueError(f"'availability.{caravan}' musí být seznam.")
        for reservation in reservations:
            for key in ("from", "to", "status"):
                if key not in reservation:
                    raise ValueError(f"U rezervace pro karavan {caravan} chybí '{key}'.")
            start = parse_date(reservation["from"])
            end = parse_date(reservation["to"])
            if start >= end:
                raise ValueError(
                    f"Neplatná rezervace pro karavan {caravan}: "
                    f"'from' musí být dříve než 'to'."
                )
            status = reservation["status"]
            if status not in VALID_STATUSES:
                raise ValueError(
                    f"Neplatný status '{status}' u karavanu {caravan}. "
                    f"Povolené hodnoty: {', '.join(sorted(VALID_STATUSES))}"
                )


def save_data(path: Path, data: dict[str, Any]) -> None:
    data["meta"]["lastUpdated"] = today_iso()
    backup_path = create_backup(path)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
    print(f"\nZměny byly uloženy do: {path}")
    print(f"Záloha byla vytvořena zde: {backup_path}")


def create_backup(path: Path) -> Path:
    backup_dir = path.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    backup_path = backup_dir / f"{path.stem}-{timestamp}{path.suffix}"
    backup_path.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    return backup_path


def reservation_sort_key(item: dict[str, str]) -> tuple[str, str, str]:
    return (item["from"], item["to"], item["status"])


def sort_reservations(data: dict[str, Any]) -> None:
    for caravan in data["availability"]:
        data["availability"][caravan].sort(key=reservation_sort_key)


def status_to_czech(value: str) -> str:
    return STATUS_LABELS.get(value, value)


def normalize_status(value: str) -> str:
    normalized = normalize_text(value)
    aliases = {
        "reserved": "reserved",
        "rezervovano": "reserved",
        "rezervace": "reserved",
        "potvrzeno": "reserved",
        "booked": "reserved",
        "tentative": "tentative",
        "predbezne": "tentative",
        "predbezna": "tentative",
        "nezavazne": "tentative",
        "docasne": "tentative",
        "provisional": "tentative",
    }
    if normalized not in aliases:
        raise ValueError(
            "Status musí být jedna z hodnot: reserved / tentative "
            "(česky také rezervováno / předběžně)."
        )
    return aliases[normalized]


def overlaps(existing_from: date, existing_to: date, new_from: date, new_to: date) -> bool:
    # Polootevřené intervaly: [from, to)
    # Sousedící rozsahy jsou povolené:
    # - new_from == existing_to  -> bez překryvu
    # - new_to == existing_from  -> bez překryvu
    return new_from < existing_to and existing_from < new_to


def reservation_conflicts(
    reservations: list[dict[str, str]],
    new_from: date,
    new_to: date,
) -> list[dict[str, str]]:
    conflicts = []
    for reservation in reservations:
        existing_from = parse_date(reservation["from"])
        existing_to = parse_date(reservation["to"])
        if overlaps(existing_from, existing_to, new_from, new_to):
            conflicts.append(reservation)
    return conflicts


def prompt(text: str) -> str:
    return input(text).strip()


def get_special_command(value: str) -> str | None:
    normalized = normalize_text(value)
    if normalized in BACK_VALUES:
        return BACK
    if normalized in MENU_VALUES:
        return MENU
    return None


def prompt_with_navigation(text: str, allow_empty: bool = False) -> str:
    while True:
        value = prompt(text)
        special = get_special_command(value)
        if special:
            return special
        if value or allow_empty:
            return value
        print("Hodnota nesmí být prázdná. Pro návrat napište 'zpet' nebo 'menu'.")


def prompt_date_nav(text: str) -> str:
    while True:
        value = prompt_with_navigation(text)
        if value in (BACK, MENU):
            return value
        try:
            parse_date(value)
            return value
        except ValueError as exc:
            print(exc)


def prompt_status_nav() -> str:
    while True:
        value = prompt_with_navigation(
            "Status (reserved/tentative nebo rezervováno/předběžně): "
        )
        if value in (BACK, MENU):
            return value
        try:
            return normalize_status(value)
        except ValueError as exc:
            print(exc)


def is_yes(value: str) -> bool:
    return normalize_text(value) in YES_VALUES


def print_action_help() -> None:
    print("\033[90m\nNápověda: 'zpet' pro návrat o krok zpět nebo 'menu' pro hlavní menu.\033[0m")

def prompt_menu_choice() -> str:
    print("\n-----------------------------------------------")
    print("Vyberte akci:")
    print("  1) Přidat rezervaci")
    print("  2) Smazat rezervaci")
    print("  3) Zobrazit rezervace")
    print("  4) Založit novou sezónu a archivovat aktuální")
    print("  5) Konec")
    return prompt("Zadejte volbu (1-5): ")


def prompt_caravan(data: dict[str, Any]) -> str:
    caravans = data["caravans"]
    print("\nDostupné karavany:", ", ".join(caravans))
    while True:
        value = prompt_with_navigation("Vyberte karavan: ")
        if value in (BACK, MENU):
            return value
        value = value.upper()
        if value in caravans:
            return value
        print(f"Neznámý karavan '{value}'. Vyberte jednu z možností: {', '.join(caravans)}")


def print_reservations_for_caravan(data: dict[str, Any], caravan: str) -> None:
    reservations = data["availability"].get(caravan, [])
    print(f"\nRezervace pro karavan {caravan}:")
    if not reservations:
        print("  (žádné)")
        return

    for index, reservation in enumerate(sorted(reservations, key=reservation_sort_key), start=1):
        print(
            f"  {index}) {reservation['from']} -> {reservation['to']} "
            f"[{status_to_czech(reservation['status'])}]"
        )


def show_reservations(data: dict[str, Any]) -> None:
    print("\nAktuální sezóna:")
    print(f"  Začátek: {data['meta']['seasonStart']}")
    print(f"  Konec:   {data['meta']['seasonEnd']}")
    print(f"  Měsíce:  {', '.join(data['months']) if data['months'] else '(žádné)'}")

    for caravan in data["caravans"]:
        print_reservations_for_caravan(data, caravan)


def ensure_within_season(data: dict[str, Any], start_str: str, end_str: str) -> None:
    season_start = parse_date(data["meta"]["seasonStart"])
    season_end = parse_date(data["meta"]["seasonEnd"])
    reservation_start = parse_date(start_str)
    reservation_end = parse_date(end_str)

    if reservation_start < season_start:
        raise ValueError(
            f"Rezervace začíná před seasonStart ({data['meta']['seasonStart']})."
        )
    if reservation_end > season_end:
        raise ValueError(
            f"Rezervace končí po seasonEnd ({data['meta']['seasonEnd']})."
        )


def add_reservation(data: dict[str, Any]) -> bool:
    print_action_help()
    print("\nPřidání rezervace")

    step = 0
    caravan = ""
    start_str = ""
    end_str = ""
    status = ""

    while True:
        if step == 0:
            value = prompt_caravan(data)
            if value == MENU:
                print("Návrat do hlavního menu.")
                return False
            if value == BACK:
                print("Návrat do hlavního menu.")
                return False
            caravan = value
            step = 1

        elif step == 1:
            value = prompt_date_nav("Datum začátku rezervace (RRRR-MM-DD): ")
            if value == MENU:
                print("Návrat do hlavního menu.")
                return False
            if value == BACK:
                step = 0
                continue
            start_str = value
            step = 2

        elif step == 2:
            value = prompt_date_nav("Datum konce rezervace    (RRRR-MM-DD): ")
            if value == MENU:
                print("Návrat do hlavního menu.")
                return False
            if value == BACK:
                step = 1
                continue
            end_str = value
            step = 3

        elif step == 3:
            value = prompt_status_nav()
            if value == MENU:
                print("Návrat do hlavního menu.")
                return False
            if value == BACK:
                step = 2
                continue
            status = value

            start = parse_date(start_str)
            end = parse_date(end_str)

            if start >= end:
                print("Datum začátku musí být dříve než datum konce.")
                print("Vrátím vás o krok zpět na datum konce.")
                step = 2
                continue

            try:
                ensure_within_season(data, start_str, end_str)
            except ValueError as exc:
                print(exc)
                print("Vrátím vás o krok zpět na datum konce.")
                step = 2
                continue

            reservations = data["availability"].setdefault(caravan, [])
            conflicts = reservation_conflicts(reservations, start, end)

            if conflicts:
                print("\nRezervaci nelze přidat, protože se překrývá s:")
                for item in conflicts:
                    print(f"  - {item['from']} -> {item['to']} [{status_to_czech(item['status'])}]")
                print("Vrátím vás o krok zpět na datum konce.")
                step = 2
                continue

            reservations.append(
                {
                    "from": start_str,
                    "to": end_str,
                    "status": status,
                }
            )
            sort_reservations(data)
            print(
                f"\nRezervace byla přidána pro karavan {caravan}: "
                f"{start_str} -> {end_str} [{status_to_czech(status)}]"
            )
            return True


def prompt_index_nav(max_index: int) -> int | str:
    while True:
        raw = prompt_with_navigation(f"Vyberte číslo rezervace (1-{max_index}): ")
        if raw in (BACK, MENU):
            return raw
        try:
            value = int(raw)
        except ValueError:
            print("Zadejte prosím číslo.")
            continue

        if 1 <= value <= max_index:
            return value
        print(f"Číslo musí být v rozsahu 1 až {max_index}.")


def remove_reservation(data: dict[str, Any]) -> bool:
    print_action_help()
    print("\nSmazání rezervace")

    step = 0
    caravan = ""

    while True:
        if step == 0:
            value = prompt_caravan(data)
            if value == MENU:
                print("Návrat do hlavního menu.")
                return False
            if value == BACK:
                print("Jste už na prvním kroku. Návrat do hlavního menu.")
                return False
            caravan = value
            sort_reservations(data)
            step = 1

        elif step == 1:
            reservations = data["availability"].get(caravan, [])

            if not reservations:
                print(f"\nKaravan {caravan} nemá žádné rezervace ke smazání.")
                step = 0
                continue

            print_reservations_for_caravan(data, caravan)
            choice = prompt_index_nav(len(reservations))
            if choice == MENU:
                print("Návrat do hlavního menu.")
                return False
            if choice == BACK:
                step = 0
                continue

            selected = reservations[choice - 1]
            confirm = prompt_with_navigation(
                f"Smazat {selected['from']} -> {selected['to']} "
                f"[{status_to_czech(selected['status'])}]? (a/N): ",
                allow_empty=True,
            )

            if confirm == MENU:
                print("Návrat do hlavního menu.")
                return False
            if confirm == BACK:
                continue

            if not is_yes(confirm):
                print("Mazání bylo zrušeno.")
                continue

            reservations.pop(choice - 1)
            print(
                f"\nRezervace byla smazána z karavanu {caravan}: "
                f"{selected['from']} -> {selected['to']} [{status_to_czech(selected['status'])}]"
            )
            return True


def build_archive_key(start: str, end: str, archive: dict[str, Any]) -> str:
    base_key = f"{start}_to_{end}"
    key = base_key
    suffix = 2
    while key in archive:
        key = f"{base_key}_{suffix}"
        suffix += 1
    return key


def prompt_months_default(start_str: str, end_str: str) -> list[str] | str:
    suggested = generate_months(start_str, end_str)
    print("\nNavržené měsíce:", ", ".join(suggested) if suggested else "(žádné)")
    custom = prompt_with_navigation(
        "Stiskněte Enter pro použití navržených měsíců,\n"
        "nebo zadejte vlastní měsíce jako seznam RRRR-MM oddělený čárkou: ",
        allow_empty=True,
    )

    if custom in (BACK, MENU):
        return custom

    if not custom:
        return suggested

    months = []
    for item in custom.split(","):
        value = item.strip()
        if not value:
            continue
        months.append(parse_month(value))

    if not months:
        raise ValueError("Je potřeba zadat alespoň jeden platný měsíc.")
    return months


def start_new_season(data: dict[str, Any]) -> bool:
    print_action_help()
    print("\nZaložení nové sezóny")

    step = 0
    new_start = ""
    new_end = ""
    new_months: list[str] = []

    while True:
        if step == 0:
            value = prompt_date_nav("Začátek nové sezóny (RRRR-MM-DD): ")
            if value == MENU:
                print("Návrat do hlavního menu.")
                return False
            if value == BACK:
                print("Jste už na prvním kroku. Návrat do hlavního menu.")
                return False
            new_start = value
            step = 1

        elif step == 1:
            value = prompt_date_nav("Konec nové sezóny    (RRRR-MM-DD): ")
            if value == MENU:
                print("Návrat do hlavního menu.")
                return False
            if value == BACK:
                step = 0
                continue
            new_end = value

            start_date = parse_date(new_start)
            end_date = parse_date(new_end)
            if start_date >= end_date:
                print("Začátek nové sezóny musí být dříve než její konec.")
                print("Vrátím vás o krok zpět na konec sezóny.")
                continue

            step = 2

        elif step == 2:
            try:
                months_value = prompt_months_default(new_start, new_end)
            except ValueError as exc:
                print(exc)
                print("Zadejte měsíce znovu, nebo napište 'zpet' / 'menu'.")
                continue

            if months_value == MENU:
                print("Návrat do hlavního menu.")
                return False
            if months_value == BACK:
                step = 1
                continue

            new_months = months_value
            current_start = data["meta"]["seasonStart"]
            current_end = data["meta"]["seasonEnd"]
            archive_key = build_archive_key(current_start, current_end, data["archive"])

            print("\nAktuální sezóna bude archivována pod klíčem:", archive_key)
            print("Nová sezóna:")
            print(f"  Začátek: {new_start}")
            print(f"  Konec:   {new_end}")
            print(f"  Měsíce:  {', '.join(new_months)}")
            print("  Všechny aktuální rezervace budou pro novou sezónu vymazány.")

            confirm = prompt_with_navigation("Pokračovat? (a/N): ", allow_empty=True)
            if confirm == MENU:
                print("Návrat do hlavního menu.")
                return False
            if confirm == BACK:
                step = 2
                continue
            if not is_yes(confirm):
                print("Vytvoření nové sezóny bylo zrušeno.")
                return False

            snapshot = {
                "meta": copy.deepcopy(data["meta"]),
                "caravans": copy.deepcopy(data["caravans"]),
                "months": copy.deepcopy(data["months"]),
                "availability": copy.deepcopy(data["availability"]),
                "archivedAt": today_iso(),
            }
            data["archive"][archive_key] = snapshot

            data["meta"]["seasonStart"] = new_start
            data["meta"]["seasonEnd"] = new_end
            data["meta"]["lastUpdated"] = today_iso()
            data["months"] = new_months
            data["availability"] = {caravan: [] for caravan in data["caravans"]}

            print("\nNová sezóna byla vytvořena a předchozí sezóna archivována.")
            return True


def main() -> int:
    print("Správce karavanů")
    print(f"Datový soubor: {DATA_PATH}")

    try:
        data = load_data(DATA_PATH)
    except Exception as exc:
        print(f"\nChyba při načítání dat: {exc}")
        return 1

    while True:
        choice = prompt_menu_choice()

        changed = False

        if choice == "1":
            changed = add_reservation(data)
        elif choice == "2":
            changed = remove_reservation(data)
        elif choice == "3":
            show_reservations(data)
        elif choice == "4":
            changed = start_new_season(data)
        elif choice == "5":
            return 0
        else:
            print("Neplatná volba. Zadejte číslo od 1 do 5.")
            continue

        if changed:
            try:
                save_data(DATA_PATH, data)
            except Exception as exc:
                print(f"\nChyba při ukládání dat: {exc}")
                return 1


if __name__ == "__main__":
    sys.exit(main())
