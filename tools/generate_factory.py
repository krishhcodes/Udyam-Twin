"""UDYAM-TWIN: Blender Industrial Digital Twin Factory Generator.

Builds a high-quality, realistic industrial factory scene containing:
1. SAW-01: Industrial horizontal metal band saw (roller bed, clamping vise, cutting bow, moving blade)
2. LATHE-01: CNC slant-bed turning center (spindle, 3-jaw chuck, bar stock, 8-tool turret, tailstock)
3. VMC-01: 3-Axis Vertical Machining Center (spindle, BT40 tool, worktable, coolant system, enclosure)
4. COMP-01: Shared rotary screw air compressor (receiver tank, motor, cooling fan, dial pressure gauge)
5. Factory Environment: Concrete floor, safety demarcation zones, overhead air piping utility header, cable trays

Exports:
- Individual assets: saw_01.glb, lathe_01.glb, vmc_01.glb, comp_01.glb
- Full layout scene: factory_scene.glb
- Master Blender file: udyam_factory.blend

Can be executed inside Blender via BlendRelay MCP or headlessly via CLI:
blender --background --python tools/generate_factory.py
"""

import math
import os
import sys
from pathlib import Path
import bpy
import mathutils

ROOT = Path(__file__).resolve().parent.parent
ASSETS_3D = ROOT / "assets" / "3d"
ASSETS_3D.mkdir(parents=True, exist_ok=True)

# -----------------------------------------------------------------------------
# Material Factory & Helpers
# -----------------------------------------------------------------------------
def clear_all():
    """Clear all objects, meshes, materials, and collections."""
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)
    for col in list(bpy.data.collections):
        bpy.data.collections.remove(col)
    for mat in list(bpy.data.materials):
        bpy.data.materials.remove(mat)

def create_mat(name, base_color, metallic=0.0, roughness=0.5, transmission=0.0, alpha=1.0, emissive=(0, 0, 0), emissive_strength=1.0):
    """Create a physically-based material using Principled BSDF."""
    mat = bpy.data.materials.get(name)
    if not mat:
        mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()

    out = nodes.new(type='ShaderNodeOutputMaterial')
    bsdf = nodes.new(type='ShaderNodeBsdfPrincipled')
    links.new(bsdf.outputs['BSDF'], out.inputs['Surface'])

    bsdf.inputs['Base Color'].default_value = (base_color[0], base_color[1], base_color[2], alpha)
    if 'Metallic' in bsdf.inputs:
        bsdf.inputs['Metallic'].default_value = metallic
    if 'Roughness' in bsdf.inputs:
        bsdf.inputs['Roughness'].default_value = roughness
    if transmission > 0:
        if 'Transmission Weight' in bsdf.inputs:
            bsdf.inputs['Transmission Weight'].default_value = transmission
        elif 'Transmission' in bsdf.inputs:
            bsdf.inputs['Transmission'].default_value = transmission
    if 'Alpha' in bsdf.inputs:
        bsdf.inputs['Alpha'].default_value = alpha

    if any(c > 0 for c in emissive):
        if 'Emission Color' in bsdf.inputs:
            bsdf.inputs['Emission Color'].default_value = (emissive[0], emissive[1], emissive[2], 1.0)
            bsdf.inputs['Emission Strength'].default_value = emissive_strength
        elif 'Emission' in bsdf.inputs:
            bsdf.inputs['Emission'].default_value = (emissive[0], emissive[1], emissive[2], 1.0)
            if 'Emission Strength' in bsdf.inputs:
                bsdf.inputs['Emission Strength'].default_value = emissive_strength

    if alpha < 1.0 or transmission > 0:
        mat.blend_method = 'BLEND'
    return mat

def add_box(name, size, location, material=None, parent=None, collection=None, rotation=(0, 0, 0)):
    """Create and return a box mesh."""
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=location, rotation=rotation)
    obj = bpy.context.active_object
    obj.name = name
    obj.scale = mathutils.Vector(size)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    if material:
        obj.data.materials.append(material)
    if parent:
        obj.parent = parent
    if collection and obj.name not in collection.objects:
        collection.objects.link(obj)
        if obj.name in bpy.context.scene.collection.objects:
            bpy.context.scene.collection.objects.unlink(obj)
    return obj

def add_cylinder(name, radius, depth, location, rotation=(0, 0, 0), material=None, parent=None, collection=None, vertices=32):
    """Create and return a cylinder mesh."""
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices, radius=radius, depth=depth, location=location, rotation=rotation)
    obj = bpy.context.active_object
    obj.name = name
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    if material:
        obj.data.materials.append(material)
    if parent:
        obj.parent = parent
    if collection and obj.name not in collection.objects:
        collection.objects.link(obj)
        if obj.name in bpy.context.scene.collection.objects:
            bpy.context.scene.collection.objects.unlink(obj)
    return obj

def add_empty(name, location=(0, 0, 0), parent=None, collection=None):
    """Create a transform empty / group node."""
    bpy.ops.object.empty_add(type='PLAIN_AXES', location=location)
    obj = bpy.context.active_object
    obj.name = name
    if parent:
        obj.parent = parent
    if collection and obj.name not in collection.objects:
        collection.objects.link(obj)
        if obj.name in bpy.context.scene.collection.objects:
            bpy.context.scene.collection.objects.unlink(obj)
    return obj

