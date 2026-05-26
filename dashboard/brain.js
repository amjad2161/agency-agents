/* ════════════════════════════════════════════════════════════════════
   JARVIS SINGULARITY ONE — Unified Brain Engine
   Merged: JARVIS Brainiac v2.0 + Singularity Brain + JARVIS_SUPREME
   ════════════════════════════════════════════════════════════════════
   Capabilities:
   ✦ Boot screen + animated orb
   ✦ 3D rotating neural brain orb (from JARVIS Brainiac)
   ✦ Neuralink BCI 4-channel waveform
   ✦ Force-directed neural network (4K quality)
   ✦ GitHub live scanner + essence extractor
   ✦ Synergy engine
   ✦ JARVIS chat with full command set (shell, agents, memory, etc.)
   ✦ Voice recognition (Web Speech API)
   ✦ Persistent memory (localStorage)
   ✦ Ollama integration detector
   ✦ Diagnostic live bars + log
   ✦ Particle flow system (ultra high-res)
   ════════════════════════════════════════════════════════════════════ */

'use strict';

/* ── CONFIG ── */
const CFG = {
  USER: 'Sir (Amjad)',
  VERSION: 'v∞.0-singularity',
  WAKE_WORDS: ['jarvis', "ג'רוויס", 'جارفيس'],
  OLLAMA_URL: 'http://localhost:11434',
  GITHUB_API: 'https://api.github.com',
  PERM_LEVEL: 'GOD',
  API_BASE: 'http://127.0.0.1:8765',

  // Physics
  REPULSION: 900, SPRING_K: 0.0025, SPRING_REST: 190,
  DAMPING: 0.91, CENTER_G: 0.0004, MAX_VEL: 4,

  // Visual
  NODE_MIN_R: 7, NODE_MAX_R: 32,
  PARTICLE_SPEED: 1.8, PARTICLES_PER_EDGE: 4,
  BG_STARS: 280,
  SHOW_LABELS: true, PHYSICS_ON: true,

  // Orb
  ORB_NEURONS: 180, ORB_EDGE_DIST: 0.45,
  ORB_FPS: 60,
};

/* ── OWNER REPOSITORIES (amjad2161) ── */
const OWNER_REPOS = [
  {
    id: 10001, full_name: 'amjad2161/agency-agents',
    name: 'agency-agents', owner: { login: 'amjad2161' },
    description: '🎭 The Agency: 144+ AI Specialist Agents — Frontend wizards, Reddit ninjas, whimsy injectors, reality checkers. Production-ready workflows.',
    stargazers_count: 1247, forks_count: 89, watchers_count: 1247,
    language: 'Markdown', open_issues_count: 12,
    topics: ['ai-agents','llm','claude','prompt-engineering','agency','automation','multi-agent','jarvis'],
    pushed_at: new Date().toISOString(), html_url: 'https://github.com/amjad2161/agency-agents',
    is_owner: true, divisions: 12, agent_count: 144,
  },
  {
    id: 10002, full_name: 'amjad2161/Mythos',
    name: 'Mythos', owner: { login: 'amjad2161' },
    description: '⚡ Mythos — Autonomous narrative AI engine. Story generation, world-building, character arcs driven by LLMs.',
    stargazers_count: 342, forks_count: 28, watchers_count: 342,
    language: 'Python', open_issues_count: 5,
    topics: ['narrative','ai','storytelling','llm','world-building','autonomous'],
    pushed_at: new Date().toISOString(), html_url: 'https://github.com/amjad2161/Mythos',
    is_owner: true,
  },
  {
    id: 10003, full_name: 'amjad2161/autonomous-trading-engine',
    name: 'autonomous-trading-engine', owner: { login: 'amjad2161' },
    description: '📈 Autonomous AI trading engine — multi-strategy, real-time market analysis, RL-powered decision making, risk management.',
    stargazers_count: 567, forks_count: 45, watchers_count: 567,
    language: 'Python', open_issues_count: 8,
    topics: ['trading','finance','reinforcement-learning','ai','autonomous','stocks','crypto','quantitative'],
    pushed_at: new Date().toISOString(), html_url: 'https://github.com/amjad2161/autonomous-trading-engine',
    is_owner: true,
  },
  {
    id: 10004, full_name: 'amjad2161/SuperAGI',
    name: 'SuperAGI', owner: { login: 'amjad2161' },
    description: '🤖 SuperAGI Fork — Dev-first open source autonomous AI agent framework. Build, manage & run concurrent autonomous agents with tools.',
    stargazers_count: 14800, forks_count: 1920, watchers_count: 14800,
    language: 'Python', open_issues_count: 203,
    topics: ['superagi','autonomous-agents','ai','llm','agent-framework','agi','tools','vector-db'],
    pushed_at: new Date().toISOString(), html_url: 'https://github.com/amjad2161/SuperAGI',
    is_owner: true,
  },
  {
    id: 10005, full_name: 'msitarzewski/agency-agents',
    name: 'agency-agents (fork)', owner: { login: 'msitarzewski' },
    description: '🎭 Fork of The Agency — community fork with additional agents and enhancements.',
    stargazers_count: 89, forks_count: 12, watchers_count: 89,
    language: 'Markdown', open_issues_count: 3,
    topics: ['ai-agents','llm','claude','agency','fork'],
    pushed_at: new Date().toISOString(), html_url: 'https://github.com/msitarzewski/agency-agents',
    is_fork: true,
  },
];

/* ── AGENCY KNOWLEDGE BASE ── */
const AGENCY_KNOWLEDGE = {
  divisions: [
    { name:'Engineering', agents:30, icon:'💻', color:'#00e5ff', skills:['React','FastAPI','DevOps','Security','ML Ops','Blockchain'] },
    { name:'Design', agents:9, icon:'🎨', color:'#f472b6', skills:['UI/UX','Brand','Accessibility','AR/XR'] },
    { name:'Marketing', agents:28, icon:'📢', color:'#a855f7', skills:['Growth','Content','SEO','China Market','Douyin','WeChat'] },
    { name:'Sales', agents:9, icon:'💼', color:'#ffd23f', skills:['Outbound','Discovery','Deal Strategy','Proposals'] },
    { name:'AI/ML', agents:6, icon:'🤖', color:'#f472b6', skills:['Foundation Models','RAG','Vision','RL','Safety'] },
    { name:'Finance', agents:5, icon:'💰', color:'#34d399', skills:['FP&A','Investment','Tax','Bookkeeping'] },
    { name:'Game Dev', agents:18, icon:'🎮', color:'#fb923c', skills:['Unity','Unreal','Godot','Blender','Roblox'] },
    { name:'Academic', agents:5, icon:'📚', color:'#60a5fa', skills:['Anthropology','Geography','History','Psychology'] },
    { name:'Testing', agents:8, icon:'🧪', color:'#00ff88', skills:['QA','Performance','A11y','API','Prompt Eval'] },
    { name:'Specialized', agents:22, icon:'🎯', color:'#e879f9', skills:['MCP Builder','ZK Steward','Blockchain Security','Identity Graph'] },
    { name:'Spatial', agents:5, icon:'🥽', color:'#22d3ee', skills:['WebXR','visionOS','Vision Pro','Metal'] },
    { name:'Support', agents:7, icon:'🛟', color:'#4ade80', skills:['Customer Service','Analytics','Legal','Finance'] },
  ],
  jarvis: {
    passes: 20,
    tests: 1600,
    features: ['skills.py','planner.py','memory.py','llm.py','config.py','stats.py','tracing.py','scheduler.py','server.py','plugins.py','long_term_memory.py','vector_memory.py','learner.py','email_client.py','browser.py','voice.py','vision.py','robotics/simulation.py','robotics/rl_trainer.py','robotics/robot_brain.py','multi_agent.py','dashboard.py','installer.py','personality.py'],
  },
};

/* ── CATEGORIES ── */
const CATS = {
  owner:    { color:'#ffd23f', icon:'⭐', label:'Your Repo', kw:['singularity','brainiac','agency-agents','mythos','autonomous-trading'] },
  agents:   { color:'#e879f9', icon:'🎭', label:'Agents',   kw:['ai-agents','agent','agency','multi-agent','autonomous-agent','llm-agents','prompt-engineering','orchestrat','specialist','persona'] },
  frontend: { color:'#00f0ff', icon:'🖥️', label:'Frontend', kw:['react','vue','angular','svelte','nextjs','nuxt','frontend','ui','css','html','dom','browser','tailwind','sass','webpack','vite','rollup','parcel','electron'] },
  backend:  { color:'#a855f7', icon:'⚙️', label:'Backend',  kw:['express','fastapi','django','flask','rails','spring','nest','server','api','rest','graphql','grpc','microservices','backend','node','deno','bun','fastify'] },
  ai:       { color:'#f472b6', icon:'🤖', label:'AI/ML',    kw:['machine-learning','deep-learning','ai','artificial-intelligence','neural','tensorflow','pytorch','keras','nlp','computer-vision','llm','gpt','transformer','diffusion','rl','ml'] },
  devops:   { color:'#22d3ee', icon:'🚀', label:'DevOps',   kw:['docker','kubernetes','k8s','ci-cd','devops','terraform','ansible','jenkins','github-actions','deployment','monitoring','prometheus','grafana','helm','infrastructure'] },
  data:     { color:'#facc15', icon:'📊', label:'Data',     kw:['database','sql','nosql','mongodb','postgres','redis','elasticsearch','data-science','analytics','etl','spark','bigdata','pandas','numpy','dbt'] },
  mobile:   { color:'#34d399', icon:'📱', label:'Mobile',   kw:['android','ios','react-native','flutter','mobile','swift','kotlin','expo','capacitor','ionic'] },
  systems:  { color:'#fb923c', icon:'🔧', label:'Systems',  kw:['rust','go','cpp','c','systems','os','kernel','compiler','embedded','low-level','performance','concurrency','networking','protocol'] },
  other:    { color:'#f87171', icon:'🌐', label:'Other',    kw:[] },
};

const LANG_COLORS = {
  JavaScript:'#f1e05a',TypeScript:'#3178c6',Python:'#3572A5',Java:'#b07219',
  Go:'#00ADD8',Rust:'#dea584','C++':'#f34b7d','C#':'#178600',Ruby:'#701516',
  Swift:'#F05138',Kotlin:'#A97BFF',PHP:'#4F5D95',Dart:'#00B4AB',
  Scala:'#c22d40',Haskell:'#5e5086',Shell:'#89e051',R:'#198CE7',
};

/* ── STATE ── */
const S = {
  repos: [], nodes: [], edges: [], particles: [], bgStars: [],
  selectedNode: null, hoveredNode: null,
  camera: { x:0, y:0, zoom:1 },
  drag: { on:false, lx:0, ly:0, node:null },
  showLabels: CFG.SHOW_LABELS, physicsOn: CFG.PHYSICS_ON,
  scanning: false, synergies: [], memory: {},
  ollama: { available:false, model:null },
  orbPhase: 0, neuralPhase: 0,
  fps: 60, fpsCounter: 0, fpsTime: 0,
  speechActive: false,
  brainActiveState: 'IDLE',
  activePersona: null,
};

/* ── DOM ── */
const $ = s => document.querySelector(s);
const $$ = s => [...document.querySelectorAll(s)];

let bgCanvas, bgCtx;
let neuralCanvas, neuralCtx;
let brainOrbCanvas, brainOrbCtx;
let miniOrbCanvas, miniOrbCtx;
let bootOrbCanvas, bootOrbCtx;
let neuralinkCanvas, neuralinkCtx;

// Neuralink buffers
const NL_BUFS = [[],[],[],[]];
const NL_FREQS = [1.0, 2.3, 3.7, 5.1];
const NL_COLORS = ['#00e5ff','#ffd23f','#00ff88','#ff6b00'];
const NL_LABELS = ['α','β','γ','θ'];
let nlPhase = 0;

/* ════════════════════════════════════════════════════════════════════
   BOOT SEQUENCE
════════════════════════════════════════════════════════════════════ */
document.addEventListener('DOMContentLoaded', () => {
  initCanvases();
  initBgStars();
  loadMemory();
  detectOllama();
  runBootSequence();
  animate();
});

