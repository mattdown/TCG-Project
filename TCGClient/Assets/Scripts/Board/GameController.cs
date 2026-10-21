using System.Collections;
using System.Collections.Generic;
using Newtonsoft.Json.Linq;
using Tcg.Protocol;
using Tcg.View;
using UnityEngine;

namespace Tcg.Board
{
    /// <summary>
    /// The client flow from docs/client-protocol.md: card_set, new_game, then render each state.
    /// The human acts by dragging, by the inspect buttons, or with END TURN; the AI's decisions
    /// run one ai_move at a time so each can be shown, animated from the server's action results.
    /// </summary>
    public class GameController : MonoBehaviour
    {
        public NetworkClient Network;
        public BoardView Board;
        public BoardInteraction Interaction;

        [Tooltip("neural, heuristic or random.")]
        public string Opponent = "neural";
        [Tooltip("Used when the server has no trained model for the neural opponent.")]
        public string FallbackOpponent = "heuristic";
        public int HumanSeat = 0;
        [Tooltip("Negative: a random game each time.")]
        public int Seed = -1;
        [Tooltip("Pause between the AI's decisions, in seconds.")]
        public float AiStepDelay = 0.6f;

        readonly Dictionary<string, CardDef> _cards = new Dictionary<string, CardDef>();
        GameState _state;
        string _opponentName = "";
        bool _busy;
        JObject _scenario;  // the dev panel's last scenario: NEW GAME replays it
        int? _scenarioSeed;

        void Start()
        {
            Network.ConnectionError += OnConnectionError;
            Board.EndTurnButton.onClick.AddListener(OnEndTurnPressed);
            Board.SpareSporeButton.onClick.AddListener(() =>
            {
                var spore = _state != null ? Commands.Find(_state, x => x.type == ActionTypes.SpareSpore) : null;
                if (spore != null) Execute(new ActionCommand(spore));
            });
            Interaction.CommandIssued += Execute;
            Interaction.NewGameRequested += () => NewGame(Opponent);
            Interaction.ScenarioRequested += (scenario, seed) =>
            {
                _scenario = scenario;
                _scenarioSeed = seed;
                NewGame(Opponent);
            };
            SetBusy(true);
            Network.Send<CardSetResponse>(new Request("card_set"), OnCardSet);
        }

        void OnCardSet(CardSetResponse r)
        {
            if (!Check(r)) return;
            _cards.Clear();
            foreach (var c in r.cards) _cards[c.id] = c;
            CardText.Keywords = r.keywords ?? new Dictionary<string, KeywordInfo>();
            Debug.Log($"Card set {r.name}: {_cards.Count} cards");
            NewGame(Opponent);
        }

        void NewGame(string opponent)
        {
            SetBusy(true);
            int? seed = _scenarioSeed ?? (Seed >= 0 ? Seed : (int?)null);
            Network.Send<StateResponse>(new NewGameRequest(opponent, HumanSeat, seed, _scenario), r =>
            {
                if (!r.Ok && opponent != FallbackOpponent && !string.IsNullOrEmpty(FallbackOpponent))
                {
                    Debug.LogWarning($"new_game with {opponent} failed ({r.msg}); trying {FallbackOpponent}");
                    NewGame(FallbackOpponent);
                    return;
                }
                if (!Check(r)) return;
                _opponentName = r.opponent;
                _state = null;  // a fresh board: nothing to animate from
                Board.ShowMessage(null);
                StartCoroutine(Advance(r));
            });
        }

        /// <summary>True while a request is in flight or a reply is being shown.</summary>
        public bool Busy => _busy;

        /// <summary>Sends the human's command, one act per step; only its last reply is shown.</summary>
        public void Execute(IGameCommand command)
        {
            var action = !_busy && _state != null && _state.HumanDecides ? command.NextAction(_state) : null;
            if (action == null)
            {
                Board.Relayout();
                return;
            }
            SetBusy(true);
            Send(command, action);
        }

        void Send(IGameCommand command, GameAction action)
        {
            Network.Send<StateResponse>(new ActRequest(action.index), r =>
            {
                if (!Check(r)) return;
                Debug.Log($"You: {r.action.text}");
                var next = r.state.HumanDecides ? command.NextAction(r.state) : null;
                if (next != null)
                {
                    _state = r.state;  // a middle step: not shown
                    Send(command, next);
                    return;
                }
                StartCoroutine(Advance(r));
            });
        }

