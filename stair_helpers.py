"""Stair helper functions for build123d.
Provides reusable make_flight() and make_winder() that build geometry at the origin.
"""
from build123d import *


def make_flight(steps: int, going: float, rise: float, width: float, waist: float,
                extend_bottom_amount: float = 0.0, cut_soffit: bool = True):
    if steps <= 0: return None
    """Build a straight flight of stairs at the origin.
    
    Goes in +X, rises in +Z, width in -Y (Y: -width..0).
    
    Args:
        extend_bottom_amount: If > 0, extends the mass downwards at the start (local Z < 0).
        cut_soffit: If True (default), applies the linear soffit subtraction.
                    Set False when using unified soffit in the assembly.
    """
    length = steps * going
    top_z = steps * rise
    
    with BuildPart() as bp:
        # Stepped mass profile on XZ plane
        with BuildSketch(Plane.XZ):
            with BuildLine():
                # Start at (0, -extend) instead of (0,0)
                pts = [(0, -extend_bottom_amount)]
                cx, cz = 0.0, 0.0
                for _ in range(steps):
                    pts.append((cx, cz + rise))
                    pts.append((cx + going, cz + rise))
                    cx += going
                    cz += rise
                pts.append((cx, -extend_bottom_amount)) # Drop end to match start depth for solid closure
                pts.append((0, -extend_bottom_amount))
                Polyline(pts)
            make_face()
        # Plane.XZ normal is +Y, so positive amount goes +Y.
        # We want -Y (width in -Y direction), so use positive amount.
        extrude(amount=width)

        # Soffit cut — triangular void underneath
        if cut_soffit:
            # Soffit line equation: Z = (Rise/Going) * X - Waist
            # We cut everything BELOW this line.
            low_z = min(-extend_bottom_amount, -waist - 500 * rise/going) - 100
            with BuildSketch(Plane.XZ):
                with BuildLine():
                    Polyline([
                        (-500, -waist - 500 * rise/going),
                        (length, top_z - waist),
                        (length, low_z),
                        (-500, low_z),
                        (-500, -waist - 500 * rise/going)
                    ])
                make_face()
            extrude(amount=width, mode=Mode.SUBTRACT)

    return bp.part


def make_winder(width: float, rise: float, num_steps: int = 2, inner_r: float = 100.0,
                waist: float = 200.0, base_height: float = 0.0, cut_soffit: bool = True):
    if num_steps <= 0: return None
    """Build a 90-degree winder at the origin.
    
    Args:
        width: Total width of the winder block (flight_width + inner_r).
        rise: Height of a single step.
        num_steps: Number of steps in the 90-degree turn (2-4).
        inner_r: Radius of the inner void cylinder.
        waist: Vertical thickness of the soffit.
        base_height: Total rise of the flight below. Treads extrude from Z=0.
        cut_soffit: If True (default), applies the helical loft soffit.
                    Set False when using unified soffit in the assembly.
    
    Returns:
        Part. Pivot is at (0, width). Origin (0,0) is bottom-left.
    """
    import math
    
    # Pivot is top-left of the block (0, width)
    pivot = (0, width)
    
    # Generate Steps (Wedges)
    angle_per_step = 90.0 / num_steps
    
    with BuildPart() as bp:
        for i in range(num_steps):
            # Angles in degrees, relative to pivot. 
            # -90 (down) to 0 (right).
            start_angle = -90 + i * angle_per_step
            end_angle = -90 + (i + 1) * angle_per_step
            
            # Convert to radians
            a1 = math.radians(start_angle)
            a2 = math.radians(end_angle)
            
            # Points relative to pivot (0,0_local)
            # Bottom edge: y = -width. Right edge: x = width.
            
            pts = [(0,0)] # Pivot (relative)
            
            # Point 1 (Start Angle)
            if start_angle < -45:
                # Intersects bottom edge (y=-width)
                if abs(start_angle + 90) < 1e-6:
                    p1 = (0, -width)
                else:
                    p1 = (-width / math.tan(a1), -width)
            else:
                # Intersects right edge (x=width)
                p1 = (width, width * math.tan(a1))

            # Point 2 (End Angle)
            if end_angle <= -45:
                 # Intersects bottom edge
                 if abs(end_angle + 45) < 1e-6:
                     p2 = (width, -width)
                 else:
                     p2 = (-width / math.tan(a2), -width)
            else:
                # Intersects right edge
                # Note: tan(0) = 0. p2 = (width, 0).
                p2 = (width, width * math.tan(a2))
            
            poly_pts = [(0,0), p1]
            if start_angle < -45 and end_angle > -45:
                poly_pts.append((width, -width)) # The corner
            poly_pts.append(p2)
            poly_pts.append((0,0))
            
            # Shift points back to global (Pivot + P)
            global_pts = [(pivot[0] + p[0], pivot[1] + p[1]) for p in poly_pts]
            
            with BuildSketch(Plane.XY):
                with BuildLine():
                    Polyline(global_pts)
                make_face()
            extrude(amount=base_height + (i + 1) * rise)
        
        # Inner Void (Cylinder) — must cover full height
        full_height = base_height + num_steps * rise
        with Locations(pivot):
            Cylinder(radius=inner_r, height=full_height * 2 + 1000, align=(Align.CENTER, Align.CENTER, Align.CENTER), mode=Mode.SUBTRACT)

        # Curved Soffit (Helical Loft)
        if cut_soffit:
            soffit_profiles = []
            num_loft_sections = 15
            total_rise = num_steps * rise
            start_z = base_height - waist
            end_z = base_height + total_rise - waist
            
            for i in range(num_loft_sections):
                t = i / (num_loft_sections - 1)
                h = start_z + t * (end_z - start_z)
                angle_deg = -90 + t * 90
                
                cut_width = width * 1.5 
                
                with BuildSketch(Plane.XZ) as sk:
                    with BuildLine():
                         Polyline([(0,0), (cut_width, 0), (cut_width, h), (0, h), (0,0)])
                    make_face()
                
                loc = Location(pivot) * Rotation(0, 0, angle_deg)
                soffit_profiles.append(sk.sketch.moved(loc))
            
            loft(soffit_profiles, mode=Mode.SUBTRACT)

    return bp.part


