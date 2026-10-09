"use strict";
const $ = (selector) => document.querySelector(selector);
const state = {
  boms: [],
  active: null,
  component: null,
  supplier: "direnc",
  csrf: "",
  page: "dashboard",
  query: "",
  jobs: new Map(),
  polling: new Set(),
  maxUpload: 0,
};
const titles = {
  dashboard: "Dashboard",
  workspace: "BoM Workspace",
  suppliers: "Supplier Explorer",
  procurement: "Procurement",
};
let toastTimer;

// All external data goes through textContent / DOM properties, never HTML parsing.
function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (key === "class") node.className = value;
    else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
    else if (key === "text") node.textContent = value;
    else if (
      ["checked", "disabled", "value", "selected", "hidden"].includes(key)
    )
      node[key] = value;
    else node.setAttribute(key, value);
  }
  for (const child of children.flat())
    if (child !== null && child !== undefined)
      node.append(
        child instanceof Node ? child : document.createTextNode(String(child)),
      );
  return node;
}
const btn = (text, handler, cls = "") =>
  el("button", { type: "button", class: cls, onclick: handler }, text);
const badge = (text, cls = "") => el("span", { class: `badge ${cls}` }, text);
function notify(text) {
  $("#toast").textContent = text;
  $("#toast").hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => {
    $("#toast").hidden = true;
  }, 7000);
}
function fail(error) {
  notify(error.message || "Request failed");
}
async function api(path, options = {}) {
  const headers = { "X-Sonar-CSRF": state.csrf, ...options.headers };
  if (options.body && !(options.body instanceof ArrayBuffer)) {
    headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(options.body);
  }
  const response = await fetch(path, {
    ...options,
    headers,
    credentials: "same-origin",
  });
  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    try {
      const body = await response.json();
      message =
        typeof body.detail === "string"
          ? body.detail
          : body.detail
              ?.map((e) => `${e.loc.slice(1).join(".")}: ${e.msg}`)
              .join(";") || message;
    } catch {}
    throw new Error(message);
  }
  return response.status === 204 ? null : response.json();
}
async function refresh() {
  const data = await api("/api/session");
  state.csrf = data.csrf;
  state.boms = data.boms;
  state.maxUpload = data.max_upload;
  if (!state.boms.some((b) => b.id === state.active))
    state.active = state.boms[0]?.id || null;
  $("#bom-count").textContent = state.boms.length;
  state.jobs = new Map((data.jobs || []).map((job) => [job.id, job]));
  for (const job of state.jobs.values())
    if (job.state !== "done" && !state.polling.has(job.id)) pollJob(job.id);
}
function activeBom() {
  return state.boms.find((b) => b.id === state.active);
}
function activeComponent() {
  const b = activeBom();
  return (
    b?.components.find((c) => c.id === state.component) ||
    b?.components.find((c) => c.selected && c.dnp === false) ||
    b?.components[0]
  );
}
function replaceBom(bom) {
  state.boms = state.boms.map((b) => (b.id === bom.id ? bom : b));
}
function navigate(page) {
  location.hash = page;
  if (state.page === page) render();
}
function heading(title, subtitle, action) {
  return el(
    "div",
    { class: "page-heading" },
    el(
      "div",
      {},
      el("div", { class: "eyebrow" }, "SONAR / A1"),
      el("h1", {}, title),
      el("p", {}, subtitle),
    ),
    action,
  );
}
function empty(title, description, action, mark = "▤") {
  return el(
    "div",
    { class: "empty" },
    el("div", { class: "empty-mark", "aria-hidden": "true" }, mark),
    el("h3", {}, title),
    el("p", {}, description),
    action,
  );
}
function stat(label, number, note) {
  return el(
    "div",
    { class: "stat" },
    el("div", { class: "stat-label" }, label),
    el("div", { class: "stat-number" }, number),
    el("div", { class: "stat-note" }, note),
  );
}
function notice(text, good = false) {
  return el("div", { class: `notice ${good ? "good" : ""}` }, text);
}
function field(label, input, hint) {
  const id = `field-${crypto.randomUUID()}`;
  input.id = id;
  return el(
    "div",
    { class: "field" },
    el("label", { for: id }, label),
    input,
    hint ? el("small", {}, hint) : null,
  );
}
function select(options, value, handler, label) {
  const node = el("select", {
    "aria-label": label,
    onchange: handler || (() => {}),
  });
  for (const [v, t] of options) node.append(el("option", { value: v }, t));
  node.value = value ?? "";
  return node;
}
function bomSelect() {
  return select(
    state.boms.map((b) => [b.id, `${b.name} · ${b.filename}`]),
    state.active,
    (e) => {
      state.active = e.target.value;
      state.component = null;
      render();
    },
    "Current BoM",
  );
}
function table(headers, rows) {
  return el(
    "div",
    { class: "table-wrap" },
    el(
      "table",
      {},
      el(
        "thead",
        {},
        el(
          "tr",
          {},
          headers.map((h) => el("th", { scope: "col" }, h)),
        ),
      ),
      el("tbody", {}, rows),
    ),
  );
}
function modal(title, subtitle) {
  $("#dialog").setAttribute("aria-label", title);
  const body = $("#dialog-body");
  body.replaceChildren();
  body.append(
    el(
      "div",
      { class: "dialog-head" },
      el("div", {}, el("h2", {}, title), el("p", {}, subtitle)),
      btn("×", () => $("#dialog").close(), "text-button"),
    ),
  );
  $("#dialog").showModal();
  return body;
}
function modalError(body, error) {
  body.querySelector(".error-box")?.remove();
  body.prepend(el("div", { class: "error-box", role: "alert" }, error.message));
}
function addUpload() {
  const input = el("input", {
    type: "file",
    accept: ".csv,.tsv,.xlsx",
    "aria-label": "Choose a BoM file",
    class: "hidden",
  });
  input.addEventListener("change", () => {
    if (input.files[0]) previewFile(input.files[0]).catch(fail);
    input.remove();
  });
  input.addEventListener("cancel", () => input.remove(), { once: true });
  document.body.append(input);
  input.click();
}
async function previewFile(file, sheet) {
  if (file.size > state.maxUpload)
    throw new Error(`Upload limit is ${state.maxUpload / 1024 / 1024} MB`);
  notify("Reading your BoM…");
  const preview = await api(
    `/api/import/preview${sheet ? `?sheet=${encodeURIComponent(sheet)}` : ""}`,
    {
      method: "POST",
      headers: {
        "X-Filename": encodeURIComponent(file.name),
        "Content-Type": "application/octet-stream",
      },
      body: await file.arrayBuffer(),
    },
  );
  $("#dialog").close();
  const body = modal(
    "Review your import",
    `${preview.row_count} components · header at row ${preview.header_row}. All source columns will be preserved.`,
  );
  const name = el("input", {
    value: file.name.replace(/\.[^.]+$/, ""),
    maxlength: 150,
  });
  body.append(field("BoM name", name));
  if (preview.sheets.length > 1)
    body.append(
      field(
        "Worksheet",
        select(
          preview.sheets.map((s) => [s, s]),
          preview.sheet,
          (e) => {
            previewFile(file, e.target.value).catch((error) =>
              modalError(body, error),
            );
          },
          "Worksheet",
        ),
      ),
    );
  const mappings = {},
    grid = el("div", { class: "mapping-grid" });
  const labels = {
    name: "Component name",
    mpn: "Manufacturer MPN",
    quantity: "Quantity per PCB",
    references: "References",
    dnp: "DNP / Fitted",
  };
  for (const [key, label] of Object.entries(labels)) {
    const node = select(
      [
        ["", "Not mapped"],
        ...preview.headers.map((h, i) => [String(i), `${i + 1} · ${h}`]),
      ],
      preview.mapping[key],
      null,
      label,
    );
    mappings[key] = node;
    grid.append(el("label", {}, label), node);
  }
  body.append(
    grid,
    notice(
      "Missing quantities are inferred only when a references column is mapped and quantity is unmapped. Fitted / Populate columns are interpreted inversely. Unknown DNP values require review.",
    ),
  );
  body.append(
    el("h3", {}, "Source preview"),
    el(
      "div",
      { class: "preview-wrap" },
      table(
        preview.headers,
        preview.sample.map((row) =>
          el(
            "tr",
            {},
            row.map((v) => el("td", {}, v || "—")),
          ),
        ),
      ),
    ),
  );
  const submit = btn(
    "Import BoM",
    async () => {
      submit.disabled = true;
      try {
        const mapping = {};
        for (const [k, v] of Object.entries(mappings))
          if (v.value !== "") mapping[k] = Number(v.value);
        const bom = await api("/api/boms", {
          method: "POST",
          body: { preview_id: preview.preview_id, name: name.value, mapping },
        });
        state.boms.push(bom);
        state.active = bom.id;
        state.component = null;
        $("#bom-count").textContent = state.boms.length;
        $("#dialog").close();
        notify(`Imported ${bom.components.length} components`);
        navigate("workspace");
      } catch (error) {
        modalError(body, error);
      } finally {
        submit.disabled = false;
      }
    },
    "primary",
  );
  body.append(
    el(
      "div",
      { class: "dialog-footer" },
      btn("Cancel", () => $("#dialog").close()),
      submit,
    ),
  );
}

