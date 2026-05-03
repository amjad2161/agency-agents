"""
SuperSplat Bridge Adapter
=========================

A Python integration adapter for the SuperSplat 3D Gaussian Splat editor
(https://github.com/playcanvas/supersplat).

SuperSplat is a browser-based application with no native REST API. This bridge
uses Playwright browser automation to load the editor and exposes its internal
event-driven API to Python via JavaScript injection.

Architecture:
- A headless Chromium instance loads SuperSplat (local build or hosted).
- A bridge script is injected into the page to create `window._superSplatBridge`
  which mediates between Python and the internal `window.scene.events` system.
- File I/O is bridged via base64-encoded blobs passed through Playwright's
  `page.evaluate()`.
- Exports are captured by intercepting downloads or by injecting a custom
  MemoryFileSystem that buffers output in JS and returns it to Python.

Usage:
    async with SuperSplatBridge() as bridge:
        await bridge.load()
        await bridge.import_file("/path/to/scene.ply")
        splats = await bridge.list_splats()
        await bridge.camera_focus()
        ply_bytes = await bridge.export_to_ply()

Dependencies:
    pip install playwright
    playwright install chromium
"""

import asyncio
import base64
import json
import logging
import os
import tempfile
import time
import traceback
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Literal, Optional, Tuple, Union

# Playwright is an optional dependency; handle gracefully
try:
    from playwright.async_api import async_playwright, Browser, BrowserContext, Page, Download
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False
    Browser = Any
    BrowserContext = Any
    Page = Any
    Download = Any

logger = logging.getLogger(__name__)


class ExportFormat(str, Enum):
    """Supported export formats."""
    PLY = "ply"
    COMPRESSED_PLY = "compressedPly"
    SPLAT = "splat"
    SOG = "sog"
    VIEWER_HTML = "htmlViewer"
    VIEWER_ZIP = "packageViewer"


class SelectionTool(str, Enum):
    """Available selection tools."""
    RECT = "rectSelection"
    BRUSH = "brushSelection"
    FLOOD = "floodSelection"
    POLYGON = "polygonSelection"
    LASSO = "lassoSelection"
    SPHERE = "sphereSelection"
    BOX = "boxSelection"
    EYEDROPPER = "eyedropperSelection"


class TransformTool(str, Enum):
    """Available transform tools."""
    MOVE = "move"
    ROTATE = "rotate"
    SCALE = "scale"
    MEASURE = "measure"


@dataclass
class CameraPose:
    """Camera pose descriptor."""
    position: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    target: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    fov: float = 60.0


@dataclass
class SplatInfo:
    """Minimal descriptor for a loaded splat."""
    name: str
    filename: str
    num_splats: int
    num_selected: int
    num_deleted: int
    num_locked: int
    visible: bool
    tint: Tuple[float, float, float] = (1.0, 1.0, 1.0)
    temperature: float = 0.0
    saturation: float = 1.0
    brightness: float = 0.0
    transparency: float = 1.0


@dataclass
class BridgeConfig:
    """Configuration for the SuperSplat bridge."""
    # URL to load SuperSplat from. Use hosted or local build.
    editor_url: str = "https://superspl.at/editor"
    # headless=True for servers, False for debugging
    headless: bool = True
    # Playwright browser launch args
    browser_args: List[str] = field(default_factory=lambda: [
        "--disable-web-security",
        "--allow-file-access-from-files",
        "--no-sandbox",
        "--disable-setuid-sandbox",
        "--disable-dev-shm-usage",
        "--disable-gpu",
    ])
    # Default viewport size
    viewport_width: int = 1280
    viewport_height: int = 720
    # Timeouts
    init_timeout_ms: float = 30000.0
    eval_timeout_ms: float = 30000.0
    export_timeout_ms: float = 120000.0
    # Enable download interception for exports
    intercept_downloads: bool = True
    # Logging
    log_js_console: bool = False


