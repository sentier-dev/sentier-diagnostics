// A small stand-in for the part of the DOM the page script uses, so that the page can be
// drawn under Node without a browser or a package. Elements hold children, attributes and
// listeners; text nodes hold text. `page(data, breakdowns)` runs diagnostics.js against
// the ids of index.html and returns what it drew.
'use strict';

const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const PAGE = path.join(__dirname, '..', '..', 'src', 'sentier_diagnostics', 'page');

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
    this.onclick = null;
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

  addEventListener(type, listener) { (this.listeners[type] = this.listeners[type] || []).push(listener); }

  dispatch(type, event) { (this.listeners[type] || []).forEach((listener) => listener({ target: this, ...event })); }

  closest(selector) {
    if (selector !== 'tr[data-item]') throw new Error('the stand-in knows tr[data-item] only');
    for (let node = this; node; node = node.parentNode) {
      if (node.tagName === 'TR' && node.getAttribute('data-item') !== null) return node;
    }
    return null;
  }

  scrollIntoView() {}

  // every text a reader sees: text nodes and tooltips, in order
  seen() {
    if (this.text !== undefined) return [this.text];
    const own = this.attributes.title ? [this.attributes.title] : [];
    return own.concat(...this.childNodes.map((c) => c.seen()));
  }

  // every element below this one, this one first
  all() { return this.text !== undefined ? [] : [this].concat(...this.childNodes.map((c) => c.all())); }
}

function page(data, breakdowns) {
  const html = fs.readFileSync(path.join(PAGE, 'index.html'), 'utf8');
  const byId = {};
  for (const [whole, tag] of html.matchAll(/<([a-z0-9]+)\b[^>]*>/g)) {
    const id = /\sid="([^"]+)"/.exec(whole);
    if (!id) continue;
    byId[id[1]] = new FakeNode(tag);
    byId[id[1]].attributes.id = id[1];
    byId[id[1]].hidden = /\shidden[\s>=]/.test(whole);
  }
  const listeners = {};
  const document = {
    title: '',
    readyState: 'complete',
    createElement: (tag) => new FakeNode(tag),
    createTextNode: (text) => new FakeNode(null, String(text)),
    getElementById: (id) => byId[id] || null,
    addEventListener: () => {},
  };
  const context = {
    document,
    location: { hash: '', search: '', pathname: '/index.html', protocol: 'file:' },
    history: { replaceState: () => {} },
    addEventListener: (type, listener) => { (listeners[type] = listeners[type] || []).push(listener); },
    URLSearchParams,
    FileReader: class {},
    fetch: () => Promise.reject(new Error('no network')),
    SENTIER_DIAGNOSTICS: data,
    SENTIER_DIAGNOSTICS_BREAKDOWNS: breakdowns || {},
  };
  context.window = context;
  vm.createContext(context);
  vm.runInContext(fs.readFileSync(path.join(PAGE, 'diagnostics.js'), 'utf8'), context, { filename: 'diagnostics.js' });
  return {
    byId,
    document,
    // the text of everything drawn, tooltips included
    text: () => Object.values(byId).filter((n) => !n.hidden).map((n) => n.seen().join(' ')).join('\n'),
    open: (hash) => {
      context.location.hash = '#' + hash;
      (listeners.hashchange || []).forEach((listener) => listener({}));
    },
  };
}

module.exports = { FakeNode, page };
