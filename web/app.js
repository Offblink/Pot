/* Pot web UI */
marked.setOptions({ breaks: true, gfm: true });
const FC = window.PotCommon;
const T = window.PotI18N.t;
const msgs = document.getElementById('messages'), input = document.getElementById('input'),
  btn = document.getElementById('send'), status = document.getElementById('status'),
  tray = document.getElementById('agent-tray');
let processing = false, currentSessionId = null, allSessions = [], sessionDirty = false;
let _liveCount = 0; // live-node count at last streaming render (motion: animate only fresh nodes)
let rawMessages = [];
let sessionHidden = false; // the open session's records are toggled hidden (card clicked again)

function setCurrentSession(id) {
  currentSessionId = id;
  try { if (id) localStorage.setItem('pot-session', id); else localStorage.removeItem('pot-session'); } catch (e) {}
  refreshSendButton(); // send vs retry depends on the session (shuttle always sends)
  startJobsPoll(); // jobs 芯片: one interval per open session, torn down on close/switch
}

/* ---------- helpers ---------- */
const escapeHtml = FC.escapeHtml;
/* #messages has exactly one owner at a time. Every write below goes through a
   pane writer: S for the session transcript, F for the friend thread. A writer
   whose view does not own the pane paints nothing (FC.initPane). */
const pane = FC.initPane({
  msgs: () => msgs, tray: () => tray, isNearBottom, onPaint: updateScrollBtn,
});
const S = pane.of('session'), F = pane.of('friend');
function isNearBottom(el) { return el.scrollHeight - el.scrollTop - el.clientHeight < 60; }
function updateScrollBtn() {
  const b = document.getElementById('scroll-bottom');
  if (!b) return;
  if (isNearBottom(msgs)) b.classList.remove('visible'); else b.classList.add('visible');
}
document.getElementById('scroll-bottom').addEventListener('click', () => { msgs.scrollTop = msgs.scrollHeight; updateScrollBtn(); });
msgs.addEventListener('scroll', updateScrollBtn);

/* #status carries motion.js's wave bars as an element child beside its text,
   so the text is never assigned with `textContent =` — that takes every child
   with it, and the wave died at the first event of the turn (only the opening
   "Thinking..." ever animated — 2026-09-28). Swap the text nodes and leave the
   elements connected: detaching the wave would restart its CSS animation on
   every rewritten line. Without motion.js there are no element children and
   this is plain textContent. */
function setStatus(t) {
  for (const n of Array.from(status.childNodes)) {
    if (n.nodeType !== Node.ELEMENT_NODE) n.remove();
  }
  status.append(t);
}

const getSessionTitle = list => FC.getSessionTitle(list, 55, 52);
/* 输出速率（§64）：喂它的只有本页自己那条流的 text/reasoning chunk */
const rateTok = FC.tokenRate(document.getElementById('tok-rate'));

/* ---------- confirm modal (shared impl in common.js) ---------- */
FC.initConfirmModal({ keyboard: 'desktop' });
const showConfirm = FC.showConfirm, closeConfirm = FC.closeConfirm;

/* ---------- sessions ---------- */
let _sessionsSeq = 0;
async function loadSessions() {
  const seq = ++_sessionsSeq;
  try {
    const r = await fetch('/sessions');
    if (!r.ok) throw new Error(r.status);
    const sessions = (await r.json()).sessions || [];
    if (seq !== _sessionsSeq) return; // a newer fetch superseded this response
    allSessions = sessions;
    // §61: the alert map from /session/seen outranks the payload's copy of it —
    // the claim that produced it also cleared what it covered (a session the
    // user just opened must not wear its dot again for this fetch).
    const known = Alerts.map();
    if (known) applyAlerts(known);
    renderSessionList();
  } catch (e) { console.error('loadSessions:', e); }
}
async function reloadSessionFromServer() {
  if (!currentSessionId) return;
  try {
    const r = await fetch('/session?id=' + encodeURIComponent(currentSessionId));
    if (!r.ok) return;
    const s = await r.json();
    rawMessages = s.messages || [];
    registerArchived(s.subagents);
    const stick = isNearBottom(msgs); // measure before the repaint replaces the DOM
    renderMessages(s);
    if (stick && S.stick()) updateScrollBtn();
    loadSessions();
  } catch (e) {}
}
async function closeCurrentSession() {
  if (!currentSessionId) return;
  if (processing && turn && turn.sessionId === currentSessionId) {
    // A turn is running in this session: never delete or save over it. The
    // server persists the whole turn on its own at turn end — just detach.
    // (2026-09-04: switching sessions before the first token arrived deleted
    // the session out from under the running turn — the response vanished.)
    setCurrentSession(null);
    return;
  }
  if (!sessionDirty) { setCurrentSession(null); return; }
  const list = rawMessages;
  if (!list || list.length <= 1) {
    try { await fetch('/session?id=' + encodeURIComponent(currentSessionId), { method: 'DELETE' }); } catch (e) {}
    setCurrentSession(null);
  } else {
    const title = getSessionTitle(list);
    try {
      await fetch('/save', { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id: currentSessionId, title, messages: list }) });
    } catch (e) {}
  }
  loadSessions();
}
async function switchSession(id) {
  if (id === currentSessionId) {
    // The open session's own card: alternate showing/hiding its records. The
    // user's rule (2026-10-31) — click to open, click again to hide, click again
    // to bring them back. (Was an early return + an unconditional pane wipe, so
    // the records vanished with nothing to repaint them.)
    sessionHidden = !sessionHidden;
    if (sessionHidden) S.clearMsgs();
    else await reloadSessionFromServer();
    return;
  }
  await closeCurrentSession();
  sessionHidden = false;
  sessionDirty = false;
  try {
    const r = await fetch('/session?id=' + encodeURIComponent(id));
    if (!r.ok) throw new Error(r.status);
    const s = await r.json();
    setCurrentSession(s.id);
    rawMessages = s.messages || [];
    S.clear();
    registerArchived(s.subagents);
    renderMessages(s);
    S.stick(); updateScrollBtn(); // a freshly opened session starts at the latest message
    renderSessionList(); loadSessions();
    reattachIfRunning(s.id);
    Alerts.tick(); // 用户正在看这个会话：立刻告诉服务端（红点该掉、铃该停）
  } catch (e) { console.error('switchSession:', e); }
}

