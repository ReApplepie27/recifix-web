/*
 * Tiny fetch wrapper for the Recifix backend (same-origin, cookie session).
 * Always resolves to { ok, status, data } and never throws.
 */
async function recifixApi(path, options) {

    options = options || {};

    const init = {
        method: options.method || "GET",
        credentials: "same-origin",
        headers: {}
    };

    if (options.body !== undefined) {

        init.headers["Content-Type"] = "application/json";
        init.body = JSON.stringify(options.body);

    }

    try {

        const response = await fetch(path, init);

        let data = {};

        try {
            data = await response.json();
        } catch {}

        return { ok: response.ok, status: response.status, data: data };

    } catch {

        return {
            ok: false,
            status: 0,
            data: {
                error: "Can't reach the server. Check your connection and try again."
            }
        };

    }

}

function recifixShowMessage(element, text, isSuccess) {

    if (!element) {
        return;
    }

    element.textContent = text || "";
    element.classList.toggle("is-success", Boolean(isSuccess));

    if (element.classList.contains("auth-message")) {
        element.hidden = !text;
    }

}
