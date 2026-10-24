// three_mill.js – Interactive 3D Digital Twin Visualizer for All 4 Factory Assets
// Procedural Three.js representations:
// 1. VMC-01: 3-Axis CNC Vertical Machining Center (Spindle, Tool Holder, Carbide Tool, Bed, Workpiece)
// 2. LATHE-01: CNC Turning Lathe (Slant Bed, 3-Jaw Chuck, Bar Stock, Carriage Turret, Tailstock)
// 3. SAW-01: Horizontal Metal Band Saw (Roller Bed, Clamping Vise, Saw Bow, Dual Wheels, Band Blade)
// 4. COMP-01: Rotary Air Compressor (Receiver Pressure Tank, Motor, Cooling Fan, Live Pressure Gauge)

let threeRenderer = null;
let threeScene = null;
let threeCamera = null;
let orbitControls = null;
let animationId = null;
let animating = true;
let currentMachineId = null;
let currentTemplate = null;

// Dynamic animated components
let animComponents = {
  rotatingGroup: null,
  speed: 0.02,
  hotMesh: null,
  gaugeNeedle: null,
  tankMesh: null,
  bladeMesh: null,
};

function disposeThree() {
  if (animationId) {
    cancelAnimationFrame(animationId);
    animationId = null;
  }
  if (orbitControls) {
    orbitControls.dispose();
    orbitControls = null;
  }
  if (threeRenderer) {
    threeRenderer.dispose();
    const canvas = threeRenderer.domElement;
    if (canvas && canvas.parentNode) canvas.parentNode.removeChild(canvas);
    threeRenderer = null;
  }
  threeScene = null;
  threeCamera = null;
  currentMachineId = null;
  currentTemplate = null;
  animComponents = {
    rotatingGroup: null,
    speed: 0.02,
    hotMesh: null,
    gaugeNeedle: null,
    tankMesh: null,
    bladeMesh: null,
  };
}

function initThreeView(machineId) {
  disposeThree();

  const wrapper = document.getElementById('threeCanvasWrapper') || document.getElementById('detailView');
  if (!wrapper) return;

  wrapper.innerHTML = '';

  const canvas = document.createElement('canvas');
  canvas.id = 'threeCanvas';
  canvas.style.width = '100%';
  canvas.style.height = '360px';
  canvas.style.display = 'block';
  canvas.style.borderRadius = 'var(--radius-sm, 6px)';
  canvas.style.background = '#090d16';
  wrapper.appendChild(canvas);

  const width = wrapper.clientWidth || 500;
  const height = 360;

  threeRenderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
  threeRenderer.setSize(width, height);
  threeRenderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));

  threeScene = new THREE.Scene();
  threeCamera = new THREE.PerspectiveCamera(45, width / height, 0.1, 1000);
  threeCamera.position.set(2.5, 2.0, 3.5);

  // Lighting
  const ambient = new THREE.AmbientLight(0xffffff, 0.65);
  threeScene.add(ambient);
  const keyLight = new THREE.DirectionalLight(0xffd700, 0.85); // Metallic gold accent
  keyLight.position.set(5, 10, 7);
  threeScene.add(keyLight);
  const fillLight = new THREE.DirectionalLight(0x4488ff, 0.4); // Cool blue fill
  fillLight.position.set(-6, -2, -5);
  threeScene.add(fillLight);

  // Ground Grid
  const gridHelper = new THREE.GridHelper(5, 12, 0x444f60, 0x1b2333);
  gridHelper.position.y = -0.5;
  threeScene.add(gridHelper);

  // Determine template from machine ID or registry
  let template = "cnc_mill";
  if (typeof state !== 'undefined' && state.machines && state.machines[machineId]) {
    template = state.machines[machineId].template;
  } else if (machineId.includes("LATHE")) {
    template = "cnc_lathe";
  } else if (machineId.includes("SAW")) {
    template = "bar_saw";
  } else if (machineId.includes("COMP")) {
    template = "air_compressor";
  }

  currentMachineId = machineId;
  currentTemplate = template;

  if (template === "cnc_mill") {
    buildMillScene();
  } else if (template === "cnc_lathe") {
    buildLatheScene();
  } else if (template === "bar_saw") {
    buildSawScene();
  } else if (template === "air_compressor") {
    buildCompressorScene();
  }

  // OrbitControls
  orbitControls = new THREE.OrbitControls(threeCamera, threeRenderer.domElement);
  orbitControls.enableDamping = true;
  orbitControls.dampingFactor = 0.05;
  orbitControls.minDistance = 1;
  orbitControls.maxDistance = 10;
  orbitControls.target.set(0, 0.35, 0);

  // Apply latest telemetry state if available
  if (typeof state !== 'undefined' && state.obs && state.obs[machineId]) {
    window.updateMachineVisualization(machineId, state.obs[machineId], state.twin ? state.twin[machineId] : null);
  }

  function animate() {
    animationId = requestAnimationFrame(animate);
    if (animating && animComponents.rotatingGroup) {
      if (template === "cnc_mill") {
        animComponents.rotatingGroup.rotation.y += animComponents.speed;
      } else if (template === "cnc_lathe") {
        animComponents.rotatingGroup.rotation.z += animComponents.speed;
      } else if (template === "bar_saw") {
        animComponents.rotatingGroup.rotation.z += animComponents.speed;
      } else if (template === "air_compressor") {
        animComponents.rotatingGroup.rotation.x += animComponents.speed;
      }
    }
    if (orbitControls) orbitControls.update();
    if (threeRenderer && threeScene && threeCamera) {
      threeRenderer.render(threeScene, threeCamera);
    }
  }
  animate();
}

