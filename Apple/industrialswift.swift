//
// SwiftAIEngine.swift
//
// Swift 6
// On-device AI runtime architecture
//
// Public-framework oriented.
// Designed for iOS / macOS / visionOS / watchOS where supported.
//
// Backends can be implemented using:
// - Core ML
// - MLX Swift
// - another local inference runtime
//

import Foundation
import CryptoKit
import os

#if canImport(CoreML)
import CoreML
#endif

// MARK: - Logging

public enum AIEngineLog {
    private static let logger = Logger(
        subsystem: "SwiftAIEngine",
        category: "Runtime"
    )

    public static func info(_ message: String) {
        logger.info("\(message, privacy: .public)")
    }

    public static func debug(_ message: String) {
        logger.debug("\(message, privacy: .public)")
    }

    public static func warning(_ message: String) {
        logger.warning("\(message, privacy: .public)")
    }

    public static func error(_ message: String) {
        logger.error("\(message, privacy: .public)")
    }
}

// MARK: - Errors

public enum AIEngineError: Error, LocalizedError, Sendable {
    case engineNotStarted
    case engineAlreadyStarted
    case modelNotFound(String)
    case modelUnavailable(String)
    case modelLoadFailed(String)
    case tokenizerUnavailable
    case invalidPrompt
    case contextLimitExceeded
    case generationCancelled
    case generationLimitReached
    case backendUnavailable
    case backendFailure(String)
    case toolNotFound(String)
    case toolExecutionFailed(String)
    case unsafeInput
    case unsafeOutput
    case invalidConfiguration
    case memoryLimitExceeded
    case cacheFailure(String)

    public var errorDescription: String? {
        switch self {
        case .engineNotStarted:
            return "The AI engine has not been started."

        case .engineAlreadyStarted:
            return "The AI engine is already running."

        case .modelNotFound(let id):
            return "Model not found: \(id)"

        case .modelUnavailable(let id):
            return "Model unavailable: \(id)"

        case .modelLoadFailed(let reason):
            return "Model loading failed: \(reason)"

        case .tokenizerUnavailable:
            return "No tokenizer is available."

        case .invalidPrompt:
            return "The supplied prompt is invalid."

        case .contextLimitExceeded:
            return "The requested context exceeds the model limit."

        case .generationCancelled:
            return "Generation was cancelled."

        case .generationLimitReached:
            return "The generation limit was reached."

        case .backendUnavailable:
            return "The inference backend is unavailable."

        case .backendFailure(let reason):
            return "Inference backend failure: \(reason)"

        case .toolNotFound(let name):
            return "Tool not found: \(name)"

        case .toolExecutionFailed(let reason):
            return "Tool execution failed: \(reason)"

        case .unsafeInput:
            return "Input rejected by the configured safety policy."

        case .unsafeOutput:
            return "Output rejected by the configured safety policy."

        case .invalidConfiguration:
            return "The AI engine configuration is invalid."

        case .memoryLimitExceeded:
            return "The AI runtime memory limit was exceeded."

        case .cacheFailure(let reason):
            return "Cache failure: \(reason)"
        }
    }
}

// MARK: - Identifiers

public struct AIModelID: Hashable, Codable, Sendable {
    public let rawValue: String

    public init(_ rawValue: String) {
        self.rawValue = rawValue
    }
}

public struct AISessionID: Hashable, Codable, Sendable {
    public let rawValue: UUID

    public init(rawValue: UUID = UUID()) {
        self.rawValue = rawValue
    }
}

public struct AIToolID: Hashable, Codable, Sendable {
    public let rawValue: String

    public init(_ rawValue: String) {
        self.rawValue = rawValue
    }
}

// MARK: - Model Description

public enum AIModelType: String, Codable, Sendable {
    case language
    case embedding
    case vision
    case speech
    case multimodal
}

public enum AIModelQuantization: String, Codable, Sendable {
    case float32
    case float16
    case int8
    case int4
    case mixed
    case unknown
}

public struct AIModelMetadata: Codable, Sendable, Equatable {

    public let id: AIModelID
    public let name: String
    public let version: String
    public let type: AIModelType

    public let contextLength: Int
    public let embeddingDimension: Int?

    public let parameterCount: Int64?
    public let quantization: AIModelQuantization

    public let estimatedMemoryBytes: Int64
    public let supportsStreaming: Bool
    public let supportsTools: Bool

    public init(
        id: AIModelID,
        name: String,
        version: String,
        type: AIModelType,
        contextLength: Int,
        embeddingDimension: Int? = nil,
        parameterCount: Int64? = nil,
        quantization: AIModelQuantization = .unknown,
        estimatedMemoryBytes: Int64,
        supportsStreaming: Bool,
        supportsTools: Bool
    ) {
        self.id = id
        self.name = name
        self.version = version
        self.type = type
        self.contextLength = contextLength
        self.embeddingDimension = embeddingDimension
        self.parameterCount = parameterCount
        self.quantization = quantization
        self.estimatedMemoryBytes = estimatedMemoryBytes
        self.supportsStreaming = supportsStreaming
        self.supportsTools = supportsTools
    }
}

// MARK: - Model State

public enum AIModelState: String, Codable, Sendable {
    case registered
    case downloading
    case available
    case loading
    case loaded
    case unloading
    case failed
}

// MARK: - Model Descriptor

public struct AIModelDescriptor: Codable, Sendable {

    public let metadata: AIModelMetadata
    public let localURL: URL?

    public var id: AIModelID {
        metadata.id
    }

    public init(
        metadata: AIModelMetadata,
        localURL: URL? = nil
    ) {
        self.metadata = metadata
        self.localURL = localURL
    }
}

// MARK: - Model Backend

public protocol AIModelBackend: Sendable {

    var identifier: String { get }

    func load(
        model: AIModelDescriptor
    ) async throws

    func unload(
        model: AIModelDescriptor
    ) async

    func generate(
        request: AIInferenceRequest
    ) async throws -> AIInferenceResult

    func stream(
        request: AIInferenceRequest
    ) -> AsyncThrowingStream<AIGenerationEvent, Error>

    func embed(
        request: AIEmbeddingRequest
    ) async throws -> AIEmbeddingResult

    func memoryFootprint(
        model: AIModelDescriptor
    ) async -> Int64
}

// MARK: - Generation Configuration

public struct AIGenerationConfiguration: Codable, Sendable {

    public var maximumTokens: Int
    public var temperature: Double
    public var topP: Double
    public var topK: Int
    public var repetitionPenalty: Double

    public var stopSequences: [String]

    public init(
        maximumTokens: Int = 512,
        temperature: Double = 0.7,
        topP: Double = 0.95,
        topK: Int = 40,
        repetitionPenalty: Double = 1.0,
        stopSequences: [String] = []
    ) {
        self.maximumTokens = maximumTokens
        self.temperature = temperature
        self.topP = topP
        self.topK = topK
        self.repetitionPenalty = repetitionPenalty
        self.stopSequences = stopSequences
    }

    public static let deterministic = AIGenerationConfiguration(
        maximumTokens: 512,
        temperature: 0,
        topP: 1,
        topK: 1,
        repetitionPenalty: 1
    )
}

// MARK: - Prompt

public enum AIMessageRole: String, Codable, Sendable {
    case system
    case user
    case assistant
    case tool
}

public struct AIMessage: Codable, Sendable, Equatable {

    public let role: AIMessageRole
    public let content: String

    public init(
        role: AIMessageRole,
        content: String
    ) {
        self.role = role
        self.content = content
    }
}

// MARK: - Inference Request

public struct AIInferenceRequest: Sendable {

    public let modelID: AIModelID
    public let messages: [AIMessage]
    public let configuration: AIGenerationConfiguration
    public let sessionID: AISessionID?
    public let metadata: [String: String]

    public init(
        modelID: AIModelID,
        messages: [AIMessage],
        configuration: AIGenerationConfiguration = .init(),
        sessionID: AISessionID? = nil,
        metadata: [String: String] = [:]
    ) {
        self.modelID = modelID
        self.messages = messages
        self.configuration = configuration
        self.sessionID = sessionID
        self.metadata = metadata
    }
}

// MARK: - Result

public struct AIInferenceResult: Sendable {

    public let text: String
    public let inputTokenCount: Int
    public let outputTokenCount: Int
    public let duration: Duration

    public init(
        text: String,
        inputTokenCount: Int,
        outputTokenCount: Int,
        duration: Duration
    ) {
        self.text = text
        self.inputTokenCount = inputTokenCount
        self.outputTokenCount = outputTokenCount
        self.duration = duration
    }

    public var tokensPerSecond: Double {
        let seconds = Double(duration.components.seconds)
            + Double(duration.components.attoseconds) / 1e18

        guard seconds > 0 else {
            return 0
        }

        return Double(outputTokenCount) / seconds
    }
}

// MARK: - Generation Events

public enum AIGenerationEvent: Sendable {

    case started(AIGenerationMetadata)
    case token(String)
    case text(String)
    case toolCall(AIToolCall)
    case finished(AIGenerationStatistics)
}

public struct AIGenerationMetadata: Sendable {

    public let sessionID: AISessionID
    public let modelID: AIModelID
    public let startTime: ContinuousClock.Instant

    public init(
        sessionID: AISessionID,
        modelID: AIModelID,
        startTime: ContinuousClock.Instant
    ) {
        self.sessionID = sessionID
        self.modelID = modelID
        self.startTime = startTime
    }
}

public struct AIGenerationStatistics: Sendable {

    public let inputTokens: Int
    public let outputTokens: Int
    public let duration: Duration
    public let tokensPerSecond: Double

    public init(
        inputTokens: Int,
        outputTokens: Int,
        duration: Duration
    ) {
        self.inputTokens = inputTokens
        self.outputTokens = outputTokens
        self.duration = duration

        let seconds =
            Double(duration.components.seconds) +
            Double(duration.components.attoseconds) / 1e18

        self.tokensPerSecond =
            seconds > 0
            ? Double(outputTokens) / seconds
            : 0
    }
}

// MARK: - Tokenizer

public protocol AITokenizer: Sendable {

    func encode(_ text: String) throws -> [Int]
    func decode(_ tokens: [Int]) throws -> String

    func countTokens(
        messages: [AIMessage]
    ) throws -> Int
}

public struct ApproximateTokenizer: AITokenizer {

    public init() {}

    public func encode(_ text: String) throws -> [Int] {
        guard !text.isEmpty else {
            return []
        }

        return text
            .split(whereSeparator: \.isWhitespace)
            .map { $0.hashValue }
    }

    public func decode(_ tokens: [Int]) throws -> String {
        tokens.map(String.init).joined(separator: " ")
    }

    public func countTokens(
        messages: [AIMessage]
    ) throws -> Int {
        messages.reduce(0) { result, message in
            result + max(1, message.content.count / 4)
        }
    }
}

// MARK: - Embeddings

public struct AIEmbeddingRequest: Sendable {

    public let modelID: AIModelID
    public let text: String

    public init(
        modelID: AIModelID,
        text: String
    ) {
        self.modelID = modelID
        self.text = text
    }
}

public struct AIEmbeddingResult: Sendable {

    public let vector: [Float]
    public let modelID: AIModelID

    public init(
        vector: [Float],
        modelID: AIModelID
    ) {
        self.vector = vector
        self.modelID = modelID
    }

    public func cosineSimilarity(
        with other: AIEmbeddingResult
    ) -> Float {

        guard vector.count == other.vector.count else {
            return 0
        }

        var dot: Float = 0
        var magnitudeA: Float = 0
        var magnitudeB: Float = 0

        for index in vector.indices {
            let a = vector[index]
            let b = other.vector[index]

            dot += a * b
            magnitudeA += a * a
            magnitudeB += b * b
        }

        guard magnitudeA > 0, magnitudeB > 0 else {
            return 0
        }

        return dot /
            (sqrt(magnitudeA) * sqrt(magnitudeB))
    }
}

// MARK: - Model Registry

public actor AIModelRegistry {

    private struct Entry: Sendable {
        let descriptor: AIModelDescriptor
        var state: AIModelState
    }

    private var models: [AIModelID: Entry] = [:]

    public init() {}

    public func register(
        _ descriptor: AIModelDescriptor
    ) throws {

        guard descriptor.metadata.contextLength > 0 else {
            throw AIEngineError.invalidConfiguration
        }

        models[descriptor.id] = Entry(
            descriptor: descriptor,
            state: .registered
        )
    }

    public func unregister(
        _ id: AIModelID
    ) {
        models.removeValue(forKey: id)
    }

    public func descriptor(
        for id: AIModelID
    ) throws -> AIModelDescriptor {

        guard let entry = models[id] else {
            throw AIEngineError.modelNotFound(id.rawValue)
        }

        return entry.descriptor
    }

    public func state(
        for id: AIModelID
    ) throws -> AIModelState {

        guard let entry = models[id] else {
            throw AIEngineError.modelNotFound(id.rawValue)
        }

        return entry.state
    }

    public func setState(
        _ state: AIModelState,
        for id: AIModelID
    ) throws {

        guard var entry = models[id] else {
            throw AIEngineError.modelNotFound(id.rawValue)
        }

        entry.state = state
        models[id] = entry
    }

    public func allModels() -> [AIModelDescriptor] {
        models.values.map(\.descriptor)
    }
}

// MARK: - Context Window

public struct AIContextWindow: Sendable {

    public let maximumTokens: Int
    public private(set) var messages: [AIMessage]

    public init(
        maximumTokens: Int,
        messages: [AIMessage] = []
    ) {
        self.maximumTokens = maximumTokens
        self.messages = messages
    }

    public mutating func append(
        _ message: AIMessage,
        tokenizer: any AITokenizer
    ) throws {

        let candidate = messages + [message]
        let count = try tokenizer.countTokens(messages: candidate)

        guard count <= maximumTokens else {
            throw AIEngineError.contextLimitExceeded
        }

        messages.append(message)
    }

    public mutating func removeOldestUserContent() {
        guard !messages.isEmpty else {
            return
        }

        if let index = messages.firstIndex(
            where: { $0.role == .user }
        ) {
            messages.remove(at: index)
        } else {
            messages.removeFirst()
        }
    }

    public mutating func compact(
        tokenizer: any AITokenizer
    ) throws {

        while try tokenizer.countTokens(messages: messages)
            > maximumTokens {

            guard messages.count > 1 else {
                throw AIEngineError.contextLimitExceeded
            }

            removeOldestUserContent()
        }
    }
}

// MARK: - Session

public struct AISessionConfiguration: Codable, Sendable {

    public let modelID: AIModelID
    public let systemPrompt: String?

    public init(
        modelID: AIModelID,
        systemPrompt: String? = nil
    ) {
        self.modelID = modelID
        self.systemPrompt = systemPrompt
    }
}

public actor AISession {

    public let id: AISessionID

    private let configuration: AISessionConfiguration
    private let tokenizer: any AITokenizer

    private var context: AIContextWindow

    init(
        id: AISessionID,
        configuration: AISessionConfiguration,
        contextLength: Int,
        tokenizer: any AITokenizer
    ) {
        self.id = id
        self.configuration = configuration
        self.tokenizer = tokenizer

        self.context = AIContextWindow(
            maximumTokens: contextLength
        )

        if let systemPrompt = configuration.systemPrompt {
            self.context.messages.append(
                AIMessage(
                    role: .system,
                    content: systemPrompt
                )
            )
        }
    }

    public func messages() -> [AIMessage] {
        context.messages
    }

    public func append(
        role: AIMessageRole,
        content: String
    ) throws {

        guard !content.isEmpty else {
            throw AIEngineError.invalidPrompt
        }

        try context.append(
            AIMessage(
                role: role,
                content: content
            ),
            tokenizer: tokenizer
        )
    }

    public func compactContext() throws {
        try context.compact(
            tokenizer: tokenizer
        )
    }

    public func configurationValue() -> AISessionConfiguration {
        configuration
    }
}

// MARK: - Safety

public enum AISafetyDecision: Sendable {
    case allow
    case reject(AIEngineError)
}

public protocol AISafetyPolicy: Sendable {

    func inspectInput(
        messages: [AIMessage]
    ) async -> AISafetyDecision

    func inspectOutput(
        text: String
    ) async -> AISafetyDecision
}

public struct BasicSafetyPolicy: AISafetyPolicy {

    public init() {}

    public func inspectInput(
        messages: [AIMessage]
    ) async -> AISafetyDecision {

        let totalCharacters = messages.reduce(0) {
            $0 + $1.content.count
        }

        if totalCharacters > 1_000_000 {
            return .reject(.unsafeInput)
        }

        return .allow
    }

    public func inspectOutput(
        text: String
    ) async -> AISafetyDecision {

        if text.count > 10_000_000 {
            return .reject(.unsafeOutput)
        }

        return .allow
    }
}

// MARK: - Tools

public struct AIToolDefinition: Codable, Sendable {

    public let id: AIToolID
    public let name: String
    public let description: String
    public let inputSchema: String

    public init(
        id: AIToolID,
        name: String,
        description: String,
        inputSchema: String
    ) {
        self.id = id
        self.name = name
        self.description = description
        self.inputSchema = inputSchema
    }
}

public struct AIToolCall: Sendable {

    public let id: UUID
    public let toolID: AIToolID
    public let argumentsJSON: String

    public init(
        id: UUID = UUID(),
        toolID: AIToolID,
        argumentsJSON: String
    ) {
        self.id = id
        self.toolID = toolID
        self.argumentsJSON = argumentsJSON
    }
}

public struct AIToolResult: Sendable {

    public let callID: UUID
    public let content: String
    public let success: Bool

    public init(
        callID: UUID,
        content: String,
        success: Bool
    ) {
        self.callID = callID
        self.content = content
        self.success = success
    }
}

public protocol AITool: Sendable {

    var definition: AIToolDefinition { get }

    func execute(
        argumentsJSON: String
    ) async throws -> String
}

public actor AIToolRegistry {

    private var tools: [AIToolID: any AITool] = [:]

    public init() {}

    public func register(
        _ tool: any AITool
    ) {
        tools[tool.definition.id] = tool
    }

    public func unregister(
        _ id: AIToolID
    ) {
        tools.removeValue(forKey: id)
    }

    public func definitions() -> [AIToolDefinition] {
        tools.values.map(\.definition)
    }

    public func execute(
        _ call: AIToolCall
    ) async throws -> AIToolResult {

        guard let tool = tools[call.toolID] else {
            throw AIEngineError.toolNotFound(
                call.toolID.rawValue
            )
        }

        do {
            let content = try await tool.execute(
                argumentsJSON: call.argumentsJSON
            )

            return AIToolResult(
                callID: call.id,
                content: content,
                success: true
            )

        } catch {
            throw AIEngineError.toolExecutionFailed(
                String(describing: error)
            )
        }
    }
}

// MARK: - Memory

public struct AIMemoryRecord: Codable, Sendable, Identifiable {

    public let id: UUID
    public let text: String
    public let timestamp: Date
    public let embedding: [Float]?

    public init(
        id: UUID = UUID(),
        text: String,
        timestamp: Date = Date(),
        embedding: [Float]? = nil
    ) {
        self.id = id
        self.text = text
        self.timestamp = timestamp
        self.embedding = embedding
    }
}

public actor AIMemoryStore {

    private var records: [UUID: AIMemoryRecord] = [:]

    public init() {}

    public func insert(
        _ record: AIMemoryRecord
    ) {
        records[record.id] = record
    }

    public func delete(
        id: UUID
    ) {
        records.removeValue(forKey: id)
    }

    public func all() -> [AIMemoryRecord] {
        records.values.sorted {
            $0.timestamp < $1.timestamp
        }
    }

    public func search(
        queryVector: [Float],
        limit: Int = 10
    ) -> [AIMemoryRecord] {

        func similarity(
            _ a: [Float],
            _ b: [Float]
        ) -> Float {

            guard a.count == b.count else {
                return 0
            }

            var dot: Float = 0
            var aMag: Float = 0
            var bMag: Float = 0

            for index in a.indices {
                dot += a[index] * b[index]
                aMag += a[index] * a[index]
                bMag += b[index] * b[index]
            }

            guard aMag > 0, bMag > 0 else {
                return 0
            }

            return dot / sqrt(aMag * bMag)
        }

        return records.values
            .compactMap { record -> (AIMemoryRecord, Float)? in

                guard let embedding = record.embedding else {
                    return nil
                }

                return (
                    record,
                    similarity(queryVector, embedding)
                )
            }
            .sorted {
                $0.1 > $1.1
            }
            .prefix(limit)
            .map(\.0)
    }
}

// MARK: - Cache

public struct AICacheKey: Hashable, Sendable {

    public let digest: String

    public init(
        request: AIInferenceRequest
    ) {

        var source = request.modelID.rawValue

        for message in request.messages {
            source += "|\(message.role.rawValue)|\(message.content)"
        }

        source += "|\(request.configuration.maximumTokens)"
        source += "|\(request.configuration.temperature)"
        source += "|\(request.configuration.topP)"

        let data = Data(source.utf8)
        let hash = SHA256.hash(data: data)

        self.digest = hash
            .map { String(format: "%02x", $0) }
            .joined()
    }
}

public actor AIResponseCache {

    private var values: [AICacheKey: AIInferenceResult] = [:]

    public init() {}

    public func get(
        _ key: AICacheKey
    ) -> AIInferenceResult? {
        values[key]
    }

    public func set(
        _ value: AIInferenceResult,
        for key: AICacheKey
    ) {
        values[key] = value
    }

    public func removeAll() {
        values.removeAll()
    }

    public func count() -> Int {
        values.count
    }
}

// MARK: - Runtime Metrics

public struct AIRuntimeMetrics: Sendable {

    public let requestCount: UInt64
    public let successfulRequests: UInt64
    public let failedRequests: UInt64
    public let generatedTokens: UInt64
    public let totalInputTokens: UInt64
    public let totalDuration: Duration

    public init(
        requestCount: UInt64 = 0,
        successfulRequests: UInt64 = 0,
        failedRequests: UInt64 = 0,
        generatedTokens: UInt64 = 0,
        totalInputTokens: UInt64 = 0,
        totalDuration: Duration = .zero
    ) {
        self.requestCount = requestCount
        self.successfulRequests = successfulRequests
        self.failedRequests = failedRequests
        self.generatedTokens = generatedTokens
        self.totalInputTokens = totalInputTokens
        self.totalDuration = totalDuration
    }

    public var averageGenerationTokens: Double {
        guard successfulRequests > 0 else {
            return 0
        }

        return Double(generatedTokens) /
            Double(successfulRequests)
    }
}

public actor AIRuntimeMetricsStore {

    private var requestCount: UInt64 = 0
    private var successfulRequests: UInt64 = 0
    private var failedRequests: UInt64 = 0
    private var generatedTokens: UInt64 = 0
    private var totalInputTokens: UInt64 = 0
    private var totalDuration: Duration = .zero

    public init() {}

    public func recordSuccess(
        inputTokens: Int,
        outputTokens: Int,
        duration: Duration
    ) {

        requestCount += 1
        successfulRequests += 1

        generatedTokens += UInt64(
            max(0, outputTokens)
        )

        totalInputTokens += UInt64(
            max(0, inputTokens)
        )

        totalDuration += duration
    }

    public func recordFailure() {
        requestCount += 1
        failedRequests += 1
    }

    public func snapshot() -> AIRuntimeMetrics {

        AIRuntimeMetrics(
            requestCount: requestCount,
            successfulRequests: successfulRequests,
            failedRequests: failedRequests,
            generatedTokens: generatedTokens,
            totalInputTokens: totalInputTokens,
            totalDuration: totalDuration
        )
    }
}

// MARK: - Backend Registry

public actor AIBackendRegistry {

    private var backends: [String: any AIModelBackend] = [:]

    public init() {}

    public func register(
        _ backend: any AIModelBackend
    ) {
        backends[backend.identifier] = backend
    }

    public func backend(
        identifier: String
    ) -> (any AIModelBackend)? {
        backends[identifier]
    }

    public func identifiers() -> [String] {
        Array(backends.keys).sorted()
    }
}

// MARK: - Session Registry

public actor AISessionRegistry {

    private var sessions: [AISessionID: AISession] = [:]

    public init() {}

    public func insert(
        _ session: AISession
    ) {
        sessions[session.id] = session
    }

    public func session(
        id: AISessionID
    ) -> AISession? {
        sessions[id]
    }

    public func remove(
        id: AISessionID
    ) {
        sessions.removeValue(forKey: id)
    }

    public func count() -> Int {
        sessions.count
    }
}

// MARK: - Runtime Configuration

public struct AIEngineConfiguration: Sendable {

    public var defaultBackendIdentifier: String

    public var maximumConcurrentRequests: Int
    public var maximumMemoryBytes: Int64

    public var enableResponseCache: Bool
    public var enableMemory: Bool
    public var enableSafetyChecks: Bool

    public init(
        defaultBackendIdentifier: String = "mock",
        maximumConcurrentRequests: Int = 1,
        maximumMemoryBytes: Int64 = 2_000_000_000,
        enableResponseCache: Bool = true,
        enableMemory: Bool = true,
        enableSafetyChecks: Bool = true
    ) {
        self.defaultBackendIdentifier = defaultBackendIdentifier
        self.maximumConcurrentRequests =
            max(1, maximumConcurrentRequests)

        self.maximumMemoryBytes =
            max(1, maximumMemoryBytes)

        self.enableResponseCache = enableResponseCache
        self.enableMemory = enableMemory
        self.enableSafetyChecks = enableSafetyChecks
    }
}

// MARK: - Engine State

public enum AIEngineState: String, Sendable {
    case stopped
    case starting
    case running
    case stopping
    case failed
}

// MARK: - Main Engine

public actor SwiftAIEngine {

    public let configuration: AIEngineConfiguration

    private let modelRegistry: AIModelRegistry
    private let backendRegistry: AIBackendRegistry
    private let sessionRegistry: AISessionRegistry
    private let toolRegistry: AIToolRegistry
    private let memoryStore: AIMemoryStore
    private let responseCache: AIResponseCache
    private let metrics: AIRuntimeMetricsStore

    private let tokenizer: any AITokenizer
    private let safetyPolicy: any AISafetyPolicy

    private var state: AIEngineState = .stopped

    private var loadedModels: Set<AIModelID> = []

    private var activeRequests: Int = 0

    public init(
        configuration: AIEngineConfiguration = .init(),
        tokenizer: any AITokenizer = ApproximateTokenizer(),
        safetyPolicy: any AISafetyPolicy = BasicSafetyPolicy()
    ) {

        self.configuration = configuration

        self.modelRegistry = AIModelRegistry()
        self.backendRegistry = AIBackendRegistry()
        self.sessionRegistry = AISessionRegistry()
        self.toolRegistry = AIToolRegistry()
        self.memoryStore = AIMemoryStore()
        self.responseCache = AIResponseCache()
        self.metrics = AIRuntimeMetricsStore()

        self.tokenizer = tokenizer
        self.safetyPolicy = safetyPolicy
    }

    // MARK: Lifecycle

    public func start() async throws {

        guard state == .stopped else {
            throw AIEngineError.engineAlreadyStarted
        }

        state = .starting

        AIEngineLog.info("Starting SwiftAIEngine")

        state = .running

        AIEngineLog.info("SwiftAIEngine started")
    }

    public func stop() async {

        guard state == .running else {
            state = .stopped
            return
        }

        state = .stopping

        let models = loadedModels

        for modelID in models {

            do {
                let descriptor =
                    try await modelRegistry.descriptor(
                        for: modelID
                    )

                let backend =
                    try await selectedBackend()

                await backend.unload(
                    model: descriptor
                )

                try? await modelRegistry.setState(
                    .available,
                    for: modelID
                )

            } catch {
                AIEngineLog.warning(
                    "Failed unloading \(modelID.rawValue)"
                )
            }
        }

        loadedModels.removeAll()

        state = .stopped
    }

    public func currentState() -> AIEngineState {
        state
    }

    // MARK: Backend

    public func registerBackend(
        _ backend: any AIModelBackend
    ) async {
        await backendRegistry.register(backend)
    }

    private func selectedBackend() async throws -> any AIModelBackend {

        guard let backend =
                await backendRegistry.backend(
                    identifier:
                        configuration.defaultBackendIdentifier
                )
        else {
            throw AIEngineError.backendUnavailable
        }

        return backend
    }

    // MARK: Models

    public func registerModel(
        _ descriptor: AIModelDescriptor
    ) async throws {

        try await modelRegistry.register(
            descriptor
        )

        AIEngineLog.info(
            "Registered model \(descriptor.id.rawValue)"
        )
    }

    public func loadModel(
        _ modelID: AIModelID
    ) async throws {

        guard state == .running else {
            throw AIEngineError.engineNotStarted
        }

        let descriptor =
            try await modelRegistry.descriptor(
                for: modelID
            )

        if loadedModels.contains(modelID) {
            return
        }

        try await modelRegistry.setState(
            .loading,
            for: modelID
        )

        let backend = try await selectedBackend()

        let footprint =
            await backend.memoryFootprint(
                model: descriptor
            )

        guard footprint <= configuration.maximumMemoryBytes
        else {
            try await modelRegistry.setState(
                .failed,
                for: modelID
            )

            throw AIEngineError.memoryLimitExceeded
        }

        do {

            try await backend.load(
                model: descriptor
            )

            loadedModels.insert(modelID)

            try await modelRegistry.setState(
                .loaded,
                for: modelID
            )

        } catch {

            try? await modelRegistry.setState(
                .failed,
                for: modelID
            )

            throw AIEngineError.modelLoadFailed(
                String(describing: error)
            )
        }
    }

    public func unloadModel(
        _ modelID: AIModelID
    ) async throws {

        guard loadedModels.contains(modelID)
        else {
            return
        }

        let descriptor =
            try await modelRegistry.descriptor(
                for: modelID
            )

        let backend = try await selectedBackend()

        try? await modelRegistry.setState(
            .unloading,
            for: modelID
        )

        await backend.unload(
            model: descriptor
        )

        loadedModels.remove(modelID)

        try? await modelRegistry.setState(
            .available,
            for: modelID
        )
    }

    // MARK: Sessions

    public func createSession(
        configuration:
            AISessionConfiguration
    ) async throws -> AISessionID {

        let descriptor =
            try await modelRegistry.descriptor(
                for: configuration.modelID
            )

        let sessionID = AISessionID()

        let session = AISession(
            id: sessionID,
            configuration: configuration,
            contextLength:
                descriptor.metadata.contextLength,
            tokenizer: tokenizer
        )

        await sessionRegistry.insert(
            session
        )

        return sessionID
    }

    public func destroySession(
        _ id: AISessionID
    ) async {
        await sessionRegistry.remove(
            id: id
        )
    }

    // MARK: Generation

    public func generate(
        _ request: AIInferenceRequest
    ) async throws -> AIInferenceResult {

        guard state == .running else {
            throw AIEngineError.engineNotStarted
        }

        guard !request.messages.isEmpty else {
            throw AIEngineError.invalidPrompt
        }

        guard activeRequests <
                configuration.maximumConcurrentRequests
        else {
            throw AIEngineError.backendFailure(
                "Maximum concurrent request count reached."
            )
        }

        if configuration.enableSafetyChecks {

            switch await safetyPolicy.inspectInput(
                messages: request.messages
            ) {

            case .allow:
                break

            case .reject(let error):
                throw error
            }
        }

        if configuration.enableResponseCache {

            let key = AICacheKey(
                request: request
            )

            if let cached =
                await responseCache.get(key)
            {
                return cached
            }
        }

        guard loadedModels.contains(
            request.modelID
        ) else {
            throw AIEngineError.modelUnavailable(
                request.modelID.rawValue
            )
        }

        activeRequests += 1

        defer {
            activeRequests -= 1
        }

        let backend = try await selectedBackend()

        let start = ContinuousClock.now

        do {

            let result =
                try await backend.generate(
                    request: request
                )

            if configuration.enableSafetyChecks {

                switch await safetyPolicy.inspectOutput(
                    text: result.text
                ) {

                case .allow:
                    break

                case .reject(let error):
                    await metrics.recordFailure()
                    throw error
                }
            }

            let duration =
                start.duration(to: ContinuousClock.now)

            let finalResult = AIInferenceResult(
                text: result.text,
                inputTokenCount:
                    result.inputTokenCount,
                outputTokenCount:
                    result.outputTokenCount,
                duration: duration
            )

            await metrics.recordSuccess(
                inputTokens:
                    result.inputTokenCount,
                outputTokens:
                    result.outputTokenCount,
                duration: duration
            )

            if configuration.enableResponseCache {

                let key = AICacheKey(
                    request: request
                )

                await responseCache.set(
                    finalResult,
                    for: key
                )
            }

            return finalResult

        } catch {

            await metrics.recordFailure()

            throw error
        }
    }

    // MARK: Streaming

    public func stream(
        _ request: AIInferenceRequest
    ) async throws
        -> AsyncThrowingStream<AIGenerationEvent, Error>
    {

        guard state == .running else {
            throw AIEngineError.engineNotStarted
        }

        guard loadedModels.contains(
            request.modelID
        ) else {
            throw AIEngineError.modelUnavailable(
                request.modelID.rawValue
            )
        }

        let backend = try await selectedBackend()

        return backend.stream(
            request: request
        )
    }

    // MARK: Embeddings

    public func embedding(
        modelID: AIModelID,
        text: String
    ) async throws -> AIEmbeddingResult {

        guard state == .running else {
            throw AIEngineError.engineNotStarted
        }

        guard !text.isEmpty else {
            throw AIEngineError.invalidPrompt
        }

        guard loadedModels.contains(
            modelID
        ) else {
            throw AIEngineError.modelUnavailable(
                modelID.rawValue
            )
        }

        let backend = try await selectedBackend()

        return try await backend.embed(
            request: AIEmbeddingRequest(
                modelID: modelID,
                text: text
            )
        )
    }

    // MARK: Tools

    public func registerTool(
        _ tool: any AITool
    ) async {
        await toolRegistry.register(tool)
    }

    public func executeTool(
        _ call: AIToolCall
    ) async throws -> AIToolResult {

        try await toolRegistry.execute(
            call
        )
    }

    public func availableTools()
        async -> [AIToolDefinition]
    {
        await toolRegistry.definitions()
    }

    // MARK: Memory

    public func remember(
        text: String,
        embedding: [Float]? = nil
    ) async throws {

        guard configuration.enableMemory else {
            return
        }

        guard !text.isEmpty else {
            throw AIEngineError.invalidPrompt
        }

        await memoryStore.insert(
            AIMemoryRecord(
                text: text,
                embedding: embedding
            )
        )
    }

    public func searchMemory(
        queryVector: [Float],
        limit: Int = 10
    ) async -> [AIMemoryRecord] {

        guard configuration.enableMemory else {
            return []
        }

        return await memoryStore.search(
            queryVector: queryVector,
            limit: limit
        )
    }

    // MARK: Diagnostics

    public func metricsSnapshot()
        async -> AIRuntimeMetrics
    {
        await metrics.snapshot()
    }

    public func loadedModelIDs()
        -> [AIModelID]
    {
        Array(loadedModels)
    }

    public func registeredModels()
        async -> [AIModelDescriptor]
    {
        await modelRegistry.allModels()
    }

    public func registeredBackends()
        async -> [String]
    {
        await backendRegistry.identifiers()
    }

    public func sessionCount()
        async -> Int
    {
        await sessionRegistry.count()
    }

    public func cacheEntryCount()
        async -> Int
    {
        await responseCache.count()
    }
}

// MARK: - Mock Backend
//
// This backend exists so the architecture can be compiled and tested
// without requiring an actual ML model.
//
// Replace this with a Core ML / MLX backend in production.
//

public actor MockAIBackend: AIModelBackend {

    public let identifier = "mock"

    private var loaded: Set<AIModelID> = []

    public init() {}

    public func load(
        model: AIModelDescriptor
    ) async throws {
        loaded.insert(model.id)
    }

    public func unload(
        model: AIModelDescriptor
    ) async {
        loaded.remove(model.id)
    }

    public func memoryFootprint(
        model: AIModelDescriptor
    ) async -> Int64 {
        model.metadata.estimatedMemoryBytes
    }

    public func generate(
        request: AIInferenceRequest
    ) async throws -> AIInferenceResult {

        guard loaded.contains(request.modelID) else {
            throw AIEngineError.modelUnavailable(
                request.modelID.rawValue
            )
        }

        let start = ContinuousClock.now

        let lastUserMessage =
            request.messages
                .last(where: { $0.role == .user })?
                .content
                ?? ""

        let output =
            "Mock local inference response: \(lastUserMessage)"

        let duration =
            start.duration(to: ContinuousClock.now)

        return AIInferenceResult(
            text: output,
            inputTokenCount:
                request.messages.reduce(0) {
                    $0 + $1.content.count / 4
                },
            outputTokenCount:
                output.count / 4,
            duration: duration
        )
    }

    public func stream(
        request: AIInferenceRequest
    ) -> AsyncThrowingStream<AIGenerationEvent, Error> {

        AsyncThrowingStream { continuation in

            Task {

                let sessionID =
                    request.sessionID ?? AISessionID()

                continuation.yield(
                    .started(
                        AIGenerationMetadata(
                            sessionID: sessionID,
                            modelID: request.modelID,
                            startTime: ContinuousClock.now
                        )
                    )
                )

                let result =
                    try await generate(
                        request: request
                    )

                for word in result.text.split(
                    separator: " "
                ) {

                    try Task.checkCancellation()

                    continuation.yield(
                        .token(
                            String(word) + " "
                        )
                    )

                    try await Task.sleep(
                        for: .milliseconds(10)
                    )
                }

                continuation.yield(
                    .finished(
                        AIGenerationStatistics(
                            inputTokens:
                                result.inputTokenCount,
                            outputTokens:
                                result.outputTokenCount,
                            duration:
                                result.duration
                        )
                    )
                )

                continuation.finish()
            }
        }
    }

    public func embed(
        request: AIEmbeddingRequest
    ) async throws -> AIEmbeddingResult {

        guard loaded.contains(request.modelID) else {
            throw AIEngineError.modelUnavailable(
                request.modelID.rawValue
            )
        }

        // Deterministic placeholder embedding.
        // Real backend should return the model's embedding.
        let dimension = 128

        var vector = Array(
            repeating: Float.zero,
            count: dimension
        )

        for byte in request.text.utf8 {

            let index =
                Int(byte) % dimension

            vector[index] += 1
        }

        return AIEmbeddingResult(
            vector: vector,
            modelID: request.modelID
        )
    }
}

// MARK: - Example Tool

public struct CurrentDateTool: AITool {

    public let definition = AIToolDefinition(
        id: AIToolID("current-date"),
        name: "current_date",
        description: "Returns the current local date.",
        inputSchema: "{}"
    )

    public init() {}

    public func execute(
        argumentsJSON: String
    ) async throws -> String {

        ISO8601DateFormatter()
            .string(from: Date())
    }
}

// MARK: - Example Factory

public enum SwiftAIEngineFactory {

    public static func makeDevelopmentEngine()
        async throws -> SwiftAIEngine
    {

        let engine = SwiftAIEngine(
            configuration:
                AIEngineConfiguration(
                    defaultBackendIdentifier: "mock",
                    maximumConcurrentRequests: 2,
                    maximumMemoryBytes: 512_000_000
                )
        )

        let backend = MockAIBackend()

        await engine.registerBackend(
            backend
        )

        try await engine.start()

        let model = AIModelDescriptor(
            metadata: AIModelMetadata(
                id: AIModelID("development-model"),
                name: "Development Local Model",
                version: "1.0",
                type: .language,
                contextLength: 8_192,
                quantization: .int4,
                estimatedMemoryBytes: 128_000_000,
                supportsStreaming: true,
                supportsTools: true
            )
        )

        try await engine.registerModel(
            model
        )

        try await engine.loadModel(
            model.id
        )

        await engine.registerTool(
            CurrentDateTool()
        )

        return engine
    }
}

// MARK: - Example

public enum SwiftAIEngineExample {

    public static func run() async throws {

        let engine =
            try await SwiftAIEngineFactory
                .makeDevelopmentEngine()

        let sessionID =
            try await engine.createSession(
                configuration:
                    AISessionConfiguration(
                        modelID:
                            AIModelID(
                                "development-model"
                            ),
                        systemPrompt:
                            "You are a concise local assistant."
                    )
            )

        guard let session =
                await engine.sessionRegistry
                    .session(id: sessionID)
        else {
            return
        }

        try await session.append(
            role: .user,
            content: "Explain local AI."
        )

        let messages =
            await session.messages()

        let request = AIInferenceRequest(
            modelID:
                AIModelID(
                    "development-model"
                ),
            messages: messages,
            configuration:
                AIGenerationConfiguration(
                    maximumTokens: 256,
                    temperature: 0.2
                ),
            sessionID: sessionID
        )

        let result =
            try await engine.generate(
                request
            )

        print(result.text)
        print(
            "Tokens/sec:",
            result.tokensPerSecond
        )
    }
}





#if canImport(CoreML)

import CoreML

public actor CoreMLAIBackend: AIModelBackend {

    public let identifier = "coreml"

    private var models:
        [AIModelID: MLModel] = [:]

    public init() {}

    public func load(
        model: AIModelDescriptor
    ) async throws {

        guard let url = model.localURL else {
            throw AIEngineError.modelLoadFailed(
                "Model has no local URL."
            )
        }

        let configuration = MLModelConfiguration()

        configuration.computeUnits = .all

        do {
            let loaded =
                try MLModel(
                    contentsOf: url,
                    configuration: configuration
                )

            models[model.id] = loaded

        } catch {

            throw AIEngineError.modelLoadFailed(
                error.localizedDescription
            )
        }
    }

    public func unload(
        model: AIModelDescriptor
    ) async {
        models.removeValue(
            forKey: model.id
        )
    }

    public func memoryFootprint(
        model: AIModelDescriptor
    ) async -> Int64 {
        model.metadata.estimatedMemoryBytes
    }

    public func generate(
        request: AIInferenceRequest
    ) async throws -> AIInferenceResult {

        guard models[request.modelID] != nil else {
            throw AIEngineError.modelUnavailable(
                request.modelID.rawValue
            )
        }

        //
        // The exact prediction code depends on the
        // Core ML model's input/output specification.
        //
        // This intentionally does not invent a universal
        // MLModel input contract.
        //

        throw AIEngineError.backendFailure(
            "Model-specific Core ML prediction adapter required."
        )
    }

    public func stream(
        request: AIInferenceRequest
    ) -> AsyncThrowingStream<AIGenerationEvent, Error> {

        AsyncThrowingStream { continuation in

            continuation.finish(
                throwing:
                    AIEngineError.backendFailure(
                        "Streaming requires a model-specific adapter."
                    )
            )
        }
    }

    public func embed(
        request: AIEmbeddingRequest
    ) async throws -> AIEmbeddingResult {

        guard models[request.modelID] != nil else {
            throw AIEngineError.modelUnavailable(
                request.modelID.rawValue
            )
        }

        throw AIEngineError.backendFailure(
            "Embedding output mapping is model-specific."
        )
    }
}

#endif





//
// SwiftCloudEngine.swift
//
// Swift 6
// Production-oriented cloud/server foundation.
//
// Designed to be backend-neutral:
// - HTTP server framework can be plugged in
// - database can be plugged in
// - cache can be plugged in
// - queue can be plugged in
//
// The core runtime itself uses Swift concurrency and actors.
//

import Foundation
import os
import CryptoKit
import Observation

// MARK: - Logging

public enum SwiftCloudLog {

    private static let logger = Logger(
        subsystem: "SwiftCloudEngine",
        category: "CloudRuntime"
    )

    public static func info(_ message: String) {
        logger.info("\(message, privacy: .public)")
    }

    public static func debug(_ message: String) {
        logger.debug("\(message, privacy: .public)")
    }

    public static func warning(_ message: String) {
        logger.warning("\(message, privacy: .public)")
    }

    public static func error(_ message: String) {
        logger.error("\(message, privacy: .public)")
    }
}

// MARK: - Errors

public enum CloudEngineError: Error, LocalizedError, Sendable {

    case engineNotStarted
    case engineAlreadyStarted
    case invalidConfiguration

    case routeNotFound
    case methodNotAllowed
    case unauthorized
    case forbidden
    case tooManyRequests

    case invalidRequest
    case invalidJSON
    case bodyTooLarge

    case databaseUnavailable
    case databaseFailure(String)

    case cacheFailure(String)

    case jobNotFound
    case queueUnavailable
    case workerUnavailable

    case timeout
    case cancelled

    case serviceUnavailable
    case internalError(String)

    public var errorDescription: String? {

        switch self {

        case .engineNotStarted:
            return "Cloud engine is not running."

        case .engineAlreadyStarted:
            return "Cloud engine is already running."

        case .invalidConfiguration:
            return "Invalid cloud engine configuration."

        case .routeNotFound:
            return "Route not found."

        case .methodNotAllowed:
            return "HTTP method not allowed."

        case .unauthorized:
            return "Authentication required."

        case .forbidden:
            return "Access denied."

        case .tooManyRequests:
            return "Rate limit exceeded."

        case .invalidRequest:
            return "Invalid request."

        case .invalidJSON:
            return "Invalid JSON."

        case .bodyTooLarge:
            return "Request body is too large."

        case .databaseUnavailable:
            return "Database unavailable."

        case .databaseFailure(let reason):
            return "Database failure: \(reason)"

        case .cacheFailure(let reason):
            return "Cache failure: \(reason)"

        case .jobNotFound:
            return "Job not found."

        case .queueUnavailable:
            return "Queue unavailable."

        case .workerUnavailable:
            return "Worker unavailable."

        case .timeout:
            return "Operation timed out."

        case .cancelled:
            return "Operation cancelled."

        case .serviceUnavailable:
            return "Service unavailable."

        case .internalError(let reason):
            return "Internal error: \(reason)"
        }
    }
}

// MARK: - IDs

public struct CloudRequestID: Hashable, Codable, Sendable {

    public let rawValue: UUID

    public init(rawValue: UUID = UUID()) {
        self.rawValue = rawValue
    }
}

public struct CloudJobID: Hashable, Codable, Sendable {

    public let rawValue: UUID

    public init(rawValue: UUID = UUID()) {
        self.rawValue = rawValue
    }
}

public struct CloudConnectionID: Hashable, Codable, Sendable {

    public let rawValue: UUID

    public init(rawValue: UUID = UUID()) {
        self.rawValue = rawValue
    }
}

public struct CloudServiceID: Hashable, Codable, Sendable {

    public let rawValue: String

    public init(_ rawValue: String) {
        self.rawValue = rawValue
    }
}

// MARK: - HTTP

public enum HTTPMethod: String, Codable, Sendable {

    case GET
    case POST
    case PUT
    case PATCH
    case DELETE
    case HEAD
    case OPTIONS
}

public struct HTTPHeaders: Sendable {

    private var values: [String: String] = [:]

    public init() {}

    public subscript(
        _ name: String
    ) -> String? {
        get {
            values[name.lowercased()]
        }
        set {
            values[name.lowercased()] = newValue
        }
    }

    public mutating func set(
        _ value: String,
        for name: String
    ) {
        values[name.lowercased()] = value
    }

    public func contains(
        _ name: String
    ) -> Bool {
        values[name.lowercased()] != nil
    }

    public func allValues()
        -> [String: String]
    {
        values
    }
}

// MARK: - HTTP Request

public struct CloudHTTPRequest: Sendable {

    public let id: CloudRequestID
    public let method: HTTPMethod
    public let path: String
    public let query: [String: String]

    public let headers: HTTPHeaders
    public let body: Data?

    public init(
        id: CloudRequestID = CloudRequestID(),
        method: HTTPMethod,
        path: String,
        query: [String: String] = [:],
        headers: HTTPHeaders = HTTPHeaders(),
        body: Data? = nil
    ) {
        self.id = id
        self.method = method
        self.path = path
        self.query = query
        self.headers = headers
        self.body = body
    }
}

// MARK: - HTTP Response

public struct CloudHTTPResponse: Sendable {

    public let statusCode: Int
    public let headers: HTTPHeaders
    public let body: Data?

    public init(
        statusCode: Int,
        headers: HTTPHeaders = HTTPHeaders(),
        body: Data? = nil
    ) {
        self.statusCode = statusCode
        self.headers = headers
        self.body = body
    }

    public static func json<T: Encodable>(
        _ value: T,
        statusCode: Int = 200
    ) throws -> CloudHTTPResponse {

        let data = try JSONEncoder().encode(value)

        var headers = HTTPHeaders()

        headers.set(
            "application/json",
            for: "Content-Type"
        )

        return CloudHTTPResponse(
            statusCode: statusCode,
            headers: headers,
            body: data
        )
    }

    public static func text(
        _ text: String,
        statusCode: Int = 200
    ) -> CloudHTTPResponse {

        var headers = HTTPHeaders()

        headers.set(
            "text/plain; charset=utf-8",
            for: "Content-Type"
        )

        return CloudHTTPResponse(
            statusCode: statusCode,
            headers: headers,
            body: Data(text.utf8)
        )
    }

    public static func empty(
        statusCode: Int
    ) -> CloudHTTPResponse {

        CloudHTTPResponse(
            statusCode: statusCode
        )
    }
}

// MARK: - Request Context

public struct CloudRequestContext: Sendable {

    public let request: CloudHTTPRequest
    public let receivedAt: Date

    public let remoteAddress: String?
    public let authenticatedUserID: String?

    public init(
        request: CloudHTTPRequest,
        receivedAt: Date = Date(),
        remoteAddress: String? = nil,
        authenticatedUserID: String? = nil
    ) {
        self.request = request
        self.receivedAt = receivedAt
        self.remoteAddress = remoteAddress
        self.authenticatedUserID =
            authenticatedUserID
    }
}

// MARK: - Route Handler

public typealias CloudRouteHandler =
    @Sendable (
        CloudRequestContext
    ) async throws -> CloudHTTPResponse

// MARK: - Route

public struct CloudRoute: Sendable {

    public let method: HTTPMethod
    public let path: String
    public let handler: CloudRouteHandler

    public init(
        method: HTTPMethod,
        path: String,
        handler: @escaping CloudRouteHandler
    ) {
        self.method = method
        self.path = path
        self.handler = handler
    }
}

// MARK: - Router

public actor CloudRouter {

    private var routes: [CloudRoute] = []

    public init() {}

    public func register(
        _ route: CloudRoute
    ) {
        routes.append(route)

        SwiftCloudLog.debug(
            "Registered \(route.method.rawValue) \(route.path)"
        )
    }

    public func register(
        method: HTTPMethod,
        path: String,
        handler: @escaping CloudRouteHandler
    ) {
        register(
            CloudRoute(
                method: method,
                path: path,
                handler: handler
            )
        )
    }

    public func route(
        method: HTTPMethod,
        path: String
    ) -> CloudRoute? {

        routes.first {
            $0.method == method &&
            $0.path == path
        }
    }

    public func routeCount() -> Int {
        routes.count
    }

    public func allRoutes()
        -> [(HTTPMethod, String)]
    {
        routes.map {
            ($0.method, $0.path)
        }
    }
}

// MARK: - Middleware

public protocol CloudMiddleware: Sendable {

    func handle(
        context: CloudRequestContext,
        next: @escaping CloudRouteHandler
    ) async throws -> CloudHTTPResponse
}

// MARK: - Authentication

public struct CloudIdentity: Sendable {

    public let userID: String
    public let roles: Set<String>

    public init(
        userID: String,
        roles: Set<String> = []
    ) {
        self.userID = userID
        self.roles = roles
    }

    public func hasRole(
        _ role: String
    ) -> Bool {
        roles.contains(role)
    }
}

public protocol CloudAuthenticator: Sendable {

    func authenticate(
        request: CloudHTTPRequest
    ) async throws -> CloudIdentity?
}

// MARK: - API Key Authenticator

public actor APIKeyAuthenticator:
    CloudAuthenticator {

    private var keys:
        [String: CloudIdentity] = [:]

    public init() {}

    public func register(
        key: String,
        identity: CloudIdentity
    ) {

        keys[key] = identity
    }

    public func revoke(
        key: String
    ) {

        keys.removeValue(
            forKey: key
        )
    }

    public func authenticate(
        request: CloudHTTPRequest
    ) async throws -> CloudIdentity? {

        guard let key =
            request.headers["authorization"]
        else {
            return nil
        }

        let normalized = key
            .replacingOccurrences(
                of: "Bearer ",
                with: ""
            )

        return keys[normalized]
    }
}

// MARK: - Rate Limiting

public struct RateLimitConfiguration:
    Sendable {

    public let maximumRequests: Int
    public let window: Duration

    public init(
        maximumRequests: Int = 100,
        window: Duration = .seconds(60)
    ) {
        self.maximumRequests =
            max(1, maximumRequests)

        self.window = window
    }
}

public actor CloudRateLimiter {

    private struct Bucket: Sendable {

        var start:
            ContinuousClock.Instant

        var count: Int
    }

    private let configuration:
        RateLimitConfiguration

    private let clock = ContinuousClock()

    private var buckets:
        [String: Bucket] = [:]

    public init(
        configuration: RateLimitConfiguration = .init()
    ) {
        self.configuration = configuration
    }

    public func allow(
        key: String
    ) -> Bool {

        let now = clock.now

        guard var bucket = buckets[key] else {

            buckets[key] = Bucket(
                start: now,
                count: 1
            )

            return true
        }

        let elapsed =
            bucket.start.duration(
                to: now
            )

        if elapsed >= configuration.window {

            bucket = Bucket(
                start: now,
                count: 1
            )

            buckets[key] = bucket

            return true
        }

        guard bucket.count <
                configuration.maximumRequests
        else {
            return false
        }

        bucket.count += 1

        buckets[key] = bucket

        return true
    }
}

// MARK: - Cache

public protocol CloudCache: Sendable {

    func get(
        key: String
    ) async throws -> Data?

    func set(
        key: String,
        value: Data,
        expiration: Duration?
    ) async throws

    func remove(
        key: String
    ) async throws

    func removeAll() async throws
}

public actor MemoryCloudCache:
    CloudCache {

    private struct Entry: Sendable {

        let value: Data
        let expiration:
            ContinuousClock.Instant?
    }

    private var values:
        [String: Entry] = [:]

    private let clock = ContinuousClock()

    public init() {}

    public func get(
        key: String
    ) async throws -> Data? {

        guard let entry = values[key] else {
            return nil
        }

        if let expiration =
            entry.expiration,
           expiration <= clock.now {

            values.removeValue(
                forKey: key
            )

            return nil
        }

        return entry.value
    }

    public func set(
        key: String,
        value: Data,
        expiration: Duration?
    ) async throws {

        let instant: ContinuousClock.Instant?

        if let expiration {

            instant =
                clock.now.advanced(
                    by: expiration
                )

        } else {

            instant = nil
        }

        values[key] = Entry(
            value: value,
            expiration: instant
        )
    }

    public func remove(
        key: String
    ) async throws {

        values.removeValue(
            forKey: key
        )
    }

    public func removeAll()
        async throws
    {
        values.removeAll()
    }
}

// MARK: - Database

public protocol CloudDatabase: Sendable {

    func execute(
        _ operation: String
    ) async throws

    func fetch(
        _ operation: String
    ) async throws -> [[String: String]]
}

public actor InMemoryCloudDatabase:
    CloudDatabase {

    private var rows:
        [[String: String]] = []

    public init() {}

    public func execute(
        _ operation: String
    ) async throws {

        SwiftCloudLog.debug(
            "Database operation: \(operation)"
        )
    }

    public func fetch(
        _ operation: String
    ) async throws
        -> [[String: String]]
    {

        rows
    }

    public func insert(
        _ row: [String: String]
    ) {
        rows.append(row)
    }
}

// MARK: - Jobs

public enum CloudJobState:
    String,
    Codable,
    Sendable {

    case queued
    case running
    case completed
    case failed
    case cancelled
}

public struct CloudJob: Codable, Sendable {

    public let id: CloudJobID
    public let type: String

    public let payload: Data

    public let createdAt: Date

    public var state: CloudJobState

    public var attempts: Int

    public init(
        id: CloudJobID = CloudJobID(),
        type: String,
        payload: Data,
        createdAt: Date = Date(),
        state: CloudJobState = .queued,
        attempts: Int = 0
    ) {

        self.id = id
        self.type = type
        self.payload = payload
        self.createdAt = createdAt
        self.state = state
        self.attempts = attempts
    }
}

// MARK: - Job Queue

public actor CloudJobQueue {

    private var jobs:
        [CloudJobID: CloudJob] = [:]

    private var order:
        [CloudJobID] = []

    public init() {}

    public func enqueue(
        _ job: CloudJob
    ) {

        jobs[job.id] = job
        order.append(job.id)

        SwiftCloudLog.debug(
            "Queued job \(job.id.rawValue)"
        )
    }

    public func dequeue() -> CloudJob? {

        while !order.isEmpty {

            let id = order.removeFirst()

            guard var job = jobs[id] else {
                continue
            }

            guard job.state == .queued else {
                continue
            }

            job.state = .running
            job.attempts += 1

            jobs[id] = job

            return job
        }

        return nil
    }

    public func complete(
        _ id: CloudJobID
    ) {

        guard var job = jobs[id] else {
            return
        }

        job.state = .completed

        jobs[id] = job
    }

    public func fail(
        _ id: CloudJobID
    ) {

        guard var job = jobs[id] else {
            return
        }

        job.state = .failed

        jobs[id] = job
    }

    public func cancel(
        _ id: CloudJobID
    ) {

        guard var job = jobs[id] else {
            return
        }

        job.state = .cancelled

        jobs[id] = job
    }

    public func job(
        id: CloudJobID
    ) -> CloudJob? {
        jobs[id]
    }

    public func count() -> Int {
        jobs.count
    }
}

// MARK: - Worker

public typealias CloudJobHandler =
    @Sendable (
        CloudJob
    ) async throws -> Void

public actor CloudWorker {

    public let identifier: String

    private let queue: CloudJobQueue

    private var handlers:
        [String: CloudJobHandler] = [:]

    private var running = false

    public init(
        identifier: String,
        queue: CloudJobQueue
    ) {

        self.identifier = identifier
        self.queue = queue
    }

    public func register(
        jobType: String,
        handler: @escaping CloudJobHandler
    ) {

        handlers[jobType] = handler
    }

    public func start() {

        guard !running else {
            return
        }

        running = true
    }

    public func stop() {

        running = false
    }

    public func runOnce()
        async throws
    {

        guard running else {
            throw CloudEngineError.workerUnavailable
        }

        guard let job =
                await queue.dequeue()
        else {
            return
        }

        guard let handler =
                handlers[job.type]
        else {

            await queue.fail(
                job.id
            )

            throw CloudEngineError.internalError(
                "No handler for \(job.type)"
            )
        }

        do {

            try await handler(job)

            await queue.complete(
                job.id
            )

        } catch {

            await queue.fail(
                job.id
            )

            throw error
        }
    }

    public func runLoop(
        interval: Duration = .milliseconds(100)
    ) async {

        while running {

            do {
                try await runOnce()
            } catch {
                SwiftCloudLog.error(
                    "Worker error: \(error.localizedDescription)"
                )
            }

            do {
                try await Task.sleep(
                    for: interval
                )
            } catch {
                break
            }
        }
    }
}

// MARK: - WebSocket

public enum CloudWebSocketEvent: Sendable {

    case connected
    case text(String)
    case binary(Data)
    case disconnected
}

public actor CloudWebSocketConnection {

    public let id: CloudConnectionID

    private var continuation:
        AsyncStream<CloudWebSocketEvent>.Continuation?

    private var active = true

    public init(
        id: CloudConnectionID = CloudConnectionID()
    ) {
        self.id = id
    }

    public func attach(
        _ continuation:
            AsyncStream<CloudWebSocketEvent>.Continuation
    ) {

        self.continuation = continuation

        continuation.yield(
            .connected
        )
    }

    public func send(
        text: String
    ) {

        guard active else {
            return
        }

        continuation?.yield(
            .text(text)
        )
    }

    public func send(
        binary: Data
    ) {

        guard active else {
            return
        }

        continuation?.yield(
            .binary(binary)
        )
    }

    public func close() {

        guard active else {
            return
        }

        active = false

        continuation?.yield(
            .disconnected
        )

        continuation?.finish()

        continuation = nil
    }

    public func isActive() -> Bool {
        active
    }
}

// MARK: - Connection Manager

public actor CloudConnectionManager {

    private var connections:
        [CloudConnectionID: CloudWebSocketConnection]
        = [:]

    public init() {}

    public func add(
        _ connection: CloudWebSocketConnection
    ) {

        connections[connection.id] =
            connection
    }

    public func remove(
        id: CloudConnectionID
    ) {

        connections.removeValue(
            forKey: id
        )
    }

    public func broadcast(
        text: String
    ) async {

        for connection in connections.values {

            await connection.send(
                text: text
            )
        }
    }

    public func connectionCount()
        -> Int
    {
        connections.count
    }

    public func closeAll()
        async
    {

        for connection in connections.values {
            await connection.close()
        }

        connections.removeAll()
    }
}

// MARK: - Service Health

public enum CloudHealthStatus:
    String,
    Codable,
    Sendable {

    case healthy
    case degraded
    case unhealthy
}

public struct CloudHealthReport:
    Codable,
    Sendable {

    public let service:
        CloudServiceID

    public let status:
        CloudHealthStatus

    public let timestamp:
        Date

    public let details:
        [String: String]

    public init(
        service: CloudServiceID,
        status: CloudHealthStatus,
        timestamp: Date = Date(),
        details: [String: String] = [:]
    ) {

        self.service = service
        self.status = status
        self.timestamp = timestamp
        self.details = details
    }
}

public actor CloudHealthRegistry {

    private var reports:
        [CloudServiceID: CloudHealthReport]
        = [:]

    public init() {}

    public func report(
        _ report: CloudHealthReport
    ) {

        reports[report.service] =
            report
    }

    public func report(
        for service: CloudServiceID
    ) -> CloudHealthReport? {

        reports[service]
    }

    public func allReports()
        -> [CloudHealthReport]
    {

        Array(reports.values)
    }

    public func overallStatus()
        -> CloudHealthStatus
    {

        if reports.values.contains(
            where: { $0.status == .unhealthy }
        ) {
            return .unhealthy
        }

        if reports.values.contains(
            where: { $0.status == .degraded }
        ) {
            return .degraded
        }

        return .healthy
    }
}

// MARK: - Metrics

public struct CloudMetricsSnapshot:
    Sendable {

    public let requestCount: UInt64
    public let successfulRequests: UInt64
    public let failedRequests: UInt64

    public let totalResponseTime:
        Duration

    public let activeRequests:
        Int

    public init(
        requestCount: UInt64,
        successfulRequests: UInt64,
        failedRequests: UInt64,
        totalResponseTime: Duration,
        activeRequests: Int
    ) {

        self.requestCount =
            requestCount

        self.successfulRequests =
            successfulRequests

        self.failedRequests =
            failedRequests

        self.totalResponseTime =
            totalResponseTime

        self.activeRequests =
            activeRequests
    }
}

public actor CloudMetrics {

    private var requestCount:
        UInt64 = 0

    private var successfulRequests:
        UInt64 = 0

    private var failedRequests:
        UInt64 = 0

    private var totalResponseTime:
        Duration = .zero

    private var activeRequests:
        Int = 0

    public init() {}

    public func beginRequest() {
        requestCount += 1
        activeRequests += 1
    }

    public func finishSuccess(
        duration: Duration
    ) {

        successfulRequests += 1
        totalResponseTime += duration
        activeRequests =
            max(0, activeRequests - 1)
    }

    public func finishFailure(
        duration: Duration
    ) {

        failedRequests += 1
        totalResponseTime += duration
        activeRequests =
            max(0, activeRequests - 1)
    }

    public func snapshot()
        -> CloudMetricsSnapshot
    {

        CloudMetricsSnapshot(
            requestCount: requestCount,
            successfulRequests:
                successfulRequests,
            failedRequests:
                failedRequests,
            totalResponseTime:
                totalResponseTime,
            activeRequests:
                activeRequests
        )
    }
}

// MARK: - Cloud Configuration

public struct SwiftCloudConfiguration:
    Sendable {

    public var serviceName: String

    public var host: String
    public var port: Int

    public var maximumBodyBytes:
        Int

    public var maximumConcurrentRequests:
        Int

    public var rateLimit:
        RateLimitConfiguration

    public init(
        serviceName: String = "SwiftCloudService",
        host: String = "127.0.0.1",
        port: Int = 8080,
        maximumBodyBytes: Int = 4_000_000,
        maximumConcurrentRequests: Int = 256,
        rateLimit:
            RateLimitConfiguration = .init()
    ) {

        self.serviceName =
            serviceName

        self.host = host
        self.port = port

        self.maximumBodyBytes =
            max(1, maximumBodyBytes)

        self.maximumConcurrentRequests =
            max(
                1,
                maximumConcurrentRequests
            )

        self.rateLimit = rateLimit
    }
}

// MARK: - Cloud Engine State

public enum SwiftCloudState:
    String,
    Sendable {

    case stopped
    case starting
    case running
    case stopping
    case failed
}

// MARK: - Cloud Engine

public actor SwiftCloudEngine {

    public let configuration:
        SwiftCloudConfiguration

    public let router:
        CloudRouter

    public let cache:
        any CloudCache

    public let database:
        any CloudDatabase

    public let jobQueue:
        CloudJobQueue

    public let connections:
        CloudConnectionManager

    public let health:
        CloudHealthRegistry

    public let metrics:
        CloudMetrics

    private let rateLimiter:
        CloudRateLimiter

    private var authenticator:
        (any CloudAuthenticator)?

    private var workers:
        [String: CloudWorker] = [:]

    private var state:
        SwiftCloudState = .stopped

    private var activeRequests:
        Int = 0

    public init(
        configuration:
            SwiftCloudConfiguration = .init(),
        cache:
            any CloudCache = MemoryCloudCache(),
        database:
            any CloudDatabase = InMemoryCloudDatabase()
    ) {

        self.configuration =
            configuration

        self.router =
            CloudRouter()

        self.cache =
            cache

        self.database =
            database

        self.jobQueue =
            CloudJobQueue()

        self.connections =
            CloudConnectionManager()

        self.health =
            CloudHealthRegistry()

        self.metrics =
            CloudMetrics()

        self.rateLimiter =
            CloudRateLimiter(
                configuration:
                    configuration.rateLimit
            )
    }

    // MARK: Lifecycle

    public func start()
        async throws
    {

        guard state == .stopped else {

            throw CloudEngineError
                .engineAlreadyStarted
        }

        state = .starting

        SwiftCloudLog.info(
            "Starting \(configuration.serviceName)"
        )

        await health.report(
            CloudHealthReport(
                service:
                    CloudServiceID(
                        configuration.serviceName
                    ),
                status: .healthy
            )
        )

        state = .running

        SwiftCloudLog.info(
            "Cloud engine running on " +
            "\(configuration.host):" +
            "\(configuration.port)"
        )
    }

    public func stop()
        async
    {

        guard state == .running else {

            state = .stopped

            return
        }

        state = .stopping

        for worker in workers.values {
            await worker.stop()
        }

        await connections.closeAll()

        state = .stopped

        SwiftCloudLog.info(
            "Cloud engine stopped"
        )
    }

    public func currentState()
        -> SwiftCloudState
    {
        state
    }

    // MARK: Authentication

    public func setAuthenticator(
        _ authenticator:
            any CloudAuthenticator
    ) {

        self.authenticator =
            authenticator
    }

    // MARK: Routes

    public func registerRoute(
        method: HTTPMethod,
        path: String,
        handler:
            @escaping CloudRouteHandler
    ) async {

        await router.register(
            method: method,
            path: path,
            handler: handler
        )
    }

    // MARK: Request Processing

    public func handle(
        _ request: CloudHTTPRequest,
        remoteAddress: String? = nil
    ) async throws
        -> CloudHTTPResponse
    {

        guard state == .running else {
            throw CloudEngineError.engineNotStarted
        }

        if let body = request.body,
           body.count >
                configuration.maximumBodyBytes {

            throw CloudEngineError.bodyTooLarge
        }

        guard activeRequests <
                configuration
                    .maximumConcurrentRequests
        else {

            throw CloudEngineError
                .tooManyRequests
        }

        let rateKey =
            remoteAddress
            ?? "anonymous"

        guard await rateLimiter.allow(
            key: rateKey
        ) else {

            throw CloudEngineError
                .tooManyRequests
        }

        activeRequests += 1

        await metrics.beginRequest()

        let start =
            ContinuousClock.now

        defer {
            activeRequests =
                max(
                    0,
                    activeRequests - 1
                )
        }

        let identity:
            CloudIdentity?

        if let authenticator {

            identity =
                try await authenticator
                    .authenticate(
                        request: request
                    )

        } else {

            identity = nil
        }

        let context =
            CloudRequestContext(
                request: request,
                remoteAddress:
                    remoteAddress,
                authenticatedUserID:
                    identity?.userID
            )

        guard let route =
                await router.route(
                    method: request.method,
                    path: request.path
                )
        else {

            let duration =
                start.duration(
                    to: ContinuousClock.now
                )

            await metrics.finishFailure(
                duration: duration
            )

            throw CloudEngineError
                .routeNotFound
        }

        do {

            let response =
                try await route.handler(
                    context
                )

            let duration =
                start.duration(
                    to: ContinuousClock.now
                )

            await metrics.finishSuccess(
                duration: duration
            )

            return response

        } catch {

            let duration =
                start.duration(
                    to: ContinuousClock.now
                )

            await metrics.finishFailure(
                duration: duration
            )

            throw error
        }
    }

    // MARK: JSON Convenience

    public func decodeJSON<T: Decodable>(
        _ type: T.Type,
        from request: CloudHTTPRequest
    ) throws -> T {

        guard let body =
                request.body
        else {

            throw CloudEngineError
                .invalidRequest
        }

        do {

            return try JSONDecoder()
                .decode(
                    T.self,
                    from: body
                )

        } catch {

            throw CloudEngineError
                .invalidJSON
        }
    }

    // MARK: Jobs

    public func enqueueJob<T: Encodable>(
        type: String,
        payload: T
    ) async throws
        -> CloudJobID
    {

        let data =
            try JSONEncoder()
                .encode(payload)

        let job =
            CloudJob(
                type: type,
                payload: data
            )

        await jobQueue.enqueue(
            job
        )

        return job.id
    }

    public func registerWorker(
        _ worker: CloudWorker
    ) async {

        workers[worker.identifier] =
            worker

        await worker.start()
    }

    public func runWorker(
        identifier: String
    ) async throws {

        guard let worker =
                workers[identifier]
        else {

            throw CloudEngineError
                .workerUnavailable
        }

        try await worker.runOnce()
    }

    // MARK: Cache

    public func cacheSet<T: Encodable>(
        _ value: T,
        key: String,
        expiration: Duration? = nil
    ) async throws {

        let data =
            try JSONEncoder()
                .encode(value)

        try await cache.set(
            key: key,
            value: data,
            expiration: expiration
        )
    }

    public func cacheGet<T: Decodable>(
        _ type: T.Type,
        key: String
    ) async throws -> T? {

        guard let data =
                try await cache.get(
                    key: key
                )
        else {
            return nil
        }

        return try JSONDecoder()
            .decode(
                T.self,
                from: data
            )
    }

    // MARK: Health

    public func healthReport()
        async -> CloudHealthReport
    {

        let status =
            await health.overallStatus()

        return CloudHealthReport(
            service:
                CloudServiceID(
                    configuration.serviceName
                ),
            status: status,
            details: [
                "state":
                    state.rawValue,
                "routes":
                    String(
                        await router.routeCount()
                    ),
                "connections":
                    String(
                        await connections
                            .connectionCount()
                    )
            ]
        )
    }

    // MARK: Metrics

    public func metricsSnapshot()
        async -> CloudMetricsSnapshot
    {
        await metrics.snapshot()
    }
}

// MARK: - Example API Models

public struct HealthResponse:
    Codable,
    Sendable {

    public let status: String
    public let service: String

    public init(
        status: String,
        service: String
    ) {
        self.status = status
        self.service = service
    }
}

public struct EchoRequest:
    Codable,
    Sendable {

    public let message: String

    public init(
        message: String
    ) {
        self.message = message
    }
}

public struct EchoResponse:
    Codable,
    Sendable {

    public let message: String
    public let timestamp: Date

    public init(
        message: String,
        timestamp: Date = Date()
    ) {
        self.message = message
        self.timestamp = timestamp
    }
}

// MARK: - Example Service

public enum SwiftCloudExample {

    public static func makeEngine()
        async throws -> SwiftCloudEngine
    {

        let engine =
            SwiftCloudEngine(
                configuration:
                    SwiftCloudConfiguration(
                        serviceName:
                            "IndustrialSwiftAPI",
                        host:
                            "0.0.0.0",
                        port:
                            8080,
                        maximumBodyBytes:
                            8_000_000,
                        maximumConcurrentRequests:
                            512
                    )
            )

        let authentication =
            APIKeyAuthenticator()

        await authentication.register(
            key: "development-key",
            identity:
                CloudIdentity(
                    userID: "developer",
                    roles: [
                        "admin"
                    ]
                )
        )

        await engine.setAuthenticator(
            authentication
        )

        try await engine.start()

        await engine.registerRoute(
            method: .GET,
            path: "/health"
        ) { context in

            let response =
                HealthResponse(
                    status: "ok",
                    service:
                        "IndustrialSwiftAPI"
                )

            return try CloudHTTPResponse
                .json(
                    response
                )
        }

        await engine.registerRoute(
            method: .POST,
            path: "/echo"
        ) { context in

            let body =
                context.request.body
                ?? Data()

            let input =
                try JSONDecoder()
                    .decode(
                        EchoRequest.self,
                        from: body
                    )

            return try CloudHTTPResponse
                .json(
                    EchoResponse(
                        message:
                            input.message
                    )
                )
        }

        return engine
    }

    public static func run()
        async throws {

        let engine =
            try await makeEngine()

        var headers =
            HTTPHeaders()

        headers.set(
            "Bearer development-key",
            for: "Authorization"
        )

        let request =
            CloudHTTPRequest(
                method: .GET,
                path: "/health",
                headers: headers
            )

        let response =
            try await engine.handle(
                request,
                remoteAddress:
                    "127.0.0.1"
            )

        print(
            "HTTP:",
            response.statusCode
        )

        let metrics =
            await engine.metricsSnapshot()

        print(
            "Requests:",
            metrics.requestCount
        )
    }
}



//
// SwiftIndustrialTelemetry.swift
//
// Swift 6
// Industrial telemetry / time-series processing foundation.
//

import Foundation
import os

// MARK: - Logging

public enum IndustrialTelemetryLog {

    private static let logger = Logger(
        subsystem: "SwiftIndustrialTelemetry",
        category: "Runtime"
    )

    public static func info(_ message: String) {
        logger.info("\(message, privacy: .public)")
    }

    public static func debug(_ message: String) {
        logger.debug("\(message, privacy: .public)")
    }

    public static func warning(_ message: String) {
        logger.warning("\(message, privacy: .public)")
    }

    public static func error(_ message: String) {
        logger.error("\(message, privacy: .public)")
    }
}

// MARK: - Errors

public enum TelemetryError:
    Error,
    LocalizedError,
    Sendable {

    case invalidSensorID
    case invalidTimestamp
    case invalidValue

    case duplicateSample
    case outOfOrderSample

    case bufferFull
    case bufferEmpty

    case sensorNotFound

    case invalidConfiguration
    case storageUnavailable

    case aggregationFailure
    case processingFailure(String)

    public var errorDescription: String? {

        switch self {

        case .invalidSensorID:
            return "Invalid sensor identifier."

        case .invalidTimestamp:
            return "Invalid telemetry timestamp."

        case .invalidValue:
            return "Invalid telemetry value."

        case .duplicateSample:
            return "Duplicate telemetry sample."

        case .outOfOrderSample:
            return "Telemetry sample arrived out of order."

        case .bufferFull:
            return "Telemetry buffer is full."

        case .bufferEmpty:
            return "Telemetry buffer is empty."

        case .sensorNotFound:
            return "Sensor was not found."

        case .invalidConfiguration:
            return "Invalid telemetry configuration."

        case .storageUnavailable:
            return "Telemetry storage is unavailable."

        case .aggregationFailure:
            return "Telemetry aggregation failed."

        case .processingFailure(let message):
            return "Telemetry processing failed: \(message)"
        }
    }
}

// MARK: - IDs

public struct SensorID:
    Hashable,
    Codable,
    Sendable {

    public let rawValue: String

    public init(
        _ rawValue: String
    ) {

        self.rawValue =
            rawValue
    }
}

public struct DeviceID:
    Hashable,
    Codable,
    Sendable {

    public let rawValue: String

    public init(
        _ rawValue: String
    ) {

        self.rawValue =
            rawValue
    }
}

public struct TelemetryStreamID:
    Hashable,
    Codable,
    Sendable {

    public let rawValue: UUID

    public init(
        _ rawValue: UUID = UUID()
    ) {

        self.rawValue =
            rawValue
    }
}

public struct TelemetryBatchID:
    Hashable,
    Codable,
    Sendable {

    public let rawValue: UUID

    public init(
        _ rawValue: UUID = UUID()
    ) {

        self.rawValue =
            rawValue
    }
}

// MARK: - Sensor Definition

public enum SensorKind:
    String,
    Codable,
    Sendable {

    case temperature
    case pressure
    case humidity

    case voltage
    case current
    case power
    case energy

    case speed
    case acceleration
    case vibration

    case flow
    case level

    case position
    case torque
    case force

    case radiation
    case acoustic

    case generic
}

public struct SensorDefinition:
    Codable,
    Sendable {

    public let id: SensorID
    public let deviceID: DeviceID

    public let name: String
    public let kind: SensorKind

    public let unit: String

    public let minimumValue: Double?
    public let maximumValue: Double?

    public init(
        id: SensorID,
        deviceID: DeviceID,
        name: String,
        kind: SensorKind,
        unit: String,
        minimumValue: Double? = nil,
        maximumValue: Double? = nil
    ) {

        self.id = id
        self.deviceID = deviceID
        self.name = name
        self.kind = kind
        self.unit = unit
        self.minimumValue = minimumValue
        self.maximumValue = maximumValue
    }
}

// MARK: - Quality

public enum TelemetryQuality:
    Int,
    Codable,
    Comparable,
    Sendable {

    case unknown = 0
    case bad = 1
    case uncertain = 2
    case good = 3

    public static func < (
        lhs: TelemetryQuality,
        rhs: TelemetryQuality
    ) -> Bool {

        lhs.rawValue < rhs.rawValue
    }
}

// MARK: - Telemetry Sample

public struct TelemetrySample:
    Codable,
    Sendable {

    public let sensorID: SensorID

    public let timestamp: Date

    public let value: Double

    public let quality:
        TelemetryQuality

    public let sequenceNumber: UInt64?

    public init(
        sensorID: SensorID,
        timestamp: Date = Date(),
        value: Double,
        quality:
            TelemetryQuality = .good,
        sequenceNumber: UInt64? = nil
    ) {

        self.sensorID = sensorID
        self.timestamp = timestamp
        self.value = value
        self.quality = quality
        self.sequenceNumber =
            sequenceNumber
    }
}

// MARK: - Batch

public struct TelemetryBatch:
    Codable,
    Sendable {

    public let id: TelemetryBatchID

    public let createdAt: Date

    public let samples:
        [TelemetrySample]

    public init(
        id: TelemetryBatchID =
            TelemetryBatchID(),
        createdAt: Date = Date(),
        samples: [TelemetrySample]
    ) {

        self.id = id
        self.createdAt = createdAt
        self.samples = samples
    }
}

// MARK: - Statistics

public struct TelemetryStatistics:
    Codable,
    Sendable {

    public let count: Int

    public let minimum: Double?
    public let maximum: Double?

    public let mean: Double?
    public let standardDeviation: Double?

    public let sum: Double

    public let firstTimestamp: Date?
    public let lastTimestamp: Date?

    public init(
        count: Int,
        minimum: Double?,
        maximum: Double?,
        mean: Double?,
        standardDeviation: Double?,
        sum: Double,
        firstTimestamp: Date?,
        lastTimestamp: Date?
    ) {

        self.count = count
        self.minimum = minimum
        self.maximum = maximum
        self.mean = mean
        self.standardDeviation =
            standardDeviation
        self.sum = sum
        self.firstTimestamp =
            firstTimestamp
        self.lastTimestamp =
            lastTimestamp
    }
}

// MARK: - Statistics Calculator

public enum TelemetryStatisticsCalculator {

    public static func calculate(
        _ samples: [TelemetrySample]
    ) -> TelemetryStatistics {

        guard !samples.isEmpty else {

            return TelemetryStatistics(
                count: 0,
                minimum: nil,
                maximum: nil,
                mean: nil,
                standardDeviation: nil,
                sum: 0,
                firstTimestamp: nil,
                lastTimestamp: nil
            )
        }

        let values =
            samples.map(\.value)

        let sum =
            values.reduce(
                0,
                +
            )

        let mean =
            sum / Double(values.count)

        let variance =
            values.reduce(
                0
            ) { partial, value in

                let delta =
                    value - mean

                return partial +
                    delta * delta
            }
            / Double(values.count)

        return TelemetryStatistics(
            count: values.count,
            minimum: values.min(),
            maximum: values.max(),
            mean: mean,
            standardDeviation:
                sqrt(variance),
            sum: sum,
            firstTimestamp:
                samples.map(\.timestamp).min(),
            lastTimestamp:
                samples.map(\.timestamp).max()
        )
    }
}

// MARK: - Sensor Registry

public actor SensorRegistry {

    private var sensors:
        [SensorID: SensorDefinition] = [:]

    public init() {}

    public func register(
        _ sensor: SensorDefinition
    ) {

        sensors[sensor.id] =
            sensor

        IndustrialTelemetryLog.debug(
            "Registered sensor \(sensor.id.rawValue)"
        )
    }

    public func remove(
        id: SensorID
    ) {

        sensors.removeValue(
            forKey: id
        )
    }

    public func sensor(
        id: SensorID
    ) -> SensorDefinition? {

        sensors[id]
    }

    public func contains(
        id: SensorID
    ) -> Bool {

        sensors[id] != nil
    }

    public func allSensors()
        -> [SensorDefinition]
    {

        Array(sensors.values)
    }

    public func count() -> Int {
        sensors.count
    }
}

// MARK: - Validator

public struct TelemetryValidationConfiguration:
    Sendable {

    public let maximumFutureSkew:
        TimeInterval

    public let maximumPastAge:
        TimeInterval

    public init(
        maximumFutureSkew: TimeInterval = 5,
        maximumPastAge: TimeInterval = 86_400
    ) {

        self.maximumFutureSkew =
            maximumFutureSkew

        self.maximumPastAge =
            maximumPastAge
    }
}

public actor TelemetryValidator {

    private let configuration:
        TelemetryValidationConfiguration

    private let registry:
        SensorRegistry

    public init(
        configuration:
            TelemetryValidationConfiguration = .init(),
        registry:
            SensorRegistry
    ) {

        self.configuration =
            configuration

        self.registry =
            registry
    }

    public func validate(
        _ sample: TelemetrySample
    ) async throws {

        guard !sample.sensorID.rawValue
            .isEmpty
        else {
            throw TelemetryError.invalidSensorID
        }

        guard sample.timestamp.timeIntervalSince1970
            .isFinite
        else {
            throw TelemetryError.invalidTimestamp
        }

        guard sample.value.isFinite else {
            throw TelemetryError.invalidValue
        }

        guard await registry.contains(
            id: sample.sensorID
        ) else {
            throw TelemetryError.sensorNotFound
        }

        let now =
            Date()

        let futureDistance =
            sample.timestamp
                .timeIntervalSince(now)

        if futureDistance >
            configuration.maximumFutureSkew {

            throw TelemetryError.invalidTimestamp
        }

        let age =
            now.timeIntervalSince(
                sample.timestamp
            )

        if age >
            configuration.maximumPastAge {

            throw TelemetryError.invalidTimestamp
        }

        if let sensor =
            await registry.sensor(
                id: sample.sensorID
            ) {

            if let minimum =
                sensor.minimumValue,
               sample.value < minimum {

                throw TelemetryError.invalidValue
            }

            if let maximum =
                sensor.maximumValue,
               sample.value > maximum {

                throw TelemetryError.invalidValue
            }
        }
    }
}

// MARK: - Ingestion Buffer

public actor TelemetryBuffer {

    private var storage:
        [TelemetrySample] = []

    private let capacity:
        Int

    public init(
        capacity: Int = 100_000
    ) {

        self.capacity =
            max(1, capacity)
    }

    public func append(
        _ sample: TelemetrySample
    ) throws {

        guard storage.count < capacity else {
            throw TelemetryError.bufferFull
        }

        storage.append(sample)
    }

    public func append(
        _ samples: [TelemetrySample]
    ) throws {

        guard
            storage.count +
            samples.count <= capacity
        else {
            throw TelemetryError.bufferFull
        }

        storage.append(
            contentsOf: samples
        )
    }

    public func pop(
        maximum: Int
    ) -> [TelemetrySample] {

        let amount =
            min(
                max(0, maximum),
                storage.count
            )

        guard amount > 0 else {
            return []
        }

        let result =
            Array(
                storage.prefix(amount)
            )

        storage.removeFirst(amount)

        return result
    }

    public func count() -> Int {
        storage.count
    }

    public func clear() {
        storage.removeAll()
    }
}

// MARK: - Time Series Store

public protocol TelemetryStore:
    Sendable {

    func append(
        _ sample: TelemetrySample
    ) async throws

    func append(
        _ samples: [TelemetrySample]
    ) async throws

    func query(
        sensorID: SensorID,
        from: Date,
        to: Date
    ) async throws -> [TelemetrySample]

    func latest(
        sensorID: SensorID
    ) async throws -> TelemetrySample?

    func count(
        sensorID: SensorID
    ) async throws -> Int
}

// MARK: - In Memory Store

public actor InMemoryTelemetryStore:
    TelemetryStore {

    private var samples:
        [SensorID: [TelemetrySample]] = [:]

    public init() {}

    public func append(
        _ sample: TelemetrySample
    ) async throws {

        samples[sample.sensorID, default: []]
            .append(sample)
    }

    public func append(
        _ samples: [TelemetrySample]
    ) async throws {

        for sample in samples {

            self.samples[
                sample.sensorID,
                default: []
            ].append(sample)
        }
    }

    public func query(
        sensorID: SensorID,
        from: Date,
        to: Date
    ) async throws
        -> [TelemetrySample]
    {

        guard
            let values =
                samples[sensorID]
        else {
            return []
        }

        return values.filter {
            $0.timestamp >= from &&
            $0.timestamp <= to
        }
    }

    public func latest(
        sensorID: SensorID
    ) async throws
        -> TelemetrySample?
    {

        samples[sensorID]?
            .max(
                by: {
                    $0.timestamp <
                    $1.timestamp
                }
            )
    }

    public func count(
        sensorID: SensorID
    ) async throws
        -> Int
    {

        samples[sensorID]?.count ?? 0
    }
}

// MARK: - Rolling Window

public struct RollingWindow:
    Sendable {

    public let duration:
        TimeInterval

    public init(
        duration: TimeInterval
    ) {
        self.duration =
            max(0, duration)
    }
}

public actor RollingTelemetryWindow {

    private struct Entry:
        Sendable {

        let timestamp: Date
        let value: Double
    }

    private let window:
        RollingWindow

    private var entries:
        [Entry] = []

    public init(
        window: RollingWindow
    ) {

        self.window =
            window
    }

    public func add(
        _ sample: TelemetrySample
    ) {

        entries.append(
            Entry(
                timestamp:
                    sample.timestamp,
                value:
                    sample.value
            )
        )

        prune(
            reference:
                sample.timestamp
        )
    }

    public func values() -> [Double] {

        entries.map(\.value)
    }

    public func statistics()
        -> TelemetryStatistics
    {

        let samples =
            entries.map {
                TelemetrySample(
                    sensorID:
                        SensorID("window"),
                    timestamp:
                        $0.timestamp,
                    value:
                        $0.value
                )
            }

        return TelemetryStatisticsCalculator
            .calculate(samples)
    }

    private func prune(
        reference: Date
    ) {

        let cutoff =
            reference.addingTimeInterval(
                -window.duration
            )

        entries.removeAll {
            $0.timestamp < cutoff
        }
    }
}

// MARK: - Exponential Moving Average

public actor ExponentialMovingAverage {

    private let alpha: Double

    private var value:
        Double?

    public init(
        alpha: Double = 0.2
    ) {

        self.alpha =
            min(
                1,
                max(0.000001, alpha)
            )
    }

    public func update(
        _ newValue: Double
    ) -> Double {

        guard let previous = value else {

            value = newValue

            return newValue
        }

        let next =
            alpha * newValue +
            (1 - alpha) * previous

        value = next

        return next
    }

    public func current()
        -> Double?
    {
        value
    }

    public func reset() {
        value = nil
    }
}

// MARK: - Anomaly Detection

public enum AnomalySeverity:
    String,
    Codable,
    Sendable {

    case information
    case warning
    case critical
}

public struct TelemetryAnomaly:
    Codable,
    Sendable {

    public let sensorID:
        SensorID

    public let timestamp:
        Date

    public let value:
        Double

    public let expected:
        Double?

    public let deviation:
        Double?

    public let severity:
        AnomalySeverity

    public let reason:
        String

    public init(
        sensorID: SensorID,
        timestamp: Date,
        value: Double,
        expected: Double?,
        deviation: Double?,
        severity: AnomalySeverity,
        reason: String
    ) {

        self.sensorID = sensorID
        self.timestamp = timestamp
        self.value = value
        self.expected = expected
        self.deviation = deviation
        self.severity = severity
        self.reason = reason
    }
}

// MARK: - Z Score Detector

public actor ZScoreAnomalyDetector {

    private let threshold:
        Double

    private var values:
        [Double] = []

    private let maximumHistory:
        Int

    public init(
        threshold: Double = 3.0,
        maximumHistory: Int = 1_000
    ) {

        self.threshold =
            max(0.1, threshold)

        self.maximumHistory =
            max(10, maximumHistory)
    }

    public func evaluate(
        _ sample: TelemetrySample
    ) -> TelemetryAnomaly? {

        defer {

            values.append(
                sample.value
            )

            if values.count >
                maximumHistory {

                values.removeFirst(
                    values.count -
                    maximumHistory
                )
            }
        }

        guard values.count >= 10 else {
            return nil
        }

        let mean =
            values.reduce(
                0,
                +
            ) /
            Double(values.count)

        let variance =
            values.reduce(
                0
            ) { partial, value in

                let difference =
                    value - mean

                return partial +
                    difference *
                    difference
            }
            /
            Double(values.count)

        let standardDeviation =
            sqrt(variance)

        guard standardDeviation > 0 else {
            return nil
        }

        let zScore =
            abs(
                sample.value - mean
            ) /
            standardDeviation

        guard zScore >= threshold else {
            return nil
        }

        let severity:
            AnomalySeverity =
            zScore >= threshold * 2
            ? .critical
            : .warning

        return TelemetryAnomaly(
            sensorID:
                sample.sensorID,
            timestamp:
                sample.timestamp,
            value:
                sample.value,
            expected:
                mean,
            deviation:
                zScore,
            severity:
                severity,
            reason:
                "Value exceeded statistical threshold."
        )
    }
}

// MARK: - Threshold Detector

public struct ThresholdRule:
    Sendable {

    public let minimum:
        Double?

    public let maximum:
        Double?

    public init(
        minimum: Double? = nil,
        maximum: Double? = nil
    ) {

        self.minimum = minimum
        self.maximum = maximum
    }
}

public struct ThresholdDetector:
    Sendable {

    public let rule:
        ThresholdRule

    public init(
        rule: ThresholdRule
    ) {

        self.rule = rule
    }

    public func evaluate(
        _ sample: TelemetrySample
    ) -> TelemetryAnomaly? {

        if let maximum =
            rule.maximum,
           sample.value > maximum {

            return TelemetryAnomaly(
                sensorID:
                    sample.sensorID,
                timestamp:
                    sample.timestamp,
                value:
                    sample.value,
                expected:
                    maximum,
                deviation:
                    sample.value - maximum,
                severity:
                    .critical,
                reason:
                    "Maximum threshold exceeded."
            )
        }

        if let minimum =
            rule.minimum,
           sample.value < minimum {

            return TelemetryAnomaly(
                sensorID:
                    sample.sensorID,
                timestamp:
                    sample.timestamp,
                value:
                    sample.value,
                expected:
                    minimum,
                deviation:
                    minimum - sample.value,
                severity:
                    .critical,
                reason:
                    "Minimum threshold breached."
            )
        }

        return nil
    }
}

// MARK: - Aggregation

public enum AggregationMethod:
    String,
    Codable,
    Sendable {

    case minimum
    case maximum
    case average
    case sum
    case count
    case first
    case last
}

public struct AggregatedTelemetry:
    Codable,
    Sendable {

    public let sensorID:
        SensorID

    public let start:
        Date

    public let end:
        Date

    public let method:
        AggregationMethod

    public let value:
        Double

    public let sampleCount:
        Int

    public init(
        sensorID: SensorID,
        start: Date,
        end: Date,
        method: AggregationMethod,
        value: Double,
        sampleCount: Int
    ) {

        self.sensorID = sensorID
        self.start = start
        self.end = end
        self.method = method
        self.value = value
        self.sampleCount = sampleCount
    }
}

public enum TelemetryAggregator {

    public static func aggregate(
        samples: [TelemetrySample],
        method: AggregationMethod
    ) throws -> Double {

        guard !samples.isEmpty else {
            throw TelemetryError
                .aggregationFailure
        }

        let values =
            samples.map(\.value)

        switch method {

        case .minimum:
            return values.min()!

        case .maximum:
            return values.max()!

        case .average:

            return values.reduce(
                0,
                +
            ) /
            Double(values.count)

        case .sum:

            return values.reduce(
                0,
                +
            )

        case .count:

            return Double(values.count)

        case .first:

            return samples.first!.value

        case .last:

            return samples.last!.value
        }
    }
}

// MARK: - Downsampling

public actor TelemetryDownsampler {

    public init() {}

    public func downsample(
        samples: [TelemetrySample],
        bucketSize: TimeInterval
    ) -> [TelemetrySample] {

        guard
            !samples.isEmpty,
            bucketSize > 0
        else {
            return samples
        }

        let sorted =
            samples.sorted {
                $0.timestamp <
                $1.timestamp
            }

        guard let first =
                sorted.first
        else {
            return []
        }

        var buckets:
            [Int: [TelemetrySample]] = [:]

        for sample in sorted {

            let offset =
                sample.timestamp
                    .timeIntervalSince(
                        first.timestamp
                    )

            let bucket =
                Int(
                    floor(
                        offset /
                        bucketSize
                    )
                )

            buckets[bucket, default: []]
                .append(sample)
        }

        return buckets
            .keys
            .sorted()
            .compactMap { bucket in

                guard let values =
                    buckets[bucket],
                    !values.isEmpty
                else {
                    return nil
                }

                let average =
                    values
                        .map(\.value)
                        .reduce(
                            0,
                            +
                        ) /
                    Double(values.count)

                let timestamp =
                    values.first!.timestamp

                return TelemetrySample(
                    sensorID:
                        values.first!.sensorID,
                    timestamp:
                        timestamp,
                    value:
                        average,
                    quality:
                        values
                            .map(\.quality)
                            .min()
                            ?? .unknown
                )
            }
    }
}

// MARK: - Pipeline Processor

public protocol TelemetryProcessor:
    Sendable {

    func process(
        _ sample: TelemetrySample
    ) async throws
}

public actor TelemetryPipeline {

    private var processors:
        [any TelemetryProcessor] = []

    private let store:
        any TelemetryStore

    public init(
        store: any TelemetryStore
    ) {

        self.store =
            store
    }

    public func addProcessor(
        _ processor:
            any TelemetryProcessor
    ) {

        processors.append(
            processor
        )
    }

    public func process(
        _ sample: TelemetrySample
    ) async throws {

        try await store.append(
            sample
        )

        for processor in processors {

            try await processor.process(
                sample
            )
        }
    }
}

// MARK: - Anomaly Processor

public actor AnomalyProcessor:
    TelemetryProcessor {

    private let detector:
        ZScoreAnomalyDetector

    private var anomalies:
        [TelemetryAnomaly] = []

    public init(
        detector:
            ZScoreAnomalyDetector =
                ZScoreAnomalyDetector()
    ) {

        self.detector =
            detector
    }

    public func process(
        _ sample: TelemetrySample
    ) async throws {

        if let anomaly =
            await detector.evaluate(
                sample
            ) {

            anomalies.append(
                anomaly
            )

            IndustrialTelemetryLog.warning(
                "Anomaly detected for " +
                "\(sample.sensorID.rawValue)"
            )
        }
    }

    public func allAnomalies()
        -> [TelemetryAnomaly]
    {
        anomalies
    }

    public func clear() {
        anomalies.removeAll()
    }
}

// MARK: - EMA Processor

public actor EMAProcessor:
    TelemetryProcessor {

    private var filters:
        [SensorID: ExponentialMovingAverage]
        = [:]

    private let alpha:
        Double

    public init(
        alpha: Double = 0.2
    ) {

        self.alpha = alpha
    }

    public func process(
        _ sample: TelemetrySample
    ) async throws {

        let filter:
            ExponentialMovingAverage

        if let existing =
            filters[sample.sensorID] {

            filter = existing

        } else {

            filter =
                ExponentialMovingAverage(
                    alpha: alpha
                )

            filters[sample.sensorID] =
                filter
        }

        _ = await filter.update(
            sample.value
        )
    }

    public func smoothedValue(
        sensorID: SensorID
    ) async -> Double? {

        guard let filter =
            filters[sensorID]
        else {
            return nil
        }

        return await filter.current()
    }
}

// MARK: - Telemetry Subscription

public struct TelemetrySubscriptionID:
    Hashable,
    Sendable {

    public let rawValue:
        UUID

    public init(
        _ rawValue: UUID = UUID()
    ) {

        self.rawValue =
            rawValue
    }
}

public actor TelemetryStream {

    private struct Subscriber:
        Sendable {

        let id:
            TelemetrySubscriptionID

        let continuation:
            AsyncStream<TelemetrySample>
                .Continuation
    }

    private var subscribers:
        [TelemetrySubscriptionID: Subscriber]
        = [:]

    public init() {}

    public func subscribe()
        -> (
            TelemetrySubscriptionID,
            AsyncStream<TelemetrySample>
        )
    {

        let id =
            TelemetrySubscriptionID()

        let stream =
            AsyncStream<
                TelemetrySample
            > { continuation in

                let subscriber =
                    Subscriber(
                        id: id,
                        continuation:
                            continuation
                    )

                Task {
                    await self.add(
                        subscriber
                    )
                }

                continuation.onTermination = {
                    _ in

                    Task {
                        await self.remove(
                            id: id
                        )
                    }
                }
            }

        return (
            id,
            stream
        )
    }

    private func add(
        _ subscriber: Subscriber
    ) {

        subscribers[subscriber.id] =
            subscriber
    }

    private func remove(
        id: TelemetrySubscriptionID
    ) {

        subscribers.removeValue(
            forKey: id
        )
    }

    public func publish(
        _ sample: TelemetrySample
    ) {

        for subscriber in
            subscribers.values {

            subscriber.continuation.yield(
                sample
            )
        }
    }

    public func finish() {

        for subscriber in
            subscribers.values {

            subscriber.continuation.finish()
        }

        subscribers.removeAll()
    }

    public func subscriberCount()
        -> Int
    {
        subscribers.count
    }
}

// MARK: - Telemetry Engine Configuration

public struct IndustrialTelemetryConfiguration:
    Sendable {

    public let bufferCapacity:
        Int

    public let maximumBatchSize:
        Int

    public let validation:
        TelemetryValidationConfiguration

    public let downsampleBucket:
        TimeInterval

    public init(
        bufferCapacity: Int = 100_000,
        maximumBatchSize: Int = 1_000,
        validation:
            TelemetryValidationConfiguration =
                .init(),
        downsampleBucket:
            TimeInterval = 1
    ) {

        self.bufferCapacity =
            max(1, bufferCapacity)

        self.maximumBatchSize =
            max(1, maximumBatchSize)

        self.validation =
            validation

        self.downsampleBucket =
            max(0, downsampleBucket)
    }
}

// MARK: - Engine

public actor IndustrialTelemetryEngine {

    public let configuration:
        IndustrialTelemetryConfiguration

    public let registry:
        SensorRegistry

    public let store:
        any TelemetryStore

    public let buffer:
        TelemetryBuffer

    public let stream:
        TelemetryStream

    private let validator:
        TelemetryValidator

    private var running =
        false

    private var acceptedSamples:
        UInt64 = 0

    private var rejectedSamples:
        UInt64 = 0

    private var processedBatches:
        UInt64 = 0

    public init(
        configuration:
            IndustrialTelemetryConfiguration =
                .init(),
        store:
            any TelemetryStore =
                InMemoryTelemetryStore()
    ) {

        self.configuration =
            configuration

        self.registry =
            SensorRegistry()

        self.store =
            store

        self.buffer =
            TelemetryBuffer(
                capacity:
                    configuration.bufferCapacity
            )

        self.stream =
            TelemetryStream()

        self.validator =
            TelemetryValidator(
                configuration:
                    configuration.validation,
                registry:
                    self.registry
            )
    }

    // MARK: Lifecycle

    public func start() {

        guard !running else {
            return
        }

        running = true

        IndustrialTelemetryLog.info(
            "Industrial telemetry engine started."
        )
    }

    public func stop() {

        running = false

        IndustrialTelemetryLog.info(
            "Industrial telemetry engine stopped."
        )
    }

    public func isRunning() -> Bool {
        running
    }

    // MARK: Registration

    public func registerSensor(
        _ sensor: SensorDefinition
    ) async {

        await registry.register(
            sensor
        )
    }

    // MARK: Ingestion

    public func ingest(
        _ sample: TelemetrySample
    ) async throws {

        guard running else {
            throw TelemetryError
                .processingFailure(
                    "Engine is not running."
                )
        }

        do {

            try await validator.validate(
                sample
            )

            try await buffer.append(
                sample
            )

            acceptedSamples += 1

            await stream.publish(
                sample
            )

        } catch {

            rejectedSamples += 1

            throw error
        }
    }

    public func ingest(
        _ samples: [TelemetrySample]
    ) async throws {

        for sample in samples {

            try await ingest(
                sample
            )
        }
    }

    // MARK: Flush

    public func flush()
        async throws
    {

        let samples =
            await buffer.pop(
                maximum:
                    configuration
                        .maximumBatchSize
            )

        guard !samples.isEmpty else {
            return
        }

        try await store.append(
            samples
        )

        processedBatches += 1
    }

    public func flushAll()
        async throws
    {

        while await buffer.count() > 0 {

            try await flush()
        }
    }

    // MARK: Queries

    public func query(
        sensorID: SensorID,
        from: Date,
        to: Date
    ) async throws
        -> [TelemetrySample]
    {

        try await store.query(
            sensorID:
                sensorID,
            from:
                from,
            to:
                to
        )
    }

    public func latest(
        sensorID: SensorID
    ) async throws
        -> TelemetrySample?
    {

        try await store.latest(
            sensorID:
                sensorID
        )
    }

    public func statistics(
        sensorID: SensorID,
        from: Date,
        to: Date
    ) async throws
        -> TelemetryStatistics
    {

        let samples =
            try await query(
                sensorID:
                    sensorID,
                from:
                    from,
                to:
                    to
            )

        return TelemetryStatisticsCalculator
            .calculate(
                samples
            )
    }

    // MARK: Diagnostics

    public func diagnostics()
        async -> TelemetryDiagnostics
    {

        TelemetryDiagnostics(
            running:
                running,
            sensorCount:
                await registry.count(),
            bufferedSamples:
                await buffer.count(),
            acceptedSamples:
                acceptedSamples,
            rejectedSamples:
                rejectedSamples,
            processedBatches:
                processedBatches
        )
    }
}

// MARK: - Diagnostics

public struct TelemetryDiagnostics:
    Sendable {

    public let running:
        Bool

    public let sensorCount:
        Int

    public let bufferedSamples:
        Int

    public let acceptedSamples:
        UInt64

    public let rejectedSamples:
        UInt64

    public let processedBatches:
        UInt64

    public init(
        running: Bool,
        sensorCount: Int,
        bufferedSamples: Int,
        acceptedSamples: UInt64,
        rejectedSamples: UInt64,
        processedBatches: UInt64
    ) {

        self.running = running
        self.sensorCount = sensorCount
        self.bufferedSamples =
            bufferedSamples
        self.acceptedSamples =
            acceptedSamples
        self.rejectedSamples =
            rejectedSamples
        self.processedBatches =
            processedBatches
    }
}

// MARK: - Industrial Device

public struct IndustrialDevice:
    Codable,
    Sendable {

    public let id:
        DeviceID

    public let name:
        String

    public let manufacturer:
        String

    public let model:
        String

    public init(
        id: DeviceID,
        name: String,
        manufacturer: String,
        model: String
    ) {

        self.id = id
        self.name = name
        self.manufacturer =
            manufacturer
        self.model = model
    }
}

// MARK: - Device Registry

public actor IndustrialDeviceRegistry {

    private var devices:
        [DeviceID: IndustrialDevice]
        = [:]

    public init() {}

    public func register(
        _ device: IndustrialDevice
    ) {

        devices[device.id] =
            device
    }

    public func device(
        id: DeviceID
    ) -> IndustrialDevice? {

        devices[id]
    }

    public func all()
        -> [IndustrialDevice]
    {

        Array(devices.values)
    }
}

// MARK: - Sensor Health

public enum SensorHealth:
    String,
    Codable,
    Sendable {

    case unknown
    case healthy
    case stale
    case degraded
    case failed
}

public struct SensorHealthReport:
    Codable,
    Sendable {

    public let sensorID:
        SensorID

    public let health:
        SensorHealth

    public let lastSample:
        Date?

    public let sampleAge:
        TimeInterval?

    public let quality:
        TelemetryQuality

    public init(
        sensorID: SensorID,
        health: SensorHealth,
        lastSample: Date?,
        sampleAge: TimeInterval?,
        quality: TelemetryQuality
    ) {

        self.sensorID = sensorID
        self.health = health
        self.lastSample = lastSample
        self.sampleAge = sampleAge
        self.quality = quality
    }
}

// MARK: - Sensor Health Monitor

public actor SensorHealthMonitor {

    private let store:
        any TelemetryStore

    private let staleAfter:
        TimeInterval

    public init(
        store:
            any TelemetryStore,
        staleAfter:
            TimeInterval = 30
    ) {

        self.store =
            store

        self.staleAfter =
            max(0, staleAfter)
    }

    public func health(
        sensorID:
            SensorID
    ) async throws
        -> SensorHealthReport
    {

        guard let latest =
                try await store.latest(
                    sensorID:
                        sensorID
                )
        else {

            return SensorHealthReport(
                sensorID:
                    sensorID,
                health:
                    .unknown,
                lastSample:
                    nil,
                sampleAge:
                    nil,
                quality:
                    .unknown
            )
        }

        let age =
            Date()
                .timeIntervalSince(
                    latest.timestamp
                )

        let status:
            SensorHealth

        if latest.quality == .bad {

            status = .failed

        } else if age >
                    staleAfter {

            status = .stale

        } else if latest.quality ==
                    .uncertain {

            status = .degraded

        } else {

            status = .healthy
        }

        return SensorHealthReport(
            sensorID:
                sensorID,
            health:
                status,
            lastSample:
                latest.timestamp,
            sampleAge:
                age,
            quality:
                latest.quality
        )
    }
}

// MARK: - Example Industrial Configuration

public enum IndustrialTelemetryExample {

    public static func makeEngine()
        async -> IndustrialTelemetryEngine
    {

        let engine =
            IndustrialTelemetryEngine(
                configuration:
                    IndustrialTelemetryConfiguration(
                        bufferCapacity:
                            250_000,
                        maximumBatchSize:
                            2_000,
                        validation:
                            .init(
                                maximumFutureSkew:
                                    5,
                                maximumPastAge:
                                    172_800
                            ),
                        downsampleBucket:
                            1
                    )
            )

        await engine.registerSensor(
            SensorDefinition(
                id:
                    SensorID(
                        "plant.temperature.001"
                    ),
                deviceID:
                    DeviceID(
                        "plant.boiler.001"
                    ),
                name:
                    "Boiler Temperature",
                kind:
                    .temperature,
                unit:
                    "°C",
                minimumValue:
                    -40,
                maximumValue:
                    1_000
            )
        )

        await engine.registerSensor(
            SensorDefinition(
                id:
                    SensorID(
                        "plant.pressure.001"
                    ),
                deviceID:
                    DeviceID(
                        "plant.boiler.001"
                    ),
                name:
                    "Boiler Pressure",
                kind:
                    .pressure,
                unit:
                    "bar",
                minimumValue:
                    0,
                maximumValue:
                    500
            )
        )

        return engine
    }

    public static func run()
        async throws {

        let engine =
            await makeEngine()

        await engine.start()

        let temperature =
            TelemetrySample(
                sensorID:
                    SensorID(
                        "plant.temperature.001"
                    ),
                value:
                    284.7
            )

        try await engine.ingest(
            temperature
        )

        try await engine.flushAll()

        let latest =
            try await engine.latest(
                sensorID:
                    SensorID(
                        "plant.temperature.001"
                    )
            )

        print(
            "Latest:",
            latest?.value ?? 0
        )

        let diagnostics =
            await engine.diagnostics()

        print(
            "Sensors:",
            diagnostics.sensorCount
        )

        print(
            "Samples:",
            diagnostics.acceptedSamples
        )
    }
}





//
// HighRateTelemetryIngestor.swift
//

import Foundation

public actor HighRateTelemetryIngestor {

    private let engine:
        IndustrialTelemetryEngine

    private let processing:
        IndustrialTelemetryProcessingEngine

    private var pending:
        [TelemetrySample] = []

    private let maximumPending:
        Int

    public init(
        engine:
            IndustrialTelemetryEngine,
        processing:
            IndustrialTelemetryProcessingEngine,
        maximumPending:
            Int = 50_000
    ) {

        self.engine = engine
        self.processing = processing
        self.maximumPending =
            max(1, maximumPending)
    }

    public func ingest(
        _ sample: TelemetrySample
    ) async throws {

        guard pending.count <
                maximumPending
        else {

            throw TelemetryError
                .bufferFull
        }

        pending.append(
            sample
        )

        _ =
            try await processing.process(
                sample
            )

        if pending.count >= 1_000 {

            try await flush()
        }
    }

    public func flush()
        async throws
    {

        guard !pending.isEmpty else {
            return
        }

        let samples =
            pending

        pending.removeAll(
            keepingCapacity: true
        )

        try await engine.ingest(
            samples
        )

        try await engine.flushAll()
    }

    public func pendingCount()
        -> Int
    {
        pending.count
    }
}






//
//  SwiftIndustrialRuntime.swift
//
//  Swift Industrial Runtime
//  Production-oriented industrial execution framework
//
//  Swift 6
//

import Foundation
import os

// MARK: - Logging

enum IndustrialRuntimeLog {
    static let runtime = Logger(
        subsystem: "com.example.industrial-runtime",
        category: "runtime"
    )

    static let scheduler = Logger(
        subsystem: "com.example.industrial-runtime",
        category: "scheduler"
    )

    static let worker = Logger(
        subsystem: "com.example.industrial-runtime",
        category: "worker"
    )

    static let state = Logger(
        subsystem: "com.example.industrial-runtime",
        category: "state"
    )

    static let resource = Logger(
        subsystem: "com.example.industrial-runtime",
        category: "resource"
    )

    static let health = Logger(
        subsystem: "com.example.industrial-runtime",
        category: "health"
    )
}

// MARK: - Errors

enum IndustrialRuntimeError: Error, Sendable {
    case runtimeNotStarted
    case runtimeAlreadyStarted
    case runtimeStopping

    case taskNotFound
    case taskAlreadyRegistered
    case taskAlreadyRunning
    case taskCancelled
    case taskTimedOut

    case invalidDeadline
    case invalidConfiguration

    case resourceUnavailable(String)
    case resourceAlreadyOwned(String)

    case invalidStateTransition
    case stateMachineStopped

    case workerPoolStopped
    case workerPoolSaturated

    case retryLimitExceeded

    case shutdownTimeout
}

// MARK: - IDs

struct RuntimeTaskID: Hashable, Codable, Sendable {
    let rawValue: UUID

    init() {
        self.rawValue = UUID()
    }

    init(rawValue: UUID) {
        self.rawValue = rawValue
    }
}

struct WorkerID: Hashable, Codable, Sendable {
    let rawValue: UUID

    init() {
        self.rawValue = UUID()
    }
}

struct ResourceID: Hashable, Codable, Sendable {
    let rawValue: String

    init(_ rawValue: String) {
        self.rawValue = rawValue
    }
}

struct StateMachineID: Hashable, Codable, Sendable {
    let rawValue: UUID

    init() {
        self.rawValue = UUID()
    }
}

// MARK: - Runtime State

enum IndustrialRuntimeState: String, Codable, Sendable {
    case created
    case starting
    case running
    case degraded
    case stopping
    case stopped
    case failed
}

// MARK: - Task Priority

enum IndustrialTaskPriority: Int, Codable, Comparable, Sendable {
    case background = 0
    case low = 25
    case normal = 50
    case high = 75
    case critical = 100

    static func < (
        lhs: IndustrialTaskPriority,
        rhs: IndustrialTaskPriority
    ) -> Bool {
        lhs.rawValue < rhs.rawValue
    }
}

// MARK: - Execution Classes

enum IndustrialExecutionClass: String, Codable, Sendable {
    case bestEffort
    case scheduled
    case deadline
    case realtime
    case safetyCritical
}

// MARK: - Task State

enum RuntimeTaskState: String, Codable, Sendable {
    case registered
    case queued
    case running
    case completed
    case failed
    case cancelled
    case timedOut
    case retrying
}

// MARK: - Task Result

enum RuntimeTaskResult: Sendable {
    case success
    case failure(String)
    case cancelled
}

// MARK: - Runtime Clock

protocol IndustrialRuntimeClock: Sendable {
    func now() -> ContinuousClock.Instant
}

struct SystemIndustrialRuntimeClock: IndustrialRuntimeClock {
    private let clock = ContinuousClock()

    func now() -> ContinuousClock.Instant {
        clock.now
    }
}

// MARK: - Retry Policy

struct IndustrialRetryPolicy: Codable, Sendable {

    let maximumAttempts: Int
    let initialDelay: Duration
    let maximumDelay: Duration
    let multiplier: Double

    init(
        maximumAttempts: Int = 3,
        initialDelay: Duration = .milliseconds(250),
        maximumDelay: Duration = .seconds(30),
        multiplier: Double = 2.0
    ) {
        self.maximumAttempts = max(1, maximumAttempts)
        self.initialDelay = initialDelay
        self.maximumDelay = maximumDelay
        self.multiplier = max(1.0, multiplier)
    }

    func delay(forAttempt attempt: Int) -> Duration {

        guard attempt > 1 else {
            return initialDelay
        }

        var delay = initialDelay

        for _ in 2..<attempt {
            delay = scaled(
                delay,
                multiplier: multiplier
            )

            if delay >= maximumDelay {
                return maximumDelay
            }
        }

        return minDuration(delay, maximumDelay)
    }

    private func scaled(
        _ duration: Duration,
        multiplier: Double
    ) -> Duration {

        let components = duration.components

        let seconds = Double(components.seconds)
        let attoseconds = Double(components.attoseconds) / 1e18

        let total = (seconds + attoseconds) * multiplier

        let wholeSeconds = Int64(total)
        let fractional = total - Double(wholeSeconds)

        let nanos = Int64(fractional * 1_000_000_000)

        return .seconds(
            wholeSeconds
        ) + .nanoseconds(
            nanos
        )
    }

    private func minDuration(
        _ lhs: Duration,
        _ rhs: Duration
    ) -> Duration {

        let l = lhs.components
        let r = rhs.components

        if l.seconds < r.seconds {
            return lhs
        }

        if l.seconds > r.seconds {
            return rhs
        }

        return l.attoseconds <= r.attoseconds ? lhs : rhs
    }
}

// MARK: - Runtime Task Definition

struct IndustrialTaskDefinition: Sendable {

    let id: RuntimeTaskID
    let name: String

    let priority: IndustrialTaskPriority
    let executionClass: IndustrialExecutionClass

    let deadline: ContinuousClock.Instant?
    let timeout: Duration?

    let retryPolicy: IndustrialRetryPolicy

    let requiresExclusiveExecution: Bool

    let resourceRequirements: Set<ResourceID>

    init(
        id: RuntimeTaskID = RuntimeTaskID(),
        name: String,
        priority: IndustrialTaskPriority = .normal,
        executionClass: IndustrialExecutionClass = .bestEffort,
        deadline: ContinuousClock.Instant? = nil,
        timeout: Duration? = nil,
        retryPolicy: IndustrialRetryPolicy = IndustrialRetryPolicy(),
        requiresExclusiveExecution: Bool = false,
        resourceRequirements: Set<ResourceID> = []
    ) {
        self.id = id
        self.name = name
        self.priority = priority
        self.executionClass = executionClass
        self.deadline = deadline
        self.timeout = timeout
        self.retryPolicy = retryPolicy
        self.requiresExclusiveExecution = requiresExclusiveExecution
        self.resourceRequirements = resourceRequirements
    }
}

// MARK: - Task Context

struct IndustrialTaskContext: Sendable {

    let taskID: RuntimeTaskID
    let workerID: WorkerID

    let attempt: Int

    let startedAt: ContinuousClock.Instant

    let cancellation: TaskCancellationSource

    func checkCancellation() throws {
        try cancellation.checkCancellation()
    }
}

// MARK: - Cancellation Source

final class TaskCancellationSource: @unchecked Sendable {

    private let lock = NSLock()
    private var cancelled = false

    func cancel() {
        lock.lock()
        cancelled = true
        lock.unlock()
    }

    var isCancelled: Bool {
        lock.lock()
        defer { lock.unlock() }

        return cancelled
    }

    func checkCancellation() throws {
        if isCancelled {
            throw IndustrialRuntimeError.taskCancelled
        }

        try Task.checkCancellation()
    }
}

// MARK: - Task Handler

typealias IndustrialTaskHandler =
    @Sendable (IndustrialTaskContext) async throws -> Void

// MARK: - Runtime Task

struct RuntimeTask: Sendable {

    let definition: IndustrialTaskDefinition

    let handler: IndustrialTaskHandler

    var state: RuntimeTaskState

    var attempt: Int

    var queuedAt: ContinuousClock.Instant?

    var startedAt: ContinuousClock.Instant?

    var completedAt: ContinuousClock.Instant?

    var lastError: String?

    let cancellationSource: TaskCancellationSource
}

// MARK: - Scheduler Entry

struct SchedulerEntry: Sendable {

    let taskID: RuntimeTaskID

    let priority: IndustrialTaskPriority

    let queuedAt: ContinuousClock.Instant

    let deadline: ContinuousClock.Instant?

    let executionClass: IndustrialExecutionClass
}

// MARK: - Scheduler

actor IndustrialTaskScheduler {

    private var tasks: [RuntimeTaskID: RuntimeTask] = [:]

    private var queue: [SchedulerEntry] = []

    private let clock: any IndustrialRuntimeClock

    init(
        clock: any IndustrialRuntimeClock = SystemIndustrialRuntimeClock()
    ) {
        self.clock = clock
    }

    // MARK: Registration

    func register(
        _ definition: IndustrialTaskDefinition,
        handler: @escaping IndustrialTaskHandler
    ) throws {

        guard tasks[definition.id] == nil else {
            throw IndustrialRuntimeError.taskAlreadyRegistered
        }

        let task = RuntimeTask(
            definition: definition,
            handler: handler,
            state: .registered,
            attempt: 0,
            queuedAt: nil,
            startedAt: nil,
            completedAt: nil,
            lastError: nil,
            cancellationSource: TaskCancellationSource()
        )

        tasks[definition.id] = task

        IndustrialRuntimeLog.scheduler.debug(
            "Registered task \(definition.name, privacy: .public)"
        )
    }

    // MARK: Queue

    func enqueue(
        _ id: RuntimeTaskID
    ) throws {

        guard var task = tasks[id] else {
            throw IndustrialRuntimeError.taskNotFound
        }

        guard task.state == .registered ||
              task.state == .retrying ||
              task.state == .failed
        else {
            throw IndustrialRuntimeError.taskAlreadyRunning
        }

        let now = clock.now()

        task.state = .queued
        task.queuedAt = now
        task.lastError = nil

        tasks[id] = task

        queue.append(
            SchedulerEntry(
                taskID: id,
                priority: task.definition.priority,
                queuedAt: now,
                deadline: task.definition.deadline,
                executionClass: task.definition.executionClass
            )
        )

        reorderQueue()
    }

    // MARK: Cancel

    func cancel(
        _ id: RuntimeTaskID
    ) throws {

        guard var task = tasks[id] else {
            throw IndustrialRuntimeError.taskNotFound
        }

        task.cancellationSource.cancel()

        if task.state == .queued ||
           task.state == .registered ||
           task.state == .retrying {

            task.state = .cancelled
            tasks[id] = task

            queue.removeAll {
                $0.taskID == id
            }
        }
    }

    // MARK: Dequeue

    func nextTask() -> RuntimeTask? {

        while !queue.isEmpty {

            let entry = queue.removeFirst()

            guard var task = tasks[entry.taskID] else {
                continue
            }

            if task.cancellationSource.isCancelled {
                task.state = .cancelled
                tasks[entry.taskID] = task
                continue
            }

            if let deadline = task.definition.deadline,
               clock.now() >= deadline {

                task.state = .timedOut
                tasks[entry.taskID] = task
                continue
            }

            task.state = .running
            task.attempt += 1
            task.startedAt = clock.now()

            tasks[entry.taskID] = task

            return task
        }

        return nil
    }

    // MARK: Completion

    func complete(
        _ id: RuntimeTaskID
    ) throws {

        guard var task = tasks[id] else {
            throw IndustrialRuntimeError.taskNotFound
        }

        task.state = .completed
        task.completedAt = clock.now()

        tasks[id] = task
    }

    // MARK: Failure

    func fail(
        _ id: RuntimeTaskID,
        error: Error
    ) throws -> Bool {

        guard var task = tasks[id] else {
            throw IndustrialRuntimeError.taskNotFound
        }

        task.lastError = String(describing: error)

        if task.attempt < task.definition.retryPolicy.maximumAttempts {

            task.state = .retrying
            tasks[id] = task

            return true
        }

        task.state = .failed
        task.completedAt = clock.now()

        tasks[id] = task

        return false
    }

    // MARK: Inspection

    func state(
        for id: RuntimeTaskID
    ) -> RuntimeTaskState? {
        tasks[id]?.state
    }

    func task(
        for id: RuntimeTaskID
    ) -> RuntimeTask? {
        tasks[id]
    }

    func pendingCount() -> Int {
        queue.count
    }

    func allTasks() -> [RuntimeTask] {
        Array(tasks.values)
    }

    // MARK: Queue Ordering

    private func reorderQueue() {

        queue.sort { lhs, rhs in

            if lhs.priority != rhs.priority {
                return lhs.priority > rhs.priority
            }

            if lhs.executionClass != rhs.executionClass {

                let l = executionRank(lhs.executionClass)
                let r = executionRank(rhs.executionClass)

                return l > r
            }

            switch (lhs.deadline, rhs.deadline) {

            case let (l?, r?):
                if l != r {
                    return l < r
                }

            case (_?, nil):
                return true

            case (nil, _?):
                return false

            default:
                break
            }

            return lhs.queuedAt < rhs.queuedAt
        }
    }

    private func executionRank(
        _ value: IndustrialExecutionClass
    ) -> Int {

        switch value {
        case .bestEffort:
            return 0
        case .scheduled:
            return 1
        case .deadline:
            return 2
        case .realtime:
            return 3
        case .safetyCritical:
            return 4
        }
    }
}

// MARK: - Resource Ownership

struct ResourceLease: Sendable {

    let resourceID: ResourceID
    let taskID: RuntimeTaskID
    let acquiredAt: ContinuousClock.Instant
}

// MARK: - Resource Manager

actor IndustrialResourceManager {

    private var owners: [ResourceID: ResourceLease] = [:]

    private let clock: any IndustrialRuntimeClock

    init(
        clock: any IndustrialRuntimeClock = SystemIndustrialRuntimeClock()
    ) {
        self.clock = clock
    }

    func acquire(
        resources: Set<ResourceID>,
        for taskID: RuntimeTaskID
    ) throws {

        for resource in resources {

            if let owner = owners[resource],
               owner.taskID != taskID {

                throw IndustrialRuntimeError.resourceAlreadyOwned(
                    resource.rawValue
                )
            }
        }

        for resource in resources {

            owners[resource] = ResourceLease(
                resourceID: resource,
                taskID: taskID,
                acquiredAt: clock.now()
            )
        }

        IndustrialRuntimeLog.resource.debug(
            "Acquired \(resources.count) resources"
        )
    }

    func release(
        resources: Set<ResourceID>,
        for taskID: RuntimeTaskID
    ) {

        for resource in resources {

            guard let owner = owners[resource],
                  owner.taskID == taskID
            else {
                continue
            }

            owners.removeValue(
                forKey: resource
            )
        }
    }

    func isAvailable(
        _ resource: ResourceID
    ) -> Bool {
        owners[resource] == nil
    }

    func currentOwners() -> [ResourceID: RuntimeTaskID] {

        Dictionary(
            uniqueKeysWithValues:
                owners.map {
                    ($0.key, $0.value.taskID)
                }
        )
    }

    func releaseAll(
        for taskID: RuntimeTaskID
    ) {

        owners = owners.filter {
            $0.value.taskID != taskID
        }
    }
}

// MARK: - Worker

actor IndustrialWorker {

    let id: WorkerID

    private(set) var running = false

    init(
        id: WorkerID = WorkerID()
    ) {
        self.id = id
    }

    func start() {
        running = true
    }

    func stop() {
        running = false
    }
}

// MARK: - Worker Pool

actor IndustrialWorkerPool {

    private var workers: [WorkerID: IndustrialWorker] = [:]

    private var activeTasks: [WorkerID: RuntimeTaskID] = [:]

    private let maximumWorkers: Int

    init(
        maximumWorkers: Int
    ) {
        self.maximumWorkers = max(
            1,
            maximumWorkers
        )
    }

    func start() async {

        for _ in 0..<maximumWorkers {

            let worker = IndustrialWorker()

            await worker.start()

            workers[await worker.id] = worker
        }
    }

    func stop() async {

        for worker in workers.values {
            await worker.stop()
        }

        workers.removeAll()
        activeTasks.removeAll()
    }

    func acquireWorker() async -> WorkerID? {

        for (id, worker) in workers {

            guard await worker.running else {
                continue
            }

            if activeTasks[id] == nil {
                return id
            }
        }

        return nil
    }

    func assign(
        workerID: WorkerID,
        taskID: RuntimeTaskID
    ) {

        activeTasks[workerID] = taskID
    }

    func release(
        workerID: WorkerID
    ) {

        activeTasks.removeValue(
            forKey: workerID
        )
    }

    func activeCount() -> Int {
        activeTasks.count
    }

    func capacity() -> Int {
        workers.count
    }
}

// MARK: - Runtime Metrics

struct RuntimeMetrics: Sendable {

    let timestamp: ContinuousClock.Instant

    let registeredTasks: Int
    let queuedTasks: Int
    let activeTasks: Int

    let completedTasks: Int
    let failedTasks: Int
    let cancelledTasks: Int
    let timedOutTasks: Int

    let totalExecutions: Int

    let averageExecutionTime: Duration
}

// MARK: - Metrics Store

actor IndustrialRuntimeMetricsStore {

    private var completed = 0
    private var failed = 0
    private var cancelled = 0
    private var timedOut = 0
    private var executions = 0

    private var totalExecutionNanoseconds: UInt64 = 0

    func recordExecution(
        duration: Duration
    ) {

        executions += 1

        let components = duration.components

        let nanos =
            UInt64(max(0, components.seconds)) * 1_000_000_000
            + UInt64(max(0, components.attoseconds / 1_000_000_000))

        totalExecutionNanoseconds += nanos
    }

    func recordCompletion() {
        completed += 1
    }

    func recordFailure() {
        failed += 1
    }

    func recordCancellation() {
        cancelled += 1
    }

    func recordTimeout() {
        timedOut += 1
    }

    func snapshot(
        timestamp: ContinuousClock.Instant,
        registered: Int,
        queued: Int,
        active: Int
    ) -> RuntimeMetrics {

        let average: Duration

        if executions == 0 {
            average = .zero
        } else {
            average = .nanoseconds(
                Int64(
                    totalExecutionNanoseconds /
                    UInt64(executions)
                )
            )
        }

        return RuntimeMetrics(
            timestamp: timestamp,
            registeredTasks: registered,
            queuedTasks: queued,
            activeTasks: active,
            completedTasks: completed,
            failedTasks: failed,
            cancelledTasks: cancelled,
            timedOutTasks: timedOut,
            totalExecutions: executions,
            averageExecutionTime: average
        )
    }
}

// MARK: - Health

enum RuntimeHealthState: String, Sendable {

    case healthy
    case degraded
    case critical
}

struct RuntimeHealthReport: Sendable {

    let state: RuntimeHealthState

    let timestamp: ContinuousClock.Instant

    let workerCapacity: Int
    let activeWorkers: Int
    let queuedTasks: Int

    let resourceCount: Int

    let message: String
}

// MARK: - Health Monitor

actor IndustrialRuntimeHealthMonitor {

    func evaluate(
        runtimeState: IndustrialRuntimeState,
        workerCapacity: Int,
        activeWorkers: Int,
        queuedTasks: Int,
        resources: Int,
        timestamp: ContinuousClock.Instant
    ) -> RuntimeHealthReport {

        if runtimeState == .failed ||
           runtimeState == .stopped {

            return RuntimeHealthReport(
                state: .critical,
                timestamp: timestamp,
                workerCapacity: workerCapacity,
                activeWorkers: activeWorkers,
                queuedTasks: queuedTasks,
                resourceCount: resources,
                message: "Runtime is not operational."
            )
        }

        if workerCapacity == 0 {

            return RuntimeHealthReport(
                state: .critical,
                timestamp: timestamp,
                workerCapacity: workerCapacity,
                activeWorkers: activeWorkers,
                queuedTasks: queuedTasks,
                resourceCount: resources,
                message: "No workers are available."
            )
        }

        if queuedTasks > workerCapacity * 10 {

            return RuntimeHealthReport(
                state: .degraded,
                timestamp: timestamp,
                workerCapacity: workerCapacity,
                activeWorkers: activeWorkers,
                queuedTasks: queuedTasks,
                resourceCount: resources,
                message: "Task queue is experiencing sustained pressure."
            )
        }

        return RuntimeHealthReport(
            state: .healthy,
            timestamp: timestamp,
            workerCapacity: workerCapacity,
            activeWorkers: activeWorkers,
            queuedTasks: queuedTasks,
            resourceCount: resources,
            message: "Runtime operating normally."
        )
    }
}

// MARK: - Runtime Configuration

struct IndustrialRuntimeConfiguration: Sendable {

    let maximumWorkers: Int

    let schedulerPollInterval: Duration

    let shutdownTimeout: Duration

    let healthCheckInterval: Duration

    let enableAutomaticRetry: Bool

    init(
        maximumWorkers: Int = 4,
        schedulerPollInterval: Duration = .milliseconds(10),
        shutdownTimeout: Duration = .seconds(5),
        healthCheckInterval: Duration = .seconds(2),
        enableAutomaticRetry: Bool = true
    ) {

        self.maximumWorkers = max(
            1,
            maximumWorkers
        )

        self.schedulerPollInterval =
            schedulerPollInterval

        self.shutdownTimeout =
            shutdownTimeout

        self.healthCheckInterval =
            healthCheckInterval

        self.enableAutomaticRetry =
            enableAutomaticRetry
    }
}

// MARK: - Runtime Supervisor

actor IndustrialRuntimeSupervisor {

    private(set) var state: IndustrialRuntimeState = .created

    private let configuration: IndustrialRuntimeConfiguration

    private let scheduler: IndustrialTaskScheduler
    private let resources: IndustrialResourceManager
    private let workerPool: IndustrialWorkerPool
    private let metrics: IndustrialRuntimeMetricsStore
    private let health: IndustrialRuntimeHealthMonitor

    private let clock: any IndustrialRuntimeClock

    private var executionTask: Task<Void, Never>?
    private var healthTask: Task<Void, Never>?

    init(
        configuration: IndustrialRuntimeConfiguration =
            IndustrialRuntimeConfiguration(),
        clock: any IndustrialRuntimeClock =
            SystemIndustrialRuntimeClock()
    ) {

        self.configuration = configuration
        self.clock = clock

        self.scheduler = IndustrialTaskScheduler(
            clock: clock
        )

        self.resources = IndustrialResourceManager(
            clock: clock
        )

        self.workerPool = IndustrialWorkerPool(
            maximumWorkers: configuration.maximumWorkers
        )

        self.metrics = IndustrialRuntimeMetricsStore()
        self.health = IndustrialRuntimeHealthMonitor()
    }

    // MARK: Start

    func start() async throws {

        guard state == .created ||
              state == .stopped
        else {
            throw IndustrialRuntimeError.runtimeAlreadyStarted
        }

        state = .starting

        IndustrialRuntimeLog.runtime.info(
            "Industrial runtime starting"
        )

        await workerPool.start()

        state = .running

        executionTask = Task { [weak self] in

            guard let self else {
                return
            }

            await self.executionLoop()
        }

        healthTask = Task { [weak self] in

            guard let self else {
                return
            }

            await self.healthLoop()
        }

        IndustrialRuntimeLog.runtime.info(
            "Industrial runtime started"
        )
    }

    // MARK: Stop

    func stop() async throws {

        guard state == .running ||
              state == .degraded
        else {
            return
        }

        state = .stopping

        executionTask?.cancel()
        healthTask?.cancel()

        executionTask = nil
        healthTask = nil

        let tasks = await scheduler.allTasks()

        for task in tasks {

            if task.state == .running ||
               task.state == .queued {

                task.cancellationSource.cancel()

                await resources.releaseAll(
                    for: task.definition.id
                )
            }
        }

        await workerPool.stop()

        state = .stopped

        IndustrialRuntimeLog.runtime.info(
            "Industrial runtime stopped"
        )
    }

    // MARK: Task Registration

    func register(
        _ definition: IndustrialTaskDefinition,
        handler: @escaping IndustrialTaskHandler
    ) async throws {

        guard state == .running ||
              state == .starting
        else {
            throw IndustrialRuntimeError.runtimeNotStarted
        }

        try await scheduler.register(
            definition,
            handler: handler
        )
    }

    // MARK: Submit

    func submit(
        _ id: RuntimeTaskID
    ) async throws {

        guard state == .running ||
              state == .degraded
        else {
            throw IndustrialRuntimeError.runtimeNotStarted
        }

        try await scheduler.enqueue(id)
    }

    // MARK: Cancel

    func cancel(
        _ id: RuntimeTaskID
    ) async throws {

        try await scheduler.cancel(id)

        await resources.releaseAll(
            for: id
        )
    }

    // MARK: Execution Loop

    private func executionLoop() async {

        while !Task.isCancelled {

            guard state == .running ||
                  state == .degraded
            else {
                return
            }

            guard let workerID =
                    await workerPool.acquireWorker()
            else {

                do {
                    try await Task.sleep(
                        for: configuration.schedulerPollInterval
                    )
                } catch {
                    return
                }

                continue
            }

            guard let task =
                    await scheduler.nextTask()
            else {

                do {
                    try await Task.sleep(
                        for: configuration.schedulerPollInterval
                    )
                } catch {
                    return
                }

                continue
            }

            await workerPool.assign(
                workerID: workerID,
                taskID: task.definition.id
            )

            await execute(
                task,
                workerID: workerID
            )

            await workerPool.release(
                workerID: workerID
            )
        }
    }

    // MARK: Execute

    private func execute(
        _ task: RuntimeTask,
        workerID: WorkerID
    ) async {

        let taskID = task.definition.id

        do {

            try await resources.acquire(
                resources: task.definition.resourceRequirements,
                for: taskID
            )

        } catch {

            _ = try? await scheduler.fail(
                taskID,
                error: error
            )

            await workerPool.release(
                workerID: workerID
            )

            return
        }

        let started = clock.now()

        let context = IndustrialTaskContext(
            taskID: taskID,
            workerID: workerID,
            attempt: task.attempt,
            startedAt: started,
            cancellation: task.cancellationSource
        )

        do {

            if let timeout = task.definition.timeout {

                try await withThrowingTaskGroup(
                    of: Void.self
                ) { group in

                    group.addTask {
                        try await task.handler(context)
                    }

                    group.addTask {

                        try await Task.sleep(
                            for: timeout
                        )

                        throw IndustrialRuntimeError.taskTimedOut
                    }

                    guard let result =
                            try await group.next()
                    else {
                        throw IndustrialRuntimeError.taskTimedOut
                    }

                    group.cancelAll()

                    return result
                }

            } else {

                try await task.handler(context)
            }

            let finished = clock.now()

            await metrics.recordExecution(
                duration: finished - started
            )

            try await scheduler.complete(
                taskID
            )

            await metrics.recordCompletion()

        } catch is CancellationError {

            await metrics.recordCancellation()

            _ = try? await scheduler.cancel(
                taskID
            )

        } catch IndustrialRuntimeError.taskTimedOut {

            await metrics.recordTimeout()

            _ = try? await scheduler.fail(
                taskID,
                error: IndustrialRuntimeError.taskTimedOut
            )

        } catch {

            await metrics.recordFailure()

            let shouldRetry =
                (try? await scheduler.fail(
                    taskID,
                    error: error
                )) ?? false

            if shouldRetry &&
               configuration.enableAutomaticRetry {

                if let updated =
                    await scheduler.task(for: taskID) {

                    let delay =
                        updated.definition.retryPolicy.delay(
                            forAttempt: updated.attempt + 1
                        )

                    let schedulerReference = scheduler

                    Task {

                        do {

                            try await Task.sleep(
                                for: delay
                            )

                            try await schedulerReference.enqueue(
                                taskID
                            )

                        } catch {

                            IndustrialRuntimeLog.scheduler.error(
                                "Retry scheduling failed"
                            )
                        }
                    }
                }
            }
        }

        await resources.release(
            resources: task.definition.resourceRequirements,
            for: taskID
        )
    }

    // MARK: Health Loop

    private func healthLoop() async {

        while !Task.isCancelled {

            let currentState = state

            let workers =
                await workerPool.capacity()

            let active =
                await workerPool.activeCount()

            let queued =
                await scheduler.pendingCount()

            let owners =
                await resources.currentOwners()

            let report =
                await health.evaluate(
                    runtimeState: currentState,
                    workerCapacity: workers,
                    activeWorkers: active,
                    queuedTasks: queued,
                    resources: owners.count,
                    timestamp: clock.now()
                )

            switch report.state {

            case .healthy:
                if state == .degraded {
                    state = .running
                }

            case .degraded:
                if state == .running {
                    state = .degraded
                }

            case .critical:
                if state == .running ||
                   state == .degraded {
                    state = .degraded
                }
            }

            IndustrialRuntimeLog.health.debug(
                "Runtime health: \(report.state.rawValue, privacy: .public)"
            )

            do {

                try await Task.sleep(
                    for: configuration.healthCheckInterval
                )

            } catch {
                return
            }
        }
    }

    // MARK: Metrics

    func metricsSnapshot() async -> RuntimeMetrics {

        await metrics.snapshot(
            timestamp: clock.now(),
            registered: await scheduler.allTasks().count,
            queued: await scheduler.pendingCount(),
            active: await workerPool.activeCount()
        )
    }

    // MARK: Task Inspection

    func taskState(
        _ id: RuntimeTaskID
    ) async -> RuntimeTaskState? {

        await scheduler.state(
            for: id
        )
    }
}

// MARK: - State Machine

struct IndustrialStateTransition<State: Hashable & Sendable>: Sendable {

    let from: State
    let to: State

    init(
        from: State,
        to: State
    ) {
        self.from = from
        self.to = to
    }
}

struct IndustrialStateMachineDefinition<State: Hashable & Sendable>:
    Sendable
{

    let initialState: State

    let transitions:
        Set<IndustrialStateTransition<State>>

    init(
        initialState: State,
        transitions: Set<IndustrialStateTransition<State>>
    ) {

        self.initialState = initialState
        self.transitions = transitions
    }

    func canTransition(
        from: State,
        to: State
    ) -> Bool {

        transitions.contains {
            $0.from == from &&
            $0.to == to
        }
    }
}

// MARK: - Generic Industrial State Machine

actor IndustrialStateMachine<State: Hashable & Sendable> {

    let id: StateMachineID

    private let definition:
        IndustrialStateMachineDefinition<State>

    private(set) var currentState: State

    private(set) var transitionCount = 0

    init(
        id: StateMachineID = StateMachineID(),
        definition:
            IndustrialStateMachineDefinition<State>
    ) {

        self.id = id
        self.definition = definition
        self.currentState = definition.initialState
    }

    func transition(
        to newState: State
    ) throws {

        guard definition.canTransition(
            from: currentState,
            to: newState
        ) else {

            throw IndustrialRuntimeError.invalidStateTransition
        }

        currentState = newState
        transitionCount += 1

        IndustrialRuntimeLog.state.debug(
            "State transition executed"
        )
    }

    func canTransition(
        to newState: State
    ) -> Bool {

        definition.canTransition(
            from: currentState,
            to: newState
        )
    }
}

// MARK: - Machine Lifecycle

enum IndustrialMachineState: String, Sendable {

    case offline
    case initializing
    case ready
    case running
    case paused
    case stopping
    case faulted
    case emergencyStopped
}

enum IndustrialMachineEvent: Sendable {

    case initialize
    case initialized

    case start
    case pause
    case resume
    case stop

    case fault
    case clearFault

    case emergencyStop
    case resetEmergencyStop
}

// MARK: - Machine Controller

actor IndustrialMachineController {

    private let machine:
        IndustrialStateMachine<IndustrialMachineState>

    init() {

        let transitions: Set<
            IndustrialStateTransition<IndustrialMachineState>
        > = [

            .init(
                from: .offline,
                to: .initializing
            ),

            .init(
                from: .initializing,
                to: .ready
            ),

            .init(
                from: .ready,
                to: .running
            ),

            .init(
                from: .running,
                to: .paused
            ),

            .init(
                from: .paused,
                to: .running
            ),

            .init(
                from: .running,
                to: .stopping
            ),

            .init(
                from: .paused,
                to: .stopping
            ),

            .init(
                from: .stopping,
                to: .offline
            ),

            .init(
                from: .running,
                to: .faulted
            ),

            .init(
                from: .paused,
                to: .faulted
            ),

            .init(
                from: .faulted,
                to: .ready
            ),

            .init(
                from: .running,
                to: .emergencyStopped
            ),

            .init(
                from: .paused,
                to: .emergencyStopped
            ),

            .init(
                from: .ready,
                to: .emergencyStopped
            ),

            .init(
                from: .emergencyStopped,
                to: .offline
            )
        ]

        let definition =
            IndustrialStateMachineDefinition(
                initialState: .offline,
                transitions: transitions
            )

        self.machine =
            IndustrialStateMachine(
                definition: definition
            )
    }

    func handle(
        _ event: IndustrialMachineEvent
    ) throws {

        let target: IndustrialMachineState

        switch event {

        case .initialize:
            target = .initializing

        case .initialized:
            target = .ready

        case .start:
            target = .running

        case .pause:
            target = .paused

        case .resume:
            target = .running

        case .stop:
            target = .stopping

        case .fault:
            target = .faulted

        case .clearFault:
            target = .ready

        case .emergencyStop:
            target = .emergencyStopped

        case .resetEmergencyStop:
            target = .offline
        }

        try await machine.transition(
            to: target
        )
    }

    func state() async -> IndustrialMachineState {
        await machine.currentState
    }
}

// MARK: - Runtime Event

enum IndustrialRuntimeEvent: Sendable {

    case runtimeStarted
    case runtimeStopped

    case taskQueued(RuntimeTaskID)
    case taskStarted(RuntimeTaskID)
    case taskCompleted(RuntimeTaskID)
    case taskFailed(RuntimeTaskID)

    case resourceAcquired(ResourceID)
    case resourceReleased(ResourceID)

    case machineStateChanged(
        IndustrialMachineState
    )

    case healthChanged(
        RuntimeHealthState
    )
}

// MARK: - Runtime Event Bus

actor IndustrialRuntimeEventBus {

    typealias Subscriber =
        @Sendable (IndustrialRuntimeEvent) async -> Void

    private var subscribers:
        [UUID: Subscriber] = [:]

    func subscribe(
        _ subscriber: @escaping Subscriber
    ) -> UUID {

        let id = UUID()

        subscribers[id] = subscriber

        return id
    }

    func unsubscribe(
        _ id: UUID
    ) {

        subscribers.removeValue(
            forKey: id
        )
    }

    func publish(
        _ event: IndustrialRuntimeEvent
    ) async {

        let current =
            Array(subscribers.values)

        for subscriber in current {
            await subscriber(event)
        }
    }
}

// MARK: - Runtime Container

actor IndustrialRuntimeContainer {

    let runtime: IndustrialRuntimeSupervisor

    let events: IndustrialRuntimeEventBus

    let machineController:
        IndustrialMachineController

    init(
        configuration:
            IndustrialRuntimeConfiguration =
                IndustrialRuntimeConfiguration()
    ) {

        self.runtime =
            IndustrialRuntimeSupervisor(
                configuration: configuration
            )

        self.events =
            IndustrialRuntimeEventBus()

        self.machineController =
            IndustrialMachineController()
    }

    func start() async throws {

        try await runtime.start()

        await events.publish(
            .runtimeStarted
        )
    }

    func stop() async throws {

        try await runtime.stop()

        await events.publish(
            .runtimeStopped
        )
    }
}

// MARK: - Industrial Runtime API

@MainActor
final class SwiftIndustrialRuntime {

    private let container:
        IndustrialRuntimeContainer

    init(
        configuration:
            IndustrialRuntimeConfiguration =
                IndustrialRuntimeConfiguration()
    ) {

        self.container =
            IndustrialRuntimeContainer(
                configuration: configuration
            )
    }

    func start() async throws {
        try await container.start()
    }

    func stop() async throws {
        try await container.stop()
    }

    func register(
        _ definition: IndustrialTaskDefinition,
        handler: @escaping IndustrialTaskHandler
    ) async throws {

        try await container.runtime.register(
            definition,
            handler: handler
        )
    }

    func submit(
        _ taskID: RuntimeTaskID
    ) async throws {

        try await container.runtime.submit(
            taskID
        )

        await container.events.publish(
            .taskQueued(taskID)
        )
    }

    func cancel(
        _ taskID: RuntimeTaskID
    ) async throws {

        try await container.runtime.cancel(
            taskID
        )
    }

    func machineEvent(
        _ event: IndustrialMachineEvent
    ) async throws {

        try await container.machineController.handle(
            event
        )

        let state =
            await container.machineController.state()

        await container.events.publish(
            .machineStateChanged(state)
        )
    }

    func metrics() async -> RuntimeMetrics {
        await container.runtime.metricsSnapshot()
    }
}

// MARK: - Example Industrial Tasks

enum IndustrialExample {

    static func registerTasks(
        with runtime: SwiftIndustrialRuntime
    ) async throws {

        // ---------------------------------------------------------
        // Pump control task
        // ---------------------------------------------------------

        let pumpID =
            RuntimeTaskID()

        let pumpResource =
            ResourceID("pump.main")

        let pumpTask =
            IndustrialTaskDefinition(
                id: pumpID,
                name: "Main Pump Control",
                priority: .critical,
                executionClass: .realtime,
                timeout: .seconds(2),
                retryPolicy:
                    IndustrialRetryPolicy(
                        maximumAttempts: 2,
                        initialDelay: .milliseconds(100)
                    ),
                requiresExclusiveExecution: true,
                resourceRequirements: [
                    pumpResource
                ]
            )

        try await runtime.register(
            pumpTask
        ) { context in

            try context.checkCancellation()

            // Industrial control logic would execute here.

            try await Task.sleep(
                for: .milliseconds(50)
            )

            try context.checkCancellation()
        }

        // ---------------------------------------------------------
        // Telemetry processing task
        // ---------------------------------------------------------

        let telemetryID =
            RuntimeTaskID()

        let telemetryTask =
            IndustrialTaskDefinition(
                id: telemetryID,
                name: "Telemetry Processing",
                priority: .high,
                executionClass: .scheduled,
                timeout: .seconds(10)
            )

        try await runtime.register(
            telemetryTask
        ) { context in

            try context.checkCancellation()

            // Connect this to the #3 telemetry engine.

            try await Task.sleep(
                for: .milliseconds(100)
            )
        }

        // ---------------------------------------------------------
        // Maintenance task
        // ---------------------------------------------------------

        let maintenanceID =
            RuntimeTaskID()

        let maintenanceTask =
            IndustrialTaskDefinition(
                id: maintenanceID,
                name: "Predictive Maintenance",
                priority: .normal,
                executionClass: .bestEffort,
                timeout: .seconds(30)
            )

        try await runtime.register(
            maintenanceTask
        ) { context in

            try context.checkCancellation()

            // Maintenance calculations.

            try await Task.sleep(
                for: .seconds(1)
            )
        }

        try await runtime.submit(
            pumpID
        )

        try await runtime.submit(
            telemetryID
        )

        try await runtime.submit(
            maintenanceID
        )
    }
}



import Foundation

@main
struct IndustrialApplication {

    static func main() async {

        let configuration =
            IndustrialRuntimeConfiguration(
                maximumWorkers: 8,
                schedulerPollInterval: .milliseconds(5),
                shutdownTimeout: .seconds(10),
                healthCheckInterval: .seconds(1)
            )

        let runtime =
            await MainActor.run {
                SwiftIndustrialRuntime(
                    configuration: configuration
                )
            }

        do {

            try await runtime.start()

            try await IndustrialExample.registerTasks(
                with: runtime
            )

            try await runtime.machineEvent(
                .initialize
            )

            try await runtime.machineEvent(
                .initialized
            )

            try await runtime.machineEvent(
                .start
            )

            try await Task.sleep(
                for: .seconds(5)
            )

            let metrics =
                await runtime.metrics()

            print(
                """
                Industrial Runtime
                ------------------
                Registered: \(metrics.registeredTasks)
                Queued:     \(metrics.queuedTasks)
                Active:     \(metrics.activeTasks)
                Completed:  \(metrics.completedTasks)
                Failed:     \(metrics.failedTasks)
                Cancelled:  \(metrics.cancelledTasks)
                Executions: \(metrics.totalExecutions)
                """
            )

            try await runtime.stop()

        } catch {

            print(
                "Industrial runtime error: \(error)"
            )
        }
    }
}



//
//  SwiftQuant.swift
//
//  SwiftQuant — Industrial Quantitative Computing Engine
//
//  Swift 6
//

import Foundation
import os

// MARK: - Logging

enum SwiftQuantLog {

    static let engine = Logger(
        subsystem: "com.example.swiftquant",
        category: "engine"
    )

    static let market = Logger(
        subsystem: "com.example.swiftquant",
        category: "market"
    )

    static let risk = Logger(
        subsystem: "com.example.swiftquant",
        category: "risk"
    )

    static let pricing = Logger(
        subsystem: "com.example.swiftquant",
        category: "pricing"
    )

    static let optimisation = Logger(
        subsystem: "com.example.swiftquant",
        category: "optimisation"
    )
}

// MARK: - Errors

enum QuantError: Error, Sendable {

    case emptyData
    case invalidData
    case dimensionMismatch
    case singularMatrix

    case invalidProbability
    case invalidVariance
    case invalidVolatility
    case invalidRate

    case invalidPrice
    case invalidQuantity

    case instrumentNotFound

    case optimisationFailed
    case insufficientObservations

    case simulationFailed
}

// MARK: - IDs

struct QuantInstrumentID: Hashable, Codable, Sendable {

    let rawValue: String

    init(_ rawValue: String) {
        self.rawValue = rawValue
    }
}

struct MarketSeriesID: Hashable, Codable, Sendable {

    let rawValue: String

    init(_ rawValue: String) {
        self.rawValue = rawValue
    }
}

struct PortfolioID: Hashable, Codable, Sendable {

    let rawValue: UUID

    init() {
        rawValue = UUID()
    }
}

// MARK: - Scalar Utilities

enum QuantMath {

    static func mean(
        _ values: [Double]
    ) throws -> Double {

        guard !values.isEmpty else {
            throw QuantError.emptyData
        }

        return values.reduce(0, +) / Double(values.count)
    }

    static func variance(
        _ values: [Double],
        sample: Bool = true
    ) throws -> Double {

        guard values.count >= 2 else {
            throw QuantError.insufficientObservations
        }

        let average = try mean(values)

        let sum = values.reduce(0.0) {
            $0 + ($1 - average) * ($1 - average)
        }

        let denominator =
            sample
            ? Double(values.count - 1)
            : Double(values.count)

        return sum / denominator
    }

    static func standardDeviation(
        _ values: [Double],
        sample: Bool = true
    ) throws -> Double {

        sqrt(
            try variance(
                values,
                sample: sample
            )
        )
    }

    static func covariance(
        _ x: [Double],
        _ y: [Double]
    ) throws -> Double {

        guard x.count == y.count,
              x.count >= 2
        else {
            throw QuantError.dimensionMismatch
        }

        let mx = try mean(x)
        let my = try mean(y)

        var total = 0.0

        for index in x.indices {
            total +=
                (x[index] - mx) *
                (y[index] - my)
        }

        return total / Double(x.count - 1)
    }

    static func correlation(
        _ x: [Double],
        _ y: [Double]
    ) throws -> Double {

        let covariance =
            try covariance(x, y)

        let sx =
            try standardDeviation(x)

        let sy =
            try standardDeviation(y)

        guard sx > 0, sy > 0 else {
            throw QuantError.invalidVariance
        }

        return covariance / (sx * sy)
    }

    static func clamp(
        _ value: Double,
        minimum: Double,
        maximum: Double
    ) -> Double {

        Swift.max(
            minimum,
            Swift.min(maximum, value)
        )
    }
}

// MARK: - Quantile

enum Quantile {

    static func value(
        _ values: [Double],
        probability: Double
    ) throws -> Double {

        guard !values.isEmpty else {
            throw QuantError.emptyData
        }

        guard probability >= 0,
              probability <= 1
        else {
            throw QuantError.invalidProbability
        }

        let sorted =
            values.sorted()

        if sorted.count == 1 {
            return sorted[0]
        }

        let position =
            probability *
            Double(sorted.count - 1)

        let lower =
            Int(floor(position))

        let upper =
            Int(ceil(position))

        if lower == upper {
            return sorted[lower]
        }

        let fraction =
            position - Double(lower)

        return sorted[lower] +
            (sorted[upper] - sorted[lower]) *
            fraction
    }
}

// MARK: - Return Series

struct ReturnSeries: Sendable {

    let values: [Double]

    static func simple(
        prices: [Double]
    ) throws -> ReturnSeries {

        guard prices.count >= 2 else {
            throw QuantError.insufficientObservations
        }

        var result: [Double] = []
        result.reserveCapacity(prices.count - 1)

        for index in 1..<prices.count {

            let previous = prices[index - 1]
            let current = prices[index]

            guard previous > 0,
                  current > 0
            else {
                throw QuantError.invalidPrice
            }

            result.append(
                current / previous - 1.0
            )
        }

        return ReturnSeries(
            values: result
        )
    }

    static func logarithmic(
        prices: [Double]
    ) throws -> ReturnSeries {

        guard prices.count >= 2 else {
            throw QuantError.insufficientObservations
        }

        var result: [Double] = []

        for index in 1..<prices.count {

            let previous = prices[index - 1]
            let current = prices[index]

            guard previous > 0,
                  current > 0
            else {
                throw QuantError.invalidPrice
            }

            result.append(
                log(current / previous)
            )
        }

        return ReturnSeries(
            values: result
        )
    }
}

// MARK: - Time Series

struct QuantObservation: Codable, Sendable {

    let timestamp: Date
    let value: Double
}

struct QuantTimeSeries: Codable, Sendable {

    let id: MarketSeriesID

    private(set) var observations: [QuantObservation]

    init(
        id: MarketSeriesID,
        observations: [QuantObservation] = []
    ) {
        self.id = id
        self.observations = observations.sorted {
            $0.timestamp < $1.timestamp
        }
    }

    mutating func append(
        timestamp: Date,
        value: Double
    ) {

        observations.append(
            QuantObservation(
                timestamp: timestamp,
                value: value
            )
        )
    }

    func values() -> [Double] {
        observations.map(\.value)
    }

    func returns() throws -> ReturnSeries {
        try ReturnSeries.simple(
            prices: values()
        )
    }

    func logarithmicReturns() throws -> ReturnSeries {
        try ReturnSeries.logarithmic(
            prices: values()
        )
    }
}

// MARK: - Statistics

struct DescriptiveStatistics: Sendable {

    let count: Int
    let mean: Double
    let variance: Double
    let standardDeviation: Double
    let minimum: Double
    let maximum: Double
    let median: Double
    let percentile05: Double
    let percentile95: Double
}

enum StatisticsEngine {

    static func describe(
        _ values: [Double]
    ) throws -> DescriptiveStatistics {

        guard !values.isEmpty else {
            throw QuantError.emptyData
        }

        let mean =
            try QuantMath.mean(values)

        let variance =
            values.count >= 2
            ? try QuantMath.variance(values)
            : 0

        let deviation =
            sqrt(variance)

        let median =
            try Quantile.value(
                values,
                probability: 0.50
            )

        let p05 =
            try Quantile.value(
                values,
                probability: 0.05
            )

        let p95 =
            try Quantile.value(
                values,
                probability: 0.95
            )

        return DescriptiveStatistics(
            count: values.count,
            mean: mean,
            variance: variance,
            standardDeviation: deviation,
            minimum: values.min()!,
            maximum: values.max()!,
            median: median,
            percentile05: p05,
            percentile95: p95
        )
    }
}

// MARK: - Matrix

struct QuantMatrix: Sendable {

    let rows: Int
    let columns: Int

    private(set) var values: [Double]

    init(
        rows: Int,
        columns: Int,
        repeating value: Double = 0
    ) {

        self.rows = rows
        self.columns = columns

        self.values =
            Array(
                repeating: value,
                count: rows * columns
            )
    }

    init(
        rows: Int,
        columns: Int,
        values: [Double]
    ) throws {

        guard rows > 0,
              columns > 0,
              values.count == rows * columns
        else {
            throw QuantError.dimensionMismatch
        }

        self.rows = rows
        self.columns = columns
        self.values = values
    }

    subscript(
        row: Int,
        column: Int
    ) -> Double {

        get {
            values[
                row * columns + column
            ]
        }

        set {
            values[
                row * columns + column
            ] = newValue
        }
    }

    static func identity(
        _ size: Int
    ) -> QuantMatrix {

        var matrix =
            QuantMatrix(
                rows: size,
                columns: size
            )

        for index in 0..<size {
            matrix[index, index] = 1
        }

        return matrix
    }

    func transposed() -> QuantMatrix {

        var result =
            QuantMatrix(
                rows: columns,
                columns: rows
            )

        for row in 0..<rows {
            for column in 0..<columns {
                result[column, row] =
                    self[row, column]
            }
        }

        return result
    }

    static func + (
        lhs: QuantMatrix,
        rhs: QuantMatrix
    ) throws -> QuantMatrix {

        guard lhs.rows == rhs.rows,
              lhs.columns == rhs.columns
        else {
            throw QuantError.dimensionMismatch
        }

        return try QuantMatrix(
            rows: lhs.rows,
            columns: lhs.columns,
            values: zip(
                lhs.values,
                rhs.values
            ).map(+)
        )
    }

    static func - (
        lhs: QuantMatrix,
        rhs: QuantMatrix
    ) throws -> QuantMatrix {

        guard lhs.rows == rhs.rows,
              lhs.columns == rhs.columns
        else {
            throw QuantError.dimensionMismatch
        }

        return try QuantMatrix(
            rows: lhs.rows,
            columns: lhs.columns,
            values: zip(
                lhs.values,
                rhs.values
            ).map(-)
        )
    }

    static func * (
        lhs: QuantMatrix,
        rhs: QuantMatrix
    ) throws -> QuantMatrix {

        guard lhs.columns == rhs.rows
        else {
            throw QuantError.dimensionMismatch
        }

        var result =
            QuantMatrix(
                rows: lhs.rows,
                columns: rhs.columns
            )

        for i in 0..<lhs.rows {

            for j in 0..<rhs.columns {

                var sum = 0.0

                for k in 0..<lhs.columns {

                    sum +=
                        lhs[i, k] *
                        rhs[k, j]
                }

                result[i, j] = sum
            }
        }

        return result
    }
}

// MARK: - Covariance Matrix

enum CovarianceEngine {

    static func matrix(
        returns: [[Double]]
    ) throws -> QuantMatrix {

        guard !returns.isEmpty else {
            throw QuantError.emptyData
        }

        let dimensions =
            returns.count

        let observations =
            returns[0].count

        guard observations >= 2 else {
            throw QuantError.insufficientObservations
        }

        guard returns.allSatisfy({
            $0.count == observations
        }) else {
            throw QuantError.dimensionMismatch
        }

        var result =
            QuantMatrix(
                rows: dimensions,
                columns: dimensions
            )

        for i in 0..<dimensions {

            for j in 0..<dimensions {

                result[i, j] =
                    try QuantMath.covariance(
                        returns[i],
                        returns[j]
                    )
            }
        }

        return result
    }
}

// MARK: - Instrument

enum QuantInstrumentType: String, Codable, Sendable {

    case equity
    case bond
    case future
    case option
    case currency
    case commodity
    case cryptocurrency
    case index
}

struct QuantInstrument: Codable, Sendable {

    let id: QuantInstrumentID
    let symbol: String
    let type: QuantInstrumentType
    let currency: String
}

// MARK: - Market Quote

struct MarketQuote: Codable, Sendable {

    let instrumentID: QuantInstrumentID

    let timestamp: Date

    let bid: Double
    let ask: Double

    let last: Double

    var mid: Double {
        (bid + ask) / 2
    }

    var spread: Double {
        ask - bid
    }
}

// MARK: - Market Data Store

actor QuantMarketDataStore {

    private var instruments:
        [QuantInstrumentID: QuantInstrument] = [:]

    private var latestQuotes:
        [QuantInstrumentID: MarketQuote] = [:]

    private var histories:
        [QuantInstrumentID: [MarketQuote]] = [:]

    func register(
        _ instrument: QuantInstrument
    ) {

        instruments[instrument.id] =
            instrument
    }

    func instrument(
        _ id: QuantInstrumentID
    ) -> QuantInstrument? {

        instruments[id]
    }

    func update(
        quote: MarketQuote
    ) throws {

        guard quote.bid >= 0,
              quote.ask >= quote.bid,
              quote.last >= 0
        else {
            throw QuantError.invalidPrice
        }

        latestQuotes[
            quote.instrumentID
        ] = quote

        histories[
            quote.instrumentID,
            default: []
        ].append(quote)
    }

    func latest(
        _ id: QuantInstrumentID
    ) -> MarketQuote? {

        latestQuotes[id]
    }

    func history(
        _ id: QuantInstrumentID
    ) -> [MarketQuote] {

        histories[id] ?? []
    }
}

// MARK: - Portfolio Position

struct QuantPosition: Codable, Sendable {

    let instrumentID: QuantInstrumentID

    var quantity: Double
    var averagePrice: Double

    var marketValue: Double {

        quantity * averagePrice
    }
}

// MARK: - Portfolio

struct QuantPortfolio: Codable, Sendable {

    let id: PortfolioID

    private(set) var positions:
        [QuantInstrumentID: QuantPosition]

    var cash: Double

    init(
        id: PortfolioID = PortfolioID(),
        cash: Double = 0
    ) {

        self.id = id
        self.cash = cash
        self.positions = [:]
    }

    mutating func trade(
        instrumentID: QuantInstrumentID,
        quantity: Double,
        price: Double
    ) throws {

        guard price >= 0 else {
            throw QuantError.invalidPrice
        }

        guard quantity != 0 else {
            throw QuantError.invalidQuantity
        }

        let existing =
            positions[instrumentID]

        let oldQuantity =
            existing?.quantity ?? 0

        let oldAverage =
            existing?.averagePrice ?? 0

        let newQuantity =
            oldQuantity + quantity

        if newQuantity == 0 {

            positions.removeValue(
                forKey: instrumentID
            )

        } else {

            let newAverage: Double

            if oldQuantity == 0 {

                newAverage = price

            } else if
                (oldQuantity > 0 && quantity > 0) ||
                (oldQuantity < 0 && quantity < 0)
            {

                newAverage =
                    (
                        oldQuantity * oldAverage +
                        quantity * price
                    ) / newQuantity

            } else {

                newAverage = oldAverage
            }

            positions[instrumentID] =
                QuantPosition(
                    instrumentID: instrumentID,
                    quantity: newQuantity,
                    averagePrice: newAverage
                )
        }

        cash -= quantity * price
    }
}

// MARK: - Portfolio Valuation

struct PortfolioValuation: Sendable {

    let timestamp: Date

    let cash: Double

    let positionsValue: Double

    let totalValue: Double
}

enum PortfolioValuationEngine {

    static func value(
        portfolio: QuantPortfolio,
        quotes: [QuantInstrumentID: MarketQuote]
    ) throws -> PortfolioValuation {

        var positionValue = 0.0

        for position in portfolio.positions.values {

            guard let quote =
                    quotes[position.instrumentID]
            else {
                continue
            }

            positionValue +=
                position.quantity *
                quote.mid
        }

        return PortfolioValuation(
            timestamp: Date(),
            cash: portfolio.cash,
            positionsValue: positionValue,
            totalValue:
                portfolio.cash +
                positionValue
        )
    }
}

// MARK: - Portfolio Returns

struct PortfolioReturnSeries: Sendable {

    let values: [Double]

    var cumulativeReturn: Double {

        values.reduce(1.0) {
            $0 * (1 + $1)
        } - 1
    }

    var annualisedReturn: Double {

        guard !values.isEmpty else {
            return 0
        }

        let growth =
            1 + cumulativeReturn

        return pow(
            growth,
            252.0 / Double(values.count)
        ) - 1
    }
}

// MARK: - Sharpe Ratio

enum PortfolioRiskStatistics {

    static func sharpeRatio(
        returns: [Double],
        riskFreeRate: Double = 0
    ) throws -> Double {

        guard returns.count >= 2 else {
            throw QuantError.insufficientObservations
        }

        let average =
            try QuantMath.mean(returns)

        let deviation =
            try QuantMath.standardDeviation(returns)

        guard deviation > 0 else {
            throw QuantError.invalidVariance
        }

        let excess =
            average - riskFreeRate / 252.0

        return excess /
            deviation *
            sqrt(252.0)
    }

    static func maximumDrawdown(
        returns: [Double]
    ) -> Double {

        var wealth = 1.0
        var peak = 1.0
        var maximumDrawdown = 0.0

        for value in returns {

            wealth *= 1 + value

            peak =
                max(
                    peak,
                    wealth
                )

            let drawdown =
                wealth / peak - 1

            maximumDrawdown =
                min(
                    maximumDrawdown,
                    drawdown
                )
        }

        return maximumDrawdown
    }
}

// MARK: - Value at Risk

enum VaRMethod: Sendable {

    case historical
    case parametric
    case monteCarlo
}

struct RiskMeasure: Sendable {

    let confidence: Double
    let valueAtRisk: Double
    let conditionalValueAtRisk: Double
}

enum ValueAtRiskEngine {

    static func historical(
        returns: [Double],
        portfolioValue: Double,
        confidence: Double
    ) throws -> RiskMeasure {

        guard portfolioValue > 0 else {
            throw QuantError.invalidPrice
        }

        let losses =
            returns.map {
                -$0 * portfolioValue
            }

        let threshold =
            try Quantile.value(
                losses,
                probability: confidence
            )

        let tail =
            losses.filter {
                $0 >= threshold
            }

        let cvar =
            tail.isEmpty
            ? threshold
            : try QuantMath.mean(tail)

        return RiskMeasure(
            confidence: confidence,
            valueAtRisk: threshold,
            conditionalValueAtRisk: cvar
        )
    }

    static func parametric(
        returns: [Double],
        portfolioValue: Double,
        confidence: Double
    ) throws -> RiskMeasure {

        let mean =
            try QuantMath.mean(returns)

        let deviation =
            try QuantMath.standardDeviation(returns)

        // Approximation for common confidence levels.
        let z: Double

        switch confidence {

        case 0.90:
            z = 1.2815515655

        case 0.95:
            z = 1.6448536269

        case 0.975:
            z = 1.9599639845

        case 0.99:
            z = 2.326347874

        default:
            throw QuantError.invalidProbability
        }

        let loss =
            -(mean - z * deviation) *
            portfolioValue

        return RiskMeasure(
            confidence: confidence,
            valueAtRisk: loss,
            conditionalValueAtRisk: loss
        )
    }
}

// MARK: - Black-Scholes

struct BlackScholesInput: Sendable {

    let spot: Double
    let strike: Double
    let timeToExpiry: Double

    let riskFreeRate: Double
    let volatility: Double

    let dividendYield: Double
}

struct OptionPriceResult: Sendable {

    let call: Double
    let put: Double

    let deltaCall: Double
    let deltaPut: Double

    let gamma: Double
    let vega: Double

    let thetaCall: Double
    let thetaPut: Double

    let rhoCall: Double
    let rhoPut: Double
}

enum BlackScholesEngine {

    static func price(
        input: BlackScholesInput
    ) throws -> OptionPriceResult {

        guard input.spot > 0,
              input.strike > 0,
              input.timeToExpiry >= 0,
              input.volatility > 0
        else {
            throw QuantError.invalidData
        }

        let s = input.spot
        let k = input.strike
        let t = input.timeToExpiry
        let r = input.riskFreeRate
        let sigma = input.volatility
        let q = input.dividendYield

        guard t > 0 else {

            let call =
                max(
                    0,
                    s - k
                )

            let put =
                max(
                    0,
                    k - s
                )

            return OptionPriceResult(
                call: call,
                put: put,
                deltaCall: s > k ? 1 : 0,
                deltaPut: s < k ? -1 : 0,
                gamma: 0,
                vega: 0,
                thetaCall: 0,
                thetaPut: 0,
                rhoCall: 0,
                rhoPut: 0
            )
        }

        let sqrtT =
            sqrt(t)

        let d1 =
            (
                log(s / k) +
                (r - q + 0.5 * sigma * sigma) * t
            ) /
            (sigma * sqrtT)

        let d2 =
            d1 -
            sigma * sqrtT

        let nd1 =
            normalCDF(d1)

        let nd2 =
            normalCDF(d2)

        let density =
            normalPDF(d1)

        let discount =
            exp(-r * t)

        let dividendDiscount =
            exp(-q * t)

        let call =
            s * dividendDiscount * nd1 -
            k * discount * nd2

        let put =
            k * discount * normalCDF(-d2) -
            s * dividendDiscount * normalCDF(-d1)

        let deltaCall =
            dividendDiscount * nd1

        let deltaPut =
            dividendDiscount * (nd1 - 1)

        let gamma =
            dividendDiscount *
            density /
            (s * sigma * sqrtT)

        let vega =
            s *
            dividendDiscount *
            density *
            sqrtT

        let thetaCall =
            -(
                s *
                dividendDiscount *
                density *
                sigma /
                (2 * sqrtT)
            )
            - r *
            k *
            discount *
            nd2
            + q *
            s *
            dividendDiscount *
            nd1

        let thetaPut =
            -(
                s *
                dividendDiscount *
                density *
                sigma /
                (2 * sqrtT)
            )
            + r *
            k *
            discount *
            normalCDF(-d2)
            - q *
            s *
            dividendDiscount *
            normalCDF(-d1)

        let rhoCall =
            k *
            t *
            discount *
            nd2

        let rhoPut =
            -k *
            t *
            discount *
            normalCDF(-d2)

        return OptionPriceResult(
            call: call,
            put: put,
            deltaCall: deltaCall,
            deltaPut: deltaPut,
            gamma: gamma,
            vega: vega,
            thetaCall: thetaCall,
            thetaPut: thetaPut,
            rhoCall: rhoCall,
            rhoPut: rhoPut
        )
    }

    private static func normalPDF(
        _ x: Double
    ) -> Double {

        exp(
            -0.5 * x * x
        ) /
        sqrt(
            2 * Double.pi
        )
    }

    private static func normalCDF(
        _ x: Double
    ) -> Double {

        let sign =
            x < 0 ? -1.0 : 1.0

        let absolute = abs(x)

        let t =
            1 /
            (
                1 +
                0.2316419 * absolute
            )

        let polynomial =
            t *
            (
                0.319381530 +
                t *
                (
                    -0.356563782 +
                    t *
                    (
                        1.781477937 +
                        t *
                        (
                            -1.821255978 +
                            t *
                            1.330274429
                        )
                    )
                )
            )

        let result =
            1 -
            normalPDF(absolute) *
            polynomial

        return 0.5 *
            (
                1 +
                sign *
                (2 * result - 1)
            )
    }
}

// MARK: - Random Number Generator

struct QuantRandomGenerator: Sendable {

    private var generator:
        SystemRandomNumberGenerator

    init() {
        generator =
            SystemRandomNumberGenerator()
    }

    mutating func uniform() -> Double {

        Double.random(
            in: 0..<1,
            using: &generator
        )
    }

    mutating func normal() -> Double {

        var u1 = uniform()
        let u2 = uniform()

        u1 = max(
            u1,
            Double.leastNonzeroMagnitude
        )

        return sqrt(
            -2 * log(u1)
        ) *
        cos(
            2 * Double.pi * u2
        )
    }
}

// MARK: - Monte Carlo

struct MonteCarloResult: Sendable {

    let paths: Int

    let mean: Double

    let standardDeviation: Double

    let percentile05: Double

    let percentile50: Double

    let percentile95: Double
}

enum MonteCarloEngine {

    static func simulateGBM(
        initialValue: Double,
        drift: Double,
        volatility: Double,
        years: Double,
        steps: Int,
        paths: Int
    ) throws -> MonteCarloResult {

        guard initialValue > 0,
              volatility >= 0,
              years > 0,
              steps > 0,
              paths > 0
        else {
            throw QuantError.simulationFailed
        }

        let dt =
            years / Double(steps)

        let sqrtDT =
            sqrt(dt)

        var generator =
            QuantRandomGenerator()

        var terminalValues:
            [Double] = []

        terminalValues.reserveCapacity(paths)

        for _ in 0..<paths {

            var value =
                initialValue

            for _ in 0..<steps {

                let z =
                    generator.normal()

                value *= exp(
                    (
                        drift -
                        0.5 * volatility * volatility
                    ) * dt
                    +
                    volatility *
                    sqrtDT *
                    z
                )
            }

            terminalValues.append(
                value
            )
        }

        let mean =
            try QuantMath.mean(
                terminalValues
            )

        let deviation =
            try QuantMath.standardDeviation(
                terminalValues
            )

        return MonteCarloResult(
            paths: paths,
            mean: mean,
            standardDeviation: deviation,
            percentile05:
                try Quantile.value(
                    terminalValues,
                    probability: 0.05
                ),
            percentile50:
                try Quantile.value(
                    terminalValues,
                    probability: 0.50
                ),
            percentile95:
                try Quantile.value(
                    terminalValues,
                    probability: 0.95
                )
        )
    }
}

// MARK: - Portfolio Optimisation

struct PortfolioConstraints: Sendable {

    let minimumWeight: Double
    let maximumWeight: Double

    init(
        minimumWeight: Double = 0,
        maximumWeight: Double = 1
    ) {

        self.minimumWeight =
            minimumWeight

        self.maximumWeight =
            maximumWeight
    }
}

struct PortfolioOptimisationResult: Sendable {

    let weights: [Double]

    let expectedReturn: Double

    let volatility: Double

    let sharpeRatio: Double
}

enum PortfolioOptimiser {

    static func equalWeight(
        assets: Int
    ) throws -> [Double] {

        guard assets > 0 else {
            throw QuantError.invalidData
        }

        let weight =
            1.0 / Double(assets)

        return Array(
            repeating: weight,
            count: assets
        )
    }

    static func minimumVariance(
        expectedReturns: [Double],
        covariance: QuantMatrix,
        constraints:
            PortfolioConstraints =
                PortfolioConstraints()
    ) throws -> PortfolioOptimisationResult {

        let count =
            expectedReturns.count

        guard count > 0,
              covariance.rows == count,
              covariance.columns == count
        else {
            throw QuantError.dimensionMismatch
        }

        // A deterministic projected-gradient approximation.
        // Suitable as a foundation; production optimisation can
        // replace this with a specialised numerical solver.

        var weights =
            try equalWeight(
                assets: count
            )

        let learningRate = 0.01

        for _ in 0..<2_000 {

            var gradient =
                Array(
                    repeating: 0.0,
                    count: count
                )

            for i in 0..<count {

                for j in 0..<count {

                    gradient[i] +=
                        2 *
                        covariance[i, j] *
                        weights[j]
                }
            }

            for i in 0..<count {

                weights[i] -=
                    learningRate *
                    gradient[i]

                weights[i] =
                    QuantMath.clamp(
                        weights[i],
                        minimum:
                            constraints.minimumWeight,
                        maximum:
                            constraints.maximumWeight
                    )
            }

            let total =
                weights.reduce(0, +)

            guard total > 0 else {
                throw QuantError.optimisationFailed
            }

            weights =
                weights.map {
                    $0 / total
                }
        }

        var expectedReturn = 0.0

        for i in 0..<count {

            expectedReturn +=
                weights[i] *
                expectedReturns[i]
        }

        var variance = 0.0

        for i in 0..<count {

            for j in 0..<count {

                variance +=
                    weights[i] *
                    covariance[i, j] *
                    weights[j]
            }
        }

        let volatility =
            sqrt(
                max(0, variance)
            )

        let sharpe =
            volatility > 0
            ? expectedReturn / volatility
            : 0

        return PortfolioOptimisationResult(
            weights: weights,
            expectedReturn: expectedReturn,
            volatility: volatility,
            sharpeRatio: sharpe
        )
    }
}

// MARK: - Exponential Moving Average

struct EMAState: Sendable {

    private(set) var value: Double?

    let alpha: Double

    init(
        period: Int
    ) {

        let safePeriod =
            max(1, period)

        self.alpha =
            2.0 /
            Double(safePeriod + 1)

        self.value = nil
    }

    mutating func update(
        _ newValue: Double
    ) -> Double {

        if let value {

            self.value =
                alpha * newValue +
                (1 - alpha) * value

        } else {

            self.value =
                newValue
        }

        return self.value!
    }
}

// MARK: - Rolling Statistics

struct RollingStatistics: Sendable {

    let window: Int

    private var values:
        [Double]

    init(
        window: Int
    ) {

        self.window =
            max(1, window)

        self.values = []
    }

    mutating func append(
        _ value: Double
    ) {

        values.append(value)

        if values.count > window {
            values.removeFirst(
                values.count - window
            )
        }
    }

    func statistics()
        throws -> DescriptiveStatistics {

        try StatisticsEngine.describe(
            values
        )
    }
}

// MARK: - Correlation Matrix

enum CorrelationEngine {

    static func matrix(
        returns: [[Double]]
    ) throws -> QuantMatrix {

        let covariance =
            try CovarianceEngine.matrix(
                returns: returns
            )

        var deviations:
            [Double] = []

        for index in 0..<covariance.rows {

            deviations.append(
                sqrt(
                    max(
                        0,
                        covariance[index, index]
                    )
                )
            )
        }

        var result =
            QuantMatrix(
                rows: covariance.rows,
                columns: covariance.columns
            )

        for i in 0..<covariance.rows {

            for j in 0..<covariance.columns {

                let denominator =
                    deviations[i] *
                    deviations[j]

                result[i, j] =
                    denominator > 0
                    ? covariance[i, j] /
                      denominator
                    : 0
            }
        }

        return result
    }
}

// MARK: - Quant Risk Engine

struct PortfolioRiskReport: Sendable {

    let statistics: DescriptiveStatistics

    let sharpeRatio: Double

    let maximumDrawdown: Double

    let historicalVaR: RiskMeasure

    let parametricVaR: RiskMeasure
}

enum QuantRiskEngine {

    static func analyse(
        returns: [Double],
        portfolioValue: Double,
        confidence: Double = 0.95
    ) throws -> PortfolioRiskReport {

        let statistics =
            try StatisticsEngine.describe(
                returns
            )

        let sharpe =
            try PortfolioRiskStatistics.sharpeRatio(
                returns: returns
            )

        let drawdown =
            PortfolioRiskStatistics.maximumDrawdown(
                returns: returns
            )

        let historical =
            try ValueAtRiskEngine.historical(
                returns: returns,
                portfolioValue: portfolioValue,
                confidence: confidence
            )

        let parametric =
            try ValueAtRiskEngine.parametric(
                returns: returns,
                portfolioValue: portfolioValue,
                confidence: confidence
            )

        return PortfolioRiskReport(
            statistics: statistics,
            sharpeRatio: sharpe,
            maximumDrawdown: drawdown,
            historicalVaR: historical,
            parametricVaR: parametric
        )
    }
}

// MARK: - Quant Job

struct QuantJobID: Hashable, Sendable {

    let rawValue: UUID

    init() {
        rawValue = UUID()
    }
}

enum QuantJobState: Sendable {

    case queued
    case running
    case completed
    case failed
}

// MARK: - Quant Job Engine

actor QuantJobEngine {

    private var states:
        [QuantJobID: QuantJobState] = [:]

    func submit<T: Sendable>(
        operation:
            @escaping @Sendable () async throws -> T
    ) async throws -> T {

        let id =
            QuantJobID()

        states[id] = .queued

        states[id] = .running

        do {

            let result =
                try await operation()

            states[id] = .completed

            return result

        } catch {

            states[id] = .failed

            throw error
        }
    }

    func state(
        _ id: QuantJobID
    ) -> QuantJobState? {

        states[id]
    }
}

// MARK: - Quant Engine

actor SwiftQuantEngine {

    let marketData:
        QuantMarketDataStore

    let jobs:
        QuantJobEngine

    private(set) var portfolios:
        [PortfolioID: QuantPortfolio] = [:]

    init() {

        self.marketData =
            QuantMarketDataStore()

        self.jobs =
            QuantJobEngine()
    }

    // MARK: Instruments

    func register(
        instrument: QuantInstrument
    ) async {

        await marketData.register(
            instrument
        )
    }

    // MARK: Quotes

    func update(
        quote: MarketQuote
    ) async throws {

        try await marketData.update(
            quote: quote
        )
    }

    func latestQuote(
        _ id: QuantInstrumentID
    ) async -> MarketQuote? {

        await marketData.latest(id)
    }

    // MARK: Portfolio

    func createPortfolio(
        cash: Double
    ) -> PortfolioID {

        var portfolio =
            QuantPortfolio(
                cash: cash
            )

        let id =
            portfolio.id

        portfolios[id] =
            portfolio

        return id
    }

    func trade(
        portfolioID: PortfolioID,
        instrumentID: QuantInstrumentID,
        quantity: Double,
        price: Double
    ) throws {

        guard var portfolio =
                portfolios[portfolioID]
        else {
            throw QuantError.invalidData
        }

        try portfolio.trade(
            instrumentID: instrumentID,
            quantity: quantity,
            price: price
        )

        portfolios[portfolioID] =
            portfolio
    }

    func portfolio(
        _ id: PortfolioID
    ) -> QuantPortfolio? {

        portfolios[id]
    }

    // MARK: Valuation

    func valuation(
        portfolioID: PortfolioID
    ) async throws -> PortfolioValuation {

        guard let portfolio =
                portfolios[portfolioID]
        else {
            throw QuantError.invalidData
        }

        var quotes:
            [QuantInstrumentID: MarketQuote] = [:]

        for instrumentID
            in portfolio.positions.keys {

            if let quote =
                await marketData.latest(
                    instrumentID
                ) {

                quotes[instrumentID] =
                    quote
            }
        }

        return try PortfolioValuationEngine.value(
            portfolio: portfolio,
            quotes: quotes
        )
    }

    // MARK: Option Pricing

    func priceOption(
        _ input: BlackScholesInput
    ) throws -> OptionPriceResult {

        try BlackScholesEngine.price(
            input: input
        )
    }

    // MARK: Monte Carlo

    func monteCarlo(
        initialValue: Double,
        drift: Double,
        volatility: Double,
        years: Double,
        steps: Int,
        paths: Int
    ) throws -> MonteCarloResult {

        try MonteCarloEngine.simulateGBM(
            initialValue: initialValue,
            drift: drift,
            volatility: volatility,
            years: years,
            steps: steps,
            paths: paths
        )
    }

    // MARK: Risk

    func riskReport(
        returns: [Double],
        portfolioValue: Double,
        confidence: Double = 0.95
    ) throws -> PortfolioRiskReport {

        try QuantRiskEngine.analyse(
            returns: returns,
            portfolioValue: portfolioValue,
            confidence: confidence
        )
    }

    // MARK: Optimisation

    func optimise(
        expectedReturns: [Double],
        covariance: QuantMatrix,
        constraints:
            PortfolioConstraints =
                PortfolioConstraints()
    ) throws -> PortfolioOptimisationResult {

        try PortfolioOptimiser.minimumVariance(
            expectedReturns: expectedReturns,
            covariance: covariance,
            constraints: constraints
        )
    }
}





import Foundation

@main
struct SwiftQuantApplication {

    static func main() async {

        let engine =
            SwiftQuantEngine()

        // ---------------------------------------------------------
        // Instruments
        // ---------------------------------------------------------

        let apple =
            QuantInstrument(
                id: QuantInstrumentID("US.AAPL"),
                symbol: "AAPL",
                type: .equity,
                currency: "USD"
            )

        let microsoft =
            QuantInstrument(
                id: QuantInstrumentID("US.MSFT"),
                symbol: "MSFT",
                type: .equity,
                currency: "USD"
            )

        await engine.register(
            instrument: apple
        )

        await engine.register(
            instrument: microsoft
        )

        // ---------------------------------------------------------
        // Market data
        // ---------------------------------------------------------

        try? await engine.update(
            quote: MarketQuote(
                instrumentID:
                    QuantInstrumentID("US.AAPL"),
                timestamp: Date(),
                bid: 224.90,
                ask: 225.10,
                last: 225.00
            )
        )

        try? await engine.update(
            quote: MarketQuote(
                instrumentID:
                    QuantInstrumentID("US.MSFT"),
                timestamp: Date(),
                bid: 510.20,
                ask: 510.60,
                last: 510.40
            )
        )

        // ---------------------------------------------------------
        // Portfolio
        // ---------------------------------------------------------

        let portfolio =
            await engine.createPortfolio(
                cash: 1_000_000
            )

        try? await engine.trade(
            portfolioID: portfolio,
            instrumentID:
                QuantInstrumentID("US.AAPL"),
            quantity: 1_000,
            price: 225
        )

        try? await engine.trade(
            portfolioID: portfolio,
            instrumentID:
                QuantInstrumentID("US.MSFT"),
            quantity: 500,
            price: 510
        )

        if let valuation =
            try? await engine.valuation(
                portfolioID: portfolio
            ) {

            print(
                "Portfolio value:",
                valuation.totalValue
            )
        }

        // ---------------------------------------------------------
        // Option pricing
        // ---------------------------------------------------------

        let option =
            BlackScholesInput(
                spot: 225,
                strike: 230,
                timeToExpiry: 0.5,
                riskFreeRate: 0.04,
                volatility: 0.25,
                dividendYield: 0.005
            )

        if let result =
            try? await engine.priceOption(option) {

            print(
                "Call:",
                result.call
            )

            print(
                "Put:",
                result.put
            )

            print(
                "Gamma:",
                result.gamma
            )
        }

        // ---------------------------------------------------------
        // Monte Carlo
        // ---------------------------------------------------------

        if let simulation =
            try? await engine.monteCarlo(
                initialValue: 100,
                drift: 0.07,
                volatility: 0.20,
                years: 1,
                steps: 252,
                paths: 10_000
            ) {

            print(
                "Monte Carlo mean:",
                simulation.mean
            )

            print(
                "5th percentile:",
                simulation.percentile05
            )

            print(
                "95th percentile:",
                simulation.percentile95
            )
        }

        // ---------------------------------------------------------
        // Risk
        // ---------------------------------------------------------

        let returns = [
            0.010,
            -0.004,
            0.006,
            -0.012,
            0.003,
            0.008,
            -0.006,
            0.011,
            -0.003,
            0.005,
            -0.009,
            0.007
        ]

        if let report =
            try? await engine.riskReport(
                returns: returns,
                portfolioValue: 1_000_000
            ) {

            print(
                "Sharpe:",
                report.sharpeRatio
            )

            print(
                "Maximum drawdown:",
                report.maximumDrawdown
            )

            print(
                "Historical VaR:",
                report.historicalVaR.valueAtRisk
            )
        }
    }
}






//
//  SwiftIndustrialOptimisation.swift
//
//  #6 Swift Industrial Optimisation & Control Engine
//
//  Swift 6
//

import Foundation
import os

// MARK: - Logging

enum IndustrialOptimisationLog {

    static let engine = Logger(
        subsystem: "com.example.swift-industrial",
        category: "optimisation"
    )

    static let solver = Logger(
        subsystem: "com.example.swift-industrial",
        category: "solver"
    )

    static let control = Logger(
        subsystem: "com.example.swift-industrial",
        category: "control"
    )

    static let safety = Logger(
        subsystem: "com.example.swift-industrial",
        category: "safety"
    )
}

// MARK: - Errors

enum OptimisationError: Error, Sendable {

    case emptyProblem
    case invalidVariable
    case invalidConstraint
    case infeasible
    case unbounded
    case solverFailed
    case maximumIterationsReached
    case invalidObjective
    case unsafeControlAction
    case invalidBounds
    case dimensionMismatch
}

// MARK: - IDs

struct OptimisationVariableID:
    Hashable,
    Codable,
    Sendable
{
    let rawValue: String

    init(_ value: String) {
        rawValue = value
    }
}

struct OptimisationProblemID:
    Hashable,
    Codable,
    Sendable
{
    let rawValue: UUID

    init() {
        rawValue = UUID()
    }
}

struct ControlChannelID:
    Hashable,
    Codable,
    Sendable
{
    let rawValue: String

    init(_ value: String) {
        rawValue = value
    }
}

// MARK: - Bounds

struct VariableBounds: Codable, Sendable {

    let minimum: Double
    let maximum: Double

    init(
        minimum: Double,
        maximum: Double
    ) throws {

        guard minimum <= maximum else {
            throw OptimisationError.invalidBounds
        }

        self.minimum = minimum
        self.maximum = maximum
    }

    func contains(
        _ value: Double
    ) -> Bool {

        value >= minimum &&
        value <= maximum
    }

    func clamp(
        _ value: Double
    ) -> Double {

        max(
            minimum,
            min(maximum, value)
        )
    }
}

// MARK: - Optimisation Variable

struct OptimisationVariable:
    Codable,
    Sendable
{

    let id: OptimisationVariableID
    let name: String
    let bounds: VariableBounds

    let initialValue: Double

    init(
        id: OptimisationVariableID,
        name: String,
        bounds: VariableBounds,
        initialValue: Double
    ) throws {

        guard bounds.contains(initialValue) else {
            throw OptimisationError.invalidVariable
        }

        self.id = id
        self.name = name
        self.bounds = bounds
        self.initialValue = initialValue
    }
}

// MARK: - Variable Vector

struct VariableVector: Sendable {

    private(set) var values:
        [OptimisationVariableID: Double]

    init(
        variables: [OptimisationVariable]
    ) {

        var result:
            [OptimisationVariableID: Double] = [:]

        for variable in variables {
            result[variable.id] =
                variable.initialValue
        }

        self.values = result
    }

    init(
        values:
            [OptimisationVariableID: Double]
    ) {
        self.values = values
    }

    subscript(
        _ id: OptimisationVariableID
    ) -> Double? {
        values[id]
    }

    mutating func set(
        _ value: Double,
        for id: OptimisationVariableID
    ) {
        values[id] = value
    }
}

// MARK: - Objective Direction

enum ObjectiveDirection:
    String,
    Codable,
    Sendable
{
    case minimize
    case maximize
}

// MARK: - Objective Function

struct ObjectiveFunction:
    Sendable
{

    let name: String
    let direction: ObjectiveDirection

    let evaluate:
        @Sendable (
            VariableVector
        ) throws -> Double

    init(
        name: String,
        direction: ObjectiveDirection,
        evaluate:
            @escaping @Sendable (
                VariableVector
            ) throws -> Double
    ) {

        self.name = name
        self.direction = direction
        self.evaluate = evaluate
    }
}

// MARK: - Constraint Relation

enum ConstraintRelation:
    String,
    Codable,
    Sendable
{
    case lessThanOrEqual
    case greaterThanOrEqual
    case equal
}

// MARK: - Constraint

struct OptimisationConstraint:
    Sendable
{

    let name: String
    let relation: ConstraintRelation
    let limit: Double

    let evaluate:
        @Sendable (
            VariableVector
        ) throws -> Double

    init(
        name: String,
        relation: ConstraintRelation,
        limit: Double,
        evaluate:
            @escaping @Sendable (
                VariableVector
            ) throws -> Double
    ) {

        self.name = name
        self.relation = relation
        self.limit = limit
        self.evaluate = evaluate
    }

    func violation(
        at vector: VariableVector
    ) throws -> Double {

        let value =
            try evaluate(vector)

        switch relation {

        case .lessThanOrEqual:
            return max(
                0,
                value - limit
            )

        case .greaterThanOrEqual:
            return max(
                0,
                limit - value
            )

        case .equal:
            return abs(
                value - limit
            )
        }
    }

    func isSatisfied(
        at vector: VariableVector,
        tolerance: Double = 1e-8
    ) throws -> Bool {

        try violation(at: vector) <= tolerance
    }
}

// MARK: - Optimisation Problem

struct OptimisationProblem:
    Sendable
{

    let id: OptimisationProblemID

    let variables:
        [OptimisationVariable]

    let objective:
        ObjectiveFunction

    let constraints:
        [OptimisationConstraint]

    let maximumIterations: Int

    let tolerance: Double

    init(
        id: OptimisationProblemID = OptimisationProblemID(),
        variables: [OptimisationVariable],
        objective: ObjectiveFunction,
        constraints:
            [OptimisationConstraint] = [],
        maximumIterations: Int = 10_000,
        tolerance: Double = 1e-7
    ) throws {

        guard !variables.isEmpty else {
            throw OptimisationError.emptyProblem
        }

        guard maximumIterations > 0,
              tolerance > 0
        else {
            throw OptimisationError.invalidObjective
        }

        self.id = id
        self.variables = variables
        self.objective = objective
        self.constraints = constraints
        self.maximumIterations = maximumIterations
        self.tolerance = tolerance
    }
}

// MARK: - Solution

struct OptimisationSolution:
    Sendable
{

    let problemID:
        OptimisationProblemID

    let values:
        VariableVector

    let objectiveValue: Double

    let iterations: Int

    let feasible: Bool

    let converged: Bool

    let executionTime:
        Duration
}

// MARK: - Projection

enum ConstraintProjection {

    static func projectBounds(
        vector: VariableVector,
        variables: [OptimisationVariable]
    ) -> VariableVector {

        var result = vector

        for variable in variables {

            guard let value =
                    result[variable.id]
            else {
                continue
            }

            result.set(
                variable.bounds.clamp(value),
                for: variable.id
            )
        }

        return result
    }
}

// MARK: - Finite Difference Gradient

enum NumericalGradient {

    static func gradient(
        objective: ObjectiveFunction,
        vector: VariableVector,
        variables: [OptimisationVariable],
        step: Double = 1e-5
    ) throws -> VariableVector {

        var result:
            [OptimisationVariableID: Double] = [:]

        for variable in variables {

            guard let original =
                    vector[variable.id]
            else {
                throw OptimisationError.invalidVariable
            }

            let delta =
                max(
                    step,
                    abs(original) * step
                )

            var plus = vector
            var minus = vector

            plus.set(
                variable.bounds.clamp(
                    original + delta
                ),
                for: variable.id
            )

            minus.set(
                variable.bounds.clamp(
                    original - delta
                ),
                for: variable.id
            )

            let upper =
                try objective.evaluate(plus)

            let lower =
                try objective.evaluate(minus)

            let denominator =
                max(
                    1e-12,
                    2 * delta
                )

            result[variable.id] =
                (upper - lower) /
                denominator
        }

        return VariableVector(
            values: result
        )
    }
}

// MARK: - Projected Gradient Solver

actor ProjectedGradientSolver {

    func solve(
        problem: OptimisationProblem
    ) throws -> OptimisationSolution {

        let start =
            ContinuousClock.now

        var vector =
            VariableVector(
                variables: problem.variables
            )

        let direction =
            problem.objective.direction

        let sign =
            direction == .minimize
            ? 1.0
            : -1.0

        var previousObjective:
            Double?

        var converged = false
        var iterations = 0

        let learningRate = 0.01

        for iteration in 0..<problem.maximumIterations {

            iterations =
                iteration + 1

            let rawObjective =
                try problem.objective.evaluate(
                    vector
                )

            let gradient =
                try NumericalGradient.gradient(
                    objective:
                        problem.objective,
                    vector: vector,
                    variables:
                        problem.variables
                )

            var candidate = vector

            for variable in problem.variables {

                guard let value =
                        candidate[variable.id],
                      let gradientValue =
                        gradient[variable.id]
                else {
                    continue
                }

                let updated =
                    value -
                    sign *
                    learningRate *
                    gradientValue

                candidate.set(
                    variable.bounds.clamp(
                        updated
                    ),
                    for: variable.id
                )
            }

            candidate =
                ConstraintProjection.projectBounds(
                    vector: candidate,
                    variables: problem.variables
                )

            let penalty =
                try constraintPenalty(
                    problem.constraints,
                    vector: candidate
                )

            let candidateObjective =
                try problem.objective.evaluate(
                    candidate
                )

            let effectiveObjective =
                sign *
                candidateObjective +
                penalty

            if let previousObjective {

                if abs(
                    effectiveObjective -
                    previousObjective
                ) < problem.tolerance {

                    vector = candidate
                    converged = true
                    break
                }
            }

            previousObjective =
                effectiveObjective

            vector =
                candidate

            if penalty <= problem.tolerance {

                if abs(
                    effectiveObjective -
                    sign * rawObjective
                ) < problem.tolerance {

                    converged = true
                    break
                }
            }
        }

        let objectiveValue =
            try problem.objective.evaluate(
                vector
            )

        let feasible =
            try problem.constraints.allSatisfy {
                try $0.isSatisfied(
                    at: vector,
                    tolerance: problem.tolerance
                )
            }

        return OptimisationSolution(
            problemID: problem.id,
            values: vector,
            objectiveValue: objectiveValue,
            iterations: iterations,
            feasible: feasible,
            converged: converged,
            executionTime:
                ContinuousClock.now - start
        )
    }

    private func constraintPenalty(
        _ constraints:
            [OptimisationConstraint],
        vector: VariableVector
    ) throws -> Double {

        var penalty = 0.0

        for constraint in constraints {

            let violation =
                try constraint.violation(
                    at: vector
                )

            penalty +=
                violation *
                violation *
                1_000
        }

        return penalty
    }
}

// MARK: - Linear Constraint

struct LinearConstraint:
    Sendable
{

    let coefficients:
        [OptimisationVariableID: Double]

    let relation:
        ConstraintRelation

    let limit: Double

    func asConstraint(
        name: String
    ) -> OptimisationConstraint {

        OptimisationConstraint(
            name: name,
            relation: relation,
            limit: limit
        ) { vector in

            coefficients.reduce(0) {
                total,
                element in

                total +
                element.value *
                (vector[element.key] ?? 0)
            }
        }
    }
}

// MARK: - Quadratic Objective

struct QuadraticObjective:
    Sendable
{

    let target:
        [OptimisationVariableID: Double]

    let weights:
        [OptimisationVariableID: Double]

    func objective(
        direction:
            ObjectiveDirection = .minimize
    ) -> ObjectiveFunction {

        ObjectiveFunction(
            name: "Quadratic Objective",
            direction: direction
        ) { vector in

            var result = 0.0

            for (id, targetValue)
                in target {

                let value =
                    vector[id] ?? 0

                let weight =
                    weights[id] ?? 1

                let difference =
                    value - targetValue

                result +=
                    weight *
                    difference *
                    difference
            }

            return result
        }
    }
}

// MARK: - Energy Optimisation

struct EnergyAsset:
    Codable,
    Sendable
{

    let id: String

    let minimumPower: Double
    let maximumPower: Double

    let marginalCost: Double

    let rampRate: Double
}

struct EnergyDispatchInput:
    Sendable
{

    let assets:
        [EnergyAsset]

    let demand:
        Double
}

struct EnergyDispatchResult:
    Sendable
{

    let dispatch:
        [String: Double]

    let totalGeneration:
        Double

    let estimatedCost:
        Double

    let feasible:
        Bool
}

enum EnergyDispatchSolver {

    static func solve(
        input: EnergyDispatchInput
    ) throws -> EnergyDispatchResult {

        guard input.demand >= 0,
              !input.assets.isEmpty
        else {
            throw OptimisationError.emptyProblem
        }

        let sorted =
            input.assets.sorted {
                $0.marginalCost <
                $1.marginalCost
            }

        var remaining =
            input.demand

        var dispatch:
            [String: Double] = [:]

        var totalCost = 0.0

        for asset in sorted {

            let output =
                min(
                    asset.maximumPower,
                    max(
                        asset.minimumPower,
                        remaining
                    )
                )

            dispatch[asset.id] =
                output

            remaining -= output

            totalCost +=
                output *
                asset.marginalCost

            if remaining <= 0 {
                break
            }
        }

        let generation =
            dispatch.values.reduce(
                0,
                +
            )

        return EnergyDispatchResult(
            dispatch: dispatch,
            totalGeneration: generation,
            estimatedCost: totalCost,
            feasible:
                generation >= input.demand
        )
    }
}

// MARK: - Production Planning

struct ProductionLine:
    Sendable
{

    let id: String

    let minimumOutput:
        Double

    let maximumOutput:
        Double

    let energyPerUnit:
        Double

    let labourPerUnit:
        Double

    let costPerUnit:
        Double
}

struct ProductionPlan:
    Sendable
{

    let output:
        [String: Double]

    let totalOutput:
        Double

    let energyUsed:
        Double

    let labourUsed:
        Double

    let totalCost:
        Double
}

enum ProductionPlanner {

    static func plan(
        lines: [ProductionLine],
        demand: Double,
        energyLimit: Double,
        labourLimit: Double
    ) throws -> ProductionPlan {

        guard demand >= 0 else {
            throw OptimisationError.invalidConstraint
        }

        var remaining =
            demand

        var output:
            [String: Double] = [:]

        var energy = 0.0
        var labour = 0.0
        var cost = 0.0

        let ordered =
            lines.sorted {
                $0.costPerUnit <
                $1.costPerUnit
            }

        for line in ordered {

            guard remaining > 0 else {
                break
            }

            let availableByEnergy =
                line.energyPerUnit > 0
                ? (energyLimit - energy) /
                    line.energyPerUnit
                : Double.infinity

            let availableByLabour =
                line.labourPerUnit > 0
                ? (labourLimit - labour) /
                    line.labourPerUnit
                : Double.infinity

            let capacity =
                min(
                    line.maximumOutput,
                    min(
                        remaining,
                        min(
                            availableByEnergy,
                            availableByLabour
                        )
                    )
                )

            let quantity =
                max(
                    0,
                    capacity
                )

            output[line.id] =
                quantity

            remaining -= quantity

            energy +=
                quantity *
                line.energyPerUnit

            labour +=
                quantity *
                line.labourPerUnit

            cost +=
                quantity *
                line.costPerUnit
        }

        let totalOutput =
            output.values.reduce(
                0,
                +
            )

        return ProductionPlan(
            output: output,
            totalOutput: totalOutput,
            energyUsed: energy,
            labourUsed: labour,
            totalCost: cost
        )
    }
}

// MARK: - Control State

enum IndustrialControlMode:
    String,
    Codable,
    Sendable
{
    case manual
    case assisted
    case automatic
    case safe
    case emergency
}

struct ControlValue:
    Sendable
{

    let channel:
        ControlChannelID

    let requestedValue:
        Double

    let validatedValue:
        Double

    let timestamp:
        Date
}

// MARK: - Control Limits

struct ControlLimits:
    Sendable
{

    let minimum:
        Double

    let maximum:
        Double

    let maximumRateOfChange:
        Double

    func validate(
        previous: Double?,
        requested: Double
    ) throws -> Double {

        guard requested.isFinite else {
            throw OptimisationError.unsafeControlAction
        }

        let bounded =
            max(
                minimum,
                min(
                    maximum,
                    requested
                )
            )

        if let previous {

            let rate =
                abs(
                    bounded - previous
                )

            guard rate <= maximumRateOfChange else {
                throw OptimisationError.unsafeControlAction
            }
        }

        return bounded
    }
}

// MARK: - Control Channel

struct ControlChannel:
    Sendable
{

    let id:
        ControlChannelID

    let name:
        String

    let limits:
        ControlLimits
}

// MARK: - Safety Validator

actor IndustrialControlSafetyValidator {

    private var previousValues:
        [ControlChannelID: Double] = [:]

    func validate(
        channel: ControlChannel,
        requestedValue: Double
    ) throws -> ControlValue {

        let previous =
            previousValues[channel.id]

        let validated =
            try channel.limits.validate(
                previous: previous,
                requested: requestedValue
            )

        previousValues[channel.id] =
            validated

        IndustrialOptimisationLog.safety.debug(
            "Control action validated"
        )

        return ControlValue(
            channel: channel.id,
            requestedValue: requestedValue,
            validatedValue: validated,
            timestamp: Date()
        )
    }

    func reset(
        channel: ControlChannelID
    ) {

        previousValues.removeValue(
            forKey: channel
        )
    }
}

// MARK: - Model Predictive Control

struct MPCConfiguration:
    Sendable
{

    let predictionHorizon:
        Int

    let controlHorizon:
        Int

    let stateWeight:
        Double

    let controlWeight:
        Double

    let maximumIterations:
        Int

    init(
        predictionHorizon: Int = 10,
        controlHorizon: Int = 5,
        stateWeight: Double = 1,
        controlWeight: Double = 0.1,
        maximumIterations: Int = 500
    ) {

        self.predictionHorizon =
            max(
                1,
                predictionHorizon
            )

        self.controlHorizon =
            max(
                1,
                controlHorizon
            )

        self.stateWeight =
            max(
                0,
                stateWeight
            )

        self.controlWeight =
            max(
                0,
                controlWeight
            )

        self.maximumIterations =
            max(
                1,
                maximumIterations
            )
    }
}

struct MPCResult:
    Sendable
{

    let controlSequence:
        [Double]

    let predictedStates:
        [Double]

    let objective:
        Double
}

enum SimpleMPCSolver {

    static func solve(
        currentState: Double,
        targetState: Double,
        minimumControl: Double,
        maximumControl: Double,
        configuration:
            MPCConfiguration
    ) -> MPCResult {

        let horizon =
            configuration.controlHorizon

        var controls =
            Array(
                repeating: 0.0,
                count: horizon
            )

        var bestControls =
            controls

        var bestObjective =
            Double.infinity

        let step =
            max(
                0.001,
                (
                    maximumControl -
                    minimumControl
                ) / 20
            )

        // Coordinate-descent MPC approximation.
        for _ in 0..<configuration.maximumIterations {

            var improved = false

            for index in 0..<horizon {

                let candidates = [
                    controls[index] - step,
                    controls[index],
                    controls[index] + step
                ]

                for candidate in candidates {

                    let bounded =
                        max(
                            minimumControl,
                            min(
                                maximumControl,
                                candidate
                            )
                        )

                    var trial =
                        controls

                    trial[index] =
                        bounded

                    let evaluation =
                        evaluate(
                            currentState:
                                currentState,
                            targetState:
                                targetState,
                            controls:
                                trial,
                            configuration:
                                configuration
                        )

                    if evaluation <
                        bestObjective {

                        bestObjective =
                            evaluation

                        bestControls =
                            trial

                        improved = true
                    }
                }

                controls =
                    bestControls
            }

            if !improved {
                break
            }
        }

        let states =
            simulate(
                initial:
                    currentState,
                controls:
                    bestControls
            )

        return MPCResult(
            controlSequence:
                bestControls,
            predictedStates:
                states,
            objective:
                bestObjective
        )
    }

    private static func evaluate(
        currentState: Double,
        targetState: Double,
        controls: [Double],
        configuration:
            MPCConfiguration
    ) -> Double {

        let states =
            simulate(
                initial:
                    currentState,
                controls:
                    controls
            )

        var objective = 0.0

        for state in states {

            let error =
                state - targetState

            objective +=
                configuration.stateWeight *
                error *
                error
        }

        for control in controls {

            objective +=
                configuration.controlWeight *
                control *
                control
        }

        return objective
    }

    private static func simulate(
        initial: Double,
        controls: [Double]
    ) -> [Double] {

        var state =
            initial

        var states:
            [Double] = []

        for control in controls {

            // Simple first-order plant model.
            state +=
                control

            states.append(
                state
            )
        }

        return states
    }
}

// MARK: - Thermal Optimisation

struct ThermalSystem:
    Sendable
{

    let currentTemperature:
        Double

    let targetTemperature:
        Double

    let minimumPower:
        Double

    let maximumPower:
        Double

    let coolingCoefficient:
        Double

    let heatingCoefficient:
        Double
}

struct ThermalOptimisationResult:
    Sendable
{

    let power:
        Double

    let predictedTemperature:
        Double

    let error:
        Double
}

enum ThermalOptimiser {

    static func calculate(
        system: ThermalSystem
    ) -> ThermalOptimisationResult {

        let temperatureError =
            system.targetTemperature -
            system.currentTemperature

        let gain =
            temperatureError >= 0
            ? system.heatingCoefficient
            : system.coolingCoefficient

        let rawPower =
            temperatureError /
            max(
                gain,
                1e-9
            )

        let power =
            max(
                system.minimumPower,
                min(
                    system.maximumPower,
                    rawPower
                )
            )

        let predicted =
            system.currentTemperature +
            gain * power

        return ThermalOptimisationResult(
            power: power,
            predictedTemperature: predicted,
            error:
                system.targetTemperature -
                predicted
        )
    }
}

// MARK: - Battery Optimisation

struct BatteryState:
    Sendable
{

    let stateOfCharge:
        Double

    let minimumStateOfCharge:
        Double

    let maximumStateOfCharge:
        Double

    let maximumChargePower:
        Double

    let maximumDischargePower:
        Double
}

enum BatteryAction:
    Sendable
{
    case charge(Double)
    case discharge(Double)
    case idle
}

struct BatteryOptimisationResult:
    Sendable
{

    let action:
        BatteryAction

    let resultingStateOfCharge:
        Double
}

enum BatteryOptimiser {

    static func optimise(
        battery: BatteryState,
        electricityPrice: Double,
        priceThreshold: Double,
        timestepHours: Double
    ) -> BatteryOptimisationResult {

        let safeStep =
            max(
                0,
                timestepHours
            )

        if electricityPrice <
            priceThreshold {

            let available =
                battery.maximumStateOfCharge -
                battery.stateOfCharge

            let power =
                min(
                    battery.maximumChargePower,
                    available /
                    max(
                        safeStep,
                        1e-9
                    )
                )

            let resulting =
                battery.stateOfCharge +
                power *
                safeStep

            return BatteryOptimisationResult(
                action: .charge(power),
                resultingStateOfCharge:
                    min(
                        battery.maximumStateOfCharge,
                        resulting
                    )
            )
        }

        if electricityPrice >
            priceThreshold {

            let available =
                battery.stateOfCharge -
                battery.minimumStateOfCharge

            let power =
                min(
                    battery.maximumDischargePower,
                    available /
                    max(
                        safeStep,
                        1e-9
                    )
                )

            let resulting =
                battery.stateOfCharge -
                power *
                safeStep

            return BatteryOptimisationResult(
                action: .discharge(power),
                resultingStateOfCharge:
                    max(
                        battery.minimumStateOfCharge,
                        resulting
                    )
            )
        }

        return BatteryOptimisationResult(
            action: .idle,
            resultingStateOfCharge:
                battery.stateOfCharge
        )
    }
}

// MARK: - Industrial Objective

struct IndustrialObjective:
    Sendable
{

    let productionValue:
        Double

    let energyCost:
        Double

    let maintenanceCost:
        Double

    let carbonCost:
        Double

    func totalCost(
        energy:
            Double,
        maintenance:
            Double,
        carbon:
            Double
    ) -> Double {

        energy * energyCost +
        maintenance * maintenanceCost +
        carbon * carbonCost -
        productionValue
    }
}

// MARK: - Control Command

struct IndustrialControlCommand:
    Sendable
{

    let channel:
        ControlChannel

    let requestedValue:
        Double

    let mode:
        IndustrialControlMode

    let reason:
        String
}

// MARK: - Control Engine

actor IndustrialControlEngine {

    private let safetyValidator:
        IndustrialControlSafetyValidator

    private var mode:
        IndustrialControlMode = .manual

    init() {

        self.safetyValidator =
            IndustrialControlSafetyValidator()
    }

    func setMode(
        _ mode:
            IndustrialControlMode
    ) {

        self.mode = mode

        IndustrialOptimisationLog.control.info(
            "Control mode changed"
        )
    }

    func currentMode()
        -> IndustrialControlMode
    {
        mode
    }

    func execute(
        _ command:
            IndustrialControlCommand
    ) async throws -> ControlValue {

        guard mode != .emergency else {
            throw OptimisationError.unsafeControlAction
        }

        guard mode == command.mode ||
              mode == .assisted ||
              mode == .automatic
        else {
            throw OptimisationError.unsafeControlAction
        }

        return try await safetyValidator.validate(
            channel: command.channel,
            requestedValue:
                command.requestedValue
        )
    }
}

// MARK: - Optimisation Pipeline

struct OptimisationPipelineResult:
    Sendable
{

    let solution:
        OptimisationSolution

    let controls:
        [ControlValue]
}

actor IndustrialOptimisationPipeline {

    private let solver:
        ProjectedGradientSolver

    private let controlEngine:
        IndustrialControlEngine

    init() {

        self.solver =
            ProjectedGradientSolver()

        self.controlEngine =
            IndustrialControlEngine()
    }

    func solve(
        problem:
            OptimisationProblem
    ) async throws
        -> OptimisationSolution
    {

        try await solver.solve(
            problem:
                problem
        )
    }

    func execute(
        solution:
            OptimisationSolution,
        commands:
            [IndustrialControlCommand]
    ) async throws
        -> OptimisationPipelineResult
    {

        guard solution.feasible else {
            throw OptimisationError.infeasible
        }

        var results:
            [ControlValue] = []

        for command in commands {

            let result =
                try await controlEngine.execute(
                    command
                )

            results.append(
                result
            )
        }

        return OptimisationPipelineResult(
            solution:
                solution,
            controls:
                results
        )
    }

    func setControlMode(
        _ mode:
            IndustrialControlMode
    ) async {

        await controlEngine.setMode(
            mode
        )
    }
}

// MARK: - Industrial Optimisation Engine

actor SwiftIndustrialOptimisationEngine {

    let pipeline:
        IndustrialOptimisationPipeline

    init() {

        self.pipeline =
            IndustrialOptimisationPipeline()
    }

    func solve(
        problem:
            OptimisationProblem
    ) async throws
        -> OptimisationSolution
    {

        try await pipeline.solve(
            problem:
                problem
        )
    }

    func execute(
        solution:
            OptimisationSolution,
        commands:
            [IndustrialControlCommand]
    ) async throws
        -> OptimisationPipelineResult
    {

        try await pipeline.execute(
            solution:
                solution,
            commands:
                commands
        )
    }

    func setMode(
        _ mode:
            IndustrialControlMode
    ) async {

        await pipeline.setControlMode(
            mode
        )
    }
}








//
// SwiftSystemCore.swift
//
// #7 — Swift System Core
//
// Swift 6
//

import Foundation
import Dispatch
import os

// MARK: - Logging

enum SystemCoreLog {

    static let core = Logger(
        subsystem: "com.example.industrial",
        category: "system-core"
    )

    static let process = Logger(
        subsystem: "com.example.industrial",
        category: "process"
    )

    static let resource = Logger(
        subsystem: "com.example.industrial",
        category: "resource"
    )

    static let scheduler = Logger(
        subsystem: "com.example.industrial",
        category: "scheduler"
    )

    static let diagnostics = Logger(
        subsystem: "com.example.industrial",
        category: "diagnostics"
    )
}

// MARK: - Errors

enum SystemCoreError: Error, Sendable {

    case serviceNotFound
    case serviceAlreadyRegistered
    case serviceUnavailable
    case invalidConfiguration
    case processAlreadyRunning
    case processNotRunning
    case dependencyUnavailable
    case resourceUnavailable
    case invalidResourceRequest
    case schedulerStopped
    case taskNotFound
    case timeout
    case cancelled
}

// MARK: - IDs

struct SystemServiceID:
    Hashable,
    Codable,
    Sendable
{
    let rawValue: String

    init(_ value: String) {
        rawValue = value
    }
}

struct SystemProcessID:
    Hashable,
    Codable,
    Sendable
{
    let rawValue: UUID

    init() {
        rawValue = UUID()
    }
}

struct SystemTaskID:
    Hashable,
    Codable,
    Sendable
{
    let rawValue: UUID

    init() {
        rawValue = UUID()
    }
}

struct ResourceLeaseID:
    Hashable,
    Codable,
    Sendable
{
    let rawValue: UUID

    init() {
        rawValue = UUID()
    }
}

// MARK: - System Lifecycle

enum SystemLifecycleState:
    String,
    Codable,
    Sendable
{
    case booting
    case initializing
    case running
    case degraded
    case shuttingDown
    case stopped
}

// MARK: - Process State

enum SystemProcessState:
    String,
    Codable,
    Sendable
{
    case created
    case starting
    case running
    case suspended
    case stopping
    case stopped
    case failed
}

// MARK: - Service State

enum SystemServiceState:
    String,
    Codable,
    Sendable
{
    case registered
    case starting
    case running
    case degraded
    case stopping
    case stopped
    case failed
}

// MARK: - Priority

enum SystemPriority:
    Int,
    Codable,
    Sendable,
    Comparable
{
    case background = 0
    case utility = 25
    case normal = 50
    case userInitiated = 75
    case high = 90
    case critical = 100
}

// MARK: - System Clock

protocol SystemClock:
    Sendable
{
    func now() -> ContinuousClock.Instant
}

struct DefaultSystemClock:
    SystemClock
{

    func now() ->
        ContinuousClock.Instant
    {
        ContinuousClock.now
    }
}

// MARK: - CPU Resource

struct CPUResource:
    Codable,
    Sendable
{

    let logicalProcessors: Int

    let utilization:
        Double

    let loadAverage:
        Double

    init(
        logicalProcessors: Int,
        utilization: Double,
        loadAverage: Double
    ) {

        self.logicalProcessors =
            max(
                1,
                logicalProcessors
            )

        self.utilization =
            max(
                0,
                min(
                    1,
                    utilization
                )
            )

        self.loadAverage =
            max(
                0,
                loadAverage
            )
    }
}

// MARK: - Memory Resource

struct MemoryResource:
    Codable,
    Sendable
{

    let totalBytes:
        UInt64

    let usedBytes:
        UInt64

    let availableBytes:
        UInt64

    let pressure:
        Double

    var usedFraction:
        Double {

        guard totalBytes > 0 else {
            return 0
        }

        return Double(usedBytes) /
            Double(totalBytes)
    }
}

// MARK: - Power

enum PowerCondition:
    String,
    Codable,
    Sendable
{
    case normal
    case lowPower
    case charging
    case externalPower
}

// MARK: - Thermal State

enum SystemThermalState:
    String,
    Codable,
    Sendable
{
    case nominal
    case fair
    case serious
    case critical
}

// MARK: - System Resource Snapshot

struct SystemResourceSnapshot:
    Codable,
    Sendable
{

    let timestamp:
        Date

    let cpu:
        CPUResource

    let memory:
        MemoryResource

    let thermal:
        SystemThermalState

    let power:
        PowerCondition
}

// MARK: - Resource Request

struct ResourceRequest:
    Codable,
    Sendable
{

    let cpuFraction:
        Double

    let memoryBytes:
        UInt64

    let priority:
        SystemPriority

    let requiresExternalPower:
        Bool

    let maximumThermalState:
        SystemThermalState

    init(
        cpuFraction: Double = 0,
        memoryBytes: UInt64 = 0,
        priority:
            SystemPriority = .normal,
        requiresExternalPower:
            Bool = false,
        maximumThermalState:
            SystemThermalState = .serious
    ) {

        self.cpuFraction =
            max(
                0,
                min(
                    1,
                    cpuFraction
                )
            )

        self.memoryBytes =
            memoryBytes

        self.priority =
            priority

        self.requiresExternalPower =
            requiresExternalPower

        self.maximumThermalState =
            maximumThermalState
    }
}

// MARK: - Resource Lease

struct ResourceLease:
    Codable,
    Sendable
{

    let id:
        ResourceLeaseID

    let process:
        SystemProcessID

    let request:
        ResourceRequest

    let createdAt:
        Date

    var expiration:
        Date?
}

// MARK: - Resource Manager

actor SystemResourceManager {

    private var snapshot:
        SystemResourceSnapshot

    private var leases:
        [ResourceLeaseID: ResourceLease] = [:]

    private let memoryLimit:
        UInt64

    init(
        memoryLimit:
            UInt64 = 1_024 * 1_024 * 1_024
    ) {

        self.memoryLimit =
            memoryLimit

        snapshot =
            SystemResourceSnapshot(
                timestamp: Date(),
                cpu:
                    CPUResource(
                        logicalProcessors:
                            ProcessInfo.processInfo
                                .processorCount,
                        utilization: 0,
                        loadAverage: 0
                    ),
                memory:
                    MemoryResource(
                        totalBytes:
                            ProcessInfo.processInfo
                                .physicalMemory,
                        usedBytes: 0,
                        availableBytes:
                            ProcessInfo.processInfo
                                .physicalMemory,
                        pressure: 0
                    ),
                thermal: .nominal,
                power: .normal
            )
    }

    func update(
        _ snapshot:
            SystemResourceSnapshot
    ) {

        self.snapshot =
            snapshot
    }

    func currentSnapshot()
        -> SystemResourceSnapshot
    {
        snapshot
    }

    func acquire(
        process:
            SystemProcessID,
        request:
            ResourceRequest
    ) throws
        -> ResourceLease
    {

        guard request.memoryBytes <=
                memoryLimit
        else {
            throw SystemCoreError.resourceUnavailable
        }

        if request.requiresExternalPower {

            guard snapshot.power ==
                    .externalPower ||
                  snapshot.power ==
                    .charging
            else {
                throw SystemCoreError.resourceUnavailable
            }
        }

        let lease =
            ResourceLease(
                id:
                    ResourceLeaseID(),
                process:
                    process,
                request:
                    request,
                createdAt:
                    Date(),
                expiration: nil
            )

        leases[lease.id] =
            lease

        SystemCoreLog.resource.debug(
            "Resource lease acquired"
        )

        return lease
    }

    func release(
        _ id:
            ResourceLeaseID
    ) {

        leases.removeValue(
            forKey:
                id
        )
    }

    func leasesForProcess(
        _ process:
            SystemProcessID
    ) -> [ResourceLease] {

        leases.values.filter {
            $0.process == process
        }
    }
}

// MARK: - Service Definition

struct SystemServiceDefinition:
    Sendable
{

    let id:
        SystemServiceID

    let name:
        String

    let dependencies:
        [SystemServiceID]

    let priority:
        SystemPriority
}

// MARK: - Service Protocol

protocol SystemService:
    Sendable
{

    var definition:
        SystemServiceDefinition
    { get }

    func start() async throws

    func stop() async
}

// MARK: - Service Registry

actor SystemServiceRegistry {

    private struct RegisteredService:
        Sendable
    {
        let definition:
            SystemServiceDefinition

        let service:
            any SystemService

        var state:
            SystemServiceState
    }

    private var services:
        [SystemServiceID: RegisteredService]
            = [:]

    func register(
        _ service:
            any SystemService
    ) throws {

        let id =
            service.definition.id

        guard services[id] == nil else {
            throw SystemCoreError
                .serviceAlreadyRegistered
        }

        services[id] =
            RegisteredService(
                definition:
                    service.definition,
                service:
                    service,
                state:
                    .registered
            )

        SystemCoreLog.core.debug(
            "Service registered"
        )
    }

    func state(
        for id:
            SystemServiceID
    ) throws
        -> SystemServiceState
    {

        guard let service =
                services[id]
        else {
            throw SystemCoreError
                .serviceNotFound
        }

        return service.state
    }

    func start(
        _ id:
            SystemServiceID
    ) async throws {

        guard var service =
                services[id]
        else {
            throw SystemCoreError
                .serviceNotFound
        }

        guard service.state != .running else {
            return
        }

        service.state =
            .starting

        services[id] =
            service

        do {

            try await service.service.start()

            service.state =
                .running

            services[id] =
                service

        } catch {

            service.state =
                .failed

            services[id] =
                service

            throw error
        }
    }

    func stop(
        _ id:
            SystemServiceID
    ) async throws {

        guard var service =
                services[id]
        else {
            throw SystemCoreError
                .serviceNotFound
        }

        service.state =
            .stopping

        services[id] =
            service

        await service.service.stop()

        service.state =
            .stopped

        services[id] =
            service
    }

    func allDefinitions()
        -> [SystemServiceDefinition]
    {

        services.values.map {
            $0.definition
        }
    }
}

// MARK: - Dependency-Aware Service Manager

actor SystemServiceManager {

    private let registry:
        SystemServiceRegistry

    private var started:
        Set<SystemServiceID> = []

    init(
        registry:
            SystemServiceRegistry
    ) {

        self.registry =
            registry
    }

    func startAll() async throws {

        let definitions =
            await registry.allDefinitions()

        var remaining =
            Set(
                definitions.map {
                    $0.id
                }
            )

        while !remaining.isEmpty {

            var progress = false

            for definition
                in definitions
            {

                guard remaining.contains(
                    definition.id
                )
                else {
                    continue
                }

                let dependenciesSatisfied =
                    definition.dependencies.allSatisfy {
                        started.contains($0)
                    }

                guard dependenciesSatisfied
                else {
                    continue
                }

                try await registry.start(
                    definition.id
                )

                started.insert(
                    definition.id
                )

                remaining.remove(
                    definition.id
                )

                progress = true
            }

            guard progress else {
                throw SystemCoreError
                    .dependencyUnavailable
            }
        }
    }

    func stopAll() async {

        let services =
            Array(
                started
            )

        for service in services.reversed() {

            try? await registry.stop(
                service
            )
        }

        started.removeAll()
    }
}

// MARK: - Managed Process

struct ManagedProcess:
    Sendable
{

    let id:
        SystemProcessID

    let name:
        String

    let priority:
        SystemPriority

    var state:
        SystemProcessState

    let createdAt:
        Date

    var startedAt:
        Date?

    var stoppedAt:
        Date?

    var restartCount:
        Int
}

// MARK: - Process Supervisor

actor SystemProcessSupervisor {

    private var processes:
        [SystemProcessID: ManagedProcess]
            = [:]

    func create(
        name:
            String,
        priority:
            SystemPriority = .normal
    ) -> SystemProcessID {

        let id =
            SystemProcessID()

        processes[id] =
            ManagedProcess(
                id:
                    id,
                name:
                    name,
                priority:
                    priority,
                state:
                    .created,
                createdAt:
                    Date(),
                startedAt:
                    nil,
                stoppedAt:
                    nil,
                restartCount:
                    0
            )

        SystemCoreLog.process.debug(
            "Process created"
        )

        return id
    }

    func start(
        _ id:
            SystemProcessID
    ) throws {

        guard var process =
                processes[id]
        else {
            throw SystemCoreError
                .serviceNotFound
        }

        guard process.state != .running else {
            throw SystemCoreError
                .processAlreadyRunning
        }

        process.state =
            .running

        process.startedAt =
            Date()

        processes[id] =
            process
    }

    func suspend(
        _ id:
            SystemProcessID
    ) throws {

        guard var process =
                processes[id]
        else {
            throw SystemCoreError
                .serviceNotFound
        }

        guard process.state == .running else {
            throw SystemCoreError
                .processNotRunning
        }

        process.state =
            .suspended

        processes[id] =
            process
    }

    func resume(
        _ id:
            SystemProcessID
    ) throws {

        guard var process =
                processes[id]
        else {
            throw SystemCoreError
                .serviceNotFound
        }

        guard process.state == .suspended else {
            throw SystemCoreError
                .processNotRunning
        }

        process.state =
            .running

        processes[id] =
            process
    }

    func stop(
        _ id:
            SystemProcessID
    ) throws {

        guard var process =
                processes[id]
        else {
            throw SystemCoreError
                .serviceNotFound
        }

        process.state =
            .stopped

        process.stoppedAt =
            Date()

        processes[id] =
            process
    }

    func restart(
        _ id:
            SystemProcessID
    ) throws {

        guard var process =
                processes[id]
        else {
            throw SystemCoreError
                .serviceNotFound
        }

        process.restartCount +=
            1

        process.state =
            .running

        process.startedAt =
            Date()

        processes[id] =
            process
    }

    func process(
        _ id:
            SystemProcessID
    ) throws
        -> ManagedProcess
    {

        guard let process =
                processes[id]
        else {
            throw SystemCoreError
                .serviceNotFound
        }

        return process
    }

    func allProcesses()
        -> [ManagedProcess]
    {
        Array(
            processes.values
        )
    }
}

// MARK: - Scheduled Task

struct ScheduledSystemTask:
    Sendable
{

    let id:
        SystemTaskID

    let name:
        String

    let priority:
        SystemPriority

    let deadline:
        ContinuousClock.Instant?

    let work:
        @Sendable () async throws -> Void
}

// MARK: - Scheduler

actor SystemTaskScheduler {

    private var tasks:
        [SystemTaskID: ScheduledSystemTask]
            = [:]

    private var running =
        false

    private var workerTask:
        Task<Void, Never>?

    func start() {

        guard !running else {
            return
        }

        running = true

        workerTask =
            Task { [weak self] in

                while !Task.isCancelled {

                    guard let self else {
                        return
                    }

                    do {

                        try await self.executeNext()

                    } catch {

                        SystemCoreLog.scheduler.error(
                            "Scheduled task failed"
                        )

                        try? await Task.sleep(
                            for:
                                .milliseconds(50)
                        )
                    }

                    try? await Task.sleep(
                        for:
                            .milliseconds(1)
                    )
                }
            }
    }

    func stop() {

        running = false

        workerTask?.cancel()

        workerTask =
            nil
    }

    @discardableResult
    func submit(
        name:
            String,
        priority:
            SystemPriority = .normal,
        deadline:
            ContinuousClock.Instant? = nil,
        work:
            @escaping @Sendable () async throws -> Void
    ) -> SystemTaskID {

        let id =
            SystemTaskID()

        tasks[id] =
            ScheduledSystemTask(
                id:
                    id,
                name:
                    name,
                priority:
                    priority,
                deadline:
                    deadline,
                work:
                    work
            )

        return id
    }

    func cancel(
        _ id:
            SystemTaskID
    ) {

        tasks.removeValue(
            forKey:
                id
        )
    }

    private func executeNext()
        async throws
    {

        guard running else {
            throw SystemCoreError
                .schedulerStopped
        }

        guard let task =
                selectNext()
        else {
            return
        }

        tasks.removeValue(
            forKey:
                task.id
        )

        try await task.work()
    }

    private func selectNext()
        -> ScheduledSystemTask?
    {

        tasks.values.max {
            lhs,
            rhs in

            if lhs.priority !=
                rhs.priority {

                return lhs.priority <
                    rhs.priority
            }

            switch (
                lhs.deadline,
                rhs.deadline
            ) {

            case let (.some(left), .some(right)):
                return left > right

            case (.some, .none):
                return false

            case (.none, .some):
                return true

            case (.none, .none):
                return false
            }
        }
    }
}

// MARK: - Event Bus

enum SystemEvent:
    Sendable
{

    case lifecycle(
        SystemLifecycleState
    )

    case resourcePressure(
        Double
    )

    case thermalChange(
        SystemThermalState
    )

    case powerChange(
        PowerCondition
    )

    case processStateChanged(
        SystemProcessID,
        SystemProcessState
    )

    case serviceStateChanged(
        SystemServiceID,
        SystemServiceState
    )
}

struct SystemEventSubscriptionID:
    Hashable,
    Sendable
{
    let rawValue:
        UUID

    init() {
        rawValue =
            UUID()
    }
}

actor SystemEventBus {

    typealias Handler =
        @Sendable (
            SystemEvent
        ) async -> Void

    private var handlers:
        [SystemEventSubscriptionID: Handler]
            = [:]

    @discardableResult
    func subscribe(
        handler:
            @escaping Handler
    ) -> SystemEventSubscriptionID {

        let id =
            SystemEventSubscriptionID()

        handlers[id] =
            handler

        return id
    }

    func unsubscribe(
        _ id:
            SystemEventSubscriptionID
    ) {

        handlers.removeValue(
            forKey:
                id
        )
    }

    func publish(
        _ event:
            SystemEvent
    ) async {

        let snapshot =
            Array(
                handlers.values
            )

        for handler in snapshot {

            await handler(
                event
            )
        }
    }
}

// MARK: - Diagnostics

struct SystemDiagnosticsSnapshot:
    Codable,
    Sendable
{

    let timestamp:
        Date

    let lifecycle:
        SystemLifecycleState

    let resources:
        SystemResourceSnapshot

    let processCount:
        Int

    let runningProcessCount:
        Int

    let serviceCount:
        Int
}

// MARK: - Diagnostics Engine

actor SystemDiagnosticsEngine {

    private var samples:
        [SystemDiagnosticsSnapshot]
            = []

    private let maximumSamples:
        Int

    init(
        maximumSamples:
            Int = 1_000
    ) {

        self.maximumSamples =
            max(
                1,
                maximumSamples
            )
    }

    func record(
        _ snapshot:
            SystemDiagnosticsSnapshot
    ) {

        samples.append(
            snapshot
        )

        if samples.count >
            maximumSamples {

            samples.removeFirst(
                samples.count -
                maximumSamples
            )
        }
    }

    func latest()
        -> SystemDiagnosticsSnapshot?
    {
        samples.last
    }

    func history()
        -> [SystemDiagnosticsSnapshot]
    {
        samples
    }

    func clear() {

        samples.removeAll(
            keepingCapacity: true
        )
    }
}

// MARK: - System Core

actor SwiftSystemCore {

    private(set) var lifecycle:
        SystemLifecycleState = .booting

    let resources:
        SystemResourceManager

    let services:
        SystemServiceRegistry

    let serviceManager:
        SystemServiceManager

    let processes:
        SystemProcessSupervisor

    let scheduler:
        SystemTaskScheduler

    let events:
        SystemEventBus

    let diagnostics:
        SystemDiagnosticsEngine

    init() {

        let registry =
            SystemServiceRegistry()

        self.resources =
            SystemResourceManager()

        self.services =
            registry

        self.serviceManager =
            SystemServiceManager(
                registry:
                    registry
            )

        self.processes =
            SystemProcessSupervisor()

        self.scheduler =
            SystemTaskScheduler()

        self.events =
            SystemEventBus()

        self.diagnostics =
            SystemDiagnosticsEngine()
    }

    func boot() async throws {

        guard lifecycle == .booting else {
            return
        }

        lifecycle =
            .initializing

        await events.publish(
            .lifecycle(
                .initializing
            )
        )

        scheduler.start()

        try await serviceManager.startAll()

        lifecycle =
            .running

        await events.publish(
            .lifecycle(
                .running
            )
        )

        SystemCoreLog.core.info(
            "System core boot complete"
        )
    }

    func shutdown() async {

        lifecycle =
            .shuttingDown

        await events.publish(
            .lifecycle(
                .shuttingDown
            )
        )

        scheduler.stop()

        await serviceManager.stopAll()

        lifecycle =
            .stopped

        await events.publish(
            .lifecycle(
                .stopped
            )
        )
    }

    func updateResources(
        _ snapshot:
            SystemResourceSnapshot
    ) async {

        await resources.update(
            snapshot
        )

        await events.publish(
            .thermalChange(
                snapshot.thermal
            )
        )

        await events.publish(
            .powerChange(
                snapshot.power
            )

        )

        await events.publish(
            .resourcePressure(
                snapshot.memory.pressure
            )
        )
    }

    func captureDiagnostics()
        async {

        let resourceSnapshot =
            await resources.currentSnapshot()

        let allProcesses =
            await processes.allProcesses()

        let running =
            allProcesses.filter {
                $0.state == .running
            }

        let definitions =
            await services.allDefinitions()

        let snapshot =
            SystemDiagnosticsSnapshot(
                timestamp:
                    Date(),
                lifecycle:
                    lifecycle,
                resources:
                    resourceSnapshot,
                processCount:
                    allProcesses.count,
                runningProcessCount:
                    running.count,
                serviceCount:
                    definitions.count
            )

        await diagnostics.record(
            snapshot
        )
    }
}

// MARK: - Example Service

struct TelemetrySystemService:
    SystemService
{

    let definition =
        SystemServiceDefinition(
            id:
                SystemServiceID(
                    "telemetry"
                ),
            name:
                "Industrial Telemetry",
            dependencies: [],
            priority:
                .high
        )

    func start() async throws {

        SystemCoreLog.core.info(
            "Telemetry service started"
        )
    }

    func stop() async {

        SystemCoreLog.core.info(
            "Telemetry service stopped"
        )
    }
}

struct OptimisationSystemService:
    SystemService
{

    let definition =
        SystemServiceDefinition(
            id:
                SystemServiceID(
                    "optimisation"
                ),
            name:
                "Industrial Optimisation",
            dependencies: [
                SystemServiceID(
                    "telemetry"
                )
            ],
            priority:
                .critical
        )

    func start() async throws {

        SystemCoreLog.core.info(
            "Optimisation service started"
        )
    }

    func stop() async {

        SystemCoreLog.core.info(
            "Optimisation service stopped"
        )
    }
}



import Foundation

@main
struct IndustrialSystemExample {

    static func main() async {

        let system =
            SwiftSystemCore()

        do {

            try await system.services.register(
                TelemetrySystemService()
            )

            try await system.services.register(
                OptimisationSystemService()
            )

            try await system.boot()

            // Create a managed industrial process.
            let process =
                await system.processes.create(
                    name:
                        "Hydrogen Plant Controller",
                    priority:
                        .critical
                )

            try await system.processes.start(
                process
            )

            // Acquire system resources.
            let lease =
                try await system.resources.acquire(
                    process:
                        process,
                    request:
                        ResourceRequest(
                            cpuFraction:
                                0.25,
                            memoryBytes:
                                256 * 1024 * 1024,
                            priority:
                                .critical
                        )
                )

            print(
                "Resource lease:",
                lease.id.rawValue
            )

            // Schedule high-priority control work.
            await system.scheduler.submit(
                name:
                    "Industrial Control Cycle",
                priority:
                    .critical
            ) {

                print(
                    "Executing control cycle"
                )
            }

            // Capture diagnostics.
            await system.captureDiagnostics()

            if let diagnostics =
                await system.diagnostics.latest()
            {

                print(
                    "System state:",
                    diagnostics.lifecycle
                )

                print(
                    "Processes:",
                    diagnostics.processCount
                )

                print(
                    "Running:",
                    diagnostics.runningProcessCount
                )
            }

            await system.resources.release(
                lease.id
            )

            await system.shutdown()

        } catch {

            print(
                "System failure:",
                error
            )
        }
    }
}




//
//  SwiftAutonomy.swift
//
//  Swift 6
//  Public-API application-level autonomy framework
//

import Foundation
import os

// MARK: - Logging

private let autonomyLog = Logger(
    subsystem: "SwiftAutonomy",
    category: "Runtime"
)

// MARK: - Errors

public enum AutonomyError: Error, Sendable, CustomStringConvertible {
    case notStarted
    case alreadyStarted
    case invalidConfiguration(String)
    case invalidSensorData(String)
    case stateUnavailable
    case planningFailed(String)
    case noSafeAction
    case actionRejected(String)
    case actuatorFailure(String)
    case emergencyStop
    case timeout
    case dependencyFailure(String)

    public var description: String {
        switch self {
        case .notStarted:
            return "Autonomy runtime is not started."
        case .alreadyStarted:
            return "Autonomy runtime is already started."
        case .invalidConfiguration(let message):
            return "Invalid configuration: \(message)"
        case .invalidSensorData(let message):
            return "Invalid sensor data: \(message)"
        case .stateUnavailable:
            return "Autonomous state is unavailable."
        case .planningFailed(let message):
            return "Planning failed: \(message)"
        case .noSafeAction:
            return "No safe action was available."
        case .actionRejected(let message):
            return "Action rejected: \(message)"
        case .actuatorFailure(let message):
            return "Actuator failure: \(message)"
        case .emergencyStop:
            return "Emergency stop active."
        case .timeout:
            return "Operation timed out."
        case .dependencyFailure(let message):
            return "Dependency failure: \(message)"
        }
    }
}

// MARK: - Identifiers

public struct AgentID: Hashable, Codable, Sendable {
    public let rawValue: UUID

    public init(rawValue: UUID = UUID()) {
        self.rawValue = rawValue
    }
}

public struct SensorID: Hashable, Codable, Sendable {
    public let rawValue: String

    public init(_ rawValue: String) {
        self.rawValue = rawValue
    }
}

public struct ObservationID: Hashable, Codable, Sendable {
    public let rawValue: UUID

    public init(rawValue: UUID = UUID()) {
        self.rawValue = rawValue
    }
}

public struct WorldObjectID: Hashable, Codable, Sendable {
    public let rawValue: UUID

    public init(rawValue: UUID = UUID()) {
        self.rawValue = rawValue
    }
}

public struct PlanID: Hashable, Codable, Sendable {
    public let rawValue: UUID

    public init(rawValue: UUID = UUID()) {
        self.rawValue = rawValue
    }
}

public struct ActionID: Hashable, Codable, Sendable {
    public let rawValue: UUID

    public init(rawValue: UUID = UUID()) {
        self.rawValue = rawValue
    }
}

// MARK: - Geometry

public struct Vector2: Codable, Hashable, Sendable {
    public var x: Double
    public var y: Double

    public init(x: Double, y: Double) {
        self.x = x
        self.y = y
    }

    public static let zero = Vector2(x: 0, y: 0)

    public var magnitude: Double {
        sqrt(x * x + y * y)
    }

    public var squaredMagnitude: Double {
        x * x + y * y
    }

    public func distance(to other: Vector2) -> Double {
        (self - other).magnitude
    }

    public func normalized() -> Vector2 {
        let length = magnitude

        guard length > 1e-12 else {
            return .zero
        }

        return Vector2(
            x: x / length,
            y: y / length
        )
    }

    public func dot(_ other: Vector2) -> Double {
        x * other.x + y * other.y
    }

    public func clampedMagnitude(
        maximum: Double
    ) -> Vector2 {
        guard maximum >= 0 else {
            return .zero
        }

        if magnitude <= maximum {
            return self
        }

        return normalized() * maximum
    }
}

public func + (lhs: Vector2, rhs: Vector2) -> Vector2 {
    Vector2(
        x: lhs.x + rhs.x,
        y: lhs.y + rhs.y
    )
}

public func - (lhs: Vector2, rhs: Vector2) -> Vector2 {
    Vector2(
        x: lhs.x - rhs.x,
        y: lhs.y - rhs.y
    )
}

public func * (lhs: Vector2, rhs: Double) -> Vector2 {
    Vector2(
        x: lhs.x * rhs,
        y: lhs.y * rhs
    )
}

public func * (lhs: Double, rhs: Vector2) -> Vector2 {
    rhs * lhs
}

public func / (lhs: Vector2, rhs: Double) -> Vector2 {
    guard abs(rhs) > 1e-12 else {
        return .zero
    }

    return Vector2(
        x: lhs.x / rhs,
        y: lhs.y / rhs
    )
}

// MARK: - Pose

public struct Pose2D: Codable, Hashable, Sendable {
    public var position: Vector2
    public var headingRadians: Double

    public init(
        position: Vector2,
        headingRadians: Double
    ) {
        self.position = position
        self.headingRadians = headingRadians
    }

    public static let origin = Pose2D(
        position: .zero,
        headingRadians: 0
    )

    public func translated(
        by velocity: Vector2,
        deltaTime: Double
    ) -> Pose2D {
        Pose2D(
            position: position + velocity * deltaTime,
            headingRadians: headingRadians
        )
    }
}

// MARK: - Motion State

public struct MotionState: Codable, Hashable, Sendable {
    public var pose: Pose2D
    public var velocity: Vector2
    public var acceleration: Vector2
    public var angularVelocity: Double

    public init(
        pose: Pose2D,
        velocity: Vector2 = .zero,
        acceleration: Vector2 = .zero,
        angularVelocity: Double = 0
    ) {
        self.pose = pose
        self.velocity = velocity
        self.acceleration = acceleration
        self.angularVelocity = angularVelocity
    }

    public static let stationary = MotionState(
        pose: .origin
    )

    public var speed: Double {
        velocity.magnitude
    }
}

// MARK: - Time

public protocol AutonomyClock: Sendable {
    func now() -> ContinuousClock.Instant
}

public struct DefaultAutonomyClock: AutonomyClock {
    private let clock = ContinuousClock()

    public init() {}

    public func now() -> ContinuousClock.Instant {
        clock.now
    }
}

// MARK: - Sensor Model

public enum SensorKind: String, Codable, Sendable {
    case lidar
    case radar
    case camera
    case imu
    case gps
    case wheelEncoder
    case ultrasonic
    case temperature
    case pressure
    case proximity
    case custom
}

public struct SensorMetadata: Codable, Sendable {
    public let id: SensorID
    public let kind: SensorKind
    public let updateRateHz: Double
    public let maximumLatency: Duration

    public init(
        id: SensorID,
        kind: SensorKind,
        updateRateHz: Double,
        maximumLatency: Duration
    ) {
        self.id = id
        self.kind = kind
        self.updateRateHz = updateRateHz
        self.maximumLatency = maximumLatency
    }
}

// MARK: - Observation

public enum ObservationPayload: Codable, Sendable {
    case scalar(Double)
    case vector(Vector2)
    case pose(Pose2D)
    case motion(MotionState)
    case object(WorldObjectID, Vector2)
    case objects([WorldObjectID: Vector2])
    case boolean(Bool)
}

public struct Observation: Codable, Sendable {
    public let id: ObservationID
    public let sensor: SensorMetadata
    public let timestamp: ContinuousClock.Instant
    public let payload: ObservationPayload
    public let confidence: Double

    public init(
        id: ObservationID = ObservationID(),
        sensor: SensorMetadata,
        timestamp: ContinuousClock.Instant,
        payload: ObservationPayload,
        confidence: Double
    ) {
        self.id = id
        self.sensor = sensor
        self.timestamp = timestamp
        self.payload = payload
        self.confidence = min(
            max(confidence, 0),
            1
        )
    }
}

// MARK: - World Objects

public enum WorldObjectType: String, Codable, Sendable {
    case vehicle
    case pedestrian
    case robot
    case obstacle
    case building
    case machine
    case railVehicle
    case unknown
}

public struct WorldObject: Codable, Sendable {
    public let id: WorldObjectID
    public var type: WorldObjectType
    public var position: Vector2
    public var velocity: Vector2
    public var confidence: Double
    public var lastSeen: ContinuousClock.Instant

    public init(
        id: WorldObjectID = WorldObjectID(),
        type: WorldObjectType,
        position: Vector2,
        velocity: Vector2 = .zero,
        confidence: Double,
        lastSeen: ContinuousClock.Instant
    ) {
        self.id = id
        self.type = type
        self.position = position
        self.velocity = velocity
        self.confidence = confidence
        self.lastSeen = lastSeen
    }

    public func predictedPosition(
        after deltaTime: Double
    ) -> Vector2 {
        position + velocity * deltaTime
    }
}

// MARK: - World Model

public struct WorldModel: Sendable {
    public var timestamp: ContinuousClock.Instant
    public var selfState: MotionState
    public var objects: [WorldObjectID: WorldObject]
    public var freeSpace: [Vector2]
    public var confidence: Double

    public init(
        timestamp: ContinuousClock.Instant,
        selfState: MotionState,
        objects: [WorldObjectID: WorldObject] = [:],
        freeSpace: [Vector2] = [],
        confidence: Double = 1
    ) {
        self.timestamp = timestamp
        self.selfState = selfState
        self.objects = objects
        self.freeSpace = freeSpace
        self.confidence = confidence
    }

    public func nearestObject(
        to position: Vector2
    ) -> WorldObject? {
        objects.values.min {
            $0.position.distance(to: position) <
            $1.position.distance(to: position)
        }
    }
}

// MARK: - Perception

public protocol PerceptionProcessor: Sendable {
    func process(
        observations: [Observation],
        timestamp: ContinuousClock.Instant
    ) async throws -> WorldModel
}

// MARK: - Basic Perception Processor

public actor BasicPerceptionProcessor: PerceptionProcessor {

    private var currentState = MotionState.stationary
    private var objects: [WorldObjectID: WorldObject] = [:]

    public init() {}

    public func process(
        observations: [Observation],
        timestamp: ContinuousClock.Instant
    ) async throws -> WorldModel {

        for observation in observations {
            switch observation.payload {

            case .motion(let motion):
                currentState = motion

            case .pose(let pose):
                currentState.pose = pose

            case .object(let id, let position):
                objects[id] = WorldObject(
                    id: id,
                    type: .unknown,
                    position: position,
                    confidence: observation.confidence,
                    lastSeen: timestamp
                )

            case .objects(let positions):
                for (id, position) in positions {
                    objects[id] = WorldObject(
                        id: id,
                        type: .unknown,
                        position: position,
                        confidence: observation.confidence,
                        lastSeen: timestamp
                    )
                }

            default:
                break
            }
        }

        return WorldModel(
            timestamp: timestamp,
            selfState: currentState,
            objects: objects,
            confidence: calculateConfidence(
                observations: observations
            )
        )
    }

    private func calculateConfidence(
        observations: [Observation]
    ) -> Double {

        guard !observations.isEmpty else {
            return 0
        }

        let total = observations.reduce(
            0
        ) {
            $0 + $1.confidence
        }

        return total / Double(observations.count)
    }
}

// MARK: - State Estimation

public protocol StateEstimator: Sendable {
    func estimate(
        world: WorldModel,
        deltaTime: Double
    ) async throws -> MotionState
}

// MARK: - Alpha-Beta State Estimator

public actor AlphaBetaStateEstimator: StateEstimator {

    private var previousState: MotionState?

    private let alpha: Double
    private let beta: Double

    public init(
        alpha: Double = 0.85,
        beta: Double = 0.20
    ) {
        self.alpha = min(max(alpha, 0), 1)
        self.beta = min(max(beta, 0), 1)
    }

    public func estimate(
        world: WorldModel,
        deltaTime: Double
    ) async throws -> MotionState {

        guard deltaTime > 0 else {
            previousState = world.selfState
            return world.selfState
        }

        guard let previousState else {
            self.previousState = world.selfState
            return world.selfState
        }

        let predictedPosition =
            previousState.pose.position +
            previousState.velocity * deltaTime

        let residual =
            world.selfState.pose.position -
            predictedPosition

        let correctedPosition =
            predictedPosition +
            residual * alpha

        let correctedVelocity =
            previousState.velocity +
            residual * (beta / deltaTime)

        let result = MotionState(
            pose: Pose2D(
                position: correctedPosition,
                headingRadians:
                    world.selfState.pose.headingRadians
            ),
            velocity: correctedVelocity,
            acceleration: world.selfState.acceleration,
            angularVelocity:
                world.selfState.angularVelocity
        )

        self.previousState = result

        return result
    }
}

// MARK: - Autonomy State

public enum AutonomyMode: String, Codable, Sendable {
    case disabled
    case standby
    case supervised
    case autonomous
    case degraded
    case emergency
}

public struct AutonomyState: Sendable {
    public var mode: AutonomyMode
    public var motion: MotionState
    public var world: WorldModel?
    public var confidence: Double
    public var timestamp: ContinuousClock.Instant

    public init(
        mode: AutonomyMode,
        motion: MotionState,
        world: WorldModel?,
        confidence: Double,
        timestamp: ContinuousClock.Instant
    ) {
        self.mode = mode
        self.motion = motion
        self.world = world
        self.confidence = confidence
        self.timestamp = timestamp
    }
}

// MARK: - Goals

public enum AutonomyGoal: Sendable {
    case holdPosition(Vector2)
    case moveTo(Vector2)
    case follow(WorldObjectID, distance: Double)
    case patrol([Vector2])
    case stop
    case dock(Vector2)
    case custom(String)
}

// MARK: - Action

public enum ActionType: String, Codable, Sendable {
    case accelerate
    case decelerate
    case steer
    case stop
    case hold
    case dock
    case wait
}

public struct ActionCommand: Sendable {
    public let id: ActionID
    public let type: ActionType
    public let linearVelocity: Vector2
    public let angularVelocity: Double
    public let duration: Double
    public let issuedAt: ContinuousClock.Instant

    public init(
        id: ActionID = ActionID(),
        type: ActionType,
        linearVelocity: Vector2 = .zero,
        angularVelocity: Double = 0,
        duration: Double,
        issuedAt: ContinuousClock.Instant
    ) {
        self.id = id
        self.type = type
        self.linearVelocity = linearVelocity
        self.angularVelocity = angularVelocity
        self.duration = max(duration, 0)
        self.issuedAt = issuedAt
    }

    public static func stop(
        now: ContinuousClock.Instant
    ) -> ActionCommand {
        ActionCommand(
            type: .stop,
            duration: 0,
            issuedAt: now
        )
    }
}

// MARK: - Planning

public struct TrajectoryPoint: Sendable {
    public let time: Double
    public let position: Vector2
    public let velocity: Vector2

    public init(
        time: Double,
        position: Vector2,
        velocity: Vector2
    ) {
        self.time = time
        self.position = position
        self.velocity = velocity
    }
}

public struct Trajectory: Sendable {
    public let points: [TrajectoryPoint]

    public init(points: [TrajectoryPoint]) {
        self.points = points
    }

    public var duration: Double {
        points.last?.time ?? 0
    }
}

public struct Plan: Sendable {
    public let id: PlanID
    public let goal: AutonomyGoal
    public let trajectory: Trajectory
    public let cost: Double
    public let confidence: Double

    public init(
        id: PlanID = PlanID(),
        goal: AutonomyGoal,
        trajectory: Trajectory,
        cost: Double,
        confidence: Double
    ) {
        self.id = id
        self.goal = goal
        self.trajectory = trajectory
        self.cost = cost
        self.confidence = confidence
    }
}

public protocol TrajectoryPlanner: Sendable {
    func plan(
        from state: AutonomyState,
        toward goal: AutonomyGoal
    ) async throws -> Plan
}

// MARK: - Direct Trajectory Planner

public actor DirectTrajectoryPlanner: TrajectoryPlanner {

    public struct Configuration: Sendable {
        public let horizon: Double
        public let step: Double
        public let maximumSpeed: Double

        public init(
            horizon: Double = 5,
            step: Double = 0.1,
            maximumSpeed: Double = 5
        ) {
            self.horizon = horizon
            self.step = step
            self.maximumSpeed = maximumSpeed
        }
    }

    private let configuration: Configuration

    public init(
        configuration: Configuration = Configuration()
    ) {
        self.configuration = configuration
    }

    public func plan(
        from state: AutonomyState,
        toward goal: AutonomyGoal
    ) async throws -> Plan {

        guard configuration.horizon > 0 else {
            throw AutonomyError.planningFailed(
                "Planning horizon must be positive."
            )
        }

        switch goal {

        case .moveTo(let target),
             .dock(let target),
             .holdPosition(let target):

            return try buildPointPlan(
                state: state,
                target: target,
                goal: goal
            )

        case .stop:

            let point = TrajectoryPoint(
                time: 0,
                position: state.motion.pose.position,
                velocity: .zero
            )

            return Plan(
                goal: goal,
                trajectory: Trajectory(
                    points: [point]
                ),
                cost: 0,
                confidence: 1
            )

        case .follow(let objectID, let distance):

            guard
                let world = state.world,
                let object = world.objects[objectID]
            else {
                throw AutonomyError.planningFailed(
                    "Follow target unavailable."
                )
            }

            let target =
                object.position -
                object.velocity.normalized() * distance

            return try buildPointPlan(
                state: state,
                target: target,
                goal: goal
            )

        case .patrol(let waypoints):

            guard !waypoints.isEmpty else {
                throw AutonomyError.planningFailed(
                    "Patrol route contains no waypoints."
                )
            }

            let first = waypoints[0]

            return try buildPointPlan(
                state: state,
                target: first,
                goal: goal
            )

        case .custom(let name):

            throw AutonomyError.planningFailed(
                "No planner registered for custom goal '\(name)'."
            )
        }
    }

    private func buildPointPlan(
        state: AutonomyState,
        target: Vector2,
        goal: AutonomyGoal
    ) throws -> Plan {

        let start = state.motion.pose.position
        let displacement = target - start
        let distance = displacement.magnitude

        if distance < 0.001 {
            return Plan(
                goal: goal,
                trajectory: Trajectory(
                    points: [
                        TrajectoryPoint(
                            time: 0,
                            position: start,
                            velocity: .zero
                        )
                    ]
                ),
                cost: 0,
                confidence: 1
            )
        }

        let direction = displacement.normalized()

        let speed = min(
            configuration.maximumSpeed,
            max(
                state.motion.speed,
                configuration.maximumSpeed * 0.5
            )
        )

        let duration = max(
            distance / speed,
            configuration.step
        )

        var points: [TrajectoryPoint] = []

        var time = 0.0

        while time < duration {
            let ratio = min(
                time / duration,
                1
            )

            let position =
                start +
                displacement * ratio

            points.append(
                TrajectoryPoint(
                    time: time,
                    position: position,
                    velocity: direction * speed
                )
            )

            time += configuration.step
        }

        points.append(
            TrajectoryPoint(
                time: duration,
                position: target,
                velocity: .zero
            )
        )

        return Plan(
            goal: goal,
            trajectory: Trajectory(
                points: points
            ),
            cost: distance,
            confidence: 0.95
        )
    }
}

// MARK: - Safety

public enum SafetyLevel: Int, Codable, Comparable, Sendable {
    case normal = 0
    case caution = 1
    case restricted = 2
    case emergency = 3
}

public struct SafetyEnvelope: Sendable {
    public let maximumSpeed: Double
    public let maximumAcceleration: Double
    public let minimumObstacleDistance: Double
    public let maximumPlanningAge: Double

    public init(
        maximumSpeed: Double,
        maximumAcceleration: Double,
        minimumObstacleDistance: Double,
        maximumPlanningAge: Double
    ) {
        self.maximumSpeed = max(maximumSpeed, 0)
        self.maximumAcceleration = max(maximumAcceleration, 0)
        self.minimumObstacleDistance =
            max(minimumObstacleDistance, 0)
        self.maximumPlanningAge =
            max(maximumPlanningAge, 0)
    }
}

public struct SafetyAssessment: Sendable {
    public let level: SafetyLevel
    public let approved: Bool
    public let reasons: [String]

    public init(
        level: SafetyLevel,
        approved: Bool,
        reasons: [String]
    ) {
        self.level = level
        self.approved = approved
        self.reasons = reasons
    }
}

public protocol SafetySupervisor: Sendable {
    func assess(
        state: AutonomyState,
        plan: Plan
    ) async -> SafetyAssessment
}

// MARK: - Safety Supervisor

public actor DefaultSafetySupervisor: SafetySupervisor {

    private let envelope: SafetyEnvelope

    public init(
        envelope: SafetyEnvelope
    ) {
        self.envelope = envelope
    }

    public func assess(
        state: AutonomyState,
        plan: Plan
    ) async -> SafetyAssessment {

        var reasons: [String] = []
        var level: SafetyLevel = .normal

        guard state.mode != .emergency else {
            return SafetyAssessment(
                level: .emergency,
                approved: false,
                reasons: ["Autonomy is in emergency mode."]
            )
        }

        if state.confidence < 0.40 {
            level = max(
                level,
                .restricted
            )

            reasons.append(
                "State confidence is below safe threshold."
            )
        }

        if plan.confidence < 0.50 {
            level = max(
                level,
                .restricted
            )

            reasons.append(
                "Plan confidence is below safe threshold."
            )
        }

        for point in plan.trajectory.points {

            if point.velocity.magnitude >
                envelope.maximumSpeed {

                return SafetyAssessment(
                    level: .emergency,
                    approved: false,
                    reasons: [
                        "Trajectory exceeds maximum speed."
                    ]
                )
            }

            if let world = state.world {
                for object in world.objects.values {

                    let distance =
                        point.position.distance(
                            to: object.position
                        )

                    if distance <
                        envelope.minimumObstacleDistance {

                        return SafetyAssessment(
                            level: .emergency,
                            approved: false,
                            reasons: [
                                "Trajectory enters obstacle envelope."
                            ]
                        )
                    }
                }
            }
        }

        if state.motion.speed >
            envelope.maximumSpeed {

            level = max(
                level,
                .caution
            )

            reasons.append(
                "Current speed is above preferred operating speed."
            )
        }

        return SafetyAssessment(
            level: level,
            approved: level < .emergency,
            reasons: reasons
        )
    }
}

// MARK: - Actuator Interface

public protocol ActuatorInterface: Sendable {
    func execute(
        _ command: ActionCommand
    ) async throws
}

// MARK: - Simulated Actuator

public actor SimulatedActuator: ActuatorInterface {

    private var lastCommand: ActionCommand?

    public init() {}

    public func execute(
        _ command: ActionCommand
    ) async throws {

        if command.type == .stop {
            autonomyLog.notice(
                "Simulated actuator STOP command received."
            )
        }

        lastCommand = command
    }

    public func latestCommand() -> ActionCommand? {
        lastCommand
    }
}

// MARK: - Action Generator

public protocol ActionGenerator: Sendable {
    func action(
        for plan: Plan,
        state: AutonomyState,
        now: ContinuousClock.Instant
    ) async throws -> ActionCommand
}

public actor DefaultActionGenerator: ActionGenerator {

    public init() {}

    public func action(
        for plan: Plan,
        state: AutonomyState,
        now: ContinuousClock.Instant
    ) async throws -> ActionCommand {

        guard
            let first = plan.trajectory.points.first
        else {
            throw AutonomyError.planningFailed(
                "Trajectory contains no points."
            )
        }

        let desiredVelocity = first.velocity
        let currentVelocity = state.motion.velocity

        let delta =
            desiredVelocity -
            currentVelocity

        let actionType: ActionType

        if desiredVelocity.magnitude < 0.001 {
            actionType = .stop
        } else if delta.magnitude > 0.05 {
            actionType = .accelerate
        } else {
            actionType = .hold
        }

        return ActionCommand(
            type: actionType,
            linearVelocity: desiredVelocity,
            angularVelocity:
                state.motion.angularVelocity,
            duration: max(
                first.time,
                0.05
            ),
            issuedAt: now
        )
    }
}

// MARK: - Emergency Stop

public actor EmergencyStopController {

    private var engaged = false
    private var reason: String?

    public init() {}

    public func engage(
        reason: String
    ) {
        engaged = true
        self.reason = reason

        autonomyLog.error(
            "Emergency stop engaged: \(reason)"
        )
    }

    public func reset() {
        engaged = false
        reason = nil
    }

    public func isEngaged() -> Bool {
        engaged
    }

    public func currentReason() -> String? {
        reason
    }
}

// MARK: - Observation Buffer

public actor ObservationBuffer {

    private var observations: [Observation] = []
    private let maximumCount: Int

    public init(
        maximumCount: Int = 10_000
    ) {
        self.maximumCount = max(
            maximumCount,
            1
        )
    }

    public func append(
        _ observation: Observation
    ) {
        observations.append(observation)

        if observations.count > maximumCount {
            observations.removeFirst(
                observations.count - maximumCount
            )
        }
    }

    public func append(
        contentsOf values: [Observation]
    ) {
        observations.append(
            contentsOf: values
        )

        if observations.count > maximumCount {
            observations.removeFirst(
                observations.count - maximumCount
            )
        }
    }

    public func latest(
        limit: Int
    ) -> [Observation] {
        Array(
            observations.suffix(
                max(limit, 0)
            )
        )
    }

    public func clear() {
        observations.removeAll(
            keepingCapacity: true
        )
    }

    public func count() -> Int {
        observations.count
    }
}

// MARK: - Sensor Registry

public actor SensorRegistry {

    private var sensors: [SensorID: SensorMetadata] = [:]

    public init() {}

    public func register(
        _ sensor: SensorMetadata
    ) {
        sensors[sensor.id] = sensor
    }

    public func unregister(
        _ id: SensorID
    ) {
        sensors.removeValue(
            forKey: id
        )
    }

    public func sensor(
        _ id: SensorID
    ) -> SensorMetadata? {
        sensors[id]
    }

    public func allSensors() -> [SensorMetadata] {
        Array(
            sensors.values
        )
    }
}

// MARK: - Goal Manager

public actor GoalManager {

    private var currentGoal: AutonomyGoal?

    public init() {}

    public func setGoal(
        _ goal: AutonomyGoal
    ) {
        currentGoal = goal
    }

    public func clearGoal() {
        currentGoal = nil
    }

    public func goal() -> AutonomyGoal? {
        currentGoal
    }
}

// MARK: - Decision Engine

public protocol DecisionEngine: Sendable {
    func chooseGoal(
        state: AutonomyState
    ) async throws -> AutonomyGoal
}

public actor DefaultDecisionEngine: DecisionEngine {

    private let goalManager: GoalManager

    public init(
        goalManager: GoalManager
    ) {
        self.goalManager = goalManager
    }

    public func chooseGoal(
        state: AutonomyState
    ) async throws -> AutonomyGoal {

        if state.mode == .emergency {
            return .stop
        }

        if let configuredGoal =
            await goalManager.goal() {
            return configuredGoal
        }

        return .holdPosition(
            state.motion.pose.position
        )
    }
}

// MARK: - Autonomy Diagnostics

public struct AutonomyCycleMetrics: Sendable {
    public let cycleNumber: UInt64
    public let observationCount: Int
    public let planningDuration: Duration
    public let totalCycleDuration: Duration
    public let stateConfidence: Double
    public let planConfidence: Double
    public let safetyLevel: SafetyLevel
    public let actionExecuted: Bool

    public init(
        cycleNumber: UInt64,
        observationCount: Int,
        planningDuration: Duration,
        totalCycleDuration: Duration,
        stateConfidence: Double,
        planConfidence: Double,
        safetyLevel: SafetyLevel,
        actionExecuted: Bool
    ) {
        self.cycleNumber = cycleNumber
        self.observationCount = observationCount
        self.planningDuration = planningDuration
        self.totalCycleDuration = totalCycleDuration
        self.stateConfidence = stateConfidence
        self.planConfidence = planConfidence
        self.safetyLevel = safetyLevel
        self.actionExecuted = actionExecuted
    }
}

public struct AutonomyDiagnostics: Sendable {
    public let cycles: UInt64
    public let successfulActions: UInt64
    public let rejectedActions: UInt64
    public let planningFailures: UInt64
    public let emergencyStops: UInt64
    public let latestMetrics: AutonomyCycleMetrics?

    public init(
        cycles: UInt64,
        successfulActions: UInt64,
        rejectedActions: UInt64,
        planningFailures: UInt64,
        emergencyStops: UInt64,
        latestMetrics: AutonomyCycleMetrics?
    ) {
        self.cycles = cycles
        self.successfulActions = successfulActions
        self.rejectedActions = rejectedActions
        self.planningFailures = planningFailures
        self.emergencyStops = emergencyStops
        self.latestMetrics = latestMetrics
    }
}

public actor AutonomyDiagnosticsEngine {

    private var cycles: UInt64 = 0
    private var successfulActions: UInt64 = 0
    private var rejectedActions: UInt64 = 0
    private var planningFailures: UInt64 = 0
    private var emergencyStops: UInt64 = 0

    private var latestMetrics: AutonomyCycleMetrics?

    public init() {}

    public func recordCycle(
        _ metrics: AutonomyCycleMetrics
    ) {
        cycles += 1

        if metrics.actionExecuted {
            successfulActions += 1
        }

        latestMetrics = metrics
    }

    public func recordRejectedAction() {
        rejectedActions += 1
    }

    public func recordPlanningFailure() {
        planningFailures += 1
    }

    public func recordEmergencyStop() {
        emergencyStops += 1
    }

    public func snapshot() -> AutonomyDiagnostics {
        AutonomyDiagnostics(
            cycles: cycles,
            successfulActions: successfulActions,
            rejectedActions: rejectedActions,
            planningFailures: planningFailures,
            emergencyStops: emergencyStops,
            latestMetrics: latestMetrics
        )
    }
}

// MARK: - Runtime Configuration

public struct AutonomyConfiguration: Sendable {

    public let controlFrequencyHz: Double
    public let minimumConfidence: Double
    public let maximumObservationAge: Duration
    public let allowAutonomousMode: Bool

    public init(
        controlFrequencyHz: Double = 20,
        minimumConfidence: Double = 0.50,
        maximumObservationAge: Duration = .milliseconds(250),
        allowAutonomousMode: Bool = true
    ) throws {

        guard controlFrequencyHz > 0 else {
            throw AutonomyError.invalidConfiguration(
                "Control frequency must be greater than zero."
            )
        }

        guard
            minimumConfidence >= 0,
            minimumConfidence <= 1
        else {
            throw AutonomyError.invalidConfiguration(
                "Minimum confidence must be between 0 and 1."
            )
        }

        self.controlFrequencyHz = controlFrequencyHz
        self.minimumConfidence = minimumConfidence
        self.maximumObservationAge =
            maximumObservationAge
        self.allowAutonomousMode =
            allowAutonomousMode
    }

    public static var `default`: AutonomyConfiguration {
        try! AutonomyConfiguration()
    }
}

// MARK: - Autonomy Runtime

public actor SwiftAutonomy {

    private let agentID: AgentID
    private let configuration: AutonomyConfiguration
    private let clock: AutonomyClock

    private let perception: PerceptionProcessor
    private let estimator: StateEstimator
    private let decision: DecisionEngine
    private let planner: TrajectoryPlanner
    private let safety: SafetySupervisor
    private let actions: ActionGenerator
    private let actuator: ActuatorInterface

    private let observationBuffer: ObservationBuffer
    private let diagnostics: AutonomyDiagnosticsEngine
    private let emergencyStop: EmergencyStopController

    private var running = false
    private var mode: AutonomyMode = .disabled
    private var cycleNumber: UInt64 = 0

    private var latestState: AutonomyState?

    private var controlTask: Task<Void, Never>?

    public init(
        agentID: AgentID = AgentID(),
        configuration: AutonomyConfiguration = .default,
        clock: AutonomyClock = DefaultAutonomyClock(),
        perception: PerceptionProcessor,
        estimator: StateEstimator,
        decision: DecisionEngine,
        planner: TrajectoryPlanner,
        safety: SafetySupervisor,
        actions: ActionGenerator,
        actuator: ActuatorInterface,
        observationBuffer: ObservationBuffer =
            ObservationBuffer(),
        diagnostics: AutonomyDiagnosticsEngine =
            AutonomyDiagnosticsEngine(),
        emergencyStop: EmergencyStopController =
            EmergencyStopController()
    ) {
        self.agentID = agentID
        self.configuration = configuration
        self.clock = clock
        self.perception = perception
        self.estimator = estimator
        self.decision = decision
        self.planner = planner
        self.safety = safety
        self.actions = actions
        self.actuator = actuator
        self.observationBuffer = observationBuffer
        self.diagnostics = diagnostics
        self.emergencyStop = emergencyStop
    }

    // MARK: Lifecycle

    public func start() async throws {

        guard !running else {
            throw AutonomyError.alreadyStarted
        }

        running = true

        if configuration.allowAutonomousMode {
            mode = .autonomous
        } else {
            mode = .supervised
        }

        autonomyLog.notice(
            "SwiftAutonomy started for agent \(self.agentID.rawValue.uuidString)"
        )
    }

    public func stop() async {

        running = false
        mode = .disabled

        controlTask?.cancel()
        controlTask = nil

        autonomyLog.notice(
            "SwiftAutonomy stopped."
        )
    }

    public func setMode(
        _ newMode: AutonomyMode
    ) async {

        if newMode == .autonomous &&
            !configuration.allowAutonomousMode {
            mode = .supervised
            return
        }

        mode = newMode
    }

    public func currentMode() -> AutonomyMode {
        mode
    }

    public func isRunning() -> Bool {
        running
    }

    // MARK: Observation Ingestion

    public func ingest(
        _ observation: Observation
    ) async throws {

        guard running else {
            throw AutonomyError.notStarted
        }

        guard observation.confidence >= 0 else {
            throw AutonomyError.invalidSensorData(
                "Observation confidence is invalid."
            )
        }

        await observationBuffer.append(
            observation
        )
    }

    public func ingest(
        _ observations: [Observation]
    ) async throws {

        guard running else {
            throw AutonomyError.notStarted
        }

        await observationBuffer.append(
            contentsOf: observations
        )
    }

    // MARK: Control Cycle

    public func runCycle() async throws {

        guard running else {
            throw AutonomyError.notStarted
        }

        cycleNumber += 1

        let cycleStart = clock.now()

        if await emergencyStop.isEngaged() {
            mode = .emergency

            await diagnostics.recordEmergencyStop()

            throw AutonomyError.emergencyStop
        }

        let observations =
            await observationBuffer.latest(
                limit: 512
            )

        let now = clock.now()

        let world = try await perception.process(
            observations: observations,
            timestamp: now
        )

        let previousMotion =
            latestState?.motion ??
            world.selfState

        let deltaTime = estimateDeltaTime(
            current: now,
            previous: latestState?.timestamp
        )

        let estimatedMotion =
            try await estimator.estimate(
                world: world,
                deltaTime: deltaTime
            )

        let state = AutonomyState(
            mode: mode,
            motion: estimatedMotion,
            world: world,
            confidence: world.confidence,
            timestamp: now
        )

        latestState = state

        if state.confidence <
            configuration.minimumConfidence {

            mode = .degraded

            let stopCommand =
                ActionCommand.stop(
                    now: now
                )

            try await actuator.execute(
                stopCommand
            )

            await diagnostics.recordRejectedAction()

            return
        }

        let goal = try await decision.chooseGoal(
            state: state
        )

        let planningStart = clock.now()

        let plan: Plan

        do {
            plan = try await planner.plan(
                from: state,
                toward: goal
            )
        } catch {
            await diagnostics.recordPlanningFailure()

            let stopCommand =
                ActionCommand.stop(
                    now: now
                )

            try await actuator.execute(
                stopCommand
            )

            throw error
        }

        let planningEnd = clock.now()

        let assessment =
            await safety.assess(
                state: state,
                plan: plan
            )

        guard assessment.approved else {

            await diagnostics.recordRejectedAction()

            let stopCommand =
                ActionCommand.stop(
                    now: now
                )

            try await actuator.execute(
                stopCommand
            )

            return
        }

        let command = try await actions.action(
            for: plan,
            state: state,
            now: now
        )

        do {
            try await actuator.execute(
                command
            )
        } catch {
            await emergencyStop.engage(
                reason:
                    "Actuator execution failed: \(error)"
            )

            await diagnostics.recordEmergencyStop()

            mode = .emergency

            throw AutonomyError.actuatorFailure(
                String(
                    describing: error
                )
            )
        }

        let cycleEnd = clock.now()

        let metrics = AutonomyCycleMetrics(
            cycleNumber: cycleNumber,
            observationCount: observations.count,
            planningDuration:
                planningStart.duration(
                    to: planningEnd
                ),
            totalCycleDuration:
                cycleStart.duration(
                    to: cycleEnd
                ),
            stateConfidence:
                state.confidence,
            planConfidence:
                plan.confidence,
            safetyLevel:
                assessment.level,
            actionExecuted: true
        )

        await diagnostics.recordCycle(
            metrics
        )

        _ = previousMotion
    }

    // MARK: Continuous Loop

    public func startControlLoop() {

        guard controlTask == nil else {
            return
        }

        let frequency =
            configuration.controlFrequencyHz

        let intervalNanoseconds =
            UInt64(
                1_000_000_000 / frequency
            )

        controlTask = Task { [weak self] in

            while !Task.isCancelled {

                guard let self else {
                    return
                }

                do {
                    try await self.runCycle()
                } catch {
                    autonomyLog.error(
                        "Autonomy cycle failed: \(String(describing: error))"
                    )
                }

                try? await Task.sleep(
                    nanoseconds:
                        intervalNanoseconds
                )
            }
        }
    }

    public func stopControlLoop() {

        controlTask?.cancel()
        controlTask = nil
    }

    // MARK: Emergency

    public func engageEmergencyStop(
        reason: String
    ) async {

        await emergencyStop.engage(
            reason: reason
        )

        mode = .emergency

        do {
            try await actuator.execute(
                ActionCommand.stop(
                    now: clock.now()
                )
            )
        } catch {
            autonomyLog.error(
                "Failed to issue emergency stop: \(String(describing: error))"
            )
        }
    }

    public func resetEmergencyStop() async {

        await emergencyStop.reset()

        guard running else {
            mode = .disabled
            return
        }

        mode = configuration.allowAutonomousMode
            ? .autonomous
            : .supervised
    }

    // MARK: State

    public func state() -> AutonomyState? {
        latestState
    }

    public func diagnosticsSnapshot()
        async -> AutonomyDiagnostics {

        await diagnostics.snapshot()
    }

    private func estimateDeltaTime(
        current: ContinuousClock.Instant,
        previous: ContinuousClock.Instant?
    ) -> Double {

        guard let previous else {
            return 1.0 /
                configuration.controlFrequencyHz
        }

        let duration =
            previous.duration(
                to: current
            )

        return max(
            duration.timeInterval,
            1e-6
        )
    }
}

// MARK: - Duration Conversion

private extension Duration {

    var timeInterval: Double {

        let components = self.components

        let seconds =
            Double(components.seconds)

        let attoseconds =
            Double(components.attoseconds)

        return seconds +
            attoseconds / 1e18
    }
}

// MARK: - Simple Sensor Factory

public enum SensorFactory {

    public static func motionSensor(
        id: String = "imu"
    ) -> SensorMetadata {

        SensorMetadata(
            id: SensorID(id),
            kind: .imu,
            updateRateHz: 100,
            maximumLatency: .milliseconds(20)
        )
    }

    public static func positionSensor(
        id: String = "gps"
    ) -> SensorMetadata {

        SensorMetadata(
            id: SensorID(id),
            kind: .gps,
            updateRateHz: 10,
            maximumLatency: .milliseconds(100)
        )
    }

    public static func lidar(
        id: String = "lidar"
    ) -> SensorMetadata {

        SensorMetadata(
            id: SensorID(id),
            kind: .lidar,
            updateRateHz: 20,
            maximumLatency: .milliseconds(50)
        )
    }
}

// MARK: - Autonomous Vehicle Model

public struct AutonomousVehicleState: Sendable {
    public let position: Vector2
    public let velocity: Vector2
    public let heading: Double
    public let batteryLevel: Double

    public init(
        position: Vector2,
        velocity: Vector2,
        heading: Double,
        batteryLevel: Double
    ) {
        self.position = position
        self.velocity = velocity
        self.heading = heading
        self.batteryLevel = batteryLevel
    }
}

// MARK: - Battery Safety

public actor BatterySafetySupervisor {

    private let minimumBatteryLevel: Double

    public init(
        minimumBatteryLevel: Double = 0.10
    ) {
        self.minimumBatteryLevel =
            min(
                max(minimumBatteryLevel, 0),
                1
            )
    }

    public func shouldContinue(
        batteryLevel: Double
    ) -> Bool {

        batteryLevel >= minimumBatteryLevel
    }
}

// MARK: - Obstacle Monitor

public struct ObstacleRisk: Sendable {
    public let objectID: WorldObjectID
    public let distance: Double
    public let closingSpeed: Double
    public let riskScore: Double

    public init(
        objectID: WorldObjectID,
        distance: Double,
        closingSpeed: Double,
        riskScore: Double
    ) {
        self.objectID = objectID
        self.distance = distance
        self.closingSpeed = closingSpeed
        self.riskScore = riskScore
    }
}

public actor ObstacleRiskAnalyzer {

    public init() {}

    public func analyze(
        world: WorldModel
    ) -> [ObstacleRisk] {

        let ownPosition =
            world.selfState.pose.position

        let ownVelocity =
            world.selfState.velocity

        return world.objects.values.map { object in

            let relative =
                object.position -
                ownPosition

            let distance =
                relative.magnitude

            let relativeVelocity =
                object.velocity -
                ownVelocity

            let closingSpeed =
                -relativeVelocity.dot(
                    relative.normalized()
                )

            let distanceRisk =
                1 / max(
                    distance,
                    0.1
                )

            let velocityRisk =
                max(
                    closingSpeed,
                    0
                )

            let score =
                distanceRisk *
                (1 + velocityRisk)

            return ObstacleRisk(
                objectID: object.id,
                distance: distance,
                closingSpeed: closingSpeed,
                riskScore: score
            )
        }
    }
}

// MARK: - Route

public struct RouteSegment: Sendable {
    public let start: Vector2
    public let end: Vector2
    public let maximumSpeed: Double

    public init(
        start: Vector2,
        end: Vector2,
        maximumSpeed: Double
    ) {
        self.start = start
        self.end = end
        self.maximumSpeed = maximumSpeed
    }

    public var length: Double {
        start.distance(
            to: end
        )
    }
}

public struct AutonomousRoute: Sendable {
    public let segments: [RouteSegment]

    public init(
        segments: [RouteSegment]
    ) {
        self.segments = segments
    }

    public var totalLength: Double {
        segments.reduce(
            0
        ) {
            $0 + $1.length
        }
    }
}

// MARK: - Route Planner

public actor RoutePlanner {

    public init() {}

    public func route(
        from start: Vector2,
        through waypoints: [Vector2],
        maximumSpeed: Double
    ) -> AutonomousRoute {

        var points = [start]
        points.append(contentsOf: waypoints)

        guard points.count >= 2 else {
            return AutonomousRoute(
                segments: []
            )
        }

        var segments: [RouteSegment] = []

        for index in 0..<(points.count - 1) {

            segments.append(
                RouteSegment(
                    start: points[index],
                    end: points[index + 1],
                    maximumSpeed: maximumSpeed
                )
            )
        }

        return AutonomousRoute(
            segments: segments
        )
    }
}

// MARK: - Mission

public enum MissionStatus: String, Sendable {
    case pending
    case active
    case paused
    case completed
    case aborted
}

public struct Mission: Sendable {
    public let id: UUID
    public let name: String
    public let goals: [AutonomyGoal]

    public init(
        id: UUID = UUID(),
        name: String,
        goals: [AutonomyGoal]
    ) {
        self.id = id
        self.name = name
        self.goals = goals
    }
}

public actor MissionController {

    private var mission: Mission?
    private var status: MissionStatus = .pending
    private var currentGoalIndex = 0

    private let goalManager: GoalManager

    public init(
        goalManager: GoalManager
    ) {
        self.goalManager = goalManager
    }

    public func load(
        mission: Mission
    ) {
        self.mission = mission
        status = .pending
        currentGoalIndex = 0
    }

    public func start() async throws {

        guard let mission else {
            throw AutonomyError.dependencyFailure(
                "No mission loaded."
            )
        }

        guard !mission.goals.isEmpty else {
            throw AutonomyError.dependencyFailure(
                "Mission contains no goals."
            )
        }

        status = .active
        currentGoalIndex = 0

        await goalManager.setGoal(
            mission.goals[0]
        )
    }

    public func advance() async {

        guard let mission else {
            return
        }

        currentGoalIndex += 1

        if currentGoalIndex >=
            mission.goals.count {

            status = .completed

            await goalManager.clearGoal()

            return
        }

        await goalManager.setGoal(
            mission.goals[
                currentGoalIndex
            ]
        )
    }

    public func pause() {
        status = .paused
    }

    public func abort() async {

        status = .aborted

        await goalManager.clearGoal()
    }

    public func currentStatus() -> MissionStatus {
        status
    }
}

// MARK: - Autonomy Event

public enum AutonomyEvent: Sendable {
    case started
    case stopped
    case observationReceived(ObservationID)
    case planGenerated(PlanID)
    case actionExecuted(ActionID)
    case safetyRestriction(SafetyLevel)
    case emergencyStop(String)
    case missionCompleted
}

public actor AutonomyEventBus {

    public typealias Handler =
        @Sendable (AutonomyEvent) async -> Void

    private var handlers: [UUID: Handler] = [:]

    public init() {}

    public func subscribe(
        _ handler: @escaping Handler
    ) -> UUID {

        let id = UUID()

        handlers[id] = handler

        return id
    }

    public func unsubscribe(
        _ id: UUID
    ) {
        handlers.removeValue(
            forKey: id
        )
    }

    public func publish(
        _ event: AutonomyEvent
    ) async {

        let currentHandlers =
            Array(handlers.values)

        for handler in currentHandlers {
            await handler(event)
        }
    }
}

// MARK: - Autonomy Coordinator

public actor AutonomyCoordinator {

    private let runtime: SwiftAutonomy
    private let missionController: MissionController
    private let eventBus: AutonomyEventBus

    public init(
        runtime: SwiftAutonomy,
        missionController: MissionController,
        eventBus: AutonomyEventBus
    ) {
        self.runtime = runtime
        self.missionController = missionController
        self.eventBus = eventBus
    }

    public func start(
        mission: Mission
    ) async throws {

        await missionController.load(
            mission: mission
        )

        try await runtime.start()

        try await missionController.start()

        await eventBus.publish(
            .started
        )

        await runtime.startControlLoop()
    }

    public func stop() async {

        await runtime.stopControlLoop()
        await runtime.stop()

        await eventBus.publish(
            .stopped
        )
    }

    public func emergencyStop(
        reason: String
    ) async {

        await runtime.engageEmergencyStop(
            reason: reason
        )

        await eventBus.publish(
            .emergencyStop(reason)
        )
    }

    public func advanceMission() async {

        await missionController.advance()

        if await missionController.currentStatus()
            == .completed {

            await eventBus.publish(
                .missionCompleted
            )
        }
    }
}

// MARK: - Simulation

public actor AutonomySimulation {

    private var state =
        MotionState.stationary

    private let clock =
        DefaultAutonomyClock()

    public init() {}

    public func step(
        command: ActionCommand,
        deltaTime: Double
    ) {

        state.velocity =
            command.linearVelocity

        state.pose =
            state.pose.translated(
                by: state.velocity,
                deltaTime: deltaTime
            )

        state.pose.headingRadians +=
            command.angularVelocity *
            deltaTime
    }

    public func motionState()
        -> MotionState {

        state
    }

    public func makeObservation()
        -> Observation {

        let sensor =
            SensorFactory.motionSensor()

        return Observation(
            sensor: sensor,
            timestamp: clock.now(),
            payload: .motion(state),
            confidence: 0.99
        )
    }
}

// MARK: - Factory

public enum SwiftAutonomyFactory {

    public static func makeDefault()
        throws -> SwiftAutonomy {

        let configuration =
            try AutonomyConfiguration(
                controlFrequencyHz: 20,
                minimumConfidence: 0.50,
                maximumObservationAge:
                    .milliseconds(250),
                allowAutonomousMode: true
            )

        let goalManager =
            GoalManager()

        let perception =
            BasicPerceptionProcessor()

        let estimator =
            AlphaBetaStateEstimator()

        let decision =
            DefaultDecisionEngine(
                goalManager: goalManager
            )

        let planner =
            DirectTrajectoryPlanner()

        let safety =
            DefaultSafetySupervisor(
                envelope: SafetyEnvelope(
                    maximumSpeed: 10,
                    maximumAcceleration: 4,
                    minimumObstacleDistance: 1.5,
                    maximumPlanningAge: 0.5
                )
            )

        let actions =
            DefaultActionGenerator()

        let actuator =
            SimulatedActuator()

        return SwiftAutonomy(
            configuration: configuration,
            perception: perception,
            estimator: estimator,
            decision: decision,
            planner: planner,
            safety: safety,
            actions: actions,
            actuator: actuator
        )
    }
}

// MARK: - Example

public enum SwiftAutonomyExample {

    public static func run()
        async throws {

        let autonomy =
            try SwiftAutonomyFactory.makeDefault()

        let goalManager =
            GoalManager()

        await goalManager.setGoal(
            .moveTo(
                Vector2(
                    x: 100,
                    y: 50
                )
            )
        )

        try await autonomy.start()

        let sensor =
            SensorFactory.motionSensor()

        let observation =
            Observation(
                sensor: sensor,
                timestamp:
                    DefaultAutonomyClock().now(),
                payload: .motion(
                    MotionState(
                        pose: Pose2D(
                            position: Vector2(
                                x: 0,
                                y: 0
                            ),
                            headingRadians: 0
                        ),
                        velocity: Vector2(
                            x: 1,
                            y: 0
                        )
                    )
                ),
                confidence: 0.98
            )

        try await autonomy.ingest(
            observation
        )

        try await autonomy.runCycle()

        let diagnostics =
            await autonomy.diagnosticsSnapshot()

        autonomyLog.notice(
            """
            Autonomy cycle \(diagnostics.cycles)
            successful actions:
            \(diagnostics.successfulActions)
            """
        )

        await autonomy.stop()
    }
}



//
//  SwiftUniversalRuntime.swift
//
//  Swift 6
//
//  Cross-platform application/runtime abstraction layer.
//
//  Goals:
//  - deterministic lifecycle
//  - structured concurrency
//  - typed resources
//  - task execution
//  - capability discovery
//  - runtime services
//  - device abstraction
//  - event propagation
//  - workload placement
//  - health monitoring
//  - graceful shutdown
//

import Foundation
import os

// MARK: - Logging

private let universalRuntimeLog = Logger(
    subsystem: "SwiftUniversalRuntime",
    category: "Runtime"
)

// MARK: - Errors

public enum UniversalRuntimeError: Error, Sendable,
    CustomStringConvertible
{
    case notStarted
    case alreadyStarted
    case shuttingDown
    case invalidConfiguration(String)
    case serviceUnavailable(String)
    case resourceUnavailable(String)
    case taskRejected(String)
    case taskTimeout
    case capabilityUnavailable(String)
    case deviceUnavailable(String)
    case invalidState(String)
    case dependencyFailure(String)
    case executionFailed(String)

    public var description: String {
        switch self {
        case .notStarted:
            return "Universal runtime has not started."

        case .alreadyStarted:
            return "Universal runtime is already running."

        case .shuttingDown:
            return "Universal runtime is shutting down."

        case .invalidConfiguration(let value):
            return "Invalid configuration: \(value)"

        case .serviceUnavailable(let value):
            return "Service unavailable: \(value)"

        case .resourceUnavailable(let value):
            return "Resource unavailable: \(value)"

        case .taskRejected(let value):
            return "Task rejected: \(value)"

        case .taskTimeout:
            return "Task exceeded its deadline."

        case .capabilityUnavailable(let value):
            return "Capability unavailable: \(value)"

        case .deviceUnavailable(let value):
            return "Device unavailable: \(value)"

        case .invalidState(let value):
            return "Invalid runtime state: \(value)"

        case .dependencyFailure(let value):
            return "Dependency failure: \(value)"

        case .executionFailed(let value):
            return "Execution failed: \(value)"
        }
    }
}

// MARK: - Runtime Identifiers

public struct RuntimeID: Hashable, Codable, Sendable {
    public let rawValue: UUID

    public init(
        rawValue: UUID = UUID()
    ) {
        self.rawValue = rawValue
    }
}

public struct WorkloadID: Hashable, Codable, Sendable {
    public let rawValue: UUID

    public init(
        rawValue: UUID = UUID()
    ) {
        self.rawValue = rawValue
    }
}

public struct RuntimeTaskID: Hashable, Codable, Sendable {
    public let rawValue: UUID

    public init(
        rawValue: UUID = UUID()
    ) {
        self.rawValue = rawValue
    }
}

public struct RuntimeServiceID: Hashable, Codable, Sendable {
    public let rawValue: String

    public init(
        _ rawValue: String
    ) {
        self.rawValue = rawValue
    }
}

public struct RuntimeResourceID: Hashable, Codable, Sendable {
    public let rawValue: String

    public init(
        _ rawValue: String
    ) {
        self.rawValue = rawValue
    }
}

// MARK: - Lifecycle

public enum UniversalRuntimeState: String,
    Codable,
    Sendable
{
    case created
    case starting
    case running
    case degraded
    case stopping
    case stopped
    case failed
}

// MARK: - Runtime Clock

public protocol UniversalRuntimeClock: Sendable {
    func now() -> ContinuousClock.Instant
}

public struct DefaultUniversalRuntimeClock:
    UniversalRuntimeClock
{
    private let clock = ContinuousClock()

    public init() {}

    public func now()
        -> ContinuousClock.Instant
    {
        clock.now
    }
}

// MARK: - Platform

public enum RuntimePlatform: String,
    Codable,
    Sendable
{
    case macOS
    case iOS
    case iPadOS
    case watchOS
    case tvOS
    case visionOS
    case linux
    case windows
    case embedded
    case server
    case simulation
    case unknown
}

public enum RuntimeArchitecture: String,
    Codable,
    Sendable
{
    case arm64
    case x86_64
    case arm
    case x86
    case unknown
}

// MARK: - Platform Description

public struct RuntimePlatformInfo: Sendable {

    public let platform: RuntimePlatform
    public let architecture: RuntimeArchitecture
    public let operatingSystemVersion: String
    public let processIdentifier: Int32

    public init(
        platform: RuntimePlatform,
        architecture: RuntimeArchitecture,
        operatingSystemVersion: String,
        processIdentifier: Int32
    ) {
        self.platform = platform
        self.architecture = architecture
        self.operatingSystemVersion =
            operatingSystemVersion
        self.processIdentifier =
            processIdentifier
    }
}

// MARK: - Capability System

public enum RuntimeCapability: String,
    Codable,
    Hashable,
    Sendable
{
    case graphics
    case compute
    case neuralCompute
    case camera
    case microphone
    case location
    case bluetooth
    case networking
    case filesystem
    case gpu
    case sensorInput
    case actuatorOutput
    case persistentStorage
    case backgroundExecution
    case highPerformanceCPU
    case lowPowerExecution
    case virtualization
    case simulation
}

public struct CapabilitySet: Sendable {

    private var values: Set<RuntimeCapability>

    public init(
        _ values: Set<RuntimeCapability> = []
    ) {
        self.values = values
    }

    public mutating func insert(
        _ capability: RuntimeCapability
    ) {
        values.insert(capability)
    }

    public mutating func remove(
        _ capability: RuntimeCapability
    ) {
        values.remove(capability)
    }

    public func contains(
        _ capability: RuntimeCapability
    ) -> Bool {
        values.contains(capability)
    }

    public func containsAll(
        _ capabilities: Set<RuntimeCapability>
    ) -> Bool {
        capabilities.isSubset(
            of: values
        )
    }

    public var all: Set<RuntimeCapability> {
        values
    }
}

// MARK: - Runtime Resources

public enum RuntimeResourceKind: String,
    Codable,
    Sendable
{
    case cpu
    case memory
    case gpu
    case storage
    case network
    case energy
    case sensor
    case actuator
}

public struct RuntimeResource: Sendable {

    public let id: RuntimeResourceID
    public let kind: RuntimeResourceKind
    public let capacity: Double
    public let unit: String

    public init(
        id: RuntimeResourceID,
        kind: RuntimeResourceKind,
        capacity: Double,
        unit: String
    ) {
        self.id = id
        self.kind = kind
        self.capacity = max(
            capacity,
            0
        )
        self.unit = unit
    }
}

// MARK: - Resource Reservation

public struct ResourceRequirement: Sendable {

    public let kind: RuntimeResourceKind
    public let amount: Double

    public init(
        kind: RuntimeResourceKind,
        amount: Double
    ) {
        self.kind = kind
        self.amount = max(
            amount,
            0
        )
    }
}

public struct ResourceReservationID:
    Hashable,
    Codable,
    Sendable
{
    public let rawValue: UUID

    public init(
        rawValue: UUID = UUID()
    ) {
        self.rawValue = rawValue
    }
}

public struct ResourceReservation:
    Sendable
{
    public let id: ResourceReservationID
    public let workload: WorkloadID
    public let requirements:
        [ResourceRequirement]
    public let createdAt:
        ContinuousClock.Instant

    public init(
        id: ResourceReservationID =
            ResourceReservationID(),
        workload: WorkloadID,
        requirements:
            [ResourceRequirement],
        createdAt:
            ContinuousClock.Instant
    ) {
        self.id = id
        self.workload = workload
        self.requirements = requirements
        self.createdAt = createdAt
    }
}

// MARK: - Resource Manager

public actor UniversalResourceManager {

    private var resources:
        [RuntimeResourceKind: RuntimeResource] = [:]

    private var reservations:
        [ResourceReservationID:
            ResourceReservation] = [:]

    private let clock:
        UniversalRuntimeClock

    public init(
        clock: UniversalRuntimeClock =
            DefaultUniversalRuntimeClock()
    ) {
        self.clock = clock
    }

    public func register(
        resource: RuntimeResource
    ) {
        resources[
            resource.kind
        ] = resource
    }

    public func available(
        kind: RuntimeResourceKind
    ) -> Double {

        guard let resource =
            resources[kind]
        else {
            return 0
        }

        let reserved =
            reservations.values
                .flatMap(\.requirements)
                .filter {
                    $0.kind == kind
                }
                .reduce(0) {
                    $0 + $1.amount
                }

        return max(
            resource.capacity - reserved,
            0
        )
    }

    public func reserve(
        workload: WorkloadID,
        requirements:
            [ResourceRequirement]
    ) throws
        -> ResourceReservation
    {
        for requirement in requirements {

            let availableAmount =
                available(
                    kind: requirement.kind
                )

            guard availableAmount >=
                requirement.amount
            else {
                throw UniversalRuntimeError
                    .resourceUnavailable(
                        "\(requirement.kind) requires " +
                        "\(requirement.amount), available " +
                        "\(availableAmount)"
                    )
            }
        }

        let reservation =
            ResourceReservation(
                workload: workload,
                requirements: requirements,
                createdAt: clock.now()
            )

        reservations[
            reservation.id
        ] = reservation

        return reservation
    }

    public func release(
        _ reservation:
            ResourceReservationID
    ) {
        reservations.removeValue(
            forKey: reservation
        )
    }

    public func snapshot()
        -> [RuntimeResourceKind: Double]
    {
        Dictionary(
            uniqueKeysWithValues:
                RuntimeResourceKind.allCases.map {
                    (
                        $0,
                        available(
                            kind: $0
                        )
                    )
                }
        )
    }
}

// MARK: - RuntimeResourceKind CaseIterable

extension RuntimeResourceKind:
    CaseIterable {}

// MARK: - Workload Priority

public enum WorkloadPriority: Int,
    Comparable,
    Codable,
    Sendable
{
    case background = 0
    case utility = 1
    case normal = 2
    case userInitiated = 3
    case high = 4
    case critical = 5
}

// MARK: - Workload

public struct WorkloadDescriptor: Sendable {

    public let id: WorkloadID
    public let name: String
    public let priority: WorkloadPriority
    public let requiredCapabilities:
        Set<RuntimeCapability>
    public let resources:
        [ResourceRequirement]

    public init(
        id: WorkloadID = WorkloadID(),
        name: String,
        priority: WorkloadPriority,
        requiredCapabilities:
            Set<RuntimeCapability> = [],
        resources:
            [ResourceRequirement] = []
    ) {
        self.id = id
        self.name = name
        self.priority = priority
        self.requiredCapabilities =
            requiredCapabilities
        self.resources = resources
    }
}

// MARK: - Workload State

public enum WorkloadState: String,
    Sendable
{
    case created
    case queued
    case running
    case suspended
    case completed
    case failed
    case cancelled
}

// MARK: - Workload Handle

public struct WorkloadHandle:
    Hashable,
    Sendable
{
    public let id: WorkloadID

    public init(
        id: WorkloadID
    ) {
        self.id = id
    }
}

// MARK: - Runtime Task

public struct RuntimeTaskDescriptor:
    Sendable
{
    public let id: RuntimeTaskID
    public let workload: WorkloadID
    public let name: String
    public let priority: WorkloadPriority
    public let deadline: Duration?

    public init(
        id: RuntimeTaskID =
            RuntimeTaskID(),
        workload: WorkloadID,
        name: String,
        priority: WorkloadPriority,
        deadline: Duration? = nil
    ) {
        self.id = id
        self.workload = workload
        self.name = name
        self.priority = priority
        self.deadline = deadline
    }
}

// MARK: - Task Result

public enum RuntimeTaskResult:
    Sendable
{
    case success
    case cancelled
    case failed(String)
}

// MARK: - Task Scheduler

public actor UniversalTaskScheduler {

    private struct ScheduledTask {
        let descriptor:
            RuntimeTaskDescriptor

        let operation:
            @Sendable () async throws -> Void

        let continuation:
            CheckedContinuation<
                RuntimeTaskResult,
                Never
            >
    }

    private var queue:
        [ScheduledTask] = []

    private var runningTasks:
        Set<RuntimeTaskID> = []

    private var workerTask:
        Task<Void, Never>?

    private var acceptingTasks = false

    public init() {}

    public func start() {
        guard workerTask == nil else {
            return
        }

        acceptingTasks = true

        workerTask = Task { [weak self] in

            while !Task.isCancelled {

                guard let self else {
                    return
                }

                await self.processNextTask()

                try? await Task.sleep(
                    nanoseconds: 1_000_000
                )
            }
        }
    }

    public func stop() {

        acceptingTasks = false

        workerTask?.cancel()
        workerTask = nil
    }

    public func submit(
        descriptor:
            RuntimeTaskDescriptor,
        operation:
            @escaping @Sendable () async throws -> Void
    ) async -> RuntimeTaskResult {

        guard acceptingTasks else {
            return .failed(
                UniversalRuntimeError
                    .shuttingDown
                    .description
            )
        }

        return await withCheckedContinuation {
            continuation in

            let scheduled =
                ScheduledTask(
                    descriptor: descriptor,
                    operation: operation,
                    continuation: continuation
                )

            queue.append(
                scheduled
            )

            queue.sort {
                $0.descriptor.priority >
                $1.descriptor.priority
            }
        }
    }

    private func processNextTask() async {

        guard !queue.isEmpty else {
            return
        }

        guard let next =
            queue.first
        else {
            return
        }

        queue.removeFirst()

        let taskID =
            next.descriptor.id

        runningTasks.insert(
            taskID
        )

        do {

            if let deadline =
                next.descriptor.deadline
            {
                try await executeWithDeadline(
                    deadline,
                    operation:
                        next.operation
                )
            } else {
                try await next.operation()
            }

            next.continuation.resume(
                returning: .success
            )

        } catch is CancellationError {

            next.continuation.resume(
                returning: .cancelled
            )

        } catch {

            next.continuation.resume(
                returning:
                    .failed(
                        String(
                            describing: error
                        )
                    )
            )
        }

        runningTasks.remove(
            taskID
        )
    }

    private func executeWithDeadline(
        _ deadline: Duration,
        operation:
            @escaping @Sendable () async throws -> Void
    ) async throws {

        try await withThrowingTaskGroup(
            of: Void.self
        ) { group in

            group.addTask {
                try await operation()
            }

            group.addTask {

                try await Task.sleep(
                    for: deadline
                )

                throw UniversalRuntimeError
                    .taskTimeout
            }

            guard let result =
                try await group.next()
            else {
                throw UniversalRuntimeError
                    .taskTimeout
            }

            group.cancelAll()

            return result
        }
    }
}

// MARK: - Service Protocol

public protocol UniversalRuntimeService:
    Sendable
{
    var descriptor:
        RuntimeServiceDescriptor { get }

    func start() async throws

    func stop() async
}

// MARK: - Service Descriptor

public struct RuntimeServiceDescriptor:
    Sendable
{
    public let id: RuntimeServiceID
    public let name: String
    public let dependencies:
        [RuntimeServiceID]

    public init(
        id: RuntimeServiceID,
        name: String,
        dependencies:
            [RuntimeServiceID] = []
    ) {
        self.id = id
        self.name = name
        self.dependencies =
            dependencies
    }
}

// MARK: - Service Registry

public actor UniversalServiceRegistry {

    private var services:
        [RuntimeServiceID:
            any UniversalRuntimeService] = [:]

    public init() {}

    public func register(
        _ service:
            any UniversalRuntimeService
    ) {
        services[
            service.descriptor.id
        ] = service
    }

    public func service(
        _ id: RuntimeServiceID
    ) -> (
        any UniversalRuntimeService
    )? {
        services[id]
    }

    public func all()
        -> [
            any UniversalRuntimeService
        ]
    {
        Array(
            services.values
        )
    }
}

// MARK: - Service Manager

public actor UniversalServiceManager {

    private let registry:
        UniversalServiceRegistry

    private var started:
        Set<RuntimeServiceID> = []

    public init(
        registry:
            UniversalServiceRegistry
    ) {
        self.registry = registry
    }

    public func startAll()
        async throws
    {
        let services =
            await registry.all()

        var remaining =
            Dictionary(
                uniqueKeysWithValues:
                    services.map {
                        (
                            $0.descriptor.id,
                            $0
                        )
                    }
            )

        while !remaining.isEmpty {

            var progress = false

            for (id, service) in remaining {

                let dependencies =
                    service.descriptor
                        .dependencies

                guard dependencies.allSatisfy({
                    started.contains($0)
                }) else {
                    continue
                }

                try await service.start()

                started.insert(id)
                remaining.removeValue(
                    forKey: id
                )

                progress = true
            }

            guard progress else {
                throw UniversalRuntimeError
                    .dependencyFailure(
                        "Service dependency graph contains " +
                        "an unresolved dependency or cycle."
                    )
            }
        }
    }

    public func stopAll() async {

        let services =
            await registry.all()

        for service in services.reversed() {

            if started.contains(
                service.descriptor.id
            ) {
                await service.stop()
            }
        }

        started.removeAll()
    }
}

// MARK: - Device Abstraction

public enum RuntimeDeviceType:
    String,
    Codable,
    Sendable
{
    case computer
    case phone
    case tablet
    case watch
    case headset
    case vehicle
    case robot
    case industrialController
    case server
    case virtual
    case unknown
}

public struct RuntimeDeviceDescriptor:
    Sendable
{
    public let id: UUID
    public let name: String
    public let type:
        RuntimeDeviceType
    public let capabilities:
        CapabilitySet

    public init(
        id: UUID = UUID(),
        name: String,
        type: RuntimeDeviceType,
        capabilities:
            CapabilitySet
    ) {
        self.id = id
        self.name = name
        self.type = type
        self.capabilities =
            capabilities
    }
}

// MARK: - Device Registry

public actor UniversalDeviceRegistry {

    private var devices:
        [UUID: RuntimeDeviceDescriptor] = [:]

    public init() {}

    public func register(
        _ device:
            RuntimeDeviceDescriptor
    ) {
        devices[
            device.id
        ] = device
    }

    public func unregister(
        _ id: UUID
    ) {
        devices.removeValue(
            forKey: id
        )
    }

    public func device(
        _ id: UUID
    ) -> RuntimeDeviceDescriptor? {
        devices[id]
    }

    public func devicesWith(
        _ capability:
            RuntimeCapability
    ) -> [
        RuntimeDeviceDescriptor
    ] {
        devices.values.filter {
            $0.capabilities.contains(
                capability
            )
        }
    }

    public func all()
        -> [RuntimeDeviceDescriptor]
    {
        Array(
            devices.values
        )
    }
}

// MARK: - Event System

public enum UniversalRuntimeEvent:
    Sendable
{
    case runtimeStarting
    case runtimeStarted
    case runtimeDegraded(String)
    case runtimeStopping
    case runtimeStopped

    case workloadCreated(WorkloadID)
    case workloadStarted(WorkloadID)
    case workloadCompleted(WorkloadID)
    case workloadFailed(
        WorkloadID,
        String
    )

    case resourcePressure(
        RuntimeResourceKind
    )

    case deviceAdded(UUID)
    case deviceRemoved(UUID)
}

// MARK: - Event Bus

public actor UniversalRuntimeEventBus {

    public typealias Handler =
        @Sendable (
            UniversalRuntimeEvent
        ) async -> Void

    private var handlers:
        [UUID: Handler] = [:]

    public init() {}

    public func subscribe(
        _ handler:
            @escaping Handler
    ) -> UUID {

        let id = UUID()

        handlers[id] = handler

        return id
    }

    public func unsubscribe(
        _ id: UUID
    ) {
        handlers.removeValue(
            forKey: id
        )
    }

    public func publish(
        _ event:
            UniversalRuntimeEvent
    ) async {

        let current =
            Array(
                handlers.values
            )

        for handler in current {
            await handler(event)
        }
    }
}

// MARK: - Workload Registry

public actor WorkloadRegistry {

    private struct Entry {
        let descriptor:
            WorkloadDescriptor

        var state:
            WorkloadState
    }

    private var workloads:
        [WorkloadID: Entry] = [:]

    public init() {}

    public func create(
        _ descriptor:
            WorkloadDescriptor
    ) throws
        -> WorkloadHandle
    {
        guard workloads[
            descriptor.id
        ] == nil else {
            throw UniversalRuntimeError
                .taskRejected(
                    "Workload already exists."
                )
        }

        workloads[
            descriptor.id
        ] = Entry(
            descriptor: descriptor,
            state: .created
        )

        return WorkloadHandle(
            id: descriptor.id
        )
    }

    public func setState(
        _ state: WorkloadState,
        for id: WorkloadID
    ) {
        guard var entry =
            workloads[id]
        else {
            return
        }

        entry.state = state

        workloads[id] = entry
    }

    public func state(
        for id: WorkloadID
    ) -> WorkloadState? {
        workloads[id]?.state
    }

    public func descriptor(
        for id: WorkloadID
    ) -> WorkloadDescriptor? {
        workloads[id]?.descriptor
    }

    public func all()
        -> [
            WorkloadDescriptor,
            WorkloadState
        ]
    {
        workloads.values.map {
            (
                $0.descriptor,
                $0.state
            )
        }
    }
}

// MARK: - Runtime Health

public enum RuntimeHealth:
    String,
    Sendable
{
    case healthy
    case warning
    case critical
}

public struct RuntimeHealthReport:
    Sendable
{
    public let health:
        RuntimeHealth

    public let messages:
        [String]

    public let timestamp:
        ContinuousClock.Instant

    public init(
        health:
            RuntimeHealth,
        messages:
            [String],
        timestamp:
            ContinuousClock.Instant
    ) {
        self.health = health
        self.messages = messages
        self.timestamp = timestamp
    }
}

// MARK: - Health Monitor

public actor UniversalHealthMonitor {

    private let clock:
        UniversalRuntimeClock

    private var latest:
        RuntimeHealthReport?

    public init(
        clock:
            UniversalRuntimeClock =
                DefaultUniversalRuntimeClock()
    ) {
        self.clock = clock
    }

    public func evaluate(
        resources:
            [RuntimeResourceKind: Double]
    ) {

        var messages: [String] = []

        var health =
            RuntimeHealth.healthy

        for (kind, amount)
            in resources
        {
            if amount <= 0 {

                health = .critical

                messages.append(
                    "\(kind) resource exhausted."
                )

            } else if amount < 10 {

                if health ==
                    .healthy
                {
                    health = .warning
                }

                messages.append(
                    "\(kind) resource is low."
                )
            }
        }

        latest =
            RuntimeHealthReport(
                health: health,
                messages: messages,
                timestamp:
                    clock.now()
            )
    }

    public func report()
        -> RuntimeHealthReport?
    {
        latest
    }
}

// MARK: - Runtime Metrics

public struct UniversalRuntimeMetrics:
    Sendable
{
    public let startTime:
        ContinuousClock.Instant?

    public let tasksSubmitted:
        UInt64

    public let tasksCompleted:
        UInt64

    public let tasksFailed:
        UInt64

    public let workloads:
        UInt64

    public init(
        startTime:
            ContinuousClock.Instant?,
        tasksSubmitted:
            UInt64,
        tasksCompleted:
            UInt64,
        tasksFailed:
            UInt64,
        workloads:
            UInt64
    ) {
        self.startTime = startTime
        self.tasksSubmitted =
            tasksSubmitted
        self.tasksCompleted =
            tasksCompleted
        self.tasksFailed =
            tasksFailed
        self.workloads =
            workloads
    }
}

// MARK: - Metrics Actor

public actor UniversalMetrics {

    private var startTime:
        ContinuousClock.Instant?

    private var tasksSubmitted:
        UInt64 = 0

    private var tasksCompleted:
        UInt64 = 0

    private var tasksFailed:
        UInt64 = 0

    private var workloads:
        UInt64 = 0

    public init() {}

    public func start(
        at time:
            ContinuousClock.Instant
    ) {
        startTime = time
    }

    public func recordWorkload() {
        workloads += 1
    }

    public func recordTaskSubmitted() {
        tasksSubmitted += 1
    }

    public func recordTaskCompleted() {
        tasksCompleted += 1
    }

    public func recordTaskFailed() {
        tasksFailed += 1
    }

    public func snapshot()
        -> UniversalRuntimeMetrics
    {
        UniversalRuntimeMetrics(
            startTime: startTime,
            tasksSubmitted:
                tasksSubmitted,
            tasksCompleted:
                tasksCompleted,
            tasksFailed:
                tasksFailed,
            workloads:
                workloads
        )
    }
}

// MARK: - Runtime Configuration

public struct UniversalRuntimeConfiguration:
    Sendable
{
    public let maximumConcurrentWorkloads:
        Int

    public let enableResourceManagement:
        Bool

    public let enableHealthMonitoring:
        Bool

    public let enableEventBus:
        Bool

    public init(
        maximumConcurrentWorkloads:
            Int = 8,
        enableResourceManagement:
            Bool = true,
        enableHealthMonitoring:
            Bool = true,
        enableEventBus:
            Bool = true
    ) throws {

        guard maximumConcurrentWorkloads > 0
        else {
            throw UniversalRuntimeError
                .invalidConfiguration(
                    "Maximum concurrent workloads must be positive."
                )
        }

        self.maximumConcurrentWorkloads =
            maximumConcurrentWorkloads

        self.enableResourceManagement =
            enableResourceManagement

        self.enableHealthMonitoring =
            enableHealthMonitoring

        self.enableEventBus =
            enableEventBus
    }

    public static var `default`:
        UniversalRuntimeConfiguration
    {
        try! UniversalRuntimeConfiguration()
    }
}

// MARK: - Runtime Core

public actor SwiftUniversalRuntime {

    public let id:
        RuntimeID

    private let configuration:
        UniversalRuntimeConfiguration

    private let clock:
        UniversalRuntimeClock

    private let resourceManager:
        UniversalResourceManager

    private let taskScheduler:
        UniversalTaskScheduler

    private let serviceRegistry:
        UniversalServiceRegistry

    private let serviceManager:
        UniversalServiceManager

    private let deviceRegistry:
        UniversalDeviceRegistry

    private let eventBus:
        UniversalRuntimeEventBus

    private let workloadRegistry:
        WorkloadRegistry

    private let healthMonitor:
        UniversalHealthMonitor

    private let metrics:
        UniversalMetrics

    private var state:
        UniversalRuntimeState = .created

    public init(
        id: RuntimeID = RuntimeID(),
        configuration:
            UniversalRuntimeConfiguration =
                .default,
        clock:
            UniversalRuntimeClock =
                DefaultUniversalRuntimeClock()
    ) {

        self.id = id
        self.configuration =
            configuration
        self.clock = clock

        let resourceManager =
            UniversalResourceManager(
                clock: clock
            )

        let serviceRegistry =
            UniversalServiceRegistry()

        self.resourceManager =
            resourceManager

        self.taskScheduler =
            UniversalTaskScheduler()

        self.serviceRegistry =
            serviceRegistry

        self.serviceManager =
            UniversalServiceManager(
                registry:
                    serviceRegistry
            )

        self.deviceRegistry =
            UniversalDeviceRegistry()

        self.eventBus =
            UniversalRuntimeEventBus()

        self.workloadRegistry =
            WorkloadRegistry()

        self.healthMonitor =
            UniversalHealthMonitor(
                clock: clock
            )

        self.metrics =
            UniversalMetrics()
    }

    // MARK: Lifecycle

    public func start()
        async throws
    {
        guard state == .created ||
              state == .stopped
        else {

            if state == .running {
                throw UniversalRuntimeError
                    .alreadyStarted
            }

            throw UniversalRuntimeError
                .invalidState(
                    "Runtime cannot start from \(state)."
                )
        }

        state = .starting

        if configuration.enableEventBus {
            await eventBus.publish(
                .runtimeStarting
            )
        }

        try await serviceManager.startAll()

        await taskScheduler.start()

        await metrics.start(
            at: clock.now()
        )

        state = .running

        if configuration.enableEventBus {
            await eventBus.publish(
                .runtimeStarted
            )
        }

        universalRuntimeLog.notice(
            "Universal runtime started: \(self.id.rawValue.uuidString)"
        )
    }

    public func stop()
        async
    {
        guard state != .stopped else {
            return
        }

        state = .stopping

        if configuration.enableEventBus {
            await eventBus.publish(
                .runtimeStopping
            )
        }

        await taskScheduler.stop()
        await serviceManager.stopAll()

        state = .stopped

        if configuration.enableEventBus {
            await eventBus.publish(
                .runtimeStopped
            )
        }

        universalRuntimeLog.notice(
            "Universal runtime stopped."
        )
    }

    public func currentState()
        -> UniversalRuntimeState
    {
        state
    }

    // MARK: Resource Registration

    public func registerResource(
        _ resource:
            RuntimeResource
    ) async {

        await resourceManager.register(
            resource: resource
        )
    }

    public func reserveResources(
        workload:
            WorkloadID,
        requirements:
            [ResourceRequirement]
    ) async throws
        -> ResourceReservation
    {
        try await resourceManager.reserve(
            workload: workload,
            requirements: requirements
        )
    }

    public func releaseResources(
        _ reservation:
            ResourceReservationID
    ) async {

        await resourceManager.release(
            reservation
        )
    }

    // MARK: Services

    public func registerService(
        _ service:
            any UniversalRuntimeService
    ) async {

        await serviceRegistry.register(
            service
        )
    }

    // MARK: Devices

    public func registerDevice(
        _ device:
            RuntimeDeviceDescriptor
    ) async {

        await deviceRegistry.register(
            device
        )

        if configuration.enableEventBus {
            await eventBus.publish(
                .deviceAdded(
                    device.id
                )
            )
        }
    }

    public func unregisterDevice(
        _ id: UUID
    ) async {

        await deviceRegistry.unregister(
            id
        )

        if configuration.enableEventBus {
            await eventBus.publish(
                .deviceRemoved(
                    id
                )
            )
        }
    }

    public func devices()
        async -> [
            RuntimeDeviceDescriptor
        ]
    {
        await deviceRegistry.all()
    }

    // MARK: Workloads

    public func createWorkload(
        _ descriptor:
            WorkloadDescriptor
    ) async throws
        -> WorkloadHandle
    {
        guard state == .running else {
            throw UniversalRuntimeError
                .notStarted
        }

        guard descriptor
            .requiredCapabilities
            .isEmpty ||
            await hasCapabilities(
                descriptor.requiredCapabilities
            )
        else {
            throw UniversalRuntimeError
                .capabilityUnavailable(
                    "Required workload capabilities are unavailable."
                )
        }

        let handle =
            try await workloadRegistry
                .create(
                    descriptor
                )

        await workloadRegistry.setState(
            .queued,
            for: descriptor.id
        )

        await metrics.recordWorkload()

        if configuration.enableEventBus {
            await eventBus.publish(
                .workloadCreated(
                    descriptor.id
                )
            )
        }

        return handle
    }

    public func execute(
        workload:
            WorkloadHandle,
        name: String,
        operation:
            @escaping @Sendable () async throws -> Void
    ) async
        -> RuntimeTaskResult
    {

        guard state == .running else {
            return .failed(
                UniversalRuntimeError
                    .notStarted
                    .description
            )
        }

        guard let descriptor =
            await workloadRegistry
                .descriptor(
                    for: workload.id
                )
        else {
            return .failed(
                "Workload does not exist."
            )
        }

        await workloadRegistry.setState(
            .running,
            for: workload.id
        )

        if configuration.enableEventBus {
            await eventBus.publish(
                .workloadStarted(
                    workload.id
                )
            )
        }

        await metrics.recordTaskSubmitted()

        let taskDescriptor =
            RuntimeTaskDescriptor(
                workload:
                    workload.id,
                name: name,
                priority:
                    descriptor.priority
            )

        let result =
            await taskScheduler.submit(
                descriptor:
                    taskDescriptor,
                operation:
                    operation
            )

        switch result {

        case .success:

            await workloadRegistry.setState(
                .completed,
                for: workload.id
            )

            await metrics.recordTaskCompleted()

            if configuration.enableEventBus {
                await eventBus.publish(
                    .workloadCompleted(
                        workload.id
                    )
                )
            }

        case .failed(let message):

            await workloadRegistry.setState(
                .failed,
                for: workload.id
            )

            await metrics.recordTaskFailed()

            if configuration.enableEventBus {
                await eventBus.publish(
                    .workloadFailed(
                        workload.id,
                        message
                    )
                )
            }

        case .cancelled:

            await workloadRegistry.setState(
                .cancelled,
                for: workload.id
            )
        }

        return result
    }

    // MARK: Capabilities

    public func hasCapabilities(
        _ capabilities:
            Set<RuntimeCapability>
    ) async -> Bool {

        let devices =
            await deviceRegistry.all()

        return devices.contains {
            $0.capabilities.containsAll(
                capabilities
            )
        }
    }

    // MARK: Health

    public func evaluateHealth()
        async
        -> RuntimeHealthReport?
    {

        let resources =
            await resourceManager.snapshot()

        await healthMonitor.evaluate(
            resources: resources
        )

        let report =
            await healthMonitor.report()

        if report?.health == .critical {
            state = .degraded

            if configuration.enableEventBus {
                await eventBus.publish(
                    .runtimeDegraded(
                        report?
                            .messages
                            .joined(
                                separator: "; "
                            )
                        ?? "Critical resource condition."
                    )
                )
            }
        }

        return report
    }

    // MARK: Events

    public func subscribe(
        _ handler:
            @escaping
            UniversalRuntimeEventBus.Handler
    ) async -> UUID {

        await eventBus.subscribe(
            handler
        )
    }

    public func unsubscribe(
        _ id: UUID
    ) async {

        await eventBus.unsubscribe(
            id
        )
    }

    // MARK: Metrics

    public func metricsSnapshot()
        async
        -> UniversalRuntimeMetrics
    {
        await metrics.snapshot()
    }
}

// MARK: - Example Runtime Service

public actor LoggingRuntimeService:
    UniversalRuntimeService
{
    public let descriptor =
        RuntimeServiceDescriptor(
            id:
                RuntimeServiceID(
                    "logging"
                ),
            name:
                "Runtime Logging Service"
        )

    private var active = false

    public init() {}

    public func start()
        async throws
    {
        active = true

        universalRuntimeLog.notice(
            "Logging service started."
        )
    }

    public func stop()
        async
    {
        active = false

        universalRuntimeLog.notice(
            "Logging service stopped."
        )
    }

    public func isActive()
        -> Bool
    {
        active
    }
}

// MARK: - Storage Service

public actor RuntimeMemoryStore:
    UniversalRuntimeService
{
    public let descriptor =
        RuntimeServiceDescriptor(
            id:
                RuntimeServiceID(
                    "memory-store"
                ),
            name:
                "Runtime Memory Store",
            dependencies: [
                RuntimeServiceID(
                    "logging"
                )
            ]
        )

    private var values:
        [String: Data] = [:]

    private var active = false

    public init() {}

    public func start()
        async throws
    {
        active = true
    }

    public func stop()
        async
    {
        active = false
        values.removeAll()
    }

    public func write(
        key: String,
        value: Data
    ) throws {

        guard active else {
            throw UniversalRuntimeError
                .serviceUnavailable(
                    "Memory store is inactive."
                )
        }

        values[key] = value
    }

    public func read(
        key: String
    ) throws -> Data? {

        guard active else {
            throw UniversalRuntimeError
                .serviceUnavailable(
                    "Memory store is inactive."
                )
        }

        return values[key]
    }
}

// MARK: - Compute Service

public actor RuntimeComputeService:
    UniversalRuntimeService
{
    public let descriptor =
        RuntimeServiceDescriptor(
            id:
                RuntimeServiceID(
                    "compute"
                ),
            name:
                "Universal Compute Service",
            dependencies: [
                RuntimeServiceID(
                    "logging"
                )
            ]
        )

    private var active = false

    public init() {}

    public func start()
        async throws
    {
        active = true
    }

    public func stop()
        async
    {
        active = false
    }

    public func execute(
        _ operation:
            @escaping @Sendable () async -> Void
    ) async throws {

        guard active else {
            throw UniversalRuntimeError
                .serviceUnavailable(
                    "Compute service is inactive."
                )
        }

        await operation()
    }
}

// MARK: - Device Factory

public enum UniversalDeviceFactory {

    public static func desktop()
        -> RuntimeDeviceDescriptor
    {
        var capabilities =
            CapabilitySet()

        capabilities.insert(
            .compute
        )

        capabilities.insert(
            .graphics
        )

        capabilities.insert(
            .gpu
        )

        capabilities.insert(
            .networking
        )

        capabilities.insert(
            .filesystem
        )

        capabilities.insert(
            .persistentStorage
        )

        capabilities.insert(
            .highPerformanceCPU
        )

        return RuntimeDeviceDescriptor(
            name:
                "Universal Desktop",
            type:
                .computer,
            capabilities:
                capabilities
        )
    }

    public static func mobile()
        -> RuntimeDeviceDescriptor
    {
        var capabilities =
            CapabilitySet()

        capabilities.insert(
            .compute
        )

        capabilities.insert(
            .graphics
        )

        capabilities.insert(
            .camera
        )

        capabilities.insert(
            .microphone
        )

        capabilities.insert(
            .location
        )

        capabilities.insert(
            .networking
        )

        capabilities.insert(
            .lowPowerExecution
        )

        return RuntimeDeviceDescriptor(
            name:
                "Universal Mobile",
            type:
                .phone,
            capabilities:
                capabilities
        )
    }

    public static func industrial()
        -> RuntimeDeviceDescriptor
    {
        var capabilities =
            CapabilitySet()

        capabilities.insert(
            .compute
        )

        capabilities.insert(
            .sensorInput
        )

        capabilities.insert(
            .actuatorOutput
        )

        capabilities.insert(
            .networking
        )

        capabilities.insert(
            .persistentStorage
        )

        capabilities.insert(
            .highPerformanceCPU
        )

        return RuntimeDeviceDescriptor(
            name:
                "Industrial Controller",
            type:
                .industrialController,
            capabilities:
                capabilities
        )
    }
}

// MARK: - Simulation Runtime

public actor UniversalSimulationRuntime {

    private var simulatedTime:
        TimeInterval = 0

    private var running = false

    public init() {}

    public func start() {
        running = true
    }

    public func stop() {
        running = false
    }

    public func advance(
        by delta:
            TimeInterval
    ) {

        guard running else {
            return
        }

        simulatedTime +=
            max(delta, 0)
    }

    public func time()
        -> TimeInterval
    {
        simulatedTime
    }

    public func reset() {
        simulatedTime = 0
    }
}

// MARK: - Workload Graph

public struct WorkloadNode:
    Sendable
{
    public let id: WorkloadID
    public let dependencies:
        [WorkloadID]

    public init(
        id: WorkloadID,
        dependencies:
            [WorkloadID] = []
    ) {
        self.id = id
        self.dependencies =
            dependencies
    }
}

public actor WorkloadGraph {

    private var nodes:
        [WorkloadID: WorkloadNode] = [:]

    public init() {}

    public func add(
        _ node:
            WorkloadNode
    ) throws {

        guard nodes[node.id] == nil
        else {
            throw UniversalRuntimeError
                .invalidState(
                    "Workload graph node already exists."
                )
        }

        nodes[node.id] = node
    }

    public func ready(
        completed:
            Set<WorkloadID>
    ) -> [
        WorkloadID
    ] {

        nodes.values
            .filter {
                $0.dependencies.allSatisfy {
                    completed.contains($0)
                }
            }
            .map(\.id)
    }
}

// MARK: - Runtime Coordinator

public actor UniversalRuntimeCoordinator {

    private let runtime:
        SwiftUniversalRuntime

    public init(
        runtime:
            SwiftUniversalRuntime
    ) {
        self.runtime = runtime
    }

    public func boot()
        async throws
    {
        try await runtime.start()
    }

    public func shutdown()
        async
    {
        await runtime.stop()
    }

    public func run(
        descriptor:
            WorkloadDescriptor,
        operation:
            @escaping @Sendable () async throws -> Void
    ) async throws
        -> RuntimeTaskResult
    {

        let workload =
            try await runtime
                .createWorkload(
                    descriptor
                )

        return await runtime.execute(
            workload:
                workload,
            name:
                descriptor.name,
            operation:
                operation
        )
    }
}

// MARK: - Demonstration

public enum SwiftUniversalRuntimeExample {

    public static func run()
        async throws
    {
        let runtime =
            SwiftUniversalRuntime()

        // Register core services.

        await runtime.registerService(
            LoggingRuntimeService()
        )

        await runtime.registerService(
            RuntimeMemoryStore()
        )

        await runtime.registerService(
            RuntimeComputeService()
        )

        // Register resources.

        await runtime.registerResource(
            RuntimeResource(
                id:
                    RuntimeResourceID(
                        "cpu"
                    ),
                kind:
                    .cpu,
                capacity:
                    100,
                unit:
                    "%"
            )
        )

        await runtime.registerResource(
            RuntimeResource(
                id:
                    RuntimeResourceID(
                        "memory"
                    ),
                kind:
                    .memory,
                capacity:
                    16_384,
                unit:
                    "MB"
            )
        )

        await runtime.registerResource(
            RuntimeResource(
                id:
                    RuntimeResourceID(
                        "gpu"
                    ),
                kind:
                    .gpu,
                capacity:
                    100,
                unit:
                    "%"
            )
        )

        // Register devices.

        await runtime.registerDevice(
            UniversalDeviceFactory.desktop()
        )

        await runtime.registerDevice(
            UniversalDeviceFactory.industrial()
        )

        // Subscribe to events.

        _ = await runtime.subscribe {
            event in

            switch event {

            case .runtimeStarted:
                universalRuntimeLog.notice(
                    "EVENT: runtime started."
                )

            case .workloadCompleted(let id):
                universalRuntimeLog.notice(
                    "EVENT: workload completed \(id.rawValue.uuidString)"
                )

            case .workloadFailed(
                let id,
                let message
            ):
                universalRuntimeLog.error(
                    "EVENT: workload \(id.rawValue.uuidString) failed: \(message)"
                )

            default:
                break
            }
        }

        // Start runtime.

        try await runtime.start()

        // Create a workload.

        let workload =
            try await runtime.createWorkload(
                WorkloadDescriptor(
                    name:
                        "Industrial Compute",
                    priority:
                        .high,
                    requiredCapabilities: [
                        .compute,
                        .highPerformanceCPU
                    ],
                    resources: [
                        ResourceRequirement(
                            kind:
                                .cpu,
                            amount:
                                20
                        ),
                        ResourceRequirement(
                            kind:
                                .memory,
                            amount:
                                512
                        )
                    ]
                )
            )

        // Reserve resources.

        let reservation =
            try await runtime
                .reserveResources(
                    workload:
                        workload.id,
                    requirements: [
                        ResourceRequirement(
                            kind:
                                .cpu,
                            amount:
                                20
                        ),
                        ResourceRequirement(
                            kind:
                                .memory,
                            amount:
                                512
                        )
                    ]
                )

        // Execute.

        let result =
            await runtime.execute(
                workload:
                    workload,
                name:
                    "Numerical Control Calculation"
            ) {

                var total = 0.0

                for index in 0..<1_000_000 {
                    total +=
                        Double(index) * 0.000001
                }

                _ = total
            }

        universalRuntimeLog.notice(
            "Workload result: \(String(describing: result))"
        )

        // Health.

        if let health =
            await runtime.evaluateHealth()
        {
            universalRuntimeLog.notice(
                "Runtime health: \(health.health.rawValue)"
            )
        }

        // Metrics.

        let metrics =
            await runtime.metricsSnapshot()

        universalRuntimeLog.notice(
            """
            Metrics:
            workloads = \(metrics.workloads)
            submitted = \(metrics.tasksSubmitted)
            completed = \(metrics.tasksCompleted)
            failed = \(metrics.tasksFailed)
            """
        )

        // Release reservation.

        await runtime.releaseResources(
            reservation.id
        )

        // Shutdown.

        await runtime.stop()
    }
}





//
//  SwiftSecureCore.swift
//
//  Swift 6
//
//  Universal security foundation for the Swift industrial/runtime stack.
//
//  Provides:
//  - identities
//  - principals
//  - roles
//  - capabilities
//  - authorization policies
//  - cryptographic hashing
//  - authenticated encryption
//  - signing / verification
//  - key references
//  - secure secret storage abstraction
//  - secure sessions
//  - workload authorization
//  - replay protection
//  - audit logging
//  - tamper-evident audit chains
//  - security event monitoring
//  - rate limiting
//  - security state
//  - policy enforcement
//
//  Uses public Apple/Swift APIs.
//  For production deployment, platform-specific Keychain / Secure Enclave
//  adapters should be supplied rather than storing secrets in memory.
//
//

import Foundation
import CryptoKit
import os

// MARK: - Logging

private let secureCoreLog = Logger(
    subsystem: "SwiftSecureCore",
    category: "Security"
)

// MARK: - Errors

public enum SecureCoreError:
    Error,
    Sendable,
    CustomStringConvertible
{
    case invalidIdentity
    case identityNotFound
    case authenticationFailed
    case authorizationDenied
    case policyDenied(String)
    case invalidSignature
    case invalidKey
    case keyNotFound
    case cryptographicFailure
    case encryptionFailure
    case decryptionFailure
    case replayDetected
    case expiredSession
    case invalidSession
    case rateLimited
    case secureStoreUnavailable
    case secureStoreFailure(String)
    case invalidNonce
    case invalidConfiguration(String)
    case auditFailure
    case revokedIdentity
    case revokedCredential
    case malformedToken
    case unsupportedOperation

    public var description: String {
        switch self {
        case .invalidIdentity:
            return "Invalid identity."

        case .identityNotFound:
            return "Identity was not found."

        case .authenticationFailed:
            return "Authentication failed."

        case .authorizationDenied:
            return "Authorization denied."

        case .policyDenied(let reason):
            return "Security policy denied operation: \(reason)"

        case .invalidSignature:
            return "Signature verification failed."

        case .invalidKey:
            return "Invalid cryptographic key."

        case .keyNotFound:
            return "Cryptographic key was not found."

        case .cryptographicFailure:
            return "Cryptographic operation failed."

        case .encryptionFailure:
            return "Encryption failed."

        case .decryptionFailure:
            return "Decryption failed."

        case .replayDetected:
            return "Replay attack detected."

        case .expiredSession:
            return "Security session has expired."

        case .invalidSession:
            return "Invalid security session."

        case .rateLimited:
            return "Security operation rate limited."

        case .secureStoreUnavailable:
            return "Secure storage is unavailable."

        case .secureStoreFailure(let reason):
            return "Secure storage failure: \(reason)"

        case .invalidNonce:
            return "Invalid nonce."

        case .invalidConfiguration(let reason):
            return "Invalid security configuration: \(reason)"

        case .auditFailure:
            return "Security audit operation failed."

        case .revokedIdentity:
            return "Identity has been revoked."

        case .revokedCredential:
            return "Credential has been revoked."

        case .malformedToken:
            return "Malformed security token."

        case .unsupportedOperation:
            return "Operation is unsupported."
        }
    }
}

// MARK: - IDs

public struct SecureIdentityID:
    Hashable,
    Codable,
    Sendable
{
    public let rawValue: UUID

    public init(
        rawValue: UUID = UUID()
    ) {
        self.rawValue = rawValue
    }
}

public struct CredentialID:
    Hashable,
    Codable,
    Sendable
{
    public let rawValue: UUID

    public init(
        rawValue: UUID = UUID()
    ) {
        self.rawValue = rawValue
    }
}

public struct SecureSessionID:
    Hashable,
    Codable,
    Sendable
{
    public let rawValue: UUID

    public init(
        rawValue: UUID = UUID()
    ) {
        self.rawValue = rawValue
    }
}

public struct SecurityPolicyID:
    Hashable,
    Codable,
    Sendable
{
    public let rawValue: String

    public init(
        _ rawValue: String
    ) {
        self.rawValue = rawValue
    }
}

public struct AuditEventID:
    Hashable,
    Codable,
    Sendable
{
    public let rawValue: UUID

    public init(
        rawValue: UUID = UUID()
    ) {
        self.rawValue = rawValue
    }
}

public struct SecurityKeyID:
    Hashable,
    Codable,
    Sendable
{
    public let rawValue: UUID

    public init(
        rawValue: UUID = UUID()
    ) {
        self.rawValue = rawValue
    }
}

// MARK: - Security Identity

public enum IdentityKind:
    String,
    Codable,
    Sendable
{
    case human
    case device
    case service
    case workload
    case controller
    case administrator
    case system
}

public enum IdentityStatus:
    String,
    Codable,
    Sendable
{
    case active
    case suspended
    case revoked
    case expired
}

public struct SecureIdentity:
    Sendable,
    Codable
{
    public let id:
        SecureIdentityID

    public let name:
        String

    public let kind:
        IdentityKind

    public let createdAt:
        Date

    public var status:
        IdentityStatus

    public init(
        id:
            SecureIdentityID =
                SecureIdentityID(),
        name:
            String,
        kind:
            IdentityKind,
        createdAt:
            Date = Date(),
        status:
            IdentityStatus = .active
    ) {
        self.id = id
        self.name = name
        self.kind = kind
        self.createdAt = createdAt
        self.status = status
    }
}

// MARK: - Roles

public enum SecurityRole:
    String,
    Codable,
    Hashable,
    Sendable
{
    case viewer
    case operator
    case engineer
    case developer
    case administrator
    case securityAdministrator
    case system
}

// MARK: - Capabilities

public enum SecurityCapability:
    String,
    Codable,
    Hashable,
    Sendable
{
    case readTelemetry
    case writeTelemetry

    case readConfiguration
    case writeConfiguration

    case executeWorkload
    case terminateWorkload

    case readDeviceState
    case controlDevice

    case readFinancialData
    case executeTransaction

    case accessNetwork
    case accessStorage

    case manageIdentity
    case manageCredentials
    case managePolicies

    case readAuditLog
    case writeAuditLog

    case performCryptographicOperation
    case administerRuntime
}

// MARK: - Capability Set

public struct SecurityCapabilitySet:
    Sendable,
    Codable
{
    private var values:
        Set<SecurityCapability>

    public init(
        _ values:
            Set<SecurityCapability> = []
    ) {
        self.values = values
    }

    public func contains(
        _ capability:
            SecurityCapability
    ) -> Bool {
        values.contains(
            capability
        )
    }

    public func containsAll(
        _ required:
            Set<SecurityCapability>
    ) -> Bool {
        required.isSubset(
            of: values
        )
    }

    public mutating func insert(
        _ capability:
            SecurityCapability
    ) {
        values.insert(
            capability
        )
    }

    public var all:
        Set<SecurityCapability>
    {
        values
    }
}

// MARK: - Principal

public struct SecurityPrincipal:
    Sendable
{
    public let identity:
        SecureIdentity

    public let roles:
        Set<SecurityRole>

    public let capabilities:
        SecurityCapabilitySet

    public init(
        identity:
            SecureIdentity,
        roles:
            Set<SecurityRole> = [],
        capabilities:
            SecurityCapabilitySet =
                SecurityCapabilitySet()
    ) {
        self.identity = identity
        self.roles = roles
        self.capabilities = capabilities
    }

    public func hasRole(
        _ role:
            SecurityRole
    ) -> Bool {
        roles.contains(role)
    }

    public func hasCapability(
        _ capability:
            SecurityCapability
    ) -> Bool {
        capabilities.contains(
            capability
        )
    }
}

// MARK: - Key Types

public enum SecureKeyKind:
    String,
    Codable,
    Sendable
{
    case symmetric
    case signing
    case encryption
    case keyAgreement
}

// MARK: - Key Metadata

public struct SecureKeyMetadata:
    Sendable,
    Codable
{
    public let id:
        SecurityKeyID

    public let kind:
        SecureKeyKind

    public let createdAt:
        Date

    public let label:
        String

    public let exportable:
        Bool

    public init(
        id:
            SecurityKeyID =
                SecurityKeyID(),
        kind:
            SecureKeyKind,
        createdAt:
            Date = Date(),
        label:
            String,
        exportable:
            Bool = false
    ) {
        self.id = id
        self.kind = kind
        self.createdAt = createdAt
        self.label = label
        self.exportable = exportable
    }
}

// MARK: - SHA-256

public enum SecureHash {

    public static func sha256(
        _ data:
            Data
    ) -> Data {

        Data(
            SHA256.hash(
                data: data
            )
        )
    }

    public static func sha256Hex(
        _ data:
            Data
    ) -> String {

        SHA256.hash(
            data: data
        )
        .map {
            String(
                format: "%02x",
                $0
            )
        }
        .joined()
    }
}

// MARK: - HMAC

public enum SecureHMAC {

    public static func authenticate(
        data:
            Data,
        key:
            SymmetricKey
    ) -> Data {

        let authenticationCode =
            HMAC<SHA256>.authenticationCode(
                for:
                    data,
                using:
                    key
            )

        return Data(
            authenticationCode
        )
    }

    public static func verify(
        data:
            Data,
        authenticationCode:
            Data,
        key:
            SymmetricKey
    ) -> Bool {

        HMAC<SHA256>.isValidAuthenticationCode(
            authenticationCode,
            authenticating:
                data,
            using:
                key
        )
    }
}

// MARK: - Symmetric Encryption

public struct EncryptedPayload:
    Sendable,
    Codable
{
    public let ciphertext:
        Data

    public let nonce:
        Data

    public let tag:
        Data

    public init(
        ciphertext:
            Data,
        nonce:
            Data,
        tag:
            Data
    ) {
        self.ciphertext = ciphertext
        self.nonce = nonce
        self.tag = tag
    }
}

public enum SecureEncryption {

    public static func encrypt(
        _ plaintext:
            Data,
        using key:
            SymmetricKey,
        authenticatedData:
            Data? = nil
    ) throws
        -> EncryptedPayload
    {
        do {

            let sealed =
                try AES.GCM.seal(
                    plaintext,
                    using:
                        key,
                    authenticating:
                        authenticatedData ?? Data()
                )

            guard let combined =
                sealed.combined
            else {
                throw SecureCoreError
                    .encryptionFailure
            }

            let nonceLength = 12
            let tagLength = 16

            guard combined.count >=
                    nonceLength + tagLength
            else {
                throw SecureCoreError
                    .encryptionFailure
            }

            let nonce =
                combined.prefix(
                    nonceLength
                )

            let tag =
                combined.suffix(
                    tagLength
                )

            let ciphertextStart =
                combined.index(
                    combined.startIndex,
                    offsetBy:
                        nonceLength
                )

            let ciphertextEnd =
                combined.index(
                    combined.endIndex,
                    offsetBy:
                        -tagLength
                )

            let ciphertext =
                combined[
                    ciphertextStart..<ciphertextEnd
                ]

            return EncryptedPayload(
                ciphertext:
                    Data(ciphertext),
                nonce:
                    Data(nonce),
                tag:
                    Data(tag)
            )

        } catch {
            throw SecureCoreError
                .encryptionFailure
        }
    }

    public static func decrypt(
        _ payload:
            EncryptedPayload,
        using key:
            SymmetricKey,
        authenticatedData:
            Data? = nil
    ) throws -> Data {

        guard payload.nonce.count == 12,
              payload.tag.count == 16
        else {
            throw SecureCoreError
                .invalidNonce
        }

        do {

            let nonce =
                try AES.GCM.Nonce(
                    data:
                        payload.nonce
                )

            let box =
                try AES.GCM.SealedBox(
                    nonce:
                        nonce,
                    ciphertext:
                        payload.ciphertext,
                    tag:
                        payload.tag
                )

            return try AES.GCM.open(
                box,
                using:
                    key,
                authenticating:
                    authenticatedData ?? Data()
            )

        } catch {
            throw SecureCoreError
                .decryptionFailure
        }
    }
}

// MARK: - Symmetric Key Store

public actor SymmetricKeyStore {

    private var keys:
        [SecurityKeyID: SymmetricKey] = [:]

    private var metadata:
        [SecurityKeyID:
            SecureKeyMetadata] = [:]

    public init() {}

    public func generate(
        label:
            String,
        size:
            SymmetricKeySize =
                .bits256,
        exportable:
            Bool = false
    ) -> SecureKeyMetadata {

        let key =
            SymmetricKey(
                size:
                    size
            )

        let metadata =
            SecureKeyMetadata(
                kind:
                    .symmetric,
                label:
                    label,
                exportable:
                    exportable
            )

        keys[
            metadata.id
        ] = key

        metadata[
            metadata.id
        ] = metadata

        return metadata
    }

    public func key(
        _ id:
            SecurityKeyID
    ) throws -> SymmetricKey {

        guard let key =
            keys[id]
        else {
            throw SecureCoreError
                .keyNotFound
        }

        return key
    }

    public func metadataFor(
        _ id:
            SecurityKeyID
    ) throws
        -> SecureKeyMetadata
    {
        guard let metadata =
            metadata[id]
        else {
            throw SecureCoreError
                .keyNotFound
        }

        return metadata
    }

    public func remove(
        _ id:
            SecurityKeyID
    ) {
        keys.removeValue(
            forKey:
                id
        )

        metadata.removeValue(
            forKey:
                id
        )
    }
}

// MARK: - Signing Identity

public struct SigningIdentity:
    Sendable
{
    public let id:
        SecurityKeyID

    public let privateKey:
        P256.Signing.PrivateKey

    public let publicKey:
        P256.Signing.PublicKey

    public init(
        id:
            SecurityKeyID =
                SecurityKeyID(),
        privateKey:
            P256.Signing.PrivateKey =
                P256.Signing.PrivateKey()
    ) {
        self.id = id
        self.privateKey = privateKey
        self.publicKey =
            privateKey.publicKey
    }
}

// MARK: - Signature

public struct SecureSignature:
    Sendable,
    Codable
{
    public let keyID:
        SecurityKeyID

    public let signature:
        Data

    public init(
        keyID:
            SecurityKeyID,
        signature:
            Data
    ) {
        self.keyID = keyID
        self.signature = signature
    }
}

// MARK: - Signing Service

public actor SecureSigningService {

    private var identities:
        [SecurityKeyID:
            SigningIdentity] = [:]

    public init() {}

    public func generateIdentity()
        -> SecurityKeyID
    {
        let identity =
            SigningIdentity()

        identities[
            identity.id
        ] = identity

        return identity.id
    }

    public func sign(
        _ data:
            Data,
        with id:
            SecurityKeyID
    ) throws
        -> SecureSignature
    {
        guard let identity =
            identities[id]
        else {
            throw SecureCoreError
                .keyNotFound
        }

        do {

            let signature =
                try identity.privateKey
                    .signature(
                        for:
                            data
                    )

            return SecureSignature(
                keyID:
                    id,
                signature:
                    signature.derRepresentation
            )

        } catch {
            throw SecureCoreError
                .cryptographicFailure
        }
    }

    public func verify(
        _ data:
            Data,
        signature:
            SecureSignature
    ) throws -> Bool {

        guard let identity =
            identities[
                signature.keyID
            ]
        else {
            throw SecureCoreError
                .keyNotFound
        }

        do {

            let parsed =
                try P256.Signing.ECDSASignature(
                    derRepresentation:
                        signature.signature
                )

            return identity.publicKey
                .isValidSignature(
                    parsed,
                    for:
                        data
                )

        } catch {
            throw SecureCoreError
                .invalidSignature
        }
    }

    public func publicKey(
        _ id:
            SecurityKeyID
    ) throws
        -> Data
    {
        guard let identity =
            identities[id]
        else {
            throw SecureCoreError
                .keyNotFound
        }

        return identity.publicKey
            .x963Representation
    }
}

// MARK: - Secure Storage Protocol

public protocol SecureSecretStore:
    Sendable
{
    func put(
        key:
            String,
        value:
            Data
    ) async throws

    func get(
        key:
            String
    ) async throws -> Data?

    func remove(
        key:
            String
    ) async throws
}

// MARK: - In-Memory Development Store

public actor InMemorySecureSecretStore:
    SecureSecretStore
{
    private var storage:
        [String: Data] = [:]

    public init() {}

    public func put(
        key:
            String,
        value:
            Data
    ) async throws {
        storage[key] = value
    }

    public func get(
        key:
            String
    ) async throws -> Data? {
        storage[key]
    }

    public func remove(
        key:
            String
    ) async throws {
        storage.removeValue(
            forKey:
                key
        )
    }
}

// MARK: - Credential

public struct SecurityCredential:
    Sendable,
    Codable
{
    public let id:
        CredentialID

    public let identity:
        SecureIdentityID

    public let issuedAt:
        Date

    public let expiresAt:
        Date?

    public var revoked:
        Bool

    public init(
        id:
            CredentialID =
                CredentialID(),
        identity:
            SecureIdentityID,
        issuedAt:
            Date = Date(),
        expiresAt:
            Date? = nil,
        revoked:
            Bool = false
    ) {
        self.id = id
        self.identity = identity
        self.issuedAt = issuedAt
        self.expiresAt = expiresAt
        self.revoked = revoked
    }

    public func isValid(
        at date:
            Date = Date()
    ) -> Bool {

        guard !revoked else {
            return false
        }

        guard let expiresAt else {
            return true
        }

        return date < expiresAt
    }
}

// MARK: - Identity Registry

public actor SecureIdentityRegistry {

    private var identities:
        [SecureIdentityID:
            SecureIdentity] = [:]

    private var credentials:
        [CredentialID:
            SecurityCredential] = [:]

    public init() {}

    public func register(
        _ identity:
            SecureIdentity
    ) throws {

        guard identities[
            identity.id
        ] == nil else {
            throw SecureCoreError
                .invalidIdentity
        }

        identities[
            identity.id
        ] = identity
    }

    public func identity(
        _ id:
            SecureIdentityID
    ) throws
        -> SecureIdentity
    {
        guard let identity =
            identities[id]
        else {
            throw SecureCoreError
                .identityNotFound
        }

        guard identity.status ==
                .active
        else {

            if identity.status ==
                .revoked
            {
                throw SecureCoreError
                    .revokedIdentity
            }

            throw SecureCoreError
                .authenticationFailed
        }

        return identity
    }

    public func suspend(
        _ id:
            SecureIdentityID
    ) throws {

        guard var identity =
            identities[id]
        else {
            throw SecureCoreError
                .identityNotFound
        }

        identity.status =
            .suspended

        identities[id] =
            identity
    }

    public func revoke(
        _ id:
            SecureIdentityID
    ) throws {

        guard var identity =
            identities[id]
        else {
            throw SecureCoreError
                .identityNotFound
        }

        identity.status =
            .revoked

        identities[id] =
            identity
    }

    public func issueCredential(
        for identity:
            SecureIdentityID,
        expiresAt:
            Date? = nil
    ) throws
        -> SecurityCredential
    {
        _ = try self.identity(
            identity
        )

        let credential =
            SecurityCredential(
                identity:
                    identity,
                expiresAt:
                    expiresAt
            )

        credentials[
            credential.id
        ] = credential

        return credential
    }

    public func revokeCredential(
        _ id:
            CredentialID
    ) throws {

        guard var credential =
            credentials[id]
        else {
            throw SecureCoreError
                .malformedToken
        }

        credential.revoked = true

        credentials[id] =
            credential
    }

    public func validateCredential(
        _ id:
            CredentialID
    ) throws
        -> SecurityCredential
    {
        guard let credential =
            credentials[id]
        else {
            throw SecureCoreError
                .malformedToken
        }

        guard credential.isValid()
        else {
            throw SecureCoreError
                .revokedCredential
        }

        return credential
    }
}

// MARK: - Authorization Request

public struct AuthorizationRequest:
    Sendable
{
    public let principal:
        SecurityPrincipal

    public let capability:
        SecurityCapability

    public let resource:
        String

    public let timestamp:
        Date

    public init(
        principal:
            SecurityPrincipal,
        capability:
            SecurityCapability,
        resource:
            String,
        timestamp:
            Date = Date()
    ) {
        self.principal = principal
        self.capability = capability
        self.resource = resource
        self.timestamp = timestamp
    }
}

// MARK: - Authorization Decision

public enum AuthorizationDecision:
    String,
    Sendable
{
    case allow
    case deny
}

// MARK: - Policy Rule

public struct SecurityPolicyRule:
    Sendable
{
    public let policyID:
        SecurityPolicyID

    public let requiredCapability:
        SecurityCapability

    public let allowedRoles:
        Set<SecurityRole>

    public let resourcePrefix:
        String?

    public let enabled:
        Bool

    public init(
        policyID:
            SecurityPolicyID,
        requiredCapability:
            SecurityCapability,
        allowedRoles:
            Set<SecurityRole> = [],
        resourcePrefix:
            String? = nil,
        enabled:
            Bool = true
    ) {
        self.policyID =
            policyID

        self.requiredCapability =
            requiredCapability

        self.allowedRoles =
            allowedRoles

        self.resourcePrefix =
            resourcePrefix

        self.enabled =
            enabled
    }
}

// MARK: - Policy Engine

public actor SecurityPolicyEngine {

    private var rules:
        [SecurityPolicyID:
            SecurityPolicyRule] = [:]

    public init() {}

    public func register(
        _ rule:
            SecurityPolicyRule
    ) {
        rules[
            rule.policyID
        ] = rule
    }

    public func remove(
        _ id:
            SecurityPolicyID
    ) {
        rules.removeValue(
            forKey:
                id
        )
    }

    public func evaluate(
        _ request:
            AuthorizationRequest
    ) -> AuthorizationDecision {

        let applicable =
            rules.values.filter {
                $0.enabled &&
                $0.requiredCapability ==
                    request.capability
            }

        guard !applicable.isEmpty
        else {
            return request.principal
                .hasCapability(
                    request.capability
                )
                ? .allow
                : .deny
        }

        for rule in applicable {

            guard request.principal
                .hasCapability(
                    rule.requiredCapability
                )
            else {
                continue
            }

            if !rule.allowedRoles.isEmpty &&
               rule.allowedRoles
                .intersection(
                    request.principal.roles
                )
                .isEmpty
            {
                continue
            }

            if let prefix =
                rule.resourcePrefix
            {
                guard request.resource
                    .hasPrefix(prefix)
                else {
                    continue
                }
            }

            return .allow
        }

        return .deny
    }
}

// MARK: - Secure Session

public struct SecureSession:
    Sendable,
    Codable
{
    public let id:
        SecureSessionID

    public let identity:
        SecureIdentityID

    public let issuedAt:
        Date

    public let expiresAt:
        Date

    public let nonce:
        UInt64

    public init(
        id:
            SecureSessionID =
                SecureSessionID(),
        identity:
            SecureIdentityID,
        issuedAt:
            Date = Date(),
        expiresAt:
            Date,
        nonce:
            UInt64
    ) {
        self.id = id
        self.identity = identity
        self.issuedAt = issuedAt
        self.expiresAt = expiresAt
        self.nonce = nonce
    }

    public func isValid(
        at date:
            Date = Date()
    ) -> Bool {
        date < expiresAt
    }
}

// MARK: - Secure Session Manager

public actor SecureSessionManager {

    private var sessions:
        [SecureSessionID:
            SecureSession] = [:]

    private let lifetime:
        TimeInterval

    public init(
        lifetime:
            TimeInterval = 3600
    ) throws {

        guard lifetime > 0 else {
            throw SecureCoreError
                .invalidConfiguration(
                    "Session lifetime must be positive."
                )
        }

        self.lifetime =
            lifetime
    }

    public func create(
        identity:
            SecureIdentityID
    ) -> SecureSession {

        let issued =
            Date()

        let session =
            SecureSession(
                identity:
                    identity,
                issuedAt:
                    issued,
                expiresAt:
                    issued.addingTimeInterval(
                        lifetime
                    ),
                nonce:
                    UInt64.random(
                        in:
                            UInt64.min...
                    )
            )

        sessions[
            session.id
        ] = session

        return session
    }

    public func validate(
        _ id:
            SecureSessionID
    ) throws
        -> SecureSession
    {
        guard let session =
            sessions[id]
        else {
            throw SecureCoreError
                .invalidSession
        }

        guard session.isValid()
        else {
            sessions.removeValue(
                forKey:
                    id
            )

            throw SecureCoreError
                .expiredSession
        }

        return session
    }

    public func invalidate(
        _ id:
            SecureSessionID
    ) {
        sessions.removeValue(
            forKey:
                id
        )
    }
}

// MARK: - Replay Protection

public actor ReplayProtection {

    private var seen:
        [SecureSessionID: Set<UInt64>] = [:]

    private let maximumEntries:
        Int

    public init(
        maximumEntries:
            Int = 10_000
    ) {
        self.maximumEntries =
            maximumEntries
    }

    public func accept(
        session:
            SecureSessionID,
        nonce:
            UInt64
    ) throws {

        var values =
            seen[session] ?? []

        guard !values.contains(
            nonce
        ) else {
            throw SecureCoreError
                .replayDetected
        }

        if values.count >=
            maximumEntries
        {
            values.removeFirst()
        }

        values.insert(
            nonce
        )

        seen[session] =
            values
    }

    public func clear(
        session:
            SecureSessionID
    ) {
        seen.removeValue(
            forKey:
                session
        )
    }
}

// MARK: - Security Operation

public enum SecurityOperation:
    String,
    Sendable
{
    case authenticate
    case authorize
    case encrypt
    case decrypt
    case sign
    case verify
    case createSession
    case terminateSession
    case accessResource
    case createIdentity
    case revokeIdentity
    case modifyPolicy
}

// MARK: - Audit Result

public enum AuditResult:
    String,
    Codable,
    Sendable
{
    case success
    case failure
    case denied
}

// MARK: - Audit Event

public struct SecurityAuditEvent:
    Sendable,
    Codable
{
    public let id:
        AuditEventID

    public let timestamp:
        Date

    public let identity:
        SecureIdentityID?

    public let session:
        SecureSessionID?

    public let operation:
        SecurityOperation

    public let resource:
        String

    public let result:
        AuditResult

    public let detail:
        String

    public let previousHash:
        String

    public let hash:
        String

    public init(
        id:
            AuditEventID =
                AuditEventID(),
        timestamp:
            Date = Date(),
        identity:
            SecureIdentityID?,
        session:
            SecureSessionID?,
        operation:
            SecurityOperation,
        resource:
            String,
        result:
            AuditResult,
        detail:
            String,
        previousHash:
            String,
        hash:
            String
    ) {
        self.id = id
        self.timestamp = timestamp
        self.identity = identity
        self.session = session
        self.operation = operation
        self.resource = resource
        self.result = result
        self.detail = detail
        self.previousHash = previousHash
        self.hash = hash
    }
}

// MARK: - Audit Ledger

public actor SecurityAuditLedger {

    private var events:
        [SecurityAuditEvent] = []

    private var lastHash:
        String = "GENESIS"

    public init() {}

    public func append(
        identity:
            SecureIdentityID?,
        session:
            SecureSessionID?,
        operation:
            SecurityOperation,
        resource:
            String,
        result:
            AuditResult,
        detail:
            String
    ) throws
        -> SecurityAuditEvent
    {
        let timestamp =
            Date()

        let canonical =
            """
            \(timestamp.timeIntervalSince1970)|
            \(identity?.rawValue.uuidString ?? "-")|
            \(session?.rawValue.uuidString ?? "-")|
            \(operation.rawValue)|
            \(resource)|
            \(result.rawValue)|
            \(detail)|
            \(lastHash)
            """

        let hash =
            SecureHash.sha256Hex(
                Data(
                    canonical.utf8
                )
            )

        let event =
            SecurityAuditEvent(
                timestamp:
                    timestamp,
                identity:
                    identity,
                session:
                    session,
                operation:
                    operation,
                resource:
                    resource,
                result:
                    result,
                detail:
                    detail,
                previousHash:
                    lastHash,
                hash:
                    hash
            )

        events.append(
            event
        )

        lastHash =
            hash

        return event
    }

    public func all()
        -> [SecurityAuditEvent]
    {
        events
    }

    public func verifyChain()
        -> Bool
    {
        var previous =
            "GENESIS"

        for event in events {

            let canonical =
                """
                \(event.timestamp.timeIntervalSince1970)|
                \(event.identity?.rawValue.uuidString ?? "-")|
                \(event.session?.rawValue.uuidString ?? "-")|
                \(event.operation.rawValue)|
                \(event.resource)|
                \(event.result.rawValue)|
                \(event.detail)|
                \(previous)
                """

            let calculated =
                SecureHash.sha256Hex(
                    Data(
                        canonical.utf8
                    )
                )

            guard event.previousHash ==
                    previous,
                  event.hash ==
                    calculated
            else {
                return false
            }

            previous =
                event.hash
        }

        return true
    }
}

// MARK: - Rate Limiter

public actor SecurityRateLimiter {

    private struct Bucket {
        var timestamps:
            [Date]
    }

    private var buckets:
        [String: Bucket] = [:]

    private let maximumRequests:
        Int

    private let window:
        TimeInterval

    public init(
        maximumRequests:
            Int = 100,
        window:
            TimeInterval = 60
    ) {
        self.maximumRequests =
            max(
                maximumRequests,
                1
            )

        self.window =
            max(
                window,
                0.001
            )
    }

    public func consume(
        key:
            String,
        now:
            Date = Date()
    ) throws {

        let cutoff =
            now.addingTimeInterval(
                -window
            )

        var bucket =
            buckets[key] ??
            Bucket(
                timestamps:
                    []
            )

        bucket.timestamps.removeAll {
            $0 < cutoff
        }

        guard bucket.timestamps.count <
                maximumRequests
        else {
            buckets[key] =
                bucket

            throw SecureCoreError
                .rateLimited
        }

        bucket.timestamps.append(
            now
        )

        buckets[key] =
            bucket
    }
}

// MARK: - Security Token Payload

public struct SecurityTokenPayload:
    Sendable,
    Codable
{
    public let credential:
        CredentialID

    public let identity:
        SecureIdentityID

    public let session:
        SecureSessionID

    public let issuedAt:
        Date

    public let expiresAt:
        Date

    public let nonce:
        UInt64

    public init(
        credential:
            CredentialID,
        identity:
            SecureIdentityID,
        session:
            SecureSessionID,
        issuedAt:
            Date,
        expiresAt:
            Date,
        nonce:
            UInt64
    ) {
        self.credential = credential
        self.identity = identity
        self.session = session
        self.issuedAt = issuedAt
        self.expiresAt = expiresAt
        self.nonce = nonce
    }
}

// MARK: - Token Codec

public enum SecurityTokenCodec {

    public static func encode(
        _ payload:
            SecurityTokenPayload
    ) throws -> Data {

        try JSONEncoder()
            .encode(
                payload
            )
    }

    public static func decode(
        _ data:
            Data
    ) throws
        -> SecurityTokenPayload
    {
        do {
            return try JSONDecoder()
                .decode(
                    SecurityTokenPayload.self,
                    from:
                        data
                )
        } catch {
            throw SecureCoreError
                .malformedToken
        }
    }
}

// MARK: - Signed Security Token

public struct SignedSecurityToken:
    Sendable,
    Codable
{
    public let payload:
        Data

    public let signature:
        SecureSignature

    public init(
        payload:
            Data,
        signature:
            SecureSignature
    ) {
        self.payload = payload
        self.signature = signature
    }
}

// MARK: - Security Token Service

public actor SecurityTokenService {

    private let identityRegistry:
        SecureIdentityRegistry

    private let sessionManager:
        SecureSessionManager

    private let signing:
        SecureSigningService

    private let replay:
        ReplayProtection

    private let credentialTTL:
        TimeInterval

    private let signingKeyID:
        SecurityKeyID

    public init(
        identityRegistry:
            SecureIdentityRegistry,
        sessionManager:
            SecureSessionManager,
        signing:
            SecureSigningService,
        replay:
            ReplayProtection,
        credentialTTL:
            TimeInterval = 900
    ) async {

        self.identityRegistry =
            identityRegistry

        self.sessionManager =
            sessionManager

        self.signing =
            signing

        self.replay =
            replay

        self.credentialTTL =
            credentialTTL

        self.signingKeyID =
            await signing.generateIdentity()
    }

    public func issue(
        credential:
            SecurityCredential,
        session:
            SecureSession
    ) async throws
        -> SignedSecurityToken
    {
        guard credential.isValid()
        else {
            throw SecureCoreError
                .revokedCredential
        }

        guard session.isValid()
        else {
            throw SecureCoreError
                .expiredSession
        }

        let now =
            Date()

        let payload =
            SecurityTokenPayload(
                credential:
                    credential.id,
                identity:
                    credential.identity,
                session:
                    session.id,
                issuedAt:
                    now,
                expiresAt:
                    min(
                        session.expiresAt,
                        now.addingTimeInterval(
                            credentialTTL
                        )
                    ),
                nonce:
                    session.nonce
            )

        let encoded =
            try SecurityTokenCodec.encode(
                payload
            )

        let signature =
            try await signing.sign(
                encoded,
                with:
                    signingKeyID
            )

        return SignedSecurityToken(
            payload:
                encoded,
            signature:
                signature
        )
    }

    public func verify(
        _ token:
            SignedSecurityToken
    ) async throws
        -> SecurityTokenPayload
    {
        let valid =
            try await signing.verify(
                token.payload,
                signature:
                    token.signature
            )

        guard valid else {
            throw SecureCoreError
                .invalidSignature
        }

        let payload =
            try SecurityTokenCodec.decode(
                token.payload
            )

        guard payload.expiresAt >
                Date()
        else {
            throw SecureCoreError
                .expiredSession
        }

        try await replay.accept(
            session:
                payload.session,
            nonce:
                payload.nonce
        )

        _ = try await identityRegistry
            .validateCredential(
                payload.credential
            )

        _ = try await sessionManager
            .validate(
                payload.session
            )

        return payload
    }
}

// MARK: - Security State

public enum SecureSystemState:
    String,
    Sendable
{
    case initializing
    case secure
    case degraded
    case lockdown
    case shuttingDown
    case stopped
}

// MARK: - Security Configuration

public struct SecureCoreConfiguration:
    Sendable
{
    public let sessionLifetime:
        TimeInterval

    public let tokenLifetime:
        TimeInterval

    public let rateLimit:
        Int

    public let rateWindow:
        TimeInterval

    public let enableAudit:
        Bool

    public init(
        sessionLifetime:
            TimeInterval = 3600,
        tokenLifetime:
            TimeInterval = 900,
        rateLimit:
            Int = 100,
        rateWindow:
            TimeInterval = 60,
        enableAudit:
            Bool = true
    ) throws {

        guard sessionLifetime > 0 else {
            throw SecureCoreError
                .invalidConfiguration(
                    "Session lifetime must be positive."
                )
        }

        guard tokenLifetime > 0 else {
            throw SecureCoreError
                .invalidConfiguration(
                    "Token lifetime must be positive."
                )
        }

        self.sessionLifetime =
            sessionLifetime

        self.tokenLifetime =
            tokenLifetime

        self.rateLimit =
            rateLimit

        self.rateWindow =
            rateWindow

        self.enableAudit =
            enableAudit
    }

    public static var `default`:
        SecureCoreConfiguration
    {
        try! SecureCoreConfiguration()
    }
}

// MARK: - Secure Core

public actor SwiftSecureCore {

    public let configuration:
        SecureCoreConfiguration

    public let identityRegistry:
        SecureIdentityRegistry

    public let sessionManager:
        SecureSessionManager

    public let policyEngine:
        SecurityPolicyEngine

    public let auditLedger:
        SecurityAuditLedger

    public let replayProtection:
        ReplayProtection

    public let rateLimiter:
        SecurityRateLimiter

    public let symmetricKeys:
        SymmetricKeyStore

    public let signing:
        SecureSigningService

    private let tokenService:
        SecurityTokenService

    private var state:
        SecureSystemState =
            .initializing

    public init(
        configuration:
            SecureCoreConfiguration =
                .default
    ) async throws {

        self.configuration =
            configuration

        self.identityRegistry =
            SecureIdentityRegistry()

        self.sessionManager =
            try SecureSessionManager(
                lifetime:
                    configuration.sessionLifetime
            )

        self.policyEngine =
            SecurityPolicyEngine()

        self.auditLedger =
            SecurityAuditLedger()

        self.replayProtection =
            ReplayProtection()

        self.rateLimiter =
            SecurityRateLimiter(
                maximumRequests:
                    configuration.rateLimit,
                window:
                    configuration.rateWindow
            )

        self.symmetricKeys =
            SymmetricKeyStore()

        self.signing =
            SecureSigningService()

        self.tokenService =
            await SecurityTokenService(
                identityRegistry:
                    identityRegistry,
                sessionManager:
                    sessionManager,
                signing:
                    signing,
                replay:
                    replayProtection,
                credentialTTL:
                    configuration.tokenLifetime
            )
    }

    // MARK: Lifecycle

    public func start()
        async
    {
        state =
            .secure

        secureCoreLog.notice(
            "SwiftSecureCore entered secure state."
        )
    }

    public func stop()
        async
    {
        state =
            .shuttingDown

        state =
            .stopped

        secureCoreLog.notice(
            "SwiftSecureCore stopped."
        )
    }

    public func currentState()
        -> SecureSystemState
    {
        state
    }

    // MARK: Identity

    public func createIdentity(
        name:
            String,
        kind:
            IdentityKind,
        roles:
            Set<SecurityRole>,
        capabilities:
            SecurityCapabilitySet
    ) async throws
        -> SecurityPrincipal
    {
        let identity =
            SecureIdentity(
                name:
                    name,
                kind:
                    kind
            )

        try await identityRegistry
            .register(
                identity
            )

        let principal =
            SecurityPrincipal(
                identity:
                    identity,
                roles:
                    roles,
                capabilities:
                    capabilities
            )

        if configuration.enableAudit {

            _ = try await auditLedger
                .append(
                    identity:
                        identity.id,
                    session:
                        nil,
                    operation:
                        .createIdentity,
                    resource:
                        "identity/\(identity.id.rawValue.uuidString)",
                    result:
                        .success,
                    detail:
                        "Identity created."
                )
        }

        return principal
    }

    // MARK: Authentication

    public func authenticate(
        principal:
            SecurityPrincipal
    ) async throws
        -> SecurityCredential
    {
        guard principal.identity.status ==
                .active
        else {
            throw SecureCoreError
                .authenticationFailed
        }

        try await rateLimiter.consume(
            key:
                principal.identity.id
                    .rawValue.uuidString
        )

        let credential =
            try await identityRegistry
                .issueCredential(
                    for:
                        principal.identity.id,
                    expiresAt:
                        Date()
                            .addingTimeInterval(
                                configuration.tokenLifetime
                            )
                )

        if configuration.enableAudit {

            _ = try await auditLedger
                .append(
                    identity:
                        principal.identity.id,
                    session:
                        nil,
                    operation:
                        .authenticate,
                    resource:
                        "authentication",
                    result:
                        .success,
                    detail:
                        "Credential issued."
                )
        }

        return credential
    }

    // MARK: Session

    public func createSession(
        credential:
            SecurityCredential
    ) async throws
        -> SecureSession
    {
        _ = try await identityRegistry
            .validateCredential(
                credential.id
            )

        let session =
            await sessionManager
                .create(
                    identity:
                        credential.identity
                )

        if configuration.enableAudit {

            _ = try await auditLedger
                .append(
                    identity:
                        credential.identity,
                    session:
                        session.id,
                    operation:
                        .createSession,
                    resource:
                        "session/\(session.id.rawValue.uuidString)",
                    result:
                        .success,
                    detail:
                        "Session created."
                )
        }

        return session
    }

    // MARK: Token

    public func issueToken(
        credential:
            SecurityCredential,
        session:
            SecureSession
    ) async throws
        -> SignedSecurityToken
    {
        try await tokenService.issue(
            credential:
                credential,
            session:
                session
        )
    }

    public func verifyToken(
        _ token:
            SignedSecurityToken
    ) async throws
        -> SecurityTokenPayload
    {
        try await tokenService.verify(
            token
        )
    }

    // MARK: Authorization

    public func authorize(
        principal:
            SecurityPrincipal,
        capability:
            SecurityCapability,
        resource:
            String
    ) async throws {

        let request =
            AuthorizationRequest(
                principal:
                    principal,
                capability:
                    capability,
                resource:
                    resource
            )

        let decision =
            await policyEngine.evaluate(
                request
            )

        switch decision {

        case .allow:

            if configuration.enableAudit {

                _ = try await auditLedger
                    .append(
                        identity:
                            principal.identity.id,
                        session:
                            nil,
                        operation:
                            .authorize,
                        resource:
                            resource,
                        result:
                            .success,
                        detail:
                            "Authorization allowed."
                    )
            }

        case .deny:

            if configuration.enableAudit {

                _ = try await auditLedger
                    .append(
                        identity:
                            principal.identity.id,
                        session:
                            nil,
                        operation:
                            .authorize,
                        resource:
                            resource,
                        result:
                            .denied,
                        detail:
                            "Authorization denied."
                    )
            }

            throw SecureCoreError
                .authorizationDenied
        }
    }

    // MARK: Encryption

    public func generateSymmetricKey(
        label:
            String
    ) async
        -> SecureKeyMetadata
    {
        await symmetricKeys.generate(
            label:
                label
        )
    }

    public func encrypt(
        _ data:
            Data,
        using key:
            SecurityKeyID,
        authenticatedData:
            Data? = nil
    ) async throws
        -> EncryptedPayload
    {
        let symmetricKey =
            try await symmetricKeys.key(
                key
            )

        return try SecureEncryption.encrypt(
            data,
            using:
                symmetricKey,
            authenticatedData:
                authenticatedData
        )
    }

    public func decrypt(
        _ payload:
            EncryptedPayload,
        using key:
            SecurityKeyID,
        authenticatedData:
            Data? = nil
    ) async throws
        -> Data
    {
        let symmetricKey =
            try await symmetricKeys.key(
                key
            )

        return try SecureEncryption.decrypt(
            payload,
            using:
                symmetricKey,
            authenticatedData:
                authenticatedData
        )
    }

    // MARK: Policy

    public func registerPolicy(
        _ rule:
            SecurityPolicyRule
    ) async {
        await policyEngine.register(
            rule
        )
    }

    // MARK: Audit

    public func verifyAuditChain()
        async -> Bool
    {
        await auditLedger.verifyChain()
    }

    public func auditEvents()
        async -> [SecurityAuditEvent]
    {
        await auditLedger.all()
    }
}

// MARK: - Secure Workload Envelope

public struct SecureWorkloadEnvelope:
    Sendable,
    Codable
{
    public let workloadID:
        UUID

    public let owner:
        SecureIdentityID

    public let createdAt:
        Date

    public let payload:
        Data

    public let digest:
        String

    public let signature:
        SecureSignature

    public init(
        workloadID:
            UUID,
        owner:
            SecureIdentityID,
        createdAt:
            Date,
        payload:
            Data,
        digest:
            String,
        signature:
            SecureSignature
    ) {
        self.workloadID =
            workloadID
        self.owner =
            owner
        self.createdAt =
            createdAt
        self.payload =
            payload
        self.digest =
            digest
        self.signature =
            signature
    }
}

// MARK: - Workload Security Service

public actor SecureWorkloadService {

    private let signing:
        SecureSigningService

    private let identityRegistry:
        SecureIdentityRegistry

    private let audit:
        SecurityAuditLedger

    private let signingKey:
        SecurityKeyID

    public init(
        signing:
            SecureSigningService,
        identityRegistry:
            SecureIdentityRegistry,
        audit:
            SecurityAuditLedger
    ) async {

        self.signing =
            signing

        self.identityRegistry =
            identityRegistry

        self.audit =
            audit

        self.signingKey =
            await signing.generateIdentity()
    }

    public func seal(
        payload:
            Data,
        owner:
            SecureIdentityID
    ) async throws
        -> SecureWorkloadEnvelope
    {
        _ = try await identityRegistry
            .identity(
                owner
            )

        let digest =
            SecureHash.sha256Hex(
                payload
            )

        let signingData =
            Data(
                "\(owner.rawValue.uuidString)|\(digest)"
                    .utf8
            )

        let signature =
            try await signing.sign(
                signingData,
                with:
                    signingKey
            )

        let envelope =
            SecureWorkloadEnvelope(
                workloadID:
                    UUID(),
                owner:
                    owner,
                createdAt:
                    Date(),
                payload:
                    payload,
                digest:
                    digest,
                signature:
                    signature
            )

        _ = try await audit.append(
            identity:
                owner,
            session:
                nil,
            operation:
                .sign,
            resource:
                "workload/\(envelope.workloadID.uuidString)",
            result:
                .success,
            detail:
                "Workload envelope signed."
        )

        return envelope
    }

    public func verify(
        _ envelope:
            SecureWorkloadEnvelope
    ) async throws -> Bool {

        _ = try await identityRegistry
            .identity(
                envelope.owner
            )

        let calculatedDigest =
            SecureHash.sha256Hex(
                envelope.payload
            )

        guard calculatedDigest ==
                envelope.digest
        else {
            return false
        }

        let signingData =
            Data(
                "\(envelope.owner.rawValue.uuidString)|\(envelope.digest)"
                    .utf8
            )

        return try await signing.verify(
            signingData,
            signature:
                envelope.signature
        )
    }
}

// MARK: - Security Monitor

public struct SecurityMonitorSnapshot:
    Sendable
{
    public let state:
        SecureSystemState

    public let auditIntegrity:
        Bool

    public let activeAuditEvents:
        Int

    public init(
        state:
            SecureSystemState,
        auditIntegrity:
            Bool,
        activeAuditEvents:
            Int
    ) {
        self.state =
            state
        self.auditIntegrity =
            auditIntegrity
        self.activeAuditEvents =
            activeAuditEvents
    }
}

public actor SecureCoreMonitor {

    private let core:
        SwiftSecureCore

    public init(
        core:
            SwiftSecureCore
    ) {
        self.core =
            core
    }

    public func snapshot()
        async
        -> SecurityMonitorSnapshot
    {
        SecurityMonitorSnapshot(
            state:
                await core.currentState(),
            auditIntegrity:
                await core.verifyAuditChain(),
            activeAuditEvents:
                await core.auditEvents().count
        )
    }
}

// MARK: - Example

public enum SwiftSecureCoreExample {

    public static func run()
        async throws
    {
        let core =
            try await SwiftSecureCore()

        await core.start()

        var capabilities =
            SecurityCapabilitySet()

        capabilities.insert(
            .readTelemetry
        )

        capabilities.insert(
            .executeWorkload
        )

        capabilities.insert(
            .readDeviceState
        )

        let principal =
            try await core.createIdentity(
                name:
                    "Industrial Control Operator",
                kind:
                    .human,
                roles: [
                    .operator
                ],
                capabilities:
                    capabilities
            )

        // Policy requiring operator role.

        await core.registerPolicy(
            SecurityPolicyRule(
                policyID:
                    SecurityPolicyID(
                        "telemetry-read"
                    ),
                requiredCapability:
                    .readTelemetry,
                allowedRoles: [
                    .operator,
                    .engineer,
                    .administrator
                ],
                resourcePrefix:
                    "telemetry/"
            )
        )

        // Authenticate.

        let credential =
            try await core.authenticate(
                principal:
                    principal
            )

        // Create session.

        let session =
            try await core.createSession(
                credential:
                    credential
            )

        // Issue signed token.

        let token =
            try await core.issueToken(
                credential:
                    credential,
                session:
                    session
            )

        // Verify token.

        let payload =
            try await core.verifyToken(
                token
            )

        secureCoreLog.notice(
            """
            Security token verified.
            Identity: \(payload.identity.rawValue.uuidString)
            Session: \(payload.session.rawValue.uuidString)
            """
        )

        // Authorization.

        try await core.authorize(
            principal:
                principal,
            capability:
                .readTelemetry,
            resource:
                "telemetry/motor/temperature"
        )

        // Generate encryption key.

        let key =
            await core.generateSymmetricKey(
                label:
                    "Industrial Telemetry"
            )

        let plaintext =
            Data(
                "temperature=72.4".utf8
            )

        let encrypted =
            try await core.encrypt(
                plaintext,
                using:
                    key.id
            )

        let decrypted =
            try await core.decrypt(
                encrypted,
                using:
                    key.id
            )

        secureCoreLog.notice(
            """
            Encryption round trip:
            \(String(
                data:
                    decrypted,
                encoding:
                    .utf8
                ) ?? "<invalid>")
            """
        )

        // Verify audit integrity.

        let auditOK =
            await core.verifyAuditChain()

        secureCoreLog.notice(
            "Audit chain valid: \(auditOK)"
        )

        // Monitor.

        let monitor =
            SecureCoreMonitor(
                core:
                    core
            )

        let snapshot =
            await monitor.snapshot()

        secureCoreLog.notice(
            """
            Security state:
            \(snapshot.state.rawValue)
            Audit integrity:
            \(snapshot.auditIntegrity)
            Events:
            \(snapshot.activeAuditEvents)
            """
        )

        await core.stop()
    }
}



