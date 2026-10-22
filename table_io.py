import csv
import io

ALIASES = {
    "sku": {"артикул", "sku", "код", "код товара"},
    "name": {"название", "наименование", "товар", "name"},
    "price": {"цена", "стоимость", "price", "цена руб"},
    "stock": {"остаток", "количество", "stock", "наличие"},
}


def read_file(file):
    if not isinstance(file, dict):
        raise ValueError("Некорректное описание файла.")
    name, text = file.get("name"), file.get("text")
    if not isinstance(name, str) or not name.strip() or len(name) > 120:
        raise ValueError("Укажите имя файла длиной до 120 символов.")
    if not isinstance(text, str) or not text.strip() or len(text) > 600_000:
        raise ValueError(f"{name}: пустой или слишком большой файл.")
    header_row = file.get("header_row", 1)
    if type(header_row) is not int or not 1 <= header_row <= 20:
        raise ValueError(f"{name}: строка заголовка должна быть от 1 до 20.")
    lines = text.lstrip("\ufeff").splitlines(keepends=True)
    if header_row > len(lines):
        raise ValueError(f"{name}: строка заголовка отсутствует.")
    body = "".join(lines[header_row - 1 :])
    delimiter = file.get("delimiter", "auto")
    if delimiter not in ["auto", ";", ",", "\t", "|"]:
        raise ValueError(f"{name}: неизвестный разделитель.")
    if delimiter == "auto":
        try:
            delimiter = csv.Sniffer().sniff(lines[header_row - 1], delimiters=";,\t|").delimiter
        except csv.Error:
            delimiter = ";"
    reader = csv.reader(io.StringIO(body), delimiter=delimiter, strict=True)
    try:
        headers = next(reader)
        normalized = [h.strip().casefold() for h in headers]
        if not headers or len(headers) > 60 or any(not h or len(h) > 150 for h in normalized):
            raise ValueError(f"{name}: заголовки должны содержать от 1 до 60 непустых колонок.")
        if len(normalized) != len(set(normalized)):
            raise ValueError(f"{name}: повторяющиеся названия колонок.")
        records = []
        for values in reader:
            if not values or all(not value.strip() for value in values):
                continue
            if len(records) >= 20_000:
                raise ValueError("Лимит — 20 000 записей суммарно.")
            records.append(
                {
                    "line": reader.line_num + header_row - 1,
                    "values": dict(zip(headers, values)),
                    "malformed": len(values) != len(headers),
                }
            )
    except (csv.Error, StopIteration):
        raise ValueError(f"{name}: некорректная структура CSV.")
    return {"name": name.strip(), "headers": headers, "records": records, "delimiter": delimiter}


def read_files(files):
    if not isinstance(files, list) or not 1 <= len(files) <= 5:
        raise ValueError("Выберите от одного до пяти CSV-файлов.")
    parsed = [read_file(file) for file in files]
    names = [source["name"] for source in parsed]
    if len(set(names)) != len(names):
        raise ValueError("Имена файлов должны быть уникальными.")
    if sum(len(source["records"]) for source in parsed) > 20_000:
        raise ValueError("Лимит — 20 000 записей суммарно.")
    return parsed


def mapping_for(file, source, fields, aliases=False):
    explicit = file.get("mapping")
    if explicit is not None and not isinstance(explicit, dict):
        raise ValueError(f"{source['name']}: некорректное сопоставление колонок.")
    mapping = {}
    for field in fields:
        key = field["name"]
        if explicit is not None:
            column = explicit.get(key)
            if column is not None and (
                not isinstance(column, str) or column and column not in source["headers"]
            ):
                raise ValueError(f"{source['name']}: выбранная колонка для «{key}» отсутствует.")
        else:
            variants = ALIASES.get(key, {key.casefold()}) if aliases else {key.casefold()}
            matches = [h for h in source["headers"] if h.strip().casefold() in variants]
            column = matches[0] if len(matches) == 1 else None
        if not column and field.get("required"):
            raise ValueError(f"{source['name']}: выберите колонку для «{field.get('label', key)}».")
        mapping[key] = column or None
    used = [value for value in mapping.values() if value]
    if len(set(used)) != len(used):
        raise ValueError(f"{source['name']}: одна исходная колонка назначена нескольким полям.")
    if not used:
        raise ValueError(f"{source['name']}: сопоставьте хотя бы одну колонку.")
    return mapping


def validate_fields(fields):
    if not isinstance(fields, list) or not 1 <= len(fields) <= 20:
        raise ValueError("Укажите от 1 до 20 столбцов результата.")
    validated, names = [], set()
    for field in fields:
        if not isinstance(field, dict):
            raise ValueError("Некорректное описание столбца.")
        name = field.get("name")
        if not isinstance(name, str) or not name.strip() or len(name) > 60 or name.startswith("__"):
            raise ValueError("Название столбца: от 1 до 60 символов, без префикса __.")
        name = name.strip()
        if name.casefold() in names:
            raise ValueError("Названия столбцов результата должны различаться.")
        kind = field.get("type", "text")
        if (
            kind not in ["text", "number", "integer"]
            or type(field.get("required", False)) is not bool
        ):
            raise ValueError("Некорректный тип или обязательность столбца.")
        names.add(name.casefold())
        validated.append({"name": name, "type": kind, "required": field.get("required", False)})
    return validated
