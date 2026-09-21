# Nutrition Bot

Telegram-бот для учета питания, КБЖУ, веса и целей. Проект разрабатывается
поэтапно по [BOT_SPEC.md](BOT_SPEC.md). Сейчас реализованы ЭТАПЫ 0-9:

Production-эксплуатация Mini App описана в
[MINIAPP_SERVER_RUNBOOK.md](MINIAPP_SERVER_RUNBOOK.md).

- запуск aiogram и подключение к PostgreSQL;
- автоматическое создание пользователя по Telegram ID;
- обновление Telegram-профиля при изменении данных;
- команды `/start` и `/menu`;
- постоянное главное меню.
- создание и редактирование ингредиентов с валидацией КБЖУ;
- список ингредиентов с пагинацией, поиск и удаление;
- команды `/ingredients` и `/cancel`.
- отдельный `NutritionService` для точного расчета КБЖУ по граммовке через
  `Decimal`.
- блюда из нескольких ингредиентов с динамическим расчетом КБЖУ;
- редактор состава, поиск, пагинация, изменение и удаление блюд;
- команда `/dishes`.
- дневной рацион для ингредиентов и блюд со snapshot КБЖУ;
- выбор даты и приёма пищи, дневные суммы и проценты энергии БЖУ;
- просмотр, изменение граммов/приёма пищи/даты и удаление записей;
- команды `/today` и `/addfood`.
- журнал измерений веса с локальными датой и временем;
- текущий и первый вес, разница между ними, пагинированная история;
- изменение и удаление измерений;
- команда `/weight`.
- одна активная цель по весу со сроком или без срока;
- snapshot стартового веса и прогресс для снижения или набора массы;
- замена, завершение и отмена активной цели;
- команда `/goal`.
- единое форматирование дат, времени и числовых значений;
- глобальная обработка и безопасное логирование неожиданных ошибок;
- понятные ответы для неизвестных сообщений и устаревших inline-кнопок;
- пагинация ингредиентов, блюд, дневника и истории веса;
- команды `/help`, `/cancel` и ответы на все кнопки главного меню.
- unit- и integration-тесты с отдельной временной PostgreSQL;
- автоматическая проверка прямого и обратного хода всех миграций;
- многоэтапный Docker-образ и production-like Compose с запуском без root,
  read-only filesystem, healthcheck PostgreSQL и ротацией логов.

Из дополнений реализованы ЭТАПЫ D1-D19:

- единая нормализация и токенизация поисковых запросов;
- общее поисковое ядро с relevance score и изоляцией пользователей;
- PostgreSQL `pg_trgm` и GIN-индексы для ингредиентов и блюд.
- умный поиск ингредиентов с опечатками, частичными словами и несколькими
  токенами;
- результаты по релевантности и actionable empty state в Telegram.
- умный поиск пользовательских блюд на том же поисковом ядре.
- десятисегментный progress bar цели по весу для снижения и набора массы;
- отдельные карточки достигнутой цели и цели без стартового веса.
- рабочие настройки часового пояса, точности чисел и поведения дневника;
- экран сведений о версии и среде без раскрытия конфигурации и секретов.
- сводка количества пользовательских сущностей;
- транзакционное удаление данных с двойным подтверждением, сохранением строки
  пользователя и изоляцией аккаунтов.
- сквозные regression-тесты полного пользовательского сценария D1-D6.
- централизованные stdout-логи с correlation ID для Telegram updates,
  безопасным контекстом ошибок и Docker-ротацией без записи лог-файлов внутрь
  контейнера.
- HealthService для проверки heartbeat приложения, PostgreSQL, Telegram API,
  scheduler status и Alembic revision; Docker healthcheck без публичного HTTP
  endpoint.
- безопасные Telegram-уведомления администраторам о критических ошибках с
  fingerprint, cooldown, агрегацией повторов и защитой от notification storm.
- закрытая read-only команда `/admin` с состоянием системы, агрегатами
  пользователей и данных, сведениями о PostgreSQL/Alembic, версии приложения и
  runtime-ошибках.
- graceful shutdown для SIGTERM/SIGINT с прекращением приёма updates, ожиданием
  коротких транзакций, остановкой lifecycle-компонентов и background tasks,
  закрытием Telegram HTTP client и SQLAlchemy engine.
- in-memory rate limiting до DB middleware для сообщений, callbacks, поиска и
  будущего графика веса с независимыми buckets пользователей и cooldown
  видимого предупреждения.
- защита подтверждаемых операций одноразовыми `action_token`, in-memory lock с
  TTL и проверкой устаревших callback; повторные сохранения и удаления не
  создают вторую операцию.
- исторические цели по калориям, белкам, жирам и углеводам с частичным
  заполнением, датой начала, безопасной сменой/отключением и progress bars в
  дневнике, включая нейтральное отображение превышения цели.
