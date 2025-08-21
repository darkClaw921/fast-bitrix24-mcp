# Топ-5 клиентов по сумме сделок
_Exported on 21.08.2025 at 17:00:15 GMT+3 from Cursor (1.4.5)_

---

**User**

используя mcp fast_bitrix24_mcp
Покажи топ-5 клиентов по сумме сделок клиенты это связанные контакты

---

**Cursor**

Сначала соберу сделки и контакты параллельно, чтобы посчитать суммы по `CONTACT_ID` и сопоставить имена для топ-5.
request:
{
  "fields_id": [
    "ID",
    "CONTACT_ID",
    "OPPORTUNITY",
    "CURRENCY_ID",
    "TITLE"
  ]
}
result:
==игорь==
  ID: 1
  Имя: игорь
  Отчество: None
  Фамилия: None
  Телефон: [{'ID': '1', 'VALUE_TYPE': 'WORK', 'VALUE': '+79308316666', 'TYPE_ID': 'PHONE'}]

==михаил==
  ID: 3
  Имя: михаил
  Отчество: None
  Фамилия: михайлов
  Телефон: [{'ID': '3', 'VALUE_TYPE': 'WORK', 'VALUE': '+79308316689', 'TYPE_ID': 'PHONE'}]


Сделаю экспорт сделок и контактов в JSON, затем посчитаю сумму `OPPORTUNITY` по `CONTACT_ID` и сопоставлю имена контактов; начну с экспорта в два потока.
{
  "entity": "contact",
  "select_fields": [
    "ID",
    "NAME",
    "SECOND_NAME",
    "LAST_NAME",
    "PHONE",
    "EMAIL"
  ]
}
result:
{
  "entity": "contact",
  "count": 2,
  "file": "exports/contact_export_20250821_165829.json"
}

Запущу анализ сумм сделок по `CONTACT_ID` и параллельно прочитаю JSON контактов для сопоставления имён.
{
  "file_path": "exports/deal_export_20250821_165828.json",
  "operation": "sum",
  "fields": "OPPORTUNITY",
  "group_by": [
    "CONTACT_ID"
  ]
}
result:
{
  "operation": "sum",
  "group_by": [
    "CONTACT_ID"
  ],
  "result": [
    {
      "group": {
        "CONTACT_ID": "1"
      },
      "values": {
        "OPPORTUNITY": 123.0
      }
    },
    {
      "group": {
        "CONTACT_ID": "0"
      },
      "values": {
        "OPPORTUNITY": 0.0
      }
    }
  ],
  "total_records": 2
}
Я завершил экспорт, агрегацию и сопоставление имен. Отмечу задачи выполненными и покажу итоговый топ-5.

- **План**
  - Экспортировать сделки и контакты в JSON.
  - Просуммировать `OPPORTUNITY` по `CONTACT_ID`.
  - Исключить `CONTACT_ID = 0` (без контакта).
  - Сопоставить `CONTACT_ID` с именами контактов.
  - Вывести топ-5 по сумме.

- **Топ-5 контактов по сумме сделок**
  1. игорь — 123.0
  2. михаил — 0.0

- **Примечание**
  - В данных только 2 контакта и 2 сделки; `CONTACT_ID=0` исключён.
  - Сумма для контактов рассчитана из `exports/deal_export_20250821_165828.json`, имена взяты из `exports/contact_export_20250821_165829.json`.

Я всё сделал: экспорт, агрегация и сопоставление отработали.

