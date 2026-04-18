document.addEventListener('DOMContentLoaded', () => {
    // --- 1. Populate form from URL parameters ---
    const populateFormFromURL = () => {
        const urlParams = new URLSearchParams(window.location.search);
        const fieldMapping = {
            firstName: 'firstName', lastName: 'lastName', email: 'email',
            phone: 'phone', comments: 'reason',
            dob: 'dob', address: 'address'
        };
        for (const [param, fieldId] of Object.entries(fieldMapping)) {
            const value = urlParams.get(param);
            const element = document.getElementById(fieldId);
            if (value && element) {
                // URLSearchParams.get() already decodes the value
                element.value = value;
            }
        }

        // Force numeric keypad for phone number on mobile
        const phoneInput = document.getElementById('phone');
        if (phoneInput) {
            phoneInput.setAttribute('inputmode', 'tel');
        }
    };

    // --- 2. Setup drawable canvas for body charts ---
    const setupCanvas = (containerId) => {
    const container = document.getElementById(containerId);
    if (!container) return;

    const image = container.querySelector("img");
    const undoBtn = container.querySelector(".undo-btn");

    // Create a wrapper for the image and canvas to position them correctly
    const imageWrapper = document.createElement("div");
    imageWrapper.style.position = "relative";
    // Insert the wrapper before the image and move the image inside it
    image.parentNode.insertBefore(imageWrapper, image);
    imageWrapper.appendChild(image);

    const canvas = document.createElement("canvas");
    imageWrapper.appendChild(canvas); // Append canvas to the new wrapper
    const ctx = canvas.getContext("2d");

    let isDrawing = false;
    let history = [];

    // Function to set canvas size based on the image
    const setCanvasSize = () => {
      const newWidth = image.offsetWidth;
      const newHeight = image.offsetHeight;

      // Only resize if the dimensions have actually changed to prevent clearing on scroll
      if (canvas.width === newWidth && canvas.height === newHeight) return;

      // Save current content to restore after resize
      const tempContent = canvas.toDataURL();

      canvas.width = newWidth;
      canvas.height = newHeight;

      const img = new Image();
      img.onload = () => ctx.drawImage(img, 0, 0, newWidth, newHeight);
      img.src = tempContent;

      ctx.strokeStyle = "red";
      ctx.lineWidth = 3;
      ctx.lineCap = "round";
      ctx.lineJoin = "round";
    };

    // Initially disable the undo button
    undoBtn.disabled = true;

    // Set initial size and resize if window changes
    image.onload = setCanvasSize;
    window.addEventListener("resize", setCanvasSize);
    // If image is already loaded (e.g., from cache)
    if (image.complete) {
      setCanvasSize();
    }

    // Save the current state for undo
    const saveState = () => {
      history.push(canvas.toDataURL());
      if (history.length > 20) history.shift(); // Prevent memory leak by limiting history size
    };

    // Undo the last drawing action
    const undo = () => {
      history.pop(); // Remove the last state
      if (history.length > 0) {
        // Restore the previous state
        const img = new Image();
        img.onload = () => {
            ctx.clearRect(0, 0, canvas.width, canvas.height);
            ctx.drawImage(img, 0, 0);
        };
        img.src = history[history.length - 1];

      } else {
        // If history is empty, clear the canvas
        ctx.clearRect(0, 0, canvas.width, canvas.height);
      }
      // Disable the button if there's nothing left to undo
      undoBtn.disabled = history.length === 0;
    };

    // Get coordinates relative to the canvas
    const getCoords = (e) => {
      const rect = canvas.getBoundingClientRect();
      const scaleX = canvas.width / rect.width;
      const scaleY = canvas.height / rect.height;
      const clientX = e.touches ? e.touches[0].clientX : e.clientX;
      const clientY = e.touches ? e.touches[0].clientY : e.clientY;
      return {
        x: (clientX - rect.left) * scaleX,
        y: (clientY - rect.top) * scaleY,
      };
    };

    const startDrawing = (e) => {
      e.preventDefault();
      isDrawing = true;
      undoBtn.disabled = false; // Enable the undo button
      const { x, y } = getCoords(e);
      ctx.beginPath();
      ctx.moveTo(x, y);
    };

    const draw = (e) => {
      if (!isDrawing) return;
      e.preventDefault();
      const { x, y } = getCoords(e);
      ctx.lineTo(x, y);
      ctx.stroke();
    };

    const stopDrawing = () => {
      if (isDrawing) {
        ctx.closePath();
        isDrawing = false;
        saveState(); // Save state after a line is completed
      }
    };

    // Event Listeners
    canvas.addEventListener("mousedown", startDrawing);
    canvas.addEventListener("mousemove", draw);
    canvas.addEventListener("mouseup", stopDrawing);
    canvas.addEventListener("mouseout", stopDrawing);

    canvas.addEventListener("touchstart", startDrawing);
    canvas.addEventListener("touchmove", draw);
    canvas.addEventListener("touchend", stopDrawing);

    undoBtn.addEventListener("click", undo);
    };

    // --- 3. Handle Terms & Conditions Validation ---
    const setupTermsValidation = () => {
        const form = document.querySelector('.intake-form');
        const agreeTermsCheckbox = document.getElementById('agreeTerms');
        const agreeTermsText = document.querySelector('.agreement-text');
        const errorMessage = document.getElementById('agree-error-message');

        if (!form || !agreeTermsCheckbox || !agreeTermsText || !errorMessage) return;

        // Remove the error styling once the user checks the box
        agreeTermsCheckbox.addEventListener('change', () => {
            agreeTermsText.style.color = ''; // Reset text color
            errorMessage.style.display = 'none'; // Hide the error message
        });
    };

    // --- 4. Handle Intake Form Submission (Future Use) ---
    const handleAdvancedFormSubmission = () => {
        const intakeForm = document.querySelector('.intake-form');
        if (!intakeForm) return;

        const scrollToField = (el, offset = 180) => {
            const y = el.getBoundingClientRect().top + window.pageYOffset - offset;
            window.scrollTo({
                top: y,
                behavior: 'smooth'
            });
        };


        let isInternalValidation = false;
        intakeForm.addEventListener('invalid', (e) => {
            if (isInternalValidation) return;

            const firstInvalid = intakeForm.querySelector(':invalid');
            if (firstInvalid && e.target === firstInvalid) {
                e.preventDefault();

                const scrollTarget = firstInvalid.closest('.form-group, .agreement-group, fieldset') || firstInvalid;
                scrollToField(scrollTarget);

                setTimeout(() => {
                    isInternalValidation = true;
                    firstInvalid.reportValidity();
                    isInternalValidation = false;
                    firstInvalid.focus({ preventScroll: true });
                }, 300);
            }
        }, true);

        intakeForm.addEventListener('submit', async (e) => {
            const submitButton = intakeForm.querySelector('button[type="submit"]');
            const agreeTermsCheckbox = document.getElementById('agreeTerms');

            // 1. Handle Custom Checkbox Validation
            if (!agreeTermsCheckbox.checked) {
                agreeTermsCheckbox.setCustomValidity("Please agree to the terms and conditions to continue.");
                document.querySelector('.agreement-text').style.color = 'var(--accent-color-dark)';
                document.getElementById('agree-error-message').style.display = 'block';
            } else {
                agreeTermsCheckbox.setCustomValidity("");
            }

            // 2. Validation check - triggering the global scroll + bubble logic in main.js
            if (!intakeForm.checkValidity()) {
                e.preventDefault();
                return;
            }

            e.preventDefault(); // Valid form, proceed with custom submission

            // --- Add loading state to the submit button ---
            submitButton.disabled = true;
            submitButton.classList.add('loading');
            // We'll store the original text to restore it later
            const originalButtonText = submitButton.innerHTML;
            submitButton.innerHTML = 'Submitting...';

            try {
                // 1. Gather all form data
                const formData = new FormData(intakeForm);
                const payload = Object.fromEntries(formData.entries());

                // 2. Combine background image and drawing into a single data URL
                const getCombinedCanvasData = (containerId) => {
                    const container = document.getElementById(containerId);
                    const image = container.querySelector('img');
                    const drawingCanvas = container.querySelector('canvas');

                    // Create a temporary canvas to merge the image and the drawing
                    const tempCanvas = document.createElement('canvas');
                    const tempCtx = tempCanvas.getContext('2d');
                    tempCanvas.width = image.naturalWidth; // Use natural dimensions for best quality
                    tempCanvas.height = image.naturalHeight;

                    // Draw the background image first, then the user's drawing on top
                    tempCtx.drawImage(image, 0, 0);
                    tempCtx.drawImage(drawingCanvas, 0, 0, tempCanvas.width, tempCanvas.height);

                    return tempCanvas.toDataURL('image/png');
                };
                payload.drawingFront = getCombinedCanvasData('body-chart-front');
                payload.drawingBack = getCombinedCanvasData('body-chart-back');

                // 3. Add booking details from the URL to link the intake to the booking
                const urlParams = new URLSearchParams(window.location.search);
                payload.bookingDate = urlParams.get('date');
                payload.bookingTime = urlParams.get('time');
                payload.calendarId = urlParams.get('calendarId');
                payload.serviceType = urlParams.get('service');

                // 4. Send data to the new backend endpoint
                const response = await fetch('/api/submit-intake', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });

                if (!response.ok) throw new Error('Failed to submit intake form.');

                // 5. Redirect on success
                window.location.href = '/IntakeConfirm.html';
            } catch (error) {
                console.error('Intake form submission error:', error);
                alert('There was an error submitting your form. Please try again.');
            } finally {
                // --- Remove loading state ---
                submitButton.disabled = false;
                submitButton.classList.remove('loading');
                submitButton.innerHTML = originalButtonText;
            }
        });
    };

    // --- Initialize all functionalities ---
    populateFormFromURL();
    setupCanvas("body-chart-front");
    setupCanvas("body-chart-back");
    setupTermsValidation();
    handleAdvancedFormSubmission();
});