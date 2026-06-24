@preconcurrency import AVFoundation
import CoreImage
import Foundation
import Metal
import VideoToolbox

struct RenderResult: Encodable {
    let success: Bool
    let backend: String
    let input: String
    let output: String
    let width: Int
    let height: Int
    let fps: Double
    let durationSeconds: Double
    let frames: Int
    let bitrate: Int
    let lutApplied: Bool
    let coverApplied: Bool
    let renderSeconds: Double

    enum CodingKeys: String, CodingKey {
        case success, backend, input, output, width, height, fps, frames, bitrate
        case durationSeconds = "duration_seconds"
        case lutApplied = "lut_applied"
        case coverApplied = "cover_applied"
        case renderSeconds = "render_seconds"
    }
}

final class GPURenderer: @unchecked Sendable {
    private let options: RenderOptions
    private let targetRect: CGRect
    private let colorSpace: CGColorSpace
    private let context: CIContext
    private let lut: CubeLUT?

    init(options: RenderOptions) throws {
        self.options = options
        self.targetRect = CGRect(x: 0, y: 0, width: options.width, height: options.height)
        guard let device = MTLCreateSystemDefaultDevice() else {
            throw RenderError.media("Metal is unavailable")
        }
        guard let colorSpace = CGColorSpace(name: CGColorSpace.itur_709) else {
            throw RenderError.media("Cannot create BT.709 color space")
        }
        self.colorSpace = colorSpace
        self.context = CIContext(
            mtlDevice: device,
            options: [
                .cacheIntermediates: false,
                .workingColorSpace: colorSpace,
                .outputColorSpace: colorSpace,
            ]
        )
        self.lut = try options.lut.map(CubeLUT.load(from:))
    }

