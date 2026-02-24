# Knowledge Base: FastAPI + build123d + Three.js GLTF Bridge

> **Purpose:** Portable reference for any application that uses `build123d` to generate 3D geometry server-side and streams it to a Three.js browser viewer via a GLB/GLTF payload. Distilled from a full implementation cycle including all failures and the solutions that worked.

---

## 1. Architecture Overview

```
build123d (Python)   ──► export_gltf ──►  GLTF JSON + .bin
                                              │
                                  pack_glb (manual GLB assembly)
                                              │
                                    FastAPI (/generate endpoint)
                                              │
                               base64-encoded GLB in JSON response
                                              │
                             Three.js GLTFLoader in browser
                                              │
                           meshMap (index → [THREE.Mesh, ...])
```

---

## 2. build123d ↔ GLTF: Critical Facts & Gotchas

### 2.1 `export_gltf` Flattens Compound into a Single Mesh

> [!CAUTION]
> When you call `export_gltf(Compound(parts), path)`, the OCCT exporter produces **one glTF Mesh** with **N primitives**, where N is the **total number of topological faces** across all parts. There is no concept of "one mesh per solid" unless you post-process the JSON.

**Working solution:** After export, splice the flat primitive list back into per-part meshes using the face count of each part.

### 2.2 Face Counts Match Primitive Counts — Reliably

Diagnostic testing with `test_glb_structure.py` confirmed:
- `len(shape.faces())` → topological face count
- Each face produces exactly **one glTF primitive**
- Total glTF primitives == sum of all face counts

This is a stable invariant you can rely on for slicing.

### 2.3 Topological Order IS Preserved

> [!IMPORTANT]
> `Compound(all_parts)` preserves the **insertion order** of parts in the primitive array. Primitive 0–5 belong to `all_parts[0]`, 6–11 to `all_parts[1]`, etc. Confirmed by checking bounding box Z-ranges of each primitive in `spatial_results.json`.

Do **not** attempt to reorder or sort `all_parts` after building it without also reordering `part_face_counts`.

### 2.4 Do NOT Pass a List to `export_gltf`

```python
# ❌ WRONG — causes crash ("not a Shape")
export_gltf(all_parts, path)

# ✅ CORRECT
export_gltf(Compound(all_parts), path)
```

### 2.5 OCCT Node Names Are Cryptic — Don't Rely on Them

OCCT's native glTF node names look like `=>[0:1:1:4]`. They carry no semantic meaning from your Python code. You **must inject names** yourself after export.

Setting `.label` on a `build123d` shape does NOT propagate to glTF node names.

### 2.6 Native Assembly Export Produces Separate Meshes — But Unusable Names

Using `Compound(children=[...])` does produce one mesh per child (great!), but the node names are still OCCT internal strings. This approach is currently not viable without a name injection step on top.

---

## 3. Backend: pack_glb and _inject_materials_into_gltf Pattern

### 3.1 The GLB Packaging Function

`export_gltf` with `binary=False` produces two files: `file.gltf` (JSON) + `file.bin` (buffer). The standard pattern to produce a self-contained `.glb`:

```python
def pack_glb(gltf_path, category_counts=None, part_face_counts=None):
    with open(gltf_path, "r") as f:
        gltf_json = json.load(f)

    bin_path = gltf_path.rsplit(".", 1)[0] + ".bin"
    bin_data = b""
    if os.path.exists(bin_path):
        with open(bin_path, "rb") as f:
            bin_data = f.read()
        for buf in gltf_json.get("buffers", []):
            buf.pop("uri", None)
            buf["byteLength"] = len(bin_data)

    if category_counts and part_face_counts:
        _inject_materials_into_gltf(gltf_json, category_counts, part_face_counts)

    json_bytes = json.dumps(gltf_json, separators=(",", ":")).encode("utf-8")
    json_bytes += b" " * ((4 - len(json_bytes) % 4) % 4)
    bin_data  += b"\x00" * ((4 - len(bin_data)  % 4) % 4)

    total_length = 12 + 8 + len(json_bytes) + 8 + len(bin_data)
    glb = bytearray()
    glb += struct.pack("<I", 0x46546C67)  # magic
    glb += struct.pack("<I", 2)            # version
    glb += struct.pack("<I", total_length)
    glb += struct.pack("<I", len(json_bytes)); glb += struct.pack("<I", 0x4E4F534A)
    glb += json_bytes
    glb += struct.pack("<I", len(bin_data));  glb += struct.pack("<I", 0x004E4942)
    glb += bin_data
    return bytes(glb)
```

### 3.2 Splitting the Monolithic Mesh

