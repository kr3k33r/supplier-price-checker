import csv
import io
from collections import defaultdict
from decimal import Decimal, InvalidOperation

from table_io import mapping_for, read_files, validate_fields

PRICE_FIELDS = [
    {"name": "sku", "label": "Артикул", "required": True},
    {"name": "name", "label": "Название товара", "required": True},
    {"name": "price", "label": "Цена", "required": True},
    {"name": "stock", "label": "Остаток", "required": False},
]


def number(value, integer=False, price=False):
    text = (
        str(value)
        .strip()
        .replace("\u00a0", "")
        .replace("\u202f", "")
        .replace(" ", "")
        .replace(",", ".")
    )
    try:
        result = Decimal(text)
    except InvalidOperation:
        raise ValueError("Ожидается число")
    if not result.is_finite() or result.copy_abs() > Decimal("1000000000"):
        raise ValueError("Число должно быть конечным и не больше миллиарда по модулю")
    if integer and result != result.to_integral_value():
        raise ValueError("Ожидается целое число")
    if price and (result < 0 or result.as_tuple().exponent < -2):
        raise ValueError("Цена должна быть неотрицательной с точностью до двух знаков")
    return int(result) if integer else result


def inspect(files, mode="prices", fields=None):
    if mode not in ["prices", "merge"]:
        raise ValueError("Неизвестный режим обработки.")
    schema = PRICE_FIELDS if mode == "prices" else validate_fields(fields)
    output = []
    for source in read_files(files):
        suggestions = {}
        for field in schema:
            try:
                suggestions.update(
                    mapping_for({}, source, [{**field, "required": False}], mode == "prices")
                )
            except ValueError:
                suggestions[field["name"]] = None
        output.append(
            {
                "name": source["name"],
                "headers": source["headers"],
                "delimiter": source["delimiter"],
                "preview": [record["values"] for record in source["records"][:3]],
                "suggestions": suggestions,
            }
        )
    return {"files": output}


def issue(source, row, sku, kind, reason):
    return {"source": source, "line": row, "sku": sku, "type": kind, "reason": reason}


def analyze(files):
    parsed = read_files(files)
    candidates, issues = [], []
    total, excluded, duplicates = 0, 0, 0
    for file, source in zip(files, parsed):
        mapping = mapping_for(file, source, PRICE_FIELDS, aliases=True)
        same_source = {}
        for record in source["records"]:
            total += 1
            raw = {
                key: record["values"].get(column, "").strip() if column else ""
                for key, column in mapping.items()
            }
            sku, line, name = raw["sku"], record["line"], source["name"]
            reason = None
            if record["malformed"]:
                reason = "Количество полей не совпадает с заголовком"
            elif not sku or len(sku) > 80:
                reason = "Пустой или слишком длинный артикул"
            elif not raw["name"] or len(raw["name"]) > 300:
                reason = "Пустое или слишком длинное название"
            try:
                price = number(raw["price"], price=True)
                stock = number(raw["stock"], integer=True) if mapping["stock"] else None
                if stock is not None and stock < 0:
                    raise ValueError("Остаток не может быть отрицательным")
            except ValueError as exc:
                reason = reason or str(exc)
            if reason:
                excluded += 1
                issues.append(issue(name, line, sku, "Ошибка", reason))
                continue
            entry = {
                "source": name,
                "line": line,
                "sku": sku,
                "name": raw["name"],
                "price": price,
                "stock": stock,
            }
            signature = (sku, raw["name"], price, stock)
            if signature in same_source:
                duplicates += 1
                issues.append(
                    issue(
                        name,
                        line,
                        sku,
                        "Дубль",
                        f"Точное повторение строки {same_source[signature]}",
                    )
                )
                continue
            same_source[signature] = line
            candidates.append(entry)
    per_source = defaultdict(list)
    for entry in candidates:
        per_source[(entry["source"], entry["sku"])].append(entry)
    blocked = set()
    for entries in per_source.values():
        if len(entries) > 1:
            for entry in entries:
                blocked.add((entry["source"], entry["line"]))
                issues.append(
                    issue(
                        entry["source"],
                        entry["line"],
                        entry["sku"],
                        "Конфликт",
                        "Один артикул в источнике имеет разные данные",
                    )
                )
    valid = [entry for entry in candidates if (entry["source"], entry["line"]) not in blocked]
    by_sku = defaultdict(list)
    for entry in valid:
        by_sku[entry["sku"]].append(entry)
    comparison = []
    for sku, entries in sorted(by_sku.items()):
        known_available = [
            entry for entry in entries if entry["stock"] is not None and entry["stock"] > 0
        ]
        unknown_stock = [entry for entry in entries if entry["stock"] is None]
        eligible = known_available + unknown_stock or entries
        low, high = min(entry["price"] for entry in eligible), max(
            entry["price"] for entry in eligible
        )
        winners = sorted({entry["source"] for entry in eligible if entry["price"] == low})
        naming_conflict = len({entry["name"].casefold() for entry in entries}) > 1
        availability = None if unknown_stock else bool(known_available)
        comparison.append(
            {
                "sku": sku,
                "name": entries[0]["name"],
                "sources": len(entries),
                "min_price": str(low),
                "max_price": str(high),
                "spread": str(high - low),
                "best_source": ", ".join(winners),
                "available": availability,
                "review": naming_conflict,
            }
        )
        if naming_conflict:
            issues.append(
                issue(
                    " / ".join(entry["source"] for entry in entries),
                    "",
                    sku,
                    "Проверить",
                    "Названия одного артикула различаются",
                )
            )
    return {
        "mode": "prices",
        "summary": {
            "input_rows": total,
            "valid_rows": len(valid),
            "excluded_rows": excluded,
            "duplicates": duplicates,
            "conflict_rows": len(blocked),
            "products": len(comparison),
            "balance_ok": total == len(valid) + excluded + duplicates + len(blocked),
        },
        "rows": [
            {
                key: str(value) if isinstance(value, Decimal) else value
                for key, value in entry.items()
            }
            for entry in valid
        ],
        "products": comparison,
        "issues": issues,
    }


