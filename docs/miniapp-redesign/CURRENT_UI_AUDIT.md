# MR1. Аудит текущего Mini App

Дата: 13.09.2026. Исходный revision: `f99796a`.
Область: frontend после M1-M9. MR1 не завершает production deploy M10,
интеграцию M11 или реализацию нового дизайна.

## Статус и метод

**MR1 завершён.** Инвентаризация исходников, функциональный контракт,
воспроизводимый baseline и визуальная проверка выполнены. Галерея:
[`screenshots/baseline/index.html`](screenshots/baseline/index.html), машинные
результаты: [`manifest.json`](screenshots/baseline/manifest.json).

Baseline: 88 PNG; populated страницы на 320x568, 390x844, 768x1024 и 1280x800
в обеих темах; full-page на 390x844; отдельные системные и вложенные состояния.
`run-status=complete`, 0 browser/unmocked API errors, 88 уникальных файлов,
0 отсутствующих файлов и 0 расхождений SHA-256. Chrome 152.0.7977.84,
locale ru-RU, timezone Europe/Moscow, DPR 1, reduced motion, фиксированное время.

PNG просмотрены вручную на основных мобильных/desktop страницах, sheets,
delete dialog, OFF review, empty/error, safe area, offline и конфликте темы.
Реальные Telegram WebView, backend, камера, torch и screen reader не проверялись;
эти ограничения не подменяются browser fixtures.

Источники требований: `BOT_MINIAPP_REDESIGNED_STAGED.md`, базовый `BOT_SPEC.md`,
дополнения 01/02, sharing и `BOT_SPEC_ADD_MINIAPP_STAGED.md`. При редизайне
визуальный порядок определяется MR, а предметная модель и безопасность остаются
в ведении прежних спецификаций и backend.

## Карта экранов

Все пути к исходникам ниже относительно `frontend/src/`.

| Route | Экран и вложенные сценарии | Состояние навигации |
| --- | --- | --- |
| `/` | Последний раздел из localStorage, иначе `default_section` | `app/App.tsx`, ключ `miniapp:last-section` |
| `/ration` | День, итоги КБЖУ, проценты, цели, приёмы пищи; details/edit/copy/delete записи | `pages/RationPage.tsx`; дата из query, затем локальный state |
| `/ration/add` | Поиск ингредиента/блюда, выбор источника, приём пищи, граммы и предпросмотр | `components/ration/RationAddSheet.tsx`; query `date`, `meal` |
| `/food` | Ингредиенты/блюда, поиск, сортировка, пагинация, фильтр папок, множественный выбор | `pages/FoodPage.tsx`; фильтры и выделение в state |
| `/food/new` | Создание ингредиента или блюда, поиск/порядок/граммы компонентов | `FoodEditorSheet`; query `kind` |
| `/food/share/:token` | Preview, конфликты, импорт, собственная/импортированная/недоступная ссылка | `pages/SharePreviewPage.tsx` |
| `/weight` | Текущий вес, цель, график, диапазон, история; создание/изменение/удаление веса и цели | `pages/WeightPage.tsx`; lazy route, период в state |
| `/profile` | Тема, числа, timezone, поведение после добавления, подтверждения, цели, напоминания, экспорт и удаление | `pages/ProfilePage.tsx` |
| `/privacy-policy` | Публичная политика и ссылка назад | Отдельный layout; не требует успешной авторизации |
| `*` | Неизвестный раздел и нижняя навигация | Общий `ErrorState` |

Ещё внутри `/food`: редактирование строки каталога, delete-consequences и
подтверждение удаления, создание/переименование/порядок/удаление папки,
перенос одной или нескольких позиций, создание/copy/send/revoke sharing-ссылки,
камера/manual barcode, найденный или отсутствующий OFF-продукт, ручная проверка
данных, создание ингредиента и открытие дубля. Это не отдельные routes.

## Общие компоненты

