/* Фильтры, плеер Spotify и окно альбома. Без библиотек.

   Плитка сингла работает в два шага: нажатие на обложку только выбирает
   трек и зажигает кнопку плей, а звук запускает уже она. Так ничего не
   начинает играть само от случайного касания. */
(function () {
  "use strict";

  var ctrl = null;          // контроллер Spotify iFrame API
  var current = null;       // плитка, загруженная в плеер
  var armed = null;         // плитка, выбранная но ещё не запущенная
  var isPaused = true;
  var wantPlay = false;     // сафари на айфоне глушит автостарт
  var pendingUri = null;

  var grid = document.querySelector(".grid");
  var panel = document.getElementById("player");

  /* ── фильтры: жанр и роль, работают вместе ───────────────── */
  var bar = document.querySelector(".filterbar");
  var picked = { g: "ALL", r: "ALL" };

  function applyFilters() {
    document.querySelectorAll(".grid > li").forEach(function (li) {
      var tile = li.querySelector(".tile");
      if (!tile) return;
      var okGenre = picked.g === "ALL" || tile.dataset.g === picked.g;
      var roles = (tile.dataset.r || "").split(" ");
      var okRole = picked.r === "ALL" || roles.indexOf(picked.r) !== -1;
      li.hidden = !(okGenre && okRole);
    });
  }

  if (bar) {
    bar.addEventListener("click", function (e) {
      var btn = e.target.closest("button[data-f]");
      if (!btn) return;
      var row = btn.closest(".filters");
      picked[row.dataset.dim] = btn.dataset.f;
      row.querySelectorAll("button").forEach(function (b) {
        b.setAttribute("aria-pressed", String(b === btn));
      });
      applyFilters();
    });
  }

  /* ── состояние плиток ────────────────────────────────────── */
  function playBtn(tile) {
    return tile.parentElement.querySelector(".pbtn");
  }

  function refresh() {
    if (!grid) return;
    grid.querySelectorAll(".tile[data-id]").forEach(function (tile) {
      var btn = playBtn(tile);
      if (!btn) return;
      var isCurrent = tile === current;
      var show = tile === armed || isCurrent;
      btn.hidden = !show;
      var playing = isCurrent && !isPaused;
      btn.classList.toggle("on", playing);
      tile.classList.toggle("armed", tile === armed && !isCurrent);
      tile.classList.toggle("playing", isCurrent);
      var word = playing ? grid.dataset.pause : grid.dataset.listen;
      btn.setAttribute("aria-label", word + ": " + btn.dataset.label);
    });
  }

  function arm(tile) {
    armed = tile;
    refresh();
    var btn = playBtn(tile);
    if (btn) btn.focus();
  }

  function disarm() {
    if (!armed) return;
    armed = null;
    refresh();
  }

  /* ── плеер ───────────────────────────────────────────────── */
  window.onSpotifyIframeApiReady = function (IFrameAPI) {
    var el = document.getElementById("pframe");
    IFrameAPI.createController(el, { width: "100%", height: 80 }, function (c) {
      ctrl = c;
      c.addListener("playback_update", function (ev) {
        if (!current) return;
        isPaused = !!(ev && ev.data && ev.data.isPaused);
        if (wantPlay && isPaused) {
          try { c.resume(); } catch (err) { current.classList.add("retap"); }
        } else if (!isPaused) {
          wantPlay = false;
          current.classList.remove("retap");
        }
        refresh();
      });
      if (pendingUri) { start(pendingUri); pendingUri = null; }
    });
  };

  function start(uri) {
    ctrl.loadUri(uri);
    ctrl.play();
  }

  /* Запускает трек плитки. Повторный вызов на той же плитке — пауза. */
  window.play = function (tile) {
    var id = tile.dataset.id;
    if (!id) return;
    if (current === tile && ctrl) { ctrl.togglePlay(); return; }
    if (current && current !== tile) current.classList.remove("playing", "retap");
    current = tile;
    armed = null;
    isPaused = false;
    wantPlay = true;
    panel.classList.add("on");
    refresh();
    var uri = "spotify:track:" + id;
    if (ctrl) { start(uri); } else { pendingUri = uri; }
  };

  /* ── клики по сетке ──────────────────────────────────────── */
  if (grid) {
    grid.addEventListener("click", function (e) {
      var btn = e.target.closest(".pbtn");
      if (btn) {                       // второй шаг: играем
        window.play(btn.parentElement.querySelector(".tile"));
        return;
      }
      var tile = e.target.closest(".tile");
      if (!tile) return;
      if (tile.dataset.album !== undefined) {
        window.openAlbum(Number(tile.dataset.album));
      } else if (tile === current) {   // играющую плитку не сбрасываем
        window.play(tile);
      } else {                         // первый шаг: только выбираем
        arm(tile);
      }
    });
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape") disarm();
    });
  }

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
