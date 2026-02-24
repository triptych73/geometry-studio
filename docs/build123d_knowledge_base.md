# build123d — Essential Knowledge Base for AI Agents

> **Purpose**: Hard-won lessons, critical gotchas, and battle-tested patterns from building complex parametric 3D models (staircases) with `build123d`. Written so that any AI agent can hit the ground running without repeating our mistakes.

---

## 1. Core Architecture

`build123d` is a Python BREP (Boundary Representation) CAD framework using **context managers** ("Builder mode") or **algebraic operators** ("Algebra mode").

### Builder Mode (preferred for complex models)
```python
from build123d import *

with BuildPart() as bp:                # 3D builder
    with BuildSketch(Plane.XZ):        # 2D profile on a plane
        with BuildLine():              # 1D path
            Polyline([(0,0), (10,0), (10,10), (0,0)])
        make_face()                    # close wire → face
    extrude(amount=5)                  # face → solid
result = bp.part                       # access the Part
```

### Algebra Mode (good for quick one-liners)
```python
base = Box(10, 20, 5)
hole = Cylinder(3, 5)
result = base - hole                   # boolean subtraction
result = base & hole                   # boolean intersection
result = base + hole                   # fuse
```

---

## 2. Critical Gotchas (Things That WILL Bite You)

### 2.1 ⚠️ Plane.XZ Extrusion Direction is -Y

**The single biggest source of bugs in our project.**

When you build a sketch on `Plane.XZ` and call `extrude(amount=positive)`, the extrusion goes in the **-Y direction** (not +Y). This is because `Plane.XZ`'s normal points in -Y.

```python
# WRONG mental model: "extrude(amount=width) goes +Y"
# CORRECT: extrude(amount=width) goes -Y, from Y=0 to Y=-width

with BuildPart() as bp:
    with BuildSketch(Plane.XZ):
        Rectangle(100, 50)
    extrude(amount=800)   # Goes from Y=0 to Y=-800
```

**Consequences:**
- Stringer at "inner edge" (Y=0) that extrudes into the staircase body extrudes towards -Y ✓
- Stringer at "outer edge" needs to be translated to `Y = -width + thickness`
- All Y alignment on `Plane.XZ`-extruded `Box()` objects should use `Align.MAX` (not `Align.MIN`) to extend in -Y

```python
# CORRECT: Box extending in -Y from origin
box = Box(going, width, thickness,
          align=(Align.MIN, Align.MAX, Align.MAX))
# Y goes from 0 (MAX) to -width (MIN)
```

### 2.2 ⚠️ Sketch Context is Lost When Extracted

**Another major bug source.** If you build a sketch in one `BuildSketch` context, extract it via `sk.sketch`, and then `add()` it to a different `BuildPart`, the **plane information is lost**. The extrusion may happen in an unexpected direction (typically defaulting to Z instead of Y), producing zero-width or misplaced geometry.

```python
# ❌ BROKEN: sketch loses Plane.XZ orientation
def make_profile():
    with BuildSketch(Plane.XZ) as sk:
        with BuildLine():
            Polyline(pts)
        make_face()
    return sk.sketch                    # plane info lost!

with BuildPart() as bp:
    add(make_profile())                 # adds sketch, but plane is gone
    extrude(amount=50)                  # may extrude in Z instead of Y → zero width!
```

```python
# ✅ CORRECT: build everything in one BuildPart context
def make_solid(thickness):
    with BuildPart() as bp:
        with BuildSketch(Plane.XZ):
            with BuildLine():
                Polyline(pts)
            make_face()
        extrude(amount=thickness)       # plane info preserved → extrudes in -Y
    return bp.part
```

**Rule:** Always keep `BuildSketch` + `extrude` in the same `BuildPart` context.

### 2.3 ⚠️ Align Semantics

`Align.MIN`, `Align.CENTER`, `Align.MAX` control which edge of a primitive sits at the origin on each axis:

| Align | Meaning |
|-------|---------|
| `Align.MIN` | Minimum coordinate edge at origin → object extends in +direction |
| `Align.CENTER` | Center at origin → object extends ±½ in both directions |
| `Align.MAX` | Maximum coordinate edge at origin → object extends in -direction |

**With Plane.XZ (-Y extrusion):**
- Use `Align.MAX` on Y to make the box extend from Y=0 into -Y
- Use `Align.MIN` on Z to make the box extend upward from a reference point
- Use `Align.MAX` on Z to make the box extend downward from a reference point

