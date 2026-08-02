-- Схема БД калькулятора. Таблицы = ценовые регистры «Транспортных перевозок»
-- (структура выведена из запросов движка тп_РасчетЦен).

DROP TABLE IF EXISTS ceny_klient_vid;
CREATE TABLE ceny_klient_vid (        -- ЦеныНаГрузДляКлиентовПоВидамТоваров
    клиент TEXT, вид_товара TEXT, тип_упаковки TEXT, склад TEXT,
    цена REAL DEFAULT 0, экспресс_цена REAL DEFAULT 0, по_весу INTEGER DEFAULT 0,
    цена_авиа REAL DEFAULT 0, авиа_по_объему INTEGER DEFAULT 0,
    цена_бренд REAL DEFAULT 0, цена_z REAL DEFAULT 0, цена_бренд_авиа REAL DEFAULT 0,
    вес_от REAL DEFAULT 0, вес_до REAL DEFAULT 1e12,
    дата_начала TEXT, дата_окончания TEXT, используется INTEGER DEFAULT 1,
    период TEXT
);

DROP TABLE IF EXISTS ceny_klient_gruppa;
CREATE TABLE ceny_klient_gruppa (     -- ЦеныНаГрузДляКлиентовПоГруппамВидовТоваров
    клиент TEXT, группа TEXT, тип_упаковки TEXT, склад TEXT,
    цена REAL DEFAULT 0, экспресс_цена REAL DEFAULT 0, по_весу INTEGER DEFAULT 0,
    цена_авиа REAL DEFAULT 0, авиа_по_объему INTEGER DEFAULT 0,
    цена_бренд REAL DEFAULT 0, цена_z REAL DEFAULT 0, цена_бренд_авиа REAL DEFAULT 0,
    вес_от REAL DEFAULT 0, вес_до REAL DEFAULT 1e12,
    дата_начала TEXT, дата_окончания TEXT, используется INTEGER DEFAULT 1,
    период TEXT
);

DROP TABLE IF EXISTS ceny_po_vidu;
CREATE TABLE ceny_po_vidu (           -- ЦеныНаГрузПоВидамТовара
    склад TEXT, вид_товара TEXT, тип_упаковки TEXT,
    цена REAL DEFAULT 0, экспресс_цена REAL DEFAULT 0, по_весу INTEGER DEFAULT 0,
    цена_авиа REAL DEFAULT 0, авиа_по_объему INTEGER DEFAULT 0,
    цена_бренд REAL DEFAULT 0, цена_z REAL DEFAULT 0, цена_бренд_авиа REAL DEFAULT 0,
    вес_от REAL DEFAULT 0, вес_до REAL DEFAULT 1e12,
    используется INTEGER DEFAULT 1, период TEXT
);

DROP TABLE IF EXISTS ceny_na_gruz;
CREATE TABLE ceny_na_gruz (           -- ЦеныНаГруз (общая цена склад+вес, без вида товара)
    склад TEXT, вес_от REAL DEFAULT 0, вес_до REAL DEFAULT 1e12,
    цена REAL DEFAULT 0, экспресс_цена REAL DEFAULT 0, по_весу INTEGER DEFAULT 0,
    цена_авиа REAL DEFAULT 0, авиа_по_объему INTEGER DEFAULT 0,
    цена_бренд REAL DEFAULT 0, цена_z REAL DEFAULT 0, цена_бренд_авиа REAL DEFAULT 0,
    срок_действия TEXT, период TEXT
);

DROP TABLE IF EXISTS koef_dorozhnyh;
CREATE TABLE koef_dorozhnyh (         -- КоэффициентыДорожныхРасходов
    склад TEXT, коэффициент REAL DEFAULT 0, расчет_по_таблице INTEGER DEFAULT 1, период TEXT
);

DROP TABLE IF EXISTS cena_doprashodov;
CREATE TABLE cena_doprashodov (       -- ЦенаДопРасходов
    вес_от REAL DEFAULT 0, вес_до REAL DEFAULT 1e12, цена REAL DEFAULT 0,
    по_весу INTEGER DEFAULT 1, период TEXT
);

DROP TABLE IF EXISTS tarify_perevozka;
CREATE TABLE tarify_perevozka (       -- тп_ТарифыНаПеревозку (для ветки «по новому»)
    вид_тарифа TEXT, город_отправки TEXT, вес_от REAL DEFAULT 0, вес_до REAL DEFAULT 1e12,
    цена REAL DEFAULT 0, по_весу INTEGER DEFAULT 1, период TEXT
);

DROP TABLE IF EXISTS ceny_rastamozhka;
CREATE TABLE ceny_rastamozhka (       -- тп_ЦеныНаРастаможку
    вид_товара TEXT, цена REAL DEFAULT 0, по_весу INTEGER DEFAULT 0,
    по_количеству INTEGER DEFAULT 0, логистика_включена INTEGER DEFAULT 0, период TEXT
);

DROP TABLE IF EXISTS nacenki_tovar;
CREATE TABLE nacenki_tovar (          -- тп_НаценкиНаТовар
    вид_наценки TEXT, наценка REAL DEFAULT 0, период TEXT
);

DROP TABLE IF EXISTS stavki_press;
CREATE TABLE stavki_press (           -- тп_СтавкиЗаПресс
    склад TEXT, тип_упаковки TEXT, магазин TEXT, ставка REAL DEFAULT 0, валюта_ставки TEXT, период TEXT
);

DROP TABLE IF EXISTS nastroyki_rascheta;
CREATE TABLE nastroyki_rascheta (     -- НастройкиРасчетаШК (флаги веток)
    расчет_экспресс INTEGER DEFAULT 1, расчет_авиа INTEGER DEFAULT 0,
    расчет_бренд INTEGER DEFAULT 0, расчет_z INTEGER DEFAULT 0, период TEXT
);

DROP TABLE IF EXISTS sklady;
CREATE TABLE sklady (                 -- Справочник тп_Склады
    ид TEXT PRIMARY KEY, код TEXT, наименование TEXT,
    город_отправки TEXT, страна TEXT, только_свои_цены INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS i_ckv ON ceny_klient_vid(вид_товара, тип_упаковки, склад, клиент);
CREATE INDEX IF NOT EXISTS i_ckg ON ceny_klient_gruppa(группа, тип_упаковки, склад, клиент);
CREATE INDEX IF NOT EXISTS i_cpv ON ceny_po_vidu(вид_товара, тип_упаковки, склад);
