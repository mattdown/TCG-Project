using System;
using System.Collections.Generic;
using DG.Tweening;
using Tcg.Protocol;
using Tcg.View;
using TMPro;
using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.UI;

namespace Tcg.Board
{
    /// <summary>
    /// Drag to act, tap to inspect (docs/client-design.md, "Interaction"). Every drop zone comes
    /// from the state's legal_actions: a zone lights up only if a matching action exists, and a
    /// drop sends that action's index. Previews come from the server's action previews.
    /// </summary>
    public class BoardInteraction : MonoBehaviour, ICardInputHandler
    {
        public BoardView Board;

        /// <summary>The human decided something: send it to the server.</summary>
        public event Action<IGameCommand> CommandIssued;
        public event Action NewGameRequested;

        /// <summary>True while the human may act: their decision and no request in flight.</summary>
        public bool Interactive { get; set; }
        public ArrowView Arrow { get; private set; }

        /// <summary>The cards picked to put back during the mulligan, in hand order.</summary>
        public IReadOnlyList<int> MulliganSelection => _mulligan.Selection;

        InspectView _inspect;
        MulliganView _mulligan;
        GameOverView _gameOver;
        DropZone _field, _energy, _score;
        RectTransform _finger;

        CardView _dragged;
        bool _arrowMode;
        readonly List<GameAction> _options = new List<GameAction>();
        GameAction _hover;

        static readonly Color PlayLabel = Palette.Hex("#2F8A27");
        static readonly Color EnergyLabel = Palette.Hex("#A32A9A");
        static readonly Color ScoreLabel = Palette.Hex("#C77E0E");
        static readonly Color BadgeRed = Palette.Hex("#C42A3A");

        void Start()
        {
            Ui.Theme = Board.Theme;
            Board.InputHandler = this;
            var root = Board.Root;
            int below = root.Find("Fade").GetSiblingIndex() + 1;

            _field = DropZone.Create("PlayZone", root, Palette.GlowPlayable, PlayLabel, 0.18f);
            Ui.Anchor(_field.Rect, new Vector2(0.5f, 1), new Vector2(0.5f, 1), new Vector2(0, -282), new Vector2(1200, 198));
            _field.PlaceLabel(new Vector2(0.5f, 1), new Vector2(0.5f, 0.5f), Vector2.zero);
            _energy = DropZone.Create("EnergyZone", root, Palette.Energy, EnergyLabel, 0.25f);
            Ui.Anchor(_energy.Rect, new Vector2(1, 0), new Vector2(1, 0), new Vector2(-14, 180), new Vector2(266, 52));
            _energy.PlaceLabel(new Vector2(0, 1), new Vector2(1, 1), new Vector2(-12, -10));
            _score = DropZone.Create("ScoreZone", root, Palette.Gold, ScoreLabel, 0.22f);
            Ui.Anchor(_score.Rect, new Vector2(0, 0), new Vector2(0, 0), new Vector2(12, 126), new Vector2(276, 100));
            _score.PlaceLabel(new Vector2(0, 1), new Vector2(0, 0.5f), new Vector2(16, 0));
            foreach (var z in new[] { _field, _energy, _score }) z.Rect.SetSiblingIndex(below);

            Arrow = ArrowView.Create(Board.TopLayer);
            _finger = Ui.Node("Finger", Board.TopLayer);
            _finger.sizeDelta = new Vector2(34, 34);
            Ui.Img(_finger, Board.Theme.Dot, Color.white.WithAlpha(0.35f));
            Ui.Img(Ui.Stretch("Edge", _finger, 0, 0, 0, 0), Board.Theme.TargetRing, Color.white);
            _finger.gameObject.SetActive(false);

            _inspect = InspectView.Create(root, Board.CardPrefab);
            _inspect.ActionChosen += a => CommandIssued?.Invoke(new ActionCommand(a));
            _mulligan = MulliganView.Create(root, Board.CardPrefab);
            _mulligan.KeepRequested += putBack => CommandIssued?.Invoke(new MulliganCommand(putBack));
            _gameOver = GameOverView.Create(root);
            _gameOver.NewGameRequested += () => NewGameRequested?.Invoke();
        }

        /// <summary>Shows the screens that depend on the phase: mulligan and game over.</summary>
        public void OnStateChanged(GameState s, IReadOnlyDictionary<string, CardDef> defs, string opponentName)
        {
            if (s.InMulligan && s.HumanDecides) _mulligan.Show(s, defs);
            else _mulligan.Hide();
            if (s.game_over) _gameOver.Show(s, opponentName);
            else _gameOver.Hide();
            if (_inspect.IsOpen) _inspect.Hide();
        }

        // --- taps

