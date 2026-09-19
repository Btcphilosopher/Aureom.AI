//
//  SiriLatencyEngine.swift
//
//  Pure Swift / native iOS
//
//  Objective:
//      Minimise perceived latency between:
//          speech -> understanding -> action -> response
//
//  Architecture:
//
//      Microphone
//          |
//          v
//      Voice Activity Detection
//          |
//          v
//      Speech Chunker
//          |
//          +--------------------+
//          |                    |
//          v                    v
//      Acoustic Analysis    Partial Recognition
//          |                    |
//          +----------+---------+
//                     |
//                     v
//              Intent Predictor
//                     |
//                     v
//               Context Engine
//                     |
//                     v
//              Speculative Action
//                     |
//                     v
//              Response Engine
//
//  No Python.
//  No Julia.
//  No external runtime.
//

import Foundation
import AVFoundation
import Accelerate
import os


// ============================================================
// MARK: - Clock
// ============================================================

@inline(__always)
func nowNs() -> UInt64 {

    DispatchTime
        .now()
        .uptimeNanoseconds
}


// ============================================================
// MARK: - Latency Measurement
// ============================================================

struct LatencyMeasurement {

    let microphone: UInt64
    let vad: UInt64
    let featureExtraction: UInt64
    let recognition: UInt64
    let intent: UInt64
    let planning: UInt64
    let action: UInt64
    let response: UInt64

    var total: UInt64 {

        response - microphone
    }

    var totalMilliseconds: Double {

        Double(total) / 1_000_000.0
    }
}


// ============================================================
// MARK: - Pipeline Clock
// ============================================================

final class PipelineClock {

    private var marks:
        [String: UInt64] = [:]

    func mark(
        _ name: String
    ) {

        marks[name] =
            nowNs()
    }

    func interval(
        from start: String,
        to end: String
    ) -> UInt64 {

        guard
            let a = marks[start],
            let b = marks[end]
        else {
            return 0
        }

        return b - a
    }

    func milliseconds(
        from start: String,
        to end: String
    ) -> Double {

        Double(
            interval(
                from: start,
                to: end
            )
        ) / 1_000_000.0
    }
}


// ============================================================
// MARK: - VAD
// ============================================================

final class VoiceActivityDetector {

    private let threshold:
        Float

    private let silenceDuration:
        TimeInterval

    private var silenceStart:
        UInt64?

    private(set) var speaking =
        false

    init(
        threshold: Float = 0.008,
        silenceDuration:
            TimeInterval = 0.35
    ) {

        self.threshold =
            threshold

        self.silenceDuration =
            silenceDuration
    }


    func process(
        samples: [Float]
    ) -> Bool {

        guard !samples.isEmpty
        else {
            return false
        }

        var rms: Float = 0

        vDSP_rmsqv(
            samples,
            1,
            &rms,
            vDSP_Length(
                samples.count
            )
        )

        let voice =
            rms > threshold

        if voice {

            speaking = true

            silenceStart = nil

        } else if speaking {

            if silenceStart == nil {

                silenceStart =
                    nowNs()
            }

            if let start =
                silenceStart {

                let elapsed =
                    Double(
                        nowNs() - start
                    ) / 1_000_000_000

                if elapsed >=
                    silenceDuration {

                    speaking = false

                    silenceStart =
                        nil
                }
            }
        }

        return speaking
    }
}


// ============================================================
// MARK: - Speech Chunk
// ============================================================

struct SpeechChunk {

    let samples: [Float]

    let startTime:
        UInt64

    let endTime:
        UInt64
}


// ============================================================
// MARK: - Speech Chunker
// ============================================================

final class SpeechChunker {

    private var samples =
        [Float]()

    private var startTime:
        UInt64?

    func append(
        _ input: [Float]
    ) {

        if startTime == nil {

            startTime =
                nowNs()
        }

        samples.append(
            contentsOf:
                input
        )
    }