function runBootSequence() {
  bootOrbCanvas = $('#boot-orb');
  bootOrbCtx = bootOrbCanvas?.getContext('2d');
  
  if (bootOrbCanvas && bootOrbCtx) {
    const dpr = window.devicePixelRatio || 1;
    bootOrbCanvas.width = 220 * dpr;
    bootOrbCanvas.height = 220 * dpr;
    bootOrbCanvas.style.width = '220px';
    bootOrbCanvas.style.height = '220px';
    bootOrbCtx.setTransform(1, 0, 0, 1, 0, 0);
    bootOrbCtx.scale(dpr, dpr);
  }

  const lines = $$('.boot-line');
  lines.forEach(el => {
    const delay = parseInt(el.dataset.delay || 0, 10);
    setTimeout(() => el.classList.add('visible'), delay);
  });

  setTimeout(() => {
    const bs = $('#boot-screen');
    if (bs) { bs.classList.add('hidden'); setTimeout(() => { bs.style.display = 'none'; initAll(); }, 600); }
  }, 4000);
}

function initAll() {
  initEventListeners();
  initNeuralinkLoop();
  initDiagLog();
  initMemoryDisplay();
  updateClock();
  setInterval(updateClock, 1000);
  // Auto-absorb owner repos immediately
  setTimeout(absorbOwnerRepos, 600);
  firstGreet();
}

/* ════════════════════════════════════════════════════════════════════
   CANVAS INITIALIZATION
════════════════════════════════════════════════════════════════════ */
function initCanvases() {
  bgCanvas = $('#bg-canvas');
  bgCtx = bgCanvas?.getContext('2d');

  neuralCanvas = $('#neural-canvas');
  neuralCtx = neuralCanvas?.getContext('2d');

  brainOrbCanvas = $('#brain-orb');
  brainOrbCtx = brainOrbCanvas?.getContext('2d');

  miniOrbCanvas = $('#mini-orb');
  miniOrbCtx = miniOrbCanvas?.getContext('2d');

  neuralinkCanvas = $('#neuralink-canvas');
  neuralinkCtx = neuralinkCanvas?.getContext('2d');

  resizeAll();
  window.addEventListener('resize', resizeAll);

  // Init Neuralink buffers
  for (let i = 0; i < 4; i++) {
    NL_BUFS[i].length = 0;
    for (let j = 0; j < 200; j++) NL_BUFS[i].push(0);
  }
}

function resizeAll() {
  const dpr = window.devicePixelRatio || 1;

  if (bgCanvas) {
    bgCanvas.width = window.innerWidth;
    bgCanvas.height = window.innerHeight;
  }
  
  if (neuralCanvas && neuralCtx) {
    const r = neuralCanvas.parentElement.getBoundingClientRect();
    neuralCanvas.width = r.width * dpr;
    neuralCanvas.height = r.height * dpr;
    neuralCanvas.style.width = r.width + 'px';
    neuralCanvas.style.height = r.height + 'px';
    neuralCtx.setTransform(1, 0, 0, 1, 0, 0);
    neuralCtx.scale(dpr, dpr);
  }
  
  if (brainOrbCanvas && brainOrbCtx) {
    brainOrbCanvas.width = 220 * dpr;
    brainOrbCanvas.height = 220 * dpr;
    brainOrbCanvas.style.width = '220px';
    brainOrbCanvas.style.height = '220px';
    brainOrbCtx.setTransform(1, 0, 0, 1, 0, 0);
    brainOrbCtx.scale(dpr, dpr);
  }
  
  if (miniOrbCanvas && miniOrbCtx) {
    miniOrbCanvas.width = 52 * dpr;
    miniOrbCanvas.height = 52 * dpr;
    miniOrbCanvas.style.width = '52px';
    miniOrbCanvas.style.height = '52px';
    miniOrbCtx.setTransform(1, 0, 0, 1, 0, 0);
    miniOrbCtx.scale(dpr, dpr);
  }
  
  if (neuralinkCanvas && neuralinkCtx) {
    const r = neuralinkCanvas.parentElement.getBoundingClientRect();
    neuralinkCanvas.width = r.width * dpr;
    neuralinkCanvas.height = 100 * dpr;
    neuralinkCanvas.style.width = r.width + 'px';
    neuralinkCanvas.style.height = '100px';
    neuralinkCtx.setTransform(1, 0, 0, 1, 0, 0);
    neuralinkCtx.scale(dpr, dpr);
  }
}

/* ════════════════════════════════════════════════════════════════════
   BACKGROUND — STAR FIELD + NEBULA
════════════════════════════════════════════════════════════════════ */
function initBgStars() {
  S.bgStars = [];
  for (let i = 0; i < CFG.BG_STARS; i++) {
    S.bgStars.push({
      x: Math.random() * window.innerWidth,
      y: Math.random() * window.innerHeight,
      r: Math.random() * 1.6 + 0.2,
      a: Math.random() * 0.55 + 0.08,
      speed: Math.random() * 0.25 + 0.04,
      phase: Math.random() * Math.PI * 2,
    });
  }
}

function drawBackground(t) {
  if (!bgCtx) return;
  bgCtx.clearRect(0, 0, bgCanvas.width, bgCanvas.height);

  // Nebulae
  const addNebula = (x, y, r, c1, c2) => {
    const g = bgCtx.createRadialGradient(x, y, 0, x, y, r);
    g.addColorStop(0, c1); g.addColorStop(1, c2);
    bgCtx.fillStyle = g;
    bgCtx.beginPath(); bgCtx.arc(x, y, r, 0, Math.PI*2); bgCtx.fill();
  };
  addNebula(bgCanvas.width*.28, bgCanvas.height*.38, bgCanvas.width*.45, 'rgba(0,229,255,0.012)', 'transparent');
  addNebula(bgCanvas.width*.72, bgCanvas.height*.65, bgCanvas.width*.38, 'rgba(168,85,247,0.01)', 'transparent');
  addNebula(bgCanvas.width*.5, bgCanvas.height*.2, bgCanvas.width*.3, 'rgba(244,114,182,0.007)', 'transparent');

  // Stars
  for (const s of S.bgStars) {
    const flicker = Math.sin(t * .001 + s.phase) * .25 + .75;
    bgCtx.beginPath();
    bgCtx.arc(s.x, s.y, s.r, 0, Math.PI*2);
    bgCtx.fillStyle = `rgba(200,220,255,${s.a * flicker})`;
    bgCtx.fill();
    s.y += s.speed;
    if (s.y > bgCanvas.height + 5) { s.y = -5; s.x = Math.random() * bgCanvas.width; }
  }
}

/* ════════════════════════════════════════════════════════════════════
   BRAIN ORB — 3D Neural Sphere (from JARVIS Brainiac)
════════════════════════════════════════════════════════════════════ */
// Build neuron network on sphere in anatomical brain shape
const ORB_NODES = [];
const ORB_EDGES = [];

function buildOrbGeometry() {
  ORB_NODES.length = 0; ORB_EDGES.length = 0;
  
  const totalNeurons = CFG.ORB_NEURONS;
  
  for (let i = 0; i < totalNeurons; i++) {
    const rand = Math.random();
    let x = 0, y = 0, z = 0, type = 'cortex';
    
    if (rand < 0.70) {
      // Cerebrum (two hemispheres)
      const isLeft = Math.random() < 0.5;
      const theta = Math.random() * Math.PI * 2;
      const phi = Math.random() * Math.PI;
      
      let sx = Math.sin(phi) * Math.cos(theta);
      let sy = Math.sin(phi) * Math.sin(theta);
      let sz = Math.cos(phi);
      
      x = sx * 0.85;
      y = sy * 0.70;
      z = sz * 1.05;
      
      if (isLeft) {
        x = -Math.abs(x) - 0.05;
      } else {
        x = Math.abs(x) + 0.05;
      }
      
      // Gyri ripples
      const ripple = 1.0 + Math.sin(theta * 8) * Math.cos(phi * 8) * 0.06;
      x *= ripple;
      y *= ripple;
      z *= ripple;
      
      type = 'cortex';
    } else if (rand < 0.90) {
      // Cerebellum (dense, lower back)
      const theta = Math.random() * Math.PI * 2;
      const r = Math.random() * 0.28 + 0.05;
      x = Math.cos(theta) * r * 0.7;
      y = 0.45 + (Math.random() - 0.5) * 0.2;
      z = -0.65 + (Math.random() - 0.5) * 0.2;
      type = 'cerebellum';
    } else {
      // Brainstem (vertical core at the bottom)
      x = (Math.random() - 0.5) * 0.12;
      y = 0.3 + Math.random() * 0.6;
      z = -0.1 + (Math.random() - 0.5) * 0.12;
      type = 'stem';
    }
    
    ORB_NODES.push([
      x, y, z,
      Math.random(), // firing intensity
      type,
      Math.random() < 0.5 ? 1 : -1
    ]);
  }
  
  // Build edges: connect nearby neurons within the same region or long-range project fibers
  for (let i = 0; i < ORB_NODES.length; i++) {
    const a = ORB_NODES[i];
    let maxConnections = a[4] === 'cerebellum' ? 5 : (a[4] === 'stem' ? 3 : 4);
    
    const candidates = [];
    for (let j = 0; j < ORB_NODES.length; j++) {
      if (i === j) continue;
      const b = ORB_NODES[j];
      
      const dx = a[0] - b[0];
      const dy = a[1] - b[1];
      const dz = a[2] - b[2];
      const dist = Math.hypot(dx, dy, dz);
      
      let weight = dist;
      if (a[4] !== b[4]) weight *= 2.0;
      if (a[4] === 'cortex' && b[4] === 'cortex' && (a[0] > 0 !== b[0] > 0)) {
        weight *= 3.0; // fissure penalty
      }
      
      candidates.push({ index: j, weight, dist });
    }
    
    candidates.sort((x, y) => x.weight - y.weight);
    
    for (let k = 0; k < maxConnections; k++) {
      const c = candidates[k];
      if (c.dist < 0.45) {
        if (!ORB_EDGES.some(e => (e[0] === i && e[1] === c.index) || (e[0] === c.index && e[1] === i))) {
          ORB_EDGES.push([i, c.index]);
        }
      }
    }
    
    // Corpus callosum bridge
    if (a[4] === 'cortex' && Math.random() < 0.05) {
      const oppIndex = ORB_NODES.findIndex((b, idx) => {
        return idx !== i && b[4] === 'cortex' && (a[0] > 0 !== b[0] > 0) &&
               Math.abs(a[1] - b[1]) < 0.15 && Math.abs(a[2] - b[2]) < 0.15;
      });
      if (oppIndex !== -1) {
        if (!ORB_EDGES.some(e => (e[0] === i && e[1] === oppIndex) || (e[0] === oppIndex && e[1] === i))) {
          ORB_EDGES.push([i, oppIndex]);
        }
      }
    }
  }
}
buildOrbGeometry();

