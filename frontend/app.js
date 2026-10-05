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

  function sectorLabel(sector) {
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
  function toast(message, kind) {
    var wrap = byId("toastWrap");
    if (!wrap) {
      wrap = document.createElement("div");
      wrap.className = "toast-wrap";
      wrap.id = "toastWrap";
      document.body.appendChild(wrap);
    }
    var t = document.createElement("div");
    t.className = "toast " + (kind || "");
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
    if (typeof refreshActiveView === "function") refreshActiveView();
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
    "investments",
    "support",
    "requests",
    "approvals",
    "documents",
    "bi",
    "analytics",
    "inbox",
    "leads",
    "admin",
  ];
  var NAV_PERM = {
    dashboard: ["dashboard.holding", "dashboard.company"],
    subsidiaries: ["company.read"],
    reports: ["monthly_report.read_own", "monthly_report.read_all"],
    investments: ["dashboard.holding"],
    support: ["support_request.read_own", "support_request.read_all"],
    requests: ["form.read"],
    approvals: ["approval.read_own", "approval.read_all"],
    documents: ["document.read"],
    bi: ["ai.holding", "ai.company"],
    analytics: [
      "analytics.holding",
      "analytics.company",
      "analytics.operations",
      "analytics.compliance",
    ],
    inbox: ["notification.read_own"],
    leads: ["website_lead.read"],
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
      n.classList.toggle("active", n.getAttribute("data-view") === view);
    });
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
    if (view === "support") return renderSupportView();
    if (view === "requests") return renderRequestsView();
    if (view === "approvals") return renderApprovalsView();
    if (view === "documents") return renderDocumentsView();
    if (view === "investments") return renderInvestments();
    if (view === "bi") return renderBi();
    if (view === "analytics") return renderAnalytics();
    if (view === "inbox") return renderInbox();
    if (view === "leads") return renderLeads();
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
          '<div id="repActions" class="modal-foot" style="margin-top:14px;border-radius:12px;border:1px solid var(--line-2)"></div>';

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
        '<div class="av-field"><label>' + dual("الوصف", "Description") + '</label><textarea class="av-textarea" id="ncDesc"></textarea></div>',
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
          '<div class="s">' + dual("إيرادات ", "Revenue ") + dual(rev.ar, rev.en) + " · " + dual("صافي ", "Net ") + dual(net.ar, net.en) + "</div></div>" +
          growthHtml(r.revenue_pct) + healthBadge(r.health) + "</div>"
        );
      }).join("") + "</div>"
    );
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

  function renderLeads() {
    var host = byId("leadContent");
    if (!host) return Promise.resolve();
    if (!STATE.leadBound) {
      STATE.leadBound = true;
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
    host.innerHTML = loadingHtml();
    return Promise.all([loadLeadStats(), loadLeadList()]);
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
  var ADMIN_TABS = ["structure", "companies", "departments", "users", "roles", "builder", "workflows", "integrations", "audit"];
  var ADMIN_TAB_PERM = {
    structure: ["company.read", "ownership.read"],
    companies: ["company.read"],
    departments: ["department.read"],
    users: ["user.read_all"],
    roles: ["role.read"],
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
    host.className = "av-grid " + (tab === "users" || tab === "roles" || tab === "builder" ? "cols-1" : "cols-2");
    host.innerHTML = loadingHtml();
    if (tab === "structure") return renderAdminStructure();
    if (tab === "companies") return renderAdminCompanies();
    if (tab === "departments") return renderAdminDepartments();
    if (tab === "users") return renderAdminUsers();
    if (tab === "roles") return renderAdminRoles();
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
      if (!rows.length) {
        host.innerHTML = adminPanel("الشركات", "Companies", '<p class="av-empty">' + dual("لا توجد شركات.", "No companies.") + "</p>");
        return;
      }
      host.innerHTML = rows.map(function (c) {
        return adminPanel("شركة", "Company", companyAdminCard(c));
      }).join("");
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

  // ---- tab: audit ----
  function renderAdminAudit() {
    var host = byId("adminContent");
    var page = STATE.adminAudit || (STATE.adminAudit = { limit: 40, offset: 0, total: 0 });
    return get("/api/v1/admin/audit-logs?limit=" + page.limit + "&offset=" + page.offset).then(function (data) {
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
      host.innerHTML = adminPanel("سجل النشاط", "Audit trail", (rows ? '<div class="av-list">' + rows + "</div>" : '<p class="av-empty">' + dual("لا توجد سجلات.", "No entries.") + "</p>") + pager);
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
        applyPermissions();
        bindAskBox();
        bindLogout();
        bindHeaderActions();
        bindNav();
        showLoadingStates();
        return resolvePeriod();
      })
      .then(function () {
        // Reports back the dashboard cards' "View Report" action and the
        // company drill-downs, so load them first even when the period was
        // pinned via the URL (resolvePeriod skips its own fetch in that case).
        return Promise.all([ensureReports(), ensureCompanies()]);
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
        if (has("form.read") || has("form_submit")) {
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
