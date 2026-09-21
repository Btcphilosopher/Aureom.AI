struct Player
    x::Float64
    y::Float64
    vx::Float64
    vy::Float64
    grounded::Bool
end

struct Physics
    gravity::Float64
    jump_velocity::Float64
    acceleration::Float64
    air_acceleration::Float64
    friction::Float64
    max_speed::Float64
    max_fall_speed::Float64
end

function update_player(
    p::Player,
    phys::Physics,
    left::Bool,
    right::Bool,
    jump_pressed::Bool,
    jump_held::Bool,
    dt::Float64
)
    x, y = p.x, p.y
    vx, vy = p.vx, p.vy

    # --------------------------------------------------
    # HORIZONTAL MOVEMENT
    # --------------------------------------------------

    direction = (right ? 1.0 : 0.0) - (left ? 1.0 : 0.0)

    accel = p.grounded ?
        phys.acceleration :
        phys.air_acceleration

    vx += direction * accel * dt

    # Friction when there is no directional input
    if direction == 0
        friction = phys.friction * dt

        if abs(vx) <= friction
            vx = 0.0
        else
            vx -= sign(vx) * friction
        end
    end

    vx = clamp(vx, -phys.max_speed, phys.max_speed)

    # --------------------------------------------------
    # JUMP
    # --------------------------------------------------

    if jump_pressed && p.grounded
        vy = phys.jump_velocity
    end

    # --------------------------------------------------
    # VARIABLE JUMP HEIGHT
    # --------------------------------------------------

    # Releasing jump early cuts upward velocity.
    if !jump_held && vy > 0
        vy *= 0.65
    end

    # --------------------------------------------------
    # GRAVITY
    # --------------------------------------------------

    vy -= phys.gravity * dt
    vy = max(vy, -phys.max_fall_speed)

    # --------------------------------------------------
    # INTEGRATION
    # --------------------------------------------------

    x += vx * dt
    y += vy * dt

    return Player(
        x,
        y,
        vx,
        vy,
        p.grounded
    )
end













struct Planet
    name::String
    gravity::Float64
end

struct Player
    x::Float64
    y::Float64
    vx::Float64
    vy::Float64
    grounded::Bool
end

struct Physics
    jump_velocity::Float64
    acceleration::Float64
    air_acceleration::Float64
    friction::Float64
    max_speed::Float64
    max_fall_speed::Float64
end

Then:

function update_player(
    p::Player,
    planet::Planet,
    physics::Physics,
    left::Bool,
    right::Bool,
    jump::Bool,
    dt::Float64
)

    x = p.x
    y = p.y
    vx = p.vx
    vy = p.vy

    # ---------------------------
    # Horizontal movement
    # ---------------------------

    direction =
        (right ? 1.0 : 0.0) -
        (left  ? 1.0 : 0.0)

    acceleration =
        p.grounded ?
        physics.acceleration :
        physics.air_acceleration

    vx += direction * acceleration * dt

    # friction
    if direction == 0
        vx *= 0.90
    end

    vx = clamp(
        vx,
        -physics.max_speed,
        physics.max_speed
    )

    # ---------------------------
    # Jump
    # ---------------------------

    if jump && p.grounded
        vy = physics.jump_velocity
    end

    # ---------------------------
    # PLANETARY GRAVITY
    # ---------------------------

    vy -= planet.gravity * dt

    vy = max(
        vy,
        -physics.max_fall_speed
    )

    # ---------------------------
    # Position integration
    # ---------------------------

    x += vx * dt
    y += vy * dt

    return Player(
        x,
        y,
        vx,
        vy,
        p.grounded
    )
end

Now we can simply swap planets:

earth  = Planet("Earth", 9.81)
moon   = Planet("Moon", 1.62)
mars   = Planet("Mars", 3.71)
jupiter = Planet("Jupiter", 24.79)








struct Water
    density::Float64
    buoyancy::Float64
    drag::Float64
    swim_impulse::Float64
    horizontal_drag::Float64
end

struct Player
    x::Float64
    y::Float64
    vx::Float64
    vy::Float64
end

function underwater_update(
    p::Player,
    planet_gravity::Float64,
    water::Water,
    swim::Bool,
    left::Bool,
    right::Bool,
    dt::Float64
)

    x, y = p.x, p.y
    vx, vy = p.vx, p.vy

    # ----------------------------
    # Swimming impulse
    # ----------------------------

    if swim
        vy += water.swim_impulse
    end

    # ----------------------------
    # Gravity
    # ----------------------------

    vy -= planet_gravity * dt

    # ----------------------------
    # Buoyancy
    # ----------------------------

    vy += water.buoyancy * dt

    # ----------------------------
    # Water drag
    # ----------------------------

    vy -= water.drag * vy * abs(vy) * dt

    # ----------------------------
    # Horizontal movement
    # ----------------------------

    direction =
        (right ? 1.0 : 0.0) -
        (left ? 1.0 : 0.0)

    vx += direction * 20.0 * dt

    # horizontal water resistance
    vx *= exp(-water.horizontal_drag * dt)

    # ----------------------------
    # Integrate
    # ----------------------------

    x += vx * dt
    y += vy * dt

    return Player(x, y, vx, vy)
end

We could start with something like:

earth_g = 9.81

water = Water(
    1000.0,   # density kg/m³
    9.0,      # buoyancy acceleration
    0.15,     # vertical drag
    4.0,       # swimming impulse
    1.2       # horizontal drag
)








# ============================================================
# PROFESSOR OAK AI
# Adaptive NPC / Online ML Prototype
# Julia
# ============================================================

using Random
using Statistics

# ------------------------------------------------------------
# PLAYER MODEL
# ------------------------------------------------------------

mutable struct PlayerModel
    exploration::Float64
    aggression::Float64
    collection::Float64
    trading::Float64
    experimentation::Float64

    battles::Int
    pokemon_seen::Int
    pokemon_caught::Int

    type_affinity::Vector{Float64}
end

function PlayerModel()
    PlayerModel(
        0.5,       # exploration
        0.5,       # aggression
        0.5,       # collection
        0.5,       # trading
        0.5,       # experimentation
        0,
        0,
        0,
        zeros(18)
    )
end


# ------------------------------------------------------------
# OAK'S ACTIONS
# ------------------------------------------------------------

@enum OakAction begin
    GIVE_HINT
    GIVE_QUEST
    ASK_QUESTION
    TEACH_TYPE
    REQUEST_SPECIMEN
    GIVE_ITEM
    COMMENT_BATTLE
    SEND_TO_LOCATION
    DO_NOTHING
end

const ACTIONS = instances(OakAction)


# ------------------------------------------------------------
# OAK'S KNOWLEDGE MODEL
# ------------------------------------------------------------

mutable struct OakKnowledge
    known_species::Set{Int}
    known_locations::Set{Int}
    type_knowledge::Vector{Float64}
end

function OakKnowledge()
    OakKnowledge(
        Set{Int}(),
        Set{Int}(),
        zeros(18)
    )
end


# ------------------------------------------------------------
# OAK AI
# ------------------------------------------------------------

mutable struct OakAI
    player::PlayerModel
    knowledge::OakKnowledge

    # preference for each possible Oak action
    action_weights::Vector{Float64}

    # learning rate
    learning_rate::Float64

    # exploration probability
    exploration_rate::Float64
end

function OakAI()

    OakAI(
        PlayerModel(),
        OakKnowledge(),
        ones(length(ACTIONS)),
        0.08,
        0.15
    )

end


# ------------------------------------------------------------
# NORMALISE VALUE
# ------------------------------------------------------------

function clamp01(x)
    return clamp(x, 0.0, 1.0)
end


# ------------------------------------------------------------
# PLAYER OBSERVATION
# ------------------------------------------------------------

function observe_catch!(
    oak::OakAI,
    species::Int,
    pokemon_type::Int
)

    p = oak.player

    p.pokemon_caught += 1
    p.pokemon_seen += 1

    # Collection behaviour increases
    p.collection += 0.03

    # Type preference increases
    p.type_affinity[pokemon_type] += 0.05

    # Oak learns the species
    push!(oak.knowledge.known_species, species)

    # Keep values bounded
    p.collection = clamp01(p.collection)

end


function observe_seen!(
    oak::OakAI,
    species::Int
)

    oak.player.pokemon_seen += 1

    push!(
        oak.knowledge.known_species,
        species
    )

end


function observe_exploration!(
    oak::OakAI,
    location::Int
)

    p = oak.player

    p.exploration += 0.04

    p.exploration = clamp01(p.exploration)

    push!(
        oak.knowledge.known_locations,
        location
    )

end


function observe_trade!(
    oak::OakAI
)

    oak.player.trading += 0.08

    oak.player.trading =
        clamp01(oak.player.trading)

end


function observe_experiment!(
    oak::OakAI
)

    oak.player.experimentation += 0.05

    oak.player.experimentation =
        clamp01(oak.player.experimentation)

end


# ------------------------------------------------------------
# BATTLE OBSERVATION
# ------------------------------------------------------------

function observe_battle!(
    oak::OakAI,
    pokemon_type::Int,
    won::Bool,
    damage_ratio::Float64
)

    p = oak.player

    p.battles += 1

    # Battle behaviour
    p.aggression += 0.02

    if won
        p.aggression += 0.01
    end

    # Taking lots of damage indicates experimentation/risk
    if damage_ratio > 0.75
        p.experimentation += 0.03
    end

    # Learn player's preferred type
    p.type_affinity[pokemon_type] += 0.03

    p.aggression =
        clamp01(p.aggression)

    p.experimentation =
        clamp01(p.experimentation)

end


# ------------------------------------------------------------
# PLAYER PROFILE
# ------------------------------------------------------------

function player_profile(oak::OakAI)

    p = oak.player

    println("\n========== OAK PLAYER MODEL ==========")

    println(
        "Exploration:      ",
        round(p.exploration, digits=2)
    )

    println(
        "Aggression:       ",
        round(p.aggression, digits=2)
    )

    println(
        "Collection:       ",
        round(p.collection, digits=2)
    )

    println(
        "Trading:          ",
        round(p.trading, digits=2)
    )

    println(
        "Experimentation:  ",
        round(p.experimentation, digits=2)
    )

    println(
        "Battles:          ",
        p.battles
    )

    println(
        "Pokémon seen:     ",
        p.pokemon_seen
    )

    println(
        "Pokémon caught:   ",
        p.pokemon_caught
    )

    println(
        "Species known:    ",
        length(oak.knowledge.known_species)
    )

    println(
        "Locations known:  ",
        length(oak.knowledge.known_locations)
    )

    println("=======================================\n")

end


# ------------------------------------------------------------
# FEATURE VECTOR
# ------------------------------------------------------------

function features(oak::OakAI)

    p = oak.player

    return [
        p.exploration,
        p.aggression,
        p.collection,
        p.trading,
        p.experimentation,

        min(p.battles / 100, 1.0),
        min(p.pokemon_seen / 150, 1.0),
        min(p.pokemon_caught / 150, 1.0),

        length(oak.knowledge.known_locations) / 100
    ]

end


# ------------------------------------------------------------
# ACTION SCORING
# ------------------------------------------------------------

function action_scores(oak::OakAI)

    p = oak.player

    scores = zeros(length(ACTIONS))

    # -----------------------------------------
    # Give hint
    # -----------------------------------------

    scores[Int(GIVE_HINT)] =
        0.5 +
        (1.0 - p.experimentation) * 1.5

    # -----------------------------------------
    # Quest
    # -----------------------------------------

    scores[Int(GIVE_QUEST)] =
        0.5 +
        p.exploration * 2.0

    # -----------------------------------------
    # Ask question
    # -----------------------------------------

    scores[Int(ASK_QUESTION)] =
        0.5 +
        p.experimentation * 1.8

    # -----------------------------------------
    # Teach type
    # -----------------------------------------

    scores[Int(TEACH_TYPE)] =
        0.5 +
        (1.0 - p.experimentation) * 1.2

    # -----------------------------------------
    # Request specimen
    # -----------------------------------------

    scores[Int(REQUEST_SPECIMEN)] =
        0.5 +
        p.collection * 2.0

    # -----------------------------------------
    # Give item
    # -----------------------------------------

    scores[Int(GIVE_ITEM)] =
        0.4 +
        p.collection

    # -----------------------------------------
    # Comment on battle
    # -----------------------------------------

    scores[Int(COMMENT_BATTLE)] =
        0.5 +
        p.aggression * 2.0

    # -----------------------------------------
    # Send to location
    # -----------------------------------------

    scores[Int(SEND_TO_LOCATION)] =
        0.5 +
        p.exploration * 2.2

    # -----------------------------------------
    # Do nothing
    # -----------------------------------------

    scores[Int(DO_NOTHING)] = 0.15

    # Learned action weights
    scores .*= oak.action_weights

    return scores

end


# ------------------------------------------------------------
# OAK DECISION
# ------------------------------------------------------------

function choose_action(oak::OakAI)

    scores = action_scores(oak)

    # Exploration
    if rand() < oak.exploration_rate

        return rand(ACTIONS)

    end

    index = argmax(scores)

    return ACTIONS[index]

end


# ------------------------------------------------------------
# ONLINE REINFORCEMENT LEARNING
# ------------------------------------------------------------

function learn!(
    oak::OakAI,
    action::OakAction,
    reward::Float64
)

    index = Int(action)

    old_value =
        oak.action_weights[index]

    oak.action_weights[index] =
        old_value +
        oak.learning_rate *
        (reward - old_value)

end


# ------------------------------------------------------------
# OAK DIALOGUE
# ------------------------------------------------------------

function dialogue(
    oak::OakAI,
    action::OakAction
)

    p = oak.player

    if action == GIVE_HINT

        return """
Oak:
I have been watching your progress.

You seem to be experimenting less than you were
earlier. Perhaps there is something about this area
that you haven't discovered yet.
"""

    elseif action == GIVE_QUEST

        return """
Oak:
I've been studying the Pokémon population nearby.

Would you explore the area and report back to me
with anything unusual that you discover?
"""

    elseif action == ASK_QUESTION

        return """
Oak:
Tell me something.

What do you think makes this particular Pokémon
well suited to its environment?
"""

    elseif action == TEACH_TYPE

        return """
Oak:
Ah! Before you continue, there's something about
Pokémon types that you should consider carefully.

Observation is often more useful than brute force.
"""

    elseif action == REQUEST_SPECIMEN

        return """
Oak:
Your collection is becoming quite interesting.

I'd like you to find another specimen for my research.
I suspect it may reveal something about this region.
"""

    elseif action == GIVE_ITEM

        return """
Oak:
Take this.

A good researcher needs the right equipment.
"""

    elseif action == COMMENT_BATTLE

        return """
Oak:
That was an interesting battle.

I've noticed that you tend to favour direct attacks.
Perhaps we should investigate what happens when
you change your strategy.
"""

    elseif action == SEND_TO_LOCATION

        return """
Oak:
There is an unusual Pokémon habitat to the north.

I would like you to investigate it.
"""

    else

        return """
Oak:
Hmm...

I'll continue my research.
"""

    end

end


# ------------------------------------------------------------
# SIMULATED GAME
# ------------------------------------------------------------

function simulate_player!(oak::OakAI)

    println("Starting Professor Oak learning simulation...\n")

    for turn in 1:100

        event = rand(1:6)

        if event == 1

            observe_catch!(
                oak,
                rand(1:151),
                rand(1:18)
            )

        elseif event == 2

            observe_exploration!(
                oak,
                rand(1:50)
            )

        elseif event == 3

            observe_trade!(oak)

        elseif event == 4

            observe_experiment!(oak)

        elseif event == 5

            observe_battle!(
                oak,
                rand(1:18),
                rand(Bool),
                rand()
            )

        elseif event == 6

            observe_seen!(
                oak,
                rand(1:151)
            )

        end

        # Oak periodically makes a decision
        if turn % 10 == 0

            action = choose_action(oak)

            println("Turn $turn")
            println("Oak chooses: ", action)
            println(dialogue(oak, action))

            # Simulated player response
            reward = rand()

            learn!(
                oak,
                action,
                reward
            )

        end

    end

end


# ------------------------------------------------------------
# RUN
# ------------------------------------------------------------

oak = OakAI()

simulate_player!(oak)

player_profile(oak)

println("Final Oak action weights:")

for action in ACTIONS

    println(
        action,
        " => ",
        round(
            oak.action_weights[Int(action)],
            digits=3
        )
    )

end








struct CyberBall
    scan_accuracy::Float64
    capture_model::Vector{Float64}
    learning_rate::Float64
    attempts::Int
end

struct PokemonObservation
    species::Int
    level::Int
    hp_ratio::Float64
    aggression::Float64
    speed::Float64
    distance::Float64
    environment::Int
end

Then:

function cyberball_prediction(
    ball::CyberBall,
    p::PokemonObservation
)

    x = [
        p.level / 100,
        p.hp_ratio,
        p.aggression,
        p.speed / 100,
        p.distance / 100
    ]

    score = dot(
        ball.capture_model[1:5],
        x
    )

    return 1 / (1 + exp(-score))

end





1. Game difficulty model

Give the game a stage variable:

stage = 0.0   # beginning
stage = 0.5   # mid-game
stage = 1.0   # end-game

Then calculate difficulty from several factors:

PLAYER
 ├── story progression
 ├── average Pokémon level
 ├── battle win rate
 ├── recent victories
 ├── team composition
 └── Cyberball discoveries
          │
          ▼
   DIFFICULTY MODEL
          │
          ▼
     ENCOUNTER

I'd avoid simply saying:

difficulty = stage * 100

Instead:

difficulty =
    0.40 * stage +
    0.25 * player_mastery +
    0.20 * recent_performance +
    0.15 * exploration_progress

That gives us a continuous difficulty signal.

2. Julia implementation
mutable struct DifficultyModel

    stage::Float64

    player_mastery::Float64
    recent_winrate::Float64
    exploration::Float64

    difficulty::Float64

end


function DifficultyModel()

    DifficultyModel(
        0.0,
        0.5,
        0.5,
        0.0,
        0.0
    )

end


function update_difficulty!(d::DifficultyModel)

    d.difficulty =
        0.40 * d.stage +
        0.25 * d.player_mastery +
        0.20 * d.recent_winrate +
        0.15 * d.exploration

    d.difficulty =
        clamp(d.difficulty, 0.0, 1.0)

end

Now we can change the difficulty continuously.

3. Pokémon level adjustment

Instead of making the final Pokémon absurdly powerful, use a controlled scaling curve.

function encounter_level(
    base_level::Int,
    difficulty::Float64
)

    bonus =
        round(Int, difficulty * 15)

    return base_level + bonus

end

For example:

EARLY GAME

Base:       Lv 8
Difficulty: 0.15
Result:     Lv 10


MID GAME

Base:       Lv 30
Difficulty: 0.55
Result:     Lv 38


LATE GAME

Base:       Lv 50
Difficulty: 0.90
Result:     Lv 64

But I'd go further.

4. Late-game difficulty should change behaviour

A difficult late-game Pokémon shouldn't merely have:

+20 level
+50 HP
+30 attack

Instead, the AI becomes more sophisticated.

Early game
RANDOM MOVE
RANDOM SWITCH
BASIC ATTACK
Mid-game
TYPE ADVANTAGE
STATUS MOVES
SWITCHING
Late-game
PREDICT PLAYER
TEAM SYNERGY
STATUS MANAGEMENT
SWITCH STRATEGY
MOVE COMBINATIONS

So difficulty becomes qualitative as well as quantitative.

5. ML version

This is where Professor Oak comes back into the system.

Oak's model could estimate:

function player_mastery(
    winrate,
    average_level,
    battle_count,
    recent_streak
)

    mastery =
        0.40 * winrate +
        0.20 * clamp(average_level / 100, 0, 1) +
        0.20 * clamp(battle_count / 100, 0, 1) +
        0.20 * clamp(recent_streak / 10, 0, 1)

    return clamp(mastery, 0, 1)

end

Then:

difficulty.player_mastery =
    player_mastery(
        0.82,    # win rate
        67,      # average level
        84,      # battles
        7        # win streak
    )

update_difficulty!(difficulty)

The game can therefore say:

This player is demonstrating substantial mastery.

and increase the sophistication of subsequent encounters.

6. Don't let DDA cheat

This is crucial.

A bad DDA system secretly changes the game whenever the player is winning.

I'd impose difficulty envelopes:

struct DifficultyLimits

    minimum_level::Int
    maximum_level::Int

    minimum_ai::Float64
    maximum_ai::Float64

end

For example:

STAGE 1
Level:       5–15
AI:          0.1–0.3

STAGE 2
Level:       15–30
AI:          0.3–0.5

STAGE 3
Level:       30–50
AI:          0.5–0.75

STAGE 4
Level:       45–70
AI:          0.7–0.95






