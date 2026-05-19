/*!
 * GeneLink Tutorial System v2
 * - ?tour=1 na URL: sempre mostra (ignora localStorage)
 * - Sem ?tour=1: mostra só na primeira visita (localStorage)
 * - Navegação por teclado: ← → Enter Esc
 */
(function () {
  const IS_INST    = window.location.pathname.includes('inst-dashboard');
  const STORAGE_KEY = IS_INST ? 'gl_tut_inst_v1' : 'gl_tut_researcher_v1';
  const params      = new URLSearchParams(window.location.search);
  const FORCE       = params.get('tour') === '1';

  // Limpa ?tour=1 da URL sem recarregar
  if (FORCE) history.replaceState(null, '', window.location.pathname);

  // Sem força e já viu → sai
  if (!FORCE && localStorage.getItem(STORAGE_KEY)) return;

  // ── CSS injetado ─────────────────────────────────────────────────────────
  const css = document.createElement('style');
  css.textContent = `
    #gl-tut-hl {
      position: fixed; z-index: 99999; border-radius: 12px;
      transition: all .38s cubic-bezier(.4,0,.2,1);
      pointer-events: none; opacity: 0;
    }
    #gl-tut-hl.on {
      opacity: 1;
      box-shadow: 0 0 0 5px #6dd5fa, 0 0 0 9000px rgba(4,16,30,.80);
      animation: gl-pulse 2s ease-in-out infinite;
    }
    #gl-tut-hl.no-el {
      width:0;height:0;top:0;left:0;border-radius:0;
      box-shadow: 0 0 0 9000px rgba(4,16,30,.80) !important;
      animation: none !important;
    }
    @keyframes gl-pulse {
      0%,100%{ box-shadow:0 0 0 5px #6dd5fa,0 0 0 9000px rgba(4,16,30,.80); }
      50%     { box-shadow:0 0 0 9px rgba(109,213,250,.4),0 0 0 9000px rgba(4,16,30,.80); }
    }
    #gl-tut-card {
      position: fixed; z-index: 100000; width: 330px;
      background: #fff; border-radius: 20px;
      box-shadow: 0 24px 64px rgba(0,0,0,.38),0 0 0 1px rgba(109,213,250,.15);
      font-family: -apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
      transition: top .35s cubic-bezier(.4,0,.2,1), left .35s cubic-bezier(.4,0,.2,1), opacity .25s;
      animation: gl-drop .35s ease;
    }
    @keyframes gl-drop {
      from { opacity:0; transform:translateY(-10px); }
      to   { opacity:1; transform:none; }
    }
    .gt-head { display:flex;align-items:center;justify-content:space-between;padding:14px 18px 0; }
    .gt-counter {
      font-size:.68rem;font-weight:800;letter-spacing:.08em;
      color:#6dd5fa;background:#071e33;padding:3px 11px;border-radius:20px;
    }
    .gt-skip {
      font-size:.73rem;color:#94a3b8;background:none;border:none;
      cursor:pointer;padding:4px 8px;border-radius:8px;font-family:inherit;
      transition:color .15s,background .15s;
    }
    .gt-skip:hover { color:#ef4444;background:#fff1f1; }
    .gt-body { padding:16px 22px 10px; }
    .gt-icon { font-size:2.1rem;display:block;margin-bottom:10px; }
    .gt-title { font-size:1.05rem;font-weight:800;color:#071e33;margin:0 0 8px;line-height:1.3; }
    .gt-desc  { font-size:.85rem;color:#475569;line-height:1.58;margin:0; }
    .gt-dots  { display:flex;justify-content:center;gap:7px;padding:12px 22px 4px; }
    .gt-dot   {
      width:7px;height:7px;border-radius:50%;background:#cbd5e1;
      border:none;cursor:pointer;transition:all .22s;padding:0;
    }
    .gt-dot.on { background:#1b4f72;width:22px;border-radius:4px; }
    .gt-foot  {
      display:flex;gap:8px;padding:12px 18px 18px;
      border-top:1px solid #f1f5f9;margin-top:12px;
    }
    .gt-btn {
      flex:1;padding:10px 14px;border-radius:12px;font-size:.84rem;
      font-weight:700;cursor:pointer;border:none;transition:all .15s;font-family:inherit;
    }
    .gt-prev { background:#f1f5f9;color:#64748b; }
    .gt-prev:hover { background:#e2e8f0;transform:translateX(-1px); }
    .gt-next { background:linear-gradient(135deg,#1b4f72,#0b3356);color:#fff; }
    .gt-next:hover { opacity:.88;transform:translateX(1px); }
    .gt-fin  { background:linear-gradient(135deg,#16a34a,#15803d);color:#fff; }
    .gt-fin:hover { opacity:.88; }
    .gt-sp { flex:1; }
  `;
  document.head.appendChild(css);

  // ── Steps ─────────────────────────────────────────────────────────────────
  const RESEARCHER = [
    { sel:null, icon:'👋', title:'Bem-vindo ao GeneLink!',
      desc:'Esta é a sua base de pesquisa genômica colaborativa. Vamos conhecer o que cada seção faz — leva menos de 1 minuto!' },
    { sel:'a[href="/gl/search"]', icon:'🔬', title:'Pesquisar Genes',
      desc:'Clique aqui para buscar genes, variantes genéticas e encontrar outros pesquisadores por área de estudo ou instituição.' },
    { sel:'a[href="/gl/forum"]', icon:'💬', title:'Fórum Científico',
      desc:'Crie discussões e responda perguntas da comunidade científica. Troque conhecimento com pesquisadores do mundo todo.' },
    { sel:'a[href="/gl/chat"]', icon:'💌', title:'Chat ao Vivo',
      desc:'Converse em tempo real com outros pesquisadores. Tire dúvidas, faça conexões e colabore com mais agilidade.' },
    { sel:'a[href="/gl/canais"]', icon:'📡', title:'Canais Temáticos',
      desc:'Grupos focados em temas específicos — genômica, bioinformática, CRISPR e mais. Entre nos canais do seu interesse!' },
    { sel:'a[href="/gl/preprints"]', icon:'📄', title:'Preprints',
      desc:'Publique e leia artigos científicos preliminares antes da revisão por pares. Compartilhe sua pesquisa com rapidez.' },
    { sel:'.dash-tabs', icon:'📊', title:'Suas Abas',
      desc:'Navegue entre "Visão Geral" com métricas, "Fórum" com suas postagens e "Parcerias" com suas colaborações.' },
    { sel:'.nav-avatar,.nav-user-btn,.avatar-circle,[data-nav-profile]', icon:'👤', title:'Seu Perfil',
      desc:'Clique no seu avatar para editar perfil, área de pesquisa e bio. Em Perfil você também pode rever este tutorial.' },
  ];

  const INST = [
    { sel:null, icon:'🏛️', title:'Bem-vindo ao Painel Institucional!',
      desc:'Este é o centro de gestão da sua instituição no GeneLink. Vamos conhecer cada seção — leva menos de 1 minuto!' },
    // action:'openDrawer' → tutorial abre o drawer automaticamente neste passo
    { sel:'.gl-menu-btn,.inst-drawer-toggle,[data-drawer-toggle],.nav-drawer-btn,.drawer-btn',
      icon:'☰', title:'Menu de Navegação',
      desc:'Este botão abre o menu lateral com todas as seções disponíveis para sua conta institucional.',
      action: 'openDrawer' },
    { sel:'a[href="/gl/parcerias"]', icon:'🤝', title:'Parcerias',
      desc:'Publique vagas, projetos e oportunidades de colaboração. Pesquisadores poderão se candidatar diretamente pelo GeneLink.' },
    { sel:'a[href="/gl/inst-candidates"]', icon:'🎓', title:'Candidatos',
      desc:'Veja todos os pesquisadores que se candidataram às suas parcerias, com nome, área de estudo e mensagem de interesse.' },
    { sel:'.metric-row', icon:'📈', title:'Métricas da Instituição',
      desc:'Acompanhe em tempo real: membros vinculados, parcerias ativas e candidatos recebidos pela sua instituição.' },
    { sel:'.dash-tabs', icon:'📋', title:'Abas do Painel',
      desc:'Navegue entre "Visão Geral", "Membros" com pesquisadores vinculados e "Biblioteca" com seus documentos de pesquisa.' },
  ];

  const steps = IS_INST ? INST : RESEARCHER;

  // ── State & DOM ────────────────────────────────────────────────────────────
  let cur = 0, hl, card;

  function getEl(sel) {
    if (!sel) return null;
    for (const s of sel.split(',')) {
      const el = document.querySelector(s.trim());
      if (el) return el;
    }
    return null;
  }

  // Executa a ação opcional ao sair de um passo
  function leaveStep(i) {
    const s = steps[i];
    if (!s) return;
    if (s.action === 'openDrawer') {
      if (typeof _glCloseDrawer === 'function') _glCloseDrawer();
    }
  }

  // Executa a ação opcional ao entrar em um passo
  function enterStep(i) {
    const s = steps[i];
    if (!s) return;
    if (s.action === 'openDrawer') {
      if (typeof _glOpenDrawer === 'function') {
        // Pequeno atraso para garantir que o DOM do navbar já foi injetado
        setTimeout(_glOpenDrawer, 150);
      }
    }
  }

  function render(i) {
    const s = steps[i], last = i === steps.length - 1;
    const dots = steps.map((_,j)=>`<button class="gt-dot${j===i?' on':''}" onclick="window.__glTut.go(${j})"></button>`).join('');
    card.innerHTML = `
      <div class="gt-head">
        <span class="gt-counter">${i+1} / ${steps.length}</span>
        <button class="gt-skip" onclick="window.__glTut.done()">Pular tutorial ✕</button>
      </div>
      <div class="gt-body">
        <span class="gt-icon">${s.icon}</span>
        <h3 class="gt-title">${s.title}</h3>
        <p class="gt-desc">${s.desc}</p>
      </div>
      <div class="gt-dots">${dots}</div>
      <div class="gt-foot">
        ${i > 0 ? '<button class="gt-btn gt-prev" onclick="window.__glTut.prev()">← Anterior</button>'
                : '<span class="gt-sp"></span>'}
        ${!last ? '<button class="gt-btn gt-next" onclick="window.__glTut.next()">Próximo →</button>'
                : '<button class="gt-btn gt-fin"  onclick="window.__glTut.done()">Concluir ✓</button>'}
      </div>`;
  }

  function place(el) {
    const m=14, cw=330, vw=window.innerWidth, vh=window.innerHeight;
    const ch = card.offsetHeight || 290;
    let top, left;
    if (!el) {
      top  = (vh-ch)/2; left = (vw-cw)/2;
    } else {
      const r = el.getBoundingClientRect();
      top  = (r.top+r.height/2 < vh/2) ? r.bottom+16 : r.top-ch-16;
      left = r.left+r.width/2 - cw/2;
    }
    card.style.top  = Math.max(m, Math.min(top,  vh-ch-m)) + 'px';
    card.style.left = Math.max(m, Math.min(left, vw-cw-m)) + 'px';
  }

  function placeHl(el) {
    if (!el) { hl.className = 'no-el on'; return; }
    const r=el.getBoundingClientRect(), p=7;
    hl.className = 'on';
    hl.style.top   = (r.top-p)+'px';  hl.style.left  = (r.left-p)+'px';
    hl.style.width = (r.width+p*2)+'px'; hl.style.height = (r.height+p*2)+'px';
  }

  function show(i) {
    // Executa ação de saída do passo atual antes de trocar
    if (i !== cur) leaveStep(cur);

    cur = i;
    const s = steps[i];
    const el = getEl(s.sel);

    // Executa ação de entrada do novo passo
    enterStep(i);

    render(i);
    if (el) el.scrollIntoView({behavior:'smooth',block:'nearest'});
    setTimeout(() => { placeHl(el); place(el); }, el ? 200 : 0);
  }

  window.__glTut = {
    next() { if (cur < steps.length-1) show(cur+1); },
    prev() { if (cur > 0) show(cur-1); },
    go(i)  { show(i); },
    done() {
      localStorage.setItem(STORAGE_KEY, '1');
      // Fecha o drawer caso esteja aberto pelo tutorial
      leaveStep(cur);
      [hl, card].forEach(el => {
        if (!el) return;
        el.style.opacity='0'; el.style.transition='opacity .3s';
        setTimeout(()=>el.remove(), 320);
      });
      document.removeEventListener('keydown', onKey);
    },
  };

  function onKey(e) {
    if (!card?.isConnected) return;
    if (e.key==='ArrowRight'||e.key==='Enter') window.__glTut.next();
    if (e.key==='ArrowLeft')                   window.__glTut.prev();
    if (e.key==='Escape')                      window.__glTut.done();
  }
  document.addEventListener('keydown', onKey);

  // ── Start ──────────────────────────────────────────────────────────────────
  function start() {
    hl   = Object.assign(document.createElement('div'), {id:'gl-tut-hl'});
    card = Object.assign(document.createElement('div'), {id:'gl-tut-card'});
    document.body.append(hl, card);
    show(0);
  }

  if (document.readyState === 'loading')
    document.addEventListener('DOMContentLoaded', () => setTimeout(start, 900));
  else
    setTimeout(start, 900);
})();