function renderMessages(s) {
  // #messages has exactly one owner, and it is not us: the open friend view
  // owns it until it is left. A session turn finishing, a stream recovering
  // from a drop, or a session reload used to paint here while a friend
  // conversation was on screen — the friend thread was replaced by the session
  // (and the friend poll would not repaint it, because its payload had not
  // changed). The pane writers enforce this now; the early return keeps the
  // work from happening at all. 2026-09-10 real-machine finding.
  if (!pane.is('session')) return;
  sessionHidden = false; // any repaint means the records are on screen
  _liveCount = 0; // full re-render: transcript replay is CSS-static, live nodes re-baseline
  // Full re-render must actually replace: renderTranscript only appends, so
  // without this clear every reload (done/ESC/retry) stacked a second copy of
  // the whole transcript below the live nodes. Clearing here makes the
  // reload path byte-for-byte the same render a page refresh does.
  S.clearMsgs();
  FC.renderTranscript(S, rawMessages, s.asks || [], renderOpts());
  if (turn && turn.sessionId === currentSessionId) {
    // The transcript just rendered comes from the disk copy, which (turn-
    // start save) already contains the running turn's user message — the
    // live userText bubble would draw it a second time (mid-turn switch
    // back). Mark it rendered so renderTurnLive skips the bubble.
    if (turn.userText && rawMessages.some(m => m.role === 'user' && m.content === turn.userText)) {
      turn.userRendered = true;
    }
    renderTurnLive();
  }
  placeAskCards(); // friend-view inline cards move back to the banner here
  renderPlan(s.plan || []);
  syncJobChips(); // a re-rendered transcript loses chips; re-bind them from text
}

/* ---- plan drawer (裁决 17): the session's plan lives in a collapsible
   right-edge sidebar (Spore drawer pattern), never in the transcript. A flip to
   done strikes the item through with a growing bar (style.css), so a fresh
   paint (all-done items) shows them struck and a live flip animates. Only a
   user toggle persists the open/collapsed state (pot-plan-open, like the
   theme); auto-opens are momentary. ---- */
const planDrawer = document.getElementById('plan-drawer');
const planKnob = document.getElementById('plan-knob');
const planList = document.getElementById('plan-list');
const planCount = document.getElementById('plan-count');

function planPrefOpen() {
  try { return localStorage.getItem('pot-plan-open') !== '0'; } catch (e) { return true; }
}

function setPlanOpen(open, persist) {
  if (!planDrawer) return;
  planDrawer.classList.toggle('open', open);
  if (persist !== false) { try { localStorage.setItem('pot-plan-open', open ? '1' : '0'); } catch (e) {} }
}

function renderPlan(plan, live) {
  if (!planDrawer || !planList) return;
  const items = plan || [];
  const wasEmpty = planDrawer.classList.contains('empty');
  planDrawer.classList.toggle('empty', !items.length);
  if (!items.length) {
    planDrawer.classList.remove('open');
    planList.innerHTML = '';
    delete planDrawer.dataset.sig;
    return;
  }
  // empty→non-empty: a load restores the stored preference; a live plan event
  // (the agent just started planning) opens so it is seen, not just the knob.
  if (wasEmpty) setPlanOpen(live ? true : planPrefOpen(), false);
  const sig = items.map(it => it.text).join('\u0001');
  if (planDrawer.dataset.sig !== sig) {
    planDrawer.dataset.sig = sig;
    planList.innerHTML = items.map(it => '<li class="plan-item' + (it.done ? ' done' : '') + '"><span class="plan-text">'
      + escapeHtml(it.text) + '</span></li>').join('');
  } else {
    // Same list: only toggle done classes — the CSS width transition is the animation.
    const rows = planList.querySelectorAll('.plan-item');
    items.forEach((it, i) => { if (rows[i]) rows[i].classList.toggle('done', !!it.done); });
  }
  const left = items.filter(it => !it.done).length;
  planCount.textContent = left ? String(left) : '\u2713';
  planCount.classList.toggle('all-done', left === 0);
}

planKnob && planKnob.addEventListener('click', () => setPlanOpen(!planDrawer.classList.contains('open')));
document.getElementById('plan-close')?.addEventListener('click', () => setPlanOpen(false));

/* Timeline + transcript rendering live in common.js (FC.renderTranscript /
   FC.insertByTs): m.js is the same renderer with different cosmetics, and two
   copies of it is how the friend view's bugs got fixed twice. What cannot be
   shared is injected below. */
const renderOpts = extra => Object.assign({
  asks: { buildAnsweredAskCard },
  spawnLookup: callId => specByCall[callId] || archivedByCall[callId],
  argsMax: 80,
  my: MY_SIDE,   // a row sits on the side of the device it came from (§59)
  canOpen: true, // §73: this shell *is* the machine the card's file lives on
  reasoningHtml: t => '<div style="white-space:pre-wrap;max-height:200px;overflow-y:auto">' + escapeHtml(t) + '</div>',
  liveText: r => { const text = FC.silentText(r.text); return text ? marked.parse(text) : ''; },
}, extra || {});
/* This shell *is* the computer: it renders its own rows on the right and the
   phone's on the left, and it tells the server the same thing when it sends, so
   a plain message row can be sided too (§59). */
const MY_SIDE = 'computer';

async function newSession() {
  rateTok.clear();  // 新对话从零开始：速率读数只在“有输出/刚输出过”时才有意义
  // Any untouched "(new session)" on disk? Focus it instead of creating
  // another one — repeated clicks and switches must not litter the list.
  const empty = allSessions.find(s => s.title === '(new session)' && (s.msgCount || 0) <= 1 && !s.running);
  if (empty) {
    if (empty.id !== currentSessionId) await switchSession(empty.id);
    return;
  }
  await closeCurrentSession();
  try {
    const r = await fetch('/new', { method: 'POST' });
    if (!r.ok) throw new Error(r.status);
    const { id } = await r.json();
    setCurrentSession(id); rawMessages = []; S.clear();
    sessionDirty = false;
    await loadSessions();
  } catch (e) { console.error('newSession:', e); }
}
async function deleteSession(id) {
  try {
    await fetch('/session?id=' + encodeURIComponent(id), { method: 'DELETE' });
    if (id === currentSessionId) { setCurrentSession(null); S.clear(); }
    document.getElementById('session-filter').value = '';
    await loadSessions();
  } catch (e) {}
}
/* The live list entry for a row, by id. Rows are reused keyed by id, so a row's
   handlers hold the session object of whatever /sessions fetch created that row
   — an older generation after the next poll. Write through this, never through
   the captured object: renderSessionList's title guard compares the painted name
   against the live entry, and a stale write is exactly how a rename silently
   reverted to the old name (2026-09-11 user report). */
const sessionById = id => allSessions.find(s => s.id === id) || null;

