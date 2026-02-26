"""Structural Construction-Level Staircase Builder.

Generates a staircase model decomposed into real construction elements:
  - Treads & Risers (20mm timber, 50% transparent)
  - Stringers (side beams, opaque)
  - Carriages (internal bearers, opaque)
  - Soffit Ribs (CNC-cut plywood formers, opaque)
  - Plaster Soffit (10mm shell via boolean subtraction, 50% transparent)

Backward-compatible: --mode volumetric delegates to staircase_parametric.py.

Usage:
    python staircase_structural.py [--mode structural|volumetric]
"""
import math
import argparse
from build123d import *
from ocp_vscode import show, set_port

# Re-use the volumetric builder for plaster boolean and backward compat
from staircase_parametric import build_staircase, DEFAULT_CONFIG as PARAM_DEFAULTS

# ---------------------------------------------------------------------------
# Configuration (extends the parametric defaults)
# ---------------------------------------------------------------------------
DEFAULT_CONFIG = {**PARAM_DEFAULTS,
    "tread_thickness": 20.0,
    "riser_thickness": 20.0,
    "nosing":          20.0,
    "stringer_width":  50.0,
    "stringer_depth": 220.0,
    "carriage_width":  50.0,
    "carriage_depth": 180.0,
    "rib_spacing":    300.0,
    "rib_width":       18.0,
    "rib_depth":      100.0,
    "plaster_thickness": 10.0,
}

from handrail_generator import build_handrail, build_walkline
from baluster_generator import build_balusters

# Colours
C_TREAD    = (0.72, 0.52, 0.30)
C_RISER    = (0.78, 0.60, 0.38)
C_STRINGER = (0.55, 0.38, 0.20)
C_CARRIAGE = (0.48, 0.33, 0.18)
C_RIB      = (0.60, 0.45, 0.25)
C_PLASTER  = (0.93, 0.91, 0.87)
C_HANDRAIL = (0.40, 0.26, 0.13) # Rich Walnut Finish
C_BALUSTER  = (0.20, 0.20, 0.20) # Slate Grey/Metallic
C_WALKLINE = (0.0, 0.8, 1.0) # Neon blue ribbon

# ===========================================================================
# WINDER POLYGON HELPER  (exact copy of make_winder logic from stair_helpers)
# ===========================================================================

def _winder_step_polygon(step_idx, num_steps, winder_width):
    """Return XY polygon points for one winder step, relative to pivot (0,0).

    Uses RECTANGULAR outer boundary (bottom edge y=-winder_width, right edge x=winder_width).
    Angles sweep from -90° (down) to 0° (right).
    """
    angle_per = 90.0 / num_steps
    sa = -90 + step_idx * angle_per
    ea = -90 + (step_idx + 1) * angle_per
    a1, a2 = math.radians(sa), math.radians(ea)
    w = winder_width

    # Point 1 (start angle boundary intersection)
    if sa < -45:
        p1 = (0, -w) if abs(sa + 90) < 1e-6 else (-w / math.tan(a1), -w)
    else:
        p1 = (w, w * math.tan(a1))

    # Point 2 (end angle boundary intersection)
    if ea <= -45:
        p2 = (w, -w) if abs(ea + 45) < 1e-6 else (-w / math.tan(a2), -w)
    else:
        p2 = (w, w * math.tan(a2))

    pts = [(0, 0), p1]
    if sa < -45 and ea > -45:
        pts.append((w, -w))  # rectangular corner
    pts.append(p2)
    pts.append((0, 0))
    return pts


# ===========================================================================
# STRAIGHT FLIGHT ELEMENTS
# ===========================================================================

