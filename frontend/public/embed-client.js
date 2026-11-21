(function () {
  "use strict";
  var config = JSON.parse(document.getElementById("config").textContent),
    messages = document.getElementById("messages"),
    input = document.getElementById("question"),
    send = document.getElementById("send");
  config.token =
    new URLSearchParams(window.location.hash.slice(1)).get("token") || "";
  function message(text, type) {
    var p = document.createElement("p");
    p.className = type;
    p.textContent = text;
    messages.appendChild(p);
    messages.scrollTop = messages.scrollHeight;
    return p;
  }
  send.disabled = true;
  fetch("/api/v1/public/" + encodeURIComponent(config.project) + "/config", {
    credentials: "omit",
    headers: { Authorization: "Bearer " + config.token },
  })
    .then(async function (response) {
      if (!response.ok)
        throw new Error("Assistant unavailable or access revoked.");
      Object.assign(config, await response.json());
      document.getElementById("title").textContent = config.title;
      document.documentElement.style.setProperty("--accent", config.color);
      document.body.dataset.theme = config.theme;
      message(config.welcome, "assistant");
      send.disabled = false;
    })
    .catch(function (error) {
      message(error.message, "error");
    });
  document
    .getElementById("form")
    .addEventListener("submit", async function (event) {
      event.preventDefault();
      var question = input.value.trim();
      if (question.length < 2) return;
      input.value = "";
      message(question, "user");
      send.disabled = true;
      var pending = message("Finding supporting evidence…", "assistant");
      try {
        var response = await fetch(
          "/api/v1/public/" + encodeURIComponent(config.project) + "/query",
          {
            method: "POST",
            credentials: "omit",
            headers: {
              "Content-Type": "application/json",
              Authorization: "Bearer " + config.token,
            },
            body: JSON.stringify({ question: question }),
          },
        );
        var data = await response.json();
        if (!response.ok)
          throw new Error(
            typeof data.detail === "string"
              ? data.detail
              : "The assistant is unavailable.",
          );
        pending.textContent = data.answer;
        data.citations.forEach(function (c) {
          var details = document.createElement("details"),
            summary = document.createElement("summary"),
            quote = document.createElement("p");
          summary.textContent = "[" + c.number + "] " + c.document_name;
          quote.textContent = c.quote;
          details.appendChild(summary);
          details.appendChild(quote);
          messages.appendChild(details);
        });
      } catch (error) {
        pending.textContent = error.message;
        pending.className = "error";
      } finally {
        send.disabled = false;
        messages.scrollTop = messages.scrollHeight;
        input.focus();
      }
    });
})();