function renderSessionList() {
  const list = document.getElementById('session-list');
  const empty = document.getElementById('session-list-empty');
  const filter = (document.getElementById('session-filter')?.value || '').trim().toLowerCase();
  const filtered = filter ? allSessions.filter(s => (s.title || '').toLowerCase().includes(filter)) : allSessions;
  // Keyed row reconciliation: Flip needs persistent nodes to animate a
  // reorder/move — rebuilding rows every render would make every list change
  // look like remove+add.
  const mutate = () => {
    const existing = {};
    list.querySelectorAll('.session-row').forEach(r => { existing[r.dataset.sid] = r; });
    const wanted = filtered.map(s => {
      const row = existing[s.id];
      if (row) {
        delete existing[s.id];
        const titleEl = row.querySelector('.session-row-title');
        if (titleEl && !row.querySelector('.rename-input') && titleEl.textContent !== (s.title || T('session.untitled')))
          titleEl.textContent = s.title || T('session.untitled');
        row.querySelector('.session-row-meta').textContent = fmtDate(s.created) + (s.running ? ' \u25cf' : '');
        paintAlert(row, s.alert);  // §61: reuse must refresh the dot too
        row.classList.toggle('active', s.id === currentSessionId);
        row.classList.toggle('pinned', !!s.pinned);  // 裁决 18: the pin survives every repaint
        return row;
      }
      const fresh = document.createElement('div');
      fresh.dataset.sid = s.id;
      fresh.className = 'session-row' + (s.pinned ? ' pinned' : '')
        + (s.id === currentSessionId ? ' active' : '');
      fresh.innerHTML = '<span class="session-row-title">' + escapeHtml(s.title || T('session.untitled')) + '</span>'
        + (s.role ? '<span class="session-row-role">' + escapeHtml(s.role) + '</span>' : '')
        + '<span class="session-row-meta">' + fmtDate(s.created) + (s.running ? ' \u25cf' : '') + '</span>'
        + '<span class="session-row-actions">'
        + '<button class="session-row-pin" title="' + escapeHtml(T('desktop.pin')) + '"></button>'
        + '<button class="session-row-act" title="' + escapeHtml(T('desktop.rename')) + '">&#9998;</button>'
        + '<button class="session-row-act del" title="' + escapeHtml(T('desktop.delete')) + '">&#10005;</button></span>';
      fresh.querySelector('.session-row-pin').addEventListener('click', async e => {
        e.stopPropagation();
        const cur = sessionById(fresh.dataset.sid);
        try {
          await fetch('/pin', { method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ id: fresh.dataset.sid, pinned: !(cur && cur.pinned) }) });
        } catch (err) {}
        await loadSessions();  // the server owns the order: pinned group first
      });
      fresh.querySelector('.session-row-act.del').addEventListener('click', e => {
        e.stopPropagation();
        const cur = sessionById(fresh.dataset.sid);
        showConfirm({
          title: T('desktop.deleteTitle'),
          message: T('desktop.deleteMessage', { title: (cur && cur.title) || T('session.untitled') }),
          confirmText: T('desktop.deleteConfirm'),
          danger: true,
          onConfirm: () => deleteSession(fresh.dataset.sid)
        });
      });
      fresh.querySelector('.session-row-act:not(.del)').addEventListener('click', e => { e.stopPropagation(); startRename(fresh); });
      paintAlert(fresh, s.alert);
      fresh.addEventListener('click', () => switchSession(s.id));
      return fresh;
    });
    Object.values(existing).forEach(r => r.remove());
    // 只搬**位置不对**的那几行（2026-09-25 用户报告：切换会话/停止会话都像在「视图重排」）。
    // 以前每行无条件 `list.appendChild(row)`：一次重绘就是 N 次 DOM 搬动（21 行 = 130 次
    // childList 变更），既让 Flip 每次都算一遍移动，也在滚动容器上把滚动位置顶掉。
    // 从后往前放，锚点就是「下一个该在它后面的行」——已经在位的行一个指头都不碰。
    let anchor = null;
    for (let i = wanted.length - 1; i >= 0; i--) {
      const row = wanted[i];
      // A row built above is still detached, and a detached node reports
      // nextElementSibling === null — so "not attached" is its own reason to insert.
      if (row.parentNode !== list || row.nextElementSibling !== anchor) list.insertBefore(row, anchor);
      anchor = row;
    }
    if (filtered.length === 0) { empty.style.display = ''; empty.textContent = filter ? T('desktop.noMatches') : T('desktop.noSessions'); }
    else empty.style.display = 'none';
  };
  // 顺序没变就别进动画（2026-09-25 用户：「切换会话也好，停止会话也好，就会触发视图重排」）。
  // 一次纯重绘（切会话只改 `.active`、停一轮只改那个圆点）以前也会跑一遍 Flip：GSAP 为了
  // 量每一行，会把测量代理 `<div>` 往列表里插一遍再拔掉（5 行 = 24 次 childList 变更），
  // 再开一个 340ms 什么也不动的动画。进这里之前先比顺序：一样就原地更新，一个节点都不碰。
  const ids = filtered.map(s => s.id);
  const painted = Array.from(list.querySelectorAll('.session-row'), r => r.dataset.sid);
  const moved = ids.length !== painted.length || ids.some((id, i) => id !== painted[i]);
  if (moved && window.potMotion && !window.potMotion.reduced && window.potMotion.listFlip)
    window.potMotion.listFlip(list, mutate);
  else mutate();
}
const fmtDate = d => FC.fmtDate(d);
function startRename(row) {
  const s = sessionById(row.dataset.sid);
  if (!s) return;
  const titleEl = row.querySelector('.session-row-title');
  const inp = document.createElement('input');
  inp.className = 'rename-input'; inp.value = s.title || titleEl.textContent;
  inp.addEventListener('blur', () => finishRename(row, inp));
  inp.addEventListener('keydown', e => {
    // Enter swaps the input back out, which blurs it: one finish per rename
    // (finishRename's `done` flag absorbs the blur that its own teardown fires).
    if (e.key === 'Enter') { e.preventDefault(); finishRename(row, inp); }
    if (e.key === 'Escape') { row.replaceChild(titleEl, inp); titleEl.textContent = s.title || T('session.untitled'); }
  });
  row.replaceChild(inp, titleEl); inp.focus(); inp.select();
}
async function finishRename(row, inp) {
  if (inp.dataset.done) return;
  inp.dataset.done = '1';
  const newTitle = inp.value.trim() || T('session.untitled');
  try {
    await fetch('/save', { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id: row.dataset.sid, title: newTitle, messages: [] }) });
  } catch (e) {}
  if (inp.parentNode === row) {
    const titleEl = document.createElement('span');
    titleEl.className = 'session-row-title'; titleEl.textContent = newTitle;
    row.replaceChild(titleEl, inp);
  }
  // Onto the LIVE entry, so renderSessionList's guard agrees with the paint
  // instead of restoring the old name from a list object this row predates.
  const s = sessionById(row.dataset.sid);
  if (s) s.title = newTitle;
  renderSessionList();
}