    func render() async throws -> RenderResult {
        let startedAt = Date()
        guard FileManager.default.fileExists(atPath: options.input.path) else {
            throw RenderError.media("Input file does not exist: \(options.input.path)")
        }
        if let thumbnail = options.thumbnail, !FileManager.default.fileExists(atPath: thumbnail.path) {
            throw RenderError.media("Thumbnail file does not exist: \(thumbnail.path)")
        }
        try FileManager.default.createDirectory(
            at: options.output.deletingLastPathComponent(),
            withIntermediateDirectories: true
        )
        if FileManager.default.fileExists(atPath: options.output.path) {
            try FileManager.default.removeItem(at: options.output)
        }

        let asset = AVAsset(url: options.input)
        guard let videoTrack = try await asset.loadTracks(withMediaType: .video).first else {
            throw RenderError.media("Input has no video track")
        }
        let loadedFPS = try await videoTrack.load(.nominalFrameRate)
        let nominalFPS = loadedFPS > 0 ? Double(loadedFPS) : 30
        let outputFPS = min(max(nominalFPS, 1), 60)
        let coverApplied = options.thumbnail != nil && options.coverDuration > 0
        let videoTimeRange = try await videoTrack.load(.timeRange)
        let preferredTransform = try await videoTrack.load(.preferredTransform)
        let assetDuration = try await asset.load(.duration)

        let reader = try AVAssetReader(asset: asset)
        let videoOutput = AVAssetReaderTrackOutput(
            track: videoTrack,
            outputSettings: [
                kCVPixelBufferPixelFormatTypeKey as String: kCVPixelFormatType_420YpCbCr8BiPlanarVideoRange,
                kCVPixelBufferMetalCompatibilityKey as String: true,
            ]
        )
        videoOutput.alwaysCopiesSampleData = false
        guard reader.canAdd(videoOutput) else { throw RenderError.media("Cannot configure video reader") }
        reader.add(videoOutput)

        let writer = try AVAssetWriter(outputURL: options.output, fileType: .mp4)
        let videoSettings: [String: Any] = [
            AVVideoCodecKey: AVVideoCodecType.h264,
            AVVideoWidthKey: options.width,
            AVVideoHeightKey: options.height,
            AVVideoColorPropertiesKey: [
                AVVideoColorPrimariesKey: AVVideoColorPrimaries_ITU_R_709_2,
                AVVideoTransferFunctionKey: AVVideoTransferFunction_ITU_R_709_2,
                AVVideoYCbCrMatrixKey: AVVideoYCbCrMatrix_ITU_R_709_2,
            ],
            AVVideoCompressionPropertiesKey: [
                AVVideoAverageBitRateKey: options.bitrate,
                AVVideoProfileLevelKey: kVTProfileLevel_H264_High_4_2 as String,
                AVVideoExpectedSourceFrameRateKey: Int(outputFPS.rounded()),
                AVVideoMaxKeyFrameIntervalDurationKey: 2,
            ],
        ]
        let videoInput = AVAssetWriterInput(mediaType: .video, outputSettings: videoSettings)
        videoInput.expectsMediaDataInRealTime = false
        guard writer.canAdd(videoInput) else { throw RenderError.writer("Cannot configure video writer") }
        writer.add(videoInput)

        let adaptor = AVAssetWriterInputPixelBufferAdaptor(
            assetWriterInput: videoInput,
            sourcePixelBufferAttributes: [
                kCVPixelBufferPixelFormatTypeKey as String: kCVPixelFormatType_32BGRA,
                kCVPixelBufferWidthKey as String: options.width,
                kCVPixelBufferHeightKey as String: options.height,
                kCVPixelBufferMetalCompatibilityKey as String: true,
                kCVPixelBufferIOSurfacePropertiesKey as String: [:],
            ]
        )

        guard writer.startWriting() else {
            throw RenderError.writer(writer.error?.localizedDescription ?? "Writer failed to start")
        }
        writer.startSession(atSourceTime: .zero)
        guard reader.startReading() else {
            writer.cancelWriting()
            throw RenderError.media(reader.error?.localizedDescription ?? "Reader failed to start")
        }

        let coverOffset = CMTime(seconds: coverApplied ? options.coverDuration : 0, preferredTimescale: 600_000)
        let timelineStart = videoTimeRange.start
        let errorBox = ConcurrentError()
        let frameCounter = LockedCounter()
        let group = DispatchGroup()
        let videoResources = UnsafeSendableBox((videoOutput, videoInput, adaptor, writer))

        group.enter()
        DispatchQueue(label: "oneshot-gpu-render.video", qos: .userInitiated).async {
            defer { group.leave() }
            do {
                let (videoOutput, videoInput, adaptor, writer) = videoResources.value
                try self.writeVideo(
                    output: videoOutput,
                    input: videoInput,
                    adaptor: adaptor,
                    transform: preferredTransform,
                    fps: outputFPS,
                    timelineStart: timelineStart,
                    coverOffset: coverOffset,
                    writer: writer,
                    frameCounter: frameCounter
                )
                videoInput.markAsFinished()
            } catch {
                errorBox.set(error)
            }
        }

        await withCheckedContinuation { continuation in
            group.notify(queue: .global(qos: .userInitiated)) {
                continuation.resume()
            }
        }
        if let error = errorBox.value {
            reader.cancelReading()
            writer.cancelWriting()
            throw error
        }
        if reader.status == .failed {
            writer.cancelWriting()
            throw RenderError.media(reader.error?.localizedDescription ?? "Reader failed")
        }

        await withCheckedContinuation { continuation in
            writer.finishWriting { continuation.resume() }
        }
        guard writer.status == .completed else {
            throw RenderError.writer(writer.error?.localizedDescription ?? "Writer failed")
        }

        let sourceDuration = max(0, assetDuration.seconds)
        return RenderResult(
            success: true,
            backend: "metal-videotoolbox",
            input: options.input.path,
            output: options.output.path,
            width: options.width,
            height: options.height,
            fps: outputFPS,
            durationSeconds: sourceDuration + coverOffset.seconds,
            frames: frameCounter.value,
            bitrate: options.bitrate,
            lutApplied: lut != nil && options.lutIntensity > 0,
            coverApplied: coverApplied,
            renderSeconds: Date().timeIntervalSince(startedAt)
        )
    }

