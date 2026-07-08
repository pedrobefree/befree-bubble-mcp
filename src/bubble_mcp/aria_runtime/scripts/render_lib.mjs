async function resolveEngine() {
  try {
    const mod = await import("playwright");
    return { engine: "playwright", playwrightChromium: mod.chromium, puppeteerLib: null };
  } catch (_) {
    try {
      const mod = await import("puppeteer");
      const puppeteerLib = mod?.default || mod;
      return { engine: "puppeteer", playwrightChromium: null, puppeteerLib };
    } catch (err) {
      throw new Error(
        `Neither Playwright nor Puppeteer is available: ${String(err && err.message ? err.message : err)}`
      );
    }
  }
}

const STYLE_IMPORT_STATE_PROPS = [
  "background",
  "background-color",
  "color",
  "font-size",
  "font-weight",
  "font-family",
  "line-height",
  "letter-spacing",
  "border",
  "border-width",
  "border-style",
  "border-color",
  "border-radius",
  "border-top",
  "border-right",
  "border-bottom",
  "border-left",
  "border-top-width",
  "border-right-width",
  "border-bottom-width",
  "border-left-width",
  "border-top-style",
  "border-right-style",
  "border-bottom-style",
  "border-left-style",
  "border-top-color",
  "border-right-color",
  "border-bottom-color",
  "border-left-color",
  "border-top-left-radius",
  "border-top-right-radius",
  "border-bottom-right-radius",
  "border-bottom-left-radius",
  "box-shadow",
  "padding",
  "padding-top",
  "padding-right",
  "padding-bottom",
  "padding-left",
  "opacity",
];

async function styleSubsetForSelector(page, selector, props = STYLE_IMPORT_STATE_PROPS) {
  return await page.evaluate(
    ({ sel, propNames }) => {
      const el = document.querySelector(sel || "body");
      if (!el) return null;
      const cs = window.getComputedStyle(el);
      const out = {};
      for (const prop of propNames) {
        const value = String(cs.getPropertyValue(prop) || "").trim();
        if (!value || value === "normal" || value === "auto") continue;
        out[prop] = value;
      }
      return out;
    },
    { sel: selector || "body", propNames: props },
  );
}

function diffStyleSubset(base, state) {
  if (!base || !state) return {};
  const diff = {};
  for (const [key, value] of Object.entries(state)) {
    if (String(base[key] || "").trim() !== String(value || "").trim()) {
      diff[key] = value;
    }
  }
  return diff;
}

async function resetElementState(page, selector) {
  try {
    await page.mouse.up();
  } catch (_) {
    // Best effort only.
  }
  try {
    await page.mouse.move(0, 0);
  } catch (_) {
    // Best effort only.
  }
  try {
    await page.evaluate((sel) => {
      const el = document.querySelector(sel || "body");
      if (el && typeof el.blur === "function") el.blur();
    }, selector || "body");
  } catch (_) {
    // Best effort only.
  }
}

async function captureStyleImportStates(page, selector, sleep) {
  const safeSelector = selector || "body";
  const exists = await page.evaluate((sel) => Boolean(document.querySelector(sel || "body")), safeSelector);
  if (!exists) {
    return { base: {}, hover: {}, focus: {}, pressed: {}, disabled: {} };
  }

  await resetElementState(page, safeSelector);
  const base = (await styleSubsetForSelector(page, safeSelector)) || {};
  const states = { base, hover: {}, focus: {}, pressed: {}, disabled: {} };

  try {
    await page.hover(safeSelector);
    await sleep(80);
    states.hover = diffStyleSubset(base, await styleSubsetForSelector(page, safeSelector));
  } catch (_) {
    states.hover = {};
  } finally {
    await resetElementState(page, safeSelector);
  }

  try {
    await page.focus(safeSelector);
    await sleep(80);
    states.focus = diffStyleSubset(base, await styleSubsetForSelector(page, safeSelector));
  } catch (_) {
    states.focus = {};
  } finally {
    await resetElementState(page, safeSelector);
  }

  try {
    const handle = await page.$(safeSelector);
    const box = handle && typeof handle.boundingBox === "function" ? await handle.boundingBox() : null;
    if (box && box.width > 0 && box.height > 0) {
      await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
      await page.mouse.down();
      await sleep(80);
      states.pressed = diffStyleSubset(base, await styleSubsetForSelector(page, safeSelector));
      await page.mouse.up();
    }
  } catch (_) {
    states.pressed = {};
  } finally {
    await resetElementState(page, safeSelector);
  }

  try {
    const disabledState = await page.evaluate(
      ({ sel, propNames }) => {
        const el = document.querySelector(sel || "body");
        if (!el) return null;
        const hadAttribute = el.hasAttribute("disabled");
        const previousAttribute = el.getAttribute("disabled");
        const hadDisabledProperty = "disabled" in el;
        const previousDisabledProperty = hadDisabledProperty ? Boolean(el.disabled) : undefined;
        el.setAttribute("disabled", "");
        if (hadDisabledProperty) el.disabled = true;
        const cs = window.getComputedStyle(el);
        const out = {};
        for (const prop of propNames) {
          const value = String(cs.getPropertyValue(prop) || "").trim();
          if (!value || value === "normal" || value === "auto") continue;
          out[prop] = value;
        }
        if (hadAttribute) {
          el.setAttribute("disabled", previousAttribute || "");
        } else {
          el.removeAttribute("disabled");
        }
        if (hadDisabledProperty) el.disabled = previousDisabledProperty;
        return out;
      },
      { sel: safeSelector, propNames: STYLE_IMPORT_STATE_PROPS },
    );
    states.disabled = diffStyleSubset(base, disabledState);
  } catch (_) {
    states.disabled = {};
  }

  return states;
}

