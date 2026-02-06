document.addEventListener('DOMContentLoaded', () => {
    const chatHistory = document.getElementById('chat-history');
    const userInput = document.getElementById('userInput');
    const sendBtn = document.getElementById('sendBtn');

    // Scroll to bottom
    const scrollToBottom = () => {
        chatHistory.scrollTop = chatHistory.scrollHeight;
    };

    const addMessage = (text, isUser = false) => {
        const div = document.createElement('div');
        div.className = `message ${isUser ? 'user-message' : 'ai-message'}`;
        div.textContent = text;
        chatHistory.appendChild(div);
        scrollToBottom();
    };

    const sendMessage = async () => {
        const text = userInput.value.trim();
        if (!text) return;

        addMessage(text, true);
        userInput.value = '';

        try {
            // Get Tabs
            const tabs = await chrome.tabs.query({});
            const tabData = tabs.map(t => ({
                id: t.id,
                title: t.title,
                url: t.url
            }));

            // Send to Backend
            const response = await fetch('http://localhost:8000/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    message: text,
                    tabs: tabData
                })
            });

            const data = await response.json();

            if (data.response) {
                addMessage(data.response);
            }

            if (data.action === 'open_dashboard' && data.dashboard_url) {
                chrome.tabs.create({ url: data.dashboard_url });
                addMessage("Opening dashboard in a new tab...");
            }

        } catch (error) {
            console.error(error);
            addMessage("Error connecting to the Intelligence Layer. Is the Python server running?", false);
        }
    };

    sendBtn.addEventListener('click', sendMessage);
    userInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') sendMessage();
    });
});