def _flight_treads_risers(steps, going, rise, width, tread_t, riser_t, nosing=0.0):
    """Individual treads & risers for one straight flight at local origin.
    Includes 'nosing' overhang for architectural finish.
    """
    treads, risers = [], []
    for i in range(steps):
        x0 = i * going
        z_tread_top = (i + 1) * rise
        # Tread: depth is going + nosing
        t = Box(going + nosing, width, tread_t,
                align=(Align.MIN, Align.MAX, Align.MAX))
        # Riser is at the back of the nosing
        treads.append(t.translate((x0 - nosing, 0, z_tread_top)))
        # Riser: vertical panel
        # Dropped by tread_t to meet the tread below, pushed back by riser_t
        r = Box(riser_t, width, rise,
                align=(Align.MIN, Align.MAX, Align.MIN))
        risers.append(r.translate((x0, 0, i * rise - tread_t if i > 0 else 0)))
    return treads, risers


def _make_stringer_solid(steps, going, rise, depth, thickness, tread_t=20.0, riser_t=20.0, nosing=20.0):
    """Build a single stringer solid entirely in one BuildPart context.
    
    OPTIMIZED: Uses extremely fast 2D Sketch Boolean subtraction to notch out
    the treads and risers BEFORE extruding into 3D.
    """
    length = steps * going
    top_z = steps * rise

    with BuildPart() as bp:
        with BuildSketch(Plane.XZ):
            # 1. Base Stringer Profile (Solid Sawtooth)
            with BuildLine():
                pts = [(0, -depth)]
                cx, cz = 0.0, 0.0
                for _ in range(steps):
                    pts.append((cx, cz + rise))
                    pts.append((cx + going, cz + rise))
                    cx += going
                    cz += rise
                pts.append((length, top_z - depth))
                pts.append((0, -depth))
                Polyline(pts)
            make_face()
            
            # 2. Subtract Treads & Risers in 2D
            with Locations((0, 0)):
                for i in range(steps):
                    x0 = i * going
                    z0 = i * rise
                    z_tread_top = (i + 1) * rise
                    
                    # Subtract Tread
                    # Recess into the stringer by exactly the tread thickness
                    with Locations((x0 - nosing + (going + nosing)/2, z_tread_top - tread_t/2)):
                        Rectangle(going + nosing, tread_t, mode=Mode.SUBTRACT)
                        
                    # Subtract Riser
                    # Recess into the stringer by exactly the riser thickness
                    # We drop the riser cutout slightly to meet the tread below
                    drop_z = tread_t if i > 0 else 0
                    cut_rise = rise + drop_z
                    with Locations((x0 + riser_t/2, z0 - drop_z + cut_rise/2)):
                        Rectangle(riser_t, cut_rise, mode=Mode.SUBTRACT)
                        
        # 3. Extrude the fully notched 2D profile into 3D
        extrude(amount=thickness)
    return bp.part


def _flight_stringers(steps, going, rise, width, str_depth, str_width, tread_t=20.0, riser_t=20.0, nosing=20.0):
    if steps <= 0: return []
    """Two wall-flush stringers for a straight flight.

    Plane.XZ extrudes in -Y, so inner stringer at Y=0..-str_width,
    outer stringer translated to the outer wall edge.
    """
    stringers = []
    # Inner stringer: at Y=0, extruded -Y → Y from 0 to -str_width
    inner = _make_stringer_solid(steps, going, rise, str_depth, str_width, tread_t, riser_t, nosing)
    stringers.append(inner)
    
    # User requested to REMOVE the outer stringer for straight flights and just
    # rely on the long outer stringer generated by the winder boolean intersection.
    # outer = _make_stringer_solid(steps, going, rise, str_depth, str_width, tread_t, riser_t, nosing)
    # stringers.append(outer.translate((0, -width, 0)))
    
    return stringers


def _flight_carriages(steps, going, rise, width, car_depth, car_width, tread_t=20.0, riser_t=20.0, nosing=20.0):
    if steps <= 0: return []
    """Width-dependent internal carriage beams (central stringers).

    Number of carriages scales with width: 1 per ~400mm clear span.
    Carriages sit above the soffit line (car_depth < waist).
    """
    n_carriages = max(1, round(width / 400) - 1)
    carriages = []
    for i in range(n_carriages):
        frac = (i + 1) / (n_carriages + 1)  # evenly spaced
        # Width extends in -Y: position at -width*frac, centre the carriage
        y_pos = -width * frac + car_width / 2
        c = _make_stringer_solid(steps, going, rise, car_depth, car_width, tread_t, riser_t, nosing)
        carriages.append(c.translate((0, y_pos, 0)))
    return carriages


