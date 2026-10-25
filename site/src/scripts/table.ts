// Sortable, filterable tables. Markup contract:
//   <table data-sortable>  with <th data-key="name" data-type="num|text"><button>..</button></th>
//   rows: <tr data-name=".." data-zone=".." data-verdict="..">, cells carry data-v for sorting
//   filters: <input data-filter="text" data-for="tableId">, <select data-filter="zone" data-for="tableId">
function init() {
  document.querySelectorAll<HTMLTableElement>("table[data-sortable]").forEach((table) => {
    const tbody = table.tBodies[0];
    const heads = Array.from(table.tHead!.rows[0].cells);
    heads.forEach((th, col) => {
      const btn = th.querySelector("button");
      if (!btn) return;
      btn.addEventListener("click", () => {
        const num = th.dataset.type === "num";
        const dir = th.getAttribute("aria-sort") === "descending" ? "ascending" : "descending";
        heads.forEach((h) => h.removeAttribute("aria-sort"));
        th.setAttribute("aria-sort", dir);
        const rows = Array.from(tbody.rows);
        rows.sort((a, b) => {
          const av = a.cells[col].dataset.v ?? a.cells[col].textContent ?? "";
          const bv = b.cells[col].dataset.v ?? b.cells[col].textContent ?? "";
          let c = num ? (parseFloat(av) || -Infinity) - (parseFloat(bv) || -Infinity) : av.localeCompare(bv);
          return dir === "ascending" ? c : -c;
        });
        rows.forEach((r) => tbody.appendChild(r));
      });
    });
  });

  const groups = new Map<string, HTMLElement[]>();
  document.querySelectorAll<HTMLInputElement | HTMLSelectElement>("[data-filter]").forEach((el) => {
    const id = el.dataset.for!;
    if (!groups.has(id)) groups.set(id, []);
    groups.get(id)!.push(el);
  });
  groups.forEach((controls, id) => {
    const table = document.getElementById(id) as HTMLTableElement | null;
    const count = document.querySelector<HTMLElement>(`[data-count-for="${id}"]`);
    if (!table) return;
    const apply = () => {
      let shown = 0;
      Array.from(table.tBodies[0].rows).forEach((row) => {
        const ok = controls.every((c) => {
          const v = (c as HTMLInputElement).value.trim().toLowerCase();
          if (!v) return true;
          const key = c.dataset.filter!;
          if (key === "text") return (row.dataset.search || "").includes(v);
          return (row.dataset[key] || "").toLowerCase() === v;
        });
        row.hidden = !ok;
        if (ok) shown++;
      });
      if (count) count.textContent = `${shown} shown`;
      const params = new URLSearchParams(location.search);
      controls.forEach((c) => {
        const v = (c as HTMLInputElement).value.trim();
        if (v) params.set(c.dataset.filter!, v); else params.delete(c.dataset.filter!);
      });
      const qs = params.toString();
      history.replaceState(null, "", qs ? `?${qs}` : location.pathname);
    };
    const params = new URLSearchParams(location.search);
    controls.forEach((c) => {
      const v = params.get(c.dataset.filter!);
      if (v) (c as HTMLInputElement).value = v;
      c.addEventListener("input", apply);
    });
    apply();
  });
}
init();
