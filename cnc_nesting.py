"""CNC Nesting utility for Geometry Studio (Precision Factory Edition v4).
Handles multi-sheet nesting, thickness grouping, and automatic part splitting (scarf joints).
Vertex ordering is preserved by tracing wire edges to avoid "spiky" concave shapes.
"""
from build123d import *
import rectpack
import math

def extract_2d_profile(part):
    """
    Robustly extracts the 2D perimeter of a 3D part using tessellation.
    """
    print(f"    [ENGINE] Extracting 2D profile for {type(part)}...", flush=True)
    # 1. Find the face with the largest area
    try:
        if hasattr(part, "faces"):
            faces = part.faces().sort_by(lambda f: f.area)
        else:
            print(f"    [ENGINE] ERROR: Object {type(part)} has no faces method.", flush=True)
            return None
    except Exception as e:
        print(f"    [ENGINE] ERROR during face extraction: {e}", flush=True)
        return None
        
    if not faces:
        print("    [ENGINE] ERROR: Face list is empty.", flush=True)
        return None
    
    face = faces[-1]
    print(f"    [ENGINE] Selected face area: {face.area:.2f}", flush=True)
    
    # 2. Create a local coordinate system (Plane) based on this face
    # We use the face's center and its normal to define the "floor" for 2D extraction
    f_plane = Plane(face.center(), z_dir=face.normal_at(face.center()))
    
    # 3. Extract vertices in sequential order by walking edges
    wire = face.outer_wire()
    edges = wire.edges()
    print(f"    [ENGINE] Walking {len(edges)} edges for perimeter...", flush=True)
    
    ordered_pts = []
    for edge in edges:
        try:
            p = edge.start_point()
            # Convert to local 2D coords
            lv = f_plane.to_local_coords(p)
            pt = (round(float(lv.X), 2), round(float(lv.Y), 2))
            
            # Add point if not duplicate of previous
            if not ordered_pts or pt != ordered_pts[-1]:
                ordered_pts.append(pt)
        except Exception:
            continue
            
    # Ensure the loop is closed if needed
    if edges:
        p_final = edges[-1].end_point()
        lv_f = f_plane.to_local_coords(p_final)
        pt_f = (round(float(lv_f.X), 2), round(float(lv_f.Y), 2))
        if pt_f != ordered_pts[0] and pt_f != ordered_pts[-1]:
            ordered_pts.append(pt_f)
    
    if len(ordered_pts) < 3:
        print(f"    [ENGINE] ERROR: Only {len(ordered_pts)} points found. Perimeter failed.", flush=True)
        return None
        
    # 4. Calculate 2D bounding box
    xs = [p[0] for p in ordered_pts]
    ys = [p[1] for p in ordered_pts]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    
    width = round(max_x - min_x, 2)
    height = round(max_y - min_y, 2)
    print(f"    [ENGINE] Profile Extracted: {width}x{height}mm ({len(ordered_pts)} vertices)", flush=True)
    if width > 0 and height > 0:
        print(f"    [ENGINE] Perimeter Start: {ordered_pts[:2]}", flush=True)
    
    # 5. Normalise points so the bounding box starts at 0,0
    normalised_pts = [(round(p[0] - min_x, 2), round(p[1] - min_y, 2)) for p in ordered_pts]
    
    return {
        "width": width,
        "height": height,
        "points": normalised_pts,
        "area": face.area
    }