        void OnEndTurnPressed()
        {
            if (_busy || _state == null) return;
            if (_state.game_over)
            {
                NewGame(Opponent);
                return;
            }
            if (_state.InMulligan)
            {
                Execute(new MulliganCommand(Interaction.MulliganSelection));
                return;
            }
            var action = PrimaryAction(_state);
            if (action == null) return;
            Board.SetEndTurnButton(action.text.ToUpperInvariant(), false);
            Execute(new ActionCommand(action));
        }

        /// <summary>Shows a reply's action and state, then hands the decision to the AI if it's theirs.</summary>
        IEnumerator Advance(StateResponse r)
        {
            SetBusy(true);
            bool fromOpponent = _state != null && r.action != null && r.action.player.HasValue &&
                                r.action.player.Value != _state.human_seat;
            if (fromOpponent)
            {
                Debug.Log($"{_opponentName}: {r.action.text}");
                yield return Board.ShowAction(r.action, Interaction.Arrow);
            }
            bool animate = _state != null;
            _state = r.state;
            Board.Render(_state, _cards, _opponentName, animate, r.action);
            Interaction.OnStateChanged(_state, _cards, _opponentName);

            if (!_state.game_over && !_state.HumanDecides)
            {
                Board.SetEndTurnButton(UiText.Waiting, false);
                // Leave the AI's ability prompt up a little longer, so it can be read.
                yield return new WaitForSeconds(_state.pending != null ? AiStepDelay * 2f : AiStepDelay);
                Network.Send<StateResponse>(new Request("ai_move"), ai =>
                {
                    if (Check(ai)) StartCoroutine(Advance(ai));
                });
                yield break;
            }
            SetBusy(false);
        }

        void SetBusy(bool busy)
        {
            _busy = busy;
            Interaction.Interactive = !busy && _state != null && _state.HumanDecides;
            Board.SetEndTurnGlow(!busy && NothingLeftButEndTurn(_state));
            if (busy || _state == null)
            {
                if (busy) Board.SetEndTurnButton(Board.EndTurnLabel.text, false);
                return;
            }
            if (_state.game_over)
            {
                Board.SetEndTurnButton(UiText.NewGame, true);
                return;
            }
            var action = PrimaryAction(_state);
            Board.SetEndTurnButton(action != null ? action.text.ToUpperInvariant() : UiText.Waiting, action != null);
        }

        /// <summary>
        /// Your main-phase decision with only END TURN left to do (the Spare Spore alone doesn't
        /// count: it only matters if there's something to spend the mana on).
        /// </summary>
        static bool NothingLeftButEndTurn(GameState s)
        {
            if (s == null || !s.HumanDecides || s.InMulligan || s.pending != null) return false;
            bool canEnd = false;
            foreach (var a in s.legal_actions)
            {
                if (a.type == ActionTypes.EndTurn) canEnd = true;
                else if (a.type != ActionTypes.SpareSpore) return false;
            }
            return canEnd;
        }

        /// <summary>The legal action the button stands for: end_turn, or keep_hand during the mulligan.</summary>
        static GameAction PrimaryAction(GameState s)
        {
            GameAction keep = null;
            foreach (var a in s.legal_actions)
            {
                if (a.type == ActionTypes.EndTurn) return a;
                if (a.type == ActionTypes.KeepHand) keep = a;
            }
            return keep;
        }

        bool Check(Response r)
        {
            if (r.Ok) return true;
            Debug.LogWarning($"Server error: {r.msg}");
            Board.ShowMessage(r.msg);
            SetBusy(false);
            Board.Relayout();
            return false;
        }

        void OnConnectionError(string msg)
        {
            Debug.LogError(msg);
            Board.ShowMessage(msg);
            SetBusy(false);
            Board.Relayout();
            // Still starting up: keep trying until the server answers.
            if (_cards.Count == 0)
            {
                SetBusy(true);
                Network.Send<CardSetResponse>(new Request("card_set"), OnCardSet);
            }
        }
    }
}
