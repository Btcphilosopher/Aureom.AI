1. Core Swift ProMotion layer
For an 8K/120-Hz-class iPad, I'd build something like this:
import UIKit
import QuartzCore

final class ProMotionController {

    private var displayLink: CADisplayLink?
    
    private(set) var currentRefreshRate: Double = 60.0
    private(set) var frameDuration: Double = 1.0 / 60.0
    
    var onFrame: ((CADisplayLink, Double) -> Void)?

    init() {
        createDisplayLink()
    }

    private func createDisplayLink() {

        let link = CADisplayLink(
            target: self,
            selector: #selector(displayLinkTick)
        )

        // Allow the system to select anything from 24–120 Hz.
        // 120 Hz is the preferred rate for interactive content.
        link.preferredFrameRateRange = CAFrameRateRange(
            minimum: 24,
            maximum: 120,
            preferred: 120
        )

        displayLink = link

        link.add(
            to: .main,
            forMode: .common
        )
    }

    @objc
    private func displayLinkTick(_ link: CADisplayLink) {

        let duration =
            link.targetTimestamp - link.timestamp

        guard duration > 0 else {
            return
        }

        frameDuration = duration
        currentRefreshRate = 1.0 / duration

        onFrame?(link, duration)
    }

    func setInteractiveMode() {

        displayLink?.preferredFrameRateRange =
            CAFrameRateRange(
                minimum: 80,
                maximum: 120,
                preferred: 120
            )
    }

    func setBalancedMode() {

        displayLink?.preferredFrameRateRange =
            CAFrameRateRange(
                minimum: 48,
                maximum: 120,
                preferred: 60
            )
    }

    func setPowerSavingMode() {

        displayLink?.preferredFrameRateRange =
            CAFrameRateRange(
                minimum: 24,
                maximum: 60,
                preferred: 30
            )
    }

    func stop() {
        displayLink?.invalidate()
        displayLink = nil
    }

    deinit {
        displayLink?.invalidate()
    }
}

The critical point is not to assume you're actually running at 120 Hz. The OS can change the refresh rate because of thermal conditions, power management and other system policies. Your rendering loop therefore measures the actual interval using targetTimestamp - timestamp. Apple Developer
2. For an actual 8K iPad, I'd go further
At 8K resolution, the problem becomes much more interesting.
An 8K panel is approximately:
7680 × 4320 = 33.2 million pixels/frame
At 120 Hz:
~3.98 billion pixels/second
So you don't want every application simply attempting to redraw the entire 8K framebuffer 120 times a second.
I'd architect the rendering system around:
                    ┌─────────────────────┐
                    │   SwiftUI / UIKit   │
                    └──────────┬──────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │ ProMotion Scheduler  │
                    │                     │
                    │ 24–120 Hz           │
                    └──────────┬──────────┘
                               │
                 ┌─────────────┴─────────────┐
                 ▼                           ▼
        ┌─────────────────┐        ┌─────────────────┐
        │ Core Animation  │        │      Metal      │
        │ UI composition  │        │  8K rendering   │
        └────────┬────────┘        └────────┬────────┘
                 │                          │
                 └────────────┬─────────────┘
                              ▼
                   ┌─────────────────────┐
                   │ Display Controller  │
                   │                     │
                   │ OLED / 8K / VRR     │
                   └─────────────────────┘

For ordinary SwiftUI/UIKit applications, Apple already handles frame pacing automatically. You mainly need custom display-link logic when you're doing specialised rendering. Apple Developer
3. An 8K Metal renderer
For serious 8K workloads, I'd use Metal rather than attempting to draw everything through CPU-side Swift.
For example:
import Metal
import MetalKit
import QuartzCore

final class EightKRenderer: NSObject, MTKViewDelegate {

    private let device: MTLDevice
    private let commandQueue: MTLCommandQueue

    private var lastTime: CFTimeInterval = 0

    init?(view: MTKView) {

        guard let device = MTLCreateSystemDefaultDevice(),
              let queue = device.makeCommandQueue()
        else {
            return nil
        }

        self.device = device
        self.commandQueue = queue

        super.init()

        view.device = device
        view.delegate = self

        view.colorPixelFormat = .bgra8Unorm
        view.framebufferOnly = true

        // Let the display system determine actual pacing.
        view.preferredFramesPerSecond = 120
    }

    func draw(in view: MTKView) {

        guard
            let commandBuffer = commandQueue.makeCommandBuffer(),
            let drawable = view.currentDrawable
        else {
            return
        }

        let currentTime = CACurrentMediaTime()

        let deltaTime: Double

        if lastTime == 0 {
            deltaTime = 1.0 / 120.0
        } else {
            deltaTime = currentTime - lastTime
        }

        lastTime = currentTime

        // Update simulation using actual elapsed time.
        update(deltaTime: deltaTime)

        let passDescriptor =
            view.currentRenderPassDescriptor

        if let descriptor = passDescriptor,
           let encoder =
            commandBuffer.makeRenderCommandEncoder(
                descriptor: descriptor
            ) {

            render(
                encoder: encoder,
                deltaTime: deltaTime
            )

            encoder.endEncoding()
        }

        commandBuffer.present(drawable)
        commandBuffer.commit()
    }

