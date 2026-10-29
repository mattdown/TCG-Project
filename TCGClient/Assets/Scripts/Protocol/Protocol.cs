using System.Collections.Generic;
using Newtonsoft.Json.Linq;

// JSON shapes of the game server's requests and responses: docs/client-protocol.md.
// Field names match the JSON exactly (snake_case) so the mapping stays obvious.
namespace Tcg.Protocol
{
    // --- requests

    public class Request
    {
        public string type;
        public Request(string type) { this.type = type; }
    }

    public class NewGameRequest : Request
    {
        public string opponent;
        public int human_seat;
        public int? seed;
        public JObject scenario;  // optional: chosen cards in hand and in play, mana, hero health
        public NewGameRequest(string opponent, int humanSeat, int? seed, JObject scenario = null) : base("new_game")
        {
            this.opponent = opponent;
            human_seat = humanSeat;
            this.seed = seed;
            this.scenario = scenario;
        }
    }

    public class ActRequest : Request
    {
        public int action_index;
        public ActRequest(int actionIndex) : base("act") { action_index = actionIndex; }
    }

    // --- responses

    public class Response
    {
        public string status;
        public string msg;
        public bool Ok => status == "ok";
    }

    public class CardSetResponse : Response
    {
        public string name;
        public List<CardDef> cards;
        public Dictionary<string, KeywordInfo> keywords;  // by keyword key, e.g. "duelist"
        public Dictionary<string, AspectInfo> aspects;    // aspect_1 … aspect_6, and "neutral"
    }

    /// <summary>A habitat's player-facing name and its feel in one line.</summary>
    public class AspectInfo
    {
        public string name;
        public string description;
    }

    /// <summary>A keyword's player-facing name and reminder text (N stands for its number).</summary>
    public class KeywordInfo
    {
        public string name;
        public bool numbered;
        public string rule;
    }

    /// <summary>Reply to new_game, state, act, ai_move and ai_turn; the fields not sent stay null.</summary>
    public class StateResponse : Response
    {
        public GameState state;
        public string opponent;            // new_game: the AI's name
        public GameAction action;          // act, ai_move
        public List<GameAction> actions;   // ai_turn
    }

    /// <summary>Reply to graph: the state graph the GNN reads, from the human's side.</summary>
    public class GraphResponse : Response
    {
        public GraphData graph;
    }

    // --- data

    public class CardDef
    {
        public string id;
        public string name;
        public string subtitle;  // units: the version of the character ("Up Before Dawn"); actions: ""
        public string type;
        public List<string> aspects;
        public int cost;
        public int power;
        public int health;
        public List<string> traits;
        public Dictionary<string, JToken> keywords;  // true, or a number for Duelist / Armor
        public List<string> ability_text;

        public bool IsAction => type == "action";
    }

    public static class KeywordValues
    {
        /// <summary>A keyword's number: 1 for flags (true), 0 if absent.</summary>
        public static int Of(Dictionary<string, JToken> keywords, string key)
        {
            if (keywords == null || !keywords.TryGetValue(key, out var v) || v == null) return 0;
            return v.Type == JTokenType.Boolean ? (v.Value<bool>() ? 1 : 0) : v.Value<int>();
        }
    }

    /// <summary>One physical card. uid is stable for the whole game, across zones.</summary>
    public class CardInstance
    {
        public int uid;
        public string card_id;
        public bool attacked;
        public bool fresh;
        public int damage;
        // Current values, with abilities' changes. Units only (null for action cards).
        public int cost;
        public int? power;
        public int? health;
        public Dictionary<string, JToken> keywords;
        public bool can_attack;  // it's its owner's turn and it can attack now
        public bool frozen;      // can't attack on its owner's next turn
        public bool hidden;      // Elusive and hasn't attacked yet: enemies can't target it
    }

    public class PlayerState
    {
        public int health;        // the hero's health left; 0 loses
        public int mana;          // unspent mana this turn
        public int crystals;      // mana crystals (up to max_mana)
        public bool spare_spore;  // the second player's one-off +1 mana is still available
        public int fatigue;       // damage from the last draw from an empty deck
        public int deck_count;
        public int hand_count;
        public List<CardInstance> hand;       // null for the AI
        public List<CardInstance> play;
        public List<CardInstance> discard;
        public List<int> mulligan_marked;     // null for the AI
    }

    public class GameAction
    {
        public int index;      // legal_actions only
        public string type;
        public int? card;
        public int? target;
        public int? option;    // choose_option: which option
        public int? player;    // action records only
        public string text;
        public ActionResult preview;   // legal actions: what play, score or duel would do
        public ActionResult result;    // action records: what the action did
    }

    /// <summary>
    /// Every change an action makes, recorded by the server's rules engine. The client animates
    /// and previews these; it never works a result out itself.
    /// </summary>
    public class ActionResult
    {
        public List<UidAmount> damage = new List<UidAmount>();
        public List<int> defeated = new List<int>();
        public List<PlayerAmount> hero_damage = new List<PlayerAmount>();
        public List<PlayerAmount> hero_healed = new List<PlayerAmount>();
        public List<PlayerAmount> mana_spent = new List<PlayerAmount>();
        public List<PlayerAmount> crystals = new List<PlayerAmount>();  // empty crystals gained from abilities
        public List<int> attacked = new List<int>();
        public List<CardMove> moves = new List<CardMove>();
        public List<int> abilities = new List<int>();     // sources of abilities that started resolving, in order
        public List<UidAmount> healed = new List<UidAmount>();
        public List<EffectRecord> effects = new List<EffectRecord>();

