// Cyberpunk Canvas Matrix Rain Animation
function initMatrixRain(canvasId = 'matrix-canvas') {
  const canvas = document.getElementById(canvasId);
  if (!canvas) return;
  const ctx = canvas.getContext('2d');

  function resize() {
    canvas.width = window.innerWidth;
    canvas.height = window.innerHeight;
  }
  resize();
  window.addEventListener('resize', resize);

  const characters = '01アイウエオカキクケコサシスセソタチツテトナニヌネノハヒフヘホマミムメモヤユヨラリルレロワヲンABCDEF<>/{};:*+-~#$';
  const fontSize = 14;
  const columns = Math.floor(canvas.width / fontSize);
  const drops = Array(columns).fill(1);

  function draw() {
    ctx.fillStyle = 'rgba(6, 7, 10, 0.07)';
    ctx.fillRect(0, 0, canvas.width, canvas.height);

    ctx.font = ${fontSize}px 'JetBrains Mono', monospace;

    for (let i = 0; i < drops.length; i++) {
      const text = characters.charAt(Math.floor(Math.random() * characters.length));
      
      // Randomly color green or cyan
      if (Math.random() > 0.85) {
        ctx.fillStyle = '#00f0ff';
      } else {
        ctx.fillStyle = '#00ff66';
      }

      ctx.fillText(text, i * fontSize, drops[i] * fontSize);

      if (drops[i] * fontSize > canvas.height && Math.random() > 0.975) {
        drops[i] = 0;
      }
      drops[i]++;
    }
  }

  setInterval(draw, 40);
}

// Interactive Audio Visualizer Simulation
function initAudioVisualizer(canvasId = 'visualizer-canvas') {
  const canvas = document.getElementById(canvasId);
  if (!canvas) return;
  const ctx = canvas.getContext('2d');

  let isPlaying = false;
  let audioContext = null;
  let synthOsc = null;
  let synthGain = null;

  function resize() {
    canvas.width = canvas.parentElement ? canvas.parentElement.clientWidth : 600;
    canvas.height = 140;
  }
  resize();
  window.addEventListener('resize', resize);

  const barCount = 48;
  const barHeights = Array(barCount).fill(10);

  function animate() {
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    const barWidth = canvas.width / barCount;

    for (let i = 0; i < barCount; i++) {
      if (isPlaying) {
        // Dynamic pulsating bars
        const target = Math.sin(Date.now() * 0.005 + i * 0.25) * 45 + Math.random() * 35 + 20;
        barHeights[i] += (target - barHeights[i]) * 0.2;
      } else {
        // Idle ambient breathing
        const target = Math.sin(Date.now() * 0.002 + i * 0.15) * 8 + 12;
        barHeights[i] += (target - barHeights[i]) * 0.1;
      }

      const h = Math.max(4, Math.min(canvas.height - 10, barHeights[i]));
      const x = i * barWidth;
      const y = canvas.height - h;

      const grad = ctx.createLinearGradient(0, y, 0, canvas.height);
      grad.addColorStop(0, '#00f0ff');
      grad.addColorStop(0.5, '#b026ff');
      grad.addColorStop(1, '#ff0077');

      ctx.fillStyle = grad;
      ctx.shadowBlur = isPlaying ? 12 : 4;
      ctx.shadowColor = '#00f0ff';
      ctx.fillRect(x + 2, y, barWidth - 4, h);
    }

    requestAnimationFrame(animate);
  }
  animate();

  // Synthetic Web Audio Cyberpunk Beats Demo
  window.toggleCyberAudio = function() {
    const btn = document.getElementById('play-demo-btn');
    const status = document.getElementById('player-track-status');

    if (!audioContext) {
      audioContext = new (window.AudioContext || window.webkitAudioContext)();
    }

    if (!isPlaying) {
      isPlaying = true;
      if (btn) btn.innerHTML = '<i data-feather=\"pause\"></i> PAUSE DEMO STREAM';
      if (status) status.innerText = 'PLAYING: CYBER_SYNTH_WAVE_01 [24-BIT 96kHz HI-RES]';
      if (window.feather) feather.replace();
    } else {
      isPlaying = false;
      if (btn) btn.innerHTML = '<i data-feather=\"play\"></i> PLAY CYBER DEMO BEAT';
      if (status) status.innerText = 'STATUS: STANDBY // YOUTUBE MUSIC ENGINE READY';
      if (window.feather) feather.replace();
    }
  };
}

document.addEventListener('DOMContentLoaded', () => {
  initMatrixRain();
  initAudioVisualizer();
});
