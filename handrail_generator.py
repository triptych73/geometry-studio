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

def get_true_walkline(config, offset_from_inner=None, z_offset=0.0):
    """
    Calculates the mathematically exact 3D path up the stairs.
    offset_from_inner: Distance from the inside handrail plane. 
                      (e.g., width/2 = centerline, 0 = inner boundary).
    z_offset: Vertical shift (e.g., 900mm for handrail height, or 0 for floor level).
    """
    width = config["width"]
    rise = config["rise"]
    going = config["going"]
    inner_r = config["inner_r"]
    sb = config["s_bottom_steps"]
    w_steps = config["winder_steps"]
    st = config["s_top_steps"]
    nosing = config.get("nosing", 0)
    
    if offset_from_inner is None:
        offset_from_inner = width / 2.0
        
    pts = []
    
    # 1. Base Z line logic
    local_y = -inner_r - offset_from_inner
    
    # Bottom Flight (0 to sb)
    for i in range(sb + 1):
        x = i * going
        z = i * rise + z_offset
        pts.append(Vector(x, local_y, z))
        
    # Winder (Angles from -90 to 0)
    pivot_x = sb * going
    r_walk = inner_r + offset_from_inner
    angle_per = 90.0 / w_steps if w_steps > 0 else 0
    
    if w_steps > 0:
        for i in range(1, w_steps):
            angle_rad = math.radians(-90 + i * angle_per)
            x = pivot_x + r_walk * math.cos(angle_rad)
            y = r_walk * math.sin(angle_rad)
            z = (sb + i) * rise + z_offset
            pts.append(Vector(x, y, z))
            
    # Top Flight
    start_z = (sb + w_steps) * rise
    for i in range(st + 1):
        x = pivot_x + inner_r + offset_from_inner
        y = i * going
        z = start_z + i * rise + z_offset
        pts.append(Vector(x, y, z))
        
    return pts


def get_outer_perimeter_path(config, inset=25.0, z_offset=0.0):
    """
    Calculates the 3D path following the geometric square outer corner of the stairwell,
    rather than a curved arc. Used for exterior balusters and handrails that mount to 
    the external stringer/wall.
    """
    width = config["width"]
    rise = config["rise"]
    going = config["going"]
    inner_r = config["inner_r"]
    sb = config["s_bottom_steps"]
    w_steps = config["winder_steps"]
    st = config["s_top_steps"]
    
    pts = []
    
    # Bottom Flight
    local_y = -inner_r - width + inset
    for i in range(sb + 1):
        x = i * going
        z = i * rise + z_offset
        pts.append(Vector(x, local_y, z))
        
    # Winder (Angles from -90 to 0)
    pivot_x = sb * going
    angle_per = 90.0 / w_steps if w_steps > 0 else 0
    winder_width = width - inset  # Radius to the handrail line
    
    if w_steps > 0:
        for i in range(1, w_steps):
            angle_deg = -90 + i * angle_per
            a_rad = math.radians(angle_deg)
            
            # Calculate intersection with the square perimeter bounding box
            if angle_deg < -45:
                if abs(angle_deg + 90) < 1e-6:
                    r_outer = winder_width
                else:
                    r_outer = abs(-winder_width / math.sin(a_rad))
            else:
                r_outer = abs(winder_width / math.cos(a_rad))
            
            total_r = inner_r + r_outer
            x = pivot_x + total_r * math.cos(a_rad)
            y = total_r * math.sin(a_rad)
            z = (sb + i) * rise + z_offset
            pts.append(Vector(x, y, z))
            
    # Top Flight
    start_z = (sb + w_steps) * rise
    for i in range(st + 1):
        x = pivot_x + inner_r + width - inset
        y = i * going
        z = start_z + i * rise + z_offset
        pts.append(Vector(x, y, z))
        
    return pts


def build_handrail(config, height=900.0, diameter=40.0):
    """
    Builds a 3D handrail solid by sweeping a profile.
    Uses perfectly straight geometry over straight flights, and tangent-matched 
    splines over winders to eliminate "curvy wurvy" wobbles.
    """
    # The inner handrail usually sits vertically above the inner stringer (offset ~ 0)
    pts = get_true_walkline(config, offset_from_inner=-25.0, z_offset=height)
    
    sb = config["s_bottom_steps"]
    w = config["winder_steps"]
    
    # Split the exact calculated points into topological feature zones
    bottom_pts = pts[:sb + 1]
    winder_pts = pts[sb : sb + w + 1] if w > 0 else []
    top_pts = pts[sb + w :]
    
    try:
        with BuildPart() as rail:
            with BuildLine() as p_line:
                # 1. Perfectly straight bottom flight
                if len(bottom_pts) > 1:
                    l1 = Line(bottom_pts[0], bottom_pts[-1])
                    
                # 2. Tangent-constrained winder arc
                if len(winder_pts) > 1:
                    # In Vector format
                    t_in = Vector(config["going"], 0, config["rise"]).normalized()
                    t_out = Vector(0, config["going"], config["rise"]).normalized()
                    Spline(winder_pts, tangents=(t_in, t_out))
                    
                # 3. Perfectly straight top flight
                if len(top_pts) > 1:
                    l2 = Line(top_pts[0], top_pts[-1])
                    
            path_wire = p_line.wires()[0]
            
            # Position the profile at the start of the path
            with BuildSketch(Plane(pts[0], z_dir=path_wire.tangent_at(0))):
                Circle(diameter / 2)
            
            sweep(path=path_wire, transition=Transition.ROUND)
            
        return rail.part
    except Exception as e:
        print(f"  [!] Handrail sweep fallback: {e}")
        # Always return something valid
        with BuildLine() as backup:
            Polyline(*pts)
        return backup.wires()[0]

def build_walkline(config):
    """
    Builds a clear 3D ribbon showing the geometric walkline (centre of stairs).
    Sweeping a flat ribbon (e.g. 50x5mm) makes it clearly visible in GLTF exports.
    """
    pts = get_true_walkline(config, offset_from_inner=config["width"] / 2.0, z_offset=20.0)
    
    sb = config["s_bottom_steps"]
    w = config["winder_steps"]
    
    bottom_pts = pts[:sb + 1]
    winder_pts = pts[sb : sb + w + 1] if w > 0 else []
    top_pts = pts[sb + w :]
    
    try:
        with BuildPart() as walk_p:
            with BuildLine() as p_line:
                if len(bottom_pts) > 1:
                    Line(bottom_pts[0], bottom_pts[-1])
                if len(winder_pts) > 1:
                    t_in = Vector(config["going"], 0, config["rise"]).normalized()
                    t_out = Vector(0, config["going"], config["rise"]).normalized()
                    Spline(winder_pts, tangents=(t_in, t_out))
                if len(top_pts) > 1:
                    Line(top_pts[0], top_pts[-1])
                    
            path_wire = p_line.wires()[0]
            
            # Using a rectangular ribbon so it clearly shows the walkline path
            with BuildSketch(Plane(pts[0], z_dir=path_wire.tangent_at(0))):
                Rectangle(50, 5)
                
            sweep(path=path_wire, transition=Transition.ROUND)
            
        return walk_p.part
    except Exception as e:
        print(f"  [!] Walkline sweep fallback: {e}")
        return None

