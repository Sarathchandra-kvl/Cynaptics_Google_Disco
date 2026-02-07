document.addEventListener('DOMContentLoaded', () => {
    const chatContainer = document.getElementById('chat-container');
    const userInput = document.getElementById('user-input');
    const sendBtn = document.getElementById('send-btn');
    const welcomeSection = document.getElementById('welcome-section');
    const statusIndicator = document.getElementById('status-indicator');

    // Handle Suggestion Chips
    const chips = document.querySelectorAll('.suggestion-chip');
    chips.forEach(chip => {
        chip.addEventListener('click', () => {
            const text = chip.getAttribute('data-input');
            if (text) {
                userInput.value = text;
                userInput.focus();
            }
        });
    });

    // Auto-Start Analysis (Silent)
    startAnalysis();

    sendBtn.addEventListener('click', sendMessage);
    userInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') sendMessage();
    });

    async function startAnalysis() {
        // Just pinging server to wake it up or get initial context if needed
        chrome.tabs.query({}, async (tabs) => {
            const tabData = tabs.map(t => ({
                id: t.id,
                title: t.title,
                url: t.url
            }));
            try {
                fetch('http://localhost:8000/chat', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        message: "AUTO_ANALYZE_INIT",
                        tabs: tabData
                    })
                }).catch(e => console.log("Silent analysis ping failed", e));
            } catch (error) {
                console.log("Server not ready");
            }
        });
    }

    async function sendMessage() {
        const text = userInput.value.trim();
        if (!text) return;

        // 1. UI Updates
        if (welcomeSection) {
            welcomeSection.classList.add('hidden'); // Hide welcome screen on first message
            welcomeSection.style.display = 'none'; // Ensure it's gone
        }

        appendMessage(text, 'user');
        userInput.value = '';

        const loadingId = showLoading();

        // 2. Data Gathering
        chrome.tabs.query({}, async (tabs) => {
            const tabData = tabs.map(t => ({ id: t.id, title: t.title, url: t.url }));
            try {
                const response = await fetch('http://localhost:8000/chat', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ message: text, tabs: tabData })
                });
                const data = await response.json();

                removeLoading(loadingId);
                handleBackendResponse(data);

            } catch (error) {
                removeLoading(loadingId);
                appendMessage("Error: Could not reach the GenTab Brain. Is the server running? 🚨", 'error');
                console.error(error);
            }
        });
    }

    function handleBackendResponse(data) {
        // 1. Check for Actions (Dashboard/Download)
        if (data.action === 'open_dashboard' && data.dashboard_url) {

            // AUTO-OPEN dashboard in new tab!
            chrome.tabs.create({ url: data.dashboard_url, active: true });

            appendMessage(`
                <div style="display: flex; flex-direction: column; gap: 8px;">
                    <div style="display: flex; align-items: center; gap: 8px;">
                        <span style="width: 8px; height: 8px; border-radius: 50%; background: #10b981; animation: pulse 2s infinite;"></span>
                        <span style="color: #34d399; font-weight: bold; font-size: 12px; text-transform: uppercase;">Dashboard Generated</span>
                    </div>
                    <span style="color: #cbd5e1; font-size: 14px;">I've opened the dashboard in a new tab.</span>
                    <a href="${data.dashboard_url}" target="_blank" style="display: block; width: 100%; text-align: center; padding: 10px; border-radius: 12px; background: rgba(16, 185, 129, 0.1); border: 1px solid rgba(16, 185, 129, 0.2); color: #34d399; text-decoration: none; font-size: 12px; font-weight: bold; text-transform: uppercase; transition: all 0.2s;">
                        Re-open Dashboard
                    </a>
                </div>
            `, 'agent');

            // Also append the text response if it's meaningful
            if (data.response && !data.response.includes("opening it now")) {
                appendMessage(data.response, 'agent');
            }

        } else {
            // Normal Message
            if (data.response) {
                appendMessage(data.response, 'agent');
            }
        }
    }

    function appendMessage(text, sender) {
        const div = document.createElement('div');
        div.className = `message-row ${sender}`;

        const isAgent = sender === 'agent';
        const isError = sender === 'error';

        // Avatar
        const avatar = isAgent ?
            `<div class="avatar">
                <svg class="avatar-icon" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z" /></svg>
             </div>` :
            (sender === 'user' ? `` : `<div class="avatar" style="background: rgba(239, 68, 68, 0.2);"><span style="color:#ef4444; font-weight:bold;">!</span></div>`);


        // Bubble Style
        const bubbleClass = `bubble ${sender === 'user' ? 'user' : 'agent'}`;

        div.innerHTML = `
            ${isAgent || isError ? avatar : ''}
            <div class="${bubbleClass}">
                ${parseMarkdown(text)}
            </div>
        `;

        chatContainer.appendChild(div);
        chatContainer.scrollTop = chatContainer.scrollHeight;
    }

    function showLoading() {
        const id = 'loading-' + Date.now();
        const div = document.createElement('div');
        div.id = id;
        div.className = "message-row agent";
        div.innerHTML = `
            <div class="avatar" style="opacity: 0.7;">
               <svg class="avatar-icon" style="animation: pulse 1s infinite;" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z" /></svg>
            </div>
            <div class="bubble agent" style="display: flex; align-items: center; gap: 6px; padding: 14px;">
                <span style="width: 6px; height: 6px; background: #a78bfa; border-radius: 50%; animation: bounce 1s infinite;"></span>
                <span style="width: 6px; height: 6px; background: #e879f9; border-radius: 50%; animation: bounce 1s infinite 0.2s;"></span>
                <span style="width: 6px; height: 6px; background: #22d3ee; border-radius: 50%; animation: bounce 1s infinite 0.4s;"></span>
            </div>
            <style>
                @keyframes bounce { 0%, 100% { transform: translateY(0); } 50% { transform: translateY(-4px); } }
            </style>
        `;
        chatContainer.appendChild(div);
        chatContainer.scrollTop = chatContainer.scrollHeight;
        return id;
    }

    function removeLoading(id) {
        const el = document.getElementById(id);
        if (el) el.remove();
    }

    // Basic Markdown Parser for Chat
    function parseMarkdown(text) {
        if (!text) return '';

        // Links
        let html = text.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank">$1</a>');

        // Bold
        html = html.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');

        // Code blocks (inline)
        html = html.replace(/`([^`]+)`/g, '<code>$1</code>');

        // Lists
        html = html.replace(/^\s*-\s+(.*)/gm, '<li>$1</li>');
        if (html.includes('<li>')) {
            // Very basic wrapping checks
            if (!html.includes('<ul>')) {
                html = html.replace(/(<li.*<\/li>)/s, '<ul>$1</ul>');
            }
        }

        // Newlines to <br> (only if not already in block tags?)
        // Simple replace is safer for chat bubbles
        html = html.replace(/\n/g, '<br>');

        return html;
    }

});
