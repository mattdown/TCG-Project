using System;
using System.Collections.Generic;
using Tcg.Protocol;
using Tcg.View;
using TMPro;
using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.UI;

namespace Tcg.Board
{
    /// <summary>
    /// Tap to inspect (the mockup's "Landscape inspect"): the card at about 2x over a dimmed board,
    /// a box for anything that needs explaining, and PLAY / ADD ENERGY for hand cards, enabled only
    /// when the matching legal action exists. Tap anywhere to close.
    /// </summary>
    public class InspectView : MonoBehaviour
    {
        const float Scale = 2.1f;
        static readonly Color ChipOpponent = Palette.Hex("#A8321F");
        static readonly Color ChipNeutral = Palette.Hex("#2E4680");
        static readonly Color PlayFace = Palette.Hex("#5BC84E"), PlayLip = Palette.Hex("#2F8A27");

        public event Action<GameAction> ActionChosen;
        public bool IsOpen => gameObject.activeSelf;

        CardView _card;
        RectTransform _chips, _column, _buttons;
        Button _play;
        TMP_Text _playText;
        GameObject _note;
        readonly List<GameObject> _built = new List<GameObject>();
        GameAction _playAction;

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

            view._column = Ui.Box("Column", root, 660, 122, 340, 400);
            var col = view._column.gameObject.AddComponent<VerticalLayoutGroup>();
            col.spacing = 12;
            col.childControlWidth = col.childControlHeight = true;
            col.childForceExpandWidth = true;
            col.childForceExpandHeight = false;
            view._column.gameObject.AddComponent<ContentSizeFitter>().verticalFit = ContentSizeFitter.FitMode.PreferredSize;

            view._buttons = Ui.Node("Buttons", view._column);
            var buttonsSize = view._buttons.gameObject.AddComponent<LayoutElement>();
            buttonsSize.minHeight = buttonsSize.preferredHeight = 66;
            buttonsSize.flexibleHeight = 0;
            var row = view._buttons.gameObject.AddComponent<HorizontalLayoutGroup>();
            row.spacing = 12;
            row.padding = new RectOffset(0, 0, 10, 0);
            row.childControlWidth = row.childControlHeight = true;
            row.childForceExpandWidth = row.childForceExpandHeight = true;
            view._play = Ui.Button(Ui.Node("Play", view._buttons), "PLAY", PlayFace, PlayLip, 19, out view._playText);
            view._play.onClick.AddListener(() => view.Choose(view._playAction));
            view._note = Ui.Body(Ui.Node("Note", view._column), UiText.ButtonsNote, 13, Palette.SubtleText).gameObject;

            Ui.Body(Ui.TopStrip("Hint", root, 0, 652, 24), UiText.TapToClose, 14, Palette.SubtleText,
                TextAlignmentOptions.Center);
            root.gameObject.SetActive(false);
            return view;
        }