function dashboard(main) {
  const components = state.boms.flatMap((b) => b.components);
  const selected = components.filter((c) => c.selected && c.dnp !== true);
  const choiceCount = selected.filter((c) => c.choice).length;
  const issues = components.filter((c) => c.issues.length).length;
  main.append(
    el(
      "div",
      { class: "hero" },
      el(
        "div",
        {},
        el("div", { class: "eyebrow" }, "YOUR ENGINEERING WORKSPACE"),
        el("h1", {}, "From design to procurement."),
        el(
          "p",
          {},
          "Bring your BoM into focus. Review components, explore Turkish suppliers and build a purchasing list you can trust.",
        ),
        btn("+ Import a BoM", addUpload, "primary"),
      ),
      el(
        "div",
        { class: "hero-art", "aria-hidden": "true" },
        el("div", { class: "radar" }, el("span", {}, "SIGNAL → SOURCE")),
      ),
    ),
  );
  main.append(
    el(
      "div",
      { class: "stats" },
      stat(
        "BoMs in this session",
        state.boms.length,
        "Altium Designer & KiCad",
      ),
      stat(
        "Component rows",
        components.length,
        `${components.filter((c) => c.dnp === true).length} marked DNP`,
      ),
      stat(
        "Required components",
        selected
          .reduce((sum, c) => sum + (c.required || 0), 0)
          .toLocaleString(),
        `${selected.filter((c) => c.required === null).length} rows have unresolved quantities`,
      ),
      stat(
        "Products selected",
        `${choiceCount} / ${selected.length}`,
        `${issues} rows need review`,
      ),
    ),
  );
  const recent = el(
    "div",
    { class: "panel" },
    el(
      "div",
      { class: "section-head" },
      el("h2", {}, "Session BoMs"),
      btn("View workspace →", () => navigate("workspace"), "text-button"),
    ),
  );
  if (!state.boms.length)
    recent.append(
      empty(
        "Start with your design",
        "Import an Altium or KiCad BoM. Your real project statistics will appear here.",
        btn("Choose a BoM file", addUpload, "primary"),
      ),
    );
  for (const b of [...state.boms].reverse())
    recent.append(
      el(
        "div",
        { class: "bom-row" },
        el(
          "div",
          { class: "file-icon" },
          b.filename.split(".").pop().toUpperCase(),
        ),
        el(
          "div",
          { class: "bom-meta" },
          el("strong", {}, b.name),
          el(
            "small",
            {},
            `${b.components.length} rows · ${b.boards} PCB${b.boards === 1 ? "" : "s"}`,
          ),
        ),
        badge(
          `${b.components.filter((c) => c.issues.length).length} to review`,
          b.components.some((c) => c.issues.length) ? "warn" : "good",
        ),
        btn(
          "Open →",
          () => {
            state.active = b.id;
            navigate("workspace");
          },
          "text-button",
        ),
      ),
    );
  const readiness = el(
    "div",
    { class: "panel" },
    el("h2", {}, "Procurement readiness"),
    el("p", {}, "A clear view of what is known and what needs your attention."),
  );
  readiness.append(
    el(
      "div",
      { class: "check-list" },
      ...[
        [
          `${components.length - issues} rows without validation warnings`,
          "Warnings remain visible in the workspace.",
        ],
        [
          `${choiceCount} supplier products selected`,
          "Product candidates require your review.",
        ],
        [
          "Costs preserve their currency and VAT basis",
          "Unknown data never becomes a zero.",
        ],
      ].map(([title, sub]) =>
        el(
          "div",
          { class: "check-item" },
          el("span", {}, "↗"),
          el("div", {}, el("strong", {}, title), el("p", {}, sub)),
        ),
      ),
    ),
  );
  readiness.append(
    notice(
      "BoMs are stored in this browser’s server session. Export before the session expires or the server restarts.",
    ),
  );
  main.append(el("div", { class: "grid-two" }, recent, readiness));
}

