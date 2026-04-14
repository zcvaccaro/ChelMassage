document.addEventListener('DOMContentLoaded', () => {
    const dateInput = document.getElementById('date');
    const timeSelect = document.getElementById('time');
    const bookingForm = document.querySelector('.reservation-form');
    const serviceSelect = document.getElementById('service');
    const lengthSelect = document.getElementById('length');

    // --- Square Payment SDK Initialization ---
    const appId = window.SQUARE_APP_ID;
    const locationId = window.SQUARE_LOCATION_ID;

    let card;
    let squareInitialized = false;

    // Initialize the Calendar immediately
    initializeDatePicker();

    // Initialize Square immediately after DOM content is parsed
    if (window.location.protocol === 'file:') {
        alert("Square Payments will not work while opening the HTML file directly.");
    } else {
        initializeSquare().catch(err => console.error("Square Init Error:", err));
    }

    async function initializeSquare() {
        if (squareInitialized) return;

        if (!window.Square) {
            // Retry once if the script tag hasn't finished loading
            await new Promise(resolve => setTimeout(resolve, 500));
            if (!window.Square) {
                console.error('Square.js failed to load properly');
                return;
            }
        }

        const cardContainer = document.getElementById('card-container');
        if (!cardContainer) {
            console.error("Square Initialization Error: #card-container not found in DOM.");
            return;
        }

        try {
            const payments = window.Square.payments(appId, locationId);

            // ✅ FIX: Initializing without a style object resolves focus/typing issues on desktop
            card = await payments.card();
            await card.attach('#card-container');

            squareInitialized = true;
            console.log("✅ Square Card attached successfully");

        } catch (e) {
            console.error('Square Card Attachment Failed:', e);
        }
    }

    // --- 0. Service Length and Pricing Data ---
    const servicePricing = {
        'swedish': [
            { length: 30, price: 75 },
            { length: 60, price: 130 },
            { length: 90, price: 180 }
        ],
        'deep-tissue': [
            { length: 30, price: 75 },
            { length: 60, price: 130 },
            { length: 90, price: 180 }
        ],
        'prenatal': [
            { length: 60, price: 120 }
        ],
        'mfr': [
            { length: 30, price: 85 },
            { length: 60, price: 140 },
            { length: 90, price: 190 }
        ]
    };

    const updateLengthOptions = () => {
        const selectedService = serviceSelect.value;
        if (servicePricing[selectedService]) {
            lengthSelect.innerHTML = '<option value="" disabled selected>Select duration</option>';
            lengthSelect.classList.add('placeholder-selected');
            servicePricing[selectedService].forEach(opt => {
                const option = document.createElement('option');
                option.value = opt.length;
                option.textContent = `${opt.length} min — $${opt.price}`;
                lengthSelect.appendChild(option);
            });
            lengthSelect.disabled = false;
        } else {
            lengthSelect.innerHTML = '<option value="" disabled selected>Please select service first</option>';
            lengthSelect.classList.add('placeholder-selected');
            lengthSelect.disabled = true;
        }
        // Reset time availability because service/length context has changed
        fetchAndDisplayAvailability();
    };

    // --- 1. Fetch and Display Availability ---

    const fetchAndDisplayAvailability = async () => {
        // Guard against accessing flatpickr before it is initialized
        const selectedDate = dateInput._flatpickr ? dateInput._flatpickr.selectedDates[0] : null;
        const duration = lengthSelect.value;

        // Differentiate placeholders based on what is missing
        if (!selectedDate) {
            timeSelect.innerHTML = '<option value="" disabled selected>Please select a date first...</option>';
            timeSelect.classList.add('placeholder-selected');
            timeSelect.disabled = true;
            return;
        } else if (!duration) {
            timeSelect.innerHTML = '<option value="" disabled selected>Please select a duration first...</option>';
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
            // 1. Tokenize the card with Square
            if (!card) {
                alert("Payment form is still loading. Please wait a moment.");
                submitButton.classList.remove('loading');
                submitButton.disabled = false;
                return;
}
            const tokenResult = await card.tokenize();
            if (tokenResult.status !== 'OK') {
                throw new Error(tokenResult.errors[0].message);
            }

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
                description: `Comments: ${formData.get('comments')}`,
                service_type: serviceName, // NEW: Add the service type for calendar coloring
                source_id: tokenResult.token, // Token string from Square
            };

            const response = await fetch('/api/book', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });

            let bookingResponse;
            const contentType = response.headers.get("content-type");
            if (contentType && contentType.indexOf("application/json") !== -1) {
                bookingResponse = await response.json();
            } else {
                // If response is not JSON (e.g., HTML error page), handle it gracefully
                const text = await response.text();
                console.error("Server returned non-JSON response:", text);
                throw new Error("Server timeout or internal error. Please check the Render logs.");
            }

            if (!response.ok) {
                throw new Error(bookingResponse.error || 'An unknown error occurred.');
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
                comments: formData.get('comments'),
                service: serviceName,
                calendarId: bookingResponse.calendar_event_id
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
    async function initializeDatePicker() {
        // Initialize flatpickr immediately so the grid appears on click
        const fp = flatpickr("#date", {
            inline: false, // Desktop friendly: open on click, close on select
            disableMobile: true,
            minDate: "today",
            dateFormat: "Y-m-d",
            onChange: (selectedDates) => {
                if (selectedDates.length > 0) fetchAndDisplayAvailability();
            }
        });

        try {
            // Fetch all available days for the next 90 days
            const response = await fetch('/api/available-days?range=90');
            if (!response.ok) throw new Error('Could not fetch available days.');
            const availableDays = await response.json();

            // Update the existing calendar instance with the whitelisted dates from the server
            fp.set("enable", availableDays);

        } catch (error) {
            console.error("Failed to initialize date picker:", error);
            // Fallback for when the API fails
            dateInput.value = "Could not load calendar.";
            dateInput.disabled = true;
        }
    }

    // Also fetch availability when the service length changes
    lengthSelect.addEventListener('change', () => {
        lengthSelect.classList.remove('placeholder-selected');
        fetchAndDisplayAvailability();
    });

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
        if (serviceSelect) {
            if (service && Array.from(serviceSelect.options).some(opt => opt.value === service)) { // Check if the service exists
                serviceSelect.value = service; // Pre-select the service
            }
            updateLengthOptions(); // Update duration options and trigger availability fetch
        }
    };

    serviceSelect.addEventListener('change', updateLengthOptions); // Ensure this is still active for manual changes

    preselectService(); // Run on page load (within DOMContentLoaded)
});