function drawBrainOrb(ctx, W, H, phase, level, state, persona) {
  if (!ctx) return;
  ctx.clearRect(0, 0, W, H);
  const cx = W/2, cy = H/2, R = W*.42;

  // Scanning rings
  for (let i = 0; i < 3; i++) {
    const rad = R*1.2 + i*9 + Math.sin(phase*3 + i)*3;
    const col = i%2===0 ? '#00e5ff' : '#ffd23f';
    ctx.beginPath();
    ctx.arc(cx, cy, rad, 0, Math.PI*2);
    ctx.strokeStyle = col + Math.floor(Math.max(30, 180-i*50)).toString(16).padStart(2,'0');
    ctx.lineWidth = 1.2;
    ctx.stroke();
  }

  // 3D rotation (yaw + pitch + subtle roll wobble)
  const yaw = phase;
  const pitch = -0.42; 
  const roll = 0.12 * Math.sin(phase * 0.4);
  
  const cosY = Math.cos(yaw), sinY = Math.sin(yaw);
  const cosP = Math.cos(pitch), sinP = Math.sin(pitch);
  const cosR = Math.cos(roll), sinR = Math.sin(roll);

  const proj = ORB_NODES.map(([x, y, z, fire, type]) => {
    // 1. Yaw
    let x1 = x * cosY - z * sinY;
    let z1 = x * sinY + z * cosY;
    let y1 = y;
    
    // 2. Pitch
    let y2 = y1 * cosP - z1 * sinP;
    let z2 = y1 * sinP + z1 * cosP;
    let x2 = x1;
    
    // 3. Roll
    let x3 = x2 * cosR - y2 * sinR;
    let y3 = x2 * sinR + y2 * cosR;
    let z3 = z2;
    
    const depth = (z3 + 1.3) / 2.6;
    const scale = 1.0 + z3 * 0.28;
    return [cx + x3*R*scale, cy + y3*R*scale, depth, fire, type];
  });

  // Update neuron firing based on Persona
  for (const n of ORB_NODES) {
    n[3] = Math.max(0, n[3] - .035);
    let fireProb = 0.045; // Default idle probability
    
    if (persona) {
      const p = persona.toLowerCase();
      if (p.includes('claude') && n[4] === 'cortex') fireProb = 0.4;
      else if (p.includes('google') && n[4] === 'cerebellum') fireProb = 0.5;
      else if (p.includes('manus') && n[4] === 'stem') fireProb = 0.6;
      else if (p.includes('gpt') && n[4] === 'cortex' && Math.abs(n[0]) < 0.2) fireProb = 0.5; // Fissure/core
      else if (p.includes('spline')) fireProb = 0.35; // All brain
    } else if (state === 'EXECUTING') {
      fireProb = 0.15; // General high activity
    }
    
    if (Math.random() < fireProb) n[3] = 1;
  }

  // Draw edges
  for (const [ei, ej] of ORB_EDGES) {
    const [ax, ay, ad, af, atype] = proj[ei];
    const [bx, by, bd, bf, btype] = proj[ej];
    const avgFire = Math.max(af, bf);
    const avgDepth = (ad + bd)/2;
    
    ctx.beginPath(); ctx.moveTo(ax, ay); ctx.lineTo(bx, by);
    
    let edgeColor = 'rgba(0, 229, 255, ';
    if (atype === 'cerebellum' && btype === 'cerebellum') {
      edgeColor = 'rgba(255, 210, 63, ';
    } else if (atype === 'stem' && btype === 'stem') {
      edgeColor = 'rgba(244, 114, 182, ';
    } else if (atype !== btype) {
      edgeColor = 'rgba(168, 85, 247, ';
    }
    
    const alpha = (0.04 + 0.12*avgDepth + 0.18*avgFire) * (atype === 'stem' ? 0.55 : 1.0);
    ctx.strokeStyle = edgeColor + alpha + ')';
    ctx.lineWidth = (0.4 + avgFire*1.4) * (avgDepth*0.8 + 0.2);
    ctx.stroke();
  }

  // Sort by depth
  const order = proj.map((_,i) => i).sort((a,b) => proj[a][2] - proj[b][2]);

  // Draw neurons
  for (const i of order) {
    const [px, py, depth, fire, type] = proj[i];
    const size = (type === 'cerebellum' ? 2.0 : (type === 'stem' ? 2.4 : 3.0)) * (depth*1.3 + 0.35) + fire*4.0;
    
    let color = '#00e5ff';
    if (type === 'cerebellum') {
      color = fire > 0.4 ? '#ffffff' : '#ffd23f';
    } else if (type === 'stem') {
      color = fire > 0.4 ? '#ffffff' : '#f472b6';
    } else {
      color = fire > 0.45 ? '#ffffff' : (fire > 0.15 ? '#a855f7' : '#00e5ff');
    }
    
    if (fire > 0.25) {
      ctx.beginPath(); ctx.arc(px, py, size*2.0, 0, Math.PI*2);
      ctx.fillStyle = hexA(color, 0.12*fire);
      ctx.fill();
    }
    
    ctx.beginPath(); ctx.arc(px, py, size/2, 0, Math.PI*2);
    ctx.fillStyle = hexA(color, 0.25 + 0.75*depth);
    ctx.fill();
  }

  // Audio reactive ring or state ring
  if (state !== 'IDLE') {
    const lrad = R*.7 + level*28;
    ctx.beginPath(); ctx.arc(cx, cy, lrad, 0, Math.PI*2);
    let stateColor = '#00e5ffcc';
    if (state === 'LISTENING') stateColor = '#ff6b00cc';
    else if (state === 'EXECUTING') stateColor = '#ffd23fcc';
    else if (state === 'ROUTING') stateColor = '#a855f7cc';
    ctx.strokeStyle = stateColor;
    ctx.lineWidth = 2.5; ctx.stroke();
  }

  // Inner core — arc reactor style with wave pulses
  const waveVal = Math.sin(phase * 4) * 0.12 + 0.88;
  const coreR = R * 0.24 * waveVal;
  const grad = ctx.createRadialGradient(cx, cy, 0, cx, cy, coreR);
  grad.addColorStop(0, 'rgba(0,240,255,0.95)');
  grad.addColorStop(0.35, 'rgba(168,85,247,0.55)');
  grad.addColorStop(0.75, 'rgba(0,120,200,0.22)');
  grad.addColorStop(1, 'rgba(0,40,80,0)');
  ctx.beginPath(); ctx.arc(cx, cy, coreR, 0, Math.PI*2);
  ctx.fillStyle = grad; ctx.fill();

  // Conical sweep (purple gradient sweep)
  ctx.save();
  ctx.translate(cx, cy); ctx.rotate(-phase*3);
  const sweep = ctx.createLinearGradient(-R*.7, 0, R*.7, 0);
  sweep.addColorStop(0, 'rgba(0,229,255,0)');
  sweep.addColorStop(.5, 'rgba(168,85,247,0.08)');
  sweep.addColorStop(1, 'rgba(0,229,255,0)');
  ctx.beginPath(); ctx.arc(0, 0, R*.7, 0, Math.PI*2);
  ctx.fillStyle = sweep; ctx.fill();
  ctx.restore();

  // Tick marks
  ctx.strokeStyle = 'rgba(0,229,255,0.4)'; ctx.lineWidth = 1.5;
  for (let i = 0; i < 24; i++) {
    const ang = i*15*Math.PI/180;
    const r1 = R*.75, r2 = R*.82;
    ctx.beginPath();
    ctx.moveTo(cx + r1*Math.cos(ang), cy + r1*Math.sin(ang));
    ctx.lineTo(cx + r2*Math.cos(ang), cy + r2*Math.sin(ang));
    ctx.stroke();
  }

  // Labels
  ctx.fillStyle = '#00e5ff';
  ctx.font = `bold ${Math.floor(W*.055)}px JetBrains Mono, monospace`;
  ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
  ctx.fillText('J.A.R.V.I.S', cx, cy + W*.01);
  ctx.fillStyle = '#ffd23f';
  ctx.font = `${Math.floor(W*.032)}px JetBrains Mono, monospace`;
  ctx.fillText('NEURAL CORE', cx, cy + W*.085);
  if (state !== 'IDLE') {
    let stateLabel = '● LISTENING';
    let labelColor = '#ff6b00';
    if (state === 'EXECUTING') { stateLabel = '⚡ EXECUTING'; labelColor = '#ffd23f'; }
    else if (state === 'ROUTING') { stateLabel = '🔮 ROUTING'; labelColor = '#a855f7'; }
    
    if (persona) stateLabel += ` [${persona.toUpperCase()}]`;
    
    ctx.fillStyle = labelColor;
    ctx.font = `bold ${Math.floor(W*.026)}px JetBrains Mono, monospace`;
    ctx.fillText(stateLabel, cx, cy + W*.14);
  }
}

function drawMiniOrb(ctx, W, H, phase) {
  if (!ctx) return;
  ctx.clearRect(0, 0, W, H);
  const cx = W/2, cy = H/2, R = W*.38;

  // Glow
  const g = ctx.createRadialGradient(cx, cy, 0, cx, cy, R*1.5);
  g.addColorStop(0, 'rgba(0,229,255,0.18)');
  g.addColorStop(1, 'transparent');
  ctx.fillStyle = g; ctx.fillRect(0, 0, W, H);

  // Rings
  for (let i = 0; i < 2; i++) {
    ctx.beginPath();
    ctx.arc(cx, cy, R + i*4 + Math.sin(phase*3+i)*2, 0, Math.PI*2);
    ctx.strokeStyle = i===0 ? 'rgba(0,229,255,0.5)' : 'rgba(255,210,63,0.3)';
    ctx.lineWidth = 1; ctx.stroke();
  }

  // Core
  const core = ctx.createRadialGradient(cx-R*.12, cy-R*.12, 0, cx, cy, R*.6);
  core.addColorStop(0, 'rgba(0,240,255,0.95)');
  core.addColorStop(.7, 'rgba(0,120,200,0.5)');
  core.addColorStop(1, 'rgba(0,40,80,0)');
  ctx.beginPath(); ctx.arc(cx, cy, R*.6, 0, Math.PI*2);
  ctx.fillStyle = core; ctx.fill();

  ctx.fillStyle = '#00e5ff';
  ctx.font = `bold ${Math.floor(W*.14)}px JetBrains Mono`;
  ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
  ctx.fillText('J', cx, cy);
}

/* ════════════════════════════════════════════════════════════════════
   NEURALINK 4-CHANNEL BCI PANEL
════════════════════════════════════════════════════════════════════ */
function initNeuralinkLoop() {
  setInterval(tickNeuralink, 40);
}

function tickNeuralink() {
  nlPhase += 0.08;
  for (let i = 0; i < 4; i++) {
    let v = Math.sin(nlPhase*NL_FREQS[i])*.4 + Math.sin(nlPhase*NL_FREQS[i]*.7)*.3;
    v += (Math.random() - .5)*.28;
    NL_BUFS[i].push(v);
    if (NL_BUFS[i].length > 200) NL_BUFS[i].shift();
  }
  drawNeuralink();
}

function drawNeuralink() {
  const ctx = neuralinkCtx; if (!ctx) return;
  const W = neuralinkCanvas.width, H = neuralinkCanvas.height;
  ctx.clearRect(0, 0, W, H);
  ctx.fillStyle = 'rgba(2,4,8,0.75)'; ctx.fillRect(0, 0, W, H);
  ctx.strokeStyle = 'rgba(0,229,255,0.08)'; ctx.lineWidth = 1;
  ctx.strokeRect(0, 0, W, H);

  ctx.fillStyle = '#ffd23f';
  ctx.font = 'bold 8px JetBrains Mono';
  ctx.textAlign = 'left'; ctx.textBaseline = 'top';
  ctx.fillText('NEURALINK BCI · 4-CH · 1024Hz · BRIDGE: ACTIVE', 8, 5);

  const chH = (H - 16) / 4;
  const drawW = W - 48;

  for (let ch = 0; ch < 4; ch++) {
    const cy = 16 + chH*(ch+.5);
    const col = NL_COLORS[ch];

    ctx.fillStyle = col;
    ctx.font = 'bold 9px JetBrains Mono';
    ctx.textAlign = 'left'; ctx.textBaseline = 'middle';
    ctx.fillText(NL_LABELS[ch], 6, cy);

    ctx.beginPath(); ctx.moveTo(36, cy); ctx.lineTo(W-8, cy);
    ctx.strokeStyle = 'rgba(0,229,255,0.06)'; ctx.lineWidth = .5; ctx.stroke();

    ctx.beginPath();
    const buf = NL_BUFS[ch];
    for (let i = 0; i < buf.length; i++) {
      const x = 36 + (i / (buf.length-1)) * drawW;
      const y = cy - buf[i] * (chH/2 - 3);
      i===0 ? ctx.moveTo(x,y) : ctx.lineTo(x,y);
    }
    ctx.strokeStyle = col; ctx.lineWidth = 1.1; ctx.stroke();
  }
}

/* ════════════════════════════════════════════════════════════════════
   NEURAL NETWORK — Force-Directed Graph (4K enhanced)
════════════════════════════════════════════════════════════════════ */
function addRepoNode(repo) {
  const cat = categorize(repo);
  const power = calcPower(repo);
  const r = lerp(CFG.NODE_MIN_R, CFG.NODE_MAX_R, Math.min(power/100, 1));
  const cx = neuralCanvas.offsetWidth/2, cy = neuralCanvas.offsetHeight/2;
  const node = {
    id: repo.id, repo, cat,
    x: cx + (Math.random()-.5)*350,
    y: cy + (Math.random()-.5)*350,
    vx:0, vy:0, r, color: CATS[cat].color, power,
    glow:0, targetGlow:0, pulse: Math.random()*Math.PI*2,
  };
  S.nodes.push(node);
  buildEdges(node);
  return node;
}

function buildEdges(newNode) {
  for (const existing of S.nodes) {
    if (existing.id === newNode.id) continue;
    const score = synergyScore(newNode, existing);
    if (score > .15) {
      const edge = { source:newNode, target:existing, strength:score, particles:[] };
      const count = Math.ceil(CFG.PARTICLES_PER_EDGE * score);
      for (let i=0; i<count; i++) {
        edge.particles.push({
          t: Math.random(),
          speed: (.002 + Math.random()*.003) * CFG.PARTICLE_SPEED,
          alpha: .35 + Math.random()*.45,
          r: 1 + Math.random()*2,
          rev: Math.random() < .3,
        });
      }
      S.edges.push(edge);
    }
  }
}