    func flush()
        -> SpeechChunk?
    {

        guard
            !samples.isEmpty,
            let start = startTime
        else {
            return nil
        }

        let result =
            SpeechChunk(

                samples:
                    samples,

                startTime:
                    start,

                endTime:
                    nowNs()
            )

        samples.removeAll(
            keepingCapacity: true
        )

        startTime = nil

        return result
    }
}


// ============================================================
// MARK: - Audio Preprocessor
// ============================================================

final class AudioPreprocessor {

    func mono(
        buffer:
            AVAudioPCMBuffer
    ) -> [Float] {

        guard
            let channels =
                buffer.floatChannelData
        else {
            return []
        }

        let channelCount =
            Int(
                buffer.format.channelCount
            )

        let frameCount =
            Int(
                buffer.frameLength
            )

        var output =
            [Float](
                repeating: 0,
                count:
                    frameCount
            )

        if channelCount == 1 {

            output.withUnsafeMutableBufferPointer {
                destination in

                destination
                    .baseAddress!
                    .assign(
                        from:
                            channels[0],
                        count:
                            frameCount
                    )
            }

            return output
        }

        let scale =
            1.0 /
            Float(channelCount)

        for channel in
            0..<channelCount {

            let source =
                channels[channel]

            for i in
                0..<frameCount {

                output[i] +=
                    source[i] *
                    scale
            }
        }

        return output
    }


    func removeDC(
        _ audio: [Float]
    ) -> [Float] {

        guard !audio.isEmpty
        else {
            return []
        }

        var mean: Float = 0

        vDSP_meanv(
            audio,
            1,
            &mean,
            vDSP_Length(
                audio.count
            )
        )

        return audio.map {
            $0 - mean
        }
    }
}


// ============================================================
// MARK: - Acoustic Snapshot
// ============================================================

struct AcousticSnapshot {

    let rms: Float

    let peak: Float

    let zeroCrossingRate:
        Float

    let duration:
        TimeInterval
}


// ============================================================
// MARK: - Acoustic Analyzer
// ============================================================

final class AcousticAnalyzer {

    func analyse(
        _ audio: [Float],
        sampleRate: Double
    ) -> AcousticSnapshot {

        guard !audio.isEmpty
        else {

            return AcousticSnapshot(
                rms: 0,
                peak: 0,
                zeroCrossingRate: 0,
                duration: 0
            )
        }

        var rms: Float = 0

        vDSP_rmsqv(
            audio,
            1,
            &rms,
            vDSP_Length(
                audio.count
            )
        )

        var peak: Float = 0

        vDSP_maxmgv(
            audio,
            1,
            &peak,
            vDSP_Length(
                audio.count
            )
        )

        var crossings = 0

        if audio.count > 1 {

            for i in
                1..<audio.count {

                if (
                    audio[i] >= 0
                    &&
                    audio[i - 1] < 0
                )
                ||
                (
                    audio[i] < 0
                    &&
                    audio[i - 1] >= 0
                ) {

                    crossings += 1
                }
            }
        }

        let zcr =
            Float(crossings) /
            Float(
                max(
                    1,
                    audio.count - 1
                )
            )

        return AcousticSnapshot(

            rms:
                rms,

            peak:
                peak,

            zeroCrossingRate:
                zcr,

            duration:
                Double(
                    audio.count
                ) /
                sampleRate
        )
    }
}


// ============================================================
// MARK: - Intent
// ============================================================

enum SiriIntent {

    case unknown

    case playMedia

    case pauseMedia

    case nextMedia

    case search

    case weather

    case navigation

    case reminder

    case timer

    case call

    case message

    case question

    case systemCommand
}


// ============================================================
// MARK: - Intent Prediction
// ============================================================

struct IntentPrediction {

    let intent:
        SiriIntent

    let confidence:
        Float

    let entities:
        [String: String]
}


// ============================================================
// MARK: - Fast Intent Engine
// ============================================================

final class FastIntentEngine {

