# Screen blueprints WTracker Mini App

Статус: проект для второго подтверждения. Дата: 13.09.2026.
Визуальная основа: A с кольцом КБЖУ из B. API и предметная логика не меняются.

## 1. Общий shell

### Порядок

1. Compact top bar: знак W, WTracker, контекст раздела, saved/offline status.
2. Scrollable page content.
3. Fixed bottom navigation: Рацион, Еда, Вес, Профиль.
4. Toast layer над navigation.
5. Scrim и один активный sheet/dialog поверх shell.

### Первый viewport

На телефоне header занимает `58px + safe-top`, navigation —
`66px + safe-bottom`. Между ними виден заголовок текущей рабочей страницы и
начало primary content. Marketing, onboarding и пояснение возможностей сюда
не добавляются.

### Действия и sticky

Bottom navigation остаётся fixed. Header фиксируется только если измерения
WebView не вызывают скачок; иначе он является первым стабильным блоком страницы.
Primary page action находится справа от page title или section title и имеет
полную подпись. На `320px` подпись можно заменить знаком Plus только с
`aria-label` и tooltip.

### Системные состояния

| State | Blueprint |
| --- | --- |
| Initial auth | Геометрический skeleton shell; nav disabled до `/me` |
| Offline cold start | Видимый «Нет сети», cached data остаются с датой обновления |
| Offline transition | Реактивный indicator; pending mutation не объявляется успешной |
| 401 | Один auth error с повторным открытием через Telegram, без бесконечного retry |
| 403/404 | Предметное сообщение, безопасное действие назад |
| 429 | Время ожидания, disabled повтор до разрешённого момента |
| 5xx/network | Сохранить контекст страницы, показать correlation ID и retry |
| Unknown route | «Раздел не найден» и переход в рацион |
| Success | Короткий `role=status` toast, данные уже обновлены |

Skeleton повторяет итоговые строки/график. Empty state не занимает весь экран,
если рядом остаётся полезное действие. Error не стирает локальный draft формы.

### Overlays и keyboard

При открытом overlay фон inert, body locked, focus trapped. Telegram BackButton
закрывает верхний overlay раньше route. Sheet body прокручивается независимо,
footer учитывает `max(safe-bottom, content-safe-bottom)` и keyboard. После
закрытия focus возвращается на trigger. Изменённый draft требует confirm.

### Mobile и desktop

На `320-799px` один основной столбец. На `>=800px` shell до `1120px`, связанные
обзор/список могут стать двумя колонками. Bottom navigation сохраняет четыре
раздела и не превращается в отдельную административную sidebar.

## 2. Рацион `/ration`

### Порядок populated day

1. Date switcher: previous, текущая дата/день недели, next.
2. Hybrid summary: статус цели, donut БЖУ, численная легенда, калории/цель.
3. Заголовок «Приёмы пищи» и primary «Добавить».
4. Завтрак, обед, ужин, перекус, другое при наличии.
5. Внутри заполненного приёма — entries; пустой сохраняет inline add action.

### Первый viewport

На `390x844` видны ответы на четыре вопроса: итог калорий, остаток/превышение,
распределение БЖУ и минимум один заполненный приём пищи. На `320x568` видны
summary, заголовок приёмов и primary add. Нижняя навигация ничего не перекрывает.

### Summary

Центр кольца: фактические калории и цель. Легенда: Белки/Жиры/Углеводы,
фактические граммы, target и процент. При превышении отдельный текст
«Цель превышена на …», danger accent и `118%`; кольцо остаётся распределением,
а не progress >100. Длинные числа используют tabular digits и не меняют сетку.

### Meal и entry

Meal header показывает название, суммарные ккал и БЖУ, Plus 44px. Entry содержит
тип, название до двух строк, граммы, ккал и menu. Полные КБЖУ доступны в entry
sheet. Удалённый source отмечается «Источник удалён»; snapshot остаётся видимым,
изменение граммов disabled, copy/delete доступны по серверному контракту.

### Добавление `/ration/add`

Первый sheet: tabs Все/Ингредиенты/Блюда, search input, recent/results, empty/error.
Выбор source открывает второй view того же sheet: название, meal selector,
граммы/stepper, live preview КБЖУ, submit. Primary: «Добавить в …».
Secondary: назад к поиску и смена приёма. Create использует Idempotency-Key.