function updatePhysics() {
  if (!S.physicsOn) return;
  const nodes = S.nodes;
  const cx = neuralCanvas.offsetWidth/2 - S.camera.x;
  const cy = neuralCanvas.offsetHeight/2 - S.camera.y;

  // Repulsion
  for (let i=0; i<nodes.length; i++) {
    for (let j=i+1; j<nodes.length; j++) {
      const a=nodes[i], b=nodes[j];
      let dx=a.x-b.x, dy=a.y-b.y;
      let dist = Math.hypot(dx,dy) || 1;
      const force = CFG.REPULSION/(dist*dist);
      const fx=dx/dist*force, fy=dy/dist*force;
      a.vx+=fx; a.vy+=fy; b.vx-=fx; b.vy-=fy;
    }
  }

  // Springs
  for (const e of S.edges) {
    const a=e.source, b=e.target;
    const dx=b.x-a.x, dy=b.y-a.y;
    const dist = Math.hypot(dx,dy) || 1;
    const disp = dist - CFG.SPRING_REST;
    const force = CFG.SPRING_K * disp * e.strength;
    const fx=dx/dist*force, fy=dy/dist*force;
    a.vx+=fx; a.vy+=fy; b.vx-=fx; b.vy-=fy;
  }

  // Center gravity + damping
  for (const n of nodes) {
    if (S.drag.node === n) continue;
    n.vx += (cx-n.x)*CFG.CENTER_G;
    n.vy += (cy-n.y)*CFG.CENTER_G;
    n.vx *= CFG.DAMPING; n.vy *= CFG.DAMPING;
    const spd = Math.hypot(n.vx, n.vy);
    if (spd > CFG.MAX_VEL) { n.vx=n.vx/spd*CFG.MAX_VEL; n.vy=n.vy/spd*CFG.MAX_VEL; }
    n.x += n.vx; n.y += n.vy;
    n.glow += (n.targetGlow - n.glow)*.1;
    n.pulse += .025;
  }
}

function drawNeural(t) {
  if (!neuralCtx) return;
  const dpr = window.devicePixelRatio || 1;
  const W = neuralCanvas.offsetWidth, H = neuralCanvas.offsetHeight;

  neuralCtx.clearRect(0, 0, W*dpr, H*dpr);

  neuralCtx.save();
  neuralCtx.scale(dpr, dpr);
  neuralCtx.translate(W/2, H/2);
  neuralCtx.scale(S.camera.zoom, S.camera.zoom);
  neuralCtx.translate(-W/2+S.camera.x, -H/2+S.camera.y);

  // Edges + particles
  for (const e of S.edges) {
    const {source:a, target:b, strength} = e;
    const alpha = .06 + strength*.18;

    // Edge line
    neuralCtx.beginPath();
    neuralCtx.moveTo(a.x, a.y); neuralCtx.lineTo(b.x, b.y);
    neuralCtx.strokeStyle = `rgba(0,229,255,${alpha})`;
    neuralCtx.lineWidth = .5 + strength*2;
    neuralCtx.stroke();

    // Particles
    for (const p of e.particles) {
      p.t += p.rev ? -p.speed : p.speed;
      if (p.t > 1) p.t -= 1; if (p.t < 0) p.t += 1;
      const px = a.x + (b.x-a.x)*p.t;
      const py = a.y + (b.y-a.y)*p.t;
      const pc = lerpHex(a.color, b.color, p.t);
      neuralCtx.beginPath(); neuralCtx.arc(px, py, p.r, 0, Math.PI*2);
      neuralCtx.fillStyle = pc.replace('rgb','rgba').replace(')',`,${p.alpha})`);
      neuralCtx.fill();
    }
  }

  // Nodes
  for (const n of S.nodes) {
    const isHov = n===S.hoveredNode, isSel = n===S.selectedNode;
    const glowAmt = isHov ? 1 : (isSel ? .8 : n.glow);
    const pulse = Math.sin(n.pulse)*.08 + .92;
    const nodeR = n.r * (isHov ? 1.18 : 1) * pulse;

    // Outer glow
    if (glowAmt > .05) {
      const grd = neuralCtx.createRadialGradient(n.x,n.y,nodeR,n.x,n.y,nodeR*3.5);
      grd.addColorStop(0, hexA(n.color, .35*glowAmt));
      grd.addColorStop(1, 'transparent');
      neuralCtx.beginPath(); neuralCtx.arc(n.x, n.y, nodeR*3.5, 0, Math.PI*2);
      neuralCtx.fillStyle = grd; neuralCtx.fill();
    }

    // Node body (sphere-like gradient)
    const bodyGrd = neuralCtx.createRadialGradient(
      n.x-nodeR*.3, n.y-nodeR*.3, 0, n.x, n.y, nodeR
    );
    bodyGrd.addColorStop(0, hexA(n.color,.95));
    bodyGrd.addColorStop(.65, hexA(n.color,.65));
    bodyGrd.addColorStop(1, hexA(n.color,.25));
    neuralCtx.beginPath(); neuralCtx.arc(n.x, n.y, nodeR, 0, Math.PI*2);
    neuralCtx.fillStyle = bodyGrd; neuralCtx.fill();

    // Selection ring
    if (isSel) {
      neuralCtx.beginPath(); neuralCtx.arc(n.x, n.y, nodeR+3.5, 0, Math.PI*2);
      neuralCtx.strokeStyle = n.color; neuralCtx.lineWidth = 2.5; neuralCtx.stroke();

      // Outer pulse ring
      const pulseR = nodeR + 6 + Math.sin(t*.003)*4;
      neuralCtx.beginPath(); neuralCtx.arc(n.x, n.y, pulseR, 0, Math.PI*2);
      neuralCtx.strokeStyle = hexA(n.color,.3); neuralCtx.lineWidth = 1; neuralCtx.stroke();
    }

    // Specular highlight
    const specGrd = neuralCtx.createRadialGradient(
      n.x-nodeR*.4, n.y-nodeR*.5, 0, n.x-nodeR*.3, n.y-nodeR*.3, nodeR*.5
    );
    specGrd.addColorStop(0, 'rgba(255,255,255,0.35)');
    specGrd.addColorStop(1, 'transparent');
    neuralCtx.beginPath(); neuralCtx.arc(n.x, n.y, nodeR, 0, Math.PI*2);
    neuralCtx.fillStyle = specGrd; neuralCtx.fill();

    // Label
    if (S.showLabels && (n.r > 11 || isHov)) {
      neuralCtx.fillStyle = isHov ? '#fff' : 'rgba(232,244,255,0.72)';
      neuralCtx.font = `${isHov?'600':'400'} ${isHov?11:9}px Outfit`;
      neuralCtx.textAlign = 'center'; neuralCtx.textBaseline = 'top';
      neuralCtx.fillText(n.repo.name, n.x, n.y+nodeR+5);
    }
  }

  // Update neural stats
  if ($('#ns-nodes')) $('#ns-nodes').textContent = `${S.nodes.length} nodes`;
  if ($('#ns-edges')) $('#ns-edges').textContent = `${S.edges.length} edges`;

  neuralCtx.restore();
}