// -----------------------------------------------------------------------------
// Procedural Model Builders
// -----------------------------------------------------------------------------

function buildMillScene() {
  // Base
  const baseGeom = new THREE.BoxGeometry(2.0, 0.5, 1.6);
  const baseMat = new THREE.MeshStandardMaterial({ color: 0x222733, metalness: 0.7, roughness: 0.3 });
  const base = new THREE.Mesh(baseGeom, baseMat);
  base.position.y = -0.25;
  threeScene.add(base);

  // Column
  const colGeom = new THREE.BoxGeometry(0.65, 1.8, 0.7);
  const colMat = new THREE.MeshStandardMaterial({ color: 0x181d28, metalness: 0.6, roughness: 0.4 });
  const col = new THREE.Mesh(colGeom, colMat);
  col.position.set(0, 0.6, -0.45);
  threeScene.add(col);

  // Headstock
  const headGeom = new THREE.BoxGeometry(0.55, 0.4, 0.7);
  const headMat = new THREE.MeshStandardMaterial({ color: 0x2c3545, metalness: 0.6, roughness: 0.35 });
  const head = new THREE.Mesh(headGeom, headMat);
  head.position.set(0, 1.05, -0.15);
  threeScene.add(head);

  // Rotating Spindle Group
  const spindleGroup = new THREE.Group();
  spindleGroup.position.set(0, 0.85, 0.05);

  const chuckGeom = new THREE.CylinderGeometry(0.09, 0.09, 0.35, 32);
  const chuckMat = new THREE.MeshStandardMaterial({ color: 0xd0d5dd, metalness: 0.9, roughness: 0.1 });
  const chuck = new THREE.Mesh(chuckGeom, chuckMat);
  spindleGroup.add(chuck);

  // Carbide Tool (Gold / Metallic)
  const toolGeom = new THREE.CylinderGeometry(0.025, 0.025, 0.32, 16);
  const toolMat = new THREE.MeshStandardMaterial({
    color: 0xd4af37,
    emissive: 0x000000,
    metalness: 0.85,
    roughness: 0.2,
  });
  const tool = new THREE.Mesh(toolGeom, toolMat);
  tool.position.y = -0.28;
  spindleGroup.add(tool);
  threeScene.add(spindleGroup);

  // Machine Vise & Workpiece
  const pieceGeom = new THREE.BoxGeometry(0.5, 0.22, 0.5);
  const pieceMat = new THREE.MeshStandardMaterial({ color: 0x475467, metalness: 0.5, roughness: 0.5 });
  const piece = new THREE.Mesh(pieceGeom, pieceMat);
  piece.position.set(0, 0.11, 0.05);
  threeScene.add(piece);

  animComponents.rotatingGroup = spindleGroup;
  animComponents.hotMesh = tool;
  animComponents.speed = 0.03;
}

