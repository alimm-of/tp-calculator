# -*- coding: utf-8 -*-
"""CLI: импорт цен и разовый расчёт.

  python cli.py import sample/prices_sample.json prices.db
  python cli.py calc prices.db --вес 1000 --объём 2 --вид-товара ВТ1 --упаковка Короб --склад СКЛ1 --клиент К1
"""
import argparse, sqlite3, json
from datetime import date
from tp_calc.importer import импорт_json
from tp_calc.models import PriceRepository
from tp_calc import engine


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    pi = sub.add_parser("import"); pi.add_argument("json"); pi.add_argument("db")

    pc = sub.add_parser("calc"); pc.add_argument("db")
    pc.add_argument("--вес", type=float, required=True)
    pc.add_argument("--объём", type=float, required=True)
    pc.add_argument("--вид-товара", required=True)
    pc.add_argument("--группа", default=None)
    pc.add_argument("--упаковка", default=None)
    pc.add_argument("--склад", default=None)
    pc.add_argument("--клиент", default=None)
    pc.add_argument("--операция", default="ОднородныйТовар")
    pc.add_argument("--экспресс", action="store_true")
    pc.add_argument("--по-новому", action="store_true")
    pc.add_argument("--тип-перевозки", default=None, help="вид тарифа на перевозку (для ветки по-новому)")
    pc.add_argument("--мест", type=int, default=0)
    pc.add_argument("--в-упаковке", type=int, default=0)
    pc.add_argument("--брэнд", action="store_true")
    pc.add_argument("--z-товар", action="store_true")

    a = ap.parse_args()
    if a.cmd == "import":
        print(json.dumps(импорт_json(a.db, a.json), ensure_ascii=False, indent=2))
        return

    repo = PriceRepository(sqlite3.connect(a.db))
    inp = engine.CalcInput(
        общий_вес=a.вес, общий_объем=a.объём, вид_товара=a.вид_товара,
        группа_вида_товара=a.группа, тип_упаковки=a.упаковка, склад=a.склад,
        клиент=a.клиент, вид_операции=a.операция, экспресс_доставка=a.экспресс, дата=date.today(),
        вид_тарифа_на_перевозку=a.тип_перевозки, количество_мест=a.мест, количество_в_упаковке=a.в_упаковке,
        брэнд=a.брэнд, z_товар=a.z_товар,
    )
    res = engine.рассчитать(inp, repo, расчет_по_новому=a.по_новому)
    print(json.dumps(res.__dict__, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
