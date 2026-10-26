/*
 * SYR Local card: one compact, read-only overview of a SYR water softener.
 *
 * Served and loaded by the SYR Local integration; no separate install needed.
 * Entities are found through the device and their translation keys, so renamed
 * entity IDs keep working.
 *
 *   type: custom:syr-local-card
 *   device: <device id>        # optional, defaults to the first SYR Local device
 *   name: Water softener       # optional
 *   salt_warning_weeks: 3      # optional
 *   show_graph: true           # optional, hourly water use for the last 24 h
 */

const DOMAIN = "syr_local";
const STATS_REFRESH_MS = 10 * 60 * 1000;
const EMPTY_STATES = new Set(["unknown", "unavailable", ""]);

const DEFAULTS = { salt_warning_weeks: 3, show_graph: true };

// Card texts per language; numbers, units and relative times come from Intl and HA.
const STRINGS = {
  en: {
    no_device: "No SYR Local device found. Set up the SYR Local integration first.",
    default_title: "SYR water softener",
    offline: "Offline",
    alarm: "Alarm",
    regenerating: "Regenerating",
    ready: "Ready",
    resin: "Resin",
    soft_water_left: "{value} soft water left",
    salt: "Salt",
    weeks_left: "≈ {value} weeks left",
    flow: "Flow",
    today: "Today",
    last_regeneration: "Last regen",
    pressure: "Pressure",
    regenerations: "{value} regenerations",
    total: "{value} m³ total",
    graph_title: "Water per hour, last 24 h",
    editor_device: "Device (optional, defaults to the first SYR Local device)",
    editor_name: "Name (optional)",
    editor_salt_warning_weeks: "Warn when salt lasts this many weeks or less",
    editor_show_graph: "Show hourly water use (last 24 h)",
    weeks: "weeks",
  },
  de: {
    no_device: "Kein SYR-Local-Gerät gefunden. Richte zuerst die SYR-Local-Integration ein.",
    default_title: "SYR Enthärtungsanlage",
    offline: "Offline",
    alarm: "Alarm",
    regenerating: "Regeneration läuft",
    ready: "Bereit",
    resin: "Harz",
    soft_water_left: "noch {value} Weichwasser",
    salt: "Salz",
    weeks_left: "reicht ≈ {value} Wochen",
    flow: "Durchfluss",
    today: "Heute",
    last_regeneration: "Letzte Regen.",
    pressure: "Druck",
    regenerations: "{value} Regenerationen",
    total: "{value} m³ gesamt",
    graph_title: "Wasser pro Stunde, letzte 24 h",
    editor_device: "Gerät (optional, sonst das erste SYR-Local-Gerät)",
    editor_name: "Name (optional)",
    editor_salt_warning_weeks: "Warnen, wenn das Salz höchstens so viele Wochen reicht",
    editor_show_graph: "Stündlichen Wasserverbrauch anzeigen (letzte 24 h)",
    weeks: "Wochen",
  },
};

function language(hass) {
  return hass?.locale?.language || hass?.language || "en";
}

function localize(hass, key, value) {
  const strings = STRINGS[language(hass).split("-")[0]] || STRINGS.en;
  const text = strings[key] ?? STRINGS.en[key] ?? key;
  return value === undefined ? text : text.replace("{value}", value);
}

