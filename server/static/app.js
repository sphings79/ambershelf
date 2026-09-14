// AmberShelf - AGPL-3.0-or-later
// Keeps the job panel current without reloading the page underneath it.
(function () {
  var container = document.getElementById("jobs");
  if (!container) return;

  var labels = JSON.parse(container.dataset.labels || "{}");
  var wasBusy = false;

  function humanBytes(value) {
    var units = ["B", "KB", "MB", "GB", "TB"];
    var index = 0;
    while (value >= 1024 && index < units.length - 1) { value /= 1024; index += 1; }
    return (index === 0 ? value : value.toFixed(1)) + " " + units[index];
  }

  function escapeHtml(text) {
    return String(text).replace(/[&<>"']/g, function (character) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[character];
    });
  }

  function svg(paths) {
    return '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor"' +
      ' stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">' + paths + "</svg>";
  }

  var ICON_PLAY = svg('<path d="M8 5.5 18.5 12 8 18.5V5.5Z"/>');
  var ICON_PAUSE = svg('<path d="M9 5.5v13M15 5.5v13"/>');
  var ICON_CLOSE = svg('<path d="M6 6l12 12M18 6 6 18"/>');

  function render(jobs) {
    if (!jobs.length) { container.innerHTML = ""; return; }

    container.innerHTML = jobs.map(function (job) {
      var meta = ["<span>" + job.percent + " %</span>"];
      if (job.bytes_total) {
        meta.push("<span>" + humanBytes(job.bytes_done) + " / " +
          humanBytes(job.bytes_total) + "</span>");
      }
      if (job.files_total) {
        meta.push("<span>" + job.files_done.toLocaleString() + " / " +
          job.files_total.toLocaleString() + "</span>");
      }
      if (job.current_path) {
        meta.push('<span class="path">' + escapeHtml(job.current_path) + "</span>");
      }

      var paused = job.state === "paused";
      var stateLabel = labels[job.state] || job.state;
      var phaseLabel = job.phase ? (labels["phase." + job.phase] || job.phase) : "";

      return '<div class="job ' + job.state + '">' +
        '<div class="job-head">' +
          "<strong>" + escapeHtml(job.label) + "</strong>" +
          '<span class="chip ' + (paused ? "warn" : "accent") + '">' + stateLabel + "</span>" +
          (phaseLabel ? '<span class="chip outline">' + phaseLabel + "</span>" : "") +
          '<span class="spacer">' +
            '<form class="inline" method="post" action="/jobs/' + job.id +
              (paused ? "/resume" : "/pause") + '">' +
              '<button class="quiet icon-only">' + (paused ? ICON_PLAY : ICON_PAUSE) + "</button></form>" +
            '<form class="inline" method="post" action="/jobs/' + job.id + '/cancel">' +
              '<button class="quiet icon-only danger">' + ICON_CLOSE + "</button></form>" +
          "</span>" +
        "</div>" +
        '<div class="meter' + (job.state === "running" ? " is-running" : "") + '">' +
          '<span style="width:' + job.percent + '%"></span></div>' +
        '<div class="job-meta">' + meta.join("") + "</div>" +
        "</div>";
    }).join("");
  }

  function poll() {
    fetch("/api/jobs", { cache: "no-store" })
      .then(function (response) {
        // The session can expire while a page sits open; say so rather than
        // leaving a progress panel that quietly stopped moving.
        if (response.status === 401) {
          window.location.href = "/login";
          return null;
        }
        return response.json();
      })
      .then(function (data) {
        if (!data) { return; }
        render(data.active);
        var busy = data.active.length > 0;
        // A finished job changes what the page below shows, so reload once.
        if (wasBusy && !busy) { window.location.reload(); }
        wasBusy = busy;
      })
      .catch(function () { /* the page stays usable without live progress */ });
  }

  poll();
  setInterval(poll, 2000);
})();

// --------------------------------------------------------------- messages
// A message is shown once and then gone - it is no longer carried in the
// address, so reloading will not bring it back. Which is exactly why only
// the harmless ones disappear on their own.
(function () {
  var notes = document.querySelectorAll(".flash");

  function dismiss(note) {
    note.style.opacity = "0";
    note.style.transition = "opacity .4s";
    setTimeout(function () { note.remove(); }, 400);
  }

  Array.prototype.forEach.call(notes, function (note) {
    var close = note.querySelector(".flash-close");
    if (close) {
      close.addEventListener("click", function () { dismiss(note); });
    }
    var seconds = parseInt(note.getAttribute("data-hide-after"), 10);
    if (seconds > 0) {
      var timer = setTimeout(function () { dismiss(note); }, seconds * 1000);
      // Reading it should not be a race: hovering keeps it on screen.
      note.addEventListener("mouseenter", function () { clearTimeout(timer); });
    }
  });
})();

// ------------------------------------------------------------- registering
// Nothing can be registered until a role has been chosen, and only then does
// the button start looking like one worth pressing.
(function () {
  Array.prototype.forEach.call(document.querySelectorAll(".register-form"), function (form) {
    var role = form.querySelector("select[name=role]");
    var button = form.querySelector("button");
    if (!role || !button) { return; }
    function sync() {
      var chosen = role.value !== "";
      button.disabled = !chosen;
      button.classList.toggle("primary", chosen);
      button.classList.toggle("quiet", !chosen);
    }
    role.addEventListener("change", sync);
    sync();
  });
})();

// ---------------------------------------------------------------- labels
// A volume label is as long as its filesystem allows: eleven characters on
// exFAT, thirty-two on NTFS. mkfs.exfat refuses a longer one instead of
// shortening it, so the field has to say so before the disk is erased.
(function () {
  Array.prototype.forEach.call(document.querySelectorAll(".fs-choice"), function (choice) {
    var form = choice.closest("form");
    var field = form && form.querySelector(".fs-label");
    if (!field) { return; }
    function sync() {
      var max = parseInt(choice.options[choice.selectedIndex]
        .getAttribute("data-label-max"), 10) || 11;
      field.maxLength = max;
      // Switching from NTFS to exFAT can leave a name that no longer fits.
      if (field.value.length > max) { field.value = field.value.slice(0, max); }
    }
    choice.addEventListener("change", sync);
    sync();
  });
})();
