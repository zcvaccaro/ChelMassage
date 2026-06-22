document.addEventListener('DOMContentLoaded', () => {
    const urlParams = new URLSearchParams(window.location.search);
    const waitlistForm = document.querySelector('.reservation-form');

    ['firstName', 'lastName', 'email', 'phone', 'service', 'length'].forEach(id => {
        const value = urlParams.get(id);
        const field = document.getElementById(id);
        if (value && field) {
            field.value = value;
            field.classList.remove('placeholder-selected');
        }
    });

    const phoneInput = document.getElementById('phone');
    if (phoneInput) phoneInput.setAttribute('inputmode', 'tel');

    if (window.flatpickr) {
        flatpickr('.datepicker', { minDate: 'today', dateFormat: 'F j, Y' });
    }

    if (waitlistForm) {
        waitlistForm.addEventListener('submit', async (e) => {
            e.preventDefault();

            if (!waitlistForm.checkValidity()) {
                waitlistForm.reportValidity();
                return;
            }

            const submitButton = waitlistForm.querySelector('button[type="submit"]');
            const originalButtonText = submitButton ? submitButton.innerHTML : '';

            if (submitButton) {
                submitButton.disabled = true;
                submitButton.classList.add('loading');
                submitButton.innerHTML = 'Submitting...';
            }

            try {
                const formData = new FormData(waitlistForm);
                const payload = Object.fromEntries(formData.entries());

                const response = await fetch('/api/submit-waitlist', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });

                const result = await response.json().catch(() => ({}));
                if (!response.ok) {
                    throw new Error(result.error || 'Failed to submit waitlist request.');
                }

                window.location.href = '/WaitListConfirm.html';
            } catch (error) {
                console.error('Waitlist submission error:', error);
                alert(error.message || 'There was an error submitting your waitlist request. Please try again.');
            } finally {
                if (submitButton) {
                    submitButton.disabled = false;
                    submitButton.classList.remove('loading');
                    submitButton.innerHTML = originalButtonText;
                }
            }
        });
    }
});