    private func update(deltaTime: Double) {

        // Physics / animation / simulation
    }

    private func render(
        encoder: MTLRenderCommandEncoder,
        deltaTime: Double
    ) {

        // GPU rendering
    }

    func mtkView(
        _ view: MTKView,
        drawableSizeWillChange size: CGSize
    ) {

        // Handle 8K / external-display / orientation changes.
    }
}

One caveat: preferredFramesPerSecond is deprecated in the modern CADisplayLink API in favour of preferredFrameRateRange; for a production implementation I'd build the newer frame-rate architecture rather than hard-code 120 FPS. Apple Developer
4. Adaptive 8K quality
This is where I'd make the hypothetical Apple implementation much more sophisticated.
You could have:
enum RenderQuality {
    case ultra
    case high
    case balanced
    case powerSaving
}

final class AdaptiveRenderer {

    var quality: RenderQuality = .ultra

    func selectQuality(
        refreshRate: Double,
        gpuFrameTime: Double,
        thermalPressure: Double
    ) {

        if thermalPressure > 0.8 {

            quality = .powerSaving

        } else if gpuFrameTime > 0.010 {

            quality = .balanced

        } else if refreshRate >= 100 {

            quality = .ultra

        } else {

            quality = .high
        }
    }
}

But don't continuously oscillate quality based on instantaneous frame timing. Apple explicitly warns that dynamically changing rendering quality in response to refresh rate can create undesirable feedback loops and GPU throttling. Apple Developer
I'd instead use hysteresis:
120 Hz
 │
 │ GPU comfortable
 ▼
8K Ultra
 │
 │ sustained GPU pressure
 ▼
8K High
 │
 │ thermal pressure
 ▼
8K Balanced
 │
 │ severe power constraint
 ▼
Lower rendering resolution

5. The really important part: 8K doesn't necessarily mean 8K rendering
For an Apple-style system, I'd separate:
DISPLAY RESOLUTION
       ↓
7680 × 4320 OLED

UI RESOLUTION
       ↓
Logical points / Retina scaling

RENDER RESOLUTION
       ↓
Dynamic GPU resolution

TEXT
       ↓
Vector / Core Text rendering

PHOTOS
       ↓
Native-resolution assets

VIDEO
       ↓
Hardware decode + appropriate scaling

3D
       ↓
Metal dynamic resolution

That lets the system maintain the appearance of an 8K interface without forcing every GPU operation to happen at 33 million pixels.
6. ProMotion modes I'd define
For the hypothetical device:
Mode	Range	Use
Ultra Smooth	80–120 Hz	Scrolling, Apple Pencil, UI
Normal	48–120 Hz	General applications
Cinema	24–48 Hz	24 fps/film
Static	1–10 Hz*	Reading/static content
Gaming	60–120 Hz	Games
Power	24–60 Hz	Battery saving


*The exact minimum would be a hardware/OS property, not something an app can simply invent. Apple's current iPad Pro ProMotion range is documented as 24–120 Hz. Apple Developer
7. Apple Pencil should be treated differently
For an 8K iPad, I'd make Pencil input a first-class high-frequency path:
final class PencilRenderer {

    func process(
        point: CGPoint,
        force: CGFloat,
        azimuth: CGFloat,
        altitude: CGFloat
    ) {

        // Predict stroke position
        // Update vector stroke
        // Render only affected regions
    }
}

The important idea is:
don't redraw the entire 8K canvas for every Pencil event.
Instead:
Pencil event
     ↓
Stroke prediction
     ↓
Dirty region
     ↓
Metal tile
     ↓
GPU composite
     ↓
OLED

That becomes particularly important when you're dealing with an enormous 8K canvas.
8. What you'd actually need to build
If your goal is essentially "Apple ProMotion for a hypothetical 8K OLED iPad", I'd divide the project into:
Swift / iPadOS
ProMotionController.swift
DisplayScheduler.swift
FramePacing.swift
AdaptiveQuality.swift
ThermalPolicy.swift
PowerPolicy.swift
PencilRenderer.swift
AnimationScheduler.swift

Metal
EightKRenderer.swift
EightKShaders.metal
DynamicResolution.metal
TileRenderer.metal
OLEDComposite.metal

UI
SwiftUI
UIKit
Core Animation
Core Text
MetalKit

Hardware/OS layer
This is the part you cannot implement purely in Swift:
OLED panel driver
Display controller
VRR hardware
GPU display pipeline
EDR/HDR pipeline
panel timing controller
memory bandwidth
thermal management
power management
color management






For a 4K OLED iPad running at a fixed 60 Hz, the architecture becomes considerably simpler. You don't need adaptive ProMotion/VRR logic; the main objective is reliable 60 FPS frame pacing, efficient 4K rendering, HDR/OLED support, and avoiding unnecessary redraws.
1. Core 60 Hz display controller
import UIKit
import QuartzCore

final class DisplayController {

    private var displayLink: CADisplayLink?

    private(set) var refreshRate: Double = 60.0
    private(set) var frameDuration: Double = 1.0 / 60.0

