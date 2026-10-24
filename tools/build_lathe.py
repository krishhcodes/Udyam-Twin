"""Blender script to construct a realistic, industrial CNC Lathe (LATHE-01).

Features:
- Cast-iron slant bed and vibration-damped machine base
- Slanted sheet-metal enclosure with sliding door and inspection window
- Heavy headstock housing with precision spindle bore
- Dedicated rotating spindle shaft (LATHE_01_SPINDLE)
- 3-Jaw scroll chuck (LATHE_01_CHUCK) with 3 stepped hardened jaws
- Machined cylindrical bar stock workpiece (LATHE_01_WORKPIECE)
- 8-station octagonal CNC indexing tool turret with tool holders
- Tailstock with pneumatic quill and live center
- Operator CNC control pendant with LCD screen and red E-stop button
- 3-tier andon status light tower and live status indicator (LATHE_01_STATUS_INDICATOR)
- Laser-etched nameplate (LATHE_01_LABEL)
- Centered rotational pivots for wobble-free rotation in Three.js
"""

import math
import os
from pathlib import Path
import bpy
import mathutils

def clear_scene():
    """Clear existing objects and collections in Blender."""
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)
    for col in list(bpy.data.collections):
        bpy.data.collections.remove(col)

def create_pbr_material(name, base_color, metallic=0.0, roughness=0.5, transmission=0.0, alpha=1.0, emissive=(0, 0, 0), emissive_strength=1.0):
    """Create or update a Principled BSDF material."""
    mat = bpy.data.materials.get(name)
    if not mat:
        mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()

    node_out = nodes.new(type='ShaderNodeOutputMaterial')
    node_out.location = (300, 0)

    node_principled = nodes.new(type='ShaderNodeBsdfPrincipled')
    node_principled.location = (0, 0)

    # Base Color (RGBA)
    node_principled.inputs['Base Color'].default_value = (
        base_color[0], base_color[1], base_color[2], alpha
    )
    if 'Metallic' in node_principled.inputs:
        node_principled.inputs['Metallic'].default_value = metallic
    if 'Roughness' in node_principled.inputs:
        node_principled.inputs['Roughness'].default_value = roughness
    if transmission > 0:
        if 'Transmission Weight' in node_principled.inputs:
            node_principled.inputs['Transmission Weight'].default_value = transmission
        elif 'Transmission' in node_principled.inputs:
            node_principled.inputs['Transmission'].default_value = transmission
    if 'Alpha' in node_principled.inputs:
        node_principled.inputs['Alpha'].default_value = alpha

    # Emissive (Emission Color / Strength in Blender 4+)
    if any(c > 0 for c in emissive):
        if 'Emission Color' in node_principled.inputs:
            node_principled.inputs['Emission Color'].default_value = (emissive[0], emissive[1], emissive[2], 1.0)
            node_principled.inputs['Emission Strength'].default_value = emissive_strength
        elif 'Emission' in node_principled.inputs:
            node_principled.inputs['Emission'].default_value = (emissive[0], emissive[1], emissive[2], 1.0)
            if 'Emission Strength' in node_principled.inputs:
                node_principled.inputs['Emission Strength'].default_value = emissive_strength

    links.new(node_principled.outputs['BSDF'], node_out.inputs['Surface'])

    # Set blend mode for transparent materials
    if alpha < 1.0 or transmission > 0:
        mat.blend_method = 'BLEND'
    return mat

def create_mesh_box(name, size, location, material=None, parent=None, collection=None):
    """Create a box mesh with specified dimensions and location."""
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=location)
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

def create_mesh_cylinder(name, radius, depth, location, rotation=(0, 0, 0), material=None, parent=None, collection=None, vertices=32):
    """Create a cylinder mesh with specified radius and depth."""
    bpy.ops.mesh.primitive_cylinder_add(
        vertices=vertices,
        radius=radius,
        depth=depth,
        location=location,
        rotation=rotation
    )
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