def merge(files, fields, deduplicate=False):
    fields = validate_fields(fields)
    if type(deduplicate) is not bool:
        raise ValueError("Некорректный режим удаления дублей.")
    rows, issues, seen = [], [], {}
    total, excluded, duplicates = 0, 0, 0
    parsed = read_files(files)
    for file, source in zip(files, parsed):
        mapping = mapping_for(file, source, fields)
        for record in source["records"]:
            total += 1
            values, reasons = {}, []
            if record["malformed"]:
                reasons.append("Количество полей не совпадает с заголовком")
            for field in fields:
                key = field["name"]
                text = record["values"].get(mapping[key], "").strip() if mapping[key] else ""
                values[key] = text
                if not text:
                    if field["required"]:
                        reasons.append(f"Пустое поле «{key}»")
                elif field["type"] != "text":
                    try:
                        values[key] = str(number(text, integer=field["type"] == "integer"))
                    except ValueError:
                        reasons.append(f"Некорректное число в «{key}»")
            if reasons:
                excluded += 1
                issues.append(
                    issue(source["name"], record["line"], "", "Ошибка", "; ".join(reasons))
                )
                continue
            signature = tuple(values[field["name"]] for field in fields)
            if deduplicate and signature in seen:
                duplicates += 1
                issues.append(
                    issue(
                        source["name"],
                        record["line"],
                        "",
                        "Дубль",
                        f"Совпадает со строкой {seen[signature]}",
                    )
                )
                continue
            seen[signature] = f"{source['name']}:{record['line']}"
            rows.append({"source": source["name"], "line": record["line"], "values": values})
    return {
        "mode": "merge",
        "fields": fields,
        "rows": rows,
        "products": [],
        "issues": issues,
        "summary": {
            "input_rows": total,
            "valid_rows": len(rows),
            "excluded_rows": excluded,
            "duplicates": duplicates,
            "conflict_rows": 0,
            "products": 0,
            "balance_ok": total == len(rows) + excluded + duplicates,
        },
    }


def safe_csv(rows, fields):
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, delimiter=";", lineterminator="\r\n")

    def protect(value):
        value = "" if value is None else str(value)
        if value.lstrip().startswith(("=", "+", "-", "@")) or value.startswith(("\t", "\r", "\n")):
            value = "'" + value
        return value

    writer.writerow([protect(field) for field in fields])
    for row in rows:
        writer.writerow([protect(row.get(key)) for key in fields])
    return "\ufeff" + buffer.getvalue()
