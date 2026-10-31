using System;
using System.Collections.Generic;
using Tcg.Protocol;
using Tcg.View;
using TMPro;
using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.InputSystem;
using UnityEngine.UI;

namespace Tcg.Board
{
    /// <summary>
    /// Tap to inspect (the mockup's "Landscape inspect"): the card at about 2x over a dimmed board,
    /// a box for anything that needs explaining, and PLAY for hand cards, enabled only when the
    /// legal action exists. From a hand card, arrows (or the ← → keys) step through your hand
    /// without closing it. Tap anywhere to close.
    /// </summary>
    public class InspectView : MonoBehaviour
    {
        const float Scale = 2.1f;
        static readonly Color ChipOpponent = Palette.OpponentAccent;
        static readonly Color ChipNeutral = Palette.Glass;

        public event Action<GameAction> ActionChosen;
        /// <summary>PLAY tapped on a card that can't be played now: why not.</summary>
        public event Action<string> Refused;
        /// <summary>An arrow: -1 for the previous card, +1 for the next.</summary>
        public event Action<int> Stepped;
        public bool IsOpen => gameObject.activeSelf;

        CardView _card;
        RectTransform _chips, _column, _buttons;
        Button _play, _prev, _next;
        TMP_Text _count;
        readonly List<GameObject> _built = new List<GameObject>();
        GameAction _playAction;
        string _unusable;

        public static InspectView Create(RectTransform parent, CardView prefab)
        {
            var root = Ui.Stretch("Inspect", parent, 0, 0, 0, 0);
            var view = root.gameObject.AddComponent<InspectView>();
            Ui.Scrim(root, "Scrim", 0.8f).onClick.AddListener(view.Hide);

            var holder = Ui.Box("Card", root, 300, 122, CardView.Width * Scale, CardView.Height * Scale);
            view._card = Instantiate(prefab, holder);
            view._card.Rect.anchorMin = view._card.Rect.anchorMax = new Vector2(0.5f, 0.5f);
            view._card.Rect.anchoredPosition = Vector2.zero;
            view._card.Rect.localScale = Vector3.one * Scale;
            view._card.Group.blocksRaycasts = false;  // taps go through to the scrim

            view._chips = Ui.Box("Chips", root, 300, 62, 700, 30);
            var chipLayout = view._chips.gameObject.AddComponent<HorizontalLayoutGroup>();
            chipLayout.spacing = 6;
            chipLayout.childControlWidth = chipLayout.childControlHeight = false;
            chipLayout.childForceExpandWidth = chipLayout.childForceExpandHeight = false;

            view._prev = Arrow(root, "Previous", UiText.Previous, 222, view, -1);
            view._next = Arrow(root, "Next", UiText.Next, 300 + CardView.Width * Scale + 22, view, 1);
            view._count = Ui.Body(Ui.Box("Count", root, 300, 122 + CardView.Height * Scale + 10, CardView.Width * Scale, 24),
                "", 14, Palette.SubtleText, TextAlignmentOptions.Center);

            view._column = Ui.Box("Column", root, 700, 122, 340, 400);
            var col = view._column.gameObject.AddComponent<VerticalLayoutGroup>();
            col.spacing = 12;
            col.childControlWidth = col.childControlHeight = true;
            col.childForceExpandWidth = true;
            col.childForceExpandHeight = false;
            view._column.gameObject.AddComponent<ContentSizeFitter>().verticalFit = ContentSizeFitter.FitMode.PreferredSize;

            // Pinned level with the card's bottom edge, so it stays put however many boxes there are.
            const float buttonHeight = 56f;
            view._buttons = Ui.Box("Buttons", root, 700, 122 + CardView.Height * Scale - buttonHeight, 340, buttonHeight);
            var row = view._buttons.gameObject.AddComponent<HorizontalLayoutGroup>();
            row.spacing = 12;
            row.childControlWidth = row.childControlHeight = true;
            row.childForceExpandWidth = row.childForceExpandHeight = true;
            view._play = Ui.Button(Ui.Node("Play", view._buttons), UiText.PlayButton, Palette.GlowPlayable, 19, out _, true);
            view._play.onClick.AddListener(() =>
            {
                if (view._playAction == null && view._unusable != null) view.Refused?.Invoke(view._unusable);
                else view.Choose(view._playAction);
            });

            Ui.Body(Ui.TopStrip("Hint", root, 0, 652, 24), UiText.TapToClose, 14, Palette.SubtleText,
                TextAlignmentOptions.Center);
            root.gameObject.SetActive(false);
            return view;
        }

