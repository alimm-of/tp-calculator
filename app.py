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
ВЕРСИЯ = "v9"   # номер релиза — виден на странице
HERE = os.path.dirname(os.path.abspath(__file__))

# --- Значения по умолчанию для выпадающих списков (если в БД пусто) ---
УПАКОВКИ_DEFAULT = ["Korobka", "Yashik", "Bochka", "Rulon", "Pres", "Pres zavodskoy", "Seyf", "Meshok", "Poddon"]

# Типы перевозки как в форме «Калькуляция» 1С. Каждый раскладывается на флаги движка:
#   экспресс  — берётся колонка «Экспресс цена» (РасчетСреднейЦеныПоСтарому)
#   авиа      — берётся колонка «Цена авиа» (вид операции ПриемПочтыСтационарный)
ТИПЫ_ПЕРЕВОЗКИ = {
    "Авто":         {"экспресс": False, "авиа": False, "вид_тарифа": "000000001"},
    "Авто Экспресс": {"экспресс": True,  "авиа": False, "вид_тарифа": "000000002"},
    "Авиа":         {"экспресс": False, "авиа": True,  "вид_тарифа": "000000001"},
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

# Справочник типов упаковки: код → название (из 1С)
def _загрузить_упаковки():
    path = os.path.join(HERE, "tp_calc", "upakovki.json")
    if os.path.exists(path):
        try:
            return json.load(open(path, encoding="utf-8"))
        except Exception:
            return {}
    return {}

УПАКОВКИ_СПРАВОЧНИК = _загрузить_упаковки()   # {"1": "Korobka", ...}

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
    """Склады (ид+наименование) и упаковки — из БД. Виды товара — из справочника 1С.
    Склады фильтруются: для расчёта нужны только страны отправки (Китай, Киргизия/Бишкек);
    склады приёма в Узбекистане не показываются. Если поля 'страна' в базе нет — показываем все."""
    склады, упаковки = [], []
    if os.path.exists(DB):
        c = sqlite3.connect(DB); c.row_factory = sqlite3.Row
        # есть ли колонка страна?
        cols = [r[1] for r in c.execute("PRAGMA table_info(sklady)")]
        # Коды стран-отправителей (ISO): 156=Китай, 417=Киргизия. Остальное (860=Узбекистан,
        # 643=Россия, пустые служебные группы) в калькуляторе не показываем.
        СТРАНЫ_ОТПРАВКИ = ("156", "417")
        try:
            if "страна" in cols:
                строки = c.execute("""
                    SELECT ид, наименование, страна FROM sklady
                    WHERE страна IN (?, ?)
                    ORDER BY наименование""", СТРАНЫ_ОТПРАВКИ).fetchall()
            else:
                строки = c.execute("SELECT ид, наименование, NULL FROM sklady ORDER BY наименование").fetchall()
            склады = [(r[0], r[1] or r[0]) for r in строки]
        except Exception:
            pass
        try:
            коды_в_ценах = {r[0] for r in c.execute(
                "SELECT DISTINCT тип_упаковки FROM ceny_po_vidu WHERE тип_упаковки IS NOT NULL")}
            # пары (код, название); название из справочника, иначе сам код
            упаковки = sorted(
                [(k, УПАКОВКИ_СПРАВОЧНИК.get(k, k)) for k in коды_в_ценах],
                key=lambda x: x[1])
        except Exception: pass
    return (склады, упаковки, ВИДЫ_ТОВАРА, list(ТИПЫ_ПЕРЕВОЗКИ.keys()))


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
 .результаты{position:absolute;z-index:10;left:0;right:0;background:#fff;border:1px solid #ccd0d5;border-radius:8px;max-height:260px;overflow:auto;box-shadow:0 4px 12px rgba(0,0,0,.12)}
 .результаты div{padding:7px 10px;cursor:pointer;font-size:14px;border-bottom:1px solid #f0f1f3}
 .результаты div:hover{background:#eaf1fd}
 .результаты .код{color:#888;font-size:12px}
 .err{color:#b00}
</style></head><body><div class=wrap>
<h1>Калькуляция · на основе цен «Транспортных перевозок» <span style="font-size:13px;color:#888;font-weight:normal">{{версия}}</span></h1>
{% if not db_ok %}<div class="card err">База цен <b>{{db}}</b> не найдена.
Создайте: <code>python cli.py import &lt;prices.json&gt; {{db}}</code></div>{% endif %}
<form method=post class=card>
 <div class=grid>
  <div><label>Склад</label>
    <select name=склад>{% for ид,имя in склады %}<option value="{{ид}}" {{'selected' if f.склад==ид else ''}}>{{имя}}</option>{% endfor %}</select></div>
  <div><label>Тип перевозки</label>
    <select name=тип_перевозки>{% for t in типы %}<option {{'selected' if f.тип_перевозки==t else ''}}>{{t}}</option>{% endfor %}</select></div>
  <div style="position:relative"><label>Вид товара</label>
    <input id=вид_поиск autocomplete=off value="{{f.вид_товара_имя or ''}}"
           placeholder="название (рус/лат) или код" oninput="искатьВид()" onfocus="искатьВид()">
    <input type=hidden name=вид_товара id=вид_товара_код value="{{f.вид_товара or ''}}">
    <input type=hidden name=вид_товара_имя id=вид_товара_имя value="{{f.вид_товара_имя or ''}}">
    <div id=вид_результаты class=результаты style="display:none"></div>
  </div>
  <div><label>Тип упаковки</label>
    <select name=упаковка>{% for код,имя in упаковки %}<option value="{{код}}" {{'selected' if f.упаковка==код else ''}}>{{имя}}</option>{% endfor %}</select></div>
  <div><label>Вес, кг</label><input name=вес type=number step=any value="{{f.вес or 1000}}"></div>
  <div><label>Объём, м³</label><input id=поле_объём name=объём type=number step=any value="{{f.объём or 2}}"></div>
  <div><label>Кол-во мест</label><input id=поле_мест name=мест type=number value="{{f.мест or 1}}"></div>
  <div id=box_вупак style="display:none"><label>В упаковке (шт)</label><input name=в_упаковке type=number value="{{f.в_упаковке or 0}}"></div>
 </div>
 <div class=chk style="margin-top:8px"><input type=checkbox id=по_объёму name=по_объёму value=1 {{'checked' if f.по_объёму is not defined or f.по_объёму else ''}}>
   <label for=по_объёму style="margin:0">По объёму (вводить объём вручную; иначе — из габаритов)</label></div>
 <div class=grid style="margin-top:8px">
  <div><label>Длина, см</label><input id=g_дл name=длина type=number step=any value="{{f.длина or ''}}"></div>
  <div><label>Ширина, см</label><input id=g_ш name=ширина type=number step=any value="{{f.ширина or ''}}"></div>
  <div><label>Высота, см</label><input id=g_в name=высота type=number step=any value="{{f.высота or ''}}"></div>
 </div>
 <div class=src style="margin:4px 0 0">При снятой галке «По объёму» объём считается из Д×Ш×В×места ÷ 1 000 000.</div>
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
window.__ВИДЫ__ = {{ виды_json|safe }};
</script>
<script>
function пересчётОбъёма(){
  // если галка "По объёму" стоит — объём вводится вручную, габариты не считаем
  var поОбъёму=document.getElementById('по_объёму');
  if(поОбъёму && поОбъёму.checked) return;
  var д=parseFloat(document.getElementById('g_дл').value)||0;
  var ш=parseFloat(document.getElementById('g_ш').value)||0;
  var в=parseFloat(document.getElementById('g_в').value)||0;
  var м=parseFloat(document.getElementById('поле_мест').value)||1;
  if(д>0&&ш>0&&в>0){
    var объём=(д*ш*в*м)/1000000;   // см³ → м³
    document.getElementById('поле_объём').value=объём.toFixed(4);
  }
}
function переключитьОбъём(){
  var поОбъёму=document.getElementById('по_объёму').checked;
  var объём=document.getElementById('поле_объём');
  var габ=['g_дл','g_ш','g_в'].map(function(id){return document.getElementById(id);});
  // галка ВКЛ → объём активен, габариты серые; галка ВЫКЛ → наоборот
  объём.disabled=!поОбъёму;
  объём.style.background=поОбъёму?'':'#f0f0f0';
  габ.forEach(function(el){ if(el){ el.disabled=поОбъёму; el.style.background=поОбъёму?'#f0f0f0':''; } });
  if(!поОбъёму) пересчётОбъёма();
}
var ВИДЫ = window.__ВИДЫ__ || [];
function искатьВид(){
  var поле=document.getElementById('вид_поиск');
  var box=document.getElementById('вид_результаты');
  var q=поле.value.trim().toLowerCase();
  document.getElementById('вид_товара_имя').value=поле.value;
  if(q.length<1){ box.style.display='none'; return; }
  var res=[];
  for(var i=0;i<ВИДЫ.length && res.length<50;i++){
    var v=ВИДЫ[i];
    var имя=(v.имя||'').toLowerCase();
    var рус=(v.имя_рус||'').toLowerCase();
    var код=(v.код||'').toLowerCase();
    // поиск по латинскому, русскому названию или коду
    if(имя.indexOf(q)>=0 || рус.indexOf(q)>=0 || код.indexOf(q)>=0) res.push(v);
  }
  if(!res.length){ box.innerHTML='<div class=код>ничего не найдено</div>'; box.style.display='block'; return; }
  var h='';
  for(var j=0;j<res.length;j++){
    var v=res[j];
    // показываем латинское (для расчёта) + русское для понятности
    var подпись=(v.имя||'');
    var доп=(v.имя_рус?(' · '+v.имя_рус):'')+(v.группа?(' · '+v.группа):'');
    h+='<div onclick="выбратьВид(\''+v.код+'\',this)" data-имя="'+(v.имя||'').replace(/"/g,'&quot;')+'">'+
       подпись+'<span class=код>'+доп+' ['+v.код+']</span></div>';
  }
  box.innerHTML=h; box.style.display='block';
}
function выбратьВид(код,el){
  document.getElementById('вид_товара_код').value=код;
  var имя=el.getAttribute('data-имя');
  document.getElementById('вид_поиск').value=имя;
  document.getElementById('вид_товара_имя').value=имя;
  document.getElementById('вид_результаты').style.display='none';
}
document.addEventListener('click',function(e){
  var box=document.getElementById('вид_результаты');
  var поле=document.getElementById('вид_поиск');
  if(box && e.target!==поле && !box.contains(e.target)) box.style.display='none';
});
(function(){
  var pn = document.getElementById('pn');
  var box = document.getElementById('box_вупак');
  function upd(){ if(box) box.style.display = pn.checked ? '' : 'none'; }
  if(pn && box){ pn.addEventListener('change', upd); upd(); }
})();
// Надёжная привязка обработчиков (inline с кириллицей ненадёжен)
document.addEventListener('DOMContentLoaded', function(){
  var чек=document.getElementById('по_объёму');
  if(чек) чек.addEventListener('change', переключитьОбъём);
  ['g_дл','g_ш','g_в','поле_мест'].forEach(function(id){
    var el=document.getElementById(id);
    if(el) el.addEventListener('input', пересчётОбъёма);
  });
  переключитьОбъём();  // начальное состояние
});
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
            вид_тарифа_на_перевозку=флаги.get("вид_тарифа", "000000001"),
            количество_мест=int(f.get("мест") or 0), количество_в_упаковке=int(f.get("в_упаковке") or 0),
            брэнд=bool(f.get("брэнд")), z_товар=bool(f.get("z_товар")),
        )
        res = engine.рассчитать(inp, repo, расчет_по_новому=bool(f.get("по_новому")))
    import json as _json
    виды_json = _json.dumps(
        [{"код": v["код"], "имя": v["имя"], "имя_рус": v.get("имя_рус", ""), "группа": v.get("группа", "")}
         for v in виды_товара],
        ensure_ascii=False)
    return render_template_string(PAGE, res=res, f=f, db=DB, db_ok=db_ok, версия=ВЕРСИЯ,
                                  склады=склады, упаковки=упаковки, виды_товара=виды_товара,
                                  виды_json=виды_json, типы=типы)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
