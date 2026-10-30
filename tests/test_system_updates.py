"""Fixed dated patches, role-aware history and harmless per-browser read state."""
from datetime import date
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import shutil
import subprocess

from flask import render_template, render_template_string, session
import pytest

from app import create_app
from app.system_updates import SYSTEM_UPDATES, updates_for


@pytest.fixture
def app():
    app = create_app()
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False, SINGLE_SESSION_ENABLED=False)
    return app


@pytest.mark.parametrize("role,user_id,count", [("admin", 1, 9), ("staff", 1, 4), ("customer", 1, 0), ("admin", None, 0)])
def test_header_filters_notes_before_rendering_and_uses_real_bell(app, role, user_id, count):
    with app.test_request_context("/dashboard"):
        session.update(role=role, user_id=user_id)
        html = render_template("layout.html")
    assert html.count('data-update-id="') == count
    assert html.count('id="systemUpdatesButton"') == bool(count)
    assert html.count('id="systemUpdatesModal"') == bool(count)
    if count:
        assert '<i class="bi bi-bell fs-5" aria-hidden="true"></i>' in html
        assert f'ideaflow:updates:seen:{user_id}:{role}' in html
    if role != "admin" or not user_id:
        assert "Monthly accountant PDF" not in html
        assert "salary-expenses" not in html
        assert "2026-10-30-customer-visit-filters" not in html
        assert "2026-10-30-staff-attendance-filters" not in html
        assert 'href="/admin/reports?view=' not in html
    if role == "staff":
        assert 'href="/expenses-view"' in html and 'href="/admin/expenses"' not in html


def test_rendering_without_http_request_does_not_require_a_browser_session(app):
    with app.app_context():
        assert render_template_string("{{ system_updates|length }}") == "0"


def test_published_dates_and_previous_patch_stay_fixed():
    # Approved October 29 notes stay intact when later patches or code edits ship.
    previous = [entry for entry in SYSTEM_UPDATES if entry["date"] == "2026-10-29"]
    assert hashlib.sha256(json.dumps(previous, sort_keys=True).encode()).hexdigest() == (
        "f00f5c98928b3cabc52f4b1b57bdea9c842e13f1d6390e88fb285052ab74cc32"
    )
    for entry in SYSTEM_UPDATES:
        assert entry["id"].startswith(entry["date"] + "-")
        assert date.fromisoformat(entry["date"]).isoformat() == entry["date"]
    assert max(entry["date"] for entry in SYSTEM_UPDATES) == "2026-10-30"


@pytest.mark.parametrize("role", ["admin", "staff"])
def test_latest_patch_is_first_and_previous_patch_is_in_hidden_history(app, role):
    class PatchParser(HTMLParser):
        def __init__(self):
            super().__init__()
            self.patches = []

        def handle_starttag(self, tag, attrs):
            attrs = dict(attrs)
            if tag == "section" and "data-update-patch" in attrs:
                self.patches.append(attrs)

    with app.test_request_context("/dashboard"):
        session.update(role=role, user_id=1)
        html = render_template("layout.html")
    markup = PatchParser()
    markup.feed(html)
    latest, previous = markup.patches
    assert latest["data-update-patch"] == "2026-10-30"
    assert "data-latest-patch" in latest and "hidden" not in latest
    assert previous["data-update-patch"] == "2026-10-29" and "hidden" in previous
    assert '<time datetime="2026-10-30">October 30, 2026</time>' in html
    assert '<time datetime="2026-10-29">October 29, 2026</time>' in html
    assert 'aria-controls="systemUpdatesPatches">Show All</button>' in html
    # The catalog is copied for rendering; role links/date labels do not rewrite it.
    assert all("paths" in entry and "url" not in entry and "date_label" not in entry for entry in SYSTEM_UPDATES)


def test_catalog_links_work_for_the_intended_role_and_public_pages_stay_public(app):
    client = app.test_client()
    assert len({entry["id"] for entry in SYSTEM_UPDATES}) == len(SYSTEM_UPDATES)
    for role in ("admin", "staff"):
        with client.session_transaction() as state:
            state.update(user_id=1, username="test_user", role=role)
        for path in {entry["url"] for entry in updates_for(role)}:
            assert client.get(path).status_code == 200, path
    for path in ("/login", "/current-customer"):
        assert 'id="systemUpdatesModal"' not in client.get(path).get_data(as_text=True)
    with client.session_transaction() as state:
        state.update(user_id=1, username="test_user", role="staff")
    assert client.get('/admin/reports/api/monthly-accountant?month=2026-10').status_code == 403


