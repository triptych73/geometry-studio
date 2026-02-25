"""Baluster (Spindle) Generator for Geometry Studio.
Places vertical supports between treads and handrails based on nosing paths.
"""
from build123d import *
import math
from handrail_generator import get_true_walkline

def build_balusters(config, handrail_height=900.0, diameter=20.0, max_spacing=100.0):
    """
    Generates a list of vertical spindle Parts with code-compliant spacing.
    Automatically calculates spindles per step to ensure gap is < max_spacing.
    """
    width = config["width"]
    going = config["going"]
    # Traces the inner arc to precisely match the handrail
    nodes = get_true_walkline(config, offset_from_inner=-25.0, z_offset=0.0)
    
    balusters = []
    
    # 1. Build the exact mathematical Wire path that the handrail sweeps
    sb = config["s_bottom_steps"]
    w = config["winder_steps"]
    
    bottom_pts = nodes[:sb + 1]
    winder_pts = nodes[sb : sb + w + 1] if w > 0 else []
    top_pts = nodes[sb + w :]
    
    try:
        with BuildLine() as p_line:
            if len(bottom_pts) > 1:
                Line(bottom_pts[0], bottom_pts[-1])
            if len(winder_pts) > 1:
                t_in = Vector(going, 0, config["rise"]).normalized()
                t_out = Vector(0, going, config["rise"]).normalized()
                Spline(winder_pts, tangents=(t_in, t_out))
            if len(top_pts) > 1:
                Line(top_pts[0], top_pts[-1])
                
        path_wire = p_line.wires()[0]
    except Exception as e:
        # Fallback to pure linear if the spline solver complains
        with BuildLine() as p_line:
            Polyline(*nodes)
        path_wire = p_line.wires()[0]
        
    # 2. Extract 3D points densely to compute a 2D Top-Down crawl
    samples = 1000
    points_3d = []
    
    # Pre-compute the dense 3D points and tangents along the spline
    for i in range(samples + 1):
        t = i / samples
        pt = path_wire.position_at(t)
        tan = path_wire.tangent_at(t)
        points_3d.append((pt, tan))
        
    # Calculate the cumulative horizontal (2D XY) distance ONLY
    cumulative_2d = [0.0]
    total_2d_dist = 0.0
    for i in range(samples):
        p1, _ = points_3d[i]
        p2, _ = points_3d[i+1]
        dist2d = math.sqrt((p2.X - p1.X)**2 + (p2.Y - p1.Y)**2)
        total_2d_dist += dist2d
        cumulative_2d.append(total_2d_dist)
        
    # Determine how many balusters we need based on horizontal gap
    count = math.ceil(total_2d_dist / max_spacing)
    if count < 2:
        return []
        
    actual_spacing_2d = total_2d_dist / count
    
    # 3. Drop balusters at exactly even 2D horizontal intervals
    for j in range(1, count):
        target_dist = j * actual_spacing_2d
        
        # Find which dense sample interval contains this target horizontal distance
        idx = 0
        while idx < samples and cumulative_2d[idx + 1] < target_dist:
            idx += 1
            
        # Linearly interpolate between the two dense 3D points to find the exact drop spot
        d1 = cumulative_2d[idx]
        d2 = cumulative_2d[idx + 1]
        
        # Safe-guard division by zero if two points are perfectly stacked
        frac = (target_dist - d1) / (d2 - d1) if d2 > d1 else 0.0
        
        p1, tan1 = points_3d[idx]
        p2, tan2 = points_3d[idx + 1]
        
        # True 3D coordinate and Tangent interpolation
        curr_pos = p1 + (p2 - p1) * frac
        tangent = tan1 + (tan2 - tan1) * frac
        
        # Architectural alignment: Push the baluster center backwards along the flight vector
        # so it sits firmly on the wood step, not hovering off the geometric nosing edge
        flight_dir = Vector(tangent.X, tangent.Y, 0).normalized()
        offset_pos = curr_pos - (flight_dir * (diameter / 2 + 5))
        
        with BuildPart() as b:
            with BuildSketch(Plane.XY.offset(offset_pos.Z)):
                with Locations((offset_pos.X, offset_pos.Y)):
                    Circle(diameter / 2)
            extrude(amount=handrail_height)
        balusters.append(b.part)
        
    return balusters

