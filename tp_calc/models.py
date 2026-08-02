# -*- coding: utf-8 -*-
"""Модели строк ценовых регистров и репозиторий доступа к ценам (SQLite)."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional
import sqlite3


@dataclass
class PriceRow:
    """Строка базовой цены (регистры ЦеныНаГруз*)."""
    источник: str
    приоритет: int
    цена: float
    экспресс_цена: float
    по_весу: bool
    цена_авиа: float
    авиа_по_объему: bool
    цена_бренд: float
    цена_z: float
    цена_бренд_авиа: float
    склад: Optional[str]
    период: Optional[str]


@dataclass
class Настройки:
    расчет_экспресс: bool = True
    расчет_авиа: bool = False
    расчет_бренд: bool = False
    расчет_z: bool = False


@dataclass
class Коэффициент:
    коэффициент: float
    расчет_по_таблице: bool


@dataclass
class ДопРасходСтрока:
    цена: float
    по_весу: bool


def _to_date(s) -> Optional[date]:
    if not s:
        return None
    if isinstance(s, (datetime, date)):
        return s if isinstance(s, date) and not isinstance(s, datetime) else s.date()
    s = str(s)[:10]
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        return None


class PriceRepository:
    """
    Доступ к ценам поверх SQLite. Схема — schema.sql. Данные загружаются importer.py
    из JSON-выгрузки базы ТП. Все методы соответствуют запросам движка тп_РасчетЦен.
    """

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self.conn.row_factory = sqlite3.Row

    # --- Базовая цена: приоритетный подбор (источники 0..5) ---
    def подобрать_базовую_цену(self, inp, средний_вес: float) -> Optional[PriceRow]:
        d = inp.дата.isoformat() if isinstance(inp.дата, date) else str(inp.дата)
        cands: list[PriceRow] = []

        # Приоритеты 0/1 — ЦеныНаГрузДляКлиентовПоВидамТоваров (склад / пустой склад)
        cands += self._q_client_view(inp, средний_вес, d, склад=inp.склад, приоритет=0)
        cands += self._q_client_view(inp, средний_вес, d, склад=None, приоритет=1)
        # Приоритеты 2/3 — ...ПоГруппамВидовТоваров
        cands += self._q_client_group(inp, средний_вес, d, склад=inp.склад, приоритет=2)
        cands += self._q_client_group(inp, средний_вес, d, склад=None, приоритет=3)
        # ЦеныНаГруз — общая цена по складу+весу (без вида товара).
        # В 1С перебивает товарную цену для складов, где она задана. Приоритет между
        # клиентскими (0-3) и товарными (4-5): ставим 3.4/3.6, чтобы клиентские были главнее,
        # но ЦеныНаГруз выигрывала у товарной.
        cands += self._q_na_gruz(inp, средний_вес, d, приоритет=3.4)
        # Приоритеты 4/5 — ЦеныНаГрузПоВидамТовара (без клиента)
        cands += self._q_by_view(inp, средний_вес, склад=inp.склад, приоритет=4)
        cands += self._q_by_view(inp, средний_вес, склад=None, приоритет=5)

        if not cands:
            return None
        # УПОРЯДОЧИТЬ ПО Приоритет (возр), Период УБЫВ  → первая запись.
        # Стабильная сортировка в два прохода: сперва период по убыванию, затем приоритет по возрастанию.
        cands.sort(key=lambda r: (r.период or ""), reverse=True)
        cands.sort(key=lambda r: r.приоритет)
        return cands[0]

    def _q_client_view(self, inp, средний_вес, d, склад, приоритет):
        sql = """
            SELECT * FROM ceny_klient_vid
            WHERE клиент IS ? AND вид_товара = ? AND тип_упаковки IS ?
              AND (склад IS ?)
              AND ? BETWEEN вес_от AND вес_до
              AND используется = 1
              AND (дата_начала IS NULL OR ? >= дата_начала)
              AND (дата_окончания IS NULL OR ? <= дата_окончания)
        """
        rows = self.conn.execute(sql, (inp.клиент, inp.вид_товара, inp.тип_упаковки,
                                        склад, средний_вес, d, d)).fetchall()
        return [_row_to_price(r, "ЦеныНаГрузДляКлиентовПоВидамТоваров", приоритет) for r in rows]

    def _q_client_group(self, inp, средний_вес, d, склад, приоритет):
        sql = """
            SELECT * FROM ceny_klient_gruppa
            WHERE клиент IS ? AND группа = ? AND тип_упаковки IS ?
              AND (склад IS ?)
              AND ? BETWEEN вес_от AND вес_до
              AND используется = 1
              AND (дата_начала IS NULL OR ? >= дата_начала)
              AND (дата_окончания IS NULL OR ? <= дата_окончания)
        """
        rows = self.conn.execute(sql, (inp.клиент, inp.группа_вида_товара, inp.тип_упаковки,
                                        склад, средний_вес, d, d)).fetchall()
        return [_row_to_price(r, "ЦеныНаГрузДляКлиентовПоГруппамВидовТоваров", приоритет) for r in rows]

    def _q_by_view(self, inp, средний_вес, склад, приоритет):
        sql = """
            SELECT * FROM ceny_po_vidu
            WHERE (склад IS ?) AND вид_товара = ? AND тип_упаковки IS ?
              AND ? BETWEEN вес_от AND вес_до
              AND используется = 1
        """
        rows = self.conn.execute(sql, (склад, inp.вид_товара, inp.тип_упаковки, средний_вес)).fetchall()
        return [_row_to_price(r, "ЦеныНаГрузПоВидамТовара", приоритет) for r in rows]

    def _q_na_gruz(self, inp, средний_вес, d, приоритет):
        """ЦеныНаГруз — общая цена по складу+весу (без вида товара и упаковки)."""
        # таблица может отсутствовать в старых базах
        try:
            sql = """
                SELECT * FROM ceny_na_gruz
                WHERE склад IS ?
                  AND ? BETWEEN вес_от AND вес_до
                  AND (срок_действия IS NULL OR срок_действия = '' OR ? <= срок_действия)
            """
            rows = self.conn.execute(sql, (inp.склад, средний_вес, d)).fetchall()
            return [_row_to_price(r, "ЦеныНаГруз", приоритет) for r in rows]
        except Exception:
            return []

    # --- Прочие источники ---
    def настройки_расчета(self, d: date) -> Настройки:
        row = self.conn.execute("SELECT * FROM nastroyki_rascheta ORDER BY период DESC LIMIT 1").fetchone()
        if not row:
            return Настройки()
        return Настройки(
            расчет_экспресс=bool(row["расчет_экспресс"]),
            расчет_авиа=bool(row["расчет_авиа"]),
            расчет_бренд=bool(row["расчет_бренд"]),
            расчет_z=bool(row["расчет_z"]),
        )

    def склад_только_свои_цены(self, склад: Optional[str]) -> bool:
        if not склад:
            return False
        row = self.conn.execute("SELECT только_свои_цены FROM sklady WHERE ид = ?", (склад,)).fetchone()
        return bool(row and row["только_свои_цены"])

    def коэффициент_дорожных_расходов(self, склад: Optional[str], d: date) -> Optional[Коэффициент]:
        row = self.conn.execute(
            "SELECT * FROM koef_dorozhnyh WHERE склад IS ? ORDER BY период DESC LIMIT 1", (склад,)
        ).fetchone()
        if not row:
            return None
        return Коэффициент(коэффициент=row["коэффициент"], расчет_по_таблице=bool(row["расчет_по_таблице"]))

    def доп_расход_по_весу(self, inp, средний_вес: float) -> Optional[ДопРасходСтрока]:
        row = self.conn.execute(
            "SELECT * FROM cena_doprashodov WHERE ? BETWEEN вес_от AND вес_до ORDER BY период DESC LIMIT 1",
            (средний_вес,)
        ).fetchone()
        if not row:
            return None
        return ДопРасходСтрока(цена=row["цена"], по_весу=bool(row["по_весу"]))

    # --- Ветка «по новому»: растаможка, тарифы на перевозку, наценки ---
    def _город_склада(self, склад: Optional[str]) -> Optional[str]:
        if not склад:
            return None
        row = self.conn.execute("SELECT город_отправки FROM sklady WHERE ид = ?", (склад,)).fetchone()
        return row["город_отправки"] if row else None

    def цена_растаможки(self, inp) -> Optional[dict]:
        """тп_ЦеныНаРастаможку.СрезПоследних(дата, ВидТовара = ?)."""
        row = self.conn.execute(
            "SELECT * FROM ceny_rastamozhka WHERE вид_товара = ? ORDER BY период DESC LIMIT 1",
            (inp.вид_товара,)
        ).fetchone()
        if not row:
            return None
        return {
            "цена": row["цена"],
            "по_весу": bool(row["по_весу"]),
            "по_количеству": bool(row["по_количеству"]),
            "логистика_включена": bool(row["логистика_включена"]),
        }

    def тариф_перевозки(self, inp, средний_вес: float) -> Optional[dict]:
        """тп_ТарифыНаПеревозку: ВидТарифа + ГородОтправки(склада) + СреднийВес МЕЖДУ ВесОт И ВесДо."""
        город = self._город_склада(inp.склад)
        row = self.conn.execute(
            """SELECT * FROM tarify_perevozka
               WHERE вид_тарифа IS ? AND город_отправки IS ?
                 AND ? BETWEEN вес_от AND вес_до
               ORDER BY период DESC LIMIT 1""",
            (inp.вид_тарифа_на_перевозку, город, средний_вес)
        ).fetchone()
        if not row:
            return None
        return {"цена": row["цена"], "по_весу": bool(row["по_весу"])}

    def наценки_на_товар(self, d: date) -> dict:
        """тп_НаценкиНаТовар → {вид_наценки: наценка} (срез последних по каждому виду)."""
        rows = self.conn.execute(
            "SELECT вид_наценки, наценка FROM nacenki_tovar ORDER BY период DESC"
        ).fetchall()
        out: dict = {}
        for r in rows:
            if r["вид_наценки"] not in out:   # первая = самый свежий период
                out[r["вид_наценки"]] = r["наценка"]
        return out


def _row_to_price(r: sqlite3.Row, источник: str, приоритет: int) -> PriceRow:
    g = lambda k, dflt=0: (r[k] if k in r.keys() and r[k] is not None else dflt)
    return PriceRow(
        источник=f"{источник} (приоритет {приоритет})",
        приоритет=приоритет,
        цена=g("цена"), экспресс_цена=g("экспресс_цена"), по_весу=bool(g("по_весу", 0)),
        цена_авиа=g("цена_авиа"), авиа_по_объему=bool(g("авиа_по_объему", 0)),
        цена_бренд=g("цена_бренд"), цена_z=g("цена_z"), цена_бренд_авиа=g("цена_бренд_авиа"),
        склад=(r["склад"] if "склад" in r.keys() else None),
        период=(r["период"] if "период" in r.keys() else None),
    )