function workspace(main) {
  main.append(
    heading(
      "BoM Workspace",
      "Inspect the design. Resolve uncertainty. Set your production quantity.",
      btn("+ Import BoM", addUpload, "primary"),
    ),
  );
  const b = activeBom();
  if (!b) {
    main.append(
      empty(
        "Your next build starts here",
        "Import CSV or XLSX from Altium, or CSV / TSV from KiCad. Review detected columns before importing.",
        btn("Choose a BoM file", addUpload, "primary"),
      ),
    );
    return;
  }
  const selector = bomSelect();
  selector.className = "bom-selector";
  const boards = el("input", {
    type: "number",
    min: 1,
    max: 100000,
    value: b.boards,
    "aria-label": "PCB production quantity",
  });
  const updateBoards = btn("Apply", async () => {
    try {
      const result = await api(`/api/boms/${b.id}`, {
        method: "PATCH",
        body: { boards: Number(boards.value) },
      });
      replaceBom(result);
      render();
      notify("Production quantities updated");
    } catch (e) {
      fail(e);
    }
  });
  const remove = btn(
    "Remove BoM",
    () => {
      const body = modal(
        "Remove this BoM?",
        `${b.name} will be removed from this session. Export your source or procurement list first if you need a copy.`,
      );
      body.append(
        el(
          "div",
          { class: "dialog-footer" },
          btn("Keep BoM", () => $("#dialog").close()),
          btn(
            "Remove BoM",
            async () => {
              try {
                await api(`/api/boms/${b.id}`, { method: "DELETE" });
                $("#dialog").close();
                await refresh();
                render();
              } catch (e) {
                modalError(body, e);
              }
            },
            "danger",
          ),
        ),
      );
    },
    "text-button",
  );
  main.append(
    el(
      "div",
      { class: "toolbar" },
      el(
        "div",
        { class: "actions" },
        selector,
        badge(`${b.filename}${b.sheet ? ` · ${b.sheet}` : ""}`),
      ),
      el(
        "div",
        { class: "actions" },
        el("label", {}, "PCBs"),
        boards,
        updateBoards,
        remove,
      ),
    ),
  );
  const warnings = b.components.filter((c) => c.issues.length).length;
  main.append(
    el(
      "div",
      { class: "stats" },
      stat(
        "Component rows",
        b.components.length,
        "Original rows kept separately",
      ),
      stat(
        "Production quantity",
        b.boards.toLocaleString(),
        "Required = quantity × PCBs",
      ),
      stat("Needs review", warnings, "Validation and missing fields"),
      stat(
        "DNP components",
        b.components.filter((c) => c.dnp === true).length,
        "Excluded from procurement",
      ),
    ),
  );
  const search = el("input", {
    type: "search",
    class: "search-input",
    placeholder: "Search name, MPN or reference…",
    value: state.query,
    "aria-label": "Search components",
  });
  const results = el("div");
  const draw = () => {
    const q = search.value.toLowerCase();
    state.query = search.value;
    const filtered = b.components.filter((c) =>
      `${c.name} ${c.mpn} ${c.references}`.toLowerCase().includes(q),
    );
    results.replaceChildren();
    const all = el("input", {
      type: "checkbox",
      "aria-label": "Select all visible populated components",
      checked:
        filtered.length > 0 &&
        filtered.filter((c) => c.dnp === false).every((c) => c.selected),
      onchange: async (e) => {
        all.disabled = true;
        try {
          const ids = filtered.filter((c) => c.dnp === false).map((c) => c.id);
          if (ids.length)
            replaceBom(
              await api(`/api/boms/${b.id}/selection`, {
                method: "POST",
                body: { component_ids: ids, selected: e.target.checked },
              }),
            );
          render();
        } catch (error) {
          fail(error);
        }
      },
    });
    const rows = filtered.map((c, index) => {
      const check = el("input", {
        type: "checkbox",
        checked: c.selected && c.dnp !== true,
        disabled: c.dnp !== false,
        "aria-label": `Select ${c.name || c.mpn || c.references}`,
        onchange: async (e) => {
          try {
            replaceBom(
              await api(`/api/boms/${b.id}/components/${c.id}`, {
                method: "PATCH",
                body: { selected: e.target.checked },
              }),
            );
            render();
          } catch (error) {
            e.target.checked = !e.target.checked;
            fail(error);
          }
        },
      });
      const status =
        c.dnp === true
          ? badge("DNP")
          : c.issues.length
            ? badge(`${c.issues.length} warnings`, "warn")
            : badge("Ready", "good");
      status.title = c.issues.join("\n");
      return el(
        "tr",
        { class: c.issues.length ? "row-warning" : "" },
        el("td", {}, check),
        el("td", { class: "mono" }, String(index + 1).padStart(2, "0")),
        el(
          "td",
          {},
          el(
            "div",
            { class: "component-name", title: c.name },
            c.name || "Unnamed component",
          ),
          el(
            "div",
            { class: "secondary" },
            c.references || "References missing",
          ),
        ),
        el("td", { class: "mono" }, c.mpn || "—"),
        el("td", { class: "mono" }, c.quantity || "—"),
        el(
          "td",
          { class: "mono" },
          c.required === null ? "Unknown" : c.required.toLocaleString(),
        ),
        el("td", {}, status),
        el(
          "td",
          {},
          c.choice ? badge("Selected", "good") : badge("Unassigned"),
        ),
        el(
          "td",
          {},
          btn("Edit", () => editComponent(b, c), "compact"),
          btn(
            "Explore",
            () => {
              state.component = c.id;
              navigate("suppliers");
            },
            "text-button",
          ),
        ),
      );
    });
    results.append(
      table(
        [
          all,
          "#",
          "COMPONENT / REFERENCES",
          "MANUFACTURER MPN",
          "QTY / PCB",
          "REQUIRED",
          "VALIDATION",
          "SUPPLIER",
          "ACTIONS",
        ],
        rows,
      ),
      el(
        "div",
        { class: "table-note" },
        el("span", {}, `${filtered.length} of ${b.components.length} rows`),
        el(
          "span",
          {},
          "Edit a row to view all source fields. Duplicate rows are never merged.",
        ),
      ),
    );
    if (!filtered.length)
      results.append(
        empty(
          "No matching components",
          "Try another MPN, component name or reference.",
          null,
          "⌕",
        ),
      );
  };
  search.addEventListener("input", draw);
  main.append(
    el(
      "div",
      { class: "toolbar" },
      search,
      el(
        "div",
        { class: "actions" },
        el(
          "a",
          { href: `/api/boms/${b.id}/source.csv` },
          "Export original source",
        ),
        btn("Explore selected components →", () => navigate("suppliers")),
      ),
    ),
  );
  draw();
  main.append(results);
}

