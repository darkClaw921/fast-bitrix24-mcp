#!/usr/bin/env python3
"""
Скрипт для анализа экспортированных JSON файлов из Bitrix24
Использование:
    python analyze_file.py <file_path> <operation> [--fields FIELDS] [--condition CONDITION] [--group-by GROUP_BY]
    
Примеры:
    # Подсчет всех записей
    python analyze_file.py exports/deal_export_20251109_131103.json count
    
    # Подсчет с условием по дате
    python analyze_file.py exports/deal_export_20251109_131103.json count --condition 'DATE_CREATE >= "2025-11-03 00:00:00" and DATE_CREATE < "2025-11-10 00:00:00"'
    
    # Сумма по полю с условием
    python analyze_file.py exports/deal_export_20251109_131103.json sum --fields OPPORTUNITY --condition 'CLOSED == "N"'
    
    # Группировка по полю
    python analyze_file.py exports/deal_export_20251109_131103.json count --group-by STAGE_ID
"""
import asyncio
import argparse
import json
from pathlib import Path
from pprint import pprint
from fast_bitrix24_mcp.tools.helper import analyze_export_file


async def main():
    parser = argparse.ArgumentParser(
        description="Анализ экспортированных JSON файлов из Bitrix24",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    
    parser.add_argument(
        "file_path",
        type=str,
        help="Путь к JSON файлу для анализа"
    )
    
    parser.add_argument(
        "operation",
        type=str,
        choices=["count", "sum", "avg", "min", "max"],
        help="Операция анализа: count, sum, avg, min, max"
    )
    
    parser.add_argument(
        "--fields",
        type=str,
        nargs="+",
        help="Поля для анализа (требуется для sum, avg, min, max). Можно указать несколько полей через пробел"
    )
    
    parser.add_argument(
        "--condition",
        type=str,
        help="Условие фильтрации в виде строки. Пример: 'DATE_CREATE >= \"2025-11-03 00:00:00\" and DATE_CREATE < \"2025-11-10 00:00:00\"'"
    )
    
    parser.add_argument(
        "--group-by",
        type=str,
        nargs="+",
        help="Поля для группировки. Можно указать несколько полей через пробел"
    )
    
    args = parser.parse_args()
    
    # Проверка существования файла
    file_path = Path(args.file_path)
    if not file_path.exists():
        print(f"Ошибка: файл не найден: {args.file_path}")
        return
    
    # Подготовка параметров
    fields = args.fields if args.fields else None
    condition = args.condition if args.condition else None
    group_by = args.group_by if args.group_by else None
    
    print(f"Анализ файла: {args.file_path}")
    print(f"Операция: {args.operation}")
    if fields:
        print(f"Поля: {fields}")
    if condition:
        print(f"Условие: {condition}")
    if group_by:
        print(f"Группировка: {group_by}")
    print("-" * 80)
    
    # Запуск анализа
    try:
        result = await analyze_export_file(
            file_path=str(file_path),
            operation=args.operation,
            fields=fields,
            condition=condition,
            group_by=group_by
        )
        
        # Вывод результата
        if "error" in result:
            print(f"Ошибка: {result['error']}")
            return
        
        print(f"\nРезультат анализа:")
        print(f"Операция: {result.get('operation', 'unknown')}")
        print(f"Всего записей после фильтрации: {result.get('total_records', 0)}")
        
        if group_by:
            print(f"\nГруппировка по полям: {result.get('group_by', [])}")
            print("\nРезультаты по группам:")
            for group_result in result.get('result', []):
                print(f"\n  Группа: {group_result.get('group', {})}")
                values = group_result.get('values', {})
                if 'count' in values:
                    print(f"    Количество: {values['count']}")
                else:
                    for field, value in values.items():
                        if value is not None:
                            print(f"    {field}: {value}")
        else:
            print("\nРезультат:")
            result_data = result.get('result', {})
            if 'count' in result_data:
                print(f"  Количество: {result_data['count']}")
            else:
                for field, value in result_data.items():
                    if value is not None:
                        print(f"  {field}: {value}")
        
        # Дополнительный вывод в JSON формате для сложных случаев
        if group_by or (fields and len(fields) > 1):
            print("\n" + "-" * 80)
            print("Полный результат (JSON):")
            print(json.dumps(result, ensure_ascii=False, indent=2))
            
    except Exception as e:
        print(f"Ошибка при выполнении анализа: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())

