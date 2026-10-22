const $ = (id) => document.getElementById(id);
const escapeHTML = (value) =>
  String(value ?? "").replace(
    /[&<>"']/g,
    (character) =>
      ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;",
      })[character],
  );
const money = (value) =>
  new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 2 }).format(Number(value)) + " ₽";
const priceFields = [
  { name: "sku", label: "Артикул", required: true },
  { name: "name", label: "Название", required: true },
  { name: "price", label: "Цена", required: true },
  { name: "stock", label: "Остаток", required: false },
];
let fields = [
  { name: "Код", type: "text", required: true },
  { name: "Название", type: "text", required: false },
  { name: "Сумма", type: "number", required: false },
  { name: "Город", type: "text", required: false },
];
let files = [];
let result = null;
let activeTab = "products";
let inspectionVersion = 0;
let resultVersion = 0;
let busy = false;

async function api(path, payload) {
  const response = await fetch(
    path,
    payload
      ? {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        }
      : {},
  );
  const data = await response.json();
  if (!response.ok) throw Error(data.error || "Не удалось выполнить запрос.");
  return data;
}

function showError(message) {
  $("error").textContent = message;
  $("error").hidden = !message;
}

function invalidate() {
  resultVersion += 1;
  result = null;
  $("results").hidden = true;
  showError("");
}

function setBusy(value) {
  busy = value;
  $("analyze").disabled = value || !files.length || files.some((file) => !file.headers);
  $("sample").disabled = value;
}

function schema() {
  return $("mode").value === "prices" ? priceFields : fields;
}

function payload() {
  return {
    mode: $("mode").value,
    fields,
    deduplicate: $("deduplicate").checked,
    files: files.map(({ name, text, delimiter, header_row, mapping }) => ({
      name,
      text,
      delimiter,
      header_row,
      mapping,
    })),
  };
}