function buildLatheScene() {
  // Slant Bed
  const bedGeom = new THREE.BoxGeometry(2.4, 0.5, 1.2);
  const bedMat = new THREE.MeshStandardMaterial({ color: 0x1f242e, metalness: 0.7, roughness: 0.3 });
  const bed = new THREE.Mesh(bedGeom, bedMat);
  bed.position.y = -0.25;
  threeScene.add(bed);

  // Headstock Housing (Left)
  const hsGeom = new THREE.BoxGeometry(0.7, 0.9, 0.9);
  const hsMat = new THREE.MeshStandardMaterial({ color: 0x2b3342, metalness: 0.6, roughness: 0.4 });
  const hs = new THREE.Mesh(hsGeom, hsMat);
  hs.position.set(-0.75, 0.35, 0);
  threeScene.add(hs);

  // Rotating Chuck & Cylindrical Bar Stock
  const chuckGroup = new THREE.Group();
  chuckGroup.position.set(-0.35, 0.35, 0);
  chuckGroup.rotation.y = Math.PI / 2;

  // 3-Jaw Chuck
  const chuckGeom = new THREE.CylinderGeometry(0.28, 0.28, 0.16, 32);
  const chuckMat = new THREE.MeshStandardMaterial({ color: 0xd0d5dd, metalness: 0.9, roughness: 0.1 });
  const chuck = new THREE.Mesh(chuckGeom, chuckMat);
  chuck.rotation.x = Math.PI / 2;
  chuckGroup.add(chuck);

  // Workpiece Stock Cylinder
  const stockGeom = new THREE.CylinderGeometry(0.12, 0.12, 0.9, 32);
  const stockMat = new THREE.MeshStandardMaterial({
    color: 0x64748b,
    emissive: 0x000000,
    metalness: 0.7,
    roughness: 0.3,
  });
  const stock = new THREE.Mesh(stockGeom, stockMat);
  stock.position.y = -0.5;
  stock.rotation.x = Math.PI / 2;
  chuckGroup.add(stock);
  threeScene.add(chuckGroup);

  // Carriage & Tool Post
  const postGeom = new THREE.BoxGeometry(0.35, 0.3, 0.4);
  const postMat = new THREE.MeshStandardMaterial({ color: 0x334155, metalness: 0.6, roughness: 0.4 });
  const post = new THREE.Mesh(postGeom, postMat);
  post.position.set(0.1, 0.25, 0.32);
  threeScene.add(post);

  // Lathe Insert (Gold Carbide)
  const insertGeom = new THREE.BoxGeometry(0.06, 0.04, 0.12);
  const insertMat = new THREE.MeshStandardMaterial({ color: 0xd4af37, metalness: 0.9, roughness: 0.1 });
  const insert = new THREE.Mesh(insertGeom, insertMat);
  insert.position.set(0.1, 0.35, 0.18);
  threeScene.add(insert);

  // Tailstock (Right)
  const tsGeom = new THREE.BoxGeometry(0.45, 0.6, 0.6);
  const tsMat = new THREE.MeshStandardMaterial({ color: 0x242c3b, metalness: 0.6, roughness: 0.4 });
  const ts = new THREE.Mesh(tsGeom, tsMat);
  ts.position.set(0.85, 0.25, 0);
  threeScene.add(ts);

  animComponents.rotatingGroup = chuckGroup;
  animComponents.hotMesh = stock;
  animComponents.speed = 0.04;
}

