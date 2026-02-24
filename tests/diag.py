"""Find all zero-volume parts in the manifest - outputs to file."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Redirect stderr to suppress build123d prints
import io
old_stderr = sys.stderr
sys.stderr = io.StringIO()

from fastapi.testclient import TestClient
from api import app

client = TestClient(app)
cfg = {
    'model_type': 'structural',
    'width': 600, 'rise': 220, 'going': 250, 'waist': 200, 'inner_r': 100,
    's_bottom_steps': 2, 'winder_steps': 2, 's_top_steps': 2,
    'extend_top_flight': 0, 'unified_soffit': False,
    'tread_thickness': 20, 'riser_thickness': 20,
    'stringer_width': 50, 'stringer_depth': 220,
    'carriage_width': 50, 'carriage_depth': 180,
    'rib_spacing': 300, 'rib_width': 18, 'rib_depth': 100,
    'plaster_thickness': 10,
}

# Suppress stdout during generation
old_stdout = sys.stdout
sys.stdout = io.StringIO()
r = client.post('/generate', json=cfg)
sys.stdout = old_stdout
sys.stderr = old_stderr

# Now print clean results
cats = r.json()['manifest']['categories']
results = []
for c in cats:
    for p in c['parts']:
        vol = p['volume_mm3']
        sz = p['bbox']['size']
        is_zero = vol <= 0 or any(d <= 0 for d in sz)
        if is_zero:
            results.append(f"ZERO: cat={c['name']} part={p['name']} vol={vol} bbox={sz}")
    results.append(f"CAT: {c['name']} ({len(c['parts'])} parts)")

with open('diag_output.txt', 'w') as f:
    f.write('\n'.join(results))
print('\n'.join(results))