# -----------------------------------------------------------------------------
# Shared Materials Palette (Graphite & Steel with Gold/Cyan/Amber accents)
# -----------------------------------------------------------------------------
class Materials:
    def __init__(self):
        self.cast_iron = create_mat("MAT_CastIron", (0.13, 0.15, 0.18), metallic=0.6, roughness=0.65)
        self.enclosure_slate = create_mat("MAT_EnclosureSlate", (0.18, 0.22, 0.28), metallic=0.7, roughness=0.35)
        self.enclosure_white = create_mat("MAT_EnclosureWhite", (0.85, 0.87, 0.90), metallic=0.4, roughness=0.3)
        self.accent_amber = create_mat("MAT_AccentAmber", (0.85, 0.48, 0.05), metallic=0.25, roughness=0.4)
        self.accent_cyan = create_mat("MAT_AccentCyan", (0.05, 0.65, 0.85), metallic=0.3, roughness=0.3)
        self.machined_steel = create_mat("MAT_MachinedSteel", (0.82, 0.84, 0.86), metallic=0.95, roughness=0.18)
        self.dark_steel = create_mat("MAT_DarkSteel", (0.09, 0.10, 0.12), metallic=0.85, roughness=0.4)
        self.bar_stock = create_mat("MAT_BarStock", (0.75, 0.77, 0.80), metallic=0.85, roughness=0.3)
        self.polycarbonate = create_mat("MAT_Polycarbonate", (0.12, 0.20, 0.28), roughness=0.1, transmission=0.85, alpha=0.45)
        self.screen_lcd = create_mat("MAT_ScreenLcd", (0.04, 0.10, 0.16), emissive=(0.05, 0.25, 0.35), emissive_strength=1.8)
        self.estop_red = create_mat("MAT_EstopRed", (0.90, 0.06, 0.06), metallic=0.1, roughness=0.3)
        self.status_green = create_mat("MAT_StatusGreen", (0.12, 0.85, 0.22), emissive=(0.12, 0.85, 0.22), emissive_strength=2.5)
        self.status_amber = create_mat("MAT_StatusAmber", (0.90, 0.55, 0.05), emissive=(0.90, 0.55, 0.05), emissive_strength=1.5)
        self.status_red = create_mat("MAT_StatusRed", (0.90, 0.08, 0.08), emissive=(0.90, 0.08, 0.08), emissive_strength=1.5)
        self.coolant_fluid = create_mat("MAT_CoolantFluid", (0.1, 0.7, 0.9), roughness=0.1, transmission=0.7, alpha=0.6, emissive=(0.05, 0.35, 0.5), emissive_strength=1.2)
        self.concrete_floor = create_mat("MAT_ConcreteFloor", (0.14, 0.16, 0.19), metallic=0.1, roughness=0.85)
        self.safety_stripe = create_mat("MAT_SafetyStripe", (0.90, 0.65, 0.05), metallic=0.1, roughness=0.6)
        self.utility_pipe = create_mat("MAT_UtilityPipe", (0.25, 0.55, 0.75), metallic=0.8, roughness=0.35)
        self.air_tank = create_mat("MAT_AirTank", (0.20, 0.45, 0.65), metallic=0.75, roughness=0.35)

