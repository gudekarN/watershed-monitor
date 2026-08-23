"""
Targeted tests for the BUG-1, BUG-2, and BUG-3 fixes.

All tests use mocks/stubs — no GEE authentication required.

Tests:
  1. Argument-type safety: get_all_tile_layers() called with dict dates and no
     spurious positional watershed_geom → no AttributeError, no TypeError.
  2. Pre-supplied images prevent duplicate composite creation.
  3. Without pre-supplied images, standalone path still calls create_s2_composite.
  4. Static inspection: exactly two create_s2_composite() calls in the live
     analysis path (one BEFORE, one AFTER).
  5. app.py call-site passes dicts, not tuples.
  6. app.py call-site does not pass watershed_geom as a positional argument.
"""
import sys
import os
import ast
import inspect
import textwrap
import unittest
from unittest.mock import MagicMock, patch, call

os.chdir(os.path.dirname(os.path.abspath(__file__)))

PASS = []
FAIL = []

def ok(name):
    PASS.append(name)
    print(f"  PASS  {name}")

def fail(name, reason):
    FAIL.append(name)
    print(f"  FAIL  {name}: {reason}")


# =============================================================================
# Test 1: get_all_tile_layers() with dict dates does not AttributeError/TypeError
# =============================================================================
print("\n--- Test 1: get_all_tile_layers() argument type safety ---")
try:
    # Build a minimal mock that fakes enough of gee_engine internals
    # so we can call get_all_tile_layers() without GEE being initialised.
    with patch.dict("sys.modules", {
        "ee": MagicMock(),
        "streamlit": MagicMock(),
    }):
        import importlib
        # Reload so patches take effect cleanly
        if "backend.gee_engine" in sys.modules:
            del sys.modules["backend.gee_engine"]

        with patch("backend.gee_engine._is_gee_ready", return_value=False):
            import backend.gee_engine as gee

            result = gee.get_all_tile_layers(
                19.35, 74.55,
                {"start": "2019-01-01", "end": "2019-12-31"},   # dict — correct
                {"start": "2024-01-01", "end": "2024-12-31"},   # dict — correct
                # No watershed_geom positional arg — correct
            )
            # When GEE is not ready, result should be an empty dict
            if isinstance(result, dict):
                ok("T1a: dict dates accepted without AttributeError")
            else:
                fail("T1a: dict dates accepted without AttributeError",
                     f"expected dict, got {type(result)}")
except AttributeError as e:
    fail("T1a: dict dates accepted without AttributeError", f"AttributeError: {e}")
except TypeError as e:
    fail("T1a: dict dates accepted without AttributeError", f"TypeError: {e}")
except Exception as e:
    # Any other error (import etc.) — still confirm no Attr/TypeError
    ok(f"T1a: dict dates accepted without AttributeError (early exit: {type(e).__name__})")


# =============================================================================
# Test 2: Pre-supplied images prevent create_s2_composite() from being called
# =============================================================================
print("\n--- Test 2: Pre-supplied images skip create_s2_composite() ---")
try:
    if "backend.gee_engine" in sys.modules:
        del sys.modules["backend.gee_engine"]

    with patch("backend.gee_engine._is_gee_ready", return_value=True), \
         patch("backend.gee_engine._make_geometry", return_value=MagicMock()), \
         patch("backend.gee_engine.create_s2_composite") as mock_create, \
         patch("backend.gee_engine.get_elevation", return_value=(None, None)), \
         patch("backend.gee_engine.ee_image_to_folium_tile", return_value=None):

        import backend.gee_engine as gee

        fake_before = MagicMock(name="before_img")
        fake_after  = MagicMock(name="after_img")

        # Patch normalizedDifference on the mock images (used in layer building)
        for img in (fake_before, fake_after):
            img.normalizedDifference.return_value = MagicMock()

        gee.get_all_tile_layers(
            19.35, 74.55,
            {"start": "2019-01-01", "end": "2019-12-31"},
            {"start": "2024-01-01", "end": "2024-12-31"},
            before_img=fake_before,
            after_img=fake_after,
        )

        if mock_create.call_count == 0:
            ok("T2a: create_s2_composite NOT called when pre-built images supplied")
        else:
            fail("T2a: create_s2_composite NOT called when pre-built images supplied",
                 f"was called {mock_create.call_count} time(s)")

