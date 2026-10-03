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
    dashboard: null,
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
      business_development: "تط",
      marketing: "تس",
      design: "تص",
      accounting: "مح",
      general: "عم",
      holding_owner: "عم",
      designer: "تص",
      accountant: "مح",
    };
    return map[name] || "عم";
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
      deptInitial(deptName) +
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
  var VIEWS = ["dashboard", "subsidiaries", "reports", "investments", "support", "bi"];
  var NAV_PERM = {
    dashboard: ["dashboard.holding", "dashboard.company"],
    subsidiaries: ["company.read"],
    reports: ["monthly_report.read_own", "monthly_report.read_all"],
    investments: ["dashboard.holding"],
    support: ["support_request.read_own", "support_request.read_all"],
    bi: ["ai.holding", "ai.company"],
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
    if (view === "investments") return renderInvestments();
    if (view === "bi") return renderBi();
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
            ? '<div class="av-field" style="margin-top:10px"><textarea class="av-textarea" id="cmtBody" placeholder="' +
              (STATE.lang === "ar" ? "أضف تعليقًا…" : "Add a comment…") + '"></textarea>' +
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

  // ---- search ----------------------------------------------------------
  function openSearch() {
    var panel = document.createElement("div");
    panel.className = "search-panel";
    panel.id = "searchPanel";
    panel.innerHTML =
      '<div class="search-box"><div class="search-in">' +
      '<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="#9DAABD" stroke-width="1.9" stroke-linecap="round"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.2-3.2"/></svg>' +
      '<input id="searchInput" placeholder="' + (STATE.lang === "ar" ? "ابحث في الشركات والتقارير والدعم…" : "Search companies, reports, support…") + '" autocomplete="off">' +
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
