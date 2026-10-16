using System.Collections.Generic;
using Tcg.Protocol;
using Tcg.View;
using UnityEngine;

namespace Tcg.Board
{
    /// <summary>
    /// The client flow from docs/client-protocol.md: card_set, new_game, then render each state.
    /// The human acts only through the END TURN button for now (the matching legal action);
    /// the AI's decisions run through ai_turn.
    /// </summary>
    public class GameController : MonoBehaviour
    {
        public NetworkClient Network;
        public BoardView Board;

        [Tooltip("neural, heuristic or random.")]
        public string Opponent = "neural";
        [Tooltip("Used when the server has no trained model for the neural opponent.")]
        public string FallbackOpponent = "heuristic";
        public int HumanSeat = 0;
        [Tooltip("Negative: a random game each time.")]
        public int Seed = -1;

        readonly Dictionary<string, CardDef> _cards = new Dictionary<string, CardDef>();
        GameState _state;
        string _opponentName = "";
        bool _busy;

        void Start()
        {
            Network.ConnectionError += OnConnectionError;
            Board.EndTurnButton.onClick.AddListener(OnEndTurnPressed);
            Board.SetEndTurnButton(UiText.Waiting, false);
            _busy = true;
            Network.Send<CardSetResponse>(new Request("card_set"), OnCardSet);
        }

        void OnCardSet(CardSetResponse r)
        {
            if (!Check(r)) return;
            _cards.Clear();
            foreach (var c in r.cards) _cards[c.id] = c;
            Debug.Log($"Card set {r.name}: {_cards.Count} cards");
            NewGame(Opponent);
        }

        void NewGame(string opponent)
        {
            _busy = true;
            Network.Send<StateResponse>(new NewGameRequest(opponent, HumanSeat, Seed >= 0 ? Seed : (int?)null), r =>
            {
                if (!r.Ok && opponent != FallbackOpponent && !string.IsNullOrEmpty(FallbackOpponent))
                {
                    Debug.LogWarning($"new_game with {opponent} failed ({r.msg}); trying {FallbackOpponent}");
                    NewGame(FallbackOpponent);
                    return;
                }
                if (!Check(r)) return;
                _opponentName = r.opponent;
                Board.ShowMessage(null);
                Apply(r);
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
            var action = PrimaryAction(_state);
            if (action == null) return;
            _busy = true;
            Board.SetEndTurnButton(action.text.ToUpperInvariant(), false);
            Network.Send<StateResponse>(new ActRequest(action.index), r =>
            {
                if (!Check(r)) return;
                Debug.Log($"You: {r.action.text}");
                Apply(r);
            });
        }

        /// <summary>Renders a state, then hands the decision to the AI if it's theirs.</summary>
        void Apply(StateResponse r)
        {
            _state = r.state;
            Board.Render(_state, _cards, _opponentName);
            if (!_state.game_over && !_state.HumanDecides)
            {
                _busy = true;
                Board.SetEndTurnButton(UiText.Waiting, false);
                Network.Send<StateResponse>(new Request("ai_turn"), ai =>
                {
                    if (!Check(ai)) return;
                    foreach (var a in ai.actions) Debug.Log($"{_opponentName}: {a.text}");
                    Apply(ai);
                });
                return;
            }
            _busy = false;
            UpdateButton();
        }

        void UpdateButton()
        {
            if (_state.game_over)
            {
                Board.SetEndTurnButton(UiText.NewGame, true);
                return;
            }
            var action = PrimaryAction(_state);
            Board.SetEndTurnButton(action != null ? action.text.ToUpperInvariant() : UiText.Waiting, action != null);
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
            _busy = false;
            if (_state != null) UpdateButton();
            return false;
        }

        void OnConnectionError(string msg)
        {
            Debug.LogError(msg);
            Board.ShowMessage(msg);
            _busy = false;
            if (_state != null) UpdateButton();
            else Board.SetEndTurnButton(UiText.Waiting, false);
            // Still starting up: keep trying until the server answers.
            if (_cards.Count == 0)
            {
                _busy = true;
                Network.Send<CardSetResponse>(new Request("card_set"), OnCardSet);
            }
        }
    }
}
