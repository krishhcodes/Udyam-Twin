// three_mill.js – Photorealistic 3D Digital Twin Visualizer
// Loads high-fidelity Blender GLB assets exported from udyam_factory.blend with seamless procedural fallbacks.
// Assets:
// 1. VMC-01: 3-Axis Vertical Machining Center (Spindle, BT40 Tool, Worktable, Coolant System, Enclosure)
// 2. LATHE-01: CNC Slant-Bed Lathe (Spindle, 3-Jaw Chuck, Bar Stock, 8-Tool Turret, Tailstock)
// 3. SAW-01: Industrial Metal Band Saw (Roller Conveyor, Vise, Cutting Bow, Moving Blade)
// 4. COMP-01: Shared Rotary Air Compressor (Receiver Vessel, Motor, Cooling Fan, Live Pressure Gauge)
// 5. FACTORY: Full Factory Scene (4 Stations, Safety Demarcation, Utility Air Header, Lighting)

let threeRenderer = null;
let threeScene = null;
let threeCamera = null;
let orbitControls = null;
let animationId = null;
let animating = true;
let currentMachineId = null;
let currentTemplate = null;
let currentModelSource = "loading";

// Dynamic animated components and telemetry bindings
let animComponents = {
  rotatingGroup: null,
  rotatingElements: [],
  rotationAxis: "y",
  speed: 0.02,
  hotMesh: null,
  coolantIndicator: null,
  gaugeNeedle: null,
  tankMesh: null,
  airInlet: null,
  bladeMesh: null,
  statusIndicator: null,
  allSpindles: [], // for full factory scene overview
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
  if (threeScene) {
    threeScene.traverse((child) => {
      if (child.isMesh) {
        if (child.geometry) child.geometry.dispose();
        if (child.material) {
          if (Array.isArray(child.material)) {
            child.material.forEach((m) => m && m.dispose && m.dispose());
          } else if (child.material.dispose) {
            child.material.dispose();
          }
        }
      }
    });
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
  currentModelSource = "none";
  animComponents = {
    rotatingGroup: null,
    rotatingElements: [],
    rotationAxis: "y",
    speed: 0.02,
    hotMesh: null,
    coolantIndicator: null,
    gaugeNeedle: null,
    tankMesh: null,
    airInlet: null,
    bladeMesh: null,
    statusIndicator: null,
    allSpindles: [],
  };
}

function updateModelSourceBadge(text, isGlb) {
  const badge = document.getElementById("threeModelBadge");
  if (badge) {
    badge.textContent = text;
    badge.style.color = isGlb ? "var(--status-ok, #22c55e)" : "var(--status-warn, #f59e0b)";
  }
}

function initThreeView(machineId) {
  disposeThree();

  const wrapper = document.getElementById("threeCanvasWrapper") || document.getElementById("detailView");
  if (!wrapper) return;

  if (typeof THREE === "undefined") {
    wrapper.innerHTML = '<div style="padding:40px; text-align:center; color:var(--text-muted); font-size:13px;">3D visualizer requires Three.js. (Offline/CDN fallback mode).</div>';
    return;
  }

  wrapper.innerHTML = "";

  const canvas = document.createElement("canvas");
  canvas.id = "threeCanvas";
  canvas.style.width = "100%";
  canvas.style.height = "360px";
  canvas.style.display = "block";
  canvas.style.borderRadius = "var(--radius-sm, 6px)";
  canvas.style.background = "#090d16";
  wrapper.appendChild(canvas);

  const width = wrapper.clientWidth || 500;
  const height = 360;

  threeRenderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
  threeRenderer.setSize(width, height);
  threeRenderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));

  threeScene = new THREE.Scene();
  threeCamera = new THREE.PerspectiveCamera(45, width / height, 0.1, 1000);

  // Default camera angle
  if (machineId === "FACTORY") {
    threeCamera.position.set(0.5, 7.5, 11.0);
  } else {
    threeCamera.position.set(2.4, 2.0, 3.2);
  }

  // Realistic Industrial Lighting
  const ambient = new THREE.AmbientLight(0xffffff, 0.75);
  threeScene.add(ambient);

  const sunKey = new THREE.DirectionalLight(0xfffaed, 0.95);
  sunKey.position.set(6, 12, 8);
  threeScene.add(sunKey);

  const fillCool = new THREE.DirectionalLight(0x4080ff, 0.45);
  fillCool.position.set(-8, -2, -6);
  threeScene.add(fillCool);

  // Ground Grid
  const gridHelper = new THREE.GridHelper(machineId === "FACTORY" ? 22 : 6, machineId === "FACTORY" ? 22 : 12, 0x3d4b64, 0x141a29);
  gridHelper.position.y = -0.01;
  threeScene.add(gridHelper);

  // Determine template and GLB file mapping
  let template = "cnc_mill";
  let glbFile = "vmc_01.glb";

  if (machineId === "FACTORY") {
    template = "factory_scene";
    glbFile = "factory_scene.glb";
  } else if (typeof state !== "undefined" && state.machines && state.machines[machineId]) {
    template = state.machines[machineId].template;
    if (template === "cnc_mill") glbFile = "vmc_01.glb";
    else if (template === "cnc_lathe") glbFile = "lathe_01.glb";
    else if (template === "bar_saw") glbFile = "saw_01.glb";
    else if (template === "air_compressor") glbFile = "comp_01.glb";
  } else if (machineId.includes("LATHE")) {
    template = "cnc_lathe";
    glbFile = "lathe_01.glb";
  } else if (machineId.includes("SAW")) {
    template = "bar_saw";
    glbFile = "saw_01.glb";
  } else if (machineId.includes("COMP")) {
    template = "air_compressor";
    glbFile = "comp_01.glb";
  }

  currentMachineId = machineId;
  currentTemplate = template;

  // Initialize OrbitControls
  orbitControls = new THREE.OrbitControls(threeCamera, threeRenderer.domElement);
  orbitControls.enableDamping = true;
  orbitControls.dampingFactor = 0.05;
  orbitControls.minDistance = 0.8;
  orbitControls.maxDistance = machineId === "FACTORY" ? 25 : 12;

  if (machineId === "FACTORY") {
    orbitControls.target.set(0.5, 0.8, 0);
  } else {
    orbitControls.target.set(0, 0.65, 0);
  }

  // Load Blender GLB Model with Procedural Fallback
  loadMachineModel(machineId, template, glbFile);

  // Animation Loop
  function animate() {
    animationId = requestAnimationFrame(animate);

    if (animating) {
      // 1. Single Machine Active Spindle / Fan / Blade Rotation
      if (animComponents.rotatingGroup) {
        const axis = animComponents.rotationAxis || "y";
        animComponents.rotatingGroup.rotation[axis] += animComponents.speed;
      }
      for (const elem of animComponents.rotatingElements) {
        elem.obj.rotation[elem.axis] += animComponents.speed;
      }

      // 2. Full Factory Scene Spindles (Animates all 4 stations concurrently)
      for (const s of animComponents.allSpindles) {
        s.obj.rotation[s.axis] += s.speed;
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
// GLTF Loader & Mesh Telemetry Node Binder
// -----------------------------------------------------------------------------

function loadMachineModel(machineId, template, glbFileName) {
  updateModelSourceBadge("Loading Blender 3D asset...", true);

  const fallbackFn = () => {
    updateModelSourceBadge("Procedural WebGL Fallback", false);
    buildProceduralFallback(template);
  };

  if (typeof THREE.GLTFLoader !== "undefined" && glbFileName) {
    const loader = new THREE.GLTFLoader();
    const url = `/assets/3d/${glbFileName}`;

    loader.load(
      url,
      (gltf) => {
        // Discard if user switched active selection during fetch
        if (currentMachineId !== machineId) return;

        const model = gltf.scene;
        threeScene.add(model);
        currentModelSource = "blender_glb";
        updateModelSourceBadge("Blender Photorealistic GLB", true);

        // Bind model hierarchy to telemetry components
        bindModelTelemetryNodes(machineId, template, model);

        // Re-apply latest telemetry if state is available
        if (typeof state !== "undefined" && state.obs) {
          const obs = machineId === "FACTORY" ? state.obs["VMC-01"] : state.obs[machineId];
          const twin = state.twin ? state.twin[machineId] : null;
          if (obs) window.updateMachineVisualization(machineId, obs, twin);
        }
      },
      undefined,
      (err) => {
        console.warn(`GLB load failed for ${url}, switching to procedural fallback:`, err);
        fallbackFn();
      }
    );
  } else {
    fallbackFn();
  }
}

function bindModelTelemetryNodes(machineId, template, model) {
  // Clear previous binds
  animComponents.rotatingElements = [];
  animComponents.allSpindles = [];

  if (template === "cnc_lathe") {
    const spindle = model.getObjectByName("LATHE_01_SPINDLE");
    if (spindle) {
      animComponents.rotatingGroup = spindle;
      animComponents.rotationAxis = "x";
    }
    animComponents.hotMesh = model.getObjectByName("LATHE_01_WORKPIECE") || model.getObjectByName("LATHE_01_CARBIDE_INSERT");
    animComponents.statusIndicator = model.getObjectByName("LATHE_01_STATUS_INDICATOR");
    animComponents.airInlet = model.getObjectByName("LATHE_01_AIR_INLET");
  } else if (template === "cnc_mill") {
    const spindle = model.getObjectByName("VMC_01_SPINDLE");
    if (spindle) {
      animComponents.rotatingGroup = spindle;
      animComponents.rotationAxis = "y";
    }
    animComponents.hotMesh = model.getObjectByName("VMC_01_ENDMILL") || model.getObjectByName("VMC_01_WORKPIECE");
    animComponents.coolantIndicator = model.getObjectByName("VMC_01_COOLANT_INDICATOR");
    animComponents.statusIndicator = model.getObjectByName("VMC_01_STATUS_INDICATOR");
    animComponents.airInlet = model.getObjectByName("VMC_01_AIR_INLET");
  } else if (template === "bar_saw") {
    const blade = model.getObjectByName("SAW_01_BLADE");
    const driveWheel = model.getObjectByName("SAW_01_DRIVE_WHEEL");
    if (blade) {
      animComponents.rotatingGroup = blade;
      animComponents.rotationAxis = "x";
    }
    if (driveWheel) {
      animComponents.rotatingElements.push({ obj: driveWheel, axis: "x" });
    }
    animComponents.bladeMesh = model.getObjectByName("SAW_01_BLADE_RIBBON");
    animComponents.statusIndicator = model.getObjectByName("SAW_01_STATUS_INDICATOR");
  } else if (template === "air_compressor") {
    const fan = model.getObjectByName("COMP_01_FAN");
    if (fan) {
      animComponents.rotatingGroup = fan;
      animComponents.rotationAxis = "x";
    }
    animComponents.tankMesh = model.getObjectByName("COMP_01_TANK");
    animComponents.gaugeNeedle = model.getObjectByName("COMP_01_GAUGE_NEEDLE");
    animComponents.statusIndicator = model.getObjectByName("COMP_01_STATUS_INDICATOR");
  } else if (template === "factory_scene") {
    // Multi-asset scene binds all 4 rotating components
    const vmcSpindle = model.getObjectByName("VMC_01_SPINDLE");
    const latheSpindle = model.getObjectByName("LATHE_01_SPINDLE");
    const sawBlade = model.getObjectByName("SAW_01_BLADE");
    const compFan = model.getObjectByName("COMP_01_FAN");

    if (vmcSpindle) animComponents.allSpindles.push({ obj: vmcSpindle, axis: "y", speed: 0.05 });
    if (latheSpindle) animComponents.allSpindles.push({ obj: latheSpindle, axis: "x", speed: 0.05 });
    if (sawBlade) animComponents.allSpindles.push({ obj: sawBlade, axis: "x", speed: 0.04 });
    if (compFan) animComponents.allSpindles.push({ obj: compFan, axis: "x", speed: 0.08 });

    animComponents.gaugeNeedle = model.getObjectByName("COMP_01_GAUGE_NEEDLE");
    animComponents.tankMesh = model.getObjectByName("COMP_01_TANK");
    animComponents.statusIndicator = model.getObjectByName("VMC_01_STATUS_INDICATOR");
  }
}

// -----------------------------------------------------------------------------
// Live Telemetry & Digital Twin State Binding
// -----------------------------------------------------------------------------

window.updateMachineVisualization = function (machineId, obs, twin) {
  if (!obs) return;

  const rpmBadge = document.getElementById("threeSpindleRpm");

  // 1. Spindle / Motor / Blade Speed Binding
  if (typeof obs.rpm === "number" && Number.isFinite(obs.rpm)) {
    animComponents.speed = Math.min(0.5, (obs.rpm / 60) * (2 * Math.PI) / 60);
    if (rpmBadge) rpmBadge.textContent = `${obs.rpm.toFixed(0)} RPM`;
  } else if (typeof obs.duty_pct === "number") {
    animComponents.speed = (obs.duty_pct / 100) * 0.15;
    if (rpmBadge) rpmBadge.textContent = `${obs.duty_pct.toFixed(0)}% DUTY`;
  }

  // 2. Machine Operational Status Light & Andon Indicator
  if (animComponents.statusIndicator && animComponents.statusIndicator.material) {
    const mat = animComponents.statusIndicator.material;
    let color = 0x22c55e; // Nominal Green
    let intensity = 2.0;

    const plc = obs.plc_state || "RUN";
    const risk = twin && twin.risk && twin.risk.rules;

    if (plc === "ALARM" || risk === "HIGH") {
      color = 0xef4444; // Alarm Red
      intensity = 3.0;
    } else if (plc === "WARN" || risk === "MEDIUM" || (typeof obs.derate_pct === "number" && obs.derate_pct > 0)) {
      color = 0xf59e0b; // Warning Amber
      intensity = 2.2;
    } else if (plc === "MAINT") {
      color = 0x3b82f6; // Maintenance Blue
      intensity = 2.0;
    }

    if (mat.emissive) {
      mat.emissive.setHex(color);
      mat.emissiveIntensity = intensity;
    }
  }

  // 3. Thermal State & Process Temperature Glow Highlighting
  if (animComponents.hotMesh && typeof obs.process_temp_k === "number" && animComponents.hotMesh.material) {
    const tempK = obs.process_temp_k;
    const warning = twin && twin.forecast && twin.forecast.warning;
    const anomaly = twin && twin.residual && twin.residual.state === "ANOMALY";
    const mat = animComponents.hotMesh.material;

    if (tempK > 316.0 || warning === "OVERTEMP") {
      mat.emissive.setHex(0xff3300); // Hot red-orange
      mat.emissiveIntensity = 0.8;
    } else if (anomaly) {
      mat.emissive.setHex(0x9333ea); // Purple anomaly marker
      mat.emissiveIntensity = 0.65;
    } else if (tempK > 313.0) {
      mat.emissive.setHex(0xf59e0b); // Elevated amber
      mat.emissiveIntensity = 0.35;
    } else {
      mat.emissive.setHex(0x000000);
      mat.emissiveIntensity = 0.0;
    }
  }

  // 4. VMC Coolant System Glow & Alarm Indication
  if (animComponents.coolantIndicator && animComponents.coolantIndicator.material) {
    const mat = animComponents.coolantIndicator.material;
    const isCoolantFault = obs.active_fault === "coolant_degradation" || (twin && twin.residual && twin.residual.state === "DRIFT");

    if (isCoolantFault) {
      mat.emissive.setHex(0xef4444); // Flash coolant warning
      mat.emissiveIntensity = 2.5;
    } else {
      mat.emissive.setHex(0x06b6d4); // Cool cyan flow
      mat.emissiveIntensity = 1.0;
    }
  }

  // 5. Compressor Pressure Gauge Needle & Tank State
  if (typeof obs.pressure_bar === "number") {
    const p = obs.pressure_bar;
    if (rpmBadge && (machineId.includes("COMP") || currentTemplate === "air_compressor")) {
      rpmBadge.textContent = `${p.toFixed(2)} BAR`;
    }

    // Drive live analog gauge needle
    if (animComponents.gaugeNeedle) {
      // Map 0 to 10 bar across -135° to +135°
      const angle = (p / 10.0) * (Math.PI * 1.5) - (Math.PI * 0.75);
      animComponents.gaugeNeedle.rotation.y = -angle; // in GLB exported orientation
    }

    // Tank highlight on low pressure
    if (animComponents.tankMesh && animComponents.tankMesh.material) {
      if (p < 6.0) {
        animComponents.tankMesh.material.emissive.setHex(0xef4444);
        animComponents.tankMesh.material.emissiveIntensity = 0.6;
      } else {
        animComponents.tankMesh.material.emissive.setHex(0x000000);
        animComponents.tankMesh.material.emissiveIntensity = 0.0;
      }
    }
  }

  // 6. Compressor Dependency Propagation to Downstream CNCs
  // If compressor drops below 6.0 bar, pneumatic clamping on VMC/Lathe is flagged
  if (animComponents.airInlet && animComponents.airInlet.material) {
    const compObs = typeof state !== "undefined" && state.obs && state.obs["COMP-01"];
    const compPressure = compObs ? compObs.pressure_bar : 7.2;

    if (compPressure < 6.0) {
      animComponents.airInlet.material.emissive.setHex(0xef4444); // Red pneumatic pressure drop warning
      animComponents.airInlet.material.emissiveIntensity = 1.8;
    } else {
      animComponents.airInlet.material.emissive.setHex(0x000000);
      animComponents.airInlet.material.emissiveIntensity = 0.0;
    }
  }

  // 7. Band Saw Blade Wear Tinting
  if (animComponents.bladeMesh && typeof obs.blade_wear_pct === "number" && animComponents.bladeMesh.material) {
    const wear = obs.blade_wear_pct;
    const mat = animComponents.bladeMesh.material;
    if (wear > 75.0) {
      mat.emissive.setHex(0xef4444);
      mat.emissiveIntensity = 0.7;
    } else if (wear > 40.0) {
      mat.emissive.setHex(0xd97706);
      mat.emissiveIntensity = 0.35;
    } else {
      mat.emissive.setHex(0x000000);
      mat.emissiveIntensity = 0.0;
    }
  }
};

// -----------------------------------------------------------------------------
// Procedural Fallback Builders (Preserved for offline/low-spec resilience)
// -----------------------------------------------------------------------------

function buildProceduralFallback(template) {
  if (template === "cnc_mill") buildMillFallback();
  else if (template === "cnc_lathe") buildLatheFallback();
  else if (template === "bar_saw") buildSawFallback();
  else if (template === "air_compressor") buildCompressorFallback();
  else buildMillFallback();
}

function buildMillFallback() {
  const baseGeom = new THREE.BoxGeometry(2.0, 0.5, 1.6);
  const baseMat = new THREE.MeshStandardMaterial({ color: 0x222733, metalness: 0.7, roughness: 0.3 });
  const base = new THREE.Mesh(baseGeom, baseMat);
  base.position.y = -0.25;
  threeScene.add(base);

  const colGeom = new THREE.BoxGeometry(0.65, 1.8, 0.7);
  const colMat = new THREE.MeshStandardMaterial({ color: 0x181d28, metalness: 0.6, roughness: 0.4 });
  const col = new THREE.Mesh(colGeom, colMat);
  col.position.set(0, 0.6, -0.45);
  threeScene.add(col);

  const headGeom = new THREE.BoxGeometry(0.55, 0.4, 0.7);
  const headMat = new THREE.MeshStandardMaterial({ color: 0x2c3545, metalness: 0.6, roughness: 0.35 });
  const head = new THREE.Mesh(headGeom, headMat);
  head.position.set(0, 1.05, -0.15);
  threeScene.add(head);

  const spindleGroup = new THREE.Group();
  spindleGroup.position.set(0, 0.85, 0.05);

  const chuckGeom = new THREE.CylinderGeometry(0.09, 0.09, 0.35, 32);
  const chuckMat = new THREE.MeshStandardMaterial({ color: 0xd0d5dd, metalness: 0.9, roughness: 0.1 });
  const chuck = new THREE.Mesh(chuckGeom, chuckMat);
  spindleGroup.add(chuck);

  const toolGeom = new THREE.CylinderGeometry(0.025, 0.025, 0.32, 16);
  const toolMat = new THREE.MeshStandardMaterial({ color: 0xd4af37, metalness: 0.85, roughness: 0.2 });
  const tool = new THREE.Mesh(toolGeom, toolMat);
  tool.position.y = -0.28;
  spindleGroup.add(tool);
  threeScene.add(spindleGroup);

  const pieceGeom = new THREE.BoxGeometry(0.5, 0.22, 0.5);
  const pieceMat = new THREE.MeshStandardMaterial({ color: 0x475467, metalness: 0.5, roughness: 0.5 });
  const piece = new THREE.Mesh(pieceGeom, pieceMat);
  piece.position.set(0, 0.11, 0.05);
  threeScene.add(piece);

  animComponents.rotatingGroup = spindleGroup;
  animComponents.rotationAxis = "y";
  animComponents.hotMesh = tool;
  animComponents.speed = 0.03;
}

function buildLatheFallback() {
  const bedGeom = new THREE.BoxGeometry(2.4, 0.5, 1.2);
  const bedMat = new THREE.MeshStandardMaterial({ color: 0x1f242e, metalness: 0.7, roughness: 0.3 });
  const bed = new THREE.Mesh(bedGeom, bedMat);
  bed.position.y = -0.25;
  threeScene.add(bed);

  const hsGeom = new THREE.BoxGeometry(0.7, 0.9, 0.9);
  const hsMat = new THREE.MeshStandardMaterial({ color: 0x2b3342, metalness: 0.6, roughness: 0.4 });
  const hs = new THREE.Mesh(hsGeom, hsMat);
  hs.position.set(-0.75, 0.35, 0);
  threeScene.add(hs);

  const chuckGroup = new THREE.Group();
  chuckGroup.position.set(-0.35, 0.35, 0);
  chuckGroup.rotation.y = Math.PI / 2;

  const chuckGeom = new THREE.CylinderGeometry(0.28, 0.28, 0.16, 32);
  const chuckMat = new THREE.MeshStandardMaterial({ color: 0xd0d5dd, metalness: 0.9, roughness: 0.1 });
  const chuck = new THREE.Mesh(chuckGeom, chuckMat);
  chuck.rotation.x = Math.PI / 2;
  chuckGroup.add(chuck);

  const stockGeom = new THREE.CylinderGeometry(0.12, 0.12, 0.9, 32);
  const stockMat = new THREE.MeshStandardMaterial({ color: 0x64748b, metalness: 0.7, roughness: 0.3 });
  const stock = new THREE.Mesh(stockGeom, stockMat);
  stock.position.y = -0.5;
  stock.rotation.x = Math.PI / 2;
  chuckGroup.add(stock);
  threeScene.add(chuckGroup);

  const turretGeom = new THREE.BoxGeometry(0.4, 0.5, 0.4);
  const turretMat = new THREE.MeshStandardMaterial({ color: 0x334155, metalness: 0.8, roughness: 0.2 });
  const turret = new THREE.Mesh(turretGeom, turretMat);
  turret.position.set(0.2, 0.35, 0.3);
  threeScene.add(turret);

  animComponents.rotatingGroup = chuckGroup;
  animComponents.rotationAxis = "z";
  animComponents.hotMesh = stock;
  animComponents.speed = 0.04;
}

function buildSawFallback() {
  const tableGeom = new THREE.BoxGeometry(2.0, 0.4, 0.8);
  const tableMat = new THREE.MeshStandardMaterial({ color: 0x1f242e, metalness: 0.6, roughness: 0.4 });
  const table = new THREE.Mesh(tableGeom, tableMat);
  table.position.y = -0.2;
  threeScene.add(table);

  const bladeGroup = new THREE.Group();
  bladeGroup.position.set(0, 0.45, 0);

  const wheelGeom = new THREE.CylinderGeometry(0.25, 0.25, 0.05, 32);
  const wheelMat = new THREE.MeshStandardMaterial({ color: 0xd4af37, metalness: 0.8, roughness: 0.2 });
  const wheel = new THREE.Mesh(wheelGeom, wheelMat);
  wheel.rotation.x = Math.PI / 2;
  bladeGroup.add(wheel);
  threeScene.add(bladeGroup);

  animComponents.rotatingGroup = bladeGroup;
  animComponents.rotationAxis = "z";
  animComponents.speed = 0.05;
}

function buildCompressorFallback() {
  const tankGeom = new THREE.CylinderGeometry(0.4, 0.4, 1.8, 32);
  const tankMat = new THREE.MeshStandardMaterial({ color: 0x1e293b, metalness: 0.8, roughness: 0.2 });
  const tank = new THREE.Mesh(tankGeom, tankMat);
  tank.rotation.z = Math.PI / 2;
  tank.position.y = 0.05;
  threeScene.add(tank);

  const fanGroup = new THREE.Group();
  fanGroup.position.set(-0.78, 0.55, -0.1);

  const hubGeom = new THREE.CylinderGeometry(0.06, 0.06, 0.05, 16);
  const hubMat = new THREE.MeshStandardMaterial({ color: 0x0f172a, metalness: 0.8, roughness: 0.2 });
  const hub = new THREE.Mesh(hubGeom, hubMat);
  hub.rotation.z = Math.PI / 2;
  fanGroup.add(hub);
  threeScene.add(fanGroup);

  animComponents.rotatingGroup = fanGroup;
  animComponents.rotationAxis = "x";
  animComponents.tankMesh = tank;
  animComponents.speed = 0.08;
}

// -----------------------------------------------------------------------------
// Interactive Controls & Global Window Exports
// -----------------------------------------------------------------------------

window.updateSpindleSpeed = function (rpm) {
  if (currentMachineId && typeof state !== "undefined" && state.obs) {
    window.updateMachineVisualization(currentMachineId, state.obs[currentMachineId], state.twin ? state.twin[currentMachineId] : null);
  } else if (typeof rpm === "number") {
    animComponents.speed = (rpm / 60) * (2 * Math.PI) / 60;
  }
};

window.resetThreeView = function () {
  if (threeCamera && orbitControls) {
    if (currentMachineId === "FACTORY") {
      threeCamera.position.set(0.5, 7.5, 11.0);
      orbitControls.target.set(0.5, 0.8, 0);
    } else {
      threeCamera.position.set(2.4, 2.0, 3.2);
      orbitControls.target.set(0, 0.65, 0);
    }
    orbitControls.update();
  }
};

window.toggleThreeAnimation = function () {
  animating = !animating;
  const btn = document.getElementById("btnToggleAnim");
  if (btn) btn.textContent = animating ? "Pause" : "Resume";
  return animating;
};

window.showFactoryOverview = function () {
  initThreeView("FACTORY");
  const title = document.getElementById("threeTitle");
  if (title) title.textContent = "3D Kinematic Twin — Complete Factory Floor";
};

window.addEventListener("resize", () => {
  if (!threeCamera || !threeRenderer) return;
  const wrapper = document.getElementById("threeCanvasWrapper") || document.getElementById("detailView");
  if (!wrapper) return;
  const width = wrapper.clientWidth || 500;
  threeCamera.aspect = width / 360;
  threeCamera.updateProjectionMatrix();
  threeRenderer.setSize(width, 360);
});

window.initThreeView = initThreeView;
window.disposeThree = disposeThree;
