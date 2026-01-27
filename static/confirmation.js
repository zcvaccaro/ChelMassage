document.addEventListener('DOMContentLoaded', () => {
    const intakeLink = document.getElementById('intake-form-link');
    const confirmationMessage = document.getElementById('confirmation-message');

    if (intakeLink) {
        // Get all parameters from the current URL
        const urlParams = new URLSearchParams(window.location.search);
        const date = urlParams.get('date');
        const time = urlParams.get('time');

        // Update the confirmation message with the booking details
        if (date && time) {
            // Create a Date object, replacing hyphens with slashes to avoid timezone issues.
            const bookingDate = new Date(date.replace(/-/g, '\/'));
            // Get the full day of the week (e.g., "Monday")
            const dayOfWeek = bookingDate.toLocaleDateString('en-US', { weekday: 'long' });
            confirmationMessage.innerHTML = `Thank you for your booking on <strong>${dayOfWeek}, ${date}</strong> at <strong>${time}</strong>! You will receive an email confirmation shortly.<br>As a next step, please fill out our secure client intake form.`;
        }

        // Forward all parameters to the intake form link
        intakeLink.href = `${intakeLink.href}?${urlParams.toString()}`;
    }
});