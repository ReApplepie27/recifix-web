-- Recifix MySQL schema (MySQL 8+ / MariaDB 10.5+)
-- Create the database and a dedicated user first (see README.md), then run:
--     python init_db.py

CREATE TABLE IF NOT EXISTS users (
    id            INT UNSIGNED NOT NULL AUTO_INCREMENT,
    full_name     VARCHAR(100)  NOT NULL,
    email         VARCHAR(254)  NOT NULL,
    password_hash VARCHAR(255)  NOT NULL,
    created_at    DATETIME      NOT NULL,
    updated_at    DATETIME      NOT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uq_users_email (email)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- A pending "forgot password" request. The new password only takes effect once
-- the account owner opens the emailed link. Only a SHA-256 of the token is stored.
CREATE TABLE IF NOT EXISTS password_resets (
    id                INT UNSIGNED NOT NULL AUTO_INCREMENT,
    user_id           INT UNSIGNED NOT NULL,
    token_hash        CHAR(64)     NOT NULL,
    new_password_hash VARCHAR(255) NOT NULL,
    expires_at        DATETIME     NOT NULL,
    created_at        DATETIME     NOT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uq_password_resets_token (token_hash),
    KEY idx_password_resets_user (user_id),
    CONSTRAINT fk_password_resets_user
        FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---------------------------------------------------------------------------
-- Recipes (loaded from the spreadsheet by import_recipes.py)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS recipes (
    id                 INT UNSIGNED NOT NULL AUTO_INCREMENT,
    slug               VARCHAR(120)  NOT NULL,
    name               VARCHAR(150)  NOT NULL,
    description        TEXT          NOT NULL,
    meal_course        VARCHAR(40)   NOT NULL,
    difficulty         VARCHAR(10)   NOT NULL DEFAULT '',
    servings           SMALLINT UNSIGNED NOT NULL DEFAULT 2,
    prep_minutes       INT UNSIGNED  NULL,
    cook_minutes       INT UNSIGNED  NULL,
    total_minutes      INT UNSIGNED  NULL,
    time_notes         VARCHAR(600)  NOT NULL DEFAULT '',
    allergen_text      VARCHAR(1000) NOT NULL DEFAULT '',
    allergens_verified TINYINT(1)    NOT NULL DEFAULT 0,
    image              VARCHAR(255)  NULL,
    created_at         DATETIME      NOT NULL,
    updated_at         DATETIME      NOT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uq_recipes_slug (slug),
    KEY idx_recipes_name (name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- One row per ingredient line. match_spec is what pantry matching uses:
-- groups are separated by semicolons (all needed), alternatives inside a group by pipes (any one).
CREATE TABLE IF NOT EXISTS recipe_ingredients (
    id          INT UNSIGNED NOT NULL AUTO_INCREMENT,
    recipe_id   INT UNSIGNED NOT NULL,
    position    SMALLINT UNSIGNED NOT NULL,
    section     VARCHAR(100)  NULL,
    raw         VARCHAR(500)  NOT NULL,
    display     VARCHAR(600)  NOT NULL DEFAULT '',
    match_spec  VARCHAR(1000) NOT NULL DEFAULT '',
    is_optional TINYINT(1)    NOT NULL DEFAULT 0,
    is_staple   TINYINT(1)    NOT NULL DEFAULT 0,
    PRIMARY KEY (id),
    KEY idx_recipe_ingredients_recipe (recipe_id),
    CONSTRAINT fk_recipe_ingredients_recipe
        FOREIGN KEY (recipe_id) REFERENCES recipes (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS recipe_steps (
    id        INT UNSIGNED NOT NULL AUTO_INCREMENT,
    recipe_id INT UNSIGNED NOT NULL,
    position  SMALLINT UNSIGNED NOT NULL,
    body      TEXT NOT NULL,
    PRIMARY KEY (id),
    KEY idx_recipe_steps_recipe (recipe_id),
    CONSTRAINT fk_recipe_steps_recipe
        FOREIGN KEY (recipe_id) REFERENCES recipes (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- kind: meal | flavor | course | occasion | allergen | allergen_may
CREATE TABLE IF NOT EXISTS recipe_tags (
    recipe_id INT UNSIGNED NOT NULL,
    kind      VARCHAR(20)  NOT NULL,
    value     VARCHAR(40)  NOT NULL,
    PRIMARY KEY (recipe_id, kind, value),
    KEY idx_recipe_tags_lookup (kind, value),
    CONSTRAINT fk_recipe_tags_recipe
        FOREIGN KEY (recipe_id) REFERENCES recipes (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS saved_recipes (
    user_id    INT UNSIGNED NOT NULL,
    recipe_id  INT UNSIGNED NOT NULL,
    created_at DATETIME     NOT NULL,
    PRIMARY KEY (user_id, recipe_id),
    KEY idx_saved_recipes_recipe (recipe_id),
    CONSTRAINT fk_saved_user   FOREIGN KEY (user_id)   REFERENCES users (id)   ON DELETE CASCADE,
    CONSTRAINT fk_saved_recipe FOREIGN KEY (recipe_id) REFERENCES recipes (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;