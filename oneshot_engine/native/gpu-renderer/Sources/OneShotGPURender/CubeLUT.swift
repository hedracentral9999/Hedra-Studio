import CoreImage
import Foundation

struct CubeLUT {
    let dimension: Int
    let domainMin: SIMD3<Float>
    let domainMax: SIMD3<Float>
    let data: Data

    static func load(from url: URL) throws -> CubeLUT {
        let text: String
        do {
            text = try String(contentsOf: url, encoding: .utf8)
        } catch {
            throw RenderError.lut("Cannot read LUT: \(error.localizedDescription)")
        }

        var dimension: Int?
        var domainMin = SIMD3<Float>(repeating: 0)
        var domainMax = SIMD3<Float>(repeating: 1)
        var entries: [SIMD3<Float>] = []

        for (lineNumber, sourceLine) in text.components(separatedBy: .newlines).enumerated() {
            let uncommented = sourceLine.firstIndex(of: "#").map { String(sourceLine[..<$0]) } ?? sourceLine
            let line = uncommented.trimmingCharacters(in: .whitespacesAndNewlines)
            if line.isEmpty { continue }
            let fields = line.split(whereSeparator: { $0.isWhitespace }).map(String.init)
            guard let keyword = fields.first else { continue }

            switch keyword.uppercased() {
            case "TITLE":
                continue
            case "LUT_3D_SIZE":
                guard fields.count == 2, let size = Int(fields[1]), (2...128).contains(size) else {
                    throw RenderError.lut("Invalid LUT_3D_SIZE at line \(lineNumber + 1)")
                }
                dimension = size
            case "DOMAIN_MIN":
                domainMin = try vector(fields, lineNumber: lineNumber)
            case "DOMAIN_MAX":
                domainMax = try vector(fields, lineNumber: lineNumber)
            case "LUT_1D_SIZE":
                throw RenderError.lut("1D .cube LUTs are not supported")
            default:
                guard fields.count == 3,
                      let red = Float(fields[0]), let green = Float(fields[1]), let blue = Float(fields[2]),
                      red.isFinite, green.isFinite, blue.isFinite else {
                    throw RenderError.lut("Invalid LUT data at line \(lineNumber + 1)")
                }
                entries.append(SIMD3(red, green, blue))
            }
        }

        guard let dimension else { throw RenderError.lut("Missing LUT_3D_SIZE") }
        let expected = dimension * dimension * dimension
        guard entries.count == expected else {
            throw RenderError.lut("Expected \(expected) LUT entries, found \(entries.count)")
        }
        guard all(domainMax .> domainMin) else {
            throw RenderError.lut("DOMAIN_MAX must be greater than DOMAIN_MIN")
        }

        var rgba: [Float] = []
        rgba.reserveCapacity(expected * 4)
        for entry in entries {
            rgba.append(contentsOf: [entry.x, entry.y, entry.z, 1])
        }
        return CubeLUT(
            dimension: dimension,
            domainMin: domainMin,
            domainMax: domainMax,
            data: rgba.withUnsafeBufferPointer { Data(buffer: $0) }
        )
    }

    private static func vector(_ fields: [String], lineNumber: Int) throws -> SIMD3<Float> {
        guard fields.count == 4,
              let x = Float(fields[1]), let y = Float(fields[2]), let z = Float(fields[3]),
              x.isFinite, y.isFinite, z.isFinite else {
            throw RenderError.lut("Invalid domain at line \(lineNumber + 1)")
        }
        return SIMD3(x, y, z)
    }
}
