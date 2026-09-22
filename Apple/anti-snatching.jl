module AntiSnatching

using Statistics
using LinearAlgebra
using Random
using SHA

export DeviceObservation,
       RiskState,
       PrivacyConfig,
       AntiSnatchModel,
       evaluate,
       update!,
       forget!,
       risk_score

# ============================================================
# ANTI-SNATCHING PRIVACY ENGINE
#
# Design principles:
#   1. Raw sensor streams never leave the device.
#   2. The ML layer produces a risk estimate only.
#   3. Security actions are handled by a deterministic policy.
#   4. Features are short-lived and aggressively discarded.
#   5. No GPS history is required.
#   6. No continuous identity profiling is required.
#   7. Model state contains statistical information only.
# ============================================================


# ============================================================
# 1. PRIVACY CONFIGURATION
# ============================================================

Base.@kwdef mutable struct PrivacyConfig

    # Maximum number of observations retained locally.
    max_history::Int = 32

    # Maximum age of behavioural observations in seconds.
    retention_seconds::Float64 = 30.0

    # Noise added to non-security-critical analytics.
    differential_noise::Float64 = 0.01

    # Whether behavioural history is enabled.
    behavioural_history::Bool = true

    # Never persist raw sensor samples.
    persist_raw_sensor_data::Bool = false

    # Whether cryptographic integrity checks are enabled.
    integrity_checks::Bool = true

end


# ============================================================
# 2. DEVICE OBSERVATION
# ============================================================

"""
A deliberately compressed representation of a sensor window.

The system should receive already-derived features rather than
retaining raw accelerometer/gyroscope/microphone/location data.
"""
Base.@kwdef struct DeviceObservation

    timestamp::Float64

    # Motion
    acceleration_magnitude::Float64 = 0.0
    acceleration_variance::Float64 = 0.0

    angular_velocity::Float64 = 0.0
    angular_velocity_variance::Float64 = 0.0

    # Device orientation
    orientation_change::Float64 = 0.0

    # Interaction
    screen_interaction_rate::Float64 = 0.0
    unlock_attempts::Int = 0
    authentication_failures::Int = 0

    # Device/context changes
    charging_state_changed::Bool = false
    connectivity_changed::Bool = false
    bluetooth_state_changed::Bool = false

    # Optional acoustic/physical signal already converted
    # into a local feature. No audio is retained.
    acoustic_event_score::Float64 = 0.0

end


# ============================================================
# 3. RISK STATES
# ============================================================

@enum RiskState begin
    NORMAL
    ELEVATED
    SUSPICIOUS
    HIGH_RISK
end


# ============================================================
# 4. ML MODEL
# ============================================================

"""
Compact anomaly-detection model.

This is deliberately interpretable. A production Apple-class
implementation could replace the scoring layer with a calibrated
Core ML model while preserving the privacy/security architecture.
"""
Base.@kwdef mutable struct AntiSnatchModel

    # Learned baseline
    baseline_acceleration::Float64 = 1.0
    baseline_angular_velocity::Float64 = 0.5
    baseline_interaction_rate::Float64 = 1.0

    # Running variance
    acceleration_scale::Float64 = 0.5
    angular_scale::Float64 = 0.3
    interaction_scale::Float64 = 0.5

    # Model confidence
    confidence::Float64 = 0.5

    # Short-lived feature history
    history::Vector{Tuple{Float64,Float64}} = Tuple{Float64,Float64}[]

    # Privacy policy
    privacy::PrivacyConfig = PrivacyConfig()

    # Integrity state
    integrity_digest::Vector{UInt8} = UInt8[]

end


# ============================================================
# 5. SAFE NORMALISATION
# ============================================================

@inline function safe_zscore(
    x::Float64,
    μ::Float64,
    σ::Float64
)

    denominator = max(abs(σ), 1e-6)

    return abs(x - μ) / denominator
end


# ============================================================
# 6. FEATURE EXTRACTION
# ============================================================

"""
Convert an observation into a small privacy-preserving feature
vector.

Raw sensor information is not retained.
"""
function extract_features(
    obs::DeviceObservation,
    model::AntiSnatchModel
)

    motion_score =
        safe_zscore(
            obs.acceleration_magnitude,
            model.baseline_acceleration,
            model.acceleration_scale
        )

    rotational_score =
        safe_zscore(
            obs.angular_velocity,
            model.baseline_angular_velocity,
            model.angular_scale
        )

    interaction_score =
        safe_zscore(
            obs.screen_interaction_rate,
            model.baseline_interaction_rate,
            model.interaction_scale
        )

    authentication_score =
        min(
            obs.authentication_failures / 3.0,
            1.0
        )

    orientation_score =
        min(
            abs(obs.orientation_change) / π,
            1.0
        )

    connectivity_score =
        obs.connectivity_changed ? 1.0 : 0.0

    charging_score =
        obs.charging_state_changed ? 1.0 : 0.0

    bluetooth_score =
        obs.bluetooth_state_changed ? 1.0 : 0.0

    acoustic_score =
        clamp(obs.acoustic_event_score, 0.0, 1.0)

    return [
        motion_score,
        rotational_score,
        interaction_score,
        authentication_score,
        orientation_score,
        connectivity_score,
        charging_score,
        bluetooth_score,
        acoustic_score
    ]
