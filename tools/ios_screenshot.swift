#!/usr/bin/env swift
// ios_screenshot.swift - Capture iPhone screen via USB using AVFoundation/CoreMediaIO
// Usage: swift ios_screenshot.swift [output_path]

import AVFoundation
import CoreImage
import CoreMediaIO
import Foundation

// 1. Enable screen capture devices (required opt-in for iOS device video)
var property = CMIOObjectPropertyAddress(
    mSelector: CMIOObjectPropertySelector(kCMIOHardwarePropertyAllowScreenCaptureDevices),
    mScope: CMIOObjectPropertyScope(kCMIOObjectPropertyScopeGlobal),
    mElement: CMIOObjectPropertyElement(kCMIOObjectPropertyElementMain)
)
var allow: UInt32 = 1
CMIOObjectSetPropertyData(
    CMIOObjectID(kCMIOObjectSystemObject),
    &property, 0, nil,
    UInt32(MemoryLayout<UInt32>.size), &allow
)

// 2. Wait for device discovery
Thread.sleep(forTimeInterval: 2.0)

// 3. Discover external (USB) devices
let discovery = AVCaptureDevice.DiscoverySession(
    deviceTypes: [.external],
    mediaType: .muxed,
    position: .unspecified
)

let devices = discovery.devices
if devices.isEmpty {
    fputs("No external capture devices found. Ensure iPhone is connected, unlocked, and trusted.\n", stderr)
    exit(1)
}

let device = devices[0]
fputs("Found device: \(device.localizedName) (\(device.uniqueID))\n", stderr)

// 4. Set up capture session
let session = AVCaptureSession()
session.sessionPreset = .high

guard let input = try? AVCaptureDeviceInput(device: device) else {
    fputs("Failed to create capture input\n", stderr)
    exit(1)
}

guard session.canAddInput(input) else {
    fputs("Cannot add input to session\n", stderr)
    exit(1)
}
session.addInput(input)

// 5. Set up video output
let output = AVCaptureVideoDataOutput()
output.videoSettings = [
    kCVPixelBufferPixelFormatTypeKey as String: kCVPixelFormatType_32BGRA
]

guard session.canAddOutput(output) else {
    fputs("Cannot add output to session\n", stderr)
    exit(1)
}
session.addOutput(output)

// 6. Capture delegate to grab a single frame
class FrameGrabber: NSObject, AVCaptureVideoDataOutputSampleBufferDelegate {
    var outputPath: String
    var captured = false
    let semaphore = DispatchSemaphore(value: 0)

    init(outputPath: String) {
        self.outputPath = outputPath
    }

    func captureOutput(
        _ output: AVCaptureOutput,
        didOutput sampleBuffer: CMSampleBuffer,
        from connection: AVCaptureConnection
    ) {
        guard !captured else { return }
        captured = true

        guard let pixelBuffer = CMSampleBufferGetImageBuffer(sampleBuffer) else {
            fputs("Failed to get pixel buffer\n", stderr)
            semaphore.signal()
            return
        }

        let ciImage = CIImage(cvPixelBuffer: pixelBuffer)
        let context = CIContext()

        guard let cgImage = context.createCGImage(ciImage, from: ciImage.extent) else {
            fputs("Failed to create CGImage\n", stderr)
            semaphore.signal()
            return
        }

        let url = URL(fileURLWithPath: outputPath)
        guard let dest = CGImageDestinationCreateWithURL(url as CFURL, "public.png" as CFString, 1, nil) else {
            fputs("Failed to create image destination\n", stderr)
            semaphore.signal()
            return
        }

        CGImageDestinationAddImage(dest, cgImage, nil)
        if CGImageDestinationFinalize(dest) {
            let w = cgImage.width
            let h = cgImage.height
            fputs("Screenshot saved: \(outputPath) (\(w)x\(h))\n", stderr)
        } else {
            fputs("Failed to write PNG\n", stderr)
        }

        semaphore.signal()
    }
}

let outputPath = CommandLine.arguments.count > 1
    ? CommandLine.arguments[1]
    : "/tmp/ios_screenshot.png"

let grabber = FrameGrabber(outputPath: outputPath)
let queue = DispatchQueue(label: "screenshot")
output.setSampleBufferDelegate(grabber, queue: queue)

// 7. Start capture
session.startRunning()
fputs("Waiting for frame...\n", stderr)

// Wait up to 10 seconds for a frame
let result = grabber.semaphore.wait(timeout: .now() + 10.0)
session.stopRunning()

if result == .timedOut {
    fputs("Timeout waiting for frame. Is the iPhone screen on?\n", stderr)
    exit(1)
}

exit(0)
