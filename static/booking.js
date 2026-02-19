document.addEventListener('DOMContentLoaded', () => {
    const dateInput = document.getElementById('date');
    const timeSelect = document.getElementById('time');
    const bookingForm = document.querySelector('.reservation-form');
    const serviceSelect = document.getElementById('service');
    const lengthSelect = document.getElementById('length');
    const cardNumberInput = document.getElementById('cardNumber');
    const cardExpiryInput = document.getElementById('cardExpiry');

    // --- 1. Fetch and Display Availability ---

    const fetchAndDisplayAvailability = async () => {
        const selectedDate = dateInput._flatpickr.selectedDates[0];
        const duration = lengthSelect.value;

        // Don't fetch if we don't have both a date and a duration
        if (!selectedDate || !duration) {
            timeSelect.innerHTML = '<option value="" disabled selected>Select a service length</option>';
            timeSelect.classList.add('placeholder-selected');
            timeSelect.disabled = true;
            return;
        }

        // Clear previous times and show a loading message
        timeSelect.innerHTML = '<option>Fetching times...</option>';
        timeSelect.disabled = true;

        try {
            // Format the date to YYYY-MM-DD for the API
            const dateStr = selectedDate.toISOString().split('T')[0];
            const response = await fetch(`/api/availability?date=${dateStr}&duration=${duration}`);

            if (!response.ok) {
                throw new Error('Network response was not ok');
            }

            // The API now returns a simple array of valid start times
            const availableTimes = await response.json();
            populateTimeSlots(availableTimes);

        } catch (error) {
            console.error('Error fetching availability:', error);
            timeSelect.innerHTML = '<option>Could not load times.</option>';
        }
    };

    const populateTimeSlots = (availableTimes) => {
        timeSelect.innerHTML = ''; // Clear loading message

        if (!availableTimes || availableTimes.length === 0) {
            timeSelect.innerHTML = '<option value="" disabled selected>No times available on this day</option>';
            timeSelect.classList.add('placeholder-selected');
            return;
        }

        timeSelect.classList.remove('placeholder-selected');
        // Populate the dropdown
        availableTimes.forEach(timeISO => {
            const slot = new Date(timeISO);
            const option = document.createElement('option');
            // Format time as "HH:MM AM/PM"
            option.value = slot.toTimeString().slice(0, 5); // "HH:MM"
            option.textContent = slot.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
            timeSelect.appendChild(option);
        });

        timeSelect.disabled = false;
    };

    // --- 2. Handle Form Submission ---

    bookingForm.addEventListener('submit', async (e) => {
        e.preventDefault(); // Prevent the browser from reloading

        const submitButton = bookingForm.querySelector('button[type="submit"]');
        submitButton.classList.add('loading');
        submitButton.disabled = true;

        try {
            const selectedDate = dateInput._flatpickr.selectedDates[0];
            const [hour, minute] = timeSelect.value.split(':');
            const startTime = new Date(selectedDate);
            startTime.setHours(parseInt(hour), parseInt(minute), 0, 0);

            const formData = new FormData(bookingForm);
            const clientName = `${formData.get('firstName')} ${formData.get('lastName')}`;
            const serviceName = serviceSelect.options[serviceSelect.selectedIndex].text;

            const payload = {
                client: {
                    first_name: formData.get('firstName'),
                    last_name: formData.get('lastName'),
                    email: formData.get('email'),
                    phone: formData.get('phone'),
                },
                start_time: startTime.toISOString(),
                service_duration: parseInt(lengthSelect.value),
                summary: `${serviceName} for ${clientName}`,
                description: `Comments: ${formData.get('comments')}`
            };

            const response = await fetch('/api/book', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });

            let result;
            const contentType = response.headers.get("content-type");
            if (contentType && contentType.indexOf("application/json") !== -1) {
                result = await response.json();
            } else {
                // If response is not JSON (e.g., HTML error page), handle it gracefully
                const text = await response.text();
                console.error("Server returned non-JSON response:", text);
                throw new Error("Server timeout or internal error. Please check the Render logs.");
            }

            if (!response.ok) {
                throw new Error(result.error || 'An unknown error occurred.');
            }

            // On success, redirect to the confirmation page.
            // We'll pass user data to the confirmation page and then to the intake form.
            const formattedDate = selectedDate.toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' });
            const formattedTime = startTime.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
            const params = new URLSearchParams({
                date: formattedDate,
                time: formattedTime,
                firstName: formData.get('firstName'),
                lastName: formData.get('lastName'),
                email: formData.get('email'),
                phone: formData.get('phone'),
                comments: formData.get('comments')
            });
            const redirectUrl = `/BookingConfirm.html?${params.toString()}`;
            window.location.href = redirectUrl;

        } catch (error) {
            console.error('Booking failed:', error);
            alert(`Booking failed: ${error.message}`);
            submitButton.classList.remove('loading');
            submitButton.disabled = false;
        }
    });

    // --- 3. Initialize Date Picker with Enabled Dates ---
    const initializeDatePicker = async () => {
        try {
            // Fetch all available days for the next 90 days
            const response = await fetch('/api/available-days?range=90');
            if (!response.ok) {
                throw new Error('Could not fetch available days.');
            }
            const availableDays = await response.json();

            // Configure and initialize the date picker
            flatpickr("#date", {
                minDate: "today",
                // The 'enable' option acts as a whitelist for dates.
                enable: availableDays,
                // When a valid date is selected, fetch the time slots for it.
                onChange: function(selectedDates) {
                    fetchAndDisplayAvailability();
                }
            });

        } catch (error) {
            console.error("Failed to initialize date picker:", error);
            // Fallback for when the API fails
            dateInput.value = "Could not load calendar.";
            dateInput.disabled = true;
        }
    };

    initializeDatePicker(); // Run the initialization

    // Also fetch availability when the service length changes
    lengthSelect.addEventListener('change', fetchAndDisplayAvailability);

    // When a real time is selected, remove the placeholder styling
    timeSelect.addEventListener('change', () => {
        timeSelect.classList.remove('placeholder-selected');
    });

    // --- 4. Cancellation Policy Modal Logic ---
    const modal = document.getElementById('cancellation-modal');
    const openModalBtn = document.getElementById('cancellation-policy-btn');
    const closeModalBtn = document.getElementById('close-modal-btn');

    if (modal && openModalBtn && closeModalBtn) {
        openModalBtn.addEventListener('click', () => {
            modal.style.display = 'flex';
        });

        closeModalBtn.addEventListener('click', () => {
            modal.style.display = 'none';
        });

        // Also close modal if user clicks on the overlay
        modal.addEventListener('click', (e) => {
            if (e.target === modal) {
                modal.style.display = 'none';
            }
        });
    }

    // --- 5. Pre-select service from URL ---
    const preselectService = () => {
        const urlParams = new URLSearchParams(window.location.search);
        const service = urlParams.get('service');
        if (service && serviceSelect) {
            serviceSelect.value = service;
        }
    };

    preselectService(); // Run on page load

    // --- 6. Credit Card and Expiration Date Formatting ---

    // Format credit card number with spaces
    if (cardNumberInput) {
        cardNumberInput.addEventListener('input', (e) => {
            let value = e.target.value.replace(/\D/g, ''); // Remove all non-digit characters
            if (value.length > 16) {
                value = value.slice(0, 16); // Max 16 digits
            }
            // Add a space after every 4 digits
            const formattedValue = value.replace(/(\d{4})(?=\d)/g, '$1 ');
            e.target.value = formattedValue;
        });
    }

    // Format expiration date with a slash
    if (cardExpiryInput) {
        cardExpiryInput.addEventListener('input', (e) => {
            let value = e.target.value.replace(/\D/g, ''); // Remove all non-digit characters
            if (value.length > 2) {
                value = value.slice(0, 2) + '/' + value.slice(2, 4); // Insert a slash after the first two digits (MM)
            }
            e.target.value = value;
        });
    }
});
