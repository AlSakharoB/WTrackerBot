# Mini App Server Runbook

Этот runbook предназначен для одного production-сервера с Docker Compose.
Команды выполняются из корня репозитория. Не публикуйте вывод `docker compose
config`: он может содержать значения из `.env`.

## 1. DNS и firewall

1. Создайте DNS `A` для Mini App domain на IPv4 сервера.
2. Не создавайте `AAAA`, пока IPv6 не настроен на сервере и в firewall.
3. Разрешите текущий SSH port, `80/tcp`, `443/tcp` и при необходимости
   `443/udp` для HTTP/3.
4. Не открывайте `5432`, `8080`, `5173` и `5174` наружу.
5. Firewall меняйте из действующей SSH-сессии и не закрывайте ее до проверки
   второго подключения.

Проверка с внешней машины:

```bash
cp scripts/miniapp-audit.env.example /tmp/miniapp-audit.env
nano /tmp/miniapp-audit.env
ENV_FILE=/tmp/miniapp-audit.env ./scripts/miniapp_public_audit.sh
```

## 2. Production env

После `./scripts/sync_env.sh` задайте реальные секреты и следующие безопасные
параметры. `APP_VERSION` обновляйте вручную: синхронизация не перезаписывает
существующие значения.

```env
APP_ENVIRONMENT=production
APP_VERSION=1.1.0
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

Не помещайте `BOT_TOKEN`, пароль PostgreSQL или полный `DATABASE_URL` в issue,
логи, shell history и диагностические отчеты.

## 3. Первый deploy

```bash
git clone <repository-url> WTrackerBot
cd WTrackerBot
cp .env.example .env
chmod 600 .env
nano .env
./scripts/deploy.sh
```

Первый deploy выполняйте с `MINIAPP_ENABLED=false`. После него:

```bash
docker compose ps
docker compose exec -T bot python scripts/healthcheck.py
docker compose exec -T web python scripts/web_healthcheck.py --mode readiness
./scripts/miniapp_production_smoke.sh
```

## 4. Обычный deploy

```bash
git status --short
git pull --ff-only
./scripts/sync_env.sh
nano .env  # выставить APP_VERSION из релиза
./scripts/deploy.sh
```

Deploy создает и проверяет backup, применяет миграции, ожидает health и только
после smoke удаляет завершенные containers, unused images и build cache.
Named volumes не удаляются.

## 5. Rollout и BotFather

Порядок rollout:

1. `MINIAPP_ENABLED=false` и проверка инфраструктуры.
2. `MINIAPP_ENABLED=true` с Telegram ID администраторов в allowlist.
3. Расширение allowlist на ограниченную группу.
4. Пустой allowlist для глобального доступа.
5. Настройка Main Mini App URL через `@BotFather`.

```bash
./scripts/miniapp_rollout.sh status
./scripts/miniapp_rollout.sh checklist
```

В BotFather: `/mybots` -> bot -> `Bot Settings` -> `Configure Mini App` ->
`Enable Mini App` -> production HTTPS URL. Проверяйте также
`https://t.me/<bot_username>?startapp`.

При критической ошибке первым действием верните `MINIAPP_ENABLED=false` и
выполните deploy. Не удаляйте containers или volumes.

## 6. Health, logs и версии

```bash
docker compose ps
docker compose logs --no-color --tail=200 bot web miniapp
docker compose exec -T bot python scripts/healthcheck.py
docker compose exec -T web python scripts/web_healthcheck.py --mode readiness
./scripts/miniapp_production_smoke.sh
MINIAPP_OBSERVABILITY_SINCE=6h ./scripts/miniapp_observability.sh
```

Production smoke сверяет version и git commit frontend, API и бота. Auth smoke
принимает свежий `initData` только скрытым prompt:

```bash
python3 scripts/miniapp_auth_smoke.py https://app.example.com
```

## 7. Backup и restore

Каждый deploy создает проверенный PostgreSQL 16 custom dump. Ротация хранит два
последних файла. Просмотр не раскрывает данные:

```bash
docker compose run --rm --no-deps migrate ls -lh /backups
docker compose run --rm --no-deps migrate cat /backups/.last-verified
```

Restore является аварийной операцией. Сначала сохраните отдельную копию
текущего dump, проверьте `pg_restore --list`, согласуйте downtime и укажите имя
проверенного файла из marker. Выполняйте только на совместимой версии кода:

```bash
export BACKUP_FILE=nutrition_bot_YYYYMMDDTHHMMSSZ.dump
docker compose stop bot web miniapp
docker compose exec -T db sh -ec \
  'dropdb --force --if-exists -U "$POSTGRES_USER" "$POSTGRES_DB" && createdb -U "$POSTGRES_USER" "$POSTGRES_DB"'
docker compose run --rm --no-deps --entrypoint sh -e BACKUP_FILE backup -ec \
  'pg_restore --exit-on-error --no-owner --dbname "$PGDATABASE" "/backups/$BACKUP_FILE"'
docker compose up -d --wait
docker compose exec -T web python scripts/web_healthcheck.py --mode readiness
```

Не выполняйте restore поверх работающих bot/Web API и не запускайте
автоматический Alembic downgrade.

## 8. Rollback

Rollback разрешен только на совместимый предыдущий semver tag:

```bash
./scripts/rollback.sh v1.0.6
```

Скрипт не меняет основную checkout-ветку, не удаляет `.env`, DB/TLS volumes и
не выполняет downgrade схемы.

## 9. Disk и Docker cleanup

```bash
df -h /
docker system df
docker stats --no-stream
```

Успешный `deploy.sh` сам выполняет image/build-cache cleanup. Не запускайте
`docker compose down -v`: флаг `-v` удалит PostgreSQL, backups и TLS state.
Обычные `docker compose down` и `docker compose up -d` named volumes сохраняют.

## 10. Staging deployment regression

Не имитируйте аварии на production. На отдельном staging host последовательно
проверьте:

1. первый deploy на пустом Docker host;
2. deploy поверх существующей БД, повтор той же версии и следующую версию;
3. restart `bot`, `web`, `miniapp` и `db` с сохранением данных;
4. временную остановку PostgreSQL и восстановление health/readiness;
5. блокировку deploy при ошибке backup/migration, Web readiness и Caddy startup;
6. сохранение TLS state после restart Caddy;
7. совместимый rollback;
8. два deploy без роста unused images/build cache;
9. наличие только двух последних проверенных dump.

До и после сохраняйте только агрегированные результаты `docker system df`,
`df -h /`, `docker compose ps` и health-команд. Не сохраняйте rendered Compose,
request headers или `initData`.

## 11. Финальный release gate

```bash
RELEASE_GATE_STAGING_ATTESTED=true \
RELEASE_GATE_CLIENTS_ATTESTED=true \
RELEASE_GATE_CRITICAL_HIGH_DEFECTS=0 \
./scripts/release_gate.sh
```

Attestation выставляется только после staging regression, проверки
Android/iOS/Desktop/Web, обычных команд бота и подтверждения отсутствия
critical/high дефектов.
