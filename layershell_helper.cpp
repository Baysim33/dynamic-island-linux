#include <QWindow>
#include <QScreen>
#include <QSize>
#include <QMargins>
#include <LayerShellQt/window.h>
#include <iostream>

extern "C" {
    bool setup_layershell_window(void *qwindow_ptr, void *qscreen_ptr, int width, int height) {
        if (!qwindow_ptr) return false;
        QWindow *window = reinterpret_cast<QWindow*>(qwindow_ptr);
        QScreen *screen = reinterpret_cast<QScreen*>(qscreen_ptr);
        auto lWindow = LayerShellQt::Window::get(window);
        if (!lWindow) {
            std::cerr << "Failed to get LayerShellQt::Window" << std::endl;
            return false;
        }
        lWindow->setLayer(LayerShellQt::Window::LayerOverlay);
        lWindow->setAnchors(LayerShellQt::Window::AnchorTop);
        lWindow->setExclusiveZone(0);
        lWindow->setKeyboardInteractivity(LayerShellQt::Window::KeyboardInteractivityNone);
        lWindow->setDesiredSize(QSize(width, height));
        lWindow->setMargins(QMargins(0, 0, 0, 0));
        if (screen) {
            lWindow->setScreen(screen);
        }
        return true;
    }
}