- PNG-график динамики веса за 7/30/90/180/365 дней или выбранный период до
  365 дней, с точками измерений, 7-дневным средним и линией активной цели.
- opt-in напоминания о взвешивании и дневном рационе по выбранным дням и
  локальному времени пользователя, с восстановлением расписания после рестарта.
- безопасный migration flow с проверенным backup PostgreSQL 16, advisory lock,
  контролем Alembic revision до polling и версией релиза в админ-панели.
- финальный production-like regression gate с lint, проверкой миграций,
  unit/integration-тестами, параллельной нагрузкой на DB pool, rate limiter и
  защиту повторных операций.

Все этапы дополнений D1-D19 завершены.

Из дополнения Telegram Mini App реализованы этапы M1-M9:

- FastAPI Web API с health/readiness endpoints;
- серверная проверка подписи и срока действия Telegram `initData`;
- защищенный `GET /api/v1/me` через общий `UserService`;
- постоянные idempotency receipts для будущих Web API мутаций;
- React/TypeScript/Vite frontend и Telegram adapter;
- адаптивный shell с разделами `Рацион`, `Еда`, `Вес`, `Профиль`;
- Telegram BackButton, темы, safe area и стабильная высота viewport;
- серверные переносимые настройки интерфейса и локальный последний раздел;
- профиль с настройками, целями КБЖУ, напоминаниями и управлением данными;
- дневной рацион с итогами, БЖУ, приемами пищи и CRUD записей;
- учет веса с целью, историей, диапазонами и интерактивным графиком Recharts.
- каталог ингредиентов и блюд с поиском, CRUD, sharing и пользовательскими
  папками.
- сканирование EAN/UPC/GTIN камерой или ручной ввод штрихкода;
- серверный поиск продукта в Open Food Facts с ограничением запросов,
  кэшированием и проверкой внешних данных;
- обязательная проверка найденных КБЖУ перед созданием ингредиента и защита от
  дублей по штрихкоду или похожему названию.

## Требования

- Docker Engine с Docker Compose; или
- Python 3.12+ и доступный PostgreSQL.

## Запуск через Docker Compose

1. Создайте локальный файл настроек:

   ```bash
   cp .env.example .env
   ```

2. Укажите настоящий токен Telegram-бота в `BOT_TOKEN` файла `.env`.
3. Запустите безопасный deploy:

   ```bash
   ./scripts/deploy.sh
   ```

Compose выполняет строгую цепочку `db -> backup -> migrate -> bot + web ->
miniapp`. Одноразовый
сервис `backup` на образе PostgreSQL 16 создаёт и проверяет dump через
`pg_dump`/`pg_restore`, записывает SHA-256 marker и сохраняет только два последних
успешных dump. Сервис `migrate` проверяет marker, применяет Alembic под advisory
lock и сверяет итоговую revision. Только после их успешного завершения
запускаются polling Telegram, Web API и HTTPS frontend.
Проверка состояния и логов:

```bash
docker compose ps
docker compose logs backup
docker compose logs migrate
docker compose logs -f bot
docker compose logs -f web miniapp
```

Полную контейнерную проверку можно запустить вручную:

```bash
docker compose exec bot python scripts/healthcheck.py
docker compose exec web python scripts/web_healthcheck.py --mode readiness
```

Успешный результат проверяет свежий heartbeat приложения, доступность
PostgreSQL и совпадение текущей Alembic revision с версией кода. Telegram API
проверяется отдельно через внутренний `HealthService`, чтобы healthcheck не
обращался к Telegram каждые 30 секунд.

Уровень логирования задаётся через `LOG_LEVEL` (`INFO` по умолчанию,
`DEBUG` для разработки). Каждая обработка Telegram update получает
`correlation_id=tg-<update_id>`; traceback остаётся только в серверных логах.
Интервал heartbeat задаётся через `HEALTH_HEARTBEAT_INTERVAL_SECONDS` и по
умолчанию равен 30 секундам.

Для уведомлений об ошибках укажите Telegram ID администраторов через запятую:

