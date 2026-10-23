/*
 * Recifix dashboard: pantry recipe search, recipe details and saved recipes.
 *
 * Talks to the backend (backend/recipes.py):
 *   GET    /api/recipes/search     GET /api/recipes/<id>
 *   GET    /api/saved              PUT/DELETE /api/saved/<id>
 *   GET    /api/ingredients/suggest
 *
 * All recipe text is inserted with textContent (never innerHTML), so recipe data
 * can't inject markup into the page.
 */
(function () {

    "use strict";

    const PAGE_SIZE = 10;

    const MEAL_LABELS = {
        breakfast: "Breakfast",
        lunch: "Lunch",
        dinner: "Dinner",
        snack: "Snack",
        dessert: "Dessert"
    };

    document.addEventListener("DOMContentLoaded", function () {

        const generateButton = document.getElementById("generateRecipe");
        const showcase = document.getElementById("pantryRecipeShowcase");
        const note = document.getElementById("pantryNote");
        const heading = document.getElementById("pantrySuggestionsHeading");
        const headingSub = document.getElementById("pantrySuggestionsSub");
        const grid = document.getElementById("pantryRecipeGrid");
        const loadMoreButton = document.getElementById("pantryLoadMore");
        const ingredientTags = document.getElementById("ingredientTags");
        const ingredientInput = document.getElementById("ingredientInput");
        const suggestionList = document.getElementById("ingredientSuggestions");
        const savedGrid = document.getElementById("savedRecipeGrid");
        const savedCount = document.querySelector(".saved-recipes-count strong");
        const savedDashboard = document.querySelector(".dashboard-saved");
        const modal = document.getElementById("adoboRecipeModal");

        if (!generateButton || !showcase || !grid || !modal) {
            return;
        }

        const savedIds = new Set();
        let lastParams = null;
        let shownCount = 0;
        let totalCount = 0;
        let searchToken = 0;

        // ------------------------------------------------------------ helpers
        function el(tag, className, text) {

            const node = document.createElement(tag);

            if (className) {
                node.className = className;
            }

            if (text !== undefined && text !== null) {
                node.textContent = text;
            }

            return node;

        }

        function icon(name) {

            const img = document.createElement("img");

            img.src = "images/icons/" + name + ".svg";
            img.alt = "";

            return img;

        }

        function capitalize(text) {
            return text ? text.charAt(0).toUpperCase() + text.slice(1) : "";
        }

        function formatMinutes(n) {

            if (n === null || n === undefined) {
                return "";
            }

            if (n < 60) {
                return n + " min";
            }

            if (n < 1440) {

                const hours = Math.floor(n / 60);
                const mins = n % 60;

                return hours + " h" + (mins ? " " + mins + " min" : "");

            }

            const days = Math.round(n / 1440 * 10) / 10;

            return days + (days === 1 ? " day" : " days");

        }

        function sessionExpired() {
            window.location.replace("pages/login.html");
        }

        function setNote(messages) {

            const text = messages.filter(Boolean).join(" ");

            note.textContent = text;
            note.hidden = !text;

        }

        function reveal() {

            showcase.hidden = false;
            showcase.classList.add("is-revealed");
            generateButton.setAttribute("aria-expanded", "true");

        }

        // ------------------------------------------------------- card pieces
        function placeholder(recipe) {

            const box = el("div", "recipe-image-placeholder");

            box.setAttribute("role", "img");
            box.setAttribute("aria-label", "No photo yet for " + recipe.name);
            box.appendChild(el("span", "", recipe.name.charAt(0).toUpperCase()));

            return box;

        }

        function imageNode(recipe) {

            if (!recipe.image) {
                return placeholder(recipe);
            }

            const img = document.createElement("img");

            img.src = recipe.image;
            img.alt = recipe.name;
            img.loading = "lazy";

            img.addEventListener("error", function () {
                if (img.parentNode) {
                    img.parentNode.replaceChild(placeholder(recipe), img);
                }
            });

            return img;

        }

        // Which meal to show on a card: the one the user filtered for, otherwise the most specific.
        const MEAL_PRIORITY = ["breakfast", "lunch", "dinner", "dessert", "snack"];

        function mealTag(recipe, preferred) {

            const meals = recipe.meals || [];

            if (preferred && meals.indexOf(preferred) !== -1) {
                return [MEAL_LABELS[preferred], preferred];
            }

            if (meals.indexOf("lunch") !== -1 && meals.indexOf("dinner") !== -1) {
                return ["Lunch / Dinner", "dinner"];
            }

            for (let i = 0; i < MEAL_PRIORITY.length; i++) {
                if (meals.indexOf(MEAL_PRIORITY[i]) !== -1) {
                    return [MEAL_LABELS[MEAL_PRIORITY[i]], MEAL_PRIORITY[i]];
                }
            }

            return [recipe.meal_course, "main"];

        }

        function tagsNode(recipe, preferredMeal) {

            const tags = el("div", "pantry-recipe-tags");
            const meal = mealTag(recipe, preferredMeal);

            tags.appendChild(el("span", "recipe-meal-" + meal[1], meal[0]));

            (recipe.flavors || []).slice(0, 2).forEach(function (flavor) {
                tags.appendChild(el("span", "recipe-taste-" + flavor, capitalize(flavor)));
            });

            return tags;

        }

        function metaNode(recipe) {

            const meta = el("div", "pantry-recipe-meta");

            function stat(iconName, label, value) {

                const span = el("span");

                span.appendChild(icon(iconName));
                span.appendChild(el("strong", "", label));
                span.appendChild(document.createTextNode(" " + value));
                meta.appendChild(span);

            }

            if (recipe.prep_minutes !== null) {
                stat("recipe-prep", "Prep", formatMinutes(recipe.prep_minutes));
            }

            if (recipe.cook_minutes !== null) {
                stat("recipe-cook", "Cook", formatMinutes(recipe.cook_minutes));
            }

            stat("recipe-servings", "Serves", String(recipe.servings));

            if (recipe.difficulty) {

                const level = recipe.difficulty.toLowerCase();
                const span = el("span", "recipe-difficulty");
                const bars = el("i", "difficulty-bars " + level);

                bars.setAttribute("aria-label", recipe.difficulty + " difficulty");
                bars.appendChild(document.createElement("b"));
                bars.appendChild(document.createElement("b"));
                bars.appendChild(document.createElement("b"));

                span.appendChild(icon("recipe-difficulty"));
                span.appendChild(el("strong", "", recipe.difficulty));
                span.appendChild(bars);
                meta.appendChild(span);

            }

            return meta;

        }

        function matchNode(recipe) {

            const match = recipe.match;

            if (!match) {
                return null;
            }

            const box = el("div", "recipe-match");
            const have = match.have.length;

            if (!match.required) {

                box.appendChild(el("span", "recipe-match-badge is-complete", "Everything you need"));
                return box;

            }

            const badge = el(
                "span",
                "recipe-match-badge" + (match.percent === 100 ? " is-complete" : ""),
                match.percent === 100
                    ? "You have everything"
                    : "You have " + have + " of " + match.required
            );

            box.appendChild(badge);

            if (match.missing.length) {

                const shown = match.missing.slice(0, 4).join(", ");
                const more = match.missing.length > 4 ? " +" + (match.missing.length - 4) + " more" : "";

                box.appendChild(el("span", "recipe-match-missing", "Still need: " + shown + more));

            }

            return box;

        }

        function allergenText(recipe) {

            if (!recipe.allergens_verified) {
                return "Allergen info not verified";
            }

            const contains = recipe.allergens.filter(function (a) { return a.level === "contains"; });
            const may = recipe.allergens.filter(function (a) { return a.level === "may"; });
            const parts = [];

            if (contains.length) {
                parts.push("Contains " + contains.map(function (a) { return a.label.toLowerCase(); }).join(", "));
            }

            if (may.length) {
                parts.push("may contain " + may.map(function (a) { return a.label.toLowerCase(); }).join(", "));
            }

            return parts.length ? parts.join(" · ") : "No common allergens listed";

        }

        function setSaveButton(button, saved) {

            button.classList.toggle("is-saved", saved);
            button.setAttribute("aria-pressed", String(saved));
            button.setAttribute("aria-label", saved ? "Remove saved recipe" : "Save recipe");
            button.lastChild.textContent = saved ? " Saved Recipe" : " Save Recipe";

        }

        function actionsNode(recipe, withArrow) {

            const wrap = el("div", "pantry-recipe-actions");
            const view = el("button", "pantry-view-recipe");
            const save = el("button", "pantry-save-recipe");

            view.type = "button";
            view.dataset.viewId = recipe.id;
            view.appendChild(icon("eye"));
            view.appendChild(document.createTextNode("View Recipe"));

            if (withArrow) {
                view.appendChild(document.createTextNode(" "));
                view.appendChild(el("span", "", "→")).setAttribute("aria-hidden", "true");
            }

            save.type = "button";
            save.dataset.saveId = recipe.id;
            save.appendChild(icon("saved-recipe-dashboard"));
            save.appendChild(document.createTextNode(" Save Recipe"));
            setSaveButton(save, savedIds.has(recipe.id));

            wrap.appendChild(view);
            wrap.appendChild(save);

            return wrap;

        }

        function appendCommon(container, recipe, withArrow) {

            container.appendChild(tagsNode(recipe, lastParams ? lastParams.meal : ""));
            container.appendChild(el("h3", "", recipe.name));
            container.appendChild(el("p", "", recipe.description));
            container.appendChild(metaNode(recipe));

            const match = matchNode(recipe);

            if (match) {
                container.appendChild(match);
            }

            container.appendChild(el("p", "recipe-allergen-line", allergenText(recipe)));
            container.appendChild(actionsNode(recipe, withArrow));

        }

        function featuredCard(recipe) {

            const card = el("article", "pantry-featured-recipe");
            const image = el("div", "pantry-featured-image");
            const content = el("div", "pantry-featured-content");

            image.appendChild(imageNode(recipe));
            appendCommon(content, recipe, true);
            card.appendChild(image);
            card.appendChild(content);

            return card;

        }

        function smallCard(recipe) {

            const card = el("article", "pantry-small-recipe");
            const image = el("div", "pantry-small-image");
            const content = el("div", "pantry-small-content");

            image.appendChild(imageNode(recipe));
            appendCommon(content, recipe, false);
            card.appendChild(image);
            card.appendChild(content);

            return card;

        }

        // ----------------------------------------------------- pantry search
        function selectedPills(groupTitle) {

            let found = [];

            document.querySelectorAll(".filter-group").forEach(function (group) {

                if (group.querySelector("h2").textContent.trim() === groupTitle) {

                    found = Array.from(group.querySelectorAll(".filter-pill.selected")).map(function (pill) {
                        return pill.textContent.trim().toLowerCase();
                    });

                }

            });

            return found;

        }

        function readControls() {

            const ingredients = Array.from(ingredientTags.querySelectorAll(".ingredient-tag")).map(function (tag) {
                return tag.firstChild.textContent.trim();
            });

            return {
                ingredients: ingredients,
                meal: selectedPills("Meal Type")[0] || "",
                taste: selectedPills("Taste Preference")[0] || "",
                allergens: selectedPills("Allergies / Restrictions")
            };

        }

        function buildQuery(controls, offset) {

            const params = new URLSearchParams();

            if (controls.ingredients.length) { params.set("ingredients", controls.ingredients.join(",")); }
            if (controls.meal) { params.set("meal", controls.meal); }
            if (controls.taste) { params.set("taste", controls.taste); }
            if (controls.allergens.length) { params.set("allergens", controls.allergens.join(",")); }

            params.set("limit", String(PAGE_SIZE));
            params.set("offset", String(offset));

            return params.toString();

        }

        function clearResults() {

            showcase.querySelectorAll(".pantry-featured-recipe").forEach(function (card) { card.remove(); });
            grid.replaceChildren();
            heading.hidden = true;
            loadMoreButton.hidden = true;
            shownCount = 0;
            totalCount = 0;

        }

        function updateLoadMore() {
            loadMoreButton.hidden = shownCount >= totalCount;
        }

        function renderPage(data, append) {

            data.results.forEach(function (recipe) {
                if (recipe.saved) { savedIds.add(recipe.id); } else { savedIds.delete(recipe.id); }
            });

            let list = data.results;

            if (!append) {

                clearResults();

                if (list.length) {

                    showcase.insertBefore(featuredCard(list[0]), heading);
                    list = list.slice(1);

                }

            }

            list.forEach(function (recipe) {
                grid.appendChild(smallCard(recipe));
            });

            shownCount += data.results.length;
            totalCount = data.total;
            heading.hidden = grid.children.length === 0;

            headingSub.textContent =
                totalCount + (totalCount === 1 ? " recipe matches" : " recipes match") +
                " · best matches first";

            updateLoadMore();

        }

        function notesFor(controls, data) {

            const messages = [];

            if (data.unrecognised && data.unrecognised.length) {

                messages.push(
                    "We don't have " + data.unrecognised.join(", ") + " in our recipes yet, so " +
                    (data.unrecognised.length === 1 ? "it was" : "they were") + " left out of the matching."
                );

            }

            if (controls.ingredients.length) {
                messages.push("Salt, pepper, water and cooking oil are assumed to be in your kitchen.");
            }

            if (data.allergen_filter_active) {

                messages.push(
                    "Allergen filter: recipes are hidden if the recipe data or its ingredient list suggests any " +
                    "allergen you selected, including \"may contain\" notes. It can't account for every brand, " +
                    "so always check ingredient labels."
                );

                if (data.unverified_hidden) {
                    messages.push("Recipes with no allergen information are hidden.");
                }

            }

            return messages;

        }

        async function runSearch(offset) {

            const token = ++searchToken;
            const controls = lastParams || readControls();
            const result = await recifixApi("/api/recipes/search?" + buildQuery(controls, offset));

            if (token !== searchToken) {
                return null;
            }

            if (result.status === 401) {
                sessionExpired();
                return null;
            }

            if (!result.ok) {

                reveal();
                clearResults();
                setNote([result.data.error || "Something went wrong while finding recipes. Please try again."]);
                return null;

            }

            return { controls: controls, data: result.data };

        }

        generateButton.addEventListener("click", async function () {

            const controls = readControls();

            reveal();

            if (!controls.ingredients.length && !controls.meal && !controls.taste && !controls.allergens.length) {

                clearResults();
                setNote(["Add at least one ingredient, or choose a meal type or taste, then try again."]);
                return;

            }

            lastParams = controls;
            generateButton.disabled = true;
            generateButton.lastChild.textContent = " Finding recipes…";

            const outcome = await runSearch(0);

            generateButton.disabled = false;
            generateButton.lastChild.textContent = " Generate Recipe";

            if (!outcome) {
                return;
            }

            if (outcome.data.total === 0) {

                clearResults();

                setNote(
                    ["No recipes matched. Try adding more ingredients or removing a filter."]
                        .concat(notesFor(controls, outcome.data))
                );

                return;

            }

            renderPage(outcome.data, false);
            setNote(notesFor(controls, outcome.data));
            showcase.scrollIntoView({ behavior: "smooth", block: "start" });

        });

        loadMoreButton.addEventListener("click", async function () {

            loadMoreButton.disabled = true;

            const outcome = await runSearch(shownCount);

            loadMoreButton.disabled = false;

            if (outcome) {
                renderPage(outcome.data, true);
            }

        });

        // ------------------------------------------------- ingredient hints
        let suggestTimer = null;

        ingredientInput.addEventListener("input", function () {

            window.clearTimeout(suggestTimer);

            const query = ingredientInput.value.trim();

            if (query.length < 2) {
                suggestionList.replaceChildren();
                return;
            }

            suggestTimer = window.setTimeout(async function () {

                const result = await recifixApi("/api/ingredients/suggest?q=" + encodeURIComponent(query));

                if (!result.ok || ingredientInput.value.trim() !== query) {
                    return;
                }

                suggestionList.replaceChildren();

                result.data.suggestions.forEach(function (s) {

                    const option = document.createElement("option");

                    option.value = capitalize(s.name);
                    suggestionList.appendChild(option);

                });

            }, 200);

        });

        // ---------------------------------------------------------- saving
        function syncSaveButtons(id) {

            const saved = savedIds.has(id);

            document.querySelectorAll('.pantry-save-recipe[data-save-id="' + id + '"]').forEach(function (button) {
                setSaveButton(button, saved);
            });

        }

        async function toggleSave(id) {

            const wasSaved = savedIds.has(id);

            if (wasSaved) { savedIds.delete(id); } else { savedIds.add(id); }
            syncSaveButtons(id);

            const result = await recifixApi("/api/saved/" + id, { method: wasSaved ? "DELETE" : "PUT" });

            if (result.status === 401) {
                sessionExpired();
                return;
            }

            if (!result.ok) {

                if (wasSaved) { savedIds.add(id); } else { savedIds.delete(id); }
                syncSaveButtons(id);
                setNote(["We couldn't update your saved recipes. Please try again."]);
                reveal();
                return;

            }

            if (!savedDashboard.hidden) {
                loadSaved();
            }

        }

        function savedCard(recipe, featured) {

            const card = el("article", "saved-recipe-card" + (featured ? " saved-recipe-card-featured" : ""));
            const image = el("div", "saved-recipe-image");
            const heart = el("button", "saved-heart");
            const content = el("div", "saved-recipe-content");
            const footer = el("div", "saved-recipe-footer");
            const open = el("button", "saved-open-recipe");

            image.appendChild(imageNode(recipe));

            heart.type = "button";
            heart.dataset.saveId = recipe.id;
            heart.setAttribute("aria-label", "Remove " + recipe.name + " from saved recipes");
            heart.textContent = "♥";
            image.appendChild(heart);

            content.appendChild(tagsNode(recipe));
            content.appendChild(el("h3", "", recipe.name));
            content.appendChild(el("p", "", recipe.description));

            if (recipe.total_minutes !== null) {
                footer.appendChild(el("span", "", formatMinutes(recipe.total_minutes)));
            }

            if (recipe.difficulty) {
                footer.appendChild(el("span", "", recipe.difficulty));
            }

            open.type = "button";
            open.dataset.viewId = recipe.id;
            open.appendChild(document.createTextNode("View recipe "));
            open.appendChild(el("span", "", "→")).setAttribute("aria-hidden", "true");
            footer.appendChild(open);
            content.appendChild(footer);

            card.appendChild(image);
            card.appendChild(content);

            return card;

        }

        async function loadSaved() {

            const result = await recifixApi("/api/saved");

            if (result.status === 401) {
                sessionExpired();
                return;
            }

            if (!result.ok) {
                savedGrid.replaceChildren(el("p", "saved-empty-state", "We couldn't load your saved recipes. Please refresh the page."));
                return;
            }

            const recipes = result.data.results;

            savedIds.clear();
            recipes.forEach(function (r) { savedIds.add(r.id); });
            savedCount.textContent = String(recipes.length);
            savedGrid.replaceChildren();

            if (!recipes.length) {

                savedGrid.appendChild(el(
                    "p", "saved-empty-state",
                    "Your saved collection is empty. Save a recipe from My Pantry to see it here."
                ));

                return;

            }

            recipes.forEach(function (recipe, index) {
                savedGrid.appendChild(savedCard(recipe, index === 0));
            });

        }

        document.addEventListener("recifix:viewchange", function (event) {

            if (event.detail.view === "saved") {
                loadSaved();
            }

        });

        // ----------------------------------------------------- recipe modal
        const modalHero = modal.querySelector(".recipe-dialog-hero");
        const modalHeroText = modalHero.querySelector("div");
        const modalTitle = document.getElementById("adoboRecipeTitle");
        const modalIngredients = modal.querySelector(".recipe-dialog-ingredients");
        const modalSteps = modal.querySelector(".recipe-dialog-steps");
        const modalAllergens = document.getElementById("recipeAllergensBody");

        function setModalOpen(open) {

            if (typeof window.recifixSetRecipeModal === "function") {
                window.recifixSetRecipeModal(open);
                return;
            }

            modal.classList.toggle("is-open", open);
            modal.setAttribute("aria-hidden", String(!open));
            document.body.classList.toggle("recipe-modal-open", open);

        }

        function modalMetaNode(recipe) {

            const meta = el("div", "recipe-dialog-meta");

            function stat(iconName, label, value) {

                const span = el("span");

                span.appendChild(icon(iconName));
                span.appendChild(document.createTextNode(label + " "));
                span.appendChild(el("strong", "", value));
                meta.appendChild(span);

            }

            if (recipe.prep_minutes !== null) { stat("recipe-prep", "Prep", formatMinutes(recipe.prep_minutes)); }
            if (recipe.cook_minutes !== null) { stat("recipe-cook", "Cook", formatMinutes(recipe.cook_minutes)); }

            stat("recipe-servings", "Serves", String(recipe.servings));

            if (recipe.difficulty) {

                const span = el("span");
                const bars = el("i", "difficulty-bars " + recipe.difficulty.toLowerCase());

                bars.setAttribute("aria-label", recipe.difficulty + " difficulty");
                bars.appendChild(document.createElement("b"));
                bars.appendChild(document.createElement("b"));
                bars.appendChild(document.createElement("b"));

                span.appendChild(icon("recipe-difficulty"));
                span.appendChild(document.createTextNode(recipe.difficulty + " "));
                span.appendChild(bars);
                meta.appendChild(span);

            }

            return meta;

        }

        function fillModal(recipe) {

            const oldMedia = modalHero.querySelector("img, .recipe-image-placeholder");

            modalHero.replaceChild(imageNode(recipe), oldMedia);
            modalHeroText.replaceChildren();

            modalHeroText.appendChild(tagsNode(recipe));

            const title = el("h2", "", recipe.name);

            title.id = "adoboRecipeTitle";
            modalHeroText.appendChild(title);
            modalHeroText.appendChild(el("p", "", recipe.description));

            const meta = modalMetaNode(recipe);

            modalHeroText.appendChild(meta);

            if (recipe.time_notes) {
                modalHeroText.appendChild(el("p", "recipe-time-notes", "Plus: " + recipe.time_notes));
            }

            const actions = el("div", "pantry-recipe-actions");
            const save = el("button", "pantry-save-recipe");

            save.type = "button";
            save.dataset.saveId = recipe.id;
            save.appendChild(icon("saved-recipe-dashboard"));
            save.appendChild(document.createTextNode(" Save Recipe"));
            setSaveButton(save, savedIds.has(recipe.id));
            actions.appendChild(save);
            modalHeroText.appendChild(actions);

            modalIngredients.replaceChildren();

            recipe.ingredients.forEach(function (section) {

                if (section.section) {
                    modalIngredients.appendChild(el("li", "recipe-ingredient-section", section.section));
                }

                section.items.forEach(function (item) {
                    modalIngredients.appendChild(el("li", "", item.text));
                });

            });

            modalSteps.replaceChildren();

            recipe.steps.forEach(function (step) {
                modalSteps.appendChild(el("li", "", step));
            });

            fillAllergens(recipe);

        }

        function chips(items, className) {

            const row = el("div", "allergen-chips");

            items.forEach(function (a) {
                row.appendChild(el("span", className, a.label));
            });

            return row;

        }

        function fillAllergens(recipe) {

            modalAllergens.replaceChildren();

            const contains = recipe.allergens.filter(function (a) { return a.level === "contains"; });
            const may = recipe.allergens.filter(function (a) { return a.level === "may"; });

            if (!recipe.allergens_verified) {
                modalAllergens.appendChild(el(
                    "p", "allergen-warning",
                    "The recipe doesn't list allergen information. The items below are only guesses from the ingredient list."
                ));
            }

            if (contains.length) {
                modalAllergens.appendChild(el("p", "allergen-label", "Contains"));
                modalAllergens.appendChild(chips(contains, "allergen-chip"));
            }

            if (may.length) {
                modalAllergens.appendChild(el("p", "allergen-label", "May contain (conditional, optional or inferred from the ingredients)"));
                modalAllergens.appendChild(chips(may, "allergen-chip is-may"));
            }

            if (!contains.length && !may.length) {
                modalAllergens.appendChild(el("p", "allergen-label", "No common allergens listed."));
            }

            if (recipe.allergen_note) {
                modalAllergens.appendChild(el("p", "allergen-note", "Recipe note: " + recipe.allergen_note));
            }

            modalAllergens.appendChild(el(
                "p", "allergen-disclaimer",
                "This information comes from the recipe data and may be incomplete. Brands and substitutions " +
                "can change what's in a dish, so always check ingredient labels if you have an allergy."
            ));

        }

        async function openRecipe(id) {

            const result = await recifixApi("/api/recipes/" + id);
            if (result.status === 401) {
                sessionExpired();
                return;
            }

            if (!result.ok) {
                reveal();
                setNote(["We couldn't open that recipe. Please try again."]);
                return;
            }

            if (result.data.recipe.saved) { savedIds.add(id); } else { savedIds.delete(id); }

            fillModal(result.data.recipe);
            setModalOpen(true);
            modal.querySelector(".recipe-dialog").scrollTop = 0;

        } 

        window.recifixOpenRecipeModalGlobal = openRecipe;

        // -------------------------------------------- one delegated handler
        document.addEventListener("click", function (event) {

            const view = event.target.closest("[data-view-id]");

            if (view) {
                openRecipe(Number(view.dataset.viewId));
                return;
            }

            const save = event.target.closest("[data-save-id]");

            if (save) {
                toggleSave(Number(save.dataset.saveId));
            }

        });

        if (!savedDashboard.hidden) {
            loadSaved();
        }

    });

}());