/* ---------- sidebar wiring ---------- */
const burger = document.getElementById('hamburger-sidebar');
function toggleSidebar() {
  const collapsed = document.getElementById('sidebar').classList.toggle('collapsed');
  burger.textContent = collapsed ? '\u276F' : '\u276E'; /* collapsed: > (reopen), open: < (collapse) */
}
burger.addEventListener('click', toggleSidebar);
burger.textContent = document.getElementById('sidebar').classList.contains('collapsed') ? '\u276F' : '\u276E';
document.getElementById('session-filter').addEventListener('input', renderSessionList);
document.getElementById('btn-new-session').addEventListener('click', () => newSession());

/* ---------- agent tray + replayable modal ----------
   M2b retired live spawns (spec §3.4): the server no longer emits
   agent_spawn/agent_status/agent_event, so there are no live bubbles or status
   flips any more. What stays is the read-only replay of the subagents records
   persisted in OLD session files: registerArchived maps them, the spawn/
   background tool cards deep-link here (attachSpawnClick -> openAgentModal). */
const specByCall = {};     // live tool_call id -> spec id (no writer since M2b; kept for the lookup chain)
let archived = {};         // persisted spec id -> {layer, tool, goal, replyFormat}
const archivedByCall = {}; // persisted tool_call id -> spec id

function agentEvent(id, ev) {
  const a = archived[id];
  if (!a || !a.eventsEl) return;
  const body = a.eventsEl;
  if (ev.type === 'text' || ev.type === 'reasoning') {
    let last = body.lastElementChild;
    if (!last || !last.classList.contains('stream-ev')) {
      body.insertAdjacentHTML('beforeend', '<div class="ev stream-ev"></div>');
      last = body.lastElementChild;
    }
    last.textContent += ev.content || '';
    body.scrollTop = body.scrollHeight;
  } else if (ev.type === 'tool') {
    body.insertAdjacentHTML('beforeend', '<div class="ev tool-ev">\u{1F527} ' + escapeHtml(ev.content.name) + ' ' + escapeHtml((ev.content.args || '').slice(0, 120)) + '</div>');
    body.scrollTop = body.scrollHeight;
  } else if (ev.type === 'tool_result') {
    const text = String(ev.content.content || '');
    body.insertAdjacentHTML('beforeend', '<div class="ev">' + escapeHtml(text.slice(0, 400)) + (text.length > 400 ? '...' : '') + '</div>');
    body.scrollTop = body.scrollHeight;
  } else if (ev.type === 'agent_spawn') {
    body.insertAdjacentHTML('beforeend', '<div class="ev tool-ev">\u{1F9E9} spawn L' + (ev.content.layer || '?') + ': ' + escapeHtml((ev.content.goal || '').slice(0, 120)) + '</div>');
    body.scrollTop = body.scrollHeight;
  } else if (ev.type === 'agent_status') {
    body.insertAdjacentHTML('beforeend', '<div class="ev">' + escapeHtml(ev.content.status) + '</div>');
    body.scrollTop = body.scrollHeight;
  } else if (ev.type === 'error') {
    body.insertAdjacentHTML('beforeend', '<div class="ev err-ev">\u26A0 ' + escapeHtml(ev.content) + '</div>');
    body.scrollTop = body.scrollHeight;
  }
}
function openAgentModal(id) {
  const a = archived[id];
  if (!a) return;
  const overlay = document.getElementById('agent-modal-overlay');
  overlay.innerHTML = '<div id="agent-modal">'
    + '<div class="agent-modal-head"><h3>' + (a.tool === 'background' ? T('agent.bgCommand') : (a.layer === 3 ? T('agent.l3Worker') : T('agent.l2TaskAgent'))) + ' \u00B7 ' + escapeHtml((a.goal || '').slice(0, 60)) + '</h3>'
    + '<button id="agent-modal-close">\u2715</button></div>'
    + '<div class="agent-modal-taskspec"><b>' + T('agent.goal') + '</b> ' + escapeHtml(a.goal || '')
    + '<br><b>' + T('agent.replyFormat') + '</b> ' + escapeHtml(a.replyFormat || T('agent.free'))
    + '<br><b>' + T('agent.status') + '</b> ' + escapeHtml(a.status || T('agent.unknown')) + '</div>'
    + '<div class="agent-modal-body"></div></div>';
  const bodyEl = overlay.querySelector('.agent-modal-body');
  a.eventsEl = bodyEl;
  (a.history || []).forEach(ev => agentEvent(id, ev));
  overlay.querySelector('#agent-modal-close').addEventListener('click', () => {
    overlay.classList.remove('show'); a.eventsEl = null;
  });
  overlay.classList.add('show');
}
function registerArchived(subs) {
  archived = {};
  for (const k of Object.keys(archivedByCall)) delete archivedByCall[k];
  (subs || []).forEach(r => {
    archived[r.id] = {
      layer: r.layer, tool: r.tool, goal: r.goal, replyFormat: r.reply_format,
      // Old session files are the only source of these records (M2b retired
      // spawn), and they carry the tail as `status` + `events` (trilayer.py's
      // record). Without these two the modal showed "unknown" over an empty
      // body — the fields were simply never mapped.
      status: r.status || '',
      history: r.events || [],
    };
    if (r.call_id) archivedByCall[r.call_id] = r.id;
  });
}

/* ---------- send / stream ---------- */
let abortCtrl = null;
let stopRequested = false; // first Esc: graceful stop via /stop; second Esc: hard disconnect
let stopTimer = null;
let turn = null; // active turn: {sessionId, buffer, reasoning, reasoningOpen, tools, asks, errors}

/* The send button is three things in one: send, a visible stop while a turn
   runs, and — when the box is empty — a retry of the last turn. */

function refreshSendButton() {
  if (processing) return; // the busy (■) label is owned by setBusy
  const retry = !input.value.trim();
  btn.innerHTML = retry ? T('ui.retry') : T('ui.send');
  btn.title = retry ? T('ui.retry') : T('ui.send');
}
function setBusy(busy, stopping) {
  btn.classList.toggle('stopping', !!stopping);
  if (busy) {
    btn.innerHTML = '&#x25A0;';
    btn.title = stopping ? T('ui.stopForce') : T('ui.stop');
  } else {
    refreshSendButton(); // back to send / retry for the current box + session
  }
  btn.disabled = false; // must stay clickable: it IS the stop button while busy
}
/* One stop path shared by the button and Esc: first press asks the server to
   stop (stream stays open for the persisted partial), second press hard-cuts a
   server stuck in a long tool call. */
function requestStop() {
  if (!abortCtrl || !turn) return;
  const sid = turn.sessionId || currentSessionId;
  if (!stopRequested) {
    stopRequested = true;
    setBusy(true, true);
    setStatus(T('status.stopping'));
    if (sid) fetch('/stop', { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ sessionId: sid }) }).catch(() => {});
    stopTimer = setTimeout(() => { if (abortCtrl) { abortCtrl.abort(); abortCtrl = null; } }, 15000);
  } else {
    if (stopTimer) { clearTimeout(stopTimer); stopTimer = null; }
    stopRequested = false;
    abortCtrl.abort(); abortCtrl = null;
    setStatus(T('status.aborted'));
  }
}

