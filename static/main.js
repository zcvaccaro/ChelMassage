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
    overlay.style.display = 'block';
    overlay.style.pointerEvents = 'auto'; // Allow the overlay to be clicked
    requestAnimationFrame(() => overlay.style.opacity = '1');

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

    overlay.addEventListener('click', onCloseClick, { once: true }); // Close when overlay is clicked

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

    // Remove close listeners to prevent multiple clicks
    overlay.removeEventListener('click', onCloseClick); // This listener is now added with {once: true}
    cardClone.querySelector('.close-card-btn').removeEventListener('click', onCloseClick);

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
    overlay.style.opacity = '0';
    setTimeout(() => {
      cardClone.remove();
      originalCard.style.opacity = '1';
      overlay.style.pointerEvents = 'none';
      overlay.style.display = 'none';
      originalCard = null;
      isAnimating = false;
      if (url) {
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
          const headerOffset = 101; // Height of your sticky header
          // Calculate position at the bottom of the services section
          const padding = 30; // Extra space to stop "a little higher"
          const elementPosition = servicesSection.getBoundingClientRect().bottom + window.pageYOffset;
          const offsetPosition = elementPosition - headerOffset - padding;
          window.scrollTo({ top: offsetPosition, behavior: 'smooth' });
        }
      } else if (targetElement) {
        // Calculate the position of the target element, accounting for the sticky header
        const headerOffset = 101; // Height of your sticky header
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
});