/*
    POKEMON DYNAMIC DIFFICULTY
    Pure / Flat C

    No libraries except stdio/math.
    No dynamic allocation.
    No external ML framework.

    Difficulty depends on:
        - game stage
        - player mastery
        - recent win rate
        - team strength
        - exploration

    The system outputs:
        - encounter level
        - AI sophistication
        - enemy HP multiplier
        - enemy attack multiplier
        - enemy defence multiplier
        - tactical behaviour
*/

#include <stdio.h>
#include <math.h>

/* ---------------------------------------------------------
   CLAMP
   --------------------------------------------------------- */

float clamp(float x, float min, float max)
{
    if (x < min)
        return min;

    if (x > max)
        return max;

    return x;
}


/* ---------------------------------------------------------
   PLAYER STATE
   --------------------------------------------------------- */

float game_stage;
float player_mastery;
float recent_winrate;
float team_strength;
float exploration;


/* ---------------------------------------------------------
   DIFFICULTY STATE
   --------------------------------------------------------- */

float difficulty;

int encounter_level;

float ai_level;
float hp_multiplier;
float attack_multiplier;
float defence_multiplier;


/* ---------------------------------------------------------
   CALCULATE DIFFICULTY
   --------------------------------------------------------- */

void calculate_difficulty(void)
{
    difficulty =
        (game_stage      * 0.40f) +
        (player_mastery  * 0.25f) +
        (recent_winrate  * 0.20f) +
        (team_strength   * 0.10f) +
        (exploration     * 0.05f);

    difficulty = clamp(
        difficulty,
        0.0f,
        1.0f
    );
}


/* ---------------------------------------------------------
   CALCULATE ENCOUNTER LEVEL
   --------------------------------------------------------- */

int calculate_level(int base_level)
{
    int bonus;

    bonus =
        (int)roundf(
            difficulty * 15.0f
        );

    return base_level + bonus;
}


/* ---------------------------------------------------------
   CALCULATE STAT SCALING
   --------------------------------------------------------- */

void calculate_stats(void)
{
    hp_multiplier =
        1.0f +
        difficulty * 0.30f;

    attack_multiplier =
        1.0f +
        difficulty * 0.20f;

    defence_multiplier =
        1.0f +
        difficulty * 0.15f;
}


/* ---------------------------------------------------------
   AI SOPHISTICATION
   --------------------------------------------------------- */

void calculate_ai(void)
{
    ai_level = difficulty;

    if (ai_level < 0.25f)
    {
        printf("AI: BASIC\n");
        printf("    Random attacks\n");
        printf("    Limited switching\n");
    }

    else if (ai_level < 0.50f)
    {
        printf("AI: INTERMEDIATE\n");
        printf("    Type advantages\n");
        printf("    Basic switching\n");
        printf("    Status moves\n");
    }

    else if (ai_level < 0.75f)
    {
        printf("AI: ADVANCED\n");
        printf("    Type prediction\n");
        printf("    Tactical switching\n");
        printf("    Team synergy\n");
        printf("    Status management\n");
    }

    else
    {
        printf("AI: MASTER\n");
        printf("    Player prediction\n");
        printf("    Tactical switching\n");
        printf("    Team synergy\n");
        printf("    Move combinations\n");
        printf("    Adaptive strategy\n");
    }
}


/* ---------------------------------------------------------
   UPDATE PLAYER MASTERY
   --------------------------------------------------------- */

void update_mastery(
    int battles,
    int wins,
    float average_level
)
{
    float win_component;
    float battle_component;
    float level_component;

    if (battles > 0)
        win_component =
            (float)wins / (float)battles;
    else
        win_component = 0.0f;

    battle_component =
        clamp(
            (float)battles / 100.0f,
            0.0f,
            1.0f
        );

    level_component =
        clamp(
            average_level / 100.0f,
            0.0f,
            1.0f
        );

    player_mastery =
        win_component * 0.50f +
        battle_component * 0.20f +
        level_component * 0.30f;

    player_mastery =
        clamp(
            player_mastery,
            0.0f,
            1.0f
        );
}


/* ---------------------------------------------------------
   DISPLAY MODEL
   --------------------------------------------------------- */

void display_model(void)
{
    printf("\n");
    printf("========================================\n");
    printf("        PROFESSOR OAK DDA MODEL\n");
    printf("========================================\n");

    printf("Game stage:          %.2f\n", game_stage);
    printf("Player mastery:      %.2f\n", player_mastery);
    printf("Recent win rate:     %.2f\n", recent_winrate);
    printf("Team strength:       %.2f\n", team_strength);
    printf("Exploration:         %.2f\n", exploration);

    printf("----------------------------------------\n");

    printf("DIFFICULTY:          %.2f\n", difficulty);

    printf("----------------------------------------\n");

    printf("Encounter level:     %d\n",
           encounter_level);

    printf("HP multiplier:       %.2fx\n",
           hp_multiplier);

    printf("Attack multiplier:   %.2fx\n",
           attack_multiplier);

    printf("Defence multiplier:  %.2fx\n",
           defence_multiplier);

    printf("----------------------------------------\n");

    calculate_ai();

    printf("========================================\n");
}


/* ---------------------------------------------------------
   GAME EVENT
   --------------------------------------------------------- */

void battle_result(
    int won,
    float damage_taken
)
{
    if (won)
    {
        recent_winrate =
            recent_winrate * 0.90f +
            0.10f;
    }
    else
    {
        recent_winrate =
            recent_winrate * 0.90f;
    }

    /*
        High damage taken means the player
        is struggling, so don't immediately
        increase difficulty.
    */

    if (damage_taken > 0.75f)
    {
        player_mastery -= 0.03f;
    }

    else if (damage_taken < 0.30f && won)
    {
        player_mastery += 0.02f;
    }

    player_mastery =
        clamp(
            player_mastery,
            0.0f,
            1.0f
        );
}


/* ---------------------------------------------------------
   ADVANCE GAME STAGE
   --------------------------------------------------------- */

void set_game_stage(float stage)
{
    game_stage =
        clamp(
            stage,
            0.0f,
            1.0f
        );
}


/* ---------------------------------------------------------
   MAIN
   --------------------------------------------------------- */

int main(void)
{
    int base_level = 50;

    /*
        Example late-game player.
    */

    set_game_stage(0.90f);

    recent_winrate = 0.82f;

    team_strength = 0.78f;

    exploration = 0.85f;

    update_mastery(
        87,      /* battles */
        72,      /* wins */
        68.0f    /* average Pokémon level */
    );

    calculate_difficulty();

    encounter_level =
        calculate_level(base_level);

    calculate_stats();

    display_model();


    /*
        Simulate a successful easy victory.
    */

    printf("\nPLAYER WINS EASILY...\n");

    battle_result(
        1,
        0.20f
    );

    calculate_difficulty();

    encounter_level =
        calculate_level(base_level);

    calculate_stats();

    display_model();


    /*
        Simulate player struggling.
    */

    printf("\nPLAYER STRUGGLES...\n");

    battle_result(
        0,
        0.90f
    );

    calculate_difficulty();

    encounter_level =
        calculate_level(base_level);

    calculate_stats();

    display_model();

    return 0;
}






    RED ML BATTLE ADAPTATION
    Pokémon Gold-style prototype

    Pure / flat C
    No external libraries
    No dynamic allocation
    No neural-network framework

    Red analyses why he lost and changes
    his next team accordingly.
*/

#include <stdio.h>
#include <string.h>

/* ---------------------------------------------------------
   TYPES
   --------------------------------------------------------- */

#define MAX_TEAM 6
#define NUM_TYPES 18

#define FIRE       0
#define WATER      1
#define GRASS      2
#define ELECTRIC   3
#define GROUND     4
#define ICE        5
#define FIGHTING   6
#define PSYCHIC    7
#define ROCK       8
#define FLYING     9
#define BUG        10
#define POISON     11
#define GHOST      12
#define DRAGON     13
#define DARK       14
#define STEEL      15
#define FAIRY      16
#define NORMAL     17


/* ---------------------------------------------------------
   POKÉMON
   --------------------------------------------------------- */

typedef struct
{
    char name[32];

    int type1;
    int type2;

    int level;

    int attack;
    int defense;
    int speed;

} Pokemon;


/* ---------------------------------------------------------
   RED'S MACHINE LEARNING MEMORY
   --------------------------------------------------------- */

float player_type_threat[NUM_TYPES];

float physical_threat;
float special_threat;
float speed_threat;
float status_threat;

int losses;

float adaptation;


/* ---------------------------------------------------------
   TEAM
   --------------------------------------------------------- */

Pokemon red_team[MAX_TEAM];


/* ---------------------------------------------------------
   INITIAL RED TEAM
   --------------------------------------------------------- */

void create_initial_team(void)
{
    strcpy(red_team[0].name, "Pikachu");
    red_team[0].type1 = ELECTRIC;
    red_team[0].type2 = -1;
    red_team[0].level = 81;
    red_team[0].attack = 80;
    red_team[0].defense = 60;
    red_team[0].speed = 90;

    strcpy(red_team[1].name, "Espeon");
    red_team[1].type1 = PSYCHIC;
    red_team[1].type2 = -1;
    red_team[1].level = 73;
    red_team[1].attack = 65;
    red_team[1].defense = 60;
    red_team[1].speed = 95;

    strcpy(red_team[2].name, "Snorlax");
    red_team[2].type1 = NORMAL;
    red_team[2].type2 = -1;
    red_team[2].level = 75;
    red_team[2].attack = 110;
    red_team[2].defense = 100;
    red_team[2].speed = 30;

    strcpy(red_team[3].name, "Venusaur");
    red_team[3].type1 = GRASS;
    red_team[3].type2 = POISON;
    red_team[3].level = 77;
    red_team[3].attack = 82;
    red_team[3].defense = 83;
    red_team[3].speed = 80;

    strcpy(red_team[4].name, "Charizard");
    red_team[4].type1 = FIRE;
    red_team[4].type2 = FLYING;
    red_team[4].level = 77;
    red_team[4].attack = 100;
    red_team[4].defense = 78;
    red_team[4].speed = 100;

    strcpy(red_team[5].name, "Blastoise");
    red_team[5].type1 = WATER;
    red_team[5].type2 = -1;
    red_team[5].level = 77;
    red_team[5].attack = 83;
    red_team[5].defense = 100;
    red_team[5].speed = 78;
}


/* ---------------------------------------------------------
   RESET MEMORY
   --------------------------------------------------------- */

void initialise_learning(void)
{
    int i;

    for (i = 0; i < NUM_TYPES; i++)
        player_type_threat[i] = 0.0f;

    physical_threat = 0.0f;
    special_threat = 0.0f;
    speed_threat = 0.0f;
    status_threat = 0.0f;

    losses = 0;

    adaptation = 0.15f;
}


/* ---------------------------------------------------------
   RECORD PLAYER ATTACK
   --------------------------------------------------------- */

void observe_attack(
    int attacker_type,
    int physical,
    int damage,
    int attacker_speed,
    int status
)
{
    player_type_threat[attacker_type] +=
        (float)damage / 100.0f;

    if (physical)
        physical_threat +=
            (float)damage / 100.0f;
    else
        special_threat +=
            (float)damage / 100.0f;

    if (attacker_speed > 90)
        speed_threat += 0.15f;

    if (status)
        status_threat += 0.20f;
}


/* ---------------------------------------------------------
   LEARN FROM LOSS
   --------------------------------------------------------- */

void learn_from_loss(void)
{
    int i;

    losses++;

    /*
        Learning rate increases slightly after
        repeated defeats.
    */

    adaptation =
        0.15f +
        (float)losses * 0.05f;

    if (adaptation > 1.0f)
        adaptation = 1.0f;

    /*
        Normalize threat values.
    */

    for (i = 0; i < NUM_TYPES; i++)
    {
        if (player_type_threat[i] > 10.0f)
            player_type_threat[i] = 10.0f;
    }
}


/* ---------------------------------------------------------
   FIND MOST DANGEROUS TYPE
   --------------------------------------------------------- */

int strongest_player_type(void)
{
    int i;
    int strongest = 0;

    for (i = 1; i < NUM_TYPES; i++)
    {
        if (player_type_threat[i] >
            player_type_threat[strongest])
        {
            strongest = i;
        }
    }

    return strongest;
}


/* ---------------------------------------------------------
   TYPE COUNTER
   --------------------------------------------------------- */

int counter_type(int threat)
{
    if (threat == WATER)
        return GRASS;

    if (threat == FIRE)
        return WATER;

    if (threat == GRASS)
        return FIRE;

    if (threat == ELECTRIC)
        return GROUND;

    if (threat == GROUND)
        return WATER;

    if (threat == FLYING)
        return ELECTRIC;

    if (threat == PSYCHIC)
        return DARK;

    if (threat == FIGHTING)
        return PSYCHIC;

    if (threat == ROCK)
        return WATER;

    if (threat == ICE)
        return FIRE;

    if (threat == DRAGON)
        return ICE;

    return STEEL;
}


/* ---------------------------------------------------------
   BUILD ADAPTIVE TEAM
   --------------------------------------------------------- */

void adapt_team(void)
{
    int threat;
    int counter;

    threat = strongest_player_type();
    counter = counter_type(threat);

    /*
        Red replaces the weakest appropriate
        team member with a counter.
    */

    if (counter == GRASS)
    {
        strcpy(red_team[5].name, "Exeggutor");

        red_team[5].type1 = GRASS;
        red_team[5].type2 = PSYCHIC;

        red_team[5].level = 78;
        red_team[5].attack = 95;
        red_team[5].defense = 85;
        red_team[5].speed = 55;
    }

    else if (counter == GROUND)
    {
        strcpy(red_team[0].name, "Dugtrio");

        red_team[0].type1 = GROUND;
        red_team[0].type2 = -1;

        red_team[0].level = 82;
        red_team[0].attack = 100;
        red_team[0].defense = 50;
        red_team[0].speed = 120;
    }

    else if (counter == WATER)
    {
        strcpy(red_team[4].name, "Lapras");

        red_team[4].type1 = WATER;
        red_team[4].type2 = ICE;

        red_team[4].level = 80;
        red_team[4].attack = 85;
        red_team[4].defense = 95;
        red_team[4].speed = 60;
    }

    else if (counter == FIRE)
    {
        strcpy(red_team[3].name, "Arcanine");

        red_team[3].type1 = FIRE;
        red_team[3].type2 = -1;

        red_team[3].level = 79;
        red_team[3].attack = 110;
        red_team[3].defense = 80;
        red_team[3].speed = 95;
    }

    else if (counter == DARK)
    {
        strcpy(red_team[1].name, "Umbreon");

        red_team[1].type1 = DARK;
        red_team[1].type2 = -1;

        red_team[1].level = 80;
        red_team[1].attack = 65;
        red_team[1].defense = 110;
        red_team[1].speed = 65;
    }

    else if (counter == ICE)
    {
        strcpy(red_team[3].name, "Mamoswine");

        red_team[3].type1 = ICE;
        red_team[3].type2 = GROUND;

        red_team[3].level = 81;
        red_team[3].attack = 120;
        red_team[3].defense = 80;
        red_team[3].speed = 80;
    }
}


/* ---------------------------------------------------------
   DISPLAY RED'S TEAM
   --------------------------------------------------------- */

void display_team(void)
{
    int i;

    printf("\n");
    printf("=====================================\n");
    printf("          RED'S NEW TEAM\n");
    printf("=====================================\n");

    for (i = 0; i < MAX_TEAM; i++)
    {
        printf(
            "%d. %-12s Lv.%d\n",
            i + 1,
            red_team[i].name,
            red_team[i].level
        );
    }

    printf("=====================================\n");
}


/* ---------------------------------------------------------
   DISPLAY LEARNING MODEL
   --------------------------------------------------------- */

void display_learning(void)
{
    int threat;

    threat = strongest_player_type();

    printf("\n");
    printf("========== RED AI MEMORY ============\n");

    printf(
        "Losses:              %d\n",
        losses
    );

    printf(
        "Adaptation:          %.2f\n",
        adaptation
    );

    printf(
        "Physical threat:    %.2f\n",
        physical_threat
    );

    printf(
        "Special threat:     %.2f\n",
        special_threat
    );

    printf(
        "Speed threat:       %.2f\n",
        speed_threat
    );

    printf(
        "Status threat:      %.2f\n",
        status_threat
    );

    printf(
        "Strongest threat:   %d\n",
        threat
    );

    printf("=====================================\n");
}


/* ---------------------------------------------------------
   SIMULATE A LOSS
   --------------------------------------------------------- */

void simulate_loss(
    int player_type,
    int physical,
    int damage,
    int speed,
    int status
)
{
    printf("\n");
    printf("RED HAS LOST.\n");

    observe_attack(
        player_type,
        physical,
        damage,
        speed,
        status
    );

    learn_from_loss();

    display_learning();

    adapt_team();

    display_team();
}


/* ---------------------------------------------------------
   MAIN
   --------------------------------------------------------- */

int main(void)
{
    initialise_learning();

    create_initial_team();

    printf("INITIAL RED TEAM\n");

    display_team();


    /*
        PLAYER BEATS RED USING
        A STRONG ELECTRIC ATTACK.
    */

    simulate_loss(
        ELECTRIC,
        0,
        95,
        110,
        0
    );


    /*
        PLAYER BEATS RED AGAIN USING
        ELECTRIC ATTACKS.
    */

    simulate_loss(
        ELECTRIC,
        0,
        100,
        115,
        0
    );


    /*
        PLAYER THEN USES A FAST
        PHYSICAL ATTACKER.
    */

    simulate_loss(
        NORMAL,
        1,
        90,
        120,
        0
    );


    /*
        PLAYER USES STATUS EFFECTS.
    */

    simulate_loss(
        POISON,
        0,
        70,
        80,
        1
    );


    return 0;
}







/*
    RED REINFORCEMENT LEARNING
    Pure / flat C
    No malloc
    No external ML libraries

    Red learns which Pokemon to use based on repeated battles.

    RL model:

        STATE  = player's dominant threat profile
        ACTION = choose a Pokemon
        REWARD = battle performance
        Q      = learned value of Pokemon in that state

    Red uses epsilon-greedy exploration:
        - sometimes try something new
        - usually use what has worked before
*/

#include <stdio.h>
#include <stdlib.h>
#include <time.h>

/* ---------------------------------------------------------
   CONSTANTS
   --------------------------------------------------------- */

#define POKEMON_COUNT 20
#define TEAM_SIZE 6
#define STATES 32

#define TYPE_NORMAL   0
#define TYPE_FIRE     1
#define TYPE_WATER    2
#define TYPE_ELECTRIC 3
#define TYPE_GRASS    4
#define TYPE_ICE      5
#define TYPE_FIGHTING 6
#define TYPE_POISON   7
#define TYPE_GROUND   8
#define TYPE_FLYING   9
#define TYPE_PSYCHIC  10
#define TYPE_BUG      11
#define TYPE_ROCK     12
#define TYPE_GHOST    13
#define TYPE_DRAGON   14
#define TYPE_DARK     15
#define TYPE_STEEL    16

/* ---------------------------------------------------------
   POKEMON DATABASE
   --------------------------------------------------------- */

const char *pokemon_name[POKEMON_COUNT] =
{
    "Pikachu",
    "Espeon",
    "Snorlax",
    "Venusaur",
    "Charizard",
    "Blastoise",

    "Steelix",
    "Tyranitar",
    "Ampharos",
    "Heracross",
    "Skarmory",
    "Houndoom",
    "Kingdra",
    "Scizor",
    "Umbreon",
    "Gengar",
    "Jolteon",
    "Gyarados",
    "Alakazam",
    "Dragonite"
};

int pokemon_type1[POKEMON_COUNT] =
{
    TYPE_ELECTRIC,
    TYPE_PSYCHIC,
    TYPE_NORMAL,
    TYPE_GRASS,
    TYPE_FIRE,
    TYPE_WATER,

    TYPE_STEEL,
    TYPE_ROCK,
    TYPE_ELECTRIC,
    TYPE_BUG,
    TYPE_STEEL,
    TYPE_DARK,
    TYPE_WATER,
    TYPE_BUG,
    TYPE_DARK,
    TYPE_GHOST,
    TYPE_ELECTRIC,
    TYPE_WATER,
    TYPE_PSYCHIC,
    TYPE_DRAGON
};

int pokemon_type2[POKEMON_COUNT] =
{
    -1,
    -1,
    -1,
    TYPE_POISON,
    TYPE_FLYING,
    -1,

    TYPE_GROUND,
    TYPE_DARK,
    -1,
    TYPE_FIGHTING,
    TYPE_FLYING,
    TYPE_FIRE,
    TYPE_DRAGON,
    TYPE_STEEL,
    -1,
    TYPE_POISON,
    -1,
    TYPE_FLYING,
    -1,
    TYPE_FLYING
};

/* Rough strategic attributes */