# ---------------------------------------------------------------------------
# Bridge script injected into the page
# ---------------------------------------------------------------------------
_BRIDGE_JS = """
(() => {
    if (window._superSplatBridge) return;

    const bridge = {
        _callbacks: new Map(),
        _callbackId: 0,
        _pendingExports: new Map(),
        _listeners: [],
    };

    function ensureScene() {
        if (!window.scene || !window.scene.events) {
            throw new Error('SuperSplat scene is not ready');
        }
        return window.scene;
    }

    function ensureEvents() {
        return ensureScene().events;
    }

    // --- File I/O helpers ---
    // We override BrowserFileSystem to capture writes into a JS buffer
    // that Python can read back via evaluate().

    class BridgeMemoryFileSystem {
        constructor() {
            this.files = new Map();
        }
        createWriter(filename) {
            const chunks = [];
            const writer = {
                get bytesWritten() { return chunks.reduce((s, c) => s + c.byteLength, 0); },
                write(data) {
                    chunks.push(new Uint8Array(data));
                    return Promise.resolve();
                },
                close() {
                    const total = chunks.reduce((s, c) => s + c.byteLength, 0);
                    const merged = new Uint8Array(total);
                    let off = 0;
                    for (const c of chunks) { merged.set(c, off); off += c.byteLength; }
                    this.files.set(filename, merged);
                    return Promise.resolve();
                }
            };
            return writer;
        }
        mkdir(_path) { return Promise.resolve(); }
    }

    bridge.createMemoryFileSystem = () => new BridgeMemoryFileSystem();

    bridge.getFileResult = (fs, filename) => {
        return fs.files.get(filename) || null;
    };

    // --- Core API wrappers ---

    bridge.importFiles = async (files) => {
        // files: [{ filename, dataBase64? }]
        const events = ensureEvents();
        const { MappedReadFileSystem, BlobReadSource } = await import('./src/io/index.js').catch(() => ({}));
        // Fallback: use internal modules if ES import fails in bundle
        const mappedFS = new (window.MappedReadFileSystem || MappedReadFileSystem || function() {
            this.addFile = () => {};
            this.createSource = () => { throw new Error('No MappedReadFileSystem'); };
        })();

        const importList = [];
        for (const f of files) {
            if (f.dataBase64) {
                const binary = atob(f.dataBase64);
                const bytes = new Uint8Array(binary.length);
                for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
                const blob = new Blob([bytes.buffer]);
                // We need to attach to the internal filesystem. Since we can't easily
                // reach the internal classes from bundled code, we use the global
                // 'import' event which the file-handler.ts registers.
                importList.push({ filename: f.filename, contents: blob });
            } else if (f.url) {
                importList.push({ filename: f.filename, url: f.url });
            }
        }
        return await events.invoke('import', importList);
    };

    bridge.listSplats = () => {
        const events = ensureEvents();
        const splats = events.invoke('scene.allSplats') || [];
        return splats.map(s => ({
            name: s.name,
            filename: s.filename,
            numSplats: s.numSplats,
            numSelected: s.numSelected,
            numDeleted: s.numDeleted,
            numLocked: s.numLocked,
            visible: s.visible,
            tint: [s.tintClr?.r ?? 1, s.tintClr?.g ?? 1, s.tintClr?.b ?? 1],
            temperature: s.temperature ?? 0,
            saturation: s.saturation ?? 1,
            brightness: s.brightness ?? 0,
            transparency: s.transparency ?? 1,
        }));
    };

    bridge.getSceneState = () => {
        const events = ensureEvents();
        return {
            empty: events.invoke('scene.empty'),
            dirty: events.invoke('scene.dirty'),
            splatCount: (events.invoke('scene.allSplats') || []).length,
        };
    };

    bridge.setCameraPose = (pose) => {
        const events = ensureEvents();
        const { Vec3 } = window.pc || {};
        if (!Vec3) throw new Error('PlayCanvas not loaded');
        events.fire('camera.setPose', {
            position: new Vec3(pose.position[0], pose.position[1], pose.position[2]),
            target: new Vec3(pose.target[0], pose.target[1], pose.target[2]),
            fov: pose.fov ?? 60
        }, pose.speed ?? 1);
    };

    bridge.getCameraPose = () => {
        const events = ensureEvents();
        return events.invoke('camera.getPose');
    };

    bridge.cameraFocus = () => {
        ensureEvents().fire('camera.focus');
    };

    bridge.cameraReset = () => {
        ensureEvents().fire('camera.reset');
    };

    bridge.cameraAlign = (axis) => {
        ensureEvents().fire('camera.align', axis);
    };

    bridge.selectAll = () => {
        ensureEvents().fire('select.all');
    };

    bridge.selectNone = () => {
        ensureEvents().fire('select.none');
    };

    bridge.selectInvert = () => {
        ensureEvents().fire('select.invert');
    };

    bridge.selectDelete = () => {
        ensureEvents().fire('select.delete');
    };

    bridge.selectHide = () => {
        ensureEvents().fire('select.hide');
    };

    bridge.selectUnhide = () => {
        ensureEvents().fire('select.unhide');
    };

    bridge.selectBySphere = async (center, radius, op = 'set') => {
        const events = ensureEvents();
        await events.fire('select.bySphere', op, [center[0], center[1], center[2], radius]);
    };

    bridge.selectByBox = async (center, extents, op = 'set') => {
        const events = ensureEvents();
        await events.fire('select.byBox', op, [
            center[0], center[1], center[2],
            extents[0], extents[1], extents[2]
        ]);
    };

    bridge.duplicateSelection = async () => {
        await ensureEvents().fire('select.duplicate');
    };

    bridge.separateSelection = async () => {
        await ensureEvents().fire('select.separate');
    };

    bridge.resetSplats = () => {
        ensureEvents().fire('scene.reset');
    };

    bridge.clearScene = () => {
        ensureEvents().fire('scene.clear');
    };

    bridge.undo = () => {
        ensureEvents().fire('edit.undo');
    };

    bridge.redo = () => {
        ensureEvents().fire('edit.redo');
    };

    bridge.setTool = (toolName) => {
        ensureEvents().fire('tool.set', toolName);
    };

    bridge.getActiveTool = () => {
        return ensureEvents().invoke('tool.active');
    };

    bridge.setViewBands = (bands) => {
        ensureEvents().fire('view.setBands', bands);
    };

    bridge.setSplatSize = (size) => {
        ensureEvents().fire('camera.setSplatSize', size);
    };

    bridge.setGridVisible = (visible) => {
        ensureEvents().fire('grid.setVisible', visible);
    };

    bridge.setOutlineSelection = (enabled) => {
        ensureEvents().fire('view.setOutlineSelection', enabled);
    };

    // --- Export with memory filesystem ---
    // This hijacks the export pipeline to write to a JS buffer instead of
    // triggering a browser download.
    bridge.exportToBuffer = async (exportType, options) => {
        const events = ensureEvents();
        const fs = new BridgeMemoryFileSystem();

        // We need to invoke scene.write directly with our custom fs
        // The options shape expected by scene.write in file-handler.ts:
        const writeOptions = {
            filename: options.filename || 'export',
            splatIdx: options.splatIdx ?? 'all',
            serializeSettings: {
                maxSHBands: options.maxSHBands ?? 3,
                selected: options.selected ?? false,
                minOpacity: options.minOpacity ?? 0,
                removeInvalid: options.removeInvalid ?? false,
                keepStateData: false,
                keepWorldTransform: false,
                keepColorTint: false,
            },
            compressedPly: exportType === 'compressedPly',
            sogIterations: options.sogIterations ?? 10,
            viewerExportSettings: exportType.startsWith('viewer')
                ? {
                    type: exportType === 'packageViewer' ? 'zip' : 'html',
                    experienceSettings: options.experienceSettings || {
                        version: 2,
                        tonemapping: 'linear',
                        highPrecisionRendering: false,
                        background: { color: [0, 0, 0] },
                        postEffectSettings: {
                            sharpness: { enabled: false, amount: 0 },
                            bloom: { enabled: false, intensity: 1, blurLevel: 2 },
                            grading: { enabled: false, brightness: 0, contrast: 1, saturation: 1, tint: [1,1,1] },
                            vignette: { enabled: false, intensity: 0.5, inner: 0.3, outer: 0.75, curvature: 1 },
                            fringing: { enabled: false, intensity: 0.5 }
                        },
                        animTracks: [],
                        cameras: [],
                        annotations: [],
                        startMode: 'default'
                    }
                }
                : undefined,
        };

        await events.invoke('scene.write', exportType, writeOptions, null);

        // The writer writes to 'output.ply', 'output.compressed.ply', 'output.splat', etc.
        // We scan fs.files for the output.
        for (const [fname, data] of fs.files) {
            return { filename: fname, data: Array.from(data) };
        }
        return null;
    };

    // Wait for scene to be ready (scene.start() has been called)
    bridge.waitForScene = async (timeoutMs = 30000) => {
        const start = Date.now();
        while (!window.scene || !window.scene.events) {
            if (Date.now() - start > timeoutMs) {
                throw new Error('Timeout waiting for SuperSplat scene initialization');
            }
            await new Promise(r => setTimeout(r, 100));
        }
        // Wait one extra frame for all event registrations
        await new Promise(r => setTimeout(r, 500));
    };

    window._superSplatBridge = bridge;
})();
"""