        public int DamageTo(int uid)
        {
            foreach (var d in damage) if (d.uid == uid) return d.amount;
            return 0;
        }

        public bool Defeats(int uid) => defeated.Contains(uid);
        public int HeroDamageTo(int player) => AmountFor(hero_damage, player);
        public int ManaFor(int player) => AmountFor(mana_spent, player);

        static int AmountFor(List<PlayerAmount> list, int player)
        {
            foreach (var e in list) if (e.player == player) return e.amount;
            return 0;
        }
    }

    /// <summary>A lasting change an ability made: a stat change, a granted keyword, or a freeze.</summary>
    public class EffectRecord
    {
        public int uid;
        public string kind;     // "stat" | "keyword" | "freeze"
        public string stat;     // power, health, score
        public string keyword;
        public int value;
        public bool this_turn;
        public string lasts;    // this_turn, until_your_next_turn, until_its_next_turn, while_in_play, permanent
    }

    /// <summary>An ability waiting for a choice; the legal actions are its answers.</summary>
    public class PendingChoice
    {
        public int source;
        public string card_id;
        public string kind;      // "choose" | "may" | "choose_one"
        public int chooser;
        public string ability_text;
    }

    public class UidAmount
    {
        public int uid;
        public int amount;
    }

    public class PlayerAmount
    {
        public int player;
        public int amount;
    }

    /// <summary>A card moving between zones; uid and card_id are null when the move is hidden.</summary>
    public class CardMove
    {
        public int? uid;
        public string card_id;
        public int player;
        public string from;
        public string to;
    }

    /// <summary>Zone names used in card moves.</summary>
    public static class Zones
    {
        public const string Deck = "deck";
        public const string Hand = "hand";
        public const string Play = "play";
        public const string Discard = "discard";
    }

    public class GameState
    {
        public int turn;
        public string phase;
        public int active_player;
        public int decision_player;
        public int human_seat;
        public bool game_over;
        public int? winner;
        public List<PlayerState> players;
        public int hero_health;  // a full hero (30)
        public int max_mana;     // the most mana crystals (10)
        public PendingChoice pending;
        public List<GameAction> legal_actions;

        public PlayerState Human => players[human_seat];
        public PlayerState Opponent => players[1 - human_seat];
        public bool HumanDecides => !game_over && decision_player == human_seat;
        public bool InMulligan => phase == "mulligan";
    }

    /// <summary>
    /// The GNN's view of the state: nodes of four types and the forward edges between them (each
    /// stands for both directions). Node ids are indexes into nodes.
    /// </summary>
    public class GraphData
    {
        public string embedding;  // "gnn": the network's embeddings; "features": raw inputs (no model)
        public int layers;        // vectors per node: the input projection, then one per GNN layer
        public int dim;           // numbers per vector
        public List<GraphNode> nodes;
        public List<GraphEdge> edges;
        public List<GraphAction> actions;  // the human's legal actions, in legal_actions order; empty otherwise
        public GraphValue value;
    }

    /// <summary>A legal action and the node ids the policy head scores it from (null: the slot is empty).</summary>
    public class GraphAction
    {
        public int index;
        public string type;
        public string text;
        public int? actor, target;     // card nodes
        public int? context, option;   // ability nodes
        public int global;
        public float? probability;     // null without a GNN model
    }

    /// <summary>The value head's estimate for the human, in [-1, 1], and the nodes it reads.</summary>
    public class GraphValue
    {
        public float? estimate;        // null without a GNN model
        public List<int> nodes;
    }

    public class GraphNode
    {
        public int id;
        public string type;       // card, player, global, ability
        public int? uid;          // card: the card on the board
        public string card_id;    // card
        public int? owner;        // card, player: 0 = the human, 1 = the opponent
        public string zone;       // card: hand, play, discard
        public int? card;         // ability: the id of its card's node
        public string kind;       // ability: entry, choose, effect, if, may, choose_one, end, modifier
        public string label;      // ability: its kind and what it does, e.g. "effect: deal_damage"
        public bool resolving;    // ability: the step being resolved now
        public List<List<float>> vectors;  // one per layer, averaged down to dim numbers
    }

    public class GraphEdge
    {
        public string type;       // belongs_to, faces, opposes, in, part_of, next, uses, matches, bound_to
        public int src;
        public int dst;
    }

    /// <summary>Action type names from the protocol.</summary>
    public static class ActionTypes
    {
        public const string Mulligan = "mulligan";
        public const string KeepHand = "keep_hand";
        public const string Play = "play";
        public const string Attack = "attack";
        public const string AttackHero = "attack_hero";
        public const string SpareSpore = "spare_spore";
        public const string EndTurn = "end_turn";
        public const string ChooseTarget = "choose_target";
        public const string Accept = "accept";
        public const string Decline = "decline";
        public const string ChooseOption = "choose_option";
    }
}