function buildSawScene() {
  // Base
  const baseGeom = new THREE.BoxGeometry(2.2, 0.5, 1.2);
  const baseMat = new THREE.MeshStandardMaterial({ color: 0x1a202c, metalness: 0.7, roughness: 0.3 });
  const base = new THREE.Mesh(baseGeom, baseMat);
  base.position.y = -0.25;
  threeScene.add(base);

  // Raw Stock Bar in Vise
  const barGeom = new THREE.CylinderGeometry(0.15, 0.15, 1.8, 24);
  const barMat = new THREE.MeshStandardMaterial({ color: 0x475569, metalness: 0.6, roughness: 0.4 });
  const bar = new THREE.Mesh(barGeom, barMat);
  bar.rotation.z = Math.PI / 2;
  bar.position.set(0, 0.15, 0);
  threeScene.add(bar);

  // Clamping Vise Jaws
  const viseGeom = new THREE.BoxGeometry(0.4, 0.4, 0.8);
  const viseMat = new THREE.MeshStandardMaterial({ color: 0x334155, metalness: 0.6, roughness: 0.4 });
  const vise = new THREE.Mesh(viseGeom, viseMat);
  vise.position.set(0, 0.15, 0);
  threeScene.add(vise);

  // Saw Bow Frame (Pivoting Arm)
  const bowGeom = new THREE.BoxGeometry(1.6, 0.45, 0.25);
  const bowMat = new THREE.MeshStandardMaterial({ color: 0x2d3748, metalness: 0.6, roughness: 0.4 });
  const bow = new THREE.Mesh(bowGeom, bowMat);
  bow.position.set(0, 0.55, 0.25);
  threeScene.add(bow);

  // Rotating Band Wheels Group
  const wheelsGroup = new THREE.Group();
  wheelsGroup.position.set(0, 0.55, 0.25);

  const wheelMat = new THREE.MeshStandardMaterial({ color: 0x94a3b8, metalness: 0.8, roughness: 0.2 });
  const wheelGeom = new THREE.CylinderGeometry(0.2, 0.2, 0.08, 24);

  const leftWheel = new THREE.Mesh(wheelGeom, wheelMat);
  leftWheel.rotation.x = Math.PI / 2;
  leftWheel.position.set(-0.65, 0, 0);
  wheelsGroup.add(leftWheel);

  const rightWheel = new THREE.Mesh(wheelGeom, wheelMat);
  rightWheel.rotation.x = Math.PI / 2;
  rightWheel.position.set(0.65, 0, 0);
  wheelsGroup.add(rightWheel);

  // Band Saw Blade Strip
  const bladeGeom = new THREE.BoxGeometry(1.4, 0.04, 0.02);
  const bladeMat = new THREE.MeshStandardMaterial({
    color: 0xcfd4dc,
    emissive: 0x000000,
    metalness: 0.9,
    roughness: 0.2,
  });
  const blade = new THREE.Mesh(bladeGeom, bladeMat);
  blade.position.set(0, -0.18, 0);
  wheelsGroup.add(blade);
  threeScene.add(wheelsGroup);

  animComponents.rotatingGroup = wheelsGroup;
  animComponents.bladeMesh = blade;
  animComponents.speed = 0.02;
}