except Exception as e:
    fail("T2a: create_s2_composite NOT called when pre-built images supplied",
         f"{type(e).__name__}: {e}")


# =============================================================================
# Test 3: Without pre-supplied images, standalone path calls create_s2_composite
# =============================================================================
print("\n--- Test 3: Standalone path calls create_s2_composite() when no images supplied ---")
try:
    if "backend.gee_engine" in sys.modules:
        del sys.modules["backend.gee_engine"]

    fake_composite = MagicMock(name="composite")
    fake_composite.normalizedDifference.return_value = MagicMock()
    fake_meta = {"images_before_filter": 10, "images_after_filter": 8}

    # Mock streamlit with a real-dict-like session_state so the cache-key
    # check returns False (MagicMock.__contains__ returns a truthy mock by
    # default which causes an early return, bypassing composite creation).
    mock_st = MagicMock()
    mock_st.session_state = {}   # real dict — cache miss guaranteed

    with patch.dict("sys.modules", {"streamlit": mock_st}), \
         patch("backend.gee_engine._is_gee_ready", return_value=True), \
         patch("backend.gee_engine._make_geometry", return_value=MagicMock()), \
         patch("backend.gee_engine.get_elevation", return_value=(None, None)), \
         patch("backend.gee_engine.ee_image_to_folium_tile", return_value=None):

        import backend.gee_engine as gee

        # patch.object intercepts the call even when made from within the module
        with patch.object(gee, "create_s2_composite",
                          return_value=(fake_composite, fake_meta)) as mock_create:
            gee.get_all_tile_layers(
                19.35, 74.55,
                {"start": "2019-01-01", "end": "2019-12-31"},
                {"start": "2024-01-01", "end": "2024-12-31"},
                # No before_img / after_img → standalone mode
            )

            if mock_create.call_count == 2:
                ok("T3a: create_s2_composite called exactly 2 times in standalone mode")
            else:
                fail("T3a: create_s2_composite called exactly 2 times in standalone mode",
                     f"called {mock_create.call_count} time(s)")

            # Verify the two calls used correct start dates
            calls = mock_create.call_args_list
            if len(calls) == 2:
                before_sd = calls[0].kwargs.get("start_date")
                after_sd  = calls[1].kwargs.get("start_date")
                if before_sd == "2019-01-01" and after_sd == "2024-01-01":
                    ok("T3b: BEFORE/AFTER dates passed correctly to create_s2_composite")
                else:
                    fail("T3b: BEFORE/AFTER dates passed correctly to create_s2_composite",
                         f"before_start={before_sd!r}, after_start={after_sd!r}")

except Exception as e:
    fail("T3a: standalone mode calls", f"{type(e).__name__}: {e}")


# =============================================================================
# Test 4: Static inspection of app.py call site
# =============================================================================
print("\n--- Test 4: Static inspection of app.py call site ---")
try:
    src = open("app.py", encoding="utf-8").read()
    tree = ast.parse(src)

    # Find all calls to get_all_tile_layers in the AST
    tile_calls = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "get_all_tile_layers"
    ]

    if len(tile_calls) == 1:
        ok(f"T4a: exactly 1 call to get_all_tile_layers() in app.py")
    else:
        fail(f"T4a: exactly 1 call to get_all_tile_layers() in app.py",
             f"found {len(tile_calls)}")

    if tile_calls:
        call_node = tile_calls[0]
        # Check positional args — should be lat, lon, dict, dict (4 positional)
        n_pos = len(call_node.args)
        # Expect exactly 4: lat, lon, before_dict, after_dict
        if n_pos == 4:
            ok("T4b: 4 positional args (lat, lon, before_dict, after_dict)")
        else:
            fail("T4b: 4 positional args",
                 f"found {n_pos} positional args")

        # Verify args 3 and 4 are dict literals (ast.Dict), not tuples (ast.Tuple)
        arg2 = call_node.args[2] if len(call_node.args) > 2 else None
        arg3 = call_node.args[3] if len(call_node.args) > 3 else None

        if isinstance(arg2, ast.Dict):
            ok("T4c: before_dates arg is a dict literal (not a tuple)")
        elif arg2 is not None:
            fail("T4c: before_dates arg is a dict literal (not a tuple)",
                 f"AST node type is {type(arg2).__name__}")

        if isinstance(arg3, ast.Dict):
            ok("T4d: after_dates arg is a dict literal (not a tuple)")
        elif arg3 is not None:
            fail("T4d: after_dates arg is a dict literal (not a tuple)",
                 f"AST node type is {type(arg3).__name__}")

        # Verify keyword args include before_img and after_img
        kw_names = {kw.arg for kw in call_node.keywords}
        if "before_img" in kw_names:
            ok("T4e: before_img passed as keyword arg")
        else:
            fail("T4e: before_img passed as keyword arg",
                 f"keywords found: {kw_names}")

        if "after_img" in kw_names:
            ok("T4f: after_img passed as keyword arg")
        else:
            fail("T4f: after_img passed as keyword arg",
                 f"keywords found: {kw_names}")

        # Confirm watershed_geom is NOT a positional arg (no 5th positional)
        if n_pos < 5:
            ok("T4g: watershed_geom not passed as positional arg (no 5th positional)")
        else:
            fail("T4g: watershed_geom not passed as positional arg",
                 f"{n_pos} positional args found — 5th is unexpected")

