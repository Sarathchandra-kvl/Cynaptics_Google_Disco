// background.js

// Enable Side Panel on Action Click
chrome.sidePanel
    .setPanelBehavior({ openPanelOnActionClick: true })
    .catch((error) => console.error(error));

// 1. Listen for messages from the popup
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
    if (request.action === 'processTabs') {
        performAnalysis(request.apiKey)
            .then(sendResponse)
            .catch(err => sendResponse({ error: err.message }));
        return true; // Keep the channel open for the async response
    }
});

// 2. Main Analysis Logic
async function performAnalysis(apiKey) {
    try {
        // A. Gather Tabs
        const tabs = await chrome.tabs.query({});
        const tabContents = [];

        // B. Scrape each tab
        for (const tab of tabs) {
            if (tab.url.startsWith('chrome://') || tab.url.startsWith('edge://')) continue;

            try {
                const result = await chrome.scripting.executeScript({
                    target: { tabId: tab.id },
                    files: ['content_extractor.js']
                });

                if (result && result[0] && result[0].result) {
                    tabContents.push(result[0].result);
                }
            } catch (e) {
                // Ignore individual tab errors
                console.warn(`Skipping tab ${tab.id}:`, e);
            }
        }

        // C. Prepare the prompt
        const prompt = `
        I have these browser tabs open. I want you to act as a Project Manager.
        Review the content and generate a consolidated To-Do list.
        
        TABS DATA:
        ${JSON.stringify(tabContents)}
        
        OUTPUT FORMAT:
        - Group tasks by project/topic
        - Detect what I am likely trying to achieve
        - List specific action items
        `;

        // D. Call Groq API
        const aiResponse = await callGroq(apiKey, prompt);

        // E. Save to History
        const historyData = await chrome.storage.local.get('analysisHistory');
        const history = historyData.analysisHistory || [];

        history.unshift({
            timestamp: Date.now(),
            text: aiResponse
        });

        await chrome.storage.local.set({ analysisHistory: history });

        // F. Open Dashboard
        await chrome.tabs.create({ url: 'chrome-extension://' + chrome.runtime.id + '/dashboard.html' });

        return { success: true };

    } catch (err) {
        console.error("Analysis failed:", err);
        return { error: err.message };
    }
}

// 3. API Call Function (Using FETCH, not SDK)
async function callGroq(apiKey, prompt) {
    const response = await fetch('https://api.groq.com/openai/v1/chat/completions', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${apiKey}`
        },
        body: JSON.stringify({
            // Model from your screenshot
            model: "qwen/qwen3-32b",

            // Messages array
            messages: [
                {
                    role: "system",
                    content: "You are an expert productivity assistant. Analyze the user's browser tabs and create a structured Markdown to-do list."
                },
                { role: "user", content: prompt }
            ],

            // PARAMS from your screenshot:
            temperature: 0.6,               // As requested
            max_completion_tokens: 4096,    // Correct field for new models
            top_p: 0.95,
            reasoning_effort: "default",
            stream: false                   // Must be false for this code to work
        })
    });

    const data = await response.json();

    if (data.error) {
        throw new Error(data.error.message);
    }

    return data.choices[0].message.content;
}
