/**
 * Central Data Agency — Entity Registry Browser
 * Fetches static JSON API, renders filterable/searchable entry cards.
 *
 * API base path is read from:
 *   1. window.CDA_API_BASE (set this before the script loads for overrides)
 *   2. data-api-base attribute on <html>
 *   3. Falls back to '/api'
 */

(function () {
  'use strict';

  // ── Config ────────────────────────────────────────────────────────────────

  const API_BASE =
    window.CDA_API_BASE ||
    document.documentElement.dataset.apiBase ||
    '/api';

  // ── State ─────────────────────────────────────────────────────────────────

  const state = {
    entries: [],          // { official, abbreviation, description, tags, variants, _collection }
    collections: [],      // [{ name, label, count }]
    allTags: [],          // sorted unique tag strings
    activeCollection: '', // '' = all
    activeTags: new Set(),
    query: '',
  };

  // ── DOM refs ──────────────────────────────────────────────────────────────

  const $ = id => document.getElementById(id);
  const el = {
    status:     $('header-status'),
    search:     $('search'),
    collList:   $('collection-list'),
    tagList:    $('tag-list'),
    main:       $('main'),
    resultCount:$('result-count'),
    toolbarHint:$('toolbar-hint'),
    clearBtn:   $('clear-filters'),
  };

  // ── Fetch helpers ─────────────────────────────────────────────────────────

  async function fetchJSON(url) {
    const res = await fetch(url);
    if (!res.ok) throw new Error(`HTTP ${res.status} — ${url}`);
    return res.json();
  }

  // ── Bootstrap ─────────────────────────────────────────────────────────────

  async function init() {
    try {
      setStatus('LOADING…');

      const index = await fetchJSON(`${API_BASE}/index.json`);
      // index.json: { collections: [{ name, label }] }  OR  string[]
      const collDefs = Array.isArray(index)
        ? index.map(name => ({ name, label: labelFromName(name) }))
        : (index.collections || []);

      if (collDefs.length === 0) throw new Error('No collections in index.json');

      const results = await Promise.allSettled(
        collDefs.map(c => fetchJSON(`${API_BASE}/${c.name}.json`).then(data => ({ ...c, data })))
      );

      const tagSet = new Set();

      results.forEach(r => {
        if (r.status === 'rejected') {
          console.warn('Failed to load collection:', r.reason);
          return;
        }
        const { name, label, data } = r.value;
        const entries = Array.isArray(data) ? data : (data.entries || []);
        entries.forEach(e => {
          state.entries.push({ ...e, _collection: name, _collectionLabel: label });
          (e.tags || []).forEach(t => tagSet.add(t));
        });
        state.collections.push({ name, label, count: entries.length });
      });

      state.allTags = [...tagSet].sort();

      renderSidebar();
      renderResults();
      setStatus('READY', 'ready');
    } catch (err) {
      console.error(err);
      setStatus('ERROR', 'error');
      showError(err.message);
    }
  }

  function labelFromName(name) {
    return name.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
  }

  // ── Sidebar ───────────────────────────────────────────────────────────────

  function renderSidebar() {
    // Collections
    el.collList.innerHTML = '';
    const allBtn = makeCollBtn('', 'All Collections', state.entries.length);
    el.collList.appendChild(allBtn);
    state.collections.forEach(c => {
      el.collList.appendChild(makeCollBtn(c.name, c.label, c.count));
    });

    // Tags
    el.tagList.innerHTML = '';
    state.allTags.forEach(tag => {
      const btn = document.createElement('button');
      btn.className = 'tag-btn';
      btn.textContent = tag;
      btn.dataset.tag = tag;
      btn.setAttribute('role', 'option');
      btn.setAttribute('aria-selected', 'false');
      btn.addEventListener('click', () => toggleTag(tag));
      el.tagList.appendChild(btn);
    });
  }

  function makeCollBtn(name, label, count) {
    const li = document.createElement('li');
    const btn = document.createElement('button');
    btn.className = 'coll-btn' + (state.activeCollection === name ? ' active' : '');
    btn.dataset.coll = name;
    btn.setAttribute('role', 'option');
    btn.setAttribute('aria-selected', String(state.activeCollection === name));
    btn.innerHTML = `<span>${escHtml(label)}</span><span class="coll-count">${count}</span>`;
    btn.addEventListener('click', () => setCollection(name));
    li.appendChild(btn);
    return li;
  }

  // ── Filter actions ────────────────────────────────────────────────────────

  function setCollection(name) {
    state.activeCollection = name;
    document.querySelectorAll('.coll-btn').forEach(b => {
      const active = b.dataset.coll === name;
      b.classList.toggle('active', active);
      b.setAttribute('aria-selected', String(active));
    });
    renderResults();
  }

  function toggleTag(tag) {
    if (state.activeTags.has(tag)) {
      state.activeTags.delete(tag);
    } else {
      state.activeTags.add(tag);
    }
    document.querySelectorAll('.tag-btn').forEach(b => {
      const active = state.activeTags.has(b.dataset.tag);
      b.classList.toggle('active', active);
      b.setAttribute('aria-selected', String(active));
    });
    renderResults();
  }

  function clearFilters() {
    state.activeCollection = '';
    state.activeTags.clear();
    state.query = '';
    el.search.value = '';
    document.querySelectorAll('.coll-btn').forEach(b => {
      const active = b.dataset.coll === '';
      b.classList.toggle('active', active);
      b.setAttribute('aria-selected', String(active));
    });
    document.querySelectorAll('.tag-btn').forEach(b => {
      b.classList.remove('active');
      b.setAttribute('aria-selected', 'false');
    });
    renderResults();
  }

  // ── Search ────────────────────────────────────────────────────────────────

  let searchTimer;
  el.search.addEventListener('input', () => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => {
      state.query = el.search.value.trim().toLowerCase();
      renderResults();
    }, 120);
  });

  el.clearBtn.addEventListener('click', clearFilters);

  // ── Filter + render ───────────────────────────────────────────────────────

  function getFiltered() {
    const q = state.query;
    return state.entries.filter(e => {
      // Collection filter
      if (state.activeCollection && e._collection !== state.activeCollection) return false;
      // Tag filter (all active tags must be present)
      if (state.activeTags.size > 0) {
        const entryTags = new Set(e.tags || []);
        for (const t of state.activeTags) {
          if (!entryTags.has(t)) return false;
        }
      }
      // Text search
      if (q) {
        const haystack = [
          e.official,
          e.abbreviation,
          e.description,
          ...(e.variants || []),
        ].filter(Boolean).join(' ').toLowerCase();
        if (!haystack.includes(q)) return false;
      }
      return true;
    });
  }

  function renderResults() {
    const filtered = getFiltered();
    const hasFilters = state.activeCollection || state.activeTags.size > 0 || state.query;

    // Toolbar
    el.resultCount.innerHTML = `<span>${filtered.length}</span> of ${state.entries.length} entries`;
    el.toolbarHint.textContent = hasFilters ? 'matching current filters' : 'total entries';
    el.clearBtn.classList.toggle('hidden', !hasFilters);

    // Highlight active card tags
    document.querySelectorAll('.card-tag').forEach(t => {
      t.classList.toggle('active', state.activeTags.has(t.dataset.tag));
    });

    if (filtered.length === 0) {
      el.main.innerHTML = '';
      el.main.appendChild(makeEmptyScreen(hasFilters));
      return;
    }

    el.main.innerHTML = '';
    const grid = document.createElement('div');
    grid.id = 'entries-grid';

    filtered.forEach((entry, i) => {
      const card = makeCard(entry, state.query);
      card.style.animationDelay = `${Math.min(i * 18, 300)}ms`;
      grid.appendChild(card);
    });

    el.main.appendChild(grid);
  }

  // ── Card builder ──────────────────────────────────────────────────────────

  function makeCard(entry, q) {
    const card = document.createElement('article');
    card.className = 'entry-card';

    // Header: official + abbreviation
    const header = document.createElement('div');
    header.className = 'card-header';
    const official = document.createElement('div');
    official.className = 'card-official';
    official.innerHTML = highlight(entry.official, q);
    header.appendChild(official);
    if (entry.abbreviation) {
      const abbr = document.createElement('span');
      abbr.className = 'card-abbr';
      abbr.innerHTML = highlight(entry.abbreviation, q);
      abbr.title = 'Abbreviation';
      header.appendChild(abbr);
    }
    card.appendChild(header);

    // Collection label
    if (state.activeCollection === '') {
      const collLabel = document.createElement('div');
      collLabel.className = 'card-collection';
      collLabel.textContent = entry._collectionLabel;
      card.appendChild(collLabel);
    }

    // Description
    if (entry.description) {
      const desc = document.createElement('div');
      desc.className = 'card-description';
      desc.innerHTML = highlight(entry.description, q);
      card.appendChild(desc);
    }

    // Tags
    if (entry.tags && entry.tags.length > 0) {
      const tagsDiv = document.createElement('div');
      tagsDiv.className = 'card-tags';
      entry.tags.forEach(tag => {
        const t = document.createElement('button');
        t.className = 'card-tag' + (state.activeTags.has(tag) ? ' active' : '');
        t.textContent = tag;
        t.dataset.tag = tag;
        t.setAttribute('aria-label', `Filter by tag: ${tag}`);
        t.addEventListener('click', () => toggleTag(tag));
        tagsDiv.appendChild(t);
      });
      card.appendChild(tagsDiv);
    }

    // Variants
    if (entry.variants && entry.variants.length > 0) {
      const varDiv = document.createElement('div');
      varDiv.className = 'card-variants';

      const toggle = document.createElement('button');
      toggle.className = 'variants-toggle';
      toggle.innerHTML = `<span class="toggle-arrow">▶</span> ${entry.variants.length} variant${entry.variants.length > 1 ? 's' : ''}`;
      toggle.setAttribute('aria-expanded', 'false');

      const list = document.createElement('div');
      list.className = 'variants-list';
      entry.variants.forEach(v => {
        const chip = document.createElement('span');
        chip.className = 'variant-chip';
        chip.innerHTML = highlight(v, q);
        list.appendChild(chip);
      });

      toggle.addEventListener('click', () => {
        const open = list.classList.toggle('open');
        toggle.classList.toggle('open', open);
        toggle.setAttribute('aria-expanded', String(open));
      });

      // Auto-open if a query matched a variant
      if (q && entry.variants.some(v => v.toLowerCase().includes(q))) {
        list.classList.add('open');
        toggle.classList.add('open');
        toggle.setAttribute('aria-expanded', 'true');
      }

      varDiv.appendChild(toggle);
      varDiv.appendChild(list);
      card.appendChild(varDiv);
    }

    return card;
  }

  // ── Empty / Error screens ─────────────────────────────────────────────────

  function makeEmptyScreen(hasFilters) {
    const div = document.createElement('div');
    div.className = 'state-screen';
    div.innerHTML = hasFilters
      ? `<div class="state-icon">◌</div>
         <div class="state-title">No matches found</div>
         <div>Try adjusting your search or filters</div>`
      : `<div class="state-icon">◌</div>
         <div class="state-title">Registry is empty</div>`;
    return div;
  }

  function showError(msg) {
    el.main.innerHTML = `
      <div class="state-screen error">
        <div class="state-icon">⊗</div>
        <div class="state-title">Failed to load registry</div>
        <div>${escHtml(msg)}</div>
      </div>`;
    el.resultCount.textContent = '—';
  }

  function setStatus(text, cls = '') {
    el.status.textContent = text;
    el.status.className = cls ? `ready ${cls}` : '';
    el.status.className = cls;
  }

  // ── Utilities ─────────────────────────────────────────────────────────────

  function escHtml(str) {
    return String(str ?? '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function highlight(text, q) {
    const safe = escHtml(text);
    if (!q) return safe;
    const re = new RegExp(`(${q.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')})`, 'gi');
    return safe.replace(re, '<mark>$1</mark>');
  }

  // ── Go ────────────────────────────────────────────────────────────────────

  init();
})();
