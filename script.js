// Shared behavior for all pages: navigation and the public CV preview.
const navToggle = document.querySelector(".nav-toggle");
const navList = document.querySelector(".nav-list");

if (navToggle && navList) {
  const closeMenu = (restoreFocus = false) => {
    navList.classList.remove("is-open");
    navToggle.setAttribute("aria-expanded", "false");
    if (restoreFocus) navToggle.focus();
  };

  navToggle.addEventListener("click", () => {
    const isOpen = navList.classList.toggle("is-open");
    navToggle.setAttribute("aria-expanded", String(isOpen));
  });

  navList.addEventListener("click", (event) => {
    if (event.target.closest("a")) closeMenu();
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && navList.classList.contains("is-open")) closeMenu(true);
  });

  // Hide the small-screen links only after their menu button is operational.
  document.documentElement.classList.add("nav-ready");
}

// A short decorative handoff; the original mail link remains the fallback.
{
  const contact = document.querySelector("[data-email-courier]");
  if (contact) {
    const motionPreference = window.matchMedia("(prefers-reduced-motion: reduce)");
    const atlasUrl = new URL("assets/mascot/spider-courier.webp", document.baseURI).href;
    let atlasReady = false;
    let atlasLoading = false;
    let stage = null;
    let active = false;
    let timers = [];
    let restoreTarget = null;

    const preload = () => {
      if (motionPreference.matches || atlasReady || atlasLoading) return;
      atlasLoading = true;
      const atlas = new Image();
      atlas.onload = () => {
        const decoded = typeof atlas.decode === "function" ? atlas.decode() : Promise.resolve();
        decoded.then(() => {
          atlasReady = atlas.naturalWidth === 1536 && atlas.naturalHeight === 624;
          atlasLoading = false;
        }).catch(() => { atlasLoading = false; });
      };
      atlas.onerror = () => { atlasLoading = false; };
      atlas.src = atlasUrl;
    };

    contact.addEventListener("pointerenter", preload);
    contact.addEventListener("pointerdown", preload);
    contact.addEventListener("focus", preload);
    if ("requestIdleCallback" in window) window.requestIdleCallback(preload, { timeout: 2500 });
    else window.setTimeout(preload, 1800);

    const clearTimers = () => {
      timers.forEach((timer) => window.clearTimeout(timer));
      timers = [];
    };
    const schedule = (callback, delay) => timers.push(window.setTimeout(callback, delay));
    const dismiss = () => {
      clearTimers();
      active = false;
      if (!stage) return;
      const focusInside = stage.contains(document.activeElement);
      stage.hidden = true;
      stage.dataset.phase = "idle";
      if (focusInside && restoreTarget?.isConnected) restoreTarget.focus({ preventScroll: true });
    };

    const showEmailOptions = () => {
      clearTimers();
      stage.dataset.phase = "ready";
      stage.querySelector("[data-courier-status]").textContent = "Opening your email app…";
      schedule(dismiss, 12000);
    };

    const createStage = () => {
      if (stage) return;
      stage = document.createElement("section");
      stage.className = "email-courier";
      stage.id = "email-courier";
      stage.hidden = true;
      stage.setAttribute("aria-label", "Contact Sven Weber");
      contact.setAttribute("aria-controls", stage.id);
      stage.innerHTML = `
        <div class="email-courier__top">
          <p data-courier-status role="status" aria-live="polite" aria-atomic="true"></p>
          <button type="button" class="email-courier__dismiss" aria-label="Dismiss email animation">×</button>
        </div>
        <div class="email-courier__scene" aria-hidden="true">
          <div class="email-courier__runner">
            <div class="email-courier__sprite"></div>
            <span class="email-courier__letter"></span>
          </div>
          <span class="email-courier__mailbox"><span></span></span>
        </div>
        <div class="email-courier__options">
          <a data-courier-open>Open email app</a>
          <button type="button" data-courier-copy>Copy address</button>
          <span class="email-courier__address"></span>
        </div>
      `;
      document.body.append(stage);
      const open = stage.querySelector("[data-courier-open]");
      const address = decodeURIComponent(contact.getAttribute("href").slice(7).split("?")[0]);
      open.href = contact.href;
      stage.querySelector(".email-courier__address").textContent = address;
      stage.querySelector(".email-courier__dismiss").addEventListener("click", dismiss);
      // This explicit link retains a fresh user gesture if a browser blocks
      // the animation's delayed handoff to an external email application.
      open.addEventListener("click", showEmailOptions);
      stage.querySelector("[data-courier-copy]").addEventListener("click", async () => {
        showEmailOptions();
        try {
          await navigator.clipboard.writeText(address);
          stage.querySelector("[data-courier-status]").textContent = "Email address copied.";
        } catch {
          stage.querySelector("[data-courier-status]").textContent = "You can select and copy the address below.";
          const selection = window.getSelection();
          const range = document.createRange();
          range.selectNodeContents(stage.querySelector(".email-courier__address"));
          if (selection) {
            selection.removeAllRanges();
            selection.addRange(range);
          }
        }
      });
    };

    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && active && !document.querySelector("dialog[open]")) {
        event.preventDefault();
        dismiss();
      }
    });

    contact.addEventListener("click", (event) => {
      if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey || motionPreference.matches) return;
      if (active) {
        event.preventDefault();
        return;
      }
      // A missing or undecoded image must never prevent opening the mail link.
      if (!atlasReady) {
        preload();
        return;
      }
      createStage();
      event.preventDefault();
      restoreTarget = contact;
      active = true;
      stage.hidden = false;
      stage.dataset.phase = "running";
      stage.querySelector("[data-courier-status]").textContent = "Getting your email link ready…";
      stage.querySelector("[data-courier-open]").focus({ preventScroll: true });
      schedule(() => { stage.dataset.phase = "waving"; }, 1050);
      schedule(() => {
        showEmailOptions();
        if (!document.querySelector("dialog[open]")) {
          try { window.location.href = contact.href; } catch { /* The explicit mail link remains available. */ }
        }
      }, 1700);
    });
  }
}

