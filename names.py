import json
import os
import re
import sqlite3
import sys
from pathlib import Path

# Обеспечиваем корректный вывод UTF-8 в Windows консоли
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "data" / "bot.db"
PROMPTS_DIR = BASE_DIR / "промты"
NAMES_JSON_PATH = BASE_DIR / "names.json"


def get_db_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def clean_default_name(filename: str) -> str:
    name = Path(filename).stem
    # Убираем дубли в скобках, лишние пробелы, опечатки
    name = re.sub(r"\s*\(\d+\)", "", name)
    name = re.sub(r"\(full\)", " (Full)", name, flags=re.IGNORECASE)
    name = re.sub(r"\(new\)", "", name, flags=re.IGNORECASE)
    name = name.replace("antygravity", "Antigravity").replace("antigravity", "Antigravity")
    name = re.sub(r"\s+", " ", name).strip()
    return name.title() if not name.isupper() else name


def scan_and_register_new_files() -> int:
    """Сканирует папку 'промты' и добавляет новые файлы в базу данных, если их там ещё нет."""
    if not PROMPTS_DIR.exists():
        return 0

    con = get_db_connection()
    cur = con.cursor()

    existing_files = {row["filename"]: row["id"] for row in cur.execute("SELECT filename, id FROM prompts")}
    added = 0

    for file_path in PROMPTS_DIR.glob("*.txt"):
        fname = file_path.name
        if fname not in existing_files:
            clean_title = clean_default_name(fname)
            slug_id = re.sub(r"[^a-zA-Z0-9_]+", "_", clean_title.lower()).strip("_")
            if not slug_id:
                slug_id = f"prompt_{abs(hash(fname)) % 10000}"

            cur.execute("""
                INSERT OR IGNORE INTO prompts (id, title, filename, price, description, is_active)
                VALUES (?, ?, ?, ?, ?, 1)
            """, (slug_id, clean_title, fname, 20, f"Системный промт: {clean_title}"))
            added += 1

    con.commit()
    con.close()
    return added


def get_all_prompts():
    con = get_db_connection()
    cur = con.cursor()
    rows = cur.execute("SELECT * FROM prompts ORDER BY price ASC, title ASC").fetchall()
    prompts = [dict(r) for r in rows]
    con.close()
    return prompts


def export_to_json(filepath: Path = NAMES_JSON_PATH) -> int:
    prompts = get_all_prompts()
    data = []
    for p in prompts:
        data.append({
            "id": p["id"],
            "title": p["title"],
            "price": p["price"],
            "filename": p["filename"],
            "description": p["description"],
            "is_active": p["is_active"]
        })

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    return len(data)


