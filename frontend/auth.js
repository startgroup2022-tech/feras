/*
 * Safir Holding 2027 — session + API client.
 *
 * Thin wrapper around the backend's existing JWT authentication. The access and
 * refresh tokens live in localStorage under one key; every API call attaches
 * ``Authorization: Bearer <access>`` automatically and transparently refreshes
 * once on a 401 before failing. No token is ever placed in the URL or in HTML.
 */
(function (global) {
  "use strict";

  var STORE_KEY = "safir.session.v1";
  var API_BASE = "";

  var session = null;

  function load() {
    try {
      var raw = localStorage.getItem(STORE_KEY);
      session = raw ? JSON.parse(raw) : null;
    } catch (e) {
      session = null;
    }
    return session;
  }

  function save(s) {
    session = s;
    try {
      if (s) localStorage.setItem(STORE_KEY, JSON.stringify(s));
      else localStorage.removeItem(STORE_KEY);
    } catch (e) {
      /* storage disabled — session stays in memory for this page only */
    }
  }

  function clear() {
    save(null);
  }

  function setBase(base) {
    API_BASE = (base || "").replace(/\/$/, "");
  }

  function authHeaders() {
    var h = { "Content-Type": "application/json" };
    if (session && session.access_token) {
      h["Authorization"] = "Bearer " + session.access_token;
    }
    return h;
  }

  function request(path, options) {
    options = options || {};
    var url = API_BASE + path;
    return fetch(url, {
      method: options.method || "GET",
      headers: authHeaders(),
      body: options.body ? JSON.stringify(options.body) : undefined,
    }).then(function (res) {
      if (res.status === 204) return null;
      var ct = res.headers.get("content-type") || "";
      var parse = ct.indexOf("application/json") >= 0 ? res.json() : res.text();
      return parse.then(function (data) {
        if (res.ok) return data;
        var err = new Error(messageFor(res.status, data));
        err.status = res.status;
        err.data = data;
        throw err;
      });
    });
  }

  function messageFor(status, data) {
    if (data && typeof data === "object" && data.detail) {
      if (typeof data.detail === "string") return data.detail;
      if (Array.isArray(data.detail) && data.detail.length) {
        return data.detail[0].msg || "Request failed.";
      }
    }
    if (status === 401) return "Invalid email or password.";
    if (status === 403) return "You do not have permission for this action.";
    if (status === 429) return "Too many attempts. Please try again later.";
    if (status === 404) return "Not found.";
    return "Request failed (" + status + ").";
  }

  // Retry once after refreshing the access token. Only 401 triggers a refresh;
  // a 403 is a genuine authorization boundary and must surface to the caller.
  function authed(path, options) {
    options = options || {};
    return request(path, options).catch(function (err) {
      if (err.status !== 401 || !session || !session.refresh_token) throw err;
      return fetch(API_BASE + "/api/v1/auth/refresh", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: session.refresh_token }),
      })
        .then(function (res) {
          if (!res.ok) throw err;
          return res.json();
        })
        .then(function (tok) {
          save({
            access_token: tok.access_token,
            refresh_token: tok.refresh_token,
            expires_at: Date.now() + tok.expires_in * 1000,
          });
          return request(path, options);
        });
    });
  }

  function login(email, password) {
    return fetch(API_BASE + "/api/v1/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email: email, password: password }),
    }).then(function (res) {
      return res
        .json()
        .catch(function () {
          return {};
        })
        .then(function (data) {
          if (!res.ok) {
            var e = new Error(messageFor(res.status, data));
            e.status = res.status;
            throw e;
          }
          save({
            access_token: data.access_token,
            refresh_token: data.refresh_token,
            expires_at: Date.now() + data.expires_in * 1000,
          });
          return data;
        });
    });
  }

  function logout() {
    var p = session
      ? authed("/api/v1/auth/logout", { method: "POST" }).catch(function () {})
      : Promise.resolve();
    return p.then(function () {
      clear();
    });
  }

  function me() {
    return authed("/api/v1/auth/me");
  }

  function isAuthenticated() {
    return !!(session && session.access_token);
  }

  global.SafirApi = {
    setBase: setBase,
    load: load,
    login: login,
    logout: logout,
    me: me,
    get: function (path) {
      return authed(path);
    },
    post: function (path, body) {
      return authed(path, { method: "POST", body: body });
    },
    patch: function (path, body) {
      return authed(path, { method: "PATCH", body: body });
    },
    del: function (path) {
      return authed(path, { method: "DELETE" });
    },
    isAuthenticated: isAuthenticated,
    clear: clear,
  };
})(window);
