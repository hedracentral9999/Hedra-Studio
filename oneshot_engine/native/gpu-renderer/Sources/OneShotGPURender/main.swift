import Foundation
import Metal
import VideoToolbox

struct FailureResult: Encodable {
    let success = false
    let error: String
}

struct PreflightResult: Encodable {
    let success: Bool
    let backend = "metal-videotoolbox"
    let metal: Bool
    let hardwareH264Encode: Bool
    let hardwareHEVCDecode: Bool

    enum CodingKeys: String, CodingKey {
        case success, backend, metal
        case hardwareH264Encode = "hardware_h264_encode"
        case hardwareHEVCDecode = "hardware_hevc_decode"
    }
}

func printJSON<T: Encodable>(_ value: T) {
    let encoder = JSONEncoder()
    encoder.outputFormatting = [.sortedKeys, .withoutEscapingSlashes]
    if let data = try? encoder.encode(value), let string = String(data: data, encoding: .utf8) {
        print(string)
    }
}

func hardwareH264EncoderAvailable() -> Bool {
    var session: VTCompressionSession?
    let specification = [
        kVTVideoEncoderSpecification_RequireHardwareAcceleratedVideoEncoder as String: true,
    ] as CFDictionary
    let status = VTCompressionSessionCreate(
        allocator: kCFAllocatorDefault,
        width: 16,
        height: 16,
        codecType: kCMVideoCodecType_H264,
        encoderSpecification: specification,
        imageBufferAttributes: nil,
        compressedDataAllocator: nil,
        outputCallback: nil,
        refcon: nil,
        compressionSessionOut: &session
    )
    if let session {
        VTCompressionSessionInvalidate(session)
    }
    return status == noErr && session != nil
}

if Array(CommandLine.arguments.dropFirst()) == ["--preflight"] {
    let metal = MTLCreateSystemDefaultDevice() != nil
    let h264 = hardwareH264EncoderAvailable()
    let hevc = VTIsHardwareDecodeSupported(kCMVideoCodecType_HEVC)
    let result = PreflightResult(
        success: metal && h264 && hevc,
        metal: metal,
        hardwareH264Encode: h264,
        hardwareHEVCDecode: hevc
    )
    printJSON(result)
    exit(result.success ? 0 : 1)
}

do {
    let options = try RenderOptions.parse(Array(CommandLine.arguments.dropFirst()))
    let result = try await GPURenderer(options: options).render()
    printJSON(result)
} catch {
    let message = (error as? LocalizedError)?.errorDescription ?? error.localizedDescription
    printJSON(FailureResult(error: message))
    exit(1)
}
