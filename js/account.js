
const isEmbeddedAuth =
    new URLSearchParams(window.location.search).has("embedded");

const storedUserText =
    localStorage.getItem("recifix-user");

if (storedUserText) {
    try {
        const storedUser = JSON.parse(storedUserText);

        if (
            storedUser &&
            typeof storedUser === "object" &&
            Object.prototype.hasOwnProperty.call(storedUser, "password")
        ) {
            delete storedUser.password;
            localStorage.setItem("recifix-user", JSON.stringify(storedUser));
        }
    } catch {}
}

if (isEmbeddedAuth) {

    document.body.classList.add("auth-embedded");

}

function prepareAuthBackground(frame) {

    const savedScroll =
        localStorage.getItem("recifixReturnScroll");

    if (savedScroll !== null) {

        frame.contentDocument.documentElement.style.scrollBehavior =
            "auto";

        frame.contentWindow.scrollTo({
            top: parseInt(savedScroll, 10),
            left: 0,
            behavior: "instant"
        });

        localStorage.removeItem(
            "recifixReturnScroll"
        );

    }

}

function togglePassword(inputId, button) {

    const input =
        document.getElementById(inputId);

    if (!input) {
        return;
    }

    if (input.type === "password") {

        input.type = "text";

        button.setAttribute("aria-label", "Hide password");

    } else {

        input.type = "password";

        button.setAttribute("aria-label", "Show password");

    }

}

function closeAuth() {

    if (isEmbeddedAuth) {

        window.parent.postMessage(
            { type: "close-auth" },
            "*"
        );

        return;

    }

    const frame =
        document.querySelector(".auth-background iframe");

    if (frame && window.history.length > 1) {

        window.history.back();

        return;

    }

    navigateAfterAuthExit("../index.html");

}

function navigateAfterAuthExit(destination) {

    const wrapper =
        document.querySelector(".auth-wrapper");

    if (wrapper) {

        wrapper.classList.add("closing");

    }

    setTimeout(function () {

        window.location.href = destination;

    }, 320);

}

document.querySelectorAll(".switch-auth a").forEach(function (link) {

    link.addEventListener("click", function (event) {

        event.preventDefault();

        if (isEmbeddedAuth) {

            window.parent.postMessage(
                {
                    type: "switch-auth",
                    href: link.href
                },
                "*"
            );

            return;

        }

        navigateAfterAuthExit(link.href);

    });

});

const authForm =
    document.querySelector(".auth-form");

if (authForm) {

    const isSignup =
        Boolean(authForm.querySelector('input[name="fullname"]'));

    const submitButton =
        authForm.querySelector(".auth-submit");

    const authMessage =
        document.createElement("p");

    authMessage.className = "auth-message";
    authMessage.setAttribute("role", "alert");
    authMessage.hidden = true;

    authForm.insertBefore(authMessage, submitButton);

    const resetStatus =
        new URLSearchParams(window.location.search).get("reset");

    if (resetStatus === "success") {

        recifixShowMessage(
            authMessage,
            "Your password was updated. Log in with your new password.",
            true
        );

    } else if (resetStatus === "invalid") {

        recifixShowMessage(
            authMessage,
            "That reset link is invalid or has expired. Please request a new one."
        );

    }

    authForm.addEventListener("submit", async function (event) {

        event.preventDefault();

        const emailInput =
            authForm.querySelector('input[name="email"]');

        const nameInput =
            authForm.querySelector('input[name="fullname"]');

        const passwordInput =
            authForm.querySelector('input[name="password"]');

        const email = emailInput.value.trim();
        const password = passwordInput.value;
        const fullname = nameInput ? nameInput.value.trim() : "";

        if (isSignup && !fullname) {
            recifixShowMessage(authMessage, "Please enter your full name.");
            return;
        }

        if (!email || !password) {
            recifixShowMessage(authMessage, "Enter your email and password.");
            return;
        }

        if (isSignup && password.length < 8) {
            recifixShowMessage(authMessage, "Password must be at least 8 characters.");
            return;
        }

        recifixShowMessage(authMessage, "");

        const originalLabel = submitButton.textContent;

        submitButton.disabled = true;
        submitButton.textContent =
            isSignup ? "Creating account..." : "Logging in...";

        const result = await recifixApi(
            isSignup ? "/api/auth/signup" : "/api/auth/login",
            {
                method: "POST",
                body: isSignup
                    ? { fullname: fullname, email: email, password: password }
                    : { email: email, password: password }
            }
        );

        if (!result.ok) {

            submitButton.disabled = false;
            submitButton.textContent = originalLabel;

            recifixShowMessage(
                authMessage,
                result.data.error || "Something went wrong. Please try again."
            );

            return;

        }

        localStorage.setItem(
            "recifix-user",
            JSON.stringify({
                name: result.data.user.name,
                email: result.data.user.email
            })
        );

        const dashboardUrl =
            new URL("../dashboard.html", window.location.href).href;

        (window.top || window).location.href = dashboardUrl;

    });

}

const forgotPasswordLink =
    document.getElementById("forgotPasswordLink");

const passwordModal =
    document.getElementById("passwordModal");

const closePasswordModalButton =
    document.getElementById("closePasswordModal");

const forgotPasswordForm =
    document.getElementById("forgotPasswordForm");

if (forgotPasswordLink && passwordModal && closePasswordModalButton) {

    function closePasswordModal() {
        passwordModal.classList.remove("show");
        passwordModal.setAttribute("aria-hidden", "true");
    }

    forgotPasswordLink.addEventListener("click", function (event) {
        event.preventDefault();
        passwordModal.classList.add("show");
        passwordModal.setAttribute("aria-hidden", "false");
    });

    closePasswordModalButton.addEventListener("click", closePasswordModal);

    passwordModal.addEventListener("click", function (event) {
        if (event.target === passwordModal) {
            closePasswordModal();
        }
    });

    if (forgotPasswordForm) {

        const resetSubmit =
            forgotPasswordForm.querySelector(".auth-submit");

        const resetMessage =
            document.createElement("p");

        resetMessage.className = "auth-message";
        resetMessage.setAttribute("role", "alert");
        resetMessage.hidden = true;

        forgotPasswordForm.insertBefore(resetMessage, resetSubmit);

        forgotPasswordForm.addEventListener("submit", async function (event) {

            event.preventDefault();

            const email =
                document.getElementById("resetEmail").value.trim();

            const newPassword =
                document.getElementById("resetPassword").value;

            const confirmPassword =
                document.getElementById("resetPasswordConfirm").value;

            if (!email) {
                recifixShowMessage(resetMessage, "Enter your account email.");
                return;
            }

            if (newPassword.length < 8) {
                recifixShowMessage(resetMessage, "Password must be at least 8 characters.");
                return;
            }

            if (newPassword !== confirmPassword) {
                recifixShowMessage(resetMessage, "The passwords don't match.");
                return;
            }

            resetSubmit.disabled = true;

            const result = await recifixApi("/api/auth/forgot-password", {
                method: "POST",
                body: { email: email, new_password: newPassword }
            });

            resetSubmit.disabled = false;

            if (!result.ok) {
                recifixShowMessage(
                    resetMessage,
                    result.data.error || "Something went wrong. Please try again."
                );
                return;
            }

            forgotPasswordForm.reset();

            recifixShowMessage(
                resetMessage,
                result.data.message ||
                    "Check your email for a link to confirm the new password.",
                true
            );

        });

    }

}

