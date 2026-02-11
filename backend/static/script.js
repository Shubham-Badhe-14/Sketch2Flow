
document.addEventListener('DOMContentLoaded', () => {
    mermaid.initialize({ startOnLoad: false, theme: 'default', securityLevel: 'loose' });

    const dropZone = document.getElementById('drop-zone');
    const fileInput = document.getElementById('file-input');
    const previewContainer = document.getElementById('preview-container');
    const imagePreview = document.getElementById('image-preview');
    const processBtn = document.getElementById('process-btn');

    const uploadSection = document.getElementById('upload-section');
    const progressSection = document.getElementById('progress-section');
    const resultSection = document.getElementById('result-section');
    const statusText = document.getElementById('status-text');

    const mermaidOutput = document.getElementById('mermaid-output');
    const mermaidCode = document.getElementById('mermaid-code');
    const serverRenderStatus = document.getElementById('server-render-status');
    const downloadPngBtn = document.getElementById('download-png-btn');
    const downloadMmdBtn = document.getElementById('download-mmd-btn');
    const newBtn = document.getElementById('new-btn');
    const errorToast = document.getElementById('error-toast');
    const errorMessage = document.getElementById('error-message');

    let currentJobId = null;

    // --- Upload Handling ---

    dropZone.addEventListener('click', () => fileInput.click());

    dropZone.addEventListener('dragover', (e) => {
        e.preventDefault();
        dropZone.classList.add('dragover');
    });

    dropZone.addEventListener('dragleave', () => {
        dropZone.classList.remove('dragover');
    });

    dropZone.addEventListener('drop', (e) => {
        e.preventDefault();
        dropZone.classList.remove('dragover');
        if (e.dataTransfer.files.length) {
            handleFile(e.dataTransfer.files[0]);
        }
    });

    fileInput.addEventListener('change', () => {
        if (fileInput.files.length) {
            handleFile(fileInput.files[0]);
        }
    });

    function handleFile(file) {
        if (!file.type.startsWith('image/')) {
            showError('Please upload an image file.');
            return;
        }

        const reader = new FileReader();
        reader.onload = (e) => {
            imagePreview.src = e.target.result;
            previewContainer.classList.remove('hidden');
        };
        reader.readAsDataURL(file);

        // Store file for upload
        fileInput.fileToUpload = file;
    }

    // --- API Interactions ---

    processBtn.addEventListener('click', async () => {
        const file = fileInput.fileToUpload;
        if (!file) return;

        setStep('processing');

        const formData = new FormData();
        formData.append('file', file);

        try {
            // 1. Upload
            statusText.textContent = "Uploading image...";
            const uploadRes = await fetch('/api/v1/upload', {
                method: 'POST',
                body: formData
            });

            if (!uploadRes.ok) throw new Error('Upload failed');
            const uploadData = await uploadRes.json();
            currentJobId = uploadData.job_id;

            // 2. Start Processing
            statusText.textContent = "Initializing intelligence...";
            const processRes = await fetch(`/api/v1/process/${currentJobId}`, {
                method: 'POST'
            });
            if (!processRes.ok) throw new Error('Processing start failed');

            // 3. Poll Status
            pollStatus(currentJobId);

        } catch (err) {
            console.error(err);
            showError(err.message);
            setStep('upload');
        }
    });

    async function pollStatus(jobId) {
        const interval = setInterval(async () => {
            try {
                const res = await fetch(`/api/v1/status/${jobId}`);
                if (!res.ok) throw new Error('Status check failed');
                const data = await res.json();

                statusText.textContent = `Status: ${data.status.replace('_', ' ')}...`;

                // Handle rate limit messages specifically
                if (data.status.startsWith('waiting_rate_limit')) {
                    const waitTime = data.status.split('_').pop().replace('s', '');
                    statusText.textContent = `Rate Limit Hit! ... (Waiting ${waitTime}s)`;
                    statusText.className = "text-xl font-medium text-orange-600 animate-pulse";
                } else {
                    statusText.className = "text-xl font-medium text-gray-800";
                }

                if (data.status === 'completed' || data.status === 'completed_with_warnings') {
                    clearInterval(interval);
                    fetchResults(jobId);
                } else if (data.status.startsWith('failed')) {
                    clearInterval(interval);
                    showError(`Processing failed: ${data.status}`);
                    setStep('upload');
                }
            } catch (err) {
                clearInterval(interval);
                showError(err.message);
                setStep('upload'); // Reset on serious error
            }
        }, 1000);
    }

    async function fetchResults(jobId) {
        try {
            // Get Mermaid Code
            const mmdRes = await fetch(`/api/v1/results/${jobId}/mermaid`);
            if (!mmdRes.ok) throw new Error('Failed to fetch result code');
            const mmdCode = await mmdRes.text();

            mermaidCode.value = mmdCode;

            // CRITICAL FIX: Make the result section visible BEFORE rendering
            // Mermaid cannot calculate BBox (dimensions) if the container is display:none
            setStep('result');

            // --- Client-side Render with Fresh DOM Strategy ---

            // Function to render code into the container
            const renderDiagram = async (code) => {
                // 1. Clear container completely
                mermaidOutput.innerHTML = '';

                // 2. Create a FRESH element for Mermaid to consume
                // Using a div with a unique ID ensures no caching conflicts
                const uniqueId = `mermaid-${Date.now()}`;
                const graphDiv = document.createElement('pre');
                graphDiv.id = uniqueId;
                graphDiv.className = 'mermaid';
                graphDiv.textContent = code;
                // graphDiv.style.visibility = 'hidden'; // REMOVED: Don't hide it, just let it render. BBox needs it.
                mermaidOutput.appendChild(graphDiv);

                // 3. Run Mermaid on the new element
                await mermaid.run({
                    nodes: [graphDiv]
                });

                // 4. Post-processing: Ensure size
                const svg = graphDiv.querySelector('svg');
                if (svg) {
                    svg.style.width = '100%';
                    svg.style.height = 'auto'; // allow scaling
                    svg.style.maxWidth = '100%';
                }
            };

            try {
                // Try Vertical (TD) first
                await renderDiagram(mmdCode);
            } catch (renderErr) {
                console.warn("Mermaid TD render failed, retrying with LR layout...", renderErr);

                // Fallback: Try Left-Right
                const mmdCodeLR = mmdCode.replace('flowchart TD', 'flowchart LR');
                try {
                    await renderDiagram(mmdCodeLR);
                    mermaidCode.value = mmdCodeLR;
                } catch (retryErr) {
                    console.error("Mermaid LR render failed too", retryErr);
                    mermaidOutput.innerHTML = `<p class="text-red-500 p-4 font-bold">Render Failed: The diagram is too complex.</p><p class="text-gray-500 px-4 text-sm">${retryErr.message}</p>`;
                }
            }

            // Hide server status since we are in purely client-side mode
            if (serverRenderStatus && serverRenderStatus.parentElement) {
                serverRenderStatus.parentElement.style.display = 'none';
            }

        } catch (err) {
            console.error(err);
            showError("Could not render results. " + err.message);
        }
    }

    // --- Downloads ---

    // --- Downloads & Actions ---

    downloadMmdBtn.addEventListener('click', () => {
        if (!mermaidCode.value) return;
        const blob = new Blob([mermaidCode.value], { type: 'text/plain' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `diagram-${currentJobId || 'export'}.mmd`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    });

    const toggleOrientationBtn = document.getElementById('toggle-orientation-btn');
    toggleOrientationBtn.addEventListener('click', async () => {
        if (!mermaidCode.value) return;

        let code = mermaidCode.value;
        if (code.includes('flowchart TD')) {
            code = code.replace('flowchart TD', 'flowchart LR');
        } else if (code.includes('flowchart LR')) {
            code = code.replace('flowchart LR', 'flowchart TD');
        } else {
            // Default if missing
            code = 'flowchart LR\n' + code;
        }

        mermaidCode.value = code;
        mermaidCode.value = code;

        // Manual Re-render using the same logic as above
        mermaidOutput.innerHTML = '';
        const graphDiv = document.createElement('pre');
        graphDiv.className = 'mermaid';
        graphDiv.textContent = code;
        mermaidOutput.appendChild(graphDiv);

        try {
            await mermaid.run({ nodes: [graphDiv] });
            // resize fix
            const svg = graphDiv.querySelector('svg');
            if (svg) { svg.style.width = '100%'; svg.style.height = 'auto'; }
        } catch (err) {
            showError("Layout rotation failed: " + err.message);
        }
    });

    downloadPngBtn.addEventListener('click', () => {
        const svg = mermaidOutput.querySelector('svg');
        if (!svg) {
            showError("No diagram to download.");
            return;
        }

        // Serializing SVG to string
        const serializer = new XMLSerializer();
        let source = serializer.serializeToString(svg);

        // Add namespaces
        if (!source.match(/^<svg[^>]+xmlns="http\:\/\/www\.w3\.org\/2000\/svg"/)) {
            source = source.replace(/^<svg/, '<svg xmlns="http://www.w3.org/2000/svg"');
        }
        if (!source.match(/^<svg[^>]+xmlns:xlink/)) {
            source = source.replace(/^<svg/, '<svg xmlns:xlink="http://www.w3.org/1999/xlink"');
        }

        // Restore explicit sizes if missing (Mermaid sometimes uses 100%)
        const bbox = svg.getBoundingClientRect();
        const width = bbox.width * 2; // High-res
        const height = bbox.height * 2;

        const canvas = document.createElement('canvas');
        canvas.width = width;
        canvas.height = height;
        const ctx = canvas.getContext('2d');
        ctx.fillStyle = '#ffffff';
        ctx.fillRect(0, 0, width, height); // White background

        const img = new Image();
        img.onload = () => {
            ctx.drawImage(img, 0, 0, width, height);
            const a = document.createElement('a');
            a.download = `flowchart-${currentJobId || Date.now()}.png`;
            a.href = canvas.toDataURL('image/png');
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
        };
        img.onerror = (e) => showError("Failed to generate PNG image.");

        // Convert SVG string to base64 for Image.src
        img.src = 'data:image/svg+xml;base64,' + btoa(unescape(encodeURIComponent(source)));
    });

    newBtn.addEventListener('click', () => {
        setStep('upload');
        fileInput.value = '';
        fileInput.fileToUpload = null;
        imagePreview.src = '#';
        previewContainer.classList.add('hidden');
        mermaidOutput.innerHTML = '';
        mermaidOutput.removeAttribute('data-processed'); // Reset mermaid attribute
        mermaidCode.value = '';
        currentJobId = null;
    });


    // --- Helpers ---

    function setStep(step) {
        uploadSection.classList.add('hidden');
        progressSection.classList.add('hidden');
        resultSection.classList.add('hidden');

        if (step === 'upload') uploadSection.classList.remove('hidden');
        if (step === 'processing') progressSection.classList.remove('hidden');
        if (step === 'result') resultSection.classList.remove('hidden');
    }

    function showError(msg) {
        errorMessage.textContent = msg;
        errorToast.classList.remove('hidden');
        setTimeout(() => errorToast.classList.add('hidden'), 5000);
    }
});
