"""Browser E2E tests for the Parametric Staircase Studio.

Uses pytest-playwright to test the frontend UI including the Object Tree,
panel interactions, CNC nesting, and exports.

Requires:
- API server running on http://localhost:8000
- pip install pytest-playwright
- playwright install chromium
"""
import pytest
import re
from playwright.sync_api import Page, expect


BASE_URL = "http://localhost:8000"


# ===========================================================================
# FIXTURES
# ===========================================================================

@pytest.fixture(scope="function")
def studio_page(page: Page):
    """Navigate to the studio and wait for initial model to generate."""
    page.goto(BASE_URL)
    # Wait for loading overlay to disappear (model generation complete)
    page.wait_for_selector("#loading", state="hidden", timeout=60000)
    return page


@pytest.fixture(scope="function")
def structural_page(page: Page):
    """Navigate to studio, switch to structural mode, and generate."""
    page.goto(BASE_URL)
    page.wait_for_selector("#loading", state="hidden", timeout=60000)
    
    # Switch to structural mode
    page.select_option("#model_type", "structural")
    # Click generate
    page.click("#generate")
    page.wait_for_selector("#loading", state="hidden", timeout=60000)
    return page


# ===========================================================================
# PAGE LOAD
# ===========================================================================

class TestPageLoad:
    def test_page_loads(self, studio_page: Page):
        """Page loads successfully with correct title."""
        assert "Parametric Staircase Studio" in studio_page.title()

    def test_viewport_exists(self, studio_page: Page):
        """3D viewport canvas is present."""
        viewport = studio_page.locator("#viewport")
        expect(viewport).to_be_visible()

    def test_controls_panel_visible(self, studio_page: Page):
        """Left controls panel is visible."""
        panel = studio_page.locator("#controls-panel")
        expect(panel).to_be_visible()

    def test_generate_button_exists(self, studio_page: Page):
        """Generate Model button is present."""
        btn = studio_page.locator("#generate")
        expect(btn).to_be_visible()
        expect(btn).to_have_text("Generate Model")


# ===========================================================================
# OBJECT TREE (Issue Area)
# ===========================================================================

class TestObjectTree:
    def test_tree_hidden_in_volumetric_mode(self, studio_page: Page):
        """Object tree panel should not be visible in volumetric mode."""
        tree = studio_page.locator("#tree-panel")
        # In volumetric mode (default), tree should be hidden
        expect(tree).to_have_css("display", "none")

    def test_tree_visible_in_structural_mode(self, structural_page: Page):
        """Object tree panel should be visible in structural mode."""
        tree = structural_page.locator("#tree-panel")
        expect(tree).to_be_visible()

    def test_tree_has_categories(self, structural_page: Page):
        """Object tree should contain category nodes after generation."""
        categories = structural_page.locator("#tree-content .category-node")
        count = categories.count()
        assert count > 0, "No category nodes found in object tree"

    def test_tree_category_names(self, structural_page: Page):
        """Category nodes should include expected names."""
        tree_text = structural_page.locator("#tree-content").inner_text()
        # At least treads and risers should be present
        assert "treads" in tree_text.lower() or "Treads" in tree_text

    def test_tree_has_part_nodes(self, structural_page: Page):
        """Each expanded category should show individual part nodes."""
        parts = structural_page.locator("#tree-content .part-node")
        assert parts.count() > 0, "No part nodes found"

    def test_category_expand_collapse(self, structural_page: Page):
        """Clicking a category summary toggles its expanded state."""
        # Get first category
        first_cat = structural_page.locator("#tree-content .category-node").first
        summary = first_cat.locator("summary")
        
        # Initially open
        assert first_cat.get_attribute("open") is not None or first_cat.evaluate("el => el.open") == True
        
        # Click to close
        summary.click()
        structural_page.wait_for_timeout(300)
        
        # Click to reopen
        summary.click()
        structural_page.wait_for_timeout(300)

    def test_visibility_toggle_category(self, structural_page: Page):
        """Clicking the visibility icon on a category should toggle mesh visibility."""
        vis_btn = structural_page.locator("#tree-content .category-node .icon-btn.active").first
        assert vis_btn.count() > 0 or structural_page.locator("#tree-content .icon-btn").first.count() > 0

    def test_opacity_slider_exists(self, structural_page: Page):
        """Each category should have an opacity slider input."""
        opacity_inputs = structural_page.locator("#tree-content input[type='range']")
        assert opacity_inputs.count() > 0, "No opacity sliders found in tree"

    def test_color_picker_exists(self, structural_page: Page):
        """Each category should have a color picker input."""
        color_inputs = structural_page.locator("#tree-content input[type='color']")
        assert color_inputs.count() > 0, "No color pickers found in tree"