int pokemon_attack[POKEMON_COUNT] =
{
    110, 65, 110, 82, 84, 83,
    85, 134, 75, 125, 80, 90,
    95, 130, 65, 65, 90, 125,
    50, 134
};

int pokemon_defense[POKEMON_COUNT] =
{
    60, 60, 110, 83, 78, 100,
    200, 110, 85, 95, 140, 90,
    95, 100, 130, 60, 55, 79,
    45, 95
};

int pokemon_speed[POKEMON_COUNT] =
{
    90, 110, 30, 80, 100, 78,
    30, 61, 55, 85, 70, 95,
    85, 65, 65, 110, 130, 81,
    120, 80
};

/* ---------------------------------------------------------
   RL MEMORY
   --------------------------------------------------------- */

/*
    Q[state][pokemon]

    This is Red's learned value for selecting a Pokemon
    under a particular observed player state.
*/

float Q[STATES][POKEMON_COUNT];

/* Learning parameters */

float learning_rate = 0.20f;
float discount = 0.80f;

/* Exploration starts relatively high */

float epsilon = 0.35f;

/* ---------------------------------------------------------
   PLAYER STATE
   --------------------------------------------------------- */

int player_type_threat[17];

int player_physical;
int player_special;
int player_fast;
int player_status;

int red_losses = 0;
int red_wins = 0;

/* ---------------------------------------------------------
   RANDOM
   --------------------------------------------------------- */

float random_float(void)
{
    return (float)rand() / (float)RAND_MAX;
}

/* ---------------------------------------------------------
   CLAMP
   --------------------------------------------------------- */

float clamp(float x, float a, float b)
{
    if (x < a) return a;
    if (x > b) return b;
    return x;
}

/* ---------------------------------------------------------
   BUILD PLAYER STATE
   --------------------------------------------------------- */

int build_state(void)
{
    int dominant_type = 0;
    int i;

    for (i = 1; i < 17; i++)
    {
        if (player_type_threat[i] >
            player_type_threat[dominant_type])
        {
            dominant_type = i;
        }
    }

    /*
        Compress the battle situation into 32 states.

        0-16  = dominant player type
        +16   = very physical
        +16   = very fast
    */

    int state = dominant_type;

    if (player_physical > 60)
        state += 16;

    if (player_fast > 60)
        state += 8;

    state %= STATES;

    return state;
}

/* ---------------------------------------------------------
   INITIALIZE LEARNING
   --------------------------------------------------------- */

void initialize_learning(void)
{
    int s;
    int p;

    for (s = 0; s < STATES; s++)
    {
        for (p = 0; p < POKEMON_COUNT; p++)
        {
            Q[s][p] = 0.0f;
        }
    }

    /*
        Red begins with some prior knowledge.

        This is not the learned component;
        it is simply his starting policy.
    */

    Q[0][0] = 5.0f;
    Q[0][1] = 5.0f;
    Q[0][2] = 5.0f;
    Q[0][3] = 5.0f;
    Q[0][4] = 5.0f;
    Q[0][5] = 5.0f;
}

/* ---------------------------------------------------------
   CHOOSE ACTION
   --------------------------------------------------------- */

int choose_pokemon(int state, int already_used[])
{
    int p;
    int best = -1;
    float best_value = -999999.0f;

    /*
        Exploration:
        randomly try a Pokemon that isn't already
        on the team.
    */

    if (random_float() < epsilon)
    {
        int attempts;

        for (attempts = 0; attempts < 100; attempts++)
        {
            p = rand() % POKEMON_COUNT;

            if (!already_used[p])
                return p;
        }
    }

    /*
        Exploitation:
        select highest learned Q value.
    */

    for (p = 0; p < POKEMON_COUNT; p++)
    {
        if (already_used[p])
            continue;

        if (Q[state][p] > best_value)
        {
            best_value = Q[state][p];
            best = p;
        }
    }

    return best;
}

/* ---------------------------------------------------------
   TYPE EFFECTIVENESS
   --------------------------------------------------------- */

float type_effect(int attack_type, int defender)
{
    int t1 = pokemon_type1[defender];
    int t2 = pokemon_type2[defender];

    float value = 1.0f;

    /*
        Simplified effectiveness model.
    */

    if (attack_type == TYPE_FIRE)
    {
        if (t1 == TYPE_GRASS ||
            t2 == TYPE_GRASS ||
            t1 == TYPE_BUG ||
            t2 == TYPE_BUG ||
            t1 == TYPE_STEEL ||
            t2 == TYPE_STEEL)
            value *= 2.0f;

        if (t1 == TYPE_WATER ||
            t2 == TYPE_WATER ||
            t1 == TYPE_ROCK ||
            t2 == TYPE_ROCK)
            value *= 0.5f;
    }

    if (attack_type == TYPE_WATER)
    {
        if (t1 == TYPE_FIRE ||
            t2 == TYPE_FIRE ||
            t1 == TYPE_ROCK ||
            t2 == TYPE_ROCK ||
            t1 == TYPE_GROUND ||
            t2 == TYPE_GROUND)
            value *= 2.0f;

        if (t1 == TYPE_GRASS ||
            t2 == TYPE_GRASS)
            value *= 0.5f;
    }

    if (attack_type == TYPE_ELECTRIC)
    {
        if (t1 == TYPE_WATER ||
            t2 == TYPE_WATER ||
            t1 == TYPE_FLYING ||
            t2 == TYPE_FLYING)
            value *= 2.0f;

        if (t1 == TYPE_GROUND ||
            t2 == TYPE_GROUND)
            value = 0.0f;
    }

    if (attack_type == TYPE_GRASS)
    {
        if (t1 == TYPE_WATER ||
            t2 == TYPE_WATER ||
            t1 == TYPE_GROUND ||
            t2 == TYPE_GROUND ||
            t1 == TYPE_ROCK ||
            t2 == TYPE_ROCK)
            value *= 2.0f;

        if (t1 == TYPE_FIRE ||
            t2 == TYPE_FIRE)
            value *= 0.5f;
    }

    if (attack_type == TYPE_ICE)
    {
        if (t1 == TYPE_DRAGON ||
            t2 == TYPE_DRAGON ||
            t1 == TYPE_FLYING ||
            t2 == TYPE_FLYING ||
            t1 == TYPE_GRASS ||
            t2 == TYPE_GRASS)
            value *= 2.0f;
    }

    return value;
}

/* ---------------------------------------------------------
   ESTIMATE PERFORMANCE
   --------------------------------------------------------- */

float pokemon_performance(int p, int state)
{
    int dominant_type = state % 16;

    float score = 0.0f;

    /*
        Defensive value against the player's
        dominant attack type.
    */

    if (dominant_type == TYPE_ELECTRIC)
    {
        if (pokemon_type1[p] == TYPE_GROUND ||
            pokemon_type2[p] == TYPE_GROUND)
            score += 40.0f;
    }

    if (dominant_type == TYPE_FIRE)
    {
        if (pokemon_type1[p] == TYPE_WATER ||
            pokemon_type2[p] == TYPE_WATER)
            score += 40.0f;
    }

    if (dominant_type == TYPE_WATER)
    {
        if (pokemon_type1[p] == TYPE_GRASS ||
            pokemon_type2[p] == TYPE_GRASS)
            score += 40.0f;
    }

    if (dominant_type == TYPE_GRASS)
    {
        if (pokemon_type1[p] == TYPE_FIRE ||
            pokemon_type2[p] == TYPE_FIRE)
            score += 40.0f;
    }

    /*
        Speed matters when Red is being outsped.
    */

    if (player_fast > 60)
    {
        if (pokemon_speed[p] > 90)
            score += 20.0f;
    }

    /*
        Defense matters against physical players.
    */

    if (player_physical > 60)
    {
        score += pokemon_defense[p] * 0.10f;
    }

    /*
        Attack matters when Red needs to finish fights.
    */

    score += pokemon_attack[p] * 0.05f;

    return score;
}

/* ---------------------------------------------------------
   REINFORCEMENT UPDATE
   --------------------------------------------------------- */

void update_q(int state, int action, float reward)
{
    float old_value;
    float target;

    old_value = Q[state][action];

    /*
        For this simplified one-step RL system:

            target = immediate reward

        The next state can later be added to create
        full temporal-difference learning.
    */

    target = reward;

    Q[state][action] =
        old_value +
        learning_rate * (target - old_value);
}

/* ---------------------------------------------------------
   LEARN FROM LOSS
   --------------------------------------------------------- */

void learn_from_loss(int state, int team[])
{
    int i;
    float reward;

    red_losses++;

    /*
        Every member of the losing team receives
        negative reinforcement.

        But Pokémon that were strategically good
        still receive a smaller penalty.
    */

    for (i = 0; i < TEAM_SIZE; i++)
    {
        int p = team[i];

        reward = -20.0f;

        /*
            Estimate whether this Pokémon was
            actually a reasonable answer to the
            observed player.
        */

        reward += pokemon_performance(p, state) * 0.20f;

        update_q(state, p, reward);
    }

    /*
        Increase exploration after repeated losses.

        Red becomes more willing to experiment.
    */

    epsilon += 0.04f;

    if (epsilon > 0.60f)
        epsilon = 0.60f;
}

/* ---------------------------------------------------------
   LEARN FROM WIN
   --------------------------------------------------------- */

void learn_from_win(int state, int team[])
{
    int i;

    red_wins++;

    for (i = 0; i < TEAM_SIZE; i++)
    {
        int p = team[i];

        /*
            Winning team receives positive reinforcement.
        */

        update_q(state, p, 25.0f);
    }

    /*
        After success Red exploits his knowledge more.
    */

    epsilon -= 0.03f;

    if (epsilon < 0.05f)
        epsilon = 0.05f;
}

/* ---------------------------------------------------------
   BUILD TEAM
   --------------------------------------------------------- */

void build_team(int state, int team[])
{
    int used[POKEMON_COUNT];
    int i;

    for (i = 0; i < POKEMON_COUNT; i++)
        used[i] = 0;

    for (i = 0; i < TEAM_SIZE; i++)
    {
        team[i] = choose_pokemon(state, used);
        used[team[i]] = 1;
    }
}

/* ---------------------------------------------------------
   DISPLAY TEAM
   --------------------------------------------------------- */

void display_team(int team[])
{
    int i;

    printf("\nRED'S TEAM\n");
    printf("----------------------------\n");

    for (i = 0; i < TEAM_SIZE; i++)
    {
        int p = team[i];

        printf("%d. %-12s Q = %7.2f\n",
               i + 1,
               pokemon_name[p],
               Q[build_state()][p]);
    }
}

/* ---------------------------------------------------------
   DISPLAY LEARNING
   --------------------------------------------------------- */

void display_learning(int state)
{
    int p;

    printf("\nLEARNED POLICY\n");
    printf("----------------------------\n");

    for (p = 0; p < POKEMON_COUNT; p++)
    {
        printf("%-12s %7.2f\n",
               pokemon_name[p],
               Q[state][p]);
    }

    printf("\nLosses: %d\n", red_losses);
    printf("Wins:   %d\n", red_wins);
    printf("Epsilon: %.2f\n", epsilon);
}

/* ---------------------------------------------------------
   SIMULATE PLAYER
   --------------------------------------------------------- */

void player_attack(
    int type,
    int physical,
    int speed,
    int status)
{
    int i;

    /*
        Forgetting factor:
        recent battles matter more than ancient battles.
    */

    for (i = 0; i < 17; i++)
        player_type_threat[i] =
            (int)(player_type_threat[i] * 0.90f);

    player_type_threat[type] += 25;

    if (physical)
        player_physical += 25;
    else
        player_special += 25;

    if (speed)
        player_fast += 25;

    if (status)
        player_status += 25;

    player_physical =
        (int)clamp(player_physical, 0, 100);

    player_special =
        (int)clamp(player_special, 0, 100);

    player_fast =
        (int)clamp(player_fast, 0, 100);

    player_status =
        (int)clamp(player_status, 0, 100);
}

/* ---------------------------------------------------------
   SIMULATE BATTLE
   --------------------------------------------------------- */

void simulate_battle(
    int type,
    int physical,
    int speed,
    int status,
    int red_won)
{
    int state;
    int team[TEAM_SIZE];

    /*
        Red observes the player.
    */

    player_attack(
        type,
        physical,
        speed,
        status);

    state = build_state();

    /*
        Red chooses a team using his current policy.
    */

    build_team(state, team);

    printf("\n=================================\n");

    if (red_won)
    {
        printf("RED WON THE BATTLE\n");

        learn_from_win(
            state,
            team);
    }
    else
    {
        printf("RED LOST THE BATTLE\n");

        learn_from_loss(
            state,
            team);
    }

    display_team(team);
}

/* ---------------------------------------------------------
   MAIN
   --------------------------------------------------------- */

int main(void)
{
    srand((unsigned int)time(NULL));

    initialize_learning();

    printf("RED REINFORCEMENT LEARNING SYSTEM\n");

    /*
        Battle 1:
        Player heavily uses Electric attacks.
    */

    simulate_battle(
        TYPE_ELECTRIC,
        0,
        1,
        0,
        0);

    /*
        Battle 2:
        Same player strategy.
        Red has now learned something.
    */

    simulate_battle(
        TYPE_ELECTRIC,
        0,
        1,
        0,
        0);

    /*
        Battle 3:
        Red starts adapting.
    */

    simulate_battle(
        TYPE_ELECTRIC,
        0,
        1,
        0,
        1);

    /*
        Battle 4:
        Player changes strategy.
    */

    simulate_battle(
        TYPE_WATER,
        1,
        0,
        0,
        0);

    /*
        Battle 5:
        Red learns from the new loss.
    */

    simulate_battle(
        TYPE_WATER,
        1,
        0,
        0,
        0);

    /*
        Battle 6:
        Test whether Red has adapted.
    */

    simulate_battle(
        TYPE_WATER,
        1,
        0,
        0,
        1);

    display_learning(build_state());

    return 0;
}









/*
    POKEMON GOLD REGIONAL ECONOMY + PPP
    -----------------------------------

    Pure flat C.

    No malloc.
    No external libraries.
    Fixed arrays.
    Simple functions.

    PPP MODEL:

        PPP = regional income / regional price level

    100.0 = national average purchasing power.

    Higher PPP:
        - trainers can afford more
        - shops can charge more
        - infrastructure is better funded
        - specialist Pokemon services are easier to support

    Lower PPP:
        - lower wages
        - cheaper local goods
        - greater economic scarcity
        - stronger sensitivity to expensive items
*/

#include <stdio.h>
#include <stdlib.h>
#include <time.h>

/* ---------------------------------------------------------
   CONSTANTS
   --------------------------------------------------------- */

#define CITY_COUNT 19
#define MAX_TEAM 6
#define POKEMON_COUNT 20

#define JOHTO 0
#define KANTO 1

/* ---------------------------------------------------------
   CITIES
   --------------------------------------------------------- */

const char *city_name[CITY_COUNT] =
{
    "New Bark",
    "Cherrygrove",
    "Violet",
    "Azalea",
    "Goldenrod",
    "Ecruteak",
    "Olivine",
    "Cianwood",
    "Mahogany",
    "Blackthorn",

    "Viridian",
    "Pewter",
    "Cerulean",
    "Vermilion",
    "Lavender",
    "Celadon",
    "Fuchsia",
    "Saffron",
    "Pallet"
};

/* 0 = Johto, 1 = Kanto */

int city_region[CITY_COUNT] =
{
    JOHTO, JOHTO, JOHTO, JOHTO, JOHTO,
    JOHTO, JOHTO, JOHTO, JOHTO, JOHTO,

    KANTO, KANTO, KANTO, KANTO, KANTO,
    KANTO, KANTO, KANTO, KANTO
};

/* Population, millions */

float city_population[CITY_COUNT] =
{
    0.03f,
    0.20f,
    0.15f,
    0.12f,
    1.20f,
    0.35f,
    0.55f,
    0.08f,
    0.10f,
    0.07f,

    0.50f,
    0.30f,
    0.70f,
    0.80f,
    0.18f,
    1.50f,
    0.25f,
    1.80f,
    0.05f
};

/* ---------------------------------------------------------
   ECONOMIC VARIABLES
   --------------------------------------------------------- */

/*
    Regional output per person.

    Fictional GDP-style measure.
*/

float income_per_person[CITY_COUNT] =
{
    28000.0f,
    30000.0f,
    29500.0f,
    27000.0f,
    38000.0f,
    35000.0f,
    37000.0f,
    25000.0f,
    26000.0f,
    28500.0f,

    33000.0f,
    31000.0f,
    36000.0f,
    39000.0f,
    32000.0f,
    46000.0f,
    35000.0f,
    50000.0f,
    34000.0f
};

/*
    Local consumer price index.

    100 = national average.
*/

float price_index[CITY_COUNT] =
{
     92.0f,
     99.0f,
     98.0f,
     90.0f,
    108.0f,
    103.0f,
    106.0f,
     87.0f,
     89.0f,
     94.0f,

    101.0f,
     96.0f,
    108.0f,
    111.0f,
     98.0f,
    118.0f,
    106.0f,
    123.0f,
     97.0f
};

/*
    PPP is calculated from income relative to prices.
*/

float ppp_index[CITY_COUNT];

/*
    Economic output.
*/

float city_output[CITY_COUNT];

/*
    Trainer purchasing power.
*/

float trainer_purchasing_power[CITY_COUNT];

/*
    Local unemployment.

    Used as an economic-pressure variable.
*/

float unemployment[CITY_COUNT] =
{
    5.0f, 4.8f, 5.2f, 6.2f, 4.1f,
    4.5f, 4.2f, 7.0f, 6.5f, 5.8f,

    4.6f, 5.0f, 4.3f, 4.0f, 5.1f,
    3.5f, 4.2f, 3.2f, 4.8f
};

/* ---------------------------------------------------------
   BASE ECONOMY
   --------------------------------------------------------- */

void calculate_economy(void)
{
    int i;

    for (i = 0; i < CITY_COUNT; i++)
    {
        /*
            PPP:

            income / price level

            multiplied by 100 to create
            an intuitive index.
        */

        ppp_index[i] =
            (income_per_person[i] / 35000.0f)
            *
            (100.0f / price_index[i])
            *
            100.0f;

        /*
            Output = population × income.
        */

        city_output[i] =
            city_population[i]
            *
            income_per_person[i];

        /*
            Trainer purchasing power.

            Slightly more sensitive to PPP than GDP.
        */

        trainer_purchasing_power[i] =
            ppp_index[i] * 0.85f;
    }
}

/* ---------------------------------------------------------
   PPP PRICE CALCULATION
   --------------------------------------------------------- */

float local_price(int city, float national_price)
{
    /*
        Example:

        National Potion = 300 P

        Celadon:
            300 × 1.18 = 354

        Cianwood:
            300 × 0.87 = 261
    */

    return national_price *
           (price_index[city] / 100.0f);
}

/* ---------------------------------------------------------
   TRAINER INCOME
   --------------------------------------------------------- */

float trainer_income(int city, int trainer_class)
{
    float base;

    /*
        Different trainer classes earn
        different amounts.
    */

    if (trainer_class == 0)
        base = 500.0f;

    else if (trainer_class == 1)
        base = 1200.0f;

    else if (trainer_class == 2)
        base = 2500.0f;

    else
        base = 5000.0f;

    /*
        Local wages respond to PPP.
    */

    return base *
           (ppp_index[city] / 100.0f);
}

/* ---------------------------------------------------------
   REGIONAL TAX REVENUE
   --------------------------------------------------------- */

float regional_tax(int city)
{
    /*
        Simplified 20% effective taxation.
    */

    return city_output[city] * 0.20f;
}

/* ---------------------------------------------------------
   INFRASTRUCTURE CAPACITY
   --------------------------------------------------------- */

float infrastructure_capacity(int city)
{
    /*
        Wealth + population produce infrastructure.

        Large rich cities receive the greatest capacity.
    */

    float capacity;

    capacity =
        ppp_index[city]
        *
        city_population[city];

    return capacity;
}

/* ---------------------------------------------------------
   POKEMON SERVICE COST
   --------------------------------------------------------- */

float pokemon_service_cost(
    int city,
    float national_cost)
{
    return local_price(
        city,
        national_cost);
}

/* ---------------------------------------------------------
   ECONOMIC SHOCK
   --------------------------------------------------------- */

void economic_shock(
    int city,
    float output_change,
    float price_change)
{
    income_per_person[city] *=
        (1.0f + output_change);

    price_index[city] *=
        (1.0f + price_change);

    calculate_economy();
}

/* ---------------------------------------------------------
   CITY REPORT
   --------------------------------------------------------- */