# -----------------------------------------------------------------------------
# 1. ASSET: SAW-01 (Industrial Metal Band Saw)
# -----------------------------------------------------------------------------
def build_saw(mats, origin=(0, 0, 0), parent=None):
    """Build horizontal industrial metal band saw (SAW-01)."""
    col_name = "ASSET_SAW_01"
    col = bpy.data.collections.get(col_name) or bpy.data.collections.new(col_name)
    if col.name not in bpy.context.scene.collection.children:
        bpy.context.scene.collection.children.link(col)

    root = add_empty("SAW_01", location=origin, parent=parent, collection=col)

    # Base cabinet
    add_box("SAW_01_BASE", (1.6, 0.9, 0.55), (0.0, 0.0, 0.275), mats.cast_iron, root, col)

    # Roller Infeed Conveyor (4 steel rollers supporting raw bar stock)
    add_box("SAW_01_ROLLER_BED", (1.2, 0.45, 0.12), (-0.9, 0.0, 0.60), mats.dark_steel, root, col)
    for i in range(4):
        rx = -1.35 + i * 0.30
        add_cylinder(f"SAW_01_ROLLER_{i+1}", radius=0.035, depth=0.40, location=(rx, 0.0, 0.66), rotation=(math.radians(90), 0, 0), material=mats.machined_steel, parent=root, collection=col)

    # Hydraulic Clamping Vise
    add_box("SAW_01_VISE_FIXED", (0.10, 0.38, 0.18), (-0.18, 0.0, 0.68), mats.cast_iron, root, col)
    add_box("SAW_01_VISE_JAW", (0.08, 0.36, 0.16), (0.08, 0.0, 0.68), mats.machined_steel, root, col)

    # Raw Bar Stock Workpiece resting on rollers and clamped in vise
    add_cylinder("SAW_01_WORKPIECE", radius=0.07, depth=2.0, location=(-0.5, 0.0, 0.67), rotation=(0, math.radians(90), 0), material=mats.bar_stock, parent=root, collection=col)

    # Cutting Bow / Head (tilted cutting frame pivoted at rear)
    bow_group = add_empty("SAW_01_BOW", location=(0.0, 0.15, 0.85), parent=root, collection=col)
    bow_group.rotation_euler = (math.radians(-12), 0, 0)

    # Bow structural housing
    add_box("SAW_01_BOW_FRAME", (1.3, 0.22, 0.38), (0.1, 0.0, 0.12), mats.enclosure_slate, bow_group, col)
    add_box("SAW_01_BOW_TRIM", (1.31, 0.23, 0.04), (0.1, 0.0, 0.28), mats.accent_amber, bow_group, col)

    # Drive Wheel and Idler Wheel (large pulleys driving the band blade)
    add_cylinder("SAW_01_DRIVE_WHEEL", radius=0.18, depth=0.06, location=(-0.4, 0.02, 0.12), rotation=(0, math.radians(90), 0), material=mats.machined_steel, parent=bow_group, collection=col)
    add_cylinder("SAW_01_IDLER_WHEEL", radius=0.18, depth=0.06, location=(0.6, 0.02, 0.12), rotation=(0, math.radians(90), 0), material=mats.machined_steel, parent=bow_group, collection=col)

    # Continuous Band Saw Blade (pivoted moving element for rotation/animation)
    blade_pivot = add_empty("SAW_01_BLADE", location=(-0.4, 0.02, 0.12), parent=bow_group, collection=col)
    add_box("SAW_01_BLADE_RIBBON", (1.05, 0.008, 0.035), (0.5, 0.0, -0.16), mats.machined_steel, blade_pivot, col)

    # Drive Electric Motor & Gearbox on back of bow
    add_cylinder("SAW_01_MOTOR", radius=0.11, depth=0.28, location=(-0.4, 0.22, 0.12), rotation=(math.radians(90), 0, 0), material=mats.dark_steel, parent=bow_group, collection=col)

    # Hydraulic Downfeed Rate Cylinder
    add_cylinder("SAW_01_DOWNFEED_CYLINDER", radius=0.03, depth=0.35, location=(0.35, 0.20, 0.72), rotation=(math.radians(35), 0, 0), material=mats.machined_steel, parent=root, collection=col)

    # Operator Controls & Safety Andon
    panel = add_box("SAW_01_CONTROLS", (0.24, 0.15, 0.32), (0.7, -0.42, 0.95), mats.enclosure_slate, root, col)
    panel.rotation_euler = (0, 0, math.radians(-15))
    add_cylinder("SAW_01_ESTOP", radius=0.028, depth=0.02, location=(0.72, -0.48, 0.90), rotation=(math.radians(90), 0, 0), material=mats.estop_red, parent=panel, collection=col)

    # Status indicator light
    add_cylinder("SAW_01_STATUS_INDICATOR", radius=0.03, depth=0.05, location=(0.7, -0.42, 1.20), material=mats.status_green, parent=root, collection=col)

    # Identification Nameplate
    add_box("SAW_01_LABEL", (0.28, 0.01, 0.07), (0.0, -0.46, 0.50), mats.machined_steel, root, col)

    return root