        public void OnCardTap(CardView card)
        {
            if (_dragged != null || Board.State == null || card.Def == null) return;
            var s = Board.State;
            CardInstance instance = Find(s.Human.hand, card.Uid) ?? Find(s.Human.play, card.Uid) ?? Find(s.Opponent.play, card.Uid);
            string owner = Board.IsInHumanHand(card.Uid) ? UiText.InYourHand
                : Board.IsHumanUnit(card.Uid) ? UiText.YourUnit : UiText.OpponentsUnit;
            _inspect.Show(card.Def, instance, owner, Board.IsInHumanHand(card.Uid), s);
        }

        static CardInstance Find(List<CardInstance> cards, int uid)
        {
            if (cards == null) return null;
            foreach (var c in cards) if (c.uid == uid) return c;
            return null;
        }

        // --- drags

        public bool OnCardDragStart(CardView card, PointerEventData e)
        {
            if (!Interactive || Board.State == null || _inspect.IsOpen) return false;
            int uid = card.Uid;
            _options.Clear();
            _hover = null;
            if (Board.IsInHumanHand(uid))
            {
                Collect(uid, ActionTypes.Play, ActionTypes.AddEnergy);
                _arrowMode = false;
                card.Rect.DOKill();
                card.transform.SetParent(Board.TopLayer, true);
                card.SetMark(CardMark.None);
                foreach (var a in _options)
                    (a.type == ActionTypes.Play ? _field : _energy).Show(false, null);
            }
            else if (Board.IsHumanUnit(uid))
            {
                Collect(uid, ActionTypes.Score, ActionTypes.Duel);
                if (_options.Count == 0) return false;
                _arrowMode = true;
                card.SetMark(CardMark.Selected);
                foreach (var unit in Board.OpponentUnitViews())
                {
                    bool target = _options.Exists(a => a.type == ActionTypes.Duel && a.target == unit.Uid);
                    if (target) unit.SetTargetRing(TargetRing.Valid);
                    else unit.SetDimmed(true);
                }
                if (_options.Exists(a => a.type == ActionTypes.Score)) _score.Show(false, null);
            }
            else
            {
                return false;
            }
            _dragged = card;
            _finger.gameObject.SetActive(true);
            _finger.SetAsLastSibling();
            OnCardDrag(card, e);
            return true;
        }

        void Collect(int uid, params string[] types)
        {
            foreach (var a in Board.State.legal_actions)
                if (a.card == uid && Array.IndexOf(types, a.type) >= 0) _options.Add(a);
        }

        public void OnCardDrag(CardView card, PointerEventData e)
        {
            if (_dragged != card) return;
            RectTransformUtility.ScreenPointToLocalPointInRectangle(Board.TopLayer, e.position, e.pressEventCamera, out var p);
            _finger.anchoredPosition = p;
            var hover = FindHover(e);
            if (hover != _hover)
            {
                ClearHover();
                _hover = hover;
                ShowHover();
            }
            if (_arrowMode)
            {
                Vector2 from = Board.ToTop(card.Rect.position);
                bool duel = _hover != null && _hover.type == ActionTypes.Duel;
                Vector2 to = duel ? Board.ToTop(Board.CardByUid(_hover.target.Value).Rect.position) : p;
                Color colour = _hover == null ? Color.white : duel ? Palette.GlowTarget : Palette.Gold;
                Arrow.Show(from, to, colour, duel);
                Arrow.transform.SetAsLastSibling();
                _finger.SetAsLastSibling();
            }
            else
            {
                // Held above the finger, tilting with the motion; smaller over the energy bar so the
                // new gem slot stays visible.
                bool overEnergy = _hover != null && _hover.type == ActionTypes.AddEnergy;
                card.Rect.anchoredPosition = p + new Vector2(0f, overEnergy ? 90f : 70f);
                float tilt = Mathf.Clamp(-e.delta.x * 0.6f, -8f, 8f);
                card.Rect.localRotation = Quaternion.Slerp(card.Rect.localRotation, Quaternion.Euler(0, 0, tilt), 0.3f);
                card.Rect.localScale = Vector3.Lerp(card.Rect.localScale, Vector3.one * (overEnergy ? 0.7f : 0.95f), 0.35f);
            }
        }

        GameAction FindHover(PointerEventData e)
        {
            var cam = e.pressEventCamera;
            foreach (var a in _options)
            {
                switch (a.type)
                {
                    case ActionTypes.AddEnergy:
                        if (_energy.Contains(e.position, cam)) return a;
                        break;
                    case ActionTypes.Play:
                        if (_field.Contains(e.position, cam)) return a;
                        break;
                    case ActionTypes.Score:
                        if (_score.Contains(e.position, cam)) return a;
                        break;
                    case ActionTypes.Duel:
                        var target = a.target.HasValue ? Board.CardByUid(a.target.Value) : null;
                        if (target != null && RectTransformUtility.RectangleContainsScreenPoint(target.Rect, e.position, cam))
                            return a;
                        break;
                }
            }
            return null;
        }