def import_from_json(filepath: Path = NAMES_JSON_PATH) -> int:
    if not filepath.exists():
        print(f"❌ Файл {filepath.name} не найден!")
        return 0

    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)

    con = get_db_connection()
    cur = con.cursor()
    updated = 0

    for item in data:
        fname = item.get("filename", "").strip()
        raw_id = item.get("id", "").strip().replace(" ", "_")
        title = item.get("title", "").strip()
        price = int(item.get("price", 20))
        description = item.get("description", "").strip()
        is_active = int(item.get("is_active", 1))

        # Ищем запись по имени файла или старому id
        cur.execute("SELECT id FROM prompts WHERE filename = ? OR id = ?", (fname, raw_id))
        row = cur.fetchone()

        if row:
            old_id = row["id"]
            cur.execute("""
                UPDATE prompts
                SET id = ?, title = ?, price = ?, description = ?, is_active = ?, filename = ?
                WHERE id = ?
            """, (raw_id, title, price, description, is_active, fname, old_id))
            updated += 1
        else:
            cur.execute("""
                INSERT INTO prompts (id, title, filename, price, description, is_active)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (raw_id, title, fname, price, description, is_active))
            updated += 1

    con.commit()
    con.close()
    return updated


def update_single_prompt(prompt_id: str, new_title: str = None, new_price: int = None, new_desc: str = None) -> bool:
    con = get_db_connection()
    cur = con.cursor()

    fields = []
    params = []
    if new_title is not None and new_title.strip():
        fields.append("title = ?")
        params.append(new_title.strip())
    if new_price is not None and new_price > 0:
        fields.append("price = ?")
        params.append(new_price)
    if new_desc is not None and new_desc.strip():
        fields.append("description = ?")
        params.append(new_desc.strip())

    if not fields:
        con.close()
        return False

    params.append(prompt_id)
    query = f"UPDATE prompts SET {', '.join(fields)} WHERE id = ?"
    cur.execute(query, params)
    con.commit()
    success = cur.rowcount > 0
    con.close()

    if success:
        export_to_json()
    return success


def print_menu(prompts):
    print("\n" + "=" * 70)
    print("       РЕДАКТОР НАЗВАНИЙ И ЦЕН ПРОМТОВ (White Lord IntelLab)")
    print("=" * 70)
    for idx, p in enumerate(prompts, 1):
        status = "🟢" if p["is_active"] else "🔴"
        print(f"[{idx:2d}] {status} {p['title']:<32} | {p['price']:2d} ⭐️ | файл: {p['filename']}")
    print("-" * 70)
    print("  [1-{:<2d}]  Редактировать конкретный промт в консоли".format(len(prompts)))
    print("  [E]     Экспортировать названия в 'names.json' (для правки в блокноте)")
    print("  [I]     Импортировать изменения из 'names.json' в базу бота")
    print("  [S]     Сканировать папку 'промты' на новые .txt файлы")
    print("  [Q]     Выход")
    print("=" * 70)


def interactive_mode():
    scan_and_register_new_files()
    export_to_json()

    while True:
        prompts = get_all_prompts()
        if not prompts:
            print("База данных пуста! Сначала запусти бота или проверь папку 'промты'.")
            break

        print_menu(prompts)
        try:
            choice = input("Выбери действие или номер: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nВыход.")
            break

        if not choice:
            continue

        choice_upper = choice.upper()

        if choice_upper == "Q":
            print("Завершение работы.")
            break

        elif choice_upper == "E":
            count = export_to_json()
            print(f"✅ Экспортировано {count} промтов в файл: {NAMES_JSON_PATH}")
            print(f"💡 Теперь можно открыть names.json в любом редакторе, изменить поля и нажать [I].")
            input("\nНажмите Enter для продолжения...")

        elif choice_upper == "I":
            count = import_from_json()
            print(f"✅ Успешно обновлено в базе данных: {count} промтов из names.json!")
            input("\nНажмите Enter для продолжения...")

        elif choice_upper == "S":
            added = scan_and_register_new_files()
            if added > 0:
                print(f"✅ Найдено и добавлено новых промтов: {added} шт.")
                export_to_json()
            else:
                print("ℹ️ Новых файлов в папке 'промты' не обнаружено.")
            input("\nНажмите Enter для продолжения...")

        elif choice.isdigit():
            idx = int(choice)
            if 1 <= idx <= len(prompts):
                target = prompts[idx - 1]
                print("\n" + "-" * 50)
                print(f"Редактирование промта: {target['title']}")
                print(f"Файл: {target['filename']}")
                print("-" * 50)

                print(f"Текущее название: {target['title']}")
                try:
                    new_title = input("Новое название (Enter — оставить без изменений): ").strip()
                except Exception:
                    new_title = ""

                print(f"Текущая цена: {target['price']} ⭐️")
                new_price = None
                try:
                    price_in = input("Новая цена в Stars (Enter — оставить): ").strip()
                    if price_in.isdigit():
                        new_price = int(price_in)
                except Exception:
                    pass

                print(f"Текущее описание: {target['description']}")
                try:
                    new_desc = input("Новое описание (Enter — оставить): ").strip()
                except Exception:
                    new_desc = ""

                if new_title or new_price or new_desc:
                    ok = update_single_prompt(
                        target["id"],
                        new_title if new_title else None,
                        new_price,
                        new_desc if new_desc else None
                    )
                    if ok:
                        print("✅ Изменения успешно сохранены в базу данных!")
                    else:
                        print("❌ Ошибка при сохранении.")
                else:
                    print("Никаких изменений не внесено.")

                input("\nНажмите Enter для продолжения...")
            else:
                print(f"❌ Номер должен быть от 1 до {len(prompts)}")
        else:
            print("❌ Неизвестная команда.")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        arg = sys.argv[1].lower()
        if arg in ["--export", "-e"]:
            n = export_to_json()
            print(f"Экспортировано {n} записей в names.json")
        elif arg in ["--import", "-i", "--sync"]:
            n = import_from_json()
            print(f"Импортировано {n} записей из names.json")
        elif arg in ["--scan", "-s"]:
            n = scan_and_register_new_files()
            print(f"Добавлено {n} новых файлов в базу")
        elif arg in ["--list", "-l"]:
            for p in get_all_prompts():
                print(f"{p['id']}: '{p['title']}' ({p['price']} ⭐️) -> {p['filename']}")
        else:
            print("Использование: py names.py [--export | --import | --scan | --list]")
    else:
        interactive_mode()
