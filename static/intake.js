document.addEventListener('DOMContentLoaded', () => {
    // --- 1. Populate form from URL parameters ---
    const populateFormFromURL = () => {
        const urlParams = new URLSearchParams(window.location.search);
        const fieldMapping = {
            firstName: 'firstName', lastName: 'lastName', email: 'email',
            phone: 'phone', comments: 'reason'
        };
        for (const [param, fieldId] of Object.entries(fieldMapping)) {
            const value = urlParams.get(param);
            if (value) document.getElementById(fieldId).value = decodeURIComponent(value);
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
      canvas.width = image.offsetWidth;
      canvas.height = image.offsetHeight;
      ctx.strokeStyle = "red";
      ctx.lineWidth = 3; // Thick enough to see, but not too thick
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

        form.addEventListener('submit', (event) => {
            // First, check if the rest of the form is valid.
            // If not, let the browser handle showing the native error messages.
            if (!form.checkValidity()) {
                return;
            }

            // Now, specifically check our custom checkbox.
            if (!agreeTermsCheckbox.checked) {
                // If other fields are valid but the box isn't checked,
                // prevent submission and show our custom error.
                event.preventDefault();

                // Show our custom error message and styling
                agreeTermsText.style.color = 'var(--accent-color-dark)';
                errorMessage.style.display = 'block';
            }
        });

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

        intakeForm.addEventListener('submit', async (e) => {
            e.preventDefault();

            const submitButton = intakeForm.querySelector('button[type="submit"]');

            // Check both native and custom validation
            if (!intakeForm.checkValidity() || !document.getElementById('agreeTerms').checked) {
                intakeForm.reportValidity(); // Show native validation errors
                return;
            }

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