| Группа | Состав | Что сохранять / учитывать |
| --- | --- | --- |
| Bootstrap | `main.tsx`, `app/App.tsx`, `context.ts` | React StrictMode, QueryClient, Router; авторизация до рабочих экранов |
| Telegram | `telegram/adapter.ts`, `hooks.ts`, `types.ts` | ready/expand, theme/viewport subscriptions, BackButton; browser preview не изобретает initData |
| Layout | `AppShell`, `TopBar`, `BottomNavigation` | Четыре раздела, active state, offline-индикатор, сохранение последнего раздела |
| Формы | `FormField`, `SegmentedControl`, `IconButton` | Labels, aria-describedby/invalid, aria-pressed, icon labels/title |
| Данные | `MetricTile`, `ProgressBar`, `DateSwitcher` | Единицы, ограничение видимого прогресса, день/timezone и возврат сегодня |
| Состояния | `States`, `Toast`, `toast-context` | Skeleton, empty, error/retry, live region и закрытие уведомления |
| Overlays | `BottomSheet`, `ConfirmDialog` | Escape, backdrop, стартовый фокус; замечания к модальности ниже |
| Рацион | `RationAddSheet`, `RationEntrySheet` | Поиск, предпросмотр, граммы, перенос даты, copy, source snapshot, stale conflict |
| Вес | `WeightChart`, `WeightEntrySheet`, `WeightGoalSheet` | Recharts, доступная сводка, выбранная точка, заметки, цель и её прогресс |
| Еда | `FoodEditorSheet`, `FolderManagerSheet`, `BarcodeScannerSheet`, `camera.ts` | Состав и поиск, зависимости, папки, проверка OFF и остановка MediaStream tracks |

## Контракт данных и операций

`api/client.ts` содержит DTO и fetch-функции. Идентификаторы и decimal остаются
строками; Number используется для отображения/локального предпросмотра, но не
заменяет серверные расчёты. Заголовок авторизации: `Authorization: tma <initData>`.
APIError хранит status, correlationId и details. Не добавлять секреты в UI/логи.

Все API-пути в таблице имеют префикс `/api/v1`.

| Область | Чтение / Query keys | Мутации и обязательное поведение |
| --- | --- | --- |
| Вход и UI | GET `/me`, `/ui-preferences`; `current-user`, `ui-preferences` | PATCH preferences; theme/default section/compact; setQueryData после успеха |
| Профиль | GET `/profile`, `/profile/stats`; `profile`, `profile-stats` | PATCH `/profile/settings`; timezone, number_format, after_food_add_action, confirm_deletions |
| Цели питания | GET `/goals/nutrition`; `nutrition-goal` | PUT nullable КБЖУ, enabled; сохранить отсутствие отдельных целей, не путать null и 0 |
| Напоминания | GET `/reminders`; `reminders` | POST, PATCH/DELETE `/:id`; weigh_in/nutrition, H:MM, weekdays, enable; обновить reminders/profile |
| Приватность | GET `/account/export` | POST deletion-request и deletion-confirm; token, контрольная фраза, TTL; два подтверждения; после удаления invalidate all |
| Рацион | GET `/ration/:date`, `/ration/sources?q&kind`; `ration`, `ration-sources` | POST `/:date/entries`, PATCH/DELETE `/ration/entries/:id`, POST `/:id/copy`; Idempotency-Key для create/copy; expected_updated_at для edit; обновить затронутые дни |
| Вес | GET `/weight?date_from&date_to`; `weight` | POST `/weight`, PATCH/DELETE `/:id`; строковый вес, local datetime, note; create-key и optimistic concurrency для edit |
| Цель веса | GET/PUT `/goals/weight`; `weight-goal` | enabled, target, nullable date; после мутации инвалидируются weight/weight-goal; UI берёт цель из range response |
| Каталог | GET `/ingredients`, `/dishes` с q/sort/cursor/folder_id; `food` | POST/PATCH/DELETE; ключ create, 409 existing; delete-consequences перед удалением; invalidate food/ration-sources |
| Поиск состава | GET `/ingredients?q`; `food-picker` | Локальные компоненты и граммы; итоговый POST/PATCH блюда содержит ingredient_id/grams |
| Папки | GET `/food-folders`; `food-folders` | POST, PATCH/DELETE `/:id`, POST `/reorder`, `/food-items/folder-batch`; удаление папки не удаляет еду; invalidate food/folders |
| OFF | POST `/barcodes/lookup` | POST `/barcodes/:barcode/create-ingredient`; confirmed/token, missing/derived fields, источник, nullable вес и фото, duplicate; никакого автоматического добавления сразу после сканирования |
| Sharing | GET `/sharing/packages/:token/preview`; `sharing-preview` | POST packages, DELETE `/:id`, POST `/:token/import`; ссылка/copy/send/revoke, owner/already_imported; текущий client выбирает reuse ингредиента/create_copy блюда для конфликтов |

