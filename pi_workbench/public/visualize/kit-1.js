/* Pi visualization kit 1.0.0. Project-authored local display behavior. */
(() => {
  'use strict';
  const initializedTabs = new WeakSet();
  const initializedTooltips = new WeakSet();
  let sequence = 0;
  function initTabs(root) {
    for (const group of root.querySelectorAll('[data-viz-tabs]')) {
      if (initializedTabs.has(group)) continue;
      const list = group.querySelector('[role="tablist"]');
      const tabs = [...(list?.querySelectorAll('button[role="tab"]') || [])];
      const panels = tabs.map(tab => document.getElementById(tab.getAttribute('aria-controls')));
      if (!tabs.length || panels.some(panel => !panel || !group.contains(panel))) throw new Error('Tabs need local labelled panels.');
      const available = tabs.filter(tab => !tab.disabled);
      if (!available.length) throw new Error('Tabs need an enabled tab.');
      const select = tab => {
        tabs.forEach((item, index) => {
          const active = item === tab;
          item.id ||= 'pv-tab-' + (++sequence);
          item.type = 'button'; item.setAttribute('aria-selected', String(active)); item.tabIndex = active ? 0 : -1;
          panels[index].hidden = !active;
          panels[index].setAttribute('role', 'tabpanel'); panels[index].setAttribute('aria-labelledby', item.id);
        });
      };
      select(available.find(tab => tab.getAttribute('aria-selected') === 'true') || available[0]);
      list.addEventListener('click', event => {
        const tab = event.target.closest('button[role="tab"]');
        if (available.includes(tab)) select(tab);
      });
      list.addEventListener('keydown', event => {
        const current = available.indexOf(document.activeElement);
        const origin = current < 0 ? available.indexOf(event.target) : current;
        if (origin < 0) return;
        const vertical = list.getAttribute('aria-orientation') === 'vertical';
        let next;
        if (event.key === 'Home') next = 0;
        else if (event.key === 'End') next = available.length - 1;
        else if (event.key === (vertical ? 'ArrowDown' : 'ArrowRight')) next = (origin + 1) % available.length;
        else if (event.key === (vertical ? 'ArrowUp' : 'ArrowLeft')) next = (origin - 1 + available.length) % available.length;
        else return;
        event.preventDefault(); select(available[next]); available[next].focus();
      });
      initializedTabs.add(group);
    }
  }
  function initTooltips(root) {
    for (const trigger of root.querySelectorAll('[data-viz-tooltip]')) {
      if (initializedTooltips.has(trigger)) continue;
      const tooltip = document.createElement('div');
      tooltip.id = 'pv-tooltip-' + (++sequence); tooltip.className = 'viz-tooltip';
      tooltip.setAttribute('role', 'tooltip'); tooltip.hidden = true;
      tooltip.textContent = trigger.getAttribute('data-viz-tooltip').slice(0, 500);
      document.body.append(tooltip);
      trigger.setAttribute('aria-describedby', [trigger.getAttribute('aria-describedby'), tooltip.id].filter(Boolean).join(' '));
      const hide = () => { tooltip.hidden = true; };
      const show = () => {
        tooltip.hidden = false;
        const rect = trigger.getBoundingClientRect(), box = tooltip.getBoundingClientRect();
        const left = Math.max(8, Math.min(innerWidth - box.width - 8, rect.left + rect.width / 2 - box.width / 2));
        const top = rect.top >= box.height + 16 ? rect.top - box.height - 8 : Math.min(innerHeight - box.height - 8, rect.bottom + 8);
        tooltip.style.left = left + 'px'; tooltip.style.top = Math.max(8, top) + 'px';
      };
      trigger.addEventListener('focus', show); trigger.addEventListener('blur', hide);
      trigger.addEventListener('mouseenter', show); trigger.addEventListener('mouseleave', hide);
      trigger.addEventListener('pointerdown', event => { if (event.pointerType === 'touch') tooltip.hidden ? show() : hide(); });
      trigger.addEventListener('keydown', event => { if (event.key === 'Escape') { hide(); event.preventDefault(); } });
      document.addEventListener('pointerdown', event => { if (!trigger.contains(event.target)) hide(); });
      addEventListener('scroll', hide, true); addEventListener('resize', hide);
      initializedTooltips.add(trigger);
    }
  }
  const properties = { background: 'bg', text: 'text', surface: 'surface', raised: 'raised', muted: 'muted', border: 'border', primary: 'primary', onPrimary: 'on-primary', input: 'input', focus: 'focus', danger: 'danger', series1: 'series-1', series2: 'series-2', series3: 'series-3', series4: 'series-4', series5: 'series-5', series6: 'series-6' };
  function getTheme() {
    const style = getComputedStyle(document.documentElement);
    return Object.freeze({ mode: document.documentElement.dataset.theme || 'dark', colors: Object.freeze(Object.fromEntries(Object.entries(properties).map(([key, name]) => [key, style.getPropertyValue('--viz-' + name).trim()]))) });
  }
  function initIcons(root = document) {
    if (root.querySelector('[data-lucide]')) {
      if (!window.lucide) throw new Error('Declare the local lucide library before using icons.');
      window.lucide.createIcons({ root, attrs: { 'aria-hidden': 'true', focusable: 'false' } });
    }
  }
  window.PiViz = Object.freeze({ version: '1.0.0', getTheme, initIcons,
    get reducedMotion() { return matchMedia('(prefers-reduced-motion: reduce)').matches; },
    init(root = document) { initTabs(root); initTooltips(root); initIcons(root); }
  });
})();