def _flight_ribs(steps, going, rise, width, waist,
                 rib_spacing, rib_width, rib_depth):
    """Soffit ribs perpendicular to flight direction."""
    length = steps * going
    slope = rise / going
    n_ribs = max(2, int(length / rib_spacing) + 1)
    ribs = []
    for i in range(n_ribs):
        x = i * length / (n_ribs - 1) if n_ribs > 1 else 0
        z_soffit = x * slope - waist
        # Rib sits ABOVE soffit (supports plaster from inside staircase)
        rib = Box(rib_width, width, rib_depth,
                  align=(Align.CENTER, Align.MAX, Align.MIN))
        ribs.append(rib.translate((x, 0, z_soffit)))
    return ribs


# ===========================================================================
# WINDER ELEMENTS
# ===========================================================================

def _winder_treads_risers(num_steps, rise, winder_width, inner_r,
                          base_z, tread_t, riser_t, pivot_global, nosing=0.0):
    """Winder treads & risers with RECTANGULAR outer boundary.
    Includes 'nosing' overhang for architectural finish.
    """
    if num_steps <= 0: return [], []
    px, py = pivot_global
    treads, risers = [], []
    angle_per = 90.0 / num_steps

    for i in range(num_steps):
        z_top = base_z + (i + 1) * rise
        
        # --- Tread (thin wedge) ---
        # For nosing, we make the start angle of the tread slightly earlier
        # Approximation: shift angle by nosing distance at average radius
        avg_r = inner_r + winder_width / 2
        nosing_angle = math.degrees(nosing / avg_r)
        
        # We also need the tread to extend *backward* into the riser behind it 
        # to ensure they physically overlap/seal at the inner corner.
        riser_overlap_angle = math.degrees((riser_t / 2) / inner_r)
        
        sa = -90 + i * angle_per - nosing_angle
        ea = -90 + (i + 1) * angle_per + riser_overlap_angle
        
        # We need a modified polygon helper or just inline the logic for nosing
        # To keep it robust, we'll use the standard polygon but rotate the tread result
        poly = _winder_step_polygon(i, num_steps, winder_width)
        gpts = [(px + p[0], py + p[1]) for p in poly]
        
        with BuildPart() as bp:
            with BuildSketch(Plane.XY):
                with BuildLine():
                    Polyline(gpts)
                make_face()
            extrude(amount=tread_t)
            # Subtract inner void
            with Locations((px, py)):
                Cylinder(inner_r, tread_t * 3,
                         align=(Align.CENTER, Align.CENTER, Align.CENTER),
                         mode=Mode.SUBTRACT)
        
        # Rotate the tread slightly clockwise to create the nosing overhang
        tread_part = bp.part.rotate(Axis((px, py, 0), (0, 0, 1)), -nosing_angle)
        treads.append(tread_part.translate((0, 0, z_top - tread_t)))

        # --- Riser (thin panel at leading edge angle) ---
        riser_angle = -90 + i * angle_per
        a_rad = math.radians(riser_angle)
        # Radial line from inner_r to outer boundary
        if riser_angle < -45:
            if abs(riser_angle + 90) < 1e-6:
                r_outer = winder_width
            else:
                r_outer = abs(-winder_width / math.sin(a_rad))
        else:
            r_outer = abs(winder_width / math.cos(a_rad))
        radial_len = r_outer - inner_r
        # Let the riser drop by tread_t so it touches the tread below
        drop_z = tread_t if i > 0 else 0
        actual_rise = rise + drop_z
        
        # Build as thin box along the radial line
        riser = Box(radial_len, riser_t, actual_rise,
                    align=(Align.MIN, Align.CENTER, Align.MIN))
        riser = riser.translate((inner_r, 0, 0))
        riser = riser.rotate(Axis((0, 0, 0), (0, 0, 1)), riser_angle)
        risers.append(riser.translate((px, py, base_z + i * rise - drop_z)))

    return treads, risers