Если поиск пуст, действие «Создать ингредиент» ведёт в food editor и сохраняет
return date/meal. После успешного создания пользователь возвращается к исходному
рациону, а новый продукт уже выбран или доступен первым результатом.

### Entry sheet

Details показывает source name, snapshot, граммы, КБЖУ, дату и meal. Действия:
Изменить, Копировать, Удалить. Edit сохраняет `expected_updated_at`; 409 оставляет
sheet открытым, объясняет конфликт и предлагает обновить данные. Copy выбирает
дату/meal и имеет собственный idempotency key. Delete требует confirm согласно
настройке пользователя, но последствия всегда названы.

### Варианты

| State | Blueprint |
| --- | --- |
| Без целей | Кольцо и граммы остаются; target заменён «не задана», ссылка в профиль |
| Пустой день | Нейтральное кольцо, 0 ккал, четыре компактных empty meals, add рядом |
| Пустой meal | Заголовок/0 ккал и inline «Добавить еду» |
| Будущая дата | Badge «Будущий день»; add разрешён по текущему backend contract |
| Loading | Date switcher стабилен; skeleton summary и первых meals |
| Error | Дата сохраняется; error/retry вместо данных |
| Большой рацион | Page scroll; meal cards не имеют вложенного scroll |
| Long name | До двух строк, ккал/menu не выталкиваются |

### Desktop

Date switcher остаётся сверху. Ниже summary слева (`~360px`), meals справа.
Meals раскладываются в две колонки, но порядок чтения остаётся завтрак → обед →
ужин → перекус. Sheet центрируется, max-width `680px`.

## 3. Еда `/food`

### Порядок каталога

1. Page title, scanner icon, primary «Добавить».
2. Search и filter/sort action.
3. Segmented Ингредиенты/Блюда с количеством.
4. Горизонтальная folder strip: Все, пользовательские, Без папки, manager.
5. Cursor-paginated rows.
6. Selection toolbar вместо обычных page actions при выборе.

### Первый viewport

На `390x844` видны search, оба типа, folders и минимум три строки. Barcode и
add доступны без scroll. Горизонтальный scroll разрешён только внутри folder
strip; document width всегда равен viewport.

### Product row

Строка показывает icon типа, название до двух строк, `ккал · Б · Ж · У / 100 г`,
folder label и menu. Tap строки открывает editor/details. Checkbox появляется
только в selection mode, но вся label area не меньше 44px.

### Selection mode

Long press или действие «Выбрать» включает checkbox. Toolbar показывает число,
«В папку», «Поделиться», «Снять выбор». Mixed ingredient/dish разрешён согласно
sharing contract. После batch move список и folders инвалидируются; ошибка
сохраняет выделение для retry.

### Папки

Folder manager sheet содержит create input и rows с rename, reorder, delete.
Reorder доступен drag handle и кнопками вверх/вниз. Delete dialog прямо сообщает,
что продукты останутся без папки. Empty folder показывает фильтр, 0 позиций и
действия «Добавить продукт»/«Переместить существующие».

### Ingredient editor

Поля: name, energy, protein, fat, carbs на 100 г, barcode/source metadata при
наличии, folder. Inputs 16px; decimal принимает comma/dot согласно настройке.
Primary footer «Сохранить» sticky над keyboard. Server field errors связываются
с inputs. Закрытие изменённого draft требует confirm.

### Duplicate state

409 не выглядит общей ошибкой. Inline notice показывает найденный объект,
причину совпадения и действия «Открыть существующий»/«Изменить название».
Новый объект не создаётся. Для нескольких кандидатов показывается короткий список
с именем и КБЖУ, окончательное решение остаётся серверным.

### Dish editor

Сверху name/folder. Ниже search ингредиентов с loading/error/empty, результаты
не ограничиваются молча восемью без действия «Показать ещё». Выбранный состав
показывает ingredient, grams, move/remove. Итог рецепта пересчитывает общий вес,
ккал и БЖУ на 100 г. Delete ingredient dependency возвращает понятный переход
к затронутому блюду.

### Sharing

Selection → preview package → create link. Sheet показывает полный Telegram URL,
срок/статус, copy/send/revoke. Clipboard failure предлагает выделяемое поле.
Public preview перечисляет owner-neutral состав, конфликты и итог import.
Повторный import разрешается после удаления импортированных объектов согласно
актуальному backend contract; idempotency защищает одновременный повтор запроса.

### Состояния каталога