```python
def _inject_materials_into_gltf(gltf_json, category_counts, part_face_counts):
    """
    category_counts: [(cat_name, part_count), ...]  — ordered like all_parts
    part_face_counts: [face_count_for_part_0, face_count_for_part_1, ...]
    """
    # Build materials array from your style definitions
    materials = []
    for cat_name, _ in category_counts:
        style = CATEGORY_STYLE[cat_name]
        r, g, b = style["color"]
        a = style["opacity"]
        mat = {"name": cat_name, "pbrMetallicRoughness": {"baseColorFactor": [r, g, b, a], "metallicFactor": 0.05, "roughnessFactor": 0.65}}
        if a < 1.0:
            mat["alphaMode"] = "BLEND"; mat["doubleSided"] = True
        materials.append(mat)
    gltf_json["materials"] = materials

    original_primitives = gltf_json["meshes"][0]["primitives"]
    new_meshes, new_nodes = [], []
    prim_idx, mat_idx, part_idx = 0, 0, 0

    for cat_name, count in category_counts:
        for _ in range(count):
            face_count = part_face_counts[part_idx]
            part_prims = original_primitives[prim_idx : prim_idx + face_count]
            for prim in part_prims:
                prim["material"] = mat_idx
            new_meshes.append({"primitives": part_prims, "name": f"mesh_{part_idx}"})
            new_nodes.append({"mesh": part_idx, "name": f"part_{part_idx}"})
            prim_idx += face_count
            part_idx += 1
        mat_idx += 1

    gltf_json["meshes"] = new_meshes
    gltf_json["nodes"] = new_nodes
    gltf_json["scenes"][0]["nodes"] = list(range(len(new_nodes)))
```

### 3.3 Generating face counts alongside the manifest

```python
all_parts = []
part_face_counts = []

for cat_name in CATEGORY_ORDER:
    parts = elements.get(cat_name, [])
    for p in parts:
        all_parts.append(p)
        part_face_counts.append(len(p.faces()))  # ← CRITICAL: same order

export_gltf(Compound(all_parts), gltf_path)
glb = pack_glb(gltf_path, category_counts=category_counts, part_face_counts=part_face_counts)
```

> [!WARNING]
> The order of `all_parts`, `part_face_counts`, and `manifest_categories` must all be identical. Any divergence causes misaligned part highlighting.

---

## 4. Frontend: Three.js GLTFLoader Mesh Mapping

### 4.1 The Core Problem

Three.js `GLTFLoader` creates a `THREE.Group` hierarchy for glTF. A single glTF Mesh with N primitives becomes N separate `THREE.Mesh` objects all under one `THREE.Object3D` parent. The parent gets the glTF node name (`part_X`), but the children typically **don't**.

### 4.2 Use Ancestor Search — Not Just Child Name

> [!IMPORTANT]
> Never assume `child.name` contains the part index. Walk **up the parent chain** until you find a `part_X` or `mesh_X` ancestor.

```javascript
const assignMesh = (child) => {
    if (!child.isMesh) return;
    if (!isStructural) return; // volumetric has a different path

    let index = -1;
    let current = child;
    while (current) {
        const cname = current.name || "";
        if (cname.startsWith("part_") || cname.startsWith("mesh_")) {
            index = parseInt(cname.split("_")[1], 10);
            break;
        }
        current = current.parent;
    }

    if (index >= 0) {
        if (!meshMap.has(index)) meshMap.set(index, []);
        meshMap.get(index).push(child);
    } else {
        console.warn("[GLTF] Unmapped mesh:", child.name);
    }
};

model.traverse(assignMesh);
```

### 4.3 meshMap Must Store Arrays

> [!CAUTION]
> Using `meshMap.set(index, child)` is **wrong** — it overwrites every mesh after the first. A solid with 6 faces will only have 1 face highlighted.

```javascript
// ❌ WRONG
meshMap.set(index, child);

// ✅ CORRECT
if (!meshMap.has(index)) meshMap.set(index, []);
meshMap.get(index).push(child);
```

### 4.4 Visibility and Highlighting Must Iterate Arrays

```javascript
function setVisible(index, visible) {
    const meshes = meshMap.get(index);
    if (!meshes) return;
    meshes.forEach(m => m.visible = visible);
}

function highlightMesh(index, active) {
    const meshes = meshMap.get(index);
    if (!meshes) return;
    meshes.forEach(m => {
        if (active) {
            m.userData.originalEmissive = m.material.emissive?.clone() ?? new THREE.Color(0, 0, 0);
            m.material.emissive = new THREE.Color(0x38bdf8);
            m.material.emissiveIntensity = 0.5;
        } else {
            m.material.emissive = m.userData.originalEmissive ?? new THREE.Color(0, 0, 0);
            m.material.emissiveIntensity = 0;
        }
    });
}
```

---

## 5. FastAPI Endpoint Pattern

