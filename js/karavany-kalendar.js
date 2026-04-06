(function () {
  const calendarRoot = document.getElementById("availability-calendar");
  const lastUpdatedNode = document.getElementById("availability-last-updated");
  const periodLabelNode = document.getElementById("availability-period-label");
  const modeToggleBtn = document.getElementById("availability-mode-toggle");
  const prevBtn = document.getElementById("availability-prev");
  const nextBtn = document.getElementById("availability-next");
  const DATA_URL = "data/karavany-availability.json";
  const SEASON_START_MONTH = 4; // květen
  const SEASON_END_MONTH = 8; // září

  if (!calendarRoot) return;

  const STATUS_MAP = {
    free: { className: "status-free", label: "Volno" },
    reserved: { className: "status-reserved", label: "Obsazeno" },
    tentative: { className: "status-tentative", label: "Předběžně" },
  };
  const STATUS_FILL_MAP = {
    free: "#d8efdc",
    reserved: "#f5d7d7",
    tentative: "#f8e7cd",
  };
  const STATUS_BORDER_MAP = {
    free: "#b1d9b8",
    reserved: "#e3afaf",
    tentative: "#e7c89d",
  };

  const state = {
    mode: "month",
    currentStart: null,
    minDate: null,
    caravans: [],
    lookup: {},
    note: "",
  };

  function toDate(dateText) {
    return new Date(dateText + "T00:00:00");
  }

  function normalizeDate(date) {
    return new Date(date.getFullYear(), date.getMonth(), date.getDate());
  }

  function toIsoDate(date) {
    const normalized = normalizeDate(date);
    const year = normalized.getFullYear();
    const month = String(normalized.getMonth() + 1).padStart(2, "0");
    const day = String(normalized.getDate()).padStart(2, "0");
    return `${year}-${month}-${day}`;
  }

  function addDays(date, amount) {
    const clone = normalizeDate(date);
    clone.setDate(clone.getDate() + amount);
    return clone;
  }

  function startOfMonth(date) {
    return new Date(date.getFullYear(), date.getMonth(), 1);
  }

  function endOfMonth(date) {
    return new Date(date.getFullYear(), date.getMonth() + 1, 0);
  }

  function alignToWeekStart(date) {
    const d = normalizeDate(date);
    const day = d.getDay();
    const offset = day === 0 ? -6 : 1 - day;
    return addDays(d, offset);
  }

  function monthToLabel(date) {
    return date.toLocaleDateString("cs-CZ", {
      month: "long",
      year: "numeric",
    });
  }

  function formatRowDate(date) {
    return date.toLocaleDateString("cs-CZ", {
      day: "2-digit",
      month: "2-digit",
      weekday: "short",
    });
  }

  function ensureDayEntry(lookup, caravan, iso) {
    if (!lookup[caravan]) lookup[caravan] = {};
    if (!lookup[caravan][iso]) {
      lookup[caravan][iso] = { am: "free", pm: "free" };
    }
    return lookup[caravan][iso];
  }

  function createStatusLookup(availability) {
    const lookup = {};

    Object.entries(availability || {}).forEach(([caravan, ranges]) => {
      lookup[caravan] = {};

      (ranges || []).forEach((range) => {
        if (!range.from || !range.to || !STATUS_MAP[range.status]) return;

        const start = toDate(range.from);
        const end = toDate(range.to);
        const status = range.status;

        if (end < start) return;

        if (toIsoDate(start) === toIsoDate(end)) {
          const singleDayEntry = ensureDayEntry(lookup, caravan, toIsoDate(start));
          singleDayEntry.am = status;
          singleDayEntry.pm = status;
          return;
        }

        const startEntry = ensureDayEntry(lookup, caravan, toIsoDate(start));
        startEntry.pm = status;

        const endEntry = ensureDayEntry(lookup, caravan, toIsoDate(end));
        endEntry.am = status;

        let current = addDays(start, 1);
        while (current < end) {
          const currentEntry = ensureDayEntry(lookup, caravan, toIsoDate(current));
          currentEntry.am = status;
          currentEntry.pm = status;
          current = addDays(current, 1);
        }
      });
    });

    return lookup;
  }

  function getRangeFromData(data) {
    const starts = [];
    const ends = [];
    if (data.meta && data.meta.seasonStart) starts.push(toDate(data.meta.seasonStart));
    if (data.meta && data.meta.seasonEnd) ends.push(toDate(data.meta.seasonEnd));
    Object.values(data.availability || {}).forEach((ranges) => {
      (ranges || []).forEach((range) => {
        if (range.from) starts.push(toDate(range.from));
        if (range.to) ends.push(toDate(range.to));
      });
    });
    if (!starts.length || !ends.length) {
      const now = normalizeDate(new Date());
      return { minDate: new Date(now.getFullYear(), SEASON_START_MONTH, 1) };
    }
    const min = starts.reduce((a, b) => (a < b ? a : b));
    const seasonStart = data.meta && data.meta.seasonStart ? toDate(data.meta.seasonStart) : null;
    const firstSeasonDate = seasonStart || min;
    return {
      minDate: new Date(firstSeasonDate.getFullYear(), SEASON_START_MONTH, 1),
    };
  }

  function parseMonthText(monthText) {
    if (!monthText || !/^\d{4}-\d{2}$/.test(monthText)) return null;
    const [year, month] = monthText.split("-").map(Number);
    return new Date(year, month - 1, 1);
  }

  function getInitialStartDate(data, range) {
    const seasonStart = data.meta && data.meta.seasonStart ? toDate(data.meta.seasonStart) : null;
    const firstConfiguredMonth =
      Array.isArray(data.months) && data.months.length ? parseMonthText(data.months[0]) : null;
    const base = seasonStart || firstConfiguredMonth || range.minDate;
    return startOfMonth(base);
  }

  function getMonthMin() {
    return startOfMonth(state.minDate);
  }

  function getWeekMin() {
    return alignToWeekStart(state.minDate);
  }

  function isInSeasonMonth(date) {
    const month = date.getMonth();
    return month >= SEASON_START_MONTH && month <= SEASON_END_MONTH;
  }

  function getSeasonStartForYear(year) {
    return new Date(year, SEASON_START_MONTH, 1);
  }

  function getSeasonEndForYear(year) {
    return endOfMonth(new Date(year, SEASON_END_MONTH, 1));
  }

  function jumpToNextSeasonStart(date) {
    const year = date.getMonth() > SEASON_END_MONTH ? date.getFullYear() + 1 : date.getFullYear();
    return getSeasonStartForYear(year);
  }

  function jumpToPrevSeasonEnd(date) {
    const year = date.getMonth() < SEASON_START_MONTH ? date.getFullYear() - 1 : date.getFullYear();
    return getSeasonEndForYear(year);
  }

  function moveSeasonMonth(date, step) {
    const current = startOfMonth(date);
    const month = current.getMonth();
    const year = current.getFullYear();
    if (step > 0) {
      if (month < SEASON_END_MONTH) return new Date(year, month + 1, 1);
      return new Date(year + 1, SEASON_START_MONTH, 1);
    }
    if (month > SEASON_START_MONTH) return new Date(year, month - 1, 1);
    return new Date(year - 1, SEASON_END_MONTH, 1);
  }

  function clampCurrentStart() {
    if (!state.currentStart) return;
    if (state.mode === "month") {
      const min = getMonthMin();
      if (state.currentStart < min) state.currentStart = new Date(min);
      if (!isInSeasonMonth(state.currentStart)) {
        state.currentStart = state.currentStart.getMonth() < SEASON_START_MONTH
          ? getSeasonStartForYear(state.currentStart.getFullYear())
          : jumpToNextSeasonStart(state.currentStart);
      }
      state.currentStart = startOfMonth(state.currentStart);
      return;
    }
    const min = getWeekMin();
    if (state.currentStart < min) state.currentStart = new Date(min);
    if (!isInSeasonMonth(state.currentStart)) {
      state.currentStart = alignToWeekStart(jumpToNextSeasonStart(state.currentStart));
    }
    state.currentStart = alignToWeekStart(state.currentStart);
  }

  function getVisibleDates() {
    const dates = [];
    if (state.mode === "week") {
      const weekStart = alignToWeekStart(state.currentStart);
      for (let i = 0; i < 7; i += 1) {
        const day = addDays(weekStart, i);
        if (isInSeasonMonth(day)) dates.push(day);
      }
      return dates;
    }
    const start = startOfMonth(state.currentStart);
    const end = endOfMonth(state.currentStart);
    let current = new Date(start);
    while (current <= end) {
      dates.push(new Date(current));
      current = addDays(current, 1);
    }
    return dates;
  }

  function getPeriodLabel(dates) {
    if (!dates.length) return "";
    if (state.mode === "month") {
      return monthToLabel(dates[0]);
    }
    const start = dates[0];
    const end = dates[dates.length - 1];
    return (
      "Týden " +
      start.toLocaleDateString("cs-CZ", { day: "2-digit", month: "2-digit" }) +
      "–" +
      end.toLocaleDateString("cs-CZ", { day: "2-digit", month: "2-digit", year: "numeric" })
    );
  }

  function createHeaderRow(caravans) {
    const tr = document.createElement("tr");
    const dateTh = document.createElement("th");
    dateTh.scope = "col";
    dateTh.textContent = "Datum";
    tr.appendChild(dateTh);
    caravans.forEach((caravan) => {
      const th = document.createElement("th");
      th.scope = "col";
      th.textContent = caravan;
      tr.appendChild(th);
    });
    return tr;
  }

  function getDayParts(lookup, caravan, iso) {
    const entry = (lookup[caravan] && lookup[caravan][iso]) || null;
    return {
      am: entry && entry.am ? entry.am : "free",
      pm: entry && entry.pm ? entry.pm : "free",
    };
  }

  function setAdjacentStatusColors(node, status) {
    node.style.setProperty("--status-adjacent-fill", STATUS_FILL_MAP[status] || STATUS_FILL_MAP.free);
    node.style.setProperty(
      "--status-adjacent-border",
      STATUS_BORDER_MAP[status] || STATUS_BORDER_MAP.free
    );
  }

  function createDayRow(date, caravans, lookup) {
    const tr = document.createElement("tr");
    const iso = toIsoDate(date);
    const readableDate = formatRowDate(date);

    const dateCell = document.createElement("th");
    dateCell.scope = "row";
    dateCell.className = "date-cell";
    dateCell.textContent = readableDate;
    tr.appendChild(dateCell);

    caravans.forEach((caravan) => {
      const parts = getDayParts(lookup, caravan, iso);
      const morningStatus = parts.am;
      const afternoonStatus = parts.pm;

      const morningMeta = STATUS_MAP[morningStatus] || STATUS_MAP.free;
      const afternoonMeta = STATUS_MAP[afternoonStatus] || STATUS_MAP.free;

      const td = document.createElement("td");
      td.className = "status-cell";

      if (morningStatus === afternoonStatus) {
        td.className += " " + morningMeta.className;
        td.setAttribute(
          "aria-label",
          `Karavan ${caravan}, ${readableDate}: ${morningMeta.label}`
        );
      } else if (morningStatus === "free") {
        td.className += " " + afternoonMeta.className + " status-edge-start";
        setAdjacentStatusColors(td, morningStatus);
        td.setAttribute(
          "aria-label",
          `Karavan ${caravan}, ${readableDate}: ráno ${morningMeta.label}, odpoledne ${afternoonMeta.label}`
        );
      } else if (afternoonStatus === "free") {
        td.className += " " + morningMeta.className + " status-edge-end";
        setAdjacentStatusColors(td, afternoonStatus);
        td.setAttribute(
          "aria-label",
          `Karavan ${caravan}, ${readableDate}: ráno ${morningMeta.label}, odpoledne ${afternoonMeta.label}`
        );
      } else {
        td.className += " " + afternoonMeta.className + " status-edge-start";
        setAdjacentStatusColors(td, morningStatus);
        td.setAttribute(
          "aria-label",
          `Karavan ${caravan}, ${readableDate}: ráno ${morningMeta.label}, odpoledne ${afternoonMeta.label}`
        );
      }

      td.innerHTML = '<span class="status-dot" aria-hidden="true"></span>';
      tr.appendChild(td);
    });

    return tr;
  }

  function renderTable(caravans, dates, lookup) {
    const block = document.createElement("section");
    block.className = "availability-month";
    const title = document.createElement("h5");
    title.textContent = getPeriodLabel(dates);
    block.appendChild(title);
    const wrap = document.createElement("div");
    wrap.className = "availability-table-wrap";
    const table = document.createElement("table");
    table.className = "availability-table";
    const caption = document.createElement("caption");
    caption.textContent = "Kalendář dostupnosti karavanů pro " + getPeriodLabel(dates);
    table.appendChild(caption);
    const thead = document.createElement("thead");
    thead.appendChild(createHeaderRow(caravans));
    table.appendChild(thead);
    const tbody = document.createElement("tbody");
    dates.forEach((date) => tbody.appendChild(createDayRow(date, caravans, lookup)));
    table.appendChild(tbody);
    wrap.appendChild(table);
    block.appendChild(wrap);
    return block;
  }

  function updateControls(dates) {
    if (periodLabelNode) periodLabelNode.textContent = getPeriodLabel(dates);
    if (modeToggleBtn) {
      modeToggleBtn.classList.add("is-active");
      modeToggleBtn.setAttribute("aria-pressed", "true");
      modeToggleBtn.textContent =
        state.mode === "month" ? "Zobrazit týden" : "Zobrazit měsíc";
      modeToggleBtn.setAttribute(
        "aria-label",
        state.mode === "month"
          ? "Aktuálně měsíční zobrazení, přepnout na týden"
          : "Aktuálně týdenní zobrazení, přepnout na měsíc"
      );
    }

    if (prevBtn && nextBtn && state.currentStart) {
      if (state.mode === "month") {
        prevBtn.disabled = state.currentStart <= getMonthMin();
        nextBtn.disabled = false;
      } else {
        prevBtn.disabled = state.currentStart <= getWeekMin();
        nextBtn.disabled = false;
      }
    }
  }

  function renderCurrentPeriod() {
    clampCurrentStart();
    const dates = getVisibleDates();
    const noteNode = calendarRoot.querySelector(".availability-note");
    calendarRoot.innerHTML = "";
    if (noteNode) calendarRoot.appendChild(noteNode);
    calendarRoot.appendChild(renderTable(state.caravans, dates, state.lookup));
    updateControls(dates);
  }

  function move(step) {
    if (!state.currentStart) return;
    if (state.mode === "month") {
      state.currentStart = moveSeasonMonth(state.currentStart, step);
      if (state.currentStart < getMonthMin()) state.currentStart = getMonthMin();
      renderCurrentPeriod();
      return;
    }
    let candidate = addDays(state.currentStart, step * 7);
    if (!isInSeasonMonth(candidate)) {
      candidate =
        step > 0
          ? jumpToNextSeasonStart(candidate)
          : alignToWeekStart(jumpToPrevSeasonEnd(candidate));
    }
    state.currentStart = candidate;
    if (state.currentStart < getWeekMin()) state.currentStart = getWeekMin();
    renderCurrentPeriod();
  }

  function renderError() {
    calendarRoot.innerHTML =
      '<p class="availability-fallback">Kalendář dostupnosti se nepodařilo načíst. Pro aktuální stav rezervací nás prosím kontaktujte telefonicky nebo e-mailem.</p>';
  }

  function initCalendar(data) {
    state.caravans = Array.isArray(data.caravans) ? data.caravans : [];
    state.lookup = createStatusLookup(data.availability || {});
    state.note = data.meta && data.meta.note ? data.meta.note : "";
    const range = getRangeFromData(data);
    state.minDate = range.minDate;
    state.currentStart = getInitialStartDate(data, range);

    if (!state.caravans.length) {
      throw new Error("Chybí seznam karavanů.");
    }

    if (state.note) {
      const noteNode = document.createElement("p");
      noteNode.className = "availability-note";
      noteNode.textContent = state.note;
      calendarRoot.innerHTML = "";
      calendarRoot.appendChild(noteNode);
    } else {
      calendarRoot.innerHTML = "";
    }

    if (modeToggleBtn) {
      modeToggleBtn.addEventListener("click", function () {
        state.mode = state.mode === "month" ? "week" : "month";
        state.currentStart =
          state.mode === "month"
            ? startOfMonth(state.currentStart)
            : alignToWeekStart(state.currentStart);
        renderCurrentPeriod();
      });
    }

    if (prevBtn) {
      prevBtn.addEventListener("click", function () {
        move(-1);
      });
    }
    if (nextBtn) {
      nextBtn.addEventListener("click", function () {
        move(1);
      });
    }

    renderCurrentPeriod();
  }

  fetch(DATA_URL, { cache: "no-cache" })
    .then((response) => {
      if (!response.ok) throw new Error("HTTP " + response.status);
      return response.json();
    })
    .then((data) => {
      initCalendar(data);
      if (lastUpdatedNode) {
        lastUpdatedNode.textContent = (data.meta && data.meta.lastUpdated) || "neuvedeno";
      }
    })
    .catch(() => {
      if (lastUpdatedNode) lastUpdatedNode.textContent = "data nejsou dostupná";
      renderError();
    });
})();