function esc(value) {
  return String(value ?? "").replace(
    /[&<>"']/g,
    (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c],
  );
}

/** Map translation keys to entity IDs for one SYR Local device. */
function findEntities(hass, deviceId) {
  const own = Object.values(hass.entities || {}).filter((e) => e.platform === DOMAIN);
  const device = deviceId || own.find((e) => e.device_id)?.device_id;
  const entities = {};
  for (const entry of own) {
    if (entry.device_id === device && entry.translation_key) {
      entities[entry.translation_key] = entry.entity_id;
    }
  }
  return { device, entities };
}

function relativeTime(date, language) {
  const seconds = (date.getTime() - Date.now()) / 1000;
  const units = [
    ["day", 86400],
    ["hour", 3600],
    ["minute", 60],
  ];
  const format = new Intl.RelativeTimeFormat(language, { numeric: "auto" });
  for (const [unit, size] of units) {
    if (Math.abs(seconds) >= size) return format.format(Math.round(seconds / size), unit);
  }
  return format.format(0, "minute");
}

function toMillis(value) {
  return typeof value === "number" ? value : Date.parse(value);
}

class SyrLocalCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this.shadowRoot.addEventListener("click", (ev) => {
      const target = ev.target.closest("[data-entity]");
      if (target?.dataset.entity) this._moreInfo(target.dataset.entity);
    });
    this._stats = null;
    this._statsFor = null;
    this._renderKey = null;
  }

  static getStubConfig() {
    return {};
  }

  static getConfigElement() {
    return document.createElement("syr-local-card-editor");
  }

  setConfig(config) {
    if (!config || typeof config !== "object") throw new Error("Invalid configuration");
    this._config = { ...DEFAULTS, ...config };
    this._renderKey = null;
    this._statsFor = null;
    this._update();
  }

  set hass(hass) {
    this._hass = hass;
    this._update();
  }

  getCardSize() {
    return this._config?.show_graph ? 5 : 4;
  }

  getGridOptions() {
    return { columns: 12, min_columns: 6 };
  }

  connectedCallback() {
    this._timer = setInterval(() => this._loadStats(), STATS_REFRESH_MS);
  }

  disconnectedCallback() {
    clearInterval(this._timer);
  }

  _update() {
    if (!this._hass || !this._config) return;
    const { device, entities } = findEntities(this._hass, this._config.device);
    this._device = device;
    this._entities = entities;

    const total = entities.total_water_l;
    if (total && this._statsFor !== total) {
      this._statsFor = total;
      this._loadStats();
    }

    // Only rebuild the DOM when something visible changed (hass updates often).
    const key = JSON.stringify([
      this._config,
      Object.values(entities).map((id) => this._hass.states[id]?.state),
      this._stats,
      Math.floor(Date.now() / 60000),
      this._hass.themes?.darkMode,
    ]);
    if (key === this._renderKey) return;
    this._renderKey = key;
    this._render();
  }

  /** Today's water use always; the hourly series only when the graph is shown. */
  async _loadStats() {
    const id = this._entities?.total_water_l;
    if (!this._hass || !id) return;
    const start = new Date();
    start.setMinutes(0, 0, 0);
    start.setHours(start.getHours() - 23);
    try {
      const [today, hourly] = await Promise.all([
        this._hass.callWS({
          type: "recorder/statistic_during_period",
          statistic_id: id,
          calendar: { period: "day" },
          types: ["change"],
          units: { volume: "L" },
        }),
        this._config.show_graph
          ? this._hass.callWS({
              type: "recorder/statistics_during_period",
              start_time: start.toISOString(),
              period: "hour",
              statistic_ids: [id],
              types: ["change"],
              units: { volume: "L" },
            })
          : null,
      ]);
      let hours = null;
      if (hourly) {
        const byHour = new Map((hourly[id] || []).map((row) => [toMillis(row.start), row.change]));
        hours = [];
        for (let i = 0; i < 24; i++) {
          const at = start.getTime() + i * 3600 * 1000;
          hours.push({ at, liters: Math.max(0, byHour.get(at) ?? 0) });
        }
      }
      this._stats = { hours, today: today?.change ?? null };
    } catch (_err) {
      // Recorder unavailable or no statistics yet: show "—" and hide the graph quietly.
      this._stats = null;
    }
    this._renderKey = null;
    this._update();
  }

  _state(key) {
    const id = this._entities[key];
    return id ? this._hass.states[id] : undefined;
  }

  _number(key) {
    const value = parseFloat(this._state(key)?.state);
    return Number.isFinite(value) ? value : null;
  }

  _format(key) {
    const stateObj = this._state(key);
    if (!stateObj || EMPTY_STATES.has(stateObj.state)) return "—";
    return this._hass.formatEntityState
      ? this._hass.formatEntityState(stateObj)
      : `${stateObj.state} ${stateObj.attributes.unit_of_measurement ?? ""}`.trim();
  }

  _formatNumber(value, digits = 0) {
    return new Intl.NumberFormat(this._language(), { maximumFractionDigits: digits }).format(value);
  }

  _language() {
    return language(this._hass);
  }

  _t(key, value) {
    return localize(this._hass, key, value);
  }

  _moreInfo(entityId) {
    this.dispatchEvent(
      new CustomEvent("hass-more-info", { detail: { entityId }, bubbles: true, composed: true }),
    );
  }

  _title() {
    if (this._config.name) return this._config.name;
    const device = this._hass.devices?.[this._device];
    return device?.name_by_user || device?.name || this._t("default_title");
  }

  _status() {
    const regen = this._state("regeneration_running");
    const alarm = this._state("alarm");
    if (!regen || regen.state === "unavailable") {
      return { label: this._t("offline"), tone: "off", icon: "mdi:lan-disconnect" };
    }
    if (alarm && !EMPTY_STATES.has(alarm.state)) {
      return { label: this._t("alarm"), tone: "error", icon: "mdi:alert" };
    }
    if (regen.state === "on") {
      return { label: this._t("regenerating"), tone: "info", icon: "mdi:autorenew", spin: true };
    }
    return { label: this._t("ready"), tone: "ok", icon: "mdi:check-circle" };
  }

  _render() {
    if (!this._device || !Object.keys(this._entities).length) {
      this.shadowRoot.innerHTML = `${STYLE}<ha-card><div class="empty">
        ${esc(this._t("no_device"))}</div></ha-card>`;
      return;
    }
    const e = this._entities;
    const status = this._status();
    const regenerating = this._state("regeneration_running")?.state === "on";
    const alarm = this._state("alarm");
    const alarmText = alarm && !EMPTY_STATES.has(alarm.state) ? alarm.state : null;

    const resin = this._number("resin_percent");
    const weeks = this._number("salt_weeks");
    const warn = this._config.salt_warning_weeks;
    const saltTone = weeks === null ? "" : weeks <= 1 ? "error" : weeks <= warn ? "warning" : "";

    const lastRegen = this._state("last_regeneration");
    const lastRegenDate =
      lastRegen && !EMPTY_STATES.has(lastRegen.state) ? new Date(lastRegen.state) : null;
    const lastRegenText =
      lastRegenDate && !isNaN(lastRegenDate) ? relativeTime(lastRegenDate, this._language()) : "—";

    const total = this._number("total_water_l");
    const count = this._number("regeneration_count");
    const today = this._stats?.today;

    const stats = [
      { key: "flow_lph", label: this._t("flow"), value: this._format("flow_lph") },
      {
        key: "total_water_l",
        label: this._t("today"),
        value: today === null || today === undefined ? "—" : `${this._formatNumber(today)} L`,
      },
      { key: "last_regeneration", label: this._t("last_regeneration"), value: lastRegenText },
    ];
    if (this._number("pressure_bar") !== null) {
      stats.push({ key: "pressure_bar", label: this._t("pressure"), value: this._format("pressure_bar") });
    }

    const footer = [];
    if (count !== null) {
      footer.push(
        `<span data-entity="${esc(e.regeneration_count)}">${esc(this._t("regenerations", this._formatNumber(count)))}</span>`,
      );
    }
    if (total !== null) {
      footer.push(
        `<span data-entity="${esc(e.total_water_l)}">${esc(this._t("total", this._formatNumber(total / 1000, 1)))}</span>`,
      );
    }
    const statusText = this._state("status");
    if (statusText && !EMPTY_STATES.has(statusText.state)) {
      footer.push(`<span data-entity="${esc(e.status)}">${esc(statusText.state)}</span>`);
    }

    this.shadowRoot.innerHTML = `${STYLE}
      <ha-card>
        <div class="header">
          <div class="badge"><ha-icon icon="mdi:water-opacity"></ha-icon></div>
          <div class="title">${esc(this._title())}</div>
          <div class="pill ${status.tone}" data-entity="${esc(e.regeneration_running ?? "")}">
            <ha-icon class="${status.spin ? "spin" : ""}" icon="${status.icon}"></ha-icon>
            ${esc(status.label)}
          </div>
        </div>

        ${
          alarmText
            ? `<div class="alarm" data-entity="${esc(e.alarm)}">
                 <ha-icon icon="mdi:alert"></ha-icon>${esc(alarmText)}</div>`
            : ""
        }

        <div class="tiles">
          <div class="tile" data-entity="${esc(e.resin_percent ?? "")}">
            <div class="label"><ha-icon icon="mdi:cylinder"></ha-icon>${esc(this._t("resin"))}</div>
            <div class="value">${esc(this._format("resin_percent"))}</div>
            <div class="bar ${regenerating ? "busy" : ""}">
              <div style="width:${resin === null ? 0 : Math.min(100, Math.max(0, resin))}%"></div>
            </div>
            <div class="sub" data-entity="${esc(e.remaining_capacity_l ?? "")}">
              ${esc(this._t("soft_water_left", this._format("remaining_capacity_l")))}</div>
          </div>
          <div class="tile ${saltTone}" data-entity="${esc(e.salt_kg ?? "")}">
            <div class="label"><ha-icon icon="mdi:shaker-outline"></ha-icon>${esc(this._t("salt"))}</div>
            <div class="value">${esc(this._format("salt_kg"))}</div>
            <div class="sub" data-entity="${esc(e.salt_weeks ?? "")}">
              ${weeks === null ? "—" : esc(this._t("weeks_left", this._formatNumber(weeks)))}</div>
          </div>
        </div>

        <div class="stats">
          ${stats
            .map(
              (s) => `<div class="stat" data-entity="${esc(e[s.key] ?? "")}">
                <div class="label">${esc(s.label)}</div>
                <div class="value">${esc(s.value)}</div></div>`,
            )
            .join("")}
        </div>

        ${this._config.show_graph && this._stats?.hours ? this._graph() : ""}

        ${footer.length ? `<div class="footer">${footer.join("<span class=dot>·</span>")}</div>` : ""}
      </ha-card>`;
  }

  _graph() {
    const hours = this._stats.hours;
    const max = Math.max(...hours.map((h) => h.liters), 1);
    const sum = hours.reduce((acc, h) => acc + h.liters, 0);
    const timeFormat = new Intl.DateTimeFormat(this._language(), { hour: "2-digit", minute: "2-digit" });
    const width = 240;
    const height = 36;
    const slot = width / hours.length;
    const bars = hours
      .map((h, i) => {
        const barHeight = h.liters > 0 ? Math.max(1.5, (h.liters / max) * height) : 0.75;
        return `<rect x="${(i * slot + 1).toFixed(2)}" y="${(height - barHeight).toFixed(2)}"
          width="${(slot - 2).toFixed(2)}" height="${barHeight.toFixed(2)}" rx="1"
          class="${h.liters > 0 ? "" : "zero"}">
          <title>${esc(timeFormat.format(h.at))} · ${esc(this._formatNumber(h.liters))} L</title></rect>`;
      })
      .join("");
    return `<div class="graph" data-entity="${esc(this._entities.total_water_l)}">
        <div class="graph-head"><span>${esc(this._t("graph_title"))}</span>
          <span>${esc(this._formatNumber(sum))} L</span></div>
        <svg viewBox="0 0 ${width} ${height}" preserveAspectRatio="none">${bars}</svg>
      </div>`;
  }
}

