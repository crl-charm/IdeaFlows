"""Staff pages must still load when real-time updates are unavailable."""

import json
import re
import shutil
import subprocess

import pytest
from flask import render_template, session

from app import create_app


@pytest.fixture
def app():
    application = create_app()
    application.config.update(TESTING=True, WTF_CSRF_ENABLED=False, SINGLE_SESSION_ENABLED=True)
    return application


def test_staff_bootstrap_survives_socket_failure_and_rejects_bad_api_responses(app):
    with app.test_request_context("/staff/menu"):
        session.update(user_id=1, username="test_user", role="staff")
        pages = {
            "menu": ("admin/menu.html", {}, "function loadCategories()"),
            "inventory": ("admin/inventory.html", {}, "function loadInventory()"),
            "daily_balance": ("admin/daily_balance.html", {}, "function loadReports()"),
            "expenses": ("staff/expenses.html", {"expenses": [], "categories": []}, "function loadExpenses()"),
            "payables": ("admin/payables.html", {}, "function loadPayables()"),
        }
        rendered = {name: render_template(template, **context) for name, (template, context, _) in pages.items()}

    def inline_scripts(html):
        return re.findall(r"<script(?:\s[^>]*)?>(.*?)</script>", html, re.DOTALL)

    scripts = inline_scripts(rendered["menu"])
    bootstrap = next(script for script in scripts if "window.createSmartPoller =" in script)
    tracker = next(script for script in scripts if "const sessionSocket =" in script)
    helpers = next(script for script in scripts if "window.fetchJSON =" in script)
    page_scripts = {
        name: next(script for script in inline_scripts(rendered[name]) if marker in script)
        for name, (_, _, marker) in pages.items()
    }
    assert scripts.index(bootstrap) < scripts.index(tracker)
    assert "window.managementBase =" in bootstrap
    assert "window.createDebouncedRefresh =" in bootstrap

    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is needed to exercise the rendered browser script")
    check = r"""
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const scripts = JSON.parse(fs.readFileSync(0, 'utf8'));
(async () => {
  const expected = {
    menu: ['/staff/menu/api/categories', '/staff/menu/api/items/all'],
    inventory: ['/staff/inventory/api/dashboard-items'],
    daily_balance: ['/staff/daily-balance/api/reports?', '/staff/daily-balance/api/today-stats', '/staff/daily-balance/api/soft-balances'],
    expenses: ['/expenses-view/api/expenses', '/staff/daily-balance/api/reports?'],
    payables: ['/staff/payables/api/payables', '/staff/daily-balance/api/reports?']
  };
  for (const [name, page] of Object.entries(scripts.pages)) {
    const ready = [];
    const elements = new Map();
    const requested = [];
    const window = {
      io() { throw new Error('Socket.IO unavailable'); },
      setTimeout() { return 1; }, clearTimeout() {}, setInterval() { throw new Error('Session timer unavailable'); },
      addEventListener() {}, location: { href: '' }
    };
    const document = {
      addEventListener(event, callback) { if (event === 'DOMContentLoaded') ready.push(callback); },
      getElementById(id) {
        if (id === 'markPayablePaidModal' || id === 'addExpenseModal') return null;
        if (!elements.has(id)) elements.set(id, {
          addEventListener() {}, setAttribute() {}, value: '', style: {}, children: [],
          classList: { add() {}, remove() {} }, innerHTML: '', textContent: ''
        });
        return elements.get(id);
      },
      querySelector() { return null; }, querySelectorAll() { return []; }, hidden: false
    };
    const context = vm.createContext({ window, document, URLSearchParams, console: { warn() {}, error() {} } });
    vm.runInContext(scripts.helpers, context);
    vm.runInContext(scripts.bootstrap, context);
    assert.equal(window.managementBase, '/staff');
    assert.equal(typeof window.createDebouncedRefresh, 'function');
    assert.equal(window.getIdeaFlowSocket(), null);
    assert.throws(() => vm.runInContext(scripts.tracker, context), /Session timer unavailable/);
    window.setInterval = () => 1;
    if (name === 'menu' || name === 'inventory') {
      window.io = () => ({ on() { throw new Error('Socket listener unavailable'); } });
    }
    context.fetchJSON = url => { requested.push(url); return Promise.reject(new Error('Offline')); };
    vm.runInContext(page, context);
    context.showToast = () => {};
    ready.forEach(callback => callback());
    for (const path of expected[name]) assert(requested.some(url => url.startsWith(path)), `${name}: missing ${path}`);
    assert(requested.every(url => !url.includes('/undefined/')), `${name}: undefined API base`);
    await new Promise(resolve => setImmediate(resolve));
    if (name === 'daily_balance') {
      const banner = elements.get('daily-balance-load-error');
      assert.equal(banner.hidden, false);
      assert(banner.textContent.includes('Daily Balance reports'));
    }
    if (name === 'expenses') {
      const day = new Intl.DateTimeFormat('sv-SE', { timeZone: 'Asia/Manila', year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date());
      const expense = { category: 'supplies', description: 'Test supply', amount: 12,
        business_date: day, expense_date: day, payment_method: 'cash', funding_source: 'business',
        balance_before: null, voided_at: null, logged_by: 'Diana' };
      context.escapeHTML = value => String(value);
      context.fetchJSON = url => url === '/expenses-view/api/expenses'
        ? Promise.resolve({ success: true, data: [expense] }) : Promise.reject(new Error('Totals unavailable'));
      vm.runInContext('loadExpenses()', context);
      await new Promise(resolve => setImmediate(resolve));
      assert(elements.get('expenses-table-body').innerHTML.includes('Test supply'));
      assert.equal(elements.get('expense-method-cards').textContent, 'Expense totals unavailable.');
    }
    if (name !== 'menu') continue;
    window.csrfFetch = async () => ({ ok: false, status: 401, json: async () => ({ error: 'Session expired' }) });
    await assert.rejects(window.fetchJSON('/staff/menu/api/items/all'), /Session expired/);
    assert.equal(window.location.href, '/login');
    window.csrfFetch = async () => ({ ok: true, status: 200, json: async () => { throw new SyntaxError('HTML'); } });
    await assert.rejects(window.fetchJSON('/staff/menu/api/items/all'), /invalid response/);
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
"""
    result = subprocess.run([node, "-e", check], input=json.dumps({"helpers": helpers, "bootstrap": bootstrap, "tracker": tracker, "pages": page_scripts}),
                            text=True, capture_output=True, check=False)
    assert result.returncode == 0, result.stderr