end


# ============================================================
# 7. SNATCH SIGNATURE MODEL
# ============================================================

"""
Detects a rapid combination of physical and device-state changes.

The key idea is temporal correlation rather than one sensor
triggering the security response.
"""
function snatch_signature(
    features::Vector{Float64}
)

    motion,
    rotation,
    interaction,
    authentication,
    orientation,
    connectivity,
    charging,
    bluetooth,
    acoustic = features

    # Physical movement
    physical_component =
        0.30 * clamp(motion / 5.0, 0.0, 1.0) +
        0.20 * clamp(rotation / 5.0, 0.0, 1.0) +
        0.15 * orientation

    # Device-state anomaly
    device_component =
        0.10 * connectivity +
        0.05 * charging +
        0.05 * bluetooth

    # Security anomalies
    security_component =
        0.10 * authentication +
        0.05 * interaction

    # Optional local acoustic feature
    acoustic_component =
        0.05 * acoustic

    return clamp(
        physical_component +
        device_component +
        security_component +
        acoustic_component,
        0.0,
        1.0
    )
end


# ============================================================
# 8. TEMPORAL CONFIRMATION
# ============================================================

"""
Require multiple correlated observations.

This greatly reduces false positives from:
    dropping a phone
    running
    cycling
    taking a train
    putting the phone on a table
    normal orientation changes
"""
function temporal_confirmation(
    model::AntiSnatchModel,
    timestamp::Float64
)

    cutoff =
        timestamp -
        model.privacy.retention_seconds

    recent =
        filter(
            x -> x[1] >= cutoff,
            model.history
        )

    isempty(recent) && return 0.0

    scores = [x[2] for x in recent]

    # Recent high-risk persistence
    persistence =
        mean(scores)

    peak =
        maximum(scores)

    recent_high =
        count(x -> x >= 0.70, scores)

    density =
        recent_high / length(scores)

    return clamp(
        0.50 * persistence +
        0.30 * peak +
        0.20 * density,
        0.0,
        1.0
    )
end


# ============================================================
# 9. RISK FUSION
# ============================================================

function risk_score(
    model::AntiSnatchModel,
    obs::DeviceObservation
)

    features =
        extract_features(obs, model)

    instantaneous =
        snatch_signature(features)

    # Store only the derived risk score.
    if model.privacy.behavioural_history
        push!(
            model.history,
            (obs.timestamp, instantaneous)
        )
    end

    temporal =
        temporal_confirmation(
            model,
            obs.timestamp
        )

    # Temporal evidence is deliberately important.
    score =
        0.40 * instantaneous +
        0.60 * temporal

    return clamp(score, 0.0, 1.0)
end


# ============================================================
# 10. RISK CLASSIFICATION
# ============================================================

function classify_risk(
    score::Float64
)

    if score < 0.25
        return NORMAL

    elseif score < 0.50
        return ELEVATED

    elseif score < 0.75
        return SUSPICIOUS

    else
        return HIGH_RISK
    end
end


# ============================================================
# 11. MODEL UPDATE
# ============================================================

"""
Slowly adapt the model to normal device behaviour.

Important:
The adaptation rate is deliberately conservative so that a
short anomalous period cannot rapidly redefine "normal".
"""
function update!(
    model::AntiSnatchModel,
    obs::DeviceObservation;
    learning_rate::Float64 = 0.01
)

    α = clamp(learning_rate, 0.0, 0.05)

    # Update only under relatively normal conditions.
    features =
        extract_features(obs, model)

    instantaneous =
        snatch_signature(features)

    if instantaneous > 0.35
        return model
    end

    model.baseline_acceleration =
        (1 - α) * model.baseline_acceleration +
        α * obs.acceleration_magnitude

    model.baseline_angular_velocity =
        (1 - α) * model.baseline_angular_velocity +
        α * obs.angular_velocity

    model.baseline_interaction_rate =
        (1 - α) * model.baseline_interaction_rate +
        α * obs.screen_interaction_rate

    model.confidence =
        min(
            model.confidence + α,
            0.99
        )

    return model
end


# ============================================================
# 12. PRIVACY GARBAGE COLLECTION
# ============================================================

function forget!(
    model::AntiSnatchModel,
    current_time::Float64
)

    cutoff =
        current_time -
        model.privacy.retention_seconds

    filter!(
        x -> x[1] >= cutoff,
        model.history
    )

    # Hard maximum.
    if length(model.history) >
       model.privacy.max_history

        excess =
            length(model.history) -
            model.privacy.max_history

        deleteat!(
            model.history,
            1:excess
        )
    end

    return model
