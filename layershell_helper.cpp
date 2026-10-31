/**
 * layershell_helper.cpp — Wayland LayerShell + Input Region helper
 *
 * Exported functions:
 *   setup_layershell_window(qwindow, qscreen, w, h, anchor_flags)
 *   set_click_through(qwindow, enable)   ← NEW
 *
 * anchor_flags maps to LayerShellQt::Window::Anchor bitmask:
 *   0=none  1=Top  2=Bottom  4=Left  8=Right
 *   e.g. Top|Left|Right = 1|4|8 = 13
 */
#include <QWindow>
#include <QScreen>
#include <QSize>
#include <QMargins>
#include <QGuiApplication>
#include <LayerShellQt/window.h>
#include <qpa/qplatformnativeinterface.h>
#include <qguiapplication_platform.h>
#include <wayland-client.h>
#include <iostream>

// ── Internal: get wl_surface & wl_compositor from Qt ─────────────────────
static struct wl_surface* get_wl_surface(QWindow *window) {
    QPlatformNativeInterface *native = QGuiApplication::platformNativeInterface();
    if (!native) return nullptr;
    return reinterpret_cast<struct wl_surface*>(
        native->nativeResourceForWindow("surface", window)
    );
}

static struct wl_compositor* get_wl_compositor() {
    QPlatformNativeInterface *native = QGuiApplication::platformNativeInterface();
    if (!native) return nullptr;
    return reinterpret_cast<struct wl_compositor*>(
        native->nativeResourceForIntegration("compositor")
    );
}

extern "C" {

/**
 * Setup a QWindow as a Wayland layer-shell surface.
 * anchor_flags: OR of 1=Top, 2=Bottom, 4=Left, 8=Right
 * exclusive_zone: 0=overlay (no strut), >0=reserve space
 */
bool setup_layershell_window(void *qwindow_ptr, void *qscreen_ptr,
                              int width, int height,
                              int anchor_flags = 1,
                              int exclusive_zone = 0) {
    if (!qwindow_ptr) return false;
    QWindow *window = reinterpret_cast<QWindow*>(qwindow_ptr);
    QScreen *screen = reinterpret_cast<QScreen*>(qscreen_ptr);

    auto lWindow = LayerShellQt::Window::get(window);
    if (!lWindow) {
        std::cerr << "[layershell] Failed to get LayerShellQt::Window" << std::endl;
        return false;
    }

    lWindow->setLayer(LayerShellQt::Window::LayerOverlay);

    // Build anchor from flags
    LayerShellQt::Window::Anchors anchors;
    if (anchor_flags & 1) anchors |= LayerShellQt::Window::AnchorTop;
    if (anchor_flags & 2) anchors |= LayerShellQt::Window::AnchorBottom;
    if (anchor_flags & 4) anchors |= LayerShellQt::Window::AnchorLeft;
    if (anchor_flags & 8) anchors |= LayerShellQt::Window::AnchorRight;
    lWindow->setAnchors(anchors);

    lWindow->setExclusiveZone(exclusive_zone);
    lWindow->setKeyboardInteractivity(LayerShellQt::Window::KeyboardInteractivityOnDemand);
    lWindow->setDesiredSize(QSize(width, height));
    lWindow->setMargins(QMargins(0, 0, 0, 0));

    if (screen) lWindow->setScreen(screen);

    return true;
}

/**
 * Toggle click-through (input transparency) on a Wayland layer-shell window.
 *   enable=true  → Empty input region  → mouse clicks fall through to desktop
 *   enable=false → NULL input region   → normal full-surface input (default)
 *
 * Must be called AFTER the window is shown (wl_surface must exist).
 */
bool set_click_through(void *qwindow_ptr, bool enable) {
    if (!qwindow_ptr) return false;
    QWindow *window = reinterpret_cast<QWindow*>(qwindow_ptr);

    struct wl_surface *surface = get_wl_surface(window);
    if (!surface) {
        std::cerr << "[layershell] set_click_through: no wl_surface" << std::endl;
        return false;
    }

    if (enable) {
        // Empty region → no part of the surface accepts input → full click-through
        struct wl_compositor *compositor = get_wl_compositor();
        if (!compositor) {
            std::cerr << "[layershell] set_click_through: no wl_compositor" << std::endl;
            return false;
        }
        struct wl_region *empty_region = wl_compositor_create_region(compositor);
        // Don't add any rectangles → stays empty
        wl_surface_set_input_region(surface, empty_region);
        wl_region_destroy(empty_region);
    } else {
        // NULL → compositor resets to full-surface default input
        wl_surface_set_input_region(surface, nullptr);
    }

    wl_surface_commit(surface);
    return true;
}

} // extern "C"