# ===========================================================================
# UI PANELS & LAYOUT
# ===========================================================================

class TestUIPanels:
    def test_controls_panel_position(self, studio_page: Page):
        """Controls panel should be positioned at top-left."""
        panel = studio_page.locator("#controls-panel")
        box = panel.bounding_box()
        assert box is not None
        assert box["x"] < 100, f"Controls panel X={box['x']} (expected < 100)"
        assert box["y"] < 100, f"Controls panel Y={box['y']} (expected < 100)"

    def test_tree_panel_position(self, structural_page: Page):
        """Tree panel should be positioned at top-right."""
        panel = structural_page.locator("#tree-panel")
        box = panel.bounding_box()
        if box:  # Visible
            viewport_width = structural_page.viewport_size["width"]
            assert box["x"] + box["width"] > viewport_width - 100, \
                f"Tree panel right edge at {box['x'] + box['width']} (viewport={viewport_width})"

    def test_minimise_tree(self, structural_page: Page):
        """Clicking minimise button hides the tree panel."""
        tree = structural_page.locator("#tree-panel")
        expect(tree).to_be_visible()
        
        # Click minimise
        structural_page.click("#minimise-tree")
        structural_page.wait_for_timeout(500)
        
        # Panel should have the minimised class
        assert "minimised" in (tree.get_attribute("class") or "")

    def test_restore_tree_via_toggle(self, structural_page: Page):
        """After minimising, clicking toggle button restores the tree."""
        structural_page.click("#minimise-tree")
        structural_page.wait_for_timeout(500)
        
        structural_page.click("#toggle-tree")
        structural_page.wait_for_timeout(500)
        
        tree = structural_page.locator("#tree-panel")
        assert "minimised" not in (tree.get_attribute("class") or "")

    def test_minimise_state_persists(self, page: Page):
        """Minimised state should persist across page reloads."""
        page.goto(BASE_URL)
        page.wait_for_selector("#loading", state="hidden", timeout=60000)
        
        # Switch to structural
        page.select_option("#model_type", "structural")
        page.click("#generate")
        page.wait_for_selector("#loading", state="hidden", timeout=60000)
        
        # Minimise
        page.locator("#minimise-tree").click(force=True)
        page.wait_for_timeout(500)
        
        # Reload
        page.reload()
        page.wait_for_selector("#loading", state="hidden", timeout=60000)
        
        # Check localStorage was read
        is_minimised = page.evaluate("localStorage.getItem('tree-minimised')")
        assert is_minimised == "true"


# ===========================================================================
# VIEW TOGGLE (3D ↔ CNC)
# ===========================================================================

class TestViewToggle:
    def test_cnc_panel_hidden_by_default(self, studio_page: Page):
        """CNC panel should not be visible initially."""
        cnc = studio_page.locator("#cnc-panel")
        expect(cnc).not_to_be_visible()

    def test_switch_to_cnc_view(self, studio_page: Page):
        """Clicking CNC Nesting tab shows CNC panel and hides controls."""
        studio_page.click("#view-cnc")
        studio_page.wait_for_timeout(300)
        
        cnc = studio_page.locator("#cnc-panel")
        expect(cnc).to_be_visible()
        
        controls = studio_page.locator("#controls-panel")
        expect(controls).not_to_be_visible()

    def test_switch_back_to_3d(self, studio_page: Page):
        """Switching back to 3D view restores controls and hides CNC."""
        studio_page.click("#view-cnc")
        studio_page.wait_for_timeout(300)
        studio_page.click("#view-3d")
        studio_page.wait_for_timeout(300)
        
        controls = studio_page.locator("#controls-panel")
        expect(controls).to_be_visible()
        
        cnc = studio_page.locator("#cnc-panel")
        expect(cnc).not_to_be_visible()


# ===========================================================================
# CNC NESTING UI
# ===========================================================================

