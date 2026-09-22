/* Mini Bazaar - small UI behaviours (no framework).
   Forms post to the server; this file only adds convenience (menu, steppers, checks). */
(function () {
    "use strict";

    function toast(message, isError) {
        var region = document.getElementById("toast-region");
        if (!region) return;
        var el = document.createElement("div");
        el.className = "toast" + (isError ? " toast-error" : "");
        el.textContent = message;
        region.appendChild(el);
        setTimeout(function () { el.remove(); }, 3200);
    }

    /* Mobile menu -------------------------------------------------------- */
    var toggle = document.querySelector(".nav-toggle");
    var menu = document.getElementById("nav-menu");
    if (toggle && menu) {
        toggle.addEventListener("click", function () {
            var open = menu.classList.toggle("is-open");
            toggle.setAttribute("aria-expanded", String(open));
            toggle.setAttribute("aria-label", open ? "Close menu" : "Open menu");
        });
    }

    /* Sort dropdown submits by itself -------------------------------------- */
    document.querySelectorAll("[data-autosubmit]").forEach(function (select) {
        select.addEventListener("change", function () { select.form.submit(); });
    });

    /* "Use my location": asks the browser for the position and fills the coordinate boxes.
       The position is only used to fill the form - nothing is stored by this script. */
    document.querySelectorAll("[data-geolocate]").forEach(function (button) {
        button.addEventListener("click", function () {
            if (!navigator.geolocation) {
                toast("This browser cannot share its location. Please type it in instead.", true);
                return;
            }
            button.classList.add("is-loading");
            navigator.geolocation.getCurrentPosition(function (position) {
                button.classList.remove("is-loading");
                document.getElementById(button.dataset.lat).value = position.coords.latitude.toFixed(6);
                document.getElementById(button.dataset.lng).value = position.coords.longitude.toFixed(6);
                if (button.dataset.submit === "true") {
                    document.getElementById(button.dataset.form).submit();
                } else {
                    toast("Location filled in. Remember to save your changes.");
                }
            }, function (error) {
                button.classList.remove("is-loading");
                toast(error.code === 1
                    ? "Location permission was denied. You can type your location in instead."
                    : "Could not find your location. You can type it in instead.", true);
            }, { timeout: 10000 });
        });
    });

    /* Ask before risky actions: <form data-confirm="Are you sure?"> ------------ */
    document.querySelectorAll("form[data-confirm]").forEach(function (f) {
        f.addEventListener("submit", function (event) {
            if (!window.confirm(f.dataset.confirm)) event.preventDefault();
        });
    });

    /* Quantity steppers ---------------------------------------------------- */
    document.querySelectorAll("[data-stepper]").forEach(function (stepper) {
        var input = stepper.querySelector("[data-qty]");
        stepper.querySelectorAll("[data-step]").forEach(function (button) {
            button.addEventListener("click", function () {
                var max = parseInt(input.dataset.max, 10) || 99;
                var next = parseInt(input.value, 10) + parseInt(button.dataset.step, 10);
                next = Math.max(1, Math.min(next, max));
                if (next === parseInt(input.value, 10) && button.dataset.step === "1") {
                    toast("Only " + max + " available in stock.", true);
                }
                input.value = next;
                stepper.dispatchEvent(new CustomEvent("qtychange", { bubbles: true }));
            });
        });
    });

    /* Checkout form: friendly validation + loading state ------------------- */
    var form = document.getElementById("checkout-form");
    if (form) {
        var rules = {
            full_name: function (v) { return v.trim().length >= 2 ? "" : "Please enter your full name."; },
            phone: function (v) { return /^[6-9]\d{9}$/.test(v.trim()) ? "" : "Enter a valid 10-digit mobile number."; },
            address: function (v) { return v.trim().length >= 10 ? "" : "Please enter your full delivery address (at least 10 characters)."; }
        };

        var check = function (name) {
            var input = form.elements[name];
            var message = rules[name](input.value);
            var box = form.querySelector('[data-error-for="' + name + '"]');
            box.textContent = message;
            box.hidden = !message;
            input.closest(".field").classList.toggle("has-error", !!message);
            input.setAttribute("aria-invalid", message ? "true" : "false");
            return !message;
        };

        Object.keys(rules).forEach(function (name) {
            form.elements[name].addEventListener("blur", function () { check(name); });
        });

        form.addEventListener("submit", function (event) {
            var valid = Object.keys(rules).map(check).every(Boolean);
            if (!valid) {
                event.preventDefault();
                toast("Please fix the highlighted fields.", true);
                var firstBad = form.querySelector(".has-error input, .has-error textarea");
                if (firstBad) firstBad.focus();
                return;
            }
            // Valid: let the form post to the server, but stop a second click.
            var button = document.getElementById("place-order");
            button.classList.add("is-loading");
            button.setAttribute("aria-disabled", "true");
            if (form.dataset.submitting) { event.preventDefault(); return; }
            form.dataset.submitting = "1";
        });
    }
})();
