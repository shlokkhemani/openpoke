// Tiny DOM helpers. No framework, no build step.

export function h(tag, attrs, ...children) {
  const el = document.createElement(tag);
  if (attrs) {
    for (const [k, v] of Object.entries(attrs)) {
      if (v == null || v === false) continue;
      if (k === "class") el.className = Array.isArray(v) ? v.filter(Boolean).join(" ") : v;
      else if (k === "style" && typeof v === "object") Object.assign(el.style, v);
      else if (k.startsWith("on") && typeof v === "function") el.addEventListener(k.slice(2), v);
      else if (k === "html") el.innerHTML = v;
      else el.setAttribute(k, v === true ? "" : v);
    }
  }
  append(el, children);
  return el;
}

function append(el, children) {
  for (const c of children) {
    if (c == null || c === false) continue;
    if (Array.isArray(c)) append(el, c);
    else if (c instanceof Node) el.appendChild(c);
    else el.appendChild(document.createTextNode(String(c)));
  }
}

export function clear(el) {
  while (el.firstChild) el.removeChild(el.firstChild);
  return el;
}

export const fmt = {
  num(v, d = 2) {
    return typeof v === "number" && Number.isFinite(v) ? v.toFixed(d) : "—";
  },
  time(ts) {
    if (!ts || typeof ts !== "string") return "—";
    const m = ts.match(/T(\d\d:\d\d:\d\d(?:\.\d+)?)/);
    return m ? m[1] : ts;
  },
  shortId(id) {
    if (!id || typeof id !== "string") return "—";
    return id.length > 14 ? id.slice(0, 8) + "…" + id.slice(-4) : id;
  },
  json(v) {
    try {
      return JSON.stringify(v, null, 2);
    } catch {
      return String(v);
    }
  },
};