function editComponent(bom, c) {
  const body = modal(
    "Edit component",
    "Changes to component data clear prior supplier results and selections. Original source fields remain available.",
  );
  const grid = el("div", { class: "dialog-grid" }),
    inputs = {};
  for (const [key, label] of [
    ["name", "Component name"],
    ["mpn", "Manufacturer MPN"],
    ["quantity", "Quantity per PCB"],
    ["references", "Reference designators"],
  ]) {
    inputs[key] = el("input", { value: c[key], maxlength: 2000 });
    grid.append(field(label, inputs[key]));
  }
  const dnp = select(
    [
      ["false", "Populate"],
      ["true", "DNP — do not populate"],
      ["unknown", "Unknown — requires review"],
    ],
    c.dnp === null ? "unknown" : String(c.dnp),
    null,
    "Population status",
  );
  grid.append(field("Population status", dnp));
  body.append(grid);
  if (c.issues.length)
    body.append(
      el(
        "ul",
        { class: "validation-list" },
        c.issues.map((issue) => el("li", {}, issue)),
      ),
    );
  const source = el(
    "details",
    {},
    el("summary", {}, "Original source fields"),
    el(
      "pre",
      { class: "source-fields" },
      Object.entries(c.raw)
        .map(([k, v]) => `${k}: ${v}`)
        .join("\n"),
    ),
  );
  body.append(source);
  const save = btn(
    "Save component",
    async () => {
      save.disabled = true;
      try {
        const updates = {};
        for (const [k, v] of Object.entries(inputs)) updates[k] = v.value;
        if (dnp.value !== "unknown") updates.dnp = dnp.value === "true";
        replaceBom(
          await api(`/api/boms/${bom.id}/components/${c.id}`, {
            method: "PATCH",
            body: updates,
          }),
        );
        $("#dialog").close();
        render();
        notify("Component updated");
      } catch (error) {
        modalError(body, error);
      } finally {
        save.disabled = false;
      }
    },
    "primary",
  );
  body.append(
    el(
      "div",
      { class: "dialog-footer" },
      btn("Cancel", () => $("#dialog").close()),
      save,
    ),
  );
}