GET ration summary и GET weight goal есть в client, но основной обзор использует
полные ответы day/range. Не добавлять дублирующие запросы ради нового layout.
Backend отвечает за подпись/TTL initData, изоляцию пользователей, повторные
мутации, проверку дублей, расчёт snapshot КБЖУ, OFF-кэш и ограничения запросов.
Этот аудит не утверждает, что браузерные fixtures проверяют backend.

## Наблюдения по экранам

### Рацион

Сохранить: КБЖУ в граммах даже без целей; явное превышение; численные проценты
рядом с кольцом; пустые приёмы пищи; source-deleted snapshot и запрет изменения
граммов при удалённом источнике; копирование и 409 refresh.

Evidence: [320x568 light](screenshots/baseline/ration-320x568-light.png),
[390x844 dark](screenshots/baseline/ration-390x844-dark.png),
[390x844 full](screenshots/baseline/ration-390x844-light-full.png),
[empty](screenshots/baseline/ration-empty-390x844-light.png),
[picker](screenshots/baseline/ration-picker-390x844-light.png),
[deleted source](screenshots/baseline/ration-deleted-source-390x844-light.png).

- `RationPage.tsx:284-306`: итог калорий повторяется в energy block, центре кольца
  и дневных целях. Приёмы пищи идут только после обеих сводок. MR2/MR5 должны
  сравнить более компактную композицию без потери чисел и превышения. Замер:
  meals начинаются на y=810 при первом viewport 320x568 и 390x844; на 390px их
  заголовок уже перекрывается нижней навигацией y=773, на 320px он ниже экрана.
- `styles.css:264-277,835`: кольцо и легенда используют фиксированные минимальные
  колонки. Горизонтального overflow рациона baseline не показал, но на планшете
  summary сжимается в левую часть двухколоночной сетки. Сохранить проверку
  длинных локализованных чисел и процентов в MR5.
- `styles.css:866-867`: на ширине <=350px калории каждой записи скрыты, а не
  перенесены. Это реальная потеря данных в списке, не просто вкусовой вопрос.
- `RationAddSheet.tsx:166`, `FoodPage.tsx:170`: переход из пустого поиска содержит
  `return=ration`, но closeEditor всегда возвращает `/food`. Возврат к исходному
  дню/приёму не реализован; не рисовать его как уже существующий контракт.

### Еда, папки и обмен

Сохранить: быстрый поиск, разделение ингредиент/блюдо, сортировку/cursor,
фильтр unfiled, множественный перенос, полную ссылку обмена, предостережение
при зависимостях, поиск ингредиентов состава и ручное исправление OFF.

Evidence: [390x844](screenshots/baseline/food-390x844-light.png),
[1280x800](screenshots/baseline/food-1280x800-light.png),
[selection](screenshots/baseline/food-selection-390x844-light.png),
[dish editor](screenshots/baseline/food-editor-dishes-390x844-light.png),
[folders 320x568](screenshots/baseline/food-folders-320x568-light.png),
[delete dialog](screenshots/baseline/folder-delete-320x568-light.png).

- **Высокая серьёзность:** заполненный `/food` имеет scrollWidth 458 при
  viewport 320 и 464 при viewport 390, в обеих темах. На 390px справа полностью
  уходят кнопки barcode/add, обрезаются вкладка «Блюда», сортировка и
  «Поделиться»; виден горизонтальный scrollbar. Empty имеет 401px, а error,
  loading и compact — 464px. Это воспроизводимый дефект layout, MR4/MR6.

- `styles.css:474-498`: кнопки выбора 34x34, переноса 34x38, папок 38x38;
  selected toolbar использует nowrap кнопки и не умеет переносить flex-строку.
  Размеры ниже требуемых 44x44; измерить особенно 320px. MR4/MR6.
- `styles.css:491,541,567`: длинные названия обрезаются до одной строки; это
  мешает различать похожие продукты/папки. Для папок дополнительно четыре
  действия в одной строке, для состава три маленьких действия 29x34. MR6.