    private func writeVideo(
        output: AVAssetReaderTrackOutput,
        input: AVAssetWriterInput,
        adaptor: AVAssetWriterInputPixelBufferAdaptor,
        transform: CGAffineTransform,
        fps: Double,
        timelineStart: CMTime,
        coverOffset: CMTime,
        writer: AVAssetWriter,
        frameCounter: LockedCounter
    ) throws {
        guard let pool = adaptor.pixelBufferPool else {
            throw RenderError.writer("Pixel buffer pool is unavailable")
        }

        if let thumbnail = options.thumbnail, coverOffset > .zero {
            guard let coverImage = CIImage(contentsOf: thumbnail, options: [.applyOrientationProperty: true]) else {
                throw RenderError.media("Cannot decode thumbnail: \(thumbnail.path)")
            }
            let image = aspectFill(coverImage)
            let count = Int(ceil(options.coverDuration * fps))
            for index in 0..<count {
                try waitUntilReady(input, writer: writer)
                let presentationTime = CMTime(value: CMTimeValue(index), timescale: CMTimeScale(fps.rounded()))
                try append(image: image, at: presentationTime, pool: pool, adaptor: adaptor)
                frameCounter.increment()
            }
        }

        var lastAccepted = CMTime.invalid
        let minimumFrameStep = CMTime(seconds: 1 / fps, preferredTimescale: 600_000)
        while let sample = output.copyNextSampleBuffer() {
            try autoreleasepool {
                guard let pixelBuffer = CMSampleBufferGetImageBuffer(sample) else {
                    throw RenderError.media("Video sample has no pixel buffer")
                }
                let sourcePTS = CMSampleBufferGetPresentationTimeStamp(sample) - timelineStart
                if lastAccepted.isValid && CMTimeCompare(
                    sourcePTS - lastAccepted,
                    CMTimeMultiplyByFloat64(minimumFrameStep, multiplier: 0.95)
                ) < 0 {
                    return
                }
                lastAccepted = sourcePTS
                try waitUntilReady(input, writer: writer)
                // AVFoundation's display transform is expressed in display coordinates;
                // Core Image uses the opposite rotation convention for pixel-space transforms.
                let source = CIImage(cvPixelBuffer: pixelBuffer).transformed(by: transform.inverted())
                var image = aspectFill(normalizeOrigin(source))
                image = applyLook(to: image)
                try append(image: image, at: sourcePTS + coverOffset, pool: pool, adaptor: adaptor)
                frameCounter.increment()
            }
        }
    }

    private func append(
        image: CIImage,
        at time: CMTime,
        pool: CVPixelBufferPool,
        adaptor: AVAssetWriterInputPixelBufferAdaptor
    ) throws {
        var outputBuffer: CVPixelBuffer?
        guard CVPixelBufferPoolCreatePixelBuffer(nil, pool, &outputBuffer) == kCVReturnSuccess,
              let outputBuffer else {
            throw RenderError.writer("Cannot allocate output pixel buffer")
        }
        context.render(image, to: outputBuffer, bounds: targetRect, colorSpace: colorSpace)
        guard adaptor.append(outputBuffer, withPresentationTime: time) else {
            throw RenderError.writer("Video append failed")
        }
    }