const pageName = (value) => {
  const path = value.split(/[?#]/)[0].replace(/\/+$/, "");
  return (path.split("/").pop() || "index").replace(/\.html$/, "");
};
let currentPage = pageName(window.location.pathname);
const navLinks = document.querySelectorAll(".nav-list a");
if (window.location.pathname.endsWith("/") && !Array.from(navLinks).some((link) => pageName(link.getAttribute("href")) === currentPage)) {
  currentPage = "index";
}

navLinks.forEach((link) => {
  const linkPage = pageName(link.getAttribute("href"));

  if (linkPage === currentPage) {
    link.classList.add("is-active");
    link.setAttribute("aria-current", "page");
  }
});

// Keep ordinary PDF links as the fallback when modal dialogs are unavailable.
if (typeof HTMLDialogElement !== "undefined" && typeof HTMLDialogElement.prototype.showModal === "function") {
  const cvLinks = Array.from(document.querySelectorAll("a[href]")).filter((link) => {
    try {
      const url = new URL(link.href, window.location.href);
      return url.origin === window.location.origin && url.pathname.endsWith("/cv/Sven_Weber_CV_public.pdf") && !link.hasAttribute("download");
    } catch {
      return false;
    }
  });

  const cvPages = document.getElementById("cv-preview-pages");
  if (cvLinks.length && cvPages instanceof HTMLTemplateElement) {
    const dialog = document.createElement("dialog");
    dialog.className = "cv-dialog";
    dialog.id = "cv-preview";
    dialog.setAttribute("aria-labelledby", "cv-preview-heading");
    dialog.setAttribute("aria-describedby", "cv-preview-help");
    dialog.innerHTML = `
      <div class="cv-dialog__header">
        <h2 id="cv-preview-heading">Sven Weber · CV</h2>
        <div class="cv-dialog__controls">
          <a class="cv-dialog__download" download="Sven_Weber_CV_public.pdf">Download PDF</a>
          <button class="cv-dialog__close" type="button" autofocus>Close <span aria-hidden="true">×</span></button>
        </div>
      </div>
      <div class="cv-dialog__document" tabindex="0" role="document" aria-label="Sven Weber’s public curriculum vitae"></div>
      <p class="cv-dialog__help" id="cv-preview-help">Scroll to read all pages. <a target="_blank" rel="noopener noreferrer">Open the full PDF</a>.</p>
    `;
    document.body.append(dialog);

    const documentPreview = dialog.querySelector(".cv-dialog__document");
    const download = dialog.querySelector(".cv-dialog__download");
    const openPdf = dialog.querySelector(".cv-dialog__help a");
    const closeButton = dialog.querySelector("button");
    let trigger = null;
    let pageState = null;

    const closePreview = () => dialog.close();

    closeButton.addEventListener("click", closePreview);
    dialog.addEventListener("cancel", (event) => {
      event.preventDefault();
      closePreview();
    });
    dialog.addEventListener("click", (event) => {
      if (event.target !== dialog) return;
      const bounds = dialog.getBoundingClientRect();
      if (event.clientX < bounds.left || event.clientX > bounds.right || event.clientY < bounds.top || event.clientY > bounds.bottom) closePreview();
    });

    // Native modal dialogs keep the page inert; these boundaries also keep
    // keyboard navigation within the controls and scrollable document.
    dialog.addEventListener("keydown", (event) => {
      if (event.key !== "Tab") return;
      const focusable = Array.from(dialog.querySelectorAll('a[href], button, [tabindex="0"]')).filter((element) => !element.hidden && !element.disabled);
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && (document.activeElement === first || document.activeElement === dialog)) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    });

    dialog.addEventListener("close", () => {
      if (pageState) {
        document.documentElement.classList.remove("cv-viewer-open");
        document.body.style.top = pageState.top;
        document.body.style.paddingRight = pageState.paddingRight;
        window.scrollTo({ left: pageState.x, top: pageState.y, behavior: "instant" });
        pageState = null;
      }
      if (trigger && trigger.isConnected) trigger.focus({ preventScroll: true });
      trigger = null;
    });

    cvLinks.forEach((link) => {
      link.setAttribute("aria-haspopup", "dialog");
      link.setAttribute("aria-controls", dialog.id);
      link.addEventListener("click", (event) => {
        if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
        // Use the rendered link, including the build's current PDF fingerprint.
        const url = new URL(link.href, window.location.href);
        download.href = url.href;
        openPdf.href = url.href;
        const previousPageState = {
          x: window.scrollX,
          y: window.scrollY,
          top: document.body.style.top,
          paddingRight: document.body.style.paddingRight,
        };
        try {
          dialog.showModal();
        } catch {
          return;
        }
        event.preventDefault();
        trigger = link;
        pageState = previousPageState;
        if (!documentPreview.hasChildNodes()) documentPreview.append(cvPages.content.cloneNode(true));
        const bodyWidthBeforeLock = document.body.getBoundingClientRect().width;
        const paddingRight = parseFloat(window.getComputedStyle(document.body).paddingRight) || 0;
        document.body.style.top = `${-pageState.y}px`;
        document.documentElement.classList.add("cv-viewer-open");
        const scrollbarWidth = Math.max(0, document.body.getBoundingClientRect().width - bodyWidthBeforeLock);
        document.body.style.paddingRight = `${paddingRight + scrollbarWidth}px`;
        documentPreview.scrollTop = 0;
        closeButton.focus({ preventScroll: true });
      });
    });
  }
}