    func predict(
        text: String
    ) -> IntentPrediction {

        let lower =
            text.lowercased()

        if lower.contains(
            "play"
        ) {

            return IntentPrediction(
                intent:
                    .playMedia,
                confidence:
                    0.95,
                entities:
                    extractMedia(
                        lower
                    )
            )
        }

        if lower.contains(
            "pause"
        ) {

            return IntentPrediction(
                intent:
                    .pauseMedia,
                confidence:
                    0.98,
                entities: [:]
            )
        }

        if lower.contains(
            "next"
        )
        ||
        lower.contains(
            "skip"
        ) {

            return IntentPrediction(
                intent:
                    .nextMedia,
                confidence:
                    0.97,
                entities: [:]
            )
        }

        if lower.contains(
            "weather"
        ) {

            return IntentPrediction(
                intent:
                    .weather,
                confidence:
                    0.96,
                entities: [:]
            )
        }

        if lower.contains(
            "remind me"
        ) {

            return IntentPrediction(
                intent:
                    .reminder,
                confidence:
                    0.94,
                entities: [:]
            )
        }

        if lower.contains(
            "timer"
        ) {

            return IntentPrediction(
                intent:
                    .timer,
                confidence:
                    0.96,
                entities: [:]
            )
        }

        if lower.contains(
            "call"
        ) {

            return IntentPrediction(
                intent:
                    .call,
                confidence:
                    0.93,
                entities: [:]
            )
        }

        if lower.contains(
            "message"
        )
        ||
        lower.contains(
            "text"
        ) {

            return IntentPrediction(
                intent:
                    .message,
                confidence:
                    0.92,
                entities: [:]
            )
        }

        if lower.hasPrefix(
            "what "
        )
        ||
        lower.hasPrefix(
            "who "
        )
        ||
        lower.hasPrefix(
            "where "
        )
        ||
        lower.hasPrefix(
            "when "
        )
        ||
        lower.hasPrefix(
            "why "
        )
        ||
        lower.hasPrefix(
            "how "
        ) {

            return IntentPrediction(
                intent:
                    .question,
                confidence:
                    0.85,
                entities: [:]
            )
        }

        return IntentPrediction(
            intent:
                .unknown,
            confidence:
                0.0,
            entities: [:]
        )
    }


    private func extractMedia(
        _ text: String
    ) -> [String: String] {

        guard
            let range =
                text.range(
                    of: "play "
                )
        else {
            return [:]
        }

        let media =
            String(
                text[
                    range.upperBound...
                ]
            )

        return [
            "media": media
        ]
    }
}


// ============================================================
// MARK: - Context
// ============================================================

actor SiriContext {

    private var recentText:
        [String] = []

    private var lastMedia:
        String?

    private var lastIntent:
        SiriIntent?

    func update(
        text: String,
        prediction:
            IntentPrediction
    ) {

        recentText.append(
            text
        )

        if recentText.count > 10 {

            recentText.removeFirst()
        }

        lastIntent =
            prediction.intent

        if let media =
            prediction.entities[
                "media"
            ] {

            lastMedia =
                media
        }
    }


    func previousMedia()
        -> String?
    {

        return lastMedia
    }


    func previousIntent()
        -> SiriIntent?
    {

        return lastIntent
    }
}


// ============================================================
// MARK: - Action
// ============================================================

struct SiriAction {

    let name:
        String

    let parameters:
        [String: String]
}


// ============================================================
// MARK: - Speculative Planner
// ============================================================

final class SpeculativePlanner {

    func plan(
        _ prediction:
            IntentPrediction
    ) -> SiriAction? {

        switch prediction.intent {

        case .playMedia:

            return SiriAction(
                name:
                    "play",
                parameters:
                    prediction.entities
            )

        case .pauseMedia:

            return SiriAction(
                name:
                    "pause",
                parameters: [:]
            )

        case .nextMedia:

            return SiriAction(
                name:
                    "next",
                parameters: [:]
            )

        case .weather:

            return SiriAction(
                name:
                    "weather",
                parameters: [:]
            )

        case .timer:

            return SiriAction(
                name:
                    "timer",
                parameters: [:]
            )

        default:

            return nil
        }
    }
}


