#!/usr/bin/env python3
"""
Blender 3D Model Generator
This script runs inside Blender to generate 3D models from plan.json data.
"""

import sys
import json
import argparse
import math
from pathlib import Path

# Import Blender modules
try:
    import bpy
    import bmesh
    from mathutils import Vector
except ImportError:
    print("Error: This script must be run from within Blender")
    print("Usage: blender --background --python blender_generator.py -- --plan <plan.json> --height <height> --out <output_dir>")
    sys.exit(1)


def clear_scene():
    """Clear all objects from the scene."""
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)


def setup_scene():
    """Set up scene for metric units and correct settings."""
    # Set units to metric
    bpy.context.scene.unit_settings.system = 'METRIC'
    bpy.context.scene.unit_settings.scale_length = 1.0
    
    # Set viewport shading for better visibility
    for area in bpy.context.screen.areas:
        if area.type == 'VIEW_3D':
            area.spaces[0].shading.type = 'SOLID'
    
    print("Scene configured for metric units")


def create_wall_mesh(wall_points, height, thickness=0.2):
    """
    Create a wall mesh from a polyline.
    
    Args:
        wall_points: List of [x, y] coordinates
        height: Wall height in meters
        thickness: Wall thickness in meters
    """
    if len(wall_points) < 2:
        return None
    
    # Convert to 3D coordinates
    points_3d = [Vector([p[0], p[1], 0]) for p in wall_points]
    
    # Create wall geometry by extruding along the path
    mesh = bpy.data.meshes.new(name="WallMesh")
    
    bm = bmesh.new()
    vert_map = {}

    def get_vert(coord):
        key = (round(coord.x, 6), round(coord.y, 6), round(coord.z, 6))
        if key not in vert_map:
            vert_map[key] = bm.verts.new(coord)
        return vert_map[key]
    
    # For each segment, create a rectangular face with shared vertices
    for i in range(len(points_3d) - 1):
        p1 = points_3d[i]
        p2 = points_3d[i + 1]
        
        # Calculate perpendicular direction for thickness
        direction = (p2 - p1).normalized()
        perpendicular = Vector([-direction.y, direction.x, 0])
        
        # Create base rectangle vertices
        v1 = p1 + perpendicular * (thickness / 2)
        v2 = p1 - perpendicular * (thickness / 2)
        v3 = p2 - perpendicular * (thickness / 2)
        v4 = p2 + perpendicular * (thickness / 2)
        
        verts = (get_vert(v1), get_vert(v2), get_vert(v3), get_vert(v4))
        
        # Create face if it does not already exist
        try:
            bm.faces.new(verts)
        except ValueError:
            pass  # face already exists
    
    bm.normal_update()
    
    # Extrude upward
    ret = bmesh.ops.extrude_face_region(bm, geom=[f for f in bm.faces])
    geom_extruded = ret['geom']
    
    # Move the extruded geometry upward by wall height
    bmesh.ops.translate(
        bm,
        vec=Vector((0, 0, height)),
        verts=[v for v in geom_extruded if isinstance(v, bmesh.types.BMVert)]
    )
    
    bm.to_mesh(mesh)
    bm.free()
    
    return mesh


