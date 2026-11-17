// A small stand-in for the part of the DOM the page script uses, so that the page can be
// drawn under Node without a browser or a package. Elements hold children, attributes and
// listeners; text nodes hold text. `page(data, breakdowns)` builds the elements of body.html
// that carry `data-sd`, runs diagnostics.js against them and returns what it drew.
'use strict';

const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const PAGE = path.join(__dirname, '..', '..', 'src', 'sentier_diagnostics', 'page');

// the selectors the script asks for: [attr], [attr="value"], tag[attr], tag[attr="value"]
function matches(node, selector) {
  const one = /^([a-z0-9]*)\[([a-z-]+)(?:="([^"]*)")?\]$/.exec(selector);
  if (!one) throw new Error('the stand-in does not know the selector ' + selector);
  const [, tag, key, value] = one;
  if (node.text !== undefined) return false;
  if (tag && node.tagName !== tag.toUpperCase()) return false;
  if (!(key in node.attributes)) return false;
  return value === undefined || node.attributes[key] === value;
}

class FakeNode {
  constructor(tag, text) {
    this.tagName = tag ? tag.toUpperCase() : null;
    this.text = text; // a text node holds this; an element has none
    this.childNodes = [];
    this.parentNode = null;
    this.attributes = {};
    this.listeners = {};
    this.hidden = false;
    this.className = '';
    this.value = '';
    this.disabled = false;
    this.focused = false;
    // the inline style, as the CSSOM sets it: by property
    const values = {};
    this.style = { setProperty: (name, value) => { values[name] = String(value); }, getPropertyValue: (name) => values[name] || '' };
  }

  get firstChild() { return this.childNodes[0] || null; }

  appendChild(child) {
    if (child.parentNode) child.parentNode.removeChild(child);
    child.parentNode = this;
    this.childNodes.push(child);
    return child;
  }

  removeChild(child) {
    const at = this.childNodes.indexOf(child);
    if (at < 0) throw new Error('not a child of this node');
    this.childNodes.splice(at, 1);
    child.parentNode = null;
    return child;
  }

  get textContent() {
    return this.text !== undefined ? this.text : this.childNodes.map((c) => c.textContent).join('');
  }

  set textContent(value) {
    if (this.text !== undefined) { this.text = String(value); return; }
    this.childNodes.forEach((c) => { c.parentNode = null; });
    this.childNodes = [];
    if (value !== '' && value !== null && value !== undefined) this.appendChild(new FakeNode(null, String(value)));
  }

  setAttribute(key, value) {
    this.attributes[key] = String(value);
    if (key === 'value') this.value = String(value);
  }

  getAttribute(key) { return key in this.attributes ? this.attributes[key] : null; }

  removeAttribute(key) { delete this.attributes[key]; }

  addEventListener(type, listener) { (this.listeners[type] = this.listeners[type] || []).push(listener); }

  removeEventListener(type, listener) {
    const held = this.listeners[type] || [];
    if (held.indexOf(listener) >= 0) held.splice(held.indexOf(listener), 1);
  }

  // an event on this node, passed up to its parents as a browser does
  dispatch(type, event) {
    const full = { target: this, ...event };
    for (let node = this; node; node = node.parentNode) (node.listeners[type] || []).forEach((listener) => listener(full));
  }

  closest(selector) {
    for (let node = this; node; node = node.parentNode) if (matches(node, selector)) return node;
    return null;
  }

  querySelectorAll(selector) { return this.all().slice(1).filter((n) => matches(n, selector)); }

  querySelector(selector) { return this.querySelectorAll(selector)[0] || null; }

  contains(other) { for (let n = other; n; n = n.parentNode) if (n === this) return true; return false; }

  focus(options) { this.focused = true; this.focusOptions = options; }

  scrollIntoView() {}

  // every text a reader sees: text nodes and tooltips, in order; nothing under a hidden node
  seen() {
    if (this.text !== undefined) return [this.text];
    if (this.hidden) return [];
    const own = this.attributes.title ? [this.attributes.title] : [];
    return own.concat(...this.childNodes.map((c) => c.seen()));
  }

  // every element below this one, this one first
  all() { return this.text !== undefined ? [] : [this].concat(...this.childNodes.map((c) => c.all())); }
}

