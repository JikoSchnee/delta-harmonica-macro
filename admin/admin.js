(() => {
  const versionNodes = [...document.querySelectorAll("[data-site-version]")];
  const fallback = document.documentElement.dataset.siteVersion || "3.1.0";

  function applyVersion(version) {
    const value = String(version || fallback).trim() || fallback;
    versionNodes.forEach((node) => {
      node.textContent = `ADMIN v${value} · WEB SYNC`;
      node.setAttribute("aria-label", `后台版本 v${value}，与网页同步`);
    });
    document.title = `${document.title.replace(/ · v\d+\.\d+\.\d+$/, "")} · v${value}`;
  }

  applyVersion(fallback);
  fetch("../version.json", { cache: "no-store" })
    .then((response) => {
      if (!response.ok) throw new Error("version metadata request failed");
      return response.json();
    })
    .then((metadata) => applyVersion(metadata?.version))
    .catch(() => {});
})();
