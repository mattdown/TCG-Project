using System.Collections.Generic;

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
        public NewGameRequest(string opponent, int humanSeat, int? seed) : base("new_game")
        {
            this.opponent = opponent;
            human_seat = humanSeat;
            this.seed = seed;
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
    }

    /// <summary>Reply to new_game, state, act, ai_move and ai_turn; the fields not sent stay null.</summary>
    public class StateResponse : Response
    {
        public GameState state;
        public string opponent;            // new_game: the AI's name
        public GameAction action;          // act, ai_move
        public List<GameAction> actions;   // ai_turn
    }

    // --- data

    public class CardDef
    {
        public string id;
        public string name;
        public string type;
        public List<string> aspects;
        public bool energy_source;
        public int cost;
        public int power;
        public int health;
        public int score;
        public List<string> traits;
    }

    /// <summary>One physical card. uid is stable for the whole game, across zones.</summary>
    public class CardInstance
    {
        public int uid;
        public string card_id;
        public bool exhausted;
        public bool fresh;
        public int damage;
    }

    public class PlayerState
    {
        public int vp;
        public int energy_ready;
        public int energy_total;
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
        public List<PlayerAmount> vp = new List<PlayerAmount>();
        public List<PlayerAmount> energy_spent = new List<PlayerAmount>();
        public List<int> exhausted = new List<int>();
        public List<int> readied = new List<int>();
        public List<CardMove> moves = new List<CardMove>();

        public int DamageTo(int uid)
        {
            foreach (var d in damage) if (d.uid == uid) return d.amount;
            return 0;
        }

        public bool Defeats(int uid) => defeated.Contains(uid);
        public int VpFor(int player) => AmountFor(vp, player);
        public int EnergyFor(int player) => AmountFor(energy_spent, player);

        static int AmountFor(List<PlayerAmount> list, int player)
        {
            foreach (var e in list) if (e.player == player) return e.amount;
            return 0;
        }
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
        public const string Energy = "energy";
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
        public int vp_to_win;
        public List<GameAction> legal_actions;

        public PlayerState Human => players[human_seat];
        public PlayerState Opponent => players[1 - human_seat];
        public bool HumanDecides => !game_over && decision_player == human_seat;
        public bool InMulligan => phase == "mulligan";
    }

    /// <summary>Action type names from the protocol.</summary>
    public static class ActionTypes
    {
        public const string Mulligan = "mulligan";
        public const string KeepHand = "keep_hand";
        public const string AddEnergy = "add_energy";
        public const string Play = "play";
        public const string Score = "score";
        public const string Duel = "duel";
        public const string EndTurn = "end_turn";
    }
}
