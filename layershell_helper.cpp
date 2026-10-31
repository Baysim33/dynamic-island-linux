/**
 * layershell_helper.cpp — Wayland LayerShell + Precision Input Region helper
 *
 * Exported functions:
 *   setup_layershell_window(qwindow, qscreen, w, h, anchor_flags, exclusive_zone)
 *   set_click_through(qwindow, enable)
 *   set_input_rect(qwindow, x, y, width, height)  ← Precision pill hit-testing!
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

bool set_click_through(void *qwindow_ptr, bool enable) {
    if (!qwindow_ptr) return false;
    QWindow *window = reinterpret_cast<QWindow*>(qwindow_ptr);

    struct wl_surface *surface = get_wl_surface(window);
    if (!surface) return false;

    if (enable) {
        struct wl_compositor *compositor = get_wl_compositor();
        if (!compositor) return false;
        struct wl_region *empty_region = wl_compositor_create_region(compositor);
        wl_surface_set_input_region(surface, empty_region);
        wl_region_destroy(empty_region);
    } else {
        wl_surface_set_input_region(surface, nullptr);
    }

    wl_surface_commit(surface);
    return true;
}

/**
 * Sets input region to precisely (x, y, width, height).
 * Only this rectangle will receive mouse clicks and hovers!
 * All pixels outside will pass clicks through to windows underneath.
 */
bool set_input_rect(void *qwindow_ptr, int x, int y, int width, int height) {
    if (!qwindow_ptr) return false;
    QWindow *window = reinterpret_cast<QWindow*>(qwindow_ptr);

    struct wl_surface *surface = get_wl_surface(window);
    if (!surface) return false;

    struct wl_compositor *compositor = get_wl_compositor();
    if (!compositor) return false;

    struct wl_region *region = wl_compositor_create_region(compositor);
    if (width > 0 && height > 0) {
        wl_region_add(region, x, y, width, height);
    }
    wl_surface_set_input_region(surface, region);
    wl_region_destroy(region);

    wl_surface_commit(surface);
    return true;
}

} // extern "C"