async function launchJob(bom, ids, supplier, url, button) {
  button.disabled = true;
  try {
    const job = await api("/api/supplier-jobs", {
      method: "POST",
      body: {
        bom_id: bom.id,
        component_ids: ids,
        supplier,
        ...(url ? { url } : {}),
      },
    });
    state.jobs.set(job.id, job);
    render();
    pollJob(job.id);
  } catch (error) {
    fail(error);
  } finally {
    button.disabled = false;
  }
}
async function pollJob(id) {
  if (state.polling.has(id)) return;
  state.polling.add(id);
  try {
    while (true) {
      const job = await api(`/api/supplier-jobs/${id}`);
      state.jobs.set(id, job);
      if (job.state === "done") {
        await refresh();
        render();
        notify(
          job.message ||
            `Supplier lookup complete: ${job.completed} of ${job.total} components`,
        );
        return;
      }
      if (state.page === "suppliers") drawJobs();
      await new Promise((resolve) => setTimeout(resolve, 1500));
    }
  } catch (error) {
    state.jobs.delete(id);
    fail(error);
    if (state.page === "suppliers") drawJobs();
  } finally {
    state.polling.delete(id);
  }
}
function drawJobs() {
  const area = $("#jobs");
  if (!area) return;
  area.replaceChildren();
  for (const job of state.jobs.values())
    if (job.state !== "done")
      area.append(
        el(
          "div",
          { class: "job-status", role: "status" },
          `${job.state === "queued" ? "Queued" : "Retrieving supplier information"} · ${job.completed} / ${job.total} components`,
          el("progress", {
            value: job.completed,
            max: job.total,
            "aria-label": "Supplier lookup progress",
          }),
        ),
      );
}
function suppliers(main) {
  main.append(
    heading(
      "Supplier Explorer",
      "Find candidates. Compare source information. Make an informed selection.",
    ),
  );
  const b = activeBom();
  if (!b) {
    main.append(
      empty(
        "Import a BoM to explore suppliers",
        "Supplier searches are linked to your components and production quantities.",
        btn("Import BoM", addUpload, "primary"),
        "⌕",
      ),
    );
    return;
  }
  const c = activeComponent();
  state.component = c.id;
  const control = el(
    "div",
    { class: "panel" },
    el("h2", {}, "Find a supplier product"),
  );
  control.append(
    field("Current BoM", bomSelect()),
    field(
      "Component",
      select(
        b.components.map((c) => [
          c.id,
          `${c.references || "—"} · ${c.mpn || c.name || "Unnamed"}`,
        ]),
        c.id,
        (e) => {
          state.component = e.target.value;
          render();
        },
        "Component",
      ),
    ),
  );
  control.append(
    field(
      "Distributor",
      select(
        [
          ["direnc", "Direnc.net"],
          ["ozdisan", "Özdisan"],
        ],
        state.supplier,
        (e) => {
          state.supplier = e.target.value;
          render();
        },
        "Distributor",
      ),
    ),
  );
  const ready = c.selected && c.dnp === false && c.required !== null;
  control.append(
    el(
      "div",
      { class: "notice good" },
      `${c.mpn || "MPN missing"} · ${c.required === null ? "Quantity unresolved" : `${c.required} required`}`,
    ),
  );
  const search = btn(
    "Search this MPN",
    () => launchJob(b, [c.id], state.supplier, null, search),
    "primary wide",
  );
  search.disabled = !ready || !c.mpn || state.supplier === "ozdisan";
  control.append(search);
  if (state.supplier === "direnc") {
    const bulk = btn(
      "Search selected rows (up to 10)",
      () => {
        const ids = activeBom()
          .components.filter(
            (c) =>
              c.selected && c.dnp === false && c.required !== null && c.mpn,
          )
          .map((c) => c.id);
        if (ids.length > 10) {
          notify(
            "Select at most 10 eligible components in the workspace for a batch lookup.",
          );
          return;
        }
        if (!ids.length) {
          notify(
            "No eligible selected components. Review MPN, quantity and DNP.",
          );
          return;
        }
        launchJob(b, ids, state.supplier, null, bulk);
      },
      "text-button",
    );
    control.append(bulk);
  }
  const url = el("input", {
    type: "url",
    placeholder:
      state.supplier === "direnc"
        ? "https://www.direnc.net/…"
        : "https://www.ozdisan.com/p/…",
    maxlength: 2000,
  });
  control.append(
    el("hr"),
    field(
      "Known product URL",
      url,
      "HTTPS URLs on the selected supplier’s supported domains only.",
    ),
  );
  const read = btn(
    "Read product URL",
    () => {
      if (!url.value.trim()) {
        notify("Enter a supplier product URL");
        return;
      }
      launchJob(b, [c.id], state.supplier, url.value.trim(), read);
    },
    "wide",
  );
  read.disabled = !ready;
  control.append(read);
  if (!ready)
    control.append(
      notice(
        "Select this populated component and resolve quantity / DNP in the BoM Workspace before retrieval.",
      ),
    );
  control.append(
    el(
      "div",
      { class: "supplier-info" },
      state.supplier === "ozdisan"
        ? "Özdisan · Automatic discovery is restricted by the known robots policy. Use a product URL. Prices and stock may be incomplete."
        : "Direnc.net · Discovery is partial. Explicit manufacturer MPNs, stock counts and packaging may be absent. Title matches require review.",
    ),
  );
  const results = el("div", {}, el("div", { id: "jobs" }));
  const result = c.results[state.supplier];
  results.append(
    el(
      "div",
      { class: "section-head" },
      el(
        "div",
        {},
        el("h2", {}, "Product candidates"),
        el(
          "p",
          {},
          `${c.name || c.mpn} · ${c.references || "References unknown"}`,
        ),
      ),
      badge(
        result?.status.replaceAll("_", " ") || "Not searched",
        result?.status === "ok" ? "good" : "warn",
      ),
    ),
  );
  if (!result)
    results.append(
      empty(
        "Bring the supplier data into view",
        "Search an MPN or read a known product URL. Results are fetched on the backend with A0’s access restrictions.",
        null,
        "⌕",
      ),
    );
  else {
    if (result.message) results.append(notice(result.message));
    if (!result.offers.length)
      results.append(
        empty(
          "No product information retrieved",
          "A failed or restricted lookup does not mean zero stock. Check the status above or try a permitted product URL.",
          null,
          "⌕",
        ),
      );
    result.offers.forEach((offer, index) =>
      results.append(offerCard(b, c, result, offer, index)),
    );
  }
  for (const [supplier, comparison] of Object.entries(c.results)) {
    if (supplier === state.supplier) continue;
    results.append(
      el(
        "div",
        { class: "section-head" },
        el(
          "h2",
          {},
          `Also retrieved · ${supplier === "direnc" ? "Direnc.net" : "Özdisan"}`,
        ),
        badge(
          comparison.status.replaceAll("_", " "),
          comparison.status === "ok" ? "good" : "warn",
        ),
      ),
    );
    if (comparison.message) results.append(notice(comparison.message));
    comparison.offers.forEach((offer, index) =>
      results.append(offerCard(b, c, comparison, offer, index)),
    );
  }
  results.append(
    notice(
      "Supplier-reported information is a snapshot, not a purchase guarantee. VAT, availability and product identity must be verified before ordering.",
    ),
  );
  main.append(el("div", { class: "supplier-layout" }, control, results));
  drawJobs();
}