void city_report(int city)
{
    printf("\n");
    printf("----------------------------------------\n");
    printf("%s\n", city_name[city]);
    printf("----------------------------------------\n");

    printf("Region:             %s\n",
        city_region[city] == JOHTO
        ? "Johto"
        : "Kanto");

    printf("Population:         %.2f million\n",
        city_population[city]);

    printf("Income/person:      %.0f\n",
        income_per_person[city]);

    printf("Price index:        %.1f\n",
        price_index[city]);

    printf("PPP index:          %.1f\n",
        ppp_index[city]);

    printf("Trainer purchasing: %.1f\n",
        trainer_purchasing_power[city]);

    printf("Unemployment:       %.1f%%\n",
        unemployment[city]);

    printf("Economic output:    %.2f billion\n",
        city_output[city]);

    printf("Tax revenue:        %.2f billion\n",
        regional_tax(city));

    printf("Infrastructure:     %.2f\n",
        infrastructure_capacity(city));
}

/* ---------------------------------------------------------
   REGIONAL COMPARISON
   --------------------------------------------------------- */

void compare_regions(void)
{
    int i;

    float johto_output = 0.0f;
    float kanto_output = 0.0f;

    float johto_population = 0.0f;
    float kanto_population = 0.0f;

    for (i = 0; i < CITY_COUNT; i++)
    {
        if (city_region[i] == JOHTO)
        {
            johto_output += city_output[i];
            johto_population += city_population[i];
        }
        else
        {
            kanto_output += city_output[i];
            kanto_population += city_population[i];
        }
    }

    printf("\n========================================\n");
    printf("JOHTO VS KANTO ECONOMY\n");
    printf("========================================\n");

    printf("\nJOHTO\n");
    printf("Population: %.2f million\n",
        johto_population);

    printf("Output: %.2f billion\n",
        johto_output);

    printf("Output/person: %.0f\n",
        johto_output / johto_population);

    printf("\nKANTO\n");
    printf("Population: %.2f million\n",
        kanto_population);

    printf("Output: %.2f billion\n",
        kanto_output);

    printf("Output/person: %.0f\n",
        kanto_output / kanto_population);
}

/* ---------------------------------------------------------
   ECONOMICALLY ADJUSTED REWARD
   --------------------------------------------------------- */

float economic_reward(
    int city,
    float base_reward)
{
    /*
        A trainer winning in a poorer region
        receives slightly greater economic value.

        A wealthy city produces lower marginal
        utility from the same reward.
    */

    float purchasing_power;

    purchasing_power =
        ppp_index[city] / 100.0f;

    return base_reward /
           purchasing_power;
}

/* ---------------------------------------------------------
   RED'S ECONOMIC DECISION
   --------------------------------------------------------- */

float red_operating_budget[CITY_COUNT];

/*
    Red's budget depends upon local economic capacity.
*/

void calculate_red_budget(void)
{
    int i;

    for (i = 0; i < CITY_COUNT; i++)
    {
        /*
            Regional League infrastructure
            is partly funded by local output.
        */

        red_operating_budget[i] =
            regional_tax(i) * 0.01f;
    }
}

/* ---------------------------------------------------------
   RED'S TEAM COST
   --------------------------------------------------------- */

float pokemon_operating_cost(int pokemon)
{
    /*
        Abstract annualised training/maintenance cost.

        Stronger/specialist Pokemon cost more.
    */

    float cost;

    cost = 1000.0f + pokemon * 150.0f;

    return cost;
}

float team_cost(int team[])
{
    int i;
    float total = 0.0f;

    for (i = 0; i < MAX_TEAM; i++)
    {
        total += pokemon_operating_cost(team[i]);
    }

    return total;
}

/* ---------------------------------------------------------
   CAN RED AFFORD TEAM?
   --------------------------------------------------------- */

int team_affordable(
    int city,
    int team[])
{
    float cost;
    float budget;

    cost = team_cost(team);

    budget =
        red_operating_budget[city];

    if (cost <= budget)
        return 1;

    return 0;
}

/* ---------------------------------------------------------
   ECONOMIC TEAM SCORE
   --------------------------------------------------------- */

float economic_team_score(
    int city,
    int team[])
{
    float cost;
    float budget;

    cost = team_cost(team);
    budget = red_operating_budget[city];

    /*
        If a team is cheap relative to
        regional resources, score increases.
    */

    if (cost <= budget)
        return 1.0f + (budget - cost) / budget;

    /*
        If the team exceeds local capacity,
        it receives an economic penalty.
    */

    return budget / cost;
}

/* ---------------------------------------------------------
   FULL ECONOMIC REPORT
   --------------------------------------------------------- */

void economy_report(void)
{
    int i;

    calculate_economy();
    calculate_red_budget();

    printf("\n");
    printf("========================================\n");
    printf("POKEMON GOLD REGIONAL ECONOMY\n");
    printf("========================================\n");

    for (i = 0; i < CITY_COUNT; i++)
    {
        printf(
            "%-12s | PPP %6.1f | GDP %8.2f B | "
            "POP %5.2f M\n",
            city_name[i],
            ppp_index[i],
            city_output[i],
            city_population[i]);
    }
}

/* ---------------------------------------------------------
   MAIN
   --------------------------------------------------------- */

int main(void)
{
    int city;

    srand((unsigned int)time(NULL));

    calculate_economy();
    calculate_red_budget();

    economy_report();

    compare_regions();

    /*
        Detailed example:
        Goldenrod.
    */

    city = 4;

    city_report(city);

    printf("\n");
    printf("POKEMON ECONOMY EXAMPLES\n");
    printf("----------------------------------------\n");

    printf(
        "Potion in %s: %.0f P\n",
        city_name[city],
        local_price(city, 300.0f));

    printf(
        "Trainer income: %.0f P\n",
        trainer_income(city, 1));

    printf(
        "Pokemon service: %.0f P\n",
        pokemon_service_cost(city, 500.0f));

    /*
        Economic shock example.

        A port recession:
        - output -5%
        - prices +3%
    */

    printf("\nECONOMIC SHOCK\n");

    economic_shock(
        city,
        -0.05f,
        0.03f);

    city_report(city);

    return 0;
}







/*
    TEAM ROCKET DAO
    ----------------

    Fictional in-game organisational simulation.

    Pure / flat C
    No malloc
    No external libraries
    Fixed arrays
    No blockchain dependency

    DAO FEATURES:

        - Rocket members
        - Reputation
        - Treasury
        - Proposals
        - Voting
        - Voting power
        - Treasury expenditure
        - Regional operations
        - Leadership elections
        - Proposal history
        - DAO statistics

    This is a GAME SIMULATION, not a real cryptocurrency system.
*/

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

/* ---------------------------------------------------------
   CONSTANTS
   --------------------------------------------------------- */

#define MEMBERS 20
#define PROPOSALS 50
#define REGIONS 10
#define TRANSACTIONS 100

#define YES 1
#define NO 0

#define PROPOSAL_OPEN 0
#define PROPOSAL_PASSED 1
#define PROPOSAL_REJECTED 2

/* ---------------------------------------------------------
   MEMBERS
   --------------------------------------------------------- */

const char *member_name[MEMBERS] =
{
    "Giovanni",
    "Archer",
    "Ariana",
    "Proton",
    "Petrel",

    "Rocket Grunt 01",
    "Rocket Grunt 02",
    "Rocket Grunt 03",
    "Rocket Grunt 04",
    "Rocket Grunt 05",

    "Rocket Scientist 01",
    "Rocket Scientist 02",
    "Rocket Executive 01",
    "Rocket Executive 02",

    "Rocket Ranger 01",
    "Rocket Ranger 02",
    "Rocket Trader 01",
    "Rocket Trader 02",
    "Rocket Recruit 01",
    "Rocket Recruit 02"
};

/*
    Voting power.

    In this fictional DAO, voting power is based on
    reputation rather than one-person-one-vote.
*/

float reputation[MEMBERS] =
{
    1000,
    800,
    750,
    700,
    680,

    100,
    100,
    100,
    100,
    100,

    300,
    300,
    500,
    500,

    250,
    250,
    200,
    200,
    50,
    50
};

int active_member[MEMBERS];

/* ---------------------------------------------------------
   REGIONS
   --------------------------------------------------------- */

const char *region_name[REGIONS] =
{
    "New Bark",
    "Violet",
    "Azalea",
    "Goldenrod",
    "Ecruteak",
    "Olivine",
    "Mahogany",
    "Blackthorn",
    "Saffron",
    "Celadon"
};

/*
    Regional economic capacity.

    This connects the DAO to the previous
    Pokémon regional economy system.
*/

float regional_ppp[REGIONS] =
{
    96.0f,
    98.0f,
    94.0f,
    112.0f,
    105.0f,
    109.0f,
    93.0f,
    97.0f,
    130.0f,
    125.0f
};

/* Rocket influence */

float rocket_influence[REGIONS] =
{
    5.0f,
    10.0f,
    35.0f,
    60.0f,
    30.0f,
    45.0f,
    25.0f,
    15.0f,
    40.0f,
    55.0f
};

/* ---------------------------------------------------------
   TREASURY
   --------------------------------------------------------- */

float treasury = 1000000.0f;

/*
    Treasury categories.
*/

float research_budget = 200000.0f;
float operations_budget = 400000.0f;
float recruitment_budget = 100000.0f;
float reserve_budget = 300000.0f;

/* ---------------------------------------------------------
   PROPOSALS
   --------------------------------------------------------- */

char proposal_name[PROPOSALS][80];

int proposal_author[PROPOSALS];

float proposal_cost[PROPOSALS];

int proposal_region[PROPOSALS];

int proposal_status[PROPOSALS];

float proposal_yes[PROPOSALS];

float proposal_no[PROPOSALS];

int proposal_count = 0;

/* ---------------------------------------------------------
   TRANSACTION LOG
   --------------------------------------------------------- */

char transaction_name[TRANSACTIONS][80];

float transaction_amount[TRANSACTIONS];

int transaction_from[TRANSACTIONS];

int transaction_region[TRANSACTIONS];

int transaction_count = 0;

/* ---------------------------------------------------------
   INITIALISE DAO
   --------------------------------------------------------- */

void initialize_dao(void)
{
    int i;

    for (i = 0; i < MEMBERS; i++)
        active_member[i] = 1;

    printf("\nTEAM ROCKET DAO INITIALISED\n");
    printf("----------------------------\n");

    printf("Members: %d\n", MEMBERS);
    printf("Treasury: %.0f Pokedollars\n", treasury);
}

/* ---------------------------------------------------------
   VOTING POWER
   --------------------------------------------------------- */

float voting_power(int member)
{
    /*
        Reputation becomes voting weight.

        Square-root style weighting prevents the
        largest members from completely dominating.
    */

    return reputation[member] * 0.10f + 1.0f;
}

/* ---------------------------------------------------------
   CREATE PROPOSAL
   --------------------------------------------------------- */

int create_proposal(
    int author,
    const char *name,
    float cost,
    int region)
{
    int id;

    if (proposal_count >= PROPOSALS)
        return -1;

    id = proposal_count;

    strcpy(proposal_name[id], name);

    proposal_author[id] = author;
    proposal_cost[id] = cost;
    proposal_region[id] = region;

    proposal_status[id] = PROPOSAL_OPEN;

    proposal_yes[id] = 0.0f;
    proposal_no[id] = 0.0f;

    proposal_count++;

    printf("\nNEW DAO PROPOSAL\n");
    printf("----------------------------\n");

    printf("ID: %d\n", id);
    printf("Proposal: %s\n", proposal_name[id]);
    printf("Author: %s\n", member_name[author]);
    printf("Cost: %.0f\n", cost);
    printf("Region: %s\n", region_name[region]);

    return id;
}

/* ---------------------------------------------------------
   VOTE
   --------------------------------------------------------- */

void vote(
    int proposal,
    int member,
    int decision)
{
    float weight;

    if (proposal < 0 ||
        proposal >= proposal_count)
        return;

    if (!active_member[member])
        return;

    weight = voting_power(member);

    if (decision == YES)
        proposal_yes[proposal] += weight;
    else
        proposal_no[proposal] += weight;

    printf(
        "%s voted %s with %.2f voting power\n",
        member_name[member],
        decision == YES ? "YES" : "NO",
        weight);
}

/* ---------------------------------------------------------
   TREASURY CAPACITY
   --------------------------------------------------------- */

int treasury_can_afford(float cost)
{
    if (cost <= treasury)
        return 1;

    return 0;
}

/* ---------------------------------------------------------
   EXECUTE PROPOSAL
   --------------------------------------------------------- */

void execute_proposal(int proposal)
{
    int region;
    float cost;

    if (proposal < 0 ||
        proposal >= proposal_count)
        return;

    cost = proposal_cost[proposal];
    region = proposal_region[proposal];

    /*
        Proposal passes if YES > NO.
    */

    if (proposal_yes[proposal] >
        proposal_no[proposal])
    {
        proposal_status[proposal] =
            PROPOSAL_PASSED;

        if (!treasury_can_afford(cost))
        {
            printf(
                "\nPROPOSAL PASSED BUT TREASURY "
                "CANNOT FUND IT.\n");

            return;
        }

        treasury -= cost;

        rocket_influence[region] +=
            cost / 10000.0f;

        if (rocket_influence[region] > 100.0f)
            rocket_influence[region] = 100.0f;

        printf("\nPROPOSAL EXECUTED\n");
        printf("----------------------------\n");

        printf("%s\n",
            proposal_name[proposal]);

        printf("Cost: %.0f\n", cost);

        printf("Remaining treasury: %.0f\n",
            treasury);

        printf("Regional influence: %.1f\n",
            rocket_influence[region]);
    }
    else
    {
        proposal_status[proposal] =
            PROPOSAL_REJECTED;

        printf("\nPROPOSAL REJECTED\n");
        printf("----------------------------\n");

        printf("%s\n",
            proposal_name[proposal]);
    }
}

/* ---------------------------------------------------------
   REGIONAL ECONOMIC RETURN
   --------------------------------------------------------- */

float regional_return(int region)
{
    /*
        Wealthier regions have greater economic
        potential.

        This gives the DAO an economic reason to
        debate where resources should be deployed.
    */

    return regional_ppp[region] *
           (1.0f + rocket_influence[region] / 100.0f);
}

/* ---------------------------------------------------------
   ROI ESTIMATION
   --------------------------------------------------------- */

float proposal_roi(
    float cost,
    int region)
{
    float economic_value;

    economic_value =
        regional_return(region) * 10000.0f;

    return economic_value / cost;
}

/* ---------------------------------------------------------
   DAO TREASURY REPORT
   --------------------------------------------------------- */

void treasury_report(void)
{
    printf("\n");
    printf("========================================\n");
    printf("TEAM ROCKET DAO TREASURY\n");
    printf("========================================\n");

    printf("Total treasury: %.0f P\n",
        treasury);

    printf("Research:        %.0f P\n",
        research_budget);

    printf("Operations:      %.0f P\n",
        operations_budget);

    printf("Recruitment:     %.0f P\n",
        recruitment_budget);

    printf("Reserve:         %.0f P\n",
        reserve_budget);
}

/* ---------------------------------------------------------
   DAO MEMBER REPORT
   --------------------------------------------------------- */

void member_report(void)
{
    int i;

    printf("\n");
    printf("========================================\n");
    printf("ROCKET DAO MEMBERS\n");
    printf("========================================\n");

    for (i = 0; i < MEMBERS; i++)
    {
        printf(
            "%-20s REP %7.0f "
            "VOTE %7.2f\n",
            member_name[i],
            reputation[i],
            voting_power(i));
    }
}

/* ---------------------------------------------------------
   REGIONAL REPORT
   --------------------------------------------------------- */

void regional_report(void)
{
    int i;

    printf("\n");
    printf("========================================\n");
    printf("ROCKET REGIONAL ECONOMY\n");
    printf("========================================\n");

    for (i = 0; i < REGIONS; i++)
    {
        printf(
            "%-12s PPP %6.1f "
            "Influence %6.1f "
            "Return %8.1f\n",
            region_name[i],
            regional_ppp[i],
            rocket_influence[i],
            regional_return(i));
    }
}

/* ---------------------------------------------------------
   LEADERSHIP ELECTION
   --------------------------------------------------------- */

int elect_leader(void)
{
    int i;
    int leader = 0;
    float highest = -1.0f;

    for (i = 0; i < MEMBERS; i++)
    {
        if (!active_member[i])
            continue;

        if (reputation[i] > highest)
        {
            highest = reputation[i];
            leader = i;
        }
    }

    return leader;
}

/* ---------------------------------------------------------
   REPUTATION UPDATE
   --------------------------------------------------------- */

void update_reputation(
    int member,
    float change)
{
    reputation[member] += change;

    if (reputation[member] < 0.0f)
        reputation[member] = 0.0f;
}

/* ---------------------------------------------------------
   DAO LEARNING
   --------------------------------------------------------- */

/*
    The organisation itself can learn.

    Successful proposals increase the author's
    reputation.

    Failed proposals reduce it.

    This creates an evolutionary governance system.
*/

void learn_from_proposal(int proposal)
{
    int author;

    author = proposal_author[proposal];

    if (proposal_status[proposal] ==
        PROPOSAL_PASSED)
    {
        update_reputation(
            author,
            25.0f);
    }
    else
    {
        update_reputation(
            author,
            -10.0f);
    }
}

/* ---------------------------------------------------------
   SIMULATE DAO CYCLE
   --------------------------------------------------------- */

void dao_cycle(void)
{
    int proposal;

    /*
        Archer proposes an operation
        in Goldenrod.
    */

    proposal = create_proposal(
        1,
        "Goldenrod Rocket Expansion",
        150000.0f,
        3);

    /*
        Members vote.
    */

    vote(proposal, 0, YES);
    vote(proposal, 1, YES);
    vote(proposal, 2, YES);
    vote(proposal, 3, YES);

    vote(proposal, 5, NO);
    vote(proposal, 6, YES);
    vote(proposal, 10, YES);

    /*
        Execute.
    */

    execute_proposal(proposal);

    /*
        Update governance reputation.
    */

    learn_from_proposal(proposal);
}

/* ---------------------------------------------------------
   MAIN
   --------------------------------------------------------- */

int main(void)
{
    int leader;

    srand((unsigned int)time(NULL));

    initialize_dao();

    economy_report:
    regional_report();

    member_report();

    treasury_report();

    /*
        DAO governance cycle.
    */

    dao_cycle();

    /*
        Elect leader according to reputation.
    */

    leader = elect_leader();

    printf("\n");
    printf("========================================\n");
    printf("CURRENT ROCKET LEADER\n");
    printf("========================================\n");

    printf("%s\n",
        member_name[leader]);

    printf(
        "Reputation: %.0f\n",
        reputation[leader]);

    /*
        Final treasury.
    */

    treasury_report();

    return 0;
}








/*
    TEAM ROCKET NPC DATABASE
    ========================

    Pure flat C
    No malloc
    No external libraries

    Generates persistent random Team Rocket NPCs.

    Each NPC has:

        ID
        Name
        Age
        Region
        Rank
        Personality
        Occupation
        Loyalty
        Intelligence
        Combat skill
        Economic skill
        Reputation
        Salary
        Wealth
        Morale
        Wanted level
        Pokémon preference
        Number of Pokémon
        Experience
        Active status

    NPCs can later connect directly to:

        - Team Rocket DAO
        - Pokémon economy
        - Red reinforcement learning
        - Regional PPP
        - Missions
        - Promotions
        - Battles
*/

#include <stdio.h>
#include <stdlib.h>
#include <time.h>

/* =========================================================
   DATABASE SIZE
   ========================================================= */

#define MAX_NPCS 10000

int npc_count = 0;

/* =========================================================
   NAME DATABASE
   ========================================================= */

const char *first_names[] =
{
    "Alex",
    "Morgan",
    "Sam",
    "Jordan",
    "Taylor",
    "Jamie",
    "Chris",
    "Casey",
    "Riley",
    "Drew",
    "Avery",
    "Cameron",
    "Blake",
    "Elliot",
    "Charlie",
    "Robin",
    "Max",
    "Lee",
    "Kai",
    "Jesse"
};

#define FIRST_NAME_COUNT 20

const char *last_names[] =
{
    "Stone",
    "Black",
    "Cole",
    "Cross",
    "Graves",
    "Fox",
    "Reed",
    "Knight",
    "Drake",
    "Wolfe",
    "Ash",
    "Steel",
    "Vale",
    "Rook",
    "West",
    "North",
    "Frost",
    "Grant",
    "Miles",
    "Kane"
};

#define LAST_NAME_COUNT 20

/* =========================================================
   REGIONS
   ========================================================= */

const char *region_name[] =
{
    "New Bark",
    "Violet",
    "Azalea",
    "Goldenrod",
    "Ecruteak",
    "Olivine",
    "Cianwood",
    "Mahogany",
    "Blackthorn",
    "Viridian",
    "Pewter",
    "Cerulean",
    "Vermilion",
    "Lavender",
    "Celadon",
    "Fuchsia",
    "Saffron",
    "Pallet"
};

#define REGION_COUNT 18

