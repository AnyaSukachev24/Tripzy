document.getElementById('runBtn').addEventListener('click', async () => {
    const prompt = document.getElementById('promptInput').value;
    const btn = document.getElementById('runBtn');
    const status = document.getElementById('status');
    const outputSection = document.getElementById('output-section');
    const responseContainer = document.getElementById('responseContainer');
    const debugLog = document.getElementById('debugLog');

    if (!prompt.trim()) return;

    // Reset UI
    btn.disabled = true;
    status.classList.remove('hidden');
    status.textContent = "Agent is thinking... (This may take 30-60s)";
    outputSection.classList.add('hidden');
    responseContainer.innerHTML = '';
    debugLog.textContent = '';

    try {
        const response = await fetch('/api/execute', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ prompt: prompt })
        });

        const data = await response.json();

        if (data.status === 'ok') {
            // Render Markdown
            responseContainer.innerHTML = marked.parse(data.response);
            
            // Render Debug Steps
            if (data.steps && data.steps.length > 0) {
                debugLog.textContent = JSON.stringify(data.steps, null, 2);
            } else {
                debugLog.textContent = "No debug steps returned.";
            }

            outputSection.classList.remove('hidden');
        } else {
            alert('Error: ' + data.response);
        }

    } catch (e) {
        console.error(e);
        alert('Failed to connect to server.');
    } finally {
        btn.disabled = false;
        status.classList.add('hidden');
    }
});