def _winder_ribs(num_steps, rise, winder_width, inner_r,
                 base_z, waist, rib_spacing, rib_width, rib_depth,
                 pivot_global):
    """Radially-fanned CNC-cut plywood soffit ribs for the winder.
    
    OPTIMIZED: The rib geometry is calculated exactly (clipped to the outer
    rectangular corner) so no 3D boolean intersection is needed later.
    """
    px, py = pivot_global
    arc_len = (inner_r + winder_width) / 2 * math.pi / 2
    n_ribs = max(3, int(arc_len / rib_spacing) + 1)
    ribs = []
    for i in range(n_ribs):
        t = i / (n_ribs - 1) if n_ribs > 1 else 0
        angle_deg = -90 + t * 90
        a_rad = math.radians(angle_deg)
        z_soffit = base_z + t * num_steps * rise - waist
        
        # Calculate exact radial length to the rectangular outer boundary
        if angle_deg < -45:
            if abs(angle_deg + 90) < 1e-6:
                r_outer = winder_width
            else:
                r_outer = abs(-winder_width / math.sin(a_rad))
        else:
            r_outer = abs(winder_width / math.cos(a_rad))
            
        radial_len = r_outer - inner_r
        
        rib = Box(radial_len, rib_width, rib_depth,
                  align=(Align.MIN, Align.CENTER, Align.MIN))
        rib = rib.translate((inner_r, 0, 0))
        rib = rib.rotate(Axis((0, 0, 0), (0, 0, 1)), angle_deg)
        ribs.append(rib.translate((px, py, z_soffit)))
    return ribs


def _winder_corner_stringers(volumetric, winder_width, str_width, pivot_global):
    """Stepped stringers at the winder's rectangular outer corner.

    Uses volumetric intersection: slice the full staircase solid with thin
    slabs at the outer boundary positions. This automatically produces
    correctly stepped profiles matching the winder geometry.
    """
    px, py = pivot_global
    bb = volumetric.bounding_box()
    z_span = bb.max.Z - bb.min.Z + 400
    z_mid  = (bb.max.Z + bb.min.Z) / 2
    stringers = []

    # Bottom edge stringer (parallel to X at outer Y = py - winder_width)
    bottom_slab = Box(winder_width * 10, str_width, z_span,
                      align=(Align.CENTER, Align.CENTER, Align.CENTER))
    bottom_slab = bottom_slab.translate(
        (px,
         py - winder_width + str_width / 2,
         z_mid))
    bottom_str = volumetric & bottom_slab
    if bottom_str.volume > 0:
        stringers.append(bottom_str)

    # Right edge stringer (parallel to Y at outer X = px + winder_width)
    right_slab = Box(str_width, winder_width * 10, z_span,
                     align=(Align.CENTER, Align.CENTER, Align.CENTER))
    right_slab = right_slab.translate(
        (px + winder_width - str_width / 2,
         py,
         z_mid))
    right_str = volumetric & right_slab
    if right_str.volume > 0:
        stringers.append(right_str)

    return stringers


# ===========================================================================
# PLASTER SOFFIT VIA BOOLEAN SUBTRACTION
# ===========================================================================# ===========================================================================
# MAIN ASSEMBLY
# ===========================================================================