function offerCard(bom, c, result, offer, index) {
  const exact = offer.match === "exact_mpn";
  const card = el(
    "article",
    { class: "offer-card" },
    el(
      "div",
      { class: "offer-top" },
      el(
        "div",
        {},
        el(
          "div",
          { class: "eyebrow" },
          result.supplier === "direnc" ? "DIRENC.NET" : "ÖZDISAN",
        ),
        el("h3", {}, offer.title || "Unnamed supplier product"),
        el(
          "small",
          { class: "mono" },
          `MPN: ${offer.mpn || "not disclosed"} · SKU: ${offer.sku || "not disclosed"}`,
        ),
      ),
      badge(
        exact ? "Exact reported MPN" : "Unverified match",
        exact ? "good" : "warn",
      ),
    ),
  );
  const date = offer.fetched_at
    ? new Date(offer.fetched_at).toLocaleString()
    : "Unknown";
  const details = [
    ["Availability", offer.stock_status.replaceAll("_", " ")],
    [
      "Stock count",
      offer.stock_quantity === null
        ? "Not disclosed"
        : String(offer.stock_quantity),
    ],
    [
      "Manufacturer",
      `${offer.manufacturer || "Not disclosed"} (${offer.manufacturer_status})`,
    ],
    ["MOQ / multiple", `${offer.moq ?? "?"} / ${offer.order_multiple ?? "?"}`],
    [
      "Package / packaging",
      `${offer.package || "?"} / ${offer.packaging || "?"}`,
    ],
    ["Retrieved", date],
  ];
  card.append(
    el(
      "dl",
      { class: "offer-details" },
      details.map(([k, v]) => el("div", {}, el("dt", {}, k), el("dd", {}, v))),
    ),
  );
  const prices = el("div", { class: "price-list" }),
    radios = [];
  offer.prices.forEach((price, tier) => {
    const selected =
      c.choice?.supplier === result.supplier &&
      c.choice?.offer === index &&
      c.choice?.tier === tier;
    const radio = el("input", {
      type: "radio",
      name: `price-${c.id}-${result.supplier}-${index}`,
      value: tier,
      checked: selected || (!c.choice && tier === 0),
    });
    radios.push(radio);
    prices.append(
      el(
        "label",
        { class: "price-option" },
        radio,
        el(
          "span",
          {},
          el("strong", {}, `${price.unit_price} ${price.currency} / unit`),
          el("br"),
          `${price.min_quantity}+${price.max_quantity ? ` (max ${price.max_quantity})` : ""} · VAT ${price.vat}`,
          el("br"),
          price.packaging || "Packaging unknown",
        ),
      ),
    );
  });
  card.append(
    offer.prices.length
      ? prices
      : notice(
          "Price unavailable. This product can be selected with an unknown cost.",
        ),
  );
  if (offer.warnings.length)
    card.append(
      el(
        "ul",
        { class: "offer-warnings" },
        offer.warnings.map((w) => el("li", {}, w)),
      ),
    );
  const sources = el(
    "details",
    {},
    el("summary", {}, "Field sources and retrieval evidence"),
    el(
      "pre",
      { class: "source-fields" },
      JSON.stringify(
        {
          field_sources: offer.field_sources,
          request_evidence: result.evidence,
        },
        null,
        2,
      ),
    ),
  );
  card.append(sources);
  const acknowledge = el("input", { type: "checkbox" });
  if (!exact)
    card.append(
      el(
        "label",
        { class: "uncertain-check" },
        acknowledge,
        "I understand that this product match is unverified and needs engineering review.",
      ),
    );
  const choose = btn(
    c.choice?.supplier === result.supplier && c.choice?.offer === index
      ? "Update selection"
      : "Select product",
    async () => {
      if (!exact && !acknowledge.checked) {
        notify("Acknowledge the unverified product match before selecting it.");
        acknowledge.focus();
        return;
      }
      choose.disabled = true;
      try {
        const tier = radios.find((r) => r.checked)?.value;
        await api(`/api/boms/${bom.id}/components/${c.id}/choice`, {
          method: "PUT",
          body: {
            supplier: result.supplier,
            offer: index,
            tier: tier === undefined ? -1 : Number(tier),
            acknowledge_uncertain: exact || acknowledge.checked,
          },
        });
        await refresh();
        render();
        notify("Product added to procurement review");
      } catch (error) {
        fail(error);
      } finally {
        choose.disabled = false;
      }
    },
    "primary",
  );
  const link = el(
    "a",
    { href: "#", target: "_blank", rel: "noopener noreferrer" },
    "Original supplier product ↗",
  );
  try {
    const url = new URL(offer.url);
    if (
      url.protocol === "https:" &&
      [
        "www.direnc.net",
        "direnc.net",
        "www.ozdisan.com",
        "ozdisan.com",
      ].includes(url.hostname) &&
      !url.username &&
      !url.password
    )
      link.href = url.href;
  } catch {}
  card.append(el("div", { class: "offer-actions" }, link, choose));
  return card;
}