/* 后台执行 (§74 / 裁决 20): move a long-running bash call into the job table.
   The POST only arms the session's detach signal — the running bash hands its
   own process to the job table and returns BACKGROUNDED (job=…) as its tool
   result, which is where the card learns the job id. So the response is just
   {ok}: on ok the card is marked as moved over (chip in running state, id bound
   when the result lands); the final output arrives later as a [job report]
   turn, the chip only tracks status via the /jobs poll. */
function backgroundTool(spec) {
  const sid = (turn && turn.sessionId) || currentSessionId;
  if (!sid || !spec.id) return;
  fetch('/background-tool', { method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ sessionId: sid }) })
    .then(r => r.json())
    .then(d => {
      if (!d || !d.ok) return;
      bgPending.add(spec.id); // job id unknown until the BACKGROUNDED result lands
      syncJobChips();
    })
    .catch(() => {});
}

async function send() {
  const text = input.value.trim();
  if (!text || processing) return;
  processing = true;
  sessionHidden = false; // a new message always brings the records back
  abortCtrl = new AbortController(); stopRequested = false;
  if (stopTimer) { clearTimeout(stopTimer); stopTimer = null; }
  if (!currentSessionId) {
    try {
      const r = await fetch('/new', { method: 'POST', signal: abortCtrl.signal });
      const { id } = await r.json();
      setCurrentSession(id); loadSessions();
    } catch (e) {}
  }
  const sid = currentSessionId;
  turn = { sessionId: sid, entries: [] }; // chronological: reasoning/text/tool/ask/error
  rawMessages.push({ role: 'user', content: text });
  sessionDirty = true;
  turn.userText = text;
  input.value = ''; setBusy(true); setStatus(T('status.thinking'));
  _liveCount = 0; window.potMotion?.waveOn?.(status);
  renderTurnLive();
  await pumpStream('/chat', { message: text, sessionId: sid, side: MY_SIDE });
  if (currentSessionId === sid) input.focus();
}

/* Alt+R: rerun the failed/stopped turn with no new prompt. */
async function retryTurn() {
  if (processing || !currentSessionId) return;
  processing = true;
  sessionHidden = false;
  abortCtrl = new AbortController(); stopRequested = false;
  if (stopTimer) { clearTimeout(stopTimer); stopTimer = null; }
  const sid = currentSessionId;
  turn = { sessionId: sid, entries: [] };
  sessionDirty = true;
  setBusy(true);
  setStatus(T('status.retrying'));
  _liveCount = 0; window.potMotion?.waveOn?.(status);
  renderTurnLive();
  await pumpStream('/retry', { sessionId: sid });
  if (currentSessionId === sid) input.focus();
}

/* ---------- 后台执行 → 作业状态芯片 (M2b, spec §3.4 裁决 20) ----------
   A backgrounded bash call comes back as a tool result starting with
   BACKGROUNDED (job=xxxxxxxx); the card keeps a status chip bound to that id.
   State rides ONE 3 s /jobs poll for the open session (restarted per session
   in setCurrentSession). /jobs carries no output — the final output arrives as
   a [job report] turn, so the chip only ever shows status (+ exit code). */
const JOB_RE = /job=([0-9a-f]{8})/;               // BACKGROUNDED (job=<8 hex>)
const JOB_STATUS = ['running', 'done', 'failed', 'killed', 'interrupted'];
const jobByCall = {};   // tool call id -> job id (from the card's own result text)
const bgPending = new Set(); // call ids backgrounded but not yet bound to a job id
const jobState = {};    // job id -> last /jobs row seen this page life
const jobGone = new Set();  // transcript job ids the server table no longer knows
let jobsPoll = null;    // the single interval handle

function jobChipText(job) {
  if (!job) return T('jobs.running');
  const status = job.status || 'running';
  if (!JOB_STATUS.includes(status)) return status;
  const text = T('jobs.' + status);
  return status === 'failed' && job.exitCode != null ? text + ' (exit ' + job.exitCode + ')' : text;
}

function paintJobChip(chip, jobId) {
  const job = jobId ? jobState[jobId] : null;
  chip.classList.toggle('running', !job || job.status === 'running');
  let state = chip.querySelector('.job-state');
  if (!state) {
    state = document.createElement('b');
    state.className = 'job-state';
    chip.prepend(state);
  }
  state.textContent = jobChipText(job);
  // Kill only for a job we can address and that is still running.
  const killable = !!jobId && (!job || job.status === 'running');
  const hasKill = !!chip.querySelector('.job-kill');
  if (killable && !hasKill) {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'job-kill';
    btn.textContent = '\u2715';
    btn.title = T('jobs.kill');
    btn.addEventListener('click', () => {
      btn.disabled = true;
      fetch('/jobs/kill', { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id: jobId }) }).catch(() => {});
    });
    chip.appendChild(btn);
  } else if (!killable && hasKill) {
    chip.querySelector('.job-kill').remove();
  }
}

/* Every tool card that carries a job id (its own result text live or from the
   re-rendered transcript) wears a chip; a card backgrounded but not yet bound
   wears one too, in running state. */
function syncJobChips() {
  if (!currentSessionId || !pane.is('session')) return;
  S.el().querySelectorAll('.msg.tool').forEach(card => {
    const callId = card.id && card.id.indexOf('tool-') === 0 ? card.id.slice(5) : '';
    const out = card.querySelector('.tool-result');
    const m = JOB_RE.exec(out ? out.textContent : '');
    const jobId = m ? m[1] : ((callId && jobByCall[callId]) || '');
    let chip = card.querySelector('.job-chip');
    if (jobId && jobGone.has(jobId)) { if (chip) chip.remove(); return; }
    if (!jobId && !(callId && bgPending.has(callId))) {
      if (chip && !chip.dataset.job) chip.remove(); // detach lost the race: no job coming
      return;
    }
    if (!chip) {
      chip = document.createElement('span');
      chip.className = 'job-chip';
      card.appendChild(chip);
    }
    if (jobId) chip.dataset.job = jobId;
    paintJobChip(chip, jobId);
  });
}

function pollJobs() {
  if (!currentSessionId || !pane.is('session')) return;
  syncJobChips(); // place/bind first so this response has chips to paint
  fetch('/jobs?sessionId=' + encodeURIComponent(currentSessionId))
    .then(r => r.json())
    .then(d => {
      const list = (d && d.jobs) || [];
      const ids = new Set(list.map(j => j.id));
      list.forEach(j => { jobState[j.id] = j; });
      S.el().querySelectorAll('.job-chip').forEach(chip => {
        const jobId = chip.dataset.job || '';
        if (!jobId) { paintJobChip(chip, ''); return; } // bgPending, id not bound yet
        if (ids.has(jobId)) { jobGone.delete(jobId); paintJobChip(chip, jobId); }
        else if (jobState[jobId]) paintJobChip(chip, jobId); // known final state
        else { jobGone.add(jobId); chip.remove(); } // table has no such job (restart)
      });
    })
    .catch(() => {});
}