        public void Show(CardDef def, CardInstance instance, string owner, bool inHand, GameState s)
        {
            foreach (var go in _built) Destroy(go);
            _built.Clear();
            gameObject.SetActive(true);
            transform.SetAsLastSibling();
            _card.Bind(def, instance);
            _card.SetMark(CardMark.None);

            Chip(owner, owner == UiText.OpponentsUnit ? ChipOpponent : owner == UiText.YourUnit ? Palette.HumanAccent : ChipNeutral);
            if (!inHand && instance != null)
            {
                if (instance.exhausted) Chip(UiText.Exhausted, ChipNeutral);
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

            // ⟳ abilities this unit can use now, labelled with the action's text minus the card name.
            foreach (var a in s.legal_actions)
            {
                if (a.type != ActionTypes.Activate || a.card != instance?.uid) continue;
                string label = a.text.StartsWith(def.name + ": ") ? a.text.Substring(def.name.Length + 2) : a.text;
                var rt = Ui.Node("Activate", _column);
                rt.SetSiblingIndex(index++);
                var size = rt.gameObject.AddComponent<LayoutElement>();
                size.minHeight = size.preferredHeight = 60;
                var action = a;
                Ui.Button(rt, label, Palette.Gold, Palette.GoldLip, 16, out var text).onClick.AddListener(() => Choose(action));
                text.textWrappingMode = TextWrappingModes.Normal;
                _built.Add(rt.gameObject);
            }

            _buttons.gameObject.SetActive(inHand);
            _note.SetActive(inHand);
            if (inHand)
            {
                _playAction = null;
                foreach (var a in s.legal_actions)
                    if (a.card == instance?.uid && a.type == ActionTypes.Play) _playAction = a;
                int cost = _playAction?.preview != null ? _playAction.preview.ManaFor(s.human_seat) : instance?.cost ?? def.cost;
                _playText.text = string.Format(UiText.PlayButton, cost);
                _play.interactable = _playAction != null;
            }
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
            Ui.Rounded(rt, Palette.Outline, 12);
            var ring = Ui.Rounded(Ui.Stretch("Ring", rt, 3, 3, 3, 3), ChipNeutral, 9);
            ring.gameObject.AddComponent<LayoutElement>().ignoreLayout = true;
            var face = Ui.Rounded(Ui.Stretch("Face", rt, 5, 5, 5, 5), Palette.CardNavy, 7);
            face.gameObject.AddComponent<LayoutElement>().ignoreLayout = true;
            var layout = rt.gameObject.AddComponent<VerticalLayoutGroup>();
            layout.padding = new RectOffset(16, 16, 12, 14);
            layout.spacing = 3;
            layout.childControlWidth = layout.childControlHeight = true;
            layout.childForceExpandWidth = true;
            layout.childForceExpandHeight = false;
            Ui.Display(Ui.Node("Title", rt), title, 18, TextAlignmentOptions.Left);
            var body = Ui.Text(Ui.Node("Text", rt), text, Ui.Theme.Nunito, 14, Palette.TraitText, TextAlignmentOptions.TopLeft);
            body.textWrappingMode = TextWrappingModes.Normal;
            _built.Add(rt.gameObject);
        }
    }

    /// <summary>
    /// The mulligan (not designed yet, kept simple): the hand large; tap cards to pick the ones to
    /// put back (tap again to keep one), then KEEP. Picking is local: nothing goes to the server
    /// until KEEP, which sends the whole choice as a MulliganCommand.
    /// </summary>
    public class MulliganView : MonoBehaviour, ICardInputHandler
    {
        const float Spacing = 162f;
        static readonly Color BadgeRed = Palette.Hex("#C42A3A");

        /// <summary>KEEP: put back these cards (in hand order), then keep the hand.</summary>
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
        TMP_Text _keepText;
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
            view._keep = Ui.Button(keep, UiText.Keep, Palette.Gold, Palette.GoldLip, 22, out view._keepText);
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
            // Cards the server already has marked (after a failed KEEP) count as picked.
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
            _keepText.text = keepAction != null ? keepAction.text.ToUpperInvariant() : UiText.Keep;
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
                kv.Value.SetDimmed(picked);
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
            Ui.Rounded(panel, Palette.Outline, 18);
            Ui.Rounded(Ui.Stretch("Ring", panel, 3, 3, 3, 3), Palette.Hex("#2E4680"), 15);
            Ui.Rounded(Ui.Stretch("Face", panel, 6, 6, 6, 6), Palette.UiNavy, 12);
            view._title = Ui.Display(Ui.TopStrip("Title", panel, 0, 34, 60), "", 48);
            view._title.color = Palette.Gold;
            view._score = Ui.Text(Ui.TopStrip("Score", panel, 0, 104, 30), "", Ui.Theme.NunitoBlack, 20, Color.white,
                TextAlignmentOptions.Center);
            var button = Ui.Node("NewGame", panel);
            Ui.Anchor(button, new Vector2(0.5f, 0), new Vector2(0.5f, 0), new Vector2(0, 30), new Vector2(220, 60));
            Ui.Button(button, UiText.NewGame, Palette.Gold, Palette.GoldLip, 22, out _)
                .onClick.AddListener(() => view.NewGameRequested?.Invoke());
            root.gameObject.SetActive(false);
            return view;
        }

        public void Show(GameState s, string opponentName)
        {
            gameObject.SetActive(true);
            transform.SetAsLastSibling();
            _title.text = s.winner == null ? UiText.Draw : s.winner == s.human_seat ? UiText.YouWin : UiText.YouLose;
            _score.text = string.Format(UiText.FinalScore, UiText.You, s.Human.health, opponentName, s.Opponent.health);
        }

        public void Hide() => gameObject.SetActive(false);
    }
}
