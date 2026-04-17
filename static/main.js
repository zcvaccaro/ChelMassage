document.addEventListener("DOMContentLoaded", () => {
  // --- Mobile Navigation Toggle ---
  const navToggle = document.getElementById("navToggle");
  const navMenu = document.getElementById("navMenu");
  if (navToggle && navMenu) {
    navToggle.addEventListener("click", () => {
      navMenu.classList.toggle("is-active");
    });
  }

  // Close mobile menu when clicking outside of it
  document.addEventListener('click', (e) => {
    if (navMenu.classList.contains('is-active') && !navMenu.contains(e.target) && !navToggle.contains(e.target)) {
      navMenu.classList.remove('is-active');
    }
  });

  // --- Card Expansion Logic (Cloning Method) ---
  const serviceCards = document.querySelectorAll(".card[data-service-id]");
  const overlay = document.querySelector(".overlay");
  let originalCard = null;
  let isAnimating = false;

  // --- Returning Client Lookup Modal ---
  const showLookupModal = (targetUrl) => {
    const modalHtml = `
      <div id="lookup-modal" class="modal-overlay" style="display:flex; opacity:1; pointer-events:auto;">
          <div class="modal-content" style="text-align: center; max-width: 450px;">
              <button class="close-modal-btn" id="close-lookup-btn">&times;</button>
              <h2 style="font-size: 1.8rem; margin-bottom: 0.5rem;">Returning Client?</h2>
              <p style="margin-bottom: 1.5rem; color: #666;">Enter your email or phone number to pre-fill your info.</p>
              <form id="lookup-form" class="reservation-form" style="max-width: 100%; gap: 1rem;">
                  <div class="form-group">
                      <input type="text" id="lookup-identifier" placeholder="Email or Phone Number" required style="text-align: center;">
                  </div>
                  <button type="submit" class="cta" id="lookup-submit-btn" style="width: 100%;">Find My Profile</button>
                  <p id="lookup-error" style="color: var(--accent-color-dark); display: none; margin-top: 10px; font-size: 0.9rem;">Profile not found.</p>
              </form>
              <div style="margin: 1.5rem 0; display: flex; align-items: center; gap: 1rem; color: #ccc;">
                  <hr style="flex: 1; border: 0; border-top: 1px solid #eee;"><span>or</span><hr style="flex: 1; border: 0; border-top: 1px solid #eee;">
              </div>
              <button id="new-client-btn" class="cta" style="width: 100%;">Continue as a new client &rarr;</button>
          </div>
      </div>`;
    document.body.insertAdjacentHTML('beforeend', modalHtml);

    const modal = document.getElementById('lookup-modal');
    // Close modal when clicking on the overlay (off the modal content)
    modal.onclick = (e) => {
        if (e.target === modal) modal.remove();
    };

    document.getElementById('close-lookup-btn').onclick = () => modal.remove();
    document.getElementById('new-client-btn').onclick = () => window.location.href = targetUrl;

    document.getElementById('lookup-form').onsubmit = async (e) => {
        e.preventDefault();
        const identifier = document.getElementById('lookup-identifier').value;
        const btn = document.getElementById('lookup-submit-btn');
        const error = document.getElementById('lookup-error');
        btn.classList.add('loading');
        error.style.display = 'none';

        try {
            const res = await fetch(`/api/lookup-client?identifier=${encodeURIComponent(identifier)}`);
            const data = await res.json();
            if (data.found) {
                const params = new URLSearchParams({
                    firstName: data.firstName, lastName: data.lastName,
                    email: data.email, phone: data.phone,
                    dob: data.dob || '', address: data.address || '',
                    hasCard: data.hasCard ? 'true' : 'false',
                    last4: data.last4 || ''
                });
                window.location.href = targetUrl.includes('?') ? `${targetUrl}&${params.toString()}` : `${targetUrl}?${params.toString()}`;
            } else { error.style.display = 'block'; }
        } catch (err) { console.error(err); } finally { btn.classList.remove('loading'); }
    };
  };

  // Intercept all Booking and OnSite links
  document.addEventListener('click', (e) => {
    const btn = e.target.closest('a, button');
    if (!btn || e.target.closest('#lookup-modal')) return;
    const href = btn.getAttribute('href') || '';
    if (href.includes('Booking.html') || href.includes('OnSiteRequest.html') || btn.classList.contains('reserve-btn')) {
        e.preventDefault();
        showLookupModal(href || '/Booking.html');
    }
  });

  // Helper function to animate elements
  const animateCard = (element, keyframes, options) => {
    return new Promise(resolve => {
      const animation = element.animate(keyframes, options);
      animation.onfinish = resolve;
    });
  };

  const onCardClick = async (e) => {
    if (isAnimating) return;
    isAnimating = true;

    originalCard = e.currentTarget;
    const { top, left, width, height } = originalCard.getBoundingClientRect();

    // 1. Create and position the clone
    const cardClone = originalCard.cloneNode(true);
    cardClone.style.position = 'fixed';
    cardClone.style.top = `${top}px`;
    cardClone.style.left = `${left}px`;
    cardClone.style.width = `${width}px`;
    cardClone.style.height = `${height}px`;
    cardClone.style.zIndex = '2000';
    cardClone.style.margin = '0';

    // 2. Hide original card and show overlay
    originalCard.style.opacity = '0';
    document.body.appendChild(cardClone);
    if (overlay) {
      overlay.style.display = 'block';
      overlay.style.pointerEvents = 'auto';
      requestAnimationFrame(() => overlay.style.opacity = '1');
    }

    // 3. Hide summary content, show detailed content
    const summary = cardClone.querySelector('.card-summary');
    const details = cardClone.querySelector('.info-box');
    summary.style.display = 'none';
    details.style.display = 'flex';
    details.style.opacity = '0'; // Start transparent

    // 4. Animate the clone expanding
    await animateCard(cardClone, [
      { top: `${top}px`, left: `${left}px`, width: `${width}px`, height: `${height}px` },
      { top: '50%', left: '50%', width: '70vw', height: '60vh', transform: 'translate(-50%, -50%)' }
    ], { duration: 400, easing: 'ease-in-out', fill: 'forwards' });

    // 5. Fade in the detailed content
    details.style.transition = 'opacity 0.3s ease-in'; // Removed the 0.1s delay
    details.style.opacity = '1';

    // 6. Add close listeners
    const closeButton = cardClone.querySelector('.close-card-btn');
    const bookNowButton = cardClone.querySelector('.book-now-btn');

    if (closeButton) {
      closeButton.addEventListener('click', (e) => {
        e.stopPropagation(); // Prevent the overlay click from also firing
        onCloseClick();
      });
    }

    if (bookNowButton) {
      bookNowButton.addEventListener('click', (e) => {
        e.preventDefault();
        e.stopPropagation();
        // Determine target URL based on button href or default to booking
        let targetUrl = bookNowButton.getAttribute('href') || '/Booking.html';
        const serviceId = cardClone.getAttribute('data-service-id');

        if (serviceId && !targetUrl.includes('service=')) {
            targetUrl += (targetUrl.includes('?') ? '&' : '?') + `service=${serviceId}`;
        }

        showLookupModal(targetUrl);
      });
    }

    if (overlay) {
      overlay.addEventListener('click', () => onCloseClick(), { once: true });
    }

    isAnimating = false;
  };

  const onCloseClick = async (url = null) => {
    if (isAnimating) return;
    isAnimating = true;

    const cardClone = document.querySelector('.card[style*="fixed"]');
    if (!cardClone || !originalCard) {
      isAnimating = false;
      return;
    }

    // 1. Fade out detailed content
    const details = cardClone.querySelector('.info-box');
    details.style.transition = 'opacity 0.2s ease-out';
    details.style.opacity = '0';

    // 2. Animate the clone shrinking
    const { top, left, width, height } = originalCard.getBoundingClientRect();
    await animateCard(cardClone, [
      { top: '50%', left: '50%', width: '70vw', height: '60vh', transform: 'translate(-50%, -50%)' },
      { top: `${top}px`, left: `${left}px`, width: `${width}px`, height: `${height}px`, transform: 'translate(0, 0)' }
    ], { duration: 400, easing: 'ease-in-out', fill: 'forwards' });

    // 3. Fade out overlay and clean up
    if (overlay) overlay.style.opacity = '0';

    setTimeout(() => {
      cardClone.remove();
      originalCard.style.opacity = '1';
      if (overlay) {
        overlay.style.pointerEvents = 'none';
        overlay.style.display = 'none';
      }
      originalCard = null;
      isAnimating = false;
      if (url && typeof url === 'string') {
        window.location.href = url; // Navigate to the booking page
      }
    }, 400); // Match the animation duration
  };

  // Attach the primary click listener to each card's "Learn More" button
  serviceCards.forEach(card => {
    const learnMoreBtn = card.querySelector('.learn-more');
    learnMoreBtn.addEventListener('click', (e) => {
      e.stopPropagation(); // Prevent the card's own click listener from firing
      onCardClick({ currentTarget: card }); // Pass the parent card to the handler
    });
  });

  // --- Smooth Scrolling for Nav Links ---
  const navLinks = document.querySelectorAll('#navMenu a[href^="#"]');

  navLinks.forEach(link => {
    link.addEventListener('click', function(e) {
      // Prevent the default instant jump
      e.preventDefault();

      const href = this.getAttribute('href');
      const targetId = href.substring(1); // Remove the '#'
      const targetElement = document.getElementById(targetId);

      // Special case for the "Home" link which might be just "#"
      if (href === '#') {
        window.scrollTo({ top: 0, behavior: 'smooth' });
      } else if (href === '#about') {
        // Special case for the "About" link to scroll below the services
        const servicesSection = document.getElementById('services');
        if (servicesSection) {
          const headerOffset = 180; // Standardized height of sticky header + label clearance
          // Calculate position at the bottom of the services section
          const padding = 30; // Extra space to stop "a little higher"
          const elementPosition = servicesSection.getBoundingClientRect().bottom + window.pageYOffset;
          const offsetPosition = elementPosition - headerOffset - padding;
          window.scrollTo({ top: offsetPosition, behavior: 'smooth' });
        }
      } else if (targetElement) {
        // Calculate the position of the target element, accounting for the sticky header
        const headerOffset = 180; // Standardized height of sticky header + label clearance
        const elementPosition = targetElement.getBoundingClientRect().top + window.pageYOffset;
        const offsetPosition = elementPosition - headerOffset;
        window.scrollTo({ top: offsetPosition, behavior: 'smooth' });
      }

      // Close the mobile menu after any link is clicked
      if (navMenu.classList.contains('is-active')) {
        navMenu.classList.remove('is-active');
      }
    });
  });

  // --- Global Form Validation Scroll Fix ---
  // Intercepts native browser "jumps" to invalid fields and adds an offset for the sticky header
  document.addEventListener('invalid', (e) => {
    e.preventDefault(); // Stop the browser from jumping instantly to the field

    if (!e.target.form) return;

    const firstInvalid = e.target.form.querySelector(':invalid');
    if (firstInvalid && e.target === firstInvalid) {
      // Find the first invalid element and its visible container
      const scrollTarget = firstInvalid.closest('.form-group, .agreement-group') || firstInvalid;
      const headerOffset = 180;
      const elementPosition = scrollTarget.getBoundingClientRect().top + window.scrollY;

      window.scrollTo({
        top: elementPosition - headerOffset,
        behavior: 'smooth'
      });

      // Focus the element after scrolling so the validation bubble appears in the right spot
      setTimeout(() => firstInvalid.focus({ preventScroll: true }), 450);
    }
  }, true); // Use capture phase to catch event before browser default
});