- `FoodEditorSheet.tsx:284-289`: поиск состава показывает только первые восемь
  найденных вариантов; loading/error/empty не отображаются. При отказе API
  результат выглядит как пустой поиск. MR6 должен добавить отдельные состояния.
- `styles.css:556-559`, `FoodEditorSheet.tsx:253`: fields КБЖУ и metadata в двух
  колонках внутри sheet, без narrow override. Проверить не только ширину input,
  но и действие «Сохранить» после экранной клавиатуры. MR4/MR6.
- `FoodPage.tsx:126,257`: revoke/copy ошибки не представлены отдельными понятными
  UI-состояниями; clipboard rejection не перехватывается. MR6; сейчас не исправлять.
- `SharePreviewPage.tsx`, `client.ts:1025`: конфликтующие ингредиенты повторно
  используются автоматически, блюда копируются. Не рисовать выбор стратегии,
  которого нет в текущем UI; новую политику согласовывать отдельно.

### Штрихкод

Сохранить: запуск камеры по действию, manual fallback, torch при поддержке,
подтверждение данных перед созданием, missing fields, рассчитанные ккал,
ссылку OFF и duplicate opening. Видеопоток не отправляется в backend.

Evidence: [manual](screenshots/baseline/barcode-manual-390x844-light.png),
[permission denied](screenshots/baseline/barcode-denied-390x844-light.png),
[found review](screenshots/baseline/barcode-review-populated-390x844-light.png),
[missing fields](screenshots/baseline/barcode-review-barcode-missing-390x844-light.png).

- `styles.css:500,518-525`: preview 4:3, фото проверки 72x72, длинное название
  обрезано. Фото с object-fit:contain сохраняет упаковку, но размер и отсутствие
  увеличения затрудняют проверку. MR6 должен проверить это на реальном фото.
- `BarcodeScannerSheet.tsx:124-169`: асинхронный startCamera не защищён от
  повторного старта/закрытия во время pending разрешения. Это риск по коду;
  отказ в fixtures не доказывает корректность жизненного цикла реальной камеры.
- `BarcodeScannerSheet.tsx:213,242`: close останавливает камеру, но не сбрасывает
  review/form. Повторное открытие может вернуть старую карточку. Нужно явно
  решить ожидаемое поведение в MR6 и покрыть тестом.

### Вес

Сохранить: actual/7d average/goal, разные штрихи линий и текстовую сводку;
несколько измерений за день; отметку времени, note, диапазоны 7/30/90/180/365
и custom <=365; nullable start weight; backend progress; 409 refresh.

Evidence: [320x568](screenshots/baseline/weight-320x568-light.png),
[390x844](screenshots/baseline/weight-390x844-light.png),
[1280x800](screenshots/baseline/weight-1280x800-light.png),
[custom range](screenshots/baseline/weight-custom-range-390x844-light.png).

- `WeightPage.tsx:171-194`: цель/прогресс повторяются в metric tile и отдельной
  сводке. На мобильном график расположен ниже обоих блоков. Замер: chart y=531;
  при 320x568 он начинается уже под навигацией y=482, при 390x844 видна только
  верхняя часть. На desktop chart y=172 и читается сразу. MR2/MR7.
- `WeightChart.tsx:54-61`: дальняя цель входит в Y-domain и сжимает амплитуду
  фактических изменений. Нужна осмысленная композиция/шкала, без искажения данных.
- `WeightChart.tsx:87`: selectable circle имеет r=5 (10px), активный r=7;
  этого мало для точного touch. Клавиатурный Enter/Space уже поддерживается.
- Сейчас нет pan/pinch и контроллера видимого окна. Это новая функциональность
  MR7, а не поломка уже реализованного жеста. Сохранить требования пользователя:
  один палец листает время, два меняют масштаб вокруг midpoint; окно 7-365 дней,
  без ухода в будущее, запрос после жеста, вертикальный scroll, tap/drag threshold,
  кнопки/мышь/reset. Recharts остаётся движком отрисовки.
- `styles.css:844-845`: note скрыта в мобильной истории; сам текст доступен через
  редактирование. Решить, нужна ли в списке отметка наличия заметки. MR7.

### Профиль и приватность

