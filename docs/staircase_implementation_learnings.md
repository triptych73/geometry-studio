# Staircase Web App Implementation: Key Learnings & Retrospective

This document synthesizes the core learnings, pitfalls, and successful strategies discovered during the development of the Parametric Staircase Studio. It is designed to serve as a comprehensive reference for porting this project to new agent chats or expanding its capabilities.

---

## 1. What Worked Well (Best Practices)

### Architecture & Separation of Concerns
- **Decoupled Geometry & Assembly:** Moving from monolithic scripts to a structured approach worked flawlessly. `stair_helpers.py` handles the pure geometric math (the "engine"), while `staircase_assembled.py` (or the API) handles the configuration and orchestration. This separation made the code vastly easier for agents to reason about and test.
- **Server-Side Analytical Engine:** Offloading complex calculations (precise volume in cm³, exact bounding boxes, and 2D nesting profiles) to the Python backend (`build123d` / `rectpack`) rather than attempting them in the browser (Three.js) ensured physical accuracy and simplified the frontend.

### Frontend UI & User Experience
- **Object Tree & Raycasting:** Implementing a hierarchical object tree synchronized with Three.js raycasting selection provided a professional, CAD-like experience. 
- **Persisted State:** Using `localStorage` for UI panel states (e.g., minimizing the tree) greatly improved usability during iterative testing.
- **Dumb Frontend / Smart Backend Material Pipeline:** Refactoring the frontend to simply render standard WebGL materials—and shifting the burden of building those materials into the Python backend's GLTF post-processor—eliminated fragile name/index scanning in the JavaScript.

### Test-Driven Agent Development
- **Layered Test Architecture:** Creating a 3-tier testing strategy dramatically improved stability:
  1. **Geometry (`pytest` + `build123d`):** Fast, headless headless stress tests of pure math.
  2. **API (`httpx`):** Validating the FastAPI endpoints and JSON manifest integrity.
  3. **Browser (`pytest-playwright`):** Headless E2E tests validating the UI panels, object tree, and CNC nesting interactions.

---

## 2. Pitfalls & Mistakes to Avoid

### Geometry Engine (`build123d`) Quirks
- **API Hallucinations:** Agents frequently hallucinate `build123d` methods by mixing them with raw OpenCascade (OCCT) or CadQuery syntax. 
  - *Fix:* Always provide agents with strict, verified API patterns (e.g., `BuildSketch` -> `BuildLine` -> `Polyline` -> `make_face()`). Do not allow `Face.make_from_wires()` or `Shell.make_loft()`.
- **Extrude Direction Traps:** The default extrusion direction varies wildly depending on the working plane. For example, `Plane.XZ` extrudes in the `-Y` direction by default!
  - *Fix:* Explicitly define the extrusion direction or use negative amounts (e.g., `extrude(amount=-WIDTH)`) to force the correct vector.
- **Boolean Failures / Standard_TypeMismatch:** Complex Boolean operations (like sweeping a soffit) often crash due to inverted polygons or non-manifold geometry.
  - *Fix:* When building custom profiles via `Polyline`, ensure vertices are defined in a consistent winding order (typically counter-clockwise) to guarantee the face normal points outward.

### GLTF Export Disasters
- **The "Monolithic Mesh" Trap:** Exporting a `Compound` using `build123d.export_gltf` merged *all* objects into a single glTF Mesh where each individual *face* became a primitive. This completely broke frontend UI selection and styling, which expected a 1-to-1 mapping of 3D parts.
  - *Fix:* The backend MUST intercept the export. We had to write a post-processor in `api.py` that collects face counts per part (`len(p.faces())`), slices the monolithic primitives array, and rebuilds independent meshes and nodes within the GLTF JSON structure.
- **Lost Transparency & Colors:** The default OpenCascade GLTF writer drops assigned RGB colors and transparency settings (`alphaMode`, `baseColorFactor`). 
  - *Fix:* Our GLTF post-processor explicitly injects PBR materials (with `alphaMode="BLEND"` for transparent layers like plaster/treads) and maps them to the appropriate meshes during the slicing process.

---

## 3. Outstanding Issues & Areas for Resolution

While the core functionality is robust, a few areas require further refinement in future iterations:

- **Soffit Continuity at the Winder:** The transition between the straight flight soffits and the sweeping, ruled-surface soffit of the winder can occasionally exhibit microscopic gaps or "kinks" depending on the precise `waist` parameters. A more unified swept-surface approach that natively handles the C1 continuity across the entire path length is needed.
- **CNC Nesting Optimizations:** 
  - The current `rectpack` grouping is purely 2D bounding-box based. It doesn't perform true "true-shape" or outline nesting for complex polygons (like the curved winder treads or stringers), wasting sheet material.
  - Integration with a more advanced nesting algorithm (e.g., SVGNest or Deepnest logic) via a Python wrapper would massively improve sheet yield.
- **Newel Posts & Wall Mountings:** The structural model assumes the staircase is floating or seamlessly glued between two walls. Generating actual newel posts at the winder turn, as well as wall-stringer mounting brackets, would make the model fully ready for physical manufacturing.
- **AutoCAD Bundle Script Hardcoding:** The `import_staircase.lsp` currently relies on hardcoded pathing assumptions for the extracted zip. Making this more relative/robust would smooth out the CAD engineer's workflow.

---

## 4. How to Bootstrap a New Agent

When starting a new session or handing this off to a new agent, provide them with the **"Verified API Reference"** from the task packets:

1. Instruct them to review `stair_helpers.py` for acceptable `build123d` patterns.
2. Explicitly warn them about the GLTF monolithic mesh issue—any new 3D exports MUST pass through the `pack_glb` JSON injection pipeline in `api.py`.
3. Demand that any new endpoint or geometry feature include corresponding tests in `test_geometry.py` or `test_api.py` before touching the browser UI.
