// AmberSync - AGPL-3.0-or-later
// Keeps the job panel current without reloading the page the user is reading.
(function () {
  var container = document.getElementById("jobs");
  if (!container) return;

  var wasBusy = false;

  function humanBytes(value) {
    var units = ["B", "KB", "MB", "GB", "TB"];
    var index = 0;
    while (value >= 1024 && index < units.length - 1) { value /= 1024; index++; }
    return (index === 0 ? value : value.toFixed(1)) + " " + units[index];
  }

  function render(jobs) {
    if (!jobs.length) {
      container.innerHTML = "";
      return;
    }
    container.innerHTML = jobs.map(function (job) {
      var meta = [job.percent + " %"];
      if (job.bytes_total) {
        meta.push(humanBytes(job.bytes_done) + " / " + humanBytes(job.bytes_total));
      }
      if (job.files_total) {
        meta.push(job.files_done.toLocaleString() + " / " + job.files_total.toLocaleString());
      }
      var pauseAction = job.state === "paused" ? "resume" : "pause";
      var pauseLabel = job.state === "paused" ? "▶" : "⏸";
      return '<div class="job ' + job.state + '">' +
        '<div class="job-head"><strong>' + escapeHtml(job.label) + "</strong>" +
        '<span class="tag">' + job.state + "</span>" +
        (job.phase ? '<span class="tag quiet">' + job.phase + "</span>" : "") +
        "</div>" +
        '<div class="bar"><span style="width:' + job.percent + '%"></span></div>' +
        '<div class="job-meta"><span>' + meta.join("</span><span>") + "</span>" +
        (job.current_path ? '<span class="path">' + escapeHtml(job.current_path) + "</span>" : "") +
        "</div>" +
        '<form class="inline" method="post" action="/jobs/' + job.id + "/" + pauseAction + '">' +
        "<button>" + pauseLabel + "</button></form>" +
        '<form class="inline" method="post" action="/jobs/' + job.id + '/cancel">' +
        '<button class="danger">✕</button></form>' +
        (job.message ? '<p class="quiet small">' + escapeHtml(job.message) + "</p>" : "") +
        "</div>";
    }).join("");
  }

  function escapeHtml(text) {
    return String(text).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  function poll() {
    fetch("/api/jobs", { cache: "no-store" })
      .then(function (response) { return response.json(); })
      .then(function (data) {
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
