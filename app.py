# -*- coding: utf-8 -*-
"""
Веб-калькулятор цен (Flask) на основе цен «Транспортных перевозок».
Форма приведена к виду документа «Калькуляция» в 1С: склад, тип перевозки, вид товара,
тип упаковки (списки), габариты/объём, вес, галка «Расчёт по новому».

Списки СКЛАДЫ / УПАКОВКИ / ТИПЫ_ПЕРЕВОЗКИ / ВИДЫ_ТОВАРА заполняются автоматически из БД,
а если данных нет — из значений по умолчанию ниже (подставьте свои коды из 1С).
"""
import os, sqlite3, json
from datetime import date
from flask import Flask, request, render_template_string
from tp_calc.models import PriceRepository
from tp_calc import engine

DB = os.environ.get("PRICES_DB", "prices.db")
HERE = os.path.dirname(os.path.abspath(__file__))

# --- Значения по умолчанию для выпадающих списков (если в БД пусто) ---
УПАКОВКИ_DEFAULT = ["Korobka", "Yashik", "Bochka", "Rulon", "Pres", "Pres zavodskoy", "Seyf", "Meshok", "Poddon"]

# Типы перевозки как в форме «Калькуляция» 1С. Каждый раскладывается на флаги движка:
#   экспресс  — берётся колонка «Экспресс цена» (РасчетСреднейЦеныПоСтарому)
#   авиа      — берётся колонка «Цена авиа» (вид операции ПриемПочтыСтационарный)
ТИПЫ_ПЕРЕВОЗКИ = {
    "Авто":         {"экспресс": False, "авиа": False},
    "Авто Экспресс": {"экспресс": True,  "авиа": False},
    "Авиа":         {"экспресс": False, "авиа": True},
}

# Полный справочник видов товара (код → имя, группа), выгружен из 1С.
def _загрузить_виды_товара():
    path = os.path.join(HERE, "tp_calc", "vidy_tovarov.json")
    if os.path.exists(path):
        try:
            return json.load(open(path, encoding="utf-8"))
        except Exception:
            return []
    return []

ВИДЫ_ТОВАРА = _загрузить_виды_товара()
ГРУППА_ПО_КОДУ = {v["код"]: v.get("группа", "") for v in ВИДЫ_ТОВАРА}

app = Flask(__name__)

# --- Защита паролем (HTTP Basic Auth) ---
# Включается, если задана переменная окружения APP_PASSWORD.
# Логин по умолчанию "admin" (меняется через APP_USERNAME). Если пароль не задан — доступ открыт.
from functools import wraps
from flask import Response

def _auth_ок(u, p):
    need_user = os.environ.get("APP_USERNAME", "admin")
    need_pass = os.environ.get("APP_PASSWORD", "")
    return (not need_pass) or (u == need_user and p == need_pass)

@app.before_request
def _проверка_пароля():
    if not os.environ.get("APP_PASSWORD"):
        return  # пароль не задан — не защищаем
    a = request.authorization
    if not a or not _auth_ок(a.username, a.password):
        return Response("Authorization required", 401,
                        {"WWW-Authenticate": 'Basic realm="Price Calculator"'})

# Авто-инициализация БД при старте (Railway стартует с чистого образа).
if not os.path.exists(DB):
    seed = os.environ.get("SEED_JSON", os.path.join("sample", "prices_sample.json"))
    if os.path.exists(seed):
        try:
            from tp_calc.importer import импорт_json
            импорт_json(DB, seed)
        except Exception as e:
            print(f"[seed] не удалось создать БД из {seed}: {e}")


def _списки():
    """Склады и упаковки — из БД (или дефолты). Виды товара — из справочника 1С."""
    склады, упаковки = [], []
    if os.path.exists(DB):
        c = sqlite3.connect(DB); c.row_factory = sqlite3.Row
        try:
            склады = [r["ид"] for r in c.execute("SELECT ид FROM sklady ORDER BY наименование")]
        except Exception: pass
        try:
            упаковки = sorted({r[0] for r in c.execute(
                "SELECT DISTINCT тип_упаковки FROM ceny_po_vidu WHERE тип_упаковки IS NOT NULL")})
        except Exception: pass
        c.close()
    return (склады, упаковки or УПАКОВКИ_DEFAULT, ВИДЫ_ТОВАРА, list(ТИПЫ_ПЕРЕВОЗКИ.keys()))


