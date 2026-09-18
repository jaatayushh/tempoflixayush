// Interactive Cyberpunk Hacker CLI & Live GitHub Tracker
async function loadLiveGitHubRepos() {
  const container = document.getElementById('github-repos-grid');
  const countEl = document.getElementById('repo-count-badge');
  const starsEl = document.getElementById('total-stars-badge');

  if (!container) return;

  try {
    const res = await fetch('https://api.github.com/users/jaatayushh/repos?sort=updated');
    if (!res.ok) throw new Error('GitHub API rate limited');
    const repos = await res.json();

    if (countEl) countEl.innerText = `${repos.length} REPOSITORIES`;

    let totalStars = 0;
    container.innerHTML = '';

    repos.forEach(repo => {
      totalStars += (repo.stargazers_count || 0);

      const card = document.createElement('div');
      card.className = 'cyber-box p-5 flex flex-col justify-between hover:border-[var(--neon-green)] transition-all';
      
      const langColor = repo.language === 'Kotlin' ? '#b026ff' : (repo.language === 'Python' ? '#ffe600' : '#00f0ff');
      
      card.innerHTML = `
        <div>
          <div class="flex items-center justify-between mb-2">
            <h3 class="font-bold text-lg text-white font-mono flex items-center gap-2">
              <span class="text-[var(--neon-cyan)]">#</span> ${repo.name}
            </h3>
            <span class="text-xs px-2 py-0.5 rounded border border-white/20 text-white/70">
              ${repo.visibility || 'public'}
            </span>
          </div>
          <p class="text-sm text-gray-400 mb-4 line-clamp-2 leading-relaxed">
            ${repo.description || 'Cybernetic engineering project.'}
          </p>
        </div>
        <div class="pt-4 border-t border-white/10 flex items-center justify-between text-xs text-gray-400">
          <div class="flex items-center gap-4">
            ${repo.language ? `<span class="flex items-center gap-1.5"><span class="w-2.5 h-2.5 rounded-full" style="background: ${langColor}"></span> ${repo.language}</span>` : ''}
            <span class="flex items-center gap-1 hover:text-[var(--neon-yellow)]"><i data-feather="star" class="w-3.5 h-3.5"></i> ${repo.stargazers_count}</span>
            <span class="flex items-center gap-1"><i data-feather="git-branch" class="w-3.5 h-3.5"></i> ${repo.forks_count}</span>
          </div>
          <a href="${repo.html_url}" target="_blank" class="text-[var(--neon-cyan)] hover:underline flex items-center gap-1 font-bold">
            SOURCE <i data-feather="external-link" class="w-3 h-3"></i>
          </a>
        </div>
      `;
      container.appendChild(card);
    });

    if (starsEl) starsEl.innerText = `${totalStars} ★ TOTAL`;
    if (window.feather) feather.replace();

  } catch (err) {
    console.warn('[GitHub Tracker] Live API fallback:', err);
    if (container) {
      container.innerHTML = `
        <div class="cyber-box p-5">
          <h3 class="font-bold text-lg text-white font-mono mb-2"><span class="text-[var(--neon-cyan)]">#</span> ayushflix</h3>
          <p class="text-sm text-gray-400 mb-4">Free & open-source, ad-free streaming for Android, TV & Web with default Hindi dubs and 1080p FHD playback.</p>
          <div class="flex items-center justify-between text-xs text-gray-400">
            <span class="text-[var(--neon-purple)]">Kotlin / Python</span>
            <a href="https://github.com/jaatayushh/ayushflix" target="_blank" class="text-[var(--neon-cyan)] font-bold">SOURCE &rarr;</a>
          </div>
        </div>
        <div class="cyber-box p-5">
          <h3 class="font-bold text-lg text-white font-mono mb-2"><span class="text-[var(--neon-cyan)]">#</span> ayushmuzic</h3>
          <p class="text-sm text-gray-400 mb-4">Modern, open-source multiplatform music player for Android, Windows, macOS, and Linux built with Kotlin Compose.</p>
          <div class="flex items-center justify-between text-xs text-gray-400">
            <span class="text-[var(--neon-purple)]">Kotlin Multiplatform</span>
            <a href="https://github.com/jaatayushh/ayushmuzic" target="_blank" class="text-[var(--neon-cyan)] font-bold">SOURCE &rarr;</a>
          </div>
        </div>
      `;
      if (window.feather) feather.replace();
    }
  }
}

// Interactive Hacker CLI Console
function initHackerTerminal() {
  const input = document.getElementById('terminal-cli-input');
  const output = document.getElementById('terminal-cli-output');
  if (!input || !output) return;

  const COMMANDS = {
    help: 'AVAILABLE COMMANDS:\n- whoami       : Display developer identity\n- skills       : Print tech stack matrix\n- repos        : List public GitHub engineering projects\n- flix         : Open Ayushflix streaming portal\n- music        : Open Ayush Muzic player\n- api          : Open Streaming REST API\n- contact      : Print encrypted contact channels\n- clear        : Clear terminal display buffer',
    whoami: 'AYUSH (jaatayushh)\nROLE: Systems Architect, Multiplatform Mobile Engineer & Streaming Protocol Specialist\nMISSION: Building zero-compromise, ad-free, high-performance multimedia applications.',
    skills: 'CYBERNETIC TECH STACK MATRIX:\n[LANGUAGES]    : Kotlin, Python, JavaScript, Modern C++, Bash\n[MULTIPLATFORM]: Kotlin Compose Multiplatform (Android, Desktop, Tizen Smart TV)\n[STREAMING]    : DASH (Dynamic Adaptive Streaming over HTTP), HLS, MSE decoders\n[NETWORKING]   : Protocol Reverse Engineering, Proxy byte-range chunking, Cloudflare Tunnels',
    repos: 'CORE REPOSITORIES:\n1. ayushflix  - Ad-free 1080p streaming with multi-audio dubs (Android, TV, Web)\n2. ayushmuzic - Hi-Res YouTube Music client (Android, Desktop, Tizen)\n3. ayushtube  - High-speed media downloader utility',
    contact: 'COMMUNICATION CHANNELS:\n- GitHub : https://github.com/jaatayushh\n- Portal : https://ayush.ai.studio',
    clear: ''
  };

  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
      const cmd = input.value.trim().toLowerCase();
      input.value = '';

      if (cmd === 'clear') {
        output.innerHTML = '';
        return;
      }

      const line = document.createElement('div');
      line.className = 'mb-2';
      line.innerHTML = `<span class="text-[var(--neon-green)]">root@ayush:~#</span> <span class="text-white">${cmd}</span>`;
      output.appendChild(line);

      const respLine = document.createElement('div');
      respLine.className = 'text-gray-300 whitespace-pre-line mb-3 font-mono text-xs pl-4 border-l-2 border-[var(--neon-cyan)]';

      if (cmd === 'flix') {
        window.location.href = '/flix';
        return;
      } else if (cmd === 'music') {
        window.location.href = '/music';
        return;
      } else if (cmd === 'api') {
        window.location.href = '/api';
        return;
      }

      if (COMMANDS[cmd]) {
        respLine.innerText = COMMANDS[cmd];
      } else if (cmd) {
        respLine.innerHTML = `<span class="text-[var(--neon-magenta)]">bash: command not found: ${cmd}. Type 'help' for manual.</span>`;
      }

      output.appendChild(respLine);
      output.scrollTop = output.scrollHeight;
    }
  });
}

document.addEventListener('DOMContentLoaded', () => {
  loadLiveGitHubRepos();
  initHackerTerminal();
});
