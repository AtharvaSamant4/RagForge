(function () {
  "use strict";
  var script = document.currentScript;
  if (!script || !script.dataset.project || !script.dataset.token) return;
  var origin = new URL(script.src).origin;
  var button = document.createElement("button");
  button.textContent = "Ask a question";
  button.setAttribute("aria-label", "Open knowledge assistant");
  button.style.cssText =
    "position:fixed;bottom:24px;right:24px;z-index:2147483000;background:#142c25;color:#b5f2da;border:1px solid #42715d;border-radius:28px;padding:14px 22px;font:500 15px system-ui;cursor:pointer;box-shadow:0 4px 24px #0003";
  var frame = document.createElement("iframe");
  frame.title = "Knowledge assistant";
  frame.referrerPolicy = "no-referrer";
  frame.src =
    origin +
    "/embed?project=" +
    encodeURIComponent(script.dataset.project) +
    "#token=" +
    encodeURIComponent(script.dataset.token);
  frame.style.cssText =
    "display:none;position:fixed;bottom:86px;right:24px;z-index:2147483000;width:min(400px,calc(100vw - 32px));height:min(600px,calc(100dvh - 115px));border:1px solid #3a4944;border-radius:16px;box-shadow:0 10px 80px #0005;background:#11171b";
  button.addEventListener("click", function () {
    var open = frame.style.display === "none";
    frame.style.display = open ? "block" : "none";
    button.textContent = open ? "Close assistant" : "Ask a question";
    button.setAttribute("aria-expanded", String(open));
  });
  document.body.appendChild(button);
  document.body.appendChild(frame);
})();
