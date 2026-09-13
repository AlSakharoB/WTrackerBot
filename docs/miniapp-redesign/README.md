# Mini App Redesign

Работа ведётся по `BOT_MINIAPP_REDESIGNED_STAGED.md`. Этот каталог содержит
аудит текущего UI, сравнение концепций, утверждённое визуальное направление,
дизайн-систему, полные screen blueprints и production foundation.

Текущий статус: MR4 завершён. Выбрано направление A с круговой диаграммой КБЖУ
из B. В production перенесены semantic tokens, общий shell и базовые компоненты;
существующие страницы и API-сценарии сохранены. Решение зафиксировано в
`DESIGN_DIRECTION.md`, токены и правила — в `DESIGN_SYSTEM.md`, все экраны и
состояния — в `SCREEN_BLUEPRINTS.md`. Контрольная галерея нового shell находится
в `screenshots/mr4-shell/index.html`.

## Повторение проверки MR4

При работающем frontend выполните из `frontend`:

```bash
UI_AUDIT_OUTPUT=../docs/miniapp-redesign/screenshots/mr4-shell \
UI_AUDIT_TITLE='MR4: общий shell' npm run audit:ui
```

Скрипт создаёт 89 снимков: обязательные viewport и темы, основные состояния,
sheet/dialog flows, safe area, offline и длинный заголовок. Поля проверяются на
мобильный размер шрифта, а интерактивные элементы — по фактической зоне нажатия,
включая полную область label для checkbox.

## Повторение финальных blueprints

В первом терминале запустите frontend:

```bash
cd frontend
npm run dev -- --strictPort
```

Во втором терминале из `frontend` сделайте восемь контрольных снимков:

```bash
npm run design:capture-final
```

Финальное направление открывается с `concept=selected`. Доступные страницы:
`ration`, `food`, `weight`, `profile`, `barcode`; тема задаётся через
`theme=light|dark`. Скрипт проверяет отсутствие browser errors, размеры shell,
touch targets, первый приём пищи и загрузку product photo, затем записывает
результат и SHA-256 в `screenshots/final/manifest.json`.

## Повторение концепций

В первом терминале запустите frontend:

```bash
cd frontend
npm run dev -- --strictPort
```

Во втором терминале из того же каталога сделайте 18 снимков:

```bash
npm run design:capture
```

Прототип доступен по `/design/ration-concepts/` и принимает query-параметры
`concept=a|b`, `page=ration|food|weight|profile`, `theme=light|dark`, `sheet=1`.
Его код находится вне `src` и не включается в production build. Для установленного
браузера можно использовать те же `UI_AUDIT_EXECUTABLE` или `UI_AUDIT_CDP_URL`,
что и baseline capture.

## Повторение baseline

Из корня проекта:

```bash
cd frontend
npm ci
npx playwright install chromium --only-shell
```

Нужен один локальный frontend. Если `http://127.0.0.1:5173` уже работает,
используйте его. Иначе в отдельном терминале:

```bash
npm run dev -- --strictPort
```

Снимки снимаются второй командой из `frontend`:

```bash
npm run audit:ui
```

Скрипт не запускает сервер и не переключается сам на 5174. При необходимости
можно указать другой локальный frontend через `UI_AUDIT_URL`. Внешние адреса
запрещены. `UI_AUDIT_EXECUTABLE` позволяет указать уже установленный совместимый
Chromium, а `UI_AUDIT_CDP_URL` — локальный Chrome DevTools endpoint. По умолчанию
используется версия Playwright из lockfile.

Результат: `screenshots/baseline/index.html`, PNG и `manifest.json`.
Галерея открывается как обычный HTML-файл, без сервера. В manifest записываются
размеры элементов, маленькие зоны нажатия, список запросов без заголовков,
версия браузера, revision кода, хеш fixtures и хеши PNG.

Для сравнения, не перезаписывая исходный baseline:

```bash
UI_AUDIT_OUTPUT=/tmp/miniapp-ui-comparison npm run audit:ui
```

Это запись состояния, а не тест на отсутствие UX-дефектов. Известный overflow
и маленькие кнопки должны остаться на исходных снимках. Неизвестный API-запрос
или JavaScript-ошибка останавливают успешное завершение команды.
Проверять `run-status.json`: только `complete` означает успешный текущий прогон.

## Изоляция

- Все ответы `/api/**` перехватываются в тестовом браузере. Неизвестные запросы
  получают тестовую ошибку, а не отправляются в backend.
- `/internal/**` блокируется; внешние HTTP-запросы не уходят в интернет.
- Telegram SDK заменён минимальным bridge со строкой `AUDIT_SYNTHETIC_NOT_VALID_AUTH`.
  Это не обход авторизации приложения: фиктивная строка не принимается сервером
  и не покидает перехватчик Playwright.
- Fixtures не содержат реальных пользователей, токенов, фотографий или экспортов.
  Запись в БД, Telegram, Open Food Facts и реальная камера не используются.
- Разрешение камеры заменено отказом. Offline-снимок проверяет только индикатор,
  а не доставку запросов при реальном разрыве соединения.
- Время фиксировано: `2026-09-13T09:00:00Z`, timezone `Europe/Moscow`, locale `ru-RU`,
  DPR 1, reduced motion. Для каждого самостоятельного сценария создаётся новый
  контекст браузера без сохранённых cookies/localStorage.
- PNG могут отличаться между ОС и версиями Chromium из-за системных шрифтов.
  Сравнивать пиксели следует в одинаковом окружении.

## Проверки

```bash
cd frontend
npm run lint
npm run typecheck
npm test
npm run build
```

Зависимость Playwright нужна только для разработки, в production bundle она
не включается. Исходный baseline MR1 остаётся неизменным для сравнения.