def create_floor_ceiling(bounds, height):
    """Create floor and ceiling planes."""
    min_x, min_y = bounds['min']
    max_x, max_y = bounds['max']
    
    # Use exact bounds from the blueprint
    floor_width = max_x - min_x
    floor_depth = max_y - min_y
    
    # Floor
    bpy.ops.mesh.primitive_plane_add(size=1, location=(0, 0, 0))
    floor = bpy.context.active_object
    floor.name = "Floor"
    floor.scale = [floor_width, floor_depth, 1]
    floor.location = [(min_x + max_x) / 2, (min_y + max_y) / 2, 0]
    
    # Apply material
    mat_floor = bpy.data.materials.new(name="FloorMaterial")
    mat_floor.use_nodes = True
    mat_floor.node_tree.nodes.clear()
    bsdf = mat_floor.node_tree.nodes.new(type='ShaderNodeBsdfPrincipled')
    bsdf.inputs['Base Color'].default_value = (0.3, 0.3, 0.3, 1.0)
    output = mat_floor.node_tree.nodes.new(type='ShaderNodeOutputMaterial')
    mat_floor.node_tree.links.new(bsdf.outputs[0], output.inputs[0])
    floor.data.materials.append(mat_floor)
    
    # Ceiling
    bpy.ops.mesh.primitive_plane_add(size=1, location=(0, 0, height))
    ceiling = bpy.context.active_object
    ceiling.name = "Ceiling"
    ceiling.scale = [max_x - min_x, max_y - min_y, 1]
    ceiling.location = [(min_x + max_x) / 2, (min_y + max_y) / 2, height]
    
    # Apply material
    mat_ceiling = bpy.data.materials.new(name="CeilingMaterial")
    mat_ceiling.use_nodes = True
    mat_ceiling.node_tree.nodes.clear()
    bsdf = mat_ceiling.node_tree.nodes.new(type='ShaderNodeBsdfPrincipled')
    bsdf.inputs['Base Color'].default_value = (0.9, 0.9, 0.9, 1.0)
    output = mat_ceiling.node_tree.nodes.new(type='ShaderNodeOutputMaterial')
    mat_ceiling.node_tree.links.new(bsdf.outputs[0], output.inputs[0])
    ceiling.data.materials.append(mat_ceiling)


def create_stairs(stair_polygon, height, width=1.2):
    """Create stair geometry from a polygon."""
    if not stair_polygon or len(stair_polygon) < 3:
        print(f"Warning: Invalid stair polygon: {stair_polygon}")
        return
    
    # Calculate bounds of stair polygon
    min_x = min(p[0] for p in stair_polygon)
    max_x = max(p[0] for p in stair_polygon)
    min_y = min(p[1] for p in stair_polygon)
    max_y = max(p[1] for p in stair_polygon)
    
    stair_length = max_x - min_x if max_x > min_x else width
    stair_depth = max_y - min_y if max_y > min_y else width
    
    print(f"Creating stairs: bounds [{min_x}, {max_x}] x [{min_y}, {max_y}], length={stair_length}, depth={stair_depth}")
    
    # Create a mesh for stairs
    mesh = bpy.data.meshes.new("StairsMesh")
    stairs_obj = bpy.data.objects.new("Stairs", mesh)
    bpy.context.collection.objects.link(stairs_obj)
    
    # Create stepped geometry as a single mesh
    num_steps = max(3, int(height / 0.17))  # ~17cm per step
    step_height = height / num_steps
    step_length = stair_length / num_steps
    
    vertices = []
    faces = []
    
    # Create vertices for stepped geometry
    for i in range(num_steps + 1):
        # Bottom front edge of step
        x = min_x + step_length * i
        vertices.append([x, min_y, step_height * i])
        # Bottom back edge of step
        vertices.append([x, max_y, step_height * i])
        # Top front edge of step
        vertices.append([x, min_y, step_height * (i + 1)])
        # Top back edge of step
        vertices.append([x, max_y, step_height * (i + 1)])
    
    # Create faces for the steps
    for i in range(num_steps):
        base_idx = i * 4
        
        # Top surface of step
        faces.append([base_idx + 2, base_idx + 3, base_idx + 7, base_idx + 6])
        
        # Front vertical surface
        faces.append([base_idx, base_idx + 2, base_idx + 6, base_idx + 4])
        
        # Back vertical surface  
        faces.append([base_idx + 1, base_idx + 5, base_idx + 7, base_idx + 3])
        
        # Left side surface
        if i == 0:
            faces.append([base_idx, base_idx + 1, base_idx + 3, base_idx + 2])
        
        # Right side surface
        if i == num_steps - 1:
            faces.append([base_idx + 4, base_idx + 6, base_idx + 7, base_idx + 5])
    
    # Update mesh
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    
    # Add smooth shading
    bpy.context.view_layer.objects.active = stairs_obj
    stairs_obj.select_set(True)
    bpy.ops.object.shade_smooth()
    
    # Apply stair material
    mat_stair = bpy.data.materials.new(name="StairMaterial")
    mat_stair.use_nodes = True
    mat_stair.node_tree.nodes.clear()
    bsdf = mat_stair.node_tree.nodes.new(type='ShaderNodeBsdfPrincipled')
    bsdf.inputs['Base Color'].default_value = (0.6, 0.5, 0.4, 1.0)  # Brown color
    output = mat_stair.node_tree.nodes.new(type='ShaderNodeOutputMaterial')
    mat_stair.node_tree.links.new(bsdf.outputs[0], output.inputs[0])
    stairs_obj.data.materials.append(mat_stair)
    
    stairs_obj.select_set(False)
    print(f"Successfully created stairs with {num_steps} steps")