PAGE = r"""
<!doctype html><html lang=ru><head><meta charset=utf-8>
<meta name=viewport content="width=device-width, initial-scale=1">
<title>Калькуляция · Транспортные перевозки</title>
<style>
 body{font-family:system-ui,Segoe UI,Arial;margin:0;background:#f5f6f8;color:#1c1e21}
 .wrap{max-width:820px;margin:24px auto;padding:0 16px}
 h1{font-size:19px}
 .card{background:#fff;border:1px solid #e3e5e8;border-radius:12px;padding:18px;margin-bottom:16px}
 label{display:block;font-size:13px;color:#555;margin:8px 0 3px}
 input,select{width:100%;padding:8px;border:1px solid #ccd0d5;border-radius:8px;box-sizing:border-box}
 .grid{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}
 .row2{display:grid;grid-template-columns:1fr 1fr;gap:12px}
 .chk{display:flex;align-items:center;gap:8px;margin-top:12px}
 .chk input{width:auto}
 button{margin-top:14px;background:#2d6cdf;color:#fff;border:0;padding:10px 18px;border-radius:8px;font-size:15px;cursor:pointer}
 .out{display:grid;grid-template-columns:1fr auto;gap:6px 18px;font-size:15px}
 .out .k{color:#555} .out .v{text-align:right;font-variant-numeric:tabular-nums}
 .tot{font-weight:700;font-size:18px;border-top:1px solid #e3e5e8;padding-top:8px;margin-top:8px}
 .note{color:#a15c00;font-size:13px;margin-top:8px} .src{color:#666;font-size:12px}
 .err{color:#b00}
</style></head><body><div class=wrap>
<h1>Калькуляция · на основе цен «Транспортных перевозок»</h1>
{% if not db_ok %}<div class="card err">База цен <b>{{db}}</b> не найдена.
Создайте: <code>python cli.py import &lt;prices.json&gt; {{db}}</code></div>{% endif %}
<form method=post class=card>
 <div class=grid>
  <div><label>Склад</label>
    <select name=склад>{% for s in склады %}<option {{'selected' if f.склад==s else ''}}>{{s}}</option>{% endfor %}</select></div>
  <div><label>Тип перевозки</label>
    <select name=тип_перевозки>{% for t in типы %}<option {{'selected' if f.тип_перевозки==t else ''}}>{{t}}</option>{% endfor %}</select></div>
  <div><label>Вид товара</label>
    <input id=вид_товара_поиск list=виды_товара_list autocomplete=off
           value="{{f.вид_товара_имя or ''}}" placeholder="введите название или код"
           oninput="подобратьВид(this.value)">
    <input type=hidden name=вид_товара id=вид_товара_код value="{{f.вид_товара or ''}}">
    <input type=hidden name=вид_товара_имя id=вид_товара_имя value="{{f.вид_товара_имя or ''}}">
    <datalist id=виды_товара_list>
      {% for v in виды_товара %}<option data-код="{{v.код}}" value="{{v.имя}}{% if v.группа %} · {{v.группа}}{% endif %} [{{v.код}}]"></option>{% endfor %}
    </datalist></div>
  <div><label>Тип упаковки</label>
    <select name=упаковка>{% for u in упаковки %}<option {{'selected' if f.упаковка==u else ''}}>{{u}}</option>{% endfor %}</select></div>
  <div><label>Вес, кг</label><input name=вес type=number step=any value="{{f.вес or 1000}}"></div>
  <div><label>Объём, м³</label><input name=объём type=number step=any value="{{f.объём or 2}}"></div>
  <div><label>Кол-во мест</label><input name=мест type=number value="{{f.мест or 1}}"></div>
  <div id=box_вупак style="display:none"><label>В упаковке (шт)</label><input name=в_упаковке type=number value="{{f.в_упаковке or 0}}"></div>
 </div>
 <div class=chk><input type=checkbox id=pn name=по_новому value=1 {{'checked' if f.по_новому else ''}}>
   <label for=pn style="margin:0">Расчёт «по новому» (перевозка + растаможка + наценки)</label></div>
 <div class=chk><input type=checkbox id=br name=брэнд value=1 {{'checked' if f.брэнд else ''}}>
   <label for=br style="margin:0">Бренд</label></div>
 <div class=chk><input type=checkbox id=zt name=z_товар value=1 {{'checked' if f.z_товар else ''}}>
   <label for=zt style="margin:0">Z-товар (батарея)</label></div>
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
  {% if res.сумма_бренд %}<div class=k>· в т.ч. бренд</div><div class=v>{{'%.2f'|format(res.сумма_бренд)}}</div>{% endif %}
  {% if res.сумма_z %}<div class=k>· в т.ч. Z-товар</div><div class=v>{{'%.2f'|format(res.сумма_z)}}</div>{% endif %}
  <div class=k>Допрасходы за доставку</div><div class=v>{{'%.2f'|format(res.сумма_допрасходов_за_доставку)}}</div>
  <div class="k tot">Итого</div><div class="v tot">{{'%.2f'|format(res.итого)}}</div>
 </div>
 <div class=src>Средний вес: {{'%.2f'|format(res.средний_вес)}} кг/м³ · Источник: {{res.источник_цены or '—'}} · По весу: {{'да' if res.по_весу else 'нет'}}</div>
 {% for n in res.примечания %}<div class=note>⚠ {{n}}</div>{% endfor %}
</div>{% endif %}
<div class=src>Логика перенесена из общего модуля тп_РасчетЦен. Свои тарифы / last-mile — в <code>tp_calc/extensions.py</code>.</div>
<script>
function подобратьВид(v){
  // формат опции: "Название · Группа [КОД]" — вытащим КОД из хвоста
  var m = v.match(/\[([^\]]+)\]\s*$/);
  document.getElementById('вид_товара_код').value = m ? m[1] : v.trim();
  document.getElementById('вид_товара_имя').value = v;
}
(function(){
  var pn = document.getElementById('pn');
  var box = document.getElementById('box_вупак');
  function upd(){ if(box) box.style.display = pn.checked ? '' : 'none'; }
  if(pn && box){ pn.addEventListener('change', upd); upd(); }
})();
</script>
</div></body></html>"""


