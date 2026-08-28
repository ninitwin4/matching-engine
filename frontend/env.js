// Frontend config — which API the page talks to. Kept out of the app code so
// the same index.html works locally and when deployed.
//
// Local dev  -> the page is served from localhost, so it calls the local API.
// Deployed   -> anywhere else, it calls the hosted API below.
//
// After deploying the API to Render, replace PRODUCTION_API with that URL
// (e.g. "https://matching-engine-api.onrender.com" — no trailing slash).
(function () {
  var PRODUCTION_API = "https://matching-engine-api-15zp.onrender.com";
  var host = window.location.hostname;
  var isLocal = host === "localhost" || host === "127.0.0.1" || host === "";
  window.API_BASE = isLocal ? "http://localhost:8000" : PRODUCTION_API;
})();
