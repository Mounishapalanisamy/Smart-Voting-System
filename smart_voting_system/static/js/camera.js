// Shared webcam helpers

async function startCamera(videoEl) {
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    throw new Error("Camera API unavailable. Use http://localhost:5000 or HTTPS.");
  }
  const stream = await navigator.mediaDevices.getUserMedia({
    video: { width: { ideal: 640 }, height: { ideal: 480 }, facingMode: "user" },
    audio: false
  });
  videoEl.srcObject = stream;
  await videoEl.play();
}

function captureFrame(videoEl) {
  if (!videoEl.videoWidth) return null;
  const canvas = document.createElement("canvas");
  canvas.width = videoEl.videoWidth;
  canvas.height = videoEl.videoHeight;
  canvas.getContext("2d").drawImage(videoEl, 0, 0);
  return canvas.toDataURL("image/jpeg", 0.9);
}

// Capture n frames, `delay` ms apart (used by the "Begin Scan" button)
async function captureBurst(videoEl, n, delay, onFrame) {
  const frames = [];
  for (let i = 0; i < n; i++) {
    const f = captureFrame(videoEl);
    if (f) { frames.push(f); if (onFrame) onFrame(f, i + 1, n); }
    await new Promise(r => setTimeout(r, delay));
  }
  return frames;
}
