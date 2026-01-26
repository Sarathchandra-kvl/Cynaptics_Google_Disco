document.addEventListener('DOMContentLoaded', loadHistory);

// Listen for updates from background script
chrome.storage.onChanged.addListener((changes, namespace) => {
    if (namespace === 'local' && changes.analysisHistory) {
        loadHistory();
    }
});

async function loadHistory() {
    const data = await chrome.storage.local.get('analysisHistory');
    const history = data.analysisHistory || [];
    const historyList = document.getElementById('historyList');
    const contentDiv = document.getElementById('content');

    if (history.length > 0) {
        const latest = history[0];
        
        // Render the main content (assuming you have a markdown parser like 'marked' loaded in HTML)
        // If you don't have 'marked', we just show plain text.
        const htmlContent = typeof marked !== 'undefined' ? marked.parse(latest.text) : `<pre>${latest.text}</pre>`;
        
        contentDiv.innerHTML = `
            <div class="timestamp">Generated: ${new Date(latest.timestamp).toLocaleString()}</div>
            <div class="markdown-body">${htmlContent}</div>
        `;
        
        // Render Sidebar List
        historyList.innerHTML = history.map((item, index) => `
            <div class="history-item" onclick="viewItem(${index})">
                📝 Plan from ${new Date(item.timestamp).toLocaleTimeString()}
            </div>
        `).join('');
    } else {
        contentDiv.innerHTML = '<p>No analysis found yet. Open tabs and click "Generate Action Plan".</p>';
    }
}

// Global function to switch views from sidebar
window.viewItem = async (index) => {
    const data = await chrome.storage.local.get('analysisHistory');
    const history = data.analysisHistory || [];
    const item = history[index];
    const contentDiv = document.getElementById('content');
    
    const htmlContent = typeof marked !== 'undefined' ? marked.parse(item.text) : `<pre>${item.text}</pre>`;
    contentDiv.innerHTML = `
        <div class="timestamp">Viewed: ${new Date(item.timestamp).toLocaleString()}</div>
        <div class="markdown-body">${htmlContent}</div>
    `;
};