def create_opening_wall_cutout(wall_obj, center_x, center_y, width, depth, height, rotation_angle, base_height=0.0):
    """Create a rectangular opening cutout aligned to a wall."""
    bpy.ops.mesh.primitive_cube_add(size=1, location=(center_x, center_y, base_height + height / 2))
    cutter = bpy.context.active_object
    cutter.name = "OpeningCutter"
    cutter.scale = [width / 2, depth / 2, height / 2]
    cutter.rotation_euler = (0, 0, rotation_angle)
    
    bpy.context.view_layer.objects.active = wall_obj
    wall_obj.select_set(True)
    cutter.select_set(True)
    try:
        bpy.ops.object.modifier_add(type='BOOLEAN')
        mod = wall_obj.modifiers[-1]
        mod.operation = 'DIFFERENCE'
        mod.object = cutter
        bpy.ops.object.modifier_apply(modifier=mod.name)
    except Exception as e:
        print(f"Warning: failed to apply boolean opening: {e}")
    finally:
        if cutter.name in bpy.data.objects:
            bpy.data.objects.remove(cutter, do_unlink=True)
        wall_obj.select_set(False)


def object_is_near_point(obj, x, y, tolerance=0.5):
    """Check whether a point lies within a wall object's bounding box plus tolerance."""
    bbox = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
    xs = [v.x for v in bbox]
    ys = [v.y for v in bbox]
    return (min(xs) - tolerance) <= x <= (max(xs) + tolerance) and (min(ys) - tolerance) <= y <= (max(ys) + tolerance)


def create_door_opening(wall_obj, door_data, wall_thickness, door_height=2.1):
    """Create a door opening using a boolean cutout."""
    x1 = door_data.get('x1', 0.0)
    y1 = door_data.get('y1', 0.0)
    x2 = door_data.get('x2', x1 + 0.9)
    y2 = door_data.get('y2', y1)
    width = max(abs(x2 - x1), 0.9)
    depth = wall_thickness * 1.5
    center_x = (x1 + x2) / 2
    center_y = (y1 + y2) / 2
    angle = math.atan2(y2 - y1, x2 - x1)

    create_opening_wall_cutout(
        wall_obj,
        center_x,
        center_y,
        width,
        depth,
        door_height,
        rotation_angle=angle,
        base_height=0.0
    )


def set_node_input(node, name, value):
    if name in node.inputs:
        node.inputs[name].default_value = value
        return True
    for inp in node.inputs:
        if inp.name.lower() == name.lower():
            inp.default_value = value
            return True
    print(f"Warning: material input '{name}' not found on {node.type}")
    return False


def create_material_glass(name="GlassMaterial"):
    if name in bpy.data.materials:
        return bpy.data.materials[name]

    mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    nodes.clear()

    bsdf = nodes.new(type='ShaderNodeBsdfPrincipled')
    set_node_input(bsdf, 'Base Color', (0.7, 0.85, 0.95, 1.0))
    set_node_input(bsdf, 'Transmission', 0.85)
    set_node_input(bsdf, 'Roughness', 0.08)
    set_node_input(bsdf, 'IOR', 1.45)
    set_node_input(bsdf, 'Specular', 0.7)

    output = nodes.new(type='ShaderNodeOutputMaterial')
    mat.node_tree.links.new(bsdf.outputs[0], output.inputs[0])
    if hasattr(mat, 'blend_method'):
        mat.blend_method = 'BLEND'
    if hasattr(mat, 'shadow_method'):
        mat.shadow_method = 'NONE'
    return mat


