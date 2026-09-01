(function () {
  "use strict";
  var CAT = JSON.parse(document.getElementById("catalog").textContent);
  var S;
  try { S = JSON.parse(document.getElementById("state").textContent); } catch (e) { S = null; }
  if (!S || typeof S !== "object") S = {};
  if (!S.edits) S.edits = {};
  if (!S.adds) S.adds = [];

  var FONTS =
    '<link rel="preconnect" href="https://fonts.googleapis.com">\n' +
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>\n' +
    '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Oswald:wght@500;700' +
    '&family=Golos+Text:wght@400;500;700&subset=cyrillic,latin&display=swap">';

  var ORDER = CAT.roleOrder, WORD = CAT.roles;
  var byslug = {};
  CAT.items.forEach(function (it) { byslug[it.slug] = it; });

  var root = document.getElementById("root");
  var tab = "cat", q = "", onlyChanged = false, open = null;
  var api = null, apiReady = false, saveState = "", timer = null;
  var lastFocus = null, sheetFocused = false;

  if (typeof claude !== "undefined" && claude.use) {
    claude.use("artifact").then(function (a) {
      api = a; apiReady = true;
      if (!a) { saveState = "nosave"; paint(); } else { paintDock(); }
    }, function () { apiReady = true; saveState = "nosave"; paint(); });
  } else {
    apiReady = true; saveState = "nosave";
  }

  /* ── состояние правок ───────────────────────────────────── */
  function edit(slug) {
    if (!S.edits[slug]) {
      var it = byslug[slug];
      S.edits[slug] = { artist: it.artist, title: it.title };
    }
    return S.edits[slug];
  }
  function clean(slug) {
    var e = S.edits[slug];
    if (!e) return;
    var real = Object.keys(e).filter(function (k) {
      return k !== "artist" && k !== "title";
    });
    if (!real.length) delete S.edits[slug];
  }
  function effRoles(it) {
    var e = S.edits[it.slug];
    return (e && e.roles) || it.roles;
  }
  function effTrackRoles(it, i) {
    var t = S.edits[it.slug] && S.edits[it.slug].tracks &&
            S.edits[it.slug].tracks[i];
    return (t && t.roles) || it.tracks[i].roles;
  }
  function effAbout(it) {
    var e = S.edits[it.slug];
    return e && typeof e.about === "string" ? e.about : it.about;
  }
  function effTrackAbout(it, i) {
    var t = S.edits[it.slug] && S.edits[it.slug].tracks &&
            S.edits[it.slug].tracks[i];
    return t && typeof t.about === "string" ? t.about : it.tracks[i].about;
  }
  function trackEdit(it, i) {
    var e = edit(it.slug);
    if (!e.tracks) e.tracks = {};
    if (!e.tracks[i]) e.tracks[i] = {};
    return e.tracks[i];
  }
  function pruneTrack(it, i) {
    var e = S.edits[it.slug];
    if (!e || !e.tracks || !e.tracks[i]) return;
    if (!Object.keys(e.tracks[i]).length) delete e.tracks[i];
    if (!Object.keys(e.tracks).length) delete e.tracks;
    clean(it.slug);
  }
  function effGenre(it) {
    var e = S.edits[it.slug];
    return e && typeof e.genre === "string" ? e.genre : it.genre;
  }
  function effHidden(it) {
    var e = S.edits[it.slug];
    return e && typeof e.hidden === "boolean" ? e.hidden : !!it.hidden;
  }
  function changed(it) { return !!S.edits[it.slug]; }
  function count() { return Object.keys(S.edits).length + S.adds.length; }
  function same(a, b) {
    return a.length === b.length && a.every(function (v, i) { return v === b[i]; });
  }
  function albumRoles(it) {
    if (it.type !== "album") return effRoles(it);
    var set = {};
    it.tracks.forEach(function (tr, i) {
      effTrackRoles(it, i).forEach(function (r) { set[r] = 1; });
    });
    return ORDER.filter(function (r) { return set[r]; });
  }

  /* правка без перерисовки всей страницы — чтобы окно не прыгало */
  function touch() {
    S.updated = new Date().toISOString();
    paintDock();
    schedule();
  }
  function mutate(fn) { fn(); S.updated = new Date().toISOString(); paint(); schedule(); }

  /* ── сохранение через публикацию новой версии ───────────── */
  function schedule() {
    if (!api) { saveState = "nosave"; paintDock(); return; }
    if (timer) clearTimeout(timer);
    saveState = "wait";
    paintDock();
    timer = setTimeout(function () {
      timer = null;
      saveState = "saving";
      paintDock();
      api.publish(buildDoc()).then(function () {
        saveState = "saved"; paintDock();
      }, function (err) {
        saveState = (err && err.code === "conflict") ? "conflict" : "error";
        paintDock();
      });
    }, 1200);
  }

  function esc(s) { return s.replace(/</g, "\\u003c"); }
  var SHUT = "</scr" + "ipt>";
  function openTag(id, type) {
    return "<scr" + "ipt id=\"" + id + "\"" +
           (type ? " type=\"" + type + "\"" : "") + ">";
  }
  function buildDoc() {
    return "<!doctype html>\n<html lang=\"ru\">\n<head>\n" +
      "<meta charset=\"utf-8\">\n" +
      "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">\n" +
      "<title>Песочница КАССЫ</title>\n" + FONTS + "\n" +
      "<style id=\"css\">" + document.getElementById("css").textContent +
      "</sty" + "le>\n</head>\n<body>\n<div id=\"root\"></div>\n" +
      openTag("catalog", "application/json") +
        esc(document.getElementById("catalog").textContent) + SHUT + "\n" +
      openTag("state", "application/json") + esc(JSON.stringify(S)) + SHUT + "\n" +
      openTag("app", "") + document.getElementById("app").textContent + SHUT +
      "\n</body>\n</html>";
  }

  /* ── помощники ──────────────────────────────────────────── */
  function el(tag, cls, txt) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (txt != null) n.textContent = txt;
    return n;
  }
  function roleWords(list) {
    return ORDER.filter(function (r) { return list.indexOf(r) > -1; })
                .map(function (r) { return WORD[r]; });
  }
  function genreLabel(code) {
    var g = CAT.genres.filter(function (x) { return x.code === code; })[0];
    return g ? g.label : "без жанра";
  }
  function cover(h) { return CAT.covers[h] || ""; }

  /* панель ролей: сама себя подсвечивает, страницу не трогает */
  function rolePicker(get, set) {
    var box = el("div", "rr"), btns = [];
    function sync() {
      var now = get();
      btns.forEach(function (p) {
        p.b.setAttribute("aria-pressed", now.indexOf(p.r) > -1 ? "true" : "false");
      });
    }
    ORDER.forEach(function (r) {
      var b = el("button", "rb", WORD[r]);
      b.type = "button";
      b.addEventListener("click", function () {
        var next = get().slice(), at = next.indexOf(r);
        if (at > -1) next.splice(at, 1); else next.push(r);
        set(ORDER.filter(function (x) { return next.indexOf(x) > -1; }));
        sync();
      });
      btns.push({ b: b, r: r });
      box.appendChild(b);
    });
    sync();
    return box;
  }
  /* описание: пусто — собирается само, поэтому автотекст стоит подсказкой */
  function aboutField(get, auto, set, withHint) {
    var box = el("div", "fld");
    box.appendChild(el("span", "lbl", "Описание"));
    var ta = el("textarea", "ta");
    ta.value = get() || "";
    ta.placeholder = auto;
    ta.rows = 3;
    ta.setAttribute("aria-label", "Описание трека");
    function mark() { ta.className = "ta" + (ta.value.trim() ? " own" : ""); }
    mark();
    var take, drop;
    function tools() {
      take.disabled = !!ta.value.trim();
      drop.disabled = !ta.value.trim();
    }
    ta.addEventListener("input", function () {
      set(ta.value);
      mark();
      tools();
    });
    box.appendChild(ta);
    var row = el("div", "tools");
    take = el("button", "tiny", "Взять автотекст");
    take.type = "button";
    take.addEventListener("click", function () {
      ta.value = auto;
      set(auto);
      mark();
      tools();
      ta.focus();
    });
    drop = el("button", "tiny", "Вернуть автотекст");
    drop.type = "button";
    drop.addEventListener("click", function () {
      ta.value = "";
      set("");
      mark();
      tools();
    });
    row.appendChild(take);
    row.appendChild(drop);
    box.appendChild(row);
    tools();
    if (withHint) {
      box.appendChild(el("p", "hint",
        "Пусто — строка соберётся сама, как сейчас в подсказке. Свой текст заменит её " +
        "и на странице, и в описании для поиска. Пустая строка между абзацами разбивает текст."));
    }
    return box;
  }

  function genreSelect(value, zero, onPick) {
    var sel = el("select", "sel");
    var o0 = el("option", null, zero);
    o0.value = "";
    sel.appendChild(o0);
    CAT.genres.forEach(function (g) {
      var o = el("option", null, g.label);
      o.value = g.code;
      sel.appendChild(o);
    });
    sel.value = value || "";
    sel.addEventListener("change", function () { onPick(sel.value); });
    return sel;
  }

  /* ── каталог ────────────────────────────────────────────── */
  function viewCatalog() {
    var box = el("div"), bar = el("div", "bar");
    var inp = el("input", "search");
    inp.type = "search";
    inp.placeholder = "Артист или название";
    inp.value = q;
    inp.setAttribute("aria-label", "Поиск по каталогу");
    inp.addEventListener("input", function () { q = inp.value; regrid(); });
    bar.appendChild(inp);
    var lab = el("label", "toggle"), chk = el("input");
    chk.type = "checkbox";
    chk.checked = onlyChanged;
    chk.addEventListener("change", function () { onlyChanged = chk.checked; regrid(); });
    lab.appendChild(chk);
    lab.appendChild(el("span", null, "только изменённые"));
    bar.appendChild(lab);
    box.appendChild(bar);
    var grid = el("div", "grid");
    grid.id = "grid";
    box.appendChild(grid);
    fillGrid(grid);
    return box;
  }
  function regrid() {
    var g = document.getElementById("grid");
    if (g) { g.textContent = ""; fillGrid(g); }
  }
  function fillGrid(grid) {
    var needle = q.trim().toLowerCase();
    var list = CAT.items.filter(function (it) {
      if (onlyChanged && !changed(it)) return false;
      if (!needle) return true;
      if ((it.artist + " " + it.title).toLowerCase().indexOf(needle) > -1) return true;
      return it.tracks.some(function (t) {
        return t.title.toLowerCase().indexOf(needle) > -1;
      });
    });
    if (!list.length) {
      grid.appendChild(el("p", "empty", "Ничего не нашлось"));
      return;
    }
    list.forEach(function (it) {
      var t = el("button", "tile" + (changed(it) ? " changed" : "") +
                           (effHidden(it) ? " hid" : ""));
      t.type = "button";
      if (changed(it)) t.appendChild(el("span", "flag", "правка"));
      else if (it.type === "album") t.appendChild(el("span", "flag mut", it.tracks.length + " трека"));
      var img = el("img", "cov");
      img.src = cover(it.cover);
      img.alt = "";
      img.loading = "lazy";
      t.appendChild(img);
      var m = el("div", "meta");
      m.appendChild(el("div", "art", it.artist));
      m.appendChild(el("div", "ttl", it.title));
      var chips = el("div", "chips");
      roleWords(albumRoles(it)).forEach(function (w) { chips.appendChild(el("span", "chip", w)); });
      if (effHidden(it)) chips.appendChild(el("span", "chip", "скрыт"));
      m.appendChild(chips);
      t.appendChild(m);
      t.addEventListener("click", function () { openSheet(it.slug); });
      grid.appendChild(t);
    });
  }

  /* ── окно правки ────────────────────────────────────────── */
  function openSheet(slug) {
    lastFocus = document.activeElement;
    sheetFocused = false;
    open = slug;
    document.body.style.overflow = "hidden";
    paint();
  }
  function closeSheet() {
    open = null;
    document.body.style.overflow = "";
    paint();
    if (lastFocus && lastFocus.focus) lastFocus.focus();
    lastFocus = null;
  }
  var FOCUSABLE = "button:not([disabled]),select,input,a[href],[tabindex]:not([tabindex='-1'])";

  function sheet() {
    var it = byslug[open];
    var back = el("div", "sheet");
    back.addEventListener("click", function (e) {
      if (e.target === back) closeSheet();
    });
    var close = closeSheet;
    back.addEventListener("keydown", function (e) {
      if (e.key !== "Tab") return;
      var f = card.querySelectorAll(FOCUSABLE);
      if (!f.length) return;
      var first = f[0], last = f[f.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault(); last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault(); first.focus();
      }
    });

    var card = el("div", "card");
    card.setAttribute("role", "dialog");
    card.setAttribute("aria-modal", "true");
    card.setAttribute("aria-label", it.artist + " — " + it.title);

    var head = el("div", "chead");
    var img = el("img");
    img.src = cover(it.cover);
    img.alt = "";
    head.appendChild(img);
    var h = el("div");
    h.appendChild(el("div", "art", it.artist));
    h.appendChild(el("h2", null, it.title));
    h.appendChild(el("div", "yr", (it.year || "") +
      (it.type === "album" ? " · альбом, " + it.tracks.length + " трека" : "")));
    head.appendChild(h);
    var x = el("button", "x", "×");
    x.type = "button";
    x.setAttribute("aria-label", "Закрыть");
    x.addEventListener("click", close);
    head.appendChild(x);
    card.appendChild(head);

    var undo;
    function refreshUndo() { if (undo) undo.disabled = !changed(it); }

    if (it.type === "album") {
      var f0 = el("div", "fld");
      f0.appendChild(el("span", "lbl", "Роли и описания по трекам"));
      f0.appendChild(el("p", "hint",
        "У каждого трека альбома своя страница. Пустое описание собирается само — " +
        "то, что стоит подсказкой в поле. Пустая строка между абзацами разбивает текст."));
      it.tracks.forEach(function (tr, i) {
        var row = el("div", "trk");
        row.appendChild(el("p", "tn", tr.title));
        row.appendChild(rolePicker(
          function () { return effTrackRoles(it, i); },
          function (next) {
            if (same(next, it.tracks[i].roles)) delete trackEdit(it, i).roles;
            else trackEdit(it, i).roles = next;
            pruneTrack(it, i);
            refreshUndo();
            touch();
          }));
        row.appendChild(aboutField(
          function () { return effTrackAbout(it, i); },
          it.tracks[i].auto,
          function (text) {
            if (text.trim() === (it.tracks[i].about || "").trim()) {
              delete trackEdit(it, i).about;
            } else trackEdit(it, i).about = text;
            pruneTrack(it, i);
            refreshUndo();
            touch();
          }, false));
        f0.appendChild(row);
      });
      card.appendChild(f0);
    } else {
      var f1 = el("div", "fld");
      f1.appendChild(el("span", "lbl", "Роли"));
      f1.appendChild(rolePicker(
        function () { return effRoles(it); },
        function (next) {
          var e = edit(it.slug);
          if (same(next, it.roles)) delete e.roles; else e.roles = next;
          clean(it.slug);
          refreshUndo();
          touch();
        }));
      card.appendChild(f1);
      card.appendChild(aboutField(
        function () { return effAbout(it); },
        it.auto,
        function (text) {
          var e = edit(it.slug);
          if (text.trim() === (it.about || "").trim()) delete e.about;
          else e.about = text;
          clean(it.slug);
          refreshUndo();
          touch();
        }, true));
    }

    var f2 = el("div", "fld");
    f2.appendChild(el("span", "lbl", "Жанр"));
    f2.appendChild(genreSelect(effGenre(it), "— без жанра —", function (v) {
      var e = edit(it.slug);
      if ((v || null) === (it.genre || null)) delete e.genre; else e.genre = v;
      clean(it.slug);
      refreshUndo();
      touch();
    }));
    card.appendChild(f2);

    var f3 = el("div", "fld");
    var lab = el("label", "toggle"), chk = el("input");
    chk.type = "checkbox";
    chk.checked = effHidden(it);
    chk.addEventListener("change", function () {
      var e = edit(it.slug);
      if (chk.checked === !!it.hidden) delete e.hidden; else e.hidden = chk.checked;
      clean(it.slug);
      refreshUndo();
      touch();
    });
    lab.appendChild(chk);
    lab.appendChild(el("span", null, "спрятать с сайта"));
    f3.appendChild(lab);
    f3.appendChild(el("p", "hint",
      "Работа пропадёт с витрины и из каталога. Страница трека останется по прямой ссылке."));
    card.appendChild(f3);

    var row = el("div", "row");
    undo = el("button", "btn dim", "Отменить правку");
    undo.type = "button";
    undo.addEventListener("click", function () {
      mutate(function () { delete S.edits[it.slug]; });
    });
    refreshUndo();
    row.appendChild(undo);
    var done = el("button", "btn on", "Готово");
    done.type = "button";
    done.addEventListener("click", close);
    row.appendChild(done);
    card.appendChild(row);

    back.appendChild(card);
    if (!sheetFocused) {
      sheetFocused = true;
      setTimeout(function () {
        var f = card.querySelector(FOCUSABLE);
        if (f) f.focus();
      }, 0);
    }
    return back;
  }

  /* ── добавление трека ───────────────────────────────────── */
  var draft = { url: "", roles: ["mix"], genre: "", note: "" };
  function draftOk() {
    return draft.roles.length > 0 && /open\.spotify\.com\/\S+/.test(draft.url.trim());
  }
  function viewAdd() {
    var box = el("div", "form"), btn;
    var f1 = el("div", "fld");
    f1.appendChild(el("span", "lbl", "Ссылка на Spotify"));
    var inp = el("input", "inp");
    inp.type = "url";
    inp.placeholder = "https://open.spotify.com/track/…";
    inp.value = draft.url;
    inp.addEventListener("input", function () {
      draft.url = inp.value;
      if (btn) btn.disabled = !draftOk();
    });
    f1.appendChild(inp);
    f1.appendChild(el("p", "hint",
      "Трек, альбом или плейлист целиком. Название, артист, год и обложка приедут сами."));
    box.appendChild(f1);

    var f2 = el("div", "fld");
    f2.appendChild(el("span", "lbl", "Твои роли"));
    f2.appendChild(rolePicker(
      function () { return draft.roles; },
      function (next) { draft.roles = next; if (btn) btn.disabled = !draftOk(); }));
    box.appendChild(f2);

    var f3 = el("div", "fld");
    f3.appendChild(el("span", "lbl", "Жанр"));
    f3.appendChild(genreSelect(draft.genre, "— определить по артисту —",
      function (v) { draft.genre = v; }));
    box.appendChild(f3);

    var f4 = el("div", "fld");
    f4.appendChild(el("span", "lbl", "Заметка"));
    var note = el("input", "inp");
    note.placeholder = "если нужно что-то уточнить";
    note.value = draft.note;
    note.addEventListener("input", function () { draft.note = note.value; });
    f4.appendChild(note);
    box.appendChild(f4);

    btn = el("button", "btn on", "В список");
    btn.type = "button";
    btn.disabled = !draftOk();
    btn.addEventListener("click", function () {
      mutate(function () {
        S.adds.push({ url: draft.url.trim(), roles: draft.roles.slice(),
                      genre: draft.genre, note: draft.note.trim() });
        draft = { url: "", roles: ["mix"], genre: "", note: "" };
      });
    });
    box.appendChild(btn);

    if (S.adds.length) {
      var list = el("div", "added");
      list.appendChild(el("span", "lbl", "В очереди на добавление"));
      S.adds.forEach(function (a, i) {
        var c = el("div", "acard"), d = el("div");
        d.appendChild(el("div", "u", a.url));
        var chips = el("div", "chips");
        roleWords(a.roles).forEach(function (w) { chips.appendChild(el("span", "chip", w)); });
        if (a.genre) chips.appendChild(el("span", "chip", genreLabel(a.genre)));
        d.appendChild(chips);
        if (a.note) d.appendChild(el("p", "hint", a.note));
        c.appendChild(d);
        var rm = el("button", "x", "×");
        rm.type = "button";
        rm.style.marginLeft = "auto";
        rm.setAttribute("aria-label", "Убрать из списка");
        rm.addEventListener("click", function () {
          mutate(function () { S.adds.splice(i, 1); });
        });
        c.appendChild(rm);
        list.appendChild(c);
      });
      box.appendChild(list);
    }
    return box;
  }

  /* ── сводка ─────────────────────────────────────────────── */
  function aboutLine(auto, own) {
    var p = el("p");
    if (!own.trim()) {
      p.appendChild(document.createTextNode("описание: "));
      p.appendChild(el("span", "was", "своё"));
      p.appendChild(document.createTextNode("  →  "));
      p.appendChild(el("span", "now", "снова собирается само"));
      return p;
    }
    p.appendChild(el("span", "was", auto));
    p.appendChild(el("br"));
    p.appendChild(el("span", "now", own.replace(/\s+/g, " ")));
    return p;
  }
  function arrow(p, was, now) {
    p.appendChild(el("span", "was", was));
    p.appendChild(document.createTextNode("  →  "));
    p.appendChild(el("span", "now", now));
  }
  function viewSum() {
    var box = el("div", "sum");
    if (!count()) {
      box.appendChild(el("p", "empty",
        "Правок пока нет. Открой любую работу в каталоге или добавь трек."));
      return box;
    }
    Object.keys(S.edits).forEach(function (slug) {
      var it = byslug[slug], e = S.edits[slug], c = el("div", "sitem");
      c.appendChild(el("h3", null, it.artist + " — " + it.title));
      if (e.roles) {
        var p = el("p");
        arrow(p, roleWords(it.roles).join(", ") || "без ролей",
                 roleWords(e.roles).join(", ") || "без ролей");
        c.appendChild(p);
      }
      if (typeof e.about === "string") c.appendChild(aboutLine(it.auto, e.about));
      if (e.tracks) {
        Object.keys(e.tracks).forEach(function (i) {
          var t = e.tracks[i];
          if (t.roles) {
            var p2 = el("p");
            p2.appendChild(document.createTextNode(it.tracks[i].title + ": "));
            arrow(p2, roleWords(it.tracks[i].roles).join(", ") || "без ролей",
                      roleWords(t.roles).join(", ") || "без ролей");
            c.appendChild(p2);
          }
          if (typeof t.about === "string") {
            var p4 = el("p");
            p4.appendChild(document.createTextNode(it.tracks[i].title + ": описание"));
            c.appendChild(p4);
            c.appendChild(aboutLine(it.tracks[i].auto, t.about));
          }
        });
      }
      if (typeof e.genre === "string") {
        var p3 = el("p");
        p3.appendChild(document.createTextNode("жанр: "));
        arrow(p3, genreLabel(it.genre), genreLabel(e.genre));
        c.appendChild(p3);
      }
      if (typeof e.hidden === "boolean") {
        c.appendChild(el("p", null, e.hidden ? "спрятать с сайта" : "вернуть на сайт"));
      }
      box.appendChild(c);
    });
    S.adds.forEach(function (a) {
      var c = el("div", "sitem");
      c.appendChild(el("h3", null, "Добавить трек"));
      c.appendChild(el("p", null, a.url));
      c.appendChild(el("p", null, "роли: " + roleWords(a.roles).join(", ") +
        (a.genre ? " · жанр: " + genreLabel(a.genre) : "")));
      if (a.note) c.appendChild(el("p", null, a.note));
      box.appendChild(c);
    });
    var say = el("div", "say");
    say.appendChild(el("p", "lbl", "Как выкатить на сайт"));
    var p = el("p");
    p.style.margin = "8px 0 0";
    p.appendChild(document.createTextNode("Песочница ничего не меняет на "));
    p.appendChild(el("span", "now", "credits.kaccamusic.com"));
    p.appendChild(document.createTextNode(" сама — она копит правки. Когда список готов, напиши Клоду "));
    p.appendChild(el("code", null, "забирай правки из песочницы"));
    p.appendChild(document.createTextNode(": он прочитает эту страницу, применит всё к данным, пересоберёт сайт и зальёт."));
    say.appendChild(p);
    box.appendChild(say);
    return box;
  }

  /* ── сборка страницы ────────────────────────────────────── */
  function paint() {
    root.textContent = "";
    var hd = el("header"), w1 = el("div", "wrap"), top = el("div", "top");
    var svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("class", "mark");
    svg.setAttribute("viewBox", "25 35 135 82");
    svg.setAttribute("aria-hidden", "true");
    svg.innerHTML = CAT.logo;
    top.appendChild(svg);
    top.appendChild(el("h1", "name", "КАССА"));
    top.appendChild(el("span", "badge", "песочница"));
    w1.appendChild(top);
    w1.appendChild(el("p", "sub",
      "Черновик сайта. Правь роли, жанры и видимость, складывай новые треки — всё копится здесь и уезжает на сайт только по твоей команде."));
    var tabs = el("div", "tabs");
    [["cat", "Каталог", CAT.items.length],
     ["add", "Добавить трек", S.adds.length],
     ["sum", "Сводка", count()]].forEach(function (t) {
      var b = el("button", "tab");
      b.type = "button";
      b.setAttribute("aria-selected", tab === t[0] ? "true" : "false");
      b.appendChild(document.createTextNode(t[1]));
      if (t[2]) b.appendChild(el("span", "n", String(t[2])));
      b.addEventListener("click", function () { tab = t[0]; paint(); });
      tabs.appendChild(b);
    });
    w1.appendChild(tabs);
    hd.appendChild(w1);
    root.appendChild(hd);

    var main = el("main"), w2 = el("div", "wrap");
    if (apiReady && !api) {
      w2.appendChild(el("p", "ro",
        "Страница открыта без права записи: правки будут видны только тебе и пропадут при перезагрузке."));
    }
    w2.appendChild(tab === "cat" ? viewCatalog() : tab === "add" ? viewAdd() : viewSum());
    main.appendChild(w2);
    root.appendChild(main);
    if (open) root.appendChild(sheet());
    paintDock();
  }

  function paintDock() {
    var old = document.getElementById("dock");
    if (old) old.remove();
    var d = el("div", "dock");
    d.id = "dock";
    var w = el("div", "wrap"), n = count(), c = el("div", "cnt");
    if (n) {
      c.appendChild(document.createTextNode("правок: "));
      c.appendChild(el("b", null, String(n)));
    } else c.textContent = "правок нет";
    w.appendChild(c);
    var st = el("div", "state");
    var msg = { wait: "сохраняю…", saving: "сохраняю…", saved: "сохранено",
                error: "не сохранилось — правка живёт только в этом окне",
                conflict: "страницу изменили в другом окне, обнови",
                nosave: "только просмотр" }[saveState];
    if (msg) st.appendChild(el("span",
      "saved" + (saveState === "error" || saveState === "conflict" ? " err" : ""), msg));
    if (n) {
      var go = el("button", "btn" + (tab === "sum" ? " on" : ""), "Сводка правок");
      go.type = "button";
      go.addEventListener("click", function () {
        tab = "sum";
        if (open) closeSheet(); else paint();
      });
      st.appendChild(go);
    }
    w.appendChild(st);
    d.appendChild(w);
    root.appendChild(d);
  }

  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && open) closeSheet();
  });

  paint();
})();