/* =========================================================
   RANKS
   ========================================================= */

const char *rank_name[] =
{
    "Recruit",
    "Grunt",
    "Specialist",
    "Senior Grunt",
    "Commander",
    "Executive"
};

#define RANK_COUNT 6

/* =========================================================
   PERSONALITIES
   ========================================================= */

const char *personality_name[] =
{
    "Ambitious",
    "Loyal",
    "Greedy",
    "Cautious",
    "Aggressive",
    "Intellectual",
    "Opportunistic",
    "Idealistic",
    "Cynical",
    "Disciplined"
};

#define PERSONALITY_COUNT 10

/* =========================================================
   OCCUPATIONS
   ========================================================= */

const char *occupation_name[] =
{
    "Trainer",
    "Scientist",
    "Trader",
    "Mechanic",
    "Scout",
    "Courier",
    "Accountant",
    "Engineer",
    "Researcher",
    "Security",
    "Smuggler",
    "Administrator"
};

#define OCCUPATION_COUNT 12

/* =========================================================
   POKEMON PREFERENCES
   ========================================================= */

const char *pokemon_style[] =
{
    "Electric",
    "Fire",
    "Water",
    "Grass",
    "Poison",
    "Dark",
    "Steel",
    "Ground",
    "Psychic",
    "Flying",
    "Bug",
    "Rock",
    "Ghost",
    "Dragon",
    "Normal"
};

#define STYLE_COUNT 15

/* =========================================================
   NPC DATABASE
   ========================================================= */

/*
    Flat arrays rather than structs.

    This makes the database extremely easy to
    serialize, process and connect to a game engine.
*/

int npc_id[MAX_NPCS];

char npc_first[MAX_NPCS][32];
char npc_last[MAX_NPCS][32];

int npc_age[MAX_NPCS];

int npc_region[MAX_NPCS];
int npc_rank[MAX_NPCS];
int npc_personality[MAX_NPCS];
int npc_occupation[MAX_NPCS];

int npc_loyalty[MAX_NPCS];
int npc_intelligence[MAX_NPCS];
int npc_combat[MAX_NPCS];
int npc_economic_skill[MAX_NPCS];

int npc_reputation[MAX_NPCS];

float npc_salary[MAX_NPCS];
float npc_wealth[MAX_NPCS];

int npc_morale[MAX_NPCS];
int npc_wanted[MAX_NPCS];

int npc_pokemon_style_id[MAX_NPCS];
int npc_pokemon_count[MAX_NPCS];

int npc_experience[MAX_NPCS];

int npc_active[MAX_NPCS];

/* =========================================================
   RANDOM INTEGER
   ========================================================= */

int random_int(int min, int max)
{
    return min +
        rand() % (max - min + 1);
}

/* =========================================================
   RANDOM FLOAT
   ========================================================= */

float random_float(float min, float max)
{
    float r;

    r = (float)rand() /
        (float)RAND_MAX;

    return min + r * (max - min);
}

/* =========================================================
   CLAMP
   ========================================================= */

int clamp_int(int value, int min, int max)
{
    if (value < min)
        return min;

    if (value > max)
        return max;

    return value;
}

/* =========================================================
   GENERATE NPC
   ========================================================= */

int generate_npc(void)
{
    int id;

    if (npc_count >= MAX_NPCS)
        return -1;

    id = npc_count;

    npc_id[id] = id;

    /* -----------------------------------------
       Identity
       ----------------------------------------- */

    snprintf(
        npc_first[id],
        32,
        "%s",
        first_names[
            random_int(
                0,
                FIRST_NAME_COUNT - 1)
        ]);

    snprintf(
        npc_last[id],
        32,
        "%s",
        last_names[
            random_int(
                0,
                LAST_NAME_COUNT - 1)
        ]);

    npc_age[id] =
        random_int(18, 65);

    /* -----------------------------------------
       Social characteristics
       ----------------------------------------- */

    npc_region[id] =
        random_int(
            0,
            REGION_COUNT - 1);

    npc_rank[id] =
        random_int(
            0,
            RANK_COUNT - 1);

    npc_personality[id] =
        random_int(
            0,
            PERSONALITY_COUNT - 1);

    npc_occupation[id] =
        random_int(
            0,
            OCCUPATION_COUNT - 1);

    /* -----------------------------------------
       Attributes
       ----------------------------------------- */

    npc_loyalty[id] =
        random_int(20, 100);

    npc_intelligence[id] =
        random_int(20, 100);

    npc_combat[id] =
        random_int(10, 100);

    npc_economic_skill[id] =
        random_int(10, 100);

    npc_reputation[id] =
        random_int(0, 500);

    npc_morale[id] =
        random_int(40, 100);

    npc_wanted[id] =
        random_int(0, 20);

    /* -----------------------------------------
       Economy
       ----------------------------------------- */

    npc_salary[id] =
        500.0f +
        npc_rank[id] * 750.0f +
        npc_intelligence[id] * 15.0f;

    npc_wealth[id] =
        random_float(
            100.0f,
            10000.0f);

    /* -----------------------------------------
       Pokémon profile
       ----------------------------------------- */

    npc_pokemon_style_id[id] =
        random_int(
            0,
            STYLE_COUNT - 1);

    npc_pokemon_count[id] =
        random_int(1, 6);

    npc_experience[id] =
        random_int(0, 1000);

    npc_active[id] = 1;

    npc_count++;

    return id;
}

/* =========================================================
   GENERATE DATABASE
   ========================================================= */

void generate_database(int number)
{
    int i;

    for (i = 0; i < number; i++)
    {
        if (generate_npc() < 0)
            break;
    }
}

/* =========================================================
   DISPLAY NPC
   ========================================================= */

void display_npc(int id)
{
    printf("\n");
    printf("========================================\n");
    printf("TEAM ROCKET NPC #%d\n", npc_id[id]);
    printf("========================================\n");

    printf(
        "Name:              %s %s\n",
        npc_first[id],
        npc_last[id]);

    printf(
        "Age:               %d\n",
        npc_age[id]);

    printf(
        "Region:            %s\n",
        region_name[npc_region[id]]);

    printf(
        "Rank:              %s\n",
        rank_name[npc_rank[id]]);

    printf(
        "Personality:       %s\n",
        personality_name[npc_personality[id]]);

    printf(
        "Occupation:        %s\n",
        occupation_name[npc_occupation[id]]);

    printf("\n");

    printf(
        "Loyalty:           %d\n",
        npc_loyalty[id]);

    printf(
        "Intelligence:      %d\n",
        npc_intelligence[id]);

    printf(
        "Combat skill:      %d\n",
        npc_combat[id]);

    printf(
        "Economic skill:    %d\n",
        npc_economic_skill[id]);

    printf(
        "Reputation:        %d\n",
        npc_reputation[id]);

    printf(
        "Morale:            %d\n",
        npc_morale[id]);

    printf(
        "Wanted level:      %d\n",
        npc_wanted[id]);

    printf("\n");

    printf(
        "Salary:            %.0f P\n",
        npc_salary[id]);

    printf(
        "Wealth:            %.0f P\n",
        npc_wealth[id]);

    printf(
        "Pokemon style:     %s\n",
        pokemon_style[
            npc_pokemon_style_id[id]
        ]);

    printf(
        "Pokemon count:     %d\n",
        npc_pokemon_count[id]);

    printf(
        "Experience:        %d\n",
        npc_experience[id]);

    printf(
        "Active:            %s\n",
        npc_active[id]
        ? "YES"
        : "NO");
}

/* =========================================================
   NPC PROMOTION
   ========================================================= */

void promote_npc(int id)
{
    if (npc_rank[id] < RANK_COUNT - 1)
    {
        npc_rank[id]++;

        npc_salary[id] *= 1.30f;

        npc_reputation[id] += 100;

        printf(
            "\n%s %s promoted to %s.\n",
            npc_first[id],
            npc_last[id],
            rank_name[npc_rank[id]]);
    }
}

/* =========================================================
   NPC BATTLE
   ========================================================= */

void npc_battle_result(
    int id,
    int won)
{
    if (won)
    {
        npc_combat[id] += 2;
        npc_experience[id] += 50;
        npc_reputation[id] += 10;
        npc_morale[id] += 5;

        npc_morale[id] =
            clamp_int(
                npc_morale[id],
                0,
                100);
    }
    else
    {
        npc_combat[id] -= 1;
        npc_morale[id] -= 10;

        npc_morale[id] =
            clamp_int(
                npc_morale[id],
                0,
                100);

        /*
            A defeated Rocket member becomes
            slightly more likely to defect.
        */

        npc_loyalty[id] -= 2;

        if (npc_loyalty[id] < 0)
            npc_loyalty[id] = 0;
    }
}

/* =========================================================
   NPC ECONOMIC UPDATE
   ========================================================= */

void update_npc_economy(
    int id,
    float regional_ppp)
{
    /*
        Wages rise with regional purchasing power.
    */

    npc_salary[id] *=
        regional_ppp / 100.0f;

    /*
        Wealth accumulates from salary.
    */

    npc_wealth[id] +=
        npc_salary[id] * 0.05f;

    /*
        Better economic skill produces
        greater savings.
    */

    npc_wealth[id] +=
        npc_economic_skill[id] * 2.0f;
}

/* =========================================================
   NPC DAO VOTE
   ========================================================= */

int npc_vote(
    int id,
    int proposal_attractiveness)
{
    int score;

    /*
        Decision is influenced by:

        loyalty
        intelligence
        personality
        proposal attractiveness
    */

    score =
        npc_loyalty[id]
        +
        npc_intelligence[id] / 2
        +
        proposal_attractiveness;

    /*
        Greedy members care more about
        economic proposals.
    */

    if (npc_personality[id] == 2)
        score += npc_economic_skill[id];

    if (score > 100)
        return 1;

    return 0;
}

/* =========================================================
   RANDOM NPC QUERY
   ========================================================= */

int random_active_npc(void)
{
    int attempts;
    int id;

    for (attempts = 0; attempts < 100; attempts++)
    {
        id = random_int(
            0,
            npc_count - 1);

        if (npc_active[id])
            return id;
    }

    return 0;
}

/* =========================================================
   SEARCH BY REGION
   ========================================================= */

void list_region(int region)
{
    int i;

    printf("\n");
    printf("ROCKET MEMBERS IN %s\n",
        region_name[region]);

    printf("----------------------------------------\n");

    for (i = 0; i < npc_count; i++)
    {
        if (npc_region[i] == region &&
            npc_active[i])
        {
            printf(
                "#%04d %-16s Rank=%s Combat=%d\n",
                npc_id[i],
                npc_first[i],
                rank_name[npc_rank[i]],
                npc_combat[i]);
        }
    }
}

/* =========================================================
   DATABASE STATISTICS
   ========================================================= */

void database_statistics(void)
{
    int i;

    int recruits = 0;
    int grunts = 0;
    int specialists = 0;
    int commanders = 0;
    int executives = 0;

    float total_wealth = 0.0f;

    for (i = 0; i < npc_count; i++)
    {
        total_wealth += npc_wealth[i];

        if (npc_rank[i] == 0)
            recruits++;

        else if (npc_rank[i] == 1)
            grunts++;

        else if (npc_rank[i] == 2)
            specialists++;

        else if (npc_rank[i] == 4)
            commanders++;

        else if (npc_rank[i] == 5)
            executives++;
    }

    printf("\n");
    printf("========================================\n");
    printf("ROCKET NPC DATABASE STATISTICS\n");
    printf("========================================\n");

    printf("NPCs:          %d\n", npc_count);

    printf("Recruits:       %d\n", recruits);
    printf("Grunts:         %d\n", grunts);
    printf("Specialists:    %d\n", specialists);
    printf("Commanders:     %d\n", commanders);
    printf("Executives:     %d\n", executives);

    printf(
        "Total wealth:   %.0f P\n",
        total_wealth);
}

/* =========================================================
   MAIN
   ========================================================= */

int main(void)
{
    int id;
    int i;

    srand(
        (unsigned int)
        time(NULL));

    /*
        Generate 1,000 persistent Rocket NPCs.
    */

    generate_database(1000);

    printf(
        "Generated %d Team Rocket NPCs.\n",
        npc_count);

    /*
        Show a random member.
    */

    id = random_active_npc();

    display_npc(id);

    /*
        Simulate several battles.
    */

    for (i = 0; i < 5; i++)
    {
        npc_battle_result(
            id,
            rand() % 2);
    }

    /*
        Economic update.
    */

    update_npc_economy(
        id,
        112.0f);

    /*
        Possible promotion.
    */

    if (npc_experience[id] > 900)
        promote_npc(id);

    /*
        Show updated NPC.
    */

    display_npc(id);

    /*
        Region query.
    */

    list_region(
        npc_region[id]);

    /*
        Database statistics.
    */

    database_statistics();

    return 0;
}









/*
    POKEMON GOLD
    TEAM ROCKET AGENT-BASED SIMULATION
    ====================================

    PURE / FLAT C

    No malloc
    No external libraries
    Fixed-size arrays
    One source file

    SYSTEMS:

        1. 10,000 persistent Rocket NPCs
        2. Regional economy / PPP
        3. Rocket DAO
        4. NPC careers
        5. NPC movement
        6. NPC missions
        7. NPC battles
        8. NPC morale
        9. NPC loyalty
       10. Promotions
       11. Defections
       12. Treasury
       13. Regional Rocket influence
       14. Simple reinforcement learning
       15. Daily simulation ticks

    This is a fictional simulation layer inspired by
    Pokemon Gold/Silver.
*/

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

/* =========================================================
   CONFIGURATION
   ========================================================= */

#define MAX_NPCS        10000
#define MAX_PROPOSALS   100
#define MAX_TRANSACTIONS 500

#define CITY_COUNT      18
#define TEAM_SIZE       6

#define SIMULATION_DAYS 365

/* =========================================================
   REGIONS / CITIES
   ========================================================= */

const char *city_name[CITY_COUNT] =
{
    "New Bark",
    "Cherrygrove",
    "Violet",
    "Azalea",
    "Goldenrod",
    "Ecruteak",
    "Olivine",
    "Cianwood",
    "Mahogany",
    "Blackthorn",

    "Viridian",
    "Pewter",
    "Cerulean",
    "Vermilion",
    "Lavender",
    "Celadon",
    "Fuchsia",
    "Saffron"
};

/* 0 = Johto, 1 = Kanto */

int city_region[CITY_COUNT] =
{
    0,0,0,0,0,
    0,0,0,0,0,

    1,1,1,1,1,1,1,1
};

/* =========================================================
   REGIONAL ECONOMY
   ========================================================= */

float population[CITY_COUNT] =
{
    0.03f, 0.20f, 0.15f, 0.12f, 1.20f,
    0.35f, 0.55f, 0.08f, 0.10f, 0.07f,

    0.50f, 0.30f, 0.70f, 0.80f, 0.18f,
    1.50f, 0.25f, 1.80f
};

float income[CITY_COUNT] =
{
    28000, 30000, 29500, 27000, 38000,
    35000, 37000, 25000, 26000, 28500,

    33000, 31000, 36000, 39000, 32000,
    46000, 35000, 50000
};

float prices[CITY_COUNT] =
{
     92, 99, 98, 90,108,
    103,106, 87, 89, 94,

    101, 96,108,111, 98,
    118,106,123
};

float ppp[CITY_COUNT];

float rocket_influence[CITY_COUNT] =
{
     5,  5, 10, 35, 60,
    30, 45,  5, 25, 15,

    10,  5,  5, 10,  5,
    55,  5, 40
};

float regional_output[CITY_COUNT];

/* =========================================================
   ROCKET NPC IDENTITY
   ========================================================= */

const char *first_names[] =
{
    "Alex","Morgan","Sam","Jordan","Taylor",
    "Jamie","Chris","Casey","Riley","Drew",
    "Avery","Cameron","Blake","Elliot","Charlie",
    "Robin","Max","Lee","Kai","Jesse"
};

const char *last_names[] =
{
    "Stone","Black","Cole","Cross","Graves",
    "Fox","Reed","Knight","Drake","Wolfe",
    "Ash","Steel","Vale","Rook","West",
    "North","Frost","Grant","Miles","Kane"
};

#define FIRST_COUNT 20
#define LAST_COUNT 20

/* =========================================================
   RANKS
   ========================================================= */

#define RECRUIT       0
#define GRUNT         1
#define SPECIALIST    2
#define SENIOR        3
#define COMMANDER     4
#define EXECUTIVE     5

const char *rank_name[] =
{
    "Recruit",
    "Grunt",
    "Specialist",
    "Senior Grunt",
    "Commander",
    "Executive"
};

/* =========================================================
   NPC CAREER STATES
   ========================================================= */

#define STATE_WORK       0
#define STATE_TRAVEL     1
#define STATE_TRAIN      2
#define STATE_MISSION    3
#define STATE_BATTLE     4
#define STATE_RETURN     5
#define STATE_REST       6
#define STATE_VOTE       7
#define STATE_DEFECT     8

const char *state_name[] =
{
    "WORK",
    "TRAVEL",
    "TRAIN",
    "MISSION",
    "BATTLE",
    "RETURN",
    "REST",
    "VOTE",
    "DEFECT"
};

/* =========================================================
   PERSONALITIES
   ========================================================= */

#define AMBITIOUS      0
#define LOYAL          1
#define GREEDY         2
#define CAUTIOUS       3
#define AGGRESSIVE     4
#define INTELLECTUAL   5
#define OPPORTUNIST    6
#define IDEALIST       7
#define CYNICAL        8
#define DISCIPLINED    9

const char *personality_name[] =
{
    "Ambitious",
    "Loyal",
    "Greedy",
    "Cautious",
    "Aggressive",
    "Intellectual",
    "Opportunist",
    "Idealist",
    "Cynical",
    "Disciplined"
};

/* =========================================================
   NPC DATABASE
   ========================================================= */

int npc_count = 0;

int npc_id[MAX_NPCS];

char npc_first[MAX_NPCS][24];
char npc_last[MAX_NPCS][24];

int npc_age[MAX_NPCS];

int npc_city[MAX_NPCS];

int npc_rank[MAX_NPCS];
int npc_personality[MAX_NPCS];

int npc_state[MAX_NPCS];

int npc_loyalty[MAX_NPCS];
int npc_intelligence[MAX_NPCS];
int npc_combat[MAX_NPCS];
int npc_economic_skill[MAX_NPCS];

int npc_reputation[MAX_NPCS];
int npc_morale[MAX_NPCS];

int npc_experience[MAX_NPCS];

float npc_salary[MAX_NPCS];
float npc_wealth[MAX_NPCS];

int npc_missions[MAX_NPCS];
int npc_wins[MAX_NPCS];
int npc_losses[MAX_NPCS];

int npc_active[MAX_NPCS];

int npc_days_in_state[MAX_NPCS];

/* =========================================================
   POKEMON PREFERENCE
   ========================================================= */

#define STYLE_ELECTRIC 0
#define STYLE_FIRE     1
#define STYLE_WATER    2
#define STYLE_GRASS    3
#define STYLE_POISON   4
#define STYLE_DARK     5
#define STYLE_STEEL    6
#define STYLE_GROUND   7
#define STYLE_PSYCHIC  8
#define STYLE_FLYING   9
#define STYLE_BUG      10
#define STYLE_ROCK     11
#define STYLE_GHOST    12
#define STYLE_DRAGON   13
#define STYLE_NORMAL   14

const char *style_name[] =
{
    "Electric",
    "Fire",
    "Water",
    "Grass",
    "Poison",
    "Dark",
    "Steel",
    "Ground",
    "Psychic",
    "Flying",
    "Bug",
    "Rock",
    "Ghost",
    "Dragon",
    "Normal"
};

int npc_pokemon_style[MAX_NPCS];
int npc_pokemon_count[MAX_NPCS];

/* =========================================================
   DAO
   ========================================================= */

float rocket_treasury = 10000000.0f;

float dao_research = 2000000.0f;
float dao_operations = 4000000.0f;
float dao_recruitment = 1000000.0f;
float dao_reserve = 3000000.0f;

char proposal_name[MAX_PROPOSALS][80];

int proposal_author[MAX_PROPOSALS];
int proposal_city[MAX_PROPOSALS];

float proposal_cost[MAX_PROPOSALS];

float proposal_yes[MAX_PROPOSALS];
float proposal_no[MAX_PROPOSALS];

int proposal_active[MAX_PROPOSALS];
int proposal_count = 0;

/* =========================================================
   REINFORCEMENT LEARNING
   ========================================================= */

/*
    Very small organisational RL model.

    State:
        city
        morale
        rank
        economic environment

    Action:
        WORK
        TRAIN
        MISSION
        TRAVEL
        REST
        DEFECT

    Q[state][action]
*/

#define RL_STATES 32
#define RL_ACTIONS 6