| State | Blueprint |
| --- | --- |
| Полностью пусто | Search/types остаются, illustration не нужна, primary add + scanner |
| Пустая папка | Название папки, 0, move/add actions |
| Нет результатов | Query виден, clear и create ingredient/dish |
| Loading page | Стабильные filters, 4 row skeletons |
| Next cursor loading | Старые rows остаются, progress внизу |
| Error | Filters/query сохраняются; retry конкретного списка |
| Long catalog | Window/page scroll, sticky selection toolbar |

### Desktop

Filters остаются сверху в одну строку; list получает максимум читаемой ширины.
При `>=960px` folders могут стать левой колонкой `220px`, список — правой.
Editor sheet остаётся ограниченным по ширине, dish composition может иметь две
колонки search/selected.

## 4. Barcode scanner и Open Food Facts

### Scanner sheet

1. Heading и close.
2. Camera viewport 4:3 с рамкой и live status.
3. Torch button только при capability.
4. Primary scan/start action.
5. Manual barcode input и lookup.

Камера запрашивается только после user gesture. На close/background все tracks
останавливаются, pending start не может повторно прикрепить stream. Permission
denied сохраняет manual fallback. Unsupported/secure-context errors объясняются
без технического traceback.

### Found review

Порядок: barcode/source status → реальное фото упаковки → brand/name/pack weight →
OFF source link → missing/derived warning → editable КБЖУ на 100 г → явное
подтверждение соответствия → «Создать ингредиент».

Фото использует contain, полная упаковка видна и может открыться крупнее. Broken
image заменяется предметным placeholder с подписью «Фото недоступно». Derived
ккал получает warning и формулу в accessible description. Missing field не
подставляется нулём: поле пустое, отмечено и требует проверки.

### Not found

Barcode остаётся виден. Сообщение «В Open Food Facts продукт не найден» и
primary «Заполнить вручную» открывают ingredient editor с barcode. Secondary:
сканировать снова. Lookup не создаёт продукт автоматически.

### Duplicate after OFF

Create response с existing object открывает duplicate notice и действие
«Открыть существующий». Review data не создаёт вторую запись.

## 5. Вес `/weight`

### Порядок populated

1. Page title и primary «Записать».
2. Metrics: текущий, среднее 7 дней, до цели.
3. Chart panel: title и даты окна, affordance, plot, legend, period selector.
4. Previous/next, zoom out/in, reset.
5. Accessible text summary.
6. История измерений с edit action.

### Первый viewport

На `390x844` целиком видны metrics, plot и все controls. Начало истории допускается
ниже controls, но primary запись доступна сверху. На `320x568` plot сохраняет
стабильную высоту, history уходит ниже nav и доступна page scroll.

### Plot

Y-domain строится по фактическому weight и average с readable padding. Goal,
если далеко, показывается подписью/edge marker без сжатия actual series. Оси имеют
не больше четырёх Y ticks и две крайние даты. Tooltip ограничен chart bounds.
Однодневные multiple entries различаются временем и остаются отдельными points.

### Временное окно и жесты

Current dates и число дней всегда видимы. Period options: 7/30/90/180/365/custom.
Один горизонтальный pointer двигает окно после threshold `8px`; вертикальный
scroll не блокируется. Pinch масштабирует вокруг midpoint. Preview обновляется
во время жеста, network request — после завершения. Нельзя уйти правее today.

Кнопки previous/next/zoom/reset имеют 44px и полностью повторяют жесты. Keyboard:
focused plot принимает Left/Right для точки, Shift+Left/Right для окна, +/- для
zoom; это дополнительный путь, обычные controls остаются.

### Loading после жеста

Старая линия остаётся с `aria-busy=true`; тонкий progress появляется в heading.
Controls временно предотвращают второй fetch, но reset доступен. Ошибка возвращает
предыдущее окно и показывает retry без очистки графика.

### Weight entry sheet

Create/edit: weight, local date/time, optional note. Primary sticky save.
Edit дополнен delete. Validation не разрешает будущий timestamp/неверный decimal.
409 сохраняет draft и предлагает загрузить актуальную запись. Delete confirm
называет дату и значение.

### Goal sheet

Toggle enabled, target, optional target date, nullable start weight. Направление
снижение/набор определяется backend progress. Preview показывает старт, текущий,
цель и остаток без оценочных медицинских обещаний.

### Варианты