```python
# Rib that sits ABOVE the soffit line, extending upward:
rib = Box(18, width, 100,
          align=(Align.CENTER, Align.MAX, Align.MIN))
rib = rib.translate((x, 0, z_soffit))
# Z goes from z_soffit (MIN) upward to z_soffit+100 (MAX) ✓

# ❌ WRONG: Align.MAX on Z makes it extend BELOW the soffit
rib = Box(18, width, 100,
          align=(Align.CENTER, Align.MAX, Align.MAX))
# Z goes from z_soffit-100 to z_soffit → hangs below soffit!
```

### 2.4 ⚠️ Boolean Operations Can Be Very Slow

Complex boolean operations (intersection, subtraction) on BREP geometry are expensive. A single `Part & Part` operation on a complex staircase takes 10-30 seconds. If you need to do many (e.g., trimming 20 elements), it can take several minutes.

**Optimisations:**
1. **Build the volumetric reference once** and reuse it for all operations
2. **Use `Compound`** to batch objects before subtracting: `compound = Compound(list_of_parts)` then `result = stringer - compound`
3. **Avoid unnecessary booleans** — simple placement with `translate()` is instant

### 2.5 ⚠️ Polyline Must Be Closed for make_face()

`make_face()` requires a closed wire. Ensure your `Polyline` returns to the start point:

```python
# ✅ Closed polyline
Polyline([(0, 0), (10, 0), (10, 10), (0, 0)])

# ❌ Open polyline → make_face() will fail or produce unexpected results
Polyline([(0, 0), (10, 0), (10, 10)])
```

---

## 3. Proven Patterns

### 3.1 Sawtooth Stringer Profile

A universal pattern for staircase stringers, carriages, or any stepped beam:

```python
def make_stringer_solid(steps, going, rise, depth, thickness):
    """Profile on XZ plane, extruded in -Y by thickness."""
    length = steps * going
    top_z = steps * rise

    with BuildPart() as bp:
        with BuildSketch(Plane.XZ):
            with BuildLine():
                pts = [(0, -depth)]           # bottom-left
                cx, cz = 0.0, 0.0
                for _ in range(steps):
                    pts.append((cx, cz + rise))
                    pts.append((cx + going, cz + rise))
                    cx += going
                    cz += rise
                pts.append((length, top_z - depth))  # bottom-right (raked)
                pts.append((0, -depth))               # close
                Polyline(pts)
            make_face()
        extrude(amount=thickness)
    return bp.part
```

### 3.2 Volumetric Intersection for Trimming

When structural elements must not protrude below a curved soffit, intersect them with the volumetric staircase envelope:

```python
# Build volumetric model once
volumetric = build_staircase(config)

# Trim all structural elements
stringers = [(s & volumetric) for s in stringers]
carriages = [(c & volumetric) for c in carriages]
ribs      = [(r & volumetric) for r in ribs]
```

This is also perfect for creating **stepped corner stringers** at complex winder junctions — just slice the volumetric model with a thin slab:

```python
# Slice volumetric model at outer edge to get stepped stringer
slab = Box(x_span, stringer_width, z_span,
           align=(Align.CENTER, Align.CENTER, Align.CENTER))
slab = slab.translate((center_x, outer_y, center_z))
corner_stringer = volumetric & slab
```

### 3.3 Shell via Boolean Subtraction

Create thin-walled shells (e.g., plaster soffit) by subtracting a slightly smaller version of the same shape:

```python
def build_shell(config, shell_thickness=10.0):
    # Outer surface (full waist)
    outer = build_staircase(config)

    # Inner surface (waist reduced)
    inner_config = config.copy()
    inner_config["waist"] = config["waist"] - shell_thickness
    inner = build_staircase(inner_config)

    shell = outer - inner  # thin shell!
    return shell
```

### 3.4 Recessing Stringers Under Treads

Subtract the combined treads and risers from stringers to create notched housing joints:

```python
# Combine all treads + risers into one compound for efficient subtraction
tr_compound = Compound(all_treads + all_risers)
all_stringers = [(s - tr_compound) for s in all_stringers]
```

### 3.5 Width-Dependent Element Count

Scale internal structural elements based on staircase width:

```python
n_carriages = max(1, round(width / 400) - 1)
for i in range(n_carriages):
    frac = (i + 1) / (n_carriages + 1)  # evenly spaced
    y_pos = -width * frac + car_width / 2
    # build and position carriage...
```

### 3.6 Winder Polygon with Rectangular Outer Boundary

Winder step polygons must have a **rectangular** outer boundary (not arc-based). Each polygon is a wedge from the pivot to the rectangular boundary:

```python
def winder_step_polygon(step_idx, num_steps, winder_width):
    """XY polygon for one winder step. Outer boundary is rectangular."""
    angle_per = 90.0 / num_steps
    sa = -90 + step_idx * angle_per      # start angle
    ea = -90 + (step_idx + 1) * angle_per  # end angle
    w = winder_width

    # Boundary intersection for start angle
    if sa < -45:
        p1 = (0, -w) if abs(sa + 90) < 1e-6 else (-w / math.tan(math.radians(sa)), -w)
    else:
        p1 = (w, w * math.tan(math.radians(sa)))

    # Boundary intersection for end angle
    if ea <= -45:
        p2 = (w, -w) if abs(ea + 45) < 1e-6 else (-w / math.tan(math.radians(ea)), -w)
    else:
        p2 = (w, w * math.tan(math.radians(ea)))

    pts = [(0, 0), p1]
    if sa < -45 and ea > -45:
        pts.append((w, -w))  # add the corner point
    pts.append(p2)
    pts.append((0, 0))
    return pts
```

### 3.7 Unified Soffit (Smooth Curve Across Junctions)

Per-component soffit cuts leave kinks where flights meet the winder. The solution is a **unified RuledSurface** that spans the entire staircase:

```python
# Build inner/outer spline control points along the soffit path
inner_pts = [...]  # curved arc at inner radius
outer_pts = [...]  # square corner at outer boundary

# Create splines
with BuildLine() as inner_path:
    Spline(inner_pts)
with BuildLine() as outer_path:
    Spline(outer_pts)

# RuledSurface between the two curves
soffit_face = Face.make_surface_from_curves(
    inner_path.edges()[0], outer_path.edges()[0])

# Extrude downward to create cutting volume
soffit_cut = extrude(soffit_face, amount=3000, dir=(0, 0, -1))
result = staircase_solid - soffit_cut
```

---

## 4. Coordinate System Conventions

Our staircase uses these axes consistently:

| Axis | Direction in Bottom Flight | Direction in Top Flight (after 90° rotation) |
|------|---------------------------|----------------------------------------------|
| **X** | Along flight (+X = uphill) | Perpendicular to flight |
| **Y** | Width (-Y = into staircase from inner edge) | Along flight (+Y = uphill) |
| **Z** | Height (+Z = up) | Height (+Z = up) |

**Key positions:**
- Pivot (winder center): `(sb_steps * going, 0, 0)`
- Winder width: `flight_width + inner_radius`
- Top flight origin: `(pivot_x + inner_r, 0, winder_top_z)` after 90° Z-rotation

---

## 5. Visualisation with ocp_vscode

```python
from ocp_vscode import show, set_port

set_port(3939)

# Show with labels, colours, and transparency
show(*parts,
     names=["tread_1", "stringer_1", ...],
     colors=[(0.72, 0.52, 0.30), ...],     # RGB tuples
     alphas=[0.5, 1.0, ...])               # 0.5 = 50% transparent
```

**Tips:**
- Use transparency (`alpha=0.5`) for "skin" elements (treads, risers, plaster) and full opacity (`alpha=1.0`) for structural elements
- Category-based colouring makes complex models navigable
- `set_port(3939)` must match the OCP viewer port in VS Code

---

## 6. Common Errors and Their Fixes

| Symptom | Cause | Fix |
|---------|-------|-----|
| Elements have **zero width** | Sketch plane context lost during `add()` | Build sketch + extrude in one `BuildPart` (§2.2) |
| Elements **extend wrong way** on Y | `Plane.XZ` extrudes in -Y | Use `Align.MAX` on Y axis (§2.1) |
| Ribs/structure **below soffit** | Wrong Z alignment direction | `Align.MIN` = extends up, `Align.MAX` = extends down (§2.3) |
| Structure **protrudes below plaster** | Element not clipped to envelope | Intersect with volumetric model: `elem & volumetric` (§3.2) |
| Soffit has **kink at winder junction** | Per-component soffit cuts don't align | Use unified RuledSurface spline soffit (§3.7) |
| Winder has **rounded outer edge** | Using arc/circle for boundary | Use rectangular boundary intersection (§3.6) |
| Boolean operation **very slow** | Complex geometry intersection | Build compound once, reuse; minimise operations (§2.4) |
| `make_face()` **fails silently** | Polyline not closed | Ensure last point = first point (§2.5) |

