let currentQuery = "";

document.addEventListener("DOMContentLoaded", () => {
  if (!requireAuth()) return;
  injectNavbar("/search");

  const params = new URLSearchParams(window.location.search);
  const q = params.get("q");
  if (q) {
    document.getElementById("search-input").value = q;
    performSearch(q);
  }
});

document.addEventListener("DOMContentLoaded", () => {
  const form = document.getElementById("search-form");
  if (form) {
    form.addEventListener("submit", (e) => {
      e.preventDefault();
      const q = document.getElementById("search-input").value.trim();
      if (q) performSearch(q);
    });
  }
});

async function performSearch(query) {
  currentQuery = query;
  const resultsEl = document.getElementById("results-container");
  const metaEl = document.getElementById("search-meta");
  const alertEl = document.getElementById("search-alert");

  hideAlert(alertEl);
  resultsEl.innerHTML = `<div class="loading-state"><div class="spinner spinner-dark"></div><p style="margin-top:12px">Consultando banco de dados NCBI Gene…</p></div>`;
  metaEl.textContent = "";

  const url = new URL(window.location.href);
  url.searchParams.set("q", query);
  window.history.replaceState({}, "", url);

  try {
    const res = await apiFetch(`/search-gene?q=${encodeURIComponent(query)}&max=25`);
    const data = await res.json();

    if (!res.ok) {
      showAlert(alertEl, data.error || "Falha na busca", "error");
      resultsEl.innerHTML = "";
      return;
    }

    const { results, total, returned } = data;
    if (!results.length) {
      metaEl.textContent = `Nenhum resultado encontrado para "${query}" no banco de dados NCBI Gene.`;
      resultsEl.innerHTML = `<div class="empty-state">
        <div class="empty-state-icon">🔎</div>
        <h3>Nenhum gene encontrado</h3>
        <p style="font-size:.85rem;margin-top:8px">Nenhum gene correspondente a "<strong>${escHtml(query)}</strong>" foi encontrado no banco NCBI.</p>
        <p style="font-size:.82rem;color:var(--text-light);margin-top:6px">Tente um termo diferente, símbolo do gene ou nome do organismo.</p>
      </div>`;
      return;
    }

    metaEl.textContent = `Exibindo ${returned} de ${total.toLocaleString("pt-BR")} resultados do banco NCBI Gene · Busca: "${query}"`;

    const rows = results.map((g) => `
      <tr>
        <td><div class="gene-name">${escHtml(g.name)}</div></td>
        <td><div class="gene-id">${escHtml(g.id)}</div></td>
        <td><div class="gene-desc">${escHtml(g.description)}</div>
          ${g.summary ? `<div class="gene-summary-text">${escHtml(g.summary.slice(0, 200))}${g.summary.length > 200 ? "…" : ""}</div>` : ""}
        </td>
        <td><div class="gene-org">${escHtml(g.organism_scientific)}</div>
          ${g.organism_common ? `<div style="font-size:.78rem;color:var(--text-light)">${escHtml(g.organism_common)}</div>` : ""}
        </td>
        <td>${g.chromosome !== "N/A" ? `<span class="badge badge-muted">Cr ${escHtml(g.chromosome)}</span>` : ""}</td>
        <td>
          <a class="ncbi-link" href="https://www.ncbi.nlm.nih.gov/gene/${g.id}" target="_blank" rel="noopener">
            NCBI →
          </a>
        </td>
      </tr>`).join("");

    resultsEl.innerHTML = `
      <div class="table-wrapper">
        <table>
          <thead>
            <tr>
              <th>Símbolo do Gene</th>
              <th>ID do Gene</th>
              <th>Descrição</th>
              <th>Organismo</th>
              <th>Cromossomo</th>
              <th>Link</th>
            </tr>
          </thead>
          <tbody>${rows}</tbody>
        </table>
      </div>
      <div style="padding:10px 14px;font-size:.78rem;color:var(--text-muted);border-top:1px solid var(--border);background:var(--surface-alt)">
        Dados obtidos em tempo real do banco NCBI Gene (eutils.ncbi.nlm.nih.gov). Todos os resultados são não modificados.
      </div>`;
  } catch (err) {
    showAlert(alertEl, "Falha na requisição de busca. Tente novamente.", "error");
    resultsEl.innerHTML = "";
  }
}

function escHtml(s) {
  return String(s || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}