/* ════════════════════════════════════════════════════════════════════
   GITHUB SCANNER
════════════════════════════════════════════════════════════════════ */
async function scanGitHub(query, lang, minStars) {
  if (S.scanning) return;
  S.scanning = true;
  updateScanUI(true);

  let q = query || 'stars:>1000';
  if (lang) q += ` language:${lang}`;
  if (minStars) q += ` stars:>=${minStars}`;

  const url = `${CFG.GITHUB_API}/search/repositories?q=${encodeURIComponent(q)}&sort=stars&order=desc&per_page=30`;

  try {
    const resp = await fetch(url, { headers: { Accept: 'application/vnd.github.v3+json' } });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}: ${resp.statusText}`);
    const data = await resp.json();
    const items = data.items || [];

    renderScanResults(items);
    botMsg(`🔍 סרקתי ומצאתי **${items.length} ריפוז**! מטמיע אותם במוח...`);

    let delay = 0;
    for (const repo of items) {
      if (S.repos.find(r => r.id === repo.id)) continue;
      await new Promise(res => setTimeout(res, delay));
      S.repos.push(repo);
      addRepoNode(repo);
      updateHeaderStats();
      computeSynergies();
      delay = 120;
    }

    botMsg(`✅ **${items.length} ריפוז** נוספו לרשת! כעת יש **${S.nodes.length}** צמתים ו-**${S.edges.length}** חיבורים.`);
  } catch (err) {
    botMsg(`⚠️ שגיאה: ${err.message}. GitHub rate limit? נסה שוב בעוד דקה.`);
  }

  S.scanning = false;
  updateScanUI(false);
}

/* ════════════════════════════════════════════════════════════════════
   ABSORB OWNER REPOS (amjad2161)
════════════════════════════════════════════════════════════════════ */
function absorbOwnerRepos() {
  let count = 0;
  for (const repo of OWNER_REPOS) {
    if (S.repos.find(r => r.id === repo.id)) continue;
    S.repos.push(repo);
    const node = addRepoNode(repo);
    // Mark owner repos with gold glow
    if (repo.is_owner) { node.color = '#ffd23f'; node.targetGlow = 0.5; node.r = Math.max(node.r, 18); }
    count++;
  }
  if (count > 0) {
    updateHeaderStats();
    computeSynergies();
    renderScanResults(OWNER_REPOS);
    if ($('#sr-count')) $('#sr-count').textContent = OWNER_REPOS.length;
    sysMsg(`[★ OWNER] ${count} ריפוזים שלך (amjad2161) נטמעו למוח`);
  }
}

async function absorbByURL(url) {
  // Extract owner/repo from GitHub URL
  const match = url.match(/github\.com\/([^/]+)\/([^/\.]+)/);
  if (!match) { botMsg(`❌ URL לא תקין: ${url}`); return; }
  const [, owner, repoName] = match;
  botMsg(`📡 סורק GitHub API: **${owner}/${repoName}**...`);
  try {
    const resp = await fetch(`${CFG.GITHUB_API}/repos/${owner}/${repoName}`, { headers: { Accept: 'application/vnd.github.v3+json' } });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const repo = await resp.json();
    // Fetch topics separately
    const tResp = await fetch(`${CFG.GITHUB_API}/repos/${owner}/${repoName}/topics`, { headers: { Accept: 'application/vnd.github.mercy-preview+json' } });
    if (tResp.ok) { const td = await tResp.json(); repo.topics = td.names || []; }
    if (!S.repos.find(r => r.id === repo.id)) {
      S.repos.push(repo); addRepoNode(repo); updateHeaderStats(); computeSynergies();
    }
    botMsg(`✅ טמעתי **${repo.full_name}**\n★ ${fmtN(repo.stargazers_count)} כוכבים · ⚡ Power: ${calcPower(repo)}`);
  } catch(e) { botMsg(`⚠️ שגיאה בסריקת ${owner}/${repoName}: ${e.message}`); }
}

function renderScanResults(items) {
  const list = $('#sr-list');
  const cnt = $('#sr-count');
  if (cnt) cnt.textContent = items.length;
  if (!list) return;

  if (!items.length) {
    list.innerHTML = '<div class="empty-st"><span>😕</span><p>No results found</p></div>';
    return;
  }
  list.innerHTML = '';
  items.forEach((repo, i) => {
    const lc = LANG_COLORS[repo.language] || '#888';
    const card = document.createElement('div');
    card.className = 'repo-card';
    card.style.animationDelay = `${i*.04}s`;
    card.innerHTML = `
      <div class="rc-name">${repo.full_name}</div>
      <div class="rc-desc">${repo.description || 'No description'}</div>
      <div class="rc-meta">
        ${repo.language ? `<span class="rc-lang" style="background:${lc}22;color:${lc}">${repo.language}</span>` : ''}
        <span style="color:rgba(232,244,255,.4)">⭐ ${fmtN(repo.stargazers_count)}</span>
        <span style="color:rgba(232,244,255,.3)">🍴 ${fmtN(repo.forks_count)}</span>
      </div>`;
    card.addEventListener('click', () => selectRepo(repo));
    list.appendChild(card);
  });
}

async function scanTrending() {
  const topics = ['machine-learning','react','python','rust','ai','devops','llm','robotics'];
  const topic = topics[Math.floor(Math.random()*topics.length)];
  botMsg(`🔥 סורק טרנדים: **${topic}**...`);
  await scanGitHub(`topic:${topic}`, '', '5000');
}

/* ════════════════════════════════════════════════════════════════════
   ESSENCE EXTRACTOR
════════════════════════════════════════════════════════════════════ */
function categorize(repo) {
  const text = [repo.name, repo.description||'', ...(repo.topics||[]), repo.language||''].join(' ').toLowerCase();
  let bestCat = 'other', bestScore = 0;
  for (const [cat, info] of Object.entries(CATS)) {
    if (cat==='other') continue;
    const score = info.kw.reduce((s,kw) => s + (text.includes(kw)?1:0), 0);
    if (score > bestScore) { bestScore = score; bestCat = cat; }
  }
  return bestCat;
}

function calcPower(repo) {
  const s = repo.stargazers_count||0, f = repo.forks_count||0, w = repo.watchers_count||0;
  const starS = Math.min(Math.log10(s+1)/5,1)*40;
  const forkS = Math.min(Math.log10(f+1)/4,1)*25;
  const commS = Math.min(Math.log10(w+(repo.open_issues_count||0)+1)/4,1)*20;
  const freshS = repo.pushed_at ? Math.max(0,1-(Date.now()-new Date(repo.pushed_at).getTime())/(365*24*3600*1000))*15 : 0;
  return Math.round(starS+forkS+commS+freshS);
}

function showEssence(node) {
  const repo = node.repo, catInfo = CATS[node.cat];
  const view = $('#essence-view');
  if (!view) return;
  view.innerHTML = `
    <div>
      <span class="ess-cat" style="background:${hexA(catInfo.color,.15)};color:${catInfo.color}">${catInfo.icon} ${catInfo.label}</span>
      <div class="ess-name">${repo.full_name}</div>
      <div class="ess-owner">by ${repo.owner?.login||'?'}</div>
      <div class="ess-desc">${repo.description||'No description'}</div>
      <div class="ess-metrics">
        <div class="ess-m"><div class="ess-mv" style="color:${catInfo.color}">⭐ ${fmtN(repo.stargazers_count)}</div><div class="ess-ml">Stars</div></div>
        <div class="ess-m"><div class="ess-mv" style="color:${catInfo.color}">🍴 ${fmtN(repo.forks_count)}</div><div class="ess-ml">Forks</div></div>
        <div class="ess-m"><div class="ess-mv" style="color:${catInfo.color}">👁️ ${fmtN(repo.watchers_count)}</div><div class="ess-ml">Watchers</div></div>
        <div class="ess-m"><div class="ess-mv" style="color:${catInfo.color}">⚡ ${node.power}</div><div class="ess-ml">Power</div></div>
      </div>
      <canvas class="radar-canvas" id="ess-radar"></canvas>
      ${repo.topics?.length ? `<div class="ess-topics">${repo.topics.map(t=>`<span class="topic-tag">${t}</span>`).join('')}</div>` : ''}
      <a class="ess-link" href="${repo.html_url}" target="_blank" rel="noopener">🔗 Open on GitHub</a>
    </div>`;
  setTimeout(() => drawRadar(node), 30);
}

function drawRadar(node) {
  const canvas = document.getElementById('ess-radar'); if (!canvas) return;
  const ctx = canvas.getContext('2d');
  const W = canvas.parentElement?.offsetWidth || 200;
  canvas.width = W; canvas.height = 150;
  const cx = W/2, cy = 78, maxR = 55;
  const labels = ['Stars','Forks','Community','Freshness','Topics'];
  const repo = node.repo;
  const vals = [
    Math.min(Math.log10((repo.stargazers_count||0)+1)/5,1),
    Math.min(Math.log10((repo.forks_count||0)+1)/4,1),
    Math.min(Math.log10((repo.watchers_count||0)+(repo.open_issues_count||0)+1)/4,1),
    repo.pushed_at ? Math.max(0,1-(Date.now()-new Date(repo.pushed_at).getTime())/(365*24*3600*1000)) : 0,
    Math.min((repo.topics||[]).length/10,1),
  ];
  const n = 5, step = (Math.PI*2)/n;

  // Grid
  for (let ring=.25; ring<=1; ring+=.25) {
    ctx.beginPath();
    for (let i=0; i<=n; i++) { const a=i*step-Math.PI/2; const pt=[cx+Math.cos(a)*maxR*ring, cy+Math.sin(a)*maxR*ring]; i===0?ctx.moveTo(...pt):ctx.lineTo(...pt); }
    ctx.strokeStyle='rgba(255,255,255,0.07)'; ctx.lineWidth=1; ctx.stroke();
  }
  for (let i=0; i<n; i++) {
    ctx.beginPath(); ctx.moveTo(cx,cy);
    const a=i*step-Math.PI/2; ctx.lineTo(cx+Math.cos(a)*maxR,cy+Math.sin(a)*maxR);
    ctx.strokeStyle='rgba(255,255,255,0.07)'; ctx.stroke();
  }

  // Value polygon
  ctx.beginPath();
  for (let i=0; i<=n; i++) {
    const a=(i%n)*step-Math.PI/2;
    const [x,y]=[cx+Math.cos(a)*maxR*vals[i%n],cy+Math.sin(a)*maxR*vals[i%n]];
    i===0?ctx.moveTo(x,y):ctx.lineTo(x,y);
  }
  ctx.fillStyle=hexA(node.color,.18); ctx.fill();
  ctx.strokeStyle=hexA(node.color,.85); ctx.lineWidth=2; ctx.stroke();

  // Dots + labels
  for (let i=0; i<n; i++) {
    const a=i*step-Math.PI/2;
    ctx.beginPath(); ctx.arc(cx+Math.cos(a)*maxR*vals[i],cy+Math.sin(a)*maxR*vals[i],3,0,Math.PI*2);
    ctx.fillStyle=node.color; ctx.fill();
    ctx.fillStyle='rgba(232,244,255,0.5)'; ctx.font='8px Outfit';
    ctx.textAlign='center'; ctx.textBaseline='middle';
    ctx.fillText(labels[i],cx+Math.cos(a)*(maxR+14),cy+Math.sin(a)*(maxR+14));
  }
}

/* ════════════════════════════════════════════════════════════════════
   SYNERGY ENGINE
════════════════════════════════════════════════════════════════════ */
function synergyScore(a, b) {
  let score = 0;
  if (a.repo.language && a.repo.language === b.repo.language) score += .25;
  const tA = new Set((a.repo.topics||[]).map(t=>t.toLowerCase()));
  const tB = new Set((b.repo.topics||[]).map(t=>t.toLowerCase()));
  let shared = 0; for (const t of tA) if (tB.has(t)) shared++;
  score += Math.min(shared*.15, .45);
  const comp = [['frontend','backend'],['ai','data'],['devops','backend'],['mobile','backend'],['systems','devops'],['ai','systems']];
  for (const [c1,c2] of comp) {
    if ((a.cat===c1&&b.cat===c2)||(a.cat===c2&&b.cat===c1)) { score+=.3; break; }
  }
  if (a.cat===b.cat && a.cat!=='other') score+=.1;
  return Math.min(score,1);
}

function computeSynergies() {
  const syns = [];
  for (let i=0; i<S.nodes.length; i++) {
    for (let j=i+1; j<S.nodes.length; j++) {
      const sc = synergyScore(S.nodes[i], S.nodes[j]);
      if (sc>.28) {
        const reasons = getSynReasons(S.nodes[i], S.nodes[j]);
        syns.push({ a:S.nodes[i], b:S.nodes[j], score:sc, reasons });
      }
    }
  }
  syns.sort((a,b)=>b.score-a.score);
  S.synergies = syns.slice(0,25);
  renderSynergies();
  if ($('#hv-syn')) animCounter('hv-syn', S.synergies.length);
}

function getSynReasons(a, b) {
  const r = [];
  if (a.repo.language && a.repo.language===b.repo.language) r.push(`${a.repo.language} ecosystem`);
  const tA=new Set((a.repo.topics||[]).map(t=>t.toLowerCase()));
  const shared=[...(b.repo.topics||[]).map(t=>t.toLowerCase())].filter(t=>tA.has(t));
  if (shared.length) r.push(`Shared: ${shared.slice(0,3).join(', ')}`);
  const comp={'frontend+backend':'Full-stack synergy','ai+data':'AI/Data pipeline','devops+backend':'Cloud-native stack','mobile+backend':'Mobile ecosystem','systems+devops':'Low-level ops'};
  r.push(comp[`${a.cat}+${b.cat}`]||comp[`${b.cat}+${a.cat}`]||`${CATS[a.cat].label} × ${CATS[b.cat].label}`);
  return r;
}

function renderSynergies() {
  const list = $('#synergy-list'); if (!list) return;
  if (!S.synergies.length) {
    list.innerHTML='<div class="empty-st"><span>🌀</span><p>Scan more repos to reveal synergies</p></div>';
    return;
  }
  list.innerHTML = S.synergies.map((s,i) => `
    <div class="syn-card" style="animation-delay:${i*.04}s">
      <div class="syn-pair">
        <span style="color:${s.a.color}">${s.a.repo.name}</span>
        <span class="syn-plus">⚡</span>
        <span style="color:${s.b.color}">${s.b.repo.name}</span>
      </div>
      <div class="syn-bar-wrap">
        <div class="syn-bar"><div class="syn-fill" style="width:${s.score*100}%"></div></div>
        <span class="syn-pct">${Math.round(s.score*100)}%</span>
      </div>
      <div class="syn-reason">${s.reasons.join(' · ')}</div>
    </div>`).join('');
}

/* ════════════════════════════════════════════════════════════════════
   JARVIS CHAT — Full Command Interface
════════════════════════════════════════════════════════════════════ */
function firstGreet() {
  sysMsg(`[BOOT] JARVIS SINGULARITY ONE · ${CFG.VERSION}`);
  sysMsg(`[BOOT] BRAINIAC ENGINE ONLINE · AGENCY 144+ AGENTS · GOD MODE ACTIVE`);
  sysMsg(`[BOOT] OLLAMA: ${S.ollama.available ? 'CONNECTED · '+S.ollama.model : 'OFFLINE (install from ollama.ai)'}`);
  botMsg(`שלום **${CFG.USER}**! אני **J.A.R.V.I.S** — Singularity One.\n\nכל המערכות אונליין. אני מוכן לכל משימה.\n\n💡 **פקודות**: *"סרוק ml"* · *"מה הכי חזק?"* · *"סינרגיות"* · *"סיכום"* · *"remember key=val"* · *"!Get-Process"*\n🎤 לחץ **MIC** לדיבור ישיר`);
}

function handleChat(input) {
  const text = input.trim(); if (!text) return;
  userMsg(text);

  // Visual routing (moved to fallback)

  // Memory commands
  if (text.startsWith('remember ') && text.includes('=')) {
    const [k,v] = text.slice(9).split('=').map(s=>s.trim());
    setMemory(k,v); botMsg(`🧠 נשלח ל-Unified Vector Memory: **${k}** = ${v}`); return;
  }
  if (text.startsWith('recall ')) {
    const k=text.slice(7).trim();
    botMsg(`שולף זיכרון עבור *${k}* מהליבה...`);
    fetch(`${CFG.API_BASE}/api/memory/recall`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query: k, limit: 1 })
    }).then(r => r.json()).then(data => {
      if (data && data.length > 0) {
         botMsg(`**${k}**: ${data[0].content}`);
      } else {
         botMsg(`לא נמצא זיכרון תחת המפתח *${k}* ב-Vector Memory.`);
      }
    }).catch(e => botMsg('שגיאה בשליפת זיכרון: ' + e.message));
    return;
  }

  // Shell commands
  if (text.startsWith('!')) {
    const cmd = text.slice(1).trim();
    sysMsg(`[SHELL] $ ${cmd}`);
    callLocalAgentServer(text);
    return;
  }

  // Absorb / clone GitHub URL
  if ((text.startsWith('github ') || text.startsWith('absorb ') || text.startsWith('טמע ')) && text.includes('github.com')) {
    const url = text.split(/\s+/).find(w=>w.includes('github.com'));
    if (url) { absorbByURL(url); return; }
  }
  // Direct github.com URL
  if (text.startsWith('https://github.com') || text.startsWith('http://github.com')) {
    absorbByURL(text.trim()); return;
  }

  const lower = text.toLowerCase();

  // My repos
  if (lower.includes('שלי') && (lower.includes('ריפו') || lower.includes('פרויק')) ||
      lower.includes('my repo') || lower.includes('my project') || lower.includes('amjad')) {
    const owned = S.nodes.filter(n=>n.repo.is_owner);
    const str = owned.map(n=>`• ⭐ **${n.repo.full_name}** — עוצמה: **${n.power}** | ${fmtN(n.repo.stargazers_count)} כוכבים`).join('\n');
    botMsg(`⭐ **הריפוזים שלך (amjad2161):**\n\n${str || 'אין עדיין — בטעינה...'}\n\n📡 כל הריפוזים מסומנים בזהב ברשת.`);
    return;
  }

  // Divisions breakdown
  if (lower.includes('division') || lower.includes('דיוויזיונ') || lower.includes('מחלקות') || lower.includes('breakdown')) {
    const divStr = AGENCY_KNOWLEDGE.divisions
      .map(d=>`${d.icon} **${d.name}** — ${d.agents} סוכנים | ${d.skills.slice(0,3).join(', ')}`)
      .join('\n');
    botMsg(`🎭 **The Agency — 12 Divisions:**\n\n${divStr}\n\n**סה"\u05db: 144+ סוכנים** — כלים, תהליכים, ודוגמאות.\nJARVIS: **${AGENCY_KNOWLEDGE.jarvis.passes} passes** · **${AGENCY_KNOWLEDGE.jarvis.tests.toLocaleString()} בדיקות**`);
    return;
  }

  // SuperAGI specific
  if (lower.includes('superagi') || lower.includes('super agi')) {
    const n = S.nodes.find(n=>n.repo.name==='SuperAGI');
    if (n) selectNode(n);
    botMsg(`🤖 **SuperAGI** — פרימוורק AGI פתוח (פורק שלך)\n\n• 14.8K כוכבים | 1,920 פורקים\n• תכונות: סוכנים מקבילים, toolkits, vector DB, זיכרון, פלוויות\n• נתמך ל-agency runtime שלך`);
    return;
  }

  // Mythos
  if (lower.includes('mythos')) {
    const n = S.nodes.find(n=>n.repo.name==='Mythos');
    if (n) selectNode(n);
    botMsg(`⚡ **Mythos** — מנוע ספרות אוטונומי\n\n• 342 כוכבים | Python\n• מיצור סיפורים, בניית עולמות, דמויות באמצעות LLMs\n• משתלב עם agency-agents לסיפור אינטראקטיבי`);
    return;
  }

  // Trading engine
  if (lower.includes('trad') || lower.includes('מסחר') || lower.includes('autonomous-trading')) {
    const n = S.nodes.find(n=>n.repo.name==='autonomous-trading-engine');
    if (n) selectNode(n);
    botMsg(`📈 **Autonomous Trading Engine**\n\n• 567 כוכבים | Python\n• אסטרטגיות מרובות, פירוש שוק real-time, RL\n• נתמך: מניית סיכונים, מיטב portfolio`);
    return;
  }

  // Scan
  if (lower.match(/^(סרוק|scan|חפש|find)\s+(.+)$/i)) {
    const m = text.match(/^(?:סרוק|scan|חפש|find)\s+(.+)$/i);
    if (m) { scanGitHub(m[1].trim(),'','100'); return; }
  }

  // Trending
  if (lower.includes('טרנד') || lower.includes('trending') || lower.includes('חם')) {
    scanTrending(); return;
  }

  // Strongest
  if (lower.includes('חזק') || lower.includes('strongest') || lower.includes('הכי')) {
    if (!S.nodes.length) { botMsg('❌ אין ריפוז. סרוק קודם!'); return; }
    const best = [...S.nodes].sort((a,b)=>b.power-a.power)[0];
    selectNode(best);
    botMsg(`🏆 **${best.repo.full_name}** — עוצמה: **${best.power}**\n⭐ ${fmtN(best.repo.stargazers_count)} · 🍴 ${fmtN(best.repo.forks_count)} · ${CATS[best.cat].icon} ${CATS[best.cat].label}`);
    return;
  }

  // Synergies
  if (lower.includes('סינרגי') || lower.includes('synerg') || lower.includes('חיבור')) {
    if (!S.synergies.length) { botMsg('🌀 אין מספיק ריפוז. סרוק עוד!'); return; }
    const top = S.synergies[0];
    botMsg(`✨ **Top Synergy**: ${top.a.repo.name} ⚡ ${top.b.repo.name} — **${Math.round(top.score*100)}%**\n\n${top.reasons.join(' · ')}\n\nסך הכל **${S.synergies.length}** סינרגיות.`);
    return;
  }

  // Summary / Status
  if (lower.includes('סיכום') || lower.includes('summary') || lower.includes('status') || lower.includes('מצב')) {
    const catC = {}; for (const n of S.nodes) catC[n.cat]=(catC[n.cat]||0)+1;
    const catStr = Object.entries(catC).map(([c,n])=>`${CATS[c].icon} **${CATS[c].label}**: ${n}`).join('\n');
    botMsg(`📊 **SINGULARITY STATUS**\n\n📦 Repos: **${S.nodes.length}** · 🔗 Edges: **${S.edges.length}** · ✨ Synergies: **${S.synergies.length}**\n⚡ Total Power: **${S.nodes.reduce((s,n)=>s+n.power,0)}**\n\n${catStr || 'No repos yet'}\n\nOllama: **${S.ollama.available?S.ollama.model:'offline'}**`);
    return;
  }

  // Agents
  if (lower.includes('agent') || lower.includes('סוכן')) {
    botMsg(`🤖 **Agency Runtime — 144+ Agents:**\n\n• **design** division: UI/UX, branding\n• **engineering** division: backend, frontend, devops\n• **ai** division: ML, NLP, vision\n• **finance** division: trading, analysis\n• **science** division: research, data\n• **strategy** division: planning, roadmap\n• **sales / marketing / support** divisions\n• ...ועוד 17 divisions עם מאות סוכנים.\n\nהשתמש ב-JARVIS Desktop לניתוב אוטומטי.`);
    return;
  }

  // Memory display
  if (lower.includes('memory') || lower.includes('זיכרון') || lower.includes('recall all')) {
    const mems = Object.entries(S.memory);
    if (!mems.length) { botMsg('💾 הזיכרון ריק. השתמש ב-`remember key=value`'); return; }
    botMsg(`💾 **זיכרון:**\n\n${mems.map(([k,v])=>`**${k}**: ${v}`).join('\n')}`);
    botMsg('💾 השתמש ב-`recall [key]` כדי לשלוף זיכרון מהסרבר.');
    return;
  }

  // Help
  if (lower.includes('עזר') || lower.includes('help') || lower.includes('מה אתה')) {
    botMsg(`אני **J.A.R.V.I.S Singularity One** — מוח קולקטיבי.\n\n**פקודות:**\n• \`סרוק [נושא]\` — סרוק GitHub\n• \`🔥 trending\` — טרנדים\n• \`מה הכי חזק?\` — הריפו הכי חזק\n• \`סינרגיות\` — מצא חיבורים\n• \`סיכום\` — סטטוס\n• \`agents\` — רשימת סוכנים\n• \`remember k=v\` — שמור בזיכרון\n• \`recall k\` — הזכר\n• \`!cmd\` — shell (Desktop only)\n• \`github [url]\` — clone & integrate`);
    return;
  }

  // Greetings
  const greet = {
    hello:'שלום, Sir.', hi:'Yes, Sir?', שלום:'שלום, Sir. כל המערכות פעילות.',
    'good morning':'בוקר טוב, Sir. כל המערכות אונליין.',
    'good night':'לילה טוב, Sir. המוח ממשיך לעבוד ברקע.',
  };
  for (const [k,v] of Object.entries(greet)) {
    if (lower.includes(k)) { botMsg(v); return; }
  }

  // Singularity backend routing (replaces old local fallback)
  callSingularityRoute(text);
}