        static Button Arrow(RectTransform root, string name, string label, float x, InspectView view, int step)
        {
            const float size = 56f;
            var rt = Ui.Box(name, root, x, 122 + (CardView.Height * Scale - size) / 2f, size, size);
            var button = Ui.Button(rt, label, Palette.Lantern, 20, out var text);
            text.characterSpacing = 0f;
            button.onClick.AddListener(() => view.Stepped?.Invoke(step));
            return button;
        }

        /// <summary>Where this card is among the ones the arrows step through (1-based); fewer than 2 hides the arrows.</summary>
        public void SetPosition(int position, int count)
        {
            _prev.gameObject.SetActive(count > 1);
            _next.gameObject.SetActive(count > 1);
            _prev.interactable = position > 1;
            _next.interactable = position < count;
            _count.text = count > 1 ? string.Format(UiText.InspectCount, position, count) : "";
        }

        void Update()
        {
            var keys = Keyboard.current;
            if (keys == null) return;
            if (keys.leftArrowKey.wasPressedThisFrame && _prev.isActiveAndEnabled && _prev.interactable) Stepped?.Invoke(-1);
            else if (keys.rightArrowKey.wasPressedThisFrame && _next.isActiveAndEnabled && _next.interactable) Stepped?.Invoke(1);
            else if (keys.escapeKey.wasPressedThisFrame) Hide();
        }

        public void Show(CardDef def, CardInstance instance, string owner, bool inHand, GameState s)
        {
            foreach (var go in _built) Destroy(go);
            _built.Clear();
            gameObject.SetActive(true);
            transform.SetAsLastSibling();
            _card.Bind(def, instance);
            // The board's green glow: a hand card you can play, or your unit that can still attack.
            _playAction = inHand ? Commands.Find(s, a => a.card == instance?.uid && a.type == ActionTypes.Play) : null;
            bool ready = _playAction != null || (!inHand && instance != null && Commands.Find(s, a =>
                a.card == instance.uid && (a.type == ActionTypes.Attack || a.type == ActionTypes.AttackHero)) != null);
            _card.SetMark(ready ? CardMark.Playable : CardMark.None);

            Chip(owner, owner == UiText.OpponentsUnit ? ChipOpponent : owner == UiText.YourUnit ? Palette.HumanAccent : ChipNeutral);
            if (!inHand && instance != null)
            {
                if (instance.attacked) Chip(UiText.Attacked, ChipNeutral);
                if (instance.fresh) Chip(UiText.Fresh, ChipNeutral);
                if (instance.damage > 0) Chip(string.Format(UiText.DamageChip, instance.damage), ChipNeutral);
                if (instance.frozen) Chip(UiText.FrozenChip, ChipOpponent);
                if (instance.hidden) Chip(UiText.HiddenChip, ChipNeutral);
            }

            // A box per keyword (with the server's reminder text), the full card text, the cost
            // gem's rim, and any damage taken.
            int index = 0;
            var keywords = instance?.keywords ?? def.keywords;
            if (keywords != null)
                foreach (var kv in keywords)
                {
                    int value = KeywordValues.Of(keywords, kv.Key);
                    if (value > 0) Tip(CardText.KeywordLabel(kv.Key, value), CardText.KeywordRule(kv.Key, value), index++);
                }
            if (def.ability_text != null && def.ability_text.Count > 0)
            {
                var lines = new List<string>();
                foreach (var line in def.ability_text) lines.Add(CardText.Ability(line));
                Tip(UiText.CardTextTitle, string.Join("\n", lines), index++);
            }
            int health = instance?.health ?? def.health;
            if (instance != null && instance.damage > 0)
                Tip(string.Format(UiText.HealthTitle, health - instance.damage, health),
                    string.Format(UiText.HealthText, instance.damage), index++);

            _buttons.gameObject.SetActive(inHand);
            // Greyed out, not just faded, when the card can't be played now.
            // An unusable card's grey PLAY still answers a tap, with the reason.
            _unusable = inHand ? instance?.unusable : null;
            _play.interactable = _playAction != null || _unusable != null;
            bool playable = _playAction != null;
            Ui.TintButton(_play, playable ? Palette.GlowPlayable : Palette.Muted, playable);
            LayoutRebuilder.ForceRebuildLayoutImmediate(_column);
        }

