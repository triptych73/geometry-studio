"""Parametric Staircase Builder.
Generates a staircase model based on user-defined parameters for:
- Width, Rise, Going, Waist
- Step Counts (S_bottom, Winder, S_top)
- Inner Radius
- Unified vs per-component soffit

Usage:
    python staircase_parametric.py [--width 800] [--winder 3] [--no_unified_soffit]
"""
import math
import argparse
from build123d import *
from ocp_vscode import show, set_port
from stair_helpers import make_flight, make_winder

# Default Configuration
DEFAULT_CONFIG = {
    "width": 800.0,
    "rise": 220.0,
    "going": 250.0,
    "waist": 200.0,
    "inner_r": 100.0,
    "s_bottom_steps": 3,
    "winder_steps": 3,
    "s_top_steps": 8,
    "extend_top_flight": 300.0,
    "unified_soffit": False
}

def build_staircase(config):
    """Build the full staircase assembly from config dict."""
    width = config["width"]
    rise = config["rise"]
    going = config["going"]
    waist = config["waist"]
    inner_r = config["inner_r"]
    
    sb_steps = config["s_bottom_steps"]
    w_steps = config["winder_steps"]
    st_steps = config["s_top_steps"]
    ext_top = config["extend_top_flight"]
    unified = config.get("unified_soffit", True)
    
    # Derived Dimensions
    winder_width = width + inner_r
    sb_length = sb_steps * going
    sb_top_z = sb_steps * rise
    winder_base_z = sb_top_z
    winder_top_z = winder_base_z + w_steps * rise
    st_base_z = winder_top_z
    
    # Pivot Point (Global): inner corner of the turn
    pivot_x = sb_length
    pivot_y = 0.0
    
    print(f"Building: W={width}, Rise={rise}, Steps={sb_steps}+{w_steps}+{st_steps}, Unified={unified}")
    
    # --- Build Components ---
    # When unified=False: each component cuts its own soffit (old method, may have kinks)
    # When unified=True: raw blocks are fused, then a single smooth RuledSurface soffit is subtracted
    do_cut = not unified
    
    # 1. S_Bottom: +X direction, inner edge at Y=-inner_r
    sb = make_flight(steps=sb_steps, going=going, rise=rise, width=width, waist=waist, cut_soffit=do_cut)
    sb = sb.translate((0, -inner_r, 0))
    
    # 2. Winder: pivot at global (pivot_x, pivot_y)
    winder = make_winder(width=winder_width, rise=rise, num_steps=w_steps,
                         inner_r=inner_r, waist=waist, base_height=winder_base_z, cut_soffit=do_cut)
    winder = winder.translate((pivot_x, -winder_width, 0))
    
    # 3. S_Top: +Y direction after 90° rotation, inner edge at X=pivot_x+inner_r
    st = make_flight(steps=st_steps, going=going, rise=rise, width=width, waist=waist,
                     extend_bottom_amount=ext_top, cut_soffit=do_cut)
    st = st.rotate(Axis.Z, 90)
    st = st.translate((pivot_x + inner_r, 0, st_base_z))
    
    if not unified:
        # Per-component soffit (old method) — may have kinks at junctions
        stair = Compound([sb, winder, st])
        return stair
    
    # --- Unified Soffit (RuledSurface Spline Subtraction) ---
    # Build a smooth surface between an inner Spline (curved at winder) and
    # an outer Spline (square at winder), then extrude downwards to create
    # a cutting block. This guarantees:
    #  - C2 continuity at the flight/winder junctions (no kink)
    #  - Square outer corner is preserved (not rounded)
    #  - Consistent waist thickness throughout
    
    stair_solid = sb.fuse(winder).fuse(st)
    st_length = st_steps * going
    
    def get_soffit_path_pts(is_outer):
        """Generate Spline control points for the soffit edge."""
        pts = []
        
        # 10mm buffer so cutting solid cleanly engulfs the staircase width
        if is_outer:
            y_off = -winder_width - 10
            x_off = pivot_x + winder_width + 10
            corner_x = pivot_x + winder_width + 10
            corner_y = pivot_y - winder_width - 10
            cur_r = winder_width + 10
        else:
            y_off = -inner_r + 10
            x_off = pivot_x + inner_r - 10
            cur_r = inner_r - 10
        
        # Bottom flight (extend well beyond start)
        pts.append((-2000, pivot_y + y_off, -2000 * rise / going - waist))
        
        if sb_length > 0:
            n_sb = 6
            for i in range(n_sb):
                x = i * sb_length / (n_sb - 1)
                z = x * rise / going - waist
                pts.append((x, pivot_y + y_off, z))
        else:
            pts.append((0, pivot_y + y_off, -waist))
        
        # Winder transition
        if is_outer:
            # Square corner — single point at the exact outer corner
            z = winder_base_z + 0.5 * (w_steps * rise) - waist
            pts.append((corner_x, corner_y, z))
        else:
            # Curved inner — sample multiple points around the arc
            n_arc = 5
            for i in range(n_arc):
                t = (i + 1) / (n_arc + 1)
                angle = math.radians(-90 + t * 90)
                x = pivot_x + cur_r * math.cos(angle)
                y = pivot_y + cur_r * math.sin(angle)
                z = winder_base_z + t * (w_steps * rise) - waist
                pts.append((x, y, z))
        
        # Top flight (extend well beyond end)
        if st_length > 0:
            n_st = 6
            for i in range(1, n_st):
                y = i * st_length / (n_st - 1)
                z = winder_top_z + y * rise / going - waist
                pts.append((x_off, y, z))
        else:
             pts.append((x_off, 0, winder_top_z - waist))
        
        pts.append((x_off, st_length + 2000, winder_top_z + (st_length + 2000) * rise / going - waist))
        return pts
    
    inner_pts = get_soffit_path_pts(is_outer=False)
    outer_pts = get_soffit_path_pts(is_outer=True)
    
    with BuildLine() as inner_path:
        Spline(inner_pts)
    with BuildLine() as outer_path:
        Spline(outer_pts)
    
    soffit_face = Face.make_surface_from_curves(inner_path.edges()[0], outer_path.edges()[0])
    soffit_cut = extrude(soffit_face, amount=3000, dir=(0, 0, -1))
    
    result = stair_solid - soffit_cut
    print(f"Unified soffit applied (RuledSurface spline)")
    return result