def split_with_scarf_joint(part: Part, sheet_width: float):
    """
    Splits a 3D part into interlocking segments using a multi-tooth structural scarf joint.
    Automatically detects the longest axis (X, Y, or Z) to apply the split correctly.
    """
    bb = part.bounding_box()
    dims = {
        'X': bb.max.X - bb.min.X,
        'Y': bb.max.Y - bb.min.Y,
        'Z': bb.max.Z - bb.min.Z
    }
    
    max_dim = max(dims.values())
    max_axis = [k for k, v in dims.items() if v == max_dim][0]
    
    if max_dim <= sheet_width:
        return [part]
    
    print(f"    [ENGINE] Oversized part detected ({max_dim:.1f}mm on {max_axis}). Splitting with Triple-Tooth Scarf...", flush=True)
    
    # Calculate split point (center)
    overlap = 150.0
    split_pos = (getattr(bb.min, max_axis) + getattr(bb.max, max_axis)) / 2
    
    # Create the multi-tooth interlocking cutting tool
    # We'll build it on XY and rotate it to the target axis if necessary
    h = 2000.0 # Excessively tall to ensure through-cut
    tooth_w = overlap / 3
    
    # Define a generic tooth profile on a plane
    with BuildPart() as tool_builder:
        with BuildSketch(Plane.XY):
            with BuildLine():
                # A Triple-Tooth "Puzzle" Profile
                # This profile cuts the "A" half (keeps everything to the left/bottom)
                p_min = -5000 # Large enough to cover part
                p_max = 5000
                
                # We'll define the zig-zag along the X-equivalent axis of the cut
                # And the depth along the Y-equivalent
                pts = [
                    (p_min, p_min),
                    (split_pos - overlap/2, p_min),
                    (split_pos - overlap/2, -20),
                    (split_pos - overlap/2 + tooth_w, -20),
                    (split_pos - overlap/2 + tooth_w, 20),
                    (split_pos + overlap/2 - tooth_w, 20),
                    (split_pos + overlap/2 - tooth_w, p_max),
                    (p_min, p_max),
                    (p_min, p_min)
                ]
                Polyline(pts)
            make_face()
        extrude(amount=h, both=True)
    
    cutter_a = tool_builder.part
    
    # Rotate cutter if we are splitting along Y or Z
    if max_axis == 'Y':
        cutter_a = cutter_a.rotate(Axis.Z, 90)
    elif max_axis == 'Z':
        cutter_a = cutter_a.rotate(Axis.Y, 90)
        
    part_a = part & cutter_a
    part_b = part - cutter_a
    
    results = []
    if part_a.volume > 1000: results.append(part_a)
    if part_b.volume > 1000: results.append(part_b)
    
    return results

def nest_parts_optimized(part_data, sheet_width=2440, sheet_height=1220):
    """Runs multiple packing algorithms and returns the most efficient one."""
    algos = [
        rectpack.MaxRectsBaf,
        rectpack.MaxRectsBl,
        rectpack.SkylineBl,
        rectpack.GuillotineBssfLas
    ]
    best_result = None
    min_sheets = 999
    max_efficiency = -1.0
    
    # Filter fittable vs oversized
    fittable = [p for p in part_data if (p["width"] <= sheet_width and p["height"] <= sheet_height) or (p["height"] <= sheet_width and p["width"] <= sheet_height)]
    
    for algo in algos:
        packer = rectpack.newPacker(mode=rectpack.PackingMode.Offline, bin_algo=rectpack.PackingBin.BFF, pack_algo=algo, rotation=True)
        for _ in range(50): packer.add_bin(sheet_width, sheet_height)
        for p in fittable: packer.add_rect(p["width"], p["height"], rid=p["id"])
        packer.pack()
        
        rects = packer.rect_list()
        num_sheets = max([r[0] for r in rects]) + 1 if rects else 0
        
        packed_ids = [r[5] for r in rects]
        packed_area = sum(p["width"] * p["height"] for p in fittable if p["id"] in packed_ids)
        total_area = num_sheets * sheet_width * sheet_height
        efficiency = packed_area / total_area if total_area > 0 else 0
        
        if (num_sheets > 0 and num_sheets < min_sheets) or (num_sheets == min_sheets and efficiency > max_efficiency):
            min_sheets = num_sheets
            max_efficiency = efficiency
            sheets = {}
            for bin_idx, x, y, w, h, rid in rects:
                if bin_idx not in sheets: sheets[bin_idx] = []
                orig = next(p for p in fittable if p["id"] == rid)
                sheets[bin_idx].append({
                    "id": rid, "name": orig["name"], "x": x, "y": y, "width": w, "height": h, 
                    "is_rotated": not (abs(w - orig["width"]) < 0.1), "points": orig["points"]
                })
            best_result = {
                "algo": str(algo), "efficiency": round(efficiency * 100, 2),
                "sheet_count": num_sheets, "sheets": sheets
            }
    return best_result