/* One interval only: re-arming on every session open/close clears the old one,
   so no session ever stacks a second poll. */
function startJobsPoll() {
  if (jobsPoll) { clearInterval(jobsPoll); jobsPoll = null; }
  if (!currentSessionId) return;
  jobsPoll = setInterval(pollJobs, 3000);
  pollJobs();
}

/* A session's turn may still be running server-side (the client reloaded or
   switched away): /events replays what was missed, then streams live. */
function reattachIfRunning(sid) {
  if (processing || turn || !sid) return;
  const s = allSessions.find(x => x.id === sid);
  if (!s || !s.running) return;
  processing = true;
  abortCtrl = new AbortController(); stopRequested = false;
  turn = { sessionId: sid, entries: [] };
  setBusy(true); setStatus(T('status.reattaching'));
  _liveCount = 0; window.potMotion?.waveOn?.(status);
  renderTurnLive();
  pumpStream('/events?sessionId=' + encodeURIComponent(sid), null, 'GET');
}
/* A stream that dies without a done event (user hard-abort, network drop,
   server crash) leaves live-node cards whose content never reached a disk-
   backed render. Reconcile with the persisted transcript immediately, then
   resume streaming if the turn still runs server-side — otherwise the cards
   vanish at the next renderTurnLive (new send / reattach), with no done ever
   arriving to reload them. */
async function recoverAfterDrop(sid) {
  if (!sid) return;
  // Reconcile the session pane only when it is the pane on screen: a friend
  // conversation must survive a chat stream dying behind it.
  if (pane.is('session')) await reloadSessionFromServer();
  if (turn || processing) return; // user already started something else
  await loadSessions();           // fresh s.running for the reattach check
  reattachIfRunning(sid);
}
async function pumpStream(url, body, method = 'POST') {
  const sid = turn ? turn.sessionId : null; // the stream may die mid-turn
  try {
    const opts = { method, signal: abortCtrl.signal };
    if (body !== null) {
      opts.headers = { 'Content-Type': 'application/json' };
      opts.body = JSON.stringify(body);
    }
    const resp = await fetch(url, opts);
    if (!resp.ok) {
      // No early return: skipping the tail would leave the send button
      // disabled forever and the next send dead (no stream, no recovery).
      setStatus(T('status.http', { status: resp.status })); turn = null;
    } else {
      const reader = resp.body.getReader();
      const dec = new TextDecoder();
      let leftover = '';
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        leftover += dec.decode(value, { stream: true });
        const lines = leftover.split('\n');
        leftover = lines.pop() || '';
        for (const line of lines) {
          if (!line) continue;
          let obj;
          try { obj = JSON.parse(line); } catch (e) { continue; }
          handleTurnEvent(obj);
        }
      }
    }
  } catch (e) {
    if (e.name === 'AbortError') setStatus(T('status.aborted'));
    else setStatus(T('status.error', { msg: e.message }));
    turn = null;
    recoverAfterDrop(sid);
  }
  if (turn) {
    // Stream ended without a done event (server died mid-turn): the UI used
    // to stay stuck on "Writing..." with a phantom live turn.
    setStatus(T('status.retryHint'));
    turn = null;
    recoverAfterDrop(sid);
  }
  processing = false; setBusy(false);
  window.potMotion?.waveOff?.();
}

/* Turn events update the model first, then touch the DOM only when the
   turn's session is on screen — switching sessions mid-turn keeps the turn
   running in the background (no detached-node errors). */
function handleTurnEvent(obj) {
  const t = turn;
  if (!t) return;
  const visible = currentSessionId === t.sessionId && pane.is('session');
  const stick = isNearBottom(msgs); // measure before the event mutates the DOM
  switch (obj.type) {
    case 'text': {
      const last = t.entries[t.entries.length - 1];
      if (last && last.kind === 'text') last.content += obj.content;
      else t.entries.push({ kind: 'text', content: obj.content });
      setStatus(T('status.writing'));
      rateTok.feed();
      if (visible) updateLastText();
      break;
    }
    case 'reasoning_start':
      t.entries.push({ kind: 'reasoning', content: '', closed: false });
      if (visible) renderTurnLive();
      break;
    case 'reasoning': {
      const last = t.entries[t.entries.length - 1];
      if (last && last.kind === 'reasoning') last.content += obj.content;
      rateTok.feed();
      if (visible) updateLastReasoning();
      break;
    }
    case 'reasoning_end': {
      const idx = t.entries.map(x => x.kind).lastIndexOf('reasoning');
      if (idx >= 0) t.entries[idx].closed = true;
      if (visible) { const d = document.getElementById('live-details-' + idx); if (d) d.open = false; }
      break;
    }
    case 'tool':
      t.entries.push({ kind: 'tool', id: obj.content.id, name: obj.content.name, args: obj.content.args, result: '', startedAt: Date.now(), timeout_s: obj.content.timeout_s || 0 });
      // A long tool used to leave a stale "Writing..." on the status bar.
      if (visible) { setStatus(T('status.runningTool', { name: obj.content.name || 'tool' })); renderTurnLive(); }
      break;
    case 'tool_result': {
      const rec = t.entries.find(x => x.kind === 'tool' && x.id === obj.content.id)
        || [...t.entries].reverse().find(x => x.kind === 'tool' && !x.result);
      if (rec) rec.result = obj.content.content;
      // BACKGROUNDED (job=…): bind call -> job right away (M2b jobs chip). A
      // result WITHOUT the marker means the detach lost the race (the call had
      // finished first) — the pending mark goes either way, so no chip waits
      // on a job that will never exist.
      const jm = JOB_RE.exec(String(obj.content.content || ''));
      const wasPending = bgPending.delete(obj.content.id);
      if (jm) jobByCall[obj.content.id] = jm[1];
      if (visible) { setStatus(T('status.thinking')); const block = document.getElementById('tool-' + obj.content.id); if (block) FC.fillToolResult(block, obj.content.content); else renderTurnLive(); }
      if (jm || wasPending) syncJobChips();
      break;
    }
    case 'ask':
      t.entries.filter(x => x.kind === 'ask').forEach(a => a.active = false);
      t.entries.push({ kind: 'ask', id: obj.content.id, questions: obj.content.questions || [], answers: null, active: true });
      if (visible) renderTurnLive();
      break;
    case 'status':
      // Server-side progress notes (e.g. "queued behind a still-running turn").
      if (visible) setStatus(obj.content);
      break;
    case 'error':
      if (obj.content === 'Aborted by user') t.aborted = true;
      t.entries.push({ kind: 'error', content: obj.content });
      if (visible) renderTurnLive();
      break;
    case 'sessionId':
      if (!t.sessionId) t.sessionId = obj.content;
      break;
    case 'plan':
      // 裁决 17: the plan drawer repaints in place; done flips strike through
      // with the CSS sweep. The disk copy is re-read on the next full render.
      if (visible) renderPlan(obj.content.plan || [], true);
      break;
    case 'done': {
      // A finished session turn may only repaint its own pane: with a friend
      // conversation open, refresh the session list and leave #messages alone
      // (renderMessages enforces this too — this keeps the fetch out as well).
      const viewing = currentSessionId === t.sessionId && pane.is('session');
      const failed = t.entries.length && t.entries[t.entries.length - 1].kind === 'error';
      turn = null; abortCtrl = null; stopRequested = false;
      if (stopTimer) { clearTimeout(stopTimer); stopTimer = null; }
      // (Stop leaves jobs alone by design: a backgrounded bash lives in the job
      // table, and its chip keeps tracking it from here.)
      // The line under the input is a progress readout, so the end of a turn has
      // to clear it: nothing else does, and a session that never wrote a word
      // (the transfer session: one row, no model — §53) left "Thinking..." on
      // screen for good.
      setStatus(t.aborted ? T('status.aborted') : (failed ? T('status.turnFailed') : ''));
      if (viewing) reloadSessionFromServer();
      else loadSessions(); // the finished turn landed in a background session
      break;
    }
  }
  if (visible && currentSessionId === t.sessionId) { if (stick) S.stick(); updateScrollBtn(); }
}