```env
ADMIN_TELEGRAM_IDS=123456789,987654321
ADMIN_ERROR_COOLDOWN_SECONDS=300
ADMIN_ERROR_MAX_PER_MINUTE=10
APP_VERSION=1.1.0
GIT_COMMIT_SHA=unknown
MIGRATION_BACKUP_DIR=/backups
MIGRATION_BACKUP_MARKER=/backups/.last-verified
ALLOW_MIGRATION_WITHOUT_BACKUP=false
SHUTDOWN_DRAIN_TIMEOUT_SECONDS=20
RATE_LIMIT_MESSAGES_COUNT=10
RATE_LIMIT_MESSAGES_WINDOW_SECONDS=10
RATE_LIMIT_CALLBACKS_COUNT=20
RATE_LIMIT_CALLBACKS_WINDOW_SECONDS=10
RATE_LIMIT_SEARCH_COUNT=5
RATE_LIMIT_SEARCH_WINDOW_SECONDS=10
RATE_LIMIT_WEIGHT_CHART_COUNT=3
RATE_LIMIT_WEIGHT_CHART_WINDOW_SECONDS=60
RATE_LIMIT_SHARE_CREATE_COUNT=10
RATE_LIMIT_SHARE_CREATE_WINDOW_SECONDS=60
RATE_LIMIT_SHARE_OPEN_COUNT=20
RATE_LIMIT_SHARE_OPEN_WINDOW_SECONDS=60
RATE_LIMIT_SHARE_IMPORT_COUNT=10
RATE_LIMIT_SHARE_IMPORT_WINDOW_SECONDS=60
RATE_LIMIT_SHARE_ROTATE_COUNT=5
RATE_LIMIT_SHARE_ROTATE_WINDOW_SECONDS=60
RATE_LIMIT_NOTICE_COOLDOWN_SECONDS=5
ACTION_LOCK_TTL_SECONDS=20
REMINDER_MISFIRE_GRACE_SECONDS=1800
SHARE_LINK_TTL_DAYS=30
SHARE_PACKAGE_RETENTION_DAYS=30
```

Истёкшие и отозванные share-пакеты удаляются scheduler небольшими пачками после
`SHARE_PACKAGE_RETENTION_DAYS`. В разделах ингредиентов и блюд экран
`📦 Мои ссылки` позволяет посмотреть статус и число завершённых импортов,
отозвать ссылку или выпустить новый token без изменения snapshot пакета.

После отправки сообщения боту свой Telegram ID можно увидеть как `user_id` в
серверных логах. Одинаковые ошибки агрегируются в течение cooldown, а ожидаемые
ошибки валидации и отсутствия пользовательских сущностей админу не отправляются.

После перезапуска администратор может открыть закрытую панель командой
`/admin`. Каждый callback панели повторно проверяет Telegram ID. Панель работает
только на чтение и не содержит списков пользователей, traceback, секретов,
управления сервером или произвольных SQL-команд.

При `docker compose restart bot` или `docker compose down` контейнер получает
SIGTERM и имеет 30 секунд на остановку. Новые updates перестают приниматься,
активные операции ожидаются до `SHUTDOWN_DRAIN_TIMEOUT_SECONDS`, после чего
незавершённые транзакции отменяются с rollback. Черновики до подтверждения могут
быть потеряны, но подтверждённые бизнес-операции сохраняются в PostgreSQL.

Rate limiter хранится в памяти одного процесса. При превышении пользователь
получает сообщение «Слишком много действий подряд» не чаще заданного cooldown;
другие пользователи продолжают работать независимо. После рестарта buckets
обнуляются. Для нескольких replicas storage потребуется перенести в Redis или
PostgreSQL.

Для share-ссылок лимиты `SHARE_CREATE`, `SHARE_OPEN`, `SHARE_IMPORT` и
`SHARE_ROTATE` считаются по Telegram user ID. Они не привязаны к token, поэтому
действия одного пользователя не блокируют пакет для остальных получателей.
Share-token считается bearer secret, хранится в БД только как SHA-256 hash и
редактируется в обычных сообщениях, URL и traceback серверного лога.

PostgreSQL доступен с хоста только через `127.0.0.1`. Порт можно изменить
через `POSTGRES_PORT` в `.env`.

Остановка:

```bash
docker compose down
```

Не используйте `docker compose down -v` или `docker compose down
--volumes` для штатной остановки: эти команды удалят PostgreSQL,
migration backups и TLS state.

## Автотесты в Docker

Полная проверка не использует рабочую БД. Отдельный Compose поднимает временную
PostgreSQL, запускает Ruff, применяет все миграции, проверяет их откат и
повторное применение, сверяет модели с Alembic и запускает unit- и
integration-тесты. Рекомендуемая команда автоматически удаляет тестовые
контейнеры и сеть после завершения:

```bash
./scripts/regression.sh
```

Эквивалентный ручной запуск:

```bash
docker compose -f docker-compose.test.yml up \
  --build --abort-on-container-exit --exit-code-from tests
docker compose -f docker-compose.test.yml down
```