# -----------------------------------------------------------------------------
# 2. ASSET: LATHE-01 (CNC Slant-Bed Turning Center)
# -----------------------------------------------------------------------------
def build_lathe(mats, origin=(0, 0, 0), parent=None):
    """Build CNC slant-bed turning center (LATHE-01)."""
    col_name = "ASSET_LATHE_01"
    col = bpy.data.collections.get(col_name) or bpy.data.collections.new(col_name)
    if col.name not in bpy.context.scene.collection.children:
        bpy.context.scene.collection.children.link(col)

    root = add_empty("LATHE_01", location=origin, parent=parent, collection=col)

    # Cast Iron Base
    add_box("LATHE_01_BASE", (2.1, 1.1, 0.5), (0.0, 0.0, 0.25), mats.cast_iron, root, col)

    # Slant Bed casting (30-degree incline)
    slant_bed = add_box("LATHE_01_SLANT_BED", (1.5, 0.7, 0.35), (0.15, -0.05, 0.65), mats.cast_iron, root, col)
    slant_bed.rotation_euler = (math.radians(-25), 0, 0)

    # Precision Guide Rails
    add_box("LATHE_01_GUIDE_RAIL_1", (1.4, 0.05, 0.04), (0.15, -0.22, 0.73), mats.machined_steel, root, col)
    add_box("LATHE_01_GUIDE_RAIL_2", (1.4, 0.05, 0.04), (0.15, 0.10, 0.60), mats.machined_steel, root, col)

    # Enclosure Walls (Open Front Machining Bay)
    add_box("LATHE_01_ENCLOSURE_REAR", (2.15, 0.08, 0.95), (0.0, 0.48, 1.0), mats.enclosure_slate, root, col)
    add_box("LATHE_01_ENCLOSURE_LEFT", (0.08, 1.00, 0.95), (-1.04, 0.0, 1.0), mats.enclosure_slate, root, col)
    add_box("LATHE_01_ENCLOSURE_RIGHT", (0.08, 1.00, 0.95), (1.04, 0.0, 1.0), mats.enclosure_slate, root, col)
    add_box("LATHE_01_ENCLOSURE_ROOF", (2.15, 0.75, 0.06), (0.0, 0.15, 1.48), mats.enclosure_slate, root, col)

    roof_visor = add_box("LATHE_01_ROOF_VISOR", (2.15, 0.35, 0.04), (0.0, -0.32, 1.42), mats.accent_amber, root, col)
    roof_visor.rotation_euler = (math.radians(-25), 0, 0)

    add_box("LATHE_01_FRONT_SILL", (2.15, 0.08, 0.28), (0.0, -0.48, 0.64), mats.enclosure_slate, root, col)
    add_box("LATHE_01_DOOR", (1.05, 0.05, 0.76), (0.05, -0.50, 1.05), mats.dark_steel, root, col)
    add_box("LATHE_01_WINDOW", (0.95, 0.02, 0.65), (0.05, -0.51, 1.05), mats.polycarbonate, root, col)

    # Headstock & Spindle Cartridge
    add_box("LATHE_01_HEADSTOCK", (0.55, 0.85, 0.70), (-0.75, 0.0, 0.85), mats.cast_iron, root, col)
    add_cylinder("LATHE_01_SPINDLE_FLANGE", radius=0.22, depth=0.06, location=(-0.45, 0.0, 0.85), rotation=(0, math.radians(90), 0), material=mats.machined_steel, parent=root, collection=col)

    # ROTATING SPINDLE & CHUCK
    spindle_pivot = add_empty("LATHE_01_SPINDLE", location=(-0.42, 0.0, 0.85), parent=root, collection=col)

    add_cylinder("LATHE_01_SPINDLE_NOSE", radius=0.14, depth=0.10, location=(-0.37, 0.0, 0.85), rotation=(0, math.radians(90), 0), material=mats.machined_steel, parent=spindle_pivot, collection=col)
    add_cylinder("LATHE_01_CHUCK", radius=0.20, depth=0.14, location=(-0.25, 0.0, 0.85), rotation=(0, math.radians(90), 0), material=mats.machined_steel, parent=spindle_pivot, collection=col)

    for i in range(3):
        angle = math.radians(i * 120)
        jy = math.sin(angle) * 0.12
        jz = math.cos(angle) * 0.12
        jaw = add_box(f"LATHE_01_JAW_{i+1}", (0.06, 0.045, 0.07), (-0.16, jy, 0.85 + jz), mats.dark_steel, spindle_pivot, col)
        jaw.rotation_euler = (angle, 0, 0)

    add_cylinder("LATHE_01_WORKPIECE", radius=0.045, depth=0.48, location=(0.06, 0.0, 0.85), rotation=(0, math.radians(90), 0), material=mats.bar_stock, parent=spindle_pivot, collection=col)

    # CNC Tool Turret
    add_box("LATHE_01_CROSS_SLIDE", (0.32, 0.36, 0.12), (0.05, -0.22, 0.88), mats.cast_iron, root, col)
    add_cylinder("LATHE_01_TURRET", radius=0.16, depth=0.09, location=(0.05, -0.20, 0.98), rotation=(math.radians(90), 0, 0), material=mats.dark_steel, parent=root, collection=col, vertices=8)
    add_box("LATHE_01_TOOL_HOLDER", (0.04, 0.14, 0.04), (0.05, -0.09, 0.86), mats.machined_steel, root, col)
    add_box("LATHE_01_CARBIDE_INSERT", (0.02, 0.02, 0.015), (0.05, -0.04, 0.85), mats.accent_amber, root, col)

    # Tailstock
    add_box("LATHE_01_TAILSTOCK", (0.38, 0.44, 0.45), (0.65, 0.0, 0.82), mats.cast_iron, root, col)
    add_cylinder("LATHE_01_TAILSTOCK_QUILL", radius=0.05, depth=0.18, location=(0.42, 0.0, 0.85), rotation=(0, math.radians(90), 0), material=mats.machined_steel, parent=root, collection=col)
    add_cylinder("LATHE_01_LIVE_CENTER", radius=0.035, depth=0.08, location=(0.32, 0.0, 0.85), rotation=(0, math.radians(90), 0), material=mats.machined_steel, parent=root, collection=col)

    # Control Pendant & E-Stop
    pendant = add_box("LATHE_01_CONTROL_PANEL", (0.35, 0.12, 0.48), (0.95, -0.58, 1.35), mats.enclosure_slate, root, col)
    pendant.rotation_euler = (0, 0, math.radians(-15))
    add_box("LATHE_01_SCREEN", (0.28, 0.01, 0.22), (0.94, -0.63, 1.45), mats.screen_lcd, pendant, col)
    add_cylinder("LATHE_01_ESTOP", radius=0.032, depth=0.025, location=(0.94, -0.65, 1.22), rotation=(math.radians(90), 0, 0), material=mats.estop_red, parent=pendant, collection=col)

    # Status Tower & Live Indicator
    add_cylinder("LATHE_01_ANDON_MAST", radius=0.015, depth=0.28, location=(-0.85, -0.35, 1.62), material=mats.machined_steel, parent=root, collection=col)
    add_cylinder("LATHE_01_STATUS_INDICATOR", radius=0.03, depth=0.05, location=(-0.85, -0.35, 1.76), material=mats.status_green, parent=root, collection=col)

    # Pneumatic Air Inlet Pipe (connected to shared compressor header)
    add_cylinder("LATHE_01_AIR_INLET", radius=0.02, depth=0.35, location=(-0.95, 0.48, 0.85), rotation=(math.radians(90), 0, 0), material=mats.utility_pipe, parent=root, collection=col)

    # Label
    add_box("LATHE_01_LABEL", (0.32, 0.01, 0.08), (-0.45, -0.58, 1.35), mats.machined_steel, root, col)

    return root