#define ACTION_WORK    0
#define ACTION_TRAIN   1
#define ACTION_MISSION 2
#define ACTION_TRAVEL  3
#define ACTION_REST    4
#define ACTION_DEFECT  5

float Q[RL_STATES][RL_ACTIONS];

float rl_learning_rate = 0.15f;
float rl_discount = 0.80f;
float rl_epsilon = 0.20f;

/* =========================================================
   RANDOM
   ========================================================= */

int rnd(int min, int max)
{
    return min + rand() % (max - min + 1);
}

float rndf(float min, float max)
{
    float x;

    x = (float)rand() / RAND_MAX;

    return min + x * (max - min);
}

/* =========================================================
   CLAMP
   ========================================================= */

int clamp(int x, int min, int max)
{
    if (x < min)
        return min;

    if (x > max)
        return max;

    return x;
}

/* =========================================================
   ECONOMY
   ========================================================= */

void calculate_economy(void)
{
    int i;

    for (i = 0; i < CITY_COUNT; i++)
    {
        ppp[i] =
            (income[i] / 35000.0f)
            *
            (100.0f / prices[i])
            *
            100.0f;

        regional_output[i] =
            population[i] * income[i];
    }
}

/* =========================================================
   NPC CREATION
   ========================================================= */

int generate_npc(void)
{
    int id;

    if (npc_count >= MAX_NPCS)
        return -1;

    id = npc_count;

    npc_id[id] = id;

    strcpy(
        npc_first[id],
        first_names[rnd(0,FIRST_COUNT-1)]);

    strcpy(
        npc_last[id],
        last_names[rnd(0,LAST_COUNT-1)]);

    npc_age[id] = rnd(18,65);

    npc_city[id] = rnd(0,CITY_COUNT-1);

    npc_rank[id] = rnd(0,3);

    npc_personality[id] =
        rnd(0,9);

    npc_state[id] =
        STATE_WORK;

    npc_loyalty[id] =
        rnd(30,100);

    npc_intelligence[id] =
        rnd(20,100);

    npc_combat[id] =
        rnd(10,100);

    npc_economic_skill[id] =
        rnd(10,100);

    npc_reputation[id] =
        rnd(0,300);

    npc_morale[id] =
        rnd(40,100);

    npc_experience[id] =
        rnd(0,500);

    npc_salary[id] =
        500.0f +
        npc_rank[id] * 500.0f;

    npc_wealth[id] =
        rndf(100,10000);

    npc_missions[id] = 0;

    npc_wins[id] = 0;

    npc_losses[id] = 0;

    npc_pokemon_style[id] =
        rnd(0,14);

    npc_pokemon_count[id] =
        rnd(1,6);

    npc_active[id] = 1;

    npc_days_in_state[id] = 0;

    npc_count++;

    return id;
}

/* =========================================================
   DATABASE INITIALISATION
   ========================================================= */

void generate_database(int number)
{
    int i;

    for (i = 0; i < number; i++)
        generate_npc();
}

/* =========================================================
   RL STATE
   ========================================================= */

int build_rl_state(int id)
{
    int state;

    state = npc_city[id] % 16;

    if (npc_morale[id] < 40)
        state += 8;

    if (npc_rank[id] >= COMMANDER)
        state += 4;

    state %= RL_STATES;

    return state;
}

/* =========================================================
   RL ACTION
   ========================================================= */

int choose_action(int id)
{
    int state;
    int action;

    float best;
    float value;

    state = build_rl_state(id);

    /*
        Exploration.
    */

    if (rndf(0,1) < rl_epsilon)
        return rnd(0,RL_ACTIONS-1);

    /*
        Exploitation.
    */

    action = ACTION_WORK;

    best = -999999;

    for (int a = 0; a < RL_ACTIONS; a++)
    {
        value = Q[state][a];

        if (value > best)
        {
            best = value;
            action = a;
        }
    }

    return action;
}

/* =========================================================
   RL UPDATE
   ========================================================= */

void update_rl(
    int id,
    int action,
    float reward)
{
    int state;

    float old;
    float target;

    state = build_rl_state(id);

    old = Q[state][action];

    target = reward;

    Q[state][action] =
        old +
        rl_learning_rate *
        (target - old);
}

/* =========================================================
   NPC ECONOMY
   ========================================================= */

void update_npc_economy(int id)
{
    int city;

    city = npc_city[id];

    /*
        Regional PPP changes effective wages.
    */

    npc_salary[id] *=
        0.995f +
        ppp[city] / 20000.0f;

    /*
        Normal consumption.
    */

    npc_wealth[id] -=
        npc_salary[id] * 0.015f;

    /*
        Economic skill creates savings.
    */

    npc_wealth[id] +=
        npc_economic_skill[id] * 2.0f;

    if (npc_wealth[id] < 0)
        npc_wealth[id] = 0;
}

/* =========================================================
   WORK
   ========================================================= */

void npc_work(int id)
{
    float reward;

    reward = 5.0f;

    npc_wealth[id] +=
        npc_salary[id] * 0.10f;

    npc_reputation[id] += 1;

    npc_experience[id] += 2;

    update_rl(
        id,
        ACTION_WORK,
        reward);
}

/* =========================================================
   TRAIN
   ========================================================= */

void npc_train(int id)
{
    float reward;

    npc_combat[id] += rnd(0,2);

    npc_intelligence[id] += rnd(0,1);

    npc_experience[id] += 10;

    reward = 8.0f;

    update_rl(
        id,
        ACTION_TRAIN,
        reward);
}

/* =========================================================
   BATTLE
   ========================================================= */

void npc_battle(int id)
{
    int chance;
    int won;

    chance =
        npc_combat[id]
        +
        npc_experience[id] / 20
        +
        npc_morale[id] / 5;

    chance =
        clamp(chance,5,95);

    won =
        rnd(1,100) <= chance;

    if (won)
    {
        npc_wins[id]++;

        npc_reputation[id] += 15;

        npc_experience[id] += 50;

        npc_morale[id] =
            clamp(
                npc_morale[id] + 8,
                0,
                100);

        npc_wealth[id] += 500;

        update_rl(
            id,
            ACTION_MISSION,
            25.0f);
    }
    else
    {
        npc_losses[id]++;

        npc_reputation[id] -= 5;

        npc_morale[id] =
            clamp(
                npc_morale[id] - 15,
                0,
                100);

        npc_loyalty[id] -= 3;

        update_rl(
            id,
            ACTION_MISSION,
            -20.0f);
    }
}

/* =========================================================
   MISSION
   ========================================================= */

void npc_mission(int id)
{
    npc_missions[id]++;

    /*
        Mission success leads to battle.
    */

    if (rnd(0,100) < 70)
    {
        npc_battle(id);
    }
    else
    {
        npc_morale[id] -= 5;

        npc_wealth[id] -= 100;
    }
}

/* =========================================================
   TRAVEL
   ========================================================= */

void npc_travel(int id)
{
    int destination;

    destination =
        rnd(0,CITY_COUNT-1);

    npc_city[id] =
        destination;

    npc_wealth[id] -=
        100.0f;

    if (npc_wealth[id] < 0)
        npc_wealth[id] = 0;

    update_rl(
        id,
        ACTION_TRAVEL,
        2.0f);
}

/* =========================================================
   REST
   ========================================================= */

void npc_rest(int id)
{
    npc_morale[id] =
        clamp(
            npc_morale[id] + 5,
            0,
            100);

    update_rl(
        id,
        ACTION_REST,
        3.0f);
}

/* =========================================================
   PROMOTION
   ========================================================= */

void promotion_check(int id)
{
    int required;

    required =
        500 +
        npc_rank[id] * 500;

    if (npc_experience[id] >= required &&
        npc_reputation[id] >= required / 2)
    {
        if (npc_rank[id] < EXECUTIVE)
        {
            npc_rank[id]++;

            npc_salary[id] *= 1.30f;

            npc_reputation[id] += 50;

            printf(
                "PROMOTION: %s %s -> %s\n",
                npc_first[id],
                npc_last[id],
                rank_name[npc_rank[id]]);
        }
    }
}

/* =========================================================
   DEFECTION
   ========================================================= */

void check_defection(int id)
{
    int probability;

    /*
        Low loyalty + low morale =
        increased defection risk.
    */

    probability =
        100
        -
        npc_loyalty[id]
        -
        npc_morale[id] / 2;

    if (probability < 1)
        probability = 1;

    if (probability > 50)
        probability = 50;

    if (rnd(1,100) <= probability)
    {
        npc_active[id] = 0;

        npc_state[id] =
            STATE_DEFECT;

        printf(
            "DEFECTION: %s %s left Team Rocket.\n",
            npc_first[id],
            npc_last[id]);
    }
}

/* =========================================================
   DAO VOTING POWER
   ========================================================= */

float voting_power(int id)
{
    return
        npc_reputation[id] * 0.10f
        +
        npc_rank[id] * 10.0f;
}

/* =========================================================
   CREATE DAO PROPOSAL
   ========================================================= */

int create_proposal(
    int author,
    int city,
    const char *name,
    float cost)
{
    int p;

    if (proposal_count >= MAX_PROPOSALS)
        return -1;

    p = proposal_count;

    strcpy(
        proposal_name[p],
        name);

    proposal_author[p] = author;

    proposal_city[p] = city;

    proposal_cost[p] = cost;

    proposal_yes[p] = 0;

    proposal_no[p] = 0;

    proposal_active[p] = 1;

    proposal_count++;

    return p;
}

/* =========================================================
   DAO VOTE
   ========================================================= */

void dao_vote(
    int proposal,
    int member)
{
    float power;

    if (!npc_active[member])
        return;

    power =
        voting_power(member);

    /*
        Intelligent members evaluate
        economic proposals more carefully.
    */

    if (npc_personality[member] == GREEDY)
    {
        if (proposal_cost[proposal] < 500000)
            power *= 1.20f;
    }

    if (npc_personality[member] == CAUTIOUS)
    {
        if (proposal_cost[proposal] > 1000000)
            power *= 0.70f;
    }

    /*
        Basic vote probability.
    */

    if (rnd(0,100) <
        npc_loyalty[member])
    {
        proposal_yes[proposal] += power;
    }
    else
    {
        proposal_no[proposal] += power;
    }
}

/* =========================================================
   EXECUTE DAO PROPOSAL
   ========================================================= */

void execute_proposal(int p)
{
    int city;

    if (!proposal_active[p])
        return;

    city =
        proposal_city[p];

    if (proposal_yes[p] >
        proposal_no[p])
    {
        if (proposal_cost[p] <=
            rocket_treasury)
        {
            rocket_treasury -=
                proposal_cost[p];

            rocket_influence[city] +=
                proposal_cost[p] / 100000.0f;

            if (rocket_influence[city] > 100)
                rocket_influence[city] = 100;

            npc_reputation[
                proposal_author[p]
            ] += 50;

            printf(
                "DAO PASSED: %s\n",
                proposal_name[p]);

            printf(
                "Region: %s\n",
                city_name[city]);

            printf(
                "Cost: %.0f P\n",
                proposal_cost[p]);

            printf(
                "Influence: %.1f\n",
                rocket_influence[city]);
        }
    }
    else
    {
        npc_reputation[
            proposal_author[p]
        ] -= 10;

        printf(
            "DAO REJECTED: %s\n",
            proposal_name[p]);
    }

    proposal_active[p] = 0;
}

/* =========================================================
   DAILY AI
   ========================================================= */

void process_npc_day(int id)
{
    int action;

    if (!npc_active[id])
        return;

    npc_days_in_state[id]++;

    update_npc_economy(id);

    /*
        Select behaviour using RL.
    */

    action =
        choose_action(id);

    if (action == ACTION_WORK)
    {
        npc_state[id] =
            STATE_WORK;

        npc_work(id);
    }

    else if (action == ACTION_TRAIN)
    {
        npc_state[id] =
            STATE_TRAIN;

        npc_train(id);
    }

    else if (action == ACTION_MISSION)
    {
        npc_state[id] =
            STATE_MISSION;

        npc_mission(id);
    }

    else if (action == ACTION_TRAVEL)
    {
        npc_state[id] =
            STATE_TRAVEL;

        npc_travel(id);
    }

    else if (action == ACTION_REST)
    {
        npc_state[id] =
            STATE_REST;

        npc_rest(id);
    }

    else if (action == ACTION_DEFECT)
    {
        npc_state[id] =
            STATE_DEFECT;

        check_defection(id);
    }

    /*
        Promotion check.
    */

    promotion_check(id);

    /*
        Independent defection check.
    */

    if (npc_loyalty[id] < 20)
        check_defection(id);
}

/* =========================================================
   DAO DAILY CYCLE
   ========================================================= */

void dao_daily_cycle(int day)
{
    int author;
    int city;
    int proposal;
    int i;

    /*
        Every 30 days DAO creates a major proposal.
    */

    if (day % 30 != 0)
        return;

    author = rnd(0,npc_count-1);

    while (!npc_active[author])
        author = rnd(0,npc_count-1);

    city = rnd(0,CITY_COUNT-1);

    proposal =
        create_proposal(
            author,
            city,
            "Regional Rocket Expansion",
            rndf(100000,1000000));

    if (proposal < 0)
        return;

    /*
        Sample voting population.

        We don't need every NPC to vote every day.
    */

    for (i = 0; i < 1000; i++)
    {
        int member;

        member =
            rnd(0,npc_count-1);

        dao_vote(
            proposal,
            member);
    }

    execute_proposal(proposal);
}

/* =========================================================
   WORLD ECONOMIC CYCLE
   ========================================================= */

void economic_cycle(void)
{
    int i;

    for (i = 0; i < CITY_COUNT; i++)
    {
        /*
            Small stochastic economic movement.
        */

        income[i] *=
            1.0f + rndf(-0.002f,0.003f);

        prices[i] *=
            1.0f + rndf(-0.001f,0.002f);
    }

    calculate_economy();
}

/* =========================================================
   DISPLAY NPC
   ========================================================= */

void display_npc(int id)
{
    printf("\n");
    printf("========================================\n");
    printf("ROCKET NPC #%d\n",
        npc_id[id]);
    printf("========================================\n");

    printf(
        "Name:          %s %s\n",
        npc_first[id],
        npc_last[id]);

    printf(
        "Age:           %d\n",
        npc_age[id]);

    printf(
        "Location:      %s\n",
        city_name[npc_city[id]]);

    printf(
        "Rank:          %s\n",
        rank_name[npc_rank[id]]);

    printf(
        "Personality:   %s\n",
        personality_name[
            npc_personality[id]]);

    printf(
        "State:         %s\n",
        state_name[npc_state[id]]);

    printf("\n");

    printf(
        "Loyalty:       %d\n",
        npc_loyalty[id]);

    printf(
        "Morale:        %d\n",
        npc_morale[id]);

    printf(
        "Combat:        %d\n",
        npc_combat[id]);

    printf(
        "Intelligence:  %d\n",
        npc_intelligence[id]);

    printf(
        "Reputation:    %d\n",
        npc_reputation[id]);

    printf(
        "Experience:    %d\n",
        npc_experience[id]);

    printf("\n");

    printf(
        "Salary:        %.0f P\n",
        npc_salary[id]);

    printf(
        "Wealth:        %.0f P\n",
        npc_wealth[id]);

    printf(
        "Pokemon style: %s\n",
        style_name[
            npc_pokemon_style[id]]);

    printf(
        "Pokemon:       %d\n",
        npc_pokemon_count[id]);

    printf("\n");

    printf(
        "Missions:      %d\n",
        npc_missions[id]);

    printf(
        "Wins:          %d\n",
        npc_wins[id]);

    printf(
        "Losses:        %d\n",
        npc_losses[id]);

    printf(
        "Active:        %s\n",
        npc_active[id]
        ? "YES"
        : "NO");
}

/* =========================================================
   WORLD STATISTICS
   ========================================================= */

void world_statistics(void)
{
    int i;

    int active = 0;
    int defectors = 0;

    int recruits = 0;
    int grunts = 0;
    int specialists = 0;
    int commanders = 0;
    int executives = 0;

    float wealth = 0;

    for (i = 0; i < npc_count; i++)
    {
        if (npc_active[i])
            active++;
        else
            defectors++;

        wealth += npc_wealth[i];

        if (npc_rank[i] == RECRUIT)
            recruits++;

        if (npc_rank[i] == GRUNT)
            grunts++;

        if (npc_rank[i] == SPECIALIST)
            specialists++;

        if (npc_rank[i] == COMMANDER)
            commanders++;

        if (npc_rank[i] == EXECUTIVE)
            executives++;
    }

    printf("\n");
    printf("========================================\n");
    printf("WORLD STATISTICS\n");
    printf("========================================\n");

    printf(
        "Rocket population: %d\n",
        npc_count);

    printf(
        "Active:            %d\n",
        active);

    printf(
        "Defectors:         %d\n",
        defectors);

    printf("\n");

    printf(
        "Recruits:          %d\n",
        recruits);

    printf(
        "Grunts:            %d\n",
        grunts);

    printf(
        "Specialists:       %d\n",
        specialists);

    printf(
        "Commanders:        %d\n",
        commanders);

    printf(
        "Executives:        %d\n",
        executives);

    printf("\n");

    printf(
        "NPC wealth:        %.0f P\n",
        wealth);

    printf(
        "DAO treasury:      %.0f P\n",
        rocket_treasury);

    printf(
        "DAO proposals:     %d\n",
        proposal_count);
}

/* =========================================================
   REGIONAL ROCKET REPORT
   ========================================================= */

void regional_rocket_report(void)
{
    int i;

    printf("\n");
    printf("========================================\n");
    printf("REGIONAL ROCKET NETWORK\n");
    printf("========================================\n");

    for (i = 0; i < CITY_COUNT; i++)
    {
        printf(
            "%-12s PPP=%6.1f "
            "Influence=%6.1f "
            "GDP=%8.2f B\n",
            city_name[i],
            ppp[i],
            rocket_influence[i],
            regional_output[i]);
    }
}

/* =========================================================
   MAIN SIMULATION
   ========================================================= */

int main(void)
{
    int day;
    int sample;

    srand(
        (unsigned int)
        time(NULL));

    /*
        --------------------------------------
        INITIALISE WORLD
        --------------------------------------
    */

    calculate_economy();

    generate_database(
        MAX_NPCS);

    printf(
        "POKEMON GOLD ROCKET SIMULATION\n");

    printf(
        "Generated %d persistent NPCs.\n",
        npc_count);

    /*
        --------------------------------------
        SIMULATION
        --------------------------------------
    */

    for (day = 1;
         day <= SIMULATION_DAYS;
         day++)
    {
        int i;

        /*
            Economy changes.
        */

        economic_cycle();

        /*
            Process all active NPCs.
        */

        for (i = 0;
             i < npc_count;
             i++)
        {
            process_npc_day(i);
        }

        /*
            DAO governance.
        */

        dao_daily_cycle(day);

        /*
            Every 30 days show progress.
        */

        if (day % 30 == 0)
        {
            printf(
                "\n--- DAY %d ---\n",
                day);

            world_statistics();
        }
    }

    /*
        --------------------------------------
        FINAL REPORT
        --------------------------------------
    */

    world_statistics();

    regional_rocket_report();

    /*
        Pick a random NPC and inspect
        his complete life state.
    */

    sample =
        rnd(0,npc_count-1);

    display_npc(sample);

    return 0;
}







/*
    POKEMON GOLD - SWITCH ONLINE BATTLE PROTOTYPE
    ------------------------------------------------

    Single-file C prototype.

    Features:
      - Two-player online battle architecture
      - Battle-code matchmaking
      - Gen II-style turn system
      - Six Pokemon per trainer
      - Type effectiveness
      - Physical / special attacks
      - Critical hits
      - Status effects
      - Battle synchronization
      - Opponent statistics
      - Adaptive Red AI

    Build on a normal computer:

        gcc -O2 pokemon_online.c -o pokemon_online

    This is an architecture/gameplay prototype.
    Nintendo Switch networking would require replacing
    network_*() with Nintendo's approved networking APIs.
*/

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#define TEAM_SIZE       6
#define MAX_MOVES       4
#define MAX_PLAYERS     100
#define MAX_BATTLES     1000
#define MAX_TYPES       17
#define MAX_HISTORY     64

#define TRUE  1
#define FALSE 0

/* ---------------------------------------------------------
   TYPES
   --------------------------------------------------------- */

enum
{
    TYPE_NORMAL,
    TYPE_FIGHTING,
    TYPE_FLYING,
    TYPE_POISON,
    TYPE_GROUND,
    TYPE_ROCK,
    TYPE_BUG,
    TYPE_GHOST,
    TYPE_FIRE,
    TYPE_WATER,
    TYPE_GRASS,
    TYPE_ELECTRIC,
    TYPE_PSYCHIC,
    TYPE_ICE,
    TYPE_DRAGON,
    TYPE_DARK,
    TYPE_STEEL
};