if __name__ == "__main__":
    set_port(3939)
    
    parser = argparse.ArgumentParser()
    parser.add_argument("--width", type=float, default=DEFAULT_CONFIG["width"])
    parser.add_argument("--rise", type=float, default=DEFAULT_CONFIG["rise"])
    parser.add_argument("--going", type=float, default=DEFAULT_CONFIG["going"])
    parser.add_argument("--steps_bottom", type=int, default=DEFAULT_CONFIG["s_bottom_steps"])
    parser.add_argument("--steps_winder", type=int, default=DEFAULT_CONFIG["winder_steps"])
    parser.add_argument("--steps_top", type=int, default=DEFAULT_CONFIG["s_top_steps"])
    parser.add_argument("--no_unified_soffit", action="store_true", 
                        help="Use per-component soffit cuts (old method)")
    args = parser.parse_args()
    
    config = DEFAULT_CONFIG.copy()
    config.update({
        "width": args.width,
        "rise": args.rise,
        "going": args.going,
        "s_bottom_steps": args.steps_bottom,
        "winder_steps": args.steps_winder,
        "s_top_steps": args.steps_top,
        "unified_soffit": not args.no_unified_soffit if args.no_unified_soffit else DEFAULT_CONFIG["unified_soffit"]
    })
    
    stair = build_staircase(config)
    
    bb = stair.bounding_box()
    print(f"BBox: X={bb.min.X:.1f}..{bb.max.X:.1f}, Y={bb.min.Y:.1f}..{bb.max.Y:.1f}, Z={bb.min.Z:.1f}..{bb.max.Z:.1f}")
    
    export_stl(stair, "staircase_parametric.stl")
    print("Exported: staircase_parametric.stl")
    
    show(stair, names=["Staircase"])
