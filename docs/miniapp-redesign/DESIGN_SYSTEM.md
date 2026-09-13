# Дизайн-система WTracker Mini App

Статус: проект для второго подтверждения. Дата: 13.09.2026.
Направление: A с круговой диаграммой КБЖУ из B.

## 1. Принципы

- Рабочие данные и действия начинаются сразу после компактного header.
- Поверхность отделяет самостоятельный объект, а не каждый смысловой блок.
- В первом мобильном viewport видны статус раздела и начало основной работы.
- Значение, единица и состояние читаются без tooltip и без зависимости от цвета.
- Плотность высокая, но touch targets, inputs и системные сообщения не мельчают.
- Telegram theme и safe-area учитываются без смешивания explicit light/dark темы.
- Жесты ускоряют работу, но у каждого жеста есть видимый button/control аналог.

## 2. Semantic colors

Названия описывают роль, а не оттенок. Telegram variables используются как
входные данные только в режиме `system`; явный выбор light/dark применяет
зафиксированный набор целиком.

| Token | Light | Dark | Применение |
| --- | --- | --- | --- |
| `--color-background` | `#f7f9f8` | `#111814` | Основной фон приложения |
| `--color-canvas` | `#e9eeeb` | `#0c1210` | Поля вокруг desktop shell |
| `--color-surface` | `#ffffff` | `#18211d` | Карточки, inputs, overlays |
| `--color-surface-muted` | `#eff3f1` | `#202b26` | Фильтры, inactive controls |
| `--color-text-primary` | `#18211d` | `#f2f6f4` | Основной текст |
| `--color-text-secondary` | `#68746e` | `#a6b2ac` | Подписи и metadata |
| `--color-border` | `#d6ded9` | `#34423b` | Разделители и рамки |
| `--color-action-primary` | `#0d5c3e` | `#75d7a8` | Primary action и active nav |
| `--color-action-on-primary` | `#ffffff` | `#0f1814` | Текст primary action |
| `--color-action-soft` | `#e3f2eb` | `#1d3b2f` | Selected/pressed background |
| `--color-link` | `#096c4b` | `#68d5a3` | Текстовые ссылки |
| `--color-focus` | `#0879c9` | `#72bdf0` | Focus ring независимо от primary |
| `--color-danger` | `#bd3e4c` | `#ff7883` | Ошибка и destructive action |
| `--color-danger-soft` | `#fbe9eb` | `#41262b` | Спокойный фон ошибки |
| `--color-warning` | `#a96f0f` | `#efb751` | Derived/missing data |
| `--color-warning-soft` | `#f7edd9` | `#3a3020` | Фон предупреждения |
| `--color-success` | `#167451` | `#53bd8d` | Успех и online/saved |
| `--color-energy` | `#c98516` | `#efb751` | Калории и цель веса |
| `--color-macro-protein` | `#20885f` | `#58c493` | Белки |
| `--color-macro-fat` | `#d65e55` | `#f08077` | Жиры |
| `--color-macro-carbs` | `#337daf` | `#68afe0` | Углеводы |
| `--color-scrim` | `rgb(10 16 13 / 58%)` | `rgb(0 0 0 / 68%)` | Modal/sheet backdrop |

Для normal text требуется WCAG AA `4.5:1`, для крупного текста и графических
контролов — минимум `3:1`. Вторичный текст нельзя дополнительно снижать opacity.
В MR4 значения проверяются автоматическим contrast-тестом на обеих темах.

## 3. Типографика

Font stack: `Inter`, если он уже доступен в Telegram/OS, затем
`-apple-system`, `BlinkMacSystemFont`, `Segoe UI`, `sans-serif`. Внешний font
request запрещён. `letter-spacing: 0` для всех уровней.

| Role | Size / line-height | Weight | Применение |
| --- | --- | --- | --- |
| `display-number` | `28/32px` | 750 | Главный вес или калории |
| `page-title` | `24/28px` | 750 | Название раздела |
| `section-title` | `18/22px` | 700 | Основная секция |
| `subsection-title` | `15/20px` | 700 | Группа настроек, приём пищи |
| `body-strong` | `13/18px` | 650 | Название записи |
| `body` | `13/19px` | 400 | Описание и поля |
| `label` | `11/16px` | 650 | Labels, tabs, buttons |
| `caption` | `10/14px` | 400 | Время, единицы, metadata |