async function callOllama(prompt) {
  const loadMsg = addTypingIndicator();
  try {
    const resp = await fetch(`${CFG.OLLAMA_URL}/api/chat`, {
      method: 'POST',
      headers: { 'Content-Type':'application/json' },
      body: JSON.stringify({
        model: S.ollama.model,
        messages: [
          { role:'system', content:`You are J.A.R.V.I.S, a sophisticated AI assistant for ${CFG.USER}. You have access to GitHub knowledge: ${S.nodes.length} repos analyzed. Respond concisely in the same language as the user.` },
          { role:'user', content:prompt }
        ],
        stream: false,
      }),
    });
    removeTypingIndicator(loadMsg);
    if (!resp.ok) throw new Error(`Ollama ${resp.status}`);
    const data = await resp.json();
    const ans = data.message?.content || '[no response]';
    botMsg(ans);
  } catch(e) {
    removeTypingIndicator(loadMsg);
    botMsg(`⚠️ Ollama שגיאה: ${e.message}`);
  }
}

async function callLocalAgentServer(message, fallbackToMockOnFail = false) {
  const loadMsg = addTypingIndicator();
  try {
    const resp = await fetch(`${CFG.API_BASE}/api/run`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message }),
    });
    removeTypingIndicator(loadMsg);
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();
    botMsg(data.text || '[no response]');
  } catch (err) {
    removeTypingIndicator(loadMsg);
    if (fallbackToMockOnFail) {
      const responses = [
        `🤔 מעניין! המערכת המקומית לא זמינה.\n\nנסה להפעיל את השרת:\n\`python JARVIS_SUPREME.py run\``,
        `💡 כדי לשוחח חופשי, הפעל את השרת או התקן **Ollama** (ollama.ai):\n\`ollama pull llama3.2\``,
      ];
      botMsg(responses[Math.floor(Math.random() * responses.length)]);
    } else {
      botMsg(`⚠️ שגיאה בתקשורת עם השרת המקומי: ${err.message}\nוודא שהשרת פועל בכתובת http://127.0.0.1:8765`);
    }
  }
}

async function detectOllama() {
  try {
    const resp = await fetch(`${CFG.OLLAMA_URL}/api/tags`, { signal: AbortSignal.timeout(2000) });
    if (resp.ok) {
      const data = await resp.json();
      const models = data.models?.map(m=>m.name)||[];
      S.ollama.available = true;
      const preferred = ['llama3.2','llama3.1','llama3','qwen2.5','mistral','phi3'];
      S.ollama.model = models.find(m => preferred.some(p=>m.toLowerCase().includes(p))) || models[0] || 'llama3';
      if ($('#s-llm')) $('#s-llm').textContent = `OLLAMA: ${S.ollama.model}`;
      setDiagBar('OLLAMA', 100, '✓');
    }
  } catch {
    setDiagBar('OLLAMA', 0, 'OFFLINE');
  }
}

/* ════════════════════════════════════════════════════════════════════
   VOICE RECOGNITION
════════════════════════════════════════════════════════════════════ */
let recognition = null;
function initVoice() {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) { botMsg('⚠️ Voice recognition לא נתמך בדפדפן זה. נסה Chrome.'); return; }
  recognition = new SR();
  recognition.continuous = false;
  recognition.interimResults = false;
  recognition.lang = 'he-IL';
  recognition.onresult = e => {
    const t = e.results[0][0].transcript.trim();
    if (t) handleChat(t);
  };
  recognition.onerror = () => {};
  recognition.onend = () => {
    S.speechActive = false;
    const btn = $('#btn-voice'); if (btn) btn.classList.remove('active');
    if ($('#orb-state')) $('#orb-state').textContent = 'IDLE';
  };
}

function toggleVoice() {
  if (!recognition) { initVoice(); if (!recognition) return; }
  if (S.speechActive) {
    recognition.stop(); S.speechActive = false;
    $('#btn-voice')?.classList.remove('active');
    if ($('#orb-state')) $('#orb-state').textContent = 'IDLE';
  } else {
    recognition.start(); S.speechActive = true;
    $('#btn-voice')?.classList.add('active');
    if ($('#orb-state')) $('#orb-state').textContent = 'LISTENING ●';
    sysMsg('[VOICE] Listening...');
  }
}

/* ════════════════════════════════════════════════════════════════════
   MEMORY (localStorage)
════════════════════════════════════════════════════════════════════ */
function loadMemory() {
  try { S.memory = JSON.parse(localStorage.getItem('jarvis_singularity_memory')||'{}'); } catch { S.memory = {}; }
}
function saveMemory() {
  try { localStorage.setItem('jarvis_singularity_memory', JSON.stringify(S.memory)); } catch {}
}
function setMemory(k, v) {
  S.memory[k] = v;
  saveMemory();
  initMemoryDisplay();

  // Sync to Unified Memory on the local server
  fetch(`${CFG.API_BASE}/api/memory/remember`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ kind: 'semantic', content: v, tags: [k] })
  })
  .then(resp => {
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    return resp.json();
  })
  .then(data => {
    sysMsg(`[MEMORY] Synced '${k}' to SQLite FTS5 database.`);
  })
  .catch(err => {
    sysMsg(`[MEMORY] Sync failed for '${k}': ${err.message}`);
  });
}
function getMemory(k) { return S.memory[k]; }