---

## 7. Project Structure Pattern

```
geometry_studio/
├── stair_helpers.py              # Pure geometry: make_flight(), make_winder()
├── staircase_parametric.py       # Volumetric assembly + unified soffit
├── staircase_structural.py       # Construction-level decomposition
├── build123d_redux.md            # API quick-reference
├── docs/
│   └── build123d_knowledge_base.md   # This file
└── web/                          # Web viewer (Three.js)
```

**Design principles:**
1. **Helpers are pure geometry** — no display logic, no config parsing
2. **Parametric builds the envelope** — used as reference for both display and boolean operations
3. **Structural decomposes into real elements** — uses parametric as a "cookie cutter" via boolean intersection
4. **Config is a flat dict** — easily serialisable, CLI-overridable, extensible

---

## 8. Performance Considerations

| Operation | Typical Time | Notes |
|-----------|-------------|-------|
| Simple `Box`/`Cylinder` creation | <1ms | Instant |
| `BuildSketch` + `extrude` | 5-50ms | Fast |
| Single boolean (`&`, `-`, `+`) | 1-30s | Depends on complexity |
| 20× boolean intersections | 2-10min | Batch with `Compound` where possible |
| `build_staircase()` (full) | 5-15s | Cache result, build once |
| `Face.make_surface_from_curves()` | 1-5s | RuledSurface creation |

**Key rule:** Build the volumetric reference model **once** and pass it to all functions that need it, rather than rebuilding it multiple times.

---

## 9. Checklist for New Staircase Features

When adding a new element type:

- [ ] Which `Plane` are you sketching on? Remember `Plane.XZ` extrudes in -Y
- [ ] Are you using `Align.MAX` on Y for -Y extension?
- [ ] Is your `Polyline` closed (last point = first point)?
- [ ] Is sketch + extrude in the **same** `BuildPart` context?
- [ ] Does the element need trimming to the soffit envelope (`& volumetric`)?
- [ ] Does it need recessing for treads/risers (`- tr_compound`)?
- [ ] Have you translated to the correct global position?
- [ ] For winder elements: are you using the rectangular outer boundary?
- [ ] Is the element count parametric (width-dependent)?

---

## Appendix A: Complete build123d API Reference

> All classes, objects, and operations available in `from build123d import *`, extracted from the official documentation.

---

### A.1 Builders (Context Managers)

| Builder | Purpose | Output Property |
|---------|---------|-----------------|
| `BuildPart(*workplanes)` | 3D solid modelling | `.part` |
| `BuildSketch(*workplanes)` | 2D profile/face construction | `.sketch` |
| `BuildLine(*workplanes)` | 1D wire/edge construction | `.line` |

---

### A.2 1D Objects (Curves) — used inside `BuildLine`

| Class | Description |
|-------|-------------|
| `Airfoil` | NACA 4-digit airfoil profile |
| `ArcArcTangentArc` | Arc tangent to two other arcs |
| `ArcArcTangentLine` | Line tangent to two arcs |
| `Bezier` | Bézier curve from control points and optional weights |
| `BlendCurve` | Curve blending curvature of two existing curves |
| `CenterArc` | Arc defined by center, radius, start angle, end angle |
| `DoubleTangentArc` | Arc tangent to a point/tangent pair and another curve |
| `EllipticalCenterArc` | Elliptical arc from center, radii, and angles |
| `FilletPolyline` | Polyline with filleted (rounded) corners |
| `Helix` | Helical spiral defined by pitch, radius, height |
| `HyperbolicCenterArc` | Hyperbolic arc from center, radii, and angles |
| `IntersectingLine` | Line from start point in a direction, intersecting another line |
| `JernArc` | Arc defined by start point, tangent, and end point |
| `Line` | Straight line segment between two points |
| `ParabolicCenterArc` | Parabolic arc from vertex, focal length, and angles |
| `PointArcTangentArc` | Arc through a point, tangent to another arc |
| `PointArcTangentLine` | Line through a point, tangent to an arc |
| `PolarLine` | Line from start point using length and angle |
| `Polyline` | Connected line segments through a list of points |
| `RadiusArc` | Arc through two points with a given radius |
| `SagittaArc` | Arc through two points with a given sagitta (height) |
| `Spline` | Smooth B-spline curve through control points |
| `TangentArc` | Arc tangent to the previous line segment |
| `ThreePointArc` | Arc through three points |

