document.addEventListener('DOMContentLoaded', () => {
    const urlParams = new URLSearchParams(window.location.search);
    const waitlistForm = document.querySelector('.reservation-form');
    const lengthSelect = document.getElementById('length');
    const availabilityModal = document.getElementById('waitlist-availability-modal');
    const availabilityMessage = document.getElementById('waitlist-availability-message');
    const modalTimeSelect = document.getElementById('waitlist-modal-time');
    const bookNowBtn = document.getElementById('waitlist-book-now-btn');
    const continueWaitlistBtn = document.getElementById('waitlist-continue-link');
    const closeModalBtn = document.getElementById('close-waitlist-availability-modal');

    let availabilityRequestId = 0;
    let availabilityCheckTimeout = null;
    let modalSelectedDate = null;
    let modalSelectedDateDisplay = '';
    let lastAvailabilityCheck = { date: null, dateFieldId: null };

    const scheduleAvailabilityCheck = (selectedDate, dateFieldId) => {
        clearTimeout(availabilityCheckTimeout);
        availabilityCheckTimeout = setTimeout(() => {
            maybeShowAvailabilityModal(selectedDate, dateFieldId);
        }, 50);
    };

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

    const formatDateForApi = (date) => [
        date.getFullYear(),
        (date.getMonth() + 1).toString().padStart(2, '0'),
        date.getDate().toString().padStart(2, '0')
    ].join('-');

    const populateModalTimeSlots = (availableTimes) => {
        modalTimeSelect.innerHTML = '';

        if (!availableTimes || availableTimes.length === 0) {
            modalTimeSelect.innerHTML = '<option value="" disabled selected>No times available on this day</option>';
            modalTimeSelect.disabled = true;
            modalTimeSelect.classList.add('placeholder-selected');
            return false;
        }

        modalTimeSelect.classList.remove('placeholder-selected');
        availableTimes.forEach(timeISO => {
            const slot = new Date(timeISO);
            const option = document.createElement('option');
            option.value = slot.toTimeString().slice(0, 5);
            option.textContent = slot.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
            modalTimeSelect.appendChild(option);
        });

        modalTimeSelect.disabled = false;
        return true;
    };

    const closeAvailabilityModal = () => {
        if (!availabilityModal) return;
        availabilityModal.style.display = 'none';
        availabilityModal.setAttribute('aria-hidden', 'true');
    };

    const openAvailabilityModal = (dateDisplay) => {
        if (!availabilityModal) return;
        availabilityMessage.textContent =
            `There is available time on ${dateDisplay} that could accommodate your request! You can select an available time here:`;
        availabilityModal.style.display = 'flex';
        availabilityModal.setAttribute('aria-hidden', 'false');
    };

    const maybeShowAvailabilityModal = async (selectedDate, dateFieldId) => {
        const duration = lengthSelect?.value;
        if (!duration || !selectedDate || !availabilityModal) return;

        lastAvailabilityCheck = { date: selectedDate, dateFieldId };
        const requestId = ++availabilityRequestId;
        const dateDisplay = window.flatpickr.formatDate(selectedDate, 'F j, Y');

        modalTimeSelect.innerHTML = '<option>Fetching times...</option>';
        modalTimeSelect.disabled = true;

        try {
            const response = await fetch(
                `/api/availability?date=${formatDateForApi(selectedDate)}&duration=${duration}`
            );

            if (requestId !== availabilityRequestId) return;

            if (!response.ok) {
                throw new Error('Could not check availability.');
            }

            const availableTimes = await response.json();
            if (requestId !== availabilityRequestId) return;

            const hasTimes = populateModalTimeSlots(availableTimes);
            if (!hasTimes) return;

            modalSelectedDate = selectedDate;
            modalSelectedDateDisplay = dateDisplay;
            openAvailabilityModal(dateDisplay);
        } catch (error) {
            if (requestId !== availabilityRequestId) return;
            console.error('Waitlist availability check failed:', error);
        }
    };

    if (window.flatpickr) {
        ['date1', 'date2', 'date3'].forEach(id => {
            const input = document.getElementById(id);
            if (!input) return;

            flatpickr(input, {
                minDate: 'today',
                dateFormat: 'F j, Y',
                enable: [
                    date => [0, 1, 2].includes(date.getDay())
                ],
                onChange: (selectedDates) => {
                    if (selectedDates.length > 0) {
                        scheduleAvailabilityCheck(selectedDates[0], id);
                    }
                },
                onDayCreate: (_dObj, _dStr, fp, dayElem) => {
                    dayElem.addEventListener('click', () => {
                        setTimeout(() => {
                            const selected = fp.selectedDates[0];
                            if (selected) scheduleAvailabilityCheck(selected, id);
                        }, 0);
                    });
                }
            });
        });
    }

    if (lengthSelect) {
        lengthSelect.addEventListener('change', () => {
            lengthSelect.classList.remove('placeholder-selected');
            if (lastAvailabilityCheck.date) {
                scheduleAvailabilityCheck(
                    lastAvailabilityCheck.date,
                    lastAvailabilityCheck.dateFieldId
                );
            }
        });
    }

    if (closeModalBtn) closeModalBtn.addEventListener('click', closeAvailabilityModal);
    if (continueWaitlistBtn) continueWaitlistBtn.addEventListener('click', closeAvailabilityModal);

    if (availabilityModal) {
        availabilityModal.addEventListener('click', (e) => {
            if (e.target === availabilityModal) closeAvailabilityModal();
        });
    }

    if (modalTimeSelect) {
        modalTimeSelect.addEventListener('change', () => {
            modalTimeSelect.classList.remove('placeholder-selected');
        });
    }

    if (bookNowBtn) {
        bookNowBtn.addEventListener('click', () => {
            if (!modalTimeSelect?.value || !modalSelectedDate) {
                alert('Please select an available time first.');
                return;
            }

            const params = new URLSearchParams();
            ['firstName', 'lastName', 'email', 'phone', 'service', 'length'].forEach(id => {
                const value = document.getElementById(id)?.value.trim();
                if (value) params.set(id, value);
            });
            params.set('date', formatDateForApi(modalSelectedDate));
            params.set('time', modalTimeSelect.value);

            window.location.href = `/Booking.html?${params.toString()}`;
        });
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
