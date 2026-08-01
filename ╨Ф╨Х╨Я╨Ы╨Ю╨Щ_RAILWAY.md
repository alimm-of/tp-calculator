# Деплой на Railway через GitHub

Приложение уже подготовлено: `Procfile`, `requirements.txt` (с gunicorn),
порт берётся из `PORT`, база создаётся автоматически из `sample/prices_sample.json`.

## Шаг 1. Залить код в GitHub

В папке проекта (эта распакованная папка) выполните:

```bash
git init
git add .
git commit -m "Веб-калькулятор цен ТП"
git branch -M main
git remote add origin https://github.com/ВАШ_ЛОГИН/tp-calculator.git
git push -u origin main
```

Репозиторий на GitHub создайте заранее (New repository → без README, пустой).

## Шаг 2. Развернуть на Railway

1. https://railway.app → **New Project** → **Deploy from GitHub repo**.
2. Выберите репозиторий `tp-calculator` (при первом разе — дать Railway доступ к репо).
3. Railway сам определит Python, установит `requirements.txt` и запустит команду из `Procfile`.
4. Дождитесь сборки (вкладка **Deployments** → лог).

## Шаг 3. Открыть сайт

1. Вкладка **Settings** сервиса → раздел **Networking** → **Generate Domain**.
2. Получите адрес вида `https://tp-calculator-production.up.railway.app`.
3. Откройте — увидите калькулятор. По умолчанию работает на тестовых данных (sample).

## Обновление цен

Реальные цены: выгрузите `цены.json` из базы ТП (внешняя обработка
`ВыгрузкаЦен_JSON_МодульФормы.bsl`), затем два варианта:

- **Просто:** положите файл как `sample/prices_sample.json`, удалите строку с sample —
  замените своим, закоммитьте и `git push`. Railway пересоберётся, БД обновится из него.
- **Через переменную:** в Railway → **Variables** задайте `SEED_JSON=sample/мои_цены.json`,
  положив файл в репозиторий.

## Обновление кода

Любой `git push` в `main` → Railway автоматически пересобирает и деплоит.

## Важно про базу

БД (`prices.db`) пересоздаётся при каждом рестарте контейнера из JSON —
это нормально для калькулятора (данные только на чтение). Ничего вручную
на сервере хранить не нужно.
