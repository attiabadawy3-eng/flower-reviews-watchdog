/* FLOWER staging-only design switcher. No tracking, no dependencies. */
(() => {
  if (location.hostname !== "flower-unified-staging.onrender.com") return;
  const ready = () => {
    if (!document.body?.classList.contains("v15-editorial")) return;
    const mode = document.documentElement.dataset.flowerDesign === "classic" ? "classic" : "editorial";
    const ui = document.createElement("nav");
    ui.className = "flower-design-compare";
    ui.setAttribute("aria-label", "مقارنة واجهة فلور");
    for (const [value, label] of [
      ["classic", "الشكل الحالي"],
      ["editorial", "النموذج الفاخر"]
    ]) {
      const a = document.createElement("a");
      const url = new URL(location.href);
      url.searchParams.set("design", value);
      a.href = url.pathname + url.search + url.hash;
      a.textContent = label;
      if (value === mode) a.setAttribute("aria-current", "page");
      ui.append(a);
    }
    document.body.append(ui);
  };
  document.readyState === "loading"
    ? document.addEventListener("DOMContentLoaded", ready, {once:true})
    : ready();
})();