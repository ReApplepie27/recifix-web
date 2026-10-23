function toggleDashboardPassword(inputId, button) {

    const input =
        document.getElementById(inputId);

    if (!input) {
        return;
    }

    const showingPassword =
        input.type === "text";

    input.type = showingPassword ? "password" : "text";
    button.setAttribute(
        "aria-label",
        showingPassword ? "Show password" : "Hide password"
    );

}

document.addEventListener("DOMContentLoaded", function () {

    const themeToggle =
        document.querySelector(".theme-toggle");

    const currentView =
        new URLSearchParams(window.location.search).get("view");

    const activeView = ["pantry", "saved", "contact"].includes(currentView)
        ? currentView
        : "home";

    const pantryDashboard =
        document.querySelector(".dashboard-pantry");

    const homeDashboard =
        document.querySelector(".dashboard-home");

    const savedDashboard =
        document.querySelector(".dashboard-saved");

    const contactDashboard =
        document.querySelector(".dashboard-contact");

    const dashboardPage =
        document.querySelector(".dashboard-page");

    const homeLink =
        document.querySelector('.sidebar-nav a[href="dashboard.html?view=home"]');

    const pantryLink =
        document.querySelector('.sidebar-nav a[href="dashboard.html?view=pantry"]');

    const savedLink =
        document.querySelector('.sidebar-nav a[href="dashboard.html?view=saved"]');

    const contactLink =
        document.querySelector('.sidebar-nav a[href="dashboard.html?view=contact"]');

    const openPantryAction =
        document.querySelector(".home-dashboard-action");

    const generateRecipeButton =
        document.getElementById("generateRecipe");

    const pantryRecipeShowcase =
        document.getElementById("pantryRecipeShowcase");

    setDashboardView(activeView, false);

    function switchDashboardView(view) {

        dashboardPage.classList.add("view-switching");

        window.setTimeout(function () {

            setDashboardView(view, true);

            window.requestAnimationFrame(function () {
                dashboardPage.classList.remove("view-switching");
            });

        }, 180);

    }

    homeLink.addEventListener("click", function (event) {
        event.preventDefault();
        switchDashboardView("home");
    });

    pantryLink.addEventListener("click", function (event) {
        event.preventDefault();
        switchDashboardView("pantry");

    });

    savedLink.addEventListener("click", function (event) {
        event.preventDefault();
        switchDashboardView("saved");
    });

    contactLink.addEventListener("click", function (event) {
        event.preventDefault();
        switchDashboardView("contact");
    });

    openPantryAction.addEventListener("click", function (event) {
        event.preventDefault();
        switchDashboardView("pantry");
    });

    window.addEventListener("popstate", function () {
        const view = new URLSearchParams(window.location.search).get("view");
        setDashboardView(["pantry", "saved", "contact"].includes(view) ? view : "home", false);
    });

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

    const ingredientInput =
        document.getElementById("ingredientInput");

    const addIngredientButton =
        document.getElementById("addIngredient");

    const ingredientTags =
        document.getElementById("ingredientTags");

    const clearIngredientsButton =
        document.getElementById("clearIngredients");

    const profileButton =
        document.getElementById("profileButton");

    const logoutModal =
        document.getElementById("logoutModal");

    const closeLogoutButton =
        document.getElementById("closeLogout");

    const cancelLogoutButton =
        document.getElementById("cancelLogout");

    const profileGreeting =
        document.getElementById("profileGreeting");

    const profileInitial =
        document.getElementById("profileInitial");

    const accountTitle =
        document.getElementById("accountTitle");

    const accountEmail =
        document.getElementById("accountEmail");

    const accountAvatar =
        document.getElementById("accountAvatar");

    const openAccountSettingsButton =
        document.getElementById("openAccountSettings");

    const openChangePasswordButton =
        document.getElementById("openChangePassword");

    const accountSettingsForm =
        document.getElementById("accountSettingsForm");

    const changePasswordForm =
        document.getElementById("changePasswordForm");

    const dashboardCurrentPassword =
        document.getElementById("dashboardCurrentPassword");

    const changePasswordMessage =
        document.getElementById("changePasswordMessage");

    const cancelAccountSettingsButton =
        document.getElementById("cancelAccountSettings");

    const cancelChangePasswordButton =
        document.getElementById("cancelChangePassword");

    const queryUser =
        new URLSearchParams(window.location.search);

    let storedUser = {};

    try {
        storedUser = JSON.parse(
            localStorage.getItem("recifix-user") || "{}"
        ) || {};
    } catch {}

    if (typeof storedUser !== "object") {
        storedUser = {};
    }

    if (Object.prototype.hasOwnProperty.call(storedUser, "password")) {
        delete storedUser.password;
        localStorage.setItem("recifix-user", JSON.stringify(storedUser));
    }

    const accountNameInput =
        document.getElementById("accountNameInput");

    const accountEmailInput =
        document.getElementById("accountEmailInput");

    let accountName =
        storedUser.name || "Your account";

    let accountEmailAddress =
        storedUser.email || "";

    function renderAccountDetails() {

        const hasName =
            accountName !== "Your account";

        const initial =
            hasName
                ? accountName.charAt(0).toUpperCase()
                : "?";

        profileGreeting.textContent =
            hasName
                ? "Hi, " + accountName.split(" ")[0]
                : "Hi";

        profileInitial.textContent = initial;
        accountTitle.textContent = accountName;
        accountEmail.textContent = accountEmailAddress || "Email not set";
        accountAvatar.textContent = initial;
        accountNameInput.value = hasName ? accountName : "";
        accountEmailInput.value = accountEmailAddress;

    }

    function applyUser(user) {

        accountName = user.name;
        accountEmailAddress = user.email;

        localStorage.setItem(
            "recifix-user",
            JSON.stringify({ name: user.name, email: user.email })
        );

        renderAccountDetails();

    }

    function sessionExpired() {

        localStorage.removeItem("recifix-user");
        window.location.replace("pages/login.html");

    }

    renderAccountDetails();

    recifixApi("/api/auth/me").then(function (result) {

        if (result.status === 401) {
            sessionExpired();
            return;
        }

        if (result.ok) {
            applyUser(result.data.user);
        }

    });

    function closeLogoutModal() {

        logoutModal.classList.remove("show");

        logoutModal.setAttribute("aria-hidden", "true");

    }

    profileButton.addEventListener("click", function () {

        logoutModal.classList.add("show");

        logoutModal.setAttribute("aria-hidden", "false");

    });

    closeLogoutButton.addEventListener(
        "click",
        closeLogoutModal
    );

    cancelLogoutButton.addEventListener(
        "click",
        closeLogoutModal
    );

    openAccountSettingsButton.addEventListener("click", function () {

        accountSettingsForm.hidden = false;
        changePasswordForm.hidden = true;
        openAccountSettingsButton.hidden = true;
        openChangePasswordButton.hidden = true;

    });

    openChangePasswordButton.addEventListener("click", function () {

        accountSettingsForm.hidden = true;
        changePasswordForm.hidden = false;
        openAccountSettingsButton.hidden = true;
        openChangePasswordButton.hidden = true;
        changePasswordForm.reset();
        recifixShowMessage(changePasswordMessage, "");
        dashboardCurrentPassword.focus();

    });

    cancelAccountSettingsButton.addEventListener("click", function () {

        accountSettingsForm.hidden = true;
        changePasswordForm.hidden = true;
        openAccountSettingsButton.hidden = false;
        openChangePasswordButton.hidden = false;

    });

    cancelChangePasswordButton.addEventListener("click", function () {

        changePasswordForm.hidden = true;
        accountSettingsForm.hidden = true;
        openAccountSettingsButton.hidden = false;
        openChangePasswordButton.hidden = false;

    });

    const accountSettingsMessage =
        document.createElement("p");

    accountSettingsMessage.className = "account-settings-message";
    accountSettingsMessage.setAttribute("role", "status");

    accountSettingsForm.insertBefore(
        accountSettingsMessage,
        accountSettingsForm.querySelector(".account-settings-actions")
    );

    accountSettingsForm.addEventListener("input", function () {
        recifixShowMessage(accountSettingsMessage, "");
    });

    async function saveAccountSettings() {

        const saveButton =
            accountSettingsForm.querySelector(".confirm-logout");

        const name = accountNameInput.value.trim();
        const email = accountEmailInput.value.trim();

        if (!name || !email) {
            recifixShowMessage(accountSettingsMessage, "Name and email are required.");
            return;
        }

        saveButton.disabled = true;

        const result = await recifixApi("/api/account", {
            method: "PATCH",
            body: { name: name, email: email }
        });

        saveButton.disabled = false;

        if (result.status === 401) {
            sessionExpired();
            return;
        }

        if (!result.ok) {
            recifixShowMessage(
                accountSettingsMessage,
                result.data.error || "Could not save your changes."
            );
            return;
        }

        applyUser(result.data.user);
        recifixShowMessage(accountSettingsMessage, "Changes saved.", true);

    }

    accountSettingsForm.addEventListener("submit", function (event) {
        event.preventDefault();
        saveAccountSettings();
    });

    accountSettingsForm
        .querySelector(".confirm-logout")
        .addEventListener("click", saveAccountSettings);

    async function saveNewPassword() {

        const saveButton =
            changePasswordForm.querySelector(".confirm-logout");

        const currentPassword = dashboardCurrentPassword.value;

        const newPassword =
            document.getElementById("dashboardNewPassword").value;

        const confirmPassword =
            document.getElementById("dashboardConfirmPassword").value;

        if (!currentPassword) {
            recifixShowMessage(changePasswordMessage, "Enter your current password.");
            return;
        }

        if (newPassword.length < 8) {
            recifixShowMessage(changePasswordMessage, "New password must be at least 8 characters.");
            return;
        }

        if (newPassword !== confirmPassword) {
            recifixShowMessage(changePasswordMessage, "The new passwords don't match.");
            return;
        }

        saveButton.disabled = true;

        const result = await recifixApi("/api/account/password", {
            method: "POST",
            body: {
                current_password: currentPassword,
                new_password: newPassword
            }
        });

        saveButton.disabled = false;

        if (result.status === 401) {
            sessionExpired();
            return;
        }

        if (!result.ok) {
            recifixShowMessage(
                changePasswordMessage,
                result.data.error || "Could not update your password."
            );
            return;
        }

        changePasswordForm.reset();
        recifixShowMessage(changePasswordMessage, "Password updated.", true);

    }

    changePasswordForm.addEventListener("submit", function (event) {
        event.preventDefault();
        saveNewPassword();
    });

    changePasswordForm
        .querySelector(".confirm-logout")
        .addEventListener("click", saveNewPassword);

    const confirmLogoutButton =
        document.getElementById("confirmLogout");

    confirmLogoutButton.addEventListener("click", async function () {

        confirmLogoutButton.disabled = true;

        await recifixApi("/api/auth/logout", { method: "POST" });

        localStorage.removeItem("recifix-user");
        window.location.replace("index.html");

    });

    logoutModal.addEventListener("click", function (event) {

        if (event.target === logoutModal) {

            closeLogoutModal();

        }

    });

    function addIngredient() {

        const value =
            ingredientInput.value.trim();

        if (value === "") {

            ingredientInput.focus();

            return;

        }

        const existingTags =
            ingredientTags.querySelectorAll(
                ".ingredient-tag"
            );

        const alreadyExists =
            Array.from(existingTags).some(
                function (tag) {

                    const ingredientName =
                        tag.firstChild
                            .textContent
                            .trim();

                    return (
                        ingredientName.toLowerCase() ===
                        value.toLowerCase()
                    );

                }
            );

        if (alreadyExists) {

            ingredientInput.value = "";

            ingredientInput.focus();

            return;

        }

        const tag =
            document.createElement("button");

        tag.type = "button";

        tag.className =
            "ingredient-tag";

        const ingredientName =
            value.charAt(0).toUpperCase() +
            value.slice(1);

        const text =
            document.createTextNode(
                ingredientName
            );

        const remove =
            document.createElement("span");

        remove.className =
            "remove-tag";

        remove.textContent =
            "×";

        tag.appendChild(text);

        tag.appendChild(remove);

        ingredientTags.appendChild(tag);

        clearIngredientsButton.disabled = false;

        ingredientInput.value = "";

        ingredientInput.focus();

    }

    addIngredientButton.addEventListener(
        "click",
        addIngredient
    );

    ingredientInput.addEventListener(
        "keydown",
        function (event) {

            if (event.key === "Enter") {

                event.preventDefault();

                addIngredient();

            }

        }
    );

    ingredientTags.addEventListener(
        "click",
        function (event) {

            if (
                event.target.classList.contains(
                    "remove-tag"
                )
            ) {

                event.preventDefault();

                event.stopPropagation();

                event.target.closest(
                    ".ingredient-tag"
                ).remove();

                clearIngredientsButton.disabled =
                    ingredientTags.querySelector(
                        ".ingredient-tag"
                    ) === null;

                return;

            }

            const tag =
                event.target.closest(
                    ".ingredient-tag"
                );

            if (!tag) {

                return;

            }

        }
    );

    clearIngredientsButton.addEventListener(
        "click",
        function () {

            ingredientTags.replaceChildren();

            clearIngredientsButton.disabled = true;

        }
    );

    const filterPills =
        document.querySelectorAll(
            ".filter-pill"
        );

    const filterToneByName = {
        spicy: "tone-coral",
        savory: "tone-savory",
        sweet: "tone-gold",
        mild: "tone-blue",
        tangy: "tone-coral",
        sour: "tone-gold",
        nuts: "tone-nuts",
        dairy: "tone-dairy",
        eggs: "tone-eggs",
        seafood: "tone-seafood",
        gluten: "tone-gluten",
        soy: "tone-soy",
        shellfish: "tone-shellfish",
        sesame: "tone-sesame",
        breakfast: "tone-gold",
        lunch: "tone-lunch",
        dinner: "tone-night",
        dessert: "tone-pink"
    };

    filterPills.forEach(function (pill) {

        const tone =
            filterToneByName[
                pill.textContent.trim().toLowerCase()
            ];

        if (tone) {

            pill.classList.add(tone);

        }

    });

    filterPills.forEach(
        function (pill) {

            pill.addEventListener(
                "click",
                function () {

                    const group =
                        pill.closest(
                            ".filter-group"
                        );

                    const heading =
                        group.querySelector(
                            "h2"
                        ).textContent.trim();

                    if (
                        heading === "Taste Preference" ||
                        heading === "Meal Type"
                    ) {

                        const wasSelected =
                            pill.classList.contains(
                                "selected"
                            );

                        group
                            .querySelectorAll(
                                ".filter-pill"
                            )
                            .forEach(
                                function (otherPill) {

                                    otherPill.classList.remove(
                                        "selected"
                                    );

                                }
                            );

                        if (!wasSelected) {

                            pill.classList.add(
                                "selected"
                            );

                        }

                        return;

                    }

                    pill.classList.toggle(
                        "selected"
                    );

                }
            );

        }
    );

    const adoboRecipeModal =
        document.getElementById("adoboRecipeModal");

    const closeAdoboRecipe =
        document.getElementById("closeAdoboRecipe");

    function setAdoboRecipeModal(open) {
        adoboRecipeModal.classList.toggle("is-open", open);
        adoboRecipeModal.setAttribute("aria-hidden", String(!open));
        document.body.classList.toggle("recipe-modal-open", open);
    }

    window.recifixSetRecipeModal = setAdoboRecipeModal;

    closeAdoboRecipe.addEventListener("click", function () {
        setAdoboRecipeModal(false);
    });

    adoboRecipeModal.addEventListener("click", function (event) {
        if (event.target === adoboRecipeModal) {
            setAdoboRecipeModal(false);
        }
    });

    document.addEventListener("keydown", function (event) {
        if (event.key === "Escape" && adoboRecipeModal.classList.contains("is-open")) {
            setAdoboRecipeModal(false);
        }
    });

    
    function setDashboardView(view, updateUrl) {

        const showHome = view === "home";
        const showPantry = view === "pantry";

        pantryDashboard.hidden = !showPantry;
        homeDashboard.hidden = !showHome;
        savedDashboard.hidden = view !== "saved";
        contactDashboard.hidden = view !== "contact";
        document.documentElement.classList.toggle("home-view", showHome);
        homeLink.classList.toggle("active", showHome);
        pantryLink.classList.toggle("active", showPantry);
        savedLink.classList.toggle("active", view === "saved");
        contactLink.classList.toggle("active", view === "contact");
        document.dispatchEvent(new CustomEvent("recifix:viewchange", { detail: { view: view } }));

        if (updateUrl) {
            window.history.pushState(
                {},
                "",
                "dashboard.html?view=" + view
            );
        }

         //  TIMED AUTOMATED CORRELATION TRIGGER
        if (showHome) {
            window.setTimeout(function() {
                if (typeof loadHomeScreenRecommendations === "function") {
                    loadHomeScreenRecommendations();
                }
            }, 50);
        }
    }   

    // ========================================================
    //  USER HISTORY & SAVED-BASED ML RECIPES FETCHER
    // ========================================================
    async function loadHomeScreenRecommendations() {
        // 🔍 target the correct HTML ID element from your Home view markup
        const homeGrid = document.getElementById("homeRecipeRecommendationsGrid");
        if (!homeGrid) return;

        try {
            const response = await fetch("/api/recipes/recommend", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json"
                },
                body: JSON.stringify({})
            });

            const data = await response.json();

            if (data.error || !data.recipes || data.recipes.length === 0) {
                homeGrid.innerHTML = '<div style="padding: 20px; color: var(--ref-muted, #888); text-align: center;">Save a few recipes to unlock hyper-personalized taste matching choices here!</div>';
                return;
            }

            // Clear the "Querying..." loading placeholder text instantly
            homeGrid.innerHTML = "";

            // Dynamically alter subheadings based on history personalization states
            const subtitleElement = document.querySelector(".ml-recommendations-section p");
            if (subtitleElement) {
                subtitleElement.textContent = data.personalized 
                    ? "Tailored recipe discoveries matching flavors and parameters from your collection."
                    : "Popular recipes matching standard pantry staples in your kitchen right now.";
            }

            data.recipes.forEach(recipe => {
                const card = document.createElement("article");
                card.className = "recipe-card";
                
                const badgeLabel = data.personalized ? "✦ For You" : "✦ Popular Option";
                const badgeBg = data.personalized ? "#e0f2fe" : "#eafaf1";
                const badgeColor = data.personalized ? "#0369a1" : "#2e7d32";

                // Ensure fallback covers missing image values
                const imageSrc = recipe.image ? recipe.image : "images/intro-image.jpg";

                // 🔍 Cleaned up template variable cash handles (\$) and image targets below
                card.innerHTML = `
                    <div style="width: 100%; height: 160px; overflow: hidden; border-radius: 8px; margin-bottom: 14px; background: #f1f5f9;">
                        <img src="${imageSrc}" alt="${recipe.title}" style="width: 100%; height: 100%; object-fit: cover;">
                    </div>
                    <div style="display: flex; justify-content: space-between; align-items: center;">
                        <span style="background: ${badgeBg}; color: ${badgeColor}; font-size: 0.75rem; font-weight: 600; padding: 4px 10px; border-radius: 12px;">
                            ${badgeLabel}
                        </span>
                        <span style="font-size: 0.75rem; color: var(--ref-muted, #718181); font-weight: 600;">
                            ${recipe.match_percentage}% Match
                        </span>
                    </div>
                    <h3 style="margin: 12px 0 6px 0; font-family: 'Playfair Display', serif; font-size: 1.4rem; color: #1e293b;">
                        ${recipe.title}
                    </h3>
                    <p style="font-size: 0.9rem; color: #64748b; line-height: 1.5; margin: 0 0 16px 0;">
                        ${data.personalized ? 'Matches ingredients and flavor profiles from recipes you saved recently.' : 'A classic recipe choice perfectly suited to common household kitchen items.'}
                    </p>
                    <button type="button" class="view-recipe-btn">
                        View Recipe
                    </button>
                `;

                // Safe click listener that handles your built-in popup modal activation flawlessly
                                // Safe click listener that hooks directly into your site's native popup engine!
                                // safe click listener that triggers your app's true native data populator
                const btn = card.querySelector(".view-recipe-btn");
                btn.addEventListener("click", function() {
                    if (typeof window.recifixOpenRecipeModalGlobal === "function") {
                        window.recifixOpenRecipeModalGlobal(recipe.id);
                    } else {
                        alert("The recipe module layout engine is still loading. Please try again in a second!");
                    }
                });

                homeGrid.appendChild(card);
            });

        } catch (error) {
            console.error("Home view personalized ML fetch failure:", error);
            homeGrid.innerHTML = '<div style="color: red; padding: 20px; text-align: center;">Unable to connect to the recommendation engine.</div>';
        }
    }

});