async function purchasing(main) {
  main.append(
    heading(
      "Procurement",
      "Review selected products, known costs and unresolved information.",
      el("a", { href: "/api/procurement.csv" }, "↓ Export procurement CSV"),
    ),
  );
  const loading = el(
    "div",
    { class: "loading" },
    "Preparing procurement review…",
  );
  main.append(loading);
  try {
    const report = await api("/api/procurement");
    if (state.page !== "procurement") return;
    loading.remove();
    if (!report.lines.length) {
      main.append(
        empty(
          "No components selected for procurement",
          "Import a BoM and select populated components in the workspace. Supplier product selection is available in the explorer.",
          btn("Open BoM Workspace", () => navigate("workspace")),
          "≡",
        ),
      );
      return;
    }
    const totals = el("div", { class: "totals" });
    for (const t of report.totals)
      totals.append(
        el(
          "div",
          { class: "total-box" },
          el(
            "small",
            {},
            `${t.supplier === "direnc" ? "Direnc.net" : "Özdisan"} · VAT ${t.vat}`,
          ),
          el("strong", {}, `${t.amount} ${t.currency}`),
          el("small", {}, "Known item costs"),
        ),
      );
    main.append(
      totals,
      notice(
        `${report.note} ${report.missing_costs} line${report.missing_costs === 1 ? "" : "s"} have unknown costs.`,
      ),
    );
    const groups = new Map();
    for (const line of report.lines) {
      if (!groups.has(line.supplier)) groups.set(line.supplier, []);
      groups.get(line.supplier).push(line);
    }
    for (const [supplier, lines] of groups) {
      const rows = lines.map((item) => {
        const review = btn(
          item.warnings.length ? `${item.warnings.length} notes` : "Review",
          () => {
            const body = modal(
              "Procurement line details",
              `${item.name || item.mpn} · ${item.bom}`,
            );
            body.append(
              el(
                "pre",
                { class: "source-fields" },
                JSON.stringify(
                  Object.fromEntries(
                    Object.entries(item).filter(([k]) => k !== "raw"),
                  ),
                  null,
                  2,
                ),
              ),
            );
            body.append(
              el(
                "div",
                { class: "dialog-footer" },
                btn("Close", () => $("#dialog").close()),
                btn(
                  "Review supplier",
                  () => {
                    const b = state.boms.find((b) =>
                      b.components.some((c) => c.id === item.component_id),
                    );
                    state.active = b.id;
                    state.component = item.component_id;
                    if (supplier !== "Unassigned") state.supplier = supplier;
                    $("#dialog").close();
                    navigate("suppliers");
                  },
                  "primary",
                ),
              ),
            );
          },
          "compact",
        );
        const clear =
          supplier === "Unassigned"
            ? null
            : btn(
                "Clear",
                async () => {
                  const b = state.boms.find((b) =>
                    b.components.some((c) => c.id === item.component_id),
                  );
                  try {
                    await api(
                      `/api/boms/${b.id}/components/${item.component_id}/choice`,
                      { method: "DELETE" },
                    );
                    await refresh();
                    render();
                  } catch (e) {
                    fail(e);
                  }
                },
                "text-button",
              );
        return el(
          "tr",
          {},
          el(
            "td",
            {},
            el("div", { class: "component-name" }, item.name || item.mpn),
            el(
              "div",
              { class: "secondary" },
              `${item.bom} · ${item.references || "No refs"}`,
            ),
          ),
          el("td", { class: "mono" }, item.mpn || "—"),
          el("td", { class: "mono" }, item.required ?? "Unknown"),
          el("td", { class: "mono" }, item.order_quantity ?? "Unknown"),
          el(
            "td",
            { class: "mono" },
            item.unit_price === null
              ? "Unknown"
              : `${item.unit_price} ${item.currency}`,
          ),
          el(
            "td",
            { class: "mono" },
            item.known_cost === null
              ? "Unknown"
              : `${item.known_cost} ${item.currency}`,
          ),
          el(
            "td",
            {},
            badge(
              item.match === "exact_mpn" ? "Exact MPN" : "Review match",
              item.match === "exact_mpn" ? "good" : "warn",
            ),
            el(
              "div",
              { class: "secondary" },
              `${item.stock_status.replaceAll("_", " ")} · VAT ${item.vat}`,
            ),
          ),
          el("td", {}, review, clear),
        );
      });
      main.append(
        el(
          "div",
          { class: "section-head" },
          el(
            "h2",
            {},
            supplier === "direnc"
              ? "Direnc.net"
              : supplier === "ozdisan"
                ? "Özdisan"
                : "Unassigned components",
          ),
          badge(`${lines.length} lines`),
        ),
        table(
          [
            "COMPONENT",
            "MPN",
            "REQUIRED",
            "ORDER QTY",
            "UNIT PRICE",
            "KNOWN COST",
            "STATUS",
            "REVIEW",
          ],
          rows,
        ),
        el(
          "div",
          { class: "table-note" },
          "Order quantity respects reported MOQ, order multiples and the chosen price tier.",
        ),
      );
    }
  } catch (error) {
    loading.remove();
    main.append(notice(error.message));
  }
}

