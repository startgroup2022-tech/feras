/*
 * Safir Holding 2027 — live data bridge.
 *
 * The dashboard ships as a self-contained, presentation-quality mockup. This
 * script upgrades it to a *live* dashboard when the FastAPI backend is
 * reachable, and otherwise leaves the curated demo figures in place. That
 * graceful degradation matters for a Holding platform: a stakeholder opening
 * the file directly still sees a coherent screen, while the deployed product
 * shows real, company-scoped data.
 *
 * Configuration (all optional, via <body> data-* attributes or query string):
 *   data-api="http://localhost:8000"   backend origin
 *   data-token="<jwt>"                 a pre-issued access token
 *   ?year=2027&month=10                the reporting period
 *
 * No credentials are ever hardcoded here.
 */
(function () {
  "use strict";

  var body = document.body;
  var params = new URLSearchParams(location.search);
  var configured = body.getAttribute("data-api") || params.get("api") || "";
  // When served by the backend itself, fall back to the current origin so the
  // dashboard goes live with no configuration. Opened as a file, it stays demo.
  var sameOrigin = /^https?:$/.test(location.protocol) ? location.origin : "";
  var API = (configured || sameOrigin).replace(/\/$/, "");
  var TOKEN = body.getAttribute("data-token") || params.get("token") || "";
  var YEAR = params.get("year");
  var MONTH = params.get("month");

  var period = "";
  if (YEAR && MONTH) period = "?year=" + YEAR + "&month=" + MONTH;

  function headers() {
    var h = { "Content-Type": "application/json" };
    if (TOKEN) h["Authorization"] = "Bearer " + TOKEN;
    return h;
  }

  function get(path) {
    return fetch(API + path, { headers: headers() }).then(function (r) {
      if (!r.ok) throw new Error(path + " -> " + r.status);
      return r.json();
    });
  }

  function post(path, payload) {
    return fetch(API + path, {
      method: "POST",
      headers: headers(),
      body: JSON.stringify(payload),
    }).then(function (r) {
      if (!r.ok) throw new Error(path + " -> " + r.status);
      return r.json();
    });
  }

  // ---- formatting ------------------------------------------------------
  var NUM = new Intl.NumberFormat("en-US");

  function money(value) {
    if (value === null || value === undefined) return "—";
    return NUM.format(Math.round(Number(value)));
  }

  // Compact form for the KPI tiles: 192.4 (millions).
  function millions(value) {
    if (value === null || value === undefined) return "—";
    return (Number(value) / 1e6).toFixed(1);
  }

  function pct(value) {
    if (value === null || value === undefined) return null;
    var sign = value >= 0 ? "+" : "−";
    return sign + Math.abs(value).toFixed(1) + "%";
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
      Math.abs(p).toFixed(1) +
      "٪</span>"
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
    return (
      '<div class="rep">' +
      '<div class="rep-top">' +
      '<div class="rep-logo" style="background:' +
      bg +
      '">' +
      initial(row.name_ar) +
      "</div>" +
      '<div class="rep-id">' +
      '<div class="rep-name"><span class="ar">' +
      row.name_ar +
      '</span><span class="en">' +
      (row.name_en || row.name_ar) +
      "</span></div>" +
      '<div class="rep-sec"><span class="ar">' +
      sector.ar +
      '</span><span class="en">' +
      sector.en +
      "</span></div>" +
      "</div></div>" +
      '<div class="rep-stats">' +
      '<div class="stat"><div class="l"><span class="ar">الإيرادات</span><span class="en">Revenue</span></div><div class="v">' +
      millions(row.revenue) +
      "</div></div>" +
      '<div class="stat"><div class="l"><span class="ar">المصروفات</span><span class="en">Expenses</span></div><div class="v">' +
      millions(row.expenses) +
      "</div></div>" +
      '<div class="stat"><div class="l"><span class="ar">الصافي</span><span class="en">Net</span></div><div class="v">' +
      millions(row.net_result) +
      "</div></div>" +
      "</div>" +
      '<div class="rep-foot">' +
      '<span class="rep-upd"><span class="ar">' +
      (row.has_report ? "محدّث" : "متأخر") +
      '</span><span class="en">' +
      (row.has_report ? "Updated" : "Overdue") +
      "</span></span>" +
      '<div style="display:flex;align-items:center;gap:5px">' +
      growthHtml(row.revenue_pct) +
      '<span class="status ' +
      status +
      '"><i></i><span class="ar">' +
      label.ar +
      '</span><span class="en">' +
      label.en +
      "</span></span>" +
      "</div></div></div>"
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
          Math.abs(row.revenue_pct).toFixed(1) +
          "٪") +
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
    if (!rows.length) return;

    var repGrid = document.querySelector(".rep-grid");
    if (repGrid) repGrid.innerHTML = rows.map(reportCard).join("");

    var subs = document.querySelector(".subs");
    if (subs) subs.innerHTML = rows.map(subCard).join("");

    var overview = document.querySelector(".ov-card .card-body");
    if (overview) overview.innerHTML = rows.map(overviewCard).join("");

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
    if (!body || !rows.length) return;
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
      var p = pct(change.revenue_pct);
      if (p === null) {
        delta.className = "delta flat";
        delta.textContent = "لا توجد مقارنة";
      } else {
        delta.className = "delta " + (change.revenue_pct >= 0 ? "up" : "down");
        delta.textContent =
          (change.revenue_pct >= 0 ? "▲ " : "▼ ") + p.replace(/^[+−]/, "");
      }
    }

    var netDelta = document.querySelector('[data-kpi="net_delta"]');
    if (netDelta && change.net_pct !== null && change.net_pct !== undefined) {
      netDelta.className = "delta " + (change.net_pct >= 0 ? "up" : "down");
      netDelta.textContent =
        (change.net_pct >= 0 ? "▲ " : "▼ ") +
        Math.abs(change.net_pct).toFixed(1) +
        "٪";
    }

    var margin = document.querySelector('[data-kpi="net_margin"]');
    if (margin && Number(k.total_revenue)) {
      var m = (Number(k.total_net_result) / Number(k.total_revenue)) * 100;
      margin.textContent = m.toFixed(1) + "٪";
    }

    var marginEn = document.querySelector('[data-kpi="net_margin_en"]');
    if (marginEn && Number(k.total_revenue)) {
      var m2 = (Number(k.total_net_result) / Number(k.total_revenue)) * 100;
      marginEn.textContent = m2.toFixed(1) + "%";
    }
  }

  function renderInsights(insights) {
    var list = document.getElementById("insightsList");
    if (!list || !insights.length) return;

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

  function askAi(question) {
    return post("/api/v1/ai/holding" + period, { question: question }).then(
      function (data) {
        hydrateAiAnswer(data, question);
        return data;
      },
    );
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
        console.warn("[safir] AI request failed:", err.message);
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

  // ---- boot ------------------------------------------------------------
  function boot() {
    if (!API) {
      console.info("[safir] No data-api configured; showing demo figures.");
      return;
    }
    bindAskBox();

    get("/api/v1/dashboard/holding" + period)
      .then(function (data) {
        hydrateKpis(data);
        hydrateCompanies(data);
        document.body.classList.add("is-live");
      })
      .catch(function (err) {
        console.warn(
          "[safir] Dashboard unavailable, keeping demo data:",
          err.message,
        );
      });

    get("/api/v1/support-requests")
      .then(hydrateSupport)
      .catch(function () {});

    get("/api/v1/ai/insights" + period)
      .then(renderInsights)
      .catch(function () {});

    askAi("ملخص أداء المجموعة هذا الشهر").catch(function () {});
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