| State | Blueprint |
| --- | --- |
| Нет измерений | Metrics «—», стабильный empty plot, primary «Записать вес» |
| Одна точка | Одна крупная selectable point, axes/summary без фиктивной линии |
| Плотная история | Downsample только display; tooltip использует исходные points |
| Цель достигнута | Success text и 100%, без конфетти/блокировки новых записей |
| Цель на набор | Остаток и progress меняют формулу, не semantic palette |
| Без start weight | Progress «—», target и current остаются |
| Пустой старый интервал | Даты видны, «Вернуться к текущему периоду» |
| Custom >365 | Inline validation до запроса |

### Desktop

Metrics остаются над plot или слева от него; plot шире, но не выше `320px`.
История может стать правой колонкой. Mouse drag работает, wheel страницы не
перехватывается. Bottom navigation остаётся доступной.

## 6. Профиль `/profile`

### Порядок

1. Page title и compact identity.
2. Nutrition goals table и edit action.
3. Settings rows: theme, default section, number format, timezone.
4. Behavior: after food add, deletion confirms, compact mode.
5. Reminders summary и editor.
6. Version, privacy policy, export.
7. Danger zone: deletion request.

### Первый viewport

Видны identity, цели и начало настроек. Avatar не является hero. Privacy и danger
zone ниже, но доступны через обычный page scroll и не спрятаны в неочевидном menu.

### Settings interaction

Каждая row открывает компактный sheet или inline segmented control, но не держит
все формы раскрытыми. Saved server value и pending status видны в строке.
Success закрывает editor только после ответа; error остаётся рядом с полем.
`default_section`, `after_food_add_action` и `confirm_deletions` должны не только
сохраняться, но и фактически использоваться соответствующими flows.

### Nutrition goals

Collapsed table показывает enabled state и КБЖУ. Editor принимает nullable поля,
не путает `null` с нулём и объясняет, что отключённая цель не скрывает фактические
граммы рациона. Save инвалидирует profile, goal и видимый ration day.

### Reminders

Summary: тип, локальное время, weekdays, enabled. Editor поддерживает `H:MM` и
`HH:MM`; сервер хранит нормализованное время. Weekday controls 44px, toggle имеет
полную label area. Nutrition reminder не называется напоминанием о конкретном
блюде, если такого поля нет в API. Delete доступен внутри editor с confirm.

### Export и privacy

Export показывает pending и начинает JSON download только после успешного ответа.
Ошибка сохраняет кнопку retry и correlation ID. Privacy policy — публичный route
со ссылкой назад, читаемой шириной текста и без требования успешной авторизации.
Version берётся из API/runtime setting, не из `frontend/package.json`.

### Полное удаление

Первый dialog перечисляет удаляемые данные и действие «Продолжить». После server
request второй dialog показывает TTL и точную контрольную фразу. Confirm input
не автозаполняется; final destructive button disabled до точного совпадения.
Expiry возвращает к первому шагу. После успеха query cache очищается, Mini App
показывает финальный статус и безопасно закрывается/возвращается в `/start`.

### Варианты

| State | Blueprint |
| --- | --- |
| Loading | Identity/goals/settings row skeletons |
| Empty optional data | «Не настроено» внутри конкретной row, не общая пустая страница |
| Save pending | Row и submit стабильны, spinner + текст «Сохраняем» |
| Field error | Связан с input, draft остаётся |
| Server error | Sheet открыт, message/correlation/retry |
| Long timezone/name | Две строки без horizontal overflow |
| Много reminders | Collapsed rows, editor отдельно |

### Desktop

Identity/goals занимают левую колонку, настройки и reminders — правую. Privacy,
export и danger zone остаются ниже общей сетки. Form sheets не растягиваются на
всю ширину.

## 7. Проверочная матрица перед production CSS

| Область | Обязательная проверка |
| --- | --- |
| Viewports | 320x568, 390x844, 768x1024, 1280x800 |
| Themes | explicit light/dark и Telegram system light/dark |
| Insets | top/bottom/content safe area, stable height change |
| Keyboard | search, decimal, date/time, deletion phrase |
| Content | длинные русские имена, 4-значные ккал, decimal comma |
| Accessibility | Tab order, focus trap/return, names, live regions, contrast |
| Network | offline transition, 401, 409, 429, 5xx, retry |
| Camera | denied, unsupported, background/close track cleanup |
| Weight gestures | pan/pinch/tap threshold, buttons, keyboard, reduced motion |
| Data integrity | idempotency, optimistic conflict, snapshot, nullable goals |

До явного подтверждения этих blueprints production React/CSS не изменяются.