---

### A.3 2D Objects (Sketches) — used inside `BuildSketch`

| Class | Description |
|-------|-------------|
| `Circle` | Circle from radius |
| `Ellipse` | Ellipse from major/minor radii |
| `Polygon` | Regular or irregular polygon |
| `Rectangle` | Rectangle from width and height |
| `RectangleRounded` | Rectangle with rounded corners |
| `RegularPolygon` | Regular n-sided polygon from radius |
| `SlotArc` | Arc-shaped slot |
| `SlotCenterPoint` | Slot defined by center and point |
| `SlotCenterToCenter` | Slot defined by two center points |
| `SlotOverall` | Slot defined by overall dimensions |
| `Text` | Text rendered as 2D geometry |
| `Trapezoid` | Trapezoid from widths and height |
| `Triangle` | Triangle from side lengths or points |

---

### A.4 3D Objects (Parts) — used inside `BuildPart`

| Class | Description |
|-------|-------------|
| `Box` | Rectangular prism from length, width, height |
| `Cone` | Cone from bottom radius, top radius, height |
| `ConvexPolyhedron` | Convex hull of 3D points |
| `CounterBoreHole` | Hole with counterbore |
| `CounterSinkHole` | Hole with countersink |
| `Cylinder` | Cylinder from radius and height |
| `Hole` | Simple through-hole |
| `Sphere` | Sphere from radius |
| `Torus` | Torus from major and minor radii |
| `Wedge` | Wedge (tapered box) |

---

### A.5 Operations

#### Generic Operations (work on Part, Sketch, or Line)

| Function | Description |
|----------|-------------|
| `add` | Add shapes to the current builder |
| `bounding_box` | Get or create bounding box |
| `chamfer` | Chamfer edges by length |
| `fillet` | Fillet (round) edges by radius |
| `mirror` | Mirror about a plane |
| `offset` | Offset faces/edges by distance |
| `project` | Project geometry onto a plane or face |
| `scale` | Scale uniformly or per-axis |
| `split` | Split a shape with a plane |
| `sweep` | Sweep a profile along a path |

#### Part Operations (3D-specific)

| Function | Description |
|----------|-------------|
| `draft` | Apply draft angle to faces |
| `extrude` | Extrude a 2D face into 3D (key params: `amount`, `dir`, `mode`) |
| `loft` | Loft between multiple cross-section profiles |
| `make_brake_formed` | Create brake-formed sheet metal |
| `project_workplane` | Project a workplane onto a shape |
| `revolve` | Revolve a 2D profile around an axis |
| `section` | Create a cross-section at a plane |
| `thicken` | Thicken a face into a solid |

#### Sketch Operations (2D-specific)

| Function | Description |
|----------|-------------|
| `full_round` | Create a full-round fillet between two edges |
| `make_face` | Convert a closed wire into a face (**wire must be closed!**) |
| `make_hull` | Create a convex hull of 2D shapes |
| `trace` | Trace a wire with a circular cross-section |

---

### A.6 Topology Classes

| Class | Description |
|-------|-------------|
| `Vertex` | 0D point |
| `Edge` | 1D curve/line segment |
| `Wire` | 1D connected sequence of edges |
| `Face` | 2D surface (key methods: `.make_surface_from_curves()`, `.make_gordon_surface()`) |
| `Shell` | Collection of connected faces |
| `Solid` | 3D enclosed volume |
| `Part` | A solid with additional metadata |
| `Sketch` | A 2D collection of faces |
| `Curve` | A 1D collection of edges |
| `Compound` | Collection of any shapes |
| `Shape` | Base class for all topology |
| `ShapeList` | Extended list with selector methods (`.sort_by()`, `.filter_by()`, `.group_by()`) |
| `Joint` | Connection point between parts |

---

### A.7 Location & Placement Contexts