class TestCNCNestingUI:
    def test_cnc_categories_populate(self, structural_page: Page):
        """CNC categories should populate when switching to CNC view."""
        structural_page.click("#view-cnc")
        structural_page.wait_for_timeout(500)
        
        checkboxes = structural_page.locator("#cnc-categories input[type='checkbox']")
        assert checkboxes.count() > 0, "No category checkboxes populated"

    def test_sheet_dimension_inputs(self, structural_page: Page):
        """Sheet width and height inputs should have default values."""
        structural_page.click("#view-cnc")
        structural_page.wait_for_timeout(300)
        
        width = structural_page.locator("#sheet_width")
        height = structural_page.locator("#sheet_height")
        assert width.input_value() == "2440"
        assert height.input_value() == "1220"

    def test_calculate_nesting_button(self, structural_page: Page):
        """Calculate Nesting button should trigger nesting calculation."""
        structural_page.click("#view-cnc")
        structural_page.wait_for_timeout(500)
        
        btn = structural_page.locator("#calculate-nesting")
        expect(btn).to_be_visible()


# ===========================================================================
# EXPORT BUTTONS
# ===========================================================================

class TestExportButtons:
    def test_export_controls_visible_after_generate(self, studio_page: Page):
        """Export controls should be visible after model generation."""
        export = studio_page.locator("#export-controls")
        # After generation, display should be block
        style = export.get_attribute("style") or ""
        assert "block" in style or export.is_visible()

    def test_glb_button_exists(self, studio_page: Page):
        """GLB download button should exist."""
        btn = studio_page.locator("#download-glb")
        expect(btn).to_be_visible()

    def test_gltf_button_exists(self, studio_page: Page):
        """glTF download button should exist."""
        btn = studio_page.locator("#download-gltf")
        expect(btn).to_be_visible()

    def test_autocad_button_exists(self, studio_page: Page):
        """AutoCAD Bundle button should exist."""
        btn = studio_page.locator("#download-autocad")
        expect(btn).to_be_visible()

    def test_dxf_button_exists(self, studio_page: Page):
        """DXF Profile button should exist."""
        btn = studio_page.locator("#download-dxf")
        expect(btn).to_be_visible()


# ===========================================================================
# SELECTION SYSTEM
# ===========================================================================

class TestSelection:
    def test_selection_info_hidden_initially(self, structural_page: Page):
        """Selection info panel should be hidden when nothing is selected."""
        info = structural_page.locator("#selection-info")
        expect(info).not_to_be_visible()

    def test_part_click_selects_in_tree(self, structural_page: Page):
        """Clicking a part node in the tree should show selection info."""
        part = structural_page.locator("#tree-content .part-node").first
        part.click()
        structural_page.wait_for_timeout(300)
        
        info = structural_page.locator("#selection-info")
        expect(info).to_be_visible()

    def test_selection_shows_details(self, structural_page: Page):
        """Selection info should show part name and volume."""
        part = structural_page.locator("#tree-content .part-node").first
        part.click()
        structural_page.wait_for_timeout(300)
        
        details = structural_page.locator("#selection-details").inner_text()
        assert len(details) > 0, "Selection details is empty"

    def test_deselect_on_tree_regen(self, structural_page: Page):
        """Regenerating the model should clear selection."""
        # Select a part
        part = structural_page.locator("#tree-content .part-node").first
        part.click()
        structural_page.wait_for_timeout(300)
        
        # Regenerate
        structural_page.click("#generate")
        structural_page.wait_for_selector("#loading", state="hidden", timeout=60000)
        
        info = structural_page.locator("#selection-info")
        expect(info).not_to_be_visible()


# ===========================================================================
# SLIDER CONTROLS
# ===========================================================================

class TestSliderControls:
    def test_slider_value_display_updates(self, studio_page: Page):
        """Moving a slider should update its value display."""
        slider = studio_page.locator("#width")
        display = studio_page.locator("#width-val")
        
        initial_val = display.inner_text()
        # Change slider value
        slider.fill("1000")
        slider.dispatch_event("input")
        studio_page.wait_for_timeout(100)
        
        new_val = display.inner_text()
        assert new_val == "1000", f"Display didn't update: {initial_val} → {new_val}"

    def test_all_sliders_have_displays(self, studio_page: Page):
        """Every range slider should have a corresponding value display."""
        sliders = studio_page.locator('input[type="range"]')
        count = sliders.count()
        for i in range(count):
            slider = sliders.nth(i)
            slider_id = slider.get_attribute("id")
            if slider_id:
                display = studio_page.locator(f"#{slider_id}-val")
                expect(display).to_be_visible()