# -----------------------------------------------------------------------------
# 3. ASSET: VMC-01 (Vertical Machining Center - Hero Digital Twin)
# -----------------------------------------------------------------------------
def build_vmc(mats, origin=(0, 0, 0), parent=None):
    """Build 3-axis CNC Vertical Machining Center (VMC-01)."""
    col_name = "ASSET_VMC_01"
    col = bpy.data.collections.get(col_name) or bpy.data.collections.new(col_name)
    if col.name not in bpy.context.scene.collection.children:
        bpy.context.scene.collection.children.link(col)

    root = add_empty("VMC_01", location=origin, parent=parent, collection=col)

    # Cast Iron Base & Column
    add_box("VMC_01_BASE", (2.0, 1.8, 0.45), (0.0, 0.0, 0.225), mats.cast_iron, root, col)
    add_box("VMC_01_COLUMN", (1.1, 0.9, 1.8), (0.0, 0.45, 1.35), mats.cast_iron, root, col)

    # Enclosure Walls with Panoramic Front Doors
    add_box("VMC_01_ENCLOSURE_REAR", (2.1, 0.08, 1.9), (0.0, 0.92, 1.40), mats.enclosure_slate, root, col)
    add_box("VMC_01_ENCLOSURE_LEFT", (0.08, 1.84, 1.9), (-1.01, 0.0, 1.40), mats.enclosure_slate, root, col)
    add_box("VMC_01_ENCLOSURE_RIGHT", (0.08, 1.84, 1.9), (1.01, 0.0, 1.40), mats.enclosure_slate, root, col)
    add_box("VMC_01_ENCLOSURE_ROOF", (2.1, 1.84, 0.08), (0.0, 0.0, 2.36), mats.enclosure_slate, root, col)

    # Front Dual Sliding Doors with Large Inspection Windows
    add_box("VMC_01_DOOR_LEFT", (0.65, 0.05, 1.50), (-0.35, -0.92, 1.30), mats.dark_steel, root, col)
    add_box("VMC_01_WINDOW_LEFT", (0.55, 0.02, 1.10), (-0.35, -0.93, 1.35), mats.polycarbonate, root, col)

    add_box("VMC_01_DOOR_RIGHT", (0.65, 0.05, 1.50), (0.35, -0.92, 1.30), mats.dark_steel, root, col)
    add_box("VMC_01_WINDOW_RIGHT", (0.55, 0.02, 1.10), (0.35, -0.93, 1.35), mats.polycarbonate, root, col)

    # X/Y Milling Table
    add_box("VMC_01_SADDLE", (1.3, 0.9, 0.18), (0.0, -0.05, 0.54), mats.cast_iron, root, col)
    add_box("VMC_01_TABLE", (1.2, 0.55, 0.12), (0.0, -0.05, 0.69), mats.machined_steel, root, col)

    # Precision Vise & Workpiece block
    add_box("VMC_01_VISE", (0.32, 0.28, 0.14), (0.0, -0.05, 0.82), mats.dark_steel, root, col)
    add_box("VMC_01_WORKPIECE", (0.20, 0.18, 0.12), (0.0, -0.05, 0.95), mats.bar_stock, root, col)

    # Vertical Spindle Head Casting (Z-axis carriage)
    add_box("VMC_01_HEAD", (0.58, 0.70, 0.85), (0.0, 0.05, 1.65), mats.enclosure_slate, root, col)

    # Rotating Vertical Spindle Assembly
    spindle_pivot = add_empty("VMC_01_SPINDLE", location=(0.0, -0.05, 1.35), parent=root, collection=col)

    # Spindle cartridge nose (child of spindle_pivot)
    add_cylinder("VMC_01_SPINDLE_NOSE", radius=0.10, depth=0.18, location=(0.0, -0.05, 1.30), material=mats.machined_steel, parent=spindle_pivot, collection=col)

    # BT40 Tool Holder & Carbide Endmill
    add_cylinder("VMC_01_TOOL_HOLDER", radius=0.045, depth=0.14, location=(0.0, -0.05, 1.14), material=mats.dark_steel, parent=spindle_pivot, collection=col)
    add_cylinder("VMC_01_ENDMILL", radius=0.016, depth=0.12, location=(0.0, -0.05, 1.01), material=mats.accent_amber, parent=spindle_pivot, collection=col)

    # 16-Tool Automatic Carousel Magazine (ATC) on left side of head
    add_cylinder("VMC_01_TOOL_MAGAZINE", radius=0.32, depth=0.08, location=(-0.52, 0.05, 1.70), material=mats.dark_steel, parent=root, collection=col)

    # Coolant System: External sump tank, recirculation pump, and flood nozzles
    add_box("VMC_01_COOLANT_TANK", (0.65, 0.45, 0.40), (0.85, 0.55, 0.25), mats.enclosure_slate, root, col)
    add_cylinder("VMC_01_COOLANT_PUMP", radius=0.09, depth=0.25, location=(0.85, 0.55, 0.55), material=mats.dark_steel, parent=root, collection=col)

    # Flexible Coolant Nozzles pointing at endmill
    add_cylinder("VMC_01_COOLANT_PIPES", radius=0.012, depth=0.32, location=(0.08, -0.05, 1.15), rotation=(0, math.radians(-35), 0), material=mats.coolant_fluid, parent=root, collection=col)

    # Live Coolant / Thermal indicator light (updates on coolant degradation fault)
    add_cylinder("VMC_01_COOLANT_INDICATOR", radius=0.025, depth=0.04, location=(0.08, -0.05, 1.25), material=mats.coolant_fluid, parent=root, collection=col)

    # Control Console on Swing Arm
    pendant = add_box("VMC_01_CONTROL_PANEL", (0.42, 0.14, 0.55), (1.15, -0.85, 1.45), mats.enclosure_slate, root, col)
    pendant.rotation_euler = (0, 0, math.radians(-25))
    add_box("VMC_01_SCREEN", (0.34, 0.01, 0.26), (1.13, -0.91, 1.56), mats.screen_lcd, pendant, col)
    add_cylinder("VMC_01_ESTOP", radius=0.035, depth=0.025, location=(1.13, -0.91, 1.28), rotation=(math.radians(90), 0, 0), material=mats.estop_red, parent=pendant, collection=col)

    # Status Andon Tower
    add_cylinder("VMC_01_STATUS_INDICATOR", radius=0.035, depth=0.06, location=(-0.90, -0.80, 2.45), material=mats.status_green, parent=root, collection=col)

    # Pneumatic air inlet fitting for tool changer drawbar
    add_cylinder("VMC_01_AIR_INLET", radius=0.02, depth=0.40, location=(-0.95, 0.92, 1.20), rotation=(math.radians(90), 0, 0), material=mats.utility_pipe, parent=root, collection=col)

    # Machine Label
    add_box("VMC_01_LABEL", (0.35, 0.01, 0.09), (0.0, -0.93, 2.15), mats.machined_steel, root, col)

    return root