def build_structural_staircase(config):
    """Build the full structural staircase as categorised element lists."""
    width    = config["width"]
    rise     = config["rise"]
    going    = config["going"]
    waist    = config["waist"]
    inner_r  = config["inner_r"]
    sb_steps = config["s_bottom_steps"]
    w_steps  = config["winder_steps"]
    st_steps = config["s_top_steps"]
    ext_top  = config["extend_top_flight"]
    tread_t  = config["tread_thickness"]
    riser_t  = config["riser_thickness"]
    str_w    = config["stringer_width"]
    str_d    = config["stringer_depth"]
    car_w    = config["carriage_width"]
    car_d    = config["carriage_depth"]
    rib_sp   = config["rib_spacing"]
    rib_w    = config["rib_width"]
    rib_d    = config["rib_depth"]

    winder_width  = width + inner_r
    sb_length     = sb_steps * going
    sb_top_z      = sb_steps * rise
    winder_base_z = sb_top_z
    winder_top_z  = winder_base_z + w_steps * rise
    st_base_z     = winder_top_z
    pivot_x       = sb_length
    pivot_y       = 0.0

    all_treads, all_risers = [], []
    all_stringers, all_carriages = [], []

    # -----------------------------------------------------------------------
    # 0. BUILD VOLUMETRIC REFERENCE (reused for winder stringers + plaster)
    # -----------------------------------------------------------------------
    print(f"  Building volumetric reference...")
    vol_config = config.copy()
    vol_config["unified_soffit"] = config.get("unified_soffit", True)
    
    vol_res = build_staircase(vol_config, return_cuts=True)
    if isinstance(vol_res, tuple) and len(vol_res) == 2:
        volumetric, soffit_cut = vol_res
    else:
        volumetric = vol_res
        soffit_cut = None

    if volumetric and not isinstance(volumetric, (Solid, Compound)):
        if hasattr(volumetric, "solids"):
            volumetric = Compound(children=volumetric.solids())
        else:
            volumetric = Compound(children=volumetric)

    # -----------------------------------------------------------------------
    # 1. BOTTOM FLIGHT  — +X, inner edge at Y=-inner_r
    # -----------------------------------------------------------------------
    print(f"  Bottom flight: {sb_steps} steps")
    t, r = _flight_treads_risers(sb_steps, going, rise, width, tread_t, riser_t, config.get("nosing", 0))
    # Translate: flight built at Y=0..width, need inner edge at Y=-inner_r
    off_sb = (0, -inner_r, 0)
    all_treads.extend([p.translate(off_sb) for p in t])
    all_risers.extend([p.translate(off_sb) for p in r])

    s = _flight_stringers(sb_steps, going, rise, width, str_d, str_w, tread_t, riser_t, config.get("nosing", 0))
    all_stringers.extend([p.translate(off_sb) for p in s])

    c = _flight_carriages(sb_steps, going, rise, width, car_d, car_w, tread_t, riser_t, config.get("nosing", 0))
    # Trim carriages to volumetric envelope (so they don't protrude below soffit)
    all_carriages.extend([p.translate(off_sb) for p in c])

    # -----------------------------------------------------------------------
    # 2. WINDER — pivot at (pivot_x, pivot_y)
    # -----------------------------------------------------------------------
    print(f"  Winder: {w_steps} steps")
    wt, wr = _winder_treads_risers(
        w_steps, rise, winder_width, inner_r,
        winder_base_z, tread_t, riser_t,
        pivot_global=(pivot_x, pivot_y),
        nosing=config.get("nosing", 0))
    all_treads.extend(wt)
    all_risers.extend(wr)

    # Winder corner stringers (sliced from volumetric → stepped profiles)
    ws = _winder_corner_stringers(
        volumetric, winder_width, str_w,
        pivot_global=(pivot_x, pivot_y))
    all_stringers.extend(ws)

    # -----------------------------------------------------------------------
    # 3. TOP FLIGHT — rotated 90°, inner edge at X=pivot_x+inner_r
    # -----------------------------------------------------------------------
    print(f"  Top flight: {st_steps} steps")
    t2, r2 = _flight_treads_risers(st_steps, going, rise, width, tread_t, riser_t, config.get("nosing", 0))
    s2 = _flight_stringers(st_steps, going, rise, width, str_d, str_w, tread_t, riser_t, config.get("nosing", 0))
    c2 = _flight_carriages(st_steps, going, rise, width, car_d, car_w, tread_t, riser_t, config.get("nosing", 0))

    def _rotate_translate(parts):
        return [p.rotate(Axis.Z, 90).translate((pivot_x + inner_r, 0, st_base_z))
                for p in parts]

    all_treads.extend(_rotate_translate(t2))
    all_risers.extend(_rotate_translate(r2))
    all_stringers.extend(_rotate_translate(s2))
    all_carriages.extend(_rotate_translate(c2))

    # -----------------------------------------------------------------------
    # 4. PLASTER SOFFIT (fast boolean intersection)
    # -----------------------------------------------------------------------
    print(f"  Building plaster shell (fast boolean intersection)...")
    plaster_t = config.get("plaster_thickness", 10.0)
    plaster = None
    if plaster_t > 0 and soffit_cut is not None:
        try:
            # The soffit_cut object represents the entire void mass underneath the stairs.
            # We lift it by plaster_t and intersect it with the staircase itself 
            # to extract a perfect slice of the bottom geometry.
            plaster_cut = soffit_cut.translate((0, 0, plaster_t))
            plaster_raw = volumetric & plaster_cut
            if plaster_raw and len(plaster_raw.solids()) > 0:
                plaster = plaster_raw
        except Exception as e:
            print(f"  [!] Failed to generate fast plaster shell: {e}")

    # -----------------------------------------------------------------------
    # 5. RECESS STRINGERS & CARRIAGES
    # -----------------------------------------------------------------------
    # Restore strict boolean containment to prevent stringers/carriages from
    # protruding through the plaster soffit at complex transitions (e.g. winder base).
    # We intersect with the volumetric model to guarantee they stay inside the envelope.
    print(f"  Trimming structural elements to volumetric envelope...")
    
    def _trim_to_envelope(parts, envelope, subtract_envelope=None):
        trimmed = []
        for p in parts:
            if not p or len(p.solids()) == 0: continue
            try:
                # Intersect with the overall volumetric envelope
                clipped = p & envelope
                
                # If there's a plaster envelope, subtract it so framing stays INSIDE the plaster layer
                if clipped and subtract_envelope and len(clipped.solids()) > 0:
                    try:
                        clipped = clipped - subtract_envelope
                    except Exception as sub_e:
                        print(f"    Warning: Plaster subtract failed: {sub_e}")

                if clipped and len(clipped.solids()) > 0:
                    trimmed.append(clipped)
                else:
                    trimmed.append(p)
            except Exception as e:
                print(f"    Warning: Boolean intersect failed on element: {e}")
                trimmed.append(p)
        return trimmed

    all_stringers = _trim_to_envelope(all_stringers, volumetric, subtract_envelope=plaster)
    all_carriages = _trim_to_envelope(all_carriages, volumetric, subtract_envelope=plaster)

    # -----------------------------------------------------------------------
    # 5.5 ROUTE OUTER STRINGERS
    # -----------------------------------------------------------------------
    # The winder corner stringers (which act as outer stringers for the whole stairs)
    # were sliced from the volumetric model, so they lacked the 20mm recesses for
    # the treads and risers. We physically boolean subtract all treads and risers
    # from the stringers to perfectly rout out their housing joints.
    print(f"  Routing stringer recesses via 3D boolean subtraction...")
    all_skin = all_treads + all_risers
    if all_skin:
        try:
            skin_compound = Compound(children=all_skin)
            routed_stringers = []
            for s in all_stringers:
                if not s or len(s.solids()) == 0: continue
                try:
                    routed_stringers.append(s - skin_compound)
                except Exception as e:
                    print(f"    Warning: Boolean subtract failed on stringer element: {e}")
                    routed_stringers.append(s)
            all_stringers = routed_stringers
        except Exception as e:
            print(f"  [!] Failed to build skin compound for routing: {e}")

    # Filter out empty geometry
    all_treads = [p for p in all_treads if p and len(p.solids()) > 0]
    all_risers = [p for p in all_risers if p and len(p.solids()) > 0]
    all_stringers = [p for p in all_stringers if p and len(p.solids()) > 0]
    all_carriages = [p for p in all_carriages if p and len(p.solids()) > 0]

    print(f"  Total: {len(all_treads)} treads, {len(all_risers)} risers, "
          f"{len(all_stringers)} stringers, {len(all_carriages)} carriages, "
          f"1 plaster shell")

    # -----------------------------------------------------------------------
    # 6. ARCHITECTURAL ELEMENTS (Handrail, Balusters, Walkline)
    # -----------------------------------------------------------------------
    print(f"  Building architectural suite...")
    handrail = build_handrail(config)
    balusters = build_balusters(config)
    walkline = build_walkline(config)

    return {
        "treads": all_treads,
        "risers": all_risers,
        "stringers": all_stringers,
        "carriages": all_carriages,
        "plaster": [plaster] if plaster else [],
        "handrail": [handrail] + balusters,
        "walkline": [walkline] if walkline else [],
    }


