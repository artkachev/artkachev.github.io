/* Фильтры, плеер Spotify и окно альбома. Без библиотек. */
(function () {
  "use strict";

  var ctrl = null;          // контроллер Spotify iFrame API
  var current = null;       // активная плитка
  var wantPlay = false;     // сафари на айфоне глушит автостарт
  var pendingUri = null;

  /* ── фильтры ─────────────────────────────────────────────── */
  var filters = document.querySelector(".filters");
  if (filters) {
    filters.addEventListener("click", function (e) {
      var btn = e.target.closest("button[data-f]");
      if (!btn) return;
      var f = btn.dataset.f;
      filters.querySelectorAll("button").forEach(function (b) {
        b.setAttribute("aria-pressed", String(b === btn));
      });
      document.querySelectorAll(".grid > li").forEach(function (li) {
        var tile = li.querySelector(".tile");
        var show = f === "ALL" || (tile && tile.dataset.g === f);
        li.hidden = !show;
      });
    });
  }

  /* ── плеер ───────────────────────────────────────────────── */
  var panel = document.getElementById("player");

  window.onSpotifyIframeApiReady = function (IFrameAPI) {
    var el = document.getElementById("pframe");
    IFrameAPI.createController(el, { width: "100%", height: 80 }, function (c) {
      ctrl = c;
      c.addListener("playback_update", function (ev) {
        if (!current) return;
        var paused = ev && ev.data && ev.data.isPaused;
        if (wantPlay && paused) {
          try { c.resume(); } catch (err) { current.classList.add("retap"); }
        } else if (!paused) {
          wantPlay = false;
          current.classList.remove("retap");
        }
      });
      if (pendingUri) { start(pendingUri); pendingUri = null; }
    });
  };

  function start(uri) {
    ctrl.loadUri(uri);
    ctrl.play();
  }

  window.play = function (el) {
    var id = el.dataset.id;
    if (!id) return;
    if (current === el && ctrl) { ctrl.togglePlay(); return; }
    if (current) current.classList.remove("playing", "retap");
    current = el;
    el.classList.add("playing");
    wantPlay = true;
    panel.classList.add("on");
    var uri = "spotify:track:" + id;
    if (ctrl) { start(uri); } else { pendingUri = uri; }
  };

  /* ── окно альбома ────────────────────────────────────────── */
  var modal = document.getElementById("amodal");
  var openerTile = null;

  window.openAlbum = function (i) {
    var al = (window.ALBUMS || [])[i];
    if (!al) return;
    openerTile = document.activeElement;
    document.getElementById("awho").textContent = al.artist;
    document.getElementById("atitle").textContent = al.title;
    var cover = document.getElementById("acover");
    cover.src = "/covers/" + al.cover + ".jpg";
    cover.alt = al.artist + " — " + al.title;
    var list = document.getElementById("alist");
    list.textContent = "";
    al.tracks.forEach(function (t, n) {
      var li = document.createElement("li");
      var b = document.createElement("button");
      b.type = "button";
      b.dataset.id = t.id;
      var num = document.createElement("span");
      num.className = "n";
      num.textContent = String(n + 1);
      var name = document.createElement("span");
      name.textContent = t.title;
      b.append(num, name);
      b.addEventListener("click", function () { window.play(b); });
      li.appendChild(b);
      list.appendChild(li);
    });
    modal.classList.add("on");
    modal.querySelector(".close").focus();
  };

  function closeAlbum() {
    modal.classList.remove("on");
    if (openerTile && openerTile.focus) openerTile.focus();
  }

  if (modal) {
    modal.addEventListener("click", function (e) {
      if (e.target === modal || e.target.closest(".close")) closeAlbum();
    });
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && modal.classList.contains("on")) closeAlbum();
    });
  }
})();