@app.route("/", methods=["GET", "POST"])
def index():
    db_ok = os.path.exists(DB)
    склады, упаковки, виды_товара, типы = _списки()
    f = {k: request.form.get(k) for k in request.form}
    res = None
    if request.method == "POST" and db_ok:
        repo = PriceRepository(sqlite3.connect(DB))
        # Тип перевозки → флаги движка (экспресс/авиа) + вид операции
        тип_пер = f.get("тип_перевозки") or "Авто"
        флаги = ТИПЫ_ПЕРЕВОЗКИ.get(тип_пер, ТИПЫ_ПЕРЕВОЗКИ["Авто"])
        вид_операции = "ПриемПочтыСтационарный" if флаги["авиа"] else "ОднородныйТовар"
        код_товара = (f.get("вид_товара") or "").strip()
        inp = engine.CalcInput(
            общий_вес=float(f.get("вес") or 0), общий_объем=float(f.get("объём") or 0),
            вид_товара=код_товара, группа_вида_товара=ГРУППА_ПО_КОДУ.get(код_товара) or None,
            тип_упаковки=f.get("упаковка") or None, склад=f.get("склад") or None,
            вид_операции=вид_операции, экспресс_доставка=флаги["экспресс"], дата=date.today(),
            вид_тарифа_на_перевозку=тип_пер,
            количество_мест=int(f.get("мест") or 0), количество_в_упаковке=int(f.get("в_упаковке") or 0),
            брэнд=bool(f.get("брэнд")), z_товар=bool(f.get("z_товар")),
        )
        res = engine.рассчитать(inp, repo, расчет_по_новому=bool(f.get("по_новому")))
    return render_template_string(PAGE, res=res, f=f, db=DB, db_ok=db_ok,
                                  склады=склады, упаковки=упаковки, виды_товара=виды_товара, типы=типы)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
