const runBtn = document.getElementById('runBtn');
const promptInput = document.getElementById('promptInput');
const chatDisplay = document.getElementById('chat-display');
const statDest = document.getElementById('stat-dest');
const statBudget = document.getElementById('stat-budget');
const statStatus = document.getElementById('stat-status');
const profileSummary = document.getElementById('profile-summary');
const agentThought = document.getElementById('agent-thought');

// API base URL: same-origin by default.
// If the file is opened directly (file://), fallback to local FastAPI server.
const API_BASE = window.location.protocol === 'file:'
    ? 'http://127.0.0.1:8000'
    : window.location.origin;

// PERSISTENT SESSION ID - Maintains state across multiple messages
let sessionId = sessionStorage.getItem('tripzy_session_id');
if (!sessionId) {
    sessionId = 'session_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
    sessionStorage.setItem('tripzy_session_id', sessionId);
    console.log('New session created:', sessionId);
} else {
    console.log('Resuming session:', sessionId);
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

    // Reset Input
    promptInput.value = '';
    appendMessage('user', prompt);

    // Update UI Status
    runBtn.disabled = true;
    statStatus.textContent = 'Initializing...';
    statStatus.style.color = 'var(--accent)';
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
        statStatus.textContent = 'Offline';
    } finally {
        runBtn.disabled = false;
        statStatus.textContent = 'Completed';
        statStatus.style.color = 'var(--success)';
    }
});

let currentThreadId = null;
const approvalSection = document.getElementById('approval-section');
const approveBtn = document.getElementById('approveBtn');
const cancelBtn = document.getElementById('cancelBtn');

function handleStreamEvent(data) {
    switch (data.type) {
        case 'status':
            agentThought.textContent = data.content;
            statStatus.textContent = 'Working...';
            break;
        case 'node_complete':
            statStatus.textContent = `Node: ${data.node}`;
            if (data.node === 'Researcher') {
                agentThought.textContent = 'Searching for local insights...';
            } else if (data.node === 'Critique') {
                agentThought.textContent = 'Reviewing plan quality...';
            }
            break;
        case 'waiting_for_approval':
            currentThreadId = data.thread_id;
            statStatus.textContent = 'Paused';
            statStatus.style.color = 'var(--primary)';
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
            statStatus.textContent = 'Error';
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
        statStatus.textContent = 'Error';
        return;
    }

    const data = await response.json();
    if (data.status === 'ok') {
        appendMessage('agent', data.response);
        statStatus.textContent = 'Completed';
        agentThought.textContent = 'Trip successfully planned!';
    } else {
        appendMessage('system', 'Approval failed: ' + data.error);
        agentThought.textContent = 'Failed to generate itinerary.';
    }
});

cancelBtn.addEventListener('click', () => {
    approvalSection.classList.add('hidden');
    statStatus.textContent = 'Cancelled';
    agentThought.textContent = 'Approval cancelled by user.';
});

// Allow Enter to send (but Shift+Enter for new line)
promptInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        runBtn.click();
    }
});