## Локальный запуск

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
alembic upgrade head
python -m app.main
```

При локальном запуске замените хост `db` в `DATABASE_URL` на `localhost`.

### Mini App M1-M10

Backend запускается отдельно от polling-процесса и использует ту же БД:

```bash
python -m app.web.main
```

Проверка незашифрованного локального health endpoint:

```bash
curl http://127.0.0.1:8080/internal/healthz
```

В production Compose запускает отдельный service `web` из того же release
image, что и бот. Uvicorn слушает только внутреннюю Docker network; порт `8080`
на public interface не публикуется. Проверки внутри container:

```bash
docker compose exec -T web python scripts/web_healthcheck.py
docker compose exec -T web python scripts/web_healthcheck.py --mode readiness
docker compose logs --no-color --tail=100 web
```

`MINIAPP_ENABLED=false` сохраняет internal health endpoints, но возвращает
`503 miniapp_disabled` для `/api/*`. При включенном Mini App непустой
`MINIAPP_ALLOWED_TELEGRAM_IDS` разрешает Web API только подписанным Telegram
пользователям из allowlist; пустое значение разрешает всех валидно
авторизованных пользователей.

Frontend требует Node.js 22+:

```bash
cd frontend
npm ci
npm run dev
```

Development URL: `http://127.0.0.1:5173`. В development обычный браузер
показывает интерфейс без пользовательских данных. В production вне Telegram
отображается экран авторизации. Защищенные `/api/v1/me` и
`/api/v1/ui-preferences` принимают только свежий подписанный
`Telegram.WebApp.initData`; production-публикация и кнопка открытия из Telegram
используют настроенный HTTPS URL Mini App.

Production frontend собирается отдельным multi-stage image: Node выполняет
lint, typecheck, tests и Vite build, а итоговый runtime содержит только Caddy и
`dist/` без исходников, `node_modules` и source maps:

```bash
docker build --target runtime -t wtrackerbot-miniapp:local frontend
```

`frontend/Caddyfile` сохраняет `/api/*` prefix при проксировании в `web:8080`,
закрывает внешний `/internal/*` и отдает все SPA routes через `index.html`.
HTML не кэшируется, hashed assets получают immutable cache, а CSP допускает
Telegram Web App script и запросы к API только с текущего origin.

Production Compose запускает цепочку `db -> backup -> migrate -> bot + web ->
miniapp`. Только `miniapp` публикует HTTP/HTTPS на `80/tcp`, `443/tcp` и
`443/udp`; PostgreSQL остается привязан к `127.0.0.1`, а Web API доступен только
в Docker network. Сеть `database` изолирует PostgreSQL от Caddy, сеть `edge`
соединяет Caddy с Web API и оставляет боту/API исходящий доступ в интернет.
Caddy работает без Node runtime, с read-only root filesystem и минимальной
capability `NET_BIND_SERVICE`.

Сертификаты и данные сервисов переживают обычную остановку благодаря named
volumes `postgres_data`, `postgres_backups`, `caddy_data` и `caddy_config`:

```bash
docker compose up -d --build --wait
docker compose down
```

Не используйте `docker compose down -v`: эта команда удаляет volumes базы,
backup и TLS-сертификатов. После запуска проверьте бюджет сервера без установки
жестких memory limits:

```bash
docker compose ps
docker stats --no-stream
docker system df
df -h /
```

В Mini App доступны профиль, рацион, учет веса и каталог еды. Раздел еды
поддерживает серверный поиск и сортировку, cursor pagination, CRUD ингредиентов
и блюд, поиск ингредиентов внутри редактора рецепта, проверку похожих названий,
безопасное удаление и существующий формат sharing-пакетов. Для создания deep
link из Mini App задайте `BOT_USERNAME` без символа `@`. Пользовательские папки
могут одновременно содержать ингредиенты и блюда, поддерживают ручной порядок,
одиночный и массовый перенос. Удаление папки оставляет еду в системном фильтре
`Без папки`. Сканер принимает EAN-8, UPC-A, EAN-13 и GTIN-14 через камеру или
ручной ввод. Данные Open Food Facts запрашивает только backend; перед созданием
ингредиента пользователь проверяет и подтверждает КБЖУ. Пустой direct link
`https://t.me/<bot_username>?startapp` открывает Main Mini App. Смысловые
`startapp=<payload>` пока не поддерживаются frontend/backend-контрактом.

Раздел веса использует общие с ботом записи и цели, поддерживает CRUD
измерений, диапазоны до 365 дней, 7-дневное скользящее среднее и интерактивный
график Recharts.

## Проверки

```bash
ruff check .
ruff format --check .
pytest tests/unit
docker compose config
docker compose -f docker-compose.test.yml config
```

Для локального запуска integration-тестов задайте адрес отдельной PostgreSQL с
примененными миграциями:

```bash
docker compose up -d --wait db
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/nutrition_bot \
  BOT_TOKEN=test alembic upgrade head
TEST_DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/nutrition_bot \
  pytest tests/integration
```

Frontend release gate:

```bash
cd frontend
npm ci
npm run lint
npm run typecheck
npm test -- --run
npm run build
npm run verify:build
UI_AUDIT_OUTPUT=../docs/miniapp-redesign/screenshots/mr9-final npm run audit:ui
```

Полная проверка Docker и backend выполняется на машине с установленными Docker
Compose, Python dev-зависимостями и PostgreSQL:

```bash
./scripts/regression.sh
docker compose config
```

## Миграции

Миграции не выполняются процессом бота. Сервис `backup` на той же major-версии,
что и сервер PostgreSQL, создаёт проверенный custom-format dump в именованном
volume `postgres_backups`. Затем `migrate` проверяет SHA-256 и выполняет только
`alembic upgrade head`. Ошибка backup, checksum, миграции или итоговой проверки
revision завершает соответствующий сервис с ненулевым кодом, поэтому бот не
запускается.
После успешной проверки нового dump ротация оставляет в volume два последних
backup-файла. Marker всегда указывает на самый новый из них.
Production не позволяет `ALLOW_MIGRATION_WITHOUT_BACKUP=true`; этот флаг
допустим только для явно выбранного development-окружения.

Диагностические команды:

```bash
docker compose run --rm --no-deps migrate alembic current
docker compose run --rm --no-deps migrate alembic history
docker compose run --rm --no-deps migrate alembic check
docker compose run --rm --no-deps migrate ls -lh /backups
```

Новые изменения схемы оформляются отдельной ревизией и проверяются полным
тестовым прогоном:

```bash
alembic revision --autogenerate -m "describe schema change"
docker compose -f docker-compose.test.yml up \
  --build --abort-on-container-exit --exit-code-from tests
```

Приложение дополнительно сверяет revision перед запуском scheduler и polling.
Админ-панель показывает `Current revision`, `Expected head` и один из статусов:
`UP_TO_DATE`, `BEHIND`, `AHEAD_UNKNOWN`. Любой статус кроме `UP_TO_DATE`
блокирует startup с `CRITICAL`-логом.

## Deploy и rollback

Для каждого релиза явно обновите `APP_VERSION` в server `.env`.
`GIT_COMMIT_SHA` скрипт получает из текущего git commit автоматически. Compose
тегирует application и frontend images версией и revision; значения приложения
и DB revision видны в админ-панели. Deploy разрешен только из чистого git
working tree и защищен от параллельного запуска exclusive lock. Выполните:

```bash
./scripts/deploy.sh
```

Скрипт выполняет production preflight, показывает использование диска, собирает
backup/application/frontend images и ожидает всю цепочку Compose. Затем он
проверяет bot, внутреннюю readiness Web API, Caddy и, при настроенном реальном
домене, HTTPS frontend, `/api/*` и внешний запрет `/internal/*`. При любой
ошибке deploy завершается ненулевым кодом, выводит status и последние логи и не
начинает очистку.

Только после всех smoke-тестов удаляются завершенные `backup`/`migrate`,
неиспользуемые images и build cache командами `docker image prune -a -f` и
`docker builder prune -a -f`. `docker system df` и `df -h /` выводятся до и
после. Volumes PostgreSQL, backup и TLS не удаляются.

Перед сборкой `deploy.sh` автоматически запускает `scripts/sync_env.sh`.
Скрипт добавляет в существующий `.env` только отсутствующие переменные из
`.env.example` и никогда не заменяет заданные токены, пароли или ID
администраторов. Резервные копии создаются только при изменении `.env` в каталоге
`.env.backups`; сохраняются две последние. Синхронизацию можно запустить отдельно:

```bash
./scripts/sync_env.sh
```

Если `.env` отсутствует, скрипт создаст его с правами `0600` и остановится, чтобы
секреты были заполнены до deploy.

Перед production-развертыванием Mini App заполните доменный контракт в `.env`:

```env
MINIAPP_ENABLED=false
MINIAPP_DOMAIN=app.example.com
MINIAPP_ACME_EMAIL=admin@example.com
MINIAPP_EXPECTED_IPV4=203.0.113.10
MINIAPP_EXPECTED_IPV6=
MINIAPP_SSH_PORT=22
MINIAPP_PUBLIC_URL=https://app.example.com
MINIAPP_CORS_ORIGINS=https://app.example.com
MINIAPP_ALLOWED_TELEGRAM_IDS=
MINIAPP_MANAGE_MENU_BUTTON=true
MINIAPP_MENU_BUTTON_TEXT=Открыть дневник
```

Пока HTTPS и Telegram entry point не проверены, оставляйте
`MINIAPP_ENABLED=false`. Production preflight не выводит токен или пароль и
проверяет согласованность domain/URL/CORS, Docker Compose, свободное место и
публичные порты:

```bash
./scripts/miniapp_preflight.sh
```

Проверка требует `APP_ENVIRONMENT=production`, установленный Docker Compose и
минимум 2 GB свободного места. Переменные, появившиеся после обновления проекта,
добавляются командой `./scripts/sync_env.sh` без замены существующих секретов.

При `MINIAPP_MANAGE_MENU_BUTTON=true` polling-бот на каждом старте приводит
Telegram menu button к состоянию из `.env`: выключенный Mini App возвращает
commands menu, непустой allowlist получает Web App-кнопку только в указанных
private chats, а пустой allowlist включает ее по умолчанию для всех. Повторный
старт безопасен. Ошибка Telegram API отправляется администраторам и не блокирует
polling. Значение `false` оставляет управление кнопкой за BotFather.

После успешной проверки staging HTTPS настройте Main Mini App вручную через
официальный `@BotFather`:

```text
/mybots
-> bot
-> Bot Settings
-> Configure Mini App
-> Enable Mini App
-> production HTTPS URL
```

Fallback для menu button:

```text
/setmenubutton
-> bot
-> button text
-> production HTTPS URL
```

После этого проверьте `https://t.me/<bot_username>?startapp`. Пустой параметр
только открывает приложение; маршрутизация смысловых payload не реализована.
Официальные контракты: [Telegram Mini Apps](https://core.telegram.org/bots/webapps)
и [setChatMenuButton](https://core.telegram.org/bots/api#setchatmenubutton).

### DNS, firewall, TLS и staging

Создайте отдельную DNS A-запись `MINIAPP_DOMAIN`, указывающую точно на
`MINIAPP_EXPECTED_IPV4`. Не создавайте AAAA без настроенного IPv6; при его
наличии задайте точный адрес в `MINIAPP_EXPECTED_IPV6`. Для первого выпуска
Cloudflare должен быть в DNS-only режиме, иначе аудит увидит адрес proxy вместо
origin server.

До включения firewall сохраните текущий SSH port, разрешите его, `80/tcp` и
`443/tcp`; `443/udp` нужен только для HTTP/3. Порты `5432`, `8080`, `5173` и
`5174` публично не открывайте. Firewall меняется вручную из активной SSH-сессии:
audit-скрипты намеренно не выполняют `ufw enable`, `iptables` или `nft`.

После DNS propagation заполните `.env`, оставьте в allowlist только Telegram ID
тестировщиков и выполните deploy. На сервере проверьте NTP, listeners,
readiness и сохранение сертификата после перезапуска Caddy:

```bash
./scripts/deploy.sh
MINIAPP_AUDIT_RESTART_CADDY=true ./scripts/miniapp_host_audit.sh
```

С ноутбука или другой машины вне сервера установите `dig`, `curl`, `openssl` и
`python3`. Создайте из безопасного шаблона отдельный файл без токена и пароля,
заполните домен и адреса, затем запустите read-only внешний аудит:

```bash
cp scripts/miniapp-audit.env.example /tmp/miniapp-audit.env
ENV_FILE=/tmp/miniapp-audit.env ./scripts/miniapp_public_audit.sh
```

Он проверит точные A/AAAA/CNAME, redirect HTTP -> HTTPS, hostname/цепочку/срок
сертификата, HSTS, frontend/API routes и внешний port scan. Затем вручную
проверьте авторизацию хотя бы на одном мобильном и одном desktop Telegram
client. Полная staging-матрица: Android, iOS, Desktop и Web. Камеру проверяйте
на физическом телефоне по production-like HTTPS URL; noVNC этого не заменяет.

### Production rollout и наблюдаемость

Выпускайте Mini App поэтапно: сначала deploy с
`MINIAPP_ENABLED=false`, затем админский allowlist, ограниченная
группа и только после полной проверки пустой allowlist для всех
пользователей. Текущий этап не выводит Telegram ID:

```bash
./scripts/miniapp_rollout.sh status
./scripts/miniapp_rollout.sh require disabled
./scripts/miniapp_rollout.sh require limited
./scripts/miniapp_rollout.sh require global
./scripts/miniapp_rollout.sh checklist
```

После каждого изменения флагов выполните `./scripts/deploy.sh`. На
этапах `disabled`, `limited` и `global` запустите полный read-only
smoke на production-сервере:

```bash
./scripts/miniapp_production_smoke.sh
```

Он проверяет DNS, TLS, redirect, HTML content type, direct SPA route,
отсутствие source maps, закрытость `/internal/*`, health контейнеров,
внутреннюю API readiness, совпадение version/commit у frontend, API и
бота, а также закрытые порты `5432/8080/5173/5174`.

Для auth smoke вставьте свежий `initData` только в скрытый prompt. Не
передавайте его аргументом командной строки или переменной окружения:

```bash
python3 scripts/miniapp_auth_smoke.py https://app.example.com
```

Легкий диагностический отчет показывает Docker health, CPU/RAM,
соединения PostgreSQL, диск и ошибки Web API/Caddy. Ошибки Open Food
Facts выводятся отдельно и не влияют на application readiness:

```bash
MINIAPP_OBSERVABILITY_SINCE=6h ./scripts/miniapp_observability.sh
```

В production бот также сам проверяет Web API readiness. После трех
подряд ошибок администратор получает одно Telegram-уведомление на
инцидент; recovery фиксируется в логе. При критической ошибке сначала
верните `MINIAPP_ENABLED=false` и выполните deploy. Не удаляйте containers
и не используйте `docker compose down -v`.

Очистка включена по умолчанию, чтобы Docker не заполнял небольшой production
SSD. Для разовой диагностики с сохранением контейнеров и build cache ее можно
отключить:

```bash
DOCKER_PRUNE_AFTER_DEPLOY=false ./scripts/deploy.sh
```

После автоматической очистки следующий deploy может собираться дольше, потому
что Python-зависимости будут загружены заново.

Rollback принимает только предыдущий semver tag, являющийся предком текущего
commit:

```bash
./scripts/rollback.sh v1.0.2
```

Скрипт блокирует параллельный deploy, проверяет текущую DB readiness и SHA-256
marker последнего backup, создает отдельный detached `git worktree` и собирает
images из выбранного тега. Текущая `.env`, Compose project, database и TLS
volumes сохраняются. Перед запуском target-код отдельно проверяется против
текущей Alembic revision. Несовместимый tag отклоняется до замены работающих
services; автоматический downgrade не выполняется.

После успешного rollback основная ветка репозитория остается на новой версии:
откат относится к запущенным images. Поэтому следующий обычный
`./scripts/deploy.sh` снова выполняет forward-deploy текущего commit. Если схема
несовместима, используйте исправленный forward-deploy или отдельный утвержденный
план восстановления БД. Перед ручным восстановлением обязательно сохраните
текущую БД и проверьте dump командой `pg_restore --list`.

## Ручная проверка

1. Откройте бота в Telegram и отправьте `/start`.
2. Убедитесь, что бот показывает приветствие и постоянное главное меню.
3. Повторно отправьте `/start`: бот должен показать главное меню без повторного
   приветствия.
4. Отправьте `/menu`: бот должен повторно показать главное меню.
5. Измените username Telegram и снова отправьте сообщение боту. Поле пользователя
   в БД должно обновиться, новая строка создаваться не должна.

### Ингредиенты

1. Нажмите `🥕 Ингредиенты` или отправьте `/ingredients`.
2. Нажмите `➕ Добавить` и последовательно введите название, калории, белки,
   жиры и углеводы на 100 г.
3. Подтвердите сохранение и откройте ингредиент из общего списка.
4. Измените название и одно из значений КБЖУ.
5. Найдите ингредиент по части названия.
6. Создайте больше восьми ингредиентов и проверьте переключение страниц.
7. Удалите ингредиент через экран подтверждения.
8. Во время любого ввода отправьте `/cancel` или нажмите `❌ Отмена`.

### Блюда

1. Создайте минимум два ингредиента и откройте `🍲 Блюда` или `/dishes`.
2. Нажмите `➕ Создать блюдо`, задайте название и добавьте ингредиенты с
   граммовкой.
3. Проверьте КБЖУ всего рецепта и значения на 100 г.
4. Сохраните блюдо, откройте состав и измените граммовку компонента.
5. Измените КБЖУ исходного ингредиента и снова откройте блюдо: расчет должен
   измениться автоматически.
6. Проверьте поиск, список и удаление блюда.
7. Попробуйте удалить ингредиент, используемый в блюде: бот должен показать
   названия рецептов и запретить удаление.

### Дневной рацион

1. Нажмите `➕ Добавить еду` или отправьте `/addfood`.
2. Добавьте ингредиент, указав граммы, приём пищи и дату `Сегодня`.
3. Добавьте блюдо целиком, затем добавьте его повторно с произвольной граммовкой.
4. Нажмите `📅 Сегодня` или отправьте `/today` и проверьте суммы, проценты БЖУ
   и группировку по приёмам пищи.
5. Через `✏️ Изменить рацион` поменяйте граммы, приём пищи и дату записи.
6. Измените КБЖУ исходного ингредиента: старая запись не должна измениться.
   После ручного изменения граммов записи snapshot должен пересчитаться.
7. Откройте ингредиент или блюдо из справочника и проверьте кнопку
   `➕ В рацион`.

### Вес

1. Нажмите `⚖️ Вес` или отправьте `/weight`.
2. Добавьте измерение через `➕ Добавить вес`, выбрав `Сейчас`.
3. Добавьте ещё два измерения через `Сегодня утром` и ручной ввод даты/времени.
4. Проверьте текущий и первый вес, разницу и порядок последних записей.
5. Откройте `📋 История`, затем измените вес и время одной записи.
6. Удалите запись через экран подтверждения.
7. Создайте больше восьми записей и проверьте пагинацию истории.

### Цель

1. Добавьте текущее измерение веса, затем нажмите `🎯 Цель` или отправьте
   `/goal`.
2. Создайте цель со сроком и проверьте стартовый вес, остаток, процент и шкалу
   из десяти сегментов.
3. Добавьте новое измерение ближе к цели: процент и заполнение шкалы должны
   увеличиться.
4. Создайте цель на набор массы и проверьте расчёт в обратном направлении.
5. Добавьте вес в противоположную сторону: прогресс должен остаться на `0%`.
6. Добавьте вес за целевым значением: должна появиться карточка `Цель
   достигнута!`, шкала `██████████ 100%` и кнопки завершения или новой цели.
7. Удалите историю веса, создайте цель и проверьте подсказку с кнопкой
   `➕ Добавить вес`; после первой записи веса она должна стать стартовой точкой.
8. Проверьте цель без срока: карточка должна показывать `Срок: не указан`.
9. Замените активную цель через экран подтверждения.
10. Завершите цель и убедитесь, что активной цели больше нет.
11. Создайте новую цель и отмените её через экран подтверждения.

### UX и ошибки

1. Отправьте `/help` и нажмите `❓ Помощь`: должна открыться краткая справка.
2. Нажмите `⚙️ Настройки` и смените часовой пояс; повторно откройте раздел и
   убедитесь, что выбор сохранился.
3. На границе календарного дня проверьте, что `📅 Сегодня` определяется по
   выбранному часовому поясу пользователя.
4. В `🎛 Отображение` последовательно выберите автоматическую точность, один и
   два знака; проверьте числа в рационе, ингредиентах, весе и цели.
5. В `📅 Поведение дневника` проверьте оба варианта после добавления еды:
   открытие локального «Сегодня» и возврат к выбору следующего продукта.
6. Откройте `ℹ️ О боте`: должны отображаться версия текущего релиза и среда
   `production`, но не адрес БД и не токен.
7. Откройте `🔐 Данные и приватность` → `📊 Мои данные` и сравните счётчики с
   созданными ингредиентами, блюдами, рационом, весом и активной целью.
8. Начните удаление и нажмите `❌ Отмена`: данные должны сохраниться.
9. Повторите удаление, нажмите `🗑 Продолжить` и отправьте текст, отличный от
   точного `УДАЛИТЬ`: удаление должно отмениться.
10. Полное удаление проверяйте отдельным тестовым аккаунтом: отправьте точную
    фразу `УДАЛИТЬ`, убедитесь в нулевых счётчиках и работе `/start`.
11. Во время любого сценария ввода отправьте `/cancel`: состояние должно
   очиститься и появиться главное меню.
12. Отправьте неизвестный текст вне сценария: бот должен предложить меню и
   `/help`.
13. Нажмите старую inline-кнопку после удаления связанного объекта: бот не должен
   падать и должен сообщить, что объект или кнопка устарели.
14. Создайте больше восьми записей рациона за один день и проверьте пагинацию
   экрана `✏️ Изменить рацион`.

### Финальный сценарий D7

1. Создайте нового Telegram-пользователя через `/start`.
2. Создайте ингредиент и блюдо, затем найдите их с опечатками.
3. Добавьте блюдо в рацион и откройте `📅 Сегодня`.
4. Добавьте вес, создайте цель и новым измерением получите `50%` прогресса.
5. Измените timezone, точность чисел и поведение дневника.
6. Откройте `📊 Мои данные` и проверьте итоговые счётчики.
7. Полное удаление выполняйте только отдельным тестовым аккаунтом.

### Финальный checklist D19

Перед релизом выполните `./scripts/regression.sh`, затем
`./scripts/deploy.sh`. После deploy:

1. Проверьте `docker compose ps` и
   `docker compose exec -T bot python scripts/healthcheck.py`: DB, heartbeat и
   revision должны быть healthy.
2. Откройте `/admin` → `Состояние системы`: `Bot`, `Database`, `Telegram`,
   `Scheduler` и `DB revision` должны иметь статус `OK`.
3. Выполните `docker compose restart bot`, дождитесь healthy и убедитесь по
   `docker compose logs bot`, что присутствуют shutdown и новый startup, а
   созданные ранее данные и расписание напоминаний сохранились.
4. На тестовом аккаунте проверьте цель КБЖУ сегодня, смену цели со следующего
   дня и отображение старого дня с прежней целью.
5. Откройте графики за 7, 30, 90, 180 и 365 дней; проверьте произвольный период
   364 дня и отказ для 366 дней.
6. Настройте напоминание на ближайшее время, проверьте доставку в выбранном
   timezone, восстановление после restart и отсутствие доставки после
   отключения.

Spam burst, двойное подтверждение, controlled exception с correlation ID и
admin alert, 40 параллельных DB-запросов, история целей, границы графика и
восстановление scheduler дополнительно проверяются автоматически. Эти проверки
не нужно воспроизводить на рабочем Telegram-аккаунте массовой отправкой updates.