```python
@app.post("/generate")
async def generate(config: StaircaseConfig):
    with tempfile.TemporaryDirectory() as tmpdir:
        gltf_path = os.path.join(tmpdir, "model.gltf")

        elements = build_structural_staircase(config.dict())

        all_parts, part_face_counts = [], []
        manifest_categories = []

        for cat_name in CATEGORY_ORDER:
            parts = elements.get(cat_name, [])
            cat_manifest = {"name": cat_name, "parts": []}
            for p in parts:
                all_parts.append(p)
                part_face_counts.append(len(p.faces()))
                cat_manifest["parts"].append({"mesh_index": len(all_parts) - 1, ...})
            manifest_categories.append(cat_manifest)

        if not all_parts:
            raise HTTPException(status_code=500, detail="No geometry produced")

        export_gltf(Compound(all_parts), gltf_path)

        category_counts = [(c["name"], len(c["parts"])) for c in manifest_categories]
        glb_bytes = pack_glb(gltf_path, category_counts=category_counts, part_face_counts=part_face_counts)

        return JSONResponse({
            "glb": base64.b64encode(glb_bytes).decode("ascii"),
            "manifest": {"categories": manifest_categories},
            "styles": CATEGORY_STYLE,
        })
```

---

## 6. Diagnostic Scripts

### 6.1 Verify primitive counts match face counts per part

```python
# test_glb_structure.py
for i, part in enumerate(all_parts):
    expected = len(part.faces())
    export_gltf(part, f"/tmp/part_{i}.glb", binary=True)
    with open(f"/tmp/part_{i}.glb", "rb") as f: b = f.read()
    cl, _ = struct.unpack("<II", b[12:20])
    j = json.loads(b[20:20+cl])
    actual = sum(len(m["primitives"]) for m in j["meshes"])
    if actual != expected:
        print(f"MISMATCH part {i}: faces={expected}, prims={actual}")
```

### 6.2 Verify spatial ordering of primitives

```python
# test_order_spatial.py — confirms topological order = spatial order
b1 = Box(10, 10, 10)          # Z near 0
b2 = Box(10, 10, 10).translate((0, 0, 100))  # Z near 100

export_gltf(Compound([b1, b2]), "/tmp/order_test.glb", binary=True)
# Read glTF JSON, check pos accessors[min][2] for each primitive
# Expected: prims 0-5 at Z≈0, prims 6-11 at Z≈100 ✓
```

### 6.3 Inspect a live GLB in Python

```python
# inspect_gltf.py
with open("model.glb", "rb") as f: b = f.read()
cl, _ = struct.unpack("<II", b[12:20])
j = json.loads(b[20:20+cl])
print(f"Meshes: {len(j['meshes'])}, Nodes: {len(j['nodes'])}")
for i, node in enumerate(j["nodes"][:5]):
    print(f"  Node {i}: name={node.get('name')}, mesh={node.get('mesh')}")
```

---

## 7. Material Configuration Pattern

```python
CATEGORY_STYLE = {
    "treads":    {"color": [0.8, 0.6, 0.3], "opacity": 0.5},
    "risers":    {"color": [0.7, 0.7, 0.7], "opacity": 0.5},
    "plaster":   {"color": [0.9, 0.9, 0.8], "opacity": 0.5},
    "stringers": {"color": [0.4, 0.4, 0.6], "opacity": 1.0},
}
```

- **Opacity < 1.0** → set `alphaMode: "BLEND"` and `doubleSided: true` in the glTF material.
- In Three.js, set `material.transparent = material.opacity < 1.0` and optionally `material.depthWrite = false` for translucent surfaces.

---

## 8. Critical Checklist for New Projects

| # | Check | Notes |
|---|-------|-------|
| 1 | `all_parts` list order matches `part_face_counts` order | Any divergence breaks mapping |
| 2 | Face counts computed **after** geometry finalization | Boolean ops can change face count |
| 3 | `export_gltf(Compound(all_parts), path)` — not a list | List arg crashes |
| 4 | `pack_glb` removes `uri` from buffers before GLB assembly | Otherwise GLB is invalid |
| 5 | `meshMap` stores arrays, not single meshes | Multiple primitives per part |
| 6 | Ancestor search in `traverse` callback | Child.name may be empty |
| 7 | Transparency parts get `depthWrite = false` in Three.js | Prevents z-fighting |
| 8 | `scenes[0].nodes` updated after injecting new nodes | Avoids orphaned scene nodes |

---

## 9. Common Failure Modes

| Symptom | Root Cause | Fix |
|---------|-----------|-----|
| Only top/bottom face highlights | `meshMap` stores single mesh (overwrites) | Use array: `meshMap.set(idx, [])` → `.push()` |
| Wrong part highlights | `all_parts` order ≠ `part_face_counts` order | Ensure both built in one loop |
| Half the model invisible | `scenes[0].nodes` not updated after node injection | Set `scenes[0].nodes = range(len(new_nodes))` |
| API crash on generate | Passing list to `export_gltf` | Wrap with `Compound(all_parts)` |
| No material colours | `category_counts` miscount | Count parts AFTER filtering out empty geometries |
| Transparent objects z-fighting | `depthWrite = true` on transparent materials | Set `material.depthWrite = false` |
