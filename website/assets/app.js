/*
 * Safir Holding — public website behaviour.
 *
 * Progressive enhancement only: every page is a complete server-rendered
 * document, and this script adds three things on top of it.
 *
 *   1. Attribution capture. UTM parameters, the referrer and the landing page
 *      are read once per session and attached to every submission, so a lead's
 *      origin is recorded even if the visitor filled the form several pages in.
 *   2. Client-side form handling with real server validation. The browser
 *      checks required fields for a fast error, but the server is the source of
 *      truth: its 422 response is mapped back onto the right fields.
 *   3. Small UI affordances — mobile navigation, the multi-step listing wizard
 *      and the live opportunities list.
 *
 * No framework, no build step. All text that reaches the DOM from data is set
 * with textContent, never innerHTML, so a stored value cannot inject markup.
 */
(function () {
  "use strict";

  var AR = document.documentElement.lang === "ar";

  // ------------------------------------------------------------------ i18n
  var T = {
    sending: AR ? "جارٍ الإرسال…" : "Sending…",
    sent: AR ? "تم استلام طلبك. سنتواصل معك قريبًا." : "Your request has been received. We will be in touch shortly.",
    ref: AR ? "الرقم المرجعي" : "Reference",
    error: AR ? "تعذّر إرسال الطلب. يرجى المحاولة مرة أخرى." : "We could not submit your request. Please try again.",
    required: AR ? "هذا الحقل مطلوب." : "This field is required.",
    invalidEmail: AR ? "يرجى إدخال بريد إلكتروني صحيح." : "Please enter a valid email address.",
    tooMany: AR ? "محاولات كثيرة. يرجى المحاولة لاحقًا." : "Too many attempts. Please try again later.",
    noOpps: AR ? "لا توجد فرص منشورة حاليًا في هذا السوق." : "No published opportunities in this market right now.",
    stepRequired: AR ? "يرجى إكمال هذا القسم." : "Please complete this section.",
    pickOpp: AR ? "يرجى اختيار الفرصة التي تهمك أولًا." : "Please choose the opportunity you are interested in first.",
  };

  // --------------------------------------------------------- attribution
  // Captured once and kept for the session so a lead keeps the campaign that
  // brought the visitor to the site, not the page they happened to submit from.
  var ATTR_KEY = "safir.attr.v1";

  function readAttribution() {
    var params = new URLSearchParams(window.location.search);
    var fresh = {
      utm_source: params.get("utm_source"),
      utm_medium: params.get("utm_medium"),
      utm_campaign: params.get("utm_campaign"),
      utm_content: params.get("utm_content"),
      utm_term: params.get("utm_term"),
      referrer: document.referrer || null,
      landing_page: window.location.pathname + window.location.search,
    };
    var stored = null;
    try {
      stored = JSON.parse(sessionStorage.getItem(ATTR_KEY) || "null");
    } catch (e) {
      stored = null;
    }
    // A fresh campaign in the URL always wins; otherwise keep the session's
    // original landing attribution.
    if (fresh.utm_source || fresh.utm_campaign || !stored) {
      try { sessionStorage.setItem(ATTR_KEY, JSON.stringify(fresh)); } catch (e) {}
      return fresh;
    }
    return stored;
  }

  var ATTRIBUTION = readAttribution();

  // ------------------------------------------------------------- helpers
  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text != null) node.textContent = text;
    return node;
  }

  function clearErrors(form) {
    form.querySelectorAll(".field.has-error").forEach(function (f) {
      f.classList.remove("has-error");
    });
    form.querySelectorAll(".field-error").forEach(function (p) {
      p.hidden = true;
      p.textContent = "";
    });
    var status = form.querySelector(".form-status");
    if (status) { status.textContent = ""; status.className = "form-status"; }
  }

  function showFieldError(form, name, message) {
    var input = form.querySelector('[name="' + CSS.escape(name) + '"]');
    if (!input) return;
    var wrap = input.closest(".field");
    var error = wrap ? wrap.querySelector(".field-error") : null;
    if (wrap) wrap.classList.add("has-error");
    if (error) { error.textContent = message; error.hidden = false; }
    input.setAttribute("aria-invalid", "true");
  }

  function collect(form) {
    var data = {};
    new FormData(form).forEach(function (value, key) {
      if (key === "honeypot") return;
      data[key] = value;
    });
    // Booleans and numbers must be typed correctly for the API schemas.
    ["consent", "needs_office"].forEach(function (k) {
      if (k in data) data[k] = data[k] === "on" || data[k] === "true" || data[k] === "yes";
    });
    ["number_of_partners", "business_age_years", "opportunity_id"].forEach(function (k) {
      if (k in data && data[k] !== "") data[k] = parseInt(data[k], 10);
    });
    ["approximate_capital", "value_min", "value_max"].forEach(function (k) {
      if (k in data && data[k] !== "") data[k] = parseFloat(data[k]);
    });
    // Drop empty optional strings so the API sees nulls, not "".
    Object.keys(data).forEach(function (k) {
      if (data[k] === "") delete data[k];
    });
    if (data.needs_office === false) data.needs_office = false;
    data.attribution = ATTRIBUTION;
    data.honeypot = new FormData(form).get("honeypot") || "";
    return data;
  }

  function successPanel(form, result) {
    var wrap = el("div", "form-success");
    wrap.setAttribute("role", "status");
    wrap.appendChild(el("p", null, T.sent));
    if (result && result.reference) {
      wrap.appendChild(el("p", "muted", T.ref));
      wrap.appendChild(el("span", "ref", result.reference));
    }
    form.replaceWith(wrap);
    wrap.scrollIntoView({ block: "center", behavior: "smooth" });
  }

  function handleServerErrors(form, body) {
    var fields = body && body.error && body.error.fields;
    if (Array.isArray(fields)) {
      fields.forEach(function (f) {
        var name = (f.field || "").split(".").pop();
        showFieldError(form, name, f.message || T.required);
      });
    }
    var status = form.querySelector(".form-status");
    if (status) {
      status.textContent = (body && body.error && body.error.message) || T.error;
      status.className = "form-status err";
    }
  }

  function submitForm(form, onDone) {
    var status = form.querySelector(".form-status");
    var button = form.querySelector("[data-submit]");
    clearErrors(form);

    if (!form.reportValidity()) return;
    if (status) { status.textContent = T.sending; status.className = "form-status"; }
    if (button) button.disabled = true;

    fetch(form.action, {
      method: "POST",
      headers: { "Content-Type": "application/json", "Accept": "application/json" },
      body: JSON.stringify(collect(form)),
    })
      .then(function (res) {
        return res.json().catch(function () { return {}; }).then(function (body) {
          return { ok: res.ok, status: res.status, body: body };
        });
      })
      .then(function (r) {
        if (button) button.disabled = false;
        if (r.ok) {
          successPanel(form, r.body);
          if (onDone) onDone();
          return;
        }
        if (r.status === 429) {
          if (status) { status.textContent = T.tooMany; status.className = "form-status err"; }
          return;
        }
        handleServerErrors(form, r.body);
      })
      .catch(function () {
        if (button) button.disabled = false;
        if (status) { status.textContent = T.error; status.className = "form-status err"; }
      });
  }

  // A multipart submission for forms that carry files (the careers CV). The
  // structured fields travel as one JSON part under "payload"; the file inputs
  // are appended under their own field names. The API validates the JSON part
  // with the same strict schema used by the JSON forms.
  function submitMultipart(form) {
    var status = form.querySelector(".form-status");
    var button = form.querySelector("[data-submit]");
    clearErrors(form);

    if (!form.reportValidity()) return;
    if (status) { status.textContent = T.sending; status.className = "form-status"; }
    if (button) button.disabled = true;

    var data = collect(form);
    // File inputs are sent separately below; drop them from the JSON part so
    // the schema sees only scalar fields.
    form.querySelectorAll('input[type="file"]').forEach(function (input) {
      delete data[input.name];
    });
    var fd = new FormData();
    fd.append("payload", JSON.stringify(data));
    form.querySelectorAll('input[type="file"]').forEach(function (input) {
      for (var i = 0; i < input.files.length; i++) {
        if (input.files[i] && input.files[i].name) fd.append(input.name, input.files[i]);
      }
    });

    fetch(form.action, { method: "POST", body: fd, headers: { "Accept": "application/json" } })
      .then(function (res) {
        return res.json().catch(function () { return {}; }).then(function (body) {
          return { ok: res.ok, status: res.status, body: body };
        });
      })
      .then(function (r) {
        if (button) button.disabled = false;
        if (r.ok) { successPanel(form, r.body); return; }
        if (r.status === 429) {
          if (status) { status.textContent = T.tooMany; status.className = "form-status err"; }
          return;
        }
        handleServerErrors(form, r.body);
      })
      .catch(function () {
        if (button) button.disabled = false;
        if (status) { status.textContent = T.error; status.className = "form-status err"; }
      });
  }

  // ------------------------------------------------------- form binding
  document.querySelectorAll("form.site-form").forEach(function (form) {
    if (form.dataset.form === "business-listing") return; // handled by wizard
    form.addEventListener("submit", function (event) {
      event.preventDefault();
      // The interest form only makes sense against a chosen listing. The id is
      // set when the visitor clicks "I'm interested" on a specific card.
      if (form.dataset.form === "opportunity-interest") {
        var oppId = form.querySelector('input[name="opportunity_id"]');
        if (!oppId || !oppId.value) {
          var s = form.querySelector(".form-status");
          if (s) { s.textContent = T.pickOpp; s.className = "form-status err"; }
          var list = document.querySelector("[data-opportunities]");
          if (list) list.scrollIntoView({ block: "center", behavior: "smooth" });
          return;
        }
      }
      // The careers form carries a CV, so it submits as multipart: the
      // structured fields go as one JSON part, the file(s) alongside.
      if (form.dataset.multipart === "1") {
        submitMultipart(form);
        return;
      }
      submitForm(form);
    });
  });

  // -------------------------------------------------------- mobile nav
  var navToggle = document.querySelector("[data-nav-toggle]");
  var nav = document.querySelector("[data-nav]");
  if (navToggle && nav) {
    var closeNav = function () {
      nav.classList.remove("is-open");
      navToggle.setAttribute("aria-expanded", "false");
    };
    navToggle.addEventListener("click", function () {
      var open = nav.classList.toggle("is-open");
      navToggle.setAttribute("aria-expanded", open ? "true" : "false");
    });
    // Close the drawer once a destination is chosen, or on Escape.
    nav.addEventListener("click", function (event) {
      if (event.target.closest("a")) closeNav();
    });
    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape" && nav.classList.contains("is-open")) {
        closeNav();
        navToggle.focus();
      }
    });
  }

  // A subtle elevation once the page scrolls under the sticky header.
  var header = document.querySelector("[data-header]");
  if (header) {
    var onScroll = function () {
      header.classList.toggle("is-stuck", window.scrollY > 8);
    };
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
  }

  // --------------------------------------------------- opportunities list
  var oppHost = document.querySelector("[data-opportunities]");
  if (oppHost) {
    var market = oppHost.getAttribute("data-market");
    fetch("/api/v1/public/opportunities?market=" + encodeURIComponent(market), {
      headers: { "Accept": "application/json" },
    })
      .then(function (r) { return r.ok ? r.json() : []; })
      .then(function (rows) {
        oppHost.textContent = "";
        if (!rows.length) {
          oppHost.appendChild(el("p", "state", T.noOpps));
          return;
        }
        var typeLabels = {
          full_sale: AR ? "بيع كامل" : "Full Sale",
          partial_sale: AR ? "بيع حصة" : "Partial Sale",
          strategic_partner: AR ? "شريك استراتيجي" : "Strategic Partner",
          investment: AR ? "استثمار" : "Investment",
          acquisition: AR ? "استحواذ" : "Acquisition",
        };
        rows.forEach(function (row) {
          var card = el("article", "opp-card");
          var title = AR ? row.title_ar : row.title_en;
          card.appendChild(el("h3", null, title || (AR ? "فرصة" : "Opportunity")));
          var tags = el("div", "opp-tags");
          tags.appendChild(el("span", "tag gold", typeLabels[row.opportunity_type] || row.opportunity_type));
          if (row.sector) tags.appendChild(el("span", "tag", row.sector));
          card.appendChild(tags);
          var summary = AR ? row.summary_ar : row.summary_en;
          if (summary) card.appendChild(el("p", null, summary));
          var link = el("a", "service-link", AR ? "أنا مهتم" : "I'm interested");
          link.href = "#form";
          link.addEventListener("click", function () {
            var hidden = document.querySelector('input[name="opportunity_id"]');
            if (!hidden) {
              hidden = document.createElement("input");
              hidden.type = "hidden";
              hidden.name = "opportunity_id";
              var target = document.querySelector('form[data-form="opportunity-interest"]');
              if (target) target.appendChild(hidden);
            }
            hidden.value = String(row.id);
          });
          card.appendChild(link);
          oppHost.appendChild(card);
        });
      })
      .catch(function () {
        oppHost.textContent = "";
        oppHost.appendChild(el("p", "state", T.noOpps));
      });
  }

  // ----------------------------------------------- listing wizard (6 steps)
  var wizard = document.querySelector("form.listing-form");
  if (wizard) {
    var steps = Array.prototype.slice.call(wizard.querySelectorAll(".form-step"));
    var progressItems = Array.prototype.slice.call(document.querySelectorAll(".progress li"));
    var nextBtn = wizard.querySelector("[data-next]");
    var prevBtn = wizard.querySelector("[data-prev]");
    var submitBtn = wizard.querySelector("[data-submit]");
    var current = 0;

    function fieldsetValid(step) {
      var valid = true;
      step.querySelectorAll("[required]").forEach(function (input) {
        var ok = input.type === "radio"
          ? !!step.querySelector('input[name="' + CSS.escape(input.name) + '"]:checked')
          : (input.type === "checkbox" ? input.checked : input.value.trim() !== "");
        if (input.type === "email" && ok) ok = /.+@.+\..+/.test(input.value);
        if (!ok) {
          valid = false;
          var wrap = input.closest(".field");
          if (wrap) wrap.classList.add("has-error");
        } else {
          var w = input.closest(".field");
          if (w) w.classList.remove("has-error");
        }
      });
      return valid;
    }

    function renderReview() {
      var box = wizard.querySelector("[data-review]");
      if (!box) return;
      box.textContent = "";
      var dl = document.createElement("dl");
      var data = new FormData(wizard);
      var labels = {
        market: AR ? "الدولة" : "Country",
        applicant_capacity: AR ? "صفة مقدم الطلب" : "Applicant capacity",
        opportunity_type: AR ? "نوع الفرصة" : "Opportunity type",
        company_name: AR ? "اسم الشركة" : "Company name",
        sector: AR ? "القطاع" : "Sector",
        business_age_years: AR ? "عمر النشاط" : "Business age",
        value_min: AR ? "القيمة من" : "Value from",
        value_max: AR ? "القيمة إلى" : "Value to",
      };
      var choiceLabels = {
        applicant_capacity: {
          owner: AR ? "مالك" : "Owner",
          representative: AR ? "ممثل" : "Representative",
          advisor: AR ? "مستشار / وسيط" : "Advisor / Broker",
        },
        opportunity_type: {
          full_sale: AR ? "بيع كامل" : "Full Sale",
          partial_sale: AR ? "بيع حصة" : "Partial Sale",
          strategic_partner: AR ? "شريك استراتيجي" : "Strategic Partner",
          investment: AR ? "استثمار" : "Investment",
        },
      };
      Object.keys(labels).forEach(function (key) {
        if (!data.get(key)) return;
        var value = String(data.get(key));
        if (choiceLabels[key] && choiceLabels[key][value]) value = choiceLabels[key][value];
        var dt = el("dt", null, labels[key]);
        var dd = el("dd", null, value);
        dl.appendChild(dt);
        dl.appendChild(dd);
      });
      box.appendChild(dl);
    }

    function show(index) {
      current = Math.max(0, Math.min(index, steps.length - 1));
      steps.forEach(function (step, i) { step.hidden = i !== current; });
      progressItems.forEach(function (item, i) {
        item.setAttribute("data-state", i < current ? "done" : (i === current ? "current" : "todo"));
      });
      prevBtn.hidden = current === 0;
      nextBtn.hidden = current === steps.length - 1;
      submitBtn.hidden = current !== steps.length - 1;
      if (current === steps.length - 1) renderReview();
      var legend = steps[current].querySelector("legend");
      if (legend) legend.setAttribute("tabindex", "-1");
    }

    nextBtn.addEventListener("click", function () {
      if (!fieldsetValid(steps[current])) {
        var status = wizard.querySelector(".form-status");
        if (status) { status.textContent = T.stepRequired; status.className = "form-status err"; }
        return;
      }
      show(current + 1);
    });
    prevBtn.addEventListener("click", function () { show(current - 1); });

    wizard.addEventListener("submit", function (event) {
      event.preventDefault();
      for (var i = 0; i < steps.length - 1; i++) {
        if (!fieldsetValid(steps[i])) { show(i); return; }
      }
      // Multipart is required because a listing may carry attachments; the
      // structured fields go as one JSON part.
      var data = collect(wizard);
      var fd = new FormData();
      fd.append("payload", JSON.stringify(data));
      var honeypot = wizard.querySelector('input[name="honeypot"]');
      if (honeypot && honeypot.value) fd.append("honeypot", honeypot.value);

      var status = wizard.querySelector(".form-status");
      if (status) { status.textContent = T.sending; status.className = "form-status"; }
      submitBtn.disabled = true;

      fetch(wizard.action, { method: "POST", body: fd, headers: { "Accept": "application/json" } })
        .then(function (res) {
          return res.json().catch(function () { return {}; }).then(function (body) {
            return { ok: res.ok, status: res.status, body: body };
          });
        })
        .then(function (r) {
          submitBtn.disabled = false;
          if (r.ok) { successPanel(wizard, r.body); return; }
          if (r.status === 429) {
            if (status) { status.textContent = T.tooMany; status.className = "form-status err"; }
            return;
          }
          handleServerErrors(wizard, r.body);
        })
        .catch(function () {
          submitBtn.disabled = false;
          if (status) { status.textContent = T.error; status.className = "form-status err"; }
        });
    });

    show(0);
  }

  // ------------------------------------------------------ group companies
  // Desktop: the choice list drives one detail panel. Mobile (<=600px): the
  // same markup becomes an accordion -- the chosen name opens its inline panel
  // and the previous one closes, with every name kept visible (no horizontal
  // scroll, no filters). The first company is selected by default server-side.
  var selector = document.querySelector("[data-company-selector]");
  if (selector) {
    var choices = selector.querySelectorAll("[data-company-choice]");
    var panels = selector.querySelectorAll("[data-company-panel]");
    var desktopDetail = selector.querySelector("[data-company-detail]");
    var chooseCompany = function (index) {
      choices.forEach(function (b, i) {
        b.setAttribute("aria-expanded", i === index ? "true" : "false");
      });
      panels.forEach(function (p, i) {
        if (i === index) { p.removeAttribute("hidden"); }
        else { p.setAttribute("hidden", ""); }
      });
      if (desktopDetail && panels[index]) {
        desktopDetail.innerHTML = panels[index].innerHTML;
      }
    };
    choices.forEach(function (b, i) {
      b.addEventListener("click", function () { chooseCompany(i); });
    });
  }
})();