const STYLE = `<style>
  :host {
    --syr-accent: var(--info-color, #039be5);
    --syr-ok: var(--success-color, #43a047);
    --syr-warning: var(--warning-color, #ffa600);
    --syr-error: var(--error-color, #db4437);
    --syr-tile-background: rgba(127, 127, 127, 0.08);
  }
  ha-card { padding: 16px; display: flex; flex-direction: column; gap: 12px; }
  [data-entity] { cursor: pointer; }
  ha-icon { --mdc-icon-size: 18px; }
  .empty { color: var(--secondary-text-color); }

  .header { display: flex; align-items: center; gap: 12px; }
  .badge {
    width: 36px; height: 36px; border-radius: 50%; display: grid; place-items: center;
    color: var(--syr-accent); background: color-mix(in srgb, var(--syr-accent) 18%, transparent);
  }
  .badge ha-icon { --mdc-icon-size: 22px; }
  .title { flex: 1; font-size: 16px; font-weight: 500; color: var(--primary-text-color); }
  .pill {
    display: flex; align-items: center; gap: 4px; padding: 4px 10px; border-radius: 999px;
    font-size: 12px; font-weight: 500; --tone: var(--secondary-text-color);
    color: var(--tone); background: color-mix(in srgb, var(--tone) 15%, transparent);
  }
  .pill.ok { --tone: var(--syr-ok); }
  .pill.info { --tone: var(--syr-accent); }
  .pill.error { --tone: var(--syr-error); }
  .pill ha-icon { --mdc-icon-size: 16px; }
  .spin { animation: spin 2s linear infinite; }
  @keyframes spin { to { transform: rotate(360deg); } }

  .alarm {
    display: flex; align-items: center; gap: 8px; padding: 8px 12px; border-radius: 8px;
    color: var(--syr-error); background: color-mix(in srgb, var(--syr-error) 12%, transparent);
    font-weight: 500;
  }

  .tiles { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
  .tile {
    padding: 10px 12px; border-radius: 12px; background: var(--syr-tile-background);
    display: flex; flex-direction: column; gap: 4px; min-width: 0;
  }
  .tile.warning { background: color-mix(in srgb, var(--syr-warning) 16%, transparent); }
  .tile.error { background: color-mix(in srgb, var(--syr-error) 16%, transparent); }
  .tile .value { font-size: 22px; font-weight: 500; color: var(--primary-text-color); }
  .label {
    display: flex; align-items: center; gap: 4px; font-size: 12px;
    color: var(--secondary-text-color);
  }
  .label ha-icon { --mdc-icon-size: 16px; }
  .sub { font-size: 12px; color: var(--secondary-text-color); }
  .bar { height: 6px; border-radius: 3px; background: var(--divider-color); overflow: hidden; }
  .bar > div { height: 100%; border-radius: 3px; background: var(--syr-accent); transition: width .6s; }
  .bar.busy > div {
    background-image: linear-gradient(45deg, rgba(255,255,255,.3) 25%, transparent 25%,
      transparent 50%, rgba(255,255,255,.3) 50%, rgba(255,255,255,.3) 75%, transparent 75%);
    background-size: 12px 12px; animation: stripes 1s linear infinite;
  }
  @keyframes stripes { to { background-position: 12px 0; } }

  .stats { display: flex; justify-content: space-between; gap: 8px; }
  .stat { min-width: 0; }
  .stat .value {
    font-size: 14px; font-weight: 500; color: var(--primary-text-color);
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  }

  .graph-head {
    display: flex; justify-content: space-between; font-size: 12px;
    color: var(--secondary-text-color); margin-bottom: 4px;
  }
  svg { width: 100%; height: 36px; display: block; }
  rect { fill: var(--syr-accent); }
  rect.zero { fill: var(--divider-color); }

  .footer { font-size: 12px; color: var(--secondary-text-color); display: flex; flex-wrap: wrap; gap: 6px; }
</style>`;

