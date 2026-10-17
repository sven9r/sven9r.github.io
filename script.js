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
        const scrollbarWidth = window.innerWidth - document.documentElement.clientWidth;
        const paddingRight = parseFloat(window.getComputedStyle(document.body).paddingRight) || 0;
        document.body.style.top = `${-pageState.y}px`;
        document.body.style.paddingRight = `${paddingRight + scrollbarWidth}px`;
        document.documentElement.classList.add("cv-viewer-open");
        documentPreview.scrollTop = 0;
        closeButton.focus({ preventScroll: true });
      });
    });
  }
}