function download(text, filename, type) {
  const url = URL.createObjectURL(new Blob([text], { type }));
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function updateFiles() {
  $("file-list").replaceChildren();
  files.forEach((file, index) => {
    const chip = document.createElement("div");
    chip.className = "file-chip";
    chip.textContent = "▤ " + file.name;
    const remove = document.createElement("button");
    remove.textContent = "×";
    remove.setAttribute("aria-label", "Удалить " + file.name);
    remove.onclick = () => {
      if (busy) return;
      files.splice(index, 1);
      invalidate();
      updateFiles();
      renderMappings();
    };
    chip.append(remove);
    $("file-list").append(chip);
  });
  setBusy(busy);
}

async function inspectFiles(preserve = true) {
  const version = ++inspectionVersion;
  invalidate();
  if (!files.length) {
    renderMappings();
    setBusy(false);
    return;
  }
  setBusy(true);
  try {
    const data = await api("/api/inspect", payload());
    if (version !== inspectionVersion) return;
    data.files.forEach((source, index) => {
      const old = preserve ? files[index].mapping || {} : {};
      files[index].headers = source.headers;
      files[index].preview = source.preview;
      files[index].mapping = {};
      for (const field of schema()) {
        const previous = old[field.name];
        files[index].mapping[field.name] =
          preserve &&
          Object.hasOwn(old, field.name) &&
          (!previous || source.headers.includes(previous))
            ? previous
            : source.suggestions[field.name] || "";
      }
    });
    renderMappings();
  } catch (error) {
    if (version === inspectionVersion) {
      files.forEach((file) => {
        file.headers = null;
      });
      renderMappings();
      showError(error.message);
    }
  } finally {
    if (version === inspectionVersion) setBusy(false);
  }
}

function renderMappings() {
  if (!files.length) {
    $("mapping-list").innerHTML =
      '<p class="mapping-empty">Загрузите файлы, чтобы увидеть их колонки и первые строки.</p>';
    return;
  }
  $("mapping-list").innerHTML = files
    .map((file, index) => {
      const headers = file.headers || [];
      const controls = schema()
        .map(
          (field) => `<label>${escapeHTML(field.label || field.name)}${field.required ? " *" : ""}
      <select data-file="${index}" data-field="${escapeHTML(field.name)}">
      <option value="">${field.required ? "Выберите колонку" : "Не использовать"}</option>
      ${headers.map((header) => `<option value="${escapeHTML(header)}"${file.mapping?.[field.name] === header ? " selected" : ""}>${escapeHTML(header)}</option>`).join("")}
      </select></label>`,
        )
        .join("");
      const preview = file.preview || [];
      return `<details class="mapping-file"${index === 0 ? " open" : ""}>
      <summary><strong>${escapeHTML(file.name)}</strong><span>${headers.length} колонок · настроить ↓</span></summary>
      <div class="source-settings">
        <label>Разделитель<select data-setting="delimiter" data-file="${index}">${[
          ["auto", "Автоматически"],
          [";", "Точка с запятой"],
          [",", "Запятая"],
          ["\t", "Табуляция"],
          ["|", "Вертикальная черта"],
        ]
          .map(
            ([value, label]) =>
              `<option value="${escapeHTML(value)}"${file.delimiter === value ? " selected" : ""}>${label}</option>`,
          )
          .join("")}</select></label>
        <label>Строка заголовков<input data-setting="header_row" data-file="${index}" type="number" min="1" max="20" value="${file.header_row || 1}"></label>
        <label>Кодировка<select data-setting="encoding" data-file="${index}"${file.buffer ? "" : " disabled"}><option value="utf-8"${file.encoding !== "windows-1251" ? " selected" : ""}>UTF-8</option><option value="windows-1251"${file.encoding === "windows-1251" ? " selected" : ""}>Windows-1251</option></select></label>
      </div><div class="mapping-fields">${controls}</div>
      ${headers.length ? `<details class="preview-block"><summary>Первые строки исходного файла</summary><div class="table-scroll"><table><thead><tr>${headers.map((header) => `<th>${escapeHTML(header)}</th>`).join("")}</tr></thead><tbody>${preview.map((row) => "<tr>" + headers.map((header) => `<td>${escapeHTML(row[header])}</td>`).join("") + "</tr>").join("")}</tbody></table></div></details>` : '<p class="mapping-empty">Проверьте разделитель и строку заголовков.</p>'}
      </details>`;
    })
    .join("");
  $("mapping-list")
    .querySelectorAll("[data-field]")
    .forEach((select) => {
      select.onchange = () => {
        files[Number(select.dataset.file)].mapping[select.dataset.field] = select.value;
        invalidate();
      };
    });
  $("mapping-list")
    .querySelectorAll("[data-setting]")
    .forEach((control) => {
      control.onchange = async () => {
        const file = files[Number(control.dataset.file)];
        const key = control.dataset.setting;
        file[key] = key === "header_row" ? Number(control.value) : control.value;
        if (key === "encoding" && file.buffer) {
          try {
            file.text = new TextDecoder(file.encoding, { fatal: true }).decode(file.buffer);
          } catch {
            showError("Не удалось прочитать файл в выбранной кодировке.");
            setBusy(true);
            $("sample").disabled = false;
            return;
          }
        }
        await inspectFiles();
      };
    });
}

async function readFiles(list) {
  try {
    if (!list.length || list.length > 5) throw Error("Выберите от 1 до 5 CSV-файлов.");
    const loaded = [];
    for (const file of list) {
      if (!file.name.toLowerCase().endsWith(".csv"))
        throw Error("Поддерживается CSV. XLSX сначала сохраните как CSV.");
      if (file.size > 600000) throw Error("Один файл должен быть не больше 600 КБ.");
      const buffer = await file.arrayBuffer();
      let text,
        encoding = "utf-8";
      try {
        text = new TextDecoder(encoding, { fatal: true }).decode(buffer);
      } catch {
        encoding = "windows-1251";
        text = new TextDecoder(encoding).decode(buffer);
      }
      loaded.push({ name: file.name, text, buffer, encoding, delimiter: "auto", header_row: 1 });
    }
    files = loaded;
    updateFiles();
    await inspectFiles(false);
  } catch (error) {
    showError(error.message);
  }
}

function renderTypes() {
  $("field-types").innerHTML = fields
    .map(
      (field, index) =>
        `<div class="field-rule"><span>${escapeHTML(field.name)}</span><label>Тип<select data-type="${index}">${[
          ["text", "Текст"],
          ["number", "Число"],
          ["integer", "Целое число"],
        ]
          .map(
            ([key, label]) =>
              `<option value="${key}"${field.type === key ? " selected" : ""}>${label}</option>`,
          )
          .join(
            "",
          )}</select></label><label class="required-option"><input data-required="${index}" type="checkbox"${field.required ? " checked" : ""}>Обязательно</label></div>`,
    )
    .join("");
  $("field-types")
    .querySelectorAll("[data-type]")
    .forEach((control) => {
      control.onchange = () => {
        fields[Number(control.dataset.type)].type = control.value;
        invalidate();
      };
    });
  $("field-types")
    .querySelectorAll("[data-required]")
    .forEach((control) => {
      control.onchange = () => {
        fields[Number(control.dataset.required)].required = control.checked;
        invalidate();
        renderMappings();
      };
    });
}

$("apply-fields").onclick = async () => {
  const names = $("field-names")
    .value.split(",")
    .map((name) => name.trim())
    .filter(Boolean);
  if (
    !names.length ||
    names.length > 20 ||
    new Set(names.map((name) => name.toLowerCase())).size !== names.length ||
    names.some((name) => name.length > 60 || name.startsWith("__"))
  ) {
    showError("Укажите от 1 до 20 разных названий до 60 символов, без префикса __.");
    return;
  }
  fields = names.map(
    (name) =>
      fields.find((field) => field.name === name) || { name, type: "text", required: false },
  );
  renderTypes();
  await inspectFiles(false);
};

$("mode").onchange = async () => {
  const prices = $("mode").value === "prices";
  $("custom-schema").hidden = prices;
  $("mode-hint").textContent = prices
    ? "Артикул связывает предложения поставщиков. Названия исходных колонок могут быть любыми."
    : "Задайте столбцы результата и сопоставьте с ними колонки каждого файла. Строки будут добавлены друг за другом.";
  renderTypes();
  await inspectFiles(false);
};
$("deduplicate").onchange = invalidate;
$("files").onchange = (event) => readFiles([...event.target.files]);
for (const event of ["dragover", "dragenter"])
  $("dropzone").addEventListener(event, (e) => {
    e.preventDefault();
    $("dropzone").classList.add("drag");
  });
for (const event of ["dragleave", "drop"])
  $("dropzone").addEventListener(event, (e) => {
    e.preventDefault();
    $("dropzone").classList.remove("drag");
    if (event === "drop") readFiles([...e.dataTransfer.files]);
  });
$("sample").onclick = async () => {
  try {
    const data = await api("/api/sample");
    files = data.files.map((file) => ({
      ...file,
      encoding: "utf-8",
      delimiter: "auto",
      header_row: 1,
    }));
    updateFiles();
    await inspectFiles(false);
  } catch (error) {
    showError(error.message);
  }
};

$("analyze").onclick = async () => {
  setBusy(true);
  invalidate();
  const version = resultVersion;
  const inspection = inspectionVersion;
  try {
    const data = await api("/api/analyze", payload());
    if (version !== resultVersion) return;
    result = data;
    const summary = result.summary;
    const cards = [
      [summary.input_rows, "Исходных записей", "Во всех загруженных файлах"],
      result.mode === "prices"
        ? [summary.products, "Товаров в каталоге", "Группировка по артикулу"]
        : [fields.length, "Столбцов результата", "Сопоставлены по вашим правилам"],
      [summary.valid_rows, "Принято записей", "С источниками и строками"],
      [
        summary.excluded_rows + summary.conflict_rows + summary.duplicates,
        "Отделено записей",
        "Ошибки, конфликты и дубли",
      ],
    ];
    $("metrics").innerHTML = cards
      .map(
        ([count, label, note]) =>
          `<div class="metric"><span>${label}</span><strong>${count}</strong><small>${note}</small></div>`,
      )
      .join("");
    $("balance").textContent = summary.balance_ok
      ? "✓ Все исходные записи учтены"
      : "Баланс не сошёлся";
    $("issue-count").textContent = result.issues.length;
    $("results").hidden = false;
    activeTab = result.mode === "prices" ? "products" : "rows";
    document.querySelector('[data-tab="products"]').hidden = result.mode !== "prices";
    $("method").textContent =
      result.mode === "prices"
        ? "Сравниваются цены предложений с положительным или неуказанным остатком. Если остаток неизвестен, наличие не подтверждается. Если везде нулевой остаток, показаны цены без наличия. Конфликтующие строки одного источника отделяются."
        : "Строки собраны в порядке файлов. Столбцы __source и __line сохраняют происхождение записи. Полные совпадения удаляются только при включённой настройке. Связывание разных таблиц по ключу в этом режиме не выполняется.";
    $("search").value = "";
    render();
    $("results").scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (error) {
    if (version !== resultVersion) return;
    invalidate();
    showError(error.message);
  } finally {
    if (inspection === inspectionVersion) setBusy(false);
  }
};

function render() {
  if (!result) return;
  const schemas = {
    products: [
      ["sku", "Артикул"],
      ["name", "Наименование"],
      ["sources", "Источников"],
      ["min_price", "Лучшая цена"],
      ["spread", "Разница цен"],
      ["best_source", "Поставщик"],
      ["available", "Проверка"],
    ],
    issues: [
      ["source", "Источник"],
      ["line", "Строка"],
      ["sku", "Артикул"],
      ["type", "Тип"],
      ["reason", "Причина"],
    ],
    rows:
      result.mode === "merge"
        ? [
            ...result.fields.map((field) => [field.name, field.name]),
            ["__source", "Источник"],
            ["__line", "Строка"],
          ]
        : [
            ["source", "Источник"],
            ["line", "Строка"],
            ["sku", "Артикул"],
            ["name", "Наименование"],
            ["price", "Цена"],
            ["stock", "Остаток"],
          ],
  };
  document.querySelectorAll(".tab").forEach((button) => {
    button.classList.toggle("active", button.dataset.tab === activeTab);
    button.setAttribute("aria-selected", String(button.dataset.tab === activeTab));
  });
  const columns = schemas[activeTab];
  const source =
    activeTab === "rows" && result.mode === "merge"
      ? result.rows.map((row) => ({ ...row.values, __source: row.source, __line: row.line }))
      : result[activeTab];
  const query = $("search").value.trim().toLocaleLowerCase();
  const rows = source.filter((row) =>
    Object.values(row).some((value) =>
      String(value ?? "")
        .toLocaleLowerCase()
        .includes(query),
    ),
  );
  $("thead").innerHTML =
    "<tr>" +
    columns.map(([, label]) => `<th scope="col">${escapeHTML(label)}</th>`).join("") +
    "</tr>";
  $("tbody").innerHTML =
    rows
      .slice(0, 300)
      .map(
        (row) =>
          "<tr>" +
          columns
            .map(([key]) => {
              if (activeTab === "products" && key === "available") {
                const label = row.review
                  ? "Сверить название"
                  : row.available === null
                    ? "Остаток неизвестен"
                    : row.available
                      ? "В наличии"
                      : "Нет в наличии";
                return `<td><span class="tag ${row.review || !row.available ? "warn" : ""}">${label}</span></td>`;
              }
              const value =
                result.mode === "prices" && ["min_price", "spread", "price"].includes(key)
                  ? money(row[key])
                  : row[key];
              return `<td class="${key === "sku" ? "sku" : ""}">${escapeHTML(value)}</td>`;
            })
            .join("") +
          "</tr>",
      )
      .join("") || `<tr><td colspan="${columns.length}">Ничего не найдено</td></tr>`;
  $("row-count").textContent =
    `Записей: ${rows.length}${rows.length > 300 ? ", показаны первые 300" : ""}. Выгрузка содержит всю вкладку без фильтра.`;
}

document.querySelectorAll(".tab").forEach((button) => {
  button.onclick = () => {
    activeTab = button.dataset.tab;
    render();
  };
});
$("search").oninput = render;
$("download").onclick = () => {
  if (!result) return;
  const key = { products: "catalog", issues: "issues", rows: "normalized" }[activeTab];
  download(result.downloads[key], key + ".csv", "text/csv;charset=utf-8");
};
$("save-profile").onclick = () => {
  if (!files.length) {
    showError("Сначала загрузите и настройте файлы.");
    return;
  }
  const profile = {
    version: 1,
    mode: $("mode").value,
    fields,
    deduplicate: $("deduplicate").checked,
    files: files.map(({ name, delimiter, header_row, mapping, encoding }) => ({
      name,
      delimiter,
      header_row,
      mapping,
      encoding,
    })),
  };
  download(JSON.stringify(profile, null, 2), "table-rules.json", "application/json");
};
$("load-profile").onchange = async (event) => {
  try {
    const file = event.target.files[0];
    if (!file || file.size > 100000) throw Error("Файл правил должен быть не больше 100 КБ.");
    const profile = JSON.parse(await file.text());
    if (
      profile.version !== 1 ||
      !["prices", "merge"].includes(profile.mode) ||
      !Array.isArray(profile.files) ||
      !Array.isArray(profile.fields)
    )
      throw Error("Неизвестный формат правил.");
    if (
      !profile.fields.length ||
      profile.fields.length > 20 ||
      profile.fields.some(
        (field) =>
          !field ||
          typeof field.name !== "string" ||
          !field.name.trim() ||
          field.name.length > 60 ||
          field.name.startsWith("__") ||
          !["text", "number", "integer"].includes(field.type) ||
          typeof field.required !== "boolean",
      )
    )
      throw Error("Некорректные столбцы в файле правил.");
    if (
      new Set(profile.fields.map((field) => field.name.toLowerCase())).size !==
        profile.fields.length ||
      profile.files.some(
        (item) =>
          !item ||
          typeof item.name !== "string" ||
          !["auto", ";", ",", "\t", "|"].includes(item.delimiter) ||
          !Number.isInteger(item.header_row) ||
          item.header_row < 1 ||
          item.header_row > 20 ||
          !["utf-8", "windows-1251"].includes(item.encoding) ||
          !item.mapping ||
          typeof item.mapping !== "object" ||
          Array.isArray(item.mapping),
      )
    )
      throw Error("Некорректные настройки источников.");
    if (!files.length) throw Error("Сначала загрузите исходные CSV-файлы.");
    if (
      profile.files.length !== files.length ||
      files.some((source) => !profile.files.some((item) => item.name === source.name))
    )
      throw Error("Имена загруженных файлов должны совпадать с сохранёнными правилами.");
    for (const source of files) {
      const settings = profile.files.find((item) => item.name === source.name);
      Object.assign(source, {
        delimiter: settings.delimiter,
        header_row: settings.header_row,
        mapping: settings.mapping,
        encoding: settings.encoding,
      });
      if (source.buffer)
        source.text = new TextDecoder(source.encoding, { fatal: true }).decode(source.buffer);
    }
    fields = profile.fields;
    $("mode").value = profile.mode;
    $("custom-schema").hidden = profile.mode !== "merge";
    $("field-names").value = fields.map((field) => field.name).join(", ");
    $("deduplicate").checked = profile.deduplicate === true;
    renderTypes();
    await inspectFiles();
  } catch (error) {
    showError(error.message);
  } finally {
    event.target.value = "";
  }
};
renderTypes();