# -----------------------------------------------------------------------------
# 4. ASSET: COMP-01 (Shared Industrial Rotary Air Compressor)
# -----------------------------------------------------------------------------
def build_compressor(mats, origin=(0, 0, 0), parent=None):
    """Build shared industrial rotary screw compressor with pressure vessel (COMP-01)."""
    col_name = "ASSET_COMP_01"
    col = bpy.data.collections.get(col_name) or bpy.data.collections.new(col_name)
    if col.name not in bpy.context.scene.collection.children:
        bpy.context.scene.collection.children.link(col)

    root = add_empty("COMP-01", location=origin, parent=parent, collection=col)

    # Vibration Isolated Base Skid
    add_box("COMP_01_BASE", (1.8, 1.0, 0.15), (0.0, 0.0, 0.075), mats.cast_iron, root, col)

    # Horizontal Cylindrical Receiver Pressure Vessel
    tank = add_cylinder("COMP_01_TANK", radius=0.38, depth=1.45, location=(0.0, 0.0, 0.48), rotation=(0, math.radians(90), 0), material=mats.air_tank, parent=root, collection=col)

    # Dished Vessel Heads (Ends)
    add_cylinder("COMP_01_TANK_HEAD_LEFT", radius=0.36, depth=0.08, location=(-0.75, 0.0, 0.48), rotation=(0, math.radians(90), 0), material=mats.air_tank, parent=root, collection=col)
    add_cylinder("COMP_01_TANK_HEAD_RIGHT", radius=0.36, depth=0.08, location=(0.75, 0.0, 0.48), rotation=(0, math.radians(90), 0), material=mats.air_tank, parent=root, collection=col)

    # Platform Deck above tank
    add_box("COMP_01_DECK", (1.5, 0.85, 0.05), (0.0, 0.0, 0.90), mats.dark_steel, root, col)

    # Heavy Industrial Electric Motor
    add_cylinder("COMP_01_MOTOR", radius=0.18, depth=0.55, location=(-0.35, 0.0, 1.15), rotation=(0, math.radians(90), 0), material=mats.dark_steel, parent=root, collection=col)

    # Rotating Multi-Blade Cooling Fan (inside wire shroud)
    fan_pivot = add_empty("COMP_01_FAN", location=(-0.65, 0.0, 1.15), parent=root, collection=col)
    add_cylinder("COMP_01_FAN_HUB", radius=0.06, depth=0.05, location=(-0.65, 0.0, 1.15), rotation=(0, math.radians(90), 0), material=mats.accent_amber, parent=fan_pivot, collection=col)
    for i in range(6):
        angle = math.radians(i * 60)
        by = math.sin(angle) * 0.10
        bz = math.cos(angle) * 0.10
        blade = add_box(f"COMP_01_FAN_BLADE_{i+1}", (0.015, 0.08, 0.03), (-0.65, by, 1.15 + bz), mats.accent_amber, fan_pivot, col)
        blade.rotation_euler = (angle, 0, math.radians(20))

    # Rotary Screw Air End Pump
    add_box("COMP_01_AIR_END", (0.45, 0.42, 0.42), (0.25, 0.0, 1.12), mats.cast_iron, root, col)

    # Air Intake Filter Canister
    add_cylinder("COMP_01_AIR_FILTER", radius=0.12, depth=0.28, location=(0.25, 0.0, 1.48), material=mats.accent_amber, parent=root, collection=col)

    # LIVE ANALOG DIAL PRESSURE GAUGE
    gauge_body = add_cylinder("COMP_01_PRESSURE_GAUGE", radius=0.11, depth=0.06, location=(0.65, -0.32, 1.25), rotation=(math.radians(90), 0, 0), material=mats.machined_steel, parent=root, collection=col)
    add_cylinder("COMP_01_GAUGE_FACE", radius=0.095, depth=0.005, location=(0.65, -0.355, 1.25), rotation=(math.radians(90), 0, 0), material=mats.enclosure_white, parent=gauge_body, collection=col)

    # Rotating Gauge Needle (driven by obs.pressure_bar)
    needle_pivot = add_empty("COMP_01_GAUGE_NEEDLE", location=(0.65, -0.36, 1.25), parent=gauge_body, collection=col)
    add_box("COMP_01_NEEDLE_POINTER", (0.006, 0.002, 0.075), (0.65, -0.362, 1.285), mats.estop_red, needle_pivot, col)

    # Regulator & Safety Relief Valve
    add_cylinder("COMP_01_REGULATOR", radius=0.045, depth=0.14, location=(0.65, 0.15, 1.05), material=mats.machined_steel, parent=root, collection=col)
    add_cylinder("COMP_01_SAFETY_VALVE", radius=0.03, depth=0.10, location=(0.0, 0.0, 0.95), material=mats.accent_amber, parent=root, collection=col)

    # Main Supply Discharge Pipe
    add_cylinder("COMP_01_MAIN_PIPE", radius=0.035, depth=0.45, location=(0.65, 0.45, 1.10), rotation=(math.radians(90), 0, 0), material=mats.utility_pipe, parent=root, collection=col)

    # Control Box & Status Indicator Light
    ctrl = add_box("COMP_01_CONTROL_PANEL", (0.35, 0.10, 0.40), (0.1, -0.42, 1.15), mats.enclosure_slate, root, col)
    add_cylinder("COMP_01_STATUS_INDICATOR", radius=0.03, depth=0.04, location=(0.1, -0.42, 1.40), material=mats.status_green, parent=root, collection=col)

    # Label
    add_box("COMP_01_LABEL", (0.30, 0.01, 0.08), (0.0, -0.40, 0.48), mats.machined_steel, root, col)

    return root

