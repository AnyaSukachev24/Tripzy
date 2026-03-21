const runBtn = document.getElementById('runBtn');
const promptInput = document.getElementById('promptInput');
const chatDisplay = document.getElementById('chat-display');
const statDest = document.getElementById('stat-dest');
const statBudget = document.getElementById('stat-budget');
const statStatus = document.getElementById('stat-status');
const profileSummary = document.getElementById('profile-summary');
const agentThought = document.getElementById('agent-thought');
const newChatBtn = document.getElementById('newChatBtn');
const suggestionsBlock = document.getElementById('suggestions-block');

// ── Suggestion cards: click to inject prompt ──────────────
document.querySelectorAll('.suggestion-card').forEach(card => {
    card.addEventListener('click', () => {
        promptInput.value = card.dataset.prompt;
        promptInput.dispatchEvent(new Event('input')); // trigger auto-resize
        promptInput.focus();
    });
});

// API base URL: same-origin by default.
// If the file is opened directly (file://), fallback to local FastAPI server.
const API_BASE = window.location.protocol === 'file:'
    ? 'http://127.0.0.1:8000'
    : window.location.origin;

// WINDOW-SCOPED THREAD ID
// For parallel testing, always create a unique thread per browser window runtime.
// This avoids accidental context carryover between duplicated tabs/windows.
let sessionId = 'session_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
console.log('Window thread created:', sessionId);
let lastProgressMessage = '';

function mapToolToProgressMessage(toolName) {
    const name = (toolName || '').toLowerCase();

    if (name.includes('search_flights') || name.includes('cheapest_flights')) {
        return 'Searching flights...';
    }
    if (name.includes('search_hotels') || name.includes('hotel_ratings')) {
        return 'Searching hotels...';
    }
    if (name.includes('suggest_attractions') || name.includes('search_tours') || name.includes('search_points_of_interest')) {
        return 'Searching restaurants and local places...';
    }
    if (name.includes('resolve_airport_code')) {
        return 'Resolving airport codes...';
    }
    if (name.includes('create_plan')) {
        return 'Building your itinerary...';
    }
    return 'Working on your trip...';
}

function appendProgressMessage(text) {
    if (!text || text === lastProgressMessage) return;
    lastProgressMessage = text;
    appendMessage('system', text);
}

function resetForNewChat() {
    sessionId = 'session_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
    currentThreadId = null;
    lastProgressMessage = '';

    chatDisplay.innerHTML = '<div class="message agent">Hello! I\'m your AI Travel Agent. Where would you like to go today?</div>';
    promptInput.value = '';

    if (statDest) statDest.textContent = '-';
    if (statBudget) statBudget.textContent = '-';
    if (statStatus) {
        statStatus.textContent = 'Idle';
        statStatus.style.color = '';
    }

    if (profileSummary) profileSummary.textContent = 'Waiting for input...';
    agentThought.textContent = 'I\'m ready to plan your next adventure.';

    // Restore suggestions on new chat
    if (suggestionsBlock) suggestionsBlock.classList.remove('hidden');

    approvalSection.classList.add('hidden');

    console.log('New chat thread created:', sessionId);
}

function formatPreview(plan) {
    if (!plan) return "No plan details.";
    let md = `**Draft Itinerary for ${plan.destination || 'Unknown'}**\n`;
    md += `*Budget Estimate: $${plan.budget_estimate || 0}*\n\n`;

    const itinerary = plan.itinerary || [];
    itinerary.forEach(item => {
        md += `- **Day ${item.day}**: ${item.activity} ($${item.cost})\n`;
    });
    return md;
}

function appendMessage(role, text) {
    const msgDiv = document.createElement('div');
    msgDiv.className = `message ${role}`;

    if (role === 'agent') {
        msgDiv.innerHTML = marked.parse(text);
    } else {
        msgDiv.textContent = text;
    }

    chatDisplay.appendChild(msgDiv);
    chatDisplay.scrollTop = chatDisplay.scrollHeight;
}

