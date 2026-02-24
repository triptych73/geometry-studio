import json
import io
import csv

def generate_csv(manifest_data):
    if isinstance(manifest_data, str):
        data = json.loads(manifest_data)
    else:
        data = manifest_data

    MATERIAL_MAP = {
        "treads": "20mm Timber",
        "risers": "20mm Timber",
        "stringers": "50mm Structural",
        "carriages": "50mm Structural",
        "ribs": "18mm Plywood",
        "plaster": "18mm Plywood",
    }

    output = io.StringIO()
    writer = csv.writer(output)
    
    # Write Factory Takeoff Headers
    writer.writerow(["Part ID", "Name", "Quantity", "Length (mm)", "Width (mm)", "Thickness (mm)", "Material", "Volume (Liters)"])

    part_id_counter = 1
    categories = data.get("categories", [])
    
    for category in categories:
        cat_name = category.get("name")
        material = MATERIAL_MAP.get(cat_name, "Unknown Material")
            
        parts = category.get("parts", [])
        
        # Group identical parts to calculate quantity (based on dimensions)
        grouped_parts = {}
        for part in parts:
            name = part.get("name", "Unknown")
            length = round(part.get("length", 0.0), 1)
            width = round(part.get("width", 0.0), 1)
            thickness = round(part.get("thickness", 0.0), 1)
            vol_liters = round(part.get("volume_mm3", 0.0) / 1000000.0, 3)
            
            # Key for grouping identical parts
            key = f"{cat_name}_{length}x{width}x{thickness}"
            
            if key not in grouped_parts:
                grouped_parts[key] = {
                    "name": cat_name.capitalize().rstrip('s'), # e.g. Treads -> Tread
                    "qty": 0,
                    "l": length,
                    "w": width,
                    "t": thickness,
                    "vol": vol_liters,
                    "mat": material
                }
            grouped_parts[key]["qty"] += 1

        for key, details in grouped_parts.items():
            part_id = f"PT-{part_id_counter:03d}"
            writer.writerow([
                part_id,
                details["name"],
                details["qty"],
                f"{details['l']:.1f}",
                f"{details['w']:.1f}",
                f"{details['t']:.1f}",
                details["mat"],
                f"{details['vol']:.3f}"
            ])
            part_id_counter += 1

    return output.getvalue()
