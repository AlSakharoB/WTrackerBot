# Baseline MR1

Baseline завершён 13.09.2026: 88 PNG, `run-status.json` содержит `complete`,
а `manifest.json` — 0 JavaScript/unmocked API errors. Все PNG присутствуют и
совпадают с записанными SHA-256.

Проверены populated страницы на 320x568, 390x844, 768x1024 и 1280x800 в
светлой и тёмной теме. На 390x844 также записаны full-page варианты.
Дополнительно сняты loading/empty/error, no-goals, future/auth/offline/safe-area,
sharing/import, selection/move/folders/duplicate, ration sheets, food editors,
barcode manual/denied/found/missing, weight forms и удаление аккаунта.

Начать просмотр: [`baseline/index.html`](baseline/index.html). Метрики,
маршруты, API-запросы и hashes: [`baseline/manifest.json`](baseline/manifest.json).

Снимки получены Windows Chrome 152.0.7977.84 через локальный CDP relay, потому
что официальный Playwright CDN был недоступен из WSL. Это влияет на системный
шрифт и вид scrollbars, но не на измеренные CSS layout boxes. Обычная команда
из `../README.md` остаётся предпочтительным способом повторения.

Baseline хранит известные дефекты текущего интерфейса, включая горизонтальный
overflow. Это намеренно: PNG фиксируют исходное состояние до MR4.

## Концепции рациона

Каталог [`concepts`](concepts/index.html) содержит два направления на одинаковых
данных и viewport `390x844`: рацион, еду, вес и профиль в обеих темах, а также
add-sheet для каждого направления. Параметры и SHA-256 всех 18 снимков записаны
в `concepts/manifest.json`.

## Финальное направление MR3

Галерея [`final`](final/index.html) содержит восемь browser-rendered blueprints
утверждённой комбинации A с кольцом КБЖУ из B: рацион в обеих темах, каталог,
проверку продукта после Open Food Facts, вес в обеих темах, профиль и desktop.
Параметры, layout-метрики, версия браузера и SHA-256 записаны в
[`final/manifest.json`](final/manifest.json). `run-status.json` должен иметь
статус `complete` и восемь captures.

## Production foundation MR4

Галерея [`mr4-shell`](mr4-shell/index.html) содержит 89 снимков production UI
после переноса semantic tokens, общего shell и базовых компонентов. Проверены
все обязательные viewport, light/dark, Telegram theme override, safe area,
offline, длинный заголовок, loading/empty/error и вложенные sheet/dialog flows.

В [`mr4-shell/manifest.json`](mr4-shell/manifest.json) нет browser/API errors,
horizontal overflow, пересечений нижней навигации или полей со шрифтом меньше
16px. Оставшиеся маленькие интерактивные элементы в метриках — точки прежнего
графика веса; их pointer, keyboard и gesture-модель будет заменена целиком на
этапе MR7.
