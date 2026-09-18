/* Read-only financial workspace. Monetary source values remain decimal strings. */
"use strict";

(() => {
  const $ = (id) => document.getElementById(id);
  const demo = window.CREDITLAKE_DEMO;
  const names = {
    TXN: "Texas Instruments",
    T: "AT&T",
    LUV: "Southwest Airlines",
    CBRE: "CBRE Group",
    CPRT: "Copart",
    DHI: "D.R. Horton",
    WING: "Wingstop",
    EAT: "Brinker International",
  };
  const metrics = {
    revenue: "Revenue",
    net_income: "Net income",
    operating_income: "Operating income",
    operating_cash_flow: "Operating cash flow",
    assets: "Total assets",
    liabilities: "Total liabilities",
    equity: "Stockholders’ equity",
    current_assets: "Current assets",
    current_liabilities: "Current liabilities",
    cash: "Cash and equivalents",
  };
  const views = {
    overview: [
      "Overview",
      "Company financials",
      "Annual statements and the evidence behind them.",
    ],
    sources: [
      "Source evidence",
      "Source evidence",
      "Reported values, filing documents, and original source records.",
    ],
    changes: [
      "Filing changes",
      "Filing changes",
      "Trace how reported values changed across annual filings.",
    ],
    quality: [
      "Data quality",
      "Data quality",
      "Coverage and review findings for the published dataset.",
    ],
  };
  const state = {
    companies: [],
    history: [],
    facts: [],
    revisions: [],
    status: null,
    quality: null,
    ticker: "TXN",
    cutoff: "",
    period: "",
    view: "overview",
    request: 0,
    sourceRequest: 0,
    ready: false,
  };
  const fmtDate = (value) =>
    value
      ? new Intl.DateTimeFormat("en-GB", {
          day: "2-digit",
          month: "short",
          year: "numeric",
          timeZone: "UTC",
        }).format(new Date(value.slice(0, 10) + "T00:00:00Z"))
      : "—";
  const numeric = (value) =>
    value === null || value === undefined || value === ""
      ? null
      : Number(value);
  const percent = (value, signed = false) =>
    numeric(value) === null
      ? "—"
      : (signed && Number(value) > 0 ? "+" : "") +
        (Number(value) * 100).toFixed(1) +
        "%";
  const compact = (value) => {
    const n = numeric(value);
    if (n === null) return "—";
    const absolute = Math.abs(n),
      unit =
        absolute >= 1e12
          ? [1e12, "T"]
          : absolute >= 1e9
            ? [1e9, "B"]
            : absolute >= 1e6
              ? [1e6, "M"]
              : absolute >= 1e3
                ? [1e3, "K"]
                : [1, ""];
    return (
      (n < 0 ? "−" : "") +
      "$" +
      (absolute / unit[0]).toLocaleString("en-US", {
        maximumFractionDigits: 2,
        minimumFractionDigits: unit[1] ? 2 : 0,
      }) +
      unit[1]
    );
  };
  const exactUSD = (value) => {
    if (value === null || value === undefined) return "—";
    const match = String(value).match(/^(-?)(\d+)(?:\.(\d+))?$/);
    if (!match) return String(value);
    const fraction = (match[3] || "").replace(/0+$/, "");
    return (
      (match[1] ? "−" : "") +
      "$" +
      BigInt(match[2]).toLocaleString("en-US") +
      (fraction ? "." + fraction : "")
    );
  };
  const billions = (value) =>
    numeric(value) === null
      ? "—"
      : (Number(value) / 1e9).toLocaleString("en-US", {
          minimumFractionDigits: 2,
          maximumFractionDigits: 2,
        });
  const text = (id, value) => {
    $(id).textContent = value;
  };
  const element = (tag, className, value) => {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (value !== undefined) node.textContent = value;
    return node;
  };
  const cell = (row, value, className = "") => {
    const node = element("td", className);
    if (value instanceof Node) node.append(value);
    else node.textContent = value;
    row.append(node);
    return node;
  };
  const empty = (body, columns, message) => {
    const row = element("tr"),
      td = cell(row, message, "empty-cell");
    td.colSpan = columns;
    body.append(row);
  };
  const link = (label, url) => {
    const node = element("a", "document-link", label);
    node.href = url;
    node.target = "_blank";
    node.rel = "noopener noreferrer";
    return node;
  };
  const requestJSON = async (path) => {
    const response = await fetch(path, {
      headers: { Accept: "application/json" },
      cache: "no-store",
    });
    if (!response.ok)
      throw new Error(
        "The published dataset could not be loaded. Check the service and retry.",
      );
    return response.json();
  };
  const announce = (value) => text("announcement", value);

  function canonical(ticker, cutoff) {
    const ordered = (demo.candidates[ticker] || [])
      .filter((f) => f.filed <= cutoff)
      .slice()
      .sort(
        (a, b) =>
          b.filed.localeCompare(a.filed) ||
          a.alias_priority - b.alias_priority ||
          b.accession.localeCompare(a.accession) ||
          b.first_observed.localeCompare(a.first_observed) ||
          a.fact_id.localeCompare(b.fact_id),
      );
    const chosen = new Map();
    ordered.forEach((f) => {
      const key = f.metric + "|" + f.period_end;
      if (!chosen.has(key)) chosen.set(key, f);
    });
    return [...chosen.values()].sort(
      (a, b) =>
        a.period_end.localeCompare(b.period_end) ||
        a.metric.localeCompare(b.metric),
    );
  }
  function offlineHistory(facts, issuer) {
    const grouped = new Map();
    facts.forEach((f) => {
      if (!grouped.has(f.period_end))
        grouped.set(f.period_end, {
          cik: issuer.cik,
          period_end: f.period_end,
          available_metrics: 0,
          latest_evidence_filed: f.filed,
          ...Object.fromEntries(Object.keys(metrics).map((key) => [key, null])),
        });
      const row = grouped.get(f.period_end);
      row[f.metric] = f.value;
      row.available_metrics++;
      if (f.filed > row.latest_evidence_filed)
        row.latest_evidence_filed = f.filed;
    });
    const history = [...grouped.values()]
      .filter((r) => r.revenue !== null)
      .sort((a, b) => a.period_end.localeCompare(b.period_end));
    const ratio = (a, b) =>
      numeric(a) !== null && numeric(b) !== null && Number(b) !== 0
        ? Number(a) / Number(b)
        : null;
    history.forEach((r, index) => {
      const previous = history[index - 1],
        days = previous
          ? (new Date(r.period_end) - new Date(previous.period_end)) / 86400000
          : null;
      r.net_margin = ratio(r.net_income, r.revenue);
      r.current_ratio = ratio(r.current_assets, r.current_liabilities);
      r.liabilities_to_assets = ratio(r.liabilities, r.assets);
      r.revenue_growth_yoy =
        previous && days >= 330 && days <= 400 && Number(previous.revenue) !== 0
          ? Number(r.revenue) / Number(previous.revenue) - 1
          : null;
    });
    return history;
  }

  function renderView() {
    const key = location.hash.slice(1);
    state.view = Object.hasOwn(views, key) ? key : "overview";
    Object.keys(views).forEach((id) => {
      $(id).hidden = id !== state.view;
    });
    document.querySelectorAll("[data-view]").forEach((node) => {
      if (node.dataset.view === state.view)
        node.setAttribute("aria-current", "page");
      else node.removeAttribute("aria-current");
    });
    const [breadcrumb, title, description] = views[state.view];
    text("breadcrumb-current", breadcrumb);
    text("page-title", title);
    text("page-description", description);
    const isQuality = state.view === "quality";
    $("filters").hidden = isQuality;
    $("company-heading").hidden = isQuality;
    $("export-button").hidden = isQuality;
    text(
      "view-cutoff",
      isQuality
        ? "Published cutoff · " + fmtDate(state.status?.filing_date_cutoff)
        : "Filing cutoff · " + fmtDate(state.cutoff),
    );
    if (state.view === "overview") requestAnimationFrame(renderChart);
    document.title = views[state.view][0] + " · CreditLake";
  }
  function setBusy(busy) {
    $("content").setAttribute("aria-busy", String(busy));
    $("apply-button").disabled = busy;
    $("company").disabled = busy;
    $("export-button").disabled = busy || !state.ready || !state.history.length;
    $("period").disabled = busy || !state.history.length;
  }
  async function refresh(desiredPeriod = "") {
    const request = ++state.request;
    state.ready = false;
    setBusy(true);
    $("error").hidden = true;
    const ticker = $("company").value,
      cutoff = $("cutoff").value;
    try {
      let status, issuer, history, facts, revisions, quality;
      if (demo) {
        status = demo.status;
        issuer = state.companies.find((c) => c.ticker === ticker);
        facts = canonical(ticker, cutoff);
        history = offlineHistory(facts, issuer);
        revisions = (demo.revisions[ticker] || []).filter(
          (r) => r.filed <= cutoff,
        );
        quality = demo.quality;
      } else {
        const [release, h, f, r, q] = await Promise.all([
          requestJSON("/api/status"),
          requestJSON(
            `/api/companies/${encodeURIComponent(ticker)}/history?as_of=${cutoff}`,
          ),
          requestJSON(
            `/api/companies/${encodeURIComponent(ticker)}/facts?as_of=${cutoff}`,
          ),
          requestJSON(
            `/api/companies/${encodeURIComponent(ticker)}/revisions?as_of=${cutoff}`,
          ),
          requestJSON("/api/quality"),
        ]);
        if ([h, f, r, q].some((data) => data.run_id !== release.run_id))
          throw new Error(
            "The release changed while loading. Retry to load a consistent dataset.",
          );
        status = release;
        issuer = h.issuer;
        history = h.history;
        facts = f.facts;
        revisions = r.revisions;
        quality = q;
      }
      if (request !== state.request) return;
      Object.assign(state, {
        status,
        ticker,
        cutoff,
        history,
        facts,
        revisions,
        quality,
        ready: true,
      });
      text("ticker", ticker);
      text("company-name", names[ticker] || issuer.name);
      text(
        "company-meta",
        [issuer.sector, issuer.headquarters].filter(Boolean).join(" · "),
      );
      text("publication-date", "Published " + fmtDate(status.published_at));
      $("period").replaceChildren();
      history
        .slice()
        .reverse()
        .forEach((row) => {
          const option = element("option", "", fmtDate(row.period_end));
          option.value = row.period_end;
          $("period").append(option);
        });
      state.period = history.some((r) => r.period_end === desiredPeriod)
        ? desiredPeriod
        : history.at(-1)?.period_end || "";
      $("period").value = state.period;
      renderStatements();
      renderPeriod();
      renderRevisions();
      renderQuality();
      renderView();
      announce(
        `${names[ticker] || ticker}: ${history.length} annual periods through ${fmtDate(cutoff)}.`,
      );
    } catch (error) {
      if (request !== state.request) return;
      state.history = [];
      state.facts = [];
      state.revisions = [];
      state.period = "";
      $("period").replaceChildren();
      text("ticker", ticker);
      text("company-name", names[ticker] || ticker);
      text("company-meta", "Data unavailable");
      renderStatements();
      renderPeriod();
      renderRevisions();
      text("error-message", error.message);
      $("error").hidden = false;
    } finally {
      if (request === state.request) setBusy(false);
    }
  }
  function selectPeriod(period) {
    state.period = period;
    $("period").value = period;
    renderStatements();
    renderPeriod();
    announce("Selected fiscal period ending " + fmtDate(period) + ".");
  }
  function renderPeriod() {
    const row = state.history.find((r) => r.period_end === state.period);
    text("revenue", compact(row?.revenue));
    text("assets", compact(row?.assets));
    text("margin", percent(row?.net_margin));
    text(
      "liquidity",
      numeric(row?.current_ratio) === null
        ? "—"
        : Number(row.current_ratio).toFixed(2) + "×",
    );
    text(
      "growth",
      numeric(row?.revenue_growth_yoy) === null
        ? "YoY unavailable"
        : percent(row.revenue_growth_yoy, true) + " year over year",
    );
    $("growth").className =
      "metric-detail" +
      (numeric(row?.revenue_growth_yoy) === null
        ? ""
        : Number(row.revenue_growth_yoy) >= 0
          ? " positive"
          : " negative");
    text(
      "leverage",
      numeric(row?.liabilities_to_assets) === null
        ? "Liabilities / assets unavailable"
        : percent(row.liabilities_to_assets) + " liabilities / assets",
    );
    text(
      "period-label",
      row
        ? "Period ending " + fmtDate(row.period_end)
        : "No annual period available",
    );
    text("coverage-count", row ? row.available_metrics : "—");
    const complete = row?.available_metrics === 10;
    text(
      "coverage-status",
      row ? (complete ? "Complete" : "Partial") : "No data",
    );
    $("coverage-status").className =
      "badge" + (row ? (complete ? " badge-positive" : " badge-warning") : "");
    const missing = row
      ? Object.keys(metrics).filter((key) => numeric(row[key]) === null)
      : [];
    text(
      "coverage-note",
      !row
        ? "Select a later filing cutoff to view annual financials."
        : missing.length
          ? "Missing: " +
            missing.map((key) => metrics[key].toLowerCase()).join(", ") +
            "."
          : "All ten financial metrics are available for this period.",
    );
    $("coverage-track").replaceChildren(
      ...Object.keys(metrics).map((key) =>
        element("i", row && numeric(row[key]) !== null ? "available" : ""),
      ),
    );
    renderEvidence();
    renderChart();
  }
  function renderStatements() {
    const body = $("annual-statements").querySelector("tbody");
    body.replaceChildren();
    text("statement-count", state.history.length + " periods");
    state.history
      .slice()
      .reverse()
      .forEach((record) => {
        const row = element(
          "tr",
          record.period_end === state.period ? "selected" : "",
        );
        const button = element(
          "button",
          "period-button",
          fmtDate(record.period_end),
        );
        button.type = "button";
        button.setAttribute(
          "aria-label",
          "Select period " + fmtDate(record.period_end),
        );
        button.addEventListener("click", () => selectPeriod(record.period_end));
        cell(row, button);
        cell(row, billions(record.revenue), "number");
        const growth = cell(
          row,
          percent(record.revenue_growth_yoy, true),
          "number",
        );
        if (numeric(record.revenue_growth_yoy) !== null)
          growth.classList.add(
            Number(record.revenue_growth_yoy) >= 0 ? "positive" : "negative",
          );
        cell(row, billions(record.net_income), "number");
        cell(row, percent(record.net_margin), "number");
        cell(row, billions(record.assets), "number");
        cell(row, record.available_metrics + " / 10", "number");
        body.append(row);
      });
    if (!state.history.length)
      empty(
        body,
        7,
        "No annual statements are available for this filing cutoff.",
      );
  }
  function renderEvidence() {
    const body = $("evidence");
    body.replaceChildren();
    const facts = state.facts.filter((f) => f.period_end === state.period);
    text("evidence-count", facts.length + " facts");
    facts
      .sort(
        (a, b) =>
          Object.keys(metrics).indexOf(a.metric) -
          Object.keys(metrics).indexOf(b.metric),
      )
      .forEach((fact) => {
        const row = element("tr");
        cell(row, metrics[fact.metric] || fact.metric, "metric-name");
        cell(row, exactUSD(fact.value), "number");
        cell(row, fmtDate(fact.filed));
        cell(row, link(fact.form + " ↗", fact.filing_url));
        const button = element("button", "text-button", "View source");
        button.type = "button";
        button.setAttribute(
          "aria-label",
          "View source for " + (metrics[fact.metric] || fact.metric),
        );
        button.addEventListener("click", () => openSource(fact));
        cell(row, button);
        body.append(row);
      });
    if (!facts.length)
      empty(body, 5, "No source facts are available for the selected period.");
  }
  function renderRevisions() {
    const body = $("revisions");
    body.replaceChildren();
    text("revision-count", state.revisions.length + " changes");
    state.revisions.forEach((fact) => {
      const row = element("tr");
      cell(row, fmtDate(fact.period_end));
      cell(row, metrics[fact.metric] || fact.metric, "metric-name");
      cell(row, exactUSD(fact.previous_value), "number");
      cell(row, exactUSD(fact.value), "number");
      const issuer = state.companies.find((c) => c.ticker === state.ticker);
      cell(
        row,
        link(
          fmtDate(fact.filed) + " ↗",
          `https://www.sec.gov/Archives/edgar/data/${issuer.cik}/${fact.accession.replaceAll("-", "")}/${fact.accession}-index.html`,
        ),
      );
      body.append(row);
    });
    if (!state.revisions.length)
      empty(
        body,
        5,
        "No changed annual values are available for this filing cutoff.",
      );
  }
  function renderQuality() {
    const quality = state.quality;
    if (!quality) return;
    const summary = quality.summary;
    text(
      "quality-release",
      "Published dataset · filing cutoff " +
        fmtDate(state.status.filing_date_cutoff),
    );
    text("checks", state.status.dbt.tests_passed + " checks passed");
    text("periods-count", summary.annual_periods);
    text("issuers-count", summary.issuers + " companies");
    text("complete-count", summary.complete_periods);
    text("incomplete-count", summary.incomplete_periods);
    text("balance-count", summary.balance_warnings);
    text(
      "facts-count",
      state.status.total_facts.toLocaleString("en-US") + " fact versions",
    );
    const issuers = $("quality-issuers");
    issuers.replaceChildren();
    quality.by_issuer.forEach((issuer) => {
      const row = element("tr"),
        company = element("div", "company-cell");
      company.append(
        element("strong", "", issuer.ticker),
        element("span", "", names[issuer.ticker] || issuer.ticker),
      );
      cell(row, company);
      cell(row, issuer.annual_periods, "number");
      cell(row, issuer.complete_periods, "number");
      const ratio = issuer.annual_periods
        ? issuer.complete_periods / issuer.annual_periods
        : 0;
      const coverage = element("div", "quality-coverage"),
        bar = element("span", "bar"),
        fill = element("i");
      fill.style.width = ratio * 100 + "%";
      bar.append(fill);
      coverage.append(
        bar,
        element("span", "percent", Math.round(ratio * 100) + "%"),
      );
      cell(row, coverage);
      cell(
        row,
        Object.values(issuer.missing_by_metric).reduce((a, b) => a + b, 0),
        "number",
      );
      issuers.append(row);
    });
    const balances = $("quality-balances");
    balances.replaceChildren();
    quality.balance_warnings.forEach((record) => {
      const row = element("tr");
      cell(row, record.ticker, "metric-name");
      cell(row, fmtDate(record.period_end));
      cell(row, exactUSD(record.residual), "number");
      cell(row, exactUSD(record.tolerance), "number");
      const button = element("button", "text-button", "View period");
      button.type = "button";
      button.setAttribute(
        "aria-label",
        `View ${record.ticker} period ${fmtDate(record.period_end)}`,
      );
      button.addEventListener("click", () => {
        $("company").value = record.ticker;
        $("cutoff").value = state.status.filing_date_cutoff;
        location.hash = "sources";
        refresh(record.period_end);
      });
      cell(row, button);
      balances.append(row);
    });
    if (!quality.balance_warnings.length)
      empty(balances, 5, "No balance equation findings in this release.");
    text(
      "missing-count",
      quality.incomplete_periods.length + " incomplete periods",
    );
    const missing = $("quality-missing");
    missing.replaceChildren();
    quality.incomplete_periods.forEach((record) => {
      const row = element("tr");
      cell(row, record.ticker, "metric-name");
      cell(row, fmtDate(record.period_end));
      cell(
        row,
        record.missing_metrics.map((key) => metrics[key] || key).join(", "),
        "missing-metrics",
      );
      missing.append(row);
    });
    if (!quality.incomplete_periods.length)
      empty(missing, 3, "All annual periods satisfy the ten-metric contract.");
  }

  function renderChart() {
    if (state.view !== "overview") return;
    const svg = $("chart"),
      metric = $("chart-metric").value;
    text("chart-series", metrics[metric]);
    $("chart-series").prepend(element("i", "legend-line"));
    svg.replaceChildren();
    const values = state.history.filter((r) => numeric(r[metric]) !== null);
    $("chart-empty").hidden = values.length > 0;
    svg.setAttribute(
      "aria-label",
      `${metrics[metric]} in USD billions across ${values.length} annual periods for ${names[state.ticker] || state.ticker}`,
    );
    if (!values.length) return;
    const width = svg.clientWidth,
      height = svg.clientHeight;
    if (!width || !height) return;
    svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
    const ns = "http://www.w3.org/2000/svg",
      add = (tag, attributes, label) => {
        const node = document.createElementNS(ns, tag);
        Object.entries(attributes).forEach(([k, v]) =>
          node.setAttribute(k, String(v)),
        );
        if (label !== undefined) node.textContent = label;
        svg.append(node);
        return node;
      };
    const left = 43,
      right = 17,
      top = 14,
      bottom = 30,
      plotWidth = width - left - right,
      plotHeight = height - top - bottom;
    const minimum = Math.min(0, ...values.map((r) => Number(r[metric]) / 1e9)),
      maximum = Math.max(0, ...values.map((r) => Number(r[metric]) / 1e9));
    const stepPower = Math.pow(
        10,
        Math.floor(Math.log10((maximum - minimum || 1) / 4)),
      ),
      rough = (maximum - minimum || 1) / 4 / stepPower,
      step =
        (rough <= 1
          ? 1
          : rough <= 2
            ? 2
            : rough <= 2.5
              ? 2.5
              : rough <= 5
                ? 5
                : 10) * stepPower;
    const low = Math.floor(minimum / step) * step,
      high = Math.ceil(maximum / step) * step || step;
    const timestamps = state.history.map((r) => Date.parse(r.period_end)),
      earliest = Math.min(...timestamps),
      latest = Math.max(...timestamps);
    const x = (row) =>
        left +
        (latest === earliest
          ? plotWidth / 2
          : ((Date.parse(row.period_end) - earliest) / (latest - earliest)) *
            plotWidth),
      y = (n) => top + ((high - n) / (high - low)) * plotHeight;
    for (let value = low; value <= high + step / 100; value += step) {
      add("line", {
        x1: left,
        y1: y(value),
        x2: width - right,
        y2: y(value),
        class: "grid-line",
      });
      add(
        "text",
        { x: left - 10, y: y(value) + 3, "text-anchor": "end" },
        Number(value.toFixed(3)).toLocaleString("en-US", {
          maximumFractionDigits: 2,
        }),
      );
    }
    const stride = Math.max(
        1,
        Math.ceil(state.history.length / (width < 400 ? 4 : 6)),
      ),
      labelRows = state.history.filter((_, i) => i % stride === 0);
    const last = state.history.at(-1);
    if (labelRows.at(-1) !== last) {
      if (labelRows.length > 1 && x(last) - x(labelRows.at(-1)) < 40)
        labelRows.pop();
      labelRows.push(last);
    }
    labelRows.forEach((row) =>
      add(
        "text",
        { x: x(row), y: height - 7, "text-anchor": "middle" },
        row.period_end.slice(0, 4),
      ),
    );
    const segments = [];
    let current = [];
    state.history.forEach((row) => {
      if (numeric(row[metric]) === null) {
        if (current.length) segments.push(current);
        current = [];
      } else current.push(row);
    });
    if (current.length) segments.push(current);
    const zero = y(0);
    segments.forEach((segment) => {
      const points = segment
        .map((row) => `${x(row)},${y(Number(row[metric]) / 1e9)}`)
        .join(" ");
      if (segment.length > 1) {
        add("polygon", {
          points: `${x(segment[0])},${zero} ${points} ${x(segment.at(-1))},${zero}`,
          class: "series-area",
        });
        add("polyline", { points, class: "series-line" });
      }
    });
    const selected = values.find((row) => row.period_end === state.period);
    if (selected)
      add("line", {
        x1: x(selected),
        y1: top,
        x2: x(selected),
        y2: height - bottom,
        class: "selection-line",
      });
    values.forEach((row) => {
      const selected = row.period_end === state.period,
        circle = add("circle", {
          cx: x(row),
          cy: y(Number(row[metric]) / 1e9),
          r: selected ? 4.5 : 3.1,
          class: selected ? "chart-point selected-point" : "chart-point",
          tabindex: "0",
          role: "button",
          "aria-label": `Select ${fmtDate(row.period_end)}: ${metrics[metric]} ${exactUSD(row[metric])}`,
        });
      const title = document.createElementNS(ns, "title");
      title.textContent =
        fmtDate(row.period_end) + " · " + exactUSD(row[metric]);
      circle.append(title);
      circle.addEventListener("click", () => selectPeriod(row.period_end));
      circle.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          selectPeriod(row.period_end);
        }
      });
    });
  }
  async function openSource(fact) {
    const request = ++state.sourceRequest;
    const dialog = $("source-dialog");
    text("source-title", metrics[fact.metric] || fact.metric);
    text(
      "source-period",
      state.ticker + " · period ending " + fmtDate(fact.period_end),
    );
    text("source-value", exactUSD(fact.value));
    $("source-fields").replaceChildren();
    $("source-links").replaceChildren();
    text(
      "source-integrity",
      demo
        ? "This preview contains captured financial facts and source checksums. Archive and full lineage downloads are available from the running service."
        : "Loading source provenance…",
    );
    const field = (label, value, mono = false) => {
      if (value === undefined || value === null) return;
      const row = element("div");
      row.append(
        element("dt", "", label),
        element("dd", mono ? "monospace" : "", String(value)),
      );
      $("source-fields").append(row);
    };
    field("Filed", fmtDate(fact.filed));
    field("Form", fact.form);
    field("Accession", fact.accession, true);
    field("Taxonomy concept", fact.concept, true);
    field("First observed", fact.first_observed);
    field("Fact ID", fact.fact_id, true);
    field("Original response SHA-256", fact.source_sha, true);
    $("source-links").append(link("Open SEC filing ↗", fact.filing_url));
    dialog.showModal();
    if (demo) return;
    try {
      const lineage = await requestJSON(
        `/api/facts/${encodeURIComponent(fact.fact_id)}/lineage`,
      );
      if (request !== state.sourceRequest || !dialog.open) return;
      if (lineage.run_id !== state.status.run_id)
        throw new Error(
          "The release changed. Close this record and apply the filters again to refresh.",
        );
      field("Bronze archive", lineage.storage.bronze, true);
      field("Silver partition", lineage.storage.silver, true);
      field("Warehouse relation", lineage.storage.raw_relation, true);
      field("Annual model path", lineage.annual_model_path.join(" → "));
      $("source-links").append(
        link(
          "Download original source (.json.gz)",
          lineage.source.archive_download,
        ),
        link(
          "Open provenance JSON ↗",
          `/api/facts/${encodeURIComponent(fact.fact_id)}/lineage`,
        ),
      );
      text(
        "source-integrity",
        lineage.source.integrity_check + " " + lineage.selection_note,
      );
    } catch (error) {
      if (request === state.sourceRequest && dialog.open)
        text("source-integrity", error.message);
    }
  }
  function exportCSV() {
    if (!state.ready || !state.history.length) return;
    const columns = [
      "ticker",
      "as_of",
      "period_end",
      ...Object.keys(metrics),
      "net_margin",
      "current_ratio",
      "liabilities_to_assets",
      "revenue_growth_yoy",
      "available_metrics",
      "latest_evidence_filed",
    ];
    const quote = (value) =>
      value === null || value === undefined
        ? ""
        : '"' + String(value).replaceAll('"', '""') + '"';
    const content =
      [
        columns.join(","),
        ...state.history.map((row) =>
          columns
            .map((key) =>
              quote(
                key === "ticker"
                  ? state.ticker
                  : key === "as_of"
                    ? state.cutoff
                    : row[key],
              ),
            )
            .join(","),
        ),
      ].join("\r\n") + "\r\n";
    const url = URL.createObjectURL(
        new Blob([content], { type: "text/csv;charset=utf-8" }),
      ),
      anchor = element("a");
    anchor.href = url;
    anchor.download = `creditlake-${state.ticker}-as-of-${state.cutoff}.csv`;
    document.body.append(anchor);
    anchor.click();
    anchor.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    announce(
      "Exported " +
        state.history.length +
        " annual periods for " +
        state.ticker +
        ".",
    );
  }
  async function initialize() {
    renderView();
    try {
      const [status, companies] = demo
        ? [demo.status, demo.companies]
        : await Promise.all([
            requestJSON("/api/status"),
            requestJSON("/api/companies"),
          ]);
      state.status = status;
      state.companies = companies;
      $("company").replaceChildren();
      companies.forEach((company) => {
        const option = element(
          "option",
          "",
          company.ticker + " · " + (names[company.ticker] || company.name),
        );
        option.value = company.ticker;
        $("company").append(option);
      });
      $("company").value = companies.some((c) => c.ticker === "TXN")
        ? "TXN"
        : companies[0]?.ticker || "";
      $("cutoff").value = status.filing_date_cutoff;
      await refresh();
    } catch (error) {
      text("error-message", error.message);
      $("error").hidden = false;
      setBusy(false);
    }
  }
  $("filters").addEventListener("submit", (event) => {
    event.preventDefault();
    refresh();
  });
  $("period").addEventListener("change", (event) =>
    selectPeriod(event.target.value),
  );
  $("chart-metric").addEventListener("change", renderChart);
  $("export-button").addEventListener("click", exportCSV);
  $("retry-button").addEventListener("click", () =>
    state.companies.length ? refresh() : initialize(),
  );
  $("close-source").addEventListener("click", () => $("source-dialog").close());
  $("source-dialog").addEventListener("close", () => state.sourceRequest++);
  window.addEventListener("hashchange", renderView);
  new ResizeObserver(() => renderChart()).observe($("chart"));
  initialize();
})();