function browserEvaluateFn(selector) {
  const EXTRACT_STYLE_PROPS = [
    "display",
    "position",
    "inset",
    "top",
    "right",
    "bottom",
    "left",
    "z-index",
    "width",
    "height",
    "min-width",
    "min-height",
    "max-width",
    "max-height",
    "margin-top",
    "margin-right",
    "margin-bottom",
    "margin-left",
    "padding-top",
    "padding-right",
    "padding-bottom",
    "padding-left",
    "gap",
    "row-gap",
    "column-gap",
    "grid-template-columns",
    "grid-template-rows",
    "grid-column",
    "grid-row",
    "grid-auto-columns",
    "grid-auto-rows",
    "flex-wrap",
    "flex-direction",
    "align-content",
    "justify-content",
    "align-items",
    "align-self",
    "text-align",
    "text-transform",
    "text-decoration",
    "white-space",
    "vertical-align",
    "font-size",
    "font-weight",
    "font-style",
    "font-family",
    "line-height",
    "letter-spacing",
    "color",
    "background-color",
    "background-image",
    "background-size",
    "background-position",
    "background-repeat",
    "filter",
    "border",
    "border-width",
    "border-style",
    "border-color",
    "border-radius",
    "border-top-left-radius",
    "border-top-right-radius",
    "border-bottom-left-radius",
    "border-bottom-right-radius",
    "box-shadow",
    "opacity",
    "aspect-ratio",
    "object-fit",
    "object-position",
    "overflow",
    "overflow-x",
    "overflow-y",
    "transform",
    "transform-origin",
  ];
  const PSEUDO_STYLE_PROPS = [
    "display",
    "position",
    "inset",
    "top",
    "right",
    "bottom",
    "left",
    "width",
    "height",
    "background",
    "background-image",
    "background-size",
    "background-position",
    "background-repeat",
    "opacity",
    "transform",
    "z-index",
  ];

  const stabilizeDynamicUi = () => {
    const style = document.createElement("style");
    style.setAttribute("data-bubble-mcp-render-freeze", "1");
    style.textContent = [
      "*, *::before, *::after {",
      "  animation-delay: 0s !important;",
      "  animation-duration: 0s !important;",
      "  animation-iteration-count: 1 !important;",
      "  transition-delay: 0s !important;",
      "  transition-duration: 0s !important;",
      "  scroll-behavior: auto !important;",
      "}",
    ].join("\n");
    document.head.appendChild(style);

    for (const carousel of Array.from(document.querySelectorAll(".owl-carousel"))) {
      const stage = carousel.querySelector(".owl-stage");
      const items = stage ? Array.from(stage.querySelectorAll(".owl-item")) : [];
      const originals = items.filter((item) => !String(item.className || "").split(/\s+/).includes("cloned"));
      const first = originals[0] || items[0];
      if (!stage || !first) continue;
      const firstRect = first.getBoundingClientRect();
      const firstWidth = Number(firstRect.width || parseFloat(window.getComputedStyle(first).width || "") || 0);
      const firstHeight = Number(firstRect.height || parseFloat(window.getComputedStyle(first).height || "") || 0);
      stage.style.transform = "translate3d(0px, 0px, 0px)";
      stage.style.left = "0px";
      if (firstWidth > 0) stage.style.width = `${firstWidth}px`;
      if (firstHeight > 0) stage.style.height = `${firstHeight}px`;
      for (const item of items) {
        const isFirst = item === first;
        item.classList.toggle("active", isFirst);
        item.classList.remove("center");
        item.style.display = isFirst ? "block" : "none";
        item.style.transform = "none";
        if (firstWidth > 0) item.style.width = `${firstWidth}px`;
        if (firstHeight > 0) item.style.height = `${firstHeight}px`;
      }
      const outer = carousel.querySelector(".owl-stage-outer");
      if (outer) {
        outer.style.transform = "none";
        outer.style.overflow = "visible";
        if (firstWidth > 0) outer.style.width = `${firstWidth}px`;
        if (firstHeight > 0) outer.style.height = `${firstHeight}px`;
      }
      carousel.querySelectorAll(".owl-dot").forEach((dot, index) => dot.classList.toggle("active", index === 0));
      carousel.querySelectorAll(".owl-nav, .owl-controls, .owl-dots").forEach((controls) => {
        controls.style.display = "none";
      });
    }
  };

  const findFixedTop = () => {
    const els = Array.from(document.querySelectorAll("*"));
    const winW = window.innerWidth || 0;
    let best = null;
    let bestScore = -Infinity;
    for (const el of els) {
      const cs = window.getComputedStyle(el);
      if (cs.position !== "fixed") continue;
      const top = parseFloat(cs.top || "");
      if (!Number.isFinite(top) || Math.abs(top) > 2) continue;
      const rect = el.getBoundingClientRect();
      if (!rect || !rect.width || !rect.height) continue;
      const leftOk = Math.abs(rect.left) <= 5;
      const rightOk = winW ? Math.abs(rect.right - winW) <= 5 : false;
      const widthScore = winW ? rect.width / winW : 0;
      const score = widthScore + (leftOk ? 0.3 : 0) + (rightOk ? 0.3 : 0) - Math.abs(rect.top || 0) / 100;
      if (score > bestScore) {
        bestScore = score;
        best = el;
      }
    }
    return best;
  };

  const selected = selector ? document.querySelector(selector) : null;
  const root =
    selected ||
    findFixedTop() ||
    document.body ||
    document.documentElement;

  stabilizeDynamicUi();

  const abs = (rawUrl) => {
    const txt = String(rawUrl || "").trim();
    if (!txt) return "";
    try {
      return new URL(txt, window.location.href).toString();
    } catch (_) {
      return txt;
    }
  };

  const normalizeCssUrls = (value) => {
    const raw = String(value || "").trim();
    if (!raw || !raw.includes("url(")) return raw;
    return raw.replace(/url\((['"]?)(.*?)\1\)/g, (_match, _quote, url) => {
      const resolved = abs(url);
      if (!resolved) return _match;
      return `url("${resolved}")`;
    });
  };

  const mergeInlineStyles = (el, styleEntries) => {
    const existing = String(el.getAttribute("style") || "").trim();
    const pairs = new Map();

    const putPair = (chunk) => {
      const idx = chunk.indexOf(":");
      if (idx <= 0) return;
      const key = chunk.slice(0, idx).trim().toLowerCase();
      const val = chunk.slice(idx + 1).trim();
      if (!key || !val) return;
      pairs.set(key, val);
    };

    if (existing) {
      existing
        .split(";")
        .map((s) => s.trim())
        .filter(Boolean)
        .forEach(putPair);
    }
    for (const entry of styleEntries) {
      putPair(entry);
    }
    const finalStyle = Array.from(pairs.entries())
      .map(([k, v]) => `${k}: ${v}`)
      .join("; ");
    if (finalStyle) {
      el.setAttribute("style", `${finalStyle};`);
    }
  };

  const nodes = [root, ...Array.from(root.querySelectorAll("*"))];
  for (const el of nodes) {
    const cs = window.getComputedStyle(el);
    const styleEntries = [];
    for (const p of EXTRACT_STYLE_PROPS) {
      const v = String(cs.getPropertyValue(p) || "").trim();
      if (!v || v === "normal" || v === "auto") continue;
      styleEntries.push(`${p}: ${v}`);
    }
    if (styleEntries.length) {
      mergeInlineStyles(el, styleEntries);
    }

    for (const attr of ["src", "href", "poster", "data-src", "data-lottie-url"]) {
      if (el.hasAttribute(attr)) {
        const resolved = abs(el.getAttribute(attr));
        if (resolved) el.setAttribute(attr, resolved);
      }
    }

    if (el.hasAttribute("srcset")) {
      const normalized = String(el.getAttribute("srcset") || "")
        .split(",")
        .map((part) => {
          const chunks = part.trim().split(/\s+/);
          const first = chunks.shift() || "";
          if (!first) return "";
          const resolved = abs(first);
          return [resolved, ...chunks].join(" ").trim();
        })
        .filter(Boolean)
        .join(", ");
      if (normalized) {
        el.setAttribute("srcset", normalized);
      }
    }
  }

  const normalizeText = (txt) =>
    String(txt || "")
      .replace(/\s+/g, " ")
      .trim();

  const cssSubsetFor = (cs, props) => {
    const out = {};
    for (const p of props) {
      const v = String(cs.getPropertyValue(p) || "").trim();
      if (!v || v === "normal" || v === "auto") continue;
      out[p] = v.includes("url(") ? normalizeCssUrls(v) : v;
    }
    return out;
  };
  const cssSubset = (cs) => cssSubsetFor(cs, EXTRACT_STYLE_PROPS);

  let nodeCount = 0;
  let domTruncated = false;
  // Keep large rendered sections intact (Framer/visual builders can exceed 12k nodes).
  const MAX_NODES = 120000;

  const serializeNode = (node) => {
    if (!node) return null;
    if (nodeCount >= MAX_NODES) {
      domTruncated = true;
      return null;
    }

    if (node.nodeType === Node.TEXT_NODE) {
      const rawText = String(node.nodeValue || "");
      if (!rawText || !rawText.trim()) return null;
      nodeCount += 1;
      return {
        type: "text",
        text: rawText.replace(/\s+/g, " "),
        rawText,
        leadingSpace: /^\s/.test(rawText),
        trailingSpace: /\s$/.test(rawText),
      };
    }

    if (node.nodeType !== Node.ELEMENT_NODE) {
      return null;
    }

    nodeCount += 1;
    const el = node;
    const cs = window.getComputedStyle(el);
    const rect = el.getBoundingClientRect();
    const tag = String(el.tagName || "").toLowerCase();

    let intrinsicWidth = 0;
    let intrinsicHeight = 0;
    if (tag === "img") {
      intrinsicWidth = Number(el.naturalWidth || 0);
      intrinsicHeight = Number(el.naturalHeight || 0);
    } else if (tag === "video") {
      intrinsicWidth = Number(el.videoWidth || 0);
      intrinsicHeight = Number(el.videoHeight || 0);
    }

    const attributes = {};
    for (const attr of Array.from(el.attributes || [])) {
      const key = String(attr.name || "").trim();
      if (!key) continue;
      let value = String(attr.value || "");
      if (["src", "href", "poster", "data-src", "data-lottie-url"].includes(key)) {
        value = abs(value);
      }
      if (key === "srcset") {
        value = String(value)
          .split(",")
          .map((part) => {
            const chunks = part.trim().split(/\s+/);
            const first = chunks.shift() || "";
            if (!first) return "";
            const resolved = abs(first);
            return [resolved, ...chunks].join(" ").trim();
          })
          .filter(Boolean)
          .join(", ");
      }
      attributes[key] = value;
    }

    const children = [];
    for (const child of Array.from(el.childNodes || [])) {
      const serializedChild = serializeNode(child);
      if (serializedChild) children.push(serializedChild);
    }

    const afterStyles = cssSubsetFor(window.getComputedStyle(el, "::after"), PSEUDO_STYLE_PROPS);
    const beforeStyles = cssSubsetFor(window.getComputedStyle(el, "::before"), PSEUDO_STYLE_PROPS);
    const pseudo = {};
    const afterBg =
      (afterStyles["background-image"] && afterStyles["background-image"] !== "none") ||
      (afterStyles["background"] && afterStyles["background"] !== "none");
    if (afterBg) {
      pseudo.after = afterStyles;
    }
    const beforeBg =
      (beforeStyles["background-image"] && beforeStyles["background-image"] !== "none") ||
      (beforeStyles["background"] && beforeStyles["background"] !== "none");
    if (beforeBg) {
      pseudo.before = beforeStyles;
    }
    const hasPseudo = Object.keys(pseudo).length > 0;
    return {
      type: "element",
      tag: String(el.tagName || "").toLowerCase(),
      attributes,
      computedStyle: cssSubset(cs),
      pseudo: hasPseudo ? pseudo : undefined,
      rect: {
        x: Number(rect.x || 0),
        y: Number(rect.y || 0),
        top: Number(rect.top || 0),
        left: Number(rect.left || 0),
        right: Number(rect.right || 0),
        bottom: Number(rect.bottom || 0),
        width: Number(rect.width || 0),
        height: Number(rect.height || 0),
      },
      intrinsic: {
        width: intrinsicWidth,
        height: intrinsicHeight,
      },
      text: normalizeText(el.textContent || ""),
      children,
    };
  };

  return {
    html: root.outerHTML || "",
    selected: Boolean(selected),
    selector: selector || "body",
    dom: serializeNode(root),
    dom_truncated: domTruncated,
    dom_node_count: nodeCount,
  };
}

export async function extractRenderedHtml({
  url,
  selector = "body",
  timeout = 30000,
  viewportWidth = 1440,
  viewportHeight = 2400,
}) {
  if (!url) {
    throw new Error("Missing required url");
  }
  const safeTimeout = Number.isFinite(timeout) && timeout > 0 ? timeout : 30000;
  const safeSelector = selector || "body";

  const { engine, playwrightChromium, puppeteerLib } = await resolveEngine();
  const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
  const selectorExists = async (page, sel) => {
    if (!sel || sel === "body") return true;
    return await page.evaluate((s) => Boolean(document.querySelector(s)), sel);
  };
  const scrollToFindSelector = async (page, sel, maxDurationMs) => {
    if (!sel || sel === "body") return true;
    const started = Date.now();
    while (Date.now() - started < maxDurationMs) {
      if (await selectorExists(page, sel)) {
        return true;
      }
      const metrics = await page.evaluate(() => {
        const doc = document.documentElement;
        return {
          scrollY: window.scrollY || 0,
          scrollHeight: doc ? doc.scrollHeight : 0,
          innerHeight: window.innerHeight || 0,
        };
      });
      const { scrollY, scrollHeight, innerHeight } = metrics || {};
      if (!scrollHeight || scrollY + innerHeight + 2 >= scrollHeight) {
        break;
      }
      const step = Math.max(200, Math.floor((innerHeight || 800) * 0.7));
      const nextY = Math.min(scrollY + step, scrollHeight);
      await page.evaluate((y) => window.scrollTo(0, y), nextY);
      await sleep(250);
    }
    return await selectorExists(page, sel);
  };
  let browser = null;
  try {
    const executablePath =
      String(process.env.BUBBLE_CLI_BROWSER_PATH || process.env.PUPPETEER_EXECUTABLE_PATH || "").trim() ||
      undefined;
    if (engine === "playwright") {
      browser = await playwrightChromium.launch({
        headless: true,
        ...(executablePath ? { executablePath } : {}),
        args: ["--no-sandbox", "--disable-setuid-sandbox"],
      });
    } else {
      browser = await puppeteerLib.launch({
        headless: true,
        ...(executablePath ? { executablePath } : {}),
        args: ["--no-sandbox", "--disable-setuid-sandbox"],
      });
    }

    const page = await browser.newPage();
    if (engine === "playwright") {
      await page.setViewportSize({ width: viewportWidth, height: viewportHeight });
    } else {
      await page.setViewport({ width: viewportWidth, height: viewportHeight });
    }

    await page.goto(url, {
      waitUntil: "domcontentloaded",
      timeout: safeTimeout,
    });

    if (engine === "playwright") {
      try {
        await page.waitForLoadState("networkidle", {
          timeout: Math.max(3000, Math.min(12000, Math.floor(safeTimeout / 2))),
        });
      } catch (_) {
        // Best effort only.
      }
    } else if (typeof page.waitForNetworkIdle === "function") {
      try {
        await page.waitForNetworkIdle({
          idleTime: 700,
          timeout: Math.max(3000, Math.min(12000, Math.floor(safeTimeout / 2))),
        });
      } catch (_) {
        // Best effort only.
      }
    }

    if (safeSelector && safeSelector !== "body") {
      try {
        const selectorTimeout = Math.max(2000, Math.min(10000, Math.floor(safeTimeout / 3)));
        if (engine === "playwright") {
          await page.waitForSelector(safeSelector, {
            timeout: selectorTimeout,
            state: "attached",
          });
        } else {
          await page.waitForSelector(safeSelector, { timeout: selectorTimeout });
        }
      } catch (_) {
        // Continue with fallback to body in page context.
      }
    }

    if (safeSelector && safeSelector !== "body") {
      const found = await selectorExists(page, safeSelector);
      if (!found) {
        const scrollTimeout = Math.max(3000, Math.min(16000, Math.floor(safeTimeout / 2)));
        await scrollToFindSelector(page, safeSelector, scrollTimeout);
      }
    }

    const styleStates = await captureStyleImportStates(page, safeSelector, sleep).catch(() => ({
      base: {},
      hover: {},
      focus: {},
      pressed: {},
      disabled: {},
    }));

    await sleep(900);
    const result = await page.evaluate(browserEvaluateFn, safeSelector);
    return { ...result, engine, styleStates };
  } finally {
    if (browser) {
      await browser.close().catch(() => {});
    }
  }
}
