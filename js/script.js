if (window.self !== window.top) {

    document.documentElement.classList.add("auth-background-mode");

}

document.addEventListener("DOMContentLoaded", function () {

    const themeToggle =
        document.querySelector(".theme-toggle");

    const savedTheme =
        localStorage.getItem("recifix-theme");

    const initialTheme =
        savedTheme === "dark"
            ? "dark"
            : "light";

    function updateThemeButton() {

        const darkMode =
            document.body.classList.contains("dark-mode");

        document.documentElement.classList.toggle(
            "dark-mode",
            darkMode
        );

        themeToggle.setAttribute(
            "aria-pressed",
            String(darkMode)
        );

        themeToggle.setAttribute(
            "aria-label",
            darkMode
                ? "Switch to light mode"
                : "Switch to dark mode"
        );

        themeToggle.querySelector("img").src =
            darkMode
                ? "images/icons/darkmode.svg"
                : "images/icons/lightmode.svg";

    }

    document.body.classList.toggle(
        "dark-mode",
        initialTheme === "dark"
    );

    localStorage.setItem(
        "recifix-theme",
        initialTheme
    );

    if (initialTheme === "dark") {

        document.body.classList.add("dark-mode");

    }

    updateThemeButton();

    themeToggle.addEventListener("click", function () {

        document.body.classList.toggle("dark-mode");

        localStorage.setItem(
            "recifix-theme",
            document.body.classList.contains("dark-mode")
                ? "dark"
                : "light"
        );

        updateThemeButton();

    });

    const cards = document.querySelectorAll(
        ".feature-card, .process-step, .benefit-card, .recipe-card"
    );

    const authLinks = document.querySelectorAll(
        'a[href="pages/signup.html"], a[href="pages/login.html"]'
    );

    authLinks.forEach(function (link) {

        link.addEventListener("click", function (event) {

            event.preventDefault();

            const authFrame =
                document.createElement("iframe");

            const authBackdrop =
                document.createElement("div");

            authBackdrop.className = "auth-modal-backdrop";

            authBackdrop.style.position = "fixed";
            authBackdrop.style.inset = "0";
            authBackdrop.style.zIndex = "1999";

            document.body.appendChild(authBackdrop);

            document.body.classList.add("auth-modal-open");

            authFrame.src =
                link.href + "?embedded=1";

            authFrame.title = "Recifix authentication";

            authFrame.style.position = "fixed";
            authFrame.style.inset = "0";
            authFrame.style.width = "100%";
            authFrame.style.height = "100%";
            authFrame.style.border = "none";
            authFrame.style.zIndex = "2000";

            authFrame.className = "auth-modal-frame";

            document.body.appendChild(authFrame);

        });

    });

    window.addEventListener("message", function (event) {

        if (!event.data || !event.data.type) {
            return;
        }

        const authFrame =
            document.querySelector(".auth-modal-frame");

        const isTrustedOrigin =
            event.origin === window.location.origin ||
            (window.location.protocol === "file:" && event.origin === "null");

        if (
            !authFrame ||
            event.source !== authFrame.contentWindow ||
            !isTrustedOrigin
        ) {
            return;
        }

        if (event.data.type === "close-auth") {

            const savedThemeAfterAuth =
                localStorage.getItem("recifix-theme");

            document.body.classList.toggle(
                "dark-mode",
                savedThemeAfterAuth === "dark"
            );

            authFrame.remove();

            const authBackdrop =
                document.querySelector(".auth-modal-backdrop");

            if (authBackdrop) {
                authBackdrop.remove();
            }

            document.body.classList.remove("auth-modal-open");

        }

        if (event.data.type === "switch-auth") {

            let authUrl;

            try {
                authUrl = new URL(event.data.href, window.location.href);
            } catch {
                return;
            }

            const allowedAuthPages = [
                "pages/login.html",
                "pages/signup.html"
            ].map(function (path) {
                return new URL(path, window.location.href);
            });

            const isAllowedAuthPage = allowedAuthPages.some(function (page) {
                return (
                    page.origin === authUrl.origin &&
                    page.pathname === authUrl.pathname
                );
            });

            if (
                !isAllowedAuthPage
            ) {
                return;
            }

            authUrl.search = "";
            authUrl.searchParams.set("embedded", "1");
            authFrame.src = authUrl.href;

        }

    });

    const observer = new IntersectionObserver(
        function (entries) {

            entries.forEach(function (entry) {

                if (entry.isIntersecting) {

                    entry.target.classList.add("show");

                    observer.unobserve(entry.target);

                }

            });

        },
        {
            threshold: 0.15
        }
    );

    cards.forEach(function (card, index) {

        card.classList.add("hidden");

        card.style.transitionDelay =
            (index * 0.07) + "s";

        observer.observe(card);

    });

    const navLinks = document.querySelectorAll(
        '.navbar nav a[href^="#"]'
    );

    const navSections = Array.from(navLinks)
        .map(function (link) {
            return document.querySelector(link.getAttribute("href"));
        })
        .filter(Boolean);

    function updateActiveNav() {

        const headerOffset = Math.max(90, window.innerHeight * 0.35);
        let activeSection = navSections[0];

        const isAtPageBottom =
            window.innerHeight + window.scrollY >=
            document.documentElement.scrollHeight - 2;

        if (isAtPageBottom) {
            activeSection = navSections[navSections.length - 1];
        }

        if (!isAtPageBottom) {
            navSections.forEach(function (section) {

                if (section.getBoundingClientRect().top <= headerOffset) {
                    activeSection = section;
                }

            });
        }

        navLinks.forEach(function (link) {

            const isActive =
                link.getAttribute("href") === "#" + activeSection.id;

            link.classList.toggle("active", isActive);

            if (isActive) {
                link.setAttribute("aria-current", "page");
            } else {
                link.removeAttribute("aria-current");
            }

        });

    }

    window.addEventListener("scroll", updateActiveNav, {
        passive: true
    });

    updateActiveNav();

    navLinks.forEach(function (link) {

        link.addEventListener("click", function (event) {

            event.preventDefault();

            const targetId =
                link.getAttribute("href");

            const target =
                document.querySelector(targetId);

            if (!target) {
                return;
            }

            if (targetId === "#showcase") {

                const recipeGrid =
                    document.querySelector(".recipe-grid");

                if (recipeGrid) {

                    const gridPosition =
                        recipeGrid.getBoundingClientRect().top
                        + window.scrollY;

                    const gridHeight =
                        recipeGrid.offsetHeight;

                    const scrollPosition =
                        gridPosition
                        - (window.innerHeight / 2)
                        + (gridHeight / 2)
                        - 70;

                    window.scrollTo({

                        top: Math.max(
                            0,
                            scrollPosition
                        ),

                        behavior: "smooth"

                    });

                    return;
                }
            }

            target.scrollIntoView({

                behavior: "smooth",

                block: "center"

            });

        });

    });

});