const char *type_name[MAX_TYPES] =
{
    "Normal",
    "Fighting",
    "Flying",
    "Poison",
    "Ground",
    "Rock",
    "Bug",
    "Ghost",
    "Fire",
    "Water",
    "Grass",
    "Electric",
    "Psychic",
    "Ice",
    "Dragon",
    "Dark",
    "Steel"
};

/*
    Gen II style move category.

    0 = physical
    1 = special
*/
enum
{
    PHYSICAL,
    SPECIAL
};

/* ---------------------------------------------------------
   MOVES
   --------------------------------------------------------- */

typedef struct
{
    char name[32];

    int type;
    int power;
    int accuracy;

    int category;

    int status;
} Move;

/* A small Gen II-compatible move database */

Move moves[] =
{
    {"Tackle",       TYPE_NORMAL,   35, 95, PHYSICAL, 0},
    {"Quick Attack",TYPE_NORMAL,   40,100, PHYSICAL, 0},
    {"Thunderbolt",  TYPE_ELECTRIC, 95,100, SPECIAL,  0},
    {"Thunder",      TYPE_ELECTRIC,120, 70, SPECIAL,  0},
    {"Surf",         TYPE_WATER,    95,100, SPECIAL,  0},
    {"Hydro Pump",   TYPE_WATER,   120, 80, SPECIAL,  0},
    {"Flamethrower", TYPE_FIRE,     95,100, SPECIAL,  0},
    {"Fire Blast",   TYPE_FIRE,    120, 85, SPECIAL,  0},
    {"Psychic",      TYPE_PSYCHIC,  90,100, SPECIAL,  0},
    {"Ice Beam",     TYPE_ICE,      95,100, SPECIAL,  0},
    {"Earthquake",   TYPE_GROUND, 100,100, PHYSICAL, 0},
    {"Rock Slide",   TYPE_ROCK,     75, 90, PHYSICAL, 0},
    {"Sludge Bomb",  TYPE_POISON,   90,100, PHYSICAL, 0},
    {"Shadow Ball",  TYPE_GHOST,    80,100, PHYSICAL, 0},
    {"Iron Tail",    TYPE_STEEL,   100, 75, PHYSICAL, 0},
    {"Crunch",       TYPE_DARK,     80,100, PHYSICAL, 0}
};

#define MOVE_COUNT 16

/* ---------------------------------------------------------
   POKEMON
   --------------------------------------------------------- */

typedef struct
{
    char name[32];

    int species;

    int type1;
    int type2;

    int level;

    int max_hp;
    int hp;

    int attack;
    int defense;

    int special_attack;
    int special_defense;

    int speed;

    int moves[MAX_MOVES];

    int status;

    int fainted;
} Pokemon;

/* ---------------------------------------------------------
   TRAINER
   --------------------------------------------------------- */

typedef struct
{
    char name[32];

    int trainer_id;

    Pokemon team[TEAM_SIZE];

    int active;

    int wins;
    int losses;

    int rating;

    int battle_count;

    int type_threat[MAX_TYPES];

    int aggressive;
    int defensive;
    int speed_preference;

} Trainer;

/* ---------------------------------------------------------
   NETWORK PACKET
   --------------------------------------------------------- */

enum
{
    PACKET_JOIN,
    PACKET_READY,
    PACKET_MOVE,
    PACKET_SWITCH,
    PACKET_STATE,
    PACKET_RESULT,
    PACKET_PING
};

typedef struct
{
    int packet_type;

    int battle_id;

    int trainer_id;

    int turn;

    int pokemon;

    int move;

    int target;

    int hp;

    int checksum;

} BattlePacket;

/* ---------------------------------------------------------
   BATTLE
   --------------------------------------------------------- */

typedef struct
{
    int battle_id;

    int trainer_a;
    int trainer_b;

    int turn;

    int active_a;
    int active_b;

    int finished;

    int winner;

    BattlePacket last_packet;

} Battle;

/* ---------------------------------------------------------
   RED AI
   --------------------------------------------------------- */

typedef struct
{
    int type_threat[MAX_TYPES];

    int physical_threat;
    int special_threat;
    int speed_threat;

    int losses;

    double learning_rate;

    double exploration;

} RedBrain;

RedBrain red;

/* ---------------------------------------------------------
   RANDOM
   --------------------------------------------------------- */

int random_range(int min, int max)
{
    if (max <= min)
        return min;

    return min + rand() % (max - min + 1);
}

/* ---------------------------------------------------------
   TYPE EFFECTIVENESS
   --------------------------------------------------------- */

double type_effectiveness(int attack_type, int defend_type)
{
    /*
        Simplified Gen II type chart.

        0.0 = immune
        0.5 = not very effective
        1.0 = normal
        2.0 = super effective
    */

    if (attack_type == TYPE_NORMAL &&
        defend_type == TYPE_GHOST)
        return 0.0;

    if (attack_type == TYPE_FIGHTING &&
        (defend_type == TYPE_GHOST))
        return 0.0;

    if (attack_type == TYPE_ELECTRIC &&
        defend_type == TYPE_GROUND)
        return 0.0;

    if (attack_type == TYPE_GROUND &&
        defend_type == TYPE_FLYING)
        return 0.0;

    if (attack_type == TYPE_PSYCHIC &&
        defend_type == TYPE_DARK)
        return 0.0;

    if (attack_type == TYPE_FIRE)
    {
        if (defend_type == TYPE_GRASS ||
            defend_type == TYPE_ICE ||
            defend_type == TYPE_BUG ||
            defend_type == TYPE_STEEL)
            return 2.0;

        if (defend_type == TYPE_FIRE ||
            defend_type == TYPE_WATER ||
            defend_type == TYPE_ROCK ||
            defend_type == TYPE_DRAGON)
            return 0.5;
    }

    if (attack_type == TYPE_WATER)
    {
        if (defend_type == TYPE_FIRE ||
            defend_type == TYPE_GROUND ||
            defend_type == TYPE_ROCK)
            return 2.0;

        if (defend_type == TYPE_WATER ||
            defend_type == TYPE_GRASS ||
            defend_type == TYPE_DRAGON)
            return 0.5;
    }

    if (attack_type == TYPE_GRASS)
    {
        if (defend_type == TYPE_WATER ||
            defend_type == TYPE_GROUND ||
            defend_type == TYPE_ROCK)
            return 2.0;

        if (defend_type == TYPE_FIRE ||
            defend_type == TYPE_GRASS ||
            defend_type == TYPE_POISON ||
            defend_type == TYPE_FLYING ||
            defend_type == TYPE_BUG ||
            defend_type == TYPE_DRAGON ||
            defend_type == TYPE_STEEL)
            return 0.5;
    }

    if (attack_type == TYPE_ELECTRIC)
    {
        if (defend_type == TYPE_WATER ||
            defend_type == TYPE_FLYING)
            return 2.0;

        if (defend_type == TYPE_ELECTRIC ||
            defend_type == TYPE_GRASS ||
            defend_type == TYPE_DRAGON)
            return 0.5;
    }

    if (attack_type == TYPE_ICE)
    {
        if (defend_type == TYPE_GRASS ||
            defend_type == TYPE_GROUND ||
            defend_type == TYPE_FLYING ||
            defend_type == TYPE_DRAGON)
            return 2.0;

        if (defend_type == TYPE_FIRE ||
            defend_type == TYPE_WATER ||
            defend_type == TYPE_ICE)
            return 0.5;
    }

    if (attack_type == TYPE_GROUND)
    {
        if (defend_type == TYPE_FIRE ||
            defend_type == TYPE_ELECTRIC ||
            defend_type == TYPE_POISON ||
            defend_type == TYPE_ROCK ||
            defend_type == TYPE_STEEL)
            return 2.0;

        if (defend_type == TYPE_GRASS ||
            defend_type == TYPE_BUG)
            return 0.5;
    }

    if (attack_type == TYPE_ROCK)
    {
        if (defend_type == TYPE_FIRE ||
            defend_type == TYPE_ICE ||
            defend_type == TYPE_FLYING ||
            defend_type == TYPE_BUG)
            return 2.0;

        if (defend_type == TYPE_FIGHTING ||
            defend_type == TYPE_GROUND ||
            defend_type == TYPE_STEEL)
            return 0.5;
    }

    if (attack_type == TYPE_PSYCHIC)
    {
        if (defend_type == TYPE_FIGHTING ||
            defend_type == TYPE_POISON)
            return 2.0;

        if (defend_type == TYPE_PSYCHIC ||
            defend_type == TYPE_STEEL)
            return 0.5;
    }

    if (attack_type == TYPE_FIGHTING)
    {
        if (defend_type == TYPE_NORMAL ||
            defend_type == TYPE_ICE ||
            defend_type == TYPE_ROCK ||
            defend_type == TYPE_DARK ||
            defend_type == TYPE_STEEL)
            return 2.0;

        if (defend_type == TYPE_POISON ||
            defend_type == TYPE_FLYING ||
            defend_type == TYPE_PSYCHIC ||
            defend_type == TYPE_BUG)
            return 0.5;
    }

    if (attack_type == TYPE_STEEL)
    {
        if (defend_type == TYPE_ICE ||
            defend_type == TYPE_ROCK)
            return 2.0;

        if (defend_type == TYPE_FIRE ||
            defend_type == TYPE_WATER ||
            defend_type == TYPE_ELECTRIC ||
            defend_type == TYPE_STEEL)
            return 0.5;
    }

    if (attack_type == TYPE_DARK)
    {
        if (defend_type == TYPE_PSYCHIC ||
            defend_type == TYPE_GHOST)
            return 2.0;

        if (defend_type == TYPE_FIGHTING ||
            defend_type == TYPE_DARK ||
            defend_type == TYPE_STEEL)
            return 0.5;
    }

    return 1.0;
}

/* ---------------------------------------------------------
   DAMAGE
   --------------------------------------------------------- */

int calculate_damage(Pokemon *attacker,
                     Pokemon *defender,
                     Move *move)
{
    int attack_stat;
    int defense_stat;

    double damage;
    double modifier;

    int critical;

    if (move->category == PHYSICAL)
    {
        attack_stat = attacker->attack;
        defense_stat = defender->defense;
    }
    else
    {
        attack_stat = attacker->special_attack;
        defense_stat = defender->special_defense;
    }

    damage =
        (((2.0 * attacker->level / 5.0 + 2.0)
        * move->power
        * attack_stat
        / defense_stat) / 50.0) + 2.0;

    critical = (random_range(1, 16) == 1);

    if (critical)
        damage *= 2.0;

    modifier =
        type_effectiveness(move->type, defender->type1);

    if (defender->type2 != defender->type1)
    {
        modifier *=
            type_effectiveness(move->type, defender->type2);
    }

    damage *= modifier;

    damage *=
        random_range(217, 255) / 255.0;

    if (damage < 1.0 &&
        modifier > 0.0)
        damage = 1.0;

    if (modifier == 0.0)
        damage = 0;

    printf("  %s -> %s: %.0f damage\n",
           move->name,
           defender->name,
           damage);

    if (critical)
        printf("  CRITICAL HIT!\n");

    if (modifier >= 2.0)
        printf("  SUPER EFFECTIVE!\n");

    if (modifier > 0.0 && modifier < 1.0)
        printf("  Not very effective...\n");

    return (int)damage;
}

/* ---------------------------------------------------------
   APPLY MOVE
   --------------------------------------------------------- */

void use_move(Pokemon *attacker,
              Pokemon *defender,
              int move_id)
{
    Move *move;

    int damage;

    if (move_id < 0 ||
        move_id >= MOVE_COUNT)
        return;

    move = &moves[move_id];

    if (random_range(1,100) > move->accuracy)
    {
        printf("%s missed!\n", move->name);
        return;
    }

    damage =
        calculate_damage(attacker,
                         defender,
                         move);

    defender->hp -= damage;

    if (defender->hp < 0)
        defender->hp = 0;

    if (defender->hp == 0)
    {
        defender->fainted = TRUE;

        printf("%s fainted!\n",
               defender->name);
    }
}

/* ---------------------------------------------------------
   CREATE POKEMON
   --------------------------------------------------------- */

void create_pokemon(Pokemon *p,
                    const char *name,
                    int type1,
                    int type2,
                    int level,
                    int attack,
                    int defense,
                    int special,
                    int speed)
{
    int i;

    strcpy(p->name, name);

    p->type1 = type1;
    p->type2 = type2;

    p->level = level;

    p->max_hp =
        50 + level * 3;

    p->hp = p->max_hp;

    p->attack = attack;
    p->defense = defense;

    p->special_attack = special;
    p->special_defense = special;

    p->speed = speed;

    p->status = 0;
    p->fainted = FALSE;

    for (i = 0; i < MAX_MOVES; i++)
        p->moves[i] = 0;
}

/* ---------------------------------------------------------
   TEAM CREATION
   --------------------------------------------------------- */

void create_red_team(Trainer *red_trainer)
{
    strcpy(red_trainer->name, "RED");

    red_trainer->trainer_id = 999;

    create_pokemon(
        &red_trainer->team[0],
        "Pikachu",
        TYPE_ELECTRIC,
        TYPE_ELECTRIC,
        81,
        150,
        120,
        145,
        180
    );

    red_trainer->team[0].moves[0] = 2;
    red_trainer->team[0].moves[1] = 1;

    create_pokemon(
        &red_trainer->team[1],
        "Espeon",
        TYPE_PSYCHIC,
        TYPE_PSYCHIC,
        73,
        130,
        120,
        170,
        150
    );

    red_trainer->team[1].moves[0] = 8;
    red_trainer->team[1].moves[1] = 1;

    create_pokemon(
        &red_trainer->team[2],
        "Snorlax",
        TYPE_NORMAL,
        TYPE_NORMAL,
        75,
        160,
        160,
        120,
        65
    );

    red_trainer->team[2].moves[0] = 0;
    red_trainer->team[2].moves[1] = 10;

    create_pokemon(
        &red_trainer->team[3],
        "Venusaur",
        TYPE_GRASS,
        TYPE_POISON,
        77,
        145,
        145,
        150,
        110
    );

    red_trainer->team[3].moves[0] = 5;
    red_trainer->team[3].moves[1] = 12;

    create_pokemon(
        &red_trainer->team[4],
        "Charizard",
        TYPE_FIRE,
        TYPE_FLYING,
        77,
        155,
        135,
        150,
        145
    );

    red_trainer->team[4].moves[0] = 6;
    red_trainer->team[4].moves[1] = 7;

    create_pokemon(
        &red_trainer->team[5],
        "Blastoise",
        TYPE_WATER,
        TYPE_WATER,
        77,
        145,
        165,
        150,
        105
    );

    red_trainer->team[5].moves[0] = 4;
    red_trainer->team[5].moves[1] = 5;

    red_trainer->active = 0;
}

/* ---------------------------------------------------------
   PLAYER TEAM
   --------------------------------------------------------- */

void create_player_team(Trainer *player)
{
    strcpy(player->name, "PLAYER");

    player->trainer_id = 1;

    create_pokemon(
        &player->team[0],
        "Typhlosion",
        TYPE_FIRE,
        TYPE_FIRE,
        70,
        145,
        120,
        155,
        145
    );

    player->team[0].moves[0] = 6;
    player->team[0].moves[1] = 7;

    create_pokemon(
        &player->team[1],
        "Feraligatr",
        TYPE_WATER,
        TYPE_WATER,
        70,
        160,
        150,
        105,
        110
    );

    player->team[1].moves[0] = 4;
    player->team[1].moves[1] = 10;

    create_pokemon(
        &player->team[2],
        "Meganium",
        TYPE_GRASS,
        TYPE_GRASS,
        70,
        120,
        155,
        135,
        105
    );

    player->team[2].moves[0] = 5;
    player->team[2].moves[1] = 12;

    create_pokemon(
        &player->team[3],
        "Ampharos",
        TYPE_ELECTRIC,
        TYPE_ELECTRIC,
        70,
        130,
        120,
        165,
        95
    );

    player->team[3].moves[0] = 2;
    player->team[3].moves[1] = 3;

    create_pokemon(
        &player->team[4],
        "Espeon",
        TYPE_PSYCHIC,
        TYPE_PSYCHIC,
        70,
        130,
        110,
        165,
        155
    );

    player->team[4].moves[0] = 8;
    player->team[4].moves[1] = 15;

    create_pokemon(
        &player->team[5],
        "Steelix",
        TYPE_STEEL,
        TYPE_GROUND,
        70,
        155,
        190,
        80,
        65
    );

    player->team[5].moves[0] = 10;
    player->team[5].moves[1] = 14;

    player->active = 0;
}

/* ---------------------------------------------------------
   NETWORK
   --------------------------------------------------------- */

/*
    In a real Switch implementation these functions become
    calls into the platform's networking layer.

    The important point is that the battle engine doesn't
    care whether the packet arrived over local wireless,
    Internet Wi-Fi or another transport.
*/

void network_send(BattlePacket *packet)
{
    printf("\n[NETWORK SEND]\n");

    printf("packet = %d\n",
           packet->packet_type);

    printf("battle = %d\n",
           packet->battle_id);

    printf("trainer = %d\n",
           packet->trainer_id);

    printf("turn = %d\n",
           packet->turn);

    printf("pokemon = %d\n",
           packet->pokemon);

    printf("move = %d\n",
           packet->move);
}

void network_receive(BattlePacket *packet)
{
    /*
        Placeholder.

        A real implementation would block/wait for the
        remote player's packet.
    */

    memset(packet, 0, sizeof(BattlePacket));
}

/* ---------------------------------------------------------
   PACKET CHECKSUM
   --------------------------------------------------------- */

int packet_checksum(BattlePacket *p)
{
    return
        p->packet_type ^
        p->battle_id ^
        p->trainer_id ^
        p->turn ^
        p->pokemon ^
        p->move ^
        p->target ^
        p->hp;
}

/* ---------------------------------------------------------
   SEND MOVE
   --------------------------------------------------------- */

void send_move_packet(int battle_id,
                      int trainer_id,
                      int turn,
                      int pokemon,
                      int move)
{
    BattlePacket packet;

    memset(&packet, 0, sizeof(packet));

    packet.packet_type = PACKET_MOVE;
    packet.battle_id = battle_id;
    packet.trainer_id = trainer_id;
    packet.turn = turn;
    packet.pokemon = pokemon;
    packet.move = move;

    packet.checksum =
        packet_checksum(&packet);

    network_send(&packet);
}

/* ---------------------------------------------------------
   RED LEARNING
   --------------------------------------------------------- */

void red_init(void)
{
    int i;

    memset(&red, 0, sizeof(red));

    red.learning_rate = 0.20;
    red.exploration = 0.15;

    for (i = 0; i < MAX_TYPES; i++)
        red.type_threat[i] = 0;
}

/* ---------------------------------------------------------
   OBSERVE PLAYER
   --------------------------------------------------------- */

void red_observe_player(Pokemon *p)
{
    if (p->type1 >= 0 &&
        p->type1 < MAX_TYPES)
        red.type_threat[p->type1]++;

    if (p->type2 >= 0 &&
        p->type2 < MAX_TYPES)
        red.type_threat[p->type2]++;

    /*
        Estimate battle style.
    */

    if (p->attack > p->special_attack)
        red.physical_threat++;

    else
        red.special_threat++;

    if (p->speed > 130)
        red.speed_threat++;
}

/* ---------------------------------------------------------
   RED COUNTER SCORE
   --------------------------------------------------------- */

double red_counter_score(Pokemon *candidate)
{
    int i;

    double score;

    score = 0.0;

    /*
        Reward candidates that resist common player types.
    */

    for (i = 0; i < MAX_TYPES; i++)
    {
        if (red.type_threat[i] == 0)
            continue;

        score +=
            red.type_threat[i] *
            (1.0 -
             type_effectiveness(
                 i,
                 candidate->type1));
    }

    score += candidate->speed * 0.10;

    score += candidate->defense * 0.05;

    return score;
}

/* ---------------------------------------------------------
   RED ADAPT
   --------------------------------------------------------- */

void red_adapt(Trainer *red_trainer,
               Trainer *player)
{
    int i;
    int best;
    double best_score;

    /*
        Observe every Pokémon used by the player.
    */

    for (i = 0; i < TEAM_SIZE; i++)
        red_observe_player(
            &player->team[i]);

    /*
        Find a replacement candidate.

        For the prototype we use existing Red Pokémon
        plus generated counters.
    */

    best = 0;
    best_score = -999999.0;

    for (i = 0; i < TEAM_SIZE; i++)
    {
        double score;

        score =
            red_counter_score(
                &red_trainer->team[i]);

        if (score > best_score)
        {
            best_score = score;
            best = i;
        }
    }

    printf("\nRED AI ANALYSIS\n");

    printf("Highest threat type: ");

    {
        int highest;
        int type;

        highest = -1;
        type = 0;

        for (i = 0; i < MAX_TYPES; i++)
        {
            if (red.type_threat[i] > highest)
            {
                highest =
                    red.type_threat[i];

                type = i;
            }
        }

        printf("%s\n",
               type_name[type]);
    }

    printf("Red's highest counter score: %s\n",
           red_trainer->team[best].name);
}