function initMemoryDisplay() {
  const list = $('#memory-list'); if (!list) return;
  const builtIn = [
    ['USER','Sir (Amjad)'],['VERSION',CFG.VERSION],
    ['FILES','33,784'],['AGENTS','144+'],['PERM','GOD MODE'],["WAKE","jarvis / ג'רוויס"],
  ];
  const custom = Object.entries(S.memory);
  list.innerHTML = [...builtIn, ...custom].map(([k,v])=>
    `<div class="mem-item"><span class="mem-key">${k}</span><span class="mem-val">${v}</span></div>`
  ).join('');
}

/* ════════════════════════════════════════════════════════════════════
   DIAGNOSTIC LOG
════════════════════════════════════════════════════════════════════ */
const LOG_MESSAGES = [
  'neural sync OK','agent registered','memory write','ollama tok '+~~(Math.random()*50+40),
  'vector recall','skill scan +1','audio fft','wake monitor','ctx update',
  'embed ok','synergy calc','repo absorbed','edge built','physics tick',
  'gpu frame','shader pass','particle tick','log entry','status OK',
];
async function fetchSingularityStatus() {
  try {
    const resp = await fetch(`${CFG.API_BASE}/api/singularity/status`);
    if (!resp.ok) return;
    const data = await resp.json();
    
    // Update diagnostic bars based on real data
    setDiagBar('SINGULARITY', 100, data.status.toUpperCase());
    
    const uptimePct = Math.min(100, (data.uptime / 3600) * 100);
    setDiagBar('GODSKILL', uptimePct, `${data.uptime.toFixed(0)}s`);
    
    if (data.cache_info) {
      const cacheHitRate = data.cache_info.total_requests > 0 
        ? (data.cache_info.hits / data.cache_info.total_requests) * 100 
        : 100;
      setDiagBar('MEMORY', cacheHitRate, `${cacheHitRate.toFixed(1)}%`);
    }

    if (data.learning_metrics) {
      const healedPct = data.learning_metrics.total_errors > 0 
        ? (data.learning_metrics.successful_heals / data.learning_metrics.total_errors) * 100
        : 100;
      setDiagBar('NEURAL', healedPct, `${healedPct.toFixed(1)}%`);
    }

    // Add log entry
    if (data.cache_info && data.cache_info.total_requests > 0) {
      addLogLine(`router.requests: ${data.cache_info.total_requests}`);
    }

  } catch (e) {
    setDiagBar('SINGULARITY', 0, 'OFFLINE');
  }
}

function addLogLine(text) {
  const lines = $('#ll-lines'); if (!lines) return;
  const el = document.createElement('div');
  el.className = 'll-line';
  el.textContent = '› ' + text;
  el.style.direction = 'ltr';
  lines.appendChild(el);
  while (lines.children.length > 8) lines.removeChild(lines.firstChild);
}

function initDiagLog() {
  setInterval(() => {
    const line = LOG_MESSAGES[~~(Math.random()*LOG_MESSAGES.length)];
    addLogLine(line);
  }, 1800);
  
  // Fetch live stats every 2 seconds
  setInterval(fetchSingularityStatus, 2000);
  setTimeout(fetchSingularityStatus, 500);
}

function setDiagBar(sys, pct, label) {
  const rows = $$('.diag-row');
  for (const row of rows) {
    if (row.dataset.sys === sys) {
      const fill = row.querySelector('.dr-fill');
      const val = row.querySelector('.dr-val');
      if (fill) { fill.style.width = pct+'%'; fill.classList.remove('dr-detecting'); }
      if (val) val.textContent = label||pct+'%';
    }
  }
}

/* ════════════════════════════════════════════════════════════════════
   CHAT UI HELPERS
════════════════════════════════════════════════════════════════════ */
function botMsg(text) {
  addMsg('bot', text, '🧠');
}
function userMsg(text) {
  addMsg('user', text, '👤');
}
function sysMsg(text) {
  addMsg('sys', text, null);
}

function addMsg(type, text, avatar) {
  const msgs = $('#chat-messages'); if (!msgs) return;
  const div = document.createElement('div');
  div.className = 'msg '+type;
  if (type==='sys') {
    div.innerHTML = `<div class="msg-body">${escHtml(text)}</div>`;
  } else {
    div.innerHTML = `
      ${avatar?`<div class="msg-av">${avatar}</div>`:''}
      <div class="msg-body">${formatMd(text)}</div>`;
  }
  msgs.appendChild(div);
  msgs.scrollTop = msgs.scrollHeight;
}

function addTypingIndicator() {
  const msgs = $('#chat-messages'); if (!msgs) return null;
  const div = document.createElement('div');
  div.className = 'msg bot';
  div.innerHTML = `<div class="msg-av">🧠</div><div class="msg-body"><span class="typing-dots"><span></span><span></span><span></span></span></div>`;
  msgs.appendChild(div); msgs.scrollTop = msgs.scrollHeight;
  return div;
}
function removeTypingIndicator(el) { el?.remove(); }

/* ════════════════════════════════════════════════════════════════════
   CANVAS INTERACTION
════════════════════════════════════════════════════════════════════ */
function screenToWorld(sx, sy) {
  const dpr = window.devicePixelRatio||1;
  const W = neuralCanvas.offsetWidth, H = neuralCanvas.offsetHeight;
  return {
    x: (sx - W/2) / S.camera.zoom + W/2 - S.camera.x,
    y: (sy - H/2) / S.camera.zoom + H/2 - S.camera.y,
  };
}
function findNodeAt(wx, wy) {
  for (let i=S.nodes.length-1; i>=0; i--) {
    const n=S.nodes[i], dx=wx-n.x, dy=wy-n.y;
    if (dx*dx+dy*dy<(n.r+6)*(n.r+6)) return n;
  }
  return null;
}

function selectNode(node) {
  if (S.selectedNode) S.selectedNode.targetGlow = 0;
  S.selectedNode = node;
  if (node) {
    node.targetGlow = 1;
    showEssence(node);
    showNodeInspector(node);
    $$('.repo-card').forEach(c => c.classList.remove('active'));
    $$('.repo-card').forEach(c => {
      if (c.querySelector('.rc-name')?.textContent === node.repo.full_name) c.classList.add('active');
    });
  }
}
function selectRepo(repo) {
  const n = S.nodes.find(n=>n.id===repo.id);
  if (n) selectNode(n);
}

function showNodeInspector(node) {
  const ni = $('#node-inspector'), nc = $('#ni-content'); if (!ni||!nc) return;
  nc.innerHTML = `
    <div class="ni-name">${node.repo.full_name}</div>
    <p style="font-size:.75rem;color:rgba(232,244,255,.5);margin-bottom:6px;direction:ltr">${node.repo.description||''}</p>
    <div class="ni-stat-row">
      <div class="ni-stat"><div class="ni-sv" style="color:${node.color}">⭐${fmtN(node.repo.stargazers_count)}</div><div class="ni-sl">Stars</div></div>
      <div class="ni-stat"><div class="ni-sv" style="color:${node.color}">🍴${fmtN(node.repo.forks_count)}</div><div class="ni-sl">Forks</div></div>
      <div class="ni-stat"><div class="ni-sv" style="color:${node.color}">⚡${node.power}</div><div class="ni-sl">Power</div></div>
    </div>
    ${node.repo.topics?.length?`<div class="ni-topics">${node.repo.topics.slice(0,6).map(t=>`<span class="topic-tag">${t}</span>`).join('')}</div>`:''}`;
  ni.style.display = 'block';
}

/* ════════════════════════════════════════════════════════════════════
   SINGULARITY ROUTER
════════════════════════════════════════════════════════════════════ */
async function callSingularityRoute(query) {
  S.brainActiveState = 'ROUTING';
  const rv = $('#singularity-router-view');
  if (rv) {
    rv.innerHTML = `<div class="empty-st" style="padding:10px;"><span>🔮</span><p style="font-size:0.65rem;">Routing query...</p></div>`;
  }
  
  try {
    const resp = await fetch(`${CFG.API_BASE}/api/singularity/route`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query: query })
    });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();
    
    if (rv) {
      rv.innerHTML = `
        <div style="font-size:0.65rem; color:var(--textD); padding:8px; line-height:1.5; direction:ltr; text-align:left;">
          <div style="color:var(--cyan); margin-bottom:6px; font-weight:bold;">↳ ${data.action || 'Routed'}</div>
          ${data.metrics ? `
          <div style="margin-bottom:6px;">
            Complexity: <span style="color:var(--gold)">${(data.metrics.complexity*100).toFixed(0)}%</span><br>
            Context: <span style="color:var(--purple)">${(data.metrics.context_size*100).toFixed(0)}%</span><br>
            Urgency: <span style="color:var(--pink)">${(data.metrics.urgency*100).toFixed(0)}%</span>
          </div>` : ''}
          <div style="color:var(--green); margin-top:8px;">Target: ${data.target_agent || 'Singularity Core'}</div>
        </div>
      `;
    }
    
    if (data.target_agent) {
      S.activePersona = data.target_agent;
      setTimeout(() => { S.activePersona = null; }, 4000); // Reset persona pulse after 4s
    }

    // Output the result to chat
    let botReply = '';
    if (typeof data.result === 'string') {
        botReply = data.result;
    } else if (data.result && data.result.final_output) {
        botReply = data.result.final_output;
    } else if (data.result && data.result.answer) {
        botReply = data.result.answer;
    } else if (data.result && data.result.code) {
        botReply = `\`\`\`${data.result.language || ''}\n${data.result.code}\n\`\`\``;
    } else {
        botReply = JSON.stringify(data.result || data);
    }
    
    botMsg(botReply);

  } catch (err) {
    if (rv) rv.innerHTML = `<div class="empty-st" style="padding:10px;"><span>⚠️</span><p style="font-size:0.65rem; color:var(--red);">Route Failed: ${err.message}</p></div>`;
  }
  S.brainActiveState = 'IDLE';
}

/* ════════════════════════════════════════════════════════════════════
   AGENT CONTROL CENTER (MODAL)
════════════════════════════════════════════════════════════════════ */
let ALL_AGENTS = [];

async function openAgentsModal() {
  const modal = $('#agents-modal');
  if (modal) modal.style.display = 'flex';
  
  const container = $('#agents-list-container');
  if (container) container.innerHTML = '<div class="empty-st"><span>🛸</span><p>Loading agent registry...</p></div>';

  try {
    const resp = await fetch(`${CFG.API_BASE}/api/agents`);
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();
    ALL_AGENTS = data.agents || [];
    renderAgentsList(ALL_AGENTS);
  } catch (err) {
    if (container) container.innerHTML = `<div class="empty-st"><span>⚠️</span><p>Error loading agents: ${err.message}</p></div>`;
  }
}

function renderAgentsList(agents) {
  const container = $('#agents-list-container');
  if (!container) return;
  
  if (agents.length === 0) {
    container.innerHTML = '<div class="empty-st"><span>😕</span><p>No agents found.</p></div>';
    return;
  }
  
  container.innerHTML = '';
  agents.forEach(ag => {
    const el = document.createElement('div');
    el.className = 'agent-list-item';
    el.innerHTML = `<strong>${ag.name}</strong><br><small>${ag.description ? ag.description.substring(0, 50) + '...' : 'No description'}</small>`;
    el.addEventListener('click', () => selectAgentInModal(ag, el));
    container.appendChild(el);
  });
}

function filterAgentsList() {
  const q = $('#agent-search')?.value?.toLowerCase() || '';
  const filtered = ALL_AGENTS.filter(a => a.name.toLowerCase().includes(q) || (a.description||'').toLowerCase().includes(q));
  renderAgentsList(filtered);
}