    var onFrame: ((CADisplayLink, Double) -> Void)?

    init() {
        createDisplayLink()
    }

    private func createDisplayLink() {

        let link = CADisplayLink(
            target: self,
            selector: #selector(displayLinkTick)
        )

        link.preferredFrameRateRange = CAFrameRateRange(
            minimum: 60,
            maximum: 60,
            preferred: 60
        )

        displayLink = link

        link.add(
            to: .main,
            forMode: .common
        )
    }

    @objc
    private func displayLinkTick(_ link: CADisplayLink) {

        let duration =
            link.targetTimestamp - link.timestamp

        guard duration > 0 else {
            return
        }

        frameDuration = duration
        refreshRate = 1.0 / duration

        onFrame?(link, duration)
    }

    func stop() {
        displayLink?.invalidate()
        displayLink = nil
    }

    deinit {
        displayLink?.invalidate()
    }
}

The important target is simply:
60 Hz
↓
16.67 ms
↓
one frame every 16.67 ms

You don't need the 24–120 Hz scheduling system from the previous version.
2. 4K Metal renderer
For a high-performance 4K application, I'd use Metal:
import Metal
import MetalKit
import QuartzCore

final class FourKRenderer: NSObject, MTKViewDelegate {

    private let device: MTLDevice
    private let commandQueue: MTLCommandQueue

    private var lastFrameTime: CFTimeInterval = 0

    init?(view: MTKView) {

        guard
            let device = MTLCreateSystemDefaultDevice(),
            let queue = device.makeCommandQueue()
        else {
            return nil
        }

        self.device = device
        self.commandQueue = queue

        super.init()

        view.device = device
        view.delegate = self

        view.colorPixelFormat = .bgra8Unorm
        view.framebufferOnly = true

        // Fixed 60 Hz rendering target.
        view.preferredFramesPerSecond = 60
    }

    func draw(in view: MTKView) {

        guard
            let commandBuffer =
                commandQueue.makeCommandBuffer(),

            let drawable =
                view.currentDrawable
        else {
            return
        }

        let now = CACurrentMediaTime()

        let deltaTime: Double

        if lastFrameTime == 0 {
            deltaTime = 1.0 / 60.0
        } else {
            deltaTime =
                now - lastFrameTime
        }

        lastFrameTime = now

        update(
            deltaTime: deltaTime
        )

        if let descriptor =
            view.currentRenderPassDescriptor {

            let encoder =
                commandBuffer.makeRenderCommandEncoder(
                    descriptor: descriptor
                )

            encoder?.endEncoding()
        }

        commandBuffer.present(drawable)
        commandBuffer.commit()
    }

    private func update(deltaTime: Double) {

        // Animation
        // Physics
        // Simulation
        // Application state
    }

    func mtkView(
        _ view: MTKView,
        drawableSizeWillChange size: CGSize
    ) {

        // Respond to resolution/orientation changes.
    }
}

3. 4K resolution
A 4K display is approximately:
3840 × 2160

= 8,294,400 pixels

At 60 Hz:
8.29 million pixels × 60
≈ 498 million pixels/second

That's still a substantial GPU workload, but dramatically easier than 8K at 120 Hz.
I'd therefore target:
3840 × 2160
60 FPS
16.67 ms frame budget

4. Frame budget
Your application effectively gets:
┌──────────────────────────────┐
│        16.67 ms              │
├──────────┬──────────┬────────┤
│ CPU      │ GPU      │ Present│
│ work     │ rendering│        │
└──────────┴──────────┴────────┘

For a demanding application, I'd aim for something like:
CPU simulation       < 3 ms
Metal encoding       < 2 ms
GPU rendering        < 10 ms
presentation         < 1 ms
----------------------------
total                < 16.67 ms

The exact split depends heavily on the application.
5. 4K OLED HDR
If the hypothetical iPad has a high-quality OLED panel, I'd also design the renderer around extended dynamic range.
For example:
view.colorPixelFormat = .rgba16Float

rather than limiting the rendering pipeline to 8-bit SDR.
A production HDR pipeline would involve:
Metal
  ↓
16-bit / floating-point rendering
  ↓
Extended Dynamic Range
  ↓
Color management
  ↓
HDR tone mapping
  ↓
OLED

You would also want to investigate Apple's EDR APIs rather than implementing your own OLED brightness model.
6. Don't redraw static content
This is particularly important at 4K.
If the screen hasn't changed:
NO STATE CHANGE
      ↓
NO NEW FRAME
      ↓
NO GPU WORK

For an application such as a document reader, dashboard or photo viewer, you don't necessarily want to execute a full 4K render pipeline 60 times per second.
For animation:
animation active
      ↓
60 FPS

For static content:
animation stopped
      ↓
render once
      ↓
hold frame

7. Apple Pencil / drawing
For a 4K drawing application I'd use a separate input path:
final class PencilRenderer {

    func addPoint(
        _ point: CGPoint,
        force: CGFloat,
        azimuth: CGFloat,
        altitude: CGFloat
    ) {

        // Add point to vector stroke.
        // Update stroke geometry.
        // Mark affected region as dirty.
    }
}




