// swift-tools-version: 5.9

import PackageDescription

let package = Package(
    name: "OneShotGPURender",
    platforms: [.macOS(.v13)],
    products: [
        .executable(name: "oneshot-gpu-render", targets: ["OneShotGPURender"]),
    ],
    targets: [
        .executableTarget(name: "OneShotGPURender"),
    ]
)
