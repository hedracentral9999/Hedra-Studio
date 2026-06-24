import Foundation

struct RenderOptions {
    let input: URL
    let output: URL
    let lut: URL?
    let lutIntensity: Float
    let thumbnail: URL?
    let coverDuration: Double
    let width: Int
    let height: Int
    let bitrate: Int

    static func parse(_ arguments: [String]) throws -> RenderOptions {
        var values: [String: String] = [:]
        var index = 0
        while index < arguments.count {
            let key = arguments[index]
            guard key.hasPrefix("--") else {
                throw RenderError.invalidArguments("Unexpected argument: \(key)")
            }
            guard index + 1 < arguments.count else {
                throw RenderError.invalidArguments("Missing value for \(key)")
            }
            values[key] = arguments[index + 1]
            index += 2
        }

        guard let inputPath = values["--input"], let outputPath = values["--output"] else {
            throw RenderError.invalidArguments("--input and --output are required")
        }

        let known = Set([
            "--input", "--output", "--lut", "--lut-intensity", "--thumbnail",
            "--cover-duration", "--width", "--height", "--bitrate",
        ])
        if let unknown = values.keys.first(where: { !known.contains($0) }) {
            throw RenderError.invalidArguments("Unknown option: \(unknown)")
        }

        let intensity = try floatValue(values["--lut-intensity"], default: 1, name: "--lut-intensity")
        let coverDuration = try doubleValue(values["--cover-duration"], default: 0.28, name: "--cover-duration")
        let width = try intValue(values["--width"], default: 1080, name: "--width")
        let height = try intValue(values["--height"], default: 1920, name: "--height")
        let bitrate = try intValue(values["--bitrate"], default: 16_000_000, name: "--bitrate")

        guard (0...1).contains(intensity) else {
            throw RenderError.invalidArguments("--lut-intensity must be between 0 and 1")
        }
        guard coverDuration >= 0 else {
            throw RenderError.invalidArguments("--cover-duration must be non-negative")
        }
        guard width > 0, height > 0, width.isMultiple(of: 2), height.isMultiple(of: 2) else {
            throw RenderError.invalidArguments("--width and --height must be positive even integers")
        }
        guard bitrate > 0 else {
            throw RenderError.invalidArguments("--bitrate must be positive")
        }

        return RenderOptions(
            input: URL(fileURLWithPath: inputPath),
            output: URL(fileURLWithPath: outputPath),
            lut: values["--lut"].map(URL.init(fileURLWithPath:)),
            lutIntensity: intensity,
            thumbnail: values["--thumbnail"].map(URL.init(fileURLWithPath:)),
            coverDuration: coverDuration,
            width: width,
            height: height,
            bitrate: bitrate
        )
    }

    private static func intValue(_ raw: String?, default defaultValue: Int, name: String) throws -> Int {
        guard let raw else { return defaultValue }
        guard let value = Int(raw) else { throw RenderError.invalidArguments("Invalid integer for \(name): \(raw)") }
        return value
    }

    private static func floatValue(_ raw: String?, default defaultValue: Float, name: String) throws -> Float {
        guard let raw else { return defaultValue }
        guard let value = Float(raw), value.isFinite else { throw RenderError.invalidArguments("Invalid number for \(name): \(raw)") }
        return value
    }

    private static func doubleValue(_ raw: String?, default defaultValue: Double, name: String) throws -> Double {
        guard let raw else { return defaultValue }
        guard let value = Double(raw), value.isFinite else { throw RenderError.invalidArguments("Invalid number for \(name): \(raw)") }
        return value
    }
}

enum RenderError: LocalizedError {
    case invalidArguments(String)
    case media(String)
    case lut(String)
    case writer(String)

    var errorDescription: String? {
        switch self {
        case .invalidArguments(let message), .media(let message), .lut(let message), .writer(let message):
            return message
        }
    }
}
