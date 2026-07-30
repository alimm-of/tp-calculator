# -*- coding: utf-8 -*-
"""
Веб-калькулятор цен (Flask). Читает цены из prices.db (создать: python cli.py import ...).
Запуск:  python app.py    →  http://127.0.0.1:5000

Зависимости: Flask (pip install flask). Если Flask нет — используйте cli.py.
"""
import os, sqlite3
from datetime import date
from flask import Flask, request, render_template_string
from tp_calc.models import PriceRepository
from tp_calc import engine

DB = os.environ.get("PRICES_DB", "prices.db")
app = Flask(__name__)

# Авто-инициализация БД при старте (Railway: контейнер стартует с чистого образа).
# Если базы нет, создаём её из выгрузки, указанной в SEED_JSON (по умолчанию sample).
if not os.path.exists(DB):
    seed = os.environ.get("SEED_JSON", os.path.join("sample", "prices_sample.json"))
    if os.path.exists(seed):
        try:
            from tp_calc.importer import импорт_json
            импорт_json(DB, seed)
        except Exception as e:
            print(f"[seed] не удалось создать БД из {seed}: {e}")

PAGE = """
<!doctype html><html lang=ru><head><meta charset=utf-8>
<title>Калькулятор цен · Транспортные перевозки</title>
<style>
 body{font-family:system-ui,Segoe UI,Arial;margin:0;background:#f5f6f8;color:#1c1e21}
 .wrap{max-width:860px;margin:24px auto;padding:0 16px}
 h1{font-size:20px} .card{background:#fff;border:1px solid #e3e5e8;border-radius:12px;padding:18px;margin-bottom:16px}
 label{display:block;font-size:13px;color:#555;margin:8px 0 3px}
 input,select{width:100%;padding:8px;border:1px solid #ccd0d5;border-radius:8px;box-sizing:border-box}
 .grid{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}
 button{margin-top:14px;background:#2d6cdf;color:#fff;border:0;padding:10px 18px;border-radius:8px;font-size:15px;cursor:pointer}
 .out{display:grid;grid-template-columns:1fr auto;gap:6px 18px;font-size:15px}
 .out .k{color:#555} .out .v{text-align:right;font-variant-numeric:tabular-nums}
 .tot{font-weight:700;font-size:18px;border-top:1px solid #e3e5e8;padding-top:8px;margin-top:8px}
 .note{color:#a15c00;font-size:13px;margin-top:8px} .src{color:#666;font-size:12px}
 .err{color:#b00}
</style></head><body><div class=wrap>
<h1>Калькулятор цен · на основе цен «Транспортных перевозок»</h1>
{% if not db_ok %}<div class="card err">База цен <b>{{db}}</b> не найдена. Создайте её:
<code>python cli.py import &lt;prices.json&gt; {{db}}</code></div>{% endif %}
<form method=post class=card>
 <div class=grid>
  <div><label>Вес, кг</label><input name=вес type=number step=any value="{{f.вес or 1000}}"></div>
  <div><label>Объём, м³</label><input name=объём type=number step=any value="{{f.объём or 2}}"></div>
  <div><label>Вид товара</label><input name=вид_товара value="{{f.вид_товара or 'ВТ1'}}"></div>
  <div><label>Группа вида (опц.)</label><input name=группа value="{{f.группа or ''}}"></div>
  <div><label>Тип упаковки</label><input name=упаковка value="{{f.упаковка or 'Короб'}}"></div>
  <div><label>Склад</label><input name=склад value="{{f.склад or 'СКЛ1'}}"></div>
  <div><label>Клиент (опц.)</label><input name=клиент value="{{f.клиент or ''}}"></div>
  <div><label>Вид операции</label><select name=операция>
     {% for o in ['ОднородныйТовар','Экспресс','ПриемПочты','ПриемПочтыСтационарный'] %}
     <option {{'selected' if f.операция==o else ''}}>{{o}}</option>{% endfor %}</select></div>
  <div><label>Экспресс-доставка</label><select name=экспресс>
     <option value="0">Нет</option><option value="1" {{'selected' if f.экспресс=='1' else ''}}>Да</option></select></div>
 </div>
 <label><input type=checkbox name=по_новому value=1 {{'checked' if f.по_новому else ''}}> Расчёт «по новому» (перевозка + растаможка + last-mile)</label>
 <button type=submit>Рассчитать</button>
</form>
{% if res %}
<div class=card>
 <div class=out>
  <div class=k>Цена за тонну</div><div class=v>{{'%.2f'|format(res.цена_за_тонну)}}</div>
  <div class=k>Цена за куб</div><div class=v>{{'%.2f'|format(res.цена_за_куб)}}</div>
  <div class=k>Стоимость перевозки</div><div class=v>{{'%.2f'|format(res.сумма)}}</div>
  {% if res.сумма_за_перевозку %}<div class=k>· в т.ч. перевозка</div><div class=v>{{'%.2f'|format(res.сумма_за_перевозку)}}</div>{% endif %}
  {% if res.сумма_за_растаможку %}<div class=k>· в т.ч. растаможка</div><div class=v>{{'%.2f'|format(res.сумма_за_растаможку)}}</div>{% endif %}
  <div class=k>Допрасходы за доставку</div><div class=v>{{'%.2f'|format(res.сумма_допрасходов_за_доставку)}}</div>
  <div class="k tot">Итого</div><div class="v tot">{{'%.2f'|format(res.итого)}}</div>
 </div>
 <div class=src>Средний вес: {{'%.2f'|format(res.средний_вес)}} кг/м³ · Источник цены: {{res.источник_цены or '—'}} · По весу: {{'да' if res.по_весу else 'нет'}}</div>
 {% for n in res.примечания %}<div class=note>⚠ {{n}}</div>{% endfor %}
</div>{% endif %}
<div class=src>Ветки бренд/Z/«по новому» — точки расширения в <code>tp_calc/extensions.py</code>.</div>
</div></body></html>
"""


@app.route("/", methods=["GET", "POST"])
def index():
    db_ok = os.path.exists(DB)
    f = {k: request.form.get(k) for k in request.form}
    res = None
    if request.method == "POST" and db_ok:
        repo = PriceRepository(sqlite3.connect(DB))
        inp = engine.CalcInput(
            общий_вес=float(f.get("вес") or 0), общий_объем=float(f.get("объём") or 0),
            вид_товара=f.get("вид_товара") or "", группа_вида_товара=f.get("группа") or None,
            тип_упаковки=f.get("упаковка") or None, склад=f.get("склад") or None,
            клиент=f.get("клиент") or None, вид_операции=f.get("операция") or "ОднородныйТовар",
            экспресс_доставка=(f.get("экспресс") == "1"), дата=date.today(),
        )
        res = engine.рассчитать(inp, repo, расчет_по_новому=bool(f.get("по_новому")))
    return render_template_string(PAGE, res=res, f=f, db=DB, db_ok=db_ok)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
