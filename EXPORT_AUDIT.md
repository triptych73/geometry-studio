# Export Pipeline Review

**Date:** 2026-02-24
**Reviewer:** Wesley (Sub-agent Proxy)

## 1. Bill of Materials (BOM) CSV Pipeline
*   **Status:** ✅ Upgraded
*   **Issue:** The previous `bom_export.py` only output a high-level summary (Material, Total Parts, Total Volume, Estimated Sheets). This was insufficient for factory takeoff, which requires line-by-line part dimensions.
*   **Fix:** 
    1.  Modified `api.py` (`export_bom_csv` route) to extract the exact `bounding_box()` dimensions (length, width, thickness) of every generated 3D solid and inject them into the JSON manifest.
    2.  Rewrote `bom_export.py` to process these new dimensions. It now groups identical parts and outputs a detailed factory takeoff table with the headers: `[Part ID, Name, Quantity, Length (mm), Width (mm), Thickness (mm), Material, Volume (Liters)]`.
*   **Result:** Clicking "Download Takeoff (CSV)" on the frontend now delivers a production-ready parts list.

## 2. CNC DXF Export Pipeline
*   **Status:** ✅ Verified (with notes)
*   **Review:** The `/export/dxf` route in `api.py` uses `ezdxf` to generate the file. It successfully loops through the structural components (treads, risers, stringers, carriages, ribs).
*   **Key Features Confirmed:**
    1.  **3D Scarf Split:** It correctly applies the `split_with_scarf_joint` logic before exporting to ensure parts longer than 2440mm (like long stringers) are split for CNC routing.
    2.  **2D Projection:** It uses the `extract_2d_profile` function (Edge Trace logic) to reliably flatten the 3D shapes into 2D polylines.
    3.  **Layout:** The parts are laid out in a grid with labels (`cat_name_index`).
*   **Note for Future:** The current DXF export lays out the parts in a grid, which is perfect for viewing/profiling. True high-efficiency algorithmic nesting (packing pieces tightly onto a 2440x1220 sheet) is currently handled on the frontend via SVGNest, not in the raw DXF output. The DXF output is structurally sound.

## 3. API Routes
*   **Status:** ✅ Verified
*   The endpoints `/export/bom` and `/export/dxf` are correctly bound and returning the appropriate file buffers (`text/csv` and `application/dxf` respectively) with `attachment` Content-Disposition headers to trigger browser downloads.

**Conclusion:** The export pipeline is fully operational and structurally accurate for factory handoff.
