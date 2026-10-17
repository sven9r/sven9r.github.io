// Shared behavior for all pages: mobile navigation and active-page highlighting.
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