        public void Hide() => gameObject.SetActive(false);

        void Choose(GameAction action)
        {
            if (action == null) return;
            Hide();
            ActionChosen?.Invoke(action);
        }

        void Chip(string text, Color background)
        {
            var rt = Ui.Node("Chip", _chips);
            Ui.Pill(rt, text, background, 13, display: false);
            _built.Add(rt.gameObject);
        }

        void Tip(string title, string text, int index)
        {
            var rt = Ui.Node("Tip", _column);
            rt.SetSiblingIndex(index);
            Ui.Panel(rt, 12, Palette.Lantern.WithAlpha(0.45f), 0.86f);
            var layout = rt.gameObject.AddComponent<VerticalLayoutGroup>();
            layout.padding = new RectOffset(16, 16, 12, 14);
            layout.spacing = 3;
            layout.childControlWidth = layout.childControlHeight = true;
            layout.childForceExpandWidth = true;
            layout.childForceExpandHeight = false;
            Ui.Display(Ui.Node("Title", rt), title, 18, TextAlignmentOptions.Left).color = Palette.Lantern;
            var body = Ui.Text(Ui.Node("Text", rt), text, Ui.Theme.Body, 14, Palette.TraitText, TextAlignmentOptions.TopLeft);
            body.textWrappingMode = TextWrappingModes.Normal;
            _built.Add(rt.gameObject);
        }
    }

    /// <summary>
    /// The mulligan (not designed yet, kept simple): the hand large; tap cards to pick the ones to
    /// put back (tap again to keep one), then CONFIRM. Picking is local: nothing goes to the server
    /// until CONFIRM, which sends the whole choice as a MulliganCommand.
    /// </summary>
    public class MulliganView : MonoBehaviour, ICardInputHandler
    {
        const float Spacing = 162f;
        static readonly Color BadgeRed = Palette.Hex("#C42A3A");

        /// <summary>CONFIRM: put back these cards (in hand order), then keep the hand.</summary>
        public event Action<IReadOnlyList<int>> KeepRequested;

        /// <summary>The cards picked to put back, in hand order.</summary>
        public IReadOnlyList<int> Selection
        {
            get
            {
                var picked = new List<int>();
                if (_state?.Human.hand != null)
                    foreach (var c in _state.Human.hand)
                        if (_selected.Contains(c.uid)) picked.Add(c.uid);
                return picked;
            }
        }

        RectTransform _cards;
        CardView _prefab;
        Button _keep;
        readonly Dictionary<int, CardView> _views = new Dictionary<int, CardView>();
        readonly HashSet<int> _selected = new HashSet<int>();
        GameState _state;

        public static MulliganView Create(RectTransform parent, CardView prefab)
        {
            var root = Ui.Stretch("Mulligan", parent, 0, 0, 0, 0);
            var view = root.gameObject.AddComponent<MulliganView>();
            view._prefab = prefab;
            Ui.Scrim(root, "Scrim", 0.82f).interactable = false;
            Ui.Display(Ui.TopStrip("Title", root, 0, 70, 40), UiText.MulliganTitle, 32);
            Ui.Body(Ui.TopStrip("Text", root, 0, 116, 24), UiText.MulliganText, 16, Palette.SubtleText,
                TextAlignmentOptions.Center);
            view._cards = Ui.Node("Cards", root);
            Ui.Anchor(view._cards, new Vector2(0.5f, 1), new Vector2(0.5f, 0.5f), new Vector2(0, -345), Vector2.zero);
            var keep = Ui.Node("Keep", root);
            Ui.Anchor(keep, new Vector2(0.5f, 1), new Vector2(0.5f, 1), new Vector2(0, -560), new Vector2(220, 60));
            view._keep = Ui.Button(keep, UiText.Confirm, Palette.Lantern, 21, out _, true);
            view._keep.onClick.AddListener(() => view.KeepRequested?.Invoke(view.Selection));
            root.gameObject.SetActive(false);
            return view;
        }