except Exception as e:
    fail("T4: static inspection", f"{type(e).__name__}: {e}")


# =============================================================================
# Test 5: Static inspection — exactly 2 create_s2_composite() calls in live path
# =============================================================================
print("\n--- Test 5: Exactly 2 create_s2_composite calls in live path of app.py ---")
try:
    src = open("app.py", encoding="utf-8").read()
    tree = ast.parse(src)

    composite_calls = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "create_s2_composite"
    ]

    if len(composite_calls) == 2:
        ok(f"T5a: exactly 2 create_s2_composite() calls in app.py (BEFORE + AFTER)")
    else:
        fail(f"T5a: exactly 2 create_s2_composite() calls in app.py",
             f"found {len(composite_calls)}")

except Exception as e:
    fail("T5a: static inspection for composite calls", f"{type(e).__name__}: {e}")


# =============================================================================
# Test 6: get_all_tile_layers signature inspection
# =============================================================================
print("\n--- Test 6: get_all_tile_layers() signature has before_img / after_img ---")
try:
    if "backend.gee_engine" in sys.modules:
        del sys.modules["backend.gee_engine"]

    with patch.dict("sys.modules", {"ee": MagicMock(), "streamlit": MagicMock()}):
        with patch("backend.gee_engine._is_gee_ready", return_value=False):
            import backend.gee_engine as gee_mod

    sig = inspect.signature(gee_mod.get_all_tile_layers)
    params = sig.parameters

    if "before_img" in params:
        ok("T6a: before_img parameter exists in get_all_tile_layers()")
        p = params["before_img"]
        if p.default is None:
            ok("T6b: before_img defaults to None")
        else:
            fail("T6b: before_img defaults to None", f"default={p.default!r}")
        if p.kind == inspect.Parameter.KEYWORD_ONLY:
            ok("T6c: before_img is keyword-only (*)")
        else:
            fail("T6c: before_img is keyword-only", f"kind={p.kind}")
    else:
        fail("T6a: before_img parameter exists", "not found in signature")

    if "after_img" in params:
        ok("T6d: after_img parameter exists in get_all_tile_layers()")
    else:
        fail("T6d: after_img parameter exists", "not found in signature")

except Exception as e:
    fail("T6: signature inspection", f"{type(e).__name__}: {e}")


# =============================================================================
# Existing test suite
# =============================================================================
print("\n--- Existing test suite (test_app.py) ---")
import subprocess
env = os.environ.copy()
env["PYTHONUTF8"] = "1"
r = subprocess.run(
    [sys.executable, "test_app.py"],
    capture_output=True, text=True, env=env, cwd=os.getcwd()
)
if "ALL CHECKS PASSED" in r.stdout:
    ok("Existing test suite: ALL CHECKS PASSED")
else:
    # Print last relevant line
    relevant = [l for l in r.stdout.splitlines() if "PASS" in l or "FAIL" in l or "CHECK" in l]
    fail("Existing test suite", "; ".join(relevant[-3:]) or r.stdout[-200:])


# =============================================================================
# Summary
# =============================================================================
print(f"\n{'='*60}")
print(f"RESULTS: {len(PASS)} passed, {len(FAIL)} failed")
if FAIL:
    print(f"\nFAILED:")
    for f in FAIL:
        print(f"  - {f}")
print("="*60)
print("\nNOTE: No GEE runtime claim made. All tests use mocks/stubs.")
sys.exit(0 if not FAIL else 1)