end


# ============================================================
# 13. INTEGRITY PROTECTION
# ============================================================

function calculate_integrity(
    model::AntiSnatchModel
)

    payload = string(
        model.baseline_acceleration,
        model.baseline_angular_velocity,
        model.baseline_interaction_rate,
        model.confidence
    )

    return sha256(payload)
end


function refresh_integrity!(
    model::AntiSnatchModel
)

    if model.privacy.integrity_checks
        model.integrity_digest =
            calculate_integrity(model)
    end

    return model
end


function integrity_valid(
    model::AntiSnatchModel
)

    if !model.privacy.integrity_checks
        return true
    end

    isempty(model.integrity_digest) &&
        return true

    return model.integrity_digest ==
           calculate_integrity(model)
end


# ============================================================
# 14. COMPLETE EVALUATION
# ============================================================

struct AntiSnatchResult

    score::Float64
    state::RiskState
    confidence::Float64
    integrity_valid::Bool

end


function evaluate(
    model::AntiSnatchModel,
    obs::DeviceObservation
)

    forget!(
        model,
        obs.timestamp
    )

    score =
        risk_score(
            model,
            obs
        )

    state =
        classify_risk(score)

    valid =
        integrity_valid(model)

    refresh_integrity!(model)

    return AntiSnatchResult(
        score,
        state,
        model.confidence,
        valid
    )
end


# ============================================================
# 15. DETERMINISTIC SECURITY POLICY
# ============================================================

"""
ML NEVER directly locks the device.

This function represents a separate security policy layer.

The real implementation would use platform security primitives
and require additional authenticated evidence before destructive
or irreversible actions.
"""
@enum SecurityAction begin
    NO_ACTION
    INCREASE_MONITORING
    STEP_UP_AUTHENTICATION
    PROTECT_SENSITIVE_FUNCTIONS
end


function security_policy(
    result::AntiSnatchResult
)

    # Integrity failure is treated independently from ML risk.
    if !result.integrity_valid
        return PROTECT_SENSITIVE_FUNCTIONS
    end

    if result.state == NORMAL
        return NO_ACTION

    elseif result.state == ELEVATED
        return INCREASE_MONITORING

    elseif result.state == SUSPICIOUS
        return STEP_UP_AUTHENTICATION

    elseif result.state == HIGH_RISK
        return PROTECT_SENSITIVE_FUNCTIONS
    end

    return NO_ACTION
end


# ============================================================
# 16. PRIVACY-PRESERVING DIFFERENTIAL NOISE
# ============================================================

"""
Noise is useful if aggregate diagnostics are exported.

It should NOT be added to safety/security decisions where
precision is required.
"""
function private_metric(
    value::Float64,
    scale::Float64,
    rng::AbstractRNG = Random.default_rng()
)

    noise =
        randn(rng) * scale

    return value + noise
end


# ============================================================
# 17. SIMULATION
# ============================================================

function simulate_normal(
    model::AntiSnatchModel;
    n::Int = 20,
    start_time::Float64 = 0.0
)

    results =
        AntiSnatchResult[]

    for i in 1:n

        t =
            start_time + i

        obs =
            DeviceObservation(
                timestamp=t,
                acceleration_magnitude=
                    1.0 + 0.1 * randn(),
                acceleration_variance=
                    0.1,
                angular_velocity=
                    0.5 + 0.05 * randn(),
                angular_velocity_variance=
                    0.05,
                orientation_change=
                    0.1,
                screen_interaction_rate=
                    1.0,
                unlock_attempts=
                    1,
                authentication_failures=
                    0
            )

        push!(
            results,
            evaluate(model, obs)
        )

        update!(
            model,
            obs
        )
    end

    return results
end


# ============================================================
# 18. SIMULATED RAPID EVENT
# ============================================================

function simulate_snatch_event(
    model::AntiSnatchModel;
    start_time::Float64 = 100.0
)

    results =
        AntiSnatchResult[]

    for i in 1:8

        t =
            start_time + i * 0.5

        # Artificially abnormal physical signature.
        obs =
            DeviceObservation(
                timestamp=t,
                acceleration_magnitude=
                    7.0 + rand(),
                acceleration_variance=
                    4.0,
                angular_velocity=
                    4.0 + rand(),
                angular_velocity_variance=
                    2.0,
                orientation_change=
                    2.5,
                screen_interaction_rate=
                    0.1,
                unlock_attempts=
                    0,
                authentication_failures=
                    2,
                connectivity_changed=
                    i == 4,
                bluetooth_state_changed=
                    i == 5,
                acoustic_event_score=
                    0.4
            )

        push!(
            results,
            evaluate(model, obs)
        )
    end

    return results
end


end # module