function buildCompressorScene() {
  // Mounting Skid Base
  const skidGeom = new THREE.BoxGeometry(2.2, 0.15, 1.2);
  const skidMat = new THREE.MeshStandardMaterial({ color: 0x1e293b, metalness: 0.7, roughness: 0.3 });
  const skid = new THREE.Mesh(skidGeom, skidMat);
  skid.position.y = -0.42;
  threeScene.add(skid);

  // Horizontal Air Receiver Tank (Cylinder)
  const tankGeom = new THREE.CylinderGeometry(0.42, 0.42, 1.7, 32);
  const tankMat = new THREE.MeshStandardMaterial({
    color: 0x0f766e, // Industrial teal/graphite
    emissive: 0x000000,
    metalness: 0.6,
    roughness: 0.35,
  });
  const tank = new THREE.Mesh(tankGeom, tankMat);
  tank.rotation.z = Math.PI / 2;
  tank.position.set(0, -0.05, -0.1);
  threeScene.add(tank);

  // Motor Housing
  const motorGeom = new THREE.CylinderGeometry(0.24, 0.24, 0.75, 24);
  const motorMat = new THREE.MeshStandardMaterial({ color: 0x334155, metalness: 0.7, roughness: 0.3 });
  const motor = new THREE.Mesh(motorGeom, motorMat);
  motor.rotation.z = Math.PI / 2;
  motor.position.set(-0.35, 0.55, -0.1);
  threeScene.add(motor);

  // Rotary Screw Pump Block
  const pumpGeom = new THREE.BoxGeometry(0.5, 0.45, 0.5);
  const pumpMat = new THREE.MeshStandardMaterial({ color: 0x475569, metalness: 0.8, roughness: 0.25 });
  const pump = new THREE.Mesh(pumpGeom, pumpMat);
  pump.position.set(0.4, 0.55, -0.1);
  threeScene.add(pump);

  // Rotating Cooling Fan (Multi-Blade)
  const fanGroup = new THREE.Group();
  fanGroup.position.set(-0.78, 0.55, -0.1);

  const hubGeom = new THREE.CylinderGeometry(0.06, 0.06, 0.05, 16);
  const hubMat = new THREE.MeshStandardMaterial({ color: 0x0f172a, metalness: 0.8, roughness: 0.2 });
  const hub = new THREE.Mesh(hubGeom, hubMat);
  hub.rotation.z = Math.PI / 2;
  fanGroup.add(hub);

  const bladeMat = new THREE.MeshStandardMaterial({ color: 0x94a3b8, metalness: 0.5, roughness: 0.3 });
  for (let i = 0; i < 6; i++) {
    const angle = (i * Math.PI) / 3;
    const bladeGeom = new THREE.BoxGeometry(0.02, 0.22, 0.06);
    const blade = new THREE.Mesh(bladeGeom, bladeMat);
    blade.position.set(0, Math.sin(angle) * 0.12, Math.cos(angle) * 0.12);
    blade.rotation.x = angle + 0.3;
    fanGroup.add(blade);
  }
  threeScene.add(fanGroup);

  // Pressure Gauge Dial with Live Needle
  const gaugeDialGeom = new THREE.CylinderGeometry(0.14, 0.14, 0.04, 24);
  const gaugeDialMat = new THREE.MeshStandardMaterial({ color: 0xf8fafc, metalness: 0.2, roughness: 0.5 });
  const gauge = new THREE.Mesh(gaugeDialGeom, gaugeDialMat);
  gauge.rotation.x = Math.PI / 2;
  gauge.position.set(0.2, 0.9, 0.25);
  threeScene.add(gauge);

  // Brass Bezel Ring
  const bezelGeom = new THREE.TorusGeometry(0.14, 0.02, 12, 32);
  const bezelMat = new THREE.MeshStandardMaterial({ color: 0xd4af37, metalness: 0.9, roughness: 0.1 });
  const bezel = new THREE.Mesh(bezelGeom, bezelMat);
  bezel.position.set(0.2, 0.9, 0.27);
  threeScene.add(bezel);

  // Needle Indicator
  const needleGroup = new THREE.Group();
  needleGroup.position.set(0.2, 0.9, 0.28);
  const needleGeom = new THREE.BoxGeometry(0.015, 0.1, 0.01);
  const needleMat = new THREE.MeshBasicMaterial({ color: 0xdc2626 });
  const needle = new THREE.Mesh(needleGeom, needleMat);
  needle.position.y = 0.04;
  needleGroup.add(needle);
  threeScene.add(needleGroup);

  animComponents.rotatingGroup = fanGroup;
  animComponents.tankMesh = tank;
  animComponents.gaugeNeedle = needleGroup;
  animComponents.speed = 0.08;
}

// -----------------------------------------------------------------------------
// Live Telemetry & Thermal Fault Updates
// -----------------------------------------------------------------------------