function render() {
  state.page =
    location.hash.slice(1) in titles ? location.hash.slice(1) : "dashboard";
  $("#breadcrumb").textContent = titles[state.page];
  document.title = `SONAR · ${titles[state.page]}`;
  document.querySelectorAll("nav a").forEach((link) => {
    const active = link.dataset.page === state.page;
    link.classList.toggle("active", active);
    if (active) link.setAttribute("aria-current", "page");
    else link.removeAttribute("aria-current");
  });
  const main = $("#main");
  main.replaceChildren();
  ({ dashboard, workspace, suppliers, procurement: purchasing })[state.page](
    main,
  );
}
function applyTheme(theme) {
  document.documentElement.dataset.theme = theme;
  $("#theme").textContent =
    theme === "dark" ? "Switch to light theme" : "Switch to dark theme";
}
let preferredTheme;
try {
  preferredTheme = localStorage.getItem("sonar-theme");
} catch {}
applyTheme(
  preferredTheme ||
    (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light"),
);
$("#theme").addEventListener("click", () => {
  const theme =
    document.documentElement.dataset.theme === "dark" ? "light" : "dark";
  applyTheme(theme);
  try {
    localStorage.setItem("sonar-theme", theme);
  } catch {}
});
$("#theme-mobile").addEventListener("click", () => $("#theme").click());
// Mobile theme access: same keyboard shortcut is available at every screen size.
document.addEventListener("keydown", (e) => {
  if (e.altKey && e.key.toLowerCase() === "t") {
    e.preventDefault();
    $("#theme").click();
  }
});
window.addEventListener("hashchange", render);
refresh()
  .then(render)
  .catch((error) => {
    $("#main").replaceChildren(
      empty(
        "Workspace unavailable",
        error.message,
        btn("Retry connection", () => {
          refresh().then(render).catch(fail);
        }),
      ),
    );
  });