function updateLastText() {
  const t = turn;
  const idx = t.entries.map(x => x.kind).lastIndexOf('text');
  if (idx < 0) return renderTurnLive();
  const el = document.getElementById('live-text-' + idx);
  if (el) { const stick = isNearBottom(msgs); el.innerHTML = marked.parse(FC.silentText(t.entries[idx].content)); if (stick) S.stick(); }
  else renderTurnLive();
}

function updateLastReasoning() {
  const t = turn;
  const idx = t.entries.map(x => x.kind).lastIndexOf('reasoning');
  if (idx < 0) return;
  const el = document.getElementById('live-reasoning-' + idx);
  if (el) { el.textContent = t.entries[idx].content; el.scrollTop = el.scrollHeight; const d = document.getElementById('live-details-' + idx); if (d) d.open = true; }
  else renderTurnLive();
}

function renderTurnLive() {
  if (!turn || turn.sessionId !== currentSessionId || !pane.is('session')) return;
  const saved = saveAskCardState();
  const stick = isNearBottom(msgs); // measure before the repaint replaces the DOM
  S.el().querySelectorAll('.live-node').forEach(n => n.remove());
  if (turn.userText && !turn.userRendered) {
    const u = document.createElement('div');
    u.className = 'msg user live-node';
    u.innerHTML = marked.parse(turn.userText);
    S.append(u);
  }
  turn.entries.forEach((e, i) => {
    if (e.kind === 'reasoning') {
      const det = document.createElement('details');
      det.className = 'msg reasoning live-node'; det.id = 'live-details-' + i; det.open = !e.closed;
      det.innerHTML = '<summary>' + T('transcript.thinking') + '</summary><div id="live-reasoning-' + i + '"></div>';
      det.querySelector('#live-reasoning-' + i).textContent = e.content;
      S.append(det);
    } else if (e.kind === 'text') {
      const text = FC.silentText(e.content);
      if (!text) return;
      const ad = document.createElement('div');
      ad.className = 'msg assistant live-node' + (FC.isSilentOnly(e.content) ? ' silent' : '');
      ad.id = 'live-text-' + i;
      ad.innerHTML = marked.parse(text);
      S.append(ad);
    } else if (e.kind === 'tool') {
      const d = FC.buildToolCard({ id: e.id, name: e.name, args: e.args, result: e.result, startedAt: e.startedAt, timeout_s: e.timeout_s }, { argsMax: 80, onBackground: backgroundTool });
      d.classList.add('live-node');
      S.append(d);
      if (e.name === 'spawn' || e.name === 'background') FC.attachSpawnClick(d, e.id, callId => specByCall[callId] || archivedByCall[callId]);
    } else if (e.kind === 'ask') {
      const card = e.active ? buildActiveAskCard(e, saved) : buildAnsweredAskCard(e);
      card.classList.add('live-node');
      S.append(card);
    } else if (e.kind === 'error') {
      const d = document.createElement('div');
      d.className = 'msg error live-node';
      d.innerHTML = '&#x26A0; ' + escapeHtml(e.content);
      S.append(d);
    }
  });
  S.stick();
  // Motion: animate only nodes that appeared since the previous streaming
  // re-render — every text chunk rebuilds .live-node, re-animating all of
  // them would flicker (docs/webui-ux.md contract).
  var _live = S.el().querySelectorAll('.live-node');
  if (window.potMotion && !window.potMotion.reduced) {
    for (var _li = _liveCount; _li < _live.length; _li++) {
      var _n = _live[_li];
      window.potMotion.msgIn(_n, _n.classList.contains('user') ? 'user'
        : _n.classList.contains('assistant') ? 'assistant' : 'other');
    }
  }
  _liveCount = _live.length;
  syncJobChips(); // live tool cards are rebuilt on every repaint
}
input.addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); }
  if (e.key === 'Escape' && abortCtrl && turn) requestStop();
});
// The button is stop while a turn runs, retry when the box is empty, send otherwise.
btn.addEventListener("click", () => {
  if (processing && turn) { requestStop(); return; }
  if (!input.value.trim()) {
    retryTurn(); // empty box = retry the last turn
    return;
  }
  send();
});
input.addEventListener('input', refreshSendButton);
refreshSendButton(); // initial label (empty box = retry, unless a shuttle is open)
document.addEventListener('keydown', e => {
  if (e.altKey && (e.key === 'r' || e.key === 'R')) {
    if (processing || !currentSessionId) return;
    if (document.getElementById('confirm-overlay').classList.contains('show')) return;
    e.preventDefault();
    retryTurn();
  }
});
document.getElementById('btn-browse').addEventListener('click', async () => {
  try {
    const r = await fetch('/pickfile', { method: 'POST' });
    const d = await r.json();
    if (d.path) { input.value = (input.value ? input.value + ' ' : '') + d.path; input.focus(); }
  } catch (e) {}
});
/* The header's model dropdown (spec §66): it loads the list itself and reports a
   switch on the status line — which the next turn overwrites, hence the colour
   the picker keeps on itself. */