Сохранить: настройки сервера отдельно от UI preferences, H:MM без первого нуля,
weekdays, enable, экспорт JSON, публичную политику, два шага удаления и фразу,
версию из ответа API, а не из frontend package.json.

Evidence: [390x844](screenshots/baseline/profile-390x844-light.png),
[full page](screenshots/baseline/profile-390x844-light-full.png),
[1280x800](screenshots/baseline/profile-1280x800-light.png),
[deletion challenge](screenshots/baseline/profile-delete-challenge-390x844-light.png).

- **Высокая серьёзность:** profile имеет scrollWidth 374 при viewport 320 и
  402 при viewport 390; виден горизонтальный scrollbar. Первая причина для MR4
  — min-content ширина сегментированных controls/форм. Высота заполненной страницы
  2716px на 390, поэтому приватность и удаление находятся далеко от первого экрана.

- `ProfilePage.tsx:578-606`: большие формы целей и двух напоминаний всегда
  раскрыты. Экспорт/приватность ниже длинной страницы. MR8 должен рассмотреть
  settings rows с отдельными editor views, сохранив все поля.
- `styles.css:663,821`: статус напоминаний позиционируется с отрицательным
  margin-top на узком экране. Нужен замер с длинным именем. MR4/MR8.
- `styles.css:727,860`: дни недели ниже 44px. У switch-row фактическая зона
  label больше checkbox; не считать каждый маленький native checkbox дефектом
  без проверки clickable label. У компактного переключателя нужен отдельный замер.
- `ProfilePage.tsx:541-576`: default_section есть в preferences/API, но UI выбора
  отсутствует. confirm_deletions и after_food_add_action сохраняются, однако
  редакторы рациона/еды не читают их. Зафиксировать расхождение, не обещать
  пользователю действующее поведение и не убирать настройки молча. MR8/MR9.
- `ProfilePage.tsx:594`: пользователь видит технический текст про планировщик.
  Сократить в MR8, не менять юридические подтверждения удаления.

## Сквозные риски

1. **Модальность и черновики (MR4).** `BottomSheet.tsx:16-24`,
   `ConfirmDialog.tsx:24-32`: есть стартовый фокус/Escape, но нет focus trap,
   возврата фокуса, inert фона, scroll lock и guard несохранённых изменений.
   BackButton отслеживает путь, поэтому не учитывает sheets, открытые state
   внутри `/food`, `/weight`, `/profile`. Измерение подтвердило: после фокуса
   последней кнопки ration sheet и Tab активным стал `<a>` вне dialog
   (`diagnostics.sheet-tab-focus.insideDialog=false`).
2. **Тема Telegram против явного выбора (MR4).** `styles.css:5-13,31-39`:
   Telegram CSS variables имеют приоритет в обеих темах. dataset=dark не отменяет
   светлые значения bridge. [Baseline](screenshots/baseline/ration-telegram-light-override-390x844-dark.png)
   подтвердил dataset=dark при body background rgb(255,255,255): результат
   смешивает светлые Telegram-поверхности с тёмными fallback-границами.
3. **Safe area / клавиатура (MR4/MR9).** Shell использует max safe/content insets,
   но sheet ограничен `82vh` и padding учитывает только safe-bottom
   (`styles.css:776`), не content-safe-bottom/динамическую клавиатуру.
   [Synthetic 24/34px insets](screenshots/baseline/food-safe-area-390x844-light.png)
   не перекрывают topbar/nav, но desktop Chromium не подтверждает iOS/Android
   WebView-поведение и экранную клавиатуру.
4. **Согласованность ввода (MR4).** FormField input 16px, food filters/range select
   13px, custom date наследует 11px. Свести токены без простого уменьшения текста.
5. **Обновление кэша (MR9).** Цели/настройки профиля обновляют собственный query,
   но не инвалидируют рацион/current-user; проверить немедленное применение
   timezone/формата/целей при возврате. Не менять API ради устранения этого риска.
6. **Offline не реактивен (MR4/MR9).** `TopBar.tsx:13` читает
   `navigator.onLine` во время рендера, но не подписывается на `online/offline`.
   Индикатор появится, если приложение уже открыто без сети, но не при потере
   соединения на неизменённом экране. [Cold offline](screenshots/baseline/food-offline-indicator-390x844-light.png)
   показывает значок; отдельного поведения запросов/retry нет.