def build_lathe():
    """Build the complete, detailed LATHE-01 digital twin model."""
    # 1. Create target collection
    col_name = "ASSET_LATHE_01"
    col = bpy.data.collections.get(col_name)
    if not col:
        col = bpy.data.collections.new(col_name)
        bpy.context.scene.collection.children.link(col)

    # 2. Materials definition
    mat_cast_iron = create_pbr_material("MAT_CastIron", (0.12, 0.14, 0.18), metallic=0.6, roughness=0.65)
    mat_enclosure = create_pbr_material("MAT_Enclosure", (0.16, 0.20, 0.26), metallic=0.7, roughness=0.4)
    mat_accent = create_pbr_material("MAT_Accent", (0.85, 0.47, 0.05), metallic=0.3, roughness=0.35)
    mat_machined_steel = create_pbr_material("MAT_MachinedSteel", (0.80, 0.82, 0.85), metallic=0.95, roughness=0.2)
    mat_dark_metal = create_pbr_material("MAT_DarkMetal", (0.08, 0.09, 0.11), metallic=0.8, roughness=0.5)
    mat_workpiece = create_pbr_material("MAT_Workpiece", (0.75, 0.77, 0.80), metallic=0.85, roughness=0.25)
    mat_glass = create_pbr_material("MAT_SafetyGlass", (0.1, 0.2, 0.3), roughness=0.1, transmission=0.8, alpha=0.5)
    mat_status_green = create_pbr_material("MAT_StatusGreen", (0.1, 0.8, 0.2), emissive=(0.1, 0.8, 0.2), emissive_strength=2.5)
    mat_estop = create_pbr_material("MAT_EstopRed", (0.9, 0.05, 0.05), metallic=0.1, roughness=0.3)
    mat_screen = create_pbr_material("MAT_CncScreen", (0.05, 0.12, 0.18), emissive=(0.05, 0.25, 0.35), emissive_strength=1.8)

    # Root Empty for Machine
    bpy.ops.object.empty_add(type='PLAIN_AXES', location=(0, 0, 0))
    root = bpy.context.active_object
    root.name = "LATHE_01"
    if root.name not in col.objects:
        col.objects.link(root)
        if root.name in bpy.context.scene.collection.objects:
            bpy.context.scene.collection.objects.unlink(root)

    # Lathe Spindle Center Axis: Height Z = 0.85, Y = 0.0, Axis along X
    # Machine dimensions: X: -1.1 to +1.0, Y: -0.55 to +0.55, Z: 0 to 1.6

    # 3. Heavy Machine Base (Cast Iron Foundation & Slant Bed support)
    base_main = create_mesh_box(
        "LATHE_01_BASE",
        size=(2.1, 1.1, 0.5),
        location=(0.0, 0.0, 0.25),
        material=mat_cast_iron,
        parent=root,
        collection=col
    )

    # Slant Bed casting (30-degree incline for chip disposal)
    slant_bed = create_mesh_box(
        "LATHE_01_SLANT_BED",
        size=(1.5, 0.7, 0.35),
        location=(0.15, -0.05, 0.65),
        material=mat_cast_iron,
        parent=root,
        collection=col
    )
    slant_bed.rotation_euler = (math.radians(-25), 0, 0)

    # Precision Hardened Steel Way Guides (X-axis rails)
    rail_1 = create_mesh_box(
        "LATHE_01_GUIDE_RAIL_1",
        size=(1.4, 0.05, 0.04),
        location=(0.15, -0.22, 0.73),
        material=mat_machined_steel,
        parent=root,
        collection=col
    )
    rail_2 = create_mesh_box(
        "LATHE_01_GUIDE_RAIL_2",
        size=(1.4, 0.05, 0.04),
        location=(0.15, 0.10, 0.60),
        material=mat_machined_steel,
        parent=root,
        collection=col
    )

    # 4. Sheet Metal Machine Enclosure with Open Front Machining Chamber
    # Rear enclosure wall
    enclosure_rear = create_mesh_box(
        "LATHE_01_ENCLOSURE_REAR",
        size=(2.15, 0.08, 0.95),
        location=(0.0, 0.48, 1.0),
        material=mat_enclosure,
        parent=root,
        collection=col
    )
    # Left enclosure wall (Headstock cover)
    enclosure_left = create_mesh_box(
        "LATHE_01_ENCLOSURE_LEFT",
        size=(0.08, 1.00, 0.95),
        location=(-1.04, 0.0, 1.0),
        material=mat_enclosure,
        parent=root,
        collection=col
    )
    # Right enclosure wall (Tailstock / Electrical cabinet)
    enclosure_right = create_mesh_box(
        "LATHE_01_ENCLOSURE_RIGHT",
        size=(0.08, 1.00, 0.95),
        location=(1.04, 0.0, 1.0),
        material=mat_enclosure,
        parent=root,
        collection=col
    )
    # Top canopy / slanted roof
    enclosure_roof = create_mesh_box(
        "LATHE_01_ENCLOSURE_ROOF",
        size=(2.15, 0.75, 0.06),
        location=(0.0, 0.15, 1.48),
        material=mat_enclosure,
        parent=root,
        collection=col
    )
    # Slanted front roof visor
    roof_visor = create_mesh_box(
        "LATHE_01_ROOF_VISOR",
        size=(2.15, 0.35, 0.04),
        location=(0.0, -0.32, 1.42),
        material=mat_accent,
        parent=root,
        collection=col
    )
    roof_visor.rotation_euler = (math.radians(-25), 0, 0)

    # Front lower chip splash guard & basin
    front_sill = create_mesh_box(
        "LATHE_01_FRONT_SILL",
        size=(2.15, 0.08, 0.28),
        location=(0.0, -0.48, 0.64),
        material=mat_enclosure,
        parent=root,
        collection=col
    )

    # Front Sliding Door with large clear polycarbonate inspection window
    door_frame = create_mesh_box(
        "LATHE_01_DOOR",
        size=(1.05, 0.05, 0.76),
        location=(0.05, -0.50, 1.05),
        material=mat_dark_metal,
        parent=root,
        collection=col
    )

    # Inspection Window (Transparent safety glass, allows looking into spindle chamber)
    inspection_window = create_mesh_box(
        "LATHE_01_WINDOW",
        size=(0.95, 0.02, 0.65),
        location=(0.05, -0.51, 1.05),
        material=mat_glass,
        parent=root,
        collection=col
    )

    # 5. Headstock & Main Spindle Assembly
    headstock_box = create_mesh_box(
        "LATHE_01_HEADSTOCK",
        size=(0.55, 0.85, 0.70),
        location=(-0.75, 0.0, 0.85),
        material=mat_cast_iron,
        parent=root,
        collection=col
    )

    # Spindle Bearing Cartridge Flange
    spindle_flange = create_mesh_cylinder(
        "LATHE_01_SPINDLE_FLANGE",
        radius=0.22,
        depth=0.06,
        location=(-0.45, 0.0, 0.85),
        rotation=(0, math.radians(90), 0),
        material=mat_machined_steel,
        parent=root,
        collection=col
    )

    # =========================================================================
    # ROTATING SPINDLE & CHUCK HIERARCHY
    # Pivot is centered at X = -0.42, Y = 0.0, Z = 0.85 (spindle center axis)
    # =========================================================================
    bpy.ops.object.empty_add(type='PLAIN_AXES', location=(-0.42, 0.0, 0.85))
    spindle_pivot = bpy.context.active_object
    spindle_pivot.name = "LATHE_01_SPINDLE"
    spindle_pivot.parent = root
    if spindle_pivot.name not in col.objects:
        col.objects.link(spindle_pivot)
        if spindle_pivot.name in bpy.context.scene.collection.objects:
            bpy.context.scene.collection.objects.unlink(spindle_pivot)

    # Spindle Nose Shaft (child of spindle_pivot, local location at 0)
    spindle_nose = create_mesh_cylinder(
        "LATHE_01_SPINDLE_NOSE",
        radius=0.14,
        depth=0.10,
        location=(-0.37, 0.0, 0.85),
        rotation=(0, math.radians(90), 0),
        material=mat_machined_steel,
        parent=spindle_pivot,
        collection=col
    )

    # 3-Jaw Scroll Chuck Body (child of spindle_pivot)
    chuck = create_mesh_cylinder(
        "LATHE_01_CHUCK",
        radius=0.20,
        depth=0.14,
        location=(-0.25, 0.0, 0.85),
        rotation=(0, math.radians(90), 0),
        material=mat_machined_steel,
        parent=spindle_pivot,
        collection=col
    )

    # Chuck Jaws (3 hardened stepped jaws at 0°, 120°, 240°)
    for i in range(3):
        angle = math.radians(i * 120)
        # Radial offset for jaw slot
        jy = math.sin(angle) * 0.12
        jz = math.cos(angle) * 0.12
        jaw = create_mesh_box(
            f"LATHE_01_JAW_{i+1}",
            size=(0.06, 0.045, 0.07),
            location=(-0.16, jy, 0.85 + jz),
            material=mat_dark_metal,
            parent=spindle_pivot,
            collection=col
        )
        jaw.rotation_euler = (angle, 0, 0)

    # Machined Workpiece (Cylindrical Bar Stock) clamped in chuck extending along X
    workpiece = create_mesh_cylinder(
        "LATHE_01_WORKPIECE",
        radius=0.045,
        depth=0.48,
        location=(0.06, 0.0, 0.85),
        rotation=(0, math.radians(90), 0),
        material=mat_workpiece,
        parent=spindle_pivot,
        collection=col
    )

    # 6. CNC Tool Turret Assembly (8-station indexing disc on cross slide)
    turret_cross_slide = create_mesh_box(
        "LATHE_01_CROSS_SLIDE",
        size=(0.32, 0.36, 0.12),
        location=(0.05, -0.22, 0.88),
        material=mat_cast_iron,
        parent=root,
        collection=col
    )

    turret_body = create_mesh_cylinder(
        "LATHE_01_TURRET",
        radius=0.16,
        depth=0.09,
        location=(0.05, -0.20, 0.98),
        rotation=(math.radians(90), 0, 0),
        vertices=8,  # Octagonal 8-station tool turret
        material=mat_dark_metal,
        parent=root,
        collection=col
    )

    # Active Carbide Tool Holder pointing towards workpiece
    tool_holder = create_mesh_box(
        "LATHE_01_TOOL_HOLDER",
        size=(0.04, 0.14, 0.04),
        location=(0.05, -0.09, 0.86),
        material=mat_machined_steel,
        parent=root,
        collection=col
    )

    # Golden TiN Carbide Insert
    mat_carbide = create_pbr_material("MAT_CarbideTiN", (0.9, 0.75, 0.2), metallic=0.9, roughness=0.15)
    tool_insert = create_mesh_box(
        "LATHE_01_CARBIDE_INSERT",
        size=(0.02, 0.02, 0.015),
        location=(0.05, -0.04, 0.85),
        material=mat_carbide,
        parent=root,
        collection=col
    )

    # 7. Heavy CNC Tailstock Assembly (support on right side)
    tailstock_body = create_mesh_box(
        "LATHE_01_TAILSTOCK",
        size=(0.38, 0.44, 0.45),
        location=(0.65, 0.0, 0.82),
        material=mat_cast_iron,
        parent=root,
        collection=col
    )

    # Pneumatic Quill (extends along X axis to hold workpiece)
    tailstock_quill = create_mesh_cylinder(
        "LATHE_01_TAILSTOCK_QUILL",
        radius=0.05,
        depth=0.18,
        location=(0.42, 0.0, 0.85),
        rotation=(0, math.radians(90), 0),
        material=mat_machined_steel,
        parent=root,
        collection=col
    )

    # Live Revolving Center 60° point
    live_center = create_mesh_cylinder(
        "LATHE_01_LIVE_CENTER",
        radius=0.035,
        depth=0.08,
        location=(0.32, 0.0, 0.85),
        rotation=(0, math.radians(90), 0),
        material=mat_machined_steel,
        parent=root,
        collection=col
    )

    # 8. CNC Operator Control Pendant
    pendant_arm = create_mesh_cylinder(
        "LATHE_01_PENDANT_ARM",
        radius=0.025,
        depth=0.45,
        location=(0.85, -0.55, 1.25),
        rotation=(math.radians(20), math.radians(15), 0),
        material=mat_dark_metal,
        parent=root,
        collection=col
    )

    pendant_box = create_mesh_box(
        "LATHE_01_CONTROL_PANEL",
        size=(0.35, 0.12, 0.48),
        location=(0.95, -0.58, 1.35),
        material=mat_enclosure,
        parent=root,
        collection=col
    )
    pendant_box.rotation_euler = (0, 0, math.radians(-15))

    # CNC LCD Screen
    screen = create_mesh_box(
        "LATHE_01_SCREEN",
        size=(0.28, 0.01, 0.22),
        location=(0.94, -0.63, 1.45),
        material=mat_screen,
        parent=pendant_box,
        collection=col
    )

    # Emergency Stop (E-Stop) Mushroom Button
    estop_base = create_mesh_cylinder(
        "LATHE_01_ESTOP_BASE",
        radius=0.025,
        depth=0.02,
        location=(0.94, -0.63, 1.22),
        rotation=(math.radians(90), 0, 0),
        material=mat_accent,
        parent=pendant_box,
        collection=col
    )
    estop_button = create_mesh_cylinder(
        "LATHE_01_ESTOP",
        radius=0.032,
        depth=0.025,
        location=(0.94, -0.65, 1.22),
        rotation=(math.radians(90), 0, 0),
        material=mat_estop,
        parent=pendant_box,
        collection=col
    )

    # 9. Andon 3-Tier Status Tower Light (Red, Amber, Green)
    andon_mast = create_mesh_cylinder(
        "LATHE_01_ANDON_MAST",
        radius=0.015,
        depth=0.28,
        location=(-0.85, -0.35, 1.62),
        material=mat_machined_steel,
        parent=root,
        collection=col
    )

    andon_green = create_mesh_cylinder(
        "LATHE_01_STATUS_INDICATOR",
        radius=0.03,
        depth=0.05,
        location=(-0.85, -0.35, 1.76),
        material=mat_status_green,
        parent=root,
        collection=col
    )

    mat_andon_amber = create_pbr_material("MAT_AndonAmber", (0.8, 0.5, 0.05), emissive=(0.8, 0.5, 0.05), emissive_strength=0.1)
    andon_amber = create_mesh_cylinder(
        "LATHE_01_ANDON_AMBER",
        radius=0.03,
        depth=0.05,
        location=(-0.85, -0.35, 1.82),
        material=mat_andon_amber,
        parent=root,
        collection=col
    )

    mat_andon_red = create_pbr_material("MAT_AndonRed", (0.8, 0.05, 0.05), emissive=(0.8, 0.05, 0.05), emissive_strength=0.1)
    andon_red = create_mesh_cylinder(
        "LATHE_01_ANDON_RED",
        radius=0.03,
        depth=0.05,
        location=(-0.85, -0.35, 1.88),
        material=mat_andon_red,
        parent=root,
        collection=col
    )

    # 10. Identification Nameplate ("LATHE-01")
    nameplate = create_mesh_box(
        "LATHE_01_LABEL",
        size=(0.32, 0.01, 0.08),
        location=(-0.45, -0.58, 1.35),
        material=mat_machined_steel,
        parent=root,
        collection=col
    )

    return root

