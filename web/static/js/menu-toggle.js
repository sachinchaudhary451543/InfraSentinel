document.addEventListener("DOMContentLoaded", () => {
  const nav = document.querySelector("nav");
  if (!nav) return;

  // Ensure toggle button exists (create if missing)
  let toggle = nav.querySelector("#menuToggle");
  if (!toggle) {
    const rightContainer = nav.querySelector("div") || nav;
    toggle = document.createElement("button");
    toggle.id = "menuToggle";
    toggle.type = "button";
    toggle.className = "md:hidden text-blue-900 text-3xl focus:outline-none";
    toggle.setAttribute("aria-label", "Open menu");
    toggle.innerText = "☰";
    // append at end of nav header area
    rightContainer.appendChild(toggle);
  }

  // Ensure mobile menu container exists (create if missing)
  let mobileMenu = document.getElementById("mobileMenu");
  if (!mobileMenu) {
    mobileMenu = document.createElement("div");
    mobileMenu.id = "mobileMenu";
    mobileMenu.className =
      "hidden flex flex-col bg-gray-800 px-6 pb-4 md:hidden";
    nav.appendChild(mobileMenu);
  }

  // Populate mobile menu dynamically from desktop nav links (only once)
  function populateMobileMenu() {
    // don't re-populate if items already present
    if (mobileMenu.querySelectorAll("a").length > 0) return;

    // Collect links inside the nav element (exclude links that point to current page anchors)
    const anchors = Array.from(nav.querySelectorAll("a")).filter((a) => {
      if (!a.href) return false;
      // ignore mailto/tel and javascript pseudo links
      const href = a.getAttribute("href") || "";
      if (
        href.startsWith("mailto:") ||
        href.startsWith("tel:") ||
        href.startsWith("javascript:")
      )
        return false;
      // ignore anchors inside the mobileMenu itself
      if (a.closest("#mobileMenu")) return false;
      // ignore logo anchors or images without href target (best-effort)
      if (a.querySelector("img")) return false;
      return true;
    });

    // If no desktop links found, create a few safe defaults
    if (anchors.length === 0) {
      const defaults = [
        { text: "Dashboard", href: "/dashboard" },
        { text: "Smart Analyzer", href: "/smart-analyzer/" },
        { text: "Users", href: "/users" },
        { text: "Logout", href: "/logout" },
      ];
      defaults.forEach((d) => {
        const a = document.createElement("a");
        a.href = d.href;
        a.className =
          "py-2 border-b border-gray-700 text-white hover:text-yellow-300";
        a.textContent = d.text;
        mobileMenu.appendChild(a);
      });
      return;
    }

    anchors.forEach((a) => {
      const clone = a.cloneNode(true);
      // normalize classes for mobile menu appearance
      clone.classList.remove(
        "nav-link",
        "font-semibold",
        "text-lg",
        "hover:text-blue-600",
        "underline",
        "text-yellow-500"
      );
      clone.classList.add(
        "py-2",
        "border-b",
        "border-gray-700",
        "text-white",
        "hover:text-yellow-300"
      );
      mobileMenu.appendChild(clone);
    });
  }

  populateMobileMenu();

  // Accessibility attributes
  toggle.setAttribute("aria-controls", "mobileMenu");
  toggle.setAttribute(
    "aria-expanded",
    String(!mobileMenu.classList.contains("hidden"))
  );

  // Toggle handler
  toggle.addEventListener("click", (e) => {
    e.stopPropagation();
    mobileMenu.classList.toggle("hidden");
    const isOpen = !mobileMenu.classList.contains("hidden");
    toggle.setAttribute("aria-expanded", String(isOpen));
  });

  // Close when clicking outside
  document.addEventListener("click", (e) => {
    if (
      !mobileMenu.classList.contains("hidden") &&
      !mobileMenu.contains(e.target) &&
      !toggle.contains(e.target)
    ) {
      mobileMenu.classList.add("hidden");
      toggle.setAttribute("aria-expanded", "false");
    }
  });

  // Close on ESC
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && !mobileMenu.classList.contains("hidden")) {
      mobileMenu.classList.add("hidden");
      toggle.setAttribute("aria-expanded", "false");
      toggle.focus();
    }
  });

  // Close menu on link click and ensure navigation works
  mobileMenu.querySelectorAll("a").forEach((link) => {
    link.addEventListener("click", () => {
      if (!mobileMenu.classList.contains("hidden")) {
        mobileMenu.classList.add("hidden");
        toggle.setAttribute("aria-expanded", "false");
      }
    });
  });
});
