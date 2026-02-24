"""Handrail Generator for Geometry Studio.
Traces 3D paths along staircase stringers and sweeps profiles to create continuous handrails.
"""
from build123d import *
import math

"""Handrail Generator for Geometry Studio.
Calculates 3D nosing paths and sweeps architectural profiles for continuous handrails.
"""
from build123d import *
import math

def get_stair_nosing_points(config):
    """
    Calculates the 3D coordinates of every step's nosing point.
    Returns a list of Vector points in global space.
    """
    width = config["width"]
    rise = config["rise"]
    going = config["going"]
    inner_r = config["inner_r"]
    sb_steps = config["s_bottom_steps"]
    w_steps = config["winder_steps"]
    st_steps = config["s_top_steps"]
    
    pts = []
    
    # 1. Bottom Flight (Straight along X)
    for i in range(sb_steps + 1):
        # Nosing point is at the outer corner of each tread
        # Inner edge is at -inner_r. Outer edge is at -(inner_r + width)
        pts.append(Vector(i * going, -inner_r, i * rise))
        
    # 2. Winder (Radial Pivot at sb_length, 0)
    pivot_x = sb_steps * going
    angle_per = 90.0 / w_steps if w_steps > 0 else 0
    for i in range(1, w_steps + 1) if w_steps > 0 else []:
        angle_rad = math.radians(-90 + i * angle_per)
        x = pivot_x + inner_r * math.cos(angle_rad)
        y = inner_r * math.sin(angle_rad)
        z = (sb_steps + i) * rise
        pts.append(Vector(x, y, z))
        
    # 3. Top Flight (Straight along Y)
    start_z = (sb_steps + w_steps) * rise
    for i in range(1, st_steps + 1):
        x = pivot_x + inner_r
        y = i * going
        z = start_z + i * rise
        pts.append(Vector(x, y, z))
        
    return pts

def build_handrail(config, height=900.0, diameter=40.0):
    """
    Builds a 3D handrail solid by sweeping a profile along a smooth 3D path.
    Uses a guided spline to avoid self-intersection at tight winder turns.
    """
    nodes = get_stair_nosing_points(config)
    rail_pts = [p + Vector(0, 0, height) for p in nodes]
    
    # We sample the path at key transitions to create a smooth guided spline.
    # Too many points in a tight winder cause "wiggly" paths that break sweeps.
    sb = config["s_bottom_steps"]
    w = config["winder_steps"]
    
    # Key indices: Start, Mid-Bottom, Winder-Start, Winder-Mid, Winder-End, Mid-Top, End
    sample_idx = [
        0, 
        sb // 2, 
        sb, 
        sb + (w // 2), 
        sb + w, 
        sb + w + (len(nodes) - (sb + w)) // 2, 
        len(nodes) - 1
    ]
    # Filter valid indices and remove duplicates
    sample_idx = sorted(list(set([i for i in sample_idx if 0 <= i < len(nodes)])))
    smooth_pts = [rail_pts[i] for i in sample_idx]
    
    try:
        # Use a slightly smaller diameter for very tight winders to avoid self-intersection
        effective_dia = diameter if config["inner_r"] >= 150 else diameter * 0.75
        
        with BuildPart() as rail:
            # Create a smooth spline wire
            with BuildLine() as p_line:
                path_wire = Spline(smooth_pts)
            
            # Position the profile at the start of the path
            with BuildSketch(Plane(rail_pts[0], z_dir=path_wire.tangent_at(0))):
                Circle(effective_dia / 2)
            
            # Sweep with ROUND transitions for structural smoothness
            sweep(path=path_wire, transition=Transition.ROUND)
            
        return rail.part
    except Exception as e:
        print(f"  [!] Handrail sweep fallback: {e}. Returning path wire.")
        # Re-build a simple wire to ensure we return a valid Build123d object
        with BuildLine() as fallback_line:
            path = Spline(smooth_pts)
        return path