def create_material_frame(name="FrameMaterial"):
    if name in bpy.data.materials:
        return bpy.data.materials[name]

    mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    nodes.clear()

    bsdf = nodes.new(type='ShaderNodeBsdfPrincipled')
    set_node_input(bsdf, 'Base Color', (0.2, 0.18, 0.15, 1.0))
    set_node_input(bsdf, 'Roughness', 0.35)
    set_node_input(bsdf, 'Specular', 0.4)

    output = nodes.new(type='ShaderNodeOutputMaterial')
    mat.node_tree.links.new(bsdf.outputs[0], output.inputs[0])
    return mat


def transform_local_to_world(cx, cy, dx, dy, angle):
    """Convert local window coordinates to world coordinates."""
    x = cx + math.cos(angle) * dx - math.sin(angle) * dy
    y = cy + math.sin(angle) * dx + math.cos(angle) * dy
    return x, y


def create_window_glass(center_x, center_y, width, depth, height, angle, base_height):
    """Create a glass pane for a window opening."""
    inset = max(depth * 0.35, 0.02)
    plane_x, plane_y = transform_local_to_world(center_x, center_y, 0, -inset, angle)
    bpy.ops.mesh.primitive_plane_add(size=1, location=(plane_x, plane_y, base_height + height / 2), rotation=(0, 0, angle))
    glass = bpy.context.active_object
    glass.name = "WindowGlass"
    glass.scale = [width / 2, height / 2, 1]
    glass.data.materials.append(create_material_glass())
    return glass


def create_window_frame(center_x, center_y, width, depth, height, angle, base_height, frame_thickness=0.06):
    """Create a simple window frame around the opening."""
    frame_depth = max(depth * 0.28, 0.04)
    frame_mat = create_material_frame()

    def add_frame_segment(dx, dy, sz_x, sz_y, sz_z, z_offset):
        world_x, world_y = transform_local_to_world(center_x, center_y, dx, dy, angle)
        bpy.ops.mesh.primitive_cube_add(size=1, location=(world_x, world_y, base_height + z_offset), rotation=(0, 0, angle))
        segment = bpy.context.active_object
        segment.scale = [sz_x / 2, sz_y / 2, sz_z / 2]
        segment.data.materials.append(frame_mat)
        return segment

    half_w = width / 2
    half_h = height / 2
    half_d = frame_depth / 2
    frame_height = height + frame_thickness

    # Left and right vertical posts
    add_frame_segment(-half_w + frame_thickness / 2, 0, frame_thickness, frame_depth, frame_height, half_h)
    add_frame_segment(half_w - frame_thickness / 2, 0, frame_thickness, frame_depth, frame_height, half_h)

    # Top and bottom rails
    add_frame_segment(0, 0, width + frame_thickness * 2, frame_depth, frame_thickness, height + frame_thickness / 2)
    add_frame_segment(0, 0, width + frame_thickness * 2, frame_depth, frame_thickness, 0 - frame_thickness / 2)


def create_window_opening(wall_obj, window_data, wall_thickness, window_height=1.2, sill_height=1.0):
    """Create a window opening using a boolean cutout."""
    x1 = window_data.get('x1', 0.0)
    y1 = window_data.get('y1', 0.0)
    x2 = window_data.get('x2', x1 + 1.2)
    y2 = window_data.get('y2', y1)
    width = max(abs(x2 - x1), 1.2)
    depth = wall_thickness * 1.5
    center_x = (x1 + x2) / 2
    center_y = (y1 + y2) / 2
    angle = math.atan2(y2 - y1, x2 - x1)

    create_opening_wall_cutout(
        wall_obj,
        center_x,
        center_y,
        width,
        depth,
        window_height,
        rotation_angle=angle,
        base_height=sill_height
    )

    create_window_glass(center_x, center_y, width, depth, window_height, angle, sill_height)
    create_window_frame(center_x, center_y, width, depth, window_height, angle, sill_height)