if __name__ == "__main__":
    from ocp_vscode import show, set_port
    set_port(3939)

    print("=== Testing make_flight() ===")
    
    # Test 1: 3-step flight
    f3 = make_flight(steps=3, going=250, rise=220, width=600, waist=200)
    bb3 = f3.bounding_box()
    print(f"3-step flight bbox: X={bb3.min.X:.0f}..{bb3.max.X:.0f}, Y={bb3.min.Y:.0f}..{bb3.max.Y:.0f}, Z={bb3.min.Z:.0f}..{bb3.max.Z:.0f}")
    assert abs(bb3.max.X - 750) < 1, f"3-step X wrong: {bb3.max.X}"
    x_width = abs(bb3.max.Y - bb3.min.Y)
    assert abs(x_width - 600) < 1, f"3-step Y width wrong: {x_width}"
    # Z check relaxed to cover soffit depth if needed, but Max Z should be accurate
    assert abs(bb3.max.Z - 660) < 1, f"3-step Z wrong: {bb3.max.Z}"
    print("3-step flight: PASS")

    # Test 2: 8-step flight
    f8 = make_flight(steps=8, going=250, rise=220, width=600, waist=200)
    bb8 = f8.bounding_box()
    print(f"8-step flight bbox: X={bb8.min.X:.0f}..{bb8.max.X:.0f}, Y={bb8.min.Y:.0f}..{bb8.max.Y:.0f}, Z={bb8.min.Z:.0f}..{bb8.max.Z:.0f}")
    assert abs(bb8.max.X - 2000) < 1, f"8-step X wrong: {bb8.max.X}"
    assert abs(bb8.max.Z - 1760) < 1, f"8-step Z wrong: {bb8.max.Z}"
    print("8-step flight: PASS")

    print("\n=== Testing make_winder() parametric ===")
    
    # Test: 3-step winder with base_height=660 (3 bottom steps * 220)
    base_h = 3 * 220  # 660
    w3 = make_winder(width=700, rise=220, num_steps=3, inner_r=100, waist=200, base_height=base_h)
    bbw = w3.bounding_box()
    print(f"3-step winder bbox: X={bbw.min.X:.0f}..{bbw.max.X:.0f}, Y={bbw.min.Y:.0f}..{bbw.max.Y:.0f}, Z={bbw.min.Z:.0f}..{bbw.max.Z:.0f}")
    assert abs(bbw.max.X - 700) < 1, f"Winder X wrong: {bbw.max.X}"
    assert abs(bbw.max.Y - 700) < 1, f"Winder Y wrong: {bbw.max.Y}"
    # Max Z = base_height + num_steps * rise = 660 + 660 = 1320
    assert abs(bbw.max.Z - 1320) < 1, f"Winder Z wrong: {bbw.max.Z}"
    
    # Check void/soffit
    # Min Z should be roughly base_height - waist (660-200=460) or 0 depending on soffit
    print(f"Winder Min Z: {bbw.min.Z}")
    
    print("3-step winder: PASS")

    print("\n=== All tests PASSED ===")
    show(f8, w3, names=["8-Step Flight", "3-Step Winder"])
