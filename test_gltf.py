import json
from build123d import *
from staircase_structural import build_structural_staircase
from api import CATEGORY_ORDER

config = {'model_type': 'structural', 'width': 900, 'rise': 2600, 'going': 250, 'inner_r': 100, 's_bottom_steps': 3, 'winder_steps': 3, 's_top_steps': 8, 'nosing': 20, 'tread_thickness': 20, 'riser_thickness': 20, 'stringer_width': 50, 'carriage_width': 50, 'unified_soffit': True, 'extend_top_flight': 300, 'waist': 150}
elements = build_structural_staircase(config)
all_parts = []
part_face_counts = []
for cat in CATEGORY_ORDER:
    parts = elements.get(cat, [])
    all_parts.extend(parts)
    part_face_counts.extend([len(p.faces()) for p in parts])

comp = Compound(all_parts)
comp.export_gltf('test.gltf')

with open('test.gltf') as f:
    j = json.load(f)

meshes = j.get('meshes', [])
if not meshes:
    print("No meshes")
else:
    prims = meshes[0].get('primitives', [])
    print(f"Total primitives in test.gltf: {len(prims)}")
    print(f"Total TopoDS faces: {sum(part_face_counts)}")
    print(f"Total distinct parts: {len(all_parts)}")