/* ---------------------------------------------------------
   FIND NEXT POKEMON
   --------------------------------------------------------- */

int find_next_pokemon(Trainer *trainer)
{
    int i;

    for (i = 0; i < TEAM_SIZE; i++)
    {
        if (!trainer->team[i].fainted)
            return i;
    }

    return -1;
}

/* ---------------------------------------------------------
   BATTLE END
   --------------------------------------------------------- */

int battle_finished(Trainer *a,
                    Trainer *b)
{
    int i;

    for (i = 0; i < TEAM_SIZE; i++)
    {
        if (!a->team[i].fainted)
            goto A_ALIVE;
    }

    return 2;

A_ALIVE:

    for (i = 0; i < TEAM_SIZE; i++)
    {
        if (!b->team[i].fainted)
            goto B_ALIVE;
    }

    return 1;

B_ALIVE:

    return 0;
}

/* ---------------------------------------------------------
   TURN
   --------------------------------------------------------- */

void battle_turn(Battle *battle,
                 Trainer *a,
                 Trainer *b)
{
    Pokemon *pa;
    Pokemon *pb;

    int move_a;
    int move_b;

    pa = &a->team[battle->active_a];
    pb = &b->team[battle->active_b];

    printf("\n=============================\n");
    printf("TURN %d\n", battle->turn);
    printf("=============================\n");

    printf("%s HP: %d/%d\n",
           pa->name,
           pa->hp,
           pa->max_hp);

    printf("%s HP: %d/%d\n",
           pb->name,
           pb->hp,
           pb->max_hp);

    /*
        Very simple AI selection.
        A real online client would receive these choices
        from each player.
    */

    move_a =
        random_range(0, MAX_MOVES - 1);

    move_b =
        random_range(0, MAX_MOVES - 1);

    send_move_packet(
        battle->battle_id,
        a->trainer_id,
        battle->turn,
        battle->active_a,
        pa->moves[move_a]);

    send_move_packet(
        battle->battle_id,
        b->trainer_id,
        battle->turn,
        battle->active_b,
        pb->moves[move_b]);

    /*
        Faster Pokémon moves first.
    */

    if (pa->speed >= pb->speed)
    {
        use_move(
            pa,
            pb,
            pa->moves[move_a]);

        if (!pb->fainted)
        {
            use_move(
                pb,
                pa,
                pb->moves[move_b]);
        }
    }
    else
    {
        use_move(
            pb,
            pa,
            pb->moves[move_b]);

        if (!pa->fainted)
        {
            use_move(
                pa,
                pb,
                pa->moves[move_a]);
        }
    }

    if (pa->fainted)
    {
        battle->active_a =
            find_next_pokemon(a);

        printf("%s sends out %s!\n",
               a->name,
               a->team[
                   battle->active_a
               ].name);
    }

    if (pb->fainted)
    {
        battle->active_b =
            find_next_pokemon(b);

        printf("%s sends out %s!\n",
               b->name,
               b->team[
                   battle->active_b
               ].name);
    }

    battle->turn++;
}

/* ---------------------------------------------------------
   RESULT
   --------------------------------------------------------- */

void battle_result(Battle *battle,
                   Trainer *a,
                   Trainer *b)
{
    int result;

    result =
        battle_finished(a,b);

    if (result == 0)
        return;

    battle->finished = TRUE;

    if (result == 1)
    {
        battle->winner =
            a->trainer_id;

        a->wins++;
        b->losses++;

        a->rating += 15;
        b->rating -= 15;

        printf("\n%s WINS!\n",
               a->name);
    }
    else
    {
        battle->winner =
            b->trainer_id;

        b->wins++;
        a->losses++;

        b->rating += 15;
        a->rating -= 15;

        printf("\n%s WINS!\n",
               b->name);
    }

    printf("\nFINAL RATING\n");

    printf("%s: %d\n",
           a->name,
           a->rating);

    printf("%s: %d\n",
           b->name,
           b->rating);
}

/* ---------------------------------------------------------
   ONLINE BATTLE
   --------------------------------------------------------- */

void online_battle(Trainer *a,
                   Trainer *b)
{
    Battle battle;

    memset(&battle, 0, sizeof(battle));

    battle.battle_id =
        random_range(10000,99999);

    battle.trainer_a =
        a->trainer_id;

    battle.trainer_b =
        b->trainer_id;

    battle.active_a = 0;
    battle.active_b = 0;

    battle.turn = 1;

    printf("\n");
    printf("================================\n");
    printf("      JOHTO ONLINE BATTLE\n");
    printf("================================\n");

    printf("Battle ID: %d\n",
           battle.battle_id);

    printf("%s VS %s\n",
           a->name,
           b->name);

    while (!battle.finished)
    {
        battle_turn(
            &battle,
            a,
            b);

        battle_result(
            &battle,
            a,
            b);

        if (battle.turn > 200)
        {
            printf("Battle timeout.\n");
            break;
        }
    }
}

/* ---------------------------------------------------------
   TRAINER DATABASE
   --------------------------------------------------------- */

Trainer players[MAX_PLAYERS];

int player_count = 0;

/* ---------------------------------------------------------
   CREATE PLAYER
   --------------------------------------------------------- */

void create_player(const char *name)
{
    Trainer *p;

    if (player_count >= MAX_PLAYERS)
        return;

    p =
        &players[player_count];

    memset(p, 0, sizeof(Trainer));

    strcpy(p->name, name);

    p->trainer_id =
        player_count + 1;

    p->rating = 1000;

    player_count++;

    printf("Created trainer: %s\n",
           p->name);
}

/* ---------------------------------------------------------
   DISPLAY TRAINER
   --------------------------------------------------------- */

void display_trainer(Trainer *p)
{
    int i;

    printf("\n============================\n");
    printf("TRAINER: %s\n",
           p->name);

    printf("Rating: %d\n",
           p->rating);

    printf("Wins: %d\n",
           p->wins);

    printf("Losses: %d\n",
           p->losses);

    printf("\nTEAM\n");

    for (i = 0; i < TEAM_SIZE; i++)
    {
        printf("%d. %-12s Lv.%d HP %d/%d\n",
               i + 1,
               p->team[i].name,
               p->team[i].level,
               p->team[i].hp,
               p->team[i].max_hp);
    }
}

/* ---------------------------------------------------------
   ONLINE LOBBY
   --------------------------------------------------------- */

void online_lobby(void)
{
    printf("\n");
    printf("=============================\n");
    printf("       JOHTO ONLINE\n");
    printf("=============================\n");

    printf("1. Quick Battle\n");
    printf("2. Battle Code\n");
    printf("3. Ranked Battle\n");
    printf("4. Friend Battle\n");
    printf("5. Red AI Challenge\n");
}

/* ---------------------------------------------------------
   RED LEARNING REPORT
   --------------------------------------------------------- */

void red_report(void)
{
    int i;

    printf("\n");
    printf("=============================\n");
    printf("       RED AI MEMORY\n");
    printf("=============================\n");

    printf("Losses learned from: %d\n",
           red.losses);

    printf("\nObserved threats:\n");

    for (i = 0; i < MAX_TYPES; i++)
    {
        if (red.type_threat[i] > 0)
        {
            printf("%-10s %d\n",
                   type_name[i],
                   red.type_threat[i]);
        }
    }
}

/* ---------------------------------------------------------
   MAIN
   --------------------------------------------------------- */

int main(void)
{
    Trainer player;
    Trainer red_trainer;

    srand(
        (unsigned int)time(NULL));

    printf("\n");
    printf("========================================\n");
    printf(" POKEMON GOLD - ONLINE BATTLE ENGINE\n");
    printf("========================================\n");

    red_init();

    memset(&player, 0, sizeof(player));
    memset(&red_trainer, 0, sizeof(red_trainer));

    create_player_team(&player);

    create_red_team(&red_trainer);

    /*
        Demonstrate Red learning.
    */

    red_adapt(
        &red_trainer,
        &player);

    /*
        Display online lobby.
    */

    online_lobby();

    /*
        Run demonstration battle.
    */

    online_battle(
        &player,
        &red_trainer);

    /*
        Update Red's learning after battle.
    */

    if (player.losses > 0)
    {
        red.losses++;

        red.learning_rate *= 1.01;

        if (red.learning_rate > 0.50)
            red.learning_rate = 0.50;

        red_adapt(
            &red_trainer,
            &player);
    }

    display_trainer(
        &player);

    display_trainer(
        &red_trainer);

    red_report();

    printf("\n");
    printf("Online battle simulation complete.\n");

    return 0;
}










hard16_battle.jl
using Colors
using FileIO
using ImageIO
using ImageShow

# ============================================================
# HARD 16-BIT BATTLE ANIMATION
# ============================================================

const W = 160
const H = 144

const SCALE = 4

const BG      = RGB(0.035, 0.045, 0.055)
const BLACK   = RGB(0.015, 0.018, 0.022)
const WHITE   = RGB(0.92, 0.94, 0.90)

const STEEL1  = RGB(0.22, 0.25, 0.29)
const STEEL2  = RGB(0.38, 0.42, 0.47)

const RED1    = RGB(0.65, 0.08, 0.06)
const RED2    = RGB(0.95, 0.18, 0.10)

const GOLD1   = RGB(0.75, 0.48, 0.08)
const GOLD2   = RGB(1.00, 0.72, 0.18)

const BLUE1   = RGB(0.05, 0.25, 0.65)
const BLUE2   = RGB(0.10, 0.55, 1.00)

const CYAN    = RGB(0.20, 0.95, 1.00)

# ============================================================
# PIXEL CANVAS
# ============================================================

function canvas()
    fill(BG, H, W)
end

function px!(img, x, y, colour)
    if x >= 1 && x <= W && y >= 1 && y <= H
        img[y, x] = colour
    end
end

function rect!(img, x, y, w, h, colour)

    for yy in y:(y+h-1)
        for xx in x:(x+w-1)
            px!(img, xx, yy, colour)
        end
    end

end

function line!(img, x1, y1, x2, y2, colour)

    dx = abs(x2 - x1)
    dy = -abs(y2 - y1)

    sx = x1 < x2 ? 1 : -1
    sy = y1 < y2 ? 1 : -1

    err = dx + dy

    x = x1
    y = y1

    while true

        px!(img, x, y, colour)

        if x == x2 && y == y2
            break
        end

        e2 = 2 * err

        if e2 >= dy
            err += dy
            x += sx
        end

        if e2 <= dx
            err += dx
            y += sy
        end
    end
end

# ============================================================
# PIXELATED CIRCLE
# ============================================================

function disc!(img, cx, cy, r, colour)

    for y in -r:r
        for x in -r:r

            if x*x + y*y <= r*r
                px!(img,
                    cx + x,
                    cy + y,
                    colour)
            end

        end
    end

end

# ============================================================
# HARD GROUND
# ============================================================

function draw_ground!(img)

    # horizon

    rect!(
        img,
        1,
        92,
        W,
        2,
        STEEL1
    )

    # platform

    rect!(
        img,
        20,
        103,
        120,
        4,
        STEEL2
    )

    rect!(
        img,
        27,
        107,
        106,
        2,
        BLACK
    )

    # perspective lines

    line!(20, 103, 4, 143, STEEL1)
    line!(140, 103, 156, 143, STEEL1)

    line!(45, 103, 30, 143, STEEL1)
    line!(115, 103, 130, 143, STEEL1)

end

# ============================================================
# PLAYER MONSTER
# ============================================================

function draw_player_monster!(
    img,
    cx,
    cy;
    scale=1,
    attack=false
)

    # shadow

    disc!(
        img,
        cx,
        cy + 23,
        18 * scale,
        BLACK
    )

    # body

    rect!(
        img,
        cx - 12*scale,
        cy - 14*scale,
        24*scale,
        30*scale,
        RED1
    )

    rect!(
        img,
        cx - 8*scale,
        cy - 18*scale,
        16*scale,
        10*scale,
        RED2
    )

    # armour

    rect!(
        img,
        cx - 8*scale,
        cy - 8*scale,
        16*scale,
        14*scale,
        STEEL1
    )

    rect!(
        img,
        cx - 5*scale,
        cy - 5*scale,
        10*scale,
        7*scale,
        STEEL2
    )

    # eye

    rect!(
        img,
        cx + 5*scale,
        cy - 12*scale,
        3*scale,
        3*scale,
        WHITE
    )

    # legs

    rect!(
        img,
        cx - 10*scale,
        cy + 13*scale,
        7*scale,
        9*scale,
        BLACK
    )

    rect!(
        img,
        cx + 3*scale,
        cy + 13*scale,
        7*scale,
        9*scale,
        BLACK
    )

    # attack arm

    if attack

        line!(
            img,
            cx + 8*scale,
            cy - 2*scale,
            cx + 25*scale,
            cy - 13*scale,
            RED2
        )

        line!(
            img,
            cx + 25*scale,
            cy - 13*scale,
            cx + 33*scale,
            cy - 13*scale,
            GOLD2
        )

    else

        line!(
            img,
            cx + 8*scale,
            cy - 2*scale,
            cx + 18*scale,
            cy + 8*scale,
            RED2
        )

    end

end

# ============================================================
# ENEMY MONSTER
# ============================================================

function draw_enemy_monster!(
    img,
    cx,
    cy;
    scale=1,
    hit=false
)

    # shadow

    disc!(
        img,
        cx,
        cy + 21,
        17 * scale,
        BLACK
    )

    # body

    rect!(
        img,
        cx - 13*scale,
        cy - 15*scale,
        26*scale,
        29*scale,
        BLUE1
    )

    # armour plates

    rect!(
        img,
        cx - 9*scale,
        cy - 11*scale,
        18*scale,
        7*scale,
        BLUE2
    )

    rect!(
        img,
        cx - 8*scale,
        cy,
        16*scale,
        10*scale,
        STEEL2
    )

    # horns

    line!(
        img,
        cx - 9*scale,
        cy - 12*scale,
        cx - 18*scale,
        cy - 23*scale,
        CYAN
    )

    line!(
        img,
        cx + 9*scale,
        cy - 12*scale,
        cx + 18*scale,
        cy - 23*scale,
        CYAN
    )

    # eyes

    rect!(
        img,
        cx - 8*scale,
        cy - 5*scale,
        4*scale,
        3*scale,
        WHITE
    )

    rect!(
        img,
        cx + 4*scale,
        cy - 5*scale,
        4*scale,
        3*scale,
        WHITE
    )

    # hit flash

    if hit

        rect!(
            img,
            cx - 18*scale,
            cy - 20*scale,
            36*scale,
            40*scale,
            GOLD2
        )

        rect!(
            img,
            cx - 11*scale,
            cy - 14*scale,
            22*scale,
            28*scale,
            WHITE
        )

    end

end

# ============================================================
# PROJECTILE
# ============================================================

function draw_projectile!(
    img,
    x,
    y,
    radius
)

    disc!(
        img,
        x,
        y,
        radius + 3,
        BLACK
    )

    disc!(
        img,
        x,
        y,
        radius,
        CYAN
    )

    # hard directional tail

    line!(
        img,
        x - radius*3,
        y + radius,
        x - radius,
        y,
        BLUE2
    )

    line!(
        img,
        x - radius*4,
        y + radius*2,
        x - radius*2,
        y + radius,
        BLUE1
    )

end

# ============================================================
# IMPACT
# ============================================================

function draw_impact!(
    img,
    cx,
    cy,
    intensity
)

    # central flash

    disc!(
        img,
        cx,
        cy,
        intensity,
        WHITE
    )

    # diagonal shards

    for i in 1:8

        angle = i * π / 4

        x2 =
            cx +
            round(Int,
                cos(angle) *
                intensity * 3)

        y2 =
            cy +
            round(Int,
                sin(angle) *
                intensity * 3)

        line!(
            img,
            cx,
            cy,
            x2,
            y2,
            GOLD2
        )

    end

    # square energy blocks

    for i in 1:6

        dx = rand(-intensity*3:intensity*3)
        dy = rand(-intensity*3:intensity*3)

        rect!(
            img,
            cx + dx,
            cy + dy,
            2,
            2,
            CYAN
        )

    end

end

# ============================================================
# SCREEN SHAKE
# ============================================================

function shake(frame)

    if frame < 3
        return (0, 0)
    elseif frame < 6
        return (3, -2)
    elseif frame < 9
        return (-3, 2)
    elseif frame < 12
        return (2, 1)
    else
        return (0, 0)
    end

end

# ============================================================
# FRAME GENERATOR
# ============================================================

function make_frame(frame)

    img = canvas()

    sx, sy = shake(frame)

    draw_ground!(img)

    # --------------------------------------------------------
    # PHASE 1: IDLE
    # --------------------------------------------------------

    if frame <= 4

        draw_player_monster!(
            img,
            43 + sx,
            80 + sy;
            scale=1,
            attack=false
        )

        draw_enemy_monster!(
            img,
            116 + sx,
            72 + sy;
            scale=1,
            hit=false
        )

    # --------------------------------------------------------
    # PHASE 2: ATTACK WINDUP
    # --------------------------------------------------------

    elseif frame <= 8

        t = (frame - 4) / 4

        px =
            43 +
            round(Int, 18*t)

        draw_player_monster!(
            img,
            px + sx,
            80 + sy;
            scale=1,
            attack=true
        )

        draw_enemy_monster!(
            img,
            116 + sx,
            72 + sy;
            scale=1,
            hit=false
        )

        # charging energy

        disc!(
            img,
            px + 30,
            67,
            3 + frame % 2,
            CYAN
        )

    # --------------------------------------------------------
    # PHASE 3: PROJECTILE
    # --------------------------------------------------------

    elseif frame <= 13

        draw_player_monster!(
            img,
            61 + sx,
            80 + sy;
            scale=1,
            attack=true
        )

        draw_enemy_monster!(
            img,
            116 + sx,
            72 + sy;
            scale=1,
            hit=false
        )

        projectile_x =
            65 +
            (frame - 8) * 10

        projectile_y =
            67 -
            (frame - 8) * 2

        draw_projectile!(
            img,
            projectile_x + sx,
            projectile_y + sy,
            3
        )

    # --------------------------------------------------------
    # PHASE 4: IMPACT
    # --------------------------------------------------------

    elseif frame <= 17

        draw_player_monster!(
            img,
            61 + sx,
            80 + sy;
            scale=1,
            attack=true
        )

        draw_enemy_monster!(
            img,
            116 + sx,
            72 + sy;
            scale=1,
            hit=true
        )

        intensity =
            5 +
            (frame - 13) * 2

        draw_impact!(
            img,
            111 + sx,
            67 + sy,
            intensity
        )

    # --------------------------------------------------------
    # PHASE 5: RECOVERY
    # --------------------------------------------------------

    else

        draw_player_monster!(
            img,
            43,
            80;
            scale=1,
            attack=false
        )

        draw_enemy_monster!(
            img,
            116,
            72;
            scale=1,
            hit=false
        )

    end

    # --------------------------------------------------------
    # 16-BIT UI
    # --------------------------------------------------------

    rect!(
        img,
        8,
        8,
        144,
        18,
        BLACK
    )

    rect!(
        img,
        10,
        10,
        140,
        14,
        STEEL1
    )

    rect!(
        img,
        12,
        12,
        80,
        4,
        RED2
    )

    rect!(
        img,
        12,
        18,
        55,
        2,
        GOLD2
    )

    # enemy status block

    rect!(
        img,
        91,
        115,
        61,
        17,
        BLACK
    )

    rect!(
        img,
        94,
        118,
        54,
        3,
        BLUE2
    )

    rect!(
        img,
        94,
        125,
        42,
        2,
        CYAN
    )

    return img
end

# ============================================================
# UPSCALE WITHOUT BLUR
# ============================================================

function nearest_upscale(img, factor)

    h, w = size(img)

    output =
        Array{RGB{Float64}}(
            undef,
            h * factor,
            w * factor
        )

    for y in 1:h
        for x in 1:w

            c = img[y,x]

            for yy in 1:factor
                for xx in 1:factor

                    output[
                        (y-1)*factor + yy,
                        (x-1)*factor + xx
                    ] = c

                end
            end

        end
    end

    return output
end

# ============================================================
# GENERATE ANIMATION
# ============================================================

frames = Matrix{RGB{Float64}}[]

for frame in 1:22

    base =
        make_frame(frame)

    enlarged =
        nearest_upscale(
            base,
            SCALE
        )

    push!(
        frames,
        enlarged
    )

end

# ============================================================
# EXPORT
# ============================================================

println("Generating 16-bit battle animation...")

ImageShow.gif(
    frames;
    fps=12
)

println("Animation generated.")