def create_furniture(polygon, height=1.0):
    """Create simple furniture placeholder."""
    if not polygon or len(polygon) < 3:
        return None
    
    bm = bmesh.new()
    
    # Create base vertices
    for point in polygon:
        bm.verts.new(Vector([point[0], point[1], 0]))
    
    # Create face
    bm.faces.new(bm.verts)
    
    # Extrude upward
    bmesh.ops.extrude_face_region(bm, geom=bm.faces[:])
    ret = bmesh.ops.extrude_face_region(bm, geom=bm.faces[:])
    geom_extruded = ret['geom']
    bmesh.ops.translate(
        bm,
        vec=Vector((0, 0, height)),
        verts=[v for v in geom_extruded if isinstance(v, bmesh.types.BMVert)]
    )
    
    mesh = bpy.data.meshes.new(name="FurnitureMesh")
    bm.to_mesh(mesh)
    bm.free()
    
    return mesh


def generate_model(plan_json_path, height, output_dir, wall_thickness=0.2, stair_width=1.2, furniture_enabled=True, map_path=None, door_height=None, door_width=1.0):
    """Generate 3D model from plan data."""
    
    # Read plan data
    print(f"Loading plan data from {plan_json_path}")
    with open(plan_json_path, 'r') as f:
        plan_data = json.load(f)
    
    # Set defaults based on height
    if door_height is None:
        door_height = height * 0.85  # 85% of building height
    
    walls = plan_data.get('walls', [])
    doors = plan_data.get('doors', [])
    windows = plan_data.get('windows', [])
    stairs = plan_data.get('stairs', [])
    furniture = plan_data.get('furniture', [])
    bounds = plan_data.get('bounds', {'min': [0, 0], 'max': [10, 10]})
    
    print(f"Generating model with {len(walls)} walls, {len(doors)} doors, {len(windows)} windows, {len(stairs)} stairs, {len(furniture)} furniture")
    print(f"Parameters: wall_thickness={wall_thickness}m, door_height={door_height}m, door_width={door_width}m, stair_width={stair_width}m")
    
    # Clear scene
    clear_scene()
    setup_scene()
    
    # Create wall meshes
    wall_objects = []
    for i, wall_points in enumerate(walls):
        wall_mesh = create_wall_mesh(wall_points, height, wall_thickness)
        if wall_mesh:
            wall_obj = bpy.data.objects.new(f"Wall_{i}", wall_mesh)
            bpy.context.collection.objects.link(wall_obj)
            wall_objects.append(wall_obj)
            
            # Apply material
            mat_wall = bpy.data.materials.new(name="WallMaterial")
            mat_wall.use_nodes = True
            mat_wall.node_tree.nodes.clear()
            bsdf = mat_wall.node_tree.nodes.new(type='ShaderNodeBsdfPrincipled')
            bsdf.inputs['Base Color'].default_value = (0.8, 0.8, 0.8, 1.0)
            output = mat_wall.node_tree.nodes.new(type='ShaderNodeOutputMaterial')
            mat_wall.node_tree.links.new(bsdf.outputs[0], output.inputs[0])
            wall_obj.data.materials.append(mat_wall)

    # Create door openings only on nearby wall objects
    for door in doors:
        center_x = (door.get('x1', 0.0) + door.get('x2', door.get('x1', 0.0) + 0.9)) / 2
        center_y = (door.get('y1', 0.0) + door.get('y2', door.get('y1', 0.0))) / 2
        for wall_obj in wall_objects:
            if object_is_near_point(wall_obj, center_x, center_y, tolerance=max(wall_thickness, 0.5)):
                create_door_opening(wall_obj, door, wall_thickness, door_height=door_height)

    # Create window openings only on nearby wall objects
    for window in windows:
        center_x = (window.get('x1', 0.0) + window.get('x2', window.get('x1', 0.0) + 1.2)) / 2
        center_y = (window.get('y1', 0.0) + window.get('y2', window.get('y1', 0.0))) / 2
        for wall_obj in wall_objects:
            if object_is_near_point(wall_obj, center_x, center_y, tolerance=max(wall_thickness, 0.5)):
                create_window_opening(wall_obj, window, wall_thickness)
    create_floor_ceiling(bounds, height)
    
    # Create stairs
    for stair_poly in stairs:
        create_stairs(stair_poly, height, stair_width)
    
    # Create furniture
    if furniture_enabled:
        for i, furn in enumerate(furniture):
            poly = furn.get('polygon', [])
            if poly:
                furn_mesh = create_furniture(poly, height=1.0)
                if furn_mesh:
                    furn_obj = bpy.data.objects.new(f"Furniture_{i}", furn_mesh)
                    bpy.context.collection.objects.link(furn_obj)
                    
                    # Apply furniture material
                    mat_furn = bpy.data.materials.new(name="FurnitureMaterial")
                    mat_furn.use_nodes = True
                    mat_furn.node_tree.nodes.clear()
                    bsdf = mat_furn.node_tree.nodes.new(type='ShaderNodeBsdfPrincipled')
                    bsdf.inputs['Base Color'].default_value = (0.6, 0.4, 0.3, 1.0)
                    output = mat_furn.node_tree.nodes.new(type='ShaderNodeOutputMaterial')
                    mat_furn.node_tree.links.new(bsdf.outputs[0], output.inputs[0])
                    furn_obj.data.materials.append(mat_furn)
    
    # Set up camera
    bpy.ops.object.camera_add(location=(10, -10, 8))
    camera = bpy.context.active_object
    camera.rotation_euler = (math.radians(60), 0, math.radians(45))
    
    # Set as active camera
    bpy.context.scene.camera = camera
    
    # Export GLB
    glb_path = Path(output_dir) / 'model.glb'
    print(f"Exporting GLB to {glb_path}")
    bpy.ops.export_scene.gltf(
        filepath=str(glb_path),
        export_format='GLB',
        use_selection=False,
        export_materials='EXPORT'
    )
    
    # Export OBJ
    obj_path = Path(output_dir) / 'model.obj'
    print(f"Exporting OBJ to {obj_path}")
    bpy.ops.wm.obj_export(
        filepath=str(obj_path),
        export_selected_objects=False,
        export_materials=True,
        path_mode='AUTO'
    )
    
    print("Model generation complete!")