runBtn.addEventListener('click', async () => {
    const prompt = promptInput.value.trim();
    if (!prompt) return;
    lastProgressMessage = '';

    // Reset Input
    promptInput.value = '';
    promptInput.style.height = 'auto';
    appendMessage('user', prompt);

    // Hide suggestions once the conversation starts
    if (suggestionsBlock) suggestionsBlock.classList.add('hidden');

    // Update UI Status
    runBtn.disabled = true;
    if (statStatus) {
        statStatus.textContent = 'Initializing...';
        statStatus.style.color = 'var(--accent)';
    }
    agentThought.textContent = 'Connecting to the Tripzy Engine...';

    try {
        const response = await fetch(`${API_BASE}/api/stream`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                prompt: prompt,
                thread_id: sessionId  // Pass persistent session ID
            })
        });

        if (!response.ok) {
            throw new Error(`API error ${response.status}: ${response.statusText}`);
        }
        if (!response.body) {
            throw new Error('Stream response has no body. Check server logs and proxy settings.');
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
            const { value, done } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n\n');
            buffer = lines.pop();

            for (const line of lines) {
                if (line.trim().startsWith('data: ')) {
                    const data = JSON.parse(line.trim().substring(6));
                    handleStreamEvent(data);
                }
            }
        }

    } catch (e) {
        console.error('Stream error:', e);
        console.error('Error type:', e.name);
        console.error('Error message:', e.message);
        console.error('Error stack:', e.stack);
        appendMessage('system', `Connection failed: ${e.message}. API base: ${API_BASE}. Please check the console for details.`);
        if (statStatus) statStatus.textContent = 'Offline';
    } finally {
        runBtn.disabled = false;
        if (statStatus) {
            statStatus.textContent = 'Completed';
            statStatus.style.color = 'var(--success)';
        }
    }
});

let currentThreadId = null;
const approvalSection = document.getElementById('approval-section');
const approveBtn = document.getElementById('approveBtn');
const cancelBtn = document.getElementById('cancelBtn');

newChatBtn.addEventListener('click', () => {
    if (runBtn.disabled) {
        appendMessage('system', 'Please wait for the current request to finish before starting a new chat.');
        return;
    }
    resetForNewChat();
});

function handleStreamEvent(data) {
    switch (data.type) {
        case 'status':
            agentThought.textContent = data.content;
            if (statStatus) statStatus.textContent = 'Working...';

            if (typeof data.content === 'string') {
                if (data.content.startsWith('Executing Tool:')) {
                    const match = data.content.match(/^Executing Tool:\s*([^\.\s]+).*$/i);
                    const toolName = match ? match[1] : '';
                    appendProgressMessage(mapToolToProgressMessage(toolName));
                } else if (data.content.includes('Starting Graph')) {
                    appendProgressMessage('Working on your request...');
                }
            }
            break;
        case 'node_complete':
            if (statStatus) statStatus.textContent = `Node: ${data.node}`;
            if (data.node === 'Researcher') {
                agentThought.textContent = 'Searching for local insights...';
            } else if (data.node === 'Critique') {
                agentThought.textContent = 'Reviewing plan quality...';
            }
            break;
        case 'waiting_for_approval':
            currentThreadId = data.thread_id;
            if (statStatus) {
                statStatus.textContent = 'Paused';
                statStatus.style.color = 'var(--primary)';
            }
            agentThought.textContent = 'The plan is ready for your review. Please approve to finalize.';
            if (data.preview) {
                const previewMd = formatPreview(data.preview);
                const previewEl = document.getElementById('plan-preview');
                if (previewEl) {
                    previewEl.innerHTML = marked.parse(previewMd);
                } else {
                    console.warn('plan-preview element not found - browser cache may need refresh');
                }
            }
            approvalSection.classList.remove('hidden');
            break;
        case 'final_response':
            appendMessage('agent', data.content);
            agentThought.textContent = 'Trip plan finalized.';
            break;
        case 'error':
            appendMessage('system', 'Error: ' + data.content);
            if (statStatus) statStatus.textContent = 'Error';
            break;
    }
}

approveBtn.addEventListener('click', async () => {
    if (!currentThreadId) return;

    approvalSection.classList.add('hidden');
    statStatus.textContent = 'Finalizing...';
    agentThought.textContent = 'Generating your final itinerary...';

    const response = await fetch(`${API_BASE}/api/approve`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ thread_id: currentThreadId, prompt: '' })
    });

    if (!response.ok) {
        appendMessage('system', `Approval failed: API error ${response.status}: ${response.statusText}`);
        if (statStatus) statStatus.textContent = 'Error';
        return;
    }

    const data = await response.json();
    if (data.status === 'ok') {
        appendMessage('agent', data.response);
        if (statStatus) statStatus.textContent = 'Completed';
        agentThought.textContent = 'Trip successfully planned!';
    } else {
        appendMessage('system', 'Approval failed: ' + data.error);
        agentThought.textContent = 'Failed to generate itinerary.';
    }
});

cancelBtn.addEventListener('click', () => {
    approvalSection.classList.add('hidden');
    if (statStatus) statStatus.textContent = 'Cancelled';
    agentThought.textContent = 'Approval cancelled by user.';
});

// Allow Enter to send (but Shift+Enter for new line)
promptInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        runBtn.click();
    }
});

// Auto-resize textarea as user types
promptInput.addEventListener('input', () => {
    promptInput.style.height = 'auto';
    promptInput.style.height = Math.min(promptInput.scrollHeight, 130) + 'px';
});