// the root of body.html and every element in it that carries `data-sd` or `data-sd-word`, each a child of the
// root; the data scripts as the Python writes them where `scripts` holds them
function body(scripts) {
  const html = fs.readFileSync(path.join(PAGE, 'body.html'), 'utf8');
  const root = new FakeNode('div');
  root.setAttribute('class', 'sentier-diagnostics');
  root.setAttribute('data-sentier-diagnostics', '');
  for (const [whole, tag] of html.matchAll(/<([a-z0-9]+)\b[^>]*>/g)) {
    const word = /\sdata-sd-word="([^"]+)"/.exec(whole);
    if (word) { const span = new FakeNode(tag); span.setAttribute('data-sd-word', word[1]); root.appendChild(span); continue; }
    const name = /\sdata-sd="([^"]+)"/.exec(whole);
    if (!name) continue;
    const node = new FakeNode(tag);
    node.setAttribute('data-sd', name[1]);
    node.hidden = /\shidden[\s>=]/.test(whole);
    root.appendChild(node);
  }
  for (const [name, value] of Object.entries(scripts || {})) {
    const node = new FakeNode('script');
    node.setAttribute('type', 'application/json');
    node.setAttribute('data-sd', name);
    node.textContent = JSON.stringify(value);
    root.appendChild(node);
  }
  return root;
}

// `options`: {standalone, attributes, globals, fetch, protocol, scripts, hash, historyState}
function page(data, breakdowns, options) {
  options = options || {};
  const scripts = options.scripts || {};
  if (data !== undefined && !options.globals) scripts.data = data;
  if (breakdowns && !options.globals) scripts.breakdowns = breakdowns;
  const root = body(scripts);
  if (options.standalone) root.setAttribute('data-sd-standalone', '');
  for (const [key, value] of Object.entries(options.attributes || {})) root.setAttribute(key, value);
  const head = new FakeNode('head');
  const listeners = {};
  const documentListeners = {}; // by type: [listener, capture]
  const document = {
    title: '',
    readyState: 'complete',
    head,
    activeElement: null,
    createElement: (tag) => new FakeNode(tag),
    createTextNode: (text) => new FakeNode(null, String(text)),
    querySelectorAll: (selector) => (matches(root, selector) ? [root] : []),
    addEventListener: (type, listener, capture) => { (documentListeners[type] = documentListeners[type] || []).push([listener, !!capture]); },
    removeEventListener: (type, listener, capture) => {
      const held = documentListeners[type] || [];
      const at = held.findIndex(([l, c]) => l === listener && c === !!capture);
      if (at >= 0) held.splice(at, 1);
    },
  };
  root.ownerDocument = document;
  const context = {
    document,
    location: { hash: options.hash ? '#' + options.hash : '', search: '', pathname: '/index.html', protocol: options.protocol || 'file:' },
    // replaceState drops the "#"; each call is kept, with the state it was given
    history: {
      state: options.historyState === undefined ? null : options.historyState,
      replaced: [],
      replaceState: (state, title, url) => { context.history.replaced.push({ state, url }); context.history.state = state; context.location.hash = ''; },
    },
    addEventListener: (type, listener) => { (listeners[type] = listeners[type] || []).push(listener); },
    removeEventListener: (type, listener) => { const held = listeners[type] || []; if (held.indexOf(listener) >= 0) held.splice(held.indexOf(listener), 1); },
    URLSearchParams,
    WeakRef, // as a browser has it; a test takes it away to see the page without it
    TextDecoder,
    FileReader: class {},
    fetch: options.fetch || (() => Promise.reject(new Error('no network'))),
    ...(options.globals || {}),
  };
  if (options.globals && data !== undefined) context.SENTIER_DIAGNOSTICS = data;
  if (options.globals && breakdowns) context.SENTIER_DIAGNOSTICS_BREAKDOWNS = breakdowns;
  context.window = context;
  vm.createContext(context);
  vm.runInContext(fs.readFileSync(path.join(PAGE, 'diagnostics.js'), 'utf8'), context, { filename: 'diagnostics.js' });
  const byName = {};
  root.childNodes.forEach((n) => { if (n.getAttribute('data-sd')) byName[n.getAttribute('data-sd')] = n; });
  return {
    root,
    byId: byName, // by the name in data-sd
    head,
    document,
    context,
    // the text of everything drawn and not hidden, tooltips included
    text: () => root.childNodes.filter((n) => !n.hidden && n.tagName !== 'SCRIPT').map((n) => n.seen().join(' ')).join('\n'),
    open: (hash) => {
      context.location.hash = '#' + hash;
      (listeners.hashchange || []).slice().forEach((listener) => listener({}));
    },
    // the hashchange a browser fires after the page itself wrote the hash
    changed: () => (listeners.hashchange || []).slice().forEach((listener) => listener({})),
    listeners,
    documentListeners,
  };
}

module.exports = { FakeNode, page, body };