| Class | Description |
|-------|-------------|
| `Locations` | Place geometry at specific points |
| `GridLocations` | Grid of placement points (x_spacing, y_spacing, x_count, y_count) |
| `PolarLocations` | Circular arrangement of points (radius, count) |
| `HexLocations` | Hexagonal packing arrangement |
| `Pos` | Shorthand position: `Pos(x, y, z)` (Algebra mode) |
| `Rot` | Shorthand rotation: `Rot(rx, ry, rz)` (Algebra mode) |
| `Location` | Full 6-DOF placement: `Location(position, orientation)` |
| `Rotation` | Rotation transform: `Rotation(rx, ry, rz)` |

---

### A.8 Planes & Axes

| Constant | Normal Direction | Sketch Axes |
|----------|-----------------|-------------|
| `Plane.XY` | +Z | X right, Y up |
| `Plane.XZ` | **-Y** ⚠️ | X right, Z up |
| `Plane.YZ` | +X | Y right, Z up |
| `Plane.YX` | -Z | Y right, X up |
| `Plane.ZX` | +Y | Z right, X up |
| `Plane.ZY` | -X | Z right, Y up |
| `Axis.X` / `Axis.Y` / `Axis.Z` | Standard axes for rotation, sorting, filtering |

---

### A.9 Selectors & Filters

```python
# Selector methods on ShapeList
shape.vertices()          # all vertices
shape.edges()             # all edges
shape.faces()             # all faces
shape.solids()            # all solids

# Sort, filter, group
.sort_by(Axis.Z)          # sort by position on an axis
.filter_by(GeomType.PLANE)# filter by geometry type
.group_by(Axis.X)         # group by position on an axis

# Operator shortcuts
faces() > Axis.Z          # sort ascending, equivalent to .sort_by(Axis.Z)
faces() < Axis.Z          # sort descending
faces() >> Axis.X         # group_by, return last group
faces() << Axis.X         # group_by, return first group
faces() | GeomType.CYLINDER  # filter_by geometry type

# Select.LAST — edges/faces from the most recent operation
edges(Select.LAST)
```

---

### A.10 Importers & Exporters

| Function | Description |
|----------|-------------|
| `import_brep` | Import BREP file |
| `import_step` | Import STEP file |
| `import_stl` | Import STL mesh |
| `import_svg` | Import SVG as curves |
| `import_svg_as_buildline_code` | Convert SVG to build123d Python code |
| `export_brep` | Export as BREP |
| `export_step` | Export as STEP |
| `export_stl` | Export as STL mesh |
| `export_gltf` | Export as glTF/GLB (3D web viewer format) |
| `ExportSVG` | Export 2D technical drawings as SVG |

---

### A.11 Enums

| Enum | Values |
|------|--------|
| `Align` | `MIN`, `CENTER`, `MAX` |
| `Mode` | `ADD`, `SUBTRACT`, `INTERSECT`, `REPLACE`, `PRIVATE` |
| `Select` | `ALL`, `LAST` |
| `GeomType` | `BEZIER`, `BSPLINE`, `CIRCLE`, `CONE`, `CYLINDER`, `ELLIPSE`, `EXTRUSION`, `HYPERBOLA`, `LINE`, `OFFSET`, `OTHER`, `PARABOLA`, `PLANE`, `REVOLUTION`, `SPHERE`, `TORUS` |
| `SortBy` | `LENGTH`, `RADIUS`, `AREA`, `VOLUME`, `DISTANCE` |
| `Unit` | `MM`, `CM`, `M`, `IN`, `FT` |

---

### A.12 Key Shape Methods

```python
# Transformations
shape.translate((x, y, z))      # move
shape.rotate(Axis.Z, degrees)   # rotate around axis
shape.mirror(Plane.XZ)          # mirror
shape.fuse(other)               # boolean union (also: shape + other)
shape.cut(other)                # boolean subtraction (also: shape - other)
shape.intersect(other)          # boolean intersection (also: shape & other)

# Queries
shape.bounding_box()            # returns BoundBox with .min, .max, .size
shape.volume                    # volume in mm³
shape.area                      # surface area in mm²
shape.center()                  # center of mass

# Face-specific
Face.make_surface_from_curves(edge1, edge2)  # RuledSurface between two curves
Face.make_gordon_surface(profiles, guides)   # Gordon surface from profile/guide curves

# Edge-specific
edge @ 0.5                      # point at parameter (0.0 to 1.0)
edge % 0.5                      # tangent vector at parameter
```