class SyrLocalCardEditor extends HTMLElement {
  setConfig(config) {
    this._config = config;
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  _render() {
    if (!this._hass || !this._config) return;
    if (!this._form) {
      this._form = document.createElement("ha-form");
      this._form.schema = [
        { name: "device", selector: { device: { filter: { integration: DOMAIN } } } },
        { name: "name", selector: { text: {} } },
        {
          name: "salt_warning_weeks",
          selector: {
            number: { min: 1, max: 20, mode: "box", unit_of_measurement: localize(this._hass, "weeks") },
          },
        },
        { name: "show_graph", selector: { boolean: {} } },
      ];
      this._form.computeLabel = (schema) => localize(this._hass, `editor_${schema.name}`);
      this._form.addEventListener("value-changed", (ev) => {
        this.dispatchEvent(
          new CustomEvent("config-changed", {
            detail: { config: ev.detail.value },
            bubbles: true,
            composed: true,
          }),
        );
      });
      this.appendChild(this._form);
    }
    this._form.hass = this._hass;
    this._form.data = { ...DEFAULTS, ...this._config };
  }
}


if (!customElements.get("syr-local-card")) {
  customElements.define("syr-local-card", SyrLocalCard);
  customElements.define("syr-local-card-editor", SyrLocalCardEditor);
  window.customCards = window.customCards || [];
  window.customCards.push({
    type: "syr-local-card",
    name: "SYR Local",
    description: "Compact read-only overview of a SYR water softener.",
    preview: true,
    documentationURL: "https://github.com/valentinpurrucker/syr-local",
  });
}