window.updateMachineVisualization = function(machineId, obs, twin) {
  if (!obs) return;

  const rpmBadge = document.getElementById('threeSpindleRpm');

  // 1. Spindle / Motor / Wheel Rotation Speed
  if (typeof obs.rpm === 'number' && Number.isFinite(obs.rpm)) {
    animComponents.speed = Math.min(0.5, (obs.rpm / 60) * (2 * Math.PI) / 60);
    if (rpmBadge) rpmBadge.textContent = `${obs.rpm.toFixed(0)} RPM`;
  } else if (typeof obs.duty_pct === 'number') {
    animComponents.speed = (obs.duty_pct / 100) * 0.15;
    if (rpmBadge) rpmBadge.textContent = `${obs.duty_pct.toFixed(0)}% DUTY`;
  }

  // 2. Temperature & Fault Glow Highlighting
  if (animComponents.hotMesh && obs.process_temp_k) {
    const tempK = obs.process_temp_k;
    const warning = twin && twin.forecast && twin.forecast.warning;
    const anomaly = twin && twin.residual && twin.residual.state === "ANOMALY";

    if (tempK > 316.0 || warning === "OVERTEMP") {
      // Glow hot orange/red
      animComponents.hotMesh.material.emissive.setHex(0xff3300);
      animComponents.hotMesh.material.emissiveIntensity = 0.75;
    } else if (anomaly) {
      // Flashing alert purple/magenta
      animComponents.hotMesh.material.emissive.setHex(0x9333ea);
      animComponents.hotMesh.material.emissiveIntensity = 0.6;
    } else if (tempK > 313.0) {
      // Warm amber
      animComponents.hotMesh.material.emissive.setHex(0xf59e0b);
      animComponents.hotMesh.material.emissiveIntensity = 0.35;
    } else {
      // Normal operating temperature
      animComponents.hotMesh.material.emissive.setHex(0x000000);
      animComponents.hotMesh.material.emissiveIntensity = 0.0;
    }
  }

  // 3. Compressor Pressure Gauge & Tank State
  if (animComponents.gaugeNeedle && typeof obs.pressure_bar === 'number') {
    const p = obs.pressure_bar;
    // Map 0 - 10 bar to angle (-135 deg to +135 deg)
    const angle = (p / 10.0) * (Math.PI * 1.5) - (Math.PI * 0.75);
    animComponents.gaugeNeedle.rotation.z = -angle;

    if (rpmBadge) rpmBadge.textContent = `${p.toFixed(2)} BAR`;

    if (animComponents.tankMesh) {
      if (p < 6.0) {
        // Critical low pressure (common-cause state)
        animComponents.tankMesh.material.emissive.setHex(0xef4444);
        animComponents.tankMesh.material.emissiveIntensity = 0.5;
      } else {
        animComponents.tankMesh.material.emissive.setHex(0x000000);
        animComponents.tankMesh.material.emissiveIntensity = 0.0;
      }
    }
  }

  // 4. Bar Saw Blade Wear Tinting
  if (animComponents.bladeMesh && typeof obs.blade_wear_pct === 'number') {
    const wear = obs.blade_wear_pct;
    if (wear > 75.0) {
      animComponents.bladeMesh.material.emissive.setHex(0xef4444);
      animComponents.bladeMesh.material.emissiveIntensity = 0.6;
    } else if (wear > 40.0) {
      animComponents.bladeMesh.material.emissive.setHex(0xd97706);
      animComponents.bladeMesh.material.emissiveIntensity = 0.3;
    } else {
      animComponents.bladeMesh.material.emissive.setHex(0x000000);
      animComponents.bladeMesh.material.emissiveIntensity = 0.0;
    }
  }
};

// Backward compatibility alias for earlier calls
window.updateSpindleSpeed = function(rpm) {
  if (currentMachineId && typeof state !== 'undefined' && state.obs) {
    window.updateMachineVisualization(currentMachineId, state.obs[currentMachineId], state.twin ? state.twin[currentMachineId] : null);
  } else if (typeof rpm === 'number') {
    animComponents.speed = (rpm / 60) * (2 * Math.PI) / 60;
  }
};

window.resetThreeView = function() {
  if (threeCamera && orbitControls) {
    threeCamera.position.set(2.5, 2.0, 3.5);
    orbitControls.target.set(0, 0.35, 0);
    orbitControls.update();
  }
};

window.toggleThreeAnimation = function() {
  animating = !animating;
  const btn = document.getElementById('btnToggleAnim');
  if (btn) btn.textContent = animating ? 'Pause' : 'Resume';
  return animating;
};

window.addEventListener('resize', () => {
  if (!threeCamera || !threeRenderer) return;
  const wrapper = document.getElementById('threeCanvasWrapper') || document.getElementById('detailView');
  if (!wrapper) return;
  const width = wrapper.clientWidth || 500;
  threeCamera.aspect = width / 360;
  threeCamera.updateProjectionMatrix();
  threeRenderer.setSize(width, 360);
});

window.initThreeView = initThreeView;
window.disposeThree = disposeThree;