// ============================================================
// MARK: - Response
// ============================================================

final class ResponseEngine {

    func response(
        for action:
            SiriAction
    ) -> String {

        switch action.name {

        case "play":

            if let media =
                action.parameters[
                    "media"
                ] {

                return "Playing \(media)."
            }

            return "Playing."

        case "pause":

            return "Paused."

        case "next":

            return "Skipping."

        case "weather":

            return "I'll check the weather."

        case "timer":

            return "Timer set."

        default:

            return "Done."
        }
    }
}


// ============================================================
// MARK: - Latency Engine
// ============================================================

final class SiriLatencyEngine {

    private let audioEngine =
        AVAudioEngine()

    private let preprocessor =
        AudioPreprocessor()

    private let vad =
        VoiceActivityDetector()

    private let chunker =
        SpeechChunker()

    private let analyzer =
        AcousticAnalyzer()

    private let intentEngine =
        FastIntentEngine()

    private let planner =
        SpeculativePlanner()

    private let responseEngine =
        ResponseEngine()

    private let context =
        SiriContext()

    private let logger =
        Logger(
            subsystem:
                "Aureom.Siri",
            category:
                "Latency"
        )

    private var running =
        false


    //----------------------------------------------------------
    // START
    //----------------------------------------------------------

    func start() throws {

        guard !running else {
            return
        }

        let session =
            AVAudioSession.sharedInstance()

        try session.setCategory(
            .record,
            mode:
                .measurement,
            options:
                [
                    .duckOthers
                ]
        )

        try session.setPreferredSampleRate(
            16_000
        )

        try session.setPreferredIOBufferDuration(
            0.01
        )

        try session.setActive(
            true,
            options:
                []
        )

        let input =
            audioEngine.inputNode

        let format =
            input.inputFormat(
                forBus: 0
            )

        input.installTap(
            onBus: 0,
            bufferSize: 1600,
            format: format
        ) {

            [weak self]
            buffer,
            _ in

            self?.receive(
                buffer
            )
        }

        audioEngine.prepare()

        try audioEngine.start()

        running = true

        logger.info(
            "Siri latency engine started"
        )
    }


    //----------------------------------------------------------
    // STOP
    //----------------------------------------------------------

    func stop() {

        guard running else {
            return
        }

        audioEngine
            .inputNode
            .removeTap(
                onBus: 0
            )

        audioEngine.stop()

        running = false

        logger.info(
            "Siri latency engine stopped"
        )
    }


    //----------------------------------------------------------
    // AUDIO INGESTION
    //----------------------------------------------------------

    private func receive(
        _ buffer:
            AVAudioPCMBuffer
    ) {

        let clock =
            PipelineClock()

        clock.mark(
            "microphone"
        )

        var samples =
            preprocessor.mono(
                buffer:
                    buffer
            )

        samples =
            preprocessor.removeDC(
                samples
            )

        clock.mark(
            "preprocessed"
        )

        let speaking =
            vad.process(
                samples:
                    samples
            )

        clock.mark(
            "vad"
        )

        if speaking {

            chunker.append(
                samples
            )

            /*
             IMPORTANT:

             In a production implementation,
             this is where the partial ASR
             decoder would receive audio.

             The key latency optimisation is:

                 DO NOT WAIT FOR SENTENCE END.

             Decode partial hypotheses continuously.
             */

            analysePartial(
                samples:
                    samples,
                clock:
                    clock
            )

        } else {

            if let chunk =
                chunker.flush() {

                finalise(
                    chunk:
                        chunk,
                    clock:
                        clock
                )
            }
        }
    }


    //----------------------------------------------------------
    // PARTIAL PIPELINE
    //----------------------------------------------------------

    private func analysePartial(
        samples:
            [Float],
        clock:
            PipelineClock
    ) {

        let snapshot =
            analyzer.analyse(
                samples,
                sampleRate:
                    16_000
            )

        clock.mark(
            "features"
        )

        logger.debug(
            """
            Partial audio:
            rms=\(snapshot.rms)
            duration=\(snapshot.duration)
            """
        )
    }