# -----------------------------------------------------------------------------
# 5. FACTORY ENVIRONMENT & UTILITY PIPING (Shared Infrastructure)
# -----------------------------------------------------------------------------
def build_factory_environment(mats):
    """Build factory floor, safety markings, overhead compressed air piping header, and lighting."""
    col_name = "ENVIRONMENT_FACTORY"
    col = bpy.data.collections.get(col_name) or bpy.data.collections.new(col_name)
    if col.name not in bpy.context.scene.collection.children:
        bpy.context.scene.collection.children.link(col)

    env_root = add_empty("FACTORY_ENVIRONMENT", location=(0, 0, 0), collection=col)

    # Concrete Shop Floor Slab (18m x 10m)
    add_box("FACTORY_FLOOR", (18.0, 10.0, 0.10), (0.0, 0.0, -0.05), mats.concrete_floor, env_root, col)

    # Safety Walkway Stripes (Yellow demarcation bands)
    add_box("SAFETY_STRIPE_FRONT", (17.0, 0.12, 0.005), (0.0, -2.2, 0.003), mats.safety_stripe, env_root, col)
    add_box("SAFETY_STRIPE_AISLE_1", (0.12, 4.0, 0.005), (-2.7, 0.0, 0.003), mats.safety_stripe, env_root, col)
    add_box("SAFETY_STRIPE_AISLE_2", (0.12, 4.0, 0.005), (0.3, 0.0, 0.003), mats.safety_stripe, env_root, col)
    add_box("SAFETY_STRIPE_AISLE_3", (0.12, 4.0, 0.005), (3.3, 0.0, 0.003), mats.safety_stripe, env_root, col)

    # Shared High-Pressure Compressed Air Utility Header (Overhead blue piping)
    # Header spans from COMP-01 (+4.5) across VMC-01 (+1.8) and LATHE-01 (-1.2)
    add_cylinder("UTILITY_AIR_HEADER", radius=0.035, depth=8.0, location=(1.5, 1.8, 3.2), rotation=(0, math.radians(90), 0), material=mats.utility_pipe, parent=env_root, collection=col)

    # Drop pipe to COMP-01
    add_cylinder("UTILITY_DROP_COMP", radius=0.03, depth=1.8, location=(4.8, 1.8, 2.3), material=mats.utility_pipe, parent=env_root, collection=col)
    # Drop pipe to VMC-01
    add_cylinder("UTILITY_DROP_VMC", radius=0.025, depth=1.6, location=(1.8, 1.8, 2.4), material=mats.utility_pipe, parent=env_root, collection=col)
    # Drop pipe to LATHE-01
    add_cylinder("UTILITY_DROP_LATHE", radius=0.025, depth=1.8, location=(-1.2, 1.8, 2.3), material=mats.utility_pipe, parent=env_root, collection=col)

    # Studio Lighting Rig for Realistic Industrial Atmosphere
    # Key light (Gold / Warm daylight)
    bpy.ops.object.light_add(type='SUN', location=(6.0, -8.0, 9.0))
    sun = bpy.context.active_object
    sun.name = "LIGHT_SUN_KEY"
    sun.data.energy = 4.5
    sun.data.color = (1.0, 0.95, 0.88)
    sun.rotation_euler = (math.radians(48), math.radians(18), math.radians(-32))
    if sun.name not in col.objects:
        col.objects.link(sun)
        if sun.name in bpy.context.scene.collection.objects:
            bpy.context.scene.collection.objects.unlink(sun)

    # Fill light (Cool ambient factory ceiling light)
    bpy.ops.object.light_add(type='AREA', location=(0.0, 0.0, 5.0))
    area = bpy.context.active_object
    area.name = "LIGHT_AREA_CEILING"
    area.data.energy = 350.0
    area.data.size = 12.0
    area.data.color = (0.85, 0.92, 1.0)
    if area.name not in col.objects:
        col.objects.link(area)
        if area.name in bpy.context.scene.collection.objects:
            bpy.context.scene.collection.objects.unlink(area)

    # Master Overview Camera (Framing all 4 machines in production line order)
    bpy.ops.object.camera_add(location=(1.0, -7.5, 5.2))
    cam = bpy.context.active_object
    cam.name = "CAMERA_FACTORY_OVERVIEW"
    cam.rotation_euler = (math.radians(62), 0, math.radians(5))
    cam.data.lens = 35
    bpy.context.scene.camera = cam
    if cam.name not in col.objects:
        col.objects.link(cam)
        if cam.name in bpy.context.scene.collection.objects:
            bpy.context.scene.collection.objects.unlink(cam)

    return env_root