# ===========================================================================
# DISPLAY
# ===========================================================================

def display_structural(elements):
    """Show with skin at 50% alpha, structural at 100%."""
    parts, names, colours, alphas = [], [], [], []

    def _add(category, items, colour, alpha):
        for i, p in enumerate(items):
            parts.append(p)
            names.append(f"{category}_{i+1}")
            colours.append(colour)
            alphas.append(alpha)

    _add("tread",    elements["treads"],    C_TREAD,    0.5)
    _add("riser",    elements["risers"],    C_RISER,    0.5)
    _add("plaster",  elements["plaster"],   C_PLASTER,  0.5)
    _add("stringer", elements["stringers"], C_STRINGER, 1.0)
    _add("carriage", elements["carriages"], C_CARRIAGE, 1.0)
    _add("rib",      elements["ribs"],      C_RIB,      1.0)
    _add("handrail", elements["handrail"],  C_HANDRAIL, 1.0)

    show(*parts, names=names, colors=colours, alphas=alphas)
    n_skin = len(elements["treads"]) + len(elements["risers"]) + len(elements["plaster"])
    n_struct = len(elements["stringers"]) + len(elements["carriages"]) + len(elements["ribs"])
    print(f"Showing {len(parts)} objects ({n_skin} skin @ 50%, {n_struct} structural @ 100%)")


