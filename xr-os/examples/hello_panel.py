"""
The smallest possible XR-OS app: mount a floating panel with a button, and
run the world for a few frames without any real headset.

    python examples/hello_panel.py
"""

from xr_os.runtime.app import XRApp, XRWorld
from xr_os.ui.elements import Button3D, SpatialPanel


class HelloPanelApp(XRApp):
    app_id = "hello_panel"

    def on_start(self) -> None:
        self.panel = SpatialPanel(position=(0, 0, -2), size=(1.5, 0.8))
        self.world.add(self.panel)

        self.count = 0
        button = self.panel.add(Button3D("Click me", position=(0, -0.2, 0.01), on_click=self._on_click))
        self.button = button

    def _on_click(self, button: Button3D) -> None:
        self.count += 1
        print(f"[{self.app_id}] {button.label} clicked ({self.count} total)")

    def on_update(self, dt: float) -> None:
        if self.world.frame_count % 90 == 0:
            print(f"[{self.app_id}] frame={self.world.frame_count} fps={self.world.fps:.1f}")


def main() -> None:
    world = XRWorld()
    app = world.load_app(HelloPanelApp)

    # simulate a user pressing the button a couple of times
    app.button.click()
    app.button.click()

    world.run(fps=90, max_frames=180)  # ~2 seconds
    print(f"ran {world.frame_count} frames, final fps={world.fps:.1f}, latency={world.latency_ms:.2f}ms")


if __name__ == "__main__":
    main()