Inputs используют минимум `16px`, чтобы iOS WebView не увеличивал страницу.
Числа КБЖУ, веса, дат и прогресса получают `font-variant-numeric: tabular-nums`.
Значение и единица остаются разными spans, но доступны screen reader как одна
фраза. Длинные русские названия занимают до двух строк; одна строка с ellipsis
допустима только там, где соседнее открытие показывает полное название.

## 4. Spacing и размеры

Spacing scale: `0, 4, 8, 12, 16, 20, 24, 32, 40px`. Не вводить промежуточное
значение без измеримой причины.

| Element | Размер |
| --- | --- |
| Mobile horizontal padding | `12px`, на формах `16px` |
| Desktop max shell | `1120px` |
| Top bar | `58px + safe-top` |
| Bottom navigation | `66px + safe-bottom` |
| Button / icon button | минимум `44x44px` |
| Primary form action | минимум `48px` по высоте |
| Text input / select | минимум `48px`, font `16px` |
| Segmented option | минимум `44px` по высоте |
| Compact list row | минимум `56px` |
| Product / settings row | `64-72px` |
| Mobile weight chart plot | `166-184px`, стабильная высота |
| Bottom sheet | до `82dvh`, max-width `680px` |
| Dialog | max-width `440px` |

Радиусы: `4px` для progress, `6px` для badge/tooltip, `8px` для controls,
карточек, sheets и dialogs. Круг разрешён для avatar, chart point, ring и
круглого status indicator. Радиусы больше `8px` не используются для контейнеров.

## 5. Borders и shadows

- Основное разделение: `1px solid --color-border`.
- Active/selected: border primary плюс soft background, без изменения размера.
- Ошибка поля: danger border и связанный текст; красная заливка всей формы не нужна.
- Карточки по умолчанию без тени.
- Tooltip: `0 2px 8px rgb(16 30 23 / 10%)`.
- Bottom sheet: `0 -8px 30px rgb(19 36 28 / 12%)`, в dark до `32%` black.
- Modal: одна аналогичная тень; blur backdrop не используется.

## 6. Интерактивные состояния

| State | Правило |
| --- | --- |
| `hover` | Только pointer devices: лёгкий soft background/border |
| `pressed` | Soft background и визуальное смещение не более `1px`; layout стабилен |
| `focus-visible` | `3px` focus ring, offset `2px`, не обрезается overflow |
| `disabled` | Сохранить читаемость; `opacity >= .55`; cursor и aria-disabled |
| `pending` | Размер control неизменен; spinner заменяет icon, label остаётся |
| `success` | Короткий live toast и обновлённые данные; не только зелёная галочка |
| `error` | Сообщение рядом с причиной, retry где операция повторяема |
| `destructive` | Danger text/icon; filled danger только в последнем подтверждении |

Motion: `120ms` для pressed/color и `180ms` для sheet/toast. Анимации только
opacity/transform. При `prefers-reduced-motion: reduce` duration становится `0ms`.
Ни одна анимация не двигает соседний контент.

## 7. Shell и навигация

- Header содержит знак W, `WTracker`, контекст и saved/offline status.
- Offline status подписан текстом или имеет доступное имя, а не только точку.
- Bottom navigation всегда имеет четыре равные колонки и active state цветом,
  более сильным stroke и `aria-current=page`.
- Контент получает bottom padding не меньше nav + safe-bottom + `12px`.
- На desktop shell остаётся рабочим Mini App, центрируется и не превращается в
  landing page; связанные данные используют две колонки.
- Последний выбранный раздел сохраняется, неизвестный route показывает error/retry.

## 8. Списки и поверхности

- Page sections остаются unframed или разделяются полной полосой.
- Карточка используется для приёма пищи, продукта с самостоятельным контекстом,
  аналитического графика, sheet или dialog.