# ---------------------------------------------------------------------------
# Python bridge class
# ---------------------------------------------------------------------------

class SuperSplatBridge:
    """
    Python bridge for automating SuperSplat via Playwright.

    This bridge loads SuperSplat in a headless Chromium browser and exposes
    editor operations (import, export, camera, selection) through an async
    Python API.

    Example:
        bridge = SuperSplatBridge(BridgeConfig(headless=True))
        await bridge.start()
        await bridge.import_file("model.ply")
        info = await bridge.list_splats()
        await bridge.camera_focus()
        data = await bridge.export_to_ply()
        await bridge.stop()
    """

    def __init__(self, config: Optional[BridgeConfig] = None):
        if not HAS_PLAYWRIGHT:
            raise RuntimeError(
                "Playwright is required for SuperSplatBridge. "
                "Install it with: pip install playwright && playwright install chromium"
            )
        self.config = config or BridgeConfig()
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None
        self._download_dir: Optional[str] = None
        self._running = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> "SuperSplatBridge":
        """Launch browser, load SuperSplat, inject bridge, and wait for init."""
        if self._running:
            return self

        logger.info("Starting SuperSplat bridge...")
        pw = await async_playwright().start()
        self._browser = await pw.chromium.launch(
            headless=self.config.headless,
            args=self.config.browser_args,
        )

        ctx_opts: Dict[str, Any] = {
            "viewport": {
                "width": self.config.viewport_width,
                "height": self.config.viewport_height,
            },
            "accept_downloads": self.config.intercept_downloads,
        }
        if self.config.intercept_downloads:
            self._download_dir = tempfile.mkdtemp(prefix="supersplat_")
            ctx_opts["downloads_path"] = self._download_dir

        self._context = await self._browser.new_context(**ctx_opts)
        self._page = await self._context.new_page()

        if self.config.log_js_console:
            self._page.on("console", lambda msg: logger.debug("[JS] %s", msg.text))
            self._page.on("pageerror", lambda err: logger.error("[JS Error] %s", err))

        logger.info("Loading SuperSplat from %s", self.config.editor_url)
        await self._page.goto(self.config.editor_url, wait_until="networkidle")

        # Inject bridge script
        await self._page.evaluate(_BRIDGE_JS)

        # Wait for scene initialization
        logger.info("Waiting for SuperSplat scene initialization...")
        await self._page.evaluate(
            "window._superSplatBridge.waitForScene()",
            timeout=self.config.init_timeout_ms,
        )

        self._running = True
        logger.info("SuperSplat bridge ready.")
        return self

    async def stop(self) -> None:
        """Close browser and clean up resources."""
        if not self._running:
            return
        logger.info("Stopping SuperSplat bridge...")
        if self._page:
            await self._page.close()
            self._page = None
        if self._context:
            await self._context.close()
            self._context = None
        if self._browser:
            await self._browser.close()
            self._browser = None
        if self._download_dir and os.path.exists(self._download_dir):
            import shutil
            shutil.rmtree(self._download_dir, ignore_errors=True)
            self._download_dir = None
        self._running = False
        logger.info("SuperSplat bridge stopped.")

    async def __aenter__(self) -> "SuperSplatBridge":
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.stop()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _eval(self, js: str, arg: Any = None) -> Any:
        """Evaluate JavaScript in the page with the bridge."""
        if not self._page:
            raise RuntimeError("Bridge not started. Call start() first.")
        try:
            return await self._page.evaluate(js, arg, timeout=self.config.eval_timeout_ms)
        except Exception as e:
            logger.error("JS evaluation failed: %s\n%s", e, traceback.format_exc())
            raise

    async def _call_bridge(self, method: str, *args: Any) -> Any:
        """Call a method on window._superSplatBridge."""
        serialized = json.dumps(args)
        js = f"window._superSplatBridge.{method}(...{serialized})"
        return await self._eval(js)

    @staticmethod
    def _encode_bytes(data: bytes) -> str:
        return base64.b64encode(data).decode("ascii")

    @staticmethod
    def _decode_int_list(int_list: List[int]) -> bytes:
        return bytes(int_list)

    # ------------------------------------------------------------------
    # Import / Scene
    # ------------------------------------------------------------------

    async def import_file(
        self,
        file_path: Union[str, Path],
        filename: Optional[str] = None,
    ) -> List[SplatInfo]:
        """Import a local file into SuperSplat.

        Args:
            file_path: Path to the file (PLY, SPLAT, SOG, SPZ, etc.)
            filename: Optional override filename shown in editor.

        Returns:
            List of SplatInfo objects currently in the scene.
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        data = path.read_bytes()
        name = filename or path.name
        return await self.import_bytes(data, name)

    async def import_bytes(
        self,
        data: bytes,
        filename: str,
    ) -> List[SplatInfo]:
        """Import raw bytes as a file into SuperSplat.

        Args:
            data: Raw file bytes.
            filename: Filename to register in the editor.

        Returns:
            List of SplatInfo objects currently in the scene.
        """
        b64 = self._encode_bytes(data)
        files = [{"filename": filename, "dataBase64": b64}]
        await self._call_bridge("importFiles", files)
        # Allow time for loading spinner and scene update
        await asyncio.sleep(1.5)
        return await self.list_splats()

    async def import_url(self, url: str, filename: Optional[str] = None) -> List[SplatInfo]:
        """Import a remote URL into SuperSplat.

        Args:
            url: Remote file URL.
            filename: Optional filename override.

        Returns:
            List of SplatInfo objects currently in the scene.
        """
        fname = filename or url.split("/")[-1] or "model.ply"
        files = [{"filename": fname, "url": url}]
        await self._call_bridge("importFiles", files)
        await asyncio.sleep(2.0)
        return await self.list_splats()

    async def list_splats(self) -> List[SplatInfo]:
        """Return metadata for all loaded splats."""
        raw = await self._call_bridge("listSplats")
        if not raw:
            return []
        return [
            SplatInfo(
                name=r.get("name", ""),
                filename=r.get("filename", ""),
                num_splats=r.get("numSplats", 0),
                num_selected=r.get("numSelected", 0),
                num_deleted=r.get("numDeleted", 0),
                num_locked=r.get("numLocked", 0),
                visible=r.get("visible", True),
                tint=tuple(r.get("tint", [1.0, 1.0, 1.0])),
                temperature=r.get("temperature", 0.0),
                saturation=r.get("saturation", 1.0),
                brightness=r.get("brightness", 0.0),
                transparency=r.get("transparency", 1.0),
            )
            for r in raw
        ]

    async def get_scene_state(self) -> Dict[str, Any]:
        """Return scene state: {empty, dirty, splatCount}."""
        return await self._call_bridge("getSceneState")

    async def clear_scene(self) -> None:
        """Remove all splats from the scene."""
        await self._call_bridge("clearScene")
        await asyncio.sleep(0.5)

    async def is_scene_dirty(self) -> bool:
        """Check whether the scene has unsaved changes."""
        state = await self.get_scene_state()
        return bool(state.get("dirty", False))

    # ------------------------------------------------------------------
    # Camera
    # ------------------------------------------------------------------

    async def get_camera_pose(self) -> CameraPose:
        """Get current camera pose."""
        raw = await self._call_bridge("getCameraPose")
        pos = raw.get("position", {})
        tgt = raw.get("target", {})
        return CameraPose(
            position=(pos.get("x", 0.0), pos.get("y", 0.0), pos.get("z", 0.0)),
            target=(tgt.get("x", 0.0), tgt.get("y", 0.0), tgt.get("z", 0.0)),
            fov=raw.get("fov", 60.0),
        )

    async def set_camera_pose(
        self,
        position: Tuple[float, float, float],
        target: Tuple[float, float, float],
        fov: float = 60.0,
        speed: float = 1.0,
    ) -> None:
        """Set camera pose with optional animated transition."""
        pose = {
            "position": list(position),
            "target": list(target),
            "fov": fov,
            "speed": speed,
        }
        await self._call_bridge("setCameraPose", pose)

    async def camera_focus(self) -> None:
        """Focus camera on the currently selected splat/selection."""
        await self._call_bridge("cameraFocus")

    async def camera_reset(self) -> None:
        """Reset camera to default pose."""
        await self._call_bridge("cameraReset")

    async def camera_align(self, axis: Literal["px", "py", "pz", "nx", "ny", "nz"]) -> None:
        """Align camera to an axis and switch to orthographic mode."""
        await self._call_bridge("cameraAlign", axis)

    # ------------------------------------------------------------------
    # Selection
    # ------------------------------------------------------------------

    async def select_all(self) -> None:
        await self._call_bridge("selectAll")

    async def select_none(self) -> None:
        await self._call_bridge("selectNone")

    async def select_invert(self) -> None:
        await self._call_bridge("selectInvert")

    async def select_delete(self) -> None:
        await self._call_bridge("selectDelete")

    async def select_hide(self) -> None:
        await self._call_bridge("selectHide")

    async def select_unhide(self) -> None:
        await self._call_bridge("selectUnhide")

    async def select_by_sphere(
        self,
        center: Tuple[float, float, float],
        radius: float,
        op: Literal["set", "add", "remove"] = "set",
    ) -> None:
        """Select gaussians inside a sphere.

        Args:
            center: (x, y, z) sphere center in world space.
            radius: Sphere radius.
            op: Selection operation mode.
        """
        await self._call_bridge("selectBySphere", list(center), radius, op)

    async def select_by_box(
        self,
        center: Tuple[float, float, float],
        half_extents: Tuple[float, float, float],
        op: Literal["set", "add", "remove"] = "set",
    ) -> None:
        """Select gaussians inside an axis-aligned box.

        Args:
            center: Box center in world space.
            half_extents: Half-extents (lenx/2, leny/2, lenz/2).
            op: Selection operation mode.
        """
        await self._call_bridge("selectByBox", list(center), list(half_extents), op)

    async def duplicate_selection(self) -> None:
        """Duplicate the current selection into a new splat."""
        await self._call_bridge("duplicateSelection")
        await asyncio.sleep(1.0)

    async def separate_selection(self) -> None:
        """Separate the current selection into a new splat (removes from original)."""
        await self._call_bridge("separateSelection")
        await asyncio.sleep(1.0)

    async def reset_splats(self) -> None:
        """Reset selected splats to initial state."""
        await self._call_bridge("resetSplats")

    # ------------------------------------------------------------------
    # Edit History
    # ------------------------------------------------------------------

    async def undo(self) -> None:
        await self._call_bridge("undo")

    async def redo(self) -> None:
        await self._call_bridge("redo")

    # ------------------------------------------------------------------
    # Tools
    # ------------------------------------------------------------------

    async def set_tool(self, tool: Union[SelectionTool, TransformTool, str]) -> None:
        """Activate a tool by name."""
        name = tool.value if isinstance(tool, (SelectionTool, TransformTool)) else str(tool)
        await self._call_bridge("setTool", name)

    async def get_active_tool(self) -> str:
        """Return the name of the currently active tool."""
        return await self._call_bridge("getActiveTool")

    # ------------------------------------------------------------------
    # View Settings
    # ------------------------------------------------------------------

    async def set_view_bands(self, bands: Literal[0, 1, 2, 3]) -> None:
        """Limit spherical harmonic bands (0-3)."""
        await self._call_bridge("setViewBands", bands)

    async def set_splat_size(self, size: float) -> None:
        """Set the display size for center-mode visualization."""
        await self._call_bridge("setSplatSize", size)

    async def set_grid_visible(self, visible: bool) -> None:
        await self._call_bridge("setGridVisible", visible)

    async def set_outline_selection(self, enabled: bool) -> None:
        await self._call_bridge("setOutlineSelection", enabled)

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    async def export_to_ply(
        self,
        filename: str = "export.ply",
        max_sh_bands: int = 3,
        selected_only: bool = False,
        min_opacity: float = 0.0,
        remove_invalid: bool = False,
    ) -> bytes:
        """Export scene to PLY format and return raw bytes.

        Args:
            filename: Suggested filename (used in internal buffer naming).
            max_sh_bands: Max spherical harmonic bands (0-3).
            selected_only: Export only selected gaussians.
            min_opacity: Filter out gaussians with opacity <= this value.
            remove_invalid: Remove NaN/Inf gaussians.

        Returns:
            Raw PLY file bytes.
        """
        result = await self._call_bridge("exportToBuffer", "ply", {
            "filename": filename,
            "maxSHBands": max_sh_bands,
            "selected": selected_only,
            "minOpacity": min_opacity,
            "removeInvalid": remove_invalid,
        })
        if not result:
            raise RuntimeError("PLY export failed or returned no data.")
        return self._decode_int_list(result["data"])

    async def export_to_compressed_ply(
        self,
        filename: str = "export.compressed.ply",
        max_sh_bands: int = 3,
        selected_only: bool = False,
    ) -> bytes:
        """Export scene to compressed PLY format."""
        result = await self._call_bridge("exportToBuffer", "compressedPly", {
            "filename": filename,
            "maxSHBands": max_sh_bands,
            "selected": selected_only,
            "removeInvalid": True,
            "minOpacity": 1 / 255,
        })
        if not result:
            raise RuntimeError("Compressed PLY export failed.")
        return self._decode_int_list(result["data"])

    async def export_to_splat(
        self,
        filename: str = "export.splat",
        max_sh_bands: int = 3,
        selected_only: bool = False,
    ) -> bytes:
        """Export scene to .splat binary format."""
        result = await self._call_bridge("exportToBuffer", "splat", {
            "filename": filename,
            "maxSHBands": max_sh_bands,
            "selected": selected_only,
        })
        if not result:
            raise RuntimeError("Splat export failed.")
        return self._decode_int_list(result["data"])

    async def export_to_sog(
        self,
        filename: str = "export.sog",
        max_sh_bands: int = 3,
        sog_iterations: int = 10,
    ) -> bytes:
        """Export scene to SOG (PlayCanvas optimized scene) format.

        Note: SOG export produces a zip-like bundle. The returned bytes are
        the raw SOG file contents.
        """
        result = await self._call_bridge("exportToBuffer", "sog", {
            "filename": filename,
            "maxSHBands": max_sh_bands,
            "removeInvalid": True,
            "minOpacity": 1 / 255,
            "sogIterations": sog_iterations,
        })
        if not result:
            raise RuntimeError("SOG export failed.")
        return self._decode_int_list(result["data"])

    async def export_to_viewer(
        self,
        filename: str = "viewer",
        viewer_type: Literal["html", "zip"] = "html",
        max_sh_bands: int = 3,
    ) -> bytes:
        """Export a self-contained HTML or ZIP viewer package.

        Args:
            filename: Base filename.
            viewer_type: 'html' for single HTML file, 'zip' for ZIP package.
            max_sh_bands: Max SH bands in viewer.

        Returns:
            Raw HTML or ZIP bytes.
        """
        export_type = "packageViewer" if viewer_type == "zip" else "htmlViewer"
        result = await self._call_bridge("exportToBuffer", export_type, {
            "filename": filename,
            "maxSHBands": max_sh_bands,
        })
        if not result:
            raise RuntimeError("Viewer export failed.")
        return self._decode_int_list(result["data"])

    # ------------------------------------------------------------------
    # Screenshot / Render
    # ------------------------------------------------------------------

    async def screenshot(self, path: Optional[str] = None) -> bytes:
        """Capture a screenshot of the editor canvas as PNG.

        Args:
            path: Optional file path to save the screenshot.

        Returns:
            PNG image bytes.
        """
        if not self._page:
            raise RuntimeError("Bridge not started.")
        # Screenshot the canvas element specifically
        canvas_data = await self._page.evaluate("""
            async () => {
                const canvas = document.getElementById('canvas');
                if (!canvas) return null;
                const blob = await new Promise(res => canvas.toBlob(res, 'image/png'));
                const buf = await blob.arrayBuffer();
                return Array.from(new Uint8Array(buf));
            }
        """)
        if canvas_data is None:
            # Fallback: screenshot the whole page
            data = await self._page.screenshot(type="png", path=path)
            return data
        data = bytes(canvas_data)
        if path:
            Path(path).write_bytes(data)
        return data

    # ------------------------------------------------------------------
    # Raw JavaScript access (escape hatch)
    # ------------------------------------------------------------------

    async def eval_js(self, js_code: str) -> Any:
        """Evaluate raw JavaScript in the SuperSplat page.

        This is an escape hatch for accessing internal APIs not yet wrapped
        by the bridge.
        """
        return await self._eval(js_code)

    async def call_event(self, event_name: str, *args: Any) -> Any:
        """Fire an event on the internal event bus.

        Args:
            event_name: Event name (e.g., 'camera.focus').
            *args: Event arguments.
        """
        serialized = json.dumps(args)
        js = f"window.scene.events.fire('{event_name}', ...{serialized})"
        return await self._eval(js)

    async def invoke_function(self, function_name: str, *args: Any) -> Any:
        """Invoke a registered function on the internal event bus.

        Args:
            function_name: Function name (e.g., 'scene.splats').
            *args: Function arguments.
        """
        serialized = json.dumps(args)
        js = f"window.scene.events.invoke('{function_name}', ...{serialized})"
        return await self._eval(js)
