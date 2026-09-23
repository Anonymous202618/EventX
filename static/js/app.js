(() => {

    /* =====================================================
       THEME
    ===================================================== */

    const root = document.documentElement;

    const stored =
        localStorage.getItem('eventx-theme') || 'light';

    root.setAttribute(
        'data-theme',
        stored
    );


    function syncIcon() {

        document
            .querySelectorAll('#themeToggle')
            .forEach(btn => {

                const icon =
                    btn.querySelector('i');

                if (!icon) {
                    return;
                }

                icon.className =
                    root.getAttribute('data-theme') === 'dark'
                        ? 'bi bi-sun'
                        : 'bi bi-moon-stars';
            });
    }


    syncIcon();


    document.addEventListener(
        'click',
        (e) => {

            const btn =
                e.target.closest(
                    '#themeToggle'
                );

            if (!btn) {
                return;
            }

            const next =
                root.getAttribute('data-theme') === 'dark'
                    ? 'light'
                    : 'dark';

            root.setAttribute(
                'data-theme',
                next
            );

            localStorage.setItem(
                'eventx-theme',
                next
            );

            syncIcon();
        }
    );


    /* =====================================================
       NOTIFICATIONS
    ===================================================== */

   const notificationList =
    document.getElementById(
        'notificationList'
    );

const notificationBtn =
    document.getElementById(
        'notificationBtn'
    );


async function loadNotifications() {

    if (!notificationList) {
        return;
    }

    try {

        const res =
            await fetch(
                '/api/notifications'
            );

        if (!res.ok) {
            return;
        }

        const items =
            await res.json();


        notificationList.innerHTML =
            items.length

                ? items
                    .map(
                        n => `
                            <div class="cardx p-3 notification-pop ${
                                n.is_read
                                    ? ''
                                    : 'notification-unread'
                            }">

                                <div class="notification-title fw-bold">
                                    ${escapeHtml(n.title)}
                                </div>

                                <div class="notification-message muted small mt-1">
                                    ${escapeHtml(n.message)}
                                </div>

                                <div class="notification-time muted small mt-2">
                                    ${new Date(
                                        n.created_at + 'Z'
                                    ).toLocaleString(
                                        'en-IN',
                                        {
                                            timeZone:
                                                'Asia/Kolkata',

                                            dateStyle:
                                                'medium',

                                            timeStyle:
                                                'short'
                                        }
                                    )}
                                </div>

                            </div>
                        `
                    )
                    .join('')

                : `
                    <div class="empty">
                        No notifications yet.
                    </div>
                `;


        /*
         * The notification panel has been opened,
         * so mark the currently unread notifications
         * as read immediately.
         */
        const readRes =
            await fetch(
                '/api/notifications/read',
                {
                    method: 'POST'
                }
            );


        if (readRes.ok) {

            /*
             * Remove the unread number from
             * the bell immediately.
             */
            const notifDot =
                notificationBtn?.querySelector(
                    '.notif-dot'
                );

            if (notifDot) {
                notifDot.remove();
            }


            /*
             * Remove unread styling from
             * notifications already displayed.
             */
            document
                .querySelectorAll(
                    '.notification-unread'
                )
                .forEach(
                    function (item) {
                        item.classList.remove(
                            'notification-unread'
                        );
                    }
                );

        }

    } catch (e) {

        console.error(
            'EventX notification error:',
            e
        );

    }
}


if (notificationBtn) {

    notificationBtn.addEventListener(
        'click',
        loadNotifications
    );

}
    /* =====================================================
       HTML ESCAPING
    ===================================================== */

    function escapeHtml(s) {

        return String(s).replace(
            /[&<>"']/g,

            c => ({
                '&': '&amp;',
                '<': '&lt;',
                '>': '&gt;',
                '"': '&quot;',
                "'": '&#039;'
            }[c])
        );
    }


    /* =====================================================
       EVENT COUNTDOWN
    ===================================================== */

    function startEventCountdown() {

        const countdown =
            document.getElementById(
                'eventCountdown'
            );


        /*
            This is important.

            If we're not on an event-detail page,
            there won't be a countdown element.

            Just stop without causing an error.
        */

        if (!countdown) {
            return;
        }


        const target =
            new Date(
                countdown.dataset.start
            ).getTime();


        /*
            Check if the event date is valid.
        */

        if (Number.isNaN(target)) {

            countdown.textContent =
                'Date unavailable';

            return;
        }


        function updateCountdown() {

            const now =
                Date.now();


            const difference =
                target - now;


            /* Event has started */

            if (difference <= 0) {

                countdown.textContent =
                    'LIVE NOW';

                countdown.style.color =
                    'var(--success)';

                return;
            }


            /* Remaining time */

            const days =
                Math.floor(
                    difference /
                    (1000 * 60 * 60 * 24)
                );


            const hours =
                Math.floor(
                    (
                        difference /
                        (1000 * 60 * 60)
                    ) % 24
                );


            const minutes =
                Math.floor(
                    (
                        difference /
                        (1000 * 60)
                    ) % 60
                );


            const seconds =
                Math.floor(
                    (
                        difference /
                        1000
                    ) % 60
                );


            countdown.textContent =
                `${days}d ${hours}h ${minutes}m ${seconds}s`;
        }


        updateCountdown();


        setInterval(
            updateCountdown,
            1000
        );
    }


    startEventCountdown();

/* =====================================================
   REGISTRATION BUTTON
===================================================== */

document.addEventListener(
    'submit',
    (event) => {

        const form =
            event.target;

        if (
            !form.matches(
                '.registration-form'
            )
        ) {
            return;
        }

        const button =
            form.querySelector(
                '.btn-register'
            );

        if (!button) {
            return;
        }


        /* Prevent accidental double clicking */

        button.disabled = true;

        button.classList.add(
            'is-loading'
        );


        /* Change button content */

        button.innerHTML = `
            <span
                class="spinner-border
                       spinner-border-sm
                       me-2"
                aria-hidden="true">
            </span>

            Registering...
        `;
    }
);
/* =========================================================
   FEEDBACK RATING
   ========================================================= */

const ratingPicker = document.getElementById("ratingPicker");

if (ratingPicker) {

    const stars = ratingPicker.querySelectorAll(".rating-star");
    const ratingValue = document.getElementById("ratingValue");
    const ratingHelper = document.getElementById("ratingHelper");

    const ratingLabels = {
        1: "1 — Very poor",
        2: "2 — Poor",
        3: "3 — Average",
        4: "4 — Good",
        5: "5 — Excellent"
    };


    function updateRating(value) {

        if (ratingValue) {
            ratingValue.value = value;
        }

        stars.forEach((star) => {

            const starValue = Number(star.dataset.rating);

            star.classList.toggle(
                "active",
                starValue <= value
            );

        });

        if (ratingHelper) {
            ratingHelper.textContent =
                ratingLabels[value] || "";
        }

    }


    stars.forEach((star) => {

        star.addEventListener("click", () => {

            const value = Number(star.dataset.rating);

            updateRating(value);

        });

    });


    updateRating(
        Number(ratingValue?.value || 5)
    );

}


/* Character counter */

const feedbackComment =
    document.getElementById("feedbackComment");

const feedbackCharacterCount =
    document.getElementById("feedbackCharacterCount");

if (feedbackComment && feedbackCharacterCount) {

    const updateCharacterCount = () => {

        feedbackCharacterCount.textContent =
            feedbackComment.value.length;

    };

    feedbackComment.addEventListener(
        "input",
        updateCharacterCount
    );

    updateCharacterCount();

}


/* Feedback submit state */

const feedbackForm =
    document.getElementById("feedbackForm");

if (feedbackForm) {

    feedbackForm.addEventListener("submit", () => {

        const submitButton =
            feedbackForm.querySelector(".feedback-submit-btn");

        if (!submitButton) {
            return;
        }

        submitButton.disabled = true;

        submitButton.innerHTML = `
            <span
                class="spinner-border spinner-border-sm me-2"
                aria-hidden="true"
            ></span>
            Submitting...
        `;

    });

}
})();