7. **Состояния ошибок.** ErrorState общий с retry, но поля серверной валидации
   не сопоставляются с inputs во всех формах; часто выводится только message.
   Нужны field-level acceptance tests MR4/MR6/MR8.

## CSS-инвентаризация

Один `styles.css` (872 строки). Tokens: app bg/surface/raised/text/muted/border,
primary/primary-text/link/danger, macro protein/fat/carbs/energy, focus ring,
stable height и safe/content insets. Palette: нейтрально-зелёная основа,
зелёный белок, коралловый жир, синий углевод, охристая энергия; обе темы заданы.

Magic values: shell 1120, page 960, sheet 680/720/82vh, topbar 62, nav 70,
content bottom padding 94/112; плотности 34/36/38/40/42/44/46/48/52/62/72;
радиусы 5/6/7/8; множество подписей 9/10/11/12/13px. Breakpoints 350/520/768.
Повторяются date/time/decimal formatters и mutationKey в страницах/редакторах;
это кандидаты для последующего осторожного упорядочивания, не повод для
отдельного массового рефакторинга MR1.

Предположительно неиспользуемые `.food-open`, `.toolbar-row`, `.summary-value`
нужно повторно проверить перед удалением в MR4. Не удалены в этом этапе.

## Состояния и пробелы покрытия

| Область | Проверено fixtures + Chrome baseline | Остаётся проверить позже |
| --- | --- | --- |
| Четыре раздела | Populated, empty, error/retry surface, loading; 4 размера x 2 темы | Реальный backend и переходы после всех успешных мутаций |
| Рацион | Без целей, превышение, future, удалённый источник, picker/portion/edit/copy | Реальный 409, смена timezone на границе дня, большой рацион |
| Еда | Длинные имена, compact, selection/share/move, folder delete, editor, duplicate | Cursor pages, 1000+ позиций, rename/reorder persistence, ошибки вложенного поиска |
| OFF | Manual, camera denied, found без фото, missing, review | Настоящее фото/битый URL, permissions prompt, torch, реальное сканирование и остановка при фоне |
| Вес | 14 точек, два измерения за день, entry/goal/custom forms, пустой диапазон | Одна точка в браузере (есть unit), большой разрыв дат, achieved goal, future validation, pan/pinch MR7 |
| Профиль | Полная страница, reminder forms, delete warning/challenge, privacy | Export download, challenge expiry, мутации/reset, WebView keyboard |
| Общие | Auth 401, safe area, offline indicator, theme override, Tab из sheet | Real offline/reconnect, 403/404/429, screen reader, contrast audit, Telegram iOS/Android/Desktop |

Имеющиеся тесты: 27 tests в 4 файлах. `App.test.tsx` проверяет routes, preview,
nav/last section/BackButton, открытие editor/folders/barcode/ration/weight,
custom range, theme, future date, публичную политику и safe area;
`adapter.test.ts` проверяет bridge/fallback/events; `ui.test.tsx` проверяет
progress clamp, связь ошибок с полями, Escape; `WeightChart.test.tsx` проверяет
одну и несколько доступных точек. Нет полноценного тестирования мутаций всех
форм с ответами API и нет доказательства реальной touch/WebView доступности.

В MR1 добавлены четыре unit-теста fixtures: равенство итогов рациона сумме
приёмов/записей, разделение empty/no-goals/deleted-source, согласованность состава
блюда и истории веса, отсутствие выдуманных ответов неизвестных мутаций.
Итог проверки: **31 test / 5 файлов проходят**, lint, typecheck и build проходят.
`git diff --check` без ошибок. Backend-тесты не запускались: backend и
production frontend исходники не изменены. Browser capture завершён отдельно:
88 снимков, строгая проверка 0 page/unmocked API errors.

## Переход к MR2

Следующим этапом MR2 готовит два варианта рациона (390x844, обе темы,
sheet добавления, empty/populated meals и превышение), а не переписывает CSS.
Приоритет сравнения: видимость еды/добавления, компактность сводки без потери
данных, читаемость длинных названий и размер действий. Панорамирование веса
остаётся в blueprints и критериях MR7. Выбор концепции делает пользователь.

Версия приложения для MR1 не меняется. Новый release tag не требуется.
