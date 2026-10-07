// Live comparison console by default; the static trace viewer stays available behind ?mode=replay.
const mode = new URLSearchParams(location.search).get("mode");
if (mode === "replay") {
  document.body.classList.add("replay");
  import("./replay.js");
} else {
  document.body.classList.add("live");
  import("./live_app.js").then((m) => m.start());
}
