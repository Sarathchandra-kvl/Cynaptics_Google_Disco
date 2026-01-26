(function() {
  // 1. Clone the body so we don't mess up the actual page
  const clone = document.body.cloneNode(true);

  // 2. Remove "Junk" Elements (Ads, Menus, Footers)
  const junkSelectors = [
    'script', 'style', 'noscript', 'iframe', 
    'header', 'footer', 'nav', 
    '.ad', '.advertisement', '.cookie-banner', 
    '#sidebar', '.comments'
  ];
  
  junkSelectors.forEach(selector => {
    const elements = clone.querySelectorAll(selector);
    elements.forEach(el => el.remove());
  });

  // 3. Get text from the Cleaned DOM
  let text = clone.innerText;

  // 4. Remove excessive whitespace (tabs, double newlines)
  text = text.replace(/\s+/g, ' ').trim();

  // 5. TRUNCATE: The most important part.
  // Take only the first 2000 characters. 
  // Usually, the main idea is in the first 20% of the page.
  return {
    url: window.location.href,
    title: document.title,
    content: text.substring(0, 2000) + "..." // Limit to 2k chars
  };
})();