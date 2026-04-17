document.addEventListener('DOMContentLoaded', () => {
    // --- 1. Populate form from URL parameters (Returning Customers) ---
    const prefillFromURL = () => {
        const urlParams = new URLSearchParams(window.location.search);
        // Map URL parameters to the expected HTML IDs in OnSiteRequest.html
        const fields = ['firstName', 'lastName', 'email', 'phone', 'address', 'dob'];

        fields.forEach(id => {
            const val = urlParams.get(id);
            const el = document.getElementById(id);
            if (val && el) el.value = val;
        });

        // Mobile UX: Force numeric keypad for phone number
        const phoneInput = document.getElementById('phone');
        if (phoneInput) phoneInput.setAttribute('inputmode', 'tel');
    };

    prefillFromURL();

    // --- 2. Initialize Date Pickers ---
    if (window.flatpickr) {
        flatpickr(".datepicker", { minDate: "today", dateFormat: "F j, Y" });
    }

    // --- 3. Dynamic Treatment Fields Logic ---
    const numberOfClientsInput = document.getElementById('numberOfClients');
    const dynamicTreatmentFields = document.getElementById('dynamicTreatmentFields');

    const renderTreatmentFields = (count) => {
        if (!dynamicTreatmentFields) return;
        dynamicTreatmentFields.innerHTML = ''; // Clear existing fields

        for (let i = 1; i <= count; i++) {
            const clientDiv = document.createElement('div');
            clientDiv.classList.add('client-treatment-group');
            clientDiv.innerHTML = `
              <div class="form-row date-time-row">
                <div class="form-group">
                  <label for="clientName_${i}">Client ${i} Name</label>
                  <input type="text" id="clientName_${i}" name="clientName_${i}" required>
                </div>
                <div class="form-group">
                  <label for="treatmentType_${i}">Client ${i} Treatment Type</label>
                  <select id="treatmentType_${i}" name="treatmentType_${i}" required>
                    <option value="" disabled selected>Select a service</option>
                    <option value="Deep Tissue">Deep Tissue</option>
                    <option value="Swedish">Swedish</option>
                    <option value="Prenatal">Prenatal</option>
                    <option value="MFR">Myofascial Release (MFR)</option>
                  </select>
                </div>
              </div>
            `;
            dynamicTreatmentFields.appendChild(clientDiv);
        }
    };

    if (numberOfClientsInput) {
        // Initial render for 1 client on page load
        renderTreatmentFields(parseInt(numberOfClientsInput.value));

        // Listen for changes to the number of clients
        numberOfClientsInput.addEventListener('change', (e) => {
            const count = parseInt(e.target.value);
            if (count >= 1 && count <= 5) {
                renderTreatmentFields(count);
            } else {
                // Reset to 1 if invalid input (should be prevented by min/max but good for robustness)
                e.target.value = 1;
                renderTreatmentFields(1);
            }
        });
    }

    // --- 4. Form Submission Logic ---
    const onsiteForm = document.querySelector('.reservation-form');
    if (onsiteForm) {
        let isInternalValidation = false;
        onsiteForm.addEventListener('invalid', (e) => {
            if (isInternalValidation) return;
            
            const firstInvalid = onsiteForm.querySelector(':invalid');
            if (firstInvalid && e.target === firstInvalid) {
                e.preventDefault();
                
                const scrollTarget = firstInvalid.closest('.form-group, .agreement-group, fieldset') || firstInvalid;
                const headerOffset = 300;
                const elementPosition = scrollTarget.getBoundingClientRect().top + window.scrollY;

                window.scrollTo({
                    top: elementPosition - headerOffset,
                    behavior: 'smooth'
                });

                setTimeout(() => {
                    isInternalValidation = true;
                    firstInvalid.reportValidity();
                    isInternalValidation = false;
                    firstInvalid.focus({ preventScroll: true });
                }, 450);
            }
        }, true);

        onsiteForm.addEventListener('submit', async (e) => {
            // Trigger native validation scroll/bubbles before custom submission
            if (!onsiteForm.checkValidity()) {
                e.preventDefault();
                return;
            }

            e.preventDefault(); // Valid form, proceed with custom submission
            const form = e.target;
            const submitBtn = form.querySelector('button[type="submit"]');

            if (!submitBtn) return;

            submitBtn.classList.add('loading');
            submitBtn.disabled = true;

            const formData = new FormData(form);
            const data = Object.fromEntries(formData.entries());

            try {
                const response = await fetch('/api/request-onsite', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(data)
                });

                if (response.ok) {
                    // Redirect to confirmation page on success (Hardcoded path for static JS)
                    window.location.href = "/RequestConfirm.html";
                } else {
                    const result = await response.json();
                    alert('Error: ' + (result.error || 'Failed to submit request.'));
                    submitBtn.classList.remove('loading');
                    submitBtn.disabled = false;
                }
            } catch (error) {
                console.error('Submission Error:', error);
                alert('An unexpected error occurred. Please try again later.');
                submitBtn.classList.remove('loading');
                submitBtn.disabled = false;
            }
        });
    }
});