"use strict";

(function () {
  const list = document.getElementById("customer-list");
  const template = document.getElementById("customer-card-template");
  const search = document.getElementById("customer-search");
  const refreshButton = document.getElementById("refresh-customers");
  const empty = document.getElementById("customer-empty-state");
  const errorBox = document.getElementById("customer-update-error");
  const count = document.getElementById("customer-count");
  const connection = document.getElementById("connection-status");
  const lastUpdated = document.getElementById("last-updated");
  const money = new Intl.NumberFormat("en-PH", { style: "currency", currency: "PHP" });
  const dateTime = new Intl.DateTimeFormat("en-PH", {
    timeZone: "Asia/Manila", month: "short", day: "numeric", year: "numeric",
    hour: "numeric", minute: "2-digit",
  });
  const updateTime = new Intl.DateTimeFormat("en-PH", {
    timeZone: "Asia/Manila", hour: "numeric", minute: "2-digit", second: "2-digit",
  });
  const cards = new Map();
  let snapshot = null;
  let socket = null;
  let timer = null;
  let debounce = null;
  let inFlight = false;
  let queued = false;
  let failures = 0;
  let nextAllowedAt = 0;

  function text(element, value) {
    if (element.textContent !== value) element.textContent = value;
  }

  function field(card, name) {
    return card.querySelector('[data-field="' + name + '"]');
  }

  function duration(seconds) {
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    return hours + "h " + String(minutes).padStart(2, "0") + "m " + String(seconds % 60).padStart(2, "0") + "s";
  }

  function updateConnectionStatus() {
    const live = socket && socket.connected;
    connection.dataset.state = failures ? "delayed" : live ? "live" : "polling";
    text(connection, failures ? "Updates delayed" : live ? "Live updates" : "Automatic refresh");
  }

  function renderFood(card, customer) {
    const food = field(card, "food-items");
    const signature = JSON.stringify(customer.food_items);
    if (food.dataset.signature !== signature) {
      const fragment = document.createDocumentFragment();
      customer.food_items.forEach(function (item) {
        const row = document.createElement("li");
        row.className = "food-item";
        const detail = document.createElement("div");
        const name = document.createElement("span");
        name.className = "food-item-name";
        name.textContent = item.item_name;
        const description = document.createElement("span");
        description.className = "food-item-description";
        description.textContent = item.quantity + " × " + money.format(item.unit_price);
        detail.append(name, description);
        const amount = document.createElement("span");
        amount.className = "food-item-amount";
        amount.textContent = money.format(item.line_total);
        row.append(detail, amount);
        fragment.append(row);
      });
      food.replaceChildren(fragment);
      food.dataset.signature = signature;
    }
    const noOrders = field(card, "no-orders");
    noOrders.hidden = customer.food_items.length > 0;
    text(noOrders, customer.carried_food_bill > 0 ? "No new food orders." : "No food orders yet.");
    field(card, "carried-charge").hidden = customer.carried_food_bill === 0;
    text(field(card, "carried-amount"), money.format(customer.carried_food_bill));
  }

  function renderCustomers() {
    if (!snapshot) return;
    const query = search.value.trim().toLocaleLowerCase();
    const activeIds = new Set();
    let visible = 0;
    snapshot.customers.forEach(function (customer, index) {
      activeIds.add(customer.session_id);
      let card = cards.get(customer.session_id);
      if (!card) {
        card = template.content.firstElementChild.cloneNode(true);
        cards.set(customer.session_id, card);
      }
      if (list.children[index] !== card) list.insertBefore(card, list.children[index] || null);
      card.hidden = !customer.customer_name.toLocaleLowerCase().includes(query);
      if (!card.hidden) visible += 1;
      text(field(card, "name"), customer.customer_name);
      text(field(card, "space"), customer.space_type);
      text(field(card, "time-in"), dateTime.format(new Date(customer.time_in)));
      text(field(card, "duration"), duration(customer.seconds_used));
      const timeStatus = field(card, "time-status");
      timeStatus.dataset.paused = String(customer.paused);
      text(timeStatus, customer.paused ? "Paused · time charge frozen" : "Running");
      text(field(card, "time-bill"), money.format(customer.time_bill));
      text(field(card, "food-bill"), money.format(customer.food_bill));
      text(field(card, "total-bill"), money.format(customer.total_bill));
      renderFood(card, customer);
    });
    cards.forEach(function (card, id) {
      if (!activeIds.has(id)) {
        card.remove();
        cards.delete(id);
      }
    });
    text(count, query ? visible + " matching visit(s)" : visible + " current visit(s)");
    empty.hidden = visible > 0;
    text(empty, snapshot.customers.length ? "No matching customer found." : "No current customers.");
  }

  function validSnapshot(data) {
    const nonnegative = value => typeof value === "number" && Number.isFinite(value) && value >= 0;
    return data && typeof data.as_of === "string" && Number.isFinite(Date.parse(data.as_of)) &&
      Array.isArray(data.customers) && data.customers.every(function (customer) {
        return customer && Number.isInteger(customer.session_id) && customer.session_id > 0 &&
          typeof customer.customer_name === "string" && typeof customer.space_type === "string" &&
          typeof customer.time_in === "string" && Number.isFinite(Date.parse(customer.time_in)) &&
          Number.isInteger(customer.seconds_used) && customer.seconds_used >= 0 &&
          typeof customer.paused === "boolean" &&
          [customer.time_bill, customer.food_bill, customer.carried_food_bill, customer.total_bill].every(nonnegative) &&
          Array.isArray(customer.food_items) && customer.food_items.every(function (item) {
            return item && typeof item.item_name === "string" && Number.isInteger(item.quantity) &&
              item.quantity >= 0 && nonnegative(item.unit_price) && nonnegative(item.line_total);
          });
      });
  }

  function scheduleRefresh() {
    window.clearTimeout(timer);
    if (!document.hidden) {
      timer = window.setTimeout(refresh, Math.max(5000, nextAllowedAt - Date.now()));
    }
  }

  async function refresh() {
    if (document.hidden) return;
    if (inFlight) { queued = true; return; }
    if (Date.now() < nextAllowedAt) { scheduleRefresh(); return; }
    window.clearTimeout(timer);
    inFlight = true;
    refreshButton.disabled = true;
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), 10000);
    let retryAfter = 0;
    try {
      const response = await fetch("/api/current-customers", {
        credentials: "omit", cache: "no-store", signal: controller.signal,
      });
      if (!response.ok) {
        if (response.status === 429) {
          const header = response.headers.get("Retry-After");
          const seconds = Number(header);
          retryAfter = Number.isFinite(seconds) ? seconds * 1000 : Math.max(0, Date.parse(header) - Date.now()) || 0;
        }
        throw new Error("Customer feed unavailable");
      }
      const data = await response.json();
      if (!validSnapshot(data)) throw new Error("Invalid customer feed");
      snapshot = data;
      failures = 0;
      nextAllowedAt = 0;
      errorBox.hidden = true;
      renderCustomers();
      text(lastUpdated, "Updated " + updateTime.format(new Date(data.as_of)) + " · Manila");
    } catch (_) {
      failures += 1;
      nextAllowedAt = Date.now() + Math.max(retryAfter, Math.min(30000, 5000 * Math.pow(2, Math.min(failures - 1, 3))));
      errorBox.hidden = false;
      text(errorBox, snapshot
        ? "Updates unavailable. Showing the last successful update; these amounts may be out of date. Retrying automatically."
        : "Could not load current customer bills. Retrying automatically, or use Refresh to check again.");
      if (!snapshot) {
        text(empty, "Waiting for current customer bills…");
        text(count, "Current visits unavailable");
      }
    } finally {
      window.clearTimeout(timeout);
      inFlight = false;
      refreshButton.disabled = false;
      updateConnectionStatus();
      const refreshAgain = queued && !failures;
      queued = false;
      if (refreshAgain) refresh();
      else scheduleRefresh();
    }
  }

  function requestRefresh() {
    if (document.hidden) return;
    window.clearTimeout(debounce);
    debounce = window.setTimeout(refresh, 150);
  }

  function connectSocket() {
    if (socket || typeof window.io !== "function") return;
    try {
      socket = window.io("/current-customer", {
        autoConnect: false, reconnection: true, reconnectionDelay: 1000,
        reconnectionDelayMax: 10000, timeout: 8000,
      });
      socket.on("connect", function () { updateConnectionStatus(); requestRefresh(); });
      socket.on("current_customers_changed", requestRefresh);
      socket.on("disconnect", updateConnectionStatus);
      socket.on("connect_error", updateConnectionStatus);
      socket.connect();
    } catch (_) {
      socket = null;
      updateConnectionStatus();
    }
  }

  search.addEventListener("input", renderCustomers);
  refreshButton.addEventListener("click", refresh);
  document.addEventListener("visibilitychange", function () {
    if (document.hidden) {
      window.clearTimeout(timer);
      window.clearTimeout(debounce);
    } else refresh();
  });
  window.addEventListener("online", refresh);
  const library = document.getElementById("customer-socket-library");
  if (library) library.addEventListener("load", connectSocket);

  refresh();
  connectSocket();
})();
