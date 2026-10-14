// Text recognition and face-quality scoring with Apple's Vision framework.
// Optional, macOS only: used by app/analysis.py instead of the portable engine (RapidOCR +
// face-region sharpness) only when VISION_ENGINE=apple is set; the app compiles it on first use.
// Reads image paths from stdin (one per line) and prints one JSON object per line:
//   {"path": ..., "text": [...], "faces": [quality 0..1, ...]}  or  {"path": ..., "error": "..."}
// Images are only read. Build: swiftc -O tools/dkvision.swift -o data/bin/dkvision
import Foundation
import Vision
import ImageIO

func loadImage(_ path: String, maxPixels: Int) -> CGImage? {
    guard let src = CGImageSourceCreateWithURL(URL(fileURLWithPath: path) as CFURL, nil) else { return nil }
    let opts: [CFString: Any] = [
        kCGImageSourceCreateThumbnailFromImageAlways: true,
        kCGImageSourceCreateThumbnailWithTransform: true,
        kCGImageSourceThumbnailMaxPixelSize: maxPixels,
    ]
    return CGImageSourceCreateThumbnailAtIndex(src, 0, opts as CFDictionary)
}

func emit(_ obj: [String: Any]) {
    if let data = try? JSONSerialization.data(withJSONObject: obj), let s = String(data: data, encoding: .utf8) {
        print(s)
        fflush(stdout)
    }
}

let maxPixels = CommandLine.arguments.count > 1 ? Int(CommandLine.arguments[1]) ?? 2048 : 2048
while let line = readLine() {
    let path = line.trimmingCharacters(in: .whitespacesAndNewlines)
    if path.isEmpty { continue }
    autoreleasepool {
        guard let image = loadImage(path, maxPixels: maxPixels) else {
            emit(["path": path, "error": "cannot read image"])
            return
        }
        let text = VNRecognizeTextRequest()
        text.recognitionLevel = .accurate
        text.usesLanguageCorrection = false
        let faces = VNDetectFaceCaptureQualityRequest()
        do {
            try VNImageRequestHandler(cgImage: image, options: [:]).perform([text, faces])
            let lines = (text.results ?? []).compactMap { $0.topCandidates(1).first }
                .filter { $0.confidence >= 0.5 }.map { $0.string }
            let quality = (faces.results ?? []).compactMap { $0.faceCaptureQuality.map { Double($0) } }
            emit(["path": path, "text": lines, "faces": quality])
        } catch {
            emit(["path": path, "error": "\(error.localizedDescription)"])
        }
    }
}
