/*
 * Safir Holding 2027 — live data bridge.
 *
 * This file binds the executive dashboard to the real FastAPI backend. It is
 * no longer a standalone mockup: every figure on screen is loaded from the API
 * and PostgreSQL for the signed-in user, and the page is gated behind the
 * backend's existing JWT authentication (see auth.js).
 *
 * The reporting period defaults to the most recent month that actually has
 * data (derived from the reports the caller may see), falling back to the
 * current month. It can still be pinned with ?year=2027&month=10.
 *
 * No credential or token is ever hardcoded here or read from the URL.
 */
(function () {
  "use strict";

  var body = document.body;
  var params = new URLSearchParams(location.search);
  var api = window.SafirApi;
  var YEAR = params.get("year");
  var MONTH = params.get("month");

  // ---- state -----------------------------------------------------------
  var STATE = {
    year: null,
    month: null,
    view: "dashboard",
    lang: "ar",
    companies: [],
    sectors: [],
    reports: [],
    support: [],
    insights: [],
    users: [],
    forms: [],
    dashboard: null,
    reqForm: "",
    reqStatus: "",
    docCategory: "",
    docExpiry: "",
    notifications: [],
    notificationsUnread: 0,
    notifFilter: "all",
    anTab: "briefing",
    integrationSecret: null,
    empTab: "employees",
    opsTab: "tasks",
    acctTab: "balances",
    acctLedgerCompany: null,
    acctLedgerType: "",
    acctLedgerYear: null,
    acctLedgerMonth: null,
    confTab: "complaints",
    loaded: {},
  };

  var period = "";
  if (YEAR && MONTH) {
    period = "?year=" + YEAR + "&month=" + MONTH;
    STATE.year = parseInt(YEAR, 10);
    STATE.month = parseInt(MONTH, 10);
  }

  // The backend defaults an unspecified period to the current calendar month,
  // which for a freshly seeded environment holds no data. Unless the caller
  // pinned ?year&month, derive the most recent period that actually has data
  // from the reports this user may see, so the dashboard opens on real figures.
  function resolvePeriod() {
    if (YEAR && MONTH) return Promise.resolve();
    if (!has("monthly_report.read_own") && !has("monthly_report.read_all")) {
      return Promise.resolve();
    }
    return get("/api/v1/monthly-reports")
      .then(function (rows) {
        var best = null;
        (rows || []).forEach(function (r) {
          var key = r.period_year * 12 + r.period_month;
          if (!best || key > best.key) {
            best = { key: key, year: r.period_year, month: r.period_month };
          }
        });
        if (best) {
          STATE.year = best.year;
          STATE.month = best.month;
          period = "?year=" + best.year + "&month=" + best.month;
        }
        STATE.reports = rows || [];
        STATE.loaded.reports = true;
      })
      .catch(function () {
        /* fall back to the backend's current-month default */
      });
  }

  function get(path) {
    return api.get(path);
  }

  function post(path, payload) {
    return api.post(path, payload);
  }

  function patch(path, payload) {
    return api.patch(path, payload);
  }

  function put(path, payload) {
    return api.put(path, payload);
  }

  function del(path) {
    return api.del(path);
  }


  // ---- i18n for dynamic strings ---------------------------------------
  //
  // The static markup switches language with the `.ar` / `.en` span pair. That
  // pattern cannot be used for attributes like placeholder/title, so dynamic
  // elements carry `data-ph-ar` / `data-ph-en` (or `data-title-ar` / `-en`) and
  // applyI18n() rewrites the attribute whenever the language changes. Keeping
  // both strings in the DOM means a switch never loses a translation.
  var I18N = {
    "ph.search.permissions": {
      ar: "ابحث بالاسم أو الوصف…",
      en: "Search by name or description…",
    },
    "ph.shortTitle": { ar: "عنوان مختصر", en: "Short title" },
    "ph.companyCode": { ar: "مثال: FIN", en: "e.g. FIN" },
    "ph.roleCode": { ar: "اتركه فارغًا للجميع", en: "leave empty for all roles" },
    "ph.integrationName": { ar: "مزامنة CRM", en: "CRM sync" },
    "ph.endpointUrl": {
      ar: "https://hooks.example.com/safir",
      en: "https://hooks.example.com/safir",
    },
    "ph.formCode": { ar: "مثال: capex", en: "e.g. capex" },
    "ph.fieldKey": { ar: "مثال: amount", en: "e.g. amount" },
    "ph.requirementKey": { ar: "مثال: quote", en: "e.g. quote" },
    "ph.workflowCode": { ar: "مثال: capex_flow", en: "e.g. capex_flow" },
    "ph.comment": { ar: "أضف تعليقًا…", en: "Add a comment…" },
    "ph.search": {
      ar: "ابحث في الشركات والتقارير والدعم…",
      en: "Search companies, reports, support…",
    },
  };

  // Emit the current placeholder plus both languages so the value survives a
  // language switch without re-rendering the view.
  function phAttr(key) {
    var e = I18N[key];
    if (!e) return "";
    return (
      ' placeholder="' +
      escAttr(STATE.lang === "ar" ? e.ar : e.en) +
      '" data-ph-ar="' +
      escAttr(e.ar) +
      '" data-ph-en="' +
      escAttr(e.en) +
      '"'
    );
  }

  function applyI18n(root) {
    var scope = root || document;
    scope.querySelectorAll("[data-ph-ar]").forEach(function (el) {
      el.setAttribute(
        "placeholder",
        el.getAttribute(STATE.lang === "ar" ? "data-ph-ar" : "data-ph-en"),
      );
    });
    scope.querySelectorAll("[data-title-ar]").forEach(function (el) {
      el.setAttribute(
        "title",
        el.getAttribute(STATE.lang === "ar" ? "data-title-ar" : "data-title-en"),
      );
    });
  }

  // ---- formatting ------------------------------------------------------
  var NUM = new Intl.NumberFormat("en-US");

  // Compact form for the KPI tiles: 192.4 (millions).
  function millions(value) {
    if (value === null || value === undefined) return "—";
    return (Number(value) / 1e6).toFixed(1);
  }

  function setText(selector, value) {
    document.querySelectorAll(selector).forEach(function (el) {
      el.textContent = value;
    });
  }

  var AR_DIGITS = ["٠", "١", "٢", "٣", "٤", "٥", "٦", "٧", "٨", "٩"];

  function toArabicDigits(text) {
    return String(text).replace(/[0-9]/g, function (d) {
      return AR_DIGITS[Number(d)];
    });
  }

  function setKpi(key, value) {
    setText('[data-kpi="' + key + '"]', value);
  }

  function statusLabel(status) {
    var map = {
      submitted: { ar: "تم الاستلام", en: "Received" },
      under_review: { ar: "قيد المراجعة", en: "Under review" },
      reviewed: { ar: "تمت المراجعة", en: "Reviewed" },
      draft: { ar: "مسودة", en: "Draft" },
    };
    return map[status] || { ar: "بانتظار التقرير", en: "Awaiting report" };
  }

  function statusClass(status) {
    if (status === "reviewed" || status === "submitted") return "ok";
    if (status === "under_review") return "late";
    return "miss";
  }

  function healthClass(health) {
    var map = {
      strong: "strong",
      stable: "stable",
      watch: "watch",
      attention: "risk",
    };
    return map[health] || "stable";
  }

  function healthLabel(health) {
    var map = {
      strong: { ar: "قوي", en: "Strong" },
      stable: { ar: "مستقر", en: "Stable" },
      watch: { ar: "تحت المراقبة", en: "Watch" },
      attention: { ar: "بحاجة لمتابعة", en: "Attention" },
    };
    return map[health] || map.stable;
  }

  var PALETTE = [
    "linear-gradient(145deg,#2C57A0,#0E2044)",
    "linear-gradient(145deg,#B08A31,#8C6A22)",
    "linear-gradient(145deg,#1F9D6B,#12603F)",
    "linear-gradient(145deg,#5C4CB0,#332766)",
    "linear-gradient(145deg,#C4483F,#8E2F28)",
    "linear-gradient(145deg,#7C8AA0,#4A5568)",
  ];

  function initial(name) {
    return (name || "؟").trim().charAt(0);
  }

  function growthHtml(p) {
    if (p === null || p === undefined) {
      return '<span class="delta flat"><span class="ar">بانتظار</span><span class="en">Pending</span></span>';
    }
    var up = p >= 0;
    return (
      '<span class="delta ' +
      (up ? "up" : "down") +
      '">' +
      (up ? "▲ " : "▼ ") +
      "<span class=\"ar\">" +
      toArabicDigits(Math.abs(p).toFixed(1)) +
      '٪</span><span class="en">' +
      Math.abs(p).toFixed(1) +
      "%</span></span>"
    );
  }

  var SECTOR = {
    Technology: { ar: "التقنية والخدمات الرقمية", en: "Technology & Digital" },
    "Real Estate": { ar: "العقار والتطوير", en: "Real Estate & Development" },
    Industrial: { ar: "الصناعة والتصنيع", en: "Industry & Manufacturing" },
    Logistics: { ar: "النقل والخدمات اللوجستية", en: "Transport & Logistics" },
    Retail: { ar: "التجزئة", en: "Retail" },
    Healthcare: { ar: "الرعاية الصحية", en: "Healthcare" },
    Contracting: { ar: "المقاولات والإنشاء", en: "Contracting & Construction" },
  };

  var AR_MONTHS = [
    "يناير",
    "فبراير",
    "مارس",
    "أبريل",
    "مايو",
    "يونيو",
    "يوليو",
    "أغسطس",
    "سبتمبر",
    "أكتوبر",
    "نوفمبر",
    "ديسمبر",
  ];
  var EN_MONTHS = [
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
  ];

  function dateLabel(iso) {
    if (!iso) return { ar: "—", en: "—" };
    var d = new Date(iso);
    if (isNaN(d.getTime()))
      return { ar: iso.slice(0, 10), en: iso.slice(0, 10) };
    return {
      ar: d.getDate() + " " + AR_MONTHS[d.getMonth()],
      en: d.getDate() + " " + EN_MONTHS[d.getMonth()],
    };
  }

  // The managed sector catalogue (S03) overrides the built-in map when the
  // viewer may read it; the static map stays as an offline fallback for
  // accounts without sector.read (e.g. a company-scoped manager).
  function ensureSectors() {
    if (STATE.loaded.sectors) return Promise.resolve(STATE.sectors);
    if (!has("sector.read")) return Promise.resolve([]);
    return get("/api/v1/admin/sectors")
      .then(function (rows) {
        STATE.sectors = rows || [];
        STATE.loaded.sectors = true;
        return STATE.sectors;
      })
      .catch(function () {
        return [];
      });
  }

  function sectorLabel(sector) {
    var key = (sector || "").toLowerCase();
    var managed = (STATE.sectors || []).filter(function (s) {
      return (
        (s.code || "").toLowerCase() === key ||
        (s.name_en || "").toLowerCase() === key ||
        (s.name_ar || "") === sector
      );
    })[0];
    if (managed) return { ar: managed.name_ar, en: managed.name_en };
    var found = SECTOR[sector];
    if (found) return found;
    return { ar: sector || "", en: sector || "" };
  }

  function reportCard(row, i) {
    var bg = PALETTE[i % PALETTE.length];
    var status = statusClass(row.report_status);
    var label = statusLabel(row.report_status);
    var sector = sectorLabel(row.sector);
    var rep = reportForCompany(row.id);
    var reportId = rep ? rep.id : null;
    var action = reportId
      ? '<button class="btn-ghost" data-report-id="' + reportId + '">' +
        dual("عرض التقرير", "View Report") +
        '<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m15 18-6-6 6-6"/></svg></button>'
      : '<button class="btn-ghost" data-remind="' + row.id + '">' +
        dual("متابعة الشركة", "Follow up") +
        '<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m15 18-6-6 6-6"/></svg></button>';
    return (
      '<div class="rep"' + (reportId ? ' data-open-report="' + reportId + '"' : "") + ">" +
      '<div class="rep-top">' +
      '<div class="rep-logo" style="background:' +
      bg +
      '">' +
      initial(row.name_ar) +
      "</div>" +
      '<div class="rep-id">' +
      '<div class="rep-name"><span class="ar">' +
      escapeHtml(row.name_ar) +
      '</span><span class="en">' +
      escapeHtml(row.name_en || row.name_ar) +
      "</span></div>" +
      '<div class="rep-sec"><span class="ar">' +
      escapeHtml(sector.ar) +
      '</span><span class="en">' +
      escapeHtml(sector.en) +
      "</span></div>" +
      "</div>" +
      '<span class="status ' + status + '"><i></i>' + dual(label.ar, label.en) + "</span>" +
      "</div>" +
      '<div class="rep-stats">' +
      '<div class="stat"><div class="l">' + dual("الإيرادات", "Revenue") + '</div><div class="v">' +
      millions(row.revenue) +
      "</div></div>" +
      '<div class="stat"><div class="l">' + dual("المصروفات", "Expenses") + '</div><div class="v">' +
      millions(row.expenses) +
      "</div></div>" +
      '<div class="stat"><div class="l">' + dual("الصافي", "Net") + '</div><div class="v">' +
      millions(row.net_result) +
      "</div></div>" +
      "</div>" +
      '<div class="rep-foot">' +
      '<span class="rep-upd"><span class="ar">' +
      (row.has_report ? "محدّث" : "متأخر") +
      '</span><span class="en">' +
      (row.has_report ? "Updated" : "Overdue") +
      "</span></span>" +
      growthHtml(row.revenue_pct) +
      action +
      "</div></div>"
    );
  }

  function subCard(row, i) {
    var bg = PALETTE[i % PALETTE.length];
    return (
      '<div class="sub">' +
      '<div class="sub-logo" style="background:' +
      bg +
      '">' +
      initial(row.name_ar) +
      "</div>" +
      '<div class="sub-name"><span class="ar">' +
      row.name_ar +
      '</span><span class="en">' +
      (row.name_en || row.name_ar) +
      "</span></div>" +
      '<div class="sub-val">' +
      (row.has_report ? millions(row.revenue) + "م" : "—") +
      "</div>" +
      '<div class="sub-pct ' +
      (row.revenue_pct === null || row.revenue_pct === undefined
        ? "down"
        : row.revenue_pct >= 0
          ? "up"
          : "down") +
      '">' +
      (row.revenue_pct === null || row.revenue_pct === undefined
        ? '<span class="ar">بانتظار</span><span class="en">Pending</span>'
        : (row.revenue_pct >= 0 ? "▲ " : "▼ ") +
          '<span class="ar">' +
          toArabicDigits(Math.abs(row.revenue_pct).toFixed(1)) +
          '٪</span><span class="en">' +
          Math.abs(row.revenue_pct).toFixed(1) +
          "%</span>") +
      "</div></div>"
    );
  }
  function sparkPath(pct, seed) {
    var rising = pct === null || pct === undefined ? true : pct >= 0;
    var base = [18, 15, 17, 12, 14, 9, 10, 4];
    if (!rising) base = [4, 8, 6, 11, 9, 14, 13, 18];
    var wobble = (seed % 3) - 1;
    return base
      .map(function (y, i) {
        var yy = Math.max(
          2,
          Math.min(20, y + ((i + seed) % 2 === 0 ? wobble : -wobble)),
        );
        return (i === 0 ? "M" : "L") + (i * 8.6 + 1).toFixed(1) + " " + yy;
      })
      .join(" ");
  }

  function overviewCard(row, i) {
    var bg = PALETTE[i % PALETTE.length];
    var h = healthLabel(row.health);
    var stroke =
      row.revenue_pct !== null &&
      row.revenue_pct !== undefined &&
      row.revenue_pct < 0
        ? "#C4483F"
        : "#1F9D6B";
    var meta = row.has_report
      ? '<span class="ar">' +
        millions(row.revenue) +
        "م" +
        (row.revenue_pct === null || row.revenue_pct === undefined
          ? ""
          : " · " +
            (row.revenue_pct >= 0 ? "نمو " : "انخفاض ") +
            Math.abs(row.revenue_pct).toFixed(1) +
            "٪") +
        '</span><span class="en">' +
        millions(row.revenue) +
        "M" +
        (row.revenue_pct === null || row.revenue_pct === undefined
          ? ""
          : " · " +
            (row.revenue_pct >= 0 ? "+" : "−") +
            Math.abs(row.revenue_pct).toFixed(1) +
            "%") +
        "</span>"
      : '<span class="ar">بانتظار التقرير الشهري</span><span class="en">Awaiting report</span>';
    return (
      '<div class="ov">' +
      '<div class="ov-logo" style="background:' +
      bg +
      '">' +
      initial(row.name_ar) +
      "</div>" +
      '<div><div class="ov-name"><span class="ar">' +
      row.name_ar +
      '</span><span class="en">' +
      (row.name_en || row.name_ar) +
      "</span></div>" +
      '<div class="ov-meta">' +
      meta +
      "</div></div>" +
      '<svg class="ov-spark" viewBox="0 0 62 22" preserveAspectRatio="none"><path d="' +
      sparkPath(row.revenue_pct, row.id) +
      '" fill="none" stroke="' +
      stroke +
      '" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>' +
      '<span class="health-pill ' +
      healthClass(row.health) +
      '"><i></i><span class="ar">' +
      h.ar +
      '</span><span class="en">' +
      h.en +
      "</span></span>" +
      "</div>"
    );
  }

  function hydrateCompanies(data) {
    var rows = data.companies_performance || [];

    var repGrid = document.querySelector(".rep-grid");
    var subs = document.querySelector(".subs");
    var overview = document.querySelector(".ov-card .card-body");

    if (!rows.length) {
      var none = emptyHtml("لا توجد بيانات شركات لهذه الفترة.", "No company data for this period.");
      if (repGrid) repGrid.innerHTML = none;
      if (subs) subs.innerHTML = none;
      if (overview) overview.innerHTML = none;
      return;
    }

    if (repGrid) repGrid.innerHTML = rows.map(reportCard).join("");
    if (subs) subs.innerHTML = rows.map(subCard).join("");
    if (overview) overview.innerHTML = rows.map(overviewCard).join("");

    bindReportCardActions(repGrid);

    var hubTotal = (data.kpis && data.kpis.total_revenue) || 0;
    setText('[data-kpi="hub_total"]', toArabicDigits(millions(hubTotal)));
    setText('[data-kpi="hub_total_en"]', millions(hubTotal));
    setText(
      '[data-kpi="structure_count"]',
      toArabicDigits(String(rows.length)),
    );
    setText('[data-kpi="structure_count_en"]', String(rows.length));

    var sectors = {};
    rows.forEach(function (r) {
      if (r.sector) sectors[r.sector] = true;
    });
    var sectorCount = Object.keys(sectors).length;
    setText('[data-kpi="sector_count"]', toArabicDigits(String(sectorCount)));
    setText('[data-kpi="sector_count_en"]', String(sectorCount));
  }

  // S01 AC-01: opening an indicator shows its source records. Table 13's
  // "عرض التفاصيل" opens the linked source without creating a copy, so this
  // only reads the API and lists links; it never writes.
  var DRILL_LABELS = {
    companies_count: { ar: "عدد الشركات", en: "Companies" },
    total_revenue: { ar: "إجمالي الإيرادات", en: "Total Revenue" },
    total_expenses: { ar: "إجمالي المصروفات", en: "Total Expenses" },
    total_net_result: { ar: "صافي النتائج", en: "Net Result" },
    reports_submitted: { ar: "التقارير المستلمة", en: "Reports Submitted" },
    reports_missing: { ar: "التقارير المفقودة", en: "Reports Missing" },
    companies_requiring_attention: { ar: "شركات تحتاج متابعة", en: "Need Attention" },
    open_support_requests: { ar: "الطلبات المفتوحة", en: "Open Requests" },
    pending_financial_reviews: { ar: "مراجعات مالية معلقة", en: "Pending Reviews" },
  };

  function openIndicatorSources(indicator) {
    var label = DRILL_LABELS[indicator] || { ar: indicator, en: indicator };
    openModal({
      title: dual(label.ar, label.en),
      body: loadingHtml(),
      wide: true,
      onMount: function () {
        get(
          "/api/v1/dashboard/indicator/" + encodeURIComponent(indicator) +
            "/sources" + period,
        )
          .then(function (data) {
            var host = byId("modalBody");
            if (!host) return;
            var rows = data.records || [];
            if (!rows.length) {
              host.innerHTML = emptyHtml(
                "لا توجد سجلات مصدر لهذا المؤشر.",
                "No source records for this indicator.",
              );
              return;
            }
            host.innerHTML =
              '<table class="table"><thead><tr><th>' +
              dual("النوع", "Type") + "</th><th>" + dual("السجل", "Record") +
              "</th></tr></thead><tbody>" +
              rows.map(function (r) {
                var typeLabel = r.kind === "company"
                  ? dual("شركة", "Company")
                  : r.kind === "support_request"
                    ? dual("طلب", "Request")
                    : dual("تقرير", "Report");
                return '<tr data-src-kind="' + escapeHtml(r.kind) +
                  '" data-src-id="' + r.record_id + '" style="cursor:pointer"><td>' +
                  typeLabel + "</td><td>" + escapeHtml(r.label_ar) + "</td></tr>";
              }).join("") +
              "</tbody></table>";
            host.querySelectorAll("[data-src-kind]").forEach(function (el) {
              el.addEventListener("click", function () {
                var kind = el.getAttribute("data-src-kind");
                var id = parseInt(el.getAttribute("data-src-id"), 10);
                closeModal();
                if (kind === "company") openCompany(id);
                else if (kind === "support_request") navTo("support");
                else if (kind === "monthly_report") openReport(id);
              });
            });
          })
          .catch(function (err) {
            var host = byId("modalBody");
            if (host) host.innerHTML = errorHtml(err && err.message);
          });
      },
    });
  }

  // Wire every KPI tile that has a drill target, once.
  function bindIndicatorDrills() {
    document.querySelectorAll("[data-drill]").forEach(function (el) {
      if (el.getAttribute("data-drill-bound")) return;
      el.setAttribute("data-drill-bound", "1");
      var go = function () {
        openIndicatorSources(el.getAttribute("data-drill"));
      };
      el.addEventListener("click", go);
      el.addEventListener("keydown", function (e) {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          go();
        }
      });
    });
  }

  // S01 "الأولويات": record links the caller may act on, restricted per access
  // by the backend, so every entry is openable.
  function hydratePriorities(data) {
    var host = byId("prioritiesList");
    if (!host) return;
    var rows = data.priorities || [];
    if (!rows.length) {
      host.innerHTML = emptyHtml("لا توجد أولويات حالية.", "No current priorities.");
      return;
    }
    host.innerHTML = rows.map(function (p) {
      var label = STATE.lang === "ar"
        ? (p.label_ar || p.label_en || "")
        : (p.label_en || p.label_ar || "");
      var sub = p.overdue
        ? dual("متأخر", "Overdue")
        : (p.reason ? escapeHtml(p.reason) : "");
      var icon = p.kind === "company" ? "🏢"
        : p.kind === "support_request" ? "💬" : "📌";
      return '<div class="av-row" data-priority-kind="' + escapeHtml(p.kind) +
        '" data-priority-id="' + p.record_id + '">' +
        '<div class="grow"><div class="t">' + icon + " " + escapeHtml(label) +
        '</div>' + (sub ? '<div class="s">' + sub + "</div>" : "") +
        "</div></div>";
    }).join("");
    host.querySelectorAll("[data-priority-kind]").forEach(function (el) {
      el.addEventListener("click", function () {
        var kind = el.getAttribute("data-priority-kind");
        var id = parseInt(el.getAttribute("data-priority-id"), 10);
        if (kind === "company") {
          openCompany(id);
        } else if (kind === "owner_decision") {
          navTo("decisions");
        } else if (kind === "support_request") {
          navTo("support");
        }
      });
    });
  }

  // The dashboard report cards offer "View Report" (a real report exists) or
  // "Follow up" (the subsidiary has not sent its report yet).
  function bindReportCardActions(repGrid) {
    if (!repGrid) return;
    repGrid.querySelectorAll("[data-report-id]").forEach(function (btn) {
      btn.addEventListener("click", function (e) {
        e.stopPropagation();
        openReport(parseInt(btn.getAttribute("data-report-id"), 10));
      });
    });
    repGrid.querySelectorAll("[data-remind]").forEach(function (btn) {
      btn.addEventListener("click", function (e) {
        e.stopPropagation();
        followUpCompany(parseInt(btn.getAttribute("data-remind"), 10));
      });
    });
    repGrid.querySelectorAll("[data-open-report]").forEach(function (card) {
      card.addEventListener("click", function () {
        openReport(parseInt(card.getAttribute("data-open-report"), 10));
      });
    });
  }

  // A subsidiary without a report has no report to open. Rather than fake a
  // "reminder" API that does not exist, open its record and offer the real,
  // permission-gated action that fits its state.
  function followUpCompany(companyId) {
    openModal({
      title: dual("متابعة الشركة", "Follow up"),
      body: loadingHtml(),
      onMount: function () {
        loadFollowUp(companyId);
      },
    });
  }

  function loadFollowUp(companyId) {
    var body = byId("modalBody");
    Promise.all([get("/api/v1/companies/" + companyId), ensureReports()])
      .then(function (res) {
        var c = res[0];
        if (!body) return;
        var rep = reportForCompany(companyId);
        var sector = sectorLabel(c.sector);
        var actions = [];
        if (rep) {
          actions.push('<button class="btn-solid" id="fuOpen">' + dual("عرض التقرير", "Open report") + "</button>");
        } else if (has("monthly_report.create")) {
          actions.push('<button class="btn-solid" id="fuCreate">' + dual("إنشاء تقرير", "Create report") + "</button>");
        }
        if (has("support_request.create")) {
          actions.push('<button class="btn-outline" id="fuSupport">' + dual("طلب دعم", "Request support") + "</button>");
        }
        actions.push('<button class="btn-outline" id="fuClose">' + dual("إغلاق", "Close") + "</button>");
        body.innerHTML =
          '<div class="kv">' +
          kv(dual("الشركة", "Company"), escapeHtml(companyName(c))) +
          kv(dual("القطاع", "Sector"), dual(escapeHtml(sector.ar), escapeHtml(sector.en))) +
          kv(dual("المؤشر", "Health"), healthBadge(c.health)) +
          kv(dual("حالة التقرير", "Report status"), rep ? statusBadge(rep.status) : statusBadge(null)) +
          "</div>" +
          '<p class="note-block" style="margin-top:12px">' +
          (rep
            ? dual(
                "تم استلام تقرير هذه الشركة لهذه الفترة. يمكنك عرضه أو طلب دعم إضافي.",
                "This company has submitted a report for this period. Open it or request additional support.",
              )
            : dual(
                "لم تُستلم بعد تقرير هذه الشركة لهذه الفترة.",
                "This company has not submitted a report for this period yet.",
              )) +
          "</p>" +
          '<div class="modal-foot" style="margin-top:6px;border-radius:12px;border:1px solid var(--line-2)">' + actions.join("") + "</div>";
        if (byId("fuClose")) byId("fuClose").addEventListener("click", closeModal);
        if (byId("fuOpen")) byId("fuOpen").addEventListener("click", function () { openReport(rep.id); });
        if (byId("fuCreate")) byId("fuCreate").addEventListener("click", function () { createReportForm(companyId); });
        if (byId("fuSupport")) byId("fuSupport").addEventListener("click", function () { supportCreateForm(companyId); });
      })
      .catch(function (err) {
        if (body) body.innerHTML = errorHtml(errText(err));
      });
  }

  function createReportForm(companyId) {
    openModal({
      title: dual("إنشاء تقرير شهري", "Create monthly report"),
      body:
        '<div class="av-field"><label>' + dual("السنة", "Year") + '</label><input class="av-input" id="crYear" style="width:100%" value="' + escAttr(String(STATE.year || new Date().getFullYear())) + '"></div>' +
        '<div class="av-field"><label>' + dual("الشهر", "Month") + '</label><input class="av-input" id="crMonth" style="width:100%" value="' + escAttr(String(STATE.month || new Date().getMonth() + 1)) + '"></div>' +
        '<div class="av-field"><label>' + dual("الإيرادات", "Revenue") + '</label><input class="av-input" id="crRev" style="width:100%"></div>' +
        '<div class="av-field"><label>' + dual("المصروفات", "Expenses") + '</label><input class="av-input" id="crExp" style="width:100%"></div>' +
        '<div class="av-field"><label>' + dual("ملاحظات الإدارة", "Management notes") + '</label><textarea class="av-textarea" id="crNotes"></textarea></div>',
      footer:
        '<button class="btn-outline" id="crCancel">' + dual("إلغاء", "Cancel") + "</button>" +
        '<button class="btn-solid" id="crSave">' + dual("إنشاء", "Create") + "</button>",
      onMount: function (root) {
        root.querySelector("#crCancel").addEventListener("click", closeModal);
        root.querySelector("#crSave").addEventListener("click", function () {
          var btn = this;
          var year = parseInt(root.querySelector("#crYear").value, 10);
          var month = parseInt(root.querySelector("#crMonth").value, 10);
          var rev = numOrNull(root.querySelector("#crRev").value);
          var exp = numOrNull(root.querySelector("#crExp").value);
          if (!year || year < 2000 || year > 2100) {
            toast(STATE.lang === "ar" ? "السنة غير صحيحة." : "Invalid year.", "err");
            return;
          }
          if (!month || month < 1 || month > 12) {
            toast(STATE.lang === "ar" ? "الشهر يجب أن يكون بين ١ و ١٢." : "Month must be between 1 and 12.", "err");
            return;
          }
          if (rev === null && exp === null) {
            toast(STATE.lang === "ar" ? "أدخل الإيرادات أو المصروفات." : "Enter revenue or expenses.", "err");
            return;
          }
          busy(btn, true);
          post("/api/v1/monthly-reports", {
            company_id: companyId,
            period_year: year,
            period_month: month,
            revenue: rev,
            expenses: exp,
            net_result: rev !== null && exp !== null ? rev - exp : null,
            management_notes: root.querySelector("#crNotes").value || null,
          })
            .then(function (created) {
              toast(STATE.lang === "ar" ? "تم إنشاء التقرير." : "Report created.", "ok");
              refreshAll().then(function () { openReport(created.id); });
            })
            .catch(function (err) {
              toast(errText(err), "err");
              busy(btn, false);
            });
        });
      },
    });
  }

  // ---- support requests ------------------------------------------------
  var CATEGORY = {
    business_development: {
      ar: "تطوير أعمال",
      en: "Business Dev.",
      cls: "dev",
    },
    marketing: { ar: "تسويق", en: "Marketing", cls: "mkt" },
    design: { ar: "تصميم", en: "Design", cls: "des" },
    accounting: { ar: "دعم مالي", en: "Financial Support", cls: "fin" },
    general: { ar: "عام", en: "General", cls: "fin" },
  };

  function supportStatus(status) {
    var map = {
      new: { ar: "جديد", en: "New", cls: "rev" },
      in_progress: { ar: "قيد التنفيذ", en: "In progress", cls: "ok" },
      waiting: { ar: "بانتظار", en: "Waiting", cls: "rev" },
      completed: { ar: "مكتمل", en: "Completed", cls: "ok" },
      closed: { ar: "مغلق", en: "Closed", cls: "ok" },
      rejected: { ar: "مرفوض", en: "Rejected", cls: "miss" },
    };
    return map[status] || map.new;
  }

  function deptInitial(name) {
    var map = {
      business_development: { ar: "تط", en: "BD" },
      marketing: { ar: "تس", en: "MK" },
      design: { ar: "تص", en: "DS" },
      accounting: { ar: "مح", en: "FN" },
      general: { ar: "عم", en: "HO" },
      holding_owner: { ar: "عم", en: "HO" },
      designer: { ar: "تص", en: "DS" },
      accountant: { ar: "مح", en: "FN" },
    };
    return map[name] || { ar: "عم", en: "HO" };
  }

  function deptInitialHtml(name) {
    var init = deptInitial(name);
    return dual(init.ar, init.en);
  }

  function deptLabel(name) {
    var map = {
      business_development: {
        ar: "التطوير التجاري",
        en: "Business Development",
      },
      marketing: { ar: "التسويق والاتصال", en: "Marketing & Comms" },
      design: { ar: "الهوية والتصميم", en: "Brand & Design" },
      accounting: { ar: "المالية والمحاسبة", en: "Finance & Accounting" },
      general: { ar: "المقر الرئيسي", en: "Head Office" },
      holding_owner: { ar: "المقر الرئيسي", en: "Head Office" },
    };
    return map[name] || { ar: "المقر الرئيسي", en: "Head Office" };
  }

  function supportRow(row) {
    var cat = CATEGORY[row.category] || CATEGORY.general;
    var st = supportStatus(row.status);
    var deptName = row.responsible_department || row.category;
    var dept = deptLabel(deptName);
    var date = dateLabel(row.created_at);
    return (
      "<tr>" +
      '<td><div class="co-cell"><div class="co-dot" style="background:' +
      PALETTE[row.company_id % PALETTE.length] +
      '">' +
      initial(row.company_name_ar || "") +
      '</div><span><span class="ar">' +
      (row.company_name_ar || "") +
      '</span><span class="en">' +
      (row.company_name_en || row.company_name_ar || "") +
      "</span></span></div></td>" +
      '<td><span class="type-tag ' +
      cat.cls +
      '"><span class="ar">' +
      cat.ar +
      '</span><span class="en">' +
      cat.en +
      "</span></span></td>" +
      '<td class="date"><span class="ar">' +
      date.ar +
      '</span><span class="en">' +
      date.en +
      "</span></td>" +
      '<td><span class="dept"><span class="av">' +
      deptInitialHtml(deptName) +
      '</span><span class="ar">' +
      dept.ar +
      '</span><span class="en">' +
      dept.en +
      "</span></span></td>" +
      '<td><span class="status ' +
      st.cls +
      '"><i></i><span class="ar">' +
      st.ar +
      '</span><span class="en">' +
      st.en +
      "</span></span></td>" +
      "</tr>"
    );
  }

  function hydrateSupport(rows) {
    var body = document.getElementById("supportBody");
    if (!body) return;
    if (!rows.length) {
      body.innerHTML =
        '<tr><td colspan="5">' +
        emptyHtml("لا توجد طلبات دعم لهذه الفترة.", "No support requests for this period.") +
        "</td></tr>";
      return;
    }
    body.innerHTML = rows.slice(0, 5).map(supportRow).join("");

    var pending = rows.filter(function (r) {
      return (
        r.status !== "completed" &&
        r.status !== "closed" &&
        r.status !== "rejected"
      );
    }).length;
    setText('[data-kpi="support_pending"]', toArabicDigits(String(pending)));
    setText('[data-kpi="support_pending_en"]', String(pending));
  }

  // ---- hydration -------------------------------------------------------
  function hydrateKpis(data) {
    var k = data.kpis || {};
    setKpi("companies_count", k.companies_count);
    setKpi("companies_count_unit", k.companies_count);
    setKpi("total_revenue", millions(k.total_revenue));
    setKpi("total_net_result", millions(k.total_net_result));
    setKpi("reports_submitted", k.reports_submitted);
    setKpi("companies_requiring_attention", k.companies_requiring_attention);
    setKpi("open_support_requests", k.open_support_requests);

    var change = data.change_vs_previous || {};
    var delta = document.querySelector('[data-kpi="revenue_delta"]');
    if (delta) {
      if (change.revenue_pct === null || change.revenue_pct === undefined) {
        delta.className = "delta flat";
        delta.innerHTML = dual("لا توجد مقارنة", "No comparison");
      } else {
        delta.className = "delta " + (change.revenue_pct >= 0 ? "up" : "down");
        delta.innerHTML = dual(
          toArabicDigits(Math.abs(change.revenue_pct).toFixed(1)) + "٪",
          Math.abs(change.revenue_pct).toFixed(1) + "%",
        );
      }
    }

    var netDelta = document.querySelector('[data-kpi="net_delta"]');
    if (netDelta && change.net_pct !== null && change.net_pct !== undefined) {
      netDelta.className = "delta " + (change.net_pct >= 0 ? "up" : "down");
      netDelta.innerHTML = dual(
        toArabicDigits(Math.abs(change.net_pct).toFixed(1)) + "٪",
        Math.abs(change.net_pct).toFixed(1) + "%",
      );
    }

    var margin = document.querySelector('[data-kpi="net_margin"]');
    if (margin && Number(k.total_revenue)) {
      var m = (Number(k.total_net_result) / Number(k.total_revenue)) * 100;
      margin.textContent = toArabicDigits(m.toFixed(1)) + "٪";
    }

    var marginEn = document.querySelector('[data-kpi="net_margin_en"]');
    if (marginEn && Number(k.total_revenue)) {
      var m2 = (Number(k.total_net_result) / Number(k.total_revenue)) * 100;
      marginEn.textContent = m2.toFixed(1) + "%";
    }

    var repPct = document.querySelector('[data-kpi="reports_pct"]');
    if (repPct && Number(k.companies_count)) {
      var rp = (Number(k.reports_submitted) / Number(k.companies_count)) * 100;
      repPct.className = "delta " + (rp >= 50 ? "up" : "down");
      repPct.innerHTML = dual(
        toArabicDigits(rp.toFixed(0)) + "٪",
        rp.toFixed(0) + "%",
      );
    }
  }

  function renderInsights(insights) {
    var list = document.getElementById("insightsList");
    if (!list) return;
    if (!insights.length) {
      list.innerHTML = emptyHtml("لا توجد رؤى لهذه الفترة.", "No insights for this period.");
      return;
    }

    setText(
      '[data-kpi="insights_count"]',
      toArabicDigits(String(insights.length)),
    );
    setText('[data-kpi="insights_count_en"]', String(insights.length));
    var toneClass = {
      up: "g",
      down: "r",
      warn: "a",
      risk: "r",
      gold: "gold",
      neutral: "a",
    };
    var tagClass = {
      up: "up",
      down: "warn",
      warn: "warn",
      risk: "risk",
      gold: "gold",
      neutral: "",
    };
    list.innerHTML = insights
      .map(function (row) {
        var tag = row.metric
          ? '<span class="ins-tag ' +
            (tagClass[row.tone] || "") +
            '">' +
            row.metric +
            "</span>"
          : "";
        return (
          '<div class="aii-row">' +
          '<div class="aii-ic ' +
          (toneClass[row.tone] || "a") +
          '"></div>' +
          '<div class="aii-txt">' +
          '<div class="aii-t"><span class="ar">' +
          row.title_ar +
          '</span><span class="en">' +
          row.title_en +
          "</span></div>" +
          '<div class="aii-d"><span class="ar">' +
          row.detail_ar +
          '</span><span class="en">' +
          row.detail_en +
          "</span></div>" +
          '<div class="aii-meta">' +
          tag +
          "</div>" +
          "</div></div>"
        );
      })
      .join("");
  }

  function escapeHtml(text) {
    return String(text)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  }

  function loadingHtml() {
    return (
      '<div class="state"><span class="spinner"></span>' +
      '<span class="ar">جارٍ تحميل البيانات…</span>' +
      '<span class="en">Loading data…</span></div>'
    );
  }

  function errorHtml(message) {
    var safe = escapeHtml(message || "تعذّر تحميل البيانات.");
    return (
      '<div class="data-error">' +
      '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 9v4"/><path d="M12 17h.01"/><path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z"/></svg>' +
      '<span class="ar">' + safe + '</span>' +
      '<span class="en">' + safe + "</span></div>"
    );
  }

  function emptyHtml(ar, en) {
    return (
      '<div class="state"><span class="ar">' + escapeHtml(ar) +
      '</span><span class="en">' + escapeHtml(en) + "</span></div>"
    );
  }

  // ---- shared helpers --------------------------------------------------
  function byId(id) {
    return document.getElementById(id);
  }

  function escAttr(text) {
    return escapeHtml(text).replace(/"/g, "&quot;");
  }

  // Bilingual span pair, the pattern the whole stylesheet switches on.
  function dual(ar, en) {
    return (
      '<span class="ar">' + ar + '</span><span class="en">' + en + "</span>"
    );
  }

  function money(value) {
    if (value === null || value === undefined || value === "") {
      return { ar: "—", en: "—" };
    }
    var n = Math.round(Number(value));
    if (isNaN(n)) return { ar: "—", en: "—" };
    var s = NUM.format(n);
    return { ar: toArabicDigits(s) + " ر.س", en: s + " SAR" };
  }

  function plainNum(value) {
    if (value === null || value === undefined || value === "") return "—";
    var n = Number(value);
    return isNaN(n) ? String(value) : NUM.format(n);
  }

  function fmtDate(iso) {
    var d = dateLabel(iso);
    return dual(d.ar, d.en);
  }

  function fmtDateTime(iso) {
    if (!iso) return dual("—", "—");
    var d = new Date(iso);
    if (isNaN(d.getTime())) return dual(iso.slice(0, 10), iso.slice(0, 10));
    var base = dateLabel(iso);
    var hh = String(d.getHours()).padStart(2, "0");
    var mm = String(d.getMinutes()).padStart(2, "0");
    return dual(
      base.ar + " · " + toArabicDigits(hh + ":" + mm),
      base.en + " · " + hh + ":" + mm,
    );
  }

  function periodLabel() {
    var y = STATE.year,
      m = STATE.month;
    if (!y || !m) return { ar: "", en: "" };
    return {
      ar: AR_MONTHS[m - 1] + " " + toArabicDigits(String(y)),
      en: EN_MONTHS[m - 1] + " " + y,
    };
  }

  function statusBadge(status) {
    var label = statusLabel(status);
    return (
      '<span class="status ' +
      statusClass(status) +
      '"><i></i>' +
      dual(label.ar, label.en) +
      "</span>"
    );
  }

  function healthBadge(health) {
    var h = healthLabel(health);
    return (
      '<span class="health-pill ' +
      healthClass(health) +
      '"><i></i>' +
      dual(h.ar, h.en) +
      "</span>"
    );
  }

  function catBadge(category) {
    var cat = CATEGORY[category] || CATEGORY.general;
    return (
      '<span class="type-tag ' + cat.cls + '">' + dual(cat.ar, cat.en) + "</span>"
    );
  }

  function supStatusBadge(status) {
    var st = supportStatus(status);
    return (
      '<span class="status ' + st.cls + '"><i></i>' + dual(st.ar, st.en) + "</span>"
    );
  }

  // ---- toasts ----------------------------------------------------------
  // The live region exists from app load (not just on first toast) so screen
  // readers observe the container before a message is inserted (audit §4).
  function ensureToastRegion() {
    var wrap = byId("toastWrap");
    if (!wrap) {
      wrap = document.createElement("div");
      wrap.className = "toast-wrap";
      wrap.id = "toastWrap";
      wrap.setAttribute("role", "status");
      wrap.setAttribute("aria-live", "polite");
      document.body.appendChild(wrap);
    }
    return wrap;
  }

  function toast(message, kind) {
    var wrap = ensureToastRegion();
    var t = document.createElement("div");
    t.className = "toast " + (kind || "");
    if (kind === "err") t.setAttribute("role", "alert");
    t.innerHTML = '<div class="grow">' + escapeHtml(message) + "</div>";
    wrap.appendChild(t);
    setTimeout(function () {
      t.style.opacity = "0";
      t.style.transform = "translateY(-8px)";
      t.style.transition = ".24s";
      setTimeout(function () {
        if (t.parentNode) t.parentNode.removeChild(t);
      }, 260);
    }, kind === "err" ? 6000 : 3600);
  }

  // Never surface raw objects or status codes to the user. HTTP failures are
  // mapped to a short bilingual-safe sentence; anything unexpected falls back.
  function errText(err, fallback) {
    var fb = fallback || (STATE.lang === "ar" ? "تعذّر تنفيذ الطلب." : "The request could not be completed.");
    if (!err) return fb;
    if (err.status) {
      var byStatus = {
        400: STATE.lang === "ar" ? "طلب غير صالح. تحقّق من البيانات." : "Invalid request. Please check the data.",
        401: STATE.lang === "ar" ? "انتهت الجلسة. يرجى تسجيل الدخول من جديد." : "Session expired. Please sign in again.",
        403: STATE.lang === "ar" ? "ليست لديك صلاحية لهذا الإجراء." : "You do not have permission for this action.",
        404: STATE.lang === "ar" ? "العنصر المطلوب غير موجود." : "The requested item was not found.",
        409: STATE.lang === "ar" ? "لا يمكن تنفيذ الإجراء في الحالة الحالية." : "This action conflicts with the current state.",
        422: STATE.lang === "ar" ? "بيانات غير مكتملة أو غير صحيحة." : "Some fields are missing or invalid.",
        429: STATE.lang === "ar" ? "محاولات كثيرة. حاول لاحقًا." : "Too many attempts. Try again later.",
        500: STATE.lang === "ar" ? "خطأ في الخادم. حاول لاحقًا." : "Server error. Please try again.",
      };
      if (byStatus[err.status]) return byStatus[err.status];
    }
    var msg = typeof err.message === "string" ? err.message : "";
    if (!msg || msg === "[object Object]") return fb;
    return msg;
  }

  // ---- modal + confirm -------------------------------------------------
  function openModal(opts) {
    closeModal();
    var backdrop = document.createElement("div");
    backdrop.className = "modal-backdrop";
    backdrop.id = "appModal";
    backdrop.innerHTML =
      '<div class="modal' +
      (opts.wide ? " wide" : "") +
      '" role="dialog" aria-modal="true">' +
      '<div class="modal-head"><h2>' +
      opts.title +
      '</h2><button class="modal-x" aria-label="close">&times;</button></div>' +
      '<div class="modal-body" id="modalBody">' +
      (opts.body || "") +
      "</div>" +
      (opts.footer
        ? '<div class="modal-foot" id="modalFoot">' + opts.footer + "</div>"
        : "") +
      "</div>";
    document.body.appendChild(backdrop);
    backdrop.addEventListener("click", function (e) {
      if (e.target === backdrop) closeModal();
    });
    backdrop.querySelector(".modal-x").addEventListener("click", closeModal);
    document.addEventListener("keydown", escClose);
    if (opts.onMount) opts.onMount(backdrop, backdrop.querySelector("#modalBody"));
  }

  function escClose(e) {
    if (e.key === "Escape") closeModal();
  }

  function closeModal() {
    var m = byId("appModal");
    if (m) m.parentNode.removeChild(m);
    document.removeEventListener("keydown", escClose);
  }

  function confirmDialog(opts) {
    return new Promise(function (resolve) {
      openModal({
        title: opts.title || dual("تأكيد", "Confirm"),
        body:
          '<p class="note-block">' +
          escapeHtml(opts.message || "") +
          "</p>" +
          (opts.detail ? '<p class="note-block">' + opts.detail + "</p>" : ""),
        footer:
          '<button class="btn-outline" id="cfCancel">' +
          dual("إلغاء", "Cancel") +
          '</button><button class="btn-solid ' +
          (opts.danger ? "danger" : "") +
          '" id="cfOk">' +
          (opts.confirmLabel || dual("تأكيد", "Confirm")) +
          "</button>",
        onMount: function (root) {
          root.querySelector("#cfCancel").addEventListener("click", function () {
            closeModal();
            resolve(false);
          });
          root.querySelector("#cfOk").addEventListener("click", function () {
            closeModal();
            resolve(true);
          });
        },
      });
    });
  }

  function busy(btn, on) {
    if (!btn) return;
    if (on) {
      btn.setAttribute("data-label", btn.innerHTML);
      btn.disabled = true;
      btn.innerHTML = '<span class="spinner"></span>';
    } else {
      btn.disabled = false;
      if (btn.getAttribute("data-label")) {
        btn.innerHTML = btn.getAttribute("data-label");
      }
    }
  }

  // ---- language --------------------------------------------------------
  function setLang(lang) {
    var html = document.documentElement;
    document.querySelectorAll(".lang-opt").forEach(function (o) {
      o.classList.toggle("on", o.getAttribute("data-lang") === lang);
    });
    html.classList.remove("lang-ar", "lang-en");
    html.classList.add("lang-" + lang);
    html.setAttribute("lang", lang);
    html.setAttribute("dir", lang === "ar" ? "rtl" : "ltr");
    var ask = document.querySelector(".ask-box input");
    if (ask) {
      ask.placeholder =
        lang === "ar"
          ? "مثال: ملخص أداء المجموعة هذا الشهر"
          : "e.g. Group performance summary this month";
    }
    try {
      localStorage.setItem("safir.lang.v1", lang);
    } catch (e) {
      /* storage disabled */
    }
    if (typeof STATE !== "undefined") STATE.lang = lang;
    if (typeof applyI18n === "function") applyI18n();
    applyDocTitle();
    if (typeof refreshActiveView === "function") refreshActiveView();
  }

  // Keep the document title in the active language (and in sync with the
  // current view) instead of leaving the server-rendered Arabic title forever.
  var VIEW_TITLES = {
    dashboard: { ar: "لوحة القيادة التنفيذية", en: "Executive Dashboard" },
    subsidiaries: { ar: "الشركات التابعة", en: "Subsidiaries" },
    reports: { ar: "التقارير الشهرية", en: "Monthly Reports" },
    financial: { ar: "المراجعة المالية", en: "Financial Review" },
    investments: { ar: "الاستثمارات", en: "Investments" },
    support: { ar: "الدعم", en: "Support" },
    requests: { ar: "الطلبات", en: "Requests" },
    approvals: { ar: "الموافقات", en: "Approvals" },
    documents: { ar: "المستندات", en: "Documents" },
    bi: { ar: "ذكاء الأعمال", en: "Business Intelligence" },
    analytics: { ar: "التحليلات", en: "Analytics" },
    inbox: { ar: "الإشعارات", en: "Notifications" },
    leads: { ar: "طلبات الموقع", en: "Website Leads" },
    employees: { ar: "الموظفون والتقييم", en: "Employees & Assessment" },
    operations: { ar: "العمليات", en: "Operations" },
    decisions: { ar: "قرارات المالك", en: "Owner Decisions" },
    projects: { ar: "المشاريع والفرص", en: "Projects & Opportunities" },
    accounting: { ar: "المحاسبة", en: "Accounting" },
    confidential: { ar: "الوصول السري", en: "Confidential Access" },
    admin: { ar: "الإدارة", en: "Administration" },
  };

  function applyDocTitle() {
    var brand =
      STATE.lang === "ar"
        ? "سفير القابضة ٢٠٢٧ — "
        : "Safir Holding 2027 — ";
    var view = (typeof STATE !== "undefined" && STATE.view) || "dashboard";
    var t = VIEW_TITLES[view];
    document.title = brand + (t ? (STATE.lang === "ar" ? t.ar : t.en) : "");
  }

  // Re-render the current view when the language changes, so any Arabic-only
  // string baked into server-driven markup is rebuilt in the new language.
  function refreshActiveView() {
    if (!USER) return;
    var view = (typeof STATE !== "undefined" && STATE.view) || "dashboard";
    if (view === "admin" && typeof renderAdminTab === "function") {
      renderAdminTab(STATE.adminTab);
      return;
    }
    if (typeof loadView === "function") loadView(view);
  }

  function bindLang() {
    document.querySelectorAll(".lang-opt").forEach(function (b) {
      b.addEventListener("click", function () {
        setLang(b.getAttribute("data-lang"));
      });
    });
    var saved = null;
    try {
      saved = localStorage.getItem("safir.lang.v1");
    } catch (e) {
      saved = null;
    }
    setLang(saved === "en" ? "en" : "ar");
  }

  // ---- state -----------------------------------------------------------

  function reportForCompany(companyId) {
    for (var i = 0; i < STATE.reports.length; i++) {
      var r = STATE.reports[i];
      if (
        r.company_id === companyId &&
        r.period_year === STATE.year &&
        r.period_month === STATE.month
      ) {
        return r;
      }
    }
    return null;
  }

  function companyById(id) {
    for (var i = 0; i < STATE.companies.length; i++) {
      if (STATE.companies[i].id === id) return STATE.companies[i];
    }
    return null;
  }

  function companyName(row) {
    if (!row) return "";
    return STATE.lang === "ar"
      ? row.name_ar || row.name_en || ""
      : row.name_en || row.name_ar || "";
  }

  function reportCompanyName(r) {
    if (!r) return "";
    return STATE.lang === "ar"
      ? r.company_name_ar || r.company_name_en || ""
      : r.company_name_en || r.company_name_ar || "";
  }


  function hydrateAiAnswer(data, question) {
    var box = document.getElementById("aiAnswer");
    if (!box || !data.answer) return;

    if (question) {
      var q = box.querySelector(".answer-q");
      if (q) {
        var safeQ = escapeHtml(question);
        q.innerHTML =
          '<span class="ar">«' +
          safeQ +
          '»</span><span class="en">“' +
          safeQ +
          "”</span>";
      }
    }

    // The provider answers in Arabic; mirror it into the EN span so the block
    // is never blank when the interface is switched to English. Escape it --
    // a real LLM provider could otherwise emit markup.
    var body = box.querySelector("#aiAnswerBody");
    if (body) {
      var safe = escapeHtml(data.answer);
      body.innerHTML =
        '<p><span class="ar">' +
        safe +
        '</span><span class="en">' +
        safe +
        "</span></p>";
    }
  }

  // ---- routing ---------------------------------------------------------
  var VIEWS = [
    "dashboard",
    "subsidiaries",
    "reports",
    "financial",
    "investments",
    "support",
    "requests",
    "approvals",
    "documents",
    "bi",
    "analytics",
    "inbox",
    "leads",
    "employees",
    "operations",
    "decisions",
    "projects",
    "accounting",
    "confidential",
    "admin",
  ];
  var NAV_PERM = {
    dashboard: ["dashboard.holding", "dashboard.company"],
    subsidiaries: ["company.read"],
    reports: ["monthly_report.read_own", "monthly_report.read_all"],
    financial: ["financial_summary.read_own", "financial_summary.read_all"],
    investments: ["dashboard.holding"],
    support: ["support_request.read_own", "support_request.read_all"],
    requests: ["form.read"],
    approvals: ["approval.read_own", "approval.read_all"],
    documents: ["document.read"],
    // The BI view renders the dashboard insights payload (group KPIs, company
    // performance), so it is gated by the same permission its endpoint
    // (`GET /ai/insights`) enforces -- not by `ai.*`, which only meters the
    // Holding/Company AI Q&A. Gating on `ai.*` let a role with AI-only access
    // open the view and then hit a 403; gating on `dashboard.*` keeps the nav
    // and the API in agreement without widening data access.
    bi: ["dashboard.holding", "dashboard.company"],
    analytics: [
      "analytics.holding",
      "analytics.company",
      "analytics.operations",
      "analytics.compliance",
    ],
    inbox: ["notification.read_own"],
    leads: ["website_lead.read"],
    employees: [
      "employee.read",
      "assessment.read",
      "advisor.read",
      "advisor.session.read_own",
    ],
    operations: [
      "task.read_own",
      "task.read_all",
      "weekly_report.read_own",
      "weekly_report.read_all",
      "campaign.read",
    ],
    decisions: ["owner_decision.read"],
    projects: ["project.read"],
    accounting: [
      "account.read",
      "journal.read",
      "invoice.read",
      "asset.read",
      "budget.read",
      "opening_balance.read",
      "kpi.read",
      "accounting_policy.read",
    ],
    confidential: ["complaint.read_own", "complaint.decide", "complaint.create"],
    admin: [
      "company.read",
      "ownership.read",
      "department.read",
      "user.read_all",
      "role.read",
    ],
  };

  function canView(view) {
    var perms = NAV_PERM[view] || [];
    return perms.some(has);
  }

  function navTo(view, push) {
    if (VIEWS.indexOf(view) < 0) view = "dashboard";
    if (!canView(view)) {
      toast(
        STATE.lang === "ar"
          ? "ليست لديك صلاحية للوصول إلى هذا القسم."
          : "You do not have permission to open this section.",
        "warn",
      );
      return;
    }
    STATE.view = view;
    document.querySelectorAll("[data-view]").forEach(function (el) {
      var isSection = el.classList.contains("view") || el.classList.contains("app-view");
      if (isSection) el.classList.toggle("view-hidden", el.getAttribute("data-view") !== view);
    });
    document.querySelectorAll(".nav-item").forEach(function (n) {
      var on = n.getAttribute("data-view") === view;
      n.classList.toggle("active", on);
      if (on) n.setAttribute("aria-current", "page");
      else n.removeAttribute("aria-current");
    });
    applyDocTitle();
    var board = byId("board");
    if (board) board.classList.toggle("view-hidden", view !== "dashboard");
    if (push !== false) {
      try {
        history.replaceState(null, "", view === "dashboard" ? location.pathname : "#" + view);
      } catch (e) {
        /* ignore */
      }
    }
    loadView(view);
  }

  function bindNav() {
    document.querySelectorAll(".nav-item").forEach(function (n) {
      var go = function () {
        navTo(n.getAttribute("data-view"));
      };
      n.addEventListener("click", go);
      n.addEventListener("keydown", function (e) {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          go();
        }
      });
    });
    document.querySelectorAll("[data-nav]").forEach(function (el) {
      el.addEventListener("click", function () {
        navTo(el.getAttribute("data-nav"));
      });
    });
    var hash = (location.hash || "").replace("#", "");
    if (hash && VIEWS.indexOf(hash) >= 0 && canView(hash)) STATE.view = hash;
    window.addEventListener("hashchange", function () {
      var h = (location.hash || "").replace("#", "");
      navTo(h || "dashboard", false);
    });
  }

  function loadView(view) {
    if (view === "subsidiaries") return renderSubsidiaries();
    if (view === "reports") return renderReports();
    if (view === "financial") return renderFinancial();
    if (view === "support") return renderSupportView();
    if (view === "requests") return renderRequestsView();
    if (view === "approvals") return renderApprovalsView();
    if (view === "documents") return renderDocumentsView();
    if (view === "investments") return renderInvestments();
    if (view === "bi") return renderBi();
    if (view === "analytics") return renderAnalytics();
    if (view === "inbox") return renderInbox();
    if (view === "leads") return renderLeads();
    if (view === "employees") return renderEmployeesView();
    if (view === "operations") return renderOperationsView();
    if (view === "decisions") return renderDecisionsView();
    if (view === "projects") return renderProjectsView();
    if (view === "accounting") return renderAccountingView();
    if (view === "confidential") return renderConfidentialView();
    if (view === "admin") return renderAdmin();
    return Promise.resolve();
  }

  function ensureCompanies() {
    if (STATE.loaded.companies) return Promise.resolve(STATE.companies);
    if (!has("company.read")) return Promise.resolve([]);
    return get("/api/v1/companies")
      .then(function (rows) {
        STATE.companies = rows || [];
        STATE.loaded.companies = true;
        return STATE.companies;
      })
      .catch(function (err) {
        handleLoadError(err);
        return [];
      });
  }

  function ensureReports() {
    if (STATE.loaded.reports) return Promise.resolve(STATE.reports);
    if (!has("monthly_report.read_own") && !has("monthly_report.read_all")) {
      return Promise.resolve([]);
    }
    return get("/api/v1/monthly-reports")
      .then(function (rows) {
        STATE.reports = rows || [];
        STATE.loaded.reports = true;
        return STATE.reports;
      })
      .catch(function (err) {
        handleLoadError(err);
        return [];
      });
  }

  function ensureSupport() {
    if (STATE.loaded.support) return Promise.resolve(STATE.support);
    if (!has("support_request.read_own") && !has("support_request.read_all")) {
      return Promise.resolve([]);
    }
    return get("/api/v1/support-requests")
      .then(function (rows) {
        STATE.support = rows || [];
        STATE.loaded.support = true;
        return STATE.support;
      })
      .catch(function (err) {
        handleLoadError(err);
        return [];
      });
  }

  // ---- subsidiaries view ----------------------------------------------
  function renderSubsidiaries() {
    var host = byId("subsList");
    if (!host) return Promise.resolve();
    host.innerHTML = loadingHtml();
    return ensureReports().then(function () {
      return ensureCompanies();
    }).then(function (rows) {
      if (!rows.length) {
        host.innerHTML = emptyHtml("لا توجد شركات متاحة لك.", "No companies available to you.");
        return;
      }
      host.innerHTML = rows.map(subsidiaryCard).join("");
      host.querySelectorAll("[data-company]").forEach(function (card) {
        card.addEventListener("click", function () {
          openCompany(parseInt(card.getAttribute("data-company"), 10));
        });
      });
    });
  }

  function subsidiaryCard(c) {
    var rep = reportForCompany(c.id);
    var sector = sectorLabel(c.sector);
    var rev = rep ? money(rep.revenue) : null;
    return (
      '<div class="av-row" data-company="' + c.id + '" style="flex-direction:column;align-items:stretch;gap:9px">' +
      '<div style="display:flex;align-items:center;gap:11px">' +
      '<div class="co-dot" style="background:' + PALETTE[c.id % PALETTE.length] + ';width:34px;height:34px;border-radius:10px;font-size:14px">' + initial(c.name_ar) + "</div>" +
      '<div class="grow"><div class="t">' + escapeHtml(companyName(c)) + "</div>" +
      '<div class="s">' + dual(escapeHtml(sector.ar), escapeHtml(sector.en)) + " · " + escapeHtml(c.code) + "</div></div>" +
      healthBadge(c.health) +
      "</div>" +
      '<div style="display:flex;align-items:center;gap:10px;font-size:11px">' +
      '<span style="color:var(--ink-400)">' + dual("الإيرادات", "Revenue") + "</span>" +
      '<b style="font-family:var(--f-display);color:var(--navy-900)">' + (rev ? dual(rev.ar, rev.en) : dual("—", "—")) + "</b>" +
      '<span style="margin-inline-start:auto">' + (rep ? statusBadge(rep.status) : statusBadge(null)) + "</span>" +
      "</div></div>"
    );
  }

  function openCompany(id) {
    openModal({
      title: dual("تفاصيل الشركة", "Company details"),
      wide: true,
      body: loadingHtml(),
      onMount: function () {
        loadCompanyDetail(id);
      },
    });
  }

  function loadCompanyDetail(id) {
    var body = byId("modalBody");
    Promise.all([
      get("/api/v1/companies/" + id),
      ensureReports(),
      ensureSupport(),
    ])
      .then(function (res) {
        var c = res[0];
        if (!body) return;
        var sector = sectorLabel(c.sector);
        var reports = STATE.reports.filter(function (r) {
          return r.company_id === id;
        });
        var reqs = STATE.support.filter(function (r) {
          return r.company_id === id;
        });
        body.innerHTML =
          '<div class="kv">' +
          kv(dual("الكود", "Code"), escapeHtml(c.code)) +
          kv(dual("القطاع", "Sector"), dual(escapeHtml(sector.ar), escapeHtml(sector.en))) +
          kv(dual("الحالة", "Status"), escapeHtml(c.status)) +
          kv(dual("المؤشر", "Health"), healthBadge(c.health)) +
          kv(dual("البريد", "Contact"), escapeHtml(c.contact_email || "—")) +
          "</div>" +
          '<div class="sec-title">' + dual("التقارير الشهرية", "Monthly reports") + "</div>" +
          (reports.length
            ? '<div class="av-list">' + reports.map(reportRow).join("") + "</div>"
            : '<p class="av-empty">' + dual("لا توجد تقارير.", "No reports.") + "</p>") +
          '<div class="sec-title">' + dual("طلبات الدعم", "Support requests") + "</div>" +
          (reqs.length
            ? '<div class="av-list">' + reqs.map(supportRowCard).join("") + "</div>"
            : '<p class="av-empty">' + dual("لا توجد طلبات.", "No requests.") + "</p>");
        body.querySelectorAll("[data-report]").forEach(function (el) {
          el.addEventListener("click", function () {
            openReport(parseInt(el.getAttribute("data-report"), 10));
          });
        });
        body.querySelectorAll("[data-request]").forEach(function (el) {
          el.addEventListener("click", function () {
            openSupport(parseInt(el.getAttribute("data-request"), 10));
          });
        });
      })
      .catch(function (err) {
        if (body) body.innerHTML = errorHtml(errText(err));
      });
  }

  function kv(k, v) {
    return '<div><div class="k">' + k + '</div><div class="v">' + v + "</div></div>";
  }

  // ---- reports view ----------------------------------------------------
  function renderReports() {
    var host = byId("reportsList");
    if (!host) return Promise.resolve();
    host.innerHTML = loadingHtml();
    populateYearSelect();
    return ensureReports().then(function (rows) {
      var year = STATE.year;
      var status = byId("repStatus") ? byId("repStatus").value : "";
      var list = rows.filter(function (r) {
        if (year && r.period_year !== year) return false;
        if (status && r.status !== status) return false;
        return true;
      });
      if (!list.length) {
        host.innerHTML = emptyHtml("لا توجد تقارير مطابقة.", "No matching reports.");
        return;
      }
      list.sort(function (a, b) {
        return b.period_year * 12 + b.period_month - (a.period_year * 12 + a.period_month);
      });
      host.innerHTML = list.map(reportRow).join("");
      host.querySelectorAll("[data-report]").forEach(function (el) {
        el.addEventListener("click", function () {
          openReport(parseInt(el.getAttribute("data-report"), 10));
        });
      });
    });
  }

  function populateYearSelect() {
    var sel = byId("repYear");
    if (!sel) return;
    var years = {};
    STATE.reports.forEach(function (r) {
      years[r.period_year] = true;
    });
    if (STATE.year) years[STATE.year] = true;
    var list = Object.keys(years).map(Number).sort(function (a, b) {
      return b - a;
    });
    sel.innerHTML =
      '<option value="">' + dual("كل السنوات", "All years") + "</option>" +
      list.map(function (y) {
        return (
          '<option value="' + y + '"' + (y === STATE.year ? " selected" : "") + ">" +
          toArabicDigits(String(y)) + " / " + y + "</option>"
        );
      }).join("");
  }

  function reportRow(r) {
    var rev = money(r.revenue);
    var net = money(r.net_result);
    return (
      '<div class="av-row" data-report="' + r.id + '">' +
      '<div class="co-dot" style="background:' + PALETTE[r.company_id % PALETTE.length] + ';width:32px;height:32px;border-radius:9px">' + initial(r.company_name_ar) + "</div>" +
      '<div class="grow"><div class="t">' + escapeHtml(reportCompanyName(r)) + "</div>" +
      '<div class="s">' + dual(AR_MONTHS[r.period_month - 1] + " " + toArabicDigits(String(r.period_year)), EN_MONTHS[r.period_month - 1] + " " + r.period_year) +
      " · " + dual("الإيرادات ", "Revenue ") + '<b>' + dual(rev.ar, rev.en) + "</b>" +
      " · " + dual("الصافي ", "Net ") + '<b>' + dual(net.ar, net.en) + "</b></div></div>" +
      statusBadge(r.status) +
      "</div>"
    );
  }

  function openReport(id) {
    openModal({
      title: dual("تفاصيل التقرير الشهري", "Monthly report"),
      wide: true,
      body: loadingHtml(),
      onMount: function () {
        loadReportDetail(id);
      },
    });
  }

  function reportField(labelAr, labelEn, value) {
    if (value === null || value === undefined || value === "") return "";
    return (
      '<div class="note-block"><span class="lbl">' + dual(labelAr, labelEn) + "</span>" +
      escapeHtml(value) + "</div>"
    );
  }

  // ---- clarification thread (S02/S09) ----------------------------------
  // A clarification is linked to the report's *original*; it never edits the
  // figures or narrative. A holder of monthly_report.clarify may raise a
  // request or reply to one. The thread is shown inside the report modal.
  function clarificationBlock(c) {
    var isReply = c.kind === "reply";
    var who = escapeHtml(
      STATE.lang === "ar" ? c.author_name_ar || "—" : c.author_name_en || c.author_name_ar || "—",
    );
    return (
      '<div class="note-block" style="' +
      (isReply ? "margin-inline-start:22px;border-inline-start:3px solid var(--gold)" : "") +
      '"><span class="lbl">' +
      dual(isReply ? "رد" : "طلب إيضاح", isReply ? "Reply" : "Clarification") +
      " · " + who + " · " + fmtDateTime(c.created_at) + "</span>" +
      escapeHtml(c.body) +
      "</div>"
    );
  }

  function loadClarifications(reportId) {
    var host = byId("repClarify");
    if (!host) return;
    var canClarify = has("monthly_report.clarify");
    get("/api/v1/monthly-reports/" + reportId + "/clarifications")
      .then(function (rows) {
        rows = rows || [];
        var head =
          '<div class="sec-title">' +
          dual("الإيضاحات المرتبطة بالأصل", "Clarifications linked to the original") +
          "</div>";
        var body = rows.length
          ? rows.map(clarificationBlock).join("")
          : '<p class="av-empty">' +
            dual("لا توجد إيضاحات بعد.", "No clarifications yet.") +
            "</p>";
        var composer = canClarify
          ? '<div class="av-field"><textarea class="av-input" id="repClarifyBody" rows="2" placeholder="' +
            escAttr(STATE.lang === "ar" ? "اكتب إيضاحًا..." : "Write a clarification...") +
            '"></textarea><div class="pbtns" style="margin-top:8px">' +
            '<button type="button" class="btn-outline" id="repClarifySend">' +
            dual("طلب إيضاح", "Request clarification") +
            "</button></div></div>"
          : "";
        host.innerHTML = head + body + composer;
        var send = byId("repClarifySend");
        if (send) {
          send.addEventListener("click", function () {
            var field = byId("repClarifyBody");
            var text = field ? field.value.trim() : "";
            if (!text) {
              toast(STATE.lang === "ar" ? "الإيضاح مطلوب." : "A message is required.", "warn");
              return;
            }
            busy(send, true);
            post("/api/v1/monthly-reports/" + reportId + "/clarifications", {
              body: text,
              kind: "request",
            })
              .then(function () {
                toast(dual("أُرسل طلب الإيضاح.", "Clarification sent."), "ok");
                loadClarifications(reportId);
              })
              .catch(function (err) {
                toast(errText(err), "err");
                busy(send, false);
              });
          });
        }
      })
      .catch(function () {
        host.innerHTML = "";
      });
  }

  function loadReportDetail(id) {
    var body = byId("modalBody");
    get("/api/v1/monthly-reports/" + id)
      .then(function (r) {
        if (!body) return;
        var rev = money(r.revenue);
        var exp = money(r.expenses);
        var net = money(r.net_result);
        var rec = money(r.outstanding_receivables);
        var fr = r.financial_review;
        var canSubmit = has("monthly_report.submit") && (r.status === "draft" || r.status === "under_review");
        var canReview = has("financial_review.write") && r.status !== "draft";
        var canDelete = has("monthly_report.delete") && r.status === "draft";

        body.innerHTML =
          '<div class="kv">' +
          kv(dual("الشركة", "Company"), escapeHtml(reportCompanyName(r))) +
          kv(dual("الفترة", "Period"), dual(AR_MONTHS[r.period_month - 1] + " " + toArabicDigits(String(r.period_year)), EN_MONTHS[r.period_month - 1] + " " + r.period_year)) +
          kv(dual("الحالة", "Status"), statusBadge(r.status)) +
          kv(dual("آخر تحديث", "Last update"), fmtDateTime(r.updated_at)) +
          "</div>" +
          '<div class="sec-title">' + dual("المؤشرات المالية", "Financials") + "</div>" +
          '<div class="kv">' +
          kv(dual("الإيرادات", "Revenue"), dual(rev.ar, rev.en)) +
          kv(dual("المصروفات", "Expenses"), dual(exp.ar, exp.en)) +
          kv(dual("صافي النتيجة", "Net result"), dual(net.ar, net.en)) +
          kv(dual("الذمم المدينة", "Receivables"), dual(rec.ar, rec.en)) +
          "</div>" +
          (r.important_developments || r.major_problems || r.new_opportunities || r.support_required || r.management_notes
            ? '<div class="sec-title">' + dual("ملاحظات الشركة", "Company notes") + "</div>" +
              reportField("أهم التطورات", "Developments", r.important_developments) +
              reportField("عملاء جدد", "New customers", r.new_customers) +
              reportField("فرص جديدة", "New opportunities", r.new_opportunities) +
              reportField("مشاكل رئيسية", "Major problems", r.major_problems) +
              reportField("الدعم المطلوب", "Support required", r.support_required) +
              reportField("ملاحظات الإدارة", "Management notes", r.management_notes)
            : "") +
          (r.attachments && r.attachments.length
            ? '<div class="sec-title">' + dual("المرفقات", "Attachments") + "</div>" +
              r.attachments.map(function (a) {
                return '<div class="note-block">' + escapeHtml(a.original_filename) +
                  " · " + dual(plainNum(a.size_bytes) + " بايت", plainNum(a.size_bytes) + " bytes") + "</div>";
              }).join("")
            : "") +
          (fr
            ? '<div class="sec-title">' + dual("المراجعة المالية", "Financial review") + "</div>" +
              '<div class="kv">' +
              kv(dual("الحالة", "Status"), escapeHtml(fr.status)) +
              kv(dual("دقيق ماليًا", "Accurate"), fr.is_financially_accurate ? dual("نعم", "Yes") : dual("لا", "No")) +
              kv(dual("إيرادات موثقة", "Verified revenue"), dual(money(fr.verified_revenue).ar, money(fr.verified_revenue).en)) +
              kv(dual("صافي موثق", "Verified net"), dual(money(fr.verified_net_result).ar, money(fr.verified_net_result).en)) +
              "</div>" +
              (fr.financial_notes ? reportField("ملاحظات", "Notes", fr.financial_notes) : "") +
              (fr.flagged_reason ? reportField("سبب التحفظ", "Flag reason", fr.flagged_reason) : "")
            : "") +
          '<div id="repClarify"></div>' +
          '<div id="repActions" class="modal-foot" style="margin-top:14px;border-radius:12px;border:1px solid var(--line-2)"></div>';

        loadClarifications(id);

        var actions = byId("repActions");
        var btns = [];
        if (canSubmit) {
          btns.push('<button class="btn-solid" id="repSubmit">' + dual("إرسال للقابضة", "Submit to Holding") + "</button>");
        }
        if (canReview) {
          btns.push('<button class="btn-solid gold" id="repReview">' + dual("مراجعة مالية", "Financial review") + "</button>");
        }
        if (canDelete) {
          btns.push('<button class="btn-solid danger" id="repDelete">' + dual("حذف المسودة", "Delete draft") + "</button>");
        }
        btns.push('<button class="btn-outline" id="repClose">' + dual("إغلاق", "Close") + "</button>");
        if (actions) actions.innerHTML = btns.join("");

        if (byId("repClose")) byId("repClose").addEventListener("click", closeModal);
        if (byId("repSubmit")) byId("repSubmit").addEventListener("click", function () { submitReport(id, this); });
        if (byId("repReview")) byId("repReview").addEventListener("click", function () { financialReviewForm(id); });
        if (byId("repDelete")) byId("repDelete").addEventListener("click", function () { deleteReport(id, this); });
      })
      .catch(function (err) {
        if (body) body.innerHTML = errorHtml(errText(err));
      });
  }

  function submitReport(id, btn) {
    confirmDialog({
      title: dual("إرسال التقرير", "Submit report"),
      message: STATE.lang === "ar"
        ? "سيتم إرسال التقرير إلى القابضة ولا يمكن تعديله بعد ذلك."
        : "The report will be sent to the Holding and can no longer be edited.",
      confirmLabel: dual("إرسال", "Submit"),
    }).then(function (ok) {
      if (!ok) return;
      busy(btn, true);
      post("/api/v1/monthly-reports/" + id + "/submit")
        .then(function () {
          toast(STATE.lang === "ar" ? "تم إرسال التقرير بنجاح." : "Report submitted.", "ok");
          refreshAll().then(function () { openReport(id); });
        })
        .catch(function (err) {
          toast(errText(err), "err");
          busy(btn, false);
        });
    });
  }

  function deleteReport(id, btn) {
    confirmDialog({
      title: dual("حذف المسودة", "Delete draft"),
      message: STATE.lang === "ar" ? "سيتم حذف هذه المسودة نهائيًا." : "This draft will be permanently deleted.",
      confirmLabel: dual("حذف", "Delete"),
      danger: true,
    }).then(function (ok) {
      if (!ok) return;
      busy(btn, true);
      api.del("/api/v1/monthly-reports/" + id)
        .then(function () {
          toast(STATE.lang === "ar" ? "تم حذف المسودة." : "Draft deleted.", "ok");
          closeModal();
          refreshAll().then(function () { loadView(STATE.view); });
        })
        .catch(function (err) {
          toast(errText(err), "err");
          busy(btn, false);
        });
    });
  }

  function financialReviewForm(id) {
    var r = null;
    for (var i = 0; i < STATE.reports.length; i++) {
      if (STATE.reports[i].id === id) r = STATE.reports[i];
    }
    var rev = r ? r.revenue : "";
    var exp = r ? r.expenses : "";
    var net = r ? r.net_result : "";
    openModal({
      title: dual("المراجعة المالية", "Financial review"),
      body:
        '<div class="av-field"><label>' + dual("إيرادات موثقة", "Verified revenue") + '</label><input class="av-input" id="frRev" style="width:100%" value="' + escAttr(rev || "") + '"></div>' +
        '<div class="av-field"><label>' + dual("مصروفات موثقة", "Verified expenses") + '</label><input class="av-input" id="frExp" style="width:100%" value="' + escAttr(exp || "") + '"></div>' +
        '<div class="av-field"><label>' + dual("صافي موثق", "Verified net") + '</label><input class="av-input" id="frNet" style="width:100%" value="' + escAttr(net || "") + '"></div>' +
        '<div class="av-field"><label>' + dual("ملاحظات", "Notes") + '</label><textarea class="av-textarea" id="frNotes"></textarea></div>' +
        '<div class="av-field"><label><input type="checkbox" id="frAccurate" checked> ' + dual("البيانات دقيقة ماليًا", "Financial data is accurate") + "</label></div>" +
        '<div class="av-field" id="frFlagWrap" style="display:none"><label>' + dual("سبب التحفظ", "Reason for flag") + '</label><input class="av-input" id="frFlag" style="width:100%"></div>',
      footer:
        '<button class="btn-outline" id="frCancel">' + dual("إلغاء", "Cancel") + "</button>" +
        '<button class="btn-solid gold" id="frSave">' + dual("حفظ المراجعة", "Save review") + "</button>",
      onMount: function (root) {
        root.querySelector("#frCancel").addEventListener("click", closeModal);
        root.querySelector("#frAccurate").addEventListener("change", function () {
          root.querySelector("#frFlagWrap").style.display = this.checked ? "none" : "";
        });
        root.querySelector("#frSave").addEventListener("click", function () {
          var btn = this;
          var accurate = root.querySelector("#frAccurate").checked;
          var payload = {
            is_financially_accurate: accurate,
            verified_revenue: numOrNull(root.querySelector("#frRev").value),
            verified_expenses: numOrNull(root.querySelector("#frExp").value),
            verified_net_result: numOrNull(root.querySelector("#frNet").value),
            financial_notes: root.querySelector("#frNotes").value || null,
          };
          if (!accurate) {
            payload.flagged_reason = root.querySelector("#frFlag").value || null;
            if (!payload.flagged_reason) {
              toast(STATE.lang === "ar" ? "سبب التحفظ مطلوب." : "A reason is required.", "err");
              return;
            }
          }
          busy(btn, true);
          post("/api/v1/monthly-reports/" + id + "/financial-review", payload)
            .then(function () {
              toast(STATE.lang === "ar" ? "تم حفظ المراجعة المالية." : "Financial review saved.", "ok");
              refreshAll().then(function () { openReport(id); });
            })
            .catch(function (err) {
              toast(errText(err), "err");
              busy(btn, false);
            });
        });
      },
    });
  }

  function numOrNull(v) {
    if (v === "" || v === null || v === undefined) return null;
    var n = Number(v);
    return isNaN(n) ? null : n;
  }
  // ---- financial summary view (Execution 02) ---------------------------
  // Bilingual (AR/EN) financial summary, accountant approval and historical
  // correction, laid out with the shared dual-language + RTL/LTR pattern.

  var FIN_STATUS = {
    draft: { ar: "مسودة", en: "Draft", cls: "miss" },
    submitted: { ar: "للمراجعة", en: "For review", cls: "late" },
    correction_required: { ar: "مطلوب تصحيح", en: "Correction required", cls: "danger" },
    approved: { ar: "معتمد", en: "Approved", cls: "ok" },
    missing: { ar: "لا يوجد ملخص", en: "No summary", cls: "miss" },
  };

  function finStatusBadge(status) {
    var s = FIN_STATUS[status] || { ar: status, en: status, cls: "miss" };
    return '<span class="status ' + s.cls + '"><i></i>' + dual(s.ar, s.en) + "</span>";
  }

  function finMoneyAr(value) {
    return money(value).ar;
  }

  function finMoneyEn(value) {
    return money(value).en;
  }

  // Locale-aware money for the active language. The previous code always used
  // the Arabic form (Arabic-Indic digits + ر.س), so the English view rendered
  // Arabic numerals; this routes through the active language instead.
  function finMoney(value) {
    return STATE.lang === "ar" ? finMoneyAr(value) : finMoneyEn(value);
  }

  function finPeriodQuery() {
    var y = STATE.year || new Date().getFullYear();
    var m = STATE.month || new Date().getMonth() + 1;
    return "year=" + y + "&month=" + m;
  }

  function renderFinancial() {
    var host = byId("financialList");
    if (!host) return Promise.resolve();
    host.innerHTML = loadingHtml();
    bindFinancialToolbar();
    return ensureCompanies().then(function () {
      populateFinCompanySelect();
      return Promise.all([
        get("/api/v1/financial/report?" + finPeriodQuery()),
        has("financial_item.manage")
          ? get("/api/v1/financial/item-definitions").catch(function () { return []; })
          : Promise.resolve([]),
      ]);
    }).then(function (res) {
      var report = res[0];
      var definitions = res[1] || [];
      var rows = (report && report.companies) || [];
      if (!rows.length) {
        host.innerHTML = emptyHtml("لا توجد شركات متاحة لك.", "No companies available to you.");
        return;
      }
      var totals = report.totals || {};
      host.innerHTML =
        finTotalsStrip(totals, report.counts || {}) +
        rows.map(finRow).join("") +
        finDefinitionsPanel(definitions);
      host.querySelectorAll("[data-fin-period]").forEach(function (el) {
        el.addEventListener("click", function () {
          finOpenPeriod(parseInt(el.getAttribute("data-fin-period"), 10));
        });
      });
      var defForm = byId("finDefForm");
      if (defForm) {
        defForm.addEventListener("submit", function (ev) {
          ev.preventDefault();
          finCreateDefinition(defForm);
        });
      }
    }).catch(function (err) {
      handleLoadError(err);
      host.innerHTML = errorHtml(errText(err));
    });
  }

  function finDefinitionsPanel(definitions) {
    if (!has("financial_item.manage")) return "";
    var list = definitions.length
      ? '<div class="av-list">' + definitions.map(function (d) {
          return '<div class="av-row" style="cursor:default"><div class="grow"><div class="t">' +
            dual(escapeHtml(d.name_ar), escapeHtml(d.name_en)) + "</div>" +
            '<div class="s">' + escapeHtml(d.code) + " · " + escapeHtml(d.kind) +
            (d.is_active ? "" : " · " + dual("غير مفعّل", "inactive")) + "</div></div>" +
            (d.note_mandatory ? '<span class="status warn"><i></i>' + dual("ملاحظة إلزامية", "Note required") + "</span>" : "") +
            "</div>";
        }).join("") + "</div>"
      : noticeHtml("لا توجد بنود معرّفة بعد.", "No item definitions yet.");
    var form =
      '<form class="av-form av-form-inline" id="finDefForm">' +
      field("الشركة", "Company", selectInput("fdCompany", companySelectOptions(false), STATE.companies.length ? STATE.companies[0].id : "")) +
      field("الكود", "Code", textInput("fdCode", "")) +
      field("الاسم (عربي)", "Name (AR)", textInput("fdNameAr", "")) +
      field("الاسم (إنجليزي)", "Name (EN)", textInput("fdNameEn", "")) +
      field("النوع", "Kind", selectInput("fdKind", [
        { value: "expense", label: opt("مصروف", "Expense") },
        { value: "revenue", label: opt("إيراد", "Revenue") },
        { value: "other", label: opt("أخرى", "Other") },
      ], "expense")) +
      field("ملاحظة إلزامية؟", "Note mandatory?", selectInput("fdNote", [
        { value: "0", label: opt("لا", "No") },
        { value: "1", label: opt("نعم", "Yes") },
      ], "0")) +
      '<div class="av-form-actions"><button class="btn-solid" type="submit">' +
      dual("إضافة بند", "Add item") + "</button></div></form>";
    return panel("بنود مالية خاصة (F-04)", "Special financial items (F-04)",
      '<p class="note-block">' + dual("البنود المعرّفة تُستخدم في الملخصات الشهرية؛ البند ذو الملاحظة الإلزامية يفرض إدخال سبب.", "Defined items feed the monthly summaries; a note-mandatory item forces a reason.") + "</p>" +
      form + list);
  }

  function finCreateDefinition(form) {
    var btn = form.querySelector("button");
    busy(btn, true);
    post("/api/v1/financial/item-definitions?company_id=" + parseInt(valOf("fdCompany"), 10), {
      code: valOf("fdCode"),
      name_ar: valOf("fdNameAr"),
      name_en: valOf("fdNameEn"),
      kind: valOf("fdKind"),
      note_mandatory: valOf("fdNote") === "1",
    }).then(function () {
      toast(dual("تمت إضافة البند.", "Item added."), "ok");
      return renderFinancial();
    }).catch(function (err) { domainError(err); busy(btn, false); });
  }

  function finTotalsStrip(totals, counts) {
    return (
      '<div class="perm-summary" style="margin-bottom:14px">' +
      '<div><div class="pnum">' + plainNum(counts.approved || 0) + '</div><div class="plabel">' +
      dual("ملخصات معتمدة", "approved summaries") + "</div></div>" +
      '<div class="psep"></div>' +
      '<div><div class="pnum">' + finMoney(totals.effective_revenue) + '</div><div class="plabel">' +
      dual("الإيرادات الفعلية", "effective revenue") + "</div></div>" +
      '<div class="psep"></div>' +
      '<div><div class="pnum">' + finMoney(totals.effective_expenses) + '</div><div class="plabel">' +
      dual("المصروفات الفعلية", "effective expenses") + "</div></div>" +
      '<div class="psep"></div>' +
      '<div><div class="pnum">' + finMoney(totals.calculated_result) + '</div><div class="plabel">' +
      dual("النتيجة", "result") + "</div></div>" +
      "</div>"
    );
  }

  function finRow(r) {
    var eff = r.is_effective
      ? finMoney(r.calculated_result)
      : dual("—", "—");
    var versionTag = r.version_number
      ? '<span class="perm-badge">' + dual("نسخة", "v") + " " + plainNum(r.version_number) + "</span>"
      : "";
    var clickable = r.period_id
      ? ' data-fin-period="' + r.period_id + '" style="cursor:pointer"'
      : "";
    var cta = r.period_id
      ? dual("عرض", "Open")
      : dual("إنشاء", "Create");
    return (
      '<div class="av-row"' + clickable + ">" +
      '<div class="co-dot" style="background:' + PALETTE[r.company_id % PALETTE.length] +
      ';width:32px;height:32px;border-radius:9px">' + initial(r.company_name_ar) + "</div>" +
      '<div class="grow"><div class="t">' + escapeHtml(finCompanyName(r)) + " " + versionTag + "</div>" +
      '<div class="s">' + dual("الإيرادات ", "Revenue ") + "<b>" + finMoney(r.effective_revenue) + "</b>" +
      " · " + dual("المصروفات ", "Expenses ") + "<b>" + finMoney(r.effective_expenses) + "</b>" +
      " · " + dual("النتيجة ", "Result ") + "<b>" + eff + "</b></div></div>" +
      finStatusBadge(r.status) +
      '<span class="perm-badge" style="margin-inline-start:8px">' + cta + "</span>" +
      "</div>"
    );
  }

  function finCompanyName(r) {
    return STATE.lang === "ar"
      ? r.company_name_ar || r.company_name_en || ""
      : r.company_name_en || r.company_name_ar || "";
  }

  function bindFinancialToolbar() {
    if (STATE.finBound) return;
    STATE.finBound = true;
    var refresh = byId("finRefresh");
    if (refresh) refresh.addEventListener("click", function () { renderFinancial(); });
    var create = byId("finNew");
    if (create) {
      create.classList.toggle("perm-hidden", !has("financial_summary.create"));
      create.addEventListener("click", finNewModal);
    }
  }

  function populateFinCompanySelect() {
    var sel = byId("finCompany");
    if (!sel) return;
    var current = sel.value;
    sel.innerHTML =
      '<option value="">' + dual("كل الشركات", "All companies") + "</option>" +
      (STATE.companies || []).map(function (c) {
        return '<option value="' + c.id + '">' + escapeHtml(companyName(c)) + "</option>";
      }).join("");
    if (current) sel.value = current;
  }

  // -- create -------------------------------------------------------------
  function finNewModal() {
    var companies = STATE.companies || [];
    if (!companies.length) {
      toast(STATE.lang === "ar" ? "لا توجد شركات متاحة." : "No companies available.", "warn");
      return;
    }
    var y = STATE.year || new Date().getFullYear();
    var m = STATE.month || new Date().getMonth() + 1;
    var opts = companies.map(function (c) {
      return '<option value="' + c.id + '">' + escapeHtml(companyName(c)) + "</option>";
    }).join("");
    openModal({
      title: dual("ملخص مالي جديد", "New financial summary"),
      body:
        '<div class="av-field"><label>' + dual("الشركة", "Company") + '</label><select class="av-select" id="finC" style="width:100%">' + opts + "</select></div>" +
        '<div class="av-field"><label>' + dual("السنة", "Year") + '</label><input class="av-input" id="finY" type="number" value="' + y + '" style="width:100%"></div>' +
        '<div class="av-field"><label>' + dual("الشهر", "Month") + '</label><input class="av-input" id="finM" type="number" min="1" max="12" value="' + m + '" style="width:100%"></div>' +
        '<div class="av-field"><label>' + dual("الإيرادات المدخلة", "Entered revenue") + '</label><input class="av-input" id="finRev" type="number" step="0.01" style="width:100%"></div>' +
        '<div class="av-field"><label>' + dual("المصروفات المدخلة", "Entered expenses") + '</label><input class="av-input" id="finExp" type="number" step="0.01" style="width:100%"></div>' +
        '<div class="av-field"><label>' + dual("رصيد البنك الختامي", "Closing bank balance") + '</label><input class="av-input" id="finBank" type="number" step="0.01" style="width:100%"></div>' +
        '<div class="av-field"><label>' + dual("رصيد النقد الختامي", "Closing cash balance") + '</label><input class="av-input" id="finCash" type="number" step="0.01" style="width:100%"></div>',
      footer:
        '<button class="btn-outline" id="finCancel">' + dual("إلغاء", "Cancel") + "</button>" +
        '<button class="btn-solid" id="finCreate">' + dual("إنشاء", "Create") + "</button>",
      onMount: function () {
        byId("finCancel").addEventListener("click", closeModal);
        byId("finCreate").addEventListener("click", function () { finCreate(this); });
      },
    });
  }

  function finCreate(btn) {
    var body = {
      company_id: parseInt(byId("finC").value, 10),
      period_year: parseInt(byId("finY").value, 10),
      period_month: parseInt(byId("finM").value, 10),
      submitted_revenue: numOrNull(byId("finRev").value),
      submitted_expenses: numOrNull(byId("finExp").value),
      closing_bank_balance: numOrNull(byId("finBank").value),
      closing_cash_balance: numOrNull(byId("finCash").value),
    };
    busy(btn, true);
    post("/api/v1/financial/summaries", body)
      .then(function (v) {
        toast(STATE.lang === "ar" ? "أُنشئ الملخص." : "Summary created.", "ok");
        closeModal();
        renderFinancial().then(function () { finOpenPeriod(v.period_id); });
      })
      .catch(function (err) { toast(errText(err), "err"); busy(btn, false); });
  }

  // -- detail -------------------------------------------------------------
  function finOpenPeriod(periodId) {
    openModal({
      title: dual("تفاصيل الملخص المالي", "Financial summary"),
      wide: true,
      body: loadingHtml(),
      onMount: function () { finLoadPeriod(periodId); },
    });
  }

  function finLoadPeriod(periodId) {
    var body = byId("modalBody");
    get("/api/v1/financial/periods/" + periodId)
      .then(function (p) {
        if (!body) return;
        var versions = (p.versions || []).slice().sort(function (a, b) {
          return b.version_number - a.version_number;
        });
        if (!versions.length) {
          body.innerHTML = emptyHtml("لا توجد نسخ.", "No versions.");
          return;
        }
        var v = versions[0];
        body.innerHTML = finPeriodHtml(p, versions, v);
        finBindPeriodActions(p, v);
      })
      .catch(function (err) {
        if (body) body.innerHTML = errorHtml(errText(err));
      });
  }

  function finPeriodHtml(p, versions, v) {
    var versionChips = versions.map(function (x) {
      return '<button type="button" class="perm-cat-chip' + (x.id === v.id ? " on" : "") +
        '" data-fin-version="' + x.id + '">' +
        dual("نسخة " + toArabicDigits(String(x.version_number)), "v" + x.version_number) + "</button>";
    }).join("");
    var items = (v.items || []).map(function (it) {
      var rule = it.inclusion_rule === "added"
        ? dual("مضاف", "Added") : dual("مشمول", "Included");
      var kind = { revenue: dual("إيراد", "Revenue"), expense: dual("مصروف", "Expense"), other: dual("أخرى", "Other") }[it.kind] || dual(it.kind, it.kind);
      return (
        '<div class="av-row"><div class="grow"><div class="t">' +
        dual(escapeHtml(it.name_ar), escapeHtml(it.name_en)) + "</div>" +
        '<div class="s">' + kind + " · " + rule +
        (it.decision_reference ? " · " + escapeHtml(it.decision_reference) : "") + "</div></div>" +
        "<b>" + finMoney(it.amount) + "</b>" +
        (finCanEdit(v)
          ? '<button class="btn-outline" data-fin-delitem="' + it.id + '" style="margin-inline-start:8px">×</button>'
          : "") +
        "</div>"
      );
    }).join("") || emptyHtml("لا توجد بنود خاصة.", "No special items.");

    var bank = (v.bank_attachments || []).map(function (a) {
      return (
        '<div class="av-row"><div class="grow"><div class="t">' + escapeHtml(a.original_filename) + "</div>" +
        '<div class="s">' + dual(plainNum(a.size_bytes) + " بايت", plainNum(a.size_bytes) + " bytes") + "</div></div>" +
        '<button class="btn-outline" data-fin-bank="' + a.id + '">' + dual("تنزيل", "Download") + "</button></div>"
      );
    }).join("") || emptyHtml("لا يوجد كشف بنك بعد.", "No bank statement yet.");

    return (
      '<div class="kv">' +
      kv(dual("الشركة", "Company"), escapeHtml(STATE.lang === "ar" ? p.company_name_ar : p.company_name_en)) +
      kv(dual("الفترة", "Period"), dual(AR_MONTHS[p.period_month - 1] + " " + p.period_year, EN_MONTHS[p.period_month - 1] + " " + p.period_year)) +
      kv(dual("الحالة", "Status"), finStatusBadge(v.status)) +
      kv(dual("العملة", "Currency"), escapeHtml(v.currency)) +
      "</div>" +
      '<div class="perm-toolbar"><div class="perm-cats">' + versionChips + "</div></div>" +
      (v.corrects_version_id
        ? '<p class="perm-code">' + dual("نسخة تصحيح مرتبطة بنسخة سابقة.", "Corrective version linked to a prior version.") + "</p>"
        : "") +
      (v.return_note
        ? '<div class="note-block"><span class="lbl">' + dual("ملاحظة التصحيح", "Correction note") + "</span>" + escapeHtml(v.return_note) + "</div>"
        : "") +
      '<div class="sec-title">' + dual("المؤشرات المالية", "Financials") + "</div>" +
      '<div class="kv">' +
      kv(dual("الإيرادات المدخلة", "Entered revenue"), dual(finMoneyAr(v.submitted_revenue), finMoneyEn(v.submitted_revenue))) +
      kv(dual("الإيرادات الفعلية", "Effective revenue"), dual(finMoneyAr(v.effective_revenue), finMoneyEn(v.effective_revenue))) +
      kv(dual("المصروفات المدخلة", "Entered expenses"), dual(finMoneyAr(v.submitted_expenses), finMoneyEn(v.submitted_expenses))) +
      kv(dual("المصروفات الفعلية", "Effective expenses"), dual(finMoneyAr(v.effective_expenses), finMoneyEn(v.effective_expenses))) +
      kv(dual("النتيجة", "Result"), dual(finMoneyAr(v.calculated_result), finMoneyEn(v.calculated_result))) +
      kv(dual("إجمالي النقد", "Total cash"), dual(finMoneyAr(v.calculated_total_cash), finMoneyEn(v.calculated_total_cash))) +
      kv(dual("الذمم المدينة", "Receivables"), dual(finMoneyAr(v.customer_receivables), finMoneyEn(v.customer_receivables))) +
      "</div>" +
      '<div class="sec-title">' + dual("البنود الخاصة", "Special items") + "</div>" +
      '<div id="finItems">' + items + "</div>" +
      (finCanEdit(v)
        ? '<div class="av-toolbar" style="margin-top:8px;flex-wrap:wrap;gap:6px">' +
          '<input class="av-input" id="finItemName" placeholder="' + escAttr(STATE.lang === "ar" ? "اسم البند" : "Item name") + '">' +
          '<select class="av-select" id="finItemKind">' +
          '<option value="expense">' + dual("مصروف", "Expense") + "</option>" +
          '<option value="revenue">' + dual("إيراد", "Revenue") + "</option>" +
          '<option value="other">' + dual("أخرى", "Other") + "</option></select>" +
          '<select class="av-select" id="finItemRule">' +
          '<option value="added">' + dual("مضاف", "Added") + "</option>" +
          '<option value="included">' + dual("مشمول", "Included") + "</option></select>" +
          '<input class="av-input" id="finItemAmount" type="number" step="0.01" style="max-width:130px" placeholder="' + escAttr(STATE.lang === "ar" ? "المبلغ" : "Amount") + '">' +
          '<button class="btn-outline" id="finAddItem">' + dual("إضافة", "Add") + "</button></div>"
        : "") +
      '<div class="sec-title">' + dual("كشف البنك", "Bank statement") + "</div>" +
      '<div id="finBank">' + bank + "</div>" +
      (finCanEdit(v)
        ? '<div class="av-toolbar" style="margin-top:8px"><input type="file" id="finBankFile"><button class="btn-outline" id="finUploadBank">' +
          dual("رفع كشف البنك", "Upload statement") + "</button></div>"
        : "") +
      '<div id="finActions" class="modal-foot" style="margin-top:14px;border-radius:12px;border:1px solid var(--line-2)"></div>'
    );
  }

  function finCanEdit(v) {
    return (v.status === "draft" || v.status === "correction_required") &&
      has("financial_summary.update");
  }

  function finBindPeriodActions(p, v) {
    var body = byId("modalBody");
    var actions = byId("finActions");
    if (!actions) return;
    var btns = [];
    if (finCanEdit(v) && has("financial_summary.submit")) {
      btns.push('<button class="btn-solid" id="finSubmit">' + dual("إرسال للمراجعة", "Submit for review") + "</button>");
    }
    if (v.status === "submitted" && has("financial_review.act")) {
      btns.push('<button class="btn-solid gold" id="finApprove">' + dual("اعتماد", "Approve") + "</button>");
      btns.push('<button class="btn-solid danger" id="finReturn">' + dual("إرجاع للتصحيح", "Return for correction") + "</button>");
    }
    if (v.status === "approved" && has("financial_summary.correct")) {
      btns.push('<button class="btn-solid" id="finCorrect">' + dual("إنشاء نسخة تصحيحية", "Create corrective version") + "</button>");
    }
    btns.push('<button class="btn-outline" id="finClose">' + dual("إغلاق", "Close") + "</button>");
    actions.innerHTML = btns.join("");

    if (byId("finClose")) byId("finClose").addEventListener("click", closeModal);
    if (byId("finSubmit")) byId("finSubmit").addEventListener("click", function () { finSubmit(p, v, this); });
    if (byId("finApprove")) byId("finApprove").addEventListener("click", function () { finApprove(p, v, this); });
    if (byId("finReturn")) byId("finReturn").addEventListener("click", function () { finReturn(p, v, this); });
    if (byId("finCorrect")) byId("finCorrect").addEventListener("click", function () { finCorrect(p, v, this); });
    if (byId("finAddItem")) byId("finAddItem").addEventListener("click", function () { finAddItem(v, this); });
    if (byId("finUploadBank")) byId("finUploadBank").addEventListener("click", function () { finUploadBank(v, this); });

    if (body) {
      body.querySelectorAll("[data-fin-version]").forEach(function (el) {
        el.addEventListener("click", function () {
          var vid = parseInt(el.getAttribute("data-fin-version"), 10);
          var chosen = (p.versions || []).filter(function (x) { return x.id === vid; })[0];
          if (!chosen) return;
          body.innerHTML = finPeriodHtml(p, p.versions.slice().sort(function (a, b) { return b.version_number - a.version_number; }), chosen);
          finBindPeriodActions(p, chosen);
        });
      });
      body.querySelectorAll("[data-fin-delitem]").forEach(function (el) {
        el.addEventListener("click", function () {
          finRemoveItem(p, v, parseInt(el.getAttribute("data-fin-delitem"), 10));
        });
      });
      body.querySelectorAll("[data-fin-bank]").forEach(function (el) {
        el.addEventListener("click", function () {
          finDownloadBank(v, parseInt(el.getAttribute("data-fin-bank"), 10));
        });
      });
    }
  }

  function finReload(p) {
    closeModal();
    renderFinancial().then(function () { finOpenPeriod(p.id); });
  }

  function finSubmit(p, v, btn) {
    confirmDialog({
      title: dual("إرسال الملخص", "Submit summary"),
      message: STATE.lang === "ar"
        ? "سيُرسل الملخص إلى المحاسب، ويلزم وجود كشف بنك."
        : "The summary will be sent to the accountant; a bank statement is required.",
      confirmLabel: dual("إرسال", "Submit"),
    }).then(function (ok) {
      if (!ok) return;
      busy(btn, true);
      post("/api/v1/financial/summaries/" + v.id + "/submit")
        .then(function () { toast(STATE.lang === "ar" ? "أُرسل الملخص." : "Submitted.", "ok"); finReload(p); })
        .catch(function (err) { toast(errText(err), "err"); busy(btn, false); });
    });
  }

  function finApprove(p, v, btn) {
    confirmDialog({
      title: dual("اعتماد الملخص", "Approve summary"),
      message: STATE.lang === "ar" ? "سيصبح هذا الملخص النسخة الفعّالة للفترة." : "This summary becomes the effective version for the period.",
      confirmLabel: dual("اعتماد", "Approve"),
    }).then(function (ok) {
      if (!ok) return;
      busy(btn, true);
      post("/api/v1/financial/summaries/" + v.id + "/approve")
        .then(function () { toast(STATE.lang === "ar" ? "اعتُمد الملخص." : "Approved.", "ok"); finReload(p); })
        .catch(function (err) { toast(errText(err), "err"); busy(btn, false); });
    });
  }

  function finReturn(p, v, btn) {
    openModal({
      title: dual("إرجاع للتصحيح", "Return for correction"),
      body:
        '<div class="av-field"><label>' + dual("ملاحظة إلزامية", "Mandatory note") + '</label>' +
        '<textarea class="av-textarea" id="finRetNote" style="width:100%"></textarea></div>',
      footer:
        '<button class="btn-outline" id="finRetCancel">' + dual("إلغاء", "Cancel") + "</button>" +
        '<button class="btn-solid danger" id="finRetGo">' + dual("إرجاع", "Return") + "</button>",
      onMount: function () {
        byId("finRetCancel").addEventListener("click", closeModal);
        byId("finRetGo").addEventListener("click", function () {
          var note = (byId("finRetNote").value || "").trim();
          if (!note) { toast(STATE.lang === "ar" ? "الملاحظة مطلوبة." : "A note is required.", "warn"); return; }
          busy(this, true);
          post("/api/v1/financial/summaries/" + v.id + "/return", { note: note })
            .then(function () { toast(STATE.lang === "ar" ? "أُعيد للتصحيح." : "Returned.", "ok"); finReload(p); })
            .catch(function (err) { toast(errText(err), "err"); busy(this, false); }.bind(this));
        });
      },
    });
    void btn;
  }

  function finCorrect(p, v, btn) {
    busy(btn, true);
    post("/api/v1/financial/periods/" + p.id + "/corrections")
      .then(function () { toast(STATE.lang === "ar" ? "أُنشئت نسخة تصحيحية." : "Corrective version created.", "ok"); finReload(p); })
      .catch(function (err) { toast(errText(err), "err"); busy(btn, false); });
  }

  function finAddItem(v, btn) {
    var name = (byId("finItemName").value || "").trim();
    var amount = numOrNull(byId("finItemAmount").value);
    if (!name) { toast(STATE.lang === "ar" ? "اسم البند مطلوب." : "An item name is required.", "warn"); return; }
    if (amount === null) { toast(STATE.lang === "ar" ? "المبلغ مطلوب." : "An amount is required.", "warn"); return; }
    busy(btn, true);
    post("/api/v1/financial/summaries/" + v.id + "/items", {
      name_ar: name, name_en: name, amount: amount,
      kind: (byId("finItemKind") && byId("finItemKind").value) || "expense",
      inclusion_rule: (byId("finItemRule") && byId("finItemRule").value) || "added",
    })
      .then(function () { finReload({ id: v.period_id }); })
      .catch(function (err) { toast(errText(err), "err"); busy(btn, false); });
  }

  function finRemoveItem(p, v, itemId) {
    api.del("/api/v1/financial/summaries/" + v.id + "/items/" + itemId)
      .then(function () { finReload(p); })
      .catch(function (err) { toast(errText(err), "err"); });
  }

  function finUploadBank(v, btn) {
    var input = byId("finBankFile");
    var file = input && input.files && input.files[0];
    if (!file) { toast(STATE.lang === "ar" ? "اختر ملفًا." : "Choose a file.", "warn"); return; }
    busy(btn, true);
    api.upload("/api/v1/financial/summaries/" + v.id + "/bank-statement", file)
      .then(function () { toast(STATE.lang === "ar" ? "رُفع كشف البنك." : "Bank statement uploaded.", "ok"); finReload({ id: v.period_id }); })
      .catch(function (err) { toast(errText(err), "err"); busy(btn, false); });
  }

  function finDownloadBank(v, attachmentId) {
    api.download("/api/v1/financial/summaries/" + v.id + "/bank-statement/" + attachmentId)
      .then(function (blob) {
        var url = URL.createObjectURL(blob);
        var a = document.createElement("a");
        a.href = url;
        a.download = "bank-statement";
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
      })
      .catch(function (err) { toast(errText(err), "err"); });
  }



  // ---- support view ----------------------------------------------------
  function renderSupportView() {
    var host = byId("supportList");
    if (!host) return Promise.resolve();
    host.innerHTML = loadingHtml();
    var bindNew = byId("supNew");
    if (bindNew && !bindNew.getAttribute("data-bound")) {
      bindNew.setAttribute("data-bound", "1");
      bindNew.addEventListener("click", supportCreateForm);
    }
    return ensureSupport().then(function (rows) {
      var st = byId("supStatus") ? byId("supStatus").value : "";
      var list = rows.filter(function (r) {
        return !st || r.status === st;
      });
      if (!list.length) {
        host.innerHTML = emptyHtml("لا توجد طلبات مطابقة.", "No matching requests.");
        return;
      }
      host.innerHTML = list.map(supportRowCard).join("");
      host.querySelectorAll("[data-request]").forEach(function (el) {
        el.addEventListener("click", function () {
          openSupport(parseInt(el.getAttribute("data-request"), 10));
        });
      });
    });
  }

  function supportRowCard(r) {
    var dept = deptLabel(r.responsible_department || r.category);
    return (
      '<div class="av-row" data-request="' + r.id + '">' +
      '<div class="co-dot" style="background:' + PALETTE[r.company_id % PALETTE.length] + ';width:32px;height:32px;border-radius:9px">' + initial(r.company_name_ar) + "</div>" +
      '<div class="grow"><div class="t">' + escapeHtml(r.title) + "</div>" +
      '<div class="s">' + escapeHtml(STATE.lang === "ar" ? r.company_name_ar : r.company_name_en || r.company_name_ar) +
      " · " + dual(dept.ar, dept.en) + " · " + fmtDate(r.created_at) + "</div></div>" +
      catBadge(r.category) + supStatusBadge(r.status) +
      "</div>"
    );
  }

  function openSupport(id) {
    openModal({
      title: dual("تفاصيل طلب الدعم", "Support request"),
      wide: true,
      body: loadingHtml(),
      onMount: function () {
        loadSupportDetail(id);
      },
    });
  }

  function loadSupportDetail(id) {
    var body = byId("modalBody");
    Promise.all([
      get("/api/v1/support-requests/" + id),
      get("/api/v1/support-requests/" + id + "/comments").catch(function () {
        return [];
      }),
    ])
      .then(function (res) {
        var r = res[0];
        var comments = res[1] || [];
        if (!body) return;
        var dept = deptLabel(r.responsible_department || r.category);
        var canComment = has("support_request.comment");
        var canStatus = has("support_request.status_change");
        var canAssign = has("support_request.assign");
        var statuses = ["new", "in_progress", "completed", "closed"];

        body.innerHTML =
          '<div class="kv">' +
          kv(dual("الشركة", "Company"), escapeHtml(STATE.lang === "ar" ? r.company_name_ar : r.company_name_en || r.company_name_ar)) +
          kv(dual("النوع", "Type"), catBadge(r.category)) +
          kv(dual("القسم المسؤول", "Department"), dual(dept.ar, dept.en)) +
          kv(dual("الحالة", "Status"), supStatusBadge(r.status)) +
          kv(dual("التاريخ", "Date"), fmtDate(r.created_at)) +
          kv(dual("آخر تحديث", "Updated"), fmtDateTime(r.updated_at)) +
          (r.dimensions ? kv(dual("المقاسات", "Dimensions"), escapeHtml(r.dimensions)) : "") +
          (r.platform ? kv(dual("المنصة", "Platform"), escapeHtml(r.platform)) : "") +
          (r.reference_link
            ? kv(dual("رابط مرجعي", "Reference link"),
                '<a href="' + escapeHtml(r.reference_link) + '" target="_blank" rel="noopener">' + escapeHtml(r.reference_link) + "</a>")
            : "") +
          (r.delivery_link
            ? kv(dual("التسليم", "Delivery"),
                '<a href="' + escapeHtml(r.delivery_link) + '" target="_blank" rel="noopener">' + escapeHtml(r.delivery_link) + "</a>")
            : "") +
          "</div>" +
          (r.description ? '<div class="sec-title">' + dual("الوصف", "Description") + '</div><p class="note-block">' + escapeHtml(r.description) + "</p>" : "") +
          '<div class="sec-title">' + dual("التعليقات", "Comments") + "</div>" +
          '<div id="cmtList">' + renderComments(comments) + "</div>" +
          (canComment
            ? '<div class="av-field" style="margin-top:10px"><textarea class="av-textarea" id="cmtBody"' +
              phAttr("ph.comment") + "></textarea>" +
              '<div style="display:flex;gap:9px;align-items:center;margin-top:8px">' +
              '<label style="font-size:10.5px;color:var(--ink-500)"><input type="checkbox" id="cmtInternal"> ' + dual("داخلي", "Internal") + "</label>" +
              '<button class="btn-solid" id="cmtAdd" style="margin-inline-start:auto">' + dual("إضافة تعليق", "Add comment") + "</button></div></div>"
            : "") +
          ((canStatus || canAssign)
            ? '<div class="sec-title">' + dual("إجراءات", "Actions") + "</div>" +
              '<div style="display:flex;gap:9px;flex-wrap:wrap;align-items:center">' +
              (canStatus
                ? '<select class="av-select" id="supNewStatus">' + statuses.map(function (s) {
                    var lab = supportStatus(s);
                    return '<option value="' + s + '"' + (s === r.status ? " selected" : "") + ">" + dual(lab.ar, lab.en) + "</option>";
                  }).join("") + "</select>" +
                  '<button class="btn-solid" id="supSetStatus">' + dual("تغيير الحالة", "Change status") + "</button>"
                : "") +
              (canAssign
                ? '<button class="btn-outline" id="supAssignBtn">' + dual("إسناد", "Assign") + "</button>"
                : "") +
              (canStatus
                ? '<button class="btn-outline" id="supDeliverBtn">' + dual("تسليم العمل", "Record delivery") + "</button>"
                : "") +
              "</div>"
            : "") +
          '<div class="modal-foot" style="margin-top:14px;border-radius:12px;border:1px solid var(--line-2)"><button class="btn-outline" id="supClose">' + dual("إغلاق", "Close") + "</button></div>";

        if (byId("supClose")) byId("supClose").addEventListener("click", closeModal);
        if (byId("cmtAdd")) {
          byId("cmtAdd").addEventListener("click", function () {
            addComment(id, this);
          });
        }
        if (byId("supSetStatus")) {
          byId("supSetStatus").addEventListener("click", function () {
            changeSupportStatus(id, byId("supNewStatus").value, this);
          });
        }
        if (byId("supAssignBtn")) {
          byId("supAssignBtn").addEventListener("click", function () {
            assignSupportForm(id, r);
          });
        }
        if (byId("supDeliverBtn")) {
          byId("supDeliverBtn").addEventListener("click", function () {
            recordSupportDelivery(id, r);
          });
        }
      })
      .catch(function (err) {
        if (body) body.innerHTML = errorHtml(errText(err));
      });
  }

  function renderComments(comments) {
    if (!comments.length) {
      return '<p class="av-empty">' + dual("لا توجد تعليقات بعد.", "No comments yet.") + "</p>";
    }
    return comments
      .map(function (c) {
        var name = c.author_name_ar || (STATE.lang === "ar" ? "مستخدم" : "User");
        return (
          '<div class="cmt' + (c.is_internal ? " internal" : "") + '">' +
          '<div class="av">' + initial(name) + "</div>" +
          '<div class="body"><div class="who">' + escapeHtml(name) +
          (c.is_internal ? " · " + dual("داخلي", "Internal") : "") +
          '</div><div class="when">' + fmtDateTime(c.created_at) + "</div>" +
          '<div class="txt">' + escapeHtml(c.body) + "</div></div></div>"
        );
      })
      .join("");
  }

  function addComment(id, btn) {
    var box = byId("cmtBody");
    var body = box ? box.value.trim() : "";
    if (!body) {
      toast(STATE.lang === "ar" ? "اكتب نص التعليق." : "Write a comment.", "err");
      return;
    }
    busy(btn, true);
    post("/api/v1/support-requests/" + id + "/comments", {
      body: body,
      is_internal: !!(byId("cmtInternal") && byId("cmtInternal").checked),
    })
      .then(function () {
        toast(STATE.lang === "ar" ? "تم إضافة التعليق." : "Comment added.", "ok");
        loadSupportDetail(id);
        STATE.loaded.support = false;
        ensureSupport();
      })
      .catch(function (err) {
        toast(errText(err), "err");
        busy(btn, false);
      });
  }

  function changeSupportStatus(id, status, btn) {
    busy(btn, true);
    api.patch("/api/v1/support-requests/" + id + "/status", { status: status })
      .then(function () {
        toast(STATE.lang === "ar" ? "تم تحديث الحالة." : "Status updated.", "ok");
        STATE.loaded.support = false;
        refreshAll().then(function () { openSupport(id); });
      })
      .catch(function (err) {
        toast(errText(err), "err");
        busy(btn, false);
      });
  }

  // Assigning needs a real user directory. It is fetched from /api/v1/users
  // (holding_owner / admin only) rather than typed by hand, so the UI can never
  // send an id that does not exist.
  function assignSupportForm(id, r) {
    openModal({
      title: dual("إسناد الطلب", "Assign request"),
      body: loadingHtml(),
      footer:
        '<button class="btn-outline" id="asgCancel">' + dual("إلغاء", "Cancel") + "</button>" +
        '<button class="btn-solid" id="asgSave" disabled>' + dual("إسناد", "Assign") + "</button>",
      onMount: function (root, body) {
        root.querySelector("#asgCancel").addEventListener("click", closeModal);
        var userOptions = "";
        var ready = has("user.read")
          ? get("/api/v1/users")
              .then(function (users) {
                STATE.users = users || [];
                userOptions = STATE.users.map(function (u) {
                  var label = (STATE.lang === "ar" ? u.full_name_ar : u.full_name_en || u.full_name_ar) +
                    " · " + (u.role_name_ar || u.role_code);
                  return '<option value="' + u.id + '"' +
                    (u.id === r.assigned_to_id ? " selected" : "") + ">" + escapeHtml(label) + "</option>";
                }).join("");
              })
              .catch(function () { userOptions = ""; })
          : Promise.resolve();

        ready.then(function () {
          var assigneeField = userOptions
            ? '<div class="av-field"><label>' + dual("المسؤول", "Assignee") + "</label>" +
              '<select class="av-select" id="asgUser" style="width:100%"><option value="">' +
              dual("— غير مُسند —", "— Unassigned —") + "</option>" + userOptions + "</select></div>"
            : '<div class="av-field"><label>' + dual("المسؤول", "Assignee") + "</label>" +
              '<input class="av-input" id="asgUser" style="width:100%" value="' + escAttr(r.assigned_to_id || "") + '" placeholder="' + escAttr(String((USER && USER.id) || "")) + '"></div>';

          body.innerHTML =
            '<div class="av-field"><label>' + dual("القسم المسؤول", "Responsible department") + "</label>" +
            '<select class="av-select" id="asgDept" style="width:100%">' +
            ["holding_owner", "business_development", "marketing", "design", "accounting", "general"].map(function (d) {
              var lab = deptLabel(d);
              return '<option value="' + d + '"' + (d === (r.responsible_department || "") ? " selected" : "") + ">" + dual(lab.ar, lab.en) + "</option>";
            }).join("") + "</select></div>" + assigneeField;

          var save = root.querySelector("#asgSave");
          save.disabled = false;
          save.addEventListener("click", function () {
            var btn = this;
            var uid = numOrNull(root.querySelector("#asgUser").value);
            busy(btn, true);
            api.patch("/api/v1/support-requests/" + id + "/assign", {
              assigned_to_id: uid,
              responsible_department: root.querySelector("#asgDept").value,
            })
              .then(function () {
                toast(STATE.lang === "ar" ? "تم إسناد الطلب." : "Request assigned.", "ok");
                STATE.loaded.support = false;
                refreshAll().then(function () { openSupport(id); });
              })
              .catch(function (err) {
                toast(errText(err), "err");
                busy(btn, false);
              });
          });
        });
      },
    });
  }

  function recordSupportDelivery(id, r) {
    openModal({
      title: dual("تسليم العمل", "Record delivery"),
      body:
        '<div class="av-field"><label>' + dual("رابط أو وسيلة التسليم", "Delivery link or channel") + '</label>' +
        '<input class="av-input" id="dlLink" style="width:100%" value="' + escAttr(r.delivery_link || "") + '" placeholder="https://"></div>',
      footer:
        '<button class="btn-outline" id="dlCancel">' + dual("إلغاء", "Cancel") + "</button>" +
        '<button class="btn-solid" id="dlSave">' + dual("حفظ التسليم", "Save delivery") + "</button>",
      onMount: function (root) {
        root.querySelector("#dlCancel").addEventListener("click", closeModal);
        root.querySelector("#dlSave").addEventListener("click", function () {
          var btn = this;
          var link = root.querySelector("#dlLink").value.trim();
          if (!link) {
            toast(STATE.lang === "ar" ? "أدخل رابط التسليم." : "Enter a delivery link.", "err");
            return;
          }
          busy(btn, true);
          api.patch("/api/v1/support-requests/" + id + "/delivery", { delivery_link: link })
            .then(function () {
              toast(STATE.lang === "ar" ? "تم تسجيل التسليم." : "Delivery recorded.", "ok");
              STATE.loaded.support = false;
              refreshAll().then(function () { openSupport(id); });
            })
            .catch(function (err) {
              toast(errText(err), "err");
              busy(btn, false);
            });
        });
      },
    });
  }

  function supportCreateForm(preselectCompanyId) {
    return ensureCompanies().then(function () {
      var opts = STATE.companies.length ? STATE.companies : [];
      openModal({
        title: dual("طلب دعم جديد", "New support request"),
        body:
          '<div class="av-field"><label>' + dual("الشركة", "Company") + '</label><select class="av-select" id="ncCompany" style="width:100%">' +
          opts.map(function (c) {
            var sel = preselectCompanyId && c.id === preselectCompanyId ? " selected" : "";
            return '<option value="' + c.id + '"' + sel + ">" + escapeHtml(companyName(c)) + "</option>";
          }).join("") + "</select></div>" +
        '<div class="av-field"><label>' + dual("النوع", "Type") + '</label><select class="av-select" id="ncCat" style="width:100%">' +
        ["business_development", "marketing", "design", "accounting", "general"].map(function (c) {
          var cat = CATEGORY[c];
          return '<option value="' + c + '">' + dual(cat.ar, cat.en) + "</option>";
        }).join("") + "</select></div>" +
        '<div class="av-field"><label>' + dual("العنوان", "Title") + '</label><input class="av-input" id="ncTitle" style="width:100%"></div>' +
        '<div class="av-field"><label>' + dual("الوصف", "Description") + '</label><textarea class="av-textarea" id="ncDesc"></textarea></div>' +
        '<div class="av-form-inline">' +
        '<div class="av-field"><label>' + dual("المقاسات", "Dimensions") + '</label><input class="av-input" id="ncDims" style="width:100%"></div>' +
        '<div class="av-field"><label>' + dual("المنصة", "Platform") + '</label><input class="av-input" id="ncPlatform" style="width:100%"></div>' +
        "</div>" +
        '<div class="av-field"><label>' + dual("رابط مرجعي", "Reference link") + '</label><input class="av-input" id="ncRef" style="width:100%"></div>',
      footer:
        '<button class="btn-outline" id="ncCancel">' + dual("إلغاء", "Cancel") + "</button>" +
        '<button class="btn-solid" id="ncSave">' + dual("إنشاء", "Create") + "</button>",
      onMount: function (root) {
        root.querySelector("#ncCancel").addEventListener("click", closeModal);
        root.querySelector("#ncSave").addEventListener("click", function () {
          var btn = this;
          var title = root.querySelector("#ncTitle").value.trim();
          if (title.length < 3) {
            toast(STATE.lang === "ar" ? "العنوان قصير جدًا." : "Title is too short.", "err");
            return;
          }
          busy(btn, true);
          post("/api/v1/support-requests", {
            company_id: parseInt(root.querySelector("#ncCompany").value, 10),
            category: root.querySelector("#ncCat").value,
            title: title,
            description: root.querySelector("#ncDesc").value || null,
            dimensions: root.querySelector("#ncDims").value || null,
            platform: root.querySelector("#ncPlatform").value || null,
            reference_link: root.querySelector("#ncRef").value || null,
          })
            .then(function (created) {
              toast(STATE.lang === "ar" ? "تم إنشاء الطلب." : "Request created.", "ok");
              STATE.loaded.support = false;
              refreshAll().then(function () { openSupport(created.id); });
            })
            .catch(function (err) {
              toast(errText(err), "err");
              busy(btn, false);
            });
        });
      },
    });
    });
  }

  // ---- requests view (dynamic forms + approvals) -----------------------
  function submissionStatusBadge(status) {
    var map = {
      draft: ["مسودة", "Draft", "late"],
      incomplete: ["غير مكتمل", "Incomplete", "late"],
      submitted: ["مُقدَّم", "Submitted", "rev"],
      in_review: ["قيد المراجعة", "In review", "rev"],
      returned: ["معاد", "Returned", "late"],
      approved: ["معتمد", "Approved", "ok"],
      rejected: ["مرفوض", "Rejected", "miss"],
      cancelled: ["ملغى", "Cancelled", "rev"],
    };
    return statusBadgeFromMap(status, map);
  }

  function statusBadgeFromMap(value, map) {
    var m = map[value] || [value || "—", value || "—", "rev"];
    return (
      '<span class="status ' + m[2] + '"><i></i>' + dual(m[0], m[1]) + "</span>"
    );
  }

  function ensureForms() {
    if (STATE.loaded.forms) return Promise.resolve(STATE.forms);
    if (!has("form.read")) return Promise.resolve([]);
    return get("/api/v1/forms")
      .then(function (rows) {
        STATE.forms = rows || [];
        STATE.loaded.forms = true;
        return STATE.forms;
      })
      .catch(function (err) {
        handleLoadError(err);
        return [];
      });
  }

  function ensureSubmissions() {
    var q = [];
    if (STATE.reqForm) q.push("form_id=" + STATE.reqForm);
    if (STATE.reqStatus) q.push("status=" + STATE.reqStatus);
    var suffix = q.length ? "?" + q.join("&") : "";
    return get("/api/v1/form-submissions" + suffix)
      .then(function (page) {
        return page && page.items ? page.items : [];
      })
      .catch(function (err) {
        handleLoadError(err);
        return [];
      });
  }

  function renderRequestsView() {
    var host = byId("requestsList");
    if (!host) return Promise.resolve();
    host.innerHTML = loadingHtml();
    bindRequestsControls();
    return Promise.all([ensureForms(), ensureSubmissions()]).then(function (res) {
      var forms = res[0];
      var rows = res[1];
      fillFormFilter(forms);
      if (!rows.length) {
        host.innerHTML = emptyHtml(
          "لا توجد طلبات مطابقة. ابدأ بإنشاء طلب جديد.",
          "No matching requests. Start by creating a new one."
        );
        return;
      }
      host.innerHTML = rows.map(requestRow).join("");
      host.querySelectorAll("[data-submission]").forEach(function (row) {
        row.addEventListener("click", function () {
          openSubmission(parseInt(row.getAttribute("data-submission"), 10));
        });
      });
    });
  }

  function fillFormFilter(forms) {
    var sel = byId("reqFormFilter");
    if (!sel) return;
    var current = sel.value;
    sel.innerHTML =
      '<option value="">' + dual("كل النماذج", "All forms") + "</option>" +
      forms
        .filter(function (f) {
          return f.status === "published";
        })
        .map(function (f) {
          return (
            '<option value="' + f.id + '">' +
            escapeHtml(companyName(f)) +
            "</option>"
          );
        })
        .join("");
    sel.value = current || STATE.reqForm || "";
  }

  function requestRow(s) {
    var company = STATE.lang === "ar" ? s.company_name_ar : s.company_name_en;
    var step = STATE.lang === "ar" ? s.current_step_name_ar : s.current_step_name_en;
    var stepText = step
      ? dual("الخطوة: " + s.current_step_order + "/" + (s.total_steps || "?"), 
             "Step " + s.current_step_order + "/" + (s.total_steps || "?") ) +
        " · " + escapeHtml(step)
      : "";
    return (
      '<div class="av-row" data-submission="' + s.id + '" style="flex-direction:column;align-items:stretch;gap:8px">' +
      '<div style="display:flex;align-items:center;gap:11px">' +
      '<div class="co-dot" style="background:var(--navy-600);width:34px;height:34px;border-radius:10px;font-size:12px">' +
      escapeHtml((s.reference || "").slice(-2)) + "</div>" +
      '<div class="grow"><div class="t">' + escapeHtml(s.title || companyName(s)) + "</div>" +
      '<div class="s">' + escapeHtml(s.reference || "") + " · " + escapeHtml(company || "") + "</div></div>" +
      submissionStatusBadge(s.status) +
      "</div>" +
      (stepText
        ? '<div style="font-size:10.5px;color:var(--ink-400)">' + stepText + "</div>"
        : "") +
      "</div>"
    );
  }

  function bindRequestsControls() {
    var refresh = byId("reqRefresh");
    if (refresh && !refresh.getAttribute("data-bound")) {
      refresh.setAttribute("data-bound", "1");
      refresh.addEventListener("click", function () { renderRequestsView(); });
    }
    var status = byId("reqStatusFilter");
    if (status && !status.getAttribute("data-bound")) {
      status.setAttribute("data-bound", "1");
      status.addEventListener("change", function () {
        STATE.reqStatus = this.value;
        renderRequestsView();
      });
    }
    var form = byId("reqFormFilter");
    if (form && !form.getAttribute("data-bound")) {
      form.setAttribute("data-bound", "1");
      form.addEventListener("change", function () {
        STATE.reqForm = this.value;
        renderRequestsView();
      });
    }
    var newBtn = byId("reqNew");
    if (newBtn && !newBtn.getAttribute("data-bound")) {
      newBtn.setAttribute("data-bound", "1");
      newBtn.addEventListener("click", newRequestForm);
    }
  }

  function newRequestForm(preselectFormId) {
    ensureForms().then(function (forms) {
      var usable = forms.filter(function (f) { return f.status === "published"; });
      if (!usable.length) {
        toast(
          STATE.lang === "ar"
            ? "لا توجد نماذج منشورة بعد."
            : "There are no published forms yet.",
          "warn"
        );
        return;
      }
      var needCompany = has("company.read");
      var companiesP = needCompany ? ensureCompanies() : Promise.resolve([]);
      companiesP.then(function (companies) {
        openModal({
          title: dual("طلب جديد", "New request"),
          body:
            field(
              "النموذج",
              "Form",
              selectInput(
                "nrForm",
                usable.map(function (f) {
                  return { value: f.id, label: companyName(f) };
                }),
                preselectFormId
              )
            ) +
            (companies.length
              ? field(
                  "الشركة",
                  "Company",
                  selectInput(
                    "nrCompany",
                    companies.map(function (c) {
                      return { value: c.id, label: companyName(c) };
                    })
                  )
                )
              : "") +
            field(
              "العنوان",
              "Title",
              textInput("nrTitle", "", "ph.shortTitle")
            ) +
            '<p class="note-block" style="margin-top:8px"><span class="lbl">' +
            dual("ملاحظة", "Note") +
            "</span>" +
            dual(
              "ستُبنى حقول النموذج تلقائيًا بعد اختيار النموذج وحفظ المسودة.",
              "The form fields are loaded from the form definition when you save the draft."
            ) +
            "</p>",
          footer:
            '<button class="btn-outline" id="nrCancel">' + dual("إلغاء", "Cancel") + "</button>" +
            '<button class="btn-solid" id="nrSave">' + dual("حفظ المسودة", "Save draft") + "</button>",
          onMount: function (root) {
            root.querySelector("#nrCancel").addEventListener("click", closeModal);
            root.querySelector("#nrSave").addEventListener("click", function () {
              var btn = this;
              var payload = {
                form_id: parseInt(root.querySelector("#nrForm").value, 10),
                company_id: root.querySelector("#nrCompany")
                  ? parseInt(root.querySelector("#nrCompany").value, 10)
                  : (primaryCompanyId() || 0),
                title: root.querySelector("#nrTitle").value || null,
                values: {},
              };
              if (!payload.company_id) {
                toast(STATE.lang === "ar" ? "اختر شركة." : "Choose a company.", "warn");
                return;
              }
              busy(btn, true);
              post("/api/v1/form-submissions", payload)
                .then(function (created) {
                  closeModal();
                  toast(STATE.lang === "ar" ? "تم إنشاء الطلب." : "Request created.", "ok");
                  renderRequestsView();
                  openSubmission(created.id);
                })
                .catch(function (err) {
                  toast(errText(err), "err");
                  busy(btn, false);
                });
            });
          },
        });
      });
    });
  }

  function openSubmission(id) {
    openModal({
      title: dual("تفاصيل الطلب", "Request details"),
      wide: true,
      body: loadingHtml(),
      onMount: function () {
        loadSubmissionDetail(id);
      },
    });
  }

  function loadSubmissionDetail(id) {
    var body = byId("modalBody");
    return get("/api/v1/form-submissions/" + id)
      .then(function (s) {
        body.innerHTML = submissionDetailHtml(s);
        bindSubmissionActions(s);
      })
      .catch(function (err) {
        body.innerHTML = errorHtml(errText(err));
      });
  }

  function submissionDetailHtml(s) {
    var company = STATE.lang === "ar" ? s.company_name_ar : s.company_name_en;
    var html =
      '<div class="note-block"><span class="lbl">' + dual("المرجع", "Reference") + "</span>" +
      escapeHtml(s.reference || "") + " · " + escapeHtml(company || "") + "</div>" +
      '<div class="note-block"><span class="lbl">' + dual("الحالة", "Status") + "</span>" +
      submissionStatusBadge(s.status) + "</div>";

    // dynamic values
    var vals = s.values || {};
    var keys = Object.keys(vals);
    if (keys.length) {
      html += '<h3 style="font-size:12.5px;margin:14px 0 8px">' + dual("البيانات", "Values") + "</h3>";
      html += keys
        .map(function (k) {
          return (
            '<div class="note-block"><span class="lbl">' + escapeHtml(k) + "</span>" +
            escapeHtml(String(vals[k])) + "</div>"
          );
        })
        .join("");
    }

    // requirements
    if (s.requirements && s.requirements.length) {
      html += '<h3 style="font-size:12.5px;margin:14px 0 8px">' + dual("المتطلبات", "Requirements") + "</h3>";
      html += s.requirements
        .map(function (r) {
          var tick = r.is_satisfied
            ? '<span class="badge badge-ok">' + dual("مستوفى", "Met") + "</span>"
            : '<span class="badge badge-err">' + dual("ناقص", "Missing") + "</span>";
          var action =
            has("document.upload") && !r.is_satisfied && s.status !== "approved"
              ? ' <button class="btn-outline" data-req-upload="' + r.id + '">' +
                dual("رفع", "Upload") + "</button>"
              : "";
          return (
            '<div class="av-row" style="cursor:default">' +
            '<div class="grow"><div class="t">' + escapeHtml(companyName(r)) + "</div>" +
            '<div class="s">' + escapeHtml(r.requirement_type) +
            (r.is_mandatory ? " · " + dual("إلزامي", "Mandatory") : "") + "</div></div>" +
            tick + action +
            "</div>"
          );
        })
        .join("");
    }

    // workflow timeline
    if (s.workflow) {
      html += '<h3 style="font-size:12.5px;margin:14px 0 8px">' + dual("مسار الموافقات", "Approval path") + "</h3>";
      html += (s.workflow.tasks || [])
        .map(function (t) {
          var name = STATE.lang === "ar" ? t.step_name_ar : t.step_name_en;
          var assignee = STATE.lang === "ar" ? t.assignee_name_ar : t.assignee_name_en;
          return (
            '<div class="av-row" style="cursor:default">' +
            '<div class="co-dot" style="width:30px;height:30px;border-radius:9px;font-size:11px">' +
            t.step_order + "</div>" +
            '<div class="grow"><div class="t">' + escapeHtml(name || "") + "</div>" +
            '<div class="s">' + escapeHtml(assignee || "—") + "</div></div>" +
            statusBadgeFromMap(t.status, {
              pending: ["قيد الانتظار", "Pending", "rev"],
              approved: ["معتمد", "Approved", "ok"],
              rejected: ["مرفوض", "Rejected", "miss"],
              skipped: ["متجاوز", "Skipped", "rev"],
              returned: ["معاد", "Returned", "late"],
            }) +
            "</div>"
          );
        })
        .join("");
    }

    // footer actions
    var actions = [];
    if (s.status === "draft" || s.status === "incomplete") {
      if (has("form.update")) {
        actions.push('<button class="btn-outline" id="subEdit">' + dual("تعديل", "Edit") + "</button>");
      }
      actions.push('<button class="btn-solid" id="subSubmit">' + dual("إرسال", "Submit") + "</button>");
    }
    if (s.can_act && s.workflow && s.workflow.tasks) {
      var mine = s.workflow.tasks.filter(function (t) {
        return t.status === "pending" && t.assignee_id === USER.id;
      })[0];
      if (mine) {
        html +=
          '<input class="av-input" id="subComment" placeholder="' +
          escapeAttrSafe(STATE.lang === "ar" ? "ملاحظة" : "Comment") +
          '" style="margin-top:12px">';
        actions.push('<button class="btn-outline" data-act="return">' + dual("إعادة", "Return") + "</button>");
        actions.push('<button class="btn-outline danger" data-act="reject">' + dual("رفض", "Reject") + "</button>");
        actions.push('<button class="btn-solid" data-act="approve">' + dual("اعتماد", "Approve") + "</button>");
      }
    }

    return (
      html +
      (actions.length
        ? '<div style="display:flex;gap:9px;justify-content:flex-end;margin-top:16px">' +
          actions.join("") + "</div>"
        : "")
    );
  }

  function escapeAttrSafe(t) {
    return escAttr(t);
  }

  function bindSubmissionActions(s) {
    var body = byId("modalBody");
    var submit = byId("subSubmit");
    if (submit) {
      submit.addEventListener("click", function () {
        var btn = this;
        busy(btn, true);
        post("/api/v1/form-submissions/" + s.id + "/submit", {})
          .then(function () {
            toast(STATE.lang === "ar" ? "تم إرسال الطلب." : "Request submitted.", "ok");
            loadSubmissionDetail(s.id);
            renderRequestsView();
          })
          .catch(function (err) {
            toast(errText(err), "err");
            busy(btn, false);
          });
      });
    }
    var edit = byId("subEdit");
    if (edit) {
      edit.addEventListener("click", function () { editSubmissionForm(s); });
    }
    body.querySelectorAll("[data-req-upload]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        uploadRequirementDocument(s.id, parseInt(btn.getAttribute("data-req-upload"), 10));
      });
    });
    body.querySelectorAll("[data-act]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        submitApprovalDecision(s, btn.getAttribute("data-act"), btn);
      });
    });
  }

  function submitApprovalDecision(s, decision, btn) {
    var mine = (s.workflow.tasks || []).filter(function (t) {
      return t.status === "pending" && t.assignee_id === USER.id;
    })[0];
    if (!mine) return;
    var commentEl = byId("subComment");
    var comment = commentEl ? commentEl.value : "";
    busy(btn, true);
    post("/api/v1/approvals/tasks/" + mine.id, { decision: decision, comment: comment || null })
      .then(function () {
        toast(STATE.lang === "ar" ? "تم تسجيل الإجراء." : "Action recorded.", "ok");
        loadSubmissionDetail(s.id);
        renderApprovalsView();
      })
      .catch(function (err) {
        toast(errText(err), "err");
        busy(btn, false);
      });
  }

  function uploadRequirementDocument(submissionId, requirementId) {
    var input = document.createElement("input");
    input.type = "file";
    input.addEventListener("change", function () {
      if (!input.files || !input.files[0]) return;
      api
        .upload(
          "/api/v1/form-submissions/" + submissionId + "/requirements/" + requirementId + "/documents",
          input.files[0]
        )
        .then(function () {
          toast(STATE.lang === "ar" ? "تم رفع المستند." : "Document uploaded.", "ok");
          loadSubmissionDetail(submissionId);
        })
        .catch(function (err) {
          toast(errText(err), "err");
        });
    });
    input.click();
  }

  function editSubmissionForm(s) {
    get("/api/v1/forms/" + s.form_id + "/versions/" + s.form_version_id)
      .then(function (version) {
        openModal({
          title: dual("تعديل الطلب", "Edit request"),
          wide: true,
          body:
            field("العنوان", "Title", textInput("seTitle", s.title || "", "")) +
            (version.fields || [])
              .map(function (f) { return dynamicFieldHtml(f, s.values || {}); })
              .join(""),
          footer:
            '<button class="btn-outline" id="seCancel">' + dual("إلغاء", "Cancel") + "</button>" +
            '<button class="btn-solid" id="seSave">' + dual("حفظ", "Save") + "</button>",
          onMount: function (root) {
            root.querySelector("#seCancel").addEventListener("click", closeModal);
            root.querySelector("#seSave").addEventListener("click", function () {
              var btn = this;
              var values = collectDynamicValues(version.fields || []);
              busy(btn, true);
              patch("/api/v1/form-submissions/" + s.id, {
                title: root.querySelector("#seTitle").value || null,
                values: values,
              })
                .then(function () {
                  closeModal();
                  toast(STATE.lang === "ar" ? "تم الحفظ." : "Saved.", "ok");
                  loadSubmissionDetail(s.id);
                })
                .catch(function (err) {
                  toast(errText(err), "err");
                  busy(btn, false);
                });
            });
          },
        });
      })
      .catch(function (err) {
        toast(errText(err), "err");
      });
  }

  function dynamicFieldHtml(f, values) {
    var label = STATE.lang === "ar" ? f.label_ar : f.label_en;
    var val = values && values[f.key] !== undefined ? values[f.key] : "";
    var control;
    if (f.field_type === "long_text") {
      control = '<textarea class="av-input" data-value-key="' + escAttr(f.key) + '">' +
        escapeHtml(String(val)) + "</textarea>";
    } else if (f.field_type === "select") {
      var opts = (f.config && f.config.options) || [];
      control = '<select class="av-input" data-value-key="' + escAttr(f.key) + '"><option value=""></option>' +
        opts.map(function (o) {
          var v = o.value !== undefined ? o.value : o;
          return '<option value="' + escAttr(v) + '"' +
            (String(v) === String(val) ? " selected" : "") + ">" + escapeHtml(v) + "</option>";
        }).join("") + "</select>";
    } else if (f.field_type === "boolean") {
      control = '<select class="av-input" data-value-key="' + escAttr(f.key) + '">' +
        '<option value=""></option><option value="true">' +
        dual("نعم", "Yes") + '</option><option value="false">' + dual("لا", "No") + "</option></select>";
    } else if (f.field_type === "date") {
      control = '<input class="av-input" type="date" data-value-key="' + escAttr(f.key) +
        '" value="' + escAttr(val) + '">';
    } else if (f.field_type === "decimal" || f.field_type === "integer") {
      control = '<input class="av-input" type="number" step="any" data-value-key="' + escAttr(f.key) +
        '" value="' + escAttr(val) + '">';
    } else {
      control = '<input class="av-input" type="text" data-value-key="' + escAttr(f.key) +
        '" value="' + escAttr(val) + '">';
    }
    return field(label, label, control);
  }

  function collectDynamicValues(fields) {
    var out = {};
    fields.forEach(function (f) {
      var el = document.querySelector('[data-value-key="' + f.key + '"]');
      if (!el) return;
      out[f.key] = el.value;
    });
    return out;
  }

  // ---- approvals view --------------------------------------------------
  function renderApprovalsView() {
    var host = byId("approvalsList");
    if (!host) return Promise.resolve();
    host.innerHTML = loadingHtml();
    var refresh = byId("apprRefresh");
    if (refresh && !refresh.getAttribute("data-bound")) {
      refresh.setAttribute("data-bound", "1");
      refresh.addEventListener("click", renderApprovalsView);
    }
    return get("/api/v1/approvals/my")
      .then(function (page) {
        var rows = page && page.items ? page.items : [];
        if (!rows.length) {
          host.innerHTML = emptyHtml(
            "لا توجد طلبات تنتظر إجرائك.",
            "No requests are waiting for your action."
          );
          return;
        }
        host.innerHTML = rows.map(requestRow).join("");
        host.querySelectorAll("[data-submission]").forEach(function (row) {
          row.addEventListener("click", function () {
            openSubmission(parseInt(row.getAttribute("data-submission"), 10));
          });
        });
      })
      .catch(function (err) {
        handleLoadError(err);
        host.innerHTML = errorHtml(errText(err));
      });
  }

  // ---- documents view --------------------------------------------------
  function renderDocumentsView() {
    var host = byId("documentsList");
    if (!host) return Promise.resolve();
    host.innerHTML = loadingHtml();
    bindDocumentsControls();
    return Promise.all([
      get("/api/v1/documents/categories").catch(function () { return []; }),
      get("/api/v1/documents/expiry-summary").catch(function () { return null; }),
    ]).then(function (meta) {
      fillDocCategoryFilter(meta[0]);
      renderDocSummary(meta[1]);
      var q = [];
      if (STATE.docCategory) q.push("category_id=" + STATE.docCategory);
      if (STATE.docExpiry) q.push("expiry=" + STATE.docExpiry);
      return get("/api/v1/documents" + (q.length ? "?" + q.join("&") : ""));
    }).then(function (page) {
      var rows = page && page.items ? page.items : [];
      if (!rows.length) {
        host.innerHTML = emptyHtml("لا توجد مستندات.", "No documents found.");
        return;
      }
      host.innerHTML = rows.map(documentRow).join("");
      host.querySelectorAll("[data-doc]").forEach(function (row) {
        row.addEventListener("click", function () {
          openDocument(JSON.parse(row.getAttribute("data-doc")));
        });
      });
    }).catch(function (err) {
      handleLoadError(err);
      host.innerHTML = errorHtml(errText(err));
    });
  }

  function renderDocSummary(summary) {
    var host = byId("docsSummary");
    if (!host) return;
    if (!summary) { host.innerHTML = ""; return; }
    summary.total =
      (summary.expired || 0) + (summary.expiring_soon || 0) +
      (summary.valid || 0) + (summary.none || 0);
    var tiles = [
      ["total", "إجمالي المستندات", "Total documents"],
      ["expiring_soon", "تنتهي قريبًا", "Expiring soon"],
      ["expired", "منتهية", "Expired"],
    ];
    host.innerHTML = tiles
      .map(function (t) {
        return (
          '<div class="av-panel"><div style="font-size:10px;color:var(--ink-400);font-weight:600">' +
          dual(t[1], t[2]) + "</div>" +
          '<div style="font-family:var(--f-display);font-size:24px;font-weight:600;color:var(--navy-900);margin-top:4px">' +
          toArabicDigits(String(summary[t[0]] || 0)) + "</div></div>"
        );
      })
      .join("");
  }

  function fillDocCategoryFilter(categories) {
    var sel = byId("docCatFilter");
    if (!sel) return;
    var current = sel.value;
    sel.innerHTML =
      '<option value="">' + dual("كل التصنيفات", "All categories") + "</option>" +
      (categories || [])
        .map(function (c) {
          return '<option value="' + c.id + '">' + escapeHtml(companyName(c)) + "</option>";
        })
        .join("");
    sel.value = current || STATE.docCategory || "";
  }

  function expiryBadge(state) {
    return statusBadgeFromMap(state, {
      expired: ["منتهي", "Expired", "miss"],
      expiring_soon: ["قريب الانتهاء", "Expiring soon", "late"],
      valid: ["ساري", "Valid", "ok"],
    });
  }

  function documentRow(d) {
    var company = STATE.lang === "ar" ? d.company_name_ar : d.company_name_en;
    return (
      '<div class="av-row" data-doc="' + escAttr(JSON.stringify(d)) + '">' +
      '<div class="co-dot" style="background:var(--gold-600);width:34px;height:34px;border-radius:10px;font-size:12px">' +
      escapeHtml((d.original_filename || "?").slice(-1).toUpperCase()) + "</div>" +
      '<div class="grow"><div class="t">' + escapeHtml(companyName(d)) + "</div>" +
      '<div class="s">' + escapeHtml(d.original_filename) + " · " + escapeHtml(company || "") + "</div></div>" +
      expiryBadge(d.expiry_state) +
      "</div>"
    );
  }

  function bindDocumentsControls() {
    var refresh = byId("docRefresh");
    if (refresh && !refresh.getAttribute("data-bound")) {
      refresh.setAttribute("data-bound", "1");
      refresh.addEventListener("click", renderDocumentsView);
    }
    var cat = byId("docCatFilter");
    if (cat && !cat.getAttribute("data-bound")) {
      cat.setAttribute("data-bound", "1");
      cat.addEventListener("change", function () {
        STATE.docCategory = this.value;
        renderDocumentsView();
      });
    }
    var exp = byId("docExpiryFilter");
    if (exp && !exp.getAttribute("data-bound")) {
      exp.setAttribute("data-bound", "1");
      exp.addEventListener("change", function () {
        STATE.docExpiry = this.value;
        renderDocumentsView();
      });
    }
    var newBtn = byId("docNew");
    if (newBtn && !newBtn.getAttribute("data-bound")) {
      newBtn.setAttribute("data-bound", "1");
      newBtn.addEventListener("click", uploadDocumentForm);
    }
  }

  function uploadDocumentForm() {
    ensureCompanies().then(function (companies) {
      get("/api/v1/documents/categories").then(function (categories) {
        openModal({
          title: dual("رفع مستند", "Upload document"),
          body:
            field("الملف", "File", '<input class="av-input" type="file" id="duFile">') +
            (companies.length
              ? field("الشركة", "Company", selectInput("duCompany", companies.map(function (c) {
                  return { value: c.id, label: companyName(c) };
                })))
              : "") +
            field("التصنيف", "Category", selectInput("duCategory", (categories || []).map(function (c) {
              return { value: c.id, label: companyName(c) };
            }))) +
            field("العنوان", "Title", textInput("duTitle", "", "")) +
            field("تاريخ الإصدار", "Issue date", '<input class="av-input" type="date" id="duIssue">') +
            field("تاريخ الانتهاء", "Expiry date", '<input class="av-input" type="date" id="duExpiry">'),
          footer:
            '<button class="btn-outline" id="duCancel">' + dual("إلغاء", "Cancel") + "</button>" +
            '<button class="btn-solid" id="duSave">' + dual("رفع", "Upload") + "</button>",
          onMount: function (root) {
            root.querySelector("#duCancel").addEventListener("click", closeModal);
            root.querySelector("#duSave").addEventListener("click", function () {
              var btn = this;
              var file = root.querySelector("#duFile").files[0];
              if (!file) {
                toast(STATE.lang === "ar" ? "اختر ملفًا." : "Choose a file.", "warn");
                return;
              }
              var fields = {
                company_id: root.querySelector("#duCompany")
                  ? root.querySelector("#duCompany").value
                  : primaryCompanyId(),
                category_id: root.querySelector("#duCategory").value,
                title_ar: root.querySelector("#duTitle").value,
                issue_date: root.querySelector("#duIssue").value,
                expiry_date: root.querySelector("#duExpiry").value,
              };
              busy(btn, true);
              api.upload("/api/v1/documents", file, fields)
                .then(function () {
                  closeModal();
                  toast(STATE.lang === "ar" ? "تم رفع المستند." : "Document uploaded.", "ok");
                  renderDocumentsView();
                })
                .catch(function (err) {
                  toast(errText(err), "err");
                  busy(btn, false);
                });
            });
          },
        });
      });
    });
  }

  function openDocument(d) {
    openModal({
      title: dual("تفاصيل المستند", "Document details"),
      body: documentDetailHtml(d),
      footer:
        '<button class="btn-outline" id="dcClose">' + dual("إغلاق", "Close") + "</button>" +
        '<button class="btn-solid" id="dcDownload">' + dual("تنزيل", "Download") + "</button>",
      onMount: function (root) {
        root.querySelector("#dcClose").addEventListener("click", closeModal);
        root.querySelector("#dcDownload").addEventListener("click", function () {
          var btn = this;
          busy(btn, true);
          api
            .download("/api/v1/documents/" + d.id + "/download")
            .then(function (blob) {
              var url = URL.createObjectURL(blob);
              var a = document.createElement("a");
              a.href = url;
              a.download = d.original_filename;
              document.body.appendChild(a);
              a.click();
              document.body.removeChild(a);
              setTimeout(function () { URL.revokeObjectURL(url); }, 4000);
              busy(btn, false);
            })
            .catch(function (err) {
              toast(errText(err), "err");
              busy(btn, false);
            });
        });
      },
    });
  }

  function documentDetailHtml(d) {
    var company = STATE.lang === "ar" ? d.company_name_ar : d.company_name_en;
    var rows = [
      [dual("ملف", "File"), d.original_filename],
      [dual("الشركة", "Company"), company],
      [dual("التصنيف", "Category"), d.category_code],
      [dual("الحالة", "Status"), d.status],
      [dual("الصلاحية", "Validity"), d.expiry_state],
      [dual("الإصدار", "Issued"), fmtDate(d.issue_date)],
      [dual("الانتهاء", "Expires"), fmtDate(d.expiry_date)],
      [dual("الحجم", "Size"), d.size_bytes ? Math.round(d.size_bytes / 1024) + " KB" : null],
    ];
    return rows
      .filter(function (r) { return r[1]; })
      .map(function (r) {
        return (
          '<div class="note-block"><span class="lbl">' + r[0] + "</span>" +
          escapeHtml(String(r[1])) + "</div>"
        );
      })
      .join("");
  }

  // ---- investments view ------------------------------------------------
  function renderInvestments() {
    var host = byId("investContent");
    if (!host) return Promise.resolve();
    host.innerHTML = loadingHtml();
    return Promise.all([ensureReports(), ensureCompanies()]).then(function () {
      var opps = STATE.insights.filter(function (i) {
        return i.kind === "opportunity";
      });
      var attention = (STATE.dashboard && STATE.dashboard.companies_requiring_attention) || [];
      var missing = (STATE.dashboard && STATE.dashboard.companies_missing_report) || [];
      host.innerHTML =
        '<div class="av-grid cols-2">' +
        '<div class="av-panel"><h3>' + dual("فرص استثمارية مرصودة", "Detected opportunities") + "</h3>" +
        (opps.length
          ? '<div class="av-list">' + opps.map(function (i) {
              return '<div class="av-row" style="cursor:default"><div class="grow"><div class="t">' + escapeHtml(STATE.lang === "ar" ? i.title_ar : i.title_en) + '</div><div class="s">' + escapeHtml(STATE.lang === "ar" ? i.detail_ar : i.detail_en) + "</div></div></div>";
            }).join("") + "</div>"
          : '<p class="av-empty">' + dual("لا توجد فرص مرصودة بعد.", "No opportunities detected yet.") + "</p>") +
        "</div>" +
        '<div class="av-panel"><h3>' + dual("شركات تحتاج متابعة", "Companies needing attention") + "</h3>" +
        (attention.length
          ? '<div class="av-list">' + attention.map(function (c) {
              return '<div class="av-row" data-invest-co="' + c.id + '"><div class="co-dot" style="background:' + PALETTE[c.id % PALETTE.length] + '">' + initial(c.name_ar) + '</div><div class="grow"><div class="t">' + escapeHtml(STATE.lang === "ar" ? c.name_ar : c.name_en || c.name_ar) + '</div><div class="s">' + escapeHtml(c.reason || "") + "</div></div>" + healthBadge(c.health) + "</div>";
            }).join("") + "</div>"
          : '<p class="av-empty">' + dual("لا توجد شركات تحتاج متابعة.", "No companies need attention.") + "</p>") +
        "</div>" +
        '<div class="av-panel"><h3>' + dual("شركات لم ترسل التقرير", "Companies missing a report") + "</h3>" +
        (missing.length
          ? '<div class="av-list">' + missing.map(function (c) {
              return '<div class="av-row" data-invest-co="' + c.id + '"><div class="co-dot" style="background:' + PALETTE[c.id % PALETTE.length] + '">' + initial(c.name_ar) + '</div><div class="grow"><div class="t">' + escapeHtml(STATE.lang === "ar" ? c.name_ar : c.name_en || c.name_ar) + '</div><div class="s">' + dual("بانتظار التقرير الشهري", "Awaiting report") + "</div></div></div>";
            }).join("") + "</div>"
          : '<p class="av-empty">' + dual("جميع الشركات أرسلت تقاريرها.", "All companies submitted reports.") + "</p>") +
        "</div>" +
        '<div class="av-panel"><h3>' + dual("مؤشرات المجموعة", "Group indicators") + "</h3>" + groupIndicators() + "</div>" +
        "</div>";
      host.querySelectorAll("[data-invest-co]").forEach(function (el) {
        el.addEventListener("click", function () {
          openCompany(parseInt(el.getAttribute("data-invest-co"), 10));
        });
      });
    });
  }

  function groupIndicators() {
    var k = (STATE.dashboard && STATE.dashboard.kpis) || {};
    var change = (STATE.dashboard && STATE.dashboard.change_vs_previous) || {};
    var margin = k.total_revenue && Number(k.total_revenue)
      ? ((Number(k.total_net_result) / Number(k.total_revenue)) * 100).toFixed(1)
      : "—";
    return (
      '<div class="kv">' +
      kv(dual("إجمالي الإيرادات", "Total revenue"), dual(money(k.total_revenue).ar, money(k.total_revenue).en)) +
      kv(dual("صافي النتائج", "Net result"), dual(money(k.total_net_result).ar, money(k.total_net_result).en)) +
      kv(dual("هامش الربح", "Net margin"), dual(toArabicDigits(margin) + "٪", margin + "%")) +
      kv(dual("نمو الإيرادات", "Revenue growth"), change.revenue_pct === null || change.revenue_pct === undefined ? dual("—", "—") : dual(toArabicDigits(change.revenue_pct.toFixed(1)) + "٪", change.revenue_pct.toFixed(1) + "%")) +
      "</div>"
    );
  }

  // ---- business intelligence view --------------------------------------
  function renderBi() {
    var host = byId("biContent");
    if (!host) return Promise.resolve();
    host.innerHTML = loadingHtml();
    return Promise.all([loadInsights(true), ensureReports(), ensureCompanies()]).then(function () {
      var insights = STATE.insights;
      host.innerHTML =
        '<div class="av-panel" style="margin-bottom:12px"><h3>' + dual("رؤى تنفيذية", "Executive insights") + "</h3>" +
        (insights.length
          ? '<div class="av-list">' + insights.map(function (i) {
              return '<div class="av-row" style="cursor:default"><div class="grow"><div class="t">' + escapeHtml(STATE.lang === "ar" ? i.title_ar : i.title_en) + '</div><div class="s">' + escapeHtml(STATE.lang === "ar" ? i.detail_ar : i.detail_en) + "</div></div>" + (i.metric ? '<span class="ins-tag">' + escapeHtml(i.metric) + "</span>" : "") + "</div>";
            }).join("") + "</div>"
          : '<p class="av-empty">' + dual("لا توجد رؤى لهذه الفترة.", "No insights for this period.") + "</p>") +
        "</div>" +
        '<div class="av-grid cols-2">' +
        '<div class="av-panel"><h3>' + dual("أداء الشركات", "Company performance") + "</h3>" + biCompanyTable() + "</div>" +
        '<div class="av-panel"><h3>' + dual("مؤشرات المجموعة", "Group indicators") + "</h3>" + groupIndicators() + "</div>" +
        "</div>";
    });
  }

  function biCompanyTable() {
    var rows = (STATE.dashboard && STATE.dashboard.companies_performance) || [];
    if (!rows.length) return '<p class="av-empty">' + dual("لا توجد بيانات.", "No data.") + "</p>";
    return (
      '<div class="av-list">' + rows.map(function (r) {
        var rev = money(r.revenue);
        var net = money(r.net_result);
        return (
          '<div class="av-row" data-bi-co="' + r.id + '"><div class="co-dot" style="background:' + PALETTE[r.id % PALETTE.length] + '">' + initial(r.name_ar) + "</div>" +
          '<div class="grow"><div class="t">' + escapeHtml(STATE.lang === "ar" ? r.name_ar : r.name_en || r.name_ar) + '</div>' +
          '<div class="s">' + dual("إيرادات ", "Revenue ") + dual(rev.ar, rev.en) + " · " + dual("صافي ", "Net ") + dual(net.ar, net.en) + "</div>" +
          goalsHtml(r.goals) + "</div>" +
          growthHtml(r.revenue_pct) + healthBadge(r.health) + "</div>"
        );
      }).join("") + "</div>"
    );
  }

  // S02/S10: goals-versus-results. A goal is an approved (active) KPI with a
  // target; the API already resolved the actual against the same metric. We
  // show target, actual and the favourable/unfavourable flag — never a figure
  // the API did not return.
  function goalsHtml(goals) {
    if (!goals || !goals.length) return "";
    return goals.map(function (g) {
      var name = STATE.lang === "ar" ? g.name_ar : g.name_en || g.name_ar;
      var target = dec(g.target_value);
      var actual = g.actual_value == null ? "—" : dec(g.actual_value);
      var cls = g.favourable === false ? "warn" : "ok";
      var arrow = g.favourable === false ? "▼" : "▲";
      return (
        '<div class="s" style="margin-top:2px">' +
        '<span class="status ' + cls + '"><i></i>' + escapeHtml(name) + " " + arrow + " " +
        escapeHtml(target) + " / " + escapeHtml(actual) + "</span></div>"
      );
    }).join("");
  }

  // ---- advanced analytics view -----------------------------------------
  //
  // Each tab is gated by the permission its endpoint requires, so a user with
  // only `analytics.company` never issues a request the API would reject. All
  // figures come straight from the API; nothing here invents a number.
  var AN_TABS = ["briefing", "holding", "operations", "compliance", "investments"];
  var AN_TAB_PERM = {
    briefing: ["analytics.holding", "analytics.company", "analytics.operations"],
    holding: ["analytics.holding"],
    operations: ["analytics.operations"],
    compliance: ["analytics.compliance"],
    investments: ["analytics.holding"],
  };

  function canAnTab(tab) {
    return (AN_TAB_PERM[tab] || []).some(has);
  }

  function renderAnalytics() {
    var host = byId("anContent");
    if (!host) return Promise.resolve();
    if (!STATE.anTab || !canAnTab(STATE.anTab)) STATE.anTab = "briefing";
    if (!STATE.anBound) {
      STATE.anBound = true;
      document.querySelectorAll("[data-an-tab]").forEach(function (btn) {
        btn.addEventListener("click", function () {
          var tab = btn.getAttribute("data-an-tab");
          if (!canAnTab(tab)) return;
          STATE.anTab = tab;
          document.querySelectorAll("[data-an-tab]").forEach(function (b) {
            b.classList.toggle("on", b === btn);
          });
          renderAnalyticsTab(tab);
        });
      });
    }
    document.querySelectorAll("[data-an-tab]").forEach(function (b) {
      b.classList.toggle("on", b.getAttribute("data-an-tab") === STATE.anTab);
    });
    return renderAnalyticsTab(STATE.anTab);
  }

  function renderAnalyticsTab(tab) {
    var host = byId("anContent");
    if (!host) return Promise.resolve();
    host.innerHTML = loadingHtml();
    if (tab === "briefing") return renderBriefing(host);
    if (tab === "holding") return renderHoldingOverview(host);
    if (tab === "operations") return renderOperations(host);
    if (tab === "compliance") return renderCompliance(host);
    if (tab === "investments") return renderInvestmentReport(host);
    return Promise.resolve();
  }

  // A compact bar chart. ``values`` are raw numbers; the caller supplies the
  // label pair for each bar. Zero-height bars are drawn as a hairline so an
  // empty month reads as "no data" rather than "missing".
  function barChart(values, labels, opts) {
    var o = opts || {};
    var max = Math.max.apply(null, values.concat([0]));
    var scale = max > 0 ? max : 1;
    return (
      '<div class="an-chart">' +
      values.map(function (v, i) {
        var h = v <= 0 ? 2 : Math.max(4, Math.round((v / scale) * 100));
        var tone = o.tone ? o.tone(v, i) : "";
        return (
          '<div class="an-bar" title="' + escAttr(labels[i].en) + '">' +
          '<div class="an-bar-fill ' + tone + '" style="height:' + h + '%"></div>' +
          '<span class="an-bar-x">' + labels[i].short + "</span>" +
          "</div>"
        );
      }).join("") +
      "</div>"
    );
  }

  function trendLabels(points) {
    return points.map(function (p) {
      return {
        short: toArabicDigits(String(p.month)) + "/" + String(p.year).slice(2),
        en: p.year + "-" + String(p.month).padStart(2, "0"),
      };
    });
  }

  function renderHoldingOverview(host) {
    return get("/api/v1/analytics/holding" + period)
      .then(function (data) {
        var trend = data.trend || [];
        var c = data.compliance || {};
        var movers = data.movers || { top: [], bottom: [] };
        host.innerHTML =
          '<div class="av-panel" style="margin-bottom:11px"><h3>' +
          dual("اتجاه الإيرادات · آخر ١٢ شهراً", "Revenue trend · last 12 months") +
          "</h3>" +
          barChart(
            trend.map(function (p) { return p.revenue; }),
            trendLabels(trend),
            { tone: function () { return "gold"; } },
          ) +
          "</div>" +
          '<div class="av-grid cols-3">' +
          '<div class="av-panel"><h3>' + dual("الالتزام بالتقارير", "Reporting compliance") + "</h3>" +
          '<div class="kv">' +
          kv(dual("إجمالي الشركات", "Companies"), plainNum(c.companies_total)) +
          kv(dual("أرسلت التقرير", "Reported"), plainNum(c.companies_reported)) +
          kv(dual("بانتظار التقرير", "Missing"), plainNum(c.companies_missing)) +
          kv(dual("نسبة الالتزام", "Compliance"), dual(toArabicDigits(String(c.compliance_pct)) + "٪", String(c.compliance_pct) + "%")) +
          "</div></div>" +
          '<div class="av-panel"><h3>' + dual("أعلى نمو", "Top movers") + "</h3>" + moverList(movers.top) + "</div>" +
          '<div class="av-panel"><h3>' + dual("أدنى أداء", "Bottom movers") + "</h3>" + moverList(movers.bottom) + "</div>" +
          "</div>" +
          '<div class="av-grid cols-2" style="margin-top:11px">' +
          '<div class="av-panel"><h3>' + dual("توزيع القطاعات", "Sector mix") + "</h3>" + sectorMix(data.sectors) + "</div>" +
          '<div class="av-panel"><h3>' + dual("الحالة التشغيلية", "Health distribution") + "</h3>" + healthMix(data.health_distribution) + "</div>" +
          "</div>";
      })
      .catch(function (err) { host.innerHTML = errorHtml(errText(err)); });
  }

  function moverList(rows) {
    if (!rows || !rows.length) {
      return '<p class="av-empty">' + dual("لا توجد بيانات كافية للمقارنة.", "Not enough data to compare.") + "</p>";
    }
    return (
      '<div class="av-list">' + rows.map(function (m) {
        return (
          '<div class="av-row" data-an-co="' + m.company_id + '" style="cursor:default">' +
          '<div class="grow"><div class="t">' + escapeHtml(STATE.lang === "ar" ? m.name_ar : m.name_en || m.name_ar) + "</div>" +
          '<div class="s">' + dual("إيرادات ", "Revenue ") + dual(money(m.revenue).ar, money(m.revenue).en) + "</div></div>" +
          growthHtml(m.change_pct) + "</div>"
        );
      }).join("") + "</div>"
    );
  }

  function sectorMix(rows) {
    if (!rows || !rows.length) {
      return '<p class="av-empty">' + dual("لا توجد بيانات قطاعات.", "No sector data.") + "</p>";
    }
    return (
      '<div class="av-list">' + rows.map(function (s) {
        return (
          '<div class="av-row" style="cursor:default"><div class="grow">' +
          '<div class="t">' + escapeHtml(s.sector || "—") + "</div>" +
          '<div class="s">' + dual(plainNum(s.companies) + " شركة", plainNum(s.companies) + " companies") + "</div></div>" +
          '<span class="ins-tag gold">' + dual(money(s.revenue).ar, money(s.revenue).en) + "</span></div>"
        );
      }).join("") + "</div>"
    );
  }

  function healthMix(rows) {
    if (!rows || !rows.length) {
      return '<p class="av-empty">' + dual("لا توجد بيانات.", "No data.") + "</p>";
    }
    return (
      '<div class="av-list">' + rows.map(function (h) {
        return (
          '<div class="av-row" style="cursor:default">' + healthBadge(h.health) +
          '<div class="grow"></div><span class="num">' + plainNum(h.companies) + "</span></div>"
        );
      }).join("") + "</div>"
    );
  }

  function renderOperations(host) {
    return get("/api/v1/analytics/operations" + period)
      .then(function (data) {
        var cyc = data.approval_cycle || {};
        var thr = data.support_throughput || {};
        host.innerHTML =
          '<div class="av-grid cols-3">' +
          '<div class="av-panel"><h3>' + dual("دورة الموافقات", "Approval cycle") + "</h3>" +
          '<div class="kv">' +
          kv(dual("مكتملة", "Completed"), plainNum(cyc.completed)) +
          kv(dual("متوسط الساعات", "Average hours"), hours(cyc.average_hours)) +
          kv(dual("الأسرع", "Fastest"), hours(cyc.fastest_hours)) +
          kv(dual("الأبطأ", "Slowest"), hours(cyc.slowest_hours)) +
          "</div></div>" +
          '<div class="av-panel"><h3>' + dual("إنتاجية الدعم", "Support throughput") + "</h3>" +
          '<div class="kv">' +
          kv(dual("طلبات مغلقة", "Closed requests"), plainNum(thr.closed_requests)) +
          kv(dual("متوسط الإغلاق", "Average close"), hours(thr.average_hours)) +
          "</div></div>" +
          '<div class="av-panel"><h3>' + dual("طلبات حسب الحالة", "Requests by status") + "</h3>" + statusCounts(data.requests_by_status) + "</div>" +
          "</div>" +
          '<div class="av-grid cols-2" style="margin-top:11px">' +
          '<div class="av-panel"><h3>' + dual("اختناقات الموافقات", "Approval bottlenecks") + "</h3>" + bottlenecks(data.approval_bottlenecks) + "</div>" +
          '<div class="av-panel"><h3>' + dual("الدعم حسب النوع", "Support by category") + "</h3>" + supportByCategory(data.support_by_category) + "</div>" +
          "</div>";
      })
      .catch(function (err) { host.innerHTML = errorHtml(errText(err)); });
  }

  function hours(v) {
    return v === null || v === undefined ? dual("—", "—") : dual(toArabicDigits(String(v)), String(v));
  }

  function statusCounts(rows) {
    if (!rows || !rows.length) return '<p class="av-empty">' + dual("لا توجد بيانات.", "No data.") + "</p>";
    return (
      '<div class="av-list">' + rows.map(function (r) {
        return '<div class="av-row" style="cursor:default"><div class="grow"><div class="t">' + escapeHtml(statusLabel(r.status).ar) + "</div></div>" + '<span class="num">' + plainNum(r.count) + "</span></div>";
      }).join("") + "</div>"
    );
  }

  function bottlenecks(rows) {
    if (!rows || !rows.length) return '<p class="av-empty">' + dual("لا توجد اختناقات.", "No bottlenecks.") + "</p>";
    return (
      '<div class="av-list">' + rows.map(function (b) {
        return '<div class="av-row" style="cursor:default"><div class="grow"><div class="t">' + escapeHtml(STATE.lang === "ar" ? b.name_ar || "—" : b.name_en || b.name_ar || "—") + "</div></div>" + '<span class="ins-tag warn">' + dual(plainNum(b.pending) + " معلّق", plainNum(b.pending) + " pending") + "</span></div>";
      }).join("") + "</div>"
    );
  }

  function supportByCategory(rows) {
    if (!rows || !rows.length) return '<p class="av-empty">' + dual("لا توجد طلبات.", "No requests.") + "</p>";
    return (
      '<div class="av-list">' + rows.map(function (r) {
        return '<div class="av-row" style="cursor:default"><div class="grow"><div class="t">' + escapeHtml((CATEGORY[r.category] || CATEGORY.general).ar) + '</div><div class="s">' + dual("مفتوحة ", "Open ") + plainNum(r.open) + " · " + dual("مغلقة ", "Closed ") + plainNum(r.closed) + "</div></div>" + '<span class="num">' + plainNum(r.total) + "</span></div>";
      }).join("") + "</div>"
    );
  }

  function renderCompliance(host) {
    return get("/api/v1/analytics/compliance" + period)
      .then(function (data) {
        var d = data.documents || {};
        var r = data.reporting || {};
        host.innerHTML =
          '<div class="av-grid cols-2">' +
          '<div class="av-panel"><h3>' + dual("حالة المستندات", "Document exposure") + "</h3>" +
          '<div class="kv">' +
          kv(dual("منتهية", "Expired"), plainNum(d.expired)) +
          kv(dual("قاربت الانتهاء", "Expiring soon"), plainNum(d.expiring_soon)) +
          kv(dual("سارية", "Valid"), plainNum(d.valid)) +
          kv(dual("بدون تاريخ", "No expiry"), plainNum(d.none)) +
          "</div></div>" +
          '<div class="av-panel"><h3>' + dual("الالتزام بالتقارير", "Reporting compliance") + "</h3>" +
          '<div class="kv">' +
          kv(dual("إجمالي الشركات", "Companies"), plainNum(r.companies_total)) +
          kv(dual("أرسلت", "Reported"), plainNum(r.companies_reported)) +
          kv(dual("قيد المراجعة", "Reviewed"), plainNum(r.companies_reviewed)) +
          kv(dual("نسبة الالتزام", "Compliance"), dual(toArabicDigits(String(r.compliance_pct)) + "٪", String(r.compliance_pct) + "%")) +
          "</div></div>" +
          "</div>" +
          '<div class="av-grid cols-2" style="margin-top:11px">' +
          '<div class="av-panel"><h3>' + dual("المستندات حسب التصنيف", "Documents by category") + "</h3>" + docCategories(data.documents_by_category) + "</div>" +
          '<div class="av-panel"><h3>' + dual("بيانات مالية تحتاج مراجعة", "Financials flagged for review") + "</h3>" + flagged(data.flagged_financials) + "</div>" +
          "</div>";
      })
      .catch(function (err) { host.innerHTML = errorHtml(errText(err)); });
  }

  function docCategories(rows) {
    if (!rows || !rows.length) return '<p class="av-empty">' + dual("لا توجد مستندات.", "No documents.") + "</p>";
    return (
      '<div class="av-list">' + rows.map(function (c) {
        return '<div class="av-row" style="cursor:default"><div class="grow"><div class="t">' + escapeHtml(STATE.lang === "ar" ? c.name_ar : c.name_en || c.name_ar) + "</div></div>" + '<span class="num">' + plainNum(c.count) + "</span></div>";
      }).join("") + "</div>"
    );
  }

  function flagged(rows) {
    if (!rows || !rows.length) return '<p class="av-empty">' + dual("لا توجد بيانات مالية معلَّمة.", "No flagged financials.") + "</p>";
    return (
      '<div class="av-list">' + rows.map(function (f) {
        return '<div class="av-row" data-an-co="' + f.company_id + '"><div class="grow"><div class="t">' + escapeHtml(STATE.lang === "ar" ? f.name_ar : f.name_en || f.name_ar) + "</div></div>" + '<span class="ins-tag risk">' + dual(plainNum(f.flagged_reviews) + " مراجعة", plainNum(f.flagged_reviews) + " reviews") + "</span></div>";
      }).join("") + "</div>"
    );
  }

  function renderInvestmentReport(host) {
    return get("/api/v1/analytics/investments" + period)
      .then(function (data) {
        host.innerHTML =
          '<div class="av-panel" style="margin-bottom:11px"><h3>' + dual("مؤشرات المحفظة", "Portfolio indicators") + "</h3>" +
          '<div class="kv">' +
          kv(dual("إيرادات المحفظة", "Portfolio revenue"), dual(money(data.portfolio_revenue).ar, money(data.portfolio_revenue).en)) +
          kv(dual("صافي المحفظة", "Portfolio net"), dual(money(data.portfolio_net).ar, money(data.portfolio_net).en)) +
          kv(dual("متوسط الهامش", "Average margin"), data.average_margin_pct === null ? dual("—", "—") : dual(toArabicDigits(String(data.average_margin_pct)) + "٪", String(data.average_margin_pct) + "%")) +
          kv(dual("فرص مرصودة", "Opportunities reported"), plainNum(data.opportunities_reported)) +
          "</div></div>" +
          '<div class="av-panel"><h3>' + dual("الشركات الاستثمارية", "Investment companies") + "</h3>" +
          ((data.companies || []).length
            ? '<div class="av-list">' + data.companies.map(function (c) {
                return (
                  '<div class="av-row" data-an-co="' + c.company_id + '">' +
                  '<div class="co-dot" style="background:' + PALETTE[c.company_id % PALETTE.length] + '">' + initial(c.name_ar) + "</div>" +
                  '<div class="grow"><div class="t">' + escapeHtml(STATE.lang === "ar" ? c.name_ar : c.name_en) + "</div>" +
                  '<div class="s">' + dual("إيرادات ", "Revenue ") + dual(money(c.revenue).ar, money(c.revenue).en) + " · " + dual("مستحقات ", "Receivables ") + dual(money(c.outstanding_receivables).ar, money(c.outstanding_receivables).en) + "</div></div>" +
                  (c.has_opportunity ? '<span class="ins-tag gold">' + dual("فرصة", "Opportunity") + "</span>" : "") +
                  healthBadge(c.health) + "</div>"
                );
              }).join("") + "</div>"
            : '<p class="av-empty">' + dual("لا توجد بيانات.", "No data.") + "</p>") +
          "</div>";
        host.querySelectorAll("[data-an-co]").forEach(function (el) {
          el.addEventListener("click", function () {
            openCompany(parseInt(el.getAttribute("data-an-co"), 10));
          });
        });
      })
      .catch(function (err) { host.innerHTML = errorHtml(errText(err)); });
  }

  // ---- executive briefing ----------------------------------------------
  function renderBriefing(host) {
    return get("/api/v1/analytics/briefing" + period)
      .then(function (data) {
        var toneTag = { positive: "up", caution: "warn", risk: "risk", opportunity: "gold" };
        host.innerHTML =
          '<div class="av-grid cols-2">' +
          '<div class="av-panel brief-hero">' +
          '<div class="brief-head">' +
          '<span class="brief-badge">' + dual("مُستمد من البيانات الحيّة", "Grounded in live data") + "</span>" +
          (data.degraded ? '<span class="ins-tag warn">' + dual("مزوّد الذكاء غير مهيّأ — ملخص تحليلي", "AI provider not configured — analytical summary") + "</span>" : "") +
          "</div>" +
          '<p class="brief-summary"><span class="ar">' + escapeHtml(data.summary_ar) + '</span><span class="en">' + escapeHtml(data.summary_en) + "</span></p>" +
          '<div class="brief-meta">' + dual("الفترة ", "Period ") + dual(periodLabel().ar, periodLabel().en) + " · " + dual("المصدر ", "Source ") + escapeHtml(data.provider) + "</div>" +
          "</div>" +
          '<div class="av-panel"><h3>' + dual("أبرز النقاط", "Highlights") + "</h3>" + briefingList(data.highlights, toneTag) + "</div>" +
          "</div>" +
          '<div class="av-grid cols-3" style="margin-top:11px">' +
          '<div class="av-panel"><h3>' + dual("المخاطر", "Risks") + "</h3>" + briefingList(data.risks, toneTag) + "</div>" +
          '<div class="av-panel"><h3>' + dual("الفرص", "Opportunities") + "</h3>" + briefingList(data.opportunities, toneTag) + "</div>" +
          '<div class="av-panel"><h3>' + dual("إجراءات مقترحة", "Recommended actions") + "</h3>" + actionList(data.recommended_actions) + "</div>" +
          "</div>";
      })
      .catch(function (err) { host.innerHTML = errorHtml(errText(err)); });
  }

  function briefingList(items, toneTag) {
    if (!items || !items.length) return '<p class="av-empty">' + dual("لا توجد عناصر.", "Nothing to report.") + "</p>";
    return (
      '<div class="av-list">' + items.map(function (i) {
        var tone = toneTag[i.tone] || "";
        return (
          '<div class="av-row" style="cursor:default"><div class="grow">' +
          '<div class="t">' + escapeHtml(STATE.lang === "ar" ? i.text_ar : i.text_en) + "</div></div>" +
          (tone ? '<span class="ins-tag ' + tone + '">' + escapeHtml(i.key) + "</span>" : "") +
          "</div>"
        );
      }).join("") + "</div>"
    );
  }

  function actionList(items) {
    if (!items || !items.length) return '<p class="av-empty">' + dual("لا توجد إجراءات.", "No actions.") + "</p>";
    return (
      '<div class="av-list">' + items.map(function (a) {
        return '<div class="av-row" style="cursor:default"><div class="grow"><div class="t">' + escapeHtml(STATE.lang === "ar" ? a.text_ar : a.text_en) + "</div></div></div>";
      }).join("") + "</div>"
    );
  }

  // ---- notification centre ---------------------------------------------
  function renderInbox() {
    var host = byId("inboxContent");
    if (!host) return Promise.resolve();
    if (!STATE.inboxBound) {
      STATE.inboxBound = true;
      var all = byId("inboxAll");
      var unread = byId("inboxUnread");
      var readAll = byId("inboxReadAll");
      if (all) all.addEventListener("click", function () {
        STATE.notifFilter = "all";
        all.classList.add("on");
        if (unread) unread.classList.remove("on");
        renderInboxList();
      });
      if (unread) unread.addEventListener("click", function () {
        STATE.notifFilter = "unread";
        unread.classList.add("on");
        if (all) all.classList.remove("on");
        renderInboxList();
      });
      if (readAll) readAll.addEventListener("click", function () {
        post("/api/v1/notifications/read-all", {}).then(function () {
          refreshNotifications();
          renderInboxList();
        });
      });
      var prefsBtn = byId("inboxPrefs");
      if (prefsBtn) prefsBtn.addEventListener("click", function () {
        var panelHost = byId("inboxPrefsPanel");
        var hidden = panelHost.classList.toggle("view-hidden");
        prefsBtn.classList.toggle("on", !hidden);
        if (!hidden) renderNotificationPreferences();
      });
    }
    host.innerHTML = loadingHtml();
    return refreshNotifications().then(renderInboxList);
  }

  function renderInboxList() {
    var host = byId("inboxContent");
    if (!host) return Promise.resolve();
    var items = STATE.notifications || [];
    if (STATE.notifFilter === "unread") {
      items = items.filter(function (n) { return !n.is_read; });
    }
    if (!items.length) {
      host.innerHTML = '<div class="av-panel">' + emptyHtml("لا توجد إشعارات.", "No notifications.") + "</div>";
      return Promise.resolve();
    }
    host.innerHTML =
      '<div class="av-panel"><div class="av-list">' + items.map(function (n) {
        return (
          '<div class="av-row notif-row' + (n.is_read ? "" : " unread") + '" data-notif="' + n.id + '">' +
          '<span class="notif-pri ' + n.priority + '"></span>' +
          '<div class="grow"><div class="t">' + escapeHtml(STATE.lang === "ar" ? n.title_ar : n.title_en) + "</div>" +
          '<div class="s">' + escapeHtml(STATE.lang === "ar" ? n.message_ar : n.message_en) + "</div>" +
          '<div class="s notif-time">' + fmtDateTime(n.created_at) + "</div></div>" +
          "</div>"
        );
      }).join("") + "</div></div>";
    host.querySelectorAll("[data-notif]").forEach(function (el) {
      el.addEventListener("click", function () {
        var id = parseInt(el.getAttribute("data-notif"), 10);
        var row = (STATE.notifications || []).filter(function (n) { return n.id === id; })[0];
        post("/api/v1/notifications/" + id + "/read", {}).then(function () {
          if (row) row.is_read = true;
          refreshNotifications();
          renderInboxList();
        });
      });
    });
    return Promise.resolve();
  }

  // D11: per-event channel preferences. In-app is the base channel; email is
  // opt-in. The preference is what the notify pipeline reads, so muting here
  // is exactly what stops an event appearing in the list above.
  function renderNotificationPreferences() {
    var host = byId("inboxPrefsPanel");
    if (!host) return Promise.resolve();
    host.innerHTML = loadingHtml();
    return get("/api/v1/notifications/preferences").then(function (data) {
      var items = (data && data.items) || [];
      var events = (data && data.event_types) || [];
      var byEvent = {};
      items.forEach(function (p) { byEvent[p.event_type] = p; });
      var defaultRow = byEvent["*"] || { in_app: true, email: false, muted: false };
      var rows = ["*"].concat(
        events.filter(function (e) { return e !== "*"; })
      );
      var body =
        '<div class="av-list">' +
        rows.map(function (key) {
          var p = byEvent[key] || defaultRow;
          var label = key === "*"
            ? dual("الافتراضي لكل الأحداث", "Default for all events")
            : escapeHtml(NOTIF_EVENT_LABEL[key] ? (STATE.lang === "ar" ? NOTIF_EVENT_LABEL[key].ar : NOTIF_EVENT_LABEL[key].en) : key);
          return (
            '<div class="av-row" style="cursor:default"><div class="grow"><div class="t">' +
            label + "</div></div>" +
            toggleBtn(key, "in_app", p.in_app, "داخل المنصة", "In-app") +
            toggleBtn(key, "email", p.email, "البريد", "Email") +
            toggleBtn(key, "muted", p.muted, "كتم", "Mute") +
            "</div>"
          );
        }).join("") + "</div>";
      host.innerHTML = panel(
        "تفضيلات القنوات (D11: القناة الأساسية داخل المنصة؛ البريد اختياري)",
        "Channel preferences (D11: in-app is the base channel; email is optional)",
        body
      );
      host.querySelectorAll("[data-pref]").forEach(function (btn) {
        btn.addEventListener("click", function () {
          var ev = btn.getAttribute("data-pref");
          var field = btn.getAttribute("data-field");
          var next = btn.getAttribute("data-on") !== "1";
          var payload = {};
          payload[field] = next;
          busy(btn, true);
          put("/api/v1/notifications/preferences/" + encodeURIComponent(ev), payload)
            .then(function () { return renderNotificationPreferences(); })
            .catch(function (err) { domainError(err); busy(btn, false); });
        });
      });
    }).catch(function (err) { handleLoadError(err); host.innerHTML = errorHtml(errText(err)); });
  }

  // Arabic/English labels for the notification event types the backend defines
  // (NotificationType). An unlabelled type falls back to its raw code.
  var NOTIF_EVENT_LABEL = {
    "system": { ar: "النظام", en: "System" },
    "approval.assigned": { ar: "موافقة مُسندة", en: "Approval assigned" },
    "approval.approved": { ar: "موافقة معتمدة", en: "Approval approved" },
    "approval.rejected": { ar: "موافقة مرفوضة", en: "Approval rejected" },
    "approval.returned": { ar: "موافقة مُعادة", en: "Approval returned" },
    "submission.incomplete": { ar: "إرسال غير مكتمل", en: "Submission incomplete" },
    "document.expiring": { ar: "مستند على وشك الانتهاء", en: "Document expiring" },
    "document.expired": { ar: "مستند منتهي", en: "Document expired" },
    "report.submitted": { ar: "تقرير شهري مُرسل", en: "Monthly report submitted" },
    "financial_summary.submitted": { ar: "ملخص مالي مُرسل", en: "Financial summary submitted" },
    "financial_summary.returned": { ar: "ملخص مالي مُعاد", en: "Financial summary returned" },
    "financial_summary.resubmitted": { ar: "ملخص مالي مُعاد إرساله", en: "Financial summary resubmitted" },
    "financial_summary.approved": { ar: "ملخص مالي معتمد", en: "Financial summary approved" },
    "support.assigned": { ar: "طلب دعم مُسند", en: "Support assigned" },
    "support.status_changed": { ar: "تغيّر حالة طلب", en: "Support status changed" },
  };

  function toggleBtn(eventKey, field, on, ar, en) {
    return (
      '<button class="btn-ghost" data-pref="' + escAttr(eventKey) + '" data-field="' + field +
      '" data-on="' + (on ? "1" : "0") + '" style="margin-inline-start:6px">' +
      dual(ar, en) + " " + (on ? "✓" : "✕") + "</button>"
    );
  }

  // ---- website leads view ---------------------------------------------
  var LEAD_SERVICE = {
    company_formation: { ar: "تأسيس شركة", en: "Company formation" },
    feasibility_study: { ar: "دراسة جدوى", en: "Feasibility study" },
    opportunity_interest: { ar: "اهتمام بفرصة", en: "Opportunity interest" },
    business_listing: { ar: "عرض شركة", en: "Business listing" },
    investment: { ar: "استثمار", en: "Investment" },
    general_contact: { ar: "تواصل عام", en: "General contact" },
  };
  var LEAD_MARKET = {
    bahrain: { ar: "البحرين", en: "Bahrain" },
    saudi: { ar: "السعودية", en: "Saudi Arabia" },
  };
  var LEAD_STATUS = {
    new: { ar: "جديد", en: "New", cls: "rev" },
    in_progress: { ar: "قيد المعالجة", en: "In progress", cls: "ok" },
    contacted: { ar: "تم التواصل", en: "Contacted", cls: "ok" },
    converted: { ar: "مُحوَّل", en: "Converted", cls: "ok" },
    closed: { ar: "مغلق", en: "Closed", cls: "ok" },
    rejected: { ar: "مرفوض", en: "Rejected", cls: "miss" },
  };
  var LEAD_PRIORITY = {
    low: { ar: "منخفضة", en: "Low" },
    normal: { ar: "عادية", en: "Normal" },
    high: { ar: "مرتفعة", en: "High" },
    urgent: { ar: "عاجلة", en: "Urgent" },
  };

  function leadLabel(map, value) {
    return map[value] || { ar: value || "—", en: value || "—" };
  }

  var OPPORTUNITY_STATUS = {
    submitted: { ar: "مُقدَّم", en: "Submitted", cls: "warn" },
    under_review: { ar: "قيد المراجعة", en: "Under review", cls: "warn" },
    published: { ar: "منشور", en: "Published", cls: "ok" },
    rejected: { ar: "مرفوض", en: "Rejected", cls: "miss" },
  };
  var OPPORTUNITY_TYPE = {
    for_sale: { ar: "للبيع", en: "For sale" },
    partnership: { ar: "شراكة", en: "Partnership" },
    investment: { ar: "استثمار", en: "Investment" },
  };

  // ---- review queue for submitted listings (S13) ----------------------
  function renderOpportunities() {
    var host = byId("oppContent");
    if (!host) return Promise.resolve();
    if (!STATE.oppBound) {
      STATE.oppBound = true;
      document.querySelectorAll("[data-opp-filter]").forEach(function (btn) {
        btn.addEventListener("click", function () {
          document.querySelectorAll("[data-opp-filter]").forEach(function (b) { b.classList.remove("on"); });
          btn.classList.add("on");
          STATE.oppStatus = btn.getAttribute("data-opp-filter") || "";
          renderOpportunities();
        });
      });
    }
    host.innerHTML = loadingHtml();
    return get("/api/v1/leads/opportunities")
      .then(function (rows) {
        var list = (rows || []).filter(function (o) { return !STATE.oppStatus || o.status === STATE.oppStatus; });
        if (!list.length) {
          host.innerHTML = noticeHtml("لا توجد عروض في هذه الحالة.", "No listings in this state.");
          return;
        }
        host.innerHTML = '<div class="av-panel"><div class="av-list">' + list.map(opportunityRow).join("") + "</div></div>";
        host.querySelectorAll("[data-opp]").forEach(function (row) {
          row.addEventListener("click", function () {
            openOpportunity(parseInt(row.getAttribute("data-opp"), 10));
          });
        });
      })
      .catch(function (err) { handleLoadError(err); host.innerHTML = errorHtml(errText(err)); });
  }

  function opportunityRow(o) {
    var status = leadLabel(OPPORTUNITY_STATUS, o.status);
    var type = leadLabel(OPPORTUNITY_TYPE, o.opportunity_type);
    var market = leadLabel(LEAD_MARKET, o.market);
    return (
      '<div class="av-row" data-opp="' + o.id + '" style="cursor:pointer">' +
      '<div class="grow"><div class="t">' +
      escapeHtml(STATE.lang === "ar" ? (o.public_title_ar || o.sector || ("عرض #" + o.id)) : (o.public_title_en || o.sector || ("Listing #" + o.id))) +
      "</div><div class=\"s\">" +
      dual(escapeHtml(type.ar), escapeHtml(type.en)) + " · " +
      dual(escapeHtml(market.ar), escapeHtml(market.en)) +
      (o.is_public ? " · " + dual("منشور علنًا", "public") : "") + "</div></div>" +
      '<span class="status ' + (status.cls || "") + '"><i></i>' + dual(escapeHtml(status.ar), escapeHtml(status.en)) + "</span>" +
      "</div>"
    );
  }

  function openOpportunity(id) {
    return get("/api/v1/leads/opportunities").then(function (rows) {
      var o = (rows || []).filter(function (x) { return x.id === id; })[0];
      if (!o) return;
      var canReview = has("website_opportunity.review");
      var canPublish = has("website_opportunity.publish");
      var money = function (v) { return v == null ? "—" : dec(v); };
      var body =
        '<div class="kv">' +
        kv(dual("النوع", "Type"), dual(escapeHtml(leadLabel(OPPORTUNITY_TYPE, o.opportunity_type).ar), escapeHtml(leadLabel(OPPORTUNITY_TYPE, o.opportunity_type).en))) +
        kv(dual("السوق", "Market"), dual(escapeHtml(leadLabel(LEAD_MARKET, o.market).ar), escapeHtml(leadLabel(LEAD_MARKET, o.market).en))) +
        kv(dual("الصفة", "Capacity"), escapeHtml(o.applicant_capacity || "—")) +
        kv(dual("القطاع", "Sector"), escapeHtml(o.sector || "—")) +
        kv(dual("عمر النشاط", "Business age"), o.business_age_years == null ? "—" : plainNum(o.business_age_years) + " " + dual("سنة", "yrs")) +
        kv(dual("نطاق القيمة", "Value range"), escapeHtml(money(o.value_min)) + " – " + escapeHtml(money(o.value_max)) + " " + escapeHtml(o.currency || "")) +
        kv(dual("الحالة", "Status"), dual(escapeHtml(leadLabel(OPPORTUNITY_STATUS, o.status).ar), escapeHtml(leadLabel(OPPORTUNITY_STATUS, o.status).en))) +
        "</div>" +
        (o.description ? '<div class="sec-title">' + dual("وصف مقدم الطلب (سري)", "Applicant description (confidential)") + '</div><p class="note-block">' + escapeHtml(o.description) + "</p>" : "") +
        (o.reason_for_listing ? '<div class="sec-title">' + dual("سبب العرض", "Reason for listing") + '</div><p>' + escapeHtml(o.reason_for_listing) + "</p>" : "") +
        (o.desired_outcome ? '<div class="sec-title">' + dual("النتيجة المرجوة", "Desired outcome") + '</div><p>' + escapeHtml(o.desired_outcome) + "</p>" : "");

      if (canReview) {
        body +=
          '<div class="sec-title">' + dual("مراجعة العرض", "Review listing") + "</div>" +
          '<div class="av-field"><label>' + dual("القرار", "Decision") + '</label><select class="av-select av-input" id="oppStatus" style="width:100%">' +
          ["submitted", "under_review", "published", "rejected"].map(function (s) {
            var l = OPPORTUNITY_STATUS[s];
            return '<option value="' + s + '"' + (s === o.status ? " selected" : "") + ">" + dual(l.ar, l.en) + "</option>";
          }).join("") + "</select></div>" +
          '<div class="av-field"><label>' + dual("العنوان العام (عربي)", "Public title (AR)") + '</label><input class="av-input" id="oppTitleAr" style="width:100%" value="' + escAttr(o.public_title_ar || "") + '"></div>' +
          '<div class="av-field"><label>' + dual("العنوان العام (إنجليزي)", "Public title (EN)") + '</label><input class="av-input" id="oppTitleEn" style="width:100%" value="' + escAttr(o.public_title_en || "") + '"></div>' +
          '<div class="av-field"><label>' + dual("الملخص العام (عربي)", "Public summary (AR)") + '</label><textarea class="av-textarea" id="oppSumAr">' + escapeHtml(o.public_summary_ar || "") + "</textarea></div>" +
          '<div class="av-field"><label>' + dual("الملخص العام (إنجليزي)", "Public summary (EN)") + '</label><textarea class="av-textarea" id="oppSumEn">' + escapeHtml(o.public_summary_en || "") + "</textarea></div>" +
          '<p class="note-block">' + dual("لا يُنشر أي شيء حتى تكتب نسخة عامة صريحة — الوصف السري لا يُنشر تلقائيًا.", "Nothing is published until you write explicit public copy — the confidential description is never auto-published.") + "</p>" +
          '<label style="display:flex;gap:8px;align-items:center;font-size:11px;margin-top:6px"><input type="checkbox" id="oppPublish"' + (canPublish ? "" : " disabled") + "> " +
          dual("نشر على الموقع العام", "Publish to the public website") + (canPublish ? "" : " (" + dual("صلاحية غير متوفرة", "permission required") + ")") + "</label>";
      }

      openModal({
        title: dual("عرض مقدم للمراجعة", "Submitted listing"),
        wide: true,
        body: body,
        footer: canReview
          ? '<button class="btn-outline" id="oppCancel">' + dual("إلغاء", "Cancel") + "</button>" +
            '<button class="btn-solid" id="oppSave">' + dual("حفظ المراجعة", "Save review") + "</button>"
          : '<button class="btn-outline" id="oppCancel">' + dual("إغلاق", "Close") + "</button>",
        onMount: function () {
          byId("oppCancel").addEventListener("click", closeModal);
          if (!canReview) return;
          byId("oppSave").addEventListener("click", function () {
            var btn = this;
            var payload = {
              status: byId("oppStatus").value,
              public_title_ar: valOf("oppTitleAr") || null,
              public_title_en: valOf("oppTitleEn") || null,
              public_summary_ar: valOf("oppSumAr") || null,
              public_summary_en: valOf("oppSumEn") || null,
              publish: byId("oppPublish").checked,
            };
            if (payload.publish && !(payload.public_title_ar || payload.public_title_en)) {
              toast(dual("العنوان العام مطلوب للنشر.", "A public title is required to publish."), "err");
              return;
            }
            busy(btn, true);
            post("/api/v1/leads/opportunities/" + o.id + "/review", payload)
              .then(function () {
                toast(dual("تم حفظ المراجعة.", "Review saved."), "ok");
                closeModal();
                renderOpportunities();
              })
              .catch(function (err) { domainError(err); busy(btn, false); });
          });
        },
      });
    });
  }

  function renderLeads() {
    var host = byId("leadContent");
    if (!host) return Promise.resolve();
    if (!STATE.leadBound) {
      STATE.leadBound = true;
      document.querySelectorAll("[data-lead-view]").forEach(function (btn) {
        btn.addEventListener("click", function () {
          var t = btn.getAttribute("data-lead-view");
          if (!leadSubTabAllowed(t)) return;
          STATE.leadView = t;
          document.querySelectorAll("[data-lead-view]").forEach(function (b) { b.classList.toggle("on", b === btn); });
          renderLeads();
        });
      });
      document.querySelectorAll("[data-lead-status]").forEach(function (btn) {
        btn.addEventListener("click", function () {
          document.querySelectorAll("[data-lead-status]").forEach(function (b) {
            b.classList.remove("on");
          });
          btn.classList.add("on");
          STATE.leadStatus = btn.getAttribute("data-lead-status") || "";
          loadLeadList();
        });
      });
    }
    STATE.leadStatus = STATE.leadStatus || "";
    if (!STATE.leadView || !leadSubTabAllowed(STATE.leadView)) {
      STATE.leadView = leadSubTabAllowed("leads") ? "leads" : "opportunities";
    }
    document.querySelectorAll("[data-lead-view]").forEach(function (b) {
      b.classList.toggle("on", b.getAttribute("data-lead-view") === STATE.leadView);
    });
    var leadFilters = byId("leadFilters");
    if (leadFilters) leadFilters.classList.toggle("view-hidden", STATE.leadView !== "leads");
    var leadStats = byId("leadStats");
    if (leadStats) leadStats.classList.toggle("view-hidden", STATE.leadView !== "leads");
    var oppView = byId("oppView");
    if (oppView) oppView.classList.toggle("view-hidden", STATE.leadView !== "opportunities");
    host.classList.toggle("view-hidden", STATE.leadView !== "leads");
    if (STATE.leadView === "opportunities") return renderOpportunities();
    host.innerHTML = loadingHtml();
    return Promise.all([loadLeadStats(), loadLeadList()]);
  }

  function leadSubTabAllowed(t) {
    if (t === "leads") return has("website_lead.read");
    if (t === "opportunities") return has("website_opportunity.review");
    return false;
  }

  function loadLeadStats() {
    var host = byId("leadStats");
    if (!host) return Promise.resolve();
    if (!has("website_lead.read")) {
      host.innerHTML = "";
      return Promise.resolve();
    }
    return get("/api/v1/leads/stats")
      .then(function (stats) {
        STATE.leadStats = stats;
        var byStatus = stats.by_status || {};
        var byMarket = stats.by_market || {};
        host.innerHTML =
          '<div class="av-panel"><h3>' + dual("نظرة عامة", "Overview") + "</h3>" +
          '<div class="av-grid cols-3">' +
          '<div class="kv">' +
          kv(dual("إجمالي الطلبات", "Total leads"), plainNum(stats.total)) +
          kv(dual("طلبات جديدة", "New"), plainNum(byStatus.new || 0)) +
          kv(dual("قيد المعالجة", "In progress"), plainNum(byStatus.in_progress || 0)) +
          kv(dual("مغلقة", "Closed"), plainNum((byStatus.closed || 0) + (byStatus.converted || 0))) +
          "</div>" +
          '<div class="kv">' +
          kv(dual("البحرين", "Bahrain"), plainNum(byMarket.bahrain || 0)) +
          kv(dual("السعودية", "Saudi Arabia"), plainNum(byMarket.saudi || 0)) +
          kv(dual("عروض مقدَّمة", "Listings submitted"), plainNum(stats.opportunities_submitted || 0)) +
          kv(dual("عروض منشورة", "Listings published"), plainNum(stats.opportunities_published || 0)) +
          "</div>" +
          '<div class="kv">' +
          Object.keys(stats.by_service || {})
            .map(function (key) {
              var label = leadLabel(LEAD_SERVICE, key);
              return kv(dual(escapeHtml(label.ar), escapeHtml(label.en)), plainNum(stats.by_service[key]));
            })
            .join("") +
          "</div>" +
          "</div></div>";
      })
      .catch(function () {
        host.innerHTML = "";
      });
  }

  function loadLeadList() {
    var host = byId("leadContent");
    if (!host) return Promise.resolve();
    var query = "/api/v1/leads?limit=50";
    if (STATE.leadStatus) query += "&status=" + encodeURIComponent(STATE.leadStatus);
    return get(query)
      .then(function (res) {
        var items = (res && res.items) || [];
        if (!items.length) {
          host.innerHTML =
            '<div class="av-panel">' +
            emptyHtml("لا توجد طلبات مطابقة.", "No matching leads.") +
            "</div>";
          return;
        }
        host.innerHTML =
          '<div class="av-panel"><div class="av-list">' +
          items.map(leadRow).join("") +
          "</div></div>";
        host.querySelectorAll("[data-lead]").forEach(function (row) {
          row.addEventListener("click", function () {
            openLead(parseInt(row.getAttribute("data-lead"), 10));
          });
        });
      })
      .catch(function (err) {
        host.innerHTML = errorHtml(
          STATE.lang === "ar" ? "تعذّر تحميل الطلبات." : "Could not load leads.",
        );
        handleLoadError(err);
      });
  }

  function leadRow(lead) {
    var service = leadLabel(LEAD_SERVICE, lead.service_type);
    var market = leadLabel(LEAD_MARKET, lead.market);
    var status = leadLabel(LEAD_STATUS, lead.status);
    var priority = leadLabel(LEAD_PRIORITY, lead.priority);
    return (
      '<div class="av-row" data-lead="' + lead.id + '" style="flex-direction:column;align-items:stretch;gap:8px">' +
      '<div style="display:flex;align-items:center;gap:11px">' +
      '<div class="grow"><div class="t">' +
      escapeHtml(lead.full_name) +
      (lead.company_name ? " · " + escapeHtml(lead.company_name) : "") +
      "</div>" +
      '<div class="s">' +
      dual(escapeHtml(service.ar), escapeHtml(service.en)) +
      " · " +
      dual(escapeHtml(market.ar), escapeHtml(market.en)) +
      " · " +
      escapeHtml(lead.reference) +
      "</div></div>" +
      '<span class="status ' + (status.cls || "") + '"><i></i>' +
      dual(escapeHtml(status.ar), escapeHtml(status.en)) +
      "</span>" +
      "</div>" +
      '<div style="display:flex;align-items:center;gap:12px;font-size:11px;color:var(--ink-400)">' +
      "<span>" + dual("الأولوية", "Priority") + ": " + dual(escapeHtml(priority.ar), escapeHtml(priority.en)) + "</span>" +
      "<span>" + dual("التوجيه", "Routed to") + ": " + escapeHtml(lead.routed_team || "—") + "</span>" +
      "<span>" + fmtDateTime(lead.created_at) + "</span>" +
      "</div></div>"
    );
  }

  function openLead(id) {
    return get("/api/v1/leads/" + id).then(function (lead) {
      var payload = lead.payload || {};
      var detailRows = Object.keys(payload)
        .filter(function (k) { return payload[k] !== null && payload[k] !== ""; })
        .map(function (k) {
          return kv(escapeHtml(k), escapeHtml(String(payload[k])));
        })
        .join("");
      var attribution = lead.attribution || {};
      var attrRows = Object.keys(attribution)
        .filter(function (k) { return attribution[k]; })
        .map(function (k) {
          return kv(escapeHtml(k), escapeHtml(String(attribution[k])));
        })
        .join("");
      var service = leadLabel(LEAD_SERVICE, lead.service_type);
      var market = leadLabel(LEAD_MARKET, lead.market);
      var status = leadLabel(LEAD_STATUS, lead.status);
      var priority = leadLabel(LEAD_PRIORITY, lead.priority);

      var contact =
        '<div class="kv">' +
        kv(dual("الاسم", "Name"), escapeHtml(lead.full_name)) +
        kv(dual("البريد", "Email"), escapeHtml(lead.email)) +
        (lead.phone ? kv(dual("الهاتف", "Phone"), escapeHtml(lead.phone)) : "") +
        (lead.nationality ? kv(dual("الجنسية", "Nationality"), escapeHtml(lead.nationality)) : "") +
        kv(dual("السوق", "Market"), dual(escapeHtml(market.ar), escapeHtml(market.en))) +
        kv(dual("الخدمة", "Service"), dual(escapeHtml(service.ar), escapeHtml(service.en))) +
        kv(dual("الحالة", "Status"), dual(escapeHtml(status.ar), escapeHtml(status.en))) +
        kv(dual("الأولوية", "Priority"), dual(escapeHtml(priority.ar), escapeHtml(priority.en))) +
        kv(dual("التوجيه", "Routed to"), escapeHtml(lead.routed_team || "—")) +
        kv(dual("التاريخ", "Created"), fmtDateTime(lead.created_at)) +
        "</div>";

      // S13: the independent manager note. Marketing reads it; only a holder of
      // website_lead.manager_note (company manager / owner) gets the composer.
      var notes = lead.manager_notes || [];
      var notesBlock =
        '<h3 style="margin-top:16px">' + dual("ملاحظات المدير", "Manager notes") + "</h3>" +
        (notes.length
          ? '<div class="kv">' + notes.map(function (n) {
              return '<div style="padding:8px 0;border-bottom:1px solid var(--line-2)">' +
                '<div>' + escapeHtml(n.body) + "</div>" +
                '<div style="font-size:11px;color:var(--ink-400);margin-top:3px">' +
                escapeHtml((STATE.lang === "ar" ? n.author_name_ar : n.author_name_en) || n.author_name_ar || "") +
                " · " + fmtDateTime(n.created_at) + "</div></div>";
            }).join("") + "</div>"
          : '<p class="av-empty">' + dual("لا توجد ملاحظات.", "No notes.") + "</p>") +
        (has("website_lead.manager_note")
          ? '<div style="margin-top:10px"><textarea class="av-textarea" id="leadNoteBody" rows="3" placeholder="' +
            escAttr(STATE.lang === "ar" ? "اكتب ملاحظة المتابعة" : "Write a follow-up note") + '"></textarea>' +
            '<div class="av-form-actions"><button class="btn-solid" id="leadNoteAdd">' +
            dual("إضافة ملاحظة", "Add note") + "</button></div></div>"
          : "");

      var body =
        contact +
        (detailRows
          ? '<h3 style="margin-top:16px">' + dual("تفاصيل الطلب", "Request details") + '</h3><div class="kv">' + detailRows + "</div>"
          : "") +
        (attrRows
          ? '<h3 style="margin-top:16px">' + dual("مصدر الحملة", "Attribution") + '</h3><div class="kv">' + attrRows + "</div>"
          : "") +
        (lead.message
          ? '<h3 style="margin-top:16px">' + dual("رسالة", "Message") + "</h3><p>" + escapeHtml(lead.message) + "</p>"
          : "") +
        notesBlock +
        (has("website_lead.manage")
          ? '<h3 style="margin-top:16px">' + dual("تحديث الطلب", "Update lead") + "</h3>" +
            '<div class="modal-foot" style="border-radius:12px;border:1px solid var(--line-2)">' +
            '<select id="leadStatusSel">' +
            Object.keys(LEAD_STATUS)
              .map(function (key) {
                var l = LEAD_STATUS[key];
                return '<option value="' + key + '"' + (key === lead.status ? " selected" : "") + ">" + l.ar + " / " + l.en + "</option>";
              })
              .join("") +
            "</select>" +
            '<select id="leadPriSel">' +
            Object.keys(LEAD_PRIORITY)
              .map(function (key) {
                var l = LEAD_PRIORITY[key];
                return '<option value="' + key + '"' + (key === lead.priority ? " selected" : "") + ">" + l.ar + " / " + l.en + "</option>";
              })
              .join("") +
            "</select>" +
            '<button class="btn-solid" id="leadSave">' + dual("حفظ", "Save") + "</button>" +
            "</div>"
          : "");

      openModal({
        title: escapeHtml(lead.full_name) + " · " + escapeHtml(lead.reference),
        body: body,
      });

      var noteBtn = byId("leadNoteAdd");
      if (noteBtn) {
        noteBtn.addEventListener("click", function () {
          var bodyEl = byId("leadNoteBody");
          var text = bodyEl ? bodyEl.value.trim() : "";
          if (!text) {
            toast(STATE.lang === "ar" ? "اكتب الملاحظة أولًا." : "Write the note first.", "err");
            return;
          }
          busy(noteBtn, true);
          post("/api/v1/leads/" + id + "/notes", { body: text })
            .then(function () {
              toast(STATE.lang === "ar" ? "تمت إضافة الملاحظة." : "Note added.", "ok");
              return openLead(id);
            })
            .catch(function (err) {
              busy(noteBtn, false);
              toast(err && err.message ? err.message : STATE.lang === "ar" ? "تعذّرت الإضافة." : "Could not add the note.", "err");
            });
        });
      }

      var saveBtn = byId("leadSave");
      if (saveBtn) {
        saveBtn.addEventListener("click", function () {
          var statusSel = byId("leadStatusSel");
          var priSel = byId("leadPriSel");
          var payloadOut = {};
          if (statusSel) payloadOut.status = statusSel.value;
          if (priSel) payloadOut.priority = priSel.value;
          patch("/api/v1/leads/" + id, payloadOut)
            .then(function () {
              toast(STATE.lang === "ar" ? "تم تحديث الطلب." : "Lead updated.", "ok");
              closeModal();
              loadLeadList();
              loadLeadStats();
            })
            .catch(function () {
              toast(STATE.lang === "ar" ? "تعذّر التحديث." : "Update failed.", "err");
            });
        });
      }
    });
  }

  function refreshNotifications() {
    if (!has("notification.read_own")) return Promise.resolve();
    return Promise.all([
      get("/api/v1/notifications?limit=50"),
      get("/api/v1/notifications/summary"),
    ])
      .then(function (res) {
        STATE.notifications = (res[0] && res[0].items) || [];
        STATE.notificationsUnread = (res[1] && res[1].unread) || 0;
        paintNotifBadge();
        return STATE.notifications;
      })
      .catch(function () { return []; });
  }

  function paintNotifBadge() {
    var dot = byId("notifDot");
    if (!dot) return;
    var n = STATE.notificationsUnread || 0;
    if (n > 0) {
      dot.textContent = n > 9 ? "9+" : String(n);
      dot.classList.add("count");
    } else {
      dot.textContent = "";
      dot.classList.remove("count");
    }
  }

  // ---- group administration view ---------------------------------------
  //
  // One delegated click handler drives every admin action, so cards can be
  // re-rendered freely without rebinding. Each tab is loaded lazily and only
  // if the caller holds the permission that tab needs.

  // ======================================================================
  // Holding-business domain views (S04, S11-S23, S26-S28)
  //
  // Every view is a thin projection of the existing permission-gated API. No
  // authorization decision is taken here: `has()` only decides what to *offer*
  // on screen, and the backend re-checks every call server-side. Actions that
  // are policy-dependent remain disabled with an explicit reason rather than
  // being silently omitted.
  // ======================================================================

  function panel(titleAr, titleEn, body) {
    return '<div class="av-panel"><h3>' + dual(titleAr, titleEn) + "</h3>" + body + "</div>";
  }

  function noticeHtml(ar, en) {
    return '<p class="av-empty">' + dual(ar, en) + "</p>";
  }

  function dec(v) {
    if (v === null || v === undefined || v === "") return "—";
    var n = Number(v);
    return isNaN(n) ? String(v) : NUM.format(n);
  }

  function dateStr(iso) {
    if (!iso) return "—";
    return String(iso).slice(0, 10);
  }

  function rowClickAttr(name, obj) {
    return " data-" + name + "='" + escAttr(JSON.stringify(obj)) + "'";
  }

  function bindRowClicks(host, name, handler) {
    host.querySelectorAll("[data-" + name + "]").forEach(function (row) {
      row.addEventListener("click", function (e) {
        if (e.target.closest && e.target.closest("[data-stop]")) return;
        handler(JSON.parse(row.getAttribute("data-" + name)));
      });
    });
  }

  function actBtn(perm, action, id, labelAr, labelEn, kind) {
    if (perm && !has(perm)) return "";
    return (
      '<button class="btn-outline ' + (kind || "") + '" data-stop="1" data-act="' + action +
      '" data-id="' + id + '">' + dual(labelAr, labelEn) + "</button>"
    );
  }

  function companyNameById(id) {
    var c = companyById(id);
    return c ? companyName(c) : String(id);
  }

  function companySelectOptions(extraAll) {
    // Option labels are plain text: selectInput escapes them, and a <select>
    // cannot hold markup, so the label must already be in the active language.
    var opts = extraAll
      ? [{ value: "", label: STATE.lang === "ar" ? "كل الشركات" : "All companies" }]
      : [];
    (STATE.companies || []).forEach(function (c) {
      opts.push({ value: c.id, label: companyName(c) });
    });
    return opts;
  }

  function opt(ar, en) {
    // Plain-text option label in the active language (a <select> cannot hold
    // markup, and selectInput escapes it).
    return STATE.lang === "ar" ? ar : en;
  }

  function numInput(id, value, placeholder) {
    return (
      '<input class="av-input" id="' + id + '" type="number" step="any" value="' +
      escAttr(value === null || value === undefined ? "" : value) + '" placeholder="' +
      escAttr(placeholder || "") + '">'
    );
  }

  function dateInput(id, value) {
    return '<input class="av-input" id="' + id + '" type="date" value="' + escAttr(value || "") + '">';
  }

  function textArea(id, value, placeholder) {
    return (
      '<textarea class="av-input" id="' + id + '" rows="2" placeholder="' +
      escAttr(placeholder || "") + '">' + escapeHtml(value || "") + "</textarea>"
    );
  }

  function valOf(id) {
    var el = byId(id);
    return el ? String(el.value).trim() : "";
  }

  function numVal(id) {
    var v = valOf(id);
    if (v === "") return null;
    var n = Number(v);
    return isNaN(n) ? null : n;
  }

  function bindHost(host, onAct) {
    if (!host || host.getAttribute("data-domain-bound")) return;
    host.setAttribute("data-domain-bound", "1");
    host.addEventListener("click", function (e) {
      var el = e.target.closest ? e.target.closest("[data-act]") : null;
      if (!el) return;
      onAct(el.getAttribute("data-act"), el.getAttribute("data-id"), el);
    });
    host.addEventListener("submit", function (e) {
      e.preventDefault();
      if (e.target && e.target.getAttribute) onAct("submit", e.target.id, e.target);
    });
  }

  function domainError(err) {
    toast(errText(err), "err");
  }

  // ======================================================================
  // S11/S12/S19 -- Employees, assessments, advisory sessions
  // ======================================================================
  function renderEmployeesView() {
    var host = byId("empContent");
    if (!host) return Promise.resolve();
    if (!STATE.empBound) {
      STATE.empBound = true;
      bindEmployeesTabs();
      bindHost(host, onEmployeeAct);
    }
    if (!STATE.empTab || !canEmpTab(STATE.empTab)) STATE.empTab = firstEmpTab();
    return renderEmployeesTab(STATE.empTab);
  }

  var EMP_TABS = ["employees", "assessments", "advisors"];
  var EMP_TAB_PERM = {
    employees: ["employee.read"],
    assessments: ["assessment.read"],
    advisors: ["advisor.read", "advisor.session.read_own"],
  };
  function canEmpTab(t) { return (EMP_TAB_PERM[t] || []).some(has); }
  function firstEmpTab() {
    for (var i = 0; i < EMP_TABS.length; i++) if (canEmpTab(EMP_TABS[i])) return EMP_TABS[i];
    return "employees";
  }
  function bindEmployeesTabs() {
    document.querySelectorAll("[data-emp-tab]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var t = btn.getAttribute("data-emp-tab");
        if (!canEmpTab(t)) return;
        STATE.empTab = t;
        document.querySelectorAll("[data-emp-tab]").forEach(function (b) {
          b.classList.toggle("on", b === btn);
        });
        renderEmployeesTab(t);
      });
    });
  }
  function renderEmployeesTab(tab) {
    var host = byId("empContent");
    document.querySelectorAll("[data-emp-tab]").forEach(function (b) {
      b.classList.toggle("on", b.getAttribute("data-emp-tab") === tab);
    });
    host.innerHTML = loadingHtml();
    if (tab === "employees") return renderEmployees();
    if (tab === "assessments") return renderAssessments();
    if (tab === "advisors") return renderAdvisors();
    return Promise.resolve();
  }

  function renderEmployees() {
    var host = byId("empContent");
    var q = STATE.empCompany ? "?company_id=" + STATE.empCompany : "";
    return Promise.all([ensureCompanies(), get("/api/v1/employees" + q)]).then(function (res) {
      var employees = res[1] || [];
      var canManage = has("employee.manage");
      var create = canManage
        ? '<form class="av-form av-form-inline" id="empForm">' +
          field("الشركة", "Company", selectInput("eCompany", companySelectOptions(false), STATE.companies.length ? STATE.companies[0].id : "")) +
          field("الاسم (عربي)", "Name (AR)", textInput("eNameAr", "")) +
          field("الاسم (إنجليزي)", "Name (EN)", textInput("eNameEn", "")) +
          field("المسمى الوظيفي", "Job title", textInput("eTitle", "")) +
          field("تاريخ التعيين", "Hire date", dateInput("eHire", "")) +
          '<div class="av-form-actions"><button class="btn-solid" type="submit">' +
          dual("إضافة موظف", "Add employee") + "</button></div></form>"
        : "";
      var filter =
        '<div class="av-form av-form-inline">' +
        field("تصفية بالشركة", "Filter by company", selectInput("empFilter", companySelectOptions(true), STATE.empCompany || "")) +
        "</div>";
      var list = employees.length
        ? '<div class="av-list">' + employees.map(employeeRow).join("") + "</div>"
        : noticeHtml("لا يوجد موظفون في نطاقك.", "No employees in your scope.");
      host.innerHTML = panel("الموظفون", "Employees", create + filter + list);
      var f = byId("empFilter");
      if (f) f.addEventListener("change", function () { STATE.empCompany = this.value ? parseInt(this.value, 10) : null; renderEmployees(); });
      bindRowClicks(host, "emp", openEmployee);
    }).catch(function (err) { handleLoadError(err); host.innerHTML = errorHtml(errText(err)); });
  }

  function employeeRow(e) {
    var name = STATE.lang === "ar" ? e.full_name_ar : e.full_name_en || e.full_name_ar;
    var salary = has("employee.salary.read") && e.base_salary != null
      ? ' · ' + dual("الراتب", "Salary") + " " + dec(e.base_salary)
      : "";
    return (
      '<div class="av-row"' + rowClickAttr("emp", e) + ">" +
      '<div class="grow"><div class="t">' + escapeHtml(name) + "</div>" +
      '<div class="s">' + escapeHtml(companyNameById(e.company_id)) + " · " +
      escapeHtml(e.job_title || "") + salary + "</div></div>" +
      statusBadgeFromMap(e.status, {
        active: ["نشط", "Active", "ok"],
        on_leave: ["في إجازة", "On leave", "warn"],
        terminated: ["منتهٍ", "Terminated", "miss"],
      }) + "</div>"
    );
  }

  function openEmployee(e) {
    openModal({
      title: dual("ملف الموظف", "Employee file"),
      wide: true,
      body: loadingHtml(),
      onMount: function (root, body) {
        get("/api/v1/employees/" + e.id + "/movements").catch(function () { return []; }).then(function (movements) {
          body.innerHTML = employeeDetail(e, movements || []);
          bindEmployeeDetail(body, e);
        });
      },
    });
  }

  function employeeDetail(e, movements) {
    var name = STATE.lang === "ar" ? e.full_name_ar : e.full_name_en || e.full_name_ar;
    var info = '<div class="kv">' +
      kv(dual("الشركة", "Company"), escapeHtml(companyNameById(e.company_id))) +
      kv(dual("الاسم", "Name"), escapeHtml(name)) +
      kv(dual("المسمى", "Job title"), escapeHtml(e.job_title || "—")) +
      kv(dual("البريد", "Email"), escapeHtml(e.email || "—")) +
      kv(dual("الهاتف", "Phone"), escapeHtml(e.phone || "—")) +
      kv(dual("تاريخ التعيين", "Hire date"), escapeHtml(dateStr(e.hire_date))) +
      kv(dual("رصيد الإجازات", "Leave balance"), dec(e.leave_balance_days)) +
      kv(dual("رصيد السلف", "Advance balance"), dec(e.advance_balance));
    if (has("employee.salary.read")) {
      info += kv(dual("الراتب الأساسي", "Base salary"), dec(e.base_salary)) +
        kv(dual("بدل السكن", "Housing"), dec(e.housing_allowance)) +
        kv(dual("بدل النقل", "Transport"), dec(e.transport_allowance));
    } else {
      info += kv(dual("الراتب", "Salary"), dual("محجوب", "Restricted"));
    }
    info += "</div>";
    var movForm = has("employee.movement.manage")
      ? '<form class="av-form av-form-inline" id="movForm">' +
        field("النوع", "Type", selectInput("mvType", [
          { value: "leave", label: opt("إجازة", "Leave") },
          { value: "advance", label: opt("سلفة", "Advance") },
          { value: "adjustment", label: opt("تسوية", "Adjustment") },
        ], "leave")) +
        field("التاريخ", "Date", dateInput("mvDate", "")) +
        field("الأيام", "Days", numInput("mvDays", "")) +
        field("المبلغ", "Amount", numInput("mvAmount", "")) +
        field("السبب", "Reason", textInput("mvReason", "")) +
        '<div class="av-form-actions"><button class="btn-outline" type="submit">' +
        dual("تسجيل حركة", "Record movement") + "</button></div></form>"
      : "";
    var movList = movements.length
      ? '<div class="av-list">' + movements.map(function (m) {
          var decide = m.status === "pending"
            ? actBtn("employee.movement.approve", "mov-approve", m.id, "اعتماد", "Approve") +
              actBtn("employee.movement.approve", "mov-reject", m.id, "رفض", "Reject")
            : "";
          return '<div class="av-row" style="cursor:default"><div class="grow"><div class="t">' +
            escapeHtml(m.movement_type) + (m.days ? " · " + dec(m.days) + dual(" يوم", " d") : "") +
            (m.amount ? " · " + dec(m.amount) : "") + "</div>" +
            '<div class="s">' + escapeHtml(dateStr(m.effective_date)) + " · " + escapeHtml(m.reason || "") + "</div></div>" +
            statusBadgeFromMap(m.status, { pending: ["قيد الاعتماد", "Pending", "warn"], approved: ["معتمد", "Approved", "ok"], rejected: ["مرفوض", "Rejected", "miss"] }) +
            decide + "</div>";
        }).join("") + "</div>"
      : noticeHtml("لا توجد حركات مسجّلة.", "No movements recorded.");
    return panel("بيانات الموظف", "Employee details", info) +
      panel("الحركات (يدوية — دون ربط آلي بالرواتب)", "Movements (manual — no automatic payroll link)", movForm + movList);
  }

  function bindEmployeeDetail(body, e) {
    var form = body.querySelector("#movForm");
    if (form) {
      form.addEventListener("submit", function (ev) {
        ev.preventDefault();
        post("/api/v1/employees/" + e.id + "/movements", {
          movement_type: valOf("mvType"),
          effective_date: valOf("mvDate") || null,
          days: numVal("mvDays"),
          amount: numVal("mvAmount"),
          reason: valOf("mvReason") || null,
        }).then(function () {
          toast(dual("تم تسجيل الحركة.", "Movement recorded."), "ok");
          openEmployee(e);
        }).catch(domainError);
      });
    }
    body.querySelectorAll("[data-act]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var approve = btn.getAttribute("data-act") === "mov-approve";
        post("/api/v1/employees/movements/" + btn.getAttribute("data-id") + "/decision", { approve: approve })
          .then(function () {
            toast(dual("تم تحديث الحركة.", "Movement updated."), "ok");
            openEmployee(e);
          }).catch(domainError);
      });
    });
  }

  function renderAssessments() {
    var host = byId("empContent");
    var canManage = has("assessment.manage");
    var owner = isConfidentialOwner();
    // The owner reviews both employee and confidential leadership assessments;
    // everyone else only sees employee ones (S12/S23, D04).
    if (STATE.assessType !== "leadership") STATE.assessType = "employee";
    if (STATE.assessType === "leadership" && !owner) STATE.assessType = "employee";
    var filter = owner
      ? '<div class="chip-row">' +
        assessTypeChip("employee", "تقييمات الموظفين", "Employee assessments") +
        assessTypeChip("leadership", "تقييمات القيادة (سرّية)", "Leadership assessments (confidential)") +
        "</div>"
      : "";
    return Promise.all([
      ensureCompanies(),
      get("/api/v1/employees/assessments/list?assessment_type=" + STATE.assessType).catch(function () { return []; }),
    ]).then(function (res) {
      var rows = res[1] || [];
      var typeOptions = [{ value: "employee", label: opt("موظف", "Employee") }];
      if (owner) typeOptions.push({ value: "leadership", label: opt("قيادة (سري)", "Leadership (confidential)") });
      var create = canManage
        ? '<form class="av-form av-form-inline" id="assessForm">' +
          field("الشركة", "Company", selectInput("asCompany", companySelectOptions(false), STATE.companies.length ? STATE.companies[0].id : "")) +
          field("الفترة", "Period", textInput("asPeriod", "")) +
          field("النوع", "Type", selectInput("asType", typeOptions, "employee")) +
          field("الموظف (المعرّف)", "Employee id", numInput("asEmp", "")) +
          field("الملخص", "Summary", textInput("asSummary", "")) +
          '<div class="av-form-actions"><button class="btn-solid" type="submit">' +
          dual("إنشاء تقييم", "Create assessment") + "</button></div></form>"
        : "";
      var list = rows.length
        ? '<div class="av-list">' + rows.map(assessmentRow).join("") + "</div>"
        : noticeHtml("لا توجد تقييمات.", "No assessments.");
      var title = STATE.assessType === "leadership" ? "تقييمات القيادة (D04: سرّية)" : "التقييمات";
      var titleEn = STATE.assessType === "leadership" ? "Leadership assessments (D04: confidential)" : "Assessments";
      host.innerHTML = panel(title, titleEn, filter + create + list);
      bindRowClicks(host, "assess", openAssessment);
      document.querySelectorAll("[data-assess-type]").forEach(function (b) {
        b.addEventListener("click", function () {
          STATE.assessType = b.getAttribute("data-assess-type");
          renderAssessments();
        });
      });
    }).catch(function (err) { handleLoadError(err); host.innerHTML = errorHtml(errText(err)); });
  }

  function assessTypeChip(value, ar, en) {
    return '<button type="button" class="chip' + (STATE.assessType === value ? " on" : "") +
      '" data-assess-type="' + escAttr(value) + '">' + dual(ar, en) + "</button>";
  }


  function assessmentRow(a) {
    var gap = a.has_evidence_gap
      ? '<span class="status miss"><i></i>' + dual("فجوة أدلة", "Evidence gap") + "</span>"
      : "";
    return (
      '<div class="av-row"' + rowClickAttr("assess", a) + ">" +
      '<div class="grow"><div class="t">' + escapeHtml(a.period_label) +
      " · " + escapeHtml(a.assessment_type) + "</div>" +
      '<div class="s">' + escapeHtml(companyNameById(a.company_id)) +
      " · " + dual("الدرجة", "Score") + " " + dec(a.overall_score) + "</div></div>" +
      gap + statusBadgeFromMap(a.status, {
        draft: ["مسودة", "Draft", "warn"],
        submitted: ["مُقدَّم", "Submitted", "warn"],
        approved: ["معتمد", "Approved", "ok"],
      }) + "</div>"
    );
  }

  function openAssessment(a) {
    openModal({
      title: dual("التقييم", "Assessment"),
      wide: true,
      body: loadingHtml(),
      onMount: function (root, body) {
        body.innerHTML = assessmentDetail(a);
        bindAssessmentDetail(body, a);
      },
    });
  }

  function assessmentDetail(a) {
    var items = a.items || [];
    var itemForm = has("assessment.manage") && a.status !== "approved"
      ? '<form class="av-form av-form-inline" id="assessItemForm">' +
        field("معيار (كود)", "Criterion code", textInput("aiCode", "")) +
        field("الاسم (عربي)", "Name (AR)", textInput("aiNameAr", "")) +
        field("الاسم (إنجليزي)", "Name (EN)", textInput("aiNameEn", "")) +
        field("الوزن", "Weight", numInput("aiWeight", "1")) +
        field("الدرجة (1-5)", "Score (1-5)", numInput("aiScore", "")) +
        field("دليل إلزامي؟", "Evidence required?", selectInput("aiEvReq", [{ value: "0", label: opt("لا", "No") }, { value: "1", label: opt("نعم", "Yes") }], "0")) +
        field("الدليل مكتمل؟", "Evidence complete?", selectInput("aiEvDone", [{ value: "0", label: opt("لا", "No") }, { value: "1", label: opt("نعم", "Yes") }], "0")) +
        '<div class="av-form-actions"><button class="btn-outline" type="submit">' +
        dual("حفظ معيار", "Save criterion") + "</button></div></form>"
      : "";
    var list = items.length
      ? '<div class="av-list">' + items.map(function (it) {
          return '<div class="av-row" style="cursor:default"><div class="grow"><div class="t">' +
            escapeHtml(STATE.lang === "ar" ? it.criterion_name_ar : it.criterion_name_en || it.criterion_name_ar) + "</div>" +
            '<div class="s">' + dual("الوزن", "Weight") + " " + dec(it.weight) + " · " +
            dual("الدرجة", "Score") + " " + dec(it.score) +
            (it.evidence_required ? " · " + dual("دليل إلزامي", "Mandatory evidence") : "") + "</div></div>" +
            (it.evidence_required && !it.evidence_complete
              ? '<span class="status miss"><i></i>' + dual("ناقص", "Missing") + "</span>"
              : "") + "</div>";
        }).join("") + "</div>"
      : noticeHtml("لا توجد معايير بعد.", "No criteria yet.");
    var approve = a.status !== "approved" && has("assessment.approve")
      ? '<div class="av-form-actions">' + actBtn("assessment.approve", "assess-approve", a.id, "اعتماد التقييم", "Approve assessment") + "</div>"
      : "";
    var gapNote = a.has_evidence_gap
      ? '<p class="note-block">' + dual("الاعتماد محجوب: يوجد معيار إلزامي بدون دليل مكتمل.", "Approval is blocked: a mandatory-evidence item is incomplete.") + "</p>"
      : "";
    return panel("ملخص", "Summary", '<div class="kv">' +
        kv(dual("الفترة", "Period"), escapeHtml(a.period_label)) +
        kv(dual("الحالة", "Status"), escapeHtml(a.status)) +
        kv(dual("الدرجة المرجّحة", "Weighted score"), dec(a.overall_score)) +
        "</div>" + gapNote + approve) +
      panel("المعايير", "Criteria", itemForm + list);
  }

  function bindAssessmentDetail(body, a) {
    var form = body.querySelector("#assessItemForm");
    if (form) {
      form.addEventListener("submit", function (ev) {
        ev.preventDefault();
        post("/api/v1/employees/assessments/" + a.id + "/items", {
          criterion_code: valOf("aiCode"),
          criterion_name_ar: valOf("aiNameAr"),
          criterion_name_en: valOf("aiNameEn") || null,
          weight: numVal("aiWeight") || 1,
          score: numVal("aiScore"),
          evidence_required: valOf("aiEvReq") === "1",
          evidence_complete: valOf("aiEvDone") === "1",
        }).then(function (updated) {
          toast(dual("تم حفظ المعيار.", "Criterion saved."), "ok");
          openAssessment(updated);
        }).catch(domainError);
      });
    }
    var btn = body.querySelector('[data-act="assess-approve"]');
    if (btn) {
      btn.addEventListener("click", function () {
        post("/api/v1/employees/assessments/" + a.id + "/approve", {})
          .then(function (updated) {
            toast(dual("تم اعتماد التقييم.", "Assessment approved."), "ok");
            openAssessment(updated);
          }).catch(domainError);
      });
    }
  }

  function renderAdvisors() {
    var host = byId("empContent");
    return Promise.all([
      ensureCompanies(),
      get("/api/v1/operations/advisory-sessions").catch(function () { return []; }),
      has("advisor.read")
        ? get("/api/v1/operations/advisors").catch(function () { return []; })
        : Promise.resolve([]),
      (has("advisor.read") || has("advisor.session.read_own"))
        ? get("/api/v1/operations/advisor-reports").catch(function () { return []; })
        : Promise.resolve([]),
    ]).then(function (res) {
      var rows = res[1] || [];
      var assignments = res[2] || [];
      var reports = res[3] || [];
      var canRecord = has("advisor.session.record");
      var create = canRecord
        ? '<form class="av-form av-form-inline" id="advForm">' +
          field("الشركة", "Company", selectInput("adCompany", companySelectOptions(false), STATE.companies.length ? STATE.companies[0].id : "")) +
          field("المستشار (معرّف المستخدم)", "Advisor user id", numInput("adUser", "")) +
          field("الموعد", "Scheduled at", '<input class="av-input" id="adWhen" type="datetime-local">') +
          field("الموضوع", "Topic", textInput("adTopic", "")) +
          field("الملاحظات", "Notes", textInput("adNotes", "")) +
          field("التوصيات", "Recommendations", textInput("adRec", "")) +
          '<div class="av-form-actions"><button class="btn-solid" type="submit">' +
          dual("تسجيل جلسة", "Record session") + "</button></div></form>"
        : "";
      var list = rows.length
        ? '<div class="av-list">' + rows.map(function (s) {
            return '<div class="av-row" style="cursor:default"><div class="grow"><div class="t">' +
              escapeHtml(s.topic || dual("جلسة استشارية", "Advisory session")) + "</div>" +
              '<div class="s">' + escapeHtml(companyNameById(s.company_id)) + " · " +
              escapeHtml(s.scheduled_at ? String(s.scheduled_at).slice(0, 16).replace("T", " ") : "—") + "</div></div>" +
              statusBadgeFromMap(s.status, { scheduled: ["مجدولة", "Scheduled", "warn"], completed: ["مكتملة", "Completed", "ok"], cancelled: ["ملغاة", "Cancelled", "miss"] }) +
              "</div>";
          }).join("") + "</div>"
        : noticeHtml("لا توجد جلسات استشارية.", "No advisory sessions.");
      host.innerHTML =
        panel("الجلسات الاستشارية", "Advisory sessions", create + list) +
        advisorAssignmentsPanel(assignments) +
        advisorReportsPanel(reports);
    }).catch(function (err) { handleLoadError(err); host.innerHTML = errorHtml(errText(err)); });
  }

  function advisorAssignmentsPanel(assignments) {
    if (!has("advisor.read")) return "";
    var canAssign = has("advisor.manage");
    var form = canAssign
      ? '<form class="av-form av-form-inline" id="advAssignForm">' +
        field("الشركة", "Company", selectInput("aaCompany", companySelectOptions(false), STATE.companies.length ? STATE.companies[0].id : "")) +
        field("المستشار (معرّف المستخدم)", "Advisor user id", numInput("aaUser", "")) +
        field("التخصص", "Specialty", textInput("aaSpecialty", "")) +
        '<div class="av-form-actions"><button class="btn-solid" type="submit">' +
        dual("إسناد مستشار", "Assign advisor") + "</button></div></form>"
      : "";
    var list = assignments.length
      ? '<div class="av-list">' + assignments.map(function (a) {
          return '<div class="av-row" style="cursor:default"><div class="grow"><div class="t">' +
            dual("مستشار", "Advisor") + " #" + plainNum(a.advisor_user_id) + "</div>" +
            '<div class="s">' + escapeHtml(companyNameById(a.company_id)) + " · " +
            escapeHtml(a.specialty || dual("بدون تخصص", "No specialty")) + "</div></div>" +
            (a.is_active
              ? '<span class="status ok"><i></i>' + dual("نشط", "Active") + "</span>"
              : '<span class="status miss"><i></i>' + dual("غير نشط", "Inactive") + "</span>") +
            "</div>";
        }).join("") + "</div>"
      : noticeHtml("لا يوجد مستشارون مُسندون.", "No advisors assigned.");
    return panel("المستشارون المُسندون (S19 / D04)", "Assigned advisors (S19 / D04)",
      '<p class="note-block">' + dual("المستشار الخارجي يرى جلساته فقط؛ الإسناد متاح لمن يملك صلاحية إدارة المستشارين.", "An external consultant sees only their own sessions; assignment requires the manage permission.") + "</p>" +
      form + list);
  }

  function advisorReportsPanel(reports) {
    var canWrite = has("advisor.session.record") || has("advisor.session.read_own");
    if (!has("advisor.read") && !has("advisor.session.read_own")) return "";
    var now = new Date();
    var form = canWrite
      ? '<form class="av-form av-form-inline" id="advReportForm">' +
        field("الشركة", "Company", selectInput("arCompany", companySelectOptions(false), STATE.companies.length ? STATE.companies[0].id : "")) +
        field("المستشار (معرّف المستخدم)", "Advisor user id", numInput("arUser", "")) +
        field("السنة", "Year", numInput("arYear", now.getFullYear())) +
        field("الشهر", "Month", numInput("arMonth", now.getMonth() + 1)) +
        field("التطويرات", "Development", textInput("arDev", "")) +
        field("التحديات", "Challenges", textInput("arChal", "")) +
        field("التوصيات", "Recommendations", textInput("arRec", "")) +
        '<div class="av-form-actions">' +
        '<button class="btn-outline" type="button" data-act="adv-report-save" data-id="advReportForm">' + dual("حفظ كمسودة", "Save draft") + "</button>" +
        '<button class="btn-solid" type="button" data-act="adv-report-submit" data-id="advReportForm">' + dual("إرسال التقرير", "Submit report") + "</button>" +
        "</div></form>"
      : "";
    var list = reports.length
      ? '<div class="av-list">' + reports.map(function (r) {
          return '<div class="av-row" style="cursor:default"><div class="grow"><div class="t">' +
            dual("تقرير", "Report") + " " + r.period_month + "/" + r.period_year + "</div>" +
            '<div class="s">' + escapeHtml(companyNameById(r.company_id)) + " · " +
            escapeHtml(r.recommendations || r.development || "—") + "</div></div>" +
            (r.status === "draft" && canWrite
              ? '<button class="btn-outline" type="button" data-act="adv-report-submit-one" data-id="' + plainNum(r.id) + '">' + dual("إرسال", "Submit") + "</button>"
              : "") +
            statusBadgeFromMap(r.status, { draft: ["مسودة", "Draft", "warn"], submitted: ["مُرسل", "Submitted", "ok"] }) +
            "</div>";
        }).join("") + "</div>"
      : noticeHtml("لا توجد تقارير شهرية.", "No monthly reports.");
    return panel("التقارير الشهرية للمستشار (S19)", "Advisor monthly reports (S19)",
      '<p class="note-block">' + dual("يحفظ المستشار تقريره الشهري (التطويرات والتحديات والتوصيات) ويرسله لمدير تطوير الأعمال؛ بعد الإرسال يصبح أصلاً غير قابل للتعديل.", "An advisor saves a monthly report (development, challenges, recommendations) and submits it to Business Development; once submitted it is an immutable original.") + "</p>" +
      form + list);
  }

  function onEmployeeAct(action, id, el) {
    if (action === "adv-report-submit-one") {
      busy(el, true);
      post("/api/v1/operations/advisor-reports/" + id + "/submit", {})
        .then(function () { toast(dual("تم إرسال التقرير.", "Report submitted."), "ok"); return renderAdvisors(); })
        .catch(function (err) { domainError(err); busy(el, false); });
      return;
    }
    if (action === "adv-report-save" || action === "adv-report-submit") {
      var payload = {
        company_id: parseInt(valOf("arCompany"), 10),
        advisor_user_id: parseInt(valOf("arUser"), 10),
        period_year: parseInt(valOf("arYear"), 10),
        period_month: parseInt(valOf("arMonth"), 10),
        development: valOf("arDev") || null,
        challenges: valOf("arChal") || null,
        recommendations: valOf("arRec") || null,
      };
      busy(el, true);
      post("/api/v1/operations/advisor-reports", payload)
        .then(function (report) {
          if (action === "adv-report-submit") {
            return post("/api/v1/operations/advisor-reports/" + report.id + "/submit", {})
              .then(function () { toast(dual("تم إرسال التقرير.", "Report submitted."), "ok"); });
          }
          toast(dual("تم حفظ المسودة.", "Draft saved."), "ok");
        })
        .then(function () { return renderAdvisors(); })
        .catch(function (err) { domainError(err); busy(el, false); });
      return;
    }
    if (action !== "submit") return;
    if (id === "empForm") {
      busy(el.querySelector("button"), true);
      return post("/api/v1/employees", {
        company_id: parseInt(valOf("eCompany"), 10),
        full_name_ar: valOf("eNameAr"),
        full_name_en: valOf("eNameEn") || null,
        job_title: valOf("eTitle") || null,
        hire_date: valOf("eHire") || null,
      }).then(function () { toast(dual("تمت إضافة الموظف.", "Employee added."), "ok"); return renderEmployees(); })
        .catch(function (err) { domainError(err); busy(el.querySelector("button"), false); });
    }
    if (id === "assessForm") {
      busy(el.querySelector("button"), true);
      var aType = valOf("asType");
      var payload = {
        company_id: parseInt(valOf("asCompany"), 10),
        period_label: valOf("asPeriod"),
        assessment_type: aType,
        summary: valOf("asSummary") || null,
      };
      // A leadership assessment is about a *user* (subject_user_id); an
      // employee assessment is about an employee (employee_id). Sending the
      // wrong key is a validation error, so map it explicitly.
      if (aType === "leadership") payload.subject_user_id = numVal("asEmp");
      else payload.employee_id = numVal("asEmp");
      return post("/api/v1/employees/assessments", payload)
        .then(function () { toast(dual("تم إنشاء التقييم.", "Assessment created."), "ok"); return renderAssessments(); })
        .catch(function (err) { domainError(err); busy(el.querySelector("button"), false); });
    }
    if (id === "advForm") {
      busy(el.querySelector("button"), true);
      return post("/api/v1/operations/advisory-sessions", {
        company_id: parseInt(valOf("adCompany"), 10),
        advisor_user_id: parseInt(valOf("adUser"), 10),
        scheduled_at: valOf("adWhen") || null,
        topic: valOf("adTopic") || null,
        notes: valOf("adNotes") || null,
        recommendations: valOf("adRec") || null,
      }).then(function () { toast(dual("تم تسجيل الجلسة.", "Session recorded."), "ok"); return renderAdvisors(); })
        .catch(function (err) { domainError(err); busy(el.querySelector("button"), false); });
    }
    if (id === "advAssignForm") {
      busy(el.querySelector("button"), true);
      return post("/api/v1/operations/advisors", {
        company_id: parseInt(valOf("aaCompany"), 10),
        advisor_user_id: parseInt(valOf("aaUser"), 10),
        specialty: valOf("aaSpecialty") || null,
      }).then(function () { toast(dual("تم إسناد المستشار.", "Advisor assigned."), "ok"); return renderAdvisors(); })
        .catch(function (err) { domainError(err); busy(el.querySelector("button"), false); });
    }
  }

  // ======================================================================
  // S13/S17/S18/S14 -- Tasks, weekly reports, campaigns
  // ======================================================================
  function renderOperationsView() {
    var host = byId("opsContent");
    if (!host) return Promise.resolve();
    if (!STATE.opsBound) {
      STATE.opsBound = true;
      bindOpsTabs();
      bindHost(host, onOpsAct);
    }
    if (!STATE.opsTab || !canOpsTab(STATE.opsTab)) STATE.opsTab = firstOpsTab();
    return renderOpsTab(STATE.opsTab);
  }

  var OPS_TABS = ["tasks", "weekly", "campaigns", "briefs"];
  var OPS_TAB_PERM = {
    tasks: ["task.read_own", "task.read_all"],
    weekly: ["weekly_report.read_own", "weekly_report.read_all"],
    campaigns: ["campaign.read"],
    briefs: ["management_brief.read"],
  };
  function canOpsTab(t) { return (OPS_TAB_PERM[t] || []).some(has); }
  function firstOpsTab() {
    for (var i = 0; i < OPS_TABS.length; i++) if (canOpsTab(OPS_TABS[i])) return OPS_TABS[i];
    return "tasks";
  }
  function bindOpsTabs() {
    document.querySelectorAll("[data-ops-tab]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var t = btn.getAttribute("data-ops-tab");
        if (!canOpsTab(t)) return;
        STATE.opsTab = t;
        document.querySelectorAll("[data-ops-tab]").forEach(function (b) { b.classList.toggle("on", b === btn); });
        renderOpsTab(t);
      });
    });
  }
  function renderOpsTab(tab) {
    var host = byId("opsContent");
    document.querySelectorAll("[data-ops-tab]").forEach(function (b) {
      b.classList.toggle("on", b.getAttribute("data-ops-tab") === tab);
    });
    host.innerHTML = loadingHtml();
    if (tab === "tasks") return renderTasks();
    if (tab === "weekly") return renderWeekly();
    if (tab === "campaigns") return renderCampaigns();
    if (tab === "briefs") return renderManagementBriefs();
    return Promise.resolve();
  }

  function renderTasks() {
    var host = byId("opsContent");
    return Promise.all([
      ensureCompanies(),
      get("/api/v1/operations/tasks").catch(function () { return []; }),
    ]).then(function (res) {
      var rows = res[1] || [];
      var canCreate = has("task.create");
      var create = canCreate
        ? '<form class="av-form av-form-inline" id="taskForm">' +
          field("الشركة", "Company", selectInput("tkCompany", companySelectOptions(false), STATE.companies.length ? STATE.companies[0].id : "")) +
          field("العنوان", "Title", textInput("tkTitle", "")) +
          field("الأولوية", "Priority", selectInput("tkPriority", [
            { value: "low", label: opt("منخفضة", "Low") },
            { value: "normal", label: opt("عادية", "Normal") },
            { value: "high", label: opt("عالية", "High") },
          ], "normal")) +
          field("تاريخ الاستحقاق", "Due date", dateInput("tkDue", "")) +
          '<div class="av-form-actions"><button class="btn-solid" type="submit">' +
          dual("إنشاء مهمة", "Create task") + "</button></div></form>"
        : "";
      var list = rows.length
        ? '<div class="av-list">' + rows.map(taskRow).join("") + "</div>"
        : noticeHtml("لا توجد مهام.", "No tasks.");
      host.innerHTML = panel("المهام", "Tasks", create + list);
      bindRowClicks(host, "task", openTask);
    }).catch(function (err) { handleLoadError(err); host.innerHTML = errorHtml(errText(err)); });
  }

  function taskRow(t) {
    var overdue = t.due_date && t.status !== "complete" && new Date(t.due_date) < new Date();
    return (
      '<div class="av-row"' + rowClickAttr("task", t) + ">" +
      '<div class="grow"><div class="t">' + escapeHtml(t.title) + "</div>" +
      '<div class="s">' + escapeHtml(companyNameById(t.company_id)) +
      (t.due_date ? " · " + dual("الاستحقاق", "Due") + " " + escapeHtml(dateStr(t.due_date)) : "") +
      (overdue ? " · " + dual("متأخرة", "Overdue") : "") + "</div></div>" +
      statusBadgeFromMap(t.priority, { low: ["منخفضة", "Low", "rev"], normal: ["عادية", "Normal", "warn"], high: ["عالية", "High", "miss"] }) +
      statusBadgeFromMap(t.status, {
        new: ["جديدة", "New", "warn"], in_progress: ["قيد التنفيذ", "In progress", "warn"],
        awaiting_review: ["بانتظار المراجعة", "Awaiting review", "warn"],
        complete: ["مكتملة", "Complete", "ok"], returned: ["مُعادة", "Returned", "miss"],
        cancelled: ["ملغاة", "Cancelled", "miss"],
      }) + "</div>"
    );
  }

  function openTask(t) {
    openModal({
      title: dual("المهمة", "Task"),
      wide: true,
      body: loadingHtml(),
      onMount: function (root, body) {
        body.innerHTML = taskDetail(t);
        var form = body.querySelector("#taskStatusForm");
        if (form) {
          form.addEventListener("submit", function (ev) {
            ev.preventDefault();
            post("/api/v1/operations/tasks/" + t.id + "/status", {
              status: valOf("tsStatus"),
              note: valOf("tsNote") || null,
            }).then(function () { toast(dual("تم تحديث المهمة.", "Task updated."), "ok"); closeModal(); renderTasks(); })
              .catch(domainError);
          });
        }
        var upForm = body.querySelector("#taskUpdateForm");
        if (upForm) {
          upForm.addEventListener("submit", function (ev) {
            ev.preventDefault();
            var btn = upForm.querySelector("button");
            busy(btn, true);
            patch("/api/v1/operations/tasks/" + t.id, {
              assignee_id: numVal("tuAssignee"),
              reviewer_id: numVal("tuReviewer"),
              priority: valOf("tuPriority"),
              progress_percent: numVal("tuProgress"),
              due_date: valOf("tuDue") || null,
            }).then(function () { toast(dual("تم حفظ المهمة.", "Task saved."), "ok"); closeModal(); renderTasks(); })
              .catch(function (err) { domainError(err); busy(btn, false); });
          });
        }
      },
    });
  }

  function taskDetail(t) {
    var events = t.events || [];
    var transition = has("task.status_change")
      ? '<form class="av-form av-form-inline" id="taskStatusForm">' +
        field("الحالة", "Status", selectInput("tsStatus", [
          { value: "new", label: opt("جديدة", "New") },
          { value: "in_progress", label: opt("قيد التنفيذ", "In progress") },
          { value: "awaiting_review", label: opt("بانتظار المراجعة", "Awaiting review") },
          { value: "complete", label: opt("مكتملة", "Complete") },
          { value: "returned", label: opt("إعادة", "Return") },
          { value: "cancelled", label: opt("إلغاء", "Cancel") },
        ], t.status)) +
        field("ملاحظة", "Note", textInput("tsNote", "")) +
        '<div class="av-form-actions"><button class="btn-outline" type="submit">' +
        dual("تحديث الحالة", "Update status") + "</button></div></form>"
      : "";
    var update = has("task.update")
      ? '<div class="sec-title">' + dual("إسناد وتقدّم", "Assignment & progress") + "</div>" +
        '<form class="av-form av-form-inline" id="taskUpdateForm">' +
        field("المسؤول (معرّف)", "Assignee id", numInput("tuAssignee", t.assignee_id || "")) +
        field("المراجع (معرّف)", "Reviewer id", numInput("tuReviewer", t.reviewer_id || "")) +
        field("الأولوية", "Priority", selectInput("tuPriority", [
          { value: "low", label: opt("منخفضة", "Low") },
          { value: "normal", label: opt("عادية", "Normal") },
          { value: "high", label: opt("عالية", "High") },
        ], t.priority)) +
        field("نسبة التقدّم", "Progress %", numInput("tuProgress", t.progress_percent == null ? 0 : t.progress_percent)) +
        field("تاريخ الاستحقاق", "Due date", dateInput("tuDue", t.due_date || "")) +
        '<div class="av-form-actions"><button class="btn-outline" type="submit">' +
        dual("حفظ", "Save") + "</button></div></form>"
      : "";
    var hist = events.length
      ? '<div class="av-list">' + events.map(function (e) {
          return '<div class="av-row" style="cursor:default"><div class="grow"><div class="t">' +
            escapeHtml((e.from_status || "—") + " → " + e.to_status) + "</div>" +
            '<div class="s">' + escapeHtml(dateStr(e.created_at)) + " · " + escapeHtml(e.note || "") + "</div></div></div>";
        }).join("") + "</div>"
      : noticeHtml("لا توجد تحولات.", "No transitions.");
    return panel("التفاصيل", "Details", '<div class="kv">' +
        kv(dual("العنوان", "Title"), escapeHtml(t.title)) +
        kv(dual("الشركة", "Company"), escapeHtml(companyNameById(t.company_id))) +
        kv(dual("المسؤول", "Assignee"), t.assignee_id ? plainNum(t.assignee_id) : "—") +
        kv(dual("المراجع", "Reviewer"), t.reviewer_id ? plainNum(t.reviewer_id) : "—") +
        kv(dual("التقدم", "Progress"), dec(t.progress_percent) + "%") +
        "</div>" + update + transition) +
      panel("السجل", "History", hist);
  }

  function renderWeekly() {
    var host = byId("opsContent");
    var canRead = has("weekly_report.read_own") || has("weekly_report.read_all");
    return Promise.all([
      ensureCompanies(),
      canRead
        ? get("/api/v1/operations/weekly-reports").catch(function () { return []; })
        : Promise.resolve([]),
      canRead
        ? get("/api/v1/operations/weekly-reports/questions").catch(function () { return []; })
        : Promise.resolve([]),
    ]).then(function (res) {
      var rows = res[1] || [];
      var questions = res[2] || [];
      var canSubmit = has("weekly_report.submit");
      var qFields = questions.map(function (q, i) {
        return field(
          STATE.lang === "ar" ? q.text_ar : q.text_en || q.text_ar,
          q.text_en || q.text_ar,
          textArea("wrQ" + i, "", ""),
        );
      }).join("");
      var create = canSubmit
        ? '<form class="av-form" id="weeklyForm">' +
          '<div class="av-form-inline">' +
          field("الشركة", "Company", selectInput("wrCompany", companySelectOptions(false), STATE.companies.length ? STATE.companies[0].id : "")) +
          field("السنة", "Year", numInput("wrYear", STATE.year || "")) +
          field("الأسبوع", "Week", numInput("wrWeek", "")) +
          "</div>" + qFields +
          field("الملخص", "Summary", textArea("wrSummary", "", "")) +
          '<div class="av-form-actions"><button class="btn-solid" type="submit">' +
          dual("إرسال التقرير الأسبوعي", "Submit weekly report") + "</button></div></form>"
        : "";
      var list = rows.length
        ? '<div class="av-list">' + rows.map(function (r) {
            return '<div class="av-row" style="cursor:default"><div class="grow"><div class="t">' +
              dual("أسبوع", "Week") + " " + dec(r.period_week) + " · " + dec(r.period_year) + "</div>" +
              '<div class="s">' + escapeHtml(companyNameById(r.company_id)) + " · " +
              (r.answers || []).length + " " + dual("إجابات", "answers") + "</div></div>" +
              statusBadgeFromMap(r.status, { draft: ["مسودة", "Draft", "warn"], submitted: ["مُقدَّم", "Submitted", "ok"] }) +
              "</div>";
          }).join("") + "</div>"
        : noticeHtml("لا توجد تقارير أسبوعية.", "No weekly reports.");
      host.innerHTML = panel("التقرير الأسبوعي (بحد أقصى الأسئلة المعتمدة)", "Weekly report (at most the approved question set)", create + list) + weeklyTemplatePanel(questions);
      var tplForm = byId("weeklyQForm");
      if (tplForm) {
        tplForm.addEventListener("submit", function (ev) {
          ev.preventDefault();
          var btn = tplForm.querySelector("button");
          busy(btn, true);
          post("/api/v1/operations/weekly-reports/questions", {
            code: valOf("wqCode"),
            text_ar: valOf("wqAr"),
            text_en: valOf("wqEn") || null,
            order_index: numVal("wqOrder") || 0,
          }).then(function () { toast(dual("تمت إضافة السؤال.", "Question added."), "ok"); return renderWeekly(); })
            .catch(function (err) { domainError(err); busy(btn, false); });
        });
      }
      var form = byId("weeklyForm");
      if (form) {
        form.addEventListener("submit", function (ev) {
          ev.preventDefault();
          var answers = questions.map(function (q, i) {
            return { question_id: q.id, question_code: q.code, answer: valOf("wrQ" + i) || null };
          });
          busy(form.querySelector("button"), true);
          post("/api/v1/operations/weekly-reports", {
            company_id: parseInt(valOf("wrCompany"), 10),
            period_year: parseInt(valOf("wrYear"), 10),
            period_week: parseInt(valOf("wrWeek"), 10),
            answers: answers,
            summary: valOf("wrSummary") || null,
          }).then(function () { toast(dual("تم إرسال التقرير.", "Report submitted."), "ok"); return renderWeekly(); })
            .catch(function (err) { domainError(err); busy(form.querySelector("button"), false); });
        });
      }
    }).catch(function (err) { handleLoadError(err); host.innerHTML = errorHtml(errText(err)); });
  }

  function weeklyTemplatePanel(questions) {
    if (!has("weekly_report.template.manage")) return "";
    var list = questions.length
      ? '<div class="av-list">' + questions.map(function (q) {
          return '<div class="av-row" style="cursor:default"><div class="grow"><div class="t">' +
            escapeHtml(STATE.lang === "ar" ? q.text_ar : q.text_en || q.text_ar) + "</div>" +
            '<div class="s">' + escapeHtml(q.code) + " · " + dual("الترتيب", "Order") + " " + plainNum(q.order_index || 0) + "</div></div></div>";
        }).join("") + "</div>"
      : noticeHtml("لا توجد أسئلة معتمدة بعد.", "No approved questions yet.");
    var form =
      '<form class="av-form av-form-inline" id="weeklyQForm">' +
      field("الكود", "Code", textInput("wqCode", "")) +
      field("النص (عربي)", "Text (AR)", textInput("wqAr", "")) +
      field("النص (إنجليزي)", "Text (EN)", textInput("wqEn", "")) +
      field("الترتيب", "Order", numInput("wqOrder", "0")) +
      '<div class="av-form-actions"><button class="btn-solid" type="submit">' +
      dual("إضافة سؤال", "Add question") + "</button></div></form>";
    return panel("قالب الأسئلة (S17)", "Question template (S17)",
      '<p class="note-block">' + dual("التقرير الأسبوعي لا يقبل أكثر من الأسئلة المعتمدة هنا.", "The weekly report accepts at most the questions approved here.") + "</p>" +
      form + list);
  }

  function renderCampaigns() {
    var host = byId("opsContent");
    return Promise.all([
      ensureCompanies(),
      get("/api/v1/operations/campaigns").catch(function () { return []; }),
    ]).then(function (res) {
      var rows = res[1] || [];
      var canManage = has("campaign.manage");
      var create = canManage
        ? '<form class="av-form av-form-inline" id="campaignForm">' +
          field("الشركة", "Company", selectInput("cpCompany", companySelectOptions(false), STATE.companies.length ? STATE.companies[0].id : "")) +
          field("الاسم", "Name", textInput("cpName", "")) +
          field("المنصة", "Platform", textInput("cpPlatform", "")) +
          field("الميزانية", "Budget", numInput("cpBudget", "")) +
          field("من", "From", dateInput("cpFrom", "")) +
          field("إلى", "To", dateInput("cpTo", "")) +
          '<div class="av-form-actions"><button class="btn-solid" type="submit">' +
          dual("إنشاء حملة", "Create campaign") + "</button></div></form>"
        : "";
      var list = rows.length
        ? '<div class="av-list">' + rows.map(function (c) {
            var results = canManage
              ? '<form class="av-form av-form-inline" data-stop="1" id="campRes' + c.id + '">' +
                field("الإنفاق", "Spend", numInput("crSpend" + c.id, c.spend)) +
                field("عدد العملاء المحتملين", "Leads", numInput("crLeads" + c.id, c.lead_count)) +
                field("التحويلات", "Conversions", numInput("crConv" + c.id, c.conversion_count)) +
                '<div class="av-form-actions"><button class="btn-outline" type="submit" data-act="camp-results" data-id="' + c.id + '">' +
                dual("حفظ النتائج", "Save results") + "</button></div></form>"
              : "";
            return '<div class="av-row" style="flex-direction:column;align-items:stretch;cursor:default"><div style="display:flex;align-items:center;gap:11px">' +
              '<div class="grow"><div class="t">' + escapeHtml(c.name) + "</div>" +
              '<div class="s">' + escapeHtml(companyNameById(c.company_id)) + " · " + escapeHtml(c.platform || "") +
              " · " + dual("الميزانية", "Budget") + " " + dec(c.budget) + "</div></div>" +
              statusBadgeFromMap(c.status, { planned: ["مخططة", "Planned", "warn"], active: ["نشطة", "Active", "ok"], completed: ["مكتملة", "Completed", "rev"], cancelled: ["ملغاة", "Cancelled", "miss"] }) +
              "</div>" + results + "</div>";
          }).join("") + "</div>"
        : noticeHtml("لا توجد حملات.", "No campaigns.");
      host.innerHTML = panel("الحملات (التنفيذ خارجي — النتائج تُسجَّل يدويًا)", "Campaigns (external execution — results recorded manually)", create + list);
    }).catch(function (err) { handleLoadError(err); host.innerHTML = errorHtml(errText(err)); });
  }

  function onOpsAct(action, id, el) {
    if (action === "brief-submit") {
      return submitManagementBrief(id, el);
    }
    if (action === "brief-load") {
      return loadBriefDraft(parseInt(valOf("mbYear"), 10), parseInt(valOf("mbMonth"), 10));
    }
    if (action !== "submit") return;
    if (id === "briefForm") {
      return saveManagementBrief(el);
    }
    if (id === "taskForm") {
      busy(el.querySelector("button"), true);
      return post("/api/v1/operations/tasks", {
        company_id: parseInt(valOf("tkCompany"), 10),
        title: valOf("tkTitle"),
        priority: valOf("tkPriority"),
        due_date: valOf("tkDue") || null,
      }).then(function () { toast(dual("تم إنشاء المهمة.", "Task created."), "ok"); return renderTasks(); })
        .catch(function (err) { domainError(err); busy(el.querySelector("button"), false); });
    }
    if (id === "campaignForm") {
      busy(el.querySelector("button"), true);
      return post("/api/v1/operations/campaigns", {
        company_id: parseInt(valOf("cpCompany"), 10),
        name: valOf("cpName"),
        platform: valOf("cpPlatform") || null,
        budget: numVal("cpBudget"),
        start_date: valOf("cpFrom") || null,
        end_date: valOf("cpTo") || null,
      }).then(function () { toast(dual("تم إنشاء الحملة.", "Campaign created."), "ok"); return renderCampaigns(); })
        .catch(function (err) { domainError(err); busy(el.querySelector("button"), false); });
    }
    var m = /^campRes(\d+)$/.exec(id);
    if (m) {
      var cid = m[1];
      busy(el.querySelector("button"), true);
      return patch("/api/v1/operations/campaigns/" + cid, {
        spend: numVal("crSpend" + cid),
        lead_count: valOf("crLeads" + cid) === "" ? null : parseInt(valOf("crLeads" + cid), 10),
        conversion_count: valOf("crConv" + cid) === "" ? null : parseInt(valOf("crConv" + cid), 10),
      }).then(function () { toast(dual("تم حفظ النتائج.", "Results saved."), "ok"); return renderCampaigns(); })
        .catch(function (err) { domainError(err); busy(el.querySelector("button"), false); });
    }
  }

  // ======================================================================
  // S21 -- BD five-axis management brief
  // ======================================================================
  var BRIEF_AXES = [
    { key: "axis_companies", ar: "الشركات التابعة", en: "Subsidiaries" },
    { key: "axis_projects", ar: "المشاريع والفرص", en: "Projects & opportunities" },
    { key: "axis_employees", ar: "الموظفون", en: "Employees" },
    { key: "axis_risks", ar: "المخاطر", en: "Risks" },
    { key: "axis_decisions", ar: "القرارات المطلوبة", en: "Decisions required" },
  ];

  function renderManagementBriefs() {
    var host = byId("opsContent");
    host.innerHTML = loadingHtml();
    return get("/api/v1/operations/management-briefs").catch(function () { return []; })
      .then(function (rows) {
        rows = rows || [];
        var canAuthor = has("management_brief.submit");
        var now = new Date();
        var form = canAuthor
          ? '<form class="av-form" id="briefForm">' +
            '<div class="av-form-inline">' +
            field("السنة", "Year", numInput("mbYear", now.getFullYear(), "")) +
            field("الشهر", "Month", selectInput("mbMonth", monthOptions(), now.getMonth() + 1)) +
            field("الأولوية", "Urgency", selectInput("mbUrgency", [
              { value: "monthly", label: opt("شهري", "Monthly") },
              { value: "urgent", label: opt("عاجل", "Urgent") },
            ], "monthly")) +
            "</div>" +
            field("الملخص التنفيذي", "Executive summary", textArea("mbSummary", "", "")) +
            BRIEF_AXES.map(function (a) {
              return field(a.ar, a.en, textArea("mb_" + a.key, "", ""));
            }).join("") +
            '<div class="av-form-actions">' +
            '<button class="btn-outline" type="button" data-act="brief-load" data-id="1">' +
            dual("تحميل مسودة الفترة", "Load period draft") + "</button>" +
            '<button class="btn-solid" type="submit">' +
            dual("حفظ المسودة", "Save draft") + "</button></div></form>"
          : "";
        var list = rows.length
          ? '<div class="av-list">' + rows.map(briefRow).join("") + "</div>"
          : noticeHtml("لا توجد تقارير بعد.", "No briefs yet.");
        host.innerHTML = panel(
          "تقرير تطوير الأعمال (خمسة محاور)",
          "Business development brief (five axes)",
          form + list,
        );
      })
      .catch(function (err) { handleLoadError(err); host.innerHTML = errorHtml(errText(err)); });
  }

  function monthOptions() {
    var out = [];
    for (var m = 1; m <= 12; m++) {
      out.push({
        value: m,
        label: STATE.lang === "ar"
          ? AR_MONTHS[m - 1] + " (" + toArabicDigits(String(m)) + ")"
          : EN_MONTHS[m - 1],
      });
    }
    return out;
  }

  function briefRow(b) {
    var period = STATE.lang === "ar"
      ? AR_MONTHS[b.period_month - 1] + " " + toArabicDigits(String(b.period_year))
      : EN_MONTHS[b.period_month - 1] + " " + b.period_year;
    var canSubmit = has("management_brief.submit") && b.status === "draft";
    return (
      '<div class="av-row" style="flex-direction:column;align-items:stretch;cursor:default">' +
      '<div style="display:flex;align-items:center;gap:11px">' +
      '<div class="grow"><div class="t">' + dual("تقرير", "Brief") + " · " + escapeHtml(period) + "</div>" +
      '<div class="s">' + escapeHtml(b.executive_summary || "") + "</div></div>" +
      statusBadgeFromMap(b.urgency, { monthly: ["شهري", "Monthly", "rev"], urgent: ["عاجل", "Urgent", "miss"] }) +
      statusBadgeFromMap(b.status, { draft: ["مسودة", "Draft", "warn"], submitted: ["مُرسل", "Submitted", "ok"] }) +
      "</div>" +
      (canSubmit
        ? '<div class="pbtns" style="margin-top:8px"><button class="btn-solid" data-stop="1" data-act="brief-submit" data-id="' + b.id + '">' +
          dual("إرسال للمالك", "Submit to owner") + "</button></div>"
        : "") +
      "</div>"
    );
  }

  function loadBriefDraft(periodYear, periodMonth) {
    return get(
      "/api/v1/operations/management-briefs?period_year=" + periodYear +
        "&period_month=" + periodMonth,
    ).then(function (rows) {
      var b = (rows || [])[0];
      var set = function (id, v) {
        var el = byId(id);
        if (el) el.value = v === null || v === undefined ? "" : v;
      };
      if (b) {
        set("mbSummary", b.executive_summary);
        BRIEF_AXES.forEach(function (a) { set("mb_" + a.key, b[a.key]); });
        var u = byId("mbUrgency");
        if (u) u.value = b.urgency;
        return b;
      }
      set("mbSummary", "");
      BRIEF_AXES.forEach(function (a) { set("mb_" + a.key, ""); });
      return null;
    });
  }

  function saveManagementBrief(el) {
    var payload = {
      period_year: parseInt(valOf("mbYear"), 10),
      period_month: parseInt(valOf("mbMonth"), 10),
      urgency: valOf("mbUrgency") || "monthly",
      executive_summary: valOf("mbSummary") || null,
    };
    BRIEF_AXES.forEach(function (a) {
      payload[a.key] = valOf("mb_" + a.key) || null;
    });
    busy(el.querySelector("button[type=submit]"), true);
    return post("/api/v1/operations/management-briefs", payload)
      .then(function () { toast(dual("تم حفظ المسودة.", "Draft saved."), "ok"); return renderManagementBriefs(); })
      .catch(function (err) { domainError(err); busy(el.querySelector("button[type=submit]"), false); });
  }

  function submitManagementBrief(id, el) {
    busy(el, true);
    return post("/api/v1/operations/management-briefs/" + id + "/submit", {})
      .then(function () { toast(dual("أُرسل التقرير للمالك.", "Brief submitted to the owner."), "ok"); return renderManagementBriefs(); })
      .catch(function (err) { domainError(err); busy(el, false); });
  }

  // ======================================================================
  // S22 -- Owner decisions (D07)
  // ======================================================================
  function renderDecisionsView() {
    var host = byId("decContent");
    if (!host) return Promise.resolve();
    host.innerHTML = loadingHtml();
    return Promise.all([
      ensureCompanies(),
      get("/api/v1/operations/owner-decisions").catch(function () { return []; }),
    ]).then(function (res) {
      var rows = res[1] || [];
      var canManage = has("owner_decision.manage");
      var create = canManage
        ? '<form class="av-form av-form-inline" id="decForm">' +
          field("الرقم", "Number", textInput("dcNumber", "")) +
          field("العنوان", "Title", textInput("dcTitle", "")) +
          field("الشركة (اختياري)", "Company (optional)", selectInput("dcCompany", companySelectOptions(true), "")) +
          field("المُنفّذ (معرّف)", "Executor id", numInput("dcExecutor", "")) +
          field("الاستحقاق", "Due date", dateInput("dcDue", "")) +
          field("النص", "Body", textInput("dcBody", "")) +
          '<div class="av-form-actions"><button class="btn-solid" type="submit">' +
          dual("إصدار قرار", "Issue decision") + "</button></div></form>"
        : "";
      var list = rows.length
        ? '<div class="av-list">' + rows.map(function (d) {
            var controls = canManage
              ? '<div class="av-user-controls" data-stop="1">' +
                selectInput("dcStatus" + d.id, [
                  { value: "open", label: opt("مفتوح", "Open") },
                  { value: "in_progress", label: opt("قيد التنفيذ", "In progress") },
                  { value: "done", label: opt("منجز", "Done") },
                  { value: "cancelled", label: opt("ملغى", "Cancelled") },
                ], d.status) +
                '<button class="btn-outline" data-act="dec-status" data-id="' + d.id + '">' + dual("تحديث", "Update") + "</button></div>"
              : "";
            return '<div class="av-row" style="flex-direction:column;align-items:stretch;cursor:default"><div style="display:flex;align-items:center;gap:11px">' +
              '<div class="grow"><div class="t">' + escapeHtml(d.number + " · " + d.title) + "</div>" +
              '<div class="s">' + (d.company_id ? escapeHtml(companyNameById(d.company_id)) + " · " : "") +
              dual("الاستحقاق", "Due") + " " + escapeHtml(dateStr(d.due_date)) + "</div></div>" +
              statusBadgeFromMap(d.status, { open: ["مفتوح", "Open", "warn"], in_progress: ["قيد التنفيذ", "In progress", "warn"], done: ["منجز", "Done", "ok"], cancelled: ["ملغى", "Cancelled", "miss"] }) +
              "</div>" + controls + "</div>";
          }).join("") + "</div>"
        : noticeHtml("لا توجد قرارات.", "No decisions.");
      host.innerHTML = panel("قرارات المالك", "Owner decisions", create + list);
      var form = byId("decForm");
      if (form) {
        form.addEventListener("submit", function (ev) {
          ev.preventDefault();
          busy(form.querySelector("button"), true);
          post("/api/v1/operations/owner-decisions", {
            number: valOf("dcNumber"),
            title: valOf("dcTitle"),
            company_id: valOf("dcCompany") ? parseInt(valOf("dcCompany"), 10) : null,
            executor_user_id: numVal("dcExecutor"),
            due_date: valOf("dcDue") || null,
            body: valOf("dcBody") || null,
          }).then(function () { toast(dual("تم إصدار القرار.", "Decision issued."), "ok"); return renderDecisionsView(); })
            .catch(function (err) { domainError(err); busy(form.querySelector("button"), false); });
        });
      }
      host.querySelectorAll('[data-act="dec-status"]').forEach(function (btn) {
        btn.addEventListener("click", function () {
          var did = btn.getAttribute("data-id");
          patch("/api/v1/operations/owner-decisions/" + did, { status: valOf("dcStatus" + did) })
            .then(function () { toast(dual("تم تحديث القرار.", "Decision updated."), "ok"); return renderDecisionsView(); })
            .catch(domainError);
        });
      });
    }).catch(function (err) { handleLoadError(err); host.innerHTML = errorHtml(errText(err)); });
  }

  // ======================================================================
  // S20 -- Projects & opportunities
  // ======================================================================
  var PROJECT_TYPE_LABEL = { opportunity: ["فرصة", "Opportunity"], project: ["مشروع", "Project"] };
  var PROJECT_STATUS_LABEL = {
    open: ["مفتوح", "Open", "warn"],
    in_progress: ["قيد التنفيذ", "In progress", "warn"],
    on_hold: ["معلّق", "On hold", "rev"],
    closed: ["مغلق", "Closed", "ok"],
    cancelled: ["ملغى", "Cancelled", "miss"],
  };

  function projectTypeBadge(t) {
    var m = PROJECT_TYPE_LABEL[t] || [t, t];
    return '<span class="badge rev">' + escapeHtml(STATE.lang === "ar" ? m[0] : m[1]) + "</span>";
  }

  function renderProjectsView() {
    var host = byId("projContent");
    if (!host) return Promise.resolve();
    host.innerHTML = loadingHtml();
    return Promise.all([
      ensureCompanies(),
      get("/api/v1/operations/projects").catch(function () { return []; }),
    ]).then(function (res) {
      var rows = res[1] || [];
      var canManage = has("project.manage");
      var create = canManage
        ? '<form class="av-form av-form-inline" id="projectForm">' +
          field("النوع", "Type", selectInput("prType", [
            { value: "opportunity", label: opt("فرصة", "Opportunity") },
            { value: "project", label: opt("مشروع", "Project") },
          ], "opportunity")) +
          field("الاسم", "Name", textInput("prName", "")) +
          field("الشركة (اختياري)", "Company (optional)", selectInput("prCompany", companySelectOptions(true), "")) +
          field("الفترة من", "Period from", dateInput("prFrom", "")) +
          field("الفترة إلى", "Period to", dateInput("prTo", "")) +
          field("تقدير القيمة", "Estimated value", numInput("prValue", "")) +
          field("العملة", "Currency", textInput("prCurrency", "SAR")) +
          field("تقدير الموارد والجدوى", "Resource / feasibility estimate", textInput("prResources", "")) +
          field("الهدف", "Objective", textInput("prObjective", "")) +
          field("الوصف", "Description", textInput("prDescription", "")) +
          field("مرتبط بقرار المالك (رقم)", "Linked owner decision (id)", numInput("prDecision", "")) +
          '<div class="av-form-actions"><button class="btn-solid" type="submit">' +
          dual("إضافة سجل", "Add record") + "</button></div></form>"
        : "";
      var list = rows.length
        ? '<div class="av-list">' + rows.map(function (r) {
            var est = r.estimated_value !== null && r.estimated_value !== undefined
              ? escapeHtml(plainNum(r.estimated_value) + " " + (r.currency || ""))
              : dual("—", "—");
            var controls = canManage
              ? '<div class="av-user-controls" data-stop="1">' +
                selectInput("prStatus" + r.id, [
                  { value: "open", label: opt("مفتوح", "Open") },
                  { value: "in_progress", label: opt("قيد التنفيذ", "In progress") },
                  { value: "on_hold", label: opt("معلّق", "On hold") },
                  { value: "closed", label: opt("مغلق", "Closed") },
                  { value: "cancelled", label: opt("ملغى", "Cancelled") },
                ], r.status) +
                '<button class="btn-outline" data-act="proj-status" data-id="' + r.id + '">' + dual("تحديث", "Update") + "</button></div>"
              : "";
            return '<div class="av-row" style="flex-direction:column;align-items:stretch;cursor:default"><div style="display:flex;align-items:center;gap:11px">' +
              '<div class="grow"><div class="t">' + escapeHtml(r.name) + "</div>" +
              '<div class="s">' + projectTypeBadge(r.record_type) + " " +
              (r.company_id ? escapeHtml(companyNameById(r.company_id)) + " · " : "") +
              (r.period_start || r.period_end
                ? dual("الفترة", "Period") + " " + escapeHtml(dateStr(r.period_start)) + " – " + escapeHtml(dateStr(r.period_end)) + " · "
                : "") +
              dual("تقدير", "Estimate") + " " + est +
              (r.resource_estimate ? " · " + escapeHtml(r.resource_estimate) : "") +
              "</div>" +
              (r.objective ? '<div class="s">' + escapeHtml(r.objective) + "</div>" : "") +
              "</div>" +
              statusBadgeFromMap(r.status, PROJECT_STATUS_LABEL) +
              "</div>" + controls + "</div>";
          }).join("") + "</div>"
        : noticeHtml("لا توجد مشاريع أو فرص.", "No projects or opportunities.");
      host.innerHTML = panel("المشاريع والفرص", "Projects & opportunities", create + list);
      var form = byId("projectForm");
      if (form) {
        form.addEventListener("submit", function (ev) {
          ev.preventDefault();
          busy(form.querySelector("button"), true);
          post("/api/v1/operations/projects", {
            record_type: valOf("prType"),
            name: valOf("prName"),
            company_id: valOf("prCompany") ? parseInt(valOf("prCompany"), 10) : null,
            period_start: valOf("prFrom") || null,
            period_end: valOf("prTo") || null,
            estimated_value: numVal("prValue"),
            currency: valOf("prCurrency") || "SAR",
            resource_estimate: valOf("prResources") || null,
            objective: valOf("prObjective") || null,
            description: valOf("prDescription") || null,
            owner_decision_id: numVal("prDecision"),
          }).then(function () { toast(dual("تمت إضافة السجل.", "Record added."), "ok"); return renderProjectsView(); })
            .catch(function (err) { domainError(err); busy(form.querySelector("button"), false); });
        });
      }
      host.querySelectorAll('[data-act="proj-status"]').forEach(function (btn) {
        btn.addEventListener("click", function () {
          var rid = btn.getAttribute("data-id");
          patch("/api/v1/operations/projects/" + rid, { status: valOf("prStatus" + rid) })
            .then(function () { toast(dual("تم تحديث السجل.", "Record updated."), "ok"); return renderProjectsView(); })
            .catch(domainError);
        });
      });
    }).catch(function (err) { handleLoadError(err); host.innerHTML = errorHtml(errText(err)); });
  }

  // ======================================================================
  // S04/S26/S27/S28 -- Holding accounting (D01/D07/D08)
  // ======================================================================
  function renderAccountingView() {
    var host = byId("acctContent");
    if (!host) return Promise.resolve();
    if (!STATE.acctBound) {
      STATE.acctBound = true;
      bindAcctTabs();
      bindHost(host, onAcctAct);
    }
    if (!STATE.acctTab || !canAcctTab(STATE.acctTab)) STATE.acctTab = firstAcctTab();
    return renderAcctTab(STATE.acctTab);
  }

  var ACCT_TABS = ["balances", "accounts", "journals", "trial", "ledger", "statements", "invoices", "parties", "interbalances", "assets", "budgets", "kpis", "policies"];
  var ACCT_TAB_PERM = {
    balances: ["opening_balance.read"],
    accounts: ["account.read"],
    journals: ["journal.read"],
    trial: ["journal.read"],
    ledger: ["journal.read"],
    statements: ["journal.read"],
    invoices: ["invoice.read"],
    parties: ["party.read"],
    interbalances: ["interbalance.read"],
    assets: ["asset.read"],
    budgets: ["budget.read"],
    kpis: ["kpi.read"],
    policies: ["accounting_policy.read"],
  };
  function canAcctTab(t) { return (ACCT_TAB_PERM[t] || []).some(has); }
  function firstAcctTab() {
    for (var i = 0; i < ACCT_TABS.length; i++) if (canAcctTab(ACCT_TABS[i])) return ACCT_TABS[i];
    return "balances";
  }
  function bindAcctTabs() {
    document.querySelectorAll("[data-acct-tab]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var t = btn.getAttribute("data-acct-tab");
        if (!canAcctTab(t)) return;
        STATE.acctTab = t;
        document.querySelectorAll("[data-acct-tab]").forEach(function (b) { b.classList.toggle("on", b === btn); });
        renderAcctTab(t);
      });
    });
  }
  function renderAcctTab(tab) {
    var host = byId("acctContent");
    document.querySelectorAll("[data-acct-tab]").forEach(function (b) {
      b.classList.toggle("on", b.getAttribute("data-acct-tab") === tab);
    });
    host.innerHTML = loadingHtml();
    if (tab === "balances") return renderOpeningBalances();
    if (tab === "accounts") return renderAccounts();
    if (tab === "journals") return renderJournals();
    if (tab === "trial") return renderTrialBalance();
    if (tab === "ledger") return renderLedgerActivity();
    if (tab === "statements") return renderStatements();
    if (tab === "invoices") return renderInvoices();
    if (tab === "parties") return renderParties();
    if (tab === "interbalances") return renderInterbalances();
    if (tab === "assets") return renderAssets();
    if (tab === "budgets") return renderBudgets();
    if (tab === "kpis") return renderKpis();
    if (tab === "policies") return renderPolicies();
    return Promise.resolve();
  }

  function renderOpeningBalances() {
    var host = byId("acctContent");
    return Promise.all([ensureCompanies(), get("/api/v1/accounting/opening-balances").catch(function () { return []; })]).then(function (res) {
      var rows = res[1] || [];
      var canManage = has("opening_balance.manage");
      var create = canManage
        ? '<form class="av-form av-form-inline" id="obForm">' +
          field("الشركة", "Company", selectInput("obCompany", companySelectOptions(false), STATE.companies.length ? STATE.companies[0].id : "")) +
          field("السنة", "Year", numInput("obYear", STATE.year || "")) +
          field("الشهر", "Month", numInput("obMonth", "")) +
          field("النوع", "Kind", selectInput("obKind", [
            { value: "opening", label: opt("افتتاحي", "Opening") },
            { value: "carry_forward", label: opt("مرحّل", "Carry-forward") },
          ], "opening")) +
          field("بنك", "Bank", numInput("obBank", "")) +
          field("نقد", "Cash", numInput("obCash", "")) +
          field("ذمم مدينة", "Receivables", numInput("obRecv", "")) +
          field("ديون", "Debts", numInput("obDebts", "")) +
          '<div class="av-form-actions"><button class="btn-solid" type="submit">' +
          dual("تسجيل رصيد", "Record balance") + "</button></div></form>"
        : "";
      var note = '<p class="note-block">' + dual("الأرصدة قيم لا إيرادات، ولا تُرحّل تلقائيًا من ديسمبر قبل المراجعة والاعتماد.", "Balances are not revenue, and are never auto-carried from December before review and approval.") + "</p>";
      var list = rows.length
        ? '<div class="av-list">' + rows.map(function (o) {
            var controls = (o.status === "draft" && has("opening_balance.manage")
              ? actBtn("opening_balance.manage", "ob-submit", o.id, "إرسال", "Submit")
              : "") + (o.status === "submitted" && has("opening_balance.approve")
              ? actBtn("opening_balance.approve", "ob-approve", o.id, "اعتماد", "Approve")
              : "");
            return '<div class="av-row" style="flex-direction:column;align-items:stretch;cursor:default"><div style="display:flex;align-items:center;gap:11px">' +
              '<div class="grow"><div class="t">' + escapeHtml(companyNameById(o.company_id)) + " · " +
              escapeHtml(o.kind) + "</div>" +
              '<div class="s">' + dec(o.period_month) + "/" + dec(o.period_year) +
              " · " + dual("بنك", "Bank") + " " + dec(o.bank) + " · " + dual("نقد", "Cash") + " " + dec(o.cash) + "</div></div>" +
              statusBadgeFromMap(o.status, { draft: ["مسودة", "Draft", "warn"], submitted: ["مُقدَّم", "Submitted", "warn"], approved: ["معتمد", "Approved", "ok"] }) +
              "</div>" + (controls ? '<div class="av-user-controls" data-stop="1">' + controls + "</div>" : "") + "</div>";
          }).join("") + "</div>"
        : noticeHtml("لا توجد أرصدة.", "No balances.");
      host.innerHTML = panel("الأرصدة الافتتاحية والمرحّلة (D08)", "Opening & carry-forward balances (D08)", note + create + list);
    }).catch(function (err) { handleLoadError(err); host.innerHTML = errorHtml(errText(err)); });
  }

  function renderAccounts() {
    var host = byId("acctContent");
    return Promise.all([ensureCompanies(), get("/api/v1/accounting/accounts").catch(function () { return []; })]).then(function (res) {
      var rows = res[1] || [];
      var canManage = has("account.manage");
      var create = canManage
        ? '<form class="av-form av-form-inline" id="acctForm">' +
          field("الشركة", "Company", selectInput("acCompany", companySelectOptions(false), STATE.companies.length ? STATE.companies[0].id : "")) +
          field("الكود", "Code", textInput("acCode", "")) +
          field("الاسم (عربي)", "Name (AR)", textInput("acNameAr", "")) +
          field("الاسم (إنجليزي)", "Name (EN)", textInput("acNameEn", "")) +
          field("النوع", "Type", selectInput("acType", [
            { value: "asset", label: opt("أصول", "Asset") },
            { value: "liability", label: opt("التزامات", "Liability") },
            { value: "equity", label: opt("حقوق ملكية", "Equity") },
            { value: "revenue", label: opt("إيرادات", "Revenue") },
            { value: "expense", label: opt("مصروفات", "Expense") },
          ], "asset")) +
          '<div class="av-form-actions"><button class="btn-solid" type="submit">' +
          dual("إضافة حساب", "Add account") + "</button></div></form>"
        : "";
      var list = rows.length
        ? '<div class="av-list">' + rows.map(function (a) {
            return '<div class="av-row" style="cursor:default"><div class="grow"><div class="t">' +
              escapeHtml(a.code + " · " + (STATE.lang === "ar" ? a.name_ar : a.name_en || a.name_ar)) + "</div>" +
              '<div class="s">' + escapeHtml(companyNameById(a.company_id)) + " · " + escapeHtml(a.account_type) + "</div></div></div>";
          }).join("") + "</div>"
        : noticeHtml("لا توجد حسابات.", "No accounts.");
      host.innerHTML = panel("دليل الحسابات (D01)", "Chart of accounts (D01)", create + list);
    }).catch(function (err) { handleLoadError(err); host.innerHTML = errorHtml(errText(err)); });
  }

  function renderJournals() {
    var host = byId("acctContent");
    return Promise.all([ensureCompanies(), get("/api/v1/accounting/journals").catch(function () { return []; })]).then(function (res) {
      var rows = res[1] || [];
      var canCreate = has("journal.create");
      var create = canCreate
        ? '<form class="av-form" id="journalForm">' +
          '<div class="av-form-inline">' +
          field("الشركة", "Company", selectInput("jnCompany", companySelectOptions(false), STATE.companies.length ? STATE.companies[0].id : "")) +
          field("التاريخ", "Date", dateInput("jnDate", "")) +
          field("الوصف", "Description", textInput("jnDesc", "")) +
          "</div>" +
          '<p class="note-block">' + dual("قيد مزدوج: أضف سطرين على الأقل بمدين ودائن متساويين. القيد المُرحّل غير قابل للتعديل.", "Double-entry: add at least two lines with equal debit and credit. A posted journal is immutable.") + "</p>" +
          '<div id="jnLines"></div>' +
          '<div class="av-form-actions"><button class="btn-outline" type="button" data-act="jn-add-line">' +
          dual("إضافة سطر", "Add line") + '</button><button class="btn-solid" type="submit">' +
          dual("حفظ القيد", "Save journal") + "</button></div></form>"
        : "";
      var list = rows.length
        ? '<div class="av-list">' + rows.map(function (j) {
            var controls = (j.status === "draft" && has("journal.post")
              ? actBtn("journal.post", "jn-post", j.id, "ترحيل", "Post")
              : "") + (j.status === "posted" && has("journal.reverse")
              ? actBtn("journal.reverse", "jn-reverse", j.id, "عكس القيد", "Reverse")
              : "");
            return '<div class="av-row" style="flex-direction:column;align-items:stretch;cursor:default"><div style="display:flex;align-items:center;gap:11px">' +
              '<div class="grow"><div class="t">' + escapeHtml(j.number || ("#" + j.id)) + " · " + escapeHtml(dateStr(j.entry_date)) + "</div>" +
              '<div class="s">' + escapeHtml(companyNameById(j.company_id)) +
              " · " + dual("مدين", "Debit") + " " + dec(j.total_debit) + " · " + dual("دائن", "Credit") + " " + dec(j.total_credit) + "</div></div>" +
              statusBadgeFromMap(j.status, { draft: ["مسودة", "Draft", "warn"], posted: ["مُرحّل", "Posted", "ok"], reversed: ["معكوس", "Reversed", "miss"] }) +
              "</div>" + (controls ? '<div class="av-user-controls" data-stop="1">' + controls + "</div>" : "") + "</div>";
          }).join("") + "</div>"
        : noticeHtml("لا توجد قيود.", "No journals.");
      host.innerHTML = panel("القيود (D01: غير قابلة للتعديل بعد الترحيل — التصحيح بالعكس)", "Journals (D01: immutable once posted — correction by reversal)", create + list);
      if (create) {
        addJournalLine();
        host.querySelector('[data-act="jn-add-line"]').addEventListener("click", addJournalLine);
      }
    }).catch(function (err) { handleLoadError(err); host.innerHTML = errorHtml(errText(err)); });
  }

  var _jnLineSeq = 0;
  function addJournalLine() {
    var host = byId("jnLines");
    if (!host) return;
    var i = _jnLineSeq++;
    var div = document.createElement("div");
    div.className = "av-form av-form-inline";
    div.innerHTML =
      field("معرّف الحساب", "Account id", numInput("jnAcct" + i, "")) +
      field("مدين", "Debit", numInput("jnDebit" + i, "0")) +
      field("دائن", "Credit", numInput("jnCredit" + i, "0")) +
      field("الوصف", "Description", textInput("jnLineDesc" + i, ""));
    host.appendChild(div);
  }

  function collectJournalLines() {
    var lines = [];
    document.querySelectorAll("#jnLines [id^='jnAcct']").forEach(function (el) {
      var idx = el.id.replace("jnAcct", "");
      lines.push({
        account_id: parseInt(valOf("jnAcct" + idx), 10),
        debit: numVal("jnDebit" + idx) || 0,
        credit: numVal("jnCredit" + idx) || 0,
        description: valOf("jnLineDesc" + idx) || null,
      });
    });
    return lines;
  }

  function renderLedgerActivity() {
    // S26 Table 53: viewing revenue/expense shows the *source* lines and adds no
    // record. Read-only; the rows point back at the journal that produced them.
    var host = byId("acctContent");
    return Promise.all([ensureCompanies(), Promise.resolve()]).then(function () {
      if (!STATE.companies.length) { host.innerHTML = noticeHtml("لا توجد شركات.", "No companies."); return; }
      var cid = STATE.acctLedgerCompany || STATE.companies[0].id;
      STATE.acctLedgerCompany = cid;
      var type = STATE.acctLedgerType || "";
      var q = "?company_id=" + cid +
        (type ? "&account_type=" + type : "") +
        (STATE.acctLedgerYear ? "&fiscal_year=" + STATE.acctLedgerYear : "") +
        (STATE.acctLedgerMonth ? "&fiscal_month=" + STATE.acctLedgerMonth : "");
      return get("/api/v1/accounting/ledger-activity" + q).then(function (data) {
        var picker = '<div class="av-form av-form-inline">' +
          field("الشركة", "Company", selectInput("laCompany", companySelectOptions(false), cid)) +
          field("النوع", "Type", selectInput("laType", [
            { value: "", label: opt("الإيرادات والمصروفات", "Revenue & expenses") },
            { value: "revenue", label: opt("الإيرادات فقط", "Revenue only") },
            { value: "expense", label: opt("المصروفات فقط", "Expenses only") },
          ], type)) +
          field("السنة", "Year", numInput("laYear", STATE.acctLedgerYear || "")) +
          field("الشهر", "Month", numInput("laMonth", STATE.acctLedgerMonth || "")) +
          "</div>";
        var lines = (data && data.lines) || [];
        var table = lines.length
          ? '<div class="av-list">' + lines.map(function (r) {
              var name = STATE.lang === "ar" ? r.name_ar : (r.name_en || r.name_ar);
              var kind = r.account_type === "revenue" ? dual("إيراد", "Revenue") : dual("مصروف", "Expense");
              var meta = [kind, r.journal_number, r.entry_date, r.description]
                .filter(function (v) { return v; }).join(" · ");
              return '<div class="av-row" style="cursor:default"><div class="grow"><div class="t">' +
                escapeHtml(r.code + " · " + name) + "</div>" +
                '<div class="s">' + escapeHtml(meta) + "</div></div>" +
                '<div class="t">' + dec(r.amount) + " " + escapeHtml(r.currency || "") + "</div></div>";
            }).join("") + "</div>"
          : noticeHtml("لا توجد سطور مصدر.", "No source lines.");
        var totals = (data && data.totals || []).length
          ? '<p class="note-block">' + data.totals.map(function (t) {
              var label = t.account_type === "revenue" ? dual("إجمالي الإيرادات", "Total revenue") : dual("إجمالي المصروفات", "Total expenses");
              return escapeHtml(label) + " " + dec(t.amount) + " " + escapeHtml(t.currency);
            }).join(" · ") + "</p>"
          : "";
        host.innerHTML = panel(
          "عرض الإيرادات والمصروفات (سطور المصدر، دون تسجيل إضافي)",
          "Revenue & expenses view (source lines, no extra posting)",
          picker + totals + table
        );
        var sel = byId("laCompany");
        if (sel) sel.addEventListener("change", function () {
          STATE.acctLedgerCompany = parseInt(valOf("laCompany"), 10);
          renderLedgerActivity();
        });
        var tSel = byId("laType");
        if (tSel) tSel.addEventListener("change", function () {
          STATE.acctLedgerType = valOf("laType");
          renderLedgerActivity();
        });
        var yEl = byId("laYear");
        if (yEl) yEl.addEventListener("change", function () {
          STATE.acctLedgerYear = valOf("laYear") ? parseInt(valOf("laYear"), 10) : null;
          renderLedgerActivity();
        });
        var mEl = byId("laMonth");
        if (mEl) mEl.addEventListener("change", function () {
          STATE.acctLedgerMonth = valOf("laMonth") ? parseInt(valOf("laMonth"), 10) : null;
          renderLedgerActivity();
        });
      });
    }).catch(function (err) { handleLoadError(err); host.innerHTML = errorHtml(errText(err)); });
  }

  function renderTrialBalance() {
    var host = byId("acctContent");
    return Promise.all([ensureCompanies(), Promise.resolve()]).then(function () {
      if (!STATE.companies.length) { host.innerHTML = noticeHtml("لا توجد شركات.", "No companies."); return; }
      var cid = STATE.acctTrialCompany || STATE.companies[0].id;
      STATE.acctTrialCompany = cid;
      return get("/api/v1/accounting/trial-balance?company_id=" + cid).then(function (tb) {
        var picker = '<div class="av-form av-form-inline">' +
          field("الشركة", "Company", selectInput("tbCompany",
            companySelectOptions(false), cid)) + "</div>";
        var rows = (tb && tb.rows) || [];
        var table = rows.length
          ? '<div class="av-list">' + rows.map(function (r) {
              var name = STATE.lang === "ar" ? r.name_ar : (r.name_en || r.name_ar);
              return '<div class="av-row" style="cursor:default"><div class="grow"><div class="t">' +
                escapeHtml(r.code + " · " + name) + "</div>" +
                '<div class="s">' + escapeHtml(r.account_type) + " · " + dual("مدين", "Debit") + " " +
                dec(r.debit) + " · " + dual("دائن", "Credit") + " " + dec(r.credit) + "</div></div>" +
                '<div class="t">' + dec(r.balance) + " " + escapeHtml(r.currency || "") + "</div></div>";
            }).join("") + "</div>"
          : noticeHtml("لا توجد قيود مُرحّلة.", "No posted entries.");
        var totals = rows.length
          ? '<p class="note-block">' + dual("إجمالي مدين", "Total debit") + " " + dec(tb.total_debit) +
            " · " + dual("إجمالي دائن", "Total credit") + " " + dec(tb.total_credit) +
            " · " + (tb.balanced ? dual("متوازن", "Balanced") : dual("غير متوازن", "Not balanced")) + "</p>"
          : "";
        host.innerHTML = panel("ميزان المراجعة (القيود المُرحّلة فقط)", "Trial balance (posted journals only)", picker + totals + table);
        var sel = byId("tbCompany");
        if (sel) sel.addEventListener("change", function () {
          STATE.acctTrialCompany = parseInt(valOf("tbCompany"), 10);
          renderTrialBalance();
        });
      });
    }).catch(function (err) { handleLoadError(err); host.innerHTML = errorHtml(errText(err)); });
  }

  function statementSection(titleAr, titleEn, rows, totals) {
    var body = (rows || []).length
      ? '<div class="av-list">' + rows.map(function (r) {
          var name = STATE.lang === "ar" ? r.name_ar : (r.name_en || r.name_ar);
          return '<div class="av-row" style="cursor:default"><div class="grow"><div class="t">' +
            escapeHtml(r.code + " · " + name) + "</div></div>" +
            '<div class="t">' + dec(r.amount) + " " + escapeHtml(r.currency || "") + "</div></div>";
        }).join("") + "</div>"
      : noticeHtml("لا توجد مبالغ.", "No amounts.");
    var footer = (totals || []).length
      ? '<p class="note-block">' + totals.map(function (t) {
          return escapeHtml(t.label) + " " + dec(t.amount) + " " + escapeHtml(t.currency);
        }).join(" · ") + "</p>"
      : "";
    return panel(titleAr, titleEn, body + footer);
  }

  function statementPeriodLabel(fy, fm) {
    return (fy || "—") + (fm ? " / " + fm : "");
  }

  function renderStatements() {
    var host = byId("acctContent");
    return Promise.all([ensureCompanies(), Promise.resolve()]).then(function () {
      if (!STATE.companies.length) { host.innerHTML = noticeHtml("لا توجد شركات.", "No companies."); return; }
      var cid = STATE.acctStmtCompany || STATE.companies[0].id;
      STATE.acctStmtCompany = cid;
      var compare = !!STATE.acctStmtCompare;
      var q = "?company_id=" + cid +
        (STATE.acctStmtYear ? "&fiscal_year=" + STATE.acctStmtYear : "") +
        (STATE.acctStmtMonth ? "&fiscal_month=" + STATE.acctStmtMonth : "") +
        (compare ? "&compare_previous=true" : "");
      return get("/api/v1/accounting/financial-statements" + q).then(function (fs) {
        var picker = '<div class="av-form av-form-inline">' +
          field("الشركة", "Company", selectInput("fsCompany", companySelectOptions(false), cid)) +
          field("السنة", "Year", numInput("fsYear", STATE.acctStmtYear || "")) +
          field("الشهر", "Month", numInput("fsMonth", STATE.acctStmtMonth || "")) +
          field("المقارنة", "Compare", selectInput("fsCompare",
            [{ value: "", label: opt("بدون", "None") }, { value: "1", label: opt("الفترة السابقة", "Previous period") }],
            compare ? "1" : "")) +
          "</div>";
        var is = fs.income_statement || {};
        var bs = fs.balance_sheet || {};
        var netTotals = (is.net || []).map(function (n) {
          return { label: dual("صافي", "Net") + " (" + statementPeriodLabel(fs.fiscal_year, fs.fiscal_month) + ")",
                   amount: n.amount, currency: n.currency };
        });
        var revTotals = (is.total_revenue || []).map(function (n) {
          return { label: dual("إجمالي الإيرادات", "Total revenue"), amount: n.amount, currency: n.currency };
        }).concat((is.total_expenses || []).map(function (n) {
          return { label: dual("إجمالي المصروفات", "Total expenses"), amount: n.amount, currency: n.currency };
        })).concat(netTotals);
        var bsTotals = (bs.total_assets || []).map(function (n) {
          return { label: dual("إجمالي الأصول", "Total assets"), amount: n.amount, currency: n.currency };
        }).concat((bs.total_liabilities || []).map(function (n) {
          return { label: dual("إجمالي الالتزامات", "Total liabilities"), amount: n.amount, currency: n.currency };
        })).concat((bs.total_equity || []).map(function (n) {
          return { label: dual("حقوق الملكية", "Equity"), amount: n.amount, currency: n.currency };
        })).concat((bs.balanced || []).map(function (b) {
          return { label: b.currency, amount: b.balanced ? dual("متوازن", "Balanced") : dual("غير متوازن", "Not balanced"), currency: "" };
        }));
        var prev = "";
        if (fs.previous) {
          var pis = fs.previous.income_statement || {};
          var prevNet = (pis.net || []).map(function (n) {
            return { label: dual("صافي", "Net") + " (" + statementPeriodLabel(fs.previous.fiscal_year, fs.previous.fiscal_month) + ")",
                     amount: n.amount, currency: n.currency };
          });
          prev = statementSection("الفترة السابقة — قائمة الدخل", "Previous period — income statement",
            pis.revenue || [], prevNet);
        }
        host.innerHTML = panel(
          "القوائم المالية (القيود المُرحّلة فقط؛ الأرقام بعملاتها دون جمع)",
          "Financial statements (posted journals only; amounts kept per currency)",
          picker +
          statementSection("قائمة الدخل", "Income statement", (is.revenue || []).concat(is.expenses || []), revTotals) +
          statementSection("الميزانية العمومية", "Balance sheet", (bs.assets || []).concat(bs.liabilities || []).concat(bs.equity || []), bsTotals) +
          prev
        );
        var sel = byId("fsCompany");
        if (sel) sel.addEventListener("change", function () {
          STATE.acctStmtCompany = parseInt(valOf("fsCompany"), 10);
          renderStatements();
        });
        var yEl = byId("fsYear");
        if (yEl) yEl.addEventListener("change", function () {
          STATE.acctStmtYear = valOf("fsYear") ? parseInt(valOf("fsYear"), 10) : null;
          renderStatements();
        });
        var mEl = byId("fsMonth");
        if (mEl) mEl.addEventListener("change", function () {
          STATE.acctStmtMonth = valOf("fsMonth") ? parseInt(valOf("fsMonth"), 10) : null;
          renderStatements();
        });
        var cEl = byId("fsCompare");
        if (cEl) cEl.addEventListener("change", function () {
          STATE.acctStmtCompare = valOf("fsCompare") === "1";
          renderStatements();
        });
      });
    }).catch(function (err) { handleLoadError(err); host.innerHTML = errorHtml(errText(err)); });
  }

  function renderInvoices() {
    var host = byId("acctContent");
    return Promise.all([
      ensureCompanies(),
      get("/api/v1/accounting/invoices").catch(function () { return []; }),
      get("/api/v1/accounting/receivables").catch(function () { return null; }),
    ]).then(function (res) {
      var rows = res[1] || [];
      var summary = res[2];
      var canManage = has("invoice.manage");
      var create = canManage
        ? '<form class="av-form" id="invoiceForm">' +
          '<div class="av-form-inline">' +
          field("الشركة", "Company", selectInput("ivCompany", companySelectOptions(false), STATE.companies.length ? STATE.companies[0].id : "")) +
          field("النوع", "Direction", selectInput("ivDirection", [{ value: "issued", label: opt("صادرة (مستحق لنا)", "Issued (receivable)") }, { value: "received", label: opt("واردة (مستحق علينا)", "Received (payable)") }], "issued")) +
          field("الرقم", "Number", textInput("ivNumber", "")) +
          field("الطرف", "Party", textInput("ivParty", "")) +
          field("تاريخ الإصدار", "Issue date", dateInput("ivIssue", "")) +
          field("الاستحقاق", "Due date", dateInput("ivDue", "")) +
          field("نسبة الضريبة", "Tax rate", numInput("ivTax", "0")) +
          "</div>" +
          '<div class="av-form-inline">' +
          field("وصف البند", "Line description", textInput("ivLineDesc", "")) +
          field("الكمية", "Quantity", numInput("ivQty", "1")) +
          field("سعر الوحدة", "Unit price", numInput("ivPrice", "0")) +
          "</div>" +
          '<div class="av-form-actions"><button class="btn-solid" type="submit">' +
          dual("إنشاء فاتورة", "Create invoice") + "</button></div></form>"
        : "";
      var totals = summary
        ? '<div class="av-grid cols-2">' +
          moneyBlock("مستحق لنا (فواتير صادرة)", "Receivable (issued)", summary.receivables) +
          moneyBlock("مستحق علينا (فواتير واردة)", "Payable (received)", summary.payables) +
          "</div>"
        : "";
      var list = rows.length
        ? '<div class="av-list">' + rows.map(function (iv) {
            var settle = iv.status !== "settled" && has("settlement.manage")
              ? '<div class="av-user-controls" data-stop="1">' +
                numInput("stAmt" + iv.id, "") +
                '<button class="btn-outline" data-act="iv-settle" data-id="' + iv.id + '">' + dual("تسجيل تسوية", "Record settlement") + "</button></div>"
              : "";
            return '<div class="av-row" style="flex-direction:column;align-items:stretch;cursor:default"><div style="display:flex;align-items:center;gap:11px">' +
              '<div class="grow"><div class="t">' + escapeHtml(iv.number + " · " + iv.party_name) + "</div>" +
              '<div class="s">' + escapeHtml(companyNameById(iv.company_id)) + " · " +
              dual("الإجمالي", "Total") + " " + dec(iv.total) + " · " + dual("المسدد", "Settled") + " " + dec(iv.settled_amount) + " · " + dual("المتبقي", "Outstanding") + " " + dec(iv.outstanding) + "</div></div>" +
              dirBadge(iv.direction) +
              statusBadgeFromMap(iv.status, { draft: ["مسودة", "Draft", "warn"], issued: ["صادرة", "Issued", "warn"], partially_settled: ["مسددة جزئيًا", "Partially settled", "warn"], settled: ["مسددة", "Settled", "ok"], cancelled: ["ملغاة", "Cancelled", "miss"] }) +
              "</div>" + settle + "</div>";
          }).join("") + "</div>"
        : noticeHtml("لا توجد فواتير.", "No invoices.");
      host.innerHTML = panel("الفواتير والمستحقات (D01/D09: لا يوجد إجراء تحويل بنكي)", "Invoices & receivables (D01/D09: no bank-transfer action)", totals + create + list);
    }).catch(function (err) { handleLoadError(err); host.innerHTML = errorHtml(errText(err)); });
  }

  function moneyBlock(ar, en, rows) {
    var body = (rows || []).length
      ? '<div class="av-list">' + rows.map(function (r) {
          return '<div class="av-row" style="cursor:default"><div class="grow"><div class="t">' +
            dec(r.amount) + " " + escapeHtml(r.currency) + "</div></div></div>";
        }).join("") + "</div>"
      : noticeHtml("لا مبالغ مستحقة.", "Nothing outstanding.");
    return '<div class="av-card">' + panel(ar, en, body) + "</div>";
  }

  function dirBadge(direction) {
    var issued = direction !== "received";
    return '<span class="badge ' + (issued ? "ok" : "warn") + '">' +
      (issued ? dual("مستحق لنا", "Receivable") : dual("مستحق علينا", "Payable")) + "</span>";
  }

  function renderParties() {
    var host = byId("acctContent");
    return Promise.all([ensureCompanies(), get("/api/v1/accounting/parties").catch(function () { return []; })]).then(function (res) {
      var rows = res[1] || [];
      var canManage = has("party.manage");
      var create = canManage
        ? '<form class="av-form av-form-inline" id="partyForm">' +
          field("الشركة", "Company", selectInput("ptCompany", companySelectOptions(false), STATE.companies.length ? STATE.companies[0].id : "")) +
          field("الاسم", "Name", textInput("ptName", "")) +
          field("النوع", "Type", selectInput("ptType", [{ value: "customer", label: opt("عميل", "Customer") }, { value: "supplier", label: opt("مورد", "Supplier") }], "customer")) +
          field("العملة", "Currency", textInput("ptCurrency", "SAR")) +
          field("التواصل", "Contact", textInput("ptContact", "")) +
          '<div class="av-form-actions"><button class="btn-solid" type="submit">' +
          dual("إضافة طرف", "Add party") + "</button></div></form>"
        : "";
      var list = rows.length
        ? '<div class="av-list">' + rows.map(function (p) {
            return '<div class="av-row" style="cursor:default"><div class="grow"><div class="t">' +
              escapeHtml(p.name) + "</div>" +
              '<div class="s">' + escapeHtml(companyNameById(p.company_id)) + " · " +
              escapeHtml(p.party_type === "supplier" ? opt("مورد", "Supplier") : opt("عميل", "Customer")) +
              " · " + escapeHtml(p.currency) + (p.contact ? " · " + escapeHtml(p.contact) : "") + "</div></div></div>";
          }).join("") + "</div>"
        : noticeHtml("لا يوجد عملاء أو موردون.", "No customers or suppliers.");
      host.innerHTML = panel("العملاء والموردون (S27: دليل واحد للفواتير الصادرة والواردة)", "Customers & suppliers (S27: one directory for issued and received invoices)", create + list);
    }).catch(function (err) { handleLoadError(err); host.innerHTML = errorHtml(errText(err)); });
  }

  function renderInterbalances() {
    var host = byId("acctContent");
    return Promise.all([ensureCompanies(), get("/api/v1/accounting/interbalances").catch(function () { return []; })]).then(function (res) {
      var rows = res[1] || [];
      var canManage = has("interbalance.manage");
      var create = canManage
        ? '<form class="av-form av-form-inline" id="interbalanceForm">' +
          field("الشركة", "Company", selectInput("ibCompany", companySelectOptions(false), STATE.companies.length ? STATE.companies[0].id : "")) +
          field("الشركة المقابلة", "Counterparty", selectInput("ibCounterparty", [{ value: "", label: opt("بدون", "None") }].concat(companySelectOptions(false)), "")) +
          field("العملة", "Currency", textInput("ibCurrency", "SAR")) +
          field("المبلغ", "Amount", numInput("ibAmount", "")) +
          field("السبب", "Reason", textInput("ibReason", "")) +
          '<div class="av-form-actions"><button class="btn-solid" type="submit">' +
          dual("تسجيل رصيد", "Record balance") + "</button></div></form>"
        : "";
      var list = rows.length
        ? '<div class="av-list">' + rows.map(function (b) {
            var other = b.counterparty_company_id ? companyNameById(b.counterparty_company_id) : (b.counterparty_name || "—");
            return '<div class="av-row" style="cursor:default"><div class="grow"><div class="t">' +
              escapeHtml(companyNameById(b.company_id) + " ↔ " + other) + "</div>" +
              '<div class="s">' + dec(b.amount) + " " + escapeHtml(b.currency) +
              (b.reason ? " · " + escapeHtml(b.reason) : "") + "</div></div></div>";
          }).join("") + "</div>"
        : noticeHtml("لا توجد أرصدة بين الشركات.", "No inter-company balances.");
      host.innerHTML = panel("أرصدة الشركات (S27: رصيد بعملته وسببه، وليس إيرادًا ولا رسوم خدمة)", "Inter-company balances (S27: a balance with its currency and reason — not revenue, not a service fee)", create + list);
    }).catch(function (err) { handleLoadError(err); host.innerHTML = errorHtml(errText(err)); });
  }

  function renderAssets() {
    var host = byId("acctContent");
    return Promise.all([ensureCompanies(), get("/api/v1/accounting/assets").catch(function () { return []; })]).then(function (res) {
      var rows = res[1] || [];
      var canManage = has("asset.manage");
      var create = canManage
        ? '<form class="av-form av-form-inline" id="assetForm">' +
          field("الشركة", "Company", selectInput("atCompany", companySelectOptions(false), STATE.companies.length ? STATE.companies[0].id : "")) +
          field("الاسم", "Name", textInput("atName", "")) +
          field("التكلفة", "Cost", numInput("atCost", "")) +
          field("الفئة", "Category", textInput("atCategory", "")) +
          field("تاريخ الاقتناء", "Acquisition date", dateInput("atDate", "")) +
          '<div class="av-form-actions"><button class="btn-solid" type="submit">' +
          dual("إضافة أصل", "Add asset") + "</button></div></form>"
        : "";
      var list = rows.length
        ? '<div class="av-list">' + rows.map(function (a) {
            return '<div class="av-row" style="cursor:default"><div class="grow"><div class="t">' +
              escapeHtml(a.name) + "</div>" +
              '<div class="s">' + escapeHtml(companyNameById(a.company_id)) + " · " +
              dual("التكلفة", "Cost") + " " + dec(a.cost) + " · " + escapeHtml(a.category || "") + "</div></div></div>";
          }).join("") + "</div>"
        : noticeHtml("لا توجد أصول.", "No assets.");
      host.innerHTML = panel("الأصول (D01)", "Assets (D01)", create + list);
    }).catch(function (err) { handleLoadError(err); host.innerHTML = errorHtml(errText(err)); });
  }

  function renderBudgets() {
    var host = byId("acctContent");
    return Promise.all([ensureCompanies(), get("/api/v1/accounting/budgets").catch(function () { return []; })]).then(function (res) {
      var rows = res[1] || [];
      var canManage = has("budget.manage");
      var create = canManage
        ? '<form class="av-form av-form-inline" id="budgetForm">' +
          field("الشركة", "Company", selectInput("bgCompany", companySelectOptions(false), STATE.companies.length ? STATE.companies[0].id : "")) +
          field("السنة المالية", "Fiscal year", numInput("bgYear", STATE.year || "")) +
          field("الإجمالي", "Total", numInput("bgTotal", "")) +
          field("المصدر", "Source", textInput("bgSource", "")) +
          '<div class="av-form-actions"><button class="btn-solid" type="submit">' +
          dual("إنشاء موازنة", "Create budget") + "</button></div></form>"
        : "";
      var list = rows.length
        ? '<div class="av-list">' + rows.map(function (b) {
            var approve = b.status !== "approved" && has("budget.approve")
              ? actBtn("budget.approve", "bg-approve", b.id, "اعتماد", "Approve")
              : "";
            return '<div class="av-row" style="flex-direction:column;align-items:stretch;cursor:default"><div style="display:flex;align-items:center;gap:11px">' +
              '<div class="grow"><div class="t">' + escapeHtml(companyNameById(b.company_id)) + " · " + dec(b.fiscal_year) +
              " · v" + dec(b.version) + "</div>" +
              '<div class="s">' + dual("الإجمالي", "Total") + " " + dec(b.total_amount) +
              " · " + dual("المصدر", "Source") + " " + escapeHtml(b.source || "—") + "</div></div>" +
              statusBadgeFromMap(b.status, { draft: ["مسودة", "Draft", "warn"], approved: ["معتمدة", "Approved", "ok"], superseded: ["مستبدلة", "Superseded", "rev"] }) +
              "</div>" + (approve ? '<div class="av-user-controls" data-stop="1">' + approve + "</div>" : "") + "</div>";
          }).join("") + "</div>"
        : noticeHtml("لا توجد موازنات.", "No budgets.");
      host.innerHTML = panel("الموازنات (D07: المصدر والإصدار محفوظان، والاعتماد لا يستبدل القيم)", "Budgets (D07: source + version preserved; approval does not overwrite)", create + list);
    }).catch(function (err) { handleLoadError(err); host.innerHTML = errorHtml(errText(err)); });
  }

  function renderKpis() {
    var host = byId("acctContent");
    return Promise.all([ensureCompanies(), get("/api/v1/accounting/kpis").catch(function () { return []; })]).then(function (res) {
      var rows = res[1] || [];
      var canManage = has("kpi.manage");
      var create = canManage
        ? '<form class="av-form av-form-inline" id="kpiForm">' +
          field("الكود", "Code", textInput("kpCode", "")) +
          field("الاسم (عربي)", "Name (AR)", textInput("kpNameAr", "")) +
          field("الاسم (إنجليزي)", "Name (EN)", textInput("kpNameEn", "")) +
          field("مصدر البيانات", "Data source", textInput("kpSource", "")) +
          field("طريقة الحساب", "Calculation method", textInput("kpMethod", "")) +
          field("الفترة", "Period", textInput("kpPeriod", "")) +
          field("المستهدف", "Target", numInput("kpTarget", "")) +
          '<div class="av-form-actions"><button class="btn-solid" type="submit">' +
          dual("إضافة مؤشر", "Add KPI") + "</button></div></form>"
        : "";
      var list = rows.length
        ? '<div class="av-list">' + rows.map(function (k) {
            return '<div class="av-row" style="cursor:default"><div class="grow"><div class="t">' +
              escapeHtml(k.code + " · " + (STATE.lang === "ar" ? k.name_ar : k.name_en || k.name_ar)) + "</div>" +
              '<div class="s">' + dual("المصدر", "Source") + " " + escapeHtml(k.data_source) +
              " · " + dual("الطريقة", "Method") + " " + escapeHtml(k.calculation_method) +
              " · " + escapeHtml(k.period_label) + "</div></div>" +
              (k.target_value != null ? '<span class="status rev"><i></i>' + dual("المستهدف", "Target") + " " + dec(k.target_value) + "</span>" : "") +
              "</div>";
          }).join("") + "</div>"
        : noticeHtml("لا توجد مؤشرات.", "No KPIs.");
      host.innerHTML = panel("مؤشرات الأداء (D02: مصدر + طريقة + فترة)", "KPIs (D02: source + method + period)", create + list);
    }).catch(function (err) { handleLoadError(err); host.innerHTML = errorHtml(errText(err)); });
  }

  var POLICY_KINDS = ["tax", "fiscal_year", "invoice", "asset", "currency"];
  function policyKindLabel(k) {
    var map = {
      tax: ["الضريبة", "Tax"],
      fiscal_year: ["السنة المالية", "Fiscal year"],
      invoice: ["الفاتورة", "Invoice"],
      asset: ["الأصول", "Asset"],
      currency: ["العملة", "Currency"],
    };
    return dual.apply(null, map[k] || [k, k]);
  }
  function renderPolicies() {
    var host = byId("acctContent");
    return Promise.all([
      ensureCompanies(),
      get("/api/v1/accounting/policies").catch(function () { return []; }),
    ]).then(function (res) {
      var rows = res[1] || [];
      var canManage = has("accounting_policy.manage");
      var canApprove = has("accounting_policy.approve");
      var kindOptions = POLICY_KINDS.map(function (k) {
        return { value: k, label: policyKindLabel(k) };
      });
      var create = canManage
        ? '<form class="av-form av-form-inline" id="policyForm">' +
          field("النوع", "Kind", selectInput("polKind", kindOptions, "tax")) +
          field("الشركة", "Company", selectInput("polCompany", [{ value: "", label: dual("القابضة (افتراضي)", "Holding (default)") }].concat(companySelectOptions(true)), "")) +
          field("القيمة", "Value", numInput("polValue", "")) +
          field("قيمة نصية", "Text value", textInput("polText", "")) +
          field("الوصف", "Description", textInput("polDesc", "")) +
          '<div class="av-form-actions"><button class="btn-solid" type="submit">' +
          dual("حفظ مسودة", "Save draft") + "</button></div></form>"
        : "";
      var list = rows.length
        ? '<div class="av-list">' + rows.map(function (p) {
            var approved = p.status === "approved";
            var badge = approved
              ? '<span class="status ok"><i></i>' + dual("معتمدة", "Approved") + "</span>"
              : '<span class="status warn"><i></i>' + dual("مسودة", "Draft") + "</span>";
            var approveBtn = (!approved && canApprove)
              ? '<button class="btn-ghost" data-act="policy-approve" data-id="' + p.id + '">' + dual("اعتماد", "Approve") + "</button>"
              : "";
            return '<div class="av-row" style="cursor:default"><div class="grow"><div class="t">' +
              escapeHtml(policyKindLabel(p.kind)) + " · " + dual("نسخة", "v") + " " + p.version +
              (p.company_id ? " · " + dual("شركة #", "company #") + p.company_id : " · " + dual("افتراضي القابضة", "holding default")) +
              "</div>" +
              '<div class="s">' + escapeHtml(p.value != null ? String(p.value) : (p.value_text || "")) +
              (p.description ? " · " + escapeHtml(p.description) : "") + "</div></div>" +
              badge + approveBtn + "</div>";
          }).join("") + "</div>"
        : noticeHtml("لا توجد سياسات محاسبية معتمدة بعد.", "No accounting policies yet.");
      host.innerHTML = panel(
        "السياسات المحاسبية (D01: مسودة لا تسري، والاعتماد هو ما يسري)",
        "Accounting policies (D01: a draft is inert; approval makes it effective)",
        create + list
      );
    }).catch(function (err) { handleLoadError(err); host.innerHTML = errorHtml(errText(err)); });
  }

  function onAcctAct(action, id, el) {
    if (action === "jn-add-line") return addJournalLine();
    if (action === "policy-approve") {
      busy(el, true);
      return post("/api/v1/accounting/policies/" + id + "/approve", {})
        .then(function () { toast(dual("تم اعتماد السياسة.", "Policy approved."), "ok"); return renderPolicies(); })
        .catch(function (err) { domainError(err); busy(el, false); });
    }
    if (action === "ob-submit") {
      busy(el, true);
      return post("/api/v1/accounting/opening-balances/" + id + "/submit", {})
        .then(function () { toast(dual("تم إرسال الرصيد.", "Balance submitted."), "ok"); return renderOpeningBalances(); })
        .catch(function (err) { domainError(err); busy(el, false); });
    }
    if (action === "ob-approve") {
      busy(el, true);
      return post("/api/v1/accounting/opening-balances/" + id + "/approve", {})
        .then(function () { toast(dual("تم اعتماد الرصيد.", "Balance approved."), "ok"); return renderOpeningBalances(); })
        .catch(function (err) { domainError(err); busy(el, false); });
    }
    if (action === "jn-post") {
      busy(el, true);
      return post("/api/v1/accounting/journals/" + id + "/post", {})
        .then(function () { toast(dual("تم ترحيل القيد.", "Journal posted."), "ok"); return renderJournals(); })
        .catch(function (err) { domainError(err); busy(el, false); });
    }
    if (action === "jn-reverse") {
      return confirmDialog({
        title: dual("عكس القيد", "Reverse journal"),
        message: dual("لا يمكن تعديل قيد مُرحّل؛ سيُنشأ قيد عكسي. متابعة؟", "A posted journal cannot be edited; a reversal entry will be created. Continue?"),
      }).then(function (ok) {
        if (!ok) return;
        busy(el, true);
        return post("/api/v1/accounting/journals/" + id + "/reverse", {})
          .then(function () { toast(dual("تم إنشاء القيد العكسي.", "Reversal created."), "ok"); return renderJournals(); })
          .catch(function (err) { domainError(err); busy(el, false); });
      });
    }
    if (action === "iv-settle") {
      busy(el, true);
      return post("/api/v1/accounting/invoices/" + id + "/settlements", { amount: numVal("stAmt" + id) })
        .then(function () { toast(dual("تم تسجيل التسوية.", "Settlement recorded."), "ok"); return renderInvoices(); })
        .catch(function (err) { domainError(err); busy(el, false); });
    }
    if (action === "bg-approve") {
      busy(el, true);
      return post("/api/v1/accounting/budgets/" + id + "/approve", {})
        .then(function () { toast(dual("تم اعتماد الموازنة.", "Budget approved."), "ok"); return renderBudgets(); })
        .catch(function (err) { domainError(err); busy(el, false); });
    }
    if (action === "conf-grant-create") return createConfGrant(el);
    if (action === "conf-grant-revoke") {
      return del("/api/v1/confidential-access/grants/" + id)
        .then(function () { toast(dual("تم إلغاء التفويض.", "Grant revoked."), "ok"); return renderConfidentialGrants(); })
        .catch(domainError);
    }
    if (action === "conf-decide") return decideComplaint(el);
    if (action !== "submit") return;
    if (id === "obForm") {
      busy(el.querySelector("button"), true);
      return post("/api/v1/accounting/opening-balances", {
        company_id: parseInt(valOf("obCompany"), 10),
        period_year: parseInt(valOf("obYear"), 10),
        period_month: numVal("obMonth"),
        kind: valOf("obKind"),
        bank: numVal("obBank"),
        cash: numVal("obCash"),
        receivables: numVal("obRecv"),
        debts: numVal("obDebts"),
      }).then(function () { toast(dual("تم تسجيل الرصيد.", "Balance recorded."), "ok"); return renderOpeningBalances(); })
        .catch(function (err) { domainError(err); busy(el.querySelector("button"), false); });
    }
    if (id === "acctForm") {
      busy(el.querySelector("button"), true);
      return post("/api/v1/accounting/accounts", {
        company_id: parseInt(valOf("acCompany"), 10),
        code: valOf("acCode"),
        name_ar: valOf("acNameAr"),
        name_en: valOf("acNameEn") || null,
        account_type: valOf("acType"),
      }).then(function () { toast(dual("تمت إضافة الحساب.", "Account added."), "ok"); return renderAccounts(); })
        .catch(function (err) { domainError(err); busy(el.querySelector("button"), false); });
    }
    if (id === "journalForm") {
      busy(el.querySelector("button"), true);
      return post("/api/v1/accounting/journals", {
        company_id: parseInt(valOf("jnCompany"), 10),
        entry_date: valOf("jnDate"),
        description: valOf("jnDesc") || null,
        lines: collectJournalLines(),
      }).then(function () { toast(dual("تم حفظ القيد.", "Journal saved."), "ok"); return renderJournals(); })
        .catch(function (err) { domainError(err); busy(el.querySelector("button"), false); });
    }
    if (id === "invoiceForm") {
      busy(el.querySelector("button"), true);
      return post("/api/v1/accounting/invoices", {
        company_id: parseInt(valOf("ivCompany"), 10),
        number: valOf("ivNumber"),
        party_name: valOf("ivParty"),
        direction: valOf("ivDirection") || "issued",
        issue_date: valOf("ivIssue") || null,
        due_date: valOf("ivDue") || null,
        tax_rate: numVal("ivTax") || 0,
        lines: [{
          description: valOf("ivLineDesc"),
          quantity: numVal("ivQty") || 1,
          unit_price: numVal("ivPrice") || 0,
        }],
      }).then(function () { toast(dual("تم إنشاء الفاتورة.", "Invoice created."), "ok"); return renderInvoices(); })
        .catch(function (err) { domainError(err); busy(el.querySelector("button"), false); });
    }
    if (id === "partyForm") {
      busy(el.querySelector("button"), true);
      return post("/api/v1/accounting/parties", {
        company_id: parseInt(valOf("ptCompany"), 10),
        name: valOf("ptName"),
        party_type: valOf("ptType") || "customer",
        currency: valOf("ptCurrency") || "SAR",
        contact: valOf("ptContact") || null,
      }).then(function () { toast(dual("تمت إضافة الطرف.", "Party added."), "ok"); return renderParties(); })
        .catch(function (err) { domainError(err); busy(el.querySelector("button"), false); });
    }
    if (id === "interbalanceForm") {
      busy(el.querySelector("button"), true);
      return post("/api/v1/accounting/interbalances", {
        company_id: parseInt(valOf("ibCompany"), 10),
        counterparty_company_id: valOf("ibCounterparty") ? parseInt(valOf("ibCounterparty"), 10) : null,
        currency: valOf("ibCurrency") || "SAR",
        amount: numVal("ibAmount") || 0,
        reason: valOf("ibReason") || null,
      }).then(function () { toast(dual("تم تسجيل الرصيد.", "Balance recorded."), "ok"); return renderInterbalances(); })
        .catch(function (err) { domainError(err); busy(el.querySelector("button"), false); });
    }
    if (id === "assetForm") {
      busy(el.querySelector("button"), true);
      return post("/api/v1/accounting/assets", {
        company_id: parseInt(valOf("atCompany"), 10),
        name: valOf("atName"),
        cost: numVal("atCost") || 0,
        category: valOf("atCategory") || null,
        acquisition_date: valOf("atDate") || null,
      }).then(function () { toast(dual("تمت إضافة الأصل.", "Asset added."), "ok"); return renderAssets(); })
        .catch(function (err) { domainError(err); busy(el.querySelector("button"), false); });
    }
    if (id === "budgetForm") {
      busy(el.querySelector("button"), true);
      return post("/api/v1/accounting/budgets", {
        company_id: parseInt(valOf("bgCompany"), 10),
        fiscal_year: parseInt(valOf("bgYear"), 10),
        total_amount: numVal("bgTotal") || 0,
        source: valOf("bgSource") || null,
      }).then(function () { toast(dual("تم إنشاء الموازنة.", "Budget created."), "ok"); return renderBudgets(); })
        .catch(function (err) { domainError(err); busy(el.querySelector("button"), false); });
    }
    if (id === "kpiForm") {
      busy(el.querySelector("button"), true);
      return post("/api/v1/accounting/kpis", {
        code: valOf("kpCode"),
        name_ar: valOf("kpNameAr"),
        name_en: valOf("kpNameEn") || null,
        data_source: valOf("kpSource"),
        calculation_method: valOf("kpMethod"),
        period_label: valOf("kpPeriod"),
        target_value: numVal("kpTarget"),
      }).then(function () { toast(dual("تمت إضافة المؤشر.", "KPI added."), "ok"); return renderKpis(); })
        .catch(function (err) { domainError(err); busy(el.querySelector("button"), false); });
    }
    if (id === "policyForm") {
      busy(el.querySelector("button"), true);
      return post("/api/v1/accounting/policies", {
        kind: valOf("polKind"),
        company_id: valOf("polCompany") ? parseInt(valOf("polCompany"), 10) : null,
        value: numVal("polValue"),
        value_text: valOf("polText") || null,
        description: valOf("polDesc") || null,
      }).then(function () { toast(dual("تم حفظ المسودة.", "Draft saved."), "ok"); return renderPolicies(); })
        .catch(function (err) { domainError(err); busy(el.querySelector("button"), false); });
    }
    if (id === "complaintForm") {
      busy(el.querySelector("button"), true);
      return post("/api/v1/operations/complaints", {
        subject: valOf("coSubject"),
        body: valOf("coBody"),
        company_id: valOf("coCompany") ? parseInt(valOf("coCompany"), 10) : null,
        is_anonymous: valOf("coAnon") === "1",
      }).then(function () { toast(dual("تم رفع الشكوى.", "Complaint submitted."), "ok"); return renderComplaints(); })
        .catch(function (err) { domainError(err); busy(el.querySelector("button"), false); });
    }
  }

  // ======================================================================
  // S15 -- Complaints & confidential access (D04)
  // ======================================================================
  function renderConfidentialView() {
    var host = byId("confContent");
    if (!host) return Promise.resolve();
    if (!STATE.confBound) {
      STATE.confBound = true;
      bindConfTabs();
      bindHost(host, onAcctAct);
    }
    if (!STATE.confTab || !canConfTab(STATE.confTab)) STATE.confTab = firstConfTab();
    return renderConfTab(STATE.confTab);
  }

  var CONF_TABS = ["complaints", "grants"];
  var CONF_TAB_PERM = {
    complaints: ["complaint.read_own", "complaint.decide", "complaint.create"],
    grants: ["confidential_access.manage"],
  };
  function canConfTab(t) { return (CONF_TAB_PERM[t] || []).some(has); }
  function firstConfTab() {
    for (var i = 0; i < CONF_TABS.length; i++) if (canConfTab(CONF_TABS[i])) return CONF_TABS[i];
    return "complaints";
  }
  function bindConfTabs() {
    document.querySelectorAll("[data-conf-tab]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var t = btn.getAttribute("data-conf-tab");
        if (!canConfTab(t)) return;
        STATE.confTab = t;
        document.querySelectorAll("[data-conf-tab]").forEach(function (b) { b.classList.toggle("on", b === btn); });
        renderConfTab(t);
      });
    });
  }
  function renderConfTab(tab) {
    var host = byId("confContent");
    document.querySelectorAll("[data-conf-tab]").forEach(function (b) {
      b.classList.toggle("on", b.getAttribute("data-conf-tab") === tab);
    });
    host.innerHTML = loadingHtml();
    if (tab === "complaints") return renderComplaints();
    if (tab === "grants") return renderConfidentialGrants();
    return Promise.resolve();
  }

  function renderComplaints() {
    var host = byId("confContent");
    return Promise.all([ensureCompanies(), get("/api/v1/operations/complaints").catch(function () { return []; })]).then(function (res) {
      var rows = res[1] || [];
      var canCreate = has("complaint.create");
      var create = canCreate
        ? '<form class="av-form av-form-inline" id="complaintForm">' +
          field("الموضوع", "Subject", textInput("coSubject", "")) +
          field("الشركة (اختياري)", "Company (optional)", selectInput("coCompany", companySelectOptions(true), "")) +
          field("مجهولة؟", "Anonymous?", selectInput("coAnon", [{ value: "0", label: opt("لا", "No") }, { value: "1", label: opt("نعم", "Yes") }], "0")) +
          field("النص", "Body", textArea("coBody", "", "")) +
          '<div class="av-form-actions"><button class="btn-solid" type="submit">' +
          dual("رفع شكوى", "Submit complaint") + "</button></div></form>"
        : "";
      var note = '<p class="note-block">' + dual("سرّي: مرئي للمالك فقط افتراضيًا، ولا يظهر في العدّادات أو البحث أو السجل العام.", "Confidential: owner-only by default, and excluded from counters, search and the public log.") + "</p>";
      var list = rows.length
        ? '<div class="av-list">' + rows.map(function (c) {
            var decide = has("complaint.decide")
              ? '<div class="av-user-controls" data-stop="1">' +
                selectInput("coStatus" + c.id, [
                  { value: "under_review", label: opt("قيد المراجعة", "Under review") },
                  { value: "routed", label: opt("محوّلة", "Routed") },
                  { value: "handled", label: opt("معالجة", "Handled") },
                  { value: "postponed", label: opt("مؤجلة", "Postponed") },
                  { value: "closed", label: opt("مغلقة", "Closed") },
                ], c.status) +
                '<button class="btn-outline" data-act="conf-decide" data-id="' + c.id + '">' + dual("قرار", "Decide") + "</button></div>"
              : "";
            return '<div class="av-row" style="flex-direction:column;align-items:stretch;cursor:default"><div style="display:flex;align-items:center;gap:11px">' +
              '<div class="grow"><div class="t">' + escapeHtml(c.subject) + "</div>" +
              '<div class="s">' + (c.company_id ? escapeHtml(companyNameById(c.company_id)) + " · " : "") +
              (c.is_anonymous ? dual("مجهولة", "Anonymous") : "") + "</div></div>" +
              statusBadgeFromMap(c.status, { new: ["جديدة", "New", "warn"], under_review: ["قيد المراجعة", "Under review", "warn"], routed: ["محوّلة", "Routed", "warn"], handled: ["معالجة", "Handled", "ok"], postponed: ["مؤجلة", "Postponed", "rev"], closed: ["مغلقة", "Closed", "ok"] }) +
              "</div>" + decide + "</div>";
          }).join("") + "</div>"
        : noticeHtml("لا توجد شكاوى.", "No complaints.");
      host.innerHTML = panel("الشكاوى (D04: سرّية)", "Complaints (D04: confidential)", note + create + list);
    }).catch(function (err) { handleLoadError(err); host.innerHTML = errorHtml(errText(err)); });
  }

  function decideComplaint(el) {
    var cid = el.getAttribute("data-id");
    busy(el, true);
    return post("/api/v1/operations/complaints/" + cid + "/decision", {
      status: valOf("coStatus" + cid),
    }).then(function () { toast(dual("تم تسجيل القرار.", "Decision recorded."), "ok"); return renderComplaints(); })
      .catch(function (err) { domainError(err); busy(el, false); });
  }

  function renderConfidentialGrants() {
    var host = byId("confContent");
    var canManage = has("confidential_access.manage");
    if (!canManage) {
      host.innerHTML = panel("التفويضات", "Delegated access", noticeHtml("ليست لديك صلاحية إدارة التفويضات.", "You may not manage delegated access."));
      return Promise.resolve();
    }
    var create = '<form class="av-form av-form-inline" id="confGrantForm">' +
      field("نوع السجل", "Subject type", selectInput("cgType", [
        { value: "complaint", label: opt("شكوى", "Complaint") },
        { value: "leadership_assessment", label: opt("تقييم قيادة", "Leadership assessment") },
      ], "complaint")) +
      field("معرّف السجل", "Subject id", numInput("cgSubject", "")) +
      field("المفوَّض له (معرّف المستخدم)", "Grantee user id", numInput("cgUser", "")) +
      field("الصلاحية", "Permission", selectInput("cgPerm", [
        { value: "complaint.read_own", label: "complaint.read_own" },
        { value: "assessment.read", label: "assessment.read" },
      ], "complaint.read_own")) +
      field("ينتهي في", "Expires at", '<input class="av-input" id="cgExpires" type="datetime-local">') +
      field("السبب", "Reason", textInput("cgReason", "")) +
      '<div class="av-form-actions"><button class="btn-solid" type="submit" data-act="conf-grant-create">' +
      dual("تفويض الوصول", "Grant access") + "</button></div></form>";
    var note = '<p class="note-block">' + dual("التفويض لسجل واحد وصلاحية واحدة فقط، مع انتهاء إلزامي وسجل تدقيق.", "A grant covers one record and one permission, with a mandatory expiry and an audit trail.") + "</p>";
    host.innerHTML = panel("تفويض الوصول السري (D04)", "Delegated confidential access (D04)", note + create);
    return Promise.resolve();
  }

  function createConfGrant(el) {
    var expires = valOf("cgExpires");
    if (!expires) {
      toast(dual("حدّد وقت الانتهاء (إلزامي).", "An expiry time is required."), "warn");
      return;
    }
    busy(el, true);
    return post("/api/v1/confidential-access/grants", {
      subject_type: valOf("cgType"),
      subject_id: parseInt(valOf("cgSubject"), 10),
      grantee_user_id: parseInt(valOf("cgUser"), 10),
      permission_code: valOf("cgPerm"),
      expires_at: expires.length === 16 ? expires + ":00" : expires,
      reason: valOf("cgReason") || null,
    }).then(function () { toast(dual("تم التفويض.", "Access granted."), "ok"); return renderConfidentialGrants(); })
      .catch(function (err) { domainError(err); busy(el, false); });
  }

  var ADMIN_TABS = ["structure", "companies", "departments", "sectors", "positions", "users", "roles", "motivation", "website", "builder", "workflows", "integrations", "audit"];
  var ADMIN_TAB_PERM = {
    structure: ["company.read", "ownership.read"],
    companies: ["company.read"],
    departments: ["department.read"],
    sectors: ["sector.read"],
    positions: ["position.read"],
    users: ["user.read_all"],
    roles: ["role.read"],
    motivation: ["motivation.read"],
    website: ["website.content.read"],
    builder: ["form.read", "form.create"],
    workflows: ["workflow.read"],
    integrations: ["integration.read"],
    audit: ["audit.read"],
  };

  function canTab(tab) {
    return (ADMIN_TAB_PERM[tab] || []).some(has);
  }

  function firstTab() {
    for (var i = 0; i < ADMIN_TABS.length; i++) {
      if (canTab(ADMIN_TABS[i])) return ADMIN_TABS[i];
    }
    return "structure";
  }

  function renderAdmin() {
    var host = byId("adminContent");
    if (!host) return Promise.resolve();
    if (!STATE.adminTab || !canTab(STATE.adminTab)) STATE.adminTab = firstTab();
    if (!STATE.adminBound) {
      STATE.adminBound = true;
      bindAdminTabs();
      host.addEventListener("click", onAdminClick);
      host.addEventListener("submit", onAdminSubmit);
    }
    return renderAdminTab(STATE.adminTab);
  }

  function bindAdminTabs() {
    document.querySelectorAll("[data-admin-tab]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var tab = btn.getAttribute("data-admin-tab");
        if (!canTab(tab)) return;
        STATE.adminTab = tab;
        document.querySelectorAll("[data-admin-tab]").forEach(function (b) {
          b.classList.toggle("on", b === btn);
        });
        renderAdminTab(tab);
      });
    });
  }

  function renderAdminTab(tab) {
    var host = byId("adminContent");
    if (!host) return Promise.resolve();
    document.querySelectorAll("[data-admin-tab]").forEach(function (b) {
      b.classList.toggle("on", b.getAttribute("data-admin-tab") === tab);
    });
    host.className = "av-grid " + (tab === "users" || tab === "roles" || tab === "builder" || tab === "website" ? "cols-1" : "cols-2");
    host.innerHTML = loadingHtml();
    if (tab === "structure") return renderAdminStructure();
    if (tab === "companies") return renderAdminCompanies();
    if (tab === "departments") return renderAdminDepartments();
    if (tab === "sectors") return renderAdminSectors();
    if (tab === "positions") return renderAdminPositions();
    if (tab === "users") return renderAdminUsers();
    if (tab === "roles") return renderAdminRoles();
    if (tab === "motivation") return renderAdminMotivation();
    if (tab === "website") return renderAdminWebsite();
    if (tab === "builder") return renderAdminBuilder();
    if (tab === "workflows") return renderAdminWorkflows();
    if (tab === "integrations") return renderAdminIntegrations();
    if (tab === "audit") return renderAdminAudit();
    return Promise.resolve();
  }

  function adminPanel(titleAr, titleEn, bodyHtml) {
    return (
      '<div class="av-panel"><h3>' + dual(titleAr, titleEn) + "</h3>" + bodyHtml + "</div>"
    );
  }

  function field(labelAr, labelEn, inputHtml) {
    return (
      '<div class="av-field"><label>' + dual(labelAr, labelEn) + "</label>" +
      inputHtml +
      "</div>"
    );
  }

  function textInput(id, value, placeholder) {
    // A placeholder that matches an I18N key is emitted bilingually so it
    // follows the language switch; anything else is a literal example token.
    var ph =
      placeholder && I18N[placeholder]
        ? phAttr(placeholder)
        : ' placeholder="' + escAttr(placeholder || "") + '"';
    return (
      '<input class="av-input" id="' + id + '" type="text" value="' +
      escAttr(value || "") + '"' + ph + ">"
    );
  }

  function selectInput(id, options, selected) {
    return (
      '<select class="av-select av-input" id="' + id + '">' +
      options.map(function (o) {
        return (
          '<option value="' + escAttr(o.value) + '"' +
          (String(o.value) === String(selected) ? " selected" : "") +
          ">" + escapeHtml(o.label) + "</option>"
        );
      }).join("") +
      "</select>"
    );
  }

  // ---- tab: structure & ownership ----
  function renderAdminStructure() {
    var host = byId("adminContent");
    return Promise.all([ensureCompanies(), get("/api/v1/admin/holding").catch(function () { return null; })]).then(function (res) {
      var holding = res[1];
      var structureP = has("ownership.read")
        ? get("/api/v1/admin/holding/structure").catch(function () { return []; })
        : Promise.resolve([]);
      var ownershipP = has("ownership.read")
        ? get("/api/v1/admin/ownerships").catch(function () { return []; })
        : Promise.resolve([]);
      return Promise.all([structureP, ownershipP]).then(function (r2) {
        host.innerHTML =
          adminPanel("بيانات القابضة", "Holding profile", holdingPanel(holding)) +
          adminPanel("هوية الموقع (الشعار)", "Website branding (logo)", brandingPanel(holding)) +
          adminPanel("هيكل الملكية", "Ownership structure", structurePanel(r2[0], r2[1]));
      });
    });
  }

  // The website logo is uploaded here and rendered by the public site's header.
  // No code change is needed to swap it later; an empty state shows the
  // built-in fallback mark the site uses until an official logo is uploaded.
  function brandingPanel(h) {
    var logoUrl = h && h.logo_url;
    var canManage = has("group.manage");
    var preview = logoUrl
      ? '<img class="brand-preview" src="' + escAttr(logoUrl) + '" alt="' +
        escAttr(dual("الشعار الحالي", "Current logo")) + '">'
      : '<div class="brand-preview brand-preview-empty">' +
        '<span class="brand-preview-mark" aria-hidden="true"></span>' +
        '<span>' + dual("لا يوجد شعار مرفوع — يستخدم الموقع الشعار الافتراضي.", "No logo uploaded — the site uses its default mark.") + "</span>" +
        "</div>";
    if (!canManage) {
      return '<div class="branding-box">' + preview + "</div>";
    }
    return (
      '<div class="branding-box">' +
      preview +
      '<p class="branding-hint">' +
      dual("ارفع شعار القابضة الرسمي (PNG أو JPEG أو WebP أو GIF، بحد أقصى 4 ميجابايت). يُعرض في ترويسة الموقع العامة.", "Upload the official Holding logo (PNG, JPEG, WebP or GIF, max 4 MB). It appears in the public website header.") +
      "</p>" +
      '<div class="branding-controls">' +
      '<input class="av-input" type="file" id="brandLogoFile" accept="image/png,image/jpeg,image/webp,image/gif">' +
      '<button class="btn-solid" type="button" data-admin-action="upload-logo">' +
      dual(logoUrl ? "استبدال الشعار" : "رفع الشعار", logoUrl ? "Replace logo" : "Upload logo") + "</button>" +
      (logoUrl
        ? '<button class="btn-outline" type="button" data-admin-action="remove-logo">' +
          dual("إزالة الشعار", "Remove logo") + "</button>"
        : "") +
      "</div></div>"
    );
  }

  function holdingPanel(h) {
    if (!h) return '<p class="av-empty">' + dual("لا توجد بيانات.", "No data.") + "</p>";
    if (!has("group.manage")) {
      return (
        '<div class="kv">' +
        kv(dual("الاسم", "Name"), escapeHtml(h.display_name_ar || h.legal_name_ar || "—")) +
        kv(dual("الاسم القانوني", "Legal name"), escapeHtml(h.legal_name_en || "—")) +
        kv(dual("العملة", "Currency"), escapeHtml(h.default_currency || "—")) +
        kv(dual("الحالة", "Status"), escapeHtml(h.status || "—")) +
        "</div>"
      );
    }
    return (
      '<form class="av-form" id="holdingForm">' +
      field("الاسم القانوني (عربي)", "Legal name (AR)", textInput("hLegalAr", h.legal_name_ar)) +
      field("الاسم القانوني (إنجليزي)", "Legal name (EN)", textInput("hLegalEn", h.legal_name_en)) +
      field("السجل التجاري", "Commercial registration", textInput("hCr", h.commercial_registration)) +
      field("الرقم الضريبي", "Tax number", textInput("hTax", h.tax_number)) +
      field("العملة الافتراضية", "Default currency", textInput("hCurrency", h.default_currency)) +
      field("البريد", "Email", textInput("hEmail", h.contact_email)) +
      field("الهاتف", "Phone", textInput("hPhone", h.phone)) +
      '<div class="av-form-actions"><button class="btn-solid" type="submit" data-admin-action="save-holding">' +
      dual("حفظ", "Save") + "</button></div></form>"
    );
  }

  function structurePanel(nodes, ownerships) {
    if (!nodes.length) return '<p class="av-empty">' + dual("لا توجد شركات.", "No companies.") + "</p>";
    var byParent = {};
    var roots = [];
    nodes.forEach(function (n) {
      if (n.parent_company_id) {
        (byParent[n.parent_company_id] = byParent[n.parent_company_id] || []).push(n);
      } else {
        roots.push(n);
      }
    });
    // A forest: nodes whose parent is not in the visible set render as roots,
    // so nothing is ever hidden by a scoping filter.
    var visible = {};
    nodes.forEach(function (n) { visible[n.company_id] = true; });
    nodes.forEach(function (n) {
      if (n.parent_company_id && !visible[n.parent_company_id] && roots.indexOf(n) < 0) {
        roots.push(n);
      }
    });

    function branch(n, depth) {
      var kids = (byParent[n.company_id] || []).filter(function (k) { return k !== n; });
      return (
        '<div class="tree-node" style="margin-inline-start:' + depth * 16 + 'px">' +
        '<div class="co-dot" style="background:' + PALETTE[n.company_id % PALETTE.length] + '">' + initial(n.name_ar) + "</div>" +
        '<div class="grow"><div class="t">' + escapeHtml(companyLabel(n)) + "</div>" +
        '<div class="s">' + escapeHtml(n.sector || "") +
        (n.ownership_percentage != null ? " · " + dual(toArabicDigits(n.ownership_percentage + "٪"), n.ownership_percentage + "%") : "") +
        "</div></div></div>" +
        kids.map(function (k) { return branch(k, depth + 1); }).join("")
      );
    }

    return (
      '<div class="av-tree">' + roots.map(function (n) { return branch(n, 0); }).join("") + "</div>" +
      (has("ownership.manage")
        ? '<form class="av-form av-form-inline" id="stakeForm">' +
          field("الشركة المملوكة", "Owned company", selectInput("stOwned", companyOptions(nodes), "")) +
          field("المالك", "Owner", selectInput("stOwner", [{ value: "", label: "—" }].concat(companyOptions(nodes)), "")) +
          field("النسبة %", "Percentage %", '<input class="av-input" id="stPct" type="number" min="0" max="100" step="0.01">') +
          field("من تاريخ", "Effective from", '<input class="av-input" id="stFrom" type="date">') +
          '<div class="av-form-actions"><button class="btn-outline" type="submit" data-admin-action="add-stake">' +
          dual("إضافة حصة", "Add stake") + "</button></div></form>"
        : "") +
      (ownerships.length
        ? '<div class="sec-title">' + dual("الحصص المسجلة", "Recorded stakes") + "</div>" +
          '<div class="av-list">' + ownerships.map(function (s) {
            return (
              '<div class="av-row" style="cursor:default"><div class="grow"><div class="t">' +
              escapeHtml(ownerLabel(s)) + " → " + escapeHtml(ownedLabel(s)) + "</div>" +
              '<div class="s">' + dual(toArabicDigits(s.ownership_percentage + "٪"), s.ownership_percentage + "%") +
              " · " + escapeHtml(s.status) + " · " + fmtDate(s.effective_from) + "</div></div>" +
              (has("ownership.manage") && s.status === "active"
                ? '<button class="btn-outline" data-admin-action="end-stake" data-id="' + s.id + '">' + dual("إنهاء", "End") + "</button>"
                : "") +
              "</div>"
            );
          }).join("") + "</div>"
        : "")
    );
  }

  function companyOptions(nodes) {
    return nodes.map(function (n) {
      return { value: n.company_id, label: companyLabel(n) };
    });
  }

  function companyLabel(n) {
    return STATE.lang === "ar" ? (n.name_ar || n.name_en) : (n.name_en || n.name_ar);
  }

  function ownedLabel(s) {
    return STATE.lang === "ar" ? (s.owned_company_name_ar || s.owned_company_name_en) : (s.owned_company_name_en || s.owned_company_name_ar);
  }

  function ownerLabel(s) {
    if (s.owner_company_id) {
      return STATE.lang === "ar" ? (s.owner_company_name_ar || s.owner_company_name_en) : (s.owner_company_name_en || s.owner_company_name_ar);
    }
    return s.external_owner_name || "—";
  }

  // ---- tab: companies ----
  function renderAdminCompanies() {
    var host = byId("adminContent");
    return ensureCompanies().then(function (rows) {
      var create = has("company.manage")
        ? adminPanel("إضافة شركة", "Add company",
            '<form class="av-form av-form-inline" id="companyCreateForm">' +
            field("الكود", "Code", textInput("ccCode", "")) +
            field("الاسم (عربي)", "Name (AR)", textInput("ccNameAr", "")) +
            field("الاسم (إنجليزي)", "Name (EN)", textInput("ccNameEn", "")) +
            field("القطاع", "Sector", textInput("ccSector", "")) +
            field("العملة", "Currency", textInput("ccCurrency", "SAR")) +
            field("الدولة", "Country", textInput("ccCountry", "")) +
            '<div class="av-form-actions"><button class="btn-solid" type="submit">' +
            dual("تسجيل شركة", "Register company") + "</button></div></form>")
        : "";
      var list = rows.length
        ? rows.map(function (c) { return adminPanel("شركة", "Company", companyAdminCard(c)); }).join("")
        : '<p class="av-empty">' + dual("لا توجد شركات.", "No companies.") + "</p>";
      host.innerHTML = create + list;
      var form = byId("companyCreateForm");
      if (form) {
        form.addEventListener("submit", function (ev) {
          ev.preventDefault();
          var btn = form.querySelector("button");
          busy(btn, true);
          post("/api/v1/companies", {
            code: valOf("ccCode"),
            name_ar: valOf("ccNameAr"),
            name_en: valOf("ccNameEn"),
            sector: valOf("ccSector") || null,
            currency: valOf("ccCurrency") || "SAR",
            country: valOf("ccCountry") || null,
          }).then(function () {
            STATE.loaded.companies = false;
            toast(dual("تم تسجيل الشركة.", "Company registered."), "ok");
            return renderAdminCompanies();
          }).catch(function (err) { adminError(err); busy(btn, false); });
        });
      }
    });
  }

  function companyAdminCard(c) {
    var sector = sectorLabel(c.sector);
    var base =
      '<div style="display:flex;align-items:center;gap:11px;margin-bottom:9px">' +
      '<div class="co-dot" style="background:' + PALETTE[c.id % PALETTE.length] + '">' + initial(c.name_ar) + "</div>" +
      '<div class="grow"><div class="t">' + escapeHtml(companyName(c)) + "</div>" +
      '<div class="s">' + escapeHtml(c.code) + " · " + dual(escapeHtml(sector.ar), escapeHtml(sector.en)) + "</div></div>" +
      healthBadge(c.health) + "</div>";
    if (!has("company.manage")) return base;
    return (
      base +
      '<form class="av-form" id="companyForm' + c.id + '">' +
      field("الاسم (عربي)", "Name (AR)", textInput("cNameAr" + c.id, c.name_ar)) +
      field("الاسم (إنجليزي)", "Name (EN)", textInput("cNameEn" + c.id, c.name_en)) +
      field("القطاع", "Sector", textInput("cSector" + c.id, c.sector)) +
      field("العملة", "Currency", textInput("cCurrency" + c.id, c.currency)) +
      field("الدولة", "Country", textInput("cCountry" + c.id, c.country)) +
      '<div class="av-form-actions"><button class="btn-outline" type="submit" data-admin-action="save-company" data-id="' + c.id + '">' +
      dual("حفظ", "Save") + "</button></div></form>"
    );
  }

  // ---- tab: departments ----
  function renderAdminDepartments() {
    var host = byId("adminContent");
    return Promise.all([ensureCompanies(), get("/api/v1/admin/departments").catch(function () { return []; })]).then(function (res) {
      var companies = res[0];
      var departments = res[1];
      var createForm = has("department.manage")
        ? '<form class="av-form av-form-inline" id="deptForm">' +
          field("الشركة", "Company", selectInput("dCompany", companies.map(function (c) { return { value: c.id, label: companyName(c) }; }), companies.length ? companies[0].id : "")) +
          field("الكود", "Code", textInput("dCode", "", "ph.companyCode")) +
          field("الاسم (عربي)", "Name (AR)", textInput("dNameAr", "")) +
          field("الاسم (إنجليزي)", "Name (EN)", textInput("dNameEn", "")) +
          '<div class="av-form-actions"><button class="btn-outline" type="submit" data-admin-action="add-department">' +
          dual("إضافة قسم", "Add department") + "</button></div></form>"
        : "";
      var list = departments.length
        ? '<div class="av-list">' + departments.map(function (d) {
            return (
              '<div class="av-row" style="cursor:default"><div class="grow"><div class="t">' +
              escapeHtml(STATE.lang === "ar" ? d.name_ar : d.name_en || d.name_ar) + "</div>" +
              '<div class="s">' + escapeHtml(d.code) + " · " +
              escapeHtml(STATE.lang === "ar" ? d.company_name_ar || "" : d.company_name_en || d.company_name_ar || "") +
              "</div></div>" +
              '<span class="status ' + (d.status === "active" ? "ok" : "warn") + '"><i></i>' + escapeHtml(d.status) + "</span></div>"
            );
          }).join("") + "</div>"
        : '<p class="av-empty">' + dual("لا توجد أقسام.", "No departments.") + "</p>";
      host.innerHTML =
        adminPanel("الأقسام", "Departments", createForm + list) +
        adminPanel("ملخص", "Summary", '<div class="kv">' +
          kv(dual("عدد الأقسام", "Departments"), plainNum(departments.length)) +
          kv(dual("الشركات المتاحة", "Companies in scope"), plainNum(companies.length)) +
          "</div>");
    });
  }

  // ---- tab: sectors ----
  //
  // The managed sector catalogue (S03) behind ``companies.sector``. Reads are
  // gated on sector.read; writes on sector.manage. The list is bilingual and
  // RTL-safe because it uses the same dual()/escapeHtml primitives as the rest
  // of the admin UI.
  function renderAdminSectors() {
    var host = byId("adminContent");
    return get("/api/v1/admin/sectors").catch(function () { return []; }).then(function (sectors) {
      var create = has("sector.manage")
        ? adminPanel("إضافة قطاع", "Add sector",
            '<form class="av-form av-form-inline" id="sectorForm">' +
            field("الكود", "Code", textInput("scCode", "", "ph.companyCode")) +
            field("الاسم (عربي)", "Name (AR)", textInput("scNameAr", "")) +
            field("الاسم (إنجليزي)", "Name (EN)", textInput("scNameEn", "")) +
            field("الترتيب", "Order", numInput("scOrder", 0)) +
            '<div class="av-form-actions"><button class="btn-solid" type="submit">' +
            dual("إضافة قطاع", "Add sector") + "</button></div></form>")
        : "";
      var list = sectors.length
        ? sectors.map(function (s) {
            var body =
              '<div style="display:flex;align-items:center;gap:11px">' +
              '<div class="grow"><div class="t">' +
              escapeHtml(STATE.lang === "ar" ? s.name_ar : s.name_en || s.name_ar) +
              '</div><div class="s">' + escapeHtml(s.code) + " · " +
              escapeHtml(STATE.lang === "ar" ? s.name_en || "" : s.name_ar || "") +
              "</div></div>" +
              '<span class="status ' + (s.status === "active" ? "ok" : "warn") + '"><i></i>' +
              escapeHtml(s.status) + "</span></div>";
            if (!has("sector.manage")) {
              return '<div class="av-row" style="cursor:default">' + body + "</div>";
            }
            return (
              '<div class="av-row" style="flex-direction:column;align-items:stretch;cursor:default">' +
              body +
              '<form class="av-form" id="sectorForm' + s.id + '">' +
              field("الاسم (عربي)", "Name (AR)", textInput("scNameAr" + s.id, s.name_ar)) +
              field("الاسم (إنجليزي)", "Name (EN)", textInput("scNameEn" + s.id, s.name_en)) +
              field("الحالة", "Status", selectInput("scStatus" + s.id, [
                { value: "active", label: opt("نشط", "Active") },
                { value: "inactive", label: opt("موقوف", "Inactive") },
              ], s.status)) +
              field("الترتيب", "Order", numInput("scOrder" + s.id, s.sort_order)) +
              '<div class="av-form-actions"><button class="btn-outline" type="submit" data-admin-action="save-sector" data-id="' + s.id + '">' +
              dual("حفظ", "Save") + "</button></div></form></div>"
            );
          }).join("")
        : '<p class="av-empty">' + dual("لا توجد قطاعات.", "No sectors.") + "</p>";
      host.innerHTML =
        create +
        adminPanel("القطاعات", "Sectors", list) +
        adminPanel("ملخص", "Summary", '<div class="kv">' +
          kv(dual("عدد القطاعات", "Sectors"), plainNum(sectors.length)) +
          kv(dual("القطاعات النشطة", "Active"),
            plainNum(sectors.filter(function (s) { return s.status === "active"; }).length)) +
          "</div>");
    });
  }
  // ---- tab: positions (S24) ----
  //
  // Company-scoped nodes in the organisation chart. Reads need position.read;
  // writes need position.manage. The department picker only offers departments
  // of the selected company, and the reporting-line picker only offers
  // positions of the same company -- mirroring the server-side invariant that a
  // position never crosses a company boundary.
  function renderAdminPositions() {
    var host = byId("adminContent");
    return Promise.all([
      ensureCompanies(),
      get("/api/v1/admin/positions").catch(function () { return []; }),
      get("/api/v1/admin/departments").catch(function () { return []; }),
    ]).then(function (res) {
      var companies = res[0];
      var positions = res[1];
      var departments = res[2];
      var editable = has("position.manage");
      var companyOptions = companies.map(function (c) { return { value: c.id, label: companyName(c) }; });

      function deptOptionsFor(companyId) {
        return [{ value: "", label: "—" }].concat(
          departments
            .filter(function (d) { return String(d.company_id) === String(companyId); })
            .map(function (d) { return { value: d.id, label: d.code + " · " + (STATE.lang === "ar" ? d.name_ar : d.name_en || d.name_ar) }; })
        );
      }
      function parentOptionsFor(companyId) {
        return [{ value: "", label: "—" }].concat(
          positions
            .filter(function (p) { return String(p.company_id) === String(companyId); })
            .map(function (p) { return { value: p.id, label: p.code + " · " + (STATE.lang === "ar" ? p.title_ar : p.title_en) }; })
        );
      }

      var createForm = editable
        ? '<form class="av-form av-form-inline" id="positionForm">' +
          field("الشركة", "Company", selectInput("posCompany", companyOptions, companies.length ? companies[0].id : "")) +
          field("الكود", "Code", textInput("posCode", "", "ph.companyCode")) +
          field("المسمى (عربي)", "Title (AR)", textInput("posTitleAr", "")) +
          field("المسمى (إنجليزي)", "Title (EN)", textInput("posTitleEn", "")) +
          '<div class="av-form-actions"><button class="btn-solid" type="submit">' +
          dual("إضافة منصب", "Add position") + "</button></div></form>"
        : "";

      var list = positions.length
        ? '<div class="av-list">' + positions.map(function (p) {
            var body =
              '<div style="display:flex;align-items:center;gap:11px">' +
              '<div class="grow"><div class="t">' +
              escapeHtml(STATE.lang === "ar" ? p.title_ar : p.title_en || p.title_ar) + "</div>" +
              '<div class="s">' + escapeHtml(p.code) + " · " +
              escapeHtml(STATE.lang === "ar" ? p.company_name_ar || "" : p.company_name_en || p.company_name_ar || "") +
              (p.department_name_en || p.department_name_ar
                ? " · " + escapeHtml(STATE.lang === "ar" ? p.department_name_ar || "" : p.department_name_en || p.department_name_ar || "")
                : "") +
              (p.reports_to_title_en || p.reports_to_title_ar
                ? " · " + dual("يتبع", "reports to") + " " + escapeHtml(STATE.lang === "ar" ? p.reports_to_title_ar || "" : p.reports_to_title_en || p.reports_to_title_ar || "")
                : "") +
              "</div></div>" +
              '<span class="status ' + (p.status === "active" ? "ok" : "warn") + '"><i></i>' +
              (p.status === "active" ? dual("نشط", "Active") : dual("موقوف", "Inactive")) + "</span></div>";
            if (!editable) {
              return '<div class="av-row" style="cursor:default">' + body + "</div>";
            }
            return (
              '<div class="av-row" style="flex-direction:column;align-items:stretch;cursor:default">' +
              body +
              '<form class="av-form" id="positionForm' + p.id + '">' +
              field("المسمى (عربي)", "Title (AR)", textInput("posTitleAr" + p.id, p.title_ar)) +
              field("المسمى (إنجليزي)", "Title (EN)", textInput("posTitleEn" + p.id, p.title_en)) +
              field("القسم", "Department", selectInput("posDept" + p.id, deptOptionsFor(p.company_id), p.department_id || "")) +
              field("يتبع منصب", "Reports to", selectInput("posParent" + p.id, parentOptionsFor(p.company_id), p.reports_to_position_id || "")) +
              field("الحالة", "Status", selectInput("posStatus" + p.id, [
                { value: "active", label: opt("نشط", "Active") },
                { value: "inactive", label: opt("موقوف", "Inactive") },
              ], p.status)) +
              '<div class="av-form-actions"><button class="btn-outline" type="submit" data-admin-action="save-position" data-id="' + p.id + '">' +
              dual("حفظ", "Save") + "</button></div></form></div>"
            );
          }).join("") + "</div>"
        : '<p class="av-empty">' + dual("لا توجد مناصب.", "No positions.") + "</p>";

      host.innerHTML =
        createForm +
        adminPanel("الهيكل الوظيفي", "Positions", list) +
        adminPanel("ملخص", "Summary", '<div class="kv">' +
          kv(dual("عدد المناصب", "Positions"), plainNum(positions.length)) +
          kv(dual("المناصب النشطة", "Active"), plainNum(positions.filter(function (p) { return p.status === "active"; }).length)) +
          kv(dual("الشركات في النطاق", "Companies in scope"), plainNum(companies.length)) +
          "</div>");
    });
  }



  // ---- tab: users ----
  function renderAdminUsers() {
    var host = byId("adminContent");
    var page = STATE.adminUsers || (STATE.adminUsers = { limit: 25, offset: 0, total: 0 });
    return Promise.all([
      get("/api/v1/admin/users?limit=" + page.limit + "&offset=" + page.offset),
      get("/api/v1/admin/roles").catch(function () { return []; }),
      ensureCompanies(),
      get("/api/v1/admin/departments").catch(function () { return []; }),
    ]).then(function (res) {
      var data = res[0];
      var roles = res[1];
      var departments = res[3];
      page.total = data.total;
      var roleOptions = roles.map(function (r) { return { value: r.code, label: STATE.lang === "ar" ? r.name_ar : r.name_en }; });
      var deptOptions = [{ value: "", label: "—" }].concat(departments.map(function (d) { return { value: d.id, label: d.code + " · " + (STATE.lang === "ar" ? d.name_ar : d.name_en) }; }));

      var rows = data.items.map(function (u) {
        var name = STATE.lang === "ar" ? u.full_name_ar : u.full_name_en || u.full_name_ar;
        var controls = has("user.manage")
          ? '<div class="av-user-controls">' +
            selectInput("uRole" + u.id, roleOptions, u.role_code) +
            selectInput("uDept" + u.id, deptOptions, u.department_id || "") +
            '<button class="btn-outline" data-admin-action="save-user" data-id="' + u.id + '">' + dual("حفظ", "Save") + "</button>" +
            '<button class="btn-outline" data-admin-action="toggle-user" data-id="' + u.id + '" data-active="' + (u.is_active ? "1" : "0") + '">' +
            (u.is_active ? dual("إيقاف", "Deactivate") : dual("تفعيل", "Activate")) + "</button>" +
            "</div>"
          : "";
        return (
          '<div class="av-row" style="flex-direction:column;align-items:stretch;cursor:default">' +
          '<div style="display:flex;align-items:center;gap:11px"><div class="co-dot" style="background:' + PALETTE[u.id % PALETTE.length] + '">' + initial(u.full_name_ar) + "</div>" +
          '<div class="grow"><div class="t">' + escapeHtml(name) + "</div>" +
          '<div class="s">' + escapeHtml(u.email) + " · " + escapeHtml(STATE.lang === "ar" ? u.role_name_ar || u.role_code : u.role_name_en || u.role_code) + "</div></div>" +
          '<span class="status ' + (u.is_active ? "ok" : "warn") + '"><i></i>' +
          (u.is_active ? dual("نشط", "Active") : dual("موقوف", "Inactive")) + "</span></div>" +
          controls + "</div>"
        );
      }).join("");

      var pager =
        '<div class="av-pager">' +
        '<button class="btn-outline" data-admin-action="users-prev"' + (page.offset === 0 ? " disabled" : "") + ">" + dual("السابق", "Previous") + "</button>" +
        '<span class="av-pager-info">' + plainNum(page.offset + 1) + " – " + plainNum(Math.min(page.offset + page.limit, page.total)) + " / " + plainNum(page.total) + "</span>" +
        '<button class="btn-outline" data-admin-action="users-next"' + (page.offset + page.limit >= page.total ? " disabled" : "") + ">" + dual("التالي", "Next") + "</button></div>";

      host.innerHTML = adminPanel("المستخدمون", "Users", (rows ? '<div class="av-list">' + rows + "</div>" : '<p class="av-empty">' + dual("لا يوجد مستخدمون.", "No users.") + "</p>") + pager);
    });
  }

  // ---- tab: roles & permissions ----
  //
  // The catalogue arrives from the API already described in Arabic and English
  // (name, description, category, action, danger), so nothing is hard-coded
  // here and a permission added on the backend appears immediately. The raw
  // code is shown only as secondary help text. Authorization is unchanged: the
  // editor only ever sends the same permission codes the API already enforces.
  function permState() {
    if (!STATE.perm) {
      STATE.perm = {
        catalogue: null,
        byCode: {},
        roleCode: null,
        selected: {},
        original: {},
        query: "",
        category: "all",
        dirty: false,
      };
    }
    return STATE.perm;
  }

  function loadPermissionCatalogue() {
    var st = permState();
    if (st.catalogue) return Promise.resolve(st.catalogue);
    return get("/api/v1/admin/permissions/catalogue").then(function (data) {
      st.catalogue = data || { categories: [], actions: [], permissions: [] };
      st.byCode = {};
      (st.catalogue.permissions || []).forEach(function (p) {
        st.byCode[p.code] = p;
      });
      return st.catalogue;
    });
  }

  function permMeta(code) {
    var st = permState();
    return (
      st.byCode[code] || {
        code: code,
        name_ar: code,
        name_en: code,
        description_ar: "",
        description_en: "",
        category: "audit",
        action: "manage",
        danger: false,
      }
    );
  }

  function permRoleByCode(roles, code) {
    for (var i = 0; i < roles.length; i++) {
      if (roles[i].code === code) return roles[i];
    }
    return null;
  }

  function renderAdminRoles() {
    var host = byId("adminContent");
    var st = permState();
    return Promise.all([get("/api/v1/admin/roles"), loadPermissionCatalogue()]).then(
      function (res) {
        var roles = res[0] || [];
        if (!roles.length) {
          host.innerHTML =
            '<p class="av-empty">' + dual("لا توجد أدوار.", "No roles.") + "</p>";
          return;
        }
        var role = permRoleByCode(roles, st.roleCode) || roles[0];
        st.roleCode = role.code;
        st.selected = {};
        (role.permissions || []).forEach(function (c) {
          st.selected[c] = true;
        });
        st.original = Object.assign({}, st.selected);
        st.dirty = false;
        host.innerHTML = rolesBar(roles, role) + permEditor(role);
        bindPermEditor(role);
      },
    );
  }

  function rolesBar(roles, active) {
    return (
      '<div class="av-panel" style="margin-bottom:12px"><h3>' +
      dual("الأدوار", "Roles") +
      "</h3>" +
      '<div class="perm-cats">' +
      roles
        .map(function (r) {
          var n = (r.permissions || []).length;
          return (
            '<button type="button" class="perm-cat-chip' +
            (r.code === active.code ? " on" : "") +
            '" data-admin-action="role-open" data-code="' +
            escAttr(r.code) +
            '">' +
            dual(escapeHtml(r.name_ar), escapeHtml(r.name_en)) +
            '<span class="c">' +
            plainNum(n) +
            "</span></button>"
          );
        })
        .join("") +
      "</div></div>"
    );
  }

  function permEditor(role) {
    var st = permState();
    var editable = has("permission.assign");
    var cats = (st.catalogue.categories || []).slice().sort(function (a, b) {
      return a.order - b.order;
    });
    var catChips =
      '<button type="button" class="perm-cat-chip on" data-admin-action="perm-cat" data-cat="all">' +
      dual("كل الأقسام", "All categories") +
      "</button>" +
      cats
        .map(function (c) {
          return (
            '<button type="button" class="perm-cat-chip" data-admin-action="perm-cat" data-cat="' +
            escAttr(c.key) +
            '">' +
            dual(escapeHtml(c.name_ar), escapeHtml(c.name_en)) +
            "</button>"
          );
        })
        .join("");

    return (
      '<div class="av-panel" id="permEditor" data-role="' +
      escAttr(role.code) +
      '">' +
      '<div class="perm-role-head"><div class="perm-role-title">' +
      dual(escapeHtml(role.name_ar), escapeHtml(role.name_en)) +
      (role.is_system
        ? '<span class="perm-badge">' + dual("دور نظام", "System role") + "</span>"
        : "") +
      "</div><div class=\"perm-role-desc\">" +
      dual(
        escapeHtml(role.description_ar || role.description || ""),
        escapeHtml(role.description || ""),
      ) +
      '</div><div class="perm-code">' +
      escapeHtml(role.code) +
      "</div></div>" +
      '<div class="perm-toolbar">' +
      '<div class="perm-search">' +
      '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.2-3.2"/></svg>' +
      '<input class="av-input" id="permSearch" type="search" autocomplete="off" value="' +
      escAttr(st.query) +
      '" aria-label="' +
      escAttr(STATE.lang === "ar" ? "ابحث في الصلاحيات" : "Search permissions") +
      '"' +
      phAttr("ph.search.permissions") +
      ">" +
      "</div></div>" +
      '<div class="perm-toolbar"><div class="perm-cats" id="permCats">' +
      catChips +
      "</div></div>" +
      '<div class="perm-summary" id="permSummary"></div>' +
      '<div id="permGroups"></div>' +
      (editable
        ? '<div class="perm-actions-bar">' +
          '<div class="pmeta" id="permDirty"></div>' +
          '<div class="pbtns">' +
          '<button type="button" class="btn-outline" data-admin-action="perm-cancel">' +
          dual("إلغاء", "Cancel") +
          "</button>" +
          '<button type="button" class="btn-solid" data-admin-action="perm-save">' +
          dual("حفظ الصلاحيات", "Save permissions") +
          "</button>" +
          "</div></div>"
        : '<p class="av-empty">' +
          dual("لا تملك صلاحية تعديل الأدوار.", "You cannot edit roles.") +
          "</p>") +
      "</div>"
    );
  }

  function permCard(code, editable) {
    var st = permState();
    var m = permMeta(code);
    var checked = !!st.selected[code];
    return (
      '<label class="perm-card' +
      (checked ? " on" : "") +
      (m.danger ? " danger" : "") +
      '">' +
      '<input type="checkbox" data-perm-code="' +
      escAttr(code) +
      '"' +
      (checked ? " checked" : "") +
      (editable ? "" : " disabled") +
      ">" +
      '<span class="perm-body">' +
      '<span class="perm-name">' +
      dual(escapeHtml(m.name_ar), escapeHtml(m.name_en)) +
      (m.danger
        ? '<span class="perm-badge danger">' +
          dual("حساس", "Sensitive") +
          "</span>"
        : "") +
      "</span>" +
      '<span class="perm-desc">' +
      dual(escapeHtml(m.description_ar), escapeHtml(m.description_en)) +
      "</span>" +
      '<span class="perm-code">' +
      escapeHtml(code) +
      "</span>" +
      "</span></label>"
    );
  }

  function renderPermGroups() {
    var st = permState();
    var groupsHost = byId("permGroups");
    if (!groupsHost) return;
    var editable = has("permission.assign");
    var q = (st.query || "").trim().toLowerCase();
    var cats = (st.catalogue.categories || []).slice().sort(function (a, b) {
      return a.order - b.order;
    });
    var acts = {};
    (st.catalogue.actions || []).forEach(function (a) {
      acts[a.key] = a;
    });

    var html = "";
    cats.forEach(function (cat) {
      if (st.category !== "all" && st.category !== cat.key) return;
      var items = (st.catalogue.permissions || []).filter(function (p) {
        if (p.category !== cat.key) return false;
        if (!q) return true;
        return permHaystack(p).indexOf(q) >= 0;
      });
      if (!items.length) return;
      items.sort(function (a, b) {
        var ao = acts[a.action] ? acts[a.action].order : 99;
        var bo = acts[b.action] ? acts[b.action].order : 99;
        return ao - bo || a.code.localeCompare(b.code);
      });
      var enabled = items.filter(function (p) {
        return st.selected[p.code];
      }).length;
      html +=
        '<div class="perm-group" data-cat="' +
        escAttr(cat.key) +
        '">' +
        '<div class="perm-group-head"><h4>' +
        dual(escapeHtml(cat.name_ar), escapeHtml(cat.name_en)) +
        ' <span class="pcount">' +
        plainNum(enabled) +
        " / " +
        plainNum(items.length) +
        "</span></h4>" +
        (editable
          ? '<button type="button" class="perm-selectall" data-admin-action="perm-selectall" data-cat="' +
            escAttr(cat.key) +
            '">' +
            dual("تحديد الكل", "Select all") +
            "</button>"
          : "") +
        "</div>" +
        '<div class="perm-list" role="group" aria-label="' +
        escAttr(STATE.lang === "ar" ? cat.name_ar : cat.name_en) +
        '">' +
        items
          .map(function (p) {
            return permCard(p.code, editable);
          })
          .join("") +
        "</div></div>";
    });

    groupsHost.innerHTML =
      html ||
      '<p class="perm-empty">' +
        dual("لا توجد صلاحيات مطابقة.", "No matching permissions.") +
        "</p>";
    updatePermSummary();
  }

  function permHaystack(p) {
    return (
      p.code +
      " " +
      p.name_ar +
      " " +
      p.name_en +
      " " +
      p.description_ar +
      " " +
      p.description_en
    ).toLowerCase();
  }

  function visiblePermCodes() {
    var st = permState();
    var q = (st.query || "").trim().toLowerCase();
    return (st.catalogue.permissions || [])
      .filter(function (p) {
        if (st.category !== "all" && p.category !== st.category) return false;
        if (!q) return true;
        return permHaystack(p).indexOf(q) >= 0;
      })
      .map(function (p) {
        return p.code;
      });
  }

  function updatePermSummary() {
    var st = permState();
    var summary = byId("permSummary");
    if (!summary) return;
    var all = (st.catalogue.permissions || []).map(function (p) {
      return p.code;
    });
    var enabled = all.filter(function (c) {
      return st.selected[c];
    }).length;
    var dangerOn = all.filter(function (c) {
      return st.selected[c] && permMeta(c).danger;
    }).length;
    var vis = visiblePermCodes();
    var visOn = vis.filter(function (c) {
      return st.selected[c];
    }).length;
    summary.innerHTML =
      "<div><div class=\"pnum\">" +
      plainNum(enabled) +
      '</div><div class="plabel">' +
      dual("صلاحية مُفعّلة", "permissions enabled") +
      "</div></div>" +
      '<div class="psep"></div>' +
      "<div><div class=\"pnum\">" +
      plainNum(all.length) +
      '</div><div class="plabel">' +
      dual("إجمالي الصلاحيات", "total permissions") +
      "</div></div>" +
      '<div class="psep"></div>' +
      "<div><div class=\"pnum\">" +
      plainNum(visOn) +
      " / " +
      plainNum(vis.length) +
      '</div><div class="plabel">' +
      dual("ضمن نتائج العرض الحالية", "in current view") +
      "</div></div>" +
      (dangerOn
        ? '<span class="pdanger">' +
          '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 9v4"/><path d="M12 17h.01"/><path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z"/></svg>' +
          dual(
            toArabicDigits(String(dangerOn)) + " صلاحية حساسة مُفعّلة",
            dangerOn + " sensitive permissions enabled",
          ) +
          "</span>"
        : "") +
      updatePermDirty();
  }

  function updatePermDirty() {
    var st = permState();
    var dirtyHost = byId("permDirty");
    var changed = 0;
    var all = (st.catalogue.permissions || []).map(function (p) {
      return p.code;
    });
    all.forEach(function (c) {
      if (!!st.selected[c] !== !!st.original[c]) changed += 1;
    });
    st.dirty = changed > 0;
    if (dirtyHost) {
      dirtyHost.innerHTML = changed
        ? dual(
            toArabicDigits(String(changed)) + " تغيير غير محفوظ",
            changed + " unsaved change(s)",
          )
        : dual("لا تغييرات غير محفوظة", "No unsaved changes");
    }
    var saveBtn = document.querySelector('[data-admin-action="perm-save"]');
    if (saveBtn) saveBtn.disabled = !changed;
    return "";
  }

  function bindPermEditor(role) {
    var st = permState();
    renderPermGroups();
    var search = byId("permSearch");
    if (search) {
      search.addEventListener(
        "input",
        debounce(function () {
          st.query = search.value;
          renderPermGroups();
        }, 140),
      );
    }
    var editor = byId("permEditor");
    if (!editor) return;
    editor.addEventListener("change", function (e) {
      var cb = e.target.closest ? e.target.closest("[data-perm-code]") : null;
      if (!cb) return;
      var code = cb.getAttribute("data-perm-code");
      st.selected[code] = cb.checked;
      var card = cb.closest(".perm-card");
      if (card) card.classList.toggle("on", cb.checked);
      updatePermSummary();
      updateGroupCounts();
    });
  }

  function updateGroupCounts() {
    var st = permState();
    void st;
    document.querySelectorAll("#permGroups .perm-group").forEach(function (g) {
      var boxes = g.querySelectorAll("[data-perm-code]");
      var on = 0;
      boxes.forEach(function (b) {
        if (b.checked) on += 1;
      });
      var count = g.querySelector(".pcount");
      if (count) count.textContent = on + " / " + boxes.length;
    });
  }

  // ---- tab: motivational sentence library (S01) ----
  //
  // A small bilingual library the owner edits; each dashboard shows one active
  // sentence chosen for the viewer's role (falling back to a role-agnostic
  // row). Reads need motivation.read, writes need motivation.manage.
  function renderAdminMotivation() {
    var host = byId("adminContent");
    return get("/api/v1/admin/motivation-texts?include_inactive=true")
      .catch(function () { return []; })
      .then(function (items) {
        var editable = has("motivation.manage");
        var createForm = editable
          ? '<form class="av-form av-form-inline" id="motivationForm">' +
            field("النص (عربي)", "Text (AR)", textInput("motTextAr", "")) +
            field("النص (إنجليزي)", "Text (EN)", textInput("motTextEn", "")) +
            field("الدور المستهدف", "Target role", textInput("motRole", "", "ph.roleCode")) +
            field("الترتيب", "Order", numInput("motOrder", 0)) +
            '<div class="av-form-actions"><button class="btn-solid" type="submit">' +
            dual("إضافة جملة", "Add sentence") + "</button></div></form>"
          : "";
        var list = items.length
          ? '<div class="av-list">' + items.map(function (m) {
              var body =
                '<div style="display:flex;align-items:center;gap:11px">' +
                '<div class="grow"><div class="t">' +
                escapeHtml(STATE.lang === "ar" ? m.text_ar : m.text_en || m.text_ar) + "</div>" +
                '<div class="s">' +
                (m.audience_role ? escapeHtml(m.audience_role) + " · " : "") +
                escapeHtml(STATE.lang === "ar" ? m.text_en || "" : m.text_ar || "") +
                "</div></div>" +
                '<span class="status ' + (m.is_active ? "ok" : "warn") + '"><i></i>' +
                (m.is_active ? dual("نشط", "Active") : dual("موقوف", "Inactive")) + "</span></div>";
              if (!editable) {
                return '<div class="av-row" style="cursor:default">' + body + "</div>";
              }
              return (
                '<div class="av-row" style="flex-direction:column;align-items:stretch;cursor:default">' +
                body +
                '<form class="av-form" id="motivationForm' + m.id + '">' +
                field("النص (عربي)", "Text (AR)", textInput("motTextAr" + m.id, m.text_ar)) +
                field("النص (إنجليزي)", "Text (EN)", textInput("motTextEn" + m.id, m.text_en)) +
                field("الدور المستهدف", "Target role", textInput("motRole" + m.id, m.audience_role || "", "ph.roleCode")) +
                field("الترتيب", "Order", numInput("motOrder" + m.id, m.sort_order)) +
                field("الحالة", "Status", selectInput("motActive" + m.id, [
                  { value: "1", label: opt("نشط", "Active") },
                  { value: "0", label: opt("موقوف", "Inactive") },
                ], m.is_active ? "1" : "0")) +
                '<div class="av-form-actions"><button class="btn-outline" type="submit" data-admin-action="save-motivation" data-id="' + m.id + '">' +
                dual("حفظ", "Save") + "</button></div></form></div>"
              );
            }).join("") + "</div>"
          : '<p class="av-empty">' + dual("لا توجد جمل.", "No sentences.") + "</p>";
        host.innerHTML =
          createForm +
          adminPanel("الجمل التحفيزية", "Motivational sentences", list) +
          adminPanel("ملخص", "Summary", '<div class="kv">' +
            kv(dual("إجمالي الجمل", "Sentences"), plainNum(items.length)) +
            kv(dual("النشطة", "Active"), plainNum(items.filter(function (m) { return m.is_active; }).length)) +
            "</div>");
      });
  }



  // ---- tab: website management (Phase 11 CMS) --------------------------
  //
  // A compact, bilingual editor for the public site. Every section reloads
  // from the API and the whole surface follows the language switch, so the
  // admin UI turns RTL/LTR with the rest of the platform. Writes are gated by
  // the same website.* permissions the API enforces; the editor never invents
  // a code the backend does not already check.
  function webVal(id) {
    var el = byId(id);
    return el ? el.value : "";
  }

  function websiteState() {
    if (!STATE.website) {
      STATE.website = { data: null, section: "overview" };
    }
    return STATE.website;
  }

  function renderAdminWebsite() {
    var host = byId("adminContent");
    var st = websiteState();
    return Promise.all([
      get("/api/v1/website/overview").catch(function () { return null; }),
      get("/api/v1/website/settings").catch(function () { return null; }),
      get("/api/v1/website/pages").catch(function () { return []; }),
      get("/api/v1/website/slides").catch(function () { return []; }),
      get("/api/v1/website/companies").catch(function () { return []; }),
      get("/api/v1/website/media").catch(function () { return []; }),
    ]).then(function (res) {
      st.data = {
        overview: res[0],
        settings: res[1],
        pages: res[2] || [],
        slides: res[3] || [],
        companies: res[4] || [],
        media: res[5] || [],
      };
      host.innerHTML = websitePanel();
      bindWebsiteTabs();
      renderWebsiteSection();
    });
  }

  function bindWebsiteTabs() {
    document.querySelectorAll("[data-web-tab]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var section = btn.getAttribute("data-web-tab");
        websiteState().section = section;
        document.querySelectorAll("[data-web-tab]").forEach(function (b) {
          b.classList.toggle("on", b === btn);
        });
        renderWebsiteSection();
      });
    });
  }

  function renderWebsiteSection() {
    var body = byId("webSection");
    if (!body) return;
    var section = websiteState().section;
    if (section === "overview") body.innerHTML = webOverviewHtml();
    else if (section === "settings") body.innerHTML = webSettingsHtml();
    else if (section === "pages") body.innerHTML = webPagesHtml();
    else if (section === "slides") body.innerHTML = webSlidesHtml();
    else if (section === "companies") body.innerHTML = webCompaniesHtml();
    else if (section === "media") body.innerHTML = webMediaHtml();
  }

  function websitePanel() {
    var st = websiteState();
    var tabs = [
      ["overview", "نظرة عامة", "Overview"],
      ["settings", "الإعدادات وSEO", "Settings & SEO"],
      ["pages", "الصفحات", "Pages"],
      ["slides", "الشرائح", "Slides"],
      ["companies", "الشركات", "Companies"],
      ["media", "الوسائط", "Media"],
    ];
    var chips = tabs
      .map(function (t) {
        return (
          '<button type="button" class="perm-cat-chip' +
          (st.section === t[0] ? " on" : "") +
          '" data-web-tab="' + t[0] + '">' + dual(t[1], t[2]) + "</button>"
        );
      })
      .join("");
    return (
      '<div class="av-panel web-panel"><h3>' +
      dual("إدارة الموقع العام", "Public website management") +
      "</h3>" +
      '<p class="av-hint">' +
      dual(
        "تحكّم في محتوى الموقع المنشور. التعديلات لا تظهر للزوار حتى يتم النشر.",
        "Manage the published site content. Changes stay hidden until published.",
      ) +
      "</p>" +
      '<div class="perm-cats" id="webTabs">' + chips + "</div>" +
      '<div id="webSection"></div></div>'
    );
  }

  function webStat(labelAr, labelEn, value) {
    return (
      '<div class="web-stat"><div class="n">' + plainNum(value) + "</div>" +
      '<div class="l">' + dual(labelAr, labelEn) + "</div></div>"
    );
  }

  function webOverviewHtml() {
    var o = websiteState().data.overview;
    if (!o) {
      return '<p class="av-empty">' + dual("تعذّر تحميل البيانات.", "Could not load data.") + "</p>";
    }
    return (
      '<div class="web-stats">' +
      webStat("الصفحات", "Pages", o.pages) +
      webStat("منشورة", "Published", o.published_pages) +
      webStat("الشرائح النشطة", "Active slides", o.active_slides) +
      webStat("الشركات الظاهرة", "Visible companies", o.visible_companies) +
      webStat("وسائط عامة", "Public media", o.public_media) +
      webStat("وسائط خاصة", "Private media", o.private_media) +
      "</div>" +
      (o.maintenance_mode
        ? '<p class="web-warning">' +
          dual("وضع الصيانة مُفعّل: الموقع العام معطّل حاليًا.", "Maintenance mode is on: the public site is offline.") +
          "</p>"
        : "")
    );
  }

  function webSettingsHtml() {
    var s = websiteState().data.settings || {};
    var editable = has("website.settings.manage");
    var dis = editable ? "" : " disabled";
    return (
      '<div class="web-form">' +
      field("اسم الموقع (عربي)", "Site name (AR)", textInput("wsNameAr", s.site_name_ar || "") ) +
      field("اسم الموقع (إنجليزي)", "Site name (EN)", textInput("wsNameEn", s.site_name_en || "") ) +
      field("البريد للتواصل", "Contact email", textInput("wsEmail", s.contact_email || "") ) +
      field("الهاتف", "Phone", textInput("wsPhone", s.contact_phone || "") ) +
      field("واتساب", "WhatsApp", textInput("wsWhatsapp", s.whatsapp_number || "") ) +
      field(
        "وضع الصيانة",
        "Maintenance mode",
        '<label class="perm-card" style="cursor:pointer"><input type="checkbox" id="wsMaintenance"' +
          (s.maintenance_mode ? " checked" : "") + dis +
          "><span class=\"perm-body\"><span class=\"perm-name\">" +
          dual("تعطيل الموقع العام مؤقتًا", "Temporarily take the public site offline") +
          "</span></span></label>",
      ) +
      (editable
        ? '<div class="perm-actions-bar"><div class="pmeta"></div><div class="pbtns">' +
          '<button type="button" class="btn-solid" data-admin-action="web-save-settings">' +
          dual("حفظ الإعدادات", "Save settings") + "</button></div></div>"
        : '<p class="av-hint">' +
          dual("لا تملك صلاحية تعديل الإعدادات.", "You cannot edit settings.") + "</p>") +
      "</div>"
    );
  }

  function webPagesHtml() {
    var pages = websiteState().data.pages || [];
    var editable = has("website.content.write");
    var publish = has("website.content.publish");
    if (!pages.length) {
      return (
        '<p class="av-empty">' +
        dual("لا توجد صفحات CMS بعد.", "No CMS pages yet.") +
        "</p>"
      );
    }
    var rows = pages
      .map(function (p) {
        var published = p.status === "published";
        return (
          '<div class="web-row"><div class="web-row-main">' +
          '<div class="web-row-title">' +
          dual(escapeHtml(p.title_ar || p.route_key), escapeHtml(p.title_en || p.route_key)) +
          "</div>" +
          '<div class="perm-code">' + escapeHtml(p.route_key) + "</div></div>" +
          '<span class="perm-badge' + (published ? "" : " danger") + '">' +
          dual(published ? "منشورة" : "مسودة", published ? "Published" : "Draft") +
          "</span>" +
          (publish
            ? '<button type="button" class="btn-outline" data-admin-action="web-toggle-page" data-id="' +
              p.id + '" data-status="' + (published ? "unpublished" : "published") + '">' +
              dual(published ? "إلغاء النشر" : "نشر", published ? "Unpublish" : "Publish") +
              "</button>"
            : "") +
          (editable
            ? '<button type="button" class="btn-outline danger" data-admin-action="web-delete-page" data-id="' +
              p.id + '">' + dual("حذف", "Delete") + "</button>"
            : "") +
          "</div>"
        );
      })
      .join("");
    return '<div class="web-list">' + rows + "</div>";
  }

  function webSlidesHtml() {
    var slides = websiteState().data.slides || [];
    if (!slides.length) {
      return '<p class="av-empty">' + dual("لا توجد شرائح.", "No slides.") + "</p>";
    }
    var rows = slides
      .map(function (s) {
        return (
          '<div class="web-row"><div class="web-row-main">' +
          '<div class="web-row-title">' +
          dual(escapeHtml(s.title_ar || "—"), escapeHtml(s.title_en || "—")) +
          "</div></div>" +
          '<span class="perm-badge' + (s.is_active ? "" : " danger") + '">' +
          dual(s.is_active ? "نشطة" : "موقوفة", s.is_active ? "Active" : "Inactive") +
          "</span></div>"
        );
      })
      .join("");
    return '<div class="web-list">' + rows + "</div>";
  }

  function webCompaniesHtml() {
    var companies = websiteState().data.companies || [];
    var editable = has("website.content.write");
    var seedBtn = editable
      ? '<button type="button" class="btn-outline" data-admin-action="web-seed-companies">' +
        dual("استيراد شركات المجموعة", "Import group companies") + "</button>"
      : "";
    if (!companies.length) {
      return (
        '<p class="av-empty">' +
        dual("لا توجد شركات. استخدم الاستيراد لإضافة القائمة المعتمدة.", "No companies. Use import to add the approved list.") +
        "</p>" + seedBtn
      );
    }
    var rows = companies
      .map(function (c) {
        return (
          '<div class="web-row"><div class="web-row-main">' +
          '<div class="web-row-title">' +
          dual(escapeHtml(c.name_ar), escapeHtml(c.name_en || c.name_ar)) +
          "</div>" +
          '<div class="perm-code">' + escapeHtml(c.slug) + "</div></div>" +
          '<span class="perm-badge' + (c.is_visible ? "" : " danger") + '">' +
          dual(c.is_visible ? "ظاهرة" : "مخفية", c.is_visible ? "Visible" : "Hidden") +
          "</span></div>"
        );
      })
      .join("");
    return '<div class="web-list">' + rows + "</div>" + seedBtn;
  }

  function webMediaHtml() {
    var media = websiteState().data.media || [];
    var editable = has("website.media.manage");
    var upload = editable
      ? '<div class="web-upload">' +
        '<input type="file" id="webMediaFile" accept="image/png,image/jpeg,image/webp,image/gif,image/avif,application/pdf">' +
        '<select class="av-select av-input" id="webMediaVisibility">' +
        '<option value="public">' + escapeHtml(STATE.lang === "ar" ? "عام" : "Public") + "</option>" +
        '<option value="private">' + escapeHtml(STATE.lang === "ar" ? "خاص" : "Private") + "</option>" +
        "</select>" +
        '<button type="button" class="btn-solid" data-admin-action="web-upload-media">' +
        dual("رفع", "Upload") + "</button></div>"
      : "";
    if (!media.length) {
      return '<p class="av-empty">' + dual("لا توجد وسائط.", "No media.") + "</p>" + upload;
    }
    var rows = media
      .map(function (m) {
        return (
          '<div class="web-row"><div class="web-row-main">' +
          '<div class="web-row-title">' + escapeHtml(m.original_name || m.storage_key) + "</div>" +
          '<div class="perm-code">' + plainNum(m.byte_size) + " bytes</div></div>" +
          '<span class="perm-badge' + (m.visibility === "public" ? "" : " danger") + '">' +
          dual(m.visibility === "public" ? "عام" : "خاص", m.visibility === "public" ? "Public" : "Private") +
          "</span>" +
          (editable
            ? '<button type="button" class="btn-outline danger" data-admin-action="web-delete-media" data-id="' +
              m.id + '">' + dual("حذف", "Delete") + "</button>"
            : "") +
          "</div>"
        );
      })
      .join("");
    return upload + '<div class="web-list">' + rows + "</div>";
  }

  // ---- tab: audit ----
  function renderAdminAudit() {
    var host = byId("adminContent");
    var page = STATE.adminAudit || (STATE.adminAudit = { limit: 40, offset: 0, total: 0, action: "", entity_type: "" });
    var query = "/api/v1/admin/audit-logs?limit=" + page.limit + "&offset=" + page.offset;
    if (page.action) query += "&action=" + encodeURIComponent(page.action);
    if (page.entity_type) query += "&entity_type=" + encodeURIComponent(page.entity_type);
    return get(query).then(function (data) {
      page.total = data.total;
      var rows = data.items.map(function (e) {
        var actor = STATE.lang === "ar" ? e.actor_name_ar || "—" : e.actor_name_en || e.actor_name_ar || "—";
        return (
          '<div class="av-row" style="cursor:default"><div class="grow"><div class="t mono">' + escapeHtml(e.action) + "</div>" +
          '<div class="s">' + escapeHtml(actor) + " · " + escapeHtml(e.entity_type || "") +
          (e.entity_id ? " #" + escapeHtml(e.entity_id) : "") + "</div></div>" +
          '<span class="s">' + fmtDateTime(e.created_at) + "</span></div>"
        );
      }).join("");
      var pager =
        '<div class="av-pager">' +
        '<button class="btn-outline" data-admin-action="audit-prev"' + (page.offset === 0 ? " disabled" : "") + ">" + dual("السابق", "Previous") + "</button>" +
        '<span class="av-pager-info">' + plainNum(page.offset + 1) + " – " + plainNum(Math.min(page.offset + page.limit, page.total)) + " / " + plainNum(page.total) + "</span>" +
        '<button class="btn-outline" data-admin-action="audit-next"' + (page.offset + page.limit >= page.total ? " disabled" : "") + ">" + dual("التالي", "Next") + "</button></div>";
      var filters =
        '<div class="av-toolbar" style="flex-wrap:wrap;gap:6px;margin-bottom:10px">' +
        '<input class="av-input" id="auditAction" placeholder="' + escAttr(STATE.lang === "ar" ? "تصفية بالإجراء (مثال: journal.posted)" : "Filter by action (e.g. journal.posted)") + '" value="' + escAttr(page.action) + '">' +
        '<input class="av-input" id="auditEntity" placeholder="' + escAttr(STATE.lang === "ar" ? "تصفية بنوع الكيان" : "Filter by entity type") + '" value="' + escAttr(page.entity_type) + '">' +
        '<button class="btn-outline" id="auditApply">' + dual("تطبيق", "Apply") + "</button>" +
        '<button class="btn-outline" id="auditClear">' + dual("مسح", "Clear") + "</button></div>";
      host.innerHTML = adminPanel("سجل النشاط", "Audit trail", filters + (rows ? '<div class="av-list">' + rows + "</div>" : '<p class="av-empty">' + dual("لا توجد سجلات.", "No entries.") + "</p>") + pager);
      var apply = byId("auditApply");
      if (apply) {
        apply.addEventListener("click", function () {
          page.action = valOf("auditAction");
          page.entity_type = valOf("auditEntity");
          page.offset = 0;
          renderAdminAudit();
        });
      }
      var clear = byId("auditClear");
      if (clear) {
        clear.addEventListener("click", function () {
          page.action = "";
          page.entity_type = "";
          page.offset = 0;
          renderAdminAudit();
        });
      }
    });
  }

  // ---- tab: integrations ----
  //
  // The signing secret is shown exactly once, in a dismissible banner after a
  // create or rotate. It is never rendered from a list read, matching the API
  // contract.
  function renderAdminIntegrations() {
    var host = byId("adminContent");
    var canManage = has("integration.manage");
    return Promise.all([
      get("/api/v1/integrations"),
      get("/api/v1/integrations/events"),
      get("/api/v1/integrations/deliveries?limit=20"),
    ]).then(function (res) {
      var endpoints = res[0] || [];
      var events = res[1] || { events: [], email_provider: "none", webhooks_enabled: false };
      var deliveries = res[2] || [];
      var createForm = canManage
        ? '<form class="av-form av-form-inline" id="hookForm">' +
          field("الاسم", "Name", textInput("hkName", "", "ph.integrationName")) +
          field("الرابط", "Endpoint URL", textInput("hkUrl", "", "ph.endpointUrl")) +
          field("النطاق", "Scope",
            selectInput("hkScope", [
              { value: "holding", label: STATE.lang === "ar" ? "القابضة" : "Holding" },
              { value: "company", label: STATE.lang === "ar" ? "شركة" : "Company" },
            ], "holding")) +
          field("الأحداث", "Events",
            '<select class="av-select av-input" id="hkEvents" multiple size="5">' +
            events.events.map(function (e) {
              return '<option value="' + escAttr(e) + '">' + escapeHtml(e) + "</option>";
            }).join("") + "</select>") +
          '<div class="av-form-actions"><button class="btn-outline" type="submit">' +
          dual("إضافة نقطة نهاية", "Add endpoint") + "</button></div></form>"
        : "";
      var secretBanner = STATE.integrationSecret
        ? '<div class="secret-banner"><div class="grow">' +
          '<div class="t">' + dual("سر التوقيع — يُعرض مرة واحدة فقط", "Signing secret — shown once only") + "</div>" +
          '<code class="mono">' + escapeHtml(STATE.integrationSecret) + "</code></div>" +
          '<button class="btn-outline" data-admin-action="hook-dismiss">' + dual("إخفاء", "Dismiss") + "</button></div>"
        : "";
      var list = endpoints.length
        ? '<div class="av-list">' + endpoints.map(function (e) {
            return (
              '<div class="av-row" style="cursor:default"><div class="grow">' +
              '<div class="t">' + escapeHtml(e.name) + "</div>" +
              '<div class="s">' + escapeHtml(e.url) + " · " + escapeHtml(e.scope) +
              " · " + dual("التسليمات ", "deliveries ") + plainNum(e.delivery_count) + "</div></div>" +
              '<span class="status ' + (e.status === "active" ? "ok" : "late") + '"><i></i>' + escapeHtml(e.status) + "</span>" +
              (canManage
                ? '<button class="btn-outline" data-admin-action="hook-rotate" data-id="' + e.id + '">' + dual("تجديد السر", "Rotate secret") + "</button>" +
                  (e.status === "active"
                    ? '<button class="btn-outline" data-admin-action="hook-disable" data-id="' + e.id + '">' + dual("تعطيل", "Disable") + "</button>"
                    : "")
                : "") +
              "</div>"
            );
          }).join("") + "</div>"
        : '<p class="av-empty">' + dual("لا توجد نقاط نهاية.", "No endpoints yet.") + "</p>";
      var deliveryList = deliveries.length
        ? '<div class="av-list">' + deliveries.map(function (d) {
            return (
              '<div class="av-row" style="cursor:default"><div class="grow">' +
              '<div class="t mono">' + escapeHtml(d.event_type) + "</div>" +
              '<div class="s">' + fmtDateTime(d.created_at) + (d.error ? " · " + escapeHtml(d.error) : "") + "</div></div>" +
              '<span class="status ' + (d.status === "delivered" ? "ok" : d.status === "failed" ? "late" : "warn") + '"><i></i>' + escapeHtml(d.status) + "</span></div>"
            );
          }).join("") + "</div>"
        : '<p class="av-empty">' + dual("لا توجد تسليمات.", "No deliveries yet.") + "</p>";
      var env = '<div class="kv">' +
        kv(dual("مزوّد البريد", "Email provider"), escapeHtml(events.email_provider)) +
        kv(dual("الويب هوكس", "Webhooks"), dual(events.webhooks_enabled ? "مُفعّل" : "معطّل", events.webhooks_enabled ? "enabled" : "disabled")) +
        "</div>";
      host.className = "av-grid cols-1";
      host.innerHTML =
        secretBanner +
        adminPanel("نقاط النهاية", "Endpoints", createForm + list) +
        '<div class="av-grid cols-2">' +
        adminPanel("سجل التسليمات", "Delivery log", deliveryList) +
        adminPanel("حالة التكامل", "Integration status", env) +
        "</div>";
    }).catch(function (err) {
      host.innerHTML = errorHtml(errText(err));
    });
  }

  // ---- tab: form builder ----
  function renderAdminBuilder() {
    var host = byId("adminContent");
    return ensureForms().then(function (forms) {
      var canCreate = has("form.create");
      var createForm = canCreate
        ? '<form class="av-form av-form-inline" id="builderForm">' +
          field("الكود", "Code", textInput("bfCode", "", "ph.formCode")) +
          field("الاسم (عربي)", "Name (AR)", textInput("bfNameAr", "")) +
          field("الاسم (إنجليزي)", "Name (EN)", textInput("bfNameEn", "")) +
          field("النطاق", "Scope",
            selectInput("bfScope", [
              { value: "holding", label: STATE.lang === "ar" ? "القابضة" : "Holding" },
              { value: "company", label: STATE.lang === "ar" ? "شركة" : "Company" },
            ], "holding")) +
          '<div class="av-form-actions"><button class="btn-outline" type="submit" data-admin-action="builder-create">' +
          dual("إنشاء نموذج", "Create form") + "</button></div></form>"
        : "";
      var list = forms.length
        ? '<div class="av-list">' + forms.map(function (f) {
            var statusCls = f.status === "published" ? "ok" : f.status === "archived" ? "warn" : "late";
            return (
              '<div class="av-row" style="cursor:default"><div class="grow"><div class="t">' +
              escapeHtml(companyName(f)) + "</div>" +
              '<div class="s">' + escapeHtml(f.code) + " · " + escapeHtml(f.scope) +
              " · " + dual("الحقول", "fields") + " " + plainNum(f.field_count || 0) + "</div></div>" +
              '<span class="status ' + statusCls + '"><i></i>' + escapeHtml(f.status) + "</span>" +
              '<button class="btn-outline" data-admin-action="builder-open" data-id="' + f.id + '">' +
              dual("إدارة", "Manage") + "</button></div>"
            );
          }).join("") + "</div>"
        : '<p class="av-empty">' + dual("لا توجد نماذج.", "No forms yet.") + "</p>";
      host.innerHTML = adminPanel("منشئ النماذج الديناميكية", "Dynamic form builder", createForm + list);
    });
  }

  function openFormBuilder(formId) {
    Promise.all([
      get("/api/v1/forms/" + formId),
      get("/api/v1/forms/" + formId + "/current").catch(function () { return null; }),
    ]).then(function (res) {
      var form = res[0];
      var version = res[1];
      var fields = version && version.fields ? version.fields : [];
      var reqs = version && version.requirements ? version.requirements : [];
      var canEdit = has("form.update");
      var canPublish = has("form.publish");
      var body =
        '<div class="note-block"><span class="lbl">' + dual("الكود", "Code") + "</span>" +
        escapeHtml(form.code) + " · " + dual("الإصدار", "Version") + " " +
        plainNum(form.latest_version_number || 1) + "</div>" +
        '<h3 style="font-size:12.5px;margin:14px 0 8px">' + dual("الحقول", "Fields") + "</h3>" +
        (fields.length
          ? fields.map(function (f) {
              return '<div class="av-row" style="cursor:default"><div class="grow"><div class="t">' +
                escapeHtml(STATE.lang === "ar" ? f.label_ar : f.label_en) + "</div>" +
                '<div class="s mono">' + escapeHtml(f.key) + " · " + escapeHtml(f.field_type) +
                (f.is_required ? " · " + dual("إلزامي", "required") : "") + "</div></div>" +
                (canEdit ? '<button class="btn-outline danger" data-field-del="' + f.id + '">&times;</button>' : "") +
                "</div>";
            }).join("")
          : '<p class="av-empty">' + dual("لا توجد حقول بعد.", "No fields yet.") + "</p>") +
        (canEdit ? addFieldForm() : "") +
        '<h3 style="font-size:12.5px;margin:16px 0 8px">' + dual("المتطلبات", "Requirements") + "</h3>" +
        (reqs.length
          ? reqs.map(function (r) {
              return '<div class="av-row" style="cursor:default"><div class="grow"><div class="t">' +
                escapeHtml(STATE.lang === "ar" ? r.name_ar : r.name_en) + "</div>" +
                '<div class="s">' + escapeHtml(r.requirement_type) +
                (r.is_mandatory ? " · " + dual("إلزامي", "mandatory") : "") + "</div></div>" +
                (has("requirement.manage") ? '<button class="btn-outline danger" data-req-del="' + r.id + '">&times;</button>' : "") +
                "</div>";
            }).join("")
          : '<p class="av-empty">' + dual("لا توجد متطلبات بعد.", "No requirements yet.") + "</p>") +
        (has("requirement.manage") ? addRequirementForm(formId) : "");

      openModal({
        title: dual("إدارة النموذج", "Manage form") + " — " + escapeHtml(companyName(form)),
        wide: true,
        body: body,
        footer:
          (canPublish
            ? '<button class="btn-solid gold" id="fbPublish">' + dual("نشر", "Publish") + "</button>"
            : "") +
          '<button class="btn-outline" id="fbClose">' + dual("إغلاق", "Close") + "</button>",
        onMount: function (root) {
          root.querySelector("#fbClose").addEventListener("click", closeModal);
          var pub = root.querySelector("#fbPublish");
          if (pub) {
            pub.addEventListener("click", function () {
              busy(pub, true);
              post("/api/v1/forms/" + formId + "/publish", {})
                .then(function () {
                  toast(STATE.lang === "ar" ? "تم نشر النموذج." : "Form published.", "ok");
                  closeModal();
                  STATE.loaded.forms = false;
                  renderAdminBuilder();
                })
                .catch(function (err) {
                  toast(errText(err), "err");
                  busy(pub, false);
                });
            });
          }
          bindFieldForm(root, formId, function () { closeModal(); openFormBuilder(formId); });
          var reqAdd = root.querySelector("#arAdd");
          if (reqAdd) {
            reqAdd.addEventListener("click", function () {
              var payload = {
                key: root.querySelector("#arKey").value.trim(),
                requirement_type: root.querySelector("#arType").value,
                name_ar: root.querySelector("#arNameAr").value.trim() || root.querySelector("#arKey").value.trim(),
                name_en: root.querySelector("#arNameEn").value.trim() || root.querySelector("#arKey").value.trim(),
                is_mandatory: root.querySelector("#arMandatory").value === "1",
              };
              busy(reqAdd, true);
              post("/api/v1/forms/" + formId + "/requirements", payload)
                .then(function () { closeModal(); openFormBuilder(formId); })
                .catch(function (err) {
                  toast(errText(err), "err");
                  busy(reqAdd, false);
                });
            });
          }
          root.querySelectorAll("[data-field-del]").forEach(function (b) {
            b.addEventListener("click", function () {
              del("/api/v1/forms/" + formId + "/fields/" + b.getAttribute("data-field-del"))
                .then(function () { closeModal(); openFormBuilder(formId); })
                .catch(function (err) { toast(errText(err), "err"); });
            });
          });
          root.querySelectorAll("[data-req-del]").forEach(function (b) {
            b.addEventListener("click", function () {
              del("/api/v1/forms/" + formId + "/requirements/" + b.getAttribute("data-req-del"))
                .then(function () { closeModal(); openFormBuilder(formId); })
                .catch(function (err) { toast(errText(err), "err"); });
            });
          });
        },
      });
    }).catch(function (err) {
      toast(errText(err), "err");
    });
  }

  function addFieldForm() {
    return (
      '<div class="av-form av-form-inline" style="margin-top:10px">' +
      field("المفتاح", "Key", textInput("afKey", "", "ph.fieldKey")) +
      field("النوع", "Type", selectInput("afType", [
        { value: "short_text", label: "Short text" },
        { value: "long_text", label: "Long text" },
        { value: "decimal", label: "Decimal" },
        { value: "integer", label: "Integer" },
        { value: "date", label: "Date" },
        { value: "boolean", label: "Boolean" },
        { value: "select", label: "Select (JSON options)" },
      ], "short_text")) +
      field("التسمية (عربي)", "Label (AR)", textInput("afLabelAr", "")) +
      field("التسمية (إنجليزي)", "Label (EN)", textInput("afLabelEn", "")) +
      field("إلزامي", "Required", selectInput("afRequired", [
        { value: "0", label: STATE.lang === "ar" ? "لا" : "No" },
        { value: "1", label: STATE.lang === "ar" ? "نعم" : "Yes" },
      ], "0")) +
      '<div class="av-form-actions"><button class="btn-outline" id="afAdd">' +
      dual("إضافة حقل", "Add field") + "</button></div></div>"
    );
  }

  function bindFieldForm(root, formId, done) {
    var btn = root.querySelector("#afAdd");
    if (!btn) return;
    btn.addEventListener("click", function () {
      var payload = {
        key: root.querySelector("#afKey").value.trim(),
        field_type: root.querySelector("#afType").value,
        label_ar: root.querySelector("#afLabelAr").value.trim() || root.querySelector("#afKey").value.trim(),
        label_en: root.querySelector("#afLabelEn").value.trim() || root.querySelector("#afKey").value.trim(),
        is_required: root.querySelector("#afRequired").value === "1",
      };
      busy(btn, true);
      post("/api/v1/forms/" + formId + "/fields", payload)
        .then(function () {
          toast(STATE.lang === "ar" ? "تمت إضافة الحقل." : "Field added.", "ok");
          done();
        })
        .catch(function (err) {
          toast(errText(err), "err");
          busy(btn, false);
        });
    });
  }

  function addRequirementForm() {
    return (
      '<div class="av-form av-form-inline" style="margin-top:10px">' +
      field("المفتاح", "Key", textInput("arKey", "", "ph.requirementKey")) +
      field("النوع", "Type", selectInput("arType", [
        { value: "document", label: STATE.lang === "ar" ? "مستند" : "Document" },
        { value: "field_value", label: STATE.lang === "ar" ? "قيمة حقل" : "Field value" },
      ], "document")) +
      field("الاسم (عربي)", "Name (AR)", textInput("arNameAr", "")) +
      field("الاسم (إنجليزي)", "Name (EN)", textInput("arNameEn", "")) +
      field("إلزامي", "Mandatory", selectInput("arMandatory", [
        { value: "1", label: STATE.lang === "ar" ? "نعم" : "Yes" },
        { value: "0", label: STATE.lang === "ar" ? "لا" : "No" },
      ], "1")) +
      '<div class="av-form-actions"><button class="btn-outline" id="arAdd">' +
      dual("إضافة متطلب", "Add requirement") + "</button></div></div>"
    );
  }

  // ---- tab: workflows ----
  function renderAdminWorkflows() {
    var host = byId("adminContent");
    return Promise.all([
      get("/api/v1/workflows").catch(function () { return []; }),
      ensureForms(),
    ]).then(function (res) {
      var workflows = res[0];
      var forms = res[1];
      var canCreate = has("workflow.create");
      var createForm = canCreate
        ? '<form class="av-form av-form-inline" id="wfForm">' +
          field("الكود", "Code", textInput("wfCode", "", "ph.workflowCode")) +
          field("الاسم (عربي)", "Name (AR)", textInput("wfNameAr", "")) +
          field("الاسم (إنجليزي)", "Name (EN)", textInput("wfNameEn", "")) +
          field("النموذج", "Form", selectInput("wfFormId", forms.map(function (f) {
            return { value: f.id, label: companyName(f) };
          }), forms.length ? forms[0].id : "")) +
          '<div class="av-form-actions"><button class="btn-outline" type="submit" data-admin-action="workflow-create">' +
          dual("إنشاء مسار", "Create workflow") + "</button></div></form>"
        : "";
      var list = workflows.length
        ? '<div class="av-list">' + workflows.map(function (w) {
            var statusCls = w.status === "published" ? "ok" : w.status === "archived" ? "warn" : "late";
            return (
              '<div class="av-row" style="cursor:default"><div class="grow"><div class="t">' +
              escapeHtml(companyName(w)) + "</div>" +
              '<div class="s">' + escapeHtml(w.code) + " · " + dual("النموذج", "form") + ": " +
              escapeHtml(STATE.lang === "ar" ? w.form_name_ar || "" : w.form_name_en || w.form_name_ar || "") +
              " · " + dual("الخطوات", "steps") + " " + plainNum(w.step_count || 0) + "</div></div>" +
              '<span class="status ' + statusCls + '"><i></i>' + escapeHtml(w.status) + "</span>" +
              '<button class="btn-outline" data-admin-action="workflow-open" data-id="' + w.id + '">' +
              dual("إدارة", "Manage") + "</button></div>"
            );
          }).join("") + "</div>"
        : '<p class="av-empty">' + dual("لا توجد مسارات.", "No workflows yet.") + "</p>";
      host.innerHTML = adminPanel("مسارات الموافقات", "Approval workflows", createForm + list);
    });
  }

  function openWorkflowBuilder(workflowId) {
    Promise.all([
      get("/api/v1/workflows/" + workflowId),
      get("/api/v1/workflows/" + workflowId + "/current").catch(function () { return null; }),
      get("/api/v1/admin/roles").catch(function () { return []; }),
    ]).then(function (res) {
      var workflow = res[0];
      var version = res[1];
      var roles = res[2];
      var steps = version && version.steps ? version.steps : [];
      var canEdit = has("workflow.update");
      var body =
        '<div class="note-block"><span class="lbl">' + dual("الكود", "Code") + "</span>" +
        escapeHtml(workflow.code) + " · " + dual("يسمح بالتجاوز", "Override allowed") + ": " +
        (workflow.allow_requirement_override ? dual("نعم", "Yes") : dual("لا", "No")) + "</div>" +
        '<h3 style="font-size:12.5px;margin:14px 0 8px">' + dual("الخطوات", "Steps") + "</h3>" +
        (steps.length
          ? steps.map(function (s) {
              var who = s.assignment_type === "role"
                ? (s.assignment_config && s.assignment_config.role_code) || ""
                : s.assignment_type;
              return '<div class="av-row" style="cursor:default">' +
                '<div class="co-dot" style="width:30px;height:30px;border-radius:9px;font-size:11px">' +
                s.display_order + "</div>" +
                '<div class="grow"><div class="t">' + escapeHtml(STATE.lang === "ar" ? s.name_ar : s.name_en) + "</div>" +
                '<div class="s mono">' + escapeHtml(s.assignment_type) + " · " + escapeHtml(who) + "</div></div>" +
                (canEdit ? '<button class="btn-outline danger" data-step-del="' + s.id + '">&times;</button>' : "") +
                "</div>";
            }).join("")
          : '<p class="av-empty">' + dual("لا توجد خطوات بعد.", "No steps yet.") + "</p>") +
        (canEdit ? addStepForm(roles) : "");

      openModal({
        title: dual("إدارة المسار", "Manage workflow") + " — " + escapeHtml(companyName(workflow)),
        wide: true,
        body: body,
        footer:
          (has("workflow.publish")
            ? '<button class="btn-solid gold" id="wfPublish">' + dual("نشر", "Publish") + "</button>"
            : "") +
          '<button class="btn-outline" id="wfClose">' + dual("إغلاق", "Close") + "</button>",
        onMount: function (root) {
          root.querySelector("#wfClose").addEventListener("click", closeModal);
          var pub = root.querySelector("#wfPublish");
          if (pub) {
            pub.addEventListener("click", function () {
              busy(pub, true);
              post("/api/v1/workflows/" + workflowId + "/publish", {})
                .then(function () {
                  toast(STATE.lang === "ar" ? "تم نشر المسار." : "Workflow published.", "ok");
                  closeModal();
                  renderAdminWorkflows();
                })
                .catch(function (err) {
                  toast(errText(err), "err");
                  busy(pub, false);
                });
            });
          }
          var addBtn = root.querySelector("#wsAdd");
          if (addBtn) {
            addBtn.addEventListener("click", function () {
              var type = root.querySelector("#wsType").value;
              var cfg = {};
              if (type === "role") cfg.role_code = root.querySelector("#wsRole").value;
              var payload = {
                key: root.querySelector("#wsKey").value.trim(),
                name_ar: root.querySelector("#wsNameAr").value.trim() || root.querySelector("#wsKey").value.trim(),
                name_en: root.querySelector("#wsNameEn").value.trim() || root.querySelector("#wsKey").value.trim(),
                assignment_type: type,
                assignment_config: cfg,
              };
              busy(addBtn, true);
              post("/api/v1/workflows/" + workflowId + "/steps", payload)
                .then(function () { closeModal(); openWorkflowBuilder(workflowId); })
                .catch(function (err) {
                  toast(errText(err), "err");
                  busy(addBtn, false);
                });
            });
          }
          root.querySelectorAll("[data-step-del]").forEach(function (b) {
            b.addEventListener("click", function () {
              del("/api/v1/workflows/" + workflowId + "/steps/" + b.getAttribute("data-step-del"))
                .then(function () { closeModal(); openWorkflowBuilder(workflowId); })
                .catch(function (err) { toast(errText(err), "err"); });
            });
          });
        },
      });
    }).catch(function (err) {
      toast(errText(err), "err");
    });
  }

  function addStepForm(roles) {
    return (
      '<div class="av-form av-form-inline" style="margin-top:10px">' +
      field("المفتاح", "Key", textInput("wsKey", "", "manager")) +
      field("النوع", "Assignment", selectInput("wsType", [
        { value: "company_manager", label: STATE.lang === "ar" ? "مدير الشركة" : "Company manager" },
        { value: "role", label: STATE.lang === "ar" ? "دور" : "Role" },
        { value: "submitter_manager", label: STATE.lang === "ar" ? "مدير مقدم الطلب" : "Submitter's manager" },
        { value: "department_manager", label: STATE.lang === "ar" ? "مدير القسم" : "Department manager" },
      ], "company_manager")) +
      field("الدور", "Role", selectInput("wsRole", roles.map(function (r) {
        return { value: r.code, label: STATE.lang === "ar" ? r.name_ar : r.name_en };
      }))) +
      field("الاسم (عربي)", "Name (AR)", textInput("wsNameAr", "")) +
      field("الاسم (إنجليزي)", "Name (EN)", textInput("wsNameEn", "")) +
      '<div class="av-form-actions"><button class="btn-outline" id="wsAdd">' +
      dual("إضافة خطوة", "Add step") + "</button></div></div>"
    );
  }

  // ---- admin event handling ----
  function onAdminClick(e) {
    var el = e.target.closest ? e.target.closest("[data-admin-action]") : null;
    if (!el) return;
    var action = el.getAttribute("data-admin-action");
    var id = el.getAttribute("data-id");

    if (action === "users-prev") { STATE.adminUsers.offset = Math.max(0, STATE.adminUsers.offset - STATE.adminUsers.limit); return renderAdminUsers(); }
    if (action === "users-next") { STATE.adminUsers.offset += STATE.adminUsers.limit; return renderAdminUsers(); }
    if (action === "audit-prev") { STATE.adminAudit.offset = Math.max(0, STATE.adminAudit.offset - STATE.adminAudit.limit); return renderAdminAudit(); }
    if (action === "audit-next") { STATE.adminAudit.offset += STATE.adminAudit.limit; return renderAdminAudit(); }

    if (action === "builder-open") return openFormBuilder(parseInt(id, 10));
    if (action === "workflow-open") return openWorkflowBuilder(parseInt(id, 10));

    if (action === "upload-logo") {
      var fileEl = byId("brandLogoFile");
      var file = fileEl && fileEl.files ? fileEl.files[0] : null;
      if (!file) {
        toast(STATE.lang === "ar" ? "اختر ملف الشعار أولًا." : "Choose a logo file first.", "warn");
        return;
      }
      busy(el, true);
      return api.upload("/api/v1/admin/branding/logo", file, null)
        .then(function () {
          toast(STATE.lang === "ar" ? "تم رفع الشعار." : "Logo uploaded.", "ok");
          applyPlatformLogo();
          return renderAdminStructure();
        })
        .catch(function (err) {
          toast(errText(err), "err");
          busy(el, false);
        });
    }
    if (action === "remove-logo") {
      busy(el, true);
      return del("/api/v1/admin/branding/logo")
        .then(function () {
          toast(STATE.lang === "ar" ? "تمت إزالة الشعار." : "Logo removed.", "ok");
          applyPlatformLogo();
          return renderAdminStructure();
        })
        .catch(function (err) {
          toast(errText(err), "err");
          busy(el, false);
        });
    }

    if (action === "hook-dismiss") {
      STATE.integrationSecret = null;
      return renderAdminIntegrations();
    }
    if (action === "hook-rotate") {
      return post("/api/v1/integrations/" + id + "/rotate-secret", {}).then(function (res) {
        STATE.integrationSecret = res.signing_secret;
        toast(STATE.lang === "ar" ? "تم تجديد السر." : "Secret rotated.", "ok");
        return renderAdminIntegrations();
      }).catch(adminError);
    }
    if (action === "hook-disable") {
      return post("/api/v1/integrations/" + id + "/disable", {}).then(function () {
        toast(STATE.lang === "ar" ? "تم تعطيل نقطة النهاية." : "Endpoint disabled.", "ok");
        return renderAdminIntegrations();
      }).catch(adminError);
    }

    // ---- website management (Phase 11 CMS) ----
    if (action === "web-save-settings") {
      busy(el, true);
      return patch("/api/v1/website/settings", {
        site_name_ar: webVal("wsNameAr"),
        site_name_en: webVal("wsNameEn"),
        contact_email: webVal("wsEmail"),
        contact_phone: webVal("wsPhone"),
        whatsapp_number: webVal("wsWhatsapp"),
        maintenance_mode: !!(byId("wsMaintenance") && byId("wsMaintenance").checked),
      })
        .then(function () {
          toast(dual("تم حفظ الإعدادات.", "Settings saved."), "ok");
          return renderAdminWebsite();
        })
        .catch(function (err) {
          toast(errText(err), "err");
          busy(el, false);
        });
    }
    if (action === "web-toggle-page") {
      var target = el.getAttribute("data-status");
      busy(el, true);
      return post("/api/v1/website/pages/" + id + "/" + (target === "published" ? "publish" : "unpublish"), {})
        .then(function () {
          toast(dual("تم تحديث حالة النشر.", "Publish state updated."), "ok");
          return renderAdminWebsite();
        })
        .catch(function (err) {
          toast(errText(err), "err");
          busy(el, false);
        });
    }
    if (action === "web-delete-page") {
      return confirmDialog({
        title: dual("حذف الصفحة", "Delete page"),
        message: STATE.lang === "ar" ? "سيتم حذف هذه الصفحة نهائيًا." : "This page will be permanently deleted.",
        danger: true,
      }).then(function (ok) {
        if (!ok) return;
        return del("/api/v1/website/pages/" + id).then(function () {
          toast(dual("تم حذف الصفحة.", "Page deleted."), "ok");
          return renderAdminWebsite();
        }).catch(adminError);
      });
    }
    if (action === "web-seed-companies") {
      busy(el, true);
      return post("/api/v1/website/companies/seed", {})
        .then(function (res) {
          toast(
            dual("تم استيراد " + plainNum(res.created) + " شركة.", "Imported " + plainNum(res.created) + " companies."),
            "ok",
          );
          return renderAdminWebsite();
        })
        .catch(function (err) {
          toast(errText(err), "err");
          busy(el, false);
        });
    }
    if (action === "web-upload-media") {
      var mediaEl = byId("webMediaFile");
      var mediaFile = mediaEl && mediaEl.files ? mediaEl.files[0] : null;
      if (!mediaFile) {
        toast(STATE.lang === "ar" ? "اختر ملفًا أولًا." : "Choose a file first.", "warn");
        return;
      }
      var visEl = byId("webMediaVisibility");
      busy(el, true);
      return api.upload("/api/v1/website/media", mediaFile, {
        visibility: visEl ? visEl.value : "public",
      })
        .then(function () {
          toast(dual("تم رفع الملف.", "File uploaded."), "ok");
          return renderAdminWebsite();
        })
        .catch(function (err) {
          toast(errText(err), "err");
          busy(el, false);
        });
    }
    if (action === "web-delete-media") {
      return confirmDialog({
        title: dual("حذف الوسيط", "Delete media"),
        message: STATE.lang === "ar" ? "سيتم حذف الملف نهائيًا." : "The file will be permanently deleted.",
        danger: true,
      }).then(function (ok) {
        if (!ok) return;
        return del("/api/v1/website/media/" + id).then(function () {
          toast(dual("تم حذف الوسيط.", "Media deleted."), "ok");
          return renderAdminWebsite();
        }).catch(adminError);
      });
    }

    if (action === "end-stake") {
      return confirmDialog({
        title: dual("إنهاء الحصة", "End stake"),
        message: STATE.lang === "ar" ? "سيتم إنهاء هذه الحصة مع الحفاظ على سجلها." : "This stake will be closed while its history is preserved.",
        danger: true,
      }).then(function (ok) {
        if (!ok) return;
        return post("/api/v1/admin/ownerships/" + id + "/end", {}).then(function () {
          toast(STATE.lang === "ar" ? "تم إنهاء الحصة." : "Stake ended.", "ok");
          return renderAdminStructure();
        });
      });
    }

    if (action === "toggle-user") {
      var active = el.getAttribute("data-active") === "1";
      return patch("/api/v1/admin/users/" + id, { is_active: !active }).then(function () {
        toast(STATE.lang === "ar" ? "تم تحديث المستخدم." : "User updated.", "ok");
        return renderAdminUsers();
      }).catch(adminError);
    }

    if (action === "save-user") {
      var roleCode = byId("uRole" + id);
      var deptId = byId("uDept" + id);
      var payload = {};
      if (roleCode) payload.role_code = roleCode.value;
      if (deptId && deptId.value) payload.department_id = parseInt(deptId.value, 10);
      return patch("/api/v1/admin/users/" + id, payload).then(function () {
        toast(STATE.lang === "ar" ? "تم الحفظ." : "Saved.", "ok");
        return renderAdminUsers();
      }).catch(adminError);
    }

    if (action === "role-open") {
      var rc = el.getAttribute("data-code");
      var st = permState();
      if (st.dirty) {
        var proceed = window.confirm(
          STATE.lang === "ar"
            ? "لديك تغييرات غير محفوظة. هل تريد المتابعة دون حفظها؟"
            : "You have unsaved changes. Continue without saving?",
        );
        if (!proceed) return;
      }
      st.roleCode = rc;
      st.query = "";
      st.category = "all";
      return renderAdminRoles();
    }

    if (action === "perm-cat") {
      var stc = permState();
      stc.category = el.getAttribute("data-cat") || "all";
      document.querySelectorAll('[data-admin-action="perm-cat"]').forEach(function (b) {
        b.classList.toggle("on", b.getAttribute("data-cat") === stc.category);
      });
      renderPermGroups();
      return;
    }

    if (action === "perm-selectall") {
      var sts = permState();
      var catKey = el.getAttribute("data-cat");
      var group = document.querySelector(
        '#permGroups .perm-group[data-cat="' + catKey + '"]',
      );
      if (!group) return;
      var boxes = group.querySelectorAll("[data-perm-code]");
      var allOn = true;
      boxes.forEach(function (b) {
        if (!b.checked) allOn = false;
      });
      boxes.forEach(function (b) {
        b.checked = !allOn;
        sts.selected[b.getAttribute("data-perm-code")] = b.checked;
        var card = b.closest(".perm-card");
        if (card) card.classList.toggle("on", b.checked);
      });
      updatePermSummary();
      updateGroupCounts();
      return;
    }

    if (action === "perm-cancel") {
      var stcancel = permState();
      stcancel.selected = Object.assign({}, stcancel.original);
      stcancel.query = "";
      stcancel.category = "all";
      var editor = byId("permEditor");
      if (editor) {
        var search = byId("permSearch");
        if (search) search.value = "";
      }
      document.querySelectorAll('[data-admin-action="perm-cat"]').forEach(function (b) {
        b.classList.toggle("on", b.getAttribute("data-cat") === "all");
      });
      renderPermGroups();
      toast(STATE.lang === "ar" ? "تم التراجع عن التغييرات." : "Changes discarded.", "ok");
      return;
    }

    if (action === "perm-save") {
      var stsave = permState();
      var editorEl = byId("permEditor");
      if (!editorEl) return;
      var roleCode = editorEl.getAttribute("data-role");
      var perms = [];
      (stsave.catalogue.permissions || []).forEach(function (p) {
        if (stsave.selected[p.code]) perms.push(p.code);
      });
      busy(el, true);
      return put(
        "/api/v1/admin/roles/" + encodeURIComponent(roleCode) + "/permissions",
        { permissions: perms },
      )
        .then(function () {
          stsave.original = Object.assign({}, stsave.selected);
          toast(STATE.lang === "ar" ? "تم حفظ الصلاحيات." : "Permissions saved.", "ok");
          return renderAdminRoles();
        })
        .catch(function (err) {
          adminError(err);
          busy(el, false);
        });
    }

    if (action === "save-sector") {
      var scid = parseInt(id, 10);
      return patch("/api/v1/admin/sectors/" + scid, {
        name_ar: byId("scNameAr" + scid) ? byId("scNameAr" + scid).value : undefined,
        name_en: byId("scNameEn" + scid) ? byId("scNameEn" + scid).value : undefined,
        status: byId("scStatus" + scid) ? byId("scStatus" + scid).value : undefined,
        sort_order: byId("scOrder" + scid) ? parseInt(byId("scOrder" + scid).value, 10) : undefined,
      }).then(function () {
        toast(STATE.lang === "ar" ? "تم حفظ القطاع." : "Sector saved.", "ok");
        return renderAdminSectors();
      }).catch(adminError);
    }

    if (action === "save-position") {
      var pid = parseInt(id, 10);
      var parentVal = byId("posParent" + pid) ? byId("posParent" + pid).value : "";
      var deptVal = byId("posDept" + pid) ? byId("posDept" + pid).value : "";
      return patch("/api/v1/admin/positions/" + pid, {
        title_ar: byId("posTitleAr" + pid) ? byId("posTitleAr" + pid).value : undefined,
        title_en: byId("posTitleEn" + pid) ? byId("posTitleEn" + pid).value : undefined,
        department_id: deptVal ? parseInt(deptVal, 10) : undefined,
        reports_to_position_id: parentVal ? parseInt(parentVal, 10) : undefined,
        status: byId("posStatus" + pid) ? byId("posStatus" + pid).value : undefined,
      }).then(function () {
        toast(STATE.lang === "ar" ? "تم حفظ المنصب." : "Position saved.", "ok");
        return renderAdminPositions();
      }).catch(adminError);
    }

    if (action === "save-motivation") {
      var mid = parseInt(id, 10);
      return patch("/api/v1/admin/motivation-texts/" + mid, {
        text_ar: byId("motTextAr" + mid) ? byId("motTextAr" + mid).value : undefined,
        text_en: byId("motTextEn" + mid) ? byId("motTextEn" + mid).value : undefined,
        audience_role: byId("motRole" + mid) ? (byId("motRole" + mid).value || null) : undefined,
        sort_order: byId("motOrder" + mid) ? parseInt(byId("motOrder" + mid).value, 10) : undefined,
        is_active: byId("motActive" + mid) ? byId("motActive" + mid).value === "1" : undefined,
      }).then(function () {
        toast(STATE.lang === "ar" ? "تم حفظ الجملة." : "Sentence saved.", "ok");
        return renderAdminMotivation();
      }).catch(adminError);
    }

    if (action === "save-company") {
      var cid = parseInt(id, 10);
      return patch("/api/v1/companies/" + cid, {
        name_ar: byId("cNameAr" + cid) ? byId("cNameAr" + cid).value : undefined,
        name_en: byId("cNameEn" + cid) ? byId("cNameEn" + cid).value : undefined,
        sector: byId("cSector" + cid) ? byId("cSector" + cid).value : undefined,
        currency: byId("cCurrency" + cid) ? byId("cCurrency" + cid).value : undefined,
        country: byId("cCountry" + cid) ? byId("cCountry" + cid).value : undefined,
      }).then(function () {
        STATE.loaded.companies = false;
        toast(STATE.lang === "ar" ? "تم حفظ الشركة." : "Company saved.", "ok");
        return renderAdminCompanies();
      }).catch(adminError);
    }
  }

  function onAdminSubmit(e) {
    var form = e.target;
    if (!form || !form.getAttribute) return;
    if (form.id === "hookForm") {
      e.preventDefault();
      var selected = [];
      var select = byId("hkEvents");
      if (select) {
        Array.prototype.forEach.call(select.options, function (o) {
          if (o.selected) selected.push(o.value);
        });
      }
      if (!selected.length) {
        toast(STATE.lang === "ar" ? "اختر حدثاً واحداً على الأقل." : "Select at least one event.", "warn");
        return;
      }
      var payload = {
        name: byId("hkName").value.trim(),
        url: byId("hkUrl").value.trim(),
        scope: byId("hkScope").value,
        subscribed_events: selected,
      };
      return post("/api/v1/integrations", payload)
        .then(function (res) {
          STATE.integrationSecret = res.signing_secret;
          toast(STATE.lang === "ar" ? "تمت إضافة نقطة النهاية." : "Endpoint added.", "ok");
          return renderAdminIntegrations();
        })
        .catch(adminError);
    }
    if (form.id === "builderForm") {
      e.preventDefault();
      return post("/api/v1/forms", {
        code: byId("bfCode").value.trim(),
        name_ar: byId("bfNameAr").value.trim(),
        name_en: byId("bfNameEn").value.trim(),
        scope: byId("bfScope").value,
      }).then(function (created) {
        STATE.loaded.forms = false;
        toast(STATE.lang === "ar" ? "تم إنشاء النموذج." : "Form created.", "ok");
        return renderAdminBuilder().then(function () { openFormBuilder(created.id); });
      }).catch(adminError);
    }
    if (form.id === "wfForm") {
      e.preventDefault();
      return post("/api/v1/workflows", {
        code: byId("wfCode").value.trim(),
        name_ar: byId("wfNameAr").value.trim(),
        name_en: byId("wfNameEn").value.trim(),
        form_id: parseInt(byId("wfFormId").value, 10),
      }).then(function (created) {
        toast(STATE.lang === "ar" ? "تم إنشاء المسار." : "Workflow created.", "ok");
        return renderAdminWorkflows().then(function () { openWorkflowBuilder(created.id); });
      }).catch(adminError);
    }
    if (form.id === "holdingForm") {
      e.preventDefault();
      return patch("/api/v1/admin/holding", {
        legal_name_ar: byId("hLegalAr").value,
        legal_name_en: byId("hLegalEn").value,
        commercial_registration: byId("hCr").value,
        tax_number: byId("hTax").value,
        default_currency: byId("hCurrency").value,
        contact_email: byId("hEmail").value,
        phone: byId("hPhone").value,
      }).then(function () {
        toast(STATE.lang === "ar" ? "تم حفظ بيانات القابضة." : "Holding profile saved.", "ok");
        return renderAdminStructure();
      }).catch(adminError);
    }
    if (form.id === "stakeForm") {
      e.preventDefault();
      var owner = byId("stOwner").value;
      var payload = {
        owned_company_id: parseInt(byId("stOwned").value, 10),
        ownership_percentage: parseFloat(byId("stPct").value),
        effective_from: byId("stFrom").value,
      };
      if (owner) payload.owner_company_id = parseInt(owner, 10);
      return post("/api/v1/admin/ownerships", payload).then(function () {
        toast(STATE.lang === "ar" ? "تمت إضافة الحصة." : "Stake added.", "ok");
        return renderAdminStructure();
      }).catch(adminError);
    }
    if (form.id === "sectorForm") {
      e.preventDefault();
      return post("/api/v1/admin/sectors", {
        code: byId("scCode").value,
        name_ar: byId("scNameAr").value,
        name_en: byId("scNameEn").value,
        sort_order: parseInt(byId("scOrder").value, 10) || 0,
      }).then(function () {
        toast(STATE.lang === "ar" ? "تمت إضافة القطاع." : "Sector added.", "ok");
        return renderAdminSectors();
      }).catch(adminError);
    }
    if (form.id === "positionForm") {
      e.preventDefault();
      return post("/api/v1/admin/positions", {
        company_id: parseInt(byId("posCompany").value, 10),
        code: byId("posCode").value,
        title_ar: byId("posTitleAr").value,
        title_en: byId("posTitleEn").value,
      }).then(function () {
        toast(STATE.lang === "ar" ? "تمت إضافة المنصب." : "Position added.", "ok");
        return renderAdminPositions();
      }).catch(adminError);
    }
    if (form.id === "motivationForm") {
      e.preventDefault();
      var roleVal = byId("motRole").value.trim();
      return post("/api/v1/admin/motivation-texts", {
        text_ar: byId("motTextAr").value,
        text_en: byId("motTextEn").value,
        audience_role: roleVal || null,
        sort_order: parseInt(byId("motOrder").value, 10) || 0,
      }).then(function () {
        toast(STATE.lang === "ar" ? "تمت إضافة الجملة." : "Sentence added.", "ok");
        return renderAdminMotivation();
      }).catch(adminError);
    }
    if (form.id === "deptForm") {
      e.preventDefault();
      return post("/api/v1/admin/departments", {
        company_id: parseInt(byId("dCompany").value, 10),
        code: byId("dCode").value,
        name_ar: byId("dNameAr").value,
        name_en: byId("dNameEn").value,
      }).then(function () {
        toast(STATE.lang === "ar" ? "تمت إضافة القسم." : "Department added.", "ok");
        return renderAdminDepartments();
      }).catch(adminError);
    }
  }

  function adminError(err) {
    toast(errText(err), "err");
  }

  // ---- search ----------------------------------------------------------
  function openSearch() {
    var panel = document.createElement("div");
    panel.className = "search-panel";
    panel.id = "searchPanel";
    panel.innerHTML =
      '<div class="search-box"><div class="search-in">' +
      '<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="#9DAABD" stroke-width="1.9" stroke-linecap="round"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.2-3.2"/></svg>' +
      '<input id="searchInput"' + phAttr("ph.search") + ' autocomplete="off">' +
      '<button class="modal-x" id="searchX">&times;</button></div>' +
      '<div class="search-res" id="searchRes"></div></div>';
    document.body.appendChild(panel);
    panel.addEventListener("click", function (e) {
      if (e.target === panel) closeSearch();
    });
    byId("searchX").addEventListener("click", closeSearch);
    document.addEventListener("keydown", searchEsc);
    var input = byId("searchInput");
    input.focus();
    var run = function () {
      runSearch(input.value.trim());
    };
    input.addEventListener("input", debounce(run, 180));
    Promise.all([ensureCompanies(), ensureReports(), ensureSupport()]).then(run);
  }

  function searchEsc(e) {
    if (e.key === "Escape") closeSearch();
  }

  function closeSearch() {
    var p = byId("searchPanel");
    if (p) p.parentNode.removeChild(p);
    document.removeEventListener("keydown", searchEsc);
  }

  var _debTimer = null;
  function debounce(fn, ms) {
    return function () {
      clearTimeout(_debTimer);
      _debTimer = setTimeout(fn, ms);
    };
  }

  function runSearch(q) {
    var host = byId("searchRes");
    if (!host) return;
    if (!q) {
      host.innerHTML = '<p class="av-empty">' + dual("اكتب للبحث…", "Type to search…") + "</p>";
      return;
    }
    var needle = q.toLowerCase();
    var hit = function (s) {
      return (s || "").toLowerCase().indexOf(needle) >= 0;
    };
    var companies = STATE.companies.filter(function (c) {
      return hit(c.name_ar) || hit(c.name_en) || hit(c.code) || hit(c.sector);
    });
    var reports = STATE.reports.filter(function (r) {
      return hit(r.company_name_ar) || hit(r.company_name_en) || hit(String(r.period_year) + "-" + r.period_month);
    });
    var support = STATE.support.filter(function (r) {
      return hit(r.title) || hit(r.description) || hit(r.company_name_ar) || hit(r.company_name_en);
    });

    var html = "";
    if (companies.length) {
      html += '<div class="sr-group">' + dual("الشركات", "Companies") + "</div>" +
        companies.map(function (c) {
          return '<div class="sr-item" data-s-co="' + c.id + '"><div class="co-dot" style="background:' + PALETTE[c.id % PALETTE.length] + '">' + initial(c.name_ar) + '</div><div class="grow"><div class="t">' + escapeHtml(companyName(c)) + '</div><div class="s">' + escapeHtml(c.code) + "</div></div></div>";
        }).join("");
    }
    if (reports.length) {
      html += '<div class="sr-group">' + dual("التقارير", "Reports") + "</div>" +
        reports.map(function (r) {
          return '<div class="sr-item" data-s-rep="' + r.id + '"><div class="grow"><div class="t">' + escapeHtml(reportCompanyName(r)) + '</div><div class="s">' + dual(AR_MONTHS[r.period_month - 1] + " " + toArabicDigits(String(r.period_year)), EN_MONTHS[r.period_month - 1] + " " + r.period_year) + "</div></div>" + statusBadge(r.status) + "</div>";
        }).join("");
    }
    if (support.length) {
      html += '<div class="sr-group">' + dual("الدعم", "Support") + "</div>" +
        support.map(function (r) {
          return '<div class="sr-item" data-s-sup="' + r.id + '"><div class="grow"><div class="t">' + escapeHtml(r.title) + '</div><div class="s">' + escapeHtml(r.company_name_ar || "") + "</div></div>" + supStatusBadge(r.status) + "</div>";
        }).join("");
    }
    host.innerHTML = html || '<p class="av-empty">' + dual("لا توجد نتائج.", "No results.") + "</p>";
    host.querySelectorAll("[data-s-co]").forEach(function (el) {
      el.addEventListener("click", function () {
        closeSearch();
        openCompany(parseInt(el.getAttribute("data-s-co"), 10));
      });
    });
    host.querySelectorAll("[data-s-rep]").forEach(function (el) {
      el.addEventListener("click", function () {
        closeSearch();
        openReport(parseInt(el.getAttribute("data-s-rep"), 10));
      });
    });
    host.querySelectorAll("[data-s-sup]").forEach(function (el) {
      el.addEventListener("click", function () {
        closeSearch();
        openSupport(parseInt(el.getAttribute("data-s-sup"), 10));
      });
    });
  }

  // ---- notifications ---------------------------------------------------
  function openNotifications() {
    var existing = byId("notifDD");
    if (existing) {
      existing.parentNode.removeChild(existing);
      return;
    }
    var dd = document.createElement("div");
    dd.className = "dd";
    dd.id = "notifDD";
    var items = STATE.insights.slice(0, 6);
    dd.innerHTML =
      '<div class="dd-head">' + dual("التنبيهات التنفيذية", "Executive alerts") + "</div>" +
      '<div class="dd-body">' +
      (items.length
        ? items.map(function (i) {
            return '<div class="dd-item"><div class="grow"><div class="t">' + escapeHtml(STATE.lang === "ar" ? i.title_ar : i.title_en) + '</div><div class="s">' + escapeHtml(STATE.lang === "ar" ? i.detail_ar : i.detail_en) + "</div></div></div>";
          }).join("")
        : '<p class="av-empty">' + dual("لا توجد تنبيهات.", "No alerts.") + "</p>") +
      "</div>" +
      '<div class="dd-foot">' + dual("مصدرها رؤى الذكاء الاصطناعي الحيّة", "Sourced from live AI insights") + "</div>";
    var host = document.querySelector(".h-actions");
    if (host) host.appendChild(dd);
    setTimeout(function () {
      document.addEventListener("click", closeDdOnce);
    }, 0);
  }

  function closeDdOnce(e) {
    var dd = byId("notifDD");
    if (dd && !dd.contains(e.target) && e.target.id !== "notifBtn" && !byId("notifBtn").contains(e.target)) {
      dd.parentNode.removeChild(dd);
      document.removeEventListener("click", closeDdOnce);
    }
  }

  function openMessages() {
    openModal({
      title: dual("الرسائل", "Messages"),
      body: '<p class="av-empty">' +
        dual(
          "لا تتوفر واجهة رسائل مباشرة في هذه المرحلة. استخدم التعليقات داخل طلبات الدعم للتواصل.",
          "No direct messaging API is available at this stage. Use comments inside support requests to communicate.",
        ) + "</p>",
      footer: '<button class="btn-outline" id="msgClose">' + dual("إغلاق", "Close") + "</button>",
      onMount: function (root) {
        root.querySelector("#msgClose").addEventListener("click", closeModal);
      },
    });
  }

  // ---- export ----------------------------------------------------------
  function exportExecutive() {
    if (!STATE.dashboard) {
      toast(STATE.lang === "ar" ? "لا توجد بيانات للتصدير." : "No data to export.", "err");
      return;
    }
    var k = STATE.dashboard.kpis || {};
    var change = STATE.dashboard.change_vs_previous || {};
    var rows = STATE.dashboard.companies_performance || [];
    var lines = [];
    lines.push(["Safir Holding 2027 — Executive Report"]);
    lines.push(["Period", (STATE.year || "") + "-" + String(STATE.month || "").padStart(2, "0")]);
    lines.push(["Generated", new Date().toISOString()]);
    lines.push([]);
    lines.push(["KPI", "Value"]);
    lines.push(["Companies", k.companies_count]);
    lines.push(["Reports submitted", k.reports_submitted]);
    lines.push(["Reports missing", k.reports_missing]);
    lines.push(["Total revenue", k.total_revenue]);
    lines.push(["Total expenses", k.total_expenses]);
    lines.push(["Total net result", k.total_net_result]);
    lines.push(["Companies needing attention", k.companies_requiring_attention]);
    lines.push(["Open support requests", k.open_support_requests]);
    lines.push(["Pending financial reviews", k.pending_financial_reviews]);
    lines.push(["Revenue change %", change.revenue_pct]);
    lines.push(["Net change %", change.net_pct]);
    lines.push([]);
    lines.push(["Company", "Code", "Sector", "Status", "Revenue", "Expenses", "Net", "Growth %"]);
    rows.forEach(function (r) {
      lines.push([r.name_en || r.name_ar, r.code, r.sector || "", r.report_status || "none", r.revenue || "", r.expenses || "", r.net_result || "", r.revenue_pct === null || r.revenue_pct === undefined ? "" : r.revenue_pct]);
    });
    var csv = lines
      .map(function (row) {
        return row
          .map(function (cell) {
            var s = cell === null || cell === undefined ? "" : String(cell);
            return /[",\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
          })
          .join(",");
      })
      .join("\r\n");
    var blob = new Blob(["\uFEFF" + csv], { type: "text/csv;charset=utf-8;" });
    var url = URL.createObjectURL(blob);
    var a = document.createElement("a");
    a.href = url;
    a.download = "safir-executive-" + (STATE.year || "") + "-" + String(STATE.month || "").padStart(2, "0") + ".csv";
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(function () {
      URL.revokeObjectURL(url);
    }, 1000);
    toast(STATE.lang === "ar" ? "تم تنزيل التقرير التنفيذي (CSV)." : "Executive report downloaded (CSV).", "ok");
  }

  // ---- period + refresh ------------------------------------------------
  function setPeriodLabels() {
    var lab = periodLabel();
    if (!lab.ar && !lab.en) return;
    var eye = byId("periodEyebrow");
    if (eye) eye.innerHTML = dual("الرؤية التنفيذية · " + lab.ar, "Executive View · " + lab.en);
    var ai = byId("aiAnswerPeriod");
    if (ai) ai.innerHTML = dual(lab.ar, lab.en);
    var chip = byId("updatedChip");
    if (chip) chip.innerHTML = dual("تحديث حي · " + lab.ar, "Live · " + lab.en);
  }

  function refreshAll() {
    STATE.loaded = {};
    var jobs = [
      loadDashboard().catch(handleLoadError),
      loadInsights().catch(handleLoadError),
      ensureCompanies(),
      ensureReports(),
      ensureSupport(),
    ];
    if (has("support_request.read_own") || has("support_request.read_all")) {
      jobs.push(loadSupport().catch(handleLoadError));
    }
    jobs.push(refreshNotifications());
    return Promise.all(jobs).then(function () {
      setPeriodLabels();
    });
  }

  // ---- permissions -----------------------------------------------------
  var USER = null;
  function has(perm) {
    return !!(USER && USER.permissions && USER.permissions.indexOf(perm) >= 0);
  }

  // D04: leadership assessments are confidential and owner-only. The frontend
  // mirrors the server's rule so a non-owner is never offered the control; the
  // backend still enforces it.
  function isConfidentialOwner() {
    return !!(
      USER &&
      (USER.is_superuser ||
        USER.role_code === "holding_owner" ||
        USER.role_code === "super_admin")
    );
  }

  function applyPermissions() {
    document.querySelectorAll("[data-perm]").forEach(function (el) {
      var needed = el.getAttribute("data-perm").split(/\s+/);
      var ok = needed.some(has);
      el.classList.toggle("perm-hidden", !ok);
    });
  }

  function fillProfile() {
    if (!USER) return;
    var name = USER.full_name_ar || USER.full_name_en || "";
    var role = USER.role_name_ar || USER.role_code || "";
    document.querySelectorAll(".profile .p-name .ar").forEach(function (el) {
      el.textContent = name;
    });
    document.querySelectorAll(".profile .p-name .en").forEach(function (el) {
      el.textContent = USER.full_name_en || name;
    });
    document.querySelectorAll(".profile .p-role .ar").forEach(function (el) {
      el.textContent = role;
    });
    document.querySelectorAll(".profile .p-role .en").forEach(function (el) {
      el.textContent = USER.role_name_en || role;
    });
    var avatar = document.querySelector(".profile .avatar");
    if (avatar) avatar.textContent = (name || "؟").trim().charAt(0);
  }

  function isHolding() {
    return has("dashboard.holding");
  }

  // The platform header shows the same admin-uploaded Holding logo as the
  // public site, falling back to the static brand mark when none is set.
  function applyPlatformLogo() {
    var img = byId("brandLogo");
    var mark = byId("brandMark");
    if (!img) return;
    get("/api/v1/public/branding")
      .then(function (branding) {
        var url = branding && branding.logo_url;
        if (url) {
          img.onload = function () {
            img.hidden = false;
            if (mark) mark.hidden = true;
          };
          img.onerror = function () {
            img.hidden = true;
            if (mark) mark.hidden = false;
          };
          img.src = url;
        } else {
          img.hidden = true;
          if (mark) mark.hidden = false;
        }
      })
      .catch(function () {
        /* keep the static brand mark on any failure */
      });
  }

  function primaryCompanyId() {
    return USER && USER.company_ids && USER.company_ids.length
      ? USER.company_ids[0]
      : null;
  }

  // ---- AI --------------------------------------------------------------
  function askAi(question) {
    var path, payload;
    if (isHolding()) {
      path = "/api/v1/ai/holding" + period;
      payload = { question: question };
    } else if (primaryCompanyId() !== null) {
      path = "/api/v1/ai/company" + period;
      payload = { question: question, company_id: primaryCompanyId() };
    } else {
      return Promise.reject(new Error("no AI scope available"));
    }
    return post(path, payload).then(function (data) {
      hydrateAiAnswer(data, question);
      return data;
    });
  }

  function bindAskBox() {
    var box = document.querySelector(".ask-box");
    if (!box) return;
    var input = box.querySelector("input");
    var send = box.querySelector(".ask-send");
    if (!input || !send) return;

    function submit() {
      var q = (input.value || "").trim();
      if (!q) return;
      input.value = "";
      askAi(q).catch(function (err) {
        showAiError(err.message);
      });
    }
    send.addEventListener("click", submit);
    input.addEventListener("keydown", function (e) {
      if (e.key === "Enter") submit();
    });
    document.querySelectorAll(".sugg").forEach(function (chip) {
      chip.addEventListener("click", function () {
        var ar = chip.querySelector(".ar");
        if (ar) {
          input.value = ar.textContent.trim();
          submit();
        }
      });
    });
  }

  function showAiError(message) {
    var box = document.getElementById("aiAnswerBody");
    if (box) box.innerHTML = errorHtml(message);
  }

  // Clear the curated demo figures immediately after sign-in so nothing is ever
  // mistaken for real data while the API responses are in flight.
  function showLoadingStates() {
    ["companies_count", "companies_count_unit", "total_revenue",
     "total_net_result", "reports_submitted", "companies_requiring_attention",
     "open_support_requests", "sector_count", "sector_count_en",
     "structure_count", "structure_count_en", "hub_total", "hub_total_en",
     "insights_count", "insights_count_en", "support_pending",
     "support_pending_en"].forEach(function (key) {
      setText('[data-kpi="' + key + '"]', "…");
    });
    ["revenue_delta", "net_delta", "reports_pct"].forEach(function (key) {
      var el = document.querySelector('[data-kpi="' + key + '"]');
      if (el) {
        el.className = "delta flat";
        el.innerHTML = dual("…", "…");
      }
    });
    var repGrid = document.querySelector(".rep-grid");
    if (repGrid) repGrid.innerHTML = loadingHtml();
    var subs = document.querySelector(".subs");
    if (subs) subs.innerHTML = loadingHtml();
    var overview = document.querySelector(".ov-card .card-body");
    if (overview) overview.innerHTML = loadingHtml();
    var list = document.getElementById("insightsList");
    if (list) list.innerHTML = loadingHtml();
    var prio = document.getElementById("prioritiesList");
    if (prio) prio.innerHTML = loadingHtml();
    var aiBody = document.getElementById("aiAnswerBody");
    if (aiBody) aiBody.innerHTML = loadingHtml();
    var sbody = document.getElementById("supportBody");
    if (sbody) {
      sbody.innerHTML = '<tr><td colspan="5">' + loadingHtml() + "</td></tr>";
    }
  }

  // ---- data loading ----------------------------------------------------
  function loadDashboard() {
    var path = isHolding()
      ? "/api/v1/dashboard/holding" + period
      : "/api/v1/dashboard/company/" + primaryCompanyId() + period;
    return get(path).then(function (data) {
      STATE.dashboard = data;
      hydrateKpis(data);
      hydrateCompanies(data);
      hydratePriorities(data);
      setPeriodLabels();
      return data;
    });
  }

  function loadSupport() {
    return get("/api/v1/support-requests").then(function (rows) {
      STATE.support = rows || [];
      STATE.loaded.support = true;
      hydrateSupport(STATE.support);
      return STATE.support;
    });
  }

  function loadInsights(keepCache) {
    return get("/api/v1/ai/insights" + period).then(function (insights) {
      STATE.insights = insights || [];
      STATE.loaded.insights = true;
      if (!keepCache) renderInsights(STATE.insights);
      return STATE.insights;
    });
  }

  function loadDefaultAi() {
    return askAi("ملخص أداء المجموعة هذا الشهر");
  }

  function showDashboardErrors(message) {
    var repGrid = document.querySelector(".rep-grid");
    if (repGrid) repGrid.innerHTML = errorHtml(message);
    var subs = document.querySelector(".subs");
    if (subs) subs.innerHTML = errorHtml(message);
    var overview = document.querySelector(".ov-card .card-body");
    if (overview) overview.innerHTML = errorHtml(message);
    var list = document.getElementById("insightsList");
    if (list) list.innerHTML = errorHtml(message);
    showAiError(message);
    var sbody = document.getElementById("supportBody");
    if (sbody) {
      sbody.innerHTML =
        '<tr><td colspan="5">' + errorHtml(message) + "</td></tr>";
    }
  }

  // ---- login screen ----------------------------------------------------
  function showLogin() {
    body.classList.remove("authed");
    var screen = document.getElementById("loginScreen");
    if (screen) screen.style.display = "";
    var pw = document.getElementById("loginPassword");
    if (pw) pw.value = "";
  }

  function hideLogin() {
    var screen = document.getElementById("loginScreen");
    if (screen) screen.style.display = "none";
    body.classList.add("authed");
  }

  function setLoginError(message) {
    var el = document.getElementById("loginError");
    if (!el) return;
    if (message) {
      el.textContent = message;
      el.classList.add("show");
    } else {
      el.classList.remove("show");
    }
  }

  function bindLogin() {
    var form = document.getElementById("loginForm");
    if (!form) return;
    form.addEventListener("submit", function (e) {
      e.preventDefault();
      var email = (document.getElementById("loginEmail").value || "").trim();
      var password = document.getElementById("loginPassword").value || "";
      var btn = document.getElementById("loginBtn");
      setLoginError("");
      if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<span class="spinner"></span>';
      }
      api
        .login(email, password)
        .then(function () {
          return enterApp();
        })
        .catch(function (err) {
          setLoginError(errText(err, STATE.lang === "ar" ? "تعذّر تسجيل الدخول. تحقّق من البريد وكلمة المرور." : "Sign-in failed. Check your email and password."));
        })
        .then(function () {
          if (btn) {
            btn.disabled = false;
            btn.innerHTML =
              '<span class="ar">دخول المنصة</span><span class="en">Sign in</span>';
          }
        });
    });
  }

  function bindLogout() {
    var btn = document.getElementById("logoutBtn");
    if (!btn) return;
    btn.addEventListener("click", function () {
      btn.disabled = true;
      api.logout().then(function () {
        USER = null;
        btn.disabled = false;
        showLogin();
        window.scrollTo(0, 0);
      });
    });
  }

  // ---- session expiry --------------------------------------------------
  var toastShown = false;
  function sessionExpired() {
    if (toastShown) return;
    toastShown = true;
    var t = document.createElement("div");
    t.className = "session-toast";
    t.innerHTML =
      '<span class="ar">انتهت الجلسة. يرجى تسجيل الدخول مرة أخرى.</span>' +
      '<span class="en">Session expired. Please sign in again.</span>';
    document.body.appendChild(t);
    setTimeout(function () {
      t.remove();
      toastShown = false;
    }, 5000);
    showLogin();
  }

  function handleLoadError(err) {
    if (err && err.status === 401) {
      api.clear();
      sessionExpired();
      return;
    }
    if (err && err.status === 403) {
      showDashboardErrors("ليست لديك صلاحية لعرض هذه البيانات.");
      return;
    }
    showDashboardErrors(err && err.message ? err.message : "تعذّر تحميل البيانات.");
  }

  // ---- boot ------------------------------------------------------------
  function enterApp() {
    hideLogin();
    return api
      .me()
      .then(function (user) {
        USER = user;
        fillProfile();
        applyPlatformLogo();
        applyPermissions();
        bindAskBox();
        bindLogout();
        bindHeaderActions();
        bindNav();
        bindIndicatorDrills();
        showLoadingStates();
        return resolvePeriod();
      })
      .then(function () {
        // Reports back the dashboard cards' "View Report" action and the
        // company drill-downs, so load them first even when the period was
        // pinned via the URL (resolvePeriod skips its own fetch in that case).
        return Promise.all([ensureReports(), ensureCompanies(), ensureSectors()]);
      })
      .then(function () {
        var jobs = [];
        if (has("dashboard.holding") || has("dashboard.company")) {
          jobs.push(
            loadDashboard().catch(function (err) {
              handleLoadError(err);
            }),
          );
        }
        if (has("support_request.read_own") || has("support_request.read_all")) {
          jobs.push(
            loadSupport().catch(function (err) {
              handleLoadError(err);
            }),
          );
        }
        // Preview the dynamic-ops counters on the dashboard without navigating
        // away: forms (for the request type list) and the approvals inbox.
        if (has("form.read") || has("form.submit")) {
          jobs.push(ensureForms().catch(function () {}));
        }
        if (has("dashboard.holding") || has("dashboard.company")) {
          jobs.push(
            loadInsights().catch(function (err) {
              handleLoadError(err);
            }),
          );
          if (has("ai.holding") || has("ai.company")) {
            jobs.push(
              loadDefaultAi().catch(function (err) {
                showAiError(err && err.message);
              }),
            );
          }
        }
        return Promise.all(jobs);
      })
      .then(function () {
        navTo(STATE.view || "dashboard", false);
      })
      .catch(function (err) {
        if (err && err.status === 401) {
          api.clear();
          showLogin();
        } else {
          handleLoadError(err);
        }
      });
  }

  function bindHeaderActions() {
    var exp = byId("exportBtn");
    if (exp && !exp.getAttribute("data-bound")) {
      exp.setAttribute("data-bound", "1");
      exp.addEventListener("click", exportExecutive);
    }
    var search = byId("searchBtn");
    if (search && !search.getAttribute("data-bound")) {
      search.setAttribute("data-bound", "1");
      search.addEventListener("click", openSearch);
    }
    var notif = byId("notifBtn");
    if (notif && !notif.getAttribute("data-bound")) {
      notif.setAttribute("data-bound", "1");
      notif.addEventListener("click", openNotifications);
    }
    var msg = byId("msgBtn");
    if (msg && !msg.getAttribute("data-bound")) {
      msg.setAttribute("data-bound", "1");
      msg.addEventListener("click", openMessages);
    }
    var repRefresh = byId("repRefresh");
    if (repRefresh && !repRefresh.getAttribute("data-bound")) {
      repRefresh.setAttribute("data-bound", "1");
      repRefresh.addEventListener("click", function () { renderReports(); });
    }
    var repYear = byId("repYear");
    if (repYear && !repYear.getAttribute("data-bound")) {
      repYear.setAttribute("data-bound", "1");
      repYear.addEventListener("change", function () {
        STATE.year = this.value ? parseInt(this.value, 10) : STATE.year;
        renderReports();
      });
    }
    var repStatus = byId("repStatus");
    if (repStatus && !repStatus.getAttribute("data-bound")) {
      repStatus.setAttribute("data-bound", "1");
      repStatus.addEventListener("change", function () { renderReports(); });
    }
    var supStatus = byId("supStatus");
    if (supStatus && !supStatus.getAttribute("data-bound")) {
      supStatus.setAttribute("data-bound", "1");
      supStatus.addEventListener("change", function () { renderSupportView(); });
    }
    var supRefresh = byId("supRefresh");
    if (supRefresh && !supRefresh.getAttribute("data-bound")) {
      supRefresh.setAttribute("data-bound", "1");
      supRefresh.addEventListener("click", function () {
        STATE.loaded.support = false;
        renderSupportView();
      });
    }
    var subsRefresh = byId("subsRefresh");
    if (subsRefresh && !subsRefresh.getAttribute("data-bound")) {
      subsRefresh.setAttribute("data-bound", "1");
      subsRefresh.addEventListener("click", function () {
        STATE.loaded.companies = false;
        renderSubsidiaries();
      });
    }
    // Ctrl/Cmd-K opens search, like a real SaaS app.
    document.addEventListener("keydown", function (e) {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        if (!byId("searchPanel")) openSearch();
      }
    });
  }

  function boot() {
    bindLang();
    api.load();
    bindLogin();
    ensureToastRegion();
    if (api.isAuthenticated()) {
      enterApp();
    } else {
      showLogin();
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