const modelPicker = FC.mountModelPicker({
  note: t => { setStatus(t); },
  labels: {
    switching: T('model.switching'), ok: T('model.answers'),
    bad: T('model.failed'), served: T('model.servedAs'),
  },
});
loadSessions().then(() => {
  // Reload keeps the current session: restore it and reattach if its turn
  // is still running server-side (the /events tape replays what was missed).
  let saved = null;
  try { saved = localStorage.getItem('pot-session'); } catch (e) {}
  if (saved && allSessions.some(s => s.id === saved)) switchSession(saved);
});

/* ---------- ask card (Inquire) ---------- */
const Asks = FC.initAsks({
  http: FC,
  getTurn: () => turn,
  labels: {
    submit: T('ask.submit'), required: T('ask.required'),
    customPlaceholder: T('ask.customPlaceholder'), answerPlaceholder: T('ask.answerPlaceholder'),
    noAnswer: T('ask.noAnswer'),
  },
});
const saveAskCardState = Asks.saveAskCardState;
const buildActiveAskCard = Asks.buildActiveAskCard;
const buildAnsweredAskCard = Asks.buildAnsweredAskCard;


/* ---------- pending card asks (consent / cross-host asks, out-of-band) ---------- */
const PendingAsks = FC.initPendingAsks({
  http: FC,
  banner: () => document.getElementById('asks-banner'),
  inlineHost: () => null,
  msgs: () => msgs,
  isNearBottom,
  displayOf,
  animatePlace: true,
  motion: {
    cardIn: el => window.potMotion?.askCardIn?.(el),
    resolved: (card, ok, settle) => {
      const M = window.potMotion;
      if (M && !M.reduced && M.askResolved) {
        M.askResolved(card, ok);
        setTimeout(settle, 1000); // let the stamp read before collapsing
      } else settle();
    },
  },
  labels: {
    fromFallback: T('consent.fromFallback'),
    consentPlaceholder: T('consent.placeholderDesktop'),
    consentHint: T('consent.hint'),
    allow: T('consent.allow'), deny: T('consent.deny'), consentSend: T('consent.send'),
    submit: T('ask.submit'), required: T('ask.required'),
    customPlaceholder: T('ask.customPlaceholder'), answerPlaceholder: T('ask.answerPlaceholder'),
  },
});
const placeAskCards = PendingAsks.place, pollPendingAsks = PendingAsks.poll;
setInterval(pollPendingAsks, 3000);
/* (the 3 s resume poll is gone with M2b: /spawn-pending and /resume were
   removed. Job status rides the per-session /jobs poll started in
   setCurrentSession instead.) */

/* ---------- config modal ---------- */
(async () => {
  try {
    const r = await fetch('/config-status');
    /* 403 means this browser holds no token: the shell loads and nothing
       inside does. That is not "not configured" — showing the config card
       here sent the reader to fill in a wizard that could not change any of
       it (BUG-08). Say what is wrong instead, and leave the card to the case
       it was written for. */
    if (r.status === 403) {
      setStatus(T('auth.expired'));
      return;
    }
    const d = await r.json();
    if (!d.configured) {
      document.getElementById('config-overlay').classList.add('show');
      document.getElementById('cfg-save').addEventListener('click', async () => {
        const api_key = document.getElementById('cfg-apikey').value.trim();
        const endpoint = document.getElementById('cfg-endpoint').value.trim();
        const model = document.getElementById('cfg-model').value.trim();
        if (!api_key) {
          const err = document.getElementById('cfg-err');
          err.textContent = T('cfg.keyRequired'); err.style.display = 'block';
          return;
        }
        try {
          const r2 = await fetch('/configure', { method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ api_key, endpoint, model }) });
          const d2 = await r2.json();
          if (d2.ok) {
            document.getElementById('config-overlay').classList.remove('show');
            if (modelPicker) modelPicker.load();  // §66: the name just typed is now in the dropdown
          }
        } catch (e) {}
      });
      document.getElementById('cfg-skip').addEventListener('click', () => {
        document.getElementById('config-overlay').classList.remove('show');
      });
    }
  } catch (e) {}
})();

/* ---------- display names (asks + session labels fall back to the wire name) ---------- */
let allPeers = []; // [{name, display}] — display is the nickname, "" falls back to name

function peerName(p) { return typeof p === 'string' ? p : (p && p.name) || ''; }
function peerDisplay(p) { return typeof p === 'string' ? p : ((p && p.display) || peerName(p)); }
function displayOf(host) {
  for (const p of allPeers) if (peerName(p) === host) return peerDisplay(p);
  return host; // no display -> wire name
}














/* the live tape renderer is shared too (FC.renderLiveEvents) */


/* theme: light default, persisted; the switch flips html[data-theme] */
const themeRoot = document.documentElement;
function applyTheme(t) {
  themeRoot.dataset.theme = t;
  try { localStorage.setItem('pot-theme', t); } catch (e) {}
}
try { applyTheme(localStorage.getItem('pot-theme') === 'dark' ? 'dark' : 'light'); } catch (e) { applyTheme('light'); }
document.getElementById('theme-switch').addEventListener('click', function () {
  var next = themeRoot.dataset.theme === 'dark' ? 'light' : 'dark';
  if (window.potMotion && !window.potMotion.reduced && window.potMotion.themeTo) {
    window.potMotion.themeTo(next, this, function () { applyTheme(next); });
    return;
  }
  themeRoot.classList.add('theme-anim'); // cross-fade colors, then back to instant
  applyTheme(next);
  setTimeout(() => themeRoot.classList.remove('theme-anim'), 500);
});

/* ---------- session alerts (§61): 会话列表上的红点 ----------
   What a session wants (a turn finished / failed / is asking a question) rides
   two places: /sessions carries it, and the /session/seen answer carries the
   live map — see FC.initSessionAlerts, which also tells the server which
   session this page is showing (that is what stops the ring). Painted on
   creation AND on every reuse: rows are reconciled in place keyed by id, so a
   dot added once would otherwise never come off again. */
const ALERT_LABEL = { ask: T('alert.ask'), done: T('alert.done'), error: T('alert.error') };

function paintAlert(row, kind) {
  let dot = row.querySelector('.session-dot');
  if (!kind) { if (dot) dot.remove(); return; }
  if (!dot) {
    dot = document.createElement('span');
    dot.className = 'session-dot';
    row.querySelector('.session-row-meta').before(dot);
  }
  dot.title = ALERT_LABEL[kind] || T('alert.new');
}

function applyAlerts(map) {
  let changed = false;
  allSessions.forEach(s => {
    const kind = map[s.id] || null;
    if ((s.alert || null) !== kind) { s.alert = kind; changed = true; }
  });
  return changed;  // the caller owns the repaint: one render per change, never two
}

const Alerts = FC.initSessionAlerts({
  http: FC,
  showing: () => currentSessionId || '',
  onChange: map => { if (applyAlerts(map)) renderSessionList(); },
});
Alerts.start();


/* ---------- input composer (the session shell) ---------- */

