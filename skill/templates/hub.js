/* Поиск по каталогу работ. Без библиотек, всё уже в разметке.

   У каждого артиста, альбома и трека лежит data-s — текст и его латиница
   сразу. Запрос тоже приводим к обеим формам, поэтому «клава», «klava»
   и «Koka» находят одно и то же. */
(function () {
  "use strict";

  var input = document.getElementById("q");
  if (!input) return;

  var clear = document.getElementById("qclear");
  var counter = document.getElementById("counter");
  var nohits = document.getElementById("nohits");
  var alpha = document.querySelector(".alpha");
  var arts = [].slice.call(document.querySelectorAll(".art"));
  var letters = [].slice.call(document.querySelectorAll(".ltr"));
  var tpl = counter ? counter.dataset.tpl : "";
  // формы слов приходят из разметки, чтобы скрипт не знал языка
  var TW = counter ? (counter.dataset.tw || "").split("|") : [];
  var AW = counter ? (counter.dataset.aw || "").split("|") : [];

  var TRANSLIT = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e",
    "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "h", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "sch",
    "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya"
  };

  function norm(s) {
    return String(s || "").toLowerCase().replace(/ё/g, "е")
      .replace(/\s+/g, " ").trim();
  }

  function translit(s) {
    var out = "";
    for (var i = 0; i < s.length; i++) {
      var ch = s[i];
      out += TRANSLIT[ch] !== undefined ? TRANSLIT[ch] : ch;
    }
    return out;
  }

  /* Совпадение по любой из двух форм запроса. */
  function hits(hay, a, b) {
    return hay.indexOf(a) !== -1 || (b !== a && hay.indexOf(b) !== -1);
  }

  function plural(n, forms) {
    n = Math.abs(n);
    if (n % 10 === 1 && n % 100 !== 11) return forms[0];
    if (n % 10 >= 2 && n % 10 <= 4 && !(n % 100 >= 12 && n % 100 <= 14)) return forms[1];
    return forms[2];
  }

  function apply() {
    var raw = norm(input.value);
    var lat = translit(raw);
    var searching = raw.length > 0;
    clear.hidden = !searching;
    if (alpha) alpha.hidden = searching;

    var shownTracks = 0, shownArtists = 0;

    arts.forEach(function (art) {
      var artistHit = !searching || hits(art.dataset.s || "", raw, lat);
      var visible = 0;

      art.querySelectorAll("li[data-s]").forEach(function (li) {
        var ok = artistHit || hits(li.dataset.s || "", raw, lat);
        li.hidden = !ok;
        if (ok) visible++;
      });

      // блок альбома или синглов прячем, когда внутри ничего не осталось
      art.querySelectorAll(".alb, .sing").forEach(function (box) {
        var any = box.querySelector("li:not([hidden])");
        box.hidden = !any;
      });

      art.hidden = visible === 0;
      if (visible) {
        shownArtists++;
        shownTracks += visible;
        art.querySelector(".cnt").textContent = visible;
      }
    });

    // буква нужна, только если под ней остался хоть один артист
    letters.forEach(function (ltr) {
      var node = ltr.nextElementSibling, any = false;
      while (node && !node.classList.contains("ltr")) {
        if (node.classList.contains("art") && !node.hidden) { any = true; break; }
        node = node.nextElementSibling;
      }
      ltr.hidden = !any;
    });

    if (nohits) nohits.hidden = shownTracks !== 0;
    if (counter) {
      counter.textContent = searching
        ? shownTracks + " " + plural(shownTracks, TW)
          + " · " + shownArtists + " " + plural(shownArtists, AW)
        : tpl;
    }
  }

  input.addEventListener("input", apply);
  clear.addEventListener("click", function () {
    input.value = "";
    apply();
    input.focus();
  });
  input.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && input.value) {
      input.value = "";
      apply();
    }
  });
  // ?q= — на этот адрес указывает SearchAction в разметке главной, и по нему
  // же удобно дать готовую ссылку на поиск: «/track/?q=клава»
  var preset = new URLSearchParams(location.search).get("q");
  if (preset) input.value = preset;
  apply();
  if (preset) input.focus();
})();
