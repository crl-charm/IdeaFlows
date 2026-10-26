"""Exercise the public page controller without adding a browser test dependency."""

import json
from pathlib import Path
import shutil
import subprocess

import pytest

from app import create_app


@pytest.fixture
def app():
    application = create_app()
    application.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    return application


def test_public_controller_refresh_recovery_search_and_read_only_rendering(app):
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is needed to exercise the public browser controller")
    source = (Path(__file__).resolve().parents[1] / "static/js/current-customers.js").read_text(encoding="utf-8")
    check = r"""
const assert = require('node:assert/strict');
const vm = require('node:vm');
const source = JSON.parse(require('node:fs').readFileSync(0, 'utf8'));
class Element {
  constructor() {
    this.children = []; this.fields = new Map(); this.listeners = {};
    this.dataset = {}; this.textContent = ''; this.value = ''; this.hidden = false;
  }
  set innerHTML(_) { throw new Error('Public customer text must not be inserted as HTML'); }
  addEventListener(name, fn) { this.listeners[name] = fn; }
  append(...nodes) { nodes.forEach(node => this.insertBefore(node, null)); }
  insertBefore(node, before) {
    if (node.parent) node.remove();
    const index = before ? this.children.indexOf(before) : this.children.length;
    this.children.splice(index, 0, node); node.parent = this;
  }
  remove() {
    if (this.parent) this.parent.children.splice(this.parent.children.indexOf(this), 1);
    this.parent = null;
  }
  replaceChildren(fragment) {
    this.children.forEach(node => { node.parent = null; }); this.children = [];
    if (fragment) this.append(...fragment.children.slice());
  }
  querySelector(selector) {
    if (!this.fields.has(selector)) this.fields.set(selector, new Element());
    return this.fields.get(selector);
  }
  cloneNode() { return new Element(); }
}
function boot(brokenSocket = false) {
  const elements = new Map();
  const document = {
    hidden: false, listeners: {},
    getElementById(id) {
      if (!elements.has(id)) elements.set(id, new Element());
      return elements.get(id);
    },
    createElement() { return new Element(); }, createDocumentFragment() { return new Element(); },
    addEventListener(name, fn) { this.listeners[name] = fn; }
  };
  document.getElementById('customer-card-template').content = { firstElementChild: new Element() };
  const timers = new Map(), requests = [], pending = [];
  let timerId = 0, now = Date.now();
  class BrowserDate extends Date { static now() { return now; } }
  const window = {
    listeners: {},
    setTimeout(fn, delay) { timers.set(++timerId, { fn, delay }); return timerId; },
    clearTimeout(id) { timers.delete(id); },
    addEventListener(name, fn) { this.listeners[name] = fn; }
  };
  if (brokenSocket) window.io = () => { throw new Error('Socket library unavailable'); };
  const context = vm.createContext({
    window, document, Date: BrowserDate, Intl, AbortController,
    fetch(url, options) {
      requests.push({url, options});
      return new Promise((resolve, reject) => pending.push({resolve, reject}));
    }
  });
  vm.runInContext(source, context);
  const flush = async () => { for (let i = 0; i < 5; i++) await new Promise(resolve => setImmediate(resolve)); };
  return {
    elements, document, window, requests, pending, timers,
    get: id => document.getElementById(id),
    advance: ms => { now += ms; },
    async timer(delay) {
      const found = [...timers].find(([, value]) => value.delay === delay);
      assert(found, `missing ${delay}ms timer`);
      timers.delete(found[0]); found[1].fn(); await flush();
    },
    async answer(data, status = 200, retry = null) {
      assert(pending.length, 'no pending request');
      pending.shift().resolve({ok: status === 200, status,
        headers: {get() { return retry; }}, json: async () => data});
      await flush();
    },
    async fail() { pending.shift().reject(new Error('Network unavailable')); await flush(); },
    flush
  };
}
const field = (card, name) => card.querySelector('[data-field="' + name + '"]');
const customer = (id, name = 'Carl') => ({
  session_id: id, customer_name: name, space_type: 'Premium Lounge',
  time_in: '2026-10-26T05:30:00+00:00', seconds_used: 3600, paused: false,
  food_items: [{item_name: '<img src=x onerror=alert(1)>', quantity: 1, unit_price: 120, line_total: 120}],
  time_bill: 20, food_bill: 120, carried_food_bill: 0, total_bill: 140
});
const snapshot = rows => ({as_of: '2026-10-26T06:30:00+00:00', customers: rows});
(async () => {
  const browser = boot();
  assert.equal(browser.requests.length, 1, 'initial load must not wait for Socket.IO');
  assert.equal(browser.requests[0].url, '/api/current-customers');
  assert.equal(browser.requests[0].options.credentials, 'omit');
  assert.equal(browser.requests[0].options.cache, 'no-store');
  await browser.answer(snapshot([customer(1), customer(2, 'Alex')]));
  const list = browser.get('customer-list');
  const firstCard = list.children[0];
  firstCard.open = true;
  assert.equal(list.children.length, 2);
  assert.equal(field(firstCard, 'total-bill').textContent, '₱140.00');
  assert.equal(field(firstCard, 'food-items').children[0].children[0].children[0].textContent,
    '<img src=x onerror=alert(1)>');
  browser.get('customer-search').value = 'cArL';
  browser.get('customer-search').listeners.input();
  assert.equal(browser.requests.length, 1, 'search must not refetch on each keystroke');
  assert.equal(firstCard.hidden, false);
  assert.equal(list.children[1].hidden, true);
  await browser.timer(5000);
  await browser.answer(snapshot([{...customer(1), paused: true}, customer(2, 'Alex')]));
  assert.equal(list.children[0], firstCard);
  assert.equal(firstCard.open, true, 'updates must preserve expanded cards');
  assert.equal(browser.get('customer-search').value, 'cArL');
  assert.equal(field(firstCard, 'time-status').textContent, 'Paused · time charge frozen');

  const socket = {connected: false, listeners: {}, on(name, fn) { this.listeners[name] = fn; },
    connect() { this.connected = true; this.listeners.connect(); }};
  browser.window.io = (namespace, options) => {
    assert.equal(namespace, '/current-customer'); assert.equal(options.autoConnect, false); return socket;
  };
  browser.get('customer-socket-library').listeners.load();
  await browser.timer(150);
  for (let i = 0; i < 10; i++) socket.listeners.current_customers_changed();
  await browser.timer(150);
  assert.equal(browser.pending.length, 1, 'refreshes must not overlap');
  await browser.answer(snapshot([{...customer(1), food_bill: 180, total_bill: 200}]));
  assert.equal(browser.pending.length, 1, 'an in-flight change must queue a fresh read');
  await browser.answer(snapshot([{...customer(1), food_bill: 200, total_bill: 220}]));
  assert.equal(field(firstCard, 'total-bill').textContent, '₱220.00');
  assert.equal(list.children.length, 1, 'closed visits must disappear');
  assert.equal(browser.get('connection-status').textContent, 'Live updates');

  await browser.timer(5000);
  await browser.answer({error: 'Feed unavailable'}, 503);
  assert.equal(field(firstCard, 'total-bill').textContent, '₱220.00');
  assert.equal(browser.get('customer-update-error').hidden, false);
  assert.match(browser.get('customer-update-error').textContent, /out of date/);
  browser.advance(5000);
  await browser.timer(5000);
  await browser.answer({}, 429, '12');
  const requestCount = browser.requests.length;
  socket.listeners.current_customers_changed();
  await browser.timer(150);
  assert.equal(browser.requests.length, requestCount, 'respect Retry-After during socket bursts');
  browser.advance(12000);
  await browser.timer(12000);
  await browser.answer(snapshot([]));
  assert.equal(list.children.length, 0);
  assert.equal(browser.get('customer-empty-state').textContent, 'No current customers.');
  assert.equal(browser.get('customer-update-error').hidden, true);

  browser.document.hidden = true;
  browser.document.listeners.visibilitychange();
  const beforeHidden = browser.requests.length;
  socket.listeners.current_customers_changed();
  browser.get('refresh-customers').listeners.click();
  assert.equal(browser.requests.length, beforeHidden);
  browser.document.hidden = false;
  browser.document.listeners.visibilitychange();
  await browser.answer(snapshot([customer(3, 'Another customer')]));
  assert.equal(browser.get('customer-empty-state').textContent, 'No matching customer found.');
  browser.get('customer-search').value = '';
  browser.get('customer-search').listeners.input();
  assert.equal(list.children[0].hidden, false);
  await browser.timer(5000);
  await browser.answer({as_of: 'bad date', customers: []});
  assert.equal(list.children.length, 1, 'invalid JSON shape must not erase the last successful data');

  const broken = boot(true);
  await broken.answer(snapshot([customer(1)]));
  assert.equal(broken.get('customer-list').children.length, 1, 'broken Socket.IO must not block loading');
  await broken.timer(5000);
  await broken.fail();
  assert.equal(broken.get('customer-list').children.length, 1);
  assert.equal(broken.get('connection-status').textContent, 'Updates delayed');
})().catch(error => { console.error(error); process.exitCode = 1; });
"""
    result = subprocess.run([node, "-e", check], input=json.dumps(source),
                            text=True, encoding="utf-8", capture_output=True, check=False)
    assert result.returncode == 0, result.stderr