# -----------------------------------------------------------------------------
# Exporter Pipeline
# -----------------------------------------------------------------------------
def export_selection(objects, output_glb_path):
    """Export specified list of objects to GLB."""
    bpy.ops.object.select_all(action='DESELECT')
    def sel_tree(obj):
        obj.select_set(True)
        for child in obj.children:
            sel_tree(child)

    for o in objects:
        if o:
            sel_tree(o)

    out_p = Path(output_glb_path).resolve()
    out_p.parent.mkdir(parents=True, exist_ok=True)
    print(f"Exporting GLB: {out_p}")
    bpy.ops.export_scene.gltf(
        filepath=str(out_p),
        export_format='GLB',
        use_selection=True,
        export_apply=False,
        export_materials='EXPORT',
        export_cameras=False,
        export_lights=False,
    )
    return {
        "path": str(out_p),
        "size_bytes": out_p.stat().st_size if out_p.exists() else 0
    }

def generate_all():
    """Build all 4 machines and the factory environment, then export all GLBs and .blend."""
    print("Initializing scene and materials...")
    clear_all()
    mats = Materials()

    # Layout machine positions along production line:
    # SAW-01:   X = -4.2, Y = 0.0
    # LATHE-01: X = -1.2, Y = 0.0
    # VMC-01:   X = +1.8, Y = 0.0
    # COMP-01:  X = +4.8, Y = 1.0 (Utility station)
    print("Building SAW-01 (Industrial Bar Saw)...")
    saw_root = build_saw(mats, origin=(-4.2, 0.0, 0.0))

    print("Building LATHE-01 (CNC Lathe)...")
    lathe_root = build_lathe(mats, origin=(-1.2, 0.0, 0.0))

    print("Building VMC-01 (Vertical Machining Center)...")
    vmc_root = build_vmc(mats, origin=(1.8, 0.0, 0.0))

    print("Building COMP-01 (Rotary Screw Compressor)...")
    comp_root = build_compressor(mats, origin=(4.8, 1.0, 0.0))

    print("Building Factory Environment & Utility Piping...")
    env_root = build_factory_environment(mats)

    results = {}

    # 1. Export individual machine GLBs (centered at machine local coordinate space for detail inspector)
    # Temporarily move each machine to (0,0,0) to export clean local GLB for single-asset view
    print("Exporting individual asset GLBs...")

    # SAW-01
    saw_root.location = (0, 0, 0)
    results["saw_01"] = export_selection([saw_root], ASSETS_3D / "saw_01.glb")
    saw_root.location = (-4.2, 0.0, 0.0)

    # LATHE-01
    lathe_root.location = (0, 0, 0)
    results["lathe_01"] = export_selection([lathe_root], ASSETS_3D / "lathe_01.glb")
    lathe_root.location = (-1.2, 0.0, 0.0)

    # VMC-01
    vmc_root.location = (0, 0, 0)
    results["vmc_01"] = export_selection([vmc_root], ASSETS_3D / "vmc_01.glb")
    vmc_root.location = (1.8, 0.0, 0.0)

    # COMP-01
    comp_root.location = (0, 0, 0)
    results["comp_01"] = export_selection([comp_root], ASSETS_3D / "comp_01.glb")
    comp_root.location = (4.8, 1.0, 0.0)

    # 2. Export complete factory scene GLB (all machines in production line positions + floor + utilities)
    print("Exporting full factory scene GLB...")
    results["factory_scene"] = export_selection([saw_root, lathe_root, vmc_root, comp_root, env_root], ASSETS_3D / "factory_scene.glb")

    # 3. Save master Blender project file
    blend_path = ASSETS_3D / "udyam_factory.blend"
    print(f"Saving master Blender file: {blend_path}")
    bpy.ops.wm.save_as_mainfile(filepath=str(blend_path))
    results["blend"] = {
        "path": str(blend_path),
        "size_bytes": blend_path.stat().st_size if blend_path.exists() else 0
    }

    print("=" * 60)
    print("UDYAM-TWIN FACTORY 3D GENERATION COMPLETED SUCCESSFULLY:")
    for k, v in results.items():
        print(f" - {k}: {v['path']} ({v['size_bytes']:,} bytes)")
    print("=" * 60)
    return results

if __name__ == "__main__":
    generate_all()