def test_read_dot_is_account_scoped_resilient_and_does_not_duplicate_handlers():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is needed for the update read-state check")
    source = (Path(__file__).resolve().parents[1] / "static/js/system-updates.js").read_text(encoding="utf-8")
    check = r"""
const assert = require('node:assert/strict');
const vm = require('node:vm');
const source = JSON.parse(require('node:fs').readFileSync(0, 'utf8'));
const saved = new Map();
function page(account, latestIds, olderIds=[], blocked=false) {
  const handlers = {}, windowHandlers = {}, dot = {hidden:true}, status = {textContent:''};
  const buttonHandlers = {}, attrs = {'aria-expanded':'false'};
  const entries = ids => ids.map(id=>({dataset:{updateId:id}}));
  const patches = [{querySelectorAll:()=>entries(latestIds),hidden:false}];
  if(olderIds.length)patches.push({querySelectorAll:()=>entries(olderIds),hidden:true});
  const showAll = olderIds.length ? {textContent:'Show All',
    setAttribute:(name,value)=>{attrs[name]=value;},getAttribute:name=>attrs[name],
    addEventListener:(event,fn)=>{assert(!buttonHandlers[event]);buttonHandlers[event]=fn;}} : null;
  let hidden = 0;
  const modal = {dataset:{readKey:`ideaflow:updates:seen:${account}`},
    querySelectorAll:selector => selector==='[data-update-patch]' ? patches : entries([...latestIds,...olderIds]),
    addEventListener:(event,fn)=>{assert(!handlers[event]);handlers[event]=fn;}};
  const document = {getElementById:id=>({systemUpdatesModal:modal,systemUpdatesDot:dot,systemUpdatesStatus:status,systemUpdatesShowAll:showAll}[id])};
  const localStorage = {getItem:key=>{if(blocked)throw Error('Blocked');return saved.get(key)||null;},
    setItem:(key,value)=>{if(blocked)throw Error('Blocked');saved.set(key,value);}};
  const window = {addEventListener:(event,fn)=>{assert(!windowHandlers[event]);windowHandlers[event]=fn;},
    bootstrap:{Modal:{getInstance:()=>({hide:()=>{hidden++;}})}}};
  const context = vm.createContext({document,window,localStorage});
  vm.runInContext(source,context);
  return {dot,status,modal,handlers,windowHandlers,context,showAll,patches,buttonHandlers,hidden:()=>hidden};
}
const first = page('1:admin',['a','b'],['old']);
assert.equal(first.dot.hidden,false);
first.handlers['show.bs.modal']();
first.handlers['shown.bs.modal']();
assert.equal(first.dot.hidden,true);
assert.equal(first.patches[1].hidden,true);
assert.deepEqual(JSON.parse(saved.get(first.modal.dataset.readKey)),['a','b']);
assert.equal(page('1:admin',['a','b'],['old']).dot.hidden,true);
assert.equal(page('1:admin',['a','b','c'],['old']).dot.hidden,false);
assert.equal(page('2:admin',['a','b']).dot.hidden,false);
assert.equal(page('1:staff',['a','b']).dot.hidden,false);
first.buttonHandlers.click();
assert.equal(first.patches[1].hidden,false);
assert.equal(first.showAll.getAttribute('aria-expanded'),'true');
assert.equal(first.showAll.textContent,'Show latest only');
assert.deepEqual(JSON.parse(saved.get(first.modal.dataset.readKey)),['a','b','old']);
first.buttonHandlers.click();
assert.equal(first.patches[1].hidden,true);
assert.equal(first.showAll.textContent,'Show All');
first.buttonHandlers.click();
first.handlers['show.bs.modal']();
assert.equal(first.patches[1].hidden,true);
assert.equal(first.showAll.getAttribute('aria-expanded'),'false');
vm.runInContext(source,first.context);
first.handlers.click({target:{closest:()=>true}});
assert.equal(first.hidden(),1);
const blocked = page('blocked:staff',['a'],['old'],true);
assert.equal(blocked.dot.hidden,false);
blocked.handlers['shown.bs.modal']();
assert.equal(blocked.dot.hidden,true);
blocked.windowHandlers.pageshow();
assert.equal(blocked.dot.hidden,true);
blocked.buttonHandlers.click();
assert.equal(blocked.patches[1].hidden,false);
saved.set('ideaflow:updates:seen:bad:staff','{bad json');
assert.equal(page('bad:staff',['a']).dot.hidden,false);
const concurrent = page('3:staff',['a']);
saved.set(concurrent.modal.dataset.readKey,'["a"]');
concurrent.windowHandlers.storage({key:concurrent.modal.dataset.readKey});
assert.equal(concurrent.dot.hidden,true);
const missing = vm.createContext({document:{getElementById:()=>null}});
vm.runInContext(source,missing);
"""
    result = subprocess.run([node, "-e", check], input=json.dumps(source), capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
