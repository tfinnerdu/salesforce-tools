/* Help & User Guide — sidebar nav highlighting + in-page search.
 * Content is server-rendered from docs/user-guide.md (routes/help.py); this
 * only adds client-side findability on top of it.
 */
(() => {
  const content = document.getElementById('helpContent');
  const nav = document.getElementById('helpNav');
  const searchInput = document.getElementById('helpSearchInput');
  const searchCount = document.getElementById('helpSearchCount');
  if (!content || !nav) return;

  const navLinks = Array.from(nav.querySelectorAll('a[href^="#"]'));
  const navItems = Array.from(nav.querySelectorAll('li'));
  const headings = Array.from(content.querySelectorAll('h2[id], h3[id], h4[id]'));

  // ── Active-section highlighting while scrolling ──────────────────────────
  const linkForId = new Map(navLinks.map(a => [a.getAttribute('href').slice(1), a]));

  const setActive = (id) => {
    navLinks.forEach(a => a.classList.remove('mc-help-nav-active'));
    const link = linkForId.get(id);
    if (link) link.classList.add('mc-help-nav-active');
  };

  if ('IntersectionObserver' in window && headings.length) {
    const observer = new IntersectionObserver((entries) => {
      const visible = entries.filter(e => e.isIntersecting)
        .sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top);
      if (visible.length) setActive(visible[0].target.id);
    }, { rootMargin: '0px 0px -70% 0px', threshold: 0 });
    headings.forEach(h => observer.observe(h));
  }

  // ── Search: filters the sidebar to matching sections, highlights + jumps
  //    to the first match in the content. A "section" is a heading plus
  //    every element up to (not including) the next heading of equal-or-
  //    higher level, so a match in body text still surfaces its heading.
  const sections = headings.map((h, i) => {
    const level = parseInt(h.tagName.slice(1), 10);
    const els = [h];
    let sib = h.nextElementSibling;
    while (sib) {
      const m = sib.tagName.match(/^H([1-6])$/);
      if (m && parseInt(m[1], 10) <= level) break;
      els.push(sib);
      sib = sib.nextElementSibling;
    }
    return { id: h.id, els, text: els.map(e => e.textContent).join(' ').toLowerCase() };
  });

  let marks = [];
  const clearMarks = () => {
    marks.forEach(m => {
      const parent = m.parentNode;
      if (!parent) return;
      parent.replaceChild(document.createTextNode(m.textContent), m);
      parent.normalize();
    });
    marks = [];
  };

  const highlightInSection = (section, term) => {
    const re = new RegExp(term.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'ig');
    section.els.forEach(el => {
      const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT, null);
      const textNodes = [];
      let n;
      while ((n = walker.nextNode())) textNodes.push(n);
      textNodes.forEach(node => {
        if (!re.test(node.textContent)) return;
        re.lastIndex = 0;
        const frag = document.createDocumentFragment();
        let lastIndex = 0;
        let match;
        while ((match = re.exec(node.textContent))) {
          frag.appendChild(document.createTextNode(node.textContent.slice(lastIndex, match.index)));
          const mark = document.createElement('mark');
          mark.textContent = match[0];
          frag.appendChild(mark);
          marks.push(mark);
          lastIndex = match.index + match[0].length;
        }
        frag.appendChild(document.createTextNode(node.textContent.slice(lastIndex)));
        node.parentNode.replaceChild(frag, node);
      });
    });
  };

  const runSearch = (rawTerm) => {
    const term = rawTerm.trim().toLowerCase();
    clearMarks();

    if (!term) {
      navItems.forEach(li => li.classList.remove('mc-help-nav-hidden'));
      if (searchCount) searchCount.textContent = '';
      return;
    }

    const matchedIds = new Set();
    sections.forEach(section => {
      if (section.text.includes(term)) {
        matchedIds.add(section.id);
        highlightInSection(section, term);
      }
    });

    // A parent tab (h2) stays visible if any of its features (h3/h4) match.
    navItems.forEach(li => {
      const link = li.querySelector(':scope > a');
      const id = link ? link.getAttribute('href').slice(1) : null;
      const descendantMatch = Array.from(li.querySelectorAll('li[data-search-text]'))
        .some(child => matchedIds.has((child.querySelector(':scope > a') || {}).getAttribute?.('href')?.slice(1)));
      const selfMatch = id && matchedIds.has(id);
      li.classList.toggle('mc-help-nav-hidden', !selfMatch && !descendantMatch);
    });

    if (searchCount) {
      const n = marks.length;
      searchCount.textContent = n ? `${n} match${n === 1 ? '' : 'es'} in ${matchedIds.size} section${matchedIds.size === 1 ? '' : 's'}` : 'No matches';
      if (!n) searchCount.classList.add('mc-help-no-results'); else searchCount.classList.remove('mc-help-no-results');
    }

    if (marks.length) {
      marks[0].scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
  };

  if (searchInput) {
    let debounceTimer;
    searchInput.addEventListener('input', (e) => {
      clearTimeout(debounceTimer);
      const value = e.target.value;
      debounceTimer = setTimeout(() => runSearch(value), 200);
    });
  }
})();