def main():
    """Main entry point when run from Blender."""
    
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description='Generate 3D model from plan data')
    parser.add_argument('--plan', required=True, help='Path to plan.json file')
    parser.add_argument('--height', type=float, required=True, help='Building height in meters')
    parser.add_argument('--out', required=True, help='Output directory')
    parser.add_argument('--wall-thickness', type=float, default=0.2, help='Wall thickness in meters')
    parser.add_argument('--stair-width', type=float, default=1.5, help='Stair width in meters')
    parser.add_argument('--no-furniture', action='store_true', help='Disable furniture generation')
    parser.add_argument('--map', type=str, default=None, help='Path to map file (mbtiles)')
    parser.add_argument('--door-height', type=float, default=None, help='Door height in meters (defaults to height * 0.85)')
    parser.add_argument('--door-width', type=float, default=1.0, help='Door width in meters')
    
    # Blender passes arguments after '--', so we need to handle that
    argv = sys.argv
    if '--' in argv:
        argv = argv[argv.index('--') + 1:]
    else:
        argv = []
    
    args = parser.parse_args(argv)
    
    # Verify files
    if not Path(args.plan).exists():
        print(f"Error: Plan file not found: {args.plan}")
        sys.exit(1)
    
    # Create output directory
    Path(args.out).mkdir(parents=True, exist_ok=True)
    
    # Generate model
    try:
        generate_model(
            args.plan, 
            args.height, 
            args.out,
            wall_thickness=args.wall_thickness,
            stair_width=args.stair_width,
            furniture_enabled=not args.no_furniture,
            map_path=args.map,
            door_height=args.door_height,
            door_width=args.door_width
        )
        print("Success!")
        sys.exit(0)
    except Exception as e:
        print(f"Error generating model: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