        void ShowHover()
        {
            if (_hover == null) return;
            var preview = _hover.preview ?? new ActionResult();
            int me = Board.State.human_seat;
            switch (_hover.type)
            {
                case ActionTypes.Play:
                    _field.Show(true, string.Format(UiText.DropToPlay, preview.EnergyFor(me)));
                    Board.ShowGhostSlot(true);
                    Board.PreviewEnergySpend(preview.EnergyFor(me));
                    break;
                case ActionTypes.AddEnergy:
                    _energy.Show(true, UiText.DropToAddEnergy);
                    Board.PreviewNewGem(true);
                    break;
                case ActionTypes.Score:
                    _score.Show(true, string.Format(UiText.DropToScore, preview.VpFor(me)));
                    Board.PreviewVp(preview.VpFor(me));
                    break;
                case ActionTypes.Duel:
                    var target = Board.CardByUid(_hover.target.Value);
                    target.SetTargetRing(TargetRing.Hovered);
                    target.SetBadge(Outcome(preview, target.Uid), BadgeRed);
                    _dragged.SetBadge(Outcome(preview, _dragged.Uid), BadgeRed);
                    break;
            }
        }

        static string Outcome(ActionResult preview, int uid) =>
            preview.Defeats(uid) ? UiText.Defeated
            : preview.DamageTo(uid) > 0 ? string.Format(UiText.Takes, preview.DamageTo(uid)) : null;

        void ClearHover()
        {
            if (_hover == null) return;
            switch (_hover.type)
            {
                case ActionTypes.Play:
                    _field.Show(false, null);
                    Board.ShowGhostSlot(false);
                    Board.PreviewEnergySpend(0);
                    break;
                case ActionTypes.AddEnergy:
                    _energy.Show(false, null);
                    Board.PreviewNewGem(false);
                    break;
                case ActionTypes.Score:
                    _score.Show(false, null);
                    Board.PreviewVp(0);
                    break;
                case ActionTypes.Duel:
                    var target = Board.CardByUid(_hover.target.Value);
                    target.SetTargetRing(TargetRing.Valid);
                    target.SetBadge(null, Color.clear);
                    _dragged.SetBadge(null, Color.clear);
                    break;
            }
            _hover = null;
        }

        public void OnCardDragEnd(CardView card, PointerEventData e)
        {
            if (_dragged != card) return;
            var chosen = _hover;
            ClearHover();
            foreach (var z in new[] { _field, _energy, _score }) z.Hide();
            Arrow.Hide();
            _finger.gameObject.SetActive(false);
            _dragged = null;
            _options.Clear();
            if (chosen != null)
            {
                Interactive = false;
                CommandIssued?.Invoke(new ActionCommand(chosen));  // the card stays put until the new state moves it
            }
            else
            {
                Board.Relayout();  // snap back
            }
        }

        // --- drop zones

        /// <summary>A flat rounded rectangle: faint for an option, bright with a label under the finger.</summary>
        class DropZone
        {
            public RectTransform Rect;
            Image _fill, _edge;
            RectTransform _label;
            TMP_Text _labelText;
            Color _colour;
            float _fillAlpha;

            public static DropZone Create(string name, RectTransform parent, Color colour, Color labelBg, float fillAlpha)
            {
                var z = new DropZone { _colour = colour, _fillAlpha = fillAlpha };
                z.Rect = Ui.Node(name, parent);
                z._fill = Ui.Rounded(Ui.Stretch("Fill", z.Rect, 0, 0, 0, 0), Color.white, 20);
                z._edge = Ui.Outline(Ui.Stretch("Edge", z.Rect, 0, 0, 0, 0), Color.white, 20);
                z._label = Ui.Node("Label", z.Rect);
                z._labelText = Ui.Pill(z._label, "", labelBg);
                z.Hide();
                return z;
            }

            public void PlaceLabel(Vector2 anchor, Vector2 pivot, Vector2 position) =>
                Ui.Anchor(_label, anchor, pivot, position, _label.sizeDelta);

            public void Show(bool bright, string label)
            {
                Rect.gameObject.SetActive(true);
                _fill.color = bright ? _colour.WithAlpha(_fillAlpha) : Color.white.WithAlpha(0.10f);
                _edge.color = bright ? _colour : Color.white.WithAlpha(0.35f);
                _edge.pixelsPerUnitMultiplier = Ui.SliceRadius / (bright ? 20f : 14f);
                _label.gameObject.SetActive(bright && !string.IsNullOrEmpty(label));
                if (bright) _labelText.text = label;
            }

            public void Hide() => Rect.gameObject.SetActive(false);

            public bool Contains(Vector2 screen, Camera cam) =>
                Rect.gameObject.activeSelf && RectTransformUtility.RectangleContainsScreenPoint(Rect, screen, cam);
        }
    }
}
