// Toggle Settings
document.getElementById('settingsBtn').addEventListener('click', () => {
    document.getElementById('settingsPanel').classList.toggle('hidden');
});

// Save API Key
document.getElementById('saveKeyBtn').addEventListener('click', () => {
    const key = document.getElementById('apiKey').value;
    if (!key.startsWith('gsk_')) {
        alert('Invalid Groq Key! It should start with "gsk_"');
        return;
    }

    chrome.storage.local.set({ 'groq_api_key': key }, () => {
        document.getElementById('keyStatus').innerText = 'Key Saved ✅';
        setTimeout(() => document.getElementById('settingsPanel').classList.add('hidden'), 1000);
    });
});

// Main Analyze Logic
document.getElementById('analyzeBtn').addEventListener('click', async () => {
    const btn = document.getElementById('analyzeBtn');
    const loader = btn.querySelector('.loader');
    const btnText = btn.querySelector('.btn-text');
    const resultContainer = document.getElementById('resultContainer');

    // UI Loading State
    btnText.innerText = 'Analyzing Tabs...';
    loader.classList.remove('hidden');
    if (resultContainer) resultContainer.classList.add('hidden');

    // Check for Key
    const data = await chrome.storage.local.get('groq_api_key');
    if (!data.groq_api_key) {
        alert('Please set your Groq API Key in settings first!');
        resetUI();
        return;
    }

    // Send to Background
    chrome.runtime.sendMessage({
        action: 'processTabs',
        apiKey: data.groq_api_key
    });

    // Close the popup immediately so the Dashboard can open
    window.close();
});

function resetUI() {
    const btn = document.getElementById('analyzeBtn');
    const loader = btn.querySelector('.loader');
    const btnText = btn.querySelector('.btn-text');
    btnText.innerText = 'Generate Action Plan';
    loader.classList.add('hidden');
}
