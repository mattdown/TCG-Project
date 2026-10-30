using System;
using System.Collections.Generic;
using DG.Tweening;
using Newtonsoft.Json.Linq;
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
        /// <summary>The dev panel's START: a scenario and an optional seed.</summary>
        public event Action<JObject, int?> ScenarioRequested;

        /// <summary>True while the human may act: their decision and no request in flight.</summary>
        public bool Interactive { get; set; }
        public ArrowView Arrow { get; private set; }

        /// <summary>The cards picked to put back during the mulligan, in hand order.</summary>
        public IReadOnlyList<int> MulliganSelection => _mulligan.Selection;

        InspectView _inspect;
        MulliganView _mulligan;
        GameOverView _gameOver;
        ChoiceBanner _choice;
        DevPanel _dev;
        HelpView _help;
        DropZone _field;
        RectTransform _finger;

        CardView _dragged;
        bool _arrowMode;
        readonly List<GameAction> _options = new List<GameAction>();
        GameAction _hover;

        static readonly Color PlayLabel = Palette.Hex("#2F8A27");
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
            _field.Rect.SetSiblingIndex(below);

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
            _choice = ChoiceBanner.Create(root);
            _choice.AnswerChosen += a => CommandIssued?.Invoke(new ActionCommand(a));
            _help = HelpView.Create(root, Board.CardPrefab);
            Board.HelpButton.onClick.AddListener(() => _help.Show(Board.Defs));
            _dev = DevPanel.Create(root);
            _dev.ScenarioRequested += (scenario, seed) => ScenarioRequested?.Invoke(scenario, seed);
        }

        /// <summary>Shows the screens that depend on the phase: mulligan and game over.</summary>
        public void OnStateChanged(GameState s, IReadOnlyDictionary<string, CardDef> defs, string opponentName)
        {
            if (s.InMulligan && s.HumanDecides) _mulligan.Show(s, defs);
            else _mulligan.Hide();
            if (s.game_over) _gameOver.Show(s, opponentName);
            else _gameOver.Hide();
            if (_inspect.IsOpen) _inspect.Hide();

            // An ability waiting on a choice: the prompt, and a gold ring on each card it can pick.
            if (s.pending != null && !s.game_over) _choice.Show(s, defs, opponentName);
            else _choice.Hide();
            foreach (var a in s.legal_actions)
                if (a.type == ActionTypes.ChooseTarget && a.target.HasValue)
                    Board.CardByUid(a.target.Value)?.SetChoiceRing(true);
            _dev.transform.SetAsLastSibling();
            if (_help.IsOpen) _help.transform.SetAsLastSibling();  // the AI may move while you read it
        }

        // --- taps

        public void OnCardTap(CardView card)
        {
            if (_dragged != null || Board.State == null || card.Def == null) return;
            var s = Board.State;
            if (Interactive && s.pending != null)
            {
                // Answering "choose a card": the tapped card, if it's one of the candidates.
                foreach (var a in s.legal_actions)
                    if (a.type == ActionTypes.ChooseTarget && a.target == card.Uid)
                    {
                        Interactive = false;
                        CommandIssued?.Invoke(new ActionCommand(a));
                        return;
                    }
            }
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
                Collect(uid, ActionTypes.Play);
                _arrowMode = false;
                card.Rect.DOKill();
                card.transform.SetParent(Board.TopLayer, true);
                card.SetMark(CardMark.None);
                if (_options.Count > 0) _field.Show(false, null);
            }
            else if (Board.IsHumanUnit(uid))
            {
                Collect(uid, ActionTypes.Attack, ActionTypes.AttackHero);
                if (_options.Count == 0) return false;
                _arrowMode = true;
                card.SetMark(CardMark.Selected);
                // Only legal targets light up: Guard, hidden Elusive units and so on are the server's call.
                foreach (var unit in Board.OpponentUnitViews())
                {
                    bool target = _options.Exists(a => a.type == ActionTypes.Attack && a.target == unit.Uid);
                    if (target) unit.SetTargetRing(TargetRing.Valid);
                    else unit.SetDimmed(true);
                }
                Board.SetHeroTarget(_options.Exists(a => a.type == ActionTypes.AttackHero), false);
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
            if (!_arrowMode)
            {
                // Held above the finger, clear of its text, tilting with the motion.
                card.Rect.anchoredPosition = p + new Vector2(0f, 130f);
                float tilt = Mathf.Clamp(-e.delta.x * 0.6f, -8f, 8f);
                card.Rect.localRotation = Quaternion.Slerp(card.Rect.localRotation, Quaternion.Euler(0, 0, tilt), 0.3f);
                card.Rect.localScale = Vector3.Lerp(card.Rect.localScale, Vector3.one * 0.95f, 0.35f);
            }
            var hover = FindHover(e, card);
            if (hover != _hover)
            {
                ClearHover();
                _hover = hover;
                ShowHover();
            }
            if (_arrowMode)
            {
                Vector2 from = Board.ToTop(card.Rect.position);
                bool unit = _hover != null && _hover.type == ActionTypes.Attack;
                Vector2 to = unit ? Board.ToTop(Board.CardByUid(_hover.target.Value).Rect.position)
                    : _hover != null ? Board.ToTop(Board.OpponentHealthText.transform.position) : p;
                Arrow.Show(from, to, _hover == null ? Color.white : Palette.GlowTarget, _hover != null);
                Arrow.transform.SetAsLastSibling();
                _finger.SetAsLastSibling();
            }
        }

        /// <summary>A play counts where the held card's centre is, since it hangs above the finger; attacks follow the finger.</summary>
        GameAction FindHover(PointerEventData e, CardView card)
        {
            var cam = e.pressEventCamera;
            var centre = RectTransformUtility.WorldToScreenPoint(cam, card.Rect.position);
            foreach (var a in _options)
            {
                switch (a.type)
                {
                    case ActionTypes.Play:
                        if (_field.Contains(centre, cam)) return a;
                        break;
                    case ActionTypes.AttackHero:
                        if (RectTransformUtility.RectangleContainsScreenPoint(Board.OpponentHero, e.position, cam)) return a;
                        break;
                    case ActionTypes.Attack:
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
                    _field.Show(true, string.Format(UiText.DropToPlay, preview.ManaFor(me)));
                    if (!_dragged.Def.IsAction) Board.ShowGhostSlot(true);  // action cards don't stay in play
                    Board.PreviewManaSpend(preview.ManaFor(me));
                    break;
                case ActionTypes.AttackHero:
                    Board.SetHeroTarget(true, true, preview.HeroDamageTo(1 - me));
                    _dragged.SetBadge(Outcome(preview, _dragged.Uid), BadgeRed);
                    break;
                case ActionTypes.Attack:
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
                    Board.PreviewManaSpend(0);
                    break;
                case ActionTypes.AttackHero:
                    Board.SetHeroTarget(true, false);
                    _dragged.SetBadge(null, Color.clear);
                    break;
                case ActionTypes.Attack:
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
            _field.Hide();
            Board.SetHeroTarget(false, false);
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