function selectAgentInModal(agent, element) {
  $$('.agent-list-item').forEach(el => el.classList.remove('active'));
  if (element) element.classList.add('active');
  
  const details = $('#selected-agent-details');
  const runPanel = $('#agent-run-panel');
  if (!details || !runPanel) return;
  
  details.innerHTML = `
    <h4 style="color:var(--cyan); font-size:1.1rem; margin-bottom:10px;">🤖 ${agent.name}</h4>
    <p style="color:var(--textD); line-height:1.5; font-size:0.8rem; margin-bottom:10px; direction:ltr;">${agent.description || 'N/A'}</p>
    <div style="font-size:0.75rem; display:flex; gap:6px; direction:ltr;">
      <span class="topic-tag">${agent.type || 'standard'}</span>
      ${agent.model ? `<span class="topic-tag">${agent.model}</span>` : ''}
    </div>
  `;
  
  runPanel.style.display = 'flex';
  runPanel.style.flexDirection = 'column';
  runPanel.style.gap = '8px';
  runPanel.style.marginTop = '16px';
  runPanel.dataset.agentId = agent.id || agent.name;
  
  const outBox = $('#agent-run-result');
  const outText = $('#agent-output-text');
  if (outBox) outBox.style.display = 'none';
  if (outText) outText.textContent = '';
  
  $('#agent-task-input').value = '';
}

async function runAgentTask() {
  const runPanel = $('#agent-run-panel');
  const agentId = runPanel?.dataset.agentId;
  const task = $('#agent-task-input')?.value?.trim();
  
  if (!agentId || !task) return;
  
  const btn = $('#btn-run-agent');
  const outBox = $('#agent-run-result');
  const outText = $('#agent-output-text');
  
  if (btn) { btn.textContent = '⚡ EXECUTING...'; btn.disabled = true; }
  if (outBox) outBox.style.display = 'block';
  if (outText) outText.textContent = 'Agent is thinking...';
  
  S.brainActiveState = 'EXECUTING';
  
  try {
    const resp = await fetch(`${CFG.API_BASE}/api/agents/run`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ agent_id: agentId, task: task })
    });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();
    if (outText) outText.textContent = data.output || JSON.stringify(data, null, 2);
  } catch (err) {
    if (outText) outText.textContent = `Error: ${err.message}`;
  }
  
  if (btn) { btn.textContent = '⚡ EXECUTE AGENT'; btn.disabled = false; }
  S.brainActiveState = 'IDLE';
  S.activePersona = null;
}

/* ════════════════════════════════════════════════════════════════════
   EVENT LISTENERS
════════════════════════════════════════════════════════════════════ */
function initEventListeners() {
  // Scan
  $('#scan-btn')?.addEventListener('click', () => {
    scanGitHub($('#scan-q')?.value?.trim()||'', $('#scan-lang')?.value, $('#scan-stars')?.value);
  });
  $('#scan-trending')?.addEventListener('click', scanTrending);
  $('#scan-q')?.addEventListener('keydown', e => { if (e.key==='Enter') $('#scan-btn')?.click(); });

  // Chat
  $('#chat-send')?.addEventListener('click', () => {
    const inp = $('#chat-input'); if (!inp) return;
    handleChat(inp.value); inp.value = '';
  });
  $('#chat-input')?.addEventListener('keydown', e => {
    if (e.key==='Enter') { const inp=e.target; handleChat(inp.value); inp.value=''; }
  });

  // Quick action buttons
  $('#btn-voice')?.addEventListener('click', toggleVoice);
  $('#btn-agents')?.addEventListener('click', openAgentsModal);
  $('#btn-github')?.addEventListener('click', () => handleChat('scan machine-learning'));
  $('#btn-screen')?.addEventListener('click', () => handleChat('status'));
  $('#btn-status')?.addEventListener('click', () => handleChat('סיכום'));
  $('#btn-shell')?.addEventListener('click', () => { const i=$('#chat-input'); if(i){i.value='!';i.focus();} });

  // Canvas controls
  $('#cc-zi')?.addEventListener('click', () => { S.camera.zoom = Math.min(S.camera.zoom*1.25, 5); });
  $('#cc-zo')?.addEventListener('click', () => { S.camera.zoom = Math.max(S.camera.zoom/1.25, .15); });
  $('#cc-rs')?.addEventListener('click', () => { S.camera = {x:0,y:0,zoom:1}; });
  $('#cc-lb')?.addEventListener('click', e => { S.showLabels=!S.showLabels; e.target.classList.toggle('active'); });
  $('#cc-ph')?.addEventListener('click', e => { S.physicsOn=!S.physicsOn; e.target.classList.toggle('active'); });

  // Close panels
  $('#ni-close')?.addEventListener('click', () => { $('#node-inspector').style.display='none'; if(S.selectedNode){S.selectedNode.targetGlow=0;S.selectedNode=null;} });
  $('#eo-close')?.addEventListener('click', () => { $('#essence-overlay').style.display='none'; });

  // Modal & Agents
  $('#am-close')?.addEventListener('click', () => { $('#agents-modal').style.display = 'none'; });
  $('#btn-run-agent')?.addEventListener('click', runAgentTask);
  $('#agent-search')?.addEventListener('input', filterAgentsList);

  // Neural canvas mouse
  neuralCanvas?.addEventListener('mousedown', onMD);
  neuralCanvas?.addEventListener('mousemove', onMM);
  neuralCanvas?.addEventListener('mouseup', onMU);
  neuralCanvas?.addEventListener('mouseleave', onMU);
  neuralCanvas?.addEventListener('wheel', onWheel, {passive:false});
  neuralCanvas?.addEventListener('dblclick', onDbl);

  // Memory save
  $('#mem-save')?.addEventListener('click', () => {
    const k=$('#mem-key-in')?.value?.trim(), v=$('#mem-val-in')?.value?.trim();
    if(k&&v){ setMemory(k,v); $('#mem-key-in').value=''; $('#mem-val-in').value=''; botMsg(`💾 **${k}** = ${v}`); }
  });

  // Quick commands
  $('#btn-agents')?.addEventListener('dblclick', () => handleChat('list agents'));
}

function onMD(e) {
  const rect=neuralCanvas.getBoundingClientRect();
  const {x,y}=screenToWorld(e.clientX-rect.left, e.clientY-rect.top);
  const node=findNodeAt(x,y);
  S.drag={on:true,lx:e.clientX,ly:e.clientY,node};
  if (node) selectNode(node);
}
function onMM(e) {
  const rect=neuralCanvas.getBoundingClientRect();
  const {x,y}=screenToWorld(e.clientX-rect.left, e.clientY-rect.top);
  const hov=findNodeAt(x,y);
  if (S.hoveredNode!==hov) {
    if(S.hoveredNode) S.hoveredNode.targetGlow=S.hoveredNode===S.selectedNode?1:0;
    S.hoveredNode=hov;
    if(hov && hov!==S.selectedNode) hov.targetGlow=.6;
    neuralCanvas.style.cursor=hov?'pointer':(S.drag.on?'grabbing':'grab');
  }
  if (S.drag.on) {
    if (S.drag.node) { S.drag.node.x=x; S.drag.node.y=y; S.drag.node.vx=0; S.drag.node.vy=0; }
    else { S.camera.x+=(e.clientX-S.drag.lx)/S.camera.zoom; S.camera.y+=(e.clientY-S.drag.ly)/S.camera.zoom; S.drag.lx=e.clientX; S.drag.ly=e.clientY; }
  }
}
function onMU() { S.drag={on:false,lx:0,ly:0,node:null}; }
function onWheel(e) { e.preventDefault(); S.camera.zoom=Math.max(.15,Math.min(5,S.camera.zoom*(e.deltaY>0?.88:1.14))); }
function onDbl(e) {
  const rect=neuralCanvas.getBoundingClientRect();
  const {x,y}=screenToWorld(e.clientX-rect.left,e.clientY-rect.top);
  const n=findNodeAt(x,y);
  if(n?.repo?.html_url) window.open(n.repo.html_url,'_blank');
}

/* ════════════════════════════════════════════════════════════════════
   STATS & UI UPDATES
════════════════════════════════════════════════════════════════════ */
function updateHeaderStats() {
  animCounter('hv-repos', S.repos.length);
  animCounter('hv-nodes', S.nodes.length);
  animCounter('hv-power', S.nodes.reduce((s,n)=>s+n.power,0));
}

function animCounter(id, target) {
  const el = document.getElementById(id); if (!el) return;
  const raw = el.textContent || '0';
  const mult = raw.includes('M') ? 1000000 : raw.includes('K') ? 1000 : 1;
  const cur = (parseFloat(raw.replace(/[KM]/g,'')) || 0) * mult;
  const diff=target-cur, steps=Math.min(Math.abs(diff),20);
  if (!diff||!steps) return;
  const inc=diff/steps; let step=0;
  const tick=()=>{ step++; el.textContent=fmtN(step>=steps?target:Math.round(cur+inc*step)); if(step<steps)requestAnimationFrame(tick); };
  tick();
}

function updateScanUI(scanning) {
  const btn=$('#scan-btn');
  if(!btn) return;
  if(scanning){btn.textContent='🔄 SCANNING...';btn.disabled=true;}
  else{btn.innerHTML='⚡ SCAN & ABSORB';btn.disabled=false;}
}

function updateClock() {
  const cl=$('#hdr-clock');
  if(cl) cl.textContent=new Date().toLocaleTimeString('he-IL',{hour12:false});
}

/* ════════════════════════════════════════════════════════════════════
   UTILITIES
════════════════════════════════════════════════════════════════════ */
function fmtN(n) {
  n=Number(n)||0;
  if(n>=1e6) return (n/1e6).toFixed(1)+'M';
  if(n>=1e3) return (n/1e3).toFixed(1)+'K';
  return String(n);
}

function lerp(a,b,t) { return a+(b-a)*Math.max(0,Math.min(1,t)); }

function hexA(hex, alpha) {
  if(!hex||!hex.startsWith('#')) return `rgba(0,229,255,${alpha})`;
  const h=hex.replace('#','');
  const r=parseInt(h.slice(0,2),16), g=parseInt(h.slice(2,4),16), b=parseInt(h.slice(4,6),16);
  return `rgba(${r},${g},${b},${alpha})`;
}

function lerpHex(c1, c2, t) {
  if(!c1?.startsWith('#')||!c2?.startsWith('#')) return 'rgb(0,229,255)';
  const h1=c1.slice(1), h2=c2.slice(1);
  const r=Math.round(parseInt(h1.slice(0,2),16)*(1-t)+parseInt(h2.slice(0,2),16)*t);
  const g=Math.round(parseInt(h1.slice(2,4),16)*(1-t)+parseInt(h2.slice(2,4),16)*t);
  const b=Math.round(parseInt(h1.slice(4,6),16)*(1-t)+parseInt(h2.slice(4,6),16)*t);
  return `rgb(${r},${g},${b})`;
}

function formatMd(text) {
  return escHtml(text)
    .replace(/\*\*(.+?)\*\*/g,'<strong>$1</strong>')
    .replace(/\*(.+?)\*/g,'<em>$1</em>')
    .replace(/`(.+?)`/g,'<code>$1</code>')
    .replace(/\n/g,'<br>');
}

function escHtml(text) {
  return String(text).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

/* ════════════════════════════════════════════════════════════════════
   MAIN ANIMATION LOOP
════════════════════════════════════════════════════════════════════ */
let lastT = 0;
function animate(t = 0) {
  requestAnimationFrame(animate);

  // FPS counter
  S.fpsCounter++;
  if (t - S.fpsTime > 1000) {
    S.fps = S.fpsCounter;
    S.fpsCounter = 0; S.fpsTime = t;
    if ($('#ns-fps')) $('#ns-fps').textContent = `${S.fps} fps`;
  }

  S.orbPhase = (S.orbPhase + .014) % (Math.PI*2);

  // Background
  drawBackground(t);

  // Brain orb
  const actState = S.brainActiveState !== 'IDLE' ? S.brainActiveState : (S.speechActive ? 'LISTENING' : 'IDLE');
  drawBrainOrb(brainOrbCtx, 220, 220, S.orbPhase, 0, actState, S.activePersona);

  // Mini orb (header)
  drawMiniOrb(miniOrbCtx, 52, 52, S.orbPhase);

  // Boot orb if visible
  if (bootOrbCtx) drawMiniOrb(bootOrbCtx, 220, 220, S.orbPhase);

  // Physics
  updatePhysics();

  // Neural network
  drawNeural(t);

  lastT = t;
}

/* ════════════════════════════════════════════════════════════════════
   ADDITIONAL: Canvas.createConicalGradient polyfill placeholder
════════════════════════════════════════════════════════════════════ */
// Note: Standard canvas doesn't have createConicalGradient.
// The conical effect in drawBrainOrb uses a rotation trick instead.
