# -*- coding: utf-8 -*-
"""Импорт JSON-выгрузки цен (из базы ТП) в SQLite по схеме schema.sql."""
from __future__ import annotations
import json
import os
import sqlite3

HERE = os.path.dirname(__file__)
SCHEMA = os.path.join(HERE, "schema.sql")

# Соответствие: ключ в JSON-выгрузке -> (таблица, [колонки таблицы])
TABLES = {
    "ЦеныНаГрузДляКлиентовПоВидамТоваров": ("ceny_klient_vid",
        ["клиент","вид_товара","тип_упаковки","склад","цена","экспресс_цена","по_весу",
         "цена_авиа","авиа_по_объему","цена_бренд","цена_z","цена_бренд_авиа",
         "вес_от","вес_до","дата_начала","дата_окончания","используется","период"]),
    "ЦеныНаГрузДляКлиентовПоГруппамВидовТоваров": ("ceny_klient_gruppa",
        ["клиент","группа","тип_упаковки","склад","цена","экспресс_цена","по_весу",
         "цена_авиа","авиа_по_объему","цена_бренд","цена_z","цена_бренд_авиа",
         "вес_от","вес_до","дата_начала","дата_окончания","используется","период"]),
    "ЦеныНаГрузПоВидамТовара": ("ceny_po_vidu",
        ["склад","вид_товара","тип_упаковки","цена","экспресс_цена","по_весу",
         "цена_авиа","авиа_по_объему","цена_бренд","цена_z","цена_бренд_авиа",
         "вес_от","вес_до","используется","период"]),
    "КоэффициентыДорожныхРасходов": ("koef_dorozhnyh", ["склад","коэффициент","расчет_по_таблице","период"]),
    "ЦенаДопРасходов": ("cena_doprashodov", ["вес_от","вес_до","цена","по_весу","период"]),
    "тп_ТарифыНаПеревозку": ("tarify_perevozka", ["вид_тарифа","город_отправки","вес_от","вес_до","цена","по_весу","период"]),
    "тп_ЦеныНаРастаможку": ("ceny_rastamozhka", ["вид_товара","цена","по_весу","по_количеству","логистика_включена","период"]),
    "тп_НаценкиНаТовар": ("nacenki_tovar", ["вид_наценки","наценка","период"]),
    "тп_СтавкиЗаПресс": ("stavki_press", ["склад","тип_упаковки","магазин","ставка","валюта_ставки","период"]),
    "НастройкиРасчетаШК": ("nastroyki_rascheta", ["расчет_экспресс","расчет_авиа","расчет_бренд","расчет_z","период"]),
    "Справочник_тп_Склады": ("sklady", ["ид","код","наименование","город_отправки","только_свои_цены"]),
}

BOOL_COLS = {"по_весу","авиа_по_объему","используется","расчет_по_таблице","по_количеству",
             "логистика_включена","расчет_экспресс","расчет_авиа","расчет_бренд","расчет_z","только_свои_цены"}


def создать_бд(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    with open(SCHEMA, encoding="utf-8") as f:
        conn.executescript(f.read())
    return conn


def _norm(col, val):
    if val is None:
        return None
    if col in BOOL_COLS:
        if isinstance(val, str):
            return 1 if val.strip().lower() in ("1","истина","true","да","yes") else 0
        return 1 if val else 0
    return val


def импорт_json(db_path: str, json_path: str) -> dict:
    """Загружает JSON-пакет в новую БД. Возвращает {таблица: число_строк}."""
    with open(json_path, encoding="utf-8") as f:
        pack = json.load(f)
    conn = создать_бд(db_path)
    stats = {}
    for key, (table, cols) in TABLES.items():
        rows = pack.get(key) or []
        if isinstance(rows, dict):        # одиночная запись (напр. настройки)
            rows = [rows]
        placeholders = ",".join("?" for _ in cols)
        sql = f"INSERT INTO {table} ({','.join(cols)}) VALUES ({placeholders})"
        for r in rows:
            vals = [_norm(c, r.get(c)) for c in cols]
            conn.execute(sql, vals)
        stats[table] = len(rows)
    conn.commit()
    return {"db": db_path, "дата_среза": pack.get("ДатаСреза"), "таблицы": stats}


if __name__ == "__main__":
    import sys
    if len(sys.argv) != 3:
        print("Использование: python -m tp_calc.importer <prices.json> <out.db>")
        sys.exit(1)
    info = импорт_json(sys.argv[2], sys.argv[1])
    print(json.dumps(info, ensure_ascii=False, indent=2))
