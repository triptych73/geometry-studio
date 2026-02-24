import json
import io
import csv

def generate_csv(manifest_data):
    """
    Parses a manifest containing geometric data for staircase parts and calculates
    Bill of Materials (BOM) including material volume and estimated sheet count.
    
    Args:
        manifest_data (dict or str): The manifest data containing categories and parts.
        
    Returns:
        str: A formatted CSV string.
    """
    if isinstance(manifest_data, str):
        data = json.loads(manifest_data)
    else:
        data = manifest_data

    # Material Definitions
    # Mapping categories to materials and their thicknesses
    MATERIAL_MAP = {
        "treads": {"material": "20mm Timber", "thickness": 20.0},
        "risers": {"material": "20mm Timber", "thickness": 20.0},
        "stringers": {"material": "50mm Structural", "thickness": 50.0},
        "carriages": {"material": "50mm Structural", "thickness": 50.0},
        "ribs": {"material": "18mm Plywood", "thickness": 18.0},
        "plaster": {"material": "18mm Plywood", "thickness": 18.0},
    }

    # Constants for nesting calculation
    SHEET_WIDTH = 2440.0
    SHEET_HEIGHT = 1220.0
    NESTING_EFFICIENCY = 0.70

    # Initialize results
    # results[material_name] = {total_parts, total_volume_mm3, thickness}
    bom_results = {}

    categories = data.get("categories", [])
    for category in categories:
        cat_name = category.get("name")
        if cat_name not in MATERIAL_MAP:
            continue
            
        mat_info = MATERIAL_MAP[cat_name]
        mat_name = mat_info["material"]
        thickness = mat_info["thickness"]
        
        if mat_name not in bom_results:
            bom_results[mat_name] = {
                "total_parts": 0,
                "total_volume_mm3": 0.0,
                "thickness": thickness
            }
            
        parts = category.get("parts", [])
        bom_results[mat_name]["total_parts"] += len(parts)
        for part in parts:
            bom_results[mat_name]["total_volume_mm3"] += part.get("volume_mm3", 0.0)

    # Prepare CSV output
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Material", "Total Parts", "Total Volume (Liters)", "Estimated Sheets Required"])

    # Sort materials for consistent output
    for mat_name in sorted(bom_results.keys()):
        res = bom_results[mat_name]
        
        # Volume in Liters (1 Liter = 1,000,000 mm3)
        volume_liters = res["total_volume_mm3"] / 1_000_000.0
        
        # Calculate Sheets Required
        # Volume of one sheet = W * H * Thickness
        sheet_volume_mm3 = SHEET_WIDTH * SHEET_HEIGHT * res["thickness"]
        
        # Effective volume per sheet accounting for 70% nesting efficiency
        effective_volume_per_sheet = sheet_volume_mm3 * NESTING_EFFICIENCY
        
        if effective_volume_per_sheet > 0:
            sheets_required = res["total_volume_mm3"] / effective_volume_per_sheet
        else:
            sheets_required = 0
            
        writer.writerow([
            mat_name,
            res["total_parts"],
            f"{volume_liters:.2f}",
            f"{sheets_required:.2f}"
        ])

    return output.getvalue()

if __name__ == "__main__":
    # Test with sample data
    test_manifest = {
        "categories": [
            {
                "name": "treads",
                "parts": [
                    {"name": "treads_1", "volume_mm3": 5000000},
                    {"name": "treads_2", "volume_mm3": 5000000}
                ]
            },
            {
                "name": "stringers",
                "parts": [
                    {"name": "stringers_1", "volume_mm3": 25000000}
                ]
            }
        ]
    }
    print(generate_csv(test_manifest))