def export_lathe(output_glb_path, output_blend_path=None):
    """Export the LATHE-01 hierarchy to GLB and save Blender file."""
    # Deselect all, select root and all descendants
    bpy.ops.object.select_all(action='DESELECT')
    root = bpy.data.objects.get("LATHE_01")
    if not root:
        raise ValueError("LATHE_01 root object not found!")

    def select_tree(obj):
        obj.select_set(True)
        for child in obj.children:
            select_tree(child)

    select_tree(root)
    bpy.context.view_layer.objects.active = root

    out_glb = Path(output_glb_path).resolve()
    out_glb.parent.mkdir(parents=True, exist_ok=True)

    print(f"Exporting GLB to: {out_glb}")
    bpy.ops.export_scene.gltf(
        filepath=str(out_glb),
        export_format='GLB',
        use_selection=True,
        export_apply=False,
        export_materials='EXPORT',
        export_cameras=False,
        export_lights=False,
    )

    if output_blend_path:
        out_blend = Path(output_blend_path).resolve()
        out_blend.parent.mkdir(parents=True, exist_ok=True)
        print(f"Saving .blend to: {out_blend}")
        bpy.ops.wm.save_as_mainfile(filepath=str(out_blend))

    return {
        "glb_path": str(out_glb),
        "glb_size_bytes": out_glb.stat().st_size if out_glb.exists() else 0,
        "blend_path": str(out_blend) if output_blend_path else None
    }

if __name__ == "__main__":
    clear_scene()
    build_lathe()
    res = export_lathe("assets/3d/lathe_01.glb", "assets/3d/lathe_01.blend")
    print("Build and export complete:", res)