        public void Show(GameState s, IReadOnlyDictionary<string, CardDef> defs)
        {
            _state = s;
            gameObject.SetActive(true);
            transform.SetAsLastSibling();
            var hand = s.Human.hand ?? new List<CardInstance>();
            var seen = new HashSet<int>();
            // Cards the server already has marked (after a failed CONFIRM) count as picked.
            foreach (int uid in s.Human.mulligan_marked ?? new List<int>()) _selected.Add(uid);

            for (int i = 0; i < hand.Count; i++)
            {
                var c = hand[i];
                seen.Add(c.uid);
                if (!_views.TryGetValue(c.uid, out var v))
                {
                    v = Instantiate(_prefab, _cards);
                    v.Input.Handler = this;
                    _views[c.uid] = v;
                }
                if (defs.TryGetValue(c.card_id, out var def)) v.Bind(def, c);
                v.Rect.anchoredPosition = new Vector2((i - (hand.Count - 1) / 2f) * Spacing, 0f);
            }
            var gone = new List<int>();
            foreach (var kv in _views) if (!seen.Contains(kv.Key)) gone.Add(kv.Key);
            foreach (int uid in gone)
            {
                Destroy(_views[uid].gameObject);
                _views.Remove(uid);
            }
            _selected.IntersectWith(seen);
            var keepAction = Commands.Find(s, a => a.type == ActionTypes.KeepHand);
            _keep.interactable = keepAction != null;
            Refresh();
        }

        public void Hide()
        {
            if (!gameObject.activeSelf) return;
            gameObject.SetActive(false);
            foreach (var v in _views.Values) Destroy(v.gameObject);
            _views.Clear();
            _selected.Clear();
        }

        /// <summary>Picks or unpicks a card. Only cards with a legal mulligan action can be picked.</summary>
        public void OnCardTap(CardView card)
        {
            if (_state == null) return;
            if (!_selected.Remove(card.Uid))
            {
                if (Commands.Find(_state, a => a.type == ActionTypes.Mulligan && a.card == card.Uid) == null) return;
                _selected.Add(card.Uid);
            }
            Refresh();
        }

        void Refresh()
        {
            foreach (var kv in _views)
            {
                bool picked = _selected.Contains(kv.Key);
                kv.Value.SetDarkened(picked);
                kv.Value.SetBadge(picked ? UiText.PutBack : null, BadgeRed);
            }
        }

        public bool OnCardDragStart(CardView card, PointerEventData e) => false;
        public void OnCardDrag(CardView card, PointerEventData e) { }
        public void OnCardDragEnd(CardView card, PointerEventData e) { }
    }

    /// <summary>Game over (not designed yet, kept simple): the result, final VP and NEW GAME.</summary>
    public class GameOverView : MonoBehaviour
    {
        public event Action NewGameRequested;
        TMP_Text _title, _score;

        public static GameOverView Create(RectTransform parent)
        {
            var root = Ui.Stretch("GameOver", parent, 0, 0, 0, 0);
            var view = root.gameObject.AddComponent<GameOverView>();
            Ui.Scrim(root, "Scrim", 0.7f).interactable = false;
            var panel = Ui.Node("Panel", root);
            Ui.Anchor(panel, new Vector2(0.5f, 0.5f), new Vector2(0.5f, 0.5f), new Vector2(0, 20), new Vector2(460, 270));
            Ui.Panel(panel, 18, Palette.Lantern.WithAlpha(0.5f), 0.9f);
            view._title = Ui.Display(Ui.TopStrip("Title", panel, 0, 34, 60), "", 48);
            view._title.characterSpacing = 10f;
            view._score = Ui.Text(Ui.TopStrip("Score", panel, 0, 104, 30), "", Ui.Theme.BodyBold, 20, Color.white,
                TextAlignmentOptions.Center);
            var button = Ui.Node("NewGame", panel);
            Ui.Anchor(button, new Vector2(0.5f, 0), new Vector2(0.5f, 0), new Vector2(0, 30), new Vector2(220, 60));
            Ui.Button(button, UiText.NewGame, Palette.Lantern, 21, out _, true)
                .onClick.AddListener(() => view.NewGameRequested?.Invoke());
            root.gameObject.SetActive(false);
            return view;
        }

        public void Show(GameState s, string opponentName)
        {
            gameObject.SetActive(true);
            transform.SetAsLastSibling();
            _title.text = s.winner == null ? UiText.Draw : s.winner == s.human_seat ? UiText.YouWin : UiText.YouLose;
            _score.text = string.Format(UiText.FinalScore, UiText.You, Mathf.Max(s.Human.health, 0), opponentName,
                Mathf.Max(s.Opponent.health, 0));
        }

        public void Hide() => gameObject.SetActive(false);
    }
}