# ===========================================================================
# ENTRY POINT
# ===========================================================================

if __name__ == "__main__":
    set_port(3939)

    parser = argparse.ArgumentParser(description="Structural Staircase Builder")
    parser.add_argument("--mode", choices=["structural", "volumetric"],
                        default="structural")
    parser.add_argument("--width",        type=float, default=DEFAULT_CONFIG["width"])
    parser.add_argument("--rise",         type=float, default=DEFAULT_CONFIG["rise"])
    parser.add_argument("--going",        type=float, default=DEFAULT_CONFIG["going"])
    parser.add_argument("--steps_bottom", type=int,   default=DEFAULT_CONFIG["s_bottom_steps"])
    parser.add_argument("--steps_winder", type=int,   default=DEFAULT_CONFIG["winder_steps"])
    parser.add_argument("--steps_top",    type=int,   default=DEFAULT_CONFIG["s_top_steps"])
    parser.add_argument("--waist",        type=float, default=DEFAULT_CONFIG["waist"], help="Distance from soffit to inner stair corner")
    parser.add_argument("--no_unified_soffit", action="store_true")
    args = parser.parse_args()

    config = DEFAULT_CONFIG.copy()
    config.update({
        "width":          args.width,
        "rise":           args.rise,
        "going":          args.going,
        "s_bottom_steps": args.steps_bottom,
        "winder_steps":   args.steps_winder,
        "s_top_steps":    args.steps_top,
        "waist":          args.waist,
    })

    if args.mode == "volumetric":
        print("Mode: VOLUMETRIC")
        config["unified_soffit"] = not args.no_unified_soffit
        stair = build_staircase(config)
        show(stair, names=["Staircase (volumetric)"])
    else:
        print("Mode: STRUCTURAL")
        elements = build_structural_staircase(config)
        display_structural(elements)