    private func applyLook(to image: CIImage) -> CIImage {
        var result = image
        if let lut, options.lutIntensity > 0 {
            let span = lut.domainMax - lut.domainMin
            let scale = SIMD3<Float>(repeating: 1) / span
            let bias = -lut.domainMin * scale
            let domainFilter = CIFilter(name: "CIColorMatrix")!
            domainFilter.setValue(result, forKey: kCIInputImageKey)
            domainFilter.setValue(CIVector(x: CGFloat(scale.x), y: 0, z: 0, w: 0), forKey: "inputRVector")
            domainFilter.setValue(CIVector(x: 0, y: CGFloat(scale.y), z: 0, w: 0), forKey: "inputGVector")
            domainFilter.setValue(CIVector(x: 0, y: 0, z: CGFloat(scale.z), w: 0), forKey: "inputBVector")
            domainFilter.setValue(CIVector(x: CGFloat(bias.x), y: CGFloat(bias.y), z: CGFloat(bias.z), w: 0), forKey: "inputBiasVector")

            let cubeFilter = CIFilter(name: "CIColorCubeWithColorSpace")!
            cubeFilter.setValue(domainFilter.outputImage!, forKey: kCIInputImageKey)
            cubeFilter.setValue(lut.dimension, forKey: "inputCubeDimension")
            cubeFilter.setValue(lut.data, forKey: "inputCubeData")
            cubeFilter.setValue(colorSpace, forKey: "inputColorSpace")
            let blend = CIFilter(name: "CIBlendWithMask")!
            blend.setValue(cubeFilter.outputImage!, forKey: kCIInputImageKey)
            blend.setValue(image, forKey: kCIInputBackgroundImageKey)
            let mask = CIImage(
                color: CIColor(
                    red: CGFloat(options.lutIntensity),
                    green: CGFloat(options.lutIntensity),
                    blue: CGFloat(options.lutIntensity),
                    alpha: 1
                )
            ).cropped(to: image.extent)
            blend.setValue(mask, forKey: kCIInputMaskImageKey)
            result = blend.outputImage ?? image
        }

        let controls = CIFilter(name: "CIColorControls")!
        controls.setValue(result, forKey: kCIInputImageKey)
        controls.setValue(1.05, forKey: kCIInputContrastKey)
        controls.setValue(1.10, forKey: kCIInputSaturationKey)
        // Core Image evaluates brightness in its RGB working space; -0.06
        // visually matches FFmpeg eq=brightness=0.02 after video-range conversion.
        controls.setValue(-0.06, forKey: kCIInputBrightnessKey)

        let sharpen = CIFilter(name: "CISharpenLuminance")!
        sharpen.setValue(controls.outputImage!, forKey: kCIInputImageKey)
        sharpen.setValue(0.8, forKey: kCIInputSharpnessKey)
        return sharpen.outputImage!.cropped(to: targetRect)
    }

    private func normalizeOrigin(_ image: CIImage) -> CIImage {
        image.transformed(by: CGAffineTransform(
            translationX: -image.extent.minX,
            y: -image.extent.minY
        ))
    }

    private func aspectFill(_ image: CIImage) -> CIImage {
        let scale = max(targetRect.width / image.extent.width, targetRect.height / image.extent.height)
        let scaled = image.transformed(by: CGAffineTransform(scaleX: scale, y: scale))
        let crop = CGRect(
            x: scaled.extent.midX - targetRect.width / 2,
            y: scaled.extent.midY - targetRect.height / 2,
            width: targetRect.width,
            height: targetRect.height
        )
        return scaled.cropped(to: crop).transformed(by: CGAffineTransform(translationX: -crop.minX, y: -crop.minY))
    }

    private func waitUntilReady(_ input: AVAssetWriterInput, writer: AVAssetWriter) throws {
        while !input.isReadyForMoreMediaData {
            if writer.status == .failed || writer.status == .cancelled {
                throw RenderError.writer(writer.error?.localizedDescription ?? "Writer failed")
            }
            Thread.sleep(forTimeInterval: 0.002)
        }
    }

}

private final class ConcurrentError: @unchecked Sendable {
    private let lock = NSLock()
    private var stored: Error?
    var value: Error? { lock.withLock { stored } }
    func set(_ error: Error) { lock.withLock { if stored == nil { stored = error } } }
}

final class LockedCounter: @unchecked Sendable {
    private let lock = NSLock()
    private var stored = 0
    var value: Int { lock.withLock { stored } }
    func increment() { lock.withLock { stored += 1 } }
}

private final class UnsafeSendableBox<Value>: @unchecked Sendable {
    let value: Value
    init(_ value: Value) { self.value = value }
}

private extension NSLock {
    func withLock<T>(_ body: () -> T) -> T {
        lock()
        defer { unlock() }
        return body()
    }
}
