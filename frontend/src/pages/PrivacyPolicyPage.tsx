import { ArrowLeft, Database, LockKeyhole, ScanBarcode, Trash2 } from "lucide-react";
import { Link } from "react-router-dom";

export function PrivacyPolicyPage() {
  return (
    <main className="policy-page">
      <article>
        <Link className="policy-back" to="/profile">
          <ArrowLeft aria-hidden="true" size={19} />
          Назад
        </Link>
        <p className="eyebrow">WTrackerBot</p>
        <h1>Политика конфиденциальности</h1>
        <p className="policy-lead">
          Приложение хранит только данные, необходимые для дневника питания,
          контроля веса, пользовательских настроек и напоминаний.
        </p>

        <section>
          <Database aria-hidden="true" />
          <div>
            <h2>Какие данные хранятся</h2>
            <p>
              Telegram ID, публичные данные профиля, ингредиенты, блюда, записи
              рациона и веса, цели, напоминания, настройки и история импорта.
            </p>
          </div>
        </section>
        <section>
          <LockKeyhole aria-hidden="true" />
          <div>
            <h2>Как используются данные</h2>
            <p>
              Данные используются только для работы WTrackerBot и не продаются.
              Авторизация Mini App проверяется по подписи Telegram.
            </p>
          </div>
        </section>
        <section>
          <ScanBarcode aria-hidden="true" />
          <div>
            <h2>Штрихкоды и камера</h2>
            <p>
              Камера включается только по вашему действию, а видеопоток не
              загружается на сервер. Штрихкод передается сервером в Open Food
              Facts для поиска сведений о продукте.
            </p>
          </div>
        </section>
        <section>
          <Trash2 aria-hidden="true" />
          <div>
            <h2>Экспорт и удаление</h2>
            <p>
              В разделе «Профиль» можно скачать данные в JSON или полностью
              удалить их с повторным подтверждением. Удаление необратимо.
            </p>
          </div>
        </section>
        <p className="policy-note">
          По вопросам обработки данных используйте диалог с ботом в Telegram.
        </p>
      </article>
    </main>
  );
}
