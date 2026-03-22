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
let sessionId = 'session_' + (typeof crypto !== 'undefined' && crypto.randomUUID
    ? crypto.randomUUID()
    : Date.now() + '_' + Math.random().toString(36).substr(2, 9));
console.log('Window thread created:', sessionId);
let lastProgressMessage = '';
let lastUserPrompt = '';

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
        msgDiv.innerHTML = (typeof DOMPurify !== 'undefined')
            ? DOMPurify.sanitize(marked.parse(text))
            : marked.parse(text);
    } else {
        msgDiv.textContent = text;
    }

    chatDisplay.appendChild(msgDiv);
    chatDisplay.scrollTop = chatDisplay.scrollHeight;
}

function appendAgentMessage(text, steps) {
    const wrapper = document.createElement('div');
    wrapper.className = 'agent-message-wrapper';

    // ── Agent response bubble ──
    const msgDiv = document.createElement('div');
    msgDiv.className = 'message agent';
    msgDiv.innerHTML = marked.parse(text);
    wrapper.appendChild(msgDiv);

    // ── Toggle button for steps ──
    const stepCount = (steps || []).length;
    const btn = document.createElement('button');
    btn.className = 'btn-run-agent';
    btn.textContent = stepCount > 0 ? `▶ Show Steps (${stepCount})` : 'No Steps';
    if (stepCount === 0) btn.disabled = true;
    wrapper.appendChild(btn);

    // ── Steps panel (hidden initially) ──
    const stepsPanel = document.createElement('div');
    stepsPanel.className = 'steps-panel hidden';
    wrapper.appendChild(stepsPanel);

    if (stepCount > 0) {
        // Populate steps immediately (data already available)
        stepsPanel.innerHTML = `<div class="steps-header">Agent Steps (${stepCount} total)</div>`;
        steps.forEach((step, i) => {
            const item = document.createElement('div');
            item.className = 'step-item';
            item.innerHTML = `
                <div class="step-title">
                    <span class="step-num">${i + 1}</span>
                    <span class="step-module">${escapeHtml(step.module || 'Unknown')}</span>
                </div>
                <div class="step-field"><span class="step-label">Prompt</span><pre class="step-content">${escapeHtml(String(step.prompt || ''))}</pre></div>
                <div class="step-field"><span class="step-label">Response</span><pre class="step-content">${escapeHtml(String(step.response || ''))}</pre></div>
            `;
            stepsPanel.appendChild(item);
        });

        // Toggle open/close
        btn.addEventListener('click', () => {
            const isHidden = stepsPanel.classList.toggle('hidden');
            btn.textContent = isHidden
                ? `▶ Show Steps (${stepCount})`
                : `▼ Hide Steps (${stepCount})`;
            if (!isHidden) chatDisplay.scrollTop = chatDisplay.scrollHeight;
        });
    }

    chatDisplay.appendChild(wrapper);
    chatDisplay.scrollTop = chatDisplay.scrollHeight;
}

function escapeHtml(str) {
    return str.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

runBtn.addEventListener('click', async () => {
    const prompt = promptInput.value.trim();
    if (!prompt) return;
    lastProgressMessage = '';

    // Reset Input
    promptInput.value = '';
    promptInput.style.height = 'auto';
    lastUserPrompt = prompt;
    appendMessage('user', prompt);

    // Hide suggestions once the conversation starts
    if (suggestionsBlock) suggestionsBlock.classList.add('hidden');

    // Update UI Status
    runBtn.disabled = true;
    if (statStatus) {
        statStatus.textContent = 'Running...';
        statStatus.style.color = 'var(--accent)';
    }
    agentThought.textContent = 'Calling the Tripzy Agent...';

    // ── Placeholder bubble while waiting ──
    const loadingDiv = document.createElement('div');
    loadingDiv.className = 'message agent loading-bubble';
    loadingDiv.textContent = 'Thinking…';
    chatDisplay.appendChild(loadingDiv);
    chatDisplay.scrollTop = chatDisplay.scrollHeight;

    try {
        const res = await fetch(`${API_BASE}/api/execute`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ prompt: prompt, thread_id: sessionId })
        });

        loadingDiv.remove();

        const data = await res.json();

        if (data.status === 'error') {
            appendMessage('system', `Error: ${data.error || 'Unknown error'}`);
            if (statStatus) statStatus.textContent = 'Error';
            return;
        }

        // For combined requests (flights + hotels etc.), each stage gets its own bubble.
        if (data.responses && data.responses.length > 1) {
            data.responses.forEach((r, idx) => {
                const isLast = idx === data.responses.length - 1;
                appendAgentMessage(r, isLast ? (data.steps || []) : []);
            });
        } else {
            appendAgentMessage(data.response || '(no response)', data.steps || []);
        }

        agentThought.textContent = 'Done.';
        if (statStatus) {
            statStatus.textContent = 'Completed';
            statStatus.style.color = 'var(--success)';
        }

    } catch (e) {
        loadingDiv.remove();
        console.error('Execute error:', e);
        appendMessage('system', `Connection failed: ${e.message}. API base: ${API_BASE}.`);
        if (statStatus) statStatus.textContent = 'Offline';
    } finally {
        runBtn.disabled = false;
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
            agentThought.textContent = 'Waiting for your confirmation.';
            // Show the approval question / option summary as a chat bubble
            if (data.message) {
                appendAgentMessage(data.message, []);
            }
            if (data.preview) {
                const previewMd = formatPreview(data.preview);
                const previewEl = document.getElementById('plan-preview');
                if (previewEl) {
                    previewEl.innerHTML = (typeof DOMPurify !== 'undefined')
                        ? DOMPurify.sanitize(marked.parse(previewMd))
                        : marked.parse(previewMd);
                } else {
                    console.warn('plan-preview element not found - browser cache may need refresh');
                }
            }
            approvalSection.classList.remove('hidden');
            break;
        case 'final_response':
            appendAgentMessage(data.content, []);
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
