/* Pot shared web layer — the helpers app.js renders with (the ex-mobile shell
   shared it too; that shell is gone with the mobile cut). Exposed as
   window.PotCommon.
   Contracts preserved here:
   - pendingAskCards registration + placeAskCards re-mount (cards vanish mid-
     stream if either half is missing — see initPendingAsks).
   - buildToolCard fills #tool-<id> blocks by selector; fillToolResult patches
     .tool-result in place so streaming never re-renders the transcript. */
(function () {
  'use strict';

  /* WebUI i18n (web/i18n.js, loaded before this file): Chinese by default. */
  const T = window.PotI18N.t;

  /* Build marker: bump per web/ change so any WebUI instance can self-identify
     (console + window.__POT_WEB_VER) — stale cache vs new server is otherwise
     indistinguishable from the outside. */
  window.__POT_WEB_VER = 'web-scene-feed-lines';
  try { console.info('[pot-web]', window.__POT_WEB_VER); } catch (e) {}
  /* ---------- http ---------- */
  /* One fetch wrapper. Mobile inits a token prefix + 403 hook; desktop inits
     nothing and gets plain relative fetches back. */
  let _prefix = p => p;
  let _onUnauthorized = null;

  function initHttp(opts) {
    opts = opts || {};
    if (opts.prefix) _prefix = opts.prefix;
    if (opts.onUnauthorized) _onUnauthorized = opts.onUnauthorized;
  }
  function url(path) { return _prefix(path); }
  async function fetchJSON(path, opts) {
    const r = await fetch(_prefix(path), opts);
    if (r.status === 403 && _onUnauthorized) { _onUnauthorized(); throw new Error('unauthorized'); }
    return r;
  }
  function postJSON(path, body) {
    return fetchJSON(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
  }

  /* ---------- helpers ---------- */
  function escapeHtml(s) {
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }
  function fmtDate(d, locale) {
    if (!d) return '';
    const diff = Date.now() - new Date(d).getTime();
    const m = Math.floor(diff / 60000);
    if (m < 1) return T('time.now');
    if (m < 60) return m + 'm';
    const h = Math.floor(m / 60);
    if (h < 24) return h + 'h';
    const days = Math.floor(h / 24);
    if (days < 7) return days + 'd';
    return new Date(d).toLocaleDateString(
      locale || (window.PotI18N.lang === 'zh' ? 'zh-CN' : 'en-US'),
      { month: 'short', day: 'numeric' }
    );
  }
  function getSessionTitle(list, wrap, keep) {
    // 裁决 35: a host note is not the user's words and never titles a row.
    const u = (list || []).find(m => m.role === 'user' && !m.internal);
    if (!u) return T('session.emptyTitle');
    const t = String(u.content).replace(/\s+/g, ' ').trim();
    return t.length > wrap ? t.slice(0, keep) + '...' : t;
  }

  /* ---------- confirm modal (基建) ----------
     Same #confirm-overlay markup on both shells; desktop adds Escape/Enter
     keys + mousedown-outside close (Enter never confirms danger), mobile
     closes on backdrop tap. */
  let _confirmState = null;
  let _confirmDefaults = { title: T('confirm.title'), confirmText: T('confirm.ok'), cancelText: T('confirm.cancel') };

  function showConfirm(opts) {
    const overlay = document.getElementById('confirm-overlay');
    const ok = document.getElementById('confirm-ok');
    document.getElementById('confirm-title').textContent = opts.title || _confirmDefaults.title;
    document.getElementById('confirm-message').textContent = opts.message || '';
    ok.textContent = opts.confirmText || _confirmDefaults.confirmText;
    document.getElementById('confirm-cancel').textContent = opts.cancelText || _confirmDefaults.cancelText;
    ok.classList.toggle('danger', !!opts.danger);
    _confirmState = { onConfirm: opts.onConfirm, danger: !!opts.danger };
    overlay.classList.add('show');
    const cancel = document.getElementById('confirm-cancel');
    if (cancel.focus) cancel.focus();
  }
  function closeConfirm(confirmed) {
    const overlay = document.getElementById('confirm-overlay');
    if (!overlay.classList.contains('show')) return;
    overlay.classList.remove('show');
    const state = _confirmState;
    _confirmState = null;
    if (confirmed && state && state.onConfirm) state.onConfirm();
  }
  function initConfirmModal(opts) {
    opts = opts || {};
    _confirmDefaults = {
      title: opts.title || T('confirm.title'),
      confirmText: opts.confirmText || T('confirm.ok'),
      cancelText: opts.cancelText || T('confirm.cancel'),
    };
    const overlay = document.getElementById('confirm-overlay');
    document.getElementById('confirm-ok').addEventListener('click', () => closeConfirm(true));
    document.getElementById('confirm-cancel').addEventListener('click', () => closeConfirm(false));
    if (opts.keyboard === 'desktop') {
      overlay.addEventListener('mousedown', e => { if (e.target === overlay) closeConfirm(false); });
      document.addEventListener('keydown', e => {
        if (!overlay.classList.contains('show')) return;
        if (e.key === 'Escape') { e.preventDefault(); closeConfirm(false); }
        // Enter confirms non-danger prompts only; destructive actions need a real click.
        if (e.key === 'Enter' && _confirmState && !_confirmState.danger) {
          e.preventDefault();
          closeConfirm(true);
        }
      });
    } else {
      overlay.addEventListener('click', e => { if (e.target.id === 'confirm-overlay') closeConfirm(false); });
    }
  }

  /* ---------- live countdown ticker (§74) ----------
     One 1s interval drives every running elapsed/total readout on screen —
     the running tool card's "已执行 Xs" and the inquire card's "已执行 Xs / 总 Ys"
     (the hidden 15-min ask wait that made users think it had hung). Elements
     register a start epoch + optional total + a format fn; a card removed from
     the DOM is pruned on the next tick, so re-renders never leak intervals. */
  const _tickEls = new Set();
  let _tickHandle = null;
  function _tickNow() {
    const now = Date.now();
    for (const el of Array.from(_tickEls)) {
      if (!el.isConnected) { _tickEls.delete(el); continue; }
      const elapsed = Math.max(0, Math.floor((now - el._tickStart) / 1000));
      el.textContent = el._tickFmt(elapsed, el._tickTotal || 0);
    }
    if (!_tickEls.size && _tickHandle) { clearInterval(_tickHandle); _tickHandle = null; }
  }
  function mountTimer(el, startedAt, totalSec, fmt) {
    el._tickStart = startedAt || Date.now();
    el._tickTotal = totalSec || 0;
    el._tickFmt = fmt;
    // Paint the first reading directly — do NOT run _tickNow() here: the card is
    // not yet in the DOM (the caller appends it after buildToolCard returns), so
    // a prune pass would drop it as disconnected and kill the interval. The 1s
    // ticker finds it connected (the append is synchronous, same task).
    el.textContent = fmt(0, el._tickTotal);
    _tickEls.add(el);
    if (!_tickHandle) _tickHandle = setInterval(_tickNow, 1000);
  }

  /* ---------- tool card rendering ----------
     spec: { id?, name, args?, result?, startedAt?, timeout_s? } — id renders the
     #tool-<id> hook the streaming tool_result patches via fillToolResult; result
     pre-fills the output (live turn replay path). startedAt (epoch ms, set by the
     shell when the tool event lands) mounts a live "已执行 Xs" readout on a still-
     running card. timeout_s (bash only) turns that readout into "已执行 Xs / 总 Ys"
     and adds a 后台执行 button so an impatient user can background the call (§74).
     opts.argsMax: args snippet cap (80 desktop / 60 mobile). opts.onBackground:
     shell callback(spec) wired to the 后台执行 button. */
  function buildToolCard(spec, opts) {
    const argsMax = (opts && opts.argsMax) || 80;
    const d = document.createElement('div');
    d.className = 'msg tool';
    if (spec.id) d.id = 'tool-' + spec.id;
    const args = spec.args || '';
    const argsHtml = args ? ' <code>' + escapeHtml(args.length > argsMax ? args.slice(0, argsMax) + '...' : args) + '</code>' : '';
    d.innerHTML = '<div class="tool-label">&#x1F527; ' + escapeHtml(spec.name || 'tool') + argsHtml + '</div><div class="tool-result">' + (spec.result ? '<pre>' + escapeHtml(spec.result) + '</pre>' : '') + '</div>';
    const running = !spec.result && spec.startedAt;
    if (running) {
      const foot = document.createElement('div');
      foot.className = 'tool-foot';
      const tEl = document.createElement('span');
      tEl.className = 'tool-timer';
      const total = spec.timeout_s || 0;
      foot.appendChild(tEl);
      mountTimer(tEl, spec.startedAt, total,
        (e, t) => t ? T('tool.elapsedTotal', { e, t }) : T('tool.elapsed', { e }));
      // A bounded shell call is the one an impatient user waits on: offer to
      // background it (reuses the bg tool) instead of watching the countdown.
      if (total && opts && opts.onBackground) {
        const bg = document.createElement('button');
        bg.type = 'button';
        bg.className = 'tool-bg';
        bg.textContent = T('tool.background');
        bg.addEventListener('click', () => { bg.disabled = true; opts.onBackground(spec); });
        foot.appendChild(bg);
      }
      d.appendChild(foot);
    }
    if (spec.result && opts && opts.fileLink) linkifyPaths(d, opts.fileLink);
    return d;
  }
  function fillToolResult(block, content, onPick) {
    const foot = block.querySelector('.tool-foot');
    if (foot) { // result landed: stop the ticker and drop the 后台执行 button
      const timer = foot.querySelector('.tool-timer');
      if (timer) _tickEls.delete(timer);
      foot.remove();
    }
    const out = block.querySelector('.tool-result');
    out.innerHTML = '<pre>' + escapeHtml(content) + '</pre>';
    linkifyPaths(out, onPick);  // tool output is where the paths show up (§52)
  }
  /* Spawn/background cards deep-link into the client's agent replay store.
     lookup(callId) -> spec id; the modal itself stays client-side (different
     data shapes on desktop vs mobile). */
  function attachSpawnClick(el, callId, lookup, title) {
    el.classList.add('spawn-block');
    el.title = title || T('spawn.title');
    el.addEventListener('click', () => {
      const id = lookup(callId);
      if (id && typeof window.openAgentModal === 'function') window.openAgentModal(id);
    });
  }

  /* ---------- ask cards (in-turn Inquire) ---------- */
  /* labels: { submit, required, customPlaceholder, answerPlaceholder, noAnswer } */
  function initAsks(opts) {
    const http = opts.http;
    const t = opts.labels;

    function saveAskCardState() {
      const card = document.getElementById('ask-card');
      if (!card) return null;
      return (card._askQuestions || []).map((q, qi) => {
        const sel = card.querySelector('.ask-option.selected[data-q="' + qi + '"]');
        const inp = card.querySelector('.ask-input[data-q="' + qi + '"]');
        return { sel: sel ? sel.querySelector('b').textContent : null, val: inp ? inp.value : '' };
      });
    }

    function askQuestionHtml(q, qi) {
      const opts2 = (q.options || []).map(o =>
        '<button type="button" class="ask-option" data-q="' + qi + '"><b>' + escapeHtml(o.label) + '</b>'
        + (o.description ? '<br><span class="ask-desc">' + escapeHtml(o.description) + '</span>' : '') + '</button>').join('');
      return '<div class="ask-q">\u2753 ' + escapeHtml(q.question) + '</div>'
        + '<div class="ask-options">' + opts2 + '</div>'
        + (((q.options || []).length === 0 || q.allow_custom !== false)
          ? '<input class="ask-input" data-q="' + qi + '" placeholder="' + ((q.options || []).length ? t.customPlaceholder : t.answerPlaceholder) + '">'
          : '');
    }

    /* Clicking the selected option clears it: an answer may be typed text alone
       (see collectVals), so every choice has to be undoable — a second click on
       the picked item must not be a no-op. */
    function bindOptionToggles(card) {
      card.querySelectorAll('.ask-option').forEach(btn => {
        btn.addEventListener('click', () => {
          const was = btn.classList.contains('selected');
          card.querySelectorAll('.ask-option[data-q="' + btn.dataset.q + '"]').forEach(b => b.classList.remove('selected'));
          if (!was) btn.classList.add('selected');
        });
      });
    }

    /* "Required" normally lands in the input's placeholder; a question that
       allow_custom:false left option-only has no input to focus, so highlight
       its block for a beat instead. */
    function flagMissing(block) {
      if (!block) return;
      block.classList.add('ask-missing');
      setTimeout(() => block.classList.remove('ask-missing'), 1600);
    }

    /* Read every answer off a card, or null after flagging the first
       unanswered question. Selected option + typed note compose ("Label:
       note"); either alone stands as-is. No silent wiping in either
       direction. */
    function collectVals(card, questions) {
      const vals = [];
      for (let qi = 0; qi < questions.length; qi++) {
        const sel = card.querySelector('.ask-option.selected[data-q="' + qi + '"]');
        const inp = card.querySelector('.ask-input[data-q="' + qi + '"]');
        const label = sel ? sel.querySelector('b').textContent : '';
        const note = inp ? inp.value.trim() : '';
        const v = label && note ? label + ': ' + note : (label || note);
        if (!v) {
          if (inp) { inp.focus(); inp.placeholder = t.required; }
          else flagMissing(card.querySelectorAll('.ask-block')[qi]);
          return null;
        }
        vals.push(v);
      }
      return vals;
    }

    function buildActiveAskCard(a, saved) {
      const card = document.createElement('div');
      card.className = 'msg ask-card live-node'; card.id = 'ask-card';
      card._askId = a.id; card._askQuestions = a.questions;
      card.innerHTML = a.questions.map((q, qi) => '<div class="ask-block">' + askQuestionHtml(q, qi) + '</div>').join('')
        + '<div class="ask-actions"><button id="ask-submit">' + escapeHtml(t.submit) + '</button></div>';
      (saved || []).forEach((s, qi) => {
        if (s.sel) card.querySelectorAll('.ask-option[data-q="' + qi + '"]').forEach(b => {
          if (b.querySelector('b').textContent === s.sel) b.classList.add('selected');
        });
        if (s.val) { const inp = card.querySelector('.ask-input[data-q="' + qi + '"]'); if (inp) inp.value = s.val; }
      });
      bindOptionToggles(card);
      card.querySelectorAll('.ask-input').forEach(inp => {
        inp.addEventListener('keydown', e => { if (e.key === 'Enter') collectAskAnswers(card); });
      });
      card.querySelector('#ask-submit').addEventListener('click', () => collectAskAnswers(card));
      return card;
    }

    function buildAnsweredAskCard(rec) {
      const card = document.createElement('div');
      card.className = 'msg ask-card answered';
      if (rec.id) card.dataset.askId = rec.id;
      const qs = rec.questions || [];
      const ans = Array.isArray(rec.answers) ? rec.answers : (rec.answers != null ? [rec.answers] : null);
      card.innerHTML = qs.map((q, qi) => {
        const labels = (q.options || []).map(o => o.label);
        const a = ans ? (ans[qi] ?? '') : '';
        const isCustom = a && !labels.includes(a);
        const opts2 = (q.options || []).map(o =>
          '<button type="button" class="ask-option' + (!isCustom && o.label === a ? ' selected' : '') + '" style="cursor:default"><b>' + escapeHtml(o.label) + '</b>'
          + (o.description ? '<br><span class="ask-desc">' + escapeHtml(o.description) + '</span>' : '') + '</button>').join('');
        let row = '<div class="ask-q">\u2753 ' + escapeHtml(q.question) + '</div>'
          + '<div class="ask-options">' + opts2 + '</div>';
        if (rec.status && rec.status !== 'answered') row += '<div class="ask-a">' + t.noAnswer + '</div>';
        else if (isCustom || !labels.length) row += '<div class="ask-a">' + (a === 'no' ? '\u274C ' : '\u2705 ') + escapeHtml(a) + '</div>';
        return '<div class="ask-block">' + row + '</div>';
      }).join('');
      return card;
    }

    function collectAskAnswers(card) {
      const qs = card._askQuestions || [];
      const vals = collectVals(card, qs);
      if (!vals) return;
      const turn = opts.getTurn ? opts.getTurn() : null;
      const rec = (turn && turn.entries || []).find(x => x.kind === 'ask' && x.id === card._askId);
      if (rec) { rec.answers = vals; rec.active = false; }
      const answered = buildAnsweredAskCard({ questions: qs, answers: vals, status: 'answered' });
      answered.classList.add('live-node');
      card.replaceWith(answered);
      http.postJSON('/answer', { id: card._askId, value: vals }).catch(() => {});
    }

    return { saveAskCardState, askQuestionHtml, buildActiveAskCard, buildAnsweredAskCard, bindOptionToggles, collectVals };
  }

  /* ---------- pending card asks (consent / cross-host asks, out-of-band) ----------
     Contract: every new ask is registered in pendingAskCards AND re-mounted by
     placeAskCards after every full repaint. Missing either makes cards vanish
     mid-stream. ctx: {
       http,                 // {fetchJSON, postJSON}
       banner,               // () -> #asks-banner element
       inlineHost,           // () -> host name while a friend view is open, else null
       msgs,                 // () -> #messages element
       isNearBottom,         // fn(el) -> bool (client-specific threshold)
       displayOf,            // fn(host) -> display name
       motion,               // { cardIn?(el), resolved?(card, ok, settle) } — both optional
       animatePlace,         // animate remounts during place() (desktop yes, mobile no)
       labels: { fromFallback, consentPlaceholder, consentHint?, allow, deny, consentSend, submit, required, customPlaceholder, answerPlaceholder }
     } */
  function initPendingAsks(ctx) {
    const asks = initAsks({ http: ctx.http, labels: { submit: ctx.labels.submit, required: ctx.labels.required, customPlaceholder: ctx.labels.customPlaceholder, answerPlaceholder: ctx.labels.answerPlaceholder, noAnswer: '' } });
    const pendingAskIds = new Set();
    const pendingAskCards = new Map(); // ask id -> {rec, el} while the card is live
    const resolvedAskCards = new Map(); // answered card asks: verdict stays visible

    function mount(el, conv, animate) {
      const inline = ctx.inlineHost() && conv === ctx.inlineHost();
      if (inline) {
        const stick = ctx.isNearBottom(ctx.msgs()); // measure before the card changes layout
        ctx.msgs().appendChild(el);
        if (stick) ctx.msgs().scrollTop = ctx.msgs().scrollHeight;
      } else if (el.parentElement !== ctx.banner()) {
        ctx.banner().appendChild(el);
      }
      if (animate && ctx.motion && ctx.motion.cardIn) ctx.motion.cardIn(el);
    }

    function place() {
      // A pending ask belongs to the conversation that raised it: inline in the
      // matching open friend view, otherwise the global banner. Answered cards
      // follow the same rule until the durable transcript record (saved by the
      // server) renders — that copy then replaces the floating one.
      pendingAskCards.forEach(({ rec, el }) => mount(el, rec.conv, ctx.animatePlace));
      resolvedAskCards.forEach(({ rec, el }) => {
        if (ctx.inlineHost() && rec.conv === ctx.inlineHost()) {
          if (ctx.msgs().querySelector('.ask-card[data-ask-id="' + rec.id + '"]')) {
            el.remove();
            resolvedAskCards.delete(rec.id);
          } else mount(el, rec.conv, false);
        } else if (el.parentElement !== ctx.banner()) {
          ctx.banner().appendChild(el);
        }
      });
    }

    function buildPendingAskCard(a) {
      const card = document.createElement('div');
      card.className = 'msg ask-card pending-ask';
      const fromRaw = String(a.from || a.src || ctx.labels.fromFallback);
      const from = escapeHtml(ctx.displayOf(fromRaw.split(':')[0]));
      if (a.kind === 'consent') {
        const q = a.questions[0] || { question: '(consent request)' };
        card.innerHTML = '<div class="ask-from">\u{1F344} ' + from + ' \u00b7 consent</div>'
          + '<div class="ask-block"><div class="ask-q">\u2753 ' + escapeHtml(q.question) + '</div></div>'
          + '<div class="ask-consent-actions"><input placeholder="' + escapeHtml(ctx.labels.consentPlaceholder) + '">'
          + '<button class="ask-allow">' + escapeHtml(ctx.labels.allow) + '</button>'
          + '<button class="ask-deny">' + escapeHtml(ctx.labels.deny) + '</button><button class="ask-send">' + escapeHtml(ctx.labels.consentSend) + '</button></div>'
          + (ctx.labels.consentHint ? '<div class="ask-hint">' + escapeHtml(ctx.labels.consentHint) + '</div>' : '');
        const inp = card.querySelector('input');
        const send = v => answerPendingAsk(a, card, v);
        card.querySelector('.ask-allow').addEventListener('click', () => send(inp.value.trim() ? 'yes: ' + inp.value.trim() : 'yes'));
        card.querySelector('.ask-deny').addEventListener('click', () => send(inp.value.trim() ? 'no: ' + inp.value.trim() : 'no'));
        const custom = () => { if (inp.value.trim()) send(inp.value.trim()); else inp.focus(); };
        card.querySelector('.ask-consent-actions input').addEventListener('keydown', e => { if (e.key === 'Enter') custom(); });
        card.querySelector('.ask-send').addEventListener('click', custom);
      } else {
        card.innerHTML = '<div class="ask-from">\u{1F344} ' + from + '</div>'
          + a.questions.map((q, qi) => '<div class="ask-block">' + asks.askQuestionHtml(q, qi) + '</div>').join('')
          + '<div class="ask-actions"><button class="ask-send">' + escapeHtml(ctx.labels.submit) + '</button></div>';
        asks.bindOptionToggles(card);
        card.querySelector('.ask-send').addEventListener('click', () => {
          const vals = asks.collectVals(card, a.questions || []);
          if (!vals) return;
          answerPendingAsk(a, card, vals.length === 1 ? vals[0] : vals);
        });
      }
      return card;
    }

    function answerPendingAsk(a, card, value) {
      ctx.http.postJSON('/answer', { id: a.id, value }).catch(() => {});
      pendingAskIds.delete(a.id);
      pendingAskCards.delete(a.id);
      // The verdict stays as a real answered card (same builder as the in-turn
      // replay path) instead of evaporating after 8 seconds; the server also
      // files it into the friend transcript so it survives reload.
      const done = asks.buildAnsweredAskCard({
        id: a.id,
        questions: a.questions,
        answers: Array.isArray(value) ? value : [value],
        status: 'answered',
      });
      const settle = () => {
        card.replaceWith(done);
        resolvedAskCards.set(a.id, { rec: a, el: done });
      };
      if (ctx.motion && ctx.motion.resolved) ctx.motion.resolved(card, value !== 'no', settle);
      else settle();
    }

    async function poll() {
      try {
        const d = await (await ctx.http.fetchJSON('/asks')).json();
        (d.asks || []).forEach(a => {
          if (pendingAskIds.has(a.id)) return;
          pendingAskIds.add(a.id);
          const el = buildPendingAskCard(a);
          pendingAskCards.set(a.id, { rec: a, el });
          mount(el, a.conv, true);
        });
      } catch (e) {}
    }

    return { poll, place, pendingAskIds, pendingAskCards, resolvedAskCards };
  }

  /* ---------- mail unread (留言未读计数, per-peer) ----------
     Polls this host's mailbox and exposes per-peer unread counts for the
     friend list. Reading happens in the friend view: markPeerRead clears
     everything a peer sent.
     opts: { http, onChange(map) }
     Backend: GET /mail -> {host, mails:[{id, from, peer, body, ts, read, mine}], unread};
     POST /mail/read {id} -> {ok}. */
  

  /* ---------- session alerts (§61): 红点 + 「我正在看这个会话」 ----------
     One request does both jobs every 3 s (POST /session/seen {id, visible}):
     it claims the session the user is looking at — the server drops that
     session's alert, which is what stops the ring — and the answer carries
     every outstanding alert, which is where the sidebar's dots come from.

     The claim rides visible AND focused: a minimized webUI is not "opened"
     (user rule, 2026-09-21) — that is exactly when the ring has to fire. A
     claim goes stale on the server after ~8 s, so a page that dies cannot
     silence the ring for good; leaving the page releases it at once.

     opts: { http, showing() -> session id | '', onChange(map) } */
  function initSessionAlerts(opts) {
    let claim = '';   // the session this page told the server it is showing
    let feed = null;  // last alert map handed to onChange (no change: no call)
    let timer = null;

    function deliver(map) {
      const key = JSON.stringify(map || {});
      if (key === feed) return;      // 没变就不碰 DOM（§55 的纪律）
      feed = key;
      if (opts.onChange) opts.onChange(map || {});
    }

    function send(id, visible) {
      return opts.http.fetchJSON('/session/seen', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id: id || '', visible: !!visible }),
        keepalive: true,  // the pagehide release still gets out
      }).then(r => r.json()).then(d => deliver(d.alerts)).catch(() => {});
    }

    function claimed() {
      if (document.hidden || !document.hasFocus()) return '';
      return opts.showing() || '';
    }

    function tick() {
      const next = claimed();
      const sent = [];
      if (next !== claim) {
        if (claim) sent.push(send(claim, false));  // switched away / hidden: release it
        claim = next;
      }
      sent.push(send(claim, !!claim));  // heartbeat + claim, or just the map
      return Promise.all(sent);         // awaitable: the release has landed when it resolves
    }

    function start() {
      document.addEventListener('visibilitychange', tick);
      // Focus counts too, so coming back claims at once instead of up to 3 s later.
      window.addEventListener('focus', tick);
      window.addEventListener('blur', tick);
      window.addEventListener('pagehide', () => { if (claim) send(claim, false); });
      tick();
      timer = setInterval(tick, 3000);
    }
    function stop() { if (timer) { clearInterval(timer); timer = null; } }
    // null until the first answer lands: a client that has not heard from
    // /session/seen yet must paint from /sessions, not from an empty map.
    function map() { return feed === null ? null : JSON.parse(feed); }
    return { start, stop, tick, map };
  }

  /* ---------- #messages ownership ----------
     One container, one owner at a time. Every render path used to write into
     the same #messages/#tray and trust separate entry guards to keep the other
     view out; a guard someone forgot painted the session transcript over an
     open friend conversation, and the friend poll would not repaint it (its
     payload had not changed) — the thread only came back on a page refresh
     (2026-09-10 real-machine finding).

     Now the writes go through a view-bound writer: `pane.of('friend').add(...)`
     writes only while the friend view owns the pane, and is a no-op otherwise
     (the node is built but never attached). Ownership is one flag instead of a
     convention spread across the render sites, and `pane.owner()` can be
     asserted directly.

     ctx: { msgs() -> el, tray() -> el, isNearBottom(el) -> bool, onPaint?() } */
  function initPane(ctx) {
    let owner = 'session';
    const refused = []; // view:paint pairs dropped for not owning the pane
    const painted = () => { if (ctx.onPaint) ctx.onPaint(); };
    // The mobile page has no persistent tray (its bubbles live in a bottom
    // sheet it manages itself), so the tray side is optional.
    const clearTray = () => {
      const t = ctx.tray && ctx.tray();
      if (t) t.innerHTML = '';
    };
    function of(view) {
      const active = () => owner === view;
      const attach = (node, ref) => {
        if (!active()) { refused.push(view + ':' + (node.nodeName || '?') + '.' + (node.className || '')); return node; }
        const el = ctx.msgs();
        if (ref) el.insertBefore(node, ref); else el.appendChild(node);
        painted();
        return node;
      };
      return {
        view,
        active,
        /* The live container. Reads (children, querySelectorAll) are safe from
           any view; a write through it is not — use the methods below. */
        el: () => ctx.msgs(),
        clear() {
          if (!active()) { refused.push(view + ':clear'); return false; }
          ctx.msgs().innerHTML = '';
          clearTray();
          painted();
          return true;
        },
        /* Messages only: a transcript repaint must not wipe the live subagent
           bubbles sitting in the tray. */
        clearMsgs() {
          if (!active()) { refused.push(view + ':clear-msgs'); return false; }
          ctx.msgs().innerHTML = '';
          painted();
          return true;
        },
        /* Build a .msg node and append it, keeping the reader pinned to the
           bottom the way a chat should. A refused write still hands the node
           back (detached), so callers can decorate what they get. pinOnAdd
           false = the caller pins once at the end of its own render. */
        add(cls, html, id) {
          const d = document.createElement('div');
          d.className = 'msg ' + cls;
          if (id) d.id = id;
          if (html) d.innerHTML = html;
          const pin = ctx.pinOnAdd !== false && active() && ctx.isNearBottom(ctx.msgs());
          attach(d);
          if (pin) { const el = ctx.msgs(); el.scrollTop = el.scrollHeight; }
          return d;
        },
        append: node => attach(node),
        before: (node, ref) => attach(node, ref),
        prepend(node) {
          if (!active()) { refused.push(view + ':prepend'); return node; }
          ctx.msgs().prepend(node);
          painted();
          return node;
        },
        /* Keep the bottom pinned after a repaint that replaced the pane. */
        stick() {
          if (!active()) return false;
          const el = ctx.msgs();
          el.scrollTop = el.scrollHeight;
          return true;
        },
        inTray(node) {
          const t = ctx.tray && ctx.tray();
          if (!active() || !t) { refused.push(view + ':tray'); return node; }
          t.appendChild(node);
          return node;
        },
      };
    }
    return {
      owner: () => owner,
      is: view => owner === view,
      /* Hand the pane to a view and wipe it: whoever takes over starts empty. */
      take(view) {
        owner = view;
        ctx.msgs().innerHTML = '';
        clearTray();
        painted();
      },
      of,
      refused,
    };
  }

  /* A human message shows up twice: the mailbox (authoritative — both sides, the
     sender's nickname, a hub timestamp) and the courier's transcript of the turn
     it woke (`[来自 <host> 的用户] text`, built by clone/base.py render_input).
     The transcript copy carries the WIRE name, so with a nickname set the same
     line looked like two messages signed by two different people (2026-09-10
     user report). The mailbox copy is the one to keep; this recognises the echo. */
  function humanEcho(content) {
    const m = /^\[来自 (.+?) 的用户\]\s?([\s\S]*)$/.exec(String(content || ''));
    return m ? { who: m[1], text: m[2].trim() } : null;
  }

  /* Owner feedback on a courier report: the box under every report in the
     friend view, and it is between the owner and their OWN courier — the note
     wakes that courier's turn locally and never reaches the peer (2026-09-11
     user instruction: 「与对面没有关系」). An empty box sends nothing: leaving
     it alone is allowed, so an empty submit is a no-op rather than an error.
     The button's label is CSS content, not a text node: a row's textContent
     stays the row's own words (the same rule the 信使汇报 label follows, and
     the row-text probes in tests/test_webui_friend.py depend on). */
  function attachReportFeedback(row, host) {
    const form = document.createElement('form');
    form.className = 'report-feedback';
    form.innerHTML =
      '<input type="text" placeholder="' + escapeHtml(T('mail.placeholder')) + '" />' +
      '<button type="submit" aria-label="' + escapeHtml(T('mail.send')) + '"></button>' +
      '<span class="fb-hint"></span>';
    const input = form.querySelector('input');
    const hint = form.querySelector('.fb-hint');
    form.addEventListener('submit', async ev => {
      ev.preventDefault();
      const text = input.value.trim();
      if (!text) { hint.textContent = ''; return; }   // 允许为空：没写就不发
      hint.textContent = T('mail.sending');
      try {
        // postJSON hands back the Response (its callers so far just fire and
        // forget), so the body decides whether the note actually landed —
        // a 200 carrying {"error": ...} must not read as success.
        const res = await postJSON('/comm-note', { host, text });
        const out = await res.json().catch(() => null);
        if (out && out.ok) {
          input.value = '';
          hint.textContent = T('mail.sent');
        } else {
          const why = (out && out.error) || T('mail.failed');
          hint.textContent = /no comm clone/.test(why) ? T('mail.notReady') : why;
        }
      } catch (e) {
        hint.textContent = T('mail.failed');
      }
    });
    row.appendChild(form);
    return form;
  }

  /* The courier's abstention marker is a delivery control token, not text to
     read: `<<SILENT>>` ends a comm turn silently (clone/comm.py). When one is
     left in a transcript — an older file, or the model adding it after real
     words — the browser throws the unknown tag away and the reader sees `<>`
     (2026-09-10 user report). Strip it wherever a body is rendered. */
  const SILENT_MARKER = '<<SILENT>>';
  function stripSilent(text) {
    const s = String(text == null ? '' : text);
    return s.includes(SILENT_MARKER) ? s.split(SILENT_MARKER).join('').trim() : s;
  }
  /* A reply that is nothing but the marker is the agent choosing not to speak
     (user rule, 2026-10-21: show 「（Agent不说话）」 instead of an empty bubble).
     Real words around the marker still win: the marker is only control text. */
  function isSilentOnly(text) {
    const s = String(text == null ? '' : text);
    return s.includes(SILENT_MARKER) && !s.split(SILENT_MARKER).join('').trim();
  }
  function silentText(text) {
    const s = stripSilent(text);
    return s || (String(text == null ? '' : text).includes(SILENT_MARKER) ? T('transcript.silent') : '');
  }

  /* ---------- transcript rendering (both clients) ----------
     Session-style rendering: markdown text, reasoning details, tool blocks and
     answered ask cards — plus the friend thread's timeline, where rows carrying
     a `ts` merge into the transcript by time and ask cards sit at the tool call
     that raised them. The two clients differ only in cosmetics, so those come
     in through opts:

       asks            the client's FC.initAsks() bundle (answered cards)
       spawnLookup     callId -> subagent spec (the client's replay store)
       friend          true for the friend thread (mail echo dedupe on)
       side            {user, agent} extra classes for the friend thread
       mailBodies      Set of mailbox bodies already on screen (echo dedupe)
       argsMax         tool-card argument preview length
       spawnTitle      tooltip wording for spawn cards (mobile says 点按…)
       reasoningHtml   (text) -> inner html of the reasoning <details>
       feedbackHost    friend view only: the peer whose courier gets the
                       feedback box on every report row
       liveText        (run) -> html for a streaming text run
  */
  function markTs(el, ts) {
    if (el && typeof ts === 'number') {
      el.dataset.ts = String(ts);
      el.dataset.when = whenLabel(ts); // hover label (style.css ::after)
    }
    return el;
  }
  const WEEKDAYS = {
    zh: ['星期日', '星期一', '星期二', '星期三', '星期四', '星期五', '星期六'],
    en: ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'],
  };
  /* When a message was sent, in words: 今天/昨天/前天 up close, the weekday
     inside the last seven days, 年月日 beyond that. 24h clock. Computed at
     paint time and re-painted with the row, so a "今天" that has since turned
     into yesterday is corrected on the next poll. */
  function whenLabel(ts) {
    const d = new Date(ts * 1000), now = new Date();
    const pad = n => String(n).padStart(2, '0');
    const sameDay = x => new Date(x.getFullYear(), x.getMonth(), x.getDate()).getTime();
    const days = Math.round((sameDay(now) - sameDay(d)) / 86400000);
    let date;
    if (days === 0) date = T('time.today');
    else if (days === 1) date = T('time.yesterday');
    else if (days === 2) date = T('time.beforeYesterday');
    else if (days >= 0 && days < 7) {
      date = (WEEKDAYS[window.PotI18N.lang] || WEEKDAYS.en)[d.getDay()];
    }
    else date = d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate());
    return date + ' ' + pad(d.getHours()) + ':' + pad(d.getMinutes());
  }
  /* The friend thread has two sides: the peer's rows and ours (the courier's).
     Everything a turn emits belongs to the side that produced it — its words,
     but also its reasoning, its tool calls and its errors (2026-09-10 user
     report: our prose sat right while our reasoning still hugged the left). */
  function sided(el, extra) {
    if (el && extra) el.className += extra;
    return el;
  }
  function insertByTs(p, el, ts) {
    if (!el || !p.active()) return el;
    if (typeof ts !== 'number') return el; // no stamp: keep it where it landed
    for (const kid of [...p.el().children]) {
      const kts = kid.dataset && kid.dataset.ts ? parseFloat(kid.dataset.ts) : null;
      if (kts !== null && kts > ts) { p.before(el, kid); return el; }
    }
    return el;
  }
  /* The question text a tool call itself carries — the only way to place an ask
     record from before records carried `call_id`. Exact match, no fuzzy. */
  function askTextOfCall(tc) {
    try {
      const args = JSON.parse(tc.function && tc.function.arguments || '{}');
      const first = Array.isArray(args.questions) && args.questions.length ? args.questions[0] : args;
      return String((first && first.question) || args.question || '').trim();
    } catch (e) { return ''; }
  }

  /* Absolute paths in the transcript become taps (§52): on the phone, tapping
     one pulls that file over. Only the shells that pass `fileLink` get links —
     the desktop already has the file it is looking at.

     The rewrite walks text nodes, never the HTML string: what comes in is
     marked's output, and a regex over markup is how tags get broken (or a link
     ends up inside an href). */
  const PATH_RE = /[A-Za-z]:[\\/][^\s"'<>|*?\u3002\uff0c\uff09\uff1f\uff01\u3011\u3015\uff1b\uff1a]+/g;
  const DRIVE_RE = /[A-Za-z]:[\\/]/g;
  /* A line that *is* the path. Nothing on a page can stat a file, so this is
     the only shape that survives a name with blanks of its own — `屏幕录制
     2026-09-17 090847.mp4` cut at the first blank is a link to nothing (§53). */
  const LINE_PATH_RE = /^[A-Za-z]:[\\/][^\r\n"'<>|*?\u3002\uff0c\uff09\uff1f\uff01\u3011\u3015\uff1b\uff1a]*$/;

  const trimTail = path => path.replace(/[\\.,;:\uff09)]+$/, '');  // trailing punctuation is prose

  /* Where the paths are in one text node: whole lines first — they are the ones
     a blank does not end — then what the narrow pattern finds. A line naming
     two files is a sentence, not a path, so it goes to the scan. */
  function pathSpans(text) {
    const spans = [];
    let at = 0;
    for (const line of text.split('\n')) {
      const from = at;
      at += line.length + 1;
      const body = line.trim();
      if (!body) continue;
      if ((body.match(DRIVE_RE) || []).length === 1 && LINE_PATH_RE.test(body)) {
        const whole = trimTail(body);
        if (whole) {
          spans.push({ start: from + line.length - line.trimStart().length, text: whole });
          continue;
        }
      }
      PATH_RE.lastIndex = 0;
      let m;
      while ((m = PATH_RE.exec(line)) !== null) {
        const path = trimTail(m[0]);
        if (path) spans.push({ start: from + m.index, text: path });
        PATH_RE.lastIndex = m.index + m[0].length;
      }
    }
    return spans;
  }

  function linkifyPaths(root, onPick) {
    if (!root || !onPick) return;
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, null);
    const texts = [];
    while (walker.nextNode()) texts.push(walker.currentNode);
    for (const node of texts) {
      const parent = node.parentNode;
      if (!parent || (parent.closest && parent.closest('a, .file-card'))) continue;
      const text = node.nodeValue || '';
      const spans = pathSpans(text);
      if (!spans.length) continue;  // nothing matched: the node stays untouched
      const frag = document.createDocumentFragment();
      let at = 0;
      for (const span of spans) {
        if (span.start < at) continue;
        if (span.start > at) frag.appendChild(document.createTextNode(text.slice(at, span.start)));
        const a = document.createElement('a');
        a.className = 'file-link';
        a.href = '#';
        a.textContent = span.text;
        a.addEventListener('click', e => { e.preventDefault(); onPick(span.text); });
        frag.appendChild(a);
        at = span.start + span.text.length;
      }
      if (at < text.length) frag.appendChild(document.createTextNode(text.slice(at)));
      parent.replaceChild(frag, node);
    }
  }

  /* ---------- transfer card (§56) ----------
     One row of the file-transfer session, as a card: what was sent, how big,
     which side sent it, and where it is. A phone that can pull files gets the
     action right here — the path is not something to hunt for in a paragraph. */
  function humanBytes(n) {
    n = Number(n) || 0;
    if (n < 1024) return n + ' B';
    if (n < 1024 * 1024) return (n / 1024).toFixed(1) + ' KB';
    if (n < 1024 * 1024 * 1024) return (n / 1024 / 1024).toFixed(1) + ' MB';
    return (n / 1024 / 1024 / 1024).toFixed(2) + ' GB';
  }

  /* The card's two actions on this machine (§73). The page cannot launch
     anything, so a click becomes a POST and the host that owns the file does
     what a double-click would: `open` = the file's own association, `reveal` =
     its folder, file selected. A refusal has to be said out loud — a card that
     silently does nothing after a click is indistinguishable from a bug
     ("把状态藏起来 = 用户认为功能不存在") — so the reason lands inside the card,
     right under the finger, for a few seconds. */
  function cardComplain(card, msg) {
    let line = card.querySelector('.fc-error');
    if (!line) {
      line = document.createElement('div');
      line.className = 'fc-error';
      card.appendChild(line);
    }
    line.textContent = msg;
    clearTimeout(line._fade);
    line._fade = setTimeout(() => { if (line.parentNode) line.remove(); }, 6000);
  }

  function openOnHost(card, path, action) {
    postJSON('/open', { path: path, action: action })
      .then(r => (r.ok ? null : r.json().catch(() => ({})).then(d => d.error || ('HTTP ' + r.status))))
      .then(err => { if (err) cardComplain(card, err); })
      .catch(e => { if (e.message !== 'unauthorized') cardComplain(card, e.message || String(e)); });
  }

  /* The card wears the side it is handed (§59): "which device is mine" is the
     shell's question, not the row's, so `renderTranscript` picks between `mine`
     and `peer` — this function only draws. */
  function buildFileCard(file, opts) {
    const d = document.createElement('div');
    d.className = 'msg file-card' + (opts && opts.side ? opts.side : '');
    // The shuttle names the two ends by device (phone/PC); the friend view
    // names them by host ("我" vs the peer) — opts.who overrides the label.
    const who = (opts && opts.who)
      || (file.direction === 'phone' ? T('file.fromPhone') : T('file.fromPc'));
    d.innerHTML =
      '<div class="fc-head"><span class="fc-icon">&#x1F4C1;</span>'
      + '<span class="fc-name">' + escapeHtml(file.name || T('file.file')) + '</span>'
      + '<span class="fc-size">' + humanBytes(file.size) + '</span></div>'
      + '<div class="fc-where"></div>';
    // textContent all the way down: who/reason can carry a peer's nickname and
    // a human-typed reason — user-chosen text, never innerHTML.
    d.querySelector('.fc-where').textContent = who;
    if (file.reason) {
      const line = document.createElement('div');
      line.className = 'fc-where';
      line.textContent = file.reason;
      d.appendChild(line);
    }
    const path = file.path || '';
    // No path, no path line: a friend-view transfer names a file on the OTHER
    // machine — there is no local path to show (and the actions below stay
    // off, they were always gated on one). The shuttle's rows always carry one.
    if (path) {
      const pe = document.createElement('div');
      pe.className = 'fc-path';
      pe.textContent = path;
      d.appendChild(pe);
    }
    const acts = document.createElement('div');
    acts.className = 'fc-actions';
    if (path && opts && opts.canPull) {
      const btn = document.createElement('button');
      btn.className = 'fc-pull';
      btn.textContent = T('file.pull');
      btn.addEventListener('click', e => {
        e.preventDefault();
        e.stopPropagation();
        opts.canPull(path);
      });
      acts.appendChild(btn);
    }
    if (path) {
      const show = document.createElement('button');
      show.className = 'fc-reveal';
      show.textContent = T('file.reveal');
      show.addEventListener('click', e => {
        e.preventDefault();
        e.stopPropagation();
        openOnHost(d, path, 'reveal');
      });
      acts.appendChild(show);
    }
    if (acts.children.length) d.appendChild(acts);
    /* A shell that answers "yes, this is the machine with the file" (desktop)
       makes the whole card the way in (§73); the phone passes nothing, because
       opening it there would pop a window on someone else's desk. Selecting the
       path text is not a click-to-open — that would make the path uncopyable. */
    if (path && opts && opts.canOpen) {
      d.classList.add('fc-openable');
      d.addEventListener('click', e => {
        if (e.target.closest('button')) return;
        const sel = window.getSelection();
        if (sel && !sel.isCollapsed) return;
        openOnHost(d, path, 'open');
      });
    }
    return d;
  }

  function renderTranscript(p, messages, asks, opts) {
    const side = opts.side || {};
    const userSide = side.user || '';
    const agentSide = side.agent || '';
    const mailBodies = opts.mailBodies;
    let toolBlocks = {};
    const askByCall = new Map();  // ask record -> the tool call that raised it
    const askQueue = [];          // records without a call id, in stored order
    (asks || []).forEach(rec => {
      if (rec && rec.call_id) askByCall.set(rec.call_id, rec);
      else if (rec) askQueue.push(rec);
    });
    for (const m of messages || []) {
      if (m.internal) continue; // 裁决 35: host notes are model-only, never a row
      if (m.role === 'user') {
        /* Which side a row sits on is the *shell's* question, not the row's
           (§59): the desktop page is the computer, the phone page is the phone,
           so the same row is "mine" on one and "the other device's" on the
           other. A card says who sent it in its own fields; a plain message only
           says it if the shell that typed it declared itself. */
        const dir = m.direction || (m.file && m.file.direction) || '';
        const side = opts.my && dir ? (dir === opts.my ? ' mine' : ' peer') : '';
        if (m.file) {
          // A transfer (§53/§56): the card IS the row.
          p.append(markTs(buildFileCard(m.file, { canPull: opts.fileLink, canOpen: opts.canOpen, side }), m.ts));
          continue;
        }
        const c = String(m.content || '');
        const echo = opts.friend ? humanEcho(c) : null; // only the friend thread merges mail
        if (echo) {
          if (mailBodies && mailBodies.has(echo.text)) continue; // the mailbox copy is already on screen
          const bubble = markTs(p.add('user' + userSide + side, marked.parse(echo.text)), m.ts);
          const lab = document.createElement('div');
          lab.className = 'human-label';
          lab.textContent = T('transcript.fromUser', { who: echo.who });
          bubble.prepend(lab);
        }
        else if (c.startsWith('[background report]')) markTs(p.add('sys-note', escapeHtml(c)), m.ts);
        else if (m.sender === 'human' && !m.mine) {
          const bubble = markTs(p.add('user' + userSide + side, marked.parse(c)), m.ts);
          const lab = document.createElement('div');
          lab.className = 'human-label';
          lab.textContent = T('transcript.fromUser', { who: m.sender_name || '?' });
          bubble.prepend(lab);
        }
        else markTs(p.add('user' + userSide + side, marked.parse(c)), m.ts);
      }
      else if (m.role === 'assistant') {
        if (m.reasoning) {
          const det = document.createElement('details');
          det.className = 'msg reasoning' + agentSide;
          det.innerHTML = '<summary>' + T('transcript.thinking') + '</summary>' + opts.reasoningHtml(m.reasoning);
          p.append(markTs(det, m.ts));
        }
        const silent = isSilentOnly(m.content);
        const text = silentText(m.content);
        if (text) {
          if (text.startsWith('(LLM error:') || text.startsWith('(Hit max tool rounds'))
            markTs(p.add('error' + agentSide, '&#x26A0; ' + escapeHtml(text)), m.ts);
          else if (silent) {
            // The abstention line is not a report to answer: no feedback box.
            markTs(p.add('assistant silent' + agentSide, escapeHtml(text)), m.ts);
          } else {
            // Friend thread: our courier's turn text is a report to *us* — it
            // never went to the peer (comm._chat_end), so the stylesheet marks
            // it as one (a ::before label, so it stays out of the row's text),
            // and the row carries the feedback box back to that courier.
            const cls = 'assistant' + agentSide + (opts.report ? ' report' : '');
            const row = markTs(p.add(cls, marked.parse(text)), m.ts);
            if (opts.report && opts.feedbackHost) attachReportFeedback(row, opts.feedbackHost);
          }
        }
        if (m.tool_calls) m.tool_calls.forEach(tc => {
          const d = buildToolCard({ id: tc.id, name: tc.function?.name, args: tc.function?.arguments || '' }, { argsMax: opts.argsMax || 80 });
          p.append(markTs(sided(d, agentSide), m.ts));
          if (tc.function?.name === 'spawn' || tc.function?.name === 'background') attachSpawnClick(d, tc.id, opts.spawnLookup, opts.spawnTitle);
          if (tc.function?.name === 'inquire' || tc.function?.name === 'confirm' || tc.function?.name === 'ask_user') { // ask_user: pre-rename transcripts
            // Anchored by the tool call that raised it; a record without a call
            // id falls back to stored order, then to the call's own question text
            // (records written before `call_id` existed).
            let rec = askByCall.get(tc.id);
            if (rec) askByCall.delete(tc.id);
            else {
              const qtext = askTextOfCall(tc);
              const idx = qtext ? askQueue.findIndex(r => String(((r.questions || [])[0] || {}).question || '').trim() === qtext) : -1;
              rec = idx >= 0 ? askQueue.splice(idx, 1)[0] : (askQueue.length ? askQueue.shift() : null);
            }
            if (rec) p.append(markTs(opts.asks.buildAnsweredAskCard(rec), rec.ts));
          }
          toolBlocks[tc.id] = d;
        });
      } else if (m.role === 'tool') {
        const block = toolBlocks[m.tool_call_id];
        if (block) fillToolResult(block, m.content || '');
        else markTs(p.add('tool' + agentSide, '<pre>' + escapeHtml(m.content || '') + '</pre>'), m.ts);
      }
    }
    // Leftovers: their tool call is gone from the transcript, so they belong to
    // a turn older than anything on screen (legacy records carry no ts) — a
    // timestamped one (card asks) slots into the timeline like any other row.
    const leftover = [...askQueue, ...askByCall.values()];
    leftover.forEach(rec => {
      const node = markTs(opts.asks.buildAnsweredAskCard(rec), rec.ts);
      if (typeof rec.ts === 'number') insertByTs(p, node, rec.ts);
      else p.prepend(node);
    });
    // Last, over the finished pane: the phone turns absolute paths into taps
    // (opts.fileLink); a shell that passes none is left untouched (§52).
    linkifyPaths(p.el(), opts.fileLink);
  }

  /* In-flight turn tape (a comm clone's live events, friend view): merge
     adjacent text/reasoning deltas into runs so streaming reads as paragraphs
     instead of one row per fragment. */
  function renderLiveEvents(live, p, opts) {
    const agentSide = opts.side ? opts.side.agent : '';
    const runs = [];
    for (const ev of live || []) {
      const k = ev && ev.kind;
      if (k === 'reasoning_start') continue;
      const last = runs[runs.length - 1];
      if (k === 'reasoning_end') {
        // The session view collapses a reasoning block the moment its stream
        // ends and leaves only the one still being written open; the friend
        // view spectates the same turn, so it must read the same way
        // (2026-09-11 user report: the friend view only ever showed the
        // "Thinking…" line, expanded on a click).
        if (last && last.kind === 'reasoning') last.closed = true;
        continue;
      }
      if ((k === 'text' || k === 'reasoning') && last && last.kind === k) {
        last.text += liveEvText(ev);
        continue;
      }
      runs.push({ kind: k, text: liveEvText(ev), ev });
    }
    for (const r of runs) {
      if (r.kind === 'text') {
        const html = opts.liveText(r);
        if (html) p.add('friend-live' + agentSide, html);
      } else if (r.kind === 'reasoning') {
        const det = document.createElement('details');
        det.className = 'msg reasoning' + agentSide;
        det.open = !r.closed;   // still streaming: open, exactly like the session view
        det.innerHTML = '<summary>' + T('transcript.thinking') + '</summary>' + opts.reasoningHtml(r.text);
        p.append(det);
      } else if (r.kind === 'tool') {
        const c = (r.ev && r.ev.content) || {};
        p.add('tool' + agentSide, '<div class="tool-label">&#x1F527; ' + escapeHtml(c.name || 'tool')
          + (c.args ? ' <code style="font-size:0.82rem;opacity:0.7">' + escapeHtml(String(c.args).slice(0, 80)) + '</code>' : '') + '</div>');
      } else if (r.kind === 'tool_result') {
        const t = String(liveEvText(r.ev) || '');
        p.add('friend-live' + agentSide, '<pre>' + escapeHtml(t.slice(0, 400)) + (t.length > 400 ? '...' : '') + '</pre>');
      } else if (r.kind === 'status') {
        p.add('friend-event', '⏳ ' + escapeHtml(r.text || T('live.running')));
      } else if (r.kind === 'error') {
        p.add('friend-event', '⚠ ' + escapeHtml(r.text || T('live.error')));
      }
    }
  }
  function liveEvText(ev) {
    const c = ev && ev.content;
    if (typeof c === 'string') return c;
    if (c && typeof c === 'object') return c.text || c.content || c.name || '';
    return '';
  }

  /* ---------- output rate (tokens/s) ---------- */
  /* The readout left of the theme switch: how fast the model is writing right
     now. One streamed chunk is one output token — measured on this box against
     the provider's own usage (212 chunks vs completion_tokens 213), so counting
     chunks needs no tokenizer and no protocol change. `text` and `reasoning`
     both count: the model burns tokens either way (reasoning was 180 of those
     213), which is also why a reasoning-heavy turn does not read as 0. Tool-call
     argument tokens are NOT counted: the page never sees them — the server
     emits one `tool` event after the call is whole (spec §64).

     Life cycle (用户 2026-09-25 点名): 停笔时**数字留在屏幕上**（最后一次更新的速率），
     只有新建对话才收起来 —— 所以空闲只停表，不动 display；`clear()` 是那个唯一的清空点。 */
  const RATE_WINDOW_MS = 1500;   // the "一段时间" the rate averages over
  const RATE_IDLE_MS = 1000;     // silence this long: the count freezes as it is
  const RATE_TICK_MS = 150;
  const RATE_MIN_SPAN_MS = 250;  // shorter than this, a window cannot measure a rate

  function tokenRate(el) {
    if (!el) return { feed() {}, clear() {} };  // a stale cached page must not kill the stream
    let hits = [];  // streamed chunks inside the window (each one is an output token)
    let timer = null;
    function stop() {
      if (timer !== null) { clearInterval(timer); timer = null; }
      hits = [];  // a fresh burst starts its own window
    }
    function clear() {
      stop();
      el.classList.remove('on');
      el.textContent = '';
    }
    function paint() {
      const now = performance.now();
      hits = hits.filter(t => now - t <= RATE_WINDOW_MS);
      if (!hits.length || now - hits[hits.length - 1] > RATE_IDLE_MS) return stop();
      // 分母是**样本自身的跨度**（最后一个 chunk - 第一个），不是「最老样本到现在的年龄」：
      // 后者会把停笔之后的空档也算进去，数字越等越低 —— 那个数现在会停在屏幕上
      // （用户 2026-09-25 的规矩），所以必须是对的。
      const span = hits[hits.length - 1] - hits[0];
      // 样本太少的窗口量不出速率：**先留着上一个数**。没有一个「地板」的话，开口第一个 chunk
      // 会算成 3.3 tok/s 挂在屏上，看着就像掉坑（数字留住之后这条才变得看得见）。
      if (span < RATE_MIN_SPAN_MS) return;
      const rate = hits.length / (span / 1000);
      el.textContent = (rate >= 10 ? String(Math.round(rate)) : rate.toFixed(1)) + ' tok/s';
      el.classList.add('on');
    }
    return {
      /* Once per streamed chunk. The timer lives only while a burst does — a
         permanent interval in the header is what docs/webui-ux.md forbids. */
      feed() {
        hits.push(performance.now());
        if (timer === null) { timer = setInterval(paint, RATE_TICK_MS); paint(); }
      },
      clear,  // 新建对话：清空并收起来（唯一的清空点）
    };
  }

  /* ---------- header model picker (spec §66) ---------- */
  /* 用户 2026-09-25：「在左上角原来显示模型的位置也改成下拉列表」。原来那里只是**印着**
     当前模型（`#model-name`），现在是个自绘下拉列表，选中哪个就用哪个；列表就是设置页那个
     输入框往里加的那一份（config.json 的 `model_list`），两个界面因此不会各说各话。

     自绘而不是 `<select>`（同日用户报告：「风格和原来的不搭，没有动画效果」）：原生 select 的
     弹出层是系统画的，吃不到这套 token（`--surface/--radius/--shadow-card/--t-fast`），也没有
     开合过程——它跟旁边那些自绘控件（主题开关、折叠卡、抽屉）根本不是一种东西。现在触发器沿用
     原来那行文字的排版（mono、小字号、暗淡→悬停转亮），面板是本文件自己的浮层，开合交给
     `motion.js`（GSAP，reduced-motion 下模块折叠 → 瞬时开合，可见性仍由这里管）。

     切换 = 一次 POST + 一次极小的补全调用，回来的两件事**分开报**：状态行说一句话
     （那是条转瞬即逝的通道，下一轮对话就把它顶掉），触发器自己留一个颜色（ok/bad，
     `MODEL_NOTE_MS` 之后褪掉，title 里留着完整句子）—— 句子没了，那次测试的结果还在。 */
  const MODEL_NOTE_MS = 8000;

  function mountModelPicker(opts) {
    opts = opts || {};
    const trigger = document.getElementById(opts.id || 'model-select');
    const note = opts.note || function () {};
    const L = opts.labels || {};
    if (!trigger) return null;  // 旧缓存的页面：这里没有下拉列表，脚本其余部分照常活着

    /* 面板由这里建（两个壳共用同一份结构），触发器留在各自的 HTML 里：
       桌面在 #header，手机在顶栏，CSS 各管各的位置。 */
    const wrap = document.createElement('div');
    wrap.className = 'model-pick';
    trigger.parentNode.insertBefore(wrap, trigger);
    wrap.appendChild(trigger);
    trigger.classList.add('model-trigger');
    trigger.setAttribute('aria-haspopup', 'listbox');
    trigger.setAttribute('aria-expanded', 'false');
    const nameEl = document.createElement('span');
    nameEl.className = 'model-trigger-name';
    const caret = document.createElement('i');
    caret.className = 'model-caret';
    trigger.textContent = '';
    trigger.appendChild(nameEl);
    trigger.appendChild(caret);

    /* 面板挂在 `body` 上、用 fixed 定位（2026-09-25 实测）：留在触发器旁边会被祖先的
       `overflow:hidden` 裁掉——手机壳的 `#title-wrap{overflow:hidden}`（为了会话名的省略号）
       正好套在触发器外面，于是行都在、就是看不见，点也点不到。浮层自己按触发器的位置摆，
       滚动/改窗口尺寸时跟着走。 */
    const menu = document.createElement('div');
    menu.className = 'model-menu';
    menu.setAttribute('role', 'listbox');
    menu.hidden = true;
    document.body.appendChild(menu);

    let names = [], current = '', busy = false, fade = null, held = -1, isOpen = false, gen = 0;

    /* 这个名单可能跨厂商（spec §68）：切模型连端点一起换，所以报结果时把「落在哪台主机上」
       也说出来 —— 否则「调通了」看不出是发到哪家的地址上通的。密钥不上屏、也不进页面。 */
    function hostOf(url) {
      try { return new URL(url).host; } catch (e) { return ''; }
    }
    function sentence(d) {
      const on = d.endpoint ? ' @ ' + hostOf(d.endpoint) : '';
      if (d.reachable) {
        const served =
          d.detail && d.detail !== d.model ? ' (' + (L.served || T('model.servedAs')) + ' ' + d.detail + ')' : '';
        return '\u2713 ' + d.model + ' ' + (L.ok || T('model.answers')) + served + on;
      }
      return '\u2717 ' + d.model + ' ' + (L.bad || T('model.failed')) + ' \u2014 ' + (d.detail || '') + on;
    }

    function itemAt(i) {
      return menu.children[i] || null;
    }
    function hold(i) {
      const prev = itemAt(held);
      if (prev) prev.classList.remove('held');
      held = i;
      const now = itemAt(held);
      if (now) {
        now.classList.add('held');
        now.scrollIntoView({ block: 'nearest' });
      }
    }
    /* 正在用的那个：名字 + 一枚勾（不是只有颜色——色盲模式与打印都还得看得出） */
    function paint() {
      nameEl.textContent = current || '—';
      menu.innerHTML = names
        .map(
          m =>
            '<button type="button" role="option" class="model-item' +
            (m === current ? ' current' : '') +
            '" data-model="' + escapeHtml(m) + '" aria-selected="' + (m === current) + '">' +
            '<span class="model-item-name">' + escapeHtml(m) + '</span>' +
            '<span class="model-item-tick" aria-hidden="true">\u2713</span></button>'
        )
        .join('');
    }
    /* 贴着触发器下方，**左沿对齐**并夹在视口里：桌面上触发器偏左（Fungi 之后），手机上它在
       顶栏最左边 —— 按右沿对齐会让面板从触发器往左长，窄屏上直接长到屏幕外（实测第一版就是
       那样，左边几截字符被切掉）。放不下时整体左移，双留 8px 边距。 */
    function place() {
      const r = trigger.getBoundingClientRect();
      const width = menu.offsetWidth || 0;
      let left = r.left;
      if (width && left + width > window.innerWidth - 8) left = window.innerWidth - 8 - width;
      menu.style.left = Math.max(8, left) + 'px';
      menu.style.right = 'auto';
      menu.style.top = r.bottom + 6 + 'px';
    }
    function open() {
      if (isOpen) return;
      isOpen = true;
      gen += 1;
      place();
      menu.hidden = false;
      wrap.classList.add('open');
      trigger.setAttribute('aria-expanded', 'true');
      /* 关闭动画还在跑时又被点开：`overwrite:'auto'`（motion.js 里设的）会把那条 out 补间掐掉，
         它的 onComplete 不会跑 —— 所以「开着没」必须由 isOpen 说了算，不能看 `menu.hidden`
         （补间没结束时它还是 false，快速两下点击就会卡成「看起来开着其实已经收掉」）。 */
      window.potMotion?.menuIn?.(menu);
      window.addEventListener('scroll', place, true);
      window.addEventListener('resize', place);
      let i = names.indexOf(current);
      if (i < 0) i = 0;
      hold(i >= 0 && names.length ? i : -1);
    }
    function close() {
      if (!isOpen) return;
      isOpen = false;
      wrap.classList.remove('open');
      trigger.setAttribute('aria-expanded', 'false');
      window.removeEventListener('scroll', place, true);
      window.removeEventListener('resize', place);
      /* 迟到的收尾不许盖住刚打开的面板（实测栽过）：关闭补间的 onComplete 可能在重新打开之后
         才回来，那一下会把 `hidden` 又摁成 true —— 面板明明 `aria-expanded=true`，行却是
         `display:none`（Playwright 的报错正是 "element is not visible"）。代际号一比就知道
         这声收尾属不属于当前这一次。 */
      const mine = gen;
      const finish = () => {
        if (mine !== gen) return;
        menu.hidden = true;
        held = -1;
      };
      if (window.potMotion?.menuOut) window.potMotion.menuOut(menu, finish);
      else finish();
    }
    function flash(cls, text) {
      clearTimeout(fade);
      trigger.classList.remove('ok', 'bad', 'busy');
      trigger.classList.add(cls);
      trigger.title = text;
      fade = setTimeout(() => trigger.classList.remove('ok', 'bad'), MODEL_NOTE_MS);
    }
    async function load() {
      try {
        const d = await (await fetchJSON('/model')).json();
        setNames(d.models, d.model);
        return d;
      } catch (e) {
        return null;
      }
    }
    function setNames(models, cur) {
      names = (models || []).slice();
      if (cur && names.indexOf(cur) < 0) names.unshift(cur);
      current = cur || '';
      paint();
    }
    async function use(name) {
      if (busy || !name) return null;
      busy = true;
      flash('busy', name);
      note((L.switching || T('model.switching')) + ' ' + name + '\u2026');
      try {
        const d = await (await postJSON('/model', { model: name })).json();
        setNames(d.models, d.model);
        const said = sentence(d);
        flash(d.reachable ? 'ok' : 'bad', said);
        note(said);
        return d;
      } catch (e) {
        flash('bad', String(e));
        note((L.bad || 'failed') + ' \u2014 ' + e);
        return null;
      } finally {
        busy = false;
      }
    }

    trigger.addEventListener('click', e => {
      e.stopPropagation();
      if (isOpen) close();
      else open();
    });
    menu.addEventListener('click', e => {
      const row = e.target.closest ? e.target.closest('.model-item') : null;
      if (!row) return;
      e.stopPropagation();
      const name = row.dataset.model;
      close();
      use(name);
    });
    trigger.addEventListener('keydown', e => {
      if (e.key === 'ArrowDown' || e.key === 'ArrowUp' || e.key === 'Enter' || e.key === ' ') {
        if (!isOpen) { open(); e.preventDefault(); return; }
        if (e.key === 'ArrowDown') { hold(Math.min(held + 1, names.length - 1)); e.preventDefault(); }
        else if (e.key === 'ArrowUp') { hold(Math.max(held - 1, 0)); e.preventDefault(); }
        else if (e.key === 'Enter' || e.key === ' ') {
          const row = itemAt(held);
          if (row) { close(); use(row.dataset.model); }
          e.preventDefault();
        }
      } else if (e.key === 'Escape' && isOpen) {
        close();
        e.preventDefault();
      }
    });
    /* 点别处 / 按 Esc（焦点不在触发器上时）就收起来——面板是浮层，不是常驻侧栏。
       面板已经不在 wrap 里（挂在 body 上），所以「里面」要连它一起算。 */
    document.addEventListener('click', e => {
      if (isOpen && !wrap.contains(e.target) && !menu.contains(e.target)) close();
    });
    document.addEventListener('keydown', e => {
      if (e.key === 'Escape' && isOpen) close();
    });
    load();
    return { load, use };
  }

  window.PotCommon = {
    initHttp, url, fetchJSON, postJSON,
    escapeHtml, fmtDate, getSessionTitle,
    initConfirmModal, showConfirm, closeConfirm,
    buildToolCard, fillToolResult, attachSpawnClick,
    initAsks, initPendingAsks, initSessionAlerts, tokenRate,
    mountModelPicker,
    initPane, stripSilent, silentText, isSilentOnly, humanEcho,
    markTs, insertByTs, askTextOfCall, linkifyPaths, buildFileCard, humanBytes,
    renderTranscript, renderLiveEvents, whenLabel,
  };
})();
