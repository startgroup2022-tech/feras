/*
 * Start Upsphere Holding 2027 — live data bridge.
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
    hrTab: "movements",
    advTab: "sessions",
    siteTab: "listings",
    aiRevTab: "proposals",
    opsTab: "tasks",
    acctTab: "balances",
    acctLedgerCompany: null,
    acctLedgerType: "",
    acctLedgerYear: null,
    acctLedgerMonth: null,
    confTab: "complaints",
    scopeCompany: null,
    loaded: {},
    filters: {},
    page: {},
    pageSize: 25,
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

  // An optional panel fetch. A 401/403/404 means the caller simply has no
  // access to this slice, so the section renders empty. Anything else (5xx,
  // network) is a real fault and must not masquerade as "no data".
  function softGet(path) {
    return api.get(path).catch(function (err) {
      var s = err && err.status;
      if (s !== 401 && s !== 403 && s !== 404) {
        toast(errText(err), "err");
      }
      return [];
    });
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
    "ph.knowledgeSlug": { ar: "مثال: leave-policy-2027", en: "e.g. leave-policy-2027" },
    "ph.fieldKey": { ar: "مثال: amount", en: "e.g. amount" },
    "ph.scopeSector": { ar: "مثال: Technology", en: "e.g. Technology" },
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
      returned: { ar: "أُعيد للتصحيح", en: "Returned for correction" },
      cancelled: { ar: "ملغى", en: "Cancelled" },
      locked: { ar: "مقفل", en: "Locked" },
    };
    return map[status] || { ar: "بانتظار التقرير", en: "Awaiting report" };
  }

  function statusClass(status) {
    if (status === "reviewed" || status === "submitted" || status === "locked") return "ok";
    if (status === "under_review" || status === "returned") return "late";
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

  // S01 "ماذا يحتاج اهتمامك اليوم؟": record links the caller may act on,
  // restricted per access by the backend, so every entry is openable. Each
  // row carries a direct action so the owner can act without navigating away
  // and hunting for the record.
  var PRIORITY_ACTION = {
    company: { view: "subsidiaries", ar: "مراجعة الشركة", en: "Review company" },
    support_request: { view: "support", ar: "فتح الطلب", en: "Open request" },
    owner_decision: { view: "decisions", ar: "اتخاذ قرار", en: "Take decision" },
    monthly_report: { view: "reports", ar: "مراجعة التقرير", en: "Review report" },
    task: { view: "operations", ar: "متابعة المهمة", en: "Follow up" },
  };

  function priorityAction(kind) {
    return PRIORITY_ACTION[kind] || { view: "dashboard", ar: "عرض", en: "View" };
  }

  function hydratePriorities(data) {
    var host = byId("prioritiesList");
    if (!host) return;
    var rows = data.priorities || [];
    var count = byId("attnCount");
    if (count) count.textContent = plainNum(rows.length);
    if (!rows.length) {
      host.innerHTML = emptyHtml(
        "لا توجد بنود تتطلب اهتمامك الآن.",
        "Nothing needs your attention right now."
      );
      return;
    }
    host.innerHTML = rows.map(function (p) {
      var label = STATE.lang === "ar"
        ? (p.label_ar || p.label_en || "")
        : (p.label_en || p.label_ar || "");
      var sub = p.overdue
        ? dual("متأخر عن الاستحقاق", "Overdue")
        : (p.reason ? escapeHtml(p.reason) : "");
      var urgent = p.overdue || p.kind === "support_request";
      var icon = p.kind === "company" ? "🏢"
        : p.kind === "support_request" ? "💬"
        : p.kind === "owner_decision" ? "✔" : "📌";
      var act = priorityAction(p.kind);
      var badge = p.overdue
        ? '<span class="attn-badge urgent">' + dual("متأخر", "Overdue") + "</span>"
        : "";
      return '<div class="attn-card' + (urgent ? " urgent" : "") +
        '" data-priority-kind="' + escapeHtml(p.kind) +
        '" data-priority-id="' + p.record_id + '">' +
        '<div class="a-ico">' + icon + "</div>" +
        '<div class="attn-main"><div class="attn-title">' + escapeHtml(label) +
        '</div>' + (sub ? '<div class="attn-sub">' + sub + "</div>" : "") + "</div>" +
        badge +
        '<button type="button" class="attn-act gold">' + dual(act.ar, act.en) +
        "</button></div>";
    }).join("");
    host.querySelectorAll("[data-priority-kind]").forEach(function (el) {
      el.addEventListener("click", function () {
        var kind = el.getAttribute("data-priority-kind");
        var id = parseInt(el.getAttribute("data-priority-id"), 10);
        if (kind === "company") {
          openCompany(id);
        } else {
          navTo(priorityAction(kind).view);
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
  var ROLE_TONE = {
    navy: "",
    green: "green",
    red: "red",
    amber: "amber",
    gold: "gold",
  };

  function roleKpiCard(kpi) {
    var tone = ROLE_TONE[kpi.tone] || "";
    var unit = kpi.unit
      ? '<span class="unit">' + escapeHtml(kpi.unit) + "</span>"
      : "";
    var foot = "";
    if (kpi.delta) {
      var dir =
        kpi.delta_dir === "up" ? "up" : kpi.delta_dir === "down" ? "down" : "flat";
      foot =
        '<div class="kpi-foot"><span class="delta ' +
        dir +
        '">' +
        escapeHtml(kpi.delta) +
        "</span></div>";
    }
    return (
      '<div class="kpi' +
      (tone ? " " + tone : "") +
      ' anim">' +
      '<div class="kpi-head"><div class="kpi-lbl">' +
      dual(escapeHtml(kpi.label_ar), escapeHtml(kpi.label_en)) +
      "</div></div>" +
      '<div class="kpi-val num">' +
      escapeHtml(kpi.value) +
      unit +
      "</div>" +
      foot +
      "</div>"
    );
  }

  // Deck slides 7-11: when the API returns a role summary, the caller gets its
  // own tile strip and the holding strip is replaced. A role with no summary
  // (or one whose every source is denied) keeps the holding strip.
  function hydrateRoleSummary(data) {
    var box = byId("roleKpis");
    if (!box) return;
    var holding = byId("holdingKpis");
    var title = byId("pageTitle");
    var sub = byId("pageSub");
    var summary = data && data.role_summary;
    var section = byId("roleSection");
    var sectionTitle = byId("roleSectionTitle");
    if (!summary || !summary.kpis || !summary.kpis.length) {
      box.hidden = true;
      box.innerHTML = "";
      if (section) section.hidden = true;
      if (holding) holding.hidden = false;
      // A role with no summary of its own keeps the holding strip; the heading
      // stays "لوحة القيادة" and the sub line falls back to the prototype's
      // generic wording rather than the owner's holding summary.
      if (title) title.innerHTML = dual("لوحة القيادة", "Dashboard");
      if (sub) {
        sub.innerHTML = dual(
          "ملخص الأعمال المرتبطة بدورك",
          "Summary of the work related to your role",
        );
      }
      return;
    }
    box.innerHTML = summary.kpis.map(roleKpiCard).join("");
    box.hidden = false;
    if (holding) holding.hidden = true;
    // Deck slides 7-11 name the follow-up section after the role; the API
    // supplies the deck's own wording so it is painted, not paraphrased.
    if (section && sectionTitle && summary.section_ar) {
      sectionTitle.innerHTML = dual(
        escapeHtml(summary.section_ar),
        escapeHtml(summary.section_en || summary.section_ar),
      );
      section.hidden = false;
    } else if (section) {
      section.hidden = true;
    }
    renderRoleShortcuts(summary);
    // Deck slides 7-11 give each role its own page title and greeting above
    // the tiles, replacing the holding heading.
    if (title) {
      title.innerHTML = dual(escapeHtml(summary.title_ar), escapeHtml(summary.title_en));
    }
    if (sub && summary.greeting_ar) {
      sub.innerHTML = dual(escapeHtml(summary.greeting_ar), escapeHtml(summary.greeting_en));
    }
  }

  // Deck slides 7-11: each role block carries a shortcut grid ("اختصارات
  // الشركة", "أدواتي", "أولويات الأسبوع", ...) and a [عرض الكل] action. Both are
  // navigation only -- the target still passes canView/navTo, so a shortcut can
  // never open a section the role lacks.
  function renderRoleShortcuts(summary) {
    var host = byId("roleShortcuts");
    var allBtn = byId("roleViewAll");
    if (allBtn) {
      var target = summary && summary.view_all;
      if (target && canView(target)) {
        allBtn.innerHTML = dual("عرض الكل", "View all");
        allBtn.hidden = false;
        if (!allBtn.dataset.bound) {
          allBtn.dataset.bound = "1";
          allBtn.addEventListener("click", function () {
            navTo(byId("roleViewAll").getAttribute("data-target") || "dashboard");
          });
        }
        allBtn.setAttribute("data-target", target);
      } else {
        allBtn.hidden = true;
      }
    }
    if (!host) return;
    var items = (summary && summary.shortcuts) || [];
    items = items.filter(function (sc) { return canView(sc.view); });
    if (!items.length) {
      host.hidden = true;
      host.innerHTML = "";
      return;
    }
    host.innerHTML = items.map(function (sc) {
      return '<button type="button" class="shortcut" data-goto="' + escAttr(sc.view) + '">' +
        '<div class="sc-t">' + dual(escapeHtml(sc.label_ar), escapeHtml(sc.label_en)) + "</div></button>";
    }).join("");
    host.hidden = false;
    host.querySelectorAll("[data-goto]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        navTo(btn.getAttribute("data-goto"));
      });
    });
  }

  // Deck slide 46: after the period's management report is approved the company
  // manager gets a short smart brief -- one fact about the company and one piece
  // of advice -- plus a plan offer. The brief is built from the *live* company
  // figures (a deterministic "smart summary", not a model call), so it can never
  // cite a number the manager cannot already see. The AI role ends here: [نعم،
  // اطلب خطة] only opens a plan request for Business Development to answer by
  // hand ("مطور الأعمال يراجع الطلب ويعدّ الخطة بشريًا").
  function renderSmartBrief() {
    var section = byId("smartBriefSection");
    if (!section) return;
    // Only the subsidiary manager sees this brief; the owner/BD read the
    // approved report itself.
    var summary = STATE.dashboard && STATE.dashboard.role_summary;
    var roleCode = (summary && summary.role_code) || (USER && USER.role_code);
    var companyId = primaryCompanyId();
    if (roleCode !== "company_manager" || companyId === null) {
      section.hidden = true;
      return;
    }
    section.hidden = false;
    var intro = byId("sbIntro");
    if (intro) {
      intro.innerHTML = dual(
        "بعد اعتماد التقرير: تنبيه موجز عن وضع الشركة ونصيحة واحدة للشهر القادم، مع خيار طلب خطة.",
        "After the report is approved: a brief note on the company and one piece of advice for next month, with an option to request a plan.");
    }
    var status = byId("sbStatus");
    var fact = byId("sbFact");
    var advice = byId("sbAdvice");
    var question = byId("sbQuestion");
    var planBtn = byId("sbPlan");
    var declineBtn = byId("sbDecline");

    var year = STATE.period ? STATE.period.year : new Date().getFullYear();
    var month = STATE.period ? STATE.period.month : new Date().getMonth() + 1;

    // Find the live report for this company/period.
    var reports = (STATE.reports || []).filter(function (r) {
      return r.company_id === companyId && r.period_year === year && r.period_month === month;
    });
    var report = reports[0];
    var approved = report && report.approval_status === "approved";

    if (question) question.innerHTML = dual("هل ترغب بطلب خطة لعمل ذلك؟", "Would you like to request a plan to do that?");
    var setPlanButtons = function (show) {
      if (planBtn) { planBtn.hidden = !show; planBtn.innerHTML = dual("نعم، اطلب خطة", "Yes, request a plan"); }
      if (declineBtn) { declineBtn.hidden = !show; declineBtn.innerHTML = dual("لا، شكرًا", "No, thank you"); }
    };

    if (!report) {
      if (status) status.innerHTML = dual("لا يوجد تقرير لهذه الفترة بعد.", "No report for this period yet.");
      if (fact) fact.textContent = "—";
      if (advice) advice.textContent = "—";
      setPlanButtons(false);
      return;
    }
    if (!approved) {
      if (status) status.innerHTML = statusBadgeFromMap(report.status, REPORT_STATUS_LABEL) +
        " " + dual("التقرير غير معتمد بعد؛ يظهر الملخص بعد الاعتماد.", "The report is not approved yet; the brief appears after approval.");
      if (fact) fact.textContent = "—";
      if (advice) advice.textContent = "—";
      setPlanButtons(false);
      return;
    }

    if (status) status.innerHTML = statusBadgeFromMap("approved", { approved: ["التقرير معتمد", "Report approved", "ok"] });
    // ---- the one fact: collection fell/rose versus the approved three months
    var perf = (STATE.dashboard && STATE.dashboard.companies_performance) || [];
    var mine = perf.filter(function (p) { return p.id === companyId; })[0];
    var factAr = "بيانات التقرير المعتمد متاحة للمراجعة.";
    var factEn = "The approved report figures are available for review.";
    if (mine && typeof mine.revenue_pct === "number") {
      var pct = Math.abs(Math.round(mine.revenue_pct));
      if (mine.revenue_pct < 0) {
        factAr = "التحصيل انخفض " + toArabicDigits(String(pct)) + "٪ عن الفترة السابقة.";
        factEn = "Collection fell " + pct + "% versus the previous period.";
      } else if (mine.revenue_pct > 0) {
        factAr = "الإيراد ارتفع " + toArabicDigits(String(pct)) + "٪ عن الفترة السابقة.";
        factEn = "Revenue rose " + pct + "% versus the previous period.";
      }
    } else if (report.major_problems) {
      factAr = "أبرز التحديات: " + report.major_problems;
      factEn = "Top challenge: " + report.major_problems;
    }
    if (fact) fact.innerHTML = dual(escapeHtml(factAr), escapeHtml(factEn));
    // ---- the one piece of advice
    var adviceAr = "راجعوا المستحقات المتأخرة وحددوا موعد متابعة لكل منها.";
    var adviceEn = "Review the overdue receivables and set a follow-up date for each.";
    if (report.outstanding_receivables && Number(report.outstanding_receivables) > 0) {
      adviceAr = "راجعوا أكبر ثلاثة مستحقات متأخرة وحددوا موعد متابعة لكل منها.";
      adviceEn = "Review the three largest overdue receivables and set a follow-up date for each.";
    } else if (report.support_required) {
      adviceAr = "تابعوا الدعم المطلوب: " + report.support_required;
      adviceEn = "Follow up the requested support: " + report.support_required;
    }
    if (advice) advice.innerHTML = dual(escapeHtml(adviceAr), escapeHtml(adviceEn));
    setPlanButtons(true);

    if (planBtn && !planBtn.dataset.bound) {
      planBtn.dataset.bound = "1";
      planBtn.addEventListener("click", function () {
        requestSmartPlan(companyId, year, month, planBtn);
      });
    }
    if (declineBtn && !declineBtn.dataset.bound) {
      declineBtn.dataset.bound = "1";
      declineBtn.addEventListener("click", function () {
        byId("smartBriefSection").hidden = true;
      });
    }
  }

  function requestSmartPlan(companyId, year, month, btn) {
    busy(btn, true);
    post("/api/v1/operations/plan-requests", {
      company_id: companyId, period_year: year, period_month: month,
    }).then(function () {
      toast(dual("أُرسل طلب الخطة لمطور الأعمال.", "Plan request sent to Business Development."), "ok");
      if (byId("smartBriefSection")) byId("smartBriefSection").hidden = true;
    }).catch(function (err) { domainError(err); busy(btn, false); });
  }

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

  function errorHtml(message, opts) {
    var safe = escapeHtml(message || "تعذّر تحميل البيانات.");
    var retry = opts && opts.retry
      ? '<button type="button" class="retry-btn" data-retry>' +
        '<span class="ar">إعادة المحاولة</span><span class="en">Retry</span></button>'
      : "";
    return (
      '<div class="data-error">' +
      '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 9v4"/><path d="M12 17h.01"/><path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z"/></svg>' +
      '<span class="ar">' + safe + '</span>' +
      '<span class="en">' + safe + "</span>" +
      retry + "</div>"
    );
  }

  // The deck's shared error state (slide 38: "تعذر الحفظ — تحقق من الاتصال
  // وحاول مجددًا [إعادة المحاولة]") offers one retry control. It re-runs the
  // active view's fetch; it never re-sends a write, so a failed save cannot be
  // silently duplicated.
  document.addEventListener("click", function (e) {
    var btn = e.target.closest && e.target.closest("[data-retry]");
    if (!btn) return;
    btn.disabled = true;
    refreshActiveView();
  });

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

  // A calendar year, a month or a week is an identifier, not a quantity: it is
  // never thousands-separated (NUM.format would render 2027 as "2,027").
  function periodPart(value) {
    if (value === null || value === undefined || value === "") return "—";
    var n = Number(value);
    return isNaN(n) ? String(value) : String(n);
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

  // Plain-text date-time in the active language, for contexts that will be
  // HTML-escaped (fmtDateTime returns dual() markup, which would leak tags).
  function stampText(iso) {
    if (!iso) return "—";
    var d = new Date(iso);
    if (isNaN(d.getTime())) return String(iso).slice(0, 10);
    var base = dateLabel(iso);
    var hh = String(d.getHours()).padStart(2, "0");
    var mm = String(d.getMinutes()).padStart(2, "0");
    return STATE.lang === "ar"
      ? base.ar + " · " + toArabicDigits(hh + ":" + mm)
      : base.en + " · " + hh + ":" + mm;
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
    if (typeof syncScopeSelects === "function") syncScopeSelects();
    if (typeof refreshActiveView === "function") refreshActiveView();
  }

  // Keep the document title in the active language (and in sync with the
  // current view) instead of leaving the server-rendered Arabic title forever.
  var VIEW_TITLES = {
    dashboard: { ar: "لوحة القيادة", en: "Dashboard" },
    feedback: { ar: "التغذية الراجعة", en: "Feedback" },
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
        ? "ستارت اب سفير القابضة ٢٠٢٧ — "
        : "Start Upsphere Holding 2027 — ";
    var view = (typeof STATE !== "undefined" && STATE.view) || "dashboard";
    var t = VIEW_TITLES[view];
    document.title = brand + (t ? (STATE.lang === "ar" ? t.ar : t.en) : "");
    var crumb = byId("crumb");
    if (crumb) {
      var label = t ? (STATE.lang === "ar" ? t.ar : t.en) : "";
      var brandLabel = STATE.lang === "ar" ? "منصة القيادة التنفيذية" : "Executive Platform";
      crumb.textContent = brandLabel + (label ? "  ·  " + label : "");
    }
  }

  // Re-render the current view when the language changes, so any Arabic-only
  // string baked into server-driven markup is rebuilt in the new language.
  function refreshActiveView() {
    if (!USER) return;
    var view = (typeof STATE !== "undefined" && STATE.view) || "dashboard";
    if (view === "group" && typeof renderAdminTab === "function") {
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

  // ---- header entity + period scope ------------------------------------
  // The deck's header carries [الشركة / المجموعة ▾] and the reporting period
  // on every screen (slides 4, 48). Selecting an entity narrows the *view*
  // filter only: it never widens access, and the backend still enforces the
  // row-level scope on every request, so an out-of-scope pick simply returns
  // nothing rather than leaking another company's rows.

  function currentScopeLabel() {
    if (STATE.scopeCompany == null) return { ar: "كل المجموعة", en: "Whole group" };
    var c = companyById(STATE.scopeCompany);
    return c
      ? { ar: c.name_ar || c.name_en || "", en: c.name_en || c.name_ar || "" }
      : { ar: "كل المجموعة", en: "Whole group" };
  }

  function syncScopeSelects() {
    // Deck slide 34 labels the consultant's header scope control [نطاق التكليف]
    // rather than [الشركة / المجموعة]; the control is the same selector, only
    // the wording is role-specific.
    var scopeLbl = document.querySelector(".scope-ctl .scope-pick .scope-lbl");
    if (scopeLbl) {
      var isConsultant = USER && USER.role_code === "external_consultant";
      scopeLbl.innerHTML = isConsultant
        ? '<span class="ar">نطاق التكليف ▾</span><span class="en">Assignment scope ▾</span>'
        : '<span class="ar">الشركة / المجموعة ▾</span><span class="en">Company / Group ▾</span>';
    }
    var sel = byId("scopeCompany");
    if (sel) {
      var opts =
        '<option value="">' +
        escAttr(STATE.lang === "ar" ? "كل المجموعة" : "Whole group") +
        "</option>";
      STATE.companies.forEach(function (c) {
        opts +=
          '<option value="' +
          c.id +
          '">' +
          escapeHtml(companyName(c)) +
          "</option>";
      });
      sel.innerHTML = opts;
      sel.value = STATE.scopeCompany == null ? "" : String(STATE.scopeCompany);
    }
    var per = byId("scopePeriod");
    if (per) {
      // Every period that appears in a report the user may already see, so a
      // manager sees their own months and the owner sees the group's.
      var seen = {};
      var list = [];
      (STATE.reports || []).forEach(function (r) {
        var key = r.period_year * 12 + (r.period_month - 1);
        if (!seen[key]) {
          seen[key] = true;
          list.push({ key: key, year: r.period_year, month: r.period_month });
        }
      });
      if (STATE.year && STATE.month) {
        var ck = STATE.year * 12 + (STATE.month - 1);
        if (!seen[ck]) list.push({ key: ck, year: STATE.year, month: STATE.month });
      }
      list.sort(function (a, b) { return b.key - a.key; });
      var html = "";
      list.forEach(function (p) {
        var ar = AR_MONTHS[p.month - 1] + " " + toArabicDigits(String(p.year));
        var en = EN_MONTHS[p.month - 1] + " " + p.year;
        html +=
          '<option value="' +
          p.year +
          "-" +
          p.month +
          '">' +
          escapeHtml(STATE.lang === "ar" ? ar : en) +
          "</option>";
      });
      per.innerHTML = html;
      if (STATE.year && STATE.month) {
        per.value = STATE.year + "-" + STATE.month;
      }
    }
  }

  function bindScopeSelects() {
    var sel = byId("scopeCompany");
    if (sel && !sel.getAttribute("data-bound")) {
      sel.setAttribute("data-bound", "1");
      sel.addEventListener("change", function () {
        var v = sel.value;
        STATE.scopeCompany = v === "" ? null : parseInt(v, 10);
        var host = byId("scopeCtl");
        if (host) host.classList.toggle("scoped", STATE.scopeCompany != null);
        syncScopeSelects();
        loadView(STATE.view);
      });
    }
    var per = byId("scopePeriod");
    if (per && !per.getAttribute("data-bound")) {
      per.setAttribute("data-bound", "1");
      per.addEventListener("change", function () {
        var parts = String(per.value).split("-");
        if (parts.length !== 2) return;
        STATE.year = parseInt(parts[0], 10);
        STATE.month = parseInt(parts[1], 10);
        period = "?year=" + STATE.year + "&month=" + STATE.month;
        STATE.loaded = {};
        syncScopeSelects();
        // The period is part of almost every payload, so drop the caches the
        // view renderers guard on and rebuild the current screen.
        Promise.all([ensureReports(), loadDashboard().catch(function () {})])
          .then(function () { return loadView(STATE.view); });
      });
    }
  }

  // Rows a list renderer may show, narrowed by the header entity picker. This
  // filters only what the user was already served.
  function scopeFilter(rows, key) {
    if (STATE.scopeCompany == null) return rows || [];
    var k = key || "company_id";
    return (rows || []).filter(function (r) {
      return r && r[k] === STATE.scopeCompany;
    });
  }

  // ---- list pagination --------------------------------------------------
  // The deck fixes one pager for every list: 25 rows a page with 10/25/50/100
  // and the same [تطبيق] [حفظ المرشح باسمي] [مسح] [تصدير النتائج] cluster
  // (slides 134-136). The pager is the only thing this adds: the rows still
  // come from the same scoped fetch, and each list owns its own sort.

  var PAGE_SIZES = [10, 25, 50, 100];

  function pageSize() {
    return STATE.pageSize || 25;
  }

  function pageFor(key) {
    STATE.page = STATE.page || {};
    return STATE.page[key] || 1;
  }

  // Filter values a list is currently narrowed by, kept per list so switching
  // views never inherits another list's filters.
  function listFilters(key) {
    STATE.filters = STATE.filters || {};
    if (!STATE.filters[key]) STATE.filters[key] = {};
    return STATE.filters[key];
  }

  // Saved named filters, persisted per user in localStorage (the deck's
  // [حفظ المرشح باسمي]). They are a convenience over the current period and
  // never widen scope: applying one only restores the same filter values.
  function savedFilters(key) {
    try {
      var raw = localStorage.getItem("safir.filters.v1." + key);
      return raw ? JSON.parse(raw) : [];
    } catch (e) {
      return [];
    }
  }

  function saveFilter(key) {
    var values = listFilters(key);
    var hasAny = Object.keys(values).some(function (k) {
      return values[k] !== "" && values[k] != null;
    });
    if (!hasAny) {
      toast(STATE.lang === "ar" ? "لا يوجد مرشح لحفظه." : "Nothing to save yet.", "err");
      return;
    }
    var name = window.prompt(
      STATE.lang === "ar" ? "اسم المرشح:" : "Filter name:",
      (STATE.lang === "ar" ? "مرشح " : "Filter ") + new Date().toLocaleDateString(),
    );
    if (!name) return;
    var list = savedFilters(key).filter(function (s) { return s.name !== name; });
    list.push({ name: name, values: JSON.parse(JSON.stringify(values)) });
    try {
      localStorage.setItem("safir.filters.v1." + key, JSON.stringify(list));
    } catch (e) {
      /* storage disabled */
    }
    toast(STATE.lang === "ar" ? "تم حفظ المرشح: " + name : "Filter saved: " + name, "ok");
    if (typeof renderPaged === "function") refreshActiveView();
  }

  function applyFilter(key) {
    var host = byId("listFilter-" + key);
    if (!host) return;
    var values = listFilters(key);
    host.querySelectorAll("[data-filter]").forEach(function (el) {
      values[el.getAttribute("data-filter")] = el.value;
    });
    STATE.page[key] = 1;
    refreshActiveView();
  }

  function clearFilter(key) {
    STATE.filters = STATE.filters || {};
    STATE.filters[key] = {};
    STATE.page = STATE.page || {};
    STATE.page[key] = 1;
    refreshActiveView();
  }

  function applySavedFilter(key, name) {
    var found = savedFilters(key).filter(function (s) { return s.name === name; })[0];
    if (!found) return;
    STATE.filters[key] = JSON.parse(JSON.stringify(found.values));
    STATE.page[key] = 1;
    refreshActiveView();
  }

  // ``spec`` is a list of {key, ar, en, options:[{value,ar,en}]} or
  // {key, ar, en, type:"search"} entries. The search field matches any of the
  // row's text fields (slide 134 "حقول البحث"); the selects match equality.
  function filterBarHtml(key, spec) {
    var values = listFilters(key);
    var html = '<div class="list-filters" id="listFilter-' + escAttr(key) + '">';
    spec.forEach(function (f) {
      var val = values[f.key] == null ? "" : values[f.key];
      if (f.type === "search") {
        html +=
          '<label class="lf-field lf-search">' +
          '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.2-3.2"/></svg>' +
          '<input class="av-input" data-filter="' + escAttr(f.key) + '" value="' + escAttr(val) + '" placeholder="' +
          escAttr(STATE.lang === "ar" ? f.ar : f.en) + '" aria-label="' + escAttr(f.ar) + '"></label>';
        return;
      }
      // A select with no choices is a dead control, so it is left out until the
      // data carries a value to filter on (the deck's lists are per-role and
      // data-driven).
      if (!f.options.length) return;
      var opts = '<option value="">' + escAttr(STATE.lang === "ar" ? f.ar : f.en) + "</option>";
      f.options.forEach(function (o) {
        opts +=
          '<option value="' + escAttr(o.value) + '"' + (o.value === val ? " selected" : "") + ">" +
          escapeHtml(STATE.lang === "ar" ? o.ar : o.en || o.ar) + "</option>";
      });
      html += '<select class="av-select lf-select" data-filter="' + escAttr(f.key) + '" aria-label="' + escAttr(f.ar) + '">' + opts + "</select>";
    });
    var saved = savedFilters(key);
    if (saved.length) {
      var sOpts = '<option value="">' + escAttr(STATE.lang === "ar" ? "مرشحاتي المحفوظة" : "My saved filters") + "</option>";
      saved.forEach(function (s) {
        sOpts += '<option value="' + escAttr(s.name) + '">' + escapeHtml(s.name) + "</option>";
      });
      html += '<select class="av-select lf-select" data-saved-filter aria-label="' +
        escAttr(STATE.lang === "ar" ? "مرشحاتي المحفوظة" : "My saved filters") + '">' + sOpts + "</select>";
    }
    html += '<div class="lf-actions">';
    html += '<button type="button" class="lf-btn primary" data-filter-apply>' + dual("تطبيق", "Apply") + "</button>";
    html += '<button type="button" class="lf-btn" data-filter-save>' + dual("حفظ المرشح باسمي", "Save filter") + "</button>";
    html += '<button type="button" class="lf-btn" data-filter-clear>' + dual("مسح", "Clear") + "</button>";
    // "عند سماح التصدير" — the button only appears when the role may export.
    if (has("analytics.export")) {
      html += '<button type="button" class="lf-btn" data-filter-export>' + dual("تصدير النتائج", "Export results") + "</button>";
    }
    html += "</div></div>";
    return html;
  }

  function bindFilterBar(host, key, rows) {
    var bar = host.querySelector("#listFilter-" + key);
    if (!bar) return;
    var apply = bar.querySelector("[data-filter-apply]");
    var save = bar.querySelector("[data-filter-save]");
    var clear = bar.querySelector("[data-filter-clear]");
    var exp = bar.querySelector("[data-filter-export]");
    var savedSel = bar.querySelector("[data-saved-filter]");
    var search = bar.querySelector('input[data-filter]');
    if (apply) apply.addEventListener("click", function () { applyFilter(key); });
    if (save) save.addEventListener("click", function () { saveFilter(key); });
    if (clear) clear.addEventListener("click", function () { clearFilter(key); });
    if (exp) exp.addEventListener("click", function () { exportListCsv(key, rows); });
    if (savedSel) {
      savedSel.addEventListener("change", function () {
        if (savedSel.value) applySavedFilter(key, savedSel.value);
      });
    }
    if (search) {
      // Enter applies, matching the deck's form-submit behaviour, and the
      // value is only committed on apply so a half-typed term never re-filters.
      search.addEventListener("keydown", function (e) {
        if (e.key === "Enter") {
          e.preventDefault();
          applyFilter(key);
        }
      });
    }
  }

  // Deck slides 130-132: "كل مخرج يحمل: الفترة والجهة والعملة وحالة البيانات
  // وآخر تحديث ومسودة/معتمد ورقم النسخة." The export is the caller's own scoped
  // list, so it is prefixed with the period and entity the list was rendered
  // for rather than left bare.
  function exportMeta(key) {
    var period = STATE.year && STATE.month ? STATE.year + "-" + STATE.month : "—";
    var entity = STATE.scopeCompany == null
      ? (STATE.lang === "ar" ? "كل المجموعة" : "Whole group")
      : (function () {
          var c = companyById(STATE.scopeCompany);
          return c ? (STATE.lang === "ar" ? c.name_ar : c.name_en || c.name_ar) : String(STATE.scopeCompany);
        })();
    return [
      "# " + (STATE.lang === "ar" ? "الفترة" : "Period") + ": " + period,
      "# " + (STATE.lang === "ar" ? "الجهة" : "Entity") + ": " + entity,
      "# " + (STATE.lang === "ar" ? "آخر تحديث" : "Generated") + ": " + new Date().toISOString(),
      "# " + (STATE.lang === "ar" ? "الحالة" : "State") + ": " +
        (STATE.lang === "ar" ? "بيانات مسحوبة من النظام" : "data read from the system"),
    ].join("\r\n") + "\r\n";
  }

  function exportListCsv(key, rows) {
    var lines = [];
    if (!rows || !rows.length) {
      toast(STATE.lang === "ar" ? "لا توجد نتائج للتصدير." : "No results to export.", "err");
      return;
    }
    var cols = Object.keys(rows[0]).filter(function (c) {
      return typeof rows[0][c] !== "object";
    });
    lines.push(cols.join(","));
    rows.forEach(function (r) {
      lines.push(
        cols
          .map(function (c) {
            var v = r[c] == null ? "" : String(r[c]);
            return '"' + v.replace(/"/g, '""') + '"';
          })
          .join(","),
      );
    });
    var blob = new Blob(["\ufeff" + exportMeta(key) + lines.join("\r\n")], { type: "text/csv;charset=utf-8" });
    var url = URL.createObjectURL(blob);
    var a = document.createElement("a");
    a.href = url;
    a.download = "safir-" + key + "-" + STATE.year + "-" + STATE.month + ".csv";
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    toast(STATE.lang === "ar" ? "تم تصدير النتائج." : "Results exported.", "ok");
  }

  function pagerHtml(key, page, pages, total, size) {
    var num = function (v) {
      return STATE.lang === "ar" ? toArabicDigits(String(v)) : String(v);
    };
    var opts = PAGE_SIZES.map(function (s) {
      return '<option value="' + s + '"' + (s === size ? " selected" : "") + ">" + num(s) + "</option>";
    }).join("");
    return (
      '<div class="pager" data-pager="' + escAttr(key) + '">' +
      '<span class="pager-total">' +
      dual(num(total) + " نتيجة", total + " results") +
      "</span>" +
      '<label class="pager-size">' +
      dual("لكل صفحة", "Per page") +
      '<select class="av-select" data-page-size>' + opts + "</select></label>" +
      '<div class="pager-nav">' +
      '<button type="button" class="pg-btn" data-page-prev' + (page <= 1 ? " disabled" : "") + ">" +
      dual("السابق", "Prev") + "</button>" +
      '<span class="pg-now">' + num(page) + " / " + num(pages) + "</span>" +
      '<button type="button" class="pg-btn" data-page-next' + (page >= pages ? " disabled" : "") + ">" +
      dual("التالي", "Next") + "</button>" +
      "</div></div>"
    );
  }

  // Render ``rows`` into ``host`` a page at a time, then wire the pager. The
  // caller keeps ownership of the row markup and of the per-row click binding
  // (``bindFn`` runs on each page so handlers follow the rows that are shown).
  function renderPaged(host, key, rows, rowFn, bindFn, spec) {
    var size = pageSize();
    var pages = Math.max(1, Math.ceil(rows.length / size));
    var page = Math.min(pageFor(key), pages);
    STATE.page[key] = page;
    var start = (page - 1) * size;
    var slice = rows.slice(start, start + size);
    host.innerHTML =
      (spec ? filterBarHtml(key, spec) : "") +
      (rows.length
        ? slice.map(rowFn).join("") + pagerHtml(key, page, pages, rows.length, size)
        : '<div class="lf-empty">' +
          emptyHtml("لا توجد نتائج مطابقة للمرشحات.", "No rows match the filters.") +
          "</div>");
    if (bindFn) bindFn(host, slice);
    if (spec) bindFilterBar(host, key, rows);
    var pager = host.querySelector("[data-pager]");
    if (!pager) return;
    var prev = pager.querySelector("[data-page-prev]");
    var next = pager.querySelector("[data-page-next]");
    var sel = pager.querySelector("[data-page-size]");
    var again = function () { renderPaged(host, key, rows, rowFn, bindFn, spec); };
    if (prev) {
      prev.addEventListener("click", function () {
        STATE.page[key] = Math.max(1, pageFor(key) - 1);
        again();
      });
    }
    if (next) {
      next.addEventListener("click", function () {
        STATE.page[key] = Math.min(pages, pageFor(key) + 1);
        again();
      });
    }
    if (sel) {
      sel.addEventListener("change", function () {
        STATE.pageSize = parseInt(sel.value, 10) || 25;
        STATE.page[key] = 1;
        again();
      });
    }
  }

  // The deck fixes a secondary sort by ID so equal keys keep a stable, paged
  // order (slides 134-136: "ترتيب ثانوي بالمعرف"). Without it, a tie could
  // shuffle rows between page renders and hide a row from the reader.
  // (Named to avoid shadowing the ``byId`` DOM lookup helper.)
  function byIdAsc(a, b) {
    return (a.id || 0) - (b.id || 0);
  }

  // Narrow ``rows`` by the list's own filters. A search entry matches if any of
  // its ``fields`` contains the term; selects match equality on one field.
  function applyListFilters(rows, key, spec) {
    var values = listFilters(key);
    return (rows || []).filter(function (r) {
      for (var i = 0; i < spec.length; i++) {
        var f = spec[i];
        var v = values[f.key];
        if (v == null || v === "") continue;
        if (f.type === "search") {
          var needle = String(v).toLowerCase();
          var hit = (f.fields || []).some(function (field) {
            var cell = r[field];
            return cell != null && String(cell).toLowerCase().indexOf(needle) >= 0;
          });
          if (!hit) return false;
        } else {
          var actual = f.resolve ? f.resolve(r) : r[f.field || f.key];
          if (String(actual == null ? "" : actual) !== String(v)) return false;
        }
      }
      return true;
    });
  }

  // Distinct values for a select, in first-seen order, so a filter never
  // offers a value no visible row carries (the deck's lists are per-role).
  // ``label`` may return a string or a {ar, en} pair.
  function distinctOptions(rows, get, label) {
    var seen = {};
    var out = [];
    (rows || []).forEach(function (r) {
      var v = get(r);
      if (v == null || v === "" || seen[v]) return;
      seen[v] = true;
      var l = label ? label(v) : v;
      var ar = l && l.ar != null ? l.ar : l;
      var en = l && l.en != null ? l.en : l;
      out.push({ value: String(v), ar: String(ar), en: String(en) });
    });
    return out;
  }

  // Company lifecycle labels. The payload stores the bare code, so map it for
  // display; an unknown code falls through unchanged rather than blanking.
  function companyStatusLabel(status) {
    var map = {
      active: { ar: "نشطة", en: "Active" },
      inactive: { ar: "موقوفة", en: "Inactive" },
      suspended: { ar: "معلّقة", en: "Suspended" },
      closed: { ar: "مغلقة", en: "Closed" },
    };
    return map[String(status || "").toLowerCase()] || { ar: status, en: status };
  }

  // Employee lifecycle labels, mirroring the S11 badge map.
  function employeeStatusLabel(status) {
    var map = {
      active: { ar: "نشط", en: "Active" },
      on_leave: { ar: "في إجازة", en: "On leave" },
      terminated: { ar: "منتهٍ", en: "Terminated" },
    };
    return map[String(status || "").toLowerCase()] || { ar: status, en: status };
  }

  // Advisory-session lifecycle labels, mirroring the S19 badge map.
  function advisorSessionStatusLabel(status) {
    var map = {
      scheduled: { ar: "مجدولة", en: "Scheduled" },
      completed: { ar: "مكتملة", en: "Completed" },
      cancelled: { ar: "ملغاة", en: "Cancelled" },
    };
    return map[String(status || "").toLowerCase()] || { ar: status, en: status };
  }

  function companyFilterOption() {
    return {
      key: "company",
      ar: "الشركة",
      en: "Company",
      field: "company_id",
      options: (STATE.companies || []).map(function (c) {
        return { value: String(c.id), ar: c.name_ar || c.name_en || "", en: c.name_en || c.name_ar || "" };
      }),
    };
  }

  // Slide 134 fixes "قطاع" and "عملة" among the report filters. Both attributes
  // live on the company, so a report row resolves them through its company id.
  function sectorByCompany() {
    var map = {};
    (STATE.companies || []).forEach(function (c) { map[c.id] = c.sector; });
    return map;
  }

  function currencyByCompany() {
    var map = {};
    (STATE.companies || []).forEach(function (c) { map[c.id] = c.currency; });
    return map;
  }

  // Slide 134/135/136 fix the filter set per list family. Options that have no
  // reliable label source (e.g. an assignee name the payload omits) are left
  // out rather than shown as a bare id.
  function reportsFilterSpec() {
    var periods = distinctOptions(
      STATE.reports || [],
      function (r) { return r.period_year + "-" + r.period_month; },
      function (v) {
        var p = v.split("-");
        var m = parseInt(p[1], 10);
        return {
          ar: AR_MONTHS[m - 1] + " " + toArabicDigits(p[0]),
          en: EN_MONTHS[m - 1] + " " + p[0],
        };
      },
    );
    return [
      { key: "q", type: "search", ar: "رقم / عنوان / فترة", en: "No. / title / period",
        fields: ["id", "status", "company_name_ar", "company_name_en", "period_year", "period_month"] },
      companyFilterOption(),
      // Slide 134 also fixes "قطاع" and "عملة" among the report filters; both
      // live on the company, so they are derived from the visible reports'
      // companies rather than a separate catalogue read.
      { key: "sector", ar: "القطاع", en: "Sector",
        resolve: function (r) { return sectorByCompany()[r.company_id]; },
        options: distinctOptions(STATE.reports || [], function (r) { return sectorByCompany()[r.company_id]; },
          function (v) { return sectorLabel(v); }) },
      { key: "currency", ar: "العملة", en: "Currency",
        resolve: function (r) { return currencyByCompany()[r.company_id]; },
        options: distinctOptions(STATE.reports || [], function (r) { return currencyByCompany()[r.company_id]; }) },
      { key: "status", ar: "الحالة", en: "Status", field: "status",
        options: [
          { value: "draft", ar: "مسودة", en: "Draft" },
          { value: "submitted", ar: "مُرسل", en: "Submitted" },
          { value: "under_review", ar: "قيد المراجعة", en: "Under review" },
          { value: "reviewed", ar: "تمت المراجعة", en: "Reviewed" },
          { value: "returned", ar: "أُعيد للتصحيح", en: "Returned" },
          { value: "locked", ar: "مقفل", en: "Locked" },
          { value: "cancelled", ar: "ملغى", en: "Cancelled" },
        ] },
      { key: "period", ar: "الفترة", en: "Period", options: periods,
        resolve: function (r) { return r.period_year + "-" + r.period_month; } },
      { key: "version", ar: "الإصدار", en: "Version", field: "version_number",
        options: distinctOptions(STATE.reports || [], function (r) { return r.version_number; }) },
      // Slide 134 lists "مراجع" among the report filters; the serialiser now
      // carries the financial reviewer's name on the report's review block.
      { key: "reviewer", ar: "المراجع", en: "Reviewer",
        resolve: function (r) { return (r.financial_review || {}).reviewer_id; },
        options: distinctOptions(
          (STATE.reports || []).filter(function (r) { return r.financial_review; }),
          function (r) { return r.financial_review.reviewer_id; },
          function (v) {
            var r = (STATE.reports || []).filter(function (x) {
              return x.financial_review && String(x.financial_review.reviewer_id) === String(v);
            })[0] || {};
            var fr = r.financial_review || {};
            return { ar: fr.reviewer_name_ar || fr.reviewer_name_en || "#" + plainNum(v),
                     en: fr.reviewer_name_en || fr.reviewer_name_ar || "#" + plainNum(v) };
          }) },
    ];
  }

  function supportFilterSpec() {
    return [
      { key: "q", type: "search", ar: "رقم / عنوان / نوع / شركة", en: "No. / title / type / company",
        fields: ["id", "title", "category", "company_name_ar", "company_name_en"] },
      companyFilterOption(),
      { key: "category", ar: "النوع", en: "Type", field: "category",
        options: distinctOptions(STATE.support || [], function (r) { return r.category; },
          function (v) { return deptLabel(v); }) },
      // Slide 134 lists "مسؤول" among the request filters; the serialiser now
      // carries the assignee's name so the select reads as a person, not an id.
      { key: "assignee", ar: "المسؤول", en: "Assignee", field: "assigned_to_id",
        options: distinctOptions(STATE.support || [], function (r) { return r.assigned_to_id; },
          function (v) {
            var r = (STATE.support || []).filter(function (x) { return String(x.assigned_to_id) === String(v); })[0] || {};
            return { ar: r.assigned_to_name_ar || r.assigned_to_name_en || "#" + plainNum(v),
                     en: r.assigned_to_name_en || r.assigned_to_name_ar || "#" + plainNum(v) };
          }) },
      { key: "status", ar: "الحالة", en: "Status", field: "status",
        options: [
          { value: "new", ar: "جديد", en: "New" },
          { value: "in_progress", ar: "قيد التنفيذ", en: "In progress" },
          { value: "completed", ar: "مكتمل", en: "Completed" },
          { value: "closed", ar: "مغلق", en: "Closed" },
        ] },
    ];
  }

  function subsidiariesFilterSpec() {
    return [
      { key: "q", type: "search", ar: "الاسم / رقم التسجيل", en: "Name / registration no.",
        fields: ["legal_name_ar", "legal_name_en", "name_ar", "name_en", "commercial_registration"] },
      { key: "country", ar: "الدولة", en: "Country", field: "country",
        options: distinctOptions(STATE.companies || [], function (c) { return c.country; }) },
      { key: "sector", ar: "القطاع", en: "Sector", field: "sector",
        options: distinctOptions(STATE.companies || [], function (c) { return c.sector; },
          function (v) { return sectorLabel(v); }) },
      { key: "status", ar: "الحالة", en: "Status", field: "status",
        options: distinctOptions(STATE.companies || [], function (c) { return c.status; },
          function (v) { return companyStatusLabel(v); }) },
      // Slide 134 fixes "مدير" among the company-list filters; the manager is
      // derived on the backend (primary company grant, then lowest id) and
      // arrives on each company row as manager_user_id / manager_name_*.
      { key: "manager", ar: "المدير", en: "Manager", field: "manager_user_id",
        options: distinctOptions(STATE.companies || [], function (c) { return c.manager_user_id; },
          function (v) {
            var c = (STATE.companies || []).filter(function (x) { return String(x.manager_user_id) === String(v); })[0] || {};
            return { ar: c.manager_name_ar || c.manager_name_en || "#" + plainNum(v),
                     en: c.manager_name_en || c.manager_name_ar || "#" + plainNum(v) };
          }) },
      { key: "currency", ar: "العملة", en: "Currency", field: "currency",
        options: distinctOptions(STATE.companies || [], function (c) { return c.currency; }) },
    ];
  }

  // The deck's remaining list families (slides 134-136). Each entry only offers
  // a select when the payload actually carries a label for it; the assignee /
  // reviewer / executor names come from the enriched serialisers, so those
  // selects now show a person instead of a bare id.
  function leadsFilterSpec() {
    var rows = STATE.leads || [];
    return [
      { key: "q", type: "search", ar: "الاسم / المرجع / البريد", en: "Name / reference / email",
        fields: ["full_name", "reference", "email", "phone", "company_name"] },
      { key: "company", ar: "الشركة", en: "Company", field: "routed_company_id",
        options: distinctOptions(rows, function (r) { return r.routed_company_id; },
          function (v) { return { ar: companyNameById(v), en: companyNameById(v) }; }) },
      { key: "manager", ar: "المسؤول", en: "Assignee", field: "assigned_to_id",
        options: distinctOptions(rows, function (r) { return r.assigned_to_id; },
          function (v) {
            var r = rows.filter(function (x) { return String(x.assigned_to_id) === String(v); })[0] || {};
            return { ar: r.assigned_to_name_ar || r.assigned_to_name_en || "#" + plainNum(v),
                     en: r.assigned_to_name_en || r.assigned_to_name_ar || "#" + plainNum(v) };
          }) },
      { key: "status", ar: "الحالة", en: "Status", field: "status",
        options: distinctOptions(rows, function (r) { return r.status; },
          function (v) { return leadLabel(LEAD_STATUS, v); }) },
      { key: "source", ar: "المصدر", en: "Source", field: "source",
        options: distinctOptions(rows, function (r) { return r.source; }) },
      { key: "service", ar: "الخدمة", en: "Service", field: "service_type",
        options: distinctOptions(rows, function (r) { return r.service_type; },
          function (v) { return leadLabel(LEAD_SERVICE, v); }) },
      // Slide 134 "العملاء / الحملات" fixes فترة on the combined customer /
      // campaign family. A lead has no follow-up date column, so its period is
      // the month it was captured (the campaign half reads its own start date).
      { key: "period", ar: "الفترة", en: "Period",
        resolve: function (r) { return r.created_at ? String(r.created_at).slice(0, 7) : ""; },
        options: distinctOptions(rows, function (r) {
          return r.created_at ? String(r.created_at).slice(0, 7) : "";
        }) },
    ];
  }

  // Slide 134 "العملاء / الحملات": the campaign list filters by company,
  // platform, status and period, and searches the campaign name / source.
  function campaignsFilterSpec() {
    var rows = STATE.campaigns || [];
    return [
      { key: "q", type: "search", ar: "اسم الحملة / الهدف / المنصة", en: "Campaign name / goal / platform",
        fields: ["name", "platform", "goal"] },
      companyFilterOption(),
      { key: "platform", ar: "المنصة", en: "Platform", field: "platform",
        options: distinctOptions(rows, function (r) { return r.platform; }) },
      { key: "status", ar: "الحالة", en: "Status", field: "status",
        options: [
          { value: "planned", ar: "مخططة", en: "Planned" },
          { value: "active", ar: "نشطة", en: "Active" },
          { value: "completed", ar: "مكتملة", en: "Completed" },
          { value: "cancelled", ar: "ملغاة", en: "Cancelled" },
        ] },
      { key: "period", ar: "الفترة", en: "Period",
        resolve: function (r) { return r.start_date ? String(r.start_date).slice(0, 7) : ""; },
        options: distinctOptions(rows, function (r) {
          return r.start_date ? String(r.start_date).slice(0, 7) : "";
        }) },
    ];
  }

  function employeesFilterSpec() {
    var rows = (STATE.hr && STATE.hr.employees) || [];
    var depts = STATE.departments || [];
    var deptById = {};
    depts.forEach(function (d) { deptById[d.id] = d; });
    var countryByCompany = {};
    (STATE.companies || []).forEach(function (c) { countryByCompany[c.id] = c.country; });
    return [
      { key: "q", type: "search", ar: "الاسم / الرقم الوظيفي / المسمى", en: "Name / employee no. / title",
        fields: ["full_name_ar", "full_name_en", "employee_code", "job_title"] },
      companyFilterOption(),
      // Slide 101/135 "جهة، دولة، جنسية، إدارة، حالة": the country is the
      // company's country, the department resolves through the department
      // directory (empty when the role cannot read departments, so the select
      // is omitted rather than shown as a bare id).
      { key: "country", ar: "الدولة", en: "Country",
        resolve: function (r) { return countryByCompany[r.company_id]; },
        options: distinctOptions(rows, function (r) { return countryByCompany[r.company_id]; }) },
      { key: "nationality", ar: "الجنسية", en: "Nationality", field: "nationality",
        options: distinctOptions(rows, function (r) { return r.nationality; }) },
      { key: "department", ar: "الإدارة", en: "Department", field: "department_id",
        options: distinctOptions(rows, function (r) { return r.department_id; },
          function (v) {
            var d = deptById[v];
            return d ? { ar: d.name_ar, en: d.name_en || d.name_ar } : "#" + plainNum(v);
          }) },
      { key: "status", ar: "الحالة", en: "Status", field: "status",
        options: distinctOptions(rows, function (r) { return r.status; },
          function (v) { return employeeStatusLabel(v); }) },
      // Slide 135 "الموظفون / التوطين" also fixes فترة and احتساب. The employee
      // carries a hire date, which is the period the record is filed under; the
      // localisation basis (احتساب) has no column on the row, so that select is
      // omitted rather than shown as a dead control.
      { key: "period", ar: "الفترة", en: "Period",
        resolve: function (r) { return r.hire_date ? String(r.hire_date).slice(0, 7) : ""; },
        options: distinctOptions(rows, function (r) {
          return r.hire_date ? String(r.hire_date).slice(0, 7) : "";
        }) },
    ];
  }

  function tasksFilterSpec() {
    var rows = (STATE.ops && STATE.ops.tasks) || [];
    return [
      { key: "q", type: "search", ar: "العنوان", en: "Title", fields: ["title", "description"] },
      companyFilterOption(),
      { key: "assignee", ar: "المكلف", en: "Assignee", field: "assignee_id",
        options: distinctOptions(rows, function (r) { return r.assignee_id; },
          function (v) {
            var r = rows.filter(function (x) { return String(x.assignee_id) === String(v); })[0] || {};
            return { ar: r.assignee_name_ar || r.assignee_name_en || "#" + plainNum(v),
                     en: r.assignee_name_en || r.assignee_name_ar || "#" + plainNum(v) };
          }) },
      // Slide 134 "الطلبات / المهام" fixes أولوية and فترة in addition to the
      // assignee, type and status selects.
      { key: "priority", ar: "الأولوية", en: "Priority", field: "priority",
        options: [
          { value: "low", ar: "منخفضة", en: "Low" },
          { value: "normal", ar: "عادية", en: "Normal" },
          { value: "high", ar: "عالية", en: "High" },
        ] },
      { key: "period", ar: "الفترة", en: "Period",
        resolve: function (r) { return r.due_date ? String(r.due_date).slice(0, 7) : ""; },
        options: distinctOptions(rows, function (r) {
          return r.due_date ? String(r.due_date).slice(0, 7) : "";
        }) },
      { key: "status", ar: "الحالة", en: "Status", field: "status",
        options: distinctOptions(rows, function (r) { return r.status; }) },
    ];
  }

  function requestsFilterSpec() {
    // The form and status selects already live in the requests toolbar and are
    // applied server-side; the generic bar adds the deck's per-list search,
    // company and period (slide 136) without duplicating those two controls.
    var rows = (STATE.submissions && STATE.submissions.items) || [];
    return [
      { key: "q", type: "search", ar: "العنوان / المرجع / الجهة", en: "Title / reference / company",
        fields: ["title", "reference", "company_name_ar", "company_name_en"] },
      companyFilterOption(),
      { key: "period", ar: "الفترة", en: "Period",
        resolve: function (r) { return r.submitted_at ? String(r.submitted_at).slice(0, 7) : ""; },
        options: distinctOptions(rows, function (r) {
          return r.submitted_at ? String(r.submitted_at).slice(0, 7) : "";
        }) },
    ];
  }

  function feedbackFilterSpec() {
    // The feedback list merges three sources; the native toolbar select already
    // narrows by source, so the generic bar adds the deck's text search only.
    return [
      { key: "q", type: "search", ar: "العنوان / الحالة", en: "Title / status",
        fields: ["title", "status", "sub"] },
    ];
  }

  function kpisFilterSpec() {
    var rows = STATE.kpis || [];
    var sectorByCompanyId = {};
    (STATE.companies || []).forEach(function (c) { sectorByCompanyId[c.id] = c.sector; });
    return [
      // Slide 136 "المؤشرات / العملات": search by name / definition / metric key
      // and filter by sector, company, period, status and unit. The KPI record
      // carries no currency of its own, so "العملة" is represented by its unit
      // (the only comparable label the payload has) rather than invented.
      { key: "q", type: "search", ar: "الاسم / التعريف / المعرّف", en: "Name / definition / key",
        fields: ["code", "name_ar", "name_en", "calculation_method", "metric_key"] },
      { key: "sector", ar: "القطاع", en: "Sector",
        resolve: function (r) { return sectorByCompanyId[r.company_id]; },
        options: distinctOptions(rows, function (r) { return sectorByCompanyId[r.company_id]; },
          function (v) { return sectorLabel(v); }) },
      { key: "company", ar: "الشركة", en: "Company", field: "company_id",
        options: distinctOptions(rows, function (r) { return r.company_id; },
          function (v) { return { ar: companyNameById(v), en: companyNameById(v) }; }) },
      { key: "period", ar: "الدورية", en: "Periodicity", field: "period_label",
        options: distinctOptions(rows, function (r) { return r.period_label; }) },
      { key: "active", ar: "الحالة", en: "Status",
        resolve: function (r) { return r.is_active ? "1" : "0"; },
        options: [
          { value: "1", ar: "معتمد", en: "Active" },
          { value: "0", ar: "موقوف", en: "Inactive" },
        ] },
      { key: "unit", ar: "الوحدة", en: "Unit", field: "unit",
        options: distinctOptions(rows, function (r) { return r.unit; }) },
    ];
  }

  function projectsFilterSpec() {
    var rows = STATE.projects || [];
    return [
      { key: "q", type: "search", ar: "الاسم / الوصف", en: "Name / description", fields: ["name", "description"] },
      companyFilterOption(),
      { key: "type", ar: "النوع", en: "Type", field: "record_type",
        options: distinctOptions(rows, function (r) { return r.record_type; },
          function (v) { var t = PROJECT_TYPE_LABEL[v]; return t ? { ar: t[0], en: t[1] } : v; }) },
      { key: "status", ar: "الحالة", en: "Status", field: "status",
        options: distinctOptions(rows, function (r) { return r.status; }) },
    ];
  }

  function decisionsFilterSpec() {
    var rows = STATE.decisions || [];
    return [
      { key: "q", type: "search", ar: "الرقم / العنوان", en: "Number / title", fields: ["number", "title"] },
      // Slide 135 "الفرص / القرارات" opens the filter set with شركة; the
      // decision carries an optional company_id and the view already loads the
      // company directory, so the select is offered when a row names a company.
      companyFilterOption(),
      { key: "executor", ar: "المسؤول", en: "Executor", field: "executor_user_id",
        options: distinctOptions(rows, function (r) { return r.executor_user_id; },
          function (v) {
            var r = rows.filter(function (x) { return String(x.executor_user_id) === String(v); })[0] || {};
            return { ar: r.executor_name_ar || r.executor_name_en || "#" + plainNum(v),
                     en: r.executor_name_en || r.executor_name_ar || "#" + plainNum(v) };
          }) },
      { key: "status", ar: "الحالة", en: "Status", field: "status",
        options: distinctOptions(rows, function (r) { return r.status; }) },
      // Slide 135 "الفرص / القرارات" fixes فترة (and a type/impact dimension);
      // the decision carries a due date, which is the period it is followed up.
      { key: "period", ar: "الفترة", en: "Period",
        resolve: function (r) { return r.due_date ? String(r.due_date).slice(0, 7) : ""; },
        options: distinctOptions(rows, function (r) {
          return r.due_date ? String(r.due_date).slice(0, 7) : "";
        }) },
    ];
  }

  function advisoriesFilterSpec() {
    var rows = STATE.advisories || [];
    return [
      // Slide 136 "جلسات المستشار": search the advisor / topic, filter by
      // assignee ("مسند إليه"), status and scheduled date.
      { key: "q", type: "search", ar: "المستشار / الموضوع", en: "Advisor / topic",
        fields: ["advisor_name_ar", "advisor_name_en", "topic"] },
      companyFilterOption(),
      { key: "advisor", ar: "مسند إليه", en: "Assigned to", field: "advisor_user_id",
        options: distinctOptions(rows, function (r) { return r.advisor_user_id; },
          function (v) {
            var r = rows.filter(function (x) { return String(x.advisor_user_id) === String(v); })[0] || {};
            return { ar: r.advisor_name_ar || r.advisor_name_en || "#" + plainNum(v),
                     en: r.advisor_name_en || r.advisor_name_ar || "#" + plainNum(v) };
          }) },
      { key: "status", ar: "الحالة", en: "Status", field: "status",
        options: distinctOptions(rows, function (r) { return r.status; },
          function (v) { return advisorSessionStatusLabel(v); }) },
      { key: "scheduled", ar: "الموعد", en: "Scheduled", field: "scheduled_date",
        resolve: function (r) { return r.scheduled_at ? String(r.scheduled_at).slice(0, 10) : ""; },
        options: distinctOptions(rows, function (r) {
          return r.scheduled_at ? String(r.scheduled_at).slice(0, 10) : "";
        }) },
    ];
  }

  function documentsFilterSpec() {
    var rows = (STATE.documentsPage && STATE.documentsPage.items) || [];
    return [
      { key: "q", type: "search", ar: "الاسم / الجهة", en: "Name / company",
        fields: ["original_filename", "title_ar", "title_en", "company_name_ar", "company_name_en"] },
      { key: "expiry", ar: "الانتهاء", en: "Expiry", field: "expiry_state",
        options: [
          { value: "expired", ar: "منتهي", en: "Expired" },
          { value: "expiring_soon", ar: "قريب الانتهاء", en: "Expiring soon" },
          { value: "valid", ar: "ساري", en: "Valid" },
        ] },
    ];
  }

  // Slide 135 "حسابات / ميزانية / مراكز" and "إيرادات / مصروفات / ذمم". The
  // accounting payloads are per-company reads, so the selects are built from the
  // rows actually returned rather than from a fixed catalogue.
  function accountsFilterSpec() {
    var rows = STATE.acctAccounts || [];
    var typeLabel = {
      asset: ["أصول", "Asset"],
      liability: ["التزامات", "Liability"],
      equity: ["حقوق ملكية", "Equity"],
      revenue: ["إيرادات", "Revenue"],
      expense: ["مصروفات", "Expense"],
    };
    return [
      { key: "q", type: "search", ar: "اسم الحساب / الرمز", en: "Account name / code",
        fields: ["code", "name_ar", "name_en"] },
      companyFilterOption(),
      { key: "type", ar: "التصنيف", en: "Type", field: "account_type",
        options: distinctOptions(rows, function (r) { return r.account_type; },
          function (v) { var t = typeLabel[v]; return t ? { ar: t[0], en: t[1] } : v; }) },
      // Slide 135 "حسابات / ميزانية / مراكز" also fixes عملة and حالة.
      { key: "currency", ar: "العملة", en: "Currency", field: "currency",
        options: distinctOptions(rows, function (r) { return r.currency; }) },
      { key: "status", ar: "الحالة", en: "Status",
        resolve: function (r) { return r.is_active ? "1" : "0"; },
        options: [
          { value: "1", ar: "نشط", en: "Active" },
          { value: "0", ar: "موقوف", en: "Inactive" },
        ] },
    ];
  }

  function journalsFilterSpec() {
    var rows = STATE.acctJournals || [];
    return [
      { key: "q", type: "search", ar: "رقم القيد / الوصف", en: "Journal no. / description",
        fields: ["number", "description"] },
      companyFilterOption(),
      { key: "status", ar: "الحالة", en: "Status", field: "status",
        options: [
          { value: "draft", ar: "مسودة", en: "Draft" },
          { value: "posted", ar: "مُرحّل", en: "Posted" },
          { value: "reversed", ar: "معكوس", en: "Reversed" },
        ] },
      // Slide 135 "القيود": the deck fixes عملة and فترة among the journal
      // filters; the period is the entry month.
      { key: "currency", ar: "العملة", en: "Currency", field: "currency",
        options: distinctOptions(rows, function (r) { return r.currency; }) },
      { key: "period", ar: "الفترة", en: "Period",
        resolve: function (r) { return r.entry_date ? String(r.entry_date).slice(0, 7) : ""; },
        options: distinctOptions(rows, function (r) {
          return r.entry_date ? String(r.entry_date).slice(0, 7) : "";
        }) },
    ];
  }

  function invoicesFilterSpec() {
    var rows = STATE.acctInvoices || [];
    return [
      { key: "q", type: "search", ar: "رقم / العميل / المورد / الوصف", en: "No. / party / description",
        fields: ["number", "party_name", "description"] },
      companyFilterOption(),
      { key: "direction", ar: "التصنيف", en: "Direction", field: "direction",
        options: [
          { value: "issued", ar: "صادرة (مستحق لنا)", en: "Issued (receivable)" },
          { value: "received", ar: "واردة (مستحق علينا)", en: "Received (payable)" },
        ] },
      { key: "status", ar: "حالة الاعتماد والتسوية", en: "Approval & settlement",
        field: "status",
        options: [
          { value: "draft", ar: "مسودة", en: "Draft" },
          { value: "issued", ar: "صادرة", en: "Issued" },
          { value: "partially_settled", ar: "مسددة جزئيًا", en: "Partially settled" },
          { value: "settled", ar: "مسددة", en: "Settled" },
          { value: "cancelled", ar: "ملغاة", en: "Cancelled" },
        ] },
      { key: "currency", ar: "العملة", en: "Currency", field: "currency",
        options: distinctOptions(rows, function (r) { return r.currency; }) },
      // Slide 135 fixes فترة among the receivable filters; the invoice's period
      // is its issue month (the due date drives the default sort instead).
      { key: "period", ar: "الفترة", en: "Period", field: "period",
        resolve: function (r) { return r.issue_date ? String(r.issue_date).slice(0, 7) : ""; },
        options: distinctOptions(rows, function (r) {
          return r.issue_date ? String(r.issue_date).slice(0, 7) : "";
        }) },
    ];
  }

  function partiesFilterSpec() {
    var rows = STATE.acctParties || [];
    return [
      { key: "q", type: "search", ar: "الاسم / التواصل", en: "Name / contact",
        fields: ["name", "contact", "currency"] },
      companyFilterOption(),
      { key: "type", ar: "التصنيف", en: "Type", field: "party_type",
        options: [
          { value: "customer", ar: "عميل", en: "Customer" },
          { value: "supplier", ar: "مورد", en: "Supplier" },
        ] },
      { key: "currency", ar: "العملة", en: "Currency", field: "currency",
        options: distinctOptions(rows, function (r) { return r.currency; }) },
    ];
  }

  function budgetsFilterSpec() {
    var rows = STATE.acctBudgets || [];
    return [
      { key: "q", type: "search", ar: "السنة / المصدر", en: "Year / source",
        fields: ["fiscal_year", "source"] },
      companyFilterOption(),
      { key: "currency", ar: "العملة", en: "Currency", field: "currency",
        options: distinctOptions(rows, function (r) { return r.currency; }) },
      { key: "year", ar: "السنة", en: "Year", field: "fiscal_year",
        options: distinctOptions(rows, function (r) { return r.fiscal_year; }) },
      // Slide 135 "حسابات / ميزانية / مراكز" fixes مسؤول too. The budget carries
      // its approver (``approved_by_id``); the serializer adds that person's
      // name so the select reads as a person rather than a bare id. The deck's
      // "شهر/ربع" is not offered: a budget has no month or quarter column, and
      // an empty select is dropped rather than shown as a dead control.
      { key: "owner", ar: "المسؤول", en: "Responsible", field: "approved_by_id",
        options: distinctOptions(rows.filter(function (r) { return r.approved_by_id; }),
          function (r) { return r.approved_by_id; },
          function (v) {
            var b = rows.filter(function (x) { return String(x.approved_by_id) === String(v); })[0] || {};
            return { ar: b.approved_by_name_ar || b.approved_by_name_en || "#" + plainNum(v),
                     en: b.approved_by_name_en || b.approved_by_name_ar || "#" + plainNum(v) };
          }) },
      { key: "status", ar: "الحالة", en: "Status", field: "status",
        options: [
          { value: "draft", ar: "مسودة", en: "Draft" },
          { value: "approved", ar: "معتمدة", en: "Approved" },
          { value: "superseded", ar: "مستبدلة", en: "Superseded" },
        ] },
    ];
  }

  function assetsFilterSpec() {
    var rows = STATE.acctAssets || [];
    return [
      // Slide 135 search terms "الاسم/البنك/المركز/رمز البند": the asset record
      // carries a name, a category and notes; the bank/centre/line-code the deck
      // lists have no backing column on ``Asset``, so only real fields are
      // searched rather than offering a term that can never match.
      { key: "q", type: "search", ar: "الاسم / الفئة / ملاحظات", en: "Name / category / notes",
        fields: ["name", "category", "notes"] },
      companyFilterOption(),
      { key: "currency", ar: "العملة", en: "Currency", field: "currency",
        options: distinctOptions(rows, function (r) { return r.currency; }) },
      { key: "status", ar: "الحالة", en: "Status",
        resolve: function (r) { return r.is_active ? "1" : "0"; },
        options: [
          { value: "1", ar: "نشط", en: "Active" },
          { value: "0", ar: "موقوف", en: "Inactive" },
        ] },
    ];
  }

  // Mount a paged, filtered list into a placeholder element inside a panel.
  // The panel owns the heading and any create form; the list owns its own
  // filter bar, rows and pager (slides 134-136).
  function mountList(containerId, key, rows, rowFn, spec, bindFn, cmp) {
    var el = byId(containerId);
    if (!el) return;
    var list = applyListFilters(rows, key, spec).slice().sort(cmp || byIdAsc);
    renderPaged(el, key, list, rowFn, bindFn || null, spec);
  }

  // The deck's default sort for the accounting lists (slides 135-136) is by
  // name / period rather than by id; a text comparison keeps a stable order.
  function byTextAsc(get) {
    return function (a, b) {
      return String(get(a) || "").localeCompare(String(get(b) || ""), "ar") || byIdAsc(a, b);
    };
  }

  function byDateAsc(get) {
    return function (a, b) {
      return String(get(a) || "9999-12-31").localeCompare(String(get(b) || "9999-12-31")) || byIdAsc(a, b);
    };
  }

  function byDateDesc(get) {
    return function (a, b) {
      return String(get(b) || "").localeCompare(String(get(a) || "")) || byIdAsc(a, b);
    };
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

  // A person's display name from a row that carries ``<prefix>_name_ar`` /
  // ``<prefix>_name_en`` (assignee, executor, reviewer). Falls back to the
  // English name and then to an empty string, so a caller can supply its own
  // "#id" placeholder.
  function personName(row, arKey, enKey) {
    if (!row) return "";
    return STATE.lang === "ar"
      ? row[arKey] || row[enKey] || ""
      : row[enKey] || row[arKey] || "";
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
    "leads",
    "requests",
    "advisory",
    "opportunities",
    "decisions",
    "reports",
    "employees",
    "hr",
    "assets",
    "site",
    "aiReview",
    "group",
    // Legacy views kept reachable (deep links / internal shortcuts) but no
    // longer in the rail, which mirrors the approved prototype's 13 sections.
    "feedback",
    "subsidiaries",
    "financial",
    "investments",
    "support",
    "approvals",
    "documents",
    "bi",
    "analytics",
    "inbox",
    "operations",
    "accounting",
    "confidential",
  ];
  var NAV_PERM = {
    dashboard: ["dashboard.holding", "dashboard.company"],
    // The Feedback view aggregates weekly reports, management briefs and
    // monthly reports the caller may already read; it introduces no new data
    // access, so it is gated by exactly those read permissions.
    feedback: [
      "weekly_report.read_own",
      "weekly_report.read_all",
      "management_brief.read",
      "monthly_report.read_own",
      "monthly_report.read_all",
    ],
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
    opportunities: ["project.read"],
    // Advisory / HR / Assets / Website / Assistant-learning sections mirror the
    // approved prototype tabs; each is gated by the read capability its
    // endpoint enforces.
    advisory: ["advisor.read", "advisor.session.read_own"],
    hr: ["employee.read", "employee.movement.read"],
    assets: ["asset.read"],
    site: ["website.manage", "website.content.read", "website_lead.read"],
    aiReview: [
      "ai.knowledge.approve",
      "ai.knowledge.manage",
      "ai.knowledge.read",
    ],
    accounting: [
      "account.read",
      "journal.read",
      "invoice.read",
      "asset.read",
      "budget.read",
      "opening_balance.read",
      "kpi.read",
      "accounting_policy.read",
      "financial_report.read",
    ],
    confidential: ["complaint.read_own", "complaint.decide", "complaint.create"],
    group: [
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
    syncMoreGroup(view);
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
    bindMoreGroup();
    bindNavDrawer();
  }

  // Deck slides 39/89/90: on a phone the rail opens from ☰. The toggle only
  // exists visually ≤1180px (CSS), but the binding is harmless on desktop.
  function bindNavDrawer() {
    var toggle = byId("navToggle");
    var scrim = byId("navScrim");
    var sidebar = byId("sidebar");
    if (!toggle || !scrim) return;

    function setOpen(open) {
      body.classList.toggle("nav-open", open);
      toggle.setAttribute("aria-expanded", open ? "true" : "false");
      scrim.hidden = !open;
    }
    function close() { setOpen(false); }

    toggle.addEventListener("click", function () {
      setOpen(!body.classList.contains("nav-open"));
    });
    scrim.addEventListener("click", close);
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape") close();
    });
    if (sidebar) {
      // Tapping a destination closes the drawer so the view is not hidden
      // behind it. Delegated so it survives permission re-renders.
      sidebar.addEventListener("click", function (e) {
        if (e.target.closest(".nav-item")) close();
      });
    }
    // A resize back to desktop must not leave the scrim armed.
    window.addEventListener("resize", function () {
      if (window.innerWidth > 1180) close();
    });
  }

  // The sidebar collapses the operational views behind one "Additional tools"
  // toggle so the owner sees six primary sections. The group auto-opens when
  // the active view lives inside it, so a deep link never hides the current
  // screen.
  function bindMoreGroup() {
    var group = byId("sbMore");
    var toggle = byId("sbMoreToggle");
    if (!group || !toggle) return;
    toggle.addEventListener("click", function () {
      var open = group.classList.toggle("open");
      toggle.setAttribute("aria-expanded", open ? "true" : "false");
    });
  }

  function syncMoreGroup(view) {
    var group = byId("sbMore");
    var toggle = byId("sbMoreToggle");
    if (!group || !toggle) return;
    var inside = !!group.querySelector('.nav-item[data-view="' + view + '"]');
    if (inside) {
      group.classList.add("open");
      toggle.setAttribute("aria-expanded", "true");
    }
  }

  function loadView(view) {
    if (view === "subsidiaries") return renderSubsidiaries();
    if (view === "reports") return renderReports();
    if (view === "financial") return renderFinancial();
    if (view === "support") return renderSupportView();
    if (view === "requests") return renderRequestsView();
    if (view === "feedback") return renderFeedbackView();
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
    if (view === "opportunities") return renderProjectsView();
    if (view === "accounting") return renderAccountingView();
    if (view === "confidential") return renderConfidentialView();
    if (view === "group") return renderAdmin();
    if (view === "advisory") return renderAdvisoryView();
    if (view === "hr") return renderHrView();
    if (view === "assets") return renderAssetsView();
    if (view === "site") return renderSiteView();
    if (view === "aiReview") return renderAiReviewView();
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
      var spec = subsidiariesFilterSpec();
      var list = applyListFilters(scopeFilter(rows, "id"), "subsidiaries", spec);
      // Deck slide 134: الشركات/المحفظة sort "آخر تحديث تنازليًا".
      list.sort(function (a, b) {
        return String(b.updated_at || "").localeCompare(String(a.updated_at || "")) || byIdAsc(a, b);
      });
      renderPaged(host, "subsidiaries", list, subsidiaryCard, function (h) {
        h.querySelectorAll("[data-company]").forEach(function (card) {
          card.addEventListener("click", function () {
            openCompany(parseInt(card.getAttribute("data-company"), 10));
          });
        });
      }, spec);
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
        // Deck slide 13 puts [تعديل البيانات] on the company file header.
        var editBtn = has("company.manage")
          ? '<div class="sec-title" style="display:flex;justify-content:space-between;align-items:center">' +
            dual("بيانات الشركة", "Company data") +
            '<button class="btn-outline" type="button" id="coFileEdit">' +
            dual("تعديل البيانات", "Edit data") + "</button></div>"
          : '<div class="sec-title">' + dual("بيانات الشركة", "Company data") + "</div>";
        body.innerHTML =
          editBtn +
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
        var edit = byId("coFileEdit");
        if (edit) {
          edit.addEventListener("click", function () { openCompanyEdit(c); });
        }
      })
      .catch(function (err) {
        if (body) body.innerHTML = errorHtml(errText(err));
      });
  }

  // Deck slide 13: the company file offers [تعديل البيانات]. The same fields the
  // admin card edits are exposed here so the owner can correct the record from
  // the file it belongs to, and the detail view reloads afterwards.
  function openCompanyEdit(c) {
    var sector = sectorLabel(c.sector);
    openModal({
      title: dual("تعديل بيانات الشركة", "Edit company data"),
      body:
        '<form class="av-form" id="companyEditForm" novalidate>' +
        field("الاسم (عربي)", "Name (AR)", textInput("ceNameAr", c.name_ar)) +
        field("الاسم (إنجليزي)", "Name (EN)", textInput("ceNameEn", c.name_en || "")) +
        field("القطاع", "Sector", textInput("ceSector", c.sector)) +
        field("العملة", "Currency", textInput("ceCurrency", c.currency)) +
        field("الدولة", "Country", textInput("ceCountry", c.country || "")) +
        '<div class="av-form-actions"><button class="btn-solid" type="button" id="ceSave">' +
        dual("حفظ التعديلات", "Save changes") + "</button></div></form>",
      onMount: function () {
        var save = byId("ceSave");
        if (!save) return;
        save.addEventListener("click", function () {
          busy(save, true);
          patch("/api/v1/companies/" + c.id, {
            name_ar: valOf("ceNameAr"),
            name_en: valOf("ceNameEn") || null,
            sector: valOf("ceSector"),
            currency: valOf("ceCurrency"),
            country: valOf("ceCountry") || null,
          })
            .then(function () {
              STATE.loaded.companies = false;
              toast(dual("تم تحديث بيانات الشركة.", "Company data updated."), "ok");
              closeModal();
              openCompany(c.id);
            })
            .catch(function (err) { busy(save, false); domainError(err); });
        });
      },
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
      var spec = reportsFilterSpec();
      var list = rows.filter(function (r) {
        if (year && r.period_year !== year) return false;
        if (status && r.status !== status) return false;
        return true;
      });
      list = applyListFilters(scopeFilter(list), "reports", spec);
      // Deck slide 134: التقارير sort "الفترة الأحدث ثم وقت الإرسال".
      list.sort(function (a, b) {
        return (
          b.period_year * 12 + b.period_month - (a.period_year * 12 + a.period_month) ||
          String(b.submitted_at || "").localeCompare(String(a.submitted_at || "")) ||
          byIdAsc(a, b)
        );
      });
      renderPaged(host, "reports", list, reportRow, function (h) {
        h.querySelectorAll("[data-report]").forEach(function (el) {
          el.addEventListener("click", function () {
            openReport(parseInt(el.getAttribute("data-report"), 10));
          });
        });
      }, spec);
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
    // Business rule 1: a report past its day-5 deadline that is still missing
    // or editable is flagged, so the list shows who is behind at a glance.
    // Reuses the existing status chip styling for visual consistency.
    var late = r.is_late
      ? '<span class="status miss" title="' +
        escapeHtml(dual("متأخر عن الموعد", "Past deadline")) + '"><i></i>' +
        dual("متأخر", "Late") + "</span> "
      : "";
    return (
      '<div class="av-row" data-report="' + r.id + '">' +
      '<div class="co-dot" style="background:' + PALETTE[r.company_id % PALETTE.length] + ';width:32px;height:32px;border-radius:9px">' + initial(r.company_name_ar) + "</div>" +
      '<div class="grow"><div class="t">' + escapeHtml(reportCompanyName(r)) + "</div>" +
      '<div class="s">' + dual(AR_MONTHS[r.period_month - 1] + " " + toArabicDigits(String(r.period_year)), EN_MONTHS[r.period_month - 1] + " " + r.period_year) +
      " · " + dual("الإيرادات ", "Revenue ") + '<b>' + dual(rev.ar, rev.en) + "</b>" +
      " · " + dual("الصافي ", "Net ") + '<b>' + dual(net.ar, net.en) + "</b></div></div>" +
      late +
      statusBadge(r.status) +
      "</div>"
    );
  }

  // ---- D03: versioned management-report workflow (S09) -----------------
  // The correction of a submitted management report is a *linked* new version,
  // never an edit of the original. These helpers render the chain + trail and
  // drive the return / correct / approve / cancel transitions.
  function promptDialog(opts) {
    return new Promise(function (resolve) {
      openModal({
        title: opts.title || dual("\u0645\u0637\u0644\u0648\u0628", "Required"),
        body:
          '<p class="note-block">' + escapeHtml(opts.message || "") + "</p>" +
          '<div class="av-field"><label>' +
          escapeHtml(opts.label || dual("\u0627\u0644\u0633\u0628\u0628", "Reason")) +
          '</label><textarea class="av-textarea" id="pdValue" rows="3"></textarea></div>',
        footer:
          '<button class="btn-outline" id="pdCancel">' + dual("\u0625\u0644\u063a\u0627\u0621", "Cancel") + "</button>" +
          '<button class="btn-solid" id="pdOk">' +
          (opts.confirmLabel || dual("\u062a\u0623\u0643\u064a\u062f", "Confirm")) +
          "</button>",
        onMount: function (root) {
          root.querySelector("#pdCancel").addEventListener("click", function () {
            closeModal();
            resolve(null);
          });
          root.querySelector("#pdOk").addEventListener("click", function () {
            var v = (root.querySelector("#pdValue").value || "").trim();
            if (!v) {
              toast(STATE.lang === "ar" ? "\u0627\u0644\u062d\u0642\u0644 \u0645\u0637\u0644\u0648\u0628." : "This field is required.", "warn");
              return;
            }
            closeModal();
            resolve(v);
          });
        },
      });
    });
  }

  var LIFECYCLE_LABEL = {
    submitted: ["\u0625\u0631\u0633\u0627\u0644", "Submitted"],
    resubmitted: ["\u0625\u0639\u0627\u062f\u0629 \u0625\u0631\u0633\u0627\u0644", "Resubmitted"],
    returned: ["\u0625\u0639\u0627\u062f\u0629 \u0644\u0644\u062a\u0635\u062d\u064a\u062d", "Returned"],
    approved: ["\u0627\u0639\u062a\u0645\u0627\u062f", "Approved"],
    cancelled: ["\u0625\u0644\u063a\u0627\u0621", "Cancelled"],
    locked: ["\u0642\u0641\u0644", "Locked"],
  };

  function reportVersionsBlock(r) {
    var versions = r.versions || [];
    if (versions.length < 2) return "";
    var rows = versions
      .map(function (v) {
        var live = v.is_live
          ? ' <span class="status ok"><i></i>' + dual("\u0633\u0627\u0631\u064a\u0629", "Live") + "</span>"
          : "";
        return (
          '<div class="note-block"><span class="lbl">' +
          dual("\u0646\u0633\u062e\u0629 " + toArabicDigits(String(v.version_number)), "v" + v.version_number) +
          (v.corrects_report_id
            ? " \u00b7 " + dual("\u062a\u0635\u062d\u064a\u062d \u0644\u0644\u0646\u0633\u062e\u0629 \u0627\u0644\u0633\u0627\u0628\u0642\u0629", "corrects the previous version")
            : "") +
          "</span>" + statusBadge(v.status) + live +
          (v.return_reason ? '<div class="s">' + escapeHtml(v.return_reason) + "</div>" : "") +
          "</div>"
        );
      })
      .join("");
    return '<div class="sec-title">' + dual("\u0633\u0644\u0633\u0644\u0629 \u0627\u0644\u0646\u0633\u062e", "Version history") + "</div>" + rows;
  }

  // Deck slide 125 — طلب التصحيح ومقارنة القيم. A correction version carries
  // ``corrects_report_id``; the original stays locked and readable. The block
  // reads the original through the same scoped GET the detail already uses and
  // shows field-by-field قبل/بعد. It is read-only: it never edits either side.
  var CORRECTION_COMPARE_FIELDS = [
    ["revenue", "الإيرادات", "Revenue", true],
    ["expenses", "المصروفات", "Expenses", true],
    ["net_result", "صافي النتيجة", "Net result", true],
    ["outstanding_receivables", "الذمم المدينة", "Receivables", true],
    ["important_developments", "أهم التطورات", "Developments", false],
    ["new_customers", "عملاء جدد", "New customers", false],
    ["new_opportunities", "فرص جديدة", "New opportunities", false],
    ["major_problems", "مشاكل رئيسية", "Major problems", false],
    ["support_required", "الدعم المطلوب", "Support required", false],
    ["management_notes", "ملاحظات الإدارة", "Management notes", false],
  ];

  function correctionValueText(value, isMoney) {
    if (value === null || value === undefined || value === "") return "—";
    if (isMoney) { var m = money(value); return STATE.lang === "ar" ? m.ar : m.en; }
    return String(value);
  }

  var CORRECTION_APPROVAL_LABEL = {
    pending: ["قيد الاعتماد", "Pending"],
    approved: ["معتمد", "Approved"],
    rejected: ["مرفوض", "Rejected"],
  };

  function loadCorrectionComparison(correctedId, originalId) {
    var host = byId("repCompare");
    if (!host) return;
    Promise.all([
      get("/api/v1/monthly-reports/" + originalId),
      get("/api/v1/monthly-reports/" + correctedId),
    ]).then(function (res) {
      var original = res[0], current = res[1];
      // The requester/date comes from the new version's own workflow trail; no
      // figure is invented when the trail is absent.
      var submit = (current.lifecycle || []).filter(function (e) {
        return e.action === "submitted" || e.action === "resubmitted";
      })[0] || {};
      var approval = CORRECTION_APPROVAL_LABEL[current.approval_status] ||
        [current.approval_status, current.approval_status];
      var head =
        '<div class="sec-title">' +
        dual("مقارنة قبل وبعد (الأصل مقابل النسخة المصححة)", "Before / after (original vs. correction)") +
        "</div>" +
        '<div class="s">' +
        dual(
          "الأصل نسخة " + toArabicDigits(String(original.version_number)) + " مقفلة وقابلة للعرض؛ النسخة الجديدة لا تصبح نهائية قبل الاعتماد.",
          "Original v" + original.version_number + " is locked and readable; the new version is not final until approved.",
        ) + "</div>" +
        '<div class="kv">' +
        kv(dual("سبب التصحيح", "Correction reason"), escapeHtml(original.return_reason || "—")) +
        kv(dual("مقدم الطلب وتاريخه", "Requester & date"),
           escapeHtml(submit.actor_name_ar || "—") + " · " + fmtDateTime(submit.created_at || current.created_at)) +
        kv(dual("المراجع والقرار", "Reviewer & decision"), dual(approval[0], approval[1])) +
        "</div>";
      var rows = CORRECTION_COMPARE_FIELDS.map(function (f) {
        var key = f[0], ar = f[1], en = f[2], isMoney = f[3];
        var before = original[key], after = current[key];
        var changed = String(before === null || before === undefined ? "" : before) !==
          String(after === null || after === undefined ? "" : after);
        return (
          '<div class="note-block"' + (changed ? ' style="border-inline-start:3px solid var(--gold)"' : "") + ">" +
          '<span class="lbl">' + dual(ar, en) + "</span>" +
          '<span class="s">' + dual("قبل: ", "Before: ") + escapeHtml(correctionValueText(before, isMoney)) + "</span><br>" +
          '<span class="s">' + dual("بعد: ", "After: ") + escapeHtml(correctionValueText(after, isMoney)) + "</span>" +
          (changed ? ' <span class="status warn"><i></i>' + dual("معدّل", "Changed") + "</span>" : "") +
          "</div>"
        );
      }).join("");
      host.innerHTML = head + rows;
    }).catch(function () { host.innerHTML = ""; });
  }

  function reportLifecycleBlock(r) {
    var events = r.lifecycle || [];
    if (!events.length) return "";
    var rows = events
      .map(function (e) {
        var lbl = LIFECYCLE_LABEL[e.action] || [e.action, e.action];
        return (
          '<div class="note-block"><span class="lbl">' + dual(lbl[0], lbl[1]) +
          " \u00b7 " + fmtDateTime(e.created_at) +
          (e.actor_name_ar ? " \u00b7 " + escapeHtml(e.actor_name_ar) : "") +
          "</span>" + (e.note ? escapeHtml(e.note) : "") + "</div>"
        );
      })
      .join("");
    return '<div class="sec-title">' + dual("\u0633\u062c\u0644 \u0633\u064a\u0631 \u0627\u0644\u0639\u0645\u0644", "Workflow trail") + "</div>" + rows;
  }

  function returnReportForm(id, btn) {
    promptDialog({
      title: dual("\u0625\u0639\u0627\u062f\u0629 \u0627\u0644\u062a\u0642\u0631\u064a\u0631 \u0644\u0644\u062a\u0635\u062d\u064a\u062d", "Return report for correction"),
      message:
        STATE.lang === "ar"
          ? "\u0633\u064a\u064f\u0639\u0627\u062f \u0627\u0644\u062a\u0642\u0631\u064a\u0631 \u0644\u0644\u0634\u0631\u0643\u0629 \u0644\u0644\u062a\u0635\u062d\u064a\u062d\u060c \u0648\u062a\u0628\u0642\u0649 \u0627\u0644\u0646\u0633\u062e\u0629 \u0627\u0644\u0623\u0635\u0644\u064a\u0629 \u0645\u062d\u0641\u0648\u0638\u0629."
          : "The report goes back to the company for correction; the original is preserved.",
      label: dual("\u0633\u0628\u0628 \u0627\u0644\u0625\u0639\u0627\u062f\u0629 (\u0645\u0637\u0644\u0648\u0628)", "Return reason (required)"),
      confirmLabel: dual("\u0625\u0639\u0627\u062f\u0629", "Return"),
    }).then(function (reason) {
      if (!reason) return;
      busy(btn, true);
      post("/api/v1/monthly-reports/" + id + "/return", { reason: reason })
        .then(function () {
          toast(dual("\u0623\u064f\u0639\u064a\u062f \u0627\u0644\u062a\u0642\u0631\u064a\u0631 \u0644\u0644\u062a\u0635\u062d\u064a\u062d.", "Report returned for correction."), "ok");
          refreshAll().then(function () { openReport(id); });
        })
        .catch(function (err) { toast(errText(err), "err"); busy(btn, false); });
    });
  }

  function correctReportForm(id, btn) {
    promptDialog({
      title: dual("\u0625\u0646\u0634\u0627\u0621 \u0646\u0633\u062e\u0629 \u062a\u0635\u062d\u064a\u062d", "Create correction version"),
      message:
        STATE.lang === "ar"
          ? "\u0633\u062a\u064f\u0646\u0634\u0623 \u0646\u0633\u062e\u0629 \u062c\u062f\u064a\u062f\u0629 \u0645\u0631\u062a\u0628\u0637\u0629 \u0628\u0627\u0644\u0623\u0635\u0644\u060c \u0645\u0639 \u0627\u0644\u0627\u062d\u062a\u0641\u0627\u0638 \u0628\u0627\u0644\u0623\u0635\u0644."
          : "A new version linked to the original is created; the original is kept.",
      label: dual("\u0645\u0634\u0627\u0643\u0644 \u0631\u0626\u064a\u0633\u064a\u0629 / \u0645\u0644\u0627\u062d\u0638\u0629 \u0627\u0644\u062a\u0635\u062d\u064a\u062d", "Major problems / correction note"),
      confirmLabel: dual("\u0625\u0646\u0634\u0627\u0621 \u0646\u0633\u062e\u0629", "Create version"),
    }).then(function (note) {
      if (!note) return;
      busy(btn, true);
      post("/api/v1/monthly-reports/" + id + "/correction", { major_problems: note })
        .then(function (created) {
          toast(dual("\u0623\u064f\u0646\u0634\u0626\u062a \u0646\u0633\u062e\u0629 \u0627\u0644\u062a\u0635\u062d\u064a\u062d.", "Correction version created."), "ok");
          refreshAll().then(function () { openReport(created.id); });
        })
        .catch(function (err) { toast(errText(err), "err"); busy(btn, false); });
    });
  }

  function approveReport(id, btn) {
    confirmDialog({
      title: dual("\u0627\u0639\u062a\u0645\u0627\u062f \u0627\u0644\u062a\u0642\u0631\u064a\u0631", "Approve report"),
      message:
        STATE.lang === "ar"
          ? "\u0633\u064a\u0639\u062a\u0645\u062f \u0627\u0644\u062a\u0642\u0631\u064a\u0631 \u0646\u0647\u0627\u0626\u064a\u064b\u0627 \u0645\u0646 \u0627\u0644\u0645\u0627\u0644\u0643."
          : "The owner gives the report final approval.",
      confirmLabel: dual("\u0627\u0639\u062a\u0645\u0627\u062f", "Approve"),
    }).then(function (ok) {
      if (!ok) return;
      busy(btn, true);
      post("/api/v1/monthly-reports/" + id + "/approve")
        .then(function () {
          toast(dual("\u0627\u0639\u062a\u0645\u062f \u0627\u0644\u062a\u0642\u0631\u064a\u0631.", "Report approved."), "ok");
          refreshAll().then(function () { openReport(id); });
        })
        .catch(function (err) { toast(errText(err), "err"); busy(btn, false); });
    });
  }

  function lockReport(id, btn) {
    confirmDialog({
      title: dual("\u0642\u0641\u0644 \u0627\u0644\u062a\u0642\u0631\u064a\u0631", "Lock report"),
      message:
        STATE.lang === "ar"
          ? "\u0633\u064a\u064f\u0642\u0641\u0644 \u0627\u0644\u062a\u0642\u0631\u064a\u0631 \u0646\u0647\u0627\u0626\u064a\u064b\u0627 \u0648\u0644\u0627 \u064a\u0645\u0643\u0646 \u062a\u0639\u062f\u064a\u0644\u0647 \u0628\u0639\u062f \u0630\u0644\u0643."
          : "The report is locked permanently and can no longer be changed.",
      confirmLabel: dual("\u0642\u0641\u0644", "Lock"),
    }).then(function (ok) {
      if (!ok) return;
      busy(btn, true);
      post("/api/v1/monthly-reports/" + id + "/lock")
        .then(function () {
          toast(dual("\u0642\u064f\u0641\u0644 \u0627\u0644\u062a\u0642\u0631\u064a\u0631.", "Report locked."), "ok");
          refreshAll().then(function () { openReport(id); });
        })
        .catch(function (err) { toast(errText(err), "err"); busy(btn, false); });
    });
  }

  function cancelReportForm(id, btn) {
    promptDialog({
      title: dual("\u0625\u0644\u063a\u0627\u0621 \u0627\u0644\u062a\u0642\u0631\u064a\u0631", "Cancel report"),
      message:
        STATE.lang === "ar"
          ? "\u0633\u064a\u064f\u0644\u063a\u0649 \u0647\u0630\u0627 \u0627\u0644\u062a\u0642\u0631\u064a\u0631 \u0645\u0639 \u062a\u0633\u062c\u064a\u0644 \u0627\u0644\u0633\u0628\u0628."
          : "This report is cancelled with a recorded reason.",
      label: dual("\u0633\u0628\u0628 \u0627\u0644\u0625\u0644\u063a\u0627\u0621 (\u0645\u0637\u0644\u0648\u0628)", "Cancellation reason (required)"),
      confirmLabel: dual("\u0625\u0644\u063a\u0627\u0621 \u0627\u0644\u062a\u0642\u0631\u064a\u0631", "Cancel report"),
    }).then(function (reason) {
      if (!reason) return;
      busy(btn, true);
      post("/api/v1/monthly-reports/" + id + "/cancel", { reason: reason })
        .then(function () {
          toast(dual("\u0623\u064f\u0644\u063a\u064a \u0627\u0644\u062a\u0642\u0631\u064a\u0631.", "Report cancelled."), "ok");
          refreshAll().then(function () { openReport(id); });
        })
        .catch(function (err) { toast(errText(err), "err"); busy(btn, false); });
    });
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
        var canReview = has("financial_review.write") && r.status !== "draft" && r.status !== "locked";
        var canDelete = has("monthly_report.delete") && r.status === "draft";
        var reviewable = ["submitted", "under_review", "reviewed"].indexOf(r.status) >= 0;
        var canReturn = has("monthly_report.review") && r.is_live && reviewable;
        var canCorrect = has("monthly_report.update") && r.is_live && r.status === "returned";
        var canApprove = has("monthly_report.approve") && r.is_live && reviewable && r.approval_status !== "approved";
        var canLock = has("monthly_report.approve") && r.is_live && r.status === "reviewed" && r.approval_status === "approved";
        var canCancel = has("monthly_report.approve") && r.status !== "cancelled" && r.status !== "locked";

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
          (r.financial_part
            ? '<div class="sec-title">' + dual("الجزء المالي (F-03)", "Financial part (F-03)") + "</div>" +
              '<div class="kv">' +
              kv(dual("حالة الملخص المالي", "Financial summary status"), finStatusBadge(r.financial_part.status)) +
              (r.financial_part.effective_version
                ? kv(dual("النسخة المعتمدة", "Approved version"),
                    dual("نسخة " + toArabicDigits(String(r.financial_part.effective_version.version_number)),
                         "v" + r.financial_part.effective_version.version_number))
                : kv(dual("النسخة المعتمدة", "Approved version"), dual("لا بيانات", "No data"))) +
              (r.financial_part.current_version && (!r.financial_part.effective_version ||
                r.financial_part.current_version.id !== r.financial_part.effective_version.id)
                ? kv(dual("النسخة الجارية", "Current version"),
                    dual("نسخة " + toArabicDigits(String(r.financial_part.current_version.version_number)),
                         "v" + r.financial_part.current_version.version_number) +
                    " · " + finStatusBadge(r.financial_part.current_version.status))
                : "") +
              "</div>" +
              '<div class="s">' + dual("الأرقام مسحوبة من الملخص المالي المعتمد، لا تُنسخ في التقرير.",
                "Figures are read from the approved financial summary, never copied into the report.") + "</div>"
            : "") +
          reportVersionsBlock(r) +
          '<div id="repCompare"></div>' +
          reportLifecycleBlock(r) +
          '<div id="repOrganize"></div>' +
          '<div id="repClarify"></div>' +
          '<div id="repActions" class="modal-foot" style="margin-top:14px;border-radius:12px;border:1px solid var(--line-2)"></div>';

        loadClarifications(id);

        // Slide 125: a correction version shows the original next to it, so the
        // reviewer sees قبل/بعد before approving. Read-only; only when this row
        // is itself a correction of another version.
        if (r.corrects_report_id) {
          loadCorrectionComparison(id, r.corrects_report_id);
        }

        // S09: AI text organization. The proposal never overwrites the report;
        // the manager applies a field explicitly through the normal PATCH.
        var organizeHost = byId("repOrganize");
        if (organizeHost && has("monthly_report.update") && r.status === "draft") {
          organizeHost.innerHTML =
            '<div class="sec-title">' + dual("تنظيم النص بالذكاء الاصطناعي", "AI text organization") + "</div>" +
            '<div class="pbtns" style="margin-top:8px"><button type="button" class="btn-outline" id="repOrganizeBtn">' +
            dual("اقترح تنظيمًا", "Suggest organization") + "</button></div>" +
            '<div id="repOrganizeOut"></div>';
          var orgBtn = byId("repOrganizeBtn");
          if (orgBtn) {
            orgBtn.addEventListener("click", function () { organizeReportNarrative(id, orgBtn); });
          }
        }

        var actions = byId("repActions");
        var btns = [];
        if (canSubmit) {
          btns.push('<button class="btn-solid" id="repSubmit">' + dual("حفظ وإرسال", "Save and submit") + "</button>");
        }
        if (canReview) {
          btns.push('<button class="btn-solid gold" id="repReview">' + dual("مراجعة مالية", "Financial review") + "</button>");
        }
        if (canDelete) {
          btns.push('<button class="btn-solid danger" id="repDelete">' + dual("حذف المسودة", "Delete draft") + "</button>");
        }
        if (canReturn) {
          btns.push('<button class="btn-solid gold" id="repReturn">' + dual("إعادة للتصحيح", "Return for correction") + "</button>");
        }
        if (canCorrect) {
          btns.push('<button class="btn-solid" id="repCorrect">' + dual("فتح للتصحيح", "Open for correction") + "</button>");
        }
        if (canApprove) {
          btns.push('<button class="btn-solid gold" id="repApprove">' + dual("اعتماد التقرير", "Approve report") + "</button>");
        }
        if (canLock) {
          btns.push('<button class="btn-solid gold" id="repLock">' + dual("قفل التقرير", "Lock report") + "</button>");
        }
        if (canCancel) {
          btns.push('<button class="btn-solid danger" id="repCancel">' + dual("إلغاء التقرير", "Cancel report") + "</button>");
        }
        btns.push('<button class="btn-outline" id="repClose">' + dual("إغلاق", "Close") + "</button>");
        if (actions) actions.innerHTML = btns.join("");

        if (byId("repClose")) byId("repClose").addEventListener("click", closeModal);
        if (byId("repSubmit")) byId("repSubmit").addEventListener("click", function () { submitReport(id, this); });
        if (byId("repReview")) byId("repReview").addEventListener("click", function () { financialReviewForm(id); });
        if (byId("repDelete")) byId("repDelete").addEventListener("click", function () { deleteReport(id, this); });
        if (byId("repReturn")) byId("repReturn").addEventListener("click", function () { returnReportForm(id, this); });
        if (byId("repCorrect")) byId("repCorrect").addEventListener("click", function () { correctReportForm(id, this); });
        if (byId("repApprove")) byId("repApprove").addEventListener("click", function () { approveReport(id, this); });
        if (byId("repLock")) byId("repLock").addEventListener("click", function () { lockReport(id, this); });
        if (byId("repCancel")) byId("repCancel").addEventListener("click", function () { cancelReportForm(id, this); });
      })
      .catch(function (err) {
        if (body) body.innerHTML = errorHtml(errText(err));
      });
  }

  var REPORT_FIELD_LABELS = {
    important_developments: ["أهم التطورات", "Developments"],
    new_customers: ["عملاء جدد", "New customers"],
    new_opportunities: ["فرص جديدة", "New opportunities"],
    major_problems: ["مشاكل رئيسية", "Major problems"],
    support_required: ["الدعم المطلوب", "Support required"],
    marketing_status: ["حالة التسويق", "Marketing status"],
    business_development_status: ["حالة تطوير الأعمال", "Business development status"],
    management_notes: ["ملاحظات الإدارة", "Management notes"],
  };

  function organizeReportNarrative(id, btn) {
    var out = byId("repOrganizeOut");
    if (!out) return;
    busy(btn, true);
    post("/api/v1/monthly-reports/" + id + "/organize-narrative")
      .then(function (res) {
        busy(btn, false);
        var proposals = (res && res.proposals) || [];
        if (!proposals.length) {
          out.innerHTML = '<p class="av-empty">' + dual("لا يوجد نص لتنظيمه.", "There is no text to organize.") + "</p>";
          return;
        }
        out.innerHTML = proposals.map(function (p) {
          var lbl = REPORT_FIELD_LABELS[p.field] || [p.field, p.field];
          var warn = p.grounded
            ? ""
            : '<div class="s" style="color:var(--miss)">' +
              dual("تنبيه: احتوى الاقتراح أرقامًا غير موجودة في الأصل، فتم استخدام التنظيم الآمن.",
                "Note: the suggestion cited numbers absent from the original, so the safe organization was used.") +
              "</div>";
          return '<div class="note-block" data-field="' + escAttr(p.field) + '">' +
            '<span class="lbl">' + dual(lbl[0], lbl[1]) + "</span>" +
            '<div class="s">' + dual("الأصل (يبقى كما هو)", "Original (unchanged)") + "</div>" +
            '<div class="orig">' + escapeHtml(p.original) + "</div>" +
            '<div class="s">' + dual("الاقتراح", "Suggestion") + "</div>" +
            '<div class="prop">' + escapeHtml(p.organized) + "</div>" +
            warn +
            (p.changed
              ? '<div class="pbtns" style="margin-top:6px"><button type="button" class="btn-outline" data-org-apply="' +
                escAttr(p.field) + '">' + dual("اعتماد المقترح", "Apply suggestion") + "</button></div>"
              : '<div class="s">' + dual("لا تغيير.", "No change.") + "</div>") +
            "</div>";
        }).join("");
        out.querySelectorAll("[data-org-apply]").forEach(function (b) {
          b.addEventListener("click", function () { applyOrganizedField(id, b, proposals); });
        });
      })
      .catch(function (err) {
        busy(btn, false);
        out.innerHTML = errorHtml(errText(err));
      });
  }

  function applyOrganizedField(id, btn, proposals) {
    var field = btn.getAttribute("data-org-apply");
    var found = null;
    for (var i = 0; i < proposals.length; i++) {
      if (proposals[i].field === field) { found = proposals[i]; break; }
    }
    if (!found) return;
    var payload = {};
    payload[field] = found.organized;
    busy(btn, true);
    patch("/api/v1/monthly-reports/" + id, payload)
      .then(function () {
        toast(dual("تم اعتماد التنظيم.", "Organization applied."), "ok");
        refreshAll().then(function () { openReport(id); });
      })
      .catch(function (err) {
        toast(errText(err), "err");
        busy(btn, false);
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
          ? softGet("/api/v1/financial/item-definitions")
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
        finTotalsStrip(totals, report.counts || {}, report.totals_by_currency || {}) +
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
      field("الكود", "Code", textInput("fdCode", "", "", true), null, null, true) +
      field("الاسم (عربي)", "Name (AR)", textInput("fdNameAr", "", "", true), null, null, true) +
      field("الاسم (إنجليزي)", "Name (EN)", textInput("fdNameEn", "", "", true), null, null, true) +
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

  function finTotalsStrip(totals, counts, byCurrency) {
    var buckets = byCurrency || {};
    var codes = Object.keys(buckets);
    // AC-10 / T10: when companies report in more than one currency the strip
    // shows one labelled group per currency rather than a mixed sum. The plain
    // single-currency strip is kept when there is exactly one (or none).
    var moneyBlock;
    if (codes.length > 1) {
      moneyBlock = codes.map(function (code) {
        var b = buckets[code] || {};
        return (
          '<div class="fin-currency"><div class="plabel">' + escapeHtml(code) + "</div>" +
          finMoneyLine("الإيرادات الفعلية", "effective revenue", b.effective_revenue) +
          finMoneyLine("المصروفات الفعلية", "effective expenses", b.effective_expenses) +
          finMoneyLine("النتيجة", "result", b.calculated_result) +
          "</div>"
        );
      }).join("");
    } else {
      var one = codes.length === 1 ? buckets[codes[0]] : totals;
      moneyBlock =
        '<div><div class="pnum">' + finMoney(one.effective_revenue) + '</div><div class="plabel">' +
        dual("الإيرادات الفعلية", "effective revenue") + "</div></div>" +
        '<div class="psep"></div>' +
        '<div><div class="pnum">' + finMoney(one.effective_expenses) + '</div><div class="plabel">' +
        dual("المصروفات الفعلية", "effective expenses") + "</div></div>" +
        '<div class="psep"></div>' +
        '<div><div class="pnum">' + finMoney(one.calculated_result) + '</div><div class="plabel">' +
        dual("النتيجة", "result") + "</div></div>";
    }
    return (
      '<div class="perm-summary" style="margin-bottom:14px">' +
      '<div><div class="pnum">' + plainNum(counts.approved || 0) + '</div><div class="plabel">' +
      dual("ملخصات معتمدة", "approved summaries") + "</div></div>" +
      '<div class="psep"></div>' +
      moneyBlock +
      "</div>"
    );
  }

  function finMoneyLine(ar, en, value) {
    return '<div class="s">' + dual(ar, en) + ": " + finMoney(value) + "</div>";
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
      // Deck slide 23 draws the manager's form itself: the mandatory input
      // fields, then [حفظ مسودة] and [إرسال للمراجعة]. The form is shown only
      // while the version is editable, so an approved version stays read-only.
      (finCanEdit(v) ? finDraftForm(v) : "") +
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
          dual("إرفاق الملف", "Attach file") + "</button></div>"
        : "") +
      '<div id="finActions" class="modal-foot" style="margin-top:14px;border-radius:12px;border:1px solid var(--line-2)"></div>'
    );
  }

  function finCanEdit(v) {
    return (v.status === "draft" || v.status === "correction_required") &&
      has("financial_summary.update");
  }

  // The manager's editable form (deck slide 23). Six mandatory money fields
  // plus optional notes, matching the deck's own field list; the computed
  // figures stay read-only underneath. [حفظ مسودة] persists the draft without
  // submitting it, so a partially filled month is never lost.
  function finDraftForm(v) {
    var disabled = has("financial_summary.update") ? "" : " disabled";
    return (
      '<div class="sec-title">' + dual("بيانات النموذج", "Form data") + "</div>" +
      '<p class="note-block"><span class="lbl">' + dual("ملاحظة", "Note") + "</span>" +
      dual("الحقول الإلزامية مميزة بعلامة *", "Mandatory fields are marked *") + "</p>" +
      '<div class="av-grid cols-2">' +
      field("إجمالي الإيرادات *", "Total revenue *", numInput("finfRevenue", v.submitted_revenue)) +
      field("إجمالي المصروفات *", "Total expenses *", numInput("finfExpenses", v.submitted_expenses)) +
      field("الرصيد البنكي نهاية الشهر *", "Closing bank balance *", numInput("finfBank", v.closing_bank_balance)) +
      field("النقد في الصندوق *", "Cash in hand *", numInput("finfCash", v.closing_cash_balance)) +
      field("الديون غير المسددة *", "Outstanding debts *", numInput("finfDebts", v.outstanding_debts)) +
      field("الذمم لدى العملاء *", "Customer receivables *", numInput("finfReceivables", v.customer_receivables)) +
      "</div>" +
      field("ملاحظات المدير *", "Manager notes *",
        '<textarea class="av-textarea" id="finfNotes" style="width:100%">' +
        escapeHtml(v.manager_notes || "") + "</textarea>",
        "اختياري", "Optional") +
      '<div class="av-toolbar" style="margin-top:8px">' +
      '<button class="btn-solid" id="finSaveDraft"' + disabled + ">" +
      dual("حفظ مسودة", "Save draft") + "</button>" +
      "</div>"
    );
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
      btns.push('<button class="btn-solid gold" id="finApprove">' + dual("اعتماد التقرير", "Approve report") + "</button>");
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
    if (byId("finSaveDraft")) byId("finSaveDraft").addEventListener("click", function () { finSaveDraft(v, this); });

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
      // Deck slide 23 names the page's primary action [إرسال للمحاسب] and the
      // form's button [إرسال للمراجعة]; this confirmation is that same send, so
      // it carries the deck's primary-action wording.
      confirmLabel: dual("إرسال للمحاسب", "Send to accountant"),
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

  function finSaveDraft(v, btn) {
    var body = {
      submitted_revenue: numVal("finfRevenue"),
      submitted_expenses: numVal("finfExpenses"),
      closing_bank_balance: numVal("finfBank"),
      closing_cash_balance: numVal("finfCash"),
      outstanding_debts: numVal("finfDebts"),
      customer_receivables: numVal("finfReceivables"),
      manager_notes: valOf("finfNotes") || null,
    };
    busy(btn, true);
    patch("/api/v1/financial/summaries/" + v.id, body)
      .then(function () {
        toast(STATE.lang === "ar" ? "حُفظت المسودة." : "Draft saved.", "ok");
        finReload({ id: v.period_id });
      })
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
      var spec = supportFilterSpec();
      var list = rows.filter(function (r) {
        return !st || r.status === st;
      });
      list = applyListFilters(scopeFilter(list), "support", spec);
      // The API already orders these newest-first; the deck's secondary sort by
      // ID (slides 134-136) is layered on so paging stays deterministic.
      list.sort(function (a, b) {
        return String(b.created_at || "").localeCompare(String(a.created_at || "")) || byIdAsc(a, b);
      });
      renderPaged(host, "support", list, supportRowCard, function (h) {
        h.querySelectorAll("[data-request]").forEach(function (el) {
          el.addEventListener("click", function () {
            openSupport(parseInt(el.getAttribute("data-request"), 10));
          });
        });
      }, spec);
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
                ? '<button class="btn-outline" id="supAssignBtn">' + dual("إسناد للمختص", "Assign to specialist") + "</button>"
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
        '<button class="btn-solid" id="asgSave" disabled>' + dual("إسناد للمختص", "Assign to specialist") + "</button>",
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
        // Deck slide 18 names two controls on the create form: [حفظ مسودة] and
        // [إرسال الطلب]. There is no draft status on the server for a support
        // request (the spec's Table 49 sends it straight to the specialist), so
        // the draft is kept on the device and re-filled the next time the form
        // opens; sending clears it.
        '<button class="btn-outline" id="ncCancel">' + dual("إلغاء", "Cancel") + "</button>" +
        '<button class="btn-outline" id="ncDraft">' + dual("حفظ مسودة", "Save draft") + "</button>" +
        '<button class="btn-solid" id="ncSave">' + dual("إرسال الطلب", "Send request") + "</button>",
      onMount: function (root) {
        var DRAFT_KEY = "safir.supportDraft.v1";
        var draft = null;
        try { draft = JSON.parse(localStorage.getItem(DRAFT_KEY) || "null"); } catch (e) { /* storage disabled */ }
        if (draft) {
          [["ncCompany", draft.company_id], ["ncCat", draft.category],
           ["ncTitle", draft.title], ["ncDesc", draft.description],
           ["ncDims", draft.dimensions], ["ncPlatform", draft.platform],
           ["ncRef", draft.reference_link]].forEach(function (pair) {
            var el = root.querySelector("#" + pair[0]);
            if (el && pair[1]) el.value = pair[1];
          });
        }
        root.querySelector("#ncCancel").addEventListener("click", closeModal);
        root.querySelector("#ncDraft").addEventListener("click", function () {
          try {
            localStorage.setItem(DRAFT_KEY, JSON.stringify({
              company_id: root.querySelector("#ncCompany").value,
              category: root.querySelector("#ncCat").value,
              title: root.querySelector("#ncTitle").value,
              description: root.querySelector("#ncDesc").value,
              dimensions: root.querySelector("#ncDims").value,
              platform: root.querySelector("#ncPlatform").value,
              reference_link: root.querySelector("#ncRef").value,
            }));
          } catch (e) { /* storage disabled */ }
          toast(dual("تم حفظ المسودة على هذا الجهاز.", "Draft saved on this device."), "ok");
        });
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
              try { localStorage.removeItem(DRAFT_KEY); } catch (e) { /* storage disabled */ }
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
        STATE.submissions = page && page.items ? page : { items: [] };
        return STATE.submissions.items;
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
      var spec = requestsFilterSpec();
      var list = applyListFilters(rows, "requests", spec);
      list.sort(function (a, b) {
        return String(b.created_at || "").localeCompare(String(a.created_at || "")) || byIdAsc(a, b);
      });
      host.innerHTML = "";
      // Deck slide 38: the empty state names the deck's own message and its
      // primary [إنشاء طلب] control, so a first-time user is not left staring
      // at "no rows match the filters".
      if (!rows.length) {
        host.innerHTML =
          '<div class="lf-empty">' +
          emptyHtml("لا توجد طلبات في هذه الفترة", "No requests in this period") +
          (has("form.submit")
            ? '<button class="btn-solid" id="reqNewEmpty">' +
              dual("إنشاء طلب", "Create request") + "</button>"
            : "") +
          "</div>";
        var emptyBtn = byId("reqNewEmpty");
        if (emptyBtn) emptyBtn.addEventListener("click", function () { newRequestForm(); });
        return;
      }
      renderPaged(host, "requests", list, requestRow, function (h) {
        h.querySelectorAll("[data-submission]").forEach(function (row) {
          row.addEventListener("click", function () {
            openSubmission(parseInt(row.getAttribute("data-submission"), 10));
          });
        });
      }, spec);
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
    get("/api/v1/forms/" + s.form_id + "/versions/" + s.form_version_id +
        (s.company_id ? "?company_id=" + s.company_id : ""))
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
                  openSubmission(s.id);
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
      softGet("/api/v1/documents/categories"),
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
      STATE.documentsPage = page || { items: [] };
      var spec = documentsFilterSpec();
      var list = applyListFilters(rows, "documents", spec);
      list.sort(function (a, b) {
        return String(b.created_at || "").localeCompare(String(a.created_at || "")) || byIdAsc(a, b);
      });
      renderPaged(host, "documents", list, documentRow, function (h) {
        h.querySelectorAll("[data-doc]").forEach(function (row) {
          row.addEventListener("click", function () {
            openDocument(JSON.parse(row.getAttribute("data-doc")));
          });
        });
      }, spec);
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
        '<div class="av-panel" id="investPortfolio"><h3>' +
        dual("سجل محفظة الملكية والاستثمارات", "Ownership & investment register") +
        "</h3>" + loadingHtml() + "</div>" +
        '<div class="av-panel"><h3>' + dual("مؤشرات المجموعة", "Group indicators") + "</h3>" + groupIndicators() + "</div>" +
        "</div>";
      host.querySelectorAll("[data-invest-co]").forEach(function (el) {
        el.addEventListener("click", function () {
          openCompany(parseInt(el.getAttribute("data-invest-co"), 10));
        });
      });
      loadInvestmentPortfolio();
    });
  }

  // ---- deck slides 107/108/109: investment register + record detail --------
  // The deck's investment screen is the *ownership* register (الملكية, القيمة
  // المرجعية/الدفترية, التقييم, المصدر) with a linked owner decision. Each
  // ownership row is the real, approved record; its documented valuation summary
  // (original value, contributions, financing, distributions, book value,
  // approved valuation) is joined from the investment-valuations endpoint when
  // the caller holds investment.read. A field with no recorded value renders as
  // "غير مُعدّ" rather than an invented zero -- the deck's own rule
  // ("عند لا يوجد لا يضع النظام صفرًا كتقييم", slide 109).
  function loadInvestmentPortfolio() {
    var host = byId("investPortfolio");
    if (!host) return;
    if (!has("ownership.read")) {
      host.innerHTML = noticeHtml(
        "لا تملك صلاحية عرض سجل الملكية.",
        "You may not view the ownership register.",
      );
      return;
    }
    var canReadVal = has("investment.read");
    Promise.all([
      softGet("/api/v1/admin/ownerships"),
      canReadVal ? softGet("/api/v1/admin/investment-valuations") : Promise.resolve([]),
    ]).then(function (res) {
      var rows = res[0] || [];
      var byCompany = {};
      (res[1] || []).forEach(function (v) { byCompany[v.owned_company_id] = v; });
      if (!rows.length) {
        host.innerHTML = portfolioActionsHtml() + noticeHtml(
          "لا توجد حصص ملكية مسجّلة بعد.",
          "No ownership stakes recorded yet.",
        );
        bindPortfolioActions(rows);
        return;
      }
      var notConfigured = dual("غير مُعدّ", "Not configured");
      function bookValueCell(v) {
        if (!v || v.book_value == null) return notConfigured;
        return escapeHtml(money(v.book_value)[STATE.lang] || "") +
          (v.book_value_date ? " · " + escapeHtml(dateStr(v.book_value_date)) : "") +
          (v.book_value_source ? " · " + escapeHtml(v.book_value_source) : "");
      }
      function valuationCell(v) {
        // Slide 109: yes/no choice; "no" states none is recorded, never a zero.
        if (!v || v.has_valuation !== true) return dual("لا يوجد تقييم معتمد", "No approved valuation");
        return escapeHtml(money(v.valuation_amount)[STATE.lang] || "") +
          (v.valuation_date ? " · " + escapeHtml(dateStr(v.valuation_date)) : "");
      }
      // The deck keeps [إضافة استثمار] / [رفع قرار] / [تقرير المحفظة] above the
      // register, so the toolbar is rendered outside the paged host (which owns
      // its own innerHTML, filter bar and pager).
      host.innerHTML = portfolioActionsHtml() + '<div id="investList"></div>';
      var listHost = byId("investList");
      var spec = [
        { key: "q", type: "search", ar: "الشركة / المالك", en: "Company / owner",
          fields: ["owned_company_name_ar", "owned_company_name_en",
                   "owner_company_name_ar", "owner_company_name_en", "external_owner_name"] },
        { key: "status", ar: "حالة الاستثمار", en: "Investment status", field: "status",
          options: distinctOptions(rows, function (r) { return r.status; },
            function (v) {
              var m = { active: ["نشط", "Active"], ended: ["مغلق", "Closed"] };
              return { ar: (m[v] || [v])[0], en: (m[v] || [v, v])[1] };
            }) },
        { key: "currency", ar: "العملة الأصلية", en: "Original currency",
          resolve: function (r) { var v = byCompany[r.owned_company_id]; return v && v.currency; },
          options: distinctOptions(rows, function (r) {
            var v = byCompany[r.owned_company_id]; return v && v.currency;
          }) },
      ];
      var list = applyListFilters(rows, "investments", spec);
      // Deck default sort: "الاسم" then the newest valuation / investment date.
      list.sort(function (a, b) {
        return String(a.owned_company_name_ar || "").localeCompare(
          String(b.owned_company_name_ar || ""), "ar") || byIdAsc(a, b);
      });
      renderPaged(listHost, "investments", list, function (o) {
        var name = STATE.lang === "ar"
          ? o.owned_company_name_ar || o.owned_company_name_en
          : o.owned_company_name_en || o.owned_company_name_ar;
        var owner = o.owner_company_id
          ? (STATE.lang === "ar" ? o.owner_company_name_ar : o.owner_company_name_en)
          : o.external_owner_name;
        var pct = plainNum(o.ownership_percentage) + "%";
        var v = byCompany[o.owned_company_id];
        var valBlock = canReadVal
          ? '<div class="s">' +
            dual("القيمة الدفترية", "Book value") + ": " + bookValueCell(v) +
            " · " + dual("التقييم", "Valuation") + ": " + valuationCell(v) +
            (v && v.currency ? " · " + escapeHtml(v.currency) : "") +
            "</div>"
          : "";
        return (
          '<div class="av-row" data-invest-own="' + o.owned_company_id + '">' +
          '<div class="co-dot" style="background:' + PALETTE[o.owned_company_id % PALETTE.length] + '">' +
          initial(name) + "</div>" +
          '<div class="grow"><div class="t">' + escapeHtml(name) + "</div>" +
          '<div class="s">' + dual("المالك", "Owner") + ": " + escapeHtml(owner || "—") +
          " · " + dual("الملكية", "Ownership") + " " + pct +
          " · " + dual("تاريخ النفاذ", "Effective") + " " + escapeHtml(dateStr(o.effective_from)) +
          "</div>" + valBlock + "</div>" +
          statusBadgeFromMap(o.status, {
            active: ["قائمة", "Active", "ok"],
            ended: ["منتهية", "Ended", "warn"],
          }) +
          '<button type="button" class="btn-outline" data-invest-open="' + o.owned_company_id + '">' +
          dual("فتح التفاصيل", "Open details") + "</button></div>"
        );
      }, function (h, slice) {
        h.querySelectorAll("[data-invest-open]").forEach(function (btn) {
          btn.addEventListener("click", function () {
            openInvestment(parseInt(btn.getAttribute("data-invest-open"), 10));
          });
        });
      }, spec);
      bindPortfolioActions(list);
    }).catch(function (err) {
      host.innerHTML = errorHtml(errText(err));
    });
  }

  // Deck slide 107 names three actions beside [فتح التفاصيل]: [إضافة استثمار]
  // (a new ownership stake), [رفع قرار] (raise the linked owner decision) and
  // [تقرير المحفظة] (export the register the caller is already looking at).
  // Each appears only when the role holds the permission its endpoint enforces,
  // so no control is offered that would 403.
  function portfolioActionsHtml() {
    var acts = "";
    if (has("ownership.manage")) {
      acts += '<button type="button" class="btn-outline" id="invAdd">' +
        dual("إضافة استثمار", "Add investment") + "</button>";
    }
    if (has("owner_decision.manage")) {
      acts += '<button type="button" class="btn-outline" id="invRaiseDecision">' +
        dual("رفع قرار", "Raise decision") + "</button>";
    }
    acts += '<button type="button" class="btn-outline" id="invReport">' +
      dual("تقرير المحفظة", "Portfolio report") + "</button>";
    return '<div class="av-form-actions" id="invActions">' + acts + "</div>";
  }

  function bindPortfolioActions(rows) {
    var add = byId("invAdd");
    if (add) add.addEventListener("click", openInvestmentCreate);
    var raise = byId("invRaiseDecision");
    if (raise) raise.addEventListener("click", openPortfolioDecision);
    var report = byId("invReport");
    if (report) {
      report.addEventListener("click", function () { exportListCsv("investments", rows); });
    }
  }

  function openInvestmentCreate() {
    var ownedOpts = (STATE.companies || []).map(function (c) {
      return { value: c.id, label: companyName(c) };
    });
    var ownerOpts = [{ value: "", label: STATE.lang === "ar" ? "— (مالك خارجي)" : "— (external owner)" }]
      .concat((STATE.companies || []).map(function (c) {
        return { value: c.id, label: companyName(c) };
      }));
    openModal({
      title: dual("إضافة استثمار (حصة ملكية)", "Add investment (ownership stake)"),
      body:
        '<form class="av-form" id="invAddForm">' +
        field("الشركة المملوكة", "Owned company", selectInput("iaOwned", ownedOpts, "")) +
        field("المالك (شركة)", "Owner (company)", selectInput("iaOwner", ownerOpts, "")) +
        field("اسم المالك الخارجي", "External owner name", textInput("iaExternal", "", "")) +
        field("نسبة الملكية %", "Ownership %", numInput("iaPct", "", "")) +
        field("من تاريخ", "Effective from", dateInput("iaFrom", "")) +
        '<div class="av-form-actions"><button class="btn" type="submit">' +
        dual("حفظ", "Save") + "</button></div></form>",
      onMount: function (root, body) {
        body.querySelector("#invAddForm").addEventListener("submit", function (ev) {
          ev.preventDefault();
          var payload = {
            owned_company_id: parseInt(valOf("iaOwned"), 10),
            ownership_percentage: numVal("iaPct"),
            effective_from: valOf("iaFrom") || null,
          };
          var owner = valOf("iaOwner");
          var external = valOf("iaExternal");
          if (owner) payload.owner_company_id = parseInt(owner, 10);
          else if (external) payload.external_owner_name = external;
          post("/api/v1/admin/ownerships", payload).then(function () {
            toast(dual("تمت إضافة الحصة.", "Stake added."), "ok");
            closeModal();
            loadInvestmentPortfolio();
          }).catch(domainError);
        });
      },
    });
  }

  function openPortfolioDecision() {
    openModal({
      title: dual("رفع قرار مالك مرتبط بالمحفظة", "Raise an owner decision linked to the portfolio"),
      body:
        '<form class="av-form" id="invDecisionForm">' +
        field("رقم القرار", "Decision number", textInput("idNumber", "", "")) +
        field("الموضوع", "Title", textInput("idTitle", "", "")) +
        field("الشركة", "Company",
          selectInput("idCompany", [{ value: "", label: STATE.lang === "ar" ? "— (القابضة)" : "— (Holding)" }]
            .concat((STATE.companies || []).map(function (c) {
              return { value: c.id, label: companyName(c) };
            })), "")) +
        field("النص", "Body", textArea("idBody", "", "")) +
        field("تاريخ الاستحقاق", "Due date", dateInput("idDue", "")) +
        '<div class="av-form-actions"><button class="btn" type="submit">' +
        dual("رفع القرار", "Raise decision") + "</button></div></form>",
      onMount: function (root, body) {
        body.querySelector("#invDecisionForm").addEventListener("submit", function (ev) {
          ev.preventDefault();
          var company = valOf("idCompany");
          post("/api/v1/operations/owner-decisions", {
            number: valOf("idNumber"),
            title: valOf("idTitle"),
            company_id: company ? parseInt(company, 10) : null,
            body: valOf("idBody") || null,
            due_date: valOf("idDue") || null,
          }).then(function () {
            toast(dual("تم رفع القرار.", "Decision raised."), "ok");
            closeModal();
          }).catch(domainError);
        });
      },
    });
  }

  function openInvestment(companyId) {
    openModal({
      title: dual("تفاصيل الاستثمار والقرار المرتبط", "Investment detail & linked decision"),
      wide: true,
      body: loadingHtml(),
      onMount: function () {
        Promise.all([
          softGet("/api/v1/admin/ownerships?owned_company_id=" + companyId),
          softGet("/api/v1/operations/owner-decisions?company_id=" + companyId),
          softGet("/api/v1/admin/investment-valuations/" + companyId),
          ensureCompanies(),
        ]).then(function (res) {
          var stakes = (res[0] || []).filter(function (o) { return o.status === "active"; });
          var decisions = res[1] || [];
          var val = res[2] || {};
          var body = byId("modalBody");
          if (!body) return;
          var name = companyNameById(companyId);
          var stake = stakes[0];
          var ownership = stake ? plainNum(stake.ownership_percentage) + "%" : null;
          // Deck slide 109: a figure with no recorded value is shown as غير مُعدّ,
          // never as an invented zero. ``dual()`` returns markup, so it is passed
          // to kv() unescaped; server strings stay escaped.
          var notConfigured = dual("غير مُعدّ", "Not configured");
          function amount(v) {
            return v === null || v === undefined ? notConfigured : escapeHtml(money(v)[STATE.lang] || "");
          }
          var hasVal = val.has_valuation === true;
          // The valuation is a yes/no choice: "yes" shows the approved amount,
          // date, source and reference; "no" explicitly states none is recorded.
          var valuationTxt = hasVal
            ? amount(val.valuation_amount) + " · " +
              dual("بتاريخ ", "on ") + escapeHtml(dateStr(val.valuation_date)) +
              (val.valuation_source ? " · " + escapeHtml(val.valuation_source) : "") +
              (val.valuation_reference ? " · " + escapeHtml(val.valuation_reference) : "")
            : dual("لا يوجد تقييم معتمد", "No approved valuation");
          var canEdit = has("investment.manage");
          body.innerHTML =
            '<div class="kv">' +
            kv(dual("الشركة", "Company"), escapeHtml(name)) +
            kv(dual("نسبة الملكية", "Ownership %"),
               ownership ? escapeHtml(ownership) + " · " +
                 dual("منذ ", "since ") + escapeHtml(dateStr(stake.effective_from))
                 : notConfigured) +
            kv(dual("الحالة", "Status"), stake
              ? statusBadgeFromMap(stake.status, { active: ["قائمة", "Active", "ok"], ended: ["منتهية", "Ended", "warn"] })
              : notConfigured) +
            kv(dual("القيمة الأصلية وتاريخ الاستثمار", "Original value & date"),
               val.original_value == null && !val.investment_date ? notConfigured
                 : amount(val.original_value) +
                   (val.investment_date ? " · " + escapeHtml(dateStr(val.investment_date)) : "")) +
            kv(dual("المساهمات الرأسمالية اللاحقة", "Subsequent contributions"), amount(val.subsequent_contributions)) +
            kv(dual("التمويل أو القروض", "Financing / loans"), amount(val.financing)) +
            kv(dual("التوزيعات المستلمة", "Distributions received"), amount(val.distributions)) +
            kv(dual("القيمة الدفترية وتاريخها", "Book value & date"),
               val.book_value == null ? notConfigured
                 : amount(val.book_value) +
                   (val.book_value_date ? " · " + escapeHtml(dateStr(val.book_value_date)) : "") +
                   (val.book_value_source ? " · " + escapeHtml(val.book_value_source) : "")) +
            kv(dual("التقييم المعتمد", "Approved valuation"), valuationTxt) +
            kv(dual("القرار المرتبط", "Linked decision"),
               escapeHtml(val.decision_reference || "") || notConfigured) +
            "</div>" +
            '<div class="s">' +
            dual(
              "القيمة الدفترية تدخل كما اعتمدها المحاسب بتاريخها ومصدرها ولا تُحسب بجمع المساهمات والتمويل والتوزيعات؛ عند غياب التقييم لا يضع النظام صفرًا.",
              "The book value is entered as approved by the accountant with its date and source, never derived by summing contributions, financing and distributions; with no valuation the system stores no zero.",
            ) + "</div>" +
            (canEdit
              ? '<div class="av-form-actions"><button type="button" class="btn" id="invEdit">' +
                dual("تعديل القيم والتقييم", "Edit figures & valuation") + "</button></div>"
              : "") +
            '<div class="sec-title">' + dual("القرار المرتبط", "Linked decision") + "</div>" +
            (decisions.length
              ? '<div class="av-list">' + decisions.map(function (d) {
                  return '<div class="av-row" style="cursor:default"><div class="grow">' +
                    '<div class="t">' + escapeHtml(d.number + " · " + d.title) + "</div>" +
                    '<div class="s">' + escapeHtml(d.follow_up_note || "") + "</div></div>" +
                    statusBadgeFromMap(d.status, {
                      open: ["مفتوح", "Open", "warn"],
                      in_progress: ["قيد التنفيذ", "In progress", "rev"],
                      done: ["منفّذ", "Done", "ok"],
                      cancelled: ["ملغى", "Cancelled", "miss"],
                    }) + "</div>";
                }).join("") + "</div>"
              : noticeHtml("لا يوجد قرار مرتبط بعد.", "No linked decision yet.")) +
            '<div class="s">' +
            dual(
              "كل زيادة ملكية أو تخارج يرتبط بقرار؛ يحتفظ بالسابق ولا يُلغى استثمار معتمد بغير إصدار مرتبط.",
              "Every ownership increase or exit links to a decision; the previous one is kept and an approved investment is never cancelled without a linked version.",
            ) + "</div>";
          var editBtn = byId("invEdit");
          if (editBtn) {
            editBtn.addEventListener("click", function () { openInvestmentEdit(companyId, val); });
          }
        }).catch(function (err) {
          var body = byId("modalBody");
          if (body) body.innerHTML = errorHtml(errText(err));
        });
      },
    });
  }

  function openInvestmentEdit(companyId, val) {
    val = val || {};
    openModal({
      title: dual("إدخال قيم الاستثمار والتقييم", "Enter investment figures & valuation"),
      wide: true,
      body:
        '<form class="av-form" id="invForm">' +
        field("العملة", "Currency", textInput("invCurrency", val.currency || "SAR")) +
        field("تاريخ الاستثمار", "Investment date", dateInput("invDate", val.investment_date || "")) +
        field("القيمة الأصلية", "Original value", numInput("invOriginal", val.original_value != null ? val.original_value : "")) +
        field("المساهمات الرأسمالية اللاحقة", "Subsequent contributions", numInput("invContrib", val.subsequent_contributions != null ? val.subsequent_contributions : "")) +
        field("التمويل أو القروض", "Financing / loans", numInput("invFinancing", val.financing != null ? val.financing : "")) +
        field("التوزيعات المستلمة", "Distributions received", numInput("invDistributions", val.distributions != null ? val.distributions : "")) +
        field("القيمة الدفترية", "Book value", numInput("invBook", val.book_value != null ? val.book_value : "")) +
        field("تاريخ القيمة الدفترية", "Book value date", dateInput("invBookDate", val.book_value_date || "")) +
        field("مصدر القيمة الدفترية", "Book value source", textInput("invBookSource", val.book_value_source || "")) +
        field("يوجد تقييم معتمد؟", "Has an approved valuation?",
          '<select id="invHasVal" class="inp"><option value="false"' + (val.has_valuation ? "" : " selected") + ">" +
          dual("لا يوجد", "No") + '</option><option value="true"' + (val.has_valuation ? " selected" : "") + ">" +
          dual("يوجد", "Yes") + "</option></select>") +
        field("مبلغ التقييم", "Valuation amount", numInput("invValAmount", val.valuation_amount != null ? val.valuation_amount : "")) +
        field("تاريخ التقييم", "Valuation date", dateInput("invValDate", val.valuation_date || "")) +
        field("جهة التقييم", "Valuation source", textInput("invValSource", val.valuation_source || "")) +
        field("مرجع التقييم", "Valuation reference", textInput("invValRef", val.valuation_reference || "")) +
        field("معرف قرار الاعتماد", "Approving decision id", textInput("invDecision", val.decision_reference || "")) +
        '<div class="av-form-actions"><button class="btn" type="submit">' +
        dual("حفظ", "Save") + "</button></div></form>",
      onMount: function (root, body) {
        var form = body.querySelector("#invForm");
        form.addEventListener("submit", function (ev) {
          ev.preventDefault();
          var hasVal = valOf("invHasVal") === "true";
          patch("/api/v1/admin/investment-valuations/" + companyId, {
            currency: valOf("invCurrency") || null,
            investment_date: valOf("invDate") || null,
            original_value: numVal("invOriginal"),
            subsequent_contributions: numVal("invContrib"),
            financing: numVal("invFinancing"),
            distributions: numVal("invDistributions"),
            book_value: numVal("invBook"),
            book_value_date: valOf("invBookDate") || null,
            book_value_source: valOf("invBookSource") || null,
            has_valuation: hasVal,
            valuation_amount: hasVal ? numVal("invValAmount") : null,
            valuation_date: hasVal ? (valOf("invValDate") || null) : null,
            valuation_source: hasVal ? (valOf("invValSource") || null) : null,
            valuation_reference: hasVal ? (valOf("invValRef") || null) : null,
            decision_reference: valOf("invDecision") || null,
          }).then(function () {
            toast(dual("تم حفظ قيم الاستثمار.", "Investment figures saved."), "ok");
            closeModal();
            openInvestment(companyId);
          }).catch(domainError);
        });
      },
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
  // Deck slide 35 carries one primary action, [إعداد ملخص]: it asks the AI
  // provider for a grounded executive summary of the current period. The
  // figures come only from the same scoped context the answer engine already
  // receives, so nothing outside the user's scope can appear.
  function bindBiToolbar() {
    var btn = byId("biSummarize");
    if (!btn || btn.getAttribute("data-bound")) return;
    btn.setAttribute("data-bound", "1");
    btn.addEventListener("click", function () {
      var panel = byId("biSummaryPanel");
      var scope = aiScope("ملخص أداء الشركات");
      if (!scope) {
        toast(STATE.lang === "ar" ? "لا نطاق متاح للتلخيص." : "No scope available to summarise.", "warn");
        return;
      }
      busy(btn, true);
      post(scope.path, scope.payload)
        .then(function (data) {
          if (panel) {
            panel.hidden = false;
            panel.innerHTML =
              "<h3>" + dual("ملخص الأداء", "Performance summary") + "</h3>" +
              '<p class="brief-summary"><span class="ar">' + escapeHtml(data.answer) +
              '</span><span class="en">' + escapeHtml(data.answer) + "</span></p>";
          }
          toast(STATE.lang === "ar" ? "تم إعداد الملخص." : "Summary prepared.", "ok");
        })
        .catch(function (err) { toast(errText(err), "err"); })
        .then(function () { busy(btn, false); });
    });
  }

  function renderBi() {
    var host = byId("biContent");
    if (!host) return Promise.resolve();
    host.innerHTML = loadingHtml();
    bindBiToolbar();
    return Promise.all([loadInsights(true), ensureReports(), ensureCompanies()]).then(function () {
      var insights = STATE.insights;
      host.innerHTML =
        '<div class="av-panel" id="biSummaryPanel" style="margin-bottom:12px" hidden></div>' +
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
          '<button class="btn-outline" data-notif-open="' + n.id + '">' +
          notifActionLabel(n) + "</button>" +
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
    host.querySelectorAll("[data-notif-open]").forEach(function (el) {
      el.addEventListener("click", function (ev) {
        ev.stopPropagation();
        var id = parseInt(el.getAttribute("data-notif-open"), 10);
        var row = (STATE.notifications || []).filter(function (n) { return n.id === id; })[0];
        if (row) openNotification(row, el);
      });
    });
    return Promise.resolve();
  }

  // Deck slide 36: every alert carries [فتح التنبيه], which marks it read and
  // opens the record it is about. The target is derived from the notification's
  // soft entity reference, so a new event type routes correctly once its entity
  // type is listed here.
  var NOTIF_TARGET = {
    monthly_report: { view: "reports", open: "report" },
    form_submission: { view: "requests", open: "submission" },
    support_request: { view: "support", open: "support" },
    financial_summary_version: { view: "financial" },
    monthly_financial_report: { view: "financial" },
    financial_report: { view: "financial" },
    document: { view: "documents" },
    website_lead: { view: "leads", open: "lead" },
    task: { view: "operations" },
    assessment: { view: "employees" },
    policy_proposal: { view: "accounting" },
    currency_change_request: { view: "accounting" },
    management_brief: { view: "operations" },
    user: { view: "group" },
    role: { view: "group" },
  };

  // Deck slide 36 names the row action after the record the alert is about: a
  // pending monthly form offers [فتح الاستمارة] and a new support request
  // offers [فتح الطلب], rather than a single generic label for every type.
  function notifActionLabel(n) {
    if (n.entity_type === "monthly_report" || n.entity_type === "form_submission") {
      return dual("فتح الاستمارة", "Open form");
    }
    if (n.entity_type === "support_request") {
      return dual("فتح الطلب", "Open request");
    }
    return dual("فتح التنبيه", "Open alert");
  }

  function openNotification(n, btn) {
    var target = NOTIF_TARGET[n.entity_type] || {};
    if (btn) busy(btn, true);
    var mark = n.is_read
      ? Promise.resolve()
      : post("/api/v1/notifications/" + n.id + "/read", {}).then(function () {
          n.is_read = true;
        });
    return mark
      .then(function () {
        refreshNotifications();
        if (target.view) navTo(target.view);
        if (!n.entity_id) return;
        if (target.open === "report") return openReport(n.entity_id);
        if (target.open === "support") return openSupport(n.entity_id);
        if (target.open === "submission") return openSubmission(n.entity_id);
        if (target.open === "lead") return openLead(n.entity_id);
      })
      .catch(function (err) { domainError(err); })
      .then(function () { if (btn) busy(btn, false); });
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
    "report.deadline_missed": { ar: "تقرير شهري متأخر", en: "Monthly report late" },
    "financial_summary.submitted": { ar: "ملخص مالي مُرسل", en: "Financial summary submitted" },
    "financial_summary.returned": { ar: "ملخص مالي مُعاد", en: "Financial summary returned" },
    "financial_summary.resubmitted": { ar: "ملخص مالي مُعاد إرساله", en: "Financial summary resubmitted" },
    "financial_summary.approved": { ar: "ملخص مالي معتمد", en: "Financial summary approved" },
    "support.assigned": { ar: "طلب دعم مُسند", en: "Support assigned" },
    "support.created": { ar: "طلب خدمة جديد", en: "New service request" },
    "support.status_changed": { ar: "تغيّر حالة طلب", en: "Support status changed" },
    "task.assigned": { ar: "مهمة مُسندة", en: "Task assigned" },
    "task.status_changed": { ar: "تغيّر حالة مهمة", en: "Task status changed" },
    "financial_report.finalised": { ar: "تقرير مالي شهري معتمد", en: "Monthly financial report finalised" },
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
    assigned: { ar: "مُوزَّع", en: "Assigned", cls: "warn" },
    in_progress: { ar: "قيد المعالجة", en: "In progress", cls: "ok" },
    qualified: { ar: "مؤهل", en: "Qualified", cls: "ok" },
    escalated: { ar: "مُصعَّد", en: "Escalated", cls: "miss" },
    converted: { ar: "مُحوَّل", en: "Converted", cls: "ok" },
    closed: { ar: "مغلق", en: "Closed", cls: "ok" },
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
        STATE.opportunities = rows || [];
        var spec = opportunitiesFilterSpec();
        // The header chips and the filter bar's status select both narrow the
        // list; the chip is applied first so the deck's quick chips still work.
        var chipRows = STATE.opportunities.filter(function (o) {
          return !STATE.oppStatus || o.status === STATE.oppStatus;
        });
        var list = applyListFilters(chipRows, "opportunities", spec);
        // Deck slide 135: newest submission first.
        list.sort(function (a, b) {
          return String(b.created_at || "").localeCompare(String(a.created_at || "")) || byIdAsc(a, b);
        });
        host.innerHTML = '<div class="av-panel"><div id="oppList"></div></div>';
        renderPaged(byId("oppList"), "opportunities", list, opportunityRow, function (h) {
          h.querySelectorAll("[data-opp]").forEach(function (row) {
            row.addEventListener("click", function () {
              openOpportunity(parseInt(row.getAttribute("data-opp"), 10));
            });
          });
        }, spec);
      })
      .catch(function (err) { handleLoadError(err); host.innerHTML = errorHtml(errText(err)); });
  }

  function opportunitiesFilterSpec() {
    var rows = STATE.opportunities || [];
    return [
      { key: "q", type: "search", ar: "العنوان / القطاع / الوصف", en: "Title / sector / description",
        fields: ["public_title_ar", "public_title_en", "sector", "description"] },
      { key: "type", ar: "النوع", en: "Type", field: "opportunity_type",
        options: distinctOptions(rows, function (r) { return r.opportunity_type; },
          function (v) { return leadLabel(OPPORTUNITY_TYPE, v); }) },
      { key: "market", ar: "السوق", en: "Market", field: "market",
        options: distinctOptions(rows, function (r) { return r.market; },
          function (v) { return leadLabel(LEAD_MARKET, v); }) },
      { key: "currency", ar: "العملة", en: "Currency", field: "currency",
        options: distinctOptions(rows, function (r) { return r.currency; }) },
      { key: "period", ar: "الفترة", en: "Period",
        resolve: function (r) { return r.created_at ? String(r.created_at).slice(0, 7) : ""; },
        options: distinctOptions(rows, function (r) {
          return r.created_at ? String(r.created_at).slice(0, 7) : "";
        }) },
    ];
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
        STATE.leads = items;
        var spec = leadsFilterSpec();
        var list = applyListFilters(items, "leads", spec);
        list.sort(function (a, b) {
          return String(b.created_at || "").localeCompare(String(a.created_at || "")) || byIdAsc(a, b);
        });
        var create = has("website_lead.manage")
          ? '<form class="av-form av-form-inline" id="leadCreateForm">' +
            field("الاسم", "Name", textInput("lcName", "", "", true)) +
            field("البريد", "Email", '<input class="av-input" id="lcEmail" type="email" required>') +
            field("الهاتف", "Phone", textInput("lcPhone", "")) +
            field("الشركة", "Company", textInput("lcCompany", "")) +
            field("الخدمة", "Service", selectInput("lcService",
              Object.keys(LEAD_SERVICE).map(function (k) { return { value: k, label: opt(LEAD_SERVICE[k].ar, LEAD_SERVICE[k].en) }; }),
              "company_formation")) +
            field("السوق", "Market", selectInput("lcMarket",
              Object.keys(LEAD_MARKET).map(function (k) { return { value: k, label: opt(LEAD_MARKET[k].ar, LEAD_MARKET[k].en) }; }),
              "saudi")) +
            field("ملاحظة", "Note", textInput("lcMessage", "")) +
            '<div class="av-form-actions"><button class="btn-solid" type="submit">' +
            dual("إضافة عميل محتمل", "Add lead") + "</button></div></form>"
          : "";
        host.innerHTML = panel("العملاء المحتملون", "Leads", create + '<div id="leadList"></div>');
        renderPaged(byId("leadList"), "leads", list, leadRow, function (h) {
          h.querySelectorAll("[data-lead]").forEach(function (row) {
            row.addEventListener("click", function () {
              openLead(parseInt(row.getAttribute("data-lead"), 10));
            });
          });
        }, spec);
        var createForm = byId("leadCreateForm");
        if (createForm) {
          createForm.addEventListener("submit", function (ev) {
            ev.preventDefault();
            busy(createForm.querySelector("button"), true);
            post("/api/v1/leads", {
              full_name: valOf("lcName"),
              email: valOf("lcEmail"),
              phone: valOf("lcPhone") || null,
              company_name: valOf("lcCompany") || null,
              service_type: valOf("lcService"),
              market: valOf("lcMarket"),
              message: valOf("lcMessage") || null,
            }).then(function () {
              toast(dual("تمت إضافة العميل المحتمل.", "Lead added."), "ok");
              return renderLeads();
            }).catch(function (err) {
              domainError(err);
              busy(createForm.querySelector("button"), false);
            });
          });
        }
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
    var campaignPromise = has("campaign.read")
      ? softGet("/api/v1/operations/campaigns")
      : Promise.resolve([]);
    // D04: the append-only assignment history (read requires website_lead.read).
    var assignmentsPromise = has("website_lead.read")
      ? softGet("/api/v1/leads/" + id + "/assignments")
      : Promise.resolve([]);
    // The assignee picker needs the real user directory (holding_owner/admin).
    var usersPromise = has("website_lead.assign") && has("user.read")
      ? softGet("/api/v1/users").then(function (rows) {
          STATE.users = rows || [];
          return STATE.users;
        })
      : Promise.resolve([]);
    return Promise.all([
      campaignPromise,
      assignmentsPromise,
      usersPromise,
      ensureCompanies(),
    ]).then(function (res) {
      return get("/api/v1/leads/" + id).then(function (lead) {
        return paintLeadModal(lead, res[0] || [], res[1] || []);
      });
    });
  }

  // D04 assignment: who owns the lead and which company it is routed to, plus
  // the append-only history. Only users holding website_lead.assign can change
  // it; everyone who can read the lead sees the current owner and history.
  function assignmentBlock(lead, assignments) {
    var canAssign = has("website_lead.assign");
    var canRoute = has("company.read");
    if (!lead.assigned_to_id && !lead.routed_company_id && !canAssign && !(assignments || []).length) {
      return "";
    }
    var current =
      '<div class="kv">' +
      kv(dual("المسؤول الحالي", "Current assignee"),
         escapeHtml(
           (STATE.lang === "ar"
             ? lead.assigned_to_name_ar
             : lead.assigned_to_name_en || lead.assigned_to_name_ar) ||
           (lead.assigned_to_id ? "#" + lead.assigned_to_id : "—"),
         )) +
      kv(dual("الشركة الموجَّه إليها", "Routed company"),
         escapeHtml(
           lead.routed_company_id
             ? companyName(companyById(lead.routed_company_id)) || "#" + lead.routed_company_id
             : "—",
         )) +
      "</div>";

    var controls = "";
    if (canAssign) {
      var userOptions = (STATE.users || []).map(function (u) {
        var label = (STATE.lang === "ar" ? u.full_name_ar : u.full_name_en || u.full_name_ar) +
          " · " + (u.role_name_ar || u.role_code);
        return '<option value="' + u.id + '"' +
          (u.id === lead.assigned_to_id ? " selected" : "") + ">" + escapeHtml(label) + "</option>";
      }).join("");
      controls =
        '<div class="av-field" style="margin-top:10px"><label>' + dual("إسناد إلى", "Assign to") + "</label>" +
        '<select class="av-select" id="leadAssignee" style="width:100%">' +
        (userOptions
          ? '<option value="">' + dual("— بدون تغيير —", "— No change —") + "</option>" + userOptions
          : '<option value="">' + dual("لا يوجد مستخدمون متاحون", "No users available") + "</option>") +
        "</select></div>" +
        (canRoute
          ? '<div class="av-field" style="margin-top:8px"><label>' + dual("توجيه إلى شركة", "Route to company") + "</label>" +
            '<select class="av-select" id="leadCompany" style="width:100%">' +
            '<option value="">' + dual("— بدون تغيير —", "— No change —") + "</option>" +
            (STATE.companies || []).map(function (c) {
              return '<option value="' + c.id + '"' +
                (c.id === lead.routed_company_id ? " selected" : "") + ">" +
                escapeHtml(companyName(c)) + "</option>";
            }).join("") +
            "</select></div>"
          : "") +
        '<div class="av-field" style="margin-top:8px"><label>' +
        dual("سبب الإسناد / إعادة الإسناد", "Assignment / reassignment reason") + "</label>" +
        '<input class="av-input" id="leadAssignReason" style="width:100%" placeholder="' +
        escAttr(STATE.lang === "ar" ? "مطلوب عند إعادة الإسناد" : "Required when reassigning") + '"></div>' +
        '<div class="av-form-actions"><button class="btn-solid" id="leadAssignSave">' +
        dual("حفظ الإسناد", "Save assignment") + "</button></div>";
    }

    // Newest first, as the API returns them.
    var history = (assignments || []).map(function (a) {
      var what = a.action === "reassign"
        ? opt("إعادة إسناد", "Reassigned")
        : opt("إسناد", "Assigned");
      var to = [];
      if (a.new_assignee_name_ar) to.push(a.new_assignee_name_ar);
      if (a.new_company_id) to.push("#" + a.new_company_id);
      return (
        '<div class="av-row"><div class="grow"><div class="t">' +
        escapeHtml(what) + (to.length ? " · " + escapeHtml(to.join(" / ")) : "") +
        "</div><div class=\"s\">" +
        (a.actor_name_ar ? escapeHtml(a.actor_name_ar) + " · " : "") +
        escapeHtml(stampText(a.created_at)) +
        (a.reason ? " · " + escapeHtml(a.reason) : "") +
        "</div></div></div>"
      );
    }).join("");

    return (
      '<h3 style="margin-top:16px">' + dual("الإسناد والتوجيه", "Assignment & routing") + "</h3>" +
      current +
      controls +
      (history
        ? '<h4 style="margin-top:12px;font-size:12px;color:var(--ink-400)">' +
          dual("سجل الإسناد", "Assignment history") + "</h4>" +
          '<div class="av-list">' + history + "</div>"
        : "")
    );
  }

  // The closed-out fields of a lead (S13): the recorded result and internal
  // notes. Kept read-only here; the "Update lead" block below edits the live
  // fields, and website_lead.manage gates the write.
  function outcomeBlock(lead) {
    if (!lead.final_result && !lead.internal_notes && !lead.closed_at) return "";
    return (
      '<h3 style="margin-top:16px">' + dual("نتيجة الطلب", "Outcome") + "</h3>" +
      '<div class="kv">' +
      kv(dual("النتيجة النهائية", "Final result"),
         lead.final_result ? escapeHtml(lead.final_result) : "—") +
      kv(dual("ملاحظات داخلية", "Internal notes"),
         lead.internal_notes ? escapeHtml(lead.internal_notes) : "—") +
      kv(dual("أُغلق في", "Closed at"), lead.closed_at ? escapeHtml(stampText(lead.closed_at)) : "—") +
      "</div>"
    );
  }

  function paintLeadModal(lead, campaigns, assignments) {
      var id = lead.id;
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
        assignmentBlock(lead, assignments) +
        outcomeBlock(lead) +
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
            // S13/§18: link the lead to its campaign (never a copied name).
            (campaigns && campaigns.length
              ? '<select id="leadCampSel">' +
                '<option value="">' + dual("بلا حملة", "No campaign") + "</option>" +
                campaigns.map(function (c) {
                  return '<option value="' + c.id + '"' + (c.id === lead.campaign_id ? " selected" : "") + ">" +
                    escapeHtml(c.name) + "</option>";
                }).join("") +
                "</select>"
              : "") +
            // S13: the closed-out fields are written here, alongside the status
            // that closes the lead; outcomeBlock above only reads them back.
            '<div class="av-field" style="margin-top:8px"><label>' +
            dual("النتيجة النهائية", "Final result") + "</label>" +
            '<input class="av-input" id="leadFinalResult" style="width:100%" value="' +
            escAttr(lead.final_result || "") + '"></div>' +
            '<div class="av-field" style="margin-top:8px"><label>' +
            dual("ملاحظات داخلية", "Internal notes") + "</label>" +
            '<input class="av-input" id="leadInternalNotes" style="width:100%" value="' +
            escAttr(lead.internal_notes || "") + '"></div>' +
            '<div class="av-user-controls" data-stop="1" style="margin-top:8px">' +
            '<button class="btn-solid" id="leadSave">' + dual("حفظ", "Save") + "</button>" +
            '<button class="btn-outline" id="leadUpdateStatus">' +
            dual("تحديث الحالة", "Update status") + "</button></div>" +
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
          var campSel = byId("leadCampSel");
          var resultInp = byId("leadFinalResult");
          var notesInp = byId("leadInternalNotes");
          var payloadOut = {};
          if (statusSel) payloadOut.status = statusSel.value;
          if (priSel) payloadOut.priority = priSel.value;
          if (campSel && campSel.value) payloadOut.campaign_id = parseInt(campSel.value, 10);
          // Only send the outcome fields when they changed: the API treats a
          // null as "unchanged", and the record should not gain empty text.
          if (resultInp && resultInp.value.trim() !== (lead.final_result || "")) {
            payloadOut.final_result = resultInp.value.trim();
          }
          if (notesInp && notesInp.value.trim() !== (lead.internal_notes || "")) {
            payloadOut.internal_notes = notesInp.value.trim();
          }
          patch("/api/v1/leads/" + id, payloadOut)
            .then(function () {
              toast(STATE.lang === "ar" ? "تم تحديث الطلب." : "Lead updated.", "ok");
              closeModal();
              loadLeadList();
              loadLeadStats();
            })
            .catch(function (err) {
              toast(
                err && err.message
                  ? err.message
                  : STATE.lang === "ar" ? "تعذّر التحديث." : "Update failed.",
                "err",
              );
            });
        });
      }

      // Deck slide 15: [تحديث الحالة] is the lead's status action on its own,
      // separate from the general save. It sends the same field the save does,
      // so the transition rules live in one place server-side.
      var statusBtn = byId("leadUpdateStatus");
      if (statusBtn) {
        statusBtn.addEventListener("click", function () {
          var statusSel = byId("leadStatusSel");
          if (!statusSel) return;
          busy(statusBtn, true);
          patch("/api/v1/leads/" + id, { status: statusSel.value })
            .then(function () {
              toast(dual("تم تحديث الحالة.", "Status updated."), "ok");
              closeModal();
              loadLeadList();
              loadLeadStats();
            })
            .catch(function (err) { domainError(err); busy(statusBtn, false); });
        });
      }

      // D04: assign/reassign. Sends only the fields the user actually changed,
      // so an unchanged company does not re-notify its manager and an unchanged
      // lead does not record a no-op history row.
      var assignBtn = byId("leadAssignSave");
      if (assignBtn) {
        assignBtn.addEventListener("click", function () {
          var aSel = byId("leadAssignee");
          var cSel = byId("leadCompany");
          var rInp = byId("leadAssignReason");
          var out = {};
          if (aSel && aSel.value && parseInt(aSel.value, 10) !== lead.assigned_to_id) {
            out.assignee_id = parseInt(aSel.value, 10);
          }
          if (cSel && cSel.value && parseInt(cSel.value, 10) !== lead.routed_company_id) {
            out.company_id = parseInt(cSel.value, 10);
          }
          if (out.assignee_id === undefined && out.company_id === undefined) {
            toast(
              STATE.lang === "ar" ? "لا يوجد تغيير في الإسناد." : "Nothing to change.",
              "err",
            );
            return;
          }
          if (rInp && rInp.value.trim()) out.reason = rInp.value.trim();
          busy(assignBtn, true);
          post("/api/v1/leads/" + id + "/assign", out)
            .then(function () {
              toast(STATE.lang === "ar" ? "تم حفظ الإسناد." : "Assignment saved.", "ok");
              return openLead(id);
            })
            .catch(function (err) {
              busy(assignBtn, false);
              toast(
                err && err.message
                  ? err.message
                  : STATE.lang === "ar" ? "تعذّر حفظ الإسناد." : "Could not save the assignment.",
                "err",
              );
            });
        });
      }
  }

  function refreshNotifications() {
    if (!has("notification.read_own")) return Promise.resolve();
    return Promise.all([
      softGet("/api/v1/notifications?limit=50"),
      softGet("/api/v1/notifications/summary"),
    ])
      .then(function (res) {
        STATE.notifications = (res[0] && res[0].items) || [];
        STATE.notificationsUnread = (res[1] && res[1].unread) || 0;
        paintNotifBadge();
        return STATE.notifications;
      });
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

  // Bind a simple chip tab group: clicking a chip sets its key on STATE and
  // re-renders via `render`. Used by the advisory/HR/site/assistant-learning
  // views, whose tabs filter an already-loaded, already-scoped payload.
  function bindSimpleTabs(attr, stateKey, render) {
    document.querySelectorAll("[" + attr + "]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        STATE[stateKey] = btn.getAttribute(attr);
        document.querySelectorAll("[" + attr + "]").forEach(function (b) {
          b.classList.toggle("on", b === btn);
        });
        render();
      });
    });
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

  function departmentNameById(id) {
    var d = (STATE.departments || []).filter(function (x) { return x.id === id; })[0];
    return d ? (STATE.lang === "ar" ? d.name_ar : d.name_en || d.name_ar) : String(id);
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

  function reqAttr(required) {
    return required ? " required" : "";
  }

  function numInput(id, value, placeholder, required) {
    return (
      '<input class="av-input" id="' + id + '" type="number" step="any" value="' +
      escAttr(value === null || value === undefined ? "" : value) + '" placeholder="' +
      escAttr(placeholder || "") + '"' + reqAttr(required) + ">"
    );
  }

  function dateInput(id, value, required) {
    return '<input class="av-input" id="' + id + '" type="date" value="' + escAttr(value || "") + '"' + reqAttr(required) + ">";
  }

  function textArea(id, value, placeholder, required) {
    return (
      '<textarea class="av-input" id="' + id + '" rows="2" placeholder="' +
      escAttr(placeholder || "") + '"' + reqAttr(required) + ">" + escapeHtml(value || "") + "</textarea>"
    );
  }

  function valOf(id) {
    var el = byId(id);
    return el ? String(el.value).trim() : "";
  }

  function setVal(id, value) {
    var el = byId(id);
    if (el) el.value = value == null ? "" : String(value);
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
    // Departments back the deck's "إدارة" filter (slides 101/135). The read is
    // soft so a role without department.read still gets the employee list.
    var deptReq = has("department.read") ? softGet("/api/v1/admin/departments") : Promise.resolve([]);
    return Promise.all([ensureCompanies(), get("/api/v1/employees" + q), deptReq]).then(function (res) {
      var employees = res[1] || [];
      STATE.departments = res[2] || [];
      STATE.hr = STATE.hr || {};
      STATE.hr.employees = employees;
      var canManage = has("employee.manage");
      var create = canManage
        ? '<form class="av-form av-form-inline" id="empForm">' +
          field("الشركة", "Company", selectInput("eCompany", companySelectOptions(false), STATE.companies.length ? STATE.companies[0].id : "")) +
          field("الاسم (عربي)", "Name (AR)", textInput("eNameAr", "", "", true)) +
          field("الاسم (إنجليزي)", "Name (EN)", textInput("eNameEn", "")) +
          field("المسمى الوظيفي", "Job title", textInput("eTitle", "")) +
          field("الجنسية", "Nationality", textInput("eNationality", "")) +
          field("تاريخ التعيين", "Hire date", dateInput("eHire", "")) +
          '<div class="av-form-actions"><button class="btn-solid" type="submit">' +
          dual("إضافة موظف", "Add employee") + "</button></div></form>"
        : "";
      var spec = employeesFilterSpec();
      var list = applyListFilters(employees, "employees", spec);
      list.sort(function (a, b) {
        return String(a.full_name_ar || "").localeCompare(String(b.full_name_ar || ""), "ar") || byIdAsc(a, b);
      });
      // Deck slide 101 names [تقرير الموظفين] next to [موظف جديد] and [فتح الملف].
      // The report is the caller's own filtered, scoped list exported as CSV --
      // it introduces no data access beyond what the list already shows.
      host.innerHTML = panel("الموظفون", "Employees", create + '<div id="empList"></div>');
      renderPaged(byId("empList"), "employees", list, employeeRow, function (h) {
        bindRowClicks(h, "emp", openEmployee);
      }, spec);
      if (has("employee.read")) {
        host.insertAdjacentHTML("beforeend",
          '<div class="av-panel" id="empReportPanel"><div class="av-form-actions">' +
          '<button type="button" class="btn-outline" id="empReport">' +
          dual("تقرير الموظفين", "Employee report") + "</button></div></div>");
        var reportBtn = byId("empReport");
        if (reportBtn) {
          reportBtn.addEventListener("click", function () { exportListCsv("employees", list); });
        }
      }
      // Appended after renderPaged (which owns the host's innerHTML).
      host.insertAdjacentHTML("beforeend",
        '<div class="av-panel" id="empLocalization"><h3>' +
        dual("لوحة التوطين لكل جهة", "Localization board per entity") +
        '</h3><div id="empLocBody"></div></div>');
      renderLocalizationBoard(employees);
      var form = byId("empForm");
      if (form) {
        form.addEventListener("submit", function (ev) {
          ev.preventDefault();
          busy(form.querySelector("button"), true);
          post("/api/v1/employees", {
            company_id: parseInt(valOf("eCompany"), 10),
            full_name_ar: valOf("eNameAr"),
            full_name_en: valOf("eNameEn") || null,
            job_title: valOf("eTitle") || null,
            nationality: valOf("eNationality") || null,
            hire_date: valOf("eHire") || null,
          }).then(function () { toast(dual("تمت إضافة الموظف.", "Employee added."), "ok"); return renderEmployees(); })
            .catch(function (err) { domainError(err); busy(form.querySelector("button"), false); });
        });
      }
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
      escapeHtml(e.job_title || "") + salary +
      (e.nationality ? " · " + dual("الجنسية", "Nationality") + " " + escapeHtml(e.nationality) : "") + "</div></div>" +
      statusBadgeFromMap(e.status, {
        active: ["نشط", "Active", "ok"],
        on_leave: ["في إجازة", "On leave", "warn"],
        terminated: ["منتهٍ", "Terminated", "miss"],
      }) + "</div>"
    );
  }

  // ---- deck slide 105: localization board per entity -----------------------
  // The "citizen" of an entity is the employee whose nationality matches the
  // entity's country (deck slide 106: "المواطن هو صاحب جنسية دولة الجهة"). The
  // counts are computed live from the employee rows the caller may already read;
  // a missing country or nationality is left out of both numerator and
  // denominator. The per-entity target and calculation-rule edition are
  // administration data on the company (deck slides 105/106); when a target is
  // approved the board raises a below-target alert, otherwise it shows غير مُعدّ.
  function renderLocalizationBoard(employees) {
    var host = byId("empLocBody");
    if (!host) return;
    var byCompany = {};
    (employees || []).forEach(function (e) {
      if (e.status !== "active") return;
      var cid = e.company_id;
      var c = companyById(cid);
      var bucket = byCompany[cid] || (byCompany[cid] = {
        country: (c && c.country) || null, total: 0, citizens: 0, counted: 0,
      });
      bucket.total += 1;
      if (bucket.country && e.nationality) {
        bucket.counted += 1;
        if (String(e.nationality).trim() === String(bucket.country).trim()) bucket.citizens += 1;
      }
    });
    var ids = Object.keys(byCompany);
    if (!ids.length) {
      host.innerHTML = noticeHtml("لا يوجد موظفون نشطون بعد.", "No active employees yet.");
      return;
    }
    var canEdit = has("company.manage");
    host.innerHTML =
      '<div class="s">' +
      dual(
        "المواطن هو صاحب جنسية دولة الجهة؛ النسبة = المحتسبون ÷ المشمولون × 100. لا متوسط بسيط لنسب الدول المختلفة.",
        "A citizen holds the entity's country nationality; rate = counted ÷ included × 100. No simple average across countries.",
      ) + "</div>" +
      '<div class="av-list">' + ids.map(function (cid) {
        var b = byCompany[cid];
        var c = companyById(cid) || {};
        var rate = b.counted ? ((b.citizens / b.counted) * 100) : null;
        var rateTxt = rate === null ? dual("غير مُعدّ", "Not configured")
          : (STATE.lang === "ar" ? toArabicDigits(rate.toFixed(1)) + "٪" : rate.toFixed(1) + "%");
        // The target is administration data; only an approved target can raise
        // the deck's below-target alert (slide 105: "الحالية − المستهدف؛
        // انخفاض = متابعة").
        var target = c.localization_target_pct != null ? Number(c.localization_target_pct) : null;
        var targetTxt = target === null ? dual("غير مُعدّ", "Not configured")
          : (STATE.lang === "ar" ? toArabicDigits(target) + "٪" : target + "%");
        var delta = (rate !== null && target !== null) ? (rate - target) : null;
        var alert = (delta !== null && delta < 0)
          ? '<div class="s" style="color:#b3261e">' +
            dual("انخفاض عن المستهدف — يحتاج متابعة", "Below target — needs follow-up") + "</div>"
          : "";
        var ruleTxt = c.localization_rule_version
          ? escapeHtml(c.localization_rule_version) +
            (c.localization_rule_effective_from
              ? " · " + dual("منذ ", "since ") + escapeHtml(dateStr(c.localization_rule_effective_from))
              : "")
          : dual("غير مُعدّ", "Not configured");
        var editBtn = canEdit
          ? '<div class="av-form-actions">' +
            '<button type="button" class="btn-outline" data-loc-edit="' + cid + '">' +
            dual("تحديث القاعدة والمستهدف", "Edit target & rule") + "</button></div>"
          : "";
        return (
          '<div class="av-row" style="cursor:default;flex-direction:column;align-items:stretch">' +
          '<div style="display:flex;align-items:center;gap:11px">' +
          '<div class="co-dot" style="background:' + PALETTE[cid % PALETTE.length] + '">' +
          initial(companyNameById(cid)) + "</div>" +
          '<div class="grow"><div class="t">' + escapeHtml(companyNameById(cid)) + "</div>" +
          '<div class="s">' + dual("الدولة", "Country") + ": " +
          escapeHtml(b.country || "—") + "</div></div>" +
          "</div>" +
          '<div class="kv">' +
          kv(dual("الإجمالي", "Total"), plainNum(b.total)) +
          kv(dual("المواطنون", "Citizens"), plainNum(b.citizens)) +
          kv(dual("غير المواطنين", "Non-citizens"), plainNum(b.total - b.citizens)) +
          kv(dual("المشمولون", "Included"), plainNum(b.counted)) +
          kv(dual("النسبة الحالية", "Current rate"), escapeHtml(rateTxt)) +
          kv(dual("المستهدف", "Target"), escapeHtml(targetTxt)) +
          kv(dual("قاعدة الاحتساب", "Calculation rule"), ruleTxt) +
          "</div>" + alert + editBtn + "</div>"
        );
      }).join("") + "</div>";
    host.querySelectorAll("[data-loc-edit]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        openLocalizationEdit(parseInt(btn.getAttribute("data-loc-edit"), 10));
      });
    });
  }

  function openLocalizationEdit(companyId) {
    var c = companyById(companyId) || {};
    openModal({
      title: dual("إعداد التوطين والتقرير المجمع", "Localization setup & aggregate report"),
      body:
        '<form class="av-form" id="locForm">' +
        field("النسبة المستهدفة ٪", "Target %", numInput("locTarget", c.localization_target_pct != null ? c.localization_target_pct : "")) +
        field("إصدار قاعدة الاحتساب", "Calculation-rule version", textInput("locRule", c.localization_rule_version || "")) +
        field("نفاذ القاعدة", "Rule effective from", dateInput("locRuleFrom", c.localization_rule_effective_from || "")) +
        '<div class="av-form-actions"><button class="btn" type="submit">' +
        dual("حفظ", "Save") + "</button></div></form>",
      onMount: function (root, body) {
        var form = body.querySelector("#locForm");
        form.addEventListener("submit", function (ev) {
          ev.preventDefault();
          patch("/api/v1/companies/" + companyId, {
            localization_target_pct: numVal("locTarget"),
            localization_rule_version: valOf("locRule") || null,
            localization_rule_effective_from: valOf("locRuleFrom") || null,
          }).then(function () {
            toast(dual("تم تحديث إعداد التوطين.", "Localization setup updated."), "ok");
            closeModal();
            return renderEmployees();
          }).catch(domainError);
        });
      },
    });
  }

  function openEmployee(e) {
    openModal({
      title: dual("ملف الموظف", "Employee file"),
      wide: true,
      body: loadingHtml(),
      onMount: function (root, body) {
        softGet("/api/v1/employees/" + e.id + "/movements").then(function (movements) {
          body.innerHTML = employeeDetail(e, movements || []);
          bindEmployeeDetail(body, e);
        });
      },
    });
  }

  function employeeDetail(e, movements) {
    var name = STATE.lang === "ar" ? e.full_name_ar : e.full_name_en || e.full_name_ar;
    // Deck slides 102/103: the employee file carries the identity and
    // relationship block (number, entity, department, direct manager, status,
    // nationality). Each is shown only when the row has it; no value is invented.
    var manager = (STATE.hr && STATE.hr.employees || []).filter(function (x) { return x.id === e.manager_id; })[0];
    var managerName = manager
      ? (STATE.lang === "ar" ? manager.full_name_ar : manager.full_name_en || manager.full_name_ar)
      : (e.manager_id ? "#" + plainNum(e.manager_id) : "—");
    var info = '<div class="kv">' +
      kv(dual("الشركة", "Company"), escapeHtml(companyNameById(e.company_id))) +
      kv(dual("الرقم الوظيفي", "Employee no."), escapeHtml(e.employee_code || "—")) +
      kv(dual("الاسم", "Name"), escapeHtml(name)) +
      kv(dual("الجنسية", "Nationality"), escapeHtml(e.nationality || "—")) +
      kv(dual("المسمى", "Job title"), escapeHtml(e.job_title || "—")) +
      kv(dual("الإدارة", "Department"), escapeHtml(e.department_id ? departmentNameById(e.department_id) : "—")) +
      kv(dual("المدير المباشر", "Direct manager"), escapeHtml(managerName)) +
      kv(dual("الحالة", "Status"), statusBadgeFromMap(e.status, {
        active: ["نشط", "Active", "ok"],
        on_leave: ["في إجازة", "On leave", "warn"],
        terminated: ["منتهٍ", "Terminated", "miss"],
      })) +
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

    // Deck slide 103: the restricted tab. Rendered only for a caller with the
    // restricted/salary permission; the same fields are omitted from the API
    // payload for anyone else, so this block can never leak them.
    var restricted = "";
    if (has("employee.salary.read")) {
      var links = (e.document_links || "").split(/\s*\n\s*/).filter(function (u) { return u.trim(); });
      var linksHtml = links.length
        ? links.map(function (u) {
            return '<a class="mono" href="' + escAttr(u.trim()) + '" target="_blank" rel="noopener">' +
              escapeHtml(u.trim()) + "</a>";
          }).join("<br>")
        : escapeHtml("—");
      var countsVal = e.counts_toward_localization === true
        ? dual("نعم", "Yes")
        : e.counts_toward_localization === false
          ? dual("لا", "No")
          : dual("ينتظر مراجعة", "Awaiting review");
      restricted = panel("الحقول المقيدة والاحتساب", "Restricted fields & localization",
        '<div class="kv">' +
        kv(dual("الهوية أو الإقامة", "Identity / residence"), escapeHtml(e.national_id_masked || "—")) +
        kv(dual("موقع العمل", "Work location"), escapeHtml(e.work_location || "—")) +
        kv(dual("تاريخ نفاذ البيانات", "Wage effective date"), escapeHtml(dateStr(e.wage_effective_date))) +
        kv(dual("المستندات أو الروابط الأساسية", "Key documents / links"), linksHtml) +
        kv(dual("يحتسب ضمن التوطين؟", "Counts toward localization?"), countsVal) +
        kv(dual("سبب عدم الاحتساب", "Exclusion reason"), escapeHtml(e.localization_exclusion_reason || "—")) +
        kv(dual("الوظيفة المحتسبة", "Localization job title"), escapeHtml(e.localization_job_title || "—")) +
        kv(dual("قاعدة الاحتساب المطبقة", "Applied calculation rule"), escapeHtml(e.localization_rule_version || "—")) +
        kv(dual("المراجع وتاريخ القرار", "Reference & decision date"), escapeHtml(e.localization_reference || "—")) +
        "</div>" +
        '<div class="s">' +
        dual(
          "المزايا بيان إداري فقط؛ لا احتساب راتب أو خصم أو صرف. هذه الحقول محجوبة عن المستشار والموظفين التنفيذيين.",
          "Allowances are an administrative statement only; no salary, deduction or payout is computed. These fields are withheld from the advisor and executive staff.",
        ) + "</div>");
    }

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
      restricted +
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
      softGet("/api/v1/employees/assessments/list?assessment_type=" + STATE.assessType),
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
        ? '<div id="assessList"></div>'
        : noticeHtml("لا توجد تقييمات.", "No assessments.");
      var title = STATE.assessType === "leadership" ? "تقييمات القيادة (D04: سرّية)" : "التقييمات";
      var titleEn = STATE.assessType === "leadership" ? "Leadership assessments (D04: confidential)" : "Assessments";
      host.innerHTML = panel(title, titleEn, filter + create + list);
      var assessHost = byId("assessList");
      if (assessHost) {
        // Slide 134/135 "التقييمات": the deck's search / company / period /
        // status filters and default "الفترة الأحدث" sort; the type chip above
        // still narrows employee vs. confidential leadership assessments.
        var assessSpec = [
          { key: "q", type: "search", ar: "الفترة", en: "Period", fields: ["period_label", "assessment_type"] },
          companyFilterOption(),
          { key: "status", ar: "الحالة", en: "Status", field: "status",
            options: [
              { value: "draft", ar: "مسودة", en: "Draft" },
              { value: "submitted", ar: "مُقدَّم", en: "Submitted" },
              { value: "approved", ar: "معتمد", en: "Approved" },
            ] },
        ];
        var assessRows = applyListFilters(scopeFilter(rows), "assessments", assessSpec);
        assessRows.sort(function (a, b) {
          return String(b.period_label || "").localeCompare(String(a.period_label || "")) || byIdAsc(a, b);
        });
        renderPaged(assessHost, "assessments", assessRows, assessmentRow, function (h) {
          bindRowClicks(h, "assess", openAssessment);
        }, assessSpec);
      }
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
        field("قالب المعايير", "Criteria template", selectInput("aiTemplate", [
          { value: "", label: opt("— بدون قالب —", "— No template —") },
          { value: "accountant", label: opt("المحاسب 35/20/20/15/10", "Accountant 35/20/20/15/10") },
          { value: "marketing", label: opt("التسويق 35/25/20/10/10", "Marketing 35/25/20/10/10") },
          { value: "designer", label: opt("المصمم 35/25/25/15", "Designer 35/25/25/15") },
          { value: "business_development_lead", label: opt("قيادة تطوير الأعمال", "BD lead") },
          { value: "company_lead", label: opt("قيادة الشركة", "Company lead") },
        ], "")) +
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
    // S23/AC-23: only the owner sees and edits the secret note. It is never
    // shown to a delegate (the API omits the field for non-owners).
    var ownerNote =
      a.assessment_type === "leadership" && isConfidentialOwner()
        ? panel(
            "ملاحظات المالك (سرّية)",
            "Owner notes (confidential)",
            '<div class="kv"><div class="k">' + dual("نص سري — سياق لاحق", "Secret text — later context") + "</div></div>" +
              '<form class="av-form" id="ownerNoteForm">' +
              '<textarea class="av-input" id="ownerNoteText" rows="3" placeholder="' +
              escAttr(dual("ملاحظة سرية للمالك فقط", "Private note for the owner only")) + '">' +
              escapeHtml(a.owner_note || "") + "</textarea>" +
              '<div class="av-form-actions"><button class="btn-solid" type="submit">' +
              dual("حفظ الملاحظة السرية", "Save secret note") + "</button></div></form>",
          )
        : "";
    return panel("ملخص", "Summary", '<div class="kv">' +
        kv(dual("الفترة", "Period"), escapeHtml(a.period_label)) +
        kv(dual("الحالة", "Status"), escapeHtml(a.status)) +
        kv(dual("الدرجة المرجّحة", "Weighted score"), dec(a.overall_score)) +
        "</div>" + gapNote + approve) +
      ownerNote +
      panel("المعايير", "Criteria", itemForm + list);
  }

  function bindAssessmentDetail(body, a) {
    var form = body.querySelector("#assessItemForm");
    if (form) {
      // AC-12: picking a role template prefills the criterion and locks the
      // specification's fixed weight, so the weight is never typed by hand.
      var tmplSel = form.querySelector("#aiTemplate");
      if (tmplSel) {
        tmplSel.addEventListener("change", function () {
          var key = tmplSel.value;
          if (!key) return;
          get("/api/v1/employees/assessments/criteria").then(function (data) {
            var rows = (data.templates || {})[key] || [];
            if (!rows.length) return;
            var first = rows[0];
            setVal("aiCode", first.criterion_code);
            setVal("aiNameAr", first.criterion_name_ar);
            setVal("aiNameEn", first.criterion_name_en || "");
            setVal("aiWeight", first.weight);
          }).catch(domainError);
        });
      }
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
    // S23/AC-23: save the owner's secret note. The endpoint refuses anyone but
    // the owner; the field is only rendered for the owner.
    var noteForm = body.querySelector("#ownerNoteForm");
    if (noteForm) {
      noteForm.addEventListener("submit", function (ev) {
        ev.preventDefault();
        post("/api/v1/employees/assessments/" + a.id + "/owner-note", {
          note: (body.querySelector("#ownerNoteText") || {}).value || null,
        }).then(function (updated) {
          toast(dual("تم حفظ الملاحظة السرية.", "Secret note saved."), "ok");
          openAssessment(updated);
        }).catch(domainError);
      });
    }
  }

  function renderAdvisors() {
    var host = byId("empContent");
    return Promise.all([
      ensureCompanies(),
      softGet("/api/v1/operations/advisory-sessions"),
      has("advisor.read")
        ? softGet("/api/v1/operations/advisors")
        : Promise.resolve([]),
      (has("advisor.read") || has("advisor.session.read_own"))
        ? softGet("/api/v1/operations/advisor-reports")
        : Promise.resolve([]),
    ]).then(function (res) {
      var rows = res[1] || [];
      var assignments = res[2] || [];
      var reports = res[3] || [];
      var canRecord = has("advisor.session.record");
      var create = canRecord
        ? '<form class="av-form av-form-inline" id="advForm">' +
          field("الشركة", "Company", selectInput("adCompany", companySelectOptions(false), STATE.companies.length ? STATE.companies[0].id : "")) +
          field("المستشار (معرّف المستخدم)", "Advisor user id", numInput("adUser", "", "", true), null, null, true) +
          field("الموعد", "Scheduled at", '<input class="av-input" id="adWhen" type="datetime-local">') +
          field("الموضوع", "Topic", textInput("adTopic", "")) +
          field("الملاحظات", "Notes", textInput("adNotes", "")) +
          field("التوصيات", "Recommendations", textInput("adRec", "")) +
          '<div class="av-form-actions"><button class="btn-solid" type="submit">' +
          dual("تسجيل جلسة", "Record session") + "</button></div></form>"
        : "";
      STATE.advisories = rows;
      var sessSpec = advisoriesFilterSpec();
      var sessList = applyListFilters(scopeFilter(rows), "advisories", sessSpec);
      sessList.sort(function (a, b) {
        return String(b.created_at || "").localeCompare(String(a.created_at || "")) || byIdAsc(a, b);
      });
      var sessRow = function (s) {
        var advisorName = personName(s, "advisor_name_ar", "advisor_name_en") ||
          (s.advisor_user_id ? "#" + plainNum(s.advisor_user_id) : "");
        return '<div class="av-row" style="cursor:default"><div class="grow"><div class="t">' +
          escapeHtml(s.topic || dual("جلسة استشارية", "Advisory session")) + "</div>" +
          '<div class="s">' + escapeHtml(companyNameById(s.company_id)) +
          (advisorName ? " · " + escapeHtml(advisorName) : "") + " · " +
          escapeHtml(s.scheduled_at ? String(s.scheduled_at).slice(0, 16).replace("T", " ") : "—") + "</div></div>" +
          statusBadgeFromMap(s.status, { scheduled: ["مجدولة", "Scheduled", "warn"], completed: ["مكتملة", "Completed", "ok"], cancelled: ["ملغاة", "Cancelled", "miss"] }) +
          "</div>";
      };
      host.innerHTML =
        panel("الجلسات الاستشارية", "Advisory sessions", create + '<div id="advSessions"></div>') +
        advisorAssignmentsPanel(assignments) +
        advisorReportsPanel(reports);
      renderPaged(byId("advSessions"), "advisories", sessList, sessRow, null, sessSpec);
      renderAdvisorReportsList(reports);
    }).catch(function (err) { handleLoadError(err); host.innerHTML = errorHtml(errText(err)); });
  }

  function advisorAssignmentsPanel(assignments) {
    if (!has("advisor.read")) return "";
    var canAssign = has("advisor.manage");
    var form = canAssign
      ? '<form class="av-form av-form-inline" id="advAssignForm">' +
        field("الشركة", "Company", selectInput("aaCompany", companySelectOptions(false), STATE.companies.length ? STATE.companies[0].id : "")) +
        field("المستشار (معرّف المستخدم)", "Advisor user id", numInput("aaUser", "", "", true), null, null, true) +
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
        field("المستشار (معرّف المستخدم)", "Advisor user id", numInput("arUser", "", "", true), null, null, true) +
        field("السنة", "Year", numInput("arYear", now.getFullYear(), "", true), null, null, true) +
        field("الشهر", "Month", numInput("arMonth", now.getMonth() + 1, "", true), null, null, true) +
        field("التطويرات", "Development", textInput("arDev", "")) +
        field("التحديات", "Challenges", textInput("arChal", "")) +
        field("التوصيات", "Recommendations", textInput("arRec", "")) +
        '<div class="av-form-actions">' +
        '<button class="btn-outline" type="button" data-act="adv-report-save" data-id="advReportForm">' + dual("حفظ كمسودة", "Save draft") + "</button>" +
        '<button class="btn-solid" type="button" data-act="adv-report-submit" data-id="advReportForm">' + dual("إضافة توصية", "Add recommendation") + "</button>" +
        "</div></form>"
      : "";
    var list = reports.length
      ? '<div id="advReports"></div>'
      : noticeHtml("لا توجد تقارير شهرية.", "No monthly reports.");
    return panel("التقارير الشهرية للمستشار (S19)", "Advisor monthly reports (S19)",
      '<p class="note-block">' + dual("يحفظ المستشار تقريره الشهري (التطويرات والتحديات والتوصيات) ويرسله لمدير تطوير الأعمال؛ بعد الإرسال يصبح أصلاً غير قابل للتعديل.", "An advisor saves a monthly report (development, challenges, recommendations) and submits it to Business Development; once submitted it is an immutable original.") + "</p>" +
      form + list);
  }

  function renderAdvisorReportsList(reports) {
    var host = byId("advReports");
    if (!host || !reports.length) return;
    var canWrite = has("advisor.session.record") || has("advisor.session.read_own");
    // Slide 136 "التقارير الشهرية للمستشار": company / period / status filters
    // with the deck's apply / save / clear / export cluster; newest period first.
    var spec = [
      { key: "q", type: "search", ar: "الشركة / التوصيات", en: "Company / recommendations",
        fields: ["recommendations", "development", "challenges", "company_name_ar", "company_name_en"] },
      companyFilterOption(),
      { key: "period", ar: "الفترة", en: "Period",
        resolve: function (r) { return r.period_year ? r.period_year + "-" + String(r.period_month).padStart(2, "0") : ""; },
        options: distinctOptions(reports, function (r) {
          return r.period_year ? r.period_year + "-" + String(r.period_month).padStart(2, "0") : "";
        }) },
      { key: "status", ar: "الحالة", en: "Status", field: "status",
        options: [
          { value: "draft", ar: "مسودة", en: "Draft" },
          { value: "submitted", ar: "مُرسل", en: "Submitted" },
        ] },
    ];
    var rows = applyListFilters(scopeFilter(reports), "advisorReports", spec);
    rows.sort(function (a, b) {
      return (b.period_year - a.period_year) || (b.period_month - a.period_month) || byIdAsc(a, b);
    });
    renderPaged(host, "advisorReports", rows, function (r) {
      return '<div class="av-row" style="cursor:default"><div class="grow"><div class="t">' +
        dual("تقرير", "Report") + " " + r.period_month + "/" + r.period_year + "</div>" +
        '<div class="s">' + escapeHtml(companyNameById(r.company_id)) + " · " +
        escapeHtml(r.recommendations || r.development || "—") + "</div></div>" +
        (r.status === "draft" && canWrite
          ? '<button class="btn-outline" type="button" data-act="adv-report-submit-one" data-id="' + plainNum(r.id) + '">' + dual("إرسال", "Submit") + "</button>"
          : "") +
        statusBadgeFromMap(r.status, { draft: ["مسودة", "Draft", "warn"], submitted: ["مُرسل", "Submitted", "ok"] }) +
        "</div>";
    }, null, spec);
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
      var advForm = byId("advReportForm");
      if (advForm && !advForm.reportValidity()) return;
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
      softGet("/api/v1/operations/tasks"),
    ]).then(function (res) {
      var rows = res[1] || [];
      var canCreate = has("task.create");
      var create = canCreate
        ? '<form class="av-form av-form-inline" id="taskForm">' +
          field("الشركة", "Company", selectInput("tkCompany", companySelectOptions(false), STATE.companies.length ? STATE.companies[0].id : "")) +
          field("العنوان", "Title", textInput("tkTitle", "", "", true), null, null, true) +
          field("الأولوية", "Priority", selectInput("tkPriority", [
            { value: "low", label: opt("منخفضة", "Low") },
            { value: "normal", label: opt("عادية", "Normal") },
            { value: "high", label: opt("عالية", "High") },
          ], "normal")) +
          field("تاريخ الاستحقاق", "Due date", dateInput("tkDue", "")) +
          '<div class="av-form-actions"><button class="btn-solid" type="submit">' +
          dual("إنشاء مهمة", "Create task") + "</button></div></form>"
        : "";
      var list = rows;
      STATE.ops = STATE.ops || {};
      STATE.ops.tasks = rows;
      var spec = tasksFilterSpec();
      list = applyListFilters(scopeFilter(list), "tasks", spec);
      // Deck slide 134: الطلبات/المهام sort "الأقرب استحقاقًا ثم الأقدم" -- the
      // nearest due date first, ties broken by the oldest task.
      list.sort(function (a, b) {
        return (
          String(a.due_date || "9999-12-31").localeCompare(String(b.due_date || "9999-12-31")) ||
          String(a.created_at || "").localeCompare(String(b.created_at || "")) ||
          byIdAsc(a, b)
        );
      });
      host.innerHTML = panel("المهام", "Tasks", create + '<div id="taskList"></div>');
      renderPaged(byId("taskList"), "tasks", list, taskRow, function (h) {
        bindRowClicks(h, "task", openTask);
      }, spec);
    }).catch(function (err) { handleLoadError(err); host.innerHTML = errorHtml(errText(err)); });
  }

  function taskRow(t) {
    // AC-17: prefer the server's verdict (it also excludes cancelled tasks).
    var overdue = typeof t.is_overdue === "boolean"
      ? t.is_overdue
      : (t.due_date && t.status !== "complete" && new Date(t.due_date) < new Date());
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
        bindTaskQuickActions(body, t);
      },
    });
  }

  // Deck slide 20: [بدء التنفيذ] advances a new task to in-progress,
  // [إضافة سؤال] records the specialist's clarification as a status note, and
  // [تسليم رابط] completes the task with the delivered link as its note. All
  // three reuse the status endpoint so the transition rules and the audit trail
  // stay in one place.
  function bindTaskQuickActions(body, t) {
    var start = body.querySelector('[data-act="task-start"]');
    if (start) {
      start.addEventListener("click", function () {
        busy(start, true);
        post("/api/v1/operations/tasks/" + t.id + "/status", { status: "in_progress", note: null })
          .then(function () { toast(dual("بدأ التنفيذ.", "Work started."), "ok"); closeModal(); renderTasks(); })
          .catch(function (err) { domainError(err); busy(start, false); });
      });
    }
    var ask = body.querySelector('[data-act="task-question"]');
    if (ask) {
      ask.addEventListener("click", function () { taskNoteForm(t, "question"); });
    }
    var deliver = body.querySelector('[data-act="task-deliver"]');
    if (deliver) {
      deliver.addEventListener("click", function () { taskNoteForm(t, "delivery"); });
    }
  }

  function taskNoteForm(t, kind) {
    var isDelivery = kind === "delivery";
    openModal({
      title: isDelivery
        ? dual("تسليم رابط", "Deliver link")
        : dual("إضافة سؤال", "Add question"),
      body:
        '<div class="av-field"><label>' +
        (isDelivery
          ? dual("رابط التسليم أو وصفه", "Delivery link or description")
          : dual("السؤال أو طلب التوضيح", "Question or clarification request")) +
        '</label><textarea class="av-textarea" id="tqBody"></textarea></div>',
      footer:
        '<button class="btn-outline" id="tqCancel">' + dual("إلغاء", "Cancel") + "</button>" +
        '<button class="btn-solid" id="tqSave">' + dual("حفظ", "Save") + "</button>",
      onMount: function (root) {
        root.querySelector("#tqCancel").addEventListener("click", closeModal);
        root.querySelector("#tqSave").addEventListener("click", function () {
          var note = valOf("tqBody");
          if (!note) {
            toast(dual("أدخل النص.", "Enter the text."), "warn");
            return;
          }
          busy(this, true);
          // A delivery hands the task to review (the deck's "غير مكتمل" step);
          // a question is appended to the log while the task stays where it is.
          var req = isDelivery
            ? post("/api/v1/operations/tasks/" + t.id + "/status", {
                status: "awaiting_review", note: note,
              })
            : post("/api/v1/operations/tasks/" + t.id + "/note", { note: note });
          req
            .then(function () {
              toast(isDelivery
                ? dual("تم تسجيل التسليم.", "Delivery recorded.")
                : dual("تمت إضافة السؤال.", "Question added."), "ok");
              closeModal();
              renderTasks();
            })
            .catch(function (err) { domainError(err); busy(root.querySelector("#tqSave"), false); });
        });
      },
    });
  }

  function taskDetail(t) {
    var events = t.events || [];
    // Deck slide 20: the task workspace names three controls -- [بدء التنفيذ]
    // to move to in-progress, [إضافة سؤال] to ask a clarification, and
    // [تسليم رابط] to record the delivery link. They sit above the state
    // dropdown, so the specialist's primary actions are one click, not a
    // two-step status edit. Each maps to an endpoint the server already owns.
    var quick = has("task.status_change")
      ? '<div class="sec-title">' + dual("المتابعة", "Follow-up") + "</div>" +
        '<div class="av-user-controls" data-stop="1">' +
        (t.status === "new"
          ? '<button class="btn-solid" data-act="task-start" data-id="' + t.id + '">' +
            dual("بدء التنفيذ", "Start work") + "</button>"
          : "") +
        '<button class="btn-outline" data-act="task-question" data-id="' + t.id + '">' +
        dual("إضافة سؤال", "Add question") + "</button>" +
        '<button class="btn-outline" data-act="task-deliver" data-id="' + t.id + '">' +
        dual("تسليم رابط", "Deliver link") + "</button></div>"
      : "";
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
        "</div>" + quick + update + transition) +
      panel("السجل", "History", hist);
  }

  function renderWeekly() {
    var host = byId("opsContent");
    var canRead = has("weekly_report.read_own") || has("weekly_report.read_all");
    return Promise.all([
      ensureCompanies(),
      canRead
        ? softGet("/api/v1/operations/weekly-reports")
        : Promise.resolve([]),
      canRead
        ? softGet("/api/v1/operations/weekly-reports/questions")
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
        ? '<div id="weeklyList"></div>'
        : noticeHtml("لا توجد تقارير أسبوعية.", "No weekly reports.");
      host.innerHTML = panel("التقرير الأسبوعي (بحد أقصى الأسئلة المعتمدة)", "Weekly report (at most the approved question set)", create + list) + weeklyTemplatePanel(questions);
      var weeklyHost = byId("weeklyList");
      if (weeklyHost) {
        // Slide 134 "التغذية / التقارير": the weekly report list carries the
        // deck's search / period / status filters and the apply / save / clear /
        // export cluster.
        var weeklySpec = [
          { key: "q", type: "search", ar: "الملخص", en: "Summary",
            fields: ["summary", "status"] },
          companyFilterOption(),
          { key: "period", ar: "الفترة", en: "Period",
            resolve: function (r) { return r.period_year ? r.period_year + "-" + String(r.period_week).padStart(2, "0") : ""; },
            options: distinctOptions(rows, function (r) {
              return r.period_year ? r.period_year + "-" + String(r.period_week).padStart(2, "0") : "";
            }) },
          { key: "status", ar: "الحالة", en: "Status", field: "status",
            options: [
              { value: "draft", ar: "مسودة", en: "Draft" },
              { value: "submitted", ar: "مُقدَّم", en: "Submitted" },
            ] },
        ];
        var weeklyRows = applyListFilters(scopeFilter(rows), "weekly", weeklySpec);
        weeklyRows.sort(function (a, b) {
          return (b.period_year - a.period_year) || (b.period_week - a.period_week) || byIdAsc(a, b);
        });
        renderPaged(weeklyHost, "weekly", weeklyRows, function (r) {
          return '<div class="av-row" style="cursor:default"><div class="grow"><div class="t">' +
            dual("أسبوع", "Week") + " " + dec(r.period_week) + " · " + dec(r.period_year) + "</div>" +
            '<div class="s">' + escapeHtml(companyNameById(r.company_id)) + " · " +
            (r.answers || []).length + " " + dual("إجابات", "answers") + "</div></div>" +
            statusBadgeFromMap(r.status, { draft: ["مسودة", "Draft", "warn"], submitted: ["مُقدَّم", "Submitted", "ok"] }) +
            "</div>";
        }, null, weeklySpec);
      }
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

  function campaignRow(c) {
    var canManage = has("campaign.manage");
    var results = canManage
      ? '<form class="av-form av-form-inline" data-stop="1" id="campRes' + c.id + '">' +
        field("الإنفاق", "Spend", numInput("crSpend" + c.id, c.spend)) +
        field("عدد العملاء المحتملين", "Leads", numInput("crLeads" + c.id, c.lead_count)) +
        field("التحويلات", "Conversions", numInput("crConv" + c.id, c.conversion_count)) +
        '<div class="av-form-actions"><button class="btn-outline" type="submit" data-act="camp-results" data-id="' + c.id + '">' +
        dual("حفظ النتائج", "Save results") + "</button></div></form>"
      : "";
    var linked = (c.linked_lead_count || 0);
    var linkedBar = '<div class="s" style="margin-top:6px">' +
      dual("عملاء مرتبطون", "Linked leads") + ": " + linked +
      ' · <button class="btn-outline" type="button" data-act="camp-leads" data-id="' + c.id + '">' +
      dual("عرض العملاء", "View leads") + "</button></div>" +
      '<div id="campLeads' + c.id + '"></div>';
    return '<div class="av-row" style="flex-direction:column;align-items:stretch;cursor:default"><div style="display:flex;align-items:center;gap:11px">' +
      '<div class="grow"><div class="t">' + escapeHtml(c.name) + "</div>" +
      '<div class="s">' + escapeHtml(companyNameById(c.company_id)) + " · " + escapeHtml(c.platform || "") +
      " · " + dual("الميزانية", "Budget") + " " + dec(c.budget) + "</div></div>" +
      statusBadgeFromMap(c.status, { planned: ["مخططة", "Planned", "warn"], active: ["نشطة", "Active", "ok"], completed: ["مكتملة", "Completed", "rev"], cancelled: ["ملغاة", "Cancelled", "miss"] }) +
      "</div>" + results + linkedBar + "</div>";
  }

  function renderCampaigns() {
    var host = byId("opsContent");
    return Promise.all([
      ensureCompanies(),
      softGet("/api/v1/operations/campaigns"),
    ]).then(function (res) {
      var rows = res[1] || [];
      STATE.campaigns = rows;
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
          dual("حملة جديدة", "New campaign") + "</button></div></form>"
        : "";
      var spec = campaignsFilterSpec();
      var list = applyListFilters(rows, "campaigns", spec);
      // Deck slide 134: العملاء/الحملات sort "موعد المتابعة تصاعديًا".
      list.sort(function (a, b) {
        return String(a.start_date || "9999").localeCompare(String(b.start_date || "9999")) || byIdAsc(a, b);
      });
      host.innerHTML = panel("الحملات (التنفيذ خارجي — النتائج تُسجَّل يدويًا)", "Campaigns (external execution — results recorded manually)", create + '<div id="campaignList"></div>');
      renderPaged(byId("campaignList"), "campaigns", list, campaignRow, null, spec);
    }).catch(function (err) { handleLoadError(err); host.innerHTML = errorHtml(errText(err)); });
  }

  function loadCampaignLeads(id) {
    var host = byId("campLeads" + id);
    if (!host) return;
    host.innerHTML = '<div class="s">' + dual("جارٍ التحميل…", "Loading…") + "</div>";
    return get("/api/v1/operations/campaigns/" + id + "/leads").then(function (leads) {
      leads = leads || [];
      host.innerHTML = leads.length
        ? '<div class="av-list">' + leads.map(function (l) {
            return '<div class="av-row"><div class="grow"><div class="t">' + escapeHtml(l.full_name) + "</div>" +
              '<div class="s">' + escapeHtml(l.reference) + " · " + escapeHtml(l.email || "") + "</div></div>" +
              statusBadgeFromMap(l.status, { new: ["جديد", "New", "warn"], contacted: ["تم التواصل", "Contacted", "ok"], qualified: ["مؤهل", "Qualified", "ok"], converted: ["محوَّل", "Converted", "rev"], closed: ["مغلق", "Closed", "miss"], lost: ["مفقود", "Lost", "miss"] }) +
              "</div>";
          }).join("") + "</div>"
        : noticeHtml("لا يوجد عملاء مرتبطون.", "No linked leads.");
    }).catch(function (err) { host.innerHTML = errorHtml(errText(err)); });
  }

  function onOpsAct(action, id, el) {
    if (action === "camp-leads") {
      return loadCampaignLeads(id);
    }
    if (action === "brief-submit") {
      return submitManagementBrief(id, el);
    }
    if (action === "brief-load") {
      var y = parseInt(valOf("mbYear"), 10);
      var mo = parseInt(valOf("mbMonth"), 10);
      if (!y || !mo) {
        toast(dual("حدد السنة والشهر أولاً.", "Choose a year and month first."), "warn");
        return;
      }
      return loadBriefDraft(y, mo);
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
    return softGet("/api/v1/operations/management-briefs")
      .then(function (rows) {
        rows = rows || [];
        var canAuthor = has("management_brief.submit");
        var now = new Date();
        var form = canAuthor
          ? '<form class="av-form" id="briefForm">' +
            '<div class="av-form-inline">' +
            field("السنة", "Year", numInput("mbYear", now.getFullYear(), "", true), null, null, true) +
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
          ? '<div id="briefList"></div>'
          : noticeHtml("لا توجد تقارير بعد.", "No briefs yet.");
        host.innerHTML = panel(
          "تقرير تطوير الأعمال (خمسة محاور)",
          "Business development brief (five axes)",
          form + list,
        );
        var briefHost = byId("briefList");
        if (briefHost) {
          // Slide 134 "التغذية / التقارير": search plus period / status filters
          // and the deck's apply / save / clear / export cluster; newest period
          // first.
          var briefSpec = [
            { key: "q", type: "search", ar: "الملخص التنفيذي", en: "Executive summary",
              fields: ["executive_summary", "status", "urgency"] },
            { key: "period", ar: "الفترة", en: "Period",
              resolve: function (r) { return r.period_year ? r.period_year + "-" + String(r.period_month).padStart(2, "0") : ""; },
              options: distinctOptions(rows, function (r) {
                return r.period_year ? r.period_year + "-" + String(r.period_month).padStart(2, "0") : "";
              }) },
            { key: "status", ar: "الحالة", en: "Status", field: "status",
              options: [
                { value: "draft", ar: "مسودة", en: "Draft" },
                { value: "submitted", ar: "مُرسل", en: "Submitted" },
              ] },
          ];
          var briefRows = applyListFilters(rows, "briefs", briefSpec);
          briefRows.sort(function (a, b) {
            return (b.period_year - a.period_year) || (b.period_month - a.period_month) || byIdAsc(a, b);
          });
          renderPaged(briefHost, "briefs", briefRows, briefRow, null, briefSpec);
        }
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
      softGet("/api/v1/operations/owner-decisions"),
    ]).then(function (res) {
      var rows = res[1] || [];
      var canManage = has("owner_decision.manage");
      var create = canManage
        ? '<form class="av-form av-form-inline" id="decForm">' +
          field("الرقم", "Number", textInput("dcNumber", "", "", true), null, null, true) +
          field("العنوان", "Title", textInput("dcTitle", "", "", true), null, null, true) +
          field("الشركة (اختياري)", "Company (optional)", selectInput("dcCompany", companySelectOptions(true), "")) +
          field("المُنفّذ (معرّف)", "Executor id", numInput("dcExecutor", "")) +
          field("الاستحقاق", "Due date", dateInput("dcDue", "")) +
          field("النص", "Body", textInput("dcBody", "")) +
          '<div class="av-form-actions"><button class="btn-solid" type="submit">' +
          dual("إصدار توجيه", "Issue directive") + "</button></div></form>"
        : "";
      var list = rows;
      STATE.decisions = rows;
      var spec = decisionsFilterSpec();
      list = applyListFilters(list, "decisions", spec);
      // Deck slide 135: الفرص/القرارات sort "آخر تحديث؛ القرار: تاريخ الرفع" --
      // newest first.
      list.sort(function (a, b) {
        return String(b.created_at || "").localeCompare(String(a.created_at || "")) || byIdAsc(a, b);
      });
      var decRow = function (d) {
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
            // S22: the person the directive names replies with an execution update.
            var reply = USER && d.executor_user_id === USER.id
              ? '<div class="av-user-controls" data-stop="1">' +
                textInput("dcReply" + d.id, "") +
                '<button class="btn-outline" data-act="dec-reply" data-id="' + d.id + '">' + dual("رد", "Reply") + "</button></div>"
              : "";
            // Deck slide 27: each decision opens on [فتح القرار] to the detail
            // screen (slide 28) before the owner acts. Slide 29 gives an
            // approved decision a [عرض سجل القرار] entry to its execution log.
            var logBtn = d.status === "done"
              ? '<button class="btn-outline" data-act="dec-log" data-id="' + d.id + '">' + dual("عرض سجل القرار", "Decision log") + "</button>"
              : "";
            return '<div class="av-row" style="flex-direction:column;align-items:stretch;cursor:default" data-decision="' + d.id + '"><div style="display:flex;align-items:center;gap:11px">' +
              '<div class="grow"><div class="t">' + escapeHtml(d.number + " · " + d.title) + "</div>" +
              '<div class="s">' + (d.company_id ? escapeHtml(companyNameById(d.company_id)) + " · " : "") +
              (d.executor_user_id ? escapeHtml(personName(d, "executor_name_ar", "executor_name_en") || ("#" + plainNum(d.executor_user_id))) + " · " : "") +
              dual("الاستحقاق", "Due") + " " + escapeHtml(dateStr(d.due_date)) + "</div></div>" +
              statusBadgeFromMap(d.status, { open: ["مفتوح", "Open", "warn"], in_progress: ["قيد التنفيذ", "In progress", "warn"], done: ["منجز", "Done", "ok"], cancelled: ["ملغى", "Cancelled", "miss"] }) +
              logBtn +
              '<button class="btn-outline" data-act="dec-open" data-id="' + d.id + '">' + dual("فتح القرار", "Open decision") + "</button>" +
              "</div>" + controls + reply + "</div>";
      };
      host.innerHTML = panel("قرارات المالك", "Owner decisions", create + '<div id="decList"></div>');
      renderPaged(byId("decList"), "decisions", list, decRow, function (h) {
        h.querySelectorAll('[data-act="dec-open"]').forEach(function (btn) {
          btn.addEventListener("click", function () {
            var did = parseInt(btn.getAttribute("data-id"), 10);
            var row = (STATE.decisions || []).filter(function (x) { return x.id === did; })[0];
            if (row) openDecision(row);
          });
        });
        h.querySelectorAll('[data-act="dec-log"]').forEach(function (btn) {
          btn.addEventListener("click", function () {
            var did = parseInt(btn.getAttribute("data-id"), 10);
            var row = (STATE.decisions || []).filter(function (x) { return x.id === did; })[0];
            // The detail panel carries the decision log (status history +
            // execution updates), which is what slide 29 asks the owner to open.
            if (row) openDecision(row);
          });
        });
        h.querySelectorAll('[data-act="dec-status"]').forEach(function (btn) {
          btn.addEventListener("click", function () {
            var did = btn.getAttribute("data-id");
            patch("/api/v1/operations/owner-decisions/" + did, { status: valOf("dcStatus" + did) })
              .then(function () { toast(dual("تم تحديث القرار.", "Decision updated."), "ok"); return renderDecisionsView(); })
              .catch(domainError);
          });
        });
        h.querySelectorAll('[data-act="dec-reply"]').forEach(function (btn) {
          btn.addEventListener("click", function () {
            var did = btn.getAttribute("data-id");
            var note = valOf("dcReply" + did);
            if (!note) { toast(dual("الرد مطلوب.", "A reply note is required."), "warn"); return; }
            post("/api/v1/operations/owner-decisions/" + did + "/respond", { note: note })
              .then(function () { toast(dual("تم إرسال الرد.", "Reply sent."), "ok"); return renderDecisionsView(); })
              .catch(domainError);
          });
        });
      }, spec);
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
    }).catch(function (err) { handleLoadError(err); host.innerHTML = errorHtml(errText(err)); });
  }

  // Deck slide 28 — تفاصيل القرار. A unified read of the request, its history
  // and the decision options, opened from [فتح القرار] on the list (slide 27).
  // It renders only fields the decision row already carries; the status change
  // and the executor reply are the same endpoints the list already calls, so no
  // new business rule or permission path is introduced. Acting on a decision
  // still requires owner_decision.manage; the executor reply still requires the
  // decision to name the signed-in user (S22).
  function openDecision(d) {
    var canManage = has("owner_decision.manage");
    var canReply = USER && d.executor_user_id === USER.id;
    var history = (d.history || []).slice().sort(function (a, b) {
      return String(a.created_at || "").localeCompare(String(b.created_at || ""));
    });
    var statusMap = {
      open: ["مفتوح", "Open", "warn"],
      in_progress: ["قيد التنفيذ", "In progress", "warn"],
      done: ["منجز", "Done", "ok"],
      cancelled: ["ملغى", "Cancelled", "miss"],
    };
    var historyBlock = history.length
      ? '<div class="sec-title">' + dual("سجل العمل", "Work log") + "</div>" +
        '<div class="kv">' +
        history
          .map(function (h) {
            var who = h.actor_id ? "#" + plainNum(h.actor_id) : "—";
            var st = h.status
              ? escapeHtml(STATE.lang === "ar" ? statusMap[h.status][0] : statusMap[h.status][1])
              : "—";
            return kv(fmtDateTime(h.created_at), st + " · " + escapeHtml(h.note || who));
          })
          .join("") +
        "</div>"
      : "";

    var actions = "";
    if (canManage) {
      actions =
        '<div class="sec-title">' + dual("خيارات القرار", "Decision options") + "</div>" +
        // Deck slide 28 names the four outcomes verbatim: [اعتماد] [رفض]
        // [طلب معلومات] [تأجيل]. Each maps to a status the model already
        // carries; the three that need an explanation are refused without one.
        '<div class="av-user-controls" data-stop="1">' +
        '<button class="btn-solid gold" data-act="dec-detail-outcome" data-id="' + d.id + '" data-outcome="done">' +
        dual("اعتماد القرار", "Approve decision") + "</button>" +
        '<button class="btn-outline danger" data-act="dec-detail-outcome" data-id="' + d.id + '" data-outcome="cancelled">' +
        dual("رفض", "Reject") + "</button>" +
        '<button class="btn-outline" data-act="dec-detail-outcome" data-id="' + d.id + '" data-outcome="in_progress">' +
        dual("طلب معلومات", "Request info") + "</button>" +
        '<button class="btn-outline" data-act="dec-detail-outcome" data-id="' + d.id + '" data-outcome="open">' +
        dual("تأجيل", "Defer") + "</button></div>" +
        '<div class="av-field" style="margin-top:10px">' +
        '<textarea class="av-textarea" id="decOpenNote"' +
        phAttr("ph.comment") + "></textarea>" +
        '<button class="btn-outline" data-act="dec-detail-note" data-id="' + d.id + '" style="margin-top:8px">' +
        dual("إضافة ملاحظة للمتابعة", "Add follow-up note") + "</button></div>";
    } else if (canReply) {
      actions =
        '<div class="sec-title">' + dual("رد المنفّذ", "Executor reply") + "</div>" +
        '<div class="av-field">' +
        '<textarea class="av-textarea" id="decOpenNote"' +
        phAttr("ph.comment") + "></textarea>" +
        '<button class="btn-solid" data-act="dec-detail-reply" data-id="' + d.id + '" style="margin-top:8px">' +
        dual("إرسال تحديث التنفيذ", "Send execution update") + "</button></div>";
    }

    openModal({
      title: dual("تفاصيل القرار", "Decision detail"),
      wide: true,
      body:
        '<div class="kv">' +
        kv(dual("الرقم", "Number"), escapeHtml(d.number)) +
        kv(dual("العنوان", "Title"), escapeHtml(d.title)) +
        kv(dual("الجهة", "Entity"), d.company_id ? escapeHtml(companyNameById(d.company_id)) : dual("القابضة", "Holding")) +
        kv(dual("الحالة", "Status"), statusBadgeFromMap(d.status, statusMap)) +
        kv(dual("المسؤول", "Executor"),
           escapeHtml(personName(d, "executor_name_ar", "executor_name_en") || (d.executor_user_id ? "#" + plainNum(d.executor_user_id) : "—"))) +
        kv(dual("الاستحقاق", "Due"), escapeHtml(dateStr(d.due_date))) +
        (d.follow_up_note ? kv(dual("ملاحظة المتابعة", "Follow-up note"), escapeHtml(d.follow_up_note)) : "") +
        "</div>" +
        (d.body ? '<div class="sec-title">' + dual("التفاصيل", "Details") + '</div><p class="note-block">' + escapeHtml(d.body) + "</p>" : "") +
        historyBlock +
        actions,
      onMount: function (root) {
        // Deck slide 28: the four named outcomes. Approve closes the decision;
        // reject, request-info and defer all need the reason typed below.
        var outcomeNote = { cancelled: "سبب الرفض مطلوب.", in_progress: "بيّن المعلومات المطلوبة.", open: "سبب التأجيل مطلوب." };
        var outcomeNoteEn = { cancelled: "A rejection reason is required.", in_progress: "State the information needed.", open: "A deferral reason is required." };
        root.querySelectorAll('[data-act="dec-detail-outcome"]').forEach(function (btn) {
          btn.addEventListener("click", function () {
            var outcome = btn.getAttribute("data-outcome");
            var note = valOf("decOpenNote");
            if (outcomeNote[outcome] && !note) {
              toast(dual(outcomeNote[outcome], outcomeNoteEn[outcome]), "warn");
              return;
            }
            var payload = { status: outcome };
            if (note) payload.follow_up_note = note;
            busy(btn, true);
            patch("/api/v1/operations/owner-decisions/" + d.id, payload)
              .then(function () {
                closeModal();
                toast(dual("تم تحديث القرار.", "Decision updated."), "ok");
                return renderDecisionsView();
              })
              .catch(function (err) { domainError(err); busy(btn, false); });
          });
        });
        var noteBtn = root.querySelector('[data-act="dec-detail-note"]');
        if (noteBtn) {
          noteBtn.addEventListener("click", function () {
            var note = valOf("decOpenNote");
            if (!note) { toast(dual("الملاحظة مطلوبة.", "A note is required."), "warn"); return; }
            busy(noteBtn, true);
            patch("/api/v1/operations/owner-decisions/" + d.id, { follow_up_note: note })
              .then(function () {
                closeModal();
                toast(dual("تم حفظ الملاحظة.", "Note saved."), "ok");
                return renderDecisionsView();
              })
              .catch(function (err) { domainError(err); busy(noteBtn, false); });
          });
        }
        var replyBtn = root.querySelector('[data-act="dec-detail-reply"]');
        if (replyBtn) {
          replyBtn.addEventListener("click", function () {
            var note = valOf("decOpenNote");
            if (!note) { toast(dual("الرد مطلوب.", "A reply note is required."), "warn"); return; }
            busy(replyBtn, true);
            post("/api/v1/operations/owner-decisions/" + d.id + "/respond", { note: note })
              .then(function () {
                closeModal();
                toast(dual("تم إرسال الرد.", "Reply sent."), "ok");
                return renderDecisionsView();
              })
              .catch(function (err) { domainError(err); busy(replyBtn, false); });
          });
        }
      },
    });
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

  // ---- Feedback (التغذية الراجعة) -------------------------------------
  //
  // The brief's "Feedback & Reporting" section. It aggregates the feedback
  // channels the platform already stores -- weekly reports, management briefs
  // and monthly reports -- into one review queue with classification and
  // follow-up. It is deliberately read-first: every row opens the record that
  // owns it, and all writes still go through the existing endpoints and their
  // permissions. No new table and no new business rule.
  var FB_SOURCES = {
    weekly_report: {
      ar: "تقرير أسبوعي",
      en: "Weekly report",
      perm: ["weekly_report.read_own", "weekly_report.read_all"],
      view: "operations",
    },
    management_brief: {
      ar: "تقرير إداري",
      en: "Management brief",
      perm: ["management_brief.read"],
      view: "operations",
    },
    monthly_report: {
      ar: "تقرير شهري",
      en: "Monthly report",
      perm: ["monthly_report.read_own", "monthly_report.read_all"],
      view: "reports",
    },
  };

  function fbAllowed(source) {
    return (FB_SOURCES[source].perm || []).some(has);
  }

  function fbStatusClass(status) {
    var s = String(status || "").toLowerCase();
    if (s.indexOf("approv") >= 0 || s === "done" || s === "complete") return "ok";
    if (s.indexOf("reject") >= 0 || s.indexOf("cancel") >= 0 || s.indexOf("return") >= 0) return "miss";
    if (s.indexOf("review") >= 0 || s.indexOf("progress") >= 0 || s.indexOf("submit") >= 0) return "warn";
    return "";
  }

  function fbStatusLabel(status) {
    var s = String(status || "");
    if (!s) return dual("—", "—");
    return escapeHtml(s.replace(/_/g, " "));
  }

  function renderFeedbackView() {
    var host = byId("feedbackList");
    if (!host) return Promise.resolve();
    host.innerHTML = loadingHtml();
    bindFeedbackControls();

    var canMonthly =
      has("monthly_report.read_own") || has("monthly_report.read_all");
    return Promise.all([
      ensureCompanies(),
      fbAllowed("weekly_report")
        ? softGet("/api/v1/operations/weekly-reports")
        : Promise.resolve([]),
      fbAllowed("management_brief")
        ? softGet("/api/v1/operations/management-briefs")
        : Promise.resolve([]),
      canMonthly
        ? softGet("/api/v1/monthly-reports")
        : Promise.resolve([]),
    ]).then(function (res) {
      var rows = [];
      (res[1] || []).forEach(function (r) {
        rows.push(fbRow("weekly_report", r, {
          title: r.summary || opt("تقرير أسبوعي", "Weekly report"),
          sub: opt("الأسبوع", "Week") + " " + periodPart(r.period_week) +
               " · " + periodPart(r.period_year),
          status: r.status,
          date: r.created_at,
          id: r.id,
        }));
      });
      (res[2] || []).forEach(function (r) {
        rows.push(fbRow("management_brief", r, {
          title: r.executive_summary || opt("تقرير إداري", "Management brief"),
          sub: opt("الفترة", "Period") + " " +
               periodPart(r.period_month) + "/" + periodPart(r.period_year),
          status: r.status,
          date: r.created_at,
          id: r.id,
        }));
      });
      (res[3] || []).forEach(function (r) {
        rows.push(fbRow("monthly_report", r, {
          title: (STATE.lang === "ar" ? r.company_name_ar : r.company_name_en) ||
                 opt("تقرير شهري", "Monthly report"),
          sub: opt("الفترة", "Period") + " " +
               periodPart(r.period_month) + "/" + periodPart(r.period_year),
          status: r.status,
          date: r.updated_at || r.created_at,
          id: r.id,
        }));
      });

      // Newest first; rows with no date sort last.
      rows.sort(function (a, b) {
        return String(b.sort_date || "").localeCompare(String(a.sort_date || ""));
      });

      renderFeedbackSummary(rows);
      var filter = (byId("fbSourceFilter") || {}).value || "";
      var shown = filter
        ? rows.filter(function (r) { return r.source === filter; })
        : rows;
      var spec = feedbackFilterSpec();
      shown = applyListFilters(shown, "feedback", spec);
      host.innerHTML = "";
      renderPaged(host, "feedback", shown, fbRowHtml, function (h) {
        h.querySelectorAll("[data-fb-source]").forEach(function (el) {
          el.addEventListener("click", function () {
            var src = el.getAttribute("data-fb-source");
            navTo((FB_SOURCES[src] || {}).view || "operations");
          });
        });
      }, spec);
    });
  }

  function fbRow(source, raw, meta) {
    return {
      source: source,
      raw: raw,
      title: meta.title,
      sub: meta.sub,
      status: meta.status,
      id: meta.id,
      sort_date: meta.date,
    };
  }

  function fbRowHtml(r) {
    var src = FB_SOURCES[r.source];
    var cls = fbStatusClass(r.status);
    var badge = src
      ? '<span class="attn-badge' + (cls ? " " + cls : "") + '">' +
        escapeHtml(STATE.lang === "ar" ? src.ar : src.en) + "</span>"
      : "";
    return (
      '<div class="av-row" data-fb-source="' + escapeHtml(r.source) + '" style="align-items:flex-start">' +
      '<div class="grow">' +
      '<div class="t">' + escapeHtml(r.title || "") + "</div>" +
      '<div class="s">' + escapeHtml(r.sub || "") + " · " + fbStatusLabel(r.status) + "</div>" +
      "</div>" + badge + "</div>"
    );
  }

  function renderFeedbackSummary(rows) {
    var host = byId("fbSummary");
    if (!host) return;
    var bySource = {};
    rows.forEach(function (r) {
      bySource[r.source] = (bySource[r.source] || 0) + 1;
    });
    var openish = rows.filter(function (r) {
      var s = String(r.status || "").toLowerCase();
      return s.indexOf("approv") < 0 && s !== "done" && s !== "complete";
    }).length;
    var cards = [
      { ar: "إجمالي المدخلات", en: "Total entries", v: rows.length },
      { ar: "قيد المعالجة", en: "Open", v: openish },
      { ar: "تقارير أسبوعية", en: "Weekly reports", v: bySource.weekly_report || 0 },
      { ar: "تقارير إدارية", en: "Management briefs", v: bySource.management_brief || 0 },
      { ar: "تقارير شهرية", en: "Monthly reports", v: bySource.monthly_report || 0 },
    ];
    host.innerHTML = cards.map(function (c) {
      return (
        '<div class="av-panel"><h3>' + dual(c.ar, c.en) + "</h3>" +
        '<div class="kpi-val num" style="font-size:22px">' + plainNum(c.v) + "</div></div>"
      );
    }).join("");
  }

  function bindFeedbackControls() {
    var refresh = byId("fbRefresh");
    if (refresh && !refresh.getAttribute("data-bound")) {
      refresh.setAttribute("data-bound", "1");
      refresh.addEventListener("click", function () {
        renderFeedbackView();
      });
    }
    var filter = byId("fbSourceFilter");
    if (filter && !filter.getAttribute("data-bound")) {
      filter.setAttribute("data-bound", "1");
      filter.addEventListener("change", function () {
        renderFeedbackView();
      });
    }
  }

  function renderProjectsView() {
    var host = byId("projContent");
    if (!host) return Promise.resolve();
    host.innerHTML = loadingHtml();
    return Promise.all([
      ensureCompanies(),
      softGet("/api/v1/operations/projects"),
    ]).then(function (res) {
      var rows = res[1] || [];
      var canManage = has("project.manage");
      var create = canManage
        ? '<form class="av-form av-form-inline" id="projectForm">' +
          field("النوع", "Type", selectInput("prType", [
            { value: "opportunity", label: opt("فرصة", "Opportunity") },
            { value: "project", label: opt("مشروع", "Project") },
          ], "opportunity")) +
          field("الاسم", "Name", textInput("prName", "", "", true), null, null, true) +
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
          dual("إضافة فرصة", "Add opportunity") + "</button></div></form>"
        : "";
      STATE.projects = rows;
      var spec = projectsFilterSpec();
      var filtered = applyListFilters(scopeFilter(rows), "projects", spec);
      filtered.sort(function (a, b) {
        return String(b.created_at || "").localeCompare(String(a.created_at || "")) || byIdAsc(a, b);
      });
      var projectRow = function (r) {
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
        return '<div class="av-row" data-proj="' + escAttr(JSON.stringify(r)) + '" style="flex-direction:column;align-items:stretch;cursor:pointer"><div style="display:flex;align-items:center;gap:11px">' +
          '<div class="grow"><div class="t">' + escapeHtml(r.name) + "</div>" +
          '<div class="s">' + projectTypeBadge(r.record_type) + " " +
          (r.stage ? statusBadgeFromMap(r.stage, PROJECT_STAGE_LABEL) + " " : "") +
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
      };
      host.innerHTML = panel("المشاريع والفرص", "Projects & opportunities", create + '<div id="projList"></div>');
      renderPaged(byId("projList"), "projects", filtered, projectRow, function (h) {
        bindRowClicks(h, "proj", function (r) { openProjectStudy(r); });
        h.querySelectorAll('[data-act="proj-status"]').forEach(function (btn) {
          btn.addEventListener("click", function () {
            var rid = btn.getAttribute("data-id");
            patch("/api/v1/operations/projects/" + rid, { status: valOf("prStatus" + rid) })
              .then(function () { toast(dual("تم تحديث السجل.", "Record updated."), "ok"); return renderProjectsView(); })
              .catch(domainError);
          });
        });
      }, spec);
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
    }).catch(function (err) { handleLoadError(err); host.innerHTML = errorHtml(errText(err)); });
  }

  // Deck slides 25-26: the opportunity pipeline and its study. The four stages
  // are a label the BD manager sets (spec §7: no automatic transition); the
  // study fields are free text -- the deck's "no feasibility engine" rule means
  // nothing here is computed. [حفظ الدراسة] persists them and
  // [رفع للمالك عند الحاجة] opens an owner decision topic linked to the record.
  var PROJECT_STAGE_LABEL = {
    new: ["جديدة", "New", "rev"],
    initial_review: ["تقييم أولي", "Initial review", "warn"],
    feasibility: ["دراسة جدوى", "Feasibility study", "gold"],
    decision: ["قرار / تنفيذ", "Decision / execution", "ok"],
  };

  function openProjectStudy(r) {
    var stageOpts = [
      { value: "", label: opt("—", "—") },
      { value: "new", label: opt("جديدة", "New") },
      { value: "initial_review", label: opt("تقييم أولي", "Initial review") },
      { value: "feasibility", label: opt("دراسة جدوى", "Feasibility study") },
      { value: "decision", label: opt("قرار / تنفيذ / إغلاق", "Decision / execution / close") },
    ];
    var studyField = function (id, ar, en, value) {
      return '<div class="av-field"><label>' + dual(ar, en) + "</label>" +
        textArea(id, value || "", "") + "</div>";
    };
    var canManage = has("project.manage");
    var body =
      '<div class="kv">' +
      kv(dual("النوع", "Type"), projectTypeBadge(r.record_type)) +
      kv(dual("الشركة", "Company"), escapeHtml(r.company_id ? companyNameById(r.company_id) : "—")) +
      kv(dual("الحالة", "Status"), statusBadgeFromMap(r.status, PROJECT_STATUS_LABEL)) +
      (r.owner_decision_id
        ? kv(dual("موضوع القرار", "Decision topic"), "#" + plainNum(r.owner_decision_id))
        : "") +
      "</div>" +
      (r.objective ? '<div class="sec-title">' + dual("الهدف", "Objective") + '</div><p>' + escapeHtml(r.objective) + "</p>" : "") +
      (canManage
        ? '<div class="sec-title">' + dual("تقييم الفرصة", "Opportunity study") + "</div>" +
          field("مرحلة الفرصة", "Opportunity stage", selectInput("psStage", stageOpts, r.stage || "")) +
          studyField("psMarket", "السوق والعملاء", "Market & customers", r.market_customers) +
          studyField("psSource", "مصدر المعلومات", "Information source", r.information_source) +
          studyField("psRevenue", "الإيراد المتوقع", "Expected revenue", r.expected_revenue) +
          studyField("psRisks", "المخاطر الرئيسية", "Key risks", r.key_risks) +
          studyField("psAlt", "البدائل", "Alternatives", r.alternatives) +
          studyField("psRec", "التوصية", "Recommendation", r.recommendation) +
          studyField("psSources", "مصادر الدراسة", "Study sources", r.study_sources) +
          '<p class="note-block">' + dual(
            "الحقائق والافتراضات والمخاطر والتوصية تُعرض قبل رفع القرار؛ لا يوجد محرك جدوى آلي.",
            "Facts, assumptions, risks and a recommendation are shown before the decision is raised; there is no automatic feasibility engine.") + "</p>"
        : "");
    openModal({
      title: dual("تفاصيل وتقييم الفرصة", "Opportunity details & study"),
      wide: true,
      body: body,
      footer: canManage
        ? '<button class="btn-outline" id="psCancel">' + dual("إغلاق", "Close") + "</button>" +
          '<button class="btn-outline" id="psRaise">' + dual("رفع للمالك عند الحاجة", "Raise to owner") + "</button>" +
          '<button class="btn-solid" id="psSave">' + dual("حفظ الدراسة", "Save study") + "</button>"
        : '<button class="btn-outline" id="psCancel">' + dual("إغلاق", "Close") + "</button>",
      onMount: function () {
        byId("psCancel").addEventListener("click", closeModal);
        var save = byId("psSave");
        if (save) {
          save.addEventListener("click", function () {
            var btn = this;
            busy(btn, true);
            patch("/api/v1/operations/projects/" + r.id, {
              stage: valOf("psStage") || null,
              market_customers: valOf("psMarket") || null,
              information_source: valOf("psSource") || null,
              expected_revenue: valOf("psRevenue") || null,
              key_risks: valOf("psRisks") || null,
              alternatives: valOf("psAlt") || null,
              recommendation: valOf("psRec") || null,
              study_sources: valOf("psSources") || null,
            }).then(function () {
              toast(dual("تم حفظ الدراسة.", "Study saved."), "ok");
              closeModal();
              renderProjectsView();
            }).catch(function (err) { domainError(err); busy(btn, false); });
          });
        }
        var raise = byId("psRaise");
        if (raise) {
          raise.addEventListener("click", function () {
            var btn = this;
            busy(btn, true);
            post("/api/v1/operations/projects/" + r.id + "/raise-to-owner", {})
              .then(function () {
                toast(dual("رُفع الموضوع للمالك.", "Topic raised to the owner."), "ok");
                closeModal();
                renderProjectsView();
              }).catch(function (err) { domainError(err); busy(btn, false); });
          });
        }
      },
    });
  }

  // ======================================================================
  // S04/S26/S27/S28 -- Holding accounting (D01/D07/D08)
  // ======================================================================

  // ---- Advisory (prototype tab "advisory") -------------------------------
  // Advisor sessions and monthly advisor reports, exactly the two records the
  // prototype's advisory tab lists. Both endpoints already scope rows by the
  // caller, so the view adds no data access.
  function renderAdvisoryView() {
    var host = byId("advContent");
    if (!host) return Promise.resolve();
    if (!STATE.advBound) {
      STATE.advBound = true;
      bindSimpleTabs("data-adv-tab", "advTab", renderAdvisoryView);
    }
    host.innerHTML = loadingHtml();
    return Promise.all([
      softGet("/api/v1/operations/advisory-sessions"),
      softGet("/api/v1/operations/advisor-reports"),
    ]).then(function (res) {
      var sessions = res[0] || [];
      var reports = res[1] || [];
      var tab = STATE.advTab || "sessions";
      if (tab === "reports") {
        host.innerHTML = panel("تقارير المستشار", "Advisor reports",
          reports.length
            ? '<div class="av-list">' + reports.map(function (r) {
                return '<div class="av-row" style="cursor:default"><div class="grow">' +
                  '<div class="t">' + escapeHtml(r.title || dual("تقرير المستشار", "Advisor report")) + '</div>' +
                  '<div class="s">' + escapeHtml((r.period_year || "") + "-" + String(r.period_month || "").padStart(2, "0") + " · " + (r.status || "")) + '</div>' +
                  '</div></div>';
              }).join("") + "</div>"
            : noticeHtml("لا توجد تقارير بعد.", "No reports yet."));
      } else {
        host.innerHTML = panel("جلسات المستشار", "Advisor sessions",
          sessions.length
            ? '<div class="av-list">' + sessions.map(function (s) {
                return '<div class="av-row" style="cursor:default"><div class="grow">' +
                  '<div class="t">' + escapeHtml(s.specialty || s.advisor_name || dual("جلسة استشارية", "Advisory session")) + '</div>' +
                  '<div class="s">' + escapeHtml((s.scheduled_at || s.date || "") + " · " + (s.status || "")) + '</div>' +
                  '</div></div>';
              }).join("") + "</div>"
            : noticeHtml("لا توجد جلسات مسجّلة.", "No sessions recorded."));
      }
    }).catch(function (err) { handleLoadError(err); host.innerHTML = errorHtml(errText(err)); });
  }

  // ---- HR movements (prototype tab "hr") --------------------------------
  // HR movements (leave, custody, warning, …) across the employees the caller
  // may see, with the approve/reject action the prototype's HR tab offers.
  function renderHrView() {
    var host = byId("hrContent");
    if (!host) return Promise.resolve();
    if (!STATE.hrBound) {
      STATE.hrBound = true;
      bindSimpleTabs("data-hr-tab", "hrTab", renderHrView);
    }
    host.innerHTML = loadingHtml();
    return get("/api/v1/employees").then(function (emps) {
      emps = emps || [];
      if ((STATE.hrTab || "movements") === "employees") {
        STATE.hr = STATE.hr || {};
        STATE.hr.employees = emps;
        host.innerHTML = panel("الموظفون", "Employees",
          emps.length
            ? '<div id="hrEmpList"></div>'
            : noticeHtml("لا يوجد موظفون في نطاقك.", "No employees in your scope."));
        if (emps.length) {
          renderPaged(byId("hrEmpList"), "hrEmployees", emps, employeeRow, function (h) {
            bindRowClicks(h, "emp", openEmployee);
          }, employeesFilterSpec());
        }
        return;
      }
      if (!emps.length) {
        host.innerHTML = panel("حركات الموظفين", "Employee movements",
          noticeHtml("لا يوجد موظفون في نطاقك.", "No employees in your scope."));
        return;
      }
      return Promise.all(emps.slice(0, 50).map(function (e) {
        return softGet("/api/v1/employees/" + e.id + "/movements").then(function (rows) {
          return (rows || []).map(function (m) { m._emp = e; return m; });
        });
      })).then(function (lists) {
        var all = [];
        lists.forEach(function (l) { all = all.concat(l); });
        all.sort(function (a, b) { return (b.id || 0) - (a.id || 0); });
        host.innerHTML = panel("حركات الموظفين", "Employee movements",
          all.length
            ? '<div class="av-list">' + all.map(function (m) {
                var emp = m._emp;
                var canDecide = has("employee.movement.approve") && (m.status === "pending" || m.status === "submitted");
                return '<div class="av-row" style="cursor:default"><div class="grow">' +
                  '<div class="t">' + escapeHtml((emp ? (STATE.lang === "ar" ? emp.full_name_ar : emp.full_name_en || emp.full_name_ar) : "") + " · " + (m.movement_type || "")) + '</div>' +
                  '<div class="s">' + escapeHtml((m.start_date || m.effective_date || "") + " · " + (m.status || "")) + '</div>' +
                  '</div>' +
                  (canDecide
                    ? '<button class="chip" data-hr-approve="' + m.id + '">' + dual("اعتماد", "Approve") + '</button>' +
                      '<button class="chip" data-hr-reject="' + m.id + '">' + dual("رفض", "Reject") + '</button>'
                    : "") +
                  '</div>';
              }).join("") + "</div>"
            : noticeHtml("لا توجد حركات.", "No movements."));
        host.querySelectorAll("[data-hr-approve],[data-hr-reject]").forEach(function (btn) {
          btn.addEventListener("click", function () {
            var approve = btn.hasAttribute("data-hr-approve");
            var id = parseInt(btn.getAttribute(approve ? "data-hr-approve" : "data-hr-reject"), 10);
            post("/api/v1/employees/movements/" + id + "/decision", { approve: approve, note: null })
              .then(function () { toast(dual("تم تحديث الحركة.", "Movement updated."), "ok"); return renderHrView(); })
              .catch(function (err) { domainError(err); });
          });
        });
      });
    }).catch(function (err) { handleLoadError(err); host.innerHTML = errorHtml(errText(err)); });
  }

  // ---- Holding assets (prototype tab "assets") --------------------------
  // The holding's own assets (gold, property, …), totalled per currency --
  // the prototype never converts between currencies.
  function renderAssetsView() {
    var host = byId("assetsContent");
    if (!host) return Promise.resolve();
    host.innerHTML = loadingHtml();
    return get("/api/v1/accounting/assets").then(function (rows) {
      rows = rows || [];
      var totals = {};
      rows.forEach(function (a) {
        var c = a.currency || "BHD";
        var v = Number(a.current_value || a.purchase_value || 0);
        totals[c] = (totals[c] || 0) + v;
      });
      var totalHtml = Object.keys(totals).length
        ? '<div class="av-list">' + Object.keys(totals).map(function (c) {
            return '<div class="av-row" style="cursor:default"><div class="grow"><div class="t">' +
              dec(totals[c]) + " " + escapeHtml(c) + '</div><div class="s">' +
              dual("إجمالي قيمة الأصول", "Total asset value") + '</div></div></div>';
          }).join("") + "</div>"
        : noticeHtml("لا توجد أصول مسجّلة.", "No assets recorded.");
      host.innerHTML =
        panel("قيمة أصول القابضة", "Holding asset value", totalHtml) +
        panel("سجل الأصول", "Asset register",
          rows.length
            ? '<div class="av-list">' + rows.map(function (a) {
                return '<div class="av-row" style="cursor:default"><div class="grow">' +
                  '<div class="t">' + escapeHtml(a.name || a.type || "") + '</div>' +
                  '<div class="s">' + escapeHtml((a.type || "") + " · " + dec(a.current_value || a.purchase_value) + " " + (a.currency || "")) + '</div>' +
                  '</div></div>';
              }).join("") + "</div>"
            : noticeHtml("لا توجد أصول مسجّلة.", "No assets recorded."));
    }).catch(function (err) { handleLoadError(err); host.innerHTML = errorHtml(errText(err)); });
  }

  // ---- Website management (prototype tab "site") ------------------------
  // The platform side of the site: submitted listings to review/publish and the
  // CMS overview. Submitter contact details are shown here only (the site never
  // publishes them), which is why this view needs website/lead permissions.
  function renderSiteView() {
    var host = byId("siteContent");
    if (!host) return Promise.resolve();
    if (!STATE.siteBound) {
      STATE.siteBound = true;
      bindSimpleTabs("data-site-tab", "siteTab", renderSiteView);
    }
    host.innerHTML = loadingHtml();
    var canLeads = has("website_lead.read");
    var canCms = has("website.content.read");
    var tab = STATE.siteTab || "listings";
    return Promise.all([
      canLeads ? softGet("/api/v1/leads/opportunities") : Promise.resolve(null),
      canCms ? softGet("/api/v1/website/overview") : Promise.resolve(null),
      canCms && tab === "content" ? softGet("/api/v1/website/pages") : Promise.resolve(null),
    ]).then(function (res) {
      var opps = res[0] || [];
      var cms = res[1];
      var pages = res[2] || [];
      var html = "";
      if (tab === "content") {
        if (!canCms) {
          host.innerHTML = noticeHtml("ليست لديك صلاحية عرض محتوى الموقع.", "You cannot view website content.");
          return;
        }
        html += siteContentPanel(cms, pages);
      } else {
        if (canLeads) {
          html += panel("العروض المقدَّمة من الموقع", "Listings submitted from the site",
            opps.length
              ? '<div class="av-list">' + opps.map(function (o) {
                  return '<div class="av-row" style="cursor:default"><div class="grow">' +
                    '<div class="t">' + escapeHtml(o.description ? o.description.slice(0, 80) : dual("عرض", "Listing")) + '</div>' +
                    '<div class="s">' + escapeHtml((o.sector || "") + " · " + (o.market || "") + " · " + (o.currency || "") + " " + dec(o.value_max)) + '</div>' +
                    '</div></div>';
                }).join("") + "</div>"
              : noticeHtml("لا توجد عروض مقدَّمة.", "No listings submitted."));
        }
        if (canCms && cms) {
          html += panel("نظرة عامة على الموقع", "Website overview",
            '<div class="av-list">' +
            '<div class="av-row" style="cursor:default"><div class="grow"><div class="t">' + dec(cms.published_pages) + " / " + dec(cms.pages) + '</div><div class="s">' + dual("الصفحات المنشورة", "Published pages") + '</div></div></div>' +
            '<div class="av-row" style="cursor:default"><div class="grow"><div class="t">' + dec(cms.visible_companies) + " / " + dec(cms.companies) + '</div><div class="s">' + dual("الشركات الظاهرة", "Visible companies") + '</div></div></div>' +
            '<div class="av-row" style="cursor:default"><div class="grow"><div class="t">' + dec(cms.active_slides) + " / " + dec(cms.slides) + '</div><div class="s">' + dual("الشرائح النشطة", "Active slides") + '</div></div></div>' +
            '</div>');
        }
      }
      host.innerHTML = html || noticeHtml("ليست لديك صلاحية عرض بيانات الموقع.", "You cannot view website data.");
      if (tab === "content") bindSiteContent(host, pages);
    }).catch(function (err) { handleLoadError(err); host.innerHTML = errorHtml(errText(err)); });
  }

  // Website content (CMS) tab: the page register with a publish/unpublish
  // control per page. Editing bodies/settings stays in Group Administration →
  // Website; this tab is the day-to-day content overview the prototype shows.
  function siteContentPanel(cms, pages) {
    var canPublish = has("website.content.publish");
    var list = pages.length
      ? '<div class="av-list">' + pages.map(function (p) {
          var published = (p.status || "") === "published";
          return '<div class="av-row" style="cursor:default"><div class="grow">' +
            '<div class="t">' + escapeHtml(p.title_ar || p.title_en || p.route_key || "") + '</div>' +
            '<div class="s">' + escapeHtml((p.route_key || "") + " · " + (p.status || "")) + '</div>' +
            '</div>' +
            (canPublish
              ? '<button class="chip" data-site-publish="' + p.id + '" data-published="' + (published ? "1" : "0") + '">' +
                dual(published ? "إلغاء النشر" : "نشر", published ? "Unpublish" : "Publish") + '</button>'
              : "") +
            '</div>';
        }).join("") + "</div>"
      : noticeHtml("لا توجد صفحات.", "No pages.");
    var overview = cms
      ? panel("نظرة عامة على الموقع", "Website overview",
          '<div class="av-list">' +
          '<div class="av-row" style="cursor:default"><div class="grow"><div class="t">' + dec(cms.published_pages) + " / " + dec(cms.pages) + '</div><div class="s">' + dual("الصفحات المنشورة", "Published pages") + '</div></div></div>' +
          '<div class="av-row" style="cursor:default"><div class="grow"><div class="t">' + dec(cms.active_slides) + " / " + dec(cms.slides) + '</div><div class="s">' + dual("الشرائح النشطة", "Active slides") + '</div></div></div>' +
          '</div>')
      : "";
    return overview + panel("صفحات الموقع", "Website pages", list);
  }

  function bindSiteContent(host, pages) {
    host.querySelectorAll("[data-site-publish]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var id = parseInt(btn.getAttribute("data-site-publish"), 10);
        var published = btn.getAttribute("data-published") === "1";
        var verb = published ? "unpublish" : "publish";
        post("/api/v1/website/pages/" + id + "/" + verb, {})
          .then(function () {
            toast(dual(published ? "تم إلغاء نشر الصفحة." : "تم نشر الصفحة.", published ? "Page unpublished." : "Page published."), "ok");
            return renderSiteView();
          })
          .catch(function (err) { domainError(err); });
      });
    });
  }

  // ---- Assistant learning (prototype tab "aiReview") --------------------
  // Owner-only review of what the assistant proposes to learn plus the approved
  // knowledge base. Approval is what moves a proposal into the KB, exactly the
  // prototype's aiReview control.
  function renderAiReviewView() {
    var host = byId("aiRevContent");
    if (!host) return Promise.resolve();
    if (!STATE.aiRevBound) {
      STATE.aiRevBound = true;
      bindSimpleTabs("data-airev-tab", "aiRevTab", renderAiReviewView);
    }
    host.innerHTML = loadingHtml();
    var canApprove = has("ai.knowledge.approve");
    var canManage = has("ai.knowledge.manage");
    // Listing proposals is a manage-only endpoint; a read-only viewer (a
    // company-scoped role that holds ``ai.knowledge.read`` but not ``manage``)
    // would get a 403. They open on the knowledge base and the proposals tab is
    // not offered, so the view never fires a request it cannot make.
    var tab = canManage ? (STATE.aiRevTab || "proposals") : "documents";
    STATE.aiRevTab = tab;
    document.querySelectorAll("[data-airev-tab]").forEach(function (b) {
      var t = b.getAttribute("data-airev-tab");
      b.classList.toggle("perm-hidden", t === "proposals" && !canManage);
      b.classList.toggle("on", t === tab);
    });
    return Promise.all([
      canManage ? softGet("/api/v1/ai/knowledge/proposals") : Promise.resolve(null),
      softGet("/api/v1/ai/knowledge/documents"),
    ]).then(function (res) {
      var proposals = res[0] || [];
      var docs = res[1] || [];
      if (tab === "documents") {
        host.innerHTML = panel("قاعدة المعرفة المعتمدة", "Approved knowledge base",
          docs.length
            ? '<div class="av-list">' + docs.map(function (d) {
                var archived = (d.status || "") === "archived";
                return '<div class="av-row" style="cursor:default"><div class="grow">' +
                  '<div class="t">' + escapeHtml(d.title || d.name || "") + '</div>' +
                  '<div class="s">' + escapeHtml(d.status || "") + '</div>' +
                  '</div>' +
                  (canManage && !archived
                    ? '<button class="chip" data-kb-archive="' + d.id + '">' + dual("أرشفة", "Archive") + '</button>'
                    : "") +
                  '</div>';
              }).join("") + "</div>"
            : noticeHtml("لا توجد مستندات معتمدة بعد.", "No approved documents yet."));
        host.querySelectorAll("[data-kb-archive]").forEach(function (btn) {
          btn.addEventListener("click", function () {
            var id = parseInt(btn.getAttribute("data-kb-archive"), 10);
            post("/api/v1/ai/knowledge/documents/" + id + "/archive", {})
              .then(function () { toast(dual("تمت أرشفة المستند.", "Document archived."), "ok"); return renderAiReviewView(); })
              .catch(function (err) { domainError(err); });
          });
        });
        return;
      }
      host.innerHTML = panel("مقترحات المساعد", "Assistant proposals",
        proposals.length
          ? '<div class="av-list">' + proposals.map(function (p) {
              var pending = (p.status || "pending") === "pending";
              return '<div class="av-row" style="cursor:default"><div class="grow">' +
                '<div class="t">' + escapeHtml(p.title || p.question || dual("مقترح", "Proposal")) + '</div>' +
                '<div class="s">' + escapeHtml(p.status || "") + '</div>' +
                '</div>' +
                (canApprove && pending
                  ? '<button class="chip" data-kb-approve="' + p.id + '">' + dual("اعتماد", "Approve") + '</button>' +
                    '<button class="chip" data-kb-reject="' + p.id + '">' + dual("رفض", "Reject") + '</button>'
                  : "") +
                '</div>';
            }).join("") + "</div>"
          : noticeHtml("لا توجد مقترحات بانتظار الاعتماد.", "No proposals awaiting approval."));
      host.querySelectorAll("[data-kb-approve],[data-kb-reject]").forEach(function (btn) {
        btn.addEventListener("click", function () {
          var approve = btn.hasAttribute("data-kb-approve");
          var id = parseInt(btn.getAttribute(approve ? "data-kb-approve" : "data-kb-reject"), 10);
          post("/api/v1/ai/knowledge/proposals/" + id + "/resolve", { decision: approve ? "approve" : "reject" })
            .then(function () { toast(dual("تم تحديث المقترح.", "Proposal updated."), "ok"); return renderAiReviewView(); })
            .catch(function (err) { domainError(err); });
        });
      });
    }).catch(function (err) { handleLoadError(err); host.innerHTML = errorHtml(errText(err)); });
  }

  function renderAccountingView() {
    var host = byId("acctContent");
    if (!host) return Promise.resolve();
    if (!STATE.acctBound) {
      STATE.acctBound = true;
      bindAcctTabs();
      bindHost(host, onAcctAct);
    }
    if (!STATE.acctTab || !canAcctTab(STATE.acctTab)) STATE.acctTab = firstAcctTab();
    STATE.acctSection = ACCT_TAB_SECTION[STATE.acctTab] || ACCT_SECTIONS[0];
    syncAcctSections();
    return renderAcctTab(STATE.acctTab);
  }

  // Approved accountant sections (spec Table 81 / AC-28). The accountant's area
  // is grouped into exactly these five; the fine-grained chips are the buttons
  // *within* the active section, so selecting a section shows only its buttons.
  var ACCT_SECTIONS = ["holding_accounts", "invoices_dues", "subsidiary_finance", "financial_reports", "tasks_requests"];
  var ACCT_SECTION_PERM = {
    holding_accounts: ["account.read", "journal.read", "opening_balance.read"],
    invoices_dues: ["invoice.read", "party.read", "interbalance.read"],
    subsidiary_finance: ["financial_summary.read_own", "financial_summary.read_all", "dashboard.holding"],
    financial_reports: ["financial_report.read", "asset.read", "budget.read", "kpi.read", "accounting_policy.read"],
    tasks_requests: ["task.read_own", "task.read_all", "support_request.read_own", "support_request.read_all"],
  };
  var ACCT_TABS = ["balances", "accounts", "journals", "trial", "ledger", "statements", "invoices", "parties", "interbalances", "company_finance", "reports", "statements_internal", "assets", "budgets", "kpis", "policies", "tasks"];
  var ACCT_TAB_SECTION = {
    balances: "holding_accounts", accounts: "holding_accounts", journals: "holding_accounts",
    trial: "holding_accounts", ledger: "holding_accounts", statements: "holding_accounts",
    invoices: "invoices_dues", parties: "invoices_dues", interbalances: "invoices_dues",
    company_finance: "subsidiary_finance",
    reports: "financial_reports", statements_internal: "financial_reports", assets: "financial_reports",
    budgets: "financial_reports", kpis: "financial_reports", policies: "financial_reports",
    tasks: "tasks_requests",
  };
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
    company_finance: ["financial_summary.read_own", "financial_summary.read_all", "dashboard.holding"],
    reports: ["financial_report.read"],
    statements_internal: ["journal.read"],
    assets: ["asset.read"],
    budgets: ["budget.read"],
    kpis: ["kpi.read"],
    policies: ["accounting_policy.read"],
    tasks: ["task.read_own", "task.read_all", "support_request.read_own", "support_request.read_all"],
  };
  function canAcctTab(t) { return (ACCT_TAB_PERM[t] || []).some(has); }
  function canAcctSection(s) { return (ACCT_SECTION_PERM[s] || []).some(has); }
  function visibleAcctSections() { return ACCT_SECTIONS.filter(canAcctSection); }
  function firstAcctSection() {
    var ok = visibleAcctSections();
    return ok.length ? ok[0] : ACCT_SECTIONS[0];
  }
  function firstAcctTab() {
    for (var i = 0; i < ACCT_TABS.length; i++) if (canAcctTab(ACCT_TABS[i])) return ACCT_TABS[i];
    return "balances";
  }
  function firstTabInSection(section) {
    for (var i = 0; i < ACCT_TABS.length; i++) {
      if (ACCT_TAB_SECTION[ACCT_TABS[i]] === section && canAcctTab(ACCT_TABS[i])) return ACCT_TABS[i];
    }
    return firstAcctTab();
  }
  function syncAcctSections() {
    if (ACCT_SECTIONS.indexOf(STATE.acctSection) < 0) STATE.acctSection = firstAcctSection();
    document.querySelectorAll("[data-acct-section-btn]").forEach(function (b) {
      var s = b.getAttribute("data-acct-section-btn");
      var allowed = canAcctSection(s);
      b.style.display = allowed ? "" : "none";
      b.classList.toggle("on", s === STATE.acctSection);
    });
    document.querySelectorAll("[data-acct-tab]").forEach(function (b) {
      var t = b.getAttribute("data-acct-tab");
      var inSection = ACCT_TAB_SECTION[t] === STATE.acctSection;
      b.style.display = (inSection && canAcctTab(t)) ? "" : "none";
    });
  }
  function bindAcctTabs() {
    document.querySelectorAll("[data-acct-section-btn]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var s = btn.getAttribute("data-acct-section-btn");
        if (!canAcctSection(s)) return;
        STATE.acctSection = s;
        STATE.acctTab = firstTabInSection(s);
        syncAcctSections();
        renderAcctTab(STATE.acctTab);
      });
    });
    document.querySelectorAll("[data-acct-tab]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var t = btn.getAttribute("data-acct-tab");
        if (!canAcctTab(t)) return;
        STATE.acctTab = t;
        STATE.acctSection = ACCT_TAB_SECTION[t] || STATE.acctSection;
        syncAcctSections();
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
    if (tab === "company_finance") return renderCompanyFinanceComparison();
    if (tab === "reports") return renderFinancialReports();
    if (tab === "statements_internal") return renderStatements();
    if (tab === "assets") return renderAssets();
    if (tab === "budgets") return renderBudgets();
    if (tab === "kpis") return renderKpis();
    if (tab === "policies") return renderPolicies();
    if (tab === "tasks") return renderTasksRegistry();
    return Promise.resolve();
  }

  // AC-28 "ماليات الشركات": company financial reports, performance comparison
  // and the group financial summary, all read-only for the accountant.
  function renderCompanyFinanceComparison() {
    var host = byId("acctContent");
    var FIN_MAP = {
      draft: ["مسودة", "Draft", "warn"],
      finalised: ["معتمد", "Finalised", "ok"],
      archived: ["مؤرشف", "Archived", "rev"],
    };
    // A user may reach this section through `dashboard.holding` alone, which
    // the group-summary panel needs but the report archive does not.
    var canReadReports = has("financial_report.read");
    return (canReadReports
      ? softGet("/api/v1/accounting/financial-reports")
      : Promise.resolve([])
    ).then(function (reports) {
      var group = has("dashboard.holding") ? groupReportPanel() : "";
      host.innerHTML = panel(
        "ماليات الشركات (المقارنة والملخص المالي للمجموعة)",
        "Subsidiary finance (comparison and group financial summary)",
        group + '<div id="finReportsList"></div>'
      );
      var listHost = byId("finReportsList");
      if (listHost) {
        // Slides 134-136: the financial-report archive carries the deck's
        // company / period / status / currency filters, the apply / save /
        // clear / export cluster, and "الفترة الأحدث" as the default sort.
        var finSpec = [
          { key: "q", type: "search", ar: "الشركة", en: "Company",
            fields: ["company_name_ar", "company_name_en", "currency"] },
          companyFilterOption(),
          { key: "period", ar: "الفترة", en: "Period",
            resolve: function (r) { return r.period_year ? r.period_year + "-" + String(r.period_month).padStart(2, "0") : ""; },
            options: distinctOptions(reports, function (r) {
              return r.period_year ? r.period_year + "-" + String(r.period_month).padStart(2, "0") : "";
            }) },
          { key: "status", ar: "الحالة", en: "Status", field: "status",
            options: distinctOptions(reports, function (r) { return r.status; },
              function (v) { return { ar: (FIN_MAP[v] || [v])[0], en: (FIN_MAP[v] || [v, v])[1] }; }) },
          { key: "currency", ar: "العملة", en: "Currency", field: "currency",
            options: distinctOptions(reports, function (r) { return r.currency; }) },
        ];
        var finRows = applyListFilters(scopeFilter(reports), "financialReports", finSpec);
        finRows.sort(function (a, b) {
          return (b.period_year - a.period_year) || (b.period_month - a.period_month) || byIdAsc(a, b);
        });
        renderPaged(listHost, "financialReports", finRows, function (r) {
          return '<div class="av-row" style="cursor:default"><div class="grow">' +
            '<div class="t">' + escapeHtml(companyNameById(r.company_id)) + " · " +
            dec(r.period_month) + "/" + dec(r.period_year) + "</div>" +
            '<div class="s">' + escapeHtml(r.currency || "") + "</div></div>" +
            statusBadgeFromMap(r.status, FIN_MAP) + "</div>";
        }, null, finSpec);
      }
      if (has("dashboard.holding")) bindHost(host, onAcctAct);
      return null;
    }).catch(function (err) { handleLoadError(err); host.innerHTML = errorHtml(errText(err)); });
  }

  // AC-28 "المهام والطلبات": the accountant's tasks and service requests.
  function renderTasksRegistry() {
    var host = byId("acctContent");
    // The tab is reachable through `support_request.read_*` as well as
    // `task.read_*`, so only ask for tasks when the caller may read them.
    var canReadTasks = has("task.read_own") || has("task.read_all");
    return Promise.all([
      canReadTasks
        ? softGet("/api/v1/operations/tasks")
        : Promise.resolve([]),
      softGet("/api/v1/support-requests"),
    ]).then(function (res) {
      var tasks = res[0] || [];
      var tlist = tasks.length
        ? '<div class="av-list">' + tasks.map(taskRow).join("") + "</div>"
        : noticeHtml("لا توجد مهام.", "No tasks.");
      var reqs = res[1] || [];
      var rlist = reqs.length
        ? '<div class="av-list">' + reqs.map(function (r) {
            return '<div class="av-row" style="cursor:default"><div class="grow"><div class="t">' +
              escapeHtml(r.subject || r.title || "") + "</div></div>" +
              statusBadgeFromMap(r.status, {}) + "</div>";
          }).join("") + "</div>"
        : noticeHtml("لا توجد طلبات.", "No requests.");
      host.innerHTML =
        (canReadTasks
          ? panel("الطلبات الجديدة", "New tasks & requests", tlist)
          : "") +
        panel("سجل الطلبات", "Requests registry", rlist);
      return null;
    }).catch(function (err) { handleLoadError(err); host.innerHTML = errorHtml(errText(err)); });
  }

  function renderOpeningBalances() {
    var host = byId("acctContent");
    return Promise.all([ensureCompanies(), softGet("/api/v1/accounting/opening-balances")]).then(function (res) {
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
              " · " + dual("بنك", "Bank") + " " + dec(o.bank) + " · " + dual("نقد", "Cash") + " " + dec(o.cash) +
              " · " + dual("إجمالي النقد", "Total cash") + " " + dec(o.total_cash) + "</div></div>" +
              statusBadgeFromMap(o.status, { draft: ["مسودة", "Draft", "warn"], submitted: ["مُقدَّم", "Submitted", "warn"], approved: ["معتمد", "Approved", "ok"] }) +
              "</div>" + (controls ? '<div class="av-user-controls" data-stop="1">' + controls + "</div>" : "") + "</div>";
          }).join("") + "</div>"
        : noticeHtml("لا توجد أرصدة.", "No balances.");
      host.innerHTML = panel("الأرصدة الافتتاحية والمرحّلة (D08)", "Opening & carry-forward balances (D08)", note + create + list);
    }).catch(function (err) { handleLoadError(err); host.innerHTML = errorHtml(errText(err)); });
  }

  function renderAccounts() {
    var host = byId("acctContent");
    return Promise.all([ensureCompanies(), softGet("/api/v1/accounting/accounts")]).then(function (res) {
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
      STATE.acctAccounts = rows;
      host.innerHTML = panel("دليل الحسابات (D01)", "Chart of accounts (D01)", create + '<div id="acctAccountsList"></div>');
      mountList("acctAccountsList", "accounts", rows, function (a) {
        return '<div class="av-row" style="cursor:default"><div class="grow"><div class="t">' +
          escapeHtml(a.code + " · " + (STATE.lang === "ar" ? a.name_ar : a.name_en || a.name_ar)) + "</div>" +
          '<div class="s">' + escapeHtml(companyNameById(a.company_id)) + " · " + escapeHtml(a.account_type) + "</div></div></div>";
      }, accountsFilterSpec(), null,
        // Slide 135 "حسابات / ميزانية / مراكز": default sort by account code.
        byTextAsc(function (a) { return a.code; }));
    }).catch(function (err) { handleLoadError(err); host.innerHTML = errorHtml(errText(err)); });
  }

  function renderJournals() {
    var host = byId("acctContent");
    return Promise.all([ensureCompanies(), softGet("/api/v1/accounting/journals")]).then(function (res) {
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
          dual("إضافة عملية", "Add transaction") + "</button></div></form>"
        : "";
      STATE.acctJournals = rows;
      host.innerHTML = panel("القيود (D01: غير قابلة للتعديل بعد الترحيل — التصحيح بالعكس)", "Journals (D01: immutable once posted — correction by reversal)", create + '<div id="acctJournalsList"></div>');
      mountList("acctJournalsList", "journals", rows, function (j) {
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
      }, journalsFilterSpec(), null,
        // Slide 135 "القيود": newest entry date first, stable by ID.
        function (a, b) {
          return String(b.entry_date || "").localeCompare(String(a.entry_date || "")) || byIdAsc(a, b);
        });
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
      softGet("/api/v1/accounting/invoices"),
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
      STATE.acctInvoices = rows;
      host.innerHTML = panel("الفواتير والمستحقات (D01/D09: لا يوجد إجراء تحويل بنكي)", "Invoices & receivables (D01/D09: no bank-transfer action)", totals + create + '<div id="acctInvoicesList"></div>');
      mountList("acctInvoicesList", "invoices", rows, function (iv) {
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
      }, invoicesFilterSpec(), null,
        // Slide 135 "إيرادات / مصروفات / ذمم": default sort "الاستحقاق تصاعديًا
        // للذمم" -- earliest due date first.
        byDateAsc(function (iv) { return iv.due_date; }));
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
    return Promise.all([ensureCompanies(), softGet("/api/v1/accounting/parties")]).then(function (res) {
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
      STATE.acctParties = rows;
      host.innerHTML = panel("العملاء والموردون (S27: دليل واحد للفواتير الصادرة والواردة)", "Customers & suppliers (S27: one directory for issued and received invoices)", create + '<div id="acctPartiesList"></div>');
      mountList("acctPartiesList", "parties", rows, function (p) {
        return '<div class="av-row" style="cursor:default"><div class="grow"><div class="t">' +
          escapeHtml(p.name) + "</div>" +
          '<div class="s">' + escapeHtml(companyNameById(p.company_id)) + " · " +
          escapeHtml(p.party_type === "supplier" ? opt("مورد", "Supplier") : opt("عميل", "Customer")) +
          " · " + escapeHtml(p.currency) + (p.contact ? " · " + escapeHtml(p.contact) : "") + "</div></div></div>";
      }, partiesFilterSpec());
    }).catch(function (err) { handleLoadError(err); host.innerHTML = errorHtml(errText(err)); });
  }

  function renderInterbalances() {
    var host = byId("acctContent");
    return Promise.all([ensureCompanies(), softGet("/api/v1/accounting/interbalances")]).then(function (res) {
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
    return Promise.all([ensureCompanies(), softGet("/api/v1/accounting/assets")]).then(function (res) {
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
      STATE.acctAssets = rows;
      host.innerHTML = panel("الأصول (D01)", "Assets (D01)", create + '<div id="acctAssetsList"></div>');
      mountList("acctAssetsList", "assets", rows, function (a) {
        return '<div class="av-row" style="cursor:default"><div class="grow"><div class="t">' +
          escapeHtml(a.name) + "</div>" +
          '<div class="s">' + escapeHtml(companyNameById(a.company_id)) + " · " +
          dual("التكلفة", "Cost") + " " + dec(a.cost) + " · " + escapeHtml(a.category || "") + "</div></div></div>";
      }, assetsFilterSpec(), null,
        // Slide 135 "حسابات / ميزانية / مراكز": default sort by asset name.
        byTextAsc(function (a) { return a.name; }));
    }).catch(function (err) { handleLoadError(err); host.innerHTML = errorHtml(errText(err)); });
  }

  function renderBudgets() {
    var host = byId("acctContent");
    return Promise.all([ensureCompanies(), softGet("/api/v1/accounting/budgets")]).then(function (res) {
      var rows = res[1] || [];
      STATE.budgetRows = rows;
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
      STATE.acctBudgets = rows;
      host.innerHTML = panel("الموازنات (D07: المصدر والإصدار محفوظان، والاعتماد لا يستبدل القيم)", "Budgets (D07: source + version preserved; approval does not overwrite)", create + budgetUtilPanel() + '<div id="acctBudgetsList"></div>');
      mountList("acctBudgetsList", "budgets", rows, function (b) {
        var approve = b.status !== "approved" && has("budget.approve")
          ? actBtn("budget.approve", "bg-approve", b.id, "اعتماد", "Approve")
          : "";
        var utilBtn = b.status === "approved" && has("budget.read")
          ? actBtn("budget.read", "bg-util", b.id, "عرض الفروق", "View variances")
          : "";
        return '<div class="av-row" style="flex-direction:column;align-items:stretch;cursor:default"><div style="display:flex;align-items:center;gap:11px">' +
          '<div class="grow"><div class="t">' + escapeHtml(companyNameById(b.company_id)) + " · " + dec(b.fiscal_year) +
          " · v" + dec(b.version) + "</div>" +
          '<div class="s">' + dual("الإجمالي", "Total") + " " + dec(b.total_amount) +
          " · " + dual("المصدر", "Source") + " " + escapeHtml(b.source || "—") + "</div></div>" +
          statusBadgeFromMap(b.status, { draft: ["مسودة", "Draft", "warn"], approved: ["معتمدة", "Approved", "ok"], superseded: ["مستبدلة", "Superseded", "rev"] }) +
          "</div>" + (approve || utilBtn ? '<div class="av-user-controls" data-stop="1">' + approve + utilBtn + "</div>" : "") + "</div>";
      }, budgetsFilterSpec(), null,
        // Slide 135 "حسابات / ميزانية / مراكز": default sort by budget period,
        // newest year first (a later year supersedes an earlier one).
        function (a, b) {
          return (b.fiscal_year - a.fiscal_year) || byIdAsc(a, b);
        });
    }).catch(function (err) { handleLoadError(err); host.innerHTML = errorHtml(errText(err)); });
  }

  // AC-28: an over-budget year reports the variance and never creates a payment
  // approval (Table 56 "يفتح المصدر والفروق دون اعتماد صرف").
  function budgetUtilPanel() {
    var u = STATE.budgetUtil;
    if (!u) return "";
    var over = u.over_budget
      ? '<span class="status warn"><i></i>' + dual("متجاوزة", "Over budget") + "</span>"
      : '<span class="status ok"><i></i>' + dual("داخل الموازنة", "Within budget") + "</span>";
    return '<div class="av-row" style="flex-direction:column;align-items:stretch;cursor:default">' +
      '<div style="display:flex;align-items:center;gap:11px"><div class="grow">' +
      '<div class="t">' + dual("فروق الموازنة", "Budget variances") + " · " +
      escapeHtml(companyNameById(u.company_id)) + " · " + dec(u.fiscal_year) + "</div>" +
      '<div class="s">' + dual("الموازنة", "Budget") + " " + dec(u.budget_total) +
      " · " + dual("الفعلي", "Actual") + " " + dec(u.actual_expenses) +
      " · " + dual("الفرق", "Variance") + " " + dec(u.variance) + " " + escapeHtml(u.currency) +
      "</div></div>" + over +
      '<button class="btn-ghost" data-act="bg-util-close">' + dual("إغلاق", "Close") + "</button>" +
      "</div></div>";
  }

  function kpiStatusBadge(ev) {
    var cls = ev.status === "active" ? "rev" : "";
    var label = ev.status === "active"
      ? dual("نشط", "Active")
      : dual("بانتظار الاعتماد", "Pending approval");
    return '<span class="status ' + cls + '"><i></i>' + label + "</span>";
  }

  function kpiVarianceCell(ev) {
    if (ev.actual_value == null || ev.target_value == null) {
      return '<span class="s">' + dual("لا نتيجة بعد", "No result yet") + "</span>";
    }
    var pct = ev.variance_pct == null ? "" : " (" + (ev.variance_pct >= 0 ? "+" : "") + NUM.format(ev.variance_pct) + "%)";
    var cls = ev.favourable ? "rev" : "warn";
    return '<span class="status ' + cls + '"><i></i>' + dual("الفرق", "Variance") + " " +
      (ev.variance >= 0 ? "+" : "") + dec(ev.variance) + escapeHtml(pct) + "</span>";
  }

  // D02: target-versus-actual comes from the server's evaluation endpoint, never
  // from client arithmetic, and every figure keeps its own source drill-down.
  function renderKpis() {
    var host = byId("acctContent");
    return Promise.all([
      ensureCompanies(),
      softGet("/api/v1/accounting/kpis"),
      softGet("/api/v1/accounting/kpis/evaluations?" + finPeriodQuery()),
    ]).then(function (res) {
      var rows = res[1] || [];
      var evals = res[2] || [];
      STATE.kpis = rows;
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
      var kpiSpec = kpisFilterSpec();
      var kpiList = applyListFilters(rows, "kpis", kpiSpec);
      // Slide 136 "المؤشرات / العملات": default sort by effective date (the
      // KPI's approval timestamp), newest first, stable by ID.
      kpiList.sort(function (a, b) {
        return String(b.approved_at || "").localeCompare(String(a.approved_at || "")) || byIdAsc(a, b);
      });
      var kpiRow = function (k) {
            var toggle = canManage
              ? actBtn("kpi.manage", k.is_active ? "kpi-deactivate" : "kpi-activate", k.id,
                  k.is_active ? "إيقاف" : "اعتماد", k.is_active ? "Deactivate" : "Approve")
              : "";
            return '<div class="av-row" style="cursor:default"><div class="grow"><div class="t">' +
              escapeHtml(k.code + " · " + (STATE.lang === "ar" ? k.name_ar : k.name_en || k.name_ar)) + "</div>" +
              '<div class="s">' + dual("المصدر", "Source") + " " + escapeHtml(k.data_source) +
              " · " + dual("الطريقة", "Method") + " " + escapeHtml(k.calculation_method) +
              " · " + escapeHtml(k.period_label) + "</div></div>" +
              (k.target_value != null ? '<span class="status rev"><i></i>' + dual("المستهدف", "Target") + " " + dec(k.target_value) + "</span>" : "") +
              toggle +
              "</div>";
      };
      var evaluations = evals.length
        ? '<div class="av-list">' + evals.map(function (ev) {
            return '<div class="av-row" data-kpi-open="' + ev.id + '"><div class="grow"><div class="t">' +
              escapeHtml(ev.code + " · " + (STATE.lang === "ar" ? ev.name_ar : ev.name_en || ev.name_ar)) + "</div>" +
              '<div class="s">' + dual("المستهدف", "Target") + " " + dec(ev.target_value) +
              " · " + dual("المتحقق", "Actual") + " " + dec(ev.actual_value) +
              (ev.unit ? " · " + escapeHtml(ev.unit) : "") + "</div></div>" +
              kpiVarianceCell(ev) + kpiStatusBadge(ev) +
              "</div>";
          }).join("") + "</div>"
        : noticeHtml("لا توجد نتائج لهذه الفترة.", "No results for this period.");
      var body =
        panel("المؤشرات · المستهدف مقابل المتحقق (" + kpiPeriodText() + ")",
              "KPIs · target versus actual",
              evaluations + '<div class="av-empty">' +
              dual("اختر مؤشرًا لعرض السجلات المصدر خلف النتيجة.",
                   "Select a KPI to see the source records behind its result.") + "</div>") +
        panel("تعريفات المؤشرات (D02: مصدر + طريقة + فترة)",
              "KPI definitions (D02: source + method + period)",
              create + '<div id="kpiDefs"></div>');
      host.innerHTML = body;
      renderPaged(byId("kpiDefs"), "kpis", kpiList, kpiRow, null, kpiSpec);
      host.querySelectorAll("[data-kpi-open]").forEach(function (row) {
        row.addEventListener("click", function (e) {
          if (e.target.closest && e.target.closest("[data-stop]")) return;
          openKpiSources(row.getAttribute("data-kpi-open"));
        });
      });
    }).catch(function (err) { handleLoadError(err); host.innerHTML = errorHtml(errText(err)); });
  }

  function kpiPeriodText() {
    var p = periodLabel();
    return p.ar ? p.ar : String(STATE.year || "");
  }

  // Drill-down: fetch the evaluation *with its source records* for one KPI.
  // Source records carry {kind, record_id, label_ar} and are opened through the
  // same navigators the dashboard drill-down uses, so a KPI can never show a
  // snapshot that drifts from the underlying record.
  function openKpiSources(id) {
    openModal({
      title: dual("سجلات المصدر", "Source records"),
      body: loadingHtml(),
      wide: true,
      onMount: function () {
        get("/api/v1/accounting/kpis/" + id + "/sources?" + finPeriodQuery())
          .then(function (ev) {
            var host = byId("modalBody");
            if (!host) return;
            var rows = ev.sources || [];
            var head = kpiVarianceCell(ev);
            if (!rows.length) {
              host.innerHTML = head + emptyHtml(
                "لا توجد سجلات مصدر لهذه الفترة.",
                "No source records for this period.",
              );
              return;
            }
            host.innerHTML = head +
              '<table class="table"><thead><tr><th>' + dual("النوع", "Type") +
              "</th><th>" + dual("السجل", "Record") + "</th></tr></thead><tbody>" +
              rows.map(function (r) {
                var typeLabel = r.kind === "company"
                  ? dual("شركة", "Company")
                  : r.kind === "support_request"
                    ? dual("طلب", "Request")
                    : dual("تقرير", "Report");
                return '<tr data-kpi-kind="' + escapeHtml(r.kind) +
                  '" data-kpi-id="' + r.record_id + '" style="cursor:pointer"><td>' +
                  typeLabel + "</td><td>" + escapeHtml(r.label_ar) + "</td></tr>";
              }).join("") + "</tbody></table>";
            host.querySelectorAll("[data-kpi-kind]").forEach(function (el) {
              el.addEventListener("click", function () {
                var kind = el.getAttribute("data-kpi-kind");
                var recId = parseInt(el.getAttribute("data-kpi-id"), 10);
                closeModal();
                if (kind === "company") openCompany(recId);
                else if (kind === "support_request") navTo("support");
                else if (kind === "monthly_report") openReport(recId);
              });
            });
          })
          .catch(function (err) {
            var host = byId("modalBody");
            if (host) host.innerHTML = errorHtml(errText(err));
          });
      },
    });
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
      softGet("/api/v1/accounting/policies"),
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

  // S28 Table 57: the accountant draws the accounts for a month, adds the
  // analysis, then finalises; the BD and owner read the archive.
  var FIN_REPORT_STATUS = {
    draft: ["مسودة", "Draft", "warn"],
    finalised: ["معتمد", "Finalised", "ok"],
    archived: ["مؤرشف", "Archived", "rev"],
  };
  function renderFinancialReports() {
    var host = byId("acctContent");
    return Promise.all([
      ensureCompanies(),
      softGet("/api/v1/accounting/financial-reports"),
    ]).then(function (res) {
      var rows = res[1] || [];
      var canManage = has("financial_report.manage");
      var canFinalise = has("financial_report.finalise");
      var create = canManage
        ? '<form class="av-form av-form-inline" id="finReportForm">' +
          field("الشركة", "Company", selectInput("frCompany", companySelectOptions(false), STATE.companies.length ? STATE.companies[0].id : "")) +
          field("السنة", "Year", numInput("frYear", STATE.year || "")) +
          field("الشهر", "Month", numInput("frMonth", STATE.month || "")) +
          '<div class="av-form-actions"><button class="btn-solid" type="submit">' +
          dual("سحب الحسابات وإعداد التقرير", "Draw accounts & prepare report") + "</button></div></form>"
        : "";
      var list = rows.length
        ? '<div class="av-list">' + rows.map(function (r) {
            var summary = (r.figures && r.figures.summary) || [];
            var money = summary.map(function (s) {
              return escapeHtml(s.currency) + " " + dec(s.net);
            }).join(" · ") || dual("لا حركة", "No movement");
            var actions = "";
            if (r.status === "draft" && canManage) {
              actions += '<input class="inp" data-field="analysis" data-id="' + r.id + '" style="min-width:220px" placeholder="' + dual("التحليل", "Analysis") + '" value="' + escAttr(r.analysis || "") + '">';
              actions += actBtn("financial_report.manage", "fr-analysis", r.id, "حفظ التحليل", "Save analysis");
            }
            if (r.status === "draft" && canFinalise) {
              actions += actBtn("financial_report.finalise", "fr-finalise", r.id, "اعتماد", "Finalise");
            }
            if (r.status === "finalised" && canFinalise) {
              actions += actBtn("financial_report.finalise", "fr-archive", r.id, "أرشفة", "Archive");
            }
            return '<div class="av-row" style="flex-direction:column;align-items:stretch;cursor:default"><div style="display:flex;align-items:center;gap:11px">' +
              '<div class="grow"><div class="t">' + escapeHtml(companyNameById(r.company_id)) + " · " +
              dec(r.period_month) + "/" + dec(r.period_year) + "</div>" +
              '<div class="s">' + money + "</div></div>" +
              statusBadgeFromMap(r.status, FIN_REPORT_STATUS) +
              "</div>" + (actions ? '<div class="av-user-controls" data-stop="1">' + actions + "</div>" : "") + "</div>";
          }).join("") + "</div>"
        : noticeHtml("لا توجد تقارير مالية بعد.", "No financial reports yet.");
      host.innerHTML = panel(
        "التقرير المالي الشهري (S28: يسحب الحسابات ويضيف التحليل، والمعتمد لا يُعدّل)",
        "Monthly financial report (S28: draws the accounts and adds the analysis; a finalised report is immutable)",
        create + (has("dashboard.holding") ? groupReportPanel() : "") + list
      );
    }).catch(function (err) { handleLoadError(err); host.innerHTML = errorHtml(errText(err)); });
  }

  // S28: the group view keeps the holding and the subsidiaries distinct and
  // never claims consolidation ("لا يدعي إلغاء التعاملات للتوحيد").
  function groupReportPanel() {
    var g = STATE.groupReport;
    if (!g) {
      return '<div class="av-row" style="cursor:default"><div class="grow">' +
        '<div class="t">' + dual("تقرير المجموعة", "Group report") + "</div>" +
        '<div class="s">' + dual("يميّز القابضة عن ملخصات التابعة دون ادعاء التوحيد",
          "Distinguishes the holding from subsidiary summaries without claiming consolidation") + "</div></div>" +
        '<button class="btn-ghost" data-act="fr-group">' + dual("عرض المجموعة", "View group") + "</button></div>";
    }
    var hold = g.holding.length
      ? g.holding.map(function (h) {
          var money = (h.summary || []).map(function (s) {
            return escapeHtml(s.currency) + " " + dec(s.net);
          }).join(" · ") || dual("لا حركة", "No movement");
          return '<div class="s">' + escapeHtml(h.name_ar) + ": " + money + "</div>";
        }).join("")
      : '<div class="s">' + dual("لا حسابات قابضة لهذه الفترة", "No holding accounts this period") + "</div>";
    var subs = g.subsidiaries.length
      ? g.subsidiaries.map(function (s) {
          var val = s.approved
            ? escapeHtml(s.currency || "") + " " + dec(s.result)
            : dual("لا يوجد ملخص معتمد", "No approved summary");
          return '<div class="s">' + escapeHtml(s.name_ar) + ": " + val + "</div>";
        }).join("")
      : "";
    return '<div class="av-row" style="flex-direction:column;align-items:stretch;cursor:default">' +
      '<div style="display:flex;align-items:center;gap:11px"><div class="grow">' +
      '<div class="t">' + dual("تقرير المجموعة", "Group report") + " · " +
      dec(g.period_month) + "/" + dec(g.period_year) + "</div>" +
      '<div class="s"><b>' + dual("القابضة", "Holding") + "</b></div>" + hold +
      (subs ? '<div class="s"><b>' + dual("التابعة", "Subsidiaries") + "</b></div>" + subs : "") +
      '<div class="s">' + escapeHtml(g.consolidation_note_ar || g.consolidation_note_en || "") + "</div>" +
      "</div>" +
      '<button class="btn-ghost" data-act="fr-group-close">' + dual("إغلاق", "Close") + "</button>" +
      "</div></div>";
  }

  function onAcctAct(action, id, el) {
    if (action === "kpi-activate" || action === "kpi-deactivate") {
      busy(el, true);
      return post("/api/v1/accounting/kpis/" + id + "/active", { active: action === "kpi-activate" })
        .then(function () { toast(dual("تم تحديث اعتماد المؤشر.", "KPI approval updated."), "ok"); return renderKpis(); })
        .catch(function (err) { domainError(err); busy(el, false); });
    }
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
    if (action === "bg-util") {
      busy(el, true);
      var budget = (STATE.budgetRows || []).filter(function (b) { return b.id === id; })[0];
      if (!budget) { busy(el, false); return; }
      return get("/api/v1/accounting/budgets/utilisation?company_id=" + budget.company_id +
                 "&fiscal_year=" + budget.fiscal_year)
        .then(function (u) { STATE.budgetUtil = u; return renderBudgets(); })
        .catch(function (err) { domainError(err); busy(el, false); });
    }
    if (action === "bg-util-close") { STATE.budgetUtil = null; return renderBudgets(); }
    if (action === "fr-group") {
      busy(el, true);
      return get("/api/v1/accounting/financial-reports/group?period_year=" +
                 (STATE.year || "") + "&period_month=" + (STATE.month || ""))
        .then(function (g) { STATE.groupReport = g; return renderFinancialReports(); })
        .catch(function (err) { domainError(err); busy(el, false); });
    }
    if (action === "fr-group-close") { STATE.groupReport = null; return renderFinancialReports(); }
    if (action === "fr-analysis") {
      busy(el, true);
      var input = document.querySelector('[data-field="analysis"][data-id="' + id + '"]');
      return patch("/api/v1/accounting/financial-reports/" + id + "/analysis",
                   { analysis: input ? input.value : null })
        .then(function () { toast(dual("تم حفظ التحليل.", "Analysis saved."), "ok"); return renderFinancialReports(); })
        .catch(function (err) { domainError(err); busy(el, false); });
    }
    if (action === "fr-finalise") {
      return confirmDialog({
        title: dual("اعتماد التقرير المالي", "Finalise the financial report"),
        message: dual("بعد الاعتماد لا يمكن تعديل التقرير. متابعة؟", "A finalised report cannot be edited. Continue?"),
      }).then(function (ok) {
        if (!ok) return;
        busy(el, true);
        return post("/api/v1/accounting/financial-reports/" + id + "/finalise", {})
          .then(function () { toast(dual("تم اعتماد التقرير المالي.", "Financial report finalised."), "ok"); return renderFinancialReports(); })
          .catch(function (err) { domainError(err); busy(el, false); });
      });
    }
    if (action === "fr-archive") {
      busy(el, true);
      return post("/api/v1/accounting/financial-reports/" + id + "/archive", {})
        .then(function () { toast(dual("تمت أرشفة التقرير.", "Report archived."), "ok"); return renderFinancialReports(); })
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
    if (id === "finReportForm") {
      busy(el.querySelector("button"), true);
      return post("/api/v1/accounting/financial-reports", {
        company_id: parseInt(valOf("frCompany"), 10),
        period_year: parseInt(valOf("frYear"), 10),
        period_month: numVal("frMonth"),
      }).then(function () { toast(dual("تم إعداد التقرير.", "Report prepared."), "ok"); return renderFinancialReports(); })
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
    return Promise.all([ensureCompanies(), softGet("/api/v1/operations/complaints")]).then(function (res) {
      var rows = res[1] || [];
      var canCreate = has("complaint.create");
      var create = canCreate
        ? '<form class="av-form av-form-inline" id="complaintForm">' +
          field("الموضوع", "Subject", textInput("coSubject", "", "", true), null, null, true) +
          field("الشركة (اختياري)", "Company (optional)", selectInput("coCompany", companySelectOptions(true), "")) +
          field("مجهولة؟", "Anonymous?", selectInput("coAnon", [{ value: "0", label: opt("لا", "No") }, { value: "1", label: opt("نعم", "Yes") }], "0")) +
          field("النص", "Body", textArea("coBody", "", "", true), null, null, true) +
          '<div class="av-form-actions"><button class="btn-solid" type="submit">' +
          dual("رفع شكوى", "Submit complaint") + "</button></div></form>"
        : "";
      var note = '<p class="note-block">' + dual("سرّي: مرئي للمالك فقط افتراضيًا، ولا يظهر في العدّادات أو البحث أو السجل العام.", "Confidential: owner-only by default, and excluded from counters, search and the public log.") + "</p>";
      var list = rows.length
        ? '<div class="av-list">' + rows.map(function (c) {
            var decide = has("complaint.decide")
              ? '<div class="av-field" style="margin-top:8px"><input class="av-input" id="coNote' + c.id + '" placeholder="' +
                dual("السبب أو الملاحظة (مطلوب عند الإحالة أو التأجيل)", "Reason or note (required to refer or defer)") + '"></div>' +
                '<div class="av-user-controls" data-stop="1">' +
                selectInput("coStatus" + c.id, [
                  { value: "under_review", label: opt("قيد المراجعة", "Under review") },
                  { value: "routed", label: opt("محوّلة", "Routed") },
                  { value: "handled", label: opt("معالجة", "Handled") },
                  { value: "postponed", label: opt("مؤجلة", "Postponed") },
                  { value: "closed", label: opt("مغلقة", "Closed") },
                ], c.status) +
                '<button class="btn-outline" data-act="conf-decide" data-id="' + c.id + '">' + dual("تسجيل إجراء", "Record action") + "</button></div>" +
                // Deck slide 31: the owner's four explicit actions on a complaint.
                '<div class="av-user-controls" data-stop="1" style="margin-top:8px">' +
                '<button class="btn-outline" data-act="conf-decide" data-id="' + c.id + '" data-status="routed">' + dual("إحالة", "Refer") + "</button>" +
                '<button class="btn-outline" data-act="conf-decide" data-id="' + c.id + '" data-status="handled">' + dual("اتخاذ إجراء", "Take action") + "</button>" +
                '<button class="btn-outline" data-act="conf-decide" data-id="' + c.id + '" data-status="under_review">' + dual("طلب معلومات", "Request info") + "</button>" +
                '<button class="btn-outline" data-act="conf-decide" data-id="' + c.id + '" data-status="postponed">' + dual("تأجيل مع سبب", "Defer with reason") + "</button></div>"
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
    // A quick-action button carries its own status; the select is the fallback.
    var status = el.getAttribute("data-status") || valOf("coStatus" + cid);
    var noteEl = byId("coNote" + cid);
    var note = noteEl ? noteEl.value.trim() : "";
    // Deck slide 31: "الإجراء | قرار / إحالة / تأجيل". Referring and deferring
    // are the two outcomes that must carry a reason, so refuse an empty one
    // rather than writing an unexplained decision.
    if ((status === "routed" || status === "postponed") && !note) {
      toast(
        dual("أدخل سبب الإحالة أو التأجيل.", "Enter a reason to refer or defer."),
        "err"
      );
      return Promise.resolve();
    }
    busy(el, true);
    return post("/api/v1/operations/complaints/" + cid + "/decision", {
      status: status,
      decision: note || null,
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

  var ADMIN_TABS = ["structure", "companies", "departments", "sectors", "positions", "users", "roles", "motivation", "website", "builder", "workflows", "integrations", "knowledge", "audit"];
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
    knowledge: ["ai.knowledge.read", "ai.admin"],
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
    if (tab === "knowledge") return renderAdminKnowledge();
    if (tab === "audit") return renderAdminAudit();
    return Promise.resolve();
  }

  function adminPanel(titleAr, titleEn, bodyHtml) {
    return (
      '<div class="av-panel"><h3>' + dual(titleAr, titleEn) + "</h3>" + bodyHtml + "</div>"
    );
  }

  function field(labelAr, labelEn, inputHtml, hintAr, hintEn, required) {
    var hint = hintAr
      ? '<span class="hint">' + dual(hintAr, hintEn || hintAr) + "</span>"
      : "";
    return (
      '<div class="av-field"><label>' + dual(labelAr, labelEn) +
      (required ? ' <span class="req">*</span>' : "") + "</label>" +
      inputHtml + hint +
      "</div>"
    );
  }

  function textInput(id, value, placeholder, required) {
    // A placeholder that matches an I18N key is emitted bilingually so it
    // follows the language switch; anything else is a literal example token.
    var ph =
      placeholder && I18N[placeholder]
        ? phAttr(placeholder)
        : ' placeholder="' + escAttr(placeholder || "") + '"';
    return (
      '<input class="av-input" id="' + id + '" type="text" value="' +
      escAttr(value || "") + '"' + ph + reqAttr(required) + ">"
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
        ? softGet("/api/v1/admin/holding/structure")
        : Promise.resolve([]);
      var ownershipP = has("ownership.read")
        ? softGet("/api/v1/admin/ownerships")
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
          field("الشركة المملوكة", "Owned company", selectInput("stOwned", companyOptions(nodes), ""), null, null, true) +
          field("المالك", "Owner", selectInput("stOwner", [{ value: "", label: "—" }].concat(companyOptions(nodes)), "")) +
          field("النسبة %", "Percentage %", '<input class="av-input" id="stPct" type="number" min="0" max="100" step="0.01" required>', null, null, true) +
          field("من تاريخ", "Effective from", '<input class="av-input" id="stFrom" type="date" required>', null, null, true) +
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
    return Promise.all([
      ensureCompanies(),
      wizardUserOptions(),
      has("ownership.read")
        ? softGet("/api/v1/admin/holding/structure")
        : Promise.resolve([]),
    ]).then(function (res) {
      var rows = res[0];
      var users = res[1];
      var nodes = res[2] || [];
      var create = has("company.manage") ? companyWizardPanel(rows, users) : "";
      var list = rows.length
        ? rows.map(function (c) { return adminPanel("شركة", "Company", companyAdminCard(c)); }).join("")
        : '<p class="av-empty">' + dual("لا توجد شركات.", "No companies.") + "</p>";
      host.innerHTML = create + list;
      if (create) bindCompanyWizard(rows, nodes);
    });
  }

  // The wizard's manager picker and linked-users list need real users. Deck
  // slide 51: "مدير الشركة *: مستخدم مدعو أو نشط" and "المستخدمون المرتبطون:
  // اختيار متعدد مع الدور والنطاق". Gated on user.read so a role that cannot
  // list users simply gets an empty picker instead of a 403.
  function wizardUserOptions() {
    if (!has("user.read")) return Promise.resolve([]);
    return softGet("/api/v1/admin/users?limit=200").then(function (data) {
      var items = (data && data.items) || [];
      return items
        .filter(function (u) { return u.is_active; })
        .map(function (u) {
          var name = STATE.lang === "ar" ? u.full_name_ar : u.full_name_en || u.full_name_ar;
          return { value: u.id, label: name + " · " + u.role_code };
        });
    });
  }

  // ---- tab: companies -- setup wizard (deck slides 50-52) ----
  // The deck specifies a three-step wizard, not a flat form: [الهوية والقطاع] →
  // [الملكية والمتابعة] → [القالب والتفعيل]. Each step offers [السابق] [حفظ
  // مسودة] [التالي]; only the last step's [تفعيل الشركة] writes the record.
  // Deck slide 52: "الحفظ لا ينشئ أرصدة أو استثمارًا أو مستخدمين بأرقام
  // افتراضية" -- a draft invents no balance, investment or user.
  var CO_WIZ_STEPS = [
    { ar: "الهوية والقطاع", en: "Identity & sector" },
    { ar: "الملكية والمتابعة", en: "Ownership & monitoring" },
    { ar: "القالب والتفعيل", en: "Template & activation" },
  ];
  // Slide 51 names the status set verbatim: "إعداد / نشطة / معلقة / مؤرشفة".
  var CO_WIZ_STATUSES = [
    { value: "setup", ar: "إعداد", en: "Setup" },
    { value: "active", ar: "نشطة", en: "Active" },
    { value: "inactive", ar: "معلقة", en: "Inactive" },
    { value: "archived", ar: "مؤرشفة", en: "Archived" },
  ];
  var CO_WIZ_LANGS = [
    { value: "ar", ar: "العربية", en: "Arabic" },
    { value: "en", ar: "English", en: "English" },
    { value: "both", ar: "ثنائية", en: "Bilingual" },
  ];
  var CO_WIZ_SCOPES = [
    { value: "single_company", ar: "شركة واحدة", en: "One company" },
    { value: "linked_roles", ar: "أدوار مرتبطة", en: "Linked roles" },
  ];
  var CO_WIZ_CURRENCIES = ["SAR", "AED", "QAR", "USD", "EUR", "KWD", "BHD", "OMR"];
  // The right-hand rail notes, verbatim and per step: slide 50 carries the
  // first pair, slide 51 the second, slide 52 the last three.
  var CO_WIZ_RAIL = [
    [
      { ar: "جميع القيم هنا وصف للحقول", en: "All values here describe the fields" },
      { ar: "لا شركة فعلية منشأة", en: "No company is actually created" },
    ],
    [
      { ar: "لا تمنح الملكية صلاحية تقنية تلقائية", en: "Ownership grants no automatic technical access" },
      { ar: "لا يستبدل الملف تسجيل الشركة رسميًا", en: "The file does not replace official registration" },
    ],
    [
      { ar: "ينشأ ملف الشركة ومعرف ثابت", en: "The company file and a stable id are created" },
      { ar: "تنشأ مسودات الفترات فقط", en: "Only period drafts are created" },
      { ar: "دعوات المستخدمين لا تمنح وصولًا حتى التفعيل", en: "User invitations grant no access until activation" },
    ],
  ];

  function coWizL(ar, en) { return STATE.lang === "ar" ? ar : en; }

  function coMonthOptions() {
    return AR_MONTHS.map(function (m, i) {
      return { value: i + 1, label: m + " / " + EN_MONTHS[i] };
    });
  }

  function companyWizardPanel(rows, users) {
    var sectors = STATE.sectors || [];
    var sectorOptions = sectors.length
      ? sectors.map(function (s) {
          return { value: s.code, label: s.name_ar + " / " + (s.name_en || s.name_ar) };
        })
      : Object.keys(SECTOR).map(function (k) {
          return { value: k, label: SECTOR[k].ar + " / " + SECTOR[k].en };
        });
    var managers = users.length
      ? users
      : [{ value: "", label: coWizL("لا مستخدمون متاحون", "No users available") }];
    var railNotes = CO_WIZ_RAIL[0].map(function (n) {
      return '<li class="co-wiz-railnote">' + dual(n.ar, n.en) + "</li>";
    }).join("");
    var step1 =
      '<fieldset class="co-wiz-pane" data-pane="1">' +
      field("الاسم القانوني *", "Legal name *", textInput("cwNameAr", ""), "نص مطابق للتسجيل", "Text matching the registration") +
      field("الاسم التجاري", "Trade name", textInput("cwTradeName", ""), "نص اختياري", "Optional text") +
      field("الدولة *", "Country *", textInput("cwCountry", ""), "قائمة الدول", "Country list") +
      field("رقم التسجيل *", "Registration number *", textInput("cwRegistration", ""), "نص، فريد داخل الدولة", "Unique within the country") +
      field("النشاط *", "Activity *", textInput("cwActivity", ""), "وصف النشاط", "Activity description") +
      field("القطاع *", "Sector *", selectInput("cwSector", sectorOptions, ""), "قطاع من قائمة القطاعات المعتمدة", "A sector from the approved catalogue") +
      field("العملة الأساسية *", "Base currency *", selectInput(
        "cwCurrency",
        CO_WIZ_CURRENCIES.map(function (c) { return { value: c, label: c }; }),
        "SAR"
      ), "قائمة العملات", "Currency list") +
      field("السنة المالية *", "Fiscal year *",
        '<div class="co-wiz-inline">' +
        selectInput("cwFyStart", coMonthOptions(), 1) +
        selectInput("cwFyEnd", coMonthOptions(), 12) +
        "</div>",
        "شهر ويوم بداية ونهاية", "Start and end month/day") +
      "</fieldset>";
    var step2 =
      '<fieldset class="co-wiz-pane" data-pane="2" hidden>' +
      field("نسبة ملكية القابضة *", "Holding ownership % *", textInput("cwOwnership", "100"), "رقم من 0 إلى 100", "A number from 0 to 100") +
      field("رأس المال *", "Capital *", textInput("cwCapital", ""), "مبلغ بعملة الجهة", "Amount in the entity currency") +
      field("تاريخ الاستثمار", "Investment date", dateInput("cwInvestDate", ""), "تاريخ عند وجود استثمار", "Date when an investment exists") +
      field("مدير الشركة *", "Company manager *", selectInput("cwManager", managers, ""), "مستخدم مدعو أو نشط", "Invited or active user") +
      field("بدء المتابعة *", "Monitoring start *", dateInput("cwTracking", ""), "تاريخ يحدد أول فترة", "Date setting the first period") +
      field("حالة الشركة *", "Company status *", selectInput(
        "cwStatus",
        CO_WIZ_STATUSES.map(function (s) { return { value: s.value, label: coWizL(s.ar, s.en) }; }),
        "setup"
      ), "إعداد / نشطة / معلقة / مؤرشفة", "Setup / active / inactive / archived") +
      field(
        "المستخدمون المرتبطون",
        "Linked users",
        '<select class="av-input" id="cwLinkedUsers" multiple size="4">' +
        managers.map(function (m) {
          return '<option value="' + m.value + '">' + escapeHtml(m.label) + "</option>";
        }).join("") +
        "</select>",
        "اختيار متعدد مع الدور والنطاق",
        "Multi-select with role and scope"
      ) +
      field("اللغة *", "Language *", selectInput(
        "cwLanguage",
        CO_WIZ_LANGS.map(function (l) { return { value: l.value, label: coWizL(l.ar, l.en) }; }),
        "ar"
      ), "العربية / English / ثنائية", "Arabic / English / bilingual") +
      "</fieldset>";
    var step3 =
      '<fieldset class="co-wiz-pane" data-pane="3" hidden>' +
      field("نموذج القطاع *", "Sector template *", selectInput("cwTemplate", sectorOptions, ""), "نسخة منشورة من قالب القطاع", "A published copy of the sector template") +
      field("المؤشرات المختارة *", "Selected indicators *", textInput(
        "cwKpis",
        coWizL("المؤشرات المشتركة + مؤشرات القطاع", "Shared + sector indicators")
      ), "مؤشرات مشتركة + القطاع", "Shared indicators + sector") +
      field("مستوى الوصول *", "Access level *", selectInput(
        "cwAccessScope",
        CO_WIZ_SCOPES.map(function (s) { return { value: s.value, label: coWizL(s.ar, s.en) }; }),
        "single_company"
      ), "شركة واحدة / أدوار مرتبطة", "One company / linked roles") +
      field("مراجعة الإعداد", "Setup review", '<div class="co-wiz-review" id="cwReview"></div>',
        "الدولة والعملة والمدير والدورية", "Country, currency, manager and periodicity") +
      field("تاريخ نفاذ القالب *", "Template effective date *", dateInput("cwTemplateDate", ""), "لا يسبق بدء المتابعة", "Cannot precede the monitoring start") +
      field("إقرار المراجعة *", "Review confirmation *",
        '<label class="co-wiz-confirm"><input type="checkbox" id="cwConfirm"></label>',
        "تأكيد المالك قبل التفعيل", "Owner confirmation before activation") +
      "</fieldset>";
    var actions =
      '<div class="co-wiz-actions">' +
      '<button type="button" class="btn-outline" data-wiz="prev" hidden>' + dual("السابق", "Previous") + "</button>" +
      '<button type="button" class="btn-outline" data-wiz="draft">' + dual("حفظ مسودة", "Save draft") + "</button>" +
      '<button type="button" class="btn-solid" data-wiz="next">' + dual("التالي", "Next") + "</button>" +
      '<button type="button" class="btn-solid" data-wiz="activate" hidden>' + dual("تفعيل الشركة", "Activate company") + "</button>" +
      "</div>";
    var footer =
      '<p class="co-wiz-footer">' +
      dual(
        "الحفظ لا ينشئ أرصدة أو استثمارًا أو مستخدمين بأرقام افتراضية. تنسخ تعريفات القالب والمؤشرات بإصدار مؤرخ، وتطبق صلاحيات الشركة المختارة.",
        "Saving invents no balances, investment or users. Template and indicator definitions are copied with a dated version, and the selected company's permissions apply."
      ) +
      "</p>";
    return adminPanel(
      "معالج إضافة شركة",
      "Company setup wizard",
      '<div class="co-wiz" id="companyWizard">' +
        '<div class="co-wiz-body">' +
          '<aside class="co-wiz-rail">' +
            '<div class="co-wiz-railcard">' +
              '<h4>' + dual("ملف الجهة", "Entity file") + "</h4>" +
              '<p class="co-wiz-railstep" id="cwRailStep">' +
                dual("الخطوة 1 من 3", "Step 1 of 3") + "</p>" +
              '<p class="co-wiz-railname" id="cwRailName">' +
                dual(CO_WIZ_STEPS[0].ar, CO_WIZ_STEPS[0].en) + "</p>" +
            "</div>" +
            '<ul class="co-wiz-railnotes" id="cwRailNotes">' + railNotes + "</ul>" +
          "</aside>" +
          '<form class="av-form co-wiz-form" id="companyWizardForm" novalidate>' +
          step1 + step2 + step3 + actions +
          "</form>" +
        "</div>" +
        footer +
      "</div>"
    );
  }

  function bindCompanyWizard(rows, nodes) {
    var root = byId("companyWizard");
    if (!root) return;
    var state = { step: 1, draftId: null, code: null };
    nodes = nodes || [];
    var nextBtn = root.querySelector('[data-wiz="next"]');
    var prevBtn = root.querySelector('[data-wiz="prev"]');
    var draftBtn = root.querySelector('[data-wiz="draft"]');
    var actBtn = root.querySelector('[data-wiz="activate"]');

    function draftCode() {
      if (!state.code) state.code = "CW-" + Date.now().toString(36).toUpperCase();
      return state.code;
    }

    function collect() {
      var own = valOf("cwOwnership");
      var cap = valOf("cwCapital");
      var mgr = valOf("cwManager");
      var linkedSel = byId("cwLinkedUsers");
      var linked = linkedSel
        ? Array.prototype.slice.call(linkedSel.selectedOptions).map(function (o) { return Number(o.value); })
        : [];
      return {
        name_ar: (valOf("cwNameAr") || "").trim(),
        name_en: (valOf("cwNameEn") || "").trim() || null,
        trade_name_ar: (valOf("cwTradeName") || "").trim() || null,
        country: (valOf("cwCountry") || "").trim() || null,
        commercial_registration: (valOf("cwRegistration") || "").trim() || null,
        activity: (valOf("cwActivity") || "").trim() || null,
        sector: valOf("cwSector") || "",
        currency: valOf("cwCurrency") || "SAR",
        fiscal_year_start_month: valOf("cwFyStart") ? Number(valOf("cwFyStart")) : null,
        fiscal_year_end_month: valOf("cwFyEnd") ? Number(valOf("cwFyEnd")) : null,
        ownership_pct: own === "" ? null : own,
        capital_amount: cap === "" ? null : cap,
        investment_date: valOf("cwInvestDate") || null,
        manager_user_id: mgr || null,
        linked_user_ids: linked,
        tracking_start_date: valOf("cwTracking") || null,
        status: valOf("cwStatus") || "active",
        default_language: valOf("cwLanguage") || "ar",
        sector_template: valOf("cwTemplate") || "",
        template_effective_from: valOf("cwTemplateDate") || null,
        access_scope: valOf("cwAccessScope") || "",
        confirmed: !!(byId("cwConfirm") && byId("cwConfirm").checked),
      };
    }

    function renderReview() {
      var d = collect();
      var sector = sectorLabel(d.sector);
      var mgr = byId("cwManager");
      var mgrLabel = mgr && mgr.selectedIndex >= 0 ? mgr.options[mgr.selectedIndex].text : "—";
      var out = [
        [dual("الدولة والعملة", "Country & currency"), (d.country || "—") + " · " + d.currency],
        [dual("المدير", "Manager"), mgrLabel],
        [dual("الدورية (السنة المالية)", "Fiscal year"), (d.fiscal_year_start_month || "—") + " → " + (d.fiscal_year_end_month || "—")],
        [dual("القطاع", "Sector"), coWizL(sector.ar, sector.en)],
        [dual("رأس المال", "Capital"), d.capital_amount == null ? "—" : d.capital_amount],
        [dual("نسبة ملكية القابضة", "Holding ownership"), d.ownership_pct == null ? "—" : d.ownership_pct + "%"],
        [dual("تاريخ نفاذ القالب", "Template effective"), d.template_effective_from || "—"],
      ];
      byId("cwReview").innerHTML = out.map(function (r) {
        return '<div class="co-wiz-rrow"><span>' + r[0] + "</span><b>" + escapeHtml(String(r[1])) + "</b></div>";
      }).join("");
    }

    function show(step) {
      state.step = step;
      root.querySelectorAll(".co-wiz-pane").forEach(function (p) {
        p.hidden = Number(p.getAttribute("data-pane")) !== step;
      });
      // Deck slides 50-52: the right-hand rail carries "الخطوة N من 3" and the
      // step's own name; it is the only step indicator in the deck.
      var railStep = byId("cwRailStep");
      var railName = byId("cwRailName");
      var s = CO_WIZ_STEPS[step - 1] || CO_WIZ_STEPS[0];
      if (railStep) {
        railStep.innerHTML = dual(
          "الخطوة " + step + " من 3",
          "Step " + step + " of 3"
        );
      }
      if (railName) railName.innerHTML = dual(s.ar, s.en);
      // Each slide in the deck shows only its own notes on the rail.
      var notesHost = byId("cwRailNotes");
      if (notesHost) {
        notesHost.innerHTML = (CO_WIZ_RAIL[step - 1] || []).map(function (n) {
          return '<li class="co-wiz-railnote">' + dual(n.ar, n.en) + "</li>";
        }).join("");
      }
      prevBtn.hidden = step === 1;
      nextBtn.hidden = step === 3;
      actBtn.hidden = step !== 3;
      if (step === 3) renderReview();
    }

    function missingFor(step) {
      var d = collect();
      var need = [];
      if (step === 1) {
        if (!d.name_ar) need.push(coWizL("الاسم القانوني", "legal name"));
        if (!d.country) need.push(coWizL("الدولة", "country"));
        if (!d.commercial_registration) need.push(coWizL("رقم التسجيل", "registration number"));
        if (!d.activity) need.push(coWizL("النشاط", "activity"));
        if (!d.sector) need.push(coWizL("القطاع", "sector"));
      } else if (step === 2) {
        if (d.ownership_pct == null) need.push(coWizL("نسبة الملكية", "ownership %"));
        if (d.capital_amount == null) need.push(coWizL("رأس المال", "capital"));
        if (!d.manager_user_id) need.push(coWizL("مدير الشركة", "company manager"));
        if (!d.tracking_start_date) need.push(coWizL("بدء المتابعة", "monitoring start"));
        if (!d.status) need.push(coWizL("حالة الشركة", "company status"));
        if (!d.default_language) need.push(coWizL("اللغة", "language"));
      } else {
        if (!d.sector_template) need.push(coWizL("نموذج القطاع", "sector template"));
        if (!d.template_effective_from) need.push(coWizL("تاريخ نفاذ القالب", "template effective date"));
        if (!d.access_scope) need.push(coWizL("مستوى الوصول", "access level"));
        if (!d.confirmed) need.push(coWizL("إقرار المراجعة", "review confirmation"));
        // Slide 52: "تاريخ نفاذ القالب *: لا يسبق بدء المتابعة".
        if (d.template_effective_from && d.tracking_start_date &&
            d.template_effective_from < d.tracking_start_date) {
          need.push(coWizL("تاريخ نفاذ القالب ≥ بدء المتابعة", "template date ≥ monitoring start"));
        }
      }
      return need;
    }

    function checkStep(step) {
      var need = missingFor(step);
      if (need.length) {
        toast(coWizL("أكمل الحقول الإلزامية: ", "Complete required fields: ") + need.join(coWizL("، ", ", ")), "warn");
        return false;
      }
      return true;
    }

    function draftPayload(d) {
      var payload = {
        code: draftCode(),
        name_ar: d.name_ar,
        name_en: d.name_en,
        trade_name_ar: d.trade_name_ar,
        country: d.country,
        commercial_registration: d.commercial_registration,
        activity: d.activity,
        sector: d.sector,
        currency: d.currency,
        fiscal_year_start_month: d.fiscal_year_start_month,
        fiscal_year_end_month: d.fiscal_year_end_month,
        capital_amount: d.capital_amount,
        tracking_start_date: d.tracking_start_date,
        default_language: d.default_language,
        template_effective_from: d.template_effective_from,
        access_scope: d.access_scope,
      };
      if (d.status) payload.status = d.status;
      return payload;
    }

    // Step 3's activation links the manager and the ownership stake the deck
    // names, plus any extra linked users from step 2 (slide 51: "المستخدمون
    // المرتبطون"). Each write is gated on the permission its endpoint enforces,
    // so no call is made that would 403, and every failure is surfaced not
    // swallowed. Slide 52: "دعوات المستخدمين لا تمنح وصولًا حتى التفعيل" -- this
    // runs only on activation, never on draft save.
    function applyWizardLinks(companyId, d) {
      if (!companyId) return Promise.resolve();
      var tasks = [];
      var seen = {};
      var grants = [];
      if (d.manager_user_id) {
        seen[d.manager_user_id] = true;
        grants.push({ id: d.manager_user_id, primary: true });
      }
      (d.linked_user_ids || []).forEach(function (uid) {
        if (uid && !seen[uid]) {
          seen[uid] = true;
          grants.push({ id: uid, primary: false });
        }
      });
      if (has("company.access.manage")) {
        grants.forEach(function (g) {
          tasks.push(post("/api/v1/users/" + g.id + "/company-access", {
            company_id: companyId,
            can_read: true,
            can_write: true,
            is_primary: g.primary,
          }));
        });
      }
      var holding = groupOwnerCompany(rows, nodes);
      if (d.ownership_pct != null && holding && has("ownership.manage")) {
        tasks.push(post("/api/v1/admin/ownerships", {
          owned_company_id: companyId,
          owner_company_id: holding.id,
          ownership_percentage: d.ownership_pct,
          effective_from: d.tracking_start_date || new Date().toISOString().slice(0, 10),
        }));
      }
      return Promise.all(tasks);
    }

    // Deck slide 51 names only "نسبة ملكية القابضة" -- the holding is implicit.
    // The data model splits owner from percentage, so resolve the group root:
    // an explicit holding-type company, else the root of the ownership tree
    // (a parent-less node that owns children), else the first company. The tree
    // node carries the parent edge that the company row does not.
    function groupOwnerCompany(rows, nodes) {
      var explicit = rows.filter(function (c) { return c.company_type === "holding"; })[0];
      if (explicit) return explicit;
      var parentIds = {};
      (nodes || []).forEach(function (n) {
        if (n.parent_company_id) parentIds[n.parent_company_id] = true;
      });
      var root = (nodes || []).filter(function (n) {
        return !n.parent_company_id && parentIds[n.company_id];
      })[0];
      if (root) {
        var match = rows.filter(function (c) { return c.id === root.company_id; })[0];
        if (match) return match;
      }
      return rows[0] || null;
    }

    function saveDraft() {
      var d = collect();
      if (!d.name_ar || !d.sector) {
        toast(coWizL("يتطلب حفظ المسودة الاسم القانوني والقطاع.", "A draft needs the legal name and sector."), "warn");
        return;
      }
      busy(draftBtn, true);
      var req = state.draftId
        ? patch("/api/v1/companies/" + state.draftId, draftPayload(d))
        : post("/api/v1/companies", draftPayload(d)).then(function (row) {
            state.draftId = row.id;
            return row;
          });
      req.then(function () {
        STATE.loaded.companies = false;
        toast(dual("تم حفظ المسودة.", "Draft saved."), "ok");
        busy(draftBtn, false);
      }).catch(function (err) { adminError(err); busy(draftBtn, false); });
    }

    function activate() {
      if (!checkStep(3)) return;
      var d = collect();
      busy(actBtn, true);
      var req = state.draftId
        ? patch("/api/v1/companies/" + state.draftId, draftPayload(d)).then(function () {
            return { id: state.draftId };
          })
        : post("/api/v1/companies", draftPayload(d));
      req.then(function (row) {
        var companyId = row && row.id ? row.id : state.draftId;
        return applyWizardLinks(companyId, d);
      }).then(function () {
        STATE.loaded.companies = false;
        toast(dual("تم تفعيل الشركة.", "Company activated."), "ok");
        return renderAdminCompanies();
      }).catch(function (err) { adminError(err); busy(actBtn, false); });
    }

    nextBtn.addEventListener("click", function () {
      if (!checkStep(state.step)) return;
      if (state.step < 3) show(state.step + 1);
    });
    prevBtn.addEventListener("click", function () {
      if (state.step > 1) show(state.step - 1);
    });
    draftBtn.addEventListener("click", function () { saveDraft(); });
    actBtn.addEventListener("click", function () { activate(); });
    show(1);
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
    return Promise.all([ensureCompanies(), softGet("/api/v1/admin/departments")]).then(function (res) {
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
    return softGet("/api/v1/admin/sectors").then(function (sectors) {
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
      softGet("/api/v1/admin/positions"),
      softGet("/api/v1/admin/departments"),
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
  // Slide 136 fixes the user list's filters (company, owner, type, status,
  // date, version) and search fields (name / email / role; record id / action).
  // The directory is server-paged, so the search and role/status selects map to
  // the API's own ``search`` / ``role_code`` / ``is_active`` parameters rather
  // than filtering a client-side page. Authorization is unchanged.
  function adminUsersPageState() {
    return STATE.adminUsers || (STATE.adminUsers = {
      limit: 25, offset: 0, total: 0, search: "", role_code: "", is_active: "",
    });
  }

  function adminUserFiltersHtml(page, roles) {
    var roleOpts = '<option value="">' + escAttr(STATE.lang === "ar" ? "كل الأدوار" : "All roles") + "</option>";
    roles.forEach(function (r) {
      roleOpts += '<option value="' + escAttr(r.code) + '"' + (r.code === page.role_code ? " selected" : "") + ">" +
        escapeHtml(STATE.lang === "ar" ? r.name_ar : r.name_en) + "</option>";
    });
    var statusOpts = [
      { value: "", ar: "كل الحالات", en: "All statuses" },
      { value: "true", ar: "نشط", en: "Active" },
      { value: "false", ar: "موقوف", en: "Inactive" },
    ].map(function (o) {
      return '<option value="' + o.value + '"' + (o.value === page.is_active ? " selected" : "") + ">" +
        escAttr(STATE.lang === "ar" ? o.ar : o.en) + "</option>";
    }).join("");
    var sizes = PAGE_SIZES.map(function (s) {
      return '<option value="' + s + '"' + (s === page.limit ? " selected" : "") + ">" +
        plainNum(s) + "</option>";
    }).join("");
    return (
      '<div class="list-filters" id="listFilter-adminUsers">' +
      '<label class="lf-field lf-search">' +
      '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.2-3.2"/></svg>' +
      '<input class="av-input" id="adminUsersSearch" value="' + escAttr(page.search) + '" placeholder="' +
      escAttr(STATE.lang === "ar" ? "الاسم / البريد / الدور" : "Name / email / role") + '" aria-label="' +
      escAttr(STATE.lang === "ar" ? "بحث" : "Search") + '"></label>' +
      '<select class="av-select lf-select" id="adminUsersRole" aria-label="' + escAttr(STATE.lang === "ar" ? "الدور" : "Role") + '">' + roleOpts + "</select>" +
      '<select class="av-select lf-select" id="adminUsersStatus" aria-label="' + escAttr(STATE.lang === "ar" ? "الحالة" : "Status") + '">' + statusOpts + "</select>" +
      '<label class="pager-size">' + dual("لكل صفحة", "Per page") +
      '<select class="av-select" id="adminUsersSize">' + sizes + "</select></label>" +
      '<div class="lf-actions">' +
      '<button type="button" class="lf-btn primary" data-admin-action="users-apply">' + dual("تطبيق", "Apply") + "</button>" +
      '<button type="button" class="lf-btn" data-admin-action="users-clear">' + dual("مسح", "Clear") + "</button>" +
      "</div></div>"
    );
  }

  function renderAdminUsers() {
    var host = byId("adminContent");
    var page = adminUsersPageState();
    var query = "/api/v1/admin/users?limit=" + page.limit + "&offset=" + page.offset;
    if (page.search) query += "&search=" + encodeURIComponent(page.search);
    if (page.role_code) query += "&role_code=" + encodeURIComponent(page.role_code);
    if (page.is_active) query += "&is_active=" + encodeURIComponent(page.is_active);
    return Promise.all([
      get(query),
      softGet("/api/v1/admin/roles"),
      ensureCompanies(),
      softGet("/api/v1/admin/departments"),
      softGet("/api/v1/admin/users?limit=1&is_active=true"),
      softGet("/api/v1/admin/users?limit=1&is_active=false"),
      softGet("/api/v1/admin/audit-logs?limit=1"),
    ]).then(function (res) {
      var data = res[0];
      var roles = res[1];
      var departments = res[3];
      var activeUsers = res[4] && typeof res[4].total === "number" ? res[4].total : null;
      var pendingUsers = res[5] && typeof res[5].total === "number" ? res[5].total : null;
      var workLog = res[6] && typeof res[6].total === "number" ? res[6].total : null;
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
            '<button class="btn-outline" data-admin-action="reset-user-password" data-id="' + u.id + '">' + dual("تعيين كلمة مرور", "Set password") + "</button>" +
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

      var pages = Math.max(1, Math.ceil(page.total / page.limit));
      var curPage = Math.floor(page.offset / page.limit) + 1;
      var pager =
        '<div class="av-pager">' +
        '<button class="btn-outline" data-admin-action="users-prev"' + (page.offset === 0 ? " disabled" : "") + ">" + dual("السابق", "Previous") + "</button>" +
        '<span class="av-pager-info">' + plainNum(page.offset + 1) + " – " + plainNum(Math.min(page.offset + page.limit, page.total)) + " / " + plainNum(page.total) +
        " · " + plainNum(curPage) + " / " + plainNum(pages) + "</span>" +
        '<button class="btn-outline" data-admin-action="users-next"' + (page.offset + page.limit >= page.total ? " disabled" : "") + ">" + dual("التالي", "Next") + "</button></div>";

      var addAction = has("user.manage")
        ? '<div class="av-actions"><button class="btn-solid" data-admin-action="user-create">' +
          dual("إضافة مستخدم", "Add user") + "</button></div>"
        : "";
      // Deck slide 37 draws a four-tile summary above the user table. Each tile
      // is a live count, never a hard-coded figure; a metric the caller cannot
      // read (e.g. the work log without audit.read) shows "—" rather than 0.
      var customRoles = roles.filter(function (r) { return !r.is_system; }).length;
      var statTile = function (ar, en, v) {
        return (
          '<div class="av-panel"><h3>' + dual(ar, en) + "</h3>" +
          '<div class="kpi-val num" style="font-size:22px">' +
          (v === null ? "—" : plainNum(v)) + "</div></div>"
        );
      };
      var stats =
        '<div class="av-grid cols-4" style="margin-bottom:12px">' +
        statTile("المستخدمون النشطون", "Active users", activeUsers) +
        statTile("الدعوات المعلقة", "Pending invites", pendingUsers) +
        statTile("أدوار مخصصة", "Custom roles", customRoles) +
        statTile("سجل العمل", "Work log", workLog) +
        "</div>";
      host.innerHTML = adminPanel("المستخدمون", "Users", addAction + adminUserFiltersHtml(page, roles) + stats + (rows ? '<div class="av-list">' + rows + "</div>" : '<p class="av-empty">' + dual("لا يوجد مستخدمون.", "No users.") + "</p>") + pager);
    });
  }

  // Deck slide 37 [إضافة مستخدم]: the owner names the role and the data scope.
  // The same rule the POST /api/v1/users endpoint enforces is mirrored here:
  // the role is required, the password is at least 8 characters, and company
  // access is granted only for the companies ticked.
  function openCreateUserForm() {
    return Promise.all([softGet("/api/v1/admin/roles"), ensureCompanies()]).then(function (res) {
      var roles = res[0] || [];
      var companies = res[1] || [];
      var roleOptions = roles.map(function (r) {
        return { value: r.code, label: STATE.lang === "ar" ? r.name_ar : r.name_en };
      });
      var companyChecks = companies.length
        ? companies.map(function (c) {
            return '<label class="av-check"><input type="checkbox" class="cuCompany" value="' + c.id + '"> ' +
              escapeHtml(STATE.lang === "ar" ? c.name_ar : (c.name_en || c.name_ar)) + "</label>";
          }).join("")
        : '<p class="hint">' + dual("لا توجد شركات متاحة.", "No companies available.") + "</p>";
      openModal({
        title: dual("إضافة مستخدم", "Add user"),
        wide: true,
        body:
          '<div class="av-form av-grid cols-2">' +
          field("الاسم (عربي)", "Name (AR)", textInput("cuNameAr", "", "")) +
          field("الاسم (إنجليزي)", "Name (EN)", textInput("cuNameEn", "", "")) +
          field("البريد الإلكتروني", "Email", textInput("cuEmail", "", "name@example.com")) +
          field("الدور", "Role", selectInput("cuRole", roleOptions, roleOptions.length ? roleOptions[0].value : "")) +
          field("كلمة المرور", "Password", '<input class="av-input" id="cuPassword" type="password" autocomplete="new-password">') +
          "</div>" +
          field("نطاق الشركات", "Company scope", '<div class="av-checklist">' + companyChecks + "</div>"),
        footer:
          '<button class="btn-outline" id="cuCancel">' + dual("إلغاء", "Cancel") + "</button>" +
          '<button class="btn-solid" id="cuSave">' + dual("حفظ", "Save") + "</button>",
        onMount: function (root) {
          root.querySelector("#cuCancel").addEventListener("click", closeModal);
          root.querySelector("#cuSave").addEventListener("click", function () {
            var btn = this;
            var email = root.querySelector("#cuEmail").value.trim();
            var password = root.querySelector("#cuPassword").value;
            var nameAr = root.querySelector("#cuNameAr").value.trim();
            var nameEn = root.querySelector("#cuNameEn").value.trim();
            var roleCode = root.querySelector("#cuRole").value;
            if (!nameAr) {
              toast(STATE.lang === "ar" ? "الاسم بالعربي مطلوب." : "The Arabic name is required.", "err");
              return;
            }
            if (!email) {
              toast(STATE.lang === "ar" ? "البريد الإلكتروني مطلوب." : "Email is required.", "err");
              return;
            }
            if (password.length < 8) {
              toast(STATE.lang === "ar" ? "كلمة المرور 8 أحرف على الأقل." : "Password must be at least 8 characters.", "err");
              return;
            }
            var companyIds = Array.prototype.slice
              .call(root.querySelectorAll(".cuCompany:checked"))
              .map(function (c) { return parseInt(c.value, 10); });
            busy(btn, true);
            post("/api/v1/users", {
              email: email,
              password: password,
              full_name_ar: nameAr,
              full_name_en: nameEn || null,
              role_code: roleCode,
              company_ids: companyIds,
            })
              .then(function () {
                toast(STATE.lang === "ar" ? "تمت إضافة المستخدم." : "User added.", "ok");
                closeModal();
                return renderAdminUsers();
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

  // Owner/administrator sets a temporary password for a locked-out account
  // (deck slide 37/38: user management). The actor never sees the old password;
  // the target can change it again from their own profile block.
  function openAdminSetPasswordForm(userId) {
    openModal({
      title: dual("تعيين كلمة مرور", "Set password"),
      body:
        '<div class="av-field"><label>' +
        dual("كلمة المرور المؤقتة الجديدة", "New temporary password") +
        '</label><input class="av-input" type="password" id="spNew" style="width:100%"></div>' +
        '<div class="av-field"><label>' +
        dual("تأكيد كلمة المرور", "Confirm password") +
        '</label><input class="av-input" type="password" id="spConfirm" style="width:100%"></div>' +
        '<p class="note-block">' +
        dual("٨ أحرف على الأقل. سلّمها للمستخدم ليقوم بتغييرها.", "At least 8 characters. Hand it to the user to change.") +
        "</p>",
      footer:
        '<button class="btn-outline" id="spCancel">' + dual("إلغاء", "Cancel") + "</button>" +
        '<button class="btn-solid" id="spSave">' + dual("حفظ", "Save") + "</button>",
      onMount: function (root) {
        root.querySelector("#spCancel").addEventListener("click", closeModal);
        root.querySelector("#spSave").addEventListener("click", function () {
          var btn = this;
          var next = root.querySelector("#spNew").value;
          var confirm = root.querySelector("#spConfirm").value;
          if (!next || next.length < 8) {
            toast(dual("كلمة المرور ٨ أحرف على الأقل.", "Password must be at least 8 characters."), "warn");
            return;
          }
          if (next !== confirm) {
            toast(dual("كلمتا المرور غير متطابقتين.", "The passwords do not match."), "warn");
            return;
          }
          busy(btn, true);
          post("/api/v1/users/" + userId + "/password", { new_password: next })
            .then(function () {
              toast(dual("تم تعيين كلمة المرور.", "Password set."), "ok");
              closeModal();
            })
            .catch(function (err) {
              toast(errText(err), "err");
              busy(btn, false);
            });
        });
      },
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
    return softGet("/api/v1/admin/motivation-texts?include_inactive=true")
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
      softGet("/api/v1/website/pages"),
      softGet("/api/v1/website/slides"),
      softGet("/api/v1/website/companies"),
      softGet("/api/v1/website/media"),
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
    var page = STATE.adminAudit || (STATE.adminAudit = { limit: 40, offset: 0, total: 0, action: "", entity_type: "", company_id: "" });
    var query = "/api/v1/admin/audit-logs?limit=" + page.limit + "&offset=" + page.offset;
    if (page.action) query += "&action=" + encodeURIComponent(page.action);
    if (page.entity_type) query += "&entity_type=" + encodeURIComponent(page.entity_type);
    if (page.company_id) query += "&company_id=" + encodeURIComponent(page.company_id);
    return Promise.all([ensureCompanies(), get(query)]).then(function (res) {
      var data = res[1];
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
      // Slide 136 "المستخدمون / النشاط": search plus company, type, status and
      // date filters, with the deck's apply / save / clear / export cluster.
      // The audit read gate is unchanged; the export is gated on analytics.export
      // exactly as the deck's "عند سماح التصدير" requires.
      var companyOpts = '<option value="">' + escAttr(STATE.lang === "ar" ? "كل الشركات" : "All companies") + "</option>" +
        (STATE.companies || []).map(function (c) {
          return '<option value="' + escAttr(c.id) + '"' + (String(c.id) === String(page.company_id) ? " selected" : "") + ">" +
            escapeHtml(STATE.lang === "ar" ? c.name_ar : c.name_en || c.name_ar) + "</option>";
        }).join("");
      var saved = savedFilters("audit");
      var savedSel = saved.length
        ? '<select class="av-select lf-select" id="auditSaved" aria-label="' + escAttr(STATE.lang === "ar" ? "مرشحاتي المحفوظة" : "My saved filters") + '">' +
          '<option value="">' + escAttr(STATE.lang === "ar" ? "مرشحاتي المحفوظة" : "My saved filters") + "</option>" +
          saved.map(function (s) { return '<option value="' + escAttr(s.name) + '">' + escapeHtml(s.name) + "</option>"; }).join("") +
          "</select>"
        : "";
      var exportBtn = has("analytics.export")
        ? '<button type="button" class="lf-btn" id="auditExport">' + dual("تصدير النتائج", "Export results") + "</button>"
        : "";
      var filters =
        '<div class="list-filters" id="listFilter-audit">' +
        '<label class="lf-field lf-search">' +
        '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.2-3.2"/></svg>' +
        '<input class="av-input" id="auditAction" placeholder="' + escAttr(STATE.lang === "ar" ? "تصفية بالإجراء (مثال: journal.posted)" : "Filter by action (e.g. journal.posted)") + '" value="' + escAttr(page.action) + '"></label>' +
        '<input class="av-input lf-select" id="auditEntity" placeholder="' + escAttr(STATE.lang === "ar" ? "تصفية بنوع الكيان" : "Filter by entity type") + '" value="' + escAttr(page.entity_type) + '">' +
        '<select class="av-select lf-select" id="auditCompany" aria-label="' + escAttr(STATE.lang === "ar" ? "الشركة" : "Company") + '">' + companyOpts + "</select>" +
        savedSel +
        '<div class="lf-actions">' +
        '<button type="button" class="lf-btn primary" id="auditApply">' + dual("تطبيق", "Apply") + "</button>" +
        '<button type="button" class="lf-btn" id="auditSave">' + dual("حفظ المرشح باسمي", "Save filter") + "</button>" +
        '<button type="button" class="lf-btn" id="auditClear">' + dual("مسح", "Clear") + "</button>" +
        exportBtn +
        "</div></div>";
      host.innerHTML = adminPanel("سجل النشاط", "Audit trail", filters + (rows ? '<div class="av-list">' + rows + "</div>" : '<p class="av-empty">' + dual("لا توجد سجلات.", "No entries.") + "</p>") + pager);
      var apply = byId("auditApply");
      if (apply) {
        apply.addEventListener("click", function () {
          page.action = valOf("auditAction");
          page.entity_type = valOf("auditEntity");
          page.company_id = valOf("auditCompany");
          page.offset = 0;
          renderAdminAudit();
        });
      }
      var clear = byId("auditClear");
      if (clear) {
        clear.addEventListener("click", function () {
          page.action = "";
          page.entity_type = "";
          page.company_id = "";
          page.offset = 0;
          renderAdminAudit();
        });
      }
      var save = byId("auditSave");
      if (save) {
        save.addEventListener("click", function () {
          var values = { action: page.action, entity_type: page.entity_type, company_id: page.company_id };
          if (!values.action && !values.entity_type && !values.company_id) {
            toast(dual("لا يوجد مرشح لحفظه.", "Nothing to save yet."), "err");
            return;
          }
          var name = window.prompt(dual("اسم المرشح:", "Filter name:"),
            dual("مرشح ", "Filter ") + new Date().toLocaleDateString());
          if (!name) return;
          var list = savedFilters("audit").filter(function (s) { return s.name !== name; });
          list.push({ name: name, values: values });
          try { localStorage.setItem("safir.filters.v1.audit", JSON.stringify(list)); } catch (e) { /* storage disabled */ }
          toast(dual("تم حفظ المرشح: " + name, "Filter saved: " + name), "ok");
          renderAdminAudit();
        });
      }
      var savedSelect = byId("auditSaved");
      if (savedSelect) {
        savedSelect.addEventListener("change", function () {
          var found = savedFilters("audit").filter(function (s) { return s.name === savedSelect.value; })[0];
          if (!found) return;
          page.action = found.values.action || "";
          page.entity_type = found.values.entity_type || "";
          page.company_id = found.values.company_id || "";
          page.offset = 0;
          renderAdminAudit();
        });
      }
      var exp = byId("auditExport");
      if (exp) exp.addEventListener("click", function () { exportListCsv("audit", data.items); });
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
        { value: "integer", label: dual("رقم", "Number") },
        { value: "short_text", label: dual("نص/سؤال", "Text / question") },
        { value: "decimal", label: dual("مبلغ", "Amount") },
        { value: "date", label: dual("تاريخ", "Date") },
        { value: "select", label: dual("قائمة", "List") },
        { value: "url", label: dual("رابط خارجي", "External link") },
      ], "short_text")) +
      field("التسمية (عربي)", "Label (AR)", textInput("afLabelAr", "")) +
      field("التسمية (إنجليزي)", "Label (EN)", textInput("afLabelEn", "")) +
      field("إلزامي", "Required", selectInput("afRequired", [
        { value: "0", label: STATE.lang === "ar" ? "لا" : "No" },
        { value: "1", label: STATE.lang === "ar" ? "نعم" : "Yes" },
      ], "0")) +
      field("نطاق الظهور", "Visibility scope", selectInput("afScope", [
        { value: "all", label: dual("الكل", "All") },
        { value: "sector", label: dual("قطاع", "Sector") },
        { value: "company", label: dual("شركة", "Company") },
      ], "all")) +
      field("القطاع", "Sector", textInput("afScopeSector", "", "ph.scopeSector")) +
      '<div class="av-form-actions"><button class="btn-outline" id="afAdd">' +
      dual("إضافة حقل", "Add field") + "</button></div></div>"
    );
  }

  function bindFieldForm(root, formId, done) {
    var btn = root.querySelector("#afAdd");
    if (!btn) return;
    btn.addEventListener("click", function () {
      var scope = root.querySelector("#afScope").value;
      var payload = {
        key: root.querySelector("#afKey").value.trim(),
        field_type: root.querySelector("#afType").value,
        label_ar: root.querySelector("#afLabelAr").value.trim() || root.querySelector("#afKey").value.trim(),
        label_en: root.querySelector("#afLabelEn").value.trim() || root.querySelector("#afKey").value.trim(),
        is_required: root.querySelector("#afRequired").value === "1",
        scope: scope,
      };
      // S07 ``نطاق الظهور``: only send the qualifier the chosen scope needs.
      if (scope === "sector") {
        payload.scope_sector = root.querySelector("#afScopeSector").value.trim();
      } else if (scope === "company") {
        payload.scope_company_id = primaryCompanyId() || null;
      }
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
      softGet("/api/v1/workflows"),
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
      softGet("/api/v1/admin/roles"),
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

  // ---- tab: AI knowledge base (RAG) ----
  // The curated knowledge base and the AI provider/usage monitor. Everything is
  // read from the API: a document is retrievable only once its version is
  // approved, and the usage panel is a counter, never a second copy of a
  // conversation. A role without `ai.knowledge.*` still reaches the provider
  // status if it holds `ai.admin`, so the two panels degrade independently.
  function knowledgeSensitivityLabel(value) {
    var map = {
      public: ["عام", "Public"],
      company: ["الشركة", "Company"],
      holding: ["القابضة", "Holding"],
      confidential: ["سري", "Confidential"],
    };
    var pair = map[value] || [value, value];
    return STATE.lang === "ar" ? pair[0] : pair[1];
  }

  function knowledgeStatusBadge(value) {
    var map = {
      draft: ["مسودة", "Draft", "warn"],
      pending: ["بانتظار المراجعة", "Pending", "warn"],
      approved: ["معتمد", "Approved", "ok"],
      archived: ["مؤرشف", "Archived", "miss"],
    };
    return statusBadgeFromMap(value, map);
  }

  function knowledgeDocumentRow(doc, canWrite, canApprove) {
    var title = STATE.lang === "ar" ? doc.title_ar : doc.title_en || doc.title_ar;
    var acts = "";
    if (canApprove && doc.status !== "archived" && !doc.current_version_id) {
      // A document with no approved version is a draft: its latest version must
      // be approved before any of it can be retrieved.
      acts += '<button class="btn-outline" data-admin-action="knowledge-approve" data-id="' +
        doc.id + '">' + dual("اعتماد الإصدار", "Approve version") + "</button>";
    }
    if (canApprove && doc.status !== "archived") {
      acts += '<button class="btn-outline" data-admin-action="knowledge-archive" data-id="' +
        doc.id + '">' + dual("أرشفة", "Archive") + "</button>";
    }
    if (canWrite) {
      acts += '<button class="btn-outline" data-admin-action="knowledge-newversion" data-id="' +
        doc.id + '">' + dual("إصدار جديد", "New version") + "</button>";
    }
    return (
      '<div class="av-row" style="cursor:default"><div class="grow">' +
      '<div class="t">' + escapeHtml(title) + "</div>" +
      '<div class="s">' + escapeHtml(doc.slug) + " · " +
      dual("الحساسية", "Sensitivity") + ": " + escapeHtml(knowledgeSensitivityLabel(doc.sensitivity)) +
      " · " + dual("الإصدار الحالي", "Current version") + ": " +
      (doc.current_version_id ? "#" + plainNum(doc.current_version_id) : dual("لا يوجد", "None")) +
      "</div></div>" +
      knowledgeStatusBadge(doc.status) + acts + "</div>"
    );
  }

  function renderAdminKnowledge() {
    var host = byId("adminContent");
    var canRead = has("ai.knowledge.read");
    var canWrite = has("ai.knowledge.write");
    var canApprove = has("ai.knowledge.approve");
    var canManage = has("ai.knowledge.manage");
    var canAdmin = has("ai.admin");

    var jobs = [];
    jobs.push(canRead ? softGet("/api/v1/ai/knowledge/categories") : Promise.resolve([]));
    jobs.push(canRead ? softGet("/api/v1/ai/knowledge/documents") : Promise.resolve([]));
    // The proposals list is gated on ai.knowledge.manage, the permission
    // list_proposals enforces -- not on the read permission that made the tab
    // reachable, otherwise a reader-only role gets a 403 in the console.
    jobs.push(canManage ? softGet("/api/v1/ai/knowledge/proposals") : Promise.resolve([]));
    jobs.push(canAdmin ? get("/api/v1/ai/usage").catch(function () { return null; }) : Promise.resolve(null));

    return Promise.all(jobs).then(function (res) {
      var categories = res[0] || [];
      var documents = res[1] || [];
      var proposals = res[2] || [];
      var usage = res[3];
      var panels = [];

      if (canWrite) {
        var catOptions = [{ value: "", label: opt("بدون تصنيف", "No category") }];
        categories.forEach(function (c) {
          catOptions.push({ value: c.id, label: STATE.lang === "ar" ? c.name_ar : c.name_en });
        });
        var companyOptions = [{ value: "", label: opt("القابضة", "Holding") }];
        (STATE.companies || []).forEach(function (c) {
          companyOptions.push({ value: c.id, label: companyName(c) });
        });
        var form = '<form class="av-form av-form-inline" id="knowledgeForm">' +
          field("المعرف", "Slug", textInput("knSlug", "", "ph.knowledgeSlug")) +
          field("العنوان (عربي)", "Title (AR)", textInput("knTitleAr", "")) +
          field("العنوان (إنجليزي)", "Title (EN)", textInput("knTitleEn", "")) +
          field("التصنيف", "Category", selectInput("knCategory", catOptions, "")) +
          field("الشركة", "Company", selectInput("knCompany", companyOptions, "")) +
          field("الحساسية", "Sensitivity", selectInput("knSensitivity", [
            { value: "public", label: opt("عام", "Public") },
            { value: "company", label: opt("الشركة", "Company") },
            { value: "holding", label: opt("القابضة", "Holding") },
            { value: "confidential", label: opt("سري", "Confidential") },
          ], "holding")) +
          field("المحتوى (عربي)", "Body (AR)", textArea("knBodyAr", "", "")) +
          '<div class="av-form-actions"><button class="btn-solid" type="submit">' +
          dual("إضافة مستند", "Add document") + "</button></div></form>";
        panels.push(adminPanel("مستند جديد", "New document", form));
      }

      if (canRead) {
        var list = documents.length
          ? '<div class="av-list">' + documents.map(function (d) {
              return knowledgeDocumentRow(d, canWrite, canApprove);
            }).join("") + "</div>"
          : noticeHtml("لا توجد مستندات في نطاقك.", "No documents in your scope yet.");
        panels.push(adminPanel("المستندات المعتمدة والنشطة", "Documents", list));
      }

      if (canManage) {
        var propList = proposals.length
          ? '<div class="av-list">' + proposals.map(function (p) {
              var acts = p.status === "pending"
                ? '<button class="btn-outline" data-admin-action="knowledge-proposal-approve" data-id="' + p.id + '">' + dual("اعتماد", "Approve") + "</button>" +
                  '<button class="btn-outline" data-admin-action="knowledge-proposal-reject" data-id="' + p.id + '">' + dual("رفض", "Reject") + "</button>"
                : "";
              return (
                '<div class="av-row" style="cursor:default"><div class="grow">' +
                '<div class="t">' + escapeHtml(p.title) + "</div>" +
                '<div class="s">' + escapeHtml(p.rationale || "") + "</div></div>" +
                knowledgeStatusBadge(p.status) + acts + "</div>"
              );
            }).join("") + "</div>"
          : noticeHtml("لا توجد مقترحات تعلّم.", "No learning proposals.");
        panels.push(adminPanel("مقترحات التعلّم", "Learning proposals", propList));
      }

      if (canAdmin && usage) {
        var totals = (usage.usage && usage.usage.totals) || {};
        var provider = '<div class="kv">' +
          kv(dual("المزوّد", "Provider"), escapeHtml(usage.provider)) +
          kv(dual("النموذج", "Model"), escapeHtml(usage.model || "—")) +
          kv(dual("المفتاح مُهيّأ", "API key present"), dual(usage.api_key_present ? "نعم" : "لا", usage.api_key_present ? "yes" : "no")) +
          kv(dual("مجاني موثّق", "Verified free"), dual(usage.verified_free ? "نعم" : "لا", usage.verified_free ? "yes" : "no")) +
          kv(dual("سقف التكلفة (دولار)", "Cost cap (USD)"), plainNum(usage.max_cost_usd)) +
          kv(dual("الطلبات (٢٤س)", "Requests (24h)"), plainNum(totals.requests || 0)) +
          kv(dual("الرموز", "Tokens"), plainNum(totals.tokens || 0)) +
          kv(dual("التكلفة (دولار)", "Cost (USD)"), plainNum(totals.cost_usd || 0)) +
          kv(dual("أخطاء", "Errors"), plainNum(totals.errors || 0)) +
          kv(dual("مرفوض مدفوع", "Rejected (paid)"), plainNum(totals.rejected_paid || 0)) +
          kv(dual("الحد اليومي", "Daily limit"), plainNum(usage.daily_limit) + " / " + plainNum(usage.daily_used)) +
          "</div>";
        var models = (usage.free_models || []).length
          ? '<div class="av-list">' + usage.free_models.slice(0, 8).map(function (m) {
              return '<div class="av-row" style="cursor:default"><div class="grow"><div class="t mono">' +
                escapeHtml(m.id) + "</div><div class=\"s\">" + escapeHtml(m.name || "") + "</div></div></div>";
            }).join("") + "</div>"
          : noticeHtml("لا توجد نماذج مجانية موثّقة.", "No verified free models.");
        panels.push(adminPanel("مزوّد الذكاء الاصطناعي والاستخدام", "AI provider & usage", provider));
        panels.push(adminPanel("النماذج المجانية المتاحة", "Available free models",
          models + (usage.discovery_error ? '<p class="av-empty">' + escapeHtml(usage.discovery_error) + "</p>" : "")));
      }

      if (!panels.length) {
        panels.push(noticeHtml("لا تملك صلاحية عرض قاعدة المعرفة.", "You cannot view the knowledge base."));
      }
      host.className = "av-grid cols-1";
      host.innerHTML = panels.join("");
    }).catch(function (err) {
      host.innerHTML = errorHtml(errText(err));
    });
  }

  // ---- admin event handling ----
  function onAdminClick(e) {
    var el = e.target.closest ? e.target.closest("[data-admin-action]") : null;
    if (!el) return;
    var action = el.getAttribute("data-admin-action");
    var id = el.getAttribute("data-id");

    if (action === "users-prev") { STATE.adminUsers.offset = Math.max(0, STATE.adminUsers.offset - STATE.adminUsers.limit); return renderAdminUsers(); }
    if (action === "users-next") { STATE.adminUsers.offset += STATE.adminUsers.limit; return renderAdminUsers(); }
    if (action === "users-apply") {
      var page = adminUsersPageState();
      var search = byId("adminUsersSearch");
      var roleSel = byId("adminUsersRole");
      var statusSel = byId("adminUsersStatus");
      var sizeSel = byId("adminUsersSize");
      page.search = search ? search.value.trim() : "";
      page.role_code = roleSel ? roleSel.value : "";
      page.is_active = statusSel ? statusSel.value : "";
      if (sizeSel) page.limit = parseInt(sizeSel.value, 10) || 25;
      page.offset = 0;
      return renderAdminUsers();
    }
    if (action === "users-clear") {
      STATE.adminUsers = { limit: 25, offset: 0, total: 0, search: "", role_code: "", is_active: "" };
      return renderAdminUsers();
    }
    if (action === "audit-prev") { STATE.adminAudit.offset = Math.max(0, STATE.adminAudit.offset - STATE.adminAudit.limit); return renderAdminAudit(); }
    if (action === "audit-next") { STATE.adminAudit.offset += STATE.adminAudit.limit; return renderAdminAudit(); }

    if (action === "user-create") return openCreateUserForm();
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

    // ---- AI knowledge base (RAG) ----
    if (action === "knowledge-approve") {
      busy(el, true);
      return get("/api/v1/ai/knowledge/documents/" + id + "/versions").then(function (versions) {
        var latest = (versions || []).slice().sort(function (a, b) {
          return (b.version_number || 0) - (a.version_number || 0);
        })[0];
        if (!latest) {
          toast(dual("لا يوجد إصدار لاعتماده.", "No version to approve."), "warn");
          return;
        }
        return post("/api/v1/ai/knowledge/versions/" + latest.id + "/approve", {})
          .then(function () {
            toast(dual("تم اعتماد الإصدار وأصبح قابلًا للاسترجاع.", "Version approved and retrievable."), "ok");
            return renderAdminKnowledge();
          });
      }).catch(adminError);
    }
    if (action === "knowledge-archive") {
      busy(el, true);
      return post("/api/v1/ai/knowledge/documents/" + id + "/archive", {}).then(function () {
        toast(dual("تمت أرشفة المستند.", "Document archived."), "ok");
        return renderAdminKnowledge();
      }).catch(adminError);
    }
    if (action === "knowledge-newversion") {
      var body = window.prompt(dual("نص الإصدار الجديد (عربي)", "New version body (AR)"));
      if (!body) return;
      busy(el, true);
      return post("/api/v1/ai/knowledge/documents/" + id + "/versions", { body_ar: body })
        .then(function (v) {
          return post("/api/v1/ai/knowledge/versions/" + v.id + "/approve", {})
            .then(function () {
              toast(dual("تم إنشاء إصدار واعتماده.", "Version created and approved."), "ok");
              return renderAdminKnowledge();
            });
        }).catch(adminError);
    }
    if (action === "knowledge-proposal-approve" || action === "knowledge-proposal-reject") {
      busy(el, true);
      return post("/api/v1/ai/knowledge/proposals/" + id + "/resolve",
        { approve: action === "knowledge-proposal-approve" })
        .then(function () {
          toast(dual("تمت معالجة المقترح.", "Proposal resolved."), "ok");
          return renderAdminKnowledge();
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
      return patch("/api/v1/users/" + id, { is_active: !active }).then(function () {
        toast(STATE.lang === "ar" ? "تم تحديث المستخدم." : "User updated.", "ok");
        return renderAdminUsers();
      }).catch(adminError);
    }

    if (action === "reset-user-password") {
      return openAdminSetPasswordForm(id);
    }

    if (action === "save-user") {
      var roleCode = byId("uRole" + id);
      var deptId = byId("uDept" + id);
      var payload = {};
      if (roleCode) payload.role_code = roleCode.value;
      if (deptId && deptId.value) payload.department_id = parseInt(deptId.value, 10);
      return patch("/api/v1/users/" + id, payload).then(function () {
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
    if (form.id === "knowledgeForm") {
      e.preventDefault();
      var knCompany = valOf("knCompany");
      var payload = {
        slug: valOf("knSlug"),
        title_ar: valOf("knTitleAr"),
        title_en: valOf("knTitleEn") || null,
        body_ar: valOf("knBodyAr"),
        category_id: valOf("knCategory") ? parseInt(valOf("knCategory"), 10) : null,
        company_id: knCompany ? parseInt(knCompany, 10) : null,
        sensitivity: valOf("knSensitivity"),
      };
      return post("/api/v1/ai/knowledge/documents", payload)
        .then(function () {
          toast(STATE.lang === "ar" ? "تمت إضافة المستند (مسودة)." : "Document added (draft).", "ok");
          return renderAdminKnowledge();
        }).catch(adminError);
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
      var optStr = function (id) { var v = valOf(id); return v === "" ? null : v; };
      return patch("/api/v1/admin/holding", {
        legal_name_ar: optStr("hLegalAr"),
        legal_name_en: optStr("hLegalEn"),
        commercial_registration: optStr("hCr"),
        tax_number: optStr("hTax"),
        default_currency: optStr("hCurrency"),
        contact_email: optStr("hEmail"),
        phone: optStr("hPhone"),
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
    lines.push(["Start Upsphere Holding 2027 — Executive Report"]);
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

    // Mirror the identity into the sidebar user block.
    var sbName = byId("sbUserName");
    if (sbName) {
      sbName.querySelectorAll(".ar").forEach(function (el) { el.textContent = name; });
      sbName.querySelectorAll(".en").forEach(function (el) {
        el.textContent = USER.full_name_en || name;
      });
    }
    var sbRole = byId("sbUserRole");
    if (sbRole) {
      sbRole.querySelectorAll(".ar").forEach(function (el) { el.textContent = role; });
      sbRole.querySelectorAll(".en").forEach(function (el) {
        el.textContent = USER.role_name_en || role;
      });
    }
    var sbAvatar = byId("sbAvatar");
    if (sbAvatar) sbAvatar.textContent = (name || "؟").trim().charAt(0);
  }

  function isHolding() {
    return has("dashboard.holding");
  }

  // The owner-supplied logo is the default in the header, login card and side
  // rail (shipped as a static asset). When an admin uploads a Holding logo it
  // replaces that default everywhere; on any failure the default asset is
  // restored rather than falling back to the generic SVG mark.
  var DEFAULT_LOGO = "/website/assets/holding-logo.png";
  function applyPlatformLogo() {
    var targets = ["brandLogo", "loginBrandLogo", "sbBrandLogo"]
      .map(byId)
      .filter(Boolean);
    if (!targets.length) return;
    get("/api/v1/public/branding")
      .then(function (branding) {
        var url = branding && branding.logo_url;
        if (!url) return;
        targets.forEach(function (img) {
          img.onerror = function () {
            img.onerror = null;
            img.src = DEFAULT_LOGO;
          };
          img.src = url;
        });
      })
      .catch(function () {
        /* keep the shipped default logo on any failure */
      });
  }

  function primaryCompanyId() {
    return USER && USER.company_ids && USER.company_ids.length
      ? USER.company_ids[0]
      : null;
  }

  // ---- AI --------------------------------------------------------------
  function aiScope(question) {
    if (isHolding()) {
      return { path: "/api/v1/ai/holding" + period, payload: { question: question } };
    }
    if (primaryCompanyId() !== null) {
      return {
        path: "/api/v1/ai/company" + period,
        payload: { question: question, company_id: primaryCompanyId() },
      };
    }
    return null;
  }

  function askAi(question) {
    var scope = aiScope(question);
    if (!scope) return Promise.reject(new Error("no AI scope available"));
    return post(scope.path, scope.payload).then(function (data) {
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

  // Knowledge-base assistant. It posts to the dedicated /ai/knowledge scope,
  // which retrieves only approved, in-scope chunks and returns them as sources.
  // The answer and its sources are escaped before insertion: a hosted provider
  // could otherwise emit markup.
  function askKnowledge(question) {
    return post("/api/v1/ai/knowledge", { question: question }).then(function (data) {
      var box = document.getElementById("kbAnswer");
      if (!box) return data;
      box.style.display = "";
      var q = document.getElementById("kbAnswerQ");
      if (q) {
        var safeQ = escapeHtml(question);
        q.innerHTML = '<span class="ar">«' + safeQ + '»</span><span class="en">“' + safeQ + '”</span>';
      }
      var body = document.getElementById("kbAnswerBody");
      if (body) {
        var safe = escapeHtml(data.answer || "");
        var html = '<p><span class="ar">' + safe + '</span><span class="en">' + safe + "</span></p>";
        var sources = data.sources || [];
        if (sources.length) {
          html += '<div class="av-list">' + sources.map(function (s) {
            var title = STATE.lang === "ar" ? s.title_ar : s.title_en || s.title_ar;
            return '<div class="av-row" style="cursor:default"><div class="grow">' +
              '<div class="t">' + escapeHtml(title) + "</div>" +
              '<div class="s">' + escapeHtml(s.excerpt || "") + "</div></div></div>";
          }).join("") + "</div>";
        }
        body.innerHTML = html;
      }
      return data;
    });
  }

  function bindKnowledgeAskBox() {
    var box = document.getElementById("kbAskBox");
    if (!box) return;
    var input = document.getElementById("kbInput");
    var send = document.getElementById("kbSend");
    if (!input || !send) return;
    function submit() {
      var q = (input.value || "").trim();
      if (!q) return;
      input.value = "";
      var body = document.getElementById("kbAnswerBody");
      var ans = document.getElementById("kbAnswer");
      if (ans) ans.style.display = "";
      if (body) body.innerHTML = loadingHtml();
      askKnowledge(q).catch(function (err) {
        if (body) body.innerHTML = errorHtml(errText(err));
      });
    }
    send.addEventListener("click", submit);
    input.addEventListener("keydown", function (e) {
      if (e.key === "Enter") submit();
    });
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
      hydrateRoleSummary(data);
      hydrateKpis(data);
      hydrateCompanies(data);
      hydratePriorities(data);
      setPeriodLabels();
      // Deck slide 46: the manager's smart brief depends on the period's
      // approved report, so make sure the report list is present first.
      ensureReports().then(function () { renderSmartBrief(); });
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
    if (repGrid) repGrid.innerHTML = errorHtml(message, { retry: true });
    var subs = document.querySelector(".subs");
    if (subs) subs.innerHTML = errorHtml(message, { retry: true });
    var overview = document.querySelector(".ov-card .card-body");
    if (overview) overview.innerHTML = errorHtml(message, { retry: true });
    var list = document.getElementById("insightsList");
    if (list) list.innerHTML = errorHtml(message, { retry: true });
    showAiError(message);
    var sbody = document.getElementById("supportBody");
    if (sbody) {
      sbody.innerHTML =
        '<tr><td colspan="5">' + errorHtml(message, { retry: true }) + "</td></tr>";
    }
  }

  // ---- login screen ----------------------------------------------------
  function showLogin() {
    body.classList.remove("authed");
    var screen = document.getElementById("loginScreen");
    if (screen) screen.style.display = "";
    var pw = document.getElementById("loginPassword");
    if (pw) pw.value = "";
    setLoginError("");
    setLoginNotice("");
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

  function setLoginNotice(message) {
    var el = document.getElementById("loginNotice");
    if (!el) return;
    if (message) {
      el.innerHTML = message;
      el.classList.add("show");
    } else {
      el.classList.remove("show");
    }
  }

  function bindLogin() {
    var form = document.getElementById("loginForm");
    if (!form) return;
    var rememberBox = document.getElementById("loginRemember");
    form.addEventListener("submit", function (e) {
      e.preventDefault();
      var email = (document.getElementById("loginEmail").value || "").trim();
      var password = document.getElementById("loginPassword").value || "";
      var remember = rememberBox ? !!rememberBox.checked : true;
      var btn = document.getElementById("loginBtn");
      setLoginError("");
      setLoginNotice("");
      if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<span class="spinner"></span>';
      }
      api
        .login(email, password, remember)
        .then(function () {
          return enterApp();
        })
        .catch(function (err) {
          // On the sign-in form a 401 means the email/password pair is wrong,
          // not that an existing session expired; the shared 401 wording would
          // otherwise be shown here and mislead the user.
          var credentialMsg =
            STATE.lang === "ar"
              ? "تعذّر تسجيل الدخول. تحقّق من البريد وكلمة المرور."
              : "Sign-in failed. Check your email and password.";
          var status = err && err.status;
          var message =
            status === 401 || status === 400 || status === 422 || !status
              ? credentialMsg
              : errText(err, credentialMsg);
          setLoginError(message);
        })
        .then(function () {
          if (btn) {
            btn.disabled = false;
            btn.innerHTML =
              '<span class="ar">تسجيل الدخول</span><span class="en">Sign in</span>';
          }
        });
    });

    // Deck slide 6 puts [نسيت كلمة المرور؟] on the sign-in form. Recovery is
    // handled by the Holding administrator in this phase (there is no
    // self-service email reset endpoint), so the link explains that rather
    // than opening a form that could not complete.
    var forgot = document.getElementById("loginForgot");
    if (forgot) {
      forgot.addEventListener("click", function () {
        setLoginNotice(
          STATE.lang === "ar"
            ? "لإعادة تعيين كلمة المرور، تواصل مع مسؤول القابضة (إدارة المستخدمين) لتزويدك برابط/كلمة مرور جديدة."
            : "To reset your password, contact the Holding administrator (User management) to be issued a new one.",
        );
      });
    }
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

  // Self-service password change (D11 account access). Reachable from the
  // header profile block so any signed-in user can rotate their own password
  // without an administrator.
  function openChangePassword() {
    openModal({
      title: dual("تغيير كلمة المرور", "Change password"),
      body:
        '<div class="av-field"><label>' +
        dual("كلمة المرور الحالية", "Current password") +
        '</label><input class="av-input" type="password" id="pwCurrent" style="width:100%"></div>' +
        '<div class="av-field"><label>' +
        dual("كلمة المرور الجديدة", "New password") +
        '</label><input class="av-input" type="password" id="pwNew" style="width:100%"></div>' +
        '<div class="av-field"><label>' +
        dual("تأكيد كلمة المرور الجديدة", "Confirm new password") +
        '</label><input class="av-input" type="password" id="pwConfirm" style="width:100%"></div>' +
        '<p class="note-block">' +
        dual("٨ أحرف على الأقل، و٧٢ بايت كحد أقصى.", "At least 8 characters, 72 bytes maximum.") +
        "</p>",
      footer:
        '<button class="btn-outline" id="pwCancel">' +
        dual("إلغاء", "Cancel") +
        '</button><button class="btn-solid" id="pwSave">' +
        dual("حفظ", "Save") +
        "</button>",
      onMount: function (root) {
        root.querySelector("#pwCancel").addEventListener("click", closeModal);
        root.querySelector("#pwSave").addEventListener("click", function () {
          var btn = root.querySelector("#pwSave");
          var current = valOf("pwCurrent");
          var next = valOf("pwNew");
          var confirm = valOf("pwConfirm");
          if (!current || !next) {
            toast(dual("املأ الحقول المطلوبة.", "Fill in the required fields."), "warn");
            return;
          }
          if (next !== confirm) {
            toast(dual("كلمتا المرور غير متطابقتين.", "The passwords do not match."), "warn");
            return;
          }
          if (next.length < 8) {
            toast(dual("كلمة المرور ٨ أحرف على الأقل.", "Password must be at least 8 characters."), "warn");
            return;
          }
          busy(btn, true);
          post("/api/v1/auth/change-password", {
            current_password: current,
            new_password: next,
          })
            .then(function () {
              closeModal();
              // Changing the password revokes every outstanding token, including
              // the one in this tab. Drop the local session and return to the
              // login screen so the next call is not a guaranteed 401.
              USER = null;
              api.logout();
              toast(dual("تم تغيير كلمة المرور. سجّل الدخول من جديد.", "Password changed. Please sign in again."), "ok");
              showLogin();
              window.scrollTo(0, 0);
            })
            .catch(function (err) {
              domainError(err);
            })
            .then(function () { busy(btn, false); });
        });
      },
    });
  }

  function bindProfileMenu() {
    var profile = document.querySelector(".profile");
    if (!profile) return;
    profile.style.cursor = "pointer";
    profile.setAttribute("role", "button");
    profile.setAttribute("tabindex", "0");
    profile.setAttribute("title", STATE.lang === "ar" ? "الحساب" : "Account");
    profile.addEventListener("click", openChangePassword);
    profile.addEventListener("keydown", function (e) {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        openChangePassword();
      }
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
        bindKnowledgeAskBox();
        bindLogout();
        bindProfileMenu();
        bindHeaderActions();
        bindNav();
        bindIndicatorDrills();
        bindScopeSelects();
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
        syncScopeSelects();
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