    //----------------------------------------------------------
    // FINAL PIPELINE
    //----------------------------------------------------------

    private func finalise(
        chunk:
            SpeechChunk,
        clock:
            PipelineClock
    ) {

        let snapshot =
            analyzer.analyse(
                chunk.samples,
                sampleRate:
                    16_000
            )

        clock.mark(
            "features"
        )


        //------------------------------------------------------
        // PLACEHOLDER:
        //
        // Replace this with the actual streaming ASR output.
        //------------------------------------------------------

        let recognisedText =
            recognise(
                chunk.samples
            )

        clock.mark(
            "recognition"
        )

        guard
            !recognisedText
                .trimmingCharacters(
                    in:
                        .whitespacesAndNewlines
                )
                .isEmpty
        else {
            return
        }


        //------------------------------------------------------
        // Intent
        //------------------------------------------------------

        let prediction =
            intentEngine.predict(
                text:
                    recognisedText
            )

        clock.mark(
            "intent"
        )


        //------------------------------------------------------
        // Context update
        //------------------------------------------------------

        Task {

            await context.update(
                text:
                    recognisedText,
                prediction:
                    prediction
            )
        }


        //------------------------------------------------------
        // SPECULATIVE ACTION
        //------------------------------------------------------

        if let action =
            planner.plan(
                prediction
            ) {

            clock.mark(
                "planning"
            )

            execute(
                action:
                    action,
                clock:
                    clock
            )
        }


        //------------------------------------------------------
        // LATENCY REPORT
        //------------------------------------------------------

        logger.info(
            """
            Siri pipeline:
            recognition=\(clock.milliseconds(
                from:
                    "microphone",
                to:
                    "recognition"
            ))ms
            intent=\(clock.milliseconds(
                from:
                    "recognition",
                to:
                    "intent"
            ))ms
            total=\(clock.milliseconds(
                from:
                    "microphone",
                to:
                    "intent"
            ))ms
            """
        )
    }


    //----------------------------------------------------------
    // SPEECH RECOGNITION ADAPTER
    //----------------------------------------------------------

    private func recognise(
        _ samples:
            [Float]
    ) -> String {

        /*
         Attach Apple's Speech framework / a local
         speech model here.

         This function intentionally represents
         the ASR boundary.

         The latency engine itself remains
         completely Swift-native.
         */

        return ""
    }


    //----------------------------------------------------------
    // ACTION
    //----------------------------------------------------------

    private func execute(
        action:
            SiriAction,
        clock:
            PipelineClock
    ) {

        switch action.name {

        case "play":

            playMedia(
                action.parameters[
                    "media"
                ]
            )

        case "pause":

            pauseMedia()

        case "next":

            nextMedia()

        case "weather":

            getWeather()

        case "timer":

            setTimer()

        default:

            break
        }

        clock.mark(
            "action"
        )

        let text =
            responseEngine.response(
                for:
                    action
            )

        speak(
            text
        )

        clock.mark(
            "response"
        )

        logger.info(
            "Response: \(text)"
        )
    }


    //----------------------------------------------------------
    // ACTION IMPLEMENTATIONS
    //----------------------------------------------------------

    private func playMedia(
        _ media:
            String?
    ) {

        logger.info(
            "PLAY \(media ?? "unknown")"
        )
    }


    private func pauseMedia() {

        logger.info(
            "PAUSE"
        )
    }


    private func nextMedia() {

        logger.info(
            "NEXT"
        )
    }


    private func getWeather() {

        logger.info(
            "WEATHER"
        )
    }


    private func setTimer() {

        logger.info(
            "TIMER"
        )
    }


    //----------------------------------------------------------
    // TTS
    //----------------------------------------------------------

    private func speak(
        _ text:
            String
    ) {

        /*
         Attach AVSpeechSynthesizer here.

         In production, keep the synthesizer
         permanently allocated rather than
         constructing it for every response.
         */

        logger.info(
            "SPEAK: \(text)"
        )
    }
}
