using System.Collections.Generic;
using Tcg.Protocol;
using UnityEngine;

namespace Tcg.Board
{
    /// <summary>
    /// Dev only: plays the human's side with random legal actions, through the same commands the
    /// UI sends, to check a whole game never gets stuck. Add it to the Game object in Play mode.
    /// </summary>
    public class AutoPlayer : MonoBehaviour
    {
        [Range(0f, 1f)] public float EndTurnChance = 0.15f;
        public float Interval = 0.2f;

        /// <summary>Human actions sent; the game it ended on, if any; a note if it got stuck.</summary>
        public int Actions { get; private set; }
        public int GamesFinished { get; private set; }
        public string Stuck { get; private set; }
        public readonly Dictionary<string, int> Answered = new Dictionary<string, int>();

        GameController _game;
        BoardView _board;
        float _next, _idleSince;

        void Awake()
        {
            _game = GetComponent<GameController>();
            _board = _game.Board;
        }

        void Update()
        {
            if (Time.time < _next || Stuck != null) return;
            _next = Time.time + Interval;
            var s = _board.State;
            if (s == null || _game.Busy) return;
            if (s.game_over)
            {
                GamesFinished++;
                enabled = false;
                return;
            }
            if (!s.HumanDecides)
            {
                // The controller asks the AI by itself; if nothing has moved for a while, it's stuck.
                if (_idleSince == 0f) _idleSince = Time.time;
                else if (Time.time - _idleSince > 10f) Stuck = $"no progress on turn {s.turn}, decision {s.decision_player}";
                return;
            }
            _idleSince = 0f;
            var pick = Pick(s);
            if (pick == null)
            {
                Stuck = $"no legal action on turn {s.turn} (pending: {s.pending?.kind ?? "none"})";
                return;
            }
            if (s.pending != null)
                Answered[s.pending.kind] = Answered.TryGetValue(s.pending.kind, out int n) ? n + 1 : 1;
            Actions++;
            _game.Execute(new ActionCommand(pick));
        }

        GameAction Pick(GameState s)
        {
            GameAction end = null;
            var options = new List<GameAction>();
            foreach (var a in s.legal_actions)
            {
                if (a.type == ActionTypes.EndTurn || a.type == ActionTypes.KeepHand) end = a;
                else if (a.type != ActionTypes.Mulligan) options.Add(a);
            }
            if (end != null && (options.Count == 0 || Random.value < EndTurnChance)) return end;
            return options.Count > 0 ? options[Random.Range(0, options.Count)] : end;
        }
    }
}