- Карточки не вкладываются друг в друга: entry внутри meal отделяется линией.
- В строке один основной tap target; дополнительные действия — icon menu 44px.
- КБЖУ продукта показывается в одной стабильной metadata-строке на 100 г.
- Empty row сохраняет название приёма/папки и видимое действие добавления.
- Skeleton повторяет геометрию результата, а не произвольные полосы.

## 9. Sheets, dialogs и toast

Bottom sheet:

- handle декоративный и `aria-hidden`;
- heading и close button находятся сверху;
- scroll только внутри body, footer action остаётся над keyboard/safe-bottom;
- при открытии: focus на heading или первом поле, фон `inert`, body scroll locked;
- Tab/Shift+Tab не выходят из sheet, Escape и Telegram BackButton закрывают;
- закрытие возвращает focus на trigger;
- незаполненный новый sheet закрывается сразу, изменённый draft требует confirm.

Confirm dialog используется для необратимых действий и содержит конкретный
объект/последствие. Полное удаление данных сохраняет два шага и контрольную фразу.

Toast имеет `role=status` для успеха и `role=alert` для ошибки, закрывается,
не перекрывает bottom navigation и не содержит единственный путь к исправлению.

## 10. Рацион и макроэлементы

- Кольцо кодирует доли protein/fat/carbs; центр показывает калории и цель.
- Рядом всегда присутствует текстовая легенда: название, граммы, цель, процент.
- Без целей показываются граммы и доли, а вместо target — «Цель не задана».
- При нулевых макросах кольцо нейтральное и имеет текст «Нет данных о БЖУ».
- Значение больше цели не меняет геометрию кольца: excess показывается строкой,
  числом и спокойным danger accent.
- Приёмы пищи идут сразу после сводки. На `390x844` видны их заголовок и минимум
  один заполненный приём; на `320x568` виден заголовок и primary add action.

## 11. График веса

Линии различаются не только цветом: фактический вес сплошной с точками,
moving average пунктирный, цель штриховая с подписью. Y-domain строится вокруг
фактических данных; далёкая цель не должна сжимать полезную вариацию до линии.

Интерактивное окно:

- один палец/mouse drag горизонтально сдвигает период;
- вправо — более ранние даты, влево — более поздние;
- вертикальный жест продолжает scroll страницы;
- pinch out уменьшает число дней, pinch in увеличивает вокруг midpoint;
- окно ограничено `7-365` днями и текущим локальным днём справа;
- fetch начинается на pointerup/touchend, во время жеста меняется preview domain;
- tap открывает tooltip, drag после `8px` threshold не считается tap;
- кнопки previous/next, zoom out/in и reset повторяют все жесты;
- обычный wheel страницы не перехватывается, системный zoom не запрещается;
- tooltip ограничен plot bounds и не выходит за мобильный viewport;
- loading после жеста сохраняет старую линию с неблокирующим progress indicator.

График имеет доступный summary: период, начало/конец, изменение, min/max,
последнее значение, average и цель. Каждая selectable point получает имя даты/веса.

## 12. Responsive и Telegram WebView

| Диапазон | Поведение |
| --- | --- |
| `320-519px` | Один столбец, padding 12, без скрытия КБЖУ/ккал |
| `520-799px` | Один широкий столбец или две равные metrics columns |
| `>=800px` | Shell до 1120px; summary/content в 2 колонки |

- `viewport-fit=cover`; safe/content insets объединяются через `max()`.
- При изменении `viewportStableHeight` shell обновляет доступную высоту без jump.
- Открытая keyboard не перекрывает focused field и footer sheet.
- Минимальная проверка: `320x568`, `390x844`, `768x1024`, `1280x800`.
- Отдельная ручная проверка: Telegram Android, iOS и Desktop, обе темы.
- Масштабирование страницы пользователем не ограничивается.

## 13. Реализация

В MR4 токены переносятся в production CSS variables. Допустимое разделение:
`tokens.css`, `base.css`, `layout.css`, `components.css`, затем page styles.
Названия из этого документа являются контрактом; prototype CSS не копируется
механически. Любое отклонение фиксируется в blueprint или тесте.
